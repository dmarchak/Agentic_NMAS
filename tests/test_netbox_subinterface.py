"""C1492: the NetBox import writes a routed dot1Q subinterface as NetBox models one.

The operator's Import into NetBox (2026-10-21 05:22:25 UTC) was refused on r7's
GigabitEthernet3.10: POST dcim/interfaces answered 400 "untagged_vlan: Interface mode does not
support untagged vlan". The importer set the subinterface's `encapsulation dot1Q` tag as an
untagged VLAN with no 802.1Q mode, and it took that VLAN from the import's list site by number,
creating one there when absent, so it could be another site's VLAN of the same number.

The operator's model, built here: a routed dot1Q subinterface (``<parent>.<n>`` with
``encapsulation dot1Q <vid>``) is a ``virtual`` interface under its parent, never with an
untagged VLAN; its VLAN, when one is carried, is the device's site's (a VLAN group scoped to the
site), as 802.1Q ``tagged``, and never another site's VLAN of the same number; when the site's
groups hold none, the VLAN is refused by name and the interface and its addresses are written
without it. NetBox accepting ``mode: tagged`` on a virtual interface was not measured, so the
VLAN is a separate write after the interface: a refusal there leaves the interface and its
addresses in place and is named.

On a REAL C8000v capture (tests/fixtures/configs/fleet/r2.cfg) with a subinterface added on
documentation addresses (192.0.2.0/24, 2001:db8::/32), the shape tests/test_subinterface_order.py
builds, against `FakeNetBox` taught NetBox's refusal of an untagged VLAN with no mode.
"""

import os

import pytest

from modules import netbox_client as nc
from modules import netbox_guard
from tests.fake_netbox import FakeNetBox, FakeResponse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAPTURE = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r2.cfg")
PARENT, SUB = "GigabitEthernet3", "GigabitEthernet3.10"
LIST = "Lab"
AUTH = "test: declared by the test (C155)"
BLOCK = ("interface GigabitEthernet3.10\n"
         " description Subinterface VLAN 10\n"
         " encapsulation dot1Q 10\n"
         " ip address 192.0.2.1 255.255.255.0\n"
         " ipv6 address 2001:DB8:10::1/64\n"
         "!\n")


def _golden() -> str:
    """r2's capture with the subinterface after its parent's block."""
    with open(CAPTURE, encoding="utf-8") as fh:
        text = fh.read()
    at = text.index(f"interface {PARENT}\n")
    end = text.index("!\n", at) + 2
    return text[:end] + BLOCK + text[end:]


class NetBox(FakeNetBox):
    """`FakeNetBox` with NetBox's refusals this finding met: an interface given an untagged VLAN
    and no 802.1Q mode (the 400 measured 2026-10-21), and, when *groups_forbidden*, a token
    with no view on VLAN groups (C1424, measured 403 on 2026-10-20)."""

    def __init__(self, groups_forbidden=False):
        super().__init__()
        self.groups_forbidden = groups_forbidden

    def _refuses(self, url, payload, obj_id=None):
        endpoint, oid = self._parse(url)
        if endpoint != "dcim/interfaces":
            return None
        held = next((o for o in self.store.get(endpoint, []) if o["id"] == (obj_id or oid)), {})
        mode = payload.get("mode", held.get("mode"))
        if payload.get("untagged_vlan") and not mode:
            return FakeResponse({"untagged_vlan": [
                "Interface mode does not support untagged vlan."]}, 400)
        return None

    def post(self, url, json=None, timeout=None):
        return self._refuses(url, dict(json or {})) or super().post(url, json=json,
                                                                     timeout=timeout)

    def patch(self, url, json=None, timeout=None):
        return self._refuses(url, dict(json or {})) or super().patch(url, json=json,
                                                                      timeout=timeout)

    def get(self, url, params=None, timeout=None):
        if self.groups_forbidden and self._parse(url)[0] == "ipam/vlan-groups":
            return FakeResponse({"detail": "You do not have permission to perform this "
                                           "action."}, 403)
        return super().get(url, params=params, timeout=timeout)


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


def _box(nb=None, site_holds_vlan=True):
    """NetBox with the list's site and another (the core's), each with a VLAN group scoped to
    it holding a VLAN 10, and a global VLAN 10 in no group: two broadcast domains of one number,
    and one belonging to neither site."""
    nb = nb or NetBox()
    site = nb.seed("dcim/sites", {"name": LIST, "slug": "lab"})
    core = nb.seed("dcim/sites", {"name": "Core", "slug": "core"})
    role = nb.seed("dcim/device-roles", {"name": "Router", "slug": "router"})
    mine = nb.seed("ipam/vlan-groups", {"name": "Lab VLANs", "slug": "lab-vlans",
                                        "scope_type": "dcim.site", "scope_id": site["id"]})
    theirs = nb.seed("ipam/vlan-groups", {"name": "Core VLANs", "slug": "core-vlans",
                                          "scope_type": "dcim.site", "scope_id": core["id"]})
    vlans = {"core": nb.seed("ipam/vlans", {"vid": 10, "name": "CORE-10", "group": theirs["id"]}),
             "global": nb.seed("ipam/vlans", {"vid": 10, "name": "GLOBAL-10"})}
    if site_holds_vlan:
        vlans["mine"] = nb.seed("ipam/vlans", {"vid": 10, "name": "LAB-10", "group": mine["id"]})
    return nb, site, core, role, vlans


