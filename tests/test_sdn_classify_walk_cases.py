"""classify_threat's walk cases (E3, the operator's order of 2026-10-28; PHASE8_PLAN 17.1 S7,
13.6; tests/fixtures/ai_cases/sdn_classify/recorded_walk.json). No provider is called.

The Lab 8 walk of 2026-10-27 (22:17 to 23:34 UTC, the loop on the network "SDN lab", Ryu 4.34
over Open vSwitch 2.17.12) as recorded cases: every threat detection the walk's loop classified
(the scan on both switches, the two floods on both, the two unauthorised flows), the twelve
scan-rule fallback false positives of objective 2.3 (each named by its AI call), and five of
the walk's quiet collections with the fallback's threshold lowered, as the recorded set's
normal cases are. A third file, so the recorded set's own count and the held-out set stay as
they are.

- **What the code builds**: each case's detection and section are what the rule and the section
  builder make now from the evidence the walk kept (the pack's port, flows and coverage, the
  sample the section names): every fallback scan, every flood (its baseline and since as its
  threshold and measurement state them), and the injected flow on s1 through the displaced-flow
  and effect code (C2004, C2021) over the network's flow intent records as of the detection
  (tests/fixtures/sdn/lab8/walk_intent_s1.json). The three the kept evidence cannot rebuild are
  named, each with why, and only they.
- **The set**: eight threats (two scans, four floods, two unauthorised flows), none sharing the
  evidence of a recorded or held-out case. The file's pin, prompt and expectations against
  their evidence are checked with the other two files' (tests/test_sdn_classify_cases.py,
  ``FILES``).
- **Retired** (``retired``, 2026-11-02; board S-HR, C2238, PHASE8_PLAN 17.8): the twelve false
  positives by their calls (three on the walk's real flood, expected a flood with no action;
  nine on the pair checks, expected no threat) and five normal cases. The scan rule's
  packet-rate fallback is High packet rate now, which the loop watches and never sends to the
  classifier, so they left the classify set; each is kept as the walk kept it, and rebuilt
  from its evidence it is a High packet rate detection, its rule and words renamed and nothing
  else (`as_high_rate`).
"""
import json
import os
import re

import pytest

from modules.ai import cases
from modules.sdn import closed_loop as CL
from modules.sdn import detect as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join("tests", "fixtures", "ai_cases", "sdn_classify")
INTENT = os.path.join(ROOT, "tests", "fixtures", "sdn", "lab8", "walk_intent_s1.json")

#: The cases the walk's kept evidence cannot rebuild, each with why; only these.
KEPT_AS_IS = {
    "walk-scan-s1": "a ports scan counts sightings kept between collections (255 ports, 255 "
                    "flows in the collection), and the pack keeps its 50 busiest flows",
    "walk-scan-s2": "as walk-scan-s1, on s2",
    "walk-unauthorised-s2": "its effect needs s2's whole table (the flows that would take h3's "
                            "traffic without it), and the pack keeps the one flow; the walk's "
                            "loop ran before C2004 and C2021, so the detection as kept names no "
                            "effect",
}

#: Objective 2.3's twelve fallback false positives, by AI call (2.3-fallback-fp.txt), and
#: whether each coincided with the walk's real flood (h2 to h4, 20 Mbit/s UDP).
FALLBACK_CALLS = {
    "ai-4a9fc8a039854cbc": False, "ai-cd5983860a734033": False, "ai-e95ff8022bc94631": False,
    "ai-879b819e3f2c4b35": False, "ai-e05a251e5d5648cf": False, "ai-31d44805c50045a4": True,
    "ai-33ce6a0408de4dde": True, "ai-6f0d6ef158cb4fd9": True, "ai-a08b1c96c66849af": False,
    "ai-6969a72b9a144cd0": False, "ai-4355dae12de04650": False, "ai-593249ac96704c80": False,
}


def load(name="recorded_walk"):
    return cases.load(os.path.join(ROOT, DIR, f"{name}.json"))


def walk_intent() -> dict:
    """The network's flow intent records on s1 as of the injected flow (23:08:47): Mercury's
    three rate-limit flows of 23:05:23, in `flow_intent.intent`'s shape."""
    with open(INTENT, encoding="utf-8") as fh:
        rows = json.load(fh)["rows"]
    return {"state": "ok", "flows": rows, "withdrawn": {}, "error": ""}


def _piece(section: dict, kind: str) -> list:
    return [p for p in section["pieces"] if p.get("kind") == kind]


