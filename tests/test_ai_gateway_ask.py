"""`gateway.ask` held to what it returns and what it records, whole, on every path (the
irreversible tier's egress path, PHASE8_PLAN 15.12): each refusal before anything is sent, its
kind, its words, its call id and its row exactly; each comparison at its edge (a prompt at its
bound, a worst case at its cap, a day's spend reaching its cap exactly is sent); a provider's
failure; an answer, each failed answer and their rows field by field. Written from tier run
#64's survivors (2026-10-25): tests/test_ai_gateway.py names each path's KIND, and this file
holds the rest. The world (hosted AI allowed, a key, a fake `send`) is that file's.
"""
import json
import logging

import pytest
from pydantic import ValidationError

from modules.ai import anthropic_adapter as A
from modules.ai import calls, connection, gateway, profiles, prompts
from tests.test_ai_gateway import KEY, own_record, world  # noqa: F401 (fixtures)

CALL_ID = "ai-planted00000001"
ACTOR = "operator@example.com"
MODEL = profiles.TASKS["connection_check"]["model"]
BASE = {"id": CALL_ID, "feature": "connection_check", "actor": ACTOR, "model": MODEL,
        "prompt": "ping.v1", "schema": "", "verdict": "", "detail": "", "cost_usd": 0.0}
SHA = prompts.load("ping", 1)["sha256"]
#: A row once the task's model is known: it records the thinking asked (the batched gateway
#: change, 2026-10-25), the model's default when the task names none.
ASKED = dict(BASE, thinking="adaptive")


@pytest.fixture(autouse=True)
def fixed_id(monkeypatch):
    monkeypatch.setattr(calls, "new_id", lambda: CALL_ID)


def _ask(world, feature="connection_check", prompt=("ping", 1), schema=connection.Ping,
         parts=None, send=None, today="2026-10-25"):
    return gateway.ask(feature, prompt, schema, {"word": "w"} if parts is None else parts,
                       actor=ACTOR, send=send or world.send, today=today)


def _row():
    (row,) = calls.read()["rows"]
    row = dict(row)
    assert isinstance(row.pop("at"), str)
    return row


def _refused(kind, detail):
    return {"ok": False, "error": kind, "detail": detail, "call_id": CALL_ID, "recorded": True}


def _request(world, **kw):
    """The masked request a call of the world's makes (sent, its answer the Ping it wants)."""
    world.answer = _answer('{"echo": "w"}')
    assert _ask(world, **kw)["ok"] is True
    body = world.sent.pop()["body"]
    calls_path = calls._path()
    open(calls_path, "w").close()
    return body


def _answer(text, stop="end_turn", usage=None, **extra):
    body = {"content": [{"type": "text", "text": text}], "stop_reason": stop,
            "usage": usage or {"input_tokens": 120, "output_tokens": 8}}
    body.update(extra)
    return body


# ---------------------------------------------------------------- refused before anything is sent

def test_hosted_ai_off_is_refused_whole_and_logged(world, caplog):
    world.settings.pop("ai_hosted")
    caplog.set_level(logging.INFO, logger=gateway.__name__)
    why = ("hosted AI is off: an admin allows it in Settings, with a recorded reason "
           "(PHASE8_PLAN 15.8)")
    assert _ask(world) == _refused("ai_off", why) and world.sent == []
    assert _row() == dict(BASE, verdict="ai_off", detail=why)
    assert [r.getMessage() for r in caplog.records if r.name == gateway.__name__] == [
        f"ai: connection_check refused for ai_off: {why}"]


def test_no_key_is_refused_whole(world, monkeypatch):
    monkeypatch.setattr(gateway, "_api_key", lambda: "")
    words = "no Anthropic API key is set (Settings: a person types it)"
    assert _ask(world) == _refused("no_key", words) and world.sent == []
    assert _row() == dict(BASE, verdict="no_key", detail=words)


