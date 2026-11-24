"""An incident's proposal as a PLAN of catalog operations (C3694; the operator's R1 flow, steps 4
and 6; `modules/fixit/plan.py`, `modules/plan_engine.py`'s ``incident-fix``, routes/fixit_v2.py's
approve, modify and deny), through tests/test_fixit_troubleshoot.py's world: r2's real
configuration and intent, a lost-stream incident from the incidents store's own writer, real
Re-subscribe runs, and the REAL gateway with only the provider replaced. No device, no network,
no live AI call.

- **Preflight, before approval:** each step's own check, its own hash, the plan's hash over
  them; a step a guard refuses is drawn refused with why, and the plan is not approvable.
- **Never offer a failed action:** a step repeating what already failed here is refused at
  preflight, and the failed operation is in Attempts and Other actions only.
- **Approve runs only the approved hash:** another hash is refused with nothing run; the
  approved one runs as the plan engine's incident-fix plan, its step's run naming the incident.
- **Modify yields a new hash and runs nothing; Deny runs nothing.**
"""
import pytest

from modules.fixit import incident as F
from modules.fixit import plan as FP
from modules.fixit import section as S
from tests.test_fixit_section_v2 import NET, attempt, incident, plant, post
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_fixit_troubleshoot import answer, fix
from tests.test_fixit_troubleshoot import ai  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)


def proposed(iid, steps):
    """A proposal line of *steps* (attempt form) in *iid*'s record, as a person's: the line."""
    return F.record_proposal(incident(iid), "person", steps=steps)


TWO = [{"operation": "telemetry-readd", "params": {"sub": "101"}},
       {"operation": "telemetry-resubscribe", "params": {"subs": ["101", "102"]}}]
ONE = [{"operation": "telemetry-resubscribe", "params": {"subs": ["101", "102"]}}]


def view(iid):
    from modules import incident_page
    return S.view(NET, incident_page.resolve(NET, iid))


class TestPreflight:
    def test_each_step_is_checked_and_the_plans_hash_binds_each_steps_own(self, web):
        iid = plant()
        line = proposed(iid, ONE)
        got = FP.preflight(incident(iid), line)
        assert got["approvable"] and len(got["hash"]) == 16
        (step,) = got["steps"]
        assert step["preflight"] == {"ok": True, "refused": "", "code": ""} and len(step["hash"]) == 16
        assert step["words"] == "Re-subscribe r2's telemetry (101, 102)"
        # The same plan in another order, or another step, is another hash.
        other = FP.preflight(incident(iid), proposed(iid, [
            {"operation": "telemetry-resubscribe", "params": {"subs": ["101"]}}]))
        assert other["hash"] and other["hash"] != got["hash"]

    def test_a_step_a_guard_refuses_is_drawn_refused_before_approval(self, web, monkeypatch):
        iid = plant()
        line = proposed(iid, ONE)
        monkeypatch.setattr("modules.nsot.device_ops.holder",
                            lambda network, device: {"operation": "a deploy",
                                                     "actor": "someone"})
        got = FP.preflight(incident(iid), line)
        assert got["approvable"] is False and got["hash"] == ""
        (step,) = got["steps"]
        assert step["preflight"]["ok"] is False
        assert "r2 is held by a deploy" in step["preflight"]["refused"]
        assert got["why_refused"].startswith("Step 1 would be refused: ")
        x = view(iid)
        assert x["proposal"]["approvable"] is False
        assert x["actions"]["approve"]["offered"] is False
        assert "r2 is held by a deploy" in x["actions"]["approve"]["refused"]
        assert x["actions"]["deny"]["offered"] and x["actions"]["modify"]["offered"]

    def test_a_step_the_incident_does_not_name_is_refused(self, web):
        iid = plant()
        line = proposed(iid, [{"operation": "telemetry-resubscribe",
                               "params": {"subs": ["999"]}}])
        got = FP.preflight(incident(iid), line)
        assert not got["approvable"] and "999" in got["why_refused"]


class TestNeverOfferAFailedAction:
    def test_a_step_that_already_failed_here_is_refused_and_is_in_other_actions(self, web):
        iid = plant()
        attempt(web)                                   # attempt 1: 101 and 102, failed
        line = proposed(iid, ONE)
        got = FP.preflight(incident(iid), line)
        assert not got["approvable"]
        assert "already failed on this incident as attempt 1" in got["why_refused"]
        x = view(iid)
        assert [a["attempt"] for a in x["other_actions"]] == [1]
        assert x["bluf"]["fix"]["kind"] != "button" or "Re-subscribe" not in \
            x["bluf"]["fix"]["label"]
        assert x["actions"]["approve"]["offered"] is False

    def test_a_variation_of_a_failed_one_is_offered(self, web):
        iid = plant()
        attempt(web, subs=("101",))
        got = FP.preflight(incident(iid), proposed(iid, ONE))
        assert got["approvable"], got["why_refused"]


