"""SDN incidents (C1999; `modules/sdn/incidents.py`, `loop.run_pass`): one attack seen on many
switches is one incident, one AI classification, one response proposed at its ingress switch,
one Needs attention row. No network: synthetic detections in the rules' own shape, the
controller's topology as Ryu 4.34 answered it with a Mininet fabric attached
(tests/fixtures/sdn/ryu/topology_rest.json: 192.0.2.1, 2001:db8:8::1 and MAC
00:00:00:00:00:01 on s1's port 1, 192.0.2.3 on s2's port 1, the one link s1:3 to s2:3),
stored as the SDN reader stores it.

- **The row's test**: 50 detections of one scan across 50 switches make one incident, one
  Needs attention row and one proposed response, and one classification call, on the ingress
  switch's detection although it fired last; the other 49 are seen also.
- **Sources in one spelling**: IPv4, IPv6 (compressed or not) and MAC (any case, colons or
  dashes) each group across switches, and the topology finds the ingress by each.
- **Two sources are two incidents**, each proposed at its own ingress.
- **The window**: a detection exactly the rule's window after the incident's last sighting
  joins it (seen also, no call); one a second later is a new incident.
- **AUTO applies once per incident**, at the ingress, the response carrying its incident.
- **Ingress not told**: said why, and the switch that saw it first is proposed.
- **C2005 at incident level**: a response in force at a known ingress holds the source off on
  every switch of its connection, so the 50 detections are already mitigated (no AI call);
  one where the ingress was not told holds its own switch only.
- **Active while any switch shows it**: one seen-also switch resolving keeps the incident
  active; the last one resolving marks it no longer active.
- **Not grouped**: unauthorised flows and a detection naming no source are each their own.
- **The table**: by severity then age, the switches seen also on expand, a filter that says it
  shows a subset.
"""
import pytest

from modules import attention as A
from modules import sdn_ops_page as P
from modules.sdn import closed_loop as CL
from modules.sdn import detect, incidents
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_topology import READ_EPOCH, _cached, _stored_controller

NET = "Default"
CONN = "c1"                          # the captured topology's controller, as stored
T0 = 1_790_000_000.0
WINDOWS = {"sdn_scan_window_seconds": 60, "sdn_flood_window_seconds": 30}
NO_DRIVER = lambda n, c: {"ok": False, "error": "unused"}  # noqa: E731


def det(dpid: int, source: str = "192.0.2.1", rule: str = "scan", at: float = T0,
        conn: str = CONN) -> dict:
    """A detection in `detect._detection`'s shape on switch *dpid*."""
    dh = f"{dpid:016x}"
    subject = ["source", source] if source else ["port", 3]
    return {"rule": rule, "title": detect.TITLES[rule],
            "key": detect.detection_key(rule, NET, conn, dh, subject), "network": NET,
            "connection": conn, "dpid": dpid, "dpid_hex": dh,
            "subject": {"kind": subject[0], "value": subject[1]}, "source": source or None,
            "targets": ["192.0.2.3"], "port": None if source else 3, "confidence": "high",
            "words": f"{source or 'port 3'} reached 25 distinct destination ports on {dh}",
            "at": LP._iso(at)}


def observed(dets: list, resolved=(), still=None):
    """`detect.observe`'s answer: *dets* fired; *still* the detections still firing (default:
    *dets*)."""
    return lambda network, collected: {
        "ok": True, "fired": [d["key"] for d in dets], "resolved": list(resolved),
        "detections": list(dets if still is None else still), "thresholds": dict(WINDOWS),
        "collected_at": dets[0]["at"] if dets else LP._iso(T0)}


def collected():
    return {"network": NET, "summary": {"switches": 50, "flows": 500}, "state": "ok"}


def a_pass(dets, at=T0, **kw):
    return LP.run_pass(NET, collect=collected, observe=observed(dets, **kw),
                       now=lambda: at, driver=NO_DRIVER)


