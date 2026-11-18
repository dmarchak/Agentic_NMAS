"""Every step kind an incident's fix admits, carried through the fix-it record generically, and
the AI's own identity with its engineer role (the operator, 2026-11-15; Gate 1a).

- **Carried, keyed on the plan engine's `STEP_KINDS` and `FIX_ADMITTED`**, never per kind: a
  proposal line holding an intent change and its deploy is kept (`incident.record_proposal`),
  read back (`plan.steps_of`, `as_catalog`), preflighted by each step kind's own preview
  (`plan.preflight`) with the hash Approve's run computes, and drawn in words (no code key);
  a step kind planted into `FIX_ADMITTED` is carried the same way with no branch of its own.
- **The repeat of a failed attempt**, the catalog's rule: a step of the plan that ran and failed
  is an attempt (`incident.attempts`), and the same step proposed again is refused naming it,
  unless a value it is compared by differs, which is named.
- **The AI's identity** (`identity.ai_identity`, the engineer role): every gated action refused
  (`identity.may`, so every settings and admin route, `route_gates.enforce`); a setting it writes
  refused naming the setting (`settings_schema.write_settings`, `list_settings.write`); and an
  AI-proposed plan holding a step a person takes through a settings route refused at preflight.

On the host's real committed documents (tests/test_committed_before_p1.py's `host`, r2 and s1 in
Lab); THE apply stood in at its one seam (`routes.deploy.apply_batch`), as
tests/test_plan_intent_deploy.py does.
"""
import dataclasses
import os
import time

import pytest

from modules import identity
from modules import plan_engine as E
from modules.fixit import incident as F
from modules.fixit import plan as FP
from tests.test_committed_before_p1 import host  # noqa: F401 (the fixture)

PERSON = "person@example.invalid"
REASON = "the port carries the new core link"
INCIDENT = "hi-abcdef12"
GI2 = "interfaces.GigabitEthernet2"
DESC = "s4 Gi1/0 - VLAN 100 CORE"
RENAME = {"path": f"{GI2}.description", "before": DESC, "after": DESC + " (plan)"}
#: IPv6 beside IPv4, documentation prefixes.
V6 = {"path": f"{GI2}.ipv6", "before": ["2001:DB8:3::12/64"],
      "after": ["2001:DB8:3::12/64", "2001:DB8:40::12/64"]}
V4 = {"path": f"{GI2}.ipv4", "before": "10.255.3.12 255.255.255.0",
      "after": "192.0.2.40 255.255.255.0"}


def incident():
    return F.Incident(network="Lab", id=INCIDENT, device_id="uid:r2-test", device="r2",
                      detected=time.time() - 3600)


@pytest.fixture
def lab(host, monkeypatch):  # noqa: F811
    """r2's incident with a page, its record and the operations' records in the network's own
    folder, r2 Mercury's to change and no planned work on it; THE apply stood in."""
    folder = os.path.dirname(host["repo"])
    monkeypatch.setattr("modules.config.list_data_path", lambda name: folder)
    monkeypatch.setattr("modules.fixit.plan._incident_for", lambda network, i: (
        (incident(), "") if (network, i) == ("Lab", INCIDENT)
        else (None, f"{i} is no incident of {network} that has a page")))
    monkeypatch.setattr("modules.inventory.management.refusal_for",
                        lambda network, device, what="": "")
    monkeypatch.setattr("modules.heal.guards.g3_planned", lambda network, device, now, **kw: None)
    seams = {"calls": [], "verify": True}

    def apply_batch(network, confirmations, command_hashes, **kw):
        seams["calls"].append(command_hashes)
        return {"results": [{"device": d, "outcome": "deployed",
                             "verify": {"ok": seams["verify"]}} for d in confirmations]}
    monkeypatch.setattr("routes.deploy.apply_batch", apply_batch)
    return dict(host, seams=seams)


def line_of(*steps, source="mercury"):
    """A proposal line recorded in the incident's record, as a plan's proposal is kept."""
    return F.record_proposal(incident(), source,
                             steps=[{"operation": op, "params": p} for op, p in steps],
                             **({"calls": ["call-1"]} if source == "ai" else {}))


