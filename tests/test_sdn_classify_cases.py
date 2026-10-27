"""classify_threat's recorded cases, their judge and their recorder (PHASE8_PLAN 17.1 S7, 13.6;
tests/fixtures/ai_cases/sdn_classify/; `cases.sdn_classify_misses`; scripts/nmas-sdn-cases).
No provider is called.

- **The files**: the recorded set holds every detection the Lab 8 run made (seven: two scans on
  both switches, the flood on both, the unauthorised redirect) and five normal-traffic cases
  (threat_detected false); the held-out set is twelve more, IPv6 twins among them; both on the
  task's pinned model, and every expectation borne out by its own evidence (`--check`).
- **The judge**: an answer each case allows, put through the real check, passes; a different
  action, source, flow, a citation the detection does not rest on, or an answer the check
  refused, each misses, named.
- **The recorder**: recorded as `evaluation:<run>`, never a person; reliability per case (every
  run correct) and consistency (compared fields) reported apart; a Mercury refusal stops (3),
  max_tokens voids (4), `--out` in the checkout is refused (2), a stale expectation stops before
  anything is asked (5).
"""
import importlib.machinery
import importlib.util
import ipaddress
import json
import os

import pytest

from modules.ai import cases, profiles, triggers
from modules.sdn import closed_loop as CL
from tests.test_sdn_classify import world  # noqa: F401 - the fixture
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join("tests", "fixtures", "ai_cases", "sdn_classify")
FILES = ("recorded", "held_out")


def load(name):
    return cases.load(os.path.join(ROOT, DIR, f"{name}.json"))