@pytest.fixture
def calls(networks, monkeypatch):  # noqa: F811 - the fixture, used
    """The loop's classify step, counted: each call a classification that passed, proposing
    the rule's catalogue default (as tests/test_sdn_modes_loop.py's AUTO pass plants)."""
    made = []

    def passed(network, d, job, **kw):
        made.append(d)
        action = CL.DEFAULT_ACTION[d["rule"]]
        return {"action": action, "risk": CL.CATALOGUE[action]["risk"], "params": {},
                "classification": {"threat_type": "port_scan", "threat_detected": True,
                                   "severity": "high"},
                "person": False, "why": "", "refused_call": "", "words": "planted: passed"}
    monkeypatch.setattr(LP, "classify", passed)
    return made


@pytest.fixture
def topology(monkeypatch):
    """The SDN reader's stored topology: the captured one, read 30 s before it is used."""
    from modules.sdn import topology as SDN
    real = SDN.stored
    monkeypatch.setattr(SDN, "stored", lambda network, now=None, cached=None: real(
        network, now=READ_EPOCH + 30, cached=_cached([_stored_controller()])))


def _rows():
    return LP.awaiting(NET)["rows"]


# ── the row's test ────────────────────────────────────────────────────────────────────────────

def test_fifty_switches_seeing_one_scan_are_one_incident_row_response_and_call(
        calls, topology, monkeypatch):
    sent = []
    monkeypatch.setattr(CL, "respond_to_threat", lambda *a, **k: sent.append(a) or {})
    # The ingress (s1, where the controller lists 192.0.2.1's host) fires LAST of the 50.
    dets = [det(n) for n in range(50, 0, -1)]
    out = a_pass(dets)
    assert out["ok"], out
    assert [d["dpid"] for d in calls] == [1], "one classification, on the ingress's detection"
    (row,) = _rows()
    assert out["proposed"] == [row["id"]] and sent == [], "one response, awaiting a person"
    assert row["detection"]["dpid_hex"] == "0000000000000001"
    assert row["detection"]["incident"] == {"key": "scan|192.0.2.1", "ingress": True,
                                            "switches": 50}
    inc = row["incident"]
    assert inc["ingress_known"] is True and inc["ingress_port"] == 1
    assert inc["ingress_words"] == (
        "the ingress switch is 0000000000000001: the controller's topology (read "
        "2026-10-27T09:35:49Z) lists 192.0.2.1's host on its port 1")
    assert (inc["window_s"], inc["window_setting"]) == (60, "sdn_scan_window_seconds")
    assert sorted(s["dpid"] for s in row["seen_also"]) == list(range(2, 51))
    assert len(row["members"]) == 50 and len(set(row["members"])) == 50
    assert len(out["seen_also"]) == 49 and out["incidents"] == [
        {"key": "scan|192.0.2.1", "id": row["id"], "joined": False, "switches": 50}]
    (line,) = [x for x in out["lines"] if x["step"] == "incident"]
    assert line["words"].startswith("SDN scan from 192.0.2.1 seen on 50 switches (within 60 s, "
                                    "the scan rule's own window (sdn_scan_window_seconds)): one "
                                    "incident, one AI call, one response; the ingress switch is "
                                    "0000000000000001")
    assert line["words"].endswith("seen also on 49 switches (0000000000000032, "
                                  "0000000000000031, 0000000000000030, 000000000000002f, "
                                  "000000000000002e and 44 more)")
    (r,) = A.sdn_responses_source(found={NET: LP.awaiting(NET)}, now=T0)["rows"]
    assert r["operands"]["switches"] == 50 and r["operands"]["incident"] == row["id"]
    assert r["what"] == "SDN scan from 192.0.2.1 on Default, seen on 50 switches, awaits a person"
    # The same 50 firing again (each still detected) add nothing: no call, no row.
    again = a_pass(dets, at=T0 + 10)
    assert len(calls) == 1 and len(_rows()) == 1 and again["proposed"] == []