def test_a_task_no_pin_names_is_refused_with_every_known_task_and_no_model(world):
    words = (f"'not_a_task' is not a task profiles.TASKS pins; known: "
             f"{', '.join(sorted(profiles.TASKS))}")
    assert len(profiles.TASKS) > 1, "the list's separator is seen only between two"
    assert _ask(world, feature="not_a_task") == _refused("unknown_task", words)
    assert _row() == dict(BASE, feature="not_a_task", model="", verdict="unknown_task",
                          detail=words)


def test_a_pinned_model_with_no_profile_is_refused_in_the_profiles_words(world, monkeypatch):
    monkeypatch.setitem(profiles.TASKS, "connection_check",
                        dict(profiles.TASKS["connection_check"], model="no-such-model"))
    with pytest.raises(KeyError) as missing:
        profiles.profile("no-such-model")
    words = str(missing.value)
    assert _ask(world) == _refused("unknown_model", words) and world.sent == []
    assert _row() == dict(BASE, model="no-such-model", verdict="unknown_model", detail=words)


def test_a_model_another_provider_serves_is_refused(world, monkeypatch):
    monkeypatch.setattr(profiles, "profile", lambda model: {"provider": "local"})
    words = f"{MODEL} is not served by the Anthropic adapter"
    assert _ask(world) == _refused("unknown_model", words) and world.sent == []
    assert _row() == dict(BASE, verdict="unknown_model", detail=words)


class Loose(connection.Ping.__base__):
    x: str


class Claims(connection.Ping.__base__):
    """Claims a registered schema's identity without being it."""
    echo: str


Claims.__ai_schema__ = connection.Ping.__ai_schema__


class _Plain:
    """A value that is not a class: it has no `__name__`, so it is named by its words."""
    def __str__(self):
        return "a plain value"


@pytest.mark.parametrize("schema,named", [(Loose, "Loose"), (Claims, "Claims"),
                                          (_Plain(), "a plain value")],
                         ids=["unregistered", "claims-an-identity", "not-a-class"])
def test_a_schema_that_is_not_the_registered_one_is_refused_naming_it(world, schema, named):
    words = f"{named} is not a registered AI schema"
    assert _ask(world, schema=schema) == _refused("schema", words) and world.sent == []
    assert _row() == dict(ASKED, verdict="schema", detail=words)


def test_a_prompt_that_does_not_load_is_refused_in_its_words(world):
    with pytest.raises(prompts.PromptError) as missing:
        prompts.load("no_such_prompt", 1)
    words = str(missing.value)
    assert _ask(world, prompt=("no_such_prompt", 1)) == _refused("prompt", words)
    assert _row() == dict(ASKED, prompt="no_such_prompt.v1", schema="ping.v1",
                          verdict="prompt", detail=words)


def test_a_stored_secret_left_after_masking_is_refused_before_the_request_is_kept(
        world, monkeypatch):
    from modules import redact
    monkeypatch.setattr(redact, "contains_known_secret",
                        lambda payload: ["default:password", "snmp:community"])
    words = ("a stored secret is still in the request after masking (default:password, "
             "snmp:community); nothing was sent")
    assert _ask(world) == _refused("unmasked_secret", words) and world.sent == []
    assert _row() == dict(ASKED, schema="ping.v1", prompt_sha256=SHA,
                          verdict="unmasked_secret", detail=words)


def test_a_prompt_over_its_bound_is_refused_with_its_estimate_and_the_long_tier(world):
    bound = profiles.TASKS["connection_check"]["max_prompt_tokens"]
    got = _ask(world, parts={"word": "w", "pack": "x" * (bound * 4)})
    row = _row()
    est = gateway.prompt_tokens(row["request"])
    words = (f"this prompt is about {est} tokens, over the task's bound of {bound} "
             f"({MODEL} charges every rate at its long tier over "
             f"{profiles.profile(MODEL)['long_prompt_tokens']}); nothing was sent")
    assert got == _refused("prompt_too_long", words) and world.sent == []
    assert row == dict(ASKED, schema="ping.v1", prompt_sha256=SHA, request=row["request"],
                       verdict="prompt_too_long", detail=words, prompt_tokens=est)
    assert row["request"]["messages"][0]["content"].count("x" * 100) > 0


