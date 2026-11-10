"""SDN › Apps' DHCP steering card (board lab9-sdn B; routes/sdn_dhcp_v2.py, templates/v2/
_sdn_dhcp.html) through the real routes, on tests/test_dhcp_steer.py's world: the Lab 9 export
with its router, Service ``dhcp`` and two end hosts, five switches on `tests.sdn_fakes.FakeRyu`
reached through a saved controller connection and the real Ryu driver.

Each test asserts on state as well as on what is drawn: the controller's recorded writes, the
flow intent's rows, or the switches' tables.
- at rest the card draws the server from the NSOT, what each flow does, IPv6 named as not
  covered, and its actions; drawing it writes nothing and calls no controller;
- Edit settings… draws the edge switches; a chosen switch's preview and confirm steer only it
  (and the switches on its way);
- Preview steering… draws every flow and its REST body and writes nothing; its confirm, bound
  to the hash as the verified person, writes exactly those flows and records each with the
  owner and the person; another hash sends nothing;
- Remove steering… removes exactly what was recorded, by cookie;
- the counters come from the SDN reader's stored flows, never a controller call;
- a refusal is drawn in the card's place and sends nothing.
"""

import re
from html import unescape

import pytest
from werkzeug.datastructures import MultiDict

from modules.nsot import export as X
from modules.sdn import connections as C
from modules.sdn import dhcp_steer as D
from modules.sdn import flow_intent as F
from tests.test_dhcp_steer import (DPIDS, NET, export_of, lab, lab9_dhcp_records,  # noqa: F401
                                   netbox_list, networks, ours_on)

CONN = "lab-controller"


@pytest.fixture
def ui(lab, monkeypatch):  # noqa: F811 - the fixture
    from modules.sdn import drivers

    real = drivers.make

    def make(kind, connection, **kw):
        kw.setdefault("session", lab)
        kw.setdefault("sleep", lambda s: None)
        return real(kind, connection, **kw)

    monkeypatch.setattr(drivers, "make", make)
    C.save_connection(NET, {"name": CONN, "kind": "ryu", "url": lab.base}, actor="op@example.com")
    import app as A
    lab.client = A.app.test_client()
    return lab


def hidden(html):
    return [(m.group(1), unescape(m.group(2))) for m in
            re.finditer(r'<input type="hidden" name="([a-z]+)" value="([^"]*)"', html)]


def confirm_form(html):
    """The confirm form's fields (the last form on the card)."""
    part = html[html.index('class="apps-act dhcp-confirm"'):]
    return MultiDict(hidden(part[:part.index("</form>")]))


def _text(r):
    return r.get_data(as_text=True)


def test_the_card_at_rest_draws_the_server_from_the_nsot_and_writes_nothing(ui):
    sent = len(ui.sent)
    html = _text(ui.client.get(f"/v2/sdn/apps?list={NET}"))
    assert 'id="dhcp-steering"' in html and "not steered" in html
    assert ("rtr, 198.51.100.1, MAC <span class=\"mono\">00:00:5e:00:53:01</span> on ovs2 port 2"
            in html)
    assert "protected: the NSOT&#39;s dhcp classes name feature:dhcp-unicast" in html
    assert "DHCPv6 (UDP 546 and 547) is not steered: it floods as before" in html
    assert "Edit settings…" in html and "Preview steering…" in html
    assert re.search(r'disabled aria-disabled="true" title="No steering flow is recorded"', html)
    assert ui.sent[sent:] == [] and F.read(NET)["state"] == "absent", \
        "drawing the card calls no controller and records nothing"


def test_preview_then_confirm_by_hash_steers_and_records_the_owner_and_person(ui):
    r = ui.client.post("/v2/sdn/dhcp/preview", data={"list": NET, "scope": "all"})
    html = _text(r)
    assert r.status_code == 200, html
    assert "Steer DHCP on 5 switches: 9 requests" in html
    assert "POST /stats/flowentry/add" in html and "client request, unicast to the server" in html
    assert ui.writes == [], "the preview writes nothing"
    fields = confirm_form(html)
    assert len(fields.getlist("cookie")) == 9
    r = ui.client.post("/v2/sdn/dhcp/confirm", data=fields)
    html = _text(r)
    assert r.status_code == 200 and "DHCP steering applied" in html and "Verified" in html, html
    rows = F.intent(NET, CONN)["flows"]
    assert len(rows) == 9 and {x["response"]["owner"] for x in rows} == {D.OWNER}
    assert {x["actor"] for x in rows} == {"test-person@example.invalid"}
    assert len([p for p, _b in ui.writes if p == "/stats/flowentry/add"]) == 9
    again = _text(ui.client.get(f"/v2/sdn/dhcp/card?list={NET}"))
    assert "on 5 switches" in again