def run_line(line, **over):
    params = FP.plan_params(incident(), line)
    p = E.preview("Lab", E.INCIDENT_FIX, params)
    assert p["ok"], p["refused"]
    kw = dict(actor=PERSON, actor_verified="access", person=True, reason=REASON)
    kw.update(over)
    return E.run("Lab", E.INCIDENT_FIX, params, p["hash"], **kw)


EDIT = ("intent-edit", {"device": "r2", "changes": [V4, V6]})
DEPLOY = ("intent-deploy", {"device": "r2"})


# ── Carried through the fix-it record, keyed on the plan engine ─────────────────────────────

class TestCarriedGenerically:
    def test_an_intent_change_and_its_deploy_are_kept_read_back_and_preflighted(self, lab):
        line = line_of(EDIT, DEPLOY)
        assert [s["operation"] for s in line["steps"]] == ["intent-edit", "intent-deploy"]
        steps = FP.steps_of(line, "r2")
        assert steps[1] == {"operation": "intent-deploy", "params": {"device": "r2",
                                                                      "remove": []}}
        plan = FP.preflight(incident(), line)
        assert plan["approvable"], plan["why_refused"]
        assert [s["preflight"]["ok"] for s in plan["steps"]] == [True, True]
        # The hash drawn is the one Approve's run computes (the engine's own preview).
        approve = E.preview("Lab", E.INCIDENT_FIX, FP.plan_params(incident(), line))
        assert plan["hash"] == approve["hash"] and approve["ok"]
        # Drawn in words, never a code key; the deploy's program from the candidate intent.
        words = [s["words"] for s in plan["steps"]]
        assert words[0].startswith("r2's intent: 2 changes") and "intent-edit" not in words[0]
        assert "ipv6 address 2001:DB8:40::12/64" in words[1], words[1]
        assert "ip address 192.0.2.40 255.255.255.0" in words[1], words[1]
        labels = [label for label, _w in plan["bound"]]
        assert "Step 2: Mercury found its program" in labels, labels

    def test_a_kind_planted_into_the_admitted_kinds_is_carried_with_no_branch(self, lab,
                                                                              monkeypatch):
        """The fix-it record reads the step kind's own declaration: a new kind added to
        `FIX_ADMITTED` is kept, read back, preflighted and drawn as the two are."""
        seen = []

        def preview(network, p, *, candidate=None):
            seen.append(dict(p))
            return {"ok": True, "hash": "planted0hash0000", "resolved": {"x": "1"},
                    "drawn": {"title": "A planted step", "change": "changes nothing"}}
        kind = dataclasses.replace(E.STEP_KINDS["intent-deploy"], key="planted-step",
                                   preview=preview, words="A planted step kind")
        monkeypatch.setitem(E.STEP_KINDS, "planted-step", kind)
        monkeypatch.setattr(E, "FIX_ADMITTED", E.FIX_ADMITTED + ("planted-step",))
        line = line_of(("planted-step", {"device": "r2", "remove": []}))
        plan = FP.preflight(incident(), line)
        assert plan["approvable"], plan["why_refused"]
        assert plan["steps"][0]["words"] == "A planted step: changes nothing"
        assert seen == [{"device": "r2", "remove": [], "incident": INCIDENT, "proposal": "p1"}]

    def test_an_attempts_words_are_the_engines_never_a_key(self):
        from modules.fixit.section import short_words
        assert short_words("intent-deploy", "r2", {}) == (
            E.STEP_KINDS["intent-deploy"].words + " (r2)")


# ── The repeat of a failed attempt, the catalog's rule ──────────────────────────────────────

