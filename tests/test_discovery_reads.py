"""Read-only discovery of a platform Mercury has no driver for (modules/discovery.py;
docs/LAB9_DISCOVERY.md, the Lab 9 sitting of 2026-11-05).

A device whose Netmiko driver is `arista_eos`, `hp_procurve` (and its two aliases) or `aruba_os`
opens with that driver, is asked only its family's capture list, each command whole, and is
sent no config, save or commit call at all, held or not; its answers are masked by
`redact_text` and then line by line. Netmiko is faked at its boundary (`ConnectHandler`), so
`open_ssh` and its guard run for real; the reads engine runs for real with its session faked at
its one seam, as tests/test_reads_engine.py does.

The masking cases are line SHAPES measured against `redact_text` on 2026-11-05, not captures:
no switch of these families has been read yet. Each is replaced by a real capture's line once
the sitting has read one (the register's row for it).
"""

import os

import pytest

from modules import connection as C
from modules import discovery
from modules.nsot import device_ops as D

LIST = "Lab"
DRIVERS = ("arista_eos", "hp_procurve", "aruba_osswitch", "aruba_procurve", "aruba_os")
ADDRESSES = ("192.0.2.31", "2001:db8::31")


class FakeConn:
    """A Netmiko session at its boundary: what it was opened with, and every command sent."""
    opened, sent = [], []

    def __init__(self, **params):
        FakeConn.opened.append(dict(params))
        self.ip = params["ip"]

    def enable(self):
        pass

    def find_prompt(self):
        return "sw1#"

    def send_command(self, cmd, **kw):
        FakeConn.sent.append(cmd)
        return "ok"

    send_command_timing = send_command

    def send_config_set(self, cmds, **kw):
        FakeConn.sent.extend(cmds)
        return "ok"

    def send_multiline(self, cmds, **kw):
        FakeConn.sent.extend(cmds)
        return "ok"

    def save_config(self, *a, **k):
        FakeConn.sent.append("write memory")
        return "ok"

    def config_mode(self, *a, **k):
        FakeConn.sent.append("configure terminal")
        return ""

    def commit(self, *a, **k):
        FakeConn.sent.append("commit")
        return ""

    def disconnect(self):
        pass


@pytest.fixture(autouse=True)
def fake_netmiko(monkeypatch):
    import netmiko

    FakeConn.opened, FakeConn.sent = [], []
    monkeypatch.setattr(netmiko, "ConnectHandler", FakeConn)
    monkeypatch.setattr(C, "vty_lines", lambda ip: (5, "the test's device"))
    C._sessions.clear()
    yield
    C._sessions.clear()
    # The cross-process slots (`ssh_slots/<ip>/<n>.lock` flocks) of sessions these tests left
    # open: clearing the count leaves their locks held by this worker, so a later test's child
    # process found the device's budget full (test_ssh_slots_across_processes, 2026-11-05).
    with C._sessions_mu:
        for key, (fd, _sid) in list(C._slots.items()):
            C._slots.pop(key, None)
            try:
                os.close(fd)
            except OSError:
                pass
    with D._mu:
        stale = list(D._held.values())
        D._held.clear()
    for info in stale:
        if info["fd"] is not None:
            os.close(info["fd"])


def _open(driver, ip=ADDRESSES[0]):
    return C.open_ssh(C.connection_params({"device_type": driver, "ip": ip, "username": "u"},
                                          password="p"), owner="test")


