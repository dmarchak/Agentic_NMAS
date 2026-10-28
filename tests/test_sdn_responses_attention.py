"""SDN responses awaiting a person reach Needs attention (`modules/attention.py`
`sdn_responses_source`; C1999's notification half): on a HITL network a threat is seen
without opening SDN › Responses.

- One row per network, never one per detection: it counts the responses awaiting, names the
  oldest's time, rule, source and proposed action, and how many are no longer active; WARNING,
  DANGER when any is classified high or critical. Its action opens the network's Responses.
- It clears when every response is applied or dismissed (it resolves), and the page reads it
  again on `sdn` (the loop's announcement, the routes' invalidation).
- A network whose responses cannot be read is the source's own error, drawn as a row of its
  own, never as no row.
"""
from modules import attention as A
from modules.sdn import loop as LP
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_modes_loop import NET, T0, detection


def _propose(key, classification=None, at=T0):
    return LP.propose(NET, detection(key), "drop_source", "low", why="HITL", now=at,
                      classification=classification)


def test_responses_awaiting_are_one_row_for_the_network(networks):  # noqa: F811
    _propose("k1")
    _propose("k2", at=T0 + 30)
    (r,) = A.sdn_responses_source(found={NET: LP.awaiting(NET)})["rows"]
    assert (r["source"], r["kind"], r["level"], r["id"]) == (
        "sdn_responses", "awaiting", "warning", "sdn_responses:Default")
    assert r["what"] == "2 SDN responses await a person on Default"
    assert r["cause"] == (f"The oldest, since {LP._iso(T0)}: SDN scan from 192.0.2.1, proposed "
                          "drop_source. Nothing is sent to a switch until a person confirms")
    assert r["action"]["href"] == "/v2/sdn/responses?list=Default"
    assert r["clears"]["ways"] == ["resolves"]
    assert r["operands"] == {"network": NET, "awaiting": 2, "oldest": LP._iso(T0), "severe": 0,
                             "inactive": 0}


def test_a_severe_classification_makes_it_danger_and_inactive_ones_are_counted(networks):  # noqa: F811,E501
    row = _propose("k1", classification={"severity": "critical"})
    LP.mark(NET, row["id"], "inactive", since=LP._iso(T0 + 5), now=T0 + 5)
    (r,) = A.sdn_responses_source(found={NET: LP.awaiting(NET)})["rows"]
    assert r["level"] == "danger" and r["what"] == "1 SDN response awaits a person on Default"
    assert "; 1 classified high or critical; 1 no longer active." in r["cause"]


def test_it_clears_when_each_is_applied_or_dismissed(networks):  # noqa: F811
    row = _propose("k1")
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
