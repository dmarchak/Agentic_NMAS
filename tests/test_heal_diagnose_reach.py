"""The "A can't reach B" runbook (board H amendment item 1, part H15; docs/HEAL_TO_INTENT.md
19.3; modules/heal/diagnose_reach.py), read-only and deterministic, on the diagnosis engine.

On the fleet's real intent (tests/test_heal_diagnose.py's `fleet`) and real captures: the path
trace's own `show ip cef` answers (`tests/fixtures/path/cef_fleet.json`, captured through
Mercury's reads engine), `show ip interface` blocks (`tests/fixtures/operational/`), ARP lines
(`tests/fixtures/endpoints/`) and the interface capture H14 uses, each edited minimally where a
scenario needs a fault, the edit said beside it.

- **The plan:** A and B from intent; B one IPv4 address (an IPv6 B refused by name, C2415);
  B's device, or outside management; the ping from A's loopback; refusals naming what they
  compared; the per-hop count and the hops the cap covers.
- **A run, through the one reads engine:** the ping (read, not interpreted), the trace hop by
  hop, each hop's egress twice, its address and access lists, the next hop's ARP entry, the
  route (read, not interpreted) and the next hop's ingress, then the return path. Every read a
  ``diagnosis`` run on History, each hypothesis citing a run that exists.
- **It stops at the first hop that diverges** and names the hops it did not check; the cap
  stops it and says where; a device in another diagnosis is not read, by name.
- **Each rule** (`PATH_RULES`) with a planted case.
"""
import json
import os

import pytest

from tests.test_heal_diagnose import ACTOR, LOOP, Fleet, block, capture, fleet, quiet
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEVICES = [{"hostname": h, "ip": f"192.0.2.{n}", "device_type": t}
            for h, n, t in (("r1", 11, "cisco_xe"), ("r2", 12, "cisco_xe"),
                            ("r3", 13, "cisco_xe"), ("r4", 14, "cisco_xe"),
                            ("r5", 15, "cisco_xe"), ("s1", 21, "cisco_ios"),
                            ("s2", 22, "cisco_ios"), ("s4", 24, "cisco_ios"))]


def _json(*parts):
    with open(os.path.join(ROOT, "tests", "fixtures", *parts), encoding="utf-8") as fh:
        return json.load(fh)


CEF = _json("path", "cef_fleet.json")["answers"]


def _arp(name: str) -> str:
    with open(os.path.join(ROOT, "tests", "fixtures", "endpoints", name), encoding="utf-8") as fh:
        return fh.read()


def arp_answer(capture_name: str, address: str) -> str:
    """`show ip arp <address>`: the capture's header and its line for *address* (what the
    narrowed read prints)."""
    lines = _arp(capture_name).splitlines()
    return "\n".join([lines[0]] + [l for l in lines[1:] if l.split()[1:2] == [address]])


def show_if(name: str) -> str:
    """`show interfaces <name>`: r2's real Loopback0 capture, its first line naming the port (no
    physical port is captured yet; H14's own stand-in)."""
    return LOOP.replace("Loopback0 is up, line protocol is up", f"{name} is up, line protocol is up")


R1_IP = capture("r1__show_ip_interface.txt")
R3_IP = capture("r3__show_ip_interface.txt")
S1_IP = capture("s1__show_ip_interface.txt")
# r4 has no `show ip interface` capture: its Gi3 is r3's Gi3 block with r4's address (r3 and
# r4 are the same platform on the same segment).
R4_GI3 = block(R3_IP, "GigabitEthernet3").replace("10.255.3.13/24", "10.255.3.14/24")
R1_GI2_BLOCK = block(R1_IP, "GigabitEthernet2")


