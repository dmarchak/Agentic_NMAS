"""A log table reads at a glance (C3452; the GUI review of the recorded screens, 2026-11-13,
item 4, approved by the operator): "no cell breaks inside a time or a mnemonic, and repeats
collapse".

- **Tokens never break.** The received time, the device and the mnemonic (each a mono cell of
  the sidebar's Logs and of History › Query › Syslog by device's opened lines) are one line at
  1280 and 1920 px, in a real browser, on the lab's real captures; at phone width a token
  longer than its column scrolls inside its cell and the page never scrolls sideways. The
  review measured the tail at 1280 drawing "%SSH-4-SSH2_UNEXPECTED_MS" over "G".
- **Repeats are one row.** Identical adjacent lines (the same device, mnemonic, severity and
  words; their times aside) are one row, "×N" with the first and last times, opening to each
  line, by History's one grouping (`history_sources.runs`, C3399; `device_logs.line_runs`):
  on the tail, Syslog by device's lines (held and older) and a device's Logs tab. Every line
  is in exactly one run and in order, so the counts stay counts of lines, and the table says
  so when it folded any. A run's key is its oldest line's: a line arriving live that repeats
  it joins it, and the live merge keeps it the same open row.

On the lab's captures (tests/fixtures/loki/lines_r4.json and lines_s3.json, the review's 77
lines): only two lines are identical and adjacent (s3's %SSH-4-SSH2_UNEXPECTED_MSG at 21:05:23
and 07:13:05), so the tail draws 76 rows for 77 lines; r4's 57 %DBAL-4-DELAYED_BATCH lines
carry 57 different counters, so no two are identical.
"""

import json
import os
import re

import pytest

from modules import device_logs, history_sources, reader_job
from tests import test_logs_buffer as B
from tests import test_logs_tail as TT
from tests.test_logs_buffer import counted, data, page  # noqa: F401 (the fixtures)
from tests.test_logs_tail import _own_store, web  # noqa: F401 (the fixtures)
from tests.test_profile_apply import lab  # noqa: F401 (the fixture)


def _window():
    return TT._read()["lines"]


def _repeat(line, later_s):
    """*line* again, *later_s* seconds after it: a minimal edit of a real line (its time)."""
    import time
    ts = line["ts"] + later_s
    return dict(line, ts=ts, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)))


# ── the grouping ───────────────────────────────────────────────────────────────────────────

