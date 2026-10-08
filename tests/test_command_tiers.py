"""The command policy's three tiers (NSOT_READS.md section 11, the operator, 2026-10-08).

An ALLOWLIST of verbs with validated arguments, never a denylist: Tier 1 runs as a read through
the reads engine, each argument one token of its shape; Tier 2 (recoverable) and Tier 3
(destructive) are refused naming the tier and where to go instead; anything in no tier is
refused naming the nearest Tier 1 verb. `modules/readonly_commands.py` decides; the engine
(`modules/nsot/reads.py`) names which extras a person and the agent may run.

The local and remote file systems are not typed from memory: they come from the real
`show file systems` captures of a C8000v and a vIOS (`tests/fixtures/operational/`), each by
the TYPE column the device prints, so the expectation is independent of `LOCAL_FS`.
"""

import os

import pytest

from modules import readonly_commands as rc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPS = os.path.join(ROOT, "tests", "fixtures", "operational")
PERSON = rc.EXTRAS


def _ok(command, extra=PERSON):
    return rc.refusal(command, extra) == ""


def _refused(command, extra=PERSON):
    why = rc.refusal(command, extra)
    assert why.startswith("REFUSED"), (command, why)
    return why


# --------------------------------------------------------------------------- Tier 1: the reads

class TestPingAndTracerouteAreBounded:
    @pytest.mark.parametrize("cmd", [
        "ping 192.0.2.1", "ping ip 192.0.2.1", "ping ipv6 2001:db8::1", "ping r2.example.net",
        "ping vrf mgmt 192.0.2.1", "ping 192.0.2.1 repeat 100", "ping 192.0.2.1 timeout 3",
        "ping 192.0.2.1 repeat 100 timeout 3", "ping 192.0.2.1 size 1500 df-bit",
        "ping 192.0.2.1 source Loopback0", "ping 192.0.2.1 source GigabitEthernet0/0",
        "ping 192.0.2.1 | include Success",
        "traceroute 192.0.2.1", "traceroute vrf mgmt 192.0.2.1 numeric",
        "traceroute 192.0.2.1 timeout 1 probe 1 ttl 1 10 source Loopback0 port 33434",
    ])
    def test_allowed(self, cmd):
        assert _ok(cmd), rc.refusal(cmd, PERSON)
        assert rc.refusal(cmd) == "", "a read: every path allows it"

    @pytest.mark.parametrize("cmd, words", [
        ("ping 192.0.2.1 repeat 100000", "1 to 100"),
        ("ping 192.0.2.1 repeat 0", "1 to 100"),
        ("ping 192.0.2.1 size 65000", "36 to 1500"),
        ("ping 192.0.2.1 timeout 60", "0 to 10"),
        ("ping 192.0.2.1 sweep", "not one of ping's options"),
        ("ping 192.0.2.1 rep 5", "not one of ping's options"),
        ("ping 192.0.2.1 repeat", "needs a value"),
        ("ping 192.0.2.1 source", "needs a value"),
        ("ping 192.0.2.1 source Lo0;reload", "not an interface or an address"),
        ("ping vrf", "needs the VRF's name"),
        ("ping vrf a;b 192.0.2.1", "not a VRF name"),
        ("ping $(x)", "not an address or a host name"),
        ("traceroute 192.0.2.1 ttl 5 1", "a minimum and a maximum"),
        ("traceroute 192.0.2.1 ttl 1 99", "a minimum and a maximum"),
        ("traceroute 192.0.2.1 probe 20", "1 to 5"),
    ])
    def test_each_argument_has_its_shape(self, cmd, words):
        assert words in _refused(cmd), (cmd, rc.refusal(cmd, PERSON))

    def test_the_worst_case_names_both_operands(self):
        """A plain traceroute is 3 x 3 s x 30 hops = 270 s (IOS's defaults), within the 300 s
        bound; a 5 s timeout makes it 450 s, refused naming the sum and the bound."""
        assert _ok("traceroute 192.0.2.1")
        why = _refused("traceroute 192.0.2.1 timeout 5")
        assert "= 450 s" in why and f"{rc.BOUND_SECONDS} s" in why, why
        why = _refused("ping 192.0.2.1 repeat 100 timeout 4")
        assert "= 400 s" in why, why

    def test_the_engine_waits_the_worst_case(self):
        assert rc.bound_seconds("traceroute 192.0.2.1") == 270 + rc.SLACK_SECONDS
        assert rc.bound_seconds("ping 192.0.2.1") == 5 * 2 + rc.SLACK_SECONDS
        assert rc.bound_seconds("ping 192.0.2.1 repeat 10 timeout 1") == 10 + rc.SLACK_SECONDS
        assert rc.bound_seconds("show clock") == 0

    @pytest.mark.parametrize("cmd", ["ping", "traceroute", "ping vrf clab-mgmt", "ping ip"])
    def test_a_target_less_ping_is_a_dialogue(self, cmd):
        assert "interactive" in _refused(cmd)


