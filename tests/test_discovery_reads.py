"""Read-only discovery of a platform Mercury has no driver for (modules/discovery.py;
docs/LAB9_DISCOVERY.md, the Lab 9 sitting of 2026-11-05).

A device whose Netmiko driver is `arista_eos`, `hp_procurve` (and its two aliases), `aruba_os`
or `hp_comware` opens with that driver, is asked only its family's capture list, each command whole, and is
sent no config, save or commit call at all, held or not; its answers are masked by
`redact_text` and then line by line. Comware's `display` is a read on a Comware session only,
never on IOS (C2530); each answer is a capture named by device, command and run. Netmiko is faked at its boundary (`ConnectHandler`), so
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
DRIVERS = ("arista_eos", "hp_procurve", "aruba_osswitch", "aruba_procurve", "aruba_os",
           "hp_comware", "ovs_linux",
           # C2608: the host kind's driver (the SDN design's `linux_host`, netmiko's `linux`).
           "linux")
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
    # Released here, the tests' own (tests/ssh_slot_guard.py fails a test that leaves one).
    from tests import ssh_slot_guard
    ssh_slot_guard.release()
    with D._mu:
        stale = list(D._held.values())
        D._held.clear()
    for info in stale:
        if info["fd"] is not None:
            os.close(info["fd"])


def _open(driver, ip=ADDRESSES[0]):
    # A plain-account driver's session is opened only for a caller that declares it (C2625).
    return C.open_ssh(C.connection_params({"device_type": driver, "ip": ip, "username": "u"},
                                          password="p"), owner="test", plain=C.is_plain(driver))


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
        ("aruba_os", "ArubaSSH"), ("hp_comware", "HPComwareSSH"),
        ("ovs_linux", "OvsLinuxSSH"), ("linux", "LinuxSSH")])
    def test_the_locked_netmiko_has_each_driver(self, driver, cls):
        from netmiko.ssh_dispatcher import CLASS_MAPPER
        assert CLASS_MAPPER[driver].__name__ == cls

    def test_every_discovery_driver_is_on_the_table_and_no_cisco_one_is(self):
        assert set(discovery.DRIVERS) == set(DRIVERS)
        for cisco in ("cisco_ios", "cisco_xe", "cisco_iosxe"):
            assert not discovery.is_driver(cisco)
            assert discovery.command_refusal(cisco, "show clock") == ""


#: Commands on no capture list. EOS lists `show running-config all` (the operator, 2026-11-10),
#: so its case asks one still off its list; every other driver's cases are as they were.
OFF_THE_LIST = ("show clock", "show running-config all", "show version | json",
                "show tech-support", "reload", "write memory", "configure terminal")
EOS_LISTS = {"show running-config all": "show running-config diffs"}


def _off_the_list(driver):
    return [EOS_LISTS.get(c, c) if driver == "arista_eos" else c for c in OFF_THE_LIST]


class TestOnlyTheCaptureList:
    @pytest.mark.parametrize("driver", DRIVERS)
    def test_each_listed_command_runs_unheld(self, driver):
        conn = _open(driver)
        for command in discovery.commands_for(driver):
            conn.send_command(command)
        assert FakeConn.sent == list(discovery.commands_for(driver))

    @pytest.mark.parametrize("ip", ADDRESSES, ids=("ipv4", "ipv6"))
    @pytest.mark.parametrize("driver,command",
                             [(d, c) for d in DRIVERS for c in _off_the_list(d)])
    def test_a_command_off_the_list_is_refused_naming_it_and_nothing_is_sent(
            self, driver, ip, command):
        conn = _open(driver, ip)
        with pytest.raises(C.DiscoveryOnly) as e:
            conn.send_command(command)
        assert repr(command) in str(e.value) and ip in str(e.value)
        assert discovery.DRIVERS[driver]["family"] in str(e.value)
        assert FakeConn.sent == []

    @pytest.mark.parametrize("ip", ADDRESSES, ids=("ipv4", "ipv6"))
    def test_show_running_config_all_is_a_read_on_eos_only_and_whole(self, ip):
        """The operator, 2026-11-10: EOS's configuration with its defaults, an allowlisted read
        for the EOS platform only, as a whole command (no pipe, nothing after it)."""
        conn = _open("arista_eos", ip)
        conn.send_command("show running-config all")
        assert FakeConn.sent == ["show running-config all"]
        for near in ("show running-config all | section router", "show running-config all detail",
                     "show running-config all | redirect flash:x", "show running-config all; bash"):
            with pytest.raises(C.DiscoveryOnly):
                conn.send_command(near)
        assert FakeConn.sent == ["show running-config all"]
        for driver in DRIVERS:
            if driver != "arista_eos":
                why = discovery.command_refusal(driver, "show running-config all")
                assert "REFUSED" in why and "'show running-config all'" in why, driver
        assert discovery.listed_on("show running-config all") == ("arista_eos",)

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


#: Comware 7's credential lines, in the shapes of the H3C/HPE Comware 7 configuration guides
#: (`local-user` / `password hash`, `super password ... hash`, `snmp-agent community ...
#: cipher`); the secret parts are fakes. Shapes, not a capture.
COMWARE_SECRETS = ("$h$6$FAKEsaltFAKE$FAKEhashFAKEhashFAKE==", "$c$3$FAKEcipherFAKEcipher==")
COMWARE_CONFIG = "\n".join([
    " sysname sw7",
    "local-user admin class manage",
    f" password hash {COMWARE_SECRETS[0]}",
    f"super password role network-admin hash {COMWARE_SECRETS[0]}",
    f"snmp-agent community read cipher {COMWARE_SECRETS[1]}",
    "interface GigabitEthernet1/0/1",
    " port link-mode bridge",
    "return"])


class Session:
    def __init__(self):
        self.opened = []

    def __call__(self, dev, fn):
        self.opened.append(dict(dev))
        return fn(self)

    def answer(self, command):
        if command == "display current-configuration":
            return COMWARE_CONFIG
        if command in ("show running-config", "show running-config all"):
            return CONFIG
        return f"{command}: ok"


@pytest.fixture
def lab(monkeypatch, tmp_path):
    rows = [{"hostname": "sw1", "ip": ADDRESSES[0], "device_type": "arista_eos"},
            {"hostname": "sw6", "ip": ADDRESSES[1], "device_type": "hp_procurve"},
            {"hostname": "sw7", "ip": "192.0.2.37", "device_type": "hp_comware"},
            {"hostname": "sw8", "ip": "2001:db8::38", "device_type": "hp_comware"},
            {"hostname": "r1", "ip": "192.0.2.11", "device_type": "cisco_xe"},
            {"hostname": "r6", "ip": "2001:db8::11", "device_type": "cisco_ios"}]
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

    def test_eos_running_config_all_is_masked_in_what_is_kept_and_drawn(self, lab, tmp_path):
        """The same masking path as `show running-config`: the record, the stored file, the
        capture and what Show commands' result draws hold no secret."""
        from modules import reads_page
        r, _s = _run(["sw1"], ["show running-config", "show running-config all"])
        plain, with_defaults = r["results"]["sw1"]["answers"]
        assert with_defaults["state"] == "answered"
        assert with_defaults["answer"] == plain["answer"] and discovery.MASK in plain["answer"]
        stored = (tmp_path / LIST / "reads" / f"{r['id']}.json").read_text()
        name = f"sw1/{discovery.command_slug('show running-config all')}/{r['id']}"
        drawn = [g["answer"] for c in reads_page.result(LIST, r["id"])["commands"]
                 for g in c["groups"]]
        for secret in SECRETS:
            assert secret not in with_defaults["answer"] and secret not in stored, secret
            assert secret not in discovery.capture(LIST, name)["text"], secret
            assert all(secret not in text for text in drawn), secret
        assert "hostname sw1" in with_defaults["answer"]

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


