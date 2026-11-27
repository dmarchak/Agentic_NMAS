"""The incident's story at a glance (the GUI redesign brief §4.1, 2026-11-18;
modules/incident_story.py, templates/v2/_inc_story.html), from the real troubleshooting record of
s5's port-security incident in the Lab 10 demo run (tests/fixtures/incident_story/): the eight
lifecycle stages each from its own record, a self-heal's AI stages skipped, a failed verify said;
the summary's cause from the AI's first hypothesis or "Inconclusive"; the hypotheses; the AI
call from the record of AI calls, or why not; and the partial drawing every part, with its
"needs" lines where Mercury records nothing."""

import json
import re
import os

from modules import incident_story as S

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "fixtures", "incident_story", "hi-ed64c53852c5.fixit.json"),
          encoding="utf-8") as _fh:
    RECORD = json.load(_fh)
LINES = RECORD["lines"]

HEADER = [{"name": "Detected", "state": "at", "at": "2026-11-17T17:53:41Z", "words": ""},
          {"name": "Decided", "state": "at", "at": "2026-11-17T17:58:22Z",
           "words": "can't fix (Tier 3)"},
          {"name": "Fixed", "state": "at", "at": "2026-11-17T18:02:13Z", "words": ""},
          {"name": "Verified", "state": "at", "at": "2026-11-17T18:02:13Z", "words": ""}]
RUN = [{"key": "approve", "since": "2026-11-17T18:01:35Z", "words": "the plan is the one approved"},
       {"key": "send", "since": "2026-11-17T18:01:56Z", "words": "sent"},
       {"key": "verify", "since": "2026-11-17T18:01:56Z", "words": "every check held"}]


def _model(resolved=True, header=HEADER, run=RUN, **fixit):
    return {"resolved": resolved, "header": header, "title": "s5: Gi0/3 err-disabled",
            # The shape incident_page.timeline makes for a fix verified by its run (C4034).
            "ttr": {"seconds": 513, "words": "lasted 8 min 33 s; the fix took 17 s"},
            "todo": {"words": "Approve the plan"},
            "wrong": {"words": ""},
            "fixit": dict({"card": {"run": run},
                           "bluf": {"what": "Gi0/3 on s5 is err-disabled",
                                    "evidence": [{"kind": "syslog", "at": "2026-11-17T17:53:41Z",
                                                  "words": "%PM-4-ERR_DISABLE"}] * 6}},
                          **fixit)}


def _stages(nodes):
    return [(n["name"], n["state"]) for n in nodes]


def test_every_stage_of_the_demo_incident_from_its_own_record():
    nodes = S.lifecycle(_model(), LINES)
    assert _stages(nodes) == [(name, "done") for name in S.STAGES]
    by = {n["name"]: n for n in nodes}
    assert by["Diagnosing"]["at"] == "2026-11-17T17:59:35Z"
    assert by["Fix proposed"]["at"] == "2026-11-17T18:00:24Z"
    assert by["Fix proposed"]["words"] == "errdisable-recover (ai)"
    assert by["Approved"]["at"] == "2026-11-17T18:01:20Z"
    assert by["Approved"]["words"] == "by operator@example.invalid"
    assert by["Applying"]["at"] == "2026-11-17T18:01:35Z"
    assert by["Healed"]["at"] == "2026-11-17T18:02:13Z"


def test_an_open_incident_waiting_for_its_approval_is_now_at_approved():
    waiting = [line for line in LINES if not line.get("choice")]
    header = HEADER[:2] + [{"name": "Fixed", "state": "", "at": ""},
                           {"name": "Verified", "state": "", "at": ""}]
    nodes = S.lifecycle(_model(resolved=False, header=header, run=[]), waiting)
    assert _stages(nodes)[3:6] == [("Fix proposed", "done"), ("Approved", "now"),
                                   ("Applying", "todo")]


def test_a_self_heal_skips_the_ai_stages():
    nodes = S.lifecycle(_model(run=[]), [])
    assert [n["state"] for n in nodes if n["name"] in ("Diagnosing", "Fix proposed",
                                                      "Approved")] == ["skip"] * 3
    assert nodes[-1]["state"] == "done"


