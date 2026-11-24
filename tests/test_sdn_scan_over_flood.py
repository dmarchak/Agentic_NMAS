"""A scan Mercury's tripwires confirmed wins over a flood from the same source (the operator,
2026-11-20: "a >100 pps small-packet scan lasting >30 s also meets the flood rule … If the flood
rule pre-empts a scan the tripwire has already confirmed, that's a bug"; `loop._scan_supersedes`,
`incidents.scan_over_flood`).

**The data.** The loop's own pass (`loop.run_pass`) over detections in `detect._detection`'s
shape (tests/test_sdn_incidents.py's `det`), the scan's basis ``tripwire`` as
`detect._tripwire_scans` makes it, with the loop's classify step counted (its ``calls``
fixture). The order is the hardware's: the flood first (its 30 s hold), then the tripwire scan;
and the reverse; and both in one pass.

- the flood first: the tripwire scan opens one incident, the flood's is closed ``joined`` into
  it and seen also there, and a watching row of the source closes joined too;
- the scan first: the flood's sighting joins the scan's incident, opening none;
- both in one pass: one incident awaiting a person, the scan's;
- the guard: a scan the tripwires did not confirm, and a flood from another source, stay their
  own;
- the scan's card offers its rate limit in packets a second (the review of 94fa79c8, 3);
- a scan's replies decided once over the pass and the floods waiting (C4195), its target told
  from a host mirroring it by the scanner's own destinations, and no response proposed against
  any host where nothing tells them apart (C4196): IPv4 and IPv6.
"""
import pytest

from modules.sdn import incidents
from modules.sdn import loop as LP
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_incidents import T0, a_pass, calls, det  # noqa: F401 - the fixture

pytestmark = pytest.mark.usefixtures("calls")
SRC = "192.0.2.61"


WATCHED = "192.0.2.0/24"


def scan(source=SRC, at=T0 + 60, basis="tripwire", watched=WATCHED):
    """A scan in `detect._tripwire_scans`' shape: no target, the subnet watched said."""
    return dict(det(3, source, "scan", at=at), basis=basis, targets=[],
                measurement={"what": "tripwire ports a source touched", "value": 16,
                             "unit": "ports", "of": 16, "watched": [watched]})


def flood(source=SRC, at=T0, since=None, pps=250, dpid=3):
    """A flood in `detect.flood`'s shape at *pps* on switch *dpid*'s port 3, its measurement's
    ``since`` *since* (default *at*)."""
    return dict(det(dpid, source, "flood", at=at), basis="rate", targets=[], port=3,
                measurement={"what": "packets received a second", "value": pps, "unit": "pps",
                             "since": LP._iso(at if since is None else since)})


def waiting():
    return {incidents.key_of(r): r for r in LP.awaiting("Default")["rows"]}


def _closed(rid):
    return [r for r in LP._read("Default", LP.PENDING_FILE)["rows"]
            if r.get("id") == rid and r.get("kind") in LP.CLOSED]


def test_the_flood_first_then_the_tripwire_scan_is_one_incident_the_scan_s():
    f = flood()
    a_pass([f])
    (fr,) = LP.awaiting("Default")["rows"]
    assert incidents.key_of(fr) == f"flood|{SRC}", "premise: the flood's own incident"
    s = scan()
    out = a_pass([s], at=T0 + 60, still=[f, s])
    (row,) = LP.awaiting("Default")["rows"]
    assert incidents.key_of(row) == f"scan|{SRC}" and row["detection"]["basis"] == "tripwire"
    assert [x["key"] for x in row["seen_also"]] == [f["key"]]
    (closed,) = _closed(fr["id"])
    assert closed["kind"] == "joined" and closed["incident"] == row["id"]
    assert {"id": fr["id"], "into": row["id"]} in out["joined_into"]
    assert any(f"joins scan incident {row['id']}" in x["words"] for x in out["lines"])


