"""AI troubleshooting's own call (`modules/ai/fixit_troubleshoot.py`, `routes/fixit_v2.py`
``troubleshoot``, `modules/ai/fix_proposal.for_incident`; the fix-it plan's S5; board
recurring-fixes v2, steps 2 and 3; docs/HEAL_TO_INTENT.md section 12, "The AI call (S5)"),
through the real app and the REAL gateway on tests/test_fixit_section_v2.py's lab (r2's real
configuration and intent, a self-healing incident opened by the incidents store's own writer
from two lost-stream alerts, attempt 1 a real Re-subscribe run that read no data). Only the
provider is replaced: every request is counted and answered with what the test sets. No device,
no network, no live AI call. The answers are stand-ins written for each case (no capture of a
model's answer exists yet: the fix-it plan's S7 records them), each shaped by the schema the
gateway sends.

- **The operator's test 1 ("no path retries without a person"), through the gateway:** the
  press is the call's trigger (a person's, the request's verified actor); no background feature
  is registered for it; the incident page, loaded and refreshed, asks no model; an unverified
  press, a resolved incident and the mode off are refused with no provider request.
- **Test 2 ("the cap refuses"):** past the per-incident cap the press is refused naming both
  figures, with no provider request and nothing recorded; the figure drawn before the press is
  the one the route compares.
- **Test 4 ("a repeated proposal is flagged"):** an answer repeating attempt 1 is drawn flagged,
  and opens the operation's own card.
- **The answer checked:** a subscription the incident does not name, another device, a command
  where a parameter goes, and a fix and a gap together are each refused as unchecked, the spend
  counted and the refusal recorded on the call (a citation not in what was sent, a past incident
  Seen before did not send among them, is marked instead: tests/test_fixit_unverified.py); a gap
  has no Approve; the evidence that cannot say, and an answer naming no fix, each say so.
- **The note:** a typed part, masked as it leaves and said; it never widens what a fix may act
  on.
- **One press, one call:** a second request with the same press key makes no second request.
- **The pack:** Seen before from Mercury's record, IPv4 and IPv6 addresses as written.
"""
import json
import types

import pytest

from modules.ai import calls, gateway
from modules.fixit import incident as F
from tests.test_fixit_section_v2 import (NET, attempt, incident, page, plant, post,
                                         section_of)
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

KEY = "sk-ant-planted-for-the-test"
ADMIN = "admin@example.com"
REAL_ASK = gateway.ask
CONFIRM = "show telemetry ietf subscription all"


def answer(fix=None, gap=None, *, cites=("attempt:1",), outcome="answer", why_not="",
           rationale="r2's streams stayed down after attempt 1 re-subscribed them.",
           hypotheses=None) -> dict:
    """An answer of the schema's shape (`fixit_troubleshoot.Troubleshoot`): a stand-in."""
    hyps = hypotheses if hypotheses is not None else [
        {"claim": "The collector still holds r2's old session, so no new one opens.",
         "evidence_refs": list(cites), "confirm_with": CONFIRM}]
    return {"outcome": outcome, "rationale": rationale, "hypotheses": hyps, "fix": fix,
            "gap": gap, "needs_human": True, "why_not": why_not}


def fix(operation="telemetry-resubscribe", device="r2", subscriptions=("101", "102"),
        subscription=None, cites=("attempt:1",)) -> dict:
    return {"operation": operation,
            "params": {"device": device,
                       "subscriptions": list(subscriptions) if subscriptions is not None
                       else None, "subscription": subscription},
            "why": "Re-subscribing opens a new session once the old one is gone.",
            "evidence_refs": list(cites)}


#: A fix the lost stream's ladder lets the AI propose after attempt 1's failed re-subscribe
#: (17215a95, the operator, 2026-11-16: "The AI never proposes a step whose equivalent already
#: failed on the incident ... It proposes the first untried rung"; `fixit.ladder`): the
#: collector's close, which resets nothing of the device's side, so no attempt makes it tried.
#: A stand-in where a case is about something other than the ladder (a check, a citation, a
#: guard); `fix()`'s re-subscribe repeats attempt 1 and is refused by the ladder.
CLOSE = "telemetry-collector-close"
#: The least one AI call of the investigation costs before any is measured (7b0bb884:
#: `fixit_troubleshoot.start_usd`, the pin's stand-in typical output at its output rate), the
#: one figure the per-incident cap compares, and a cap under it.
LEAST = "$0.0576"
UNDER_THE_LEAST = 0.02


