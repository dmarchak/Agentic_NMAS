"""Where a classified detection's time goes (C1970, the one measurement): the Lab 8 walk's
classify step landed about 60 s after its detection although its AI call took 4 to 6 s. Each
detection the loop classifies gets a ``timing`` line after its response's, stage names and
seconds only (`loop._timing_words`), and the same as ``stages``: the pass's detect (its own
pack's build inside it), holds and incidents, then its own queue, classify call (prepare,
gateway, check, and the provider's count and send from the call's row in the record of AI
calls), wait for its line, and response, and the total from its detection to its response.

The data: the Lab 8 run's own captures, the scan from h1 on s1 and the unauthorised redirect
on s2 (tests/fixtures/sdn/lab8/), collected and judged for real (`collect_threat_data` on
Ryu's captured answers, `detect.observe` building and keeping each pack); the real gateway
with a stub provider and a stub token count (no provider request). AUTO's apply runs through
the flow-operation core on `tests.sdn_fakes.FakeRyu`.

- **Carried**: each classified detection's line names every stage, in order, its words only
  stage names and seconds; the provider's count and send are its call's row's.
- **Where it says**: on a clock that moves only where a stage is planted to take time, each
  stage's seconds are exactly that stage's, so a minute in any of them is named by its line.
- **AUTO's apply is its response's**: the apply's waits (its counters read
  `flow_ops.COUNTER_INTERVAL` apart) are the respond stage, so the next detection's line
  waits for it (the responses are one after the other: a write is never concurrent).

Measured by work, never wall-clock: the stages are asserted on the planted clock, and the
real pass asserts only that each is present and not negative.
"""
import json
import re
import threading
import time

import pytest

from modules import evidence_pack as EP
from modules.ai import anthropic_adapter as A
from modules.ai import calls, reservations
from modules.sdn import closed_loop as CL
from modules.sdn import flow_ops
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from tests.sdn_fakes import Clock, lab8
from tests.test_sdn_classify import _feature_on, answer, world  # noqa: F401 - the fixture
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_lab8 import collect
from tests.test_sdn_lab8 import lab as lab8_net  # noqa: F401 - the fixture
from tests.test_sdn_loop_live import data_of
from tests.test_sdn_modes_loop import mark_lab

NET = "Default"
JOB = "sdn-loop-default-test"
AT = 1_790_000_000.0
NO_DRIVER = lambda n, c: {"ok": False, "error": "unused"}  # noqa: E731
#: How long a stub call waits for the other to start: both start within milliseconds of the
#: first (tests/test_sdn_loop_parallel.py's BARRIER_S), so a serial pass fails in seconds.
BARRIER_S = 10.0
#: The provider's latencies the stubs report (seconds), so the line's figures are the row's.
COUNT_S, SEND_S = 0.5, 4.5

#: Every stage a classified detection's line names, in its order (`loop._timing_words`).
STAGES = ("detect", "pack", "holds", "incidents", "queued", "classify", "prepare", "gateway",
          "count", "send", "check", "waited", "respond", "total", "read")
S = r"\d+\.\d s"
WORDS = re.compile(
    rf"detect {S} \(its pack {S}\), holds {S}, incidents {S}, queued {S}, classify {S} "
    rf"\(prepare {S}; gateway {S}: count {S}, send {S}, the rest {S}; check {S}\), waited {S}, "
    rf"respond {S}: {S} from detection to response \(read before it {S}\)")


def scan_and_redirect():
    """The Lab 8 run's s1 (the scan from h1) and s2 (the unauthorised redirect) read in one
    collection, the switch list naming both (the captures cut it to one each: the one edit)."""
    s1, s2 = lab8("scan_s1.json"), lab8("unauthorised_s2.json")
    both = dict(s1[0], body=json.dumps([1, 2]))
    return [both] + [e for e in s1 + s2 if e["path"] != "/stats/switches"]


def timing_lines(out):
    return [x for x in out["lines"] if x["step"] == "timing"]


