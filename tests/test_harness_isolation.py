"""Register C32 and C36: the suite never touches the live store, and importing
the program starts nothing.

Found 2026-09-26 by running the suite from a pristine checkout for the first
time: 5 failed and 19 errored, all passing here, because this checkout's
`data/` residue and settings file were doing work the tests should have done.
"3,950 passed" had been partly a statement about one checkout.
"""

import ast
import os
import subprocess
import stat
import sys
import types

import pytest

from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


#: The filesystems the store guard must hold on: this machine's own, and ext4
#: as the host has it (kernel 6.8: a 1 ms tick, measured 2026-09-26), and ext4
#: on a 1 s tick.
CLOCKS = (None, 1_000_000, 1_000_000_000)
CLOCK_IDS = ("native", "ext4-1ms", "ext4-1s")
#: A moment long before any session: where the store's last change sits.
LONG_AGO_NS = 1_000_000_000 * 1_000_000_000
EXT4_DIR_SIZE = 4096


def _clock(tick):
    """An lstat that answers as ext4 on a *tick* (ns) clock, or the real one.

    BOTH halves are needed. On tmpfs, which is the laptop's /tmp, a
    directory's SIZE grows with its entries, so a create shows up there
    whatever the clock does; on ext4 a directory is 4096 bytes regardless,
    and its mtime is the only evidence. The first version of this simulation
    coarsened the clock alone, ran on tmpfs, and passed with the backdating
    removed: a fixture that could not exhibit the host's case (2026-09-26).
    """
    if tick is None:
        return os.lstat

    def lstat(path):
        st = os.lstat(path)
        size = EXT4_DIR_SIZE if stat.S_ISDIR(st.st_mode) else st.st_size
        return types.SimpleNamespace(st_size=size, st_mode=st.st_mode,
                                     st_mtime_ns=st.st_mtime_ns // tick * tick)
    return lstat


def _predates_the_session(*paths):
    for path in paths:
        os.utime(path, ns=(LONG_AGO_NS, LONG_AGO_NS))


class TestTheStoreIsElsewhere:
    def test_the_suite_runs_on_a_temporary_store(self):
        from modules import config
        checkout = os.path.realpath(os.path.join(ROOT, "data"))
        assert os.path.realpath(config.DATA_DIR) != checkout
        assert os.path.realpath(config.DATA_DIR) == os.path.realpath(os.environ["NMAS_DATA_DIR"])

    def test_derived_paths_follow_it(self):
        """The paths the modules used to compute for themselves."""
        from modules import agent_runner, agent_timers, ai_assistant, ai_usage_log, config
        root = os.path.realpath(config.DATA_DIR)
        for path in (agent_runner._ACTIVITY_LOG_PATH, agent_timers._TIMERS_FILE,
                     ai_assistant._HISTORIES_DIR, ai_assistant._GLOBAL_KB_FILE,
                     ai_usage_log._LOG_FILE):
            assert os.path.realpath(path).startswith(root + os.sep), path

    @pytest.mark.parametrize("tick", CLOCKS, ids=CLOCK_IDS)
    def test_the_session_guard_sees_a_change(self, tmp_path, tick):
        """Positive control for `pytest_sessionfinish`'s comparison, on every
        clock. The store's last change predates the session, so the control
        backdates it: made and written within microseconds, as the first
        version was, the directory's mtime did not move on the host's 1 ms
        tick, and the control failed there while passing in CI (2026-09-26)."""
        from tests.store_guard import data_tree, tree_changes
        (tmp_path / "lists").mkdir()
        _predates_the_session(tmp_path, tmp_path / "lists")
        before = data_tree(str(tmp_path), lstat=_clock(tick))
        (tmp_path / "lists" / "x.json").write_text("{}")
        # the new file, and its directory's mtime: both are writes
        assert tree_changes(before, data_tree(str(tmp_path), lstat=_clock(tick))) == \
            ["lists", os.path.join("lists", "x.json")]
        assert tree_changes(before, before) == []

    @pytest.mark.parametrize("tick", CLOCKS, ids=CLOCK_IDS)
    def test_a_write_tidied_away_is_still_seen(self, tmp_path, tick):
        """The case the root's own entry exists for: a file created and removed
        leaves nothing below the root, and moves the root's mtime."""
        from tests.store_guard import data_tree, tree_changes
        _predates_the_session(tmp_path)
        before = data_tree(str(tmp_path), lstat=_clock(tick))
        (tmp_path / "gone.json").write_text("{}")
        (tmp_path / "gone.json").unlink()
        assert tree_changes(before, data_tree(str(tmp_path), lstat=_clock(tick))) == ["."]


def _data_literal_joins(path):
    """Calls that join a literal "data" path component."""
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    return [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "join"
            and any(isinstance(a, ast.Constant) and a.value == "data" for a in n.args)]


def _python_sources():
    out = [os.path.join(ROOT, "app.py")]
    out += tracked("modules", "routes", suffix=".py")
    return out


class TestOneOwnerOfTheDataPath:
    def test_the_scan_finds_the_owner(self):
        """Floor and anchor: config.py IS the one join, so the scan can see it."""
        files = _python_sources()
        assert len(files) >= 60, len(files)
        assert _data_literal_joins(os.path.join(ROOT, "modules", "config.py"))

    def test_no_other_module_computes_it(self):
        bad = {os.path.relpath(p, ROOT): lines for p in _python_sources()
               if not p.endswith(os.path.join("modules", "config.py"))
               for lines in [_data_literal_joins(p)] if lines}
        assert bad == {}, bad


class TestImportingStartsNothing:
    """Importing `app` started six threads, including UDP listeners on 1162
    and 9996, so the suite and every script that imports `app` ran a second
    copy of the services."""

    def test_no_thread_is_started_by_an_import(self, tmp_path):
        code = ("import logging, threading, time\n"
                "logging.disable(50)\n"
                "before = {t.name for t in threading.enumerate()}\n"
                "import app\n"
                "time.sleep(0.3)\n"
                "print(sorted(t.name for t in threading.enumerate() if t.name not in before))\n")
        env = dict(os.environ, NMAS_DATA_DIR=str(tmp_path))
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                             capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stderr[-2000:]
        assert out.stdout.strip().splitlines()[-1] == "[]", out.stdout

    def test_running_the_program_still_starts_them(self):
        """The other direction, structurally: the one call is inside the
        `__main__` block, before the server starts."""
        with open(os.path.join(ROOT, "app.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        module_calls = [n for n in tree.body if isinstance(n, ast.Expr)
                        and isinstance(n.value, ast.Call)
                        and getattr(n.value.func, "id", "") in
                        ("_start_background_daemons", "session_reaper")]
        assert module_calls == []
        main = next(n for n in tree.body if isinstance(n, ast.If)
                    and "__main__" in ast.unparse(n.test))
        called = [getattr(n.func, "id", "") for n in ast.walk(main) if isinstance(n, ast.Call)]
        assert "_start_background_daemons" in called


class TestTheStoreIsInitialisedBeforeAnyTest:
    """C43: a result must not depend on which test ran first."""

    def test_the_file_that_errored_alone_passes_alone(self):
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "tests/test_golden_migration.py::TestDuplicateDetection::test_newest_content_wins"],
            capture_output=True, text=True, cwd=ROOT, timeout=120,
            env={k: v for k, v in os.environ.items() if k != "NMAS_TEST_STORE_OWNER"})
        assert done.returncode == 0, done.stdout[-800:]

    def test_the_default_list_exists_before_this_test(self):
        from modules import config
        assert os.path.isdir(os.path.join(config.DATA_DIR, "lists", "default"))


