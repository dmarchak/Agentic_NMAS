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


def scan(source=SRC, at=T0 + 60, basis="tripwire"):
    return dict(det(3, source, "scan", at=at), basis=basis)


def flood(source=SRC, at=T0):
    return dict(det(3, source, "flood", at=at), basis="rate")


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
