"""Heal to intent's triggers, attribution, fold and lock (`modules/heal/attribution.py`,
`modules/heal/triggers.py`, `modules/heal/incidents.py`; board H, part H2, docs/HEAL_TO_INTENT.md
section 3 and N2, N12), no network, no device, a fake clock.

- **Attribution:** a configuration-change line is Mercury's only by a hold, a receipt or a
  rotation at its receive time, never by the account it names; an unreadable record is
  unknown, never Mercury's; the person the line names is kept, IPv4 and IPv6.
- **Each trigger asks "check this device now":** a CONFIG_I from outside, any firing alert on a
  managed device (N2; by label or by polled address, IPv4 and IPv6; an interface's far end
  from intent, IPv4 and IPv6), an adjacency down for two reads (both ends), a logged drop
  (the peer by router id or address, IPv6 included; a drop a deploy explains is none), and the
  drift record (its read kept). Each once; nothing where healing is off.
- **One incident per cause:** a symptom inside a changed device's blast radius, or at the far
  end of its link, folds into its incident; a radius that cannot be judged over IPv6 alone
  folds nothing and says so; a member that changed becomes the cause, or its own incident when
  both changed.
- **The per-network lock** is held across processes, refused by name.
- **Installed where the readers start,** and a step that fails never stops a reader.
"""
import json
import os
import subprocess
import sys
import time

import pytest

from tests.test_heal_policy import T0, confirm, iso
from tests.test_sdn_connections import networks  # the fixture, named by each test below


class _Lazy:
    """A module of `modules.heal`, imported when a test first names it (red on a tree without
    it, each test on its own)."""

    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        import importlib

        return getattr(importlib.import_module(f"modules.heal.{self._name}"), attr)


AT, T, I = _Lazy("attribution"), _Lazy("triggers"), _Lazy("incidents")

#: Committed intent, three routers in a chain from Mercury's subnet (192.0.2.0/30): edge-a,
#: core-b, leaf-c; leaf-c's far link carries IPv6 too, and v6-d is reached over IPv6 alone.
MASK = "255.255.255.252"
INTENTS = {
    "edge-a": {"interfaces": [{"name": "GigabitEthernet1", "ipv4": f"192.0.2.1 {MASK}"},
                              {"name": "GigabitEthernet2", "ipv4": f"192.0.2.5 {MASK}"}]},
    "core-b": {"interfaces": [{"name": "GigabitEthernet1", "ipv4": f"192.0.2.6 {MASK}"},
                              {"name": "GigabitEthernet2", "ipv4": f"192.0.2.9 {MASK}"}]},
    "leaf-c": {"interfaces": [{"name": "GigabitEthernet1", "ipv4": f"192.0.2.10 {MASK}"},
                              {"name": "GigabitEthernet3", "ipv6": ["2001:db8:0:7::1/64"]}]},
    "v6-d": {"interfaces": [{"name": "GigabitEthernet1", "ipv6": ["2001:db8:0:7::2/64",
                                                                  "fe80::2/64"]}]},
}
DEVICES = {"edge-a": "192.0.2.1", "core-b": "192.0.2.6", "leaf-c": "192.0.2.10",
           "v6-d": "2001:db8:0:7::2"}


@pytest.fixture
def world(networks, monkeypatch):
    """Default with self-healing in dry run (Branch stays off), its four devices, committed
    intent and Mercury's subnet; no hold, receipt or rotation unless a test makes one."""
    from modules import attention as A
    from modules import neighbours as N
    from modules.nsot import blast_radius as BR

    confirm("Default", heal_mode="dry_run")
    held = {d: ["Default"] for d in DEVICES}
    held["shared"] = ["Default", "Branch"]
    monkeypatch.setattr(A, "_device_networks", lambda: dict(held))
    monkeypatch.setattr(A, "_inventory", lambda: ((set(DEVICES), {
        ip: {d} for d, ip in DEVICES.items()}), ""))
    monkeypatch.setattr(N, "committed_intents", lambda repo: (INTENTS, ""))
    monkeypatch.setattr(BR, "host_networks", lambda: ["192.0.2.0/30"])
    monkeypatch.setattr("modules.nsot.scheduled_rotation.committed_rotations",
                        lambda network: {})
    monkeypatch.setattr("modules.heal.detect.wake", lambda: None)
    return networks


