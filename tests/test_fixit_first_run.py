"""The first real run of automatic troubleshooting (the operator's findings, 2026-11-15).

- **Each investigation is its own call (C3771):** the turn-on's catch-up started four
  investigations under one press key, each in its own job; r7's, s1's and r4's first calls
  each "joined call ai-2c349452c6004b2c: the same press sent again: its key was seen", s2's, so
  s1's incident showed s2's evidence. Here four incidents started by one turn-on, each job in
  its own thread as the host's job runner runs it, make four provider requests, each answered
  from its own request and checked against its own pack, and no answer is shown on another
  incident. Beside it, the press's own rule (`presses.once`): one press's calls about two
  subjects never share a slot, and a slot naming a call about another subject is never joined.
- **The AI composes a plan for s1's err-disabled port (C3755, C3764):** on the real shape of
  s1's incident hi-e56afd12e1a6 (Gi1/0 err-disabled by BPDU guard, classified from s1's
  captured lines, tests/fixtures/errdisable/), a model answering with the built-in err-disable
  command plan and its typed parameters is accepted and proposed as a plan, not a gap; a model
  answering with a gap for it is flagged, Mercury having that plan.
- **The estimate takes the first measured calls as measured (E):** s2's two calls on the host,
  $0.042098 (v5, the reads pass, 2026-11-15T07:13:52Z) and $0.029486 (v6, the second pass,
  07:14:12Z), as the operator read them from the record of AI calls; the three joins beside
  them (cost 0, no tokens) are not calls the provider billed.

Through tests/test_fixit_troubleshoot.py's world (the real app and gateway, the provider stood
in). No device, no network, no live AI.
"""
import datetime
import json
import re
import threading

import pytest

from modules.ai import calls, presses
from tests.conftest import TEST_PERSON
from tests.test_fixit_catch_up import BASE, LISTED, form_of, planted, world  # noqa: F401
from tests.test_fixit_section_v2 import NET
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_fixit_troubleshoot import CONFIRM, ai  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import DEV
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

#: The press key the turn-on was posted with: one key for the whole press, as the page sends.
KEY = "k" * 32


def own_answer(body: dict, plan=None, gap=None) -> dict:
    """An answer made from *body*'s own request: its rationale names the request's device and
    each claim cites a reference the request's own pack holds (its incident section's first
    piece), so an answer checked against another pack, or shown on another incident, says so."""
    text = json.dumps(body["messages"])
    device = re.search(r'name=\\"the_incident\\">\\n.*?\b([rs]\d+)\b', text).group(1)
    ref = re.search(r'\\"ref\\":\\"(incident:\d+)\\"', text).group(1)
    return {"outcome": "answer", "rationale": f"{device}'s own incident, from its own pack.",
            "hypotheses": [{"claim": f"{device}'s incident holds what this rests on.",
                            "evidence_refs": [ref], "confirm_with": CONFIRM}],
            "fix": None, "gap": gap, "needs_human": True, "why_not": "",
            "plan": plan or [], "improvement": None}


def provider(ai, monkeypatch, make=own_answer):  # noqa: F811
    from modules.ai import anthropic_adapter as AD
    from modules.ai import gateway

    def send(body, key, **_kw):
        ai.sent.append(body)
        return AD.Reply(status=200, body={
            "content": [{"type": "text", "text": json.dumps(make(body))}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 9000, "output_tokens": 600}},
            attempts=1, latency_s=0.2)
    monkeypatch.setattr(gateway.anthropic_adapter, "send", send)


# ── C3771: four investigations, four calls ──────────────────────────────────────────────────

