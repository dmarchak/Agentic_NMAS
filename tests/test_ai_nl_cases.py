"""Ask in words' recorded cases (PHASE8_PLAN 13.6; the operator's 20 questions, 2026-10-25;
tests/fixtures/ai_cases/nl_query/metrics.json; modules/ai/cases.py).

- The set: 25 cases (the operator's 20, the walk's two, metrics v10's low-ranked right
  metric, C1830, and two retired from held-out set 4, C1887), numbered, on the task's pinned
  model; the operator's ASK cases expect a question back, the device that does not exist and
  the injection a question or a refusal. The logs set (C1762): 20 cases, its judge
  (`cases.logs_misses`) and its stale check (`cases.stale_logs`).
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
import re
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
    # The operator's 20, and the two the walk of 2026-10-26 added (C1803's Logs route, C1805's
    # "since Monday"); the name kept, as the weakening check counts a renamed test as deleted.
    # Case 23 (2026-10-26, C1830): a question whose right metric ranks 15th of the 20 offered.
    # Cases 24 and 25 (2026-10-28, C1887): held-out set 4's 15 and 23, retired here with the
    # one-line acceptance main case 8 gives a whole-network "any" question.
    assert [c["n"] for c in SET["cases"]] == list(range(1, 26))
    assert all("retired" in c for c in SET["cases"] if c["n"] in (24, 25))
    assert SET["model"] == profiles.TASKS["nl_query"]["model"]
    assert profiles.cases_off_pin(CASES_DIR) == []


def test_the_operator_s_marks_are_the_expected_outcomes():
    by = {c["n"]: c["expect"]["outcome"] for c in SET["cases"]}
    # Case 3: a question back or one line per device (the operator, 2026-10-25), never one
    # line for every device.
    # Case 17: no metric matches its words, so Mercury answers itself (C1700).
    assert set(by[3]) == {"ask", "answer"} and by[17] == ["guide"]
    assert SET["cases"][2]["expect"]["group_any"] == ["avg:device"]
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
            # A range operation (a counter's), or `changes` (a gauge's, case 13).
            assert kind in pq.RANGE_OPS or kind in pq.CHANGES_OPS, (c["n"], kind)
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
    every = dict(dev=[], range="7d")
    assert cases.misses(three, _answer(op=["avg:device"], **every), NOW) == []
    assert cases.misses(three, _answer(op=["avg:"], **every), NOW) == [
        "operations ['avg:'] hold no group of ['avg:device']",
        "operations ['avg:'] put every device into one line (avg:), which the question did "
        "not ask for"]
    assert cases.misses(three, {"ok": False, "error": "no_match"}, NOW)[0].startswith(
        "outcome not the model's: no_match")


def test_the_judge_knows_the_named_spans_from_now():
    """C1740's spans, judged in UTC as the recorder asks (no viewer timezone): yesterday and
    last week end where the next span starts; this week runs to now, within a minute's
    slack."""
    import calendar as cal
    now = cal.timegm((2026, 10, 25, 22, 30, 0))       # a Sunday
    v = lambda frm, to: {"ok": True, "values": {"m": "x", "range": "custom",  # noqa: E731
                                                "from": frm, "to": to}}
    assert cases.misses({"outcome": ["answer"], "span": "yesterday"},
                        v("2026-10-24 00:00", "2026-10-25 00:00"), now) == []
    assert cases.misses({"outcome": ["answer"], "span": "last week"},
                        v("2026-10-12 00:00", "2026-10-19 00:00"), now) == []
    assert cases.misses({"outcome": ["answer"], "span": "this week"},
                        v("2026-10-19 00:00", "2026-10-25 22:31"), now) == []
    assert cases.misses({"outcome": ["answer"], "span": "this week"},
                        v("2026-10-18 22:30", "2026-10-25 22:30"), now) == [
        "From '2026-10-18 22:30', expected this week's start '2026-10-19 00:00'"]
    assert cases.misses({"outcome": ["answer"], "span": "this week"},
                        v("2026-10-19 00:00", "2026-10-25 20:00"), now) == [
        "to '2026-10-25 20:00', expected now"]
    assert cases.misses({"outcome": ["answer"], "span": "last week"},
                        v("2026-10-12 00:00", "2026-10-25 22:30"), now) == [
        "to '2026-10-25 22:30', expected last week's end '2026-10-19 00:00'"]


def test_mercury_s_guidance_is_a_question_back_where_one_is_expected():
    """The operator's ruling (2026-10-25, after held-out set 1 was seen; C1743): Mercury's
    own guidance asks the person to say what they mean, so it passes a case expecting a
    question back, and only such a case."""
    guide = {"ok": False, "error": "no_match", "guide": {"words": "Name a metric"}}
    asks = {"outcome": ["ask"]}
    assert cases.misses(asks, guide, NOW) == []
    assert cases.misses({"outcome": ["answer"]}, guide, NOW) == [
        "outcome guide, expected one of ['answer']"]
    assert cases.misses({"outcome": ["refuse"]}, guide, NOW) == [
        "outcome guide, expected one of ['refuse']"]
    assert asks == {"outcome": ["ask"]}, "the case's own expectation is left as written"


def test_no_case_puts_different_devices_into_one_line_unless_it_asks_for_it():
    """The operator's rule (2026-10-25), held over every case: a group with no label is one
    line for every device it reaches, a miss unless the case names it (8 and 9 count whether
    any session is down); one line for one named device is that device's."""
    fifteen = SET["cases"][14]["expect"]
    two = dict(m="cpuAvgBusy5", dev=["s3", "s4"], range="7d")
    assert cases.misses(fifteen, _answer(**two), NOW) == []
    assert cases.misses(fifteen, _answer(op=["max:"], **two), NOW) == [
        "operations ['max:'] put every device into one line (max:), which the question did "
        "not ask for"]
    eight = SET["cases"][7]["expect"]
    assert cases.misses(eight, _answer(m="cbgpPeer2State", dev=[], op=["ne:6", "count:"]),
                        NOW) == []
    one = SET["cases"][0]["expect"]
    assert cases.misses(one, _answer(op=["avg:"]), NOW) == [], "one device's one line"


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


