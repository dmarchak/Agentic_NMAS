"""The controller's apply script, `deploy/controller/mercury-ryu-apply` (the SDN platform design
revision 6, section 10 H, change C and C2; T13's change C and C2 cases; P6).

The script is loaded as a module, with its installed constants pointed into a temporary root
(the apps folder, the drop-in folder, the outcome folder) and `systemctl` replaced by a stub that
reads the drop-in's `User=` when it restarts, as systemd does. The deploy account is the user
running the test (no test runs as root); a refusal naming another owner is planted by naming
another account, or by the file's stat. Every refusal is planted, and after each the drop-in
holds what it held before. The script is also held to the controller's Python 3.5 by Mercury's
own check (`modules/apps/python_versions`), and the host step that installs it is held to the
lines it renders."""

import ast
import hashlib
import importlib.machinery
import importlib.util
import itertools
import json
import os
import pwd
import stat
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "deploy", "controller", "mercury-ryu-apply")
HOST_STEP = os.path.join(ROOT, "scripts", "host-steps", "p6-controller-apply-install.sh")
ME = pwd.getpwuid(os.getuid()).pw_name
UNIT = "ryu-manager.service"
MANAGER = "/opt/ryu-venv/bin/ryu-manager"
_names = itertools.count()


class Systemctl:
    """`systemctl` as the script calls it: `show -p ...`, `cat`, `daemon-reload`, `restart`. A
    restart starts a new MainPID and takes its User from the script's drop-in, as systemd
    would. `cat` answers as systemd does: the unit's own file (*unit_file*), then every drop-in
    in name order, each under its `# <path>` line: the planted ones (*dropins*) and
    mercury.conf as it is on disk."""

    def __init__(self, m, user="ryu", comes_up=True):
        self.m, self.calls, self.comes_up = m, [], comes_up
        self.props = {"User": user, "MainPID": "100", "ActiveState": "active"}
        self.unit_file = f"[Service]\nExecStart={MANAGER}\n"
        self.dropins = {}

    def cat(self) -> str:
        folder = os.path.join(self.m.DROPIN_ROOT, UNIT + ".d")
        texts = dict(self.dropins)
        mine = os.path.join(folder, "mercury.conf")
        if os.path.exists(mine):
            texts["mercury.conf"] = open(mine).read()
        return f"# /lib/systemd/system/{UNIT}\n{self.unit_file}" + "".join(
            f"\n# {folder}/{name}\n{texts[name]}" for name in sorted(texts))

    def __call__(self, *args):
        self.calls.append(args)
        if args[0] == "show":
            names = [args[i + 1] for i, a in enumerate(args) if a == "-p"]
            return 0, "".join(f"{n}={self.props.get(n, '')}\n" for n in names), ""
        if args[0] == "cat":
            return 0, self.cat(), ""
        if args[0] == "restart":
            path = os.path.join(self.m.DROPIN_ROOT, UNIT + ".d", "mercury.conf")
            users = [line[5:] for line in open(path).read().splitlines()
                     if line.startswith("User=")]
            self.props["User"] = users[-1] if users else ""
            self.props["MainPID"] = str(int(self.props["MainPID"]) + 1)
            self.props["ActiveState"] = "active" if self.comes_up else "failed"
        return 0, "", ""


