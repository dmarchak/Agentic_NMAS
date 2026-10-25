"""The gateway's smaller parts held to their exact shapes (`modules/ai/gateway.py`'s
`build_request`, `_delimited`, `_text_of`, `_answered`; `calls.spent_usd`; `schemas.schema_for`),
the irreversible tier's egress path (PHASE8_PLAN 15.12): the request body as sent, the record
of a failed answer, the day's spend, and what Anthropic is sent for a schema. Written from tier
run #63's survivors in these functions (2026-10-25): tests/test_ai_gateway.py drives them
through `ask`, and this file reads each one's own answer whole.
"""
import copy

import pytest

from modules.ai import calls, gateway, schemas
from modules.ai.connection import Ping

PROMPT = {"name": "ping", "version": 1, "text": "the prompt's text", "sha256": "0" * 64}


def test_the_request_body_is_exactly_what_is_sent():
    body = gateway.build_request(PROMPT, Ping, {"b": "two", "a": "one"}, "claude-haiku-5-5", 64,
                                 context={"vocab": "the shared words"})
    assert body == {
        "model": "claude-haiku-5-5",
        "max_tokens": 64,
        "system": [{"type": "text", "text": "the prompt's text"},
                   {"type": "text", "text": '<context name="vocab">\nthe shared words\n</context>',
                    "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": '<data name="a">\none\n</data>\n\n'
                                                 '<data name="b">\ntwo\n</data>'}],
        "output_config": {"format": {"type": "json_schema", "schema": schemas.schema_for(Ping)}},
    }


def test_a_call_with_no_data_says_so_and_no_context_marks_the_prompt():
    body = gateway.build_request(PROMPT, Ping, {}, "claude-haiku-5-5", 64)
    assert body["messages"] == [{"role": "user", "content": "(no data)"}]
    assert body["system"] == [{"type": "text", "text": "the prompt's text",
                               "cache_control": {"type": "ephemeral"}}]


def test_the_text_of_an_answer_is_its_text_blocks_joined():
    reply = {"content": [{"type": "text", "text": '{"echo": '}, {"type": "tool_use", "id": "x"},
                         {"type": "text", "text": '"w"}'}, {"type": "text"}]}
    assert gateway._text_of(reply) == '{"echo": "w"}'
    assert gateway._text_of({}) == "" and gateway._text_of({"content": None}) == ""


def test_a_failed_answer_is_recorded_with_its_kind_and_detail_and_said_whole(monkeypatch):
    kept = []

    def record(row):
        kept.append(row)
        return {"recorded": True}
    monkeypatch.setattr(calls, "record", record)
    row = {"id": "c-1", "cost_usd": 0.0012, "feature": "f", "actor": "a"}
    got = gateway._answered(row, "schema", "the answer is not ping.v1")
    assert kept == [dict(row, verdict="schema", detail="the answer is not ping.v1")]
    assert got == {"ok": False, "error": "schema", "detail": "the answer is not ping.v1",
                   "call_id": "c-1", "cost_usd": 0.0012, "recorded": True}
    monkeypatch.setattr(calls, "record", lambda row: {})
    assert gateway._answered(row, "refusal", "declined")["recorded"] is False


ROWS = [{"at": "2026-10-25T08:00:00Z", "cost_usd": 0.0105},
        {"at": "2026-10-25T09:00:00Z", "cost_usd": None},
        {"at": "2026-10-25T10:00:00Z"},
        {"at": "2026-10-24T23:59:59Z", "cost_usd": 5.0},
        {"cost_usd": 7.0}]


def test_the_days_spend_is_its_rows_cost_and_count(monkeypatch):
    monkeypatch.setattr(calls, "read", lambda: {"state": "ok", "rows": [dict(r) for r in ROWS],
                                                "error": ""})
    assert calls.spent_usd("2026-10-25") == {"state": "ok", "usd": 0.0105, "calls": 3,
                                             "error": ""}
    assert calls.spent_usd("2026-10-23") == {"state": "ok", "usd": 0, "calls": 0, "error": ""}


def test_an_unreadable_record_is_said_whole(monkeypatch):
    monkeypatch.setattr(calls, "read", lambda: {"state": "unreadable", "rows": [],
                                                "error": "a torn line at 3"})
    assert calls.spent_usd("2026-10-25") == {"state": "unreadable", "usd": None, "calls": 0,
                                             "error": "a torn line at 3"}


def _planted(monkeypatch, schema):
    monkeypatch.setattr(schemas, "json_schema", lambda model: schema)
    return schemas.schema_for(Ping)


def test_every_object_is_closed_however_pydantic_writes_it(monkeypatch):
    """An object with no properties (a dict field), properties with no type, and an object
    inside a list (anyOf) are each closed; a scalar is not; and the schema Pydantic gave is
    never changed by deriving what is sent."""
    given = {"type": "object", "properties": {
        "tags": {"type": "object", "additionalProperties": {"type": "string"}},
        "bare": {"properties": {"x": {"type": "string", "maxLength": 9}}},
        "either": {"anyOf": [{"type": "object", "properties": {"y": {"type": "integer",
                                                                     "minimum": 1}}},
                             {"type": "null"}]},
        "name": {"type": "string", "minLength": 1}}}
    before = copy.deepcopy(given)
    sent = _planted(monkeypatch, given)
    assert given == before, "schema_for changed the schema Pydantic gave"
    p = sent["properties"]
    assert sent["additionalProperties"] is False
    assert p["tags"]["additionalProperties"] is False
    assert p["bare"]["additionalProperties"] is False and "maxLength" not in p["bare"]["properties"]["x"]
    assert p["either"]["anyOf"][0]["additionalProperties"] is False
    assert "minimum" not in p["either"]["anyOf"][0]["properties"]["y"]
    assert p["name"] == {"type": "string"} and "additionalProperties" not in p["either"]["anyOf"][1]


def test_another_provider_is_refused_naming_it():
    with pytest.raises(ValueError) as got:
        schemas.schema_for(Ping, "local")
    assert str(got.value) == "no schema rule for the provider 'local'"
