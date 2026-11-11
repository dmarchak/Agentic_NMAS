"""Lab 9 Objective 2's operation for the hardware switches, and C2777's remainder
(docs/LAB9_OPENFLOW.md sections 1, 4 and 4b; C2902).

- **C2777's remainder:** a plan's OpenFlow values come from the network's committed NSOT export,
  never NetBox live, and its hash includes the export's SHA-256; no committed export refuses,
  naming the NSOT export card on SDN › Apps.
- **The session carries only the OpenFlow lines:** an Arista EOS or ArubaOS-Switch session (a
  discovery driver) carries one configuration set, every line one of its template's shapes,
  only while the switch is held; anything else stays refused, held or not.
- **The vendor plan** (`openflow_config.plan`): the switch's own version selects its profile
  entry, its running configuration is parsed, the program rendered against it, the undo checked
  by parsing, the hash bound to the export.
- **The vendor apply:** confirmed template, the hash compared, held, sent, verified (the
  read-back's OpenFlow layer, then the controller's switch list), rolled back on failure,
  recorded; never saved (section 4b: undecided), and said so.

The switches are the lab's own 2026-11-06 masked captures (`tests/fixtures/lab9_captures/`), and
the values the lab's NSOT export built from its NetBox records
(`tests/fixtures/nsot_export/lab9_records.json`), committed in a temporary repository. Netmiko is
faked at `ConnectHandler`, so `open_ssh` and its session guard run for real; the fake switch
keeps its running configuration as text and appends each configuration set it is sent.
"""

import copy
import os
import re

import pytest

from modules import connection as C
from modules.nsot import device_ops as D
from modules.nsot import export as X
from modules.sdn import openflow_cli as CLI
from modules.sdn import openflow_config as OC
from modules.sdn import openflow_state as S
from modules.sdn import openflow_templates as T
from tests.test_openflow_config import Controller, FakeOvs, Server
from tests.test_openflow_golden import _capture, _records, _running_config, fake_netbox

LIST = "lab9"
ACTOR = "op@example.invalid"
#: The lab's switches as the inventory holds them (their addresses are the export's); arista6
#: is arista-sw2 reached over an IPv6 management address.
ROWS = [{"hostname": "arista-sw1", "ip": "192.0.2.2", "device_type": "arista_eos"},
        {"hostname": "arista-sw2", "ip": "2001:db8::6", "device_type": "arista_eos"},
        {"hostname": "procurve-sw", "ip": "192.0.2.5", "device_type": "hp_procurve"},
        {"hostname": "ovs1", "ip": "192.0.2.3", "device_type": "ovs_linux"},
        {"hostname": "comware", "ip": "192.0.2.9", "device_type": "hp_comware"}]
#: Each lab switch's datapath id as its controller lists it (ryu-rest.txt's /stats/switches).
DPIDS = {"arista-sw1": 2214744208935, "arista-sw2": 2843895626628,
         "procurve-sw": 56298109234905574}


def _answer(text: str, command: str) -> str:
    """One command's answer in a capture: from the command to the next prompt."""
    m = re.search(re.escape(command) + r"\n(.*?)(?:\n\S+[#>]|\Z)", text, re.S)
    assert m, command
    return m.group(1)


class Switch:
    """A switch as its session shows it: its running configuration (text, each configuration
    set appended as typed), its own show answers, and what it was sent."""

    def __init__(self, capture: str, running=None, reply=""):
        text = _capture(capture)
        self.version = text
        self.running = _running_config(text) if running is None else running
        self.openflow = (_answer(text, "#show openflow") if "arista" in capture
                         else _answer(text, "# show openflow instance lab9"))
        self.reply, self.sets, self.reads, self.modes, self.saved = reply, [], [], [], False

    def answer(self, cmd):
        self.reads.append(cmd)
        if cmd == "show version":
            return self.version
        if cmd == "show running-config":
            return self.running
        if cmd in ("show openflow", "show openflow instance lab9"):
            return self.openflow
        raise AssertionError(f"an unexpected read: {cmd}")


