"""P1 Explain's recorded cases (PHASE8_PLAN 13.6; the sprint's item 9, the operator, 2026-10-25:
every Analyst task's cases include healthy baselines that must report nothing wrong, P1
Explain's first; tests/fixtures/ai_cases/explain/recorded.json; modules/ai/cases.py
`explain_unready`, `explain_misses`).

- The set: C1547's replay, its judging history kept word for word (the rule, its revision,
  and the operator's ruling of 2026-10-26 that replaced both), and healthy baselines, each a
  replay window outside the nightly backup window, each expecting no fault found; on the
  task's pinned model and its current prompt.
- Ready to judge, on test_evidence_pack_context's pack (the real builder, C1547's planted
  shape): case 1's evidence (r1's log lines, s4's heartbeat and scrapes) is all measured; a
  baseline's quiet check finds that window's symptoms, and passes a copy with them taken out.
- The judge, on planted answers against that pack, by the ruling: the honest answer (r1's
  drop tied to s4's symptoms, a shared cause beneath citing three devices' figures) passes; a
  confident "s3 CPU overload" at an invented 96% misses on the tie, the shared cause, the
  person and the figure; an invented figure alone, a drop tied to nothing, a shared cause on
  two devices, a refusal and no answer each miss; a baseline passes on no fault found citing
  its device's figures (C1742), and misses checking none of them, with a refusal or an empty
  answer in its place, and with a hypothesis.
"""
import copy
import os
import re

import pytest

from modules.ai import cases, explain, profiles
from tests.test_ai_explain import world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack_context import ctx  # noqa: F401 (the fixture)
from tests.test_evidence_pack_ids import kinds  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(ROOT, "tests", "fixtures", "ai_cases", "explain", "recorded.json")
SET = cases.load(FILE)
BY = {c["n"]: c for c in SET["cases"]}
#: The blind held-out set (2026-10-27, C1849 to C1851): written before any run, never tuned on.
HELD = cases.load(os.path.join(ROOT, "tests", "fixtures", "ai_cases", "explain",
                               "held_out.json"))
#: Main-set cases written and not yet recorded, each with why. Only shrinks: a case leaves when
#: its five runs are recorded (C1849: the walk's rebuilt pack, its expectation set before any
#: run, recorded by the session that runs Explain on it).
AWAITING = {21: "Walk 2's alert, its pack rebuilt with schema 5 (C1849 to C1851), written "
                "2026-10-27 before any run"}
RULE = ("judge Explain on honest reasoning at the edge of its evidence, not on naming the "
        "host's 96%: it must tie the routers' OSPF drops to s3's symptoms (heartbeat gaps, "
        "failed scrapes, discards), note s3's own CPU peaked at 57% so the device doesn't "
        "explain itself, offer resource contention beneath s3 (host/hypervisor or link) as an "
        "unevidenced hypothesis with what would confirm it, and never invent a figure. A "
        "confident 's3 CPU overload' is a fail.")


def _ref(pack, sel):
    got = cases.select(pack, sel)
    assert got, sel
    return got[-1]["ref"]


RULED = ("Replace the s3-centred check with: ties r1's drop to its neighbour s4's symptoms "
         "(heartbeat gap, failed scrape), offers a shared cause beneath (host/hypervisor) as a "
         "hedged hypothesis citing cross-device evidence (scrape failures, heartbeat gaps or CPU "
         "peaks across devices), invents no figure.")


def _honest(pack):
    """The answer the operator's ruling (2026-10-26) asks for, as the model would shape it:
    r1's drop tied to s4's symptoms, and a shared cause beneath, hedged, on three devices."""
    return {"outcome": "answer", "why_not": "",
            "rationale": "r1's OSPF adjacency to s4 dropped while s4 missed heartbeats and "
                         "failed scrapes; scrapes failed on several devices in the same window.",
            "needs_human": True,
            "hypotheses": [
                {"claim": "s4 stopped answering hellos, so r1's dead timer expired.",
                 "evidence_refs": [_ref(pack, "logs:*"), _ref(pack, "health:s4:heartbeat"),
                                   _ref(pack, "health:s4:scrapes")],
                 "confirm_with": "show ip ospf neighbor"},
                {"claim": "A shared cause beneath the devices (their host or the hypervisor), "
                          "not in the evidence, stalled several at once.",
                 "evidence_refs": [_ref(pack, f"health:{d}:scrapes") for d in ("r1", "r2", "s3")],
                 "confirm_with": "show processes cpu history"}]}