class TestEachTypeOpensWithItsDriver:
    @pytest.mark.parametrize("driver", DRIVERS)
    @pytest.mark.parametrize("ip", ADDRESSES, ids=("ipv4", "ipv6"))
    def test_the_session_is_opened_with_the_rows_driver(self, driver, ip):
        conn = _open(driver, ip)
        assert FakeConn.opened[-1]["device_type"] == driver
        assert FakeConn.opened[-1]["ip"] == ip
        conn.disconnect()

    @pytest.mark.parametrize("driver,cls", [
        ("arista_eos", "AristaSSH"), ("hp_procurve", "HPProcurveSSH"),
        ("aruba_osswitch", "HPProcurveSSH"), ("aruba_procurve", "HPProcurveSSH"),
        ("aruba_os", "ArubaSSH")])
    def test_the_locked_netmiko_has_each_driver(self, driver, cls):
        from netmiko.ssh_dispatcher import CLASS_MAPPER
        assert CLASS_MAPPER[driver].__name__ == cls

    def test_every_discovery_driver_is_on_the_table_and_no_cisco_one_is(self):
        assert set(discovery.DRIVERS) == set(DRIVERS)
        for cisco in ("cisco_ios", "cisco_xe", "cisco_iosxe"):
            assert not discovery.is_driver(cisco)
            assert discovery.command_refusal(cisco, "show clock") == ""


class TestOnlyTheCaptureList:
    @pytest.mark.parametrize("driver", DRIVERS)
    def test_each_listed_command_runs_unheld(self, driver):
        conn = _open(driver)
        for command in discovery.commands_for(driver):
            conn.send_command(command)
        assert FakeConn.sent == list(discovery.commands_for(driver))

    @pytest.mark.parametrize("driver", DRIVERS)
    @pytest.mark.parametrize("ip", ADDRESSES, ids=("ipv4", "ipv6"))
    @pytest.mark.parametrize("command", ["show clock", "show running-config all",
                                         "show version | json", "show tech-support",
                                         "reload", "write memory", "configure terminal"])
    def test_a_command_off_the_list_is_refused_naming_it_and_nothing_is_sent(
            self, driver, ip, command):
        conn = _open(driver, ip)
        with pytest.raises(C.DiscoveryOnly) as e:
            conn.send_command(command)
        assert repr(command) in str(e.value) and ip in str(e.value)
        assert discovery.DRIVERS[driver]["family"] in str(e.value)
        assert FakeConn.sent == []

    def test_a_command_off_the_list_is_refused_even_while_held(self):
        conn = _open("arista_eos")
        with D.hold(LIST, "sw1", "deploy", "op@example.invalid", ip=ADDRESSES[0]):
            with pytest.raises(C.DiscoveryOnly):
                conn.send_command("show clock")
        assert FakeConn.sent == []

    def test_a_procurve_openflow_instance_is_one_token_of_its_shape(self):
        assert discovery.command_refusal("hp_procurve", "show openflow instance of1") == ""
        for bad in ("show openflow instance a b", "show openflow instance x;reload",
                    "show openflow instance " + "a" * 40):
            assert "REFUSED" in discovery.command_refusal("hp_procurve", bad), bad
        assert "REFUSED" in discovery.command_refusal("arista_eos", "show openflow instance of1")

    def test_spacing_and_case_do_not_change_a_listed_command(self):
        assert discovery.command_refusal("arista_eos", "  SHOW   version ") == ""


class TestNoDeviceChangingOperation:
    @pytest.mark.parametrize("driver", DRIVERS)
    @pytest.mark.parametrize("ip", ADDRESSES, ids=("ipv4", "ipv6"))
    @pytest.mark.parametrize("call,name", [
        (lambda c: c.send_config_set(["openflow", "enable"]), "send_config_set()"),
        (lambda c: c.save_config(), "save_config()"),
        (lambda c: c.config_mode(), "config_mode()"),
        (lambda c: c.commit(), "commit()"),
        (lambda c: c.send_multiline(["show version"]), "send_multiline()")],
        ids=("deploy or restore", "save", "configure", "commit", "multiline"))
    def test_refused_by_name_even_while_held(self, driver, ip, call, name):
        conn = _open(driver, ip)
        with D.hold(LIST, "sw1", "deploy", "op@example.invalid", ip=ip):
            with pytest.raises(C.DiscoveryOnly) as e:
                call(conn)
        assert name in str(e.value) and driver in str(e.value) and ip in str(e.value)
        assert FakeConn.sent == []

    @pytest.mark.parametrize("driver", DRIVERS)
    def test_a_parse_render_or_deploy_refuses_the_platform(self, driver):
        from modules.nsot import platform
        with pytest.raises(platform.UnknownPlatform):
            platform.require_platform({"hostname": "sw1", "device_type": driver})

    def test_a_cisco_session_keeps_its_held_write(self):
        conn = _open("cisco_xe")
        with D.hold(LIST, "r1", "deploy", "op@example.invalid", ip=ADDRESSES[0]):
            conn.send_config_set(["interface Gi2"])
        assert FakeConn.sent == ["interface Gi2"]


