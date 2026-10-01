"""C307: a terminal-line range is never a stanza the push created (2026-10-01,
found computing the standardised vty change, C301).

On r1's REAL config (`line vty 0`, `line vty 1` with `length 0`, `line vty 2 4`),
intent giving all five lines one `line vty 0 4` stanza is a regrouping of lines
IOS already has. The rollback was `no line vty 0 4`, the lines the tool manages
through. Now it is the range's settings negated where not every line had them
and the old stanzas re-sent verbatim; its landing is judged by the header IOS
prints only when all five lines match; and the provenance guard admits the
re-sent stanzas and nothing else.
"""

import re

import pytest

from modules.nsot.deploy import (RollbackNotInverse, assert_rollback_provenance,
                                 created_containers, line_range_held, merge_commands,
                                 rollback_commands)

R1 = "tests/fixtures/configs/fleet/r1.cfg"
ONE = "line vty 0 4\n logging synchronous\n login local\n length 0\n transport input all\n"
OLD = ["line vty 0", " logging synchronous", " login local", " transport input all", "exit",
       "line vty 1", " logging synchronous", " login local", " length 0", " transport input all",
       "exit",
       "line vty 2 4", " logging synchronous", " login local", " transport input all", "exit"]


def _r1():
    return open(R1, encoding="utf-8").read()


def _vty_block(text):
    return re.search(r"(?ms)^line vty 0\n.*?^line vty 2 4\n(?: [^\n]*\n)*", text).group(0)


@pytest.fixture
def r1():
    pre = _r1()
    intended = pre.replace(_vty_block(pre), ONE)
    return pre, intended, merge_commands(intended, pre)


def _landed(pre, post):
    pre_set = {l.rstrip() for l in pre.splitlines()}
    return [l.rstrip() for l in post.splitlines() if l.strip() and l.rstrip() not in pre_set]


class TestTheRangeIsHeld:
    def test_the_program_sends_the_one_stanza(self, r1):
        assert r1[2] == ["line vty 0 4", " logging synchronous", " login local", " length 0",
                         " transport input all", "exit"]

    def test_a_range_the_device_has_is_not_created(self, r1):
        pre, _i, prog = r1
        assert line_range_held("line vty 0 4", pre)
        assert created_containers(prog, pre) == set()

    def test_a_range_beyond_the_device_s_lines_is_created(self, r1):
        # The control: vty 5 15 does not exist on r1, so configuring it does
        # create lines, and its undo is the single negation, as before.
        pre = r1[0]
        assert not line_range_held("line vty 5 15", pre)
        prog = ["line vty 5 15", " login local", "exit"]
        assert rollback_commands(prog, pre) == ["no line vty 5 15"]


class TestTheUndoPutsBackEachLine:
    def test_never_no_line_vty(self, r1):
        pre, _i, prog = r1
        undo = rollback_commands(prog, pre)
        assert not any(l.strip().startswith("no line") for l in undo)
        assert undo == ["line vty 0 4", " no length 0", "exit"] + OLD

    def test_after_the_push_landed_the_undo_is_the_same(self, r1):
        pre, intended, prog = r1
        # IOS after the push prints the one stanza: the post config IS intent.
        assert rollback_commands(prog, pre, landed=_landed(pre, intended)) == \
            ["line vty 0 4", " no length 0", "exit"] + OLD

    def test_a_push_that_did_not_land_undoes_nothing(self, r1):
        pre, _i, prog = r1
        assert rollback_commands(prog, pre, landed=_landed(pre, pre)) == []

    def test_the_read_back_after_the_undo_finds_nothing_left(self, r1):
        # C112's restored check: the undo computed again against the device
        # read back, here back at its old stanzas.
        pre, _i, prog = r1
        # Back at its old stanzas, with an unrelated line new since (the
        # read-back is a whole config, never only the push's lines).
        post = pre.replace("hostname r1\n", "hostname r1\nip domain lookup source-interface Loopback0\n")
        assert rollback_commands(prog, pre, landed=_landed(pre, post)) == []

    def test_a_replaced_value_is_negated_and_the_old_one_restored(self):
        # r6's REAL vty form: `transport input ssh` on every line.
        pre = _r1().replace(" transport input all", " transport input ssh")
        intended = pre.replace(_vty_block(pre), ONE)
        prog = merge_commands(intended, pre)
        undo = rollback_commands(prog, pre)
        assert undo[:4] == ["line vty 0 4", " no length 0", " no transport input all", "exit"]
        assert " transport input ssh" in undo and not any("no line" in l for l in undo)

    def test_nothing_changed_is_nothing_to_undo(self, r1):
        pre, _i, _p = r1
        prog = ["line vty 0 4", " login local", "exit"]   # every line already had it
        assert rollback_commands(prog, pre) == []


class TestTheGuard:
    def test_the_undo_traces_to_the_push(self, r1):
        pre, _i, prog = r1
        assert_rollback_provenance(rollback_commands(prog, pre), prog, pre_config=pre)

    def test_a_setting_the_old_stanzas_did_not_hold_is_refused(self, r1):
        pre, _i, prog = r1
        with pytest.raises(RollbackNotInverse):
            assert_rollback_provenance(rollback_commands(prog, pre)
                                       + ["line vty 1", " exec-timeout 0 0", "exit"],
                                       prog, pre_config=pre)

    def test_without_the_snapshot_the_stanzas_are_orphans(self, r1):
        pre, _i, prog = r1
        with pytest.raises(RollbackNotInverse):
            assert_rollback_provenance(rollback_commands(prog, pre), prog)
