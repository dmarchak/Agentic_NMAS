"""A pressed v2 control that READS (`hx-get`) is busy on itself until its answer is drawn
(C4216; design/review/ACTIONS.md, 2026-11-23).

CLAUDE.md: "A v2 control is busy on itself until the answer arrives (never a timer) and the
result updates in place; no narration beside it." tests/test_v2_busy_on_itself.py holds it for
every control that POSTS (C1023). The controls that read were outside it: a device's tabs (the
NetBox tab asks NetBox three times, History reads git and about 50 stores), the DHCP and SDN
dialogs' links that ask Kea or the switches, Preview it again. htmx puts `htmx-request` on the
element that issues a request, but the stylesheet drew it only on a disabled `.btn` (a link is
never disabled) and on a menu row (C399), so 113 `<a class="btn" hx-get>`, 37 bare links and
the tabs showed nothing between the press and the answer.

**The one mechanism:** the stylesheet draws a pressed `<a>` or `<button>` carrying `hx-get`
while htmx marks it (`htmx-request`) as a menu row is drawn: the progress cursor and the
spinner after its label. htmx takes the class off once the answer is drawn, or the request
fails, so there is no timer. A control with busy words of its own (`op-busy`) shows those and
no spinner; a menu row keeps its own (C399).

**The population, by property:** every `<a>` or `<button>` in a v2 template carrying `hx-get`
that a person presses (no `hx-trigger`, or one starting with `click`). Its floor is read from
the scan; the browser tests click the real NetBox tab with its answer held, and two controls of
the other two shapes planted on the same page (a link drawn as a button, and a button with its
own busy words), against the real stylesheet and htmx.

**A press that loads another page** (Devices' Save… and Deploy…, History, Heartbeat,
Coverage) is busy on itself the same way until that page replaces this one: nmas_v2.js
`markNavigating` sets `aria-busy` on the link followed, or on the button that submitted a
form htmx does not send. No timer: the mark ends with the page, and a page restored from the
back/forward cache is loaded again. A press after which no page replaces this one is never
marked (a download, a new tab, a place on this page, another origin, htmx's own, a press
something else handled), so a mark can never stand; the attachment routes' links declare
`download`, by a scan, so that skip is complete.
"""

import os
import re
import threading

import pytest

from tests.test_persist_screen import lab  # noqa: F401 (the fixture: one list, r2)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(ROOT, "static", "css", "nmas-v2.css")

_REAL_THREAD = threading.Thread

TAG = re.compile(r"<(a|button)\b((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", re.S)
GETS = re.compile(r"\bhx-get\s*=")
TRIGGER = re.compile(r'\bhx-trigger\s*=\s*"([^"]*)"')


def pressed_gets(texts: dict) -> list:
    """``(path, line)`` of every `<a>` or `<button>` carrying `hx-get` a person presses."""
    out = []
    for path, text in texts.items():
        for m in TAG.finditer(text):
            attrs = m.group(2)
            if not GETS.search(attrs):
                continue
            trig = TRIGGER.search(attrs)
            if trig and not re.match(r"\s*click\b", trig.group(1)):
                continue
            out.append((path, text.count("\n", 0, m.start()) + 1))
    return out


def _v2_templates() -> dict:
    from tests.source_index import tracked
    return {os.path.relpath(p, ROOT): open(p, encoding="utf-8").read()
            for p in tracked("templates/v2", suffix=".html")}


def busy_rules(css: str) -> dict:
    """The stylesheet's rules for a pressed reading control, by selector: the declarations
    of each rule whose selector names ``[hx-get].htmx-request``."""
    rules = {}
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S)):
        sel, body = " ".join(m.group(1).split()), m.group(2)
        if "[hx-get].htmx-request" in sel:
            rules[sel] = {k.strip(): v.strip() for k, v in
                          (d.split(":", 1) for d in body.split(";") if ":" in d)}
    return rules


