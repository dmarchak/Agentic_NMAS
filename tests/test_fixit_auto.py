"""R1's trigger (the operator, 2026-11-14; `modules/fixit/auto.py`, `heal_notice.run_fixit`,
`heal_notice.fixit_investigation`): when Mercury's fix fails, does not verify, or none exists for
an incident's kind, ONE AI investigation starts by itself per failure, as the background
feature ``fixit_auto``, off by default on every network and turned on only in Settings › AI.

Through tests/test_fixit_troubleshoot.py's world: r2's real configuration and intent, a
self-healing incident opened by the incidents store's own writer from two lost-stream alerts
(a lost stream: no code fix exists for its kind), and the REAL gateway with only the provider
replaced. No device, no network, no live AI call.

- **Off by default:** no switch, nothing is read further, taken or asked.
- **Once per failure, no double start:** two passes, and two takers of one key, start one.
- **The caps:** past the incident's cap nothing is asked, the start says which cap, and the
  section offers Hand over with the cap reached.
- **No catch-up:** a failure recorded before the switch's turn-on time starts nothing by
  itself; its incident offers the one Start AI troubleshooting.
- **The investigation:** a background call under fixit_auto's trigger, no person on its line,
  its proposal preflighted, and the team told with the BLUF first.
"""
import time

import pytest

from modules.fixit import incident as F
from modules.fixit import section as S
from tests.test_fixit_incident import T0
from tests.test_fixit_section_v2 import DETECTED, NET, attempt, incident, plant
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_fixit_troubleshoot import ADMIN, answer, fix
from tests.test_fixit_troubleshoot import ai  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

NOW = T0


def iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


@pytest.fixture
def clock(monkeypatch, policy):
    """The background switches' clock at the test's moment, so an approval's 14 days are read
    against it, never against the day the test runs; self-healing in AUTO (`policy`)."""
    monkeypatch.setattr("modules.ai.background._now", lambda: NOW)
    return policy


@pytest.fixture
def policy(monkeypatch):
    """Self-healing's policy as `heal.policy.current` answers it (its own tests hold how it is
    reached: the kill switch, the confirmation, the expiry, the stage guard), here AUTO by
    default, confirmed before the incident; ``policy.set(mode, at, kinds)`` changes it."""
    state = {"mode": "auto", "at": DETECTED - 900, "kinds": ["missing_line"]}

    def current(network, now=None, **kw):
        return {"network": network, "mode": state["mode"], "words": state["mode"],
                "kinds_auto": list(state["kinds"]),
                "confirmed": {"by": ADMIN, "at": iso(state["at"])}}
    monkeypatch.setattr("modules.heal.policy.current", current)

    class P:
        @staticmethod
        def set(mode, at=None, kinds=None):
            state.update(mode=mode, **({"at": at} if at is not None else {}),
                         **({"kinds": kinds} if kinds is not None else {}))
    return P


def turn_on(at, day=5.0, month=50.0):
    """fixit_auto ON for the network as `background.turn_on` writes it (who, when, the caps),
    written through the settings' one writer."""
    from modules.nsot import listref
    from modules.settings_schema import write_settings

    net = listref.network_id(NET)
    entry = {"on": True, "by": ADMIN, "verified": "access", "at": iso(at), "estimate": {},
             "day_cap_usd": day, "month_cap_usd": month, "caps_by": ADMIN, "caps_at": iso(at)}
    assert write_settings({"ai_background": {net: {"fixit_auto": entry}}}, actor="")["ok"]


def run(now=NOW):
    from modules import heal_notice

    started = []
    got = heal_notice.run_fixit(NET, now=now, starter=lambda *a: started.append(a))
    return got, started


class TestOffByDefault:
    def test_with_no_switch_nothing_is_taken_or_asked(self, ai, clock):
        iid = plant()
        got, started = run()
        assert got == {"network": NET, "started": [], "capped": [], "off": [], "failed": []}
        assert started == [] and ai.sent == []
        assert F.read(incident(iid))["state"] == "absent", "nothing written for it"

    def test_the_feature_is_declared_off_by_default_and_named_on_the_gateway(self):
        from modules.ai import background
        spec = background.FEATURES["fixit_auto"]
        assert spec["task"] == "fixit_troubleshoot" and spec["findings"] == ("fixit_failure",)
        assert background.switches() == {} or "fixit_auto" not in str(background.switches())