def test_a_model_with_no_long_tier_says_none(world, monkeypatch):
    monkeypatch.setattr(profiles, "profile", lambda model: {"provider": profiles.ANTHROPIC})
    bound = profiles.TASKS["connection_check"]["max_prompt_tokens"]
    got = _ask(world, parts={"word": "w", "pack": "x" * (bound * 4)})
    est = _row()["prompt_tokens"]
    assert got["detail"] == (f"this prompt is about {est} tokens, over the task's bound of "
                             f"{bound}; nothing was sent")


def test_a_prompt_at_its_bound_is_sent(world, monkeypatch):
    body = _request(world)
    est = gateway.prompt_tokens(body)
    monkeypatch.setitem(profiles.TASKS, "connection_check",
                        dict(profiles.TASKS["connection_check"], max_prompt_tokens=est))
    world.answer = _answer('{"echo": "w"}')
    assert _ask(world)["ok"] is True and len(world.sent) == 1


def test_a_worst_case_over_the_call_cap_is_refused_with_both_operands(world, monkeypatch):
    body = _request(world)
    worst = gateway.worst_case_usd(MODEL, body)
    monkeypatch.setattr(profiles, "cap_per_call", lambda name: worst / 2)
    words = (f"this call's worst case ${worst:.4f} is over the connection_check task's "
             f"per-call cap ${worst / 2:.4f}")
    assert _ask(world) == _refused("over_cap", words) and world.sent == []
    assert _row() == dict(ASKED, schema="ping.v1", prompt_sha256=SHA, request=body,
                          verdict="over_cap", detail=words, worst_usd=worst)


def test_a_worst_case_at_the_call_cap_is_sent(world, monkeypatch):
    body = _request(world)
    monkeypatch.setattr(profiles, "cap_per_call",
                        lambda name: gateway.worst_case_usd(MODEL, body))
    world.answer = _answer('{"echo": "w"}')
    assert _ask(world)["ok"] is True and len(world.sent) == 1


def _spent(monkeypatch, usd, state="ok", error=""):
    days = []

    def spent(day):
        days.append(day)
        return {"state": state, "usd": usd, "calls": 1, "error": error}
    monkeypatch.setattr(calls, "spent_usd", spent)
    return days


def test_an_unreadable_record_is_refused_in_its_words(world, monkeypatch):
    body = _request(world)
    days = _spent(monkeypatch, None, "unreadable", "a torn line at 3")
    words = ("the record of AI calls cannot be read, so today's spend is unknown (a torn line "
             "at 3); nothing was sent")
    assert _ask(world) == _refused("over_cap", words) and world.sent == []
    assert _row() == dict(ASKED, schema="ping.v1", prompt_sha256=SHA, request=body,
                          verdict="over_cap", detail=words)
    assert days == ["2026-10-25"], "the day given is the day counted"


def test_the_day_cap_is_refused_with_its_three_operands(world, monkeypatch):
    body = _request(world)
    worst = gateway.worst_case_usd(MODEL, body)
    _spent(monkeypatch, 1.5 - worst / 2)
    words = (f"today's spend ${1.5 - worst / 2:.4f} plus this call's worst case ${worst:.4f} "
             f"is over the day cap ${1.5:.4f}")
    assert _ask(world) == _refused("over_cap", words) and world.sent == []
    assert _row() == dict(ASKED, schema="ping.v1", prompt_sha256=SHA, request=body,
                          verdict="over_cap", detail=words, worst_usd=worst)


def test_a_days_spend_reaching_the_cap_exactly_is_sent(world, monkeypatch):
    body = _request(world)
    worst = gateway.worst_case_usd(MODEL, body)
    world.settings["ai_cap_usd_per_day"] = worst
    _spent(monkeypatch, 0.0)
    world.answer = _answer('{"echo": "w"}')
    assert _ask(world)["ok"] is True and len(world.sent) == 1


