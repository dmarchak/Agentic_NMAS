"""The NSoT-driven OpenFlow configuration (docs/LAB9_OPENFLOW.md): the vendor templates and
their citations, the values read from NetBox, the draft-or-confirmed rule, the Open vSwitch
session's shapes, and OVS's operation end to end (the operator's decision 7: OVS first).

The NetBox records are shaped as NetBox 4's REST API returns them (a device with
``config_context`` and ``custom_fields``, interfaces with ``tags`` and ``untagged_vlan``, an
``ipam/services`` Service), typed, not captured: no lab NetBox holds the OpenFlow model yet.
The OVS server is a fake that keeps a bridge's columns and answers `ovs-vsctl`'s reads in its
printed forms (ovs-vsctl(8)); the controller is a fake driver's switch list. Netmiko is faked at
`ConnectHandler` where the session guard itself is under test, so `open_ssh` runs for real.
"""

import os

import pytest

from modules import connection as C
from modules import discovery
from modules.nsot import device_ops as D
from modules.sdn import openflow_templates as T
from modules.sdn import openflow_values as V
from modules.sdn import ovs
from modules.sdn import ovs_config as O

LIST = "Lab"
V4 = {"switch.name": "srv1", "switch.address": "192.0.2.21", "controller.address": "192.0.2.10",
      "controller.port": "6653", "openflow.version": "1.3", "openflow.transport": "tcp",
      "openflow.fail_mode": "secure", "openflow.instance": "br0", "openflow.datapath_id": "",
      "openflow.vlan": "20", "mgmt.vlan": "10", "ports": ["eth1", "eth2"],
      "port.openflow_port": {"eth1": "1", "eth2": "2"}, "openflow.connection": "",
      # B's two values, as `from_netbox` gives them over IFACES (modules/protected.py).
      "protected.objects": {"interfaces": {"eth0": "it holds srv1's primary IPv4 address "
                                                   "192.0.2.21"}, "vlans": {}},
      "openflow.vlan_members": {"eth1": "untagged", "eth2": "untagged"}}
V6 = dict(V4, **{"switch.address": "2001:db8::21", "controller.address": "2001:db8::10"})
PROGRAM_V4 = ("sudo -n ovs-vsctl --may-exist add-br br0 -- set bridge br0 protocols=OpenFlow13"
              " -- set-fail-mode br0 secure -- set-controller br0 tcp:192.0.2.10:6653"
              " -- --may-exist add-port br0 eth1 -- --may-exist add-port br0 eth2"
              " -- set interface eth1 ofport_request=1 -- set interface eth2 ofport_request=2")


# --------------------------------------------------------------------------- the templates

class TestEveryTemplateCitesItsVendor:
    def test_mercury_ships_each_family(self):
        assert T.names() == ["arista_eos", "aruba_aoscx", "aruba_os_switch", "hp_comware", "ovs"]

    @pytest.mark.parametrize("name", T.names())
    def test_no_template_has_a_problem_and_every_line_cites(self, name):
        t = T.load(name)
        assert T.problems(t) == []
        for line in t["lines"]:
            assert line["cite"] and all(k in t["citations"] for k in line["cite"])
            assert line["why"].strip()
        documents = {k: c for k, c in t["citations"].items() if "measured" not in c}
        for c in documents.values():
            assert c["url"].startswith("https://") and c["read"] == "2026-11-05"

    @pytest.mark.parametrize("name", T.names())
    def test_a_measured_citation_names_its_row_and_evidence_that_exist(self, name):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "docs", "OPEN_FINDINGS.md"), encoding="utf-8") as fh:
            register = fh.read()
        for key, c in T.load(name)["citations"].items():
            if "measured" in c:
                assert f"| {c['measured']} |" in register, key
                assert os.path.isfile(os.path.join(root, c["evidence"])), (key, c["evidence"])

    def test_a_line_that_does_not_say_why_or_lists_versions_is_a_problem(self):
        t = T.load("arista_eos")
        t["lines"][0]["why"] = " "
        t["versions"] = ["1.0"]
        t["lines"][1]["when"] = "profile.openflow.versions ~ 1.3"
        t["citations"]["eos-lldp-measured"].pop("evidence")
        got = T.problems(t)
        assert any("does not say why" in p for p in got), got
        assert any("lists its own OpenFlow versions" in p for p in got), got
        assert any("is not <name>" in p for p in got), got
        assert any("eos-lldp-measured" in p and "evidence" in p for p in got), got

    def test_a_line_with_no_citation_or_an_undefined_one_is_a_problem(self):
        t = T.load("ovs")
        t["lines"].append({"text": "del-br br0"})
        t["lines"].append({"text": "list-br", "cite": ["nowhere"]})
        del t["citations"]["vsctl-add-br"]["url"]
        got = T.problems(t)
        assert any("cites no vendor document" in p for p in got)
        assert any("'nowhere'" in p for p in got)
        assert any("vsctl-add-br" in p and "url" in p for p in got)

    def test_a_template_with_a_problem_is_never_rendered(self, monkeypatch):
        t = T.load("ovs")
        t["lines"][0]["cite"] = []
        monkeypatch.setattr(T, "load", lambda name: t)
        r = T.render("ovs", V4)
        assert not r["ok"] and "cites no vendor document" in r["error"] and r["program"] == []

    def test_each_template_carries_its_own_status_draft_by_default(self, net):
        for name in T.names():
            assert T.status(LIST, name)["status"] == T.DRAFT


