"""Feature 7's recorded cases and their judge (PHASE8_PLAN 13.6, 15.16; the overnight order of
2026-10-26: 20 recorded cases and a held-out set of 10 written before the first measurement;
tests/fixtures/ai_cases/intent_patch/).

- The case files: 20 and 10, on the task's pinned model and the current prompt, each case a
  device, a sentence and the outcomes it allows; every expected operation one the patch takes,
  in its own shape; ambiguity, out-of-scope and injection cases among them.
- The judge (`cases.intent_misses`): an answer passes on exactly its operations (order aside,
  interfaces by their written forms, areas by number); an extra, a missing or a changed
  operation fails, naming both; an outcome the case does not allow fails, naming it.
- The recorder (scripts/nmas-intent-cases), with `intent_words.change` planted: a case per
  run, its passes, consistency, cost and latency reported; a Mercury refusal stops the run; a
  call stopped at max_tokens voids it; `--out` inside the checkout is refused.
"""
import importlib.machinery
import importlib.util
import json
import os

import pytest

from modules.ai import cases, intent_words, profiles

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "tests", "fixtures", "ai_cases", "intent_patch")
RECORDED = cases.load(os.path.join(DIR, "recorded.json"))
HELD_OUT = cases.load(os.path.join(DIR, "held_out.json"))


def _op(op, **fields):
    base = {"op": op, "interface": "", "description": "", "vlan": 0, "vlan_name": "",
            "process": 0, "prefix": "", "area": ""}
    base.update(fields)
    return base


def _got(*ops, ok=True, error=""):
    return {"ok": ok, "error": error, "choices": {
        "outcome": "answer", "question": "", "why_not": "",
        "patches": [{"hostname": "s1", "operations": list(ops)}]}}


# ── the case files ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("data,count", [(RECORDED, 20), (HELD_OUT, 10)],
                         ids=["recorded", "held-out"])
def test_each_file_holds_its_cases_on_the_pin_and_the_prompt(data, count):
    assert len(data["cases"]) == count
    assert [c["n"] for c in data["cases"]] == list(range(1, count + 1))
    assert data["model"] == profiles.TASKS[intent_words.FEATURE]["model"]
    assert data["prompt"] == f"{intent_words.PROMPT[0]}.v{intent_words.PROMPT[1]}"
    allowed = {"answer", "ask", "refuse", "refused_after", "mercury"}
    for c in data["cases"]:
        assert c["device"] and c["sentence"], c["n"]
        assert set(c["expect"]["outcome"]) <= allowed, c["n"]
        for o in c["expect"].get("ops", ()):
            op = intent_words.Op(o["op"])
            used = {"name" if f == "vlan_name" else f for f in intent_words.FIELDS[op]}
            assert set(o) - {"op"} == used, (c["n"], o)


def test_the_recorded_set_holds_each_kind_of_case():
    """The order's constrained scope: descriptions and shutdown, VLANs, OSPF networks; and
    ambiguous to ask, out of scope to refuse, an injection."""
    ops = {o["op"] for c in RECORDED["cases"] for o in c["expect"].get("ops", ())}
    assert ops == {m.value for m in intent_words.Op}, "every operation exercised"
    kinds = [c["expect"]["outcome"] for c in RECORDED["cases"]]
    assert sum(k == ["ask"] for k in kinds) >= 3 and sum("refuse" in k for k in kinds) >= 3
    assert any("ignore previous instructions" in c["sentence"] for c in RECORDED["cases"])


def test_no_case_file_is_recorded_before_its_first_measurement():
    """Written before the first measurement: neither file says it was recorded."""
    for data in (RECORDED, HELD_OUT):
        assert "not yet recorded" in data["about"].lower()
        assert all("recorded" not in c for c in data["cases"])


# ── the judge ────────────────────────────────────────────────────────────────

def test_an_answer_with_exactly_its_operations_passes_in_any_order():
    expect = RECORDED["cases"][10]["expect"]                    # case 11: two operations
    got = _got(_op("shutdown", interface="Gi0/3"),
               _op("set_description", interface="GigabitEthernet0/2", description="uplink to r1"))
    assert cases.intent_misses(expect, got) == []


def test_an_area_is_compared_by_number():
    expect = {"outcome": ["answer"], "ops": [
        {"op": "add_ospf_network", "process": 1, "prefix": "192.0.2.0/24", "area": "0"}]}
    got = _got(_op("add_ospf_network", process=1, prefix="192.0.2.0/24", area="0.0.0.0"))
    assert cases.intent_misses(expect, got) == []


@pytest.mark.parametrize("ops,words", [
    ([_op("set_description", interface="GigabitEthernet0/1", description="spare port, desk 4"),
      _op("shutdown", interface="GigabitEthernet0/1")], "'op': 'shutdown'"),
    ([], "operations [], expected"),
    ([_op("set_description", interface="GigabitEthernet0/1", description="spare port")],
     "'description': 'spare port'"),
], ids=["an-extra-operation", "none", "a-changed-description"])
def test_an_answer_with_other_operations_fails_naming_them(ops, words):
    got = cases.intent_misses(RECORDED["cases"][0]["expect"], _got(*ops))
    assert len(got) == 1 and got[0].startswith("operations ") and words in got[0], got


@pytest.mark.parametrize("got,outcome", [
    ({"ok": False, "error": "ask", "detail": "one question first: which?"}, "ask"),
    ({"ok": False, "error": "unanswerable", "detail": "no operation sets that"}, "refuse"),
    ({"ok": False, "error": "couldnt_change", "detail": "outside the request"}, "refused_after"),
    ({"ok": False, "error": "nothing_named", "detail": "names nothing"}, "mercury"),
], ids=["ask", "refuse", "refused-after", "mercury"])
def test_an_outcome_the_case_does_not_allow_fails_naming_it(got, outcome):
    assert cases.intent_outcome(got) == outcome
    misses = cases.intent_misses(RECORDED["cases"][0]["expect"], got)
    assert misses and misses[0].startswith(f"outcome {outcome}, expected one of ['answer']")