class SwitchConn:
    """Netmiko's session at its boundary, to the `Switch` at its address."""
    at: dict = {}

    def __init__(self, **params):
        self.sw = SwitchConn.at[params["ip"]]

    def enable(self):
        pass

    def find_prompt(self):
        return "sw#"

    def send_command(self, cmd, **kw):
        return self.sw.answer(cmd)

    send_command_timing = send_command

    def config_mode(self, *a, **k):
        self.sw.modes.append("configure terminal")
        return ""

    def send_config_set(self, cmds, **kw):
        self.config_mode()                       # as netmiko's own send_config_set does
        self.sw.sets.append(list(cmds))
        self.sw.running += "\n" + "\n".join(cmds)
        return self.sw.reply

    def save_config(self, *a, **k):
        self.sw.saved = True

    def commit(self, *a, **k):
        return ""

    def disconnect(self):
        pass


@pytest.fixture
def netmiko_fake(monkeypatch):
    import netmiko
    SwitchConn.at = {}
    monkeypatch.setattr(netmiko, "ConnectHandler", SwitchConn)
    monkeypatch.setattr(C, "vty_lines", lambda ip: (5, "the test's device"))
    C._sessions.clear()
    yield
    C._sessions.clear()
    from tests import ssh_slot_guard
    ssh_slot_guard.release()
    with D._mu:
        stale = list(D._held.values())
        D._held.clear()
    for info in stale:
        if info["fd"] is not None:
            os.close(info["fd"])


def _session(dev, fn):
    """`with_temp_connection` at its seam, through the real `open_ssh` and its guard."""
    conn = C.open_ssh(C.connection_params({"device_type": dev["device_type"], "ip": dev["ip"],
                                           "username": "u"}, password="p"),
                      owner="test", plain=C.is_plain(dev["device_type"]))
    try:
        return fn(conn)
    finally:
        conn.disconnect()


def _open(driver, ip):
    return C.open_ssh(C.connection_params({"device_type": driver, "ip": ip, "username": "u"},
                                          password="p"), owner="test", plain=C.is_plain(driver))


@pytest.fixture
def net(tmp_path, monkeypatch, netmiko_fake):
    list_dir = tmp_path / "lab9"
    os.makedirs(list_dir / "config_repo", exist_ok=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.list_data_path", lambda name: str(list_dir))
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in ROWS])
    monkeypatch.setattr("modules.list_settings.value", lambda ln, key, default=None: default)
    monkeypatch.setattr("modules.inventory.source_config.load",
                        lambda name: {"source": "netbox",
                                      "filters": {"role": "openflow-switch"}})
    return list_dir


def _commit_export(records=None) -> str:
    records = records or _records()
    get, _calls = fake_netbox(records)
    built = X.build(LIST, get=get, version=lambda: records["netbox_version"])
    assert built["ok"], built["error"]
    got = X.write(LIST, ACTOR, "access-assertion", data=built["bytes"])
    assert got["ok"], got["error"]
    return built["sha256"]


def _moved_controller_port() -> dict:
    records = copy.deepcopy(_records())
    for s in records["services"]:
        if s["name"] == "openflow":
            s["ports"] = [6633]
    return records


def _confirm(monkeypatch, host, template):
    """A real reads run of *host*'s running configuration, then *template* confirmed on it."""
    from modules import discovery
    from modules.nsot import reads
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, c, **kw: "openflow\n   no shutdown\n")
    r = reads.run(LIST, [host], ["show running-config"], ACTOR,
                  session=lambda dev, fn: fn(None))
    assert r["results"][host]["state"] == "answered", r["results"][host]
    got = T.confirm(LIST, template, discovery.capture_name(host, "show running-config", r["id"]),
                    ACTOR, "access-assertion")
    assert got["ok"], got["error"]


def _blank_procurve() -> str:
    """The ProCurve's running configuration with no OpenFlow: its OpenFlow block, LLDP lines and
    VLAN 200 membership removed, ports 2 and 3 untagged in VLAN 1 as a factory switch has them."""
    text = _running_config(_capture("procurve-sw.txt"))
    text = re.sub(r"openflow\n(?:   .*\n)+", "", text)
    text = text.replace("lldp admin-status 2-3 disable\n", "")
    text = text.replace("   no untagged 2-3\n   untagged 1,4-24\n", "   untagged 1-24\n")
    return text.replace("   untagged 2-3\n   no ip address\n", "   no ip address\n")


# --------------------------------------------------------------------------- C2777

