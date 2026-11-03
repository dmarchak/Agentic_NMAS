"""An unauthorised flow's effect and the Mercury flow it displaced, decided in code (C2021,
C2004; `flow_intent.effect` and `flow_intent.displaced`, the unauthorised rule and its section
in modules/sdn/detect.py, `closed_loop.sent_evidence`). No provider is called.

**The tables are real captures**, read through the real Ryu driver (`tests.sdn_fakes.ryu_switch`),
each with the one edit its test names, made where it is used:
- the Lab 8 redirect on s2 (tests/fixtures/sdn/lab8/unauthorised_s2.json: cookie 0xbad0 sending
  IPv4 to h3 out h4's port 2, beside the controller's L2 flows, its LLDP flow and its
  table-miss);
- the Lab 8 flood on s1 (flood_s1.json: Mercury's applied rate limit, cookie
  0x4d45d0ee98a11b65, meter 1 then port 3, for 192.0.2.2 to 192.0.2.4, beside the controller's
  L4 and L2 flows);
- S1's capture (tests/fixtures/sdn/ryu/rest_with_peer.json: two Mercury-prefixed flows with no
  record, a /24 drop and a metered flow under it, the controller's IPv4 and IPv6 L4 flows, an ARP
  flow continuing to table 1).
**IPv6 beside IPv4:** each Lab 8 case runs again over its IPv6 twin (192.0.2.N to 2001:db8:8::N,
eth_type 0x86dd, the topology's own pairing); S1's capture holds its own IPv6 flow and
test_sdn_ryu's IPv6 drop.

- **Each class**: diverts (the redirect), drops (the redirect with its output removed; S1's /24
  drop), forwards (a copy of the controller's own L4 flow above it), lifts (Mercury's rate limit
  or drop displaced, or an installed drop taken from above), shadows (Mercury's rate limit
  displaced by one keeping the meter and sending elsewhere), unknown (a table holding only the
  table-miss below it; a flow above taking all its traffic; a flow continuing to another table).
- **A copy is not a diversion while the original is delivered** (C2367, the operator's decision
  of 2026-11-03), from BU2's kept evidence section (tests/fixtures/ai_cases/sdn_classify/
  recorded_from_blind.json, its flow pieces read as the switch's table, the one edit each test
  names): copies_to_controller (BU2 as kept, floor low), mirrors (a host port added beside the
  delivery, high), diverts (the controller only; another port without the delivery), drops,
  forwards; unbound (no host binding) keeps today's diverts and says delivery is not decided;
  only the table-miss below keeps unknown.
- **The displaced flow** is a piece of its own, cited by its own id, sent, and accepted by the
  classifier's check; an expired record is never displaced.
- **The effect** is in the detection's words and fields and in what the classifier is sent, its
  flows cut to those sent.
"""
import json

import pytest

from modules import evidence_pack as EP
from modules.sdn import closed_loop as CL
from modules.sdn import detect as D
from modules.sdn import flow_intent as F
from modules.sdn.drivers.ryu import flow_from_ryu
from tests.sdn_fakes import lab8, ryu_collection, ryu_switch, with_flows
from tests.test_sdn_classify import world  # noqa: F401 - the fixture
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_ryu import DROP, V6_DROP

REDIRECT, FLOOD = "unauthorised_s2.json", "flood_s1.json"
MERCURY_LIMIT = 0x4D45D0EE98A11B65
AT = "2026-10-27T09:26:30Z"
FAMILIES = ("v4", "v6")


def s1_capture():
    with open("tests/fixtures/sdn/ryu/rest_with_peer.json", encoding="utf-8") as fh:
        return json.load(fh)


def v6_twin(flow: dict) -> dict:
    """A Ryu flow's IPv6 twin: each IPv4 address of Mininet's hosts 192.0.2.N made
    2001:db8:8::N, its eth_type 0x86dd; a flow naming no IPv4 address unchanged."""
    m = dict(flow["match"])
    if m.get("dl_type") != 2048:
        return flow
    m["dl_type"] = 0x86DD
    for old, new in (("nw_src", "ipv6_src"), ("nw_dst", "ipv6_dst")):
        if old in m:
            m[new] = "2001:db8:8::" + m.pop(old).rsplit(".", 1)[1]
    return dict(flow, match=m)


def edited(entries, dpid, family, edit=lambda flows: flows):
    """*entries* with switch *dpid*'s table through *edit*, then made its IPv6 twin for v6."""
    def both(flows):
        flows = edit(flows)
        return [v6_twin(f) for f in flows] if family == "v6" else flows
    return with_flows(entries, dpid, both)


def classified(entries, dpid, intent=None, now=None):
    """The switch's table as the unauthorised rule judges it: `classify`'s rows (each with its
    evidence id) and records."""
    sw = ryu_switch(entries, dpid)
    intent = intent or {"state": "ok", "flows": [], "withdrawn": {}}
    return F.classify(sw["flows"], {"name": "lab", "own_cookies": [0]}, intent,
                      read_switches=[dpid], now=now if now is not None else D._epoch(AT))


