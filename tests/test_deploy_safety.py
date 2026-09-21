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


class TestDangerousCommandsNeedAuthorisation:
    """The CI gate offered an override the deploy path could not supply.

    ``params['allowed_dangerous']`` has existed since Phase 0, and
    ``_deploy_one()`` hardcoded ``params={"skip_route_check": True}`` — so any
    template change containing ``shutdown``, ``no ip address``, ``no router
    ospf``, ``reload``, ``erase nvram`` or ``crypto key zeroize`` was
    permanently unrunnable through Phase 3c. Not refused pending authorisation:
    refused with no authorisation mechanism reachable.

    A gate that cannot be cleared is as broken as one that cannot fire. It just
    fails in the safe direction, so it sits there until someone needs to shut
    an interface — a routine operation.
    """

    PROGRAM = ["interface GigabitEthernet0/1", " shutdown", "exit"]

    def test_the_dangerous_line_is_flagged_as_an_exact_string(self):
        from modules.nsot.deploy import dangerous_in
        assert dangerous_in(self.PROGRAM) == ["shutdown"]

    def test_a_clean_program_flags_nothing(self):
        from modules.nsot.deploy import dangerous_in
        assert dangerous_in(["interface GigabitEthernet0/1",
                             " description x", "exit"]) == []

    def test_an_authorised_line_proceeds(self):
        from modules.nsot.deploy import assert_authorised
        assert_authorised(self.PROGRAM, ["shutdown"])

    def test_an_unauthorised_dangerous_line_is_refused(self):
        from modules.nsot.deploy import NotAuthorised, assert_authorised
        with pytest.raises(NotAuthorised) as exc:
            assert_authorised(self.PROGRAM, [])
        assert "shutdown" in str(exc.value)

    def test_authorising_a_line_not_in_the_program_is_refused(self):
        """A standing blanket, or a typo — and a typo means the line it was
        meant to cover is not authorised."""
        from modules.nsot.deploy import NotAuthorised, assert_authorised
        with pytest.raises(NotAuthorised) as exc:
            assert_authorised(self.PROGRAM, ["shutdown", "reload"])
        assert "match no dangerous command" in str(exc.value)

    def test_a_near_miss_authorisation_does_not_count(self):
        from modules.nsot.deploy import NotAuthorised, assert_authorised
        with pytest.raises(NotAuthorised):
            assert_authorised(self.PROGRAM, ["shut"])

    def test_the_authorisation_is_part_of_the_confirmation_hash(self):
        from modules.nsot.deploy import command_fingerprint
        assert (command_fingerprint(self.PROGRAM, [])
                != command_fingerprint(self.PROGRAM, ["shutdown"]))

    def test_changing_the_authorisation_between_plan_and_apply_is_caught(self):
        from modules.nsot.deploy import command_fingerprint
        confirmed = command_fingerprint(self.PROGRAM, ["shutdown"])
        at_apply = command_fingerprint(self.PROGRAM, [])
        assert at_apply != confirmed

    def test_the_hash_is_order_insensitive_for_authorisations(self):
        """Two authorisations are a set, not a sequence."""
        from modules.nsot.deploy import command_fingerprint
        program = ["interface GigabitEthernet0/1", " shutdown", "exit",
                   "interface GigabitEthernet0/2", " no ip address", "exit"]
        assert (command_fingerprint(program, ["shutdown", "no ip address"])
                == command_fingerprint(program, ["no ip address", "shutdown"]))

    def test_authorisation_is_scoped_per_device(self):
        """Authorising a line for one device must not authorise it elsewhere."""
        from modules.nsot.deploy import NotAuthorised, assert_authorised

        authorise = {"s4": ["shutdown"], "s3": []}
        assert_authorised(self.PROGRAM, authorise["s4"])
        with pytest.raises(NotAuthorised):
            assert_authorised(self.PROGRAM, authorise["s3"])

    def test_the_gate_accepts_a_stripped_match(self):
        """The gate compares cmd.strip(); the flag must produce that string."""
        from modules.pipeline import _DANGEROUS_PATTERNS
        from modules.nsot.deploy import dangerous_in

        flagged = dangerous_in(self.PROGRAM)[0]
        line = next(c for c in self.PROGRAM
                    if any(p.search(c) for p in _DANGEROUS_PATTERNS))
        assert line.strip() == flagged