def test_the_scan_first_then_the_flood_joins_the_scan_s_incident():
    s = scan(at=T0)
    a_pass([s])
    (row,) = LP.awaiting("Default")["rows"]
    f = flood(at=T0 + 30)
    a_pass([f], at=T0 + 30, still=[s, f])
    (still,) = LP.awaiting("Default")["rows"]
    assert still["id"] == row["id"] and incidents.key_of(still) == f"scan|{SRC}"
    assert f["key"] in [x["key"] for x in still["seen_also"]]


def test_both_in_one_pass_are_one_incident_the_scan_s():
    f, s = flood(at=T0), scan(at=T0)
    a_pass([f, s])
    assert list(waiting()) == [f"scan|{SRC}"], waiting()


@pytest.mark.parametrize("other", ["an-ordinary-scan", "another-source"])
def test_a_scan_the_tripwires_did_not_confirm_or_another_source_s_flood_stays_its_own(other):
    f = flood() if other == "an-ordinary-scan" else flood(source="192.0.2.99")
    a_pass([f])
    s = scan(basis="ports") if other == "an-ordinary-scan" else scan()
    a_pass([s], at=T0 + 60, still=[f, s])
    assert set(waiting()) == {incidents.key_of({"detection": f}), f"scan|{SRC}"}, waiting()


def test_a_watching_row_of_the_source_closes_into_the_scan():
    rate = dict(det(3, SRC, "high_rate"), basis="rate")
    a_pass([rate])
    (w,) = LP.watching("Default")["rows"]
    s = scan()
    a_pass([s], at=T0 + 60, still=[rate, s])
    assert LP.watching("Default")["rows"] == []
    (row,) = LP.awaiting("Default")["rows"]
    closed = [r for r in LP._read("Default", LP.PENDING_FILE)["rows"]
              if r.get("id") == w["id"] and r.get("kind") == "joined"]
    assert closed and closed[0]["incident"] == row["id"]


def test_the_scan_s_card_offers_its_rate_limit_in_packets_a_second():
    from modules import sdn_ops_page as P
    from modules.sdn import closed_loop as CL
    a_pass([scan(at=T0)])
    (row,) = P.incident_rows(LP.awaiting("Default"), network="Default")
    assert row["rate_default"] == CL.SCAN_RATE_LIMIT_DEFAULT
    a_pass([flood(source="192.0.2.99", at=T0)])
    (fl,) = [r for r in P.incident_rows(LP.awaiting("Default"), network="Default")
             if r["rule"] == "flood"]
    assert fl["rate_default"] == CL.RATE_LIMIT_DEFAULT
    assert fl["tripwire"] == {"offered": True, "refusal": ""}


def test_a_flood_long_after_the_scan_s_last_sighting_is_its_own():
    """The review of d1cb5b71 (1): within the scan incident's window only, so a scan card left
    waiting never absorbs a flood that comes much later (and AUTO may answer that one)."""
    a_pass([scan(at=T0)])
    f = flood(at=T0 + 600)
    a_pass([f], at=T0 + 600)
    assert set(waiting()) == {f"scan|{SRC}", f"flood|{SRC}"}, waiting()


# ─────────────────────────────── the scan's answer and the card's choices (the operator, 2026-11-20)

def test_a_tripwire_scan_is_proposed_as_a_rate_limit_in_packets_a_second():
    """Step 5 on the Lab 9 hardware: the scan card offered only the drop. A scan the tripwires
    confirmed is proposed as the rate limit at the scan's default, the drop beside it."""
    from modules.sdn import closed_loop as CL
    a_pass([scan(at=T0)])
    (row,) = LP.awaiting("Default")["rows"]
    assert row["action"] == "rate_limit_source"
    assert {k: row["params"][k] for k in ("unit", "rate", "burst")} == \
        CL.SCAN_RATE_LIMIT_DEFAULT
    assert row["choices"] == [{"action": "drop_source",
                               "label": CL.CATALOGUE["drop_source"]["label"]}]
    assert row["withheld"] == []