def line(dev="core-b", ts=T0, by="console by alice on vty0 (192.0.2.50)",
         mn="%SYS-5-CONFIG_I"):
    return {"at": iso(ts), "ts": ts, "dev": dev, "sev": 5, "mn": mn,
            "text": f"Configured from {by}"}


def stored(network="Default"):
    return I.read(network)["incidents"]


def opened(network="Default"):
    return [i for i in stored(network) if i["state"] in I.OPEN_STATES]


# ── Attribution ─────────────────────────────────────────────────────────────────────────────

class TestAttribution:
    def test_a_hold_that_started_before_the_line_makes_it_mercurys(self):
        hold = {"operation": "deploy", "actor": "op@example.com", "started": T0 - 30}
        got = AT.attribute("Default", "core-b", T0, holder=lambda n, d: hold,
                           receipts=lambda n, d: [], rotations=lambda n: {})
        assert got["by"] == AT.MERCURY and "deploy by op@example.com held core-b" in \
            got["words"], got

    def test_a_hold_that_started_after_the_line_is_not_its(self):
        hold = {"operation": "deploy", "actor": "op@example.com", "started": T0 + 5}
        got = AT.attribute("Default", "core-b", T0, holder=lambda n, d: hold,
                           receipts=lambda n, d: [], rotations=lambda n: {})
        assert got["by"] == AT.OUTSIDE, got

    @pytest.mark.parametrize("offset,by", [(0, "mercury"), (599, "mercury"), (-59, "mercury"),
                                           (601, "outside"), (-61, "outside")])
    def test_a_receipt_explains_a_line_600_s_before_it_to_60_s_after(self, offset, by):
        receipt = {"id": "r1x", "action": "deploy", "at": iso(T0 + offset)}
        got = AT.attribute("Default", "core-b", T0, holder=lambda n, d: None,
                           receipts=lambda n, d: [receipt], rotations=lambda n: {})
        assert got["by"] == by, (offset, got)
        assert "600 s before" in got["words"]

    def test_a_rotation_commit_explains_its_line(self):
        got = AT.attribute("Default", "core-b", T0, holder=lambda n, d: None,
                           receipts=lambda n, d: [],
                           rotations=lambda n: {"core-b": (T0 - 20, iso(T0 - 20))})
        assert got["by"] == AT.MERCURY and "credential rotation" in got["words"]

    def test_an_unreadable_record_is_unknown_never_mercurys(self):
        def broken(n, d):
            raise RuntimeError("Default's receipts cannot be read (torn)")

        got = AT.attribute("Default", "core-b", T0, holder=lambda n, d: None,
                           receipts=broken, rotations=lambda n: {})
        assert got["by"] == AT.UNKNOWN and "torn" in got["words"]
        assert "treated as from outside Mercury" in got["words"]

    def test_never_by_the_account_the_line_names(self):
        """A person signed in with the account Mercury uses is still outside Mercury."""
        got = AT.attribute("Default", "core-b", T0, holder=lambda n, d: None,
                           receipts=lambda n, d: [], rotations=lambda n: {})
        assert got["by"] == AT.OUTSIDE
        person = AT.person_of("%SYS-5-CONFIG_I", "Configured from vty0 by mercury-svc on vty0 "
                                                 "(192.0.2.50)")
        assert person["user"] == "mercury-svc" and "the account mercury-svc" in person["words"]

    @pytest.mark.parametrize("raw,want", [("(192.0.2.50)", "192.0.2.50"),
                                          ("(2001:DB8:0:0::50)", "2001:db8::50")])
    def test_the_person_is_named_ipv4_and_ipv6(self, raw, want):
        p = AT.person_of("%SYS-5-CONFIG_I", f"Configured from vty0 by alice on vty0 {raw}")
        assert (p["user"], p["line"], p["address"]) == ("alice", "vty0", want)
        assert p["words"] == f"the line names the account alice on vty0 from {want}"

    def test_a_console_line_names_no_account(self):
        """C2819 (the operator, H11 W5): said once and plainly, never "the line names no
        account named on console from console"."""
        p = AT.person_of("%SYS-5-CONFIG_I", "Configured from console by console")
        assert p["user"] == "" and p["words"] == "made on the console, no account named"
        p = AT.person_of("%SYS-5-CONFIG_I", "Configured from console by alice on console")
        assert p["words"] == "the line names the account alice on console", p["words"]

    @pytest.mark.parametrize("raw,want", [
        ("192.0.2.7", "192.0.2.7"), ("192.0.2.7:161", "192.0.2.7"),
        ("[2001:db8::7]:161", "2001:db8::7"), ("2001:DB8::7", "2001:db8::7"), ("edge-a", "")])
    def test_address_of_reads_both_families_and_their_ports(self, raw, want):
        assert AT.address_of(raw) == want

    def test_only_configuration_change_lines_are_changes(self):
        assert AT.is_change("%SYS-5-CONFIG_I", "Configured from console by console")
        assert AT.is_change("%DMI-5-CONFIG_I", "Configured from NETCONF/RESTCONF by admin")
        assert not AT.is_change("%LINK-3-UPDOWN", "Interface Gi1, changed state to down")