def r1_to_r4() -> dict:
    """r1 to r4's loopback (10.255.1.14), healthy, every answer real: r1's CEF names
    10.255.3.14 out Gi2, r1's ARP holds it on Gi2, and r4's CEF back to r1's loopback names
    10.255.3.11 out Gi3."""
    return {("r1", "ping 10.255.1.14 source Loopback0 repeat 5 timeout 2"): "",
            ("r1", "show ip cef 10.255.1.14"): CEF["r1"]["show ip cef 10.255.1.14"],
            ("r1", "show interfaces GigabitEthernet2"): show_if("GigabitEthernet2"),
            ("r1", "show ip interface GigabitEthernet2"): R1_GI2_BLOCK,
            ("r1", "show ip arp 10.255.3.14"): arp_answer("r1__show_ip_arp.txt", "10.255.3.14"),
            ("r1", "show ip route 10.255.1.14"): "",
            ("r4", "show ip interface GigabitEthernet3"): R4_GI3,
            ("r4", "show ip cef 10.255.1.11"): CEF["r4"]["show ip cef 10.255.1.11"]}


def s1_to_r4() -> dict:
    """s1 (IOS) to r4's loopback through r1: two routed hops, every forward answer real
    (s1's default route to 10.255.2.10 out Gi0/2, its ARP for it, r1's Gi3 block). r4's CEF
    toward s1's loopback is not captured, so the return path is unread."""
    out = {k: v for k, v in r1_to_r4().items() if k[0] == "r1" and "ping" not in k[1]}
    out.update({("s1", "ping 10.255.1.14 source Loopback0 repeat 5 timeout 2"): "",
                ("s1", "show ip cef 10.255.1.14"): CEF["s1"]["show ip cef 10.255.1.14"],
                ("s1", "show interfaces GigabitEthernet0/2"): show_if("GigabitEthernet0/2"),
                ("s1", "show ip interface GigabitEthernet0/2"): block(S1_IP,
                                                                      "GigabitEthernet0/2"),
                ("s1", "show ip arp 10.255.2.10"): arp_answer("s1__show_ip_arp.txt",
                                                              "10.255.2.10"),
                ("s1", "show ip route 10.255.1.14"): "",
                ("r1", "show ip interface GigabitEthernet3"): block(R1_IP, "GigabitEthernet3"),
                ("r4", "show ip interface GigabitEthernet3"): R4_GI3})
    return out


@pytest.fixture
def world(networks, monkeypatch):  # noqa: F811 (the fixture)
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in _DEVICES])
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, c, read_timeout=None: conn.answer(c))
    return networks


def reach(answers, device="r1", address="10.255.1.14", edit=None, logs=quiet, **kw):
    from modules.heal import diagnose as D
    model, intents = fleet(edit)
    f = Fleet(answers)
    got = D.run("Default", "cant_reach", {"device": device, "address": address}, ACTOR,
                session=f, logs=logs, sleep=kw.pop("sleep", lambda s: None), model=model,
                intents=intents, **kw)
    return got, f


def changed(base: dict, host: str, command: str, text: str) -> dict:
    out = dict(base)
    out[(host, command)] = text
    return out


def rules(got) -> list:
    return [h["rule"] for h in got["hypotheses"]]


# ── The plan ────────────────────────────────────────────────────────────────────────────────