class TestEachInvestigationIsItsOwnCall:
    @pytest.fixture
    def threaded(self, monkeypatch):
        """Each investigation's job runs in its own thread, one after the other (the host's
        job runner gives each its own thread; `web` runs them in the request's)."""
        def job(lst, label, actor, work, **kw):
            t = threading.Thread(target=work, args=("j-1",))
            t.start()
            t.join(60)
            return "j-1"
        monkeypatch.setattr("modules.nsot.capture_job.start", job)

    def test_four_incidents_started_by_one_turn_on_make_four_calls_each_its_own(
            self, world, monkeypatch, threaded):  # noqa: F811
        from modules import incident_page
        from modules.fixit import incident as F
        from modules.fixit import section as S
        provider(world, monkeypatch)
        got = planted()
        ticked = [got[k] for k in LISTED]
        _html, shown, each = form_of(world)
        # Gate 2 (C3769): turned on the one way, the limits acknowledged then the control
        # strip's switch pressed, bound to its line; every listed incident starts.
        from modules import troubleshoot_control as troubleshoot
        from modules.ai import background
        est = background.estimate(background._network(NET), "fixit_auto")
        # A day limit four investigations fit under: each one's worst case is four calls since
        # C3797 ($0.5004), so four plan $2.0016 against it, which $1.50 refused after two (the
        # feature's day limit within the installation's day cap, raised with it).
        from modules.settings_schema import write_settings
        assert write_settings({"ai_cap_usd_per_day": 2.50})["ok"]
        troubleshoot.set_limits(NET, incident_usd=1.0, day_usd=2.5, month_usd=10.0,
                                shown=est["digest"], accepted=True,
                                actor=TEST_PERSON, verified="access")
        r = world.client.post(
            f"/v2/settings/installation/ai/troubleshoot/{NET}/level?answer=strip",
            data={"level": "automatic", "line_digest": shown},
            headers={"HX-Request": "true", presses.HEADER: KEY})
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        rows = [x for x in calls.read()["rows"] if x.get("feature") == "fixit_troubleshoot"]
        # Premise corrected (C3872, 7d54cf24, the operator, 2026-11-16: "a refused start spends
        # no key"): the catch-up's list holds five, the incident whose automatic start a cap
        # refused among them (tests/test_fixit_catch_up.py's LISTED), so five investigations,
        # each its own request, where four were listed.
        assert len(ticked) == 5
        assert len(world.sent) == len(ticked), "one provider request an investigation"
        assert not [x for x in rows if x.get("verdict") == calls.JOINED], "no join"
        assert len({x["id"] for x in rows}) == len(ticked)
        by_id = {x["id"]: x for x in rows}
        for iid in ticked:
            inc = S.incident_of(NET, incident_page.resolve(NET, iid))["incident"]
            (line,) = [ln for ln in F.read(inc)["lines"] if "proposal" in ln]
            # Answered from its own request, checked against its own pack: nothing marked.
            assert line["shown"]["rationale"].startswith(f"{inc.device}'s own incident"), line
            assert not any(h["unverified_words"] for h in line["shown"]["hypotheses"])
            # And never shown on another incident: each call it shows is about it.
            assert line["calls"] and all(by_id[c]["subject"]["id"] == iid
                                         for c in line["calls"]), (iid, line["calls"])


