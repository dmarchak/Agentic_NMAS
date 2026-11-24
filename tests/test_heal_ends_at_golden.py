"""A read at a golden that departs from intent proves nothing (the correctness review's G4-D3
and D6, C3966; `modules/heal/triggers.py` `clean_ended`, `modules/heal/act.py`
`golden_not_proof`, `modules/heal/decide.py`).

Since C3909 a golden departing from its committed intent holds nothing: the decision stands
the incident on a can't-fix ("the golden departs from its committed intent ... the AI
investigates"). A drift run that then reads the device at that golden reads it at a state
that is not its intent, so it ends nothing, as Mercury's confirmation read already judges it
("a read at it proves nothing"); and a decision settled at such a golden never says the
golden matches its intent.

No device, no network, a fake clock; the decision's sources are tests/test_heal_decide.py's
`Fake`, the fold's world tests/test_heal_triggers.py's.
"""
import time

import pytest

import tests.test_heal_standing as HS

from tests.test_heal_analysis import ai  # noqa: F401 (the fixture)
from tests.test_heal_decide import DC, DS, GOLDEN, I, settle
from tests.test_heal_decide import Fake, lab  # noqa: F401 (the fixture `fold` builds on)
from tests.test_heal_policy import T0, iso
from tests.test_heal_standing import R8, change, decide, fold, golden_now, the  # noqa: F401
from tests.test_heal_standing import adj, pass_at, read_as
from tests.test_heal_triggers import T
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)


def _clean_read(at):
    return T.after_drift_record("Default", {"triggered_by": "scheduled", "drifted_devices": [],
                                            "clean_devices": [{"hostname": "core-b",
                                                               "read_at": at}]}, now=at + 1)


def test_departing_golden_cant_fix_not_ended_by_clean_read(fold, monkeypatch):  # noqa: F811
    change("core-b", T0)
    d = decide("core-b", R8, T0 + 150, state="departs")
    assert d["outcome"] == "cant_fix", d
    s = the("core-b")["standing"]
    assert (s["on"], s["guard"]) == ("departure", None) and s["departure"]
    golden_now(monkeypatch, "departs")
    got = _clean_read(T0 + 3600)
    assert got.get("ended", []) == [], got
    inc = the("core-b")
    assert inc["state"] == "standing" and inc["standing"]["decision"] == d["decision"]


def test_an_at_golden_decision_says_a_departing_golden_departs(lab):  # noqa: F811
    inc = settle(GOLDEN, how="at_golden")
    d = DC.decide_one("Default", inc, now=T0, sources=Fake(GOLDEN, state="departs"))
    # C3910, the operator's ruling 0 (2026-11-18): a departing golden is a Tier 3 can't-fix,
    # never "nothing to heal" (`test_at_a_departing_golden_with_no_symptom_...` below).
    assert d["outcome"] == "cant_fix", d
    assert "matches its intent" not in d["words"], d["words"]
    assert "differs from its intent" in d["words"], d["words"]


@pytest.mark.parametrize("state", ["departs", "unknown"])
def test_at_a_departing_golden_with_no_symptom_is_a_tier_3_cant_fix_never_closed(
        lab, state):  # noqa: F811
    """C3910 (the operator, 2026-11-17: "a device at a golden that departs from intent is a
    departure ... never 'nothing to heal'"; the operator's ruling 0, 2026-11-18: "Keep the
    interim (c)", a departing golden is a Tier 3 can't-fix and the AI investigates): an
    incident settled at its golden, that golden departing from committed intent (or its
    intent state unknown: no read at it proves the approved state, `act.golden_not_proof`),
    no symptom, is decided a can't-fix of Tier 3 naming the departure, as the departing golden
    with a departure is, and stays open on it: never closed as nothing to heal. Nothing is
    restored (the restore to intent is C4093's build)."""
    settle(GOLDEN, how="at_golden", claim=False)
    (ran,) = DC.run("Default", now=T0, sources=Fake(GOLDEN, state=state))["decided"]
    d = DS.find("Default", ran["decision"])
    assert (d["outcome"], d["tier"], d["guard"], d["program"]) == ("cant_fix", 3, None, []), d
    assert "nothing to heal" not in d["words"], d["words"]
    assert "differs from its intent" in d["words"], d["words"]
    assert "the AI investigates" in d["words"], d["words"]
    (inc,) = [i for i in I.read("Default")["incidents"] if i["id"] == d["incident"]]
    assert inc["state"] == "standing", inc
    assert inc["standing"]["outcome"] == "cant_fix", inc["standing"]


