"""SDN incidents awaiting a person reach Needs attention (`modules/attention.py`
`sdn_responses_source`; C1999): on a HITL network a threat is seen without opening SDN ›
Responses.

- One row per incident, never one per detection or per switch (C1999 item 3, which replaced
  the one row per network drawn before incidents): it names the network, the rule, the source,
  how many switches saw it, its severity, its age and where its response is proposed; WARNING,
  DANGER when classified high or critical; most severe first, then the longest waiting. Its
  action opens that incident on the network's Responses.
- It clears when the incident's response is applied or it is dismissed (it resolves), and the
  page reads it again on `sdn` (the loop's announcement, the routes' invalidation).
- A network whose responses cannot be read is the source's own error, drawn as a row of its
  own, never as no row.
"""
from modules import attention as A
from modules.sdn import incidents
from modules.sdn import loop as LP
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_modes_loop import NET, T0, detection


def _propose(key, classification=None, at=T0, also=0):
    d = detection(key)
    rec = {"key": incidents.group_key(d), "rule": "scan", "source": "192.0.2.1",
           "window_s": 60, "window_setting": "sdn_scan_window_seconds",
           "window_words": "within 60 s", "ingress_known": True,
           "ingress_words": "the ingress switch is 0000000000000001",
           "ingress_port": 1,
           "seen_also": [dict(incidents.brief(d), key=f"{key}-{n}", dpid=n + 2,
                              dpid_hex=f"{n + 2:016x}") for n in range(also)]}
    return LP.propose(NET, d, "drop_source", "low", why="HITL", now=at,
                      classification=classification, incident=rec)


def test_each_incident_awaiting_is_one_row_naming_its_switches(networks):  # noqa: F811
    one = _propose("k1", also=49)
    two = _propose("k2", at=T0 + 30)
    rows = A.sdn_responses_source(found={NET: LP.awaiting(NET)})["rows"]
    assert [(r["source"], r["kind"], r["level"], r["id"]) for r in rows] == [
        ("sdn_responses", "awaiting", "warning", f"sdn_responses:Default:{one['id']}"),
        ("sdn_responses", "awaiting", "warning", f"sdn_responses:Default:{two['id']}")]
    r = rows[0]
    assert r["what"] == "SDN scan from 192.0.2.1 on Default, seen on 50 switches, awaits a person"
    assert r["cause"] == (
        f"Incident {one['id']}, since {LP._iso(T0)} (last seen {LP._iso(T0)}): not classified; "
        "proposed drop_source at 0000000000000001 (the ingress switch is 0000000000000001). "
        "Nothing is sent to a switch until a person confirms")
    assert r["action"]["href"] == (f"/v2/sdn/responses?list=Default&incident={one['id']}"
                                   f"#sdn-i-{one['id']}")
    assert r["clears"]["ways"] == ["resolves"]
    assert r["operands"] == {"network": NET, "incident": one["id"], "rule": "scan",
                             "source": "192.0.2.1", "switches": 50, "severity": "unclassified",
                             "since": LP._iso(T0), "inactive": False}
    assert rows[1]["what"].endswith("seen on 1 switch, awaits a person")


def test_a_severe_classification_makes_it_danger_first_and_inactive_is_said(networks):  # noqa: F811,E501
    _propose("k1")
    row = _propose("k2", classification={"severity": "critical"}, at=T0 + 60)
    LP.mark(NET, row["id"], "inactive", since=LP._iso(T0 + 65), now=T0 + 65)
    first, second = A.sdn_responses_source(found={NET: LP.awaiting(NET)})["rows"]
    assert first["operands"]["incident"] == row["id"], "the most severe first, though newer"
    assert first["level"] == "danger" and second["level"] == "warning"
    assert "severity critical by its AI classification" in first["cause"]
    assert f"; no switch shows it since {LP._iso(T0 + 65)}." in first["cause"]


def test_it_clears_when_the_incident_is_applied_or_dismissed(networks):  # noqa: F811
    row = _propose("k1", also=3)
    LP.resolve(NET, row["id"], "dismissed", actor="op@example.com", why="a test")
    assert LP.awaiting(NET)["rows"] == []
    assert A.sdn_responses_source(found={NET: LP.awaiting(NET)})["rows"] == []


def test_an_unreadable_store_is_the_source_s_error():
    got = A.sdn_responses_source(found={NET: {"state": "unreadable", "rows": [],
                                              "error": "sdn_responses.jsonl: bad"}})
    (r,) = got["rows"]
    assert (r["source"], r["kind"]) == ("sdn_responses", "unreadable"), "a row of its own"
    assert ("the responses awaiting could not be read on Default (sdn_responses.jsonl: bad)"
            in r["what"] + " " + r["cause"]), r


def test_the_source_is_read_by_the_page_and_moved_by_sdn():
    assert A.sdn_responses_source in A.SOURCES
    assert A.SOURCE_KEYS["sdn_responses_source"] == ("sdn",)
