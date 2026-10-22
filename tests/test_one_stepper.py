"""ONE stepper for every multi-step or multi-device operation (the operator, 2026-10-12: "the
stepper you built for Save All (C605: one row per device, its steps with times, an overall
bar, the commit as its own last row; horizontal on desktop, the vertical step-by-step on
phone) was agreed as THE progress display for every multi-step or multi-device operation, but
only Save All uses it. Example from today's walk: Monitoring › Send the IP SLA probes shows 'r1
done… r2 being applied' as a plain list").

The component: `modules/run_stepper.py` (the model), `templates/v2/_run_stepper.html`
(`run_stepper`, the one macro), `.run` in nmas-v2.css (across on a desk, down below 640 px),
`static/js/nmas_stepper.js` (the running step's clock). Held here:

- every operation page (the survey, OPERATION_PAGES) draws its progress through `run_stepper`,
  is on NOT_YET (exact, only shrinking), or on DOES_NOT_FIT with the reason a stepper does not
  fit (also logged in docs/fidelity/stepper.md);
- no v2 template or script draws progress any other way: a `<progress>` element, a step marked
  current (`aria-current="step"`), the retired `job_stepper` macro, or a stepper or step-list
  class, outside the component; found by parsing the markup, with a planted case;
- the model's groups, counts, bar and grouping at scale; the script's clock (duktape).
"""

import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2 = os.path.join(ROOT, "templates", "v2")
COMPONENT = {"templates/v2/_run_stepper.html", "static/js/nmas_stepper.js"}

#: Every v2 page an operation that runs steps or devices draws its progress or result on (the
#: survey of 2026-10-12, docs/fidelity/stepper.md): template -> the operations it draws.
OPERATION_PAGES = {
    "_save.html": "Save (one device or many)",
    "_deploy.html": "Deploy, one device",
    "_apply_job.html": "Deploy several: the monitoring profile's Apply, IP SLA's Send, "
                       "Coverage's Deploy missing, History's Re-apply",
    "_restore.html": "Restore",
    "_reload.html": "Reload, and Revert by reload",
    "_rotate.html": "Rotate a credential",
    "_adopt.html": "Adopt",
    "_update.html": "Update",
    "_capture.html": "Capture",
    # pending.html draws it through its progress fragment, read again on `pending` (C1193).
    "_pending_progress.html": "Onboarding and first boot",
    "_onboard_pending.html": "Verify, onboarding's arrival",
    "_netbox_job.html": "NetBox import and removal",
    "_sc_result.html": "Show commands runs",
    "_lp_result.html": "The logging-path test",
    "_persist.html": "Persist",
    "_retire.html": "Retire",
    "_template_op.html": "Template approve",
    "_dhcp_subnet.html": "DHCP subnet writes",
    "_dhcp_reserve.html": "DHCP reservation writes",
    "_dhcp_exclusion.html": "DHCP exclusion writes",
}
#: Operation pages not yet converted (the 2026-10-12 program, finished the same day): EXACT,
#: so nothing joins it.
NOT_YET: set = set()
#: Operation pages where a stepper does not fit: template -> why (said in the fidelity record
#: and the approval log too).
DOES_NOT_FIT = {
    "_template_op.html": "Approve's check runs in its request, holds no device and sends "
                         "nothing, so there is no running state to watch; its per-device rows "
                         "are the comparison's evidence, every line that failed and where to "
                         "clear it (board B), where one step per device would draw every row "
                         "done beside a result that says pass or fail. Approve and Revoke are "
                         "a commit each",
}
#: Operation pages that draw the component's bar and counts alone (`run_summary`), because their
#: per-device rows are the run's own answers, not steps: template -> why (EXACT; said in the
#: fidelity record too).
SUMMARY_ONLY = {
    "_sc_result.html": "a Show commands run has one step per device (ask, read the answer), so a "
                       "row of steps says nothing the bar does not; its rows are the answers, "
                       "grouped where alike (boards C, D and C2)",
    "_lp_result.html": "the logging-path test sends one line per device and then watches Loki "
                       "for it: its rows are the arrivals with their delay (board F), and its "
                       "two phases are the bar's two labels, Lines sent then Lines received",
}
#: Files that still draw progress some other way, until their page is converted: EXACT.
OTHER_PROGRESS: set = set()

