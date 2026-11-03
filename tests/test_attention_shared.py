"""C1262: Needs attention computed once for every tab and request asking for the same network,
until a change is announced (an announcement, or a mutating route's declared invalidation) or
`attention.SHARED_SECONDS` pass. Measured on the host 2026-11-03: the sidebar badge read 4,024
times in 31 h at p50 2.5 s and p90 7.7 s, each open tab recomputing every source on every
announcement. Asserted on work (computations counted), never on time.
"""

import threading

import pytest

from modules import attention as A
from modules import invalidation as I


@pytest.fixture
def counted(monkeypatch):
    """Sharing on, as in production, a clock the test moves, and every computation counted."""
    monkeypatch.setattr(A, "SHARED_SECONDS", 10.0)
    A._shared.clear()
    calls, now, network = [], {"t": 1000.0}, {"name": "Lab"}
    monkeypatch.setattr(A, "needs_attention",
                        lambda: calls.append(network["name"]) or {"rows": [len(calls)],
                                                                    "badge": {"n": len(calls)}})
    monkeypatch.setattr(A, "_page_network", lambda: network["name"])
    yield {"calls": calls, "now": now, "network": network,
           "get": lambda: A.needs_attention_shared(clock=lambda: now["t"])}
    A._shared.clear()


def test_a_burst_of_tabs_is_one_computation(counted):
    got = [counted["get"]() for _ in range(5)]
    assert counted["calls"] == ["Lab"] and all(g == got[0] for g in got)


def test_an_announcement_makes_the_next_read_compute_again(counted, monkeypatch):
    counted["get"]()
    monkeypatch.setattr(I, "_emitter", lambda event, msg: None)
    I.announce(["acknowledgements"], by="a test")
    counted["get"]()
    counted["get"]()
    assert len(counted["calls"]) == 2


def test_a_mutating_route_s_invalidation_counts_as_a_change(counted):
    """An acknowledgement's POST declares `acknowledgements` on its response (no announcement):
    the page's re-read after it must not be served the value from before."""
    import app as APP
    counted["get"]()
    before = I.generation()
    with APP.app.test_request_context("/attention/acknowledge", method="POST"):
        from flask import request
        endpoint = next(e for e in I.mutating_endpoints(APP.app) if I.keys_for(e))
        request.url_rule = next(r for r in APP.app.url_map.iter_rules() if r.endpoint == endpoint)
        response = APP.app.make_response(("{}", 200, {"Content-Type": "application/json"}))
        APP.app.process_response(response)
    assert I.generation() > before
    counted["get"]()
    assert len(counted["calls"]) == 2


def test_each_network_is_its_own(counted):
    counted["get"]()
    counted["network"]["name"] = "Branch"
    counted["get"]()
    counted["get"]()
    assert counted["calls"] == ["Lab", "Branch"]


def test_with_nothing_announced_it_stands_at_most_shared_seconds(counted):
    counted["get"]()
    counted["now"]["t"] += A.SHARED_SECONDS - 0.5
    counted["get"]()
    counted["now"]["t"] += 1.0
    counted["get"]()
    assert len(counted["calls"]) == 2


def test_each_caller_gets_its_own_copy(counted):
    a = counted["get"]()
    a["rows"].append("changed by one caller")
    assert counted["get"]()["rows"] == [1]


def test_concurrent_readers_wait_for_the_one_computing(counted, monkeypatch):
    gate, started = threading.Event(), threading.Event()
    calls = counted["calls"]

    def slow():
        calls.append("Lab")
        started.set()
        gate.wait(5)
        return {"rows": [], "badge": {}}
    monkeypatch.setattr(A, "needs_attention", slow)
    threads = [threading.Thread(target=counted["get"]) for _ in range(4)]
    threads[0].start()
    assert started.wait(5)
    for t in threads[1:]:
        t.start()
    gate.set()
    for t in threads:
        t.join(5)
    assert calls == ["Lab"], "the waiting readers computed again"


def test_the_suite_computes_per_request_unless_a_test_says_otherwise():
    """conftest's `_needs_attention_computed_per_request`: every other test reads a fresh
    computation, as before C1262."""
    assert A.SHARED_SECONDS == 0.0
