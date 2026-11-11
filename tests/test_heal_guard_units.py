"""Three heal decisions held directly, each by its own inputs and its whole answer: the tier
of a kind (`decide._tier`), guard 14 (`guards.g14_rolled_back`), guard 12 (`guards.g12_size`),
and the adjacency revert's question (`kinds._revert_allowed`).

The weekly mutation measurement's run 72 (2026-11-09, C2895) left 67 open survivors in these
four functions: every one of guard 14's mutants survived, because nothing asked the guard
itself. The heal pipeline's tests reach them through whole decisions, where a wrong tier or a
guard that never fires reads as another refusal. Each test below fails on the mutants its
docstring names (applied one at a time, 2026-11-11).
"""

import calendar
import time

import pytest

from modules.heal import decide as D
from modules.heal import guards as G
from modules.heal import kinds as K

R1, R2 = "r1", "r2"
#: The newest halt's instant, and times either side of it.
BEFORE, AT, AFTER, LATER, LATEST = ("2026-10-26T06:00:00Z", "2026-10-26T06:13:20Z",
                                    "2026-10-26T07:00:00Z", "2026-10-26T08:00:00Z",
                                    "2026-10-26T09:00:00Z")
HALT = float(calendar.timegm(time.strptime(AT, "%Y-%m-%dT%H:%M:%SZ")))


def decision(did, device, outcome="rolled_back", at=AFTER):
    return {"id": did, "device": device, "applied": {"outcome": outcome, "at": at}}


class TestTheTierOfAKind:
    def test_a_kind_nobody_declared_is_tier_4(self):
        """Mutants 2 to 5 of `_tier`: the default is 4, never None and never 5."""
        assert D._tier("a-kind-nobody-declared") == 4
        assert D._tier("") == 4

    @pytest.mark.parametrize("kind, tier", [("missing_line", 1), ("process_reset", 2),
                                            ("physical", 3), ("credentials", 4)])
    def test_a_declared_kind_has_its_own_tier(self, kind, tier):
        """Mutants 1 and 3 of `_tier`: the kind asked about is the one looked up."""
        assert D._tier(kind) == tier


class TestGuard14ARolledBackHeal:
    def test_a_rollback_of_the_device_after_the_last_halt_halts_naming_the_newest(self):
        """Three rollbacks of r1 after the halt: the newest is the one named, in the words and
        in what is recorded. The whole answer, so each of its parts is held."""
        rows = [decision("hd-1", R1, at=AFTER), decision("hd-2", R1, at=LATER),
                decision("hd-3", R1, at=LATEST)]
        assert G.g14_rolled_back(rows, R1, HALT) == {
            "guard": 14, "name": "a rolled-back heal", "outcome": "halted",
            "words": ("the heal of r1 (hd-3) was rolled back, and the policy halts until a "
                      "person lifts it"),
            "operands": {"decision": "hd-3"}, "until": None}

    def test_one_before_the_halt_or_at_its_instant_does_not(self):
        """The halt that rollback wrote is in force already (guard 2's): only one AFTER it."""
        assert G.g14_rolled_back([decision("hd-1", R1, at=BEFORE)], R1, HALT) is None
        assert G.g14_rolled_back([decision("hd-1", R1, at=AT)], R1, HALT) is None
        assert G.g14_rolled_back([decision("hd-1", R1, at=AFTER)], R1, HALT)["guard"] == 14

    @pytest.mark.parametrize("never", [0, 0.0, None])
    def test_with_no_halt_ever_recorded_any_dated_rollback_halts(self, never):
        """No halt is epoch 0, so a rollback dated one second into the epoch is after it."""
        got = G.g14_rolled_back([decision("hd-1", R1, at="1970-01-01T00:00:01Z")], R1, never)
        assert got is not None and got["operands"] == {"decision": "hd-1"}

    def test_another_device_s_rollback_does_not(self):
        rows = [decision("hd-1", R2, at=AFTER)]
        assert G.g14_rolled_back(rows, R1, HALT) is None
        assert G.g14_rolled_back(rows, R2, HALT)["operands"] == {"decision": "hd-1"}

    @pytest.mark.parametrize("outcome", ["healed", "dampened", "ROLLED_BACK", "", None])
    def test_an_outcome_that_is_not_a_rollback_does_not(self, outcome):
        assert G.g14_rolled_back([decision("hd-1", R1, outcome=outcome)], R1, HALT) is None

    def test_a_decision_never_applied_does_not_and_does_not_raise(self):
        rows = [{"id": "hd-1", "device": R1}, {"id": "hd-2", "device": R1, "applied": None},
                {"id": "hd-3", "device": R1, "applied": {}}]
        assert G.g14_rolled_back(rows, R1, HALT) is None
        assert G.g14_rolled_back([], R1, HALT) is None

    def test_a_rollback_with_no_readable_time_is_not_after_any_halt(self):
        for at in (None, "", "not a time"):
            assert G.g14_rolled_back([decision("hd-1", R1, at=at)], R1, HALT) is None


