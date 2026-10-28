"""The SDN loop announces what its pass changed (`modules/sdn/loop.py` `run_pass`; C1868,
C2003): every screen shows the new state.

- A pass whose observation moved the alert history (``changed``) announces ``alerts``, so an
  open Alerts tab redraws on a new detection.
- A pass that changed a response (a detection fired and was proposed, one went no longer
  active, an expired meter removed) announces ``sdn``, so SDN › Responses draws the new card
  without waiting for the SDN reader's next announcement.
- A pass that only logged announces nothing: its lines reach the page at the reader's own
  announcement, so the region is not redrawn every pass (C2001).
- Announced as the loop's job, never as a reader; a failed announcement is said in the pass's
  answer and logged, never raised, and the pass's work stands.
"""
import pytest

from modules import invalidation as I
from modules.sdn import closed_loop as CL
from modules.sdn import loop as LP
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_modes_loop import NET, T0, collected, observed

NO_DRIVER = {"ok": False, "error": "unused"}


@pytest.fixture
def heard(networks, monkeypatch):  # noqa: F811 - the fixture, used
    sent = []
    monkeypatch.setattr(I, "_emitter", lambda event, msg: sent.append(msg))
    monkeypatch.setattr(CL, "respond_to_threat", lambda *a, **k: {})
    return sent


def _pass(observe, at=T0):
    return LP.run_pass(NET, collect=collected, observe=observe, now=lambda: at,
                       driver=lambda n, c: NO_DRIVER)


def _with_changed(observe, changed):
    return lambda network, got: dict(observe(network, got), changed=changed)


def test_a_new_detection_announces_alerts_and_sdn_as_the_loop_s_job(heard):
    out = _pass(_with_changed(observed(fired=["k1"]), True))
    assert out["ok"] and out["proposed"]
    (msg,) = heard
    assert msg["keys"] == ["alerts", "sdn"] and msg["by"] == "job:sdn-loop-default"
    assert out["announced"] == {"keys": ["alerts", "sdn"], "ok": True, "error": ""}


def test_a_detection_resolving_with_its_response_awaiting_announces_both(heard):
    _pass(_with_changed(observed(fired=["k1"]), True))
    heard.clear()
    out = _pass(_with_changed(observed(resolved=["k1"], detections=[]), True), T0 + 20)
    assert out["inactive"] and [m["keys"] for m in heard] == [["alerts", "sdn"]]


def test_a_detection_firing_again_while_awaiting_announces_sdn_alone(heard):
    _pass(_with_changed(observed(fired=["k1"]), True))
    heard.clear()
    out = _pass(_with_changed(observed(fired=["k1"]), False), T0 + 10)
    # Fired again: the response is marked active again, which the page shows: announced.
    assert out["fired"] == ["k1"] and not out["proposed"]
    assert [m["keys"] for m in heard] == [["sdn"]]


def test_a_pass_that_only_logged_announces_nothing(heard):
    out = _pass(observed(detections=[]))
    assert out["ok"] and [line["step"] for line in out["lines"]] == ["read", "detect"]
    assert heard == [] and "announced" not in out


def test_a_failed_announcement_is_said_and_the_pass_stands(networks, monkeypatch):  # noqa: F811
    monkeypatch.setattr(I, "_emitter", None)          # no socket: announce raises
    monkeypatch.setattr(CL, "respond_to_threat", lambda *a, **k: {})
    out = _pass(_with_changed(observed(fired=["k1"]), True))
    assert out["ok"] and out["proposed"] and len(LP.awaiting(NET)["rows"]) == 1
    assert out["announced"]["ok"] is False and out["announced"]["keys"] == ["alerts", "sdn"]
    assert out["announced"]["error"].startswith("RuntimeError: no emitter")
