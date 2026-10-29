"""The SDN loop's classify step at once (C1970, the operator's addendum of 2026-10-28, item 9):
a pass's detections were classified one after the other (an AUTO pass of two took 31 s); now
each is its own call, made concurrently through `fanout.read_each`, at most
`loop.CLASSIFY_WORKERS` at a time. The real gateway runs every call (its trigger, background
switch, caps, reservations and record) with a fake provider; no provider is called.

Measured by work, never wall-clock (CLAUDE.md: performance tests assert on work): a fake
provider that answers only once every call has started (`threading.Barrier`), bounded by
`BARRIER_S` so a loop that is serial again fails rather than hangs.

- **At once**: a pass of three detections makes its three calls together.
- **Deterministic**: the outcomes, the responses and the log's lines are the serial pass's
  (`CLASSIFY_WORKERS` 1), in the detections' order, although the first detection's call is
  made to finish last.
- **Isolated**: one call that raises, or that the provider fails, is that detection's
  fail-safe alone; a cap that fits two of three refuses one, recorded for that detection only.
- **Never past the cap**: at once sends no more than the serial pass under the same cap, and
  never a cost past it (it may refuse more: C2054).
- **Bounded**: a pass of more detections than the bound runs at most `CLASSIFY_WORKERS` at
  once, and all of them; the bound is derived from the busiest pass measured.
"""
import collections
import json
import os
import re
import threading

import pytest

from modules import fanout
from modules.ai import anthropic_adapter as A
from modules.ai import calls, gateway, profiles
from modules.sdn import closed_loop as CL
from modules.sdn import loop as LP
from tests.test_sdn_classify import (CASES, FLOOD, NET, PARAMS, REDIRECT, SCAN, _feature_on,
                                     answer, detection_of, keep_pack, rows,
                                     world)  # noqa: F401 - the fixture
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_loop_live import data_of

#: How long a fake call waits for the others to start: every call here starts within
#: milliseconds of the first (the gateway's gates and the reservation, measured locally at
#: well under a second for three), so this fails a serial loop in seconds rather than hanging.
BARRIER_S = 10.0
#: The provider's token count every call here is given, so each call's worst case is the same.
TOKENS = 5000
NO_DRIVER = lambda n, c: {"ok": False, "error": "unused"}  # noqa: E731

THREE = (SCAN, FLOOD, REDIRECT)


def answers() -> dict:
    """A planted answer that passes the check for each of the three detections, by rule."""
    flow = REDIRECT["detection"]["subject"]["value"]
    return {
        "scan": answer(),
        "flood": answer(threat_type="flood", affected_devices=["192.0.2.2"],
                        parameters=dict(PARAMS, source="192.0.2.2"),
                        evidence_refs=[FLOOD["expect"]["cites_any"][0]]),
        "unauthorised_flow": answer(threat_type="unauthorised_flow", action_id="remove_flow",
                                    affected_devices=["192.0.2.3"],
                                    parameters=dict(PARAMS, source="", flow=flow),
                                    evidence_refs=[flow]),
    }


def rule_of(body: dict) -> str:
    return data_of(body)["detection"]["rule"]


def reply(body: dict, text: dict) -> A.Reply:
    """The provider's answer *text*, billed exactly the call's worst case (every prompt token
    a cache write at `TOKENS`, all of max_tokens), so what a settled call counts is what it
    reserved."""
    return A.Reply(status=200, body={
        "content": [{"type": "text", "text": json.dumps(text)}], "stop_reason": "end_turn",
        "usage": {"input_tokens": 0, "output_tokens": int(body["max_tokens"]),
                  "cache_creation_input_tokens": TOKENS}}, attempts=1, latency_s=0.1)


class Provider:
    """A fake provider answering each detection by its rule; with *parties*, no call is
    answered until that many have started (`BARRIER_S` bounds the wait). *raises* maps a rule
    to the exception its call raises instead. Counts the calls in flight at once."""

    def __init__(self, parties: int = 0, raises: dict = None, before=None):
        self.barrier = threading.Barrier(parties, timeout=BARRIER_S) if parties else None
        self.raises = dict(raises or {})
        self.before = before
        self.answers = answers()
        self.lock = threading.Lock()
        self.flying = self.peak = 0
        self.sent = []

    def __call__(self, body, key):
        rule = rule_of(body)
        with self.lock:
            self.sent.append(rule)
            self.flying += 1
            self.peak = max(self.peak, self.flying)
        try:
            if self.barrier is not None:
                self.barrier.wait()
            if self.before:
                self.before(rule)
            if rule in self.raises:
                raise self.raises[rule]
            return reply(body, self.answers[rule])
        finally:
            with self.lock:
                self.flying -= 1


