"""Lab 9 B4's evaluation (modules/sdn/b4_eval.py; scripts/nmas-sdn-b4-eval; docs/HEAL_TO_INTENT.md
19.13): the analyst without tools against the analyst with the trace tool, on fixed snapshots.

The snapshots are 19.13's recorded cases (tests/fixtures/ai_cases/sdn_classify/recorded.json:
the Lab 8 run's evidence packs, real, as Mercury kept them), each converted by the module's stated
edits; the blind and held-out sets are never read here (19.13: no tuning on a blind case). No
model is called: the gateway is real (the evaluation trigger, the caps, the record) and its
provider a fake `send` scripted by what each request asks.

- **A case's snapshot** is sealed by the analyst's own code, holds the case's evidence ids and
  Lab 8's hosts, and says its table is part of the switch's; its planted issue is its
  expectation's ``cites_any``; a benign case has none.
- **The trace over a real case** (IPv4 and IPv6): h1's IPv4 traffic to h3 leaves by h4's port
  (the unauthorised flow), its IPv6 traffic is delivered.
- **The measures**, exactly, on a scripted provider: findings, misses, false positives, benign
  runs answered as a threat, cases reliable, McNemar, the calls, and the cost from the record.
- **It spends only with --yes-spend**, and the script hands both arms in.
- **The lab hardware's snapshots** (C2965, ``--snapshots``): B1's own snapshots and sheet,
  copied; each sealed snapshot a case with the issues standing at its collection, a clean one
  benign, a broken seal skipped and said; scored issue by issue by B1's rule; the estimate
  counts them; neither the network's folder nor the copy is written.
"""
import importlib.machinery
import importlib.util
import json
import os

import pytest

from modules.ai import anthropic_adapter as A
from modules.ai import calls, profiles
from modules.ai import sdn_analyst_tools as AT
from modules.sdn import analyst as AN
from modules.sdn import b4_eval as EV
from tests.ai_person import PERSON
from tests.test_sdn_analyst import NET, OVS3, collect, world  # noqa: F401 (the fixture)
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BAD = "flow:lab:0000000000000002:t0:p100:89d181012c"
H1_TO_H3 = "flow:lab:0000000000000002:t0:p1:3605883d95"
S1_PORT3 = "port:lab:0000000000000001:3"
TOKENS = (6000, 400)


def cases(*keys):
    """The recorded cases named, in the order named (the files' order otherwise)."""
    got = {c["key"]: c for c in EV.load_cases(ROOT, ["recorded"], list(keys))}
    return [got[k] for k in keys]


def reply(answer):
    return A.Reply(status=200, body={"content": [{"type": "text", "text": json.dumps(answer)}],
                                     "stop_reason": "end_turn",
                                     "usage": {"input_tokens": TOKENS[0],
                                               "output_tokens": TOKENS[1]}},
                   attempts=1, latency_s=0.1)


def finding(evidence, severity, text):
    return {"severity": severity, "finding": text, "why": "w", "evidence": list(evidence)}


# ── the cases ─────────────────────────────────────────────────────────────────────────────────

def test_each_case_is_a_sealed_snapshot_with_its_planted_issue(networks):  # noqa: F811
    bad, normal, flood = cases("unauthorised-s2", "normal-2", "flood-s1")
    snap = EV.case_snapshot(bad, NET)
    assert AN.intact(snap) and snap["id"].startswith("snap-")
    ids = AN.evidence_ids(snap)
    assert BAD in ids and H1_TO_H3 in ids and len(snap["switches"]) == 1
    (sw,) = snap["switches"]
    assert sw["dpid_hex"] == "0000000000000002" and sw["partial"].startswith("the case's")
    assert next(f for f in sw["flows"] if f["id"] == BAD)["cookie"] == 0xbad0
    assert "the flows listed are part of its table" in AN.facts(snap)
    assert [(h["mac"], h["port_no"]) for h in snap["hosts"]] == [
        ("00:00:00:00:00:03", 1), ("00:00:00:00:00:04", 2), ("00:00:00:00:00:01", 3),
        ("00:00:00:00:00:02", 3)], "h3 and h4 on s2's own ports, h1 and h2 where they enter"
    assert "detection" not in AN.facts(snap) and "unauthorised" not in AN.facts(snap)
    assert [i["evidence"] for i in EV.case_issues(bad)] == [[BAD]]
    assert EV.kind_of(normal) == "benign" and EV.case_issues(normal) == []
    (issue,) = EV.case_issues(flood)
    assert issue["evidence"] == ["port:lab:0000000000000001:2", "rate:lab:0000000000000001:2"]
    assert "rate:lab:0000000000000001:2" in AN.evidence_ids(EV.case_snapshot(flood, NET))


def test_a_trace_over_a_real_case_ipv4_and_ipv6(networks):  # noqa: F811
    (bad,) = cases("unauthorised-s2")
    snap = EV.case_snapshot(bad, NET)
    four = AT.trace_answer(snap, "192.0.2.1", "192.0.2.3")
    assert four["state"] == "not_delivered" and four["branches"][0]["outcome"] == "elsewhere"
    assert four["branches"][0]["hops"] == [
        {"switch": "0000000000000002", "in": 3, "out": 2, "flows": [BAD]}]
    assert BAD in four["evidence"] and four["partial"] == ["0000000000000002"]
    assert "a flow it does not hold may decide otherwise" in four["words"]
    six = AT.trace_answer(snap, "2001:db8:8::1", "2001:db8:8::3")
    assert six["state"] == "delivered" and six["family"] == 6
    assert six["branches"][0]["hops"][0]["flows"] == [H1_TO_H3] and BAD not in six["evidence"]


