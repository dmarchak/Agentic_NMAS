"""Stage 7.0 (3): if a payload carries it, the screen shows it.

**Today's (v1) pages only.** This measures today's JSON routes against today's JavaScript
renderers, and stays until those pages go: its lists (`UNDRAWN`, `PHANTOM`, the empty records)
shrink to nothing at P7-27, when the index and the Bootstrap pages are removed. v2 draws on the
server, and the same property is measured there by `test_v2_context_is_drawn.py` (P7-04,
2026-10-15): every key a v2 route's context carries is read by its template, or declared.

Four instances of one failure were recorded before this check existed, each
a key computed by the server, carried to the browser and drawn nowhere:
* D4: the deploy wizard dropped `commands`, `dangerous` and `attribution`;
* the pending banner dropped the list it had in hand;
* `/jobs/health` had no view at all;
* C27: the restore preview carried `commands` and never drew the lines to be
  added, while the confirm hash covered them.

Modelled on `test_server_reads_nothing_the_form_cannot_send.py`, the other
direction of the same seam. `tests/payload_render.py` says how keys and reads
are found and what the comparison cannot see; `tests/payload_providers.py`
makes the real responses.

* Each renderer is DECLARED here, with the functions that read its payload
  and the variable that holds it (a survey of the shipped source,
  2026-09-27).
* **Forward:** a payload key no declared function reads is a finding.
* **Reverse:** a depth-one read on the payload variable naming a key the
  payload does not carry is a finding: a panel drawing a field nothing sends.
* **Exemptions** are named, reasoned and capped at ten. **Findings not yet
  fixed** are a second list that only shrinks, compared exactly (no ghosts),
  its size pinned.
* **Anchors**, the recorded instances: `commands`, `dangerous` and
  `attribution` on `/deploy/plan`; the list on `/onboard/pending` (the key is
  `list`: the plan's "list_name" names the fact, not the key); and `commands`
  on `/golden/restore/preview` (C27). Each must be read, and removing a read
  fails this.
"""

import os
import shutil
import socket
from typing import NamedTuple

import pytest

from tests import payload_providers as P
from tests.payload_render import (lift, literal_keys, payload_keys, python_reads,
                                  reads, root_reads, shipped)


class Render(NamedTuple):
    #: fn(monkeypatch, tmp_path) -> the route's JSON, called through the app.
    provider: object
    #: {file: (function, ...)} whose source reads the payload or its parts.
    functions: dict
    #: ((file, function, variable), ...) that receive the WHOLE payload.
    roots: tuple
    #: Keys whose value is a dict keyed by DATA (a device, an outcome): its
    #: keys are values, read by iteration, never by name.
    maps: tuple = ()
    #: {file: (object literal, ...)} a renderer reads the payload THROUGH:
    #: the literal's keys are the keys read.
    tables: dict = None
    #: {python file: (function, ...)}: a server-side adapter that builds what
    #: the renderer draws from the payload's raw entries (7.1's
    #: preview-confirm). Its reads count as reads: it is the step that
    #: decides what reaches the screen.
    adapters: dict = None


def _answer(r):
    """A provider must get a real answer. A refusal (the identity gate's 403
    carries five keys, which a key-count check read as a payload) is a
    broken fixture, not a payload to check a renderer against."""
    assert 200 <= r.status_code < 300, (r.status_code, r.get_json(silent=True))
    return r.get_json()


def _get(path):
    return lambda mp, tmp: _answer(P._client().get(path))


def _post(path, body):
    return lambda mp, tmp: _answer(P._client().post(path, json=body))


PC = "nmas_preview_confirm.js"
PC_RESULT_FNS = ("previewConfirmResultHtml", "sentHtml", "checksHtml", "resultSection",
                 "pair", "previewConfirmResultLevel", "title")
PC_FNS = ("title", "previewConfirmHtml", "whatHtml", "whatNotHtml", "removableHtml",
          "programHtml", "operandsHtml",
          "gatesHtml", "confirmHtml", "explain", "previewConfirmButton")
CAP = "nmas_capture.js"
DW, GR1 = "partials__deploy_wizard.1.js", "partials__golden_repo.1.js"