class TestRenderingFromValues:
    def test_ovs_is_one_transaction_ipv4(self):
        r = T.render("ovs", V4)
        assert r["ok"] and r["program"] == [PROGRAM_V4]
        assert all(x["cite"] for x in r["lines"])

    def test_ovs_brackets_an_ipv6_controller(self):
        r = T.render("ovs", V6)
        assert "set-controller br0 tcp:[2001:db8::10]:6653" in r["program"][0]

    def test_a_datapath_id_is_set_only_when_given(self):
        r = T.render("ovs", dict(V4, **{"openflow.datapath_id": "00000000000000a1"}))
        assert "set bridge br0 other-config:datapath-id=00000000000000a1" in r["program"][0]
        assert "datapath-id" not in T.render("ovs", V4)["program"][0]

    @pytest.mark.parametrize("key", ["controller.port", "openflow.instance", "ports"])
    def test_a_missing_value_refuses_naming_it_and_where(self, key):
        r = T.render("ovs", dict(V4, **{key: [] if key == "ports" else ""}))
        assert not r["ok"] and r["program"] == [] and key in r["missing"]
        assert key in r["error"] and V.WHERE[key] in r["error"]

    def test_eos_417_renders_at_1_3_by_its_profile_m2(self):
        """M2 (C2598): EOS 4.17 offers 1.0 and 1.3 (the profile), so 1.3 renders; a version the
        profile does not offer is refused naming both."""
        r = T.render("arista_eos", V4)
        assert r["ok"], r["error"]
        assert "   controller tcp:192.0.2.10:6653" in r["program"]
        assert "   bind interface eth1" in r["program"] and r["profile"] == "arista_eos"
        bad = T.render("arista_eos", dict(V4, **{"openflow.version": "1.4"}))
        assert not bad["ok"] and "offers OpenFlow 1.0, 1.3" in bad["error"]
        assert "version 1.4" in bad["error"] and bad["program"] == []
        cw = T.render("hp_comware", dict(V4, **{"openflow.version": "1.0",
                                                "openflow.instance": "1"}))
        assert not cw["ok"] and "offers OpenFlow 1.3" in cw["error"]

    def test_eos_refuses_an_ipv6_controller_naming_it(self):
        r = T.render("arista_eos", dict(V6, **{"openflow.version": "1.0"}))
        assert not r["ok"] and "2001:db8::10" in r["error"] and "IPv6" in r["error"]

    def test_arubaos_switch_sets_1_3_on_its_vlans(self):
        """`version 1.3`, as the lab's K.16.02 switch runs it (it offers 1.0 and 1.3, the
        profile's versions), so a hand-built switch plans as no change."""
        r = T.render("aruba_os_switch", V4)
        assert r["ok"]
        assert ("openflow controller-id 1 ip 192.0.2.10 port 6653 controller-interface vlan 10"
                in r["program"])
        assert "openflow instance br0 member vlan 20" in r["program"]
        assert "openflow instance br0 version 1.3" in r["program"]
        assert "openflow instance br0 connection-interruption-mode fail-secure" in r["program"]

    def test_arubaos_switch_puts_each_port_in_the_member_vlan_with_lldp_off(self):
        """C2600 and the member VLAN: each OpenFlow port untagged in it, LLDP off on each,
        both before the instance is enabled."""
        r = T.render("aruba_os_switch", V4)
        p = r["program"]
        for port in ("eth1", "eth2"):
            assert f"vlan 20 untagged {port}" in p and f"lldp admin-status {port} disable" in p
            assert p.index(f"vlan 20 untagged {port}") < p.index("openflow instance br0 enable")
        assert p.index("lldp admin-status eth2 disable") < p.index("openflow enable")

    def test_eos_turns_lldp_off_on_each_bound_port(self):
        """C2600: under each bound interface, no lldp transmit and no lldp receive."""
        p = T.render("arista_eos", V4)["program"]
        for port in ("eth1", "eth2"):
            i = p.index(f"interface {port}")
            assert p[i + 1:i + 3] == ["   no lldp transmit", "   no lldp receive"]
        assert p.index("interface eth2") < p.index("openflow")

    def test_eos_restarts_its_agent_only_on_a_bind_change(self):
        """C2599: `shutdown` before `no shutdown` when the bound ports differ from the
        switch's, never otherwise; with no state given, left out and said."""
        changed = T.render("arista_eos", dict(V4, **{"state.bind_changed": True}))["program"]
        assert changed[-2:] == ["   shutdown", "   no shutdown"]
        same = T.render("arista_eos", dict(V4, **{"state.bind_changed": False}))
        assert "   shutdown" not in same["program"] and same["program"][-1] == "   no shutdown"
        unknown = T.render("arista_eos", V4)
        assert "   shutdown" not in unknown["program"]
        assert any("'shutdown'" in n and "state" in n for n in unknown["notes"])

    def test_every_rendered_line_carries_its_why_with_the_port_named(self):
        r = T.render("ovs", V4)
        whys = {x["text"]: x["why"] for x in r["lines"]}
        assert "eth1 is OpenFlow port 1" in whys["set interface eth1 ofport_request=1"]
        assert all(x["why"] and "{" not in x["why"] for x in r["lines"])

    def test_ovs_requests_netboxs_port_numbers_and_refuses_a_port_without_one(self):
        """C2603: OVS numbers ports by add order, so NetBox's number is requested; a port
        with none is refused naming it and where NetBox holds it."""
        r = T.render("ovs", V4)
        assert "set interface eth2 ofport_request=2" in r["program"][0]
        bad = T.render("ovs", dict(V4, **{"port.openflow_port": {"eth1": "1"}}))
        assert not bad["ok"] and "port.openflow_port" in bad["missing"]
        assert V.WHERE["port.openflow_port"] in bad["error"]

    @pytest.mark.parametrize("name,port,number,words", [
        ("arista_eos", "Ethernet18", "19", "Ethernet18's openflow_port is 19"),
        ("aruba_os_switch", "3", "2", "3's openflow_port is 2")])
    def test_a_number_unlike_the_platforms_own_is_refused(self, name, port, number, words):
        r = T.render(name, dict(V4, ports=[port], **{"port.openflow_port": {port: number}}))
        assert not r["ok"] and words in r["error"] and r["program"] == []
        ok = T.render(name, dict(V4, ports=[port], **{"port.openflow_port": {port: port[-2:]
                                                                             .lstrip("t")}}))
        assert ok["ok"], ok["error"]

    def test_a_template_reading_a_key_its_profile_lacks_is_refused(self, monkeypatch):
        from modules.platforms import profile as P
        doc = P.load("arista_eos")
        doc["entries"][0]["openflow"].pop("bind_change_requires")
        monkeypatch.setattr(P, "load", lambda name: doc)
        r = T.render("arista_eos", dict(V4, **{"state.bind_changed": True}))
        assert not r["ok"] and "profile.openflow.bind_change_requires" in r["error"]

    def test_a_selected_entry_is_used_and_a_wrong_platforms_is_refused(self):
        from modules.platforms import profile as P
        sel = P.select("arista_eos", "4.17.0F")
        assert T.render("arista_eos", V4, selected=sel)["ok"]
        wrong = T.render("arista_eos", V4, selected=P.select("ovs_linux", "3.3.4"))
        assert not wrong["ok"] and "ovs_linux" in wrong["error"] and "arista_eos" in wrong["error"]
        none = T.render("arista_eos", V4, selected=P.select("arista_eos", "4.31.0F"))
        assert not none["ok"] and "4.31.0F" in none["error"]

    def test_comware_takes_an_ipv6_controller_and_a_numbered_instance(self):
        r = T.render("hp_comware", dict(V6, **{"openflow.instance": "1"}))
        assert r["ok"] and " controller 1 address ipv6 2001:db8::10 port 6653" in r["program"]
        v4 = T.render("hp_comware", dict(V4, **{"openflow.instance": "1"}))
        assert " controller 1 address ip 192.0.2.10 port 6653" in v4["program"]
        bad = T.render("hp_comware", V4)
        assert not bad["ok"] and "'br0'" in bad["error"] and "number" in bad["error"]

    def test_aoscx_support_is_unknown_and_nothing_renders(self):
        r = T.render("aruba_aoscx", V4)
        assert not r["ok"] and "UNKNOWN" in r["error"] and r["program"] == []


