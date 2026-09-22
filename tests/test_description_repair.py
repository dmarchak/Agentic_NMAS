"""Correcting descriptions that were expanded in committed intent.

The parser fix stops new damage. It does not undo what is already committed:
`host_vars` hold `GigabitEthernet3` where the device says `Gi3`, and the
render will keep disagreeing with the device until that is corrected.

The repair is deliberately narrow, and the narrowness is the point. A
description that genuinely differs from the device is **drift** -- a pending
change waiting to be deployed -- and a repair tool that rewrote it would
silently discard somebody's work while claiming to fix formatting.
"""

import pytest

from scripts.nsot_fix_description_ifnames import (SKIP_BEYOND,
                                                  SKIP_NO_DEVICE_TEXT,
                                                  SKIP_NO_INTERFACE,
                                                  classify,
                                                  golden_descriptions,
                                                  golden_interfaces)

CONFIG = """hostname s1
!
interface GigabitEthernet0/2
 description P2P to r1 Gi3 - RIPng
 no switchport
!
interface GigabitEthernet0/3
 description trunk to s2 Gi0/3 - VRRP rides this
!
interface Vlan10
 description hosts
!
end
"""


class TestReadingTheDevicesOwnText:
    def test_descriptions_come_back_verbatim(self):
        found = golden_descriptions(CONFIG)
        assert found["GigabitEthernet0/2"] == "P2P to r1 Gi3 - RIPng"
        assert found["Vlan10"] == "hosts"

    def test_it_does_not_read_through_the_parser(self):
        """The parser is the thing that corrupted this text; reading back
        through it would compare a value against itself."""
        import inspect

        from scripts import nsot_fix_description_ifnames as tool

        source = inspect.getsource(tool.golden_descriptions)
        assert "get_parser" not in source and "parse(" not in source

    def test_a_description_outside_an_interface_is_ignored(self):
        config = "router bgp 65001\n description not an interface\n!\n"
        assert golden_descriptions(config) == {}


class TestOnlyTheExpansionIsCorrected:
    def test_an_expanded_description_is_corrected(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2",
             "description": "P2P to r1 GigabitEthernet3 - RIPng"}]}
        found = classify(committed, CONFIG)["fix"]
        assert found == [("GigabitEthernet0/2",
                          "P2P to r1 GigabitEthernet3 - RIPng",
                          "P2P to r1 Gi3 - RIPng")]

    def test_real_drift_is_left_alone(self):
        """Somebody edited intent and has not deployed it yet. Rewriting it
        would discard the change."""
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2", "description": "NEW purpose"}]}
        assert classify(committed, CONFIG)["fix"] == []

    def test_drift_that_also_contains_an_expansion_is_left_alone(self):
        """The subtle case: both an expansion AND a real edit. Correcting it
        would half-apply a repair over somebody's pending change."""
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2",
             "description": "P2P to r1 GigabitEthernet3 - OSPF now"}]}
        assert classify(committed, CONFIG)["fix"] == []

    def test_a_matching_description_is_not_touched(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2", "description": "P2P to r1 Gi3 - RIPng"}]}
        assert classify(committed, CONFIG)["fix"] == []

    def test_an_interface_the_device_does_not_have_is_skipped(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet9/9", "description": "x GigabitEthernet3"}]}
        assert classify(committed, CONFIG)["fix"] == []

    def test_an_interface_with_no_description_is_skipped(self):
        committed = {"interfaces": [{"name": "GigabitEthernet0/2"}]}
        assert classify(committed, CONFIG)["fix"] == []

    def test_an_empty_description_is_not_confused_with_a_missing_one(self):
        """`""` is a description the operator set; `None` is absence."""
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2", "description": ""}]}
        found = classify(committed, CONFIG)
        assert found["fix"] == []
        # The device HAS a description and intent says empty. That is a real
        # difference -- intent asking for the description to be removed -- so
        # it is SKIP_BEYOND, not "the device has none".
        assert found["skip"][0][3] == SKIP_BEYOND

    def test_the_interface_is_matched_canonically(self):
        """The header was expanded legitimately, so both sides must agree on
        which interface is which."""
        committed = {"interfaces": [
            {"name": "Gi0/2", "description": "P2P to r1 GigabitEthernet3 - RIPng"}]}
        assert classify(committed, CONFIG)["fix"][0][0] == "Gi0/2"


class TestItTouchesNothingButDescriptions:
    def test_no_other_field_is_returned(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2",
             "description": "P2P to r1 GigabitEthernet3 - RIPng",
             "ipv4": "10.0.0.1 255.255.255.0", "no_switchport": True}]}
        assert len(classify(committed, CONFIG)["fix"]) == 1

    def test_the_writer_only_assigns_description(self):
        import inspect

        from scripts import nsot_fix_description_ifnames as tool

        body = inspect.getsource(tool.main)
        assignments = [l for l in body.splitlines()
                       if "entry[" in l and "=" in l and "==" not in l]
        assert assignments, "no assignment found; the test is checking nothing"
        for line in assignments:
            assert '"description"' in line, line


