"""Watch its ports… on a watched High packet rate (Lab 9 A; routes/sdn_v2.py `watch_tripwire`,
`sdn_ops_page._tripwire_offer`), end to end through the routes.

**The data.** The route tests' controller (tests/test_sdn_ops_v2.py's ``lab``: FakeRyu behind the
real Ryu driver), its switch 1 the team's pipeline (table 0 misses to table 2); the NSOT export
built by the real `export.build` from tests/test_sdn_policy_intent.py's Lab 9 records; the
watching row the loop's own pass opens for the walk's High packet rate walk-fp-6 (a rate on s1
port 2), its source edited to the Lab 9 records' h1 and its connection to the route tests' (the
two minimal edits).

- the row draws Watch its ports…; pressed, the card previews sixteen requests and says what the
  tripwire is; nothing is sent; confirmed by hash through the flow editor's confirm, the sixteen
  flows land with a tripwire's cookie and are verified;
- a row naming no source draws the control disabled with why; a large-packet stream (the flood
  rule's) draws none; a row no longer open is refused naming it.
"""
import json
from html import unescape

import pytest

from modules.nsot import export as X
from modules.sdn import closed_loop as CL
from modules.sdn import flow_intent as F
from modules.sdn import loop as LP
from tests.test_openflow_golden import fake_netbox
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_high_rate import walk
from tests.test_sdn_incidents import calls  # noqa: F401 - the fixture
from tests.test_sdn_ops_v2 import form_fields, lab  # noqa: F401 - the fixture
from tests.test_sdn_policy_intent import lab9_records
from tests.test_sdn_watch_propose import watched

NET = "Default"
H1 = "198.51.100.11"
TEAM = 0x9A00000000000001


@pytest.fixture
def world(lab, monkeypatch):  # noqa: F811 - the fixture
    records = lab9_records()
    monkeypatch.setattr("modules.inventory.source_config.load",
                        lambda name: {"source": "netbox", "filters": {"role": "openflow-switch"}})
    get, _calls = fake_netbox(records)
    built = X.build(NET, get=get, version=lambda: records["netbox_version"])
    assert built["ok"], built["error"]
    doc = X.parse(built["bytes"])
    monkeypatch.setattr(X, "read", lambda network, rev="HEAD": {
        "ok": True, "export": doc, "sha256": doc["sha256"], "error": ""})
    lab["fake"].table[1] = [
        {"dpid": 1, "table_id": 0, "priority": 0, "cookie": TEAM, "match": {},
         "actions": [{"type": "GOTO_TABLE", "table_id": 2}], "idle_timeout": 0,
         "hard_timeout": 0},
        {"dpid": 1, "table_id": 2, "priority": 1000, "cookie": TEAM + 1,
         "match": {"eth_dst": "02:00:00:00:00:05"}, "actions": [{"type": "OUTPUT", "port": 7}],
         "idle_timeout": 0, "hard_timeout": 0}]
    return lab


def rate(source=H1):
    d = walk("walk-fp-6")
    assert (d["rule"], d["basis"], d["dpid"]) == ("high_rate", "rate", 1), "premise"
    return dict(d, source=source, connection="lab-controller")


def page(lab) -> str:  # noqa: F811
    return unescape(lab["client"].get(f"/v2/sdn/responses?list={NET}").get_data(as_text=True))


def test_watch_its_ports_previews_sixteen_tripwires_and_the_flow_confirm_sends_them(world):
    w = watched(rate())
    html = page(world)
    assert f'hx-post="/v2/sdn/watch/{w["id"]}/tripwire' in html
    assert 'Watch its ports…' in html and f'id="sdn-tw-{w["id"]}"' in html
    card = world["client"].post(f"/v2/sdn/watch/{w['id']}/tripwire", data={"list": NET})
    text = unescape(card.get_data(as_text=True))
    assert card.status_code == 200, text
    assert f"Preview: {len(CL.TRIPWIRE_PORTS)} requests on" in text
    assert "16 tripwires on switch 0000000000000001 (" in text and f"for {H1}: TCP 21" in text
    assert "198.51.100.0/24, the subnet NetBox records it in" in text
    assert world["fake"].writes == [], "the preview sends nothing"
    fields = form_fields(card.get_data(as_text=True))
    ask = json.loads(fields["ask"])
    assert len(ask["changes"]) == 16
    done = world["client"].post("/v2/sdn/flow/confirm", data=fields)
    words = unescape(done.get_data(as_text=True))
    assert "Done, verified" in words, words
    added = [f for f in world["fake"].table[1] if F.is_tripwire(f.get("cookie"))]
    assert sorted(f["match"]["tcp_dst"] for f in added) == sorted(CL.TRIPWIRE_PORTS)
    assert all(f["hard_timeout"] == 120 for f in added)
    assert all(f["actions"] == [{"type": "GOTO_TABLE", "table_id": 2}] for f in added)
    # Recorded in the flow intent, so a response to the source leaves them out of what it must
    # climb above and is placed over them (closed_loop.build_response's tripwire guard).
    recorded = {r.get("cookie") for r in F.intent(NET, "lab-controller")["flows"]}
    assert {f["cookie"] for f in added} <= recorded


def test_a_row_naming_no_source_draws_it_disabled_saying_why(world):
    w = watched(rate(source=None))
    html = page(world)
    i = html.index(f'/v2/sdn/watch/{w["id"]}/tripwire')
    assert ('data-refused="Not available: the row names no one source address to watch"'
            in html[i:i + 1500])
    # Pressed anyway (a stale page), the route refuses it the same way and sends nothing.
    r = world["client"].post(f"/v2/sdn/watch/{w['id']}/tripwire", data={"list": NET})
    assert r.status_code == 409
    assert "names no one source address" in unescape(r.get_data(as_text=True))
    assert world["fake"].writes == []


def test_a_row_no_longer_open_is_refused_naming_it(world):
    r = world["client"].post("/v2/sdn/watch/watch-gone/tripwire", data={"list": NET})
    assert r.status_code == 409
    words = unescape(r.get_data(as_text=True))
    assert "no watched row or flood incident watch-gone is open" in words
    assert world["fake"].writes == []


def test_a_flood_incident_of_one_source_offers_its_tripwire(world, calls):  # noqa: F811
    """A scan over 50 packets a second meets the flood rule after its 30 s hold, so its
    watching row has joined the flood by the time a person opens it: the flood incident's card
    offers Watch its ports… too, previewed the same way, nothing sent."""
    from tests.test_sdn_incidents import a_pass, det
    f = dict(det(1, H1, "flood", conn="lab-controller"), basis="rate")
    a_pass([f])
    (row,) = LP.awaiting(NET)["rows"]
    html = page(world)
    assert f'hx-post="/v2/sdn/watch/{row["id"]}/tripwire' in html
    card = world["client"].post(f"/v2/sdn/watch/{row['id']}/tripwire", data={"list": NET})
    text = unescape(card.get_data(as_text=True))
    assert card.status_code == 200, text
    assert "16 tripwires on switch 0000000000000001 (" in text and f"for {H1}: TCP 21" in text
    assert world["fake"].writes == []


def test_a_large_packet_stream_draws_no_tripwire(world):
    from tests.test_sdn_watch_propose import stream
    w = watched(stream())
    assert f'/v2/sdn/watch/{w["id"]}/tripwire' not in page(world)
    assert LP.watching(NET)["rows"]