# --------------------------------------------------------------------------- NetBox's values

def _device(ip4="192.0.2.21/24", ip6=None, ctx=None, cf=None):
    return {"id": 7, "name": "srv1",
            "primary_ip4": {"address": ip4} if ip4 else None,
            "primary_ip6": {"address": ip6} if ip6 else None,
            "config_context": {"openflow": ctx if ctx is not None else {"version": "1.3"}},
            "custom_fields": cf if cf is not None else {"openflow_instance": "br0"}}


def _iface(name, tag=True, vid=20, addr=None, num=None):
    return {"name": name, "tags": [{"slug": "openflow"}] if tag else [],
            "untagged_vlan": {"vid": vid} if vid else None,
            "ip_addresses": [{"address": addr}] if addr else [],
            "custom_fields": {"openflow_port": num}}


def _service(parent="ctl1", port=6653, addr=None):
    return {"name": "openflow", "protocol": {"value": "tcp"}, "ports": [port],
            "device": {"name": parent}, "ipaddresses": [{"address": addr}] if addr else []}


IFACES = [_iface("eth0", tag=False, vid=10, addr="192.0.2.21/24"), _iface("eth1"), _iface("eth2")]
CTL = {"ctl1": {"name": "ctl1", "primary_ip4": {"address": "192.0.2.10/24"}}}


class TestValuesFromNetBox:
    def test_every_value_comes_from_its_netbox_place_ipv4(self):
        got = V.from_netbox(_device(), IFACES, [_service()], CTL)
        assert got["ok"], got["error"]
        v = got["values"]
        assert (v["switch.address"], v["controller.address"], v["controller.port"]) == \
            ("192.0.2.21", "192.0.2.10", "6653")
        assert v["ports"] == ["eth1", "eth2"] and v["openflow.vlan"] == "20"
        assert v["mgmt.vlan"] == "10" and v["openflow.instance"] == "br0"
        assert any("transport tcp" in d for d in got["defaults"])

    def test_ipv6_management_and_a_service_address_of_its_own(self):
        got = V.from_netbox(_device(ip4=None, ip6="2001:db8::21/64"),
                            [_iface("eth1")], [_service(addr="2001:db8::10/64")], {})
        assert got["ok"], got["error"]
        assert got["values"]["switch.address"] == "2001:db8::21"
        assert got["values"]["controller.address"] == "2001:db8::10"

    def test_two_controllers_need_the_config_context_to_name_one(self):
        two = [_service("ctl1"), _service("ctl2")]
        got = V.from_netbox(_device(), IFACES, two, CTL)
        assert not got["ok"] and "ctl1, ctl2" in got["error"]
        named = V.from_netbox(_device(ctx={"controller": "ctl1"}), IFACES, two, CTL)
        assert named["ok"] and named["values"]["controller.name"] == "ctl1"

    @pytest.mark.parametrize("change,words", [
        ({"svc_port": 70000}, "not 1 to 65535"),
        ({"cf": {"openflow_instance": "br0", "openflow_datapath_id": "0000"}}, "16 hex"),
        ({"cf": {"openflow_instance": "br0;reboot"}}, "one name token"),
        ({"ctx": {"version": "1.5"}}, "not 1.0 or 1.3"),
        ({"ctx": {"fail_mode": "open"}}, "secure or standalone")])
    def test_a_value_not_of_its_shape_is_refused_naming_it(self, change, words):
        got = V.from_netbox(_device(ctx=change.get("ctx"), cf=change.get("cf")), IFACES,
                            [_service(port=change.get("svc_port", 6653))], CTL)
        assert not got["ok"] and words in got["error"]

    def test_openflow_ports_on_two_vlans_are_refused(self):
        got = V.from_netbox(_device(), [_iface("eth1", vid=20), _iface("eth2", vid=30)],
                            [_service()], CTL)
        assert not got["ok"] and "more than one untagged VLAN" in got["error"]

    def test_each_ports_openflow_number_is_read_from_its_custom_field(self):
        """C2603: `openflow_port` is read; a port without one is absent, not invented."""
        got = V.from_netbox(_device(), [_iface("eth1", num=7), _iface("eth2")], [_service()],
                            CTL)
        assert got["ok"], got["error"]
        assert got["values"]["port.openflow_port"] == {"eth1": "7"}

    @pytest.mark.parametrize("nums,words", [
        ((0, 2), "eth1's openflow_port '0' is not 1 to 65279"),
        ((65280, 2), "not 1 to 65279"),
        ((3, 3), "openflow_port 3 is given to eth1, eth2")])
    def test_a_port_number_not_of_its_shape_or_given_twice_is_refused(self, nums, words):
        got = V.from_netbox(_device(), [_iface("eth1", num=nums[0]), _iface("eth2", num=nums[1])],
                            [_service()], CTL)
        assert not got["ok"] and words in got["error"], got["error"]