# ── The configuration-change trigger ───────────────────────────────────────────────────────

class TestConfigChange:
    def test_a_line_from_outside_opens_the_devices_incident_naming_the_person(self, world):
        got = T.from_logs_tail("logs-tail", {"lines": [line()]}, now=T0)
        assert got["sighted"] == 1, got
        (inc,) = stored()
        assert (inc["device"], inc["cause"], inc["state"]) == ("core-b", "change", "watching")
        (t,) = inc["triggers"]
        assert t["kind"] == "config_change" and t["attribution"]["by"] == AT.OUTSIDE
        assert t["person"]["address"] == "192.0.2.50"
        assert "the account alice on vty0 from 192.0.2.50" in t["words"]

    def test_a_real_line_read_by_logs_tail_opens_its_devices_incident(self, world, monkeypatch):
        """C2467: end to end on a real capture, never typed data. The lab Loki's s3 lines
        (tests/fixtures/loki/lines_s3.json, two `%SYS-5-CONFIG_I` among them) read by the
        logs-tail reader itself, its value handed to the trigger as the reader job hands it."""
        from modules import attention as A
        from modules.nsot import blast_radius as BR
        from tests import test_logs_tail as LT

        with open(os.path.join(LT.LOKI, "lines_s3.json"), encoding="utf-8") as fh:
            streams = json.load(fh)["answer"]["data"]["result"]
        assert streams, "floor: the capture holds s3's lines"
        value = LT.T.read("Default", loki=LT.FakeLoki(streams), clock=lambda: LT.NOW)
        real = [l for l in value["lines"] if l["mn"] == "%SYS-5-CONFIG_I"]
        assert len(real) == 2 and {l["dev"] for l in real} == {"s3"}, real
        # s3 joins Default's devices; the capture's masked addresses (192.0.2.1) are not
        # Mercury's host in this test.
        held = dict(A._device_networks(), s3=["Default"])
        monkeypatch.setattr(A, "_device_networks", lambda: dict(held))
        names, by_ip = A._inventory()[0]
        monkeypatch.setattr(A, "_inventory", lambda: ((names | {"s3"}, dict(
            by_ip, **{"192.0.2.99": {"s3"}})), ""))
        monkeypatch.setattr(BR, "host_networks", lambda: ["198.51.100.0/30"])
        got = T.from_logs_tail("logs-tail", value, now=LT.NOW)
        assert got["sighted"] == 2, got
        (inc,) = [i for i in stored() if i["device"] == "s3"]
        assert (inc["cause"], inc["state"]) == ("change", "watching")
        assert {t["kind"] for t in inc["triggers"]} == {"config_change"}
        assert all(t["attribution"]["by"] == AT.OUTSIDE for t in inc["triggers"])

    def test_mercurys_own_line_is_no_trigger(self, world, monkeypatch):
        monkeypatch.setattr("modules.nsot.device_ops.holder", lambda n, d: {
            "operation": "deploy", "actor": "op@example.com", "started": T0 - 10})
        got = T.from_logs_tail("logs-tail", {"lines": [line()]}, now=T0)
        assert (got["sighted"], got["mercury"]) == (0, 1) and stored() == []

    def test_each_line_once_the_cursor_moves(self, world):
        T.from_logs_tail("logs-tail", {"lines": [line()]}, now=T0)
        again = T.from_logs_tail("logs-tail", {"lines": [line(), line(ts=T0 + 9)]}, now=T0 + 10)
        assert again["sighted"] == 1
        (inc,) = stored()
        assert len(inc["triggers"]) == 2

    def test_a_line_that_is_no_change_is_no_trigger(self, world):
        other = dict(line(), mn="%LINK-3-UPDOWN", text="Interface Gi1, changed state to down")
        assert T.from_logs_tail("logs-tail", {"lines": [other]}, now=T0)["sighted"] == 0

    def test_nothing_where_healing_is_off_but_the_lines_are_consumed(self, world, monkeypatch):
        from modules import attention as A

        monkeypatch.setattr(A, "_device_networks", lambda: {"core-b": ["Branch"]})
        got = T.from_logs_tail("logs-tail", {"lines": [line()]}, now=T0)
        assert (got["sighted"], got["off"]) == (0, 1) and stored("Branch") == []
        assert T._cursors()["cursors"]["logs-tail"] == T0

    def test_a_device_in_two_networks_is_not_placed_by_guess(self, world):
        got = T.from_logs_tail("logs-tail", {"lines": [line(dev="shared")]}, now=T0)
        assert got["sighted"] == 0 and "2 networks" in got["unplaced"][0]