class TestThePressKeyNamesItsSubject:
    """`presses.once` itself: one press (one key, one request), two subjects."""

    @pytest.fixture
    def once(self, tmp_path, monkeypatch):
        import app as A
        from flask import g
        monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
        made = []

        def call(subject, *, fresh_thread=False):
            if fresh_thread:
                g.pop("nmas_ai_press_n", None)     # a job's own thread counts from 1 again

            def make():
                row = calls.record({"id": calls.new_id(), "feature": "f", "verdict": "ok",
                                    "subject": subject, "cost_usd": 0.01})
                made.append(row["id"])
                return {"ok": True, "call_id": row["id"]}
            return presses.once("f", {"b": 1}, about={
                "network": "n", "subject": subject, "prompt": "p.v1", "model": "m",
                "scope": "s"}, actor=TEST_PERSON, make=make,
                rebuild=lambda row, why: {"ok": True, "call_id": row["id"], "why": why},
                refuse=lambda kind, why: {"ok": False, "error": kind}, wait_s=1.0)
        with A.app.test_request_context("/x", method="POST", headers={presses.HEADER: KEY}):
            yield call, made

    def test_two_subjects_under_one_key_are_two_calls(self, once):
        call, made = once
        a = call({"kind": "heal_incident", "id": "hi-a"})
        b = call({"kind": "heal_incident", "id": "hi-b"}, fresh_thread=True)
        assert len(made) == 2 and a["call_id"] != b["call_id"] and "joined" not in b

    def test_each_subject_keeps_its_own_slot(self, once):
        """hi-a, hi-b, then hi-a's press sent again: joined to hi-a's own call, never a third
        call (one slot for both would name hi-b's call, which hi-a cannot join)."""
        call, made = once
        a = call({"kind": "heal_incident", "id": "hi-a"})
        call({"kind": "heal_incident", "id": "hi-b"}, fresh_thread=True)
        again = call({"kind": "heal_incident", "id": "hi-a"}, fresh_thread=True)
        assert len(made) == 2 and again["joined"] == a["call_id"]

    def test_two_works_of_one_press_on_one_subject_are_two_calls(self, once):
        """The work a press's calls are for (`presses.within`: an investigation's incident and
        failure) is in the slot: two works, two calls."""
        call, made = once
        subject = {"kind": "heal_incident", "id": "hi-a"}
        with presses.within("hi-a:decision:1"):
            first = call(subject)
        with presses.within("hi-a:decision:2"):
            second = call(subject)
        assert len(made) == 2 and "joined" not in second and first != second

    def test_the_same_subject_sent_again_is_still_joined(self, once):
        call, made = once
        a = call({"kind": "heal_incident", "id": "hi-a"})
        again = call({"kind": "heal_incident", "id": "hi-a"}, fresh_thread=True)
        assert len(made) == 1 and again["joined"] == a["call_id"]

    def test_a_slot_naming_a_call_about_another_subject_is_never_joined(self, once):
        from flask import g
        call, made = once
        a = call({"kind": "heal_incident", "id": "hi-a"})
        # The slot hi-b's first call would take, marked done with hi-a's call (a marker an
        # earlier release wrote, or any slot that came to name another subject's call).
        g.pop("nmas_ai_press_n", None)
        slot = presses.current_press(TEST_PERSON)["slot"]
        sub = presses.subject_key({"kind": "heal_incident", "id": "hi-b"})
        presses._Slot("key-" + presses._sha(slot, sub)).mark(  # noqa: SLF001
            state="done", call_id=a["call_id"], scope="s")
        b = call({"kind": "heal_incident", "id": "hi-b"}, fresh_thread=True)
        assert len(made) == 2 and "joined" not in b, "its own call, never hi-a's answer"


# ── C3755, C3764: s1's err-disabled port, a plan, never a gap ──────────────────────────────

S1 = {"hostname": "s1", "ip": "192.0.2.11", "device_type": "cisco_ios"}
#: The built-in err-disable command plan as a plan step, its typed parameters as the model
#: gives them (`fixit_troubleshoot.StepParams`).
RECOVER = {"operation": "errdisable-recover",
           "params": {"device": "s1", "interface": "Gi1/0", "cause": "bpduguard",
                      "subscriptions": None, "subscription": None, "changes": None,
                      "remove": None},
           "why": "Gi1/0 is err-disabled by BPDU guard and its cause has cleared.",
           "evidence_refs": []}