def load(tmp_path, user="ryu", comes_up=True, account=ME, render=True):
    """A fresh copy of the script, its constants in *tmp_path*, its systemctl a stub."""
    loader = importlib.machinery.SourceFileLoader(f"mercury_ryu_apply_{next(_names)}", SCRIPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    if render:
        m.RYU_UNIT, m.RYU_MANAGER = UNIT, MANAGER
    m.DEPLOY_USER, m.REQUIRE_ROOT = account, False
    m.APPS_ROOT = str(tmp_path / "opt" / "ryu-apps")
    m.DROPIN_ROOT = str(tmp_path / "etc" / "systemd" / "system")
    m.OUTCOME_DIR = str(tmp_path / "var" / "lib" / "mercury-ryu-apply")
    m.UP_BOUND_S, m.POLL_S = 0.2, 0.01
    os.makedirs(os.path.join(m.APPS_ROOT, ".apply"), mode=0o700)
    os.chmod(m.APPS_ROOT, 0o755)
    os.makedirs(os.path.join(m.DROPIN_ROOT, UNIT + ".d"))
    m.systemctl = Systemctl(m, user=user, comes_up=comes_up)
    return m


BEFORE = "[Service]\nUser=ryu\n"


def dropin(m) -> str:
    return open(os.path.join(m.DROPIN_ROOT, UNIT + ".d", "mercury.conf")).read()


def put_dropin(m, text=BEFORE):
    with open(os.path.join(m.DROPIN_ROOT, UNIT + ".d", "mercury.conf"), "w") as fh:
        fh.write(text)


def stage_app(m, name="of_versions", version="1.0.0", files=None) -> str:
    """An app folder staged under the apps folder; returns its hash, as the script computes."""
    folder = os.path.join(m.APPS_ROOT, name, version)
    files = files or {f"{name}.py": b"OFP_VERSIONS = [1, 4]\n", "manifest.yml": b"name: x\n"}
    for rel, data in files.items():
        path = os.path.join(folder, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
        os.chmod(path, 0o644)
    for root, dirs, _ in os.walk(folder):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o755)
    os.chmod(folder, 0o755)
    return m.folder_hash(folder)


def put_request(m, apps, host="192.0.2.10", port=6653, raw=None):
    path = os.path.join(m.APPS_ROOT, ".apply", "request.json")
    body = raw if raw is not None else json.dumps(
        {"apps": apps, "listen": {"host": host, "port": port}}).encode()
    with open(path, "wb") as fh:
        fh.write(body)
    return path


def run(m, argv=()):
    """The script's main, its printed outcome returned parsed."""
    m.main(list(argv))
    with open(os.path.join(m.OUTCOME_DIR, "outcome.json")) as fh:
        return json.load(fh)


def ready(tmp_path, **kw):
    m = load(tmp_path, **kw)
    put_dropin(m)
    sha = stage_app(m)
    req = put_request(m, [{"name": "of_versions", "version": "1.0.0", "sha256": sha}])
    return m, sha, req


# ── a deploy ──────────────────────────────────────────────────────────────────────────────────

def test_a_request_renders_the_one_drop_in_keeps_the_previous_and_restarts_by_identity(tmp_path):
    m, sha, req = ready(tmp_path)
    out = run(m)
    assert out["ok"] is True, out
    assert out["main_pid_before"] == "100" and out["main_pid_after"] == "101"
    assert out["user"] == "ryu" and out["active_state"] == "active"
    text = dropin(m)
    folder = os.path.join(m.APPS_ROOT, "of_versions", "1.0.0", "of_versions.py")
    assert text.splitlines()[1:] == [
        "[Service]", "User=ryu", "ExecStart=",
        f"ExecStart={MANAGER} --observe-links --ofp-listen-host 192.0.2.10 "
        f"--ofp-tcp-listen-port 6653 {folder} ryu.app.ofctl_rest ryu.app.rest_topology"]
    assert open(os.path.join(m.DROPIN_ROOT, UNIT + ".d", "mercury.conf.prev")).read() == BEFORE
    # It reads the unit (`show`, and `cat` for the unit's own command line), then acts.
    assert [c[0] for c in m.systemctl.calls if c[0] != "show"] == ["cat", "daemon-reload",
                                                                   "restart"]
    assert not os.path.exists(req), "a request is applied once: it is removed once read"
    history = open(os.path.join(m.OUTCOME_DIR, "history.jsonl")).read().splitlines()
    assert len(history) == 1 and json.loads(history[0])["request_sha256"] == out["request_sha256"]


def test_an_ipv6_listen_address_is_rendered_as_parsed(tmp_path):
    m = load(tmp_path)
    put_dropin(m)
    sha = stage_app(m)
    put_request(m, [{"name": "of_versions", "version": "1.0.0", "sha256": sha}],
                host="2001:db8:0::10")
    out = run(m)
    assert out["ok"] is True, out
    assert "--ofp-listen-host 2001:db8::10 --ofp-tcp-listen-port 6653" in dropin(m)


def test_a_unit_that_does_not_come_back_is_a_failed_outcome_naming_the_bound(tmp_path):
    m, _, _ = ready(tmp_path, comes_up=False)
    out = run(m)
    assert out["ok"] is False and out["step"] == "wait"
    assert "2.5 times the 30 s within which Ryu answered" in out["error"]
    assert "monotonic clock" in out["error"] and "ActiveState failed" in out["error"]
    assert out["main_pid_after"] == "101", "it reads the unit's identity, not the exit code"


def test_a_unit_whose_user_is_not_ryu_after_the_restart_is_not_success(tmp_path):
    """Another drop-in setting User= after Mercury's would leave Ryu as root: success is the
    unit active with a new MainPID AND User=ryu."""
    m, _, _ = ready(tmp_path)
    real = m.systemctl

    def overridden(*args):
        got = real(*args)
        if args[0] == "restart":
            real.props["User"] = "root"
        return got
    m.systemctl = overridden
    out = run(m)
    assert out["ok"] is False and "User 'root'" in out["error"]


# ── change C's refusals, each planted; the drop-in unchanged after each ───────────────────────

def refused(m, argv=()) -> str:
    out = run(m, argv)
    assert out["ok"] is False and out.get("refused"), out
    assert dropin(m) == BEFORE, "a refusal changes nothing"
    assert not [c for c in m.systemctl.calls if c[0] in ("daemon-reload", "restart")]
    return out["refused"]


def test_any_argument_is_refused(tmp_path):
    m, _, _ = ready(tmp_path)
    assert "takes no arguments, and was given 1" in refused(m, ["--anything"])


def test_no_request_is_refused_by_name(tmp_path):
    m = load(tmp_path)
    put_dropin(m)
    assert refused(m).startswith("no request: ")


def test_a_symlinked_request_is_refused(tmp_path):
    m = load(tmp_path)
    put_dropin(m)
    sha = stage_app(m)
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text(json.dumps({"apps": [{"name": "of_versions", "version": "1.0.0",
                                               "sha256": sha}],
                                     "listen": {"host": "192.0.2.10", "port": 6653}}))
    os.symlink(elsewhere, os.path.join(m.APPS_ROOT, ".apply", "request.json"))
    assert "is a symbolic link, not a regular file" in refused(m)


def test_a_request_not_owned_by_the_deploy_account_is_refused(tmp_path, monkeypatch):
    m, _, _ = ready(tmp_path)
    real = os.fstat

    def other_owner(fd):
        st = real(fd)
        if stat.S_ISREG(st.st_mode):
            return os.stat_result((st.st_mode, st.st_ino, st.st_dev, st.st_nlink, 0, st.st_gid,
                                   st.st_size, st.st_atime, st.st_mtime, st.st_ctime))
        return st
    monkeypatch.setattr(os, "fstat", other_owner)
    why = refused(m)
    assert "request.json is owned by " in why and why.endswith(f", not {ME}")


def test_a_staging_folder_another_account_owns_is_refused(tmp_path):
    m, _, _ = ready(tmp_path, account="nobody")
    why = refused(m)
    assert ".apply is owned by " in why and why.endswith(", not nobody")


@pytest.mark.parametrize("name", ["../x", "a/b", "Of_versions", "x" * 42])
def test_a_name_holding_a_slash_or_dots_or_out_of_shape_is_refused(tmp_path, name):
    m = load(tmp_path)
    put_dropin(m)
    put_request(m, [{"name": name, "version": "1.0.0", "sha256": "0" * 64}])
    assert "apps[0].name does not match ^[a-z][a-z0-9_]{0,40}$" in refused(m)


@pytest.mark.parametrize("version", ["1.0", "1.0.0-rc1", "../1.0.0"])
def test_a_version_out_of_shape_is_refused(tmp_path, version):
    m = load(tmp_path)
    put_dropin(m)
    put_request(m, [{"name": "of_versions", "version": version, "sha256": "0" * 64}])
    assert "apps[0].version does not match" in refused(m)


def test_a_folder_outside_the_apps_folder_is_refused(tmp_path):
    m = load(tmp_path)
    put_dropin(m)
    outside = tmp_path / "outside" / "of_versions"
    outside.mkdir(parents=True)
    (outside / "of_versions.py").write_text("x = 1\n")
    os.makedirs(os.path.join(m.APPS_ROOT, "of_versions"))
    os.symlink(outside, os.path.join(m.APPS_ROOT, "of_versions", "1.0.0"))
    put_request(m, [{"name": "of_versions", "version": "1.0.0", "sha256": "0" * 64}])
    assert "is not a real directory under" in refused(m)


@pytest.mark.parametrize("host", ["not-an-address", "192.0.2.300", "", "[2001:db8::1]"])
def test_an_unparsable_host_is_refused(tmp_path, host):
    m, sha, _ = ready(tmp_path)
    put_request(m, [{"name": "of_versions", "version": "1.0.0", "sha256": sha}], host=host)
    assert refused(m) == "listen.host does not parse as an IPv4 or IPv6 address"


@pytest.mark.parametrize("port", [80, 65536, True, "6653"])
def test_a_port_out_of_range_is_refused(tmp_path, port):
    m, sha, _ = ready(tmp_path)
    put_request(m, [{"name": "of_versions", "version": "1.0.0", "sha256": sha}], port=port)
    assert refused(m) == "listen.port is not a whole number from 1024 to 65535"


PLANT = "plantedvalue"


@pytest.mark.parametrize("raw, words", [
    (b"not json " + PLANT.encode(), "is not JSON"),
    (b'{"apps": [], "listen": {"host": "192.0.2.1", "port": 6653}, "cmd": "plantedvalue"}',
     "exactly the keys apps and listen"),
    (b'{"apps": [], "apps": ["plantedvalue"], "listen": {}}', "names the key \"apps\" twice"),
    (b'{"apps": [{"name": "a", "version": "1.0.0", "sha256": "' + b"0" * 64
     + b'", "path": "plantedvalue"}], "listen": {"host": "192.0.2.1", "port": 6653}}',
     "exactly name, version and sha256"),
    (PLANT.encode() * 6554, "more than 65536"),
], ids=["not-json", "another-key", "a-key-twice", "another-field", "too-large"])
def test_a_request_of_any_other_shape_is_refused_without_quoting_it(tmp_path, raw, words):
    m = load(tmp_path)
    put_dropin(m)
    put_request(m, [], raw=raw)
    why = refused(m)
    assert words in why and PLANT not in why


def test_a_folder_edited_after_staging_is_refused_by_its_recomputed_hash(tmp_path):
    m, sha, _ = ready(tmp_path)
    with open(os.path.join(m.APPS_ROOT, "of_versions", "1.0.0", "of_versions.py"), "ab") as fh:
        fh.write(b"import os\n")
    why = refused(m)
    assert f"is not the request's {sha}" in why and "changed after it was staged" in why


@pytest.mark.parametrize("plant", ["link", "group-writable", "no entry file"])
def test_a_staged_folder_holding_a_link_a_writable_file_or_no_entry_is_refused(tmp_path, plant):
    m = load(tmp_path)
    put_dropin(m)
    sha = stage_app(m)
    folder = os.path.join(m.APPS_ROOT, "of_versions", "1.0.0")
    if plant == "link":
        os.symlink("/etc/passwd", os.path.join(folder, "extra.py"))
        words = "is a symbolic link"
    elif plant == "group-writable":
        os.chmod(os.path.join(folder, "manifest.yml"), 0o664)
        words = "writable by group or others"
    else:
        os.remove(os.path.join(folder, "of_versions.py"))
        words = "holds no file of_versions.py"
    put_request(m, [{"name": "of_versions", "version": "1.0.0", "sha256": sha}])
    assert words in refused(m)


def test_an_unrendered_copy_refuses_to_run(tmp_path):
    m = load(tmp_path, render=False)
    put_dropin(m)
    assert "RYU_UNIT, RYU_MANAGER still a placeholder" in refused(m)


# ── change C2: the unsafe state, refused before the request is read ──────────────────────────

@pytest.mark.parametrize("user", ["", "root"])
def test_root_over_a_folder_the_deploy_account_writes_is_refused_before_the_request(tmp_path,
                                                                                    user):
    m, _, req = ready(tmp_path, user=user)
    why = refused(m)
    assert why.startswith("refused before the request was read: ")
    assert f"User is {user!r} (root)" in why
    assert f"{m.APPS_ROOT} is {ME}:" in why and "drwxr-xr-x" in why
    assert os.path.exists(req), "the request was never read"


def test_root_over_a_folder_the_deploy_account_cannot_write_is_not_the_unsafe_state(tmp_path):
    """The account is another, and the folder is not writable to it: C2 does not fire (the
    folders' own checks still refuse)."""
    m, _, _ = ready(tmp_path, user="", account="nobody")
    why = refused(m)
    assert not why.startswith("refused before the request was read")


# ── one hash, two computations ───────────────────────────────────────────────────────────────

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def test_the_on_disk_hash_is_mercury_s_content_hash_of_the_same_files(tmp_path):
    """The script's recomputation and `lifecycle.content_hash` (git's ls-tree) agree on a folder
    with a nested file and an executable one: a staged folder can be checked against its pin."""
    from modules.jobs.lifecycle import content_hash

    repo = tmp_path / "code"
    folder = repo / "apps" / "of_versions"
    files = {"of_versions.py": (b"x = 1\n", 0o644), "lib/helper.py": (b"y = 2\n", 0o644),
             "tool.sh": (b"#!/bin/sh\n", 0o755)}
    for rel, (data, mode) in files.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(mode)
    env = dict(os.environ, **GIT_ENV)
    for args in (("init", "-q", "-b", "main"), ("add", "-A"), ("commit", "-q", "-m", "x")):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, env=env)
    m = load(tmp_path / "root")
    assert m.folder_hash(str(folder)) == content_hash(repo, "apps/of_versions")
    (folder / "tool.sh").chmod(0o644)
    assert m.folder_hash(str(folder)) != content_hash(repo, "apps/of_versions"), \
        "the executable bit is part of the hash on both sides"


