"""The NSOT snapshot export (the SDN platform design revision 6, section 5, C; T6):
`modules/nsot/export.py`.

- **Deterministic:** two builds of the same NetBox are byte-identical; NetBox answering in
  another order (every list reversed, every record's keys reordered) changes nothing; a
  time-varying field (``last_updated``, ``created``) is never in the document.
- **Hashed:** ``sha256`` covers the schema version, the network and NetBox's version as well as
  the body; a document edited after it was built, or of another schema version, is refused,
  naming both sides.
- **Committed and read back from history:** `write` commits ``nsot/export.json`` as the actor
  (``Source: nsot_export``), an unchanged export commits nothing, and `read` takes what is
  committed, never the working tree.
- **Read by kind, never per device:** `collect` reads each list once per hundred devices.
- **Offline:** `openflow_values.from_export` reads the same values from an export as
  `from_netbox` from the live records, IPv4 and IPv6 alike.
- **The fixture is masked:** every address in the lab's export is a documentation address.
"""

import copy
import ipaddress
import json
import os

import pytest

from modules.nsot import export as X
from modules.sdn import openflow_templates as T
from modules.sdn import openflow_values as V
from tests.test_openflow_golden import _records, fake_netbox

NETWORK = "lab9"


@pytest.fixture
def netbox_list(monkeypatch):
    monkeypatch.setattr("modules.inventory.source_config.load",
                        lambda name: {"source": "netbox",
                                      "filters": {"role": "openflow-switch"}})


def _build(records=None, **kw):
    records = records or _records()
    get, calls = fake_netbox(records)
    got = X.build(NETWORK, get=get, version=lambda: records["netbox_version"], **kw)
    assert got["ok"], got["error"]
    return got, calls


def _shuffled(node):
    """*node* with every list reversed and every mapping's keys in reverse order."""
    if isinstance(node, dict):
        return {k: _shuffled(node[k]) for k in reversed(list(node))}
    if isinstance(node, list):
        return [_shuffled(x) for x in reversed(node)]
    return node


class TestDeterministic:
    def test_two_builds_are_byte_identical(self, netbox_list):
        assert _build()[0]["bytes"] == _build()[0]["bytes"]

    def test_netbox_answering_in_another_order_changes_nothing(self, netbox_list):
        records = _records()
        assert _build(_shuffled(copy.deepcopy(records)))[0]["bytes"] == \
            _build(records)[0]["bytes"]

    def test_nothing_time_varying_is_in_the_document(self, netbox_list):
        records = _records()
        first = _build(records)[0]["bytes"]
        later = copy.deepcopy(records)
        for d in later["devices"]:
            d["last_updated"] = "2026-12-01T00:00:00Z"
        for i in later["interfaces"]:
            i["created"] = "2026-12-01T00:00:00Z"
        assert _build(later)[0]["bytes"] == first
        assert b"last_updated" not in first and b"created" not in first

    def test_every_list_is_sorted_by_its_natural_key(self, netbox_list):
        body = json.loads(_build()[0]["bytes"])["body"]
        assert [d["name"] for d in body["devices"]] == sorted(d["name"] for d in body["devices"])
        keys = [(i["device"], i["name"]) for i in body["interfaces"]]
        assert keys == sorted(keys)
        assert [p["prefix"] for p in body["prefixes"]] == ["192.0.2.0/24", "198.51.100.0/24"]

    def test_a_netbox_change_changes_the_hash(self, netbox_list):
        records = _records()
        before = _build(records)[0]["sha256"]
        records["interfaces"][2]["custom_fields"]["openflow_port"] = 20
        assert _build(records)[0]["sha256"] != before


class TestHashed:
    def test_the_schema_version_is_inside_the_hash(self, netbox_list, monkeypatch):
        records = _records()
        doc = json.loads(_build(records)[0]["bytes"])
        monkeypatch.setattr(X, "SCHEMA_VERSION", X.SCHEMA_VERSION + 1)
        other = json.loads(X.document(NETWORK, records["netbox_version"],
                                      fake_netbox_records(records)))
        assert other["body"] == doc["body"] and other["sha256"] != doc["sha256"]

    def test_another_schema_version_is_refused_naming_both(self, netbox_list, monkeypatch):
        data = _build()[0]["bytes"]
        monkeypatch.setattr(X, "SCHEMA_VERSION", 2)
        with pytest.raises(X.Refused, match=r"schema version is 1, and Mercury reads 2"):
            X.parse(data)

    def test_a_document_edited_after_it_was_built_is_refused_naming_both(self, netbox_list):
        doc = json.loads(_build()[0]["bytes"])
        doc["body"]["interfaces"][0]["enabled"] = False
        with pytest.raises(X.Refused) as got:
            X.parse(json.dumps(doc))
        assert doc["sha256"][:12] in str(got.value) and X.digest(doc)[:12] in str(got.value)


