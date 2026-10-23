"""C676, onboarding from a Planned NetBox record (the operator, 2026-10-11): a name NetBox holds
as Planned is the device's own record, read with its tags, platform, role and config context
(environment-owned lines included); any other status is refused, naming it and where to change
it in NetBox; phase 2 updates that record by its id and never makes a second.

The record is r6's real capture (tests/fixtures/netbox/device_records.json), its status edited
to Planned and given the config context and role kind the cases need.
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


def _r6(status=PLANNED, context=None):
    with open(FIXTURE, encoding="utf-8") as fh:
        dev = copy.deepcopy(json.load(fh)["r6"]["device"])
    dev["status"] = status
    dev["config_context"] = context or {}
    return dev


def _world(kind="router", **kw):
    nb = FakeNetBox()
    dev = _r6(**kw)
    nb.store.setdefault("dcim/devices", []).append(dev)
    nb.seed("dcim/device-roles", {"id": dev["role"]["id"], "name": "Router", "slug": "router",
                                  "custom_fields": {"mercury_kind": kind}})
    nb.seed("dcim/interfaces", {"name": "GigabitEthernet1", "device": {"id": dev["id"]},
                                "mgmt_only": True})
    return nb, dev, (lambda: (True, "", nb, BASE))


class TestTheRecordComesWithTheEnvironment:
    def test_status_site_role_kind_platform_and_tags_are_read(self):
        _nb, dev, ready = _world()
        env = DE.read("r6", ready=ready)
        rec = env.netbox
        assert rec["id"] == dev["id"] and rec["status"] == "planned"
        assert rec["status_label"] == "Planned" and rec["site"] == "Default"
        assert (rec["role"], rec["role_name"], rec["role_kind"]) == ("router", "Router", "router")
        assert (rec["platform"], rec["platform_name"]) == ("ios", "IOS")
        assert rec["tags"] == ["nmas-managed"]
        assert rec["url"] == f"{BASE}/dcim/devices/{dev['id']}/"
        assert list(env.reserved) == ["GigabitEthernet1"]

    def test_the_environment_owned_lines_come_from_its_config_context(self):
        _nb, _dev, ready = _world(context={DE.CONTEXT_KEY: ["username admin privilege 15 "
                                                            "password 0 x"]})
        assert DE.read("r6", ready=ready).injects_user is True

    def test_its_id_is_recorded_for_phase_two(self):
        _nb, dev, ready = _world()
        rec = DE.read("r6", ready=ready).record()
        assert rec["netbox_id"] == dev["id"] and rec["netbox_status"] == "planned"
        assert "username" not in json.dumps(rec), "never the lines themselves"

    def test_a_role_that_cannot_be_read_refuses(self):
        nb, _dev, ready = _world()
        nb.store["dcim/device-roles"] = []
        with pytest.raises(DE.EnvironmentUnreadable) as err:
            DE.read("r6", ready=ready)
        assert "could not be read" in str(err.value)

    def test_a_kind_mercury_does_not_know_reads_as_none(self):
        _nb, _dev, ready = _world(kind="l3-switch")
        assert DE.read("r6", ready=ready).netbox["role_kind"] == ""


# --- the plan --------------------------------------------------------------------------------

from tests.test_onboard_plan import _plan, lab  # noqa: E402,F401  (the plan tests' own fixture)


def _record(**over):
    rec = {"id": 12, "status": "planned", "status_label": "Planned", "site": "Default",
           "role": "router", "role_name": "Router", "role_kind": "router", "platform": "ios",
           "platform_name": "IOS", "tags": ["nmas-managed"],
           "url": f"{BASE}/dcim/devices/12/"}
    rec.update(over)
    return rec


@pytest.fixture
def held(monkeypatch):
    """NetBox holds the name: the name check says so, and the environment read returns the
    record given."""
    monkeypatch.setattr("modules.nsot.onboard._name_in_netbox", lambda hostname: (True, True))

    def give(rec, **env):
        monkeypatch.setattr(DE, "read", lambda hostname, **k: DE.Environment(
            source=f"NetBox device {hostname} (id {rec.get('id')})", netbox=rec, **env))
    return give


class TestAPlannedRecordIsOnboarded:
    def test_a_planned_record_that_agrees_is_onboardable(self, lab, held):
        held(_record(), reserved={"GigabitEthernet1": "mgmt_only"})
        plan = _plan(platform_slug="ios")
        assert plan.onboardable is True, plan.blocking_reasons
        note = plan.summary["netbox_note"]
        assert note.startswith("reads NetBox's Planned record r6 (id 12, site Default, role "
                               "Router, platform ios, tags nmas-managed")
        assert "management-only interfaces GigabitEthernet1" in note
        assert "never its status, role, platform or tags" in note
        assert plan.environment["netbox_id"] == 12

    @pytest.mark.parametrize("status,label", [("active", "Active"), ("offline", "Offline"),
                                              ("staged", "Staged")])
    def test_any_other_status_is_refused_naming_it_and_where_to_change_it(self, lab, held,
                                                                          status, label):
        held(_record(status=status, status_label=label))
        reasons = _plan(platform_slug="ios").blocking_reasons
        hit = [r for r in reasons if "already exists in NetBox" in r]
        assert hit and f"with status {label} (id 12)" in hit[0]
        assert "Set its status to Planned in NetBox" in hit[0]
        assert f"{BASE}/dcim/devices/12/" in hit[0]

    def test_a_platform_that_disagrees_is_refused_naming_both(self, lab, held):
        held(_record(platform="cisco-ios-xe"))
        reasons = _plan(platform_slug="ios").blocking_reasons
        assert any("names platform cisco-ios-xe; the form chose ios" in r for r in reasons)

    def test_a_role_kind_that_disagrees_is_refused_naming_both(self, lab, held):
        held(_record(role_name="Core switch", role_kind="switch"))
        reasons = _plan(platform_slug="ios", role="router").blocking_reasons
        assert any("has role Core switch, a switch; the form chose router" in r for r in reasons)

    def test_a_role_with_no_kind_is_said_and_the_form_s_role_stands(self, lab, held):
        held(_record(role_name="Edge", role_kind=""))
        plan = _plan(platform_slug="ios")
        assert plan.onboardable is True, plan.blocking_reasons
        assert any("NetBox's role Edge has no mercury_kind" in a for a in plan.advisories)

    def test_a_record_with_no_platform_is_said(self, lab, held):
        held(_record(platform="", platform_name=""))
        plan = _plan(platform_slug="ios")
        assert plan.onboardable is True
        assert any("names no platform" in a for a in plan.advisories)

    def test_a_name_held_with_no_record_of_that_name_keeps_the_old_refusal(self, lab, held):
        """The name check finds a device by its address too; the environment read only by
        exact name. Something NetBox holds that is not this name's record is still refused."""
        held({})
        assert "'r6' already exists in NetBox" in _plan(platform_slug="ios").blocking_reasons

    def test_the_route_carries_the_form_s_slug(self):
        from routes.onboard import _plan_args
        args = _plan_args({"hostname": "r6", "platform": "ios"}, "probe", secret="")
        assert args["platform_slug"] == "ios"


