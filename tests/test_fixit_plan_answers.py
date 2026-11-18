"""The AI composes a plan (C3755, C3764; prompts/fixit_troubleshoot.v7.md and v8.md, their
schemas `TroubleshootPlan` and `TroubleshootPlanReads`): its answer is a plan of steps in order,
each a catalog operation, a built-in command plan or the plan engine's intent change or
deploy, with an improvement note beside a clumsy plan; through the one door
(`fix_proposal.plan_for_incident`), the line kept with its steps and preflighted on the page.

On tests/test_fixit_troubleshoot.py's press (the real gateway, the provider stood in), r2's
stopped incident. No device, no network, no AI.

- A plan of one step is proposed and kept with its steps; a plan and a fix, a step outside the
  catalogue, a step on another device and a step on the AI's never-list are each refused, and
  a never-listed kind is refused at the page's preflight too.
- An improvement's shorter route is kept as a second line beside the first; each shape it
  names is held provisional in Mercury's rule for raw lines, proposed by the AI.
- A built-in command plan step's preconditions are read inside the job (`PlanStep.preflight`
  with reads) and kept; one that did not hold refuses the step at the page's preflight.
- The catalogue the prompt is sent lists the command plans and the intent steps, read from
  code, and neither prompt names one; each prompt with the recorded cases' requests fits its
  pin's bound.
"""
import dataclasses
import json

import pytest

from modules.ai import fixit_troubleshoot as FT
from modules.fixit import incident as F
from tests.test_fixit_section_v2 import incident, page  # noqa: F401
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_fixit_troubleshoot import ai, answer, fix, press, sec_of, stopped  # noqa: F401
from tests.test_fixit_troubleshoot import CLOSE
from tests.test_heal_resubscribe import lab  # noqa: F401
from tests.test_sdn_connections import networks  # noqa: F401


def step(operation="telemetry-resubscribe", device="r2", cites=("attempt:1",), **params):
    p = {"device": device, "subscriptions": None, "subscription": None, "interface": None,
         "cause": None, "changes": None, "remove": None}
    if operation == "telemetry-resubscribe" and not params:
        params = {"subscriptions": ["101"]}
    p.update(params)
    return {"operation": operation, "params": p, "why": "it rests on attempt 1.",
            "evidence_refs": list(cites)}


def planned(steps, improvement=None, **kw) -> dict:
    return dict(answer(**kw), plan=list(steps), improvement=improvement)


def lines(iid) -> list:
    return [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]


class TestThePlan:
    def test_a_plan_is_proposed_and_kept_with_its_steps(self, ai):
        iid = stopped(ai)
        # Premise corrected (17215a95's ladder: a re-subscribe of 101 repeats attempt 1 and is
        # refused as tried): the plan is the collector's close, which no attempt makes tried.
        ai.answer = planned([step(CLOSE, subscriptions=["101", "102"])])
        r, html = press(ai, iid)
        assert r.status_code == 200, html
        sec = sec_of(html)
        assert "The AI proposes a plan of 1 step" in sec, sec
        (line,) = lines(iid)
        # Every pass is v18's prompt since v17's one shape (231da1d6; C3918).
        assert line["source"] == "ai" and line["prompt"] == "fixit_troubleshoot.v18"
        assert [s["operation"] for s in line["steps"]] == [CLOSE]

    @pytest.mark.parametrize("ans,why", [
        (lambda: planned([step()], fix=fix()), "a plan and also a fix"),
        (lambda: planned([step(operation="configure terminal")]), "catalog"),
        (lambda: planned([step(device="r6")]), "r6"),
        (lambda: dict(answer(), plan=[], improvement={
            "what": "x", "saves": "y", "steps": [], "shapes": []}), "no plan"),
    ], ids=["a plan and a fix", "a step outside the catalogue", "another device",
            "an improvement with no plan"])
    def test_an_answer_out_of_shape_or_scope_is_refused(self, ai, ans, why):
        iid = stopped(ai)
        ai.answer = ans()
        _r, html = press(ai, iid)
        sec = sec_of(html)
        assert "couldn't be checked" in sec and why in sec, sec
        # Its effect: the line kept with no operation and no step, so nothing is approvable.
        (line,) = lines(iid)
        assert line["operation"] == "" and not line.get("steps"), line

    def test_a_step_on_the_ais_never_list_is_refused(self, ai, monkeypatch):
        from modules import identity
        iid = stopped(ai)
        monkeypatch.setitem(identity.AI_NEVER_ENDPOINTS, "resubscribe_v2.confirm",
                            "a planted settings change")
        ai.answer = planned([step(subscriptions=["101"])])
        _r, html = press(ai, iid)
        assert "never proposes a planted settings change" in sec_of(html)
        (line,) = lines(iid)
        assert line["operation"] == "" and not line.get("steps"), line


