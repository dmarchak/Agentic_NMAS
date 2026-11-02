"""classify_threat's recorded cases, their judge and their recorder (PHASE8_PLAN 17.1 S7, 13.6;
tests/fixtures/ai_cases/sdn_classify/; `cases.sdn_classify_misses`; scripts/nmas-sdn-cases).
No provider is called.

- **The files**: the recorded set holds every detection the Lab 8 run made (seven: two scans on
  both switches, the flood on both, the unauthorised redirect) and five normal-traffic cases
  (threat_detected false); the held-out set is twelve more, IPv6 twins among them; both on the
  task's pinned model, and every expectation borne out by its own evidence (`--check`); the
  walk's set (recorded_walk, E3) is held to the same, its own count and rebuild checked in
  tests/test_sdn_classify_walk_cases.py.
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

from modules.ai import calls, cases, profiles, triggers
from modules.sdn import closed_loop as CL
from tests.test_sdn_classify import world  # noqa: F401 - the fixture
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join("tests", "fixtures", "ai_cases", "sdn_classify")
#: The walk's set (recorded_walk, E3) is checked with the others: its pin, prompt and
#: expectations against its evidence, and an answer each case allows passing the real check
#: and the judge; what the code builds of it is tests/test_sdn_classify_walk_cases.py's.
FILES = ("recorded", "held_out", "recorded_walk")


def load(name):
    return cases.load(os.path.join(ROOT, DIR, f"{name}.json"))


# ── the unauthorised-flow cases, rebuilt from the capture the repository holds ───────────────

#: Each unauthorised-flow case's one edit of s2's captured table (tests/fixtures/sdn/lab8/
#: unauthorised_s2.json, 09:31:4x, the same table the run's 03-unauthorised/observe.json read:
#: the flow's packets, bytes and age are the case's), as its ``edit`` says it, on the
#: unauthorised flow (cookie 0xbad0), in Ryu's own shape.
UNAUTHORISED_EDITS = {
    "unauthorised-s2": lambda f: f,
    "unauthorised-v6-s2": lambda f: dict(f, match={"dl_type": 0x86DD,
                                                   "ipv6_dst": "2001:db8:8::3"}),
    "unauthorised-drop-s2": lambda f: dict(f, actions=[]),
}


def rebuilt_unauthorised(case: dict) -> tuple:
    """*case*'s detection and evidence section as the code builds them now (C2004, C2021) from
    the captured table with the case's edit: the real driver's parse, the unauthorised rule over
    the flow intent of the run (no Mercury record on the connection: the case's ``recorded``,
    0) and the section builder; the collection's time and the port sample's 2.013 s are the
    case's own (the capture kept one port read). The detection's ``key`` is the case's: the
    run computed it under its harness network, lab8, and the re-key to sdn_lab (C1948) kept it
    (the test checks it is lab8's)."""
    from modules.sdn import detect as D
    from tests.sdn_fakes import lab8, ryu_collection, ryu_switch, with_flows

    edit = UNAUTHORISED_EDITS[case["key"]]
    entries = with_flows(lab8("unauthorised_s2.json"), 2, lambda flows: [
        edit(f) if f["cookie"] == 0xBAD0 else f for f in flows])
    sw = ryu_switch(entries, 2, elapsed=2.013)
    at = case["detection"]["at"]
    collected = ryu_collection(case["detection"]["network"], at, [sw])
    got = D.unauthorised(collected, {"state": "ok", "flows": [], "withdrawn": {}},
                         now=D._epoch(at))
    (d,) = got["detections"]
    d = dict(d, key=case["detection"]["key"])
    return d, D.section(d, collected, sw)


@pytest.mark.parametrize("name,n,effect", [("recorded", 7, "diverts"),
                                           ("held_out", 6, "diverts"),
                                           ("held_out", 7, "drops")])
def test_each_unauthorised_case_is_what_the_code_builds_from_the_held_capture(name, n, effect):
    """C2004, C2021: the three unauthorised-flow cases carry the effect and any displaced
    Mercury flow because they are rebuilt through the code, never typed: each case's detection
    and section equal what the rule and the section builder make from the captured table with
    the case's one edit (its expectations untouched)."""
    from modules.sdn import detect as D

    case = next(c for c in load(name)["cases"] if c["n"] == n)
    d = case["detection"]
    assert d["key"] == D.detection_key(d["rule"], "lab8", d["connection"], d["dpid_hex"],
                                       [d["subject"]["kind"], d["subject"]["value"]])
    det, sec = rebuilt_unauthorised(case)
    assert json.loads(json.dumps(det)) == case["detection"]
    assert json.loads(json.dumps(sec)) == case["section"]
    assert case["detection"]["effect"]["class"] == effect
    assert case["detection"]["displaced"] == []          # no Mercury record on the connection
    sent = CL.sent_evidence(case["section"])
    assert sent["detection"]["effect"]["class"] == effect
    assert set(sent["detection"]["effect"]["evidence"]) <= sent["ids"]


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
    # The cases are the adopted prompt's (C1988: v3, adopted 2026-10-27).
    assert data["prompt"] == "{}.v{}".format(*CL.CLASSIFY_PROMPT) == "sdn_classify.v3"
    assert data["task"] == "sdn_classify"
    assert _script().check(ROOT, os.path.join(DIR, f"{name}.json")) == []


BLIND = os.path.join("tests", "fixtures", "blind_sets", "sdn_classify")


def test_the_blind_set_is_on_the_pin_its_key_locked_and_its_expectations_hold():
    """The blind held-out set (C1939), built 2026-11-02 by a fresh context that never saw the
    prompt, from the locked key and Mercury's kept packs: the key's bytes are the ones the
    operator confirmed (any edit would unlock it), the cases are on the pin and the adopted
    prompt, every expectation (each `any_of` alternative too) is borne out by its own
    evidence, and each case is one of the draw's scenarios."""
    import hashlib
    with open(os.path.join(ROOT, BLIND, "blind_answer_key.md"), "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() == \
            "11a6ccee4457525106f3fd72fd209021c618faf5f06f9519f496bd0d1c5a851a"
    data = cases.load(os.path.join(ROOT, BLIND, "blind_cases.json"))
    assert data["model"] == profiles.TASKS["sdn_classify"]["model"]
    assert data["prompt"] == "{}.v{}".format(*CL.CLASSIFY_PROMPT)
    assert data["task"] == "sdn_classify" and data["network"] == "sdn_lab"
    assert _script().check(ROOT, os.path.join(BLIND, "blind_cases.json")) == []
    with open(os.path.join(ROOT, BLIND, "blind_draw.json"), encoding="utf-8") as fh:
        drawn = json.dumps(json.load(fh))
    scenarios = {c["key"].split("-")[1] for c in data["cases"]}
    assert len(data["cases"]) >= 37 and len(scenarios) >= 18
    assert all(f'"{s}"' in drawn for s in scenarios), scenarios


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
    wrong["action"] = "remove_flow"           # no scan case allows it (C1988: both stopping ones)
    assert cases.sdn_classify_misses(scan["expect"], wrong) == [
        "action remove_flow, expected one of ['rate_limit_source', 'drop_source']"]
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
            # An action no scan case allows (C1988: a scan's case allows the rate limit too).
            got = dict(got, action="remove_flow")
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


def test_a_recording_asks_with_the_prompt_named_and_says_which(monkeypatch, tmp_path):
    """`--prompt N` (C1988: a version measured before it is adopted): every ask goes through
    `classify_pack` with that version, and the report names it; without it, the adopted
    `CLASSIFY_PROMPT`."""
    mod = _script()
    data = load("recorded")
    by_n = {c["n"]: c for c in data["cases"]}
    prompts = []

    def classify(network, detection, pack, *, actor, trigger, **kw):
        prompts.append(kw.get("prompt"))
        return _good(by_n[int(pack["id"].split("-")[1])])
    monkeypatch.setattr(CL, "classify_pack", classify)
    out = tmp_path / "v3.json"
    assert mod.record(ROOT, "default", "evaluation:v3", str(out),
                      os.path.join(DIR, "recorded.json"), 1, "", ("sdn_classify", 3)) == 0
    assert set(prompts) == {("sdn_classify", 3)} and len(prompts) == 12
    assert json.loads(out.read_text())["prompt"] == "sdn_classify.v3"
    prompts.clear()
    out = tmp_path / "adopted.json"
    assert mod.record(ROOT, "default", "evaluation:v1", str(out),
                      os.path.join(DIR, "recorded.json"), 1) == 0
    assert set(prompts) == {tuple(CL.CLASSIFY_PROMPT)}
    assert json.loads(out.read_text())["prompt"] == "{}.v{}".format(*CL.CLASSIFY_PROMPT)


def test_a_scan_case_allows_either_action_that_stops_a_scan():
    """C1988 (the operator's order: no rule-to-action mapping): a scan case with a threat
    allows rate_limit_source or drop_source, as a flood case does; the network's policy,
    through Mercury's check, decides which may pass."""
    for name in FILES:
        scans = [c for c in load(name)["cases"] if c["detection"]["rule"] == "scan"
                 and c["expect"]["action_id"] != [CL.NO_ACTION]]
        assert scans, name
        assert all(c["expect"]["action_id"] == ["rate_limit_source", "drop_source"]
                   for c in scans), name


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


# ── a key cell listing whole alternatives (`any_of`) ───────────────────────────────────────────

def _answered(threat, kind, action, refs, severity="low"):
    return {"ok": True, "action": action, "params": {},
            "classification": {"threat_detected": threat, "threat_type": kind,
                               "severity": severity, "evidence_refs": refs,
                               "parameters": {}}}


def _either():
    """A case whose key allows a threat answered by a rate limit, or no threat at all."""
    scan = load("recorded")["cases"][0]["expect"]
    refs = scan["cites_any"]
    return {"any_of": [
        {"threat_detected": True, "threat_type": ["port_scan"], "severity": ["low", "medium"],
         "action_id": ["rate_limit_source"], "cites_any": refs},
        {"threat_detected": False, "threat_type": ["none"], "severity": ["low"],
         "action_id": [CL.NO_ACTION], "cites_any": refs}]}, refs


def test_an_answer_either_alternative_allows_passes():
    expect, refs = _either()
    assert cases.sdn_classify_misses(
        expect, _answered(True, "port_scan", "rate_limit_source", refs[:1])) == []
    assert cases.sdn_classify_misses(
        expect, _answered(False, "none", CL.NO_ACTION, refs[:1])) == []


def test_a_mix_of_two_alternatives_misses_naming_the_nearer():
    """Judged whole, never field by field: no threat with the first alternative's action is
    neither answer the key allows."""
    expect, refs = _either()
    got = cases.sdn_classify_misses(
        expect, _answered(False, "none", "rate_limit_source", refs[:1]))
    assert got == [f"action rate_limit_source, expected one of ['{CL.NO_ACTION}']"], got


def test_the_checker_checks_each_alternative_against_the_evidence():
    mod = _script()
    case = load("recorded")["cases"][0]
    expect, refs = _either()
    sent = CL.sent_evidence(case["section"])
    assert [p for e in expect["any_of"] for p in mod._stale(case, e, sent)] == []
    expect["any_of"][1]["cites_any"] = ["flow:not-sent"]
    assert [p for e in expect["any_of"] for p in mod._stale(case, e, sent)] == [
        f"case {case['n']}: cites_any holds ['flow:not-sent'], not ids the evidence sends"]


def test_the_check_reads_every_alternative_of_a_case_file(tmp_path):
    """`check` (the recorder's first step and `--check`) reads each `any_of` alternative, so a
    stale second alternative stops a recording before anything is asked."""
    data = load("recorded")
    expect, _refs = _either()
    expect["any_of"][1]["cites_any"] = ["flow:not-sent"]
    data["cases"] = [dict(data["cases"][0], expect=expect)]
    path = tmp_path / "either.json"
    path.write_text(json.dumps(data))
    assert _script().check(ROOT, str(path)) == [
        f"case {data['cases'][0]['n']}: cites_any holds ['flow:not-sent'], not ids the evidence "
        "sends"]


# ── the batch path (`closed_loop.classify_packs_batch`, `--batch`) ─────────────────────────────

def _fake_batches(by_cid):
    """The provider's batch calls, faked (tests/test_ai_batch.py's): *by_cid(custom_id)* is the
    answer each request gets, as JSON text."""
    from tests.test_ai_batch import FakeBatches, _message
    return FakeBatches(answer=lambda cid, params: {
        "type": "succeeded", "message": _message(json.dumps(by_cid(cid)))}, states=("ended",))


def _case_of(cid):
    return int(cid.split("-")[0][1:])


def test_a_batched_round_sends_what_a_call_sends_and_checks_each_answer_the_same(world):  # noqa: F811
    """Each batched request's messages are the live call's for the same case, byte for byte
    (one request path, `prepare_classify`), and each answer goes through the same check and
    judge (`checked_answer`): an answer a case allows passes; one the check refuses (it cites
    nothing) is refused in the same words."""
    data = load("recorded")
    by_n = {c["n"]: c for c in data["cases"]}
    live = {}
    for c in data["cases"]:
        world.answer = allowed_answer(c)
        live[c["n"]] = (_classify(world, c), world.sent[-1])
    refuse = data["cases"][0]["n"]

    def answer(cid):
        n = _case_of(cid)
        a = allowed_answer(by_n[n])
        return dict(a, evidence_refs=[]) if n == refuse and cid.endswith("-r1") else a
    fake = _fake_batches(answer)
    actor = "evaluation:sdn-batch-test"
    items = [{"n": c["n"], "detection": c["detection"], "pack": _script().pack_of(c, "Default")}
             for c in data["cases"]]
    got = CL.classify_packs_batch("Default", items, 2, actor=actor,
                                  trigger=triggers.evaluation(actor), intact=False,
                                  provider=fake, sleep=lambda s: None)
    assert got["ok"] and got["batch_id"] == "msgbatch_0test", got["detail"]
    (sent,) = fake.created
    assert len(sent) == 2 * len(data["cases"])
    for r in sent:
        assert r["params"]["messages"] == live[_case_of(r["custom_id"])][1]["messages"]
    for cid, one in got["results"].items():
        n, case = _case_of(cid), by_n[_case_of(cid)]
        if n == refuse and one["run"] == 1:
            assert one["error"] == "couldnt_classify" and "cites no evidence id" in one["why"]
            assert cases.sdn_classify_misses(case["expect"], one)
            continue
        assert one["ok"] and one["action"] == live[n][0]["action"], (cid, one)
        assert cases.sdn_classify_misses(case["expect"], one) == [], cid


def test_a_case_refused_before_any_call_is_its_result_in_every_run_and_not_sent(world):  # noqa: F811
    """A pack whose hash does not match (*intact*, a stored pack changed since it was kept) is
    refused by the request path before the batch is built: its result in each run, never a
    request."""
    c = load("recorded")["cases"][0]
    fake = _fake_batches(lambda cid: allowed_answer(c))
    actor = "evaluation:sdn-batch-test"
    pack = dict(_script().pack_of(c, "Default"), hash="0" * 64)
    got = CL.classify_packs_batch("Default", [{"n": 1, "detection": c["detection"],
                                               "pack": pack}], 3, actor=actor,
                                  trigger=triggers.evaluation(actor), provider=fake)
    assert fake.created == [] and got["error"] == "nothing_sent"
    assert [r["error"] for r in got["results"].values()] == ["changed"] * 3


def test_the_batch_recorder_reports_as_the_recorder_does(world, monkeypatch, tmp_path):  # noqa: F811
    """`--batch`: one batch for the whole round, recorded as `evaluation:<run>`, the same
    report (reliability apart from consistency), the batch's id kept and its latency said not
    measured; a stale expectation stops it before anything is sent (5)."""
    from modules.ai import gateway
    mod = _script()
    data = load("recorded")
    by_n = {c["n"]: c for c in data["cases"]}

    def answer(cid):
        a = allowed_answer(by_n[_case_of(cid)])
        return dict(a, action_id="remove_flow") if cid.startswith("c1-") and \
            cid.endswith("-r1") else a
    fake = _fake_batches(answer)
    monkeypatch.setattr(gateway, "_Batches", lambda: fake)
    out = tmp_path / "batch.json"
    status = mod.record_batch(ROOT, "Default", "evaluation:batch-run", str(out),
                              os.path.join(DIR, "recorded.json"), 2)
    rec = json.loads(out.read_text())
    assert status == 0, rec
    assert len(fake.created) == 1 and len(fake.created[0]) == 2 * len(data["cases"])
    assert rec["batch_id"] == "msgbatch_0test" and rec["latency"] == "not measured: one batch"
    assert rec["actor"] == "evaluation:batch-run" and rec["runs"] == 2
    assert rec["reliability"] == {"reliable": len(data["cases"]) - 1,
                                  "cases": len(data["cases"]), "runs": 2 * len(data["cases"])}
    assert rec["report"][0]["passed"] == 1 and rec["report"][0]["reliable"] is False
    rows = calls.read()["rows"]
    assert {r["actor"] for r in rows} == {"evaluation:batch-run"} and \
        all(r.get("batch") for r in rows)
    data["cases"][0]["expect"]["source"] = "192.0.2.2"
    stale = tmp_path / "stale.json"
    stale.write_text(json.dumps(data))
    assert mod.record_batch(ROOT, "Default", "evaluation:b", str(tmp_path / "b.json"),
                            str(stale), 2) == 5
    assert len(fake.created) == 1
