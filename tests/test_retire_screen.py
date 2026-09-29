"""7.3's retire screen, over the real retire module against a real repository,
CSV, manifest and credential store (test_retire's world).

The operator (2026-09-28): the screen uses the EXPORT LOG for the break-glass
check, and says so, because it cannot open a record on the operator's
laptop: "the screen trusts the export log, the CLI trusts the record".
"""

import ast
import hashlib
import json
import os

import pytest

from modules import breakglass as bg
from modules.nsot import retire as RT
from tests.payload_render import lift, render_preview, render_result, shipped
from tests.test_retire import PW, _bg, world  # noqa: F401  (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REASON = "ISP PE, outside our administrative boundary"


@pytest.fixture
def screen(world, tmp_path, monkeypatch):  # noqa: F811
    import app as A

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr("modules.config.DATA_DIR", str(data))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
    return {**world, "client": A.app.test_client(), "data": str(data)}


def _export(screen, pw=PW, hosts=("r4", "r5")):
    """An export logged the way `nmas-breakglass export` logs one."""
    pws = {"r4": "other-pw-1234567", "r5": pw}
    bg.record_export(screen["data"], list_name="Lab", path="/dev/shm/rcn-breakglass.bg",
                     key_fingerprint="abcd1234", actor="op",
                     devices=[{"hostname": h, "username": "admin", "password": pws[h]}
                              for h in hosts])


def _preview(screen, reason=REASON):
    r = screen["client"].post("/retire/preview", json={"device": "r5", "reason": reason})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["preview"]


def _gate(p, name):
    (g,) = [g for g in p["targets"][0]["gates"] if g["name"] == name]
    return g


def _state(screen):
    """Everything the preview must not write."""
    h = hashlib.sha256()
    for base, _dirs, files in sorted(os.walk(os.path.dirname(screen["repo"]))):
        if "/.git" in base:
            continue
        for f in sorted(files):
            with open(os.path.join(base, f), "rb") as fh:
                h.update(f.encode() + fh.read())
    return h.hexdigest(), json.dumps(screen["settings"], sort_keys=True, default=str)


class TestThePreview:
    def test_every_step_and_everything_it_will_not_do(self, screen):
        _export(screen)
        p = _preview(screen)
        lines = p["targets"][0]["program"]["lines"]
        assert any(l.startswith("declare ") for l in lines)
        assert any(l.startswith("one commit: remove host_vars/r5.yml, golden/r5.cfg") for l in lines)
        assert lines[-1].startswith("delete the CSV row"), "the row goes last"
        said = " ".join(i["text"] for i in p["what_not"]["items"])
        for claim in ("NetBox device 9 is KEPT", "Oxidized keeps polling",
                      "freezes at its last sync", "running configuration is not changed",
                      "backups are kept", "is not withdrawn", "Advisory: its golden shows the "
                      "NMAS-HEARTBEAT applet"):
            assert claim in said, claim
        html = render_preview(p)
        assert "Oxidized keeps polling" in html and "is not withdrawn" in html

    def test_it_says_which_basis_it_trusts_and_what_that_cannot_show(self, screen):
        _export(screen)
        p = _preview(screen)
        (basis,) = [i for i in p["what_not"]["items"] if i["kind"] == "basis"]
        assert "trusts the EXPORT LOG" in basis["text"]
        assert "cannot show the file still exists" in basis["text"]
        assert "`nmas-retire --breakglass <file>` opens the record itself" in basis["text"]
        op = {o["name"]: o["value"] for o in p["targets"][0]["operands"]}
        assert op["break-glass basis"].startswith("the export log (not the record)")
        assert "key abcd1234" in op["break-glass basis"]
        assert "trusts the export log" in _gate(p, RT_GATE)["detail"]

    def test_a_current_export_makes_it_confirmable_and_says_what_survives(self, screen):
        _export(screen)
        p = _preview(screen)
        t = p["what"]["targets"][0]
        assert t["selectable"] and t["state"] == "retirable"
        assert _gate(p, RT_GATE)["state"] == "pass"
        effect = p["confirm"]["effect"]
        assert "stay in history" in effect and "survives ONLY in the break-glass export" in effect
        assert "not an undo" in effect
        assert p["confirm"]["button"] == "Retire r5"

    def test_no_export_is_a_failed_gate_naming_the_command(self, screen):
        p = _preview(screen)
        g = _gate(p, RT_GATE)
        assert g["state"] == "fail" and "no break-glass export of Lab is logged" in g["detail"]
        assert "nmas-breakglass export --list Lab" in g["detail"]
        t = p["what"]["targets"][0]
        assert not t["selectable"] and "no break-glass export" in t["why_not"]
        assert "effect" not in p["confirm"], "no effect is promised for what cannot be confirmed"

    def test_an_export_from_before_the_last_rotation_does_not_count(self, screen):
        _export(screen, pw="the-password-before-rotation")
        g = _gate(_preview(screen), RT_GATE)
        assert g["state"] == "fail" and "OLDER" in g["detail"]

    def test_an_export_without_the_device_does_not_count(self, screen):
        _export(screen, hosts=("r4",))
        g = _gate(_preview(screen), RT_GATE)
        assert g["state"] == "fail" and "did not include r5" in g["detail"]

    def test_an_unreadable_log_is_not_an_absent_export(self, screen):
        with open(os.path.join(screen["data"], bg.EXPORT_LOG), "w") as fh:
            fh.write("{not json\n")
        g = _gate(_preview(screen), RT_GATE)
        assert g["state"] == "fail" and "could not be read" in g["detail"]
        assert "not an absent export" in g["detail"]

    def test_no_reason_is_a_failed_gate(self, screen):
        _export(screen)
        p = _preview(screen, reason="")
        assert _gate(p, "a reason is given")["state"] == "fail"
        assert not p["what"]["targets"][0]["selectable"]

    def test_it_writes_nothing(self, screen):
        _export(screen)
        before = _state(screen)
        _preview(screen)
        assert _state(screen) == before

    def test_no_credential_value_leaves(self, screen):
        _export(screen)
        text = screen["client"].post("/retire/preview", json={
            "device": "r5", "reason": REASON}).get_data(as_text=True)
        assert PW not in text