def effect_of(entries, dpid, cookie, intent=None, now=None):
    """(the unauthorised flow *cookie*'s effect, the Mercury flows it displaced, the table)."""
    got = classified(entries, dpid, intent, now)
    (f,) = [x for x in got["flows"] if x["cookie"] == cookie]
    assert f["owner"] == "unauthorised", f
    moved = [D.displaced_piece("lab", f"{dpid:016x}", r)
             for r in F.displaced(f, got["records"])]
    return F.effect(f, got["flows"], moved), moved, got["flows"]


def id_of(table, cookie=None, **match):
    """The id of the one flow in *table* matching *match*'s fields (and *cookie*, if given)."""
    (f,) = [x for x in table if all(x["match"].get(k) == v for k, v in match.items())
            and cookie in (None, x["cookie"])]
    return f["id"]


def table_miss(table):
    (f,) = [x for x in table if not x["match"]]
    return f["id"]


# ── the classes ───────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("family", FAMILIES)
def test_the_lab_8_redirect_diverts_from_the_controller_s_own_forwarding(family):
    e, moved, table = effect_of(edited(lab8(REDIRECT), 2, family), 2, 0xBAD0)
    to_h3 = id_of(table, in_port=3, eth_dst="00:00:00:00:00:03")
    assert e["class"] == "diverts" and moved == []
    assert to_h3 in e["evidence"] and table_miss(table) in e["evidence"]
    assert e["words"].startswith("diverts the traffic it takes: it sends it out port 2, where")
    assert f"the controller's own flow {to_h3} sends it out port 1" in e["words"]
    assert "which sends it to the controller, so the controller decides it" in e["words"]


#: The controller's topology's hosts on s2's connection as `flow_intent.bindings_of` reads them:
#: h3 at 00:00:00:00:00:03 (its IPv4 and its IPv6 twin), h4 at 00:00:00:00:00:04.
BOUND = {"192.0.2.3": "00:00:00:00:00:03", "2001:db8:8::3": "00:00:00:00:00:03",
         "192.0.2.4": "00:00:00:00:00:04", "2001:db8:8::4": "00:00:00:00:00:04"}


def _redirect_out(actions):
    """The Lab 8 redirect (cookie 0xbad0, IPv4 to h3) with its one edit: *actions*."""
    return lambda flows: [dict(f, actions=actions) if f["cookie"] == 0xBAD0 else f
                          for f in flows]


def _bound_effect(entries):
    got = classified(entries, 2)
    (f,) = [x for x in got["flows"] if x["cookie"] == 0xBAD0]
    return F.effect(f, got["flows"], [], bindings=BOUND), got["flows"]


@pytest.mark.parametrize("family", FAMILIES)
def test_bu1_a_flow_forwarding_to_h3_as_the_controller_does_forwards(family):
    """BU1 (2026-10-29): an engineer's static flow, IPv4 to h3 out h3's own port 1, read
    "diverts" against the controller's L2 flow to h1 (port 3). With h3's MAC bound from the
    topology, only the controller's flow to h3 takes its traffic: it forwards as they do."""
    entries = edited(lab8(REDIRECT), 2, family, _redirect_out(["OUTPUT:1"]))
    e, table = _bound_effect(entries)
    to_h3 = id_of(table, in_port=3, eth_dst="00:00:00:00:00:03")
    to_h1 = id_of(table, in_port=1, eth_dst="00:00:00:00:00:01")
    assert e["class"] == "forwards", e
    assert to_h3 in e["evidence"] and to_h1 not in e["evidence"]
    assert "is at 00:00:00:00:00:03, so its traffic carries that destination MAC" in e["words"]
    unbound, _m, _t = effect_of(entries, 2, 0xBAD0)
    assert unbound["class"] == "diverts", "the premise: without the binding it read diverts"


@pytest.mark.parametrize("family", FAMILIES)
def test_bu2_a_sampling_flow_differs_only_by_its_copy_to_the_controller(family):
    """BU2: the same, plus a copy to the controller: compared with the controller's flow to
    h3 alone, whose one port it keeps, so it copies to the controller (C2367, the operator's
    decision of 2026-11-03: not a diversion while the original is still delivered)."""
    e, table = _bound_effect(edited(lab8(REDIRECT), 2, family,
                                    _redirect_out(["OUTPUT:1", "OUTPUT:CONTROLLER"])))
    to_h3 = id_of(table, in_port=3, eth_dst="00:00:00:00:00:03")
    assert e["class"] == "copies_to_controller", e
    assert e["words"].startswith("copies the traffic it takes to the controller: it sends it "
                                 "out port 1 and the reserved port CONTROLLER, so it still sends "
                                 f"it where without it the controller's own flow {to_h3} sends "
                                 "it out port 1, and adds the reserved port CONTROLLER "
                                 "(control-plane load and visibility)")
    assert "00:00:00:00:00:01" not in e["words"]


