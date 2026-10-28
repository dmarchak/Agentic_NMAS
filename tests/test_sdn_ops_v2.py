"""SDN's operations on v2 (routes/sdn_v2.py; PHASE8_PLAN 17.1 S8 to S10 and S16, boards
SdnResponse, SdnResponses and SdnFlowEdit): through the real app, the real connection, the
real Ryu driver and `tests.sdn_fakes.FakeRyu` seeded with Ryu's captured flow table.

- **Flows' editor**: the form opens in place; its preview draws the exact requests and the hash
  and the hidden ask the confirm carries back; the confirm (a verified person) applies, verifies
  and records; a moved hash sends nothing; a prerequisite is refused naming the field.
- **Responses**: a response awaiting a person is drawn with who chose its action (the
  catalogue's default, with no AI classification; tests/test_sdn_classify.py has the AI's); its
  preview is the plan's card; its confirm applies and closes it as confirmed; a dismissal needs
  its reason.
- **The mode and the loop**: AUTO on with a reason and an expiry, off at once; the loop started
  and stopped, each recorded.
- **The network's stage (C2009)**: its route refuses no reason, an unknown value and an
  unverified person, records who, from, to and why, and refuses a form drawn before a change;
  the SDN controllers card draws the stage and its form; the Mode card says the stage, draws
  Turn AUTO on disabled with its reason off lab (and the server refuses it, in words), and says
  AUTO is suspended when the network is marked otherwise after AUTO was turned on.
- **An announcement never takes an open card away (C2001)**: every operation card carries the
  marker the browser's hold reads; in a real browser, a preview survives two refreshes with
  its hash, Send works, the result holds with "Paused while you review this", and Show it now
  is busy on itself and redraws; with nothing open a refresh redraws at once.
"""
import json
import re
from html import unescape

import pytest

from modules.sdn import connections as C
from modules.sdn import flow_intent as F
from modules.sdn import loop as LP
from modules.sdn import modes as MD
from tests.sdn_fakes import FakeRyu
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture
from tests.test_sdn_flow_ops import captured_table

BASE = "http://192.0.2.10:8080"


@pytest.fixture
def lab(networks, monkeypatch):  # noqa: F811 - the fixture, used
    from modules.sdn import drivers

    fake = FakeRyu(BASE, flows={1: captured_table()})
    real = drivers.make

    def make(kind, connection, **kw):
        kw.setdefault("session", fake)
        kw.setdefault("sleep", lambda s: None)
        return real(kind, connection, **kw)

    monkeypatch.setattr(drivers, "make", make)
    monkeypatch.setattr("modules.sdn.flow_ops.COUNTER_INTERVAL", 0)
    C.save_connection("Default", {"name": "lab-controller", "kind": "ryu", "url": BASE},
                      actor="op@example.com")
    import app as A
    return {"client": A.app.test_client(), "fake": fake}


def mark_stage(client, stage, network="Default", reason="the course lab's network", loaded=""):
    """Mark *network*'s stage through its SDN controllers card's form (C2009)."""
    return client.post(f"/v2/settings/network/{network}/sdn/stage",
                       data={"stage": stage, "reason": reason, "loaded": loaded})


def form_fields(html):
    return {m.group(1): unescape(m.group(2)) for m in
            re.finditer(r'<input type="hidden" name="([a-z]+)" value="([^"]*)"', html)}


