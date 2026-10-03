"""The page the browser receives is the page the tool sent (C389), and says so when it is not.

The operator, 2026-10-03: a proxy in front of the tool rewrote the pages on the way out,
injecting an email decoder (`/cdn-cgi/…/email-decode.min.js`) and an analytics beacon
(`static.cloudflareinsights.com`), so the host's served HTML was not what the tests see. Two
defences, either enough alone:

- every HTML answer carries `Cache-Control: no-transform` (tests/test_cache_policy.py);
- the served page checks itself (`static/js/nmas_v2.js`, `injectedScripts`): every script a
  v2 page loads is the tool's own, from /static/, so any other was added on the way, and the
  page says so at its top with what to do. The premise is held here too: no v2 template loads
  a script from anywhere but /static/.

The live dot's served word (C390): before any script runs it says "Connecting", never "Live";
the live state is the script's to draw.
"""
import glob
import json
import os
import re

import dukpy
import pytest

from tests.test_breakglass_export import lab  # noqa: F401
from tests.test_credentials_v2 import page  # noqa: F401  (the lab with a list and its record)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGIN = "https://nmas.example"


def _eval(expr):
    with open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8") as fh:
        js = fh.read()
    return json.loads(dukpy.evaljs("var window = {};\n" + js +
                                   f"\nJSON.stringify(window.NMAS_V2.{expr});"))


class TestWhatCountsAsAdded:
    def test_the_tools_own_scripts_are_not(self):
        got = _eval(f"injectedScripts([['{ORIGIN}/static/js/nmas_v2.js?v=1', null], "
                    f"['{ORIGIN}/static/js/vendor/htmx.org/htmx.min.js?v=2', ''], "
                    "['', 'application/json']], '" + ORIGIN + "')")
        assert got == []

    def test_a_proxys_and_an_inline_one_are(self):
        got = _eval("injectedScripts(["
                    f"['{ORIGIN}/cdn-cgi/scripts/5c5dd728/cloudflare-static/email-decode.min.js', null], "
                    "['https://static.cloudflareinsights.com/beacon.min.js', 'text/javascript'], "
                    f"['{ORIGIN}/static-lookalike/x.js', null], "
                    "['https://other.example/static/x.js', null], "
                    "['', null]], '" + ORIGIN + "')")
        assert got == [f"{ORIGIN}/cdn-cgi/scripts/5c5dd728/cloudflare-static/email-decode.min.js",
                       "https://static.cloudflareinsights.com/beacon.min.js",
                       f"{ORIGIN}/static-lookalike/x.js", "https://other.example/static/x.js",
                       "(an inline script)"]

    def test_the_words_say_what_and_what_to_do(self):
        words = _eval("rewrittenWords(['https://static.cloudflareinsights.com/beacon.min.js'])")
        assert words.startswith("This page arrived changed: 1 script the tool did not send "
                                "(https://static.cloudflareinsights.com/beacon.min.js) was added")
        assert "Turn off page rewriting at the proxy" in words


class TestThePremise:
    def test_every_v2_script_is_the_tools_own(self):
        """What the check assumes stays true: no v2 template loads a script from anywhere but
        /static/ (inline ones would be refused by the strict policy anyway)."""
        found, scripts = [], 0
        for path in sorted(glob.glob(os.path.join(ROOT, "templates", "v2", "**", "*.html"),
                                     recursive=True)):
            for m in re.finditer(r"<script\b[^>]*>", open(path, encoding="utf-8").read()):
                scripts += 1
                if not re.search(r"""src="\{\{ url_for\('static', filename='[^']+'\) \}\}\"""",
                                 m.group(0)):
                    found.append(f"{os.path.relpath(path, ROOT)}: {m.group(0)}")
        assert scripts >= 12, scripts     # base.html's own: 12 on 2026-10-03 (lines 14, 17-27)
        assert not found, found

    def test_the_premise_scan_finds_a_planted_one(self):
        tag = '<script src="https://cdn.example/x.js"></script>'
        assert not re.search(r"""src="\{\{ url_for\('static', filename='[^']+'\) \}\}\"""", tag)


def test_the_served_live_word_never_claims_live(page):
    """C390: before a script runs, the dot's word is "Connecting"; "Live" is drawn only once
    the channel connects (nmas_v2.js, liveWords)."""
    html = page["client"].get("/v2/credentials?list=Lab").get_data(as_text=True)
    m = re.search(r'id="nmas-live" data-live="([a-z_]+)">.*?<span class="live-word">([^<]*)<',
                  html, re.S)
    assert m and m.group(1) == "unknown" and m.group(2) == "Connecting", m and m.groups()


#: The two scripts the operator found injected (their names as reported; not a capture of the
#: proxy's whole markup). The check keys on "not from /static/", never on these names.
INJECTED = ('<script data-cfasync="false" src="/cdn-cgi/scripts/5c5dd728/cloudflare-static/'
            'email-decode.min.js"></script><script defer '
            'src="https://static.cloudflareinsights.com/beacon.min.js"></script>')


def test_a_real_browser_says_when_the_page_arrived_changed(page):
    """The served page clean: no notice. The same page rewritten on the way (an after_request
    standing in for the proxy, adding the two scripts before </body>): the notice at the top
    names both and what to do."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    from flask import request

    def rewrite(resp):
        if request.args.get("rewritten") and resp.mimetype == "text/html":
            resp.direct_passthrough = False
            resp.set_data(resp.get_data(as_text=True).replace("</body>", INJECTED + "</body>"))
        return resp
    funcs = A.app.after_request_funcs.setdefault(None, [])
    funcs.insert(0, rewrite)     # runs LAST (after_request runs in reverse): the proxy's place
    notice = "return (document.querySelector('[data-rewritten]') || {}).textContent || ''"
    try:
        with browser.Served(A.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url("/v2/credentials?list=Lab"))
                b.wait_for("return window.htmx && window.Alpine && window.NMAS_V2")
                b.wait_for("return document.readyState === 'complete'")
                assert b.js(notice) == "", "the page as sent says nothing"
                b.go(srv.url("/v2/credentials?list=Lab&rewritten=1"))
                b.wait_for(notice + ".length > 0", 10)
                words = b.js(notice)
                assert "This page arrived changed: 2 scripts the tool did not send" in words
                assert "/cdn-cgi/scripts/5c5dd728/cloudflare-static/email-decode.min.js" in words
                assert "https://static.cloudflareinsights.com/beacon.min.js" in words
                assert b.js("return document.querySelector('main').firstElementChild"
                            ".hasAttribute('data-rewritten')"), "at the top of the page"
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
    finally:
        funcs.remove(rewrite)