class TestTheValuesComeFromTheCommittedExport:
    @pytest.mark.parametrize("host", ["ovs1", "arista-sw1"])
    def test_no_committed_export_is_refused_naming_the_export_card(self, net, host):
        server = Server(FakeOvs())
        p = OC.plan(LIST, host, session=server)
        assert not p["ok"] and p["at"] == "values"
        assert "no committed NSOT export" in p["error"]
        assert "the NSOT export card on SDN › Apps" in p["error"]
        assert server.opened == [] and p["hash"] == ""

    def test_an_ovs_plan_reads_the_export_and_its_hash_names_it(self, net):
        sha = _commit_export()
        p = OC.plan(LIST, "ovs1", session=Server(FakeOvs()))
        assert p["ok"], p["error"]
        assert p["export_sha256"] == sha and p["values"]["nsot.export_sha256"] == sha
        assert p["values"]["controller.address"] == "192.0.2.1"
        assert "tcp:192.0.2.1:6653" in p["program"][0]
        assert p["hash"] == OC.plan_hash(LIST, "ovs1", "ovs", p["program"], p["undo"],
                                         p["before"], sha)
        assert p["hash"] != OC.plan_hash(LIST, "ovs1", "ovs", p["program"], p["undo"],
                                         p["before"], "0" * 64)

    def test_an_export_committed_since_the_preview_refuses_the_apply(self, net, monkeypatch):
        _commit_export()
        _confirm(monkeypatch, "arista-sw1", "arista_eos")
        sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n")
        p = OC.plan(LIST, "arista-sw1", session=_session)
        assert p["ok"], p["error"]
        moved = _commit_export(_moved_controller_port())
        assert moved != p["export_sha256"]
        out = OC.apply(LIST, "arista-sw1", p["hash"], actor=ACTOR,
                       actor_verified="access-assertion", session=_session,
                       driver=lambda n, c: {"ok": True, "driver": Controller(lambda: [])})
        assert out["outcome"] == "refused" and p["hash"][:12] in out["error"]
        assert out["plan"]["hash"][:12] in out["error"] and sw.sets == []


# --------------------------------------------------------------------------- the session

class TestTheSessionCarriesOnlyTheOpenFlowLines:
    PROGRAM = ["interface Ethernet18", "   no lldp transmit", "   no lldp receive", "openflow",
               "   controller tcp:192.0.2.1:6653", "   bind mode interface",
               "   bind interface Ethernet18", "   no shutdown"]

    @pytest.mark.parametrize("ip", ["192.0.2.2", "2001:db8::6"], ids=("ipv4", "ipv6"))
    def test_the_lines_are_refused_unheld_and_sent_held(self, netmiko_fake, ip):
        sw = SwitchConn.at[ip] = Switch("arista-sw1.txt", running="")
        conn = _open("arista_eos", ip)
        with pytest.raises(C.DiscoveryOnly) as e:
            conn.send_config_set(self.PROGRAM)
        assert "held" in str(e.value) and sw.sets == [] and sw.modes == []
        with D.hold(LIST, "arista-sw1", "openflow config", ACTOR, ip=ip):
            conn.send_config_set(self.PROGRAM)
        assert sw.sets == [self.PROGRAM] and sw.modes == ["configure terminal"]

    @pytest.mark.parametrize("line", ["username admin secret x", "write memory",
                                      "   controller tcp:192.0.2.1:6653 ; reload",
                                      "   controller tcp:999.0.2.1:6653",
                                      "   controller tcp:[2001:db8::1]:6653", "reload",
                                      "interface Management1", "openflow\x07"])
    def test_a_line_off_its_shape_refuses_the_whole_set_even_held(self, netmiko_fake, line):
        sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="")
        conn = _open("arista_eos", "192.0.2.2")
        with D.hold(LIST, "arista-sw1", "openflow config", ACTOR, ip="192.0.2.2"):
            with pytest.raises(C.DiscoveryOnly) as e:
                conn.send_config_set(self.PROGRAM + [line])
        assert "send_config_set()" in str(e.value) and "arista_eos" in str(e.value)
        assert sw.sets == [] and sw.modes == []

    def test_config_mode_and_a_save_of_its_own_stay_refused_after_a_set(self, netmiko_fake):
        sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="")
        conn = _open("arista_eos", "192.0.2.2")
        with D.hold(LIST, "arista-sw1", "openflow config", ACTOR, ip="192.0.2.2"):
            conn.send_config_set(self.PROGRAM)
            for call in (conn.config_mode, conn.save_config):
                with pytest.raises(C.DiscoveryOnly):
                    call()
        assert sw.modes == ["configure terminal"] and not sw.saved

    def test_a_procurve_session_carries_its_one_line_forms_held(self, netmiko_fake):
        sw = SwitchConn.at["192.0.2.5"] = Switch("procurve-sw.txt", running="")
        lines = ["vlan 200 untagged 2", "lldp admin-status 2 disable",
                 "openflow controller-id 1 ip 192.0.2.1 port 6653 controller-interface vlan 100",
                 "openflow instance lab9 member vlan 200", "openflow instance lab9 enable",
                 "openflow enable", "no openflow instance lab9", "vlan 1 untagged 2"]
        conn = _open("hp_procurve", "192.0.2.5")
        with D.hold(LIST, "procurve-sw", "openflow config", ACTOR, ip="192.0.2.5"):
            conn.send_config_set(lines)
            with pytest.raises(C.DiscoveryOnly):
                conn.send_config_set(["openflow instance lab9 listen-port 6633"])
        assert sw.sets == [lines]

    @pytest.mark.parametrize("driver", ["hp_comware", "aruba_os"])
    def test_a_family_with_no_vendor_driver_still_refuses_every_set(self, netmiko_fake, driver):
        sw = SwitchConn.at["192.0.2.9"] = Switch("arista-sw1.txt", running="")
        conn = _open(driver, "192.0.2.9")
        with D.hold(LIST, "comware", "openflow config", ACTOR, ip="192.0.2.9"):
            with pytest.raises(C.DiscoveryOnly):
                conn.send_config_set(["openflow"])
        assert sw.sets == []


