"""Open vSwitch's own state, read through Mercury (C2991; `modules/sdn/ovs.py`).

The operator's Lab 9 sitting, 2026-11-10: "Read-only ovs-vsctl/ovs-ofctl verbs (show, list,
get, dump-flows, dump-ports-desc) belong in Tier 1 for ovs-linux", and Show commands refused
`ovs-vsctl show` with only "in no tier of Mercury's command policy" while the list held
`sudo -n ovs-vsctl show`.

What is held here:
- **the list is exact** (`FORMS`, written out, compared with `ovs.read_forms()`): every allowed
  command is a whole command, or a shape whose one variable part is an interface name;
- **each form is allowed** with an interface name in each of its shapes, and **nothing near it
  is**: a write verb, a second command, an option a caller chooses (`--db`), a table or column
  off the fixed sets, a name that is not one interface name, another program;
- **a near miss names the listed form** (the comparison and both operands), on the device's
  session rule and on Show commands' check, and nothing is rewritten;
- **only on an Open vSwitch server** (the driver `ovs_linux`): refused on an IOS, an EOS and a
  Linux host's session, and by the reads engine before any session opens;
- the session itself sends each read unheld and refuses a write (`connection._guard_writes`),
  Netmiko faked at its boundary as tests/test_discovery_reads.py fakes it.
"""

import os

import pytest

from modules import connection as C
from modules import discovery
from modules.nsot import device_ops as D
from modules.sdn import ovs

LIST = "Lab"
FAMILY = "Open vSwitch"

#: Every OVS read, written out: the list this file holds the module to.
FORMS = (
    "ovs-vsctl --version",
    "sudo -n ovs-vsctl show",
    "sudo -n ovs-vsctl list-br",
    "sudo -n ovs-vsctl --columns=target,is_connected list controller",
    "sudo -n ovs-vsctl list controller",
    "sudo -n ovs-vsctl get-controller <bridge>",
    "sudo -n ovs-vsctl get-fail-mode <bridge>",
    "sudo -n ovs-vsctl list-ports <bridge>",
    "sudo -n ovs-vsctl get bridge <bridge> protocols",
    "sudo -n ovs-vsctl get bridge <bridge> datapath_id",
    "sudo -n ovs-vsctl get bridge <bridge> fail_mode",
    "sudo -n ovs-vsctl get bridge <bridge> other_config",
    "sudo -n ovs-vsctl --if-exists get bridge <bridge> other-config:datapath-id",
    "sudo -n ovs-vsctl get interface <port> ofport_request",
    "sudo -n ovs-vsctl get interface <port> ofport",
    "sudo -n ovs-vsctl list bridge",
    "sudo -n ovs-vsctl list bridge <bridge>",
    "sudo -n ovs-vsctl list port",
    "sudo -n ovs-vsctl list port <port>",
    "sudo -n ovs-vsctl list interface",
    "sudo -n ovs-vsctl list interface <port>",
    "sudo -n ovs-ofctl -O OpenFlow13 show <bridge>",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows <bridge>",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-ports <bridge>",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-ports-desc <bridge>",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-tables <bridge>",
)
#: The forms this change added (the others are tests/test_openflow_config.py's `TestOvsShapes`).
ADDED = tuple(f for f in FORMS if f in (
    "sudo -n ovs-vsctl list controller", "sudo -n ovs-vsctl get bridge <bridge> fail_mode",
    "sudo -n ovs-vsctl get bridge <bridge> other_config")
    or " list bridge" in f or " list port" in f or " list interface" in f or " dump-" in f)
NAMES = ("br0", "ovs-br1", "eth1.100", "s1_p2", "a" * 15)


def _with(form, name="br0"):
    return form.replace("<bridge>", name).replace("<port>", name)


