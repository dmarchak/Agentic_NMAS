"""O4 (docs/LAB9_PLAN.md section 8): Mercury's console-server store
(`modules/nsot/console_servers.py`), keyed by NetBox's console-server PORT id.

It holds per port only the driver, the host, the SSH port, the container name (command bridge)
or the TCP port and an optional jump host (raw TCP), and a credential REFERENCE. Pinned here:

- a round trip per driver, with an IPv6 host beside the IPv4 one (brackets and a zone; stored
  canonical) and a hostname;
- a free-form command is refused (an unknown field), and so is every container name the bridge
  wrapper would refuse: injection characters, spaces, ``..``, empty, 64 characters and more;
- a field another driver owns, a missing required field, a port number out of range, a
  credential VALUE in place of a reference, a host that is neither address nor name;
- every write records who (an actor is required) and when, a removal too, in the store's log;
- the store: owner-only from creation (0600), two processes writing lose nothing, an unreadable
  store refuses every write and is preserved, and a read says unreadable, never absent.
"""

import json
import multiprocessing
import os
import stat

import pytest

ACTOR = "p@example.invalid"

BRIDGE = {"driver": "command_bridge", "host": "192.0.2.10", "ssh_port": 22,
          "container": "edge-a", "credential_ref": "console-bridge"}
RAW = {"driver": "raw_tcp", "host": "192.0.2.21", "tcp_port": 5000}
RAW_JUMP = dict(RAW, jump_host="2001:db8::7", ssh_port="2222", credential_ref="lab:@profile:jump")


@pytest.fixture
def cs(tmp_path, monkeypatch):
    from modules import config
    from modules.nsot import console_servers

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return console_servers


def _held(cs, port_id):
    got = cs.get_port(port_id)
    assert got["state"] == "read", got
    return {k: v for k, v in got["record"].items() if k not in cs.STAMPS}


class TestRoundTrip:
    def test_a_command_bridge_port(self, cs):
        got = cs.set_port(41, BRIDGE, actor=ACTOR)
        assert got["ok"], got
        assert _held(cs, 41) == BRIDGE

    def test_a_raw_tcp_port_with_no_jump(self, cs):
        assert cs.set_port(42, RAW, actor=ACTOR)["ok"]
        assert _held(cs, 42) == RAW

    def test_a_raw_tcp_port_through_an_ipv6_jump_host(self, cs):
        assert cs.set_port(43, RAW_JUMP, actor=ACTOR)["ok"]
        assert _held(cs, 43) == dict(RAW_JUMP, ssh_port=2222)

    @pytest.mark.parametrize("given,stored", [
        ("192.0.2.10", "192.0.2.10"),
        ("2001:db8::1", "2001:db8::1"),
        ("[2001:DB8:0:0::1]", "2001:db8::1"),
        ("fe80::1%eth0", "fe80::1%eth0"),
        ("Console-1.Example.net.", "console-1.example.net"),
    ])
    def test_a_host_is_stored_canonical_ipv6_beside_ipv4(self, cs, given, stored):
        assert cs.set_port(44, dict(BRIDGE, host=given), actor=ACTOR)["ok"]
        assert _held(cs, 44)["host"] == stored

    def test_each_write_records_who_and_when(self, cs):
        cs.set_port(45, BRIDGE, actor=ACTOR)
        cs.set_port(45, dict(BRIDGE, ssh_port=2022), actor="q@example.invalid")
        cs.remove_port(45, actor="r@example.invalid")
        doc = cs.read()["doc"]
        assert [(e["action"], e["by"]) for e in doc["log"]] == [
            ("added", ACTOR), ("replaced", "q@example.invalid"), ("removed", "r@example.invalid")]
        assert all(e["at"].endswith("Z") for e in doc["log"])

    def test_the_record_names_its_writer(self, cs):
        cs.set_port(46, BRIDGE, actor=ACTOR)
        rec = cs.get_port(46)["record"]
        assert rec["by"] == ACTOR and rec["at"].endswith("Z")

    def test_removal_forgets_one_port_only(self, cs):
        cs.set_port(47, BRIDGE, actor=ACTOR)
        cs.set_port(48, RAW, actor=ACTOR)
        got = cs.remove_port(47, actor=ACTOR)
        assert got["ok"] and got["removed"]["container"] == "edge-a"
        assert cs.get_port(47)["state"] == "absent" and cs.get_port(48)["state"] == "read"

    def test_removing_a_port_with_no_record_is_refused(self, cs):
        got = cs.remove_port(49, actor=ACTOR)
        assert not got["ok"] and got["error"] == "Not removed: console-server port 49 has no record"

    def test_the_log_is_bounded(self, cs, monkeypatch):
        monkeypatch.setattr(cs, "LOG_MAX", 3)
        for i in range(5):
            cs.set_port(50, dict(BRIDGE, ssh_port=1000 + i), actor=ACTOR)
        assert [e["action"] for e in cs.read()["doc"]["log"]] == ["replaced"] * 3


