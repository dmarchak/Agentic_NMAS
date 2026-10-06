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
                                 classify_diff, landed_between, rollback_commands)

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


R2 = open(os.path.join(FLEET, "r2.cfg"), encoding="utf-8").read()


class TestAPushedNoLineWithNothingToPair:
    """C200, on r2's REAL config (it holds no `logging console` line in either
    form): undoing a pushed `no X` the device held nothing for sent `no no X`,
    which IOS refuses. The undo is X, the setting back at its default, and only
    when the `no` line is known to have landed."""

    def test_the_fixture_can_exhibit_the_case(self):
        lines = [line.strip() for line in R2.splitlines()]
        assert not any(line.endswith("logging console") for line in lines)
        assert "interface GigabitEthernet2" in lines

    def test_a_landed_no_line_is_undone_by_its_positive(self):
        pushed = ["no logging console"]
        rb = rollback_commands(pushed, R2, landed=landed_between(R2, R2 + "no logging console\n"))
        assert rb == ["logging console"], rb
        assert not any(line.strip().startswith("no no") for line in rb)
        assert_rollback_provenance(rb, pushed, R2)

    def test_with_nothing_read_it_is_left_alone_never_negated(self):
        """landed None (the capture could not read the device): everything
        pushed is treated as applied, and a `no` line cannot be decided, since
        IOS never prints some `no` forms. Neither `no no X` nor X is sent."""
        rb = rollback_commands(["no logging console"], R2, landed=None)
        assert rb == [], rb

    def test_no_shutdown_on_an_up_interface_is_never_undone_as_shutdown(self):
        """The trap in the naive fix: IOS omits `no shutdown` from an up
        interface, so it never lands, and re-sending `shutdown` would take an
        interface down that was up before the deploy."""
        pushed = ["interface GigabitEthernet2", " no shutdown", "exit"]
        for landed in ([], None):
            rb = rollback_commands(pushed, R2, landed=landed)
            assert not any(line.strip() == "shutdown" for line in rb), (landed, rb)

    def test_a_positive_line_is_still_negated_the_control(self):
        rb = rollback_commands(["logging console critical"], R2,
                               landed=landed_between(R2, R2 + "logging console critical\n"))
        assert rb == ["no logging console critical"], rb


S1 = open(os.path.join(FLEET, "s1.cfg"), encoding="utf-8").read()


class TestASharedKeyIsNamedNotHidden:
    """C201, the operator's option (b), on s1's REAL config (it holds both
    `ipv6 cef` and `ipv6 unicast-routing`, which share the key `ipv6`): with
    intent lacking `ipv6 cef`, the line was neither residue nor a replacement,
    because its key-mate is kept. So nothing removed it and nothing said so.
    It is named now, with the line it collides with, and not offered."""

    def _intent_without_cef(self):
        return "\n".join(l for l in S1.splitlines() if l.strip() != "ipv6 cef") + "\n"

    def test_the_fixture_can_exhibit_the_case(self):
        lines = {l.strip() for l in S1.splitlines()}
        assert {"ipv6 cef", "ipv6 unicast-routing"} <= lines

    def test_the_hidden_line_is_named_with_its_mate(self):
        out = classify_diff(self._intent_without_cef(), S1)
        assert "ipv6 cef" not in [l.strip() for l in out["residue"]]
        assert [(s["line"].strip(), s["with"].strip()) for s in out["shares_key"]] == [
            ("ipv6 cef", "ipv6 unicast-routing")], out["shares_key"]

    def test_a_real_replacement_is_not_a_collision_the_control(self):
        """`logging trap critical` against intent's `notifications` is a
        replacement: the intent line is NOT on the device, so it replaces."""
        running = _with(S1, "logging trap critical")
        intent = _with(S1, "logging trap notifications")
        out = classify_diff(intent, running)
        assert not any(s["line"].strip().startswith("logging trap")
                       for s in out["shares_key"]), out["shares_key"]
        assert any(r["old"].strip() == "logging trap critical" for r in out["replace"])

    def test_the_deploy_preview_draws_it(self):
        from modules.preview_confirm import deploy_preview

        d = {"hostname": "s1", "deployable": True, "commands": [], "dangerous": [],
             "shares_key": classify_diff(self._intent_without_cef(), S1)["shares_key"]}
        p = deploy_preview([d], request=None)
        item = next(i for i in p["what_not"]["items"] if i["kind"] == "shares_key")
        assert "C201" in item["text"] and "will NOT be removed" in item["text"]
        assert item["lines"] == ["ipv6 cef   (shares a setting key with `ipv6 unicast-routing`)"]


class TestTheFleet:
    CONFIGS = sorted(glob.glob(os.path.join(FLEET, "*.cfg")))

    def test_the_scan_finds_the_fleet(self):
        assert len(self.CONFIGS) >= 9

    @pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(FLEET, "*.cfg"))),
                             ids=os.path.basename)
    def test_every_device_is_equal_to_itself(self, path):
        text = open(path, encoding="utf-8").read()
        assert classify_diff(text, text) == {"add": [], "replace": [], "residue": [],
                                             "shares_key": []}

    def test_the_settings_the_old_key_merged_are_apart(self):
        """From the measurement over the nine configs: each pair shared a key
        before, and each is two settings."""
        for kept, extra in (("ip http secure-server", "no ip http server"),
                            ("ipv6 cef", "no ipv6 unicast-routing"),
                            ("service compress-config", "no service password-encryption")):
            base = f"hostname x\n{kept}\n"
            d = classify_diff(base, _with(base, extra))
            assert d["residue"] == [extra], (kept, extra, d)