# ── C2367: a copy to the controller, a mirror and a diversion, from BU2's kept section ────────

#: The blind round's recorded cases (C2305): BU2's kept evidence section is the capture.
BLIND_CASES = "tests/fixtures/ai_cases/sdn_classify/recorded_from_blind.json"
BU2_FLOW = "flow:lab-ryu:0000000000000002:t0:p10:89d181012c"
BU2_TO_H3 = "flow:lab-ryu:0000000000000002:t0:p1:3605883d95"
BU2_TO_H1 = "flow:lab-ryu:0000000000000002:t0:p1:959d239b24"
BU2_MISS = "flow:lab-ryu:0000000000000002:t0:p0:44136fa355"


def bu2_case() -> dict:
    with open(BLIND_CASES, encoding="utf-8") as fh:
        (case,) = [c for c in json.load(fh)["cases"] if c["name"].startswith("BU2:")]
    return case


def bu2_table(family="v4", actions=None):
    """BU2's switch table as its kept section holds it (s2: cookie 0xb002, IPv4 to h3, OUTPUT:1
    and OUTPUT:CONTROLLER, beside the controller's L2 flows and its table-miss), each flow
    piece with its edits: the cookie and switch read as integers (the pieces carry them as
    hex), and when given, the unauthorised flow's *actions*; for v6, its match made the IPv6
    twin (192.0.2.3 to 2001:db8:8::3, eth_type 0x86dd). Then `classify`'s rows, the
    controller's cookie 0 declared its own as on lab-ryu."""
    flows = []
    for p in bu2_case()["section"]["pieces"]:
        if p["kind"] != "flow":
            continue
        f = dict(p, cookie=int(p["cookie"], 16), dpid=2)
        if p["id"] == BU2_FLOW:
            if actions is not None:
                f["actions"] = actions
            if family == "v6":
                f["match"] = {"eth_type": 0x86DD, "ipv6_dst": "2001:db8:8::3"}
        flows.append(f)
    return F.classify(flows, {"name": "lab-ryu", "own_cookies": [0]},
                      {"state": "ok", "flows": [], "withdrawn": {}}, read_switches=[2],
                      now=D._epoch(AT))["flows"]


def bu2_effect(family="v4", actions=None, bindings=BOUND):
    table = bu2_table(family, actions)
    (f,) = [x for x in table if x["id"] == BU2_FLOW]
    assert f["owner"] == "unauthorised", f
    return F.effect(f, table, [], bindings=bindings)


def out(*ports):
    return [{"type": "OUTPUT", "port": p} for p in ports]


@pytest.mark.parametrize("family", FAMILIES)
def test_bu2_as_kept_copies_to_the_controller_with_its_floor_low(family):
    """BU2's own flows, as its kept section holds them: the controller's flow to h3's MAC sends
    OUTPUT:1 and BU2 sends OUTPUT:1 and OUTPUT:CONTROLLER, so the original is still delivered and
    the one thing added is a copy to the controller: low to medium, its floor low."""
    case = bu2_case()
    assert case["detection"]["effect"]["class"] == "diverts", "the premise: kept as diverts"
    assert case["expect"]["severity"] == ["low"], "the premise: the key's low"
    e = bu2_effect(family)
    assert e["class"] == "copies_to_controller", e
    assert e["evidence"] == [BU2_TO_H3, BU2_MISS]
    assert e["words"].startswith(
        "copies the traffic it takes to the controller: it sends it out port 1 and the reserved "
        f"port CONTROLLER, so it still sends it where without it the controller's own flow "
        f"{BU2_TO_H3} sends it out port 1, and adds the reserved port CONTROLLER (control-plane "
        f"load and visibility); the rest of its traffic would reach {BU2_MISS}, which sends it "
        "to the controller, so the controller decides it")
    floor = CL.severity_floor({"effect": e})
    assert floor == {"severity": "low",
                     "words": "at least low: the flow copies its traffic to the controller (its "
                              "effect, decided in code from the switch's table)"}
    low = {"threat_detected": True, "severity": "low"}
    assert CL.apply_floor(low, {"effect": e}) == low, "the key's low is not raised"
    assert CL.apply_floor(dict(low, severity="none"), {"effect": e})["severity"] == "low"


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("name,actions,cls,floor", [
    ("to the controller only", out("CONTROLLER"), "diverts", "high"),
    ("a copy out h4's port beside the delivery", out(1, 2), "mirrors", "high"),
    ("a copy out h4's port and to the controller", out(1, 2, "CONTROLLER"), "mirrors", "high"),
    ("redirected out h4's port, copied to the controller", out(2, "CONTROLLER"), "diverts",
     "high"),
    ("redirected out h4's port", out(2), "diverts", "high"),
    ("dropped", [], "drops", "high"),
    ("as the controller", out(1), "forwards", None)])
