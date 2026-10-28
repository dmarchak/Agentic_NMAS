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
