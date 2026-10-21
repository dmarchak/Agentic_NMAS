"""C459: a live redraw never replaces what a person is editing, and a redraw never flashes a raw
time (the operator, 2026-10-05: on Needs attention, each refresh closed the open Acknowledge
form and took the cursor, and "s3 · since 1 min ago · grafana" flashed to other text and back).

In a real browser: open Acknowledge…, type a reason, fire the live update the way a reader's
announcement arrives (`nmas:acknowledgements` on the body), and the form is still open, the
text and the focus still there, and the row says newer data is waiting. Cancel, and the held
redraw happens. Without a browser: `stamp()` draws the same age words the script does, so a
fragment's first paint is never the ISO time.
"""

import pytest

from tests.test_device_v2 import lab  # noqa: F401 (the fixture)
from tests.test_swaps_in_a_browser import READY, SETTLED, served  # noqa: F401

#: C1522: its tests write reader stores, or wake readers that do; each test keeps them
#: in its own folder.
pytestmark = pytest.mark.usefixtures("reader_stores_in_tmp")

ROW = {"id": "grafana:s3:discards", "level": "warning", "what": "Interface output discards",
       "source": "grafana", "since": "2026-10-05T02:00:00Z", "devices": ["s3"], "action": {},
       "clears": "when the alert stops firing, or acknowledged", "clears_at": None,
       "cause": "", "operands": [], "attached": [], "read_at": "2026-10-05T02:01:00Z",
       "acknowledge": True, "event": "e-1"}


@pytest.fixture
def needs_one_ack(monkeypatch):
    from routes import v2
    real = v2._attention

    def with_row():
        a = dict(real())
        a["rows"] = [dict(ROW)]
        return a
    monkeypatch.setattr(v2, "_attention", with_row)


def _open_and_type(b, text):
    b.click(".att-ack button")
    b.wait_for("var i = document.querySelector('.att-ack input[name=why]');"
               "return !!i && i.offsetParent !== null && document.activeElement === i", 10)
    b.js("var i = document.querySelector('.att-ack input[name=why]'); i.value = arguments[0];"
         "i.dispatchEvent(new Event('input', {bubbles: true})); return 1", text)


def test_typing_survives_a_live_redraw(served, needs_one_ack):  # noqa: F811
    srv, b = served
    b.go(srv.url("/v2/"))
    b.wait_for(READY, 15)
    _open_and_type(b, "transient: the uplink flapped during the redeploy")
    b.js("document.body.dispatchEvent(new CustomEvent('nmas:acknowledgements')); return 1")
    b.wait_for("var a = document.getElementById('attention');"
               f"return !!a && a.getAttribute('data-held') === '1' && {SETTLED}", 15)
    state = b.js("var i = document.querySelector('.att-ack input[name=why]');"
                 "return {value: i ? i.value : null, focused: document.activeElement === i,"
                 " open: !!i && i.offsetParent !== null,"
                 " note: (document.querySelector('.held-note') || {}).textContent || ''}")
    assert state["value"] == "transient: the uplink flapped during the redeploy", state
    assert state["focused"] and state["open"], state
    assert "Newer data is waiting" in state["note"], state


def test_the_held_redraw_happens_once_the_form_closes(served, needs_one_ack):  # noqa: F811
    srv, b = served
    b.go(srv.url("/v2/"))
    b.wait_for(READY, 15)
    _open_and_type(b, "x")
    b.js("document.body.dispatchEvent(new CustomEvent('nmas:acknowledgements')); return 1")
    b.wait_for("var a = document.getElementById('attention');"
               "return !!a && a.getAttribute('data-held') === '1'", 15)
    b.js("var c = Array.prototype.filter.call(document.querySelectorAll('.att-ack button'),"
         " function (x) { return x.textContent.trim() === 'Cancel'; })[0]; c.click(); return 1")
    b.wait_for("var a = document.getElementById('attention');"
               f"return !!a && !a.getAttribute('data-held') && !document.querySelector('.held-note') && {SETTLED}",
               15)


def test_a_page_with_no_form_open_redraws_at_once(served, needs_one_ack):  # noqa: F811
    srv, b = served
    b.go(srv.url("/v2/"))
    b.wait_for(READY, 15)
    b.js("document.getElementById('attention').dataset.old = '1';"
         "document.body.dispatchEvent(new CustomEvent('nmas:acknowledgements')); return 1")
    b.wait_for("var a = document.getElementById('attention');"
               f"return !!a && !a.dataset.old && {SETTLED}", 15)


# ── C1388: a sent acknowledgement is answered in place, within a bound ──────
#
# The operator, 2026-10-19: on four rows, a reason sent sat on "Acknowledging…" for minutes
# beside "Newer data is waiting", with Cancel offered; a reload showed all four acknowledged.
# The server had answered 200 within milliseconds; the form waited for the redraw that removes
# the row, and the hold kept that redraw back because the sent reason was still shown.

