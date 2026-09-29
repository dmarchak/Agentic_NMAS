"""The operator's Save All, 2026-09-28, reproduced on r2's REAL config.

The panel said to take a current baseline; Save All read every device, found
each unchanged, denied the baseline because r2 departs from its committed
intent (`load-interval 30`, C70's residue), and WROTE NOTHING. Then:

- the preview had computed both facts and offered Confirm as if the
  operation would do what it was run for;
- the operand that decided it read "committed intent: -1";
- the result said "9 of 9 device(s) recorded" over a save that recorded none,
  and did not mention the baseline;
- the denial existed in a toast and nowhere else, and the panel went on
  recommending the action that had just been refused.
"""

import json
import subprocess

import pytest

from tests.payload_render import render_preview, render_result
from tests.test_capture import build_capture_lab
from tests.test_intent_match import _broken


def _git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def cap(tmp_path, monkeypatch):
    """r2's golden already holds the host's break: a Save All now changes no
    golden, and r2 departs from its committed intent."""
    lab = build_capture_lab(monkeypatch, tmp_path)
    lab["running"]["r2"] = _broken(lab["captured"])
    d = lab["client"].post("/golden/capture/preview", json={"devices": ["r2"]}).get_json()
    h = d["preview"]["what"]["targets"][0]["select_data"]["hash"]
    out = lab["client"].post("/golden/capture/apply", json={"confirmations": {"r2": h}})
    assert out.get_json()["ok"]
    return lab


def _fleet_preview(cap):
    d = cap["client"].post("/golden/capture/preview", json={"devices": []}).get_json()
    assert d["ok"] and d["fleet"], d
    return d


class TestThePreviewSaysWhatConfirmingAchieves:
    def test_the_confirm_states_the_effect_and_the_button_says_it(self, cap):
        p = _fleet_preview(cap)["preview"]
        effect = p["confirm"]["effect"]
        assert effect.startswith("Nothing will be recorded as a golden and no baseline will "
                                 "be taken: r2 departs from its committed intent")
        assert "`load-interval 30`" in effect
        # The WORK as well as the outcome: the devices are still read.
        assert p["confirm"]["button"] == "Read the device and record the denial only"
        assert "Every device is still read at apply" in effect
        assert p["confirm"]["working"] == "Reading the device for the denial record…"
        assert p["confirm"]["mode"] == "denial_only"
        html = render_preview(p)
        confirm = html[html.index('data-pc-part="confirm"'):]
        assert "data-pc-effect" in confirm and "Nothing will be recorded as a golden" in confirm

    def test_the_deciding_operand_is_drawn_apart_in_words(self, cap):
        p = _fleet_preview(cap)["preview"]
        (op,) = [o for o in p["targets"][0]["operands"] if o["name"] == "committed intent"]
        assert op["blocks"] == "the baseline"
        assert op["value"].startswith("departs from its committed intent: 1 line(s) on the "
                                      "device that intent does not have (`load-interval 30`)")
        html = render_preview(p)
        assert "data-pc-blocking" in html and "blocks the baseline" in html

    def test_the_shipped_button_takes_the_servers_label(self, cap):
        import dukpy
        from tests.payload_render import lift, shipped
        p = _fleet_preview(cap)["preview"]
        js = lift(shipped("nmas_preview_confirm.js"), "previewConfirmButton")
        out = dukpy.evaljs(js + "\npreviewConfirmButton(" + json.dumps(p)
                           + ", 1, 'Record 1 device(s)')")
        assert out == {"disabled": False, "text": "Read the device and record the denial only"}

    def test_a_one_device_capture_that_changes_nothing_cannot_be_confirmed(self, cap):
        d = cap["client"].post("/golden/capture/preview", json={"devices": ["r2"]}).get_json()
        c = d["preview"]["confirm"]
        assert c["may"] is False and c["statement"].startswith("Nothing to confirm")


