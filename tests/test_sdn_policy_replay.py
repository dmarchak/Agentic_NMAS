"""The classifier replayed under several response policies (C2023's replay half; C1988 is why:
v1's prompt named "a scan is answered by dropping its source", and only the Lab 8 walk found
that it answered outside the SDN lab's policy). The static half, a prompt naming a fixed
rule-to-action mapping, is tests/test_sdn_prompt_policy.py. No provider is called.

- **The permutations** (`cases.SDN_POLICY_PERMUTATIONS`): each a response policy the setting
  takes, named and with its reason, no two alike; among them the lab's as committed
  (tests/test_sdn_policy.py's SDN_LAB, a scan rate-limited only), a scan's drop allowed, a
  flood rate-limited only, and the AUTO-eligible restriction (no drop for any rule).
- **The grader** (`cases.sdn_policy_misses`, pure): on the walk's real answers
  (tests/fixtures/ai_cases/sdn_classify/policy_answers.json), each asked under the lab's policy
  (the catalogue its request carried is the lab's for its rule), none misses under it; graded
  under every permutation, each misses exactly where the table written by hand says (the real
  scan and flood answers, both rate limits, miss under drop only); the real scan answer
  planted with drop_source (its one edit) misses under the lab's policy, naming the action,
  the rule and the allowed set, and passes under drop allowed; the same as the gateway's
  answer object; no answer, a policy that is not one, and a rule that is none each miss.
- **The request carries the policy:** `closed_loop.prepare_classify` under a permutation
  (`policy_of`) is exactly the request `classify_pack` sends with that policy set on the
  network (its catalogue, the first marked default, and its data blocks), and with no
  permutation it is the network's own; a section holding no detection is refused, nothing
  sent (the moved request's hand check found no test held it).
"""
import copy
import json
import os
import re

import pytest

from modules import list_settings
from modules.ai import cases, triggers
from modules.sdn import closed_loop as CL
from tests.test_sdn_classify import world  # noqa: F401 - the fixture
from tests.test_sdn_classify_cases import _script
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_policy import SDN_LAB, catalogue_entries

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "tests", "fixtures", "ai_cases", "sdn_classify")
PERMS = {p["name"]: p for p in cases.SDN_POLICY_PERMUTATIONS}


def answers() -> list:
    return cases.load(os.path.join(DIR, "policy_answers.json"))["answers"]


def answer_of(call: str) -> dict:
    return next(a for a in answers() if a["call"] == call)


# ── the permutations ─────────────────────────────────────────────────────────────────────────

def test_each_permutation_is_a_policy_named_with_its_reason_and_no_two_alike():
    perms = cases.SDN_POLICY_PERMUTATIONS
    assert len(perms) >= 5, perms
    for p in perms:
        assert sorted(p) == ["name", "policy", "reason"], p
        assert re.fullmatch(r"[a-z0-9_]{1,32}", p["name"]), p["name"]
        assert CL.policy_problems(p["policy"]) == [], p["name"]
        assert len(p["reason"].split()) >= 8, p["name"]
    assert len(PERMS) == len(perms)
    shapes = [json.dumps(p["policy"], sort_keys=True) for p in perms]
    assert len(set(shapes)) == len(shapes), "two permutations ask the same policy"


def test_the_permutations_hold_the_lab_s_policy_and_the_kinds_the_order_names():
    got = [p["policy"] for p in cases.SDN_POLICY_PERMUTATIONS]
    assert PERMS["sdn_lab"]["policy"] == SDN_LAB
    # A scan rate-limited only; a scan's drop allowed; a flood rate-limited only.
    assert any(p["scan"] == ["rate_limit_source"] for p in got)
    assert any("drop_source" in p["scan"] for p in got)
    assert any(p["flood"] == ["rate_limit_source"] for p in got)
    # AUTO-eligible restricted: no drop for any rule.
    assert any(all("drop_source" not in p[r] for r in CL.RULES) for p in got)
    # Each source rule's single action asked both ways, so a fixed mapping misses somewhere.
    for rule in ("scan", "flood"):
        assert {"rate_limit_source", "drop_source"} <= {
            p[rule][0] for p in got if len(p[rule]) == 1}, rule


