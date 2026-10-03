"""Credentials > The break-glass record (board 7, signed off 2026-10-03): the record's state,
the export (A) through the ONE export route, and the browser's check that the download arrived
intact (B), on test_breakglass_export's lab (a real key, real device credentials, the real
route, module and record format).

- The page: under the strict policy, the sidebar's Credentials, the record's state in each of
  its states from the stores that decide it (job health's stored judgement, the export log,
  the browser's verdicts), and a name that is no list said.
- A (open=export): drawn from the real preview, revealing no value; one confirm, busy on
  itself; the passphrase fields in it.
- B: the browser's sha256 against the server's recorded, either way; a download not intact,
  or not checked, in danger and not counted as current (breakglass.currency, job health's
  row); a sha256 that is not the newest export's refused, naming both.
- Every way in opens it here: the rotation's result, Needs attention's row, today's Settings.
- The pure client functions in duktape; the whole export in a real browser.
"""

import hashlib
import json
import re
import time

import pytest

import modules.breakglass as bg
from tests.test_breakglass_export import DEVICES, LIST, PASS, VALUES, _export, lab  # noqa: F401


@pytest.fixture
def page(lab, monkeypatch):  # noqa: F811
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == LIST)
    return lab


def _get(lab, path):
    r = lab["client"].get(path)
    return r, r.get_data(as_text=True)


def _cached(jobs, at):
    return {"state": "ok", "doc": {"last_good": {"value_at": at, "value": {"health": {
        "jobs": jobs}}}}}


class TestThePage:
    def test_it_draws_under_the_strict_policy_from_the_sidebar(self, page):
        from modules import csp
        r, html = _get(page, f"/v2/credentials?list={LIST}")
        assert r.status_code == 200 and r.headers["Content-Security-Policy"] == csp.STRICT_POLICY
        assert re.search(r'class="nav-item active" href="/v2/credentials"', html)
        assert 'data-manual="credentials"' in html
        assert "Lab's break-glass record" in html and "none exported" in html
        assert 'id="bg-export"' not in html, "the export opens only when asked"

    def test_a_name_that_is_no_list_is_refused_naming_it(self, page):
        r, html = _get(page, "/v2/credentials?list=Nope")
        assert r.status_code == 404 and "no device list named" in html and "Nope" in html
        assert 'id="bg-record"' not in html

    def test_each_state_from_the_stores_that_decide_it(self, page, monkeypatch):
        from modules import breakglass_page as BP
        now = time.time()
        export = {"at": now - 3600, "list": LIST, "actor": "operator@example.com",
                  "via": "browser", "sha256": "ab" * 32, "key_fingerprint": "4be1·09c2",
                  "devices": {"r1": "x", "s1": "y"}}
        exports = {"state": "ok", "by_list": {LIST: export}}
        none = {"state": "ok", "by_sha": {}}
        later = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 60))
        stale = _cached([{"unit": f"breakglass:{LIST}/r1", "device": "r1",
                          "state": "breakglass_stale"}], later)
        ok = _cached([{"unit": f"breakglass:{LIST}", "state": "ok"}], later)
        assert BP.record(LIST, stale, exports, none)["state"] == "stale"
        assert BP.record(LIST, stale, exports, none)["stale"] == ["r1"]
        assert BP.record(LIST, ok, exports, none)["state"] == "current"
        bad = {"state": "ok", "by_sha": {"ab" * 32: {"ok": False, "sha256": "ab" * 32}}}
        assert BP.record(LIST, ok, exports, bad)["state"] == "not_intact"
        assert BP.record(LIST, ok, {"state": "absent", "by_list": {}}, none)["state"] == "never"
        # An export AFTER job health's last read held the credentials in use when made.
        earlier = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 7200))
        got = BP.record(LIST, _cached([], earlier), exports, none)
        assert got["state"] == "current" and "job health judges it again" in got["words"]
        assert BP.record(LIST, {"state": "absent", "doc": None}, exports, none)["state"] == "unjudged"
        unreadable = {"state": "unreadable", "by_list": {}, "error": "line 2 is not JSON"}
        assert BP.record(LIST, ok, unreadable, none)["state"] == "unreadable"