def fake_netbox_records(records):
    """The records as `collect` hands them to `document` (each interface with its addresses)."""
    get, _ = fake_netbox(records)
    from modules.inventory import source_config  # noqa: F401 (patched by the fixture)
    return X.collect(NETWORK, get=get, version=lambda: "")["records"]


class TestReads:
    def test_each_list_is_read_by_kind_never_per_device(self, netbox_list):
        records = _records()
        base = records["devices"][0]
        for n in range(250):
            records["devices"].append(dict(copy.deepcopy(base), id=1000 + n, name=f"sw{n:03d}"))
        _got, calls = _build(records)
        per = {}
        for path, _params in calls:
            per[path] = per.get(path, 0) + 1
        # 256 devices: three hundred-device chunks for each per-device list.
        assert per["dcim/interfaces/"] == per["ipam/ip-addresses/"] == 3
        assert per["dcim/cables/"] == 3 and per["ipam/services/"] == 1 + 3
        # The list's devices, then its one controller outside the filter, by name, then the
        # end hosts at its sites, by their tag (C2776): one read each, never one per device.
        assert per["dcim/devices/"] == 3 and per["ipam/vlans/"] == per["ipam/prefixes/"] == 1
        host_reads = [p for path, p in calls if path == "dcim/devices/" and "tag" in p]
        assert host_reads == [{"tag": X.HOST_TAG, "site_id": host_reads[0]["site_id"]}]

    def test_a_list_whose_devices_are_local_is_refused(self, monkeypatch):
        monkeypatch.setattr("modules.inventory.source_config.load",
                            lambda name: {"source": "local", "filters": {}})
        got = X.build(NETWORK, get=lambda path, **p: [], version=lambda: "")
        assert not got["ok"] and "'local', not NetBox" in got["error"] and got["bytes"] == b""

    def test_an_unreadable_netbox_is_said(self, netbox_list):
        def get(path, **params):
            raise ConnectionError("refused")
        got = X.build(NETWORK, get=get, version=lambda: "")
        assert not got["ok"] and "ConnectionError: refused" in got["error"]


