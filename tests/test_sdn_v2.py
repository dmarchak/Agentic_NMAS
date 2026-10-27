"""SDN › Controllers, SDN › Flows and Settings' SDN controllers card (PHASE8_PLAN 17.1 S11; boards
SdnControllers, SdnFlows, SdnSettings and SdnPhone, signed off 2026-10-27), through the real app,
routes, templates, reader and drivers, on a temporary store with three networks (Default, Branch,
Lab-3), the controller answered by Ryu 4.34's captured answers (tests/fixtures/sdn/ryu/
rest_with_peer.json) through the real Ryu driver, and the flow intent as Mercury would record
it: the capture's meter flow (cookie ...0002) recorded, its drop flow (...0001) not, and an IPv6
drop recorded and never installed.

- **The SDN reader** (`modules/readers/sdn_controllers.py`): what a page draws, read once per
  interval, never per request: each connection's state and version, each switch's own name, its
  flows with whose each is (`flow_intent.classify`), its records missing, its meters with their
  owner; a connection that stops answering keeps what it last read, saying since when and how
  many reads in a row; a network with no connection is not read, and never reads Default's
  (C1841).
- **Controllers:** the summary, a card per connection with its operating state, Test connection
  in place, "Edit connection" to Settings, and the board's empty state; drawn from the store
  (no controller call per view).
- **Flows:** the summary by owner; the switches folded, one with something wrong open; the
  controller's own hidden by default; the filter; each flow's owner; an unauthorised flow's
  Remove… drawn disabled with its reason (S8); the meters; the granularity note.
- **Settings card:** per network; each driver with its status, the later ones not selectable;
  a credential typed and never drawn back; Test answering in place; Save refused while Test has
  not answered for the URL as typed; Edit; Remove… saying what survives.
"""

import dataclasses
import json
import re
from html import unescape as html_unescape
from urllib.parse import parse_qs, urlsplit

import pytest

from modules import reader_job
from modules.readers import sdn_controllers as SDN
from modules.sdn import connections as C
from modules.sdn import flow_intent as F
from tests.sdn_fakes import Response, Routes, captured, fixture
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_ryu import LIMIT, V6_DROP

BASE = "http://192.0.2.10:8080"
BASE6 = "http://[2001:db8::10]:8080"
WITH_PEER = fixture("rest_with_peer.json")
PASSWORD = "Pw-sdn-ui-4471zz"
T0 = 1_790_000_000.0


class Captured(Routes):
    """Ryu's captured answers, repeatable (a read asks each GET more than once)."""

    def __init__(self, base=BASE, flows=None):
        super().__init__(WITH_PEER, base)
        self.flows = flows

    def request(self, method, url, **kwargs):
        if self.flows is not None and url.endswith("/stats/flow/1"):
            self.sent.append(dict(kwargs, method=method, url=url))
            return Response(200, json.dumps({"1": self.flows}))
        if "/v1.0/topology/" in url:
            # This capture's controller ran ofctl_rest alone: its topology REST is Ryu's own 404
            # (rest_no_switch.json, the same image), so the topology is said as not running.
            self.sent.append(dict(kwargs, method=method, url=url))
            return captured(next(e for e in fixture("rest_no_switch.json")
                                 if e["path"] == "/v1.0/topology/links"))
        return super().request(method, url, **kwargs)


class Down(Routes):
    def __init__(self, base=BASE):
        super().__init__(WITH_PEER, base)

    def request(self, method, url, **kwargs):
        import requests
        self.sent.append(dict(kwargs, method=method, url=url))
        raise requests.ConnectionError("connection refused")


@pytest.fixture
def lab(networks, monkeypatch):  # noqa: F811 - the fixture, used
    """Default with one Ryu connection over the capture; the flow intent recorded."""
    return make_lab(networks, monkeypatch)


def make_lab(networks, monkeypatch):  # noqa: F811 - a store, not the fixture
    """The fixture's body, for tests/test_board_shots.py's SDN shots."""
    from modules.sdn import drivers

    sessions = {"session": Captured()}
    real = drivers.make

    def make(kind, connection, **kw):
        kw.setdefault("session", sessions["session"])
        return real(kind, connection, **kw)

    monkeypatch.setattr(drivers, "make", make)
    C.save_connection("Default", {"name": "lab-controller", "kind": "ryu", "url": BASE,
                                  "southbound": "192.0.2.10:6653"}, actor="op@example.com")
    for spec in (LIMIT, V6_DROP):
        F.record_installed("Default", connection="lab-controller", flow=dict(spec, dpid=1),
                           actor="op@example.com", response={"id": "resp-1", "action": "x"},
                           at=T0)
    import app as A
    return {"client": A.app.test_client(), "sessions": sessions, "dir": networks}


