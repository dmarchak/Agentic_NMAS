"""The pins and prices every call is costed and capped by (`modules/ai/profiles.py`), and the
connection check's one call (`modules/ai/connection.py`), held to their exact answers: the
irreversible tier's egress path (PHASE8_PLAN 15.12). Written from tier run #64's survivors
(2026-10-25): tests/test_ai_gateway.py holds the prices themselves, and this file the words a
lookup refuses in, the long tier's threshold and the exact division, which recorded cases are
off their pin, the prices' age by the UTC day, the AI card's table row whole, and what Test
connection sends and answers.
"""
import datetime
import json
import re
import types

import pytest

from modules.ai import calls, connection, profiles
from tests.test_ai_gateway import own_record, world  # noqa: F401 (fixtures)


# ---------------------------------------------------------------- lookups

def test_a_model_with_no_profile_is_refused_naming_every_known_model():
    assert len(profiles.MODELS) > 1, "the list's separator is seen only between two"
    with pytest.raises(KeyError) as missing:
        profiles.profile("no-such-model")
    assert missing.value.args == (f"no model profile for 'no-such-model'; known: "
                                  f"{', '.join(sorted(profiles.MODELS))}",)


def test_a_task_no_pin_names_is_refused_naming_every_known_task():
    assert profiles.task("nl_query") is profiles.TASKS["nl_query"]
    with pytest.raises(KeyError) as missing:
        profiles.task("no_such_task")
    assert missing.value.args == (f"no task 'no_such_task'; known: "
                                  f"{', '.join(sorted(profiles.TASKS))}",)


# ---------------------------------------------------------------- cost

def test_a_cost_is_its_rates_per_million_exactly():
    assert profiles.cost_usd("claude-sonnet-5-5", 1_000_000, 0) == 2.00
    assert profiles.cost_usd("claude-sonnet-5-5", 0, 1_000_000) == 10.00
    assert profiles.cost_usd("claude-sonnet-5-5", 0, 0, cache_write_tokens=1_000_000) == 2.50


def test_the_long_tier_counts_cache_writes_into_the_prompt():
    """Haiku 5.5 bills a prompt over 100,000 tokens at its long tier, cache writes included:
    60,000 input and 50,000 written is 110,000, over it, though the input alone is not."""
    got = profiles.cost_usd("claude-haiku-5-5", 60_000, 0, cache_write_tokens=50_000)
    assert got == pytest.approx((60_000 * 0.50 + 50_000 * 0.625) / 1_000_000, rel=1e-12)


# ---------------------------------------------------------------- recorded cases off their pin

def test_a_file_beside_the_task_folders_is_passed_over_and_the_folders_still_read(tmp_path):
    (tmp_path / "a_note.txt").write_text("the folders' own notes")   # sorts before them
    (tmp_path / "nl_query").mkdir()
    (tmp_path / "nl_query" / "a.json").write_text(json.dumps({"model": "claude-sonnet-5-5"}))
    assert profiles.cases_off_pin(str(tmp_path)) == [
        (str(tmp_path / "nl_query" / "a.json"), "claude-sonnet-5-5", "claude-haiku-5-5")]


def test_a_case_naming_no_model_is_off_its_pin_with_no_model(tmp_path):
    (tmp_path / "nl_query").mkdir()
    (tmp_path / "nl_query" / "a.json").write_text(json.dumps({"question": "q"}))
    (tmp_path / "nl_query" / "b.json").write_text("null")
    assert profiles.cases_off_pin(str(tmp_path)) == [
        (str(tmp_path / "nl_query" / "a.json"), "", "claude-haiku-5-5"),
        (str(tmp_path / "nl_query" / "b.json"), "", "claude-haiku-5-5")]


def test_a_case_in_the_operators_words_is_read(tmp_path):
    """A case holds the operator's words (a non-ASCII question), read as JSON reads bytes."""
    (tmp_path / "nl_query").mkdir()
    (tmp_path / "nl_query" / "a.json").write_bytes(json.dumps(
        {"question": "Débit sur r1 › Gi1", "model": "claude-sonnet-5-5"},
        ensure_ascii=False).encode("utf-8"))
    assert profiles.cases_off_pin(str(tmp_path)) == [
        (str(tmp_path / "nl_query" / "a.json"), "claude-sonnet-5-5", "claude-haiku-5-5")]


def test_a_case_saved_with_a_byte_order_mark_is_read(tmp_path):
    """An editor that writes UTF-8 with a byte-order mark (Notepad's default) leaves a case
    JSON's reading of bytes still reads; a text read would hand JSON the mark."""
    (tmp_path / "nl_query").mkdir()
    (tmp_path / "nl_query" / "a.json").write_bytes(
        b"\xef\xbb\xbf" + json.dumps({"model": "claude-sonnet-5-5"}).encode("utf-8"))
    assert profiles.cases_off_pin(str(tmp_path)) == [
        (str(tmp_path / "nl_query" / "a.json"), "claude-sonnet-5-5", "claude-haiku-5-5")]


def test_no_cases_folder_is_no_case(tmp_path):
    assert profiles.cases_off_pin(str(tmp_path / "absent")) == []


# ---------------------------------------------------------------- the prices' age, the card's table