def test_at_a_departing_golden_a_symptom_cleared_by_itself_is_still_a_cant_fix(lab):  # noqa: F811
    """C3910's same branch: every symptom read gone leaves the device at a golden that departs
    from intent, which is a departure, so the decision is the interim's can't-fix, never
    "nothing to heal: every symptom ... has cleared by itself". At a golden AT its intent the
    same read is nothing to heal (tests/test_heal_decide.py's
    `test_a_symptom_that_cleared_by_itself_is_nothing_to_heal`)."""
    trig = [{"kind": "adjacency", "key": "adj:1", "epoch": T0 - 900, "at": iso(T0 - 900),
             "source": "adjacencies", "words": "the adjacency is down"}]
    src = Fake(GOLDEN, state="departs")
    src.symptom_now = lambda device, triggers: "gone"
    inc = settle(GOLDEN, how="at_golden", triggers=trig)
    d = DC.decide_one("Default", inc, now=T0, sources=src)
    assert (d["outcome"], d["tier"]) == ("cant_fix", 3), d
    assert "nothing to heal" not in d["words"], d["words"]
    assert "differs from its intent" in d["words"], d["words"]


@pytest.mark.parametrize("state", ["departs", "unknown"])
@pytest.mark.parametrize("symptom", [True, False], ids=("link down", "no symptom"))
def test_a_departure_that_leaves_no_unit_at_a_departing_golden_is_a_cant_fix(
        lab, state, symptom):  # noqa: F811
    """The correctness review's MEDIUM-C (review-devicewrite-fixes-2.md), as it holds on this
    code: an incident settled on a departure (not at its golden), read at the decision with no
    unit Mercury would restore, its golden departing from intent (or unknown), was "nothing to
    heal: what departed is not from the approved state" and closed, with its link still down.
    It is the interim's can't-fix (ruling 0), as the same golden with a unit is
    (tests/test_heal_decide.py's `test_4_a_golden_that_departs_from_intent_n5`)."""
    trig = ([{"kind": "adjacency", "key": "adj:1", "epoch": T0 - 900, "at": iso(T0 - 900),
              "source": "adjacencies", "interface": "Gi0/1", "words": "Interface down"}]
            if symptom else None)
    src = Fake(GOLDEN, state=state)
    src.symptom_now = lambda device, triggers: "present"
    inc = settle(GOLDEN, how="persisted", triggers=trig)
    d = DC.decide_one("Default", inc, now=T0, sources=src)
    assert (d["outcome"], d["tier"], d["program"]) == ("cant_fix", 3, []), d
    assert "golden differs from its committed intent" in d["words"], d["words"]
    assert "nothing to heal" not in d["words"], d["words"]


def _symptom_cant_fix_at(state):
    """A symptom can't-fix decided at edge-b's golden, that golden in *state* (its symptom not
    read since the drop, so Tier 3 standing ``on: symptom``: tests/test_heal_standing.py's
    `TestW5.standing_cant_fix`, its golden's state given)."""
    settle(GOLDEN, how="at_golden", triggers=[adj(time.time() - 60)], claim=False)
    src = Fake(GOLDEN, state=state)
    src.symptom_now = lambda device, triggers: "stale"
    (d,) = DC.run("Default", now=T0, sources=src)["decided"]
    assert d["outcome"] == "cant_fix", d
    inc = I.read("Default")["incidents"][0]
    assert inc["state"] == "standing" and inc["standing"]["on"] == "symptom", inc
    return inc


