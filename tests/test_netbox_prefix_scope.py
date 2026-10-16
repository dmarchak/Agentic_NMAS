"""C1010: a prefix Mercury writes to NetBox carries the network's site, read back from NetBox.

`_ensure_prefix` sent `site` on create. NetBox 4.2 replaced a prefix's `site` with the generic
scope (`scope_type`, `scope_id`; 4.2.0's release notes, "Breaking Changes"), and 4.6.9's
PrefixSerializer has no `site`, so NetBox ignored the field and answered 201: measured on the
host 2026-10-16, all 3 prefixes Mercury created carry no site. The tests that passed sent the
field and never read the prefix back.

So these tests READ EACH PREFIX BACK from `FakeNetBox`, which models 4.2+ deliberately
(`fake_netbox.REMOVED_FIELDS`, `SCOPED_ENDPOINTS`): a `site` key on a prefix is dropped, and a
scope is stored and returned with its nested `scope`. Sending `site` again fails them by
assertion, because the prefix comes back with no scope. Built from r3's REAL config through the
importer's own parsers (the shape of `test_import_skips_are_named.py`).
"""

import os

import pytest

from modules import netbox_client as nc
from modules import netbox_guard
from tests.fake_netbox import FakeNetBox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R3 = open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r3.cfg"), encoding="utf-8").read()
LIST = "Lab"
AUTH = "test: declared by the test (C155)"
#: r3's GigabitEthernet3's prefix (no VRF): the prefix the backfill cases hold before the sync.
HELD = next(i["prefix"] for i in nc._parse_all_interfaces_from_config(R3)
            if i["name"] == "GigabitEthernet3")
#: r3's one static route in the global table that the import models as a prefix (not a /0).
STATIC = next(r["prefix"] for r in nc._parse_static_routes_from_config(R3)
              if not r.get("vrf") and not r["prefix"].endswith("/0"))


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


def _box():
    nb = FakeNetBox()
    site = nb.seed("dcim/sites", {"name": LIST, "slug": "lab"})
    other = nb.seed("dcim/sites", {"name": "Elsewhere", "slug": "elsewhere"})
    role = nb.seed("dcim/device-roles", {"name": "Router", "slug": "router"})
    return nb, site, other, role


def _upsert(nb, site, role):
    with netbox_guard.for_list(LIST, authority=AUTH), nc._attributed_to("r3"):
        nc._upsert_device(
            nb, "http://nb.invalid", hostname="r3", ip="203.0.113.3",
            facts={"manufacturer": "Cisco", "model": "C8000v", "platform": "IOS-XE",
                   "serial": "SER0003", "sw_version": "17.6"},
            interfaces=nc._parse_all_interfaces_from_config(R3),
            vrfs=nc._parse_vrfs_from_config(R3),
            static_routes=nc._parse_static_routes_from_config(R3),
            site_id=site["id"], role_id=role["id"], ipam_stats={"skipped": []})
    return nc._drain_write_failures()


def _read_back(nb, prefix):
    """The prefix as NetBox answers a GET: by the list filter, then by its own id."""
    hits = nb.get("http://nb.invalid/api/ipam/prefixes/", params={"prefix": prefix}).json()
    assert hits["count"] == 1, (prefix, hits)
    return nb.get(f"http://nb.invalid/api/ipam/prefixes/{hits['results'][0]['id']}/").json()


def _seed_prefix(nb, *, tagged=False, scope=None):
    obj = {"prefix": HELD, "status": {"value": "active", "label": "Active"},
           "description": "", "vrf": None,
           "tags": [{"id": 900, "slug": "nmas-managed", "name": "nmas-managed"}] if tagged else []}
    if scope:
        obj["scope_type"], obj["scope_id"] = scope
    return nb.seed("ipam/prefixes", obj)


class TestTheFakeModelsNetBox42:
    """The model itself, so a test built on it cannot pass for the old reason."""

    def test_a_site_key_on_a_prefix_is_dropped_and_the_create_still_succeeds(self):
        nb, site, _o, _r = _box()
        r = nb.post("http://nb.invalid/api/ipam/prefixes/",
                    json={"prefix": "192.0.2.0/24", "site": site["id"]})
        assert r.status_code == 201
        held = nb.get(f"http://nb.invalid/api/ipam/prefixes/{r.json()['id']}/").json()
        assert "site" not in held
        assert (held["scope_type"], held["scope_id"], held["scope"]) == (None, None, None)
        assert nb.posts[-1][1]["site"] == site["id"], "what was SENT is kept for assertions"

    def test_a_scope_is_stored_and_returned_nested(self):
        nb, site, _o, _r = _box()
        r = nb.post("http://nb.invalid/api/ipam/prefixes/",
                    json={"prefix": "192.0.2.0/24", "scope_type": "dcim.site",
                          "scope_id": site["id"]})
        held = nb.get(f"http://nb.invalid/api/ipam/prefixes/{r.json()['id']}/").json()
        assert (held["scope_type"], held["scope_id"]) == ("dcim.site", site["id"])
        assert (held["scope"]["id"], held["scope"]["name"]) == (site["id"], LIST)


