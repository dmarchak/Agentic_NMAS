"""An app version's plain test run (C2854; `modules/apps/test_run.py`): the app's listed tests
in a fresh container of the harness's app test image, on the network's controller Python,
never in Mercury's process (C2635).

The docker seam is a fake here (the suite starts no container: its children are confined), fed
pytest's real output, captured from the image on Python 3.5 (pytest 6.1.2) and 3.9 (pytest
8.4.2) on 2026-11-09 (tests/fixtures/app_test_runs/, `pytest-<case>-py<python>.txt`, each
unedited). The run itself, for real, is `scripts/nmas-harness check`'s self-check (the worked
app passes, a copy with one assert broken fails) and the walk with `scripts/nmas-harness test`.

Held here: the exact `docker run` argv, every isolation flag in it; a pass only when pytest
exited 0, a test ran, the counts parsed, nothing skipped, the interpreter is the one asked for
and the folder did not move; a failing test, an error, zero collected, a skip, a timeout (the
container killed by its name), docker absent, docker not answering and the image not built each
`ok: False` naming which, never an exception; the content hash recomputed from the folder (the
hash `channel.stage` pins); the output masked before it is cut.
"""

import os
import subprocess
import sys
import types

import pytest

from modules.apps import channel, test_run

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURES = os.path.join(ROOT, "tests", "fixtures", "app_test_runs")
#: Docker 29.1.3's own words, captured on the laptop 2026-11-09.
NO_IMAGE = "Error response from daemon: No such image: mercury-harness-apptest:4.34-py3.5\n"
NO_DAEMON = ("failed to connect to the docker API at unix:///nonexistent.sock; check if the "
             "path is correct and if the daemon is running: dial unix /nonexistent.sock: "
             "connect: no such file or directory\n")
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def capture(case, python="3.5") -> bytes:
    with open(os.path.join(CAPTURES, f"pytest-{case}-py{python}.txt"), "rb") as fh:
        return fh.read()


class FakeDocker:
    """The runner seam: `docker image inspect` answers *inspect*, `docker run` answers
    *returncode* and *stdout* (or raises *run_raises*), `docker kill` answers *kill*; every
    argv is kept in `calls`."""

    def __init__(self, stdout=b"", returncode=0, stderr=b"", inspect=(0, b"sha256:ab\n", b""),
                 run_raises=None, inspect_raises=None, kill=(0, b"", b""), during=None):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.inspect, self.kill = inspect, kill
        self.run_raises, self.inspect_raises, self.during = run_raises, inspect_raises, during
        self.calls = []

    def __call__(self, argv, timeout_s):
        self.calls.append((list(argv), timeout_s))
        if argv[1:3] == ["image", "inspect"]:
            if self.inspect_raises:
                raise self.inspect_raises
            rc, out, err = self.inspect
            return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)
        if argv[1] == "kill":
            rc, out, err = self.kill
            return types.SimpleNamespace(returncode=rc, stdout=out, stderr=err)
        assert argv[1] == "run", argv
        if self.during:
            self.during()
        if self.run_raises:
            raise self.run_raises
        return types.SimpleNamespace(returncode=self.returncode, stdout=self.stdout,
                                     stderr=self.stderr)

    def ran(self):
        return [argv for argv, _ in self.calls if argv[1] == "run"]


def app(tmp_path, tests=("tests/test_logic.py",)):
    folder = tmp_path / "app"
    (folder / "tests").mkdir(parents=True)
    (folder / "logic.py").write_text("def add(a, b):\n    return a + b\n")
    for test in tests:
        (folder / test).write_text("from logic import add\n\n\ndef test_add():\n"
                                   "    assert add(1, 1) == 2\n")
    return str(folder)


def go(folder, fake, python="3.5", tests=("tests/test_logic.py",), timeout_s=7.0):
    return test_run.run(folder, python, tests=list(tests), timeout_s=timeout_s, runner=fake)


# ───────────────────────────────────────────────────────────── the command

