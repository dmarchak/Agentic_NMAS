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
    "pending.html": "Onboarding and first boot",
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
#: Operation pages not yet converted (the 2026-10-12 program): EXACT, so a converted page
#: leaves it and nothing joins it.
NOT_YET = {
    "_update.html", "_capture.html", "pending.html", "_onboard_pending.html",
    "_netbox_job.html", "_sc_result.html", "_lp_result.html", "_persist.html", "_retire.html",
    "_template_op.html", "_dhcp_subnet.html", "_dhcp_reserve.html", "_dhcp_exclusion.html",
}
#: Operation pages where a stepper does not fit: template -> why (said in the fidelity record
#: and the approval log too).
DOES_NOT_FIT: dict = {}
#: Files that still draw progress some other way, until their page is converted: EXACT.
OTHER_PROGRESS = {
    "templates/v2/_update.html", "templates/v2/pending.html", "templates/v2/_sc_result.html",
    "templates/v2/_lp_result.html", "static/js/nmas_update.js",
}

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
    return ('from "v2/_run_stepper.html" import run_stepper' in text
            and re.search(r"\brun_stepper\(", text) is not None)


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
