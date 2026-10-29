"""Evaluation rounds through the provider's Message Batches API (the operator's decision of
2026-10-29, PHASE8_PLAN 15.12, "The measurement budget and screening": evaluation rounds,
never a live feature, at the batch rate; `gateway.ask_batch`, `explain.explain_packs_batch`,
the adapter's batch calls, `profiles.batch_prices_for`).

Against a fake batch provider (`FakeBatches`: create, get, cancel, results, the results
returned in a shuffled order), never the provider:

- **the trigger:** a person's press, a background job and no trigger are each refused by name
  before anything is read, counted or sent, each request its row; no route reaches the batch
  path (the routes' scan of tests/test_ai_controls.py, seeded at `ask_batch`, its planted
  route found);
- **what leaves the host:** each batched request's body is `ask`'s for the same input, byte
  for byte after masking, but for its one cache mark's TTL (the 1-hour, on the last system
  block); every planted secret shape masked in the bytes submitted;
- **the caps:** a batch whose worst case would pass the day cap is refused whole, its words
  naming the spend, what is reserved, the batch's worst case and the cap; one over the
  evaluation's stop is refused naming both; the batch's worst case is reserved while it is in
  flight, for `BATCH_RESERVATION_TTL_S`, and settled after;
- **the record:** each result one row, priced at the batch rate from the dated table (cache
  writes by TTL, cache reads), the batch's id and the request's custom_id on it; errored,
  canceled and expired recorded as such at no cost, never a success; a result missing counts
  its worst case, said; results matched by custom_id in any order;
- **the wait:** bounded at 2.5 times the provider's stated hour, the bound firing in words
  naming what ran, the batch then asked to cancel; one that still has not ended counts every
  request's worst case;
- **the adapter:** the wire shape, the results read from an address built from the batch's id
  (never an answer's `results_url`), an id out of shape refused before anything is sent;
- **Explain's round:** `explain_packs_batch` sends what `explain_pack` sends for the same pack
  and prompt, and checks each answer as it does.
"""
import json
import random

import pytest

from modules.ai import anthropic_adapter as A
from modules.ai import calls, connection, gateway, profiles, reservations, triggers
from tests.ai_person import pressed_by
from tests.test_ai_gateway import KEY, PLANTED, own_record, world  # noqa: F401 (fixtures)

RUN = "evaluation:batch-test-1"
TODAY = "2026-10-29"


def _eval():
    return triggers.evaluation(RUN)


def _usage(**over):
    u = {"input_tokens": 120, "output_tokens": 8, "cache_read_input_tokens": 0,
         "cache_creation_input_tokens": 0}
    u.update(over)
    return u


def _message(text, usage=None, stop="end_turn"):
    return {"content": [{"type": "text", "text": text}], "stop_reason": stop,
            "usage": usage or _usage()}


class FakeBatches:
    """The provider's batch calls, faked: *answer(custom_id, params)* gives each request's
    result (a ``{"type": ...}`` dict); *states* the state each read of the batch returns
    (then "ended"); results come back shuffled."""

    def __init__(self, answer=None, states=("in_progress", "ended"), after_cancel=None):
        self.answer = answer or (lambda cid, params: {
            "type": "succeeded", "message": _message(json.dumps({"echo": _word(params)}))})
        self.states, self.after_cancel = list(states), after_cancel
        self.created, self.gets, self.canceled, self.keys = [], 0, False, []
        self.seen_reserved = []

    def create(self, batch_requests, key):
        self.created.append(batch_requests)
        self.keys.append(key)
        return A.Batch(id="msgbatch_0test", status="in_progress",
                       counts={"processing": len(batch_requests)})

    def get(self, batch_id, key):
        self.gets += 1
        self.seen_reserved.append(reservations.open_reservations()["held"])
        states = self.after_cancel if self.canceled and self.after_cancel is not None \
            else self.states
        status = states.pop(0) if states else "ended"
        return A.Batch(id=batch_id, status=status, counts={"processing": 1})

    def cancel(self, batch_id, key):
        self.canceled = True
        return A.Batch(id=batch_id, status="canceling")

    def results(self, batch_id, key):
        lines = [{"custom_id": r["custom_id"], "result": self.answer(r["custom_id"],
                                                                      r["params"])}
                 for r in self.created[-1]]
        random.Random(20261029).shuffle(lines)
        return lines


def _word(params):
    """The word a connection-check request carries (its data block)."""
    text = params["messages"][0]["content"]
    return text.split('<data name="word">\n', 1)[1].split("\n</data>", 1)[0]


def _requests(*words, parts=None):
    return [{"custom_id": f"r{i}", "feature": "connection_check", "prompt": ("ping", 1),
             "schema": connection.Ping, "parts": dict(parts or {}, word=w)}
            for i, w in enumerate(words)]


class Clock:
    """A clock the fake sleep moves."""

    def __init__(self):
        self.t, self.slept = 1000.0, []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def _batch(reqs, fake, **kw):
    clock = Clock()
    return gateway.ask_batch(reqs, actor=RUN, trigger=_eval(), today=TODAY, provider=fake,
                             sleep=clock.sleep, clock=clock, **kw)


