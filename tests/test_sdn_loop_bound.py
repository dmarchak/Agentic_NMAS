"""The SDN loop's stop condition besides Stop (Lab 9 B3; board F; the handout's ground rule:
never leave a monitoring loop running unattended; `modules/sdn/loop.py`): a run-for bound, 20
minutes by default and an hour at most, and a pass cap; whichever comes first ends the loop,
and its log says which, who and how many passes. No thread sleeps here: a fake clock moves
only when a pass runs or the schedule waits.

- the bound ends the schedule at its time, the cap at its count, a Stop at once, each named;
- a wait never runs past the bound;
- `start` refuses a bound under a minute or over an hour, saying both limits; the five-minute
  demonstration is one of the offered bounds, inside the default;
- a loop that ends itself records ``stop`` by the loop's own bound, with its reason and passes,
  and its status says when it will stop while it runs;
- SDN › Responses' Start sends Run for, and the route starts the loop with it.
"""
import threading

import pytest

from modules.sdn import loop as LP
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

NET = "Default"


class _Event:
    """A stop event a fake clock drives: `wait` moves the clock by what it waits."""

    def __init__(self, clock, stop_after=None):
        self.clock, self.waits, self.stop_after, self.passes = clock, [], stop_after, 0
        self._set = False

    def is_set(self):
        return self._set

    def wait(self, s):
        self.waits.append(round(s, 3))
        self.clock[0] += s
        assert len(self.waits) < 1000, "the schedule ran on past every bound it was given"


def _run(until=None, cap=None, took=2.0, interval=10.0, stop_after=None):
    clock = [0.0]
    ev = _Event(clock, stop_after)
    counted = {"n": 0}

    def one():
        assert counted["n"] < 1000, "the schedule ran on past every bound it was given"
        clock[0] += took
        if stop_after is not None and counted["n"] + 1 >= stop_after:
            ev._set = True
    reason = LP.schedule(NET, interval, ev, one, clock=lambda: clock[0], wall=lambda: 0.0,
                         until=until, passes_cap=cap, counted=counted)
    return reason, counted["n"], ev.waits, clock[0]


def test_the_bound_ends_the_schedule_at_its_time(networks):  # noqa: F811
    reason, passes, waits, at = _run(until=30.0)
    assert (reason, passes) == ("run_for", 3) and at == 30.0
    assert waits == [8.0, 8.0, 8.0], "the last wait stops at the bound, never past it"


def test_a_wait_never_runs_past_the_bound(networks):  # noqa: F811
    reason, passes, waits, at = _run(until=25.0)
    assert reason == "run_for" and passes == 3 and waits == [8.0, 8.0, 3.0] and at == 25.0


def test_the_pass_cap_ends_it_before_its_bound(networks):  # noqa: F811
    reason, passes, _waits, _at = _run(until=1000.0, cap=4)
    assert (reason, passes) == ("pass_cap", 4)


def test_stop_ends_it_at_once_and_says_stop(networks):  # noqa: F811
    reason, passes, _waits, _at = _run(until=1000.0, stop_after=2)
    assert (reason, passes) == ("stop", 2)


def test_the_cap_is_the_bound_s_passes_and_one_more():
    assert LP.max_passes(20 * 60, 10) == 121 and LP.max_passes(300, 7) == 44


@pytest.mark.parametrize("run_for", [30, 3601, True, "600"])
def test_start_refuses_a_bound_out_of_bounds(networks, run_for):  # noqa: F811
    with pytest.raises(ValueError, match="the loop runs for 1 to 60 minutes "
                                         r"\(a loop is never left running unattended\)"):
        LP.start(NET, actor="op@example.com", run_for=run_for)
    assert not LP.status(NET)["running"]


def test_the_five_minute_demonstration_is_offered_inside_the_default():
    assert 300 in LP.RUN_FOR_CHOICES and LP.DEFAULT_RUN_FOR_S >= 300
    assert all(LP.MIN_RUN_FOR_S <= c <= LP.MAX_RUN_FOR_S for c in LP.RUN_FOR_CHOICES)


