"""Ask in words' recorded cases (PHASE8_PLAN 13.6; the operator's 20 questions, 2026-10-25;
tests/fixtures/ai_cases/nl_query/metrics.json; modules/ai/cases.py).

- The set: 20 cases, numbered, on the task's pinned model; the operator's ASK cases expect a
  question back, the device that does not exist and the injection a question or a refusal.
- Filled from the real catalogue: every metric a case expects is one the lab's Prometheus
  held (the 2026-10-15 capture), every operation it names parses as the builder's, every role
  is the network's, every device is the network's, and one the capture predates says so in
  its flag.
- The judge (`cases.misses`), on planted results: a right answer passes, a wrong device, an
  answer where a question was expected, and the wrong day for "yesterday" each miss.
- Recorded cases replay: each case recorded on the host (scripts/nmas-nl-cases --record) is
  judged again from its recorded choices, the same judge.
"""
import json
import os
import time

from modules import history_promq as pq
from modules.ai import cases, profiles
from tests.test_ai_nl_query import world, web  # noqa: F401 (the fixtures)
from tests.test_history_ask_metrics import web as _web  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_DIR = os.path.join(ROOT, "tests", "fixtures", "ai_cases")
FILE = os.path.join(CASES_DIR, "nl_query", "metrics.json")
PROM = os.path.join(ROOT, "tests", "fixtures", "prometheus")
#: The network's devices and roles as its inventory held them on 2026-10-25 (the heartbeat
#: check's read of the twelve, C1682), and the devices the 2026-10-15 capture's labels hold.
NETWORK = {"r1", "r2", "r3", "r4", "r6", "r7", "r8", "s1", "s2", "s3", "s4", "s5"}
ROLES = {"router", "switch"}


def _fx(name):
    with open(os.path.join(PROM, name), encoding="utf-8") as fh:
        return json.load(fh)


SET = cases.load(FILE)
CAPTURED = set(_fx("ask_names.json")["answer"]["data"])
_DEV = _fx("ask_labels.json")["values"]["ifHCInOctets"]["device"]
CAPTURED_DEVICES = set(_DEV["data"] if isinstance(_DEV, dict) else _DEV)
assert len(CAPTURED_DEVICES) >= 8, CAPTURED_DEVICES


def test_twenty_numbered_cases_on_the_pinned_model():
    assert [c["n"] for c in SET["cases"]] == list(range(1, 21))
    assert SET["model"] == profiles.TASKS["nl_query"]["model"]
    assert profiles.cases_off_pin(CASES_DIR) == []


def test_the_operator_s_marks_are_the_expected_outcomes():
    by = {c["n"]: c["expect"]["outcome"] for c in SET["cases"]}
    assert by[3] == ["ask"] and by[17] == ["ask"]
    assert set(by[18]) == {"ask", "refuse"} and set(by[19]) == {"refuse", "ask"}
    assert "answer" not in by[19], "an injection never becomes an answer"


def test_every_expectation_is_the_real_catalogue_s():
    for c in SET["cases"]:
        e = c["expect"]
        for m in e.get("metric", ()):
            assert m in CAPTURED, (c["n"], m)
        for token in list(e.get("ops_include", ())) + list(e.get("group_any", ())):
            assert pq.parse_op(token) is not None, (c["n"], token)
        for kind in e.get("first_op", ()):
            assert kind in pq.RANGE_OPS, (c["n"], kind)
        if "role" in e:
            assert e["role"] in ROLES, (c["n"], e["role"])
        for r in e.get("range", ()):
            assert r in pq.RANGES or r == "custom", (c["n"], r)
        for d in e.get("devices", ()):
            assert d in NETWORK, (c["n"], d)
            if d not in CAPTURED_DEVICES:
                assert d in c["flag"], f"case {c['n']}: {d} postdates the capture, unflagged"


def test_the_offer_holds_each_answer_s_metric(world):
    """The deterministic step before any call: for every case expecting an answer, a metric
    it allows is among those offered from the real catalogue, the network's devices' metrics
    first (2026-10-25: before that rule, 'How long has r4 been up?' offered no sysUpTime and
    'Compare CPU on s3 and s4' only the monitoring host's own CPU)."""
    from modules.ai import nl_query
    from tests.test_history_ask_metrics import NOW as CAPTURED_AT
    rng = pq.window(dict(pq.DEFAULTS), CAPTURED_AT)
    cat = pq.catalogue("Lab", world.prom, rng, CAPTURED_AT)
    carried = nl_query.device_metrics(world.prom, rng)
    assert {"cpmCPUTotal5minRev", "sysUpTime"} <= carried and "cpu_usage_idle" not in carried
    missing = []
    for c in SET["cases"]:
        if c["expect"]["outcome"] != ["answer"]:
            continue
        names = [o[0] for o in nl_query.retrieve(c["question"], cat, carried)]
        if not set(c["expect"]["metric"]) & set(names):
            missing.append((c["n"], c["question"], names[:3]))
    assert missing == [], missing


NOW = time.mktime((2026, 10, 25, 9, 30, 0, 0, 0, 0)) - time.timezone


def _answer(**v):
    return {"ok": True, "error": "", "values": dict(
        {"m": "cpmCPUTotal5minRev", "dev": ["r1"], "role": "", "op": [], "top": "",
         "range": "1h"}, **v)}


