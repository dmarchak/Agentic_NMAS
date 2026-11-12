"""C1262: Needs attention computed once for every tab and request asking for the same network.
Measured on the host 2026-11-03: the sidebar badge read 4,024 times in 31 h at p50 2.5 s and
p90 7.7 s, each open tab recomputing every source on every announcement.

C3166 (the operator's rule, 2026-11-12: no page load or badge poll waits on a computation) moved
that one computation off the request altogether: the background store
(modules/attention_store.py) computes, and every tab and request reads what it holds. These are
C1262's properties as the store holds them; the store's own (one recompute per burst, the
cadence, a fix clearing within one debounce) are tests/test_attention_store.py's. Asserted on
work (computations counted), never on time: the store's clock is the test's own.
"""

import threading

import pytest

from modules import attention as A
from modules import attention_store as S
from modules import invalidation as I


@pytest.fixture
def counted(monkeypatch):
    """The store as in production (nothing computed on a read), a clock the test moves, and
    one source, declared as the drift source, whose every computation is counted with the
    network it was computed for (read the way every source reads it, `_page_network`)."""
    calls, now, network = [], {"t": 1000.0}, {"name": "Lab"}

    def drift_source():
        calls.append(A._page_network())
        return A.source_result("drift", "Drift", read_at=now["t"], took_ms=0,
                               checked=f"computation {len(calls)}")
    monkeypatch.setattr(A, "SOURCES", (drift_source,))
    monkeypatch.setattr(S, "COMPUTE_ON_READ", False)
    monkeypatch.setattr(S, "_clock", lambda: now["t"])
    monkeypatch.setattr(S, "_network", lambda: network["name"])
    monkeypatch.setattr(S, "_current", lambda: "Lab")
    monkeypatch.setattr(S, "_head", lambda name: "head")
    monkeypatch.setattr(S, "_exists", lambda name: name in ("Lab", "Branch"))
    monkeypatch.setattr(I, "_emitter", lambda event, msg: None)
    S.clear()
    yield {"calls": calls, "now": now, "network": network, "get": lambda: S.read()}
    S.clear()


def test_a_burst_of_tabs_is_one_computation(counted):
    S.step()                                        # the background's one computation
    got = [counted["get"]() for _ in range(5)]      # five tabs read it
    assert counted["calls"] == ["Lab"] and all(g == got[0] for g in got)
    assert got[0]["sources"][0]["checked"] == "computation 1"


def test_an_announcement_recomputes_its_sources_once_after_the_debounce(counted):
    S.step()
    I.announce(["drift"], by="a test")
    counted["get"]()
    counted["get"]()
    assert len(counted["calls"]) == 1, "a read never computes"
    counted["now"]["t"] += S.DEBOUNCE_S
    S.step()
    assert len(counted["calls"]) == 2
    assert counted["get"]()["sources"][0]["checked"] == "computation 2"


def test_a_mutating_route_s_invalidation_counts_as_a_change(counted):
    """A mutating route's declared invalidation (no announcement) marks the sources its keys
    move, as an announcement does: the page's next value is computed after it."""
    import app as APP
    S.step()
    endpoint = next(e for e in sorted(I.mutating_endpoints(APP.app)) if "drift" in I.keys_for(e))
    with APP.app.test_request_context("/v2/", method="POST"):
        from flask import request
        request.url_rule = next(r for r in APP.app.url_map.iter_rules() if r.endpoint == endpoint)
        response = APP.app.make_response(("{}", 200, {"Content-Type": "application/json"}))
        APP.app.process_response(response)
    counted["now"]["t"] += S.DEBOUNCE_S
    S.step()
    assert len(counted["calls"]) == 2, endpoint


def test_each_network_is_its_own(counted):
    S.step()
    counted["network"]["name"] = "Branch"
    assert counted["get"]()["store"]["state"] == "reading", "its own value, not Lab's"
    S.step()
    counted["get"]()
    counted["get"]()
    assert counted["calls"] == ["Lab", "Branch"], "each computed for its own network"


def test_with_nothing_announced_it_stands_at_most_its_cadence(counted):
    """Nothing viewed and nothing alerting: the idle cadence, SLOW_S."""
    S.step()
    counted["now"]["t"] += S.SLOW_S - 0.5
    S.step()
    assert len(counted["calls"]) == 1
    counted["now"]["t"] += 1.0
    S.step()
    assert len(counted["calls"]) == 2


def test_each_caller_gets_its_own_copy(counted):
    S.step()
    a = counted["get"]()
    a["rows"].append("changed by one caller")
    assert counted["get"]()["rows"] == []


def test_readers_never_wait_for_a_computation(counted, monkeypatch):
    """The operator's rule reverses C1262's premise that the readers waited for the one
    computing: a computation in progress holds nobody; every read draws the held value at once,
    and the one computation lands after."""
    gate, started = threading.Event(), threading.Event()
    S.step()
    calls = counted["calls"]

    def slow():
        calls.append("slow")
        started.set()
        gate.wait(5)
        return A.source_result("drift", "Drift", read_at=0, took_ms=0, checked="the new value")
    slow.__name__ = "drift_source"
    monkeypatch.setattr(A, "SOURCES", (slow,))
    S.mark(["drift"])
    counted["now"]["t"] += S.DEBOUNCE_S
    worker = threading.Thread(target=S.step)
    worker.start()
    assert started.wait(5)
    got = [counted["get"]()["sources"][0]["checked"] for _ in range(4)]
    assert got == ["computation 1"] * 4, "each read drew the held value while it computed"
    gate.set()
    worker.join(5)
    assert calls == ["Lab", "slow"]
    assert counted["get"]()["sources"][0]["checked"] == "the new value"


def test_the_suite_computes_per_request_unless_a_test_says_otherwise():
    """conftest's `_needs_attention_computed_per_request`: every other test reads a fresh
    computation, as before C3166."""
    assert S.COMPUTE_ON_READ is True
