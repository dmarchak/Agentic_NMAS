"""DHCP steering (`modules/sdn/dhcp_steer.py`; Lab 9 Objective 4, C2904; board lab9-sdn B).

**The data.** The Lab 9 NetBox records (tests/fixtures/nsot_export/lab9_records.json, through
the real export, `nsot.export.build` over a fake NetBox's list endpoints), with these minimal
additions, each a value the operator's NetBox steps record (docs/LAB9_NETBOX_STEPS.md sections
8 and 9; docs/LAB9_DHCP_TEST.md, "Before the test"):
- a datapath id on arista-sw1 (1), arista-sw2 (2) and procurve-sw (5), so every switch on a
  path is an OpenFlow switch Mercury can address (the fixture records the two OVS hosts' only);
- the router ``rtr``: its management interface (192.0.2.7), its data interface Gi0/1 with
  198.51.100.1/24 and 2001:db8:100::1/64 and its MAC 00:00:5E:00:53:01 (NetBox 4.2's
  ``primary_mac_address``), cabled to ovs2 eno3 (OpenFlow port 2), and a Service ``dhcp`` UDP 67
  on it; its config context carries section 9's four protected classes;
- two end hosts tagged ``mercury-end-host``: h1 on ovs1 eno4 (port 3), IPv4 and IPv6, and h2 on
  arista-sw2 Ethernet17 (port 17).
The switches' tables are served by `tests.sdn_fakes.FakeRyu` (Ryu 4.34's shapes, writes applied
as the lab's Open vSwitch applied them), read through the real Ryu driver.

What is held:
- **the compile**: the server from the Service (address, prefix, MAC, switch port); one request
  rewrite and two reply drops per edge port; one transit flow per switch on a path; the server's
  switch first; a chosen subset; IPv4 only, IPv6 named as not covered;
- **refusals**, each naming the value missing: no Service, a Service not on UDP 67, no MAC, no
  cable, no datapath id, a host on no switch port, an export from before hosts, no path, an
  IPv6-only server, an unknown switch chosen;
- **the protected set**: this feature's writer is allowed the ``dhcp`` classes; a person's flow
  on UDP 67 is refused naming the class and its owner; a request flow leaving ipv4_dst unset
  meets the management class (why ipv4_dst is matched);
- **the preview** writes nothing and shows every request's REST body; priorities sit above the
  fabric's overlapping flows; **the confirm** writes exactly the previewed flows, records each
  with the owner, keeps them on a second preview, refuses a moved hash with nothing sent, and
  puts back the switches already changed when a later one fails;
- **remove** deletes exactly this feature's cookies by delete-strict, never a wildcard, leaves
  a neighbour with the same match alone, and closes the record of a flow already gone.
"""

import copy
import json

import pytest

from modules.nsot import export as X
from modules.sdn import dhcp_steer as D
from modules.sdn import flow_intent as F
from modules.sdn import flow_ops as O
from modules.sdn.drivers.base import Connection
from modules.sdn.drivers.ryu import RyuDriver
from tests.sdn_fakes import Clock, FakeRyu
from tests.test_openflow_golden import _records, fake_netbox
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

NET = "Default"
BASE = "http://192.0.2.10:8080"
MAC = "00:00:5e:00:53:01"
SITE = {"id": 1, "slug": "lab"}
DPIDS = {"arista-sw1": 1, "arista-sw2": 2, "ovs1": 3, "ovs2": 4, "procurve-sw": 5}
PROTECTED = [
    {"name": "dns", "invariant": "must_reach dns", "owners": ["app:dns_blacklist"],
     "reason": "every host's DNS", "match": {"eth_type": "0x0800", "ip_proto": 17,
                                             "udp_dst": 53}},
    {"name": "dns-ipv6", "invariant": "must_reach dns", "owners": ["app:dns_blacklist"],
     "reason": "every host's DNS over IPv6", "match": {"eth_type": "0x86dd", "ip_proto": 17,
                                                       "udp_dst": 53}},
    {"name": "dhcp", "invariant": "must_reach dhcp", "owners": ["feature:dhcp-unicast"],
     "reason": "every host's lease", "match": {"eth_type": "0x0800", "ip_proto": 17,
                                               "udp_dst": 67}},
    {"name": "dhcp-reply", "invariant": "must_reach dhcp", "owners": ["feature:dhcp-unicast"],
     "reason": "the router's replies", "match": {"eth_type": "0x0800", "ip_proto": 17,
                                                 "udp_src": 67, "udp_dst": 68}}]


