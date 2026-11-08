"""The OpenFlow render against the lab as it runs (the SDN platform design revision 6, section
15: T1, T2 and T11; C2598, C2599, C2600, C2603).

- **T1, the golden render:** each of the five Lab 9 switches is rendered from an NSOT export of
  its NetBox records (`tests/fixtures/nsot_export/lab9_records.json`, read through
  `export.collect` and `openflow_values.from_export`) with the platform profile entry its own
  captured version selects, and the program's parsed model is compared with the parsed model of
  the switch's masked 2026-11-06 configuration (`tests/fixtures/lab9_captures/2026-11-06/`):
  no difference, and only what the capture does not carry (OVS's protocols and datapath id,
  which `ovs-vsctl show` does not print) unread. A template missing LLDP off (C2600), the wrong
  version (C2598) or no `ofport_request` (C2603) fails it.
- **T2, the restart on a bind change:** the Arista planned against its captured state with one
  bound port removed renders `shutdown` then `no shutdown`; against the state as captured, no
  restart (C2599).
- **T11, the profiles:** every template that renders has a profile for each of its drivers,
  every `profile.` key a template reads is held by every entry of its profile, and each lab
  switch's entry is chosen from its own captured version text.
"""

import copy
import json
import os
import re

import pytest

from modules.nsot import export as X
from modules.platforms import profile as P
from modules.sdn import openflow_state as S
from modules.sdn import openflow_templates as T
from modules.sdn import openflow_values as V

HERE = os.path.dirname(os.path.abspath(__file__))
CAPTURES = os.path.join(HERE, "fixtures", "lab9_captures", "2026-11-06")
RECORDS = os.path.join(HERE, "fixtures", "nsot_export", "lab9_records.json")

#: Each lab switch: its capture, its driver and the template Mercury renders for it.
SWITCHES = {
    "arista-sw1": ("arista-sw1.txt", "arista_eos", "arista_eos"),
    "arista-sw2": ("arista-sw2.txt", "arista_eos", "arista_eos"),
    "procurve-sw": ("procurve-sw.txt", "hp_procurve", "aruba_os_switch"),
    "ovs1": ("ovs1.txt", "ovs_linux", "ovs"),
    "ovs2": ("ovs2.txt", "ovs_linux", "ovs"),
}


def _capture(name: str) -> str:
    with open(os.path.join(CAPTURES, name), encoding="utf-8") as fh:
        return fh.read()


def _running_config(text: str) -> str:
    """The `show running-config` answer in a capture: from the command to the next prompt."""
    m = re.search(r"#\s*show running-config\n(.*?)(?:\n\S+#|\Z)", text, re.S)
    assert m, "the capture holds no show running-config"
    return m.group(1)


def _ovs_sections(text: str) -> tuple:
    show = re.search(r"### ovs\n(.*?)\n    ovs_version", text, re.S).group(1)
    interfaces = re.search(r'ovs_version: "[^"]+"\n(.*?)\n### ', text, re.S).group(1)
    return show, interfaces


def _version(capture: str, driver: str) -> str:
    """The switch's own version text, as the capture prints it."""
    text = _capture(capture)
    rx = {"arista_eos": r"Software image version:\s*(\S+)",
          "hp_procurve": r"Software revision\s*:?\s*(K\.\S+)",
          "ovs_linux": r'ovs_version: "([^"]+)"'}[driver]
    return re.search(rx, text).group(1)


def _state(template: str, capture: str) -> dict:
    text = _capture(capture)
    if template == "ovs":
        return S.parse("ovs", *_ovs_sections(text))
    return S.parse(template, _running_config(text))


def _records() -> dict:
    with open(RECORDS, encoding="utf-8") as fh:
        return json.load(fh)