class TestThePlan:
    def plan(self, target, edit=None):
        from modules.heal import diagnose as D
        model, intents = fleet(edit)
        return D.plan("Default", "cant_reach", target, model=model, intents=intents)

    def test_a_to_bs_device_from_as_loopback(self):
        p = self.plan({"device": "r1", "address": "10.255.1.14"})
        assert (p["source"], p["dest"], p["owner"], p["src"], p["src_address"]) == (
            "r1", "10.255.1.14", "r4", "Loopback0", "10.255.1.11")
        assert p["words"] == "r1 to 10.255.1.14 (r4 Lo0)" and p["outside"] == ""
        assert [c["command"] for c in p["reads"]["r1"]] == [
            "ping 10.255.1.14 source Loopback0 repeat 5 timeout 2"]

    def test_an_address_outside_management_says_what_is_read(self):
        p = self.plan({"device": "r4", "address": "8.8.8.8"})
        assert p["owner"] == "" and p["words"] == "r4 to 8.8.8.8 (outside management)"
        assert "then a traceroute; no return path is read" in p["outside"]

    def test_no_loopback_pings_unsourced(self):
        def edit(intents):
            intents["r1"]["interfaces"] = [i for i in intents["r1"]["interfaces"]
                                           if not i["name"].startswith("Loopback")]
        p = self.plan({"device": "r1", "address": "10.255.1.14"}, edit)
        assert p["src"] == "" and [c["command"] for c in p["reads"]["r1"]] == [
            "ping 10.255.1.14 repeat 5 timeout 2"]

    def test_the_cap_covers_nine_hops(self):
        from modules import path_trace
        from modules.heal import diagnose as D
        from modules.heal import diagnose_reach as R
        assert (R.PER_HOP, R.FIXED, R.HOPS_AT_CAP, D.MAX_COMMANDS) == (7, 3, 9, 70)
        assert D.TEMPLATES["cef"]["*"] == path_trace.COMMAND   # the path trace's own read

    @pytest.mark.parametrize("target,words", [
        ({"device": "r9", "address": "10.255.1.14"}, "r9 has no committed intent in Default"),
        ({"device": "r1", "address": "10.255.1"}, "'10.255.1' is not one IPv4 or IPv6 address"),
        ({"device": "r1", "address": "fe80::1%Gi2"}, "is not one IPv4 or IPv6 address"),
        ({"device": "r1", "address": "10.255.1.11"},
         "10.255.1.11 is r1's own address (Lo0), so there is no path to follow"),
        ({"device": "r1", "address": "2001:db8:1::14"},
         "2001:db8:1::14 is an IPv6 address; \"A can't reach B\" follows IPv4 forwarding only "
         "(`show ip cef`): its IPv6 form waits for `show ipv6 cef` to be captured and parsed "
         "(C2415), so nothing was read")])
    def test_refusals_name_what_they_compared(self, target, words):
        from modules.heal import diagnose as D
        with pytest.raises(D.Refused) as e:
            self.plan(target)
        assert words in str(e.value)

    @pytest.mark.parametrize("kind,field,value", [
        ("cef", "dest", "10.255.1.14 | redirect flash:x"), ("cef", "dest", "2001:db8::1"),
        ("arp", "nh", "10.255.3.14\nreload"), ("route", "dest", "10.255.1"),
        ("acl_counters", "acl", "EDGE-IN | include x"), ("acl_counters", "acl", "EDGE IN"),
        ("reach_ping_src", "src", "Loopback0 size 9000")])
    def test_a_spliced_destination_next_hop_or_acl_is_one_token(self, kind, field, value):
        from modules.heal import diagnose as D
        args = {"dest": "10.255.1.14", "nh": "10.255.3.14", "acl": "EDGE-IN",
                "src": "Loopback0"}
        names = {"cef": ("dest",), "arp": ("nh",), "route": ("dest",), "acl_counters": ("acl",),
                 "reach_ping_src": ("dest", "src")}[kind]
        assert D.render(kind, "cisco_ios", **{n: args[n] for n in names})  # the control
        args[field] = value
        with pytest.raises(D.Refused):
            D.render(kind, "cisco_ios", **{n: args[n] for n in names})

    def test_an_address_several_devices_hold_names_none(self):
        # The fleet's routers share one management address (a lab tool's); read from intent,
        # never written here.
        from modules.heal import diagnose as D
        from modules.heal import diagnose_reach as R
        from modules.neighbours import _all_lines
        _model, intents = fleet()
        one, shared = R.holders(_all_lines(intents))
        (address, hosts), = shared.items()
        assert len(hosts) == 5 and address not in one
        with pytest.raises(D.Refused) as e:
            self.plan({"device": "r1", "address": address})
        assert str(e.value) == (f"{address} is held by {' and '.join(hosts)} in intent, so which "
                                "device B is cannot be told")

    def test_an_ipv6_b_reads_nothing(self, world):
        got, f = reach({}, address="2001:db8:1::14")
        assert got["state"] == "refused" and "C2415" in got["words"] and f.sent == []


# ── A run ───────────────────────────────────────────────────────────────────────────────────