def test_with_no_day_given_the_utc_day_is_counted(world, monkeypatch):
    """A clock whose local day is a day behind UTC's (19:00 the day before) is not read."""
    import datetime
    import types
    utc_now = datetime.datetime(2026, 10, 26, 1, 0, tzinfo=datetime.timezone.utc)

    class Clock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is datetime.timezone.utc:
                return utc_now
            return (utc_now - datetime.timedelta(hours=6)).replace(tzinfo=None)
    monkeypatch.setattr(gateway, "datetime", types.SimpleNamespace(
        datetime=Clock, timezone=datetime.timezone))
    days = _spent(monkeypatch, 0.0)
    world.answer = _answer('{"echo": "w"}')
    _ask(world, today=None)
    assert days == ["2026-10-26"]


def test_a_record_that_says_nothing_is_not_recorded(world, monkeypatch):
    world.settings.pop("ai_hosted")
    monkeypatch.setattr(calls, "record", lambda row: {})
    assert _ask(world)["recorded"] is False


# ---------------------------------------------------------------- sent

def test_a_provider_failure_is_refused_with_its_attempts_and_headers(world):
    body = _request(world)

    def down(body, key):
        assert key == KEY
        raise A.Overloaded("HTTP 529 after 3 attempts: busy", status=529, attempts=3,
                           headers={"retry-after": "3"})
    assert _ask(world, send=down) == _refused("overloaded", "HTTP 529 after 3 attempts: busy")
    assert _row() == dict(ASKED, schema="ping.v1", prompt_sha256=SHA, request=body,
                          verdict="overloaded", detail="HTTP 529 after 3 attempts: busy",
                          attempts=3, ratelimit={"retry-after": "3"})


def _sending(reply_body, latency=0.1234567, attempts=2, headers=None):
    sent = []

    def send(body, key):
        sent.append((body, key))
        return A.Reply(status=200, body=reply_body, attempts=attempts, latency_s=latency,
                       headers=headers if headers is not None else {"x-ratelimit-limit": "50"})
    return send, sent


USAGE = {"input_tokens": 120, "output_tokens": 8, "cache_read_input_tokens": 1000,
         "cache_creation_input_tokens": 30}


def test_an_answer_is_returned_and_recorded_whole(world):
    body = _request(world)
    send, sent = _sending(_answer('{"echo": "w"}', usage=dict(USAGE)))
    got = _ask(world, send=send)
    cost = profiles.cost_usd(MODEL, 120, 8, cache_write_tokens=30, cache_read_tokens=1000)
    assert got == {"ok": True, "output": connection.Ping(echo="w"), "call_id": CALL_ID,
                   "cost_usd": cost, "recorded": True}
    assert sent == [(body, KEY)]
    assert _row() == dict(ASKED, schema="ping.v1", prompt_sha256=SHA, request=body,
                          cost_usd=cost, price=profiles.prices_for(MODEL, 1150),
                          tokens=USAGE, latency_s=0.123, attempts=2,
                          ratelimit={"x-ratelimit-limit": "50"}, stop_reason="end_turn",
                          response='{"echo": "w"}', verdict="ok", output={"echo": "w"})


# ------------------------------------------- thinking per task (the batched gateway change)

def test_a_task_naming_no_thinking_sends_none_and_its_request_is_unchanged(world):
    """The model's default ("adaptive") sends no `thinking` at all: the body is the one every
    call made before the change, byte for byte (the cached prefix's bytes included)."""
    body = _request(world)
    assert "thinking" not in body
    assert set(body) == {"model", "max_tokens", "system", "messages", "output_config"}


def test_thinking_off_sends_the_model_s_own_form_and_records_it(world):
    send, sent = _sending(_answer('{"echo": "w"}'))
    got = gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                      actor=ACTOR, send=send, today="2026-10-25", thinking="off")
    assert got["ok"] is True
    ((body, _key),) = sent
    assert body["thinking"] == {"type": "disabled"} == profiles.MODELS[MODEL]["thinking_off"]
    assert _row()["thinking"] == "off"


