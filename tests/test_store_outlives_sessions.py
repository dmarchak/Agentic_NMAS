"""C780: the test store and the spawn guard's folder live as long as the process, not a session.

mutmut runs two pytest sessions in one process (its statistics run, then its clean run). The
program loads the store's key once per process (`modules.device`), and the first session's end
removed the store, so the second sealed values with a key no file held, and a test's child
process refused the store (the nightly's walk, 2026-10-14: `test_inventory_role.py`, after 992
tests). The spawn guard's folder, which holds the refusing shims a child finds first on its
PATH, went with it. Here a nested process runs two sessions of a probe the same way.
"""
import os
import subprocess
import sys

from tests import tmp_roots

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROBE = '''
import os
from tests import network_guard


def test_the_store_key_and_the_shims_are_there():
    from modules import device  # noqa: F401  (loads the key once per process)
    store = os.environ["NMAS_DATA_DIR"]
    print("STORE", store, "GUARD", network_guard.spawn_guard().root)
    assert os.path.exists(os.path.join(store, "key.key")), "the key the process holds is gone"
    assert os.path.isdir(network_guard.spawn_guard().root), "the shims' folder is gone"
'''

TWO_SESSIONS = '''
import sys
import pytest
args = ["-q", "-s", "-p", "no:randomly", "-p", "no:cacheprovider", "-p", "tests.conftest",
        "--rootdir", sys.argv[1], "-c", sys.argv[2], sys.argv[3]]
first, second = pytest.main(args), pytest.main(args)
print("SESSIONS", int(first), int(second))
sys.exit(int(first) or int(second))
'''


def test_a_second_session_in_one_process_keeps_the_store_and_the_shims(tmp_path):
    probe = tmp_path / "test_probe_store.py"
    probe.write_text(PROBE)
    env = dict(os.environ, NMAS_PROBE_RUN="1")
    env.pop("PYTEST_XDIST_WORKER", None)
    out = subprocess.run([sys.executable, "-c", TWO_SESSIONS, ROOT,
                          os.path.join(ROOT, "pytest.ini"), str(probe)],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert "SESSIONS 0 0" in out.stdout, out.stdout[-1500:] + out.stderr[-800:]
    stores = {l.split()[1] for l in out.stdout.splitlines() if l.startswith("STORE ")}
    guards = {l.split()[3] for l in out.stdout.splitlines() if l.startswith("STORE ")}
    assert len(stores) == 1 and len(guards) == 1, "both sessions ran on the process's own"
    # The process has exited: what it made is gone with it.
    assert not os.path.exists(stores.pop()), "the store outlived its process"
    assert not os.path.exists(guards.pop()), "the spawn guard's folder outlived its process"


def _dead_pid() -> int:
    with open("/proc/sys/kernel/pid_max", encoding="utf-8") as fh:
        return int(fh.read()) + 1


def test_a_killed_processs_folders_are_removed_and_a_live_ones_kept(tmp_path):
    def folder(name, owner):
        path = tmp_path / name
        path.mkdir()
        (path / "key.key").write_text("x")
        if owner is not None:
            (path / ".owner").write_text(str(owner))
        return path
    dead_store = folder("nmas-test-data-abc", _dead_pid())
    dead_guard = folder("nmas-test-spawn-def", _dead_pid())
    live = folder("nmas-test-data-ghi", os.getpid())
    unowned = folder("nmas-test-data-jkl", None)
    other = folder("someone-elses", _dead_pid())
    assert tmp_roots.prune_dead_process_folders(str(tmp_path)) == [
        "nmas-test-data-abc", "nmas-test-spawn-def"]
    assert not dead_store.exists() and not dead_guard.exists()
    assert live.exists() and unowned.exists() and other.exists()


def test_this_processs_store_and_guard_are_marked_as_its_own():
    from tests import network_guard
    for folder in (os.environ["NMAS_DATA_DIR"], network_guard.spawn_guard().root):
        with open(os.path.join(folder, ".owner"), encoding="utf-8") as fh:
            assert int(fh.read()) == os.getpid(), folder