@pytest.mark.parametrize("spellings,ingress", [
    (("192.0.2.1", "192.0.2.1"), 1),
    (("2001:db8:8::1", "2001:0DB8:0008:0000:0000:0000:0000:0001"), 1),
    (("00:00:00:00:00:01", "00-00-00-00-00-01"), 1),
    (("192.0.2.3", "192.0.2.3"), 2),
    (("2001:db8:8::3", "2001:db8:8:0:0:0:0:3"), 2),
], ids=["ipv4", "ipv6", "mac", "ipv4-on-s2", "ipv6-on-s2"])
def test_a_source_in_any_spelling_groups_and_finds_its_ingress(calls, topology, spellings,
                                                                ingress):
    one, two = spellings
    out = a_pass([det(2, one), det(1, two)])
    (row,) = _rows()
    assert len(calls) == 1 and calls[0]["dpid"] == ingress and out["ok"]
    assert row["incident"]["ingress_known"] is True
    assert row["incident"]["source"] == LP.canon_source(one) == LP.canon_source(two)
    assert len(row["members"]) == 2


def test_two_sources_are_two_incidents_each_at_its_own_ingress(calls, topology):
    out = a_pass([det(2, "192.0.2.1"), det(1, "192.0.2.3"), det(1, "192.0.2.1"),
                  det(2, "192.0.2.3")])
    rows = _rows()
    assert len(rows) == 2 and len(calls) == 2 and len(out["proposed"]) == 2
    assert {(r["incident"]["source"], r["detection"]["dpid"]) for r in rows} == {
        ("192.0.2.1", 1), ("192.0.2.3", 2)}
    assert len(A.sdn_responses_source(found={NET: LP.awaiting(NET)})["rows"]) == 2


def test_the_window_joins_at_its_end_and_starts_a_new_incident_a_second_later(calls, topology):
    a_pass([det(1)])
    (first,) = _rows()
    joined = a_pass([det(2, at=T0 + 60)], at=T0 + 60)     # exactly the window: joins
    assert len(calls) == 1 and joined["incidents"] == [
        {"key": "scan|192.0.2.1", "id": first["id"], "joined": True, "switches": 1}]
    (line,) = [x for x in joined["lines"] if x["step"] == "incident"]
    assert line["words"] == (
        f"SDN scan from 192.0.2.1 seen also on 1 switch (0000000000000002), within 60 s of its "
        f"last sighting: joins incident {first['id']}, awaiting a person since {first['at']}; "
        "not classified again, nothing proposed")
    (row,) = _rows()
    assert row["members"] == [first["detection"]["key"], det(2)["key"]]
    assert row["last_seen"] == LP._iso(T0 + 60)
    late = a_pass([det(3, at=T0 + 121)], at=T0 + 121)     # 61 s after the last sighting
    assert len(calls) == 2 and len(_rows()) == 2 and late["incidents"][0]["joined"] is False


def test_a_flood_groups_within_its_own_shorter_window(calls, topology):
    a_pass([det(1, rule="flood")])
    a_pass([det(2, rule="flood", at=T0 + 31)], at=T0 + 31)
    assert len(calls) == 2 and len(_rows()) == 2, "31 s is past the flood's 30 s window"
    assert {r["incident"]["window_s"] for r in _rows()} == {30}


def test_auto_applies_once_per_incident_at_its_ingress(calls, topology, monkeypatch):
    MD.set_stage(NET, "lab", actor="admin@example.com", actor_verified="access",
                 reason="the course lab's network")
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="lab 8 run",
               until=T0 + 600, allowed_risk="low", now=T0 - 1)
    seen = []

    def respond(network, d, action, params=None, *, confirm=None, **kw):
        seen.append((d["dpid"], d.get("incident"), confirm is not None))
        if confirm is None:
            return {"ok": True, "ask": {"a": 1}, "plan": {"hash": "h"}}
        return {"id": f"sdnop-{len(seen)}", "outcome": "verified"}
    monkeypatch.setattr(CL, "respond_to_threat", respond)
    monkeypatch.setattr(CL, "log_response", lambda *a, **k: {"step": "respond", "words": "x"})
    out = a_pass([det(n) for n in range(1, 51)] + [det(n, "192.0.2.3") for n in (1, 2)])
    assert len(calls) == 2 and _rows() == []
    assert seen == [
        (1, {"key": "scan|192.0.2.1", "ingress": True, "switches": 50}, False),
        (1, {"key": "scan|192.0.2.1", "ingress": True, "switches": 50}, True),
        (2, {"key": "scan|192.0.2.3", "ingress": True, "switches": 2}, False),
        (2, {"key": "scan|192.0.2.3", "ingress": True, "switches": 2}, True)]
    assert [a["outcome"] for a in out["applied"]] == ["verified", "verified"]