class TestTheExportCard:
    def test_open_export_draws_the_real_preview_revealing_no_value(self, page):
        r, html = _get(page, f"/v2/credentials?list={LIST}&open=export")
        assert r.status_code == 200
        card = html[html.index('id="bg-export"'):]
        assert not [v for v in VALUES if v in html], "the card reveals no value"
        assert "r1" in card and "s1" in card and "key fingerprint" in card.lower()
        assert 'x-data="breakglassExport"' in card and 'data-bg-pass' in card and 'data-bg-again' in card
        assert f'data-export-url="/breakglass/export"' in card
        assert re.search(r'data-hash="[0-9a-f]{16}"', card)
        assert 'class="btn btn-danger op-confirm" data-op="breakglass-export"' in card

    def test_the_card_alone_for_the_records_button(self, page):
        r, html = _get(page, f"/v2/credentials/export?list={LIST}")
        assert r.status_code == 200 and html.lstrip().startswith('<section class="op-card op-danger" id="bg-export"')
        r, html = _get(page, "/v2/credentials/export?list=Nope")
        assert r.status_code == 404 and "Nope" in html


class TestTheBrowsersWordOnTheDownload:
    def _exported(self, lab):
        r = _export(lab)
        d = r.get_json()
        assert d["file"] and d["sha256"]
        return d

    def test_intact_is_recorded_and_drawn(self, page):
        import base64
        d = self._exported(page)
        browser = hashlib.sha256(base64.b64decode(d["file"])).hexdigest()
        r = page["client"].post("/v2/credentials/intact", data={
            "list": LIST, "sha256": d["sha256"], "browser_sha256": browser,
            "filename": d["filename"]})
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "Downloaded intact" in html and "op-ok" in html
        rows = [json.loads(l) for l in (page["dir"] / bg.INTACT_LOG).read_text().splitlines()]
        assert rows[-1]["ok"] is True and rows[-1]["sha256"] == d["sha256"]
        assert not [v for v in VALUES + [PASS] if v in html + json.dumps(rows)]

    @pytest.mark.parametrize("browser, words", [("cd" * 32, "Not intact"), ("", "Not checked")])
    def test_not_intact_or_not_checked_is_danger_and_not_current(self, page, browser, words):
        d = self._exported(page)
        html = page["client"].post("/v2/credentials/intact", data={
            "list": LIST, "sha256": d["sha256"], "browser_sha256": browser}).get_data(as_text=True)
        assert words in html and "op-danger" in html and "not counted as current" in html
        verdicts = bg.intact_verdicts(str(page["dir"]))
        last = bg.last_exports(str(page["dir"]))["by_list"][LIST]
        judged = bg.currency(last, last["devices"], verdicts["by_sha"][d["sha256"]])
        assert judged["state"] == "not_intact"

    def test_a_download_that_is_not_the_newest_export_is_refused_naming_both(self, page):
        d = self._exported(page)
        r = page["client"].post("/v2/credentials/intact", data={
            "list": LIST, "sha256": "ee" * 32, "browser_sha256": "ee" * 32})
        html = r.get_data(as_text=True)
        assert r.status_code == 409 and d["sha256"][:12] in html and ("ee" * 6) in html
        assert not (page["dir"] / bg.INTACT_LOG).exists()

    def test_history_marks_the_export_with_the_browsers_word(self, page, monkeypatch):
        from modules import history_sources as HS
        d = self._exported(page)
        page["client"].post("/v2/credentials/intact", data={
            "list": LIST, "sha256": d["sha256"], "browser_sha256": "cd" * 32})
        ref = type("Ref", (), {"name": LIST})()
        got = HS.breakglass({"ref": ref, "device": "", "limit": 30, "since": None,
                             "members": None})
        assert got["events"][0]["marks"] == ["not intact"]
        assert got["events"][0]["outcome"] == "not_intact"

    def test_job_health_says_a_download_not_intact(self, page):
        from modules import job_health
        d = self._exported(page)
        page["client"].post("/v2/credentials/intact", data={
            "list": LIST, "sha256": d["sha256"], "browser_sha256": "cd" * 32})
        last = bg.last_exports(str(page["dir"]))["by_list"][LIST]
        rows = job_health.breakglass_rows(current={LIST: last["devices"]})
        assert [r["state"] for r in rows] == ["breakglass_not_intact"]
        assert rows[0]["action"]["open"] == "breakglass_export"


