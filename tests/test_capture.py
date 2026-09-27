"""7.1 step 4: capture as an operation (register C82, C89).

There was no per-device capture, and Save All promoted whatever a device held
to golden, a baseline tag and the remote on one click. Now a capture is
previewed (each device read NOW, against its golden and its committed
INTENT), confirmed by capture hash, re-read at apply, recorded in one commit
by the verified person, and its result drawn by the component.

The fixture is r2's REAL configuration with committed intent parsed from it,
and the host's exact break (OSPFv3 off Gi2, `load-interval 30`). Only the
device read is replaced.
"""

import json
import os
import subprocess

import pytest

from tests.payload_render import render_preview, render_result
from tests.test_intent_match import R2, _broken

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def cap(tmp_path, monkeypatch):
    return build_capture_lab(monkeypatch, tmp_path)


def build_capture_lab(monkeypatch, tmp_path):
    """The real app, a list 'Lab' holding r2 with its golden and committed
    intent, and a device whose running config the test sets. Also the payload
    check's provider (`payload_providers.capture_*`)."""
    import app as A
    import routes.golden as golden
    from modules.nsot import hostvars, templates_repo
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import GoldenItem, save_golden

    list_dir = tmp_path / "lab"
    repo = str(list_dir / "config_repo")
    os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
    monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda ctx: None)
    monkeypatch.setattr("modules.settings_schema.get_setting",
                        lambda key, default=None: {
                            "nsot_git_author_name": "NMAS",
                            "nsot_git_author_email": "nmas@localhost"}.get(key, default))
    captured = open(R2, encoding="utf-8").read()
    templates_repo.seed_templates(repo)
    save_golden("Lab", [GoldenItem("r2", captured, "203.0.113.12", platform="cisco_iosxe")],
                source="onboarding", actor="t", allow_new=True, baseline=False)
    intent = get_parser("cisco_iosxe").parse(captured)
    secrets = dict(intent.get("secrets") or {})
    hostvars.write_committed(repo, intent)
    monkeypatch.setattr("modules.nsot.hostvars.hydrate_secrets",
                        lambda hv, host, ln="": {**hv, "secrets": dict(secrets)})
    device = {"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
              "platform": "cisco_iosxe"}
    monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [dict(device)])
    running = {"r2": captured}
    monkeypatch.setattr(golden, "_read_running",
                        lambda d: (running[d["hostname"]], ""))
    return {"client": A.app.test_client(), "repo": repo, "running": running,
            "captured": captured}


def _preview(cap, devices=("r2",)):
    r = cap["client"].post("/golden/capture/preview", json={"devices": list(devices)})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


def _hash(d, name="r2"):
    """The hash the confirm is bound to, as the client reads it."""
    return next(t for t in d["preview"]["what"]["targets"] if t["name"] == name)["select_data"]["hash"]


def _apply(cap, confirmations, fleet=False):
    r = cap["client"].post("/golden/capture/apply",
                           json={"confirmations": confirmations, "fleet": fleet})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


def _last_message(repo):
    return subprocess.run(["git", "-C", repo, "log", "-1", "--format=%B"],
                          capture_output=True, text=True).stdout


class TestThePreviewAsksWhatTheRestOfTheToolAsks:
    def test_the_break_is_shown_against_the_golden_and_against_intent(self, cap):
        cap["running"]["r2"] = _broken(cap["captured"])
        d = _preview(cap)
        assert "devices" not in d, "the raw reads are not sent; the preview draws them"
        target = d["preview"]["what"]["targets"][0]
        assert target["state"] == "capturable" and target["select_data"]["hash"]
        html = render_preview(d["preview"])
        assert "What will change in its golden" in html
        assert "+ load-interval 30" in html
        part = html[html.index('data-pc-part="what_not"'):]
        assert "Departs from its committed intent (+1 -1)" in part
        assert "No baseline tag: capturing part of the fleet never earns one" in part
        gates = {g["name"]: g["state"] for g in d["preview"]["targets"][0]["gates"]}
        assert gates == {"device read": "pass", "capture unchanged since this preview": "at_apply"}

    def test_it_writes_nothing(self, cap):
        before = _last_message(cap["repo"])
        cap["running"]["r2"] = _broken(cap["captured"])
        _preview(cap)
        assert _last_message(cap["repo"]) == before


class TestTheApplyRecordsWhatWasConfirmed:
    def test_a_departing_capture_is_recorded_marked_and_never_green(self, cap):
        cap["running"]["r2"] = _broken(cap["captured"])
        h = _hash(_preview(cap))
        d = _apply(cap, {"r2": h})
        msg = _last_message(cap["repo"])
        assert "Source: capture" in msg and "Intent-Match: no: r2 (+1 -1)" in msg
        from tests.conftest import TEST_PERSON
        assert f"Actor: {TEST_PERSON}" in msg and "Actor-Verified: access" in msg
        result = d["result"]
        assert result["level"] == "partial"
        html = render_result(result)
        assert "alert-success" not in html and "Checked against committed intent" in html
        assert "data-pr-receipt" not in html, "a capture has no receipt, and says nothing false"

    def test_a_device_that_moved_since_the_preview_is_refused(self, cap):
        h = _hash(_preview(cap))
        cap["running"]["r2"] = _broken(cap["captured"])          # moved after the preview
        before = _last_message(cap["repo"])
        d = _apply(cap, {"r2": h})
        assert d["result"]["happened"]["targets"][0]["outcome"] == "moved"
        assert _last_message(cap["repo"]) == before, "nothing was recorded"

    def test_the_whole_fleet_at_its_intent_earns_the_baseline_and_is_green(self, cap):
        h = _hash(_preview(cap, devices=()))
        d = _apply(cap, {"r2": h}, fleet=True)
        assert d["result"]["record"]["baseline"].startswith("baseline/")
        assert d["result"]["level"] == "success"

    def test_the_whole_fleet_with_a_departure_earns_no_baseline(self, cap):
        cap["running"]["r2"] = _broken(cap["captured"])
        h = _hash(_preview(cap, devices=()))
        d = _apply(cap, {"r2": h}, fleet=True)
        assert not d["result"]["record"]["baseline"]
        reasons = [i["text"] for i in d["result"]["did_not"]["items"] if i["kind"] == "no_baseline"]
        assert any("r2 does not match its committed intent" in r for r in reasons)


class TestTheScreensReachIt:
    def test_save_all_opens_the_fleet_capture(self):
        from tests.payload_render import lift, shipped

        body = lift(shipped("index.1.js"), "saveAllConfigs")
        assert "previewCapture(null)" in body and "fetch(" not in body

    def test_the_device_page_has_a_capture_button(self):
        page = open(os.path.join(ROOT, "templates", "device.html"), encoding="utf-8").read()
        assert 'onclick="previewCapture([this.dataset.hostname])"' in page

    def test_the_old_one_click_route_is_gone(self):
        import app as A

        rules = {r.rule for r in A.app.url_map.iter_rules()}
        assert "/golden_configs/save_all" not in rules
        assert {"/golden/capture/preview", "/golden/capture/apply"} <= rules