# ── the controller's Python 3.5, and the host step ───────────────────────────────────────────

def test_the_script_is_written_for_the_controller_s_python_3_5():
    from modules.apps.python_versions import Target, grammar_problems, name_problem

    text = open(SCRIPT).read()
    tree = ast.parse(text, feature_version=(3, 5))
    target = Target((3, 5), "the controller's Python (Ubuntu 16.04.5)")
    assert grammar_problems(tree, text, "mercury-ryu-apply", target) == []
    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert imported and all(not name_problem(i, target) for i in imported)
    assert not [n for n in ast.walk(tree) if isinstance(n, ast.JoinedStr)], "no f-strings"


def test_the_python_3_5_check_finds_an_f_string_planted_in_the_script():
    from modules.apps.python_versions import Target, grammar_problems

    text = open(SCRIPT).read() + '\nx = f"{1}"\n'
    tree = ast.parse(text)
    assert grammar_problems(tree, text, "mercury-ryu-apply", Target((3, 5), "3.5"))


def test_the_script_runs_nothing_from_a_path_it_was_given():
    """Every program it runs is SYSTEMCTL, a constant: one `subprocess.run`, its argv built from
    `(SYSTEMCTL,)`, and no os.system, exec or shell."""
    tree = ast.parse(open(SCRIPT).read())
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)]
    runs = [c for c in calls if (c.func.value.id, c.func.attr) == ("subprocess", "run")]
    assert len(runs) == 1 and ast.unparse(runs[0].args[0]).startswith("(SYSTEMCTL,)")
    assert not [c for c in calls if c.func.attr in ("system", "popen", "execv", "execve",
                                                    "Popen", "call", "check_output")]
    assert "shell=True" not in open(SCRIPT).read()


