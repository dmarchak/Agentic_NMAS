"""NSOT_PLAN P.1: the syslog block is one unit of intent.

Trap level, origin-id, source-interface, hosts and the EEM heartbeat applet
are parsed together, rendered together, and committed only together.

The heartbeat lines are the devices' OWN rendering, captured from
`show running-config` on both platforms (nmas-eem-probe run 2, 2026-09-25):
vIOS-L2 and C8000v print them identically. They are not what the template
emits -- a test comparing the template with itself would pass on any shape.
"""

import copy
import os

import pytest

from modules.nsot import hostvars, roundtrip
from modules.nsot.parsers import get_parser
from modules.nsot.roundtrip import validate_device

FLEET = os.path.join(os.path.dirname(__file__), "fixtures", "configs", "fleet")

#: Captured verbatim from both probe nodes (the host line differs by lab).
CAPTURED_BLOCK = [
    "logging trap notifications",
    "logging origin-id hostname",
    "logging source-interface Loopback0",
    "logging host 10.255.1.10",
]
CAPTURED_APPLET = [
    "event manager applet NMAS-HEARTBEAT",
    " event timer watchdog time 300",
    ' action 1.0 syslog priority notifications msg "NMAS-HEARTBEAT"',
]


def _fixture(name):
    with open(os.path.join(FLEET, f"{name}.cfg"), encoding="utf-8") as fh:
        return fh.read()


def _with_production_block(config: str) -> str:
    """The fleet config as it will be after P.1's deploy: trap raised to
    notifications, and the applet placed where both platforms put it
    (after `line vty`, before `end`)."""
    lines = [l for l in config.splitlines()
             if not l.startswith(("logging trap", "logging origin-id",
                                  "logging source-interface",
                                  "logging host"))]
    end = max(i for i, l in enumerate(lines) if l.strip() == "end")
    return "\n".join(lines[:end] + CAPTURED_BLOCK + CAPTURED_APPLET
                     + lines[end:]) + "\n"


@pytest.mark.parametrize("name,platform", [("r1", "cisco_iosxe"),
                                           ("s1", "cisco_ios")])
class TestTheCapturedBlockRoundTrips:
    def test_parse_render_compare_is_clean(self, name, platform):
        report = validate_device(_with_production_block(_fixture(name)),
                                 platform)
        assert not report.get("error"), report.get("error")
        assert report["modeled_coverage"] == 100.0, report.get("missing")
        assert report["round_trip_fidelity"] == 100.0
        assert report["host_vars"]["unmodeled"] == []

    def test_the_block_is_parsed_whole(self, name, platform):
        hv = get_parser(platform).parse(_with_production_block(_fixture(name)))
        assert hv["logging"]["syslog"] == {
            "trap": "notifications", "origin_id": "hostname",
            "source_interface": "Loopback0", "hosts": ["10.255.1.10"],
            "heartbeat": 300}
        assert hostvars.syslog_block_problems(hv) == []

    def test_the_render_carries_the_devices_own_lines(self, name, platform):
        hv = get_parser(platform).parse(_with_production_block(_fixture(name)))
        rendered = roundtrip.render(hv, platform, secret_lookup=lambda _r: "x")
        for line in CAPTURED_BLOCK + CAPTURED_APPLET:
            assert line in rendered.splitlines(), line