class TestACredentialTheKeyCannotOpen:
    """C384: one device's stored credential sealed with another key crashed the preview (HTTP
    500, InvalidToken). It is named, and nothing is built."""

    def test_it_is_named_and_the_export_refused(self, tmp_path, monkeypatch):
        import app as A
        from cryptography.fernet import Fernet
        from modules import breakglass_export as BE
        key = Fernet.generate_key()
        (tmp_path / "key.key").write_bytes(key)
        (tmp_path / "lab").mkdir()
        monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
        monkeypatch.setattr("modules.config.KEY_FILE", str(tmp_path / "key.key"))
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / "lab"))
        monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == LIST)
        monkeypatch.setattr(BE, "live_stores", lambda data_dir="": {})
        monkeypatch.setattr("modules.device.fernet", Fernet(key))
        good = Fernet(key).encrypt(b"R1-Secret-Value-771").decode()
        other = Fernet(Fernet.generate_key()).encrypt(b"lost").decode()
        monkeypatch.setattr("modules.device.load_saved_devices", lambda path: [
            {"hostname": "r1", "ip": "192.0.2.11", "username": "admin", "password": good,
             "secret": ""},
            {"hostname": "r9", "ip": "192.0.2.19", "username": "admin", "password": other,
             "secret": ""}])
        with pytest.raises(bg.BreakglassError, match=r"r9 \(InvalidToken\)"):
            BE.list_devices(LIST)
        plan = BE.export_plan(LIST)
        assert plan["ok"] is False and "r9 (InvalidToken)" in plan["refusals"][0]
        r = A.app.test_client().get(f"/v2/credentials?list={LIST}&open=export")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "r9 (InvalidToken)" in html and "Not available" in html


class TestEveryWayInOpensItHere:
    def test_the_rotations_result_needs_attention_and_settings(self):
        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        read = lambda p: open(os.path.join(root, p), encoding="utf-8").read()  # noqa: E731
        want = "url_for('v2.credentials', list="
        assert want + "c.list, open='export')" in read("templates/v2/_rotate.html")
        assert want + "r.action.list, open='export')" in read("templates/v2/_attention.html")
        settings = read("templates/partials/settings_integrations.html")
        assert "url_for('v2.credentials')" in settings
        assert 'data-nmas-open="breakglass_export"' not in settings, "nothing exports there now"


class TestTheClient:
    def _call(self, expr):
        import dukpy
        from tests.payload_render import shipped
        return dukpy.evaljs("var window = {};\n" + shipped("nmas_credentials.js")
                            + "\nwindow.NMAS_CREDENTIALS." + expr)

    def test_the_button_says_what_stops_it(self):
        assert self._call("exportButton('short', 'short', 12, 'Go')") == {
            "disabled": True, "text": "The passphrase needs 12 characters or more"}
        assert self._call("exportButton('long enough pass', 'long enough pas', 12, 'Go')") == {
            "disabled": True, "text": "The two passphrases differ"}
        assert self._call("exportButton('long enough pass', 'long enough pass', 12, 'Go')") == {
            "disabled": False, "text": "Go"}

    def test_a_refusal_is_said_in_the_servers_words(self):
        got = self._call("exportOutcome(200, {ok: true, result: {happened: {summary: "
                         "'Nothing was sent: the two passphrases do not match.'}}})")
        assert got["ok"] is False and got["error"] == ("Nothing was sent: the two passphrases do "
                                                       "not match.")
        assert self._call("exportOutcome(500, null)")["error"] == "Nothing was sent: refused (HTTP 500)"
        ok = self._call("exportOutcome(200, {ok: true, file: 'AA==', sha256: 'ab', filename: 'f.bg'})")
        assert ok["ok"] is True and ok["filename"] == "f.bg"

    def test_hex(self):
        assert self._call("hexOf([0, 15, 16, 255])") == "000f10ff"


