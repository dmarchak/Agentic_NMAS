"""Merge-only deploys, per-platform transport, concurrency, and the breaker.

Nothing here opens a socket: transport selection is asserted as a *decision*,
before any connection is attempted.
"""

import pytest

from modules.nsot import convergence, deploy
from modules.nsot.deploy import (
    CircuitBreaker, NegationSynthesised, assert_merge_only, max_workers,
    merge_diff, transport_for,
)

INTENDED = """hostname R1
no ip http server
ntp server 10.255.1.10
logging host 10.255.1.10
interface GigabitEthernet1
 description uplink
"""

RUNNING = """hostname R1
ip http server
snmp-server location old-site
interface GigabitEthernet1
 description uplink
"""


class TestMergeOnly:
    def test_adds_missing_lines(self):
        result = merge_diff(INTENDED, RUNNING)
        assert "ntp server 10.255.1.10" in result["to_add"]
        assert "logging host 10.255.1.10" in result["to_add"]

    def test_does_not_readd_present_lines(self):
        result = merge_diff(INTENDED, RUNNING)
        assert " description uplink" not in result["to_add"]
        assert result["unchanged_count"] > 0

    def test_device_only_lines_are_warnings_not_removals(self):
        result = merge_diff(INTENDED, RUNNING)
        assert "snmp-server location old-site" in result["removal_warnings"]
        # And crucially, nothing negates it.
        assert not any(c.strip().startswith("no snmp-server location")
                       for c in result["to_add"])

    def test_no_negation_is_ever_synthesised(self):
        """Provenance, not grepping for 'no'.

        A template may legitimately contain `no ip http server` — that is real
        configuration. What must never happen is this tool inventing one.
        """
        result = merge_diff(INTENDED, RUNNING)
        assert_merge_only(result["to_add"], INTENDED)

    def test_legitimate_no_line_from_the_template_is_allowed(self):
        result = merge_diff(INTENDED, RUNNING)
        assert "no ip http server" in result["to_add"]
        assert_merge_only(result["to_add"], INTENDED)

    def test_invented_command_is_refused(self):
        with pytest.raises(NegationSynthesised) as exc:
            assert_merge_only(["no snmp-server location old-site"], INTENDED)
        assert "not in the intended config" in str(exc.value)

    def test_interface_names_are_normalised_before_diffing(self):
        intended = "interface GigabitEthernet0/1\n description x\n"
        running = "interface Gi0/1\n description x\n"
        assert merge_diff(intended, running)["to_add"] == []


class TestTransportShortCircuit:
    """A platform without NETCONF must never have it attempted."""

    @pytest.fixture
    def platform_map(self, monkeypatch):
        def _get(key, default=None):
            if key == "platform_map":
                return {
                    "cisco-ios-xe": {"netmiko_device_type": "cisco_xe",
                                     "supports_netconf": True,
                                     "deploy_transport": "netconf"},
                    "cisco-ios": {"netmiko_device_type": "cisco_ios",
                                  "supports_netconf": False,
                                  "deploy_transport": "ssh"},
                }
            return default
        monkeypatch.setattr("modules.settings_schema.get_setting", _get)

    def test_platform_without_netconf_goes_straight_to_ssh(self, platform_map):
        assert transport_for("cisco-ios") == "ssh"

    def test_unknown_platform_goes_to_ssh(self, platform_map):
        assert transport_for("arista-eos") == "ssh"

    def test_netconf_requires_both_platform_and_global(self, platform_map, monkeypatch):
        monkeypatch.setattr("modules.config.get_user_setting",
                            lambda k, d=None: False)
        assert transport_for("cisco-ios-xe") == "ssh", \
            "the global switch did not veto NETCONF"

        monkeypatch.setattr("modules.config.get_user_setting",
                            lambda k, d=None: True)
        assert transport_for("cisco-ios-xe") == "netconf"

    def test_global_switch_cannot_enable_an_unsupported_platform(
            self, platform_map, monkeypatch):
        """The master switch disables everywhere; it never enables."""
        monkeypatch.setattr("modules.config.get_user_setting",
                            lambda k, d=None: True)
        assert transport_for("cisco-ios") == "ssh"

    def test_mixed_batch_makes_no_netconf_decision_for_switches(
            self, platform_map, monkeypatch):
        monkeypatch.setattr("modules.config.get_user_setting",
                            lambda k, d=None: True)
        fleet = ["cisco-ios-xe"] * 5 + ["cisco-ios"] * 4
        decisions = [transport_for(p) for p in fleet]
        assert decisions.count("ssh") == 4
        assert decisions.count("netconf") == 5


