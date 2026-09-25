"""Concurrent writers of ``user_settings.json`` lose nothing (register C20).

Measured 2026-09-25 before the fix: two threads each calling
`set_user_setting()` 150 times left the file UNREADABLE in both runs
(`JSONDecodeError: Extra data`), with 141 writes failing. Every writer used
one temp name, so two documents landed in one inode, and nothing serialised
the read-modify-write. The unreadable-file guard then refused every write,
so nothing was erased, and nothing could be saved until the `.corrupt` copy
was restored by hand: the 2026-09-23 state by a different road.

These drive the real functions on a real file, concurrently, and count what
survived. A test that only checked the lock is taken would pass a lock
taken around the wrong span.
"""

import json
import os
import subprocess
import sys
import threading

import pytest

from modules import config

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "user_settings.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "USER_SETTINGS_FILE", str(path))
    return path


def _run_threads(*targets):
    threads = [threading.Thread(target=t) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join()


class TestThreadsLoseNothing:

    N = 60

    def test_two_threads_writing_different_keys_keep_every_one(self, settings_file):
        errors = []

        def writer(prefix):
            def run():
                for i in range(self.N):
                    try:
                        config.set_user_setting(f"{prefix}{i}", i)
                    except Exception as exc:          # noqa: BLE001
                        errors.append(repr(exc))
            return run

        _run_threads(writer("a"), writer("b"))
        stored = json.loads(settings_file.read_text(encoding="utf-8"))
        assert errors == []
        assert len(stored) == 2 * self.N, (
            f"{2 * self.N - len(stored)} write(s) lost")

    def test_write_settings_and_set_user_setting_do_not_clobber_each_other(
            self, settings_file):
        """Two different read-modify-write paths, one lock."""
        from modules.settings_schema import write_settings

        def plain():
            for i in range(self.N):
                config.set_user_setting(f"k{i}", i)

        def declared():
            for i in range(self.N):
                assert write_settings({"kea_username": f"u{i}"})["ok"]

        _run_threads(plain, declared)
        stored = json.loads(settings_file.read_text(encoding="utf-8"))
        assert all(f"k{i}" in stored for i in range(self.N))
        assert stored["kea_username"] == f"u{self.N - 1}"

    def test_no_temp_file_is_left_behind(self, settings_file):
        _run_threads(*(lambda p=p: [config.set_user_setting(f"{p}{i}", i)
                                    for i in range(20)] for p in "xyz"))
        leftovers = [n for n in os.listdir(settings_file.parent) if ".tmp" in n]
        assert leftovers == []

    @pytest.mark.skipif(os.name != "posix", reason="flock is POSIX-only")
    def test_the_lock_file_is_owner_only(self, settings_file):
        config.set_user_setting("x", 1)
        lock = f"{settings_file}.lock"
        assert os.stat(lock).st_mode & 0o777 == 0o600


_WRITER = """
import sys
sys.path.insert(0, {repo!r})
from modules import config
config.USER_SETTINGS_FILE = {path!r}
for i in range({n}):
    config.set_user_setting("{prefix}%d" % i, i)
"""


@pytest.mark.skipif(os.name != "posix", reason="the cross-process lock is flock")
class TestProcessesLoseNothing:
    """A CLI (`nmas-retire`) writes settings while the app is running."""

    def test_two_processes_keep_every_key(self, settings_file):
        n = 40
        procs = [subprocess.Popen(
            [sys.executable, "-c", _WRITER.format(repo=REPO, path=str(settings_file),
                                                  n=n, prefix=prefix)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE) for prefix in "pq"]
        for proc in procs:
            _, err = proc.communicate(timeout=120)
            assert proc.returncode == 0, err.decode()[-2000:]
        stored = json.loads(settings_file.read_text(encoding="utf-8"))
        assert len(stored) == 2 * n, f"{2 * n - len(stored)} write(s) lost"


class TestTheSuiteDoesNotDependOnFileOrder:
    """C20's other half. `test_onboard_plan.py` run FIRST used to leave
    `modules.integrations.base` bound to its `get_setting` stub, so the Kea
    route's echo read `''`. Measured deterministic: 3 of 3 failed in that
    order and 2 of 2 passed in the other. `conftest.py` now imports the
    application before any test can patch it."""

    def test_the_order_that_failed_passes(self):
        out = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             "tests/test_onboard_plan.py",
             "tests/test_settings_write_path.py::TestASaveThatDidNotPersistSaysSo"],
            cwd=REPO, capture_output=True, text=True, timeout=300)
        assert out.returncode == 0, out.stdout[-3000:]
        assert " passed" in out.stdout and "failed" not in out.stdout


class TestEveryReadModifyWriteHoldsTheLock:
    """The class, not the four sites found by hand.

    A function that calls both `load_user_settings()` and
    `save_user_settings()` is a read-modify-write of the file, and must hold
    `settings_lock()`. Found by hand: `set_user_setting`, `write_settings`,
    `migrate` (which runs on every GET of the general settings panel), and the
    general-settings POST, which bypasses `write_settings()` entirely.
    """

    #: A function that does the read-modify-write WITHOUT the lock, because
    #: its only caller holds it. Each claim is checked below, not trusted.
    LOCKED_BY_CALLER = {"_migrate_unlocked": "migrate"}

    def _functions(self):
        import ast

        found = {}
        paths = ["app.py"]
        for top in ("modules", "routes", "scripts"):
            for root, _, files in os.walk(os.path.join(REPO, top)):
                paths += [os.path.join(root, f) for f in files if f.endswith(".py")]
        for path in paths:
            full = path if os.path.isabs(path) else os.path.join(REPO, path)
            with open(full, encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found[(os.path.relpath(full, REPO), node.name)] = node
        return found

    @staticmethod
    def _calls(node, name):
        import ast

        return any(isinstance(n, ast.Call) and (
            getattr(n.func, "id", None) == name or getattr(n.func, "attr", None) == name)
            for n in ast.walk(node))

    def test_each_one_holds_the_lock(self):
        functions = self._functions()
        rmw = {key: node for key, node in functions.items()
               if self._calls(node, "load_user_settings")
               and self._calls(node, "save_user_settings")}
        # Floor: the four found by hand, so a scan that matches nothing fails.
        names = {name for _, name in rmw}
        assert {"set_user_setting", "write_settings", "_migrate_unlocked"} <= names, names
        assert len(rmw) >= 4, sorted(rmw)

        unlocked = []
        for (path, name), node in rmw.items():
            if self._calls(node, "settings_lock"):
                continue
            caller = self.LOCKED_BY_CALLER.get(name)
            caller_node = functions.get((path, caller)) if caller else None
            if caller_node is not None and self._calls(caller_node, "settings_lock") \
                    and self._calls(caller_node, name):
                continue
            unlocked.append(f"{path}:{name}")
        assert unlocked == [], (
            "a read-modify-write of user_settings.json without settings_lock(): "
            + ", ".join(unlocked))