_CLASS = re.compile(r'class="([^"]*)"')
_STEPPISH = re.compile(r"^(stepper|step-[a-z_]+|[a-z]+-steplist|[a-z]+-step|[a-z]+-steps)$")
#: Class tokens that name a list of steps that is NOT progress: a preview's program and gates,
#: a settings card's Test results, setup instructions (`set-steps`).
NOT_PROGRESS = {"set-steps"}


def progress_marks(text: str) -> list:
    """What in *text* draws progress: ``["<progress>", 'aria-current="step"',
    "job_stepper(", "data-stepper", "class token X", ...]``."""
    found = []
    if re.search(r"<progress\b", text):
        found.append("<progress>")
    if 'aria-current="step"' in text:
        found.append('aria-current="step"')
    if re.search(r"\bjob_stepper\(", text):
        found.append("job_stepper(")
    if re.search(r"\bdata-stepper\b", text):
        found.append("data-stepper")
    for m in _CLASS.finditer(text):
        for tok in m.group(1).split():
            if "{" in tok or tok.startswith("run") or tok in NOT_PROGRESS:
                continue
            if _STEPPISH.match(tok):
                found.append(f"class token {tok}")
    return sorted(set(found))


def _files():
    out = [f"templates/v2/{f}" for f in sorted(os.listdir(V2)) if f.endswith(".html")]
    js = os.path.join(ROOT, "static", "js")
    out += [f"static/js/{f}" for f in sorted(os.listdir(js))
            if f.startswith("nmas_") and f.endswith(".js")]
    return out


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def _uses_component(text: str) -> bool:
    return _calls(text, "run_stepper") or _calls(text, "run_summary")


def _calls(text: str, macro: str) -> bool:
    """*text* imports *macro* from the component and calls it."""
    imp = re.search(r'from "v2/_run_stepper\.html" import ([\w, ]+)', text)
    return bool(imp and macro in [m.strip() for m in imp.group(1).split(",")]
                and re.search(r"\b%s\(" % macro, text))


class TestEveryOperationPageUsesTheOneStepper:
    def test_the_survey_is_whole(self):
        assert len(OPERATION_PAGES) >= 20                                   # the floor
        for f in OPERATION_PAGES:
            assert os.path.exists(os.path.join(V2, f)), f

    def test_each_page_uses_it_or_is_named_with_why(self):
        assert not NOT_YET & set(DOES_NOT_FIT)
        assert NOT_YET | set(DOES_NOT_FIT) <= set(OPERATION_PAGES)
        using = {f for f in OPERATION_PAGES if _uses_component(_read(f"templates/v2/{f}"))}
        assert using | NOT_YET | set(DOES_NOT_FIT) == set(OPERATION_PAGES), \
            sorted(set(OPERATION_PAGES) - using - NOT_YET - set(DOES_NOT_FIT))
        assert not using & NOT_YET, ("converted: take it off NOT_YET", sorted(using & NOT_YET))
        for f, why in DOES_NOT_FIT.items():
            assert len(why) > 40, f"{f}: say why a stepper does not fit"
        summary_only = {f for f in using if not _calls(_read(f"templates/v2/{f}"), "run_stepper")}
        assert summary_only == set(SUMMARY_ONLY), (
            "draws only the bar and counts: say why on SUMMARY_ONLY",
            sorted(summary_only - set(SUMMARY_ONLY)),
            "now draws rows: take it off SUMMARY_ONLY", sorted(set(SUMMARY_ONLY) - summary_only))
        for f, why in SUMMARY_ONLY.items():
            assert len(why) > 40, f"{f}: say why rows of steps do not fit"

    def test_no_page_draws_progress_any_other_way(self):
        files = _files()
        assert len(files) >= 150                                            # the floor
        other = {f for f in files if f not in COMPONENT and progress_marks(_read(f))}
        assert other == OTHER_PROGRESS, (
            "drawn some other way (convert it to run_stepper)", sorted(other - OTHER_PROGRESS),
            "converted (take it off OTHER_PROGRESS)", sorted(OTHER_PROGRESS - other))

    def test_the_scan_finds_a_planted_case(self):
        assert progress_marks('<progress max="3" value="1"></progress>') == ["<progress>"]
        assert progress_marks('<ol class="stepper"><li class="step step-current">') == [
            "class token step-current", "class token stepper"]
        assert progress_marks('<ol class="ob-steplist">') == ["class token ob-steplist"]
        assert progress_marks('{{ job_stepper(c.steps) }}') == ["job_stepper("]
        assert progress_marks('<ol class="set-steps">') == [], "a preview's list is not progress"
        assert progress_marks('<ol class="run-steps"><li class="run-step">') == []


