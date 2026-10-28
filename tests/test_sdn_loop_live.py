"""The SDN loop on the LIVE path (C1968, C1969, C1970, C1972; Lab 8 walk step 10, 2026-10-27):
the loop's own collection, detection and pack builder (`collect_threat_data`, `detect.observe`,
`evidence_pack.build_detection`) run over the Lab 8 run's real controller answers
(tests/fixtures/sdn/lab8/), then its classify step through the real gateway with a fake
provider. No provider is called, no switch is touched.

- **One id scheme (C1969)**: the walk's two answers cited the detection, the first flow and the
  coverage by the pack's ``sdn:<n>`` references, which were sent beside the pieces' own ids but
  never accepted. Now every id in the request is one the check accepts and every id the check
  accepts is in the request, and no pack reference is sent; an answer citing the walk's three
  pieces passes. The same holds for every recorded, held-out and walk case built by the pack
  builder.
- **Fail-safe (C1968)**: a refused classification, or none (the feature off), keeps the rule's
  catalogue default awaiting a person, said and with the refused answer's call, and AUTO never
  acts on it. A detection that resolves leaves its response awaiting, marked "no longer active
  since", its classification kept; one that fires again while it awaits is not classified
  again. Only a person closes a response; an older record's ``cleared`` still reads closed.
- **The pack in hand (C1970)**: the loop classifies the pack `detect.observe` just kept, and
  never reads the pack store to find it; the step's time is in its log line.
- **Cadence (C1972)**: passes are scheduled start to start; one that overruns starts the next
  at once and the log says so.
"""
import json
import re
import threading

import pytest

from modules import evidence_pack as EP
from modules.ai import calls
from modules.sdn import closed_loop as CL
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from tests.sdn_fakes import lab8
from tests.test_sdn_classify import (FLOOD, NET, PARAMS, REDIRECT, SCAN, _feature_on, answer,
                                     case, rows, world)  # noqa: F401 - the fixture
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_lab8 import collect, lab  # noqa: F401 - the fixture
from tests.test_sdn_modes_loop import mark_lab

T0 = 1_790_000_000.0
NO_DRIVER = lambda n, c: {"ok": False, "error": "unused"}  # noqa: E731


def data_of(body: dict) -> dict:
    """The request's data blocks, parsed: ``{"detection": {...}, "evidence": {...}, ...}``."""
    text = body["messages"][0]["content"]
    return {m.group(1): json.loads(m.group(2)) for m in
            re.finditer(r'<data name="(\w+)">\n(.*?)\n</data>', text, re.S)}


def ids_in(data: dict) -> set:
    """Every evidence id the request carries: each piece's, the detection's own and its list."""
    det, pieces = data["detection"], data["evidence"]["pieces"]
    return {det["id"], *det.get("evidence", ()), *(p["id"] for p in pieces)}


def citing(world, pick):
    """A fake provider answering a passing scan answer that cites ``pick(data)``."""
    base = world.send

    def send(body, key):
        world.answer = dict(world.answer, evidence_refs=pick(data_of(body)))
        return base(body, key)
    return send


def live_pass(world, capture="scan_s1.json", at=T0, send=None, **kw):
    """One loop pass on *capture* through the real collection, detection and pack builder."""
    got = collect(lab8(capture), at=at)
    return LP.run_pass(NET, collect=lambda: got, job="sdn-loop-default-test",
                       send=send or world.send, driver=NO_DRIVER, now=lambda: at, **kw)


# ── one id scheme (C1969) ─────────────────────────────────────────────────────────────────────

@pytest.mark.usefixtures("lab")
def test_every_id_the_live_request_holds_is_accepted_and_every_accepted_id_is_in_it(world):
    _feature_on()
    out = live_pass(world)
    assert out["ok"] and out["fired"], out
    (body,) = world.sent
    data = data_of(body)
    (key,) = out["fired"]
    pack, _why = CL.detection_pack(NET, key)
    accepted = CL.sent_evidence(CL._sdn_section(pack))["ids"]
    assert ids_in(data) == accepted
    assert all(p.get("id") for p in data["evidence"]["pieces"]) and data["detection"]["id"]
    text = json.dumps(data)
    assert '"ref"' not in text and '"sdn:' not in text, "the pack's references are not sent"
    assert len(pack["sections"][-1]["pieces"]) == len(accepted), "one id per piece kept"