class TestCircuitBreaker:
    def test_does_not_trip_below_the_limit(self):
        breaker = CircuitBreaker(limit=2)
        assert breaker.record_verify_failure("r1") is False
        assert breaker.is_tripped is False

    def test_trips_at_the_limit(self):
        breaker = CircuitBreaker(limit=2)
        breaker.record_verify_failure("r1")
        assert breaker.record_verify_failure("r2") is True
        assert breaker.tripped_after == "r2"

    def test_reason_explains_and_names_the_device(self):
        breaker = CircuitBreaker(limit=1)
        breaker.record_verify_failure("r3")
        reason = breaker.reason()
        assert "not attempted" in reason and "r3" in reason

    def test_limit_comes_from_settings(self, monkeypatch):
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: 5 if k == "deploy_verify_failure_limit" else d)
        assert CircuitBreaker().limit == 5

    def test_drift_is_not_a_verify_failure(self):
        """One drifted device is someone touching a box; it must not trip."""
        breaker = CircuitBreaker(limit=2)
        assert breaker.is_tripped is False      # skipping a drifted device
        assert breaker.verify_failures == 0     # records nothing


class TestConcurrency:
    def test_sequential_by_default(self, monkeypatch):
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: d)
        assert max_workers() == 1

    def test_configurable_and_capped(self, monkeypatch):
        for configured, expected in ((4, 4), (99, 16), (0, 1), ("x", 1)):
            monkeypatch.setattr("modules.settings_schema.get_setting",
                                lambda k, d=None, v=configured:
                                v if k == "deploy_max_workers" else d)
            assert max_workers() == expected


class TestSettleWindows:
    def test_rip_window_spans_more_than_two_update_cycles(self):
        """RIP updates every 30s; one missed cycle is normal, two is not."""
        window = convergence.window_for("rip")
        assert window["timeout"] >= 60

    def test_ospf_settles_faster_than_rip(self):
        assert convergence.window_for("ospf")["timeout"] < \
            convergence.window_for("rip")["timeout"]

    def test_bgp_sits_between_them(self):
        ospf = convergence.window_for("ospf")["timeout"]
        bgp = convergence.window_for("bgp")["timeout"]
        rip = convergence.window_for("rip")["timeout"]
        assert ospf <= bgp <= rip

    def test_first_poll_waits(self):
        """The poll immediately after a change is the most misleading one."""
        assert convergence.window_for("rip")["initial_wait"] > 0

    def test_not_yet_converged_is_distinct_from_failed(self):
        assert convergence.classify(2, 1, settled=False) == convergence.NOT_YET
        assert convergence.classify(2, 1, settled=True) == convergence.FAILED

    def test_recovery_within_the_window_converges(self):
        counts = iter([0, 1, 2])
        result = convergence.wait_for("ospf", lambda: next(counts),
                                      lambda v: v >= 2, sleep=lambda s: None)
        assert result["state"] == convergence.CONVERGED
        assert result["attempts"] == 3

    def test_pending_does_not_fail_the_device(self):
        summary = convergence.summarise({"ospf": convergence.CONVERGED,
                                         "rip": convergence.NOT_YET})
        assert summary["ok"] is True
        assert summary["pending"] is True
        assert summary["not_yet_converged"] == ["rip"]

    def test_a_real_regression_fails_the_device(self):
        summary = convergence.summarise({"ospf": convergence.FAILED})
        assert summary["ok"] is False

    def test_settings_override_the_defaults(self, monkeypatch):
        monkeypatch.setattr(
            "modules.settings_schema.get_setting",
            lambda k, d=None: {"rip": {"timeout": 120}} if k == "verify_settle_windows" else d)
        assert convergence.window_for("rip")["timeout"] == 120
        assert convergence.window_for("rip")["interval"] == 15   # default kept


