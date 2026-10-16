"""C987: a read of what is held costs what is HELD now, never what was ever held.

Every device ever held leaves its lock file (`release()` empties it and keeps it, so a crash's
non-empty leftover can be told apart, CONCURRENCY_AUDIT R5), and `held()` listed the network's
whole folder and probed every file. Since C537 the In progress chip on every v2 page reads it
on every page load and every `device_progress` step: measured 2026-10-16, 0.02 ms at no files,
3.8 ms at 90, about 40 ms at 900, 50 ms at 2,700.

Now each network's folder keeps `holds/`, one empty marker per device whose lock file may carry
a record, created by the holder after its `flock` and before its record, removed after the
record is emptied and before the `flock` is given up. A reader probes only the marked devices.

Measured here, by counting (never by timing), and with REAL second processes:

- the chip, `held_anywhere` (the update gate and `/health/operations`) and Needs attention's
  interrupted operations touch the same files at 90 released lock files as at 900, and see the
  two devices another process holds (the control: today's folder scan moves with the 900);
- a hold is marked before its record is written and unmarked after it is emptied, while its
  `flock` is still held;
- another process's hold is listed, and its death is a leftover: listed as interrupted, never as
  held, kept when the next operation takes the device, and its marker then cleared;
- a process that dies in each window (after its `flock` and before its marker; after its marker
  and before its record; after emptying its record and before its unmark) leaves nothing held
  and nothing interrupted, and the device is taken again at once;
- a folder written before markers is read in full until it is indexed; indexing marks exactly
  its records; an acquire indexes a folder first; markers that cannot be listed are never
  "nothing held";
- the app indexes every folder at its start.
"""

import ast
import builtins
import json
import os
import subprocess
import sys
import uuid

import pytest

from modules.nsot import device_ops as D

fcntl = pytest.importorskip("fcntl")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def net():
    """A network of this test's own: the store is shared by every test on the worker."""
    name = f"C987-{uuid.uuid4().hex[:8]}"
    yield name
    with D._mu:
        mine = [(k, v) for k, v in D._held.items() if k[0] == D._list_key(name)]
        for k, _v in mine:
            D._held.pop(k)
    for _k, info in mine:
        if info["fd"] is not None:
            os.close(info["fd"])


def _folder(name):
    """The network's lock folder, found independently of the code under test."""
    from modules import config
    return os.path.join(config.DATA_DIR, "device_ops", config.list_slug(name))


def _release_many(name, count, start=0):
    """*count* devices held and released the real way: what every device ever held leaves."""
    for i in range(start, start + count):
        D.acquire(name, f"gone{i:04d}", "capture", "earlier@example.invalid")
        D.release(name, f"gone{i:04d}")


def _child(name, devices, before=""):
    """A REAL second process that holds *devices* (after running *before*, which may break it
    on purpose) and says so, then waits until it is killed."""
    from modules import config

    code = ("import os, sys\n"
            f"sys.path.insert(0, {ROOT!r})\n"
            "from modules.nsot import device_ops as D\n"
            + before +
            f"for host in {list(devices)!r}:\n"
            f"    D.acquire({name!r}, host, 'capture', 'other@example.invalid')\n"
            "D.note('pre_snapshot')\n"
            "print('held', flush=True)\n"
            "sys.stdin.read()\n")
    child = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                             env=dict(os.environ, NMAS_DATA_DIR=config.DATA_DIR))
    return child


def _wait_held(child):
    line = child.stdout.readline().strip()
    assert line == "held", child.stderr.read()


def _kill(child):
    child.kill()
    child.wait(10)