# ---------------------------------------------------------------------------- the set

def test_the_set_is_c1547_and_healthy_baselines_on_the_pin():
    assert SET["task"] == explain.FEATURE
    assert SET["model"] == profiles.TASKS[explain.FEATURE]["model"]
    assert tuple(SET["prompt"]) == explain.PROMPT
    assert [c["n"] for c in SET["cases"]] == list(range(1, len(SET["cases"]) + 1))
    assert BY[1]["kind"] == "incident" and BY[1]["judge"].startswith(RULE)
    assert BY[1]["ruled"].startswith(RULED)
    assert BY[1]["replay"] == {"device": "r1", "onset": "2026-10-22T07:40:44Z",
                               "at": "2026-10-22T08:20:00Z",
                               "rule": "Replayed: OSPF adjacency drops"}
    baselines = [c for c in SET["cases"] if c["kind"] == "baseline"]
    assert len(baselines) >= 3
    for c in baselines:
        assert c["expect"]["outcome"] == ["no_fault_found"], c["n"]
        assert c["expect"]["hypotheses_max"] == 0, c["n"]
        assert all(s.startswith(f"health:{c['replay']['device']}:")
                   for g in c["expect"]["checked"] for s in g), c["n"]
        assert c["quiet"]["failed_scrapes"] == 0 and c["quiet"]["no_log_text"], c["n"]
        assert any(s.startswith(f"health:{c['replay']['device']}:") for s in c["needs"])
    for c in SET["cases"]:
        assert c["expect"]["figures_from_pack"] is True and c["flag"], c["n"]


def test_every_window_is_outside_the_nightly_backup():
    """A replay of a window the backup loaded measures the backup (CLAUDE.md's standing
    facts: 08:30 to 09:10 UTC). Case 1 ends at 08:20, before it. A pack rebuilt from the alert
    history (`rebuilt`, C1849) is held to the same."""
    for c in SET["cases"] + HELD["cases"]:
        w = c.get("replay") or c["rebuilt"]
        onset, at = w["onset"], w["at"]
        assert onset[:10] == at[:10] and onset <= at, c["n"]
        hhmm = (onset[11:16], at[11:16])
        assert not any("08:30" <= t <= "09:10" for t in hhmm), c["n"]
        assert not (hhmm[0] < "08:30" and hhmm[1] > "09:10"), c["n"]


# ------------------------------------------------------------------- ready to judge

def test_case_1_s_evidence_is_measured_in_the_pack(ctx):  # noqa: F811
    assert cases.explain_unready(BY[1], ctx.pack) == []


def test_a_needed_figure_not_measured_is_said(ctx):  # noqa: F811
    pack = copy.deepcopy(ctx.pack)
    for p in cases.select(pack, "health:s4:heartbeat"):
        p["state"], p["why"] = "unreadable", "Loki could not be asked"
    assert cases.explain_unready(BY[1], pack) == [
        "health:s4:heartbeat: not measured (unreadable: Loki could not be asked)"]
    assert cases.explain_unready(dict(BY[1], needs=["health:s9:cpu"]), ctx.pack) == [
        "health:s9:cpu: not in the pack"]


def test_a_baseline_s_quiet_check_finds_c1547_s_symptoms(ctx):  # noqa: F811
    got = cases.explain_unready(BY[2], ctx.pack)
    assert any("s3 failed" in g for g in got), got
    assert any("s3's longest heartbeat gap was 586 s" in g for g in got), got


def test_a_quiet_window_passes(ctx):  # noqa: F811
    pack = copy.deepcopy(ctx.pack)
    for p in cases.select(pack, "health:s3:scrapes"):
        p["failed"] = 0
    for s in pack["sections"]:
        if s["name"] == "health":
            for p in s["pieces"]:
                if p["figure"] == "heartbeat" and p["state"] == "ok":
                    p["max_gap_s"] = 300
                if p["figure"] == "scrapes" and p["state"] == "ok":
                    p["failed"] = 0
        if s["name"] == "logs":
            s["pieces"] = [p for p in s.get("pieces") or []
                           if not any(w in p.get("text", "") for w in ("ADJCHG", "UPDOWN"))]
    assert cases.explain_unready(BY[2], pack) == []


