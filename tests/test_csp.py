"""C88 (c): a Content-Security-Policy on every HTML page, the belt to
escaping's braces (the operator, 2026-09-27). It bounds where injected script
can send data and what it can load; it cannot stop inline script running
while the pages carry ~300 inline handlers, and `modules/csp.py` says so.

The two ways a CSP goes wrong here are breaking a page (a script the page
loads that the policy refuses) and quietly admitting too much (a whole CDN
host rather than the one file). Both are checked, both ways.
"""

import os
import re

from modules import csp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _external_loads():
    """(kind, url) for every external script src and stylesheet href in the
    templates."""
    out = []
    for dp, _d, fs in os.walk(os.path.join(ROOT, "templates")):
        for f in fs:
            if not f.endswith(".html"):
                continue
            text = open(os.path.join(dp, f), encoding="utf-8").read()
            out += [("script", u) for u in re.findall(
                r"<script[^>]*\bsrc=[\"'](https?://[^\"']+)", text)]
            out += [("style", u) for u in re.findall(
                r"<link[^>]*\bhref=[\"'](https?://[^\"']+)", text)]
    return out


class TestThePolicy:
    def test_it_bounds_where_data_can_go_and_what_can_load(self):
        for directive in ("connect-src 'self'", "object-src 'none'", "base-uri 'self'",
                          "form-action 'self'", "frame-ancestors 'none'", "default-src 'self'"):
            assert directive in csp.POLICY, directive

    def test_it_says_what_it_cannot_do(self):
        """'unsafe-inline' is there, and the module states why, so nobody
        reads the header as having closed C88."""
        assert "'unsafe-inline'" in csp.POLICY
        doc = csp.__doc__
        assert "cannot" in doc.lower() and "RUNNING" in doc and "not the braces" in doc

    def test_no_cdn_is_admitted_by_host_alone(self):
        for src in csp.CDN_SCRIPTS + csp.CDN_STYLES:
            assert src.count("/") >= 4 and src.endswith("/"), f"a path prefix, not a host: {src}"


class TestItFitsThePages:
    def test_every_external_load_is_admitted_and_every_admission_is_used(self):
        loads = _external_loads()
        assert len(loads) >= 4, loads            # the scan can see them (C123's four)
        refused = [(k, u) for k, u in loads
                   if not any(u.startswith(p) for p in
                              (csp.CDN_SCRIPTS if k == "script" else csp.CDN_STYLES))]
        assert refused == [], f"the policy would block these on the live page: {refused}"
        unused = [p for p in csp.CDN_SCRIPTS + csp.CDN_STYLES
                  if not any(u.startswith(p) for _k, u in loads)]
        assert unused == [], f"admitted and loaded by nothing (vendored? remove it): {unused}"


class TestTheHeader:
    def test_the_page_carries_it_and_json_does_not(self):
        import app as A

        c = A.app.test_client()
        page = c.get("/")
        assert page.headers.get("Content-Security-Policy") == csp.POLICY
        js = c.get("/identity/status")
        assert "Content-Security-Policy" not in js.headers

    def test_a_response_with_its_own_policy_keeps_it(self):
        """The topology SVG sets a stricter one (`default-src 'none'`). On a
        throwaway app: the real one cannot take a route after its first
        request."""
        from flask import Flask, Response

        app = Flask("csp_probe")
        csp.install(app)

        @app.route("/own")
        def own():
            r = Response("<p>x</p>", mimetype="text/html")
            r.headers["Content-Security-Policy"] = "default-src 'none'"
            return r

        @app.route("/plain")
        def plain():
            return Response("<p>x</p>", mimetype="text/html")
        c = app.test_client()
        assert c.get("/own").headers["Content-Security-Policy"] == "default-src 'none'"
        assert c.get("/plain").headers["Content-Security-Policy"] == csp.POLICY