def test_nothing_is_now_where_nothing_is_happening():
    """Tonight's shot of a rolled-back heal (2026-11-18): Diagnosing drew "now" though nothing
    diagnosed it. A failed self-heal with no AI part skips the AI stages, its Applying failed,
    and no stage is "now" until something runs."""
    header = HEADER[:2] + [{"name": "Fixed", "state": "failed", "at": ""},
                           {"name": "Verified", "state": "failed", "at": ""}]
    nodes = S.lifecycle(_model(resolved=False, header=header, run=[]), [])
    states = dict(_stages(nodes))
    assert "now" not in states.values()
    assert [states[n] for n in ("Diagnosing", "Fix proposed", "Approved")] == ["skip"] * 3
    assert states["Applying"] == "failed" and states["Healed"] == "failed"
    # The page's own header for a rolled-back heal: Fixed "none", worded "not fixed".
    header[2] = {"name": "Fixed", "state": "none", "at": "", "words": "not fixed"}
    rolled = dict(_stages(S.lifecycle(_model(resolved=False, header=header, run=[]), [])))
    assert rolled["Applying"] == "failed"
    running =dict(_model(resolved=False, header=HEADER[:2] + header[2:], run=[]),
                   done={"running": True})
    running["header"] = HEADER[:2] + [{"name": "Fixed", "state": "", "at": ""},
                                      {"name": "Verified", "state": "", "at": ""}]
    assert dict(_stages(S.lifecycle(running, [])))["Applying"] == "now"


def test_a_failed_verify_is_never_healed():
    header = HEADER[:3] + [{"name": "Verified", "state": "failed", "at": "2026-11-17T18:02:13Z"}]
    nodes = S.lifecycle(_model(header=header), LINES)
    assert nodes[-1]["state"] == "failed" and nodes[-1]["words"] == "not healed"


def test_a_failed_verify_never_draws_verifying_done():
    """C4030: a rolled-back heal drew Applying red, Verifying green with its time and Healed
    red: a verify that failed is never done (CLAUDE.md, never green over a failure)."""
    header = HEADER[:2] + [{"name": "Fixed", "state": "none", "at": "", "words": "not fixed"},
                           {"name": "Verified", "state": "failed", "at": "2026-11-17T18:02:13Z"}]
    by = {n["name"]: n for n in S.lifecycle(_model(resolved=False, header=header), LINES)}
    assert by["Verifying"]["state"] == "failed"
    assert by["Verifying"]["at"] == "2026-11-17T18:01:56Z"
    assert (by["Applying"]["state"], by["Healed"]["state"]) == ("failed", "failed")
    # A verify that held stays done.
    held = {n["name"]: n for n in S.lifecycle(_model(), LINES)}
    assert held["Verifying"]["state"] == "done"


def test_the_summary_names_the_ais_first_hypothesis_and_four_evidence_lines():
    got = S.summary(_model(), LINES)
    assert got["cause"].startswith("Unauthorised MAC aabb.cc00.8099 on VLAN 10")
    assert len(got["evidence"]) == S.EVIDENCE_SHOWN and got["evidence_more"] == 2
    assert got["next"] == "Nothing to do: resolved in 8 min 33 s" and not got["inconclusive"]


def test_a_healed_incidents_next_says_the_one_duration_never_seconds():
    """C4034: a heal's time to repair is worded "1,118 s" in its cell; the summary says the
    stepper's one duration, and nothing when no repair was timed (a cleared incident)."""
    healed = dict(_model(), ttr={"seconds": 1118, "words": "1,118 s", "span": "18 min 38 s"})
    assert S.summary(healed, LINES)["next"] == "Nothing to do: resolved in 18 min 38 s"
    cleared = dict(_model(), ttr={"seconds": None, "words": "cleared, no repair recorded"})
    assert S.summary(cleared, LINES)["next"] == "Nothing to do"


def test_an_ai_that_ended_without_a_fix_is_inconclusive():
    got = S.summary(_model(resolved=False, state="cant_fix", why="no safe plan"), [])
    assert got == dict(got, cause="Inconclusive: no safe plan", inconclusive=True,
                       next="Approve the plan")


