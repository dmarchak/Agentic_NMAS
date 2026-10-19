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
    (10.6, 4, 2, 1),       # the gate's four shards and two browsers, after the agents ended
    (30.0, 4, 2, 4),
    (21.6, 4, 2, 3),
    (1.0, 1, 0, 1),        # at least 1, however low
    (0.0, 4, 2, 1),
])
def test_the_formula(gib, runs, browsers, want):
    # *gib* in tenths, to the byte at or above it: int(4.4 * GIB) truncates to just under the
    # boundary it names.
    available = -(-int(round(gib * 10)) * GIB // 10)
    assert W.workers(available, runs, browsers) == want


def test_memavailable_is_read_from_the_file(tmp_path, monkeypatch):
    monkeypatch.setenv("NMAS_MEMINFO", _meminfo(tmp_path, 4.4))
    assert W.mem_available() == int(4.4 * 1024 * 1024) * 1024
    (tmp_path / "bad").write_text("MemTotal: 1 kB\n")
    with pytest.raises(RuntimeError, match="no MemAvailable"):
        W.mem_available(str(tmp_path / "bad"))


def test_the_helper_prints_the_count_and_its_words(tmp_path):
    env = dict(os.environ, NMAS_MEMINFO=_meminfo(tmp_path, 6.9))
    out = subprocess.run(["scripts/nmas-workers", "--cap", "2"], env=env, capture_output=True,
                         text=True, check=True).stdout.strip()
    assert out == "2"
    words = subprocess.run(["scripts/nmas-workers", "--runs", "4", "--browsers", "2",
                            "--explain"], env=env, capture_output=True, text=True,
                           check=True).stdout
    assert words.startswith("1 worker(s) per run: MemAvailable 6.9 GiB") and "/ 4))" in words


class TestTheGate:
    def test_each_shard_takes_its_share_and_its_bound_scales(self):
        gate = _load("nmas_gate_w", "scripts/nmas-gate")
        assert gate.suite_workers(int(30 * GIB))[0] == 4
        assert gate.suite_workers(int(10.6 * GIB))[0] == 1
        assert gate.suite_bound(4) == 740 and gate.suite_bound(1) == 2960
        cmd = gate.SUITE.format(py="P", shard="a", cov="D", n=1, bound=gate.suite_bound(1))
        assert " -n 1 " in cmd and "NMAS_TEST_TIMEOUT=2960 " in cmd

    def test_a_second_full_run_is_refused_naming_the_first(self, tmp_path):
        lock = str(tmp_path / "full-suite.lock")
        first = W.hold_full("nmas-gate (pid 1)", lock)
        assert not isinstance(first, str)
        second = W.hold_full("nmas-gate (pid 2)", lock)
        assert isinstance(second, str) and "nmas-gate (pid 1)" in second
        first.close()
        third = W.hold_full("nmas-gate (pid 3)", lock)
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

    def test_a_full_run_refuses_while_another_holds_the_lock(self, tmp_path):
        lock = str(tmp_path / "full.lock")
        held = W.hold_full("nmas-gate (pid 7)", lock)
        try:
            r = self._run(tmp_path, 30.0, "-q", "-p", "no:cacheprovider", "--co", lock=lock)
        finally:
            held.close()
        assert r.returncode == 75, (r.returncode, r.stderr[-800:])
        assert "another full-suite run holds" in r.stderr and "nmas-gate (pid 7)" in r.stderr