class TestEveryPrefixTheImportCreatesHasTheNetworksSite:
    def test_each_prefix_read_back_is_scoped_to_the_site(self):
        nb, site, _o, role = _box()
        failures = _upsert(nb, site, role)
        prefixes = [p["prefix"] for p in nb.objects("ipam/prefixes")]
        # The floor: r3's four interface prefixes in the global table, its loopback among them,
        # and its one static route (both create paths).
        assert len(prefixes) >= 5 and HELD in prefixes and STATIC in prefixes, prefixes
        for prefix in prefixes:
            held = _read_back(nb, prefix)
            assert (held["scope_type"], held["scope_id"]) == ("dcim.site", site["id"]), held
            assert held["scope"]["name"] == LIST
            assert "site" not in held
        assert failures == [], failures

    def test_no_prefix_write_sends_site(self):
        nb, site, _o, role = _box()
        _upsert(nb, site, role)
        sent = [p for ep, p in nb.posts if ep == "ipam/prefixes"]
        assert sent and not [p for p in sent if "site" in p], sent


class TestTheBackfill:
    """A prefix Mercury created with no scope gets the site; any other is left alone."""

    @pytest.mark.parametrize("how", ["tagged", "recorded"])
    def test_mercurys_prefix_without_a_scope_is_given_the_site_with_its_before(self, how):
        nb, site, _o, role = _box()
        held = _seed_prefix(nb, tagged=(how == "tagged"))
        if how == "recorded":
            netbox_guard.record_created(LIST, "ipam/prefixes", held["id"], HELD)
        failures = _upsert(nb, site, role)
        back = _read_back(nb, HELD)
        assert back["id"] == held["id"], "the held prefix is updated, never duplicated"
        assert (back["scope_type"], back["scope_id"]) == ("dcim.site", site["id"])
        patches = [p for ep, oid, p in nb.patches if ep == "ipam/prefixes" and oid == held["id"]]
        assert patches and {"scope_type", "scope_id"} <= set(patches[0]), patches
        mod = netbox_guard.get_modified(LIST, "ipam/prefixes")["ipam/prefixes"]
        entry = [e for e in mod if e["id"] == held["id"]]
        assert entry, mod
        assert entry[0]["fields"]["scope_type"] == {"before": None, "after": "dcim.site"}
        assert entry[0]["fields"]["scope_id"] == {"before": None, "after": site["id"]}
        assert failures == [], failures

    def test_a_prefix_mercury_did_not_create_is_left_alone(self):
        nb, site, _o, role = _box()
        held = _seed_prefix(nb)
        _upsert(nb, site, role)
        back = _read_back(nb, HELD)
        assert (back["scope_type"], back["scope_id"]) == (None, None)
        assert not [1 for ep, oid, _p in nb.patches
                    if ep == "ipam/prefixes" and oid == held["id"]], nb.patches
        assert not netbox_guard.get_modified(LIST, "ipam/prefixes")["ipam/prefixes"]

    def test_mercurys_prefix_scoped_elsewhere_is_left_alone(self):
        nb, site, other, role = _box()
        held = _seed_prefix(nb, tagged=True, scope=("dcim.site", other["id"]))
        _upsert(nb, site, role)
        back = _read_back(nb, HELD)
        assert (back["scope_type"], back["scope_id"]) == ("dcim.site", other["id"])
        assert not [1 for ep, oid, _p in nb.patches
                    if ep == "ipam/prefixes" and oid == held["id"]], nb.patches

    def test_the_static_route_path_backfills_by_the_same_rule(self):
        nb, site, _o, role = _box()
        held = nb.seed("ipam/prefixes", {
            "prefix": STATIC, "vrf": None, "description": "",
            "tags": [{"id": 900, "slug": "nmas-managed", "name": "nmas-managed"}]})
        _upsert(nb, site, role)
        back = _read_back(nb, STATIC)
        assert back["id"] == held["id"]
        assert (back["scope_type"], back["scope_id"]) == ("dcim.site", site["id"])

    def test_the_preview_shows_it_as_an_update_and_writes_nothing(self):
        from modules.preview_confirm import netbox_import_preview

        nb, site, _o, role = _box()
        held = _seed_prefix(nb, tagged=True)
        with netbox_guard.dry_run() as plan:
            _upsert(nb, site, role)
        assert not nb.patches and not nb.posts, "a preview writes nothing"
        ups = [u for u in plan.summary()["updates"]
               if u["endpoint"] == "ipam/prefixes" and u["id"] == held["id"]]
        assert ups and set(ups[0]["changed"]) == {"scope_type", "scope_id"}, ups
        p = netbox_import_preview({"list": LIST, "device_count": 1, "plan": plan.summary(),
                                   "writes_allowed": True, "plan_hash": "ab"},
                                  {"may": True, "statement": "You are confirming as p."})
        lines = p["targets"][0]["program"]["lines"]
        assert f"update ipam/prefixes #{held['id']} {HELD}: changes scope_id, scope_type" \
            in lines, lines


class TestAScopeNetBoxDidNotStoreIsAWriteFailure:
    """In production too: NetBox answers a write with the object as saved, and a scope missing
    from it is named, both operands, instead of passing as C1010's `site` did."""

    def test_a_netbox_that_drops_the_scope_is_named(self, monkeypatch):
        from tests import fake_netbox

        monkeypatch.setitem(fake_netbox.REMOVED_FIELDS, "ipam/prefixes",
                            ("site", "scope_type", "scope_id"))
        nb, site, _o, role = _box()
        failures = _upsert(nb, site, role)
        named = [f for f in failures if f["write"] == f"site of prefix {HELD}"]
        assert named, failures
        assert (f"sent scope_type=dcim.site, scope_id={site['id']}" in named[0]["error"]
                and "stored scope_type=None, scope_id=None" in named[0]["error"]), named