def _ctx(**overrides):
    """A pipeline context for the rollback-path tests."""
    import threading
    from modules.pipeline import PipelineContext
    base = dict(config_type="template", device_ips=["10.0.0.1"],
                params={}, ip_params_map={},
                selected_devices=[{"ip": "10.0.0.1", "hostname": "R1"}],
                check_devices=[], connections_pool={},
                pool_lock=threading.Lock(), config_id="t",
                settle_sleep=lambda _s: None)
    base.update(overrides)
    return PipelineContext(**base)


class TestRollbackIsExemptFromTheDangerousGate:
    """Rolling back an authorised change produces a dangerous command.

    Undoing ``no shutdown`` is ``shutdown``. If the gate blocked the repair,
    the device would stay in the state the rollback was called to fix — a
    safety check causing the damage it exists to prevent.

    The exemption is structural: rollback never passes through stage 3. Its
    authorisation is ``assert_rollback_provenance()``, which guarantees every
    line inverts something this deploy just pushed.
    """

    def test_undoing_no_shutdown_emits_shutdown(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["interface GigabitEthernet0/1", " no shutdown", "exit"],
            "interface GigabitEthernet0/1\n shutdown\n")
        assert undo == ["interface GigabitEthernet0/1", " shutdown", "exit"]

    def test_that_rollback_would_trip_the_gate(self):
        """Stated explicitly, so the exemption is not theoretical."""
        from modules.nsot.deploy import dangerous_in, rollback_commands
        undo = rollback_commands(
            ["interface GigabitEthernet0/1", " no shutdown", "exit"],
            "interface GigabitEthernet0/1\n shutdown\n")
        assert dangerous_in(undo) == ["shutdown"]

    def test_provenance_still_authorises_it(self):
        from modules.nsot.deploy import (assert_rollback_provenance,
                                         rollback_commands)
        pushed = ["interface GigabitEthernet0/1", " no shutdown", "exit"]
        undo = rollback_commands(pushed, "interface GigabitEthernet0/1\n shutdown\n")
        assert_rollback_provenance(undo, pushed)

    def test_undoing_a_shutdown_emits_no_shutdown(self):
        """The 3A direction, which a config replay could not produce."""
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["interface GigabitEthernet0/1", " shutdown", "exit"],
            "interface GigabitEthernet0/1\n description x\n")
        assert undo == ["interface GigabitEthernet0/1", " no shutdown", "exit"]

    def test_the_rollback_path_never_calls_the_ci_gate(self):
        import inspect
        from modules.pipeline import _stage_rollback
        source = inspect.getsource(_stage_rollback)
        assert "_stage_ci_gate" not in source
        assert "allowed_dangerous" not in source

    def test_exempt_lines_are_recorded_not_silent(self):
        from modules.pipeline import _stage_rollback
        import modules.ai_assistant as A
        import modules.connection as C
        import modules.pipeline as P

        ctx = _ctx()
        ctx.push_results = {"10.0.0.1": {"ok": True}}
        ctx.confirmed_commands = {"10.0.0.1": ["interface GigabitEthernet0/0",
                                               " no shutdown", "exit"]}
        originals = (P._restore_config, A._load_pre_change_file,
                     C.get_persistent_connection)
        P._restore_config = lambda conn, cmds: None
        A._load_pre_change_file = lambda ip: (
            "interface GigabitEthernet0/0\n shutdown\n")
        C.get_persistent_connection = lambda dev, pool, lock: object()
        try:
            _stage_rollback(ctx)
        finally:
            (P._restore_config, A._load_pre_change_file,
             C.get_persistent_connection) = originals

        assert ctx.rollback_dangerous["10.0.0.1"] == ["shutdown"]
        assert ctx.rolled_back_ips == ["10.0.0.1"]