class TestOncePerFailure:
    def test_two_passes_start_one_investigation(self, ai, clock):
        turn_on(DETECTED - 600)
        iid = plant()
        got, started = run()
        key = f"decision:{iid}"
        assert got["started"] == [key] and len(started) == 1
        assert started[0][1:3] == (iid, key)
        got, again = run(NOW + 30)
        assert got["started"] == [] and again == []
        (line,) = F.starts(incident(iid))["starts"]
        assert (line["start"], line["trigger"], line["state"]) == (key, "auto", "started")
        assert "by" not in line, "no person on an automatic start"

    def test_two_takers_of_one_key_take_it_once(self, ai):
        iid = plant()
        inc = incident(iid)
        first = F.claim_start(inc, "act:hd-000000000001", trigger="auto", state="started")
        second = F.claim_start(inc, "act:hd-000000000001", trigger="auto", state="started")
        assert first and second is None
        assert len(F.starts(inc)["starts"]) == 1

    def test_a_new_failure_after_the_first_starts_its_own(self, ai, clock, monkeypatch):
        turn_on(DETECTED - 600)
        iid = plant()
        run()
        # The investigation answered (a proposal line), and then an act failed: a new failure.
        F.record_proposal(incident(iid), "mercury", words="nothing", now=NOW + 1)
        from modules.fixit import auto as A
        real = A.failures

        def with_act(network, **kw):
            got = real(network, **kw)
            got["failures"].append({"key": "act:hd-00000000000a", "kind": "act",
                                    "id": "hd-00000000000a", "incident": iid, "device": "r2",
                                    "outcome": "rolled_back", "epoch": NOW + 5, "at": ""})
            return got
        monkeypatch.setattr(A, "failures", with_act)
        got, started = run(NOW + 60)
        assert got["started"] == ["act:hd-00000000000a"] and len(started) == 1


class TestTheCaps:
    def test_past_the_incidents_cap_nothing_is_asked_and_the_cap_is_said(self, ai, clock):
        from modules.settings_schema import write_settings
        assert write_settings({"ai_cap_usd_per_incident": 0.0001})["ok"]
        turn_on(DETECTED - 600)
        iid = plant()
        got, started = run()
        assert got["capped"] == [f"decision:{iid}"] and started == [] and ai.sent == []
        (line,) = F.starts(incident(iid))["starts"]
        assert line["state"] == "capped" and line["which"] == "incident"
        assert "cap" in line["words"]
        from modules import incident_page
        x = S.view(NET, incident_page.resolve(NET, iid), now=NOW + 1)
        assert x["state"] == "capped" and x["cap"]["state"] == "reached"
        assert x["cap"]["which"] == "incident"
        assert x["actions"]["hand_over"]["offered"] and not x["actions"]["start"]["offered"]
        assert x["bluf"]["fix"]["kind"] == "hand_over"

    def test_past_the_features_own_day_cap_nothing_is_asked(self, ai, clock, monkeypatch):
        turn_on(DETECTED - 600, day=0.0001, month=50.0)
        iid = plant()
        got, started = run()
        assert got["capped"] == [f"decision:{iid}"] and started == []
        (line,) = F.starts(incident(iid))["starts"]
        assert line["which"] == "day", line


class TestNoCatchUp:
    def test_a_failure_before_the_switch_went_on_starts_nothing(self, ai, clock):
        iid = plant()
        turn_on(DETECTED + 60)                   # turned on after the stream was lost
        got, started = run()
        assert got["started"] == [] and started == [] and ai.sent == []
        assert F.read(incident(iid))["state"] == "absent"
        from modules import incident_page
        from modules.fixit import auto as A
        m = A.manual_start(NET, iid, record=incident_page.resolve(NET, iid)["incident"])
        assert m["offered"] and "before automatic troubleshooting was turned on" in m["words"]
        x = S.view(NET, incident_page.resolve(NET, iid), now=NOW)
        assert x["actions"]["start"]["offered"]
        assert x["bluf"]["fix"]["kind"] == "start"

    def test_with_the_switch_off_the_page_offers_the_one_start(self, ai, clock):
        from modules import incident_page
        iid = plant()
        x = S.view(NET, incident_page.resolve(NET, iid), now=NOW)
        assert x["actions"]["start"]["offered"] and x["auto"]["on"] is False
        # The status line says why a person is needed, from the incident's own record (9f62b2c7
        # and 106c117d, the operator, 2026-11-16: a lost stream has no fix Mercury runs by
        # itself, and the AI can investigate), and that the switch is off (ruling 12, the
        # operator, 2026-11-18: "restore 'the switch is off' on the lost stream's status line").
        assert x["status"].endswith(
            "The AI can investigate, but automatic troubleshooting is off for this network"), \
            x["status"]

    def test_a_failure_after_it_went_on_does_start(self, ai, clock):
        turn_on(DETECTED - 1)
        iid = plant()
        got, _started = run()
        assert got["started"] == [f"decision:{iid}"]