class TestCreateKeepsThePlannedId:
    """C1598 (s5's first pass, 2026-10-23: its manifest entry read ``netbox_id: null`` although
    the review read the Planned s5, so every later step found the record by NAME, the path
    C1342 exists to avoid): the plan keeps the Planned record's id, in its summary (so in the
    fingerprint Create is bound to) and in the manifest entry Create commits."""

    def test_the_plan_carries_the_planned_id_and_none_for_another_status(self, lab, held):
        held(_record())
        assert _plan(platform_slug="ios").summary["netbox_id"] == 12
        held(_record(status="active", status_label="Active"))
        assert _plan(platform_slug="ios").summary["netbox_id"] is None
        held({})
        assert _plan(platform_slug="ios").planned_netbox_id is None

    def test_the_id_is_in_what_create_is_bound_to(self, lab, held):
        from modules.nsot.onboard import plan_fingerprint, plan_shown
        held(_record())
        one = plan_fingerprint(plan_shown(_plan(platform_slug="ios")))
        held(_record(id=13, url=f"{BASE}/dcim/devices/13/"))
        assert plan_fingerprint(plan_shown(_plan(platform_slug="ios"))) != one

    def test_create_commits_the_id_on_the_manifest_entry(self, lab, held):
        import json

        from modules.nsot import repo as R
        from modules.nsot.onboard import commit_step
        held(_record())
        sha = commit_step(_plan(platform_slug="ios"), actor="t@example.com")
        head = json.loads(R.git(lab["repo"], "show", f"{sha}:.nsot/manifest.json")[1])
        entry = next(e for e in head["devices"].values() if e.get("name") == "r6")
        assert entry["netbox_id"] == 12