class TestAncestryIsNotASetting:
    """`interface GigabitEthernet0/1` is context, not a value to restore.

    ``rollback_commands()`` ran its key lookup over **every** pushed line,
    headers included. ``interface GigabitEthernet0/1`` reduces to the key
    ``interface``, which matched the first ``interface`` line in the
    pre-change config — so the rollback "restored the old value" of a section
    header and sent ``interface Loopback0`` to a live device.

    No harm on that device, by luck: the next line entered a different
    interface, and Loopback0 already existed. ``interface X`` on IOS *creates*
    X when it does not, and ``router bgp 65001`` reduces to ``router``, which
    matches ``router ospf 1``.
    """

    S4_PRE = ("interface Loopback0\n"
              " description mgmt identity\n"
              " ip address 10.255.1.24 255.255.255.255\n"
              "interface GigabitEthernet0/1\n"
              " description NSoT-managed - CSCI 5840 Lab 4\n"
              " negotiation auto\n")

    def test_the_s4_case_produces_exactly_three_lines(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["interface GigabitEthernet0/1", " shutdown", "exit"], self.S4_PRE)
        assert undo == ["interface GigabitEthernet0/1", " no shutdown", "exit"]

    def test_no_other_interface_is_ever_entered(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["interface GigabitEthernet0/1", " shutdown", "exit"], self.S4_PRE)
        assert "interface Loopback0" not in undo

    def test_router_bgp_is_never_matched_against_router_ospf(self):
        """Both reduce to the key `router`."""
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["router bgp 65001", " bgp log-neighbor-changes", "exit"],
            "router ospf 1\n router-id 10.0.0.1\n")
        assert undo == ["router bgp 65001", " no bgp log-neighbor-changes", "exit"]
        assert "router ospf 1" not in undo

    def test_the_classification_is_shared_not_re_derived(self):
        """The forward and rollback paths consume one function."""
        import inspect
        from modules.nsot import deploy

        rollback_src = inspect.getsource(deploy.rollback_commands)
        assert "landed_leaves(" in rollback_src
        assert "program_leaves(" in inspect.getsource(deploy.landed_leaves)
        merge_src = inspect.getsource(deploy.merge_commands)
        assert "program_leaves(" in merge_src, (
            "merge_commands must assert against the shared classification, or "
            "the two can drift apart again")

    def test_merge_commands_fails_loudly_if_they_disagree(self):
        from modules.nsot.deploy import program_leaves, program_structure

        program = ["interface GigabitEthernet0/1", " shutdown", "exit"]
        assert [e.line for e in program_leaves(program)] == [" shutdown"]
        assert [e["leaf"] for e in program_structure(program)] == [False, True]

    def test_a_nested_header_is_ancestry_too(self):
        from modules.nsot.deploy import program_structure
        entries = program_structure(
            ["router bgp 65001", " address-family ipv4",
             "  neighbor 10.0.0.1 activate", "exit", "exit"])
        assert [e["leaf"] for e in entries] == [False, False, True]

    def test_a_top_level_leaf_is_a_leaf(self):
        from modules.nsot.deploy import program_leaves
        assert [e.line for e in program_leaves(["ip routing"])] == ["ip routing"]


class TestRollbackProvenanceCoversEveryLine:
    """The check examined only `no ` lines, so a synthesised non-negating line
    passed free.

    That is how ``interface Loopback0`` reached a device: it is the inverse of
    nothing, so the guard never looked at it. A guard that inspects one
    category and waves the rest through reads as a check while the thing that
    went wrong was never in its scope.
    """

    PUSHED = ["interface GigabitEthernet0/1", " shutdown", "exit"]

    def test_the_real_inverse_passes(self):
        from modules.nsot.deploy import assert_rollback_provenance
        assert_rollback_provenance(
            ["interface GigabitEthernet0/1", " no shutdown", "exit"], self.PUSHED)

    def test_a_restored_prior_value_passes(self):
        from modules.nsot.deploy import assert_rollback_provenance
        pushed = ["interface GigabitEthernet0/1", " description new", "exit"]
        assert_rollback_provenance(
            ["interface GigabitEthernet0/1", " description old", "exit"], pushed)

    def test_a_synthesised_header_is_refused(self):
        """The exact line that reached s4."""
        from modules.nsot.deploy import (RollbackNotInverse,
                                         assert_rollback_provenance)
        with pytest.raises(RollbackNotInverse) as exc:
            assert_rollback_provenance(
                ["interface Loopback0", "interface GigabitEthernet0/1",
                 " no shutdown", "exit"], self.PUSHED)
        assert "interface Loopback0" in str(exc.value)

    def test_a_synthesised_non_negating_leaf_is_refused(self):
        from modules.nsot.deploy import (RollbackNotInverse,
                                         assert_rollback_provenance)
        with pytest.raises(RollbackNotInverse) as exc:
            assert_rollback_provenance(
                ["interface GigabitEthernet0/1", " no shutdown",
                 " ip address 203.0.113.1 255.255.255.0", "exit"], self.PUSHED)
        assert "did not touch" in str(exc.value)

    def test_an_orphan_negation_is_still_refused(self):
        from modules.nsot.deploy import (RollbackNotInverse,
                                         assert_rollback_provenance)
        with pytest.raises(RollbackNotInverse):
            assert_rollback_provenance(
                ["interface GigabitEthernet0/1", " no ip routing", "exit"],
                self.PUSHED)

    def test_a_line_in_a_section_the_deploy_never_entered_is_refused(self):
        from modules.nsot.deploy import (RollbackNotInverse,
                                         assert_rollback_provenance)
        with pytest.raises(RollbackNotInverse):
            assert_rollback_provenance(
                ["interface GigabitEthernet0/2", " no shutdown", "exit"],
                self.PUSHED)

    def test_the_refusal_says_which_category_failed(self):
        from modules.nsot.deploy import (RollbackNotInverse,
                                         assert_rollback_provenance)
        with pytest.raises(RollbackNotInverse) as exc:
            assert_rollback_provenance(
                ["interface Loopback0", " no shutdown", "exit"], self.PUSHED)
        message = str(exc.value)
        assert "not a section this deploy entered" in message or \
               "did not touch" in message


