"""C1442: a device whose management address Kea leases has that address on its one
``ip address dhcp`` interface, in every reader (`modules/nsot/leased_address`).

The lab's r6 and r7 (ZTP devices) say ``ip address dhcp`` on Gi2, and every reader took an
interface's address from intent or the golden alone: NetBox put r6's 10.255.4.2/30 on
Loopback0, Topology drew r4 Gi5 <-> r6 Gi2 "OSPF FULL, not in committed intent" and no RIP
edge between r6 and r7, and Verify's expectations could not see r6 Gi2's adjacency.

No capture of a device with a DHCP-leased interface is in the tree, so each case here is a
MINIMAL EDIT of a real one (`tests/fixtures/configs/fleet/`): the one interface's
``ip address A M`` line replaced by ``ip address dhcp``, and its manifest entry recording the
address that line held, as Verify records a lease (``address_source`` ztp, ``mgmt_ip``,
``mgmt_prefix_len``). The peers' reports are the real Prometheus capture
(`tests/fixtures/prometheus/neighbours.json`) and the real RIP reads
(`tests/fixtures/topology/rip/`). Each planted case is shown failing without the lease.

DHCPv6 is out of scope (no IPv6 lease is recorded): an IPv6 management address in the
manifest is never applied, and an edited interface's static IPv6 addresses stay intent's.
"""

import copy
import json
import os
import subprocess

import pytest
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")
CAPTURE = os.path.join(ROOT, "tests", "fixtures", "prometheus", "neighbours.json")
UP = 'up{job=~"ospf|ospfv3|bgp"}'
METRICS = ("ospfNbrState", "ospfv3NbrState", "cbgpPeer2State")

#: r4's GigabitEthernet4, the /31 to r3 Gi4 (OSPF and OSPFv3), as its capture holds it.
R4_GI4 = " ip address 10.255.2.15 255.255.255.254"
#: r1's GigabitEthernet3, the /31 to s1 Gi0/2 (RIP and RIPng), as its capture holds it.
R1_GI3 = " ip address 10.255.2.10 255.255.255.254"


def _text(host: str) -> str:
    with open(os.path.join(FLEET, f"{host}.cfg"), encoding="utf-8") as fh:
        return fh.read()


def _address_line(host: str, interface: str) -> str:
    """*interface*'s ``ip address`` line in *host*'s capture, read from it (the emulator's
    management address is not written here)."""
    block = _text(host).split(f"\ninterface {interface}\n", 1)[1].split("\n!", 1)[0]
    return next(line for line in block.splitlines() if line.startswith(" ip address "))


def _dhcp(text: str, line: str) -> str:
    """*text* with its one *line* replaced by ``ip address dhcp`` (the minimal edit)."""
    assert text.count(line + "\n") == 1, line
    return text.replace(line + "\n", " ip address dhcp\n")


def _parse(host: str, text: str) -> dict:
    from modules.nsot.parsers import get_parser
    return get_parser("cisco_iosxe" if host.startswith("r") else "cisco_ios").parse(text)


def _fleet(**edits) -> dict:
    """The nine real captures parsed as committed intent holds them, each *edits* host's text
    replaced."""
    out = {}
    for f in sorted(os.listdir(FLEET)):
        host = f[:-4]
        out[host] = _parse(host, edits.get(host) or _text(host))
    return out


def _entry(name, address, prefix, source="ztp"):
    return {"name": name, "mgmt_ip": address, "mgmt_prefix_len": prefix,
            "address_source": source, "platform": "cisco_iosxe"}


def _manifest(*entries) -> dict:
    return {"schema_version": 1, "devices": {f"uid:{e['name']}": e for e in entries}}


R4_LEASE = _entry("r4", "10.255.2.15", 31)
R1_LEASE = _entry("r1", "10.255.2.10", 31)


def _iface(hv, name):
    return next(i for i in hv["interfaces"] if i["name"] == name)


# ---------------------------------------------------------------------------
# The helper.
# ---------------------------------------------------------------------------