RT_GATE = "a break-glass export holds its current credential"


class TestEveryRefusalHasAGate:
    def test_the_plans_refusal_keys_are_the_screens_gates(self):
        """A refusal with no gate would be a reason drawn nowhere."""
        from modules.preview_confirm import RETIRE_GATES

        tree = ast.parse(open(os.path.join(ROOT, "modules", "nsot", "retire.py")).read())
        keys = {n.args[0].value for n in ast.walk(tree)
                if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "refuse"
                and n.args and isinstance(n.args[0], ast.Constant)}
        keys.add("list")             # the early return names it directly
        assert len(keys) >= 7, keys  # the scan found the refusals
        assert keys == {k for k, _t, _d in RETIRE_GATES}


class TestTheApply:
    def _apply(self, screen, p, **over):
        data = p["what"]["targets"][0]["select_data"]
        body = {"list_name": data["list"], "device": "r5", "reason": data["reason"],
                "hash": data["hash"], **over}
        return screen["client"].post("/retire/apply", json=body)

    def test_it_retires_against_the_log_and_says_so(self, screen):
        from modules.device import load_saved_devices
        _export(screen)
        r = self._apply(screen, _preview(screen))
        res = r.get_json()["result"]
        assert res["level"] == "success", res
        assert [d["hostname"] for d in load_saved_devices(screen["csv"])] == ["r4"]
        (t,) = res["targets"]
        assert t["checks"]["statements"][0].startswith("The export log says the newest export")
        assert "`nmas-retire --breakglass <file>` opens the record itself" in \
            t["checks"]["statements"][0]
        body = screen["R"].git(screen["repo"], "log", "-1", "--format=%B")[1]
        assert f"Actor: test-person@example.invalid" in body and "Retired-Device: r5" in body
        assert res["record"]["commit"] and res["record"]["commit"] in \
            screen["R"].git(screen["repo"], "rev-parse", "HEAD")[1]
        html = render_result(res)
        # The Not-Done list drawn again, after the fact.
        assert "Oxidized keeps polling" in html and "NetBox device 9 is KEPT" in html

    def test_the_record_reads_back_by_name_after_the_golden_is_gone(self, screen):
        _export(screen)
        self._apply(screen, _preview(screen))
        d = screen["client"].get("/golden/history/r5?list_name=Lab").get_json()
        assert d["ok"] and d["history"][0]["subject"].startswith("retire: r5 -- "), d

    def test_a_rotation_after_the_preview_refuses_at_apply(self, screen):
        """The gate is checked again at apply: the log names the credential
        the export held, and the row now holds another."""
        from modules import device
        _export(screen)
        p = _preview(screen)
        rows = device.load_saved_devices(screen["csv"])
        for row in rows:
            if row["hostname"] == "r5":
                row["password"] = device.fernet.encrypt(b"rotated-again-77").decode()
        device.write_devices_csv(rows, screen["csv"])
        res = self._apply(screen, p).get_json()["result"]
        assert res["level"] == "failed"
        assert "OLDER credential" in res["targets"][0]["reason"]
        assert "r5" in {d["hostname"] for d in device.load_saved_devices(screen["csv"])}

    def test_a_different_reason_is_a_different_plan(self, screen):
        _export(screen)
        res = self._apply(screen, _preview(screen), reason="something else").get_json()["result"]
        assert res["level"] == "failed" and "the plan changed" in res["targets"][0]["reason"]

    def test_no_list_named_does_nothing(self, screen):
        _export(screen)
        r = self._apply(screen, _preview(screen), list_name="")
        assert r.status_code == 400 and "Nothing was done" in r.get_json()["error"]

    def test_the_cli_basis_is_named_as_the_record(self, screen):
        p = RT.plan("Lab", "r5", REASON)
        out = RT.apply("Lab", "r5", reason=REASON, actor="op", confirmed_hash=p["hash"],
                       breakglass=_bg())
        assert out["ok"] and out["breakglass"]["basis"] == "record"
        assert "was opened" in out["breakglass"]["statement"]


class TestTheShippedClient:
    def _button(self, preview, reason):
        import dukpy
        js = (lift(shipped("nmas_preview_confirm.js"), "previewConfirmButton") + "\n"
              + lift(shipped("nmas_retire.js"), "retireButton"))
        return dukpy.evaljs(js + f"\nretireButton({json.dumps(preview)}, {json.dumps(reason)})")

    def test_a_reason_changed_after_the_preview_cannot_be_confirmed(self, screen):
        _export(screen)
        p = _preview(screen)
        assert self._button(p, REASON) == {"disabled": False, "text": "Retire r5"}
        assert self._button(p, REASON + " (edited)") == {
            "disabled": True, "text": "Preview again: the reason changed"}

    def test_a_refused_preview_cannot_be_confirmed(self, screen):
        out = self._button(_preview(screen), REASON)
        assert out["disabled"] and "refused" in out["text"]

    def test_the_device_page_offers_it(self):
        page = open(os.path.join(ROOT, "templates", "device.html"), encoding="utf-8").read()
        assert 'onclick="openRetire(this.dataset.hostname)"' in page
