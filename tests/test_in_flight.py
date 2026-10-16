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

        monkeypatch.setattr("modules.in_flight.time.time", lambda: 2_000_000_000.0)
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


# ---------------------------------------------------------------------------
# v2 (C537): the top bar's In progress chip, a device page reopening its card, C217's one row
# and C540's words. Boards A, B and C (canvas v66), counted as signed off 2026-10-16.
# ---------------------------------------------------------------------------

from tests.test_device_rotate_v2 import _confirm, _preview, rot  # noqa: E402,F401
from tests.test_persist_screen import lab  # noqa: E402,F401

HX = {"HX-Request": "true"}


class TestOneOperationOneRow:
    """C217: a rotation on r2 drew its hold's row ("now: persisting", true) AND its job's own
    ("starting … may be stuck", false, the job registry never moving its step)."""

    JOB = {"job": "j1", "list": "Lab", "device": "r2", "card": "rotate", "state": "running"}
    OP = {"id": "j1", "device": "rotating r2", "operation": "credential rotation",
          "words": "credential rotation", "actor": "ops@example.com", "step_words": "starting",
          "stalled": True}

    def test_a_device_job_holding_its_device_is_its_hold_s_row(self):
        from modules import in_flight as F
        hold = {"device": "r2", "list": "Lab", "operation": "rotate", "words": "rotated",
                "step_words": "persisting", "stalled": False}
        rows = F.merge([hold], [dict(self.OP)], [dict(self.JOB)])
        assert len(rows) == 1, rows
        assert rows[0]["step_words"] == "persisting" and rows[0]["job"] == "j1"
        assert rows[0]["stalled"] is False

    def test_one_not_holding_yet_is_its_device_s_row_in_words_and_never_stuck(self):
        from modules import in_flight as F
        (row,) = F.merge([], [dict(self.OP)], [dict(self.JOB)])
        assert (row["device"], row["list"], row["words"]) == ("r2", "Lab", "rotated")
        assert row["stalled"] is False and row["text"].startswith("r2 is being rotated by")

    def test_an_operation_on_no_device_is_kept_as_it_is(self):
        from modules import in_flight as F
        op = dict(self.OP, id="other")
        assert F.merge([], [op], [dict(self.JOB)]) == [op]


def _until(check, bound_s=10.0):
    """Wait for *check()* to be true; the bound (10 s) is far past a fake rotation's
    milliseconds, and a firing bound fails naming what it waited on."""
    import time as _t
    end = _t.time() + bound_s
    while _t.time() < end:
        if check():
            return
        _t.sleep(0.01)
    raise AssertionError(f"waited {bound_s} s for {check.__doc__ or check}")


@pytest.fixture
def chip(rot, monkeypatch):  # noqa: F811
    """The rotate world (`tests/test_device_rotate_v2.rot`), its network the only one, a
    rotation that waits on a gate, and a person looking whom the test names."""
    import threading

    from modules.nsot import credential_rotation as cr
    monkeypatch.setattr("modules.integration_groups.network_names", lambda: ["Lab"])
    who = {"viewer": ""}
    monkeypatch.setattr("routes.operations.viewer_key", lambda: who["viewer"])
    gate = threading.Event()
    real = cr.rotate

    def slow(*a, **k):
        gate.wait(10)
        return real(*a, **k)
    monkeypatch.setattr(cr, "rotate", slow)
    yield dict(rot, gate=gate, who=who)
    gate.set()
    # Every rotation this test started ends here, while its fakes are still in place.
    from modules.nsot import capture_job
    for job in [r["job"] for r in capture_job.card_jobs() if r["state"] == "running"]:
        assert capture_job.wait(job, 30), f"job {job} did not end within 30 s"


def _bar(c):
    r = c["client"].get("/operations/in_flight", headers=HX)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _start(c):
    """Confirm a rotation of r2 and return its job id once it holds r2."""
    import re as _re
    waiting = _confirm(c, _preview(c)).get_data(as_text=True)
    job = _re.search(r"/rotate/job/([0-9a-f]+)", waiting).group(1)

    def held():
        """r2 held by the rotation"""
        return D.holder("Lab", "r2") is not None
    _until(held)
    return job


def _run_out(c, job):
    """Let the rotation finish, without drawing its card anywhere."""
    from modules.nsot import capture_job
    c["gate"].set()
    assert capture_job.wait(job, 30)