class TestACommandPlansOwnNames:
    """C3978 (the operator's decision 16, 2026-11-18: tests first): an AI plan's command plan
    step names its parameters by the plan's own names (`heal.catalog.COMMAND_PLANS`, from the
    plan's YAML: telemetry-subscription-recreate's ``subscription``), and `as_catalog` keeps
    them, as it keeps an attempt's short names (``sub``); a name the plan does not take is
    still left out. Before, the ``subscription`` was dropped, so the recreate step's preflight
    refused it for a reason that was not so ("gives no subscription")."""

    def test_the_plans_own_name_is_kept_and_a_name_it_does_not_take_is_not(self):
        from modules.fixit import plan as FP
        key = "telemetry-subscription-recreate"
        assert FP.as_catalog(key, {"subscription": "101"}, "edge1") == {
            "device": "edge1", "subscription": "101"}
        assert FP.as_catalog(key, {"sub": "101"}, "edge1") == {
            "device": "edge1", "subscription": "101"}, "an attempt's short name, as before"
        assert FP.as_catalog(key, {"subscription": "101", "collector": True,
                                   "receiver": "x"}, "edge1") == {
            "device": "edge1", "subscription": "101"}

    def test_a_plan_of_two_steps_carries_the_subscription_to_its_second(self):
        from modules.fixit import plan as FP
        line = {"steps": [{"operation": "collector-close", "params": {"subs": ["101", "102"]}},
                          {"operation": "telemetry-subscription-recreate",
                           "params": {"subscription": "101"}}]}
        (_close, recreate) = FP.steps_of(line, "edge1")
        assert recreate == {"operation": "telemetry-subscription-recreate",
                            "params": {"device": "edge1", "subscription": "101"}}


class TestTheRepeat:
    def test_a_deploy_that_failed_is_refused_again_unless_its_program_differs(self, lab):
        lab["seams"]["verify"] = False
        rec = run_line(line_of(EDIT, DEPLOY))
        assert rec["outcome"] == "stopped", rec
        whole = F.attempts(incident())
        assert whole["state"] == "ok", whole["error"]
        got = whole["attempts"]
        assert [(a["operation"], a["passed"]) for a in got] == [
            ("intent-edit", True), ("intent-deploy", False)], got
        # The same deploy proposed again: the same program, so refused naming the attempt.
        again = FP.preflight(incident(), line_of(DEPLOY))
        assert not again["approvable"]
        assert again["steps"][0]["preflight"]["code"] == "repeat"
        assert "it already failed on this incident as attempt 2" in \
            again["steps"][0]["preflight"]["refused"]
        # Intent moved since: another program, so it is offered, naming what differs.
        from modules.nsot import intent_edit
        opened = intent_edit.open_doc("Lab", "r2")
        assert intent_edit.commit("Lab", "r2", opened["yaml"].replace(
            f"description: {DESC}", f"description: {DESC} (again)"), "a person's edit",
            opened["base"], "someone")["ok"]
        other = FP.preflight(incident(), line_of(DEPLOY))
        assert other["approvable"], other["why_refused"]
        checks = E.preview("Lab", E.INCIDENT_FIX, FP.plan_params(
            incident(), line_of(DEPLOY)))["steps"][0]["drawn"]["checks"]
        assert any(c.startswith("attempt 2 ran it and did not pass; this one differs in "
                                "program (was ") for c in checks), checks

    def test_an_intent_change_that_failed_is_refused_again(self, lab, monkeypatch):
        from modules.nsot import intent_edit
        monkeypatch.setattr(intent_edit, "commit", lambda *a, **kw: {
            "ok": False, "error": "the repository refused it (a test's own words)"})
        rec = run_line(line_of(("intent-edit", {"device": "r2", "changes": [RENAME]})))
        assert rec["outcome"] == "stopped", rec
        again = FP.preflight(incident(), line_of(("intent-edit", {"device": "r2",
                                                                  "changes": [RENAME]})))
        assert again["steps"][0]["preflight"]["code"] == "repeat", again["steps"][0]
        # Another change is no repeat.
        other = FP.preflight(incident(), line_of(("intent-edit", {"device": "r2",
                                                                  "changes": [V6]})))
        assert other["approvable"], other["why_refused"]

    def test_a_plan_stopped_at_its_deploy_never_closes_the_incident(self, lab, monkeypatch):
        """The correctness review's G7-D1 (2026-11-18; C3812, 003f3292): a plan whose deploy
        step moved at apply (`plan_engine.run`: refused, outcome ``moved``, the plan
        ``stopped``, nothing sent) leaves its committed intent change as the newest attempt
        (a refused step is no attempt), and `verified_fix` closed the incident "verified on r2"
        on it. A plan step closes its incident only when its plan ran to the end, ``done``. A
        real run, its deploy step's record rewritten as the move would leave it."""
        from modules.heal import detect
        from modules.nsot import privileged
        from tests.test_fixit_incident import page_stands_in
        lab["seams"]["verify"] = False
        rec = privileged.get("Lab", run_line(line_of(EDIT, DEPLOY))["id"])
        assert rec["outcome"] == "stopped", rec
        rec["plan_steps"][1].update(state="refused", outcome="moved",
                                    words_said="step 2 moved since the plan was approved")
        privileged.record("Lab", rec)
        got = F.attempts(incident())["attempts"]
        assert [(a["operation"], a["passed"]) for a in got] == [("intent-edit", True)], got
        page_stands_in(monkeypatch, incident())
        assert detect.verified_fix("Lab", {"id": INCIDENT, "device": "r2"}) == {}

    def test_a_plan_whose_deploy_failed_is_never_drawn_passed(self, lab, monkeypatch):
        """The correctness review's G7-D6 (2026-11-18; C3809): every step of one plan run
        carries the run's one start, so its attempts tie on the section's newest-event key, and
        `max` took the first, the intent change that passed: the card read "passed" with the
        deploy failed and the plan stopped. The later step is the newer."""
        from modules.fixit import section
        lab["seams"]["verify"] = False
        rec = run_line(line_of(EDIT, DEPLOY))
        assert rec["outcome"] == "stopped", rec
        monkeypatch.setattr(section, "incident_of", lambda network, found: {
            "incident": incident(), "why": ""})
        got = section.view("Lab", {"found": "page", "id": INCIDENT,
                                   "incident": {"id": INCIDENT, "device": "r2"}})
        assert got["state"] != "passed", (got["state"], got.get("why"))

    def test_a_plan_that_ran_to_its_end_closes_the_incident(self, lab, monkeypatch):
        from modules.heal import detect
        from tests.test_fixit_incident import page_stands_in
        rec = run_line(line_of(EDIT, DEPLOY))
        assert rec["outcome"] == "done", rec
        page_stands_in(monkeypatch, incident())
        got = detect.verified_fix("Lab", {"id": INCIDENT, "device": "r2"})
        assert (got["run"], got["operation"]) == (rec["id"], "intent-deploy"), got

    def test_a_step_refused_before_its_apply_is_no_attempt(self, lab, monkeypatch):
        rec = run_line(line_of(EDIT, DEPLOY), reason="no")
        assert rec["outcome"] == "refused"
        assert F.attempts(incident())["attempts"] == []