def store_read(network="Default", clock=lambda: T0 + 10):
    """One run of the reader for *network*, stored as the scheduler stores it."""
    from modules import integration_groups as IG
    gid = IG.group_id("sdn_controllers", network)
    reader = dataclasses.replace(
        SDN.READER, name=IG.store_name(SDN.READER_NAME, gid), per_group=(), read_for=None,
        read=lambda: SDN.read(network, clock=clock, sleep=lambda s: None))
    return reader_job.run_once(reader, announce=lambda *a, **k: None, clock=clock)


def value(network="Default"):
    got = reader_job.read_cached_for(SDN.READER_NAME, network)
    return got["doc"]["last_good"]["value"]


def get(lab, path):
    r = lab["client"].get(path)
    return r, r.get_data(as_text=True)


def words(html):
    """What a person reads: the tags gone, the entities read, the spaces one."""
    import html as H
    return " ".join(H.unescape(re.sub(r"<[^>]+>", " ", html)).split())


# ───────────────────────────────────────────────────────────────────────────── the reader

class TestTheReader:
    def test_the_capture_read_whole(self, lab):
        store_read()
        (c,) = value()["controllers"]
        assert (c["name"], c["state"], c["version"]) == ("lab-controller", "connected", None)
        assert c["version_note"] == "Ryu's ofctl_rest reports no version"
        (sw,) = c["switches"]
        assert (sw["dpid_hex"], sw["name"], sw["state"]) == ("0000000000000001", "s1", "ok")
        owners = {f["cookie"]: f["owner"] for f in sw["flows"]}
        assert owners[LIMIT["cookie"]] == "mercury"
        assert owners[0x4D45524300000001] == "unauthorised", "Mercury's prefix, no record"
        assert sorted(set(owners.values())) == ["controller_own", "mercury", "unauthorised"]
        (missing,) = sw["records"]
        assert (missing["cookie"], missing["state"], missing["priority"]) == (
            V6_DROP["cookie"], "missing", 100)
        (meter,) = sw["meters"]
        assert (meter["meter_id"], meter["owner"], meter["flows"]) == (1, "mercury", 1)
        assert sw["meter_features"]["max_meter"] == 200
        assert sw["coverage"]["granularity"] == "L4"

    def test_its_calls_are_counted_and_none_is_per_request(self, lab):
        store_read()
        sent = len(lab["sessions"]["session"].sent)
        # 1 + 3N (the closed loop), test()'s 1, the topology's first request (S14: this
        # controller runs no topology application, so its 404 ends the read), and per switch
        # its description, meters (two requests on Ryu: their configuration and their
        # statistics) and meter features.
        assert sent == 4 + 1 + 1 + 4
        (c,) = value()["controllers"]
        assert c["topology"]["state"] == "could not read"
        assert "the topology app is not running" in c["topology"]["error"]
        for path in ("/v2/sdn", "/v2/sdn/flows", "/v2/sdn/view?tab=flows"):
            assert get(lab, path)[0].status_code == 200
        assert len(lab["sessions"]["session"].sent) == sent, "a page view asks no controller"

    def test_a_controller_that_stops_answering_keeps_what_it_read(self, lab):
        store_read()
        lab["sessions"]["session"] = Down()
        store_read(clock=lambda: T0 + 40)
        store_read(clock=lambda: T0 + 70)
        (c,) = value()["controllers"]
        assert (c["state"], c["failures"]) == ("not_answering", 2)
        assert c["failing_since"] == SDN._iso(T0 + 40) and "could not connect" in c["error"]
        assert c["last_good_at"] == SDN._iso(T0 + 10)
        assert [s["dpid_hex"] for s in c["switches"]] == ["0000000000000001"], "as last read"

    def test_a_network_with_none_is_not_read_and_never_reads_default_s(self, lab):
        """C1841 through the reader: Branch sets none, so there is nothing to read; it never
        reads Default's controller."""
        from modules import integration_groups as IG
        assert [g["id"] for g in IG.groups(("sdn_controllers",))] == ["default"]
        got = reader_job.read_cached_for(SDN.READER_NAME, "Branch")
        assert got["state"] == "not_configured"
        assert SDN.read("Branch", sleep=lambda s: None)["controllers"] == []

    def test_an_ipv6_controller_reads_alike(self, lab):
        lab["sessions"]["session"] = Captured(BASE6)
        C.save_connection("Branch", {"name": "v6", "kind": "ryu", "url": BASE6},
                          actor="op@example.com")
        got = SDN.read("Branch", sleep=lambda s: None)
        (c,) = got["controllers"]
        assert c["state"] == "connected" and c["url"] == BASE6