def test_the_host_step_renders_exactly_the_script_s_placeholder_lines():
    text = open(SCRIPT).read().splitlines()
    assert 'RYU_UNIT = "@RYU_UNIT@"' in text and 'RYU_MANAGER = "@RYU_MANAGER@"' in text
    step = open(HOST_STEP).read()
    assert 's|^RYU_UNIT = \\"@RYU_UNIT@\\"$|' in step
    assert 's|^RYU_MANAGER = \\"@RYU_MANAGER@\\"$|' in step
    assert 'mercury ALL=(root) NOPASSWD: /usr/local/sbin/mercury-ryu-apply ""' in step
    installs = [line for line in step.splitlines() if "sudo install " in line]
    # Four since 2026-11-11: the script, the sudoers line when its file is absent (so the
    # operator edits no file by hand), the first drop-in, and the folder's hand-over.
    assert "WORK=$(mktemp -d)" in step and len(installs) == 4
    assert 'sudo install -o root -g root -m 0440 "$WORK/mercury-ryu-apply.sudoers" ' \
           '"$SUDOERS_FILE"' in step
    assert not [line for line in installs if "*" in line or "?" in line], \
        "files are installed by name, never a glob"


def test_the_host_step_hands_the_folder_over_only_after_user_ryu_is_read_back():
    step = open(HOST_STEP).read()
    assert step.index('check "the unit runs as User=ryu and is active"') \
        < step.index("sudo install -d -o mercury -g mercury -m 0755 /opt/ryu-apps")
    assert step.index('check "with no request, the script refuses by name (no request)"') \
        < step.index("sudo install -d -o mercury -g mercury -m 0755 /opt/ryu-apps")