def _mgmt(name="eth0", vid=10, addr="192.0.2.21/24", mgmt_only=False, tag=True):
    return dict(_iface(name, tag=tag, vid=vid, addr=addr), mgmt_only=mgmt_only)


class TestManagementIsNeverOpenFlow:
    """Lab 9's management network is separate and non-OpenFlow (the operator, 2026-11-05)."""

    @pytest.mark.parametrize("device,iface,why", [
        (_device(), _mgmt("mgmt0", addr=None, mgmt_only=True), "mgmt_only"),
        (_device(), _mgmt("eth0"), "primary IP"),
        (_device(ip4=None, ip6="2001:db8::21/64"), _mgmt("eth0", addr="2001:db8::21/64"),
         "primary IP"),
        (dict(_device(), oob_ip={"address": "192.0.2.121/24"}),
         _mgmt("oob1", addr="192.0.2.121/24"), "OOB IP")],
        ids=("mgmt_only", "primary-ipv4", "primary-ipv6", "oob_ip"))
    def test_a_tagged_management_interface_is_excluded_and_said(self, device, iface, why):
        got = V.from_netbox(device, [iface, _iface("eth1"), _iface("eth2")], [_service()], CTL)
        assert got["ok"], got["error"]
        assert iface["name"] not in got["values"]["ports"]
        assert got["values"]["ports"] == ["eth1", "eth2"]
        assert got["values"]["excluded"] == [
            f"{iface['name']} is the management interface ({why}): excluded from OpenFlow"]

    def test_the_openflow_vlan_may_not_be_the_management_vlan(self):
        got = V.from_netbox(_device(), [_mgmt("eth0", tag=False, vid=20), _iface("eth1", vid=20)],
                            [_service()], CTL)
        assert not got["ok"]
        assert "OpenFlow VLAN 20 is the management VLAN 20" in got["error"]

    def test_a_device_tagging_only_management_interfaces_is_refused_naming_them(self):
        got = V.from_netbox(dict(_device(), oob_ip={"address": "192.0.2.121/24"}),
                            [_mgmt("eth0"), _mgmt("oob1", vid=11, addr="192.0.2.121/24")],
                            [_service()], CTL)
        assert not got["ok"] and got["values"]["ports"] == []
        assert "eth0: primary IP" in got["error"] and "oob1: OOB IP" in got["error"]

    def test_the_rendered_vendor_lines_never_bind_it_and_say_so(self):
        got = V.from_netbox(_device(), [_mgmt("Ethernet48"), _iface("Ethernet1")],
                            [_service()], CTL)
        r = T.render("arista_eos", dict(got["values"], **{"openflow.version": "1.0"}))
        assert r["ok"] and "   bind interface Ethernet1" in r["program"]
        assert not any("Ethernet48" in line for line in r["program"])
        assert r["excluded"] == ["Ethernet48 is the management interface (primary IP): "
                                 "excluded from OpenFlow"]


# --------------------------------------------------------------------------- OVS's session

class TestOvsShapes:
    @pytest.mark.parametrize("command", [
        "ovs-vsctl --version", "sudo -n ovs-vsctl show", "sudo -n ovs-vsctl list-br",
        "sudo -n ovs-vsctl get-controller br0", "sudo -n ovs-vsctl list-ports br0",
        "sudo -n ovs-vsctl get bridge br0 protocols",
        "sudo -n ovs-vsctl --if-exists get bridge br0 other-config:datapath-id",
        "sudo -n ovs-vsctl get interface eth1 ofport_request",
        "sudo -n ovs-vsctl get interface eth1 ofport",
        "sudo -n ovs-ofctl -O OpenFlow13 show br0"])
    def test_each_ovs_read_is_allowed(self, command):
        assert ovs.read_refusal(command) == ""

    @pytest.mark.parametrize("command", [
        "sudo -n ovs-vsctl show; reboot", "sudo ovs-vsctl show", "sudo -s",
        "sudo -n ovs-vsctl get-controller br0 extra", "sudo -n ovs-vsctl del-br br0",
        "sudo -n ovs-ofctl add-flow br0 actions=drop", "cat /etc/shadow",
        "sudo -n ovs-vsctl get-controller " + "b" * 16,
        "sudo -n ovs-vsctl get interface eth1 options",
        "sudo -n ovs-vsctl get interface eth1;id ofport"])
    def test_anything_else_is_refused_as_a_read(self, command):
        assert "REFUSED" in ovs.read_refusal(command)

    def test_the_rendered_transactions_are_of_the_write_shape(self):
        for values in (V4, V6, dict(V4, **{"openflow.datapath_id": "00000000000000a1"})):
            assert ovs.write_refusal(T.render("ovs", values)["program"][0]) == ""

    @pytest.mark.parametrize("command,words", [
        (PROGRAM_V4 + " -- add-flow br0 actions=drop", "not one of"),
        (PROGRAM_V4.replace("tcp:192.0.2.10:6653", "ssl:192.0.2.10:6653"), "tcp:"),
        (PROGRAM_V4.replace("tcp:192.0.2.10:6653", "tcp:2001:db8::10:6653"), "tcp:"),
        (PROGRAM_V4 + " && reboot", "metacharacter"),
        ("sudo -n ovs-vsctl --may-exist del-br br0", "does not go with"),
        ("ovs-vsctl set-fail-mode br0 secure", "not a `sudo -n ovs-vsctl`"),
        ("sudo -n ovs-vsctl set-fail-mode br0 open", "not one of"),
        ("sudo -n ovs-vsctl set interface eth1 ofport_request=0", "not one of"),
        ("sudo -n ovs-vsctl set interface eth1 ofport_request=65280", "not one of"),
        ("sudo -n ovs-vsctl set interface eth1 ofport_request=07", "not one of"),
        ("sudo -n ovs-vsctl set interface eth1 type=internal", "not one of"),
        ("sudo -n ovs-vsctl clear interface eth1 options", "not one of")])
    def test_a_write_off_its_shape_is_refused(self, command, words):
        why = ovs.write_refusal(command)
        assert "REFUSED" in why and words in why