class TestARun:
    def test_a_healthy_path_and_its_return_find_no_cause(self, world):
        got, f = reach(r1_to_r4())
        assert got["state"] == "done" and got["hypotheses"] == [], got["hypotheses"]
        assert got["words"] == "no cause found in what Mercury reads"
        ruled = [r["check"] for r in got["ruled_out"]]
        for words in ("each hop's egress and its next hop's ingress are up",
                      "no hop's egress errors rose across the two reads",
                      "every hop's next hop is resolved",
                      "every device on the path has a route toward B", "the path never loops",
                      "the path stays inside the network to B's device",
                      "the return path from B's device reaches A",
                      "no hop binds an access list intent does not hold",
                      "no configuration change was logged on a device read in the last hour"):
            assert words in ruled, ruled
        assert f.sent[:2] == [("r1", "ping 10.255.1.14 source Loopback0 repeat 5 timeout 2"),
                              ("r1", "show ip cef 10.255.1.14")]
        assert f.sent[7:] == [("r1", "show interfaces GigabitEthernet2"),
                              ("r4", "show ip cef 10.255.1.11")]
        assert sorted(f.sent[2:7]) == sorted([          # round 1: both devices concurrently
            ("r1", "show interfaces GigabitEthernet2"), ("r1", "show ip interface GigabitEthernet2"),
            ("r1", "show ip arp 10.255.3.14"), ("r1", "show ip route 10.255.1.14"),
            ("r4", "show ip interface GigabitEthernet3")])
        assert got["commands"] == 9 and got["devices"] == ["r1", "r4"]

    def test_the_uninterpreted_reads_are_said_never_guessed(self, world):
        got, _ = reach(r1_to_r4())
        reach_step = next(s for s in got["steps"] if s["step"] == "reach")
        assert "does A reach B, from its loopback (read, and not yet interpreted: C2414)" in \
            reach_step["words"]
        hop = next(s for s in got["steps"] if s["step"] == "hop" and s.get("device") == "r1")
        assert "the route toward B and its source (read, and not yet interpreted: C2414)" in \
            hop["words"]

    def test_every_read_is_a_diagnosis_run_and_cited_by_reference(self, world):
        from modules.nsot import reads
        got, _ = reach(changed(r1_to_r4(), "r1", "show ip arp 10.255.3.14",
                               arp_answer("r1__show_ip_arp.txt", "10.255.3.14").splitlines()[0]))
        runs = {r["id"]: r for r in reads.runs("Default")["runs"]}
        assert set(got["runs"]) == set(runs)
        assert all(r["by"] == "diagnosis" and r["actor"] == ACTOR for r in runs.values())
        first = got["hypotheses"][0]
        assert first["rule"] == "next_hop_unresolved"
        for e in first["evidence"]:
            _, run_id, host, command = e["read"].split(":", 3)
            assert reads.answer_of(runs[run_id], host, command)["state"] == "answered"

    def test_two_hops_in_order_and_an_unread_return_said(self, world):
        got, f = reach(s1_to_r4(), device="s1")
        assert got["hypotheses"] == [], got["hypotheses"]
        trace = next(s for s in got["steps"] if s["step"] == "trace")
        assert trace["words"] == ("1 branch(es): s1 Gi0/2 > r1 Gi2: delivered to r4")
        hops = [s["device"] for s in got["steps"] if s["step"] == "hop"]
        assert hops[0] == "s1" and set(hops[:2]) == {"s1", "r1"} and "r4" in hops
        assert [c["check"] for c in got["not_checked"]][:1] == ["the return path past r4"]
        assert ("r4", "show ip cef 10.255.1.21") in f.sent

    def test_the_second_read_waits_the_delta_after_the_first(self, world):
        from modules.heal import diagnose as D
        waits = []
        reach(r1_to_r4(), sleep=waits.append)
        assert waits == [D.DELTA_SECONDS]

    def test_outside_management_sends_the_traceroute_and_reads_no_return(self, world):
        # r5's answer is r4's real 8.8.8.8 answer with its next hop the outside peer
        # 203.0.113.1 out Gi4 (r5's own CEF is not captured).
        answers = {("r4", "show ip cef 8.8.8.8"): "8.8.8.8/32\n  nexthop 198.51.100.3 "
                                                    "GigabitEthernet2",
                   ("r5", "show ip cef 8.8.8.8"): "8.8.8.8/32\n  nexthop 203.0.113.1 "
                                                    "GigabitEthernet4"}
        got, f = reach(answers, device="r4", address="8.8.8.8")
        assert ("r4", "traceroute 8.8.8.8 numeric timeout 2 probe 1 ttl 1 16") in f.sent
        ret = next(s for s in got["steps"] if s["step"] == "return")
        assert ret["words"] == "the return path is not read: B is outside management"
        assert "leaves_network" not in rules(got)

    def test_the_cap_stops_and_says_where(self, world, monkeypatch):
        from modules.heal import diagnose as D
        monkeypatch.setattr(D, "MAX_COMMANDS", 4)
        got, f = reach(r1_to_r4())
        assert got["stopped"] == ("stopped at the 4-command cap before the first hop's checks; "
                                  "no hop was checked")
        assert got["commands"] == 2 and len(f.sent) == 2
        monkeypatch.setattr(D, "MAX_COMMANDS", 8)
        got, f = reach(r1_to_r4())
        assert got["stopped"] == ("stopped at the 8-command cap while following the return "
                                  "path; the devices past it not read")
        assert got["commands"] == 8 and len(f.sent) == 8

    def test_the_per_device_count_is_kept(self, world, monkeypatch):
        from modules.heal import diagnose as D
        monkeypatch.setattr(D, "MAX_PER_DEVICE", 3)
        got, f = reach(r1_to_r4())
        assert [c for h, c in f.sent if h == "r1"] == [
            "ping 10.255.1.14 source Loopback0 repeat 5 timeout 2", "show ip cef 10.255.1.14",
            "show interfaces GigabitEthernet2"]            # round 2's one read fits the three
        hop = next(s for s in got["steps"] if s["step"] == "hop" and s.get("device") == "r1")
        assert hop["result"] == "not_read" and hop["words"] == (
            "hop 1: not read: r1 has been asked 2 reads in this diagnosis, and 4 more would "
            "pass the 3 a device may be asked")

    def test_a_hop_device_in_another_diagnosis_is_not_read_by_name(self, world):
        from modules.heal import diagnose as D
        with D.DiagnosisLock("Default", ["r4"], "dg-other", "someone@example.invalid"):
            got, f = reach(r1_to_r4())
        assert "r4" not in {h for h, _ in f.sent}
        skipped = [s for s in got["steps"] if s.get("device") == "r4"]
        assert skipped and all(s["result"] == "not_read" for s in skipped)
        assert "r4 is in diagnosis dg-other" in skipped[0]["words"]
        assert "each hop's egress and its next hop's ingress are up" not in [
            r["check"] for r in got["ruled_out"]]

    def test_a_busy_a_is_refused_by_name_nothing_read(self, world):
        from modules.heal import diagnose as D
        with D.DiagnosisLock("Default", ["r1"], "dg-other", "someone@example.invalid"):
            got, f = reach(r1_to_r4())
        assert got["state"] == "busy" and "r1 is in diagnosis dg-other" in got["words"]
        assert f.sent == []

    def test_the_lock_is_released_after_the_run(self, world):
        from modules.heal import diagnose as D
        got, _ = reach(r1_to_r4())
        assert got["state"] == "done" and got["devices"] == ["r1", "r4"]   # both were held
        with D.DiagnosisLock("Default", ["r1", "r4"], "dg-next", ACTOR):
            pass