def test_the_command_is_exactly_the_isolated_run_of_the_listed_tests(tmp_path):
    folder = app(tmp_path, tests=("tests/test_logic.py", "tests/test_more.py"))
    fake = FakeDocker(stdout=capture("pass"))
    got = go(folder, fake, tests=("tests/test_logic.py", "tests/test_more.py"))
    assert fake.calls[0] == (["docker", "image", "inspect", "--format", "{{.Id}}",
                              "mercury-harness-apptest:4.34-py3.5"], test_run.DOCKER_BOUND_S)
    [argv] = fake.ran()
    name = argv[argv.index("--name") + 1]
    assert name.startswith("mercury-apptest-") and len(name) == len("mercury-apptest-") + 12
    real = os.path.realpath(folder)
    assert argv == [
        "docker", "run", "--rm", "--pull", "never", "--name", name,
        "--privileged=false", "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
        "--user", "10001:10001", "--pids-limit", "64", "--tmpfs", "/tmp:size=16m",
        "--mount", f"type=bind,src={real},dst=/app,readonly",
        "--mount", f"type=bind,src={test_run.SDK},dst=/opt/mercury-sdk,readonly",
        "-e", "PYTHONDONTWRITEBYTECODE=1", "-e", "PYTHONPATH=/app:/opt/mercury-sdk",
        "-e", "HOME=/tmp", "-w", "/app", "--entrypoint", "python",
        "mercury-harness-apptest:4.34-py3.5",
        "-B", "-m", "pytest", "-p", "no:cacheprovider", "-c", "/dev/null", "--rootdir", "/app",
        "--color=no", "-rfE", "--", "tests/test_logic.py", "tests/test_more.py"]
    assert fake.calls[1][1] == 7.0, "the caller's bound is the run's"
    assert got["command"] == argv
    assert os.path.isdir(os.path.join(test_run.SDK, "mercury_app"))


def test_each_run_is_a_fresh_container_with_its_own_name(tmp_path):
    folder = app(tmp_path)
    fake = FakeDocker(stdout=capture("pass"))
    go(folder, fake)
    go(folder, fake)
    names = [argv[argv.index("--name") + 1] for argv in fake.ran()]
    assert len(set(names)) == 2 and all("--rm" in argv for argv in fake.ran())


def test_the_default_runner_takes_an_argv_list_and_never_a_shell(tmp_path):
    got = test_run.default_runner([sys.executable, "-c", "print('a b')"], 30)
    assert got.returncode == 0 and got.stdout == b"a b\n"
    with pytest.raises(FileNotFoundError):     # a string is one program's name, never a shell
        test_run.default_runner(f"{sys.executable} -c 'print(1)'", 30)
    with pytest.raises(subprocess.TimeoutExpired):
        test_run.default_runner([sys.executable, "-c", "import time; time.sleep(30)"], 0.5)


# ───────────────────────────────────────────────────────────── the verdict

@pytest.mark.parametrize("python, pytest_version", [("3.5", "6.1.2"), ("3.9", "8.4.2")])
def test_a_passing_run_is_ok_with_its_counts_its_python_and_its_hash(tmp_path, python,
                                                                     pytest_version):
    folder = app(tmp_path)
    out = capture("pass", python)
    assert f"pytest-{pytest_version}".encode() in out
    got = go(folder, FakeDocker(stdout=out), python=python)
    assert got["ok"] is True, got["error"]
    assert (got["passed"], got["failed"], got["errors"], got["skipped"]) == (2, 0, 0, 0)
    assert got["python"] == python and got["python_seen"] == python
    assert got["error"] == "" and got["output"] == out.decode()
    assert got["content_sha256"] == channel.script().folder_hash(folder)
    assert isinstance(got["seconds"], float)