# ── Alerts (N2) ─────────────────────────────────────────────────────────────────────────────

def alert(**kw):
    out = {"rule_uid": "u1", "rule": "NMAS heartbeat missing", "kind": "condition",
           "state": "Alerting (NoData)", "labels": {"device": "core-b"},
           "active_at": iso(T0 - 60), "device": "core-b", "device_from": "label"}
    out.update(kw)
    return out


class TestAlerts:
    def test_any_firing_alert_on_a_managed_device_checks_it(self, world):
        got = T.from_alerts("grafana-alerts", {"instances": [alert()]}, now=T0)
        assert got["sighted"] == 1
        (inc,) = stored()
        assert (inc["device"], inc["cause"]) == ("core-b", "symptom")
        assert "NMAS heartbeat missing fired on core-b" in inc["triggers"][0]["words"]

    def test_a_lost_streams_trigger_carries_its_subscription(self, world):
        """C2828: the stream runbook reads which subscription was lost, and how long its alert
        takes to see one, from the trigger (the generator's labels)."""
        inst = alert(rule="NMAS telemetry stream lost: core-b subscription 101",
                     labels={"device": "core-b", "nmas": "telemetry", "subscription": "101",
                             "detect_seconds": "150"})
        T.from_alerts("grafana-alerts", {"instances": [inst]}, now=T0)
        (inc,) = stored()
        t = inc["triggers"][0]
        assert (t["subscription"], t["detect_seconds"]) == ("101", "150")
        T.from_alerts("grafana-alerts", {"instances": [alert(rule_uid="u2")]}, now=T0)
        assert not any("subscription" in t for i in stored() for t in i["triggers"]
                       if "heartbeat" in t["rule"]), "only a stream rule's labels carry it"

    def test_once_an_episode(self, world):
        T.from_alerts("grafana-alerts", {"instances": [alert()]}, now=T0)
        assert T.from_alerts("grafana-alerts", {"instances": [alert()]},
                             now=T0 + 60)["sighted"] == 0

    def test_a_condition_not_firing_is_no_trigger(self, world):
        got = T.from_alerts("grafana-alerts", {"instances": [alert(kind="no_data")]}, now=T0)
        assert got["sighted"] == 0

    @pytest.mark.parametrize("polled,device", [("192.0.2.10:161", "leaf-c"),
                                               ("[2001:db8:0:7::2]:161", "v6-d")])
    def test_a_polled_address_names_its_device_ipv4_and_ipv6(self, world, polled, device):
        inst = alert(labels={"instance": polled}, device=None, address=polled,
                     device_from="address")
        assert T.from_alerts("grafana-alerts", {"instances": [inst]}, now=T0)["sighted"] == 1
        assert [i["device"] for i in stored()] == [device]

    @pytest.mark.parametrize("device,iface,far", [("core-b", "GigabitEthernet2", "leaf-c"),
                                                  ("leaf-c", "GigabitEthernet3", "v6-d")])
    def test_an_interface_named_checks_the_far_end_intent_names_ipv4_and_ipv6(
            self, world, device, iface, far):
        inst = alert(rule="Interface down", labels={"device": device, "ifDescr": iface},
                     device=device)
        T.from_alerts("grafana-alerts", {"instances": [inst]}, now=T0)
        (inc,) = opened()
        assert inc["device"] == device, "one incident on the link"
        assert [m["device"] for m in inc["attached"]] == [far]
        assert "far end of the link" in inc["attached"][0]["why"]

    def test_far_ends_ignore_link_local_and_shut_interfaces(self):
        assert T.far_ends(INTENTS, "v6-d", "GigabitEthernet1") == ["leaf-c"]
        shut = {"a": {"interfaces": [{"name": "G1", "ipv4": f"192.0.2.1 {MASK}"}]},
                "b": {"interfaces": [{"name": "G1", "ipv4": f"192.0.2.2 {MASK}",
                                      "shutdown": True}]}}
        assert T.far_ends(shut, "a", "G1") == [] and T.far_ends(shut, "a", "G9") == []


