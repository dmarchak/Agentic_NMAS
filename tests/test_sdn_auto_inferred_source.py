"""AUTO never acts on an inferred source (C2147; the operator's rule, 2026-10-29, PHASE8_PLAN
17.7): a detection whose source Mercury inferred from the controller's topology (C2002's
``source_from``), or that names no single source the flows name, always goes to a person,
whatever the network's mode or the action's risk; only a source the flows themselves name is
applied unattended.

**The data is the Lab 8 walk's own** (tests/test_sdn_source_from_topology.py's: the walk's
flood on s1 port 2, its flows matching MAC addresses only, judged again with Ryu 4.34's captured
topology, h2 the one host on that port; h2 with only its IPv6 address for the IPv6 case; the
walk's second flood on s1, whose L4 flows name 192.0.2.2, for the flow-named case). The network
is marked lab and AUTO is on, allowing medium (so a refusal is never the risk's).

- **The decision** (`modes.decide`, `modes.source_refusal`): an inferred source is HITL for
  that response, its words naming the comparison (AUTO applies only a source the flows name)
  and both operands (the flows entering the port name none; the source and how the topology
  gave it), IPv4 and IPv6 hosts alike; a detection naming no single source (several hosts on
  the port, the topology not read when it fired) is HITL too, saying why; a flow-named source
  and an action on no source (remove a flow) are AUTO's as before.
- **The loop** (`loop.run_pass`): the inferred source's response is kept awaiting a person with
  those words, nothing previewed or applied, and it is a Needs attention row as any awaiting
  incident; the flow-named one is previewed and applied as Mercury, autonomous.
- **The apply** (`closed_loop.respond_to_threat`): an unattended (AUTO) confirm whose ask's
  source was found in the topology is refused, naming both, nothing sent, whether or not the
  detection is handed in; a person's confirm of the same ask is not refused by it.
"""
import time

import pytest

from modules import attention as A
from modules.sdn import closed_loop as CL
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_modes_loop import mark_lab
from tests.test_sdn_ops_v2 import lab  # noqa: F401 - the fixture
from tests.test_sdn_source_from_topology import (CONN, H2, H5, h2_v6_only, plus, stored,
                                                 walk_flood)

NET = "Default"
H2_V6 = "2001:db8:8::2"
#: The words an inferred source's response awaits a person with (C2147), read off the walk's
#: data by hand: the flood entered s1 by port 2; h2 is the one host the topology lists there.
INFERRED = ("A person confirms this one: the source was inferred from the topology: a person confirms "
            "it (AUTO applies only a source the flows themselves name; the flows entering port 2 "
            "name none, and {addr} came from the controller's topology: the one host on port 2, "
            "{addr} (00:00:00:00:00:02))")


def auto_on(network=NET):
    mark_lab(network)
    MD.turn_on(network, actor="admin@example.com", actor_verified="access", reason="lab 8 run",
               until=time.time() + 600, allowed_risk="medium")


def flood(key="walk-flood-1-s1", topo=None):
    """The walk's flood *key* judged again with *topo*, as a detection on the test's network;
    its ports' bytes edited to small packets (C2313: one stream of 1,512 B packets is watched
    under the rule, and AUTO's source rule is what these tests are about, on a flood)."""
    d, _c, _s = walk_flood(key, stored() if topo is None else topo, small=True)
    return dict(d, network=NET)


# ───────────────────────────────────────────────────────────────────────────── the decision

@pytest.mark.parametrize("topo,addr", [(None, H2), ("v6", H2_V6)], ids=["ipv4", "ipv6"])
@pytest.mark.parametrize("action,risk", [("drop_source", "low"), ("rate_limit_source", "low")])
def test_an_inferred_source_under_auto_is_a_person_s_whatever_the_risk(networks, topo, addr,  # noqa: F811,E501
                                                                       action, risk):
    auto_on()
    d = flood(topo=stored(edit=h2_v6_only) if topo == "v6" else None)
    assert d["source"] == addr and d["source_from"]["how"] == "topology", "premise"
    got = MD.decide(NET, risk, detection=d, action=action)
    assert got == {"auto": False, "autonomous": None, "words": INFERRED.format(addr=addr)}
    assert MD.decide(NET, risk)["auto"] is True, "premise: AUTO allows the risk"