def _file_systems():
    """``{prefix: type}`` from the real captures, every alias with its line's type."""
    out = {}
    for name in ("r1__show_file_systems.txt", "s1__show_file_systems.txt"):
        with open(os.path.join(OPS, name), encoding="utf-8") as fh:
            for line in fh:
                cols = line.replace("*", " ").split()
                if len(cols) >= 5 and cols[0] not in ("Size(b)",) and cols[2] in (
                        "disk", "nvram", "network", "opaque", "flash"):
                    for prefix in cols[4:]:
                        out[prefix] = cols[2]
    return out


class TestDirAndMoreReadOnlyLocalStorage:
    def test_every_local_file_system_the_devices_print_is_allowed(self):
        local = sorted(p for p, t in _file_systems().items() if t in ("disk", "nvram"))
        assert len(local) >= 7, local        # bootflash: flash: crashinfo: webui: nvram: flash0..3:
        for prefix in local:
            assert _ok(f"dir {prefix}"), (prefix, rc.refusal(f"dir {prefix}", PERSON))
            assert _ok(f"more {prefix}vlan.dat"), prefix

    def test_every_network_file_system_the_devices_print_is_refused(self):
        """The transfer protocols are the device reaching another host: `dir tftp:` passed
        the verb-only allowlist, having no `://` in it."""
        remote = sorted(p for p, t in _file_systems().items() if t == "network")
        assert len(remote) >= 6, remote      # tftp: rcp: http: ftp: scp: sftp: https: pram:
        for prefix in remote:
            assert "not a local file system" in _refused(f"dir {prefix}"), prefix
            assert "not a local file system" in _refused(f"more {prefix}x"), prefix

    @pytest.mark.parametrize("cmd", ["dir", "dir /all", "dir /recursive flash:",
                                     "more /ascii flash:x.txt", "more nvram:startup-config",
                                     "more system:running-config | section snmp",
                                     "more vlan.dat"])
    def test_allowed(self, cmd):
        assert _ok(cmd), rc.refusal(cmd, PERSON)

    @pytest.mark.parametrize("cmd, words", [
        ("more", "needs a file"), ("dir /format flash:", "not one of dir's options"),
        ("dir flash: tftp:", "follows it"), ("more flash:a;b", "not a file path"),
        ("more null:x", "not a local file system"), ("more tar:x", "not a local file system"),
    ])
    def test_refused(self, cmd, words):
        assert words in _refused(cmd), rc.refusal(cmd, PERSON)


# --------------------------------------------------------------------------- Tier 1: the extras