# ── Adjacencies, the adjacency log, the topology, the drift record ─────────────────────────

class TestAdjacencies:
    VALUE = {"adjacencies": {"Default|ospf|core-b|leaf-c|192.0.2.8/30": {
        "list": "Default", "protocol": "OSPF", "devices": ["core-b", "leaf-c"], "reads": 2,
        "since": iso(T0 - 120), "managed": True}}}

    def test_down_for_two_reads_checks_both_ends_in_one_incident(self, world):
        got = T.from_adjacencies("adjacencies", self.VALUE, now=T0)
        assert got["sighted"] == 2
        (inc,) = opened()
        assert inc["device"] == "core-b" and [m["device"] for m in inc["attached"]] == ["leaf-c"]

    def test_one_read_is_no_trigger_yet(self, world):
        one = json.loads(json.dumps(self.VALUE))
        one["adjacencies"]["Default|ospf|core-b|leaf-c|192.0.2.8/30"]["reads"] = 1
        assert T.from_adjacencies("adjacencies", one, now=T0)["sighted"] == 0


class TestAdjacencyLog:
    def drop(self, neighbor, epoch=T0):
        return {"adjacencies": {f"Default|leaf-c|BGP|{neighbor}": {
            "list": "Default", "device": "leaf-c", "protocol": "BGP", "neighbor": neighbor,
            "interface": "", "drops": [{"at": iso(epoch), "epoch": epoch,
                                        "reason": "BGP Notification sent"}]}}}

    @pytest.mark.parametrize("neighbor", ["192.0.2.9", "2001:db8:0:7::2"])
    def test_a_drop_checks_both_ends_its_peer_by_address_ipv4_and_ipv6(self, world, neighbor):
        peer = {"192.0.2.9": "core-b", "2001:db8:0:7::2": "v6-d"}[neighbor]
        got = T.from_adjacency_log("adjacency-log", self.drop(neighbor), now=T0, planned=[],
                                   receipts=lambda n, d: [])
        assert got["sighted"] == 2, got
        (inc,) = opened()
        assert {inc["device"]} | {m["device"] for m in inc["attached"]} == {"leaf-c", peer}

    def test_a_drop_a_deploy_explains_is_no_trigger(self, world):
        got = T.from_adjacency_log("adjacency-log", self.drop("192.0.2.9"), now=T0, planned=[],
                                   receipts=lambda n, d: [{"at": iso(T0 + 30)}])
        assert (got["sighted"], got["explained"]) == (0, 1)

    def test_each_drop_once(self, world):
        kw = {"planned": [], "receipts": lambda n, d: []}
        T.from_adjacency_log("adjacency-log", self.drop("192.0.2.9"), now=T0, **kw)
        assert T.from_adjacency_log("adjacency-log", self.drop("192.0.2.9"), now=T0 + 120,
                                    **kw)["sighted"] == 0


