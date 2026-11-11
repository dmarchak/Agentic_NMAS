"""SDN › Switches (board docs/boards/lab9-sdn.html, artboard A; Lab 9 Objective 2; C2902): the
verify view from stored reads, Configure from NetBox…'s preview, confirm and result, the
templates card's Confirm against a capture…, and Verify now.

The result card and the record it leaves (the operator on the lab's hardware, 2026-11-10): the
result lists each switch with what was sent, each value before and after, Verify with how long
it took and the outcome, "already as intended, nothing sent" where nothing changed, and what it
was built from, each value with where it came from; History's row names the switch in its
Device column and says the same. And in a real browser: with a live redraw held, the card's
"Paused while you review this" is one thin bar and every row is drawn at its full height.

The lab is tests/test_openflow_vendor.py's: the lab's NSOT export committed in a temporary
repository, its switches answered by their 2026-11-06 masked captures through the real
`open_ssh` and its guard, the controller a fake driver's switch list. Every test asserts on what
the screen drew AND on state: the record kept, what each switch was sent, what was committed, or
that no session was opened at all.
"""

import re
from html import unescape

import pytest

from modules import csp
from modules.sdn import flow_intent
from modules.sdn import openflow_config as OC
from modules.sdn import openflow_templates as T
from tests.test_openflow_config import Controller
from tests.test_openflow_vendor import (ACTOR, DPIDS, LIST, Switch, SwitchConn, _commit_export,
                                        _confirm, _session, net,  # noqa: F401 - the fixtures
                                        netmiko_fake)

BASE = "/v2/sdn/switches"


@pytest.fixture
def tab(net, monkeypatch):  # noqa: F811 - the fixture, used
    import app as A
    sha = _commit_export()
    listed = {"dpids": [DPIDS["arista-sw1"], 3, 999]}
    monkeypatch.setattr("modules.sdn_page.stored", lambda network: {
        "state": "ok", "value_at": "2026-11-10T03:00:00Z", "failed": "",
        "value": {"controllers": [{"name": "ryu", "switches": [
            {"dpid": d, "dpid_hex": f"{d:016x}"} for d in listed["dpids"]]}]}})
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == LIST)
    opened = []

    def session(dev, fn):
        opened.append(dev["hostname"])
        return _session(dev, fn)
    monkeypatch.setattr("modules.connection.with_temp_connection", session)
    ctl = Controller(lambda: listed["dpids"])
    monkeypatch.setattr(OC, "connection_name", lambda network, values, given="": "ryu")
    monkeypatch.setattr("modules.sdn.connections.driver_for",
                        lambda network, name, **kw: {"ok": True, "driver": ctl})
    monkeypatch.setattr(OC, "VERIFY_PAUSE", 0.0)
    return {"client": A.app.test_client(), "sha": sha, "opened": opened, "listed": listed,
            "ctl": ctl}


def _record(device, outcome, sha, dpid_hex=""):
    flow_intent.record_operation(LIST, {
        "id": f"ofcfg-{device}", "actor": ACTOR, "at": "2026-11-10T02:00:00Z",
        "outcome": outcome, "dpid_hex": dpid_hex, "export_sha256": sha,
        "verify": {"checks": [{"name": "x", "state": "pass", "words": "the read-back"}]},
        "response": {"kind": "openflow_config", "device": device, "template": "arista_eos"}})


def _groups(html: str) -> dict:
    out = {}
    for m in re.finditer(r'<tbody class="of-group" data-state="([a-z_]+)">(.*?)</tbody>', html,
                         re.S):
        out[m.group(1)] = re.findall(r'data-switch="([^"]+)"', m.group(2))
    return out


def _fields(html: str) -> dict:
    out = {}
    for m in re.finditer(r'<input type="hidden" name="([a-z_0-9]+)" value="([^"]*)"', html):
        out.setdefault(m.group(1), []).append(unescape(m.group(2)))
    return out


# --------------------------------------------------------------------------- the view