def test_an_ordinary_scan_keeps_the_policy_s_default_and_offers_the_rate_limit():
    from modules.sdn import closed_loop as CL
    a_pass([scan(at=T0, basis="ports")])
    (row,) = LP.awaiting("Default")["rows"]
    assert row["action"] == "drop_source"
    assert row["choices"] == [{"action": "rate_limit_source",
                               "label": CL.CATALOGUE["rate_limit_source"]["label"]}]


def test_a_drop_the_protected_set_refuses_is_withheld_saying_why(monkeypatch):
    """On the Lab 9 fabric a source drop meets an untouchable class no response owns: the
    card offers the rate limit alone and says why the drop is not offered. The class is planted
    in the protected set's own shape, and the refusal is the real guard's."""
    from modules import protected
    planted = {"state": "ok", "source": "planted", "sha256": "0" * 64, "objects": {},
               "switches": {}, "ports": {}, "external": {"owners": [], "refused": []},
               "error": "", "classes": [{
                   "name": "management", "invariant": "untouchable", "owners": [],
                   "match": [{"eth_type": 0x0800, "ipv4_src": WATCHED}],
                   "source": "planted", "reason": "the path Mercury reaches every device on"}]}
    monkeypatch.setattr(protected, "for_network", lambda network: planted)
    a_pass([scan(at=T0)])
    (row,) = LP.awaiting("Default")["rows"]
    assert row["action"] == "rate_limit_source" and row["choices"] == []
    (w,) = row["withheld"]
    assert w["action"] == "drop_source" and "management" in w["why"], w


# ───────────────────────────────────────────────── the scan's target's replies (the same report)

def _collected(port_bytes):
    """A collection holding switch 3's port 3 at 250 pps of *port_bytes* each."""
    return {"controllers": [{"connection": "c1", "switches": [{
        "dpid_hex": "0000000000000003", "ports": [
            {"port_no": 3, "rx_pps": 250.0, "rx_bytes_per_s": 250.0 * port_bytes}]}]}]}


@pytest.mark.parametrize("target,size,dests,peer,replies", [
    ("192.0.2.62", 54, [], 250, True),
    ("192.0.2.62", 54, [], None, False),
    ("192.0.2.62", 54, [], 4000, False),
    ("192.0.2.62", 1500, [], 250, False),
    ("198.51.100.62", 54, [], 250, False),
    ("192.0.2.62", 54, ["192.0.2.99"], 250, False),
    ("192.0.2.62", 54, [SRC], None, True),
], ids=["rsts-mirroring-the-scanner", "unnamed-with-no-scanner-rate",
        "unnamed-at-another-rate", "large", "another-subnet", "to-another-host",
        "named-to-the-scanner"])
def test_the_scan_s_target_s_small_packets_are_its_replies(target, size, dests, peer, replies):
    """Where a reply's destinations are unnamed (the Lab 9 fabric's table 0 names none), the
    scanner's own rate in the pass must mirror it (the review of 37e377db, 1): a second host of
    the subnet flooding at its own rate, or with no scanner traffic beside it, is its own."""
    from modules.sdn import detect as D
    reply = dict(flood(source=target), dst_hosts=dests)
    peers = [flood(pps=peer)] if peer else []
    marked = D.mark_replies([scan(), reply] + peers, _collected(size))
    (got,) = [m for m in marked if m["key"] == reply["key"]]
    if replies:
        assert got["source"] is None and got["replying_to"]["rule"] == "scan"
        assert got["replying_to"]["source"] == SRC and got["replying_hosts"] == [target]
    else:
        assert got["source"] == target and "replying_to" not in got


def test_the_replies_in_the_scan_s_pass_join_its_incident():
    from modules.sdn import detect as D
    reply = flood(source="192.0.2.62")
    (marked,) = [m for m in D.mark_replies([scan(), reply, flood()], _collected(54))
                 if m["key"] == reply["key"]]
    a_pass([scan(), marked], at=T0 + 60)
    assert list(waiting()) == [f"scan|{SRC}"], waiting()
    (row,) = LP.awaiting("Default")["rows"]
    assert marked["key"] in row["members"]


