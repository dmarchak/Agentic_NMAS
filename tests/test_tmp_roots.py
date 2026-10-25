"""C776: pytest's temporary roots of killed runs are removed when the next run starts
(tests/tmp_roots.py). Measured 2026-10-14: 429 locked roots holding 842,278 files filled 88% of
the tmpfs /tmp's inodes, and the gate then failed hundreds of tests unable to make a folder."""
import json
import os
import subprocess
import sys

from tests import tmp_roots

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _dead_pid() -> int:
    """A pid no process can have: above the kernel's pid_max."""
    with open("/proc/sys/kernel/pid_max", encoding="utf-8") as fh:
        return int(fh.read()) + 1


def _root(parent, name, owner=None, files=3):
    path = parent / name
    path.mkdir()
    for i in range(files):
        (path / f"made-by-a-test-{i}").write_text("x")
    if owner is not None:
        (path / ".lock").write_text(str(owner))
    return path


def test_a_root_whose_owner_is_gone_is_removed_and_nothing_else(tmp_path):
    dead = _dead_pid()
    gone = _root(tmp_path, "pytest-1", dead)
    alive = _root(tmp_path, "pytest-2", os.getpid())          # another shard, running now
    unlocked = _root(tmp_path, "pytest-3")                     # pytest's own rule keeps it
    current = _root(tmp_path, "pytest-4", dead)                # this run's, whatever its lock
    other = _root(tmp_path, "something-else", dead)            # not pytest's
    garbled = _root(tmp_path, "pytest-5")
    (garbled / ".lock").write_text("not a pid")
    assert tmp_roots.prune_dead_roots(str(tmp_path), current=str(current)) == ["pytest-1"]
    assert not gone.exists()
    assert alive.exists() and unlocked.exists() and current.exists() and other.exists()
    assert garbled.exists()


def test_the_owner_rule(tmp_path):
    assert tmp_roots.owner_gone(str(_root(tmp_path, "pytest-1", _dead_pid())))
    assert not tmp_roots.owner_gone(str(_root(tmp_path, "pytest-2", os.getpid())))
    assert not tmp_roots.owner_gone(str(_root(tmp_path, "pytest-3")))
    assert not tmp_roots.owner_gone(str(tmp_path / "absent"))


def test_a_run_removes_the_roots_killed_runs_left(tmp_path):
    """Through the real conftest: a nested run whose roots' parent holds a killed run's root
    (its lock's owner gone) and a live one's; after the run only the live one is left."""
    parent = tmp_path / "roots"
    parent.mkdir()
    killed = _root(parent, "pytest-7", _dead_pid(), files=50)
    live = _root(parent, "pytest-8", os.getpid())
    probe = tmp_path / "test_probe_roots.py"
    probe.write_text("def test_nothing(tmp_path):\n    assert tmp_path.exists()\n")
    env = dict(os.environ, NMAS_PROBE_RUN="1")
    env.pop("PYTEST_XDIST_WORKER", None)
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:randomly", "-p", "no:cacheprovider",
         "-p", "tests.conftest", "--rootdir", ROOT, "-c", os.path.join(ROOT, "pytest.ini"),
         "--basetemp", str(parent / "pytest-9"), str(probe)],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout[-800:] + out.stderr[-800:]
    assert not killed.exists(), "the killed run's root is left"
    assert live.exists(), "a live run's root was removed"


#: A probe that writes where its run's pytest base folder was, and the run's in-flight folder.
WHERE = ("import json, os\n\n"
         "def test_where(tmp_path_factory):\n"
         "    with open(os.environ['PROBE_OUT'], 'w', encoding='utf-8') as fh:\n"
         "        json.dump({'base': str(tmp_path_factory.getbasetemp()),\n"
         "                   'inflight': os.environ['NMAS_TEST_INFLIGHT']}, fh)\n")


def _nmas_test(tmp_path, n, *extra):
    """Start the real scripts/nmas-test over the WHERE probe (as test_suite_bound runs it)."""
    probe =tmp_path / f"test_probe_where_{n}.py"
    probe.write_text(WHERE)
    env = dict(os.environ, PYTHON=sys.executable, NMAS_PROBE_RUN="1",
               PROBE_OUT=str(tmp_path / f"where-{n}.json"))
    env.pop("PYTEST_XDIST_WORKER", None)
    env.pop("NMAS_TEST_INFLIGHT", None)
    return subprocess.Popen(
        [os.path.join(ROOT, "scripts", "nmas-test"), "--allow-unconfined", "-q",
         "-p", "no:randomly", "-p", "no:cacheprovider", "-p", "tests.conftest",
         "--rootdir", ROOT, "-c", os.path.join(ROOT, "pytest.ini"), *extra, str(probe)],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_each_run_has_its_own_base_folder_removed_at_its_end(tmp_path):
    """C1670 (2026-10-25): the gate's five shards shared pytest's one base folder under
    /tmp/pytest-of-<user>; each session's start removed the older numbered folders there, two
    removed one at once, and pytest's warning ("(rm_rf) error removing …garbage-…") turned a
    whole pass into the gate's refusal. Each scripts/nmas-test run now gives pytest a base
    folder inside its own in-flight folder: three runs started together each use their own,
    none warns, and each is gone when its run ends."""
    runs =[_nmas_test(tmp_path, n) for n in range(3)]
    outs = [p.communicate(timeout=120) for p in runs]
    seen = []
    for n, (p, (out, err)) in enumerate(zip(runs, outs)):
        assert p.returncode == 0, out[-800:] + err[-800:]
        assert "warning" not in out.lower(), out[-800:]
        where = json.loads((tmp_path / f"where-{n}.json").read_text())
        assert where["base"] == os.path.join(where["inflight"], "t"), where
        # No longer than pytest's own root (`/tmp/pytest-of-<user>/pytest-<n>`): a test's Unix
        # socket under its tmp_path has 107 bytes in all (test_no_pattern_kill's did not fit).
        assert len(where["base"]) <= len(f"/tmp/pytest-of-{os.environ.get('USER', 'u')}/pytest-0000"), where
        assert not os.path.exists(where["inflight"]), f"run {n}'s folder is left: {where}"
        seen.append(where["base"])
    assert len(set(seen)) == 3, seen


def test_a_base_folder_asked_for_is_honoured(tmp_path):
    asked = tmp_path / "asked-for"
    p = _nmas_test(tmp_path, 9, "--basetemp", str(asked))
    out, err = p.communicate(timeout=120)
    assert p.returncode == 0, out[-800:] + err[-800:]
    assert json.loads((tmp_path / "where-9.json").read_text())["base"] == str(asked)
