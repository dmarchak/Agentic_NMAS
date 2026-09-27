"""7.1 step 5: restore scope, chosen rather than inherited (register C80).

From the interface a baseline could be re-applied only to the whole fleet,
and the scoped paths all restored at HEAD, so restoring one device from a
baseline needed the browser console. Now:

* the Device page's "Restore from…" lists this device's golden now, its own
  golden tags and every baseline that holds it, each with its credential
  state, and a chosen point opens the guarded preview for this device alone;
* the Baselines panel's "Re-apply" asks for a scope that starts EMPTY, with
  the whole fleet as its own explicit choice.

The repository is real: r2's real configuration, its onboarding golden, and
a baseline earned by a whole-fleet capture at intent (`build_capture_lab`).
The shipped component runs in duktape against the route's real response.
"""

import json
import os

import dukpy
import pytest

from tests.payload_render import lift, shipped

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RS = "nmas_restore_scope.js"


def _js(expr: str):
    return dukpy.evaljs("var window = {};\n" + shipped(RS) + "\n" + expr)


@pytest.fixture
def lab(tmp_path, monkeypatch):
    from tests.test_capture import build_capture_lab

    lab = build_capture_lab(monkeypatch, tmp_path)
    c = lab["client"]
    d = c.post("/golden/capture/preview", json={"devices": []}).get_json()
    h = d["preview"]["what"]["targets"][0]["select_data"]["hash"]
    out = c.post("/golden/capture/apply",
                 json={"confirmations": {"r2": h}, "fleet": True}).get_json()
    lab["baseline"] = out["result"]["record"]["baseline"]
    assert lab["baseline"].startswith("baseline/"), "the fixture must hold a baseline"
    return lab


def _points(lab, host="r2"):
    r = lab["client"].get(f"/golden/restore_points/{host}")
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


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

    def test_an_account_the_device_no_longer_has_is_silent(self, lab):
        """The other case, from the same real line: HEAD holds a different
        account, so re-applying the baseline would ADD the old one back. No
        guard refuses an addition (C79), so the chooser must say it."""
        import re

        from modules.nsot.repo import GoldenItem, save_golden

        line = re.search(r"^username admin (privilege 15 password 0 \S+)$",
                         lab["captured"], re.M)
        renamed = lab["captured"].replace(line.group(0),
                                          "username operator " + line.group(1))
        save_golden("Lab", [GoldenItem("r2", renamed, "203.0.113.12")],
                    source="manual", actor="t", baseline=False)
        by_ref = {p["ref"]: p["credential"] for p in _points(lab)["points"]}
        assert by_ref[lab["baseline"]] == "silent", by_ref


class TestTheChooserDrawsIt:
    def test_one_row_per_point_each_opening_its_own_ref(self, lab):
        d = _points(lab)
        html = _js("window.restorePointsHtml(" + json.dumps(d) + ")")
        for p in d["points"]:
            assert f'data-rs-ref="{p["ref"]}"' in html
            assert f'data-ref="{p["ref"]}"' in html
        assert "Nothing is sent from this list" in html
        assert "in list <strong>Lab</strong>" in html

    def test_every_value_is_escaped(self, lab):
        d = _points(lab)
        d["points"][1]["subject"] = "<img src=x onerror=alert(1)>"
        html = _js("window.restorePointsHtml(" + json.dumps(d) + ")")
        assert "<img" not in html and "&lt;img" in html

    def test_a_failed_read_is_not_an_empty_list(self):
        html = _js("window.restorePointsHtml({ok: false, error: 'boom'})")
        assert "not the same as there being none" in html and "boom" in html

    def test_a_point_that_would_add_back_an_account_says_so(self, lab):
        d = _points(lab)
        d["points"][1]["credential"] = "silent"
        html = _js("window.restorePointsHtml(" + json.dumps(d) + ")")
        assert "would ADD BACK an account" in html

    def test_choosing_goes_to_the_guarded_preview_for_this_device_alone(self):
        url = _js("window.restoreFromUrl('r2', 'baseline/20260927T154517Z')")
        assert url == "/?restore_head=r2&restore_ref=baseline%2F20260927T154517Z"


