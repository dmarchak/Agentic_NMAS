"""C1009 and the branch's own NetBox site (the operator, 2026-10-21: Lab 8's rehearsal walk, D9).

After R6's and R7's Retire, their old records stay in Default, renamed ``<name>-retired-<id>``
and set to Decommissioning (`retire._netbox_record_facts`). The new R6 and R7 are planned by a
person in another site, ``Branch``. Three things must hold, or b6 has to move the old records
instead:

1. onboarding's by-name read (`device_environment.read`) takes the Planned Branch record and can
   never take the retired one; two records of the name are refused, naming both, never one
   chosen;
2. Verify records the Planned record's id in the manifest, never the retired record's (C1342:
   the retired created-object entry is not matched by name);
3. the import (C1009) finds the record by the id onboarding recorded, in whatever site, so it
   makes no second record in the network's site, and never takes a retired record by an id.

The records are r6's real capture (tests/fixtures/netbox/device_records.json), with the id,
name, site and status each case needs.
"""

import copy
import json
import os

import pytest

from modules.nsot import device_environment as DE
from tests.fake_netbox import FakeNetBox

BASE = "http://netbox.example.test:8000"
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "netbox",
                       "device_records.json")
PLANNED = {"label": "Planned", "value": "planned"}
DECOMMISSIONING = {"label": "Decommissioning", "value": "decommissioning"}
BRANCH = {"id": 902, "name": "Branch", "slug": "branch"}
RETIRED_ID, PLANNED_ID = 22, 31


def _record(dev_id, name, status, site=None):
    with open(FIXTURE, encoding="utf-8") as fh:
        dev = copy.deepcopy(json.load(fh)["r6"]["device"])
    dev.update(id=dev_id, name=name, status=status, config_context={})
    if site:
        dev["site"] = dict(site)
    return dev


def _world(retired_name="r6-retired-22"):
    """NetBox after b1 to b6: the retired record in Default, the Planned one in Branch."""
    nb = FakeNetBox()
    retired = _record(RETIRED_ID, retired_name, DECOMMISSIONING)
    planned = _record(PLANNED_ID, "r6", PLANNED, site=BRANCH)
    nb.store.setdefault("dcim/devices", []).extend([retired, planned])
    for site in (retired["site"], BRANCH):
        nb.seed("dcim/sites", {k: site[k] for k in ("id", "name", "slug")})
    nb.seed("dcim/device-roles", {"id": planned["role"]["id"], "name": "Router",
                                  "slug": "router", "custom_fields": {"mercury_kind": "router"}})
    return nb, retired, planned, (lambda: (True, "", nb, BASE))


class TestOnboardingReadsThePlannedBranchRecord:
    def test_the_by_name_read_takes_the_planned_branch_record(self):
        _nb, _retired, _planned, ready = _world()
        rec = DE.read("r6", ready=ready).netbox
        assert (rec["id"], rec["status"], rec["site"]) == (PLANNED_ID, "planned", "Branch")

    def test_the_retired_record_is_never_read_by_the_name(self):
        _nb, _retired, _planned, ready = _world()
        rec = DE.read("r6", ready=ready).record()
        assert rec["netbox_id"] == PLANNED_ID != RETIRED_ID

    def test_two_records_of_the_name_are_refused_naming_both(self):
        """Retire's rename did not land: both records are `r6`, in two sites. None is chosen."""
        _nb, _retired, _planned, ready = _world(retired_name="r6")
        with pytest.raises(DE.EnvironmentUnreadable) as err:
            DE.read("r6", ready=ready)
        assert f"NetBox holds 2 devices named r6 (ids {RETIRED_ID}, {PLANNED_ID})" \
            in str(err.value)


class TestVerifyRecordsThePlannedRecordsId:
    @pytest.fixture
    def onboarding(self, monkeypatch):
        from modules.nsot import onboard
        nb, _retired, _planned, ready = _world()
        monkeypatch.setattr("modules.netbox_client._nb_ready", ready)
        monkeypatch.setattr("modules.nsot.manifest.find_by_name",
                            lambda repo, name: ("uid:new", {"mgmt_ip": "192.0.2.6"}))
        monkeypatch.setattr("modules.goldens._load_golden_config_file",
                            lambda ip, list_name: "hostname r6\n")
        monkeypatch.setattr("modules.nsot.hostvars.read_committed", lambda repo, h: {
            "bootstrap": {"environment": {"netbox_id": PLANNED_ID,
                                          "netbox_status": "planned"}}})
        return onboard, nb, monkeypatch

    def test_the_planned_records_id_not_the_retired_ones(self, onboarding):
        onboard, _nb, monkeypatch = onboarding
        # The old r6's created-object entry, marked retired by its Retire (C1342).
        monkeypatch.setattr("modules.netbox_guard.get_created", lambda *a, **k: {
            "dcim/devices": [{"id": RETIRED_ID, "name": "r6", "retired": True}]})
        out = onboard.create_netbox_record("/nowhere", "r6", "probe",
                                           sync=lambda l, devs, **k: {"ok": True})
        assert out["ok"] and out["device_id"] == PLANNED_ID, out

    def test_an_entry_not_marked_retired_would_be_taken(self, onboarding):
        """Why Retire marks the entry: unmarked, the old id would be written for the new r6."""
        onboard, _nb, monkeypatch = onboarding
        monkeypatch.setattr("modules.netbox_guard.get_created", lambda *a, **k: {
            "dcim/devices": [{"id": RETIRED_ID, "name": "r6"}]})
        out = onboard.create_netbox_record("/nowhere", "r6", "probe",
                                           sync=lambda l, devs, **k: {"ok": True})
        assert out["device_id"] == RETIRED_ID


