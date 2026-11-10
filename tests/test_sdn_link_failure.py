"""Link failure on an SDN fabric (Lab 9 B3; board F; `modules/sdn/link_failure.py`): the
link-down rule, and its response, which verifies the reroute.

**The rule** runs on the lab's REAL controller answers (tests/fixtures/lab9_captures/2026-11-06/
ryu-rest.txt: Ryu 4.34's links and each switch's port descriptions, read by Mercury's real Ryu
driver through `closed_loop.collect_threat_data(links=True)`). The capture's ten link entries
are five links, every end up (OVS and the ProCurve set LIVE, the Aristas report 0, C2602). Each
later collection is the capture with one minimal edit, made where it is used: the link between
the two Open vSwitch hosts (DPIDs 3 and 4, each eno3, port 2) taken out of the controller's
links, and port 2 of DPID 3 given the state and speed the SAME capture shows for that host's
own down port, eno4 (state 1, LINK_DOWN; current speed 0).
- a link the topology held whose end reports LINK_DOWN fires at once, confidence high, as one
  detection naming both ends (never one per side), its alert and evidence pack kept;
- a link the controller stops listing while both ports report up fires only after
  `GONE_READS` collections, confidence lower;
- the affected hosts are named by address, IPv4 and IPv6 alike;
- a switch whose port descriptions could not be read leaves its links unjudged (a firing one
  keeps firing), and a link listed and up again resolves; links that could not be read judge
  nothing, said; a collection that did not ask for link status judges nothing.

**The verify** runs on the Lab 8 controller's REAL tables and topology (tests/test_sdn_trace.py's
captures: s1 and s2 joined by port 3), the failed link s1:3 to s2:3, each case a minimal edit:
- **not rerouted:** the link gone from the topology and the tables unchanged (still out port
  3): the pair is not delivered, said with where it ended; nothing is sent;
- **rerouted:** a second link (port 4 on each) and the four host flows moved to it, as a
  forwarding app rewrites its next hops: every pair is delivered avoiding the failed link, IPv4
  and IPv6 alike;
- **pending:** a stored read from before the failure, or one still listing the link, is never
  judged.

**The modes:** in HITL the loop keeps a card awaiting a person and verifies nothing; in AUTO
(on a network marked lab) it verifies at each pass until rerouted, records each outcome as
Mercury's, and after `VERIFY_WINDOW_S` leaves a reroute it never saw to a person; a link
listed and up again closes its card; no AI call is made for a link down.
"""
import copy

import pytest

from modules.sdn import closed_loop as CL
from modules.sdn import detect as D
from modules.sdn import link_failure as LF
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from tests.fixtures.sdn.ryu_recorded import RecordedRyu
from tests.sdn_fakes import with_flows
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_trace import NOW, READ_AT, S1, S2, cached, without_bad0

NET = "Default"
CONN = "lab9-ryu"
OVS3, OVS4 = "0000000000000003", "0000000000000004"
LINK = f"{OVS3}:2-{OVS4}:2"


# ───────────────────────────────────────────────────────────────────────────── the rule

def _collect(monkeypatch, edit=None, at=1_790_000_000.0, links=True):
    """`collect_threat_data` over the recorded controller, *edit* applied to its answers."""
    rec = RecordedRyu()
    if edit:
        edit(rec._answers)
    monkeypatch.setattr(CL, "_connections", lambda network: {
        "state": "ok", "error": "", "connections": [{"name": CONN, "kind": "ryu"}]})
    return CL.collect_threat_data(NET, 1.0, sleep=lambda s: None, now=lambda: at,
                                  driver=lambda n, c: {"ok": True, "driver": rec.driver()},
                                  links=links)


def _down(answers):
    """The OVS-to-OVS link out of the controller's links, and port 2 of DPID 3 given the state
    and speed the capture shows for that host's own down port, eno4."""
    answers["/v1.0/topology/links"] = [
        l for l in answers["/v1.0/topology/links"]
        if {(l["src"]["dpid"], l["src"]["port_no"]), (l["dst"]["dpid"], l["dst"]["port_no"])}
        != {(OVS3, "00000002"), (OVS4, "00000002")}]
    ports = answers["/stats/portdesc/3"]["3"]
    (eno4,) = [p for p in ports if p["name"] == "eno4"]
    assert eno4["state"] == 1, "the capture's own down port"
    for p in ports:
        if p["port_no"] == 2:
            p.update(state=eno4["state"], curr_speed=eno4["curr_speed"])