#: Held-out set 2 (the operator, 2026-10-25): set 1 was seen when v6 was measured, and is
#: retired as a test; it stays in the repository as v6's record, guarded by nothing here.
HELD = cases.load(os.path.join(CASES_DIR, "nl_query", "held_out_2.json"))
SEEN = cases.load(os.path.join(CASES_DIR, "nl_query", "held_out.json"))


def test_the_held_out_set_is_ten_new_questions_on_new_devices_and_metrics():
    """C1724's overfitting guard (the operator, 2026-10-25): ten questions written before v7
    was measured, on devices the 20 name none of and metrics neither the 20 nor the seen set 1
    expects (each answer case has at least one expected metric of its own), none named by any
    prompt's worked examples, in questions of its own; two ambiguous cases ask, one
    healthy-nothing case answers, and the named spans of C1740 are asked."""
    assert [c["n"] for c in HELD["cases"]] == list(range(1, 11))
    assert HELD["model"] == profiles.TASKS["nl_query"]["model"]
    words = lambda c: set(re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]*", c["question"]))  # noqa: E731
    twenty_devices = {d for c in SET["cases"] for d in c["expect"].get("devices", ())}
    twenty_devices |= {w for c in SET["cases"] for w in words(c) if w in NETWORK}
    held_devices = {d for c in HELD["cases"] for d in c["expect"].get("devices", ())}
    assert held_devices and not held_devices & twenty_devices, held_devices & twenty_devices
    seen_metrics = {m for s in (SET, SEEN) for c in s["cases"]
                    for m in c["expect"].get("metric", ())}
    for c in HELD["cases"]:
        if "metric" in c["expect"]:
            assert set(c["expect"]["metric"]) - seen_metrics, (c["n"], "no metric of its own")
            for m in c["expect"]["metric"]:
                assert m in CAPTURED, (c["n"], m)
    outcomes = [c["expect"]["outcome"] for c in HELD["cases"]]
    assert outcomes.count(["ask"]) == 2
    assert sum(1 for c in HELD["cases"] if c["flag"].startswith("HEALTHY")) == 1
    asked = {c["question"] for s in (SET, SEEN) for c in s["cases"]}
    assert not {c["question"] for c in HELD["cases"]} & asked
    assert {c["expect"].get("span") for c in HELD["cases"]} >= {"yesterday", "this week",
                                                                "last week"}