def test_bu2_s_flow_edited_reads_each_class_with_its_floor(family, name, actions, cls, floor):
    """BU2's flow with its actions edited: only a flow that keeps the controller's delivery and
    adds CONTROLLER alone copies to the controller; a host port added beside it mirrors (high,
    confidentiality); the controller only, or another port without the delivery, diverts; no
    output drops (high, as diverts)."""
    e = bu2_effect(family, actions)
    assert e["class"] == cls, (name, e)
    assert CL.severity_floor({"effect": e}).get("severity") == floor, name
    assert BU2_TO_H3 in e["evidence"] and BU2_TO_H1 not in e["evidence"], name


@pytest.mark.parametrize("family", FAMILIES)
def test_bu2_s_mirror_says_its_copy_port(family):
    e = bu2_effect(family, out(1, 2))
    assert e["words"].startswith(
        "mirrors the traffic it takes: it sends it out port 1 and port 2, so it still sends it "
        f"where without it the controller's own flow {BU2_TO_H3} sends it out port 1, and adds "
        "a copy out port 2 (confidentiality: the copy leaves where the controller would not "
        "send it)")


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("bindings", [None, {"192.0.2.99": "00:00:00:00:00:99"}])
def test_bu2_unbound_keeps_today_s_diverts_and_says_delivery_is_not_decided(family, bindings):
    """Without h3's MAC bound, BU2 is compared with the controller's flows to h1 and h4 too
    (C2245's case): whether its traffic is only what the flow to h3 would take is not decided,
    so it reads diverts as before, never guessed a copy, and its words say so."""
    e = bu2_effect(family, bindings=bindings)
    addr = "2001:db8:8::3" if family == "v6" else "192.0.2.3"
    assert e["class"] == "diverts", e
    assert e["words"].startswith(
        "diverts the traffic it takes: it sends it out port 1 and the reserved port CONTROLLER, "
        f"where without it the controller's own flow {BU2_TO_H1} sends it out port 3; ")
    assert (f"; it keeps the output of {BU2_TO_H3}, so the part of its traffic that flow would "
            "take is still delivered, with a copy out the reserved port CONTROLLER; whether its "
            f"traffic is that part alone is not decided ({addr} is not a host the controller's "
            "topology lists, so its destination MAC is not known)") in e["words"]
    assert BU2_TO_H3 in e["evidence"] and BU2_TO_H1 in e["evidence"]
    assert CL.severity_floor({"effect": e})["severity"] == "high"


@pytest.mark.parametrize("family", FAMILIES)
def test_bu2_changing_the_packet_it_delivers_keeps_today_s_diverts(family):
    """BU2's flow rewriting the destination MAC before its outputs (S1's captured SET_FIELD):
    the packet delivered is not the one the controller's flow delivers, so it is not called a
    copy: diverts, as before."""
    rewrite = [{"type": "SET_FIELD", "field": "eth_dst", "value": "00:00:00:00:00:04"}]
    e = bu2_effect(family, rewrite + out(1, "CONTROLLER"))
    assert e["class"] == "diverts", e
    assert "it keeps the output of" not in e["words"]


def test_bu2_with_only_the_table_miss_below_keeps_today_s_unknown():
    """BU2's table with the controller's L2 flows gone: no controller flow says where its
    traffic would go, so whether it is delivered is not decided: unknown, as before."""
    table = [f for f in bu2_table() if f["priority"] != 1]
    (f,) = [x for x in table if x["id"] == BU2_FLOW]
    e = F.effect(f, table, [], bindings=BOUND)
    assert e["class"] == "unknown" and e["evidence"] == [BU2_MISS]
    assert CL.severity_floor({"effect": e}) == {}


@pytest.mark.parametrize("family", FAMILIES)
def test_the_redirect_bound_is_compared_with_the_flow_to_h3_alone(family):
    e, table = _bound_effect(edited(lab8(REDIRECT), 2, family))
    to_h1 = id_of(table, in_port=1, eth_dst="00:00:00:00:00:01")
    assert e["class"] == "diverts" and to_h1 not in e["evidence"]


@pytest.mark.parametrize("family", FAMILIES)
def test_the_rule_binds_from_the_controller_s_topology(family):
    """The unauthorised rule hands the stored topology's hosts on the switch's connection to
    the effect (`detect.unauthorised`'s *topo*, `flow_intent.bindings_of`)."""
    sw = ryu_switch(edited(lab8(REDIRECT), 2, family, _redirect_out(["OUTPUT:1"])), 2)
    collected = ryu_collection("Default", AT, [sw])
    topo = {"controllers": [{"name": "lab", "hosts": [
        {"mac": "00:00:00:00:00:03", "ipv4": ["192.0.2.3"], "ipv6": ["2001:db8:8::3"]}]}]}
    (d,) = D.unauthorised(collected, {"state": "ok", "flows": [], "withdrawn": {}},
                          now=D._epoch(AT), topo=topo)["detections"]
    assert d["effect"]["class"] == "forwards", d["effect"]
    (d0,) = D.unauthorised(collected, {"state": "ok", "flows": [], "withdrawn": {}},
                           now=D._epoch(AT))["detections"]
    assert d0["effect"]["class"] == "diverts", "without the topology nothing is bound"


