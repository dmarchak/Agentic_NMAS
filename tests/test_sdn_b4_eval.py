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
from tests.test_sdn_analyst import NET, world  # noqa: F401 (the fixture)
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