#: Each refused as a read, with why it is here.
REFUSED = [
    # a verb that writes
    "sudo -n ovs-vsctl set bridge br0 fail_mode=secure",
    "sudo -n ovs-vsctl set interface eth1 ofport_request=5",
    "sudo -n ovs-vsctl add-br br9", "sudo -n ovs-vsctl del-br br0",
    "sudo -n ovs-vsctl add-port br0 eth9", "sudo -n ovs-vsctl del-port br0 eth1",
    "sudo -n ovs-vsctl clear bridge br0 protocols",
    "sudo -n ovs-vsctl remove bridge br0 other-config datapath-id",
    "sudo -n ovs-vsctl set-controller br0 tcp:192.0.2.10:6653",
    "sudo -n ovs-vsctl set-controller br0 tcp:[2001:db8::10]:6653",
    "sudo -n ovs-vsctl del-controller br0", "sudo -n ovs-vsctl set-fail-mode br0 secure",
    "sudo -n ovs-vsctl emer-reset", "sudo -n ovs-vsctl destroy bridge br0",
    "sudo -n ovs-vsctl create bridge name=br9", "sudo -n ovs-vsctl init",
    "ovs-vsctl set bridge br0 fail_mode=secure",
    "sudo -n ovs-ofctl add-flow br0 actions=drop",
    "sudo -n ovs-ofctl -O OpenFlow13 add-flow br0 actions=drop",
    "sudo -n ovs-ofctl -O OpenFlow13 mod-flows br0 actions=drop",
    "sudo -n ovs-ofctl -O OpenFlow13 del-flows br0",
    "sudo -n ovs-ofctl -O OpenFlow13 mod-port br0 1 down",
    "sudo -n ovs-ofctl -O OpenFlow13 mod-table br0 0 evict",
    "sudo -n ovs-ofctl -O OpenFlow13 replace-flows br0 flows.txt",
    "ovs-ofctl mod-flows br0 actions=drop",
    # another program
    "sudo -n ovs-appctl fdb/show br0", "ovs-appctl bridge/dump-flows br0",
    "sudo -n ovs-dpctl show", "sudo -n ovsdb-client dump", "sudo -n ovs-vswitchd --version",
    "sudo -s", "sudo -n sh", "sudo -n -u root ovs-vsctl show", "sudo -i ovs-vsctl show",
    # a second command
    "sudo -n ovs-vsctl show; reboot", "sudo -n ovs-vsctl show;reboot",
    "sudo -n ovs-vsctl show && reboot", "sudo -n ovs-vsctl show || reboot",
    "sudo -n ovs-vsctl show | tee /tmp/x", "sudo -n ovs-vsctl show > /tmp/x",
    "sudo -n ovs-vsctl show $(reboot)", "sudo -n ovs-vsctl show `reboot`",
    "sudo -n ovs-vsctl show\nreboot", "sudo -n ovs-vsctl show\rreboot",
    "sudo -n ovs-vsctl show & reboot",
    "sudo -n ovs-vsctl list bridge br0 -- del-br br0",
    "sudo -n ovs-vsctl -- show", "sudo -n ovs-vsctl show -- add-br br9",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows br0; sudo -n ovs-vsctl del-br br0",
    # an option a caller chooses
    "sudo -n ovs-vsctl --db=tcp:192.0.2.10:6640 show",
    "sudo -n ovs-vsctl --db=tcp:[2001:db8::10]:6640 show",
    "sudo -n ovs-vsctl --db=unix:/tmp/other.sock list bridge",
    "sudo -n ovs-vsctl --no-wait show", "sudo -n ovs-vsctl show --format=json",
    "sudo -n ovs-vsctl --columns=name list bridge", "sudo -n ovs-vsctl -t 5 show",
    "sudo -n ovs-vsctl --columns=target,is_connected,other_config list controller",
    "sudo -n ovs-vsctl --if-exists get bridge br0 protocols",
    "sudo -n ovs-vsctl --id=@x list bridge",
    "sudo -n ovs-ofctl -O OpenFlow13 --strict dump-flows br0",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows br0 table=0",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows br0 --sort",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-ports br0 1",
    "sudo -n ovs-ofctl -O OpenFlow15 dump-flows br0",
    "sudo -n ovs-ofctl -O OpenFlow10 dump-flows br0",
    "sudo -n ovs-ofctl -O OpenFlow13,OpenFlow10 dump-flows br0",
    "sudo -n ovs-ofctl --protocols=OpenFlow13 dump-flows br0",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows tcp:192.0.2.10:6653",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows tcp:[2001:db8::10]:6653",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows unix:/var/run/openvswitch/br0.mgmt",
    "sudo -n ovs-ofctl -O OpenFlow13 snoop br0", "sudo -n ovs-ofctl -O OpenFlow13 monitor br0",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-groups br0",
    # a table or a column off the fixed sets
    "sudo -n ovs-vsctl list open_vswitch", "sudo -n ovs-vsctl list ssl",
    "sudo -n ovs-vsctl list manager", "sudo -n ovs-vsctl list Bridge",
    "sudo -n ovs-vsctl list", "sudo -n ovs-vsctl list bridge br0 br1",
    "sudo -n ovs-vsctl list controller 5c5f4d2e-0f6b-4b7a-9a43-1d2a3b4c5d6e",
    "sudo -n ovs-vsctl get bridge br0 controller", "sudo -n ovs-vsctl get bridge br0 _uuid",
    "sudo -n ovs-vsctl get bridge br0 other_config:hwaddr",
    "sudo -n ovs-vsctl get bridge br0", "sudo -n ovs-vsctl get port eth1 tag",
    "sudo -n ovs-vsctl get open_vswitch . ssl", "sudo -n ovs-vsctl get interface eth1 options",
    "sudo -n ovs-vsctl find interface type=vxlan",
    # a name that is not one interface name
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows br 0",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows br/0",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows ../br0",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows 'br0'",
    'sudo -n ovs-ofctl -O OpenFlow13 dump-flows "br0"',
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows br*",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows br?",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows -br0",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows --all",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows " + "b" * 16,
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows brö",
    "sudo -n ovs-ofctl -O OpenFlow13 dump-flows",
    "sudo -n ovs-vsctl list bridge " + "b" * 16, "sudo -n ovs-vsctl list port eth1,eth2",
    "sudo -n ovs-vsctl list interface eth1 eth2", "sudo -n ovs-vsctl list-ports br0 br1",
    # not printable ASCII, though it reads as a listed command
    "sudo -n ovs-vsctl show", "sudo -n ovs-vsctl show ", "sudo -n ovs-vsctl show\x0b",
    "sudo\t-n ovs-vsctl show", "sudo -n ovs-vsctl shоw", "sudo -n ovs-vsctl show\x00",
    "sudo -n ovs-vsctl show\x1b[0m", "ｓudo -n ovs-vsctl show",
    # nothing, and case
    "", "   ", "SUDO -N OVS-VSCTL SHOW", "sudo -n ovs-vsctl SHOW", "sudo -n OVS-OFCTL -O OpenFlow13 show br0",
]


