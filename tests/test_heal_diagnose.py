"""The diagnosis runbooks' engine (board H amendment item 1, part H14; docs/HEAL_TO_INTENT.md
19.3; modules/heal/diagnose.py, modules/heal/diagnose_parse.py): "adjacency down with both ends
at intent", read-only and deterministic.

On the fleet's real intent (the nine real configs parsed by the real parsers, as
tests/test_network_model.py builds it) and real captures (tests/fixtures/operational/), each
edited minimally where a scenario needs a fault: r3's own `show ip interface`, OSPF and OSPFv3
neighbour tables and LLDP name r4 on Gi4, and r4's side is r3's capture with r4's addresses.

- **The parsers**, each on its real capture; a read with no capture is sent and said "not yet
  interpreted" (C2414), never parsed from a typed sample.
- **The pipe rule as a test** (19.5): every command every template can produce, on each
  dialect, passes the reads engine as kind ``diagnosis`` (no extras) and the model's read rule
  (`read_loop._cli_rule`), with no output modifier; a spliced field is one token of its shape.
- **The bounds** (N24): 14 reads a device on a dual-stack OSPF and BGP link, 28 both ends, 70 a
  diagnosis, a run reaching the cap saying where; one diagnosis per device across processes,
  refused by name and never queued; a device another operation holds is skipped by name.
- **Each rule** (`diagnose.RULES`) with a planted case, and the ranking's order.
- **Through the one reads engine:** every read a ``diagnosis`` run on History › Reads, each
  hypothesis citing ``read:<run>:<device>:<command>`` of a run that exists.
- **The record:** one ``diagnosis`` row, masked, attached to its incident or its own.
"""
import copy
import functools
import os
import subprocess
import sys
import threading

import pytest

from tests.test_sdn_connections import networks  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OP = os.path.join(ROOT, "tests", "fixtures", "operational")
ACTOR = "op@example.invalid"
GI4 = {"device": "r3", "neighbour": "r4", "interface": "GigabitEthernet4"}
_FLEET_DEVICES = [{"hostname": h, "ip": f"192.0.2.{n}", "device_type": t}
             for h, n, t in (("r3", 13, "cisco_xe"), ("r4", 14, "cisco_xe"),
                             ("r5", 15, "cisco_xe"), ("s3", 23, "cisco_ios"))]


def capture(name: str) -> str:
    with open(os.path.join(OP, name), encoding="utf-8") as fh:
        return fh.read()


def block(text: str, name: str) -> str:
    """One interface's block of a whole-table capture: what the narrowed read prints."""
    from modules.heal.diagnose_parse import _blocks
    return next(b for n, b in _blocks(text) if n == name)


@functools.lru_cache(maxsize=1)
def _fleet():
    from tests import test_topology_graph as TG
    return TG._intents()


def fleet(edit=None):
    """``(model, intents)``: the fleet's real intent compiled by the real model; *edit(intents)*
    changes it first."""
    from modules import network_model as NM
    intents = copy.deepcopy(_fleet())
    if edit:
        edit(intents)
    inv = [{"hostname": h, "ip": f"192.0.2.{30 + i}", "_netbox_id": 100 + i,
            "_platform": intents[h].get("platform")} for i, h in enumerate(sorted(intents))]
    return NM.build("Default", inv, intents), intents


# The two ends of r3 Gi4 - r4 Gi4, healthy, from the captures. `show interfaces` is r2's real
# Loopback0 capture with its first line naming the port (no physical port is captured yet).
LOOP = capture("r2__show_interfaces_Loopback0.txt")
SHOW_IF = LOOP.replace("Loopback0 is up, line protocol is up",
                       "GigabitEthernet4 is up, line protocol is up")
R3_IP = block(capture("r3__show_ip_interface.txt"), "GigabitEthernet4")
R4_IP = R3_IP.replace("10.255.2.14/31", "10.255.2.15/31")
R3_OSPF = capture("r3__show_ip_ospf_neighbor_detail.txt")
R4_OSPF = (" Neighbor 10.255.1.13, interface address 10.255.2.14, interface-id 10\n"
           + R3_OSPF.split(" Neighbor 10.255.1.14, interface address 10.255.2.15, "
                           "interface-id 10\n", 1)[1])
R3_V3 = capture("r3__show_ospfv3_neighbor.txt")
R4_V3 = "\n".join(l.replace("10.255.1.14", "10.255.1.13") if l.rstrip().endswith(
    "GigabitEthernet4") else l for l in R3_V3.splitlines())
R3_LLDP = capture("r3__show_lldp_neighbors_detail.txt")
R4_LLDP = R3_LLDP.replace("System Name: r4.example.com", "System Name: r3.example.com")
CDP = capture("r3__show_cdp_neighbors_detail.txt")


def healthy() -> dict:
    out = {}
    for host, ip, ospf, v3, lldp in (("r3", R3_IP, R3_OSPF, R3_V3, R3_LLDP),
                                     ("r4", R4_IP, R4_OSPF, R4_V3, R4_LLDP)):
        out.update({(host, "show interfaces GigabitEthernet4"): SHOW_IF,
                    (host, "show ip interface GigabitEthernet4"): ip,
                    (host, "show cdp neighbors GigabitEthernet4 detail"): CDP,
                    (host, "show lldp neighbors GigabitEthernet4 detail"): lldp,
                    (host, "show ip ospf neighbor GigabitEthernet4 detail"): ospf,
                    (host, "show ospfv3 neighbor"): v3})
    return out