@pytest.mark.usefixtures("networks")
def test_observe_binds_from_the_stored_topology(monkeypatch):
    """`observe` hands the unauthorised rule the stored topology it reads for the others."""
    from modules.sdn import topology as SDN
    sw = ryu_switch(edited(lab8(REDIRECT), 2, "v4", _redirect_out(["OUTPUT:1"])), 2)
    collected = ryu_collection("Default", AT, [sw])
    monkeypatch.setattr(SDN, "stored", lambda network, *a, **kw: {"controllers": [
        {"name": "lab", "hosts": [{"mac": "00:00:00:00:00:03", "ipv4": ["192.0.2.3"]}]}]})
    got = D.observe("Default", collected, values=dict(D.THRESHOLDS),
                    intent={"state": "ok", "flows": [], "withdrawn": {}, "error": ""})
    assert got["ok"], got.get("error")
    (d,) = [x for x in got["detections"] if x["rule"] == "unauthorised_flow"]
    assert d["effect"]["class"] == "forwards", d["effect"]


def test_a_destination_the_topology_does_not_list_is_compared_as_before():
    entries = edited(lab8(REDIRECT), 2, "v4", _redirect_out(["OUTPUT:1"]))
    got = classified(entries, 2)
    (f,) = [x for x in got["flows"] if x["cookie"] == 0xBAD0]
    e = F.effect(f, got["flows"], [], bindings={"192.0.2.99": "00:00:00:00:00:99"})
    assert e["class"] == "diverts" and "is at" not in e["words"]


@pytest.mark.parametrize("family", FAMILIES)
def test_the_redirect_with_its_output_removed_drops(family):
    """Held-out case 7's edit: the unauthorised flow's one action removed."""
    entries = edited(lab8(REDIRECT), 2, family, lambda flows: [
        dict(f, actions=[]) if f["cookie"] == 0xBAD0 else f for f in flows])
    e, _moved, table = effect_of(entries, 2, 0xBAD0)
    assert e["class"] == "drops"
    assert e["words"].startswith("drops the traffic it takes, where without it")
    assert id_of(table, in_port=3, eth_dst="00:00:00:00:00:03") in e["evidence"]


def _flood_without_mercury(flows):
    """The flood's table as it stood before Mercury's response (test_sdn_lab8's edit)."""
    return [f for f in flows if f["cookie"] != MERCURY_LIMIT]


def _copy_of_l4(port):
    """The controller's own L4 flow for the flood (h2 to h4, UDP 5001), copied above it with
    cookie 0xbad0, sending out *port*."""
    def edit(flows):
        flows = _flood_without_mercury(flows)
        l4 = next(f for f in flows if f["match"].get("tp_dst") == 5001)
        return flows + [dict(l4, cookie=0xBAD0, priority=10, actions=[f"OUTPUT:{port}"])]
    return edit


@pytest.mark.parametrize("family", FAMILIES)
def test_a_copy_of_the_controller_s_own_flow_forwards_as_the_controller_would(family):
    e, _moved, table = effect_of(edited(lab8(FLOOD), 1, family, _copy_of_l4(3)), 1, 0xBAD0)
    l4 = id_of(table, cookie=0, udp_dst=5001)
    assert e["class"] == "forwards" and e["evidence"] == [l4]
    assert e["words"] == (f"forwards as the controller would: it sends it out port 3, as "
                          f"without it the controller's own flow {l4} sends it out port 3")


@pytest.mark.parametrize("family", FAMILIES)
def test_the_same_copy_changing_the_packet_cannot_tell(family):
    """The copy sends where the controller's flow does but rewrites the destination MAC first
    (S1's captured SET_FIELD, in Ryu's shape): what the rewrite does is not judged."""
    def edit(flows):
        flows = _copy_of_l4(3)(flows)
        flows[-1] = dict(flows[-1], actions=["SET_FIELD: {eth_dst:00:00:00:00:00:03}",
                                             "OUTPUT:3"])
        return flows
    e, _moved, table = effect_of(edited(lab8(FLOOD), 1, family, edit), 1, 0xBAD0)
    assert e["class"] == "unknown" and e["evidence"] == [id_of(table, cookie=0, udp_dst=5001)]
    assert "but changes the packet otherwise (SET_FIELD:eth_dst=00:00:00:00:00:03, OUTPUT:3)" \
        in e["words"]


@pytest.mark.parametrize("family", FAMILIES)
def test_the_same_copy_sending_elsewhere_diverts(family):
    e, _moved, table = effect_of(edited(lab8(FLOOD), 1, family, _copy_of_l4(2)), 1, 0xBAD0)
    assert e["class"] == "diverts" and e["evidence"] == [id_of(table, cookie=0, udp_dst=5001)]