class TestTheVerifyView:
    def test_every_marked_switch_is_drawn_grouped_by_state_from_stored_reads(self, tab):
        _record("arista-sw1", "verified", tab["sha"], f"{DPIDS['arista-sw1']:016x}")
        _record("procurve-sw", "rolled_back", tab["sha"])
        r = tab["client"].get(f"{BASE}?list={LIST}")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert _groups(html) == {"differs": ["procurve-sw"],
                                 "not_configured": ["arista-sw2", "ovs2"],
                                 "connected": ["arista-sw1", "ovs1"]}
        text = unescape(html)
        assert "<strong>5</strong> marked for OpenFlow in NetBox" in text
        assert "<strong>1</strong> seen by the controller, not in NetBox" in text
        assert "00000000000003e7" in text and 'aria-current="page">Switches</a>' in text
        assert "IPv4 controller only" in text and "nmas:sdn from:body" in html
        # The effect: drawing the view opened no session to any switch and recorded nothing.
        assert tab["opened"] == [] and tab["ctl"].reads == 0
        assert len(flow_intent.operations(LIST)["rows"]) == 2

    def test_an_export_committed_since_a_configuration_draws_it_as_differing(self, tab):
        _record("arista-sw1", "verified", "f" * 64, f"{DPIDS['arista-sw1']:016x}")
        html = tab["client"].get(f"{BASE}/view?list={LIST}").get_data(as_text=True)
        assert "arista-sw1" in _groups(html)["differs"]
        assert "not the committed one" in unescape(html)
        assert tab["opened"] == []

    @pytest.mark.parametrize("query,want", [
        ("state=not_configured", {"not_configured": ["arista-sw1", "arista-sw2", "ovs2",
                                                     "procurve-sw"]}),
        # ovs2 is not in the network's inventory, so it has no driver and no platform.
        ("platform=ovs", {"connected": ["ovs1"]}),
        ("q=arista-sw2", {"not_configured": ["arista-sw2"]}),
        ("q=0000000000000003", {"connected": ["ovs1"]})])
    def test_search_and_the_two_filters_narrow_the_rows(self, tab, query, want):
        html = tab["client"].get(f"{BASE}/view?list={LIST}&{query}").get_data(as_text=True)
        assert _groups(html) == want
        assert tab["opened"] == []

    def test_no_committed_export_names_the_export_card_and_draws_no_switch(self, tab, net):
        from modules.nsot.repo import git
        git(str(net / "config_repo"), "rm", "-q", "nsot/export.json")
        git(str(net / "config_repo"), "commit", "-q", "-m", "gone")
        html = unescape(tab["client"].get(f"{BASE}?list={LIST}").get_data(as_text=True))
        assert "has no committed NSOT export" in html and "Export it from NetBox on SDN › Apps" \
            in html
        assert _groups(html) == {} and tab["opened"] == []


# --------------------------------------------------------------------------- configure

