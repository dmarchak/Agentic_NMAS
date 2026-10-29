"""The change record's recorded cases (PHASE8_PLAN 16.11 item 3; 13.6, 15.12;
tests/fixtures/ai_cases/change_record/recorded.json): each a deploy preview of a real captured
configuration with a minimal edit, its facts computed by the product's own code, judged by
`cases.change_record_misses`.

- The file is on the task's pin, and holds at least 8 cases, each with what the words must say,
  what they must never say, and what only a person can judge.
- Every case is ready on the code as it is (`cases.change_record_unready`): its program, risk,
  verify scope, interfaces, rollback and what is sent are what the case expects, and nothing it
  says must never be sent is in what is sent.
- The grader passes a draft that says what the case asks, and fails each planted wrong one: an
  interface the program does not touch (Mercury's own refusal), a word the case rules out, and
  a missing word; an evaluation request is exactly what a press sends.
- No model is asked: the cases' recordings are the screen's, run on the host.
"""
import json
import os

import pytest

from modules.ai import cases, change_record, profiles

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(ROOT, "tests", "fixtures", "ai_cases", "change_record", "recorded.json")


def _data():
    return cases.load(FILE)


CASES = _data()["cases"]


@pytest.fixture(scope="module")
def facts():
    return {c["n"]: cases.change_record_facts(c, ROOT) for c in CASES}


def test_the_file_is_on_the_pin_with_at_least_8_cases_each_judged():
    data = _data()
    assert data["task"] == change_record.FEATURE
    assert data["model"] == profiles.TASKS[change_record.FEATURE]["model"]
    assert data["prompt"] == f"{change_record.PROMPT[0]}.v{change_record.PROMPT[1]}"
    assert len(CASES) >= 8, len(CASES)
    assert sorted(c["n"] for c in CASES) == list(range(1, len(CASES) + 1))
    for c in CASES:
        e = c["expect"]
        assert e.get("says") and e.get("never") and c.get("flag"), c["n"]
        assert c.get("facts", {}).get("risk") and c["facts"].get("verify"), c["n"]
    # Both lower risk levels and both verify scopes are reached by some case (no recorded case
    # reaches high: no real capture's edit here derives an adjacency drop; the unit test holds
    # the rule's high level).
    assert {"low", "medium"} <= {c["facts"]["risk"] for c in CASES}
    assert {c["facts"]["verify"] for c in CASES} == {"quick", "full"}


@pytest.mark.parametrize("case", CASES, ids=[f"case-{c['n']}" for c in CASES])
def test_every_case_is_ready_on_the_code_as_it_is(case, facts):
    assert cases.change_record_unready(case, facts[case["n"]]) == []


def test_an_unready_premise_is_found(facts):
    """The control: a case expecting what the code does not compute is unready, naming it."""
    case = dict(CASES[0], facts=dict(CASES[0]["facts"], risk="high",
                                     rollback_has=["no such line"],
                                     never_sent=["GigabitEthernet4"]))
    said = cases.change_record_unready(case, facts[CASES[0]["n"]])
    assert any(s.startswith("risk medium, the case expects high") for s in said), said
    assert "the rollback lacks 'no such line'" in said
    assert "what is sent holds 'GigabitEthernet4'" in said


def _good(case, f):
    """A draft that says what the case asks: the first word of each group, on its device."""
    words = [g[0] for g in case["expect"].get("says", ())]
    words += [g[0] for g in case["expect"].get("summary_says", ())]
    return {"summary": f"On {f['host']}: " + "; ".join(dict.fromkeys(words)) + ".",
            "risk": "Verify reads the device again after the change.",
            "mentions": [f["host"]] + list(f["interfaces"])}


@pytest.mark.parametrize("case", CASES, ids=[f"case-{c['n']}" for c in CASES])
def test_the_grader_passes_what_the_case_asks_and_fails_each_planted_wrong(case, facts):
    f = facts[case["n"]]
    known = cases.change_record_names(ROOT)
    good = _good(case, f)
    assert cases.change_record_graded(case["expect"], good, f, known)["pass"], \
        cases.change_record_misses(case["expect"], good, f, known)
    other = dict(good, summary=good["summary"] + " It also shuts GigabitEthernet9.")
    assert cases.change_record_misses(case["expect"], other, f, known)[0].startswith(
        "Mercury refuses it: the answer named GigabitEthernet9")
    ruled = dict(good, risk=good["risk"] + " " + case["expect"]["never"][0])
    assert any("which the case rules out" in m
               for m in cases.change_record_misses(case["expect"], ruled, f, known))
    bare = dict(good, summary=f"On {f['host']}.")
    assert any(m.startswith("says none of") or m.startswith("the summary says none")
               for m in cases.change_record_misses(case["expect"], bare, f, known))
    assert cases.change_record_misses(case["expect"], None, f, known, "couldnt_draft") == [
        "no answer: couldnt_draft"]


def test_an_evaluation_request_is_what_a_press_sends(facts):
    f = facts[1]
    req = change_record.batch_request(1, 0, f)
    assert req["custom_id"] == "c1-change_record-v1-r0"
    assert req["feature"] == change_record.FEATURE and req["prompt"] == change_record.PROMPT
    assert req["parts"] == change_record.parts(f) and req["subject"] == change_record.subject(f)
    assert req["schema"] is change_record.ChangeRecordWords
    assert sorted(json.loads(req["parts"]["change"])) == sorted(change_record.SENT_KEYS)