class TestMergeDiffPushesOnlyCommands:
    """A blank line is not configuration.

    ``to_add`` included every blank line the render produced, so a device with
    nothing to deploy still reported additions — "is there anything to do here"
    answered yes for every device, permanently. ``!`` and ``end`` were already
    excluded from removal warnings but not from additions; the filter is
    symmetric now.
    """

    def test_identical_configs_produce_no_additions(self):
        from modules.nsot.deploy import merge_diff
        config = "hostname s1\n!\n\ninterface Vlan10\n description x\n!\nend\n"
        assert merge_diff(config, config)["to_add"] == []

    def test_a_blank_line_is_never_an_addition(self):
        from modules.nsot.deploy import merge_diff
        diff = merge_diff("hostname s1\n\n\ninterface Vlan10\n", "hostname s1\n")
        assert "" not in diff["to_add"]
        assert diff["to_add"] == ["interface Vlan10"]

    def test_a_bang_is_never_an_addition(self):
        from modules.nsot.deploy import merge_diff
        diff = merge_diff("!\nhostname s1\n!\n", "hostname s1\n")
        assert diff["to_add"] == []

    def test_end_is_never_a_removal_warning(self):
        from modules.nsot.deploy import merge_diff
        diff = merge_diff("hostname s1\n", "hostname s1\n!\nend\n")
        assert diff["removal_warnings"] == []

    def test_a_real_addition_still_comes_through(self):
        from modules.nsot.deploy import merge_diff
        diff = merge_diff("hostname s1\n description NSoT-managed\n",
                          "hostname s1\n")
        assert diff["to_add"] == [" description NSoT-managed"]


class TestMergeCommandsAreSendable:
    """``merge_diff()`` answers what differs. That is not a program.

    ``' description NSoT-managed'`` is an interface sub-command; sent on its
    own it applies in global configuration mode. The pipeline hid this by
    pushing the whole rendered config, which also made ``assert_merge_only()``
    vacuous — ``to_push`` *was* the intended config, so it could not fail.
    """

    INTENDED = (
        "hostname s4\n"
        "interface GigabitEthernet0/1\n"
        " description NSoT-managed\n"
        " no shutdown\n"
        "interface GigabitEthernet0/2\n"
        " description other\n"
        "router bgp 65001\n"
        " address-family ipv4\n"
        "  neighbor 10.0.0.1 activate\n"
        "end\n"
    )
    RUNNING = (
        "hostname s4\n"
        "interface GigabitEthernet0/1\n"
        " no shutdown\n"
        "interface GigabitEthernet0/2\n"
        " description other\n"
        "router bgp 65001\n"
        " address-family ipv4\n"
        "end\n"
    )

    def test_a_sub_command_gets_its_parent(self):
        from modules.nsot.deploy import merge_commands
        commands = merge_commands(self.INTENDED, self.RUNNING)
        index = commands.index(" description NSoT-managed")
        assert commands[index - 1] == "interface GigabitEthernet0/1"

    def test_the_full_chain_is_emitted_in_order(self):
        """A partial chain applies the line to the wrong address family."""
        from modules.nsot.deploy import merge_commands
        commands = merge_commands(self.INTENDED, self.RUNNING)
        index = commands.index("  neighbor 10.0.0.1 activate")
        assert commands[index - 2] == "router bgp 65001"
        assert commands[index - 1] == " address-family ipv4"

    def test_each_group_is_unwound_one_exit_per_level(self):
        from modules.nsot.deploy import merge_commands
        commands = merge_commands(self.INTENDED, self.RUNNING)
        assert commands == [
            "interface GigabitEthernet0/1",
            " description NSoT-managed",
            "exit",
            "router bgp 65001",
            " address-family ipv4",
            "  neighbor 10.0.0.1 activate",
            "exit",
            "exit",
        ]

    def test_end_is_never_emitted(self):
        from modules.nsot.deploy import merge_commands
        commands = merge_commands(self.INTENDED, self.RUNNING)
        assert "end" not in [c.strip() for c in commands]

    def test_a_top_level_line_gets_no_exit(self):
        """An exit from global config mode leaves configuration mode."""
        from modules.nsot.deploy import merge_commands
        commands = merge_commands("hostname s4\nip routing\n", "hostname s4\n")
        assert commands == ["ip routing"]

    def test_nothing_to_change_is_an_empty_program(self):
        from modules.nsot.deploy import merge_commands
        assert merge_commands(self.RUNNING, self.RUNNING) == []

    def test_contiguous_lines_share_one_header(self):
        from modules.nsot.deploy import merge_commands
        intended = ("interface GigabitEthernet0/1\n"
                    " description a\n"
                    " mtu 9000\n")
        commands = merge_commands(intended, "interface GigabitEthernet0/1\n")
        assert commands == ["interface GigabitEthernet0/1",
                            " description a", " mtu 9000", "exit"]

    def test_assert_merge_only_now_has_something_to_check(self):
        """It could not fail while to_push was the whole intended config."""
        from modules.nsot.deploy import (NegationSynthesised, assert_merge_only,
                                         merge_commands)
        commands = merge_commands(self.INTENDED, self.RUNNING)
        assert_merge_only(commands, self.INTENDED)          # the real list passes

        with pytest.raises(NegationSynthesised):
            assert_merge_only(commands + ["no ip routing"], self.INTENDED)

    def test_exit_is_allowed_without_provenance_but_end_is_not(self):
        from modules.nsot.deploy import (NegationSynthesised, assert_merge_only)
        assert_merge_only(["hostname s4", "exit"], "hostname s4\n")
        with pytest.raises(NegationSynthesised):
            assert_merge_only(["hostname s4", "end"], "hostname s4\n")


