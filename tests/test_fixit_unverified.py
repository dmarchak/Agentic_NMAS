"""An AI answer citing what was not sent is marked, never discarded, and asked once more; and the
card always draws what the AI found (the operator's findings from the first real run of
automatic troubleshooting, 2026-11-15; `modules/ai/fixit_troubleshoot.py` `unverified`,
`retry_once`, `shown`; `modules/fixit/plan.py` `preflight`; templates/v2/_fixit_section.html).

The operator: "Never discard a whole answer for a bad citation: mark that claim 'unverified
(cites X, not in the evidence)' and still show the rest. Then retry once automatically, telling
the AI which citation failed, within the incident cap." And: "The AI's findings, hypotheses and
next steps must always appear on the incident card ('What the AI found'), whatever the outcome
(plan, no fix, gap, partial) ... Don't show the rating without content."

On tests/test_fixit_troubleshoot.py's press (the real app and gateway, the provider stood in),
r2's stopped incident. ``history:99`` is a label r2's pack does not hold. No device, no network,
no live AI.

Each test holds one purpose:
- a hypothesis citing what was not sent is kept, marked in words naming the citation, and the
  rest shown; the retry's request names it;
- a retry whose answer cites only what was sent replaces the first answer;
- a step resting only on unverified citations is never approvable, and says why; one with a
  citation that resolves is not refused for it;
- the retry is not asked past the investigation's worst case or the incident's cap, a retry
  not answered or refused by the check leaves the first answer, marked;
- the card draws the findings, hypotheses and next steps of a gap, a no-fix and a partial
  answer, with the rating beside them; an answer with nothing to draw is its calls alone, no
  rating; in a real browser, the card is open with the findings and their marks.
"""
import json

import pytest

from modules.ai import fixit_troubleshoot as FT
from modules.fixit import incident as F
from tests.test_fixit_section_v2 import NET, incident, page  # noqa: F401
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_fixit_troubleshoot import ai, answer, fix, press, sec_of, stopped  # noqa: F401
# Premise corrected (17215a95's ladder: a re-subscribe of 101 after attempt 1's failed
# re-subscribe is refused as tried, so the answer is "couldn't be checked" and keeps nothing):
# each answer's fix and plan step is the collector's close, which no attempt makes tried.
from tests.test_fixit_troubleshoot import CLOSE
from tests.test_heal_resubscribe import lab  # noqa: F401
from tests.test_sdn_connections import networks  # noqa: F401

BAD = "history:99"
MARK = f"unverified (cites {BAD}, not in the evidence)"
RATING = "Was this right?"


def hyp(claim, *cites):
    return {"claim": claim, "evidence_refs": list(cites),
            "confirm_with": "show telemetry ietf subscription all"}


def partial(fix_=None, gap=None, **kw) -> dict:
    """An answer whose first hypothesis cites what was sent and whose second does not."""
    return answer(fix_, gap, hypotheses=[
        hyp("The collector still holds r2's old session.", "attempt:1"),
        hyp("The subscription was removed before the attempt.", BAD)], **kw)


def answers(ai, monkeypatch, *seq):  # noqa: F811
    """The provider answers *seq* in order, the last again after that."""
    from modules.ai import anthropic_adapter as AD
    from modules.ai import gateway
    left = list(seq)

    def send(body, key, **_kw):
        ai.sent.append(body)
        got = left.pop(0) if len(left) > 1 else left[0]
        return AD.Reply(status=200, body={
            "content": [{"type": "text", "text": json.dumps(got)}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 9000, "output_tokens": 600}}, attempts=1, latency_s=0.2)
    monkeypatch.setattr(gateway.anthropic_adapter, "send", send)


def ai_line(iid) -> dict:
    return [ln for ln in F.read(incident(iid))["lines"] if "proposal" in ln][-1]