class TestRefusals:
    def test_a_free_form_command_is_refused(self, cs):
        got = cs.set_port(51, dict(BRIDGE, command="docker exec -i edge-a telnet 127.0.0.1 5000"),
                          actor=ACTOR)
        assert not got["ok"] and "field 'command' is not held" in got["error"]
        assert not os.path.exists(cs.path()), "a refused write wrote the store"

    @pytest.mark.parametrize("name", [
        "edge-a;reboot", "edge-a && id", "edge-a|sh", "$(id)", "`id`", "edge a", "edge-a\n",
        "..", "a..b", "../etc", "", "x" * 64, "-edge", ".edge", "edge/a", "'edge'", '"edge"',
        "edge-a --", None, 5])
    def test_a_container_name_the_bridge_would_refuse_is_refused(self, cs, name):
        got = cs.set_port(52, dict(BRIDGE, container=name), actor=ACTOR)
        assert not got["ok"] and "container" in got["error"], got
        assert not os.path.exists(cs.path())

    def test_the_longest_name_the_bridge_takes_is_kept(self, cs):
        """The floor: 63 characters is a name, so the refusals above are about shape."""
        assert cs.set_port(53, dict(BRIDGE, container="e" * 63), actor=ACTOR)["ok"]

    @pytest.mark.parametrize("record,words", [
        (dict(RAW, container="edge-a"), "field 'container' is not held for the raw_tcp"),
        (dict(BRIDGE, tcp_port=5000), "field 'tcp_port' is not held for the command_bridge"),
        (dict(BRIDGE, driver="ssh_user_port"), "driver 'ssh_user_port' is not one of"),
        ({k: v for k, v in BRIDGE.items() if k != "driver"}, "driver None is not one of"),
        ({k: v for k, v in BRIDGE.items() if k != "container"}, "container is required"),
        ({k: v for k, v in BRIDGE.items() if k != "credential_ref"},
         "credential_ref is required"),
        (dict(RAW, ssh_port=22), "ssh_port is held only with a jump host"),
        (dict(RAW, jump_host="192.0.2.1"), "ssh_port is required with a jump host"),
        (dict(BRIDGE, ssh_port=0), "ssh_port 0 is not a port number"),
        (dict(BRIDGE, ssh_port=65536), "ssh_port 65536 is not a port number"),
        (dict(BRIDGE, ssh_port=True), "ssh_port True is not a port number"),
        (dict(RAW, tcp_port="50 00"), "tcp_port '50 00' is not a port number"),
        (dict(BRIDGE, credential_ref="hunter2 pass"), "is not a credential store key name"),
        (dict(BRIDGE, credential_ref="console-bridge\n"), "is not a credential store key name"),
        (dict(BRIDGE, host="fe80::1%eth0\n"), "is not an address or a hostname"),
        # Key material pasted where a reference belongs (a key file's base64 body; the stage
        # guard refuses a private-key header in any staged file, so none is written here).
        (dict(BRIDGE, credential_ref="b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQ=="),
         "is not a credential store key name"),
        (dict(BRIDGE, credential_ref="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI"),
         "is not a credential store key name"),
        (dict(BRIDGE, host="192.0.2.300"), "is not an IPv4 address"),
        (dict(BRIDGE, host="2001:db8::zz"), "is not an IPv6 address"),
        (dict(BRIDGE, host="[192.0.2.1]"), "only an IPv6 address is written in brackets"),
        (dict(BRIDGE, host="192.0.2.1%eth0"), "only an IPv6 address carries a zone"),
        (dict(BRIDGE, host="fe80::1%eth 0"), "is not an interface name"),
        (dict(BRIDGE, host="cons;reboot"), "is not an address or a hostname"),
        (dict(BRIDGE, host=" cons"), "is not an address or a hostname"),
        (dict(BRIDGE, host="-cons.example"), "is not an address or a hostname"),
        (dict(RAW, jump_host="jump host", ssh_port=22, credential_ref="k"),
         "is not an address or a hostname"),
        ("not a mapping", "a mapping of its fields"),
    ])
    def test_a_record_out_of_shape_is_refused_naming_why(self, cs, record, words):
        got = cs.set_port(54, record, actor=ACTOR)
        assert not got["ok"] and words in got["error"], got["error"]
        assert not os.path.exists(cs.path())

    @pytest.mark.parametrize("port_id", [0, -1, True, "54", None, 1.5])
    def test_a_port_id_that_is_not_one_is_refused(self, cs, port_id):
        got = cs.set_port(port_id, BRIDGE, actor=ACTOR)
        assert not got["ok"] and "positive number" in got["error"]
        assert cs.get_port(port_id)["state"] == "unreadable"
        assert not cs.remove_port(port_id, actor=ACTOR)["ok"]

    @pytest.mark.parametrize("actor", ["", "  ", None])
    def test_a_write_with_no_actor_is_refused(self, cs, actor):
        got = cs.set_port(55, BRIDGE, actor=actor)
        assert not got["ok"] and "every write records who" in got["error"]
        assert not os.path.exists(cs.path())


