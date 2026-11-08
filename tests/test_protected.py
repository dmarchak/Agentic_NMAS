"""B, the protected set (`modules/protected.py`; the SDN platform design revision 6, section 4;
T4 and T18 of its section 15; C2379, C2588, C2589).

- **T4, the objects, on the lab's masked NetBox model** (tests/fixtures/nsot_export/, through the
  real export): derived with no tag, Management1, eno1 and eno1.100, VLAN 100 and the ProCurve's
  port 1, and nothing else; the tag ``mercury-protected`` on an interface, a VLAN or a prefix
  adds what derivation cannot know; an export tagging each protected interface ``openflow``
  binds none of them, each said by name; the ProCurve's instance taking an untagged member of
  its VLAN that carries the management VLAN refuses the render naming the port and both reasons
  (C2588); a trunk carrying the management VLAN tagged ``openflow`` is left out (C2589). IPv6
  beside IPv4.
- **The classes:** the control channel from the ``openflow`` Service, management from the
  prefixes, a Service tagged ``mercury-protected``, the config context's
  ``mercury.protected_flows``; an entry not of its shape makes the set unreadable. A rule meets a
  class by its fields (IPv4 and IPv6 prefixes intersected); A4's DHCP edge flow meets none.
- **T18, every writer that exists:** a protected class planted, and SDN › Flows' preview (a
  person), the closed loop's response (preview and confirm; the AI's classification reaches a
  switch only through it) and the re-apply of a lost response each refuse it, naming the class,
  with nothing sent; the set's hash is bound with the plan's.
- **Where the set comes from:** the committed export; NetBox read now when none is committed; a
  local network says it has none; a committed export that does not verify refuses.
"""
import copy
import json
import os
import re
from html import unescape

import pytest

from modules import protected as P
from modules.nsot import export as X
from modules.platforms import profile as PR
from modules.sdn import closed_loop as CL
from modules.sdn import flow_intent as F
from modules.sdn import flow_ops as FO
from modules.sdn import openflow_templates as T
from modules.sdn import openflow_values as V
from modules.sdn import reapply as RA
from tests.test_openflow_golden import _records, fake_netbox, lab_export  # noqa: F401
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_ops_v2 import form_fields, lab  # noqa: F401 - the fixture

NETWORK = "lab9"


@pytest.fixture
def netbox_list(monkeypatch):
    monkeypatch.setattr("modules.inventory.source_config.load",
                        lambda name: {"source": "netbox", "filters": {"role": "openflow-switch"}})


# --------------------------------------------------------------------------- T4, the objects

