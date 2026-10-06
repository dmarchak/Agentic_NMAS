"""A test run leaves the person's home untouched (C391, C392).

The operator, 2026-10-03: 45 test records `nmas-breakglass-Lab-*.bg` in the laptop's Downloads
(the export tests' downloads; 18 of them the copy one test corrupts on purpose, so the drill
could not parse them), and, found surveying the home for it, 442 empty `nmas-browser-*` folders
with a geckodriver still running for each (2.9 GB): every confined test process probed for a
browser, the probe could not start, and a session that cannot start never reached its clean-up.
"""
import os
import re
import subprocess
import sys

import pytest

from tests import browser, home_guard

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestTheDownloadFolder:
    def test_the_desktops_name_for_it(self, tmp_path):
        (tmp_path / ".config").mkdir()
        (tmp_path / ".config" / "user-dirs.dirs").write_text(
            '# a comment\nXDG_DOWNLOAD_DIR="$HOME/Téléchargements"\n')
        assert home_guard.downloads_dir(env={}, home=str(tmp_path)) == \
            str(tmp_path / "Téléchargements")

    def test_the_environment_first_and_a_default_last(self, tmp_path):
        assert home_guard.downloads_dir(env={"XDG_DOWNLOAD_DIR": "/x/dl"}, home=str(tmp_path)) \
            == "/x/dl"
        assert home_guard.downloads_dir(env={}, home=str(tmp_path)) == str(tmp_path / "Downloads")


class TestTheJudgement:
    def _dirs(self, tmp_path):
        dl, parent = tmp_path / "Downloads", tmp_path / "common"
        dl.mkdir()
        parent.mkdir()
        (dl / "the-persons-own.pdf").write_text("x")
        (parent / ".mozilla").mkdir()
        return dl, parent

    def test_untouched_is_silent(self, tmp_path):
        dl, parent = self._dirs(tmp_path)
        before = home_guard.snapshot(str(dl), [str(parent)])
        assert home_guard.judge(before, home_guard.snapshot(str(dl), [str(parent)])) == ""

    def test_a_session_folder_fails_and_a_download_is_only_named(self, tmp_path):
        """C519: this run's session folder is the run's by its name, and fails it; a new file
        in the download folder is named, and does not (no route of the suite's reaches it)."""
        dl, parent = self._dirs(tmp_path)
        before = home_guard.snapshot(str(dl), [str(parent)])
        (dl / "winboat-0.8.7-amd64.deb").write_text("x")
        (parent / (home_guard.session_prefix("browser") + "abc")).mkdir()
        after = home_guard.snapshot(str(dl), [str(parent)])
        got = home_guard.judge(before, after)
        assert home_guard.session_prefix("browser") + "abc" in got
        assert "winboat" not in got and "the-persons-own.pdf" not in got
        note = home_guard.noted(before, after)
        assert note.startswith("NOTE:") and "winboat-0.8.7-amd64.deb" in note
        assert "the-persons-own.pdf" not in note, "a file there before the run is not new"

    @pytest.mark.parametrize("name", [".~lock.report.odt#", "winboat.deb.part",
                                      "setup.exe.crdownload", ".notes.txt.swp", ".#notes.txt",
                                      "#notes.txt#", "notes.txt~", ".goutputstream-AB12C3"])
    def test_a_desktop_programs_transient_file_is_not_even_named(self, tmp_path, name):
        dl, parent = self._dirs(tmp_path)
        before = home_guard.snapshot(str(dl), [str(parent)])
        (dl / name).write_text("x")
        after = home_guard.snapshot(str(dl), [str(parent)])
        assert home_guard.judge(before, after) == "" and home_guard.noted(before, after) == ""

    @pytest.mark.parametrize("name", ["report.odt", "lock.txt", "partial.bg", "notes.swp.bg"])
    def test_a_finished_file_is_never_transient(self, name):
        assert not home_guard.is_transient(name)

    def test_another_runs_sessions_and_the_snaps_own_files_are_not_this_runs(self, tmp_path):
        """The gate runs three shards at once: a shard judges only its own run's folders."""
        dl, parent = self._dirs(tmp_path)
        before = home_guard.snapshot(str(dl), [str(parent)])
        (parent / "nmas-browser-999999999-xyz").mkdir()
        (parent / ".cache").mkdir()
        assert home_guard.judge(before, home_guard.snapshot(str(dl), [str(parent)])) == ""

    def test_a_download_folder_that_appears_is_named(self, tmp_path):
        dl = tmp_path / "Downloads"
        before = home_guard.snapshot(str(dl), [])
        dl.mkdir()
        (dl / "x.bg").write_text("{}")
        assert str(dl) in home_guard.noted(before, home_guard.snapshot(str(dl), []))

    def test_a_folder_a_session_could_not_remove_is_named(self):
        assert "/tmp/nmas-browser-1-x" in home_guard.judge({}, {}, ["/tmp/nmas-browser-1-x"])