def _ended_by(monkeypatch, reason):
    from modules.sdn import capability
    monkeypatch.setattr(capability, "read", lambda network, **kw: {
        "ok": True, "error": "", "controllers": []})

    def schedule(network, interval, stop_event, one_pass, *, counted, **kw):
        counted["n"] = 7
        return reason
    monkeypatch.setattr(LP, "schedule", schedule)
    LP.start(NET, actor="op@example.com", interval=10, run_for=300)
    LP._jobs[NET]["thread"].join(10)
    return LP.status(NET)


@pytest.mark.parametrize("reason,words", [
    ("run_for", "stopped by itself: it ran for its bound of 5 minutes (until "),
    ("pass_cap", "stopped by itself: it reached its pass cap of 31 passes (its 5 minutes at "
                 "every 10 s, and one more) before its bound")])
def test_a_loop_that_ends_itself_records_why_by_its_bound(networks, monkeypatch,  # noqa: F811
                                                           reason, words):
    got = _ended_by(monkeypatch, reason)
    stop = got["stopped"]
    assert not got["running"] and stop["by"] == LP.BOUND_ACTOR
    assert (stop["reason"], stop["passes"]) == (reason, 7)
    assert stop["words"].startswith(words)
    start = [r for r in LP.log_lines(NET)["rows"] if r["step"] == "start"][-1]
    assert start["words"].startswith("started by op@example.com, every 10 s, for at most 5 "
                                     "minutes (until ")
    assert start["max_passes"] == 31 and start["run_for_s"] == 300


def test_a_schedule_a_person_stopped_records_no_stop_of_the_bound_s(networks,  # noqa: F811
                                                                     monkeypatch):
    _ended_by(monkeypatch, "stop")
    assert [r for r in LP.log_lines(NET)["rows"] if r["step"] == "stop"] == [], \
        "a person's Stop writes its own line (`stop`); the bound writes none"


def test_its_status_says_when_it_stops_while_it_runs(networks, monkeypatch):  # noqa: F811
    from modules.sdn import capability
    monkeypatch.setattr(capability, "read", lambda network, **kw: {
        "ok": True, "error": "", "controllers": []})
    gate = threading.Event()
    monkeypatch.setattr(LP, "run_pass", lambda network, **kw: gate.wait(5))
    LP.start(NET, actor="op@example.com", interval=5, run_for=600)
    try:
        got = LP.status(NET)
        assert got["running"] and got["run_for_s"] == 600 and got["max_passes"] == 121
        assert got["until"] > got["since"]
    finally:
        LP.stop(NET, actor="op@example.com")
        gate.set()
        LP._jobs[NET]["thread"].join(10)


@pytest.fixture
def client(networks):  # noqa: F811
    import app as A
    return A.app.test_client()


def test_the_route_starts_the_loop_for_the_minutes_run_for_names(client, monkeypatch):
    # The capability matrix's read is the page's, never this test's (no switch here); it is
    # patched in the body, so where the matrix is absent the body fails rather than its setup.
    from modules.sdn import capability
    monkeypatch.setattr(capability, "read", lambda network, **kw: {
        "ok": True, "error": "", "controllers": []})
    gate = threading.Event()
    monkeypatch.setattr(LP, "run_pass", lambda network, **kw: gate.wait(5))
    try:
        r = client.post("/v2/sdn/loop", data={"list": NET, "run": "start", "interval": "10",
                                               "run_for": "5"})
        assert r.status_code == 200 and LP.status(NET)["run_for_s"] == 300
    finally:
        client.post("/v2/sdn/loop", data={"list": NET, "run": "stop"})
        gate.set()
        LP._jobs[NET]["thread"].join(10)
    r = client.post("/v2/sdn/loop", data={"list": NET, "run": "start", "interval": "10",
                                           "run_for": "90"})
    assert "the loop runs for 1 to 60 minutes" in r.get_data(as_text=True)
    assert not LP.status(NET)["running"]