# --------------------------------------------------------------------------- the vendor plan

class TestTheVendorPlan:
    @pytest.mark.parametrize("host,capture,ip", [
        ("arista-sw1", "arista-sw1.txt", "192.0.2.2"),
        ("procurve-sw", "procurve-sw.txt", "192.0.2.5")])
    def test_the_lab_as_captured_plans_as_unchanged(self, net, host, capture, ip):
        sha = _commit_export()
        sw = SwitchConn.at[ip] = Switch(capture)
        p = OC.plan(LIST, host, session=_session)
        assert p["ok"], p["error"]
        assert p["unchanged"] and p["different"] == [] and p["undo"] == []
        assert p["export_sha256"] == sha and p["version"] in sw.version
        assert sw.reads == ["show version", "show running-config"] and sw.sets == []
        assert "running" not in str(p["before"]) and "password" not in str(p)

    def test_a_blank_arista_plans_its_whole_layer_and_an_undo_that_removes_it(self, net):
        _commit_export()
        SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n")
        p = OC.plan(LIST, "arista-sw1", session=_session)
        assert p["ok"], p["error"]
        assert p["program"] == ["interface Ethernet18", "   no lldp transmit",
                                "   no lldp receive", "interface Ethernet19",
                                "   no lldp transmit", "   no lldp receive", "openflow",
                                "   controller tcp:192.0.2.1:6653", "   bind mode interface",
                                "   bind interface Ethernet18", "   bind interface Ethernet19",
                                "   no shutdown"]
        assert p["undo"] == ["no openflow", "interface Ethernet18", "   lldp transmit",
                             "   lldp receive", "interface Ethernet19", "   lldp transmit",
                             "   lldp receive"]
        assert not p["unchanged"] and p["profile"] == "arista_eos"

    def test_a_bind_change_restarts_the_agent_and_its_undo_restarts_it_back(self, net):
        _commit_export()
        running = _running_config(_capture("arista-sw1.txt")).replace(
            "   bind interface Et18-19", "   bind interface Et18")
        SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running=running)
        p = OC.plan(LIST, "arista-sw1", session=_session)
        assert p["ok"], p["error"]
        assert p["program"][-2:] == ["   shutdown", "   no shutdown"]
        assert p["undo"] == ["openflow", "   no bind interface Ethernet19", "   shutdown",
                             "   no shutdown"]

    def test_a_blank_procurve_plans_an_undo_that_puts_each_port_back(self, net):
        _commit_export()
        SwitchConn.at["192.0.2.5"] = Switch("procurve-sw.txt", running=_blank_procurve())
        p = OC.plan(LIST, "procurve-sw", session=_session)
        assert p["ok"], p["error"]
        assert p["program"][:2] == ["vlan 200 untagged 2", "vlan 200 untagged 3"]
        assert p["undo"] == ["openflow disable", "openflow instance lab9 disable",
                             "no openflow instance lab9", "no openflow controller-id 1",
                             "lldp admin-status 2 tx_rx", "lldp admin-status 3 tx_rx",
                             "vlan 1 untagged 2", "vlan 1 untagged 3"]

    def test_a_port_in_no_vlan_before_cannot_be_put_back_and_is_refused(self, net):
        _commit_export()
        running = _blank_procurve().replace("   untagged 1-24\n", "   untagged 1,4-24\n")
        SwitchConn.at["192.0.2.5"] = Switch("procurve-sw.txt", running=running)
        p = OC.plan(LIST, "procurve-sw", session=_session)
        assert not p["ok"] and p["at"] == "undo" and "port 2" in p["error"]
        assert p["hash"] == ""

    def test_a_controller_the_template_cannot_remove_is_refused_naming_it(self, net):
        _commit_export()
        running = _running_config(_capture("arista-sw1.txt")).replace(
            "   controller tcp:192.0.2.1:6653", "   controller tcp:192.0.2.99:6633")
        sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running=running)
        p = OC.plan(LIST, "arista-sw1", session=_session)
        assert not p["ok"] and "would still differ" in p["error"]
        assert "tcp:192.0.2.99:6633" in p["error"] and sw.sets == []

    def test_an_ipv6_controller_is_refused_at_the_render_naming_it(self, net):
        records = copy.deepcopy(_records())
        for s in records["services"]:
            if s["name"] == "openflow":
                s["ipaddresses"] = [{"address": "2001:db8::1/64"}]
        _commit_export(records)
        SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n")
        p = OC.plan(LIST, "arista-sw1", session=_session)
        assert not p["ok"] and p["at"] == "render"
        assert "2001:db8::1" in p["error"] and "IPv4" in p["error"]

    def test_a_switch_managed_over_ipv6_plans_over_its_ipv6_session(self, net):
        _commit_export()
        sw = SwitchConn.at["2001:db8::6"] = Switch("arista-sw2.txt")
        p = OC.plan(LIST, "arista-sw2", session=_session)
        assert p["ok"], p["error"]
        assert p["unchanged"] and sw.reads == ["show version", "show running-config"]

    def test_a_family_with_no_vendor_driver_is_refused_by_name(self, net):
        _commit_export()
        p = OC.plan(LIST, "comware", session=_session)
        assert not p["ok"] and "hp_comware" in p["error"] and "no vendor driver" in p["error"]


