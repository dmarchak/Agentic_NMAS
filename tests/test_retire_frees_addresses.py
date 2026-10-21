"""C1494: retire frees the device's IP addresses in NetBox, and the import says when a retired
record still holds one.

Read 2026-10-21 05:3x UTC: the retired device's record (renamed ``<name>-retired-<id>``, set
Decommissioning) still held its management address on an interface, so the new device given
the same reserved address could not be given it in NetBox. Retire's NetBox step now, with
writes on: clears the record's primary addresses, DELETES the addresses Mercury created (its
delete rule: tagged ``nmas-managed`` AND in its created-object record) and UNASSIGNS the rest,
each through the write gate with its before recorded, then reads back that the record holds
none. With writes off, it says the addresses stay. And the import of a device whose address a
Decommissioning record holds says so, naming that record.

Driven through r5's REAL config and the shape the live NetBox held (`tests/test_retire_gaps.py`'s
fixture), the addresses on documentation values (192.0.2.0/24).
"""

import pytest

import modules.nsot.retire as RT
from tests.test_retire_gaps import _pending, _retire, nb  # noqa: F401  (the fixture)
from tests.test_retire import world  # noqa: F401  (the fixture nb needs)

MINE, THEIRS = "192.0.2.5/32", "192.0.2.9/30"


@pytest.fixture
def held(nb, tmp_path, monkeypatch):  # noqa: F811
    """Device 9 (r5) with two addresses on its interfaces: one Mercury created (tagged and
    recorded), one a person made (neither), the first its primary. The created-object and
    modification records are this test's own."""
    from modules import netbox_guard
    monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE", str(tmp_path / "created.json"))
    monkeypatch.setattr(netbox_guard, "_MODIFIED_FILE", str(tmp_path / "modified.json"))
    fake = nb["fake"]
    loop = fake.seed("dcim/interfaces", {"name": "Loopback0", "device": {"id": 9}})
    gi2 = fake.seed("dcim/interfaces", {"name": "GigabitEthernet2", "device": {"id": 9}})
    mine = fake.seed("ipam/ip-addresses", {
        "address": MINE, "assigned_object_type": "dcim.interface",
        "assigned_object_id": loop["id"],
        "tags": [{"id": 900, "slug": "nmas-managed", "name": "nmas-managed"}]})
    theirs = fake.seed("ipam/ip-addresses", {
        "address": THEIRS, "assigned_object_type": "dcim.interface",
        "assigned_object_id": gi2["id"]})
    netbox_guard.record_created("Lab", "ipam/ip-addresses", mine["id"], MINE)
    fake.store["dcim/devices"][0]["primary_ip4"] = {"id": mine["id"]}
    return dict(nb, mine=mine, theirs=theirs)


def _step(p):
    return next(s["what"] for s in p["steps"] if s["key"] == "netbox_record")


class TestThePreviewNamesEachAddress:
    def test_it_says_which_is_deleted_and_which_unassigned(self, held):
        p = RT.plan("Lab", "r5", "left management")
        assert p["ok"], p["refusals"]
        what = _step(p)
        assert f"delete the IP address(es) Mercury created on it ({MINE}" in what
        assert f"unassign the other(s) from it ({THEIRS})" in what
        assert "netbox_record" in _pending(p)

    def test_an_address_list_that_moves_after_the_preview_moves_the_hash(self, held):
        before = RT.plan("Lab", "r5", "left management")["hash"]
        held["fake"].seed("ipam/ip-addresses", {
            "address": "192.0.2.13/32", "assigned_object_type": "dcim.interface",
            "assigned_object_id": held["theirs"]["assigned_object_id"]})
        assert RT.plan("Lab", "r5", "left management")["hash"] != before

    def test_an_unreadable_address_list_refuses_never_none(self, held, monkeypatch):
        def broken(list_name, nb_id):
            raise RuntimeError("HTTP 500")
        monkeypatch.setattr(RT, "_netbox_address_facts", broken)
        p = RT.plan("Lab", "r5", "left management")
        assert p["ok"] is False and "HTTP 500" in p["refused_by"]["netbox_record"]

    def test_writes_off_says_the_addresses_stay(self, held):
        held["state"]["writes"] = False
        held["fake"].store["dcim/devices"][0]["local_context_data"] = {}
        p = RT.plan("Lab", "r5", "left management")
        assert any("IP addresses stay assigned" in n for n in p["not_doing"]), p["not_doing"]