class FakeConn:
    opened, sent = [], []

    def __init__(self, **params):
        FakeConn.opened.append(dict(params))

    def enable(self):
        FakeConn.sent.append("sudo -s")
        return ""

    def find_prompt(self):
        return "user@srv1:~$"

    def send_command(self, cmd, **kw):
        FakeConn.sent.append(cmd)
        return ""

    send_command_timing = send_command

    def send_config_set(self, cmds, **kw):
        FakeConn.sent.extend(cmds)
        return ""

    def disconnect(self):
        pass


@pytest.fixture
def netmiko_fake(monkeypatch):
    import netmiko
    FakeConn.opened, FakeConn.sent = [], []
    monkeypatch.setattr(netmiko, "ConnectHandler", FakeConn)
    monkeypatch.setattr(C, "vty_lines", lambda ip: (5, "the test's device"))
    C._sessions.clear()
    yield
    C._sessions.clear()


def _open(driver, ip):
    # A plain-account driver's session is opened only for a caller that declares it (C2625).
    return C.open_ssh(C.connection_params({"device_type": driver, "ip": ip, "username": "u"},
                                          password="p"), owner="test", plain=C.is_plain(driver))


class TestTheOvsSession:
    @pytest.mark.parametrize("ip", ["192.0.2.21", "2001:db8::21"], ids=("ipv4", "ipv6"))
    def test_the_transaction_is_refused_unheld_and_sent_held(self, netmiko_fake, ip):
        conn = _open("ovs_linux", ip)
        try:
            with pytest.raises(C.DiscoveryOnly):
                conn.send_command_timing(PROGRAM_V4)
            assert FakeConn.sent == []
            with D.hold(LIST, "srv1", "openflow config", "op@example.invalid", ip=ip):
                conn.send_command_timing(PROGRAM_V4)
            assert FakeConn.sent == [PROGRAM_V4]
        finally:
            conn.disconnect()

    def test_any_other_write_is_refused_even_held(self, netmiko_fake):
        conn = _open("ovs_linux", "192.0.2.21")
        try:
            with D.hold(LIST, "srv1", "openflow config", "op@example.invalid", ip="192.0.2.21"):
                for bad in ("sudo -n ovs-ofctl add-flow br0 actions=drop", "sudo reboot",
                            PROGRAM_V4 + " -- del-controller br0 ; id"):
                    with pytest.raises(C.DiscoveryOnly):
                        conn.send_command_timing(bad)
                with pytest.raises(C.DiscoveryOnly):
                    conn.send_config_set(["anything"])
            assert FakeConn.sent == []
        finally:
            conn.disconnect()

    def test_linux_enable_a_root_shell_is_never_sent(self, netmiko_fake):
        conn = _open("ovs_linux", "192.0.2.21")
        try:
            assert conn.enable() == "" and FakeConn.sent == []
            conn.send_command("sudo -n ovs-vsctl show")
            assert FakeConn.sent == ["sudo -n ovs-vsctl show"]
        finally:
            conn.disconnect()

    @pytest.mark.parametrize("command", [PROGRAM_V4, "sudo -n ovs-vsctl show"])
    def test_an_ios_session_refuses_ovs_commands_even_held(self, netmiko_fake, command):
        conn = _open("cisco_ios", "192.0.2.11")
        try:
            with D.hold(LIST, "r1", "deploy", "op@example.invalid", ip="192.0.2.11"):
                with pytest.raises(C.DiscoveryOnly) as e:
                    conn.send_command_timing(command)
            assert "Open vSwitch" in str(e.value) and FakeConn.sent == []
        finally:
            conn.disconnect()

    def test_the_platform_map_offers_ovs_linux_read_only_with_its_version_read(self):
        from modules import platform_maps as P
        assert "ovs_linux" in P.supported_drivers()
        assert discovery.version_command("ovs_linux") == "ovs-vsctl --version"


# --------------------------------------------------------------------------- draft or confirmed