@pytest.mark.usefixtures("lab")
def test_the_walk_s_answer_citing_the_first_second_and_last_pieces_passes(world):
    """The walk's answers cited sdn:1, sdn:2 and sdn:52 (the detection, the busiest flow, the
    coverage), all sent and all refused. The same pieces cited by the scheme sent pass."""
    _feature_on()
    pick = lambda d: [d["detection"]["id"], d["evidence"]["pieces"][0]["id"],  # noqa: E731
                      d["evidence"]["pieces"][-1]["id"]]
    out = live_pass(world, send=citing(world, pick))
    (resp,) = LP.awaiting(NET)["rows"]
    assert resp["classification"] is not None, resp["classified"]
    assert resp["action"] == "drop_source" and resp["params"] == {"source": "192.0.2.1"}
    assert resp["classification"]["evidence_refs"][0].startswith("detection:scan:")
    assert out["proposed"] == [resp["id"]]


@pytest.mark.usefixtures("lab")
def test_the_unauthorised_redirect_built_live_sends_exactly_its_accepted_ids(world):
    _feature_on()
    out = live_pass(world, capture="unauthorised_s2.json")
    unauth = [k for k in out["fired"]
              if CL.detection_pack(NET, k)[0]["rule"] == "SDN unauthorised flow"]
    assert unauth, out
    data = data_of(world.sent[out["fired"].index(unauth[0])])
    pack, _why = CL.detection_pack(NET, unauth[0])
    assert ids_in(data) == CL.sent_evidence(CL._sdn_section(pack))["ids"]


@pytest.mark.parametrize("name,key", [(f, c["key"]) for f in ("recorded", "held_out",
                                                               "recorded_walk")
                                      for c in json.load(open(
                                          f"tests/fixtures/ai_cases/sdn_classify/{f}.json"))[
                                          "cases"]])
def test_every_case_built_by_the_pack_builder_sends_exactly_its_accepted_ids(world, name, key):
    from tests.test_sdn_classify import classify_as_person, keep_pack
    c = case(name, key)
    pack = keep_pack(c)
    world.answer = answer(evidence_refs=["x"])          # refused or not, the request is sent
    classify_as_person(world, c)
    (body,) = world.sent
    assert ids_in(data_of(body)) == CL.sent_evidence(CL._sdn_section(pack))["ids"]


def test_the_detection_s_list_names_only_the_evidence_sent_and_counts_the_rest():
    sent = CL.sent_evidence(SCAN["section"])
    det = sent["detection"]
    assert set(det["evidence"]) <= sent["ids"]
    assert det["evidence_not_sent"] == len(SCAN["section"]["pieces"][0]["evidence"]) - \
        len(det["evidence"]) > 0


# ── fail-safe (C1968) ─────────────────────────────────────────────────────────────────────────

def _auto():
    import time
    mark_lab(NET)
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="lab 8 run",
               until=time.time() + 600, allowed_risk="low")


def _no_apply(monkeypatch):
    applied = []
    monkeypatch.setattr(CL, "respond_to_threat", lambda *a, **k: applied.append(a) or {})
    return applied


@pytest.mark.usefixtures("lab")
def test_a_refused_classification_awaits_a_person_with_its_call_and_auto_does_not_act(
        world, monkeypatch):
    _feature_on()
    _auto()
    applied = _no_apply(monkeypatch)
    world.answer = answer(evidence_refs=["flow:not-sent"])
    live_pass(world)
    assert applied == [], "AUTO never acts on a refused classification"
    (resp,) = LP.awaiting(NET)["rows"]
    assert resp["action"] == "drop_source" and resp["classification"] is None
    assert resp["classified"].startswith("AI classification refused: it cites flow:not-sent")
    assert "proposed by the catalogue default" in resp["classified"]
    (call,) = rows()
    assert resp["refused_call"] == call["id"] and resp["why"] == LP.NOT_CLASSIFIED_WHY


@pytest.mark.usefixtures("lab")
def test_with_no_classification_auto_does_not_act_and_the_default_awaits_a_person(
        world, monkeypatch):
    _auto()
    applied = _no_apply(monkeypatch)
    live_pass(world)                                    # the feature off: the default
    assert applied == [] and world.sent == []
    (resp,) = LP.awaiting(NET)["rows"]
    assert resp["action"] == "drop_source" and resp["why"] == LP.NOT_CLASSIFIED_WHY