@pytest.mark.parametrize("python", ["3.5", "3.9"])
def test_a_failing_test_is_not_ok_and_names_the_counts(tmp_path, python):
    got = go(app(tmp_path), FakeDocker(stdout=capture("fail", python), returncode=1),
             python=python)
    assert got["ok"] is False
    assert (got["passed"], got["failed"], got["errors"]) == (1, 1, 0)
    assert got["error"] == "pytest exited 1: 1 failed, 0 errors, 1 passed"
    assert "FAILED tests/test_case.py::test_two" in got["output"]


@pytest.mark.parametrize("python", ["3.5", "3.9"])
def test_an_error_collecting_is_not_ok(tmp_path, python):
    got = go(app(tmp_path), FakeDocker(stdout=capture("error", python), returncode=2),
             python=python)
    assert got["ok"] is False and got["errors"] == 1 and got["passed"] == 0
    assert got["error"] == "pytest exited 2: 0 failed, 1 errors, 0 passed"


@pytest.mark.parametrize("python", ["3.5", "3.9"])
@pytest.mark.parametrize("returncode", [5, 0])
def test_zero_collected_is_never_a_pass_whatever_the_exit(tmp_path, python, returncode):
    got = go(app(tmp_path), FakeDocker(stdout=capture("none", python), returncode=returncode),
             python=python)
    assert got["ok"] is False and got["passed"] == 0
    assert got["error"] == (f"no test ran (pytest exited {returncode}): collecting nothing is "
                            "not a pass")


@pytest.mark.parametrize("python", ["3.5", "3.9"])
def test_a_skipped_test_is_not_a_pass(tmp_path, python):
    got = go(app(tmp_path), FakeDocker(stdout=capture("skip", python)), python=python)
    assert got["ok"] is False and got["passed"] == 1 and got["skipped"] == 1
    assert got["error"] == "1 skipped: a test that did not run as written is not a pass"


def test_a_pass_summary_with_a_nonzero_exit_is_not_ok(tmp_path):
    got = go(app(tmp_path), FakeDocker(stdout=capture("pass"), returncode=3))
    assert got["ok"] is False and got["error"] == "pytest exited 3: 0 failed, 0 errors, 2 passed"


def test_counts_that_do_not_parse_are_not_ok(tmp_path):
    out = capture("pass").replace(b"2 passed in", b"2 passes in")
    got = go(app(tmp_path), FakeDocker(stdout=out))
    assert got["ok"] is False
    assert got["error"] == "pytest's summary line did not parse (pytest exited 0), so its " \
                           "counts are unknown"
    no_summary = b"\n".join(capture("pass").rstrip(b"\n").split(b"\n")[:-1]) + b"\n"
    got = go(app(tmp_path / "b"), FakeDocker(stdout=no_summary))
    assert got["ok"] is False and "did not parse" in got["error"]
    got = go(app(tmp_path / "c"), FakeDocker(stdout=b"something else entirely\n"))
    assert got["ok"] is False and got["error"] == ("pytest reported Python nothing (its "
                                                   "header), the network's controller Python "
                                                   "is 3.5")


def test_another_python_than_the_one_asked_for_is_not_ok(tmp_path):
    got = go(app(tmp_path), FakeDocker(stdout=capture("pass", "3.9")), python="3.5")
    assert got["ok"] is False and got["python_seen"] == "3.9"
    assert got["error"] == ("pytest reported Python 3.9 (its header), the network's controller "
                            "Python is 3.5")


def test_the_folder_moving_during_the_run_is_not_ok_naming_both_hashes(tmp_path):
    folder = app(tmp_path)
    before = channel.script().folder_hash(folder)

    def edit():
        with open(os.path.join(folder, "logic.py"), "a") as fh:
            fh.write("# moved\n")

    got = go(folder, FakeDocker(stdout=capture("pass"), during=edit))
    after = channel.script().folder_hash(folder)
    assert got["ok"] is False and got["content_sha256"] == before
    assert got["error"] == (f"the folder's content hash moved during the run: {before} before, "
                            f"{after} after, so what passed is not what is pinned")


# ───────────────────────────────────────────────────────────── what cannot run is said