class TestInEveryModeOfSelfHealing:
    """The operator, 2026-11-15, replacing 2026-11-14's "R1 fires only while self-healing is in
    Auto": "Drop 'R1 only while self-healing is in Auto': the AI only proposes, and nothing
    runs without a person's approval, so it investigates in Dry run too". The switch and its
    time are the whole condition; the caps and once-per-failure hold as before."""

    @pytest.mark.parametrize("mode", ["dry_run", "auto"])
    def test_dry_run_or_auto_with_the_switch_on_starts_once(self, ai, clock, mode):
        clock.set(mode, at=DETECTED - 900)
        turn_on(DETECTED - 600)
        iid = plant()
        assert run()[0]["started"] == [f"decision:{iid}"]
        assert run(NOW + 30)[0]["started"] == [], "once per failure, whatever the mode"

    def test_a_failure_before_the_switch_still_starts_nothing_in_dry_run(self, ai, clock):
        clock.set("dry_run", at=DETECTED - 900)
        turn_on(DETECTED + 60)                       # turned on after the stream was lost
        iid = plant()
        got, started = run()
        assert got["started"] == [] and started == [] and ai.sent == []
        from modules.fixit import auto as A
        from modules import incident_page
        m = A.manual_start(NET, iid, record=incident_page.resolve(NET, iid)["incident"])
        assert m["offered"], "the person's one press is offered"

    def test_a_code_fix_of_any_kind_that_failed_starts(self, clock):
        from modules.fixit import auto as A
        f = {"epoch": NOW, "outcome": "rolled_back", "fix_kind": "qos_policy"}
        sw = {"on": True, "epoch": NOW - 10}
        assert A.eligible(f, sw) == ""
        assert A.eligible(dict(f, outcome="cant_fix", fix_kind="physical"), sw) == ""
        assert "off" in A.eligible(f, {"on": False, "epoch": NOW - 10})
        assert "before automatic troubleshooting" in A.eligible(f, {"on": True, "epoch": NOW + 1})


def decide(iid, n, outcome, at, guard=None):
    """A heal decision on *iid*, through the step log's own writer."""
    from modules.heal import steplog
    steplog.record_decision(NET, dict({"id": f"hd-{n:012x}", "incident": iid, "device": "r2",
                                       "outcome": outcome, "mode": "auto", "kind": "missing_line",
                                       "words": outcome},
                                      **({"guard": guard} if guard else {})), at)


class TestAHoldIsNoFailure:
    """The review of 2026-11-14 (BLOCKER 1): a hold works as designed (R2), so it starts no paid
    investigation and takes no key; a later can't-fix on the same incident still starts once."""

    def test_a_grace_hold_starts_nothing_and_a_later_cant_fix_starts_once(
            self, ai, clock, monkeypatch):
        from modules.fixit import auto as A
        # This incident's own failure is its decisions, not its lost stream (its no-code-fix).
        monkeypatch.setattr(A, "no_code_fix", lambda record: {})
        turn_on(DETECTED - 600)
        iid = plant()
        decide(iid, 1, "held", DETECTED + 10,
               {"guard": 8, "name": "the grace period", "words": "waits out its grace"})
        got, started = run()
        assert got["started"] == [] and started == [] and ai.sent == []
        assert F.read(incident(iid))["state"] == "absent", "the hold took no key"
        from modules import incident_page
        x = S.view(NET, incident_page.resolve(NET, iid), now=NOW)
        assert "Mercury's fix failed" not in x["status"], x["status"]
        decide(iid, 2, "cant_fix", DETECTED + 20)
        got, started = run(NOW + 30)
        assert got["started"] == [f"decision:{iid}"] and len(started) == 1
        assert run(NOW + 60)[0]["started"] == []