class TestTheGrouping:
    def test_the_review_s_77_lines_are_76_rows_every_line_in_order(self):
        lines = _window()
        runs = device_logs.line_runs(lines)
        assert len(lines) == 77 and len(runs) == 76
        assert [l for r in runs for l in r["lines"]] == lines
        assert [r["n"] for r in runs] == [len(r["lines"]) for r in runs]
        two = [r for r in runs if r["n"] > 1]
        assert len(two) == 1 and two[0]["n"] == 2
        assert {(l["dev"], l["mn"]) for l in two[0]["lines"]} == {
            ("s3", "%SSH-4-SSH2_UNEXPECTED_MSG")}
        # No run holds lines that differ in anything but their time.
        for r in runs:
            assert len({(l["dev"], l["mn"], l["sev"], l["text"]) for l in r["lines"]}) == 1
        # r4's delayed batches are 57 lines of 57 different counters: none folds.
        dbal = [l for l in lines if l["mn"] == "%DBAL-4-DELAYED_BATCH"]
        assert len(dbal) == 57 and len({l["text"] for l in dbal}) == 57

    @pytest.mark.parametrize("field,other", [("dev", "r9"), ("mn", "%SYS-5-CONFIG_I"),
                                             ("text", "a different message"), ("sev", 3)])
    def test_a_line_that_differs_in_anything_but_its_time_stands_alone(self, field, other):
        line = _window()[0]
        alike = [_repeat(line, 2), _repeat(line, 1), line]
        assert [r["n"] for r in device_logs.line_runs(alike)] == [3]
        alike[1] = dict(alike[1], **{field: other})
        assert [r["n"] for r in device_logs.line_runs(alike)] == [1, 1, 1]

    def test_identical_lines_apart_are_two_runs(self):
        a, b = _window()[0], _window()[-1]
        runs = device_logs.line_runs([_repeat(a, 3), _repeat(a, 2), b, a])
        assert [r["n"] for r in runs] == [2, 1, 1]

    def test_a_run_s_key_is_its_oldest_line_s_so_a_repeat_joining_it_keeps_it(self):
        line = _window()[0]
        before = device_logs.line_runs([_repeat(line, 1), line] + _window()[1:])
        after = device_logs.line_runs([_repeat(line, 2), _repeat(line, 1), line]
                                      + _window()[1:])
        assert before[0]["n"] == 2 and after[0]["n"] == 3
        assert before[0]["key"] == after[0]["key"]
        assert re.fullmatch(r"[A-Za-z0-9_.-]+", after[0]["key"]), after[0]["key"]

    def test_keys_are_unique_on_the_table(self):
        line, other = _window()[0], _window()[1]
        runs = device_logs.line_runs([line, line, other, line, line])
        keys = [r["key"] for r in runs]
        assert [r["n"] for r in runs] == [2, 1, 2] and len(set(keys)) == 3

    def test_a_device_s_own_lines_and_loki_s_older_ones_group_by_their_fields(self):
        """A device's held rows name the mnemonic `mnemonic` and no device; Loki's older ones
        carry no `ns`, only their received time."""
        held = {"ns": 10, "at_iso": "2026-10-10T21:19:18Z", "devts": "*Oct 10 21:19:18.1",
                "unsync": True, "mnemonic": "%LINK-3-UPDOWN", "sev": 3, "sev_word": "error",
                "kind": "danger", "text": "Interface Gi0/1, changed state to down"}
        runs = device_logs.line_runs([dict(held, ns=12, devts="*Oct 10 21:19:20.1"), held])
        assert [r["n"] for r in runs] == [2] and runs[0]["key"].startswith("10-")
        older = [{"at": "2026-10-10 21:19:20", "mnemonic": "%LINK-3-UPDOWN", "text": "x"},
                 {"at": "2026-10-10 21:19:18", "mnemonic": "%LINK-3-UPDOWN", "text": "x"}]
        runs = device_logs.line_runs(older)
        assert [r["n"] for r in runs] == [2] and "2026-10-10-21-19-18" in runs[0]["key"]

    def test_history_s_rows_still_group_by_their_own_fields(self):
        """One grouping, two samenesses: History's rows by `RUN_FIELDS`, unchanged."""
        row = {"kind": "measured", "what": "Show commands", "devices": ["r2"],
               "devices_words": "r2", "who": "a", "outcome": "", "marks": []}
        assert [len(r) for r in history_sources.runs([row, dict(row), dict(row, who="b")])] \
            == [2, 1]

# ── in a real browser ──────────────────────────────────────────────────────────────────────

#: An IOS-XE mnemonic longer than a phone's column holds (47 characters).
LONG = "%PLATFORM_INFRA-5-IOS_INTR_OVER_LIMIT_HOLD_DUMP"

READY = ("return !!window.htmx && !!window.Alpine && "
         "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')")

#: How many lines each token cell of the log tables in *doc* (arguments[0], or the page's
#: own) is drawn on: the distinct tops of its text's line boxes, 3 px apart or more. Also,
#: as the measure's own check, the first mnemonic's words in a 40 px box that may break
#: anywhere: more than one line, so a cell broken in two is seen.
TOKENS = """
var doc = arguments[0] ? document.getElementById(arguments[0]).contentDocument : document;
function lines(el) {
  var tops = [], w = doc.createTreeWalker(el, NodeFilter.SHOW_TEXT), t, r = doc.createRange();
  while ((t = w.nextNode())) {
    if (!t.textContent.trim()) continue;
    r.selectNodeContents(t);
    Array.prototype.forEach.call(r.getClientRects(), function (x) {
      var seen = tops.some(function (y) { return Math.abs(y - x.top) < 3; });
      if (x.width > 0 && !seen) tops.push(x.top);
    });
  }
  return tops.length;
}
var cells = doc.querySelectorAll('table.lg-lines td.mono, table.lg-lines .lg-run-lines time');
var out = [], n = 0;
for (var i = 0; i < cells.length; i++) {
  if (!cells[i].offsetParent) continue;
  n++;
  var k = lines(cells[i]);
  if (k !== 1) out.push(cells[i].textContent.trim() + ' on ' + k + ' lines');
}
var mn = Array.prototype.filter.call(cells, function (c) { return /^%/.test(c.textContent); })[0];
var box = doc.createElement('div');
box.style.width = '40px'; box.style.overflowWrap = 'anywhere'; box.style.fontFamily = 'monospace';
box.textContent = mn ? mn.textContent : '';
doc.body.appendChild(box);
var probe = lines(box);
box.remove();
var de = doc.documentElement;
return {cells: n, broken: out, probe: probe, mnemonics: mn ? 1 : 0,
        wide: de.scrollWidth - de.clientWidth, inner: doc.defaultView.innerWidth};
"""

