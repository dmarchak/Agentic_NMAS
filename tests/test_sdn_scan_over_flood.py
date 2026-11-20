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
- the scan's card offers its rate limit in packets a second (the review of 94fa79c8, 3).
"""
import pytest

from modules.sdn import incidents
from modules.sdn import loop as LP
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_incidents import T0, a_pass, calls, det  # noqa: F401 - the fixture

pytestmark = pytest.mark.usefixtures("calls")
SRC = "192.0.2.61"


WATCHED = "192.0.2.0/24"


def scan(source=SRC, at=T0 + 60, basis="tripwire"):
    """A scan in `detect._tripwire_scans`' shape: no target, the subnet watched said."""
    return dict(det(3, source, "scan", at=at), basis=basis, targets=[],
                measurement={"what": "tripwire ports a source touched", "value": 16,
                             "unit": "ports", "of": 16, "watched": [WATCHED]})


def flood(source=SRC, at=T0, since=None, pps=250):
    """A flood in `detect.flood`'s shape at *pps*, its measurement's ``since`` *since*
    (default *at*)."""
    return dict(det(3, source, "flood", at=at), basis="rate", targets=[], port=3,
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


def test_a_flood_of_several_large_packet_sources_offers_no_tripwire():
    """The review of d1cb5b71 (4): one attack of several large-packet sources on a host
    (`detect._large_packets`) is no scan; no tripwire is offered on it."""
    from modules import sdn_ops_page as P
    attack = dict(flood(), attack_sources=[SRC, "192.0.2.62"], attack_host="192.0.2.3")
    assert P._tripwire_offer(attack) == {"offered": False, "refusal": ""}
    assert P._tripwire_offer(flood())["offered"]