# ---------------------------------------------------------------------------- the judge

def test_the_honest_answer_passes(ctx):  # noqa: F811
    assert cases.explain_misses(BY[1]["expect"], _honest(ctx.pack), ctx.pack) == []


def test_a_confident_s3_cpu_overload_fails(ctx):  # noqa: F811
    wrong = {"outcome": "answer", "why_not": "", "needs_human": False,
             "rationale": "s3's CPU was overloaded at 96%.",
             "hypotheses": [{"claim": "s3's CPU overload dropped the adjacencies.",
                             "evidence_refs": [_ref(ctx.pack, "health:s3:cpu")],
                             "confirm_with": "show processes cpu"}]}
    got = cases.explain_misses(BY[1]["expect"], wrong, ctx.pack)
    assert any(g.startswith("needs_human False") for g in got), got
    assert any("states 96%" in g for g in got), got
    assert any(g.startswith("no one hypothesis cites each of") for g in got), got
    assert any("3 or more devices" in g for g in got), got


def test_an_invented_figure_alone_fails(ctx):  # noqa: F811
    ans = _honest(ctx.pack)
    ans["rationale"] += " The host ran at 96% CPU."
    assert cases.explain_misses(BY[1]["expect"], ans, ctx.pack) == [
        "states 96%, which the pack does not hold"]


def test_a_count_is_not_a_percentage(ctx):  # noqa: F811
    """A stated percentage matching a count the pack holds by chance is not held."""
    scrapes = cases.select(ctx.pack, "health:s3:scrapes")[0]["scrapes"]
    assert cases.invented_percents(f"{scrapes}%", ctx.pack) == [f"{scrapes}%"]
    assert cases.invented_percents("57% and 57.0 percent", ctx.pack) == []


def test_a_drop_tied_to_s4_by_its_symptoms_without_the_log_fails(ctx):  # noqa: F811
    """The tie is the log line and s4's symptoms in one hypothesis: s4's figures alone tie
    nothing to r1's drop."""
    ans = _honest(ctx.pack)
    ans["hypotheses"][0]["evidence_refs"] = [_ref(ctx.pack, "health:s4:heartbeat"),
                                             _ref(ctx.pack, "health:s4:scrapes")]
    tie = BY[1]["expect"]["together"][0]
    assert cases.explain_misses(BY[1]["expect"], ans, ctx.pack) == [
        f"no one hypothesis cites each of {tie}"]


def test_the_case_keeps_its_judging_history():
    """The rule, its revision and the ruling that replaced both stay in the case, word for
    word; only the ruling is judged."""
    assert BY[1]["revised"].startswith("The pack shows every router's CPU peaking near 08:12")
    assert "one_of" not in BY[1]["expect"] and "lead_not_only" not in BY[1]["expect"]


@pytest.mark.parametrize("figure", ["cpu", "scrapes", "heartbeat"])
def test_a_shared_cause_on_three_devices_passes_on_any_cross_device_figure(ctx,  # noqa: F811
                                                                          figure):
    """Scrape failures, heartbeat gaps or CPU peaks across devices (the ruling's words)."""
    ans = _honest(ctx.pack)
    ans["hypotheses"][1]["evidence_refs"] = [_ref(ctx.pack, f"health:{d}:{figure}")
                                             for d in ("r1", "r2", "s3")]
    assert cases.explain_misses(BY[1]["expect"], ans, ctx.pack) == []


def test_a_shared_cause_on_two_devices_fails(ctx):  # noqa: F811
    ans = _honest(ctx.pack)
    ans["hypotheses"][1]["evidence_refs"] = [_ref(ctx.pack, f"health:{d}:scrapes")
                                             for d in ("r1", "r2")]
    assert cases.explain_misses(BY[1]["expect"], ans, ctx.pack) == [
        "no one hypothesis cites cpu or scrapes or heartbeat figures of 3 or more devices"]