def test_every_session_has_its_own_id_and_its_workers_share_it(monkeypatch):
    """A child pytest a test starts is its own session: with its parent's id it judged the
    folders the parent's other workers were using as left behind (the gate, 2026-10-03)."""
    monkeypatch.setenv(home_guard.RUN_ENV, "111")
    # A child started from inside a worker inherits PYTEST_XDIST_WORKER: still a session.
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw1")
    assert home_guard.start_run(is_worker=False) == str(os.getpid()), "a session: its own id"
    monkeypatch.setenv(home_guard.RUN_ENV, "111")
    assert home_guard.start_run(is_worker=True) == "111", "a worker: its session's id"


def test_a_child_started_from_a_worker_is_a_session_of_its_own(tmp_path):
    """The wiring, end to end, the shape that failed the gate twice: a child pytest run with
    a worker's environment (PYTEST_XDIST_WORKER and the parent's run id) takes a NEW id."""
    planted = tmp_path / "test_planted.py"
    planted.write_text("import os\n\ndef test_id():\n"
                       f"    print('RUN=' + os.environ[{home_guard.RUN_ENV!r}])\n")
    env = dict(os.environ, PYTHONPATH=ROOT, PYTEST_XDIST_WORKER="gw0")
    env[home_guard.RUN_ENV] = "424242"
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-s", "-p", "no:cacheprovider",
                          "-p", "tests.conftest", "--rootdir", str(tmp_path), str(planted)],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert "1 passed" in out.stdout, out.stdout[-800:] + out.stderr[-800:]
    got = [l for l in out.stdout.splitlines() if l.strip().startswith("RUN=")]
    assert got and got[0].strip() != "RUN=424242", got


def _child_run(tmp_path, body):
    """A child pytest of one planted test (*body*, its lines), its download folder a temporary
    one: ``(the completed process, the download folder)``."""
    dl = tmp_path / "dl"
    dl.mkdir()
    planted = tmp_path / "test_planted.py"
    planted.write_text("import os\nimport tempfile\n\nfrom tests import home_guard\n\n"
                       "def test_writes():\n" + "".join(f"    {l}\n" for l in body(dl)))
    env = dict(os.environ, XDG_DOWNLOAD_DIR=str(dl), PYTHONPATH=ROOT)
    env.pop(home_guard.RUN_ENV, None)
    for key in [k for k in env if k.startswith(("PYTEST_XDIST", "PYTEST_CURRENT"))]:
        env.pop(key)
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                          "-p", "tests.conftest", "--rootdir", str(tmp_path), str(planted)],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert "1 passed" in out.stdout, out.stdout[-800:] + out.stderr[-800:]
    return out, dl


def test_the_run_fails_when_it_leaves_a_session_folder_of_its_own(tmp_path):
    """The wiring, end to end: a child pytest whose one test leaves a folder named as the run's
    browser sessions are fails, naming it, though the test itself passed."""
    made = tmp_path / "made"
    out, _dl = _child_run(tmp_path, lambda dl: [
        "p = os.path.join(tempfile.gettempdir(), home_guard.session_prefix('browser') + 'x')",
        f"open({str(made)!r}, 'w').write(p)", "os.mkdir(p)"])
    left = made.read_text() if made.exists() else ""
    try:
        assert left and out.returncode != 0, out.stdout[-800:]
        assert "C391" in out.stderr and left in out.stderr, out.stderr[-800:]
    finally:
        if left and os.path.isdir(left):
            os.rmdir(left)          # recorded by the planted test, so removed whatever the guard said