class TestTheBarAndCountsAlone:
    """Show commands and the logging-path test, running, draw the component's bar and counts
    (`run_summary`) from their own records, through the real templates."""

    def _draw(self, monkeypatch, record, job_state="running"):
        import app as A
        from flask import render_template
        from modules import reads_page
        from modules.nsot import capture_job, reads as R
        monkeypatch.setattr(capture_job, "get", lambda job_id: {"state": job_state})
        monkeypatch.setattr(R, "get", lambda list_name, run_id: record)
        c = reads_page.result("Lab", record["id"], job="j1")
        with A.app.test_request_context():
            return c, render_template("v2/_sc_result.html", r=c)

    def test_a_show_commands_run_counts_its_devices_by_state(self, monkeypatch):
        from modules.nsot import reads as R
        ans = {"command": "show clock", "state": R.ANSWERED, "sha256": "a" * 64,
               "answer": "x"}
        record = {"id": "run1", "state": "running", "devices": ["r1", "r2", "r3", "r4"],
                  "commands": ["show clock"], "started_at": 1.0,
                  "results": {"r1": {"state": R.ANSWERED, "answers": [ans]},
                              "r2": {"state": R.FAILED, "answers": []}}}
        c, html = self._draw(monkeypatch, record)
        assert c["state"] == "running"
        assert html.count("data-run-stepper") == 1 and "run-summary" in html
        assert 'max="4" value="2" aria-label="2 of 4 devices read"' in html
        counts = re.sub(r"<[^>]+>", "", re.search(r'<p class="run-counts">(.*?)</p>',
                                                  html, re.S).group(1))
        assert counts == "1 answered · 2 still reading · 1 failed", counts
        assert 'class="run-failed"' in html

    def test_a_logging_path_test_says_what_it_sent_then_what_arrived(self, monkeypatch):
        from modules.nsot import logging_path
        base = {"id": "run2", "devices": ["r1", "r2", "r3"], "commands": ["send log x"],
                "purpose": logging_path.PURPOSE, "started_at": 1.0}
        _c, html = self._draw(monkeypatch, dict(base, state="running",
                                                results={"r1": {}}))
        assert 'max="3" value="1" aria-label="1 of 3 lines sent"' in html
        _c, html = self._draw(monkeypatch, dict(
            base, state="done", results={"r1": {}, "r2": {}, "r3": {}},
            logging_path={"state": "watching", "received": {"r2": 4}}), job_state="done")
        assert 'max="3" value="1" aria-label="1 of 3 lines received"' in html
        assert "<progress" not in html.replace('<progress class="run-bar"', "")