def _mercury_limit(entries, family):
    """Mercury's applied rate limit as the flood's capture holds it (its IPv6 twin for v6)."""
    body = next(e for e in entries if e["path"] == "/stats/flow/1")["body"]
    (raw,) = [f for f in json.loads(body)["1"] if f["cookie"] == MERCURY_LIMIT]
    return flow_from_ryu(1, v6_twin(raw) if family == "v6" else raw).as_dict()


def _record(flow, at, action):
    F.record_installed("Default", connection="lab", flow=flow, actor="op@example.com",
                       response={"kind": "response", "action": action, "risk": "low",
                                 "operation": "op-1"}, at=at)


def _displace_limit(actions):
    """The walk's injection (C2004: cookie 0xbad1 put where Mercury's rate limit was): Mercury's
    flow replaced at its place, the same table, priority and match, by cookie 0xbad1."""
    return lambda flows: [dict(f, cookie=0xBAD1, actions=actions)
                          if f["cookie"] == MERCURY_LIMIT else f for f in flows]


@pytest.mark.usefixtures("networks")
@pytest.mark.parametrize("family", FAMILIES)
def test_mercury_s_rate_limit_displaced_without_its_meter_is_lifted(family):
    _record(_mercury_limit(lab8(FLOOD), family), D._epoch(AT) - 30, "rate_limit_source")
    entries = edited(lab8(FLOOD), 1, family, _displace_limit(["OUTPUT:3"]))
    e, moved, _table = effect_of(entries, 1, 0xBAD1, F.intent("Default"))
    (piece,) = moved
    assert piece["id"] == f"intent:lab:0000000000000001:{F.cookie_hex(MERCURY_LIMIT)}"
    assert piece["actions_words"] == "METER:1, OUTPUT:3" and piece["state"] == "missing"
    assert piece["response"] == {"kind": "response", "action": "rate_limit_source",
                                 "risk": "low", "operation": "op-1"}
    assert e["class"] == "lifts" and e["evidence"] == [piece["id"]]
    assert e["words"] == (
        f"lifts Mercury's flow {piece['id']} (cookie {F.cookie_hex(MERCURY_LIMIT)}, METER:1, "
        "OUTPUT:3, installed by a rate_limit_source response): it took that flow's place (the "
        "same table, priority and match) and sends it out port 3, so Mercury's meter 1 is "
        "undone")


@pytest.mark.usefixtures("networks")
@pytest.mark.parametrize("family", FAMILIES)
def test_displaced_keeping_the_meter_but_sending_elsewhere_shadows(family):
    _record(_mercury_limit(lab8(FLOOD), family), D._epoch(AT) - 30, "rate_limit_source")
    entries = edited(lab8(FLOOD), 1, family, _displace_limit(["METER:1", "OUTPUT:2"]))
    e, (piece,), _table = effect_of(entries, 1, 0xBAD1, F.intent("Default"))
    assert e["class"] == "shadows" and e["evidence"] == [piece["id"]]
    assert "does METER:1, OUTPUT:2 where Mercury's does METER:1, OUTPUT:3" in e["words"]


@pytest.mark.usefixtures("networks")
def test_an_expired_record_is_never_displaced():
    """Mercury's rate limit past its hard timeout (120 s) was removed as asked: the flow at its
    place displaced nothing, and is judged against the table alone."""
    _record(_mercury_limit(lab8(FLOOD), "v4"), D._epoch(AT) - 200, "rate_limit_source")
    entries = edited(lab8(FLOOD), 1, "v4", _displace_limit(["OUTPUT:3"]))
    e, moved, _table = effect_of(entries, 1, 0xBAD1, F.intent("Default"))
    assert moved == [] and e["class"] not in ("lifts", "shadows")


@pytest.mark.usefixtures("networks")
@pytest.mark.parametrize("spec,cookie,port", [(DROP, 0x4D45524300000001, 2),
                                              (V6_DROP, None, 3)])
def test_mercury_s_drop_displaced_by_an_output_is_lifted(spec, cookie, port):
    """S1's capture: test_sdn_ryu's IPv4 /24 drop (the capture's own cookie ...0001) or its IPv6
    drop recorded as Mercury's, and a flow with cookie 0xbad1 at its place sending out a port."""
    _record(dict(spec, dpid=1), D._epoch(AT) - 30, "drop_source")
    m = {"dl_type": spec["match"]["eth_type"]}
    m.update({("nw_src" if k == "ipv4_src" else k): v for k, v in spec["match"].items()
              if k != "eth_type"})
    bad = {"priority": spec["priority"], "cookie": 0xBAD1, "idle_timeout": 0,
           "hard_timeout": 0, "byte_count": 0, "duration_sec": 1, "packet_count": 0,
           "length": 96, "flags": 0, "actions": [f"OUTPUT:{port}"], "match": m, "table_id": 0}
    entries = with_flows(s1_capture(), 1, lambda flows: [
        f for f in flows if f["cookie"] != cookie] + [bad])
    e, (piece,), _table = effect_of(entries, 1, 0xBAD1, F.intent("Default"))
    assert e["class"] == "lifts" and e["evidence"] == [piece["id"]]
    assert e["words"].endswith(f"sends it out port {port}, so Mercury's drop is undone")