class TestTheOneHelper:
    def test_the_edited_capture_says_dhcp_where_its_address_was(self):
        hv = _parse("r4", _dhcp(_text("r4"), R4_GI4))
        assert _iface(hv, "GigabitEthernet4")["ipv4"] == "dhcp"

    def test_the_lease_goes_on_the_one_dhcp_interface_and_nowhere_else(self):
        from modules.nsot import leased_address as L
        hv = _parse("r4", _dhcp(_text("r4"), R4_GI4))
        got = L.with_lease(hv, R4_LEASE)
        assert _iface(got, "GigabitEthernet4")["ipv4"] == "10.255.2.15 255.255.255.254"
        assert {i["name"]: i["ipv4"] for i in got["interfaces"]
                if i["name"] != "GigabitEthernet4"} == \
            {i["name"]: i["ipv4"] for i in hv["interfaces"] if i["name"] != "GigabitEthernet4"}
        assert _iface(hv, "GigabitEthernet4")["ipv4"] == "dhcp", "the intent read is untouched"

    def test_the_interfaces_ipv6_stays_intents_static_address(self):
        from modules.nsot import leased_address as L
        hv = _parse("r4", _dhcp(_text("r4"), R4_GI4))
        got = L.with_lease(hv, R4_LEASE)
        assert _iface(got, "GigabitEthernet4")["ipv6"] == ["2001:DB8:2:E::2/64"]

    def test_a_static_address_is_its_own_whatever_the_manifest_says(self):
        from modules.nsot import leased_address as L
        hv = _parse("r4", _text("r4"))
        gi4 = _iface(hv, "GigabitEthernet4")
        assert L.interface_ipv4(gi4, hv["interfaces"], _entry("r4", "192.0.2.9", 24)) == \
            "10.255.2.15 255.255.255.254"
        assert L.with_lease(hv, R4_LEASE) is hv

    def test_a_static_device_gives_its_dhcp_interface_nothing(self):
        """s1's real capture: Gi0/0 is the emulator's own DHCP interface, and s1's management
        address is static. A manifest that does not say the address is leased applies none."""
        from modules.nsot import leased_address as L
        hv = _parse("s1", _text("s1"))
        assert any(L.is_dhcp(i.get("ipv4")) for i in hv["interfaces"])
        for source in ("static", ""):
            assert L.with_lease(hv, _entry("s1", "10.255.1.21", 32, source)) is hv
        assert L.lease_of(_entry("s1", "10.255.1.21", 32, "static")) is None

    def test_the_reservation_is_the_lease_when_the_management_address_moved(self):
        """The lease is the reserved address (onboarding refuses a lease that disagrees with
        the reservation); a management address moved since Verify does not move it."""
        from modules.nsot import leased_address as L
        hv = _parse("r4", _dhcp(_text("r4"), R4_GI4))
        entry = dict(R4_LEASE, mgmt_ip="192.0.2.77", reserved_address="10.255.2.15")
        assert _iface(L.with_lease(hv, entry), "GigabitEthernet4")["ipv4"] == \
            "10.255.2.15 255.255.255.254"

    def test_an_address_intent_holds_statically_is_never_a_lease(self):
        """A management address moved to the device's Loopback0 (static in intent), the
        reservation not recorded: no interface is given it with the old prefix length."""
        from modules.nsot import leased_address as L
        hv = _parse("r4", _dhcp(_text("r4"), R4_GI4))
        entry = _entry("r4", "10.255.1.14", 31)
        assert L.with_lease(hv, entry) is hv
        assert "statically" in L.why_not(hv["interfaces"], entry)

    def test_no_prefix_length_is_unknown_never_guessed(self):
        from modules.nsot import leased_address as L
        hv = _parse("r4", _dhcp(_text("r4"), R4_GI4))
        assert L.with_lease(hv, _entry("r4", "10.255.2.15", 0)) is hv
        assert "prefix length" in L.why_not(hv["interfaces"], _entry("r4", "10.255.2.15", 0))

    def test_an_ipv6_management_address_is_not_a_lease_dhcpv6_is_out_of_scope(self):
        from modules.nsot import leased_address as L
        hv = _parse("r4", _dhcp(_text("r4"), R4_GI4))
        assert L.lease_of(_entry("r4", "2001:db8:2:e::2", 64)) is None
        assert L.with_lease(hv, _entry("r4", "2001:db8:2:e::2", 64)) is hv

    def test_two_dhcp_interfaces_take_the_one_outside_a_vrf(self):
        """r4's Gi1 is the emulator's management port, in VRF clab-mgmt: made DHCP too, the
        lease still goes on Gi4, the one in the global table."""
        from modules.nsot import leased_address as L
        text = _dhcp(_dhcp(_text("r4"), R4_GI4), _address_line("r4", "GigabitEthernet1"))
        hv = _parse("r4", text)
        assert [i["name"] for i in hv["interfaces"] if L.is_dhcp(i.get("ipv4"))] == \
            ["GigabitEthernet1", "GigabitEthernet4"]
        got = L.with_lease(hv, R4_LEASE)
        assert _iface(got, "GigabitEthernet4")["ipv4"] == "10.255.2.15 255.255.255.254"
        assert _iface(got, "GigabitEthernet1")["ipv4"] == "dhcp"

    def test_two_in_the_global_table_are_not_guessed_and_the_why_names_both(self):
        from modules.nsot import leased_address as L
        text = _dhcp(_dhcp(_text("r4"), R4_GI4), " ip address 10.255.3.14 255.255.255.0")
        hv = _parse("r4", text)
        assert L.with_lease(hv, R4_LEASE) is hv
        why = L.why_not(hv["interfaces"], R4_LEASE)
        assert "GigabitEthernet3" in why and "GigabitEthernet4" in why