SEND = ".att-ack-form button[data-op=needs-attention]"
ACK_STATE = ("var a = document.querySelector('.att-ack');"
             "if (!a) return {row: false};"
             "var bs = Array.prototype.slice.call(a.querySelectorAll('button'));"
             "var shown = function (x) { return !!x && x.offsetParent !== null; };"
             "var cancel = bs.filter(function (x) { return x.textContent.trim() === 'Cancel'; })[0];"
             "var opener = bs.filter(function (x) { return x.textContent.trim() === 'Acknowledge…'; })[0];"
             "var send = a.querySelector('.att-ack-form button[data-op=needs-attention]');"
             "var note = a.querySelector('.att-ack-note'), said = a.querySelector('.refusal');"
             "return {row: true, cancel: shown(cancel), opener: shown(opener),"
             " send: shown(send) ? send.textContent.trim() : '', busy: !!send && send.disabled,"
             " note: shown(note) ? note.textContent.trim() : '',"
             " said: shown(said) ? said.textContent.trim() : '',"
             " held: document.getElementById('attention').getAttribute('data-held') === '1'};")


@pytest.fixture
def acknowledged(monkeypatch, needs_one_ack):
    """POST /attention/acknowledge answered as the host answered it (200, recorded, hiding the
    row), after `acknowledged.delay` seconds; from the answer on, the row is no longer drawn.
    The real route would refuse ROW (no source holds it); its record is tests/test_acknowledge's."""
    import time

    import app as A
    from flask import jsonify
    from routes import v2
    state = {"delay": 1.0, "posts": 0, "recorded": False}
    drawn = v2._attention

    def without_once_recorded():
        a = dict(drawn())
        if state["recorded"]:
            a["rows"] = []
        return a

    def answer():
        state["posts"] += 1
        time.sleep(state["delay"])
        state["recorded"] = True
        return jsonify({"ok": True, "acknowledged": {}, "hides_now": True, "words": ""})

    monkeypatch.setattr(v2, "_attention", without_once_recorded)
    monkeypatch.setitem(A.app.view_functions, "attention.acknowledge", answer)
    return state


def test_a_sent_acknowledgement_is_drawn_at_once_though_a_redraw_waits(served, acknowledged):  # noqa: F811
    """Send a reason; a live redraw arrives while the answer is outstanding (1 s). Cancel is
    gone the moment it is sent; within the bound the form says "Acknowledged." or the row has
    gone, never left on "Acknowledging…"; and the held redraw then removes the row."""
    srv, b = served
    b.go(srv.url("/v2/"))
    b.wait_for(READY, 15)
    bound_s = b.js("return NMAS_V2.ACK_BOUND_MS") / 1000
    _open_and_type(b, "expected: the BGP session reset during the redeploy")
    assert b.js(ACK_STATE)["cancel"], "the open, unsent form offers Cancel"
    b.click(SEND)
    b.js("document.body.dispatchEvent(new CustomEvent('nmas:acknowledgements')); return 1")
    sent = b.js(ACK_STATE)
    assert sent["send"] == "Acknowledging…" and sent["busy"], sent
    assert not sent["cancel"], f"Cancel offered while the acknowledgement is being sent: {sent}"
    # The answer, in place: freed and said, or the row already gone.
    b.wait_for(f"var s = (function () {{ {ACK_STATE} }})();"
               "return !s.row || (s.note === 'Acknowledged.' && s.send !== 'Acknowledging…')",
               bound_s + 2)
    after = b.js(ACK_STATE)
    if after["row"]:
        assert not after["cancel"] and not after["opener"], (
            f"Cancel or Acknowledge… offered after the acknowledgement was recorded: {after}")
    # And the redraw it once held happens: the row leaves.
    b.wait_for(f"return !document.querySelector('.att-ack') && {SETTLED}", 10)
    assert acknowledged["posts"] == 1


def test_an_unanswered_acknowledgement_says_so_within_its_bound(served, acknowledged):  # noqa: F811
    """No answer within the bound: the button is freed and the form says that whether it was
    recorded is not known, offering no Cancel."""
    srv, b = served
    b.go(srv.url("/v2/"))
    b.wait_for(READY, 15)
    bound_s = b.js("return NMAS_V2.ACK_BOUND_MS") / 1000
    acknowledged["delay"] = bound_s + 4
    _open_and_type(b, "expected: the BGP session reset during the redeploy")
    b.click(SEND)
    b.wait_for(f"var s = (function () {{ {ACK_STATE} }})();"
               "return s.row && s.said.indexOf('whether it was recorded is not known') >= 0",
               bound_s + 3)
    late = b.js(ACK_STATE)
    assert late["send"] != "Acknowledging…" and not late["cancel"], late