# --------------------------------------------------------------------------- the vendor apply

@pytest.fixture
def lab(net, monkeypatch):
    rows = []
    monkeypatch.setattr("modules.sdn.flow_intent.record_operation",
                        lambda network, row: rows.append(row) or {"ok": True})
    monkeypatch.setattr(OC, "connection_name", lambda network, values, given="": "ryu")
    _commit_export()
    _confirm(monkeypatch, "arista-sw1", "arista_eos")
    _confirm(monkeypatch, "procurve-sw", "aruba_os_switch")
    return rows


def _apply(host, p, listed, **kw):
    ctl = Controller(listed)
    out = OC.apply(LIST, host, p["hash"], actor=ACTOR, actor_verified="access-assertion",
                   session=_session, driver=lambda n, c: {"ok": True, "driver": ctl},
                   sleep=lambda s: None, **kw)
    return out, ctl


class TestTheVendorApply:
    @pytest.mark.parametrize("host,capture,ip,running", [
        ("arista-sw1", "arista-sw1.txt", "192.0.2.2", "hostname x\n"),
        ("procurve-sw", "procurve-sw.txt", "192.0.2.5", None)], ids=("eos", "aruba_os_switch"))
    def test_confirmed_held_sent_verified_recorded_and_not_saved(self, lab, host, capture, ip,
                                                                running):
        sw = SwitchConn.at[ip] = Switch(capture, running=running if running is not None
                                        else _blank_procurve())
        p = OC.plan(LIST, host, session=_session)
        assert p["ok"], p["error"]
        out, ctl = _apply(host, p, lambda: [DPIDS[host]] if sw.sets else [])
        assert out["outcome"] == "verified" and out["ok"], out["error"]
        assert sw.sets == [p["program"]] and not sw.saved
        assert [c["state"] for c in out["verify"]["checks"]] == ["pass", "pass"]
        assert int(out["verify"]["dpid"], 16) == DPIDS[host] and ctl.reads == 1
        assert out["saved"] is False and "not saved to the startup" in out["save_words"]
        (row,) = lab
        assert row["outcome"] == "verified" and row["hash"] == p["hash"]
        assert row["response"] == {"kind": "openflow_config", "device": host,
                                   "template": p["template"],
                                   "template_capture": p["status"]["capture"]}
        assert row["export_sha256"] == p["export_sha256"] and row["saved"] is False

    def test_a_draft_template_sends_nothing_and_opens_no_session(self, net, monkeypatch):
        _commit_export()
        sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n")
        out = OC.apply(LIST, "arista-sw1", "x" * 64, actor=ACTOR,
                       actor_verified="access-assertion", session=_session,
                       driver=lambda n, c: {"ok": True, "driver": Controller(lambda: [])})
        assert out["outcome"] == "refused" and "draft" in out["error"]
        assert "arista_eos" in out["error"] and sw.reads == [] and sw.sets == []

    def test_a_switch_the_controller_never_lists_is_rolled_back_as_it_was(self, lab):
        sw = SwitchConn.at["192.0.2.5"] = Switch("procurve-sw.txt", running=_blank_procurve())
        before = S.parse("aruba_os_switch", sw.running)
        p = OC.plan(LIST, "procurve-sw", session=_session)
        out, ctl = _apply("procurve-sw", p, lambda: [])
        assert out["outcome"] == "rolled_back" and out["rollback"]["ok"], out["error"]
        assert ctl.reads == OC.VERIFY_READS and "switch list" in out["error"]
        assert sw.sets == [p["program"], p["undo"]]
        assert S.differences(before, S.parse("aruba_os_switch", sw.running)) == ([], [])
        assert lab[0]["outcome"] == "rolled_back"

    def test_a_line_the_switch_refuses_is_rolled_back(self, lab):
        sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n",
                                                 reply="% Invalid input at line 4")
        p = OC.plan(LIST, "arista-sw1", session=_session)
        out, ctl = _apply("arista-sw1", p, lambda: [])
        assert out["outcome"] == "rollback_failed" and "Invalid input" in out["error"]
        assert sw.sets == [p["program"], p["undo"]] and ctl.reads == 0

    def test_a_moved_switch_is_refused_naming_both_hashes(self, lab):
        sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n")
        p = OC.plan(LIST, "arista-sw1", session=_session)
        sw.running = "hostname x\ninterface Ethernet18\n   no lldp transmit\n   no lldp receive\n"
        out, _ctl = _apply("arista-sw1", p, lambda: [])
        assert out["outcome"] == "refused" and p["hash"][:12] in out["error"]
        assert out["plan"]["hash"][:12] in out["error"] and sw.sets == []

    def test_a_switch_already_as_intended_sends_nothing_and_verifies(self, lab):
        sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt")
        p = OC.plan(LIST, "arista-sw1", session=_session)
        out, _ctl = _apply("arista-sw1", p, lambda: [DPIDS["arista-sw1"]])
        assert out["outcome"] == "verified" and sw.sets == [] and out["sent"] == []
        assert lab[0]["outcome"] == "verified"

    def test_a_switch_held_by_another_operation_is_refused_by_name(self, lab):
        sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n")
        p = OC.plan(LIST, "arista-sw1", session=_session)
        import threading
        got = {}
        with D.hold(LIST, "arista-sw1", "deploy", "someone@example.invalid", ip="192.0.2.2"):
            t = threading.Thread(target=lambda: got.update(_apply("arista-sw1", p,
                                                                  lambda: [])[0]))
            t.start()
            t.join(30)
        assert got["outcome"] == "refused" and "someone@example.invalid" in got["error"]
        assert sw.sets == []