def _rows():
    return calls.read()["rows"]


def _worst_total(world, reqs):
    """The batch's worst case `ask_batch` judges, from a measuring run of the same requests
    (its rows then removed: nothing spent)."""
    fake = FakeBatches()
    _batch(reqs, fake)
    bodies = [r["params"] for r in fake.created[0]]
    open(calls._path(), "w").close()
    return sum(gateway.batch_worst_case_usd(b["model"], b, A.count_tokens(b, KEY).tokens)
               for b in bodies)


# ── the trigger ───────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("trig,named", [
    ("person", "a person trigger"),
    ("background", "a background trigger"),
    ("none", "no trigger"),
])
def test_a_person_a_background_job_or_no_trigger_is_refused_before_anything(
        world, monkeypatch, trig, named):
    """Refused by name before any request is read, counted or sent; each request its row."""
    def counted(*a, **k):
        raise AssertionError("nothing is counted for a refused batch")
    monkeypatch.setattr(A, "count_tokens", counted)
    fake = FakeBatches()
    given = {"person": triggers.person("operator@example.com"),
             "background": triggers.background("sdn_classify", "job-1", "lab", "detection",
                                               "d-1"),
             "none": None}[trig]
    actor = triggers.actor_of(given) if given else "operator@example.com"
    with pressed_by("operator@example.com"):
        got = gateway.ask_batch(_requests("a", "b"), actor=actor, trigger=given, today=TODAY,
                                provider=fake, sleep=pytest.fail, clock=lambda: 0.0)
    assert got["ok"] is False and got["error"] == "batch_trigger"
    assert got["detail"] == (
        "a batch is for evaluation runs only (PHASE8_PLAN 15.12: never a live feature); this "
        f"one names {named}: a person's press or a background job asks one call at a time "
        "(gateway.ask); nothing was read or sent")
    assert fake.created == [] and fake.gets == 0
    rows = _rows()
    assert sorted(r["batch"]["custom_id"] for r in rows) == ["r0", "r1"]
    assert {r["verdict"] for r in rows} == {"batch_trigger"}
    assert all(r["cost_usd"] == 0 and "request" not in r for r in rows)
    assert sorted(got["results"]) == ["r0", "r1"]


def test_an_evaluation_trigger_is_taken_and_its_run_recorded(world):
    fake = FakeBatches()
    got = _batch(_requests("a"), fake)
    assert got["ok"] is True, got
    row = _rows()[0]
    assert row["trigger"] == {"kind": "evaluation", "run": "batch-test-1"}
    assert row["actor"] == RUN and fake.keys == [KEY]


def test_no_route_reaches_the_batch_path(monkeypatch):
    """Never a live feature: the routes' scan, seeded at `ask_batch`, finds no route; a route
    planted to call it is found (the scan can fail)."""
    import os

    from tests import test_ai_controls as C
    monkeypatch.setattr(C, "SEED", ("modules.ai.gateway", "ask_batch"))
    assert C.reaching_endpoints(C._sources()) == set()
    head = "from flask import Blueprint\nbp = Blueprint('planted', __name__)\n"
    planted = head + ("from modules.ai import explain\n"
                      "@bp.route('/x', methods=['POST'])\n"
                      "def planted():\n    return explain.explain_packs_batch([], [4], 1, "
                      "actor='a', trigger={})\n")
    sources = dict(C._sources(), **{os.path.join("routes", "planted_batch.py"): planted})
    assert C.reaching_endpoints(sources) == {"planted.planted"}


# ── what leaves the host ──────────────────────────────────────────────────────────────────

def _ask_body(world, parts):
    world.answer = _message('{"echo": "w"}')
    gateway.ask("connection_check", ("ping", 1), connection.Ping, parts, actor=RUN,
                trigger=_eval(), send=world.send, today=TODAY)
    return world.sent[-1]["body"]