def test_an_ingress_not_told_is_said_and_the_first_to_see_it_is_proposed(calls, monkeypatch,
                                                                        networks):  # noqa: F811
    from modules.sdn import topology as SDN
    monkeypatch.setattr(SDN, "stored", lambda network, **kw: {
        "state": "could not read", "why": "the SDN reader has not read this network yet",
        "controllers": []})
    a_pass([det(9, at=T0), det(7, at=T0 - 20), det(8, at=T0 - 20)], at=T0)
    (row,) = _rows()
    assert row["detection"]["dpid"] == 7, "the earliest; on a tie, the first reported"
    assert row["incident"]["ingress_known"] is False
    assert row["incident"]["ingress_words"] == (
        "the ingress switch cannot be told: the controller's topology could not be read (the "
        "SDN reader has not read this network yet); proposed at 0000000000000007, the switch "
        "that saw it first")
    assert row["detection"]["incident"]["ingress"] is False


def test_a_source_the_topology_places_on_a_switch_that_did_not_fire_is_said(topology):
    inc = incidents.group([det(5, "192.0.2.3"), det(6, "192.0.2.3")], WINDOWS)[0]
    got = incidents.ingress(NET, inc)
    assert (got["known"], got["detection"]["dpid"]) == (False, 5)
    assert got["words"] == (
        "the ingress switch cannot be told: the controller's topology lists 192.0.2.3 on "
        "0000000000000002 port 1, which has not fired; proposed at 0000000000000005, the "
        "switch that saw it first")


def test_a_response_at_a_known_ingress_holds_the_source_off_on_every_switch(calls,
                                                                            monkeypatch):
    hold = {"key": "sdnop-1", "id": "resp-1", "action": "drop_source", "rule": "scan",
            "detection_key": det(1)["key"], "ingress": True, "sources": ["192.0.2.1"],
            "connection": CONN, "dpid": 1, "dpid_hex": "0000000000000001", "cookies": ["c"],
            "until": T0 + 600, "state": "active", "words": "its 1 flow(s) on the switch"}
    d = det(30, "192.0.2.1")
    assert LP.covering(d, [hold], across=True)[0] is hold
    assert LP.covering(d, [hold])[0] is None, "per switch unless asked across"
    assert LP.covering(d, [dict(hold, ingress=False)], across=True)[0] is None
    assert LP.covering(det(30, "192.0.2.9"), [hold], across=True)[0] is None
    assert LP.covering(dict(d, connection="c2"), [hold], across=True)[0] is None
    monkeypatch.setattr(LP, "holds", lambda network, collected, now, **kw: {
        "state": "ok", "error": "", "holds": [hold]})
    out = a_pass([det(n) for n in range(2, 52)])
    assert calls == [] and _rows() == [] and len(out["mitigated"]) == 50
    # The same hold applied where the ingress was not told: two other switches' detections
    # (the 50 holds above release, no longer detected) are answered as one new incident.
    monkeypatch.setattr(LP, "holds", lambda network, collected, now, **kw: {
        "state": "ok", "error": "", "holds": [dict(hold, ingress=False)]})
    out = a_pass([det(n, at=T0 + 5) for n in range(60, 62)], at=T0 + 5)
    assert len(calls) == 1 and out["mitigated"] == [], "an ingress not told holds its own switch"


def test_an_incident_stays_active_while_any_of_its_switches_shows_it(calls, topology):
    one, two = det(1), det(2)
    a_pass([one, two])
    (row,) = _rows()
    out = a_pass([], at=T0 + 10, resolved=[two["key"]], still=[one])
    assert out["inactive"] == [] and _rows()[0]["inactive_since"] == ""
    out = a_pass([], at=T0 + 20, resolved=[one["key"]], still=[])
    assert out["inactive"] == [row["id"]]
    assert _rows()[0]["inactive_since"] == LP._iso(T0)