class TestTheImportFindsTheRecordOnboardingRecorded:
    DEFAULT_SITE = 1

    @pytest.fixture(autouse=True)
    def _writes_open(self, monkeypatch):
        from modules import netbox_guard
        monkeypatch.setattr(netbox_guard, "assert_writes_allowed", lambda *a, **k: None)

    def _upsert(self, nb, **kw):
        from modules import netbox_client as NC
        return NC._upsert_device(nb, BASE, hostname="r6", ip="192.0.2.6", facts={},
                                 interfaces=[], site_id=self.DEFAULT_SITE, role_id=2,
                                 ipam_stats={}, **kw)

    @staticmethod
    def _device_posts(nb):
        return [p for p in nb.posts if p[0] == "dcim/devices"]

    def test_the_branch_record_is_updated_by_its_recorded_id(self):
        nb, _retired, _planned, _ready = _world()
        out = self._upsert(nb, recorded_netbox_id=PLANNED_ID)
        assert out["action"] == "updated"
        assert not self._device_posts(nb), "a second record was made"
        assert [p[1] for p in nb.patches if p[0] == "dcim/devices"] == [PLANNED_ID]
        written = [k for p in nb.patches if p[0] == "dcim/devices" for k in p[2]]
        assert "site" not in written, "an update never moves a record's site"

    def test_without_it_the_old_match_makes_a_second_record(self):
        """C1009 as it was: by name within the network's site, the Branch record is missed."""
        nb, _retired, _planned, _ready = _world()
        self._upsert(nb)
        assert len(self._device_posts(nb)) == 1

    def test_a_retired_record_is_never_taken_by_a_recorded_id(self):
        nb, _retired, _planned, _ready = _world()
        self._upsert(nb, recorded_netbox_id=RETIRED_ID)
        assert RETIRED_ID not in [p[1] for p in nb.patches if p[0] == "dcim/devices"]

    def test_a_recorded_record_gone_is_matched_as_before(self):
        nb, _retired, _planned, _ready = _world()
        out = self._upsert(nb, recorded_netbox_id=999)
        assert out["action"] == "created"

    def test_the_scan_offers_the_id_the_manifest_holds(self, monkeypatch):
        from modules import netbox_client as NC
        monkeypatch.setattr("modules.goldens._golden_record",
                            lambda ip, list_name: {"text": "hostname r6\n", "refused": ""})
        manifest = {"devices": {"uid:new": {"name": "r6", "netbox_id": PLANNED_ID}}}
        got = NC._scan_device_from_golden({"hostname": "r6", "ip": "192.0.2.6"}, "probe",
                                          manifest)
        assert got["recorded_netbox_id"] == PLANNED_ID
        assert got["netbox_id"] is None, "the caller's id stays the caller's"


