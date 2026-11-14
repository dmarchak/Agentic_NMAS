"""Needs attention: rows of one shape are one row, and every row's line names its action (the
GUI review's item 10, C3457; the operator, 2026-11-13; docs/UI_RULES.md, "Rows of one shape
collapse into one row"). Through the real app on the landing walk's world
(tests/test_board_shots.py's `_landing_world`: the browser layout test's lab and every source as
the payload check's provider builds it), and on a 900-device fleet. No device, no network.

- **Rows of one shape are one row.** Rows from one source, of one kind, whose words differ only
  in their subject (34 rows "reader:<name> has never run on this host" in the landing world,
  measured 2026-11-13 before the change: 56 rows drawn, 34 of them that shape) are one row
  ("34 readers have never run on this host"), opening to each of them, drawn as itself with its
  own action; its level its worst member's; its action the one its members share, else Open the
  list. A group of one is its row. Measured after: 17 rows drawn for the same 56 items.
- **Counts stay counts of findings, said:** the summary's items, the severity headings and the
  sidebar's count count each member; the summary and a heading say how many rows draw them.
- **Every row's line names its action** (CLAUDE.md, "every row names something wrong AND an
  action"): the control `attention.first_action` names, else the action's own words, else, for
  an action not known, how the row clears. Measured before: 5 of the 9 critical rows drew
  nothing on their line.
- **They hold as a person acts:** after Acknowledge… (the real route) takes an item off, the
  list keeps all three, one item fewer; a group of two with one acknowledged is its other
  item's own row.
- **Large fleets:** 900 devices with one finding each are one row, closed, the list a summary
  first, no device named outside a closed disclosure.
- **In a real browser** (headless Firefox, unconfined), at 1280 px: Open the list opens its
  group and focuses its list; the words on an opened row's line are hidden in place, so nothing
  on the line moves; at 390 px no line is wider than its row.

The expectations come by a path apart from the grouping's own (`attention._alike_shape`): a
row's words with every token holding a digit, a colon or a hyphen, and every device the row
names, replaced by one mark.
"""
import re
from html import unescape
from html.parser import HTMLParser

import pytest

from tests.test_large_fleets import LIMIT, NAMES

#: A token that names a subject (a device "r6", a unit "nmas-netbox-backup", a reader
#: "reader:adjacencies"), for the independent shape below.
SUBJECTS = re.compile(r"\S*[\d:\-]\S*")


def shape_of(words: str, devices=()) -> str:
    """A row's words with its subjects marked, independently of `attention._alike_shape`."""
    for d in sorted(devices or (), key=len, reverse=True):
        words = re.sub(rf"(?<!\S){re.escape(d)}(?=[\s:'.,]|$)", "<s>", words)
    return SUBJECTS.sub("<s>", words)


class Drawn(HTMLParser):
    """Every Needs attention row a page draws: its depth among rows (0 for a row of the list,
    1 for a row inside another), its level, its title, its line's action text, whether it
    is open, and the text outside every CLOSED disclosure (what a person sees unopened)."""

    def __init__(self):
        super().__init__()
        self.stack, self.rows, self.row_stack = [], [], []
        self.closed = 0
        self.seen = []
        self.in_what = self.in_primary = 0
        self.summary = ""
        self.in_summary_p = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = (a.get("class") or "").split()
        if tag == "details":
            is_row = "att" in cls
            shut = "open" not in a
            self.stack.append((is_row, shut, False))
            if is_row:
                level = next(c[4:] for c in cls if c.startswith("att-"))
                row = {"id": a.get("data-attention-row"), "depth": len(self.row_stack),
                       "level": level, "what": "", "line": "", "open": not shut}
                self.rows.append(row)
                self.row_stack.append(row)
        if tag == "summary" and self.stack:
            # A closed disclosure's summary is seen; what follows it inside is not.
            pass
        if tag == "h2" and "att-what" in cls:
            self.in_what = 1
        if tag == "span" and "att-primary" in cls:
            self.in_primary = 1
        elif tag == "span" and self.in_primary:
            self.in_primary += 1
        if tag == "p" and "att-summary" in cls:
            self.in_summary_p = True

    def handle_endtag(self, tag):
        if tag == "details" and self.stack:
            is_row, shut, _ = self.stack.pop()
            if is_row:
                self.row_stack.pop()
        if tag == "summary" and self.stack:
            is_row, shut, _ = self.stack[-1]
            self.stack[-1] = (is_row, shut, True)
            self.in_primary = 0
        if tag == "h2":
            self.in_what = 0
        if tag == "span" and self.in_primary:
            self.in_primary -= 1
        if tag == "p":
            self.in_summary_p = False

    def handle_data(self, data):
        if self.in_summary_p:
            self.summary += data
        hidden = any(shut and past for _r, shut, past in self.stack)
        if not hidden:
            self.seen.append(data)
        if self.row_stack:
            row = self.row_stack[-1]
            if self.in_what:
                row["what"] += data
            if self.in_primary:
                row["line"] += data