@pytest.mark.usefixtures("lab")
def test_a_resolved_detection_leaves_its_response_awaiting_marked_with_its_classification(
        world):
    _feature_on()
    pick = lambda d: [d["evidence"]["pieces"][0]["id"]]  # noqa: E731
    live_pass(world, send=citing(world, pick))
    (before,) = LP.awaiting(NET)["rows"]
    out = live_pass(world, capture="l2_only_s1.json", at=T0 + 120)
    (after,) = LP.awaiting(NET)["rows"]
    assert out["inactive"] == [before["id"]] == [after["id"]]
    assert after["inactive_since"] == LP._iso(T0 + 120), "the collection that no longer shows it"
    assert after["classification"] == before["classification"] is not None
    detect_line = next(x for x in out["lines"] if x["step"] == "detect")
    assert "1 of them with a response still awaiting a person" in detect_line["words"]


@pytest.mark.usefixtures("lab")
def test_a_detection_firing_again_while_its_response_awaits_is_not_classified_again(world):
    _feature_on()
    pick = lambda d: [d["evidence"]["pieces"][0]["id"]]  # noqa: E731
    send = citing(world, pick)
    live_pass(world, send=send)
    live_pass(world, capture="l2_only_s1.json", at=T0 + 120, send=send)
    out = live_pass(world, at=T0 + 240, send=send)
    assert len(world.sent) == 1, "one call: the response awaiting holds its classification"
    (resp,) = LP.awaiting(NET)["rows"]
    assert resp["inactive_since"] == "" and out["proposed"] == []
    assert any("not classified again" in x["words"] for x in out["lines"])


def test_only_a_person_closes_a_response_and_an_older_cleared_row_reads_closed(networks):  # noqa: F811
    d = {"key": "k1", "rule": "scan"}
    row = LP.propose(NET, d, "drop_source", "low", why="HITL", now=T0)
    with pytest.raises(ValueError, match="confirmed or dismissed by a person"):
        LP.resolve(NET, row["id"], "cleared", actor="Mercury")
    LP.mark(NET, row["id"], "inactive", since="2026-10-27T17:01:11Z", now=T0 + 1)
    assert LP.awaiting(NET)["rows"][0]["inactive_since"] == "2026-10-27T17:01:11Z"
    LP._append(NET, LP.PENDING_FILE, {"kind": "cleared", "id": row["id"], "at": "x"})
    assert LP.awaiting(NET)["rows"] == [], "an older release's cleared row still closes"


@pytest.mark.usefixtures("lab")
def test_the_card_says_the_threat_is_no_longer_active_and_links_the_refused_answer(world):
    import app as APP
    from html import unescape
    _feature_on()
    world.answer = answer(evidence_refs=["flow:not-sent"])
    live_pass(world)
    live_pass(world, capture="l2_only_s1.json", at=T0 + 120)
    html = unescape(APP.app.test_client().get(f"/v2/sdn/responses?list={NET}")
                    .get_data(as_text=True))
    (call,) = rows()
    assert "Threat no longer active since" in html and "awaits your approval or dismissal" in html
    assert "AI classification refused: it cites flow:not-sent" in html
    link = html[html.find("The refused answer in History") - 160:][:200]
    assert f"call={call['id']}" in link and "history" in link, link


# ── the pack in hand (C1970) ──────────────────────────────────────────────────────────────────

@pytest.mark.usefixtures("lab")
def test_the_loop_classifies_the_pack_observe_kept_without_reading_the_store(world,
                                                                             monkeypatch):
    _feature_on()

    def read_all(*a, **k):
        raise AssertionError("the pack store was read to find the pack in hand")
    monkeypatch.setattr(EP, "find", read_all)
    monkeypatch.setattr(EP, "read", read_all)
    out = live_pass(world)
    assert len(world.sent) == 1
    line = next(x for x in out["lines"] if x["step"] == "classify")
    assert "the step took" in line["words"] and "took_s" in line


# ── the replay (scripts/nmas-sdn-replay) ──────────────────────────────────────────────────────