@pytest.mark.parametrize("topo,why", [
    (lambda: stored(edit=plus(H5)),
     "not named: the controller's topology lists 2 hosts on port 2 (192.0.2.2 "
     "(00:00:00:00:00:02), 192.0.2.5 (00:00:00:00:00:05))"),
    (lambda: stored(now=__import__("tests.test_sdn_topology", fromlist=["READ_EPOCH"])
                    .READ_EPOCH + 3600),
     "not named: the controller's topology could not be read (the SDN reader's last read, at "
     "2026-10-27T09:35:49Z, is older than its promise of"),
], ids=["several", "unread"])
def test_a_detection_naming_no_single_source_under_auto_is_a_person_s(networks, topo, why):  # noqa: F811,E501
    auto_on()
    d = flood(topo=topo())
    assert d["source"] is None, "premise"
    got = MD.decide(NET, "low", detection=d, action="drop_source")
    assert not got["auto"]
    assert got["words"].startswith(
        "A person confirms this one: the flows name no single source, and a source they do not name is "
        "inferred: a person confirms it (AUTO applies only a source the flows themselves name; "
        + why), got["words"]


def test_a_flow_named_source_and_an_action_on_no_source_stay_auto_s(networks):  # noqa: F811
    auto_on()
    named = flood("walk-flood-2-s1", stored(edit=plus(H5)))
    assert named["source"] == H2 and "source_from" not in named, "premise: the flows name it"
    assert MD.decide(NET, "low", detection=named, action="drop_source")["auto"] is True
    assert MD.source_refusal(named, "rate_limit_source") == ""
    assert MD.source_refusal(flood(), "remove_flow") == "", "an action on no source"


# ───────────────────────────────────────────────────────────────────────────── the loop

def _pass(monkeypatch, d, action="drop_source", params=None, logged=None):
    """One loop pass over *d* with AUTO on, its classification passed proposing *action* on
    *params* (as the AI may: the detection's own source), the response core recorded."""
    seen = []

    def respond(network, det, act, prm=None, *, confirm=None, **kw):
        seen.append({"action": act, "confirm": confirm is not None, "mode": kw.get("mode")})
        if confirm is None:
            return {"ok": True, "ask": {"a": 1}, "plan": {"hash": "h"}}
        return {"id": "sdnop-1", "outcome": "verified"}

    monkeypatch.setattr(CL, "respond_to_threat", respond)
    monkeypatch.setattr(CL, "log_response", lambda *a, **k: (
        (logged.append(k) if logged is not None else None), {"step": "respond", "words": "x"})[1])
    monkeypatch.setattr(LP, "classify", lambda network, det, job, **kw: {
        "action": action, "risk": CL.CATALOGUE[action]["risk"],
        "params": dict(params or {}), "classification": {"threat_type": "flood"},
        "person": False, "why": "", "refused_call": "", "words": "planted: passed"})
    out = LP.run_pass(NET, collect=lambda: {"network": NET, "summary": {}, "state": "ok"},
                      observe=lambda network, collected: {
                          "ok": True, "fired": [d["key"]], "resolved": [], "detections": [d]},
                      driver=lambda n, c: {"ok": False, "error": "unused"})
    assert out["ok"], out["error"]
    return out, seen