class TestConfigureFromNetBox:
    def test_previewed_confirmed_by_hash_sent_verified_and_recorded(self, tab, monkeypatch):
        _confirm(monkeypatch, "arista-sw1", "arista_eos")
        sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n")
        c = tab["client"]
        r = c.post(f"{BASE}/configure/preview", data={"list": LIST, "device": "arista-sw1"})
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 200 and "Configure OpenFlow on 1 switch" in html
        assert "   controller tcp:192.0.2.1:6653" in html and "no openflow" in html
        assert tab["sha"][:7] in html and sw.sets == []
        f = _fields(r.get_data(as_text=True))
        done = c.post(f"{BASE}/configure/confirm", data={"list": LIST, "hash": f["hash"][0],
                                                         "plan": f["plan"]})
        out = unescape(done.get_data(as_text=True))
        assert done.status_code == 200 and "Configured 1 of 1" in out and "verified" in out
        assert "not saved to the startup configuration" in out
        assert len(sw.sets) == 1 and sw.sets[0][0] == "interface Ethernet18" and not sw.saved
        (row,) = flow_intent.operations(LIST)["rows"]
        assert row["outcome"] == "verified" and row["response"]["device"] == "arista-sw1"
        assert row["export_sha256"] == tab["sha"] and row["actor"]

    def test_an_aristas_preview_holds_one_bind_line_and_names_the_read_back(self, tab,
                                                                          monkeypatch):
        """C2996, C2779: the preview shows the exact line, and what Verify reads back."""
        _confirm(monkeypatch, "arista-sw1", "arista_eos")
        sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n")
        html = unescape(tab["client"].post(f"{BASE}/configure/preview", data={
            "list": LIST, "device": "arista-sw1"}).get_data(as_text=True))
        assert html.count("   bind interface ") == 1 and "   bind interface Et18-19\n" in html
        assert sw.sets == [] and not sw.saved, "a preview sends the switch nothing"
        assert ("the controller's switch list holds its datapath id within 12 s; the switch's "
                "own show openflow lists the program's bound interfaces</dd>") in html

    def test_a_switch_on_a_draft_template_is_previewed_as_not_sent(self, tab):
        sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n")
        r = tab["client"].post(f"{BASE}/configure/preview",
                               data={"list": LIST, "device": "arista-sw1"})
        html = unescape(r.get_data(as_text=True))
        assert "Nothing to configure" in html and "Not sent" in html
        assert "its template arista_eos is a draft" in html and 'name="plan"' not in html
        assert sw.sets == [] and flow_intent.operations(LIST)["rows"] == []

    def test_a_confirm_not_bound_to_the_preview_is_refused_naming_both(self, tab, monkeypatch):
        _confirm(monkeypatch, "arista-sw1", "arista_eos")
        sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n")
        c = tab["client"]
        f = _fields(c.post(f"{BASE}/configure/preview",
                           data={"list": LIST, "device": "arista-sw1"}).get_data(as_text=True))
        r = c.post(f"{BASE}/configure/confirm", data={"list": LIST, "hash": "0" * 64,
                                                      "plan": f["plan"]})
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 409 and "Nothing was configured" in html
        assert "000000000000" in html and f["hash"][0][:12] in html
        assert sw.sets == [] and flow_intent.operations(LIST)["rows"] == []

    def test_a_switch_that_moved_since_the_preview_is_refused_by_itself(self, tab, monkeypatch):
        _confirm(monkeypatch, "arista-sw1", "arista_eos")
        sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n")
        c = tab["client"]
        f = _fields(c.post(f"{BASE}/configure/preview",
                           data={"list": LIST, "device": "arista-sw1"}).get_data(as_text=True))
        sw.running = "hostname x\ninterface Ethernet18\n   no lldp transmit\n   no lldp receive\n"
        out = unescape(c.post(f"{BASE}/configure/confirm", data={
            "list": LIST, "hash": f["hash"][0], "plan": f["plan"]}).get_data(as_text=True))
        assert "Configured 0 of 1" in out and "moved since the preview" in out
        assert sw.sets == []

    def _configure(self, tab, monkeypatch, devices):
        """Preview then confirm *devices* through the two routes; the result card's text."""
        _confirm(monkeypatch, "arista-sw1", "arista_eos")
        c = tab["client"]
        f = _fields(c.post(f"{BASE}/configure/preview", data={
            "list": LIST, "device": devices}).get_data(as_text=True))
        done = c.post(f"{BASE}/configure/confirm", data={"list": LIST, "hash": f["hash"][0],
                                                         "plan": f["plan"]})
        assert done.status_code == 200
        return unescape(done.get_data(as_text=True))

    def test_the_result_lists_each_switch_sent_before_and_after_verify_and_source(
            self, tab, monkeypatch):
        """arista-sw1 blank (its whole layer sent) and arista-sw2, managed over IPv6, as
        captured (nothing to change): a row each, and the record keeps what the card says."""
        from modules.nsot import export as X
        blank = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n")
        same = SwitchConn.at["2001:db8::6"] = Switch("arista-sw2.txt")
        tab["listed"]["dpids"] = [DPIDS["arista-sw1"], DPIDS["arista-sw2"]]
        out = self._configure(tab, monkeypatch, ["arista-sw1", "arista-sw2"])
        assert "Configured 2 of 2" in out
        rows = dict(re.findall(
            r'<tbody class="of-result-row" data-switch="([^"]+)">(.*?)</tbody>', out, re.S))
        assert sorted(rows) == ["arista-sw1", "arista-sw2"]
        sent = rows["arista-sw1"]
        # What was sent, and each value before and after.
        assert "11 lines" in sent and "   controller tcp:192.0.2.1:6653" in sent
        assert 'controllers</span>: none → tcp:192.0.2.1:6653' in sent
        assert 'bound</span>: none → Ethernet18, Ethernet19' in sent
        assert 'enabled</span>: no → yes' in sent
        # Verify, with how long it took, its checks' words under the record's details.
        assert re.search(r"3 of 3 checks passed in \d+\.\d s", sent)
        assert "<summary>Details for the record</summary>" in sent
        # What it was built from: the export and its commit as links, each value's origin.
        commit = X.last_commit(LIST)["commit"]
        assert f'href="/v2/sdn/apps?list={LIST}#nsot-export"' in sent
        assert f"NSOT export <span class=\"mono\">{tab['sha'][:7]}</span>" in sent
        assert f"/v2/history?commit={commit}" in sent and f">{commit[:7]}</span>" in sent
        assert ("controller 192.0.2.1:6653 from NetBox Service 'openflow' on controller (its "
                "device's primary IPv4 address)") in sent
        assert ("version 1.3, transport tcp, fail_mode secure from the device's config context "
                "(key openflow)") in sent
        assert "ports Ethernet18, Ethernet19 from interfaces tagged openflow" in sent
        # Nothing changed on the second: said so, and nothing was sent to it.
        kept = rows["arista-sw2"]
        assert "already as intended, nothing sent" in kept and "no value changed" in kept
        assert 'class="of-change"' not in kept and "What was sent" not in kept
        assert len(blank.sets) == 1 and same.sets == []
        # The record keeps the source and the changes the card drew.
        by = {r["response"]["device"]: r for r in flow_intent.operations(LIST)["rows"]}
        one = by["arista-sw1"]
        assert one["source"]["export_sha256"] == tab["sha"]
        assert one["source"]["export_commit"] == commit
        assert {"value": "controllers", "before": "none",
                "after": "tcp:192.0.2.1:6653"} in one["changes"]
        assert {"value": "ports", "is": "Ethernet18, Ethernet19",
                "from": "interfaces tagged openflow"} in one["source"]["origins"]
        assert by["arista-sw2"]["changes"] == [] and by["arista-sw2"]["sent"] == []
        assert isinstance(one["verify"]["seconds"], float) and one["verify"]["at"]

    def test_history_names_the_switch_and_says_what_it_was_built_from(self, tab, monkeypatch):
        """The record a configure leaves, read on History: the switch in the Device column,
        one readable line, the source and each value before and after in the row, and the
        identifiers under its details."""
        from modules.nsot import export as X
        SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n")
        self._configure(tab, monkeypatch, ["arista-sw1"])
        r = tab["client"].get(f"/v2/history?kind=sdn&list={LIST}")
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 200 and html.count('data-kind="sdn"') == 1
        # The one row: from its opening tag to the list's foot.
        start = html.index('data-kind="sdn"')
        row = html[start:html.index('<div class="tl-foot"', start)]
        summary = row.split("</summary>", 1)[0]
        assert re.search(r'<span class="hist-dev">\s*arista-sw1\s*</span>', summary), summary
        assert "fleet" not in summary
        assert "OpenFlow configuration on arista-sw1: 11 lines sent, verified" in summary
        # No identifier in the one line: the datapath sits under the record's details.
        dpid = f"{DPIDS['arista-sw1']:016x}"
        assert dpid not in summary
        body = row.split("</summary>", 1)[1]
        assert "<summary>Details for the record</summary>" in body
        assert body.index("Details for the record") < body.index(dpid)
        commit = X.last_commit(LIST)["commit"]
        assert f'href="/v2/sdn/apps?list={LIST}#nsot-export"' in body
        assert f"/v2/history?commit={commit}" in body
        assert "ports Ethernet18, Ethernet19 from interfaces tagged openflow" in body
        assert 'controllers</span>: none → tcp:192.0.2.1:6653' in body
        assert re.search(r"Verify: 3 of 3 checks passed in \d+\.\d s", body)
        # The commit's link opens that commit's own row on History.
        linked = unescape(tab["client"].get(
            f"/v2/history?commit={commit}&since=&list={LIST}").get_data(as_text=True))
        assert "NSOT export: " in linked and "No row of commit" not in linked
        # And the switch's own History draws its configuration.
        from modules import history_sources as H
        from modules.nsot import listref
        (mine,) = H.sdn_operations({"device": "arista-sw1", "ref": listref.resolve(LIST),
                                    "limit": 50, "since": None, "until": None,
                                    "members": None})["events"]
        assert mine["devices"] == ["arista-sw1"]
        assert H.sdn_operations({"device": "ovs1", "ref": listref.resolve(LIST), "limit": 50,
                                 "since": None, "until": None, "members": None})["events"] == []