# ── Stops at the first hop that diverges ────────────────────────────────────────────────────

class TestStopsAtTheFirstDivergence:
    def test_the_hops_after_it_are_named_not_checked(self, world):
        answers = changed(s1_to_r4(), "s1", "show interfaces GigabitEthernet0/2",
                          show_if("GigabitEthernet0/2").replace(
                              "GigabitEthernet0/2 is up, line protocol is up",
                              "GigabitEthernet0/2 is administratively down, line protocol is "
                              "down"))
        got, f = reach(answers, device="s1")
        assert rules(got)[0] == "hop_down"
        assert ("r1", "show interfaces GigabitEthernet2") not in f.sent
        stop = [s for s in got["steps"] if s["result"] == "stopped"]
        assert stop[0]["words"] == ("stopped at s1: hop 1 diverges from intent; the hops after "
                                    "it were not checked (r1)")
        assert {"check": "the hops after s1", "why": "the runbook stops at the first hop that "
                "diverges"} in got["not_checked"]
        ret = next(s for s in got["steps"] if s["step"] == "return")
        assert ret["result"] == "not_read"


# ── Each rule, planted ──────────────────────────────────────────────────────────────────────

class TestEachRule:
    def test_hop_down_says_whether_intent_holds_it_shut(self, world):
        got, _ = reach(changed(r1_to_r4(), "r1", "show interfaces GigabitEthernet2",
                               show_if("GigabitEthernet2").replace(
                                   "is up, line protocol is up",
                                   "is administratively down, line protocol is down")))
        first = got["hypotheses"][0]
        assert (first["rule"], first["layer"], first["strength"]) == (
            "hop_down", "physical", "decisive")
        assert first["claim"] == ("r1 Gi2, the path's egress toward r4, is administratively "
                                  "down, though intent holds it up: it was shut outside intent")

    def test_the_next_hops_ingress_down(self, world):
        got, _ = reach(changed(r1_to_r4(), "r4", "show ip interface GigabitEthernet3",
                               R4_GI3.replace("GigabitEthernet3 is up, line protocol is up",
                                              "GigabitEthernet3 is down, line protocol is down")))
        first = got["hypotheses"][0]
        assert first["rule"] == "hop_down"
        assert first["claim"] == ("r4 Gi3, the next hop's ingress from r1, is down while "
                                  "administratively up")

    def test_hop_protocol_down(self, world):
        got, _ = reach(changed(r1_to_r4(), "r1", "show interfaces GigabitEthernet2",
                               show_if("GigabitEthernet2").replace("line protocol is up",
                                                                   "line protocol is down")))
        assert rules(got) == ["hop_protocol_down"]

    def test_errors_rising_across_the_two_reads(self, world):
        more = show_if("GigabitEthernet2").replace("0 input errors, 0 CRC",
                                                   "12 input errors, 9 CRC")
        got, _ = reach(changed(r1_to_r4(), "r1", "show interfaces GigabitEthernet2",
                               [show_if("GigabitEthernet2"), more]))
        first = got["hypotheses"][0]
        assert first["rule"] == "hop_errors_rising" and first["agree"] == 2
        assert first["claim"] == "r1 Gi2's input errors rose by 12 (CRC by 9) in 10 s"

    def test_next_hop_unresolved_incomplete_or_absent(self, world):
        real = arp_answer("r1__show_ip_arp.txt", "10.255.3.14")
        pending = real.replace("206   aac1.ab7b.a0db", "  0   Incomplete    ")
        for text, words in ((pending, "(ARP incomplete)"), (real.splitlines()[0],
                                                            "(ARP has no entry)")):
            got, _ = reach(changed(r1_to_r4(), "r1", "show ip arp 10.255.3.14", text))
            first = got["hypotheses"][0]
            assert (first["rule"], first["layer"]) == ("next_hop_unresolved", "link")
            assert first["claim"] == ("r1 has not resolved its next hop 10.255.3.14 on Gi2 "
                                      + words)

    def test_an_arp_answer_that_is_no_table_is_never_read_as_no_entry(self, world):
        got, _ = reach(changed(r1_to_r4(), "r1", "show ip arp 10.255.3.14", ""))
        assert got["state"] == "done" and "next_hop_unresolved" not in rules(got)
        assert "next_hop_unresolved" in [n.get("rule") for n in got["not_checked"]]
        assert "every hop's next hop is resolved" not in [r["check"] for r in got["ruled_out"]]

    def test_no_route_at_a_hop(self, world):
        # r3's real answer for 198.51.100.3 (r5 Gi3): no route.
        answers = {("r3", "ping 198.51.100.3 source Loopback0 repeat 5 timeout 2"): "",
                   ("r3", "show ip cef 198.51.100.3"): CEF["r3"]["show ip cef 198.51.100.3"]}
        got, f = reach(answers, device="r3", address="198.51.100.3")
        first = got["hypotheses"][0]
        assert (first["rule"], first["layer"], first["strength"]) == (
            "no_route", "network", "decisive")
        assert first["claim"] == "r3 has no route to 198.51.100.3"
        assert first["evidence"][0]["intent"] == "198.51.100.3 is r5 Gi3's"
        assert len(f.sent) == 2

    def test_a_forwarding_loop(self, world):
        # r1's and r4's real answers for each other's loopbacks, the prefix edited to r2's.
        answers = dict(r1_to_r4())
        answers = {(h, c.replace("10.255.1.14", "10.255.1.12")): v for (h, c), v in
                   answers.items() if h == "r1"}
        answers.update({("r1", "show ip cef 10.255.1.12"): "10.255.1.12/32\n  nexthop "
                                                           "10.255.3.14 GigabitEthernet2",
                        ("r4", "show ip cef 10.255.1.12"): "10.255.1.12/32\n  nexthop "
                                                           "10.255.3.11 GigabitEthernet3",
                        ("r4", "show ip interface GigabitEthernet3"): R4_GI3})
        got, _ = reach(answers, address="10.255.1.12")
        first = got["hypotheses"][0]
        assert first["rule"] == "loop" and "r4 sends it back to r1: a forwarding loop" in \
            first["claim"]

    def test_the_path_leaves_the_network_though_b_is_managed(self, world):
        # r1's real answer with its next hop an address no device holds.
        got, _ = reach(changed(r1_to_r4(), "r1", "show ip cef 10.255.1.14",
                               CEF["r1"]["show ip cef 10.255.1.14"].replace("10.255.3.14",
                                                                           "10.255.3.99")))
        first = got["hypotheses"][0]
        assert (first["rule"], first["strength"]) == ("leaves_network", "strong")
        assert "though 10.255.1.14 is r4 Lo0's" in first["claim"]

    def test_no_return_path(self, world):
        got, _ = reach(changed(r1_to_r4(), "r4", "show ip cef 10.255.1.11",
                               CEF["r4"]["show ip cef 198.51.100.1"]))
        first = got["hypotheses"][0]
        assert (first["rule"], first["strength"]) == ("return_path", "decisive")
        assert first["claim"] == ("the return path from r4 to r1's 10.255.1.11: dropped at r4: "
                                  "no route to 10.255.1.11")

    def test_an_acl_intent_does_not_hold_and_its_counters_read(self, world):
        got, f = reach(changed(r1_to_r4(), "r4", "show ip interface GigabitEthernet3",
                               R4_GI3.replace("Inbound  access list is not set",
                                              "Inbound  access list is EDGE-IN")))
        first = got["hypotheses"][0]
        assert (first["rule"], first["layer"]) == ("hop_acl", "policy")
        assert first["claim"] == ("r4 Gi3, on the path toward 10.255.1.14, has access list "
                                  "EDGE-IN bound in; intent binds none")
        assert ("r4", "show ip access-lists EDGE-IN") in f.sent

    def test_a_configuration_change_on_a_device_read(self, world):
        def logs(network, host, now):
            lines = ([{"mnemonic": "SYS-5-CONFIG_I", "at": "2026-11-05T01:00:00Z", "text": "x"}]
                     if host == "r4" else [])
            return {"state": "read", "why": "", "lines": lines}
        got, _ = reach(r1_to_r4(), logs=logs)
        assert [(h["rule"], h["strength"]) for h in got["hypotheses"]] == [
            ("path_config_changed", "circumstantial")]

    def test_every_rule_has_a_planted_case_here(self):
        from modules.heal import diagnose_reach as R
        planted = {"hop_down", "hop_errors_rising", "hop_protocol_down", "next_hop_unresolved",
                   "no_route", "loop", "leaves_network", "return_path", "hop_acl",
                   "path_config_changed"}
        assert {r.name for r in R.PATH_RULES} == planted


class TestTheRecord:
    def test_one_masked_row_naming_the_runbook(self, world):
        from modules.heal import steplog
        got, _ = reach(r1_to_r4())
        assert got["recorded"] is True and got["steps"][-1]["step"] == "record"
        (d,) = steplog.diagnoses("Default")["diagnoses"]
        assert (d["id"], d["runbook"], d["devices"]) == (got["id"], "cant_reach", ["r1", "r4"])