class TestDuplicateRouterId:
    """C2446: the adjacency-log reader's duplicate router-id reports (typed here in the
    reader's shape; the real lines are tests/test_duplicate_router_id.py's), each episode a
    trigger on each device that logged it, and on the neighbour intent names by its address."""

    def dup(self, reports, rid="192.0.2.77"):
        return {"duplicates": {f"Default|OSPF|{rid}": {
            "list": "Default", "protocol": "OSPF", "router_id": rid, "reports": {
                d: {"device": d, "count": 2, "first_epoch": first, "last_epoch": last,
                    "neighbors": [nbr], "interfaces": ["GigabitEthernet1"], "areas": [],
                    "variants": ["NBR"]} for d, (nbr, first, last) in reports.items()}}}}

    def test_both_routers_logging_it_are_checked_in_one_incident(self, world):
        value = self.dup({"edge-a": ("192.0.2.6", T0, T0 + 66),
                          "core-b": ("192.0.2.5", T0 + 2, T0 + 68)})
        got = T.from_adjacency_log("adjacency-log", value, now=T0 + 70)
        assert got["sighted"] == 2, got
        (inc,) = opened()
        assert {inc["device"]} | {m["device"] for m in inc["attached"]} == {"edge-a", "core-b"}
        kinds = {t["kind"] for t in inc["triggers"]}
        assert kinds == {"duplicate_router_id"}, kinds
        assert inc["triggers"][0]["router_id"] == "192.0.2.77"

    def test_one_router_logging_it_checks_the_neighbour_intent_names(self, world):
        got = T.from_adjacency_log("adjacency-log",
                                   self.dup({"edge-a": ("192.0.2.6", T0, T0 + 66)}),
                                   now=T0 + 70)
        assert got["sighted"] == 2, got
        (inc,) = opened()
        assert {inc["device"]} | {m["device"] for m in inc["attached"]} == {"edge-a", "core-b"}

    def test_each_episode_once_and_a_new_one_after_the_quiet_time(self, world):
        from modules.readers import adjacency_log as AL

        T.from_adjacency_log("adjacency-log", self.dup({"edge-a": ("192.0.2.6", T0, T0 + 66)}),
                             now=T0 + 70)
        same = self.dup({"edge-a": ("192.0.2.6", T0, T0 + 132)})
        assert T.from_adjacency_log("adjacency-log", same, now=T0 + 140)["sighted"] == 0
        back = T0 + 132 + AL.QUIET_SECONDS + 60
        again = self.dup({"edge-a": ("192.0.2.6", back, back + 66)})
        assert T.from_adjacency_log("adjacency-log", again, now=back + 70)["sighted"] == 2


class TestTopology:
    def graph(self, *links):
        return {"configured": True, "networks": {"Default": {"layers": {"physical": [
            {"a": a, "port_a": "G1", "b": b, "port_b": "G1", "state": "up"} for a, b in links]}}}}

    def test_the_first_sighting_is_no_change_and_a_new_link_is(self, world, monkeypatch):
        monkeypatch.setattr("modules.readers.topology_graph.network_of",
                            lambda value, name: value["networks"].get(name))
        T.from_topology("topology-graph", self.graph(("edge-a", "core-b")), now=T0)
        assert T.link_set("Default")["changed_epoch"] == 0
        T.from_topology("topology-graph", self.graph(("edge-a", "core-b")), now=T0 + 60)
        assert T.link_set("Default")["changed_epoch"] == 0, "state aside, the same set"
        got = T.from_topology("topology-graph",
                              self.graph(("edge-a", "core-b"), ("core-b", "leaf-c")), now=T0 + 120)
        assert got["link_sets_changed"] == ["Default"]
        assert T.link_set("Default")["changed_epoch"] == T0 + 120