@pytest.mark.parametrize("topo,addr", [(None, H2), ("v6", H2_V6)], ids=["ipv4", "ipv6"])
def test_in_the_loop_an_inferred_source_awaits_a_person_and_nothing_is_applied(networks,  # noqa: F811,E501
                                                                               monkeypatch,
                                                                               topo, addr):
    auto_on()
    d = flood(topo=stored(edit=h2_v6_only) if topo == "v6" else None)
    out, seen = _pass(monkeypatch, d, params={"source": addr})
    assert seen == [] and out["applied"] == [], "nothing previewed or applied unattended"
    (row,) = LP.awaiting(NET)["rows"]
    assert row["id"] in out["proposed"] and row["why"] == INFERRED.format(addr=addr)
    assert row["detection"]["source_from"]["state"] == "named"
    said = [x["words"] for x in out["lines"] if x["step"] == "respond"]
    assert said == [f"Awaiting a person's confirm ({row['id']}): {INFERRED.format(addr=addr)}"]
    # A Needs attention row, as any incident awaiting a person.
    rows = A.sdn_responses_source(found={NET: LP.awaiting(NET)})["rows"]
    assert len(rows) == 1 and row["id"] in str(rows[0])


def test_in_the_loop_a_flow_named_source_is_applied_as_before(networks, monkeypatch):  # noqa: F811
    auto_on()
    d = flood("walk-flood-2-s1", stored(edit=plus(H5)))
    out, seen = _pass(monkeypatch, d, params={"source": H2})
    assert out["applied"] == [{"id": "sdnop-1", "outcome": "verified"}]
    assert seen == [{"action": "drop_source", "confirm": False, "mode": None},
                    {"action": "drop_source", "confirm": True, "mode": "auto"}]
    assert LP.awaiting(NET)["rows"] == []


# ───────────────────────────────────────────────────────────────────────────── the apply

@pytest.mark.usefixtures("lab")
@pytest.mark.parametrize("handed", [True, False], ids=["detection-handed", "ask-alone"])
def test_an_unattended_confirm_of_a_topology_source_is_refused_and_nothing_is_sent(
        lab, monkeypatch, handed):  # noqa: F811
    # The walk's flood as a flood (C2313: its ports' bytes edited to small packets).
    d, _c, _s = walk_flood("walk-flood-1-s1", stored(name=CONN), small=True)
    d = dict(d, connection="lab-controller", network=NET)
    preview = CL.respond_to_threat(NET, d, "drop_source")
    assert preview["ok"], preview["error"]
    how = preview["ask"]["detection"]["source_from"]
    assert how.startswith("from the controller's topology: the one host on port 2"), "premise"
    applied = []
    monkeypatch.setattr("modules.sdn.flow_ops.apply",
                        lambda *a, **k: applied.append(k.get("mode")) or {"outcome": "planted"})
    confirm = {"ask": preview["ask"], "hash": preview["plan"]["hash"]}
    done = CL.respond_to_threat(NET, d if handed else None, "drop_source", confirm=confirm,
                                actor=LP.AUTO_ACTOR, actor_verified="system", mode="auto",
                                autonomous={"reason": "lab 8 run"})
    assert done == {"ok": False, "outcome": "refused", "error": (
        "AUTO refused: the source was inferred from the topology: a person confirms it (AUTO "
        f"applies only a source the flows themselves name, and this one's source was not: {how})"
        ": nothing was sent")}
    assert applied == [] and lab["fake"].writes == []
    # A person's confirm of the same ask is not refused by it.
    person = CL.respond_to_threat(NET, d if handed else None, "drop_source", confirm=confirm,
                                  actor="op@example.com", actor_verified="access")
    assert person == {"outcome": "planted"} and applied == ["hitl"]


# ───────────────────────────────────────────────── a source NetBox declares on its port (D)

def _netbox(monkeypatch, d, rows=None, state="read"):
    """NetBox's view (`known.read`) with one end host, h2, cabled to *d*'s switch port 2, its
    address and MAC the walk's (or *rows* instead)."""
    if rows is None:
        rows = [{"name": "h2", "kind": "end host", "interface": "eth0", "mac": "00:00:00:00:00:02",
                 "ipv4": [H2], "ipv6": [], "switch": "s1", "switch_interface": "eth2",
                 "dpid": int(d["dpid"]), "port_no": 2}]
    monkeypatch.setattr("modules.sdn.known.read",
                        lambda network: {"state": state, "why": "", "rows": rows})