class TestAChangeIsAttributedNotAssumed:
    """On the deployment host the app runs from the checkout the suite runs
    in, and its approval queue wrote while the suite ran; the guard reported
    that as the suite's write and asserted the app does not run there
    (2026-09-26). The guard now attributes."""

    _watch = None

    @classmethod
    def _extra_watch(cls, root):
        """One extra audit hook for this class (hooks cannot be removed), on a
        directory of its own, never the checkout's data/."""
        from tests import store_guard
        if cls._watch is None:
            cls._watch = store_guard.install_write_watch(root)
        return cls._watch

    def test_the_test_processs_own_writes_are_seen(self, tmp_path_factory):
        import shutil
        root = tmp_path_factory.getbasetemp() / "attribution-root"
        root.mkdir(exist_ok=True)
        watch = self._extra_watch(str(root))
        watch.current, start = "this-test", len(watch.writes)
        (root / "a.json").write_text("{}")                   # open for writing
        os.mkdir(root / "d")
        os.replace(root / "a.json", root / "d" / "b.json")   # rename
        shutil.rmtree(root / "d")
        (tmp_path_factory.getbasetemp() / "outside.json").write_text("{}")  # not under root
        seen = [(e, os.path.basename(p)) for _t, e, p in watch.writes[start:]]
        watch.current = ""
        assert ("open", "a.json") in seen and ("os.mkdir", "d") in seen
        assert ("os.rename", "b.json") in seen and ("shutil.rmtree", "d") in seen
        assert not any(p == "outside.json" for _e, p in seen)

    def test_a_read_is_not_a_write(self, tmp_path_factory):
        root = tmp_path_factory.getbasetemp() / "attribution-root"
        root.mkdir(exist_ok=True)
        (root / "r.json").write_text("{}")
        watch = self._extra_watch(str(root))
        start = len(watch.writes)
        (root / "r.json").read_text()
        os.stat(root / "r.json")
        assert watch.writes[start:] == []

    def test_the_app_is_found_by_its_argv_in_proc(self, tmp_path):
        from tests import store_guard
        checkout = tmp_path / "checkout"
        checkout.mkdir()
        (checkout / "app.py").write_text("")
        proc = tmp_path / "proc"
        for pid, argv, cwd in (("4242", [b"/usr/bin/python3", str(checkout / "app.py").encode()], "/"),
                               ("4343", [b"python3", b"app.py"], str(checkout)),
                               ("4444", [b"python3", b"-m", b"pytest"], str(checkout)),
                               ("4545", [b"python3", b"app.py"], str(tmp_path))):
            (proc / pid).mkdir(parents=True)
            (proc / pid / "cmdline").write_bytes(b"\0".join(argv) + b"\0")
            os.symlink(cwd, proc / pid / "cwd")
        found = sorted(pid for pid, _argv in store_guard.processes_running_from(str(checkout), str(proc)))
        assert found == [4242, 4343], found
        assert store_guard.processes_running_from(str(checkout), str(tmp_path / "no-proc")) == []

    def _judge(self, changed, writes, apps=None):
        from tests import store_guard

        def find_apps():
            if apps is None:
                raise AssertionError("asked for the app when nothing needed explaining")
            return apps
        return store_guard.judge(changed, writes, "/c/data", find_apps)

    def test_a_write_by_a_test_fails_naming_the_test(self):
        fail, msg = self._judge(["lists", "lists/x.json"],
                                [("tests/test_x.py::t", "open", "/c/data/lists/x.json")])
        assert fail and "tests/test_x.py::t" in msg

    def test_the_apps_write_is_a_note_naming_the_app(self):
        fail, msg = self._judge(["lists/default/approval_queue.json"], [],
                                apps=[(361070, "/usr/bin/python3 /c/app.py")])
        assert not fail and msg.startswith("note:") and "361070" in msg

    def test_an_unexplained_change_still_fails(self):
        fail, msg = self._judge(["lists/default/approval_queue.json"], [], apps=[])
        assert fail and "no app process is running" in msg

    def test_nothing_changed_is_silent(self):
        assert self._judge([], []) == (False, "")