class Provider:
    """A stub provider answering the planted scan answer to every call, each call's start and
    end kept (time.monotonic); with *parties*, none answers until that many have started."""

    def __init__(self, parties=0, latency=SEND_S, before=None):
        self.barrier = threading.Barrier(parties, timeout=BARRIER_S) if parties else None
        self.latency, self.before = latency, before
        self.lock = threading.Lock()
        self.spans = []

    def __call__(self, body, key):
        start = time.monotonic()
        try:
            if self.barrier is not None:
                self.barrier.wait()
            if self.before:
                self.before()
            return A.Reply(status=200, body={
                "content": [{"type": "text", "text": json.dumps(answer())}],
                "stop_reason": "end_turn", "usage": {"input_tokens": 3000, "output_tokens": 300}},
                attempts=1, latency_s=self.latency)
        finally:
            with self.lock:
                self.spans.append((data_of(body)["detection"]["rule"], start, time.monotonic()))


@pytest.fixture
def counted(monkeypatch):
    """The provider's token count stubbed (no request), reporting `COUNT_S`; *advance* moves
    a planted clock by that much as it counts."""
    hold = {"advance": None}

    def count(body, key, **kw):
        if hold["advance"]:
            hold["advance"](COUNT_S)
        return A.Count(tokens=3000, latency_s=COUNT_S)
    monkeypatch.setattr(A, "count_tokens", count)
    return hold


# ── carried ───────────────────────────────────────────────────────────────────────────────────

@pytest.mark.usefixtures("lab8_net")
def test_each_classified_detection_s_line_names_every_stage_in_the_lab_8_run_s_pass(
        world, counted):
    """The scan on s1 and the redirect on s2, judged for real (each pack built and kept by
    `detect.observe`) and classified at once: two calls that overlap, and after each
    detection's response its timing line, stage names and seconds only."""
    _feature_on()
    got = collect(scan_and_redirect(), at=AT)
    send = Provider(parties=2)
    out = LP.run_pass(NET, collect=lambda: got, job=JOB, send=send, driver=NO_DRIVER,
                      now=lambda: AT)
    assert out["ok"], out
    assert sorted(r for r, _s, _e in send.spans) == ["scan", "unauthorised_flow"], \
        "the premise: the run's two threats are found and each is its own call"
    (a, a0, a1), (b, b0, b1) = send.spans
    assert a0 < b1 and b0 < a1, f"the two calls did not overlap: {send.spans}"

    lines = timing_lines(out)
    assert len(lines) == 2 == len(out["proposed"])
    steps = [x["step"] for x in out["lines"]]
    for i, step in enumerate(steps):
        if step == "timing":
            assert steps[i - 1] == "respond", "a timing line follows its detection's response"
    by_id = {r["id"]: r for r in calls.read()["rows"]}
    for x in lines:
        assert WORDS.fullmatch(x["words"]), x["words"]
        st = x["stages"]
        assert tuple(sorted(st)) == tuple(sorted(STAGES)), sorted(st)
        assert all(isinstance(v, float) and v >= 0 for v in st.values()), st
        assert (st["count"], st["send"]) == (COUNT_S, SEND_S), "the call's row's own times"
    assert len(by_id) == 2 and all(r["latency_s"] == SEND_S for r in by_id.values())


# ── where it says ─────────────────────────────────────────────────────────────────────────────

#: Each stage's planted seconds, binary-exact so the sums are exact.
PLANTED = {"read": 5.0, "pack": 0.5, "holds": 1.5, "incidents": 0.5, "prepare": 0.5,
           "reserve": 2.0, "check": 0.5, "respond": 1.0}