@pytest.mark.parametrize("state", ["departs", "unknown"])
def test_the_detect_pass_ends_no_symptom_cant_fix_at_a_departing_golden(  # noqa: F811
        lab, monkeypatch, state):
    """C4109 (ruling 0, the operator, 2026-11-18: "Keep the interim (c)"; C3910's class on the
    detect pass): a symptom can't-fix at a golden departing from intent (or unknown) whose
    symptom then reads gone leaves the device at that golden, which is a departure, so the
    incident stays the interim's Tier 3 can't-fix. `detect._standing` closed it "nothing to
    heal: every symptom ... cleared by itself ... is at its golden", never asking
    `act.golden_not_proof` as `triggers.clean_ended` does. At a golden at its intent it ends
    as before (tests/test_heal_standing.py's `TestW5`)."""
    inc = _symptom_cant_fix_at(state)
    golden_now(monkeypatch, state)
    got = pass_at(T0 + 62, read_as("clean"), symptom=lambda d, tr: "gone")
    assert got["cleared"] == [], got["cleared"]
    now = I.read("Default")["incidents"][0]
    assert now["state"] == "standing" and now["standing"]["decision"] == \
        inc["standing"]["decision"], now
    golden_now(monkeypatch, "at_intent")
    got = pass_at(T0 + 63, read_as("clean"), symptom=lambda d, tr: "gone")
    assert [c["incident"] for c in got["cleared"]] == [inc["id"]], got["cleared"]


@pytest.mark.parametrize("state", ["departs", "unknown"])
def test_the_notice_ends_no_symptom_cant_fix_at_a_departing_golden(  # noqa: F811
        ai, monkeypatch, state):
    """C4109's second close: the can't-fix notice's, when Mercury's diagnosis reads the symptom
    gone and it stays quiet (`heal_notice._cleared`): at a golden departing from intent (or
    unknown) it ends nothing, and the can't-fix is told as any standing one is."""
    from modules import heal_notice
    from modules.ai import heal_analysis as HA

    inc = _symptom_cant_fix_at(state)
    golden_now(monkeypatch, state)
    monkeypatch.setattr(HA, "analyse", lambda *a, **k: {})
    events = []
    got = heal_notice.notice(
        "Default", inc["id"], deliver=lambda n, e: events.append(e) or {"ok": True},
        wait_s=5, now=T0 + 1, diagnose=HS.TestW5().diagnosis(monkeypatch), diagnosis_wait_s=5,
        quiet_wait=lambda s: None, symptom=lambda device, triggers: "gone")
    assert not got.get("cleared"), got.get("cleared")
    assert I.read("Default")["incidents"][0]["state"] == "standing"
    assert [e["event"] for e in events] == ["cant_fix"], events


def _spy_scripts(monkeypatch):
    """`saved_plans.fire_matching` stood in: the ids of the incidents it was asked to fire on."""
    from modules.nsot import saved_plans
    fired = []
    monkeypatch.setattr(saved_plans, "fire_matching", lambda network, found, **kw: fired.append(
        (found.get("incident") or {}).get("id") or found.get("id")) or [])
    return fired


@pytest.mark.parametrize("state", ["departs", "unknown"])
def test_the_interim_only_stands_and_gives_r1_its_start(lab, monkeypatch, state):  # noqa: F811
    """C4207 (the operator's ruling of 2026-11-23: "the interim's can't-fix only stands and
    gives R1 its start"): the decision job fires no saved script on it, no Alert notice is due
    for it (so no diagnosis action, team message or analysis call), and R1's own start on it
    fires none either; R1 still lists it. The review's 0-A probe: at ed71eb35 `fire_matching`
    was called on all three new interim cases."""
    from modules import heal_notice, incident_page
    from modules.fixit import auto as R1

    fired = _spy_scripts(monkeypatch)
    settle(GOLDEN, how="at_golden", claim=False)
    (ran,) = DC.run("Default", now=T0, sources=Fake(GOLDEN, state=state))["decided"]
    assert ran["outcome"] == "cant_fix", ran
    assert fired == [], fired
    assert [e["incident"] for e in heal_notice.due("Default", now=T0 + 1)] == []
    key = R1.key_of("decision", ran["incident"])
    assert key in [f["key"] for f in R1.failures("Default")["failures"]]
    assert R1.fires_no_scripts(incident_page.resolve("Default", ran["incident"]), key)