# --------------------------------------------------------------------------- Comware (C2530)

COMWARE_DISPLAYS = discovery.commands_for("hp_comware")


class FakeComware(FakeConn):
    """netmiko 4.3.0's `HPComwareBase.enable`: config mode, `system-view`."""

    def enable(self):
        return self.config_mode("system-view")


class TestComwareDisplayIsItsOwn:
    @pytest.mark.parametrize("driver", ["cisco_ios", "cisco_xe"])
    @pytest.mark.parametrize("ip", ADDRESSES, ids=("ipv4", "ipv6"))
    @pytest.mark.parametrize("held", [False, True], ids=("unheld", "held"))
    @pytest.mark.parametrize("command", COMWARE_DISPLAYS + ("display openflow instance 1",))
    def test_display_is_refused_on_an_ios_session_held_or_not(self, driver, ip, held, command):
        conn = _open(driver, ip)
        import contextlib
        hold = (D.hold(LIST, "r1", "read", "op@example.invalid", ip=ip) if held
                else contextlib.nullcontext())
        with hold, pytest.raises(C.DiscoveryOnly) as e:
            conn.send_command(command)
        assert repr(command) in str(e.value) and "HP Comware" in str(e.value)
        assert driver in str(e.value) and ip in str(e.value)
        assert FakeConn.sent == []

    def test_an_ios_multiline_carrying_display_is_refused_while_held(self):
        conn = _open("cisco_xe")
        with D.hold(LIST, "r1", "deploy", "op@example.invalid", ip=ADDRESSES[0]):
            with pytest.raises(C.DiscoveryOnly):
                conn.send_multiline(["show clock", "display version"])
        assert FakeConn.sent == []

    def test_an_ios_session_still_sends_its_own_reads(self):
        conn = _open("cisco_ios")
        conn.send_command("show version")
        assert FakeConn.sent == ["show version"]

    @pytest.mark.parametrize("ip", ADDRESSES, ids=("ipv4", "ipv6"))
    def test_each_display_runs_on_a_comware_session(self, ip):
        assert "display version" in COMWARE_DISPLAYS and len(COMWARE_DISPLAYS) >= 8
        conn = _open("hp_comware", ip)
        for command in COMWARE_DISPLAYS:
            conn.send_command(command)
        assert FakeConn.sent == list(COMWARE_DISPLAYS)

    @pytest.mark.parametrize("driver", [d for d in DRIVERS if d != "hp_comware"])
    def test_display_is_refused_on_every_other_discovery_session(self, driver):
        conn = _open(driver)
        with pytest.raises(C.DiscoveryOnly):
            conn.send_command("display version")
        assert FakeConn.sent == []

    def test_a_comware_instance_is_one_number_and_one_view(self):
        for good in ("display openflow instance 1", "display openflow instance 12 controller",
                     "display openflow instance 3 listened",
                     "display openflow instance 3 flow-table"):
            assert discovery.command_refusal("hp_comware", good) == "", good
        for bad in ("display openflow instance a", "display openflow instance 1 group",
                    "display openflow instance 1 controller 2", "display openflow instance 12345",
                    "display openflow instance 1;reset"):
            assert "REFUSED" in discovery.command_refusal("hp_comware", bad), bad

    @pytest.mark.parametrize("ip", ADDRESSES, ids=("ipv4", "ipv6"))
    def test_comware_enable_never_enters_system_view(self, monkeypatch, ip):
        import netmiko
        monkeypatch.setattr(netmiko, "ConnectHandler", FakeComware)
        conn = _open("hp_comware", ip)
        assert conn.enable() == ""
        with pytest.raises(C.DiscoveryOnly):
            conn.config_mode("system-view")
        assert FakeConn.sent == []

    def test_a_comware_temp_connection_reads_without_system_view(self, monkeypatch):
        import netmiko
        monkeypatch.setattr(netmiko, "ConnectHandler", FakeComware)
        monkeypatch.setattr(C, "stored_connection_params", lambda dev: C.connection_params(
            {"device_type": "hp_comware", "ip": dev["ip"], "username": "u"}, password="p"))
        got = C.with_temp_connection({"ip": ADDRESSES[1]},
                                     lambda conn: conn.send_command("display version"))
        assert got == "ok" and FakeConn.sent == ["display version"]

    def test_the_platform_map_test_asks_comwares_own_version_read(self, monkeypatch):
        from modules import platform_maps as P
        from modules.nsot import reads
        asked = []
        monkeypatch.setattr(reads, "start", lambda network, hosts, commands, actor, **kw:
                            asked.append(commands) or {"run": "x"})
        P.test("lab9", "sw7", "hp_comware", "op@example.invalid")
        P.test("lab9", "sw1", "arista_eos", "op@example.invalid")
        assert asked == [["display version"], ["show version"]]


