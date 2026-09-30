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


def _external_loads(root=ROOT):
    """(kind, url) for every external script src and stylesheet href in the
    templates."""
    out = []
    for dp, _d, fs in os.walk(os.path.join(root, "templates")):
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



class TestNothingLoadsFromOffTheHost:
    """C123 (closed 2026-09-28): four libraries loaded from public CDNs, two
    UNPINNED, which made the plan's constraint 8 (vendored, so the tool works
    air-gapped) false and put four external origins' script in a page that
    manages network devices. They are vendored from registry-verified
    tarballs; nothing a template loads may come from off the host."""

    def test_no_template_loads_anything_external(self):
        assert _external_loads() == []
        assert csp.CDN_SCRIPTS == () and csp.CDN_STYLES == ()
        assert "http" not in csp.POLICY

    def test_the_scan_sees_one(self, tmp_path):
        (tmp_path / "templates").mkdir()
        (tmp_path / "templates" / "x.html").write_text(
            '<script src="https://cdn.example.invalid/lib.js"></script>'
            '<link rel="stylesheet" href="https://cdn.example.invalid/a.css">')
        assert [k for k, _u in _external_loads(str(tmp_path))] == ["script", "style"]

    def test_every_vendored_file_is_what_the_manifest_says(self):
        import hashlib
        import json

        vendor = os.path.join(ROOT, "static", "js", "vendor")
        manifest = json.load(open(os.path.join(vendor, "MANIFEST.json")))
        assert len(manifest) >= 8, manifest.keys()
        for rel, entry in manifest.items():
            data = open(os.path.join(vendor, rel), "rb").read()
            assert hashlib.sha256(data).hexdigest() == entry["sha256"], rel
            assert entry["integrity"].startswith("sha512-") and entry["version"], rel

    def test_every_vendored_library_is_loaded_by_a_page(self):
        import json

        manifest = json.load(open(os.path.join(ROOT, "static", "js", "vendor", "MANIFEST.json")))
        # base.html is the layout both pages extend, so a library it loads
        # is loaded by both (the socket client moved there for C58). The
        # redesign's layout (v2/base.html) loads htmx, Alpine and uPlot.
        pages = "".join(open(os.path.join(ROOT, "templates", f), encoding="utf-8").read()
                        for f in ("base.html", "index.html", "device.html", "v2/base.html"))
        code = [rel for rel in manifest if rel.endswith((".js", ".css"))]
        assert code and not [rel for rel in code if f"js/vendor/{rel}" not in pages], code


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
