"""Needs attention as C's document with B's queue (the operator's GUI pick, 2026-11-25: "C with
B's Needs attention queue and step timeline"; Stage 5 step 3).

- **The sentence** (`attention.sentence`): what is critical, by its rows' own titles (three, then
  how many more), then what is below them, counted as the list counts its findings (a group of
  alike rows by its members, each at its own level, named once); with nothing critical, the
  warnings named the same way and the word "critical" never said; no sentence with nothing to
  draw (the summary's own "Nothing needs attention" says it once) or while the store's first
  value is still reading.
- **On the page:** the sentence is the list's first line, inside the part that redraws itself,
  and it is the one `attention.sentence` makes of the same rows.
- **B's keys, in a real browser:** j and k move from row to row, e presses the row's one action.
"""
import re
import time

import pytest

from modules import attention as A
from tests.test_attention_sections import _page, _rows, _src
from tests.test_needs_attention import _panel

NOW = time.time()


def _row(level, what, key):
    return A.row(source="drift", kind="drifted", key=key, level=level, what=what,
                 cause="c", action={"label": "do it"}, devices=[key.split(":")[1]],
                 since=NOW - 60)


class TestTheSentence:
    def test_it_names_what_is_critical_then_counts_what_is_below(self):
        rows = [_row("danger", "edge1 has drifted", "d:edge1"),
                _row("warning", "edge2 was not checked", "w:edge2"),
                _row("warning", "edge3 was not checked", "w:edge3"),
                _row("unknown", "a reader could not run", "u:r1")]
        assert A.sentence({"rows": rows}) == {
            "lead": "1 critical item needs you now: edge1 has drifted.",
            "rest": "Below it: 2 warnings and 1 unknown."}

    def test_past_three_it_names_three_and_counts_the_rest(self):
        rows = [_row("danger", f"r{i} is down", f"d:r{i}") for i in range(1, 6)]
        assert A.sentence({"rows": rows}) == {
            "lead": "5 critical items need you now: r1 is down, r2 is down, r3 is down and 2 "
                    "more.", "rest": ""}
        two = A.sentence({"rows": rows[:2]})
        assert two["lead"] == "2 critical items need you now: r1 is down and r2 is down."

    def test_a_group_of_alike_rows_counts_its_members_and_is_named_once(self):
        members = [_row("danger", f"s{i} lost its stream", f"d:s{i}") for i in range(1, 4)]
        group = dict(members[0], what="3 devices lost their stream", alike={"count": 3},
                     folded=members)
        got = A.sentence({"rows": [group, _row("warning", "x", "w:x")]})
        assert got == {"lead": "3 critical items need you now: 3 devices lost their stream.",
                       "rest": "Below them: 1 warning."}

    def test_with_nothing_critical_it_names_the_warnings_and_never_says_critical(self):
        got = A.sentence({"rows": [_row("warning", "a is late", "w:a"),
                                   _row("warning", "b is late", "w:b"),
                                   _row("unknown", "c could not be read", "u:c")]})
        assert got == {"lead": "2 warnings: a is late and b is late.",
                       "rest": "Below them: 1 unknown."}
        assert "critical" not in (got["lead"] + got["rest"]).lower()
        assert A.sentence({"rows": [_row("unknown", "c could not be read", "u:c")]}) == {
            "lead": "1 unknown: c could not be read.", "rest": ""}

    def test_with_nothing_to_draw_there_is_no_sentence(self):
        assert A.sentence({"rows": []}) == {}

    def test_while_the_list_is_reading_there_is_no_sentence(self):
        assert A.sentence({"rows": [], "store": {"state": "reading"}}) == {}


def test_the_page_draws_the_lists_own_sentence_inside_the_part_that_redraws(monkeypatch):
    page = _page(monkeypatch, [_src(_rows())])
    html = _panel(page)
    said = A.sentence(page)
    assert said["lead"] == "1 critical item needs you now: edge1 has drifted from its golden."
    m = re.search(r'<p class="doc-summary att-sentence" data-sentence><strong>(.*?)</strong>'
                  r' (.*?)</p>', html)
    assert m and (m.group(1), m.group(2)) == (said["lead"], said["rest"]), html[:2000]
    assert html.index("data-sentence") < html.index('class="att-summary"')


CHIP = re.compile(r'<a class="att-filt( on)?" href="([^"]+)"[^>]*data-show="(\w+)">'
                  r'([A-Za-z]+)<b>(\d+)</b></a>')


@pytest.mark.parametrize("show, heads, on", [
    ("", ["Critical · 1", "Warning · 1"], "all"),
    ("danger", ["Critical · 1"], "danger"),
    ("warning", ["Warning · 1"], "warning"),
    ("nonsense", ["Critical · 1", "Warning · 1"], "all"),
    ("ack", [], "ack")])