class TestThePopulation:
    def test_the_floor(self):
        found = pressed_gets(_v2_templates())
        # Measured 2026-11-24: 271 pressed `<a>` and `<button>` carrying hx-get.
        assert len(found) >= 200, len(found)
        paths = {p for p, _ in found}
        assert "templates/v2/device.html" in paths and "templates/v2/_dhcp_view.html" in paths

    def test_the_scan_finds_each_shape_and_leaves_the_unpressed(self):
        planted = {"t.html": (
            '<a class="btn" hx-get="/x">A</a>\n'
            '<button hx-get="/y" hx-trigger="click once">B</button>\n'
            '<a hx-get="/z" hx-trigger="nmas:devices from:body">C</a>\n'
            '<div hx-get="/w">D</div>\n'
            '<a href="/v">E</a>\n')}
        assert pressed_gets(planted) == [("t.html", 1), ("t.html", 2)]


class TestTheStylesheet:
    def test_a_pressed_reading_control_is_drawn_busy_on_itself(self):
        rules = busy_rules(open(CSS, encoding="utf-8").read())
        plain = [d for s, d in rules.items() if not s.endswith("::after")]
        after = [d for s, d in rules.items() if s.endswith("::after")]
        assert any(d.get("cursor") == "progress" for d in plain), rules
        assert any(d.get("content") == '""' and "nmas-spin" in d.get("animation", "")
                   for d in after), rules

    def test_the_reader_finds_a_planted_rule_and_skips_others(self):
        planted = ("/* [hx-get].htmx-request { cursor: progress; } */\n"
                   "a[hx-get].htmx-request { cursor: progress; }\n"
                   ".btn.htmx-request:disabled { opacity: .7; }\n")
        assert busy_rules(planted) == {"a[hx-get].htmx-request": {"cursor": "progress"}}


# ------------------------------------------------ pressed in a real browser, answer held

TAB = 'a.tab[hx-get*="/r2/netbox?"]'
STYLE = ("var x = document.querySelector(arguments[0]); var a = getComputedStyle(x, '::after');"
         "return {busy: x.classList.contains('htmx-request'), cursor: getComputedStyle(x).cursor,"
         " after: a.content, spin: a.animationName};")


def _browser_or_skip():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the scans above still run")
    return browser


@pytest.fixture
def held_tab(lab, monkeypatch):  # noqa: F811
    """The real app served on loopback, the NetBox tab's answer held until the test lets it
    answer (or fail)."""
    browser = _browser_or_skip()
    import app as A
    from routes import device_v2

    monkeypatch.setattr(threading, "Thread", _REAL_THREAD)
    gate, asked = threading.Event(), threading.Event()
    real = device_v2._netbox_ctx
    state = {"fail": False}

    def held(*a, **k):
        asked.set()
        assert gate.wait(30), "the test never let the tab answer"
        if state["fail"]:
            raise RuntimeError("planted: the NetBox tab failed")
        return real(*a, **k)
    monkeypatch.setattr(device_v2, "_netbox_ctx", held)
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/device/r2"))
            b.wait_for("return !!window.Alpine && !!window.htmx && "
                       "!document.querySelector('.htmx-request, .htmx-settling')", 15)
            yield {"b": b, "gate": gate, "asked": asked, "state": state}
        finally:
            gate.set()
            b.go("about:blank")
            browser.close_socketio_sessions()


def _plant(b, html):
    """A control of another shape on the same page, against the real stylesheet and htmx."""
    b.js("var d = document.createElement('div'); d.id = 't-planted'; d.innerHTML = arguments[0];"
         "document.querySelector('.tabs').after(d); htmx.process(d); return 1", html)