class TestTheConfirmedProgramIsWhatIsSent:
    """One-shot discipline, the same shape as the Phase 0 plan token."""

    def test_the_fingerprint_is_stable(self):
        from modules.nsot.deploy import command_fingerprint
        assert (command_fingerprint(["interface Gi0/1", " description x"])
                == command_fingerprint(["interface Gi0/1", " description x"]))

    def test_a_changed_program_changes_the_fingerprint(self):
        from modules.nsot.deploy import command_fingerprint
        assert (command_fingerprint(["interface Gi0/1", " description x"])
                != command_fingerprint(["interface Gi0/1", " description y"]))

    def test_order_is_part_of_the_program(self):
        from modules.nsot.deploy import command_fingerprint
        assert (command_fingerprint(["a", "b"]) != command_fingerprint(["b", "a"]))

    def test_an_added_exit_changes_the_fingerprint(self):
        from modules.nsot.deploy import command_fingerprint
        assert (command_fingerprint(["interface Gi0/1", " description x"])
                != command_fingerprint(["interface Gi0/1", " description x", "exit"]))


class TestCommandsMustBeSendable:
    """Every guard built before this validated provenance and identity.

    Where a command came from, that it matched what was confirmed, that nothing
    was synthesised. None of them asked whether the bytes could be *sent*. An
    em dash reached a device as ``description NSoT-managed b`` — three UTF-8
    bytes, the first consumed, the rest of the line lost — and the failure
    surfaced as a Netmiko echo timeout, naming a pattern rather than the
    character.
    """

    def test_an_em_dash_is_refused_before_connecting(self):
        from modules.nsot.deploy import UnsendableCommand, merge_commands
        with pytest.raises(UnsendableCommand):
            merge_commands("interface Gi0/1\n description a — b\n",
                           "interface Gi0/1\n")

    def test_the_error_names_character_codepoint_and_column(self):
        from modules.nsot.deploy import UnsendableCommand, merge_commands
        with pytest.raises(UnsendableCommand) as exc:
            merge_commands("interface Gi0/1\n description a — b\n",
                           "interface Gi0/1\n")
        message = str(exc.value)
        assert "U+2014" in message
        assert "column" in message
        assert "—" in message

    def test_a_smart_quote_is_refused_too(self):
        from modules.nsot.deploy import UnsendableCommand, merge_commands
        with pytest.raises(UnsendableCommand):
            merge_commands("interface Gi0/1\n description “x”\n",
                           "interface Gi0/1\n")

    def test_plain_ascii_passes(self):
        from modules.nsot.deploy import merge_commands
        commands = merge_commands(
            "interface Gi0/1\n description NSoT-managed - CSCI 5840 Lab 4\n",
            "interface Gi0/1\n")
        assert commands == ["interface GigabitEthernet0/1",
                            " description NSoT-managed - CSCI 5840 Lab 4",
                            "exit"]

    def test_a_tab_is_refused(self):
        """A tab inside a config line is a real source of silent difference."""
        from modules.nsot.deploy import UnsendableCommand, assert_sendable
        with pytest.raises(UnsendableCommand):
            assert_sendable(["interface Gi0/1", " description a\tb"])

    def test_the_position_is_the_command_index(self):
        from modules.nsot.deploy import UnsendableCommand, assert_sendable
        with pytest.raises(UnsendableCommand) as exc:
            assert_sendable(["hostname s4", "interface Gi0/1", " description —"])
        assert "command 3 of 3" in str(exc.value)