#: Each ZTP or auto-configuration status read, and the drivers whose list carries it.
ZTP_READS = {"show zerotouch": {"arista_eos"},
             "show dhcp client vendor-specific": {"hp_procurve", "aruba_osswitch",
                                                  "aruba_procurve"},
             "show ztp information": {"aruba_os"}}


class TestZtpStatusReads:
    @pytest.mark.parametrize("command", sorted(ZTP_READS))
    @pytest.mark.parametrize("driver", DRIVERS)
    def test_each_ztp_read_is_allowed_whole_only_on_its_vendor(self, command, driver):
        why = discovery.command_refusal(driver, command)
        assert (why == "") is (driver in ZTP_READS[command]), (driver, why)
        assert "REFUSED" in discovery.command_refusal(driver, command + " detail")

    @pytest.mark.parametrize("command", sorted(ZTP_READS))
    def test_listed_on_names_exactly_its_vendors_drivers(self, command):
        assert set(discovery.listed_on(command)) == ZTP_READS[command]


class TestTheReadsEngineAcrossDrivers:
    @pytest.mark.parametrize("host", ["sw7", "sw8"], ids=("ipv4", "ipv6"))
    def test_a_comware_device_answers_display(self, lab, host):
        r, s = _run([host], ["display version"])
        assert r["results"][host]["state"] == "answered" and len(s.opened) == 1

    @pytest.mark.parametrize("host", ["r1", "r6"], ids=("ipv4", "ipv6"))
    def test_display_on_an_ios_device_opens_no_session_and_is_named(self, lab, host):
        r, s = _run([host], ["display version"])
        out = r["results"][host]
        assert out["state"] == "failed" and "'display version'" in out["why"]
        assert "HP Comware" in out["why"] and s.opened == []

    def test_a_mixed_run_asks_display_only_of_the_comware_device(self, lab):
        r, s = _run(["sw7", "r1", "sw1"], ["display version"])
        assert r["results"]["sw7"]["state"] == "answered"
        assert r["results"]["r1"]["state"] == r["results"]["sw1"]["state"] == "failed"
        assert [d["hostname"] for d in s.opened] == ["sw7"]

    def test_the_run_level_check_knows_the_drivers_when_given(self):
        from modules.nsot import reads
        assert reads.refusal(["display version"], 1) == ""
        assert reads.refusal(["display version"], 1, drivers=("hp_comware",)) == ""
        assert "display" in reads.refusal(["display version"], 1, drivers=("cisco_xe",))
        assert "REFUSED" in reads.refusal(["display bogus"], 1)

    def test_ask_the_device_says_display_is_comwares_only(self):
        from modules import reads_page
        ios = reads_page.check("display version", 1, drivers=("cisco_ios",))
        comware = reads_page.check("display version", 1, drivers=("hp_comware",))
        assert not ios["ok"] and "HP Comware" in ios["why"]
        assert comware["ok"] and "HP Comware only" in comware["does"][0]


