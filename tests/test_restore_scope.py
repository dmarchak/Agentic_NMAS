"""7.1 step 5: restore scope, chosen rather than inherited (register C80).

From the interface a baseline could be re-applied only to the whole fleet,
and the scoped paths all restored at HEAD, so restoring one device from a
baseline needed the browser console. Now the device's restore points are its
golden now, its own golden tags and every baseline that holds it, each with its
credential state, read by the v2 device page's Restore from…, which opens the
guarded preview for this device alone. (Today's chooser and the Baselines
panel's empty-scope Re-apply left at 7.8, 2026-10-17.)

The repository is real: r2's real configuration, its onboarding golden, and
a baseline earned by a whole-fleet capture at intent (`build_capture_lab`).
"""

from tests.test_capture import run_capture_preview
from tests import capture_core
import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def lab(tmp_path, monkeypatch):
    from tests.test_capture import build_capture_lab

    lab = build_capture_lab(monkeypatch, tmp_path)
    c = lab["client"]
    d = run_capture_preview(c, {"devices": []}).get_json()
    h = d["preview"]["what"]["targets"][0]["select_data"]["hash"]
    out = capture_core.post_apply(
                 json={"confirmations": {"r2": h}, "fleet": True}).get_json()
    lab["baseline"] = out["result"]["record"]["baseline"]
    assert lab["baseline"].startswith("baseline/"), "the fixture must hold a baseline"
    return lab


def _points(lab, host="r2"):
    """*host*'s restore points as the v2 device page's chooser reads them
    (`routes.golden.restore_points_for`; today's /golden/restore_points returned the same until
    it left at 7.8, 2026-10-17)."""
    from routes.golden import restore_points_for

    return {"hostname": host, "points": restore_points_for("Lab", host)}


class TestTheDevicesRestorePoints:
    def test_its_golden_now_its_own_tags_and_the_baseline_that_holds_it(self, lab):
        d = _points(lab)
        kinds = [p["kind"] for p in d["points"]]
        refs = [p["ref"] for p in d["points"]]
        assert kinds[0] == "head" and refs[0] == "HEAD"
        assert lab["baseline"] in refs
        assert any(r.startswith("golden/r2/") for r in refs), refs
        assert all(p.get("credential") for p in d["points"])

    def test_newest_first_after_its_golden_now(self, lab):
        created = [p["created"] for p in _points(lab)["points"][1:]]
        assert created == sorted(created, reverse=True) and len(created) >= 2

    def test_a_baseline_without_the_device_is_not_a_restore_point_for_it(self, lab):
        """Re-applying it would leave the device exactly as it is."""
        from modules.nsot.repo import device_restore_points

        points = device_restore_points(lab["repo"], "s9")
        assert [p["ref"] for p in points] == ["HEAD"]

    def test_a_rotation_after_the_baseline_is_named_and_no_value_leaves(self, lab):
        """r2's credential rotated after the baseline: the baseline's point
        says the restore refuses it (C75), its own golden now says current,
        and neither the old value nor the new one is in the response."""
        import re

        from modules.nsot.repo import GoldenItem, save_golden

        line = re.search(r"^username admin privilege 15 password 0 (\S+)$",
                         lab["captured"], re.M)
        old = line.group(1)
        new = "rotated-after-the-baseline-7f3a"
        # Only the value token: in the fixture the value can equal the
        # account name, and replacing every occurrence renames the ACCOUNT,
        # which is a different case (an account added back, `silent`).
        rotated = lab["captured"].replace(
            line.group(0), line.group(0)[:line.start(1) - line.start(0)] + new)
        save_golden("Lab", [GoldenItem("r2", rotated, "203.0.113.12")],
                    source="manual", actor="t", baseline=False)
        d = _points(lab)
        by_ref = {p["ref"]: p["credential"] for p in d["points"]}
        assert by_ref["HEAD"] == "current"
        assert by_ref[lab["baseline"]] == "refused", by_ref
        body = json.dumps(d)
        assert len(old) >= 4 and new not in body and f"password 0 {old}" not in body

    def test_an_account_the_device_no_longer_has_is_refused(self, lab):
        """The other case, from the same real line: HEAD holds a different
        account, so re-applying the baseline would ADD the old one back. Until
        C79 no guard refused an addition and this read `silent`; now the
        restore's own check refuses it (unless the line is authorised with a
        reason), so the chooser reads `refused` like a rewrite."""
        import re

        from modules.nsot.repo import GoldenItem, save_golden

        line = re.search(r"^username admin (privilege 15 password 0 \S+)$",
                         lab["captured"], re.M)
        renamed = lab["captured"].replace(line.group(0),
                                          "username operator " + line.group(1))
        save_golden("Lab", [GoldenItem("r2", renamed, "203.0.113.12")],
                    source="manual", actor="t", baseline=False)
        by_ref = {p["ref"]: p["credential"] for p in _points(lab)["points"]}
        assert by_ref[lab["baseline"]] == "refused", by_ref


# Today's chooser (nmas_restore_scope.js: the device page's Restore from…, its rows and its
# hand-off to the index page's preview) and the Baselines panel's empty-scope Re-apply, with
# /golden/restore_points and /golden/baselines, left at 7.8 (2026-10-17, P7-21), and their
# tests here with them. The v2 device page's Restore from… draws these points and opens the
# preview for this device alone (tests/test_device_restore_v2.py); History's Re-apply… restores
# the devices a baseline holds, naming each it leaves as it is (tests/test_reapply_v2.py).

class TestTheScreensReachIt:
    def test_the_device_page_has_restore_from(self):
        """v2's device page's Actions menu (today's device page's Restore from… button until
        it left at 7.8, P7-22)."""
        menu = open(os.path.join(ROOT, "templates", "v2", "_actions_menu.html"),
                    encoding="utf-8").read()
        assert "('Restore from…', 'restore', 'restore')" in menu