class TestTheErrDisabledPort:
    @pytest.fixture
    def s1(self, ai, monkeypatch):  # noqa: F811
        """s1's incident as hi-e56afd12e1a6 stood on the host: opened from "Critical syslog
        received" and "Interface down" on Gi1/0, classified from s1's captured lines (BPDU guard,
        Gi1/0, h1) and confirmed by its captured device read (`errdisable.reclassify_step`, the
        detect loop's own step), in `ai`'s world with s1 in the inventory; the command plan's
        preconditions read stood in (recorded), so no device is read."""
        import dataclasses

        from modules.fixit import section
        from modules.heal import catalog
        try:
            from tests import test_errdisable as T
        except ImportError:
            # A parent without the err-disable problem: no incident to stand, so each test's
            # own body fails there (red-green reads its body, never a setup error, C2633).
            return None
        rows = [dict(DEV, _netbox_id=7), dict(S1, _netbox_id=11)]
        monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: list(rows))
        real = section._identity                    # noqa: SLF001
        monkeypatch.setattr(section, "_identity", lambda network, device: (
            real(network, device) if device == "r2" else f"uid:{device}-0001"))
        iid = T.opened("Critical syslog received")["incident"]
        T.opened("Interface down", "GigabitEthernet1/0", at=T.AT + 20)
        assert T.E.reclassify_step(NET, sources=T.Src(), now=T.AT + 600)["classified"] == [iid]
        asked = []

        # Premise corrected (5653c025, the operator, 2026-11-16: the plan's preconditions read
        # with the investigation's own reads reused): the step's preflight is asked with the
        # incident and the job's reuse too (`fix_proposal._command_plan_reads`).
        def preflight(network, params, *, reads=False, sources=None, incident="", reuse=None):
            asked.append(dict(params))
            return {"ok": True, "refused": "", "drawn": {}, "hash": "h-recover"}
        monkeypatch.setitem(catalog.COMMAND_PLANS, RECOVER["operation"], dataclasses.replace(
            catalog.COMMAND_PLANS[RECOVER["operation"]], preflight=preflight))
        ai.iid, ai.asked = iid, asked
        return ai

    @staticmethod
    def investigate(w, monkeypatch, make):
        """The troubleshoot path (`fixit_troubleshoot.troubleshoot`, a verified person's press
        in a request) on s1's incident, the provider answering *make(body)*."""
        import app as A
        from modules import incident_page
        from modules.ai import fixit_troubleshoot as AIT
        from modules.fixit import section
        provider(w, monkeypatch, make)
        found = incident_page.resolve(NET, w.iid)
        inc = section.incident_of(NET, found)["incident"]
        with A.app.test_request_context("/x", method="POST"):
            return AIT.troubleshoot(NET, found, inc, actor=TEST_PERSON, actor_verified="access",
                                    person=True), found

    def test_its_shape_is_s1s_err_disabled_port(self, s1, monkeypatch):
        from modules import incident_page, problem
        p = problem.classify(incident_page.resolve(NET, s1.iid))
        assert (p.device, p.condition, p.cause) == ("s1", "err_disabled", "BPDU guard")

    def test_a_composed_plan_of_the_built_in_command_plan_is_proposed_not_a_gap(
            self, s1, monkeypatch):
        from modules.ai import missing

        def make(body):
            a = own_answer(body)
            step = dict(RECOVER, evidence_refs=list(a["hypotheses"][0]["evidence_refs"]))
            return dict(a, plan=[step])
        got, _found = self.investigate(s1, monkeypatch, make)
        assert got["state"] == "proposed", got["words"]
        assert got["words"].startswith("The AI proposes a plan of 1 step")
        # The catalogue it was sent offers the err-disable plan (s1's problem is an
        # err-disabled port) and no telemetry operation (s1's incident names no subscription).
        system = json.dumps(s1.sent[0]["system"])
        assert "errdisable-recover" in system and "telemetry-resubscribe" not in system
        (step,) = got["proposal"]["steps"]
        assert step["operation"] == "errdisable-recover"
        assert s1.asked == [{"device": "s1", "interface": "Gi1/0", "cause": "bpduguard"}], \
            "its typed parameters, read once in the job"
        assert missing.for_incident(s1.iid) == [], "no missing capability recorded"

    def test_a_gap_for_it_is_flagged_mercury_having_the_plan(self, s1, monkeypatch):
        from modules.ai import missing
        gap = {"what": "no operation recovers an err-disabled port", "evidence_refs": []}

        def make(body):
            a = own_answer(body)
            return dict(a, gap=dict(gap, evidence_refs=a["hypotheses"][0]["evidence_refs"]))
        got, _found = self.investigate(s1, monkeypatch, make)
        assert got["state"] == "gap" and got["overlooked"] == ["errdisable-recover"]
        assert "Mercury's check flags it" in got["words"] and "errdisable-recover" in got["words"]
        assert got["shown"]["gap_overlooked"]
        (row,) = missing.for_incident(s1.iid)
        assert row["overlooked"] == ["errdisable-recover"], "the row says a plan exists"

    def test_it_reads_the_err_disable_status_confirms_bpduguard_and_proposes_the_plan(
            self, s1, monkeypatch):
        """C3797 (the operator, 2026-11-15: "Test with this incident shape: the AI reads
        err-disable status, confirms bpduguard and the cause cleared, and proposes the recovery
        plan"): the investigation's first pass asks for s1's err-disable status and its
        errdisable recovery; Mercury runs them (the read engine stood in by s1's own answers,
        measured on the host that day through it, run 20261115T192414088169Z-8ebe...); the next
        pass sees both, cites them, asks for nothing more, and proposes the built-in recovery
        plan, whose preconditions (the port err-disabled by the cause, the switch not
        recovering it itself, the cause cleared) the plan reads again before it runs."""
        from modules.ai import read_loop as RL
        from modules.ai import router_reads as RR
        from modules.nsot import command_plan as CP
        from tests.test_fixit_preview import _class
        _class(monkeypatch, True)
        monkeypatch.setattr(RR, "_committed", lambda network, hosts: (
            {h: {} for h in hosts}, {h: "interface GigabitEthernet1/0\n" for h in hosts}))
        monkeypatch.setattr(RR, "read_accounts", lambda network, hosts: {h: (True, "")
                                                                         for h in hosts})
        answers = {"show interfaces status err-disabled": S1_ERRDISABLED,
                   "show errdisable recovery": S1_RECOVERY}
        ran = []

        def device(op, args, requests, scope):
            ran.append(tuple(requests))
            return RL.Answered("\n".join(answers[r] for r in requests), run="run-s1")
        monkeypatch.setattr(RR, "run", device)
        # Premise corrected (4a8bb0df, 231da1d6: one device's reads in a round share one
        # session, the family's `run_many`, bound to `router_reads.run_many` when the family is
        # defined): the read engine's stand-in answers that path too, each read as `run` does,
        # where s1's two reads went past it to the engine.
        import dataclasses

        from modules.ai import fixit_reads as FR
        monkeypatch.setattr(FR, "FAMILY", dataclasses.replace(FR.FAMILY, run_many=lambda items,
                            scope: [device(op, a, reqs, scope) for op, a, reqs in items]))
        passes = []

        def make(body):
            a = own_answer(body)
            text = json.dumps(body["messages"])
            passes.append("mercury_reads" in text)
            if "mercury_reads" not in text:
                return dict(a, reads=[
                    {"op": "show", "args": {"device": "s1", "subscription": "",
                                            "words": w},
                     "why": "is the port err-disabled, and by what",
                     "hypothesis": "BPDU guard shut Gi1/0"}
                    for w in ("interfaces status err-disabled", "errdisable recovery")])
            assert "err-disabled bpduguard" in text and "bpduguard" in text
            step = dict(RECOVER, evidence_refs=["read:1", "read:2"])
            return dict(a, plan=[step], reads=[])
        got, _found = self.investigate(s1, monkeypatch, make)
        # Premise corrected (5653c025, the operator, 2026-11-16: "runs the standard reads at
        # once"; "the pre-gathered reads must answer it in ONE call"): an err-disabled port's
        # standard reads (`fixit_troubleshoot.PREGATHER`) run beside pass 1's build, so the one
        # pass sees both and proposes, where a first pass asked for them and a second saw them.
        assert passes == [True], "one pass, which saw the reads"
        assert ran == [("show interfaces status err-disabled",), ("show errdisable recovery",)]
        assert got["state"] == "proposed", got["words"]
        (step,) = got["proposal"]["steps"]
        assert step["operation"] == "errdisable-recover"
        assert s1.asked == [{"device": "s1", "interface": "Gi1/0", "cause": "bpduguard"}]
        assert [p["name"] for p in CP.template_of("errdisable-recover").preconditions] == [
            "The port is err-disabled by the cause now",
            "The switch does not recover the cause itself", "The cause has cleared"], \
            "the plan reads its preconditions again before it runs"
        (line,) = [ln for ln in __import__("modules.fixit.incident", fromlist=["read"]).read(
            __import__("modules.fixit.section", fromlist=["x"]).incident_of(
                NET, __import__("modules.incident_page", fromlist=["x"]).resolve(
                    NET, s1.iid))["incident"])["lines"] if "proposal" in ln]
        # Every pass is one prompt since v17's one shape (231da1d6; C3918's v18), where the
        # later pass's was v12.
        assert line["prompt"] == "fixit_troubleshoot.v18", "the answer is the one pass's"

    def test_with_no_read_to_settle_it_it_names_the_read_it_lacked(self, s1, monkeypatch):
        """C3797: it declines a plan only when its reads cannot settle the question, naming the
        read it lacked; the card keeps it for "How to fix it"."""
        from tests.test_fixit_preview import _class
        _class(monkeypatch, False)                # no device read: the plain pass alone

        def make(body):
            return dict(own_answer(body), lacked_read="show port-security interface Gi1/0")
        got, _found = self.investigate(s1, monkeypatch, make)
        assert got["shown"]["lacked_read"] == "show port-security interface Gi1/0"