def test_a_batched_request_is_asks_body_byte_for_byte_but_its_cache_ttl(world):
    """The same input through `ask` and through the batch: the bodies' bytes are equal once
    `ask`'s one cache mark is given the 1-hour TTL, and differ in nothing else; every planted
    secret shape is masked in the bytes submitted."""
    parts = dict(PLANTED, word="w")
    asked = _ask_body(world, parts)
    fake = FakeBatches()
    assert _batch(_requests("w", parts=PLANTED), fake)["ok"] is True
    params = fake.created[0][0]["params"]
    marks = [b for b in params["system"] if "cache_control" in b]
    assert len(marks) == 1 and marks[0] is params["system"][-1], "one mark, the last block"
    assert marks[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert json.dumps(params) != json.dumps(asked), "the TTL is the one difference"
    expected = json.loads(json.dumps(asked))
    expected["system"][-1]["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
    assert json.dumps(params) == json.dumps(expected)
    sent = json.dumps(fake.created[0])
    for secret in ("0822455D0A16544541", "$9$PlantedScryptHashValue01", "plantedAuthPass1",
                   "$1$mERr$plantedMd5Crypt."):
        assert secret not in sent, secret
    row = next(r for r in _rows() if r.get("batch"))
    assert row["request"] == params, "the row keeps the request as it left the host"
    assert row["prompt_count"]["how"] == "counted"


def test_a_call_keeps_the_five_minute_mark():
    """`build_request` with no TTL sends the mark as it always was."""
    from modules.ai import prompts
    body = gateway.build_request(prompts.load("ping", 1), connection.Ping, {"word": "w"},
                                 profiles.TASKS["connection_check"])
    assert body["system"][-1]["cache_control"] == {"type": "ephemeral"}


def test_a_request_the_gateway_refuses_is_refused_alone_and_the_rest_sent(world, monkeypatch):
    """Each request passes `ask`'s own gates: one over its prompt's bound is refused, recorded,
    and the others go in the batch."""
    monkeypatch.setitem(profiles.TASKS, "connection_check",
                        dict(profiles.TASKS["connection_check"], max_prompt_tokens=400))
    fake = FakeBatches()
    got = _batch(_requests("short", "x" * 4000), fake)
    assert [r["custom_id"] for r in fake.created[0]] == ["r0"]
    assert got["results"]["r1"]["error"] == "prompt_too_long"
    assert got["results"]["r0"]["ok"] is True


# ── the caps ──────────────────────────────────────────────────────────────────────────────

def test_a_batch_that_would_pass_the_day_cap_is_refused_whole_naming_both(world):
    reqs = _requests("a", "b", "c")
    total = _worst_total(world, reqs)
    world.settings["ai_cap_usd_per_day"] = total * 0.9
    fake = FakeBatches()
    got = _batch(reqs, fake)
    assert got["ok"] is False and got["error"] == "over_cap" and fake.created == []
    assert got["detail"] == (
        f"today's spend $0.0000 plus $0.0000 reserved by 0 call(s) in flight plus this "
        f"batch's worst case ${total:.4f} (3 requests at the batch rate) is over the day cap "
        f"${total * 0.9:.4f}: a round that would pass the day cap is asked for first; "
        "nothing was sent")
    rows = _rows()
    assert len(rows) == 3 and {r["verdict"] for r in rows} == {"over_cap"}
    assert all(r["batch_worst_usd"] == pytest.approx(total) for r in rows)
    assert reservations.open_reservations()["held"] == {}


def test_the_same_batch_under_the_day_cap_is_sent(world):
    """The control for the test above: the cap just over the worst case."""
    reqs = _requests("a", "b", "c")
    total = _worst_total(world, reqs)
    world.settings["ai_cap_usd_per_day"] = total * 1.01
    assert _batch(reqs, FakeBatches())["ok"] is True


def test_the_day_cap_counts_todays_spend_and_whats_in_flight(world):
    reqs = _requests("a")
    total = _worst_total(world, reqs)
    world.settings["ai_cap_usd_per_day"] = total * 3
    calls.record({"id": "ai-spent", "feature": "explain", "cost_usd": total * 1.5,
                  "verdict": "ok", "at": f"{TODAY}T01:00:00Z"})
    assert reservations.reserve("ai-flying", total * 1.0, judge=lambda h: None, ttl_s=600,
                                day=TODAY)["ok"]
    got = _batch(reqs, FakeBatches())
    assert got["error"] == "over_cap", got
    assert got["detail"].startswith(
        f"today's spend ${total * 1.5:.4f} plus ${total:.4f} reserved by 1 call(s) in flight "
        f"plus this batch's worst case ${total:.4f}")


def test_a_batch_reaching_the_day_cap_exactly_is_sent(world, monkeypatch):
    reqs = _requests("a")
    total = _worst_total(world, reqs)
    world.settings["ai_cap_usd_per_day"] = total
    assert _batch(reqs, FakeBatches())["ok"] is True


def test_an_unreadable_record_refuses_the_batch(world, monkeypatch):
    monkeypatch.setattr(calls, "spent_usd", lambda day, zone=None: {
        "state": "unreadable", "usd": None, "calls": 0, "error": "torn"})
    fake = FakeBatches()
    got = _batch(_requests("a"), fake)
    assert got["error"] == "over_cap" and fake.created == []
    assert got["detail"] == ("the record of AI calls cannot be read, so today's spend is "
                             "unknown (torn); nothing was sent")


@pytest.mark.parametrize("limit,words", [
    ("BATCH_MAX_REQUESTS", "a batch holds at most 1 requests (the provider's limit); this one "
                           "holds 2; nothing was sent"),
    ("BATCH_MAX_BYTES", "the batch's requests are"),
])
def test_a_batch_over_the_providers_limits_is_refused(world, monkeypatch, limit, words):
    monkeypatch.setattr(gateway, limit, 1)
    fake = FakeBatches()
    got = _batch(_requests("a", "b"), fake)
    assert got["error"] == "batch_shape" and fake.created == []
    assert got["detail"].startswith(words)


def test_a_batch_while_a_workspace_limit_is_held_is_refused_and_nothing_sent(world, tmp_path,
                                                                             monkeypatch):
    from modules.ai import provider_limit
    monkeypatch.setattr(provider_limit, "_path", lambda: str(tmp_path / "limit.json"))
    provider_limit.record(A.WorkspaceLimit("HTTP 400", until="2099-01-01T00:00:00Z", said="x",
                                           status=400))
    fake = FakeBatches()
    got = _batch(_requests("a"), fake)
    assert got["error"] == "nothing_sent" and fake.created == []
    assert got["results"]["r0"]["error"] == "workspace_limit"


def test_a_submitted_batch_clears_a_workspace_limit_held_from_before(world, tmp_path,
                                                                     monkeypatch):
    """The provider took the batch, so a limit held from before it was submitted no longer
    holds (as a call answered clears one, C2084). The hold is planted where the requests'
    own check (`_prepared`) does not see it: recorded by another process between the check and
    the submit."""
    from modules.ai import provider_limit
    monkeypatch.setattr(provider_limit, "_path", lambda: str(tmp_path / "limit.json"))
    provider_limit.record(A.WorkspaceLimit("HTTP 400", until=None, said="x", status=400),
                          now=provider_limit.clock() - 3600)
    seen = {}
    fake = FakeBatches()
    real = fake.create

    def create(reqs, key):
        seen["held"] = provider_limit.read()["hold"]
        return real(reqs, key)
    fake.create = create
    monkeypatch.setattr(provider_limit, "holding", lambda now=None: None)
    assert _batch(_requests("a"), fake)["ok"] is True
    assert seen["held"] is not None and provider_limit.read()["hold"] is None


def test_a_batch_over_the_evaluations_stop_is_refused_naming_both(world):
    reqs = _requests("a", "b")
    total = _worst_total(world, reqs)
    fake = FakeBatches()
    got = _batch(reqs, fake, stop_usd=total * 0.5)
    assert got["error"] == "over_stop" and fake.created == []
    assert got["detail"] == (f"this batch's worst case ${total:.4f} (2 requests at the batch "
                             f"rate) is over the evaluation's stop ${total * 0.5:.4f}; nothing "
                             "was sent")
    assert _batch(reqs, FakeBatches(), stop_usd=total * 1.01)["ok"] is True


def test_the_batchs_worst_case_is_reserved_while_in_flight_and_settled_after(world):
    reqs = _requests("a", "b")
    total = _worst_total(world, reqs)
    fake = FakeBatches()
    assert _batch(reqs, fake)["ok"] is True
    held = fake.seen_reserved[0]
    assert len(held) == 1
    (key, one), = held.items()
    assert key.startswith("ai-batch-") and one["usd"] == pytest.approx(total)
    import time
    assert one["expires_at"] > time.time() + 24 * 3600 and one["feature"] == "connection_check"
    assert gateway.BATCH_RESERVATION_TTL_S == 25 * 3600, "the provider's 24 h and an hour"
    assert reservations.open_reservations()["held"] == {}


def test_the_reservation_lives_as_long_as_the_batch_could_bill(world, monkeypatch):
    seen = {}
    real = reservations.reserve

    def keep(call_id, usd, **kw):
        seen["ttl"] = kw["ttl_s"]
        return real(call_id, usd, **kw)
    monkeypatch.setattr(reservations, "reserve", keep)
    _batch(_requests("a"), FakeBatches())
    assert seen["ttl"] == gateway.BATCH_EXPIRY_S + 3600 == 90000


def test_a_per_call_cap_holds_each_batched_request(world, monkeypatch):
    """Just under the request's worst case refuses it; just over sends it (the control)."""
    reqs = _requests("a")
    worst = _worst_total(world, reqs)
    monkeypatch.setattr(profiles, "cap_per_call", lambda name: worst * 0.99)
    fake = FakeBatches()
    got = _batch(reqs, fake)
    assert got["error"] == "nothing_sent" and fake.created == []
    assert got["results"]["r0"]["error"] == "over_cap"
    assert got["results"]["r0"]["detail"] == (
        f"this batched request's worst case ${worst:.4f} is over the connection_check task's "
        f"per-call cap ${worst * 0.99:.4f}; nothing was sent")
    monkeypatch.setattr(profiles, "cap_per_call", lambda name: worst * 1.01)
    assert _batch(reqs, FakeBatches())["ok"] is True


def test_a_row_that_could_not_be_recorded_keeps_the_batchs_reservation_unexpiring(
        world, monkeypatch):
    """C2047: the rows the record refused keep the batch's reservation, unexpiring, holding
    their cost alone (each request's actual cost), each a late row; once the record takes them
    (the next reserve asks it), the reservation is gone."""
    import time
    real = calls.record

    def refused(entry):
        out = real(entry)
        return (dict(out, recorded=False)
                if entry.get("verdict") == "ok" and not entry.get("recorded_late") else out)
    monkeypatch.setattr(calls, "record", refused)
    got = _batch(_requests("a"), FakeBatches())
    assert got["ok"] is True
    held = reservations.open_reservations(now=time.time() + 10 ** 8)["held"]
    assert len(held) == 1 and next(iter(held)).startswith("ai-batch-")
    (entry,) = held.values()
    ok = [r for r in got["results"].values() if r.get("ok")]
    assert entry["unrecorded"] is True and len(entry["rows"]) == len(ok) >= 1
    assert entry["usd"] == pytest.approx(sum(r["cost_usd"] for r in ok))
    assert entry["usd"] < got["worst_usd"], "their cost alone, not the batch's worst case"
    first = next(iter(held))
    monkeypatch.setattr(calls, "record", real)
    assert _batch(_requests("b"), FakeBatches())["ok"] is True
    assert reservations.open_reservations(now=time.time() + 10 ** 8)["held"] == {}, first
    late = [r for r in calls.read()["rows"] if r.get("recorded_late")]
    assert len(late) == len(ok) and all(r["batch"]["custom_id"] for r in late)


# ── the record ────────────────────────────────────────────────────────────────────────────

def test_the_batch_rate_is_half_of_every_standard_rate_and_dated():
    son = profiles.batch_prices_for("claude-sonnet-5-5", 1000)
    # The provider's own example: Sonnet 5.5 at $1 in and $5 out a million tokens.
    assert (son["input"], son["output"]) == (1.0, 5.0)
    assert son["cache_read"] == pytest.approx(0.05) and son["cache_write"] == 1.25
    assert son["cache_write_1h"] == 2.0, "2x the input rate, at half"
    assert son["batch"] == {"multiplier": 0.5, "as_of": "2026-10-29",
                            "source": profiles.BATCH_SOURCE,
                            "cache_source": profiles.CACHE_SOURCE}
    long = profiles.batch_prices_for("claude-haiku-5-5", 100_001)
    assert long["tier"] == "long" and long["input"] == 0.25 and long["cache_write_1h"] == 0.5


def test_results_are_recorded_at_the_batch_rate_with_the_cache_tokens(world):
    usage = _usage(input_tokens=1000, output_tokens=200, cache_read_input_tokens=5000,
                   cache_creation_input_tokens=3000,
                   cache_creation={"ephemeral_5m_input_tokens": 0,
                                   "ephemeral_1h_input_tokens": 3000})
    fake = FakeBatches(answer=lambda cid, p: {"type": "succeeded", "message": _message(
        json.dumps({"echo": _word(p)}), usage)})
    got = _batch(_requests("a"), fake)
    assert got["ok"] is True and got["batch_id"] == "msgbatch_0test"
    one = got["results"]["r0"]
    assert one["ok"] is True and one["output"].echo == "a"
    row = _rows()[0]
    # Haiku 5.5 at half: input $0.05, output $0.25, a 1-hour write $0.10, a read $0.005.
    assert row["cost_usd"] == pytest.approx((1000 * 0.05 + 200 * 0.25 + 3000 * 0.10
                                             + 5000 * 0.005) / 1e6)
    assert one["cost_usd"] == row["cost_usd"] == got["cost_usd"]
    assert row["tokens"] == {"input_tokens": 1000, "output_tokens": 200,
                             "cache_read_input_tokens": 5000,
                             "cache_creation_input_tokens": 3000}
    assert row["cache_writes"] == {"5m": 0, "1h": 3000}
    assert row["price"]["batch"]["multiplier"] == 0.5 and row["verdict"] == "ok"
    assert row["batch"] == {"custom_id": "r0", "id": "msgbatch_0test", "multiplier": 0.5}
    assert calls.spent_usd(TODAY)["usd"] == pytest.approx(row["cost_usd"])


def test_history_draws_a_batched_call_as_such(world):
    """History's AI calls: a batched request says so in its words, and its record names the
    batch, the request and the rate; a call made one at a time says neither."""
    from modules import history_sources as HS
    _batch(_requests("a"), FakeBatches())
    _ask_body(world, {"word": "w"})
    events = HS.ai_calls({"device": "", "limit": 50})["events"]
    by = {e["call"]: e for e in events}
    rows = {r["id"]: r for r in _rows()}
    batched = next(e for c, e in by.items() if rows[c].get("batch"))
    single = next(e for c, e in by.items() if not rows[c].get("batch"))
    assert batched["what"].startswith("AI call (batched), connection_check on the installation")
    assert dict(batched["record"])["Batch"] == ("msgbatch_0test, request r0, at 50% of the "
                                                "standard rates")
    assert single["what"].startswith("AI call, connection_check")
    assert "Batch" not in dict(single["record"])


@pytest.mark.parametrize("usage,want", [
    ({"cache_creation_input_tokens": 300}, {"5m": 0, "1h": 300}),
    ({"cache_creation_input_tokens": 300,
      "cache_creation": {"ephemeral_5m_input_tokens": 100, "ephemeral_1h_input_tokens": 200}},
     {"5m": 100, "1h": 200}),
    ({"cache_creation_input_tokens": 300,
      "cache_creation": {"ephemeral_5m_input_tokens": 100}}, {"5m": 100, "1h": 200}),
    ({}, {"5m": 0, "1h": 0}),
])
def test_cache_writes_without_a_breakdown_are_the_dearer_1_hour(usage, want):
    assert gateway.cache_writes(usage) == want


def test_errored_canceled_and_expired_are_recorded_so_unbilled_never_a_success(world):
    kinds = {"r0": {"type": "errored", "error": {"type": "error", "error": {
                 "type": "invalid_request_error",
                 "message": "bad request near snmp-server community plantedCommunity9 RO"}}},
             "r1": {"type": "canceled"}, "r2": {"type": "expired"}}
    got = _batch(_requests("a", "b", "c"), FakeBatches(answer=lambda cid, p: kinds[cid]))
    assert got["ok"] is True and got["cost_usd"] == 0.0
    by = {r["batch"]["custom_id"]: r for r in _rows()}
    assert {c: by[c]["verdict"] for c in by} == {"r0": "batch_errored", "r1": "batch_canceled",
                                                "r2": "batch_expired"}
    assert all(by[c]["cost_usd"] == 0.0 and by[c]["billed"] is False for c in by)
    assert all(got["results"][c]["ok"] is False for c in by)
    assert "plantedCommunity9" not in by["r0"]["detail"]
    assert by["r0"]["detail"].startswith("the batch msgbatch_0test could not answer this "
                                         "request (invalid_request_error: bad request near")
    assert by["r1"]["detail"] == ("the batch msgbatch_0test was canceled before this request "
                                  "was processed; not billed")
    assert by["r2"]["detail"] == ("the batch msgbatch_0test expired before this request was "
                                  "processed (24 hours after it was created); not billed")


def test_a_missing_or_unknown_result_counts_its_worst_case(world, caplog):
    """A result for a custom_id no request waits on is ignored and said in the log."""
    reqs = _requests("a", "b")
    fake = FakeBatches(answer=lambda cid, p: {"type": "mystery"})
    fake.results = lambda bid, key: [{"custom_id": "r1", "result": {"type": "mystery"}},
                                     {"custom_id": "zz", "result": {"type": "succeeded"}}]
    got = _batch(reqs, fake)
    by = {r["batch"]["custom_id"]: r for r in _rows()}
    assert by["r0"]["verdict"] == "batch_missing" and by["r1"]["verdict"] == \
        "batch_unknown_result"
    for c in ("r0", "r1"):
        assert by[c]["cost_usd"] == by[c]["worst_usd"] > 0
        assert by[c]["detail"].endswith(f"whether the provider billed it is unknown, so its "
                                        f"worst case ${by[c]['worst_usd']:.4f} is counted")
    assert got["cost_usd"] == round(by["r0"]["cost_usd"] + by["r1"]["cost_usd"], 6)
    assert ("ai: the batch msgbatch_0test's result for 'zz' matches no request waiting on "
            "one: ignored") in caplog.text


def test_results_are_matched_by_custom_id_in_any_order(world):
    words = [f"word{i}" for i in range(7)]
    fake = FakeBatches()
    got = _batch(_requests(*words), fake)
    sent = fake.created[0]
    assert [r["custom_id"] for r in fake.results("msgbatch_0test", KEY)] != \
        [r["custom_id"] for r in sent], "the fake returns them out of order"
    assert {c: got["results"][c]["output"].echo for c in got["results"]} == {
        f"r{i}": w for i, w in enumerate(words)}
    assert {r["batch"]["custom_id"]: r["response"] for r in _rows()} == {
        f"r{i}": json.dumps({"echo": w}) for i, w in enumerate(words)}


def test_a_result_named_twice_is_read_once_the_first(world):
    fake = FakeBatches()
    fake.results = lambda bid, key: [
        {"custom_id": "r0", "result": {"type": "canceled"}},
        {"custom_id": "r0", "result": {"type": "succeeded",
                                       "message": _message('{"echo": "a"}')}}]
    _batch(_requests("a"), fake)
    (row,) = _rows()
    assert row["verdict"] == "batch_canceled" and row["cost_usd"] == 0.0


def test_an_errored_result_carrying_a_message_is_never_read_as_an_answer(world):
    fake = FakeBatches(answer=lambda cid, p: {"type": "errored", "error": {
        "type": "error", "error": {"type": "api_error", "message": "x"}},
        "message": _message('{"echo": "a"}')})
    got = _batch(_requests("a"), fake)
    assert got["results"]["r0"]["ok"] is False and _rows()[0]["verdict"] == "batch_errored"


def test_an_answer_that_is_not_the_schema_is_its_own_kind(world):
    fake = FakeBatches(answer=lambda cid, p: {"type": "succeeded",
                                              "message": _message('{"echo": 7}')})
    got = _batch(_requests("a"), fake)
    assert got["results"]["r0"]["error"] == "schema" and _rows()[0]["cost_usd"] > 0


def test_a_batch_not_submitted_records_each_request_unbilled_and_settles(world):
    fake = FakeBatches()

    def down(reqs, key):
        raise A.ProviderDown("HTTP 500: api_error: oops", status=500)
    fake.create = down
    got = _batch(_requests("a", "b"), fake)
    assert got["error"] == "provider_down"
    assert {r["verdict"] for r in _rows()} == {"provider_down"}
    assert all(r["cost_usd"] == 0 for r in _rows())
    assert reservations.open_reservations()["held"] == {}


def test_a_workspace_limit_at_submit_is_held(world, tmp_path, monkeypatch):
    from modules.ai import provider_limit
    monkeypatch.setattr(provider_limit, "_path", lambda: str(tmp_path / "limit.json"))
    fake = FakeBatches()

    def limited(reqs, key):
        raise A.WorkspaceLimit("HTTP 400: limit", until="2026-11-01T00:00:00Z", said="x",
                               status=400)
    fake.create = limited
    got = _batch(_requests("a"), fake)
    assert got["error"] == "workspace_limit" and provider_limit.holding()
    assert _rows()[0]["limit"]["until"] == "2026-11-01T00:00:00Z"


@pytest.mark.parametrize("reqs,words", [
    ([], "a batch holds at least one request, as a list"),
    ([{"custom_id": "a"}], "request 1 does not name each of custom_id, feature, prompt, "
                           "schema, parts"),
    (_requests("a", "b")[:1] * 2, "the custom_id 'r0' is named twice: results are matched "
                                  "by it"),
    ([dict(_requests("a")[0], custom_id="has space")],
     "request 1's custom_id 'has space' is not 1 to 64 letters, digits, _ or - (the "
     "provider's shape)"),
])
def test_a_batch_out_of_shape_is_refused_and_nothing_sent(world, reqs, words):
    fake = FakeBatches()
    got = _batch(reqs, fake)
    assert got["error"] == "batch_shape" and got["detail"] == f"{words}; nothing was sent"
    assert fake.created == []


# ── the wait ──────────────────────────────────────────────────────────────────────────────

def test_the_wait_is_bounded_and_fires_naming_what_ran(world):
    """Never ended: the bound (2.5 times the provider's hour) fires, the batch is asked to
    cancel, and when that does not end it either, every request counts its worst case."""
    fake = FakeBatches(states=["in_progress"] * 1000, after_cancel=["canceling"] * 1000)
    clock = Clock()
    got = gateway.ask_batch(_requests("a"), actor=RUN, trigger=_eval(), today=TODAY,
                            provider=fake, sleep=clock.sleep, clock=clock)
    assert gateway.BATCH_WAIT_S == 9000.0 == 2.5 * gateway.BATCH_EXPECTED_S
    assert fake.canceled is True and got["error"] == "batch_unfinished"
    polls = int(gateway.BATCH_WAIT_S // gateway.BATCH_POLL_S) + 1
    assert got["detail"].startswith(
        f"the batch msgbatch_0test ran {polls * 30} s and had not ended, past its bound of "
        f"9000 s (2.5 times the 3600 s the provider says most batches finish within) ({polls} "
        "reads of its state, the last 'in_progress', 1 of its requests still processing); it "
        "was asked to cancel, and the batch msgbatch_0test ran ")
    assert "past the 300 s a cancel is waited on" in got["detail"]
    assert set(clock.slept) == {30.0}
    row = _rows()[0]
    assert row["verdict"] == "batch_unfinished" and row["cost_usd"] == row["worst_usd"] > 0
    assert reservations.open_reservations()["held"] == {}, "its row counts it now"


def test_a_batch_canceled_past_its_bound_records_what_it_processed(world):
    fake = FakeBatches(states=["in_progress"] * 1000, after_cancel=["canceling", "ended"],
                       answer=lambda cid, p: {"type": "canceled"} if cid == "r1" else {
                           "type": "succeeded", "message": _message(
                               json.dumps({"echo": _word(p)}))})
    got = _batch(_requests("a", "b"), fake)
    assert got["ok"] is True and fake.canceled
    by = {r["batch"]["custom_id"]: r["verdict"] for r in _rows()}
    assert by == {"r0": "ok", "r1": "batch_canceled"}


def test_a_state_read_failing_transiently_is_asked_again(world):
    fake = FakeBatches(states=["in_progress", "ended"])
    real, fails = fake.get, [A.Overloaded("HTTP 529", status=529)]

    def flaky(bid, key):
        if fails:
            raise fails.pop()
        return real(bid, key)
    fake.get = flaky
    assert _batch(_requests("a"), fake)["ok"] is True
    assert fake.canceled is False and fake.gets == 2, "read again, never canceled"
    assert _rows()[0]["verdict"] == "ok"


def test_a_state_read_refused_ends_the_wait_and_counts_the_worst_case(world):
    fake = FakeBatches()

    def refused(bid, key):
        raise A.KeyRefused("HTTP 401: authentication_error: bad key", status=401)
    fake.get = refused
    fake.cancel = lambda bid, key: (_ for _ in ()).throw(A.KeyRefused("HTTP 401", status=401))
    got = _batch(_requests("a"), fake)
    assert got["error"] == "batch_unfinished"
    assert got["detail"].startswith("the batch msgbatch_0test's state could not be read "
                                    "(key_refused: HTTP 401: authentication_error: bad key) "
                                    "after 1 reads; asking it to cancel failed")


# ── the adapter ───────────────────────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status, body=None, text=""):
        self.status_code, self._body, self.headers, self.text = status, body, {}, text

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


class _Session:
    def __init__(self, *responses):
        self.responses, self.sent = list(responses), []

    def post(self, url, json=None, headers=None, timeout=None):
        self.sent.append(("POST", url, json, headers, timeout))
        return self.responses.pop(0)

    def get(self, url, headers=None, timeout=None):
        self.sent.append(("GET", url, None, headers, timeout))
        return self.responses.pop(0)


BATCH = {"id": "msgbatch_01abc", "processing_status": "in_progress",
         "request_counts": {"processing": 2}, "results_url": "https://elsewhere.example/r"}


def test_the_adapter_submits_reads_cancels_and_reads_results_on_the_providers_host():
    lines = "\n".join(json.dumps({"custom_id": c, "result": {"type": "canceled"}})
                      for c in ("a", "b"))
    s = _Session(_Resp(200, BATCH), _Resp(200, dict(BATCH, processing_status="ended")),
                 _Resp(200, dict(BATCH, processing_status="canceling")),
                 _Resp(200, None, text=lines + "\n"))
    two = [{"custom_id": "a", "params": {"model": "m"}},
           {"custom_id": "b", "params": {"model": "n"}}]
    made = A.batch_create(two, KEY, session=s)
    assert (made.id, made.status, made.counts) == ("msgbatch_01abc", "in_progress",
                                                   {"processing": 2})
    assert A.batch_get(made.id, KEY, session=s).status == "ended"
    assert A.batch_cancel(made.id, KEY, session=s).status == "canceling"
    got = A.batch_results(made.id, KEY, session=s)
    assert [r["custom_id"] for r in got] == ["a", "b"]
    assert [(m, u) for m, u, *_ in s.sent] == [
        ("POST", "https://api.anthropic.com/v1/messages/batches"),
        ("GET", "https://api.anthropic.com/v1/messages/batches/msgbatch_01abc"),
        ("POST", "https://api.anthropic.com/v1/messages/batches/msgbatch_01abc/cancel"),
        ("GET", "https://api.anthropic.com/v1/messages/batches/msgbatch_01abc/results")]
    assert s.sent[0][2] == {"requests": two}
    for _m, _u, _b, headers, timeout in s.sent:
        assert headers["x-api-key"] == KEY and headers["anthropic-version"] == "2023-06-01"
    assert s.sent[3][4] == A.BATCH_RESULTS_TIMEOUT and s.sent[0][4] == A.BATCH_TIMEOUT


@pytest.mark.parametrize("bad", ["../messages", "msgbatch_01/../x", "", None,
                                 "https://elsewhere.example/r"])
def test_a_batch_id_out_of_shape_is_refused_before_anything_is_sent(bad):
    s = _Session()
    for fn in (A.batch_get, A.batch_cancel, A.batch_results):
        with pytest.raises(A.BadRequest):
            fn(bad, KEY, session=s)
    assert s.sent == []


def test_an_answer_naming_a_batch_id_out_of_shape_is_provider_down():
    s = _Session(_Resp(200, dict(BATCH, id="../../x")))
    with pytest.raises(A.ProviderDown):
        A.batch_create([], KEY, session=s)


def test_a_results_line_that_is_not_json_is_never_skipped():
    s = _Session(_Resp(200, None, text='{"custom_id": "a"}\nnot json\n'))
    with pytest.raises(A.ProviderDown) as got:
        A.batch_results("msgbatch_01abc", KEY, session=s)
    assert "line 2 is not JSON" in str(got.value)


@pytest.mark.parametrize("resp,cls", [
    (_Resp(400, {"error": {"type": "invalid_request_error", "message":
                           "You have reached your specified workspace API usage limits. You "
                           "will regain access on 2026-11-01 at 00:00 UTC."}}),
     A.WorkspaceLimit),
    (_Resp(401, {"error": {"type": "authentication_error", "message": "x"}}), A.KeyRefused),
    (_Resp(429, {"error": {"type": "rate_limit_error", "message": "x"}}), A.RateLimited),
    (_Resp(500, {"error": {"type": "api_error", "message": "x"}}), A.ProviderDown),
])
def test_a_batch_call_refused_is_its_own_kind_never_retried(resp, cls):
    s = _Session(resp)
    with pytest.raises(cls):
        A.batch_create([], KEY, session=s)
    assert len(s.sent) == 1


def test_no_key_sends_no_batch():
    s = _Session()
    with pytest.raises(A.KeyRefused):
        A.batch_create([], "", session=s)
    assert s.sent == []