class TestTwoVlan10sEachResolvedByItsOwnSite:
    """The operator, 2026-10-21: NetBox holds two VID 10s, the core's `VLAN10` at site Default
    in no group and the branch's `VLAN10` in group "Branch VLANs" scoped to site Branch (read
    live ~16:45 UTC: ids 1 and 6). Every Mercury VLAN lookup is one of two, both in the
    import: `_ensure_vlan` (a switch's VLAN definitions, access and trunk ports) filters by the
    network's site, and `_site_vlan` (a routed subinterface) takes the VLAN groups scoped to its
    record's own site. Drift, Topology and the other readers read no NetBox VLAN. The dry runs
    on the host the same afternoon (s1, s2: VLAN id 1 each; r7 in Default: refused; the Branch
    site: VLAN id 6) are these cases on the real NetBox. s1's capture is real
    (tests/fixtures/configs/fleet/s1.cfg); r7's Gi3.10 is r2's real capture with the
    subinterface block test_netbox_subinterface.py adds."""

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    SUB_BLOCK = ("interface GigabitEthernet3.10\n"
                 " description VLAN 10 behind the branch router\n"
                 " encapsulation dot1Q 10\n"
                 " ip address 192.0.2.1 255.255.255.0\n"
                 "!\n")

    @pytest.fixture(autouse=True)
    def writes_on(self, tmp_path, monkeypatch):
        from modules import netbox_client as nc
        from modules import netbox_guard
        monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
        monkeypatch.setattr(netbox_guard, "_MODIFIED_FILE",
                            str(tmp_path / "netbox_modified.json"))
        monkeypatch.setattr(netbox_guard, "_CREATED_IDS_FILE",
                            str(tmp_path / "netbox_created_ids.json"))
        monkeypatch.setattr(nc, "_managed_tag_ids", {})
        monkeypatch.setattr(nc, "excluded_vrfs", lambda: {"clab-mgmt"})
        nc._drain_write_failures()
        yield
        nc._drain_write_failures()

    @staticmethod
    def _netbox():
        nb, _retired, planned, _ready = _world()
        group = nb.seed("ipam/vlan-groups", {"name": "Branch VLANs", "slug": "branch-vlans",
                                             "scope_type": "dcim.site",
                                             "scope_id": BRANCH["id"]})
        # The branch's first: a lookup that ignored the site would take it.
        branch = nb.seed("ipam/vlans", {"vid": 10, "name": "VLAN10", "group": group["id"]})
        core = nb.seed("ipam/vlans", {"vid": 10, "name": "VLAN10", "site": 1})
        return nb, planned, core, branch

    def _capture(self, name):
        with open(os.path.join(self.ROOT, "tests", "fixtures", "configs", "fleet", name),
                  encoding="utf-8") as fh:
            return fh.read()

    def _import(self, nb, hostname, text, **kw):
        from modules import netbox_client as nc
        from modules import netbox_guard
        with netbox_guard.for_list("Default", authority="test: declared by the test (C155)"), \
                nc._attributed_to(hostname):
            nc._upsert_device(
                nb, BASE, hostname=hostname, ip="192.0.2.6",
                facts={"manufacturer": "Cisco", "model": "C8000v", "platform": "IOS-XE",
                       "serial": "", "version": "17.6"},
                interfaces=nc._parse_all_interfaces_from_config(text),
                vlans=nc._parse_vlans_from_config(text),
                vrfs=nc._parse_vrfs_from_config(text),
                site_id=1, role_id=2, ipam_stats={"skipped": []}, **kw)
        return nc._drain_write_failures()

    @staticmethod
    def _vlan_ids(nb, iface, field):
        held = next(o for o in nb.objects("dcim/interfaces") if o["name"] == iface).get(field)
        held = held if isinstance(held, list) else [held] if held else []
        return sorted(v.get("id") if isinstance(v, dict) else v for v in held)

    def test_a_core_switch_resolves_the_default_sites_vlan10(self):
        from modules import netbox_client as nc
        nb, _planned, core, branch = self._netbox()
        text = self._capture("s1.cfg")
        access = [i["name"] for i in nc._parse_all_interfaces_from_config(text)
                  if i.get("access_vlan") == 10]
        assert access, "s1's capture holds an access port in VLAN 10 (the floor)"
        self._import(nb, "s1", text)
        assert self._vlan_ids(nb, access[0], "untagged_vlan") == [core["id"]]
        assert all(branch["id"] not in self._vlan_ids(nb, o["name"], "tagged_vlans")
                   for o in nb.objects("dcim/interfaces") if o.get("tagged_vlans"))
        assert len([v for v in nb.objects("ipam/vlans") if v.get("vid") == 10]) == 2, \
            "no third VLAN 10 was made"

    def test_r7_in_branch_resolves_the_branch_groups_vlan10(self):
        nb, planned, core, branch = self._netbox()
        text = self._capture("r2.cfg")
        at = text.index("interface GigabitEthernet3\n")
        end = text.index("!\n", at) + 2
        text = text[:end] + self.SUB_BLOCK + text[end:]
        planned["name"] = "r7"
        failures = self._import(nb, "r7", text, recorded_netbox_id=planned["id"])
        assert self._vlan_ids(nb, "GigabitEthernet3.10", "tagged_vlans") == [branch["id"]], \
            failures
        assert core["id"] != branch["id"]

    def test_a_record_still_in_default_is_refused_never_given_either(self):
        """r7 today, before b6: no VLAN group is scoped to Default, so the subinterface gets
        neither VLAN 10, and the refusal names the site."""
        from modules import netbox_client as nc
        nb, _planned, _core, _branch = self._netbox()
        vlan, why = nc._site_vlan(nb, BASE, 1, 10)
        assert vlan is None and why == "no VLAN group is scoped to the device's site (site 1)"