def why_block(sec: str) -> str:
    """The card's "What the AI found" (or "Why the AI proposes this") block, or ``""``."""
    if 'data-more="why"' not in sec:
        return ""
    return sec.split('data-more="why"', 1)[1].split("</details>", 1)[0]


# ── Marked, never discarded; asked once more ────────────────────────────────────────────────

class TestMarked:
    def test_a_claim_citing_what_was_not_sent_is_marked_and_the_rest_shown(self, ai):
        iid = stopped(ai)
        ai.answer = partial(fix(operation=CLOSE))
        r, html = press(ai, iid)
        assert r.status_code == 200, html
        sec = sec_of(html)
        assert "couldn't be checked" not in sec, "the answer is kept"
        line = ai_line(iid)
        first, second = line["shown"]["hypotheses"]
        assert first["unverified_words"] == "" and second["unverified_words"] == MARK
        block = why_block(sec)
        assert MARK in block and "The collector still holds r2's old session." in block
        # Asked once more, the citation named in the request; the same answer back stays marked.
        assert len(ai.sent) == 2 and FT.RETRY_PART in json.dumps(ai.sent[1]["messages"])
        assert f"hypothesis 2 cites {BAD}" in json.dumps(ai.sent[1])
        assert FT.RETRY_PART not in json.dumps(ai.sent[0]["messages"])
        assert line["shown"]["retry"]["asked"] is True
        # Premise corrected (93120b2f, the operator, 2026-11-16: an uncited claim is marked too,
        # so the words name a citation "bad or missing").
        assert "still has a citation that is bad or missing, and is shown marked" in \
            line["shown"]["retry"]["words"]
        assert len(line["calls"]) == 2, "both calls are the incident's spend"

    def test_a_retry_citing_only_what_was_sent_replaces_the_first_answer(self, ai, monkeypatch):
        iid = stopped(ai)
        good = answer(fix(operation=CLOSE),
                      rationale="Corrected: r2's old session is still held.")
        answers(ai, monkeypatch, partial(fix(operation=CLOSE)), good)
        press(ai, iid)
        line = ai_line(iid)
        assert line["shown"]["rationale"] == "Corrected: r2's old session is still held."
        assert all(not h["unverified_words"] for h in line["shown"]["hypotheses"])
        assert "every citation of the second answer is in what was sent" in \
            line["shown"]["retry"]["words"]
        assert line["prompt"] == "fixit_troubleshoot.v18"  # one shape every pass (231da1d6)


class TestApprovable:
    def test_a_step_resting_only_on_unverified_citations_is_never_approvable(self, ai):
        from modules.fixit import plan as FP
        iid = stopped(ai)
        ai.answer = dict(partial(), plan=[{
            "operation": CLOSE,
            "params": {"device": "r2", "subscriptions": ["101"], "subscription": None,
                       "interface": None, "cause": None, "changes": None, "remove": None},
            "why": "it rests on a history line not sent.", "evidence_refs": [BAD]}],
            improvement=None)
        _r, html = press(ai, iid)
        line = ai_line(iid)
        assert line["shown"]["steps"][0]["only_unverified"] is True
        got = FP.preflight(incident(iid), line)
        assert not got["approvable"]
        pf = got["steps"][0]["preflight"]
        assert pf["code"] == "unverified" and MARK in pf["refused"], pf
        sec = sec_of(page(ai.client, iid)[1])
        assert "/fixit/approve" not in sec and "rests only on evidence Mercury could not find" \
            in sec, "the person sees why"

    def test_a_step_with_a_citation_that_resolves_is_not_refused_for_the_other(self, ai):
        from modules.fixit import plan as FP
        iid = stopped(ai)
        ai.answer = dict(partial(), plan=[{
            "operation": CLOSE,
            "params": {"device": "r2", "subscriptions": ["101"], "subscription": None,
                       "interface": None, "cause": None, "changes": None, "remove": None},
            "why": "attempt 1 and a line not sent.", "evidence_refs": ["attempt:1", BAD]}],
            improvement=None)
        press(ai, iid)
        line = ai_line(iid)
        step = line["shown"]["steps"][0]
        assert step["unverified_words"] == MARK and step["only_unverified"] is False
        assert FP.preflight(incident(iid), line)["steps"][0]["preflight"]["code"] != "unverified"