RENDERS = {
    "GET /attention": Render(
        lambda mp, tmp: P.needs_attention(mp, tmp),
        {"nmas_attention.js": ("attentionPanelHtml", "loadAttention",
                               "rowHtml", "actionHtml", "unreadableNote",
                               "memberHtml", "operandValue", "sourcesTable",
                               "sourceRows", "ageOf", "ago", "ackedHtml")},
        (("nmas_attention.js", "attentionPanelHtml", "d"),),
        maps=("operands", "networks"),
        adapters={"modules/attention.py": ("needs_attention", "source_result", "row",
                                           "job_health_source", "_job_action",
                                           "drift_source", "approvals_source",
                                           "pending_onboarding_source", "_attach",
                                           "rollback_source", "deploy_source",
                                           "baseline_source", "authorisation_source",
                                           "grafana_source", "_member", "_onset",
                                           "_incidents",
                                           "integrations_source", "ci_source",
                                           "reachability_source", "_without_acknowledged")}),
    "GET /onboard/pending": Render(
        lambda mp, tmp: P.onboard_pending(mp, tmp),
        # 7.1: each Verify and Abandon result, read back from the run record,
        # drawn by the result component and built server-side.
        {"partials__onboard_pending.1.js": ("loadOnboardPending", "pendingBannerHtml"),
         PC: PC_RESULT_FNS},
        (("partials__onboard_pending.1.js", "pendingBannerHtml", "data"),),
        adapters={"modules/preview_confirm.py": ("onboard_run_result", "onboard_verify_result",
                                                 "onboard_abandon_result",
                                                 "_run_record_statement", "build_result")}),
    "POST /deploy/plan": Render(
        # With one removal SELECTED (Mode B, 7.3 step 2), so the plan carries
        # its removal fields; the base plan's residue is exactly that line, so
        # nothing is left out and `what_not` stays empty, as before.
        lambda mp, tmp: P.deploy_plan_with_removal(mp),
        {DW: ("openDeployPlan", "_renderDeployPlan", "_reauthoriseDevice",
              "_updateDeploySummary", "applyDeploy"), PC: PC_FNS},
        ((DW, "openDeployPlan", "d"), (DW, "_renderDeployPlan", "plan")),
        maps=("select_data",),
        adapters={"modules/preview_confirm.py": ("deploy_preview", "_deploy_gates",
                                                 "_removal_words", "expected_part")}),
    "POST /deploy/apply": Render(
        lambda mp, tmp: P.deploy_apply(mp),
        {DW: ("applyDeploy", "_renderDeployResult"), PC: PC_RESULT_FNS},
        ((DW, "_renderDeployResult", "report"),),
        maps=("by_outcome", "routing_protocols", "neighbours"),
        adapters={"modules/preview_confirm.py": ("operation_result", "build_result",
                                                 "result_level"),
                  "modules/nsot/receipts.py": ("rows_for", "_checks")}),
    # C188 step 2: the POST starts a job and answers at once; the preview is
    # the job's result, read by its id when the job announces it finished.
    "POST /golden/capture/preview": Render(
        lambda mp, tmp: P.capture_preview_start(mp, tmp),
        {CAP: ("previewCapture",)},
        ((CAP, "previewCapture", "d"),)),
    "GET /golden/capture/preview/<job>": Render(
        lambda mp, tmp: P.capture_preview(mp, tmp),
        {CAP: ("previewCapture", "captureWaitingWords", "captureSelection", "refreshButton"),
         PC: PC_FNS},
        ((CAP, "previewCapture", "jd"), (CAP, "captureWaitingWords", "jd")),
        maps=("select_data",),
        adapters={"modules/preview_confirm.py": ("capture_preview", "_intent_words", "build")}),
    "POST /golden/capture/apply": Render(
        lambda mp, tmp: P.capture_apply(mp, tmp),
        {CAP: ("previewCapture",), PC: PC_RESULT_FNS},
        ((CAP, "previewCapture", "ad"),),
        adapters={"modules/preview_confirm.py": ("capture_result", "_intent_words",
                                                 "build_result")}),
    # POST /templatize/seed/preview and /templatize/seed/apply left this table at 7.8
    # (2026-10-17, P7-24) with their renderer, nmas_seed.js. v2 draws the same preview and
    # result server-side: the device page's Seed intent… card (`device_actions.seed_card`,
    # `seed_result_card`; tests/test_v2_context_is_drawn.py, tests/test_device_seed_v2.py).
    # GET /deploy/receipts left this table at 7.8 (2026-10-17, P7-22) with today's device
    # page's Changes tab, its renderer; a device's receipts are its v2 History tab's rows.
    # Today's re-apply dialog's preview (POST /golden/restore/preview), the device page's
    # restore points (GET /golden/restore_points/<host>), the Remote card's GET /remote/status
    # and the Baselines panel's GET /golden/baselines left this table at 7.8 (2026-10-17,
    # P7-21) with their routes and renderers. v2 draws each server-side: the device page's
    # restore card from THE restore plan, History's header and Remote set-up… from the list's
    # record, History › Baselines from the `baseline-usability` reader
    # (tests/test_v2_context_is_drawn.py).
    # GET /identity/posture, GET /settings/integrations/status and GET
    # /settings/integrations/general left this table at 7.8 (2026-10-15) with their renderers,
    # today's Settings modal's posture panel, Integrations strip and general block, and the
    # status bar. The posture and the integrations' state are drawn on v2 by the server
    # (Settings › Installation › Access and identity; every page's strip); /identity/posture
    # and the general block's route left too.
    # GET /templates and GET /templates/approval/<path> left this table at 7.8 (2026-10-17,
    # P7-23) with today's template library, its renderer. v2 draws each server-side: Source of
    # truth › Templates' table from `approve_op.library`, and Approve…'s card from
    # `approve_op.check` (tests/test_templates_v2.py).
    "GET /golden/history/<host>": Render(
        _get("/golden/history/r1"),
        {GR1: ("showGoldenHistory",)},
        ((GR1, "showGoldenHistory", "d"),)),
    "POST /onboard/plan": Render(
        # With a mask, so the plan renders a config and the program part has
        # lines (without one the fixture reached only the render refusal).
        _post("/onboard/plan", {"list_name": "Default", "hostname": "bp-x",
                                "platform": "cisco_iosxe", "mgmt_ip": "203.0.113.6",
                                "mgmt_mask": "255.255.255.0",
                                "manager_interface": "GigabitEthernet2"}),
        # 7.1: the review is the shared preview, built server-side from the
        # plan's summary, so the adapter's reads count as drawn.
        {"partials__onboard_wizard.1.js": ("onboardRefresh", "onboardCanCreate"),
         PC: PC_FNS},
        (("partials__onboard_wizard.1.js", "onboardRefresh", "d"),),
        adapters={"modules/preview_confirm.py": ("onboard_preview", "build")}),
    "GET /inventory/source/<list>": Render(
        _get("/inventory/source/Default"),
        {"partials__inventory_source.1.js": ("loadInventorySource", "applyInventorySourceUI",
                                             "renderInventoryBanner")},
        (("partials__inventory_source.1.js", "loadInventorySource", "d"),)),
    "GET /onboard/platforms": Render(
        _get("/onboard/platforms"),
        {"partials__onboard_wizard.1.js": ("openOnboardWizard", "onboardPlatformOptions")},
        (("partials__onboard_wizard.1.js", "openOnboardWizard", "d"),)),
    # Today's NetBox tab's four payloads (the three previews on the component, 7.1, and the
    # stored partial import its sync card drew, C85) left with the tab at 7.8 (2026-10-17):
    # v2's NetBox page draws them server-side (tests/test_v2_context_is_drawn.py).
}

