"""Self-healing reading Off closes no incident (the correctness review's G4-D1, C3880; the
operator, 2026-11-16: "Self-healing Off must not close standing incidents (unconfirmed heals
included)"; 7d54cf24: "Only 'healed' closes an incident").

`policy.current` reads ``off`` for a person's Off, for Stop everywhere, for settings that
cannot be read, and for stored values that are not the confirmed ones. None of those is a fix,
so none may close an open incident:

- the detect pass under Off closes neither a standing decision (a dry-run would-heal) nor a
  standing act (an unconfirmed heal), whichever of the four made it Off;
- a decision of ``off`` (guards 1 and 2) leaves its incident open, said: a ready incident goes
  back to watching with the Off's words, and one taken from its standing goes back on it;
- the switch-on batch's restore, when Stop everywhere lands while its job runs, leaves the
  would-heal it took standing.

No device, no network, a fake clock; the decision's sources are tests/test_heal_decide.py's
`Fake`.
"""
import pytest

from tests.test_heal_decide import DC, GOLDEN, I, ROUTE4, Fake, lab, settle  # noqa: F401
from tests.test_heal_policy import T0, confirm
from tests.test_heal_triggers import _Lazy
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

DT, P = _Lazy("detect"), _Lazy("policy")
NET = "Default"
RUNNING = GOLDEN + ROUTE4


def _would_heal(device):
    """An incident on *device* standing on the real decision's dry-run would-heal."""
    inc = settle(RUNNING, device=device, claim=False)
    (d,) = DC.run(NET, now=T0, sources=Fake(RUNNING))["decided"]
    assert d["outcome"] == "would_heal", d
    return inc["id"], d["decision"]


def _standing_act(device):
    """An incident on *device* standing on a heal that could not confirm its fix (C3870): its
    standing record an act's, outcome ``symptom_remains``, as `act.outcome_on_incident` leaves
    it."""
    inc_id, _ = _would_heal(device)

    def change(doc):
        inc = next(i for i in doc["incidents"] if i["id"] == inc_id)
        inc["standing"] = dict(inc["standing"], act=True, outcome="symptom_remains")
    I._mutate(NET, change)
    return inc_id


def _of(inc_id):
    return next(i for i in I.read(NET)["incidents"] if i["id"] == inc_id)


@pytest.fixture
def standing(lab):  # noqa: F811
    """A standing dry-run would-heal on edge-b and a standing act on edge-c."""
    return {"would_heal": _would_heal("edge-b")[0], "act": _standing_act("edge-c")}


def _off_by_unreadable_settings(monkeypatch):
    from modules import list_settings as L

    def unreadable(*a, **k):
        raise L.ListSettingsUnreadable("the settings file is torn")
    monkeypatch.setattr(L, "resolve", unreadable)


def _off_by_unconfirmed_values(monkeypatch):
    from modules import list_settings as L

    L.write(NET, {"heal_max_per_device_hour": 5})        # a guard value nobody confirmed


def _off_by_a_person(monkeypatch):
    P.turn_off(NET, actor="op@example.com")


def _off_by_stop_everywhere(monkeypatch):
    P.stop(actor="op@example.com", why="a drill")


OFF = {"unreadable settings": _off_by_unreadable_settings,
       "unconfirmed values": _off_by_unconfirmed_values,
       "a person's Off": _off_by_a_person,
       "Stop everywhere": _off_by_stop_everywhere}


class TestTheDetectPassUnderOff:
    @pytest.mark.parametrize("why", list(OFF))
    def test_off_closes_nothing_that_stands(self, standing, monkeypatch, why):
        OFF[why](monkeypatch)
        got = DT.run(NET, now=T0 + 60, check=lambda *a, **k: pytest.fail("read a device"),
                     clock=lambda: T0 + 60)
        assert got["mode"] == "off", got
        assert got["closed"] == [], got
        for kind, inc_id in standing.items():
            inc = _of(inc_id)
            assert inc["state"] == "standing", (why, kind, inc.get("closed_why"))
        assert _of(standing["act"])["standing"]["act"] is True

    def test_off_leaves_a_watching_incident_watching(self, lab):  # noqa: F811
        from modules.heal import incidents

        inc_id = incidents.sight(NET, "edge-b", {
            "kind": "config_change", "key": "cfg:9", "epoch": T0, "at": "",
            "attribution": {"by": "outside"}, "words": "CONFIG_I"}, now=T0)["incident"]
        P.turn_off(NET, actor="op@example.com")
        got = DT.run(NET, now=T0 + 60, check=lambda *a, **k: pytest.fail("read a device"),
                     clock=lambda: T0 + 60)
        assert got["closed"] == [] and _of(inc_id)["state"] == "watching"


class TestAnOffDecision:
    @pytest.mark.parametrize("why", ["a person's Off", "Stop everywhere"])
    def test_a_ready_incident_decided_off_waits_for_self_healing(self, lab, monkeypatch,  # noqa: F811
                                                                why):
        inc = settle(RUNNING, device="edge-b", claim=False)
        OFF[why](monkeypatch)
        (d,) = DC.run(NET, now=T0, sources=Fake(RUNNING))["decided"]
        assert d["outcome"] == "off", d
        got = _of(inc["id"])
        assert got["state"] in I.OPEN_STATES, got.get("closed_why")
        assert got["state"] == "watching", got["state"]
        said = (got.get("deferred") or {}).get("why") or ""
        assert "waits for self-healing" in said, said

    def test_a_standing_incident_decided_off_goes_back_on_its_decision(self, lab):  # noqa: F811
        inc_id, decision = _would_heal("edge-b")
        taken = I.take_standing(NET, inc_id, by="a test", now=T0 + 10)
        P.stop(actor="op@example.com", why="a drill")
        made = DC.decide_one(NET, taken, now=T0 + 10, sources=Fake(RUNNING))
        made.pop("steps", None), made.pop("phase", None)
        from modules.heal import decisions
        d = decisions.record(NET, made, T0 + 10)
        assert d["outcome"] == "off"
        DC._act(NET, taken, d, T0 + 10)
        got = _of(inc_id)
        assert got["state"] == "standing", got.get("closed_why")
        assert got["standing"]["decision"] == decision


class TestTheSwitchOnBatch:
    def test_a_restore_under_stop_everywhere_leaves_its_would_heal_standing(self, lab):  # noqa: F811
        from modules.heal import batch as B
        from modules.heal import decisions

        inc_id, decision = _would_heal("edge-b")
        d = decisions.find(NET, decision)
        P.stop(actor="op@example.com", why="stopped while the batch runs")
        item = {"device": "edge-b", "incident": inc_id, "decision": decision,
                "from": "would_heal", "program_hash": d["program_hash"]}
        got = B._one(NET, item, {"id": "hb-1", "by": "op@example.com"},
                     act_start=lambda *a, **k: pytest.fail("an act started under Stop"),
                     sources=Fake(RUNNING))
        assert got["outcome"] == "off", got
        inc = _of(inc_id)
        assert inc["state"] == "standing", inc.get("closed_why")
        assert inc["standing"]["decision"] == decision