#: s1's own answers through Mercury's read engine, 2026-11-15 19:24 UTC (run
#: 20261115T192414088169Z-8ebe93e8575e41a28630932247a04928), as captured.
S1_ERRDISABLED = ("\nPort      Name               Status       Reason               "
                  "Err-disabled Vlans\nGi1/0     h1 - VLAN 10       err-disabled bpduguard")
S1_RECOVERY = ("ErrDisable Reason            Timer Status\n"
               "-----------------            --------------\n"
               "arp-inspection               Disabled\n"
               "bpduguard                    Disabled\n"
               "psecure-violation            Disabled\n\n"
               "Timer interval: 300 seconds\n\n"
               "Interfaces that will be enabled at the next timeout:")


# ── E: the first measured calls ─────────────────────────────────────────────────────────────

#: s2's two calls at the first real run, as the operator read them from the host's record of AI
#: calls (2026-11-15): the time, the prompt and the cost each are the measurement; the ids and
#: the token counts are stand-ins (a sent row carries its tokens; their values were not read).
FIRST_RUN = (("2026-11-15T07:13:52Z", "fixit_troubleshoot.v5", 0.042098),
             ("2026-11-15T07:14:12Z", "fixit_troubleshoot.v6", 0.029486))
#: The three joins of that run (r7's, s1's and r4's): cost 0, no tokens.
JOINS = ("2026-11-15T07:13:53Z", "2026-11-15T07:13:54Z", "2026-11-15T07:13:55Z")
#: When the estimate is read: that morning, after the run.
AFTER = datetime.datetime(2026, 11, 15, 8, 20, tzinfo=datetime.timezone.utc)