class Fleet:
    """Device sessions at the reads engine's seam: each host's answers by command (a list is
    one answer per time it is asked), every command recorded with its host."""

    def __init__(self, answers):
        self.answers, self.sent, self.mu = answers, [], threading.Lock()

    def __call__(self, dev, fn):
        return fn(_Conn(self, dev["hostname"]))


class _Conn:
    def __init__(self, fleet_, host):
        self.fleet, self.host = fleet_, host

    def answer(self, command):
        with self.fleet.mu:
            n = sum(1 for s in self.fleet.sent if s == (self.host, command))
            self.fleet.sent.append((self.host, command))
        a = self.fleet.answers.get((self.host, command), "")
        return a[min(n, len(a) - 1)] if isinstance(a, list) else a


def quiet(network, host, now):
    return {"state": "read", "why": "", "lines": []}


@pytest.fixture
def world(networks, monkeypatch):  # noqa: F811 (the fixture)
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in _FLEET_DEVICES])
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, c, read_timeout=None: conn.answer(c))
    return networks


def diagnose(answers=None, target=GI4, edit=None, logs=quiet, **kw):
    from modules.heal import diagnose as D
    model, intents = fleet(edit)
    f = Fleet(healthy() if answers is None else answers)
    got = D.run("Default", "adjacency_down", target, ACTOR, session=f, logs=logs,
                sleep=lambda s: None, model=model, intents=intents, **kw)
    return got, f


def rules_fired(got) -> list:
    return [h["rule"] for h in got["hypotheses"]]


# ── The parsers, on real captures ───────────────────────────────────────────────────────────

class TestTheParsers:
    def test_show_interfaces_state_mtu_and_counters(self):
        from modules.heal.diagnose_parse import parse
        for name in ("r2__show_interfaces_Loopback0.txt", "s1__show_interfaces_Loopback0.txt"):
            got = parse("interfaces", capture(name), "Loopback0")
            assert got["state"] == "parsed", got
            f = got["facts"]
            assert (f["state"], f["protocol"], f["mtu"], f["input_errors"], f["crc"]) == (
                "up", "up", 1514, 0, 0)
        down = LOOP.replace("Loopback0 is up, line protocol is up",
                            "GigabitEthernet4 is down, line protocol is down (notconnect)")
        f = parse("interfaces", down, "GigabitEthernet4")["facts"]
        assert (f["state"], f["reason"]) == ("down", "notconnect")
        shut = LOOP.replace("Loopback0 is up", "Loopback0 is administratively down")
        assert parse("interfaces", shut, "Loopback0")["facts"]["state"] == "admin_down"

    def test_show_ip_interface_picks_its_block_with_address_mtu_and_acls(self):
        from modules.heal.diagnose_parse import parse
        whole = capture("r3__show_ip_interface.txt")
        f = parse("ip_interface", whole, "Gi2")["facts"]
        assert (f["address"], f["ip_mtu"], f["acl_in"], f["acl_out"]) == (
            "198.51.100.0/31", 1500, "", "")
        f = parse("ip_interface", R3_IP, "GigabitEthernet4")["facts"]
        assert f["address"] == "10.255.2.14/31" and f["state"] == "up"
        bound = R3_IP.replace("Inbound  access list is not set", "Inbound  access list is EDGE")
        assert parse("ip_interface", bound, "Gi4")["facts"]["acl_in"] == "EDGE"
        assert parse("ip_interface", whole, "Gi9")["state"] == "unreadable"

    def test_cdp_and_lldp_by_the_syncs_own_readers(self):
        from modules.heal.diagnose_parse import parse
        cdp = parse("cdp", capture("s1__show_cdp_neighbors_detail.txt"), "Gi0/3")["facts"]
        assert cdp == [{"host": "s2", "port": "GigabitEthernet0/3", "local": "GigabitEthernet0/3"}]
        assert parse("cdp", CDP, "Gi4") == {"state": "parsed", "facts": [], "why": ""}
        lldp = parse("lldp", R3_LLDP, "GigabitEthernet4")["facts"]
        assert lldp == [{"host": "r4", "port": "Gi4", "local": "Gi4"}]

    def test_ospf_neighbours_detail_and_the_ospfv3_table_on_both_dialects(self):
        from modules.heal.diagnose_parse import parse
        rows = parse("ospf_neighbor", R3_OSPF, "GigabitEthernet4")["facts"]
        assert rows == [{"router_id": "10.255.1.14", "address": "10.255.2.15",
                         "interface": "GigabitEthernet4", "state": "FULL"}]
        assert len(parse("ospf_neighbor", R3_OSPF)["facts"]) == 6
        v3 = parse("ospfv3_neighbor", R3_V3, "Gi4")["facts"]
        assert v3 == [{"router_id": "10.255.1.14", "state": "FULL", "interface": "GigabitEthernet4"}]
        r1 = parse("ospfv3_neighbor", capture("r1__show_ipv6_ospf_neighbor.txt"))["facts"]
        assert [r["state"] for r in r1] == ["2WAY", "FULL", "FULL"]

    def test_an_unknown_platform_is_refused_naming_it_never_read_as_ios(self):
        from modules.heal import diagnose as D

        assert D.dialect_of("cisco_xe", "edge1") == "cisco_iosxe"
        assert D.dialect_of("cisco_ios", "edge1") == "cisco_ios"
        for value in ("junos", "", None):
            with pytest.raises(D.Refused) as got:
                D.dialect_of(value, "edge1")
            assert "edge1" in str(got.value)
        with pytest.raises(D.Refused) as got:
            D.dialect_of("junos", "edge1")
        assert "junos" in str(got.value)

    def test_bgp_summary_by_the_one_reader_ipv4_and_ipv6(self):
        from modules.heal.diagnose_parse import parse
        got = parse("bgp_summary", capture("r3__show_ip_bgp_summary.txt"))["facts"]
        assert got["peers"] == [{"address": "198.51.100.1", "remote_as": "65002",
                                 "state": "3", "established": True}]
        six = parse("bgp_summary", capture("r3__show_bgp_ipv6_unicast_summary.txt"))["facts"]
        assert six["peers"] and all(":" in p["address"] for p in six["peers"])
        # An answer that is not a summary is never read as "no neighbours".
        assert parse("bgp_summary", "")["state"] == "unreadable"

    def test_a_read_the_device_lacks_is_unsupported(self):
        from modules.heal.diagnose_parse import parse
        got = parse("ospfv3_neighbor", capture("s1__show_ospfv3_neighbor.txt"))
        assert got["state"] == "unsupported" and "no such read" in got["why"]

    def test_a_read_with_no_capture_is_said_not_interpreted(self):
        from modules.heal.diagnose_parse import NOT_CAPTURED, parse
        assert NOT_CAPTURED == {"ospf_interface", "ospfv3_interface", "ipv6_interface",
                                "link_ping", "df_ping", "bgp_neighbor", "bgp_ping",
                                "reach_ping", "traceroute", "route", "acl_counters"}
        for kind in NOT_CAPTURED:
            got = parse(kind, "anything at all")
            assert got["state"] == "not_parsed" and "C2414" in got["why"]

    def test_a_dialect_keyed_read_without_its_dialect_is_refused(self):
        """C452: `show ip arp` is read by the platform pack's pattern for the device's own
        dialect; with no dialect it is refused, never read as IOS by default."""
        from modules.heal.diagnose_parse import BY_DIALECT, parse
        assert "arp" in BY_DIALECT
        got = parse("arp", "Protocol  Address  Age (min)  Hardware Addr  Type  Interface\n")
        assert got["state"] == "unsupported" and "dialect is not known" in got["why"], got