def test_no_prompt_names_a_held_out_device_or_its_own_metric():
    """Never tuned on: no prompt file names a held-out device or a metric only the held-out
    set expects, so the set measures generalisation."""
    twenty_metrics = {m for c in SET["cases"] for m in c["expect"].get("metric", ())}
    held_devices = {d for c in HELD["cases"] for d in c["expect"].get("devices", ())}
    own = {m for c in HELD["cases"] for m in c["expect"].get("metric", ())} - twenty_metrics
    prompts_dir = os.path.join(ROOT, "prompts")
    for name in sorted(os.listdir(prompts_dir)):
        text = open(os.path.join(prompts_dir, name), encoding="utf-8").read()
        found = [d for d in held_devices if re.search(rf"\b{re.escape(d)}\b", text)]
        found += [m for m in own if m in text]
        assert not found, (name, found)


def test_the_held_out_set_is_not_stale_against_the_captured_catalogue(world):
    rec = _recorder()
    assert rec.check(ROOT, "Lab", rec.HELD_OUT) == []


def test_a_stale_expectation_fails_the_check_not_the_model():
    """The operator's rule (2026-10-25; cases 11, 13 and 15 were stale): each answer case's
    expected metric must be carried by its devices, else its role, else the network's devices;
    a scope that could not be read is a problem too; a case expecting no answer is not asked."""
    data = {"cases": [
        {"n": 1, "expect": {"outcome": ["answer"], "metric": ["m1"], "devices": ["d1"]}},
        {"n": 2, "expect": {"outcome": ["answer"], "metric": ["m2", "m3"], "role": "edge"}},
        {"n": 3, "expect": {"outcome": ["answer"], "metric": ["m4"]}},
        {"n": 4, "expect": {"outcome": ["guide"]}},
        {"n": 5, "expect": {"outcome": ["answer"], "metric": ["m5"], "devices": ["d2"]}},
        {"n": 6, "expect": {"outcome": ["ask", "answer"], "metric": ["m6"], "role": "core"}}]}
    asked = []

    def carried(kind, value):
        asked.append((kind, value))
        return {"devices": {"m1"} if value == ["d1"] else None,
                "role": {"m3"} if value == "edge" else {"m7"}, "all": {"x"}}[kind]
    assert cases.stale(data, carried) == [
        "case 3: none of m4 is carried by the network's devices",
        "case 5: what devices d2 carry could not be read",
        "case 6: none of m6 is carried by the core role"]
    assert ("devices", ["d1"]) in asked and ("role", "edge") in asked and len(asked) == 5


def test_the_case_file_is_not_stale_against_the_captured_catalogue(world):
    """The recorder's check through the builder's own client, the 2026-10-15 capture's
    stand-in answering what the devices carry (it ignores a device or role selector)."""
    assert _recorder().check(ROOT, "Lab") == []


def test_the_recorder_stops_at_a_stale_expectation_spending_nothing(world, tmp_path, capsys):
    plain = world.prom._get

    def _get(path, **params):
        if path == "api/v1/label/__name__/values" and "match[]" in params:
            return world.prom._ok({"status": "success", "data": []})   # nothing carried
        return plain(path, **params)
    world.prom._get = _get
    out = tmp_path / "rec.json"
    assert _recorder().record(ROOT, "Lab", "evaluation:test-run", str(out)) == 3
    assert world.sent == [] and not out.exists()
    err = capsys.readouterr().err
    assert "stale expectation: case 1: none of cpmCPUTotal1minRev, cpmCPUTotal5minRev" in err
    assert "nothing recorded, nothing spent" in err


