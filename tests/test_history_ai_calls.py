"""History's record of AI calls (PHASE8_PLAN 15.14, the operator, 2026-10-25 and 2026-10-26),
on test_ai_explain's world (the real builder's pack, the gateway allowed, a fake `send`).

- Recorded at the source: the subject is written with the call (gateway), and what became of
  the answer is its own append-only use row, keyed by the call (Explain: shown, or refused by
  validation); a use row neither counts as a call nor costs.
- Drawn: the row says the feature, its subject and what became of it; its record holds the
  model, the tokens, the cost and the use; a device's History tab shows the calls whose subject
  names the device, and no other.
- Opened (the operator, 2026-10-26: "the exact wording of the prompt that was given and the
  exact structured response ... similar to how device configuration changes have a window"):
  `/v2/history/ai-call/<id>` draws the request part by part as it left the host (the
  instructions, each context block and each data block by its name) and the answer laid out
  for reading; a large part folds with its size; a secret planted in the data is never in the
  stored prompt or the drawn one; a call refused before it was sent says nothing was sent; a
  malformed or unknown id says so.
"""
import json

from modules import history_sources as HS
from modules.ai import calls, explain
from tests.test_ai_explain import _answer, _explain, world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)


def _call(world):  # noqa: F811
    world.answer = _answer(world.pack)
    got = _explain(world)
    assert got["ok"] is True, got
    return got["call_id"]


def test_the_subject_is_written_with_the_call_and_the_use_after_it(world):  # noqa: F811
    call_id = _call(world)
    (row,) = calls.read()["rows"]
    assert row["id"] == call_id
    assert row["subject"] == {"kind": "alert", "id": world.pack["id"],
                              "rule": world.pack["rule"], "devices": [world.pack["device"]]}
    (use,) = calls.uses()[call_id]
    assert use["use"] == "shown: answer" and use["links"]["anchor"] == f"explain-{world.pack['id']}"
    assert calls.spent_usd(row["at"][:10])["calls"] == 1, "a use row is no call"


def test_an_answer_refused_by_validation_is_its_use(world):  # noqa: F811
    a = _answer(world.pack)
    a["hypotheses"][0]["evidence_refs"] = ["logs:999"]
    world.answer = a
    got = _explain(world)
    assert got["error"] == "couldnt_analyse"
    (use,) = calls.uses()[got["call_id"]]
    assert use["use"] == "refused by validation" and "logs:999" in use["detail"]


def test_the_row_says_the_feature_its_subject_and_what_became_of_it(world):  # noqa: F811
    _call(world)
    ctx = {"device": "", "limit": 50}
    (e,) = HS.ai_calls(ctx)["events"]
    assert e["what"].startswith(f"AI call, explain on the alert {world.pack['rule']}: shown: "
                                "answer (claude-sonnet-5-5, $")
    record = dict(e["record"])
    assert record["About"] == f"the alert {world.pack['rule']}"
    assert record["Tokens"] == "4000 in, 300 out, cache 0 written, 0 read"
    assert record["Then"] == "shown: answer" and e["call"] and e["devices"] == ["r1"]


def test_a_join_is_drawn_as_a_join_of_its_call_and_the_call_names_who_joined(world):  # noqa: F811
    """C1854: a press sent again with its key is the joiner's own row, drawn as a join (nothing
    sent, $0, the call's outcome, opening the call's prompt and answer), never a second call;
    the call's row names who joined it, and the day's spend counts one call."""
    import app as APP
    from flask import g

    from modules.ai import presses, triggers
    from tests.ai_person import identity_of
    world.answer = _answer(world.pack)
    actor = "operator@example.com"
    for _ in range(2):
        # One request carrying the press's key and its verified person (C1843: a person
        # trigger names the request's own verified actor), as the route makes it.
        with APP.app.test_request_context("/x", method="POST",
                                          headers={presses.HEADER: "h" * 32}):
            g.nmas_identity = identity_of(actor)
            got = explain.explain(world.pack["id"], actor=actor,
                                  trigger=triggers.person(actor), send=world.send,
                                  today="2026-10-25")
    assert got["ok"] is True and len(world.sent) == 1
    by_kind = {e["record"][0][1] != got["call_id"]: e
               for e in HS.ai_calls({"device": "", "limit": 50})["events"]}
    join, call = by_kind[True], by_kind[False]
    assert join["what"] == (f"AI call, explain on the alert {world.pack['rule']}: joined call "
                            f"{got['call_id']}, nothing sent (claude-sonnet-5-5, $0.0000)")
    assert join["outcome"] == "ok" and join["call"] == got["call_id"]
    assert dict(join["record"])["Joined call"] == got["call_id"]
    (row,) = [r for r in calls.read()["rows"] if r.get("verdict") == "joined"]
    assert dict(call["record"])["Joined by"] == f"{row['actor']} at {row['at']}"
    assert calls.spent_usd(row["at"][:10])["calls"] == 1, "a join is no call"


def test_a_device_s_tab_shows_only_the_calls_about_it(world):  # noqa: F811
    _call(world)
    assert len(HS.ai_calls({"device": "r1", "limit": 50})["events"]) == 1
    assert HS.ai_calls({"device": "r2", "limit": 50})["events"] == []


def test_an_older_row_with_no_subject_reads_as_the_installation():
    assert HS.subject_words({}) == "the installation"
    assert HS.subject_words({"kind": "query", "id": "Lab"}) == "a question on Lab"