def test_unauthorised_flows_and_a_detection_naming_no_source_are_each_their_own():
    flows = [det(1, "192.0.2.1", rule="unauthorised_flow"),
             det(2, "192.0.2.1", rule="unauthorised_flow")]
    unsourced = [det(1, ""), det(2, "")]
    assert len(incidents.group(flows + unsourced, WINDOWS)) == 4
    assert incidents.window("unauthorised_flow", WINDOWS)["seconds"] == 0
    assert incidents.joinable([{"incident": {"key": incidents.group_key(unsourced[0]),
                                             "window_s": 60}, "at": LP._iso(T0)}],
                              unsourced[0], T0) is None


# ── the table ────────────────────────────────────────────────────────────────────────────────

def _propose(dpid, source, severity=None, at=T0, also=()):
    d = det(dpid, source, at=at)
    inc = {"key": incidents.group_key(d), "rule": "scan", "source": source, "window_s": 60,
           "window_setting": "sdn_scan_window_seconds", "window_words": "within 60 s",
           "ingress_known": True, "ingress_words": "the ingress switch is s1",
           "ingress_port": 1, "seen_also": [incidents.brief(det(n, source, at=at))
                                             for n in also]}
    return LP.propose(NET, d, "drop_source", "low", why="HITL", now=at, incident=inc,
                      classification={"severity": severity} if severity else None)


def test_the_table_is_by_severity_then_age_and_its_filter_says_it_shows_a_subset(networks):  # noqa: F811,E501
    low = _propose(1, "192.0.2.10", "low", at=T0)
    old = _propose(2, "192.0.2.11", None, at=T0)
    new = _propose(3, "192.0.2.12", None, at=T0 + 60)
    crit = _propose(4, "2001:db8::12", "critical", at=T0 + 120, also=range(5, 55))
    g = P.responses_view(NET)
    assert [r["id"] for r in g["awaiting"]] == [crit["id"], old["id"], new["id"], low["id"]]
    assert g["awaiting"][0]["switches"] == 51 and len(g["awaiting"][0]["seen_also"]) == 50
    assert g["incidents"]["counts"] == [
        {"severity": "critical", "words": "Critical", "tone": "danger", "count": 1},
        {"severity": "unclassified", "words": "Not classified", "tone": "warn", "count": 2},
        {"severity": "low", "words": "Low", "tone": "muted", "count": 1}]
    one = P.responses_view(NET, q="000000000000002a")         # a seen-also switch, dpid 42
    assert [r["id"] for r in one["awaiting"]] == [crit["id"]]
    assert (one["incidents"]["shown"], one["incidents"]["total"]) == (1, 4)
    assert [r["id"] for r in P.responses_view(NET, sev="unclassified")["awaiting"]] == [
        old["id"], new["id"]]
    rows = A.sdn_responses_source(found={NET: LP.awaiting(NET)}, now=T0 + 120)["rows"]
    assert [r["operands"]["incident"] for r in rows] == [crit["id"], old["id"], new["id"],
                                                         low["id"]]
    assert [r["level"] for r in rows] == ["danger", "warning", "warning", "warning"]


# ── a flood seen on a link port (C2106) ──────────────────────────────────────────────────────
#
# The Lab 8 walk's own floods (2026-10-27 23:25:13 UTC, h2 flooding over MAC-only flows): s1's
# port 2 (h2's) and s2's port 3 (the link from s1), each judged again by the flood rule over
# its kept evidence with Ryu 4.34's captured topology (tests/test_sdn_source_from_topology.py's
# `walk_flood` and `stored`, the walk's connection lab-ryu). s2's port 3 carries h2's flows
# (213,796 and 197,485 packets) and one of h1's (398 packets), as the walk kept them.

H1_MAC, H2_MAC = "00:00:00:00:00:01", "00:00:00:00:00:02"
LINK_WORDS = ("port 3 is an inter-switch link, and its flows carry 00:00:00:00:00:02, {src}'s "
              "host (and 00:00:00:00:00:01, with no incident of this rule): the same attack, "
              "seen on its way")


