"""C506 phase 4 (the board approved 2026-10-06): the deploy card says, before the confirm, what
verify will check, each check naming the object it reads (never a count), what it expects and
when it reads; and the receipt records how verify compared the interfaces and the settle an
unexpected loss was given, which the result card says in words.

The rows come from the plan's own derived and declared effects (`expected_effects.verify_checks`),
the network's settle windows, the program's verify scope and BGP's hold time in the captured
config. The windows here are the convergence module's built-in defaults, a path independent of
the code under test.
"""

import pytest

from modules.nsot import convergence
from modules.nsot import expected_effects as fx
from tests.test_declared_effects import (END, INTENTS, MOVE, MOVE_PROGRAM, ROUTES, WHY,  # noqa
                                         _get, _part, _q, _reasons, _vals, card, deploy, lab)

CAPTURED_BGP = ("hostname r2\nrouter bgp 65001\n neighbor 198.51.100.1 remote-as 65002\n"
                " neighbor 198.51.100.1 timers 10 30\n")


@pytest.fixture
def windows(monkeypatch):
    monkeypatch.setattr(convergence, "window_for",
                        lambda check, list_name: dict(convergence.DEFAULT_WINDOWS.get(
                            check, convergence.DEFAULT_WINDOWS["default"])))
    return convergence.DEFAULT_WINDOWS


def _rows(declare=(), commands=MOVE_PROGRAM, captured=CAPTURED_BGP):
    effects = fx.for_device(INTENTS, "r2", commands)
    effects["offers"] = fx.offers(INTENTS, "r2", effects)
    effects["declared"], _p = fx.declared_from(list(declare), effects["offers"])
    return {r["check"]: r for r in fx.verify_checks(effects, commands=commands,
                                                    list_name="Lab", captured=captured)}


class TestTheRows:
    def test_each_derived_effect_is_a_named_check(self, windows):
        rows = _rows()
        assert rows["GigabitEthernet3 down"]["read"] == "at the first read"
        up = rows["GigabitEthernet4 up"]
        assert up["read"] == f"within the interfaces' settle window, {windows['interfaces']['timeout']} s"

    def test_a_declared_move_is_required_where_it_was_declared(self, windows):
        rows = _rows([MOVE])
        move = rows["OSPF to r1 (10.255.1.11) formed on GigabitEthernet4"]
        assert move["expects"] == "declared move, from GigabitEthernet3"
        assert move["read"] == f"within OSPF's settle window, {windows['ospf']['timeout']} s"

    def test_every_other_interface_names_its_settle(self, windows):
        other = _rows()["Every other interface up before the change"]
        assert f"after the {windows['unexpected']['timeout']} s settle" in other["read"]
        assert "rolled back at once" in other["read"]

    def test_an_adjacency_held_to_its_own_hold_time(self, windows):
        held = _rows()["BGP to 198.51.100.1"]
        assert held["expects"] == "held"
        assert held["read"] == "to its hold time, 30 s after the push", "the neighbour's timers"

    def test_an_ended_session_is_expected_gone_not_held(self, windows):
        rows = _rows([END])
        assert rows["BGP to 198.51.100.1 gone"]["expects"] == "declared end"
        assert "BGP to 198.51.100.1" not in rows

    def test_the_route_table_by_the_floor_verify_applies_or_declared(self, windows):
        from modules.pipeline import _ROUTE_RETENTION_MIN
        assert _rows()["The route table"]["expects"] == (
            f"back to {_ROUTE_RETENTION_MIN:.0%} of its routes before the change")
        assert _rows([ROUTES])["The route table"]["expects"] == (
            "declared to change: recorded, not a failure")

    def test_a_quick_verify_reads_each_new_line_back_and_holds_no_adjacency(self, windows):
        rows = _rows(commands=["line vty 0 4", " exec-timeout 10 0", "exit"])
        assert "Each new line" in rows and "The route table" not in rows
        assert "BGP to 198.51.100.1" not in rows


class TestTheCardDrawsThem:
    def test_what_verify_checks_under_expected_effects(self, card, windows):
        _r, page = _get(card, "/v2/device/r2/deploy?" + _reasons()[1:] + "&" + _q(
            mv_id=MOVE["id"], mv_to="GigabitEthernet4", mv_why=WHY))
        part = _part(page)
        assert "What verify checks" in part
        table = part.split('class="op-checks"')[1].split("</table>")[0]
        for words in ("GigabitEthernet3 down", "GigabitEthernet4 up",
                      "OSPF to r1 (10.255.1.11) formed on GigabitEthernet4",
                      "Every other interface up before the change", "The route table"):
            assert words in table, words
        assert "never a count" in part


RESULT_CHECKS = {"interfaces": {"compared_by": "name", "lost_expected": ["GigabitEthernet3"],
                                "came_up": ["GigabitEthernet4"], "lost_unexpected": []},
                 "unexpected_settle": None, "failed_at_once": False}


class TestTheRecordAndTheResult:
    def test_the_receipt_keeps_the_comparison_and_the_settle(self):
        from modules.nsot import receipts
        settle = {"seconds": 10, "elapsed": 10.0, "basis": "the installation's default"}
        result = {"device": "r2", "outcome": "failed", "commands": ["x"], "verify": {
            "ok": False, "interfaces": {"compared_by": "name", "lost_unexpected": ["Gi2"]},
            "expected_effects": {"down": ["GigabitEthernet3"], "up": []},
            "unexpected_settle": settle, "failed_at_once": True}}
        (row,) = receipts.rows_for({"results": [result], "golden": {}}, list_name="Lab",
                                   action="deploy", actor="t", actor_kind="person",
                                   confirmations={}, command_hashes={})
        c = row["checks"]
        assert c["interfaces"]["lost_unexpected"] == ["Gi2"] and c["failed_at_once"] is True
        assert c["unexpected_settle"] == settle
        assert c["expected_effects"]["down"] == ["GigabitEthernet3"]

    def _card(self, checks):
        from modules import device_actions

        class Ref:
            name = "Lab"
        got = {"state": "done", "payload": {"result": {
            "level": "success", "happened": {"targets": [{"name": "r2", "outcome": "deployed",
                                                          "words": "deployed"}]},
            "targets": [{"name": "r2", "checks": checks, "sent": {}, "rollback": {}}]}}}
        return device_actions.deploy_job_card(Ref(), "r2", "j", got)

    def test_the_result_says_how_the_interfaces_were_compared(self):
        lines = self._card(dict(RESULT_CHECKS))["checks"]
        assert ("Interfaces compared by name: GigabitEthernet3 down, as the program intends; "
                "GigabitEthernet4 came up.") in lines

    def test_the_result_names_the_settle_and_the_failure_at_once(self):
        lines = self._card(dict(RESULT_CHECKS, interfaces={
            "compared_by": "name", "lost_unexpected": ["GigabitEthernet2"]},
            unexpected_settle={"seconds": 10, "basis": "the installation's default"},
            failed_at_once=True))["checks"]
        assert any("GigabitEthernet2 down, which the program did not touch" in l for l in lines)
        assert ("An unexpected loss was read again after the 10 s settle (the installation's "
                "default); verify failed at once, without the routing protocols' windows."
                ) in lines

    def test_a_count_is_said_to_be_a_count(self):
        lines = self._card(dict(RESULT_CHECKS, interfaces={"compared_by": "count"}))["checks"]
        assert "Interfaces counted, not named: the read named none." in lines