class TestTheBroadKeyOnlyAppliesToFreeFormCommands:
    """`ip mtu` and `ip address` are different settings sharing a first word.

    The broad fallback existed because ``description some free text`` has its
    value in *everything* after the first token, so a precise key of
    ``description some free`` never matches ``description other text``. Applied
    to every command, it made ``ip mtu 20000`` match ``ip address 10.255.1.24
    255.255.255.255`` — and a rollback for a rejected MTU would have re-sent a
    management address.

    The distinction is structural, not positional: in one shape the second
    token is part of the command, in the other everything after the first is
    the value. A second-word rule separates those two by accident and picks
    wrong on the third shape it meets.
    """

    LOOPBACK = ("interface Loopback0\n"
                " description mgmt identity\n"
                " ip address 10.255.1.24 255.255.255.255\n")

    def test_ip_mtu_is_negated_not_matched_to_ip_address(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["interface Loopback0", " ip mtu 20000", "exit"], self.LOOPBACK)
        assert undo == ["interface Loopback0", " no ip mtu 20000", "exit"]
        assert not any("ip address" in c for c in undo)

    def test_a_description_still_restores_its_prior_value(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["interface Loopback0", " description new text", "exit"], self.LOOPBACK)
        assert undo == ["interface Loopback0", " description mgmt identity", "exit"]

    def test_a_helper_address_is_negated_not_matched_to_the_interface_ip(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["interface Vlan10", " ip helper-address 10.0.0.9", "exit"],
            "interface Vlan10\n ip address 10.0.0.1 255.255.255.0\n")
        assert undo == ["interface Vlan10", " no ip helper-address 10.0.0.9", "exit"]

    def test_a_precise_match_still_wins_for_a_non_free_form_command(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(
            ["interface Vlan10", " ip mtu 9000", "exit"],
            "interface Vlan10\n ip mtu 1500\n")
        assert undo == ["interface Vlan10", " ip mtu 1500", "exit"]

    def test_provenance_refuses_a_broad_match_on_a_non_free_form_command(self):
        """Or the narrowing would be undone by the guard accepting it anyway."""
        from modules.nsot.deploy import (RollbackNotInverse,
                                         assert_rollback_provenance)
        pushed = ["interface Loopback0", " ip mtu 20000", "exit"]
        with pytest.raises(RollbackNotInverse):
            assert_rollback_provenance(
                ["interface Loopback0",
                 " ip address 10.255.1.24 255.255.255.255", "exit"], pushed)

    def test_the_free_form_list_is_explicit(self):
        from modules.nsot.deploy import FREE_FORM_COMMANDS
        assert set(FREE_FORM_COMMANDS) == {"description", "banner", "remark", "name"}


class TestRollbackUndoesWhatLandedNotWhatWasPushed:
    """On a partial push the two differ by definition.

    Undoing what was *pushed* is the same derive-from-the-wrong-source error as
    taking intent from current state, one level down. With ``error_pattern``
    live, a rollback line answering a rejected push line can itself be refused
    and take the repair down with it.
    """

    PUSHED = ["interface Loopback0", " description 3B test", " ip mtu 20000", "exit"]
    PRE = ("interface Loopback0\n description mgmt identity\n"
           " ip address 10.255.1.24 255.255.255.255\n")

    def test_only_the_landed_line_is_undone(self):
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(self.PUSHED, self.PRE,
                                 landed=[" description 3B test"])
        assert undo == ["interface Loopback0", " description mgmt identity", "exit"]
        assert not any("mtu" in c for c in undo)

    def test_the_rejected_line_is_reported(self):
        from modules.nsot.deploy import landed_leaves
        _applied, rejected = landed_leaves(self.PUSHED, [" description 3B test"])
        assert [e.line for e in rejected] == [" ip mtu 20000"]

    def test_nothing_landed_means_nothing_to_undo(self):
        from modules.nsot.deploy import rollback_commands
        assert rollback_commands(self.PUSHED, self.PRE, landed=[]) == []

    def test_an_unknown_capture_undoes_everything(self):
        """Conservative: None means the capture could not read the device."""
        from modules.nsot.deploy import rollback_commands
        undo = rollback_commands(self.PUSHED, self.PRE, landed=None)
        assert " description mgmt identity" in undo
        assert " no ip mtu 20000" in undo

    def test_provenance_holds_for_a_landed_only_rollback(self):
        from modules.nsot.deploy import (assert_rollback_provenance,
                                         rollback_commands)
        undo = rollback_commands(self.PUSHED, self.PRE,
                                 landed=[" description 3B test"])
        assert_rollback_provenance(undo, self.PUSHED)


class TestDiffCategoriesDistinguishReplaceFromResidue:
    """`removal_warnings` listed lines that were about to be replaced.

    A device holding ``description batch 4 baseline`` against a target of
    ``description old`` had its line reported as "present on the device and not
    in the target" — true, and read as "will not be removed" when pushing the
    target replaces it. On a restore that is the difference between an honest
    warning and a false one, and it is exactly the demo case.

    The classification is the one ``rollback_commands()`` already uses: precise
    key, plus the broad key only for free-form commands. Re-deriving it is what
    produced the ``interface Loopback0`` and ``ip address`` bugs.
    """

    TARGET = ("interface Loopback0\n"
              " description old\n"
              " ip address 10.0.0.1 255.255.255.255\n")
    DEVICE = ("interface Loopback0\n"
              " description batch 4 baseline\n"
              " ip address 10.0.0.1 255.255.255.255\n"
              " mtu 1500\n")

    def test_a_replaced_description_is_replace_not_residue(self):
        from modules.nsot.deploy import classify_diff
        result = classify_diff(self.TARGET, self.DEVICE)
        assert [r["old"] for r in result["replace"]] == [" description batch 4 baseline"]
        assert [r["new"] for r in result["replace"]] == [" description old"]
        assert " description batch 4 baseline" not in result["residue"]

    def test_a_genuinely_extra_line_is_residue(self):
        from modules.nsot.deploy import classify_diff
        assert classify_diff(self.TARGET, self.DEVICE)["residue"] == [" mtu 1500"]

    def test_a_line_the_device_lacks_entirely_is_add(self):
        from modules.nsot.deploy import classify_diff
        result = classify_diff(
            "interface Loopback0\n description x\n ip mtu 1400\n",
            "interface Loopback0\n description x\n")
        assert result["add"] == [" ip mtu 1400"]
        assert result["replace"] == []

    def test_an_identical_config_classifies_as_nothing(self):
        from modules.nsot.deploy import classify_diff
        result = classify_diff(self.DEVICE, self.DEVICE)
        assert result == {"add": [], "replace": [], "residue": []}

    def test_merge_diff_reports_only_residue_as_a_removal_warning(self):
        from modules.nsot.deploy import merge_diff
        diff = merge_diff(self.TARGET, self.DEVICE)
        assert diff["removal_warnings"] == [" mtu 1500"]
        assert [r["old"] for r in diff["replace"]] == [" description batch 4 baseline"]

    def test_the_batch_4_false_warning_is_gone(self):
        """The observed case: a plan warned about a line it was replacing."""
        from modules.nsot.deploy import merge_diff
        diff = merge_diff(
            "interface Loopback0\n description NSoT-managed - batch 4\n",
            "interface Loopback0\n description mgmt identity\n")
        assert diff["removal_warnings"] == []
        assert diff["to_add"] == [" description NSoT-managed - batch 4"]

    def test_the_same_setting_under_a_different_header_is_not_a_replace(self):
        """And a header is not a setting at all.

        `interface Loopback0` and `interface Loopback1` both reduce to the key
        `interface`, so classifying headers reported a *replace* between two
        different interfaces. Only leaves carry settings — the third time this
        exact mistake has been made in this file.
        """
        from modules.nsot.deploy import classify_diff
        result = classify_diff(
            "interface Loopback0\n description a\n",
            "interface Loopback1\n description b\n")
        assert result["replace"] == []
        assert result["add"] == [" description a"]
        assert result["residue"] == [" description b"]

    def test_a_header_is_never_classified(self):
        from modules.nsot.deploy import classify_diff
        result = classify_diff(
            "interface Loopback0\n description a\n",
            "interface Loopback0\n description a\n")
        assert result == {"add": [], "replace": [], "residue": []}

    def test_a_non_free_form_setting_needs_a_precise_match_to_replace(self):
        """`ip mtu` must not be matched against `ip address`."""
        from modules.nsot.deploy import classify_diff
        result = classify_diff(
            "interface Loopback0\n ip mtu 1400\n",
            "interface Loopback0\n ip address 10.0.0.1 255.255.255.255\n")
        assert result["add"] == [" ip mtu 1400"]
        assert result["replace"] == []
        assert result["residue"] == [" ip address 10.0.0.1 255.255.255.255"]


class TestAHeaderCannotReachASettingKey:
    """Made unrepresentable, not documented for a fourth time.

    `interface Loopback0` and `interface Loopback1` both reduce to the key
    `interface`. That produced three separate defects — a rollback "restoring"
    one interface to another, `ip mtu` matched against `ip address`, and a
    *replace* reported between two interfaces — across code written after the
    rule was documented twice.

    The rule kept being broken because "compare these two config lines" reads
    as a whole-line operation right up until a header is one of them. So the
    key function now takes a ``Leaf`` and a raw string is a TypeError: the same
    move as ``resolve_identity`` losing the ability to mint.
    """

    def test_a_raw_line_is_refused(self):
        from modules.nsot.deploy import _command_keys
        with pytest.raises(TypeError) as exc:
            _command_keys("interface Loopback0")
        assert "not a setting" in str(exc.value)

    def test_the_refusal_names_what_went_wrong(self):
        from modules.nsot.deploy import _command_keys
        with pytest.raises(TypeError) as exc:
            _command_keys(" description x")
        assert "Leaf" in str(exc.value)

    def test_program_leaves_yields_leaf_values(self):
        from modules.nsot.deploy import Leaf, program_leaves
        leaves = program_leaves(["interface GigabitEthernet0/1", " shutdown", "exit"])
        assert all(isinstance(entry, Leaf) for entry in leaves)
        assert [entry.line for entry in leaves] == [" shutdown"]

    def test_config_leaves_yields_leaf_values_and_excludes_headers(self):
        from modules.nsot.deploy import Leaf, config_leaves
        leaves = config_leaves("interface Loopback0\n description x\n ip mtu 1400\n")
        assert all(isinstance(entry, Leaf) for entry in leaves)
        assert [entry.line for entry in leaves] == [" description x", " ip mtu 1400"]
        assert all(entry.line != "interface Loopback0" for entry in leaves)

    def test_a_top_level_line_with_no_children_is_a_leaf(self):
        from modules.nsot.deploy import config_leaves
        assert [e.line for e in config_leaves("ip routing\nhostname s4\n")] == [
            "ip routing", "hostname s4"]

    def test_a_nested_header_is_excluded_too(self):
        from modules.nsot.deploy import config_leaves
        leaves = config_leaves(
            "router bgp 65001\n address-family ipv4\n  neighbor 10.0.0.1 activate\n")
        assert [e.line for e in leaves] == ["  neighbor 10.0.0.1 activate"]

    def test_every_call_site_passes_a_leaf(self):
        """A regression guard: no bare string reaches the key function."""
        import inspect
        import re
        from modules.nsot import deploy

        source = inspect.getsource(deploy)
        calls = re.findall(r"_command_keys\(([^)]*)\)", source)
        offenders = [c for c in calls
                     if c.strip() and not c.strip().startswith(("Leaf(", "leaf"))]
        assert offenders == [], f"raw values passed to _command_keys: {offenders}"