@pytest.mark.usefixtures("lab8_net")
def test_each_stage_s_seconds_are_that_stage_s_own(world, counted, monkeypatch):
    """A clock that moves only where a stage is planted to take time: the scan's line says
    each stage's own seconds, and the gateway's rest (the caps' reservation here) is its time
    less the provider's count and send."""
    _feature_on()
    clock = Clock(start=1000.0)

    def advance(s):
        clock.now += s

    def taking(name, fn):
        def run(*a, **kw):
            advance(PLANTED[name])
            return fn(*a, **kw)
        return run
    counted["advance"] = advance
    monkeypatch.setattr(EP, "record", taking("pack", EP.record))
    monkeypatch.setattr(LP, "_judge_holds", taking("holds", LP._judge_holds))
    monkeypatch.setattr(LP, "_incidents", taking("incidents", LP._incidents))
    monkeypatch.setattr(CL, "request_blocks", taking("prepare", CL.request_blocks))
    monkeypatch.setattr(reservations, "reserve", taking("reserve", reservations.reserve))
    monkeypatch.setattr(CL, "check_classification",
                        taking("check", CL.check_classification))
    monkeypatch.setattr(LP, "propose", taking("respond", LP.propose))
    got = collect(lab8("scan_s1.json"), at=AT)
    send = Provider(before=lambda: advance(SEND_S))
    out = LP.run_pass(NET, collect=taking("read", lambda: got), job=JOB, send=send,
                      driver=NO_DRIVER, now=lambda: AT, clock=clock)
    assert out["ok"], out
    (x,) = timing_lines(out)
    gateway = COUNT_S + PLANTED["reserve"] + SEND_S
    classify = PLANTED["prepare"] + gateway + PLANTED["check"]
    assert x["stages"] == {
        "read": 5.0, "detect": PLANTED["pack"], "pack": PLANTED["pack"],
        "holds": PLANTED["holds"], "incidents": PLANTED["incidents"], "queued": 0.0,
        "classify": classify, "prepare": PLANTED["prepare"], "gateway": gateway,
        "count": COUNT_S, "send": SEND_S, "check": PLANTED["check"], "waited": 0.0,
        "respond": PLANTED["respond"],
        "total": (PLANTED["pack"] + PLANTED["holds"] + PLANTED["incidents"] + classify
                  + PLANTED["respond"])}, x["stages"]
    assert "gateway 7.0 s: count 0.5 s, send 4.5 s, the rest 2.0 s" in x["words"], x["words"]
    assert x["words"].endswith(": 11.5 s from detection to response (read before it 5.0 s)")


# ── AUTO's apply is its response's ────────────────────────────────────────────────────────────

def test_auto_s_apply_is_its_respond_stage(networks, monkeypatch):  # noqa: F811
    """AUTO applies the scan's drop on a FakeRyu holding the capture's table: every wait the
    apply makes (its counters read `COUNTER_INTERVAL` apart) moves the planted clock, and the
    respond stage is exactly their sum, and nothing else moved."""
    from tests.test_sdn_detect import save, scan_flows
    from tests.test_sdn_respond import scan_detection, switch_with

    save()
    flows = scan_flows(25)
    d = scan_detection(flows)
    fake = switch_with(flows)
    mark_lab(NET)
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="lab 8 run",
               until=time.time() + 600, allowed_risk="low")
    monkeypatch.setattr(LP, "classify", lambda network, det, job, **kw: {
        "action": "drop_source", "risk": "low", "params": {"source": det["source"]},
        "classification": {"call_id": "call-planted", "action_id": "drop_source", "model": "m"},
        "person": False, "why": "", "refused_call": "", "words": "planted: passed"})
    clock, slept = Clock(start=1000.0), []

    def sleep(s):
        slept.append(s)
        clock.now += s
    out = LP.run_pass(NET, collect=lambda: {"network": NET, "state": "ok",
                                            "summary": {"switches": 1, "flows": 25}},
                      observe=lambda network, c: {"ok": True, "fired": [d["key"]],
                                                  "resolved": [], "detections": [d]},
                      driver=fake.driver, sleep=sleep, clock=clock)
    assert out["ok"] and out["applied"][0]["outcome"] == "verified", out
    assert sum(slept) >= flow_ops.COUNTER_INTERVAL, \
        f"the premise: the apply counts its counters {flow_ops.COUNTER_INTERVAL} s apart"
    (x,) = timing_lines(out)
    assert x["stages"]["respond"] == sum(slept) == x["stages"]["total"], x["stages"]
    assert "pack" not in x["stages"] and "(its pack" not in x["words"], \
        "a planted observe builds no pack, so none is said"