@pytest.fixture
def net(tmp_path, monkeypatch):
    list_dir = tmp_path / "lab"
    os.makedirs(list_dir / "config_repo", exist_ok=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    # The SDN record's own accessor (`flow_intent._path`), which creates nothing on a read.
    monkeypatch.setattr("modules.config.list_data_path", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    rows = [{"hostname": "srv1", "ip": "192.0.2.21", "device_type": "ovs_linux"},
            {"hostname": "srv6", "ip": "2001:db8::21", "device_type": "ovs_linux"},
            {"hostname": "r1", "ip": "192.0.2.11", "device_type": "cisco_ios"}]
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [dict(d) for d in rows])
    monkeypatch.setattr("modules.list_settings.value", lambda ln, key, default=None: default)
    return list_dir


def _capture(monkeypatch, host="srv1", command="ovs-vsctl --version"):
    """A real reads run on *host*, its session faked at the engine's seam; the capture's name."""
    from modules.nsot import reads
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, c, **kw: "ovs-vsctl (Open vSwitch) 2.17.12")
    r = reads.run(LIST, [host], [command], "op@example.invalid",
                  session=lambda dev, fn: fn(None))
    assert r["results"][host]["state"] == "answered", r["results"][host]
    return discovery.capture_name(host, command, r["id"])


class TestDraftUntilConfirmed:
    def test_a_draft_is_never_sent_and_says_so(self, net):
        why = T.push_refusal(LIST, "ovs")
        assert "REFUSED" in why and "ovs" in why and "draft" in why

    def test_a_verified_person_confirms_against_a_capture_and_it_is_committed(self, net, monkeypatch):
        name = _capture(monkeypatch)
        got = T.confirm(LIST, "ovs", name, "op@example.invalid", "access-assertion")
        assert got["ok"], got["error"]
        s = T.status(LIST, "ovs")
        assert s["status"] == T.CONFIRMED and s["capture"] == name
        assert T.push_refusal(LIST, "ovs") == ""
        from modules.nsot.repo import git
        rc, log_, _ = git(str(net / "config_repo"), "log", "-1", "--format=%B")
        assert "Actor: op@example.invalid" in log_ and "Actor-Verified:" in log_

    def test_a_changed_template_is_a_draft_again(self, net, monkeypatch):
        T.confirm(LIST, "ovs", _capture(monkeypatch), "op@example.invalid", "access-assertion")
        monkeypatch.setattr(T, "sha256", lambda name: "f" * 64)
        s = T.status(LIST, "ovs")
        assert s["status"] == T.DRAFT and "confirm it again" in s["why"]
        assert "REFUSED" in T.push_refusal(LIST, "ovs")

    def test_a_confirmation_needs_a_person_a_capture_and_the_templates_driver(self, net, monkeypatch):
        name = _capture(monkeypatch)
        assert not T.confirm(LIST, "ovs", name, "op@example.invalid", "")["ok"]
        assert "no capture" in T.confirm(LIST, "ovs", "srv1/x/y", "op@example.invalid",
                                         "access-assertion")["error"]
        wrong = T.confirm(LIST, "arista_eos", name, "op@example.invalid", "access-assertion")
        assert not wrong["ok"] and "ovs_linux" in wrong["error"] and "arista_eos" in wrong["error"]
        assert T.status(LIST, "arista_eos")["status"] == T.DRAFT


# --------------------------------------------------------------------------- OVS end to end

class FakeOvs:
    """An OVS server's bridges, answering `ovs-vsctl` in its printed forms."""

    def __init__(self, bridges=None, dpid="0000aabbccddee01", requests=None):
        self.bridges = bridges or {}
        self.dpid = dpid
        self.sent = []
        # Each interface's ofport_request; its ofport is the request, else its add order
        # (ovs-vswitchd.conf.db(5): a request is honoured when the number is free).
        self.requests = dict(requests or {})

    def ofport(self, port):
        if port in self.requests:
            return self.requests[port]
        for b in self.bridges.values():
            if port in b["ports"]:
                taken = set(self.requests.values())
                free = [n for n in range(1, 100) if str(n) not in taken]
                return str(free[b["ports"].index(port)])
        return "-1"

    def answer(self, cmd):
        self.sent.append(cmd)
        w = cmd.split()
        assert w[:3] == ["sudo", "-n", "ovs-vsctl"], cmd
        rest = w[3:]
        if rest[:2] == ["get", "interface"]:
            if rest[3] == "ofport_request":
                return self.requests.get(rest[2], "[]")
            return self.ofport(rest[2])
        if rest == ["list-br"]:
            return "\n".join(sorted(self.bridges))
        if len(rest) == 2 and rest[0] in ("get-controller", "get-fail-mode", "list-ports"):
            b = self.bridges[rest[1]]
            return {"get-controller": "\n".join(b["controllers"]),
                    "get-fail-mode": b["fail_mode"],
                    "list-ports": "\n".join(b["ports"])}[rest[0]]
        if rest[:2] == ["get", "bridge"]:
            b = self.bridges[rest[2]]
            if rest[3] == "protocols":
                return "[" + ", ".join(f'"{p}"' for p in b["protocols"]) + "]"
            return f'"{b["other"].get("datapath-id") or self.dpid}"'
        if rest[:3] == ["--if-exists", "get", "bridge"]:
            v = self.bridges[rest[3]]["other"].get("datapath-id")
            return f'"{v}"' if v else ""
        return self.transaction(rest)

    def transaction(self, rest):
        cmds, cur = [], []
        for x in rest:
            if x == "--":
                cmds.append(cur)
                cur = []
            else:
                cur.append(x)
        cmds.append(cur)
        for c in cmds:
            c = [x for x in c if x not in ("--may-exist", "--if-exists")]
            verb, args = c[0], c[1:]
            if verb == "add-br":
                self.bridges.setdefault(args[0], {"controllers": [], "fail_mode": "",
                                                  "protocols": [], "ports": [], "other": {}})
            elif verb == "del-br":
                for p in (self.bridges.pop(args[0], None) or {}).get("ports") or []:
                    self.requests.pop(p, None)
            elif verb == "add-port":
                if args[1] not in self.bridges[args[0]]["ports"]:
                    self.bridges[args[0]]["ports"].append(args[1])
            elif verb == "del-port":
                b = self.bridges[args[0]]["ports"]
                if args[1] in b:
                    b.remove(args[1])
                    self.requests.pop(args[1], None)
            elif verb == "set-controller":
                self.bridges[args[0]]["controllers"] = args[1:]
            elif verb == "del-controller":
                self.bridges[args[0]]["controllers"] = []
            elif verb == "set-fail-mode":
                self.bridges[args[0]]["fail_mode"] = args[1]
            elif verb == "del-fail-mode":
                self.bridges[args[0]]["fail_mode"] = ""
            elif verb == "set" and args[0] == "interface":
                self.requests[args[1]] = args[2].partition("=")[2]
            elif verb == "clear" and args[0] == "interface":
                self.requests.pop(args[1], None)
            elif verb == "set":
                key, _, val = args[2].partition("=")
                if key == "protocols":
                    self.bridges[args[1]]["protocols"] = val.split(",")
                else:
                    self.bridges[args[1]]["other"]["datapath-id"] = val
            elif verb == "clear":
                self.bridges[args[1]]["protocols"] = []
            elif verb == "remove":
                self.bridges[args[1]]["other"].pop("datapath-id", None)
        return ""