class TestIosRejectionsAreDetected:
    """A cleanly rejected command was invisible.

    Netmiko does not treat ``% Invalid input detected`` as an error by default,
    so the rejection returns in the output and nothing reads it. The push logs
    "pushed — N command(s)", verify passes because nothing changed and
    therefore nothing broke, and stage 8.5 commits a golden that correctly
    records a device which was never configured. A successful deploy that
    configured nothing is the quietest failure available — drift will not catch
    it either, because golden matches the device exactly.

    The em dash surfaced only because it desynchronised the CLI and broke the
    echo match. A well-formed-but-rejected command had no detection at all.
    """

    REJECTIONS = [
        "% Invalid input detected at '^' marker.",
        "% Incomplete command.",
        "% Ambiguous command: \"des\"",
        "% Unrecognized host or address.",
    ]

    class _Conn:
        """Netmiko-shaped enough for the code under test."""

        def __init__(self, output, expect_pattern=True):
            self.output = output
            self.expect_pattern = expect_pattern
            self.saved = False
            self.seen_pattern = None

        def enable(self):
            pass

        def send_config_set(self, cmds, read_timeout=60, error_pattern=None,
                            cmd_verify=True):
            self.seen_pattern = error_pattern
            import re
            if error_pattern and re.search(error_pattern, self.output):
                raise ValueError(f"Pattern detected: {error_pattern}")
            return self.output

        def save_config(self):
            self.saved = True

    @pytest.mark.parametrize("rejection", REJECTIONS)
    def test_each_rejection_raises_on_the_forward_push(self, rejection):
        from modules.pipeline import _push_via_netmiko
        import modules.connection as C

        conn = self._Conn(f"s4(config-if)#des x\n{rejection}\ns4(config-if)#")
        original = C.get_persistent_connection
        C.get_persistent_connection = lambda dev, pool, lock: conn
        try:
            with pytest.raises(ValueError):
                _push_via_netmiko({"ip": "203.0.113.24"}, ["des x"], {}, None)
        finally:
            C.get_persistent_connection = original

    @pytest.mark.parametrize("rejection", REJECTIONS)
    def test_each_rejection_raises_on_the_rollback(self, rejection):
        """A rejected rollback reported as success is the worse of the two."""
        from modules.pipeline import _restore_config

        conn = self._Conn(f"s4(config)#bad\n{rejection}\n")
        with pytest.raises(ValueError):
            _restore_config(conn, "hostname s4\nbad\n")
        assert conn.saved is False, "save_config ran after a rejected rollback"

    def test_a_clean_push_still_returns_its_output(self):
        from modules.pipeline import _push_via_netmiko
        import modules.connection as C

        conn = self._Conn("s4(config-if)# description ok\ns4(config-if)#")
        original = C.get_persistent_connection
        C.get_persistent_connection = lambda dev, pool, lock: conn
        try:
            out = _push_via_netmiko({"ip": "203.0.113.24"},
                                    [" description ok"], {}, None)
        finally:
            C.get_persistent_connection = original
        assert "description ok" in out

    def test_the_pattern_is_actually_passed(self):
        """The defect was an argument that was never supplied."""
        from modules.pipeline import IOS_ERROR_PATTERN, _restore_config

        conn = self._Conn("s4(config)#hostname s4\n")
        _restore_config(conn, "hostname s4\n")
        assert conn.seen_pattern == IOS_ERROR_PATTERN

    def test_a_plain_percent_sign_is_not_a_rejection(self):
        """`% ` appears in banners and descriptions; only the four words count."""
        from modules.pipeline import _restore_config

        conn = self._Conn("s4(config)#banner motd 100% authorised use only\n")
        _restore_config(conn, "banner motd 100% authorised use only\n")
        assert conn.saved is True