def unit(op="remove", chain=(), lines=("line",), stanza=False):
    return {"op": op, "chain": list(chain), "lines": list(lines), "stanza": stanza}


class TestGuard12TheProgramsSize:
    def test_more_removals_than_allowed_is_refused_recording_both_numbers(self):
        units = [unit("remove", ["interface GigabitEthernet0/1"]),
                 unit("remove", ["interface GigabitEthernet0/2"]),
                 unit("remove", ["router ospf 1"]), unit("add", ["router ospf 1"])]
        assert G.g12_size(units, 2, 50) == {
            "guard": 12, "name": "the program's size", "outcome": "cant_fix",
            "words": ("the heal would remove 3 units (a unit is one feature on one section, "
                      "N13), more than 2"),
            "operands": {"removal_units": 3, "heal_max_removed_units": 2}, "until": None}
        assert G.g12_size(units, 3, 50) is None

    def test_units_under_a_section_are_counted_by_that_section(self):
        """Mutant 9: a unit with a chain belongs to its chain's first line."""
        units = [unit("add", ["interface GigabitEthernet0/1"]),
                 unit("add", ["interface GigabitEthernet0/2"]),
                 unit("add", ["interface GigabitEthernet0/2", "service-policy"])]
        got = G.g12_size(units, 50, 1)
        assert got["operands"] == {"sections": 2, "heal_max_units": 1}
        assert got["words"] == "the heal spans 2 sections, more than 1: never a partial heal"
        assert G.g12_size(units, 50, 2) is None

    def test_a_stanza_with_no_chain_is_its_own_first_line(self):
        """Mutants 16 and 18 to 23: two stanzas at the top level are two sections, each named
        by its FIRST line (their second lines are the same)."""
        units = [unit("add", lines=["router ospf 1", " network 192.0.2.0 0.0.0.255 area 0"],
                      stanza=True),
                 unit("add", lines=["router ospf 2", " network 192.0.2.0 0.0.0.255 area 0"],
                      stanza=True)]
        assert G.g12_size(units, 50, 1)["operands"] == {"sections": 2, "heal_max_units": 1}
        assert G.g12_size(units, 50, 2) is None

    def test_global_lines_with_no_chain_are_one_section_together(self):
        """Mutant 17: two different global lines are the global configuration, once."""
        units = [unit("add", lines=["ip routing"]), unit("add", lines=["ipv6 unicast-routing"])]
        assert G.g12_size(units, 50, 1) is None
        # And beside a stanza they are two: the global configuration, and the stanza.
        both = units + [unit("add", lines=["router ospf 1", " router-id 192.0.2.1"],
                             stanza=True)]
        assert G.g12_size(both, 50, 1)["operands"] == {"sections": 2, "heal_max_units": 1}


class TestTheAdjacencyRevertsQuestion:
    @pytest.mark.parametrize("op", ["remove", "change"])
    def test_a_removal_or_a_change_on_an_interface_or_a_routing_process_is_allowed(self, op):
        """Mutants 10 and 11 of `_revert_allowed`: a change counts as a removal does."""
        for section in ("interface GigabitEthernet0/1", "router ospf 1", "ipv6 router ospf 1"):
            assert K._revert_allowed(unit(op, [section]), True) is True

    def test_an_addition_another_section_or_the_question_off_is_not(self):
        assert K._revert_allowed(unit("add", ["interface GigabitEthernet0/1"]), True) is False
        assert K._revert_allowed(unit("change", ["line vty 0 4"]), True) is False
        assert K._revert_allowed(unit("change", []), True) is False
        assert K._revert_allowed(unit("change", ["router ospf 1"]), False) is False