# ── the measures, on a scripted provider ──────────────────────────────────────────────────────

class Scripted:
    """Answers each request by what it asks: the baseline (B1's prompt) misses the unauthorised
    flow, citing an ordinary one, and calls the normal case's quiet port a medium threat; the
    technique asks for a trace on the unauthorised case and then cites the flow it found, and
    answers the normal case with nothing in one pass."""

    def __init__(self):
        self.bodies = []

    def __call__(self, body, key):
        self.bodies.append(body)
        text = json.dumps(body)
        tools = "Reads you may ask Mercury for" in text or "mercury_reads" in text
        s2 = BAD in text                        # the unauthorised case's snapshot
        if not tools:
            return reply({"findings": [finding([H1_TO_H3], "low", "h1 to h3 is busy")]} if s2
                         else {"findings": [finding(["rate:lab:0000000000000001:3"], "medium",
                                                    "A scan on port 3")]})
        if not s2:
            return reply({"findings": [], "reads": []})
        if "mercury_reads" not in text:
            return reply({"findings": [], "reads": [
                {"op": "trace", "args": {"src": "192.0.2.1", "dst": "192.0.2.3",
                                         "proto": "icmp"},
                 "why": "where h1's traffic to h3 goes", "hypothesis": "it is diverted"}]})
        return reply({"findings": [finding([BAD, "read:1"], "high",
                                           "h3's IPv4 traffic is sent out h4's port")]})


def test_the_runner_s_measures_are_exact_on_a_scripted_provider(world):  # noqa: F811
    from modules.ai import triggers
    from modules.sdn import analyst

    picked = cases("unauthorised-s2", "normal-2")
    send = Scripted()
    tick = iter(range(1000))
    actor = "evaluation:b4-test"
    results = EV.run(picked, {"baseline": analyst.ask_snapshot, "tools": AT.ask_snapshot},
                     runs=2, network=NET, actor=actor, trigger=triggers.evaluation(actor),
                     send=send, clock=lambda: float(next(tick)))
    assert results["stopped"] == ""
    assert len(send.bodies) == 2 * 2 + 2 * (2 + 1), "baseline 1 a run; tools 2 and 1"
    EV.recorded_cost(results, calls.read()["rows"])
    one = profiles.cost_usd("claude-haiku-5-5", *TOKENS)
    s = EV.summary(results)["roles"]["recorded"]
    b, t, d = s["techniques"]["baseline"], s["techniques"]["tools"], s["difference"]
    assert (b["reliable"], t["reliable"], s["cases"]) == (0, 2, 2)
    assert (b["findings"], b["found"], b["misses"], b["false_positives"],
            b["benign_threat_runs"]) == (4, 0, 2, 4, 2)
    assert (t["findings"], t["found"], t["misses"], t["false_positives"],
            t["benign_threat_runs"]) == (2, 2, 0, 0, 0)
    assert (b["calls"], t["calls"], t["reads"]) == (4, 6, 2)
    assert b["cost_usd"] == pytest.approx(4 * one) and t["cost_usd"] == pytest.approx(6 * one)
    assert d["cost_usd"] == pytest.approx(2 * one)
    assert (d["flipped_to_reliable"], d["flipped_from_reliable"], d["mcnemar_p"]) == (2, 0, 0.5)
    assert d["share_reliable"] == 1.0 and d["share_interval"] == (1.0, 1.0)
    assert b["seconds_median"] == 1.0
    rows = [r for r in calls.read()["rows"] if r.get("actor") == actor]
    assert len(rows) == 10 and {r["trigger"]["kind"] for r in rows} == {"evaluation"}
    assert AN._latest(NET) == {}, "the network's analyst store is untouched"
    verdict = EV.summary(results)["pass_rule"]
    assert verdict["improves"] is None and "no blind case was run" in verdict["words"]


def test_each_wrong_run_is_kept_in_the_network_s_record(world):  # noqa: F811
    """C2943: a miss, a false-positive finding and a benign case answered as a threat are kept
    per case, technique and run in the network's record; a correct run keeps nothing."""
    from modules.ai import triggers
    from modules.sdn import analyst, evaluations

    actor = "evaluation:b4-kept"
    results = EV.run(cases("unauthorised-s2", "normal-2"),
                     {"baseline": analyst.ask_snapshot, "tools": AT.ask_snapshot}, runs=2,
                     network=NET, actor=actor, trigger=triggers.evaluation(actor),
                     send=Scripted(), now=lambda: 1793500000.0)
    rows = evaluations.read(NET)["rows"]
    assert [(r["case"], r["technique"], r["n"]) for r in rows] == [
        ("unauthorised-s2", "baseline", 1), ("unauthorised-s2", "baseline", 2),
        ("normal-2", "baseline", 1), ("normal-2", "baseline", 2)]
    miss, benign = rows[0], rows[2]
    assert (miss["script"], miss["kind"], miss["run"], miss["at"]) == (
        "nmas-sdn-b4-eval", "case_run", "b4-kept", "2026-11-01T02:26:40Z")
    assert miss["missed"] and not miss["threat_answered"] and miss["case_kind"] == "threat"
    assert BAD in miss["issue"]
    assert [(f["finding"], f["judged"]) for f in miss["findings"]] == [
        ("h1 to h3 is busy", "false_positive")]
    scored = results["cases"][0]["runs"]["baseline"][0]
    assert miss["calls"] == scored["calls"] and miss["false_positives"] == 1
    assert benign["threat_answered"] and not benign["missed"]
    assert benign["case_kind"] == "benign" and benign["findings"][0]["severity"] == "medium"
    assert evaluations.read("Branch")["state"] == "absent"
    assert AN._latest(NET) == {}, "the network's analyst store is untouched"


