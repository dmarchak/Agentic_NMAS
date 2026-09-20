"""Preview fidelity and tag scope.

Two guarantees an operator relies on when they approve an import:

1. **The preview count is the executed count.** If the modal says "7 devices,
   24 interfaces", executing must create exactly that — including dependent
   objects under a device that does not exist yet, which the dry run addresses
   through placeholder ids.
2. **Only created objects are tagged.** ``nmas-managed`` marks what NMAS made,
   because removal keys off it. Tagging an object NMAS merely *updated* would
   make a pre-existing, operator-owned record eligible for deletion.

Everything runs against tests/fake_netbox.py — no network.
"""

import pytest

from fake_netbox import FakeNetBox
from modules import netbox_guard
from modules.netbox_client import _upsert_device
from modules.netbox_guard import MANAGED_TAG_SLUG, PLAN_EXCLUDED_ENDPOINTS

def _facts(n=1):
    """Device facts. Serials are distinct per device.

    _upsert_device matches an existing device by serial before falling back to
    name+site, so sharing a serial across devices would collapse them into one —
    correctly, but it would not exercise what these tests are checking.
    """
    return {"manufacturer": "Cisco", "model": "C8000v", "platform": "IOS-XE",
            "serial": f"SER{n:04d}", "sw_version": "17.6"}


FACTS = _facts(1)


@pytest.fixture(autouse=True)
def allow_writes(monkeypatch):
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)


@pytest.fixture(autouse=True)
def fresh_tag_cache(monkeypatch):
    """The managed-tag id is cached per NetBox base URL.

    Every test builds a new FakeNetBox behind the same URL, so a cached id from
    a previous test would point at an object this one does not have.
    """
    import modules.netbox_client as nbc
    monkeypatch.setattr(nbc, "_managed_tag_ids", {})


def _interfaces(n):
    return [{"name": f"GigabitEthernet{n}", "ip": f"203.0.113.{n}",
             "prefix_len": 24, "enabled": True}]


def _seeded():
    nb = FakeNetBox()
    site = nb.seed("dcim/sites", {"name": "Lab", "slug": "lab"})
    role = nb.seed("dcim/device-roles", {"name": "Router", "slug": "router"})
    return nb, site["id"], role["id"]


def _import(hosts, dry):
    """Import *hosts*, returning created-counts by endpoint."""
    nb, site_id, role_id = _seeded()
    stats = {}

    def go():
        for i, host in enumerate(hosts, start=1):
            _upsert_device(nb, "http://nb.invalid", hostname=host,
                           ip=f"203.0.113.{i}", facts=_facts(i),
                           interfaces=_interfaces(i), site_id=site_id,
                           role_id=role_id, ipam_stats=stats)

    if dry:
        with netbox_guard.dry_run() as plan, netbox_guard.for_list("Lab"):
            go()
        counts = {k.strip("/"): v for k, v in plan.summary()["creates_by_type"].items()}
        return counts, nb
    with netbox_guard.for_list("Lab"):
        go()
    counts = {k: v for k, v in nb.created_counts().items()
              if k not in PLAN_EXCLUDED_ENDPOINTS}
    return counts, nb


class TestPreviewMatchesExecution:
    @pytest.mark.parametrize("device_count", [1, 3, 5])
    def test_preview_counts_equal_executed_counts(self, device_count):
        hosts = [f"R{i}" for i in range(1, device_count + 1)]
        preview, _ = _import(hosts, dry=True)
        executed, _ = _import(hosts, dry=False)
        assert preview == executed

    def test_dependent_objects_counted_under_uncreated_device(self):
        """Interfaces and IPs hang off a device that does not exist yet."""
        preview, _ = _import(["R1"], dry=True)
        assert preview["dcim/devices"] == 1
        assert preview["dcim/interfaces"] == 1
        assert preview["ipam/ip-addresses"] == 1

    def test_shared_objects_counted_once_not_once_per_device(self):
        """Regression: the dry run used to plan one manufacturer per device.

        Get-or-create could not see what the dry run had already "created", so a
        three-device import previewed three manufacturers and created one.
        """
        preview, _ = _import(["R1", "R2", "R3"], dry=True)
        assert preview["dcim/manufacturers"] == 1
        assert preview["dcim/platforms"] == 1
        assert preview["dcim/device-types"] == 1
        assert preview["dcim/devices"] == 3

    def test_dry_run_writes_nothing(self):
        _, nb = _import(["R1", "R2"], dry=True)
        assert nb.posts == []
        assert nb.patches == []
        assert nb.deletes == []

    def test_second_import_plans_no_creates(self):
        """Importing an unchanged list again should plan nothing new."""
        nb, site_id, role_id = _seeded()
        stats = {}

        def go():
            _upsert_device(nb, "http://nb.invalid", hostname="R1", ip="203.0.113.1",
                           facts=FACTS, interfaces=_interfaces(1), site_id=site_id,
                           role_id=role_id, ipam_stats=stats)

        with netbox_guard.for_list("Lab"):
            go()
        with netbox_guard.dry_run() as plan, netbox_guard.for_list("Lab"):
            go()
        assert plan.summary()["create_count"] == 0


class TestTagScope:
    def _tag_slugs(self, obj):
        return {t.get("slug") for t in (obj.get("tags") or []) if isinstance(t, dict)}

    def test_created_objects_are_tagged(self):
        _, nb = _import(["R1"], dry=False)
        device = nb.objects("dcim/devices")[0]
        assert MANAGED_TAG_SLUG in self._tag_slugs(device)

    def test_preexisting_object_is_not_tagged_when_updated(self):
        """The core guarantee: an operator's own device stays untagged."""
        nb, site_id, role_id = _seeded()
        existing = nb.seed("dcim/devices", {
            "name": "R1", "site": site_id, "role": role_id, "tags": [],
        })
        assert self._tag_slugs(existing) == set()

        with netbox_guard.for_list("Lab"):
            _upsert_device(nb, "http://nb.invalid", hostname="R1", ip="203.0.113.1",
                           facts=FACTS, interfaces=_interfaces(1), site_id=site_id,
                           role_id=role_id, ipam_stats={})

        after = [d for d in nb.objects("dcim/devices") if d["name"] == "R1"][0]
        assert MANAGED_TAG_SLUG not in self._tag_slugs(after), (
            "an operator-owned device was tagged nmas-managed on update, which "
            "would make it eligible for deletion by Remove"
        )

    def test_no_patch_carries_the_managed_tag(self):
        """Structural check: no PATCH payload may ever add the tag."""
        nb, site_id, role_id = _seeded()
        nb.seed("dcim/devices", {"name": "R1", "site": site_id, "role": role_id})
        nb.seed("dcim/sites", {"name": "Other", "slug": "other"})

        with netbox_guard.for_list("Lab"):
            _upsert_device(nb, "http://nb.invalid", hostname="R1", ip="203.0.113.1",
                           facts=FACTS, interfaces=_interfaces(1), site_id=site_id,
                           role_id=role_id, ipam_stats={})

        tag_ids = {t["id"] for t in nb.objects("extras/tags")
                   if t.get("slug") == MANAGED_TAG_SLUG}
        for endpoint, obj_id, payload in nb.patches:
            assert not (set(payload.get("tags") or []) & tag_ids), (
                f"PATCH to {endpoint}/{obj_id} added the managed tag"
            )

    def test_tag_endpoint_excluded_from_plans(self):
        """NMAS's own tag object is bookkeeping, not previewable inventory."""
        assert "extras/tags" in PLAN_EXCLUDED_ENDPOINTS
        preview, _ = _import(["R1"], dry=True)
        assert "extras/tags" not in preview