# --------------------------------------------------------------------------- the parsers

class TestTheParsersReadTheUndoForms:
    def test_eos_no_forms_remove_what_their_lines_made(self):
        text = "\n".join(["interface Ethernet18", "   no lldp transmit", "   no lldp receive",
                          "openflow", "   controller tcp:192.0.2.1:6653",
                          "   bind interface Ethernet18", "   no shutdown",
                          "openflow", "   no controller tcp:192.0.2.1:6653",
                          "   no bind interface Ethernet18",
                          "interface Ethernet18", "   lldp transmit"])
        m = S.eos(text)
        assert m["controllers"] == [] and m["bound"] == [] and m["lldp_off"] == []
        assert m["enabled"]
        assert S.eos(text + "\nno openflow")["enabled"] is False

    def test_procurve_no_forms_and_an_untagged_port_moving_vlan(self):
        text = "\n".join([
            "vlan 1 untagged 1-4", "vlan 200 untagged 2",
            "openflow controller-id 1 ip 192.0.2.1 port 6653 controller-interface vlan 100",
            "openflow instance lab9 member vlan 200", "openflow instance lab9 controller-id 1",
            "no openflow instance lab9 controller-id 1"])
        m = S.aruba_os_switch(text)
        assert m["untagged"] == {"1": ["1", "3", "4"], "200": ["2"]}
        assert m["instances"]["lab9"]["controller_ids"] == []
        gone = S.aruba_os_switch(text + "\nno openflow instance lab9\nno openflow controller-id 1"
                                 "\nvlan 1 untagged 2")
        assert gone["instances"] == {} and gone["controllers"] == {}
        assert gone["untagged"]["1"] == ["1", "2", "3", "4"] and gone["untagged"]["200"] == []