@pytest.fixture
def three(world, monkeypatch):  # noqa: F811 - the fixture, used
    """The feature on for the network, the three detections' packs kept as `detect.observe`
    keeps them, and the provider's count fixed at `TOKENS`."""
    _feature_on()
    monkeypatch.setattr(A, "count_tokens", lambda body, key, **kw: A.Count(tokens=TOKENS))
    packs = {c["detection"]["key"]: keep_pack(c) for c in THREE}
    return world, packs


def observed(packs: dict, cases=THREE):
    dets = [detection_of(c) for c in cases]
    return lambda network, collected: {
        "ok": True, "fired": [d["key"] for d in dets], "resolved": [], "detections": dets,
        "kept": {d["key"]: packs[d["key"]] for d in dets}}


def a_pass(packs, send, cases=THREE):
    return LP.run_pass(NET, collect=lambda: {"network": NET, "summary": {"switches": 2},
                                             "state": "ok"},
                       observe=observed(packs, cases), job="sdn-loop-default-test", send=send,
                       driver=NO_DRIVER, now=lambda: 1_790_000_000.0)


def responses() -> list:
    """The responses awaiting a person, in the order kept: each's detection, action, risk,
    parameters, classification and words, ids left out."""
    out = []
    for r in LP.awaiting(NET)["rows"]:
        c = dict(r["classification"] or {})
        for k in ("call_id", "cost_usd"):
            c.pop(k, None)
        out.append((r["detection"]["key"], r["action"], r["risk"], r["params"], c,
                     same(r["classified"]), r["why"]))
    return out


def same(words: str) -> str:
    """*words* with what differs between two runs of one pass taken out: call and response
    ids, and times."""
    words = re.sub(r"\bai-[0-9a-f]{16}\b", "<call>", words)
    words = re.sub(r"AI call \S+:", "AI call <call>:", words)
    words = re.sub(r"resp-[0-9a-f]+", "<resp>", words)
    return re.sub(r"\d+\.\d s", "<s> s", words)


def lines(out: dict) -> list:
    return [(x["step"], same(x["words"])) for x in out["lines"]]


def forget_the_pass() -> None:
    """The network's responses and loop log removed, so the same pass runs again from
    nothing (the packs and the record of AI calls stay)."""
    for name in (LP.PENDING_FILE, LP.LOG_FILE):
        path = LP._path(NET, name)
        if os.path.exists(path):
            os.remove(path)


# ── at once ───────────────────────────────────────────────────────────────────────────────────

def test_a_pass_of_three_detections_makes_its_three_calls_at_once(three):
    world, packs = three
    send = Provider(parties=3)
    out = a_pass(packs, send)
    assert out["ok"], out
    assert send.peak == 3, f"{send.peak} call(s) in flight at once of 3"
    assert sorted(send.sent) == ["flood", "scan", "unauthorised_flow"]
    got = [(r[0], r[1]) for r in responses()]
    assert got == [(SCAN["detection"]["key"], "drop_source"),
                   (FLOOD["detection"]["key"], "drop_source"),
                   (REDIRECT["detection"]["key"], "remove_flow")], got
    assert sorted(r["verdict"] for r in rows()) == ["ok", "ok", "ok"]
    each = [x for x in out["lines"] if x["step"] == "classify"]
    assert [("the step took" in x["words"]) for x in each] == [True, True, True, False]
    assert each[-1]["words"].startswith(
        f"classified 3 detections at once, each its own call (at most {LP.CLASSIFY_WORKERS} "
        "at a time): ") and each[-1]["detections"] == 3 and "took_s" in each[-1]


def test_the_outcomes_and_the_log_are_the_serial_pass_s_whatever_order_calls_finish(
        three, monkeypatch):
    """The first detection's call is made to finish last: the log and the responses still
    read in the detections' order, line for line the serial pass's."""
    world, packs = three
    bound = LP.CLASSIFY_WORKERS
    monkeypatch.setattr(LP, "CLASSIFY_WORKERS", 1)
    serial = a_pass(packs, Provider())
    # The total names its bound, the one word the two passes differ in by design.
    serial_lines = [(s, w.replace("(at most 1 at a time)", f"(at most {bound} at a time)"))
                    for s, w in lines(serial)]
    serial_responses = responses()
    assert [s for s, _w in serial_lines].count("classify") == 4

    forget_the_pass()
    monkeypatch.setattr(LP, "CLASSIFY_WORKERS", bound)
    others_done = threading.Event()
    finished = []
    real = LP.classify

    def classify(network, d, job, **kw):
        got = real(network, d, job, **kw)
        finished.append(d["rule"])
        if sorted(finished) == ["flood", "unauthorised_flow"]:
            others_done.set()
        return got
    monkeypatch.setattr(LP, "classify", classify)

    def scan_last(rule):
        if rule == "scan":
            assert others_done.wait(BARRIER_S), "the other two classifications never finished"
    send = Provider(parties=3, before=scan_last)
    at_once = a_pass(packs, send)
    assert send.peak == 3, f"{send.peak} call(s) in flight at once of 3"
    assert finished[-1] == "scan" and THREE[0] is SCAN, \
        "the first detection's call finished last: completion order is not the detections'"
    assert lines(at_once) == serial_lines
    assert responses() == serial_responses
    assert at_once["fired"] == serial["fired"] and \
        len(at_once["proposed"]) == len(serial["proposed"]) == 3