def test_the_host_step_parses():
    assert subprocess.run(["bash", "-n", HOST_STEP], capture_output=True).returncode == 0


def test_the_request_hash_is_over_the_normalised_request(tmp_path):
    m = load(tmp_path)
    one = m.parse_request(b'{"apps": [], "listen": {"host": "2001:db8:0::1", "port": 6653}}')
    two = m.parse_request(b'{"listen": {"port": 6653, "host": "2001:db8::1"}, "apps": []}')
    assert m.request_sha256(one) == m.request_sha256(two) == hashlib.sha256(
        b'{"apps":[],"listen":{"host":"2001:db8::1","port":6653}}').hexdigest()


# ── what landed, in a failed apply's outcome (C2705) ─────────────────────────────────────────

def test_a_failure_after_the_drop_in_is_written_says_its_step(tmp_path):
    """An exception past the write is an outcome with a step (after-write), never one that
    reads as nothing having changed: Mercury rolls back what landed."""
    m, _, _ = ready(tmp_path)

    def broken(before):
        raise OSError(5, "planted")
    m.restart = broken
    out = run(m)
    assert out["ok"] is False and out.get("step") == "after-write", out
    assert "the drop-in was written, then OSError" in out["error"]
    assert dropin(m) != BEFORE and out["dropin_sha256"] == hashlib.sha256(
        dropin(m).encode()).hexdigest()


def test_a_failure_before_the_drop_in_is_replaced_has_no_step_and_changes_no_drop_in(tmp_path):
    m, _, _ = ready(tmp_path)

    def broken(text):
        raise OSError(28, "planted: no space")
    m.write_dropin = broken
    out = run(m)
    assert out["ok"] is False and "step" not in out and "refused" not in out, out
    assert dropin(m) == BEFORE
    assert not [c for c in m.systemctl.calls if c[0] in ("daemon-reload", "restart")]


def test_an_unanswered_read_of_the_unit_during_the_wait_is_a_poll_not_a_refusal(tmp_path):
    m, _, _ = ready(tmp_path)
    real = m.systemctl
    restarted = []

    def silent_after_restart(*args):
        if args[0] == "restart":
            restarted.append(1)
        if args[0] == "show" and restarted:
            return 1, "", "Failed to connect to bus"
        return real(*args)
    m.systemctl = silent_after_restart
    out = run(m)
    assert out["ok"] is False and out.get("step") == "wait" and "refused" not in out, out


# ── the second request kind: put the drop-in before back (decision K3) ───────────────────────