class TestAChildIsGivenTheTestStore:
    def test_an_explicit_env_still_gets_the_test_store(self):
        from modules import config
        out = subprocess.run([sys.executable, "-c", "import os; print(os.environ.get('NMAS_DATA_DIR'))"],
                             capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"}, timeout=30)
        assert os.path.realpath(out.stdout.strip()) == os.path.realpath(config.DATA_DIR)

    def test_a_child_that_writes_into_the_forbidden_data_is_recorded(self, tmp_path, monkeypatch):
        from tests import network_guard
        guard = network_guard.spawn_guard()
        forbidden = tmp_path / "checkout-data"
        forbidden.mkdir()
        monkeypatch.setattr(guard, "checkout_data", str(forbidden))
        subprocess.run([sys.executable, "-c", f"open({str(forbidden / 'x.json')!r}, 'w').write('{{}}')"],
                       env={"PATH": "/usr/bin:/bin"}, timeout=30)
        tried = guard.take()
        assert len(tried) == 1 and "write open" in tried[0] and "x.json" in tried[0], tried


class TestADirFdPathIsResolvedThroughItsDirectory:
    """`shutil.rmtree` removes entries as `os.rmdir(name, dir_fd=...)`. Resolved
    against the cwd (the checkout root), a temp directory's own `data`
    subdirectory was reported as the checkout's data/ (2026-09-26)."""

    def test_a_directory_named_data_elsewhere_is_not_the_checkouts(self, tmp_path):
        import shutil
        from tests import store_guard
        victim = tmp_path / "scratch" / "data" / "inner"
        victim.mkdir(parents=True)
        start = len(store_guard._watch.writes)
        shutil.rmtree(tmp_path / "scratch")
        assert store_guard._watch.writes[start:] == []

    def test_the_resolution_itself(self, tmp_path):
        from tests import store_guard
        fd = os.open(str(tmp_path), os.O_RDONLY)
        try:
            assert store_guard.resolve("data", fd) == os.path.realpath(str(tmp_path / "data"))
        finally:
            os.close(fd)
        assert store_guard.resolve("data", None) == os.path.realpath("data")
        assert store_guard.resolve(5, None) is None

    def test_a_child_removing_a_tree_elsewhere_records_nothing(self, tmp_path):
        from tests import network_guard
        (tmp_path / "t" / "data" / "x").mkdir(parents=True)
        subprocess.run([sys.executable, "-c", f"import shutil; shutil.rmtree({str(tmp_path / 't')!r})"],
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))), timeout=30)
        assert network_guard.spawn_guard().take() == []
