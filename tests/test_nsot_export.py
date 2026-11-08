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
        # The list's devices, then its one controller outside the filter, by name.
        assert per["dcim/devices/"] == 2 and per["ipam/vlans/"] == per["ipam/prefixes/"] == 1

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