# --- phase 2 ---------------------------------------------------------------------------------

class TestPhaseTwoUpdatesThatRecord:
    @pytest.fixture(autouse=True)
    def _writes_open(self, monkeypatch):
        from modules import netbox_guard
        monkeypatch.setattr(netbox_guard, "assert_writes_allowed", lambda *a, **k: None)

    def _upsert(self, nb, dev, name="r6", **kw):
        from modules import netbox_client as NC
        return NC._upsert_device(nb, BASE, hostname=name, ip="192.0.2.6", facts={},
                                 interfaces=[], site_id=99, role_id=2, ipam_stats={},
                                 netbox_id=dev["id"], **kw)

    def test_the_planned_record_in_another_site_is_updated_and_none_is_made(self):
        nb, dev, _ready = _world()
        out = self._upsert(nb, dev)
        assert out["action"] == "updated"
        assert not [p for p in nb.posts if p[0] == "dcim/devices"], "a second record was made"
        assert [p[1] for p in nb.patches if p[0] == "dcim/devices"] == [dev["id"]]
        written = [k for p in nb.patches if p[0] == "dcim/devices" for k in p[2]]
        assert not {"status", "role", "device_role", "platform", "site"} & set(written)
        assert dev["status"] == PLANNED

    def test_a_record_renamed_since_onboarding_is_refused_naming_both(self):
        nb, dev, _ready = _world()
        dev["name"] = "r6-old"
        with pytest.raises(RuntimeError) as err:
            self._upsert(nb, dev)
        assert f"NetBox record {dev['id']} was r6's at onboarding and is now named 'r6-old'" \
            in str(err.value)
        assert not nb.patches and not [p for p in nb.posts if p[0] == "dcim/devices"]

    def test_a_record_gone_since_onboarding_is_refused(self):
        nb, dev, _ready = _world()
        nb.store["dcim/devices"] = []
        with pytest.raises(RuntimeError) as err:
            self._upsert(nb, dev)
        assert "no longer exists: nothing was written" in str(err.value)

    def test_create_netbox_record_hands_the_recorded_id_to_the_import(self, monkeypatch):
        from modules.nsot import onboard
        monkeypatch.setattr("modules.nsot.manifest.find_by_name",
                            lambda repo, name: ("uid:x", {"mgmt_ip": "192.0.2.6"}))
        monkeypatch.setattr("modules.goldens._load_golden_config_file",
                            lambda ip, list_name: "hostname r6\n")
        monkeypatch.setattr("modules.nsot.hostvars.read_committed", lambda repo, h: {
            "bootstrap": {"environment": {"netbox_id": 12, "netbox_status": "planned"}}})
        seen = []
        onboard.create_netbox_record("/nowhere", "r6", "probe",
                                     sync=lambda l, devs, **k: seen.extend(devs) or {})
        assert seen and seen[0]["netbox_id"] == 12

    def test_the_planned_record_becomes_active_and_is_read_back(self, monkeypatch):
        """C1421: Verify took the Planned record over and left it Planned (the sync never writes
        status); onboarding now sets it Active through the write gate and reads it back."""
        from modules.nsot import onboard
        nb, dev, ready = _world()
        monkeypatch.setattr("modules.netbox_client._nb_ready", ready)
        got = onboard.activate_planned("probe", "r6", dev["id"], actor="op@example.com",
                                       authority="test")
        assert got == {"state": "activated", "id": dev["id"], "before": "planned", "error": ""}
        assert [p[2] for p in nb.patches if p[0] == "dcim/devices"] == [{"status": "active"}]

    def test_a_record_that_is_not_planned_is_left_as_it_is(self, monkeypatch):
        from modules.nsot import onboard
        nb, dev, ready = _world(status={"label": "Active", "value": "active"})
        monkeypatch.setattr("modules.netbox_client._nb_ready", ready)
        got = onboard.activate_planned("probe", "r6", dev["id"])
        assert got["state"] == "not_planned" and got["before"] == "active"
        assert not nb.patches

    def test_onboarding_activates_the_record_it_took_over(self, monkeypatch):
        from modules.nsot import onboard
        nb, dev, ready = _world()
        monkeypatch.setattr("modules.netbox_client._nb_ready", ready)
        monkeypatch.setattr("modules.nsot.manifest.find_by_name",
                            lambda repo, name: ("uid:x", {"mgmt_ip": "192.0.2.6"}))
        monkeypatch.setattr("modules.goldens._load_golden_config_file",
                            lambda ip, list_name: "hostname r6\n")
        monkeypatch.setattr("modules.nsot.hostvars.read_committed", lambda repo, h: {
            "bootstrap": {"environment": {"netbox_id": dev["id"], "netbox_status": "planned"}}})
        monkeypatch.setattr("modules.netbox_guard.get_created", lambda *a, **k: {})
        out = onboard.create_netbox_record("/nowhere", "r6", "probe",
                                           sync=lambda l, devs, **k: {"ok": True})
        assert out["ok"] and out["activated"]["state"] == "activated", out
        assert out["device_id"] == dev["id"] and not out["write_failures"]
        assert [p[2] for p in nb.patches if p[0] == "dcim/devices"] == [{"status": "active"}]

    def test_a_record_that_could_not_be_activated_is_said(self, monkeypatch):
        from modules.nsot import onboard
        monkeypatch.setattr("modules.netbox_client._nb_ready",
                            lambda: (False, "NetBox URL and API token are not configured", None,
                                     ""))
        monkeypatch.setattr("modules.nsot.manifest.find_by_name",
                            lambda repo, name: ("uid:x", {"mgmt_ip": "192.0.2.6"}))
        monkeypatch.setattr("modules.goldens._load_golden_config_file",
                            lambda ip, list_name: "hostname r6\n")
        monkeypatch.setattr("modules.nsot.hostvars.read_committed", lambda repo, h: {
            "bootstrap": {"environment": {"netbox_id": 12, "netbox_status": "planned"}}})
        monkeypatch.setattr("modules.netbox_guard.get_created", lambda *a, **k: {})
        out = onboard.create_netbox_record("/nowhere", "r6", "probe",
                                           sync=lambda l, devs, **k: {"ok": True})
        assert out["ok"], "the record exists: the step did its work"
        assert "status Planned to Active (NetBox is not reachable" in out["reason"]

    def test_a_device_with_no_recorded_record_is_imported_as_before(self, monkeypatch):
        from modules.nsot import onboard
        monkeypatch.setattr("modules.nsot.manifest.find_by_name",
                            lambda repo, name: ("uid:x", {"mgmt_ip": "192.0.2.6"}))
        monkeypatch.setattr("modules.goldens._load_golden_config_file",
                            lambda ip, list_name: "hostname r6\n")
        monkeypatch.setattr("modules.nsot.hostvars.read_committed", lambda repo, h: {
            "bootstrap": {"environment": {"netbox_id": None}}})
        seen = []
        onboard.create_netbox_record("/nowhere", "r6", "probe",
                                     sync=lambda l, devs, **k: seen.extend(devs) or {})
        assert seen and "netbox_id" not in seen[0]