def _iface(iid, device, name, **kw):
    out = {"id": iid, "device": device, "name": name, "type": {"value": "1000base-t"},
           "enabled": True, "mgmt_only": False, "mode": None, "untagged_vlan": None,
           "tagged_vlans": [], "tags": [], "custom_fields": {}}
    out.update(kw)
    return out


def _cable(a, b):
    return {"a_terminations": [{"object": {"device": {"name": a[0]}, "name": a[1]}}],
            "b_terminations": [{"object": {"device": {"name": b[0]}, "name": b[1]}}],
            "status": {"value": "connected"}, "label": ""}


def lab9_dhcp_records():
    """The Lab 9 records with the additions the module's docstring names."""
    r = copy.deepcopy(_records())
    for d in r["devices"]:
        if d["name"] in ("arista-sw1", "arista-sw2", "procurve-sw"):
            d["custom_fields"]["openflow_datapath_id"] = f"{DPIDS[d['name']]:016x}"
    rtr = {"id": 17, "name": "rtr"}
    r["devices"].append({
        "id": 17, "name": "rtr", "status": {"value": "active"}, "role": {"slug": "router"},
        "platform": {"slug": "ios"}, "site": SITE, "device_type": {"slug": "isr4321"},
        "primary_ip4": {"address": "192.0.2.7/24"}, "primary_ip6": None, "oob_ip": None,
        "custom_fields": {}, "tags": [],
        "config_context": {"mercury": {"protected_flows": copy.deepcopy(PROTECTED)}}})
    r["interfaces"] += [
        _iface(1701, rtr, "Management0", mgmt_only=True),
        _iface(1702, rtr, "GigabitEthernet0/1",
               primary_mac_address={"mac_address": "00:00:5E:00:53:01"})]
    r["ip_addresses"] += [
        {"id": 1801, "address": "192.0.2.7/24", "assigned_object": {"id": 1701}},
        {"id": 1802, "address": "198.51.100.1/24", "assigned_object": {"id": 1702}},
        {"id": 1803, "address": "2001:db8:100::1/64", "assigned_object": {"id": 1702}}]
    r["services"].append({"device": rtr, "name": "dhcp", "protocol": {"value": "udp"},
                          "ports": [67], "ipaddresses": [{"address": "198.51.100.1/24"}],
                          "tags": []})
    r["cables"].append(_cable(("rtr", "GigabitEthernet0/1"), ("ovs2", "eno3")))
    tag = [{"slug": X.HOST_TAG, "name": X.HOST_TAG}]
    for n, (did, name, mac, addrs, at) in enumerate((
            (901, "h1", "aa:bb:cc:00:00:01", ["198.51.100.101/24", "2001:db8:100::101/64"],
             ("ovs1", "eno4")),
            (902, "h2", "aa:bb:cc:00:00:02", ["198.51.100.102/24"],
             ("arista-sw2", "Ethernet17")))):
        r["devices"].append({"id": did, "name": name, "role": {"slug": "end-host"},
                             "status": {"value": "active"}, "site": SITE, "tags": tag,
                             "custom_fields": {}, "platform": None})
        r["interfaces"].append(_iface(9100 + n, {"id": did, "name": name}, "eth0",
                                      primary_mac_address={"mac_address": mac}))
        r["ip_addresses"] += [{"id": 9200 + 10 * n + k, "address": a,
                               "assigned_object": {"id": 9100 + n}}
                              for k, a in enumerate(addrs)]
        r["cables"].append(_cable((name, "eth0"), at))
    return r


@pytest.fixture
def netbox_list(monkeypatch):
    monkeypatch.setattr("modules.inventory.source_config.load",
                        lambda name: {"source": "netbox", "filters": {}})