@pytest.mark.usefixtures("networks")
def test_an_installed_mercury_drop_taken_from_above_is_lifted_for_that_traffic():
    """S1's capture with its /24 drop recorded as Mercury's (it is then Mercury's flow), and an
    unauthorised flow above it sending one host of the /24 out port 2."""
    _record(dict(DROP, dpid=1), D._epoch(AT) - 30, "drop_source")
    above = {"priority": 200, "cookie": 0xBAD1, "idle_timeout": 0, "hard_timeout": 0,
             "byte_count": 0, "duration_sec": 1, "packet_count": 0, "length": 96, "flags": 0,
             "actions": ["OUTPUT:2"], "match": {"dl_type": 2048, "nw_src": "192.0.2.3"},
             "table_id": 0}
    entries = with_flows(s1_capture(), 1, lambda flows: flows + [above])
    e, moved, table = effect_of(entries, 1, 0xBAD1, F.intent("Default"))
    mine = id_of(table, ipv4_src="192.0.2.0/255.255.255.0")
    assert moved == [] and e["class"] == "lifts" and e["evidence"] == [mine]
    assert "above it, it takes part of that flow's traffic and sends it out port 2" in e["words"]


@pytest.mark.usefixtures("networks")
def test_an_installed_ipv6_drop_taken_whole_from_above_is_lifted():
    """test_sdn_ryu's IPv6 drop recorded and installed (added to S1's table as Mercury sent it),
    and an unauthorised flow above it matching all of its source's IPv6 traffic."""
    _record(dict(V6_DROP, dpid=1), D._epoch(AT) - 30, "drop_source")
    m = {"dl_type": 0x86DD, "ipv6_src": "2001:db8::1", "nw_proto": 6, "tp_dst": 22}

    def flow(cookie, priority, match, actions):
        return {"priority": priority, "cookie": cookie, "idle_timeout": 0, "hard_timeout": 300,
                "byte_count": 0, "duration_sec": 1, "packet_count": 0, "length": 96,
                "flags": 0, "actions": actions, "match": match, "table_id": 0}
    entries = with_flows(s1_capture(), 1, lambda flows: flows + [
        flow(V6_DROP["cookie"], 100, m, []),
        flow(0xBAD1, 200, {"dl_type": 0x86DD, "ipv6_src": "2001:db8::1"}, ["OUTPUT:3"])])
    e, moved, _table = effect_of(entries, 1, 0xBAD1, F.intent("Default"))
    assert moved == [] and e["class"] == "lifts"
    assert "above it, it takes all of that flow's traffic and sends it out port 3" in e["words"]


@pytest.mark.parametrize("family", FAMILIES)
def test_a_table_holding_only_the_table_miss_below_it_cannot_tell(family):
    """The redirect's table with the controller's L2 flows gone (they had expired): below the
    unauthorised flow only the table-miss, which asks the controller."""
    entries = edited(lab8(REDIRECT), 2, family, lambda flows: [
        f for f in flows if f["priority"] != 1])
    e, _moved, table = effect_of(entries, 2, 0xBAD0)
    assert e["class"] == "unknown" and e["evidence"] == [table_miss(table)]
    assert e["words"] == (
        f"has an effect the table cannot tell: below it only {table_miss(table)} would take "
        "its traffic, which sends it to the controller, so where the controller would send "
        "it is not in the table")


def test_a_flow_another_takes_all_the_traffic_of_first_cannot_tell():
    """S1's capture as captured: its metered flow (cookie ...0002, priority 90) sits under its
    /24 drop (...0001, priority 100), which matches all of its traffic first."""
    e, _moved, table = effect_of(s1_capture(), 1, 0x4D45524300000002)
    drop = id_of(table, ipv4_src="192.0.2.0/255.255.255.0")
    assert e["class"] == "unknown" and e["evidence"] == [drop]
    assert f"it takes no traffic while {drop} (another unauthorised flow, priority 100)" \
        in e["words"]


def test_s1_s_drop_drops_and_its_prerequisite_keeps_ipv6_and_arp_out():
    """S1's /24 drop drops what the controller's IPv4 flows forward; and with its eth_type
    removed (a match leaving the prerequisite implied), it still overlaps no IPv6 or ARP flow."""
    for edit in (lambda m: m, lambda m: {k: v for k, v in m.items() if k != "dl_type"}):
        entries = with_flows(s1_capture(), 1, lambda flows: [
            dict(f, match=edit(f["match"])) if f["cookie"] == 0x4D45524300000001 else f
            for f in flows])
        e, _moved, table = effect_of(entries, 1, 0x4D45524300000001)
        assert e["class"] == "drops"
        assert id_of(table, tcp_dst=22) in e["evidence"]
        assert id_of(table, tcp_dst=443) not in e["evidence"]
        assert id_of(table, eth_type=2054) not in e["evidence"]


