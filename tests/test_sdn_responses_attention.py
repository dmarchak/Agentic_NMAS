"""SDN incidents awaiting a person reach Needs attention (`modules/attention.py`
`sdn_responses_source`; C1999): on a HITL network a threat is seen without opening SDN ›
Responses. And a controller that does not answer reaches it too (`sdn_controllers_source`,
C1869's row carried into C1999).

- One row per incident, never one per detection or per switch (C1999 item 3, which replaced
  the one row per network drawn before incidents): it names the network, the rule, the source,
  how many switches saw it, its severity, its age and where its response is proposed; WARNING,
  DANGER when classified high or critical; most severe first, then the longest waiting. Its
  action opens that incident on the network's Responses.
- **Escalation** (C1999): an incident awaiting a person for its network's
  `sdn_escalate_after_minutes` (15 by default) is the same row raised to DANGER whatever its
  classification, saying "unanswered for N minutes", counted from the time its response was
  proposed on Mercury's clock (never the detection's or a device's), and saying no on-call
  integration is configured (Mercury has none). A threshold that cannot be read is said and
  the row drawn escalated. Escalation never clears a row; the row is still one per incident.
- It clears when the incident's response is applied or it is dismissed (it resolves), and the
  page reads it again on `sdn` (the loop's announcement, the routes' invalidation) and on
  `settings` (the threshold changed).
- A network whose responses cannot be read is the source's own error, drawn as a row of its
  own, never as no row.
- **A controller not answering** (the real SDN reader over tests/test_sdn_v2.py's captured Ryu,
  then a refused connection): one DANGER row per network naming the controller, its URL (IPv4
  and IPv6), the failure, since when and how many reads in a row, cleared at the read that
  finds it answering; a network with no controller set has none; an unreadable store is the
  source's own error.
"""
import pytest

from modules import attention as A
from modules import list_settings
from modules.sdn import incidents
from modules.sdn import loop as LP
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_modes_loop import NET, T0, detection

MIN = 60


def _propose(key, classification=None, at=T0, also=0, detected_at=None):
    d = detection(key)
    if detected_at is not None:
        d["at"] = LP._iso(detected_at)
    rec = {"key": incidents.group_key(d), "rule": "scan", "source": "192.0.2.1",
           "window_s": 60, "window_setting": "sdn_scan_window_seconds",
           "window_words": "within 60 s", "ingress_known": True,
           "ingress_words": "the ingress switch is 0000000000000001",
           "ingress_port": 1,
           "seen_also": [dict(incidents.brief(d), key=f"{key}-{n}", dpid=n + 2,
                              dpid_hex=f"{n + 2:016x}") for n in range(also)]}
    return LP.propose(NET, d, "drop_source", "low", why="HITL", now=at,
                      classification=classification, incident=rec)


def _rows(now):
    return A.sdn_responses_source(found={NET: LP.awaiting(NET)}, now=now)["rows"]


def test_each_incident_awaiting_is_one_row_naming_its_switches(networks):  # noqa: F811
    one = _propose("k1", also=49)
    two = _propose("k2", at=T0 + 30)
    rows = _rows(T0 + MIN)
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
                             "since": LP._iso(T0), "inactive": False, "escalated": False,
                             "unanswered_minutes": 1, "escalate_after_minutes": 15}
    assert rows[1]["what"].endswith("seen on 1 switch, awaits a person")


def test_a_severe_classification_makes_it_danger_first_and_inactive_is_said(networks):  # noqa: F811,E501
    _propose("k1")
    row = _propose("k2", classification={"severity": "critical"}, at=T0 + 60)
    LP.mark(NET, row["id"], "inactive", since=LP._iso(T0 + 65), now=T0 + 65)
    first, second = _rows(T0 + 65)
    assert first["operands"]["incident"] == row["id"], "the most severe first, though newer"
    assert first["level"] == "danger" and second["level"] == "warning"
    assert "severity critical by its AI classification" in first["cause"]
    assert f"; no switch shows it since {LP._iso(T0 + 65)}." in first["cause"]
    assert not first["operands"]["escalated"], "danger by its classification, not escalated"


def test_it_clears_when_the_incident_is_applied_or_dismissed(networks):  # noqa: F811
    row = _propose("k1", also=3)
    LP.resolve(NET, row["id"], "dismissed", actor="op@example.com", why="a test")
    assert LP.awaiting(NET)["rows"] == []
    assert _rows(T0 + 60 * MIN) == [], "an escalated incident dismissed clears as any does"