def test_a_chip_shows_its_group_and_the_redraw_keeps_it(monkeypatch, show, heads, on):
    """B's filter chips (Stage 5 step 3): All, each level with items, and the chip the address
    chose, each a link (`?show=`); the chosen one marked, only its group drawn, and the list's
    own live redraw asks for the same chip, so a redraw never undoes it. An unknown value is
    All. With nothing acknowledged, Acknowledged says so, never "nothing to do"."""
    from html import unescape
    from urllib.parse import parse_qs, urlsplit

    import app as nmas
    monkeypatch.setattr(A, "SOURCES", (_src(_rows()),))
    client = nmas.app.test_client()
    html = client.get(f"/v2/?show={show}").get_data(as_text=True)
    assert re.findall(r'<summary class="att-grp-sum">([^<]+)</summary>', html) == heads

    def shows(href):
        url = urlsplit(unescape(href))
        return url.path, parse_qs(url.query).get("show", [""])[0]
    chips = {m.group(3): (bool(m.group(1)), shows(m.group(2)), m.group(4), int(m.group(5)))
             for m in CHIP.finditer(html)}
    assert [k for k, c in chips.items() if c[0]] == [on], chips
    assert chips["all"][1:] == (("/v2/", ""), "All", 2) and chips["danger"][3] == 1
    assert chips["warning"][1] == ("/v2/", "warning") and "unknown" not in chips
    live = unescape(re.search(r'<div id="attention" class="attention" hx-get="([^"]+)"',
                              html).group(1))
    assert shows(live) == ("/v2/attention", "" if on == "all" else on)
    again = client.get(live).get_data(as_text=True)
    assert re.findall(r'<summary class="att-grp-sum">([^<]+)</summary>', again) == heads
    if on == "ack":
        assert "Nothing is acknowledged now." in html and "Every source answered" not in html
    # A chip hides groups; it removes nothing from the list.
    assert len(A.needs_attention()["rows"]) == 2


def test_j_and_k_move_from_row_to_row_and_e_presses_its_action_in_a_real_browser(monkeypatch):
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as nmas
    monkeypatch.setattr(A, "SOURCES", (_src(_rows()),))
    on = ("var a=document.activeElement, r=a && a.closest && a.closest('details.att');"
          " return r ? r.getAttribute('data-attention-row') : null;")
    with browser.Served(nmas.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/"))
            b.wait_for("return !!window.htmx && document.querySelectorAll('details.att')"
                       ".length === 2", 15)
            order = b.js("return Array.from(document.querySelectorAll('details.att'))"
                         ".map(function(d){return d.getAttribute('data-attention-row');})")
            seen = []
            for key in ("j", "j", "k"):
                b._call("POST", f"/session/{b.session}/actions", {"actions": [{
                    "type": "key", "id": "kb", "actions": [{"type": "keyDown", "value": key},
                                                           {"type": "keyUp", "value": key}]}]})
                b.wait_for(f"var r=(function(){{{on}}})(); return r !== null", 5)
                seen.append(b.js(on))
            b._call("POST", f"/session/{b.session}/actions", {"actions": [{
                "type": "key", "id": "kb", "actions": [{"type": "keyDown", "value": "j"},
                                                       {"type": "keyUp", "value": "j"},
                                                       {"type": "keyDown", "value": "e"},
                                                       {"type": "keyUp", "value": "e"}]}]})
            b.wait_for("return location.pathname === '/v2/devices'", 15)
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert len(order) == 2 and seen == [order[0], order[1], order[0]], (order, seen)


def test_a_opens_the_row_at_its_acknowledge_form_in_a_real_browser(monkeypatch):
    """B's "a": on a row that offers Acknowledge… (an unplanned restart, acknowledged per event),
    the row opens at its form with its reason box focused; on a row that offers none, nothing."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as nmas
    restart = A.row(source="restarts", kind="unplanned", key="unplanned:edge3", level="warning",
                    what="edge3 restarted with no planned window", cause="its counter fell",
                    action={"label": "Read why"}, devices=["edge3"], since=NOW - 120, event="e1")
    monkeypatch.setattr(A, "SOURCES", (_src(_rows() + [restart]),))

    def press(b, key):
        b._call("POST", f"/session/{b.session}/actions", {"actions": [{
            "type": "key", "id": "kb", "actions": [{"type": "keyDown", "value": key},
                                                   {"type": "keyUp", "value": key}]}]})
    with browser.Served(nmas.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/"))
            b.wait_for("return !!window.Alpine && document.querySelectorAll('details.att')"
                       ".length === 3", 15)
            order = b.js("return Array.from(document.querySelectorAll('details.att'))"
                         ".map(function(d){return d.getAttribute('data-attention-row');})")
            at = order.index(restart["id"])
            assert at > 0, order
            # On the first row, which offers no acknowledgement, "a" does nothing: the focus
            # stays on its line and the row stays closed.
            press(b, "j")
            first = b.js("var a=document.activeElement, r=a.closest('details.att');"
                         " return [a.className, r.getAttribute('data-attention-row'), r.open];")
            press(b, "a")
            still = b.js("var a=document.activeElement, r=a.closest('details.att');"
                         " return [a.className, r.getAttribute('data-attention-row'), r.open];")
            for _ in range(at):
                press(b, "j")
            press(b, "a")
            b.wait_for("var a=document.activeElement; return !!a && a.id && a.id.indexOf('ack-')"
                       " === 0", 5)
            got = b.js("var a=document.activeElement, r=a.closest('details.att');"
                       " return [a.id, r.getAttribute('data-attention-row'), r.open];")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    assert not any(r.get("acknowledge") for r in _rows()), "the other rows offer none"
    assert first == still == ["att-line", order[0], False], (first, still)
    assert got == [f"ack-{restart['id']}", restart["id"], True], got
