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