class TestTheExtras:
    @pytest.mark.parametrize("cmd", [
        "verify /md5 flash:c8000v.bin", "verify /md5 bootflash:x.bin 0123456789abcdef0123456789abcdef",
        "send log Mercury logging path test", "send log 6 Mercury logging path test",
        'send log 4 "quoted, as the operator wrote it"', "send log " + "x" * rc.SEND_LOG_TEXT_MAX,
        "terminal length 0", "terminal width 512", "term len 0".replace("len", "length"),
    ])
    def test_a_person_runs_them_through_the_engine(self, cmd):
        assert _ok(cmd), rc.refusal(cmd, PERSON)

    @pytest.mark.parametrize("cmd", ["verify /md5 flash:x.bin", "send log 6 x",
                                     "terminal length 0"])
    def test_no_other_path_runs_them(self, cmd):
        """The default allows the reads only: the v1 routes and the connection guard keep the
        five verbs they had (no new capability on a v1 page)."""
        assert "runs only through the reads engine" in _refused(cmd, ())

    @pytest.mark.parametrize("cmd, words", [
        ("verify flash:x", "verify /md5 <local file>"), ("verify /md5", "needs a file"),
        ("verify /md5 tftp:x", "not a local file system"),
        ("verify /md5 flash:x nothex", "not an MD5"),
        ("send log", "needs the line"), ("send log 9 x", "0 to 7"),
        ("send log 6", "needs the line"),
        ("send log x | redirect flash:y", "never piped"),
        ("send log " + "x" * (rc.SEND_LOG_TEXT_MAX + 1), f"at most {rc.SEND_LOG_TEXT_MAX}"),
        ("send log café", "not plain printable"),
        ("terminal monitor", "terminal length"), ("terminal length 9999", "terminal length"),
        ("terminal length 0 | include x", "no '|'"),
    ])
    def test_each_has_its_shape(self, cmd, words):
        assert words in _refused(cmd), rc.refusal(cmd, PERSON)

    @pytest.mark.parametrize("level", [4, 5, 6, 7])
    def test_levels_4_to_7_run_freely(self, level):
        assert _ok(f"send log {level} a line"), rc.refusal(f"send log {level} a line", PERSON)

    @pytest.mark.parametrize("level", [0, 1, 2, 3])
    def test_levels_0_to_3_need_a_reason_and_say_test(self, level):
        """They can fire critical alert rules (the operator, 2026-10-08)."""
        from modules.nsot import reads
        cmd = f"send log {level} TEST of the alert path"
        why = _refused(cmd, ("send log",))
        assert "stated reason of three words" in why and "TEST" in why, why
        assert reads.refusal([cmd], 1, "person", reason="too short").startswith("`")
        assert reads.refusal([cmd], 1, "person", reason="checking the critical alert") == ""
        unmarked = f"send log {level} the alert path"
        why = reads.refusal([unmarked], 1, "person", reason="checking the critical alert")
        assert "the word TEST is not in it" in why, why
        assert reads.refusal([cmd], 1, "agent", reason="checking the critical alert"), \
            "the agent never logs, reason or not"

    def test_a_run_records_its_reason(self, monkeypatch, tmp_path):
        from modules.nsot import reads
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path / n))
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda path: [{"hostname": "r2", "ip": "192.0.2.12"}])
        monkeypatch.setattr("modules.list_settings.value", lambda ln, k, d=None: d)
        monkeypatch.setattr("modules.commands.run_device_command", lambda conn, c, **kw: "")
        record = reads.run("Lab", ["r2"], ["send log 2 TEST critical rule"], "op@example.invalid",
                           reason="proving the critical rule fires",
                           session=lambda dev, fn: fn(object()))
        assert record["state"] == "done" and record["reason"] == "proving the critical rule fires"

    def test_send_is_only_send_log(self):
        """`send *` messages every terminal and asks for its text interactively."""
        _refused("send *")
        _refused("se log x")

    def test_the_agent_reads_a_file_and_writes_nothing(self):
        from modules.ai_assistant import _read_only_refusal
        from modules.nsot import reads
        assert _read_only_refusal(["verify /md5 flash:x.bin"]) == ""
        for cmd in ("send log 6 x", "terminal length 0"):
            assert _read_only_refusal([cmd]).startswith("REFUSED"), cmd
            assert reads.refusal([cmd], 1, by="agent"), cmd
            assert reads.refusal([cmd], 1) == "", cmd


# --------------------------------------------------------------------------- Tiers 2 and 3

TIER2 = ["clear counters", "clear counters GigabitEthernet1", "clear arp-cache", "clear arp",
         "clear ip bgp 192.0.2.1 soft", "clear ip bgp 192.0.2.1 soft in", "clear logging",
         "undebug all", "undeb all", "no debug all"]

#: (command, words its refusal names: where to go instead)
TIER3 = [("reload", "Reload (P.14)"), ("reload in 5", "Reload (P.14)"),
         ("clear ip bgp *", "hard reset"), ("clear ip bgp 192.0.2.1", "hard reset"),
         ("clear ip ospf process", "hard reset"),
         ("write erase", "files or its saved configuration"),
         ("erase startup-config", "files or its saved configuration"),
         ("delete flash:x", "files or its saved configuration"),
         ("format flash:", "files or its saved configuration"),
         ("copy flash:x tftp:", "Capture"), ("copy tftp: running-config", "deploy"),
         ("debug ip ospf adj", "Loki"), ("crypto key zeroize rsa", "SSH key"),
         ("request platform software package install", "software"),
         ("install add file flash:x", "software")]