def _gone(answers):
    """The OVS-to-OVS link out of the controller's links, both its ports left as captured."""
    _down(answers)
    for p in answers["/stats/portdesc/3"]["3"]:
        if p["port_no"] == 2:
            p.update(state=4, curr_speed=1000000)


def test_the_capture_holds_five_links_every_end_up(monkeypatch):
    got = LF.rule(_collect(monkeypatch), {})
    assert got["detections"] == [] and len(got["held"][CONN]) == 5
    assert LINK in got["held"][CONN] and len(got["judged"]) == 5


def test_a_held_link_whose_end_reports_link_down_fires_once_naming_both_ends(monkeypatch):
    first = LF.rule(_collect(monkeypatch), {})
    got = LF.rule(_collect(monkeypatch, _down, at=1_790_000_010.0), first["held"])
    (d,) = got["detections"]
    assert d["rule"] == "link_down" and d["subject"] == {"kind": "link", "value": LINK}
    assert d["confidence"] == "high" and d["dpid_hex"] == OVS3 and d["port"] == 2
    assert [(e["dpid_hex"], e["port_no"], e["state"]) for e in d["link"]["ends"]] == [
        (OVS3, 2, "link_down"), (OVS4, 2, "up")]
    assert d["words"] == (
        f"link {OVS3} port 2 (eno3) to {OVS4} port 2 (eno3) ({CONN}) is down: {OVS3} port 2 "
        "(eno3) reports its link down (LINK_DOWN); the controller no longer lists the link "
        "(1 read)")
    assert d["evidence"] == [f"port:{CONN}:{OVS3}:2", f"port:{CONN}:{OVS4}:2"]


def test_a_link_gone_while_its_ports_report_up_fires_only_after_two_reads(monkeypatch):
    held = LF.rule(_collect(monkeypatch), {})["held"]
    once = LF.rule(_collect(monkeypatch, _gone, at=1_790_000_010.0), held)
    assert once["detections"] == [] and once["held"][CONN][LINK]["gone"] == 1
    twice = LF.rule(_collect(monkeypatch, _gone, at=1_790_000_020.0), once["held"])
    (d,) = twice["detections"]
    assert d["confidence"] == "lower" and d["link"]["how"] == "gone"
    assert d["words"].endswith("the controller no longer lists the link (2 reads), though both "
                               "its ports report up")


def test_the_affected_hosts_are_named_by_address_ipv4_and_ipv6_alike(monkeypatch):
    topo = {"state": "read", "controllers": [{"name": CONN, "hosts": [
        {"mac": "02:00:00:00:00:01", "ipv4": ["198.51.100.11"], "ipv6": [], "dpid": 3,
         "port_no": 1},
        {"mac": "02:00:00:00:00:02", "ipv4": [], "ipv6": ["fe80::2", "2001:db8:9::2"],
         "dpid": 4, "port_no": 1},
        {"mac": "02:00:00:00:00:03", "ipv4": ["198.51.100.13"], "ipv6": [], "dpid": 2214744208935,
         "port_no": 18}]}]}
    held = LF.rule(_collect(monkeypatch), {})["held"]
    (d,) = LF.rule(_collect(monkeypatch, _down, at=1_790_000_010.0), held,
                   topo=topo)["detections"]
    assert [(h["address"], h["dpid_hex"]) for h in d["affected"]] == [
        ("198.51.100.11", OVS3), ("2001:db8:9::2", OVS4)]


def test_unread_port_descriptions_leave_a_link_unjudged_and_links_unread_judge_none(
        monkeypatch):
    held = LF.rule(_collect(monkeypatch), {})["held"]

    def unread(answers):
        _down(answers)
        del answers["/stats/portdesc/3"]
    got = LF.rule(_collect(monkeypatch, unread, at=1_790_000_010.0), held)
    assert got["detections"] == [] and LF.scope(CONN, LINK) not in got["judged"]

    def no_links(answers):
        del answers["/v1.0/topology/links"]
    got = LF.rule(_collect(monkeypatch, no_links, at=1_790_000_010.0), held)
    assert got["detections"] == [] and got["judged"] == set()
    assert got["notes"][0].startswith(f"{CONN}'s links could not be read")
    plain = LF.rule(_collect(monkeypatch, _down, at=1_790_000_010.0, links=False), held)
    assert plain == {"detections": [], "judged": set(), "held": held, "notes": []}