def test_the_recorder_stops_at_hosted_ai_off_spending_nothing(world, monkeypatch, tmp_path):
    from modules import settings_schema
    monkeypatch.setattr(settings_schema, "get_setting", lambda k, d=None: d)
    out = tmp_path / "rec.json"
    assert _recorder().record(ROOT, "Lab", "evaluation:test-run", str(out)) == 0
    assert json.loads(out.read_text())["recordings"] == [] and world.sent == []


def test_the_recorder_stops_at_the_provider_s_failure(world, tmp_path):
    """No send planted: the adapter is reached and the network guard refuses it, so the
    first case is the provider's failure, not the model's answer, and the run stops."""
    out = tmp_path / "rec.json"
    assert _recorder().record(ROOT, "Lab", "evaluation:test-run", str(out)) == 0
    assert json.loads(out.read_text())["recordings"] == []


def test_the_recorder_records_each_case_and_judges_it(world, tmp_path, capsys, monkeypatch):
    from modules.ai import anthropic_adapter
    from tests.test_ai_nl_query import _choices
    monkeypatch.setattr(anthropic_adapter, "send", world.send)
    world.answer = _choices(metric="cpmCPUTotal5minRev", devices=["r1"], operations=[],
                            top="none", range="1h")
    out = tmp_path / "rec.json"
    assert _recorder().record(ROOT, "Lab", "evaluation:test-run", str(out)) == 0
    recs = json.loads(out.read_text())["recordings"]
    assert len(recs) == len(SET["cases"]) == 25 and len(world.sent) <= 25
    assert recs[0]["misses"] == [] and recs[0]["choices"]["metric"] == "cpmCPUTotal5minRev"
    assert recs[2]["misses"] and recs[2]["misses"][0].startswith("outcome "), \
        "case 3 expects a question back: an answer, or a metric not offered, misses"
    assert "case  1: pass" in capsys.readouterr().out


def test_a_comparison_on_another_model_asks_it_and_leaves_the_pin(world, tmp_path, capsys,
                                                                   monkeypatch):
    """`--model claude-sonnet-5-5` (the operator, 2026-10-26: Sonnet beside the pinned Haiku):
    every call goes to that model, the recording names it, the pin file is not touched, and
    an unknown model is refused before anything is asked."""
    from modules.ai import anthropic_adapter
    from tests.test_ai_nl_query import _choices
    monkeypatch.setattr(anthropic_adapter, "send", world.send)
    monkeypatch.setitem(profiles.TASKS, "nl_query", dict(profiles.TASKS["nl_query"]))
    pinned = profiles.load_pins()["nl_query"]
    world.answer = _choices(metric="cpmCPUTotal5minRev", devices=["r1"], operations=[],
                            top="none", range="1h")
    out = tmp_path / "rec.json"
    assert _recorder().record(ROOT, "Lab", "evaluation:test-run", str(out),
                              model="claude-sonnet-5-5") == 0
    got = json.loads(out.read_text())
    assert got["model"] == "claude-sonnet-5-5" and world.sent
    assert {s["body"]["model"] for s in world.sent} == {"claude-sonnet-5-5"}
    assert profiles.load_pins()["nl_query"] == pinned, "the pin file is never written"
    assert "a comparison on claude-sonnet-5-5, the pin file unchanged" in capsys.readouterr().out
    sent = len(world.sent)
    assert _recorder().record(ROOT, "Lab", "evaluation:test-run", str(out),
                              model="no-such-model") == 2
    assert len(world.sent) == sent


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
    rec.write_text(json.dumps({"model": "claude-haiku-5-5", "recordings": []}))
    assert _recorder().merge(str(tmp_path), str(rec)) == 2


def test_every_recorded_case_passes_and_the_rest_wait_for_their_recording():
    recorded = [c for c in SET["cases"] if c["recorded"]]
    for c in recorded:
        r = c["recorded"]
        assert r["model"] == SET["model"], (c["n"], r["model"])
        assert cases.misses(c["expect"], cases.result_of(r["choices"]), r["now"]) == [], c["n"]
    waiting = [c["n"] for c in SET["cases"] if not c["recorded"]]
    assert len(recorded) + len(waiting) == len(SET["cases"]) == 25 and all(
        c["recorded"] is None for c in SET["cases"] if c["n"] in waiting)