# ── isolated ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("exc,kind", [(RuntimeError("planted: the call broke"), "exception"),
                                      (A.Overloaded("planted: overloaded", status=529),
                                       "overloaded")], ids=["raises", "provider_fails"])
def test_one_call_that_fails_is_that_detection_s_alone(three, exc, kind):
    world, packs = three
    out = a_pass(packs, Provider(parties=3, raises={"flood": exc}))
    assert out["ok"] and out["error"] == "", out
    by_key = {r[0]: r for r in responses()}
    flood = by_key[FLOOD["detection"]["key"]]
    assert flood[4] == {} and flood[5].startswith(f"no AI classification ({kind}: "), flood
    assert flood[6] == LP.NOT_CLASSIFIED_WHY and flood[1], "the rule's default, for a person"
    assert by_key[SCAN["detection"]["key"]][4]["threat_type"] == "port_scan"
    assert by_key[REDIRECT["detection"]["key"]][1] == "remove_flow"
    verdicts = {r["subject"]["id"]: r["verdict"] for r in rows()}
    assert verdicts == {SCAN["detection"]["key"]: "ok", FLOOD["detection"]["key"]: kind,
                        REDIRECT["detection"]["key"]: "ok"}


def test_a_cap_that_fits_two_of_three_refuses_one_recorded_for_that_detection_alone(three):
    """Each call's worst case is reserved against the network's feature cap (C2039); the cap
    is set to two and a half calls' worst case, and each call is billed exactly its worst
    case, so whichever two reach the reservation first are sent and the third is refused."""
    import time

    from modules.settings_schema import write_settings

    world, packs = three
    pin = profiles.TASKS[CL.CLASSIFY_FEATURE]
    worst = gateway.worst_case_usd(pin["model"], {"max_tokens": pin["max_tokens"]}, TOKENS)
    # `_feature_on`'s entry, its day cap two and a half calls' worst case.
    assert write_settings({"ai_background": {"default": {CL.CLASSIFY_FEATURE: {
        "on": True, "by": "admin@example.com", "verified": "access",
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "day_cap_usd": 2.5 * worst, "month_cap_usd": 5.0}}}})["ok"]
    send = Provider(parties=2)
    out = a_pass(packs, send)
    assert out["ok"], out
    assert len(send.sent) == 2 and send.peak == 2
    got = rows()
    assert sorted(r["verdict"] for r in got) == ["feature_cap", "ok", "ok"], \
        [(r["verdict"], r.get("detail")) for r in got]
    assert all(abs(float(r["cost_usd"]) - worst) < 1e-9 for r in got if r["verdict"] == "ok"), \
        "the premise: a call is billed its worst case"
    (refused,) = [r["subject"]["id"] for r in got if r["verdict"] == "feature_cap"]
    for key, _a, _r, _p, c, words, _why in responses():
        if key == refused:
            assert c == {} and words.startswith("no AI classification (feature_cap: "), words
        else:
            assert c.get("threat_detected") is True and "feature_cap" not in words, words