class TestRollbackIsComputedNotReplayed:
    """A config-mode replay cannot undo a change — it is a merge.

    ``_restore_config`` was named "replace" and documented as "Replace running
    config with the saved pre-change text". It called ``send_config_set``,
    which re-applies lines and removes none. IOS omits ``no shutdown`` from an
    up interface's running config, so a snapshot taken before a ``shutdown``
    contains no line to re-apply: the replay would leave the interface down,
    call ``save_config()``, and log "restored successfully".

    Rollback would have demonstrated itself working on the one change it cannot
    reverse, and then persisted it. Fifth instance of a real mechanism
    positioned where it cannot do what it claims — and the only one where the
    docstring and the body disagreed in plain sight.
    """

    IFACE_PRE = ("interface GigabitEthernet0/1\n"
                 " description old text\n"
                 " negotiation auto\n")

    def test_shutdown_is_undone_with_no_shutdown(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["interface GigabitEthernet0/1", " shutdown", "exit"], self.IFACE_PRE)
        assert undo == ["interface GigabitEthernet0/1", " no shutdown", "exit"]

    def test_a_changed_description_is_restored_not_negated(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["interface GigabitEthernet0/1", " description new text", "exit"],
            self.IFACE_PRE)
        assert undo == ["interface GigabitEthernet0/1",
                        " description old text", "exit"]

    def test_an_added_description_is_negated(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["interface GigabitEthernet0/1", " description added", "exit"],
            "interface GigabitEthernet0/1\n negotiation auto\n")
        assert undo == ["interface GigabitEthernet0/1",
                        " no description added", "exit"]

    def test_a_changed_value_restores_the_old_value(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["interface GigabitEthernet0/2", " switchport access vlan 200", "exit"],
            "interface GigabitEthernet0/2\n switchport access vlan 100\n")
        assert undo == ["interface GigabitEthernet0/2",
                        " switchport access vlan 100", "exit"]

    def test_a_nested_section_gets_its_full_chain_and_exits(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["router bgp 65001", " address-family ipv4",
             "  neighbor 10.0.0.1 activate", "exit", "exit"],
            "router bgp 65001\n address-family ipv4\n")
        assert undo == ["router bgp 65001", " address-family ipv4",
                        "  no neighbor 10.0.0.1 activate", "exit", "exit"]

    def test_end_is_never_emitted(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["interface GigabitEthernet0/1", " shutdown", "exit"],
            self.IFACE_PRE + "end\n")
        assert "end" not in [c.strip() for c in undo]

    def test_a_line_already_present_needs_no_undo(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["interface GigabitEthernet0/1", " negotiation auto", "exit"],
            self.IFACE_PRE)
        assert undo == []

    def test_the_rollback_program_is_sendable(self):
        from modules.nsot.deploy import UnsendableCommand, rollback_commands
        with pytest.raises(UnsendableCommand):
            rollback_commands(["interface GigabitEthernet0/1",
                               " description new", "exit"],
                              "interface GigabitEthernet0/1\n description — old\n")


class TestRollbackNegationsAreBounded:
    """The one place this tool generates a ``no``, and it is checkable."""

    def test_the_real_inverse_passes(self):
        from modules.nsot.deploy import (assert_rollback_provenance,
                                         rollback_commands)
        pushed = ["interface GigabitEthernet0/1", " shutdown", "exit"]
        undo = rollback_commands(pushed, "interface GigabitEthernet0/1\n")
        assert_rollback_provenance(undo, pushed)

    def test_a_negation_undoing_nothing_is_refused(self):
        from modules.nsot.deploy import (RollbackNotInverse,
                                         assert_rollback_provenance)
        pushed = ["interface GigabitEthernet0/1", " shutdown", "exit"]
        with pytest.raises(RollbackNotInverse):
            assert_rollback_provenance(
                pushed[:1] + [" no ip routing", "exit"], pushed)

    def test_restoring_an_old_value_is_not_a_negation(self):
        from modules.nsot.deploy import assert_rollback_provenance
        pushed = ["interface GigabitEthernet0/1", " description new", "exit"]
        assert_rollback_provenance(
            ["interface GigabitEthernet0/1", " description old", "exit"], pushed)