def test_a_flow_continuing_to_another_table_cannot_tell():
    """S1's ARP flow (WRITE_ACTIONS then GOTO_TABLE:1) copied above it with cookie 0xbad0."""
    entries = with_flows(s1_capture(), 1, lambda flows: flows + [
        dict(next(f for f in flows if f["match"].get("dl_type") == 2054), cookie=0xBAD0,
             priority=6)])
    e, _moved, _table = effect_of(entries, 1, 0xBAD0)
    assert e["class"] == "unknown"
    assert e["words"] == ("has an effect the table cannot tell: it continues to table 1, and "
                          "what happens there is not judged")


# ── the detection, its section and what the classifier is sent ────────────────────────────────

def _lifted_detection(family):
    _record(_mercury_limit(lab8(FLOOD), family), D._epoch(AT) - 30, "rate_limit_source")
    sw = ryu_switch(edited(lab8(FLOOD), 1, family, _displace_limit(["OUTPUT:3"])), 1)
    collected = ryu_collection("Default", AT, [sw])
    (d,) = D.unauthorised(collected, F.intent("Default"), now=D._epoch(AT))["detections"]
    return d, D.section(d, collected, sw)


@pytest.mark.usefixtures("networks")
@pytest.mark.parametrize("family", FAMILIES)
def test_the_displaced_flow_is_evidence_of_its_own_and_the_effect_is_in_the_detection(family):
    d, sec = _lifted_detection(family)
    (piece,) = d["displaced"]
    assert d["evidence"] == [d["subject"]["value"], piece["id"]]
    assert d["effect"]["class"] == "lifts" and f"; it {d['effect']['words']}" in d["words"]
    kinds = [p["kind"] for p in sec["pieces"]]
    assert kinds == ["detection", "flow", "displaced_flow", "coverage"], kinds
    assert sec["counts"]["displaced_flows"] == 1
    det = sec["pieces"][0]
    assert det["effect"] == d["effect"] and det["evidence"] == d["evidence"]
    sent = CL.sent_evidence(sec)
    assert piece["id"] in sent["ids"] and sent["detection"]["effect"]["class"] == "lifts"
    assert sent["detection"]["evidence"] == d["evidence"]
    assert any(p["kind"] == "displaced_flow" and p["id"] == piece["id"]
               for p in sent["pieces"])


@pytest.mark.parametrize("family", FAMILIES)
def test_the_effect_s_flows_are_sent_and_cut_to_what_is_sent(family):
    """The redirect's effect names the controller's flows: each is a flow piece in the section
    after the detection's own; a flow the section did not keep is cut from the effect as sent."""
    sw = ryu_switch(edited(lab8(REDIRECT), 2, family), 2)
    collected = ryu_collection("Default", AT, [sw])
    (d,) = D.unauthorised(collected, {"state": "ok", "flows": [], "withdrawn": {}},
                          now=D._epoch(AT))["detections"]
    sec = D.section(d, collected, sw)
    flows = [p["id"] for p in sec["pieces"] if p["kind"] == "flow"]
    assert flows == [d["subject"]["value"]] + d["effect"]["evidence"]
    assert sec["total"] == len(flows) and not sec["subset"]
    gone = d["effect"]["evidence"][-1]
    sec["pieces"] = [p for p in sec["pieces"] if p.get("id") != gone]
    sent = CL.sent_evidence(sec)
    assert sent["detection"]["effect"]["evidence"] == d["effect"]["evidence"][:-1]
    assert gone not in sent["ids"]


@pytest.mark.usefixtures("networks")
@pytest.mark.parametrize("family", FAMILIES)
def test_an_answer_citing_the_displaced_flow_passes_the_check_and_both_are_sent(world, family):
    from tests.test_sdn_classify import answer
    from modules.ai import triggers

    d, sec = _lifted_detection(family)
    (piece,) = d["displaced"]
    world.answer = answer(threat_type="unauthorised_flow", severity="high",
                          affected_devices=["0000000000000001"], action_id="remove_flow",
                          parameters={"source": "", "flow": d["subject"]["value"],
                                      "hard_timeout": 0, "rate": 0, "unit": "kbps",
                                      "burst": 0},
                          evidence_refs=[piece["id"]])
    actor = "evaluation:sdn-effect-test"
    pack = {"id": "case-effect", "network": "Default", "store": "sdn",
            "sections": [dict(sec, name=EP.SDN_SECTION)]}
    got = CL.classify_pack("Default", d, pack, actor=actor, trigger=triggers.evaluation(actor),
                           send=world.send, intact=False)
    assert got["ok"], got
    assert got["action"] == "remove_flow"
    (body,) = world.sent
    text = json.dumps(body)
    assert piece["id"] in text and "lifts Mercury" in text and "displaced_flow" in text
