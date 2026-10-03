"""A test run leaves the person's home untouched (C391, C392).

The operator, 2026-10-03: 45 test records `nmas-breakglass-Lab-*.bg` in the laptop's Downloads
(the export tests' downloads; 18 of them the copy one test corrupts on purpose, so the drill
could not parse them), and, found surveying the home for it, 442 empty `nmas-browser-*` folders
with a geckodriver still running for each (2.9 GB): every confined test process probed for a
browser, the probe could not start, and a session that cannot start never reached its clean-up.
"""
import os
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

    def test_a_download_and_a_session_folder_left_are_named(self, tmp_path):
        dl, parent = self._dirs(tmp_path)
        before = home_guard.snapshot(str(dl), [str(parent)])
        (dl / "nmas-breakglass-Lab-20261003T181546Z.bg").write_text("{}")
        (parent / (home_guard.session_prefix("browser") + "abc")).mkdir()
        got = home_guard.judge(before, home_guard.snapshot(str(dl), [str(parent)]))
        assert "nmas-breakglass-Lab-20261003T181546Z.bg" in got
        assert home_guard.session_prefix("browser") + "abc" in got
        assert "the-persons-own.pdf" not in got

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
        assert str(dl) in home_guard.judge(before, home_guard.snapshot(str(dl), []))

    def test_a_folder_a_session_could_not_remove_is_named(self):
        assert "/tmp/nmas-browser-1-x" in home_guard.judge({}, {}, ["/tmp/nmas-browser-1-x"])


def test_every_session_has_its_own_id_and_its_workers_share_it(monkeypatch):
    """A child pytest a test starts is its own session: with its parent's id it judged the
    folders the parent's other workers were using as left behind (the gate, 2026-10-03)."""
    monkeypatch.setenv(home_guard.RUN_ENV, "111")
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    assert home_guard.start_run() == str(os.getpid()), "a session: its own id"
    monkeypatch.setenv(home_guard.RUN_ENV, "111")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw1")
    assert home_guard.start_run() == "111", "a worker: its session's id"


def test_the_run_fails_when_a_test_writes_into_the_download_folder(tmp_path):
    """The wiring, end to end: a child pytest whose one test writes into the download folder
    (pointed at a temporary one) fails, naming the file, though the test itself passed."""
    dl = tmp_path / "dl"
    dl.mkdir()
    planted = tmp_path / "test_planted.py"
    planted.write_text("import os\n\ndef test_writes():\n"
                       f"    open(os.path.join({str(dl)!r}, 'stray.bg'), 'w').write('{{}}')\n")
    env = dict(os.environ, XDG_DOWNLOAD_DIR=str(dl), PYTHONPATH=ROOT)
    env.pop(home_guard.RUN_ENV, None)
    for key in [k for k in env if k.startswith(("PYTEST_XDIST", "PYTEST_CURRENT"))]:
        env.pop(key)
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                          "-p", "tests.conftest", "--rootdir", str(tmp_path), str(planted)],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert "1 passed" in out.stdout, out.stdout[-800:] + out.stderr[-800:]
    assert out.returncode != 0, out.stdout[-800:]
    assert "stray.bg" in out.stderr and "C391" in out.stderr, out.stderr[-800:]


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