def test_a_task_s_pin_names_its_thinking(world, monkeypatch):
    monkeypatch.setitem(profiles.TASKS, "connection_check",
                        dict(profiles.TASKS["connection_check"], thinking="off"))
    send, sent = _sending(_answer('{"echo": "w"}'))
    assert _ask(world, send=send)["ok"] is True
    assert sent[0][0]["thinking"] == {"type": "disabled"}
    open(calls._path(), "w").close()
    send, sent = _sending(_answer('{"echo": "w"}'))
    assert gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                       actor=ACTOR, send=send, today="2026-10-25",
                       thinking="adaptive")["ok"] is True
    assert "thinking" not in sent[0][0], "a measurement's ask replaces the pin for one call"


def test_a_thinking_not_known_is_refused_before_anything_is_sent(world):
    got = gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                      actor=ACTOR, send=world.send, today="2026-10-25", thinking="low")
    words = "thinking 'low' is not one of adaptive, off; nothing was sent"
    assert got == _refused("thinking", words) and world.sent == []
    assert _row() == dict(BASE, thinking="low", verdict="thinking", detail=words)


def test_thinking_off_on_a_model_with_no_way_to_turn_it_off_is_refused(world, monkeypatch):
    monkeypatch.setitem(profiles.MODELS, MODEL,
                        {k: v for k, v in profiles.MODELS[MODEL].items() if k != "thinking_off"})
    got = gateway.ask("connection_check", ("ping", 1), connection.Ping, {"word": "w"},
                      actor=ACTOR, send=world.send, today="2026-10-25", thinking="off")
    words = f"{MODEL}'s profile names no way to turn thinking off; nothing was sent"
    assert got == _refused("thinking", words) and world.sent == []


def test_every_model_s_thinking_off_is_its_documented_form():
    """Haiku 5.5 takes `disabled`; Sonnet 5.5 refuses it and takes `between_tools` (the
    claude-api reference, read 2026-10-25); no task pins a thinking its model cannot take."""
    assert profiles.MODELS["claude-haiku-5-5"]["thinking_off"] == {"type": "disabled"}
    assert profiles.MODELS["claude-sonnet-5-5"]["thinking_off"] == {"type": "between_tools"}
    for name, pin in profiles.TASKS.items():
        mode = pin.get("thinking", "adaptive")
        assert mode in profiles.THINKING, name
        assert mode == "adaptive" or profiles.MODELS[pin["model"]].get("thinking_off"), name


def test_build_request_sends_the_pin_s_settings_only_when_it_names_them():
    p, pin = {"text": "p"}, dict(profiles.TASKS["connection_check"], max_tokens=8)
    prof = profiles.MODELS[MODEL]
    plain = gateway.build_request(p, connection.Ping, {"a": "b"}, pin, profile=prof)
    assert "thinking" not in plain and "temperature" not in plain
    assert plain["model"] == MODEL and plain["max_tokens"] == 8
    got = gateway.build_request(p, connection.Ping, {"a": "b"},
                                dict(pin, thinking="off", temperature=1), profile=prof)
    assert got["thinking"] == {"type": "disabled"} and got["temperature"] == 1


def test_a_pin_s_temperature_its_model_takes_is_sent(world, monkeypatch):
    monkeypatch.setitem(profiles.TASKS, "connection_check",
                        dict(profiles.TASKS["connection_check"], temperature=1))
    send, sent = _sending(_answer('{"echo": "w"}'))
    assert _ask(world, send=send)["ok"] is True
    assert sent[0][0]["temperature"] == 1