def test_a_timeout_kills_the_container_by_its_name_and_is_not_ok(tmp_path):
    fake = FakeDocker(run_raises=subprocess.TimeoutExpired(["docker"], 7.0,
                                                           output=b"collected 2 items\n"))
    got = go(app(tmp_path), fake)
    [run_argv] = fake.ran()
    name = run_argv[run_argv.index("--name") + 1]
    assert fake.calls[-1] == (["docker", "kill", name], test_run.DOCKER_BOUND_S)
    assert got["ok"] is False and got["seconds"] is None
    assert got["error"] == f"the test run passed its bound of 7 s: container {name} killed"
    assert got["output"] == "collected 2 items\n"


def test_a_timeout_whose_kill_fails_says_so(tmp_path):
    fake = FakeDocker(run_raises=subprocess.TimeoutExpired(["docker"], 7.0),
                      kill=(1, b"", b"Error response from daemon: cannot kill container\n"))
    got = go(app(tmp_path), fake)
    assert got["ok"] is False and "not killed: `docker kill mercury-apptest-" in got["error"]
    assert "exited 1, Error response from daemon: cannot kill container" in got["error"]


def test_docker_absent_is_not_ok_naming_it(tmp_path):
    fake = FakeDocker(inspect_raises=FileNotFoundError(2, "No such file or directory"))
    got = go(app(tmp_path), fake)
    assert got["ok"] is False and fake.ran() == []
    assert got["error"] == ("docker is not installed here (no `docker` on PATH), so the app's "
                            "tests cannot run")


def test_the_image_not_built_is_not_ok_naming_how_to_build_it(tmp_path):
    fake = FakeDocker(inspect=(1, b"[]\n", NO_IMAGE.encode()))
    got = go(app(tmp_path), fake)
    assert got["ok"] is False and fake.ran() == []
    assert got["error"] == ("the test image mercury-harness-apptest:4.34-py3.5 is not built: "
                            "`scripts/nmas-harness test --python 3.5 --app <folder>` builds it")


def test_docker_not_answering_is_not_ok_with_its_words(tmp_path):
    got = go(app(tmp_path), FakeDocker(inspect=(1, b"", NO_DAEMON.encode())))
    assert got["ok"] is False
    assert got["error"] == ("docker could not inspect mercury-harness-apptest:4.34-py3.5 "
                            f"(exit 1): {NO_DAEMON.strip()}")
    fake = FakeDocker(inspect_raises=subprocess.TimeoutExpired(["docker"], 5))
    got = go(app(tmp_path / "b"), fake)
    assert got["ok"] is False and got["error"] == (
        f"docker did not answer `docker image inspect mercury-harness-apptest:4.34-py3.5` "
        f"within {test_run.DOCKER_BOUND_S:g} s")


def test_a_container_docker_could_not_start_is_not_ok(tmp_path):
    fake = FakeDocker(returncode=125, stderr=b"docker: Error response from daemon: invalid "
                                             b"mount config\n")
    got = go(app(tmp_path), fake)
    assert got["ok"] is False and got["error"].startswith(
        "docker could not run the container of mercury-harness-apptest:4.34-py3.5 (exit 125): "
        "docker: Error response from daemon: invalid mount config")


@pytest.mark.parametrize("tests, words", [
    ((), "the manifest lists no tests: a run of nothing is not a pass"),
    (("/etc/test_x.py",), "the test '/etc/test_x.py' is not a plain path inside"),
    (("../test_x.py",), "the test '../test_x.py' is not a plain path inside"),
    (("tests/../tests/test_logic.py",), "is not a plain path inside"),
    (("tests/logic_check.py",), "the test 'tests/logic_check.py' is not a test_*.py file"),
    (("tests/test_absent.py",), "the test 'tests/test_absent.py' is not a file in"),
])
def test_a_test_list_that_is_not_the_folders_tests_runs_nothing(tmp_path, tests, words):
    fake = FakeDocker(stdout=capture("pass"))
    got = go(app(tmp_path), fake, tests=tests)
    assert got["ok"] is False and words in got["error"] and fake.calls == []