class TestOnlyTheHeartbeatShapeIsClaimed:
    def _applet(self, *body, name="NMAS-HEARTBEAT"):
        cfg = _fixture("r1")
        end = cfg.rindex("\nend")
        return (cfg[:end] + f"\nevent manager applet {name}\n"
                + "\n".join(body) + cfg[end:])

    def test_another_applet_is_unmodelled_verbatim(self):
        hv = get_parser("cisco_iosxe").parse(self._applet(
            " event timer watchdog time 300", " action 1.0 cli command enable",
            name="SOMETHING-ELSE"))
        assert any(u["line"] == "event manager applet SOMETHING-ELSE"
                   for u in hv["unmodeled"])

    def test_a_near_miss_body_is_not_claimed(self):
        """Claiming it would render the canonical body, which the device does
        not hold -- a wrong thing looking like a working thing."""
        hv = get_parser("cisco_iosxe").parse(self._applet(
            " event timer watchdog time 300",
            ' action 1.0 syslog priority critical msg "NMAS-HEARTBEAT"'))
        assert any(u["line"] == "event manager applet NMAS-HEARTBEAT"
                   for u in hv["unmodeled"])
        assert (hv["logging"]["syslog"] or {}).get("heartbeat", 0) == 0

    def test_the_fleet_has_no_heartbeat_today(self):
        """Floor: the pre-P.1 fleet parses with the block PARTIAL, which is
        what makes the commit refusal below reachable at all."""
        seen = 0
        for name in sorted(os.listdir(FLEET)):
            platform = "cisco_iosxe" if name.startswith("r") else "cisco_ios"
            with open(os.path.join(FLEET, name), encoding="utf-8") as fh:
                sl = get_parser(platform).parse(fh.read())["logging"]["syslog"]
            assert sl and sl["heartbeat"] == 0 and sl["hosts"], name
            seen += 1
        assert seen == 9


class TestAPartialBlockIsRefused:
    def _complete(self):
        return {"hostname": "x", "logging": {"settings": [], "hosts": [],
                "syslog": {"trap": "notifications", "origin_id": "hostname",
                           "source_interface": "Loopback0",
                           "hosts": ["10.255.1.10"], "heartbeat": 300}}}

    def test_a_complete_block_passes(self):
        assert hostvars.syslog_block_problems(self._complete()) == []

    def test_no_block_at_all_passes(self):
        """Absent is not partial: intent that predates P.1 is untouched."""
        assert hostvars.syslog_block_problems({"hostname": "x"}) == []
        assert hostvars.syslog_block_problems(
            {"hostname": "x", "logging": {"syslog": None}}) == []

    @pytest.mark.parametrize("field,empty", [
        ("trap", ""), ("origin_id", ""), ("source_interface", ""),
        ("hosts", []), ("heartbeat", 0)])
    def test_each_missing_part_is_named(self, field, empty):
        hv = self._complete()
        hv["logging"]["syslog"][field] = empty
        problems = hostvars.syslog_block_problems(hv)
        assert len(problems) == 1 and field in problems[0], problems

    def test_the_same_fact_in_two_places_is_refused(self):
        """A trap level in both `settings` and the block is two owners of one
        fact: whichever renders last wins, and the reader cannot tell which."""
        hv = self._complete()
        hv["logging"]["settings"] = ["trap critical"]
        hv["logging"]["hosts"] = ["10.0.0.1"]
        problems = hostvars.syslog_block_problems(hv)
        assert any("trap" in p and "settings" in p for p in problems)
        assert any("hosts" in p for p in problems)

    def test_the_AUTHORING_path_refuses_a_partial_block(self, tmp_path):
        hv = self._complete()
        hv["logging"]["syslog"]["heartbeat"] = 0
        os.makedirs(tmp_path / "host_vars")
        with pytest.raises(hostvars.PartialSyslogBlock, match="heartbeat"):
            hostvars.write_committed_text(str(tmp_path), "x",
                                          hostvars.to_yaml(hv))
        assert not os.listdir(tmp_path / "host_vars")

    def test_the_EXTRACTION_path_records_a_partial_block_as_it_is(
            self, tmp_path):
        """Whole-or-absent is a rule about AUTHORED intent. A pre-P.1 device
        genuinely holds a partial block; refusing to record it blocked
        Extract -> Commit for the whole fleet when it was tried."""
        hv = self._complete()
        hv["logging"]["syslog"]["heartbeat"] = 0
        os.makedirs(tmp_path / "host_vars")
        path = hostvars.write_committed(str(tmp_path), hv)
        assert os.path.isfile(path)
