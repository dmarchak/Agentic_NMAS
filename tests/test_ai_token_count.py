"""The provider's token count before every AI call, and the calibrated fallback (C1898; the
operator's decision of 2026-10-28; `anthropic_adapter.count_tokens`, `gateway.Counter`).

- **The adapter** asks `POST /v1/messages/count_tokens` with the send's own key handling and
  its own short bound, the request's countable fields only (never ``max_tokens`` or
  ``temperature``); a 200 is its ``input_tokens``; every failure is its own kind, never
  retried; the key is in no error.
- **The gateway** measures the masked request after every gate, with the provider's count when
  it answers (the row says ``counted``), else the fallback estimate (the row says
  ``estimated`` and why: an error, a timeout, rate-limited); the count is what the prompt's
  bound and the caps' worst case are judged on; a counted prompt over the bound sends nothing,
  its words saying it was counted. A call a gate refuses is never counted.
- **The fallback** (`gateway.CHARS_PER_TOKEN`) is at least the real input of every recorded
  call: a committed sample of the calibration's dataset (tests/fixtures/ai_calibration/, the
  tightest rows of each feature and model, numbers only) and the whole set's numbers
  (`gateway.CALIBRATION`).
- **The selectors** that fit a request to its bound (`nl_query.select_context`,
  `explain.budgeted`) measure by the same counter: a request the count fits is kept where the
  fallback would trim it; a counter whose call's gates fail counts nothing and says why; one
  press asks at most `gateway.MAX_COUNTS` counts.
"""
import csv
import json
import os

import pytest
import requests

from modules.ai import anthropic_adapter as A
from modules.ai import calls, connection, gateway, nl_query, profiles, triggers
from tests.ai_person import pressed_by
from tests.test_ai_gateway import KEY, own_record, world  # noqa: F401 (fixtures)

ACTOR = "operator@example.com"
SAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "ai_calibration",
                      "calls_sample.tsv")
