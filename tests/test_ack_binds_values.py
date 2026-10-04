"""The publication acknowledgement covers only the values the person was shown
(CONCURRENCY_AUDIT R41; 2026-10-04).

`POST /remote/acknowledge` checked that the typed text named the gated KINDS, and
`remote.acknowledge` then recorded whatever values the scan found at click time. The gate's unit
is the value (C280: each live secret by a salted fingerprint), so a new secret of a kind already
named, committed between the card being drawn and the click, was acknowledged without anyone
seeing it: R12's shape. Now the card sends the fingerprints it showed, and the acknowledgement
refuses, naming each fingerprint that differs, when its own scan's values are not those.
"""

import pytest

from modules.nsot import remote as R
from tests.test_nsot_remote import lab  # noqa: F401  (the fixture)


def _scan(fingerprints):
    rows = [{"device": "r1", "kind": "snmp_community", "recoverable": True,
             "distinct": len(fingerprints), "live": len(fingerprints), "dead": 0}]
    values = [{"fingerprint": fp, "kind": "snmp_community", "devices": ["r1"],
               "recoverable": True, "at_head": ["r1"]} for fp in fingerprints]
    return {"rows": rows, "blobs_scanned": 1, "gated_kinds": ["snmp_community"],
            "live_values": values}


@pytest.fixture
def adopted(lab, monkeypatch):  # noqa: F811
    R.adopt("default", ssh_alias="a", owner="o", repo="r")
    monkeypatch.setattr(R, "_run", lambda *a, **k: type(
        "P", (), {"stdout": "abc123\n", "stderr": "", "returncode": 0})())
    return monkeypatch


def test_the_values_shown_are_the_values_recorded(adopted):
    adopted.setattr(R, "scan_history_secrets", lambda *a, **k: _scan(["fp-a", "fp-b"]))
    out = R.acknowledge("default", actor="a@b", actor_kind="person", shown=["fp-b", "fp-a"])
    assert out["ok"] is True
    assert sorted(out["acknowledged"]["values"]) == ["fp-a", "fp-b"]


def test_a_value_committed_after_the_card_was_drawn_is_refused_naming_it(adopted):
    adopted.setattr(R, "scan_history_secrets", lambda *a, **k: _scan(["fp-a", "fp-new"]))
    out = R.acknowledge("default", actor="a@b", actor_kind="person", shown=["fp-a"])
    assert out["ok"] is False
    assert "fp-new" in out["error"] and "not shown" in out["error"]
    assert not (R.load_remote("default") or {}).get("acknowledged_secrets")


def test_the_route_refuses_an_acknowledgement_that_names_nothing_it_was_shown(adopted):
    import app as nmas
    from routes import remote as routes_remote

    adopted.setattr(routes_remote.identity, "require",
                    lambda *a, **k: (type("I", (), {"actor": "a@b", "kind": "person"})(),
                                     None))
    adopted.setattr(routes_remote, "_list_name", lambda: "default")
    adopted.setattr(R, "first_push_preview",
                    lambda name: {"ok": True, "secrets": _scan(["fp-a"])})
    adopted.setattr(R, "scan_history_secrets", lambda *a, **k: _scan(["fp-a"]))
    client = nmas.app.test_client()
    r = client.post("/remote/acknowledge", json={"typed": "snmp_community"})
    assert r.status_code == 400 and "did not say which values" in r.get_json()["error"]
    r = client.post("/remote/acknowledge", json={"typed": "snmp_community", "shown": ["fp-a"]})
    assert r.status_code == 200, r.get_json()


def test_the_card_sends_the_fingerprints_it_showed():
    from tests.payload_render import lift, shipped

    ack = lift(shipped("partials__golden_repo.2.js"), "remoteAcknowledge")
    assert "body: JSON.stringify({typed: typed, shown: Object.keys(values)})});" in ack