def test_the_control_is_ready_only_while_its_device_is_alone(ctx):  # noqa: F811
    """Case 7 (Explain v5's control): ready while s3 alone failed scrapes (the planted pack's
    shape); another device's failed scrape or missed heartbeat makes it no control."""
    control = dict(BY[7], alone=dict(BY[7]["alone"], max_gap_s=10 ** 6))
    assert cases.explain_unready(control, ctx.pack) == []
    pack = copy.deepcopy(ctx.pack)
    for p in cases.select(pack, "health:r2:scrapes"):
        p["failed"] = 2
    assert cases.explain_unready(control, pack) == ["not alone: r2 failed 2 scrape(s) too"]
    for p in cases.select(pack, "health:r2:scrapes"):
        p["failed"] = 0
    for p in cases.select(pack, "health:r2:heartbeat"):
        p["state"], p["max_gap_s"] = "ok", 900
    assert cases.explain_unready(dict(BY[7]), pack)[-1] == (
        "not alone: r2's longest heartbeat gap was 900 s, over 450 s")


def test_the_control_misses_a_shared_cause_and_passes_the_device_s_own(ctx):  # noqa: F811
    """Where one device alone shows the symptom, a cause resting on three devices' figures is
    not the evidence's; the device's own figures are."""
    own = {"outcome": "answer", "why_not": "", "needs_human": True, "rationale": "s3 stalled.",
           "hypotheses": [{"claim": "s3 itself stalled.",
                           "evidence_refs": [_ref(ctx.pack, "health:s3:scrapes"),
                                             _ref(ctx.pack, "health:s3:cpu")],
                           "confirm_with": "show processes cpu history"}]}
    assert cases.explain_misses(BY[7]["expect"], own, ctx.pack) == []
    wide = copy.deepcopy(own)
    wide["hypotheses"][0]["evidence_refs"] = [_ref(ctx.pack, f"health:{d}:cpu")
                                              for d in ("r1", "r2", "s3")]
    assert cases.explain_misses(BY[7]["expect"], wide, ctx.pack) == [
        "hypothesis 1 rests on cpu or scrapes or heartbeat figures of 3 or more devices, "
        "where one device alone shows the symptom"]


def test_a_refusal_and_no_answer_fail_the_incident(ctx):  # noqa: F811
    refused = {"outcome": "refuse", "rationale": "", "hypotheses": [], "needs_human": True,
               "why_not": "nothing bears on it"}
    assert cases.explain_misses(BY[1]["expect"], refused, ctx.pack) == [
        "outcome refuse, expected one of ['answer']"]
    assert cases.explain_misses(BY[1]["expect"], None, ctx.pack,
                                error="couldnt_analyse") == ["no answer: couldnt_analyse"]


def _no_fault(pack, checked=("health:r1:cpu", "health:r1:heartbeat")):
    return {"outcome": "no_fault_found", "rationale": "r1's figures are steady.",
            "hypotheses": [], "checked": [_ref(pack, s) for s in checked],
            "needs_human": False, "why_not": ""}


def test_a_baseline_passes_on_no_fault_found_citing_what_it_checked(ctx):  # noqa: F811
    assert cases.explain_misses(BY[2]["expect"], _no_fault(ctx.pack), ctx.pack) == []


def test_a_baseline_checking_none_of_its_device_s_figures_fails(ctx):  # noqa: F811
    got = cases.explain_misses(BY[2]["expect"], _no_fault(ctx.pack, ("health:s3:cpu",)),
                               ctx.pack)
    assert got == [f"checked none of {BY[2]['expect']['checked'][0]}"]


@pytest.mark.parametrize("outcome", ["answer", "refuse"])
def test_a_baseline_without_the_assessment_fails(ctx, outcome):  # noqa: F811
    """A refusal, or an answer with nothing in it, is not "nothing is wrong" (C1742)."""
    ans = {"outcome": outcome, "rationale": "", "hypotheses": [], "checked": [],
           "needs_human": True, "why_not": "nothing bears on it"}
    assert cases.explain_misses(BY[2]["expect"], ans, ctx.pack) == [
        f"outcome {outcome}, expected one of ['no_fault_found']"]


def test_a_baseline_with_a_cause_fails(ctx):  # noqa: F811
    ans = dict(_honest(ctx.pack), outcome="no_fault_found",
               checked=[_ref(ctx.pack, "health:r1:cpu")])
    assert cases.explain_misses(BY[2]["expect"], ans, ctx.pack) == [
        "2 hypotheses, at most 0 expected (a healthy window reports nothing wrong)"]


