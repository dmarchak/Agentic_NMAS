"""The incidents list computed once at a time per network (the redesign brief §6, 2026-11-18;
`incidents_list.held`): a request that finds the list stale while it is being computed waits for
that computation and takes it. Every open Incidents page asks at once after an announcement;
counted by computations, never by wall-clock."""

import threading

import pytest

from modules import incidents_list


@pytest.fixture
def computed(monkeypatch):
    got = []
    monkeypatch.setattr("modules.attention_store.COMPUTE_ON_READ", False)
    monkeypatch.setattr("modules.invalidation._generation", [3])
    monkeypatch.setattr(incidents_list, "_held", {})
    monkeypatch.setattr(incidents_list, "_flights", {}, raising=False)
    return got


def test_concurrent_requests_for_a_stale_list_cost_one_computation(computed, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def rows(network):
        computed.append(network)
        started.set()
        release.wait(5)
        return {"rows": [{"id": "hi-000000000001"}], "folded": [], "unreadable": []}

    monkeypatch.setattr(incidents_list, "rows", rows)
    answers = []
    first = threading.Thread(target=lambda: answers.append(incidents_list.held("Lab")))
    first.start()
    assert started.wait(5)
    second = threading.Thread(target=lambda: answers.append(incidents_list.held("Lab")))
    second.start()
    release.set()
    first.join(5)
    second.join(5)
    assert computed == ["Lab"] and len(answers) == 2
    assert answers[0]["rows"] == answers[1]["rows"]


def test_each_network_computes_its_own(computed, monkeypatch):
    monkeypatch.setattr(incidents_list, "rows", lambda network: computed.append(network) or {
        "rows": [], "folded": [], "unreadable": []})
    incidents_list.held("Lab")
    incidents_list.held("Other")
    incidents_list.held("Lab")
    assert computed == ["Lab", "Other"]