def drawn(html: str) -> Drawn:
    p = Drawn()
    p.feed(html.split("<body", 1)[-1])
    for r in p.rows:
        r["what"] = " ".join(unescape(r["what"]).split())
        r["line"] = " ".join(unescape(r["line"]).split())
    p.summary = " ".join(unescape(p.summary).split())
    return p


def _drawn_now():
    """``(findings, html, page)``: the findings the background holds, and /v2/ as drawn."""
    import app as A
    from modules import attention_store

    findings = attention_store.read()["rows"]
    html = A.app.test_client().get("/v2/").get_data(as_text=True)
    return findings, html, drawn(html)


def _ack(row: dict):
    import app as A

    return A.app.test_client().post("/attention/acknowledge", json={
        "row": row["id"], "event": row["event"], "why": "expected while the lab is rebuilt"})


def rows_of_one_shape_are_one_row(findings, page):
    """No two rows drawn share their words once each subject is a mark; the never-run readers
    are one closed row whose count is theirs, each inside it as itself; every finding drawn
    exactly once."""
    readers = [r for r in findings if r["id"].startswith("job_health:reader:")
               and r["what"].endswith(" has never run on this host")]
    assert len(readers) >= 20, "the world's population of never-run readers shrank"
    top = [r for r in page.rows if r["depth"] == 0]
    shapes = [shape_of(r["what"]) for r in top]
    alike = sorted({s for s in shapes if shapes.count(s) > 1})
    assert alike == [], f"rows of one shape still drawn apart: {alike}"
    assert len(top) < len(findings), (len(top), len(findings))
    group = [r for r in top if r["what"] == f"{len(readers)} readers have never run on this host"]
    assert len(group) == 1, [r["what"] for r in top]
    assert not group[0]["open"]
    inside = [r for r in page.rows if r["depth"] == 1 and r["id"] in {x["id"] for x in readers}]
    assert len(inside) == len(readers)
    ids = [r["id"] for r in page.rows if not r["id"].startswith("alike:")]
    assert sorted(ids) == sorted(r["id"] for r in findings)


def counts_are_the_findings(findings, page, html):
    """The summary's items and each severity's count are the findings', and the summary and a
    grouped heading say how many rows draw them."""
    top = [r for r in page.rows if r["depth"] == 0]
    n = len(findings)
    assert page.summary.startswith(f"{n} items"), page.summary
    for level, word in (("danger", "critical"), ("warning", "warning"), ("unknown", "unknown")):
        k = len([r for r in findings if r["level"] == level])
        if k:
            assert f" · {k} {word}" in page.summary, (word, page.summary)
    assert f"in {len(top)} rows" in page.summary, page.summary
    heads = re.findall(r'<summary class="att-grp-sum">([^<]+)(?:<span class="att-grp-rows">'
                       r'([^<]+)</span>)?</summary>', html)
    heads = [(h, rows) for h, rows in heads if h.startswith(("Critical", "Warning", "Unknown"))]
    assert sum(int(h.split("·")[1]) for h, _rows in heads) == n, heads
    assert any(rows for _h, rows in heads), "a heading that groups says how many rows"


