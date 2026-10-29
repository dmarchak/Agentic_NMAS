"""Explain's evaluation round as one batch (`explain.explain_packs_batch`; the operator's
decision of 2026-10-29, PHASE8_PLAN 15.12), on tests/test_ai_explain.py's world (the pack built
from the real captures, hosted AI allowed, a fake send) and tests/test_ai_batch.py's fake
batch provider:

- each batched request is what `explain_pack` sends for the same pack and prompt, byte for
  byte but for its cache mark's 1-hour TTL;
- results are keyed by custom_id (pack, prompt, run) and each answer is checked as
  `explain_pack` checks it: one citing the pack is shown, one citing what the pack does not
  hold is "couldn't analyse";
- v6's need is looked up once and its follow-up sent in a second batch, said;
- a person's press is refused before anything is built.
"""
import json

import pytest

from modules.ai import explain, triggers
from tests.ai_person import pressed_by
from tests.test_ai_batch import Clock, FakeBatches
from tests.test_ai_explain import V6_PROMPT, _answer, world  # noqa: F401 (the fixture)
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_evidence_pack import pack_lab  # noqa: F401 (the fixture)

RUN = "evaluation:explain-batch-1"


def _answering(world, answer_of):
    """A fake batch provider whose each result is what *world*'s send answers for that body,
    *answer_of(custom_id)* the planted answer."""
    def answer(cid, params):
        world.answer = answer_of(cid)
        reply = world.send(params, "k")
        return {"type": "succeeded", "message": reply.body}
    return FakeBatches(answer=answer)


def _round(world, fake, prompts_, runs, trigger=None):
    clock = Clock()
    return explain.explain_packs_batch([world.pack], prompts_, runs, actor=RUN,
                                       trigger=trigger or triggers.evaluation(RUN),
                                       today="2026-10-29", provider=fake, sleep=clock.sleep,
                                       clock=clock)


def test_each_batched_request_is_explain_packs_but_its_cache_ttl(world):
    world.answer = _answer(world.pack)
    single = explain.explain_pack(world.pack, actor=RUN, trigger=triggers.evaluation(RUN),
                                  send=world.send, today="2026-10-29")
    assert single["ok"] is True, single
    called = world.sent[-1]["body"]
    fake = _answering(world, lambda cid: _answer(world.pack))
    got = _round(world, fake, [4], 2)
    assert got["ok"] is True, got
    assert sorted(got["results"]) == ["p0-explain-v4-r0", "p0-explain-v4-r1"]
    expected = json.loads(json.dumps(called))
    expected["system"][-1]["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
    for r in fake.created[0]:
        assert json.dumps(r["params"]) == json.dumps(expected)
    for cid, one in got["results"].items():
        assert one["ok"] is True and one["answer"]["hypotheses"], one
        assert one["pack_id"] == world.pack["id"] and one["prompt"] == ["explain", 4]
    assert got["requests"]["p0-explain-v4-r1"]["run"] == 1


def test_each_answer_is_checked_as_explain_pack_checks_it(world):
    bad = _answer(world.pack, hypotheses=[{"claim": "x", "evidence_refs": ["logs:nowhere"],
                                           "confirm_with": "show version"}])
    fake = _answering(world, lambda cid: bad if cid.endswith("r1") else _answer(world.pack))
    got = _round(world, fake, [4], 2)
    assert got["results"]["p0-explain-v4-r0"]["ok"] is True
    one = got["results"]["p0-explain-v4-r1"]
    assert one["ok"] is False and one["error"] == "couldnt_analyse", one


def test_v6s_need_is_looked_up_once_and_its_follow_up_batched(world, monkeypatch):
    """The first batch's answer names a need: it is looked up once (`needs.run`), its one
    follow-up sent in a second batch (``-n``) carrying what was looked up, and the follow-up's
    answer is the one checked, the cost the round's, ``parent_call_id`` the first call's."""
    from modules.ai import needs
    monkeypatch.setitem(needs._LOOKUPS, needs.NeedKind.neighbour,
                        lambda net, subject: ({"Gi0/1": "s4"}, ""))
    monkeypatch.setattr("modules.ai.egress_classes.topology_allowed",
                        lambda net: {"allowed": True, "why": ""})
    from modules.ai import anthropic_adapter as A
    monkeypatch.setattr(A, "send", lambda body, key: pytest.fail("a call sent one at a time"))
    fake = _answering(world, lambda cid: dict(_answer(world.pack), needs=[]) if cid.endswith(
        "-n") else dict(_answer(world.pack), needs=[{"kind": "neighbour", "subject": "r1"}]))
    got = _round(world, fake, [V6_PROMPT], 1)
    one = got["results"]["p0-explain-v6-r0"]
    assert one["ok"] is True and one["needs_followed"] == "batched", one
    assert [[r["custom_id"] for r in b] for b in fake.created] == [
        ["p0-explain-v6-r0"], ["p0-explain-v6-r0-n"]]
    first = fake.created[0][0]["params"]["messages"][0]["content"]
    assert '<data name="looked_up">\n(nothing looked up)\n</data>' in first
    assert 'neighbour r1: {"Gi0/1": "s4"}' in fake.created[1][0]["params"]["messages"][0][
        "content"]
    assert one["parent_call_id"] and one["parent_call_id"] != one["call_id"]
    assert "neighbour r1: fulfilled" in one["needs_said"]
    from modules.ai import calls
    rows = {r["id"]: r for r in calls.read()["rows"]}
    assert one["cost_usd"] == round(rows[one["call_id"]]["cost_usd"]
                                    + rows[one["parent_call_id"]]["cost_usd"], 6)
    assert rows[one["call_id"]]["subject"]["parent"] == one["parent_call_id"]
    assert len(got["batch_ids"]) == 2


def test_a_person_press_is_refused_before_anything_is_built(world):
    fake = FakeBatches()
    with pressed_by("operator@example.com"):
        got = _round(world, fake, [4], 1, trigger=triggers.person("operator@example.com"))
    assert fake.created == [] and got["ok"] is False
    assert got["results"]["p0-explain-v4-r0"]["error"] == "batch_trigger"


@pytest.mark.parametrize("prompt,want", [(("explain", 4), "p3-explain-v4-r9"),
                                         (("explain", 12), "p0-explain-v12-r0")])
def test_the_custom_id_names_the_pack_the_prompt_and_the_run(prompt, want):
    pi, run = int(want.split("-")[0][1:]), int(want.rsplit("-r", 1)[1])
    assert explain.batch_custom_id(pi, prompt, run) == want