class TestTheList:
    def test_the_reads_are_exactly_these(self):
        """And a floor on this file's own tables: each added verb, table and column has a
        refusal beside it, so a shape loosened to take a free argument fails below."""
        assert ovs.read_forms() == FORMS
        assert len(ADDED) == 13, ADDED
        for word in ("list bridge", "list port", "list interface", "list controller",
                     "get bridge", "dump-flows", "dump-ports", "--db=", "add-flow",
                     "mod-flows", "ovs-appctl", "set bridge"):
            assert sum(word in c for c in REFUSED) >= 1, word
        assert len(REFUSED) >= 100

    @pytest.mark.parametrize("form", ADDED)
    def test_each_added_form_is_a_read_with_any_interface_name(self, form):
        for name in NAMES if "<" in form else ("",):
            command = _with(form, name)
            assert ovs.read_refusal(command) == "", command
            assert discovery.command_refusal("ovs_linux", command) == "", command
            # A read is never the write's shape (the session's one held write).
            assert ovs.write_refusal(command) != "", command

    @pytest.mark.parametrize("command", REFUSED)
    def test_nothing_near_a_read_is_one(self, command):
        why = ovs.read_refusal(command)
        assert why.startswith("REFUSED: "), (command, why)
        assert discovery.command_refusal("ovs_linux", command).startswith("REFUSED: ")
        assert discovery.listed_on(command) == (), command


NEAR = [("ovs-vsctl show", "sudo -n ovs-vsctl show"),
        ("sudo ovs-vsctl show", "sudo -n ovs-vsctl show"),
        ("ovs-vsctl list-br", "sudo -n ovs-vsctl list-br"),
        ("ovs-vsctl list bridge br0", "sudo -n ovs-vsctl list bridge br0"),
        ("ovs-vsctl get bridge br0 fail_mode", "sudo -n ovs-vsctl get bridge br0 fail_mode"),
        ("ovs-ofctl dump-flows br0", "sudo -n ovs-ofctl -O OpenFlow13 dump-flows br0"),
        ("sudo ovs-ofctl dump-ports-desc br0",
         "sudo -n ovs-ofctl -O OpenFlow13 dump-ports-desc br0"),
        ("sudo -n ovs-ofctl dump-tables br0", "sudo -n ovs-ofctl -O OpenFlow13 dump-tables br0"),
        ("ovs-ofctl -O OpenFlow13 show br0", "sudo -n ovs-ofctl -O OpenFlow13 show br0"),
        ("sudo -n ovs-vsctl --version", "ovs-vsctl --version")]