class TestTheApply:
    def test_mercurys_is_deleted_the_other_unassigned_with_its_before(self, held):
        fake = held["fake"]
        out = _retire(RT.plan("Lab", "r5", "left management"))
        assert out["ok"], out
        assert ("ipam/ip-addresses", held["mine"]["id"]) in fake.deletes
        assert ("ipam/ip-addresses", held["theirs"]["id"]) not in fake.deletes
        kept = next(o for o in fake.objects("ipam/ip-addresses")
                    if o["id"] == held["theirs"]["id"])
        assert (kept["assigned_object_type"], kept["assigned_object_id"]) == (None, None)
        assert (("ipam/ip-addresses", held["theirs"]["id"],
                 {"assigned_object_type": None, "assigned_object_id": None})
                in fake.patches)

    def test_the_primary_is_cleared_in_the_records_own_write_first(self, held):
        fake = held["fake"]
        _retire(RT.plan("Lab", "r5", "left management"))
        record = [p for e, i, p in fake.patches if e == "dcim/devices" and "status" in p]
        assert record == [{"status": "decommissioning", "name": "r5-retired-9",
                           "primary_ip4": None, "primary_ip6": None}]
        order = [(e, i) for e, i, _p in fake.patches]
        assert order.index(("dcim/devices", 9)) < order.index(
            ("ipam/ip-addresses", held["theirs"]["id"]))

    def test_the_read_back_holds_none(self, held):
        from modules.netbox_client import _nb_get
        _retire(RT.plan("Lab", "r5", "left management"))
        assert _nb_get(held["fake"], "http://127.0.0.1:9", "ipam/ip-addresses/",
                       device_id=9) == []

    def test_an_unassign_netbox_did_not_keep_stops_naming_the_address(self, held):
        fake = held["fake"]
        real = fake.patch

        def keeps_addresses(url, json=None, timeout=None):
            if "ipam/ip-addresses" in url:
                return type("R", (), {"ok": True, "status_code": 200,
                                      "json": lambda s: held["theirs"],
                                      "raise_for_status": lambda s: None, "text": ""})()
            return real(url, json=json, timeout=timeout)
        fake.patch = keeps_addresses
        out = _retire(RT.plan("Lab", "r5", "left management"))
        assert out["ok"] is False and out["failed_at"] == "netbox_record", out
        assert THEIRS in out["error"] and "still holds" in out["error"]

    def test_a_device_holding_none_is_written_as_before(self, nb):  # noqa: F811
        """The control: no address, and the record's write is exactly the status and name."""
        _retire(RT.plan("Lab", "r5", "left management"))
        record = [p for e, i, p in nb["fake"].patches if e == "dcim/devices" and "status" in p]
        assert record == [{"status": "decommissioning", "name": "r5-retired-9"}]


class TestTheImportNamesARetiredHolder:
    def _fake(self):
        from tests.fake_netbox import FakeNetBox
        fake = FakeNetBox()
        old = fake.seed("dcim/devices", {"name": "r5-retired-9",
                                         "status": {"value": "decommissioning"}})
        new = fake.seed("dcim/devices", {"name": "r5", "status": {"value": "active"}})
        loop = fake.seed("dcim/interfaces", {"name": "Loopback0", "device": {"id": old["id"]}})
        fake.seed("ipam/ip-addresses", {"address": "192.0.2.6/30",
                                        "assigned_object_type": "dcim.interface",
                                        "assigned_object_id": loop["id"]})
        return fake, old, new

    def test_it_is_said_naming_the_record(self):
        from modules import netbox_client as nc
        fake, old, new = self._fake()
        nc._drain_write_failures()
        named = nc._say_held_by_decommissioned(fake, "http://nb.invalid", "192.0.2.6",
                                               new["id"], "r5")
        said = nc._drain_write_failures()
        assert named == ["r5-retired-9"]
        assert said and "r5-retired-9" in said[0]["error"] and f"NetBox device {old['id']}" \
            in said[0]["error"] and "Decommissioning" in said[0]["error"]

    def test_an_active_holder_or_its_own_is_not_this_finding(self):
        from modules import netbox_client as nc
        fake, old, new = self._fake()
        fake.store["dcim/devices"][0]["status"] = {"value": "active"}
        nc._drain_write_failures()
        assert nc._say_held_by_decommissioned(fake, "http://nb.invalid", "192.0.2.6",
                                              new["id"], "r5") == []
        assert nc._say_held_by_decommissioned(fake, "http://nb.invalid", "192.0.2.6",
                                              old["id"], "r5") == []
        assert nc._drain_write_failures() == []

    def test_the_import_of_the_new_device_says_it(self, tmp_path, monkeypatch):
        """Through the import's own upsert, on r5's real config: the write failures name the
        retired record holding the management address."""
        from modules import netbox_client as nc
        from modules import netbox_guard
        from tests.test_netbox_mask_context import R5
        monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
        monkeypatch.setattr(netbox_guard, "_MODIFIED_FILE", str(tmp_path / "modified.json"))
        monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE", str(tmp_path / "created.json"))
        monkeypatch.setattr(nc, "_managed_tag_ids", {})
        monkeypatch.setattr(nc, "excluded_vrfs", lambda: {"clab-mgmt"})
        fake, _old, _new = self._fake()
        fake.store["dcim/devices"].pop()                 # the new device is created here
        site = fake.seed("dcim/sites", {"name": "Lab", "slug": "lab"})
        role = fake.seed("dcim/device-roles", {"name": "Router", "slug": "router"})
        nc._drain_write_failures()
        with netbox_guard.for_list("Lab", authority="test: declared by the test (C155)"), \
                nc._attributed_to("r5"):
            nc._upsert_device(fake, "http://nb.invalid", hostname="r5", ip="192.0.2.6",
                              facts={"manufacturer": "Cisco", "model": "C8000v",
                                     "platform": "IOS-XE", "serial": "", "version": "17.6"},
                              interfaces=nc._parse_all_interfaces_from_config(R5),
                              site_id=site["id"], role_id=role["id"],
                              ipam_stats={"skipped": []})
        said = [f for f in nc._drain_write_failures() if "192.0.2.6" in f["write"]]
        assert said and "r5-retired-9" in said[0]["error"], said

    def test_the_ipv6_address_is_checked_the_same_way(self):
        from modules import netbox_client as nc
        fake, _old, new = self._fake()
        loop = fake.objects("dcim/interfaces")[0]
        fake.seed("ipam/ip-addresses", {"address": "2001:db8::6/64",
                                        "assigned_object_type": "dcim.interface",
                                        "assigned_object_id": loop["id"]})
        nc._drain_write_failures()
        assert nc._say_held_by_decommissioned(fake, "http://nb.invalid", "2001:db8::6",
                                              new["id"], "r5") == ["r5-retired-9"]
        nc._drain_write_failures()