def test_an_unreadable_store_is_the_source_s_error():
    got = A.sdn_responses_source(found={NET: {"state": "unreadable", "rows": [],
                                              "error": "sdn_responses.jsonl: bad"}})
    (r,) = got["rows"]
    assert (r["source"], r["kind"]) == ("sdn_responses", "unreadable"), "a row of its own"
    assert ("the responses awaiting could not be read on Default (sdn_responses.jsonl: bad)"
            in r["what"] + " " + r["cause"]), r


def test_the_source_is_read_by_the_page_and_moved_by_sdn_and_settings():
    assert A.sdn_responses_source in A.SOURCES
    assert A.SOURCE_KEYS["sdn_responses_source"] == ("sdn", "settings")


# ───────────────────────────────────────────────────────────────────────────── escalation

def test_an_incident_unanswered_past_the_threshold_escalates_to_danger(networks):  # noqa: F811
    """At 14:59 it awaits; at 15:00 the same row (one per incident) is danger, says how long
    it has gone unanswered and that no on-call integration is configured, and still clears
    only when a person answers it."""
    row = _propose("k1", classification={"severity": "low"}, also=2)
    (before,) = _rows(T0 + 15 * MIN - 1)
    assert before["level"] == "warning" and not before["operands"]["escalated"]
    assert before["what"].endswith("seen on 3 switches, awaits a person")
    (after,) = _rows(T0 + 15 * MIN)
    assert after["id"] == before["id"], "the same row, escalated: never a second one"
    assert after["level"] == "danger", "whatever its classification (low here)"
    assert after["what"] == ("SDN scan from 192.0.2.1 on Default, seen on 3 switches, awaits a "
                             "person, unanswered for 15 minutes")
    assert ("; escalated: unanswered for 15 minutes, at or past Default's "
            "sdn_escalate_after_minutes (15), whatever its classification; no on-call "
            "integration is configured for this network (Mercury has none to notify), so this "
            "row is the only notice. Nothing is sent") in after["cause"]
    assert (after["operands"]["escalated"], after["operands"]["unanswered_minutes"],
            after["operands"]["escalate_after_minutes"]) == (True, 15, 15)
    assert after["clears"]["ways"] == ["resolves"] and after["since"] == LP._iso(T0)
    (later,) = _rows(T0 + 61 * MIN)
    assert later["what"].endswith("unanswered for 61 minutes")
    LP.resolve(NET, row["id"], "dismissed", actor="op@example.com", why="a test")
    assert _rows(T0 + 61 * MIN) == []


def test_the_wait_is_counted_from_the_proposal_not_the_detection(networks):  # noqa: F811
    """Mercury's clock at the proposal (the response store's time), never the detection's
    time: a detection stamped an hour earlier does not make a fresh incident escalated."""
    _propose("k1", at=T0, detected_at=T0 - 3600)
    (r,) = _rows(T0 + 5 * MIN)
    assert r["level"] == "warning" and r["operands"]["unanswered_minutes"] == 5


def test_the_threshold_is_the_network_s_setting(networks):  # noqa: F811
    got = list_settings.write(NET, {"sdn_escalate_after_minutes": 5}, actor="op@example.com")
    assert got["ok"], got
    _propose("k1")
    (r,) = _rows(T0 + 5 * MIN - 1)
    assert r["level"] == "warning"
    (r,) = _rows(T0 + 5 * MIN)
    assert r["level"] == "danger" and r["what"].endswith("unanswered for 5 minutes")
    assert "Default's sdn_escalate_after_minutes (5)" in r["cause"]


@pytest.mark.parametrize("answer", [RuntimeError("store unreadable"), 0, "15", True])
def test_a_threshold_not_known_is_said_and_drawn_escalated(networks, monkeypatch,  # noqa: F811
                                                          answer):
    """Never read as not yet reached: an unreadable or out-of-bounds value escalates the row
    and names why."""
    def value(network, key, default=None):
        if isinstance(answer, Exception):
            raise answer
        return answer
    _propose("k1")
    monkeypatch.setattr(list_settings, "value", value)
    (r,) = _rows(T0 + MIN)
    assert r["level"] == "danger" and r["operands"]["escalated"]
    assert r["operands"]["escalate_after_minutes"] is None
    want = ("could not be read (RuntimeError)" if isinstance(answer, Exception)
            else f"is {answer!r}, not a whole number of minutes from 1 to 1440")
    assert (f"; escalated, since its escalation threshold is not known (Default's "
            f"sdn_escalate_after_minutes {want}); no on-call integration is configured"
            in r["cause"]), r["cause"]