#: A person opening every run of the page (in *doc*, arguments[0], or the page's own) by its
#: summary; how many were pressed.
OPEN = """
var doc = arguments[0] ? document.getElementById(arguments[0]).contentDocument : document;
var runs = doc.querySelectorAll('tr.lg-run details');
for (var i = 0; i < runs.length; i++) runs[i].querySelector('summary').click();
return runs.length;
"""

#: The page's runs as drawn now (in *doc*, as `OPEN`): per run its "×N", whether it is open,
#: how many of its lines are shown, each shown line's instant, how many show a device time and
#: the summary's words; the table's rows; and the page's words (its notes).
RUNS = """
var doc = arguments[0] ? document.getElementById(arguments[0]).contentDocument : document;
var runs = doc.querySelectorAll('tr.lg-run details');
return {runs: Array.prototype.map.call(runs, function (d) {
  var shown = Array.prototype.filter.call(d.querySelectorAll('li'),
                                          function (li) { return !!li.offsetParent; });
  return {n: d.querySelector('.lg-run-n').textContent.trim(), open: d.open, shown: shown.length,
          at: shown.map(function (li) { return li.querySelector('time').getAttribute('datetime')
                                                || li.querySelector('time').title; }),
          devts: shown.filter(function (li) { return !!li.querySelector('.mono'); }).length,
          summary: d.querySelector('summary').textContent.replace(/\\s+/g, ' ').trim()};
}), rows: doc.querySelectorAll('table.lg-lines > tbody > tr, table.log-table > tbody > tr').length,
   text: doc.body.textContent.replace(/\\s+/g, ' ')};
"""


def _browser():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tokens' lines are measured in one")
    return browser


@pytest.fixture
def tail_served(tmp_path, monkeypatch):
    """The sidebar's Logs served, the logs-tail reader's store this test's own, holding the
    review's 77 lines; yields (the server, the browser, a function storing other lines)."""
    browser = _browser()
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: reader_job.read_cached(name))
    path = reader_job.store_path("logs-tail")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    value = TT._read()

    def put(lines):
        doc = {"last_attempt": {"at": "2026-10-11T18:20:17Z", "ok": True, "error": ""},
               "last_good": {"value": dict(value, lines=lines),
                             "value_at": "2026-10-11T18:20:12Z"}}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)
    put(value["lines"])
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            yield srv, b, put
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


def _width(b, width):
    b._call("POST", f"/session/{b.session}/window/rect", {"width": width, "height": 1000})


@pytest.mark.parametrize("width", [1280, 1920])
def test_the_tail_s_time_device_and_mnemonic_never_break_at_desktop_widths(tail_served, width):
    """The review's 77 lines and the newest sent twice more; every run opened, so its lines'
    times are measured too."""
    srv, b, put = tail_served
    lines = _window()
    put([_repeat(lines[0], 2), _repeat(lines[0], 1)] + lines)
    _width(b, width)
    b.go(srv.url("/v2/logs?list=Lab"))
    b.wait_for(READY, 15)
    b.js(OPEN, "")
    opened = b.js(RUNS, "")
    assert [(r["n"], r["shown"]) for r in opened["runs"]] == [("×3", 3), ("×2", 2)], opened
    got = b.js(TOKENS, "")
    assert got["probe"] > 1, ("the measure sees a token broken in two", got)
    assert got["mnemonics"] and got["cells"] >= 3 * 70 + 5, got
    assert got["broken"] == [], got


