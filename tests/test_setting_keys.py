"""C193: which lines set the SAME setting, across a negation, on real configs.

`_command_keys` dropped a line's last word as its "value", so a `no` form's
own second word was taken for one: `no logging buffered` and `no logging
console` both keyed as `logging`, and any two such lines under one parent
were "the same setting". Measured on s4's real config (2026-09-28): with `no
logging buffered` added beside s4's own `no logging console`, `classify_diff`
reported NOTHING. Consumers: Mode B's removable list (could not offer it),
the previews' "will NOT be removed" (omitted it), and the rollback's
previous-value lookup (could re-send the sibling).

The fix: a `no` form takes no value, so its key is its whole remainder, and a
`no` line pairs with a positive one by PREFIX (IOS names the setting by its
leading words). Positive-to-positive keys are unchanged: measured over the
nine fleet configs, re-keying positives would have split 119 line shapes,
including single-instance settings whose replacement pairing matters
(`logging trap`), where this change moves only what C193 names.
"""

import glob
import os

import pytest

from modules.nsot.deploy import (RollbackNotInverse, assert_rollback_provenance,
                                 classify_diff, rollback_commands)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
S4 = open(os.path.join(FLEET, "s4.cfg"), encoding="utf-8").read()


def _with(config: str, *lines: str) -> str:
    return config.rstrip("\n") + "\n" + "\n".join(lines) + "\n"


class TestTheFixtureCanExhibitTheCase:
    def test_s4_carries_the_sibling_that_collided(self):
        assert "\nno logging console\n" in S4
        assert "no logging buffered" not in S4


class TestTwoNegationsAreTwoSettings:
    def test_a_leftover_no_line_beside_s4s_own_is_residue(self):
        d = classify_diff(S4, _with(S4, "no logging buffered"))
        assert d["residue"] == ["no logging buffered"], d
        assert d["add"] == [] and d["replace"] == []

    def test_the_reverse_is_an_add_not_a_replacement_of_the_sibling(self):
        d = classify_diff(_with(S4, "no logging buffered"), S4)
        assert d["add"] == ["no logging buffered"], d
        assert d["replace"] == []


class TestANegationPairsWithWhatItNegates:
    def test_a_no_form_and_the_positive_with_a_value(self):
        d = classify_diff(_with(S4, "logging buffered 8192 debugging"),
                          _with(S4, "no logging buffered"))
        assert d["replace"] == [{"line": "logging buffered 8192 debugging",
                                 "old": "no logging buffered",
                                 "new": "logging buffered 8192 debugging"}], d
        assert d["residue"] == [] and d["add"] == []

    def test_a_no_form_and_its_valueless_positive(self):
        base = "hostname x\n"
        d = classify_diff(_with(base, "ip http server"), _with(base, "no ip http server"))
        assert [r["old"] for r in d["replace"]] == ["no ip http server"], d
        assert d["residue"] == []

    def test_never_across_different_words(self):
        """`no ip http server` and `ip http secure-server` shared the key `ip
        http` before; they are two settings."""
        base = "hostname x\nip http secure-server\n"
        d = classify_diff(base, _with(base, "no ip http server"))
        assert d["residue"] == ["no ip http server"], d

    def test_passive_interface_by_its_interface(self):
        target = "router ospf 1\n passive-interface Loopback0\n"
        running = "router ospf 1\n passive-interface Loopback0\n no passive-interface Vlan99\n"
        d = classify_diff(target, running)
        assert d["residue"] == [" no passive-interface Vlan99"], d

    def test_an_ambiguous_positive_pairs_with_nothing(self):
        """`no ip address` against TWO addresses is not a pairing."""
        target = ("interface Vlan10\n ip address 192.0.2.1 255.255.255.0\n"
                  " ip address 192.0.2.2 255.255.255.0 secondary\n")
        running = "interface Vlan10\n no ip address\n"
        d = classify_diff(target, running)
        assert d["residue"] == [" no ip address"], d


class TestTheRollback:
    def test_a_pushed_no_line_is_undone_with_the_value_the_device_held(self):
        pre = _with(S4, "logging buffered 8192 debugging")
        pushed = ["no logging buffered"]
        rb = rollback_commands(pushed, pre)
        assert rb == ["logging buffered 8192 debugging"], rb
        assert_rollback_provenance(rb, pushed, pre)

    def test_never_by_re_sending_the_sibling(self):
        """Consumer 4: with only `no logging console` on the device, undoing a
        pushed `logging buffered 8192` negates it; it does not re-send the
        sibling the old key paired it with."""
        pushed = ["logging buffered 8192"]
        rb = rollback_commands(pushed, S4)
        assert rb == ["no logging buffered 8192"], rb
        assert "no logging console" not in rb

    def test_provenance_still_refuses_what_the_push_did_not_touch(self):
        with pytest.raises(RollbackNotInverse):
            assert_rollback_provenance(["logging console critical"],
                                       ["no logging buffered"], S4)


class TestTheFleet:
    CONFIGS = sorted(glob.glob(os.path.join(FLEET, "*.cfg")))

    def test_the_scan_finds_the_fleet(self):
        assert len(self.CONFIGS) >= 9

    @pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(FLEET, "*.cfg"))),
                             ids=os.path.basename)
    def test_every_device_is_equal_to_itself(self, path):
        text = open(path, encoding="utf-8").read()
        assert classify_diff(text, text) == {"add": [], "replace": [], "residue": []}

    def test_the_settings_the_old_key_merged_are_apart(self):
        """From the measurement over the nine configs: each pair shared a key
        before, and each is two settings."""
        for kept, extra in (("ip http secure-server", "no ip http server"),
                            ("ipv6 cef", "no ipv6 unicast-routing"),
                            ("service compress-config", "no service password-encryption")):
            base = f"hostname x\n{kept}\n"
            d = classify_diff(base, _with(base, extra))
            assert d["residue"] == [extra], (kept, extra, d)