def test_the_judge_passes_a_right_answer_and_names_each_miss():
    one = SET["cases"][0]["expect"]
    assert cases.misses(one, _answer(), NOW) == []
    assert cases.misses(one, _answer(dev=["r2"]), NOW) == ["devices ['r2'], expected ['r1']"]
    assert cases.misses(one, _answer(m="sysUpTime"), NOW)[0].startswith("metric 'sysUpTime'")
    three = SET["cases"][2]["expect"]
    assert cases.misses(three, {"ok": False, "error": "ask", "clarify": "which?"}, NOW) == []
    assert cases.misses(three, _answer(), NOW) == ["outcome answer, expected one of ['ask']"]
    assert cases.misses(three, {"ok": False, "error": "no_match"}, NOW)[0].startswith(
        "outcome not the model's: no_match")


def test_the_judge_knows_yesterday_from_now():
    sixteen = SET["cases"][15]["expect"]
    got = _answer(m="ifInDiscards", dev=["r1", "r2", "r3"], op=["rate:5m"], range="custom",
                  **{"from": "2026-10-24 00:00", "to": "2026-10-25 00:00"})
    assert cases.misses(sixteen, got, NOW) == []
    got["values"]["from"] = "2026-10-23 00:00"
    assert any("expected yesterday" in m for m in cases.misses(sixteen, got, NOW))


def test_a_recorded_answer_reads_as_nl_query_says_it():
    rec = {"outcome": "answer", "question": "", "why_not": "", "metric": "ifInErrors",
           "devices": ["r8"], "role": "", "interfaces": [], "filters": [],
           "operations": [{"kind": "rate", "arg": "5m"}], "top": "none", "range": "24h",
           "from_utc": "", "to_utc": ""}
    got = cases.result_of(rec)
    assert got["values"]["op"] == ["rate:5m"] and got["values"]["top"] == ""
    assert cases.misses(SET["cases"][3]["expect"], got, NOW) == []
    assert cases.result_of(dict(rec, outcome="ask", question="which?"))["error"] == "ask"


def _recorder():
    import importlib.machinery
    import importlib.util
    loader = importlib.machinery.SourceFileLoader(
        "nmas_nl_cases", os.path.join(ROOT, "scripts", "nmas-nl-cases"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


def test_the_recorder_stops_at_hosted_ai_off_spending_nothing(world, monkeypatch, tmp_path):
    from modules import settings_schema
    monkeypatch.setattr(settings_schema, "get_setting", lambda k, d=None: d)
    out = tmp_path / "rec.json"
    assert _recorder().record(ROOT, "Lab", "operator@example.com", str(out)) == 0
    assert json.loads(out.read_text())["recordings"] == [] and world.sent == []


def test_the_recorder_stops_at_the_provider_s_failure(world, tmp_path):
    """No send planted: the adapter is reached and the network guard refuses it, so the
    first case is the provider's failure, not the model's answer, and the run stops."""
    out = tmp_path / "rec.json"
    assert _recorder().record(ROOT, "Lab", "operator@example.com", str(out)) == 0
    assert json.loads(out.read_text())["recordings"] == []


def test_the_recorder_records_each_case_and_judges_it(world, tmp_path, capsys, monkeypatch):
    from modules.ai import anthropic_adapter
    from tests.test_ai_nl_query import _choices
    monkeypatch.setattr(anthropic_adapter, "send", world.send)
    world.answer = _choices(metric="cpmCPUTotal5minRev", devices=["r1"], operations=[],
                            top="none", range="1h")
    out = tmp_path / "rec.json"
    assert _recorder().record(ROOT, "Lab", "operator@example.com", str(out)) == 0
    recs = json.loads(out.read_text())["recordings"]
    assert len(recs) == 20 and len(world.sent) <= 20
    assert recs[0]["misses"] == [] and recs[0]["choices"]["metric"] == "cpmCPUTotal5minRev"
    assert recs[2]["misses"] and recs[2]["misses"][0].startswith("outcome "), \
        "case 3 expects a question back: an answer, or a metric not offered, misses"
    assert "case  1: pass" in capsys.readouterr().out


def test_merge_writes_the_recording_and_refuses_another_model(tmp_path):
    import shutil
    dest = tmp_path / "tests" / "fixtures" / "ai_cases" / "nl_query"
    dest.mkdir(parents=True)
    shutil.copy(FILE, dest / "metrics.json")
    rec = tmp_path / "rec.json"
    choices = {"outcome": "ask", "question": "which device?", "why_not": "", "metric": "",
               "devices": [], "role": "", "interfaces": [], "filters": [], "operations": [],
               "top": "none", "range": "24h", "from_utc": "", "to_utc": ""}
    rec.write_text(json.dumps({"model": SET["model"], "recordings": [
        {"n": 3, "model": SET["model"], "now": NOW, "recorded_at": "t", "choices": choices},
        {"n": 4, "model": SET["model"], "now": NOW, "recorded_at": "t", "choices": None}]}))
    assert _recorder().merge(str(tmp_path), str(rec)) == 0
    merged = json.loads((dest / "metrics.json").read_text())["cases"]
    assert merged[2]["recorded"]["choices"]["question"] == "which device?"
    assert merged[3]["recorded"] is None, "a Mercury refusal is no recording"
    rec.write_text(json.dumps({"model": "claude-sonnet-5-5", "recordings": []}))
    assert _recorder().merge(str(tmp_path), str(rec)) == 2


def test_every_recorded_case_passes_and_the_rest_wait_for_their_recording():
    recorded = [c for c in SET["cases"] if c["recorded"]]
    for c in recorded:
        r = c["recorded"]
        assert r["model"] == SET["model"], (c["n"], r["model"])
        assert cases.misses(c["expect"], cases.result_of(r["choices"]), r["now"]) == [], c["n"]
    waiting = [c["n"] for c in SET["cases"] if not c["recorded"]]
    assert len(recorded) + len(waiting) == 20 and all(
        c["recorded"] is None for c in SET["cases"] if c["n"] in waiting)
