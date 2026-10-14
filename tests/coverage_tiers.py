"""Each test's run phase measured by tier, cheaply, on every push (C773; docs/TESTING.md, "Where
it runs").

A push's coverage had measured a context PER TEST (`--cov-context=test`) with branches, which
forces coverage's C tracer: the tests step went from about 5 to about 10 minutes a shard, nearly
all of it the tracer (measured on CI's runners, 2026-10-14: CTracer with lines only cost as much
as with contexts and branches; sys.monitoring cost about what no coverage did). sys.monitoring
measures no dynamic context, so the ratchet's question, which functions a UNIT test's run phase
reached, is answered here instead:

pytest-cov's one sys.monitoring instance runs all session, so a frame begun in a fixture (a
server thread's loop) has its line events. At each test's call the lines collected so far are
emptied in place and sys.monitoring's disabled events re-armed (a line already hit fires again);
at the call's end what was collected is that test's run phase. Setup and teardown are never
counted, as the per-test rule never counted them. When the test has ended its tier is known
(the counters tests/conftest.py's tier fixture reads: a browser call, a process of ours started)
and its lines join "unit" or "other". Each process writes them as the contexts `unit|run` and
`other|run` beside pytest-cov's own data, which keeps what ran before the first test (context
""). Measured on the same tree against the per-test contexts, the whole suite as CI's four
shards (2026-10-14): 0 of 4,263 functions differ, unit or every tier (2,243 and 2,247 of the
2,397 automation functions both ways). An earlier run differed on one support function, reached
by a unit test only after another test's leftovers on the same worker (C782), and on one
teardown-only function, until the teardown was cleared after each test.

On only when `NMAS_COVERAGE_TIERS=1` and coverage is measuring (CI's tests step); the per-test
drill-down and branch figures come from the nightly coverage run instead.
"""
import os
import sys

import pytest

_COV = []
_LINES = {"unit": {}, "other": {}}
_KEY = pytest.StashKey[dict]()


def _collector():
    return _COV[0]._collector if _COV else None


class _NoLock:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def pytest_collection_finish(session):
    import coverage
    cov = coverage.Coverage.current()
    if cov is None:
        return
    _COV.append(cov)
    cov._collector.flush_data()          # what ran before the first test: its own data, ""


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    from tests import network_guard
    from tests.browser import Browser
    guard = network_guard.spawn_guard()
    spawned, calls = guard.spawned_ours, Browser.calls
    item.stash[_KEY] = {}
    yield
    col = _collector()
    if col is not None:
        # The teardown's lines: never counted, and gone before pytest-cov saves its own data
        # at the session's end (its hook runs before this plugin's: measured, a teardown-only
        # function counted under "" until this cleared it here).
        col._clear_data()
    tier = ("browser" if Browser.calls > calls else
            "spawns" if guard.spawned_ours > spawned else "unit")
    into = _LINES["unit" if tier == "unit" else "other"]
    for f, lines in item.stash[_KEY].items():
        into.setdefault(f, set()).update(lines)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    col = _collector()
    if col is not None:
        col._clear_data()                # setup's lines: never counted
        sys.monitoring.restart_events()
    try:
        yield
    finally:
        if col is not None:
            with col.data_lock or _NoLock():
                item.stash[_KEY] = {f: set(s) for f, s in col.data.items() if s}
            col._clear_data()


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session):
    col = _collector()
    if col is None:
        return
    import coverage
    col._clear_data()                    # the last teardown's lines: never counted
    _COV[0].stop()                       # nothing after the last test is any test's
    out = coverage.CoverageData(basename=os.environ.get("COVERAGE_FILE", ".coverage") + ".tiers",
                                suffix=True)
    for label, by_file in _LINES.items():
        if by_file:
            out.set_context(f"{label}|run")
            out.add_lines({f: sorted(v) for f, v in by_file.items()})
    out.write()