class TestANearMissNamesTheListedForm:
    @pytest.mark.parametrize("typed,listed", NEAR)
    def test_the_refusal_names_what_was_typed_and_the_listed_form(self, typed, listed):
        assert ovs.listed_form(typed) == listed and ovs.read_refusal(listed) == ""
        why = discovery.command_refusal("ovs_linux", typed)
        assert why.startswith(f"REFUSED: {typed!r} is not a listed read; the listed form is "
                              f"`{listed}`"), why
        assert "Nothing was sent." in why and "ovs_linux" in why

    @pytest.mark.parametrize("typed,listed", NEAR)
    def test_show_commands_says_it_as_typed(self, typed, listed):
        """The operator's case: Show commands answered only "in no tier of Mercury's command
        policy". The check a person sees as they type, and the run's own refusal."""
        from modules import reads_page
        from modules.nsot import reads
        for why in (reads.refusal([typed], 2), reads_page.check(typed, 2)["why"],
                    reads_page.check(typed, 1, drivers=("ovs_linux",))["why"]):
            assert f"{typed!r} is not a listed read; the listed form is `{listed}`" in why, why
            assert FAMILY in why and "Nothing was sent." in why
            assert "in no tier" not in why
        assert reads_page.check(listed, 2)["ok"]

    @pytest.mark.parametrize("command", [
        "ovs-vsctl set bridge br0 fail_mode=secure", "ovs-ofctl add-flow br0 actions=drop",
        "sudo ovs-vsctl del-br br0", "ovs-appctl fdb/show br0", "ovs-vsctl show; reboot",
        "ovs-vsctl --db=tcp:192.0.2.10:6640 show", "ovs-vsctl list open_vswitch",
        "sudo -n ovs-vsctl show", "show clock", ""])
    def test_a_near_miss_of_nothing_names_no_form(self, command):
        """A write typed bare is still refused whole, with no form offered."""
        from modules.nsot import reads
        assert ovs.listed_form(command) == "" and discovery.near_miss(command) == ""
        if command not in ("sudo -n ovs-vsctl show", "show clock"):
            why = reads.refusal([command], 1)
            assert "REFUSED" in why.upper() and "listed form" not in why, why


# --------------------------------------------------------------------------- only on OVS

class FakeConn:
    """A Netmiko session at its boundary: what it was opened with, and every command sent."""
    sent = []

    def __init__(self, **params):
        self.ip = params["ip"]

    def enable(self):
        pass

    def find_prompt(self):
        return "ovs1$"

    def send_command(self, cmd, **kw):
        FakeConn.sent.append(cmd)
        return "ok"

    send_command_timing = send_command

    def disconnect(self):
        pass


@pytest.fixture
def netmiko_faked(monkeypatch):
    import netmiko

    FakeConn.sent = []
    monkeypatch.setattr(netmiko, "ConnectHandler", FakeConn)
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


def _open(driver, ip):
    return C.open_ssh(C.connection_params({"device_type": driver, "ip": ip, "username": "u"},
                                          password="p"), owner="test", plain=C.is_plain(driver))


class TestOnlyOnAnOvsServer:
    @pytest.mark.parametrize("ip", ["192.0.2.51", "2001:db8::51"], ids=("ipv4", "ipv6"))
    @pytest.mark.parametrize("driver", ["cisco_ios", "cisco_xe", "arista_eos", "hp_procurve",
                                        "hp_comware", "linux"])
    def test_an_ovs_session_sends_each_added_read_and_no_other_session_does(
            self, netmiko_faked, driver, ip):
        """Unheld on the OVS server's session; refused, held or not, on every other driver's
        (the platform's own key, the driver a session opens with, never a device's name)."""
        conn = _open("ovs_linux", ip)
        commands = [_with(f) for f in ADDED]
        for command in commands:
            conn.send_command(command)
        assert FakeConn.sent == commands
        conn.disconnect()
        FakeConn.sent = []
        other = _open(driver, ip)
        for command in commands:
            with pytest.raises(Exception) as e:
                other.send_command(command)
            assert "REFUSED" in str(e.value) and repr(command) in str(e.value), str(e.value)
            with D.hold(LIST, "sw1", "deploy", "op@example.invalid", ip=ip):
                with pytest.raises(Exception):
                    other.send_command(command)
        assert FakeConn.sent == []

    @pytest.mark.parametrize("ip", ["192.0.2.51", "2001:db8::51"], ids=("ipv4", "ipv6"))
    def test_an_ovs_session_refuses_what_is_near_a_read(self, netmiko_faked, ip):
        conn = _open("ovs_linux", ip)
        for command in ("ovs-vsctl show", "sudo -n ovs-vsctl list open_vswitch",
                        "sudo -n ovs-ofctl -O OpenFlow13 dump-flows br0 table=0",
                        "sudo -n ovs-ofctl -O OpenFlow13 del-flows br0",
                        "sudo -n ovs-vsctl --db=tcp:192.0.2.10:6640 list bridge"):
            with pytest.raises(C.DiscoveryOnly) as e:
                conn.send_command(command)
            assert repr(command) in str(e.value) and FAMILY in str(e.value)
        assert FakeConn.sent == []
        assert "listed form is `sudo -n ovs-vsctl show`" in discovery.command_refusal(
            "ovs_linux", "ovs-vsctl show")