class TestTheRetry:
    """`retry_once` itself, on an answer the loop kept with its marks: each branch."""

    @staticmethod
    def kept(spent):
        from modules.ai.fixit_troubleshoot import TroubleshootPlan
        a = TroubleshootPlan.model_validate_json(json.dumps(partial()))
        prep = {"marks": [(a, {"hypothesis 2": [BAD]})], "data": {"pack": "[]"}, "ctx": {},
                "subject": {"kind": "heal_incident", "id": "hi-1", "devices": ["r2"]},
                "actable": ["r2"]}
        got = {"state": "answered", "answer": a, "pass": 1, "reads": [], "cost_usd": spent,
               "call_ids": ["ai-1"]}
        return a, prep, got

    def run(self, monkeypatch, spent=0.01, cap="allowed", reply=None):
        from modules.fixit import policy as P
        a, prep, got = self.kept(spent)
        monkeypatch.setattr(P, "cap_state", lambda inc, worst: {
            "state": cap, "words": "Retry isn't available: this incident's AI spend would "
                                   "pass its cap"})
        asked = []

        def ask(*args, **kw):
            asked.append(args)
            return reply or {"ok": False, "error": "provider_down", "detail": "no answer"}
        out = FT.retry_once(prep, FT.loop_feature(prep), got, object(), ask=ask,
                            network="n", actor="a", trigger={})
        return a, got, out, asked

    # Premise corrected (7b0bb884, the operator, 2026-11-16: no worst case drawn before the
    # press; the spending limits govern every call): `retry_once` no longer compares a worst
    # case or the incident's cap itself; it asks through the gateway, which judges the retry as
    # every call (the incident's cap its spend cap) and refuses it before any provider request
    # when a limit cannot pay it (`read_loop.CAP_KINDS`). Such a retry is not asked again,
    # nothing leaves the host, and the first answer stands, marked.

    def test_past_the_investigations_worst_case_it_is_not_asked(self, monkeypatch):
        a, got, out, asked = self.run(monkeypatch, reply={
            "ok": False, "error": "feature_cap",
            "detail": "fixit_troubleshoot's day cap cannot pay the call's hold"})
        assert len(asked) == 1, "the retry is asked of the gateway, which judges its spend"
        assert out["asked"] is False and got["answer"] is a, "nothing left the host"
        assert out["words"].startswith("not asked again: feature_cap: "), out["words"]

    def test_past_the_incidents_cap_it_is_not_asked(self, monkeypatch):
        a, got, out, asked = self.run(monkeypatch, reply={
            "ok": False, "error": "over_cap",
            "detail": "this incident's AI cap cannot pay the call's hold"})
        assert out["asked"] is False
        assert out["words"].startswith("not asked again: over_cap: this incident's AI")
        assert got["answer"] is a

    def test_a_retry_not_answered_leaves_the_first_answer_marked(self, monkeypatch):
        a, got, out, asked = self.run(monkeypatch)
        assert len(asked) == 1 and out["asked"] and not out["accepted"]
        assert got["answer"] is a and out["marks"] == {"hypothesis 2": [BAD]}
        assert "not answered (provider_down" in out["words"]

    def test_a_retry_the_check_refuses_leaves_the_first_answer_marked(self, monkeypatch):
        from modules.ai.fixit_troubleshoot import TroubleshootPlan
        worse = TroubleshootPlan.model_validate_json(json.dumps(answer(fix(device="r6"))))
        a, got, out, asked = self.run(monkeypatch, reply={"ok": True, "output": worse,
                                                          "call_id": "ai-2", "cost_usd": 0.02})
        assert got["answer"] is a and not out["accepted"]
        assert "Mercury's check refused the second answer" in out["words"] and "r6" in out["words"]
        assert got["call_ids"] == ["ai-1", "ai-2"], "its call is counted all the same"

    def test_nothing_marked_asks_nothing(self, monkeypatch):
        from modules.ai.fixit_troubleshoot import TroubleshootPlan
        a = TroubleshootPlan.model_validate_json(json.dumps(answer(fix())))
        got = {"state": "answered", "answer": a, "cost_usd": 0.0}
        assert FT.retry_once({"marks": [(a, {})]}, None, got, None, ask=None, network="n",
                             actor="a", trigger={}) == {}