class TestTheResultAndTheRecord:
    def _apply_fleet(self, cap):
        p = _fleet_preview(cap)["preview"]
        h = p["what"]["targets"][0]["select_data"]["hash"]
        before = _git(cap["repo"], "rev-parse", "HEAD")
        out = cap["client"].post("/golden/capture/apply",
                                 json={"confirmations": {"r2": h}, "fleet": True}).get_json()
        assert out["ok"], out
        return out["result"], before

    def test_the_result_leads_with_the_denial_and_never_says_recorded(self, cap):
        r, _before = self._apply_fleet(cap)
        summary = r["happened"]["summary"]
        assert summary.startswith("No baseline was taken: r2 does not match its committed "
                                  "intent (")
        assert "load-interval 30" in summary
        assert "0 recorded as a new golden, 1 unchanged, so no golden changed" in summary
        assert r["level"] == "failed", "nothing it was run for happened"
        assert "records the baseline decision (denied)" in r["record"]["statement"]
        assert "No baseline was taken" in render_result(r)

    def test_the_denial_is_a_commit_that_changes_nothing(self, cap):
        r, before = self._apply_fleet(cap)
        head = _git(cap["repo"], "rev-parse", "HEAD")
        assert head != before and r["record"]["commit"] == head
        assert _git(cap["repo"], "rev-parse", "HEAD^{tree}") == \
            _git(cap["repo"], "rev-parse", f"{before}^{{tree}}")
        body = _git(cap["repo"], "log", "-1", "--format=%B")
        assert body.startswith("golden: no configuration changed; decision recorded")
        assert "Baseline: denied: r2 does not match its committed intent" in body
        assert "load-interval 30" in body

    def test_the_panel_then_names_the_blocker_not_save_all(self, cap):
        self._apply_fleet(cap)
        d = cap["client"].get("/golden/baselines").get_json()
        last = d["last_decision"]
        assert last["state"] == "denied" and "load-interval 30" in last["reasons"]
        import dukpy
        from tests.payload_render import lift, shipped
        src = shipped("partials__golden_repo.1.js")
        fns = ("_gEsc", "_gWhen", "_gBaselineClaim", "_gBaselineCoverage", "_gCredWarning",
               "_gBaselineDecision", "_gBaselineRow", "_gBaselineUsable", "_gToggle",
               "_gBaselinesHtml")
        rows = [{"tag": "baseline/x", "created": "2026-09-25T00:00:00Z",
                 "credential_stale": ["s1"], "deleted": False, "withdrawn": None}]
        html = dukpy.evaljs("\n".join(lift(src, f) for f in fns)
                            + f"\n_gBaselinesHtml({json.dumps(rows)}, {json.dumps(last)})")
        assert "A new one cannot be earned yet" in html and "load-interval 30" in html
        assert "Take a current one with Save All" not in html