class TestTheImprovement:
    def test_the_shorter_route_is_kept_beside_and_its_shapes_held_provisional(self, ai):
        from modules.nsot import command_policy
        iid = stopped(ai)
        shape = "interface {interface} > description x"
        # Premise corrected (17215a95's ladder: a re-subscribe repeats attempt 1 and is refused
        # as tried): the steps are the collector's close, which no attempt makes tried.
        ai.answer = planned([step(CLOSE, subscriptions=["101"]),
                             step(CLOSE, subscriptions=["102"])],
                            improvement={"what": "one close of both", "saves":
                                         "one step and about 2 minutes (attempt 1's run)",
                                         "steps": [step(CLOSE, subscriptions=["101", "102"])],
                                         "shapes": [{"dialect": "cisco_iosxe", "shape": shape,
                                                     "why": "a test"}]})
        _r, html = press(ai, iid)
        assert "A shorter route is proposed beside it" in sec_of(html)
        first, second = lines(iid)
        assert len(first["steps"]) == 2 and len(second["steps"]) == 1
        assert second["shown"]["alternative_of"] == first["proposal"]
        rec = command_policy.read_store(NET_OF(iid))["shapes"]["cisco_iosxe: " + shape]
        assert rec["state"] == "provisional" and rec["proposed_by"].startswith("the AI")
        assert not command_policy.check("cisco_iosxe", ["interface {interface}",
                                                        " description x"],
                                        ("interface",), network=NET_OF(iid))["ok"]


def NET_OF(_iid):
    from tests.test_fixit_section_v2 import NET
    return NET


class TestTheCommandPlanStep:
    def test_its_preconditions_are_read_in_the_job_and_refuse_at_the_page(self, ai,
                                                                          monkeypatch):
        from modules.heal import catalog
        iid = stopped(ai)
        asked = []

        # Premise corrected (5653c025, the operator, 2026-11-16: the plan's preconditions read
        # with the investigation's own reads reused): the step's preflight is asked with the
        # incident and the job's reuse too (`fix_proposal._command_plan_reads`).
        def preflight(network, params, *, reads=False, sources=None, incident="", reuse=None):
            asked.append((network, dict(params), reads))
            return {"ok": False, "refused": "the port is not err-disabled now", "drawn": {},
                    "hash": ""}
        key = "errdisable-recover"
        monkeypatch.setitem(catalog.COMMAND_PLANS, key, dataclasses.replace(
            catalog.COMMAND_PLANS[key], preflight=preflight))
        ai.answer = planned([step(operation=key, interface="Gi1/0", cause="bpduguard")])
        press(ai, iid)
        assert [a[2] for a in asked] == [True], "read once, with reads, inside the job"
        (line,) = lines(iid)
        assert line["shown"]["preconditions_read"]["1"]["ok"] is False
        sec = sec_of(page(ai.client, iid)[1])
        assert "/fixit/approve" not in sec, "a step whose preconditions failed is not approvable"
        # The page's preflight refuses it for its kept read, even where every other check of
        # the step passes (here stood in: r2 holds no err-disabled port to pass them).
        from modules.fixit import plan as FP
        monkeypatch.setattr(FP, "_check_one", lambda *a, **k: {
            "ok": True, "hash": "h", "drawn": {}, "refused": "", "code": "", "repeat": {}})
        got = FP.preflight(incident(iid), line)
        assert not got["approvable"] and got["steps"][0]["preflight"]["code"] == "preconditions"
        assert "the port is not err-disabled now" in got["steps"][0]["preflight"]["refused"]


class TestWhatIsSent:
    def test_the_catalogue_lists_plans_and_intent_steps_from_code(self, ai):
        from modules.ai import prompts
        iid = stopped(ai)
        ai.answer = planned([step(subscriptions=["101"])])
        press(ai, iid)
        system = json.dumps(ai.sent[0]["system"])
        # Premise corrected (the gate's measurement, 2026-11-15): the catalogue sent is the
        # steps this incident's device can take (`payload.catalogue_part` with the incident):
        # r2's lost stream gets the telemetry operations and the intent steps, and the
        # err-disable plan, which fixes no lost stream, only where its problem is an
        # err-disabled port (tests/test_fixit_first_run.py, s1's request).
        for key in ("telemetry-resubscribe", "intent-edit", "intent-deploy"):
            assert key in system, key
        assert "errdisable-recover" not in system
        for v in (7, 8):
            text = prompts.load(FT.FEATURE, v)["text"]
            assert "errdisable" not in text and "intent-edit" not in text, v

    @pytest.mark.parametrize("reads_on", [False, True], ids=["plain pass v7", "reads pass v8"])
    def test_each_prompt_fits_its_pins_bound(self, ai, monkeypatch, reads_on):
        """The body each pass sends, by the gateway's fallback over-estimate, within the pin's
        bound (the recorded cases hold no pack yet, so the press's own request is measured)."""
        from modules.ai import gateway, profiles
        from modules.ai import read_loop as RL
        if reads_on:
            monkeypatch.setattr(RL, "reads_off", lambda *a, **k: "")
        iid = stopped(ai)
        ai.answer = dict(planned([step(subscriptions=["101"])]), **(
            {"reads": []} if reads_on else {}))
        press(ai, iid)
        (body,) = ai.sent
        bound = profiles.TASKS[FT.FEATURE]["max_prompt_tokens"]
        want = FT.PROMPT_PLAN_READS if reads_on else FT.PROMPT_PLAN
        assert prompts_text(want) in json.dumps(body["system"]), "the pass's own prompt"
        assert gateway.prompt_tokens(body) <= bound, (gateway.prompt_tokens(body), bound)


def prompts_text(prompt) -> str:
    from modules.ai import prompts
    return json.dumps(prompts.load(*prompt)["text"])[1:-1][:200]