class TestPressedInABrowser:
    def test_the_tab_is_busy_on_itself_until_its_answer_is_drawn(self, held_tab):
        s, b = held_tab, held_tab["b"]
        assert b.js(STYLE, TAB)["after"] == "none"
        b.click(TAB)
        assert s["asked"].wait(10), "the click asked nothing"
        got = b.js(STYLE, TAB)
        assert got["busy"] and got["cursor"] == "progress", got
        assert got["after"] == '""' and got["spin"] == "nmas-spin", got
        s["gate"].set()
        b.wait_for("return !!document.querySelector('#tab-body #netbox') && "
                   "!document.querySelector('.tabs .htmx-request')", 15)
        got = b.js(STYLE, TAB)
        assert not got["busy"] and got["after"] == "none" and got["cursor"] != "progress", got

    def test_an_answer_that_fails_frees_it_too(self, held_tab):
        s, b = held_tab, held_tab["b"]
        s["state"]["fail"] = True
        b.click(TAB)
        assert s["asked"].wait(10)
        assert b.js(STYLE, TAB)["busy"]
        s["gate"].set()
        b.wait_for(f"return !document.querySelector('{TAB}').classList.contains('htmx-request')",
                   15)
        assert b.js(STYLE, TAB)["after"] == "none"

    def test_a_link_drawn_as_a_button_shows_the_spinner(self, held_tab):
        s, b = held_tab, held_tab["b"]
        _plant(b, '<a class="btn" id="t-link" href="/v2/device/r2?tab=netbox" '
                  'hx-get="/v2/device/r2/netbox" hx-target="#tab-body">Open NetBox…</a>')
        b.click("#t-link")
        assert s["asked"].wait(10)
        got = b.js(STYLE, "#t-link")
        assert got["busy"] and got["cursor"] == "progress" and got["spin"] == "nmas-spin", got
        s["gate"].set()
        b.wait_for("return !document.querySelector('#t-link.htmx-request')", 15)

    def test_a_control_with_its_own_busy_words_shows_them_and_no_spinner(self, held_tab):
        s, b = held_tab, held_tab["b"]
        _plant(b, '<button type="button" class="btn" id="t-words" hx-get="/v2/device/r2/netbox"'
                  ' hx-target="#tab-body" hx-disabled-elt="this"><span class="op-idle">Read'
                  '</span><span class="op-busy">Reading NetBox…</span></button>')
        b.click("#t-words")
        assert s["asked"].wait(10)
        got = b.js(STYLE, "#t-words")
        assert got["busy"] and got["after"] == "none", got
        assert b.js("return document.querySelector('#t-words').innerText.trim()") == \
            "Reading NetBox…"
        s["gate"].set()
        b.wait_for("return !document.querySelector('#t-words.htmx-request')", 15)


# ------------------------------------------------ a press that loads another page

ASKED = re.compile(r"\bif\b.*request\.args\.get\(\s*[\"'](\w+)[\"']")


def attachment_endpoints(app) -> dict:
    """Every endpoint whose view can answer a file (`Content-Disposition: attachment`), read
    from the view's own source: the endpoint, and the request argument that asks for the file
    when the view answers a page otherwise (the hand-over's ``download=md``), else None."""
    import inspect
    out = {}
    for name, fn in app.view_functions.items():
        try:
            lines = inspect.getsource(inspect.unwrap(fn)).splitlines()
        except (OSError, TypeError):
            continue
        at = [i for i, ln in enumerate(lines) if "attachment" in ln
              and ("Content-Disposition" in ln or "as_attachment" in ln
                   or "Content-Disposition" in "".join(lines[max(0, i - 2):i]))]
        if not at:
            continue
        asked = None
        if any("render_template" in ln for ln in lines):
            for ln in reversed(lines[max(0, at[0] - 6):at[0]]):
                m = ASKED.search(ln)
                if m:
                    asked = m.group(1)
                    break
        out[name] = asked
    return out


def links_without_download(texts: dict, endpoints: dict) -> list:
    """``(path, line, endpoint)`` of each `<a>` whose href names one of *endpoints* by
    `url_for` (passing its file's argument, where it has one) and that does not declare
    `download`."""
    out = []
    for path, text in texts.items():
        for m in re.finditer(r"<a\b((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", text, re.S):
            href = re.search(r"\bhref=\"\{\{\s*url_for\(\s*['\"]([\w.]+)['\"]([^}]*)\}\}",
                             m.group(1))
            if not href or href.group(1) not in endpoints:
                continue
            asked = endpoints[href.group(1)]
            if asked and not re.search(rf"\b{asked}\s*=", href.group(2)):
                continue
            # The attribute itself, never the word inside a value (`download='md'` in the href).
            if not re.search(r"\sdownload\b", re.sub(r"\"[^\"]*\"|'[^']*'", '""', m.group(1))):
                out.append((path, text.count("\n", 0, m.start()) + 1, href.group(1)))
    return out


