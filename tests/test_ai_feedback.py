"""Was this right? on every AI answer, and the review of the answers said wrong (PHASE8_PLAN 16.11
item 1, Decision 5; board FB, `AiFeedback.dc.html`, signed off under the Phase 7 mode
2026-10-28). Through the real routes, the real gate, the real records store and the real record
of AI calls (in the test's folder); the calls judged are planted rows, and no provider is
reachable: a model call fails the test.

Each test holds one purpose:
- Yes is recorded as the verified person, with the call's id and the hashes of what the record
  of AI calls holds, and the control draws it in place;
- No keeps what was wrong and the sentence masked, never the raw secret;
- one answer per person per call: a second is refused naming the first, nothing more kept;
- a service, or an unverified request, is refused and nothing is kept; the control draws its
  buttons disabled with the reason;
- a call the record does not hold is refused by name;
- a No needs a kind of wrong and a sentence;
- a store that cannot be read refuses, nothing kept, and the control says so;
- the control is drawn under an answer drawn and never under one Mercury's check refused, and
  each answer template includes it in its answered branch only;
- Accept is bound to the draft's hash: a moved draft is refused naming both; the draft holds no
  person and its download is the task's accepted drafts;
- Dismiss needs a reason, and a No settled once is refused naming who settled it;
- the review card leads with counts, draws one page of collapsed rows with Older…, and reads
  no call to draw them;
- nothing here calls a model.
"""
import hashlib
import json
import os
import re
import types
from html import unescape

import pytest

from modules import identity
from modules.ai import calls, feedback
from tests.conftest import TEST_PERSON
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQUEST = {"system": "the prompt", "messages": [{"role": "user", "content": "pack ep-1"}]}
RESPONSE = '{"outcome": "hypotheses", "rationale": "the link flapped", "hypotheses": []}'
#: A type-7 password in a sentence: the masked store must never hold it.
SECRET_LINE = "username admin password 7 0822455D0A16"


@pytest.fixture
def fb(networks, tmp_path, monkeypatch):  # noqa: F811 (the fixture above)
    """The record of AI calls and the answers store in the test's folder, two planted calls,
    and every way to the provider closed."""
    monkeypatch.setattr(calls, "_path", lambda: str(tmp_path / "ai_calls.jsonl"))
    from modules.ai import anthropic_adapter, gateway

    def no_model(*_a, **_k):
        raise AssertionError("Was this right? made a model call")
    monkeypatch.setattr(gateway, "ask", no_model)
    monkeypatch.setattr(anthropic_adapter, "send", no_model)
    for cid, feature in (("ai-0000000000000001", "explain"), ("ai-0000000000000002", "nl_query")):
        assert calls.record({"id": cid, "feature": feature, "actor": "asker@example.com",
                             "model": "claude-sonnet-5-5", "prompt": f"{feature}.v8",
                             "subject": {"pack": "ep-1"}, "request": REQUEST,
                             "response": RESPONSE, "verdict": "ok", "cost_usd": 0.04})["recorded"]
    return types.SimpleNamespace(client=networks["client"], dir=tmp_path)


def _post(w, path, data):
    r = w.client.post(path, data=data, headers={"HX-Request": "true"})
    return r, unescape(r.get_data(as_text=True))


def _get(w, path):
    r = w.client.get(path, headers={"HX-Request": "true"})
    return r, unescape(r.get_data(as_text=True))


def _rows(w):
    got = feedback.read()
    return got["rows"]


def _no(w, call="ai-0000000000000001", words="the errors began with the host's CPU on r2"):
    return _post(w, f"/v2/ai/feedback/answer/{call}",
                 {"verdict": "no", "why": "conclusion", "words": words})


def test_yes_is_recorded_as_the_person_with_the_calls_hashes(fb):
    r, html = _post(fb, "/v2/ai/feedback/answer/ai-0000000000000001", {"verdict": "yes"})
    assert r.status_code == 200 and "you said right" in html and "ai-fb-q" not in html
    assert r.headers["Content-Security-Policy"]
    assert "ai_feedback" in r.headers["X-NMAS-Invalidates"]
    [row] = _rows(fb)
    assert row["verdict"] == "yes" and row["actor"] == TEST_PERSON and row["verified"]
    assert row["call_id"] == "ai-0000000000000001" and row["task"] == "explain"
    assert row["request_sha256"] == hashlib.sha256(
        json.dumps(REQUEST, sort_keys=True).encode()).hexdigest()
    assert row["answer_sha256"] == hashlib.sha256(RESPONSE.encode()).hexdigest()
    assert "request" not in row and "response" not in row