#: Keys carried and correctly not drawn, EVERYWHERE, in both directions. At
#: most ten: an exemption set that grows unnoticed is the check being
#: switched off one key at a time.
EXEMPT = {
    "invalidates": "read from the X-NMAS-Invalidates HEADER by the registry "
                   "(static/js/nmas_invalidation.js); the body copy is for "
                   "a caller without it",
    "error": "read on every renderer's failure branch; the providers return "
             "successes by design, so a success payload never carries it",
}

OK = ("the renderer never reads `ok`, so a failed answer is drawn as data: "
      "the empty-list-that-means-failure shape. 7.x's rebuild of this panel")
LIST = ("the echo of the list the route answered for; the panel does not say "
        "which network it describes. 7.2's status bar names the network")

#: {route: [(keys, reason)]}: carried and not drawn, not yet fixed. Only
#: shrinks: a key that becomes drawn must leave (no ghosts).
UNDRAWN = {
    "GET /attention": [
        ("networks",
         "each named device's network (C493, 2026-10-16): drawn by the v2 page "
         "(templates/v2/_attention.html, the row's meta line and its Open links, from "
         "needs_attention() directly); today's v1 panel gains no capability (the v1 rule)"),
        ("in_force",
         "the band acknowledgements in force that hide nothing now (C460, 2026-10-05): drawn "
         "by the v2 page (templates/v2/_attention.html, #att-in-force, from needs_attention() "
         "directly); today's v1 panel gains no capability (the v1 rule), so it does not"),
        ("ways",
         "the machine form of clears.when, which both pages draw (the redesign's Needs "
         "attention also offers Acknowledge, from acknowledge and event, which the adapter "
         "reads to hide an acknowledged row)")],
    "GET /golden/history/<host>": [
        ("hostname", "the request's own echo; the dialog is titled from the "
                     "caller's argument"),
        ("list", LIST)],
    # GET /golden/baselines' eight (credential_detail and its forms, credential_guarded,
    # credential_refused, subject, list) left with the route at 7.8 (2026-10-17).
    "GET /inventory/source/<list>": [
        ("config credential_list device_order filters refresh_interval role "
         "schema_version site tag",
         "the source's configuration; the panel draws its status only, and "
         "7.4 (Fleet, Networks) draws and sets the rest (reachability group a)")],
    "POST /golden/capture/preview": [
        ("list", LIST)],
    "GET /golden/capture/preview/<job>": [("list", LIST)],
    "POST /golden/capture/apply": [("list", LIST)],
    "GET /onboard/pending": [
        ("counts total overdue stale thresholds",
         "the banner derives its counts from the rows; the server's counts "
         "and thresholds are unread duplicates, drawn or dropped in 7.4"),
        ("onboarded_at", "the banner draws the age (age_seconds), not the time")],
    # (`stage`, a ztp row's stage word, left this list in 7.1 by being DRAWN
    # beside its summary. This check matches key NAMES, and the result
    # builder reads its own `stage`, so it would have passed as "read"
    # without the banner drawing it.)
    "GET /onboard/platforms": [
        ("dialect", "the config dialect beside the slug; the wizard offers slugs"),
        ("ok", OK)],
    # GET /templates' four and GET /templates/approval/<path>'s two left with the routes and
    # today's template library (7.8, 2026-10-17, P7-23).
    "POST /deploy/apply": [
        ("capture_confirmed capture_current current_hash moved",
         "a refusal's operands: its `reason` sentence names them and which "
         "side moved, and that IS drawn (test_deploy_plan_apply_seam)"),
        ("by_outcome workers deployed total",
         "counts and groupings of the rows; the result's summary sentence counts "
         "the receipt rows it draws one by one (7.1 step 2)"),
        ("routing_neighbors routing_protocol",
         "verify's single-protocol summary, superseded by `routing_protocols`, "
         "which the result draws per protocol, before and after"),
        ("golden_commit", "each device's copy of the batch commit, which the "
                          "result's record part draws once"),
        ("receipts", "the receipt write status, drawn as the record part's "
                     "receipt line (`record.receipt`)"),
        ("list", LIST)],
    "POST /deploy/plan": [
        ("complete", "the conjunction of two gates drawn by name (template "
                     "reproduces the device; every line modelled or acknowledged)"),
        ("deployable_count", "the summary sentence recomputes it from the "
                             "devices the preview draws"),
        ("derived expected unexpected",
         "C506 phase 2, the plan's Expected effects: drawn by the v2 deploy card "
         "(templates/v2/_deploy.html, #expected, from preview_confirm.expected_part) and reached "
         "in tests/test_expected_effects_plan.py; today's v1 deploy page gains no capability "
         "(the v1 rule), so it does not"),
        ("declared ends moves offers to",
         "C506 phase 3, what a person may declare and has declared: drawn by the v2 deploy card "
         "(templates/v2/_deploy.html, #expected, from device_actions._declare_part) and reached "
         "in tests/test_declared_effects.py; the v1 deploy page gains no capability"),
        ("check expects read",
         "C506 phase 4, What verify checks: drawn by the v2 deploy card (templates/v2/_deploy.html, "
         "#expected, its table, from preview_confirm.expected_part) and reached in "
         "tests/test_verify_checks.py; the v1 deploy page gains no capability")],
    "POST /onboard/plan": [
        ("host_vars", "the intent phase 1 will commit; the review draws the "
                      "bootstrap config, and 7.4 draws the intent too"),
        ("mgmt_mac reservation_address reservation_state ztp_server ztp_subnet_id",
         "structured forms of the address claim, which is drawn in words"),
        ("writes_csv", "a phase-1 fact the review states in prose")],
}