@pytest.fixture
def net(tmp_path, monkeypatch, netbox_list):
    list_dir = tmp_path / "lab9"
    os.makedirs(list_dir / "config_repo", exist_ok=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.list_data_path", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    return list_dir


class TestCommitted:
    def test_written_as_the_actor_and_read_back_from_history(self, net):
        built, _ = _build()
        got = X.write(NETWORK, "op@example.invalid", "access-assertion", data=built["bytes"])
        assert got["ok"], got["error"]
        assert got["changed"] and got["sha256"] == built["sha256"]
        from modules.nsot.repo import git
        _rc, message, _ = git(str(net / "config_repo"), "log", "-1", "--format=%B")
        assert "Actor: op@example.invalid" in message and "Source: nsot_export" in message
        assert f"Export-Sha256: {built['sha256']}" in message
        back = X.read(NETWORK)
        assert back["ok"] and back["sha256"] == built["sha256"]

    def test_an_unchanged_export_commits_nothing(self, net):
        built, _ = _build()
        X.write(NETWORK, "op@example.invalid", "access-assertion", data=built["bytes"])
        again = X.write(NETWORK, "op@example.invalid", "access-assertion", data=built["bytes"])
        assert again["ok"] and not again["changed"] and again["commit"] == ""

    def test_read_takes_the_committed_export_never_the_working_tree(self, net):
        built, _ = _build()
        X.write(NETWORK, "op@example.invalid", "access-assertion", data=built["bytes"])
        with open(net / "config_repo" / X.PATH, "w", encoding="utf-8") as fh:
            fh.write("{}")
        assert X.read(NETWORK)["sha256"] == built["sha256"]

    def test_nothing_committed_is_said_and_an_unverified_actor_is_refused(self, net):
        assert not X.read(NETWORK)["ok"] and "no committed NSOT export" in X.read(NETWORK)["error"]
        built, _ = _build()
        assert not X.write(NETWORK, "op@example.invalid", "", data=built["bytes"])["ok"]
        other = X.write("elsewhere", "op@example.invalid", "access-assertion",
                        data=built["bytes"])
        assert not other["ok"] and "'lab9'" in other["error"]


class TestOffline:
    def test_the_export_gives_the_values_the_live_records_give(self, netbox_list):
        records = _records()
        doc = X.parse(_build(records)[0]["bytes"])
        live = fake_netbox_records(records)
        device = next(d for d in live["devices"] if d["name"] == "ovs1")
        ifaces = [i for i in live["interfaces"] if i["device"]["name"] == "ovs1"]
        controllers = {"controller": next(d for d in live["devices"]
                                          if d["name"] == "controller")}
        services = {(s["device"]["name"], s["name"]): s for s in live["services"]}
        want = V.from_netbox(device, ifaces, [s for s in services.values()
                                              if s["name"] == "openflow"], controllers)
        got = V.from_export(doc, "ovs1")
        assert got["ok"] and want["ok"]
        assert got["values"].pop("nsot.export_sha256") == doc["sha256"]
        assert got["values"] == want["values"]

    def test_an_ipv6_management_and_controller_read_from_an_export(self, netbox_list):
        records = _records()
        for d in records["devices"]:
            if d["name"] in ("ovs1", "controller"):
                d["primary_ip4"] = None
                d["primary_ip6"] = {"address": "2001:db8::%x/64" % d["id"]}
        records["ip_addresses"] += [{"address": "2001:db8::e/64", "assigned_object": {"id": 131}}]
        records["devices"][3]["primary_ip6"] = {"address": "2001:db8::e/64"}
        doc = X.parse(_build(records)[0]["bytes"])
        got = V.from_export(doc, "ovs1")
        assert got["ok"], got["error"]
        assert got["values"]["switch.address"] == "2001:db8::e"
        assert got["values"]["controller.address"] == "2001:db8::10"
        assert got["values"]["ports"] == ["eno2", "eno3", "eno4"]   # eno1.100 is management
        r = T.render("ovs", got["values"])
        assert r["ok"] and "tcp:[2001:db8::10]:6653" in r["program"][0]

    def test_a_device_the_export_does_not_hold_is_said(self, netbox_list):
        doc = X.parse(_build()[0]["bytes"])
        got = V.from_export(doc, "nowhere")
        assert not got["ok"] and "holds no device 'nowhere'" in got["error"]
        assert doc["sha256"][:12] in got["error"]


def _with_hosts(records=None):
    """The Lab 9 records with two end hosts tagged ``mercury-end-host`` at the switches' site:
    h1 cabled to ovs1 eno4 (OpenFlow port 3 on DPID 3), IPv4 and IPv6, its MAC in NetBox 4.2's
    shape; h2 with no cable, its MAC in the older field; and a host at another site, not read."""
    records = copy.deepcopy(records or _records())
    tag = [{"slug": X.HOST_TAG, "name": X.HOST_TAG}]
    site = {"id": 1, "slug": "lab"}
    for n, (dev_id, name, at) in enumerate(((901, "h1", site), (902, "h2", site),
                                            (903, "elsewhere", {"id": 9, "slug": "other"}))):
        records["devices"].append({"id": dev_id, "name": name, "role": {"slug": "end-host"},
                                   "status": {"value": "active"}, "site": at, "tags": tag,
                                   "custom_fields": {}, "platform": None})
        iface = {"id": 9100 + n, "device": {"id": dev_id, "name": name}, "name": "eth0",
                 "type": {"value": "1000base-t"}, "enabled": True, "mgmt_only": False,
                 "mode": None, "untagged_vlan": None, "tagged_vlans": [], "tags": [],
                 "custom_fields": {}}
        if name == "h1":
            iface["primary_mac_address"] = {"mac_address": "AA:BB:CC:00:00:01"}
        else:
            iface["mac_address"] = "aa-bb-cc-00-00-02"
        records["interfaces"].append(iface)
    records["ip_addresses"] += [
        {"id": 9201, "address": "192.0.2.101/24", "assigned_object": {"id": 9100}},
        {"id": 9202, "address": "2001:db8::101/64", "assigned_object": {"id": 9100}}]
    records["cables"].append({
        "a_terminations": [{"object": {"device": {"name": "h1"}, "name": "eth0"}}],
        "b_terminations": [{"object": {"device": {"name": "ovs1"}, "name": "eno4"}}],
        "status": {"value": "connected"}, "label": ""})
    return records


class TestEndHosts:
    """C2776: end hosts are the export's own kind, tagged in NetBox, never managed devices."""

    def test_a_tagged_host_at_the_network_s_site_is_a_host_and_not_a_device(self, netbox_list):
        doc = json.loads(_build(_with_hosts())[0]["bytes"])
        hosts = X.hosts_of(doc)
        assert [h["name"] for h in hosts] == ["h1", "h2"], "the other site's host is not read"
        assert "h1" not in [d["name"] for d in doc["body"]["devices"]]
        assert "h1" not in [i["device"] for i in doc["body"]["interfaces"]]
        h1 = hosts[0]["interfaces"][0]
        assert h1 == {"name": "eth0", "mac": "aa:bb:cc:00:00:01",
                      "ip_addresses": ["192.0.2.101/24", "2001:db8::101/64"],
                      "attached": ["ovs1", "eno4"]}
        assert hosts[1]["interfaces"][0]["mac"] == "aa:bb:cc:00:00:02"
        assert hosts[1]["interfaces"][0]["attached"] is None

    def test_each_host_port_is_resolved_to_its_switch_s_dpid_and_port(self, netbox_list):
        doc = json.loads(_build(_with_hosts())[0]["bytes"])
        rows = {r["host"]: r for r in X.host_ports(doc)}
        assert rows["h1"]["switch"] == "ovs1" and rows["h1"]["switch_interface"] == "eno4"
        assert rows["h1"]["dpid"] == 3 and rows["h1"]["port_no"] == 3
        assert rows["h1"]["error"] == "" and rows["h1"]["ip_addresses"] == [
            "192.0.2.101/24", "2001:db8::101/64"]
        assert rows["h2"]["dpid"] is None and "has no cable recorded in NetBox" in \
            rows["h2"]["error"]

    def test_a_host_on_a_switch_with_no_dpid_says_which_value_is_missing(self, netbox_list):
        records = _with_hosts()
        records["cables"][-1]["b_terminations"] = [
            {"object": {"device": {"name": "arista-sw1"}, "name": "Ethernet18"}}]
        doc = json.loads(_build(records)[0]["bytes"])
        h1 = next(r for r in X.host_ports(doc) if r["host"] == "h1")
        assert h1["dpid"] is None and h1["port_no"] == 18
        assert h1["error"] == "arista-sw1 records no openflow.datapath_id"

    def test_a_host_the_list_s_own_filter_also_returns_is_a_host_only(self):
        records = _with_hosts()
        records["hosts"] = [d for d in records["devices"] if d["name"] in ("h1", "h2")]
        body = X.body_of(dict(records, interfaces=records["interfaces"],
                              cables=records["cables"]))
        assert [h["name"] for h in body["hosts"]] == ["h1", "h2"]
        assert not {"h1", "h2", "elsewhere"} & {d["name"] for d in body["devices"]}, \
            "a tagged device is never a managed device, read by either path"

    def test_an_export_from_before_hosts_says_not_recorded_never_none(self, netbox_list):
        doc = json.loads(_build()[0]["bytes"])
        del doc["body"]["hosts"]
        assert X.hosts_of(doc) is None and X.host_ports(doc) == []
        assert X.hosts_of(json.loads(_build()[0]["bytes"])) == []

    def test_a_host_s_change_is_named_in_the_export_s_changes(self, netbox_list):
        old = json.loads(_build()[0]["bytes"])
        new = json.loads(_build(_with_hosts())[0]["bytes"])
        kinds = {k["kind"]: k for k in X.changes(old, new)["kinds"]}
        assert kinds["hosts"]["added"] == ["h1", "h2"] and kinds["hosts"]["count"] == 2


class TestTheFixtureIsMasked:
    def test_every_address_in_the_lab_export_is_a_documentation_address(self, netbox_list):
        doc = json.loads(_build()[0]["bytes"])
        docs = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24",
                                                    "203.0.113.0/24", "2001:db8::/32")]
        found = []

        def walk(node):
            if isinstance(node, dict):
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
            elif isinstance(node, str):
                try:
                    found.append(ipaddress.ip_interface(node).ip)
                except ValueError:
                    pass
        walk(doc["body"])
        assert len(found) >= 8
        assert all(any(a in n for n in docs if n.version == a.version) for a in found), found
