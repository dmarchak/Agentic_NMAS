"""Why a person is needed, one short reason beside the one action (20e0a401,
`fixit.section._why_person`; the operator, 2026-11-16: "Waiting for a person" says why, at a
glance), and the incident's status line saying it (`section.drawn`'s ``status``).

The reasons are asked of `_why_person` directly, each with the action `_contract` chose; the
status line through tests/test_fixit_section_v2.py's world (the real app, a lost-stream
incident planted by the incidents store's own writer). Paid for docs/FAST_LANE_DEBT.md's row
for 20e0a401 ("Why a person is needed"), the debt pass, 2026-11-18.

Each test holds one purpose:
- each reason is the one its action, guard or saved fix gives;
- the AI's plan, a saved script and guards 4 and 6 come before the action's own reason;
- with nothing to say and no decision standing, it says nothing;
- the page's status line is the reason while a person is needed.
"""
import types

import pytest

from modules.fixit import section as S
from tests.test_fixit_section_v2 import NET, plant
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)


def found(**inc) -> dict:
    """An incident's records as `_why_person` reads them; no id, so no retry is read."""
    return {"network": NET, "incident": dict(inc)}


@pytest.fixture
def cause(monkeypatch):
    """`problem.classify` naming the incident's cause."""
    monkeypatch.setattr("modules.problem.classify",
                        lambda f: types.SimpleNamespace(cause="bpduguard",
                                                        condition="port_err_disabled"))


class TestEachReason:
    @pytest.mark.parametrize("guard", [4, {"guard": 4, "name": "intent"}])
    def test_guard_4_is_saved_config_and_intent_disagreeing(self, guard):
        got = S._why_person({"kind": "hand_over"}, None, found(standing={"guard": guard}))
        assert got == "Saved config and intent disagree: decide which is right"

    def test_guard_6_is_many_devices_at_once(self):
        got = S._why_person({"kind": "approve"}, None,
                            found(standing={"guard": {"guard": 6}}))
        assert got == "Many devices changed at once: approve fixing them all"

    def test_a_saved_script_names_itself(self):
        got = S._why_person({"kind": "start"}, {"name": "bpdu-recover"}, found())
        assert got == "A saved script can fix this: bpdu-recover"

    def test_an_approvable_plan_needs_approval(self):
        assert S._why_person({"kind": "approve"}, None, found()) == (
            "The AI's plan is ready: needs your approval")

    def test_nothing_tried_names_the_cause_and_the_ai(self, cause):
        assert S._why_person({"kind": "start"}, None, found()) == (
            "No saved fix for bpduguard yet: the AI can investigate")

    def test_nothing_tried_with_no_cause_read_still_names_the_ai(self, monkeypatch):
        def unread(f):
            raise ValueError("no read")
        monkeypatch.setattr("modules.problem.classify", unread)
        assert S._why_person({"kind": "start"}, None, found()) == (
            "No saved fix yet: the AI can investigate")

    def test_nothing_found_hands_over(self):
        assert S._why_person({"kind": "hand_over"}, None, found()) == (
            "No saved fix, and the AI found no safe plan")


class TestTheOrder:
    def test_a_guard_comes_before_a_saved_script_and_the_action(self, cause):
        got = S._why_person({"kind": "start"}, {"name": "bpdu-recover"},
                            found(standing={"guard": 4}))
        assert got.startswith("Saved config and intent disagree")

    def test_a_saved_script_comes_before_the_ai(self, cause):
        got = S._why_person({"kind": "approve"}, {"name": "bpdu-recover"}, found())
        assert got == "A saved script can fix this: bpdu-recover"


def test_nothing_to_say_and_nothing_standing_says_nothing():
    assert S._why_person({"kind": "none"}, None, found()) == ""
    assert S._why_person({}, None, found()) == ""


def test_the_status_line_is_the_reason_while_a_person_is_needed(web, monkeypatch):  # noqa: F811
    """A lost stream nothing has tried (the section world's plant): the card's status line is
    `_why_person`'s reason, here the retry policy's for a lost stream (Mercury has no fix it
    runs by itself; the AI can investigate). The drawn section no longer carries
    ``why_person`` (67b90db3's sibling 4643e9bf: only `view` keeps it), so the reason is read
    from the `view` the page's section was drawn from."""
    from modules import incident_page as IP
    seen = []
    real_view = S.view

    def view(*a, **kw):
        out = real_view(*a, **kw)
        seen.append(dict(out))           # a copy: `drawn` pops why_person from the one it gets
        return out
    monkeypatch.setattr(S, "view", view)
    fixit = IP.page(NET, plant(), attention={})["fixit"]
    status = fixit["status"]
    assert "why_person" not in fixit
    assert seen and status == seen[-1]["why_person"], (status, seen and seen[-1]["why_person"])
    assert status.startswith("Mercury has no fix it runs by itself for a lost stream"), status
    # And, its network's automatic troubleshooting off, that the switch is off (ruling 12, the
    # operator, 2026-11-18: "restore 'the switch is off' on the lost stream's status line").
    assert status.endswith(
        "The AI can investigate, but automatic troubleshooting is off for this network"), status