class TestTheCaptures:
    @pytest.mark.parametrize("host,command", [
        ("sw1", "show running-config"), ("sw8", "display current-configuration")],
        ids=("ipv4", "ipv6"))
    def test_each_capture_is_named_by_device_and_command_and_kept_masked(
            self, lab, tmp_path, host, command):
        r, _s = _run([host], ["show version" if host == "sw1" else "display version", command])
        got = discovery.captures(LIST, host)
        assert got["unreadable"] == []
        names = [c["name"] for c in got["captures"]]
        name = f"{host}/{discovery.command_slug(command)}/{r['id']}"
        assert name in names and len(names) == 2
        one = discovery.capture(LIST, name)
        assert one["device"] == host and one["command"] == command
        assert one["driver"] in DRIVERS and one["at"] and len(one["sha256"]) == 64
        stored = (tmp_path / LIST / "reads" / f"{r['id']}.json").read_text()
        for secret in SECRETS + COMWARE_SECRETS:
            assert secret not in one["text"], secret
            assert secret not in stored, secret
        assert ("hostname sw1" if host == "sw1" else "interface GigabitEthernet1/0/1") \
            in one["text"]

    def test_a_cisco_devices_reads_are_not_captures(self, lab):
        _run(["r1"], ["show clock"])
        assert discovery.captures(LIST, "r1")["captures"] == []

    def test_a_name_of_no_capture_is_none(self, lab):
        r, _s = _run(["sw1"], ["show version"])
        assert discovery.capture(LIST, f"sw1/show_clock/{r['id']}") is None
        assert discovery.capture(LIST, f"r1/show_version/{r['id']}") is None
        assert discovery.capture(LIST, "sw1/show_version/not-a-run") is None
        assert discovery.capture(LIST, "sw1") is None