def fake_netbox(records: dict):
    """NetBox's list endpoints over the records, filtered as NetBox filters them; each call
    recorded, so a test can count the reads."""
    calls = []

    def get(path, **params):
        calls.append((path, params))
        ids = params.get("device_id")
        ids = set(ids if isinstance(ids, list) else [ids]) if ids is not None else None

        def by_device(rows, key="device"):
            return [copy.deepcopy(r) for r in rows if ids is None
                    or (r.get(key) or {}).get("id") in ids]
        if path == "dcim/devices/":
            rows = records["devices"]
            if "name" in params:
                rows = [d for d in rows if d["name"] == params["name"]]
            elif "role" in params:
                rows = [d for d in rows if d["role"]["slug"] == params["role"]]
            return copy.deepcopy(rows)
        if path == "dcim/interfaces/":
            return by_device(records["interfaces"])
        if path == "ipam/ip-addresses/":
            owned = {i["id"] for i in by_device(records["interfaces"])}
            return [copy.deepcopy(a) for a in records["ip_addresses"]
                    if a["assigned_object"]["id"] in owned]
        if path == "ipam/services/":
            if "name" in params:
                return [copy.deepcopy(s) for s in records["services"]
                        if s["name"] == params["name"]]
            return by_device(records["services"])
        if path == "dcim/cables/":
            return copy.deepcopy(records["cables"]) if ids else []
        if path == "ipam/vlans/":
            return copy.deepcopy(records["vlans"])
        if path == "ipam/prefixes/":
            return copy.deepcopy(records["prefixes"])
        raise AssertionError(f"an unexpected NetBox read: {path} {params}")
    return get, calls


@pytest.fixture
def lab_export(monkeypatch):
    monkeypatch.setattr("modules.inventory.source_config.load",
                        lambda name: {"source": "netbox",
                                      "filters": {"role": "openflow-switch"}})
    records = _records()
    get, _calls = fake_netbox(records)
    built = X.build("lab9", get=get, version=lambda: records["netbox_version"])
    assert built["ok"], built["error"]
    return X.parse(built["bytes"])


# --------------------------------------------------------------------------- T1