# ── The AI's own identity, with its engineer role ───────────────────────────────────────────

# Built at import only where the identity exists, so a parent without it collects this file and
# each test's own body fails there (red-green, C2633), never a collection error.
AI = identity.ai_identity("fixit") if hasattr(identity, "ai_identity") else None


class TestTheAIsRole:
    @pytest.mark.parametrize("action", identity.GATED_ACTIONS)
    def test_no_gated_action_is_the_ais(self, action):
        ok, why = identity.may(AI, action)
        assert not ok and "the engineer role" in why and identity.AI_NEVER[action] in why
        assert identity.may(identity.Identity(actor=PERSON, kind="person", verified=True,
                                              peer_trusted=True, outcome="ok"), action)[0]

    def test_its_identity_is_never_a_verified_persons(self):
        assert AI.actor == "ai:fixit" and identity.is_ai(AI) and identity.is_ai("ai:fixit")
        assert identity.verification_of(AI) == "none"
        assert E.person_refusal(AI.actor, identity.verification_of(AI), True)

    def test_every_settings_and_admin_route_refuses_it(self, monkeypatch):
        """The route gate, before any route's input: a configure route and a template
        approval refused, naming the role."""
        import app as A
        from modules import route_gates
        monkeypatch.setattr(identity, "identify", lambda request: AI)
        client = A.app.test_client()
        for url, endpoint in (("/v2/settings/installation/card/server/save",
                               "settings_v2.install_save"),
                              ("/v2/templates/approve", "templates_v2.approve")):
            assert route_gates.GATES[endpoint].kind in ("configure", "approve")
            got = client.post(url, data={"list": "Default"})
            assert got.status_code == 403, (url, got.status_code)
            body = got.get_json()
            assert body["outcome"] == "ai_role" and "the engineer role" in body["error"]

    def test_a_setting_it_writes_is_refused_naming_the_setting(self, monkeypatch):
        from modules import list_settings, settings_schema
        wrote = []
        monkeypatch.setattr(settings_schema, "save_user_settings", wrote.append)
        got = settings_schema.write_settings({"nsot_git_author_name": "x"}, actor="ai:fixit")
        assert not got["ok"] and got["refused"] == ["nsot_git_author_name"]
        assert "ai:fixit may not change the setting nsot_git_author_name" in got["error"]
        with identity.carried(AI):
            got = settings_schema.write_settings({"nsot_git_author_name": "x"})
            assert not got["ok"] and "the setting nsot_git_author_name" in got["error"]
            got = list_settings.write("Lab", {"nsot_git_author_name": "x"})
            assert not got["ok"] and "nsot_git_author_name of Lab" in got["error"]
        assert wrote == []
        assert settings_schema.write_settings({"nsot_git_author_name": "x"},
                                              actor=PERSON)["ok"]
        assert len(wrote) == 1, "a person's write is the one written"

    def test_an_ai_plan_holding_a_settings_change_is_refused_at_preflight(self, lab,
                                                                          monkeypatch):
        kind = dataclasses.replace(E.STEP_KINDS["intent-deploy"], key="planted-setting",
                                   by_hand="settings_v2.install_save",
                                   words="Change an installation setting")
        monkeypatch.setitem(E.STEP_KINDS, "planted-setting", kind)
        monkeypatch.setattr(E, "FIX_ADMITTED", E.FIX_ADMITTED + ("planted-setting",))
        ai = FP.preflight(incident(), line_of(("planted-setting", {"device": "r2"}), EDIT,
                                              source="ai"))
        assert not ai["approvable"]
        first = ai["steps"][0]["preflight"]
        assert first["code"] == "ai_role" and "never proposes system settings" in \
            first["refused"] and "settings_v2.install_save" in first["refused"], first
        assert ai["steps"][1]["preflight"]["ok"], "an intent change is the AI's to propose"
        mine = FP.preflight(incident(), line_of(("planted-setting", {"device": "r2"})))
        assert mine["steps"][0]["preflight"]["code"] != "ai_role"

    def test_a_template_approval_is_never_the_ais_to_propose(self):
        assert "approving a template" in identity.ai_never_proposes(
            "templates_v2.approve", "approve")
        assert identity.ai_never_proposes("intent_v2.commit", "approve") == ""
        assert identity.ai_never_proposes("device_v2.deploy_confirm", "confirm") == ""
        assert "declares no gate" in identity.ai_never_proposes("v2.nowhere", "")
        assert E.ai_step_refusal("intent-edit") == "" and E.ai_step_refusal("nope") == ""