def test_the_tail_draws_a_repeat_as_one_row_that_opens_to_each_line(tail_served):
    """79 lines (the review's 77, the newest sent twice more): 76 rows, the repeat one row
    "×3" with its first and last times, opened to its three lines, newest first, each at its
    own time; the counts are of lines, and the note under the table says so."""
    srv, b, put = tail_served
    lines = _window()
    top = [_repeat(lines[0], 2), _repeat(lines[0], 1)] + lines
    put(top)
    _width(b, 1280)
    b.go(srv.url("/v2/logs?list=Lab"))
    b.wait_for(READY, 15)
    b.js(OPEN, "")
    got = b.js(RUNS, "")
    first = got["runs"][0]
    assert [r["n"] for r in got["runs"]] == ["×3", "×2"] and got["rows"] == 76, got["runs"]
    assert first["open"] and first["at"] == [top[0]["at"], top[1]["at"], top[2]["at"]], first
    assert first["summary"].startswith(lines[0]["text"].strip()[:40]), first
    assert "79 lines in the last 15 minutes" in got["text"]
    assert "is one row, ×N, opening to each; every count here is of lines." in got["text"]


def test_a_repeat_arriving_live_draws_its_run_and_the_note(tail_served):
    """A window with no repeat draws a row a line and no note; a line arriving that repeats
    the newest makes that row "×2", and the note appears."""
    srv, b, put = tail_served
    lines = [l for i, l in enumerate(_window()) if i != 73]
    put(lines)
    _width(b, 1280)
    b.go(srv.url("/v2/logs?list=Lab"))
    b.wait_for(READY, 15)
    b.js(OPEN, "")
    before = b.js(RUNS, "")
    assert before["runs"] == [] and "every count here is of lines" not in before["text"]
    put([_repeat(lines[0], 1)] + lines)
    b.js("window.__settled = 0; document.addEventListener('htmx:afterSettle', function () {"
         " window.__settled++; }); htmx.trigger(document.body, 'nmas:logs'); return 1")
    b.wait_for("return window.__settled > 0 && "
               "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')", 15)
    b.js(OPEN, "")
    after = b.js(RUNS, "")
    assert [(r["n"], r["shown"]) for r in after["runs"]] == [("×2", 2)], after["runs"]
    assert after["rows"] == before["rows"], (before["rows"], after["rows"])
    assert "every count here is of lines" in after["text"]


def test_at_phone_width_a_long_token_scrolls_in_its_cell_and_the_page_never_sideways(
        tail_served, monkeypatch):
    """At 390 px (the page in a 390 px frame, as the layout tests hold a phone, its policy's
    `frame-ancestors 'none'` relaxed to `'self'` for this test alone): no token cell breaks,
    a mnemonic longer than its column scrolls inside its own cell (never the table's box),
    and the page itself is never wider than the screen. The review's mnemonics fit a phone's
    column, so the newest line is given one that does not, an IOS-XE mnemonic of 47
    characters (a minimal edit: its mnemonic and severity)."""
    from modules import csp
    monkeypatch.setattr(csp, "STRICT_POLICY", csp.STRICT_POLICY.replace(
        "frame-ancestors 'none'", "frame-ancestors 'self'"))
    srv, b, put = tail_served
    lines = _window()
    put([dict(lines[0], mn=LONG, sev=5)] + lines[1:])
    # Opened, the s3 pair's lines are measured too.
    _width(b, 1280)
    b.go(srv.url("/v2/logs?list=Lab"))
    b.wait_for(READY, 15)
    b.js("var f = document.createElement('iframe'); f.id = 'phone'; f.width = '390';"
         " f.height = '800'; f.style.position = 'fixed'; f.style.left = '0'; f.style.top = '0';"
         " f.style.border = '0'; f.style.zIndex = '9999'; f.src = arguments[0];"
         " document.documentElement.appendChild(f); return 1", srv.url("/v2/logs?list=Lab"))
    b.wait_for("var d = document.getElementById('phone').contentDocument;"
               " return !!(d && d.querySelector('table.lg-lines td.mono') && d.defaultView.htmx)",
               20)
    b.js(OPEN, "phone")
    opened = b.js(RUNS, "phone")
    assert [(r["n"], r["shown"]) for r in opened["runs"]] == [("×2", 2)], opened["runs"]
    got = b.js(TOKENS, "phone")
    assert got["inner"] <= 390 and got["probe"] > 1, got
    assert got["broken"] == [], got
    assert got["wide"] <= 0, ("the page scrolls sideways at phone width", got)
    long = b.js("var d = document.getElementById('phone').contentDocument;"
                "var c = Array.prototype.filter.call(d.querySelectorAll('table.lg-lines td.mono'),"
                " function (x) { return x.textContent.trim() === '" + LONG + "'; })[0];"
                "var w = c.closest('.table-wrap');"
                "return {cell: [c.scrollWidth, c.clientWidth],"
                " box: [w.scrollWidth, w.clientWidth]}")
    assert long["cell"][0] > long["cell"][1], ("the long mnemonic scrolls in its cell", long)
    assert long["box"][0] <= long["box"][1], ("the table's box does not scroll", long)