def _script():
    loader = importlib.machinery.SourceFileLoader(
        "nmas_sdn_cases", os.path.join(ROOT, "scripts", "nmas-sdn-cases"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


# ── the files ─────────────────────────────────────────────────────────────────────────────────

def test_the_recorded_set_is_every_lab_8_detection_and_five_normal_cases():
    data = load("recorded")
    rules = sorted(c["detection"]["rule"] for c in data["cases"] if c["expect"]["threat_detected"])
    assert rules == ["flood"] * 2 + ["scan"] * 4 + ["unauthorised_flow"], rules
    normal = [c for c in data["cases"] if not c["expect"]["threat_detected"]]
    assert len(normal) == 5 and all(c["expect"]["action_id"] == ["none"] for c in normal)
    assert [c["n"] for c in data["cases"]] == list(range(1, 13))


def test_the_held_out_set_is_its_own_twelve_with_ipv6_twins():
    held, rec = load("held_out"), load("recorded")
    assert len(held["cases"]) == 12
    # A detection's key names its subject (a port, a flow, a source), which two cases may
    # share; their evidence is what differs.
    seen = {json.dumps(c["section"], sort_keys=True) for c in rec["cases"]}
    assert not {json.dumps(c["section"], sort_keys=True) for c in held["cases"]} & seen, \
        "no recorded case's evidence"
    v6 = [c for c in held["cases"]
          if any(":" in str(a) for a in [c["detection"].get("source")]
                 + list(c["detection"].get("targets") or []))]
    assert len(v6) >= 4 and {c["detection"]["rule"] for c in v6} == {
        "scan", "flood", "unauthorised_flow"}


@pytest.mark.parametrize("name", FILES)
def test_each_file_is_on_the_pin_and_its_expectations_hold_against_its_evidence(name):
    data = load(name)
    assert data["model"] == profiles.TASKS["sdn_classify"]["model"]
    assert data["prompt"] == "sdn_classify.v1" and data["task"] == "sdn_classify"
    assert _script().check(ROOT, os.path.join(DIR, f"{name}.json")) == []


def test_a_stale_expectation_is_found(tmp_path):
    """The control: a source the detection did not see, a cited id the evidence did not send,
    and a flow that is not the detection's own, each found by the check."""
    data = load("recorded")
    data["cases"][0]["expect"]["source"] = "192.0.2.2"
    data["cases"][4]["expect"]["cites_any"] = ["port:lab:0000000000000001:9"]
    data["cases"][6]["expect"]["flow"] = "flow:lab:0000000000000002:t0:p1:0000000000"
    path = tmp_path / "stale.json"
    path.write_text(json.dumps(data))
    found = _script().check(ROOT, str(path))
    assert [p.split(":")[0] for p in found] == ["case 1", "case 5", "case 7"], found


# ── the judge ─────────────────────────────────────────────────────────────────────────────────

def allowed_answer(c: dict) -> dict:
    """An answer the case allows: its first allowed value of each field, its expected source or
    flow, one id it may cite."""
    e = c["expect"]
    source = ipaddress.ip_address(e["source"]).compressed if e.get("source") else ""
    return {"reasoning": "planted", "threat_detected": e["threat_detected"],
            "threat_type": e["threat_type"][0], "severity": e["severity"][0],
            "affected_devices": [source] if source else [],
            "recommended_action": "planted", "action_id": e["action_id"][0],
            "parameters": {"source": source, "flow": e.get("flow") or "", "hard_timeout": 0,
                           "rate": 0, "unit": "kbps", "burst": 0},
            "evidence_refs": [e["cites_any"][0]]}


def _classify(world, c):  # noqa: F811 - the fixture, used
    actor = "evaluation:sdn-cases-test"
    return CL.classify_pack("Default", c["detection"], _script().pack_of(c, "Default"),
                            actor=actor, trigger=triggers.evaluation(actor), send=world.send,
                            intact=False)


@pytest.mark.parametrize("name", FILES)
def test_an_answer_each_case_allows_passes_the_real_check_and_the_judge(world, name):  # noqa: F811
    for c in load(name)["cases"]:
        world.answer = allowed_answer(c)
        got = _classify(world, c)
        assert got["ok"], (c["n"], got)
        assert cases.sdn_classify_misses(c["expect"], got) == [], c["n"]


def test_the_judge_names_each_departure(world):  # noqa: F811
    data = load("recorded")
    scan, redirect = data["cases"][0], data["cases"][6]
    world.answer = allowed_answer(scan)
    good = _classify(world, scan)
    wrong = json.loads(json.dumps(good, default=str))
    wrong["action"] = "rate_limit_source"
    assert cases.sdn_classify_misses(scan["expect"], wrong) == [
        "action rate_limit_source, expected one of ['drop_source']"]
    wrong = dict(good, params={"source": "192.0.2.3"})
    assert cases.sdn_classify_misses(scan["expect"], wrong) == [
        "source '192.0.2.3', expected 192.0.2.1"]
    other = [i for i in CL.sent_evidence(scan["section"])["ids"]
             if i not in scan["expect"]["cites_any"]]
    wrong = dict(good, classification=dict(good["classification"], evidence_refs=other[:1]))
    assert "none of the evidence the detection rests on" in \
        cases.sdn_classify_misses(scan["expect"], wrong)[0]
    wrong = dict(good, classification=dict(good["classification"], threat_detected=False,
                                           threat_type="none"))
    assert cases.sdn_classify_misses(scan["expect"], wrong) == [
        "threat_detected False, expected True",
        "threat_type none, expected one of ['port_scan']"]
    world.answer = allowed_answer(redirect)
    good = _classify(world, redirect)
    wrong = dict(good, classification=dict(good["classification"], parameters=dict(
        good["classification"]["parameters"], flow="flow:x")))
    assert cases.sdn_classify_misses(redirect["expect"], wrong) == [
        f"flow 'flow:x', expected {redirect['expect']['flow']}"]
    world.answer = dict(allowed_answer(scan), evidence_refs=[])
    refused = _classify(world, scan)
    assert cases.sdn_classify_misses(scan["expect"], refused)[0].startswith(
        "outcome refused by the check (couldn't classify: it cites no evidence id")
    assert cases.sdn_classify_misses(scan["expect"], {"ok": False, "error": "over_cap"}) == [
        "outcome not the model's: over_cap"]


# ── the recorder ─────────────────────────────────────────────────────────────────────────────

def _planted(monkeypatch, answer):
    """`classify_pack` planted: *answer(case number, ask number)* is its result (a case is told
    by its pack's id, ``case-<n>``: two cases may share a detection key); each ask kept."""
    asked = []

    def classify(network, detection, pack, *, actor, trigger, **kw):
        asked.append((pack["id"], actor, trigger))
        return answer(int(pack["id"].split("-")[1]), len(asked))
    monkeypatch.setattr(CL, "classify_pack", classify)
    return asked


def _good(c):
    e = c["expect"]
    action = e["action_id"][0]
    source = ipaddress.ip_address(e["source"]).compressed if e.get("source") else ""
    return {"ok": True, "action": action, "params": {"source": source} if source else {},
            "cost_usd": 0.001, "call_id": "c",
            "classification": {"threat_detected": e["threat_detected"],
                               "threat_type": e["threat_type"][0],
                               "severity": e["severity"][0], "evidence_refs": e["cites_any"][:1],
                               "parameters": {"flow": e.get("flow") or ""}}}


def test_the_recorder_reports_reliability_apart_from_consistency(monkeypatch, tmp_path):
    mod = _script()
    data = load("recorded")
    by_n = {c["n"]: c for c in data["cases"]}

    def answer(n, asked):
        got = _good(by_n[n])
        if n == 1 and asked > 12:                         # case 1 misses on run 2
            got = dict(got, action="rate_limit_source")
        return got
    asked = _planted(monkeypatch, answer)
    out = tmp_path / "rec.json"
    assert mod.record(ROOT, "default", "evaluation:test-run", str(out),
                      os.path.join(DIR, "recorded.json"), 2) == 0
    rec = json.loads(out.read_text())
    assert len(asked) == 24 and {a for _k, a, _t in asked} == {"evaluation:test-run"}
    assert {t["kind"] for _k, _a, t in asked} == {"evaluation"}
    assert rec["reliability"] == {"reliable": 11, "cases": 12, "runs": 24}
    assert rec["consistency"] == {"consistent": 11, "cases": 12}
    assert rec["report"][0]["passed"] == 1 and rec["report"][0]["reliable"] is False
    assert rec["usd_per_call"] == 0.001 and rec["actor"] == "evaluation:test-run"


def test_a_recording_is_never_a_person(monkeypatch, tmp_path, capsys):
    mod = _script()
    path = os.path.join(DIR, "recorded.json")
    asked = _planted(monkeypatch, lambda k, n: {"ok": True})
    for actor in ("operator@example.com", "alex", "evaluation:"):
        assert mod.record(ROOT, "default", actor, str(tmp_path / "x.json"), path, 1) == 2
    assert asked == [] and "is not evaluation:<run id>" in capsys.readouterr().err


def test_a_mercury_refusal_stops_max_tokens_voids_and_the_checkout_is_never_written(
        monkeypatch, tmp_path):
    mod = _script()
    path = os.path.join(DIR, "recorded.json")
    _planted(monkeypatch, lambda k, n: {"ok": False, "error": "over_cap", "detail": "the cap"})
    assert mod.record(ROOT, "default", "evaluation:a", str(tmp_path / "a.json"), path, 1) == 3
    _planted(monkeypatch, lambda k, n: {"ok": False, "error": "max_tokens", "detail": "cut"})
    assert mod.record(ROOT, "default", "evaluation:a", str(tmp_path / "b.json"), path, 1) == 4
    assert mod.record(ROOT, "default", "evaluation:a", os.path.join(ROOT, "out.json"), path,
                      1) == 2
    assert not os.path.exists(os.path.join(ROOT, "out.json"))


def test_a_stale_expectation_stops_the_recording_before_any_call(monkeypatch, tmp_path):
    mod = _script()
    data = load("recorded")
    data["cases"][0]["expect"]["source"] = "192.0.2.2"
    path = tmp_path / "stale.json"
    path.write_text(json.dumps(data))
    asked = _planted(monkeypatch, lambda k, n: {"ok": True})
    out = tmp_path / "a.json"
    assert mod.record(ROOT, "default", "evaluation:a", str(out), str(path), 5) == 5
    assert asked == [] and not out.exists()