def _upsert(nb, site, role, golden=None, netbox_id=None):
    golden = golden or _golden()
    with netbox_guard.for_list(LIST, authority=AUTH), nc._attributed_to("r2"):
        out = nc._upsert_device(
            nb, "http://nb.invalid", hostname="r2", ip="10.255.1.12",
            facts={"manufacturer": "Cisco", "model": "C8000v", "platform": "IOS-XE",
                   "serial": "", "version": "17.6"},
            interfaces=nc._parse_all_interfaces_from_config(golden),
            vrfs=nc._parse_vrfs_from_config(golden),
            site_id=site["id"], role_id=role["id"], ipam_stats={"skipped": []},
            netbox_id=netbox_id)
    return out, nc._drain_write_failures()


def _iface(nb, name):
    return next(o for o in nb.objects("dcim/interfaces") if o["name"] == name)


def _held(nb, iface):
    return sorted(o["address"] for o in nb.objects("ipam/ip-addresses")
                  if o.get("assigned_object_id") == iface["id"])


class TestTheSubinterfaceIsWritten:
    def test_the_capture_holds_the_subinterface_the_parser_reads(self):
        got = {i["name"]: i for i in nc._parse_all_interfaces_from_config(_golden())}
        assert got[SUB]["dot1q_tag"] == 10 and got[SUB]["cidr"] == "192.0.2.1/24"
        assert got[SUB]["ipv6_addresses"] == ["2001:db8:10::1/64"]

    def test_it_is_virtual_under_its_parent_with_no_untagged_vlan(self):
        nb, site, _core, role, _v = _box()
        out, failures = _upsert(nb, site, role)
        sub = _iface(nb, SUB)
        assert (sub["type"], sub["parent"]) == ("virtual", out["nb_iface_map"][PARENT])
        assert not sub.get("untagged_vlan")
        assert not [f for f in failures if SUB in str(f)], failures

    def test_its_vlan_is_the_sites_tagged_never_the_cores(self):
        nb, site, _core, role, vlans = _box()
        _upsert(nb, site, role)
        sub = _iface(nb, SUB)
        assert sub["mode"] == "tagged" and sub["tagged_vlans"] == [vlans["mine"]["id"]]
        assert not [p for e, p in nb.posts if e == "ipam/vlans"], "no VLAN is created"

    def test_its_addresses_go_on_it_ipv4_and_ipv6(self):
        nb, site, _core, role, _v = _box()
        _upsert(nb, site, role)
        assert _held(nb, _iface(nb, SUB)) == ["192.0.2.1/24", "2001:db8:10::1/64"]

    def test_a_second_import_changes_nothing(self):
        nb, site, _core, role, _v = _box()
        _upsert(nb, site, role)
        before = len(nb.patches), len(nb.posts)
        _upsert(nb, site, role)
        assert [(e, i, p) for e, i, p in nb.patches[before[0]:]
                if e == "dcim/interfaces"] == []
        assert [e for e, _p in nb.posts[before[1]:]] == []


class TestTheVlanIsRefusedByName:
    def test_a_site_whose_groups_hold_none_is_refused_naming_it(self):
        nb, site, _core, role, vlans = _box(site_holds_vlan=False)
        _out, failures = _upsert(nb, site, role)
        sub = _iface(nb, SUB)
        assert sub["type"] == "virtual" and not sub.get("mode") and not sub.get("tagged_vlans")
        assert vlans["core"]["id"] not in (sub.get("tagged_vlans") or [])
        said = " ".join(str(f) for f in failures)
        assert "VLAN 10" in said and SUB in said and "Lab VLANs" in said
        assert _held(nb, sub) == ["192.0.2.1/24", "2001:db8:10::1/64"]

    def test_a_token_that_cannot_read_vlan_groups_is_said(self):
        nb, site, _core, role, _v = _box(NetBox(groups_forbidden=True))
        _out, failures = _upsert(nb, site, role)
        sub = _iface(nb, SUB)
        assert sub["type"] == "virtual" and not sub.get("tagged_vlans")
        said = " ".join(str(f) for f in failures)
        assert "VLAN groups could not be read" in said and "C1424" in said
        assert _held(nb, sub) == ["192.0.2.1/24", "2001:db8:10::1/64"]

    def test_the_devices_own_site_is_asked_not_the_lists(self):
        """A device a person moved to another site in NetBox (an update never moves it): its
        VLAN is that site's, the core's group here."""
        nb, site, core, role, vlans = _box()
        held = nb.seed("dcim/devices", {"name": "r2", "site": {"id": core["id"]},
                                        "role": {"id": role["id"]}})
        _upsert(nb, site, role, netbox_id=held["id"])
        assert _iface(nb, SUB)["tagged_vlans"] == [vlans["core"]["id"]]


class TestTheFakeRefusesWhatNetBoxRefused:
    def test_an_untagged_vlan_with_no_mode_is_the_measured_400(self):
        nb = NetBox()
        r = nb.post("http://nb.invalid/api/dcim/interfaces/",
                    json={"device": 1, "name": SUB, "type": "virtual", "untagged_vlan": 5})
        assert r.status_code == 400 and "untagged vlan" in r.text