class TestTheLabsObjects:
    def test_derived_with_no_tag_and_nothing_else(self, lab_export):  # noqa: F811
        objs = P.derive(lab_export["body"])["objects"]
        got = {d: (sorted(o["interfaces"]), sorted(o["vlans"])) for d, o in objs.items()}
        assert got == {
            "arista-sw1": (["Management1"], []), "arista-sw2": (["Management1"], []),
            "procurve-sw": (["1", "vlan100"], ["100"]),
            "ovs1": (["eno1", "eno1.100"], ["100"]), "ovs2": (["eno1", "eno1.100"], ["100"]),
            "controller": (["enp4s0.100"], ["100"])}
        pc, ovs = objs["procurve-sw"], objs["ovs1"]
        assert pc["interfaces"]["vlan100"] == ("it holds procurve-sw's primary IPv4 address "
                                               "192.0.2.5")
        assert pc["vlans"]["100"].startswith("the VLAN of vlan100 (it holds")
        assert pc["interfaces"]["1"].startswith("it carries the protected VLAN 100 (tagged; ")
        assert ovs["interfaces"]["eno1"].startswith("it is the parent of eno1.100 (it holds "
                                                    "ovs1's primary IPv4 address 192.0.2.3)")
        assert objs["arista-sw1"]["interfaces"]["Management1"] == (
            "it holds arista-sw1's primary IPv4 address 192.0.2.2")

    def test_the_tag_declares_what_derivation_cannot_know(self, lab_export):  # noqa: F811
        body = copy.deepcopy(lab_export["body"])
        for i in body["interfaces"]:
            if (i["device"], i["name"]) == ("arista-sw1", "Ethernet19"):
                i["tags"] = sorted(i["tags"] + [P.TAG])
        for v in body["vlans"]:
            if v["vid"] == 200:
                v["tags"] = [P.TAG]
        objs = P.derive(body)["objects"]
        assert objs["arista-sw1"]["interfaces"]["Ethernet19"] == "it is tagged mercury-protected"
        assert objs["procurve-sw"]["vlans"]["200"] == "VLAN 200 is tagged mercury-protected"
        # VLAN 200 protected: every port carrying it is, untagged or tagged.
        assert objs["procurve-sw"]["interfaces"]["2"].startswith(
            "it carries the protected VLAN 200 (untagged; VLAN 200 is tagged")
        assert "Ethernet18" in objs["arista-sw1"]["interfaces"]

    @pytest.mark.parametrize("address,prefix", [("198.51.100.20/24", "198.51.100.0/24"),
                                                ("2001:db8:5::20/64", "2001:db8:5::/64")])
    def test_an_address_in_a_tagged_prefix_is_protected(self, address, prefix):
        got = P.device_objects({"name": "sw"}, [{"name": "eth3", "ip_addresses": [address]}],
                               prefixes=[{"prefix": prefix, "tags": [P.TAG]}])
        assert got["interfaces"] == {"eth3": f"its address {address.split('/')[0]} is in the "
                                             f"prefix {prefix}, tagged mercury-protected"}

    def test_a_protected_lag_s_members_and_its_bridge(self):
        ifs = [{"name": "Port-Channel1", "type": "lag", "bridge": {"name": "br-mgmt"},
                "ip_addresses": [{"address": "2001:db8::5/64"}]},
               {"name": "Ethernet1", "lag": {"name": "Port-Channel1"}},
               {"name": "Ethernet2"}]
        got = P.device_objects({"name": "sw", "primary_ip6": {"address": "2001:db8::5/64"}}, ifs)
        assert sorted(got["interfaces"]) == ["Ethernet1", "Port-Channel1", "br-mgmt"]
        assert got["interfaces"]["Ethernet1"].startswith("it is a member of the LAG "
                                                         "Port-Channel1 (it holds sw's primary "
                                                         "IPv6 address 2001:db8::5)")


def _tagged_openflow(body, device, name):
    for i in body["interfaces"]:
        if (i["device"], i["name"]) == (device, name):
            i["tags"] = sorted(set(i["tags"]) | {"openflow"})


class TestAnExportTaggingEachOpenFlow:
    """T4: an export that tags every protected interface ``openflow`` binds none of them."""

    @pytest.mark.parametrize("device,name,template,why", [
        ("arista-sw1", "Management1", "arista_eos", "the management interface (mgmt_only)"),
        ("procurve-sw", "1", "aruba_os_switch", "protected (it carries the protected VLAN 100"),
        ("ovs1", "eno1", "ovs", "protected (it is the parent of eno1.100"),
        ("ovs1", "eno1.100", "ovs", "the management interface (primary IP)"),
    ])
    def test_each_is_left_out_and_said(self, lab_export, device, name, template, why):  # noqa: F811
        doc = copy.deepcopy(lab_export)
        _tagged_openflow(doc["body"], device, name)
        got = V.from_export(doc, device)
        assert got["ok"], got["error"]
        assert name not in got["values"]["ports"]
        assert any(e.startswith(f"{name} is {why}") for e in got["values"]["excluded"]), \
            got["values"]["excluded"]
        r = T.render(template, got["values"])
        assert r["ok"], r["error"]
        assert name not in [t["port"] for t in r["takes"]]