def test_a_form_marked_not_editing_holds_no_redraw(served):  # noqa: F811
    """`data-editing="false"` (a form answered or closed) holds nothing, whatever its field
    still shows: a shown field with unsent text inside it lets the live redraw happen."""
    srv, b = served
    b.go(srv.url("/v2/"))
    b.wait_for(READY, 15)
    b.js("var a = document.getElementById('attention'); a.dataset.old = '1';"
         "var d = document.createElement('div'); d.setAttribute('data-editing', 'false');"
         "var i = document.createElement('input'); i.type = 'text'; i.name = 'why';"
         "d.appendChild(i); a.appendChild(d); i.value = 'sent already';"
         "document.body.dispatchEvent(new CustomEvent('nmas:acknowledgements')); return 1")
    b.wait_for("var a = document.getElementById('attention');"
               f"return !!a && !a.dataset.old && !a.getAttribute('data-held') && {SETTLED}", 15)


# ── C472: what a person opened stays open ───────────────────────────────────
#
# R27's survey (2026-10-05): C459's guard keeps typed text, never an open `<details>`, so a
# redraw closed the evidence a person was reading on Needs attention, and the History row they
# had opened. A `<details data-keep>` is reopened after any swap that replaces its region.

def _redraw_and_wait(b, region_id, key):
    b.js("document.getElementById(arguments[0]).dataset.old = '1';"
         "document.body.dispatchEvent(new CustomEvent('nmas:' + arguments[1])); return 1",
         region_id, key)
    b.wait_for("var r = document.getElementById(arguments[0]);"
               f"return !!r && !r.dataset.old && {SETTLED}", 15, region_id)


def test_the_evidence_a_person_opened_stays_open(served):  # noqa: F811
    srv, b = served
    b.go(srv.url("/v2/"))
    b.wait_for(READY, 15)
    b.js("document.querySelector('#attention details.evidence').open = true; return 1")
    _redraw_and_wait(b, "attention", "acknowledgements")
    assert b.js("return document.querySelector('#attention details.evidence').open")
    # The control beside it: a details nobody opened stays closed.
    b.js("document.querySelector('#attention details.evidence').open = false; return 1")
    _redraw_and_wait(b, "attention", "acknowledgements")
    assert not b.js("return document.querySelector('#attention details.evidence').open")


def test_a_history_row_a_person_opened_stays_open(served):  # noqa: F811
    srv, b = served
    b.go(srv.url("/v2/device/r3?tab=history"))
    b.wait_for(READY + " && !!document.querySelector('#history details.hist-row')", 15)
    key = b.js("var d = document.querySelector('#history details.hist-row'); d.open = true;"
               "return d.getAttribute('data-keep')")
    assert key
    _redraw_and_wait(b, "history", "goldens")
    assert b.js("var d = document.querySelector('#history details[data-keep=\"' + arguments[0]"
                " + '\"]'); return !!d && d.open", key)


def test_an_htmx_write_relays_its_keys_to_its_own_page(served, monkeypatch):  # noqa: F811
    """C474 (2026-10-05): htmx asks by XHR, so a v2 confirm's `X-NMAS-Invalidates` reached
    nothing on its own page, and the sidebar's count stayed stale after Retry, Persist and
    Finish retirement. In a real browser: an htmx POST to a route declaring `remote` reaches
    a subscriber of that key; the control, a GET, reaches none."""
    import app as A
    from modules.nsot import remote as R
    monkeypatch.setattr(R, "enable_auto_push",
                        lambda name, actor="": {"ok": True, "enabled": True})
    srv, b = served
    b.go(srv.url("/v2/"))
    b.wait_for(READY, 15)
    b.js("window.__heard = 0; NMAS.subscribe('remote', 'probe', function () {"
         " window.__heard++; return true; }); return 1")
    b.js("htmx.ajax('GET', '/v2/who', {target: '#nmas-strip', swap: 'none'}); return 1")
    b.wait_for(f"return {SETTLED}", 10)
    assert b.js("return window.__heard") == 0
    # v2's Remote set-up… turns automatic pushing on (today's /remote/auto-push left with the
    # Remote card at 7.8, P7-21); it declares `remote` as the removed route did.
    b.js("htmx.ajax('POST', '/v2/history/remote/setup/auto-push',"
         " {swap: 'none', values: {list: 'Default'}}); return 1")
    assert b.wait_for("return window.__heard", 10) == 1


# ── The flash: the first paint already reads as age words ──────────────────