@pytest.mark.parametrize("began,pps,joins", [(T0 + 2, 250, True), (T0 - 200, 250, False),
                                              (T0 + 2, 5000, False)],
                         ids=["with-the-scan", "long-before", "at-its-own-rate"])
def test_a_reply_flood_already_waiting_joins_the_scan_that_began_with_it(began, pps, joins):
    """The hardware's order: scan A's 250 pps made the scanner's flood and its target's RSTs a
    flood of their own, both waiting; the tripwire scan then opens and takes both. A flood from
    the subnet that did not begin with the scanner's own is its own."""
    a_pass([flood(at=T0)])
    a_pass([flood(source="192.0.2.62", at=began, since=began, pps=pps)], at=max(T0, began),
           still=[flood(at=T0), flood(source="192.0.2.62", at=began, since=began, pps=pps)])
    a_pass([scan(at=T0 + 60)], at=T0 + 60)
    want = {f"scan|{SRC}"} | (set() if joins else {"flood|192.0.2.62"})
    assert set(waiting()) == want, waiting()


def test_two_hosts_mirroring_the_scan_with_no_destination_named_are_each_their_own():
    """The review of 7437d140: a scan of one host has one target, so where nothing names their
    destinations, two hosts of the subnet mirroring the scan's rate are not both its replies
    (one is a second attacker at the same tool's default rate): neither is taken, in the pass
    or among the floods waiting when the scan opens."""
    from modules.sdn import detect as D
    one, two = flood(source="192.0.2.62"), flood(source="192.0.2.63")
    marked = D.mark_replies([scan(), one, two, flood()], _collected(54))
    for d in (one, two):
        (got,) = [m for m in marked if m["key"] == d["key"]]
        assert got["source"] == d["source"] and "replying_to" not in got
    a_pass([flood(at=T0)])
    a_pass([one, two], at=T0 + 2, still=[flood(at=T0), one, two])
    a_pass([scan(at=T0 + 60)], at=T0 + 60)
    assert set(waiting()) == {f"scan|{SRC}", "flood|192.0.2.62", "flood|192.0.2.63"}, waiting()


def test_a_flood_of_several_large_packet_sources_offers_no_tripwire():
    """The review of d1cb5b71 (4): one attack of several large-packet sources on a host
    (`detect._large_packets`) is no scan; no tripwire is offered on it."""
    from modules import sdn_ops_page as P
    attack = dict(flood(), attack_sources=[SRC, "192.0.2.62"], attack_host="192.0.2.3")
    assert P._tripwire_offer(attack) == {"offered": False, "refusal": ""}
    assert P._tripwire_offer(flood())["offered"]


# ──────────────────── one count over the pass and the floods waiting; the target told (C4195, C4196)

#: Per address family: the scanner, the subnet its tripwires watch, and two hosts of it that
#: send small packets at the scanner's own rate (the hardware's 250 pps of 54 B RSTs).
FAMILIES = {"ipv4": (SRC, WATCHED, "192.0.2.62", "192.0.2.63"),
            "ipv6": ("2001:db8::61", "2001:db8::/64", "2001:db8::62", "2001:db8::63")}
#: The same host written another way, as a topology may list it.
SPELT = {"192.0.2.62": "192.0.2.62", "192.0.2.63": "192.0.2.63",
         "2001:db8::62": "2001:db8:0:0:0:0:0:62", "2001:db8::63": "2001:DB8::63"}


@pytest.fixture(params=sorted(FAMILIES))
def fam(request):
    return FAMILIES[request.param]


def _observing(monkeypatch, dets, fired, at):
    """`detect.observe` as the loop calls it: *dets* judged by the real `mark_replies` with
    what the loop hands it (the floods awaiting a person, C4195); *fired* the new ones."""
    from modules.sdn import detect as D
    from tests.test_sdn_incidents import WINDOWS

    def observe(network, collected, **kw):
        kw.pop("clock", None)
        return {"ok": True, "fired": [d["key"] for d in fired], "resolved": [],
                "detections": D.mark_replies(dets, _collected(54), **kw),
                "thresholds": dict(WINDOWS), "collected_at": LP._iso(at)}
    monkeypatch.setattr(D, "observe", observe)