class TestTheProCurveInstanceTakesItsVLAN:
    """C2588: an ArubaOS-Switch instance takes every port of its member VLAN."""

    def _values(self, lab_export, vlan, untagged_port_1):  # noqa: F811
        doc = copy.deepcopy(lab_export)
        for i in doc["body"]["interfaces"]:
            if i["device"] != "procurve-sw":
                continue
            if i["name"] in ("2", "3"):
                i["untagged_vlan"] = vlan
            if i["name"] == "1" and untagged_port_1:
                i["untagged_vlan"] = vlan
        doc["body"]["interfaces"].append(dict(
            doc["body"]["interfaces"][0], device="procurve-sw", name="5", untagged_vlan=vlan,
            tagged_vlans=[], tags=[], mgmt_only=False, custom_fields={}, ip_addresses=[],
            mode="access", parent="", lag="", bridge="", type="1000base-t"))
        got = V.from_export(doc, "procurve-sw")
        assert got["ok"], got["error"]
        return got["values"]

    def test_every_port_it_takes_is_named(self, lab_export):  # noqa: F811
        r = T.render("aruba_os_switch", self._values(lab_export, 200, False))
        assert r["ok"], r["error"]
        assert [t["port"] for t in r["takes"]] == ["2", "3", "5"]
        assert r["takes"][2]["why"] == ("untagged in VLAN 200, the instance's member VLAN, so "
                                        "the switch makes it an OpenFlow port though NetBox does "
                                        "not tag it openflow")

    def test_a_protected_member_refuses_naming_both_reasons(self, lab_export):  # noqa: F811
        r = T.render("aruba_os_switch", self._values(lab_export, 1, True))
        assert not r["ok"] and r["program"] == []
        assert r["error"].startswith(
            "procurve-sw's OpenFlow instance would take a protected port, and no write may take "
            "one (B, C2588, C2589): 1 (untagged in VLAN 1, the instance's member VLAN")
        assert "is protected: it carries the protected VLAN 100 (tagged; the VLAN of vlan100" \
            in r["error"]

    def test_the_arista_takes_only_what_it_binds(self, lab_export):  # noqa: F811
        values = V.from_export(lab_export, "arista-sw1")["values"]
        r = T.render("arista_eos", values, PR.select("arista_eos", "4.17.0F"))
        assert r["ok"] and [t["port"] for t in r["takes"]] == ["Ethernet18", "Ethernet19"]

    def test_a_profile_saying_nothing_of_it_refuses(self, monkeypatch):
        from tests.test_openflow_config import V4
        real = PR.value
        monkeypatch.setattr(PR, "value", lambda entry, path: PR.ABSENT
                            if path == "openflow.instance_takes" else real(entry, path))
        r = T.render("ovs", V4)
        assert not r["ok"] and "openflow.instance_takes" in r["error"]

    def test_values_carrying_no_protected_set_refuse(self):
        from tests.test_openflow_config import V4
        bare = {k: v for k, v in V4.items() if k != "protected.objects"}
        r = T.render("ovs", bare)
        assert not r["ok"] and "carry no protected.objects" in r["error"]


class TestTheManagementTrunk:
    """C2589: the physical port carrying the management VLAN (the 2026-11-05 Arista: the address
    on Vlan100, carried by the trunk Ethernet17, Management1 down and unassigned)."""

    @pytest.mark.parametrize("address", ["192.0.2.2/24", "2001:db8::2/64"])
    def test_the_trunk_tagged_openflow_is_left_out_naming_the_vlan(self, address):
        key = "primary_ip6" if ":" in address else "primary_ip4"
        device = {"name": "sw", key: {"address": address},
                  "config_context": {"openflow": {"version": "1.3"}}, "custom_fields": {}}
        ifs = [{"name": "Vlan100", "type": {"value": "virtual"}, "ip_addresses": [
                   {"address": address}]},
               {"name": "Ethernet17", "mode": {"value": "tagged"}, "tagged_vlans": [{"vid": 100}],
                "tags": [{"slug": "openflow"}]},
               {"name": "Ethernet18", "untagged_vlan": {"vid": 200},
                "tags": [{"slug": "openflow"}], "custom_fields": {"openflow_port": 18}}]
        svc = {"name": "openflow", "protocol": {"value": "tcp"}, "ports": [6653],
               "device": {"name": "ctl"}, "ipaddresses": [{"address": "192.0.2.1/24"}]}
        got = V.from_netbox(device, ifs, [svc], {})
        assert got["ok"], got["error"]
        assert got["values"]["ports"] == ["Ethernet18"]
        assert got["values"]["excluded"] == [
            "Ethernet17 is protected (it carries the protected VLAN 100 (tagged; the VLAN of "
            f"Vlan100 (it holds sw's primary IPv{6 if ':' in address else 4} address "
            f"{address.split('/')[0]}))): excluded from OpenFlow"]
        r = T.render("arista_eos", got["values"], PR.select("arista_eos", "4.17.0F"))
        assert r["ok"] and not any("Ethernet17" in line for line in r["program"])

    def test_an_openflow_vlan_the_set_protects_is_refused(self, lab_export):  # noqa: F811
        doc = copy.deepcopy(lab_export)
        for v in doc["body"]["vlans"]:
            if v["vid"] == 200:
                v["tags"] = [P.TAG]
        got = V.from_export(doc, "procurve-sw")
        # Every port carrying VLAN 200 is protected with it, so no OpenFlow port is left.
        assert not got["ok"] and got["values"]["ports"] == []
        assert got["error"].startswith("every interface tagged openflow is protected (2: it "
                                       "carries the protected VLAN 200 (untagged; VLAN 200 is "
                                       "tagged mercury-protected)")