@pytest.mark.parametrize("workers", [1, None], ids=["one_after_the_other", "at_once"])
def test_no_call_is_made_past_the_cap_at_once_or_one_after_the_other(three, monkeypatch,
                                                                      workers):
    """The same cap (two and a half calls' worst case, each call billed exactly its worst
    case) on the serial pass (`CLASSIFY_WORKERS` 1) and on the pass at once, with no barrier,
    so the calls reach the reservation as they come. One after the other: two calls sent, the
    third, the last detection's, refused. At once: never more requests than the serial pass's
    two and never a cost past the cap; it may refuse more, as a call whose row is recorded and
    whose reservation is not yet settled is counted twice by a judge in between
    (modules/ai/reservations.py, "Settled"; C2054). Every refusal is a recorded cap refusal
    with nothing sent, and every request that reached the provider is a recorded call."""
    import time

    from modules.settings_schema import write_settings

    world, packs = three
    pin = profiles.TASKS[CL.CLASSIFY_FEATURE]
    worst = gateway.worst_case_usd(pin["model"], {"max_tokens": pin["max_tokens"]}, TOKENS)
    cap = 2.5 * worst
    assert write_settings({"ai_background": {"default": {CL.CLASSIFY_FEATURE: {
        "on": True, "by": "admin@example.com", "verified": "access",
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "day_cap_usd": cap, "month_cap_usd": 5.0}}}})["ok"]
    if workers:
        monkeypatch.setattr(LP, "CLASSIFY_WORKERS", workers)
    send = Provider()
    out = a_pass(packs, send)
    assert out["ok"], out
    got = rows()
    said = [(r["verdict"], r.get("detail")) for r in got]
    assert len(got) == 3 and {r["verdict"] for r in got} <= {"ok", "feature_cap"}, said
    sent = [r for r in got if r["verdict"] == "ok"]
    assert len(send.sent) == len(sent), "every request that reached the provider is recorded"
    assert sum(float(r["cost_usd"]) for r in sent) <= cap, f"a call past the cap: {said}"
    refused = [r["subject"]["id"] for r in got if r["verdict"] == "feature_cap"]
    if workers == 1:
        assert len(sent) == 2 and refused == [THREE[-1]["detection"]["key"]], said
    else:
        assert 1 <= len(sent) <= 2 and len(refused) == 3 - len(sent), said


# ── bounded ───────────────────────────────────────────────────────────────────────────────────

def test_the_bound_is_derived_from_the_busiest_pass_measured():
    """`BUSIEST_PASS_MEASURED` is the walk's: the most detections that fired in one collection
    (each detection's ``at``) among every one the walk's loop classified."""
    with open(os.path.join(CASES, "recorded_walk.json"), encoding="utf-8") as fh:
        walk = json.load(fh)["cases"]
    per_pass = collections.Counter(c["detection"]["at"] for c in walk)
    assert len(walk) >= 20, "the floor: the walk's set is read whole"
    assert max(per_pass.values()) == LP.BUSIEST_PASS_MEASURED
    assert LP.BUSIEST_PASS_MEASURED <= LP.CLASSIFY_WORKERS, \
        "the busiest pass measured waits one call, not two"


def test_a_pass_of_more_detections_than_the_bound_runs_at_most_the_bound_at_once(
        networks, monkeypatch):  # noqa: F811
    """`CLASSIFY_WORKERS` + 3 detections: the first `CLASSIFY_WORKERS` calls each wait until
    all of them have started (so that many ran at once), the rest after; every detection is
    classified, and no more than the bound were ever in flight."""
    bound = LP.CLASSIFY_WORKERS
    n = bound + 3
    dets = [{"key": f"k{i:02d}", "rule": "scan", "words": f"planted detection {i}"}
            for i in range(n)]
    barrier = threading.Barrier(bound, timeout=BARRIER_S)
    lock = threading.Lock()
    seen = {"flying": 0, "peak": 0, "started": 0}
    asked = []

    def classify(network, d, job, **kw):
        with lock:
            seen["flying"] += 1
            seen["peak"] = max(seen["peak"], seen["flying"])
            first = seen["started"] < bound
            seen["started"] += 1
        try:
            if first:
                barrier.wait()
            return LP.verdict_of(network, d, {"ok": False, "error": "feature_off",
                                              "detail": "planted"})
        finally:
            with lock:
                seen["flying"] -= 1
    monkeypatch.setattr(LP, "classify", classify)
    real = fanout.read_each

    def read_each(fn, items, **kw):
        asked.append(kw.get("max_workers"))
        return real(fn, items, **kw)
    monkeypatch.setattr(fanout, "read_each", read_each)
    out = LP.run_pass(NET, collect=lambda: {"network": NET, "summary": {}, "state": "ok"},
                      observe=lambda network, collected: {
                          "ok": True, "fired": [d["key"] for d in dets], "resolved": [],
                          "detections": dets}, job="sdn-loop-default-test", driver=NO_DRIVER,
                      now=lambda: 1_790_000_000.0)
    assert out["ok"], out
    assert asked == [bound], "the pool is the loop's bound"
    assert seen["peak"] == bound and seen["started"] == n
    assert len(LP.awaiting(NET)["rows"]) == n
    keys = [x["words"] for x in out["lines"] if x["step"] == "classify"]
    assert len(keys) == n + 1