class TestOneInvestigationAtATime:
    """The review of 2026-11-14 (SHOULD 2): one investigation at a time, under the record's
    lock, whatever the keys."""

    def test_two_starts_with_different_keys_at_once_take_one(self, ai):
        inc = incident(plant())
        first = F.claim_start(inc, "decision:a", trigger="auto", state="started", busy_s=600,
                              now=NOW)
        second = F.claim_start(inc, "act:hd-000000000009", trigger="auto", state="started",
                               busy_s=600, now=NOW + 1)
        assert first and second is None
        # Its failure line is never refused, and past the bound a new start may come.
        assert F.claim_start(inc, "decision:a:failed", trigger="auto", state="failed",
                             busy_s=600, now=NOW + 2)
        assert F.claim_start(inc, "act:hd-000000000009", trigger="auto", state="started",
                             busy_s=600, now=NOW + 3)

    def test_a_press_while_the_automatic_pass_runs_is_refused_with_no_call(self, ai, clock):
        from tests.test_fixit_section_v2 import post
        turn_on(DETECTED - 600)
        iid = plant()
        # The pass at the press's own moment, so the press finds its start inside its bound.
        assert run(time.time())[0]["started"] == [f"decision:{iid}"]
        r = post(ai.client, iid, "start", text="")
        assert r.status_code == 409 and "already investigating" in r.get_data(as_text=True)
        assert ai.sent == [], "one paid call at most: none was made by the press"


class TestALostInvestigation:
    def test_past_its_bound_with_no_answer_it_is_drawn_failed_with_ask_again(self, ai):
        from modules import incident_page
        from modules.fixit import section
        iid = plant()
        bound = section.investigation_bound_s()
        F.claim_start(incident(iid), "person:start", trigger="person", state="started",
                      by="op@example.invalid", verified="access", now=NOW - bound - 10)
        x = S.view(NET, incident_page.resolve(NET, iid), now=NOW)
        assert x["state"] == "ready"
        assert f"did not answer in {int(bound)} s" in x["ai_failed"]
        assert "Couldn't troubleshoot" in x["status"]
        assert x["actions"]["ask_again"]["offered"], x["actions"]["ask_again"]


class TestTheInvestigation:
    def test_it_asks_as_its_background_trigger_and_tells_the_team_bluf_first(self, ai, clock):
        from modules import heal_notice
        from modules.ai import calls

        turn_on(DETECTED - 600)
        iid = plant()
        attempt(ai.client, subs=("101",))
        got, started = run()
        (_net, _iid, key, job) = started[0]
        # Premise corrected (17215a95's ladder: a re-subscribe of 101, which attempt 1 tried, is
        # refused as tried): the answer re-subscribes 102 alone, which no attempt tried.
        ai.answer = answer(fix(subscriptions=("102",)))
        told = []
        out = heal_notice.fixit_investigation(NET, iid, key, job,
                                              deliver=lambda n, e: told.append(e) or {"ok": 1})
        assert out["state"] == "proposed", out
        (row,) = [r for r in calls.read()["rows"] if r.get("id") in out["call_ids"]]
        assert row["trigger"]["kind"] == "background"
        assert row["trigger"]["feature"] == "fixit_auto"
        assert row["trigger"]["finding"] == {"kind": "fixit_failure", "id": key}
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert line["source"] == "ai" and "by" not in line
        (event,) = told
        assert event["event"] == "proposal"
        # R4: titled by its problem, never by the alert that raised it.
        assert event["lead"].startswith("r2: telemetry streams 101 and 102 lost. ")
        assert "Mercury can't see r2's interfaces or CPU; traffic is unaffected" in event["lead"]
        assert event["outcome"].startswith("The AI proposes: Re-subscribe r2's telemetry")
        assert event["link"].startswith(f"/v2/incident/{iid}")
        assert "@" not in str(event), "no person's address in the message"

    def test_a_person_trigger_never_stands_in_for_the_background_one(self, ai, clock):
        from modules import incident_page
        from modules.ai import fixit_troubleshoot as AIT
        iid = plant()
        found = incident_page.resolve(NET, iid)
        trig = AIT.background_trigger(NET, "fixit-auto-x", f"decision:{iid}")
        with pytest.raises(AIT.Refused):
            AIT.troubleshoot(NET, found, incident(iid), actor="job:another", actor_verified="",
                             person=False, trigger=trig)
        assert ai.sent == []