# --------------------------------------------------------------------------- the classes

class TestTheClasses:
    def test_the_lab_s_control_channel_and_management(self, lab_export):  # noqa: F811
        classes = {c["name"]: c for c in P.derive(lab_export["body"])["classes"]}
        assert sorted(classes) == ["control-channel", "management"]
        cc = classes["control-channel"]
        assert cc["invariant"] == "untouchable" and cc["owners"] == []
        assert {"eth_type": 0x0800, "ip_proto": 6, "ipv4_dst": "192.0.2.1/32",
                "tcp_dst": 6653} in cc["match"]
        assert cc["source"] == ("NetBox: the openflow Service on controller (192.0.2.1 TCP "
                                "6653)")
        mg = classes["management"]
        assert {"eth_type": 0x0800, "ipv4_src": "192.0.2.0/24",
                "ipv4_dst": "192.0.2.0/24"} in mg["match"]
        assert {"eth_type": 0x0806, "arp_spa": "192.0.2.0/24",
                "arp_tpa": "192.0.2.0/24"} in mg["match"]

    def test_a_tagged_service_and_a_context_class(self):
        devices = [{"name": "r1", "primary_ip4": "192.0.2.9/24", "primary_ip6": "2001:db8::9/64",
                    "config_context": {"mercury": {"protected_flows": [
                        {"name": "dhcp-broadcast", "reason": "leases",
                         "match": {"eth_type": "0x0800", "ip_proto": 17, "udp_dst": 67,
                                   "ipv4_dst": "255.255.255.255"},
                         "invariant": "must_reach dhcp", "owners": ["feature:dhcp-unicast"]}]}}}]
        services = [{"name": "dns", "parent": "r1", "protocol": "udp", "ports": [53],
                     "ipaddresses": [], "tags": [P.TAG]}]
        classes = {c["name"]: c for c in P.flow_classes(devices, [], services)}
        dns = classes["dns"]
        assert dns["invariant"] == "must_reach dns"
        assert {"eth_type": 0x86DD, "ip_proto": 17, "ipv6_dst": "2001:db8::9/128",
                "udp_dst": 53} in dns["match"]
        assert {"eth_type": 0x0800, "ip_proto": 17, "ipv4_src": "192.0.2.9/32",
                "udp_src": 53} in dns["match"]
        dhcp = classes["dhcp-broadcast"]
        assert dhcp["owners"] == ["feature:dhcp-unicast"] and dhcp["match"] == [
            {"eth_type": 2048, "ip_proto": 17, "udp_dst": 67, "ipv4_dst": "255.255.255.255/32"}]
        assert dhcp["source"] == "NetBox: r1's config context mercury.protected_flows[0]"

    @pytest.mark.parametrize("entry,said", [
        ({"name": "x", "reason": "r", "match": {"vlan_vid": 5}, "invariant": "untouchable"},
         "x's match names vlan_vid"),
        ({"name": "x", "reason": "r", "match": {"udp_dst": 53}, "invariant": "keep"},
         "x's invariant is 'untouchable' or 'must_reach <service>', not 'keep'"),
        ({"name": "x", "match": {"udp_dst": 53}, "invariant": "untouchable"}, "x says no reason"),
        ({"name": "X Y", "reason": "r", "match": {"udp_dst": 53}, "invariant": "untouchable"},
         "a class's name is a slug"),
    ])
    def test_an_entry_not_of_its_shape_is_unreadable(self, entry, said):
        devices = [{"name": "r1", "config_context": {"mercury": {"protected_flows": [entry]}}}]
        with pytest.raises(P.Unreadable, match=re.escape(said)):
            P.flow_classes(devices, [], [])


MGMT = {"name": "management", "invariant": "untouchable", "owners": [], "source": "NetBox: m",
        "reason": "r", "match": [{"eth_type": 0x0800, "ipv4_src": "192.0.2.0/24",
                                  "ipv4_dst": "192.0.2.0/24"},
                                 {"eth_type": 0x86DD, "ipv6_src": "2001:db8::/64",
                                  "ipv6_dst": "2001:db8::/64"}]}


