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

import pytest

from modules.ai import cases, explain, profiles
from tests.test_ai_explain import world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack_context import ctx  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(ROOT, "tests", "fixtures", "ai_cases", "explain", "recorded.json")
SET = cases.load(FILE)
BY = {c["n"]: c for c in SET["cases"]}
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
    facts: 08:30 to 09:10 UTC). Case 1 ends at 08:20, before it."""
    for c in SET["cases"]:
        onset, at = c["replay"]["onset"], c["replay"]["at"]
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