class TestEveryFileLinkDeclaresDownload:
    """A file never unloads the page, so `markNavigating` skips a link declaring `download`;
    a link to a file without it would be marked busy and stay so."""

    def test_the_attachment_routes_are_found(self):
        import app as A
        found = attachment_endpoints(A.app)
        # Measured 2026-11-24: 8 views answering a file.
        assert len(found) >= 6, found
        assert found["v2.history_export_download"] is None and "sdn_v2.log_download" in found
        assert found["fixit_v2.handover_page"] == "download"

    def test_every_link_to_one_declares_download(self):
        import app as A
        assert links_without_download(_v2_templates(), attachment_endpoints(A.app)) == []

    def test_the_scan_finds_a_planted_link(self):
        planted = {"t.html": (
            "<a class=\"btn\" href=\"{{ url_for('v2.history_export_download', kind='x') }}\">X</a>\n"
            "<a href=\"{{ url_for('v2.history_export_download') }}\" download>Y</a>\n"
            "<a href=\"{{ url_for('v2.history_page') }}\">Z</a>\n"
            "<a href=\"{{ url_for('fixit_v2.handover_page', version=1) }}\">The page</a>\n"
            "<a href=\"{{ url_for('fixit_v2.handover_page', download='md') }}\">The file</a>\n")}
        got = links_without_download(planted, {"v2.history_export_download": None,
                                               "fixit_v2.handover_page": "download"})
        assert got == [("t.html", 1, "v2.history_export_download"),
                       ("t.html", 5, "fixit_v2.handover_page")]


@pytest.fixture
def held_page(lab, monkeypatch):  # noqa: F811
    """The real app served on loopback, History's page held until the test lets it answer."""
    browser = _browser_or_skip()
    import app as A

    monkeypatch.setattr(threading, "Thread", _REAL_THREAD)
    gate, asked = threading.Event(), threading.Event()
    real = A.app.view_functions["v2.history_page"]

    def held(*a, **k):
        asked.set()
        assert gate.wait(30), "the test never let the page answer"
        return real(*a, **k)
    monkeypatch.setitem(A.app.view_functions, "v2.history_page", held)
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url("/v2/device/r2"))
            b.wait_for("return !!window.Alpine && !!window.htmx && "
                       "!document.querySelector('.htmx-request, .htmx-settling')", 15)
            b.js("window.__before = 1; return 1")
            yield {"b": b, "gate": gate, "asked": asked}
        finally:
            gate.set()
            b.go("about:blank")
            browser.close_socketio_sessions()


NAV = 'a.nav-item[href^="/v2/history"]'
ARIA = "var x = document.querySelector(arguments[0]); return x && x.getAttribute('aria-busy');"
#: The page that answered is the new one: the old page's marker is gone with it.
REPLACED = "return !window.__before && location.pathname === '/v2/history'"


class TestAPressThatLoadsAPage:
    def test_the_sidebar_link_is_busy_until_its_page_replaces_this_one(self, held_page):
        s, b = held_page, held_page["b"]
        assert b.js(ARIA, NAV) is None
        b.click(NAV)
        assert s["asked"].wait(10), "the click asked for no page"
        assert b.js(ARIA, NAV) == "true"
        got = b.js(STYLE, NAV)
        assert got["cursor"] == "progress" and got["spin"] == "nmas-spin", got
        s["gate"].set()
        b.wait_for(REPLACED, 20)
        assert b.js(ARIA, NAV) is None

    def test_a_plain_forms_button_is_busy_until_its_page_replaces_this_one(self, held_page):
        s, b = held_page, held_page["b"]
        _plant(b, '<form method="get" action="/v2/history"><button type="submit" class="btn"'
                  ' id="t-go">Open History</button></form>')
        b.click("#t-go")
        assert s["asked"].wait(10)
        assert b.js(ARIA, "#t-go") == "true"
        assert b.js(STYLE, "#t-go")["spin"] == "nmas-spin"
        s["gate"].set()
        b.wait_for(REPLACED, 20)