def export_of(records=None):
    records = records if records is not None else lab9_dhcp_records()
    get, _calls = fake_netbox(records)
    got = X.build(NET, get=get, version=lambda: records["netbox_version"])
    assert got["ok"], got["error"]
    return X.parse(got["bytes"])


@pytest.fixture
def lab(networks, netbox_list, monkeypatch):  # noqa: F811 - the fixture
    """The network: its committed export (read as `export.read` reads it), and a controller
    holding the five switches' tables, each with the captured table-miss flow."""
    doc = export_of()
    held = {"doc": doc}
    monkeypatch.setattr(X, "read", lambda network, rev="HEAD": {
        "ok": True, "export": held["doc"], "sha256": held["doc"]["sha256"], "error": ""})
    miss = {"table_id": 0, "priority": 0, "cookie": 0, "match": {},
            "actions": [{"type": "OUTPUT", "port": "CONTROLLER"}]}
    fake = FakeRyu(BASE, flows={d: [dict(miss)] for d in DPIDS.values()},
                   dpids=sorted(DPIDS.values()))

    def driver(_network, name):
        return {"ok": True, "error": "", "connection": {"name": name, "own_cookies": [0]},
                "driver": RyuDriver(Connection(BASE), session=fake, clock=Clock(),
                                    sleep=lambda s: None)}

    fake.driver = driver
    fake.held = held
    return fake


def compiled(records=None, **kw):
    return D.compile(export_of(records), **kw)


def flows_of(c, switch, role):
    return [f for f in c["switches"][DPIDS[switch]]["flows"] if f["role"] == role]


def steer(lab, **kw):
    p = D.preview(NET, driver=lab.driver, connection="lab", **kw)
    assert p["ok"], p["error"]
    return p


def confirm(lab, p, kind="steer", **kw):
    return D.confirm(NET, kind, p["hash"], actor="op@example.com", actor_verified="access",
                     cookies=p["cookies"], driver=lab.driver, connection="lab",
                     sleep=lambda s: None, edge_switches=kw.pop("edge_switches", None), **kw)


def ours_on(lab, dpid):
    return [f for f in lab.table[dpid] if F.is_mercury(f.get("cookie"))]


# ───────────────────────────────────────────────────────────────────────────── the compile

