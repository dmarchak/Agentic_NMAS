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

Save All's preview and result were drawn by today's renderer and Save All was opened from today's
index; both left at 7.8 (2026-10-17, P7-27). What is held here is what the capture core computes
and records for the whole fleet (tests/capture_core.py), which no v2 route starts any more:
Devices › Save is the network's save on v2, and tests/test_save_v2.py holds its baseline denial
said with why (`test_a_network_off_its_intent_is_saved_and_its_baseline_denied_saying_why`) and
its repeated-baseline warning (TestTheRepeatedBaseline).
"""

from tests.test_capture import run_capture_preview
from tests import capture_core
import subprocess

import pytest

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
    d = run_capture_preview(lab["client"], {"devices": ["r2"]}).get_json()
    h = d["preview"]["what"]["targets"][0]["select_data"]["hash"]
    out = capture_core.post_apply({"confirmations": {"r2": h}})
    assert out.get_json()["ok"]
    return lab


def _fleet_preview(cap):
    d = run_capture_preview(cap["client"], {"devices": []}).get_json()
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

    def test_the_deciding_operand_is_carried_apart_in_words(self, cap):
        p = _fleet_preview(cap)["preview"]
        (op,) = [o for o in p["targets"][0]["operands"] if o["name"] == "committed intent"]
        assert op["blocks"] == "the baseline"
        assert op["value"].startswith("departs from its committed intent: 1 line(s) on the "
                                      "device that intent does not have (`load-interval 30`)")

    def test_a_one_device_capture_that_changes_nothing_cannot_be_confirmed(self, cap):
        d = run_capture_preview(cap["client"], {"devices": ["r2"]}).get_json()
        c = d["preview"]["confirm"]
        assert c["may"] is False and c["statement"].startswith("Nothing to confirm")


class TestTheResultAndTheRecord:
    def _apply_fleet(self, cap):
        p = _fleet_preview(cap)["preview"]
        h = p["what"]["targets"][0]["select_data"]["hash"]
        before = _git(cap["repo"], "rev-parse", "HEAD")
        out = capture_core.post_apply(
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

    def test_needs_attention_then_names_the_blocker_not_save_all(self, cap, monkeypatch):
        """With no stored baseline usable, the remedy is the denial's, never "Save All" again.
        Today's Baselines panel said it from /golden/baselines' last decision until both left at
        7.8 (2026-10-17); Needs attention's baseline row reads the same decision from the
        history (`attention.baseline_source`)."""
        from modules import attention as A
        from tests.test_baseline_partial_operation import _usable_none

        self._apply_fleet(cap)
        _usable_none(monkeypatch)
        (r,) = A.baseline_source()["rows"]
        assert r["what"] == ("No stored baseline can be re-applied, and a new one cannot be "
                             "earned yet")
        assert "the last Save All was denied" in r["cause"] and "load-interval 30" in r["cause"]
        assert r["action"]["label"].startswith("Resolve each departure")
        assert "Take a current baseline" not in r["action"]["label"]


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
        capture_core.post_apply({
            "confirmations": {"r2": h}, "fleet": True, "mode": p["confirm"]["mode"]})
        capture_core.post_apply({
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