def test_a_source_netbox_declares_on_its_port_is_auto_s(networks, monkeypatch):  # noqa: F811
    """Lab 9 Part B, D (2026-11-20): a fabric whose flows match MAC addresses names no source;
    where NetBox cables exactly one end host to the port, with the source's address and the MAC
    the topology lists, the source is declared, not inferred, and AUTO acts on it."""
    auto_on()
    d = flood()
    assert d["source"] == H2 and d["source_from"]["state"] == "named", "premise"
    _netbox(monkeypatch, d)
    got = MD.decide(NET, "low", detection=d, action="drop_source")
    assert got["auto"] is True
    assert got["words"].endswith(
        "; its source: NetBox declares it: h2's eth0 (192.0.2.2, 00:00:00:00:00:02) is cabled "
        "to s1 eth2 (port 2), where the controller lists that host alone")


def test_auto_s_record_and_its_log_keep_the_basis_it_acted_on_for_the_source(networks,  # noqa: F811,E501
                                                                             monkeypatch):
    """C4154 (the Lab 9 hardware, 2026-11-20): AUTO's rate limit on a source NetBox declared
    (sdnop-20261120T064649Z-60fbeceb) was recorded "By Mercury (AUTO) (autonomous: AUTO by
    …)" alone, so whether C4133's check ran could be told only from the code. The autonomous
    record keeps the basis, the pass logs it beside the response, and a flow-named source
    says that instead."""
    from modules import history_sources as HS
    auto_on()
    d = flood()
    _netbox(monkeypatch, d)
    got = MD.decide(NET, "low", detection=d, action="rate_limit_source")
    assert got["autonomous"]["source"].startswith("NetBox declares it: h2's eth0 (192.0.2.2")
    named = flood("walk-flood-2-s1", stored(edit=plus(H5)))
    assert MD.decide(NET, "low", detection=named, action="drop_source")["autonomous"][
        "source"] == "the flows name it"
    assert "source" not in MD.decide(NET, "low", detection=d, action="remove_flow")[
        "autonomous"], "an action on no source names none"
    logged, real_log = [], CL.log_response
    _out, seen = _pass(monkeypatch, d, action="rate_limit_source", logged=logged)
    assert [s["mode"] for s in seen if s["confirm"]] == ["auto"]
    (kept,) = logged
    assert kept["basis"].startswith("NetBox declares it: h2's eth0"), "in the response's line"
    line = real_log(NET, {"id": "sdnop-1", "outcome": "verified"},
                           action="rate_limit_source", who="Mercury (AUTO)",
                           ask={"connection": "lab", "dpid": 1}, basis=kept["basis"])
    assert line["words"].endswith("; its source: " + kept["basis"])
    row = {"mode": "auto", "actor": "Mercury (AUTO)", "autonomous": got["autonomous"]}
    assert "; its source: NetBox declares it: h2's eth0" in HS._sdn_auto_who(row)


@pytest.mark.parametrize("edit,why", [
    (lambda d: d["source_from"].update(other_macs=["00:00:00:00:00:99"]),
     "another MAC on the port (no address, or claiming the same one)"),
    (lambda d: d["source_from"].update(hosts=[dict(h, mac="") for h in d["source_from"]["hosts"]]),
     "the topology's MAC not known"),
], ids=["other-mac", "no-topology-mac"])
def test_a_port_another_device_shares_or_an_unknown_mac_stays_a_person_s(networks, monkeypatch,  # noqa: F811,E501
                                                                       edit, why):
    """The re-review of 60eff5ea, 1: a rogue MAC behind the declared host's port, or a MAC the
    topology does not know, leaves the declaration unproven."""
    auto_on()
    d = flood()
    _netbox(monkeypatch, d)
    edit(d)
    got = MD.decide(NET, "low", detection=d, action="drop_source")
    assert got["auto"] is False, why