class TestDriftRecord:
    def test_a_drifted_device_opens_its_incident_with_the_runs_read(self, world):
        result = {"triggered_by": "scheduled", "drifted_devices": [
            {"hostname": "core-b", "changed_lines": 1, "read_at": T0, "departure": "abc"}]}
        assert T.after_drift_record("Default", result, now=T0)["sighted"] == 1
        (inc,) = stored()
        assert inc["cause"] == "change"
        assert [(r["state"], r["departure"], r["epoch"]) for r in inc["reads"]] == \
            [("drifted", "abc", T0)]

    def test_the_drift_checker_records_then_sights(self, world, monkeypatch):
        from modules import drift_check as D

        seen = []
        monkeypatch.setattr("modules.heal.triggers.after_drift_record",
                            lambda n, r: seen.append((n, r)))
        monkeypatch.setattr(D, "_save_state", lambda data, list_name="": None)
        D.DriftChecker().record("Default", {"drifted_devices": []})
        assert seen == [("Default", {"drifted_devices": []})]

    def test_a_failing_trigger_never_fails_the_record(self, world, monkeypatch):
        from modules import drift_check as D

        def boom(n, r):
            raise RuntimeError("no")

        monkeypatch.setattr("modules.heal.triggers.after_drift_record", boom)
        monkeypatch.setattr(D, "_save_state", lambda data, list_name="": None)
        D.DriftChecker().record("Default", {})


# ── The fold: one incident per cause ───────────────────────────────────────────────────────

def cause(device, ts=T0):
    return T.from_logs_tail("logs-tail", {"lines": [line(dev=device, ts=ts)]}, now=ts)


def symptom(device, ts=T0):
    return T.from_alerts("grafana-alerts", {"instances": [alert(
        labels={"device": device, "n": str(ts)}, device=device, active_at=iso(ts))]}, now=ts)


class TestTheFold:
    def test_a_symptom_inside_a_changed_devices_blast_radius_folds_into_it(self, world):
        cause("core-b")
        symptom("leaf-c", T0 + 30)
        (inc,) = opened()
        assert inc["device"] == "core-b"
        (m,) = inc["attached"]
        assert m["device"] == "leaf-c" and "inside core-b's blast radius" in m["why"]

    def test_a_cause_takes_in_the_symptoms_its_radius_already_holds(self, world):
        symptom("leaf-c")
        cause("core-b", T0 + 30)
        (inc,) = opened()
        assert inc["device"] == "core-b" and [m["device"] for m in inc["attached"]] == ["leaf-c"]
        (folded,) = [i for i in stored() if i["state"] == "closed"]
        assert folded["device"] == "leaf-c" and folded["folded_into"] == inc["id"]

    def test_a_symptom_outside_the_radius_is_its_own(self, world):
        cause("leaf-c")
        symptom("edge-a", T0 + 30)
        assert sorted(i["device"] for i in opened()) == ["edge-a", "leaf-c"]

    def test_a_path_over_ipv6_alone_is_not_judged_and_says_so(self, world):
        cause("leaf-c")
        symptom("v6-d", T0 + 30)
        mine = next(i for i in opened() if i["device"] == "v6-d")
        assert "a path over IPv6 alone is not judged" in mine["fold"]["why"], mine["fold"]

    def test_a_member_that_changed_becomes_the_cause(self, world):
        T.from_alerts("grafana-alerts", {"instances": [alert(
            rule="Interface down", labels={"device": "core-b", "ifDescr": "GigabitEthernet2"},
            device="core-b")]}, now=T0)
        cause("leaf-c", T0 + 30)
        (inc,) = opened()
        assert inc["device"] == "leaf-c" and inc["cause"] == "change"
        assert [m["device"] for m in inc["attached"]] == ["core-b"]

    def test_two_devices_changed_are_two_incidents_naming_each_other(self, world):
        cause("core-b")
        symptom("leaf-c", T0 + 10)
        cause("leaf-c", T0 + 20)
        a, b = sorted(opened(), key=lambda i: i["device"])
        assert (a["device"], b["device"]) == ("core-b", "leaf-c")
        assert a["related"][0]["device"] == "leaf-c" and b["related"][0]["device"] == "core-b"
        assert "a cause spanning devices" in a["related"][0]["why"]
        assert a["attached"] == []

    def test_a_device_is_in_one_open_incident_at_most(self, world):
        cause("core-b")
        symptom("leaf-c", T0 + 10)
        symptom("leaf-c", T0 + 20)
        cause("core-b", T0 + 30)
        devices = [d for i in opened() for d in [i["device"]] + [m["device"] for m in
                                                                   i["attached"]]]
        assert sorted(devices) == ["core-b", "leaf-c"]

    def test_a_network_that_does_not_exist_is_refused(self, world):
        with pytest.raises(I.Refused):
            I.sight("Nowhere", "core-b", {"kind": "drift", "key": "k", "epoch": T0}, now=T0)

    def test_an_unreadable_store_is_never_replaced(self, world):
        from modules.filestore import StoreUnreadable

        cause("core-b")
        with open(I.path("Default"), "w", encoding="utf-8") as fh:
            fh.write("{torn")
        with pytest.raises(StoreUnreadable):
            I.sight("Default", "leaf-c", {"kind": "drift", "key": "k", "epoch": T0}, now=T0)
        assert I.read("Default")["state"] == "unreadable"