class TestTheCompile:
    def test_the_server_is_the_dhcp_service_s_device_its_address_mac_and_port(self, netbox_list):
        c = compiled()
        assert c["ok"], c["error"]
        s = c["server"]
        assert (s["device"], s["address"], s["prefix"], s["interface"], s["mac"]) == (
            "rtr", "198.51.100.1", "198.51.100.0/24", "GigabitEthernet0/1", MAC)
        assert (s["switch"], s["switch_interface"], s["dpid"], s["port_no"]) == (
            "ovs2", "eno3", 4, 2)
        assert s["source"] == "the Service's address" and s["addresses_v6"] == []

    def test_a_service_naming_no_address_falls_back_to_the_primary_and_says_which(
            self, netbox_list):
        r = lab9_dhcp_records()
        for s in r["services"]:
            s["ipaddresses"] = [] if s["name"] == "dhcp" else s["ipaddresses"]
        c = compiled(r)
        assert not c["ok"] and c["error"].startswith(
            "the export records no MAC for rtr Management0 (the interface holding 192.0.2.7)")

    def test_each_edge_port_rewrites_the_broadcast_to_the_server_s_mac_toward_it(self,
                                                                               netbox_list):
        c = compiled()
        (h1,) = flows_of(c, "ovs1", "request")
        assert h1["match"] == {"in_port": 3, "eth_type": 0x0800, "eth_dst": "ff:ff:ff:ff:ff:ff",
                               "ip_proto": 17, "ipv4_dst": "255.255.255.255", "udp_dst": 67}
        assert h1["actions"] == [{"type": "SET_FIELD", "field": "eth_dst", "value": MAC},
                                 {"type": "OUTPUT", "port": 1}], "ovs1 eno2 is toward arista-sw1"
        (h2,) = flows_of(c, "arista-sw2", "request")
        assert h2["match"]["in_port"] == 17 and h2["actions"][-1] == {"type": "OUTPUT",
                                                                      "port": 18}
        assert not any(a.get("field") == "ipv4_dst" for f in (h1, h2) for a in f["actions"]), \
            "ipv4_dst is matched, never rewritten"

    def test_each_switch_on_a_path_gets_one_transit_flow_toward_the_server(self, netbox_list):
        c = compiled()
        transit = {sw: flows_of(c, sw, "transit") for sw in DPIDS if DPIDS[sw] in c["switches"]}
        assert {sw: [f["actions"] for f in fl] for sw, fl in transit.items() if fl} == {
            "arista-sw1": [[{"type": "OUTPUT", "port": 19}]],
            "procurve-sw": [[{"type": "OUTPUT", "port": 3}]],
            "ovs2": [[{"type": "OUTPUT", "port": 2}]]}
        (t,) = transit["ovs2"]
        assert t["match"] == {"eth_type": 0x0800, "eth_dst": MAC, "ip_proto": 17,
                              "ipv4_dst": "255.255.255.255", "udp_dst": 67}

    def test_server_replies_are_dropped_on_every_edge_port_and_never_on_the_server_s(
            self, netbox_list):
        c = compiled()
        drops = {(sw, f["match"]["in_port"], f["match"]["ipv4_dst"])
                 for sw in DPIDS if DPIDS[sw] in c["switches"]
                 for f in flows_of(c, sw, "reply_drop")}
        assert drops == {("ovs1", 3, "255.255.255.255"), ("ovs1", 3, "198.51.100.0/24"),
                         ("arista-sw2", 17, "255.255.255.255"),
                         ("arista-sw2", 17, "198.51.100.0/24")}
        f = flows_of(c, "ovs1", "reply_drop")[0]
        assert f["actions"] == [] and f["match"]["udp_src"] == 67 and \
            f["match"]["udp_dst"] == 68

    def test_the_server_s_switch_is_first_and_the_farthest_edge_last(self, netbox_list):
        c = compiled()
        assert c["order"] == [4, 2, 5, 1, 3], "ovs2, then by hops and name"

    def test_chosen_edge_switches_steer_only_their_hosts(self, netbox_list):
        c = compiled(edge_switches=["arista-sw2"])
        assert c["ok"] and c["chosen"] == ["arista-sw2"]
        assert sorted(c["switches"]) == [2, 4], "arista-sw2's edge and ovs2's transit"
        assert c["edge_switches"] == ["arista-sw2", "ovs1"]

    def test_ipv4_only_and_ipv6_said_by_name(self, netbox_list):
        c = compiled()
        every = [f for s in c["switches"].values() for f in s["flows"]]
        assert every and {f["match"]["eth_type"] for f in every} == {0x0800}
        assert c["ipv6"] == D.IPV6_WORDS and "DHCPv6 (UDP 546 and 547) is not steered" in \
            c["ipv6"]


def _without(records, kind, pred):
    records[kind] = [x for x in records[kind] if not pred(x)]
    return records


def _no_ipv4(records):
    """The router with no IPv4 address anywhere: its Service names none, it has no primary
    IPv4, and its interfaces hold only the IPv6 address."""
    _without(records, "ip_addresses", lambda a: a.get("id") in (1801, 1802))
    for d in records["devices"]:
        if d["name"] == "rtr":
            d["primary_ip4"] = None
    for s in records["services"]:
        if s["name"] == "dhcp":
            s["ipaddresses"] = []
    return records