def test_observe_fires_it_as_an_alert_keeps_it_firing_unread_and_resolves_it_restored(
        networks, monkeypatch):  # noqa: F811
    kw = {"values": dict(D.THRESHOLDS), "intent": {"state": "ok", "flows": []},
          "topo": {"state": "read", "controllers": []}}
    assert D.observe(NET, _collect(monkeypatch), **kw)["ok"]
    got = D.observe(NET, _collect(monkeypatch, _down, at=1_790_000_010.0), **kw)
    (key,) = [k for k in got["fired"]
              if next(d for d in got["detections"] if d["key"] == k)["rule"] == "link_down"]
    (piece,) = [p for p in CL._sdn_section(got["kept"][key])["pieces"]
                if p["kind"] == "detection"]
    assert piece["link"]["key"] == LINK and piece["rule"] == "link_down"

    def unread(answers):
        _down(answers)
        del answers["/stats/portdesc/3"]
    later = D.observe(NET, _collect(monkeypatch, unread, at=1_790_000_020.0), **kw)
    assert key not in later["resolved"] and key in [u["key"] for u in later["unjudged"]]
    back = D.observe(NET, _collect(monkeypatch, at=1_790_000_030.0), **kw)
    assert key in back["resolved"]


# ───────────────────────────────────────────────────────────────────────────── the verify

H1, H3 = "00:00:00:00:00:01", "00:00:00:00:00:03"
FAILED = {"key": "s1-s2", "how": "down", "ends": [
    {"dpid": 1, "dpid_hex": "0000000000000001", "port_no": 3, "name": "s1-eth3"},
    {"dpid": 2, "dpid_hex": "0000000000000002", "port_no": 3, "name": "s2-eth3"}]}


def _detection(at="2026-10-27T09:35:00Z"):
    return {"key": "lk1", "rule": "link_down", "network": "Lab", "connection": "lab",
            "dpid": 1, "dpid_hex": "0000000000000001", "port": 3, "at": at, "link": FAILED,
            "words": "link 0000000000000001 port 3 to 0000000000000002 port 3 is down"}


def _only_h1_h3(topo, ipv6_only=False):
    """The hosts the capture's tables carry a pair for (h1 and h3; Ryu's two stale hosts and
    h2 and h4, whose pair s2 holds no flow for, taken out); *ipv6_only* drops their IPv4."""
    topo["hosts"] = [dict(h, ipv4=[] if ipv6_only else h["ipv4"]) for h in topo["hosts"]
                     if h["mac"] in (H1, H3)]


def _link_gone(topo, ipv6_only=False):
    topo["links"] = [l for l in topo["links"] if l["src"]["port_no"] != 3]
    _only_h1_h3(topo, ipv6_only)


def _rerouted(topo, ipv6_only=False):
    """The failed link gone and a second link, port 4 on each switch, listed."""
    _link_gone(topo, ipv6_only)
    for sw in topo["switches"]:
        sw["ports"].append(dict(sw["ports"][-1], port_no=4, name=f"s{sw['dpid']}-eth4"))
    topo["links"] += [
        {"src": dict(topo["switches"][0]["ports"][-1]), "dst": dict(topo["switches"][1]["ports"][-1])},
        {"src": dict(topo["switches"][1]["ports"][-1]), "dst": dict(topo["switches"][0]["ports"][-1])}]


def _moved(flows):
    """The host flows' next hop moved from port 3 to port 4, as a forwarding app rewrites it."""
    out = []
    for f in flows:
        f = copy.deepcopy(f)
        if f["match"].get("in_port") == 3:
            f["match"]["in_port"] = 4
        f["actions"] = ["OUTPUT:4" if a == "OUTPUT:3" else a for a in f["actions"]]
        out.append(f)
    return out


def _store(topo_edit, moved=False):
    s1 = with_flows(S1, 1, _moved) if moved else S1
    s2 = with_flows(with_flows(S2, 2, without_bad0), 2, _moved) if moved else \
        with_flows(S2, 2, without_bad0)
    return cached(s1=s1, s2=s2, topo_edit=topo_edit)


def test_not_rerouted_when_the_tables_still_send_by_the_failed_link():
    got = LF.verify("Lab", _detection(), cached=_store(_link_gone), now=NOW)
    assert got["outcome"] == "not_rerouted" and got["checked"] == 2 and not got["final"]
    assert got["words"].startswith("not rerouted: 2 of 2 host pairs not delivered; 192.0.2.1 to "
                                   "192.0.2.3: Not delivered: it leaves the fabric by "
                                   "0000000000000001 port 3")


