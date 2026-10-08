"""The device-text readers OUTSIDE pipeline.py, against real output.

The operator's sweep, second half (2026-09-27): after C62-C68 were found in
the deploy's verify, every other module that parses device text was run,
on the host, against real captures (`tests/fixtures/operational/`):
topology, NetBox's CDP/LLDP import, the rotation's live username read, and
(measured on the host, not pinned here, because a running config carries
secrets) drift's comparison and the NSoT round trip on today's goldens.

The result, stated because a sweep that finds little is also a result:
- **topology, NetBox's cable readers and the Configure-networks view were
  RIGHT on real output.** Each expectation below is counted from the
  capture independently of the parser: a `State is` line, a `System Name`
  line.
- **Drift was clean on all nine devices** against their goldens, and the
  round trip was 100% with nothing unmodelled on today's goldens. The
  fleet fixtures predate P.1, and the claim holds on the current ones.
- **Two defects, both found by reading, not by the captures:**
  - the codebase had TWO BGP summary parsers, one right (topology's) and
    one wrong (the deploy's, C64). Now there is one;
  - the rotation's live read matched `username <name>` as a PREFIX, so
    `admin` would read `admin2`'s line. Latent here, since every device
    holds one account.
"""

import ast
import os
import re

from modules import topology
from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "operational")


def capture(host, slug):
    with open(os.path.join(FIX, f"{host}__{slug}.txt"), encoding="utf-8") as fh:
        return fh.read()


class TestTopologyOnRealOutput:
    def test_ospf_detail_states_match_the_devices_state_lines(self):
        for host in ("r3", "r1", "s3"):
            text = capture(host, "show_ip_ospf_neighbor_detail")
            expected = re.findall(r"State is (\S+?),", text)
            assert len(expected) >= 5, host
            got = [n["state"] for n in topology.parse_ospf_neighbors(text)]
            assert got == expected, host

    def test_bgp_the_one_reader_on_r3(self):
        peers = topology.parse_bgp_summary(capture("r3", "show_ip_bgp_summary"))["peers"]
        assert [(p["neighbor"], p["established"]) for p in peers] == [("198.51.100.1", True)]

    def test_bgp_not_running_is_empty(self):
        assert topology.parse_bgp_summary(capture("r1", "show_ip_bgp_summary")) == \
            {"local_as": "", "peers": []}

    def test_a_wrapped_ipv6_row_is_joined(self):
        """The one CONSTRUCTED case in this file: no device in the fleet has an
        IPv6 peer. Built from r3's real row, its address moved onto its own
        line the way IOS wraps a long neighbour."""
        text = capture("r3", "show_ip_bgp_summary")
        wrapped = text.replace("198.51.100.1    4", "2001:DB8::1\n                4")
        assert wrapped != text
        peers = topology.parse_bgp_summary(wrapped)["peers"]
        assert [(p["neighbor"], p["established"]) for p in peers] == [("2001:DB8::1", True)]

    def test_a_down_peer_is_configured_not_established(self):
        text = capture("r3", "show_ip_bgp_summary").replace(
            "4d13h           3", "never    Idle (Admin)")
        peers = topology.parse_bgp_summary(text)["peers"]
        assert [(p["state"], p["established"]) for p in peers] == [("Idle (Admin)", False)]

    def test_lldp_names_every_system_the_device_names(self):
        for host in ("r3", "r1", "s1", "s3"):
            text = capture(host, "show_lldp_neighbors_detail")
            expected = [n.split(".")[0] for n in re.findall(r"System Name: (\S+)", text)]
            got = [n["device_id"] for n in topology.parse_lldp_neighbors(text)]
            assert got == expected and expected, host

    def test_cdp_where_it_runs_and_empty_where_it_does_not(self):
        """The C8000vs run no CDP (`Total cdp entries displayed : 0`); the
        switches do."""
        assert topology.parse_cdp_neighbors(capture("r3", "show_cdp_neighbors_detail")) == []
        got = topology.parse_cdp_neighbors(capture("s1", "show_cdp_neighbors_detail"))
        assert [(n["device_id"], n["local_interface"]) for n in got] == \
            [("s2", "GigabitEthernet0/3")]

    def test_interfaces_brief_rows(self):
        for host in ("r3", "s1"):
            text = capture(host, "show_ip_interface_brief")
            rows = [l for l in text.splitlines()[1:] if l.strip()]
            assert len(topology.parse_ip_interfaces(text)) == len(rows), host


class TestNetBoxCableReadersOnRealOutput:
    def test_they_agree_with_topology_by_hostname(self):
        """The cable import keys on the HOSTNAME. The LLDP management address
        is the emulator's (s3 reports 10.0.0.15, which is also r1's and r3's
        own address), so a lookup by that address would have been wrong, and
        none is made."""
        from modules import netbox_client as nb

        for host in ("r3", "s1", "s3"):
            text = capture(host, "show_lldp_neighbors_detail")
            assert [n["remote_hostname"] for n in nb._parse_lldp_neighbors(text)] == \
                [n["device_id"] for n in topology.parse_lldp_neighbors(text)], host


class TestOneBgpReader:
    def test_the_deploy_reads_through_topology(self):
        src = open(os.path.join(ROOT, "modules", "pipeline.py"), encoding="utf-8").read()
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.FunctionDef) and n.name == "_parse_bgp_summary")
        body = ast.unparse(fn)
        assert "parse_bgp_summary(out)" in body and "split()" not in body

    def test_no_third_reader(self):
        """Every function whose name says it reads a BGP summary, across the
        program. The deploy's delegates; topology's is the reader."""
        found = []
        for path in tracked("modules", "routes", suffix=".py"):
            for n in ast.walk(ast.parse(open(path, encoding="utf-8").read())):
                if isinstance(n, ast.FunctionDef) and "bgp_summary" in n.name:
                    found.append((os.path.relpath(path, ROOT), n.name))
        assert sorted(found) == [("modules/pipeline.py", "_parse_bgp_summary"),
                                 ("modules/topology.py", "parse_bgp_summary")], found


class TestTheRotationReadsExactlyItsAccount:
    """Constructed lines: the fleet holds one account per device (measured on
    all nine, 2026-09-27), so the case cannot come from a capture. The
    values are placeholders; only the account NAME is under test."""

    LINES = ("username admin2 privilege 15 secret 9 $9$aaaa\n"
             "username admin privilege 15 secret 9 $9$bbbb\n")

    def test_the_named_account_not_a_prefix_of_another(self):
        from modules.nsot.credential_rotation import users_line
        assert users_line(self.LINES, "admin").startswith("username admin privilege")

    def test_a_longer_name_is_found_by_its_own_name(self):
        from modules.nsot.credential_rotation import users_line
        assert users_line(self.LINES, "admin2").startswith("username admin2 ")

    def test_absent_is_empty(self):
        from modules.nsot.credential_rotation import users_line
        assert users_line(self.LINES, "adm") == ""