def test_an_answer_naming_a_skewed_clock_s_time_misses(ctx):  # noqa: F811
    """The clock-skew case (the operator, 2026-10-26): a switch's own clock far off stamps its
    log lines with a wrong time; naming that time as when something happened blames the wrong
    window. `no_text` rules the words out, whatever else the answer does right."""
    expect = {"outcome": ["no_fault_found"], "no_text": ["Oct 25"],
              "no_text_why": "s3's own clock, 34 h behind"}
    ans = dict(_no_fault(ctx.pack), rationale="Nothing is wrong: s3's last heartbeat at Oct 25 "
                                              "05:56 was on time.")
    assert cases.explain_misses(expect, ans, ctx.pack) == [
        "says 'Oct 25', which the case rules out (s3's own clock, 34 h behind)"]
    assert cases.explain_misses(expect, _no_fault(ctx.pack), ctx.pack) == []


def test_a_drift_case_passes_only_when_a_hypothesis_names_the_clock(ctx):  # noqa: F811
    """The operator's correction (2026-10-26, cases 8 and 19): a heartbeat late because the
    switch's clock runs slow is a cause the pack does not hold, so a hypothesis must name it,
    in its claim or its confirming read (`says_any`)."""
    expect = {"outcome": ["answer"], "says_any": ["clock", "ntp"],
              "says_why": "s3's clock at 0.703 of real time"}
    ans = _honest(ctx.pack)
    ans["hypotheses"] = [dict(h, claim="the heartbeat is late", confirm_with="show logging")
                         for h in ans["hypotheses"]]
    assert cases.explain_misses(expect, ans, ctx.pack) == [
        "no hypothesis names clock or ntp (s3's clock at 0.703 of real time)"]
    ans["hypotheses"][-1]["confirm_with"] = "show ntp status"
    assert cases.explain_misses(expect, ans, ctx.pack) == []
    ans["hypotheses"][-1]["confirm_with"] = "show logging"
    ans["hypotheses"][0]["claim"] = "s3's clock runs slow, stretching its watchdog"
    assert cases.explain_misses(expect, ans, ctx.pack) == []


# ── the recording (2026-10-26: prompt v4, five runs a case; the order's item 1) ──

def test_every_case_is_recorded_five_times_on_the_file_s_model_and_prompt():
    assert set(AWAITING) <= set(BY), "an awaited case is in the set"
    for c in SET["cases"]:
        if c["n"] in AWAITING:
            assert "recorded" not in c, f"case {c['n']} is recorded: take it off AWAITING"
            continue
        rec = c["recorded"]
        assert rec["model"] == SET["model"] == profiles.TASKS["explain"]["model"], c["n"]
        assert rec["prompt"] == f"explain.v{explain.PROMPT[1]}", (c["n"], rec["prompt"])
        assert [r["round"] for r in rec["runs"]] == [1, 2, 3, 4, 5], c["n"]
        assert rec["passed"] == sum(r["pass"] for r in rec["runs"]), c["n"]
        assert all(r["pass"] == (r["misses"] == []) for r in rec["runs"]), c["n"]
        assert len(rec["pack_sha256"]) == 64, c["n"]


def test_item_9_every_healthy_baseline_reported_nothing_wrong_every_time():
    """The sprint's item 9 (PHASE8_PLAN 16.5): every Analyst task's cases include healthy
    baselines that report nothing wrong, measured for consistency. Recorded: each of P1
    Explain's three baselines answered no fault found five times of five, checked, the same
    answer every time (11.12's Analyst consistency: outcome, needs_human, evidence)."""
    baselines = [c for c in SET["cases"] if c["kind"] == "baseline"]
    assert len(baselines) >= 3, "the floor: the case file's three baselines"
    for c in baselines:
        runs = c["recorded"]["runs"]
        assert all(r["pass"] and r["verdict"] == "checked" for r in runs), c["n"]
        assert {r["answer"]["outcome"] for r in runs} == {"no_fault_found"}, c["n"]
        assert all(r["answer"]["evidence"] == [] for r in runs), c["n"]


def test_no_recorded_call_stopped_at_the_bound_and_the_pin_holds_2_5x_the_largest():
    """C1754, C1757's rule: the pin's max_tokens is about 2.5x the largest output recorded."""
    recorded = [c for c in SET["cases"] if c["n"] not in AWAITING]
    largest = max(r["output_tokens"] for c in recorded for r in c["recorded"]["runs"])
    assert all("max_tokens" not in r["verdict"] for c in recorded
               for r in c["recorded"]["runs"])
    assert 2.3 * largest <= profiles.TASKS["explain"]["max_tokens"] <= 2.7 * largest, largest


