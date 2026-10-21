"""C1516: the NetBox import made a prefix of every interface address's own network, so each
loopback became a /32 and a /128 prefix of its own (the operator, 2026-10-21, NetBox's Recent
Activity after the 05:22 UTC import: 10.255.1.17/32 and 2001:db8:1::17/128; measured: 22 such
prefixes, one pair per device). A loopback address is an address inside a pool, never a prefix.

Built: an interface address whose network is host length (IPv4 /32, IPv6 /128) is written as
its address on its interface, and no prefix is made for it; every other network is a prefix as
before. On r2's REAL C8000v capture (tests/fixtures/configs/fleet/r2.cfg), whose Loopback0
holds 10.255.1.12/32 and 2001:DB8:1::12/128.
"""

import ipaddress
import os

import pytest

from modules import netbox_client as nc
from modules import netbox_guard
from tests.fake_netbox import FakeNetBox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r2.cfg")
LIST = "Lab"
AUTH = "test: declared by the test (C155)"


@pytest.fixture(autouse=True)
def writes_on(tmp_path, monkeypatch):
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
    monkeypatch.setattr(netbox_guard, "_MODIFIED_FILE", str(tmp_path / "netbox_modified.json"))
    monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE",
                        str(tmp_path / "netbox_created_ids.json"))
    monkeypatch.setattr(nc, "_managed_tag_ids", {})
    monkeypatch.setattr(nc, "excluded_vrfs", lambda: {"clab-mgmt"})
    nc._drain_write_failures()
    yield
    nc._drain_write_failures()


@pytest.fixture
def imported():
    with open(CAPTURE, encoding="utf-8") as fh:
        golden = fh.read()
    nb = FakeNetBox()
    site = nb.seed("dcim/sites", {"name": LIST, "slug": "lab"})
    role = nb.seed("dcim/device-roles", {"name": "Router", "slug": "router"})
    with netbox_guard.for_list(LIST, authority=AUTH), nc._attributed_to("r2"):
        nc._upsert_device(
            nb, "http://nb.invalid", hostname="r2", ip="10.255.1.12",
            facts={"manufacturer": "Cisco", "model": "C8000v", "platform": "IOS-XE",
                   "serial": "", "version": "17.6"},
            interfaces=nc._parse_all_interfaces_from_config(golden),
            vrfs=nc._parse_vrfs_from_config(golden),
            site_id=site["id"], role_id=role["id"], ipam_stats={"skipped": []})
    return nb


def _networks(nb):
    return [ipaddress.ip_network(o["prefix"]) for o in nb.objects("ipam/prefixes")]


class TestALoopbackIsAnAddressNotAPrefix:
    def test_no_host_length_prefix_is_made(self, imported):
        hosts = [str(n) for n in _networks(imported) if n.prefixlen == n.max_prefixlen]
        assert hosts == []

    def test_the_link_networks_are_still_prefixes(self, imported):
        """The floor: the import still makes the prefixes it should, both families."""
        nets = _networks(imported)
        assert any(n.version == 4 and n.prefixlen < 32 for n in nets), nets
        assert any(n.version == 6 and n.prefixlen < 128 for n in nets), nets

    def test_the_loopback_addresses_are_written_on_loopback0(self, imported):
        lo = next(o for o in imported.objects("dcim/interfaces") if o["name"] == "Loopback0")
        held = sorted(o["address"] for o in imported.objects("ipam/ip-addresses")
                      if o.get("assigned_object_id") == lo["id"])
        assert held == ["10.255.1.12/32", "2001:db8:1::12/128"]


class TestHostLength:
    @pytest.mark.parametrize("prefix,host", [
        ("10.255.1.17/32", True), ("10.255.4.0/31", False), ("10.255.4.0/30", False),
        ("2001:db8:1::17/128", True), ("2001:db8:4::/127", False), ("2001:db8:70:10::/64", False),
        ("not a prefix", False),
    ])
    def test_ipv4_and_ipv6(self, prefix, host):
        assert nc._is_host_network(prefix) is host
