"""The write job's tests: pytest's format, `pytest.raises` among them (the runner's shim gives
it), run by Mercury's runner and by pytest alike."""

import pytest

from job import ArpGuard, arp_flow
from modules.jobs import ContractError, covers
from modules.jobs.testing import FakeContext, plan_run


@covers("one flow per switch")
def test_one_flow_per_switch(ryu):
    ctx = plan_run(ArpGuard, {"priority": 100}, controller=ryu.driver())
    planned = ctx.changes.changes
    assert [c["dpid"] for c in planned] == sorted(int(d) for d in ryu.dpids())
    for change in planned:
        assert change["change"] == {"do": "add_flow", "flow": {
            "priority": 100, "match": {"eth_type": 2054},
            "actions": [{"type": "OUTPUT", "port": "CONTROLLER"}]}}
    assert ctx.output.lines == [f"{len(planned)} flows planned"]


@covers("a priority out of range is refused")
def test_a_priority_out_of_range_is_refused():
    for bad in (0, 65536):
        with pytest.raises(ContractError) as refusal:
            arp_flow(bad)
        assert str(refusal.value) == (f"arp-guard's priority refused: priority is 1 to 65535, "
                                      f"not {bad}")
    assert arp_flow(1)["priority"] == 1
    assert arp_flow(65535)["priority"] == 65535


def test_the_limit_stops_the_plan(ryu):
    ctx = plan_run(ArpGuard, {"priority": 100, "limit": 2}, controller=ryu.driver())
    assert [c["dpid"] for c in ctx.changes.changes] == sorted(int(d) for d in ryu.dpids())[:2]
    assert ctx.output.lines == ["2 flows planned"]


def test_the_limit_defaults_to_eight():
    many = [{"dpid": d} for d in range(1, 11)]
    ctx = FakeContext(ArpGuard.meta, controller=_Answers(many))
    ArpGuard().run(ctx, ArpGuard.Inputs(priority=5))
    assert len(ctx.changes.changes) == 8


class _Answers:
    def __init__(self, switches, ok=True):
        self.answer = {"ok": ok, "error": "" if ok else "no answer", "switches": switches}

    def switches(self):
        return self.answer


def test_a_controller_that_does_not_answer_is_refused():
    ctx = FakeContext(ArpGuard.meta, controller=_Answers([], ok=False))
    with pytest.raises(ContractError, match="^arp-guard refused: the controller did not "
                                            "answer: no answer$"):
        ArpGuard().run(ctx, ArpGuard.Inputs(priority=5))
    assert ctx.changes.changes == []


def test_the_plan_holds_at_most_eight_changes():
    many = [{"dpid": d} for d in range(1, 11)]
    ctx = FakeContext(ArpGuard.meta, controller=_Answers(many))
    with pytest.raises(ContractError, match="change 9 is past the job's max_changes of 8"):
        ArpGuard().run(ctx, ArpGuard.Inputs(priority=5, limit=9))