# ── the grader, on the walk's real answers ───────────────────────────────────────────────────

def test_each_real_answer_was_asked_under_the_lab_s_policy_and_is_within_it():
    got = answers()
    assert len(got) >= 5 and {a["rule"] for a in got} == set(CL.RULES)
    for a in got:
        assert a["catalogue_sent"] == [
            e["action_id"] for e in CL.catalogue_for_ai(SDN_LAB[a["rule"]])], a["call"]
        assert cases.sdn_policy_misses(a["answer"], a["rule"], SDN_LAB) == [], a["call"]


#: Written by hand from each answer's action and each permutation's lists, not by the
#: grader: which permutations each real answer is outside of.
OUTSIDE = {
    "ai-4be2849575ba47e7": {"drop_only"},          # a scan, rate_limit_source
    "ai-a123895c6afc4a1c": {"drop_only"},          # a flood, rate_limit_source
    "ai-96116b6be8d64cfa": set(),                  # an unauthorised flow, remove_flow
    "ai-31d44805c50045a4": set(),                  # a scan rule's false positive, none
    "ai-6969a72b9a144cd0": set(),                  # no threat, none
}


def test_every_real_answer_misses_exactly_the_permutations_that_forbid_it():
    assert set(OUTSIDE) == {a["call"] for a in answers()}
    for a in answers():
        missed = {name for name, p in PERMS.items()
                  if cases.sdn_policy_misses(a["answer"], a["rule"], p["policy"])}
        assert missed == OUTSIDE[a["call"]], (a["call"], missed)


def test_a_planted_drop_for_a_scan_misses_under_the_lab_s_policy_and_passes_where_allowed():
    real = answer_of("ai-4be2849575ba47e7")
    planted = dict(copy.deepcopy(real["answer"]), action_id="drop_source")
    (miss,) = cases.sdn_policy_misses(planted, "scan", PERMS["sdn_lab"]["policy"])
    assert "drop_source" in miss and "scan" in miss and "rate_limit_source" in miss, miss
    assert cases.sdn_policy_misses(planted, "scan", PERMS["drop_allowed"]["policy"]) == []
    # Mercury's check refuses the same answer under the same policy (the fail-safe), naming it.
    assert "outside" in CL.policy_refusal("sdn_lab", "scan", "drop_source",
                                          CL.policy_of(SDN_LAB))


def test_an_action_answering_another_rule_misses_under_every_permutation():
    planted = dict(copy.deepcopy(answer_of("ai-4be2849575ba47e7")["answer"]),
                   action_id="remove_flow")
    for name, p in PERMS.items():
        assert cases.sdn_policy_misses(planted, "scan", p["policy"]), name


def test_the_gateway_s_answer_object_is_graded_as_its_record():
    a = answer_of("ai-a123895c6afc4a1c")
    # As the gateway parses the provider's text (`model_validate_json`).
    model = CL.ThreatAssessment.model_validate_json(json.dumps(a["answer"]))
    for name, p in PERMS.items():
        assert cases.sdn_policy_misses(model, "flood", p["policy"]) == \
            cases.sdn_policy_misses(a["answer"], "flood", p["policy"]), name
    assert cases.sdn_answer_action(model) == "rate_limit_source"


def test_no_answer_a_policy_that_is_not_one_and_no_rule_each_miss():
    real = answer_of("ai-4be2849575ba47e7")["answer"]
    assert cases.sdn_policy_misses(None, "scan", SDN_LAB)
    assert cases.sdn_policy_misses(real, "scan", {"scan": ["rate_limit_source"]})
    assert cases.sdn_policy_misses(real, "scan", dict(SDN_LAB, scan=[]))
    assert cases.sdn_policy_misses(real, "worm", SDN_LAB)
    assert cases.sdn_policy_misses(dict(real, action_id=None), "scan", SDN_LAB)