def _one_waiting_one_in_the_pass(monkeypatch, fam, names=()):
    """The hardware's order with two hosts: the scanner's flood (its destinations *names*) and
    the second host's flood each waiting as an incident, then the tripwire scan opening in a
    pass whose detections hold the first host's flood, new, beside the scanner's."""
    from tests.test_sdn_incidents import NO_DRIVER, collected
    src, net, first, second = fam

    def own(at=T0):
        return dict(flood(source=src, at=at), dst_hosts=[SPELT[n] for n in names])
    later = flood(source=second, at=T0 + 2, since=T0 + 2)
    a_pass([own()])
    a_pass([later], at=T0 + 2, still=[own(), later])
    now = flood(source=first, at=T0 + 60, since=T0 + 59)
    s = scan(source=src, at=T0 + 60, watched=net)
    _observing(monkeypatch, [s, now, own()], [s, now], T0 + 60)
    LP.run_pass("Default", collect=collected, now=lambda: T0 + 60, driver=NO_DRIVER)
    return waiting()


def test_a_host_in_the_pass_and_one_waiting_are_counted_together(monkeypatch, fam):
    """C4195 (the review of 6f023dc3, 1): one host mirroring the scan in this pass and a second
    already waiting as an incident are two, never one each: with nothing naming their
    destinations, neither is taken as the scan's replies."""
    src, _net, first, second = fam
    got = _one_waiting_one_in_the_pass(monkeypatch, fam)
    assert set(got) == {f"scan|{src}", f"flood|{first}", f"flood|{second}"}, set(got)


@pytest.mark.parametrize("target", ["in-the-pass", "waiting"])
def test_the_scanner_s_destinations_tell_its_target_across_the_two(monkeypatch, fam, target):
    """C4196 with C4195: the scanner's own flood names the host it sends to, so that host is
    the scan's target, never a source (waiting, its flood joins the scan; in the pass, it is
    the destination of the scanner's flood, C2237), and the other, mirroring the scan beside
    it, is its own, never taken as the scan's replies, its response proposed as any flood's."""
    src, _net, first, second = fam
    named, other = (first, second) if target == "in-the-pass" else (second, first)
    got = _one_waiting_one_in_the_pass(monkeypatch, fam, names=[named])
    assert f"scan|{src}" in got and f"flood|{named}" not in got, set(got)
    assert f"flood|{other}" in got, set(got)
    for row in got.values():
        if named in (row["detection"].get("replying_hosts") or []):
            assert row["detection"]["replying_to"]["source"] == src
    assert got[f"flood|{other}"]["action"] == "rate_limit_source", set(got)


def test_the_scanner_s_own_destinations_tell_its_target_from_a_host_mirroring_it(fam):
    """C4196 (the review of 6f023dc3, 2): an attacker mirroring the scan beside its real target
    is told from it. The scanner's traffic names the target (as the topology lists it, in any
    spelling), so the target is never a source (the destination of the scanner's flood,
    C2237), and the mirror, which the scanner's traffic does not name, is never taken as the
    scan's replies: it stays its own."""
    from modules.sdn import detect as D
    src, net, target, mirror = fam
    t, m = flood(source=target), flood(source=mirror)
    own = dict(flood(source=src), dst_hosts=[SPELT[target]])
    got = {x["key"]: x for x in D.mark_replies([scan(source=src, watched=net), t, m, own],
                                                _collected(54))}
    assert got[t["key"]]["source"] is None and got[t["key"]]["replying_to"]["source"] == src
    assert got[t["key"]]["replying_hosts"] == [target]
    assert got[m["key"]]["source"] == mirror and "replying_to" not in got[m["key"]]
    assert "scan_target_unsure" not in got[m["key"]]