_RELATIVE = re.compile(r"\b(today|yesterday|this week|last week|since monday|so far)\b", re.I)


def test_every_date_relative_case_carries_its_own_clock():
    """The operator, 2026-10-26: a case whose answer depends on the day it is asked ("this
    week" on a Monday) carries "now", so it tests the same thing on every day it is recorded;
    a scan of every case file, its floor the walk's four."""
    seen = 0
    for name in ("metrics.json", "logs.json", "held_out_2.json"):
        for c in cases.load(os.path.join(CASES_DIR, "nl_query", name))["cases"]:
            if _RELATIVE.search(c["question"]) or c["expect"].get("span"):
                seen += 1
                assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", c.get("now") or ""), (
                    name, c["n"], c["question"])
    assert seen >= 4


def test_a_case_with_its_own_clock_is_asked_and_judged_as_of_it(world, tmp_path, monkeypatch):
    """The recorder asks such a case with its "now" (the prompt's now and the range's), and
    records that time, so the replay judges it as of it."""
    import calendar
    from modules.ai import anthropic_adapter
    from modules.ai import nl_query
    from tests.test_ai_nl_query import _choices
    monkeypatch.setattr(anthropic_adapter, "send", world.send)
    world.answer = _choices(metric="cpmCPUTotal5minRev", devices=["r1"], operations=[],
                            top="none", range="1h")
    asked = []
    plain = nl_query.metrics

    def metrics(*a, **kw):
        asked.append(kw.get("now"))
        return plain(*a, **kw)
    monkeypatch.setattr(nl_query, "metrics", metrics)
    data = {"about": "", "model": SET["model"], "cases": [
        dict(SET["cases"][0], now="2026-10-26T20:00:00Z"), SET["cases"][1]]}
    path = tmp_path / "frozen.json"
    path.write_text(json.dumps(data))
    out = tmp_path / "rec.json"
    rc = _recorder().record(ROOT, "Lab", "evaluation:t", str(out), case_file=str(path),
                            only=(1,))
    assert rc == 0
    frozen = calendar.timegm((2026, 10, 26, 20, 0, 0, 0, 0, 0))
    assert asked == [frozen], "only case 1, asked as of its clock"
    (rec,) = json.loads(out.read_text())["recordings"]
    assert rec["now"] == frozen and rec["recorded_at"] == "2026-10-26T20:00:00Z"


def test_a_measurement_is_never_recorded_as_a_person(world, tmp_path, capsys):
    """C1784: a recording's actor names the run (evaluation:<run id>), never an address."""
    out = tmp_path / "rec.json"
    assert _recorder().record(ROOT, "Lab", "operator@example.com", str(out)) == 2
    assert world.sent == [] and not out.exists()
    assert "an evaluation is recorded as evaluation:<run id>" in capsys.readouterr().err
    # C1846: not an address, yet not a run, is refused too; none given names the run itself.
    assert _recorder().record(ROOT, "Lab", "alex", str(out)) == 2
    assert world.sent == [] and "is not evaluation:<run id>" in capsys.readouterr().err
    from modules.ai import cases
    actor, refusal = cases.evaluation_actor("", "nl-cases", now=1_793_000_000.0)
    assert refusal == "" and actor == "evaluation:nl-cases-20261026T073320Z"


# ------------------------------------------------------------------- the logs half (C1762)

LOGS = cases.load(os.path.join(CASES_DIR, "nl_query", "logs.json"))