class TestTheStore:
    def test_absent_is_said_as_absent(self, cs):
        assert cs.read()["state"] == "absent" and cs.get_port(60)["state"] == "absent"

    def test_it_is_owner_only_from_creation(self, cs):
        cs.set_port(61, BRIDGE, actor=ACTOR)
        assert stat.S_IMODE(os.stat(cs.path()).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(cs.path() + ".lock").st_mode) == 0o600

    def test_an_unreadable_store_refuses_writes_and_is_kept(self, cs):
        os.makedirs(os.path.dirname(cs.path()), exist_ok=True)
        with open(cs.path(), "w", encoding="utf-8") as fh:
            fh.write('{"version": 1, "ports": {"7": {"driver"')          # a fragment
        before = open(cs.path(), "rb").read()
        got = cs.set_port(62, BRIDGE, actor=ACTOR)
        assert not got["ok"] and "could not be read" in got["error"]
        assert not cs.remove_port(7, actor=ACTOR)["ok"]
        assert open(cs.path(), "rb").read() == before, "the store was overwritten"
        folder = os.path.dirname(cs.path())
        assert [n for n in os.listdir(folder) if ".corrupt-" in n]
        assert cs.read()["state"] == "unreadable"
        assert cs.get_port(7)["state"] == "unreadable"

    def test_a_store_of_another_shape_refuses_writes(self, cs):
        os.makedirs(os.path.dirname(cs.path()), exist_ok=True)
        with open(cs.path(), "w", encoding="utf-8") as fh:
            json.dump(["not", "a", "store"], fh)
        got = cs.set_port(63, BRIDGE, actor=ACTOR)
        assert not got["ok"] and "not a console-server store" in got["error"]
        assert json.load(open(cs.path(), encoding="utf-8")) == ["not", "a", "store"]
        assert cs.read()["state"] == "unreadable"


def _write_many(prefix, n):
    from modules.nsot import console_servers
    for i in range(n):
        assert console_servers.set_port(prefix * 1000 + i, BRIDGE, actor=f"w{prefix}")["ok"]


def test_two_processes_writing_lose_nothing(cs):
    ctx = multiprocessing.get_context("fork")
    procs = [ctx.Process(target=_write_many, args=(p, 30)) for p in (1, 2)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0, p.exitcode
    doc = cs.read()["doc"]
    assert len(doc["ports"]) == 60 and len(doc["log"]) == 60