def every_line_names_its_action(findings, page):
    """Every row's line, members' included, names its action: a row with no control of its own
    its action's words, or, its action not known, how it clears."""
    from modules import attention

    by_id = {r["id"]: r for r in findings}
    critical = [r for r in page.rows if r["id"] in by_id and by_id[r["id"]]["level"] == "danger"]
    assert len(critical) == len([r for r in findings if r["level"] == "danger"]) >= 5
    for r in page.rows:
        assert r["line"], f"{r['what']!r} names no action on its line"
        f = by_id.get(r["id"])
        if f is None or attention.first_action(f) != "":
            continue
        act = f.get("action") or {}
        want = (act["label"] if act.get("known") is not False
                else "Clears when " + f["clears"]["when"])
        assert r["line"] == " ".join(want.split()), (r["what"], r["line"])


def test_the_landing_world_drawn_and_after_an_acknowledgement(tmp_path, monkeypatch):
    """The landing walk's world as /v2/ draws it holds the three properties above, and holds
    them again once a person's acknowledgement has taken an item off: the item gone, the counts
    one fewer."""
    from modules import attention_store
    from tests.test_board_shots import _landing_world

    _landing_world(tmp_path, monkeypatch)
    # The world plants its repeated authorisation as the counts it hands the source; the
    # acknowledgement's handler asks the source again with none, so it is handed the same.
    from modules import attention
    real, planted = attention.authorisation_source, {}

    def authorisations(counts=None):
        planted.setdefault("counts", counts)
        return real(counts or planted.get("counts"))
    monkeypatch.setattr(attention, "authorisation_source", authorisations)
    findings, html, page = _drawn_now()
    for check in (rows_of_one_shape_are_one_row, every_line_names_its_action):
        check(findings, page)
    counts_are_the_findings(findings, page, html)
    gone = next(r for r in findings if r.get("acknowledge") and r.get("event"))
    assert _ack(gone).status_code == 200
    after, html, page = _drawn_now()
    assert len(after) == len(findings) - 1 and gone["id"] not in {r["id"] for r in after}
    assert gone["id"] not in {r["id"] for r in page.rows}
    assert attention_store.read()["badge"]["n"] == len(after)
    for check in (rows_of_one_shape_are_one_row, every_line_names_its_action):
        check(after, page)
    counts_are_the_findings(after, page, html)


def test_a_group_of_two_is_its_row_once_one_is_acknowledged(monkeypatch):
    """The same line authorised three times on two devices: one row about both, Open the list
    on its line; one of them acknowledged, the other is drawn as its own row, the summary one
    item and no group."""
    from modules import attention

    entry = {"count": 3, "first_at": "2026-10-01T10:00:00Z", "last_at": "2026-10-02T08:00:00Z",
             "last_actor": "a@example.com", "last_reason": "the lab link is down"}
    monkeypatch.setattr("modules.nsot.receipts.authorisations_by_device", lambda lst: {
        "state": "ok", "devices": {"edge-a": {"shutdown": dict(entry)},
                                   "edge-b": {"shutdown": dict(entry)}}})
    monkeypatch.setattr(attention, "SOURCES", [attention.authorisation_source])
    findings, _html, page = _drawn_now()
    assert len(findings) == 2
    top = [r for r in page.rows if r["depth"] == 0]
    assert [(r["what"], r["line"]) for r in top] == [
        ("'shutdown' has been authorised 3 times on each of 2 devices", "Open the list")]
    assert page.summary.startswith("2 items · 2 warning · in 1 row"), page.summary
    assert _ack(findings[0]).status_code == 200
    after, _html, page = _drawn_now()
    kept = findings[1]
    assert [r["id"] for r in after] == [kept["id"]]
    assert [(r["id"], r["depth"], r["what"]) for r in page.rows] == [
        (kept["id"], 0, kept["what"])]
    assert page.summary.startswith("1 item · 1 warning ·") and " row" not in page.summary