def _walk_floods(edit=None):
    """The walk's two floods (s1 port 2, s2 port 3) on Default, and the stored topology they
    were judged with (*edit* a minimal edit of its hosts, as tests/test_sdn_source_from_topology
    makes them)."""
    from tests.test_sdn_source_from_topology import stored, walk_flood

    topo = stored(edit=edit)
    s1, _c, _s = walk_flood("walk-flood-1-s1", topo)
    s2, _c, _s = walk_flood("walk-flood-1-s2", topo)
    return dict(s1, network=NET), dict(s2, network=NET), topo


def _stored_is(monkeypatch, topo):
    from modules.sdn import topology as SDN
    monkeypatch.setattr(SDN, "stored", lambda network, now=None, cached=None: topo)


def test_the_link_port_s_detection_carries_whose_traffic_its_flows_carry():
    """C2106's naming: s2's port 3 names no source (a link), and keeps the source MACs its
    entering flows match, most packets first, each with the addresses the topology lists for
    its host (the unspecified :: left out); never in the evidence piece the classifier is
    sent."""
    s1, s2, _t = _walk_floods()
    assert s1["source"] == "192.0.2.2" and "link_sources" not in s1
    assert s2["source"] is None and s2["source_from"]["state"] == "link"
    assert s2["link_sources"] == [
        {"mac": H2_MAC, "addresses": ["192.0.2.2", "2001:db8:8::2", "fe80::200:ff:fe00:2"]},
        {"mac": H1_MAC, "addresses": ["192.0.2.1", "2001:db8:8::1", "fe80::200:ff:fe00:1"]}]
    assert incidents.link_keys(s2) >= {"flood|192.0.2.2", "flood|00:00:00:00:00:02",
                                       "flood|2001:db8:8::2"}
    from tests.test_sdn_classify_walk_cases import collection_of, load
    case = next(c for c in load()["cases"] if c["key"] == "walk-flood-1-s2")
    collected, sw = collection_of(case)
    (piece,) = [p for p in detect.section(s2, collected, sw)["pieces"]
                if p["kind"] == "detection"]
    assert "link_sources" not in piece


@pytest.mark.parametrize("order", ["ingress first", "link first"])
def test_the_walks_flood_on_s1_and_s2_is_one_incident_at_h2_s_port(order):
    """C2106: the two floods are one attack: one incident, keyed by h2's address, its ingress
    s1 port 2 (where the topology lists h2), s2's link port seen also saying why."""
    s1, s2, topo = _walk_floods()
    dets = [s1, s2] if order == "ingress first" else [s2, s1]
    (inc,) = incidents.group(dets, WINDOWS)
    assert inc["key"] == "flood|192.0.2.2"
    assert sorted(m["dpid"] for m in inc["members"]) == [1, 2]
    chosen = incidents.ingress(NET, inc, topo)
    assert chosen["known"] is True and chosen["port"] == 2
    assert chosen["detection"]["key"] == s1["key"]
    (also,) = incidents.record(inc, chosen)["seen_also"]
    assert (also["key"], also["dpid_hex"], also["port"]) == (s2["key"], "0000000000000002", 3)
    assert also["words"] == s2["words"] + "; " + LINK_WORDS.format(src="192.0.2.2")


def test_the_walks_flood_by_h2_s_ipv6_address_is_one_incident_too():
    """IPv6: h2 listed with no IPv4 address (the topology's minimal edit, h2_v6_only), so s1's
    flood names 2001:db8:8::2, and s2's link port joins it by that address."""
    from tests.test_sdn_source_from_topology import h2_v6_only

    s1, s2, topo = _walk_floods(edit=h2_v6_only)
    assert s1["source"] == "2001:db8:8::2"
    (inc,) = incidents.group([s2, s1], WINDOWS)
    assert inc["key"] == "flood|2001:db8:8::2"
    chosen = incidents.ingress(NET, inc, topo)
    assert chosen["known"] is True and chosen["detection"]["key"] == s1["key"]
    (also,) = incidents.record(inc, chosen)["seen_also"]
    assert also["words"].endswith("its flows carry 00:00:00:00:00:02, 2001:db8:8::2's host "
                                  "(and 00:00:00:00:00:01, with no incident of this rule): "
                                  "the same attack, seen on its way")