@pytest.mark.parametrize("ipv6_only,src", [(False, "192.0.2.1"), (True, "2001:db8:8::1")])
def test_rerouted_when_every_pair_is_delivered_avoiding_the_failed_link(ipv6_only, src):
    got = LF.verify("Lab", _detection(), now=NOW, cached=_store(
        lambda t: _rerouted(t, ipv6_only), moved=True))
    assert got["outcome"] == "rerouted" and got["final"], got["words"]
    assert [p["source"] for p in got["pairs"]][0] == src
    assert all(p["state"] == "delivered" for p in got["pairs"])
    assert got["words"].startswith("rerouted: all 2 host pairs delivered on paths that avoid "
                                   "0000000000000001 port 3 (s1-eth3) to 0000000000000002 port 3")


def test_a_pair_still_leaving_by_an_end_of_the_failed_link_is_not_rerouted():
    """A table that still sends by port 3 while the topology lists another link: delivered
    only if the walk follows a link; the failed link is gone, so it leaves the fabric."""
    got = LF.verify("Lab", _detection(), cached=_store(_rerouted), now=NOW)
    assert got["outcome"] == "not_rerouted"


def test_a_read_from_before_the_failure_or_still_listing_the_link_is_pending():
    early = LF.verify("Lab", _detection(at="2026-10-27T09:40:00Z"),
                      cached=_store(_link_gone), now=NOW)
    assert early["outcome"] == "pending" and early["words"].startswith(
        f"not yet: the stored read ({READ_AT}) is from before the failure")
    listed = LF.verify("Lab", _detection(), cached=_store(_only_h1_h3), now=NOW)
    assert listed["outcome"] == "pending" and "still lists the link" in listed["words"]


# ───────────────────────────────────────────────────────────────────────────── the modes

def _lines():
    said = []
    return said, (lambda step, words, **kw: said.append((step, words)))


def _verdicts(outcomes):
    seq = iter(outcomes)

    def verify(network, d, *, cached=None, now=None):
        o = next(seq)
        return {"outcome": o, "words": f"planted {o}", "pairs": [], "checked": 1, "total": 1,
                "read_at": "", "final": o in LF.FINAL}
    return verify


def test_hitl_keeps_a_card_for_a_person_and_verifies_nothing(networks, monkeypatch):  # noqa: F811
    monkeypatch.setattr(LF, "verify", lambda *a, **k: pytest.fail("HITL verified"))
    said, line = _lines()
    got = LF.step(NET, [dict(_detection(), network=NET)], [], now=1_790_000_000.0, line=line)
    (row,) = LF.open_rows(NET)["rows"]
    assert got["opened"] == [row["id"]] and row["mode"] == "hitl" and row["verify"] is None
    assert said[0][1].endswith(f"HITL, awaiting a person ({row['id']}): {row['why']}")
    LF.step(NET, [], [], now=1_790_000_010.0, line=line)
    assert LF.open_rows(NET)["rows"][0]["verifies"] == 0


def test_auto_verifies_until_rerouted_then_stops_and_restored_closes_it(networks,  # noqa: F811
                                                                         monkeypatch):
    from tests.test_sdn_modes_loop import mark_lab
    import time
    mark_lab(NET)
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="lab 9 run",
               until=time.time() + 600, allowed_risk="low")
    monkeypatch.setattr(LF, "verify", _verdicts(["pending", "rerouted"]))
    said, line = _lines()
    t0 = time.time()
    LF.step(NET, [dict(_detection(), network=NET)], [], now=t0, line=line)
    LF.step(NET, [], [], now=t0 + 10, line=line)
    LF.step(NET, [], [], now=t0 + 20, line=line)
    (row,) = LF.open_rows(NET)["rows"]
    assert row["mode"] == "auto" and row["verifies"] == 2
    assert (row["verify"]["outcome"], row["verify"]["actor"]) == ("rerouted", "Mercury (AUTO)")
    assert [w for s, w in said if "AUTO verify" in w][-1].endswith("planted rerouted")
    LF.step(NET, [], ["lk1"], now=t0 + 30, line=line)
    assert LF.open_rows(NET)["rows"] == []
    assert said[-1][1].endswith(f"restored: its card {row['id']} is closed")


def test_auto_leaves_a_reroute_it_never_saw_to_a_person_after_its_deadline(
        networks, monkeypatch):  # noqa: F811
    from tests.test_sdn_modes_loop import mark_lab
    import time
    mark_lab(NET)
    MD.turn_on(NET, actor="admin@example.com", actor_verified="access", reason="lab 9 run",
               until=time.time() + 600, allowed_risk="low")
    monkeypatch.setattr(LF, "verify", _verdicts(["not_rerouted"] * 3))
    said, line = _lines()
    t0 = time.time()
    LF.step(NET, [dict(_detection(), network=NET)], [], now=t0, line=line)
    LF.step(NET, [], [], now=t0 + 10, line=line)
    LF.step(NET, [], [], now=t0 + LF.VERIFY_WINDOW_S + 1, line=line)
    (row,) = LF.open_rows(NET)["rows"]
    assert row["verify"]["final"] and row["verify"]["outcome"] == "not_rerouted"
    assert row["verify"]["words"].endswith(
        f"not rerouted within {LF.VERIFY_WINDOW_S} s of the failure: a person decides "
        "(nothing was sent, so nothing is rolled back)")
    LF.step(NET, [], [], now=t0 + LF.VERIFY_WINDOW_S + 20, line=line)
    assert LF.open_rows(NET)["rows"][0]["verifies"] == 2