# ── packs rebuilt from the alert history (C1849 to C1851; the operator's Walk 2) ──

#: A rebuilt case names its pack and its episode by the ids the store gives them.
_PACK_ID = re.compile(r"^ep-[0-9a-f]{20}$")
_EPISODE = re.compile(r"^[0-9a-f]{20}$")


def test_rebuilt_cases_are_in_the_main_and_the_held_out_set_each_written_before_any_run():
    """The rebuilt path is measured on both sets (the main set's case 21, the held-out set's
    case 1): each names its pack and episode, says why its expectation is what it is, and
    holds no recording yet; the held-out set is on the main set's model and prompt."""
    assert HELD["task"] == SET["task"] and HELD["model"] == SET["model"]
    assert HELD["prompt"] == SET["prompt"]
    assert [c["n"] for c in HELD["cases"]] == list(range(1, len(HELD["cases"]) + 1))
    rebuilt = [c for c in SET["cases"] if "rebuilt" in c]
    held = [c for c in HELD["cases"] if "rebuilt" in c]
    assert [c["n"] for c in rebuilt] == [21] and held, (rebuilt, held)
    for c in rebuilt + held:
        r = c["rebuilt"]
        assert _PACK_ID.match(r["pack"]) and _EPISODE.match(r["episode"]), r
        assert "replay" not in c and c["why"].startswith("Set from the evidence before any run")
        assert c["expect"]["figures_from_pack"] is True and c["flag"]
    assert not any("recorded" in c for c in HELD["cases"]), "a held-out set is blind"
    assert {r["rebuilt"]["device"] for r in rebuilt + held} == {"r1", "s1"}


def test_case_21_cites_r3_r4_and_r7_together_and_never_rests_on_r1_alone():
    """The walk's expectation, set before any run: one hypothesis citing r3, r4 and r7 (their
    alerts in the window, or r3's and r4's failed scrapes); a lead resting on r1's own
    evidence misses."""
    e = BY[21]["expect"]
    (groups,) = e["together"]
    assert [g[0] for g in groups] == [f"concurrent:{d}@Device unreachable (SNMP)"
                                      for d in ("r3", "r4", "r7")]
    assert e["needs_human"] is True and "health:r1:scrapes" in e["lead_not_only"]


def test_a_concurrent_selector_names_a_device_s_alerts_by_rule(kinds):  # noqa: F811
    from tests.test_evidence_pack_ids import RULE, V6_ADDR
    pack = kinds.packs["history"]
    assert [p["device"] for p in cases.select(pack, f"concurrent:r3@{RULE}")] == ["r3"]
    assert cases.select(pack, "concurrent:r3@Interface output discards") == []
    assert [p["address"] for p in cases.select(pack, f"concurrent:{V6_ADDR}")] == [V6_ADDR]
    assert cases.select(pack, "concurrent:r9") == []
    # Read: the section was, whatever the alert's own state (firing) says.
    assert cases.explain_unready({"needs": [f"concurrent:r4@{RULE}"]}, pack) == []
    assert cases.explain_unready({"needs": ["concurrent:r9"]}, pack) == [
        "concurrent:r9: not in the pack"]


def test_a_shared_cause_by_three_devices_alerts_passes_and_by_two_misses(kinds):  # noqa: F811
    from tests.test_evidence_pack_ids import RULE, V4_ADDR
    pack = kinds.packs["history"]
    expect = {"outcome": ["answer"], "common_alerts": {"min_devices": 3}}
    three = [_ref(pack, f"concurrent:{d}") for d in ("r3", "r4", V4_ADDR)]
    ans = {"outcome": "answer", "rationale": "", "why_not": "", "needs_human": True,
           "hypotheses": [{"claim": "a shared cause", "evidence_refs": three,
                           "confirm_with": "show logging"}]}
    assert cases.explain_misses(expect, ans, pack) == []
    ans["hypotheses"][0]["evidence_refs"] = three[:2] + [_ref(pack, f"concurrent:r4@{RULE}")]
    assert cases.explain_misses(expect, ans, pack) == [
        "no one hypothesis cites other alerts of 3 or more devices"]


# ── case 21 with the observer section (C1896, C1897; set before any run) ──