@pytest.mark.parametrize("edit,said", [
    (lambda r: _without(r, "services", lambda s: s["name"] == "dhcp"),
     "holds no NetBox Service named 'dhcp'"),
    (lambda r: [s.update(protocol={"value": "tcp"}) for s in r["services"]
                if s["name"] == "dhcp"] and r,
     "the Service 'dhcp' on rtr is tcp 67, and a DHCP server listens on UDP 67"),
    (lambda r: [i.pop("primary_mac_address") for i in r["interfaces"]
                if i["id"] == 1702] and r,
     "the export records no MAC for rtr GigabitEthernet0/1"),
    (lambda r: _without(r, "cables", lambda c: c["a_terminations"][0]["object"]["device"]
                        ["name"] == "rtr"),
     "rtr GigabitEthernet0/1 has no cable recorded in the export"),
    (lambda r: [d["custom_fields"].update(openflow_datapath_id=None) for d in r["devices"]
                if d["name"] == "ovs2"] and r,
     "is cabled to ovs2 eno3, and ovs2 records no openflow_datapath_id"),
    (lambda r: _without(r, "cables", lambda c: c["a_terminations"][0]["object"]["device"]
                        ["name"] == "h2"),
     "an end host's switch port is not known, so it cannot be steered: h2 eth0 has no cable "
     "recorded in NetBox"),
    (lambda r: [d["custom_fields"].update(openflow_datapath_id=None) for d in r["devices"]
                if d["name"] in ("arista-sw1", "procurve-sw")] and r,
     "no path from ovs1 to the server's switch ovs2"),
    (lambda r: _no_ipv4(r), "the DHCP server rtr has no IPv4 address in the export"),
])
def test_a_refusal_names_the_value_missing_never_a_guess(netbox_list, edit, said):
    c = compiled(edit(lab9_dhcp_records()))
    assert not c["ok"] and said in c["error"], c["error"]
    assert c["switches"] == {}, "nothing is compiled past a refusal"


def test_an_ipv6_only_server_is_refused_naming_dhcpv6_as_not_covered(netbox_list):
    r = lab9_dhcp_records()
    for s in r["services"]:
        if s["name"] == "dhcp":
            s["ipaddresses"] = [{"address": "2001:db8:100::1/64"}]
    c = compiled(r)
    assert not c["ok"] and "the Service names 2001:db8:100::1" in c["error"]
    assert "DHCPv6 (UDP 546 and 547) is not steered" in c["error"]


def test_an_export_from_before_hosts_is_refused_as_not_recorded(netbox_list):
    doc = export_of()
    del doc["body"]["hosts"]
    c = D.compile(doc)
    assert not c["ok"] and "predates end hosts" in c["error"]


def test_a_switch_chosen_that_is_no_edge_switch_is_refused(netbox_list):
    c = compiled(edge_switches=["procurve-sw"])
    assert not c["ok"] and c["error"] == ("procurve-sw is no edge switch of this network (the "
                                          "edge switches: arista-sw2, ovs1)")


def test_the_export_keeps_an_interface_s_mac_only_where_netbox_records_one(netbox_list):
    doc = export_of()
    by = {(i["device"], i["name"]): i for i in doc["body"]["interfaces"]}
    assert by[("rtr", "GigabitEthernet0/1")]["mac"] == MAC
    assert "mac" not in by[("ovs1", "eno2")], "no key where NetBox records none"


# ───────────────────────────────────────────────────────────────────────────── protected

class TestTheProtectedSet:
    def test_this_feature_may_write_the_dhcp_classes_and_a_person_may_not(self, lab):
        from modules import protected as P

        pset = P.for_network(NET)
        assert pset["state"] == "ok", pset["error"]
        flow = {"table_id": 0, "priority": 400, "cookie": F.new_cookie(), "actions": [],
                "match": {"eth_type": 0x0800, "ip_proto": 17, "ipv4_dst": "255.255.255.255",
                          "udp_dst": 67}}
        changes = [{"do": "add_flow", "flow": flow}]
        assert P.flow_refusal(pset, changes, 3, {}, writer=D.OWNER) == ""
        p = O.plan(NET, {"connection": "lab", "dpid": 3, "changes": changes},
                   driver=lab.driver)
        assert not p["ok"] and "the protected class dhcp" in p["error"], p["error"]
        assert "Its owners are feature:dhcp-unicast, and this write is person's" in p["error"]
        assert lab.writes == []

    def test_a_request_flow_leaving_ipv4_dst_unset_would_meet_the_management_class(self, lab):
        from modules import protected as P

        (req,) = flows_of(D.compile(X.read(NET)["export"]), "ovs1", "request")
        loose = {k: v for k, v in req["match"].items() if k != "ipv4_dst"}
        changes = [{"do": "add_flow", "flow": {"table_id": 0, "priority": 400,
                                               "cookie": F.new_cookie(), "match": loose,
                                               "actions": req["actions"]}}]
        said = P.flow_refusal(P.for_network(NET), changes, 3, {}, writer=D.OWNER)
        assert "the protected class management" in said, said
        changes[0]["flow"]["match"] = req["match"]
        assert P.flow_refusal(P.for_network(NET), changes, 3, {}, writer=D.OWNER) == ""