def test_the_setting_is_declared_bounded_and_drawn_on_a_network_card():
    from modules import settings_schema as S
    from modules import settings_scope as SC
    assert S.DEFAULTS["sdn_escalate_after_minutes"] == A.SDN_ESCALATE_DEFAULT == 15
    assert S.validate(dict(S.DEFAULTS, sdn_escalate_after_minutes=0))[0] is False
    assert S.validate(dict(S.DEFAULTS, sdn_escalate_after_minutes=1441))[0] is False
    assert SC.scope_of("sdn_escalate_after_minutes")[0] == SC.NETWORK
    assert "sdn_escalate_after_minutes" in SC.network_groups(), "set in Mercury, on a card"


# ───────────────────────────────────────────────────────────────── a controller not answering

@pytest.fixture
def lab(networks, monkeypatch):  # noqa: F811 - the fixture, used
    from tests.test_sdn_v2 import make_lab
    return make_lab(networks, monkeypatch)


def _controllers(at):
    return A.sdn_controllers_source(now=at)


def test_a_controller_not_answering_is_one_row_until_a_read_finds_it_answering(lab):
    from modules.readers import sdn_controllers as SDN
    from tests.test_sdn_v2 import BASE, T0 as TV, Captured, Down, store_read

    store_read()
    got = _controllers(TV + 10)
    assert got["rows"] == [] and got["state"] == "read"
    assert got["checked"].startswith("1 SDN controller(s) in the last read of each network "
                                      "with one set: 0 not answering"), got["checked"]
    lab["sessions"]["session"] = Down()
    store_read(clock=lambda: TV + 40)
    store_read(clock=lambda: TV + 70)
    (r,) = _controllers(TV + 70)["rows"]
    assert (r["source"], r["kind"], r["level"], r["id"]) == (
        "sdn_controllers", "not_answering", "danger", "sdn_controllers:Default")
    assert r["what"] == f"SDN controller lab-controller on Default is not answering ({BASE})"
    assert r["since"] == SDN._iso(TV + 40), "since its first failed read, not this one"
    assert r["read_at"] == SDN._iso(TV + 70)
    assert f"lab-controller (Ryu, {BASE}): " in r["cause"] and "could not connect" in r["cause"]
    assert (f"not answering since {SDN._iso(TV + 40)} (2 reads in a row), its switches as "
            f"last read at {SDN._iso(TV + 10)}") in r["cause"]
    assert r["action"]["href"] == "/v2/sdn?list=Default"
    assert r["action"]["label"].startswith(f"Check lab-controller answers at {BASE}, then read")
    assert r["clears"]["ways"] == ["resolves"]
    assert (r["operands"]["controllers"], r["operands"]["failures"]) == (["lab-controller"], 2)
    lab["sessions"]["session"] = Captured()
    store_read(clock=lambda: TV + 100)
    assert _controllers(TV + 100)["rows"] == [], "cleared by the read that finds it answering"


def test_an_ipv6_controller_not_answering_is_its_own_network_s_row(lab):
    from modules.sdn import connections as C
    from tests.test_sdn_v2 import BASE6, T0 as TV, Down, store_read

    store_read()                                              # Default answers
    C.save_connection("Branch", {"name": "v6", "kind": "ryu", "url": BASE6},
                      actor="op@example.com")
    lab["sessions"]["session"] = Down(BASE6)
    store_read("Branch", clock=lambda: TV + 40)
    (r,) = _controllers(TV + 40)["rows"]
    assert r["id"] == "sdn_controllers:Branch", "Default answers; Lab-3 has none set"
    assert r["what"] == f"SDN controller v6 on Branch is not answering ({BASE6})"
    assert r["operands"]["urls"] == [BASE6] and r["action"]["href"] == "/v2/sdn?list=Branch"


def test_a_network_with_no_controller_set_has_no_row(lab):
    """Lab-3 and Branch set none: their stores are not configured, never a row."""
    got = A.sdn_controllers_source(found={
        "Branch": {"state": "not_configured", "why": "none set"},
        "Lab-3": {"state": "not_applicable", "why": "declared"}}, now=T0)
    assert got["rows"] == [] and got["checked"].startswith("0 SDN controller(s)")


def test_an_unreadable_reader_store_is_the_source_s_error():
    got = A.sdn_controllers_source(found={NET: {"state": "unreadable", "why": "bad json"}},
                                   now=T0)
    (r,) = got["rows"]
    assert (r["source"], r["kind"]) == ("sdn_controllers", "unreadable")
    assert "the SDN reader's store could not be read for Default (bad json)" in r["cause"]


def test_the_controllers_source_is_read_by_the_page_and_moved_by_sdn():
    assert A.sdn_controllers_source in A.SOURCES
    assert A.SOURCE_KEYS["sdn_controllers_source"] == ("sdn",)