class Session:
    def __init__(self):
        self.opened, self.asked = [], []

    def __call__(self, dev, fn):
        self.opened.append(dev["hostname"])
        return fn(self)

    def answer(self, command):
        self.asked.append(command)
        if command.endswith("list interface"):
            return ('name                : "vxlan1"\n'
                    'options             : {key="5", psk="FAKEpsk99", remote_ip="192.0.2.9"}\n'
                    "type                : vxlan")
        return f"{command}: ok"


@pytest.fixture
def lab(monkeypatch, tmp_path):
    rows = [{"hostname": "ovs1", "ip": "192.0.2.51", "device_type": "ovs_linux"},
            {"hostname": "ovs2", "ip": "2001:db8::51", "device_type": "ovs_linux"},
            {"hostname": "r1", "ip": "192.0.2.11", "device_type": "cisco_xe"},
            {"hostname": "sw1", "ip": "2001:db8::31", "device_type": "arista_eos"},
            {"hostname": "ctl", "ip": "192.0.2.41", "device_type": "linux"}]
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / name))
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path: [dict(d) for d in rows])
    monkeypatch.setattr("modules.commands.run_device_command", lambda conn, c: conn.answer(c))
    monkeypatch.setattr("modules.list_settings.value", lambda ln, key, default=None: default)
    return tmp_path


def _run(hosts, commands):
    from modules.nsot import reads
    s = Session()
    return reads.run(LIST, hosts, commands, "op@example.invalid", session=s), s


class TestThroughTheReadsEngine:
    def test_a_mixed_run_asks_only_the_ovs_servers(self, lab):
        commands = ["sudo -n ovs-ofctl -O OpenFlow13 dump-flows br0",
                    "sudo -n ovs-vsctl list bridge br0"]
        r, s = _run(["ovs1", "ovs2", "r1", "sw1", "ctl"], commands)
        assert sorted(s.opened) == ["ovs1", "ovs2"] and sorted(set(s.asked)) == sorted(commands)
        for host in ("ovs1", "ovs2"):
            assert r["results"][host]["state"] == "answered"
            assert [a["command"] for a in r["results"][host]["answers"]] == commands
        for host in ("r1", "sw1", "ctl"):
            out = r["results"][host]
            assert out["state"] == "failed" and "REFUSED" in out["why"], out
            assert repr(commands[0]) in out["why"]

    def test_a_near_miss_asks_no_device_and_the_record_names_the_listed_form(self, lab):
        from modules.nsot import reads
        s = Session()
        with pytest.raises(reads.Refused) as e:
            reads.run(LIST, ["ovs1", "ovs2"], ["ovs-ofctl dump-flows br0"], "op@example.invalid",
                      session=s)
        assert "the listed form is `sudo -n ovs-ofctl -O OpenFlow13 dump-flows br0`" in str(e.value)
        assert s.opened == []
        (record,) = reads.runs(LIST)["runs"]
        assert record["state"] == "refused" and "listed form" in record["refused"]

    @pytest.mark.parametrize("host", ["ovs1", "ovs2"], ids=("ipv4", "ipv6"))
    def test_a_listed_tables_secret_is_masked_in_what_is_kept(self, lab, host):
        """`list interface` prints a tunnel's options: masked on the way out, as every answer
        of a discovery driver's session is (`discovery.masked`)."""
        r, _s = _run([host], ["sudo -n ovs-vsctl list interface"])
        (a,) = r["results"][host]["answers"]
        stored = (lab / LIST / "reads" / f"{r['id']}.json").read_text(encoding="utf-8")
        assert "FAKEpsk99" not in a["answer"] and "FAKEpsk99" not in stored
        assert discovery.MASK in a["answer"] and "type                : vxlan" in a["answer"]