# ---------------------------------------------------------------------------
# Topology and the Neighbours tab: the r4 Gi5 <-> r6 Gi2 case, on r3 <-> r4 Gi4.
# ---------------------------------------------------------------------------

def _reports(host):
    with open(CAPTURE, encoding="utf-8") as fh:
        cap = json.load(fh)
    res = {m: [r for r in cap[m]["data"]["result"] if r["metric"].get("device") == host]
           for m in METRICS}
    up = {r["metric"]["job"]: int(r["value"][1]) for r in cap[UP]["data"]["result"]
          if r["metric"]["device"] == host}
    return res, up


def _rows(view, proto):
    return next((p["rows"] for p in view["protocols"] if p["proto"] == proto), [])


class TestTheAdjacencyIsExpected:
    def _leased(self):
        from modules.nsot import leased_address as L
        return L.with_leases(_fleet(r4=_dhcp(_text("r4"), R4_GI4)), _manifest(R4_LEASE))

    def test_r3s_adjacency_to_the_leased_interface_is_expected_and_up(self):
        from modules import neighbours as N
        view = N.compare(self._leased(), "r3", *_reports("r3"))
        ospf = {(r["peer"], r["via"]): r["state"] for r in _rows(view, "ospf")}
        assert ospf[("r4", "GigabitEthernet4")] == "up"
        assert view["counts"]["unexpected"] == 0

    def test_without_the_lease_it_is_the_reported_defect(self):
        """The planted case: the same intent with no lease applied draws what Topology drew,
        an adjacency r3 reports on the /31 that intent does not explain."""
        from modules import neighbours as N
        view = N.compare(_fleet(r4=_dhcp(_text("r4"), R4_GI4)), "r3", *_reports("r3"))
        rows = _rows(view, "ospf")
        assert ("r4", "GigabitEthernet4") not in {(r["peer"], r["via"]) for r in rows}
        assert any(r["state"] == "unexpected" and r["address"] == "10.255.2.15" for r in rows)

    def test_from_the_leased_side_the_peer_is_expected_too(self):
        from modules import neighbours as N
        got = {(e["peer"], e["via"]) for e in N.expected(self._leased(), "r4")
               if e["proto"] == "ospf"}
        assert ("r3", "GigabitEthernet4") in got

    def test_ospfv3_on_the_same_interface_rides_its_static_ipv6(self):
        from modules import neighbours as N
        for intents in (self._leased(), _fleet(r4=_dhcp(_text("r4"), R4_GI4))):
            got = {(e["peer"], e["via"], e["network"]) for e in N.expected(intents, "r3")
                   if e["proto"] == "ospfv3"}
            assert ("r4", "GigabitEthernet4", "2001:db8:2:e::/64") in got

    def test_the_address_is_owned_and_the_area_read(self):
        from modules import neighbours as N
        from modules.readers import topology_graph as T
        leased = self._leased()
        import ipaddress
        assert N.addresses(leased)[ipaddress.ip_address("10.255.2.15")] == "r4"
        assert N._peer_address(leased["r4"], "10.255.2.14/31") == "10.255.2.15"
        assert T._area(leased["r4"], "ospf", "GigabitEthernet4") == "0"
        bare = _fleet(r4=_dhcp(_text("r4"), R4_GI4))
        assert T._area(bare["r4"], "ospf", "GigabitEthernet4") == ""