def test_the_estimate_takes_the_first_measured_calls_as_measured(ai, monkeypatch):  # noqa: F811
    from modules.ai import background, profiles
    from modules.ai import fixit_troubleshoot as AIT
    model = profiles.TASKS["fixit_troubleshoot"]["model"]
    for n, (at, prompt, usd) in enumerate(FIRST_RUN):
        calls.record({"id": f"ai-first-run-{n}", "feature": "fixit_troubleshoot", "at": at,
                      "model": model, "prompt": prompt, "verdict": "ok", "cost_usd": usd,
                      "tokens": {"input_tokens": 1, "output_tokens": 1}})
    for n, at in enumerate(JOINS):
        calls.record({"id": f"ai-join-{n}", "feature": "fixit_troubleshoot", "at": at,
                      "model": model, "verdict": calls.JOINED, "cost_usd": 0.0,
                      "joined": "ai-first-run-0"})
    got = background.measured_cost("fixit_troubleshoot", now=AFTER)
    assert got["measured"] is True and got["calls"] == 2, got
    assert got["usd_per_call"] == pytest.approx((0.042098 + 0.029486) / 2)     # $0.035792
    # The estimate drawn before a press reads the record's last 30 days from the record's own
    # clock (`calls._now`): that morning's.
    monkeypatch.setattr(calls, "_now", lambda: AFTER)
    est = AIT.estimate()
    # The calls one investigation is expected to make, three since C3797 (it may ask again).
    # Premise corrected (7b0bb884, the operator, 2026-11-16: no worst case): beside it the
    # least one call costs (`start_usd`, the figure a start is held to), where its worst case,
    # four calls at the pin's per-call cap, was.
    assert est["measured"] is True and est["usd"] == pytest.approx(3 * 0.035792), est
    assert "worst" not in est
    assert est["least"] == pytest.approx(AIT.start_usd())