# ───────────────────────────────────────────────────────────────────────────── Controllers

class TestControllers:
    def test_the_summary_and_a_card_per_connection(self, lab):
        from modules import csp
        store_read()
        r, html = get(lab, "/v2/sdn")
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert re.search(r'class="nav-item active" href="/v2/sdn\?list=Default"', html)
        text = words(html)
        assert "1 controller · 1 connected · 1 switch" in text
        assert "lab-controller connected" in text
        assert "Version not reported (Ryu's ofctl_rest reports no version)" in text
        assert "Southbound 192.0.2.10:6653 · informational: where switches connect" in text
        assert "read flows read port stats read meters write flows write meters " \
               "delete flows read topology" in text and "not offered by this driver" not in text
        assert "Controller's own flows cookie 0" in text
        assert 'href="/v2/sdn/flows?q=0000000000000001&amp;list=Default"' in html
        assert re.search(r'<a class="btn" href="/v2/settings/network/Default\?'
                         r'tab=integrations#sdn-card">Edit connection</a>', html)

    def test_a_connection_not_answering_says_since_when(self, lab):
        store_read()
        lab["sessions"]["session"] = Down()
        store_read(clock=lambda: T0 + 40)
        _r, html = get(lab, "/v2/sdn")
        assert "not answering" in html and "Not answering since" in html
        assert "1 read in a row" in html and "1 at the last good read" in html

    def test_saved_and_not_read_yet(self, lab):
        _r, html = get(lab, "/v2/sdn")
        assert "Not read yet" in html and "has not read this network" in html

    def test_the_empty_state_is_the_board_s(self, lab):
        _r, html = get(lab, "/v2/sdn?list=Branch")
        assert "No SDN controller is connected to this network." in html
        assert ">Add one in Settings › Integrations</a>." in html
        assert "sdn-sum" not in html and "sdn-ctl" not in html, "and nothing else drawn"

    def test_test_connection_answers_in_place(self, lab):
        r = lab["client"].post("/v2/sdn/controller/lab-controller/test?list=Default")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "Answered:" in html and "1 switch connected" in html
        lab["sessions"]["session"] = Down()
        html = lab["client"].post("/v2/sdn/controller/lab-controller/test?list=Default")\
            .get_data(as_text=True)
        assert "Couldn't connect" in html and "could not connect to" in html


# ───────────────────────────────────────────────────────────────────────────── Flows