class TestTheWorkIsNamedAsWellAsTheOutcome:
    """The operator (2026-09-28): "Record the denial only" was read as "skip the
    capture", and the in-flight panel then said every device "is being
    captured", contradicting the button that started it."""

    def test_the_apply_holds_each_device_under_the_confirmed_mode(self, cap, monkeypatch):
        from modules.nsot import device_ops
        seen = []
        real = device_ops.acquire_many

        def spy(*a, **kw):
            seen.append(kw.get("detail"))
            return real(*a, **kw)
        monkeypatch.setattr(device_ops, "acquire_many", spy)
        p = _fleet_preview(cap)["preview"]
        h = p["what"]["targets"][0]["select_data"]["hash"]
        cap["client"].post("/golden/capture/apply", json={
            "confirmations": {"r2": h}, "fleet": True, "mode": p["confirm"]["mode"]})
        cap["client"].post("/golden/capture/apply", json={
            "confirmations": {"r2": h}, "fleet": True, "mode": "<script>"})
        assert seen == ["denial_only", "record"], "an unknown mode is the ordinary capture"

    def test_the_panel_words_a_denial_hold_as_a_read(self, tmp_path, monkeypatch):
        from modules.nsot import device_ops
        monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
        device_ops.acquire("Lab", "r2", "capture", "op@example.com", "denial_only")
        device_ops.acquire("Lab", "r3", "capture", "op@example.com", "record")
        try:
            rows = {r["device"]: r for r in device_ops.in_flight("Lab")}
            assert rows["r2"]["words"].startswith("read for the denial record")
            assert rows["r3"]["words"] == "captured", "the ordinary capture is unchanged"
            text = device_ops.describe(device_ops.holder("Lab", "r2"))
            assert "is being read for the denial record" in text
            assert "denial_only" not in text, "the mode key is never drawn raw"
        finally:
            device_ops.release("Lab", "r2")
            device_ops.release("Lab", "r3")

    def test_the_shipped_client_sends_the_mode_and_says_it_is_reading(self):
        import os
        src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "static", "js", "nmas_capture.js"), encoding="utf-8").read()
        body = src[src.index("fetch('/golden/capture/apply'"):]
        body = body[:body.index("})")]
        assert "mode: conf.mode || 'record'" in body
        assert "btn.textContent = conf.working ||" in src


class TestNeedsAttentionNamesTheBlocker:
    def test_one_row_when_denied_and_none_usable(self, monkeypatch):
        from modules import attention, reader_job

        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
        monkeypatch.setattr(reader_job, "read_cached", lambda name: {
            "state": "ok", "doc": {"last_good": {"value_at": "2026-09-28T20:00:00Z", "value": {
                "lists": {"Lab": {"usable": "", "count": 1, "baselines": [
                    {"tag": "baseline/x", "withdrawn": False, "stale": ["s1"]}]}}}}}})
        log = ("abc1234567\x1f1790000000\x1fgolden: no configuration changed\n\n"
               "Source: save_all\nBaseline: denied: r2 does not match its committed intent "
               "(-1: - load-interval 30)\n")
        res = attention.baseline_source(log_fn=lambda: log)
        (row,) = res["rows"]
        assert row["what"] == ("No stored baseline can be re-applied, and a new one cannot be "
                               "earned yet")
        assert "load-interval 30" in row["cause"]
        assert "Save All alone will be refused again" in row["action"]["label"]


class TestTheBlockerNamesBothWaysOut:
    """The operator (2026-09-28): a button making intent match the device
    would launder a hand change into what should be. Both resolutions are
    named with what each ASSERTS, and neither is one click away."""

    def _blocker(self, cap):
        p = _fleet_preview(cap)["preview"]
        (op,) = [o for o in p["targets"][0]["operands"] if o.get("blocks")]
        return p, op

    def test_it_carries_the_lines_not_only_a_count(self, cap):
        _p, op = self._blocker(cap)
        assert "- load-interval 30" in op["lines"]

    def test_both_resolutions_are_named_with_what_each_asserts(self, cap):
        _p, op = self._blocker(cap)
        by = {r["asserts"]: r for r in op["resolutions"]}
        device_wrong = by["the device is wrong and intent is right"]
        # Mode B exists (7.3 step 2): the removal is a decision in the Deploy
        # plan, with a reason, and the note says when it is refused.
        assert "Deploy plan (Mode B)" in device_wrong["do"]
        assert "measured to remove exactly that line" in device_wrong["note"]
        assert "removed by hand" in device_wrong["note"], "the fallback is still said"
        adopt = by["the device is right, and intent will deploy it from now on"]
        assert adopt["do"].startswith("Adopt it into intent: Edit intent")
        assert "never automatic" in adopt["note"]

    def test_the_drawn_blocker_holds_no_button(self, cap):
        p, _op = self._blocker(cap)
        html = render_preview(p)
        block = html[html.index("data-pc-blocking"):]
        block = block[:block.index("</ul>")]
        assert "load-interval 30" in block and "asserts:" in block
        assert "<button" not in block and "onclick" not in block
