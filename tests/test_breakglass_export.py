"""The break-glass export from the browser (7.3, the operator, 2026-09-29),
through the real route, module and record format.

The day's first manual export was LOST: a copy command meant for the laptop
ran on the host and deleted the file before it was copied. So the file never
touches the host's disk; the passphrase is checked before anything is built;
the sealed bytes are OPENED and checked before they are sent; nothing is sent
unrecorded; the passphrase appears nowhere the tool writes or answers.
"""

import base64
import hashlib
import json
import os

import pytest

import modules.breakglass as bg
from modules import breakglass_export as BE
from tests.conftest import TEST_PERSON
from tests.payload_render import lift, render_preview, render_result, shipped

LIST = "Lab"
PASS = "correct horse battery staple"
DEVICES = [{"hostname": "r1", "ip": "192.0.2.11", "username": "admin",
            "password": "R1-Secret-Value-771", "secret": "", "platform": "cisco_iosxe",
            "list_name": LIST, "container": ""},
           {"hostname": "s1", "ip": "192.0.2.21", "username": "admin",
            "password": "S1-Secret-Value-229", "secret": "S1-Enable-Value-3",
            "platform": "cisco_ios", "list_name": LIST, "container": ""}]
VALUES = [d["password"] for d in DEVICES] + ["S1-Enable-Value-3"]


@pytest.fixture
def lab(tmp_path, monkeypatch):
    import app as A
    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    (tmp_path / "key.key").write_bytes(key)
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("modules.config.KEY_FILE", str(tmp_path / "key.key"))
    monkeypatch.setattr(BE, "list_devices", lambda ln: [dict(d) for d in DEVICES])
    token = Fernet(key).encrypt(b"a stored value").decode()
    monkeypatch.setattr(BE, "live_stores", lambda data_dir="": {"credential_profiles.json": [token]})
    return {"client": A.app.test_client(), "dir": tmp_path, "key": key}


def _preview(lab):
    r = lab["client"].post("/breakglass/preview", json={"list_name": LIST})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()["preview"]


def _export(lab, preview=None, passphrase=PASS, confirm=PASS, hash_=None):
    preview = preview or _preview(lab)
    data = preview["what"]["targets"][0]["select_data"]
    r = lab["client"].post("/breakglass/export", json={
        "list_name": data["list"], "hash": hash_ or data["hash"],
        "passphrase": passphrase, "confirm": confirm})
    return r


def _audit(lab):
    path = lab["dir"] / "reveal_audit.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


def _log(lab):
    path = lab["dir"] / bg.EXPORT_LOG
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


class TestThePreview:
    def test_it_names_the_devices_and_reveals_no_value(self, lab):
        r = lab["client"].post("/breakglass/preview", json={"list_name": LIST})
        text = r.get_data(as_text=True)
        assert not [v for v in VALUES if v in text], "a preview reveals no value"
        p = r.get_json()["preview"]
        lines = p["targets"][0]["program"]["lines"]
        assert lines[0].startswith("r1") and "+ enable secret" in lines[1]
        ops = {o["name"]: o["value"] for o in p["targets"][0]["operands"]}
        assert ops["key fingerprint"] == bg.key_fingerprint(lab["key"])
        assert ops["key opens"] == "1 of 1 stored value(s)"
        said = " ".join(i["text"] for i in p["what_not"]["items"])
        assert "never written to this host's disk" in said and "cannot see where" in said
        assert p["confirm"]["button"] == "Build, verify and download (2 device(s))"
        assert _audit(lab) == [] and _log(lab) == [], "a preview writes nothing"
        assert "What the record will hold" in render_preview(p)


class TestThePassphraseIsCheckedBeforeAnythingIsBuilt:
    @pytest.mark.parametrize("passphrase,confirm,said", [
        (PASS, PASS + "x", "do not match"), ("short-one", "short-one", "shorter than 12")])
    def test_refused_with_nothing_built(self, lab, monkeypatch, passphrase, confirm, said):
        monkeypatch.setattr(BE, "seal", lambda *a, **k: pytest.fail("built after a refusal"))
        body = _export(lab, passphrase=passphrase, confirm=confirm).get_json()
        assert "file" not in body
        res = body["result"]
        assert res["level"] == "failed" and said in res["happened"]["summary"]
        assert _audit(lab) == [] and _log(lab) == []

    def test_credentials_that_moved_since_the_preview_refuse(self, lab):
        body = _export(lab, hash_="0000000000000000").get_json()
        assert "file" not in body and "changed since the preview" in \
            body["result"]["happened"]["summary"]