class TestTheRipEdgeDraws:
    """The r6 <-> r7 RIPv2 case on the lab's measured r1 <-> s1 RIP (r1 Gi3 leased)."""

    def _rip(self):
        from tests.test_topology_graph import _rip
        return _rip()

    def test_rip_runs_on_the_leased_interface(self):
        from modules.nsot import leased_address as L
        from modules.readers.rip import rip_interfaces
        hv = _parse("r1", _dhcp(_text("r1"), R1_GI3))
        assert "GigabitEthernet3" not in rip_interfaces(hv)
        assert "GigabitEthernet3" in rip_interfaces(L.with_lease(hv, R1_LEASE))

    def test_the_edge_is_drawn_heard_both_ways(self):
        from modules.nsot import leased_address as L
        from modules.readers.topology_graph import rip_links
        intents = L.with_leases(_fleet(r1=_dhcp(_text("r1"), R1_GI3)), _manifest(R1_LEASE))
        links = rip_links(intents, ["r1", "r2", "s1", "s2"], self._rip())
        got = {(x["a"], x["b"], x["network"]): (x["state"], x["intended"])
               for x in links["rip"]}
        assert got[("r1", "s1", "10.255.2.10/31")] == ("up", True)

    def test_without_the_lease_no_edge_is_drawn(self):
        from modules.readers.topology_graph import rip_links
        links = rip_links(_fleet(r1=_dhcp(_text("r1"), R1_GI3)), ["r1", "r2", "s1", "s2"],
                          self._rip())
        assert not [x for x in links["rip"] if {x["a"], x["b"]} == {"r1", "s1"}]

    def test_ripng_on_the_same_link_is_drawn_either_way(self):
        from modules.nsot import leased_address as L
        from modules.readers.topology_graph import rip_links
        bare = _fleet(r1=_dhcp(_text("r1"), R1_GI3))
        for intents in (bare, L.with_leases(bare, _manifest(R1_LEASE))):
            links = rip_links(intents, ["r1", "r2", "s1", "s2"], self._rip())
            assert ("r1", "s1", "2001:db8:2:a::/64") in {(x["a"], x["b"], x["network"])
                                                         for x in links["ripng"]}


class TestVerifysExpectations:
    def test_shutting_the_leased_interface_predicts_its_adjacency_drop(self):
        from modules.nsot import expected_effects as fx
        from modules.nsot import leased_address as L
        bare = _fleet(r4=_dhcp(_text("r4"), R4_GI4))
        program = ["interface GigabitEthernet4", " shutdown", "exit"]
        leased = fx.for_device(L.with_leases(bare, _manifest(R4_LEASE)), "r4", program)
        drops = {(d["proto"], d["peer"]) for d in leased["adjacencies_drop"]}
        assert ("ospf", "r3") in drops and ("ospfv3", "r3") in drops
        without = {(d["proto"], d["peer"])
                   for d in fx.for_device(bare, "r4", program)["adjacencies_drop"]}
        assert ("ospf", "r3") not in without and ("ospfv3", "r3") in without

    def test_its_interface_network_is_known(self):
        import ipaddress

        from modules.nsot import expected_effects as fx
        from modules.nsot import leased_address as L
        hv = L.with_lease(_parse("r4", _dhcp(_text("r4"), R4_GI4)), R4_LEASE)
        assert fx._interface_networks(hv)["GigabitEthernet4"] == \
            ipaddress.ip_network("10.255.2.14/31")