def test_a_second_mac_on_the_port_is_kept_with_the_named_source(networks):  # noqa: F811
    """`port_source` keeps every other MAC the topology lists on a named port, an address or
    none, and only where there is one."""
    from modules.sdn import detect as DT

    alone = flood()
    assert "other_macs" not in alone["source_from"]
    topo = stored(edit=plus({"mac": "00:00:00:00:00:99", "ipv4": [], "ipv6": []}))
    found = DT.port_source(topo, CONN, alone["dpid"], 2)
    assert found["state"] == "named" and found["other_macs"] == ["00:00:00:00:00:99"]


@pytest.mark.parametrize("edit,why", [
    (lambda r: [dict(r[0], ipv4=["192.0.2.9"])], "another address"),
    (lambda r: [dict(r[0], mac="00:00:00:00:00:99")], "another MAC"),
    (lambda r: r + [dict(r[0], name="h9", ipv4=["192.0.2.9"])], "two end hosts on the port"),
    (lambda r: [dict(r[0], port_no=3)], "cabled to another port"),
    (lambda r: [dict(r[0], kind="device")], "a device, not an end host"),
    (lambda r: [dict(r[0], mac="")], "NetBox records no MAC"),
], ids=["address", "mac", "two", "port", "device", "no-netbox-mac"])
def test_a_source_netbox_does_not_declare_stays_a_person_s(networks, monkeypatch, edit, why):  # noqa: F811,E501
    auto_on()
    d = flood()
    base = [{"name": "h2", "kind": "end host", "interface": "eth0", "mac": "00:00:00:00:00:02",
             "ipv4": [H2], "ipv6": [], "switch": "s1", "switch_interface": "eth2",
             "dpid": int(d["dpid"]), "port_no": 2}]
    _netbox(monkeypatch, d, rows=edit(base))
    got = MD.decide(NET, "low", detection=d, action="drop_source")
    assert got == {"auto": False, "autonomous": None, "words": INFERRED.format(addr=H2)}, why


def test_an_unreadable_netbox_view_fails_closed(networks, monkeypatch):  # noqa: F811
    auto_on()
    d = flood()
    _netbox(monkeypatch, d, state="unreadable")
    assert MD.decide(NET, "low", detection=d, action="drop_source")["auto"] is False


@pytest.mark.usefixtures("lab")
def test_an_unattended_confirm_of_a_declared_source_is_applied(lab, monkeypatch):  # noqa: F811
    d, _c, _s = walk_flood("walk-flood-1-s1", stored(name=CONN), small=True)
    d = dict(d, connection="lab-controller", network=NET)
    _netbox(monkeypatch, d)
    preview = CL.respond_to_threat(NET, d, "drop_source")
    assert preview["ok"], preview["error"]
    applied = []
    monkeypatch.setattr("modules.sdn.flow_ops.apply",
                        lambda *a, **k: applied.append(k.get("mode")) or {"outcome": "planted"})
    confirm = {"ask": preview["ask"], "hash": preview["plan"]["hash"]}
    done = CL.respond_to_threat(NET, d, "drop_source", confirm=confirm, actor=LP.AUTO_ACTOR,
                                actor_verified="system", mode="auto",
                                autonomous={"reason": "lab 9 run"})
    assert done == {"outcome": "planted"} and applied == ["auto"]
    # The ask's source moved from the declared one: refused, nothing applied.
    moved = dict(confirm, ask=dict(confirm["ask"], detection=dict(
        confirm["ask"]["detection"], source="192.0.2.9")))
    done = CL.respond_to_threat(NET, d, "drop_source", confirm=moved, actor=LP.AUTO_ACTOR,
                                actor_verified="system", mode="auto",
                                autonomous={"reason": "lab 9 run"})
    assert done["outcome"] == "refused" and applied == ["auto"]