class TestFlows:
    def test_the_summary_by_owner_and_the_switch_open(self, lab):
        store_read()
        _r, html = get(lab, "/v2/sdn/flows")
        text = words(html)
        assert "1 switch · 9 flows : 1 Mercury's · 7 the controller's own · 1 unauthorised · " \
               "1 of Mercury's missing · 1 meter" in text
        assert re.search(r'<details class="sdn-sw" data-keep="sw-0000000000000001" open>', html)
        assert "s1 · lab-controller" in text

    def test_the_controller_s_own_hidden_by_default_and_shown_when_asked(self, lab):
        store_read()
        _r, html = get(lab, "/v2/sdn/flows")
        assert "7 the controller's own (hidden)" in html and "OUTPUT:CONTROLLER" not in html
        _r, html = get(lab, "/v2/sdn/flows?own=show")
        assert "OUTPUT:CONTROLLER" in html and "(hidden)" not in html

    def test_each_flow_s_owner_and_its_remove_and_edit_open_the_editor(self, lab):
        """S16 (C1912): Remove… on every flow and Edit… on Mercury's open the editor in place,
        naming the flow by its table, priority, match and cookie; the unauthorised flow has no
        Edit…, since edit is for Mercury's own flows."""
        store_read()
        _r, html = get(lab, "/v2/sdn/flows")
        row = re.search(r'<tr class="sdn-f-unauthorised">.*?</tr>', html, re.S).group(0)
        assert "unauthorised" in row and "0x4d45524300000001" in row
        assert "carries Mercury's prefix" in words(row)
        remove = re.search(r'hx-get="(/v2/sdn/flow/form\?do=remove[^"]*)"', row)
        assert remove and "Remove…" in row and "Edit…" not in row
        target = json.loads(parse_qs(urlsplit(html_unescape(remove.group(1))).query)
                            ["target"][0])
        assert target["cookie"] == 0x4d45524300000001 and set(target) == {
            "table_id", "priority", "match", "cookie"}
        ours = re.search(r'<tr class="sdn-f-mercury">.*?</tr>', html, re.S).group(0)
        assert "installed as expected" in ours and "METER:1, OUTPUT:2" in ours
        assert "do=edit" in ours and "do=remove" in ours
        missing = re.search(r'<tr class="sdn-r-missing">.*?</tr>', html, re.S).group(0)
        assert "Mercury&#39;s, missing" in missing and "not installed" in missing

    def test_the_filter(self, lab):
        store_read()
        _r, html = get(lab, "/v2/sdn/flows?q=METER")
        assert "METER:1" in html and "0x4d45524300000001" not in html
        _r, html = get(lab, "/v2/sdn/flows?q=nothing-matches-this")
        assert 'No switch or flow matches "nothing-matches-this"' in html

    def test_the_meters(self, lab):
        store_read()
        _r, html = get(lab, "/v2/sdn/flows")
        meters = re.search(r'<section class="card sdn-meters".*?</section>', html, re.S).group(0)
        assert "meters supported on 1 of 1 switch" in meters
        assert "1,000 kbit/s, drop above" in meters and "1,200" in meters
        assert "Mercury&#39;s" in meters

    def test_the_granularity_note_where_flows_cannot_show_a_scan(self, lab):
        flows = [f for f in json.loads(next(e for e in WITH_PEER if e["path"] ==
                                             "/stats/flow/1")["body"])["1"]
                 if not set(f["match"]) - {"in_port", "dl_dst", "dl_src"}]
        lab["sessions"]["session"] = Captured(flows=flows)
        store_read()
        _r, html = get(lab, "/v2/sdn/flows")
        assert "Flows on <span class=\"mono\">0000000000000001</span> match L2 only " \
               "(eth_dst, eth_src, in_port)" in html
        assert "cannot show a per-port scan" in html


# ───────────────────────────────────────────────────────────────────────────── Settings

def _card(html):
    return re.search(r'<section class="card set-card sdn-set" id="sdn-card".*?</section>',
                     html, re.S).group(0)


def _form(**kw):
    out = {"name": "branch-ctl", "kind": "ryu", "url": BASE, "verify_tls": "on",
           "southbound": "", "own_cookies": "0", "loaded": "{}"}
    out.update(kw)
    return out