def test_the_loop_answers_a_link_down_with_its_card_and_no_ai_call(networks,  # noqa: F811
                                                                    monkeypatch):
    monkeypatch.setattr(LP, "classify", lambda *a, **k: pytest.fail("a link down classified"))
    d = dict(_detection(), network=NET, key="lk1", title="SDN link down", targets=[],
             source=None)
    out = LP.run_pass(NET, collect=lambda: {"network": NET, "summary": {"switches": 2},
                                            "state": "ok"},
                      observe=lambda n, c: {"ok": True, "fired": ["lk1"], "resolved": [],
                                            "detections": [d]},
                      now=lambda: 1_790_000_000.0, driver=lambda n, c: {"ok": False})
    assert out["ok"] and out["proposed"] == [] and len(out["links"]["opened"]) == 1
    assert LP.awaiting(NET)["rows"] == []
    assert [l["step"] for l in out["lines"]] == ["read", "detect", "respond"]


@pytest.fixture
def client(networks, monkeypatch):  # noqa: F811
    import app as A
    return A.app.test_client()


def test_responses_draws_the_card_and_its_verify_and_dismiss_act(client, monkeypatch):
    """SDN › Responses (board F): the card drawn with its hosts and mode; Verify the reroute
    pressed runs the verify and keeps its outcome as the person's, drawn on the card; Dismiss
    without a reason is refused, with one the card is gone."""
    from html import unescape

    d = dict(_detection(), network=NET, affected=[
        {"address": "198.51.100.11", "mac": "02:00:00:00:00:01", "dpid_hex": OVS3,
         "port_no": 1},
        {"address": "2001:db8:9::2", "mac": "02:00:00:00:00:02", "dpid_hex": OVS4,
         "port_no": 1}])
    row = LF.open_down(NET, d, mode="hitl", why="HITL: the default")
    page = unescape(client.get(f"/v2/sdn/responses?list={NET}").get_data(as_text=True))
    assert "Link down: 0000000000000001 port 3 (s1-eth3) to 0000000000000002 port 3" in page
    assert "198.51.100.11" in page and "2001:db8:9::2" in page and "awaiting a person" in page
    monkeypatch.setattr(LF, "verify", lambda network, det, **kw: {
        "outcome": "rerouted", "final": True, "words": "rerouted: all 2 host pairs delivered",
        "pairs": [{"source": "198.51.100.11", "destination": "198.51.100.12",
                   "state": "delivered", "words": "Delivered: x"}], "checked": 1, "total": 2,
        "read_at": ""})
    r = client.post(f"/v2/sdn/link/{row['id']}/verify", data={"list": NET})
    assert r.status_code == 200
    (kept,) = LF.open_rows(NET)["rows"]
    assert kept["verify"]["outcome"] == "rerouted" and kept["verify"]["actor"]
    drawn = unescape(r.get_data(as_text=True))
    assert "rerouted: all 2 host pairs delivered" in drawn and "Each host pair traced (1 of 2)" \
        in drawn and "rerouted, verified" in drawn
    assert client.post(f"/v2/sdn/link/{row['id']}/dismiss",
                       data={"list": NET, "reason": " "}).status_code == 409
    r = client.post(f"/v2/sdn/link/{row['id']}/dismiss",
                    data={"list": NET, "reason": "the cable is moved"})
    assert r.status_code == 200 and LF.open_rows(NET)["rows"] == []
    assert "Link failures" not in r.get_data(as_text=True)


def test_a_card_is_dismissed_only_with_a_reason(networks):  # noqa: F811
    row = LF.open_down(NET, dict(_detection(), network=NET), mode="hitl", why="HITL")
    with pytest.raises(ValueError, match="names its reason"):
        LF.close(NET, row["id"], "dismissed", actor="op@example.com")
    LF.close(NET, row["id"], "dismissed", actor="op@example.com", why="the cable is moved")
    assert LF.open_rows(NET)["rows"] == []