def test_mcnemar_exact_and_the_seeded_interval():
    assert EV.mcnemar_p(0, 0) == 1.0 and EV.mcnemar_p(5, 0) == 0.0625
    assert EV.mcnemar_p(3, 1) == 0.625 and EV.mcnemar_p(1, 3) == 0.625
    assert EV.bootstrap([0, 1, 1, 1], EV._mean) == EV.bootstrap([0, 1, 1, 1], EV._mean)
    assert EV.bootstrap([], EV._mean) == (None, None)


def test_the_pass_rule_needs_more_blind_cases_reliable_and_no_more_threat_runs():
    def case(kind, base_ok, tool_ok, threat=False):
        def runs(ok):
            return [{"correct": ok, "found": ok, "missed": not ok, "findings": 1,
                     "false_positives": 0, "threat_answered": threat and not ok,
                     "calls": ["c"], "reads": 0, "cost_usd": 0.0, "seconds": 1.0}]
        return {"key": "k", "role": "blind", "kind": kind,
                "runs": {"baseline": runs(base_ok), "tools": runs(tool_ok)}}
    up = {"cases": [case("threat", False, True), case("benign", True, True)]}
    assert EV.summary(up)["pass_rule"]["improves"] is True
    worse = {"cases": [case("threat", False, True), case("benign", True, False, threat=True)]}
    got = EV.summary(worse)["pass_rule"]
    assert got["improves"] is False and got["no_more_false_positives"] is False
    assert "does not improve results" in got["words"] and "the power is low" in got["words"]


# ── a person's explicit action ────────────────────────────────────────────────────────────────

def test_without_yes_spend_nothing_is_asked_and_with_it_the_report_is_written(world, tmp_path):  # noqa: F811
    from modules.sdn import analyst

    said = []
    send = Scripted()
    arms = {"baseline": analyst.ask_snapshot, "tools": AT.ask_snapshot}
    argv = ["--list", NET, "--runs", "1", "--roles", "recorded", "--cases",
            "unauthorised-s2,normal-2", "--out", str(tmp_path / "out")]
    assert EV.main(argv, arms=arms, root=ROOT, send=send, out=said.append) == 2
    assert send.bodies == [] and calls.read()["rows"] == []
    assert any("at most 6 calls, about $" in w for w in said)
    assert "refused: nothing was asked or spent" in said[-1]
    assert not os.path.exists(tmp_path / "out")
    said.clear()
    assert EV.main(argv + ["--yes-spend", "--actor", "evaluation:b4-report"], arms=arms,
                   root=ROOT, send=send, out=said.append) == 0
    assert len(send.bodies) == 5
    md = open(tmp_path / "out" / "b4-eval-b4-report.md", encoding="utf-8").read()
    data = json.load(open(tmp_path / "out" / "b4-eval-b4-report.json", encoding="utf-8"))
    assert "| Cases reliable (every run correct) | 0 of 2 | 2 of 2 |" in md
    assert "| unauthorised-s2 | recorded | threat | 0 of 1 | 1 of 1 |" in md
    assert data["summary"]["roles"]["recorded"]["techniques"]["tools"]["calls"] == 3
    assert data["meta"]["estimate"]["calls"] == 6


def test_prompt_asks_both_arms_with_a_candidate_and_the_report_names_what_was_asked(world, tmp_path):  # noqa: F811
    """``--prompt N`` (a version measured before it is adopted): both arms ask version N of the
    analyst's prompt, the trace tool the two built on it; without it they ask the ones in use;
    the estimate's line and the report name the prompts asked."""
    from modules.sdn import analyst

    said = []
    send = Scripted()
    arms = {"baseline": analyst.ask_snapshot, "tools": AT.ask_snapshot}
    argv = ["--list", NET, "--runs", "1", "--roles", "recorded", "--cases", "unauthorised-s2",
            "--out", str(tmp_path / "out")]
    in_use = EV.asked_prompts()[0]
    assert in_use["in_use"] and in_use["baseline_prompt"] == "{}.v{}".format(*AN.PROMPT)
    assert EV.main(argv + ["--prompt", "9"], arms=arms, root=ROOT, send=send,
                   out=said.append) == 2
    assert "--prompt 9: sdn_analyse has no prompt version 9; it has v1, v2" in said[-1]
    assert "nothing was asked" in said[-1] and send.bodies == []
    assert EV.main(argv + ["--prompt", "2"], arms=arms, root=ROOT, send=send,
                   out=said.append) == 2
    assert any("prompts sdn_analyse.v2 and sdn_analyse_tools.v3 and v4" in w for w in said)
    assert send.bodies == [], "without --yes-spend nothing is asked"
    assert EV.main(argv + ["--prompt", "2", "--yes-spend", "--actor", "evaluation:b4-v2"],
                   arms=arms, root=ROOT, send=send, out=said.append) == 0
    rows = [r for r in calls.read()["rows"] if r.get("actor") == "evaluation:b4-v2"]
    assert sorted({r["prompt"] for r in rows}) == ["sdn_analyse.v2", "sdn_analyse_tools.v3",
                                                   "sdn_analyse_tools.v4"]
    data = json.load(open(tmp_path / "out" / "b4-eval-b4-v2.json", encoding="utf-8"))
    assert data["meta"]["baseline_prompt"] == "sdn_analyse.v2"
    assert data["meta"]["tools_prompts"] == "sdn_analyse_tools.v3 and v4"
    md = open(tmp_path / "out" / "b4-eval-b4-v2.md", encoding="utf-8").read()
    assert "prompt sdn_analyse.v2; technique:" in md and "prompts sdn_analyse_tools.v3 and v4" in md
    # Without --prompt, the ones in use, and the report says those.
    assert EV.main(argv + ["--yes-spend", "--actor", "evaluation:b4-in-use"], arms=arms,
                   root=ROOT, send=send, out=said.append) == 0
    rows = [r for r in calls.read()["rows"] if r.get("actor") == "evaluation:b4-in-use"]
    assert in_use["baseline_prompt"] in {r["prompt"] for r in rows}
    data = json.load(open(tmp_path / "out" / "b4-eval-b4-in-use.json", encoding="utf-8"))
    assert data["meta"]["baseline_prompt"] == in_use["baseline_prompt"]
    assert data["meta"]["prompt_in_use"] is True


