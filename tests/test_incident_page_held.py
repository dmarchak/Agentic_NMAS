"""The incident page built once per change (the redesign brief §6 step 3, 2026-11-18;
`incident_page.page`): while nothing is announced (`invalidation.generation` unchanged) and for
at most `HOLD_S`, a page is served from its last build; concurrent requests for one page cost one
build; every caller gets its own copy; a test session builds on every read. Counted by builds,
never by wall-clock (CLAUDE.md, "Performance tests assert on work or growth")."""

import threading

import pytest

from modules import incident_page


class _Builds(list):
    """The builds made, and the fake clock's reading (`now`)."""


@pytest.fixture
def builds(monkeypatch):
    got = _Builds()
    monkeypatch.setattr("modules.attention_store.COMPUTE_ON_READ", False)
    monkeypatch.setattr("modules.invalidation._generation", [7])
    now = [1000.0]
    # raising=False: on a tree without the hold these are set anyway, so the test's own body
    # is what fails there (red-green), never its setup.
    monkeypatch.setattr(incident_page, "_clock", lambda: now[0], raising=False)
    monkeypatch.setattr(incident_page, "_held", {}, raising=False)
    monkeypatch.setattr(incident_page, "_flights", {}, raising=False)

    def build(network, incident_id, attention=None):
        got.append((network, incident_id))
        return {"kind": "page", "id": incident_id, "fixit": {"n": len(got)}}

    monkeypatch.setattr(incident_page, "_timed", build, raising=False)
    got.now = now
    return got


def test_one_generation_is_one_build_and_each_caller_its_own_copy(builds):
    a = incident_page.page("Lab", "hi-000000000001")
    b = incident_page.page("Lab", "hi-000000000001")
    assert builds == [("Lab", "hi-000000000001")]
    assert a == b and a is not b and a["fixit"] is not b["fixit"]
    a["fixit"]["analysis"] = "added by the route"
    assert "analysis" not in incident_page.page("Lab", "hi-000000000001")["fixit"]


def test_an_announcement_builds_it_again(builds, monkeypatch):
    incident_page.page("Lab", "hi-000000000001")
    monkeypatch.setattr("modules.invalidation._generation", [8])
    assert incident_page.page("Lab", "hi-000000000001")["fixit"]["n"] == 2
    assert len(builds) == 2


def test_past_its_hold_it_is_built_again(builds):
    incident_page.page("Lab", "hi-000000000001")
    builds.now[0] += incident_page.HOLD_S - 0.5
    incident_page.page("Lab", "hi-000000000001")
    assert len(builds) == 1
    builds.now[0] += 1.0
    incident_page.page("Lab", "hi-000000000001")
    assert len(builds) == 2


def test_each_page_and_network_is_its_own(builds):
    incident_page.page("Lab", "hi-000000000001")
    incident_page.page("Lab", "hi-000000000002")
    incident_page.page("Other", "hi-000000000001")
    assert len(builds) == 3


def test_concurrent_requests_for_one_page_cost_one_build(builds, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def slow(network, incident_id, attention=None):
        builds.append((network, incident_id))
        started.set()
        release.wait(5)
        return {"kind": "page", "id": incident_id}

    monkeypatch.setattr(incident_page, "_timed", slow, raising=False)
    answers = []
    first = threading.Thread(target=lambda: answers.append(
        incident_page.page("Lab", "hi-000000000001")))
    first.start()
    assert started.wait(5)
    second = threading.Thread(target=lambda: answers.append(
        incident_page.page("Lab", "hi-000000000001")))
    second.start()
    release.set()
    first.join(5)
    second.join(5)
    assert len(builds) == 1 and len(answers) == 2 and answers[0] == answers[1]


def test_a_test_session_builds_on_every_read(builds, monkeypatch):
    monkeypatch.setattr("modules.attention_store.COMPUTE_ON_READ", True)
    incident_page.page("Lab", "hi-000000000001")
    incident_page.page("Lab", "hi-000000000001")
    assert len(builds) == 2


def test_the_held_pages_are_bounded(builds):
    for n in range(incident_page.HELD_MAX + 5):
        builds.now[0] += 0.001
        incident_page.page("Lab", "hi-%012d" % n)
    assert len(incident_page._held) == incident_page.HELD_MAX
    assert ("Lab", "hi-%012d" % 0) not in incident_page._held
