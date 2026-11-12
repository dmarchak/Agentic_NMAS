"""Test workers from the memory available now, and one full-suite run at a time (the operator,
2026-10-19: the laptop's RAM ran out with the gate's four shards at -n 4 and two agents' runs
beside them; swap 8 of 8 GiB, 5.2 GiB available). `scripts/nmas-workers` holds the formula and
the lock; the gate (`scripts/nmas-gate`) and `scripts/nmas-test` use them."""

import importlib.machinery
import importlib.util
import os
import subprocess

import pytest

GIB = 1024 ** 3


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, path)
    spec = importlib.util.spec_from_loader(name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


W = _load("nmas_workers", "scripts/nmas-workers")


def ENOUGH():  # noqa: N802 (a reading, named as the constant it stands for)
    """A MemAvailable reading above every floor: a test of the lock is not a test of memory."""
    return 30 * GIB


def _gate_cgroup(tmp_path, pid: int, cap, current: int):
    """``(proc root, cgroup root)`` holding pid *pid*'s cgroup and its scope's memory files, as
    the kernel lays them out (cgroup v2: "0::/<path>")."""
    proc = tmp_path / "proc" / str(pid)
    proc.mkdir(parents=True, exist_ok=True)
    (proc / "cgroup").write_text("0::/user.slice/app.slice/nmas-gate-1.scope\n")
    scope = tmp_path / "cg" / "user.slice" / "app.slice" / "nmas-gate-1.scope"
    scope.mkdir(parents=True, exist_ok=True)
    (scope / "memory.max").write_text(f"{cap}\n")
    (scope / "memory.current").write_text(f"{current}\n")
    return str(tmp_path / "proc"), str(tmp_path / "cg")


def _meminfo(tmp_path, gib: float) -> str:
    """A real /proc/meminfo's shape (Ubuntu 24.04), its MemAvailable set to *gib*."""
    p = tmp_path / "meminfo"
    p.write_text("MemTotal:       31743208 kB\nMemFree:         3638396 kB\n"
                 f"MemAvailable:   {int(gib * 1024 * 1024)} kB\nBuffers:          123456 kB\n")
    return str(p)


@pytest.mark.parametrize("gib,runs,browsers,want", [
    # min(4, floor((A - 2 - browsers x 1.2) / 1.2 / runs)), at least 1 (the operator's formula)
    (3.8, 1, 0, 1),        # 2026-10-19 21:1x UTC, two agents' runs beside it
    (4.4, 1, 0, 2),
    (6.7, 1, 0, 3),
    (6.9, 1, 0, 4),
    (30.0, 1, 0, 4),       # never more than CI's four
    (5.6, 1, 1, 2),        # a headless browser counts as one worker's memory
    # Several runs at once are the gate's suite, sized by its measured peak since 2026-11-12
    # (the operator: "A gate alone keeps 2 workers at 16 GiB free"): 16.5 GiB at 2 workers (the
    # capped gates' cgroup peak, 16.45 on 2026-11-12 12:17 UTC) plus 2 GiB, so 2 from 18.5 GiB
    # (3 and 4 projected: 27.6 and 36.7 GiB); the 2026-10-19 formula gave 3 at 21.6 GiB and 4
    # at 30 GiB.
    (10.6, 4, 2, 1),       # the gate's four shards and two browsers, after the agents ended
    (30.0, 4, 2, 3),
    (36.7, 4, 2, 4),
    (21.6, 4, 2, 2),
    (18.5, 5, 3, 2),
    (18.4, 5, 3, 1),
    (1.0, 1, 0, 1),        # at least 1, however low
    (0.0, 4, 2, 1),
])
def test_the_formula(gib, runs, browsers, want):
    # *gib* in tenths, to the byte at or above it: int(4.4 * GIB) truncates to just under the
    # boundary it names.
    available = -(-int(round(gib * 10)) * GIB // 10)
    assert W.workers(available, runs, browsers, beside=False) == want


class TestABuildBesideTheGate:
    """The operator, 2026-11-12: "when a build is testing, the gate runs with 1 worker
    (measured 7.4 GiB peak, ~17 min) under a 9 GiB cap, and the build's aimed tests run beside
    it under a 3 GiB cap, never browser tests"."""

    def test_the_gate_takes_one_worker_while_a_capped_run_tests(self):
        assert W.workers(30 * GIB, 5, 3, beside=True) == 1
        assert W.workers(37 * GIB, 5, 3, beside=False) == 4
        assert "capped run is testing beside" in W.explain(30 * GIB, 5, 3, beside=True)

    def test_a_held_beside_lock_is_seen_and_an_absent_one_is_not_made(self, tmp_path):
        import fcntl
        lock = tmp_path / "beside.lock"
        assert W.beside_held(str(lock)) is False and not lock.exists()
        lock.write_text("")
        assert W.beside_held(str(lock)) is False
        with open(lock, encoding="utf-8") as held:
            fcntl.flock(held, fcntl.LOCK_SH)
            assert W.beside_held(str(lock)) is True
        assert W.beside_held(str(lock)) is False

    def test_the_gate_s_lock_records_whether_a_capped_run_was_testing(self, tmp_path,
                                                                     monkeypatch):
        import fcntl
        lock = tmp_path / "beside.lock"
        lock.write_text("")
        monkeypatch.setattr(W, "BESIDE_LOCK", str(lock))
        fh = W.hold_full("nmas-gate (pid 1)", str(tmp_path / "full.lock"), mem=ENOUGH)
        assert (tmp_path / "full.lock").read_text() == "nmas-gate (pid 1)\nbeside=no\n"
        fh.close()
        with open(lock, encoding="utf-8") as held:
            fcntl.flock(held, fcntl.LOCK_SH)
            fh = W.hold_full("nmas-gate (pid 2)", str(tmp_path / "full.lock"), mem=ENOUGH)
            assert (tmp_path / "full.lock").read_text() == "nmas-gate (pid 2)\nbeside=yes\n"
            fh.close()

    def _ran(self, tmp_path, monkeypatch, cmd, gate_record=None, free_gib=30.0,
             gate_cap=9 * GIB, gate_using=4 * GIB):
        """``(exit code, the command run or None, whether the beside lock was held in it)``.
        A gate, when *gate_record* is given, holds the full-suite lock as pid 9, its scope
        capped at *gate_cap* (``"max"``: uncapped) and using *gate_using*."""
        monkeypatch.setenv("PATH", "/usr/bin:/bin")
        full = tmp_path / "full.lock"
        lock = str(tmp_path / "beside.lock")
        proc, cg = _gate_cgroup(tmp_path, 9, gate_cap, gate_using)
        seen = {}

        def run(argv):
            seen["argv"], seen["held"] = argv, W.beside_held(lock)
            return 0

        gate = None
        if gate_record is not None:
            gate = W.hold_full("nmas-gate (pid 9)", str(full), mem=ENOUGH)
            full.write_text(gate_record)
        try:
            rc = W.beside(cmd, run=run, lock_path=lock, full_path=str(full),
                          mem=lambda: int(free_gib * GIB), proc_root=proc, cgroup_root=cg)
        finally:
            if gate is not None:
                gate.close()
        return rc, seen.get("argv"), seen.get("held")

    def test_it_runs_the_command_under_the_cap_holding_the_lock(self, tmp_path, monkeypatch):
        rc, argv, held = self._ran(tmp_path, monkeypatch, ["scripts/nmas-test", "-n", "1",
                                                           "tests/test_nmas_workers.py"])
        assert rc == 0 and held is True
        assert argv[:4] == ["systemd-run", "--user", "--scope", "-q"]
        assert "MemoryMax=3G" in argv and "MemorySwapMax=0" in argv
        assert argv[argv.index("--") + 1:] == ["scripts/nmas-test", "-n", "1",
                                               "tests/test_nmas_workers.py"]

    def test_a_browser_run_is_refused(self, tmp_path, monkeypatch, capsys):
        rc, argv, _held = self._ran(tmp_path, monkeypatch,
                                    ["python", "-m", "pytest", "tests/test_v2_layout_in_a_browser.py"])
        assert rc == 2 and argv is None
        assert "'browser'" in capsys.readouterr().err

    def test_it_joins_only_a_gate_sized_with_it(self, tmp_path, monkeypatch, capsys):
        rc, argv, _held = self._ran(tmp_path, monkeypatch, ["scripts/nmas-test", "x"],
                                    gate_record="nmas-gate (pid 9)\nbeside=no\n")
        assert rc == 2 and argv is None
        assert "nmas-gate (pid 9) is running, sized with no capped run" in capsys.readouterr().err
        rc, argv, _held = self._ran(tmp_path, monkeypatch, ["scripts/nmas-test", "x"],
                                    gate_record="nmas-gate (pid 9)\nbeside=yes\n")
        assert rc == 0 and argv is not None


class TestTheFloors:
    """The operator, 2026-11-12: "A gate refuses to start (waits, printing why) under
    GATE_PEAK[1] + GATE_MARGIN (9.4 GiB) free; a gate with a beside run starts only at 14 GiB
    free or more; --beside refuses to start a run that would leave less than 3 GiB free beside
    the gate's cap"."""

    def _hold(self, tmp_path, readings, beside=False, bound_s=None):
        """Take the lock with MemAvailable reading *readings* in turn (GiB): ``(the result,
        the wait lines said, the seconds slept)``."""
        it = iter(readings)
        said, slept = [], []
        got = W.hold_full("nmas-gate (pid 3)", str(tmp_path / "full.lock"),
                          mem=lambda: int(next(it) * GIB), beside_now=lambda: beside,
                          sleep=slept.append, bound_s=bound_s, say=said.append)
        return got, said, slept

    def test_a_gate_waits_under_9_4_gib_saying_why_then_starts(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NMAS_GATE_SUITE", raising=False)
        got, said, slept = self._hold(tmp_path, [9.3, 9.4])
        assert not isinstance(got, str)
        got.close()
        assert slept == [W.WAIT_EVERY_S] and len(said) == 1
        assert "a gate starts at 9.4 GiB free" in said[0] and "9.3 GiB is free" in said[0]

    def test_a_gate_that_never_gets_the_memory_refuses_naming_it(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NMAS_GATE_SUITE", raising=False)
        got, said, slept = self._hold(tmp_path, [9.0] * 10, bound_s=60)
        assert isinstance(got, str) and got.startswith("waited 60 s for memory")
        assert "a gate starts at 9.4 GiB free" in got and len(slept) == 2

    def test_a_gate_beside_a_capped_run_waits_under_14_gib(self, tmp_path, monkeypatch):
        monkeypatch.delenv("NMAS_GATE_SUITE", raising=False)
        got, said, _slept = self._hold(tmp_path, [13.9, 14.0], beside=True)
        assert not isinstance(got, str)
        got.close()
        assert len(said) == 1 and "a gate beside it starts at 14.0 GiB free" in said[0]
        alone, said, _slept = self._hold(tmp_path, [13.9], beside=False)
        assert not isinstance(alone, str) and said == []
        alone.close()

    def test_a_stand_in_run_starts_no_suite_and_waits_for_nothing(self, tmp_path,
                                                                  monkeypatch):
        monkeypatch.setenv("NMAS_GATE_SUITE", "echo '12 passed in 1.00s'; exit 0")
        got, said, slept = self._hold(tmp_path, [1.0])
        assert not isinstance(got, str) and said == [] and slept == []
        got.close()

    def test_a_stand_in_that_runs_tests_meets_the_floor(self, tmp_path, monkeypatch):
        """The operator, 2026-11-12: "the exemption is decided by the run starting no suite,
        not by a flag a real gate could set"."""
        monkeypatch.setenv("NMAS_GATE_SUITE", "python -m pytest tests -n 2")
        got, said, _slept = self._hold(tmp_path, [9.0, 9.5])
        assert not isinstance(got, str) and len(said) == 1
        got.close()
        assert W.starts_a_suite(None) and W.starts_a_suite("scripts/nmas-test -n 2")
        assert not W.starts_a_suite("pwd > x; git write-tree > y; echo '1 passed'; exit 0")


class TestCISizingIsUnchanged:
    """The operator, 2026-11-12: "The measured peaks and caps apply to the laptop gate only; CI
    keeps the sizing it had before tonight … add a test that CI's sizing is unchanged". CI runs
    `scripts/nmas-test -n auto`, which asks `nmas-workers --browsers B --cap 4` (one run). The
    expectation is the 2026-10-19 formula written out here, independent of the code under test;
    the gate's measured peaks, its ceiling and a capped run beside it never reach it."""

    @staticmethod
    def formula(gib_tenths: int, browsers: int, cap: int = 4) -> int:
        # min(4, floor((A - 2 - browsers x 1.2) / 1.2)), at least 1, in tenths of a GiB.
        per = (gib_tenths - 20 - browsers * 12) // 12
        return max(1, min(cap, 4, per))

    def test_one_run_is_sized_as_before_at_every_memory(self, monkeypatch):
        monkeypatch.setenv("NMAS_GATE_CEILING", "1")             # the laptop's: no effect here
        for tenths in range(0, 321):                             # 0 to 32 GiB
            available = -(-tenths * GIB // 10)
            for browsers in (0, 1, 2, 3):
                for beside in (False, True):
                    assert W.workers(available, 1, browsers, beside=beside) == \
                        self.formula(tenths, browsers), (tenths / 10, browsers, beside)

    @pytest.mark.parametrize("gib,browsers,want", [(14.5, 0, 4), (14.5, 3, 4), (10.0, 3, 3),
                                                   (6.9, 1, 3), (4.5, 0, 2)])
    def test_ci_s_own_call_gives_what_it_did(self, tmp_path, gib, browsers, want):
        env = dict(os.environ, NMAS_MEMINFO=_meminfo(tmp_path, gib), NMAS_GATE_CEILING="1",
                   NMAS_BESIDE_LOCK=str(tmp_path / "beside.lock"))
        out = subprocess.run(["scripts/nmas-workers", "--browsers", str(browsers), "--cap", "4"],
                             env=env, capture_output=True, text=True, check=True).stdout.strip()
        assert out == str(want) == str(self.formula(int(round(gib * 10)), browsers))


class TestTheLaptopCeiling:
    """The operator, 2026-11-12: "on this laptop, the gate runs at most 2 workers until a
    3-worker gate has been measured here … The cap always matches the worker count's measured
    peak + 1 GiB"."""

    def test_the_laptop_ceiling_holds_at_30_gib_free(self, monkeypatch):
        monkeypatch.setenv("NMAS_GATE_CEILING", "2")
        assert W.workers(30 * GIB, 5, 3, beside=False) == 2
        assert W.gate_cap(30 * GIB, False) == (2, W.GATE_PEAK[2] + GIB)
        monkeypatch.delenv("NMAS_GATE_CEILING")
        assert W.workers(37 * GIB, 5, 3, beside=False) == 4     # CI's, with no ceiling set

    def test_the_cap_is_the_worker_count_s_peak_plus_1_gib(self, monkeypatch):
        """A cap only (MemoryMax), the worker count's measured peak + 1 GiB; 1 worker 9.5 GiB
        until a capped 1-worker gate measures it (the operator, 2026-11-12)."""
        monkeypatch.setenv("NMAS_GATE_CEILING", "2")
        n, cap = W.gate_cap(30 * GIB, True)                    # a capped run testing beside
        assert (n, round(cap / GIB, 1)) == (1, 9.5)
        n, cap = W.gate_cap(int(16.4 * GIB), False)
        assert (n, round(cap / GIB, 1)) == (1, 9.5)
        n, cap = W.gate_cap(int(18.5 * GIB) + 1, False)
        assert (n, round(cap / GIB, 1)) == (2, 17.5)

    def test_the_helper_prints_the_count_and_the_cap(self, tmp_path):
        env = dict(os.environ, NMAS_MEMINFO=_meminfo(tmp_path, 30.0), NMAS_GATE_CEILING="2",
                   NMAS_BESIDE_LOCK=str(tmp_path / "beside.lock"))
        out = subprocess.run(["scripts/nmas-workers", "--gate-cap"], env=env,
                             capture_output=True, text=True, check=True).stdout.split()
        assert out == ["2", str(W.GATE_PEAK[2] + GIB)]

    def test_a_capped_run_leaving_under_3_gib_is_refused(self, tmp_path, monkeypatch, capsys):
        # No gate: 3 GiB its cap, 3 GiB left.
        ran = TestABuildBesideTheGate()._ran
        rc, argv, _ = ran(tmp_path / "a", monkeypatch, ["scripts/nmas-test", "x"], free_gib=5.9)
        assert rc == 2 and argv is None and "under the 3 GiB floor" in capsys.readouterr().err
        rc, argv, _ = ran(tmp_path / "b", monkeypatch, ["scripts/nmas-test", "x"], free_gib=6.0)
        assert rc == 0 and argv is not None

    def test_the_gate_s_room_to_grow_counts(self, tmp_path, monkeypatch, capsys):
        # A 1-worker gate capped at 9 GiB using 4: 5 GiB more it may take, then 3 for the run.
        ran = TestABuildBesideTheGate()._ran
        rec = "nmas-gate (pid 9)\nbeside=yes\n"
        rc, argv, _ = ran(tmp_path / "a", monkeypatch, ["scripts/nmas-test", "x"],
                          gate_record=rec, free_gib=10.9)
        err = capsys.readouterr().err
        assert rc == 2 and argv is None and "room to grow 5.0 GiB" in err
        rc, argv, _ = ran(tmp_path / "b", monkeypatch, ["scripts/nmas-test", "x"],
                          gate_record=rec, free_gib=11.0)
        assert rc == 0 and argv is not None

    def test_an_uncapped_gate_is_never_joined(self, tmp_path, monkeypatch, capsys):
        ran = TestABuildBesideTheGate()._ran
        rc, argv, _ = ran(tmp_path, monkeypatch, ["scripts/nmas-test", "x"],
                          gate_record="nmas-gate (pid 9)\nbeside=yes\n", gate_cap="max")
        assert rc == 2 and argv is None and "no memory cap" in capsys.readouterr().err


def test_memavailable_is_read_from_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("NMAS_MEMINFO", _meminfo(tmp_path, 4.4))
    assert W.mem_available() == int(4.4 * 1024 * 1024) * 1024
    (tmp_path / "bad").write_text("MemTotal: 1 kB\n")
    with pytest.raises(RuntimeError, match="no MemAvailable"):
        W.mem_available(str(tmp_path / "bad"))


def test_the_helper_prints_the_count_and_its_words(tmp_path):
    env = dict(os.environ, NMAS_MEMINFO=_meminfo(tmp_path, 6.9),
               NMAS_BESIDE_LOCK=str(tmp_path / "beside.lock"))
    out = subprocess.run(["scripts/nmas-workers", "--cap", "2"], env=env, capture_output=True,
                         text=True, check=True).stdout.strip()
    assert out == "2"
    words = subprocess.run(["scripts/nmas-workers", "--browsers", "2", "--explain"], env=env,
                           capture_output=True, text=True, check=True).stdout
    assert words.startswith("2 worker(s) per run: MemAvailable 6.9 GiB") and "/ 1))" in words
    # Several runs: the gate's suite, by its measured peak (2026-11-12).
    words = subprocess.run(["scripts/nmas-workers", "--runs", "4", "--browsers", "2",
                            "--explain"], env=env, capture_output=True, text=True,
                           check=True).stdout
    assert words.startswith("1 worker(s) per run: MemAvailable 6.9 GiB, the gate's peaks "
                            "1 worker(s) 7.4 GiB measured, 2 worker(s) 16.5 GiB measured, "
                            "3 worker(s) 25.6 GiB projected, 4 worker(s) 34.7 GiB projected, "
                            "each plus 2 GiB")


class TestTheGate:
    def test_each_shard_takes_its_share_and_its_bound_scales(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NMAS_BESIDE_LOCK", str(tmp_path / "beside.lock"))
        gate = _load("nmas_gate_w", "scripts/nmas-gate")
        assert gate.suite_workers(int(37 * GIB))[0] == 4
        assert gate.suite_workers(int(10.6 * GIB))[0] == 1
        assert gate.suite_bound(4) == 740 and gate.suite_bound(1) == 2960
        cmd = gate.SUITE.format(py="P", shard="a", cov="D", n=1, bound=gate.suite_bound(1),
                                req=gate.browser_required("a"))
        assert " -n 1 " in cmd and "NMAS_TEST_TIMEOUT=2960 " in cmd

    def test_a_second_full_run_is_refused_naming_the_first(self, tmp_path):
        lock = str(tmp_path / "full-suite.lock")
        first = W.hold_full("nmas-gate (pid 1)", lock, mem=ENOUGH)
        assert not isinstance(first, str)
        second = W.hold_full("nmas-gate (pid 2)", lock, mem=ENOUGH)
        assert isinstance(second, str) and "nmas-gate (pid 1)" in second
        first.close()
        third = W.hold_full("nmas-gate (pid 3)", lock, mem=ENOUGH)
        assert not isinstance(third, str)
        third.close()


class TestNmasTest:
    """scripts/nmas-test lowers a -n the memory does not allow, saying so, and a run naming no
    test file is the full suite, which waits for no one: it refuses while another holds the
    lock. Each run here only collects."""

    def _run(self, tmp_path, gib, *args, lock=None):
        env = dict(os.environ, NMAS_MEMINFO=_meminfo(tmp_path, gib),
                   NMAS_FULL_LOCK=lock or str(tmp_path / "full.lock"), NMAS_TEST_TIMEOUT="120")
        return subprocess.run(["scripts/nmas-test", *args], env=env, capture_output=True,
                              text=True, timeout=180)

    def test_a_n_beyond_the_memory_is_lowered_and_said(self, tmp_path):
        # A real run of one test, so xdist says how many workers it started: words that say
        # "lowered" over a run still at -n 4 would pass a check of the words alone.
        r = self._run(tmp_path, 3.8, "-n", "4", "-p", "no:cacheprovider",
                      "tests/test_nmas_workers.py::test_memavailable_is_read_from_the_file")
        assert "nmas-test: -n 4 lowered to 1: 1 worker(s) per run: MemAvailable 3.8 GiB" \
            in r.stderr, r.stderr[-800:]
        assert "created: 1/1 worker" in r.stdout and "1 passed" in r.stdout, r.stdout[-800:]
        r = self._run(tmp_path, 30.0, "-n", "2", "-q", "-p", "no:cacheprovider", "--co",
                      "tests/test_nmas_workers.py")
        assert "lowered" not in r.stderr, "a -n the memory allows is kept"

    def test_a_n_0_stays_one_process(self, tmp_path):
        """C2355: `-n 0` read as no cap gave 4 workers ("created: 4/4 workers", 2026-11-03).
        A real run of one test, so xdist's own words say whether it distributed."""
        r = self._run(tmp_path, 30.0, "-n", "0", "-p", "no:cacheprovider",
                      "tests/test_nmas_workers.py::test_memavailable_is_read_from_the_file")
        assert "1 passed" in r.stdout, r.stdout[-800:]
        assert "created:" not in r.stdout and " workers [" not in r.stdout, r.stdout[-800:]
        assert "lowered" not in r.stderr, r.stderr[-800:]

    def test_a_full_run_refuses_while_another_holds_the_lock(self, tmp_path):
        lock = str(tmp_path / "full.lock")
        held = W.hold_full("nmas-gate (pid 7)", lock, mem=ENOUGH)
        try:
            r = self._run(tmp_path, 30.0, "-q", "-p", "no:cacheprovider", "--co", lock=lock)
        finally:
            held.close()
        assert r.returncode == 75, (r.returncode, r.stderr[-800:])
        assert "another full-suite run holds" in r.stderr and "nmas-gate (pid 7)" in r.stderr