#: Fake elements and events for `navigatingControl` in duktape: `a(attrs, url)` a link
#: (its parsed address: origin, path, query, hash), `button(attrs)`, `form(attrs)`; the page
#: is LOC, `/v2/device/r2` on this origin.
DUK_FIXTURE = (
    "var LOC = {origin: 'http://h', pathname: '/v2/device/r2', search: ''};\n"
    "function el(tag, attrs) { attrs = attrs || {}; var e = {tagName: tag,"
    " target: attrs.target || '',"
    " hasAttribute: function (n) { return Object.prototype.hasOwnProperty.call(attrs, n); },"
    " getAttribute: function (n) { return this.hasAttribute(n) ? attrs[n] : null; },"
    " closest: function () { return tag === 'A' ? e : null; }}; return e; }\n"
    "function a(attrs, url) { var e = el('A', attrs); url = url || ['http://h', '/v2/history'];"
    " e.origin = url[0]; e.pathname = url[1]; e.search = url[2] || ''; e.hash = url[3] || '';"
    " return e; }\n"
    "function click(x, more) { var e = {type: 'click', button: 0, target: x,"
    " defaultPrevented: false}; for (var k in (more || {})) e[k] = more[k]; return e; }\n"
    "function submit(f, s) { return {type: 'submit', target: f, submitter: s,"
    " defaultPrevented: false}; }\n")


class TestWhichPressIsMarked:
    """`navigatingControl`, the one choice `markNavigating` makes, run in duktape: a press is
    marked only when a page will replace this one."""

    CASES = {
        "a link to another page": ("x = a({href: '/v2/history'}); e = click(x)", True),
        "a download": ("x = a({href: '/v2/history', download: ''}); e = click(x)", False),
        "a new tab": ("x = a({href: '/v2/history', target: '_blank'}); e = click(x)", False),
        "a modifier": ("x = a({href: '/v2/history'}); e = click(x, {ctrlKey: true})", False),
        "the middle button": ("x = a({href: '/v2/history'}); e = click(x, {button: 1})", False),
        "handled already": ("x = a({href: '/v2/history'});"
                            " e = click(x, {defaultPrevented: true})", False),
        "a place on this page": ("x = a({href: '#here'}, ['http://h', '/v2/device/r2', '',"
                                 " '#here']); e = click(x)", False),
        "this page's place by path": ("x = a({href: '/v2/device/r2#n'}, ['http://h',"
                                      " '/v2/device/r2', '', '#n']); e = click(x)", False),
        "another origin": ("x = a({href: 'https://example.invalid/'},"
                           " ['https://example.invalid', '/']); e = click(x)", False),
        "htmx's own": ("x = a({href: '/v2/history', 'hx-get': '/v2/history'}); e = click(x)",
                       False),
        "a refused link": ("x = a({href: '/v2/history', 'aria-disabled': 'true'});"
                           " e = click(x)", False),
        "a plain form's button": ("x = el('BUTTON'); e = submit(el('FORM'), x)", True),
        "an htmx form": ("x = el('BUTTON'); e = submit(el('FORM', {'hx-get': '/x'}), x)", False),
        "a form to a new tab": ("x = el('BUTTON', {formtarget: '_blank'});"
                                " e = submit(el('FORM'), x)", False),
        "a form a script sent": ("x = null; e = submit(el('FORM'), null)", False),
    }

    def test_the_choice(self):
        import json
        import dukpy
        src = open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
        cases = ",\n".join(f"{json.dumps(k)}: (function () {{ var x, e; {js};"
                           " var got = window.NMAS_V2.navigatingControl(e, LOC);"
                           " return got !== null && got === x; })()"
                           for k, (js, _) in self.CASES.items())
        got = json.loads(dukpy.evaljs("var window = {};\n" + src + "\n" + DUK_FIXTURE
                                      + "JSON.stringify({" + cases + "});"))
        assert got == {k: want for k, (_, want) in self.CASES.items()}