class TestTheChip:
    def test_nothing_running_and_nothing_waiting_draws_nothing(self, chip):
        assert "ip-chip" not in _bar(chip)
        d = chip["client"].get("/operations/in_flight").get_json()
        assert d["ok"] is True and d["running"] == [], "today's JSON is unchanged"

    def test_every_v2_page_asks_for_it_and_hears_every_change(self, chip):
        page = chip["client"].get("/v2/devices").get_data(as_text=True)
        slot = page[page.index('id="nmas-in-progress"') - 60:page.index('id="nmas-in-progress"') + 400]
        assert 'hx-get="/operations/in_flight"' in slot
        for key in ("in_progress", "device_holds", "device_progress"):
            assert f"nmas:{key} from:body" in slot, key
        assert "every " not in slot[slot.index("hx-trigger"):slot.index("hx-swap")], "no timer"

    def test_a_running_rotation_is_one_row_its_step_and_a_way_back_to_its_card(self, chip):
        _start(chip)
        html = _bar(chip)
        assert 'class="ip-chip ip-run"' in html and "In progress: 1 running" in html
        assert html.count('class="ip-row"') == 1, "one operation, one row (C217)"
        assert "<strong>r2</strong> · Rotate credential" in html
        assert "Read the account" in html and "step 1 of 6" in html
        assert 'href="/v2/device/r2?list=Lab"' in html and "Open its card" in html
        d = chip["client"].get("/operations/in_flight?list_name=Lab").get_json()
        assert [r["device"] for r in d["running"]] == ["r2"], "today's panel: one row too"

    def test_one_finished_elsewhere_shows_its_outcome_until_it_is_opened(self, chip):
        _run_out(chip, _start(chip))
        html = _bar(chip)
        assert 'class="ip-chip ip-ok"' in html and "In progress: 1 done" in html
        assert "rotated and persisted" in html and "Open the result" in html
        page = chip["client"].get("/v2/device/r2").get_data(as_text=True)
        body = page[page.index('id="tab-body"'):]
        assert "op-card op-ok" in body and "Finished at" in body, "the page opens the result"
        assert "ip-chip" not in _bar(chip), "opened: the chip lets it go"
        again = chip["client"].get("/v2/device/r2").get_data(as_text=True)
        assert "Finished at" not in again, "an opened result is not reopened"

    def test_red_wins(self, chip):
        from modules.nsot import credential_rotation as cr
        chip["rot"]["persist_state"] = cr.ROTATED_UNVERIFIED
        _run_out(chip, _start(chip))
        html = _bar(chip)
        assert 'class="ip-chip ip-danger"' in html and "1 failed" in html

    def test_opened_is_each_person_s_own(self, chip):
        _run_out(chip, _start(chip))
        chip["who"]["viewer"] = "a@example.invalid"
        chip["client"].get("/v2/device/r2")
        assert "ip-chip" not in _bar(chip)
        chip["who"]["viewer"] = "b@example.invalid"
        assert "Open the result" in _bar(chip), "someone who has not seen it still has it"

    def test_its_card_drawn_in_place_opens_it(self, chip):
        """Watching the card when the result arrives is opening it."""
        job = _start(chip)
        _run_out(chip, job)
        chip["client"].get(f"/v2/device/r2/rotate/job/{job}?back=overview")
        assert "ip-chip" not in _bar(chip)

    def test_an_unreadable_network_is_never_nothing_running(self, chip, monkeypatch):
        monkeypatch.setattr(D, "in_flight", lambda *a, **k: 1 / 0)
        html = _bar(chip)
        assert 'class="ip-chip ip-danger"' in html
        assert "Could not read what runs in Lab: ZeroDivisionError" in html

    def test_a_failed_read_is_unknown_never_nothing(self, chip, monkeypatch):
        monkeypatch.setattr("modules.in_flight.chip", lambda *a, **k: 1 / 0)
        html = _bar(chip)
        assert "Could not ask which operations are running" in html
        assert "not the same as none running" in html


class TestTheChipHearsEveryChange:
    def test_a_job_s_start_its_end_and_its_result_opened_are_announced(self, monkeypatch):
        """The chip re-reads on `in_progress`, never on a timer: a job's start and its end each
        announce it, and so does a person opening its result (their other tabs)."""
        from modules import invalidation as I
        from modules.nsot import capture_job
        heard = []
        monkeypatch.setattr(I, "_emitter", lambda event, msg: heard.append(msg))
        job = capture_job.start("Lab", "rotating r2", "a@example.invalid", lambda j: {},
                                announce_keys=("rotation",), announcer="rotation",
                                device="r2", card="rotate")
        assert capture_job.wait(job, 10)
        moved = [m for m in heard if m["keys"] == ["in_progress"]]
        assert len(moved) == 2 and {m["by"] for m in moved} == {"in-progress"}, heard
        assert capture_job.mark_opened(job, "a@example.invalid") is True
        assert capture_job.mark_opened(job, "a@example.invalid") is False, "once is news"
        assert len([m for m in heard if m["keys"] == ["in_progress"]]) == 3


class TestTheDevicePageReopens:
    def test_a_running_rotation_reopens_its_running_card_never_a_second_rotation(self, chip):
        _start(chip)
        page = chip["client"].get("/v2/device/r2?tab=history").get_data(as_text=True)
        body = page[page.index('id="tab-body"'):]
        assert "Rotating r2's credential" in body and "Reopened: started by" in body
        assert "/rotate/preview" not in body and "op-confirm" not in body

    def test_a_card_freed_by_a_rotation_shows_that_rotation_never_rotate_again(self, chip):
        import re as _re
        job = _start(chip)
        held = _preview(chip)                    # drawn while r2 is held by the rotation
        since = _re.search(r"since=(\d+)", held).group(1)
        _run_out(chip, job)
        free = chip["client"].get(f"/v2/device/r2/when-free?op=rotate&back=history&since={since}")
        out = free.get_data(as_text=True)
        assert "op-card op-ok" in out and "rotated and persisted" in out
        assert "/rotate/preview" not in out
        later = int(since) + 3600                # a card drawn after it ended: a fresh one
        fresh = chip["client"].get(f"/v2/device/r2/when-free?op=rotate&back=history&since={later}")
        assert 'hx-post="/v2/device/r2/rotate/preview?list=Lab"' in fresh.get_data(as_text=True)


class TestC540TheConfirmNamesWhatExists:
    def test_v2_names_the_chip_and_today_s_the_panel(self):
        from modules.preview_confirm import rotate_preview
        from tests.test_rotate_screen import _plan
        v2 = rotate_preview(_plan(), busy="", request=None, drawn_on="v2")["confirm"]["effect"]
        today = rotate_preview(_plan(), busy="", request=None)["confirm"]["effect"]
        assert "In progress chip in the top bar" in v2 and "in-flight panel" not in v2
        assert "in-flight panel" in today and "In progress chip" not in today

    def test_the_v2_card_says_it(self, chip):
        html = _preview(chip)
        assert "In progress chip in the top bar" in html and "in-flight panel" not in html