def _two_mirrors_unnamed(fam):
    from modules.sdn import detect as D
    src, net, one, two = fam
    return D.mark_replies([scan(source=src, watched=net), flood(source=one), flood(source=two),
                           flood(source=src)], _collected(54))


def test_where_nothing_tells_the_target_no_response_is_proposed_against_either(fam):
    """C4196: two hosts mirror the scan and nothing names a destination, so one of them is the
    scan's target and Mercury cannot say which: each stays its own incident (C4191), and
    neither is proposed a response against its host; a person decides, the rule's actions
    still offered on the card."""
    src, _net, one, two = fam
    a_pass(_two_mirrors_unnamed(fam), at=T0 + 60)
    got = waiting()
    assert set(got) == {f"scan|{src}", f"flood|{one}", f"flood|{two}"}, set(got)
    for host in (one, two):
        row = got[f"flood|{host}"]
        assert row["action"] == "" and row["params"] == {}, row["action"]
        assert f"may be the target of {src}'s scan" in row["why"], row["why"]
        assert "rate_limit_source" in [c["action"] for c in row["choices"]]


def _auto(monkeypatch) -> list:
    """AUTO on for the network at its highest risk, a person's act; the sources of each
    response the loop previews or confirms, appended to the list returned."""
    from modules.sdn import closed_loop as CL
    from modules.sdn import modes as MD
    MD.set_stage("Default", "lab", actor="admin@example.com", actor_verified="access",
                 reason="the course lab's network")
    MD.turn_on("Default", actor="admin@example.com", actor_verified="access", reason="a lab run",
               until=T0 + 600, allowed_risk=MD.RISKS[-1], now=T0 - 1)
    sent = []

    def respond(network, d, action, params=None, *, confirm=None, **kw):
        sent.append(d.get("source"))
        if confirm is None:
            return {"ok": True, "ask": {"a": 1}, "plan": {"hash": "h"}}
        return {"id": f"sdnop-{len(sent)}", "outcome": "verified"}
    monkeypatch.setattr(CL, "respond_to_threat", respond)
    monkeypatch.setattr(CL, "log_response", lambda *a, **k: {"step": "respond", "words": "x"})
    return sent


def test_auto_sends_nothing_against_a_host_that_may_be_the_scan_s_target(monkeypatch, fam):
    """C4196 in AUTO, which a person turns on: the loop's own rules never act against either
    host that may be the scan's target; the scan itself is still answered."""
    src, _net, one, two = fam
    sent = _auto(monkeypatch)
    a_pass(_two_mirrors_unnamed(fam), at=T0 + 60)
    assert src in sent and one not in sent and two not in sent, sent
    assert {f"flood|{one}", f"flood|{two}"} <= set(waiting()), set(waiting())


# ─────────────── the device-write review of the C4195 and C4196 patch (2026-11-24, findings 1 to 5)

#: Per family, a host the scanner's other traffic reaches outside the watched subnet (a
#: resolver), as an IP-matched flow names it.
ELSEWHERE = {SRC: "203.0.113.99", "2001:db8::61": "2001:db8:ffff::99"}


@pytest.mark.parametrize("resolver", ["quiet", "replying"])
def test_a_lone_reply_outside_the_scanner_s_named_destinations_is_unsure(monkeypatch, fam,
                                                                         resolver):
    """Finding 1 (HIGH): the scanner's traffic names a destination, but not the one host
    replying to its scan. Named destinations are never the scanner's whole set, so that host
    may be the scan's target: no response is proposed against it, and AUTO sends none. The
    named host replying to the scanner's traffic from outside the watched subnet (marked
    replying, C2237) accounts for no target."""
    from modules.sdn import detect as D
    src, net, target, _other = fam
    t = flood(source=target)
    own = dict(flood(source=src), targets=[ELSEWHERE[src]])
    more = [flood(source=ELSEWHERE[src])] if resolver == "replying" else []
    got = {x["key"]: x for x in D.mark_replies([scan(source=src, watched=net), t, own] + more,
                                                _collected(54))}
    if more:
        assert got[more[0]["key"]]["replying_to"]["source"] == src, "premise: C2237's mark"
    assert got[t["key"]].get("scan_target_unsure", {}).get("hosts") == [target], got[t["key"]]
    sent = _auto(monkeypatch)
    a_pass(list(got.values()), at=T0 + 60)
    assert src in sent and target not in sent, sent
    assert waiting()[f"flood|{target}"]["action"] == ""