# ── The pipe rule, the bounds and the templates ─────────────────────────────────────────────

def every_command():
    """Every command each template renders, on both dialects, its addresses of the template's
    family."""
    import string

    from modules.heal import diagnose as D
    for kind, forms in D.TEMPLATES.items():
        for dialect in ("cisco_ios", "cisco_iosxe"):
            template = forms.get(dialect) or forms["*"]
            address = "2001:db8::1" if "ipv6" in template else "192.0.2.1"
            args = {"if": "GigabitEthernet0/1", "src": "Loopback0", "far": address,
                    "peer": address, "mtu": "1500", "dest": address, "nh": address,
                    "acl": "EDGE-IN"}
            names = [f for _, f, _, _ in string.Formatter().parse(template) if f]
            yield kind, dialect, D.render(kind, dialect, **{n: args[n] for n in names})


class TestThePipeRule:
    def test_every_rendered_command_is_a_read_for_the_reads_engine_and_the_model(self):
        from modules import readonly_commands
        from modules.ai.read_loop import _cli_rule
        from modules.nsot import reads
        seen = 0
        for kind, dialect, command in every_command():
            assert readonly_commands.refusal(command) == "", command
            assert reads.refusal([command], 1, by="diagnosis") == "", command
            assert _cli_rule(kind, command) == "", command
            assert "|" not in command and not command.startswith("clear"), command
            seen += 1
        assert seen == 2 * 27                          # the floor: every template, both dialects

    def test_a_diagnosis_has_no_extras_and_never_clears_counters(self):
        from modules.nsot import reads
        assert reads.EXTRAS["diagnosis"] == ()
        for planted in ("send log 6 diagnosis", "terminal length 0", "clear counters",
                        "verify /md5 flash:x"):
            assert reads.refusal([planted], 1, by="diagnosis"), planted
        assert reads.refusal(["terminal length 0"], 1, by="person") == ""

    @pytest.mark.parametrize("kind,field,value", [
        ("interfaces", "if", "Gi4 | redirect flash:x"), ("interfaces", "if", "Gi4\nreload"),
        ("interfaces", "if", "Gi4 extra"), ("link_ping", "far", "999.1.1.1"),
        ("link_ping", "far", "192.0.2.1 source x"), ("link_ping", "far", "2001:db8::1"),
        ("bgp_neighbor6", "peer", "2001:db8::1%eth0"), ("bgp_neighbor6", "peer", "192.0.2.2"),
        ("df_ping", "mtu", "1500 df-bit"), ("df_ping", "mtu", "9000"),
        ("bgp_ping_src", "src", "Lo0;reload")])
    def test_a_spliced_field_is_one_token_of_its_shape(self, kind, field, value):
        from modules.heal import diagnose as D
        six = "6" in kind
        args = {"if": "Gi4", "far": "192.0.2.1", "peer": "2001:db8::2" if six else "192.0.2.2",
                "mtu": "1500", "src": "Loopback0"}
        names = {"interfaces": ("if",), "link_ping": ("far", "if"), "bgp_neighbor6": ("peer",),
                 "df_ping": ("far", "mtu"), "bgp_ping_src": ("peer", "src")}[kind]
        assert D.render(kind, "cisco_iosxe", **{n: args[n] for n in names})  # the control
        args[field] = value
        with pytest.raises(D.Refused):
            D.render(kind, "cisco_iosxe", **{n: args[n] for n in names})

    def test_a_plan_past_the_per_device_count_is_refused(self, monkeypatch):
        from modules.heal import diagnose as D
        monkeypatch.setattr(D, "MAX_PER_DEVICE", 9)
        model, intents = fleet()
        with pytest.raises(D.Refused) as e:
            D.plan("Default", "adjacency_down", GI4, model=model, intents=intents)
        assert str(e.value) == ("10 reads on r3, past the 9 a device may be asked in one "
                                "diagnosis")

    def test_the_longest_end_is_fourteen_reads_and_the_cap_two_and_a_half_times_both(self):
        from modules.heal import diagnose as D
        end = {"host": "rx", "dialect": "cisco_iosxe", "interface": "GigabitEthernet4",
               "short": "Gi4", "v4": "192.0.2.1/31", "v6": "2001:db8::1/64",
               "far4": "192.0.2.0", "far6": "2001:db8::2", "cabled": True, "ospf": True,
               "ospfv3": True, "intent": {"mtu": "1500"},
               "bgp": {"address": "192.0.2.0", "family": "ipv4", "update_source": "Loopback0"}}
        cmds = D.commands_for(end)
        assert len(cmds) == D.MAX_PER_DEVICE == 14
        assert D.MAX_COMMANDS == 70 == round(2.5 * 2 * len(cmds))
        assert not any(c["command"].startswith("clear") for c in cmds)