# ---------------------------------------------------------------------------
# Every reader of committed intent: the manifest read in the same two git calls.
# ---------------------------------------------------------------------------

def _git(repo, *args):
    subprocess.run(["git", "-C", repo, "-c", "user.email=t@example.com", "-c", "user.name=t",
                    *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    repo = str(tmp_path / "config_repo")
    subprocess.run(["git", "init", "-q", repo], check=True)
    os.makedirs(os.path.join(repo, "host_vars"))
    os.makedirs(os.path.join(repo, ".nsot"))
    for host, hv in _fleet(r4=_dhcp(_text("r4"), R4_GI4)).items():
        with open(os.path.join(repo, "host_vars", f"{host}.yml"), "w", encoding="utf-8") as fh:
            yaml.safe_dump(dict(hv, hostname=host), fh)
    with open(os.path.join(repo, ".nsot", "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(_manifest(R4_LEASE), fh)
    _git(repo, "add", "host_vars", ".nsot")
    _git(repo, "commit", "-q", "-m", "intent and manifest")
    return repo


class TestCommittedIntentCarriesTheLease:
    def test_the_lease_is_applied_in_the_same_two_git_calls(self, repo, monkeypatch):
        from modules import neighbours as N
        calls, real_run = [], subprocess.run

        def counting(argv, *a, **k):
            if argv[:2] == ["git", "-C"]:
                calls.append(argv[3])
            return real_run(argv, *a, **k)
        monkeypatch.setattr(subprocess, "run", counting)
        docs, err = N.committed_intents(repo)
        assert err == "" and len(docs) == 9
        assert _iface(docs["r4"], "GigabitEthernet4")["ipv4"] == "10.255.2.15 255.255.255.254"
        assert calls == ["ls-tree", "cat-file"]

    def test_it_reads_the_committed_manifest_never_the_working_file(self, repo):
        from modules import neighbours as N
        with open(os.path.join(repo, ".nsot", "manifest.json"), "w", encoding="utf-8") as fh:
            json.dump(_manifest(_entry("r4", "192.0.2.15", 31)), fh)
        docs, _err = N.committed_intents(repo)
        assert _iface(docs["r4"], "GigabitEthernet4")["ipv4"] == "10.255.2.15 255.255.255.254"

    def test_no_manifest_committed_reads_intent_as_it_is(self, repo):
        from modules import neighbours as N
        _git(repo, "rm", "-q", "--cached", ".nsot/manifest.json")
        _git(repo, "commit", "-q", "-m", "no manifest")
        docs, err = N.committed_intents(repo)
        assert err == "" and _iface(docs["r4"], "GigabitEthernet4")["ipv4"] == "dhcp"

    def test_a_manifest_that_does_not_parse_is_said(self, repo):
        from modules import neighbours as N
        with open(os.path.join(repo, ".nsot", "manifest.json"), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        _git(repo, "add", ".nsot")
        _git(repo, "commit", "-q", "-m", "broken manifest")
        docs, err = N.committed_intents(repo)
        assert "manifest does not parse" in err and len(docs) == 9
        assert _iface(docs["r4"], "GigabitEthernet4")["ipv4"] == "dhcp"


# ---------------------------------------------------------------------------
# NetBox: the address on the leased interface, and the fleet's platform.
# ---------------------------------------------------------------------------

LIST = "Lab"
AUTH = "test: declared by the test (C155)"


@pytest.fixture
def writes_on(tmp_path, monkeypatch):
    from modules import netbox_client as nc
    from modules import netbox_guard
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
    monkeypatch.setattr(netbox_guard, "_MODIFIED_FILE", str(tmp_path / "netbox_modified.json"))
    monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE",
                        str(tmp_path / "netbox_created_ids.json"))
    monkeypatch.setattr(nc, "_managed_tag_ids", {})
    monkeypatch.setattr(nc, "excluded_vrfs", lambda: {"clab-mgmt"})
    nc._drain_write_failures()
    yield nc
    nc._drain_write_failures()


def _scan(monkeypatch, text, dev, manifest):
    from modules import netbox_client as nc
    monkeypatch.setattr("modules.goldens._golden_record",
                        lambda ip, list_name="": {"text": text, "refused": ""})
    return nc._scan_device_from_golden(dev, LIST, manifest)


def _box():
    from tests.fake_netbox import FakeNetBox
    nb = FakeNetBox()
    site = nb.seed("dcim/sites", {"name": LIST, "slug": "lab"})
    role = nb.seed("dcim/device-roles", {"name": "Router", "slug": "router"})
    #: The fleet's platform as NetBox holds it (read 2026-10-20: "Cisco IOS XE").
    plat = nb.seed("dcim/platforms", {"name": "Cisco IOS XE", "slug": "cisco-ios-xe"})
    return nb, site, role, plat


def _upsert(nc, nb, site, role, scan):
    from modules import netbox_guard
    with netbox_guard.for_list(LIST, authority=AUTH), nc._attributed_to(scan["hostname"]):
        return nc._upsert_device(
            nb, "http://nb.invalid", hostname=scan["hostname"], ip=scan["ip"],
            facts=scan["facts"], interfaces=scan["interfaces"], vrfs=scan["vrfs"],
            static_routes=scan["static_routes"], site_id=site["id"], role_id=role["id"],
            ipam_stats={"skipped": []}, dialect=scan["dialect"])


class TestTheNetBoxImport:
    DEV = {"ip": "10.255.2.15", "hostname": "r4", "platform": "cisco_iosxe"}

    def test_the_scan_puts_the_lease_on_the_dhcp_interface(self, writes_on, monkeypatch):
        scan = _scan(monkeypatch, _dhcp(_text("r4"), R4_GI4), dict(self.DEV),
                     _manifest(R4_LEASE))
        by = {i["name"]: i for i in scan["interfaces"]}
        assert (by["GigabitEthernet4"]["cidr"], by["GigabitEthernet4"]["prefix"]) == \
            ("10.255.2.15/31", "10.255.2.14/31")
        assert by["GigabitEthernet4"]["ipv6_addresses"] == ["2001:db8:2:e::2/64"]
        assert by["Loopback0"]["cidr"] == "10.255.1.14/32"

    def test_without_the_lease_the_interface_has_no_address(self, writes_on, monkeypatch):
        scan = _scan(monkeypatch, _dhcp(_text("r4"), R4_GI4), dict(self.DEV),
                     _manifest(_entry("r4", "10.255.2.15", 31, "static")))
        gi4 = next(i for i in scan["interfaces"] if i["name"] == "GigabitEthernet4")
        assert gi4["dhcp"] and gi4["cidr"] is None

    def test_the_record_holds_it_on_that_interface_as_its_primary(self, writes_on,
                                                                   monkeypatch):
        nc = writes_on
        nb, site, role, _plat = _box()
        scan = _scan(monkeypatch, _dhcp(_text("r4"), R4_GI4), dict(self.DEV),
                     _manifest(R4_LEASE))
        out = _upsert(nc, nb, site, role, scan)
        held = [o for o in nb.objects("ipam/ip-addresses") if o["address"] == "10.255.2.15/31"]
        assert len(held) == 1
        assert held[0]["assigned_object_id"] == out["nb_iface_map"]["GigabitEthernet4"]
        device = nb.get(f"http://nb.invalid/api/dcim/devices/{out['id']}/").json()
        assert device["primary_ip4"] == held[0]["id"]
        loop = out["nb_iface_map"]["Loopback0"]
        assert not [o for o in nb.objects("ipam/ip-addresses")
                    if o["assigned_object_id"] == loop and o["address"].startswith("10.255.2.")]

    def test_without_it_the_interface_and_the_primary_are_wrong(self, writes_on, monkeypatch):
        """The planted case: no lease, and the management address is on no interface; the
        primary falls back to Loopback0's (r6, whose Loopback0 had no address, was given its
        management address there as a new one)."""
        nc = writes_on
        nb, site, role, _plat = _box()
        text = _dhcp(_text("r4"), R4_GI4)
        scan = _scan(monkeypatch, text, dict(self.DEV), _manifest())
        out = _upsert(nc, nb, site, role, scan)
        gi4 = out["nb_iface_map"]["GigabitEthernet4"]
        assert not [o for o in nb.objects("ipam/ip-addresses")
                    if o["assigned_object_id"] == gi4 and o["address"].startswith("10.")]
        device = nb.get(f"http://nb.invalid/api/dcim/devices/{out['id']}/").json()
        primary = next(o for o in nb.objects("ipam/ip-addresses")
                       if o["id"] == device["primary_ip4"])
        assert primary["assigned_object_id"] == out["nb_iface_map"]["Loopback0"]

    def test_a_capture_without_the_header_is_given_the_fleets_platform(self, writes_on,
                                                                       monkeypatch):
        """Onboarding's own capture carries no `! Cisco IOS XE Software` header (the fleet's
        Oxidized captures do): its first line removed, the minimal edit."""
        nc = writes_on
        nb, site, role, plat = _box()
        text = _dhcp(_text("r4"), R4_GI4).split("\n", 1)[1]
        assert "IOS XE" not in text and "IOS-XE" not in text
        scan = _scan(monkeypatch, text, dict(self.DEV), _manifest(R4_LEASE))
        assert scan["facts"]["platform"] == "IOS-XE" and scan["dialect"] == "cisco_iosxe"
        _upsert(nc, nb, site, role, scan)
        created = [p for e, p in nb.posts if e == "dcim/devices"]
        assert created and created[0]["platform"] == plat["id"]
        assert not [p for e, p in nb.posts if e == "dcim/platforms"]

    def test_an_unknown_dialect_keeps_the_texts_reading(self, writes_on, monkeypatch):
        """The control: a device whose inventory names no dialect reads the text as before,
        "IOS" for a text that says nothing, and NetBox is given that platform."""
        nc = writes_on
        nb, site, role, plat = _box()
        text = _text("r4").split("\n", 1)[1]
        scan = _scan(monkeypatch, text, {"ip": "10.255.1.14", "hostname": "r4"}, _manifest())
        assert scan["facts"]["platform"] == "IOS" and scan["dialect"] == ""
        _upsert(nc, nb, site, role, scan)
        made = [p for e, p in nb.posts if e == "dcim/platforms"]
        assert [m["name"] for m in made] == ["IOS"]
        created = [p for e, p in nb.posts if e == "dcim/devices"]
        assert created[0]["platform"] != plat["id"]


class TestTheDialectsSlugs:
    def test_each_dialect_names_the_slug_the_fleet_holds(self):
        from modules.nsot.platform import netbox_slugs_for_dialect
        assert netbox_slugs_for_dialect("cisco_iosxe")[0] == "cisco-ios-xe"
        assert netbox_slugs_for_dialect("cisco_ios")[0] == "cisco-ios"
        assert netbox_slugs_for_dialect("") == [] and netbox_slugs_for_dialect("junos") == []


def test_the_fixture_edit_is_one_line():
    """The edit is minimal: the edited capture differs from the real one in one line."""
    real, edited = _text("r4").splitlines(), _dhcp(_text("r4"), R4_GI4).splitlines()
    assert len(real) == len(edited)
    assert [(a, b) for a, b in zip(real, edited) if a != b] == [(R4_GI4, " ip address dhcp")]
    assert copy.deepcopy(R4_LEASE)["mgmt_ip"] == R4_GI4.split()[2]