def put_back_request(m, before_sha256=None, raw=None):
    body = raw if raw is not None else json.dumps(
        {"kind": "put-before-back",
         "before_sha256": before_sha256 or m.before_sha256(BEFORE)}).encode()
    return put_request(m, [], raw=body)


def prev(m) -> str:
    return os.path.join(m.DROPIN_ROOT, UNIT + ".d", "mercury.conf.prev")


def applied(tmp_path, **kw):
    """The script after one apply: mercury.conf is the render, mercury.conf.prev is BEFORE."""
    m, _, _ = ready(tmp_path, **kw)
    assert run(m)["ok"] is True
    m.systemctl.calls.clear()
    return m


def test_the_put_back_puts_the_drop_in_before_back_and_restarts_by_identity(tmp_path):
    m = applied(tmp_path)
    rendered = dropin(m)
    req = put_back_request(m)
    out = run(m)
    assert out["ok"] is True, out
    assert out.get("kind") == "put-before-back" and out.get("step") == "running"
    assert dropin(m) == BEFORE, "the drop-in before is back"
    assert open(prev(m)).read() == BEFORE, "kept as it is, so a second put-back is the same"
    assert out["replaced_sha256"] == hashlib.sha256(rendered.encode()).hexdigest()
    assert out["main_pid_before"] == "101" and out["main_pid_after"] == "102"
    assert out["user"] == "ryu" and out["active_state"] == "active"
    assert [c[0] for c in m.systemctl.calls if c[0] != "show"] == ["daemon-reload", "restart"]
    assert not os.path.exists(req), "a request is applied once"


def test_the_put_back_is_judged_by_identity_as_an_apply_is(tmp_path):
    m = applied(tmp_path)
    m.systemctl.comes_up = False
    put_back_request(m)
    out = run(m)
    assert out["ok"] is False and out.get("step") == "wait", out
    assert "ActiveState failed" in out["error"]


def put_back_refused(m) -> str:
    """A refused put-back changed nothing: the drop-in is still the render, nothing restarted."""
    before = dropin(m)
    out = run(m)
    assert out["ok"] is False and out.get("refused"), out
    assert dropin(m) == before
    assert not [c for c in m.systemctl.calls if c[0] in ("daemon-reload", "restart")]
    return out["refused"]


def test_a_put_back_bound_to_another_drop_in_is_refused_naming_both(tmp_path):
    m = applied(tmp_path)
    other = "0" * 64
    put_back_request(m, before_sha256=other)
    why = put_back_refused(m)
    assert f"hashes {m.before_sha256(BEFORE)}, not the request's before_sha256 {other}" in why


def test_a_put_back_with_no_drop_in_kept_is_refused_by_name(tmp_path):
    m = applied(tmp_path)
    os.remove(prev(m))
    put_back_request(m)
    assert "there is no drop-in before to put back" in put_back_refused(m)


@pytest.mark.parametrize("text, words", [
    ("[Service]\nUser=root\n", "last User= line is 'root', not User=ryu"),
    ("[Service]\nExecStart=\n", "last User= line is absent, not User=ryu"),
    ("[Service]\nUser=ryu\nUser=root\n", "last User= line is 'root'")],
    ids=["root", "none", "root-after-ryu"])
def test_a_put_back_that_would_not_run_ryu_as_its_user_is_refused(tmp_path, text, words):
    """Removing mercury.conf, or putting back a drop-in with no User=ryu, would leave the unit
    on its own User, root on S3's layout (C2's unsafe state)."""
    m = applied(tmp_path)
    with open(prev(m), "w") as fh:
        fh.write(text)
    put_back_request(m, before_sha256=m.before_sha256(text))
    assert words in put_back_refused(m)


def test_a_put_back_through_a_link_is_refused(tmp_path):
    m = applied(tmp_path)
    target = tmp_path / "planted.conf"
    target.write_text(BEFORE)
    os.remove(prev(m))
    os.symlink(target, prev(m))
    put_back_request(m)
    assert "mercury.conf.prev is a symbolic link" in put_back_refused(m)


def test_a_put_back_kept_writable_by_others_is_refused(tmp_path):
    m = applied(tmp_path)
    os.chmod(prev(m), 0o666)
    put_back_request(m)
    assert "writable by group or others" in put_back_refused(m)


@pytest.mark.parametrize("raw, words", [
    (b'{"kind": "plantedvalue"}', "the request's kind is not put-before-back"),
    (b'{"kind": "apply", "apps": [], "listen": {"host": "192.0.2.1", "port": 6653}}',
     "the request's kind is not put-before-back"),
    (b'{"kind": "put-before-back", "before_sha256": "' + b"0" * 64 + b'", "path": "x"}',
     "exactly the keys kind and before_sha256"),
    (b'{"kind": "put-before-back"}', "exactly the keys kind and before_sha256"),
    (b'{"kind": "put-before-back", "before_sha256": "plantedvalue"}',
     "before_sha256 does not match")],
    ids=["another-kind", "apply-named", "another-key", "no-hash", "hash-out-of-shape"])