@pytest.mark.parametrize("extra, words", [
    (["--out", ROOT + "/tmp-b4"], "is inside the checkout"),
    (["--out", "/tmp/elsewhere", "--actor", "op@example.com"], "reads as a person's address"),
    (["--out", "/tmp/elsewhere", "--runs", "0"], "--runs is 1 to 50"),
])
def test_a_run_out_of_shape_is_refused_before_anything_is_read(networks, extra, words):  # noqa: F811
    said = []
    got = EV.main(["--list", NET] + extra, arms={}, root=ROOT, out=said.append)
    assert got == 2 and words in said[-1]


def test_the_script_hands_both_arms_and_refuses_without_yes_spend(networks, tmp_path,  # noqa: F811
                                                                  monkeypatch, capsys):
    loader = importlib.machinery.SourceFileLoader(
        "nmas_sdn_b4_eval", os.path.join(ROOT, "scripts", "nmas-sdn-b4-eval"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    seen = {}
    monkeypatch.setattr(EV, "main", lambda argv, **kw: seen.update(argv=argv, **kw) or 2)
    monkeypatch.chdir(tmp_path)
    assert mod.main(["--list", NET, "--out", str(tmp_path / "o")]) == 2
    from modules.sdn import analyst
    assert seen["arms"] == {"baseline": analyst.ask_snapshot, "tools": AT.ask_snapshot}
    assert seen["root"] == ROOT and "--yes-spend" not in seen["argv"]


# ── the lab hardware's snapshots (C2965) ──────────────────────────────────────────────────────
#
# B1's own path end to end: the recorded Ryu (tests/fixtures/lab9_captures/2026-11-06, read
# through `tests.test_sdn_analyst.collect`) collected, built and kept by the analyst's own
# `build_snapshot` and `save_snapshot`, the collection's time the one edit between snapshots;
# the sheet kept by `add_planted` and `remove_planted`; the network's folder then copied, as the
# operator copies it off the host, and the copy given to --snapshots.

T0 = 1_794_000_000                       # the recorded collection's own time
PORT3 = f"port:ctl-1:{OVS3}:3"            # the capture's LINK_DOWN port
DROPS = f"drop:ctl-1:{OVS3}:*"
RATE2 = f"rate:ctl-1:{OVS3}:2"


def _iso(epoch):
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _tree(folder):
    """Every file under *folder* with its bytes, to show nothing was written."""
    out = {}
    for base, _dirs, files in os.walk(folder):
        for name in files:
            path = os.path.join(base, name)
            out[os.path.relpath(path, folder)] = open(path, "rb").read()
    return out


@pytest.fixture
def lab(world, tmp_path):  # noqa: F811
    """Five snapshots of the recorded collection, an hour apart (S0 before anything was planted,
    S1 to S3, S4 whose seal the copy breaks), three planted issues (A before S1, C before S1 and
    removed between S1 and S2, B between S1 and S2), and the network's folder copied."""
    import shutil
    import types as T

    got, _s = collect(links=True)
    snaps = []
    for hour in range(-1, 4):
        snap = AN.build_snapshot(NET, dict(got, collected_at=_iso(T0 + 3600 * hour)),
                                 by=PERSON)
        AN.save_snapshot(NET, snap)
        snaps.append(snap)
    s0, s1, s2, s3, s4 = snaps
    a = AN.add_planted(NET, "OVS 3's port 3 pulled", PORT3, actor=PERSON, now=T0 - 600)
    c = AN.add_planted(NET, "Port 2 flooded", RATE2, actor=PERSON, now=T0 - 300)
    assert AN.remove_planted(NET, c["issue"]["id"], actor=PERSON, now=T0 + 1000)["ok"]
    b = AN.add_planted(NET, "A stale drop", DROPS, actor=PERSON, now=T0 + 1800)
    assert a["ok"] and b["ok"] and c["ok"]
    copy = tmp_path / "copy" / "sdn_analyst"
    shutil.copytree(AN._dir(NET), copy)
    path = copy / "snapshots" / f"{s4['id']}.json"
    kept = json.loads(path.read_text(encoding="utf-8"))
    kept["switches"][0]["name"] = "edited"
    path.write_text(json.dumps(kept), encoding="utf-8")
    return T.SimpleNamespace(s0=s0, s1=s1, s2=s2, s3=s3, s4=s4, copy=str(copy),
                             store=AN._dir(NET), world=world)


def test_each_sealed_snapshot_is_a_hardware_case_with_the_issues_standing_at_its_collection(lab):
    got = EV.load_hardware(lab.copy, NET, clean=[lab.s3["id"]])
    assert got["error"] == ""
    assert [(c["key"], c["role"], EV.kind_of(c)) for c in got["cases"]] == [
        (lab.s1["id"], "hardware", "threat"), (lab.s2["id"], "hardware", "threat"),
        (lab.s3["id"], "hardware", "benign")], "in the order they were collected"
    s1, s2, s3 = got["cases"]
    assert [i["name"] for i in EV.case_issues(s1)] == ["OVS 3's port 3 pulled"], \
        "C, removed (a correction) after S1 was collected, is not S1's; B planted after S1 neither"
    assert [i["name"] for i in EV.case_issues(s2)] == ["OVS 3's port 3 pulled", "A stale drop"], \
        "C is not S2's"
    assert all(i["name"] != "Port 2 flooded" for c in got["cases"] for i in EV.case_issues(c))
    assert [i["evidence"] for i in EV.case_issues(s2)] == [[PORT3], [DROPS]]
    assert EV.case_issues(s3) == [] and s3["clean"] and s3["sheet_issues"] == 2
    assert EV.expected_severities(s3) == {"none", "low"}
    assert EV.case_snapshot(s1, NET) == lab.s1 and AN.intact(EV.case_snapshot(s1, NET))
    assert {x["id"]: x["why"] for x in got["skipped"]} == {
        lab.s0["id"]: f"no planted issue stood on the sheet at its collection "
                      f"({_iso(T0 - 3600)}) and --clean does not name it",
        lab.s4["id"]: f"the snapshot {lab.s4['id']} changed since it was kept (its hash does "
                      "not match), so it is not analysed"}
    other = EV.load_hardware(lab.copy, "Branch", clean=[])
    assert other["cases"] == [] and len(other["skipped"]) == 5
    assert all("of the network 'Default', not" in x["why"] for x in other["skipped"]
               if x["id"] != lab.s4["id"])
    assert EV.load_hardware(lab.copy, NET, clean=["snap-0000000000000000"])["error"] == (
        f"--clean names snap-0000000000000000, which {lab.copy}/snapshots/ does not hold")


def test_a_clean_case_is_named_by_why_it_is_clean(lab, tmp_path):
    """C3029: S0 was collected before any issue was planted, S3 with two standing on the sheet;
    each named clean reads as what it is, never both as "every planted issue restored". A copy
    whose sheet holds no issue says that."""
    import shutil

    got = EV.load_hardware(lab.copy, NET, clean=[lab.s0["id"], lab.s3["id"]])
    assert got["error"] == ""
    assert {c["key"]: c["name"] for c in got["cases"] if c["clean"]} == {
        lab.s0["id"]: "clean: collected before any issue was planted",
        lab.s3["id"]: "clean: every planted issue restored"}
    s0 = got["cases"][0]
    assert s0["key"] == lab.s0["id"], "the earliest collection first"
    assert s0["sheet_issues"] == 0 and EV.case_issues(s0) == [] and EV.kind_of(s0) == "benign"
    bare = tmp_path / "bare" / "sdn_analyst"
    shutil.copytree(lab.copy, bare)
    os.remove(bare / "planted.json")
    none = EV.load_hardware(str(bare), NET, clean=[lab.s0["id"]], keys=[lab.s0["id"]])
    assert [c["name"] for c in none["cases"]] == ["clean: no issue is on the sheet"]


def test_a_hardware_run_on_fake_arms_scores_each_issue_by_b1_s_rule(lab):
    """The baseline cites A only (S1's one issue found, S2 misses B) and calls the clean S3's
    port 3 a medium threat; the technique cites every standing issue and answers S3 with
    nothing. The removed C's evidence cited on S1 is a false positive: C is no issue."""
    from modules.sdn import evaluations

    clean = lab.s3["id"]

    def finding_of(evidence, severity):
        return {"severity": severity, "finding": f"about {evidence}", "why": "w",
                "evidence": [evidence]}

    def baseline(network, snap, **kw):
        return {"ok": True, "call_id": "", "findings": [
            finding_of(PORT3, "medium" if snap["id"] == clean else "high")]}

    def tools(network, snap, **kw):
        (drop,) = [i for i in AN.evidence_ids(snap) if i.startswith("drop:")]
        found = [finding_of(PORT3, "high"), finding_of(drop, "high")]
        if snap["id"] == lab.s1["id"]:
            found.append(finding_of(RATE2, "medium"))
        return {"ok": True, "calls": [], "findings": [] if snap["id"] == clean else found}

    before = _tree(lab.store), _tree(lab.copy)
    picked = EV.load_hardware(lab.copy, NET, clean=[clean])["cases"]
    actor = "evaluation:b4-hardware"
    results = EV.run(picked, {"baseline": baseline, "tools": tools}, runs=1, network=NET,
                     actor=actor, trigger={}, now=lambda: float(T0 + 20000))
    rows = {c["key"]: c for c in results["cases"]}
    one = rows[lab.s1["id"]]["runs"]
    assert (one["baseline"][0]["missed"], one["baseline"][0]["missed_issues"],
            one["baseline"][0]["correct"]) == (False, [], True)
    assert (one["tools"][0]["found"], one["tools"][0]["correct"],
            one["tools"][0]["judged"]) == (True, True, ["planted", "real", "false_positive"])
    two = rows[lab.s2["id"]]["runs"]
    assert two["baseline"][0]["missed_issues"] == ["A stale drop"] and two["tools"][0]["correct"]
    three = rows[clean]["runs"]
    assert three["baseline"][0]["threat_answered"] and not three["baseline"][0]["correct"]
    assert three["tools"][0]["correct"] and not three["tools"][0]["threat_answered"]
    s = EV.summary(results)["roles"]["hardware"]
    b, t = s["techniques"]["baseline"], s["techniques"]["tools"]
    assert (s["cases"], b["reliable"], t["reliable"]) == (3, 1, 3)
    assert (b["misses"], t["misses"], b["benign_threat_runs"], t["benign_threat_runs"],
            b["false_positives"], t["false_positives"]) == (1, 0, 1, 0, 0, 1)
    assert EV.summary(results)["pass_rule"]["improves"] is None, "the blind role alone decides"
    kept = evaluations.read(NET)["rows"]
    assert [(r["case"], r["role"], r["technique"], r["missed_issues"], r["issue"],
             r["false_positives"], r["threat_answered"]) for r in kept] == [
        (lab.s1["id"], "hardware", "tools", [], [PORT3], 1, False),
        (lab.s2["id"], "hardware", "baseline", ["A stale drop"], [DROPS], 0, False),
        (clean, "hardware", "baseline", [], [], 0, True)]
    assert (_tree(lab.store), _tree(lab.copy)) == before, "neither folder is written"


def test_the_estimate_counts_the_hardware_cases_and_a_run_reports_them(lab, tmp_path):
    from modules.ai import sdn_analyst_tools as AT2

    said = []
    argv = ["--list", NET, "--runs", "1", "--roles", "hardware", "--snapshots", lab.copy,
            "--clean", lab.s3["id"], "--out", str(tmp_path / "out")]
    assert EV.main(argv, arms={}, root=ROOT, out=said.append) == 2
    usd = sum(AN.estimate(s)["usd"] + AT2.estimate(s)["usd"] for s in (lab.s1, lab.s2, lab.s3))
    assert (f"nmas-sdn-b4-eval: skipped the snapshot {lab.s4['id']}: the snapshot "
            in "\n".join(said))
    assert any(w.startswith(f"nmas-sdn-b4-eval: skipped the snapshot {lab.s0['id']}: no planted")
               for w in said)
    assert (f"nmas-sdn-b4-eval: 3 cases (3 of them the lab hardware's snapshots) x 1 runs x 2 "
            f"techniques: at most 9 calls, about ${round(usd, 4):.4f}") in "\n".join(said)
    assert "refused: nothing was asked or spent" in said[-1]

    def arm(network, snap, **kw):
        return {"ok": True, "call_id": "", "calls": [], "findings": []}
    said.clear()
    assert EV.main(argv + ["--yes-spend", "--actor", "evaluation:b4-hw"],
                   arms={"baseline": arm, "tools": arm}, root=ROOT, out=said.append) == 0
    md = open(tmp_path / "out" / "b4-eval-b4-hw.md", encoding="utf-8").read()
    data = json.load(open(tmp_path / "out" / "b4-eval-b4-hw.json", encoding="utf-8"))
    assert "## hardware (not blind)" in md and "- Cases: 0 from 19.13's files" in md
    assert f"- Hardware: 3 snapshots kept on the lab's switches, from {lab.copy} (1 named " \
           f"clean); skipped 2" in md
    assert data["summary"]["hardware"]["clean_with_issues"] == [
        {"id": lab.s3["id"], "standing": 2}], "A and B are still on the sheet at S3"
    assert (f"; {lab.s3['id']} named clean, with 2 issues standing on the sheet: scored "
            "benign\n") in md, "A and B are still on the sheet when S3 was collected"
    assert f"| {lab.s3['id']} | hardware | benign | 1 of 1 | 1 of 1 |" in md
    assert f"| {lab.s1['id']} | hardware | threat | 0 of 1 | 0 of 1 |" in md
    assert data["meta"]["estimate"]["hardware"] == 3
    assert [x["id"] for x in data["summary"]["hardware"]["skipped"]] == sorted(
        [lab.s0["id"], lab.s4["id"]])


@pytest.mark.parametrize("extra, words", [
    (["--roles", "hardware"], "--roles names hardware, and no --snapshots folder is given"),
    (["--snapshots", ROOT + "/data/x"], "is inside the checkout; copy the network's"),
    (["--snapshots", "/tmp/elsewhere", "--roles", "recorded"], "leaves out hardware"),
    (["--clean", "snap-0000000000000000"], "--clean names snapshots, and no --snapshots"),
    (["--roles", "recorded,hardwear"], "--roles names hardwear, not one of"),
])
def test_a_hardware_run_out_of_shape_is_refused(networks, extra, words):  # noqa: F811
    said = []
    got = EV.main(["--list", NET, "--out", "/tmp/elsewhere"] + extra, arms={}, root=ROOT,
                  out=said.append)
    assert got == 2 and words in said[-1]


# ── the Lab 9 sitting's cases (the role "sitting") ────────────────────────────────────────────
#
# What the analyst got wrong on the lab's hardware on 2026-11-10, modelled on the analyst tests'
# own fabric (tests/sdn_sitting_cases.py builds the file from the recorded controller, flows and
# hosts planted; nothing of the lab's): a planted misdirected flow B1 missed, and a pair of DHCP
# flows with disjoint matches both techniques reported as a conflict; each in IPv4 and IPv6.

SITTING_KEYS = ["misdirected-icmp-ipv4", "misdirected-icmp-ipv6", "dhcp-disjoint-ipv4",
                "dhcp-disjoint-ipv6"]
OVS4, FAR_EDGE = "0000000000000004", "0000029625637b84"


def test_the_sitting_s_cases_are_what_the_test_fabric_builds_each_a_sealed_whole_snapshot(world):  # noqa: F811
    import re

    from modules.sdn import flow_ops
    from tests import sdn_sitting_cases as SC

    loaded = EV.load_cases(ROOT, ["sitting"])
    assert [c["key"] for c in loaded] == SITTING_KEYS
    assert "sitting" in EV.ROLES and EV.FIXTURE_ROLES == EV.ROLES_1913 + ("sitting",)
    with open(os.path.join(ROOT, SC.FILE), encoding="utf-8") as fh:
        text = fh.read()
    assert text == SC.text(), "the file is what tests/sdn_sitting_cases.py builds, never typed"
    # Nothing of a lab: documentation addresses, the limited broadcast DHCP is sent to, and the
    # recording's own placeholder for its controller.
    quads = set(re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text))
    assert quads and all(q.startswith("198.51.100.") or q == "255.255.255.255" for q in quads)
    assert json.loads(text)["model"] == profiles.task("sdn_analyse")["model"]
    for case in loaded:
        assert case["role"] == "sitting" and "the Lab 9 sitting of 2026-11-10" in case["about"]
        snap = EV.case_snapshot(case, NET)
        assert AN.intact(snap) and snap["network"] == NET
        assert (len(snap["switches"]), len(snap["links"]), len(snap["hosts"])) == (5, 5, 3)
        assert not any(s.get("partial") for s in snap["switches"]), "its tables are whole"
        ids, facts = AN.evidence_ids(snap), AN.facts(snap)
        if EV.kind_of(case) == "threat":
            (issue,) = EV.case_issues(case)
            (planted,) = issue["evidence"]
            assert planted in ids and planted.startswith(f"flow:ctl-1:{OVS4}:t0:p200:")
            line = next(ln for ln in facts.splitlines() if ln.startswith(planted + " "))
            dst = "ipv6_dst=2001:db8::20" if "ipv6" in case["key"] else "ipv4_dst=198.51.100.20"
            assert dst in line and "actions OUTPUT:3" in line
            # The fabric's own links and flows say where that host is: every other flow for
            # it on the switch leaves by port 1, the link to the switch it is on.
            others = [ln for ln in facts.splitlines()
                      if ln.startswith(f"flow:ctl-1:{OVS4}:") and dst in ln and ln != line]
            assert others and all("actions OUTPUT:1," in ln for ln in others)
            assert {f"link:ctl-1:{OVS4}:1-{FAR_EDGE}:18",
                    f"link:ctl-1:{OVS4}:3-00c802d5027901e6:3"} <= ids
            assert any(h["dpid_hex"] == FAR_EDGE and (h["ipv4"], h["ipv6"]) ==
                       (["198.51.100.20"], ["2001:db8::20"]) for h in snap["hosts"])
        else:
            assert EV.kind_of(case) == "benign" and EV.case_issues(case) == []
            ((drop, request),) = EV.disjoint_groups(case)
            assert drop.startswith(f"drop:ctl-1:{FAR_EDGE}:") and {drop, request} <= ids
            edge = next(s for s in snap["switches"] if s["dpid_hex"] == FAR_EDGE)
            dropped = next(f for f in edge["drops"] if f["id"] == drop)["match"]
            forwarded = next(f for f in edge["flows"] if f["id"] == request)["match"]
            assert flow_ops.disjoint(dropped, forwarded), "no packet matches both"
            ports = (547, 546) if "ipv6" in case["key"] else (67, 68)
            assert (dropped["udp_src"], dropped["udp_dst"]) == ports
            assert forwarded["udp_dst"] == ports[0] and "udp_src" not in forwarded


def test_a_sitting_case_is_scored_by_the_flow_it_plants_or_the_pair_it_names_disjoint(world):  # noqa: F811
    by = {c["key"]: c for c in EV.load_cases(ROOT, ["sitting"])}
    assert sorted(by) == sorted(SITTING_KEYS)
    port3 = f"port:ctl-1:{OVS3}:3"

    def scored(case, *findings):
        return EV.score_run(case, EV.case_snapshot(case, NET),
                            {"ok": True, "findings": list(findings)})

    for key in ("misdirected-icmp-ipv4", "misdirected-icmp-ipv6"):
        (flow,) = EV.case_issues(by[key])[0]["evidence"]
        # The sitting's miss: the recording's down port reported, the planted flow not.
        missed = scored(by[key], finding([port3], "high", "Port 3 is down"))
        assert missed["missed"] and missed["correct"] is False
        found = scored(by[key], finding([flow], "medium", "ICMP for the host leaves by port 3"))
        assert found["found"] and found["correct"] is True and not found["missed"]
        noted = scored(by[key], finding([flow], "info", "A flow for ICMP"))
        assert noted["found"] and noted["correct"] is False, "info is not a finding of it"
    for key in ("dhcp-disjoint-ipv4", "dhcp-disjoint-ipv6"):
        ((drop, request),) = EV.disjoint_groups(by[key])
        # The sitting's false positive, at any severity above info.
        conflict = scored(by[key], finding([drop, request], "low",
                                           "The drop flow conflicts with the DHCP forward"))
        assert conflict["threat_answered"] and conflict["false_conflicts"] == 1
        assert conflict["correct"] is False
        # Each flow reported apart, the recording's down port, and a note citing both: correct.
        apart = scored(by[key], finding([drop], "high", "A drop flow that matched no packet"),
                       finding([port3], "high", "Port 3 is down"),
                       finding([request], "medium", "DHCP requests are rewritten"),
                       finding([drop, request], "info", "DHCP is steered on this port"))
        assert apart["correct"] is True and not apart["threat_answered"]
        assert apart["false_conflicts"] == 0
    # 19.13's benign cases name no disjoint flows: judged by severity alone, as before.
    (normal,) = cases("normal-2")
    assert EV.disjoint_groups(normal) == []
    quiet = scored(normal, finding(["rate:lab:0000000000000001:3"], "low", "A quiet port"))
    assert quiet["correct"] is True and quiet["false_conflicts"] == 0


def test_the_sitting_s_cases_run_as_their_own_role_and_each_wrong_run_is_kept(world, tmp_path):  # noqa: F811
    from modules import history_export
    from modules.sdn import evaluations

    loaded = EV.load_cases(ROOT, ["sitting"])
    by_snap = {EV.case_snapshot(c, NET)["id"]: c for c in loaded}
    assert len(by_snap) == 4
    port3 = f"port:ctl-1:{OVS3}:3"

    def as_at_the_sitting(network, snap, **kw):
        """Misses the planted flow; sets the DHCP pair against each other."""
        groups = EV.disjoint_groups(by_snap[snap["id"]])
        cited = groups[0] if groups else [port3]
        return {"ok": True, "call_id": "", "calls": [],
                "findings": [finding(cited, "medium", "As answered at the sitting")]}

    def right(network, snap, **kw):
        issues = EV.case_issues(by_snap[snap["id"]])
        found = [finding(issues[0]["evidence"], "high", "The misdirected flow")] if issues else []
        return {"ok": True, "call_id": "", "calls": [], "findings": found}

    said = []
    argv = ["--list", NET, "--runs", "1", "--roles", "sitting", "--out", str(tmp_path / "out")]
    arms = {"baseline": as_at_the_sitting, "tools": right}
    assert EV.main(argv, arms=arms, root=ROOT, out=said.append) == 2
    assert any("4 cases (0 of them the lab hardware's snapshots) x 1 runs x 2 techniques: at "
               "most 12 calls" in w for w in said)
    assert EV.main(argv + ["--yes-spend", "--actor", "evaluation:b4-sitting"], arms=arms,
                   root=ROOT, out=said.append) == 0
    md = open(tmp_path / "out" / "b4-eval-b4-sitting.md", encoding="utf-8").read()
    data = json.load(open(tmp_path / "out" / "b4-eval-b4-sitting.json", encoding="utf-8"))
    assert "## sitting (not blind)" in md and "- Cases: 0 from 19.13's files" in md
    assert "- The Lab 9 sitting's cases: 4, modelled on the test fabric" in md
    assert "| misdirected-icmp-ipv4 | sitting | threat | 0 of 1 | 1 of 1 |" in md
    assert "| dhcp-disjoint-ipv6 | sitting | benign | 0 of 1 | 1 of 1 |" in md
    role = data["summary"]["roles"]["sitting"]
    b, t = role["techniques"]["baseline"], role["techniques"]["tools"]
    assert (role["cases"], b["reliable"], t["reliable"]) == (4, 0, 4)
    assert (b["misses"], b["benign_threat_runs"], t["misses"], t["benign_threat_runs"]) == \
        (2, 2, 0, 0)
    assert data["summary"]["pass_rule"]["improves"] is None, "the blind role alone decides"
    kept = evaluations.read(NET)["rows"]
    assert [(r["case"], r["role"], r["technique"], r["missed"], r["threat_answered"],
             r["false_conflicts"]) for r in kept] == [
        ("misdirected-icmp-ipv4", "sitting", "baseline", True, False, 0),
        ("misdirected-icmp-ipv6", "sitting", "baseline", True, False, 0),
        ("dhcp-disjoint-ipv4", "sitting", "baseline", False, True, 1),
        ("dhcp-disjoint-ipv6", "sitting", "baseline", False, True, 1)]
    conflict = kept[2]
    assert conflict["disjoint"] == EV.disjoint_groups(by_snap[conflict["snapshot"]])
    (row,) = [r for r in history_export._b4_rows(NET, conflict)
              if r["kind"] == "eval_benign_threat"]
    assert row["expected"].startswith("no finding above info citing both flows of a pair whose "
                                      "matches are disjoint: drop:ctl-1:")
    assert AN._latest(NET) == {}, "the network's analyst store is untouched"