class TestTheHandoffReachesThePreview:
    """The seam: the URL the chooser builds, read by the index page."""

    def test_the_ref_and_the_device_arrive_at_previewBaselineRestore(self):
        fn = lift(shipped("partials__golden_repo.3.js"), "_restoreHeadFromUrl")
        calls = dukpy.evaljs(
            "var calls = [];"
            "var window = {location: {search: '?restore_head=r2&restore_ref=baseline%2FX',"
            " pathname: '/'}};"
            "var history = {replaceState: function () {}};"
            "function URLSearchParams(s) { var m = {};"
            "  s.replace(/^\\?/, '').split('&').forEach(function (kv) {"
            "    var p = kv.split('='); m[p[0]] = decodeURIComponent(p[1]); });"
            "  this.get = function (k) { return k in m ? m[k] : null; };"
            "  this.delete = function (k) { delete m[k]; };"
            "  this.toString = function () { return Object.keys(m).join('&'); }; }"
            "function previewBaselineRestore(ref, un, from) { calls.push([ref, un, from]); }"
            + fn + "; _restoreHeadFromUrl(); calls")
        assert calls == [["baseline/X", None, {"devices": ["r2"]}]]


class TestTheBaselineScopeStartsEmpty:
    B = {"tag": "baseline/X", "devices": ["r1", "r2", "s1"],
         "credential_stale": ["s1"], "credential_silent": [], "missing_devices": ["r6"]}

    def test_every_device_is_offered_and_none_is_ticked(self):
        html = _js("window.baselineScopeHtml(" + json.dumps(self.B) + ")")
        for host in self.B["devices"]:
            assert f'data-rs-device="{host}"' in html
        assert "checked" not in html
        assert "data-rs-fleet" in html and "predates r6" in html

    @pytest.mark.parametrize("devices,fleet,expected", [
        ([], False, None),
        ([("r1", True), ("r2", False)], False, {"devices": ["r1"]}),
        ([("r1", True), ("r2", True)], False, {"devices": ["r1", "r2"]}),
        ([], True, {"devices": None}),
        ([("r1", True)], True, {"devices": None}),
    ])
    def test_the_selection(self, devices, fleet, expected):
        boxes = [{"checked": c, "dataset": {"rsDevice": h}} for h, c in devices]
        got = _js("window.baselineScopeSelection(" + json.dumps(boxes) + ", "
                  + json.dumps({"checked": fleet}) + ")")
        assert got == expected


class TestTheScreensReachIt:
    def test_the_device_page_has_restore_from(self):
        page = open(os.path.join(ROOT, "templates", "device.html"), encoding="utf-8").read()
        assert 'onclick="openRestoreFrom(this.dataset.hostname)"' in page

    def test_the_component_is_loaded_on_every_page(self):
        base = open(os.path.join(ROOT, "templates", "base.html"), encoding="utf-8").read()
        assert "filename='js/nmas_restore_scope.js'" in base

    def test_re_apply_asks_for_a_scope_before_the_preview(self):
        body = lift(shipped("partials__golden_repo.1.js"), "confirmBaselineRestore")
        assert body.index("chooseBaselineScope(b)") < body.index("previewBaselineRestore(")
        assert "if (!scope) return;" in body
        assert "previewBaselineRestore(tag, null, {devices: scope.devices})" in body
        # The acknowledgement names the CHOSEN devices only.
        assert ".filter(inScope)" in body

    def test_the_baselines_route_carries_the_devices_to_offer(self, lab):
        d = lab["client"].get("/golden/baselines").get_json()
        b = next(x for x in d["baselines"] if x["tag"] == lab["baseline"])
        assert b["devices"] == ["r2"]