def test_a_pin_s_temperature_its_model_refuses_is_refused_before_anything_is_sent(
        world, monkeypatch):
    """Haiku 5.5 takes only its default, 1 (any other is a 400): a pin naming 0.2 is refused
    here, naming both, never sent to fail there."""
    monkeypatch.setitem(profiles.TASKS, "connection_check",
                        dict(profiles.TASKS["connection_check"], temperature=0.2))
    words = (f"the pin's temperature 0.2 is not one {MODEL} takes ([1]); nothing was sent")
    assert _ask(world) == _refused("temperature", words) and world.sent == []


def test_every_pin_file_is_exactly_its_keys_and_every_task_has_one(tmp_path):
    """The operator, 2026-10-25: a task's request settings are its pin file's, so tuning is an
    edit to the file. A file with a key missing or added is refused at load, naming it."""
    assert sorted(profiles.TASKS) == ["connection_check", "explain", "intent_patch",
                                      "nl_query"]
    for name, pin in profiles.TASKS.items():
        assert sorted(pin) == sorted(profiles.PIN_KEYS), name
        assert pin["temperature"] is None or pin["temperature"] in \
            profiles.MODELS[pin["model"]]["temperatures"], name
    good = json.loads(open(f"{profiles.PINS}/nl_query.json", encoding="utf-8").read())
    (tmp_path / "t.json").write_text(json.dumps(dict(good, max_tokens=99)))
    assert profiles.load_pins(str(tmp_path)) == {"t": dict(good, max_tokens=99)}
    (tmp_path / "t.json").write_text(json.dumps({k: v for k, v in good.items() if k != "why"}))
    with pytest.raises(ValueError, match="pin t.json: keys"):
        profiles.load_pins(str(tmp_path))


def test_a_pin_file_s_value_is_what_the_request_carries(world, monkeypatch, tmp_path):
    """The point of the file: a value changed there reaches the body with no code changed."""
    good = json.loads(open(f"{profiles.PINS}/connection_check.json", encoding="utf-8").read())
    (tmp_path / "connection_check.json").write_text(json.dumps(dict(good, max_tokens=77,
                                                                    thinking="off")))
    monkeypatch.setattr(profiles, "TASKS", profiles.load_pins(str(tmp_path)))
    send, sent = _sending(_answer('{"echo": "w"}'))
    assert _ask(world, send=send)["ok"] is True
    assert sent[0][0]["max_tokens"] == 77 and sent[0][0]["thinking"] == {"type": "disabled"}


def test_the_prices_charged_are_the_tier_of_every_prompt_token_counted(world):
    """Haiku 5.5's long tier is over 100,000 prompt tokens, cache writes and reads included:
    60,000 + 30,000 + 20,000 is over it, though no two of them are."""
    usage = {"input_tokens": 60_000, "output_tokens": 8, "cache_read_input_tokens": 20_000,
             "cache_creation_input_tokens": 30_000}
    send, _ = _sending(_answer('{"echo": "w"}', usage=usage))
    _ask(world, send=send)
    row = _row()
    assert row["price"] == profiles.prices_for(MODEL, 110_000) and row["price"]["tier"] == "long"


def test_an_answer_whose_record_says_nothing_is_not_recorded(world, monkeypatch):
    send, _ = _sending(_answer('{"echo": "w"}'))
    monkeypatch.setattr(calls, "record", lambda row: {})
    got = _ask(world, send=send)
    assert got["ok"] is True and got["recorded"] is False


@pytest.fixture
def dated(monkeypatch):
    """A registered schema with a field JSON writes differently from its Python value."""
    import datetime
    from modules.ai import schemas
    monkeypatch.setattr(schemas, "REGISTRY", dict(schemas.REGISTRY))

    @schemas.register("dated_plant", 1)
    class Dated(schemas.StrictModel):
        on: datetime.date
    return Dated


def test_the_output_is_recorded_as_json_writes_it(world, dated):
    send, _ = _sending(_answer('{"on": "2026-10-25"}'))
    got = _ask(world, schema=dated, send=send)
    assert got["ok"] is True and got["recorded"] is True
    assert _row()["output"] == {"on": "2026-10-25"}