def test_an_ingress_not_told_is_never_proposed_at_the_link_port():
    """C2106: with the ingress not told (the topology not read now), the response is proposed
    at the switch that saw it first among those naming the source, never at the link port's,
    which names none, though s2 saw it a second earlier."""
    s1, s2, _t = _walk_floods()
    s2 = dict(s2, at=LP._iso(detect._epoch(s1["at"]) - 1))
    (inc,) = incidents.group([s2, s1], WINDOWS)
    chosen = incidents.ingress(NET, inc, {"state": "could not read", "why": "planted"})
    assert chosen["known"] is False and chosen["detection"]["key"] == s1["key"]
    assert chosen["words"].endswith("proposed at 0000000000000001, the switch that saw it first")


def test_a_link_port_carrying_two_incidents_sources_stays_its_own():
    """Two floods behind one link (h1's as well, a detection in the rule's shape on s1 port 1):
    the link cannot tell them apart, so s2's port 3 stays its own incident; and with no
    incident of its sources in the pass it stays its own too (as before)."""
    s1, s2, _t = _walk_floods()
    h1 = dict(det(1, "192.0.2.1", rule="flood", at=detect._epoch(s1["at"])), port=1)
    got = incidents.group([s1, h1, s2], WINDOWS)
    assert sorted(i["key"] for i in got) == sorted(
        ["flood|192.0.2.2", "flood|192.0.2.1", f"detection|{s2['key']}"])
    assert [i["key"] for i in incidents.group([s2], WINDOWS)] == [f"detection|{s2['key']}"]


def test_through_the_loop_one_classification_one_row_and_s2_seen_also(calls, monkeypatch):
    """The row's test: the loop's pass over the walk's two floods makes one incident, one
    classification call (on s1's detection, the ingress), one response awaiting a person and
    one Needs attention row; a pass later still within the window, s2's link port alone joins
    it as seen also, with no call."""
    s1, s2, topo = _walk_floods()
    _stored_is(monkeypatch, topo)
    monkeypatch.setattr(CL, "respond_to_threat", lambda *a, **k: {})
    at = detect._epoch(s1["at"])
    out = a_pass([s2, s1], at=at)
    assert out["ok"], out
    assert [d["key"] for d in calls] == [s1["key"]], "one classification, at the ingress"
    (row,) = _rows()
    assert row["incident"]["key"] == "flood|192.0.2.2" and row["incident"]["ingress_port"] == 2
    assert [s["dpid_hex"] for s in row["seen_also"]] == ["0000000000000002"]
    assert row["seen_also"][0]["words"].endswith(LINK_WORDS.format(src="192.0.2.2"))
    rows = A.sdn_responses_source(found={NET: LP.awaiting(NET)}, now=at)["rows"]
    assert len(rows) == 1


def test_a_link_port_firing_a_pass_later_joins_the_incident_awaiting(calls, monkeypatch):
    """`joinable`: s1's flood proposed in one pass; s2's link port firing 10 s later (within the
    flood's 30 s window) joins that incident as seen also: no call, nothing proposed."""
    s1, s2, topo = _walk_floods()
    _stored_is(monkeypatch, topo)
    monkeypatch.setattr(CL, "respond_to_threat", lambda *a, **k: {})
    at = detect._epoch(s1["at"])
    assert a_pass([s1], at=at)["ok"]
    later = dict(s2, at=LP._iso(at + 10))
    out = a_pass([later], at=at + 10)
    assert out["ok"], out
    assert len(calls) == 1 and out["proposed"] == []
    (row,) = _rows()
    assert [s["dpid_hex"] for s in row["seen_also"]] == ["0000000000000002"]
    assert row["seen_also"][0]["words"].endswith(LINK_WORDS.format(src="192.0.2.2"))
    (line,) = [x for x in out["lines"] if x["step"] == "incident"]
    assert line["words"].startswith("SDN flood from 192.0.2.2 seen also on ")
