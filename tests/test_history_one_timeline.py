"""History as ONE timeline (C369; board D, signed off 2026-10-03): the History page and a
device's History tab are one reader, `history_sources.timeline`, and for every device they
return the SAME rows.

The lab (test_device_v2's, r3's real golden) is given records of every kind across three
devices: goldens by save and capture, a rename (s9 to s8, followed as `git log --follow`
follows one file), an intent commit, a measurement that changed no golden, the fleet's own
commit (the monitoring profile) and a baseline decision, deploy receipts, a planned-restart
window for two devices and one for the whole list, rotation rows (one for a device in no
list, which the list's timeline never shows), an acknowledgement, and a break-glass export
holding two devices. Then, for each device, the device tab's rows are the fleet timeline's
rows about that device, as data and as drawn; the fleet's own rows are on the page and never
on a tab.
"""

import html as _h
import json
import os
import re
import time

import pytest

from modules import history_sources as HS
from tests.test_device_v2 import _get, lab  # noqa: F401 (the fixture)

DEVICES = ("r3", "r4", "s8")


def _now(offset=0):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset))


def _commit(repo, message, *paths, allow_empty=False):
    from modules.nsot import repo as R
    for p in paths:
        assert R.git(repo, "add", "-A", p)[0] == 0
    args = ["commit", "-q", "-m", message] + (["--allow-empty"] if allow_empty else [])
    rc, out, err = R.git(repo, *args)
    assert rc == 0, err or out


@pytest.fixture
def planted(lab):  # noqa: F811
    from modules import acknowledgements, config, restarts
    from modules.nsot import credential_rotation as cr
    from modules.nsot import listref, receipts
    from modules.nsot import repo as R

    repo = lab["repo"]
    body = open(os.path.join(repo, "golden", "r3.cfg"), encoding="utf-8").read()
    assert R.save_golden("Lab", [R.GoldenItem("r4", body.replace("hostname r3", "hostname r4"),
                                              "203.0.113.14", platform="cisco_ios"),
                                 R.GoldenItem("s9", body.replace("hostname r3", "hostname s9"),
                                              "203.0.113.29", platform="cisco_ios")],
                         source="capture", actor="alex@example.com", allow_new=True)["ok"]
    # A rename, by hand: the older commits name s9, and s8's history follows them.
    assert R.git(repo, "mv", "golden/s9.cfg", "golden/s8.cfg")[0] == 0
    _commit(repo, "golden: rename s9 to s8\n\nSource: rename\nActor: alex@example.com")
    with open(os.path.join(repo, "golden", "r3.cfg"), "a", encoding="utf-8") as fh:
        fh.write("! a second save\n")
    _commit(repo, "golden: 1 device(s) via save_all\n\nSource: save_all\n"
                  "Actor: operator@example.com\nDevices: r3\nDevices-Measured: r3, r4\n"
                  "Baseline: earned", "golden/r3.cfg")
    _commit(repo, "golden: measured\n\nSource: capture\nActor: alex@example.com\n"
                  "Devices-Measured: s8", allow_empty=True)
    os.makedirs(os.path.join(repo, "profile"), exist_ok=True)
    with open(os.path.join(repo, "profile", "monitoring.yml"), "w", encoding="utf-8") as fh:
        fh.write("sections: {}\n")
    _commit(repo, "profile: proposed\n\nSource: profile\nActor: operator@example.com",
            "profile/monitoring.yml")
    from modules.nsot import hostvars
    hostvars.write_committed(repo, {"hostname": "r4", "interfaces": []})
    assert R.save_host_vars("Lab", ["r4"], actor="alex@example.com", source="extraction")["ok"]
    for i, d in enumerate(("r3", "r4", "r3")):
        assert receipts.write("Lab", [{"id": f"x{i}", "at": _now(i), "action": "deploy",
                                       "device": d, "actor": "operator@example.com",
                                       "outcome": "deployed", "program_lines": 2,
                                       "golden_commit": ""}])["ok"]
    assert restarts.record_planned(["r3", "r4"], time.time(), time.time() + 600,
                                   "alex@example.com", "IOS-XE upgrade", "test",
                                   list_name="Lab")["ok"]
    assert restarts.record_planned(["*"], time.time(), time.time() + 600, "alex@example.com",
                                   "the whole list", "test", list_name="Lab")["ok"]
    for d in ("r3", "zz-in-no-list"):
        cr.record_outcome("rotate", {"device": d, "actor": "alex@example.com",
                                     "state": cr.ROTATED_PERSISTED, "via": "device page",
                                     "steps": [{"name": "push", "ok": True}]})
    acknowledgements.record("authorisations:Lab:r4:shutdown", _now(), why="planned work",
                            by="alex@example.com", verified="person",
                            kind="repeated_authorisation", what="shutdown authorised 3 times")
    with open(os.path.join(config.DATA_DIR, "breakglass_exports.jsonl"), "a") as fh:
        fh.write(json.dumps({"at": time.time(), "list": "Lab", "actor": "alex@example.com",
                             "via": "browser", "devices": {"r3": "d1", "r4": "d2"},
                             "key_fingerprint": "fp"}) + "\n")
    return listref.resolve("Lab")