def test_the_editor_opens_in_place_and_its_preview_binds_the_requests(lab):
    c = lab["client"]
    html = c.get("/v2/sdn/flow/form?do=add&connection=lab-controller&dpid=0000000000000001"
                 "&list=Default").get_data(as_text=True)
    assert 'hx-post="/v2/sdn/flow/preview' in html and "Add a flow" in html
    r = c.post("/v2/sdn/flow/preview", data={
        "list": "Default", "do": "add", "connection": "lab-controller",
        "dpid": "0000000000000001", "priority": "250", "hard_timeout": "60",
        "match": "eth_type=0x0800, ipv4_src=198.51.100.9", "actions": "drop"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200, html
    assert "POST /stats/flowentry/add" in html and "Send 1 request to lab-controller" in html
    fields = form_fields(html)
    assert set(fields) >= {"list", "ask", "hash"} and len(fields["hash"]) == 64
    assert lab["fake"].writes == []
    r = c.post("/v2/sdn/flow/confirm", data=fields)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Done, verified" in html, html
    assert "testing traffic from the hosts is the operator" in html
    (rec,) = F.intent("Default", "lab-controller")["flows"]
    assert rec["match"]["ipv4_src"] == "198.51.100.9" and rec["actor"] == "test-person@example.invalid"


def test_a_moved_hash_sends_nothing(lab):
    c = lab["client"]
    html = c.post("/v2/sdn/flow/preview", data={
        "list": "Default", "do": "add", "connection": "lab-controller", "dpid": "0000000000000001",
        "priority": "250", "match": "in_port=3", "actions": "drop"}).get_data(as_text=True)
    fields = form_fields(html)
    fields["hash"] = "f" * 64
    r = c.post("/v2/sdn/flow/confirm", data=fields)
    assert r.status_code == 409 and "Nothing was sent" in r.get_data(as_text=True)
    assert lab["fake"].writes == []


def test_a_prerequisite_is_refused_naming_the_field(lab):
    r = lab["client"].post("/v2/sdn/flow/preview", data={
        "list": "Default", "do": "add", "connection": "lab-controller", "dpid": "0000000000000001",
        "priority": "200", "match": "in_port=1, eth_type=0x0800, tcp_dst=22", "actions": "drop"})
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 409 and "tcp_dst needs ip_proto 6" in html


def test_a_response_awaiting_a_person_previews_confirms_and_closes(lab):
    d = {"key": "k1", "rule": "scan", "title": "SDN scan", "network": "Default",
         "connection": "lab-controller", "dpid": 1, "dpid_hex": "0000000000000001",
         "source": "192.0.2.1", "targets": ["192.0.2.2"], "confidence": "high",
         "words": "192.0.2.1 reached 25 distinct destination ports"}
    row = LP.propose("Default", d, "drop_source", "low", why="HITL")
    c = lab["client"]
    html = unescape(c.get("/v2/sdn/responses?list=Default").get_data(as_text=True))
    assert "1 awaiting approval" in html
    assert "the catalogue's default for the rule, chosen in code (no AI classification)" in html
    assert "Preview the drop traffic from the source…" in html
    r = c.post(f"/v2/sdn/response/{row['id']}/preview", data={"list": "Default"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200, html
    fields = form_fields(html)
    ask = json.loads(fields["ask"])
    assert ask["response"] is True and ask["changes"][0]["flow"]["hard_timeout"] == 600
    r = c.post("/v2/sdn/response/confirm", data=fields)
    assert "Done, verified" in r.get_data(as_text=True)
    assert LP.awaiting("Default")["rows"] == []
    (op,) = F.operations("Default")["rows"]
    assert op["response"]["action"] == "drop_source" and op["mode"] == "hitl"


def test_a_dismissal_needs_its_reason(lab):
    row = LP.propose("Default", {"key": "k2", "rule": "flood"}, "rate_limit_source", "low",
                     why="HITL")
    c = lab["client"]
    r = c.post(f"/v2/sdn/response/{row['id']}/dismiss", data={"list": "Default", "reason": ""})
    assert r.status_code == 409 and "names its reason" in r.get_data(as_text=True)
    r = c.post(f"/v2/sdn/response/{row['id']}/dismiss",
               data={"list": "Default", "reason": "a known test"})
    assert r.status_code == 200 and LP.awaiting("Default")["rows"] == []


def test_auto_on_and_off_and_the_loop_started_and_stopped(lab, monkeypatch):
    c = lab["client"]
    # C2009: AUTO is turned on only on a network marked lab.
    assert mark_stage(c, "lab").status_code == 200
    r = c.post("/v2/sdn/mode", data={"list": "Default", "mode": "auto", "reason": "",
                                     "hours": "1", "risk": "low"})
    assert r.status_code == 409 and "recorded reason" in r.get_data(as_text=True)
    r = c.post("/v2/sdn/mode", data={"list": "Default", "mode": "auto",
                                     "reason": "lab 8 run", "hours": "1", "risk": "low"})
    assert r.status_code == 200 and MD.current("Default")["mode"] == "auto"
    assert "AUTO until" in unescape(r.get_data(as_text=True))
    r = c.post("/v2/sdn/mode", data={"list": "Default", "mode": "hitl"})
    assert r.status_code == 200 and MD.current("Default")["mode"] == "hitl"
    import threading
    gate = threading.Event()
    monkeypatch.setattr(LP, "run_pass", lambda network, **kw: gate.wait(5))
    r = c.post("/v2/sdn/loop", data={"list": "Default", "run": "start", "interval": "10"})
    assert r.status_code == 200 and LP.status("Default")["running"]
    r = c.post("/v2/sdn/loop", data={"list": "Default", "run": "stop"})
    gate.set()
    LP._jobs["Default"]["thread"].join(10)
    assert r.status_code == 200 and not LP.status("Default")["running"]


# ── C2009: the network's stage, set on its SDN controllers card, said on the Mode card ──────

GATE = ("AUTO is turned on only on a network marked lab until the AUTO production-readiness "
        "gate (PHASE8_PLAN 17.7) is complete")
CARD = "/v2/settings/network/Default/sdn"


def _stage_rows():
    import os

    from modules.config import list_data_path
    path = os.path.join(list_data_path("Default"), "settings_record.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [r for r in (json.loads(x) for x in fh if x.strip())
                if r.get("kind") == "network_stage"]


def _turn_on_button(html):
    """The Turn AUTO on button's opening tag."""
    end = html.index("Turn AUTO on</span>")
    return html[html.rindex("<button", 0, end):end]


@pytest.mark.parametrize("data,words", [
    ({"stage": "lab", "reason": ""}, "with a recorded reason, and none was given"),
    ({"stage": "staging", "reason": "r"}, "a network's stage is lab, pilot, production, not "
                                          "'staging'"),
], ids=["no-reason", "unknown-value"])
def test_the_stage_route_refuses_no_reason_and_an_unknown_value(lab, data, words):
    r = mark_stage(lab["client"], **data)
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 409 and "Not done:" in html and words in html
    assert 'id="sdn-card"' in html, "the card drawn again, the refusal in it"
    assert MD.stage("Default")["state"] == "not_marked" and _stage_rows() == []


@pytest.mark.real_identity
def test_the_stage_route_refuses_an_unverified_person(lab):
    r = mark_stage(lab["client"], "lab")
    assert r.status_code in (401, 403), r.status_code
    assert MD.stage("Default")["state"] == "not_marked" and _stage_rows() == []


def test_the_stage_route_records_who_from_to_and_why_and_redraws_the_card(lab):
    from tests.conftest import TEST_PERSON

    c = lab["client"]
    r = mark_stage(c, "production", reason="carries real traffic")
    html = unescape(r.get_data(as_text=True))
    assert r.status_code == 200
    assert "Marked Default production</strong> (was not marked)" in html
    assert "Default is marked production." in html
    assert [(x["before"], x["after"], x["actor"], x["reason"]) for x in _stage_rows()] == \
        [("", "production", TEST_PERSON, "carries real traffic")]
    # A form drawn before that change is refused, naming both.
    r = mark_stage(c, "lab", loaded="")
    assert r.status_code == 409
    assert ("Default's stage moved since the card drew it (drawn: not marked; now: "
            "production)") in unescape(r.get_data(as_text=True))
    assert MD.stage("Default")["stage"] == "production"


def test_the_settings_card_draws_the_stage_and_its_form(lab):
    html = unescape(lab["client"].get(CARD).get_data(as_text=True))
    stage = html[html.index('id="sdn-stage"'):html.index('class="sdn-set-body"')]
    assert "Default is not marked." in stage
    assert re.findall(r'<option value="([a-z]+)"', stage) == ["lab", "pilot", "production"]
    assert 'name="reason" required' in stage and 'name="loaded" value=""' in stage
    assert "/v2/settings/network/Default/sdn/stage" in stage and "Saving…" in stage


def test_the_mode_card_says_the_stage_and_draws_turn_auto_on_disabled_off_lab(lab):
    c = lab["client"]
    page = unescape(c.get("/v2/sdn/responses?list=Default").get_data(as_text=True))
    assert ("This network is not marked; AUTO is turned on only on a network marked lab until "
            "the AUTO production-readiness gate is complete") in page
    assert "#sdn-stage" in page, "the line links to the stage"
    button = _turn_on_button(page)
    assert " disabled" in button
    assert 'data-refused="Not available: this network is not marked lab"' in button
    # The server refuses it anyway, naming the stage and the gate.
    r = c.post("/v2/sdn/mode", data={"list": "Default", "mode": "auto", "reason": "lab 8 run",
                                     "hours": "1", "risk": "low"})
    assert r.status_code == 409
    assert f"{GATE}; Default is not marked" in unescape(r.get_data(as_text=True))
    assert MD.current("Default")["mode"] == "hitl"
    # Marked lab: the line says so, and the button is pressable.
    assert mark_stage(c, "lab").status_code == 200
    page = unescape(c.get("/v2/sdn/responses?list=Default").get_data(as_text=True))
    assert "This network is marked lab." in page
    assert " disabled" not in _turn_on_button(page)
    # AUTO on, then the network marked production: suspended, said.
    assert c.post("/v2/sdn/mode", data={"list": "Default", "mode": "auto",
                                        "reason": "lab 8 run", "hours": "1",
                                        "risk": "low"}).status_code == 200
    assert mark_stage(c, "production", loaded="lab").status_code == 200
    page = unescape(c.get("/v2/sdn/responses?list=Default").get_data(as_text=True))
    assert "AUTO is suspended:" in page and "This network is marked production" in page
    assert MD.decide("Default", "low")["auto"] is False


# ── C2001: an announcement never takes an open preview away (in a real browser) ───────────

READY = ("return !!window.htmx && !!document.getElementById('sdn') && "
         "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')")
REVIEW_WORDS = "Paused while you review this: newer data is waiting."


def _announce_sdn(b, times=1):
    """The SDN reader's or the loop's announcement, as it arrives (`nmas:sdn` on the body),
    *times* times; returns once each one's redraw has come back to the page (its swap asked)."""
    b.js("window.__sdnSwaps = window.__sdnSwaps || 0; if (!window.__sdnCounting) {"
         " window.__sdnCounting = true; document.body.addEventListener('htmx:beforeSwap',"
         " function (e) { if (e.detail.target && e.detail.target.id === 'sdn')"
         " window.__sdnSwaps++; }); } return 1")
    for _ in range(times):
        before = b.js("return window.__sdnSwaps")
        b.js("document.body.dispatchEvent(new CustomEvent('nmas:sdn')); return 1")
        b.wait_for(f"return window.__sdnSwaps > {before}", 15)


def test_every_operation_card_holds_a_live_redraw(lab):
    """The marker the browser's hold reads (`data-holds-live`, static/js/nmas_v2.js
    `holdReason`) is on the preview, its result and the flow editor, each drawn in place."""
    c = lab["client"]
    row = LP.propose("Default", {"key": "k-mark", "rule": "scan", "network": "Default",
                                 "connection": "lab-controller", "dpid": 1,
                                 "dpid_hex": "0000000000000001", "source": "192.0.2.1",
                                 "targets": ["192.0.2.2"]}, "drop_source", "low", why="HITL")
    preview = c.post(f"/v2/sdn/response/{row['id']}/preview", data={"list": "Default"})\
        .get_data(as_text=True)
    result = c.post("/v2/sdn/response/confirm", data=form_fields(preview)).get_data(as_text=True)
    editor = c.get("/v2/sdn/flow/form?do=add&connection=lab-controller&dpid=0000000000000001"
                   "&list=Default").get_data(as_text=True)
    for name, html in (("preview", preview), ("result", result), ("editor", editor)):
        assert re.search(r'class="card sdn-op[^"]*"[^>]* data-holds-live="review"', html), name


def test_an_open_preview_survives_two_refreshes_and_its_send_works(lab):
    """The row's test (C2001): open a preview, let two refreshes pass, the preview and its hash
    are still there and Send works; with no card open, a refresh redraws at once; after Send the
    result stays until Show it now (busy on itself), which redraws."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as A

    row = LP.propose("Default", {
        "key": "k-held", "rule": "scan", "title": "SDN scan", "network": "Default",
        "connection": "lab-controller", "dpid": 1, "dpid_hex": "0000000000000001",
        "source": "192.0.2.1", "targets": ["192.0.2.2"], "confidence": "high",
        "words": "192.0.2.1 reached 25 distinct destination ports"}, "drop_source", "low",
        why="HITL")
    slot = f"#sdn-rp-{row['id']}"
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/sdn/responses?list=Default"))
            b.wait_for(READY, 15)
            # Nothing open: a refresh redraws the region at once.
            b.js("window.__oldSdn = document.getElementById('sdn'); return 1")
            _announce_sdn(b)
            b.wait_for("return document.getElementById('sdn') !== window.__oldSdn && "
                       "!document.getElementById('sdn').getAttribute('data-held')", 15)
            b.wait_for(READY, 15)
            # The preview, opened in place.
            b.js(f"document.querySelector('form[hx-post*=\"/response/{row['id']}/preview\"]"
                 " button[type=submit]').click(); return 1")
            b.wait_for(f"return !!document.querySelector('{slot} input[name=hash]')", 15)
            drawn = b.js(f"return document.querySelector('{slot} input[name=hash]').value")
            # Two refreshes pass.
            _announce_sdn(b, times=2)
            mid = b.js(f"var s = document.querySelector('{slot}'), h = s && s.querySelector("
                       "'input[name=hash]'), n = s && s.querySelector('.held-note');"
                       "return {hash: h ? h.value : null, held: document.getElementById('sdn')"
                       ".getAttribute('data-held'), note: n ? n.textContent : '',"
                       " send: !!(s && s.querySelector('.sdn-op-confirm button[type=submit]'))}")
            assert mid == {"hash": drawn, "held": "1", "note": REVIEW_WORDS + " Show it now",
                           "send": True}, mid
            # Send still works.
            b.js(f"document.querySelector('{slot} .sdn-op-confirm button[type=submit]').click();"
                 " return 1")
            b.wait_for(f"var s = document.querySelector('{slot}');"
                       "return !!s && s.textContent.indexOf('Done, verified') >= 0", 20)
            b.wait_for(f"var n = document.querySelector('{slot} .held-note');"
                       f"return !!n && n.textContent.indexOf('{REVIEW_WORDS}') >= 0", 10)
            # Show it now: busy on itself at once, then the newer region, no card held.
            pressed = b.js(f"var b = document.querySelector('{slot} .held-resume'); b.click();"
                           "return {disabled: b.disabled, busy: b.getAttribute('aria-busy'),"
                           " words: b.textContent}")
            b.wait_for("var r = document.getElementById('sdn');"
                       "return !!r && !r.getAttribute('data-held') && "
                       "!r.querySelector('.sdn-op')", 15)
            after = b.js("return document.getElementById('sdn').textContent"
                         ".indexOf('No response is awaiting a person') >= 0")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert pressed == {"disabled": True, "busy": "true", "words": "Showing…"}, pressed
    assert after is True
    assert LP.awaiting("Default")["rows"] == []
    (op,) = F.operations("Default")["rows"]
    assert op["mode"] == "hitl" and op["response"]["action"] == "drop_source"