class TestTheGoldenRender:
    @pytest.mark.parametrize("device", sorted(SWITCHES))
    def test_each_lab_switch_renders_to_its_running_openflow_layer(self, lab_export, device):
        capture, driver, template = SWITCHES[device]
        got = V.from_export(lab_export, device)
        assert got["ok"], got["error"]
        selected = P.select(driver, _version(capture, driver))
        assert selected["ok"], selected["error"]
        plan = S.render_against(template, got["values"], _state(template, capture), selected)
        assert plan["ok"], plan["error"]
        assert plan["different"] == [], plan["different"]
        want_unread = {"ovs": ["br0.datapath_id", "br0.protocols"]}.get(template, [])
        assert sorted(plan["unread"]) == want_unread
        assert all(line["why"] for line in plan["rendered"]["lines"])

    def test_the_ovs_bridges_datapath_ids_are_the_ones_the_controller_lists(self, lab_export):
        listed = json.loads(re.search(r"### switches\n(.*?)\n", _capture("ryu-rest.txt"),
                                      re.S).group(1))
        for device in ("ovs1", "ovs2"):
            rendered = T.render("ovs", V.from_export(lab_export, device)["values"])
            dpid = S.model_of("ovs", rendered)["br0"]["datapath_id"]
            assert int(dpid, 16) in listed, (device, dpid)

    def test_the_arista_renders_at_the_version_it_negotiated_m2(self, lab_export):
        """M2 (C2598): the Aristas run 1.3 and their OpenFlow layer renders at 1.3."""
        assert "negotiated version: Version 1.3" in _capture("arista-sw1.txt")
        values = V.from_export(lab_export, "arista-sw1")["values"]
        assert values["openflow.version"] == "1.3"
        assert T.render("arista_eos", values, P.select("arista_eos", "4.17.0F"))["ok"]

    @pytest.mark.parametrize("template,capture,words", [
        ("arista_eos", "arista-sw1.txt", "lldp_off: wanted none"),
        ("aruba_os_switch", "procurve-sw.txt", "lldp_disabled: wanted none")])
    def test_a_template_without_lldp_off_differs_from_the_lab(self, lab_export, monkeypatch,
                                                              template, capture, words):
        """C2600's fault, planted: the LLDP lines' condition never holding."""
        t = T.load(template)
        for line in t["lines"]:
            if "lldp" in line["text"]:
                line["when"] = "openflow.nothing"
        monkeypatch.setattr(T, "load", lambda name: t)
        device = {"arista_eos": "arista-sw1", "aruba_os_switch": "procurve-sw"}[template]
        plan = S.render_against(template, V.from_export(lab_export, device)["values"],
                                _state(template, capture))
        assert any(d.startswith(words) for d in plan["different"]), plan["different"]

    @pytest.mark.parametrize("dropped,words", [
        ("vlan 200 untagged", "untagged.200: wanted none, the switch has 2, 3"),
        ("openflow instance", "instances: wanted none, the switch has lab9")])
    def test_a_procurve_program_missing_a_part_differs_from_the_lab(self, lab_export, dropped,
                                                                   words):
        """The member VLAN's ports and the instance are part of the layer even when a program
        sets none of them (an empty wanted part is never equal to the switch's)."""
        rendered = T.render("aruba_os_switch",
                            V.from_export(lab_export, "procurve-sw")["values"])
        rendered["program"] = [x for x in rendered["program"] if not x.startswith(dropped)]
        d, _u = S.differences(S.model_of("aruba_os_switch", rendered),
                              _state("aruba_os_switch", "procurve-sw.txt"))
        assert words in d, d

    def test_an_ovs_bridge_without_its_port_requests_differs_from_the_lab(self, lab_export):
        """C2603's fault: no ofport_request is said as numbered by add order, never equal."""
        values = V.from_export(lab_export, "ovs1")["values"]
        rendered = T.render("ovs", values)
        rendered["program"] = [re.sub(r" -- set interface \S+ ofport_request=\d+", "",
                                      rendered["program"][0])]
        d, _u = S.differences(S.model_of("ovs", rendered), _state("ovs", "ovs1.txt"))
        assert any(x.startswith("br0.ofport.eno2: wanted unrequested") for x in d), d


# --------------------------------------------------------------------------- T2

class TestTheRestartOnABindChange:
    def test_a_port_the_running_agent_does_not_bind_restarts_it(self, lab_export):
        values = V.from_export(lab_export, "arista-sw1")["values"]
        text = _running_config(_capture("arista-sw1.txt"))
        assert "   bind interface Et18-19" in text
        one_less = S.eos(text.replace("   bind interface Et18-19", "   bind interface Et18"))
        assert one_less["bound"] == ["Ethernet18"] and one_less["enabled"]
        plan = S.render_against("arista_eos", values, one_less)
        assert plan["ok"], plan["error"]
        program = plan["rendered"]["program"]
        assert program[-2:] == ["   shutdown", "   no shutdown"]
        assert plan["different"] == ["bound: wanted Ethernet18, Ethernet19, the switch has "
                                     "Ethernet18"]

    def test_the_binding_as_captured_restarts_nothing(self, lab_export):
        values = V.from_export(lab_export, "arista-sw1")["values"]
        plan = S.render_against("arista_eos", values, _state("arista_eos", "arista-sw1.txt"))
        assert "   shutdown" not in plan["rendered"]["program"]
        assert plan["rendered"]["program"][-1] == "   no shutdown"

    def test_a_first_enable_starts_the_agent_with_no_restart(self, lab_export):
        values = V.from_export(lab_export, "arista-sw1")["values"]
        plan = S.render_against("arista_eos", values, S.eos("hostname x\n"))
        assert "   shutdown" not in plan["rendered"]["program"]
        assert any(d.startswith("enabled: wanted True") for d in plan["different"])


# --------------------------------------------------------------------------- T11