def test_a_request_naming_any_other_kind_or_shape_is_refused_by_name(tmp_path, raw, words):
    m = applied(tmp_path)
    put_back_request(m, raw=raw)
    why = put_back_refused(m)
    assert words in why and "plantedvalue" not in why


def test_the_put_back_hash_is_the_one_systemctl_cat_shows_and_mercury_reads():
    """Mercury binds the put-back to the plan's `dropin_before` (systemctl cat's text, blank
    lines at either end dropped); the script hashes its kept file the same way."""
    from modules.apps import channel

    s = channel.script()
    cat = f"# /lib/systemd/system/{UNIT}\n[Service]\n\n# /etc/systemd/system/{UNIT}.d/" \
          f"mercury.conf\n{BEFORE}\n"
    assert s.before_sha256(BEFORE + "\n\n") == s.before_sha256(
        channel.dropin_before(cat, UNIT)) == hashlib.sha256(BEFORE.encode()).hexdigest()


# ── an app's start-time config, beside its version (decision K9; C2707) ──────────────────────

CONFIG = b'{"punt_table":100}\n'


def configured(tmp_path, data=CONFIG, mode=0o644, sha=None):
    m = load(tmp_path)
    put_dropin(m)
    folder_sha = stage_app(m)
    path = m.config_path(m.APPS_ROOT, "of_versions", "1.0.0")
    with open(path, "wb") as fh:
        fh.write(data)
    os.chmod(path, mode)
    put_request(m, [{"name": "of_versions", "version": "1.0.0", "sha256": folder_sha,
                     "config_sha256": sha or hashlib.sha256(data).hexdigest()}])
    return m, folder_sha, path


def test_a_config_beside_the_version_is_checked_by_its_hash_and_leaves_the_folder_s_alone(
        tmp_path):
    m, folder_sha, path = configured(tmp_path)
    assert path == os.path.join(m.APPS_ROOT, "of_versions", "1.0.0.config.json")
    assert m.folder_hash(os.path.join(m.APPS_ROOT, "of_versions", "1.0.0")) == folder_sha
    out = run(m)
    assert out["ok"] is True, out
    assert out["apps"][0]["config_sha256"] == hashlib.sha256(CONFIG).hexdigest()


def test_a_request_with_no_config_is_the_shape_and_hash_it_always_was(tmp_path):
    m = load(tmp_path)
    raw = b'{"apps": [{"name": "a", "version": "1.0.0", "sha256": "' + b"1" * 64 + \
        b'"}], "listen": {"host": "192.0.2.1", "port": 6653}}'
    got = m.parse_request(raw)
    assert got["apps"] == [{"name": "a", "version": "1.0.0", "sha256": "1" * 64}]
    assert m.request_sha256(got) == hashlib.sha256(
        b'{"apps":[{"name":"a","sha256":"' + b"1" * 64 + b'","version":"1.0.0"}],'
        b'"listen":{"host":"192.0.2.1","port":6653}}').hexdigest()


@pytest.mark.parametrize("plant, words", [
    ("edited", "changed after it was staged"),
    ("absent", "cannot be read"),
    ("link", "is a symbolic link, not a regular file"),
    ("group-writable", "writable by group or others"),
    ("not-an-object", "is not a JSON object"),
    ("not-json", "is not JSON in UTF-8"),
    ("unnamed", "the request names no config for it")])
def test_a_config_other_than_the_request_names_is_refused(tmp_path, plant, words):
    data = {"not-an-object": b"[1]\n", "not-json": b"plantedvalue\n"}.get(plant, CONFIG)
    m, folder_sha, path = configured(tmp_path, data=data,
                                     mode=0o664 if plant == "group-writable" else 0o644)
    if plant == "edited":
        with open(path, "ab") as fh:
            fh.write(b" ")
    elif plant == "absent":
        os.remove(path)
    elif plant == "link":
        os.remove(path)
        target = tmp_path / "planted.json"
        target.write_bytes(CONFIG)
        os.symlink(target, path)
    elif plant == "unnamed":
        put_request(m, [{"name": "of_versions", "version": "1.0.0", "sha256": folder_sha}])
    why = refused(m)
    assert words in why and "1.0.0.config.json" in why and "plantedvalue" not in why


def test_a_config_hash_out_of_shape_is_refused(tmp_path):
    m, _, _ = configured(tmp_path, sha="plantedvalue")
    why = refused(m)
    assert "apps[0].config_sha256 does not match" in why and "plantedvalue" not in why


# ── the app SDK, on the apps' import path (C2852, option A) ──────────────────────────────────

SDK_INIT = b'"""the SDK, as staged"""\n'