class TestOnTheRealFleetFixtures:
    """The fixtures are the sanitized real devices, so this is the shape the
    live repair will meet."""

    @pytest.mark.parametrize("host", ["s1", "r1"])
    def test_an_expanded_committed_intent_is_detected(self, host):
        import io
        import os

        from modules.nsot import ifnames
        from modules.nsot.parsers import get_parser

        path = os.path.join("tests", "fixtures", "configs", "fleet",
                            f"{host}.cfg")
        config = io.open(path, encoding="utf-8").read()
        platform = "cisco_ios" if host.startswith("s") else "cisco_iosxe"
        parsed = get_parser(platform).parse(config)

        # Reconstruct what the OLD parser committed: descriptions expanded.
        damaged = {"interfaces": []}
        for entry in parsed.get("interfaces") or []:
            text = entry.get("description")
            if text is None:
                continue
            damaged["interfaces"].append({
                "name": entry["name"],
                "description": ifnames._LINE_RE.sub(
                    lambda m: ifnames.canonical(f"{m.group(1)}{m.group(2)}"),
                    text)})

        found = classify(damaged, config)["fix"]
        assert found, f"{host} has no expanded description to repair"
        for _name, have, want in found:
            assert have != want
            assert want in config, "the correction is not the device's own text"


class TestSkipsAreFindings:
    """A skip is not a quiet no-op.

    The dangerous case is a description carrying BOTH expansion damage and a
    real edit: correcting it would half-apply a repair over somebody's pending
    change, and skipping it silently makes "nothing was skipped" and
    "something was skipped" the same output.
    """

    def test_real_drift_is_reported_not_merely_omitted(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2", "description": "NEW purpose"}]}
        found = classify(committed, CONFIG)
        assert found["fix"] == []
        assert found["skip"] == [("GigabitEthernet0/2", "NEW purpose",
                                  "P2P to r1 Gi3 - RIPng", SKIP_BEYOND)]

    def test_the_mixed_case_is_reported(self):
        """Expansion damage AND an edit on the same line."""
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2",
             "description": "P2P to r1 GigabitEthernet3 - OSPF now"}]}
        found = classify(committed, CONFIG)
        assert found["fix"] == []
        assert found["skip"][0][3] == SKIP_BEYOND

    def test_an_interface_absent_from_the_device_is_reported(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet9/9", "description": "ghost"}]}
        assert classify(committed, CONFIG)["skip"][0][3] == SKIP_NO_INTERFACE

    def test_already_correct_entries_are_counted(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/2", "description": "P2P to r1 Gi3 - RIPng"},
            {"name": "Vlan10", "description": "hosts"}]}
        found = classify(committed, CONFIG)
        assert found["correct"] == 2
        assert found["fix"] == [] and found["skip"] == []


