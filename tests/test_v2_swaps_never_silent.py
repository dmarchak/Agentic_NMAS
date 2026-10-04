"""No v2 action goes quiet (C385, C388).

C385: Credentials' "Export the record…" and "Check a break-glass file…" did nothing on the
host. Both sat inside `#bg-record`, whose `hx-select="#bg-record"` (for its own refresh) htmx
passes down, so each answer was filtered to nothing and an empty slot swapped in. The third
occurrence of the shape (C338 was History's Baselines card). Two checks end the class:

- STRUCTURAL, over every v2 template: an element that makes a request (hx-get, hx-post, …)
  inside an ancestor carrying hx-select fails unless it sets its own hx-select or an ancestor
  between them disinherits it; and the shape itself, an element carrying hx-select passes
  nothing down (`hx-disinherit` naming hx-select, or `*`), so what reaches it through an
  include, a macro or a script cannot inherit it either.
- AT RUN TIME (C388), in `static/js/nmas_v2.js`: a selection matching nothing, an answer that
  is not a drawn fragment (a 4xx or 5xx of JSON, a whole error page) and a request with no
  answer each say "Couldn't load: <why>" in place, keeping what the target showed; a drawn
  refusal (an HTML fragment, whatever its status) is the server's answer and is drawn.
"""
import glob
import json
import os
import re
from html.parser import HTMLParser

import dukpy
import pytest

from tests.test_credentials_v2 import page  # noqa: F401  (the lab with a list and its record)
from tests.test_breakglass_export import lab  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2 = os.path.join(ROOT, "templates", "v2")
REQUESTS = ("hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete")
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
        "track", "wbr"}


def _neutral(src):
    """The template as markup: comments and statements gone, every expression one word (an
    expression's quotes would otherwise end the attribute holding it)."""
    src = re.sub(r"\{#.*?#\}", "", src, flags=re.S)
    src = re.sub(r"\{%.*?%\}", "", src, flags=re.S)
    return re.sub(r"\{\{.*?\}\}", "X", src, flags=re.S)


def _get(attrs, name):
    """An htmx attribute's value (its data- form too); None when absent."""
    for key in (name, "data-" + name):
        if key in attrs:
            return attrs[key] or ""
    return None


def _covers(disinherit):
    return disinherit is not None and (disinherit.strip() == "*" or "hx-select" in disinherit.split())