class TestApprove:
    def test_another_hash_is_refused_and_nothing_runs(self, web):
        iid = plant()
        line = proposed(iid, ONE)
        r = post(web, iid, "approve", proposal=line["proposal"], hash="0" * 16)
        assert r.status_code == 409
        assert "the plan preflighted now is" in r.get_data(as_text=True)
        assert web.started["job"] == 0 and web.started["hold"] == 0
        assert not [ln for ln in F.read(incident(iid))["lines"] if ln.get("choice")]

    def test_the_approved_hash_runs_as_the_incident_fix_plan(self, web):
        from modules import plan_engine as PE
        from modules.nsot import privileged
        iid = plant()
        line = proposed(iid, ONE)
        plan = FP.preflight(incident(iid), line)
        r = post(web, iid, "approve", proposal=line["proposal"], hash=plan["hash"])
        assert r.status_code == 200, r.get_data(as_text=True)
        # Premise corrected (C3867, 8f1d8006, the operator, 2026-11-16: Approve "starts the
        # plan engine's job at once and answers 'Starting…' in place"): two jobs, Approve's
        # start (its session read again, the engine's start) and the engine's run.
        assert web.started["job"] == 2
        (ap,) = [ln for ln in F.read(incident(iid))["lines"] if ln.get("choice") == "approve"]
        assert ap["plan_hash"] == plan["hash"] and ap["run"]
        rec = PE.record_of(NET, ap["run"])
        assert rec["hash"] == plan["hash"] and rec["plan"] == PE.INCIDENT_FIX
        (step,) = rec["plan_steps"]
        run = privileged.get(NET, step["receipt"]["run"])
        assert run["fixit"]["incident"] == iid and run["fixit"]["proposal"] == line["proposal"]
        # The step's run is the incident's attempt, read from its own record.
        assert [a["run"] for a in F.attempts(incident(iid))["attempts"]] == [run["id"]]

    def test_an_unverified_press_is_refused(self, web, monkeypatch):
        iid = plant()
        line = proposed(iid, ONE)
        plan = FP.preflight(incident(iid), line)
        monkeypatch.setattr("modules.identity.verified_identity", lambda: None)
        r = post(web, iid, "approve", proposal=line["proposal"], hash=plan["hash"])
        assert r.status_code == 403 and web.started["job"] == 0


TWO_SUBS = [{"operation": "telemetry-resubscribe", "params": {"subs": ["101"]}},
            {"operation": "telemetry-resubscribe", "params": {"subs": ["102"]}}]