# --------------------------------------------------------------------------- in a browser

#: A card's own measurements: the paused note's height, and every box inside the card that
#: scrolls its content vertically (more content than its own height shows).
CARD_JS = """
var card = document.querySelector(arguments[0]);
var note = card.querySelector(':scope > .held-note');
var cut = [], all = card.querySelectorAll('*');
for (var i = 0; i < all.length; i++) {
  var e = all[i];
  if (e.scrollHeight > e.clientHeight + 1 && getComputedStyle(e).overflowY !== 'visible')
    cut.push((e.className || e.tagName) + ' shows ' + e.clientHeight + ' of ' + e.scrollHeight);
}
return {note: note ? Math.round(note.getBoundingClientRect().height) : -1, cut: cut,
        card: Math.round(card.getBoundingClientRect().height)};
"""
#: The note is one line of 12 px words and a small button (31 px measured, 2026-11-10); a
#: second line at a narrow width is still under this.
NOTE_BAR = 64
SETTLED = ("return !!window.htmx && !document.querySelector("
           "'.htmx-swapping, .htmx-settling, .htmx-request')")


def held_card(b, card):
    """An SDN announcement arriving while *card* is open: the redraw is held and the card
    says so. The card's measurements (`CARD_JS`) once the note is drawn."""
    b.wait_for(SETTLED, 20)
    b.js("document.body.dispatchEvent(new CustomEvent('nmas:sdn')); return 1")
    b.wait_for(f"return !!document.querySelector('{card} > .held-note')", 15)
    b.wait_for(SETTLED, 20)
    return b.js(CARD_JS, card)