@pytest.fixture
def ai(web, monkeypatch, tmp_path):  # noqa: F811
    """`web` with the REAL gateway (the fixture's stand-in that refuses every ask put back),
    hosted AI allowed with a $1.50 day cap and a key, the record of AI calls in the test's
    folder, no topology sent (no network model in a test's folder), and the provider replaced:
    each request kept in ``ai.sent`` and answered with ``ai.answer``."""
    from modules import installation_settings as I
    from modules.ai import explain
    from modules.settings_schema import write_settings

    monkeypatch.setattr(gateway, "ask", REAL_ASK)
    monkeypatch.setattr(I, "_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    # The AI control's own readiness asks the secrets store whether a key is stored (presence
    # only): the same key, said stored.
    monkeypatch.setattr("modules.ai.controls._key_set", lambda: True)
    assert write_settings({"ai_hosted": {"by": ADMIN, "at": "2026-11-12T00:00:00Z",
                                         "reason": "the lab's AI troubleshooting"},
                           "ai_cap_usd_per_day": 1.50})["ok"]
    monkeypatch.setattr(explain, "topology", lambda pack: {
        "sent": False, "why": "no network model in the test", "summary": "", "yaml": "",
        "ids": [], "reached": {}, "version": "", "subject": pack.get("device") or "",
        "network": pack.get("network") or "", "observed": "", "names": {}, "as_now": ""})
    w = types.SimpleNamespace(sent=[], answer=answer(), client=web)
    from modules.ai import anthropic_adapter as AD

    def send(body, key, **_kw):
        w.sent.append(body)
        return AD.Reply(status=200, body={
            "content": [{"type": "text", "text": json.dumps(w.answer)}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 9000, "output_tokens": 600}},
            attempts=1, latency_s=0.2)

    def count(body, key, **kw):
        raise AD.ProviderDown("no count in a test")
    monkeypatch.setattr(gateway, "anthropic_adapter", types.SimpleNamespace(
        **{**vars(AD), "send": send, "count_tokens": count}))
    return w


def press(w, iid, note="", **data):
    r = post(w.client, iid, "start", text=note, **data)
    return r, r.get_data(as_text=True)


def data_of(body: dict) -> str:
    return body["messages"][0]["content"]


def sec_of(html: str) -> str:
    """The section's HTML with its entities read (the words as a person reads them)."""
    from html import unescape
    return unescape(section_of(html))


def stopped(w):
    """The incident with attempt 1 failed: the STOP state. Its id."""
    iid = plant()
    attempt(w.client)
    return iid


# ── The press and its one investigation ─────────────────────────────────────────────────────

class TestThePress:
    def test_one_press_asks_once_and_proposes_a_checked_fix_flagged_as_a_repeat(self, ai):
        """Premise corrected again (17215a95, the operator, 2026-11-16: "The AI never proposes
        a step whose equivalent already failed on the incident: three re-subscribes already
        removed and re-added r7's receivers, so 're-add the receiver' counts as tried. It
        proposes the first untried rung"): the AI's answer repeating attempt 1 is no longer
        kept, flagged and refused at its preflight (a person's and Mercury's proposals keep the
        repeat flag alone, `fixit.ladder`); Mercury's check of the answer refuses it as
        unchecked, naming the attempt and the first untried rung, and records the refusal on
        its call. One press is still one call, the person's trigger, its spend the incident's."""
        iid = stopped(ai)
        ai.answer = answer(fix())
        r, html = press(ai, iid)
        assert r.status_code == 200, html
        assert len(ai.sent) == 1, "the device state class is off: the plain pass, one call"
        sec = sec_of(html)
        assert 'data-state="proposed"' in sec
        assert ("The AI's answer couldn't be checked, so it isn't shown: the plan's step 1 "
                "(telemetry-resubscribe) counts as tried: attempt:1") in sec, sec
        assert "propose the first untried rung, rung 2" in sec
        assert "/fixit/approve" not in sec, "a repeat is never approvable"
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert line["source"] == "ai" and line["operation"] == "" and line["params"] == {}
        # Every pass is v18's prompt since v17's one shape (231da1d6; C3918's v18).
        assert line["prompt"] == "fixit_troubleshoot.v18"
        (call,) = line["calls"]
        rows = calls.read()["rows"]
        sent = [x for x in rows if x.get("id") == call]
        assert sent and sent[0]["trigger"]["kind"] == "person"
        assert sent[0]["feature"] == "fixit_troubleshoot"
        assert [x["use"] for x in calls.uses().get(call, [])] == ["refused by validation"]
        # The incident's spend is the call's, drawn on the page.
        spent = F.cost_so_far(incident(iid))
        assert spent["state"] == "ok" and spent["usd"] > 0
        _r, again = page(ai.client, iid)
        assert "<strong>This incident:</strong> AI $0.00 " not in sec_of(again)

    def test_what_is_sent_is_the_pack_the_attempts_and_the_note_never_a_command(self, ai):
        iid = stopped(ai)
        press(ai, iid, note="the collector at 2001:db8::20 port 57000 still holds a session")
        (body,) = ai.sent
        text = data_of(body)
        for part in ('<data name="pack">', '<data name="note">', '<data name="the_incident">'):
            assert part in text, part
        assert "attempt:1" in text and '"name":"attempts"' in text
        assert "2001:db8::20" in text, "an IPv6 address the note holds goes as written"
        system = " ".join(b["text"] for b in body["system"])
        assert "telemetry-resubscribe" in system and "telemetry-readd" in system
        # Premise corrected (231da1d6, the operator, 2026-11-16: "one prompt shape every pass
        # so its cache is read", v17): every pass, the plain one too, carries the read set and
        # the reads' format in its context, the cached prefix the same bytes call to call.
        assert '<context name="read_set">' in system, "every pass carries the read set"
        # The attempt's approver is a stable label, never their identity (the payload's).
        from tests.test_heal_resubscribe import ACTOR
        assert ACTOR not in json.dumps(body) and "person-" in text

    def test_a_secret_in_the_note_is_masked_before_it_leaves_and_said(self, ai):
        """The note is the typed part ``note`` (`gateway.TYPED_PARTS`): masked as it leaves by
        the person's own words' mask, said back on the section, and masked at rest."""
        iid = stopped(ai)
        secret = "$9$abcdefghijklmn$opqrstuvwxyz0123456789ABCDEFG"
        r, html = press(ai, iid, note=f"the old router had enable secret 9 {secret} on it")
        assert r.status_code == 200
        (body,) = ai.sent
        assert "opqrstuvwxyz0123456789" not in json.dumps(body)
        assert "data-typed-masked" in sec_of(html), "what was masked is said in place"
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert "opqrstuvwxyz0123456789" not in json.dumps(line)

    def test_the_gap_has_no_approve(self, ai):
        iid = stopped(ai)
        ai.answer = answer(gap={"what": "close the collector's session from r2 on its host",
                                "evidence_refs": ["attempt:1"]})
        r, html = press(ai, iid)
        sec = sec_of(html)
        assert r.status_code == 200 and "a gap" in sec
        # Premise corrected (R2): the gap is said by the card's status line, the line's own
        # words, where "Proposed fix: none Mercury can run" was the old state's paragraph.
        assert "Open the fix's card…" not in sec and "/fixit/approve" not in sec
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert line["operation"] == "" and line["calls"] and line["shown"]["gap"]

    @pytest.mark.parametrize("kind,ans,said", [
        ("unanswerable", answer(outcome="refuse", hypotheses=[], why_not="nothing bears on it"),
         "the evidence cannot say"),
        ("no fix", answer(), "The AI named no fix"),
    ])
    def test_no_fix_is_said_and_kept(self, ai, kind, ans, said):
        iid = stopped(ai)
        ai.answer = ans
        _r, html = press(ai, iid)
        assert said in sec_of(html), kind
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert line["operation"] == "" and line["calls"], kind


# ── The check ───────────────────────────────────────────────────────────────────────────────

class TestTheCheck:
    @pytest.mark.parametrize("ans,why", [
        (answer(fix(subscriptions=("101", "103"))), "103"),
        (answer(fix(device="r6")), "r6"),
        (answer(fix(subscriptions=("101 ; configure terminal",))), "subscriptions"),
        (answer(fix(operation="configure terminal")), "catalog"),
        (answer(fix(operation=CLOSE), cites=("seen_before:2",)), "seen_before:2"),
        (answer(fix(), gap={"what": "both", "evidence_refs": ["attempt:1"]}), "both a fix"),
    ], ids=["another subscription", "another device", "a command as a parameter",
            "a command as the operation", "a past incident not sent", "a fix and a gap"])
    def test_an_answer_out_of_scope_is_refused_as_unchecked_and_recorded(self, ai, ans, why):
        iid = stopped(ai)
        ai.answer = ans
        r, html = press(ai, iid)
        sec = sec_of(html)
        assert r.status_code == 200
        if why == "seen_before:2":
            # Premise corrected (the operator's rule of 2026-11-15, "never discard a whole
            # answer for a bad citation"): a past incident Seen before did not send is a
            # citation not in the evidence. The answer is kept, its hypothesis resting on it
            # marked naming it, asked once more, and its step refused at the page's preflight,
            # so it is never approvable. Measured: the step cites attempt:1 (this answer's fix),
            # so it is not unverified-only; it repeats attempt 1, and is refused as a repeat (a
            # step resting only on unverified citations: tests/test_fixit_unverified.py).
            from modules.fixit import plan as FP
            mark = "unverified (cites seen_before:2, not in the evidence)"
            assert "couldn't be checked" not in sec and mark in sec, sec
            assert len(ai.sent) == 2 and "citation_check" in json.dumps(ai.sent[1]["messages"])
            (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
            assert line["shown"]["hypotheses"][0]["unverified_words"] == mark
            assert line["shown"]["steps"][0]["only_unverified"] is False
            got = FP.preflight(incident(iid), line)
            # Premise corrected (17215a95's ladder): the repeat this case rested on is refused
            # as tried now, so its fix is the collector's close (`CLOSE`). Its step rests on
            # attempt:1 too, so the citation refuses nothing at its preflight; the plan is not
            # approvable here only because the lab's collector stand-in reads no session for the
            # close to bind (measured: "Step 1 names no collector session to close").
            assert got["steps"][0]["preflight"]["ok"], got
            assert not got["approvable"] and "names no collector session" in got["why_refused"]
            assert "/fixit/approve" not in sec_of(page(ai.client, iid)[1])
            return
        assert "couldn't be checked, so it isn't shown" in sec and why in sec, sec
        assert "Open the fix's card…" not in sec
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert line["operation"] == "" and line["calls"], "the spend stays the incident's"
        uses = calls.uses().get(line["calls"][0], [])
        assert [u["use"] for u in uses] == ["refused by validation"]

    def test_the_note_never_widens_what_a_fix_may_act_on(self, ai):
        iid = stopped(ai)
        ai.answer = answer(fix(device="r6"), cites=("note:1",))
        _r, html = press(ai, iid, note="r6 is the one to re-subscribe, do it there")
        assert "which is not one the finding names" in sec_of(html)
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert line["operation"] == "" and line["params"] == {}, "nothing is proposed on r6"
        assert len(ai.sent) == 1

    def test_a_refused_fix_through_the_door_is_kept_with_no_operation(self, ai, monkeypatch):
        """A fix the catalog's schema takes and Mercury's own check refuses (here guard 3: the
        device held by planned work) is recorded on its call and kept with no operation."""
        iid = stopped(ai)
        monkeypatch.setattr("modules.heal.guards.g3_planned", lambda *a, **k: {
            "guard": 3, "name": "planned work", "words": "a planned restart window holds r2"})
        # Premise corrected (17215a95's ladder): a fix the ladder lets through (`CLOSE`), so
        # the refusal is the guard's, where `fix()`'s re-subscribe is refused as tried first.
        ai.answer = answer(fix(operation=CLOSE))
        _r, html = press(ai, iid)
        assert "Mercury's check refused" in sec_of(html)
        (line,) = [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln]
        assert line["operation"] == "" and "guard 3" in line["words"]
        uses = calls.uses().get(line["calls"][0], [])
        assert [u["use"] for u in uses] == ["refused by validation"]


# ── Refused at the press, nothing sent ──────────────────────────────────────────────────────

class TestRefusedAtThePress:
    def test_past_the_cap_nothing_is_sent_and_both_figures_are_named(self, ai):
        from modules.settings_schema import write_settings
        iid = stopped(ai)
        assert write_settings({"ai_cap_usd_per_incident": UNDER_THE_LEAST})["ok"]
        r, html = press(ai, iid, drawn_spent="0.000000", drawn_cap="1.000000")
        assert r.status_code == 409
        said = sec_of(html)
        # Premise corrected (7b0bb884): the figure is the least one call costs, no worst case.
        assert "Not asked" in said and LEAST in said and "$0.02" in said
        assert "the per-incident cap was $1.00 when the panel was drawn" in said
        assert ai.sent == [] and calls.read()["rows"] == []
        assert F.read(incident(iid))["state"] == "absent"

    def test_the_figure_drawn_is_the_figure_compared(self, ai):
        """Premise corrected again (7b0bb884, the operator, 2026-11-16: no worst case; "a
        start is refused only if the remaining budget can't cover the counted prompt plus the
        task's measured typical output"): the figure the route's cap compares is the least one
        call costs (`fixit_troubleshoot.start_usd`), and the card draws this incident's spend
        after it ("this incident's spend after its first call at least $0.0576", nothing spent
        yet), where it drew four calls' worst case at the pin's per-call cap."""
        from modules.ai import fixit_troubleshoot as AIT
        from modules.fixit import policy as P
        iid = stopped(ai)
        _r, html = page(ai.client, iid)
        sec = sec_of(html)
        least = AIT.start_usd()
        assert P.money(least) == LEAST
        assert f"this incident's spend after its first call at least {LEAST}" in sec, sec
        got = P.cap_state(incident(iid), least)
        assert (got["worst"], got["total"], got["spent"]) == (least, least, 0.0)
        assert 'name="drawn_cap" value="1.000000"' in sec

    def test_the_mode_off_sends_nothing(self, ai):
        from modules.settings_schema import write_settings
        iid = stopped(ai)
        assert write_settings({"ai_troubleshoot_mode": "off"})["ok"]
        _r, html = page(ai.client, iid)
        assert "/fixit/start" not in sec_of(html)
        r, html = press(ai, iid)
        assert r.status_code == 409 and "its mode is Off" in sec_of(html)
        assert ai.sent == []

    def test_an_unverified_press_sends_nothing(self, ai, monkeypatch):
        iid = stopped(ai)
        monkeypatch.setattr("modules.identity.verified_identity", lambda *a, **k: None)
        r, _html = press(ai, iid)
        assert r.status_code == 403 and ai.sent == []

    def test_a_resolved_incident_sends_nothing(self, ai):
        from modules.heal import incidents
        from tests.test_fixit_incident import T0
        iid = stopped(ai)
        incidents.close(NET, iid, "the alert cleared", now=T0)
        r, _html = press(ai, iid)
        assert r.status_code == 409 and ai.sent == []

    @pytest.mark.parametrize("what", ["start", "modify"])
    def test_a_press_after_the_cap_moved_is_refused_naming_what_moved(self, ai, what):
        """The old TestRetry's guarantee kept for Start and Modify (one path, `fixit_v2._ask`):
        a press from a panel drawn under the cap, made after the cap moved, is refused naming
        what moved and both figures; the model is asked zero times and nothing is recorded."""
        from modules.settings_schema import write_settings
        from tests.test_heal_resubscribe_v2 import hidden
        iid = stopped(ai)
        data = {"text": "the collector looks stuck"}
        if what == "modify":
            line = F.record_proposal(incident(iid), "person", steps=[
                {"operation": "telemetry-readd", "params": {"sub": "101"}}])
            data["proposal"] = line["proposal"]
        _r, html = page(ai.client, iid)
        drawn = {"drawn_spent": hidden(html, "drawn_spent"),
                 "drawn_cap": hidden(html, "drawn_cap")}
        assert drawn == {"drawn_spent": "0.000000", "drawn_cap": "1.000000"}
        assert write_settings({"ai_cap_usd_per_incident": UNDER_THE_LEAST})["ok"]
        kept = F.read(incident(iid))["lines"]
        r = post(ai.client, iid, what, **data, **drawn)
        said = sec_of(r.get_data(as_text=True))
        assert r.status_code == 409, said[:400]
        assert said.count("Not asked") == 1, said[:400]
        assert ("Since the panel was drawn, the per-incident cap was $1.00 when the panel was "
                "drawn and is $0.02 now") in said
        # Premise corrected (7b0bb884): the least call's figure, no worst case.
        assert LEAST in said and "against the cap of $0.02" in said, said[:600]
        assert ai.sent == [], "the model is not asked past the cap"
        assert calls.read()["rows"] == []
        assert F.read(incident(iid))["lines"] == kept, "nothing is recorded"


# ── One press, the trigger, and no other way in ─────────────────────────────────────────────

class TestNoOtherWayIn:
    def test_one_press_key_is_one_call(self, ai):
        iid = stopped(ai)
        # Premise corrected (R1, 2026-11-14): the one press is Start AI troubleshooting, taken
        # once under the record's lock; the second press is refused before anything is sent.
        h = {"HX-Request": "true", "X-NMAS-Press": "a" * 32}
        got = [ai.client.post(f"/v2/incident/{iid}/fixit/start?list={NET}",
                              data={"text": ""}, headers=h) for _ in range(2)]
        assert [r.status_code for r in got] == [200, 409]
        assert "Start AI troubleshooting is not offered now" in got[1].get_data(as_text=True)
        assert len(ai.sent) == 1

    def test_no_background_feature_and_the_only_way_in_is_the_gated_post(self):
        from modules.ai import background
        from tests import test_ai_controls as T
        from tests.test_ai_entry_points import entry_points
        # R1 (the operator, 2026-11-14): ONE background feature of AI troubleshooting's task,
        # the automatic investigation of a failure, off by default per network; its job is
        # tests/test_ai_entry_points.py's `BACKGROUND_JOBS`' fixit_investigation.
        assert [f for f in background.FEATURES if "fixit" in f] == ["fixit_auto"]
        assert background.FEATURES["fixit_auto"]["task"] == "fixit_troubleshoot"
        found = entry_points(T._sources())
        mine = {k: v for k, v in found.items() if k[0] == "routes.fixit_v2"}
        assert mine == {("routes.fixit_v2", name): {
            "endpoint": f"fixit_v2.{name}", "methods": ["POST"]}
            for name in ("modify", "ask_again", "start")}

    def test_the_incident_page_calls_no_model_and_draws_the_control(self, ai, monkeypatch):
        from tests.test_ai_entry_points import FIXIT_PAGES, _count_ai
        iid = plant()
        seen = _count_ai(monkeypatch)
        for url in FIXIT_PAGES["fixit_troubleshoot"]:
            for headers in ({}, {"HX-Request": "true"}, {}):
                r = ai.client.get(url.format(incident=iid), headers=headers)
                assert r.status_code == 200
                assert 'data-ai-control="fixit_troubleshoot"' in r.get_data(as_text=True)
        assert seen == {"asked": [], "sends": []}

    def test_the_control_s_states(self, ai, monkeypatch):
        """The AI mark, and the control disabled with its reason in each state hosted AI
        cannot answer (tests/ai_controls_check.py); Hand over, beside it, stays usable."""
        import re

        from tests import ai_controls_check
        iid = plant()

        def get_html():
            return page(ai.client, iid)[1]

        def parity(html):
            sec = sec_of(html)
            button = re.search(r'<button[^>]*>\s*<span class="op-idle">Send the hand-over', sec)
            assert button and "data-ai-off" not in button.group(0)
        ai_controls_check.check_screen(monkeypatch, get_html, "fixit_troubleshoot", parity)


# ── The pack's own parts ────────────────────────────────────────────────────────────────────

class TestThePack:
    @pytest.mark.parametrize("address", ["192.0.2.20", "2001:db8::20"])
    def test_seen_before_is_mercury_s_record_its_addresses_as_written(self, address):
        from modules.ai import fixit_troubleshoot as AIT
        value = {"streams": {"state": "read", "devices": {"r2": {"seen": {
            "state": "match", "record": f"Seen before on r2: Nov 8, the collector {address} "
                                        "held a dead session", "from": "2026-11-08T20:05:00Z",
            "to": "2026-11-08T21:01:37Z", "what": "lost telemetry", "cause": "half_open",
            "ended": {"words": "fixed by a change on r2's console"}, "held": {}}}}}}
        s = AIT.seen_section(NET, "r2", value)
        assert s["state"] == "ok" and [p["ref"] for p in s["pieces"]] == ["seen_before:1"]
        assert address in s["pieces"][0]["words"]

    def test_no_stored_reading_is_said_never_a_match(self):
        from modules.ai import fixit_troubleshoot as AIT
        s = AIT.seen_section(NET, "r2", {})
        assert s["state"] == "absent" and not s["pieces"] and s["why"]
