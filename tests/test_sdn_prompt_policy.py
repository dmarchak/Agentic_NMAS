"""The classifier's prompt names no fixed rule-to-action mapping (C2023's static half): the
network's response policy decides which catalogue actions a rule may take, so a prompt that
says "a scan is answered by dropping its source" fights the policy (v1 did; the Lab 8 walk
found it, C1988, and v3 replaced it).

- The served prompt (`closed_loop.CLASSIFY_PROMPT`) and every later version hold no sentence
  that ties a detection rule (scan, flood, unauthorised flow) to a response action as its
  answer.
- The check finds v1's own sentence (the planted case: the shape it exists to catch).

The other half, replaying a prompt change against several response policies, is a
measurement (scripts/nmas-sdn-cases), not a unit test.
"""
import os
import re

from modules.sdn import closed_loop as CL

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULE = r"(?:scan|flood|unauthori[sz]ed[- ]flow)s?"
ACTION = r"(?:dropping|drop|rate[- ]limiting|rate[- ]limit|remov(?:ing|e))"
#: "a scan is answered by dropping its source", "answer a flood by rate-limiting", "a flood by
#: rate-limiting its source" (v1's second clause, its verb carried from the first).
MAPPING = re.compile(
    rf"\b{RULE}\b[^.;:]{{0,40}}?\b(?:is |are )?(?:answered|met|handled|responded to)\s+by\s+"
    rf"{ACTION}|\b(?:answer|respond to|meet)\s+(?:a |an |the )?{RULE}\b[^.;:]{{0,30}}?\bby\s+"
    rf"{ACTION}|;\s*(?:a |an )?{RULE}\s+by\s+{ACTION}", re.I)


def _text(version: int) -> str:
    with open(os.path.join(ROOT, "prompts", f"sdn_classify.v{version}.md"),
              encoding="utf-8") as fh:
        return " ".join(fh.read().split())


def _versions() -> list:
    return sorted(int(m.group(1)) for m in (re.fullmatch(r"sdn_classify\.v(\d+)\.md", n)
                                            for n in os.listdir(os.path.join(ROOT, "prompts")))
                  if m)


def test_the_served_prompt_and_every_later_one_name_no_rule_to_action_mapping():
    served = CL.CLASSIFY_PROMPT[1]
    later = [v for v in _versions() if v >= served]
    assert served in later, (served, _versions())
    found = {v: MAPPING.findall(_text(v)) for v in later}
    assert all(not hits for hits in found.values()), found


def test_the_check_finds_v1_s_mapping():
    hits = [m.group(0) for m in MAPPING.finditer(_text(1))]
    assert [h.lower() for h in hits] == ["scan is answered by dropping",
                                         "; a flood by rate-limiting",
                                         "; an unauthorised flow by removing"], hits