def assert_drawn_whole(got, where):
    """The operator's two sentences (2026-11-10): the note "must be one thin inline bar", and
    "Draw every row at full height, with no inner scroll"."""
    assert 0 < got["note"] <= NOTE_BAR, (where, got)
    assert got["cut"] == [], (where, got)


def test_a_held_preview_and_result_draw_every_row_and_the_note_as_one_thin_bar(tab,
                                                                              monkeypatch):
    """In a real browser, at 1280: Configure from NetBox… on one blank switch, an announcement
    held on the preview and again on the result. Measured before the fix (2026-11-10): the
    note stood 114 px tall over the result and its table showed 44 px of 127, the headings
    alone."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the route tests above still run")
    import app as A

    _confirm(monkeypatch, "arista-sw1", "arista_eos")
    sw = SwitchConn.at["192.0.2.2"] = Switch("arista-sw1.txt", running="hostname x\n")
    tab["listed"]["dpids"] = [DPIDS["arista-sw1"]]
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 900})
            b.go(srv.url(f"{BASE}?list={LIST}"))
            b.wait_for(SETTLED, 20)
            b.click("input[name=device][value=arista-sw1]")
            b.click("button[form=of-config-form]")
            b.wait_for("return !!document.querySelector('#of-config-op input[name=hash]')", 60)
            preview = held_card(b, "#of-config-op")
            b.click("#of-config-op .sdn-op-confirm button[type=submit]")
            b.wait_for("return !!document.querySelector('#of-config-op .table-wrap table')", 60)
            result = held_card(b, "#of-config-op")
            rows = b.js("var t = document.querySelector('#of-config-op .table-wrap');"
                        "var r = t.querySelector('tbody tr').getBoundingClientRect();"
                        "var w = t.getBoundingClientRect();"
                        "var last = t.querySelector('tbody tr td:last-child')"
                        ".getBoundingClientRect();"
                        "return {row: r.bottom <= w.bottom + 1 && r.height > 0,"
                        " fits: t.scrollWidth <= t.clientWidth + 1 && last.right <= w.right + 1,"
                        " words: t.querySelector('tbody').textContent}")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert_drawn_whole(preview, "the preview")
    assert_drawn_whole(result, "the result")
    # The switch's row is inside the table's box, not behind its edge; and at this width the
    # table fits its card, its last column (the outcome) in view with no sideways scroll.
    assert rows["row"] and "arista-sw1" in rows["words"] and "11 lines" in rows["words"]
    assert rows["fits"], rows
    assert len(sw.sets) == 1, "the confirm pressed in the browser sent the program once"


# --------------------------------------------------------------------------- the templates card

class TestTheTemplatesCard:
    def _capture(self, monkeypatch):
        from modules import discovery
        from modules.nsot import reads
        monkeypatch.setattr("modules.commands.run_device_command",
                            lambda conn, c, **kw: "openflow\n   no shutdown\n")
        r = reads.run(LIST, ["arista-sw1"], ["show running-config"], ACTOR,
                      session=lambda dev, fn: fn(None))
        return discovery.capture_name("arista-sw1", "show running-config", r["id"])

    def test_confirm_against_a_capture_commits_bound_to_both_hashes(self, tab, net, monkeypatch):
        c = tab["client"]
        before = unescape(c.get(f"{BASE}?list={LIST}").get_data(as_text=True))
        assert "no capture of a Arista EOS device on lab9" in before
        name = self._capture(monkeypatch)
        page = c.get(f"{BASE}?list={LIST}").get_data(as_text=True)
        assert f'<option value="{name}">' in page
        r = c.post(f"{BASE}/template/preview", data={"list": LIST, "template": "arista_eos",
                                                     "capture": name})
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 200 and "Confirm arista_eos against a capture" in html
        assert "   bind interface {ports.one_line}" in html
        assert "openflow\n   no shutdown" in html
        f = _fields(r.get_data(as_text=True))
        assert f["template_sha256"] == [T.sha256("arista_eos")]
        done = c.post(f"{BASE}/template/confirm", data={k: v[0] for k, v in f.items()})
        assert "Confirmed arista_eos" in done.get_data(as_text=True)
        s = T.status(LIST, "arista_eos")
        assert s["status"] == T.CONFIRMED and s["capture"] == name
        from modules.nsot.repo import git
        _rc, message, _ = git(str(net / "config_repo"), "log", "-1", "--format=%B")
        assert "OpenFlow template confirmed: arista_eos" in message and "Actor:" in message

    def test_a_template_changed_since_the_preview_commits_nothing(self, tab, monkeypatch):
        name = self._capture(monkeypatch)
        c = tab["client"]
        f = _fields(c.post(f"{BASE}/template/preview", data={
            "list": LIST, "template": "arista_eos", "capture": name}).get_data(as_text=True))
        f["template_sha256"] = ["e" * 64]
        r = c.post(f"{BASE}/template/confirm", data={k: v[0] for k, v in f.items()})
        html = unescape(r.get_data(as_text=True))
        assert r.status_code == 409 and "eeeeeeeeeeee" in html and "nothing was committed" in html
        assert T.status(LIST, "arista_eos")["status"] == T.DRAFT


# --------------------------------------------------------------------------- verify now

class TestVerifyNow:
    def test_where_the_readers_do_not_run_it_says_so(self, tab):
        r = tab["client"].post(f"{BASE}/verify", data={"list": LIST})
        assert r.status_code == 409 and "Couldn't read now" in r.get_data(as_text=True)
        assert tab["ctl"].reads == 0

    def test_it_asks_the_sdn_reader_to_read_now(self, tab, monkeypatch):
        asked = []
        monkeypatch.setattr("modules.reader_job.running", lambda name: True)
        monkeypatch.setattr("modules.reader_job.request_run",
                            lambda reader, by, **kw: asked.append(reader.name) or
                            {"started": True, "run": "x"})
        r = tab["client"].post(f"{BASE}/verify", data={"list": LIST})
        assert r.status_code == 200 and "Reading the controllers now" in r.get_data(as_text=True)
        assert asked == ["sdn-controllers"] and tab["opened"] == []