# --------------------------------------------------------------------------- the reads engine

#: Credential lines in these platforms' shapes, each measured to pass `redact_text` with its
#: secret whole or in part on 2026-11-05 (module docstring). The secret parts are fakes.
SECRETS = ("6$abcdefgh$FAKEhashFAKEhash", "0123456789abcdef0123456789abcdef01234567",
           "AQBapFAKEciphertext==", "plainFAKE99")
CONFIG = "\n".join([
    "hostname sw1",
    f"username admin privilege 15 role network-admin secret sha512 ${SECRETS[0]}",
    f"enable secret sha512 ${SECRETS[0]}",
    f'password manager user-name "admin" sha1 "{SECRETS[1]}"',
    f"user admin group administrators password ciphertext {SECRETS[2]}",
    f'password operator user-name "op" plaintext "{SECRETS[3]}"',
    "interface Ethernet1",
    "   description uplink",
    "end"])


class Session:
    def __init__(self):
        self.opened = []

    def __call__(self, dev, fn):
        self.opened.append(dict(dev))
        return fn(self)

    def answer(self, command):
        return CONFIG if command == "show running-config" else f"{command}: ok"


@pytest.fixture
def lab(monkeypatch, tmp_path):
    rows = [{"hostname": "sw1", "ip": ADDRESSES[0], "device_type": "arista_eos"},
            {"hostname": "sw6", "ip": ADDRESSES[1], "device_type": "hp_procurve"},
            {"hostname": "r1", "ip": "192.0.2.11", "device_type": "cisco_xe"}]
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / name))
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path: [dict(d) for d in rows])
    monkeypatch.setattr("modules.commands.run_device_command", lambda conn, c: conn.answer(c))
    monkeypatch.setattr("modules.list_settings.value", lambda ln, key, default=None: default)
    return rows


def _run(hosts, commands):
    from modules.nsot import reads
    s = Session()
    return reads.run(LIST, hosts, commands, "op@example.invalid", session=s), s


class TestTheCapture:
    @pytest.mark.parametrize("host", ["sw1", "sw6"], ids=("ipv4", "ipv6"))
    def test_a_command_off_the_list_opens_no_session_and_is_named(self, lab, host):
        r, s = _run([host], ["show version", "show clock"])
        out = r["results"][host]
        assert out["state"] == "failed" and "'show clock'" in out["why"]
        assert s.opened == []

    @pytest.mark.parametrize("host", ["sw1", "sw6"], ids=("ipv4", "ipv6"))
    def test_the_capture_is_masked_and_keeps_its_shape(self, lab, host):
        r, s = _run([host], ["show version", "show running-config"])
        (dev,) = s.opened
        assert dev["device_type"] in DRIVERS
        version, config = r["results"][host]["answers"]
        assert version["state"] == config["state"] == "answered"
        for secret in SECRETS:
            assert secret not in config["answer"], secret
        assert "username admin privilege 15 role network-admin secret" in config["answer"]
        assert "   description uplink" in config["answer"] and "hostname sw1" in config["answer"]

    def test_a_cisco_device_keeps_the_read_only_allowlist(self, lab):
        r, s = _run(["r1"], ["show clock"])
        assert r["results"]["r1"]["state"] == "answered" and len(s.opened) == 1

    def test_mask_lines_masks_the_rest_of_a_credential_line_only(self):
        assert discovery.mask_lines("ip ssh key-type rsa\nsnmp-server community x ro") == \
            f"ip ssh key-type rsa\nsnmp-server community {discovery.MASK}"