def test_a_reason_that_is_already_next_is_never_also_the_cause():
    """Tonight's shots (2026-11-18): a can't-fix's reason, and a self-heal's fix, were drawn as
    the likely cause (each from What's wrong). With no hypothesis the cause is the kind of what
    opened it."""
    why = "mercury cannot fix this yet: nothing was sent (Tier 2)"
    model = dict(_model(resolved=False), wrong={"words": why},
                 todo={"words": "It needs a person: " + why})
    model["fixit"]["bluf"]["evidence"] = [{"kind": "config_change", "at": "", "words": "x"}]
    got = S.summary(model, [])
    assert got["cause"] == "A configuration change from outside Mercury"
    assert why not in got["cause"] and got["next"].endswith(why)
    model["fixit"]["bluf"]["evidence"] = [{"kind": "syslog", "at": "", "words": "x"}]
    assert S.summary(model, [])["cause"] == ""


def test_the_hypotheses_are_the_newest_proposals_the_first_chosen():
    got = S.hypotheses(LINES)
    assert [h["chosen"] for h in got] == [True, False]
    assert got[0]["confirm"] == "show port-security interface GigabitEthernet0/3"
    assert "read:3" in got[0]["cites"]


def test_the_ai_call_is_read_from_the_record_of_calls(monkeypatch):
    row = {"id": "ai-32c642bea0ba4e30", "model": "claude-sonnet-5-5",
           "prompt": "fixit_troubleshoot.v18", "cost_usd": 0.0536895, "latency_s": 10.011,
           "tokens": {"input_tokens": 7096, "cache_creation_input_tokens": 11131,
                      "cache_read_input_tokens": 0, "output_tokens": 1167}}
    monkeypatch.setattr("modules.ai.calls.rows_since",
                        lambda since: {"state": "ok", "rows": [row], "error": ""})
    got = S.ai_call(LINES, 1794938035.6)
    assert got == {"state": "ok", "id": "ai-32c642bea0ba4e30", "model": "claude-sonnet-5-5",
                   "prompt": "fixit_troubleshoot.v18",
                   "tokens": {"input": 7096, "cache_write": 11131, "cache_read": 0,
                              "output": 1167},
                   "usd": 0.0536895, "latency_s": 10.011, "calls": 1}


def test_an_unreadable_or_missing_call_says_so(monkeypatch):
    monkeypatch.setattr("modules.ai.calls.rows_since",
                        lambda since: {"state": "unreadable", "rows": [], "error": "x"})
    assert S.ai_call(LINES, 1.0)["state"] == "unreadable"
    monkeypatch.setattr("modules.ai.calls.rows_since",
                        lambda since: {"state": "ok", "rows": [], "error": ""})
    assert S.ai_call(LINES, 1.0) == {"state": "missing", "id": "ai-32c642bea0ba4e30"}
    assert S.ai_call([], 1.0) == {}


def test_the_partial_draws_every_part_and_its_needs(monkeypatch):
    from flask import render_template

    from app import app
    monkeypatch.setattr("modules.ai.calls.rows_since",
                        lambda since: {"state": "ok", "rows": [], "error": ""})
    model = _model()
    story = {"lifecycle": S.lifecycle(model, LINES), "summary": S.summary(model, LINES),
             "hypotheses": S.hypotheses(LINES), "ai": S.ai_call(LINES, 1.0),
             "needs": dict(S.NEEDS)}
    with app.test_request_context("/"):
        html = render_template("v2/_inc_story.html", p=dict(model, story=story))
    for name in S.STAGES:
        assert f'data-stage="{name}"' in html
    assert html.count('data-state="done"') == 8
    assert "Unauthorised MAC aabb.cc00.8099" in html
    from markupsafe import escape
    # Premise corrected (Stage 5 step 7, the operator, 2026-11-27: "Move the 'Not scored
    # yet…' paragraph under Details"): confidence, severity and risk are said under the
    # incident card's Details (tests/test_fix_choice.py), the hypotheses' ruled-out here.
    for key in ("ruled_out",):
        assert "needs: " + str(escape(S.NEEDS[key])) in html
    for key in ("confidence", "severity", "risk"):
        assert "needs: " + str(escape(S.NEEDS[key])) not in html
    assert "The record of AI calls holds no row for ai-32c642bea0ba4e30" in html