class TestTheOtherTiersAreRefusedByName:
    @pytest.mark.parametrize("cmd", TIER2)
    def test_tier_2_names_its_operation(self, cmd):
        why = _refused(cmd)
        assert "Tier 2" in why and "Run a privileged command" in why, why
        assert "not built yet" in why and "Nothing was sent" in why, why

    @pytest.mark.parametrize("cmd, words", TIER3)
    def test_tier_3_names_where_to_go(self, cmd, words):
        why = _refused(cmd)
        assert "Tier 3" in why and words in why and "Nothing was sent" in why, why

    @pytest.mark.parametrize("cmd", ["configure terminal", "conf t", "configure replace flash:x"])
    def test_configure_mode_is_the_pipelines(self, cmd):
        assert "deploy pipeline" in _refused(cmd)

    @pytest.mark.parametrize("cmd", ["write", "wr", "write memory", "wr mem", "copy run start",
                                     "copy running-config startup-config"])
    def test_a_save_names_persist(self, cmd):
        assert "Persist" in _refused(cmd)

    def test_reload_says_it_is_not_on_v2_yet(self):
        """Never send the operator to today's (v1) pages: the refusal says plainly that v2
        cannot do it yet."""
        why = _refused("reload")
        assert "not on v2 yet" in why and "today's" not in why, why

    @pytest.mark.parametrize("cmd, near", [("sow ip int br", "show"), ("pign 192.0.2.1", "ping"),
                                           ("tracerout 192.0.2.1", "traceroute"),
                                           ("verfy /md5 flash:x", "verify")])
    def test_no_tier_names_the_nearest_verb(self, cmd, near):
        why = _refused(cmd)
        assert "in no tier" in why and f"Did you mean {near!r}" in why, why

    def test_the_allowlist_decides_not_the_tiers(self):
        """A verb no tier names is refused all the same: an allowlist, never a denylist."""
        assert "in no tier" in _refused("frobnicate the device")
        assert "in no tier" in _refused("setup")
        assert "in no tier" in _refused("tclsh")


# --------------------------------------------------------------------------- the engine

class TestTheEngineRunsTierOne:
    def test_a_person_s_run_sends_them_with_their_bounds(self, monkeypatch, tmp_path):
        from modules.nsot import reads
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path / n))
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda path: [{"hostname": "r2", "ip": "192.0.2.12"}])
        monkeypatch.setattr("modules.list_settings.value", lambda ln, k, d=None: d)
        sent = []
        monkeypatch.setattr("modules.commands.run_device_command",
                            lambda conn, c, **kw: sent.append((c, kw)) or "")
        commands = ["traceroute 192.0.2.1", "send log 6 Mercury test", "verify /md5 flash:x.bin",
                    "terminal length 0", "show clock"]
        record = reads.run("Lab", ["r2"], commands, "op@example.invalid",
                           session=lambda dev, fn: fn(object()))
        assert record["state"] == "done", record
        assert [c for c, _ in sent] == commands
        assert dict(sent)["traceroute 192.0.2.1"] == {"read_timeout": 270 + rc.SLACK_SECONDS}
        assert dict(sent)["show clock"] == {}

    def test_the_agent_s_run_of_send_log_is_refused_and_recorded(self, monkeypatch, tmp_path):
        from modules.nsot import reads
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path / n))
        monkeypatch.setattr("modules.list_settings.value", lambda ln, k, d=None: d)
        with pytest.raises(reads.Refused, match="send log is Tier 1"):
            reads.run("Lab", ["r2"], ["send log 6 x"], "op@example.invalid", by="agent",
                      session=lambda dev, fn: pytest.fail("a device was asked"))
        record = reads.runs("Lab")["runs"][0]
        assert record["state"] == "refused" and record["by"] == "agent"

    @pytest.mark.parametrize("cmd", ["verify /md5 flash:x.bin", "send log 6 x",
                                     "terminal length 0"])
    def test_the_sender_waits_for_the_prompt(self, cmd):
        """Each returns to the prompt, so it is read as one, never on a timer."""
        from modules import commands

        class Conn:
            base_prompt = None

            def __init__(self):
                self.how = []

            def send_command(self, c, **kw):
                self.how.append("prompt")
                return ""

            def send_command_timing(self, c, **kw):
                self.how.append("timing")
                return ""

        conn = Conn()
        commands._run(conn, cmd, 60)
        assert conn.how == ["prompt"], (cmd, conn.how)