def test_a_confirm_bound_to_another_hash_sends_nothing(ui):
    html = _text(ui.client.post("/v2/sdn/dhcp/preview", data={"list": NET, "scope": "all"}))
    fields = MultiDict([(k, "f" * 64 if k == "hash" else v)
                        for k, v in confirm_form(html).items(multi=True)])
    r = ui.client.post("/v2/sdn/dhcp/confirm", data=fields)
    assert r.status_code == 409 and "Nothing was sent" in _text(r)
    assert ui.writes == [] and F.read(NET)["state"] == "absent"


def test_edit_settings_chooses_the_edge_switches_and_the_confirm_steers_only_them(ui):
    html = _text(ui.client.get(f"/v2/sdn/dhcp/settings?list={NET}"))
    assert 'name="switch" value="arista-sw2"' in html and 'name="switch" value="ovs1"' in html
    html = _text(ui.client.post("/v2/sdn/dhcp/preview", data={
        "list": NET, "scope": "chosen", "switch": "arista-sw2"}))
    assert "Steer DHCP on 2 switches: 4 requests" in html, html
    r = ui.client.post("/v2/sdn/dhcp/confirm", data=confirm_form(html))
    assert r.status_code == 200, _text(r)
    assert {x["dpid"] for x in F.intent(NET, CONN)["flows"]} == {2, 4}
    assert ours_on(ui, 3) == [] and len(ours_on(ui, 2)) == 3


def test_remove_steering_removes_exactly_what_was_recorded(ui):
    html = _text(ui.client.post("/v2/sdn/dhcp/preview", data={"list": NET, "scope": "all"}))
    ui.client.post("/v2/sdn/dhcp/confirm", data=confirm_form(html))
    cookies = {x["cookie"] for x in F.intent(NET, CONN)["flows"]}
    ui.writes.clear()
    html = _text(ui.client.post("/v2/sdn/dhcp/remove/preview", data={"list": NET}))
    assert "Remove DHCP steering: 9 flows on 5 switches" in html, html
    assert "the NSOT export and the NetBox Service are untouched" in html
    assert ui.writes == []
    r = ui.client.post("/v2/sdn/dhcp/remove/confirm", data=confirm_form(html))
    assert r.status_code == 200 and "Removed DHCP steering" in _text(r), _text(r)
    import json
    assert {json.loads(b)["cookie"] for _p, b in ui.writes} == cookies
    assert F.intent(NET, CONN)["flows"] == [] and all(ours_on(ui, d) == [] for d in
                                                     DPIDS.values())


def test_the_counts_come_from_the_stored_read_never_a_controller_call(ui):
    p = D.preview(NET)
    assert D.confirm(NET, "steer", p["hash"], actor="op@example.com", cookies=p["cookies"],
                     sleep=lambda s: None)["outcome"] == "verified"
    rows = F.intent(NET, CONN)["flows"]
    counted = {"request": 12, "reply_drop": 0, "transit": 7}
    flows = [{"cookie": x["cookie"], "packet_count": counted[D.role_of(x)]} for x in rows]
    cached = {"doc": {"last_good": {"value": {"controllers": [{
        "name": CONN, "last_good_at": "2026-11-10T04:00:00Z",
        "switches": [{"dpid": 0, "flows": flows}]}]}}}}
    sent = len(ui.sent)
    s = D.card(NET, cached=cached)
    assert s["counts"]["requests"] == 12 * 2 and s["counts"]["replies_dropped"] == 0
    assert s["counts"]["state"] == "read" and ui.sent[sent:] == []
    from flask import render_template
    import app as A
    with A.app.test_request_context():
        html = render_template("v2/_sdn_dhcp.html", s=D.view(s))
    assert "24 requests steered · 0 replies dropped from another port" in html


def test_a_refusal_is_drawn_in_the_card_s_place_and_sends_nothing(ui, monkeypatch):
    records = lab9_dhcp_records()
    records["services"] = [x for x in records["services"] if x["name"] != "dhcp"]
    ui.held["doc"] = export_of(records)
    r = ui.client.post("/v2/sdn/dhcp/preview", data={"list": NET, "scope": "all"})
    html = _text(r)
    assert r.status_code == 409 and 'id="dhcp-steering"' in html and "Refused" in html
    assert "holds no NetBox Service named &#39;dhcp&#39;" in html
    assert ui.writes == [] and X.read(NET)["ok"]