# ── The plan, from intent and the model alone ───────────────────────────────────────────────

class TestThePlan:
    def test_r3_gi4_to_r4_reads_both_ends_dual_stack(self):
        from modules.heal import diagnose as D
        model, intents = fleet()
        p = D.plan("Default", "adjacency_down", GI4, model=model, intents=intents)
        assert [e["host"] for e in p["ends"]] == ["r3", "r4"]
        a = p["ends"][0]
        assert (a["v4"], a["v6"], a["far4"], a["ospf"], a["ospfv3"]) == (
            "10.255.2.14/31", "2001:db8:2:e::1/64", "10.255.2.15", True, True)
        r3 = [c["command"] for c in p["reads"]["r3"]]
        assert r3[:2] == ["show interfaces GigabitEthernet4", "show ip interface GigabitEthernet4"]
        assert "show ospfv3 neighbor" in r3 and r3.count("show interfaces GigabitEthernet4") == 2
        assert p["count"] == 20 and p["cap"] == 70

    def test_two_devices_sharing_several_links_are_asked_which(self):
        from modules.heal import diagnose as D
        model, intents = fleet()
        with pytest.raises(D.Refused) as e:
            D.plan("Default", "adjacency_down", {"device": "r3", "neighbour": "r4"}, model=model,
                   intents=intents)
        assert "share links on Gi1, Gi3, Gi4" in str(e.value)

    def test_an_svi_end_reads_no_cdp_and_its_port_is_not_compared(self):
        from modules.heal import diagnose as D
        model, intents = fleet()
        p = D.plan("Default", "adjacency_down", {"device": "r3", "neighbour": "s3"}, model=model,
                   intents=intents)
        s3 = [c["kind"] for c in p["reads"]["s3"]]
        assert "cdp" not in s3 and "ospfv3_neighbor" not in s3
        assert "Vl100 is not one" in p["outside"]

    def test_a_bgp_peer_over_a_link_reads_the_link_and_its_session_ipv4_and_ipv6(self):
        from modules.heal import diagnose as D
        model, intents = fleet()
        for peer, summary in (("198.51.100.1", "show ip bgp summary"),
                              ("2001:db8:51::2", "show bgp ipv6 unicast summary")):
            p = D.plan("Default", "adjacency_down", {"device": "r3", "peer": peer}, model=model,
                       intents=intents)
            assert [e["host"] for e in p["ends"]] == ["r3", "r5"]
            r3 = [c["command"] for c in p["reads"]["r3"]]
            assert summary in r3 and "show interfaces GigabitEthernet2" in r3
            assert any(peer in c for c in r3)

    def test_refusals_name_what_they_compared(self):
        from modules.heal import diagnose as D
        model, intents = fleet()
        for target, words in (({"device": "r9", "neighbour": "r4"}, "r9 has no committed intent"),
                              ({"device": "r3", "neighbour": "zz"}, "zz is not a device"),
                              ({"device": "r3", "peer": "192.0.2.77"},
                               "intent names no BGP neighbour 192.0.2.77 on r3"),
                              ({"device": "r3", "peer": "999.1.1.1"}, "not one IPv4 or IPv6")):
            with pytest.raises(D.Refused) as e:
                D.plan("Default", "adjacency_down", target, model=model, intents=intents)
            assert words in str(e.value), (target, str(e.value))
        with pytest.raises(D.Refused) as e:
            D.plan("Default", "no_such_runbook", {"device": "r3"}, model=model,
                   intents=intents)
        assert "'no_such_runbook' is not a runbook" in str(e.value)
        with pytest.raises(D.Refused) as e:                # built (H15): its own refusals
            D.plan("Default", "cant_reach", {"device": "r3"}, model=model, intents=intents)
        assert str(e.value) == "'' is not one IPv4 or IPv6 address"


