"""What the NetBox import deliberately does not model is counted and NAMED
(the operator, 2026-09-28: "5 fewer writes" must be explained, never silent).

(b)'s re-import failed eight writes, five of them `ipam/prefixes 0.0.0.0/0`
refused as "Cannot create prefix with /0 mask". Measured on the fleet
configs: every one of those is `ip route vrf clab-mgmt 0.0.0.0 0.0.0.0`, the
emulator's own default route in the EXCLUDED VRF. The import skipped that
VRF's addresses and still imported its routes, two readers of one rule. Now
a route in an excluded VRF is skipped under that rule, a /0 anywhere else is
skipped because a default route is a route and not address space, and both
reach the preview and the stored result by name. The excluded addresses,
"counted, never silent" since the rule was written, were counted into
`ipam_stats` and carried into nothing a person reads; they are named now too.

Built from r3's REAL config through the importer's own parsers.
"""

import os

import pytest

from modules import netbox_client as nc
from modules import netbox_guard
from tests.fake_netbox import FakeNetBox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R3 = open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r3.cfg")).read()
# The same real line with its VRF removed: a default route in the global
# table, which the fleet does not have today (the pieces are real, the
# arrangement is moved).
GLOBAL_DEFAULT = next(l for l in R3.splitlines()
                      if l.startswith("ip route vrf clab-mgmt 0.0.0.0")).replace(
                          "vrf clab-mgmt ", "")


@pytest.fixture(autouse=True)
def writes_on(monkeypatch):
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
    monkeypatch.setattr(nc, "_managed_tag_ids", {})
    monkeypatch.setattr(nc, "excluded_vrfs", lambda: {"clab-mgmt"})
    nc._drain_write_failures()
    yield
    nc._drain_write_failures()


def _upsert(config):
    nb = FakeNetBox()
    site = nb.seed("dcim/sites", {"name": "Lab", "slug": "lab"})
    role = nb.seed("dcim/device-roles", {"name": "Router", "slug": "router"})
    stats = {"skipped": []}
    with netbox_guard.for_list("Lab", authority="test: declared by the test (C155)"), nc._attributed_to("r3"):
        nc._upsert_device(
            nb, "http://nb.invalid", hostname="r3", ip="203.0.113.3",
            facts={"manufacturer": "Cisco", "model": "C8000v", "platform": "IOS-XE",
                   "serial": "SER0003", "sw_version": "17.6"},
            interfaces=nc._parse_all_interfaces_from_config(config),
            vrfs=nc._parse_vrfs_from_config(config),
            static_routes=nc._parse_static_routes_from_config(config),
            site_id=site["id"], role_id=role["id"], ipam_stats=stats)
    prefixes = [p["prefix"] for p in nb.store.get("ipam/prefixes", [])]
    return nb, stats, prefixes, nc._drain_write_failures()


def test_the_fixture_can_exhibit_the_case():
    routes = nc._parse_static_routes_from_config(R3)
    assert {"prefix": "0.0.0.0/0", "vrf": "clab-mgmt"}.items() <= routes[1].items()
    assert any(r["prefix"] == "10.0.0.0/8" and not r["vrf"] for r in routes)


class TestTheImport:
    def test_the_excluded_vrf_s_default_route_is_skipped_and_named(self):
        _nb, stats, prefixes, failures = _upsert(R3)
        assert "0.0.0.0/0" not in prefixes
        assert "10.0.0.0/8" in prefixes, "the global static route is still imported"
        assert failures == []
        report = nc.skipped_report(stats["skipped"])
        routes = [g for g in report if g["what"] == "static routes in VRF clab-mgmt"]
        assert routes and routes[0]["devices"] == ["r3"] and routes[0]["count"] == 1
        assert "excluded" in routes[0]["why"]

    def test_the_excluded_vrf_s_addresses_are_named_not_only_counted(self):
        _nb, stats, _p, _f = _upsert(R3)
        addrs = [g for g in nc.skipped_report(stats["skipped"])
                 if g["what"] == "addresses in VRF clab-mgmt"]
        assert addrs and addrs[0]["devices"] == ["r3"] and addrs[0]["count"] >= 1
        assert stats.get("ips_excluded") == addrs[0]["count"]

    def test_a_default_route_outside_an_excluded_vrf_is_skipped_as_a_route(self):
        _nb, stats, prefixes, failures = _upsert(R3 + "\n" + GLOBAL_DEFAULT + "\n")
        assert "0.0.0.0/0" not in prefixes and failures == []
        g = [g for g in nc.skipped_report(stats["skipped"])
             if g["what"] == "static route 0.0.0.0/0 as a prefix"]
        assert g and g[0]["why"] == nc.DEFAULT_ROUTE_SKIP

    def test_skips_merge_across_devices_and_lists(self):
        a = nc.skipped_report([{"what": "w", "why": "y", "device": "r1", "count": 2},
                               {"what": "w", "why": "y", "device": "r2", "count": 1}])
        b = nc.skipped_report([{"what": "w", "why": "y", "device": "r2", "count": 3}])
        assert a == [{"what": "w", "why": "y", "devices": ["r1", "r2"], "count": 3}]
        assert nc.merge_skipped([a, b]) == [
            {"what": "w", "why": "y", "devices": ["r1", "r2"], "count": 6}]


class TestTheySayWhy:
    GROUPS = [{"what": "static routes in VRF clab-mgmt", "why": "the VRF is excluded",
               "devices": ["r1", "r2"], "count": 2}]

    def test_the_preview_names_each_skip(self):
        from modules.preview_confirm import netbox_import_preview

        p = netbox_import_preview({"list": "Default", "device_count": 9, "plan": {},
                                   "skipped": self.GROUPS},
                                  {"may": True, "kind": "person",
                                   "statement": "You are confirming as p."})
        texts = [w["text"] for w in p["what_not"]["items"]]
        assert any("Not imported, on purpose: static routes in VRF clab-mgmt on r1, r2 (2)"
                   in t for t in texts), texts

    def test_the_stored_result_names_each_skip_and_stays_complete(self):
        from modules.preview_confirm import netbox_sync_result

        r = netbox_sync_result({"total": 9, "synced": 9, "complete": True,
                                "skipped": self.GROUPS})
        assert r["level"] == "success", "a deliberate skip is not a failure"
        kinds = [d["kind"] for d in r["did_not"]["items"]]
        assert "not_modelled" in kinds and "declined" not in kinds
