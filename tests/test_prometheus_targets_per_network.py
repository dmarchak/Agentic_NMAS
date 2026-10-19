"""K11 (Core 1.0; C229's "per-network targets"): each Prometheus scrapes the networks it serves.

A network inheriting Prometheus is Default's; one that sets its own, or declares it not
applicable, is its own owner (`list_settings.group_owner`). Before this, every network's devices
were written into Default's one targets directory, so a network with its own Prometheus was
scraped by Default's, and Default's job-health row compared Default's Prometheus with every
network's devices.

- the partition: each network under its owner, Default always among the owners;
- the keeper writes each owner's lists' devices into that owner's directory, and records each
  run in that owner's record; an owner naming no directory is not written;
- two owners naming one directory are both refused, each naming the other, nothing written;
- each owner's job-health row asks that owner's Prometheus and names the network;
- retire's read-back regenerates the retired device's owner's files;
- monitoring coverage dates an SNMP exclusion by the device's own owner's record.

The goldens are the REAL fleet's r2 (`tests/fixtures/configs/fleet/`); one device carries an
IPv6 management address beside the IPv4 ones (IPv6 parity: partitioned like any other).
"""

import json
import os

import pytest

from modules import list_settings as L
from modules import prometheus_targets as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R2 = open(os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r2.cfg"),
          encoding="utf-8").read()

#: Each network's Prometheus owner: Lab9 inherits Default's, Branch sets its own, Off declares
#: Prometheus not applicable.
OWNERS = {"Default": "Default", "Lab9": "Default", "Branch": "Branch", "Off": "Off"}
DEVICES = {"Default": [("r1", "192.0.2.11")], "Lab9": [("l9", "192.0.2.60")],
           "Branch": [("b1", "2001:db8::21")], "Off": [("o1", "192.0.2.70")]}


class _Ref:
    def __init__(self, name):
        self.name, self.repo_dir = name, f"/repos/{name}"


@pytest.fixture
def world(monkeypatch, tmp_path):
    """Four networks, each owner's directory, each list's devices, and a data folder of its
    own for the keeper's records."""
    from modules import config

    dirs = {"Default": tmp_path / "default", "Branch": tmp_path / "branch"}
    for d in dirs.values():
        d.mkdir()
    named = {k: str(v) for k, v in dirs.items()}

    def group_owner(name, group):
        assert group == "prometheus", group
        return OWNERS[name], "a test's owner"

    real_value = L.value

    def value(name, key, default=None):
        if key == "prometheus_targets_dir":
            return named.get(name, "")
        return real_value(name, key, default)

    def inventory(lists=None):
        return [(_Ref(n), {"hostname": h, "ip": ip, "role": "router", "platform": "cisco_iosxe",
                           "device_type": "cisco_xe"})
                for n in lists for h, ip in DEVICES[n]]

    monkeypatch.setattr(L, "group_owner", group_owner)
    monkeypatch.setattr(L, "value", value)
    monkeypatch.setattr("modules.device.get_device_lists", lambda: [{"name": n} for n in OWNERS])
    monkeypatch.setattr(P, "inventory", inventory)
    monkeypatch.setattr(P, "read_golden", lambda ref, host: R2)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "data"))
    os.makedirs(config.DATA_DIR)
    return {"dirs": dirs, "named": named}


def _devices_in(directory):
    with open(os.path.join(directory, "nmas-snmp-all.json"), encoding="utf-8") as fh:
        return {(g["labels"]["device"], g["targets"][0]) for g in json.load(fh)}


class TestThePartition:
    def test_each_network_is_under_its_prometheus_owner(self, world):
        assert P.owners() == {"Default": ["Default", "Lab9"], "Branch": ["Branch"],
                              "Off": ["Off"]}

    def test_default_is_an_owner_even_when_no_network_inherits_it(self, world):
        assert P._with_default({"Branch": ["Branch"]}) == {"Default": [], "Branch": ["Branch"]}

    def test_a_network_s_owner_is_asked_by_name(self, world):
        assert [P.owner_of(n) for n in ("Lab9", "Branch", "")] == ["Default", "Branch", "Default"]