def test_what_is_next_leads_the_facts(monkeypatch):
    """Stage 5 step 4 (C: the answer first): the story's facts open with what is next, then the
    likely cause and the evidence; Next was their last line."""
    import re

    from flask import render_template

    from app import app
    monkeypatch.setattr("modules.ai.calls.rows_since",
                        lambda since: {"state": "ok", "rows": [], "error": ""})
    model = _model()
    summary = S.summary(model, LINES)
    story = {"lifecycle": S.lifecycle(model, LINES), "summary": summary,
             "hypotheses": S.hypotheses(LINES), "ai": S.ai_call(LINES, 1.0),
             "needs": dict(S.NEEDS)}
    with app.test_request_context("/"):
        html = render_template("v2/_inc_story.html", p=dict(model, story=story))
    facts = re.search(r"<dl class=\"inc-sum-lines[^\"]*\" data-summary>(.*?)</dl>", html, re.S)
    terms = re.findall(r"<dt>([^<]+)</dt>", facts.group(1))
    assert terms[0] == "Next" and terms.index("Likely cause") > 0, terms
    assert summary["next"], "the model has a next step"
    first = facts.group(1).split("</dd>", 1)[0]
    assert 'class="inc-sum-next"' in first, "the first fact's value is the next step"


def test_the_timeline_is_a_section_whose_line_is_the_stages_reached(monkeypatch):
    """Stage 5 step 4 (the operator's GUI pick of 2026-11-25: C with B's step timeline): the
    lifecycle is the Timeline section, closed, its line the stages reached in order and its
    state how many of the eight are done; the facts are drawn with no box, and what Mercury
    does not score is one line."""
    from flask import render_template

    from app import app
    monkeypatch.setattr("modules.ai.calls.rows_since",
                        lambda since: {"state": "ok", "rows": [], "error": ""})
    model = _model()
    life = S.lifecycle(model, LINES)
    story = {"lifecycle": life, "summary": S.summary(model, LINES),
             "hypotheses": S.hypotheses(LINES), "ai": S.ai_call(LINES, 1.0),
             "needs": dict(S.NEEDS)}
    with app.test_request_context("/"):
        html = render_template("v2/_inc_story.html", p=dict(model, story=story))
    reached = [n["name"] for n in life if n["state"] not in ("todo", "skip")]
    done = sum(1 for n in life if n["state"] == "done")
    sec = re.search(r'<details class="doc-sec" id="inc-life-[^"]*"[^>]*>\s*<summary>(.*?)</summary>',
                    html, re.S)
    assert sec and " open" not in sec.group(0).split(">")[0], "the Timeline starts closed"
    assert f'<span class="doc-gist" title="{" → ".join(reached)}">' in sec.group(1)
    assert f">{done} of {len(life)} done<" in sec.group(1)
    assert '<dl class="inc-sum-lines inc-facts' in html and 'class="card inc-sum' not in html
    # Premise corrected (Stage 5 step 7, the operator, 2026-11-27): the one line of what
    # Mercury does not score is under the incident card's Details, never in the story.
    assert html.count('data-needs') == 0


def test_what_happened_is_said_once_when_it_is_the_title(monkeypatch):
    """The title leads the page (Stage 5 step 4, slice 2): the facts draw What only where it
    says something else than the title (each fact once)."""
    from flask import render_template

    from app import app
    monkeypatch.setattr("modules.ai.calls.rows_since",
                        lambda since: {"state": "ok", "rows": [], "error": ""})
    model = _model()
    summary = S.summary(model, LINES)
    story = {"lifecycle": S.lifecycle(model, LINES), "summary": summary,
             "hypotheses": S.hypotheses(LINES), "ai": S.ai_call(LINES, 1.0),
             "needs": dict(S.NEEDS)}
    with app.test_request_context("/"):
        same = render_template("v2/_inc_story.html",
                               p=dict(model, story=story, title=summary["what"]))
        other = render_template("v2/_inc_story.html",
                                p=dict(model, story=story, title="another title"))
    assert "<dt>What</dt>" not in same
    assert f"<dt>What</dt><dd>{summary['what']}</dd>" in other