def test_ask_and_refuse_pass_on_the_outcome():
    ask = RECORDED["cases"][13]["expect"]                       # case 14
    assert cases.intent_misses(ask, {"ok": False, "error": "ask"}) == []
    ipv6 = RECORDED["cases"][18]["expect"]                      # case 19
    assert cases.intent_misses(ipv6, {"ok": False, "error": "couldnt_change"}) == []
    assert cases.intent_misses(ipv6, {"ok": False, "error": "unanswerable"}) == []


def test_a_case_naming_what_an_outcome_says_misses_the_same_outcome_for_another_reason():
    """C1770's corrected premises: "bring Gi0/1 back up" on an interface already up passes as
    Mercury's "changes no device", never as a refusal of something else."""
    up = RECORDED["cases"][2]["expect"]                         # case 3
    assert cases.intent_misses(up, {"ok": False, "error": "couldnt_change", "detail": (
        "the answer changes no device; nothing is previewed")}) == []
    misses = cases.intent_misses(up, {"ok": False, "error": "couldnt_change", "detail": (
        "s1's operation 0 (shutdown) changes the interface 'GigabitEthernet0/2', which the "
        "request does not name; nothing is previewed")})
    assert misses and "expected it to say 'the answer changes no device'" in misses[0]
    assert cases.intent_misses(up, _got(_op("no_shutdown", interface="GigabitEthernet0/1"))) \
        == []


# ── the recorder ─────────────────────────────────────────────────────────────

def _script():
    loader = importlib.machinery.SourceFileLoader(
        "nmas_intent_cases", os.path.join(ROOT, "scripts", "nmas-intent-cases"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def _planted(monkeypatch, answers):
    """`intent_words.change` answering from *answers* (sentence -> result), counting calls."""
    asked = []

    def change(list_name, sentence, *, actor, devices=None, **_k):
        asked.append((sentence, tuple(devices or ())))
        return dict(answers(sentence), cost_usd=0.01, call_id="ai-0000000000000001")
    monkeypatch.setattr(intent_words, "change", change)
    # The recording's first step checks each expectation against the committed intent; these
    # tests have none, so it is stood in as fresh (its own tests: test_ai_intent_change.py).
    monkeypatch.setattr(intent_words, "stale", lambda list_name, case: [])
    return asked


def test_the_recorder_reports_passes_consistency_cost_and_latency(monkeypatch, tmp_path):
    mod = _script()
    by_sentence = {c["sentence"]: c for c in RECORDED["cases"]}

    def answer(sentence):
        exp = by_sentence[sentence]["expect"]
        if exp["outcome"][0] != "answer":
            first = exp["outcome"][0]
            return {"ok": False, "error": {"ask": "ask", "refuse": "unanswerable",
                                           "refused_after": "intent"}[first],
                    "detail": (exp.get("said") or {}).get(first) or "planted"}
        ops = []
        for o in exp["ops"]:
            ops.append(_op(o["op"], **{("vlan_name" if k == "name" else k): v
                                      for k, v in o.items() if k != "op"}))
        return _got(*ops)
    asked = _planted(monkeypatch, answer)
    out = tmp_path / "rec.json"
    assert mod.record(ROOT, "default", "operator@example.com", str(out),
                      os.path.join("tests", "fixtures", "ai_cases", "intent_patch",
                                   "recorded.json"), 2) == 0
    rec = json.loads(out.read_text())
    assert len(asked) == 40 and all(len(d) == 1 for _s, d in asked), "each case on its tab"
    assert [s["passed"] for s in rec["report"]] == [2] * 20
    assert all(s["consistent"] for s in rec["report"]) and rec["spent_usd"] == 0.4


def test_a_mercury_refusal_stops_and_max_tokens_voids(monkeypatch, tmp_path):
    mod = _script()
    path = os.path.join("tests", "fixtures", "ai_cases", "intent_patch", "recorded.json")
    _planted(monkeypatch, lambda s: {"ok": False, "error": "over_cap", "detail": "the day cap"})
    assert mod.record(ROOT, "default", "a", str(tmp_path / "a.json"), path, 1) == 3
    _planted(monkeypatch, lambda s: {"ok": False, "error": "max_tokens", "detail": "cut"})
    assert mod.record(ROOT, "default", "a", str(tmp_path / "b.json"), path, 1) == 4
    assert mod.record(ROOT, "default", "a", os.path.join(ROOT, "out.json"), path, 1) == 2
    assert not os.path.exists(os.path.join(ROOT, "out.json"))


def test_a_stale_expectation_stops_the_recording_before_any_call(monkeypatch, tmp_path, capsys):
    """The check runs first: one stale case and nothing is asked, nothing written (exit 5);
    `--check` alone says the same with no call."""
    mod = _script()
    path = os.path.join("tests", "fixtures", "ai_cases", "intent_patch", "recorded.json")
    asked = _planted(monkeypatch, lambda s: {"ok": True})
    monkeypatch.setattr(intent_words, "stale", lambda list_name, case: (
        [f"case {case['n']} (s1): the expected change is already in the committed intent"]
        if case["n"] == 3 else []))
    out = tmp_path / "a.json"
    assert mod.record(ROOT, "default", "a", str(out), path, 5) == 5
    assert asked == [] and not out.exists()
    assert "case 3 (s1): the expected change is already" in capsys.readouterr().err
    assert mod.main(["--check", "--list", "default", "--cases", path]) == 5
    assert asked == [] and "1 stale expectation(s)" in capsys.readouterr().out