# ── What the AI found, whatever the outcome ─────────────────────────────────────────────────

class TestTheCard:
    @pytest.mark.parametrize("ans,said", [
        (lambda: partial(gap={"what": "close the collector's session from r2 on its host",
                              "evidence_refs": ["attempt:1"]}),
         "What the fix needs, which no Mercury operation does yet"),
        (lambda: partial(), "The collector still holds r2's old session."),
        (lambda: partial(fix(operation=CLOSE)), "The step it proposes"),
    ], ids=["a gap", "no fix", "a partial answer with a fix"])
    def test_the_findings_hypotheses_and_next_steps_are_drawn_with_the_rating(self, ai, ans,
                                                                            said):
        iid = stopped(ai)
        ai.answer = ans()
        press(ai, iid)
        block = why_block(sec_of(page(ai.client, iid)[1]))
        assert block, "the card draws what the AI found"
        assert "r2's streams stayed down after attempt 1" in block, "its finding"
        assert "The collector still holds r2's old session." in block, "its hypotheses"
        assert "To confirm: <span class=\"mono\">show telemetry ietf subscription all" in block, \
            "each hypothesis's next step"
        assert said in block and MARK in block
        assert RATING in block, "the rating beside content"

    def test_an_answer_with_nothing_to_draw_is_its_calls_and_no_rating(self, ai):
        iid = stopped(ai)
        ai.answer = answer(fix(device="r6"))      # refused by the check: nothing of it shown
        _r, html = press(ai, iid)
        sec = sec_of(html)
        assert why_block(sec) == "" and RATING not in sec, "no rating of nothing"
        assert "data-ai-nothing" in sec and "the call on History" in sec
        # Its effect: the line kept with its call and nothing of the answer, and no retry (the
        # refusal is the check's, not a citation's).
        line = ai_line(iid)
        assert line["calls"] and not (line.get("shown") or {}).get("rationale")
        assert len(ai.sent) == 1

    def test_in_a_real_browser_the_card_is_open_with_the_findings_and_their_marks(self, ai):
        from tests import browser
        ok, why = browser.available()
        if not ok:
            pytest.skip(f"no real browser here ({why}); the tests above still run")
        import app as nmas
        iid = stopped(ai)
        ai.answer = partial(gap={"what": "close the collector's session from r2 on its host",
                                 "evidence_refs": ["attempt:1"]})
        press(ai, iid)
        with browser.Served(nmas.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url(f"/v2/incident/{iid}?list={NET}"))
                card = "document.querySelector('details[data-more=why]')"
                b.wait_for(f"return !!{card}", 20)
                # Premise corrected (board R5, becced07, approved 2026-11-15: everything but the
                # title, impact, status and one action is under the card's one Details, closed
                # by default): Details is opened first, as a person opens it.
                b.click("#inc-details > summary")
                b.wait_for("return document.getElementById('inc-details').open")
                assert b.js(f"return {card}.open") is True, "open: no plan to read first"
                text = b.js(f"return {card}.innerText")
                assert "r2's streams stayed down after attempt 1" in text
                assert MARK in text and RATING in text
                mark = b.js(f"var m = {card}.querySelector('[data-unverified]');"
                            " return m && m.getBoundingClientRect().height > 0")
                assert mark, "the mark is drawn where it can be read"
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
