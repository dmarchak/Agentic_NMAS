"""The read job's tests: pytest's format, run by Mercury's runner and by pytest alike."""

from job import SwitchLinks, label, link_counts
from modules.jobs import covers, refused
from modules.jobs.testing import FakeContext, plan_run


def recorded_counts(ryu):
    """The links leaving each switch, counted here from the recording's raw answers."""
    counts = {int(d): 0 for d in ryu.dpids()}
    for link in ryu.get("/v1.0/topology/links"):
        counts[int(link["src"]["dpid"], 16)] += 1
    return counts


@covers("every switch is listed with its links")
def test_every_switch_is_listed_with_its_links(ryu):
    ctx = plan_run(SwitchLinks, {"busy": 2}, controller=ryu.driver())
    table = ctx.output.tables[0]
    assert table["title"] == "switch links"
    assert table["columns"] == ["dpid", "links", "state"]
    expected = recorded_counts(ryu)
    assert [row[0] for row in table["rows"]] == sorted(expected)
    assert [row[1] for row in table["rows"]] == [expected[d] for d in sorted(expected)]
    assert ctx.changes.changes == []


@covers("a switch past the threshold is busy")
def test_a_switch_past_the_threshold_is_busy():
    assert label(3, 2) == "busy"
    assert label(2, 2) == "ok"
    assert label(1, 2) == "ok"
    assert label(0, 2) == "isolated"


def test_the_threshold_defaults_to_two(ryu):
    ctx = plan_run(SwitchLinks, {}, controller=ryu.driver())
    expected = recorded_counts(ryu)
    states = [row[2] for row in ctx.output.tables[0]["rows"]]
    assert states == [label(expected[d], 2) for d in sorted(expected)]


def test_a_link_from_another_switch_is_not_counted():
    counts = link_counts([{"dpid": 1}], [{"src": {"dpid": 1}}, {"src": {"dpid": 9}}])
    assert counts == {1: 1}


class _Down:
    def switches(self):
        return {"ok": False, "error": "no answer", "switches": []}

    def links(self):
        return {"ok": True, "error": "", "links": []}


class _LinksDown(_Down):
    def switches(self):
        return {"ok": True, "error": "", "switches": [{"dpid": 1}]}

    def links(self):
        return {"ok": False, "error": "no answer", "links": []}


def test_a_controller_that_does_not_answer_is_logged():
    for down in (_Down(), _LinksDown()):
        ctx = FakeContext(SwitchLinks.meta, controller=down)
        SwitchLinks().run(ctx, SwitchLinks.Inputs())
        assert ctx.output.lines == ["the controller did not answer"]
        assert ctx.output.tables == []


def test_a_threshold_that_is_not_a_number_is_refused(ryu):
    with refused("busy"):
        plan_run(SwitchLinks, {"busy": "many"}, controller=ryu.driver())
