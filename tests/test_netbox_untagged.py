"""Register C59: a create that cannot be tagged is refused, and what the old
behaviour left behind can be found.

Remove acts only on objects TAGGED `nmas-managed` AND in NMAS's record. A
create whose tag could not be ensured went ahead untagged, silently, because
the create succeeded, and a failed tag lookup was cached for the life of the
process: one transient error, and every later create untagged until a
restart. An object NMAS made and can never clean up is a leak in the safety
mechanism, not in a report (the operator's reading).
"""

import importlib.machinery
import importlib.util
import os

import pytest

from modules import netbox_client as nc
from modules import netbox_guard
from tests.fake_netbox import FakeNetBox, FakeResponse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _script():
    path = os.path.join(ROOT, "scripts", "nmas-netbox-untagged")
    loader = importlib.machinery.SourceFileLoader("nmas_netbox_untagged", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


class TagRefusing(FakeNetBox):
    """Refuses to create the managed tag for the first `refusals` attempts."""

    def __init__(self, refusals=10**6):
        super().__init__()
        self.refusals = refusals

    def post(self, url, json=None, timeout=None):
        endpoint, _ = self._parse(url)
        if endpoint == "extras/tags" and self.refusals > 0:
            self.refusals -= 1
            return FakeResponse({"detail": "no permission for tags"}, 403)
        return super().post(url, json=json, timeout=timeout)


@pytest.fixture(autouse=True)
def writes_on(monkeypatch):
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
    monkeypatch.setattr(nc, "_managed_tag_ids", {})
    nc._drain_write_failures()
    yield
    nc._drain_write_failures()


class TestACreateThatCannotBeTaggedIsRefused:
    def test_it_is_refused_and_recorded(self):
        nb = TagRefusing()
        with netbox_guard.for_list("Lab"):
            with pytest.raises(RuntimeError, match="untagged"):
                nc._nb_post(nb, "http://nb.invalid", "ipam/vlans/", {"vid": 10, "name": "x"})
        assert not [p for p in nb.posts if p[0] == "ipam/vlans"], "nothing was created"

    def test_inside_an_upsert_it_is_a_counted_write_failure(self):
        nb = TagRefusing()
        site = nb.seed("dcim/sites", {"name": "Lab", "slug": "lab"})
        with netbox_guard.for_list("Lab"), nc._attributed_to("r1"):
            with pytest.raises(RuntimeError):
                nc._upsert_device(nb, "http://nb.invalid", hostname="r1", ip="203.0.113.1",
                                  facts={"manufacturer": "Cisco", "model": "C8000v",
                                         "platform": "IOS-XE", "serial": "S1", "sw_version": "17"},
                                  interfaces=[], site_id=site["id"], role_id=1, ipam_stats={},
                                  vlans=[{"vlan_id": 10, "name": "ten"}])
        failures = nc._drain_write_failures()
        assert any("untagged" in f["error"] for f in failures), failures

    def test_a_failure_is_not_cached(self):
        """One refusal, then the tag can be made: the next create is tagged.
        A cached failure left every later create untagged until a restart."""
        nb = TagRefusing(refusals=1)
        with netbox_guard.for_list("Lab"):
            with pytest.raises(RuntimeError):
                nc._nb_post(nb, "http://nb.invalid", "ipam/vlans/", {"vid": 10, "name": "a"})
            obj = nc._nb_post(nb, "http://nb.invalid", "ipam/vlans/", {"vid": 20, "name": "b"})
        assert netbox_guard.has_managed_tag(obj)


class Unreadable(FakeNetBox):
    def __init__(self, unreadable=()):
        super().__init__()
        self.unreadable = set(unreadable)

    def get(self, url, params=None, timeout=None):
        endpoint, obj_id = self._parse(url)
        if (endpoint, obj_id) in self.unreadable:
            return FakeResponse({"detail": "server error"}, 500)
        return super().get(url, params=params, timeout=timeout)


def _world(unreadable=()):
    nb = Unreadable(unreadable)
    tag = {"id": 900, "slug": netbox_guard.MANAGED_TAG_SLUG, "name": netbox_guard.MANAGED_TAG}
    dev = nb.seed("dcim/devices", {"name": "r1", "tags": [tag]})
    lost = nb.seed("ipam/vlans", {"name": "lost", "tags": []})
    stray = nb.seed("ipam/vlans", {"name": "stray", "tags": []})
    for oid, otype, user in ((dev["id"], "dcim.device", 7), (lost["id"], "ipam.vlan", 7),
                             (stray["id"], "ipam.vlan", 7), (4242, "ipam.vlan", 9)):
        nb.seed("core/object-changes", {"action": "create", "changed_object_type": otype,
                                        "changed_object_id": oid,
                                        "user": {"id": user, "username": f"u{user}"}})
    created = {"lab": {"dcim/devices": [{"id": dev["id"], "name": "r1"}],
                       "ipam/vlans": [{"id": lost["id"], "name": "lost"}],
                       "ipam/prefixes": [{"id": 777, "name": "gone"}],
                       "extras/tags": [{"id": 900, "name": "nmas-managed"}]}}
    return nb, created, lost, stray


class TestTheReconciliation:
    def test_it_finds_both_kinds_and_counts_the_rest(self):
        mod = _script()
        nb, created, lost, stray = _world()
        r = mod.reconcile(nb, "http://nb.invalid", created)
        assert [u["id"] for u in r["untagged"]] == [lost["id"]]
        assert r["tagged"] == 1 and r["gone"] == 1 and r["not_taggable"] == 1
        assert r["account"]["id"] == 7, "read from a recorded object's own create"
        assert [(u["id"], u["state"]) for u in r["unrecorded"]] == [(stray["id"], "untagged")]
        assert mod.verdict(r) == 1

    def test_another_account_s_creates_are_not_listed(self):
        mod = _script()
        nb, created, _lost, _stray = _world()
        r = mod.reconcile(nb, "http://nb.invalid", created)
        assert 4242 not in [u["id"] for u in r["unrecorded"]]

    def test_an_unreadable_object_is_unproven_never_gone(self):
        mod = _script()
        nb, created, lost, _stray = _world(unreadable={("ipam/vlans", 2)})
        r = mod.reconcile(nb, "http://nb.invalid", created)
        assert [u["id"] for u in r["unreadable"]] == [2]
        assert mod.verdict(r) == 2

    def test_no_changelog_is_unproven(self):
        """A check that could not read the changelog did not pass."""
        mod = _script()
        nb, created, _lost, _stray = _world()
        nb.store.pop("core/object-changes")
        r = mod.reconcile(nb, "http://nb.invalid", created)
        assert not r["changelog"].startswith("read")
        assert mod.verdict(r) == 2

    def test_both_names_and_a_mismatch_is_its_own_finding(self, capsys, monkeypatch):
        """C131: the record said "R1" at dcim/devices/7 and NetBox held r3. A
        report printing only the record's name could not show it, and a
        decision to tag r3 was made from that list."""
        mod = _script()
        nb, created, lost, _stray = _world()
        wrong = nb.seed("dcim/devices", {"name": "r3", "tags": []})
        created["lab"]["dcim/devices"].append({"id": wrong["id"], "name": "R1"})
        r = mod.reconcile(nb, "http://nb.invalid", created)
        assert [(m["record"], m["netbox"]) for m in r["mismatched"]] == [("R1", "r3")]
        assert mod.verdict(r) == 1
        # The floor: an entry whose object IS the one it names is no mismatch.
        assert not any(m["id"] == lost["id"] for m in r["mismatched"])
        monkeypatch.setattr(mod, "reconcile", lambda *a: r)
        monkeypatch.setattr("modules.netbox_client._nb_ready", lambda: (True, "", nb, "http://nb"))
        mod.main(["--list", "lab"])
        out = capsys.readouterr().out
        assert f"MISMATCH: lab dcim/devices/{wrong['id']} -- the record says 'R1', NetBox holds 'r3'" in out
        assert "do not tag it" in out
        assert f"the record says 'lost', NetBox holds 'lost'" in out

    def test_a_mismatched_entry_never_identifies_the_account(self):
        """A record entry pointing at someone else's object would name THEIR
        account as NMAS's."""
        mod = _script()
        nb, created, lost, stray = _world()
        other = nb.seed("dcim/devices", {"name": "r3", "tags": []})
        nb.seed("core/object-changes", {"action": "create", "changed_object_type": "dcim.device",
                                        "changed_object_id": other["id"],
                                        "user": {"id": 42, "username": "a-person"}})
        # First in the record, so it would be sampled first.
        created = {"aaa": {"dcim/devices": [{"id": other["id"], "name": "R1"}]}, **created}
        r = mod.reconcile(nb, "http://nb.invalid", created)
        assert r["account"]["id"] == 7, "identified from a mismatched entry's creator"

    def test_clean_is_zero(self):
        mod = _script()
        nb, created, lost, stray = _world()
        for obj in nb.store["ipam/vlans"]:
            obj["tags"] = [{"slug": netbox_guard.MANAGED_TAG_SLUG}]
        created["lab"]["ipam/vlans"].append({"id": stray["id"], "name": "stray"})
        r = mod.reconcile(nb, "http://nb.invalid", created)
        assert (r["untagged"], r["unrecorded"]) == ([], []) and mod.verdict(r) == 0

    def test_object_types_for_the_removal_endpoints(self):
        mod = _script()
        assert mod.object_type("ipam/ip-addresses") == "ipam.ipaddress"
        assert mod.object_type("ipam/prefixes") == "ipam.prefix"
        assert mod.object_type("dcim/devices") == "dcim.device"
        assert mod.object_type("dcim/regions") == "dcim.region"
        assert mod.object_type("dcim/device-roles") == "dcim.devicerole"