def stage_sdk(m, data=SDK_INIT, extra=None) -> str:
    """The SDK staged as Mercury stages it, under a folder named by its content hash."""
    tmp = os.path.join(m.APPS_ROOT, ".sdk", "staging")
    os.makedirs(os.path.join(tmp, "mercury_app"))
    files = {"mercury_app/__init__.py": data, **(extra or {})}
    for rel, body in files.items():
        path = os.path.join(tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(body)
        os.chmod(path, 0o644)
    for root, dirs, _ in os.walk(tmp):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o755)
    os.chmod(tmp, 0o755)
    sha = m.folder_hash(tmp)
    os.rename(tmp, m.sdk_folder(m.APPS_ROOT, sha))
    return sha


def sdk_ready(tmp_path, **kw):
    m = load(tmp_path)
    put_dropin(m)
    app_sha = stage_app(m)
    sdk_sha = stage_sdk(m, **kw)
    put_sdk_request(m, app_sha, sdk_sha)
    return m, app_sha, sdk_sha


def put_sdk_request(m, app_sha, sdk_sha):
    body = json.dumps({"apps": [{"name": "of_versions", "version": "1.0.0", "sha256": app_sha}],
                       "listen": {"host": "192.0.2.10", "port": 6653},
                       "sdk": {"sha256": sdk_sha}}).encode()
    put_request(m, [], raw=body)


def test_a_request_naming_the_sdk_puts_its_folder_on_the_apps_import_path(tmp_path):
    m, _, sdk_sha = sdk_ready(tmp_path)
    out = run(m)
    assert out["ok"] is True, out
    folder = os.path.join(m.APPS_ROOT, ".sdk", sdk_sha)
    assert out["sdk"] == folder
    lines = dropin(m).splitlines()
    assert lines[1:4] == ["[Service]", "User=ryu", f"Environment=PYTHONPATH={folder}"]
    assert lines[4] == "ExecStart="


def test_a_request_naming_no_sdk_renders_the_drop_in_it_always_did(tmp_path):
    m = load(tmp_path)
    req = {"apps": [{"name": "a", "version": "1.0.0", "sha256": "1" * 64}],
           "listen": {"host": "192.0.2.1", "port": 6653}}
    text = m.render_dropin(req, MANAGER, "ryu", "/opt/ryu-apps")
    assert "Environment=" not in text and "\nUser=ryu\nExecStart=\n" in text
    with_sdk = m.parse_request(json.dumps(dict(req, sdk={"sha256": "2" * 64})).encode())
    assert with_sdk["sdk"] == {"sha256": "2" * 64}
    assert m.request_sha256(with_sdk) != m.request_sha256(m.parse_request(
        json.dumps(req).encode())), "the SDK's hash is in the request's"


@pytest.mark.parametrize("plant, words", [
    ("edited", "changed after it was staged"),
    ("absent", "cannot be read"),
    ("no package", "holds no file mercury_app/__init__.py"),
    ("link", "is a symbolic link"),
    ("group-writable", "writable by group or others")])
def test_an_sdk_folder_other_than_the_request_names_is_refused(tmp_path, plant, words):
    m, app_sha, sdk_sha = sdk_ready(tmp_path)
    folder = m.sdk_folder(m.APPS_ROOT, sdk_sha)
    init = os.path.join(folder, "mercury_app", "__init__.py")
    if plant == "edited":
        with open(init, "ab") as fh:
            fh.write(b"import os\n")
    elif plant == "absent":
        put_sdk_request(m, app_sha, "3" * 64)
    elif plant == "no package":
        os.rename(init, os.path.join(folder, "mercury_app", "other.py"))
    elif plant == "link":
        os.symlink("/etc/passwd", os.path.join(folder, "mercury_app", "extra.py"))
    else:
        os.chmod(init, 0o664)
    before = dropin(m)
    why = refused(m)
    assert words in why and "/.sdk/" in why
    assert dropin(m) == before


@pytest.mark.parametrize("raw, words", [
    (b'{"sha256": "plantedvalue"}', "sdk.sha256 does not match"),
    (b'{"sha256": "' + b"4" * 64 + b'", "path": "plantedvalue"}', "sdk is not an object of "
                                                                  "exactly sha256"),
    (b'"plantedvalue"', "sdk is not an object of exactly sha256")],
    ids=["hash-shape", "another-field", "not-an-object"])
def test_an_sdk_entry_of_any_other_shape_is_refused_without_quoting_it(tmp_path, raw, words):
    m = load(tmp_path)
    put_dropin(m)
    put_request(m, [], raw=b'{"apps": [], "listen": {"host": "192.0.2.1", "port": 6653}, '
                       b'"sdk": ' + raw + b"}")
    why = refused(m)
    assert words in why and "plantedvalue" not in why


def test_an_app_named_as_the_sdk_s_package_is_refused(tmp_path):
    m = load(tmp_path)
    put_dropin(m)
    put_request(m, [{"name": "mercury_app", "version": "1.0.0", "sha256": "5" * 64}])
    assert "the app SDK's package" in refused(m)