#: {route: [(keys, reason)]}: a renderer reads a key its fixture's payload
#: does not carry. Each is a branch the fixture cannot reach; a provider
#: that reaches it lets the entry leave.
PHANTOM = {
    # GET /remote/status's eleven (the configured remote's fields the Remote card read) left
    # with the route and the card at 7.8 (2026-10-17). GET /templates/approval/<path>'s three
    # (actor, approved_at, evidence) left with the route and today's template library (7.8,
    # 2026-10-17, P7-23).
}


S_ = "strings"
R_ = "records"
_STRINGS = "items are strings: an empty list hides no field"
_DEPLOY_CHECKS = ("verify's lists of sentences; the fixture's refused row carries none and its "
                  "deployed row holds each empty. All five drawn with content, through the "
                  "receipt and the shipped renderer, in test_deploy_receipts.py "
                  "(TestEveryCheckListIsDrawnWithContent)")

#: EVERY collection a provider's payload holds EMPTY, declared (the operator's
#: rule, 2026-09-27: A CHECK IS ONLY AS GOOD AS THE STATE ITS FIXTURE CAN
#: REACH). An empty list of RECORDS hides every field its items carry from
#: BOTH directions: the forward check sees only the keys present, and the
#: reverse check reads depth one. That is how a deployed row's seven fields
#: went unexamined until the /deploy/apply provider could produce one.
#: "strings" hides nothing. "records" is a state the fixture does not reach,
#: a finding, and that list only shrinks. Measured 2026-09-27.
EMPTY_IN_FIXTURE = {
    "GET /attention acknowledged": (R_, "no row is acknowledged in the fixture; "
                                       "tests/test_acknowledge.py acknowledges one through the real "
                                       "route and reads both pages"),
    "POST /deploy/plan preview.targets[].program.notes[].from_profile": (
        S_, "this provider's lab commits no monitoring profile (P.9); the lines are "
            "reached through the real /deploy/plan and drawn by the shipped renderer in "
            "tests/test_monitoring_profile_plan.py"),
    "GET /golden/history/<host> history": (R_, "no golden commit for the device in "
                                               "the fixture; 7.3's History draws it"),
    "GET /inventory/source/<list> config.device_order": (S_, _STRINGS),
    "GET /inventory/source/<list> stale_devices": (R_, "a local list has no stale "
                                                       "NetBox devices; a map of records"),
    "POST /deploy/plan devices[].blocking_reasons": (S_, _STRINGS),
    "POST /deploy/plan devices[].expected_effects.up": (S_, _STRINGS),
    "POST /deploy/plan devices[].expected_effects.adjacencies_drop": (
        R_, "the fixture's program shuts no interface (C506 phase 2); an adjacency over a shut "
            "interface and a BGP session sourced from one are reached in "
            "tests/test_expected_effects_plan.py and drawn by the v2 deploy card"),
    "POST /deploy/plan devices[].expected_effects.may_form": (
        R_, "the fixture's program brings no interface up (C506 phase 2); reached in "
            "tests/test_expected_effects_plan.py"),
    # C506 phase 3: nothing is declared in the fixtures' plans and runs, and their programs
    # drop and bring up nothing; each declaration, offer and outcome is reached in
    # tests/test_declared_effects.py.
    "POST /deploy/plan devices[].declared": (R_, "nothing is declared in the fixture's plan"),
    "POST /deploy/plan devices[].expected_effects.declared": (
        R_, "nothing is declared in the fixture's plan"),
    "POST /deploy/plan devices[].expected_effects.offers.moves": (
        R_, "the fixture's program drops no adjacency, so none can be declared to move"),
    "POST /deploy/plan devices[].expected_effects.offers.ends": (
        R_, "the fixture's committed intent gives the device no adjacency with an identity"),
    "POST /deploy/plan devices[].expected_effects.offers.to": (S_, _STRINGS),
    "POST /deploy/apply result.targets[].checks.declared_moves": (
        R_, "no move is declared in the fixture's run"),
    "POST /deploy/apply result.targets[].checks.notes": (S_, _STRINGS),
    # C506 phase 4: the fixtures' runs record no verify by name; reached in
    # tests/test_verify_checks.py.
    "POST /deploy/apply result.targets[].checks.expected_effects": (
        R_, "the fixture's verify records no expected effects"),
    "POST /deploy/apply result.targets[].checks.interfaces": (
        R_, "the fixture's verify compared no interface by name"),
    "POST /deploy/plan devices[].excluded_unrenderable": (S_, _STRINGS),
    "POST /deploy/plan devices[].masked_refs": (S_, _STRINGS),
    "POST /deploy/plan devices[].shares_key[].chain": (S_, _STRINGS),
    "POST /deploy/plan devices[].stale_acknowledgements": (S_, _STRINGS),
    "POST /deploy/plan devices[].unacknowledged": (S_, _STRINGS),
    "POST /deploy/plan devices[].unmodeled": (S_, _STRINGS),
    "POST /deploy/plan devices[].unsendable": (S_, _STRINGS),
    "POST /deploy/plan devices[].removals.refused": (R_, "the base plan's one selection is a "
                                                      "measured shape and is removed; a "
                                                      "REFUSED selection is reached in "
                                                      "test_removal_pipeline.py"),
    "POST /deploy/plan devices[].removals.secret_position": (R_, "the base plan removes a "
                                                              "description; a secret-position "
                                                              "removal is reached in "
                                                              "test_removal_pipeline.py"),
    "POST /golden/capture/apply result.did_not.items[].lines": (S_, "the first did-not item is r2's departure from intent, whose lines are drawn under its checks; the baseline item carries no lines"),
    "POST /deploy/apply result.did_not.items[].lines": (S_, "the fixture's FIRST target is the refusal (s3), and a refused device sent nothing, so its program, rollback and not-undone lines are empty by definition; the deployed s4 carries sent lines (test_deploy_receipts asserts them on screen)"),
    "POST /deploy/apply result.targets[].rollback.commands": (S_, "the fixture's FIRST target is the refusal (s3), and a refused device sent nothing, so its program, rollback and not-undone lines are empty by definition; the deployed s4 carries sent lines (test_deploy_receipts asserts them on screen)"),
    "POST /deploy/apply result.targets[].rollback.remaining": (S_, "no rollback in the fixture; an incomplete rollback's remaining lines are drawn in test_pipeline (TestARollbackSaysWhatItAchieved)"),
    "POST /deploy/apply result.targets[].rollback.not_undone": (S_, "the fixture's FIRST target is the refusal (s3), and a refused device sent nothing, so its program, rollback and not-undone lines are empty by definition; the deployed s4 carries sent lines (test_deploy_receipts asserts them on screen)"),
    "POST /onboard/plan host_vars": (R_, "the plan carries no intent for a device "
                                         "not yet onboarded; drawn in 7.4"),
    "GET /onboard/pending runs.finished[].result.did_not.items": (R_, "the finished runs "
        "in the fixture both succeeded; a failed run's items are drawn under r7's last run"),
    "GET /onboard/pending runs.finished[].result.record.tags": (S_, "an onboarding run "
        "makes no tag"),
    "POST /onboard/plan preview.explain": (R_, "no concept is taught on the onboarding "
                                               "review yet; the concepts harness names it"),
    "POST /onboard/plan preview.targets[].program.authorised": (S_, "a startup config is "
                                               "sent to no device, so nothing is authorised"),
    "POST /onboard/plan preview.targets[].program.dangerous": (S_, "a startup config is "
                                               "sent to no device, so no line is dangerous"),
    "POST /onboard/plan preview.targets[].program.notes": (S_, "the caption says what the "
                                               "config is; there are no per-line notes"),
    "POST /onboard/plan preview.what.targets[].select_data": (R_, "Create rebuilds the plan "
                                               "and refuses a changed one, so nothing is "
                                               "carried to confirm by hash (its gate says so)"),
    "POST /onboard/plan preview.what_not.items[].lines": (S_, "onboarding's what-not items "
                                               "are sentences, never config lines"),
    # C140 / C79 (2026-09-28): the authorisation's reason and its aggregate.
    "POST /deploy/plan devices[].prior_authorised.lines": (R_, "no receipt precedes the "
        "plan in the fixture; each {count, last_at, last_actor, last_reason} is reached "
        "through real receipts in test_authorised_lines.py"),
    "POST /deploy/plan preview.targets[].program.prior.lines": (R_, "as above: the "
        "preview's copy of the aggregate, reached in test_authorised_lines.py"),
    "POST /deploy/plan preview.targets[].program.secret": (S_, "a deploy never flags a "
        "secret line: an account added from intent is additive (C75); only a restore "
        "does (C79), and the restore provider reaches it"),
    # C315 (2026-10-02): eighteen more the first-item-then-intersection walker
    # hid, each empty in one row and ABSENT from another, never held.
    **{f"{route} {base}.{k}": (S_, _DEPLOY_CHECKS)
       for route, base in (("POST /deploy/apply", "result.targets[].checks"),)
       for k in ("from_intent", "intent_unmet", "issues", "pending_convergence",
                 "unreadable")},
    "POST /deploy/apply results[].pending_convergence": (S_, _DEPLOY_CHECKS),
    "POST /deploy/apply results[].verify.issues": (S_, _DEPLOY_CHECKS),
    "GET /onboard/pending pending[].last_run.result.record.tags": (S_, "an onboarding run "
        "makes no tag"),
}
# 14 -> 13: `GET /netbox/status status` is reached (a stored import, C85).
# 13 -> 15: the onboarding review on the component (7.1) has no concept to
# teach yet and nothing to confirm by hash (Create rebuilds the plan and its
# gate says so); both are records by the component's shape, not the fixture's.
# 15 -> 21: the three NetBox previews entered this check for the first time
# (7.1); each has no concept yet and no per-target confirm data (the one-shot
# token binds the plan's hash beside the preview). New coverage, not a
# fixture that stopped reaching a state.
# 21 -> 22: the pending read's finished runs are all successes in its fixture
# (a failed run's items are drawn under a pending row's last run instead).
# 22 -> 27: C140's aggregate (four: the prior-authorisation map on the deploy
# plan and the restore preview, each twice) needs a receipt BEFORE the plan,
# which no provider writes; reached through real receipts in
# test_authorised_lines.py. And the apply's refused row authorises nothing.
# 25 -> 23: the golden panel's own fixture reaches baselines and legacy-only
# files (2026-09-28), which found four baseline fields nobody had examined.
# 23 -> 25: Mode B (7.3 step 2): a removal the plan REFUSES and one in a
# secret position; the base plan removes one measured description, and
# both are reached in test_removal_pipeline.py.
# 25 -> 24: 2c's tick boxes put a residue item in the base plan, so
# `preview.what_not.items` is reached rather than declared empty.
# 24 -> 25: C315's corrected walker (empty in SOME row and held in none, not
# the intersection) found the restore plan's per-device copy of C140's
# aggregate, the same state the deploy plan's entry already declares. New
# coverage: the walker had hidden it, the fixture did not stop reaching it.
# 26 -> 28: C506 phase 2 (2026-10-06): the plan's derived adjacency drops and the adjacencies
# that may form, empty because the fixture's program shuts and brings up nothing; both reached
# in tests/test_expected_effects_plan.py.
# 28 -> 34: C506 phase 3 (2026-10-06): the plan's declarations and offers (moves, ends) and the
# run's declared moves, empty because the fixtures declare nothing; reached in
# tests/test_declared_effects.py.
# 34 -> 38: C506 phase 4 (2026-10-06): the receipt's expected effects and interfaces, empty
# because the fixtures' runs compare no interface by name; reached in tests/test_verify_checks.py.
# 38 -> 37: 7.8 (2026-10-12): /golden/renames left, and its `pending` with it.
# 37 -> 35: 7.8 (2026-10-12): /golden/migrate/plan left, and its `devices` and `merges` with it.
# 35 -> 33: the AI family (D15, 2026-10-14): /ai/agent_log's entries and /ai/approvals' entries.
# 33 -> 32: 7.8 (2026-10-15): /identity/posture left with today's Settings modal, and its
# `settings_read_failure` with it.
# 32 -> 31: P7-03 (2026-10-15): the NetBox removal preview's `explain` carries
# provenance-limits-remove, drawn by v2's preview parts (tests/test_concepts_are_taught.py).
# 31 -> 26: 7.8 (2026-10-17): today's NetBox tab's three previews left with their routes, and
# their five records (the two imports' `explain` and per-target `select_data`, the removal's
# `select_data`).
# 26 -> 23: 7.8 (2026-10-17, P7-22): GET /deploy/receipts left with today's device page, and
# its three records (a receipt's checks' `declared_moves`, `expected_effects`, `interfaces`).
# 23 -> 21: 7.8 (2026-10-17, P7-21): POST /golden/restore/preview left with today's re-apply
# dialog, and its two records (the per-device and the preview's copy of C140's aggregate).
# 21 -> 20: 7.8 (2026-10-17, P7-23): GET /templates left with today's template library, and its
# one record (the bindings' `overrides`).
EMPTY_RECORDS_CEILING = 20