# ── Every AI entry point acts under the AI's identity ───────────────────────────────────────

class _Stop(Exception):
    """The probe's end: the entry point is not run further."""


def _probe(seen):
    """What an entry point's own code meets once it runs: a settings write, a plan's Approve,
    a re-subscribe's confirm, and who the request's person still is."""
    def probe(*_a, **_kw):
        from modules import settings_schema
        from modules.heal import resubscribe
        seen["write"] = settings_schema.write_settings({"nsot_git_author_name": "x"})
        seen["approve"] = E.person_refusal(PERSON, "access", True)
        seen["confirm"] = resubscribe.person_refusal(PERSON, "access", True)
        seen["acting"] = identity.acting_ai()
        seen["person"] = identity.request_actor()
        raise _Stop()
    return probe


def _call_troubleshoot():
    from modules.ai import fixit_troubleshoot as AIT, triggers
    AIT.troubleshoot("Lab", {}, incident(), actor="job:1", actor_verified="none", person=False,
                     trigger={"kind": triggers.BACKGROUND, "feature": AIT.AUTO_FEATURE})


def _call(module, name, *args, **kw):
    import importlib
    return lambda: getattr(importlib.import_module(module), name)(*args, **kw)


#: Every AI entry point that proposes, with the first seam its own code meets and how it is
#: called: the investigation (heal_notice's automatic, catch-up and planned starts and the
#: person's press all run it), the fix proposal door, the toolbar assistant, Change it in
#: words and the heal analysis.
ENTRIES = {
    "the investigation": ("modules.ai.triggers", "actor_of", "fixit-troubleshoot",
                          _call_troubleshoot),
    "the fix proposal door": ("modules.ai.fix_proposal", "_call_refusal", "fix-proposal",
                              _call("modules.ai.fix_proposal", "for_incident", {}, incident(),
                                    call_id="c1", actor=PERSON, actor_verified="access")),
    "the catalog's proposal door": ("modules.ai.fix_proposal", "_call_refusal", "fix-proposal",
                                    _call("modules.ai.fix_proposal", "proposal", {},
                                          network="Lab", call_id="c1", actor=PERSON,
                                          actor_verified="access")),
    "the toolbar assistant": ("modules.ai.assistant", "prepare", "assistant",
                              _call("modules.ai.assistant", "answer", "what is r2?",
                                    actor=PERSON, trigger={})),
    "Change it in words": ("modules.ai.intent_words", "screen", "intent-words",
                           _call("modules.ai.intent_words", "change", "Lab", "shut Gi2 on r2",
                                 actor=PERSON, trigger={})),
    "the heal analysis": ("modules.ai.heal_analysis", "beta", "heal-analysis",
                          _call("modules.ai.heal_analysis", "analyse", "Lab", INCIDENT,
                                job="job:1")),
}