def _replay_script():
    import importlib.machinery
    import importlib.util
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts",
                        "nmas-sdn-replay")
    loader = importlib.machinery.SourceFileLoader("nmas_sdn_replay", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


@pytest.mark.usefixtures("lab")
def test_the_replay_classifies_each_kept_pack_as_an_evaluation(world, monkeypatch, tmp_path):
    """A kept detection's pack, frozen as kept, classified through the fixed path by its key,
    recorded as evaluation:<run>; nothing kept with any response."""
    import types
    from modules.ai import gateway
    out = live_pass(world)                              # the feature off: no call, a pack kept
    (key,) = out["fired"]
    before = LP._read(NET, LP.PENDING_FILE)["rows"]
    monkeypatch.setattr(gateway, "anthropic_adapter", types.SimpleNamespace(
        **{**vars(gateway.anthropic_adapter),
           "send": citing(world, lambda d: [d["evidence"]["pieces"][0]["id"]])}))
    report = tmp_path / "replay.json"
    assert _replay_script().replay(NET, [key], "evaluation:replay-test", 2, str(report),
                                   False) == 0
    got = json.loads(report.read_text())
    assert (got["passed"], got["asked"]) == (2, 2)
    assert [r["action"] for r in got["recordings"][key]] == ["drop_source"] * 2
    assert [r["actor"] for r in rows()[:2]] == ["evaluation:replay-test"] * 2
    assert LP._read(NET, LP.PENDING_FILE)["rows"] == before


@pytest.mark.usefixtures("lab")
def test_the_replay_asks_with_the_prompt_version_named(world, monkeypatch, tmp_path):
    """C1988: `--prompt 3` replays a kept pack with prompt v3 (measured before it is adopted):
    the request's system text is v3's, never v1's scan-to-drop line, and the report names
    the version."""
    import types
    from modules.ai import gateway
    out = live_pass(world)
    (key,) = out["fired"]
    inner = citing(world, lambda d: [d["evidence"]["pieces"][0]["id"]])
    systems = []

    def send(body, *a, **kw):
        systems.append("".join(b["text"] for b in body["system"]))
        return inner(body, *a, **kw)
    monkeypatch.setattr(gateway, "anthropic_adapter", types.SimpleNamespace(
        **{**vars(gateway.anthropic_adapter), "send": send}))
    report = tmp_path / "replay-v3.json"
    assert _replay_script().replay(NET, [key], "evaluation:replay-v3", 1, str(report), False,
                                   ("sdn_classify", 3)) == 0
    assert json.loads(report.read_text())["prompt"] == "sdn_classify.v3"
    (system,) = systems
    assert "Take the catalogue's `default` action" in system
    assert "a scan is answered by dropping its source" not in system


@pytest.mark.usefixtures("lab")
def test_the_replay_s_dry_run_says_what_would_be_sent_and_asks_nothing(world, capsys):
    out = live_pass(world)
    (key,) = out["fired"]
    calls_before = len(rows())
    assert _replay_script().replay(NET, [key, "no-such-key"], "", 0, "", True) == 0
    said = capsys.readouterr().out
    assert f"{key}: pack " in said and "intact" in said and '"ids": 52' in said
    assert "no-such-key: no pack" in said and len(rows()) == calls_before


# ── cadence (C1972) ───────────────────────────────────────────────────────────────────────────

class _Stop:
    """A stop event a fake clock drives: `wait` moves the clock; set after *passes* passes."""

    def __init__(self, clock, passes):
        self.clock, self.left, self.waits = clock, passes, []

    def is_set(self):
        return self.left <= 0

    def wait(self, s):
        self.waits.append(round(s, 3))
        self.clock[0] += s


def _schedule(networks, took, interval=10.0, passes=3):  # noqa: F811
    clock = [100.0]
    stop = _Stop(clock, passes)

    def one():
        clock[0] += took
        stop.left -= 1
    LP.schedule(NET, interval, stop, one, clock=lambda: clock[0], wall=lambda: T0)
    return stop


def test_passes_are_scheduled_start_to_start(networks):  # noqa: F811
    stop = _schedule(networks, took=6.0)
    assert stop.waits == [4.0, 4.0], "a 6 s pass waits 4 s: every 10 s from start to start"
    assert LP.log_lines(NET)["state"] == "absent"


def test_a_pass_that_overruns_starts_the_next_at_once_and_says_so(networks):  # noqa: F811
    stop = _schedule(networks, took=12.0)
    assert stop.waits == []
    lines = LP.log_lines(NET)["rows"]
    assert [x["step"] for x in lines] == ["cadence", "cadence"]
    assert lines[0]["words"] == ("the pass took 12.0 s, at or over the 10 s interval: the next "
                                 "starts at once")


def test_the_job_runs_its_passes_through_the_scheduler(networks, monkeypatch):  # noqa: F811
    seen = threading.Event()
    monkeypatch.setattr(LP, "schedule", lambda network, interval, stop, one, **kw:
                        (seen.set(), stop.wait(5)))
    LP.start(NET, actor="op@example.com", interval=10)
    try:
        assert seen.wait(5)
    finally:
        LP.stop(NET, actor="op@example.com")
        LP._jobs[NET]["thread"].join(10)
