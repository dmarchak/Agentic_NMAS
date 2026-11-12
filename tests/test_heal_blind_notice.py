"""C3330 (the operator, 2026-11-12): "Add a notification event kind "self-healing is blind or
paused", on by default for everyone, so it still reaches a person at warning"
(modules/heal/blind_notice.py).

- the event kind is declared (`notify.message.EVENTS`) and every notice it sends passes the
  message's own check (its fields, its bounds, its link a Mercury page);
- detection's ``blind`` row is told once per raise, never per read, to every team in the
  teams store; a raise after a clear is told again; a row that is not blind tells nobody;
- turning self-healing off for a network and stopping it everywhere each tell every team once,
  at the press, naming the person by display name;
- a notice that cannot be sent never fails the read or the press;
- detection's row is a warning, never critical (critical is a network outage).
"""

import pytest

from modules.heal import blind_notice as BN
from modules.notify import message
from tests.test_heal_policy import H, T0, confirm  # noqa: F401
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture)


class Told:
    """`delivery.deliver_event`'s stand-in: each event checked as a message is, and kept."""

    def __init__(self):
        self.events = []

    def __call__(self, event, team_ids):
        self.events.append((message.check_event(event), list(team_ids)))
        return {"ok": True, "sent": len(team_ids), "failed": 0, "error": ""}


def blind(since, unit="self-healing:heal-detect"):
    return {"unit": unit, "state": "blind", "since": since, "list": "Default",
            "headline": "Self-healing can't see configuration changes on Default since 14:36 "
                        "UTC on 2026-11-12",
            "detail": "its last read failed: Loki did not answer within 5 s",
            "action": {"label": "Test Loki's connection in this network's Settings › "
                                "Integrations"}}


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    return tmp_path


def test_the_kind_is_declared_and_on_by_default():
    assert message.EVENTS[BN.EVENT] == "self-healing is blind or paused"
    assert BN.ON_BY_DEFAULT is True


def test_a_raise_is_told_once_to_every_team_and_again_after_a_clear(store):
    told = Told()
    teams = ["a1b2c3d4e5f6", "0f1e2d3c4b5a"]
    first = BN.notify_detection(1000, rows=[blind(900)], deliver=told, teams=teams)
    assert len(first) == 1 and len(told.events) == 1
    (event, to), = told.events
    assert to == teams and event["event"] == "heal_blind" and event["network"] == "Default"
    assert event["happened"].startswith("Self-healing can't see configuration changes")
    assert event["link"] == "/v2/attention"
    # Every later read of the same raise: nobody told again.
    for t in range(1005, 1100, 5):
        assert BN.notify_detection(t, rows=[blind(900)], deliver=told, teams=teams) == []
    assert len(told.events) == 1
    # Cleared, then blind again from a later last good read: a new raise, told.
    assert BN.notify_detection(1200, rows=[dict(blind(900), state="ok")], deliver=told,
                               teams=teams) == []
    assert len(BN.notify_detection(1300, rows=[blind(1250)], deliver=told, teams=teams)) == 1
    assert len(told.events) == 2


def test_a_row_that_is_not_blind_tells_nobody(store):
    told = Told()
    for state in ("ok", "waiting", "unscanned", "unknown"):
        BN.notify_detection(1000, rows=[dict(blind(900), state=state)], deliver=told,
                            teams=["a1b2c3d4e5f6"])
    assert told.events == []


def test_a_notice_that_cannot_be_sent_fails_nothing(store):
    def boom(event, team_ids):
        raise RuntimeError("the relay is down")
    assert BN.notify_detection(1000, rows=[blind(900)], deliver=boom, teams=["x"]) == []
    assert BN.notify_paused("Default", "op@example.com", "w", deliver=boom)["sent"] == 0


def test_turning_it_off_and_stopping_it_tell_every_team_at_the_press(networks, monkeypatch):  # noqa: F811
    told = Told()
    monkeypatch.setattr("modules.notify.delivery.deliver_event", told)
    monkeypatch.setattr(BN, "every_team", lambda: ["a1b2c3d4e5f6"])
    confirm("Default", heal_mode="dry_run")
    H.turn_off("Default", actor="op@example.com", actor_verified="access", now=T0)
    (event, to), = told.events
    assert event["event"] == "heal_blind" and event["network"] == "Default"
    assert event["happened"].startswith("Self-healing was turned off on Default by ")
    assert "op@example.com" not in event["happened"], "a person by display name, never id"
    # Off already: nothing pressed, nobody told again.
    H.turn_off("Default", actor="op@example.com")
    assert len(told.events) == 1
    H.stop(actor="op@example.com", actor_verified="access", why="a bad rollout")
    assert len(told.events) == 2
    assert told.events[1][0]["happened"].startswith(
        "Self-healing was turned off on every network by ")


def test_detections_row_is_a_warning():
    from modules import attention as A
    assert A._JOB_STATES["blind"][1] == "warning"       # noqa: SLF001
    assert A._JOB_STATES["restarting"][1] == "warning"  # noqa: SLF001