def _empty_paths(obj, path=""):
    """Every empty list or object in a payload, as a dotted path, a list's
    items written `name[]`. A path under a list is empty only if it is empty
    in EVERY item: the walker read the first item alone, so a field the
    fixture reached in the second row (Needs attention's folded `attached`,
    once a danger row sorted ahead of it) read as never reached. The first
    item stood in for all of them: the proxy shape, inside the check."""
    out = []
    if isinstance(obj, dict):
        if not obj and path:
            out.append(path)
        for k, v in obj.items():
            out += _empty_paths(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        if not obj:
            out.append(path)
        # Empty in SOME item and holding something in NONE (C315, 2026-10-02).
        # The intersection over every item read a key ABSENT from one item as
        # reached: a refused device's checks carry no `issues`, so the
        # deployed row's empty `issues` disappeared, and 21 empty collections
        # were hidden that way. An item that does not carry a path says
        # nothing about it.
        empty = set().union(*[set(_empty_paths(v, path + "[]")) for v in obj]) if obj else set()
        held = set().union(*[_held_paths(v, path + "[]") for v in obj]) if obj else set()
        out += sorted(empty - held)
    return out


def _held_paths(obj, path=""):
    """Every path in *obj* that holds something: a scalar, or a non-empty
    collection."""
    out = set()
    if isinstance(obj, dict):
        if obj and path:
            out.add(path)
        for k, v in obj.items():
            out |= _held_paths(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        if obj:
            out.add(path)
        for v in obj:
            out |= _held_paths(v, path + "[]")
    else:
        out.add(path)
    return out


def _flat(table):
    return {f"{route} {key}": reason for route, groups in table.items()
            for keys, reason in groups for key in keys.split()}


# 99 -> 106 on 2026-09-27, and NOT a loosening: the /deploy/apply provider
# could not exhibit a deployed row (it planned without the authorisation it
# applied with, so every row was a refusal). Fixed, the check saw seven keys a
# deployed row always carried and nothing had examined. A ceiling rises only
# for that reason, stated here. 106 -> 105: the restore preview moved onto
# the component (7.1), and its adapter now reads three keys it carried
# undrawn. 105 -> 102: the deploy result moved onto the component's result
# half (7.1 step 2), which draws eight keys the old renderer did not and
# carries four of the old renderer's in another form (each declared);
# a protocol name is a map key under `neighbours`, not an exemption.
# 101 -> 104, the permitted reason: `GET /netbox/status` could not reach a
# stored import (C85's fixture), and reaching one showed three keys with
# reasons, beside `notes` and `region`, which are now drawn.
# 104 -> 107: capture (7.1 step 4) is two new payloads; each carries only the
# confirming person (drawn in the confirm sentence) and the list, the same
# exemptions every other preview has. Its raw reads were removed, not exempted.
# 107 -> 108: the onboarding review moved onto the component (7.1): it carries
# the confirming person, the same exemption; its own `bootstrap_config` key
# was removed (the config is the program part), not exempted.
# 108 -> 104: the confirm part's `actor` echo removed from every preview (the
# apply records the verified actor; the statement names the person), found
# when the NetBox previews would have added three more copies of the exemption.
# 104 -> 103: a ztp row's `stage` is drawn in the pending banner (7.1).
# 103 -> 102: each integration's `name` is drawn by the status bar (7.2).
UNDRAWN_CEILING = 58  # -6: today's template library (7.8, 2026-10-17, P7-23), /templates' bindings, overrides, platforms and size and /templates/approval's path and ok, with the routes. Before: -6: today's device page (7.8, 2026-10-17, P7-22), /deploy/receipts's expected_effects, failed_at_once, interfaces, unexpected_settle, declared_moves and notes, with the route. Before: -20: today's Git tab, Remote card and Baselines (7.8, P7-21, 2026-10-17), with their routes: /golden/baselines' eight, /remote/status's list, and /golden/restore/preview's eleven. Before: -4: today's NetBox tab (7.8, 2026-10-17), /netbox/status's filename, config_template_id, last_sync and list, with the route. Before: +1: C493, the attention rows' networks, drawn by the v2 page only (the v1 panel gains nothing) (2026-10-16). Before: -4: today's posture panel (7.8, 2026-10-15), /identity/posture's action, actor_kind, certs_url and config_revealed, with the route. Before: -6: today's drift panel (7.8, 2026-10-15), /drift/status's interval_h, last_ts, next_ts, next_from, state and list. Before: -11: the AI family (D15, 2026-10-14), the agent log's and the agent timers' undrawn fields. Before: -1: 7.8 (2026-10-13), the TFTP setting's tftp_server_ip, no longer carried by the integrations payload. Before: -3: 7.8 (2026-10-12), the topology service panel's status fields. Before: -1: the monitoring stack card's `name`. Before: -8: 7.8 (2026-10-12), the legacy store's and the migration's routes left with their undrawn fields. Before: +4: C506 phase 4, the receipt's expected_effects, failed_at_once, interfaces, unexpected_settle, drawn in words by the v2 result card. +3: C506 phase 4, What verify checks (check, expects, read) drawn by the v2 deploy card only (2026-10-06). Before: +7: C506 phase 3, the plan's declarations and offers (declared, ends, moves, offers, to) drawn by the v2 deploy card only, and the receipt's declared_moves and notes drawn by the v2 result card (History's receipt display is phase 4) (2026-10-06). Before: +3: C506 phase 2, the plan's Expected effects (derived, expected, unexpected), drawn by the v2 deploy card only (the v1 page gains nothing) (2026-10-06). Before: +1: C460, in_force, drawn by the v2 page only (the v1 panel gains nothing) (2026-10-05). Before: -1: R12's client half reads the approval state's fingerprint (2026-10-04). Before: +1: clears.ways (2026-10-02), the machine form of clears.when, which both pages draw. Before: +3: C315, the Baselines provider reaches a stale credential, and credential_detail's form at the ref and at HEAD was never drawn (new coverage, not a regression). Before: -1: C310, the deploy result reads its golden's `refused` (a device whose golden was not recorded). Before: -1: P.9 (b)'s deploy wizard reads the plan's `list` (the scope carries it)
PHANTOM_CEILING = 0  # 2026-10-17 (P7-23): /templates/approval's actor, approved_at and evidence left with the route and today's template library (7.8). Before: 2026-10-17: /remote/status's eleven left with the route and today's Remote card (7.8, P7-21). Before: 2026-10-15: /identity/posture's config_withheld_reason left with the route (7.8). Before: 2026-10-12: the monitoring stack card's detail, link and metrics left with it (7.8)


@pytest.fixture(scope="module")
def measured(tmp_path_factory):
    """{route: (payload, read names, {root var: root reads})}, every payload a
    real response. The store is copied and restored, as C33's sweep does:
    several of these GETs write (C33's KNOWN_WRITERS)."""
    from modules import config

    mp = pytest.MonkeyPatch()
    store = config.DATA_DIR
    original = os.path.join(os.path.dirname(store), os.path.basename(store) + ".p7")
    shutil.copytree(store, original)
    mp.setattr(socket.socket, "connect",
               lambda *a, **k: (_ for _ in ()).throw(OSError("tests do not touch a network")))
    # The conftest's verified person is FUNCTION-scoped, and this fixture is
    # module-scoped, so without this every gated POST was refused and its
    # refusal measured as the payload. Built here, not imported: importing
    # tests.conftest re-executes it and re-points the store.
    from modules import identity

    person = identity.Identity(actor="test-person@example.invalid",
                               email="test-person@example.invalid", kind="person",
                               verified=True, outcome="ok", peer="198.51.100.7",
                               peer_trusted=True, header_present=True)
    mp.setattr(identity, "identify", lambda _request: person)
    out = {}
    try:
        P._client().get("/v2/")
        for route, spec in RENDERS.items():
            with pytest.MonkeyPatch.context() as local:
                payload = spec.provider(local, tmp_path_factory.mktemp("p"))
            names = set()
            for file, functions in spec.functions.items():
                src = shipped(file)
                for fn in functions:
                    names |= reads(lift(src, fn))
            for path, functions in (spec.adapters or {}).items():
                for fn in functions:
                    names |= python_reads(path, fn)
            for file, tables in (spec.tables or {}).items():
                for table in tables:
                    names |= literal_keys(shipped(file), table)
            roots = {}
            for file, fn, var in spec.roots:
                roots.setdefault(var, set()).update(root_reads(lift(shipped(file), fn), var))
            out[route] = (payload, names, roots)
    finally:
        mp.undo()
        shutil.rmtree(store, ignore_errors=True)
        shutil.copytree(original, store)
        shutil.rmtree(original, ignore_errors=True)
    return out


def _keys(route, payload):
    maps = RENDERS[route].maps

    def walk(obj, into):
        if isinstance(obj, dict):
            for k, v in obj.items():
                into.add(k)
                if k in maps and isinstance(v, dict):
                    for inner in v.values():
                        walk(inner, into)
                else:
                    walk(v, into)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, into)
        return into

    return walk(payload, set())


def _forward(measured):
    found = {}
    for route, (payload, names, _) in measured.items():
        for key in sorted(_keys(route, payload) - names - set(EXEMPT)):
            found[f"{route} {key}"] = True
    return found


def _reverse(measured):
    found = {}
    for route, (payload, _, roots) in measured.items():
        top = set(payload) if isinstance(payload, dict) else set()
        for var, names in roots.items():
            for key in sorted(names - top - set(EXEMPT)):
                found[f"{route} {key}"] = var
    return found


class TestThePopulation:
    def test_floors(self, measured):
        # 16 since 2026-10-17: today's four Git tab, Remote card and Baselines payloads left
        # (7.8, P7-21); the table shrinks with today's pages (v2's contexts are
        # tests/test_v2_context_is_drawn.py's).
        # 15 since GET /deploy/receipts left the same day with today's device page (P7-22).
        # 13 since today's template library's two payloads left the same day (P7-23).
        # 11 since today's seed preview and result left the same day (P7-24).
        assert len(RENDERS) >= 11
        total = sum(len(_keys(r, p)) for r, (p, _, _) in measured.items())
        assert total >= 150, total

    def test_every_payload_is_a_real_answer(self, measured):
        """An error payload has `ok` and `error` and nothing to render; a
        renderer checked against one checks nothing."""
        thin = [r for r, (p, _, _) in measured.items()
                if not isinstance(p, dict) or "error" in p and len(p) <= 3]
        assert thin == [], thin

    def test_every_declared_function_exists(self):
        for route, spec in RENDERS.items():
            for file, functions in spec.functions.items():
                src = shipped(file)
                for fn in functions:
                    lift(src, fn)
            for path, functions in (spec.adapters or {}).items():
                for fn in functions:
                    python_reads(path, fn)


class TestAnchors:
    """The four recorded instances. Each key is carried AND read."""

    @pytest.mark.parametrize("route,key", [
        ("POST /deploy/plan", "commands"), ("POST /deploy/plan", "dangerous"),
        ("POST /deploy/plan", "attribution"), ("GET /onboard/pending", "list"),
        # 7.1: the program reaches the screen THROUGH the preview; the adapter
        # reads `commands` and the renderer draws `lines` and the split.
        ("POST /deploy/plan", "preview"), ("POST /deploy/plan", "lines"),
        # The restore preview's `commands` (C27) left with POST /golden/restore/preview at 7.8
        # (2026-10-17): the v2 restore card draws the program server-side.
        ("POST /deploy/plan", "from_this_edit")])
    def test_carried_and_read(self, measured, route, key):
        payload, names, _ = measured[route]
        assert key in _keys(route, payload), f"the fixture cannot carry {key}"
        assert key in names, f"{route} carries {key!r} and no renderer reads it"


class TestBothDirections:
    def test_forward_every_carried_key_is_read(self, measured):
        new = sorted(set(_forward(measured)) - set(_flat(UNDRAWN)))
        assert new == [], (
            "carried to the browser and read by no declared renderer: "
            f"{new}. Draw it, or record it in UNDRAWN with the reason.")

    def test_forward_no_ghosts(self, measured):
        ghosts = sorted(set(_flat(UNDRAWN)) - set(_forward(measured)))
        assert ghosts == [], f"read now, or no longer carried: remove from UNDRAWN: {ghosts}"

    def test_forward_list_only_shrinks(self):
        assert len(_flat(UNDRAWN)) == UNDRAWN_CEILING

    def test_reverse_every_read_is_carried(self, measured):
        new = sorted(set(_reverse(measured)) - set(_flat(PHANTOM)))
        assert new == [], f"a renderer reads a key its payload does not carry: {new}"

    def test_reverse_no_ghosts(self, measured):
        ghosts = sorted(set(_flat(PHANTOM)) - set(_reverse(measured)))
        assert ghosts == [], ghosts

    def test_reverse_list_only_shrinks(self):
        assert len(_flat(PHANTOM)) == PHANTOM_CEILING

    def test_exemptions_are_reasoned_and_capped(self):
        assert len(EXEMPT) <= 10
        for key, reason in (list(EXEMPT.items()) + list(_flat(UNDRAWN).items())
                            + list(_flat(PHANTOM).items())):
            assert len(reason) >= 30, key


class TestTheFixturesReachTheState:
    """A check is only as good as the state its fixture can reach (the
    operator's rule, 2026-09-27)."""

    def _found(self, measured):
        return {f"{route} {p}" for route, (payload, _n, _r) in measured.items()
                for p in _empty_paths(payload)}

    def test_every_empty_collection_is_declared(self, measured):
        new = sorted(self._found(measured) - set(EMPTY_IN_FIXTURE))
        assert new == [], (f"empty in its fixture and undeclared: {new}. Reach the "
                           "state, or declare it as strings or records, with the reason.")

    def test_no_ghosts(self, measured):
        ghosts = sorted(set(EMPTY_IN_FIXTURE) - self._found(measured))
        assert ghosts == [], f"not empty now: remove from EMPTY_IN_FIXTURE: {ghosts}"

    def test_the_records_list_only_shrinks(self):
        records = [k for k, (kind, _r) in EMPTY_IN_FIXTURE.items() if kind == R_]
        assert len(records) == EMPTY_RECORDS_CEILING, len(records)
        assert all(len(r) >= 20 for _k, (_kind, r) in EMPTY_IN_FIXTURE.items())

    def test_the_scan_finds_something(self, measured):
        """The floor: a walker that saw nothing would satisfy both directions."""
        assert len(self._found(measured)) >= 20