@pytest.mark.parametrize("python", ["3", "", "3.5.10", "py3.5"])
def test_a_python_that_is_not_major_minor_runs_nothing(tmp_path, python):
    fake = FakeDocker(stdout=capture("pass"))
    got = go(app(tmp_path), fake, python=python)
    assert got["ok"] is False and fake.calls == []
    assert got["error"].startswith("the controller's Python is major.minor (such as 3.5)")


def test_a_file_the_containers_account_cannot_read_runs_nothing_naming_it(tmp_path):
    folder = app(tmp_path)
    os.chmod(os.path.join(folder, "logic.py"), 0o600)
    fake = FakeDocker(stdout=capture("pass"))
    got = go(folder, fake)
    assert got["ok"] is False and fake.calls == []
    assert got["error"] == (f"logic.py in {os.path.realpath(folder)} is mode -rw-------: the "
                            "test container's account (uid 10001) cannot read it")


def test_a_folder_that_is_not_one_runs_nothing(tmp_path):
    fake = FakeDocker()
    got = go(str(tmp_path / "absent"), fake)
    assert got["ok"] is False and got["error"].endswith("absent is not a folder")
    assert fake.calls == []


# ───────────────────────────────────────────────────────────── the hash and the output

def test_the_hash_is_the_one_a_staged_version_is_pinned_to(tmp_path):
    repo = tmp_path / "code"
    folder = repo / "apps" / "adder"
    (folder / "tests").mkdir(parents=True)
    (folder / "adder.py").write_text("def add(a, b):\n    return a + b\n")
    (folder / "tests" / "test_adder.py").write_text("def test_one():\n    assert True\n")
    for args in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "app")):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                       env=dict(os.environ, **GIT_ENV))
    staged = channel.stage(repo, "apps/adder", "HEAD", str(tmp_path / "stage"))
    got = go(staged["folder"], FakeDocker(stdout=capture("pass")),
             tests=("tests/test_adder.py",))
    assert got["ok"] is True and got["content_sha256"] == staged["sha256"]
    with open(os.path.join(staged["folder"], "adder.py"), "a") as fh:
        fh.write("# one byte more\n")
    moved = go(staged["folder"], FakeDocker(stdout=capture("pass")),
               tests=("tests/test_adder.py",))
    assert moved["content_sha256"] != staged["sha256"]


def test_the_output_is_masked(tmp_path):
    out = capture("fail", "3.9")
    assert b"Leaky-Comm-4471" in out, "the capture holds no secret, so this proves nothing"
    got = go(app(tmp_path), FakeDocker(stdout=out, returncode=1), python="3.9")
    assert "Leaky-Comm-4471" not in got["output"]
    assert "snmp-server community <redacted:snmp_community> RO" in got["output"]


def test_the_output_is_masked_before_it_is_cut(tmp_path):
    secret = b"snmp-server community Leaky-Comm-4471 RO\n"
    tail = capture("pass")
    # Cut first, the tail would begin inside the secret's line, past the words that mark it.
    lead = test_run.OUTPUT_TAIL - len(tail) - len(b"Comm-4471 RO\n")
    out = b"x" * 5000 + b"\n" + secret + b"y" * lead + b"\n" + tail
    assert b"Comm-4471 RO" in out[-test_run.OUTPUT_TAIL - 14:]
    got = go(app(tmp_path), FakeDocker(stdout=out))
    assert got["ok"] is True and len(got["output"]) <= test_run.OUTPUT_TAIL
    assert "4471" not in got["output"]


def test_stderr_is_kept_after_stdout_and_masked(tmp_path):
    got = go(app(tmp_path), FakeDocker(stdout=capture("pass"),
                                       stderr=b"warning: snmp-server community Leaky-Comm-4471 "
                                              b"RO\n"))
    assert got["ok"] is True
    assert got["output"].endswith("warning: snmp-server community <redacted:snmp_community> "
                                  "RO\n")