class TestTheExport:
    def test_the_file_opens_verifies_and_is_recorded(self, lab):
        r = _export(lab)
        assert r.headers["Cache-Control"] == "no-store"
        body = r.get_json()
        blob = base64.b64decode(body["file"])
        assert hashlib.sha256(blob).hexdigest() == body["sha256"]
        opened = bg.unseal(blob, PASS)
        assert bg.digests_of(opened["devices"]) == bg.digests_of(DEVICES)
        assert bg.escrowed_key(opened) == lab["key"]
        assert body["filename"].startswith("nmas-breakglass-Lab-") and body["filename"].endswith(".bg")
        res = body["result"]
        assert res["level"] == "success", res
        assert "verify" in res["next"]["text"] and "--against" in res["next"]["text"]
        (audit,) = _audit(lab)
        assert (audit["actor"], audit["what"], audit["target"]) == (TEST_PERSON,
                                                                    "breakglass_record", LIST)
        assert audit["sha256"] == body["sha256"] and audit["device_count"] == 2
        (row,) = _log(lab)
        assert row["via"] == "browser" and row["sha256"] == body["sha256"]
        assert row["path"].startswith(f"downloaded by {TEST_PERSON} at ")
        assert "opened with your passphrase" in render_result(res)

    def test_the_file_never_touches_the_hosts_disk(self, lab, monkeypatch):
        monkeypatch.setattr(bg, "write_record", lambda *a, **k: pytest.fail("written to disk"))
        _export(lab)
        assert not [f for root, _d, files in os.walk(lab["dir"]) for f in files
                    if f.endswith(".bg")]

    def test_a_record_that_does_not_verify_is_never_sent(self, lab, monkeypatch):
        real_seal = bg.seal

        def tampered(payload, passphrase):
            payload = dict(payload, devices=[dict(d) for d in payload["devices"]])
            payload["devices"][1]["password"] = ""       # a device lost on the way
            return real_seal(payload, passphrase)

        monkeypatch.setattr(BE, "seal", tampered)
        body = _export(lab).get_json()
        assert "file" not in body
        assert "did not verify" in body["result"]["happened"]["summary"]
        assert _audit(lab) == [] and _log(lab) == [], "nothing recorded for nothing sent"

    def test_an_escrowed_key_that_opens_less_is_never_sent(self, lab, monkeypatch):
        from cryptography.fernet import Fernet
        other = Fernet.generate_key()
        monkeypatch.setattr(BE, "build_payload", lambda devices, **k: bg.build_payload(
            devices, list_name=k["list_name"], fernet_key=other))
        body = _export(lab).get_json()
        assert "file" not in body and "escrowed key" in body["result"]["happened"]["summary"]

    def test_nothing_is_sent_unrecorded(self, lab, monkeypatch):
        from modules import reveal_audit
        monkeypatch.setattr(reveal_audit, "record", lambda **k: {"recorded": False})
        body = _export(lab).get_json()
        assert "file" not in body and "never unrecorded" in body["result"]["happened"]["summary"]
        assert _log(lab) == []


class TestThePassphraseLeavesNoTrace:
    def test_nowhere_on_success_or_on_a_failure_that_quotes_it(self, lab, monkeypatch, caplog):
        caplog.set_level("DEBUG")
        texts = [_export(lab).get_data(as_text=True)]
        monkeypatch.setattr(BE, "seal", lambda payload, p: (_ for _ in ()).throw(
            bg.BreakglassError(f"a failure quoting {p}")))
        texts.append(_export(lab).get_data(as_text=True))
        assert "<passphrase>" in texts[1], "the failure's text is scrubbed, not dropped"
        texts += [caplog.text, json.dumps(_audit(lab)), json.dumps(_log(lab))]
        assert not [t for t in texts if PASS in t]


