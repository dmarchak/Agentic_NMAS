"""The read loop, iterative (C3797; the operator, 2026-11-15: "The read loop is iterative: the AI
requests reads from its read families, Mercury runs them through the read engine ..., and the
AI continues until it's confident or hits the bounds. Bounds: the incident's cost cap, plus a
declared maximum of reads and wall time (in the wait registry), not a fixed 2 passes. An empty
or refused read is fed back so it can choose another.").

A feature that declares *rounds* (`LoopFeature.rounds`, with its *again* pass, *max_reads* and
*wall_s*, and its own *may_go_on*) is asked again with every read so far until an answer asks
for nothing, or a bound ends it with the last pass (which cannot ask); a feature that declares
none runs the two passes as before (tests/test_ai_read_loop.py holds those). Through
tests/test_ai_read_loop.py's planted family, feature and gateway: no network, no live AI.

- **It goes on until it is confident:** pass 1 asks, its reads run, the again pass sees them and
  asks more, those run, and the answer that asks for nothing ends it; every read of the
  investigation has its own id (read:1, read:2, ...), and each round is logged before its reads
  are sent.
- **A refused or empty read is fed back:** its record, with its reason, reaches the next pass,
  which may choose another.
- **Each bound ends it with the last pass:** the rounds, the reads in all (a request past them
  refused, naming the bound), the wall time from the first pass's start; the feature's own
  bound (the incident's cost cap) ends it with the newest answer, asking nothing more.
- **Only a whole declaration is taken:** rounds without an again pass that may ask, or past the
  loop's own ceilings, are refused when declared.
"""
import json

import pytest

from modules.ai import read_loop as RL
from tests.test_ai_read_loop import (DPID1, DPID2, FAMILY, SCOPE, FakeGateway, First,  # noqa: F401
                                     _ask, _family, _feature, _first, _run, _second, class_on)


def _iterative(**over):
    spec = dict(again=(("ping", 1), First), rounds=3, max_reads=9, wall_s=240.0)
    spec.update(over)
    return _feature(**spec)


def _sent_reads(call) -> list:
    return json.loads(call["parts"].get(RL.READS_PART) or "[]")


def test_it_asks_again_with_every_read_until_an_answer_asks_for_nothing():
    gw = FakeGateway(_first(_ask("topology")),
                     _first(_ask("switch_flows", dpid=DPID1), cites=("pack:1", "read:1")),
                     _first(cites=("pack:1", "read:1", "read:2")))
    got = _run(gw, feature=_iterative())
    assert got["state"] == "answered" and got["pass"] == 3 and got["rounds"] == 2, got["words"]
    assert [r["id"] for r in got["reads"]] == ["read:1", "read:2"]
    assert [c["schema"] for c in gw.calls] == [First, First, First], "each pass may ask"
    assert [r["id"] for r in _sent_reads(gw.calls[1])] == ["read:1"]
    assert [r["id"] for r in _sent_reads(gw.calls[2])] == ["read:1", "read:2"], \
        "every read so far reaches the next pass"
    assert len(got["loops"]) == 2, "each round's reads logged before they are sent"
    assert got["answer"].claim == "a scan from 192.0.2.5"
    assert "2 rounds of reads; answered" in got["words"]


def test_a_refused_read_is_fed_back_and_another_chosen():
    gw = FakeGateway(_first(_ask("switch_flows", dpid="not-a-dpid")),
                     _first(_ask("topology")),
                     _first(cites=("pack:1", "read:2")))
    got = _run(gw, feature=_iterative())
    first, second = got["reads"]
    assert (first["id"], first["verdict"]) == ("read:1", "refused")
    sent = _sent_reads(gw.calls[1])
    assert sent and sent[0]["verdict"] == "refused" and sent[0]["reason"], \
        "the refusal and its reason reach the next pass"
    assert (second["id"], second["verdict"]) == ("read:2", "run")
    assert got["state"] == "answered" and got["pass"] == 3


def test_the_rounds_bound_ends_it_with_the_last_pass_which_cannot_ask():
    gw = FakeGateway(_first(_ask("topology")),
                     _first(_ask("switch_flows", dpid=DPID1), cites=("pack:1", "read:1")),
                     _second(cites=("pack:1", "read:2")))
    got = _run(gw, feature=_iterative(rounds=2))
    assert got["pass"] == 3 and got["rounds"] == 2 and got["bound"] == "its rounds of reads"
    assert gw.calls[-1]["schema"].__name__ == "Second", "the last pass has no reads field"
    assert "at the bound on its rounds of reads" in got["words"]


def test_reads_past_the_bound_in_all_are_refused_naming_it():
    gw = FakeGateway(_first(_ask("topology"), _ask("switch_flows", dpid=DPID1),
                            _ask("port_stats", dpid=DPID2)),
                     _second(cites=("pack:1", "read:1")))
    got = _run(gw, feature=_iterative(max_reads=2))
    verdicts = [(r["id"], r["verdict"]) for r in got["reads"]]
    assert verdicts == [("read:1", "run"), ("read:2", "run"), ("read:3", "refused")], verdicts
    assert "past the investigation's 2 reads in all" in got["reads"][2]["reason"]
    assert got["bound"] == "its reads" and gw.calls[-1]["schema"].__name__ == "Second"


def test_the_wall_time_ends_it_with_the_last_pass(monkeypatch):
    clock = iter([1000.0, 1000.0 + 241.0, 1000.0 + 242.0, 1000.0 + 243.0])
    monkeypatch.setattr(RL.time, "monotonic", lambda: next(clock))
    gw = FakeGateway(_first(_ask("topology")), _second(cites=("pack:1", "read:1")))
    got = _run(gw, feature=_iterative())
    assert got["bound"] == "its time" and got["pass"] == 2
    assert gw.calls[-1]["schema"].__name__ == "Second"


def test_the_features_own_bound_stops_it_asking_nothing_more():
    seen = []

    def capped(cost):
        seen.append(cost)
        return "this incident's AI cap would be passed"
    gw = FakeGateway(_first(_ask("topology")))
    got = _run(gw, feature=_iterative(may_go_on=capped))
    assert len(gw.calls) == 1 and seen == [0.01], "asked once, with the spend so far"
    assert got["state"] == "first_pass" and got["answer"].claim == "a scan from 192.0.2.5"
    assert "not asked again: this incident's AI cap would be passed" in got["words"]


def test_a_feature_with_no_rounds_runs_its_two_passes_as_before():
    gw = FakeGateway(_first(_ask("topology")), _second())
    got = _run(gw, feature=_feature())
    assert got["pass"] == 2 and "rounds" not in got and len(gw.calls) == 2


@pytest.mark.parametrize("case", ["no again", "again without reads", "rounds past the ceiling",
                                  "reads past the ceiling", "time past the ceiling", "no time"])
def test_only_a_whole_declaration_is_taken(case):
    over, said = {
        "no again": ({"again": None}, "again pass is not"),
        "again without reads": ({"again": (("ping", 1), type("NoReads", (), {}))},
                                "again pass is not"),
        "rounds past the ceiling": ({"rounds": RL.MAX_ROUNDS + 1}, "rounds"),
        "reads past the ceiling": ({"max_reads": RL.MAX_LOOP_READS + 1}, "max_reads"),
        "time past the ceiling": ({"wall_s": RL.MAX_WALL_S + 1}, "wall_s"),
        "no time": ({"wall_s": 0}, "wall_s"),
    }[case]
    with pytest.raises(RL.Undeclarable, match=said):
        _iterative(**over)