class TestTheProfilesTheTemplatesRead:
    @pytest.mark.parametrize("name", [n for n in T.names()
                                      if T.load(n).get("support") != "unknown"])
    def test_every_rendering_template_has_a_profile_for_each_driver(self, name):
        for driver in T.load(name)["drivers"]:
            assert P.for_driver(driver), (name, driver)

    @pytest.mark.parametrize("name", [n for n in T.names()
                                      if T.load(n).get("support") != "unknown"])
    def test_every_profile_key_a_template_reads_is_held_by_every_entry(self, name):
        t = T.load(name)
        for driver in t["drivers"]:
            doc = P.load(P.for_driver(driver))
            for entry in doc["entries"]:
                for key in T.profile_keys(t):
                    assert P.value(entry, key[len("profile."):]) is not P.ABSENT, (name, key)

    def test_the_templates_read_the_three_keys_p2_adds(self):
        read = set().union(*(T.profile_keys(T.load(n)) for n in T.names()))
        assert read == {"profile.openflow.bind_change_requires",
                        "profile.openflow.openflow_ports_require",
                        "profile.openflow.port_numbering"}

    @pytest.mark.parametrize("device", sorted(SWITCHES))
    def test_each_lab_switch_selects_its_entry_from_its_own_version(self, device):
        capture, driver, _template = SWITCHES[device]
        got = P.select(driver, _version(capture, driver))
        assert got["ok"], got["error"]
        assert got["profile"] == {"arista_eos": "arista_eos", "hp_procurve": "aruba_os_switch",
                                  "ovs_linux": "ovs"}[driver]


# --------------------------------------------------------------------------- the parsers

class TestTheParsers:
    @pytest.mark.parametrize("text,want", [
        ("Et18-19", ["Ethernet18", "Ethernet19"]),
        ("Et1/1-2,Et5", ["Ethernet1/1", "Ethernet1/2", "Ethernet5"]),
        ("Ethernet7", ["Ethernet7"])])
    def test_eos_ranges_expand(self, text, want):
        assert S.expand_eos(text) == want

    def test_procurves_nested_and_one_line_forms_read_the_same(self):
        nested = _running_config(_capture("procurve-sw.txt"))
        lines = ["openflow controller-id 1 ip 192.0.2.1 port 6653 controller-interface vlan 100",
                 "openflow instance lab9 member vlan 200",
                 "openflow instance lab9 controller-id 1", "openflow instance lab9 version 1.3",
                 "openflow instance lab9 enable", "openflow enable",
                 "lldp admin-status 2 disable", "lldp admin-status 3 disable",
                 "vlan 200 untagged 2", "vlan 200 untagged 3"]
        one = S.aruba_os_switch("\n".join(lines))
        have = S.aruba_os_switch(nested)
        assert S.differences(one, have) == ([], [])
        assert have["untagged"]["1"][:2] == ["1", "4"]

    @pytest.mark.parametrize("target", ["tcp:192.0.2.1:6653", "tcp:[2001:db8::1]:6653"],
                             ids=("ipv4", "ipv6"))
    def test_an_ovs_controller_target_reads_the_same_from_show_and_program(self, target):
        show = f'    Bridge br0\n        Controller "{target}"\n        fail_mode: secure\n' \
               '        Port eno2\n            Interface eno2\n'
        program = (f"sudo -n ovs-vsctl --may-exist add-br br0 -- set-fail-mode br0 secure -- "
                   f"set-controller br0 {target} -- --may-exist add-port br0 eno2 -- "
                   "set interface eno2 ofport_request=1")
        have = S.ovs_show(show, "name : eno2\nofport : 1\n")
        assert have["br0"]["controllers"] == [target]
        assert S.differences(S.ovs_program(program), have) == ([], [])

    def test_an_unread_value_is_never_counted_equal_or_different(self):
        d, u = S.differences({"br0": {"ofport": {"eno2": "1"}}}, {"br0": {"ofport": S.UNREAD}})
        assert d == [] and u == ["br0.ofport"]