# ── The per-network lock ────────────────────────────────────────────────────────────────────

class TestTheLock:
    def test_a_second_holder_is_refused_naming_the_first(self, world):
        with I.HealLock("Default", actor="Mercury", trigger="the detect pass"):
            with pytest.raises(I.HealBusy) as got:
                with I.HealLock("Default", actor="Mercury", trigger="another pass"):
                    pass
        assert "the detect pass by Mercury" in str(got.value)
        with I.HealLock("Default", actor="Mercury", trigger="after"):
            pass

    def test_held_by_another_process_is_refused(self, world):
        path = os.path.join(I._dir("Default"), I.LOCK_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        script = ("import fcntl, json, os, sys\n"
                  "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
                  "fcntl.flock(fd, fcntl.LOCK_EX)\n"
                  "os.write(fd, json.dumps({'pid': os.getpid(), 'actor': 'Mercury', "
                  "'trigger': 'a pass elsewhere', 'started_at': 'then'}).encode())\n"
                  "print('held', flush=True)\n"
                  "sys.stdin.read()\n")
        child = subprocess.Popen([sys.executable, "-c", script, path], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, text=True)
        try:
            assert child.stdout.readline().strip() == "held"
            with pytest.raises(I.HealBusy) as got:
                with I.HealLock("Default", actor="Mercury", trigger="here"):
                    pass
            assert "a pass elsewhere" in str(got.value) and str(child.pid) in str(got.value)
        finally:
            child.stdin.close()
            child.wait(timeout=10)
        with I.HealLock("Default", actor="Mercury", trigger="after"):
            pass


# ── Installed where the readers start; never stops a reader ────────────────────────────────

class TestInstalled:
    def test_start_installs_the_steps(self, monkeypatch, world):
        from modules import reader_job as RJ

        monkeypatch.setattr(RJ, "readers", lambda: [])
        T.uninstall()
        RJ.start()
        try:
            assert T._after_store in RJ._AFTER_ANY_STORE
        finally:
            T.uninstall()

    def test_a_readers_store_runs_its_step_by_its_configurations_name(self, world):
        from modules import reader_job as RJ

        reader = RJ.Reader(name="logs-tail@t1", what="a test's tail", endpoints=("a test",),
                           interval_seconds=5, interval_basis="a test", invalidates=("logs",),
                           read=lambda: {"configured": True, "lines": [line()]})
        T.install()
        try:
            RJ.run_once(reader, clock=lambda: T0)
        finally:
            T.uninstall()
        assert [i["device"] for i in stored()] == ["core-b"]

    def test_a_step_that_fails_never_stops_the_reader(self, world, monkeypatch):
        from modules import reader_job as RJ

        def boom(store, value):
            raise RuntimeError("no")

        monkeypatch.setitem(T.STEPS, "logs-tail", boom)
        reader = RJ.Reader(name="logs-tail@t2", what="a test's tail", endpoints=("a test",),
                           interval_seconds=5, interval_basis="a test", invalidates=("logs",),
                           read=lambda: {"configured": True, "lines": []})
        T.install()
        try:
            doc = RJ.run_once(reader, clock=time.time)
        finally:
            T.uninstall()
        assert doc["last_attempt"]["ok"] is True

    def test_an_unchanged_value_is_not_read_again(self, world, monkeypatch):
        calls = []
        monkeypatch.setitem(T.STEPS, "logs-tail", lambda s, v: calls.append(s))
        T._after_store(type("R", (), {"name": "logs-tail"})(), moved=False)
        assert calls == []