def test_no_keeps_the_kind_and_the_sentence_masked(fb):
    r, html = _no(fb, words=f"it should say the line {SECRET_LINE} was added")
    assert r.status_code == 200 and "you said wrong" in html and "to review in Settings" in html
    [row] = _rows(fb)
    assert row["verdict"] == "no" and row["why"] == "conclusion"
    assert "0822455D0A16" not in row["words"] and "it should say the line" in row["words"]
    with open(feedback._path(), encoding="utf-8") as fh:
        assert "0822455D0A16" not in fh.read()


def test_one_answer_per_person_per_call(fb):
    assert _post(fb, "/v2/ai/feedback/answer/ai-0000000000000001",
                 {"verdict": "yes"})[0].status_code == 200
    r, html = _no(fb)
    assert r.status_code == 409
    assert "you said right for call ai-0000000000000001 at" in html
    assert "one answer per person per call" in html
    assert len(_rows(fb)) == 1


def test_a_service_is_refused_and_its_buttons_are_disabled(fb, monkeypatch):
    from modules.settings_schema import write_settings
    assert write_settings({"require_person_for_configure": False})["ok"]
    svc = identity.Identity(actor="service:ci", kind="service", service_id="ci", verified=True,
                            outcome="ok", peer="127.0.0.1", peer_trusted=True)
    monkeypatch.setattr(identity, "identify", lambda _request: svc)
    r, html = _post(fb, "/v2/ai/feedback/answer/ai-0000000000000001", {"verdict": "yes"})
    assert r.status_code == 409 and "recorded only as a verified person" in html
    assert "is a service (service:ci)" in html
    assert re.search(r'<button type="submit"[^>]*data-op="ai-feedback"[^>]*disabled', html)
    assert _rows(fb) == []


def test_an_unverified_request_is_refused_by_the_gate(fb, monkeypatch):
    nobody = identity.Identity(outcome="no_header", reason="no access assertion")
    monkeypatch.setattr(identity, "identify", lambda _request: nobody)
    r = fb.client.post("/v2/ai/feedback/answer/ai-0000000000000001", data={"verdict": "yes"},
                       headers={"HX-Request": "true"})
    assert r.status_code in (401, 403)
    assert _rows(fb) == []


def test_a_call_the_record_does_not_hold_is_refused_by_name(fb):
    r, html = _post(fb, "/v2/ai/feedback/answer/ai-ffffffffffffffff", {"verdict": "yes"})
    assert r.status_code == 409
    assert "call ai-ffffffffffffffff is not in the record of AI calls" in html
    assert _rows(fb) == []


@pytest.mark.parametrize("data, words", [
    ({"verdict": "no", "words": "the cause was the host's CPU"}, "say what was wrong"),
    ({"verdict": "no", "why": "missed", "words": "no"}, "say in a sentence"),
    ({"verdict": "maybe"}, "is neither yes nor no"),
])
def test_a_no_needs_a_kind_and_a_sentence(fb, data, words):
    r, html = _post(fb, "/v2/ai/feedback/answer/ai-0000000000000001", data)
    assert r.status_code == 409 and words in html
    assert _rows(fb) == []


def test_a_store_that_cannot_be_read_refuses_and_says_so(fb):
    os.makedirs(feedback._path())              # a folder where the file should be: unreadable
    r, html = _post(fb, "/v2/ai/feedback/answer/ai-0000000000000001", {"verdict": "yes"})
    assert r.status_code == 409
    assert "Couldn't record:" in html and "cannot be read" in html
    assert "nothing was recorded" in html


def _render(name, **ctx):
    from flask import render_template
    from app import app
    with app.test_request_context("/"):
        return unescape(render_template(name, **ctx))


def test_the_control_is_under_an_answer_drawn_never_under_a_refused_one(fb):
    answer = {"ok": True, "call_id": "ai-0000000000000001", "cost_usd": 0.04, "pack_id": "ep-1",
              "answer": {"outcome": "hypotheses", "rationale": "the link flapped",
                         "hypotheses": []}}
    drawn = _render("v2/_explain.html", x=answer, explain_model="m")
    assert 'id="ai-fb-ai-0000000000000001"' in drawn and "Was this right?" in drawn
    refused = _render("v2/_explain.html", x=dict(answer, ok=False, error="couldnt_analyse",
                                                 detail="the answer cited logs:999"),
                      explain_model="m")
    assert "This call in History" in refused and "ai-fb" not in refused


#: Every template drawing an AI answer (modules/ai/controls.CONTROLS, the answers' templates),
#: and the variable its answer's call id is read from.
ANSWER_TEMPLATES = {"_explain.html": "x.call_id", "_history_ask_words.html": "w.call_id",
                    "_intent_words.html": "w.call_id", "_sdn_responses.html": "a.call_id"}