def test_the_opened_row_draws_the_prompt_as_sent_and_the_answer_as_received(world):  # noqa: F811
    from html import unescape
    call_id = _call(world)
    sent = world.sent[-1]["body"]
    r = world.lab["client"].get(f"/v2/history/ai-call/{call_id}")
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200
    assert "Sent to the model" in html and "Received" in html
    names = [p["name"] for p in HS.ai_call(call_id)["sent"]]
    assert names[0] == f"the instructions (explain.v{explain.PROMPT[1]})"
    assert "context: pack_format" in names and "data: pack" in names
    assert names[-1] == "data: the_alert"
    # The instructions exactly as they were sent.
    assert sent["system"][0]["text"].strip()[:120] in html
    # The answer, laid out for reading.
    assert json.dumps(world.answer["hypotheses"][0]["claim"])[1:-1] in html
    assert '"outcome": "answer"' in html
    assert "Laid out for reading" in html


def test_a_large_part_folds_and_says_its_size(world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(HS, "AI_BLOCK_FOLD", 50)
    call_id = _call(world)
    view = HS.ai_call(call_id)
    big = [p for p in view["sent"] if p["fold"]]
    assert big and all(p["size"] > 50 for p in big)
    html = world.lab["client"].get(f"/v2/history/ai-call/{call_id}").get_data(as_text=True)
    assert f"({big[0]['size']} characters, folded)" in html


def test_a_planted_secret_is_never_in_the_stored_prompt_or_the_drawn_one(world,  # noqa: F811
                                                                           monkeypatch):
    """The pack carries a stored secret's value it kept (test_ai_explain's planted
    description); the egress mask takes it out before it leaves, so the record and the window
    hold only its mask."""
    from modules import redact
    from tests.test_evidence_pack import _section
    alias = _section(world.pack, "alert")["pieces"][0]["labels"]["ifAlias"]
    stored = alias.split()[2]
    monkeypatch.setattr(redact, "known_secret_values", lambda: {stored: "Lab:enable"})
    call_id = _call(world)
    (row,) = calls.read()["rows"]
    assert stored not in json.dumps(row)
    html = world.lab["client"].get(f"/v2/history/ai-call/{call_id}").get_data(as_text=True)
    assert stored not in html


def test_a_call_refused_before_it_was_sent_says_nothing_was_sent(world):  # noqa: F811
    world.settings.pop("ai_hosted")
    got = _explain(world)
    assert got["error"] == "ai_off"
    html = world.lab["client"].get(f"/v2/history/ai-call/{got['call_id']}").get_data(
        as_text=True)
    assert "Nothing was sent: the call was refused (ai off) before its request was built" in html


def test_the_window_adds_only_what_the_record_lacks(world):  # noqa: F811
    """The row's record already says the model, prompt, schema, tokens, cost and verdict; the
    window adds the request's bound, its thinking and why the answer ended (the shot of
    2026-10-26 drew each twice)."""
    call_id = _call(world)
    meta = dict(HS.ai_call(call_id)["meta"])
    assert set(meta) == {"Most tokens out", "Thinking", "Stopped"}
    assert meta["Most tokens out"] == world.sent[-1]["body"]["max_tokens"]
    assert meta["Stopped"] == "the model finished its answer"


def test_an_answer_cut_at_max_tokens_says_so_and_is_drawn_failed(world, monkeypatch):  # noqa: F811
    """C1754's case: an answer stopped at the bound is incomplete, said in the window and drawn
    in danger on the row, whatever its kind's colour."""
    import re
    world.answer = _answer(world.pack)
    send = world.send

    def cut(body, key):
        reply = send(body, key)
        reply.body["stop_reason"] = "max_tokens"
        return reply
    world.send = cut
    got = _explain(world)
    assert got["error"] == "couldnt_analyse" or got.get("ok") is False, got
    (row,) = calls.read()["rows"]
    assert row["verdict"] == "max_tokens"
    assert dict(HS.ai_call(row["id"])["meta"])["Stopped"].startswith("cut off at the most")
    html = world.lab["client"].get("/v2/history?kind=ai_calls&since=").get_data(as_text=True)
    assert re.search(r'badge-danger[^>]*>[^<]*AI call', html), "a cut-off answer is danger"


def test_an_answer_refused_by_validation_is_drawn_failed(world):  # noqa: F811
    import re
    a = _answer(world.pack)
    a["hypotheses"][0]["evidence_refs"] = ["logs:999"]
    world.answer = a
    assert _explain(world)["error"] == "couldnt_analyse"
    (e,) = HS.ai_calls({"device": "", "limit": 50})["events"]
    assert e["outcome"] == "refused_by_validation"
    html = world.lab["client"].get("/v2/history?kind=ai_calls&since=").get_data(as_text=True)
    assert re.search(r'badge-danger[^>]*>[^<]*AI call', html)


def test_an_answer_shown_is_drawn_in_its_kind_s_colour(world):  # noqa: F811
    import re
    _call(world)
    html = world.lab["client"].get("/v2/history?kind=ai_calls&since=").get_data(as_text=True)
    assert re.search(r'badge-muted[^>]*>[^<]*AI call', html), "the control: a shown answer"
    assert "ai_call<" not in html, "the kind in words, not its code name"


def test_a_malformed_or_unknown_id_says_so(world):  # noqa: F811
    c = world.lab["client"]
    assert "is not an AI call&#39;s id" in c.get("/v2/history/ai-call/nope").get_data(
        as_text=True)
    assert "no AI call ai-0000000000000000 is recorded" in c.get(
        "/v2/history/ai-call/ai-0000000000000000").get_data(as_text=True)