# ── A run, through the one reads engine ─────────────────────────────────────────────────────

class TestARun:
    def test_healthy_ends_find_no_cause_and_rule_out_what_they_checked(self, world):
        got, f = diagnose()
        assert got["state"] == "done" and got["hypotheses"] == [], got["hypotheses"]
        assert got["words"] == "no cause found in what Mercury reads"
        ruled = [r["check"] for r in got["ruled_out"]]
        for words in ("neither end is administratively down", "each end is up",
                      "the MTU is 1500 at both ends", "the adjacency is up now at both ends",
                      "no access list is bound that intent does not hold",
                      "no configuration change was logged on either end in the last hour"):
            assert words in ruled, ruled
        assert got["commands"] == 20 and {h for h, _ in f.sent} == {"r3", "r4"}

    def test_every_read_is_a_diagnosis_run_on_history_and_cited_by_reference(self, world):
        from modules.nsot import reads
        down = dict(healthy())
        down[("r4", "show interfaces GigabitEthernet4")] = SHOW_IF.replace(
            "GigabitEthernet4 is up, line protocol is up",
            "GigabitEthernet4 is down, line protocol is down")
        got, _f = diagnose(down)
        runs = {r["id"]: r for r in reads.runs("Default")["runs"]}
        assert set(got["runs"]) == set(runs) and len(runs) == 4
        assert all(r["by"] == "diagnosis" and r["actor"] == ACTOR for r in runs.values())
        assert reads.actor_words(next(iter(runs.values()))) == f"a diagnosis, for {ACTOR}"
        first = got["hypotheses"][0]
        assert first["rule"] == "down_admin_up" and first["strength"] == "decisive"
        assert first["claim"].startswith("r4 Gi4 is down while administratively up, and r3 Gi4 "
                                         "is up")
        for e in first["evidence"]:
            _, run_id, host, command = e["read"].split(":", 3)
            assert reads.answer_of(runs[run_id], host, command)["state"] == "answered"

    def test_both_ends_are_read_concurrently(self, world):
        gate = threading.Barrier(2, timeout=10)
        seen = []

        class Together(Fleet):
            def __call__(self, dev, fn):
                gate.wait()                           # both ends' sessions open together
                seen.append(dev["hostname"])
                return super().__call__(dev, fn)

        from modules.heal import diagnose as D
        model, intents = fleet()
        got = D.run("Default", "adjacency_down", GI4, ACTOR, session=Together(healthy()),
                    logs=quiet, sleep=lambda s: None, model=model, intents=intents)
        assert got["state"] == "done" and sorted(seen) == ["r3", "r3", "r4", "r4"]

    def test_the_second_read_waits_the_delta_after_the_first(self, world):
        from modules.heal import diagnose as D
        waits = []
        model, intents = fleet()
        D.run("Default", "adjacency_down", GI4, ACTOR, session=Fleet(healthy()), logs=quiet,
              sleep=waits.append, model=model, intents=intents)
        assert waits == [D.DELTA_SECONDS]

    def test_a_device_another_operation_holds_is_skipped_by_name(self, world):
        from modules.nsot import device_ops
        down = dict(healthy())
        down[("r3", "show interfaces GigabitEthernet4")] = SHOW_IF.replace(
            "is up, line protocol is up", "is down, line protocol is down")
        with device_ops.hold("Default", "r4", "deploy", "someone@example.invalid"):
            got, f = diagnose(down)
        assert {h for h, _ in f.sent} == {"r3"}
        skipped = [s for s in got["steps"] if s.get("device") == "r4" and s["step"] == "read"]
        assert skipped[0]["result"] == "not_read" and "someone@example.invalid" in \
            skipped[0]["words"]
        first = got["hypotheses"][0]
        assert first["rule"] == "down_admin_up" and first["incomplete"]
        assert "show interfaces GigabitEthernet4` on r4" in first["incomplete"][0]

    def test_the_command_cap_stops_and_says_where(self, world, monkeypatch):
        from modules.heal import diagnose as D
        monkeypatch.setattr(D, "MAX_COMMANDS", 19)
        got, f = diagnose()
        assert got["stopped"] == ("stopped at the 19-command cap before round 2; its reads "
                                  "were not made")
        assert got["commands"] == 16 and len(f.sent) == 16

    def test_a_refusal_is_a_diagnosis_with_nothing_read(self, world):
        got, f = diagnose(target={"device": "r3", "neighbour": "r4"})
        assert got["state"] == "refused" and got["words"].startswith("not diagnosed: r3 and r4")
        assert f.sent == []


