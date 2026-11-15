"""An incident's card draws only its own answers, and labels a previous one (the operator,
2026-11-15, items C and D).

- **C, another incident's answer is superseded:** s1's incident hi-e56afd12e1a6 showed "The AI
  named no fix: s2 reported GigabitEthernet1/0 going down ...", an answer about s2. On the host,
  the turn-on's catch-up at 07:12 UTC had started four investigations under one press key, and
  s1's, r4's and r7's first calls each "joined call ai-2c349452c6004b2c", s2's (C3771, fixed in
  a0f9a54b: a press's key now names its subject and a join across subjects is refused). The
  answers kept before the fix stay in the record; drawn, a line resting on a call about another
  incident, or on one that joined such a call (`incident.calls_of`'s ``about_other``), is
  superseded: its content withheld, said in words, never drawn as this incident's.
- **D, during a new investigation the previous answer is labelled:** "Previous answer, <time>,
  prompt v5", collapsed, while a newer start stands.

Through tests/test_fixit_troubleshoot.py's world (the real app, records and page). No device,
no network, no live AI.
"""
import time

from modules.ai import calls
from modules.fixit import incident as F
from modules.fixit import section as S
from tests.test_fixit_troubleshoot import ai, incident, page, stopped  # noqa: F401
from tests.test_fixit_section_v2 import NET, web  # noqa: F401 (the fixture `ai` builds on)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

S2_WORDS = ("The AI named no fix: s2 reported GigabitEthernet1/0 going down (a linkDown trap, "
            "then the Interface down alert)")


def _another_incident_s_answer(iid: str) -> str:
    """The host's shape: a call about another incident, and this incident's call that joined
    it, the joined answer kept on this incident's record. The kept line's id."""
    calls.record({"id": "ai-2c349452c6004b2c", "feature": "fixit_troubleshoot", "verdict": "ok",
                  "prompt": "fixit_troubleshoot.v5", "cost_usd": 0.042098,
                  "subject": {"kind": "heal_incident", "id": "hi-c85f5bf71c80",
                              "devices": ["s2"]}})
    calls.record({"id": "ai-fda599a7bf3848f9", "feature": "fixit_troubleshoot",
                  "verdict": calls.JOINED, "joined": "ai-2c349452c6004b2c", "cost_usd": 0.0,
                  "prompt": "fixit_troubleshoot.v5",
                  "subject": {"kind": "heal_incident", "id": iid, "devices": ["r2"]}})
    got = F.record_proposal(incident(iid), "ai", words=S2_WORDS, calls=["ai-fda599a7bf3848f9"],
                            prompt="fixit_troubleshoot.v5",
                            shown={"rationale": "s2 reported GigabitEthernet1/0 going down.",
                                   "hypotheses": []})
    return got.get("proposal") or ""


def _view(iid):
    from modules import incident_page
    return S.view(NET, incident_page.resolve(NET, iid))


def test_an_answer_resting_on_another_incident_s_call_is_superseded_never_drawn(ai):  # noqa: F811
    iid = stopped(ai)
    _another_incident_s_answer(iid)
    got = _view(iid)["ai_answer"]
    assert got["superseded"] == S.OTHER_INCIDENT_WORDS, got
    assert got["shown"] == {} and not got["has_plan"]
    assert "s2" not in got["words"], got["words"]
    _r, html = page(ai.client, iid)
    assert "s2 reported" not in html, "another incident's answer drawn on this one"
    assert "this answer was about another incident" in html.replace("&#39;", "'")


def test_its_own_answer_is_drawn_as_its_own(ai):  # noqa: F811
    # The control: the same line on a call about this incident is drawn, unlabelled.
    iid = stopped(ai)
    calls.record({"id": "ai-0000000000000a01", "feature": "fixit_troubleshoot", "verdict": "ok",
                  "prompt": "fixit_troubleshoot.v9", "cost_usd": 0.03,
                  "subject": {"kind": "heal_incident", "id": iid, "devices": ["r2"]}})
    F.record_proposal(incident(iid), "ai", words="The AI named no fix: r2's collector holds "
                      "the old session.", calls=["ai-0000000000000a01"],
                      prompt="fixit_troubleshoot.v9",
                      shown={"rationale": "r2's collector holds the old session.",
                             "hypotheses": []})
    got = _view(iid)["ai_answer"]
    assert got["superseded"] == "" and got["shown"]["rationale"].startswith("r2's collector")
    assert got["previous"] is False


def test_an_answer_with_no_plan_is_never_said_as_one_to_approve(ai):  # noqa: F811
    """The builder's finding (the operator, 2026-11-15): an AI answer with no plan leaves the
    section "proposed", and Incidents and Needs attention said "approve, modify or deny the
    plan" with nothing to approve."""
    from modules import incidents_list
    iid = stopped(ai)
    calls.record({"id": "ai-0000000000000a03", "feature": "fixit_troubleshoot", "verdict": "ok",
                  "prompt": "fixit_troubleshoot.v13", "cost_usd": 0.03,
                  "subject": {"kind": "heal_incident", "id": iid, "devices": ["r2"]}})
    F.record_proposal(incident(iid), "ai", words="The AI named no fix: the collector holds "
                      "the old session.", calls=["ai-0000000000000a03"],
                      prompt="fixit_troubleshoot.v13",
                      shown={"rationale": "the collector holds the old session.",
                             "hypotheses": []})
    (row,) = [r for r in incidents_list.rows(NET)["rows"] if r["id"] == iid]
    label = row["bluf"]["fix"]["label"]
    assert "approve" not in label.lower(), label
    assert "ask it again or hand it over" in label, label
    # The row's label is the one source of those words (`incidents_list.NEXT_BY_WHY`), and both
    # pages draw it; the label is held here, not a page's absence (docs/TEST_INTEGRITY.md item 4).
    assert row["bluf"]["fix"].get("kind") != "approve", row["bluf"]["fix"]


def test_during_a_new_investigation_the_previous_answer_is_labelled(ai):  # noqa: F811
    iid = stopped(ai)
    calls.record({"id": "ai-0000000000000a02", "feature": "fixit_troubleshoot", "verdict": "ok",
                  "prompt": "fixit_troubleshoot.v5", "cost_usd": 0.03,
                  "subject": {"kind": "heal_incident", "id": iid, "devices": ["r2"]}})
    F.record_proposal(incident(iid), "ai", words="The AI named no fix: r2's collector holds "
                      "the old session.", calls=["ai-0000000000000a02"],
                      prompt="fixit_troubleshoot.v5", now=time.time() - 60,
                      shown={"rationale": "r2's collector holds the old session.",
                             "hypotheses": []})
    F.claim_start(incident(iid), "k-new", trigger="person", state="started")
    v = _view(iid)
    assert v["state"] == "investigating", v["state"]
    got = v["ai_answer"]
    assert got["previous"] is True and got["version"] == "v5", got
    _r, html = page(ai.client, iid)
    assert "Previous answer" in html and "prompt v5" in html, "the previous answer unlabelled"