class TestTheSettingsCard:
    def test_drawn_per_network_with_each_driver_and_its_status(self, lab):
        _r, html = get(lab, "/v2/settings/network/Default")
        card = _card(html)
        assert "SDN controllers" in card and "network Default" in card
        assert "lab-controller" in card and "Ryu (ofctl_rest)" in card
        assert '<option value="ryu" selected>Ryu (ofctl_rest)</option>' in card
        assert '<option value="onos" disabled>ONOS (later: not built yet)</option>' in card
        assert '<option value="opendaylight" disabled>OpenDaylight (later: read-first, not ' \
               'built yet)</option>' in card
        assert '<option value="floodlight" disabled>Floodlight (unmaintained)</option>' in card
        _r, html = get(lab, "/v2/settings/network/Branch")
        card = _card(html)
        assert "network Branch" in card and "lab-controller" not in card, "C1841"

    def test_test_answers_in_place_with_its_receipt(self, lab):
        r = lab["client"].post("/v2/settings/network/Branch/sdn/test", data=_form())
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "Answered for" in html and BASE in html
        assert re.search(r'<input type="hidden" name="tested" value="\d+\.[0-9a-f]{64}">', html)
        lab["sessions"]["session"] = Down()
        html = lab["client"].post("/v2/settings/network/Branch/sdn/test", data=_form())\
            .get_data(as_text=True)
        assert "Couldn't connect to" in html and 'name="tested"' not in html

    def test_save_is_refused_until_test_answered_for_the_url_as_typed(self, lab):
        c = lab["client"]
        r = c.post("/v2/settings/network/Branch/sdn/save", data=_form())
        assert r.status_code == 409 and "Test connection has not answered for" in \
            r.get_data(as_text=True)
        html = c.post("/v2/settings/network/Branch/sdn/test", data=_form()).get_data(as_text=True)
        receipt = re.search(r'name="tested" value="([^"]+)"', html).group(1)
        r = c.post("/v2/settings/network/Branch/sdn/save",
                   data=_form(url="http://192.0.2.11:8080", tested=receipt))
        assert r.status_code == 409 and "answered for another URL" in r.get_data(as_text=True)
        assert C.connections("Branch")["state"] == "none", "nothing saved"
        r = c.post("/v2/settings/network/Branch/sdn/save",
                   data=_form(tested=receipt, password=PASSWORD))
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and r.headers["HX-Retarget"] == "#sdn-card"
        assert "Added branch-ctl" in html and PASSWORD not in html
        assert [x["name"] for x in C.connections("Branch")["connections"]] == ["branch-ctl"]
        assert "lab-controller" not in html, "Branch's own list (C1841)"

    def test_a_credential_is_typed_to_set_and_never_drawn(self, lab):
        c = lab["client"]
        html = c.post("/v2/settings/network/Branch/sdn/test", data=_form()).get_data(as_text=True)
        receipt = re.search(r'name="tested" value="([^"]+)"', html).group(1)
        c.post("/v2/settings/network/Branch/sdn/save",
               data=_form(tested=receipt, username="ctl-op", password=PASSWORD))
        for path in ("/v2/settings/network/Branch", "/v2/settings/network/Branch/sdn/edit/"
                     "branch-ctl", "/v2/sdn?list=Branch"):
            html = get(lab, path)[1]
            assert PASSWORD not in html and "ctl-op" not in html, path
        assert "a user and password set" in get(lab, "/v2/settings/network/Branch")[1]

    def test_edit_draws_its_values_and_keeps_its_name(self, lab):
        _r, html = get(lab, "/v2/settings/network/Default/sdn/edit/lab-controller")
        assert "Edit lab-controller" in html
        assert re.search(r'<input id="sdn-name" name="name" type="text" value="lab-controller" '
                         r'readonly', html)
        assert 'value="192.0.2.10:6653"' in html and 'type="password"' in html

    def test_a_save_from_a_form_drawn_before_another_change_is_refused(self, lab):
        c = lab["client"]
        html = get(lab, "/v2/settings/network/Default/sdn/edit/lab-controller")[1]
        loaded = re.search(r"name=\"loaded\" value='([^']*)'", html).group(1)
        C.save_connection("Default", {"name": "lab-controller", "kind": "ryu", "url": BASE,
                                      "southbound": "192.0.2.12:6653"}, actor="other")
        test = c.post("/v2/settings/network/Default/sdn/test",
                      data=_form(name="lab-controller", loaded=loaded)).get_data(as_text=True)
        receipt = re.search(r'name="tested" value="([^"]+)"', test).group(1)
        r = c.post("/v2/settings/network/Default/sdn/save",
                   data=_form(name="lab-controller", loaded=loaded, tested=receipt,
                              southbound="192.0.2.10:6653"))
        assert r.status_code == 409 and "changed since this form was drawn" in \
            r.get_data(as_text=True)

    def test_remove_says_what_survives_and_removes(self, lab):
        c = lab["client"]
        html = get(lab, "/v2/settings/network/Default/sdn/lab-controller/remove")[1]
        assert "Remove lab-controller from Default?" in html
        assert "Kept: the flow-intent records naming it (a history)" in html
        html = c.post("/v2/settings/network/Default/sdn/lab-controller/remove")\
            .get_data(as_text=True)
        assert "Removed lab-controller" in html
        assert C.connections("Default")["state"] == "none"
        assert F.intent("Default")["flows"], "the flow-intent records survive"