@pytest.mark.parametrize("state", ["departs", "unknown"])
def test_a_symptom_cant_fix_still_fires_and_is_told(lab, monkeypatch, state):  # noqa: F811
    """The control for the interim's test above: a symptom can't-fix (not the interim) fires its
    saved scripts, is due an Alert notice, and R1's start on it fires them, as before."""
    from modules import heal_notice, incident_page
    from modules.fixit import auto as R1

    fired = _spy_scripts(monkeypatch)
    inc = _symptom_cant_fix_at(state)
    assert fired == [inc["id"]], fired
    assert [e["incident"] for e in heal_notice.due("Default", now=T0 + 1)] == [inc["id"]]
    assert not R1.fires_no_scripts(incident_page.resolve("Default", inc["id"]),
                                   R1.key_of("decision", inc["id"]))


@pytest.mark.parametrize("kind", ["decision", "retry", "act", "held", "run"])
def test_no_failure_of_an_interim_incident_fires_a_script(lab, kind):  # noqa: F811
    """C4207's review, H1 and M1: R1's start on ANY failure of an incident standing on the
    interim's can't-fix fires no saved script (a ``retry:`` key fired them: a script's save
    re-decided the interim, its retry failed, and R1's start on the retry fired the script)."""
    from modules import incident_page
    from modules.fixit import auto as R1

    settle(GOLDEN, how="at_golden", claim=False)
    (ran,) = DC.run("Default", now=T0, sources=Fake(GOLDEN, state="departs"))["decided"]
    found = incident_page.resolve("Default", ran["incident"])
    assert R1.fires_no_scripts(found, R1.key_of(kind, "x-1")), kind


def test_an_unreadable_step_log_reads_the_interim_from_the_decisions(lab):  # noqa: F811
    """C4207's reviews, L1, N1 and N2: the newest decision in the decision store (written
    first) says whether the incident stands on the interim, over a step-log entry a failed row
    write left stale; the entry answers only where the store holds none; and where neither
    store could be read, it answers yes, so nothing fires on what could not be read."""
    from modules.heal import decide

    assert decide.is_interim({"entry": {}, "decisions": [{"outcome": "cant_fix"},
                                                         {"outcome": "cant_fix", "interim": True}]})
    assert not decide.is_interim({"entry": {}, "decisions": [
        {"outcome": "cant_fix", "interim": True}, {"outcome": "cant_fix"}]})
    # N1: the entry's row for the interim failed to write; the store's newest decision governs.
    assert decide.is_interim({"entry": {"interim": False},
                              "decisions": [{"outcome": "cant_fix", "interim": True}]})
    assert decide.is_interim({"entry": {"interim": True}, "decisions": []})
    # N2: neither store answered.
    assert decide.is_interim({"entry": {}, "decisions": [], "unreadable": ["the step log"]})
    assert not decide.is_interim({"entry": {}, "decisions": [], "unreadable": []})


@pytest.mark.parametrize("state", ["departs", "unknown"])
def test_a_scripts_save_neither_counts_nor_sends_back_the_interim(lab, state):  # noqa: F811
    """C4207's review, M2: Save's "runs on" line and the script-saved retry read one selection
    (`retry._selected`); an incident standing on the interim's can't-fix is in neither, since no
    saved script runs on it. Its problem's own match is asked, so only the interim mark keeps
    it out."""
    from modules import incident_page
    from modules import problem as P
    from modules.heal import retry

    settle(GOLDEN, how="at_golden", claim=False)
    (ran,) = DC.run("Default", now=T0, sources=Fake(GOLDEN, state=state))["decided"]
    found = incident_page.resolve("Default", ran["incident"])
    prob = P.classify(found)
    assert prob.condition, prob
    got = retry.would_run("Default", {"condition": prob.condition}, now=T0 + 1)
    assert got["error"] == "" and got["incidents"] == [], got