def test_the_default_taken_is_reported_from_the_policy_s_order():
    scan = answer_of("ai-4be2849575ba47e7")
    flood = answer_of("ai-a123895c6afc4a1c")
    reversed_ = PERMS["defaults_reversed"]["policy"]
    assert cases.sdn_took_default(scan["answer"], "scan", reversed_) is True
    assert cases.sdn_took_default(flood["answer"], "flood", reversed_) is False
    assert cases.sdn_took_default(flood["answer"], "flood", SDN_LAB) is True
    assert cases.sdn_took_default(answer_of("ai-6969a72b9a144cd0")["answer"], "scan",
                                  reversed_) is True
    assert cases.sdn_took_default(None, "scan", SDN_LAB) is False


# ── the request carries the policy ───────────────────────────────────────────────────────────

def _walk_case(key: str) -> dict:
    data = cases.load(os.path.join(DIR, "recorded_walk.json"))
    return next(c for c in data["cases"] if c["key"] == key)


@pytest.mark.parametrize("name", sorted(PERMS))
def test_the_replay_s_request_is_the_call_s_under_the_same_policy(world, name):  # noqa: F811
    c = _walk_case("walk-flood-2-s2")
    pack = _script().pack_of(c, "Default")
    perm = PERMS[name]["policy"]
    prep = CL.prepare_classify("Default", c["detection"], pack, intact=False,
                               pol=CL.policy_of(perm))
    assert "refused" not in prep, prep
    sent = json.loads(prep["context"]["catalogue"])
    assert [e["action_id"] for e in sent] == perm["flood"] + ["none"]
    assert [e["action_id"] for e in sent if e.get("default")] == [perm["flood"][0]]
    # The call, with that policy set on the network, sends the same catalogue and data.
    assert list_settings.write("Default", {CL.POLICY_KEY: perm}, actor="test")["ok"]
    world.answer = dict(answer_of("ai-a123895c6afc4a1c")["answer"])
    actor = "evaluation:sdn-policy-replay-test"
    CL.classify_pack("Default", c["detection"], pack, actor=actor,
                     trigger=triggers.evaluation(actor), send=world.send, intact=False)
    (body,) = world.sent
    assert catalogue_entries(body) == sent
    text = "\n".join(_strings(body))
    for name_, block in prep["parts"].items():
        assert block in text, name_


def _strings(o) -> list:
    if isinstance(o, str):
        return [o]
    if isinstance(o, dict):
        return [s for v in o.values() for s in _strings(v)]
    if isinstance(o, list):
        return [s for v in o for s in _strings(v)]
    return []


def test_with_no_permutation_the_request_is_asked_under_the_network_s_own(world):  # noqa: F811
    c = _walk_case("walk-scan-s1")
    pack = _script().pack_of(c, "Default")
    assert list_settings.write("Default", {CL.POLICY_KEY: SDN_LAB}, actor="test")["ok"]
    prep = CL.prepare_classify("Default", c["detection"], pack, intact=False)
    assert [e["action_id"] for e in json.loads(prep["context"]["catalogue"])] == [
        "rate_limit_source", "none"]
    assert prep["pol"] == CL.policy("Default") and prep["rule"] == "scan"
    # A permutation that is not a policy is refused before anything is built.
    bad = CL.prepare_classify("Default", c["detection"], pack, intact=False,
                              pol=CL.policy_of({"scan": []}))
    assert bad["refused"]["error"] == "policy", bad


def test_a_pack_whose_section_holds_no_detection_is_refused_and_nothing_is_sent(world):  # noqa: F811
    c = _walk_case("walk-scan-s1")
    pack = _script().pack_of(c, "Default")
    section = pack["sections"][0]
    pieces = [p for p in section["pieces"] if p.get("kind") != "detection"]
    assert len(pieces) == len(section["pieces"]) - 1
    gone = dict(pack, sections=[dict(section, pieces=pieces)])
    prep = CL.prepare_classify("Default", c["detection"], gone, intact=False)
    assert prep["refused"]["error"] == "no_pack", prep
    actor = "evaluation:sdn-policy-replay-test"
    got = CL.classify_pack("Default", c["detection"], gone, actor=actor,
                           trigger=triggers.evaluation(actor), send=world.send, intact=False)
    assert got["error"] == "no_pack" and world.sent == [], got