def test_a_group_s_level_action_and_clearing():
    from modules import attention as A

    def jrow(unit, level, label="Read the job's own output on the host"):
        r = A.row(source="job_health", kind="job", key=unit, what=f"{unit} is failing",
                  cause="its last run failed", action={"label": label}, level=level)
        return dict(r, networks={})

    one = [jrow("nmas-a", "danger")]
    assert A.group_alike(one) == one, "a group of one is its row"
    def one(rows):
        out = A.group_alike(rows)
        assert len(out) == 1, [r["what"] for r in out]
        return out[0]

    rows = [jrow("nmas-a", "warning"), jrow("nmas-b", "danger"), jrow("nmas-c", "warning")]
    g = one(rows)
    assert g["what"] == "3 jobs are failing" and g["level"] == "danger"
    assert [m["id"] for m in g["folded"]] == ["job_health:nmas-b", "job_health:nmas-a",
                                             "job_health:nmas-c"]
    assert g["alike"]["count"] == 3 and g["action"]["label"] == rows[0]["action"]["label"]
    assert A.first_action(g) == ""
    assert "every item in it has cleared" in g["clears"]["when"]
    # Members whose actions differ: Open the list.
    rows[2] = jrow("nmas-c", "warning", label="Regenerate its rules")
    g = one(rows)
    assert A.first_action(g) == "alike" and g["action"]["anchor"] == g["alike"]["anchor"]
    # Other shapes stand apart; a row about one incident, or one a run holds, never groups.
    other = dict(jrow("nmas-d", "danger"), what="nmas-d is not installed")
    held = dict(jrow("nmas-e", "danger"), held={"device": "r1"})
    out = A.group_alike(rows + [other, held])
    assert [r["id"] for r in out][1:] == ["job_health:nmas-d", "job_health:nmas-e"]
    # A subject inside a longer token is never the subject: r1 is not found in r10.
    a = dict(A.row(source="drift", kind="drifted", key="L:r1", what="r1 has drifted from r10",
                   cause="c", action={"label": "Capture it"}, level="danger", devices=["r1"]),
             networks={})
    b = dict(A.row(source="drift", kind="drifted", key="L:r2", what="r2 has drifted from r10",
                   cause="c", action={"label": "Capture it"}, level="danger", devices=["r2"]),
             networks={})
    g = one([a, b])
    assert g["what"] == "2 devices have drifted from r10" and g["devices"] == []


def test_900_alike_devices_are_one_closed_row_and_a_summary_first():
    import app as A
    from flask import render_template
    from modules import attention
    from tests.fixtures.fleet_scale import build_fleet

    fleet = [d["hostname"] for d in build_fleet(900)]
    rows = [dict(attention.row(source="job_health", kind="job", key=f"monitoring:{d}",
                               what=f"{d} is not monitored: it has no committed golden",
                               cause="no golden is committed for it",
                               action={"label": "Capture its golden"}, level="warning",
                               devices=[d]), networks={d: ["Lab"]}) for d in fleet]
    grouped = attention.group_alike(rows)
    assert len(grouped) == 1
    with A.app.test_request_context("/v2/"):
        html = render_template("v2/_attention.html", attention_trigger="",
                               a={"rows": grouped, "sources": [], "badge": {"n": len(rows)}})
    page = drawn(html)
    seen = " ".join(page.seen)
    assert len(set(NAMES.findall(seen))) <= LIMIT, "a long expanded list of devices"
    assert page.summary.startswith("900 items · 900 warning · in 1 row"), page.summary
    top = [r for r in page.rows if r["depth"] == 0]
    assert [(r["what"], r["open"], r["line"]) for r in top] == [
        ("900 devices are not monitored: each has no committed golden", False, "Open the list")]
    assert len([r for r in page.rows if r["depth"] == 1]) == 900


# ── In a real browser ─────────────────────────────────────────────────────────────────────

SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"
LINE = r"""
var d = document.querySelector(arguments[0]), line = d.querySelector(':scope > summary');
var said = line.querySelector('.att-said'), age = line.querySelector('.att-age');
return JSON.stringify({open: d.open, height: Math.round(line.getBoundingClientRect().height),
  wide: line.scrollWidth - line.clientWidth,
  said: said ? said.checkVisibility({visibilityProperty: true}) : null,
  age: age ? Math.round(age.getBoundingClientRect().left) : null});
"""


def test_open_the_list_and_the_line_in_a_real_browser(tmp_path, monkeypatch):
    """At 1280 px: Open the list on a group's line opens the group and focuses its list; a row
    whose line holds its action's words keeps them on one line, hidden in place when the row
    is opened, its age not moving. At 390 px: no line is wider than its row."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import json

    from tests.test_board_shots import _landing_world

    _landing_world(tmp_path, monkeypatch)
    import app as nmas
    from modules import attention
    from modules import attention_store
    from modules import csp

    # The phone's frame (below) is this page's own: its frame-ancestors opened to 'self' here.
    monkeypatch.setattr(csp, "STRICT_POLICY", csp.STRICT_POLICY.replace(
        "frame-ancestors 'none'", "frame-ancestors 'self'"))
    a = attention_store.read()
    grouped = attention.group_alike(a["rows"])
    jump = [g for g in grouped if attention.first_action(g) == "alike"]
    worded = [r for r in grouped if attention.first_action(r) == ""
              and (r.get("action") or {}).get("known") is not False]
    assert jump and worded, (len(jump), len(worded))
    with browser.Served(nmas.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/"))
            b.wait_for("return !!window.htmx && !!document.querySelector('#attention "
                       f"details.att') && {SETTLED}", 20)
            g = f'#attention details.att[data-attention-row="{jump[0]["id"]}"]'
            assert json.loads(b.js(LINE, g))["open"] is False
            b.click(f'{g} > summary a.att-jump')
            b.wait_for("return document.querySelector(arguments[0]).open && "
                       "document.activeElement && document.activeElement.id === arguments[1]",
                       10, g, jump[0]["alike"]["anchor"])
            assert b.js("return document.activeElement.textContent.trim()") == (
                f"{jump[0]['alike']['count']} {jump[0]['alike']['noun']} in this group")
            w = f'#attention details.att[data-attention-row="{worded[0]["id"]}"]'
            before = json.loads(b.js(LINE, w))
            assert before["said"] is True and before["height"] <= 60, before
            b.click(f"{w} > summary .att-what")
            b.wait_for("return document.querySelector(arguments[0]).open", 10, w)
            after = json.loads(b.js(LINE, w))
            assert after["said"] is False, "the line's words are hidden on the opened row"
            assert (after["age"], after["height"]) == (before["age"], before["height"])
            # A phone's width is a frame that wide (geckodriver makes no window narrower than
            # 500 px; tests/test_recheck.py measured it, and opens frame-ancestors the same way).
            b.js("var f = document.createElement('iframe'); f.width = '390';"
                 " f.height = '800'; f.style.position = 'fixed'; f.style.left = '0';"
                 " f.style.top = '0'; f.style.border = '0'; f.style.zIndex = '9999';"
                 " f.src = location.origin + '/v2/'; document.body.appendChild(f); return 1")
            b.wait_for("var f = document.querySelector('iframe'); return f &&"
                       " f.contentWindow.htmx && f.contentDocument.querySelector("
                       "'#attention summary.att-line')", 20)
            b._call("POST", f"/session/{b.session}/frame", {"id": 0})
            b.wait_for(f"return window.innerWidth <= 400 && {SETTLED}", 10)
            wide = b.js("return Array.from(document.querySelectorAll('#attention "
                        "summary.att-line')).filter(function (s) { return s.checkVisibility() "
                        "&& s.scrollWidth > s.clientWidth + 1; }).length")
            assert wide == 0, f"{wide} line(s) wider than their row at 390 px"
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
