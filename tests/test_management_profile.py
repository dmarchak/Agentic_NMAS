"""Phase 2's P1 (the operator, 2026-10-07): management protocols leave from the management
interface, through INTENT, by a section of the network's profile.

M1 measured TFTP leaving r2 from its Gi2 address and s1 from a data-interface address, while
Mercury knows each by its loopback. The profile's `management` section carries
`ip tftp source-interface` and `ip ssh source-interface` (later `ip scp server enable`, C562),
derived from the interface syslog and SNMP traps already leave from (`syslog_source_interface`),
so the network declares it once, and only where it sends syslog. Previewed and deployed like
any change: Propose commits the section, Monitoring > Apply and Plan a deploy send it.

The configs are the real fleet captures (tests/fixtures/configs/fleet), each with the two lines
added where a case needs them (the minimal edit).
"""

import os

import pytest

from modules.nsot import profile, profile_propose, roundtrip, verify_scope
from modules.nsot.parsers import get_parser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
DEVICES = [("r1.cfg", "cisco_iosxe"), ("s1.cfg", "cisco_ios")]
LINES = "ip ssh source-interface Loopback0\nip tftp source-interface Loopback0\n"


def _capture(name):
    return open(os.path.join(FLEET, name), encoding="utf-8").read()


def _planted(name):
    return _capture(name).replace("\nend", "\n" + LINES + "end", 1)


def _settings(**kw):
    values = {"syslog_host": "192.0.2.10", "syslog_source_interface": "Loopback0"}
    values.update(kw)
    return lambda key, default="": values.get(key, default)


class TestTheLinesRoundTrip:
    @pytest.mark.parametrize("name, dialect", DEVICES)
    def test_a_capture_holding_them_renders_them_back(self, name, dialect):
        report = roundtrip.validate_device(_planted(name), dialect)
        assert not report.get("error"), report.get("error")
        assert report["details"]["missing"] == [] and report["details"]["extra"] == []
        assert report["host_vars"]["source_interfaces"] == {"ssh": "Loopback0",
                                                            "tftp": "Loopback0"}

    @pytest.mark.parametrize("name, dialect", DEVICES)
    def test_a_capture_without_them_renders_neither(self, name, dialect):
        report = roundtrip.validate_device(_capture(name), dialect)
        assert "ip ssh source-interface" not in report["rendered"]
        assert "ip tftp source-interface" not in report["rendered"]
        assert report["host_vars"]["source_interfaces"] == {}


class TestTheSection:
    def test_derived_from_the_syslog_interface(self):
        got = profile_propose.connector_value("management", _settings(
            syslog_source_interface="Loopback7"))
        assert got["value"] == {"source_interfaces": {"tftp": "Loopback7", "ssh": "Loopback7"}}
        assert "syslog_source_interface (Loopback7)" in got["basis"]

    def test_not_derived_where_the_network_sends_no_syslog(self):
        """The interface setting has a default; a network that never configured syslog never
        chose it, so nothing is proposed rather than a Loopback0 a device may not have."""
        got = profile_propose.connector_value("management", _settings(syslog_host=""))
        assert "value" not in got and got["why"].startswith("syslog_host is not configured")

    def test_a_committed_section_is_a_profile(self):
        doc = {"version": 1, "sections": {"management": {
            "source": "setting",
            "data": {"source_interfaces": {"tftp": "Loopback0", "ssh": "Loopback0"}}}}}
        assert profile.problems(doc) == []

    @pytest.mark.parametrize("name, dialect", DEVICES)
    def test_every_device_inherits_it_beside_its_own_ssh_lines(self, name, dialect):
        """The pitfall the survey found: carried in the opaque `ssh` list, a device's own list
        (every device has `ip ssh` lines) replaced the profile's whole list, and the line was
        lost. As a scalar it merges, and the device keeps its own `ip ssh` lines."""
        intent = get_parser(dialect).parse(_capture(name))
        assert intent["ssh"], "the capture has its own ip ssh lines"
        doc = {"version": 1, "sections": {"management": {"source": "setting", "data": {
            "source_interfaces": {"tftp": "Loopback0", "ssh": "Loopback0"}}}}}
        eff = profile.effective(intent, doc, dialect, "")
        assert eff["source_interfaces"] == {"tftp": "Loopback0", "ssh": "Loopback0"}
        assert eff["ssh"] == intent["ssh"]
        rendered = roundtrip.render(eff, intent.get("platform", dialect))
        assert "ip ssh source-interface Loopback0" in rendered
        assert "ip tftp source-interface Loopback0" in rendered

    def test_a_device_with_its_own_interface_keeps_it(self):
        intent = get_parser("cisco_ios").parse(_planted("s1.cfg").replace(
            "ip tftp source-interface Loopback0", "ip tftp source-interface Vlan99"))
        doc = {"version": 1, "sections": {"management": {"source": "setting", "data": {
            "source_interfaces": {"tftp": "Loopback0", "ssh": "Loopback0"}}}}}
        eff = profile.effective(intent, doc, "cisco_ios", "")
        assert eff["source_interfaces"] == {"tftp": "Vlan99", "ssh": "Loopback0"}
        assert [o["path"] for o in profile.overrides(intent, doc, "cisco_ios", "")] == [
            "source_interfaces.tftp"]


class TestVerify:
    def test_a_program_of_only_these_lines_verifies_quickly(self):
        """What the device sends FROM, never what it routes: verify reads the lines back."""
        got = verify_scope.classify(LINES.splitlines())
        assert got["scope"] == verify_scope.QUICK, got