@pytest.mark.parametrize("name, var", sorted(ANSWER_TEMPLATES.items()))
def test_each_answer_template_includes_the_control(name, var):
    with open(os.path.join(ROOT, "templates", "v2", name), encoding="utf-8") as fh:
        text = fh.read()
    includes = re.findall(r"\{%-? with fb=ai_feedback\(([\w.]+)\) %\}\{% include "
                          r"\"v2/_ai_feedback.html\" %\}\{% endwith %\}", text)
    assert includes and set(includes) == {var}, (name, includes)


def test_the_answers_templates_are_every_ai_answer():
    """The population: every AI control in the registry that draws an answer (all but the AI
    card's Test, which draws a connection's verdict), by its template."""
    from modules.ai import controls
    drawn = {c["template"].split("/")[-1] for k, c in controls.CONTROLS.items()
             if k != "ai_card_test" and c.get("template")}
    # Explain's control is drawn by _explain_block.html, which includes its answer, _explain.html.
    assert drawn == (set(ANSWER_TEMPLATES) - {"_explain.html"}) | {"_explain_block.html"}


def test_accept_is_bound_to_the_draft_and_the_draft_names_no_person(fb):
    _no(fb)
    [v] = _rows(fb)
    r, html = _get(fb, f"/v2/ai/feedback/review/{v['id']}/open")
    assert r.status_code == 200 and "Accept into a case draft…" in html
    shown = re.search(r'name="draft" value="([0-9a-f]{64})"', html).group(1)
    assert TEST_PERSON not in html.split("ai-fb-draft")[1].split("</pre>")[0]
    r, html = _post(fb, f"/v2/ai/feedback/review/{v['id']}",
                    {"outcome": "accepted", "draft": "0" * 64})
    assert r.status_code == 409 and "the draft drawn (000000000000) is not the draft now" in html
    r, html = _post(fb, f"/v2/ai/feedback/review/{v['id']}",
                    {"outcome": "accepted", "draft": shown})
    assert r.status_code == 200 and "accepted" in html and "Copy the draft" in html
    got = fb.client.get("/v2/ai/feedback/drafts/explain.json")
    body = json.loads(got.get_data(as_text=True))
    assert got.status_code == 200 and [d["from_call"] for d in body["drafts"]] == \
        ["ai-0000000000000001"]
    assert body["drafts"][0]["expect"] is None and TEST_PERSON not in json.dumps(body)


def test_dismiss_needs_a_reason_and_a_no_is_settled_once(fb):
    _no(fb)
    [v] = _rows(fb)
    r, html = _post(fb, f"/v2/ai/feedback/review/{v['id']}", {"outcome": "dismissed",
                                                               "reason": "no"})
    assert r.status_code == 409 and "say why it is not a case" in html
    r, html = _post(fb, f"/v2/ai/feedback/review/{v['id']}",
                    {"outcome": "dismissed", "reason": "the pack itself was wrong, see C2110"})
    assert r.status_code == 200 and "dismissed" in html
    r, html = _post(fb, f"/v2/ai/feedback/review/{v['id']}",
                    {"outcome": "dismissed", "reason": "a second reviewer's reason here"})
    assert r.status_code == 409 and f"{TEST_PERSON} dismissed it at" in html
    assert [x["kind"] for x in _rows(fb)] == ["verdict", "review"]


def test_the_review_leads_with_counts_and_pages_collapsed_rows_reading_no_call(fb, monkeypatch):
    rows = [{"kind": "verdict", "id": f"fb-{i:012x}", "call_id": "ai-0000000000000001",
             "task": "explain", "verdict": "no", "why": "missed",
             "words": f"answer {i} missed the neighbour", "actor": f"p{i}@example.com",
             "at": f"2026-10-28T10:{i // 60:02d}:{i % 60:02d}Z"} for i in range(60)]
    rows.append(dict(rows[0], id="fb-right", verdict="yes", why="", words=""))
    with open(feedback._path(), "w", encoding="utf-8") as fh:
        fh.write("".join(json.dumps(r) + "\n" for r in rows))
    read_calls = []
    monkeypatch.setattr(calls, "find", lambda cid: read_calls.append(cid))
    r, html = _get(fb, "/v2/ai/feedback/review")
    assert r.status_code == 200 and read_calls == []
    assert "60 to review" in html and "1 said right" in html
    drawn = re.findall(r'<details class="ai-fb-row"[^>]*>', html)
    assert len(drawn) == feedback.PAGE and not any(" open" in d for d in drawn)
    assert "Older…" in html and "older=50" in html
    assert drawn[0].count("fb-00000000003b")          # newest first
    r, html = _get(fb, "/v2/ai/feedback/review?status=to_review&q=answer+7+missed")
    assert len(re.findall(r'<details class="ai-fb-row"', html)) == 1


def test_the_settings_ai_tab_draws_the_review(fb):
    r, html = _get(fb, "/v2/settings/installation?tab=ai")
    assert r.status_code == 200 and 'id="ai-feedback"' in html and "Answers said wrong" in html