def test_a_file_new_in_the_download_folder_is_named_and_the_run_passes(tmp_path):
    """C519, end to end: a file in the download folder that no route of the suite's made (the
    person's `.deb`) is named in the run's summary, and the run passes; a desktop program's
    lock file beside it is not even named."""
    out, _dl = _child_run(tmp_path, lambda dl: [
        f"open(os.path.join({str(dl)!r}, 'winboat-0.8.7-amd64.deb'), 'w').write('x')",
        f"open(os.path.join({str(dl)!r}, '.~lock.report.odt#'), 'w').write('x')"])
    assert out.returncode == 0, out.stdout[-800:] + out.stderr[-800:]
    assert "NOTE:" in out.stderr and "winboat-0.8.7-amd64.deb" in out.stderr, out.stderr[-800:]
    assert ".~lock" not in out.stderr


#: The two routes by which the suite could reach the person's download folder are closed apart
#: from the watch (home_guard's docstring, C519); this closes the second: no code names it.
DOWNLOAD_FOLDER = re.compile(r"Downloads|XDG_DOWNLOAD_DIR|user-dirs")
#: Where naming it is the point: the guard itself, the browser session pointing its own folder
#: there, and this file's tests of both.
MAY_NAME_IT = {"tests/home_guard.py", "tests/browser.py", "tests/test_home_untouched.py"}


def names_the_download_folder(path: str) -> list:
    """The lines of *path* whose CODE (a name or a string, never a comment) names the person's
    download folder."""
    import io
    import tokenize

    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    hits = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.NAME, tokenize.STRING) and DOWNLOAD_FOLDER.search(tok.string):
                hits.add(tok.start[0])
    except (tokenize.TokenError, SyntaxError):
        return [0]
    return sorted(hits)


def _python_files():
    import glob
    out = [os.path.join(ROOT, "app.py")]
    for folder in ("modules", "routes", "tests", "lab"):
        out += glob.glob(os.path.join(ROOT, folder, "**", "*.py"), recursive=True)
    for path in glob.glob(os.path.join(ROOT, "scripts", "**", "*"), recursive=True):
        if os.path.isfile(path) and not path.endswith(".py"):
            with open(path, "rb") as fh:
                if b"python" in fh.readline():
                    out.append(path)
        elif path.endswith(".py"):
            out.append(path)
    return sorted(set(out))


def test_no_code_names_the_download_folder():
    files = _python_files()
    assert len(files) >= 400, len(files)
    named = {os.path.relpath(p, ROOT): lines for p in files
             for lines in [names_the_download_folder(p)] if lines}
    assert set(named) - MAY_NAME_IT == set(), named
    assert {"tests/home_guard.py", "tests/browser.py"} <= set(named), \
        "the scan finds the two files that do name it"


def test_the_scan_finds_a_planted_one_and_skips_a_comment(tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text("import os\n# saves into ~/Downloads (a comment)\n"
                       "p = os.path.expanduser('~/Downloads/x.bg')\n")
    assert names_the_download_folder(str(planted)) == [3]


def test_a_session_that_cannot_start_leaves_nothing(monkeypatch):
    """C392: the probe's session failed to start, never reached __exit__, and left its
    geckodriver running and its folder behind, once per confined test process."""
    if not browser._geckodriver():
        pytest.skip("no geckodriver here")

    def refuse(self, method, path, body=None, timeout=60):
        raise RuntimeError("this runner cannot start Firefox (planted)")
    monkeypatch.setattr(browser.Browser, "_call", refuse)
    b = browser.Browser()
    with pytest.raises(RuntimeError):
        b.__enter__()
    assert b.proc.poll() is not None, "its geckodriver stopped"
    assert not os.path.exists(b.tmp), "its folder removed"
    assert b.tmp not in browser.LEFT_BEHIND