class TestOverlap:
    @pytest.mark.parametrize("match,meets", [
        ({"eth_type": 0x0800, "ipv4_dst": "192.0.2.9"}, True),
        ({"eth_type": 0x86DD, "ipv6_dst": "2001:db8::9"}, True),
        ({"in_port": 3}, True),                          # unset fields meet everything
        ({"eth_type": 0x0800, "ipv4_src": "198.51.100.7"}, False),
        ({"eth_type": 0x86DD, "ipv6_src": "2001:db8:1::7"}, False),
        ({"eth_type": 0x0806}, False),
        # A4's DHCP edge flow: the DISCOVER from any host, broadcast.
        ({"in_port": 1, "eth_type": 0x0800, "ip_proto": 17, "udp_src": 68, "udp_dst": 67,
          "ipv4_dst": "255.255.255.255"}, False),
        ({"ipv4_dst": "192.0.2.9"}, True),               # its EtherType implied
    ])
    def test_a_rule_meets_a_class_by_its_fields(self, match, meets):
        assert bool(P.overlap(match, MGMT)) is meets

    def test_the_overlap_is_said_field_by_field(self):
        assert P.overlap({"eth_type": 2048, "ipv4_dst": "192.0.2.9"}, MGMT) == [
            "eth_type 2048 meets the class's 2048",
            "ipv4_dst 192.0.2.9 meets the class's 192.0.2.0/24",
            "ipv4_src unset in the rule (so every ipv4_src) meets the class's 192.0.2.0/24"]

    def test_a_removal_is_refused_only_for_a_flow_naming_the_class(self):
        assert P.names_class({"eth_type": 0x0800, "ipv4_dst": "192.0.2.9"}, MGMT)
        assert P.names_class({"eth_type": 0x86DD, "ipv6_src": "2001:db8::4"}, MGMT)
        assert not P.names_class({"in_port": 3}, MGMT)
        assert not P.names_class({"eth_type": 0x0800}, MGMT)


def _pset(classes=(MGMT,), objects=None, switches=None, ports=None, state="ok"):
    return {"state": state, "source": "planted", "sha256": "ab" * 32, "error": "unreadable here",
            "classes": list(classes), "objects": objects or {}, "switches": switches or {},
            "ports": ports or {}}


def _add(match, actions=()):
    return [{"do": "add_flow", "flow": {"match": match, "actions": list(actions)}}]


class TestTheFlowGuard:
    def test_a_person_s_flow_meeting_a_class_is_refused_naming_it(self):
        got = P.flow_refusal(_pset(), _add({"eth_type": 0x86DD, "ipv6_dst": "2001:db8::9"}), 1,
                             {}, writer="person")
        assert got.startswith("change 1 adds a flow whose match meets the protected class "
                              "management (untouchable; NetBox: m): ")
        assert "ipv6_dst 2001:db8::9 meets the class's 2001:db8::/64" in got
        assert got.endswith("Its owners are none, and this write is person's: nothing is sent "
                            "(B, C2379)")

    def test_an_owner_writes_its_class(self):
        cls = dict(MGMT, owners=["feature:dhcp-unicast"])
        flow = _add({"eth_type": 0x0800, "ipv4_dst": "192.0.2.9"})
        assert P.flow_refusal(_pset([cls]), flow, 1, {}, writer="feature:dhcp-unicast") == ""
        assert P.flow_refusal(_pset([cls]), flow, 1, {}, writer="person") != ""

    def test_a_flow_naming_a_protected_vlan_or_port_is_refused(self):
        pset = _pset([], objects={"ovs1": {"interfaces": {"eno9": "planted"},
                                           "vlans": {"100": "the VLAN of eno1.100 (x)"}}},
                     switches={"3": "ovs1"}, ports={"ovs1": {"9": "eno9"}})
        got = P.flow_refusal(pset, _add({"eth_type": 0x0800, "ip_proto": 17, "vlan_vid": 0x1064}),
                             3, {}, writer="person")
        assert "vlan_vid 100 is the protected VLAN 100: the VLAN of eno1.100 (x)" in got
        got = P.flow_refusal(pset, _add({"eth_type": 0x0800, "ip_proto": 17},
                                        [{"type": "OUTPUT", "port": 9}]), 3, {}, writer="person")
        assert "an OUTPUT action 9 is ovs1's eno9, protected: planted" in got
        # On a switch NetBox does not name, its VLANs are still compared, with every device's.
        got = P.flow_refusal(pset, _add({"eth_type": 0x0800, "ip_proto": 17, "vlan_vid": 100}),
                             7, {}, writer="person")
        assert "vlan_vid 100 is the protected VLAN 100" in got and "on ovs1" in got
        assert P.switch_note(pset, 7).startswith("switch 7 is no device NetBox names")

    def test_an_unreadable_set_refuses_every_flow(self):
        got = P.flow_refusal(_pset(state="unreadable"), _add({"eth_type": 0x0800,
                                                              "ip_proto": 17}), 1, {},
                             writer="person")
        assert got == ("the protected set could not be read (unreadable here), so no flow can "
                       "be checked against it: nothing is sent")

    def test_the_control_channel_is_asked_first_for_every_writer(self):
        got = P.flow_refusal(_pset([]), _add({"eth_type": 0x88CC}), 1, {}, writer="person")
        assert got.endswith("No flow may cover it, whoever writes it (this is person's; C2022, "
                            "C2379)")


