"""P.3 step 3 (register D5): "Restore Golden Config" goes through the guarded
restore preview, and that preview draws the exact program.

Two buttons, the device page's and bulk ops', POSTed to a replay that pushed
the whole golden line by line: no plan, no confirm hash, no rollback. Both now
open `previewBaselineRestore('HEAD', ..., {devices})`, the path the approval
queue already hands off to, and the replay routes are gone.

Routing two more buttons into that preview exposed its own defect: its confirm
dialog showed counts and at most three replace and three residue lines, and
never the lines to be ADDED. `commands` was computed by the route, carried to
the browser, and drawn nowhere, while the confirm hash covered it. So the
renderer is now a pure function, executed here against the route's real
payload.
"""

import json
import os
import re

import pytest

from tests.js_source import shipped_js

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_JS = os.path.join(ROOT, "static", "js", "gen", "partials__golden_repo.3.js")

CAPTURED = """hostname r1
interface GigabitEthernet2
 description old text
 ip address 10.1.1.1 255.255.255.0
interface GigabitEthernet3
 shutdown
logging host 192.0.2.50
"""
TARGET = """hostname r1
interface GigabitEthernet2
 description restored text
 ip address 10.1.1.1 255.255.255.0
interface GigabitEthernet3
 shutdown
ip domain name example.invalid
snmp-server location lab
"""


class _Target:
    def __init__(self, device, deployable=True, reasons=()):
        self.device = device
        self.platform = "cisco_iosxe"
        self.deployable = deployable
        self.blocking_reasons = list(reasons)
        self.captured = CAPTURED
        self.target_config = TARGET


def _real_payload(monkeypatch):
    """What POST /golden/restore/preview returns, with the real merge_diff and
    merge_commands, over two targets: one deployable, one blocked."""
    import flask

    import routes.golden as golden

    monkeypatch.setattr(golden, "_active_list", lambda data=None: "Lab")
    monkeypatch.setattr(golden, "_intent_preview", lambda ln, t: {"action": "none"})
    monkeypatch.setattr("modules.nsot.deploy.prepare_restore",
                        lambda target: {"config": target.target_config})
    monkeypatch.setattr("modules.nsot.restore.build_targets",
                        lambda *a, **k: ([_Target("r1"),
                                          _Target("r2", False, ["no golden at HEAD"])],
                                         [{"hostname": "r9", "reason": "stale"}]))
    app = flask.Flask(__name__)
    app.register_blueprint(golden.bp)
    body = app.test_client().post("/golden/restore/preview",
                                  json={"ref": "HEAD", "devices": ["r1", "r2"]}).get_json()
    assert body["ok"], body
    return body


def _lift(page: str, name: str) -> str:
    start = page.index(f"function {name}(")
    depth, i, seen = 0, page.index("{", start), False
    while i < len(page):
        if page[i] == "{":
            depth += 1
            seen = True
        elif page[i] == "}":
            depth -= 1
            if seen and depth == 0:
                break
        i += 1
    return page[start:i + 1]


def _render(payload, frm=None):
    dukpy = pytest.importorskip("dukpy")
    src = _lift(open(GOLDEN_JS, encoding="utf-8").read(), "restorePreviewText")
    return dukpy.evaljs(src + f"\nrestorePreviewText({json.dumps(payload)}, "
                              f"{json.dumps(frm or {})})")


class TestThePreviewDrawsTheProgram:
    def test_every_line_that_will_be_sent_is_on_screen(self, monkeypatch):
        payload = _real_payload(monkeypatch)
        r1 = next(d for d in payload["devices"] if d["device"] == "r1")
        assert len(r1["commands"]) >= 3, r1["commands"]       # the fixture can fail
        text = _render(payload)
        for line in r1["commands"]:
            assert line in text, (line, text)
        assert f"{len(r1['commands'])} line(s) will be sent, exactly these" in text

    def test_what_it_replaces_and_what_stays_are_drawn(self, monkeypatch):
        payload = _real_payload(monkeypatch)
        r1 = next(d for d in payload["devices"] if d["device"] == "r1")
        assert r1["replace"] and r1["residue"], r1
        text = _render(payload)
        assert "replaces:" in text and "restored text" in text
        assert "stays (not removed): logging host 192.0.2.50" in text

    def test_a_blocked_device_says_nothing_is_sent_and_why(self, monkeypatch):
        text = _render(_real_payload(monkeypatch))
        assert "r2: BLOCKED, nothing will be sent: no golden at HEAD" in text
        assert "r9: stale" in text

    def test_a_dangerous_line_is_marked(self):
        payload = {"summary": "", "scope": "", "devices": [{
            "device": "s4", "deployable": True,
            "commands": ["interface Gi0/1", " shutdown", "exit"],
            "dangerous": [" shutdown"], "replace": [], "residue": []}]}
        text = _render(payload)
        assert "!  shutdown" in text
        assert "dangerous" in text

    def test_the_agents_diff_is_labelled_context(self, monkeypatch):
        text = _render(_real_payload(monkeypatch),
                       {"advisoryDiff": "-a\n+b", "advisoryNote": "seen at 03:00"})
        assert text.index("NOT what will be sent") < text.index("line(s) will be sent")


class TestTheWiring:
    """The render is pure; these pin that the flow actually uses it."""

    def test_the_restore_flow_confirms_on_the_drawn_program(self):
        src = open(GOLDEN_JS, encoding="utf-8").read()
        flow = _lift(src, "previewBaselineRestore")
        assert "_confirmProgram(" in flow and "restorePreviewText(d, from)" in flow
        # The only confirm() left is the un-onboard question, which has no program.
        assert flow.count("confirm(") == 1, flow.count("confirm(")

    def test_the_modal_puts_config_in_as_text_never_html(self):
        modal = _lift(open(GOLDEN_JS, encoding="utf-8").read(), "_confirmProgram")
        assert "querySelector('pre').textContent = text" in modal
        assert "innerHTML = text" not in modal

    def test_bulk_ops_opens_the_guarded_preview_at_head(self):
        src = open(os.path.join(ROOT, "static", "js", "gen", "index.1.js"),
                   encoding="utf-8").read()
        m = re.search(r"window\.bulkRestoreGoldenConfig = function\(\) \{(.*?)\n  \};", src, re.S)
        assert m
        assert "previewBaselineRestore('HEAD', null, {devices: hosts})" in m.group(1)
        assert "fetch(" not in m.group(1)

    def test_the_device_page_links_to_the_preview_at_head(self):
        import app as A
        with A.app.test_request_context("/"):
            from flask import url_for
            href = url_for("index", restore_head="r1")
        assert href == "/?restore_head=r1"
        page = open(os.path.join(ROOT, "templates", "device.html"), encoding="utf-8").read()
        assert "url_for('index', restore_head=device['hostname'])" in page

    def test_the_index_page_opens_it_from_the_url(self):
        index = open(os.path.join(ROOT, "templates", "index.html"), encoding="utf-8").read()
        assert "{% include 'partials/golden_repo.html' %}" in index
        page = shipped_js("partials", "golden_repo.html")
        assert "document.addEventListener('DOMContentLoaded', _restoreHeadFromUrl)" in page
        fn = _lift(page, "_restoreHeadFromUrl")
        assert "history.replaceState" in fn.split("previewBaselineRestore")[0], (
            "the parameter must be removed BEFORE the preview opens, or a "
            "reload re-opens a preview nobody asked for")
        assert "previewBaselineRestore('HEAD', null, {devices})" in fn