class TestEachOwnerHasItsOwnFiles:
    def test_each_directory_holds_its_own_networks_devices(self, world):
        out = P.sync_all("a test")
        assert sorted(out) == ["Branch", "Default"], out      # Off names no directory
        assert all(rec["ok"] for rec in out.values()), out
        assert _devices_in(world["named"]["Default"]) == {("r1", "192.0.2.11"),
                                                          ("l9", "192.0.2.60")}
        assert _devices_in(world["named"]["Branch"]) == {("b1", "2001:db8::21")}

    def test_each_run_is_recorded_in_its_owner_s_record(self, world):
        P.sync_all("a test")
        assert P.last_sync("Default")["devices"] == 2 and "network" not in P.last_sync("Default")
        branch = P.last_sync("Branch")
        assert branch["devices"] == 1 and branch["network"] == "Branch"
        assert P._record_path("Branch") != P._record_path("Default")
        assert P.last_sync("Off") == {}

    def test_two_owners_naming_one_directory_are_both_refused_naming_each_other(self, world):
        world["named"]["Branch"] = world["named"]["Default"]
        out = P.sync_all("a test")
        assert not out["Default"]["ok"] and not out["Branch"]["ok"], out
        assert "also the targets directory of Branch" in out["Default"]["error"]
        assert "also the targets directory of Default" in out["Branch"]["error"]
        assert os.listdir(world["named"]["Default"]) == []

    def test_one_owner_s_direct_run_is_refused_too(self, world):
        """retire's read-back calls `sync` for one owner: the refusal is sync's own."""
        world["named"]["Branch"] = world["named"]["Default"]
        rec = P.sync("retire of b1", owner="Branch")
        assert rec["ok"] is False and "also the targets directory of Default" in rec["error"]


class _Down:
    """A configured Prometheus that cannot be asked: its row is `unknown`, so it is drawn."""

    def __init__(self, owner):
        self.owner = owner

    def is_configured(self):
        return self.owner != "Off"

    def _get(self, path, **params):
        return {"ok": False, "error": f"{self.owner}'s Prometheus refused the connection"}


class TestEachOwnersRow:
    def test_each_row_asks_its_own_prometheus_and_names_the_network(self, world, monkeypatch):
        asked = []
        monkeypatch.setattr(P, "client_for", lambda owner: asked.append(owner) or _Down(owner))
        rows = P.every_health_row()
        assert sorted(asked) == ["Branch", "Default", "Off"]
        by_unit = {r["unit"]: r for r in rows}
        assert sorted(by_unit) == ["prometheus-targets", "prometheus-targets@branch"], by_unit
        assert "Branch's Prometheus refused" in by_unit["prometheus-targets@branch"]["detail"]
        assert by_unit["prometheus-targets@branch"]["list"] == "Branch"
        assert by_unit["prometheus-targets@branch"]["what"].endswith("for Branch's Prometheus")
        assert "Default's Prometheus refused" in by_unit["prometheus-targets"]["detail"]
        assert "list" not in by_unit["prometheus-targets"]

    def test_default_s_client_is_built_for_no_list_as_before(self, world):
        assert P.client_for("Default").list_name == ""
        assert P.client_for("Branch").list_name == "Branch"


class TestRetireReadsItsOwnersFiles:
    def test_the_read_back_regenerates_the_device_s_owner_s_directory(self, world):
        from modules.nsot import retire as RT

        got = RT.targets_after("b1", "2001:db8::21", "Branch")
        assert got["state"] == "still" and "nmas-snmp-all.json" in got["statement"], got
        assert os.listdir(world["named"]["Default"]) == []
        assert P.last_sync("Branch")["reason"] == "retire of b1"


class TestCoverageDatesByTheDevicesOwner:
    def test_an_exclusion_is_dated_by_its_own_owner_s_record(self, world, monkeypatch):
        from modules import monitoring_coverage as M
        from modules.filestore import write_atomic

        no_snmp = "".join(l for l in R2.splitlines(True) if not l.startswith("snmp-server"))
        for owner, since in (("Default", "2026-10-01T00:00:00Z"),
                             ("Branch", "2026-10-02T00:00:00Z")):
            write_atomic(P._record_path(owner), json.dumps(
                {"excluded": {"b1": {"since": since, "why": "configures no SNMP"}}}))
        vals = {"prometheus_url": "http://p"}
        (row,) = M.rows([(_Ref("Branch"), {"hostname": "b1"})], lambda ref, host: no_snmp,
                        lambda k, d=None: vals.get(k, d), now=1790800000, record=False)
        assert "2026-10-02T00:00:00Z" in row["detail"], row["detail"]
