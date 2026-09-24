"""A stanza the device does not have yet: the case no fixture could reach.

**Why this file exists rather than more assertions in `TestMergeCommands`.**
That class's assertions are *exact* — `test_each_group_is_unwound_one_exit_per_level`
compares the whole command list — and they would have caught the duplicated
header outright. They never could, because its `RUNNING` fixture contains
`interface GigabitEthernet0/1`, `interface GigabitEthernet0/2`,
`router bgp 65001` and ` address-family ipv4`: **every container already exists
on the device**, so no header is ever in `to_add` and the duplicating branch is
unreachable.

The natural fixture to write for a merge path — *"a sub-command gets its
parent"* — has the parent present **by construction**. You cannot demonstrate
that a child is given its header unless the header is already somewhere, and
the obvious place to put it is the device.

So this is a **fixture that cannot exhibit the case**: the test was correct and
the world it tested in was too small. Siblings in this project:

* `FakeNetBox` had no foreign keys, so the harness could not cascade — and the
  cascade was the defect;
* `SourceFileLoader.exec_module()` runs a module with `__name__` set, so the
  `if __name__ == "__main__"` guard never fires and a definition stranded below
  it is reachable in the test and absent in the program.

Each time: exact assertions, sound logic, an input that could never reach them.
"""

import pytest

from modules.nsot.deploy import (assert_rollback_provenance, created_containers,
                                 merge_commands, rollback_commands)

#: The device has a hostname and nothing else. **Every container in the
#: intended config is therefore new**, which is the whole point.
BARE = "hostname r6\nend\n"


def _dupes(commands):
    """Adjacent duplicate **configuration**, not duplicate unwinding.

    Two `exit` lines in a row are correct — one per open level — so a naive
    adjacent-equality check reports the two-level case as a defect. Caught by
    this file's own bgp fixture on its first run, which is the argument for
    having a fixture that reaches two levels at all.
    """
    from modules.nsot.deploy import CONTROL_WORDS

    return [c for i, c in enumerate(commands)
            if i and c == commands[i - 1] and c.strip() not in CONTROL_WORDS]


class TestANewContainerIsEmittedOnce:

    def test_a_new_interface(self):
        commands = merge_commands(
            "hostname r6\ninterface Loopback0\n description branch site identity\n"
            " ip address 10.255.1.16 255.255.255.255\nend\n", BARE)
        assert commands == [
            "interface Loopback0",
            " description branch site identity",
            " ip address 10.255.1.16 255.255.255.255",
            "exit",
        ]

    def test_a_new_routing_process(self):
        """Not interface-specific: it fired for every brand-new stanza."""
        commands = merge_commands(
            "hostname r6\nrouter ospf 1\n router-id 10.255.1.16\nend\n", BARE)
        assert commands == ["router ospf 1", " router-id 10.255.1.16", "exit"]

    def test_a_new_two_level_stanza_does_not_exit_and_re_enter(self):
        """The worse shape: the parent was closed and re-opened mid-stanza."""
        commands = merge_commands(
            "hostname r6\nrouter bgp 65010\n bgp log-neighbor-changes\n"
            " address-family ipv4\n  network 10.255.1.16 mask 255.255.255.255\n"
            "end\n", BARE)
        assert commands == [
            "router bgp 65010",
            " bgp log-neighbor-changes",
            " address-family ipv4",
            "  network 10.255.1.16 mask 255.255.255.255",
            "exit",
            "exit",
        ]
        assert commands.count("router bgp 65010") == 1
        assert commands.count(" address-family ipv4") == 1

    def test_an_existing_container_still_gets_its_child(self):
        """**The floor.** The property `TestMergeCommands` was written for
        must survive the fix — a child still gets its header."""
        commands = merge_commands(
            "hostname r6\ninterface Loopback0\n description new\n"
            " ip address 10.255.1.16 255.255.255.255\nend\n",
            "hostname r6\ninterface Loopback0\n"
            " ip address 10.255.1.16 255.255.255.255\nend\n")
        assert commands == ["interface Loopback0", " description new", "exit"]