# --------------------------------------------------------------------------- how it enters

def _form(**over):
    from werkzeug.datastructures import MultiDict
    form = {"kind": "platforms", "slug": ["cisco-ios"], "driver": ["cisco_ios"],
            "dialect": ["cisco_ios"], "transport": ["ssh"], "default_driver": ""}
    form.update(over)
    return MultiDict([(k, x) for k, v in form.items() for x in (v if isinstance(v, list) else [v])])


class TestThePlatformMap:
    """Settings › Installation › Platforms and roles: a NetBox platform is mapped to a discovery
    driver with no dialect, so its devices load into a NetBox-sourced network read only."""

    def test_the_discovery_drivers_are_offered(self):
        from modules import platform_maps as P
        assert set(DRIVERS) <= set(P.supported_drivers())
        assert "cisco_ios" in P.supported_drivers()

    @pytest.mark.parametrize("driver", DRIVERS)
    def test_a_discovery_platform_is_mapped_with_no_dialect(self, driver):
        from modules import platform_maps as P
        p = P.proposal("platforms", _form(new_slug="vendor-os", new_driver=driver,
                                          new_dialect="", new_transport="ssh"))
        assert p["platform_map"]["vendor-os"] == {
            "netmiko_device_type": driver, "template_dir": "", "deploy_transport": "ssh",
            "supports_netconf": False}

    def test_a_discovery_driver_with_a_dialect_is_refused_naming_both(self):
        from modules import platform_maps as P
        with pytest.raises(P.Refused) as e:
            P.proposal("platforms", _form(new_slug="vendor-os", new_driver="arista_eos",
                                          new_dialect="cisco_ios", new_transport="ssh"))
        assert "arista_eos" in str(e.value) and "'cisco_ios'" in str(e.value)

    def test_a_cisco_driver_still_needs_its_dialect(self):
        from modules import platform_maps as P
        with pytest.raises(P.Refused) as e:
            P.proposal("platforms", _form(new_slug="vendor-os", new_driver="cisco_ios",
                                          new_dialect="", new_transport="ssh"))
        assert "is not one Mercury knows" in str(e.value)

    def test_its_netbox_device_loads_with_the_driver_and_no_platform(self, monkeypatch):
        from modules.inventory import netbox_source
        from modules.nsot import platform
        pmap = {"vendor-os": {"netmiko_device_type": "arista_eos", "template_dir": ""}}
        lookup = lambda key, default=None: pmap if key == "platform_map" else default  # noqa: E731
        monkeypatch.setattr(netbox_source, "get_setting", lookup)
        monkeypatch.setattr("modules.settings_schema.get_setting", lookup)
        assert netbox_source.map_platform("vendor-os") == ("arista_eos", "")
        row = {"hostname": "sw1", "device_type": "arista_eos", "_platform": "vendor-os"}
        assert platform.platform_for_device(row) == ""
        with pytest.raises(platform.UnknownPlatform):
            platform.require_platform(row)

    def test_the_card_says_a_discovery_row_is_read_only(self, monkeypatch):
        from modules import platform_maps as P
        pmap = {"vendor-os": {"netmiko_device_type": "hp_procurve", "template_dir": ""}}
        monkeypatch.setattr(P, "_maps", lambda: {"platform_map": pmap, "default_driver": ""})
        (row,) = P.view()["rows"]
        assert row["problems"] == [P.READ_ONLY_WORDS]


class TestMaskLines:
    def test_mask_lines_keeps_lines_with_no_credential_word_byte_for_byte(self):
        text = "interface Ethernet1\n   description keyed-uplink\r\nopenflow\n  controller x\n"
        assert discovery.mask_lines(text) == text