class TestWhatAProgramChanges:
    """`openflow_state.changes`: the plan's own comparison (`compare`), said value by value
    as before and after, for the result card and the record."""

    def test_each_value_the_switch_holds_otherwise_is_a_row_before_and_after(self):
        have = S.eos("hostname x\nopenflow\n   controller tcp:192.0.2.9:6633\n")
        want = S.eos("\n".join(["interface Ethernet18", "   no lldp transmit",
                                "   no lldp receive", "openflow",
                                "   controller tcp:192.0.2.1:6653",
                                "   bind interface Ethernet18", "   no shutdown"]))
        assert S.changes(want, have) == [
            {"value": "bound", "before": "none", "after": "Ethernet18"},
            {"value": "controllers", "before": "tcp:192.0.2.9:6633",
             "after": "tcp:192.0.2.1:6653"},
            {"value": "enabled", "before": "no", "after": "yes"},
            {"value": "lldp off", "before": "none", "after": "Ethernet18"}]
        # The same comparison in `differences`' sentences, one for one.
        different, unread = S.differences(want, have)
        assert len(different) == 4 and unread == []
        assert "controllers: wanted tcp:192.0.2.1:6653, the switch has tcp:192.0.2.9:6633" \
            in different
        assert S.changes(want, want) == []

    def test_a_value_the_switch_does_not_hold_reads_none_before_each_leaf_its_own_row(self):
        want = {"instances": {"lab9": {"version": "1.3", "member_vlans": ["200"]}},
                "enabled": True}
        assert S.changes(want, {"enabled": True}) == [
            {"value": "instances lab9 member vlans", "before": "none", "after": "200"},
            {"value": "instances lab9 version", "before": "none", "after": "1.3"}]
        assert S.differences(want, {"enabled": True}) == ([], ["instances"])


class TestTheShapes:
    @pytest.mark.parametrize("template,host,capture", [
        ("arista_eos", "arista-sw1", "arista-sw1.txt"),
        ("aruba_os_switch", "procurve-sw", "procurve-sw.txt")])
    def test_every_line_the_lab_renders_is_of_its_shape(self, template, host, capture):
        from tests.test_openflow_golden import fake_netbox as fb
        records = _records()
        get, _ = fb(records)
        import unittest.mock as mock
        with mock.patch("modules.inventory.source_config.load",
                        lambda name: {"source": "netbox",
                                      "filters": {"role": "openflow-switch"}}):
            export = X.parse(X.build(LIST, get=get,
                                     version=lambda: records["netbox_version"])["bytes"])
        from modules.sdn import openflow_values as V
        r = T.render(template, V.from_export(export, host)["values"])
        assert r["ok"], r["error"]
        assert CLI.line_refusal(template, r["program"]) == ""

    def test_a_vendor_driver_reads_its_version_and_dpid_from_its_own_answers(self):
        eos, aos = _capture("arista-sw1.txt"), _capture("procurve-sw.txt")
        assert CLI.Eos.version(eos) == "4.17.0F"
        assert CLI.ArubaOsSwitch.version(aos) == "K.16.02.0020"
        assert int(CLI.Eos.dpid(_answer(eos, "#show openflow")), 16) == DPIDS["arista-sw1"]
        assert int(CLI.ArubaOsSwitch.dpid(_answer(aos, "# show openflow instance lab9")),
                   16) == DPIDS["procurve-sw"]