class TestOneDiagnosisPerDevice:
    def test_a_second_diagnosis_on_a_device_is_refused_by_name_never_queued(self, world):
        from modules.heal import diagnose as D
        with D.DiagnosisLock("Default", ["r4"], "dg-first", "someone@example.invalid"):
            got, f = diagnose()
        assert got["state"] == "busy" and f.sent == []
        assert got["words"].startswith("not diagnosed: r4 is in diagnosis dg-first (by "
                                       "someone@example.invalid")
        assert diagnose()[0]["state"] == "done"        # released: the next one runs

    def test_held_by_another_process_is_refused(self, world):
        from modules.heal import diagnose as D
        lock = D.DiagnosisLock("Default", ["r3"], "dg-x", ACTOR)
        path = lock._path("r3")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        script = ("import fcntl, json, os, sys\n"
                  "fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)\n"
                  "fcntl.flock(fd, fcntl.LOCK_EX)\n"
                  "os.write(fd, json.dumps({'diagnosis': 'dg-elsewhere', 'actor': 'Mercury', "
                  "'started_at': 'then'}).encode())\n"
                  "print('held', flush=True)\n"
                  "sys.stdin.read()\n")
        child = subprocess.Popen([sys.executable, "-c", script, path], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, text=True)
        try:
            assert child.stdout.readline().strip() == "held"
            got, f = diagnose()
            assert got["state"] == "busy" and "r3 is in diagnosis dg-elsewhere" in got["words"]
            assert f.sent == []
        finally:
            child.stdin.close()
            child.wait(timeout=10)
        assert diagnose()[0]["state"] == "done"

    def test_all_or_none_a_busy_second_device_releases_the_first(self, world):
        from modules.heal import diagnose as D
        with D.DiagnosisLock("Default", ["r4"], "dg-first", ACTOR):
            with pytest.raises(D.DiagnosisBusy):
                with D.DiagnosisLock("Default", ["r3", "r4"], "dg-second", ACTOR):
                    pass
            with D.DiagnosisLock("Default", ["r3"], "dg-third", ACTOR):
                pass


# ── Each rule, planted ──────────────────────────────────────────────────────────────────────

def with_answer(host, command, text, base=None):
    out = dict(healthy() if base is None else base)
    out[(host, command)] = text
    return out


def set_intent(host, name, **fields):
    def edit(intents):
        for i in intents[host]["interfaces"]:
            if i["name"] == name:
                i.setdefault("ospf_interface", {}).update(fields)
    return edit