class TestTheRunStops:
    def test_a_passed_step_of_a_plan_that_did_not_end_done_is_never_drawn_passed(self, web):
        """C4111 (ruling 6): a plan's step that passed its own verify is the fix only when the
        plan ended done. A real one-step plan run and passed, then its record given the one
        edit a later step's refusal makes (its outcome stopped): the card reads stopped and
        offers Ask again, never "passed" with nothing to press; while the plan still runs, it
        reads running."""
        from modules import plan_engine as PE
        from modules.nsot import privileged
        iid = plant()
        line = proposed(iid, ONE)
        plan = FP.preflight(incident(iid), line)
        r = post(web, iid, "approve", proposal=line["proposal"], hash=plan["hash"])
        assert r.status_code == 200, r.get_data(as_text=True)
        (ap,) = [ln for ln in F.read(incident(iid))["lines"] if ln.get("choice") == "approve"]
        rec = PE.record_of(NET, ap["run"])
        assert rec["outcome"] == "done", rec.get("why")
        assert view(iid)["state"] == "passed"
        privileged.record(NET, dict(rec, outcome="stopped", state=PE.RECORD_STATE["stopped"]))
        x = view(iid)
        assert x["state"] == "stopped", x["state"]
        assert x["actions"]["ask_again"]["offered"], x["actions"]["ask_again"]
        privileged.record(NET, dict(rec, outcome="", state="running"))
        assert view(iid)["state"] == "running"

    def test_a_two_step_plan_stops_at_its_first_failure_and_offers_ask_again(self, web):
        import time as _t
        from modules import plan_engine as PE
        from tests.test_heal_resubscribe import ABSENT, Clock, Src, seq
        iid = plant()
        line = proposed(iid, TWO_SUBS)
        plan = FP.preflight(incident(iid), line)
        assert plan["approvable"] and len(plan["steps"]) == 2, plan["why_refused"]
        # The device's stream never comes back: step 1's own verify fails.
        web.state["src"] = Src(clock=Clock(_t.time() + 5), series=seq([ABSENT] * 20))
        r = post(web, iid, "approve", proposal=line["proposal"], hash=plan["hash"])
        assert r.status_code == 200, r.get_data(as_text=True)
        (ap,) = [ln for ln in F.read(incident(iid))["lines"] if ln.get("choice") == "approve"]
        rec = PE.record_of(NET, ap["run"])
        assert rec["outcome"] == "stopped", rec.get("why")
        assert [s["state"] for s in rec["plan_steps"]] == ["failed", "not_run"]
        x = view(iid)
        assert x["state"] == "stopped"
        assert x["actions"]["ask_again"]["offered"], x["actions"]["ask_again"]

    def test_a_step_whose_program_moved_since_approve_is_refused_at_its_apply(self, web):
        from modules import plan_engine as PE
        from modules.nsot import privileged
        from modules.config import list_data_path
        iid = plant()
        kind = PE.STEP_KINDS["telemetry-resubscribe"]
        p = {"incident": iid, "proposal": "p1", "device": "r2", "subscriptions": ["101", "102"]}
        before = len(privileged.runs(NET, limit=50, data_dir=list_data_path(NET))["runs"])
        got = kind.apply(NET, p, "0" * 16, actor="op@example.invalid", reason="the review's test",
                         actor_verified="access", person=True)
        assert got["ok"] is False and got["outcome"] == "moved"
        assert "approved 0000000000000000, now " in got["words"]
        assert "nothing was sent" in got["words"]
        assert len(privileged.runs(NET, limit=50, data_dir=list_data_path(NET))["runs"]) == before


class TestTheCollectorStepsSession:
    """r7's path (the review of 2026-11-14, item 6): the collector step closes exactly the
    session the approval bound, refused naming both sessions when it moved."""

    def test_the_step_refuses_a_session_that_moved_at_its_apply(self, web, monkeypatch):
        from modules import plan_engine as PE
        from modules.heal import resubscribe as R
        real = R.plan

        # Premise corrected (17215a95: the collector close alone is a plan's step, asked of
        # `resubscribe.plan` with ``close_only``): the stand-in takes its whole signature.
        def plan(network, device, subs, *, readd=False, collector=False, sources=None,
                 close_only=False):
            got = real(network, device, subs, readd=readd, sources=sources)
            if collector:
                got = dict(got, close={"remote": "192.0.2.6:57002", "local": "192.0.2.10:57000"})
            return got
        monkeypatch.setattr(R, "plan", plan)
        kind = PE.STEP_KINDS[R.COLLECTOR_KEY]
        assert "session" in [x.name for x in kind.params] and kind.optional == ("session",)
        ok = real(NET, "r2", ["101", "102"])
        p = {"incident": plant(), "proposal": "p1", "device": "r2",
             "subscriptions": ["101", "102"], "session": "192.0.2.6:57001"}
        got = kind.apply(NET, p, ok["hash"], actor="op@example.invalid",
                         reason="the review's test", actor_verified="access", person=True)
        assert got["ok"] is False and got["outcome"] == "moved"
        assert "bound the session from 192.0.2.6:57001" in got["words"]
        assert "one from 192.0.2.6:57002 now" in got["words"]

    @pytest.mark.parametrize("bound,now", [("192.0.2.6:57001", "192.0.2.6:57002"),
                                           ("[2001:db8::6]:57001", "[2001:db8::6]:57002")],
                             ids=["IPv4", "IPv6"])
    def test_the_steps_preview_refuses_a_session_that_moved(self, web, monkeypatch, bound, now):
        from modules import plan_engine as PE
        from modules.heal import resubscribe as R
        iid = plant()
        assert PE._session_refusal(bound) == ""
        monkeypatch.setattr(PE, "collector_session",
                            lambda network, device, subs: {"session": now, "refused": ""})
        step = {"incident": iid, "proposal": "p1", "device": "r2",
                "subscriptions": ["101", "102"], "session": bound}
        got = PE.STEP_KINDS[R.COLLECTOR_KEY].preview(NET, step)
        assert got["ok"] is False
        assert f"bound the session from {bound}" in got["refused"]
        assert f"one from {now} now" in got["refused"]
        # With the session the approval bound, the preview stands.
        monkeypatch.setattr(PE, "collector_session",
                            lambda network, device, subs: {"session": bound, "refused": ""})
        assert PE.STEP_KINDS[R.COLLECTOR_KEY].preview(NET, step)["ok"]