def test_a_target_s_card_open_before_the_scanner_s_flood_closes_into_the_scan(monkeypatch, fam):
    """Finding 2 (MEDIUM): the flood rule's hold ends on the target's port first, so its card
    opens with the target as its source; the scanner's flood naming it fires next, and then
    the scan. The target, still firing and marked replying to the scanner's flood (C2237), is
    the scan's: its card closes into the scan, never left proposing a response against it."""
    from tests.test_sdn_incidents import NO_DRIVER, collected
    src, net, target, _other = fam
    t = flood(source=target, at=T0)
    own = dict(flood(source=src, at=T0 + 2), dst_hosts=[SPELT[target]])
    a_pass([t])
    a_pass([own], at=T0 + 2, still=[t, own])
    assert f"flood|{target}" in waiting(), "premise: the target's own card, waiting"
    s = scan(source=src, at=T0 + 60, watched=net)
    _observing(monkeypatch, [s, t, own], [s], T0 + 60)
    LP.run_pass("Default", collect=collected, now=lambda: T0 + 60, driver=NO_DRIVER)
    assert set(waiting()) == {f"scan|{src}"}, set(waiting())


def test_every_sighting_of_an_unsure_host_carries_it(monkeypatch, fam):
    """Finding 3 (MEDIUM): one host may be the scan's target, seen on two switches; its second
    sighting's port is not in the collection, so `scan_replied` cannot read its packets. Each
    sighting is unsure, whichever the incident chooses (here the earlier, the second), and AUTO
    sends nothing against it."""
    from modules.sdn import detect as D
    src, net, one, two = fam
    first, second = flood(source=one, at=T0 + 60), flood(source=one, at=T0 + 50, dpid=4)
    dets = [scan(source=src, watched=net), first, second, flood(source=two), flood(source=src)]
    got = {x["key"]: x for x in D.mark_replies(dets, _collected(54))}
    assert all(got[d["key"]].get("scan_target_unsure") for d in (first, second)), \
        [sorted(got[d["key"]]) for d in (first, second)]
    sent = _auto(monkeypatch)
    a_pass(list(got.values()), at=T0 + 60)
    assert src in sent and one not in sent and two not in sent, sent


def test_the_false_positive_replay_says_no_response_is_proposed_for_an_unsure_host(fam):
    """Finding 5 (LOW): the replay's words for what the loop does with a host that may be the
    scan's target are the loop's: no response proposed, a person's card. The detections carry
    the rest of `detect._detection`'s fields the replay's evidence section reads."""
    from modules.sdn import false_positives as FP
    src, _net, one, _two = fam
    (d,) = [x for x in _two_mirrors_unnamed(fam) if x.get("source") == one]
    d = dict(d, evidence=[], confidence_why="its rate alone",
             threshold={"what": "packets received a second", "value": 50, "unit": "pps"})
    words = FP.handled(d, _collected(54))
    assert words.startswith("no response proposed") and src in words, words


# ──────────────── the second device-write review of the C4195 and C4196 patch (2026-11-24, N1 to N3)