class TestTheNetBoxJob:
    """A NetBox preview or import on THE stepper: the phases `netbox_client` reports are its
    steps, the card redraws as the phase moves (`op_progress.on_phase`), and a list is no
    device."""

    PID = "stepper-netbox-0001"

    def _progress(self, phase, writing=False):
        from modules import op_progress
        op_progress.start(self.PID, "previewed for import", "NetBox (Lab)")
        op_progress.update(self.PID, phase=phase, devices_total=9, devices_done=3,
                           current="r4", writing=writing)
        return op_progress.get(self.PID)

    def _states(self, card):
        (r,) = card["rows"]
        return [(s["key"], s["state"]) for s in r["steps"]], r

    def test_a_preview_is_on_the_phase_it_reports(self):
        from modules import netbox_jobs as NJ
        card = NJ.run_card({"state": "previewing", "operation": "import", "list": "Lab"},
                           self._progress("reading and planning each device"))
        steps, r = self._states(card)
        assert steps == [("setup", "done"), ("devices", "running"), ("cables", "waiting"),
                         ("preview", "waiting")]
        assert r["name"] == "Lab" and r["device"] is False
        assert "device 4 of 9 (r4)" in r["steps"][1]["note"]

    def test_an_import_starts_re_checked_and_follows_the_write_once_it_says_so(self):
        from modules import netbox_jobs as NJ
        job = {"state": "importing", "operation": "import_all", "list": ""}
        # The re-check's last phase still stands until the write says it began.
        steps, r = self._states(NJ.run_card(job, self._progress("cables between devices")))
        assert steps[:2] == [("recheck", "done"), ("setup", "running")]
        assert r["name"] == "every network"
        steps, _r = self._states(NJ.run_card(job, self._progress("cables between devices",
                                                                 writing=True)))
        assert steps == [("recheck", "done"), ("setup", "done"), ("devices", "done"),
                         ("cables", "running")]

    def test_no_progress_held_says_so_and_other_states_draw_none(self):
        from modules import netbox_jobs as NJ
        _s, r = self._states(NJ.run_card({"state": "previewing", "operation": "remove",
                                          "list": "Lab"}, None))
        assert "holds no progress" in r["steps"][0]["note"]
        assert NJ.run_card({"state": "previewed", "operation": "import"}, None) is None

    def test_a_phase_change_runs_the_watcher_once_and_finish_drops_it(self):
        from modules import op_progress
        heard = []
        op_progress.start(self.PID, "previewed for import", "NetBox (Lab)")
        op_progress.on_phase(self.PID, lambda: heard.append(1))
        op_progress.update(self.PID, phase="reading and planning each device")
        op_progress.update(self.PID, phase="reading and planning each device", devices_done=4)
        op_progress.tick(self.PID)
        assert heard == [1]
        op_progress.finish(self.PID)
        op_progress.update(self.PID, phase="cables between devices")
        assert heard == [1]

    def test_the_card_draws_it(self):
        import app as A
        from flask import render_template
        from modules import netbox_jobs as NJ
        job = {"id": "x", "state": "previewing", "operation": "import", "list": "Lab"}
        with A.app.test_request_context():
            html = render_template("v2/_netbox_job.html", job=job, run=NJ.run_card(
                job, self._progress("setting up the region, site and template")))
        assert html.count("data-run-stepper") == 1
        assert re.search(r'<li class="run-step run-step-running" data-step="setup"', html)
        assert 'href="/v2/device/Lab"' not in html