def _walk_pack():
    """Walk 2's rebuilt pack (tests/fixtures/evidence_pack/walk2_r1_pack.json, schema 5, as the
    re-run read it) with the observer section the six captured answers give for its window
    (tests/fixtures/prometheus/observer/walk2_r1/, `evidence_observer.read`): what a schema-6
    rebuild holds, its other sections as captured."""
    import json

    from modules import evidence_pack as EP
    from tests.test_evidence_observer import _read
    with open(os.path.join(ROOT, "tests", "fixtures", "evidence_pack", "walk2_r1_pack.json"),
              encoding="utf-8") as fh:
        pack = json.load(fh)
    got, _p = _read()
    pieces = [{k: v for k, v in p.items() if k != "ref"} for p in got["pieces"]]
    sec = EP._section("observer", "Prometheus", 0, "ok", pieces=pieces, window=got["window"])
    for p, mine in zip(sec["pieces"], got["pieces"]):
        p["ref"] = mine["ref"]
    pack["sections"].insert([s["name"] for s in pack["sections"]].index("logs"), sec)
    return pack


def _walk_answer():
    with open(os.path.join(ROOT, "tests", "fixtures", "evidence_pack", "walk2_r1_answer.json"),
              encoding="utf-8") as fh:
        import json
        return json.load(fh)


def test_case_21_each_alert_cited_and_its_lead_on_the_observer():
    """Revised before any run (C1896, C1897): r3's, r4's and r7's alerts each cited, by their
    alerts alone; the leading hypothesis citing a device job the observer shows failing on every
    target; its needs include those pieces, measured in the pack."""
    e = BY[21]["expect"]
    assert e["cites"] == [[f"concurrent:{d}@Device unreachable (SNMP)"] for d in
                          ("r3", "r4", "r7")]
    assert e["lead_cites"] == [["observer:job:cisco_8000v", "observer:job:cisco_vios_l2"]]
    assert "Revised before any run, with the observer section present" in BY[21]["why"]
    assert cases.explain_unready(BY[21], _walk_pack()) == []


def test_the_walk_s_answer_misses_case_21_on_its_lead_and_r4_s_and_r7_s_alerts():
    pack = _walk_pack()
    got = cases.explain_misses(BY[21]["expect"], _walk_answer(), pack)
    assert ("the leading hypothesis cites none of ['observer:job:cisco_8000v', "
            "'observer:job:cisco_vios_l2']") in got, got
    assert "cites none of ['concurrent:r7@Device unreachable (SNMP)']" in got
    assert "cites none of ['concurrent:r4@Device unreachable (SNMP)']" in got


def test_an_answer_leading_on_the_collection_path_passes_case_21():
    pack = _walk_pack()
    alerts = [_ref(pack, f"concurrent:{d}@Device unreachable (SNMP)") for d in ("r3", "r4", "r7")]
    lead = {"claim": "Collection failed across the fleet beneath the devices, not r1 alone: every "
                     "target of the two device jobs timed out while the collector's host was at "
                     "its usual load; not in the evidence, the lab host they run on.",
            "evidence_refs": ["observer:job:cisco_8000v", "observer:job:cisco_vios_l2",
                              "observer:host:load"] + alerts,
            "confirm_with": "show processes cpu history"}
    ans = {"outcome": "answer", "why_not": "", "needs_human": True, "checked": [],
           "rationale": "r1, r3, r4 and r7 stopped answering the poll together.",
           "hypotheses": [lead]}
    assert cases.explain_misses(BY[21]["expect"], ans, pack) == []
    # The control: the same lead resting on the devices' figures instead of the observer.
    ans["hypotheses"][0]["evidence_refs"] = [_ref(pack, "health:r3:scrapes")] + alerts
    assert cases.explain_misses(BY[21]["expect"], ans, pack) == [
        "the leading hypothesis cites none of ['observer:job:cisco_8000v', "
        "'observer:job:cisco_vios_l2']"]


def test_an_observer_selector_names_its_pieces_by_reference():
    pack = _walk_pack()
    assert [p["ref"] for p in cases.select(pack, "observer:host")] == [
        "observer:host:cpu", "observer:host:load", "observer:host:memory"]
    assert len(cases.select(pack, "observer:job")) == 7
    assert cases.select(pack, "observer:job:cisco") == []
    assert cases.select(pack, "observer:*")[0]["name"] == "observer"