class Server:
    """`with_temp_connection` at its seam: each session to the fake OVS."""

    def __init__(self, fake):
        self.fake, self.opened = fake, []

    def __call__(self, dev, fn):
        self.opened.append(dev["hostname"])
        return fn(self)

    def send_command_timing(self, cmd, **kw):
        return self.fake.answer(cmd)


class Controller:
    def __init__(self, dpids):
        self.dpids, self.reads = dpids, 0

    def switches(self):
        self.reads += 1
        return {"ok": True, "switches": [{"dpid": d} for d in self.dpids()]}


@pytest.fixture
def ovs_op(net, monkeypatch):
    rows = []
    monkeypatch.setattr("modules.sdn.flow_intent.record_operation",
                        lambda network, row: rows.append(row) or {"ok": True})
    monkeypatch.setattr(O, "_connection_name", lambda network, values, given="": "ryu")
    T.confirm(LIST, "ovs", _capture(monkeypatch), "op@example.invalid", "access-assertion")
    return rows


def _driver(ctl):
    return lambda network, name: {"ok": True, "driver": ctl}


def _ok(values=V4):
    return {"ok": True, "values": dict(values), "defaults": [], "error": ""}


class TestOvsEndToEnd:
    @pytest.mark.parametrize("host,values", [("srv1", V4), ("srv6", V6)], ids=("ipv4", "ipv6"))
    def test_previewed_confirmed_held_sent_verified_and_recorded(self, ovs_op, host, values):
        fake = FakeOvs()
        p = O.plan(LIST, host, values=_ok(values), session=Server(fake))
        assert p["ok"], p["error"]
        assert p["undo"] == "sudo -n ovs-vsctl --if-exists del-br br0"
        assert p["status"]["status"] == T.CONFIRMED and fake.bridges == {}
        ctl = Controller(lambda: [int(fake.dpid, 16)] if "br0" in fake.bridges else [])
        out = O.apply(LIST, host, p["hash"], actor="op@example.invalid",
                      actor_verified="access-assertion", values=_ok(values),
                      session=Server(fake), driver=_driver(ctl), sleep=lambda s: None)
        assert out["outcome"] == "verified" and out["ok"], out["error"]
        assert [c["state"] for c in out["verify"]["checks"]] == ["pass"] * 7
        host_ = "[2001:db8::10]" if values is V6 else "192.0.2.10"
        assert fake.bridges["br0"]["controllers"] == [f"tcp:{host_}:6653"]
        (row,) = ovs_op
        assert row["outcome"] == "verified" and row["hash"] == p["hash"]
        assert row["response"]["kind"] == "openflow_config" and row["actor"]

    @pytest.mark.parametrize("server,iface,why", [
        (_device(), _mgmt("eno1"), "primary IP"),
        (_device(ip4=None, ip6="2001:db8::21/64"), _mgmt("eno1", addr="2001:db8::21/64"),
         "primary IP"),
        (dict(_device(), oob_ip={"address": "192.0.2.121/24"}),
         _mgmt("ipmi0", addr="192.0.2.121/24"), "OOB IP"),
        (_device(), _mgmt("eno2", addr=None, mgmt_only=True), "mgmt_only")],
        ids=("primary-ipv4", "primary-ipv6", "oob_ip", "mgmt_only"))
    def test_the_servers_management_interface_is_never_a_bridge_port(self, ovs_op, server,
                                                                      iface, why):
        got = V.from_netbox(server, [iface, _iface("eth1", num=1), _iface("eth2", num=2)],
                            [_service()], CTL)
        p = O.plan(LIST, "srv1", values=got, session=Server(FakeOvs()))
        assert p["ok"], p["error"]
        assert iface["name"] not in p["program"][0] and "add-port br0 eth1" in p["program"][0]
        assert p["excluded"] == [
            f"{iface['name']} is the management interface ({why}): excluded from OpenFlow"]

    def test_a_draft_template_sends_nothing_and_opens_no_session(self, net):
        fake, server = FakeOvs(), None
        server = Server(fake)
        out = O.apply(LIST, "srv1", "x" * 64, actor="op@example.invalid",
                      actor_verified="access-assertion", values=_ok(), session=server,
                      driver=_driver(Controller(lambda: [])))
        assert out["outcome"] == "refused" and "draft" in out["error"] and "ovs" in out["error"]
        assert server.opened == [] and fake.sent == []

    def test_a_moved_bridge_is_refused_naming_both_hashes(self, ovs_op):
        fake = FakeOvs()
        p = O.plan(LIST, "srv1", values=_ok(), session=Server(fake))
        fake.bridges["br0"] = {"controllers": [], "fail_mode": "", "protocols": [], "ports": [],
                               "other": {}}
        out = O.apply(LIST, "srv1", p["hash"], actor="op@example.invalid",
                      actor_verified="access-assertion", values=_ok(), session=Server(fake),
                      driver=_driver(Controller(lambda: [])))
        assert out["outcome"] == "refused" and p["hash"][:12] in out["error"]
        assert not any("add-br" in c for c in fake.sent)

    def test_a_switch_the_controller_never_lists_is_rolled_back(self, ovs_op):
        before = {"br0": {"controllers": ["tcp:192.0.2.99:6633"], "fail_mode": "standalone",
                          "protocols": ["OpenFlow10"], "ports": ["eth1"], "other": {}}}
        import copy
        fake = FakeOvs(copy.deepcopy(before))
        p = O.plan(LIST, "srv1", values=_ok(), session=Server(fake))
        assert "set-controller br0 tcp:192.0.2.99:6633" in p["undo"]
        assert "--if-exists del-port br0 eth2" in p["undo"] and "del-port br0 eth1" not in p["undo"]
        # eth1 was on the bridge with no number requested: the undo clears the request.
        assert "clear interface eth1 ofport_request" in p["undo"]
        ctl = Controller(lambda: [])
        out = O.apply(LIST, "srv1", p["hash"], actor="op@example.invalid",
                      actor_verified="access-assertion", values=_ok(), session=Server(fake),
                      driver=_driver(ctl), sleep=lambda s: None)
        assert out["outcome"] == "rolled_back" and out["rollback"]["ok"]
        assert ctl.reads == O.VERIFY_READS and "switch list" in out["error"]
        assert fake.bridges == before and fake.requests == {}
        assert ovs_op[0]["outcome"] == "rolled_back"

    def test_a_ports_own_request_is_put_back_on_a_rollback(self, ovs_op):
        fake = FakeOvs({"br0": {"controllers": [], "fail_mode": "", "protocols": [],
                                "ports": ["eth1"], "other": {}}}, requests={"eth1": "9"})
        p = O.plan(LIST, "srv1", values=_ok(), session=Server(fake))
        assert p["before"]["ofport_request"] == {"eth1": "9"}
        assert "set interface eth1 ofport_request=9" in p["undo"]
        assert ovs.write_refusal(p["undo"]) == ""

    def test_a_port_ovs_numbered_otherwise_fails_verify_and_is_rolled_back(self, ovs_op):
        """C2603: a request OVS does not honour (the number held by another interface) leaves
        the port numbered otherwise, and verify says so by name, never a pass."""
        fake = FakeOvs()
        p = O.plan(LIST, "srv1", values=_ok(), session=Server(fake))
        honour = fake.ofport
        fake.ofport = lambda port: "5" if port == "eth2" else honour(port)
        ctl = Controller(lambda: [int(fake.dpid, 16)] if "br0" in fake.bridges else [])
        out = O.apply(LIST, "srv1", p["hash"], actor="op@example.invalid",
                      actor_verified="access-assertion", values=_ok(), session=Server(fake),
                      driver=_driver(ctl), sleep=lambda s: None)
        (bad,) = [c for c in out["verify"]["checks"] if c["state"] == "fail"]
        assert bad["name"] == "its OpenFlow port numbers"
        assert bad["words"] == "eth2 is 5, wanted 2"
        assert out["outcome"] == "rolled_back" and fake.bridges == {}

    def test_a_bridge_mercury_could_not_put_back_is_refused_at_the_plan(self, net):
        fake = FakeOvs({"br0": {"controllers": ["ptcp:6634"], "fail_mode": "", "protocols": [],
                                "ports": [], "other": {}}})
        p = O.plan(LIST, "srv1", values=_ok(), session=Server(fake))
        assert not p["ok"] and "could not put back" in p["error"] and p["hash"] == ""

    def test_a_device_held_by_another_operation_is_refused_by_name(self, ovs_op):
        fake = FakeOvs()
        p = O.plan(LIST, "srv1", values=_ok(), session=Server(fake))
        with D.hold(LIST, "srv1", "deploy", "someone@example.invalid", ip="192.0.2.21"):
            import threading
            got = {}
            t = threading.Thread(target=lambda: got.update(O.apply(
                LIST, "srv1", p["hash"], actor="op@example.invalid",
                actor_verified="access-assertion", values=_ok(), session=Server(fake),
                driver=_driver(Controller(lambda: [])))))
            t.start()
            t.join(30)
        assert got["outcome"] == "refused" and "someone@example.invalid" in got["error"]
        assert not any("add-br" in c for c in fake.sent)

    def test_only_an_ovs_server_is_configured_this_way(self, net):
        p = O.plan(LIST, "r1", values=_ok(), session=Server(FakeOvs()))
        assert not p["ok"] and "cisco_ios" in p["error"] and "ovs_linux" in p["error"]

    def test_a_missing_netbox_value_reads_nothing_from_the_server(self, net):
        server = Server(FakeOvs())
        p = O.plan(LIST, "srv1", values={"ok": False, "values": {}, "defaults": [],
                                         "error": "NetBox holds no device 'srv1'"},
                   session=server)
        assert not p["ok"] and "NetBox" in p["error"] and server.opened == []

    def test_the_record_is_drawn_on_history_as_an_openflow_configuration(self, net):
        from modules.sdn import flow_intent
        flow_intent.record_operation(LIST, {"id": "ofcfg-1", "actor": "op@example.invalid",
                                            "at": "2026-11-05T04:00:00Z", "outcome": "verified",
                                            "dpid_hex": "0000aabbccddee01",
                                            "response": {"kind": "openflow_config",
                                                         "device": "srv1"}})
        from modules import history_sources as H
        from modules.nsot import listref
        ctx = {"device": "", "ref": listref.resolve(LIST), "limit": 50,
               "since": None, "until": None}
        (event,) = H.sdn_operations(ctx)["events"]
        assert event["what"] == ("SDN openflow configuration on srv1 (datapath "
                                 "0000aabbccddee01): verified")