def test_a_line_arriving_live_joins_the_run_it_repeats_and_the_opened_run_stays_open(
        tail_served):
    srv, b, put = tail_served
    lines = _window()
    put([_repeat(lines[0], 1)] + lines)
    _width(b, 1280)
    b.go(srv.url("/v2/logs?list=Lab"))
    b.wait_for(READY, 15)
    before = b.js("var d = document.querySelector('#logs-tail tr.lg-run details');"
                  "if (!d) return {n: null, rows:"
                  " document.querySelectorAll('#logs-tail tbody > tr').length};"
                  "window.__run = d; window.__region = document.getElementById('logs-tail');"
                  "d.querySelector('summary').click();"
                  "return {n: d.querySelector('.lg-run-n').textContent, rows:"
                  " document.querySelectorAll('#logs-tail tbody > tr').length}")
    assert before["n"] == " ×2", ("the repeat is drawn as one row", before)
    b.wait_for("return window.__run.open", 5)
    put([_repeat(lines[0], 2), _repeat(lines[0], 1)] + lines)
    b.js("window.__settled = 0; document.addEventListener('htmx:afterSettle', function () {"
         " window.__settled++; }); htmx.trigger(document.body, 'nmas:logs'); return 1")
    b.wait_for("return window.__settled > 0 && "
               "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')", 15)
    after = b.js("var d = window.__run;"
                 "return {same: d.isConnected && document.querySelector("
                 "'#logs-tail tr.lg-run details') === d, open: d.open,"
                 " n: d.querySelector('.lg-run-n').textContent,"
                 " lines: d.querySelectorAll('li').length,"
                 " region: window.__region === document.getElementById('logs-tail'),"
                 " rows: document.querySelectorAll('#logs-tail tbody > tr').length}")
    assert after == {"same": True, "open": True, "n": " ×3", "lines": 3, "region": True,
                     "rows": before["rows"]}, after


@pytest.fixture
def query_served(query):
    """History › Query › Syslog by device served with r4 opened (`query`'s Loki and counts)."""
    browser = _browser()
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            yield srv, b
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


@pytest.mark.parametrize("width", [1280, 1920])
def test_syslog_by_device_s_lines_never_break_their_tokens(query_served, width):
    srv, b = query_served
    _width(b, width)
    b.go(srv.url("/v2/history/query/syslog?list=Lab&range=120d&sev=all&d=r4"))
    b.wait_for("return !!document.querySelector('#lg-older td.mono') && "
               + READY[len("return "):], 20)
    # Loki's older part draws r4's newest line, sent three times, as one row; opened, its
    # three lines, and the part's foot says what a row holds.
    b.js(OPEN, "")
    opened = b.js(RUNS, "")
    assert [(r["n"], r["shown"]) for r in opened["runs"]] == [("×3", 3)], opened["runs"]
    assert "50 older lines (a line repeated beside itself is one row, ×N)" in opened["text"]
    got = b.js(TOKENS, "")
    assert got["probe"] > 1 and got["mnemonics"] and got["cells"] >= 2 * 48, got
    assert got["broken"] == [], got


