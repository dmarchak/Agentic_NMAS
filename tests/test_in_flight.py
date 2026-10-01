"""C99: an operation that is RUNNING says so, since when, and what it waits on.

A restore ran for fifty seconds with nothing on screen, the operator read the
silence as "staged", started a deploy of the same device, and one silent
screen produced a second change on a live device. The standing rule: every
process tells the person what happened or what to do next.

One panel, fixed above every modal, on every page, reading C98's lock (every
holder, the CLIs included) and the receipts (so a reload does not lose a
result); and a gate in every preview that names a holder BEFORE the confirm.
"""

from tests.test_capture import run_capture_preview
import json
import os
import time

import dukpy
import pytest

from modules.nsot import device_ops as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def no_hold_survives_a_test():
    yield
    with D._mu:
        stale = list(D._held.items())
        D._held.clear()
    for _key, mine in stale:
        try:
            os.close(mine["fd"])
        except (OSError, KeyError, TypeError):
            pass


class TestTheLockSaysWhatRuns:
    def test_a_held_device_is_listed_with_its_step_in_words(self):
        with D.hold("lab", "r2", "restore", "ops@example.com"):
            D.note("verify")
            rows = D.in_flight("lab")
        assert [r["device"] for r in rows] == ["r2"]
        row = rows[0]
        assert row["words"] == "restored" and row["actor"] == "ops@example.com"
        assert row["step"] == "verify" and "90 s" in row["step_words"]
        assert row["stalled"] is False and row["held_for_s"] >= 0
        assert row["text"].startswith("r2 is being restored by ops@example.com")

    def test_nothing_held_is_an_empty_list_and_creates_nothing(self):
        from modules import config

        folder = os.path.join(config.DATA_DIR, "device_ops", "nothing-here")
        assert D.in_flight("nothing-here") == []
        assert not os.path.exists(folder)

    def test_an_unknown_step_is_shown_as_it_is(self):
        with D.hold("lab", "r3", "rotate", "ops@example.com"):
            D.note("live_user_line_read")
            assert D.in_flight("lab")[0]["step_words"] == "live_user_line_read"

    def test_a_stall_is_said(self):
        with D.hold("lab", "r4", "deploy", "ops@example.com"):
            D.note("deploy")
            later = time.time() + D.STALL_AFTER_SECONDS + 5
            assert D.in_flight("lab", now=later)[0]["stalled"] is True


class TestTheRoute:
    @pytest.fixture
    def client(self, monkeypatch, tmp_path):
        import app as A

        monkeypatch.setattr("routes.operations.time.time", lambda: 2_000_000_000.0)
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
        monkeypatch.setattr("modules.nsot.receipts.path_for",
                            lambda ln: str(tmp_path / "receipts.jsonl"))
        return A.app.test_client(), tmp_path / "receipts.jsonl"

    def test_running_and_recently_finished(self, client):
        c, receipts = client
        stamp = lambda t: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
        with open(receipts, "w") as fh:
            for dev, t in (("r1", 2_000_000_000 - 7200), ("r2", 2_000_000_000 - 60)):
                fh.write(json.dumps({"device": dev, "action": "restore", "outcome": "deployed",
                                     "at": stamp(t), "actor": "ops@example.com"}) + "\n")
        with D.hold("lab", "s1", "deploy", "ops@example.com"):
            d = c.get("/operations/in_flight").get_json()
        assert d["ok"] and [r["device"] for r in d["running"]] == ["s1"]
        assert [r["device"] for r in d["recent"]] == ["r2"], "only the last 30 min"
        assert d["recent_state"] == "ok" and "not_recorded" in d

    def test_a_failed_read_is_an_error_not_an_empty_list(self, client, monkeypatch):
        c, _r = client
        monkeypatch.setattr(D, "in_flight", lambda *a, **k: 1 / 0)
        r = c.get("/operations/in_flight")
        assert r.status_code == 500 and r.get_json()["ok"] is False


def _panel(payload, seen=None):
    src = open(os.path.join(ROOT, "static", "js", "nmas_in_flight.js")).read()
    return dukpy.evaljs("var window = {};\n" + src
                        + f"\nwindow.inFlightPanelHtml({json.dumps(payload)}, "
                          f"{json.dumps(seen or {})});")


class TestTheShippedPanel:
    RUN = {"device": "r2", "words": "restored", "actor": "ops@example.com",
           "held_for_s": 49, "step_words": "verifying: routing protocols are given up "
           "to 90 s to settle, and it waits for them", "step_ago_s": 12, "stalled": False}

    def test_running_names_who_what_since_and_the_wait(self):
        html = _panel({"ok": True, "running": [self.RUN], "recent": []})
        assert "Running now" in html and "<strong>r2</strong> is being restored" in html
        assert "for 49 s" in html and "90 s to settle" in html

    def test_a_failed_read_never_reads_as_nothing_running(self):
        html = _panel({"ok": False, "error": "timeout"})
        assert "Could not ask" in html and "not the same as none running" in html

    def test_nothing_is_empty(self):
        assert _panel({"ok": True, "running": [], "recent": []}) == ""

    def test_a_finished_one_names_its_receipt_and_can_be_hidden(self):
        row = {"device": "r2", "action": "restore", "outcome": "deployed",
               "at": "2026-09-27T18:53:37Z", "actor": "ops@example.com"}
        html = _panel({"ok": True, "running": [], "recent": [row], "window_s": 1800})
        assert "Changes tab" in html and "18:53:37 UTC" in html and "deployed" in html
        assert _panel({"ok": True, "running": [], "recent": [row]},
                      {"r2|2026-09-27T18:53:37Z": True}) == ""

    def test_every_value_is_escaped(self):
        html = _panel({"ok": True, "running": [dict(self.RUN, device="<b>x</b>")],
                       "recent": []})
        assert "<b>x</b>" not in html and "&lt;b&gt;" in html