# ───────────────────────────────────────────────────────────────────────────── preview and confirm

class TestThePreviewAndConfirm:
    def test_the_preview_writes_nothing_and_shows_each_flow_s_rest_body(self, lab):
        p = steer(lab)
        assert lab.writes == [] and F.read(NET)["state"] == "absent"
        assert [pl["dpid"] for pl in p["plans"]] == [4, 2, 5, 1, 3]
        assert p["flows"] == 3 + 2 * 3, "two edge ports (a request and two drops each), 3 transit"
        body = json.loads(next(pl for pl in p["plans"] if pl["dpid"] == 3)["steps"][0]
                          ["request"]["body"])
        assert body["match"]["eth_dst"] == "ff:ff:ff:ff:ff:ff"
        assert {"type": "SET_FIELD", "field": "eth_dst", "value": MAC} in body["actions"]
        assert all(F.is_mercury(c) for c in p["cookies"].values()) and len(p["cookies"]) == 9

    def test_priorities_sit_above_the_fabric_s_overlapping_flow(self, lab):
        lab.table[3].append({"table_id": 0, "priority": 500, "cookie": 0,
                             "match": {"eth_type": 2048},
                             "actions": [{"type": "OUTPUT", "port": "NORMAL"}]})
        lab.table[3].append({"table_id": 0, "priority": 65535, "cookie": 0,
                             "match": {"eth_type": 0x88cc},
                             "actions": [{"type": "OUTPUT", "port": "CONTROLLER"}]})
        p = steer(lab)
        prios = {json.loads(s["request"]["body"])["priority"]
                 for pl in p["plans"] if pl["dpid"] == 3 for s in pl["steps"]}
        assert prios == {510}, "10 above the overlapping 500; LLDP's 65535 is disjoint"
        other = {json.loads(s["request"]["body"])["priority"]
                 for pl in p["plans"] if pl["dpid"] == 4 for s in pl["steps"]}
        assert other == {O.RESPONSE_PRIORITY_FLOOR}

    def test_the_confirm_writes_exactly_the_previewed_flows_and_records_the_owner(self, lab):
        p = steer(lab)
        done = confirm(lab, p)
        assert done["ok"] and done["outcome"] == "verified", done["error"]
        sent = [json.loads(b) for path, b in lab.writes if path == "/stats/flowentry/add"]
        assert sorted(b["cookie"] for b in sent) == sorted(p["cookies"].values())
        assert {path for path, _b in lab.writes} == {"/stats/flowentry/add"}
        rows = [r for r in F.read(NET)["rows"] if r["kind"] == "installed"]
        assert len(rows) == 9 and {r["response"]["owner"] for r in rows} == {D.OWNER}
        assert {r["dpid"] for r in rows} == set(DPIDS.values())
        assert len(ours_on(lab, 3)) == 3 and len(ours_on(lab, 5)) == 1

    def test_a_second_preview_keeps_every_flow_and_sends_nothing(self, lab):
        confirm(lab, steer(lab))
        before = len(lab.writes)
        again = steer(lab)
        assert again["plans"] == [] and again["unchanged"] == 9 and again["flows"] == 0
        done = confirm(lab, again)
        assert done["outcome"] == "verified" and len(lab.writes) == before

    def test_a_moved_hash_is_refused_naming_both_and_nothing_is_sent(self, lab):
        p = steer(lab)
        lab.table[4].append({"table_id": 0, "priority": 800, "cookie": 0,
                             "match": {"eth_type": 2048}, "actions": []})
        done = confirm(lab, p)
        assert done["outcome"] == "refused" and done["at"] == "hash"
        assert f"the preview's hash was {p['hash'][:12]}" in done["error"]
        assert lab.writes == [] and F.read(NET)["state"] == "absent"

    def test_a_switch_that_fails_puts_back_the_switches_already_changed(self, lab):
        p = steer(lab)
        answer = lab._answer

        def refuse_ovs1(method, path, body):
            if method == "POST" and json.loads(body).get("dpid") == 3:
                from tests.sdn_fakes import Response
                lab.writes.append((path, body))
                return Response(500, "", "text/html")
            return answer(method, path, body)

        lab._answer = refuse_ovs1
        done = confirm(lab, p)
        assert done["outcome"] == "rolled_back", done
        assert [r["dpid"] for r in done["rollback"]] == [1, 5, 2, 4]
        assert all(r["outcome"] == "verified" for r in done["rollback"])
        for dpid in DPIDS.values():
            assert ours_on(lab, dpid) == [], dpid
        assert F.intent(NET, "lab")["flows"] == [], "every flow put back is withdrawn"

    def test_a_chosen_switch_s_edge_flows_leave_when_it_is_no_longer_chosen(self, lab):
        confirm(lab, steer(lab))
        p = steer(lab, edge_switches=["arista-sw2"])
        removed = sorted((pl["dpid"], D.role_of(ch["target"])) for pl in p["plans"]
                         for ch in pl["ask"]["changes"] if ch["do"] == "remove_flow")
        assert removed == [(1, "transit"), (3, "reply_drop"), (3, "reply_drop"), (3, "request"),
                           (5, "transit")], "ovs1's three, arista-sw1's and procurve's transit"
        assert not any(ch["do"] == "add_flow" for pl in p["plans"]
                       for ch in pl["ask"]["changes"]), "arista-sw2's and ovs2's are kept"
        assert confirm(lab, p, edge_switches=["arista-sw2"])["outcome"] == "verified"
        assert ours_on(lab, 3) == [] and len(ours_on(lab, 2)) == 3