class TestNoProgramHasAdjacentDuplicates:
    """The check, on fixtures that can actually contain one."""

    CASES = [
        ("new interface", "interface Loopback0\n description x\n ip address 10.0.0.1 255.255.255.0\n"),
        ("new ospf", "router ospf 1\n router-id 10.255.1.16\n network 10.0.0.0 0.0.0.255 area 0\n"),
        ("new bgp two-level", "router bgp 65010\n bgp log-neighbor-changes\n address-family ipv4\n  network 10.255.1.16 mask 255.255.255.255\n"),
        ("new vlan", "vlan 99\n name MGMT\n"),
        ("new line", "line vty 0 4\n login local\n transport input ssh\n"),
    ]

    @pytest.mark.parametrize("label,body", CASES, ids=[c[0] for c in CASES])
    def test_no_adjacent_duplicate(self, label, body):
        commands = merge_commands("hostname r6\n" + body + "end\n", BARE)
        assert _dupes(commands) == [], f"{label}: {commands}"

    def test_the_fixtures_can_actually_contain_one(self):
        """**The floor**, and it is the reason this file exists.

        Every case above must introduce a container the device lacks. A
        duplicate check over programs that cannot duplicate is the
        `TestMergeCommands` situation again, one layer up.
        """
        for label, body in self.CASES:
            commands = merge_commands("hostname r6\n" + body + "end\n", BARE)
            created = created_containers(commands, BARE)
            assert created, f"{label} introduced no new container"
            assert len(commands) >= 3, f"{label} produced a trivial program"


class TestUndoingACreationRemovesIt:
    """Latent since the merge path was built, and only visible during a
    rollback — the one moment nobody is placed to notice, because they are
    already dealing with a failed push."""

    PUSHED = ["interface Loopback0", " description branch site identity",
              " ip address 10.255.1.16 255.255.255.255", "exit"]

    def test_the_rollback_is_the_single_negation(self):
        undo = rollback_commands(self.PUSHED, BARE)
        assert undo == ["no interface Loopback0"]

    def test_it_is_not_self_cancelling(self):
        """With the duplicated header, `program_structure` called the first
        copy a leaf and the rollback came out as `no interface Loopback0`
        followed by `interface Loopback0` — deleting it and recreating it."""
        undo = rollback_commands(self.PUSHED, BARE)
        assert "interface Loopback0" not in undo, \
            "the rollback re-enters the section it just removed"

    def test_it_leaves_no_empty_shell(self):
        """Deduplicating alone would have produced the child negations and
        left the stanza behind — quieter, still wrong."""
        undo = rollback_commands(self.PUSHED, BARE)
        assert not any("description" in c or "ip address" in c for c in undo)

    def test_an_existing_container_still_negates_its_children(self):
        """**The floor.** The single negation must not swallow the ordinary
        case, where the section pre-exists and only the child is new."""
        pre = ("hostname r6\ninterface Loopback0\n"
               " ip address 10.255.1.16 255.255.255.255\nend\n")
        undo = rollback_commands(
            ["interface Loopback0", " description new", "exit"], pre)
        assert undo == ["interface Loopback0", " no description new", "exit"]

    def test_provenance_accepts_it_only_when_told_the_prior_config(self):
        """The optional argument can only TIGHTEN, which is what makes it
        safe — the bypassed-by-omission shape is an optional argument that
        can only loosen."""
        undo = rollback_commands(self.PUSHED, BARE)
        assert_rollback_provenance(undo, self.PUSHED, BARE)   # permitted
        from modules.nsot.deploy import RollbackNotInverse

        with pytest.raises(RollbackNotInverse):
            assert_rollback_provenance(undo, self.PUSHED)     # strict default


class TestACreationIsUndoneOnlyIfItLanded:
    """`landed` already governed the leaves; a container needed its own check
    or a push rejected at its first line would be "undone" by negating a
    section that was never created."""

    PUSHED = ["interface Loopback0", " description x", "exit"]

    def test_nothing_landed_undoes_nothing(self):
        assert rollback_commands(self.PUSHED, BARE, landed=[]) == []

    def test_the_container_landed_and_is_removed(self):
        assert rollback_commands(self.PUSHED, BARE,
                                 landed=["interface Loopback0"]) == \
            ["no interface Loopback0"]

    def test_an_unreadable_capture_is_conservative(self):
        assert rollback_commands(self.PUSHED, BARE, landed=None) == \
            ["no interface Loopback0"]


class TestAnEmptySnapshotIsNotEvidence:
    """Absent and empty are different facts. A capture that came back blank
    would otherwise make every section look created, and the repair would be
    `no` on all of them — the worst push this tool could produce."""

    def test_an_empty_pre_config_creates_nothing(self):
        assert created_containers(["interface Loopback0", " description x",
                                   "exit"], "") == set()

    def test_and_the_rollback_falls_back_to_child_negation(self):
        undo = rollback_commands(["interface Loopback0", " description x",
                                  "exit"], "")
        assert undo == ["interface Loopback0", " no description x", "exit"]

    def test_the_control_a_real_snapshot_does_detect_creation(self):
        assert created_containers(["interface Loopback0", " description x",
                                   "exit"], BARE)