PING = {"content": [{"type": "text", "text": '{"echo": "w"}'}], "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 5}}


class _Resp:
    def __init__(self, status, body=None, headers=None, text=""):
        self.status_code, self._body, self.headers, self.text = status, body, headers or {}, text

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class _Session:
    def __init__(self, *responses):
        self.responses, self.sent = list(responses), []

    def post(self, url, json=None, headers=None, timeout=None):
        self.sent.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


BODY = {"model": "claude-haiku-5-5", "max_tokens": 64, "temperature": 1,
        "system": [{"type": "text", "text": "s", "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": "<data>x</data>"}],
        "thinking": {"type": "disabled"},
        "output_config": {"format": {"type": "json_schema", "schema": {}}}}


# ── the adapter ───────────────────────────────────────────────────────────────────────────

def test_the_count_is_asked_of_the_count_endpoint_with_the_sends_key_and_its_own_bound():
    s = _Session(_Resp(200, {"input_tokens": 412}, {"anthropic-ratelimit-requests-remaining":
                                                    "4999", "content-type": "x"}))
    got = A.count_tokens(BODY, KEY, session=s)
    assert got.tokens == 412 and got.headers == {"anthropic-ratelimit-requests-remaining": "4999"}
    (sent,) = s.sent
    assert sent["url"] == "https://api.anthropic.com/v1/messages/count_tokens" == A.COUNT_URL
    assert sent["headers"] == {"x-api-key": KEY, "anthropic-version": "2023-06-01",
                               "content-type": "application/json"}
    assert sent["timeout"] == A.COUNT_TIMEOUT == (5.0, 10.0)
    # The same bytes as the send, but for what the endpoint takes none of.
    assert sent["json"] == {k: v for k, v in BODY.items() if k not in ("max_tokens",
                                                                        "temperature")}


@pytest.mark.parametrize("item,cls", [
    (_Resp(429, {"error": {"type": "rate_limit_error", "message": "slow"}},
           {"retry-after": "1"}), A.RateLimited),
    (_Resp(529, {"error": {"type": "overloaded_error", "message": "busy"}}), A.Overloaded),
    (_Resp(401, {"error": {"type": "authentication_error", "message": "bad key"}}),
     A.KeyRefused),
    (_Resp(400, {"error": {"type": "invalid_request_error", "message": "bad"}}), A.BadRequest),
    (_Resp(500, {"error": {"type": "api_error", "message": "oops"}}), A.ProviderDown),
    (_Resp(200, None, text="<html>"), A.ProviderDown),
    (_Resp(200, {"input_tokens": "412"}), A.ProviderDown),
    (_Resp(200, {"input_tokens": True}), A.ProviderDown),
    (_Resp(200, {"input_tokens": -1}), A.ProviderDown),
    (_Resp(200, ["input_tokens"]), A.ProviderDown),
    (requests.Timeout("t"), A.ProviderDown),
    (requests.ConnectionError("c"), A.ProviderDown),
])
def test_every_count_failure_is_its_own_kind_and_never_retried(item, cls):
    s = _Session(item, _Resp(200, {"input_tokens": 1}))
    with pytest.raises(cls) as got:
        A.count_tokens(BODY, KEY, session=s)
    assert len(s.sent) == 1 and KEY not in str(got.value)
    assert type(got.value) is cls


def test_a_count_with_no_key_asks_nothing():
    s = _Session()
    with pytest.raises(A.KeyRefused):
        A.count_tokens(BODY, "", session=s)
    assert s.sent == []


# ── the gateway ───────────────────────────────────────────────────────────────────────────

def _ask(world, parts=None, count=None):
    world.answer = PING
    with pressed_by(ACTOR):
        return gateway.ask("connection_check", ("ping", 1), connection.Ping,
                           parts or {"word": "w"}, actor=ACTOR,
                           trigger=triggers.person(ACTOR), send=world.send,
                           today="2026-10-25", count=count)


def _row():
    (row,) = calls.read()["rows"]
    return row


def test_the_count_is_used_when_it_answers(world):
    asked = []

    def count(body, key):
        asked.append((body, key))
        return A.Count(tokens=77, latency_s=0.25)
    assert _ask(world, count=count)["ok"] is True
    (body, key), = asked
    assert key == KEY and body == world.sent[0]["body"], "the masked request the send carries"
    row = _row()
    assert row["prompt_tokens"] == 77
    assert row["prompt_count"] == {"how": "counted", "why": "", "latency_s": 0.25}


@pytest.mark.parametrize("exc,kind", [
    (A.RateLimited("HTTP 429: rate_limit_error: slow", status=429), "rate_limited"),
    (A.ProviderDown("no count within 10 s (ReadTimeout)"), "provider_down"),
    (RuntimeError("a fault in the count"), "RuntimeError"),
])
def test_the_fallback_is_used_and_said_when_the_count_fails(world, exc, kind):
    def count(body, key):
        raise exc
    assert _ask(world, count=count)["ok"] is True and len(world.sent) == 1
    row = _row()
    assert row["prompt_tokens"] == gateway.prompt_tokens(world.sent[0]["body"])
    assert row["prompt_count"] == {
        "how": "estimated", "chars_per_token": gateway.CHARS_PER_TOKEN,
        "why": f"the provider's count failed ({kind}: {exc}); the fallback over-estimate is "
               "used"}


def test_nothing_is_sent_when_the_counted_prompt_is_over_the_bound(world):
    bound = profiles.TASKS["connection_check"]["max_prompt_tokens"]
    got = _ask(world, count=lambda body, key: A.Count(tokens=bound + 1))
    assert got["error"] == "prompt_too_long" and world.sent == []
    assert got["detail"].startswith(f"this prompt is {bound + 1} tokens (counted by the "
                                    f"provider), over the task's bound of {bound}")
    assert _ask(world, count=lambda body, key: A.Count(tokens=bound))["ok"] is True


def test_a_fallback_over_the_bound_says_it_was_estimated_and_why(world):
    bound = profiles.TASKS["connection_check"]["max_prompt_tokens"]

    def count(body, key):
        raise A.Overloaded("HTTP 529: busy", status=529)
    got = _ask(world, parts={"word": "w", "pack": "x" * int(bound * 2)}, count=count)
    assert got["error"] == "prompt_too_long" and world.sent == []
    est = _row()["prompt_tokens"]
    assert got["detail"] == (
        f"this prompt is {est} tokens (by the fallback estimate, {gateway.CHARS_PER_TOKEN} "
        "characters a token (the provider's count failed (overloaded: HTTP 529: busy); the "
        "fallback over-estimate is used)), over the task's bound of "
        f"{bound} (claude-haiku-5-5 charges every rate at its long tier over 100000); nothing "
        "was sent")


def test_the_worst_case_the_caps_judge_is_the_counted_prompts(world, monkeypatch):
    seen = []
    real = gateway.worst_case_usd
    monkeypatch.setattr(gateway, "worst_case_usd",
                        lambda model, body, tokens=None: seen.append(tokens)
                        or real(model, body, tokens))
    _ask(world, count=lambda body, key: A.Count(tokens=123))
    assert seen == [123]


def test_a_call_a_gate_refuses_is_never_counted(world):
    asked = []
    world.settings.pop("ai_hosted")
    got = _ask(world, count=lambda body, key: asked.append(body) or A.Count(tokens=1))
    assert got["error"] == "ai_off" and asked == [] and world.sent == []


def test_a_stored_secret_left_after_masking_is_never_sent_to_be_counted(world, monkeypatch):
    from modules import redact
    monkeypatch.setattr(redact, "contains_known_secret", lambda payload: ["default:password"])
    c = gateway.Counter("claude-haiku-5-5", KEY,
                        count=lambda body, key: pytest.fail("the count was asked"))
    got = c.measure(dict(BODY), 1)
    assert got["how"] == "estimated" and "a stored secret is still in the request" in got["why"]


# ── the fallback, calibrated ──────────────────────────────────────────────────────────────

def _sample():
    with open(SAMPLE, encoding="utf-8") as fh:
        return [dict(r, chars=int(r["chars"]), real_input=int(r["real_input"]))
                for r in csv.DictReader(fh, delimiter="\t")]


def test_the_fallback_is_at_least_the_real_input_of_every_sampled_call():
    rows = _sample()
    assert len(rows) >= 25, "the sample holds each feature's tightest calls"
    assert {r["feature"] for r in rows} >= {"explain", "nl_query", "intent_patch",
                                            "sdn_classify", "connection_check"}
    under = [r for r in rows if gateway.tokens_of_chars(r["chars"]) < r["real_input"]]
    assert under == []
    # The planted control: the old 3.0 is under every one of them.
    assert all(int(r["chars"] / 3.0) + 1 < r["real_input"] for r in rows)


def test_the_fallback_covers_the_whole_calibration_with_its_margin():
    cal = gateway.CALIBRATION
    t = cal["tightest"]
    assert cal["calls"] == 10395 and t["chars"] / t["real_input"] == pytest.approx(
        cal["fewest_chars_per_token"], abs=1e-4)
    assert gateway.tokens_of_chars(t["chars"]) >= t["real_input"] * 1.08, "an 8% margin"
    assert gateway.CHARS_PER_TOKEN * 1.08 <= cal["fewest_chars_per_token"]
    tightest = min(_sample(), key=lambda r: r["chars"] / r["real_input"])
    assert (tightest["chars"], tightest["real_input"]) == (t["chars"], t["real_input"])


def test_the_fallback_is_the_requests_characters_as_the_dataset_counted_them():
    body = {"messages": [{"content": "é" * 100}], "max_tokens": 1}
    chars = len(json.dumps(body, ensure_ascii=False))
    assert gateway.prompt_tokens(body) == gateway.tokens_of_chars(chars) == \
        int(chars / gateway.CHARS_PER_TOKEN) + 1


# ── the counter the selectors use ─────────────────────────────────────────────────────────

def _counter(n=None, fail=False):
    asked = []

    def count(body, key):
        asked.append(body)
        if fail:
            raise A.ProviderDown("down")
        return A.Count(tokens=n if n is not None else len(json.dumps(body)) // 4)
    return gateway.Counter("claude-sonnet-5-5", KEY, count=count), asked


def test_within_the_bound_by_the_fallback_nothing_is_counted():
    c, asked = _counter()
    got = c.measure(BODY, 10 ** 6)
    assert asked == [] and got["how"] == "estimated" and \
        got["tokens"] == gateway.prompt_tokens(BODY)


def test_the_same_request_is_counted_once():
    c, asked = _counter(n=9)
    assert c.measure(BODY, 1)["tokens"] == 9 and c.measure(BODY, 1)["tokens"] == 9
    assert len(asked) == 1


def test_a_press_asks_at_most_max_counts():
    c, asked = _counter(n=10 ** 9)
    c.ratio = None
    for i in range(gateway.MAX_COUNTS + 3):
        body = dict(BODY, messages=[{"role": "user", "content": "x" * i}])
        got = c.measure(body)
    assert len(asked) == gateway.MAX_COUNTS
    assert got["how"] == "estimated" and f"asked {gateway.MAX_COUNTS} counts" in got["why"]


def test_a_candidate_far_over_by_the_measured_ratio_is_skipped_uncounted():
    c, asked = _counter()
    big = dict(BODY, messages=[{"role": "user", "content": "x" * 40000}])
    first = c.measure(big, 100)
    assert first["how"] == "counted" and len(asked) == 1
    bigger = dict(BODY, messages=[{"role": "user", "content": "x" * 50000}])
    by_ratio = len(json.dumps(bigger, ensure_ascii=False)) * c.ratio
    # 10% over by the measured ratio: skipped, uncounted.
    got = c.measure(bigger, int(by_ratio / 1.10))
    assert got["how"] == "scaled" and len(asked) == 1 and got["tokens"] == int(by_ratio) + 1
    # 2% over, within `SKIP_MARGIN`: counted, since the ratio is only this press's measure.
    got = c.measure(bigger, int(by_ratio / 1.02))
    assert got["how"] == "counted" and len(asked) == 2


def test_a_counter_whose_call_could_not_be_sent_counts_nothing_and_says_why(world):
    world.settings.pop("ai_hosted")
    with pressed_by(ACTOR):
        c = gateway.counter("nl_query", actor=ACTOR, trigger=triggers.person(ACTOR),
                            count=lambda body, key: pytest.fail("counted"))
    got = c.measure(BODY, 1)
    assert got["how"] == "estimated" and got["why"].startswith("not counted: hosted AI is off")
    world.settings["ai_hosted"] = {"by": ACTOR, "at": "2026-10-25T05:00:00Z", "reason": "r"}
    with pressed_by(ACTOR):
        assert gateway.counter("nl_query", actor=ACTOR,
                               trigger=triggers.person(ACTOR)).allowed is True
    with pressed_by(ACTOR):
        c = gateway.counter("nl_query", actor="someone-else@example.com",
                            trigger=triggers.person(ACTOR),
                            count=lambda body, key: pytest.fail("counted"))
    assert c.allowed is False and c.why_not.startswith("not counted: the call's actor")


def test_a_counter_without_a_key_or_with_its_feature_off_counts_nothing(world, monkeypatch):
    monkeypatch.setattr(gateway, "_api_key", lambda: "")
    with pressed_by(ACTOR):
        c = gateway.counter("nl_query", actor=ACTOR, trigger=triggers.person(ACTOR),
                            count=lambda body, key: pytest.fail("counted"))
    got = c.measure(BODY, 1)
    assert got["how"] == "estimated" and got["why"] == (
        "not counted: no Anthropic API key is set")
    monkeypatch.setattr(gateway, "_api_key", lambda: KEY)
    from modules.ai import background
    monkeypatch.setattr(background, "admit", lambda trigger: "the feature is off, planted")
    t = {"kind": "background", "feature": "sdn_classify", "job": "j", "network": "lab",
         "finding": {"kind": "detection", "id": "d"}}
    monkeypatch.setattr(triggers, "check", lambda trigger, actor, task: {
        "ok": True, "why": "", "trigger": t})
    c = gateway.counter("sdn_classify", actor="job:j", trigger=t,
                        count=lambda body, key: pytest.fail("counted"))
    assert c.allowed is False and c.why_not == "not counted: the feature is off, planted"


def test_the_counter_counts_only_the_masked_request():
    """A selector hands the counter the request unmasked (`build_request`'s): what is counted
    is the masked one, the same bytes the send would carry."""
    from modules import redact
    planted = "username admin privilege 15 secret 5 $1$mERr$plantedMd5Crypt."
    body = dict(BODY, messages=[{"role": "user", "content": planted}])
    asked = []
    c = gateway.Counter("claude-haiku-5-5", KEY,
                        count=lambda b, k: asked.append(b) or A.Count(tokens=5))
    assert c.measure(body)["how"] == "counted"
    (sent,) = asked
    assert "$1$mERr$plantedMd5Crypt." not in json.dumps(sent)
    assert sent == redact.egress_payload(body)


def test_a_request_the_fallback_puts_exactly_at_the_bound_is_not_counted():
    c, asked = _counter(n=1)
    est = gateway.prompt_tokens(BODY)
    assert c.measure(BODY, est)["how"] == "estimated" and asked == []
    assert c.measure(BODY, est - 1)["how"] == "counted" and len(asked) == 1


def test_the_metrics_selector_keeps_what_the_count_fits_where_the_fallback_trims(world):
    """Two levels: the richer one over the bound by the fallback estimate, under it by the
    provider's count. With the counter the richer is sent; without it (the fallback alone),
    the leaner."""
    data = {"question": "q", "metrics": "m", "coverage": "c"}
    levels = [{"level": 0, "dropped": [], "summary": "s" * 4000, "coverage": "c"},
              {"level": 1, "dropped": ["x"], "summary": "s", "coverage": "c"}]
    from modules.ai import prompts
    pin = profiles.TASKS["nl_query"]
    rich = gateway.build_request(prompts.load(*nl_query.CANDIDATE), nl_query.SCHEMA_OF[10],
                                 dict(data, coverage="c", looked_up=nl_query.looked_up([])),
                                 pin, {"builder": "b", "network": "s" * 4000})
    budget = gateway.prompt_tokens(rich) - 1
    lean = nl_query.select_context(nl_query.CANDIDATE, nl_query.SCHEMA_OF[10], data,
                                   {"builder": "b"}, levels, budget)
    assert lean["level"] == 1
    c = gateway.Counter(pin["model"], KEY, count=lambda body, key: A.Count(tokens=budget))
    got = nl_query.select_context(nl_query.CANDIDATE, nl_query.SCHEMA_OF[10], data,
                                  {"builder": "b"}, levels, budget, counter=c)
    assert got["level"] == 0 and got["estimate"] == budget


def test_explains_budget_keeps_what_the_count_fits_where_the_fallback_trims(monkeypatch):
    """`explain.budgeted` measures each candidate by the counter it is handed: a count that
    fits the richest keeps it whole; the fallback alone, on a bound just under its estimate,
    drops."""
    from modules.ai import explain
    pack = {"id": "p1", "rule": "r", "device": "", "network": "", "sections": []}
    topo = {"sent": False, "network": "", "yaml": ""}
    whole = explain.budgeted(pack, topo, ("explain", 6), explain.SCHEMA_OF[6])
    budget = whole["said"]["estimate"] - 1
    monkeypatch.setitem(profiles.TASKS, "explain",
                        dict(profiles.TASKS["explain"], max_prompt_tokens=budget))
    fallback = explain.budgeted(pack, topo, ("explain", 6), explain.SCHEMA_OF[6])
    assert fallback["said"]["estimate"] > budget, "nothing to drop: the fallback stays over"
    c = gateway.Counter(profiles.TASKS["explain"]["model"], KEY,
                        count=lambda body, key: A.Count(tokens=budget))
    got = explain.budgeted(pack, topo, ("explain", 6), explain.SCHEMA_OF[6], counter=c)
    assert got["said"]["estimate"] == budget