class TestTheModel:
    def _rows(self, groups):
        from modules import run_stepper as RS
        return [RS.row(f"d{i}", g, [RS.step("a", "A", "done", took_s=1)]) for i, g in
                enumerate(groups)]

    def test_counts_bar_and_order_lead_with_what_to_act_on(self):
        from modules import run_stepper as RS
        c = RS.card(self._rows(["done", "running", "failed", "waiting", "done"]), label="x")
        assert c["counts"] == {"failed": 1, "partial": 0, "running": 1, "waiting": 1,
                               "not_reached": 0, "done": 2}
        assert c["bar"] == {"max": 5, "value": 3, "words": "3 of 5 devices through, 1 running, "
                                                            "1 waiting, 1 failed"}
        assert [g["name"] for g in c["groups"]] == ["failed", "running", "waiting", "done"]
        assert [t["group"] for t in c["tally"]] == ["done", "running", "waiting", "failed"]
        assert c["grouped"] is False and c["single"] is False

    def test_the_counts_line_agrees_with_its_number(self):
        """C741: "1 waiting their turn" read wrong; one row waits its turn, several theirs."""
        from modules import run_stepper as RS
        one = RS.card(self._rows(["waiting", "done", "done"]), label="x")
        words = {t["group"]: t["words"] for t in one["tally"]}
        assert words["waiting"] == "waiting its turn"
        two = RS.card(self._rows(["waiting", "waiting", "done"]), label="x",
                      group_words={"done": "through their turn, waiting for the commit"})
        words = {t["group"]: t["words"] for t in two["tally"]}
        assert words["waiting"] == "waiting their turn"
        assert words["done"] == "through its turn, waiting for the commit"
        # The groups at scale keep the plural heading: a heading names the group, not a count.
        assert [g["words"] for g in two["groups"] if g["name"] == "waiting"] == [
            "waiting their turn"]

    def test_from_25_rows_it_groups_and_a_search_filters_rows_never_counts(self):
        from modules import run_stepper as RS
        c = RS.card(self._rows(["waiting"] * 24 + ["running"]), label="x", q="d24")
        assert c["grouped"] is True and c["counts"]["waiting"] == 24
        assert [r["name"] for r in c["rows"]] == ["d24"]
        assert {g["name"]: g["open"] for g in c["groups"]} == {"running": True,
                                                                "waiting": False}

    def test_a_finished_row_strikes_what_was_not_reached(self):
        from modules import run_stepper as RS
        steps = [RS.step("a", "A", "done"), RS.step("b", "B", "running"),
                 RS.step("c", "C", "waiting")]
        assert [s["state"] for s in RS.finished(steps, "failed")] == ["done", "failed",
                                                                      "not_reached"]
        assert [s["state"] for s in RS.finished(steps, "done")] == ["done"] * 3
        assert [s["state"] for s in RS.finished(steps, "partial")] == ["done", "done", "partial"]

    def test_a_partial_row_marks_the_step_that_did_not_pass(self):
        """C1541: a deploy whose verify did not pass draws its Verify step partial, never done
        beside it; a key the row lacks falls back to the last step."""
        from modules import run_stepper as RS
        steps = [RS.step("a", "A", "done"), RS.step("verify", "Verify", "done"),
                 RS.step("c", "C", "running")]
        assert [s["state"] for s in RS.finished(steps, "partial", partial_at="verify")] == \
            ["done", "partial", "done"]
        assert [s["state"] for s in RS.finished(steps, "partial", partial_at="nothing")] == \
            ["done", "done", "partial"]
        assert [s["state"] for s in RS.finished(steps, "done", partial_at="verify")] == \
            ["done"] * 3

    def test_a_wrong_state_or_group_is_refused_by_name(self):
        from modules import run_stepper as RS
        with pytest.raises(ValueError, match="not 'sent'"):
            RS.step("a", "A", "sent")
        with pytest.raises(ValueError, match="not 'through'"):
            RS.row("d", "through")


class TestTheClock:
    def test_the_running_step_counts_from_the_server_s_time(self):
        import dukpy
        js = _read("static/js/nmas_stepper.js")
        got = dukpy.evaljs("var window = {};\n" + js + "\n"
                           "[window.nmasStepper.secondsSince('2026-10-12T20:00:00Z', "
                           "Date.parse('2026-10-12T20:01:05Z')),"
                           " window.nmasStepper.secondsSince('not a time', 0)]")
        assert got == [65, None]