@pytest.mark.parametrize("ago, words", [(10, "just now"), (60, "1 min ago"), (600, "10 min ago"),
                                        (3 * 3600, "3 h ago"), (3 * 86400, "3 d ago")])
def test_the_server_draws_the_scripts_age_words(ago, words):
    from routes.v2 import age_words
    now = 1_790_000_000
    from datetime import datetime, timezone
    iso = datetime.fromtimestamp(now - ago, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert age_words(iso, now=now) == words


def test_an_unreadable_time_is_drawn_as_itself():
    from routes.v2 import age_words
    assert age_words("not a time") == "not a time"


def test_stamp_draws_words_not_the_iso_time():
    import app as A
    with A.app.test_request_context("/"):
        from flask import render_template_string
        out = render_template_string('{% from "v2/_macros.html" import stamp %}'
                                     '{{ stamp("2026-10-05T02:31:00Z") }}')
    text = out.split(">", 1)[1].split("<", 1)[0]
    assert "2026-10-05T02:31:00Z" not in text and text.endswith("ago"), out


def test_the_held_note_stays_inside_the_region_beside_the_field(served):  # noqa: F811
    """The operator, 2026-10-12: on Topology, with text left in Find and the reader's update
    arriving, the note appeared outside the page (top right) and the map's layout broke. The
    field has no Alpine component nearer than `<body x-data="frame">`, so the note became a
    child of the page grid. It now goes beside the field, inside the region."""
    from tests.test_topology_v2 import _store, _value
    _store(_value())
    srv, b = served
    b.go(srv.url("/v2/topology?list=Lab"))
    b.wait_for(READY + " && !!document.getElementById('topo-find')", 15)
    b.js("var i = document.getElementById('topo-find'); i.focus(); i.value = 'r6';"
         "i.dispatchEvent(new Event('input', {bubbles: true})); return 1")
    b.js("document.body.dispatchEvent(new CustomEvent('nmas:topology')); return 1")
    b.wait_for("var t = document.getElementById('topo');"
               f"return !!t && t.getAttribute('data-held') === '1' && {SETTLED}", 15)
    state = b.js("var n = document.querySelector('.held-note');"
                 "return {note: !!n, inside: !!n && document.getElementById('topo').contains(n),"
                 " onBody: !!n && n.parentNode === document.body,"
                 " value: document.getElementById('topo-find').value}")
    assert state == {"note": True, "inside": True, "onBody": False, "value": "r6"}, state


def test_the_map_carries_no_native_tooltip_over_its_links():
    """The operator, 2026-10-12: hovering a link drew the browser's own tooltip (the map's SVG
    `<title>`, the network's summary) over the link's card. The summary is the map's accessible
    name, as an attribute, which no browser shows on hover."""
    with open("templates/v2/_topology_map.html", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    at = [i for i, line in enumerate(lines) if line.startswith('<svg class="topo-map')]
    assert len(at) == 1, at
    assert 'aria-label="{{ t.list }}: {{ t.summary.devices }} devices' in lines[at[0]]
    assert not lines[at[0] + 1].lstrip().startswith("<title"), lines[at[0] + 1]


def test_a_failed_count_refresh_marks_the_count_not_the_sidebar(served):  # noqa: F811
    """The operator, 2026-10-12: "Couldn't load this view" appeared beside Needs attention and
    distorted the page. The count's refresh failed (a restart), and the notice, with no card or
    section around the count, went into the sidebar's link. Now the count shows its own
    unreadable "?" with the reason on hover, keeps its listener, and no box is drawn."""
    import app as A
    srv, b = served
    b.go(srv.url("/v2/"))
    b.wait_for(READY + " && !!document.getElementById('attention-count')", 15)
    real = A.app.view_functions["device_v2.attention_count"]
    # As a restart answers through the proxy: a whole error page, not a fragment.
    A.app.view_functions["device_v2.attention_count"] = lambda: (
        "<!doctype html><html><head><title>502 Bad Gateway</title></head><body></body></html>",
        502)
    try:
        b.js("document.body.dispatchEvent(new CustomEvent('nmas:acknowledgements')); return 1")
        b.wait_for("var c = document.getElementById('attention-count');"
                   f"return !!c && c.hasAttribute('data-couldnt') && {SETTLED}", 15)
        state = b.js("var c = document.getElementById('attention-count');"
                     "return {text: c.textContent.trim(), cls: c.className, title: c.title,"
                     " boxes: document.querySelectorAll('.sidebar .couldnt').length,"
                     " listens: !!c.getAttribute('hx-get')}")
    finally:
        A.app.view_functions["device_v2.attention_count"] = real
    assert state["text"] == "?" and "count-unreadable" in state["cls"], state
    assert "could not be read (" in state["title"] and "502" in state["title"], state
    assert state["boxes"] == 0 and state["listens"], state