@pytest.mark.real_identity
def test_an_unverified_caller_is_refused_before_anything_is_built(lab, monkeypatch):
    monkeypatch.setattr(BE, "export_in_memory", lambda *a, **k: pytest.fail("reached"))
    r = lab["client"].post("/breakglass/export", json={"list_name": LIST, "hash": "x",
                                                       "passphrase": PASS, "confirm": PASS})
    assert r.status_code == 403


class TestJobHealthSaysWhatTheHostKnows:
    def test_a_browser_export_reads_downloaded_and_asks_for_the_copy(self):
        from modules import job_health
        row = {"at": 1_800_000_000, "list": LIST, "via": "browser", "actor": TEST_PERSON,
               "devices": bg.digests_of(DEVICES)}
        (r,) = job_health.breakglass_rows(exports={"state": "ok", "by_list": {LIST: row}},
                                          current={LIST: bg.digests_of(DEVICES)})
        assert r["state"] == "ok" and f"downloaded by {TEST_PERSON} at" in r["detail"]
        assert "verify the copy you keep" in r["detail"]

    def test_a_stale_row_opens_the_export(self):
        from modules import job_health
        row = {"at": 1_800_000_000, "list": LIST, "via": "browser", "actor": TEST_PERSON,
               "devices": bg.digests_of(DEVICES)}
        moved = dict(bg.digests_of(DEVICES), r1="0" * 16)
        (r,) = job_health.breakglass_rows(exports={"state": "ok", "by_list": {LIST: row}},
                                          current={LIST: moved})
        assert r["state"] == "breakglass_stale"
        assert (r["action"]["open"], r["action"]["list"]) == ("breakglass_export", LIST)


class TestTheThreeEntryPointsAndOneClient:
    def _run(self, js):
        import dukpy
        return dukpy.evaljs(js)

    def test_the_button_refuses_a_short_or_mismatched_passphrase(self, lab):
        p = _preview(lab)
        js = (lift(shipped("nmas_preview_confirm.js"), "previewConfirmButton") + "\n"
              + lift(shipped("nmas_breakglass.js"), "breakglassButton") + "\nvar MIN = 12;\n")
        call = lambda a, b: self._run(js + f"breakglassButton({json.dumps(p)}, "
                                           f"{json.dumps(a)}, {json.dumps(b)})")
        assert call("short", "short")["disabled"]
        assert call(PASS, PASS + "!")["text"] == "The two passphrases differ"
        assert call(PASS, PASS) == {"disabled": False,
                                    "text": "Build, verify and download (2 device(s))"}

    def test_the_rotate_result_offers_it_in_its_next_step(self):
        js = (lift(shipped("nmas_preview_confirm.js"), "esc") + "\n"
              + "var NEXT_OPENS = {breakglass_export: 'Export the break-glass record…'};\n"
              + "var NEXT_CLASS = {breakglass_export: 'btn-outline-danger'};\n"
              + lift(shipped("nmas_preview_confirm.js"), "nextHtml"))
        html = self._run(js + "\nnextHtml({text: 'Export again', open: 'breakglass_export', "
                              "args: {list: 'Lab'}})")
        assert 'data-nmas-open="breakglass_export"' in html and 'data-nmas-list="Lab"' in html
        unknown = self._run(js + "\nnextHtml({text: 't', open: 'reload_everything'})")
        assert "data-nmas-open" not in unknown, "only a declared operation is offered"

    def test_needs_attention_offers_it_on_the_row(self):
        js = (lift(shipped("nmas_attention.js"), "esc") + "\n"
              + lift(shipped("nmas_attention.js"), "actionHtml"))
        html = self._run(js + "\nactionHtml({label: 'Export again', open: 'breakglass_export', "
                              "list: 'Lab', command: 'nmas-breakglass export'})")
        assert 'data-nmas-open="breakglass_export"' in html and "or on the host" in html

    def test_the_settings_page_offers_it_and_one_client_opens_all_three(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        partial = open(os.path.join(root, "templates", "partials",
                                    "settings_integrations.html")).read()
        assert 'data-nmas-open="breakglass_export"' in partial
        assert "js/nmas_breakglass.js" in open(os.path.join(root, "templates", "base.html")).read()
        client = shipped("nmas_breakglass.js")
        assert "closest('[data-nmas-open=\"breakglass_export\"]')" in client