class TestEveryAIEntryPointActsAsTheAI:
    @pytest.mark.parametrize("which", sorted(ENTRIES))
    def test_under_it_a_setting_an_approve_and_a_confirm_are_refused(self, which,
                                                                     monkeypatch):
        module, seam, feature, call = ENTRIES[which]
        seen = {}
        monkeypatch.setattr(f"{module}.{seam}", _probe(seen))
        with pytest.raises(_Stop):
            call()
        assert seen["acting"] is not None and seen["acting"].actor == f"ai:{feature}"
        assert not seen["write"]["ok"] and (
            f"ai:{feature} may not change the setting nsot_git_author_name"
            in seen["write"]["error"]), seen["write"]
        assert f"ai:{feature} may not approve a plan" in seen["approve"]
        assert f"ai:{feature} may not confirm" in seen["confirm"]
        assert identity.acting_ai() is None, "the AI's identity ends with its entry point"

    def test_the_person_who_pressed_stays_that_person(self, monkeypatch):
        """Inside a request a person's gate verified, the AI's entry point leaves the request's
        person as it is: what it records names them, beside the AI's own identity."""
        import app as A
        person = identity.Identity(actor=PERSON, email=PERSON, kind="person", verified=True,
                                   outcome="ok", peer_trusted=True)
        monkeypatch.setattr(identity, "request_identity", lambda: person)
        seen = {}
        monkeypatch.setattr("modules.ai.assistant.prepare", _probe(seen))
        with A.app.test_request_context("/v2/assistant/ask"):
            with pytest.raises(_Stop):
                ENTRIES["the toolbar assistant"][3]()
        assert seen["person"] == PERSON and seen["acting"].actor == "ai:assistant"

    def test_a_proposal_made_under_it_is_the_ais_beside_the_person(self, lab):
        with identity.as_ai("fixit-troubleshoot"):
            line = F.record_proposal(incident(), "ai", calls=["call-1"], by=PERSON,
                                     verified="access",
                                     steps=[{"operation": "intent-edit",
                                             "params": {"device": "r2", "changes": [RENAME]}}])
        assert line["ai"] == "ai:fixit-troubleshoot" and line["by"] == PERSON
        assert "ai" not in line_of(EDIT)

    def test_each_entry_point_is_declared(self):
        import importlib
        for which, (module, _seam, feature, _call_) in ENTRIES.items():
            mod = importlib.import_module(module if which != "the investigation"
                                          else "modules.ai.fixit_troubleshoot")
            names = {"the investigation": "troubleshoot", "the fix proposal door":
                     "for_incident", "the catalog's proposal door": "proposal",
                     "the toolbar assistant": "answer", "Change it in words": "change",
                     "the heal analysis": "analyse"}
            assert getattr(getattr(mod, names[which]), "acts_as_ai", "") == feature, which