def _dies_at(name, host, break_it):
    """A child that holds *host* and releases it, with *break_it* run first: it ends the
    process at one step of the acquire or the release (`os._exit`, which runs no `finally`
    and no `atexit`: a crash, as far as the hold can tell)."""
    from modules import config

    code = ("import os, sys\n"
            f"sys.path.insert(0, {ROOT!r})\n"
            "from modules.nsot import device_ops as D\n"
            + break_it +
            f"D.acquire({name!r}, {host!r}, 'deploy', 'other@example.invalid')\n"
            f"D.release({name!r}, {host!r})\n"
            "print('finished', flush=True)\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=dict(os.environ, NMAS_DATA_DIR=config.DATA_DIR), timeout=60)
    assert out.returncode == 0 and "finished" not in out.stdout, out.stderr


class Touches:
    """Every open, `flock` and folder listing of a path under one network's folder."""

    def __init__(self, folder, monkeypatch):
        self.folder, self.opens, self.flocks, self.lists = folder, 0, 0, 0
        real_open, real_os_open = builtins.open, os.open
        real_flock, real_listdir = fcntl.flock, os.listdir

        def under(path):
            try:
                return os.path.realpath(os.fsdecode(path)).startswith(
                    os.path.realpath(folder))
            except TypeError:
                return False

        def counting_open(file, *a, **k):
            if not isinstance(file, int) and under(file):
                self.opens += 1
            return real_open(file, *a, **k)

        def counting_os_open(path, *a, **k):
            if under(path):
                self.opens += 1
            return real_os_open(path, *a, **k)

        def counting_flock(fd, op):
            try:
                if under(os.readlink(f"/proc/self/fd/{fd}")):
                    self.flocks += 1
            except OSError:
                pass
            return real_flock(fd, op)

        def counting_listdir(path="."):
            if os.path.realpath(os.fsdecode(path)) == os.path.realpath(folder):
                self.lists += 1
            return real_listdir(path)

        monkeypatch.setattr(builtins, "open", counting_open)
        monkeypatch.setattr(os, "open", counting_os_open)
        monkeypatch.setattr(fcntl, "flock", counting_flock)
        monkeypatch.setattr(os, "listdir", counting_listdir)

    def total(self):
        return {"opens": self.opens, "flocks": self.flocks, "folder_listed": self.lists}


def _reads(name, monkeypatch, read):
    """What *read* touched in the network's folder."""
    with monkeypatch.context() as mp:
        t = Touches(_folder(name), mp)
        got = read()
    return t.total(), got


def _chip(name):
    from modules import in_flight
    return in_flight.chip([name], "viewer@example.invalid")


class TestTheReadIsFixedWhateverWasEverHeld:
    """The scale rule: the In progress chip and every other reader of the holds touch the same
    files at 90 released lock files as at 900, and see the two another process holds."""

    @pytest.fixture
    def fleet(self, net):
        child = _child(net, ["r1", "r2"])
        try:
            _wait_held(child)
            yield net, child
        finally:
            _kill(child)

    @pytest.mark.parametrize("what", ("chip", "held_anywhere", "interrupted_anywhere"))
    def test_the_files_touched_do_not_move_with_the_900(self, fleet, monkeypatch, what):
        name, _child_ = fleet
        reads = {
            "chip": lambda: {r["device"] for r in _chip(name)["running"]},
            "held_anywhere": lambda: {h["device"] for h in D.held_anywhere()
                                      if str(h.get("list")).lower() == name.lower()},
            "interrupted_anywhere": lambda: {r["device"] for r in D.interrupted_anywhere()
                                             if str(r.get("list")).lower() == name.lower()},
        }[what]
        _release_many(name, 90)
        at_90, seen_90 = _reads(name, monkeypatch, reads)
        _release_many(name, 810, start=90)
        at_900, seen_900 = _reads(name, monkeypatch, reads)
        expect = set() if what == "interrupted_anywhere" else {"r1", "r2"}
        assert seen_90 == seen_900 == expect, (seen_90, seen_900)
        assert at_90 == at_900, (f"{what} touches what was EVER held: at 90 released lock "
                                 f"files {at_90}, at 900 {at_900}")
        # The floor: the read probed the two held devices (an open and a flock each).
        assert at_900["opens"] >= 2 and at_900["flocks"] >= 2, at_900
        assert at_900["folder_listed"] == 0, at_900

    def test_the_counters_count(self, net, monkeypatch):
        """The control on the instrument: a read that opens every lock file is seen moving."""
        _release_many(net, 3)

        def every_file():
            folder = _folder(net)
            for n in os.listdir(folder):
                if n.endswith(".lock"):
                    with open(os.path.join(folder, n), encoding="utf-8") as fh:
                        fh.read()
        three, _ = _reads(net, monkeypatch, every_file)
        _release_many(net, 2, start=3)
        five, _ = _reads(net, monkeypatch, every_file)
        assert (three["opens"], five["opens"]) == (3, 5)
        assert (three["folder_listed"], five["folder_listed"]) == (1, 1)


class TestAHoldIsMarkedAroundItsRecord:
    def _marker(self, name, host):
        return os.path.join(_folder(name), "holds", host)

    def test_marked_before_the_record_and_unmarked_after_it_is_emptied(self, net,
                                                                       monkeypatch):
        """No record without its marker: marked while the lock file is still EMPTY and the
        flock already taken; unmarked when the file is empty again and the flock still taken
        (another process probing it is refused)."""
        lock = os.path.join(_folder(net), "r5.lock")
        seen = []

        def held_by_someone():
            fd = os.open(lock, os.O_RDONLY)
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
                return False
            except BlockingIOError:
                return True
            finally:
                os.close(fd)

        real_mark, real_unmark = D._mark, D._unmark

        def mark(folder, host):
            seen.append(("mark", os.path.getsize(lock), held_by_someone()))
            real_mark(folder, host)

        def unmark(folder, host):
            seen.append(("unmark", os.path.getsize(lock), held_by_someone()))
            real_unmark(folder, host)
        monkeypatch.setattr(D, "_mark", mark)
        monkeypatch.setattr(D, "_unmark", unmark)
        D.acquire(net, "r5", "deploy", "a@example.invalid")
        assert os.path.exists(self._marker(net, "r5")) and os.path.getsize(lock) > 0
        D.release(net, "r5")
        assert seen == [("mark", 0, True), ("unmark", 0, True)], seen
        assert not os.path.exists(self._marker(net, "r5"))
        assert os.path.exists(lock) and os.path.getsize(lock) == 0   # the lock file stays

    def test_a_hold_that_cannot_be_marked_is_refused_and_writes_nothing(self, net,
                                                                       monkeypatch):
        """No page would see it, nor its record if its process ended: refused, the flock given
        back, the lock file left empty, and the device taken at once when marking works."""
        def cannot(folder, host):
            raise PermissionError(13, "Permission denied", os.path.join(folder, "holds", host))
        monkeypatch.setattr(D, "_mark", cannot)
        with pytest.raises(PermissionError):
            D.acquire(net, "r6", "deploy", "a@example.invalid")
        assert os.path.getsize(os.path.join(_folder(net), "r6.lock")) == 0
        assert D.holder(net, "r6") is None
        monkeypatch.undo()
        D.acquire(net, "r6", "deploy", "a@example.invalid")
        D.release(net, "r6")

    def test_a_released_device_is_never_probed_again(self, net, monkeypatch):
        _release_many(net, 5)
        assert os.listdir(os.path.join(_folder(net), "holds")) == []
        cost, rows = _reads(net, monkeypatch, lambda: D.held(net))
        assert rows == [] and cost == {"opens": 0, "flocks": 0, "folder_listed": 0}, cost


class TestAcrossProcesses:
    def test_another_process_s_hold_is_listed_and_its_death_is_a_leftover(self, net):
        from modules import attention

        _release_many(net, 50)
        child = _child(net, ["r1", "r2"])
        try:
            _wait_held(child)
            assert {h["device"] for h in D.held(net)} == {"r1", "r2"}
            mine = [h for h in D.held_anywhere() if h["list"].lower() == net.lower()]
            assert {h["device"] for h in mine} == {"r1", "r2"}
            assert all(h["pid"] == child.pid for h in mine)
            assert {r["device"] for r in _chip(net)["running"]} == {"r1", "r2"}
            assert D.interrupted(net) == []
            with pytest.raises(D.DeviceBusy) as busy:
                D.acquire(net, "r1", "deploy", "a@example.invalid")
            assert "r1 is being captured by other@example.invalid" in str(busy.value)
        finally:
            _kill(child)                               # SIGKILL: a crash, nothing released
        assert _unmarked_records(_folder(net)) == []
        assert D.held(net) == []
        left = D.interrupted(net)
        assert sorted(r["device"] for r in left) == ["r1", "r2"]
        assert all(r["pid"] == child.pid and r["found_at"] is None
                   and r["progress"]["step"] == "pre_snapshot" for r in left)
        rows = [r for r in attention.interrupted_source()["rows"]
                if f"|{child.pid}|" in r["id"]]
        assert len(rows) == 1 and rows[0]["devices"] == ["r1", "r2"]

    def test_the_next_operation_keeps_the_record_and_clears_its_marker(self, net):
        child = _child(net, ["r3"])
        _wait_held(child)
        _kill(child)
        D.acquire(net, "r3", "capture", "next@example.invalid")
        D.release(net, "r3")
        assert not os.path.exists(os.path.join(_folder(net), "holds", "r3"))
        listed = [r for r in D.interrupted(net) if r.get("pid") == child.pid]
        assert len(listed) == 1 and listed[0]["found_at"], listed
        with open(os.path.join(_folder(net), D.INTERRUPTED_LOG), encoding="utf-8") as fh:
            kept = [json.loads(line) for line in fh]
        assert [k["found_by"]["operation"] for k in kept
                if k["record"].get("pid") == child.pid] == ["capture"]


#: Each window a holder can die in, as the lines that end its process there.
WINDOWS = {
    "after_the_flock_before_the_marker":
        "D._mark = lambda folder, name: os._exit(0)\n",
    "after_the_marker_before_the_record":
        "_m = D._mark\n"
        "def _then_die(folder, name):\n"
        "    _m(folder, name)\n"
        "    os._exit(0)\n"
        "D._mark = _then_die\n",
    "after_emptying_the_record_before_the_unmark":
        "D._unmark = lambda folder, name: os._exit(0)\n",
}


def _unmarked_records(folder):
    """Lock files carrying a record with no marker: a hold or a crash's record no page reads."""
    marks = set(os.listdir(os.path.join(folder, "holds")))
    return [n for n in os.listdir(folder) if n.endswith(".lock")
            and os.path.getsize(os.path.join(folder, n)) and n[:-5] not in marks]


class TestACrashInEachWindow:
    @pytest.mark.parametrize("window", sorted(WINDOWS))
    def test_nothing_is_held_nothing_interrupted_and_it_is_taken_again(self, net, window):
        _dies_at(net, "r7", WINDOWS[window])
        assert _unmarked_records(_folder(net)) == [], "a record no page would read"
        lock = os.path.join(_folder(net), "r7.lock")
        assert os.path.getsize(lock) == 0, "a window this test aims at wrote a record"
        marked = os.path.exists(os.path.join(_folder(net), "holds", "r7"))
        assert marked == (window != "after_the_flock_before_the_marker")
        assert D.held(net) == [] and D.interrupted(net) == []
        D.acquire(net, "r7", "deploy", "a@example.invalid")
        assert [h["device"] for h in D.held(net)] == ["r7"]
        D.release(net, "r7")
        assert not os.path.exists(os.path.join(_folder(net), "holds", "r7"))
        assert D.interrupted(net) == []


def _plant(name, records):
    """A folder written BEFORE markers: lock files as today's release and a crash left them."""
    folder = _folder(name)
    os.makedirs(folder, exist_ok=True)
    for host, record in records.items():
        with open(os.path.join(folder, f"{host}.lock"), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(record) if record else "")
    return folder


LEFT = {"device": "r9", "operation": "restore", "actor": "gone@example.invalid",
        "started": 1760000000.0, "pid": 4242, "progress": {"step": "verify", "at": 1760000001.0}}


class TestAFolderFromBeforeMarkers:
    def test_it_is_read_in_full_until_indexed_and_the_read_creates_nothing(self, net):
        folder = _plant(net, {"r9": LEFT, "r1": None, "r2": None})
        assert [r["device"] for r in D.interrupted(net)] == ["r9"]
        assert D.held(net) == []
        assert sorted(os.listdir(folder)) == ["r1.lock", "r2.lock", "r9.lock"]
        assert D.indexed(net) is False

    def test_indexing_marks_exactly_its_records(self, net):
        folder = _plant(net, {"r9": LEFT, "r1": None, "r2": None})
        slug = os.path.basename(folder)
        assert slug in D.index_all()
        assert D.indexed(net) and os.listdir(os.path.join(folder, "holds")) == ["r9"]
        assert [r["device"] for r in D.interrupted(net)] == ["r9"]
        assert slug not in D.index_all(), "indexed twice"

    def test_an_acquire_indexes_it_first(self, net):
        folder = _plant(net, {"r9": LEFT, "r1": None})
        D.acquire(net, "r2", "deploy", "a@example.invalid")
        try:
            assert D.indexed(net)
            assert sorted(os.listdir(os.path.join(folder, "holds"))) == ["r2", "r9"]
        finally:
            D.release(net, "r2")
        assert [r["device"] for r in D.interrupted(net)] == ["r9"]

    def test_markers_that_cannot_be_listed_are_never_nothing_held(self, net):
        import shutil

        folder = _plant(net, {"r9": LEFT})
        D.index_all()
        shutil.rmtree(os.path.join(folder, "holds"))       # indexed, and its markers gone
        assert D.indexed(net)
        assert [r["device"] for r in D.interrupted(net)] == ["r9"]


class TestTheAppIndexesAtItsStart:
    def test_the_start_calls_index_all(self):
        with open(os.path.join(ROOT, "app.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_start_background_daemons")
        calls = [ast.unparse(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)]
        assert any(c.endswith("device_ops.index_all") for c in calls), calls