def collection_of(case: dict) -> tuple:
    """``(collected, switch)``: the collection as the case's section keeps it, in
    `collect_threat_data`'s shape: its switch's ports, flows and coverage as the pieces hold
    them (a flow's cookie back to the switch's number), the sample (the port piece's, else the
    seconds the section's source names: the walk read every port), its controller declaring the
    cookies the detection's threshold names, at the detection's time."""
    d, sec = case["detection"], case["section"]
    ports = _piece(sec, "port")
    sample = ports[0]["sample"] if ports else {
        "elapsed_s": float(re.search(r"port rates over ([0-9.]+) s$", sec["source"]).group(1))}
    (cov,) = _piece(sec, "coverage")
    flows = [{"dpid": d["dpid"], "table_id": f["table_id"], "priority": f["priority"],
              "cookie": int(f["cookie"], 16), "match": f["match"], "actions": f["actions"],
              "idle_timeout": f["idle_timeout"], "hard_timeout": f["hard_timeout"],
              "packet_count": f["packet_count"], "byte_count": f["byte_count"],
              "duration_sec": f["duration_sec"], "id": f["id"]} for f in _piece(sec, "flow")]
    sw = {"dpid": d["dpid"], "dpid_hex": d["dpid_hex"], "state": "ok", "error": "",
          "flows": flows, "active_flows": len(flows), "drop_flows": 0,
          "ports": [{k: v for k, v in p.items() if k not in ("kind", "sample")} for p in ports],
          "sample": sample,
          "coverage": {k: v for k, v in cov.items() if k not in ("kind", "dpid")}}
    own = [int(c, 16) for c in (d["threshold"].get("own_cookies") or ["0x0"])]
    collected = {"network": d["network"], "collected_at": d["at"], "state": "ok", "error": "",
                 "controllers": [{"connection": d["connection"], "kind": "ryu",
                                  "own_cookies": own, "state": "ok", "error": "",
                                  "switches": [sw]}]}
    return collected, sw


def rebuilt(case: dict) -> tuple:
    """*case*'s detection and section as the code builds them now from `collection_of`: the
    rule its detection names (a scan's fallback at the case's threshold; a flood with the
    baseline and since its threshold and measurement state; an unauthorised flow over the walk's
    flow intent) and the section builder."""
    d = case["detection"]
    collected, sw = collection_of(case)
    t, m = d["threshold"], d["measurement"]
    if d["rule"] == "scan":
        values = dict(D.THRESHOLDS, sdn_scan_fallback_pps=t["value"])
        got = D.scan(collected, values)["detections"]
    elif d["rule"] == "flood":
        pid = d["evidence"][0]
        at = D._epoch(d["at"])
        baseline = {pid: {"samples": [t["baseline_pps"]] * t["baseline_samples"], "at": at}}
        values = dict(D.THRESHOLDS, sdn_flood_factor=t["factor"],
                      sdn_flood_window_seconds=t["window_s"])
        got = D.flood(collected, baseline, values, {pid: D._epoch(m["since"])})["detections"]
    else:
        got = D.unauthorised(collected, walk_intent(), now=D._epoch(d["at"]))["detections"]
    (det,) = [g for g in got if g["subject"] == d["subject"]]
    return det, D.section(det, collected, sw)


def _rebuildable():
    return [c for c in load()["cases"] if c["key"] not in KEPT_AS_IS]


@pytest.mark.parametrize("case", _rebuildable(), ids=lambda c: c["key"])
def test_each_case_is_what_the_code_builds_from_the_evidence_the_walk_kept(case):
    det, sec = rebuilt(case)
    assert json.loads(json.dumps(det)) == case["detection"]
    assert json.loads(json.dumps(sec)) == case["section"]


#: The scan fallback's words as the walk kept them, and High packet rate's now (board S-HR,
#: PHASE8_PLAN 17.8): the one rename between a retired case and what the code builds.
RENAMED = (("the scan fallback's rate", "the high packet rate threshold"),
           ("at or above the scan fallback's ", "at or above the high packet rate threshold of "),
           ("(sdn_scan_fallback_pps); lower confidence: ",
            "(sdn_scan_fallback_pps); lower confidence, not called a scan or a flood: "),
           ("a rate alone cannot tell a scan from other heavy traffic",
            "a rate alone cannot tell a scan from a flood's first seconds or other heavy "
            "traffic"))


def as_high_rate(kept: dict, key: bool = True) -> dict:
    """A retired case's detection (or its section's detection piece) as High packet rate names
    it: the rule, its title, its key, and the words `RENAMED`; nothing else."""
    text = json.dumps(kept)
    for old, new in RENAMED:
        text = text.replace(old, new)
    out = dict(json.loads(text), rule="high_rate", title=D.TITLES["high_rate"])
    if key:
        out["key"] = D.detection_key("high_rate", kept["network"], kept["connection"],
                                     kept["dpid_hex"], [kept["subject"]["kind"],
                                                        kept["subject"]["value"]])
    return out