@pytest.fixture
def query(tmp_path, monkeypatch):
    """History › Query › Syslog by device on test_logs_v2's counts, its older lines answered by
    Loki with r4's real lines, the newest repeated twice more (its time moved)."""
    from types import SimpleNamespace

    from tests import test_logs_v2 as L
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.readers.adjacencies.lists",
                        lambda: [("Lab", SimpleNamespace(repo_dir=str(tmp_path)), L.MANAGED)])
    monkeypatch.setattr("modules.reader_job.read_cached_for",
                        lambda name, list_name: reader_job.read_cached(name))
    monkeypatch.setattr("modules.logs_page.time.time", lambda: L.NOW)
    monkeypatch.setattr("modules.logs_page._OLDER", {})
    answer = L._fx("lines_r4.json")["answer"]
    values = answer["data"]["result"][0]["values"]
    newest = max(values, key=lambda v: int(v[0]))
    values += [[str(int(newest[0]) + 1_000_000_000), newest[1]],
               [str(int(newest[0]) + 2_000_000_000), newest[1]]]

    class _R:
        def json(self):
            return answer
    monkeypatch.setattr("modules.integrations.loki.LokiIntegration._get",
                        lambda self, path, **p: {"ok": True, "response": _R()})
    L._store(L._read(previous=L._read()))
    import app as A
    return A.app.test_client()



def _repeated_r3():
    """test_logs_buffer's corpus (r3's and s3's real lines, at this run's time), r3's newest
    line that is no heartbeat sent twice more, a second and two seconds later."""
    ns, line = max(((n, l) for n, l in B.R3 if B.HEARTBEAT not in l), key=lambda x: x[0])
    return B.CORPUS + [(ns + 1_000_000_000, line), (ns + 2_000_000_000, line)]


def _served_open(url, ready):
    """*url* served in a real browser at 1280 px, every run on it opened (`OPEN`)."""
    browser = _browser()
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            _width(b, 1280)
            b.go(srv.url(url))
            b.wait_for(ready, 20)
            b.js(OPEN, "")
            return b.js(RUNS, "")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


def test_a_device_s_logs_tab_opens_a_repeat_to_each_line_with_its_device_time(
        lab, page):  # noqa: F811
    """r3's Logs tab, from the logs-tail reader's buffer (C3166) on test_logs_buffer's lab:
    r3's newest line sent three times is one row, its mnemonic before its words; opened, its
    three lines, each with its own device time."""
    B.store(B.fill(B.FakeLoki(_repeated_r3())))
    got = _served_open("/v2/device/r3?tab=logs",
                       "return !!document.querySelector('#logs table.log-table') && "
                       + READY[len("return "):])
    assert [(r["n"], r["shown"], r["devts"]) for r in got["runs"]] == [("×3", 3, 3)], got["runs"]
    assert re.match(r"%[A-Z0-9_]+-\d-[A-Z0-9_]+ ", got["runs"][0]["summary"]), got["runs"]
    assert "is one row, ×N, opening to each; every count here is of lines." in got["text"]


def test_syslog_by_device_s_held_lines_open_a_repeat_to_each_line(data, counted,
                                                                   monkeypatch):  # noqa: F811
    """Syslog by device with r3 opened over 24 h, its lines the logs-tail reader's buffer
    (C3166), Loki asked nothing: r3's newest line sent three times is one row, opened to its
    three lines; the lines' foot says what a row holds."""
    from types import SimpleNamespace

    from modules import logs_page
    from tests import test_logs_v2 as L
    (data / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(data / "lab"))
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    monkeypatch.setattr("modules.readers.adjacencies.lists",
                        lambda: [("Lab", SimpleNamespace(repo_dir=str(data)), L.MANAGED)])
    L._store(L._read(previous=L._read(), retention=730))
    monkeypatch.setattr(logs_page, "_OLDER", {})
    B.store(B.fill(B.FakeLoki(_repeated_r3())))
    got = _served_open("/v2/history/query/syslog?list=Lab&range=24h&sev=all&d=r3",
                       "return !!document.querySelector('table.lg-lines') && "
                       + READY[len("return "):])
    assert counted == [], "the page asked Loki"
    assert [(r["n"], r["shown"]) for r in got["runs"]] == [("×3", 3)], got["runs"]
    assert "a line repeated beside itself is one row, ×N, opening to each; every count here " \
           "is of lines" in got["text"]