class TestTheWiring:
    """Every long apply marks itself busy and unmarks in a `finally`, and the
    panel sits above Bootstrap's modals (z-index 1055)."""

    APPLIES = {
        "static/js/nmas_capture.js": "/golden/capture/apply",
        "static/js/gen/partials__deploy_wizard.1.js": "/deploy/apply",
        "static/js/gen/partials__golden_repo.3.js": "/golden/restore/apply",
        "static/js/gen/partials__onboard_wizard.2.js": "/onboard/verify/",
    }

    def test_each_apply_is_wrapped(self):
        import re
        for rel, route in self.APPLIES.items():
            src = open(os.path.join(ROOT, rel)).read()
            # The fetch itself: the route's first mention can be a comment.
            # The APPLY's fetch, never a preview's on the same prefix (Verify's
            # preview, P.9 step c, reads one device and runs nothing long).
            at = next(m.start() for m in re.finditer(re.escape("fetch('" + route), src)
                      if "/preview" not in src[m.start():m.start() + 120])
            before = src.rfind("inFlightBusy(true)", 0, at)
            assert before != -1 and at - before < 400, f"{rel}: not marked busy"
            after = re.search(r"finally\s*\{\s*inFlightBusy\(false\)", src[at:])
            assert after, f"{rel}: not unmarked in a finally"

    def test_the_panel_is_above_every_modal_on_both_pages(self):
        base = open(os.path.join(ROOT, "templates", "base.html")).read()
        assert 'id="inFlightPanel"' in base and "z-index:1090" in base
        assert "js/nmas_in_flight.js" in base


class TestThePreviewNamesTheHolder:
    def test_a_held_device_fails_its_gate_and_cannot_be_confirmed(self, monkeypatch, tmp_path):
        from tests.test_capture import build_capture_lab

        lab = build_capture_lab(monkeypatch, tmp_path)
        with D.hold("Lab", "r2", "restore", "someone@example.com"):
            d = run_capture_preview(lab["client"], {"devices": ["r2"]}).get_json()
        # Selectability is in the `what` part; per-device gates in `targets`.
        target = d["preview"]["what"]["targets"][0]
        gates = {g["name"]: g for g in d["preview"]["targets"][0]["gates"]}
        busy = gates["no other operation holds this device"]
        assert busy["state"] == "fail" and "someone@example.com" in busy["detail"]
        assert target["selectable"] is False

    def test_a_free_device_says_it_is_checked_at_apply(self, monkeypatch, tmp_path):
        from tests.test_capture import build_capture_lab

        lab = build_capture_lab(monkeypatch, tmp_path)
        d = run_capture_preview(lab["client"], {"devices": ["r2"]}).get_json()
        target = d["preview"]["what"]["targets"][0]
        gates = {g["name"]: g for g in d["preview"]["targets"][0]["gates"]}
        assert gates["no other operation holds this device"]["state"] == "at_apply"
        assert target["selectable"] is True


class TestAnUnselectableTargetSaysWhy:
    """The C70 re-run: a deploy tried mid-restore made r2's checkbox
    unclickable with nothing on or near it. The refusal was at the panel and
    the interaction at the checkbox, and a greyed control with no reason is
    what P.3's own rule rejects."""

    def test_the_held_device_row_names_the_holder(self, monkeypatch, tmp_path):
        from tests.test_capture import build_capture_lab

        lab = build_capture_lab(monkeypatch, tmp_path)
        with D.hold("Lab", "r2", "restore", "someone@example.com"):
            d = run_capture_preview(lab["client"], {"devices": ["r2"]}).get_json()
        target = d["preview"]["what"]["targets"][0]
        assert target["selectable"] is False
        assert "someone@example.com" in target["why_not"], target["why_not"]
        src = open(os.path.join(ROOT, "static", "js", "nmas_preview_confirm.js")).read()
        html = dukpy.evaljs("var window = {};\n" + src + "\nwindow.previewConfirmHtml("
                            + json.dumps(d["preview"]) + ", {selectable: true});")
        assert "data-pc-why-not" in html and "someone@example.com" in html
        assert "disabled" in html

    def test_a_selectable_one_draws_no_reason(self, monkeypatch, tmp_path):
        from tests.test_capture import build_capture_lab

        lab = build_capture_lab(monkeypatch, tmp_path)
        d = run_capture_preview(lab["client"], {"devices": ["r2"]}).get_json()
        assert d["preview"]["what"]["targets"][0]["why_not"] == ""

    def test_the_builder_refuses_one_that_says_nothing(self):
        from modules import preview_confirm as P

        silent = {"name": "r9", "state": "blocked", "selectable": False,
                  "program": {"lines": [], "none": "nothing"},
                  "operands": [{"name": "x", "value": "y"}],
                  "gates": [P.gate("device read", "pass", "")]}
        with pytest.raises(P.PreviewIncomplete, match="nothing says why"):
            P.build(action="t", summary="s", targets=[silent], what_not=[],
                    nothing_left_out="n", confirm={"statement": "c"})