class TestEachRule:
    def test_admin_down_says_whether_intent_holds_it_shut(self, world):
        got, _ = diagnose(with_answer("r4", "show interfaces GigabitEthernet4", SHOW_IF.replace(
            "GigabitEthernet4 is up", "GigabitEthernet4 is administratively down").replace(
            "line protocol is up", "line protocol is down")))
        first = got["hypotheses"][0]
        assert first["rule"] == "admin_down" and first["layer"] == "physical"
        assert "though intent holds it up: it was shut outside intent" in first["claim"]

    def test_protocol_down(self, world):
        got, _ = diagnose(with_answer("r4", "show interfaces GigabitEthernet4", SHOW_IF.replace(
            "line protocol is up", "line protocol is down")))
        assert rules_fired(got) == ["protocol_down"]

    def test_cabled_elsewhere(self, world):
        got, _ = diagnose(with_answer("r3", "show lldp neighbors GigabitEthernet4 detail",
                                      R3_LLDP.replace("System Name: r4.example.com",
                                                      "System Name: s3.rcn.lab")))
        first = got["hypotheses"][0]
        assert first["rule"] == "cabled_elsewhere" and first["strength"] == "decisive"
        assert first["claim"] == "LLDP on r3 Gi4 names s3 Gi4; intent cables it to r4 Gi4"

    def test_cabled_to_the_right_device_on_the_wrong_port(self, world):
        got, _ = diagnose(with_answer("r3", "show lldp neighbors GigabitEthernet4 detail",
                                      R3_LLDP.replace("Port id: Gi4", "Port id: Gi3")))
        assert got["hypotheses"][0]["claim"] == ("LLDP on r3 Gi4 names r4 Gi3; intent cables it "
                                                 "to r4 Gi4")

    def test_an_svis_neighbour_port_is_not_compared(self, world):
        # r3's real LLDP names s3 Gi0/2 on Gi3; intent's link names s3's Vlan100, a port CDP
        # and LLDP never name.
        answers = {("r3", "show lldp neighbors GigabitEthernet3 detail"): R3_LLDP}
        got, _ = diagnose(answers, target={"device": "r3", "neighbour": "s3"})
        assert got["state"] == "done" and "cabled_elsewhere" not in rules_fired(got)

    def test_errors_rising_across_the_two_reads(self, world):
        worse = SHOW_IF.replace("0 input errors, 0 CRC", "12 input errors, 9 CRC")
        got, _ = diagnose(with_answer("r4", "show interfaces GigabitEthernet4", [SHOW_IF, worse]))
        first = got["hypotheses"][0]
        assert first["rule"] == "errors_rising" and first["strength"] == "strong"
        assert "rose by 12 and its CRC count by 9" in first["claim"]

    def test_mtu_differs_decisive_when_ospf_is_stuck_strong_otherwise(self, world):
        small = R4_IP.replace("MTU is 1500 bytes", "MTU is 1400 bytes")
        got, _ = diagnose(with_answer("r4", "show ip interface GigabitEthernet4", small))
        assert [(h["rule"], h["strength"]) for h in got["hypotheses"]] == [("mtu", "strong")]
        stuck = with_answer("r3", "show ip ospf neighbor GigabitEthernet4 detail",
                            R3_OSPF.replace("Neighbor priority is 1, State is FULL",
                                            "Neighbor priority is 1, State is EXSTART"),
                            base=with_answer("r4", "show ip interface GigabitEthernet4", small))
        got, _ = diagnose(stuck)
        first = got["hypotheses"][0]
        assert (first["rule"], first["strength"]) == ("mtu", "decisive")
        assert first["claim"] == ("the MTU differs: r3 Gi4 1500 against r4 Gi4 1400, and OSPF is "
                                  "stuck exchanging databases")

    def test_an_address_not_intents_on_another_subnet(self, world):
        got, _ = diagnose(with_answer("r4", "show ip interface GigabitEthernet4",
                                      R4_IP.replace("10.255.2.15/31", "10.255.2.21/31")))
        claims = [h["claim"] for h in got["hypotheses"]]
        assert "r4 Gi4 holds 10.255.2.21/31; intent holds 10.255.2.15/31" in claims
        assert ("the ends are on different subnets: r3 Gi4 10.255.2.14/31 against r4 Gi4 "
                "10.255.2.20/31") in claims

    def test_intent_disagreeing_with_itself_on_ospf_timers(self, world):
        both = lambda i: (set_intent("r3", "GigabitEthernet4", hello_interval="10")(i),  # noqa: E731
                          set_intent("r4", "GigabitEthernet4", hello_interval="5")(i))
        got, _ = diagnose(edit=both)
        first = got["hypotheses"][0]
        assert first["rule"] == "ospf_intent" and first["strength"] == "decisive"
        assert first["claim"] == ("intent disagrees with itself on OSPF's hello interval: r3 Gi4 "
                                  "10, r4 Gi4 5")
        assert not first["incomplete"]
        got, _ = diagnose(edit=set_intent("r4", "GigabitEthernet4", hello_interval="5"))
        first = got["hypotheses"][0]
        assert first["strength"] == "strong" and "not measured" in first["claim"]
        assert "C2414" in first["incomplete"][0]       # the read that settles it is uncaptured

    def test_passive_on_one_end(self, world):
        def edit(intents):
            intents["r4"]["routing"]["ospf"][0].setdefault("settings", []).append(
                "passive-interface GigabitEthernet4")
        got, _ = diagnose(edit=edit)
        assert [h["rule"] for h in got["hypotheses"]][:1] == ["passive"]
        assert "OSPF is passive on r4 Gi4 in intent" in got["hypotheses"][0]["claim"]

    def test_one_way(self, world):
        init = with_answer("r3", "show ip ospf neighbor GigabitEthernet4 detail",
                           R3_OSPF.replace("Neighbor priority is 1, State is FULL",
                                           "Neighbor priority is 1, State is INIT"),
                           base=with_answer("r4", "show ip ospf neighbor GigabitEthernet4 detail",
                                            ""))
        got, _ = diagnose(init)
        assert rules_fired(got) == ["one_way"]
        assert got["hypotheses"][0]["claim"].startswith("OSPF is one-way: r3 hears r4 (INIT) and "
                                                        "r4 lists no neighbour r3")

    def test_ospf_not_full_one_neighbour(self, world):
        # H20 (19.4): the interface's one OSPF neighbour stuck in EXSTART with the link up.
        full = "via interface GigabitEthernet4\n    Neighbor priority is 1, State is FULL"
        stuck = with_answer("r3", "show ip ospf neighbor GigabitEthernet4 detail",
                            R3_OSPF.replace(full, full.replace("FULL", "EXSTART")))
        got, _ = diagnose(stuck)
        assert rules_fired(got) == ["ospf_not_full_one_neighbour"]
        assert got["hypotheses"][0]["claim"].startswith("r3 Gi4 holds exactly one OSPF "
                                                        "neighbour, r4, stuck in EXSTART")

    BGP = capture("r3__show_ip_bgp_summary.txt")
    ROW = "198.51.100.1    4        65002    7255    7244        4    0    0 4d13h           3"

    def bgp(self, row):
        return {("r3", "show ip bgp summary"): self.BGP.replace(self.ROW, row)}

    def test_bgp_idle_admin_is_decisive_and_no_clear_follows(self, world):
        got, _ = diagnose(self.bgp("198.51.100.1    4        65002       0       0        1    "
                                   "0    0 never    Idle (Admin)"),
                          target={"device": "r3", "peer": "198.51.100.1"})
        first = got["hypotheses"][0]
        assert first["rule"] == "bgp_admin" and "a clear would not bring it up" in first["claim"]
        assert "bgp_not_established" not in rules_fired(got)

    def test_bgp_remote_as_not_intents(self, world):
        got, _ = diagnose(self.bgp(self.ROW.replace("65002", "65009")),
                          target={"device": "r3", "peer": "198.51.100.1"})
        assert "configured in AS 65009; intent holds AS 65002" in got["hypotheses"][0]["claim"]

    def test_bgp_not_established_with_no_configuration_cause_says_what_it_lacks(self, world):
        got, _ = diagnose(self.bgp("198.51.100.1    4        65002       0       0        1    "
                                   "0    0 never    Active"),
                          target={"device": "r3", "peer": "198.51.100.1"})
        hit = next(h for h in got["hypotheses"] if h["rule"] == "bgp_not_established")
        assert hit["strength"] == "strong" and "is Active" in hit["claim"]
        assert any("ping 198.51.100.1" in w and "C2414" in w for w in hit["incomplete"])

    def test_an_acl_intent_does_not_hold(self, world):
        got, _ = diagnose(with_answer("r4", "show ip interface GigabitEthernet4", R4_IP.replace(
            "Inbound  access list is not set", "Inbound  access list is EDGE")))
        first = got["hypotheses"][0]
        assert first["rule"] == "acl" and first["layer"] == "policy"
        assert first["claim"] == "r4 Gi4 has access list EDGE bound in; intent binds none"

    def test_a_configuration_change_in_the_window(self, world):
        def logs(network, host, now):
            lines = ([{"mnemonic": "SYS-5-CONFIG_I", "at": "2026-11-04T20:00:00Z", "text": "x"}]
                     if host == "r4" else [])
            return {"state": "read", "why": "", "lines": lines}
        got, _ = diagnose(logs=logs)
        assert [(h["rule"], h["strength"]) for h in got["hypotheses"]] == [
            ("config_changed", "circumstantial")]

    def test_a_log_not_read_is_not_checked_never_quiet(self, world):
        got, _ = diagnose(logs=lambda n, h, now: {"state": "unread", "why": "Loki is not "
                                                  "configured", "lines": []})
        assert any(c["rule"] == "config_changed" for c in got["not_checked"])
        assert not any(r["rule"] == "config_changed" for r in got["ruled_out"])

    def test_every_rule_has_a_planted_case_here(self):
        from modules.heal import diagnose as D
        planted = {"admin_down", "down_admin_up", "protocol_down", "cabled_elsewhere",
                   "errors_rising", "mtu", "subnet", "ospf_intent", "passive", "one_way",
                   "ospf_not_full_one_neighbour",
                   "bgp_admin", "bgp_remote_as", "bgp_not_established", "acl", "config_changed"}
        assert {r.name for r in D.RULES} == planted