def test_a_real_browser_exports_and_checks_the_download(page, monkeypatch):
    """The whole of A and B: the passphrase twice, the confirm busy on itself, the server's
    export, the browser's sha256 of the bytes, the result card in place reading Downloaded
    intact, and its row recorded."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url(f"/v2/credentials?list={LIST}&open=export"))
            b.wait_for("return window.Alpine && document.querySelector('#bg-export [data-bg-pass]')")
            assert b.js("return document.querySelector('#bg-export .op-confirm').disabled")
            for sel in ("[data-bg-pass]", "[data-bg-again]"):
                b.js("var f=document.querySelector('#bg-export " + sel + "'); f.value=arguments[0];"
                     "f.dispatchEvent(new Event('input', {bubbles: true}));", PASS)
            b.wait_for("return !document.querySelector('#bg-export .op-confirm').disabled")
            b.click("#bg-export .op-confirm")
            b.wait_for("return /Downloaded intact/.test(document.querySelector('#bg-export')"
                       ".textContent)", 20)
            # The record's card above shows the new state too (out of band, with the answer).
            # (This lab has no job-health reading, so "not judged yet", saying the export held
            # the credentials in use when made; never "none exported" above a finished export.)
            b.wait_for("return document.querySelector('#bg-record .badge').textContent.trim() "
                       "=== 'not judged yet'", 5)
            assert "the last export held the credentials in use when made" in b.js(
                "return document.querySelector('#bg-record').textContent")
            assert "T" in b.js("return document.querySelector('#bg-export time').getAttribute("
                               "'datetime')"), "a time, never an epoch number"
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    rows = [json.loads(l) for l in (page["dir"] / bg.INTACT_LOG).read_text().splitlines()]
    assert rows[-1]["ok"] is True and len(rows[-1]["browser_sha256"]) == 64


def test_a_real_browser_says_bytes_altered_on_the_way_are_not_intact(page, monkeypatch):
    """The browser HASHES WHAT IT RECEIVED: a byte altered between the server's record and the
    browser (here, after the export logged its sha256) reads Not intact, in danger, and its row
    says so. A browser that echoed the server's sha256 would read intact here."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    from modules import breakglass_export as BE
    real = BE.export_in_memory

    def altered(*a, **k):
        out = real(*a, **k)
        if out.get("blob"):
            out["blob"] = out["blob"][:-1] + bytes([out["blob"][-1] ^ 1])
        return out
    monkeypatch.setattr(BE, "export_in_memory", altered)
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b.go(srv.url(f"/v2/credentials?list={LIST}&open=export"))
            b.wait_for("return window.Alpine && document.querySelector('#bg-export [data-bg-pass]')")
            for sel in ("[data-bg-pass]", "[data-bg-again]"):
                b.js("var f=document.querySelector('#bg-export " + sel + "'); f.value=arguments[0];"
                     "f.dispatchEvent(new Event('input', {bubbles: true}));", PASS)
            b.wait_for("return !document.querySelector('#bg-export .op-confirm').disabled")
            b.click("#bg-export .op-confirm")
            b.wait_for("return /Not intact/.test(document.querySelector('#bg-export').textContent)", 20)
            assert b.js("return document.querySelector('#bg-export').className").endswith("op-danger")
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()
    rows = [json.loads(l) for l in (page["dir"] / bg.INTACT_LOG).read_text().splitlines()]
    assert rows[-1]["ok"] is False and rows[-1]["browser_sha256"] != rows[-1]["sha256"]
