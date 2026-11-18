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
    """Guard 14 is retired (70e89a47, the operator, 2026-11-17, round 2: "guard 14 and every
    halt write" removed; a rolled-back heal is a failure R1 sees, and verify and rollback are
    the safety): `g14_rolled_back` halts nothing, whatever rollbacks it is shown. Each test
    keeps the case it was written for and holds that it no longer halts."""

    def test_a_rollback_of_the_device_after_the_last_halt_halts_naming_the_newest(self):
        """Three rollbacks of r1 after the last halt, the case that halted naming the newest:
        it halts nothing now."""
        rows = [decision("hd-1", R1, at=AFTER), decision("hd-2", R1, at=LATER),
                decision("hd-3", R1, at=LATEST)]
        assert G.g14_rolled_back(rows, R1, HALT) is None

    def test_one_before_the_halt_or_at_its_instant_does_not(self):
        """Before, at and after the last halt's instant alike: none halts."""
        for at in (BEFORE, AT, AFTER):
            assert G.g14_rolled_back([decision("hd-1", R1, at=at)], R1, HALT) is None

    @pytest.mark.parametrize("never", [0, 0.0, None])
    def test_with_no_halt_ever_recorded_any_dated_rollback_halts(self, never):
        """No halt ever recorded, a rollback dated after the epoch: it halts nothing now."""
        assert G.g14_rolled_back([decision("hd-1", R1, at="1970-01-01T00:00:01Z")], R1,
                                 never) is None

    def test_another_device_s_rollback_does_not(self):
        """Neither another device's rollback nor the device's own halts."""
        rows = [decision("hd-1", R2, at=AFTER)]
        assert G.g14_rolled_back(rows, R1, HALT) is None
        assert G.g14_rolled_back(rows, R2, HALT) is None

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
    """Guard 12 is retired (70e89a47, the operator, 2026-11-17, round 2: "a program's size
    refuses nothing; verify and rollback are the safety"): `g12_size` refuses nothing, however
    many removals or sections, at any limit. Each test keeps the program it was written for and
    holds that it is no longer refused."""

    def test_more_removals_than_allowed_is_refused_recording_both_numbers(self):
        """Three removal units against a limit of 2, the case that was refused: not now."""
        units = [unit("remove", ["interface GigabitEthernet0/1"]),
                 unit("remove", ["interface GigabitEthernet0/2"]),
                 unit("remove", ["router ospf 1"]), unit("add", ["router ospf 1"])]
        for most_removed in (0, 2, 3):
            assert G.g12_size(units, most_removed, 50) is None

    def test_units_under_a_section_are_counted_by_that_section(self):
        """Two sections against a limit of 1, the case that was refused: not now."""
        units = [unit("add", ["interface GigabitEthernet0/1"]),
                 unit("add", ["interface GigabitEthernet0/2"]),
                 unit("add", ["interface GigabitEthernet0/2", "service-policy"])]
        for most_sections in (0, 1, 2):
            assert G.g12_size(units, 50, most_sections) is None

    def test_a_stanza_with_no_chain_is_its_own_first_line(self):
        """Two top-level stanzas against a limit of 1: not refused now."""
        units = [unit("add", lines=["router ospf 1", " network 192.0.2.0 0.0.0.255 area 0"],
                      stanza=True),
                 unit("add", lines=["router ospf 2", " network 192.0.2.0 0.0.0.255 area 0"],
                      stanza=True)]
        assert G.g12_size(units, 50, 1) is None
        assert G.g12_size(units, 50, 2) is None

    def test_global_lines_with_no_chain_are_one_section_together(self):
        """Global lines, alone or beside a stanza, against a limit of 1: not refused now."""
        units = [unit("add", lines=["ip routing"]), unit("add", lines=["ipv6 unicast-routing"])]
        assert G.g12_size(units, 50, 1) is None
        both = units + [unit("add", lines=["router ospf 1", " router-id 192.0.2.1"],
                             stanza=True)]
        assert G.g12_size(both, 50, 1) is None


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