def test_the_prices_age_is_counted_by_the_utc_day(monkeypatch):
    """With no day given, the age is the UTC day's: a clock whose local day is a day behind
    UTC's (19:00 the day before) is not read."""
    as_of = datetime.date.fromisoformat(profiles.PRICES_AS_OF)
    utc_now = datetime.datetime.combine(as_of + datetime.timedelta(days=10),
                                        datetime.time(1, 0), datetime.timezone.utc)

    class Clock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is datetime.timezone.utc:
                return utc_now
            return (utc_now - datetime.timedelta(hours=6)).replace(tzinfo=None)
    monkeypatch.setattr(profiles, "datetime", types.SimpleNamespace(
        datetime=Clock, date=datetime.date, timezone=datetime.timezone))
    assert profiles.prices_age_days() == 10


def _day(days_after):
    return (datetime.date.fromisoformat(profiles.PRICES_AS_OF)
            + datetime.timedelta(days=days_after)).isoformat()


def test_prices_are_stale_only_past_their_bound():
    at = profiles.table(today=_day(profiles.PRICES_STALE_DAYS))
    assert at["stale"] is False and at["age_days"] == profiles.PRICES_STALE_DAYS
    assert profiles.table(today=_day(profiles.PRICES_STALE_DAYS + 1))["stale"] is True


def test_the_cards_table_is_each_task_s_pin_its_model_and_its_cap_whole():
    got = profiles.table(today=profiles.PRICES_AS_OF)
    assert {k: v for k, v in got.items() if k != "rows"} == {
        "as_of": profiles.PRICES_AS_OF, "source": profiles.PRICES_SOURCE, "age_days": 0,
        "stale": False, "stale_days": profiles.PRICES_STALE_DAYS}
    rows = {r["task"]: r for r in got["rows"]}
    assert [r["task"] for r in got["rows"]] == sorted(profiles.TASKS)
    assert rows["connection_check"] == {
        "task": "connection_check", "words": "Test connection", "model": "claude-haiku-5-5",
        "model_words": "Claude Haiku 5.5", "price": profiles.MODELS["claude-haiku-5-5"]["price"],
        "long_prompt_tokens": 100_000, "max_prompt_tokens": 2_000, "max_tokens": 64,
        "cap_usd": profiles.cap_per_call("connection_check")}
    sonnet = [r for r in got["rows"] if r["model"] == "claude-sonnet-5-5"]
    assert sonnet and all(r["long_prompt_tokens"] is None for r in sonnet), \
        "a model with no long tier says none"


# ---------------------------------------------------------------- Test connection

WORD = re.compile(r'<data name="word">\n(mercury-[0-9a-f]{8})\n</data>')


def _word(world):
    m = WORD.fullmatch(world.sent[-1]["body"]["messages"][0]["content"])
    assert m, world.sent[-1]["body"]["messages"][0]["content"]
    return m.group(1)


def _answering(world, echo=None):
    """A send that answers with the word it was sent (or *echo*)."""
    def send(body, key):
        world.sent.append({"body": body})
        word = WORD.fullmatch(body["messages"][0]["content"]).group(1)
        world.answer = {"content": [{"type": "text", "text": json.dumps(
            {"echo": word if echo is None else echo})}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 120, "output_tokens": 8}}
        return _reply(world.answer)
    return send


def _reply(body):
    from modules.ai import anthropic_adapter as A
    return A.Reply(status=200, body=body, attempts=1, latency_s=0.1)


def test_the_check_sends_one_word_of_its_own_as_the_data_named_word(world):
    got = connection.check(actor="a", send=_answering(world), today="2026-10-25")
    (row,) = calls.read()["rows"]
    assert got == {"ok": True, "detail": f"answered, ${row['cost_usd']:.5f}",
                   "call_id": row["id"], "cost_usd": row["cost_usd"]}
    first = _word(world)
    connection.check(actor="a", send=_answering(world), today="2026-10-25")
    assert _word(world) != first, "a new word each check"


def test_a_wrong_echo_is_refused_naming_both_its_first_40_characters(world):
    echo = "x" * 39 + "yz" + "w" * 9
    got = connection.check(actor="a", send=_answering(world, echo=echo), today="2026-10-25")
    (row,) = calls.read()["rows"]
    assert got == {"ok": False, "error": "schema", "call_id": row["id"],
                   "detail": f"the answer echoed {echo[:40]!r}, not {_word(world)!r}"}
    assert echo[:40].endswith("y")


def test_the_check_counts_the_day_it_is_given(world, monkeypatch):
    days = []
    monkeypatch.setattr(calls, "spent_usd", lambda day: days.append(day) or {
        "state": "ok", "usd": 0.0, "calls": 0, "error": ""})
    connection.check(actor="a", send=_answering(world), today="2026-10-21")
    assert days == ["2026-10-21"]


def test_a_refused_check_is_the_gateway_s_answer_unchanged(world):
    world.settings.pop("ai_hosted")
    got = connection.check(actor="a", send=_answering(world), today="2026-10-25")
    assert got["ok"] is False and got["error"] == "ai_off" and world.sent == []
    assert set(got) == {"ok", "error", "detail", "call_id", "recorded"}