class TestTheRanking:
    def h(self, rule, layer, strength, incomplete=(), agree=1):
        return {"rule": rule, "layer": layer, "strength": strength,
                "incomplete": list(incomplete), "agree": agree}

    def test_strength_then_complete_then_layer_then_agreement(self):
        from modules.heal import diagnose as D
        got = D.rank([self.h("acl", "policy", "decisive"),
                      self.h("errors_rising", "physical", "strong"),
                      self.h("down_admin_up", "physical", "decisive", incomplete=["x"]),
                      self.h("subnet", "network", "decisive", agree=1),
                      self.h("mtu", "link", "decisive", agree=1),
                      self.h("config_changed", "policy", "circumstantial"),
                      self.h("one_way", "protocol", "strong", agree=3)])
        assert [x["rule"] for x in got] == ["mtu", "subnet", "acl", "down_admin_up",
                                            "errors_rising", "one_way", "config_changed"]
        got = D.rank([self.h("a", "link", "strong", agree=1), self.h("b", "link", "strong",
                                                                      agree=2)])
        assert [x["rule"] for x in got] == ["b", "a"]

    def test_at_most_five_shown_the_rest_counted(self, world):
        worse = R4_IP.replace("10.255.2.15/31", "10.255.2.21/31").replace(
            "MTU is 1500 bytes", "MTU is 1400 bytes").replace(
            "Inbound  access list is not set", "Inbound  access list is EDGE").replace(
            "Outgoing access list is not set", "Outgoing access list is EDGE")
        base = with_answer("r4", "show ip interface GigabitEthernet4", worse)
        base[("r3", "show interfaces GigabitEthernet4")] = [SHOW_IF, SHOW_IF.replace(
            "0 input errors, 0 CRC", "3 input errors, 3 CRC")]
        got, _ = diagnose(base)
        assert len(got["hypotheses"]) == 5 and got["more"] == 1
        assert [h["id"] for h in got["hypotheses"]] == [f"diag:{n}" for n in range(1, 6)]


# ── The record ──────────────────────────────────────────────────────────────────────────────

class TestTheRecord:
    def test_one_masked_row_its_own_record_never_an_incident_entry(self, world):
        from modules.heal import steplog
        got, _ = diagnose()
        assert got["recorded"] is True and got["steps"][-1]["step"] == "record"
        (d,) = steplog.diagnoses("Default")["diagnoses"]
        assert d["id"] == got["id"] and d["words"] == got["words"] and d["runs"] == got["runs"]
        assert steplog.incidents("Default")["entries"] == []
        assert steplog.diagnoses("Default", device="r9")["diagnoses"] == []

    def test_attached_to_its_incident_and_masked(self, world):
        from modules.heal import steplog
        steplog.append("Default", {"row": "decision", "decision": "d1", "incident": "inc-1",
                                   "device": "r4", "outcome": "cant_fix", "steps": []})
        planted = {"id": "dg-1", "incident": "inc-1", "devices": ["r4"], "state": "done",
                   "words": "snmp-server community S3cretRO RO", "hypotheses": [],
                   "raw": "never kept"}
        steplog.record_diagnosis("Default", planted)
        (entry,) = steplog.incidents("Default")["entries"]
        assert entry["diagnosis"]["id"] == "dg-1" and "raw" not in entry["diagnosis"]
        assert "S3cretRO" not in entry["diagnosis"]["words"]
        assert steplog.diagnoses("Default", incident="inc-1")["diagnoses"][0]["id"] == "dg-1"

    def test_an_unwritable_store_is_said_on_the_diagnosis(self, world, monkeypatch):
        from modules.heal import steplog

        def refuse(network, diagnosis, now=None):
            raise steplog.Refused("the store refused it")
        monkeypatch.setattr(steplog, "record_diagnosis", refuse)
        got, _ = diagnose()
        assert got["recorded"] is False
        assert got["steps"][-1] == {"step": "record", "result": "failed",
                                    "words": "not recorded: Refused: the store refused it"}