@pytest.mark.parametrize("replier", ["in-the-pass", "waiting"])
def test_a_host_naming_the_scanner_accounts_for_no_target(monkeypatch, fam, replier):
    """N1 (HIGH): the scanner's flows name only a resolver; another watched host's flows name
    the scanner; the true target's name nothing. That host shows only that the scanner reaches
    hosts its flows do not name, so the target's replies are never called a mirror's: AUTO
    sends nothing against the target."""
    from tests.test_sdn_incidents import NO_DRIVER, collected
    src, net, target, other = fam

    def own(at=T0):
        return dict(flood(source=src, at=at), targets=[ELSEWHERE[src]])
    named = dict(flood(source=other, at=T0 + 1, since=T0 + 1), targets=[src])
    t = flood(source=target, at=T0 + 60, since=T0 + 59)
    s = scan(source=src, at=T0 + 60, watched=net)
    if replier == "waiting":
        a_pass([own()])
        a_pass([named], at=T0 + 1, still=[own(), named])
        dets = [s, t, own()]
    else:
        dets = [s, t, named, own()]
    sent = _auto(monkeypatch)
    _observing(monkeypatch, dets, [s, t] + ([] if replier == "waiting" else [named, own()]),
               T0 + 60)
    LP.run_pass("Default", collect=collected, now=lambda: T0 + 60, driver=NO_DRIVER)
    assert target not in sent, sent
    row = waiting().get(f"flood|{target}")
    assert row is not None and row["action"] == "", set(waiting())


def test_a_lone_waiting_host_that_may_be_the_target_proposes_nothing_from_then(monkeypatch, fam):
    """N2 (MEDIUM): the target's flood is already waiting, its card proposing a rate limit
    against it, when the scan opens with the scanner naming only a resolver: nothing tells
    the target, so its card proposes no response from then on, saying why, the rule's
    actions still offered for a person to choose."""
    from tests.test_sdn_incidents import NO_DRIVER, collected
    src, net, target, _other = fam

    def own(at=T0):
        return dict(flood(source=src, at=at), targets=[ELSEWHERE[src]])
    t = flood(source=target, at=T0 + 2, since=T0 + 2)
    a_pass([own()])
    a_pass([t], at=T0 + 2, still=[own(), t])
    assert waiting()[f"flood|{target}"]["action"] == "rate_limit_source", "premise"
    s = scan(source=src, at=T0 + 60, watched=net)
    _observing(monkeypatch, [s, own()], [s], T0 + 60)
    LP.run_pass("Default", collect=collected, now=lambda: T0 + 60, driver=NO_DRIVER)
    row = waiting().get(f"flood|{target}")
    assert row is not None and row["action"] == "" and row["params"] == {}, row
    assert f"may be the target of {src}'s scan" in row["why"], row["why"]
    assert "rate_limit_source" in [c["action"] for c in row["choices"]], row["choices"]
    assert row["detection"]["scan_target_unsure"]["hosts"] == [target]


def test_a_waiting_card_of_two_unsure_hosts_proposes_nothing_either(monkeypatch, fam):
    """N2's other shape, C4195's own: one host waiting and one in the pass, nothing naming a
    destination; each stays its own incident and neither card proposes a response."""
    src, _net, first, second = fam
    got = _one_waiting_one_in_the_pass(monkeypatch, fam)
    for host in (first, second):
        row = got.get(f"flood|{host}")
        assert row is not None and row["action"] == "", (host, row and row["action"], set(got))


def test_every_sighting_of_a_taken_host_is_the_scan_s_replies(monkeypatch, fam):
    """N3 (MEDIUM, on main too): the scan's one replying host is seen on two switches, the
    second's port not in the collection; both sightings are its replies, so no incident of
    the host opens and AUTO sends nothing against it."""
    from modules.sdn import detect as D
    src, net, target, _other = fam
    read, unread = flood(source=target, at=T0 + 60), flood(source=target, at=T0 + 50, dpid=4)
    got = {x["key"]: x for x in D.mark_replies(
        [scan(source=src, watched=net), read, unread, flood(source=src)], _collected(54))}
    assert [got[d["key"]].get("replying_to", {}).get("source") for d in (read, unread)] == \
        [src, src], [got[d["key"]].get("source") for d in (read, unread)]
    sent = _auto(monkeypatch)
    a_pass(list(got.values()), at=T0 + 60)
    assert src in sent and target not in sent, sent