def test_the_logs_set_is_twenty_numbered_cases_on_the_pinned_model():
    from modules.ai import nl_query
    from modules import history_logq as lq
    assert LOGS["kind"] == "logs" and [c["n"] for c in LOGS["cases"]] == list(range(1, 21))
    assert LOGS["model"] == profiles.TASKS["nl_query"]["model"]
    for c in LOGS["cases"]:
        e = c["expect"]
        for s in e.get("mnemonics", ()):
            for mn in s:
                assert lq._MN.match(mn), (c["n"], mn)
        for r in e.get("range", ()):
            assert r in [x.value for x in nl_query.LogsRange], (c["n"], r)
        for d in e.get("devices", ()):
            assert d in NETWORK, (c["n"], d)
        assert c["recorded"] is None or c["recorded"]["model"] == LOGS["model"]
    # The walk's cases (C1804): reboots over 7 days, and since Monday.
    by = {c["n"]: c["expect"] for c in LOGS["cases"]}
    assert ["%SYS-5-RELOAD"] in by[1]["mnemonics"] and by[1]["range"] == ["7d"]
    assert by[2]["span"] == "this week" and by[2]["range"] == ["custom"]


def _logs_got(**v):
    base = {"job": [], "dev": [], "role": "", "sev": "", "mn": [], "has": "", "not": "",
            "show": "lines", "by": "device", "every": "5m", "range": "24h"}
    return {"ok": True, "error": "", "values": dict(base, **v)}


def test_the_logs_judge_passes_the_right_answer_and_names_each_miss():
    e = {"outcome": ["answer"], "mnemonics": [["%SYS-5-RELOAD"],
                                              ["%SYS-5-RELOAD", "%SYS-5-RESTART"]],
         "contains_empty": True, "show": ["lines", "counts"], "range": ["7d"]}
    ok = _logs_got(mn=["%SYS-5-RESTART", "%SYS-5-RELOAD"], range="7d")
    assert cases.logs_misses(e, ok, NOW) == []
    walk = _logs_got(has="reboot", range="custom", **{"from": "2026-10-26 00:00",
                                                      "to": "2026-10-26 19:00"})
    got = cases.logs_misses(e, walk, NOW)
    assert "mnemonics [], expected one of" in got[0]
    assert any("text 'reboot', expected none" in m for m in got)
    assert any("range 'custom', expected one of ['7d']" in m for m in got)
    assert cases.logs_misses({"outcome": ["refuse"]}, {"ok": False, "error": "ask"},
                             NOW) == ["outcome ask, expected one of ['refuse']"]


def test_a_recorded_logs_answer_replays_through_its_schema():
    choices = {"outcome": "answer", "question": "", "why_not": "", "kinds": [],
               "devices": [], "role": "", "severity": "any",
               "mnemonics": ["%SYS-5-RELOAD"], "contains": "", "excludes": "",
               "show": "lines", "by": "device", "every": "5m", "range": "7d",
               "from_utc": "", "to_utc": ""}
    assert cases.result_of_logs(choices)["values"]["mn"] == ["%SYS-5-RELOAD"]
    assert cases.result_of_logs(dict(choices, needs=[]))["values"]["range"] == "7d"


def test_a_logs_case_whose_mnemonics_are_no_longer_offered_is_stale():
    data = {"cases": [
        {"n": 1, "question": "q", "expect": {"outcome": ["answer"],
                                             "mnemonics": [["%BGP-5-ADJCHANGE"]]}},
        {"n": 2, "question": "q", "expect": {"outcome": ["answer"], "mnemonics": [[]]}},
        {"n": 3, "question": "q", "expect": {"outcome": ["refuse"]}}]}
    assert cases.stale_logs(data, lambda q: ["%BGP-5-ADJCHANGE"]) == []
    got = cases.stale_logs(data, lambda q: ["%OSPF-5-ADJCHG"])
    assert got == ["case 1: no expected set of [['%BGP-5-ADJCHANGE']] is offered "
                   "(['%OSPF-5-ADJCHG'])"]
    assert cases.stale_logs(data, lambda q: None) == [
        "case 1: what the question is offered could not be read"]


def test_every_recorded_logs_case_passes_and_the_rest_wait():
    for c in LOGS["cases"]:
        if c["recorded"]:
            r = c["recorded"]
            assert cases.logs_misses(c["expect"], cases.result_of_logs(r["choices"]),
                                     r["now"]) == [], c["n"]
