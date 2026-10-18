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
    # COMMITTED, not only written: intent is read from HEAD (C104), so a
    # fixture that writes and never commits is testing a device with none.
    from modules.nsot.repo import save_host_vars
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
    monkeypatch.setattr("modules.nsot.hostvars.hydrate_secrets",
                        lambda hv, host, ln="": {**hv, "secrets": dict(secrets)})
    # The credential store holds them, as it does on a real install: a ref's
    # committed intent names these refs, and the restore's intent guard asks
    # the store for each (a fixture with no committed intent never reached it).
    monkeypatch.setattr("modules.credentials.get_template_secret",
                        lambda key: secrets.get(key.rsplit(":", 1)[-1]))
    device = {"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
              "platform": "cisco_iosxe"}
    monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [dict(device)])
    running = {"r2": captured}
    monkeypatch.setattr(golden, "_read_running",
                        lambda d, phases=None: (running[d["hostname"]], ""))
    return {"client": A.app.test_client(), "repo": repo, "running": running,
            "captured": captured}


def run_capture_preview(client, body):
    """The preview as the card gets it (C188 step 2): the job started and waited for, then read
    back, through the cores v2 runs (tests/capture_core.py; today's two routes, which did this
    over HTTP, left with today's index at 7.8, P7-27). *client* is unused, kept so the callers
    read as they did."""
    from tests import capture_core

    return capture_core.post_preview(body)


def _preview(cap, devices=("r2",)):
    r = run_capture_preview(cap["client"], {"devices": list(devices)})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


def _hash(d, name="r2"):
    """The hash the confirm is bound to, as the client reads it."""
    return next(t for t in d["preview"]["what"]["targets"] if t["name"] == name)["select_data"]["hash"]


def _apply(cap, confirmations, fleet=False):
    from tests import capture_core

    r = capture_core.post_apply({"confirmations": confirmations, "fleet": fleet})
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
        # The words the preview carries; the device page's Capture card draws them
        # (tests/test_device_capture_v2.py, `test_it_draws_every_part_the_mockup_drew`). Today's
        # renderer, which this read until P7-27, left with today's index.
        p = d["preview"]
        assert p["titles"]["program"] == "What will change in its golden"
        assert "+ load-interval 30" in "\n".join(p["targets"][0]["program"]["lines"])
        part = "\n".join(w["text"] for w in p["what_not"]["items"])
        # In words, the lines named (the operator, 2026-09-28: "(+1 -1)" read
        # as a number and was the fact that decided the operation).
        assert "Departs from its committed intent: 1 line(s) on the device that intent " \
               "does not have (`load-interval 30`)" in part
        assert "1 line(s) in intent that the device does not have" in part
        assert "No baseline tag: capturing part of the fleet never earns one" in part
        gates = {g["name"]: g["state"] for g in d["preview"]["targets"][0]["gates"]}
        assert gates == {"device read": "pass", "capture unchanged since this preview": "at_apply",
                         # C99: nothing holds it, and the apply takes it
                         "no other operation holds this device": "at_apply"}

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
        assert any(t.get("checks") for t in result["targets"]), "checked against committed intent"
        # Today's renderer drew this level amber and no receipt; it left with today's index at
        # 7.8 (P7-27). The device page's Capture card draws the result
        # (tests/test_device_capture_v2.py, TestTheConfirm).

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
    # Today's Save All Configs (`index.1.js`'s saveAllConfigs, which opened the whole-fleet
    # capture) left with today's index at 7.8 (2026-10-17, P7-27): Devices › Save records every
    # device of a network (tests/test_save_v2.py, its bar's Save for the ticked and for every
    # device).

    def test_the_device_page_has_a_capture_button(self):
        """v2's device page's Actions menu (today's device page's Capture as golden button
        until it left at 7.8, P7-22)."""
        menu = open(os.path.join(ROOT, "templates", "v2", "_actions_menu.html"),
                    encoding="utf-8").read()
        assert "('Capture', 'capture', 'capture')" in menu

    def test_the_old_one_click_route_is_gone(self):
        """The one-click Save All is gone, and the capture is v2's device page's: its start
        and its confirm (today's /golden/capture/* left with today's index at 7.8, P7-27)."""
        import app as A

        rules = {r.rule for r in A.app.url_map.iter_rules()}
        assert "/golden_configs/save_all" not in rules
        assert {"/v2/device/<name>/capture/start", "/v2/device/<name>/capture/confirm"} <= rules


class TestAutoCreateIsAScopeOfCapture:
    """What Auto-Create was (one click, a first golden for every device
    without one, no preview, recorded as `ai-agent`, decided from files on
    disk) became a SCOPE of this one operation (minimalism, NSOT_STAGE7_PLAN 6a), and that
    scope (`scope: no_golden` on today's /golden/capture/preview, its button "Capture devices
    with no golden" on today's index) left with today's index at 7.8 (2026-10-17, P7-27). On v2 a
    device with no golden is captured from its page, or saved from Devices with the others
    ticked (Devices › Save). What stays the capture's own: a first golden is recorded as the
    person who confirmed it, never the agent."""

    @pytest.fixture
    def two(self, cap, monkeypatch):
        """r2 has a committed golden; s9 is in the manifest and has none."""
        from modules.nsot import manifest as M

        M.upsert_device(cap["repo"], "uid:s9", "s9", "203.0.113.19", platform="cisco_iosxe")
        devices = [{"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
                    "platform": "cisco_iosxe"},
                   {"hostname": "s9", "ip": "203.0.113.19", "device_type": "cisco_xe",
                    "platform": "cisco_iosxe"}]
        monkeypatch.setattr("modules.nsot.restore._devices_of",
                            lambda ln: [dict(d) for d in devices])
        cap["running"]["s9"] = cap["captured"].replace("hostname r2", "hostname s9")
        return cap

    def test_the_apply_records_the_person_never_the_agent(self, two):
        d = _preview(two, devices=("s9",))
        out = _apply(two, {"s9": _hash(d, "s9")})
        assert out["ok"], out
        from tests.conftest import TEST_PERSON
        msg = _last_message(two["repo"])
        assert "Source: capture" in msg and f"Actor: {TEST_PERSON}" in msg
        assert "ai-agent" not in msg

    def test_the_one_click_route_is_gone(self):
        rules = {r.rule for r in __import__("app").app.url_map.iter_rules()}
        assert "/golden_configs/auto_create" not in rules