class TestAJobItStartsActsAsTheAI:
    """A job or a fan-out's worker started inside an AI entry point acts as the AI too
    (`identity.ai_carried`, the one helper `capture_job.start` and `fanout` use)."""

    def _start_from_the_entry(self, monkeypatch, start):
        seen, done = {}, []

        def body(*_a):
            from modules import settings_schema
            seen["write"] = settings_schema.write_settings({"nsot_git_author_name": "x"})
            seen["approve"] = E.person_refusal(PERSON, "access", True)
            seen["acting"] = identity.acting_ai()
            done.append(1)
            return {}

        def prepare(*_a, **_kw):
            start(body)
            raise _Stop()
        monkeypatch.setattr("modules.ai.assistant.prepare", prepare)
        with pytest.raises(_Stop):
            ENTRIES["the toolbar assistant"][3]()
        return seen, done

    def test_a_job_it_starts_refuses_a_setting_and_an_approve(self, monkeypatch):
        from modules import troubleshoot_job
        from modules.nsot import capture_job
        jobs = []
        monkeypatch.setattr("modules.settings_schema.save_user_settings", lambda s: None)
        seen, done = self._start_from_the_entry(monkeypatch, lambda body: jobs.append(
            troubleshoot_job.start("Lab", INCIDENT, PERSON, body)))
        capture_job._jobs[jobs[0]]["thread"].join(30)
        assert done == [1], "the job's body ran"
        assert seen["acting"].actor == "ai:assistant"
        assert not seen["write"]["ok"] and "ai:assistant may not change the setting " \
                                           "nsot_git_author_name" in seen["write"]["error"]
        assert "ai:assistant may not approve a plan" in seen["approve"]

    def test_a_fan_outs_workers_act_as_the_ai(self, monkeypatch):
        from modules import fanout
        got = []
        self._start_from_the_entry(monkeypatch, lambda body: got.extend(fanout.read_each(
            lambda _i: identity.acting_ai(), [1, 2, 3])))
        assert [a.actor for a in got] == ["ai:assistant"] * 3

    def test_outside_an_entry_point_a_job_is_no_ais(self):
        from modules.nsot import capture_job
        seen = []
        job = capture_job.start("Lab", "a person's job", PERSON,
                                lambda _j: seen.append(identity.acting_ai()) or {})
        capture_job._jobs[job]["thread"].join(30)
        assert seen == [None]
        assert identity.ai_carried(len) is len


class TestTheAssistantsPlans:
    def test_a_plan_holding_a_step_never_the_ais_is_refused(self, monkeypatch):
        from types import SimpleNamespace

        from modules.ai import assistant
        kind = dataclasses.replace(E.STEP_KINDS["dhcp-reservation"],
                                   by_hand="settings_v2.install_save")
        monkeypatch.setitem(E.STEP_KINDS, "dhcp-reservation", kind)
        ask = SimpleNamespace(plan=SimpleNamespace(plan="dhcp-reservation", params=[
            SimpleNamespace(name="mac", value="aa:c1:ab:5d:20:9e"),
            SimpleNamespace(name="address", value="192.0.2.150"),
            SimpleNamespace(name="hostname", value="h5")]))
        plan, why = assistant.plan_of(ask)
        assert plan is None and "step 1: the AI acts with the engineer role and never " \
                                  "proposes system settings" in why, why
        monkeypatch.setitem(E.STEP_KINDS, "dhcp-reservation", dataclasses.replace(
            kind, by_hand="dhcp_v2.reservation_confirm"))
        plan, why = assistant.plan_of(ask)
        assert plan and plan["plan"] == "dhcp-reservation" and not why, why