# ───────────────────────────────────────────────────────────────────────────── remove

class TestRemove:
    def test_remove_deletes_exactly_this_feature_s_cookies_by_delete_strict(self, lab):
        confirm(lab, steer(lab))
        mine = {r["cookie"] for r in F.intent(NET, "lab")["flows"]}
        neighbour = {"table_id": 0, "priority": 999, "cookie": F.new_cookie(),
                     "match": {"in_port": 3, "eth_type": 2048, "ip_proto": 17,
                               "udp_dst": 67}, "actions": []}
        lab.table[3].append(dict(neighbour))
        lab.writes.clear()
        p = D.remove_preview(NET, driver=lab.driver, connection="lab")
        assert p["ok"] and lab.writes == [] and p["flows"] == 9
        done = confirm(lab, p, kind="remove")
        assert done["outcome"] == "verified", done["error"]
        bodies = [json.loads(b) for path, b in lab.writes]
        assert {path for path, _b in lab.writes} == {"/stats/flowentry/delete_strict"}
        assert {b["cookie"] for b in bodies} == mine
        assert all(b["cookie_mask"] == 2 ** 64 - 1 for b in bodies), "never a wildcard"
        assert any(f["cookie"] == neighbour["cookie"] for f in lab.table[3])
        assert F.intent(NET, "lab")["flows"] == []

    def test_a_recorded_flow_already_gone_is_named_and_its_record_closed(self, lab):
        confirm(lab, steer(lab))
        gone = ours_on(lab, 5)[0]
        lab.table[5].remove(gone)
        p = D.remove_preview(NET, driver=lab.driver, connection="lab")
        assert [r["cookie"] for r in p["closing"]] == [gone["cookie"]] and p["flows"] == 8
        done = confirm(lab, p, kind="remove")
        assert done["closed"] == [gone["cookie"]] and F.intent(NET, "lab")["flows"] == []

    def test_nothing_recorded_is_refused_with_nothing_to_remove(self, lab):
        p = D.remove_preview(NET, driver=lab.driver, connection="lab")
        assert not p["ok"] and "no DHCP steering flow recorded on lab" in p["error"]