class TestOneReaderTheSameRows:
    def test_every_device_tab_is_the_fleet_timeline_filtered_to_it(self, planted):
        from modules import device_page
        fleet = HS.timeline(planted, limit=HS.MAX_LIMIT, members=list(DEVICES))
        assert not fleet["errors"], fleet["errors"]
        kinds = {e["kind"] for e in fleet["events"]}
        # The floor: the lab reaches every kind the parity is claimed over.
        assert {"golden", "intent", "measured", "commit", "decision", "receipt", "window",
                "rotation", "acknowledged", "breakglass"} <= kinds, kinds
        for d in DEVICES:
            tab = device_page.history(planted, {"hostname": d})
            assert not tab["errors"], (d, tab["errors"])
            mine = [e for e in fleet["events"] if HS.about(e, d)][:tab["limit"]]
            assert tab["events"], d
            assert tab["events"] == mine, d

    def test_the_rename_is_followed_by_both(self, planted):
        from modules import device_page
        s8 = device_page.history(planted, {"hostname": "s8"})["events"]
        whats = [e["what"] for e in s8 if e["kind"] == "golden"]
        assert whats == ["Golden recorded (rename)", "Golden recorded (capture)"], [
            (e["what"], e["devices"], e["detail"]) for e in s8 if e["kind"] == "golden"]
        assert [e["devices"] for e in s8 if e["kind"] == "golden"] == [["s8"], ["r4", "s8"]]

    def test_the_fleets_own_rows_are_on_the_page_and_never_on_a_tab(self, planted):
        from modules import device_page
        fleet = HS.timeline(planted, limit=HS.MAX_LIMIT, members=list(DEVICES))["events"]
        own = [e for e in fleet if not e["devices"]]
        assert {e["kind"] for e in own} == {"commit", "decision"}
        for d in DEVICES:
            assert not [e for e in device_page.history(planted, {"hostname": d})["events"]
                        if not e["devices"]]
        assert not any("zz-in-no-list" in e["devices"] for e in fleet), \
            "a rotation row names no list: the list's timeline keeps its own devices"

    def test_both_screens_draw_the_same_rows(self, lab, planted, monkeypatch):  # noqa: F811
        from modules.nsot import listref
        monkeypatch.setattr(listref, "active", lambda: planted)
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda *a, **k: [{"hostname": d} for d in DEVICES])

        def rows(html):
            text = lambda s: " ".join(_h.unescape(re.sub(r"<[^>]+>", " ", s)).split())  # noqa: E731
            return [text(s) for s in re.findall(r'<summary class="hist-sum">(.*?)</summary>',
                                                html, re.S)]
        for d in DEVICES:
            tab = rows(_get(lab, f"/v2/device/{d}/history")[1])
            page = rows(lab["client"].get(f"/v2/history?device={d}&since=").get_data(as_text=True))
            assert tab and tab == page[:len(tab)], d