@pytest.mark.parametrize("case", load()["retired"], ids=lambda c: c["key"])
def test_each_retired_case_is_now_a_high_packet_rate_the_loop_never_classifies(case):
    """The walk's scan-fallback cases, rebuilt from the evidence it kept, are High packet rate
    detections (C2238): the same port, measurement, threshold value, source and evidence, the
    rule and its words renamed; a rule the loop watches and never sends to the classifier
    (`detect.WATCH_ONLY`), so the classify set no longer holds them."""
    det, sec = rebuilt(case)
    assert det["rule"] == "high_rate" and det["rule"] in D.WATCH_ONLY
    assert json.loads(json.dumps(det)) == as_high_rate(case["detection"])
    pieces = [as_high_rate(p, key=False) if p["kind"] == "detection" else p
              for p in case["section"]["pieces"]]
    assert json.loads(json.dumps(sec)) == dict(case["section"], pieces=pieces)


def test_the_injected_flow_carries_mercurys_displaced_flow_and_lifts_it():
    """C2004, C2021: the injection on s1 took the place of Mercury's rate-limit flow (cookie
    0x4d45997ed20d410a, METER:1 then port 3) with OUTPUT:NORMAL; the code names that flow
    displaced, its effect lifts, the floor high, and sends the effect with ids that were sent."""
    case = next(c for c in load()["cases"] if c["key"] == "walk-unauthorised-s1")
    d = case["detection"]
    assert [p["id"] for p in d["displaced"]] == [
        "intent:lab-ryu:0000000000000001:0x4d45997ed20d410a"]
    assert d["effect"]["class"] == "lifts"
    assert CL.severity_floor(d)["severity"] == "high"
    sent = CL.sent_evidence(case["section"])
    assert set(sent["detection"]["effect"]["evidence"]) == {d["displaced"][0]["id"]} <= sent["ids"]


def test_only_the_named_cases_are_kept_as_the_walk_kept_them():
    data = load()
    keys = {c["key"] for c in data["cases"]}
    assert set(KEPT_AS_IS) <= keys
    for c in data["cases"]:
        if c["key"] not in KEPT_AS_IS:
            continue
        assert c["edit"] == "none", c["key"]
        piece = next(p for p in c["section"]["pieces"] if p["kind"] == "detection")
        d = c["detection"]
        for k in ("rule", "words", "source", "targets", "port", "measurement", "threshold"):
            assert piece[k] == d[k], (c["key"], k)
        assert set(piece["evidence"]) <= set(d["evidence"])


def test_the_walk_set_is_its_threats_and_its_record_keeps_twelve_false_positives_and_five_normal():
    """The classify set is the walk's eight threats; the twelve fallback false positives and
    five normal cases are retired, kept verbatim as the walk's record (PHASE8_PLAN 17.8)."""
    data = load()
    assert data["network"] == "sdn_lab"
    walk = data["cases"] + data["retired"]
    assert [c["n"] for c in walk] == list(range(1, len(walk) + 1))
    threats = data["cases"]
    assert all(c["key"].startswith("walk-") and not c["key"].startswith(
        ("walk-fp-", "walk-normal-")) for c in threats)
    assert sorted(c["detection"]["rule"] for c in threats) == \
        ["flood"] * 4 + ["scan"] * 2 + ["unauthorised_flow"] * 2
    assert all(c["expect"]["threat_detected"] for c in threats)
    fps = [c for c in data["retired"] if c["key"].startswith("walk-fp-")]
    called = {re.search(r"ai-[0-9a-f]{16}", c["from"]).group(0): c for c in fps}
    assert set(called) == set(FALLBACK_CALLS) and len(fps) == 12
    for call, on_flood in FALLBACK_CALLS.items():
        c = called[call]
        d = c["detection"]
        assert (d["rule"], d["basis"], d["threshold"]["value"]) == ("scan", "rate", 100), call
        assert c["edit"] == "none"
        # The fallback names no source, so no source action can pass Mercury's check: a person
        # decides, whatever the classifier finds.
        assert c["expect"]["action_id"] == ["none"] and c["expect"]["source"] is None
        assert c["expect"]["threat_detected"] is on_flood, call
        assert c["expect"]["threat_type"] == (["flood"] if on_flood else ["none"]), call
    normal = [c for c in data["retired"] if c["key"].startswith("walk-normal-")]
    assert len(normal) == 5 and len(data["retired"]) == 12 + 5 and len(threats) == 8
    for c in normal:
        assert c["expect"]["threat_detected"] is False and c["expect"]["action_id"] == ["none"]
        assert c["detection"]["threshold"]["value"] < D.THRESHOLDS["sdn_scan_fallback_pps"]
        assert c["edit"].startswith("sdn_scan_fallback_pps set to ")


def test_no_walk_case_shares_the_evidence_of_a_recorded_or_held_out_case():
    seen = {json.dumps(c["section"], sort_keys=True)
            for name in ("recorded", "held_out") for c in load(name)["cases"]}
    mine = [json.dumps(c["section"], sort_keys=True) for c in load()["cases"]]
    assert len(set(mine)) == len(mine) and not set(mine) & seen