# --------------------------------------------------------------------------- T18, the writers

@pytest.fixture
def planted(monkeypatch):
    """A protected management class over 192.0.2.0/24 and 2001:db8::/64 planted as the
    network's set (as NetBox would give it), the guard's own code unchanged."""
    got = {"set": _pset()}
    monkeypatch.setattr(P, "for_network", lambda network: got["set"])
    return got


def test_sdn_flows_preview_refuses_a_planted_class_naming_it(lab, planted):  # noqa: F811
    r = lab["client"].post("/v2/sdn/flow/preview", data={
        "list": "Default", "do": "add", "connection": "lab-controller", "dpid": "0000000000000001",
        "priority": "250", "match": "eth_type=0x0800, ipv4_dst=192.0.2.9", "actions": "drop"})
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 409
    assert "meets the protected class management (untouchable; NetBox: m)" in html
    assert lab["fake"].writes == []


def test_sdn_flows_applies_a_flow_meeting_none(lab, planted):  # noqa: F811
    """A4's DHCP edge flow (S4 prep: each ask previews with no refusal) is previewed and, once
    confirmed, installed: B refuses only what meets a class."""
    c = lab["client"]
    r = c.post("/v2/sdn/flow/preview", data={
        "list": "Default", "do": "add", "connection": "lab-controller", "dpid": "0000000000000001",
        "priority": "250", "match": "in_port=1, eth_type=0x0800, ip_proto=17, udp_src=68, "
                                    "udp_dst=67, ipv4_dst=255.255.255.255", "actions": "drop"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200, unescape(html)[:400]
    done = c.post("/v2/sdn/flow/confirm", data=form_fields(html))
    assert done.status_code == 200, unescape(done.get_data(as_text=True))[:400]
    (body,) = [b for path, b in lab["fake"].writes if path == "/stats/flowentry/add"]
    assert (json.loads(body) if isinstance(body, str) else body)["match"]["udp_dst"] == 67


def _detection(source):
    return {"key": f"k-{source}", "rule": "scan", "title": "SDN scan", "network": "Default",
            "connection": "lab-controller", "dpid": 1, "dpid_hex": "0000000000000001",
            "source": source, "targets": ["192.0.2.2"], "confidence": "high",
            "words": f"{source} reached 25 distinct destination ports",
            "at": "2026-10-28T00:50:00Z"}


def test_a_response_is_refused_at_its_preview_and_its_confirm(lab, planted):  # noqa: F811
    planted["set"] = _pset([])
    preview = CL.respond_to_threat("Default", _detection("192.0.2.1"), "drop_source")
    assert preview["ok"], preview["error"]
    planted["set"] = _pset()
    again = CL.respond_to_threat("Default", _detection("192.0.2.1"), "drop_source")
    assert not again["ok"] and "protected class management" in again["error"]
    got = CL.respond_to_threat("Default", None, "drop_source", confirm={
        "ask": preview["ask"], "hash": preview["plan"]["hash"]}, actor="op@example.com",
        actor_verified="access", sleep=lambda s: None)
    assert got["outcome"] == "refused" and got["at"] == "plan"
    assert "protected class management" in got["error"] and lab["fake"].writes == []


def test_the_re_apply_of_a_lost_response_is_refused(lab, planted):  # noqa: F811
    import time
    planted["set"] = _pset([])
    preview = CL.respond_to_threat("Default", _detection("192.0.2.1"), "drop_source")
    done = CL.respond_to_threat("Default", None, "drop_source", confirm={
        "ask": preview["ask"], "hash": preview["plan"]["hash"]}, actor="op@example.com",
        actor_verified="access", sleep=lambda s: None)
    assert done["outcome"] == "verified", done["error"]
    cookie = json.loads(done["sent"][0]["request"]["body"])["cookie"]
    lab["fake"].table[1] = [f for f in lab["fake"].table[1] if f["cookie"] != cookie]
    writes = list(lab["fake"].writes)
    assert RA.preview("Default", "lab-controller", "0000000000000001", done["id"],
                      now=time.time())["ok"]
    planted["set"] = _pset()
    got = RA.preview("Default", "lab-controller", "0000000000000001", done["id"],
                     now=time.time())
    assert not got["ok"] and "protected class management" in got["error"]
    assert lab["fake"].writes == writes


def test_the_set_s_hash_is_bound_with_the_plan(lab, planted):  # noqa: F811
    ask = {"connection": "lab-controller", "dpid": 1, "changes": _add(
        {"eth_type": 0x0800, "ip_proto": 17, "ipv4_src": "198.51.100.7"})}
    ask["changes"][0]["flow"].update(table_id=0, priority=250, cookie=F.new_cookie())
    p = FO.plan("Default", ask)
    assert p["ok"], p["error"]
    assert p["protected"] == {"state": "ok", "source": "planted", "sha256": "ab" * 32}
    planted["set"] = dict(_pset(), sha256="cd" * 32)
    got = FO.apply("Default", ask, p["hash"], actor="op@example.com", actor_verified="access",
                   sleep=lambda s: None)
    assert got["outcome"] == "refused" and "the plan made now is" in got["error"]
    assert lab["fake"].writes == []


# --------------------------------------------------------------------------- where it comes from

@pytest.fixture
def repo(tmp_path, monkeypatch, netbox_list):
    list_dir = tmp_path / NETWORK
    os.makedirs(list_dir / "config_repo", exist_ok=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.list_data_path", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    return list_dir


class _Session:
    def get(self, url, timeout=None):
        class R:
            def raise_for_status(self):
                return None

            def json(self):
                return {"netbox-version": "4.2.6"}
        return R()


@pytest.fixture
def netbox_now(monkeypatch):
    get, calls = fake_netbox(_records())
    monkeypatch.setattr("modules.netbox_client._nb_ready",
                        lambda: (True, "", _Session(), "http://netbox.invalid"))
    monkeypatch.setattr("modules.netbox_client._nb_get",
                        lambda session, base, path, **params: get(path, **params))
    return calls


class TestWhereTheSetComesFrom:
    def test_the_committed_export_first(self, repo, netbox_now):
        built = X.build(NETWORK)
        assert X.write(NETWORK, "op@example.invalid", "access", data=built["bytes"])["ok"]
        netbox_now.clear()
        got = P.for_network(NETWORK)
        assert got["state"] == "ok" and got["sha256"] == built["sha256"]
        assert got["source"] == f"the committed NSOT export {built['sha256'][:12]}"
        assert netbox_now == [], "a committed export is read with no NetBox read"

    def test_netbox_now_when_none_is_committed(self, repo, netbox_now):
        got = P.for_network(NETWORK)
        assert got["state"] == "ok" and "NetBox read now" in got["source"]
        assert "no export is committed" in got["source"] and netbox_now

    def test_a_committed_export_that_does_not_verify_refuses(self, repo, netbox_now,
                                                             monkeypatch):
        monkeypatch.setattr(X, "read", lambda network: {
            "ok": False, "export": None, "sha256": "", "error": "edited after it was built"})
        got = P.for_network(NETWORK)
        assert got["state"] == "unreadable" and "edited after it was built" in got["error"]

    def test_netbox_unreadable_with_nothing_committed_refuses(self, repo, monkeypatch):
        monkeypatch.setattr("modules.netbox_client._nb_ready",
                            lambda: (False, "no URL set", None, ""))
        got = P.for_network(NETWORK)
        assert got["state"] == "unreadable" and "no URL set" in got["error"]

    def test_a_local_network_says_it_has_none(self, monkeypatch):
        monkeypatch.setattr("modules.inventory.source_config.load",
                            lambda name: {"source": "local"})
        got = P.for_network("Default")
        assert got["state"] == "none" and "not NetBox" in got["source"]
        assert P.switch_note(got, 1) == got["source"]