class TestAnUndescribedInterfaceIsNotASkip:
    """The false skip the loud report exposed on its first run.

    The parser writes `description: ''` for an interface with no description
    line. The device map held only interfaces that HAVE a description, so
    "this interface has no description" was indistinguishable from "this
    interface is not on the device" -- ten false loud skips across the fleet
    fixtures, every one of them wrong.

    A report nobody can trust gets ignored, which would have cost more than
    the silence it replaced.
    """

    CONFIG_WITH_BARE = CONFIG + """interface GigabitEthernet0/9
 no switchport
!
"""

    def test_it_counts_as_already_correct(self):
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/9", "description": ""}]}
        found = classify(committed, self.CONFIG_WITH_BARE)
        assert found["correct"] == 1
        assert found["skip"] == []

    def test_a_wanted_description_the_device_lacks_is_still_a_skip(self):
        """Committed intent asking for a description the device has not got
        is drift to deploy, and must not be silently absorbed."""
        committed = {"interfaces": [
            {"name": "GigabitEthernet0/9", "description": "please add me"}]}
        found = classify(committed, self.CONFIG_WITH_BARE)
        assert found["skip"][0][3] == SKIP_NO_DEVICE_TEXT

    def test_golden_interfaces_sees_undescribed_ones(self):
        names = golden_interfaces(self.CONFIG_WITH_BARE)
        assert "GigabitEthernet0/9" in names
        assert "GigabitEthernet0/9" not in golden_descriptions(
            self.CONFIG_WITH_BARE)

    def test_the_whole_fleet_reports_no_skips(self):
        """The property your review asked for, on the real shapes: 22 fixes,
        nothing skipped."""
        import io as _io
        import os

        from modules.nsot import ifnames
        from modules.nsot.parsers import get_parser

        fixes = skips = 0
        for host in ("r1", "r2", "r3", "r4", "r5", "s1", "s2", "s3", "s4"):
            path = os.path.join("tests", "fixtures", "configs", "fleet",
                                f"{host}.cfg")
            config = _io.open(path, encoding="utf-8").read()
            platform = "cisco_ios" if host.startswith("s") else "cisco_iosxe"
            parsed = get_parser(platform).parse(config)
            damaged = {"interfaces": []}
            for entry in parsed.get("interfaces") or []:
                text = entry.get("description")
                if text is None:
                    continue
                damaged["interfaces"].append({
                    "name": entry["name"],
                    "description": ifnames._LINE_RE.sub(
                        lambda m: ifnames.canonical(
                            f"{m.group(1)}{m.group(2)}"), text)})
            found = classify(damaged, config)
            fixes += len(found["fix"])
            skips += len(found["skip"])
        assert (fixes, skips) == (22, 0), (fixes, skips)


class TestTheWriteIsOneCommit:
    """Nine commits would make the history describe nine decisions nobody
    took separately."""

    def _main_source(self):
        import inspect

        from scripts import nsot_fix_description_ifnames as tool

        return inspect.getsource(tool.main)

    def _main_tree(self):
        """Parsed, so the COMMENT explaining that it commits once does not
        count as a second call -- which is exactly how this test first
        failed."""
        import ast
        import inspect
        import textwrap

        from scripts import nsot_fix_description_ifnames as tool

        return ast.parse(textwrap.dedent(inspect.getsource(tool.main)))

    def _calls(self, name):
        import ast

        return [node for node in ast.walk(self._main_tree())
                if isinstance(node, ast.Call)
                and getattr(node.func, "attr", getattr(node.func, "id", ""))
                == name]

    def test_save_host_vars_is_called_once(self):
        assert len(self._calls("save_host_vars")) == 1

    def test_it_is_outside_the_per_device_loop(self):
        """Inside the loop it would be one commit per device."""
        import ast

        commit = self._calls("save_host_vars")[0]
        for node in ast.walk(self._main_tree()):
            if not isinstance(node, ast.For):
                continue
            inside = [c for child in node.body for c in ast.walk(child)
                      if c is commit]
            assert not inside, "save_host_vars is inside a loop"

    def test_the_message_names_the_repair(self):
        assert ("host_vars: restore description text (ifname expansion, 1.4)"
                in self._main_source())

    def test_the_devices_are_passed_for_the_trailer(self):
        assert "[h for h, _ in touched]" in self._main_source()

    def test_it_writes_through_the_guarded_writer(self):
        """`write_committed()` carries the secret guards; a direct file write
        would skip them."""
        source = self._main_source()
        assert "hostvars.write_committed(" in source
        assert "open(" not in source


class TestSkippingChangesTheExitCode:
    """A warning that scrolls past has not warned anybody."""

    def test_the_script_exits_non_zero_when_anything_was_skipped(self):
        import inspect

        from scripts import nsot_fix_description_ifnames as tool

        source = inspect.getsource(tool.main)
        assert source.count("return 2 if skipped else 0") >= 2, (
            "every exit path must carry the skip verdict")