class TestAHoldThatBlocks:
    def test_a_planned_work_hold_that_refused_the_step_says_it_blocks_it(self, web,
                                                                          monkeypatch):
        from modules.heal import steplog
        iid = plant()
        steplog.record_decision(NET, {"id": "hd-0000000000a1", "incident": iid, "device": "r2",
                                      "outcome": "held", "mode": "auto",
                                      "guard": {"guard": 3, "name": "planned work",
                                                "words": "a deploy holds r2"}})
        proposed(iid, ONE)
        monkeypatch.setattr("modules.nsot.device_ops.holder",
                            lambda network, device: {"operation": "a deploy", "actor": "x"})
        x = view(iid)
        assert x["proposal"]["approvable"] is False
        assert any(h.endswith("This blocks the fix below until it ends.") for h in x["holds"]), \
            x["holds"]


class TestModifyAndDeny:
    def test_modify_yields_a_new_plan_and_hash_and_runs_nothing(self, ai):
        iid = plant()
        attempt(ai.client, subs=("101",))
        # The plan waiting is approvable (a variation of attempt 1): Modify must still run it
        # never, only ask for a revised one.
        line = proposed(iid, ONE)
        before = FP.preflight(incident(iid), line)
        assert before["approvable"], before["why_refused"]
        # Premise corrected (17215a95's ladder: a re-subscribe of 101, which attempt 1 tried, is
        # refused as tried): the revised plan re-subscribes 102 alone, which no attempt tried.
        ai.answer = answer(fix(subscriptions=("102",)))
        ai.client.started.update(dict.fromkeys(ai.client.started, 0))
        r = post(ai.client, iid, "modify", proposal=line["proposal"],
                 text="re-subscribe both streams, 101 and 102")
        assert r.status_code == 200, r.get_data(as_text=True)
        assert len(ai.sent) == 1
        assert "re-subscribe both streams" in str(ai.sent[0]), "the person's words were sent"
        after = view(iid)["proposal"]
        assert after["id"] != line["proposal"] and after["hash"] != before["hash"]
        # Nothing ran: no device held, no approval, no plan run. Premise corrected (2026-11-14,
        # "AI start returns at once, runs as a job"): the one job started is the investigation's.
        assert ai.client.started["hold"] == 0 and ai.client.started["job"] == 1
        assert not [ln for ln in F.read(incident(iid))["lines"] if ln.get("choice") == "approve"]
        from modules.nsot import privileged
        from modules.config import list_data_path
        runs = privileged.runs(NET, limit=50, data_dir=list_data_path(NET))["runs"]
        assert not [r for r in runs if isinstance(r, dict) and r.get("key") == "plan"]

    def test_modify_with_no_words_is_refused_and_sends_nothing(self, ai):
        iid = plant()
        line = proposed(iid, ONE)
        r = post(ai.client, iid, "modify", proposal=line["proposal"], text="  ")
        assert r.status_code == 400 and ai.sent == []

    def test_deny_records_its_reason_and_runs_nothing(self, web):
        iid = plant()
        line = proposed(iid, ONE)
        r = post(web, iid, "deny", proposal=line["proposal"], reason="not during the window")
        assert r.status_code == 200, r.get_data(as_text=True)
        (d,) = [ln for ln in F.read(incident(iid))["lines"] if ln.get("choice") == "deny"]
        assert d["decides"] == line["proposal"] and d["reason"] == "not during the window"
        assert web.started == {"ask": 0, "hold": 0, "job": 0, "relay": 0}
        x = view(iid)
        assert x["state"] == "denied" and x["proposal"] is None
        assert x["actions"]["ask_again"]["offered"] and x["actions"]["hand_over"]["offered"]
        assert not x["actions"]["approve"]["offered"]

    @pytest.mark.parametrize("what", ["approve", "deny", "modify"])
    def test_a_stale_proposal_is_refused(self, web, what):
        iid = plant()
        old = proposed(iid, ONE)
        proposed(iid, ONE)
        r = post(web, iid, what, proposal=old["proposal"], hash="0" * 16, text="x y z")
        assert r.status_code == 409 and web.started["job"] == 0