class _Scan(HTMLParser):
    """Each requesting element's inherited hx-select, resolved as htmx 2 resolves it (its own,
    else the nearest ancestor's, stopped by an hx-disinherit naming it), and each element
    carrying hx-select that passes it down."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.inherits, self.passes_down, self.requests = [], [], [], 0

    def _element(self, tag, attrs):
        a = {k: v for k, v in attrs}
        line = self.getpos()[0]
        own = _get(a, "hx-select")
        if own not in (None, "unset") and not _covers(_get(a, "hx-disinherit")):
            self.passes_down.append((line, tag, own))
        if any(_get(a, r) is not None for r in REQUESTS):
            self.requests += 1
            if own is None:
                for anc_line, anc_tag, anc in reversed(self.stack):
                    if _covers(_get(anc, "hx-disinherit")):
                        break
                    sel = _get(anc, "hx-select")
                    if sel is not None:
                        if sel != "unset":
                            self.inherits.append((line, tag, anc_line, sel))
                        break
        return line, a

    def handle_starttag(self, tag, attrs):
        line, a = self._element(tag, attrs)
        if tag not in VOID:
            self.stack.append((line, tag, a))

    def handle_startendtag(self, tag, attrs):
        self._element(tag, attrs)

    def handle_endtag(self, tag):
        if any(t == tag for _l, t, _a in self.stack):
            while self.stack and self.stack.pop()[1] != tag:
                pass


def scan(src):
    s = _Scan()
    s.feed(_neutral(src))
    s.close()
    return s


def _templates():
    return sorted(glob.glob(os.path.join(V2, "**", "*.html"), recursive=True))


class TestTheScanFindsTheShape:
    """The scan, on planted markup whose answer is known without it."""

    def test_a_link_inside_a_selecting_card_inherits_it(self):
        s = scan('<section id="r" hx-get="/r" hx-select="#r">\n<div>'
                 '<a hx-get="/export" hx-target="#op">Export</a></div></section>')
        assert [(t, sel) for _l, t, _al, sel in s.inherits] == [("a", "#r")]
        assert [sel for _l, _t, sel in s.passes_down] == ["#r"]

    def test_the_card_as_it_was_on_the_host_is_found(self):
        """C385's markup, the record's own lines with its Jinja."""
        src = ('<section class="op-card{{ " op-ok" if s else " op-muted" }}" id="bg-record" '
               'hx-get="{{ url_for(\'v2.credentials\', list=list_name) }}" hx-select="#bg-record"\n'
               '  hx-trigger="nmas:job_health from:body" hx-swap="outerHTML"{% if oob %} '
               'hx-swap-oob="true"{% endif %}>\n  <div class="op-hd"><h2>x</h2>\n'
               '    <div class="op-hd-actions"><a class="btn" href="/x" hx-get="{{ u }}" '
               'hx-target="#bg-op" hx-swap="innerHTML">Export the record…</a>{{ how() }}'
               '<a class="btn" hx-get="{{ c }}" hx-target="#bg-op">Check…</a></div></div>\n</section>')
        assert len(scan(src).inherits) == 2

    @pytest.mark.parametrize("markup", [
        '<section hx-get="/r" hx-select="#r" hx-disinherit="*"><a hx-get="/e">E</a></section>',
        '<section hx-get="/r" hx-select="#r" hx-disinherit="hx-target hx-select"><a hx-get="/e">E</a></section>',
        '<section hx-select="#r" hx-disinherit="*"><div hx-disinherit="*"><a hx-post="/e">E</a></div></section>',
        '<section hx-select="#r" hx-disinherit="*"><a hx-get="/help" hx-select="unset">?</a></section>',
    ])
    def test_its_own_select_or_a_disinherit_stops_it(self, markup):
        assert scan(markup).inherits == []

    def test_a_disinherit_between_stops_it_but_the_card_still_passes_down(self):
        s = scan('<section hx-select="#r"><div hx-disinherit="*"><a hx-get="/e">E</a></div></section>')
        assert s.inherits == [] and len(s.passes_down) == 1

    def test_a_disinherit_naming_something_else_does_not(self):
        s = scan('<section hx-select="#r" hx-disinherit="hx-target"><a hx-get="/e">E</a></section>')
        assert len(s.inherits) == 1 and len(s.passes_down) == 1

    def test_a_closed_card_passes_nothing_to_what_follows(self):
        assert scan('<section hx-select="#r" hx-disinherit="*"></section><a hx-get="/e">E</a>'
                    '<div hx-select="#d" hx-disinherit="*"></div>').inherits == []


class TestEveryV2Template:
    def test_the_population(self):
        """A floor under what the scan reads, so a scan that read nothing cannot pass."""
        files = _templates()
        assert len(files) >= 50, files
        requests = sum(scan(open(f, encoding="utf-8").read()).requests for f in files)
        assert requests >= 70, requests      # 73 on 2026-10-03, by the scan and by a grep

    def test_no_request_inherits_a_select(self):
        found = []
        for path in _templates():
            for line, tag, anc_line, sel in scan(open(path, encoding="utf-8").read()).inherits:
                found.append(f"{os.path.relpath(path, ROOT)}:{line}: <{tag}> inherits "
                             f"hx-select={sel!r} from line {anc_line}; its answer is filtered "
                             "to that and may swap in nothing (C385)")
        assert not found, ("set the element's own hx-select, or hx-disinherit on the container:\n"
                           + "\n".join(found))

    def test_every_selecting_element_passes_nothing_down(self):
        found = []
        for path in _templates():
            for line, tag, sel in scan(open(path, encoding="utf-8").read()).passes_down:
                found.append(f"{os.path.relpath(path, ROOT)}:{line}: <{tag} hx-select={sel!r}> "
                             "without hx-disinherit naming hx-select (or *)")
        assert not found, ("what reaches it by an include, a macro or a script would inherit "
                           "it:\n" + "\n".join(found))


# ------------------------------------------------------------ the words, in duktape

def _eval(expr):
    with open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8") as fh:
        js = fh.read()
    return json.loads(dukpy.evaljs("var window = {};\n" + js +
                                   f"\nJSON.stringify(window.NMAS_V2.{expr});"))


class TestTheWords:
    def test_a_drawn_fragment_is_the_servers_answer(self):
        assert _eval("isFragment('<section>No list</section>', 'text/html; charset=utf-8')") is True
        assert _eval("isFragment('Refused: the hash moved', 'text/html')") is True

    @pytest.mark.parametrize("body,ctype", [
        ('{"ok": false}', "application/json"),
        ("<!doctype html><title>500</title>", "text/html"),
        ("<html><body>x</body></html>", "text/html"),
        ("   ", "text/html"),
        ("", "text/html"),
    ])
    def test_anything_else_is_not(self, body, ctype):
        assert _eval(f"isFragment({json.dumps(body)}, {json.dumps(ctype)})") is False

    def test_why_comes_from_the_answer(self):
        got = _eval("failWords(404, 'NOT FOUND', JSON.stringify({ok: false, error: 'There is no "
                    "device list named X.'}), 'application/json')")
        assert got == "There is no device list named X. (HTTP 404 NOT FOUND)"
        got = _eval("failWords(500, 'INTERNAL SERVER ERROR', '<!doctype html>\\n<title>500 "
                    "Internal Server Error</title>', 'text/html')")
        assert got == ("500 Internal Server Error "
                       "(HTTP 500 INTERNAL SERVER ERROR)")
        assert _eval("couldntWords('the 6-hour view', false)") == "Couldn't load the 6-hour view."
        assert _eval("couldntWords('', true)") == "Couldn't load this card."
        assert _eval("couldntWords('', false)") == "Couldn't load this view."
        assert _eval("failWords(502, 'Bad Gateway', '', 'text/plain')") == \
            "the server answered HTTP 502 Bad Gateway"


# ------------------------------------------------------------ in a real browser

PROBE = ('<div id="probe"><div id="probe-sel">'
         '<a id="probe-a" hx-select="#nothing-here" hx-get="/v2/help/credentials/panel" hx-target="#probe-out" '
         'hx-swap="innerHTML">a</a></div>'
         '<a id="probe-json" hx-get="/v2/credentials?list=No-Such-List" hx-target="#probe-out" '
         'hx-swap="innerHTML">b</a>'
         '<a id="probe-page" hx-get="/v2/no-such-page" hx-target="#probe-out" '
         'hx-swap="innerHTML">c</a>'
         '<a id="probe-frag" hx-get="/v2/help/no-such-page/panel" hx-target="#probe-out" '
         'hx-swap="innerHTML">d</a>'
         '<a id="probe-ok" hx-get="/v2/help/credentials/panel" hx-target="#probe-out" '
         'hx-swap="innerHTML">e</a>'
         '<div id="probe-out"><p id="kept">what it showed</p></div></div>')


def test_a_real_browser_says_couldnt_load_in_place(page):
    """Each failure in place, over what the target showed; then a good answer clears it."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    from tests.test_credentials_v2 import LIST
    # What a person reads, then the technical reason on hover (C409).
    words = ("var n = document.querySelector('#probe-out [data-couldnt] p');"
             "return n ? n.textContent + ' | ' + n.title : ''")
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url(f"/v2/credentials?list={LIST}"))
            b.wait_for("return window.htmx && window.Alpine && document.querySelector('#bg-record')")

            def probe(which):
                b.js("var old = document.getElementById('probe'); if (old) old.remove();"
                     "document.querySelector('main').insertAdjacentHTML('afterbegin', arguments[0]);"
                     "htmx.process(document.getElementById('probe'));", PROBE)
                b.js(f"document.getElementById('{which}').click();")

            probe("probe-a")
            b.wait_for(words + ".indexOf('nothing matching #nothing-here') >= 0", 10)
            assert b.js("return !!document.getElementById('kept')"), "what it showed is kept"

            probe("probe-json")
            b.wait_for(words + ".indexOf('There is no device list named') >= 0", 10)
            assert "HTTP 404" in b.js(words)

            probe("probe-page")
            b.wait_for(words + ".indexOf(\"Couldn't load\") >= 0", 10)
            assert "404" in b.js(words) and b.js("return !!document.getElementById('kept')")

            probe("probe-frag")      # a drawn refusal, status 404: drawn, never "couldn't load"
            b.wait_for("return !document.getElementById('kept') && "
                       "document.querySelector('#probe-out').textContent.trim().length > 0", 10)
            assert not b.js(words)

            probe("probe-a")
            b.wait_for(words + ".length > 0", 10)
            b.js("document.getElementById('probe-ok').click();")
            b.wait_for("return !document.querySelector('#probe-out [data-couldnt]') && "
                       "!document.getElementById('kept')", 10)
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