def test_an_answer_wrong_deep_inside_names_its_path(world):
    from modules.ai import explain
    text = json.dumps({"outcome": "answer", "rationale": "r", "needs_human": False,
                       "why_not": "", "hypotheses": [{"claim": 5, "evidence_refs": [],
                                                      "confirm_with": ""}]})
    with pytest.raises(ValidationError) as exc:
        explain.Explanation.model_validate_json(text)
    first = exc.value.errors()[0]
    assert first["loc"] == ("hypotheses", 0, "claim")
    send, _ = _sending(_answer(text))
    got = _ask(world, schema=explain.Explanation, send=send)
    assert got["detail"] == f"the answer is not explain.v1: hypotheses.0.claim: {first['msg']}"


def test_an_answer_with_no_usage_and_no_stop_reason_counts_nothing_and_says_none(world):
    reply = _answer('{"echo": "w"}')
    del reply["usage"], reply["stop_reason"]
    send, _ = _sending(reply, headers={})
    got = _ask(world, send=send)
    row = _row()
    assert got["ok"] is True and got["cost_usd"] == 0.0
    assert row["tokens"] == {"input_tokens": 0, "output_tokens": 0,
                             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    assert row["stop_reason"] == "" and row["ratelimit"] == {} and row["cost_usd"] == 0.0


def test_a_usage_of_none_counts_as_none(world):
    send, _ = _sending(_answer('{"echo": "w"}', usage={"input_tokens": None,
                                                       "output_tokens": 8}))
    _ask(world, send=send)
    assert _row()["tokens"] == {"input_tokens": 0, "output_tokens": 8,
                                "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}


def test_the_answer_kept_is_masked_for_egress(world):
    from modules import redact
    text = '{"echo": "snmp-server community plantedCommunity99 RO"}'
    send, _ = _sending(_answer(text))
    _ask(world, send=send)
    row = _row()
    assert row["response"] == redact.redact_egress(text) and "plantedCommunity99" not in \
        row["response"]


def _failed(world, reply, kind, words):
    send, _ = _sending(reply)
    cost = profiles.cost_usd(MODEL, 120, 8)
    assert _ask(world, send=send) == {"ok": False, "error": kind, "detail": words,
                                      "call_id": CALL_ID, "cost_usd": cost, "recorded": True}
    row = _row()
    assert row["verdict"] == kind and row["detail"] == words and row["cost_usd"] == cost
    assert "output" not in row and row["response"] == reply["content"][0]["text"]


def test_a_refusal_is_said_with_its_category(world):
    _failed(world, _answer("", stop="refusal", stop_details={"category": "cyber"}),
            "refusal", "the model declined (category cyber)")


@pytest.mark.parametrize("extra", [{}, {"stop_details": None}, {"stop_details": {}}])
def test_a_refusal_with_no_category_says_none_given(world, extra):
    _failed(world, _answer("", stop="refusal", **extra), "refusal",
            "the model declined (category none given)")


def test_an_answer_past_max_tokens_names_the_bound(world):
    _failed(world, _answer('{"echo": "w', stop="max_tokens"), "max_tokens",
            f"the answer ran past max_tokens "
            f"({profiles.TASKS['connection_check']['max_tokens']})")


def _pydantic_says(text):
    with pytest.raises(ValidationError) as exc:
        connection.Ping.model_validate_json(text)
    return exc.value.errors()[0]


def test_an_answer_not_the_schema_names_where_and_why(world):
    first = _pydantic_says('{"echo": 5}')
    assert first["loc"] == ("echo",)
    _failed(world, _answer('{"echo": 5}'), "schema",
            f"the answer is not ping.v1: echo: {first['msg']}")


def test_an_answer_that_is_not_json_is_the_answer_at_fault(world):
    first = _pydantic_says("not json at all")
    assert first["loc"] == ()
    _failed(world, _answer("not json at all"), "schema",
            f"the answer is not ping.v1: the answer: {first['msg']}")
