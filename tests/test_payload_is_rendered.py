"""Stage 7.0 (3): if a payload carries it, the screen shows it.

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


NBS = "partials__netbox_safety_modal.1.js"
PC = "nmas_preview_confirm.js"
PC_RESULT_FNS = ("previewConfirmResultHtml", "sentHtml", "checksHtml", "resultSection",
                 "pair", "previewConfirmResultLevel", "title")
PC_FNS = ("title", "previewConfirmHtml", "whatHtml", "whatNotHtml", "removableHtml",
          "programHtml", "operandsHtml",
          "gatesHtml", "confirmHtml", "explain", "previewConfirmButton")
DC = "partials__device_changes.1.js"
CAP = "nmas_capture.js"
SEED = "nmas_seed.js"
RS = "nmas_restore_scope.js"
DW, GR1, GR2, GR3 = ("partials__deploy_wizard.1.js", "partials__golden_repo.1.js",
                     "partials__golden_repo.2.js", "partials__golden_repo.3.js")
I1, I4 = "index.1.js", "index.4.js"

RENDERS = {
    "GET /attention": Render(
        lambda mp, tmp: P.needs_attention(mp, tmp),
        {"nmas_attention.js": ("attentionPanelHtml", "loadAttention",
                               "rowHtml", "actionHtml", "unreadableNote",
                               "memberHtml", "operandValue", "sourcesTable",
                               "sourceRows", "ageOf", "ago", "ackedHtml")},
        (("nmas_attention.js", "attentionPanelHtml", "d"),),
        maps=("operands",),
        adapters={"modules/attention.py": ("needs_attention", "source_result", "row",
                                           "job_health_source", "_job_action",
                                           "drift_source", "approvals_source",
                                           "pending_onboarding_source", "_attach",
                                           "rollback_source", "deploy_source",
                                           "baseline_source", "authorisation_source",
                                           "grafana_source", "_member", "_onset",
                                           "_incidents", "freshness_source",
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
    "POST /templatize/seed/preview": Render(
        lambda mp, tmp: P.seed_preview(mp, tmp),
        {SEED: ("previewSeed", "seedSelection", "refreshButton"), PC: PC_FNS},
        ((SEED, "previewSeed", "d"),), maps=("select_data",),
        adapters={"modules/preview_confirm.py": ("seed_preview", "_fidelity_words", "build")}),
    "POST /templatize/seed/apply": Render(
        lambda mp, tmp: P.seed_apply(mp, tmp),
        {SEED: ("previewSeed",), PC: PC_RESULT_FNS},
        ((SEED, "previewSeed", "ad"),),
        adapters={"modules/preview_confirm.py": ("seed_result", "_fidelity_words",
                                                 "build_result")}),
    "GET /golden/restore_points/<host>": Render(
        lambda mp, tmp: P.restore_points(mp, tmp),
        {RS: ("openRestoreFrom", "restorePointsHtml", "credBadge")},
        ((RS, "restorePointsHtml", "d"),)),
    "GET /deploy/receipts": Render(
        lambda mp, tmp: P.deploy_receipts(mp),
        {DC: ("deviceChangesHtml", "loadDeviceChanges"), PC: PC_RESULT_FNS},
        ((DC, "deviceChangesHtml", "d"),), maps=("neighbours",),
        adapters={"modules/preview_confirm.py": ("receipt_history", "operation_result",
                                                 "build_result", "result_level")}),
    "POST /golden/restore/preview": Render(
        lambda mp, tmp: P.restore_preview(mp),
        {GR3: ("previewBaselineRestore", "_authoriseDangerous", "_confirmRestorePreview",
               "_restoreSelected"), PC: PC_FNS},
        ((GR3, "previewBaselineRestore", "d"), (GR3, "_confirmRestorePreview", "d")),
        maps=("select_data",),
        adapters={"modules/preview_confirm.py": ("restore_preview", "_restore_gates")}),
    "GET /drift/status": Render(
        # C96: through a REAL drift run, so the fields a run carries are seen.
        lambda mp, tmp: P.drift_status(mp, tmp),
        {I4: ("loadDriftStatus", "driftDetailHtml")},
        ((I4, "loadDriftStatus", "data"), (I4, "driftDetailHtml", "data"))),
    "GET /remote/status": Render(
        _get("/remote/status"),
        # remotePublicationHtml draws `publication` (C223).
        {GR2: ("loadRemotePanel", "remotePublicationHtml"), GR3: ("_gLastPush",)},
        ((GR2, "loadRemotePanel", "s"),)),
    "GET /ai/agent_log": Render(
        _get("/ai/agent_log?limit=50"),
        {I4: ("loadAgentTab", "agentBadgeState", "agentHealthBanner",
              "_markAgentEntriesSeen", "_hasUnseenFailures")},
        ((I4, "loadAgentTab", "data"),)),
    "GET /identity/posture": Render(
        _get("/identity/posture"),
        {"partials__security_posture.1.js": ("loadSecurityPosture",)},
        (("partials__security_posture.1.js", "loadSecurityPosture", "d"),),
        maps=("access_values_set",)),
    "GET /templates": Render(
        _get("/templates"),
        {"partials__template_editor.1.js": ("loadTemplateLibrary", "templateRowHtml")},
        (("partials__template_editor.1.js", "loadTemplateLibrary", "d"),),
        maps=("platforms",)),
    "GET /templates/approval/<path>": Render(
        _get("/templates/approval/cisco_ios/base.j2"),
        {"partials__template_editor.1.js": ("_loadApproval", "approvalCellHtml",
                                            "approvalEvidenceText")},
        (("partials__template_editor.1.js", "approvalCellHtml", "d"),)),
    "GET /golden/baselines": Render(
        lambda mp, tmp: P.golden_panel(mp, tmp, "/golden/baselines"),
        {GR3: ("loadGoldenRepoPanel",), GR1: ("_gBaselineCoverage", "_gCredWarning",
                                               "_gBaselineClaim", "_gBaselineDecision",
                                               "_gBaselineRow", "_gBaselinesHtml"),
         RS: ("baselineScopeHtml",)},
        ((GR3, "loadGoldenRepoPanel", "bRes"),)),
    "GET /golden/history/<host>": Render(
        _get("/golden/history/r1"),
        {GR1: ("showGoldenHistory",)},
        ((GR1, "showGoldenHistory", "d"),)),
    "GET /golden/legacy_store": Render(
        lambda mp, tmp: P.golden_panel(mp, tmp, "/golden/legacy_store"),
        {GR3: ("loadGoldenRepoPanel", "_gLegacyStoreCard")},
        ((GR3, "loadGoldenRepoPanel", "lRes"), (GR3, "_gLegacyStoreCard", "l"))),
    "GET /golden/renames": Render(
        _get("/golden/renames"),
        {GR3: ("loadGoldenRepoPanel",)},
        ((GR3, "loadGoldenRepoPanel", "rRes"),)),
    "GET /golden/migrate/plan": Render(
        _get("/golden/migrate/plan"),
        {GR3: ("loadGoldenRepoPanel", "_migrationCard")},
        ((GR3, "loadGoldenRepoPanel", "mRes"), (GR3, "_migrationCard", "m"))),
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
    # 7.1: the NetBox safety modal on the component. Each preview is built
    # server-side, so the adapter's reads count as drawn.
    "POST /netbox/safety/import/preview": Render(
        lambda mp, tmp: P.netbox_import_preview(mp, tmp),
        {NBS: ("netboxPreviewImport", "_nbShowPreview"), PC: PC_FNS},
        ((NBS, "netboxPreviewImport", "d"), (NBS, "_nbShowPreview", "d")),
        adapters={"modules/preview_confirm.py": ("netbox_import_preview", "_nb_gates",
                                                 "_nb_line", "build")}),
    "POST /netbox/safety/import_all/preview": Render(
        lambda mp, tmp: P.netbox_import_all_preview(mp, tmp),
        {NBS: ("netboxPreviewImport", "_nbShowPreview"), PC: PC_FNS},
        ((NBS, "netboxPreviewImport", "d"), (NBS, "_nbShowPreview", "d")),
        adapters={"modules/preview_confirm.py": ("netbox_import_preview", "_nb_gates",
                                                 "_nb_line", "build")}),
    "POST /netbox/safety/remove/preview": Render(
        lambda mp, tmp: P.netbox_remove_preview(mp, tmp),
        {NBS: ("netboxPreviewRemoval", "_nbShowPreview"), PC: PC_FNS},
        ((NBS, "netboxPreviewRemoval", "d"), (NBS, "_nbShowPreview", "d")),
        adapters={"modules/preview_confirm.py": ("netbox_removal_preview", "_nb_gates",
                                                 "_nb_line", "build")}),
    "GET /inventory/source/<list>": Render(
        _get("/inventory/source/Default"),
        {"partials__inventory_source.1.js": ("loadInventorySource", "applyInventorySourceUI",
                                             "renderInventoryBanner")},
        (("partials__inventory_source.1.js", "loadInventorySource", "d"),)),
    "GET /ai/approvals": Render(
        _get("/ai/approvals"),
        {I4: ("loadApprovalsTab", "_renderApprovalCard")},
        ((I4, "loadApprovalsTab", "data"),)),
    "GET /monitoring/stack/<tool>": Render(
        _get("/monitoring/stack/grafana"),
        {"partials__monitoring_stack.1.js": ("loadMonitoringStack", "_stackRender")},
        (("partials__monitoring_stack.1.js", "_stackRender", "data"),)),
    "GET /topology/service/status": Render(
        _get("/topology/service/status"),
        # topoSvcStateFor decides what an unconfigured service says (C126).
        {"partials__topology_service.1.js": ("topoSvcRefresh", "topoSvcStateFor")},
        (("partials__topology_service.1.js", "topoSvcRefresh", "d"),
         ("partials__topology_service.1.js", "topoSvcStateFor", "d"))),
    "GET /settings/integrations/status": Render(
        # The reader stores a value first (the real reader over the real
        # registry, every integration unconfigured in the test store): the
        # route serves only what was stored.
        lambda mp, tmp: _answer(P.integration_status(mp, tmp)),
        {"partials__settings_integrations.1.js": ("loadIntegrationStatus",),
         "nmas_status_bar.js": ("statusBarHtml",)},
        (("partials__settings_integrations.1.js", "loadIntegrationStatus", "d"),
         ("nmas_status_bar.js", "statusBarHtml", "d"))),
    "GET /ai/agent_timers": Render(
        _get("/ai/agent_timers"),
        {I4: ("loadAgentTimers",)},
        ((I4, "loadAgentTimers", "j"),)),
    "GET /devices/regions": Render(
        _get("/devices/regions"),
        {I1: ("applyDeviceRegions", "refreshDeviceRegions")},
        ((I1, "applyDeviceRegions", "data"),)),
    "GET /onboard/platforms": Render(
        _get("/onboard/platforms"),
        {"partials__onboard_wizard.1.js": ("openOnboardWizard", "onboardPlatformOptions")},
        (("partials__onboard_wizard.1.js", "openOnboardWizard", "d"),)),
    "GET /settings/integrations/general": Render(
        _get("/settings/integrations/general"),
        {"partials__settings_integrations.1.js": ("loadGeneralIntegrationSettings",)},
        (("partials__settings_integrations.1.js", "loadGeneralIntegrationSettings", "d"),),
        tables={"partials__settings_integrations.1.js": ("_GENERAL_MAP",)}),
    "GET /monitoring/config": Render(
        _get("/monitoring/config"),
        {I4: ("loadMonitoringTab",)},
        ((I4, "loadMonitoringTab", "cfg"),)),
    # A STORED PARTIAL IMPORT (C85). This entry used `_get("/netbox/status")`
    # on a store with no import, so `status` was empty (declared "NetBox is
    # not configured in the fixture") and the summary C8 filled with
    # `write_failures`, `partial` and `complete` was never examined: the
    # forward check would have named them as drawn nowhere, had the fixture
    # reached them. C72's class, found by a positive control on 2026-09-27.
    "GET /netbox/status": Render(
        lambda mp, tmp: P.netbox_status(mp, tmp),
        {I4: ("loadNetboxTab",), PC: PC_RESULT_FNS},
        ((I4, "loadNetboxTab", "nbs"),),
        maps=("lists",),
        adapters={"modules/preview_confirm.py": ("netbox_sync_result", "build_result")}),
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
        ("in_force",
         "the band acknowledgements in force that hide nothing now (C460, 2026-10-05): drawn "
         "by the v2 page (templates/v2/_attention.html, #att-in-force, from needs_attention() "
         "directly); today's v1 panel gains no capability (the v1 rule), so it does not"),
        ("ways",
         "the machine form of clears.when, which both pages draw (the redesign's Needs "
         "attention also offers Acknowledge, from acknowledge and event, which the adapter "
         "reads to hide an acknowledged row)")],
    "GET /ai/agent_log": [
        ("failed inconclusive interrupted last_run_at outcomes running "
         "runs_since_ok same_error_count",
         "the health breakdown behind the badge; the panel draws the streak "
         "and the badge. The agent panel is rebuilt in 8.4, when it returns"),
        ("ok", OK)],
    "GET /ai/agent_timers": [
        ("ai_enabled", "the timers draw the same whether AI is on or off; 8.4 "
                       "decides what a disabled agent's timers say"),
        ("ok", OK)],
    "GET /drift/status": [
        ("interval_h last_ts next_ts", "machine forms of values drawn as text "
                                       "(interval_s, last_at, next_at)"),
        ("next_from", "the panel says the schedule is held in memory by a fixed "
                      "title, not from this field; 7.2 reads it"),
        ("state", "drawn through `disabled` and `running`, not the state word; "
                  "7.2's Needs attention reads the state"),
        ("list", LIST)],
    "GET /golden/history/<host>": [
        ("hostname", "the request's own echo; the dialog is titled from the "
                     "caller's argument"),
        ("list", LIST)],
    "GET /golden/legacy_store": [
        ("in_repo", "the complement of only_legacy, which is drawn; 7.5 draws both"),
        ("list", LIST)],
    # Carried since before 2026-09-28 and never EXAMINED: the fixture had no
    # baseline tag until the panel's own fixture reached one.
    "GET /golden/baselines": [
        ("credential_detail credential_guarded credential_refused",
         "the per-device detail and the two subsets behind the stale list; the row "
         "draws the stale devices and the ones an account would be added back on, "
         "and the restore preview names each refusal. 7.5 (Versions) draws them"),
        # C315 (2026-10-02): reached once the provider rotated r1 after every
        # baseline. `credential_detail` is keyed by DEVICE, so `r1` is a
        # device name read as a field; inside it, the credential's FORM at the
        # ref and at HEAD (`secret 9`), never a value.
        ("at_head at_ref r1",
         "credential_detail's contents: the account's form at the ref and at HEAD, keyed "
         "by device. The row names the stale device and not the forms; 7.5 (Versions) "
         "draws them"),
        ("subject", "the tag's subject; the row is named by its tag"),
        ("list", "the list the withdrawal record belongs to; the panel is that list's")],
    "GET /golden/migrate/plan": [
        ("candidates devices marker merge_count staged_files",
         "the migration has run on every list; the card says only whether it "
         "has, and 7.8 removes the card"),
        ("list", LIST)],
    "GET /identity/posture": [
        ("action actor_kind", "per-gate detail (what a gate guards, which "
                              "actor kind); the panel draws value and origin. "
                              "7.7 (Settings)"),
        ("certs_url", "where assertions are verified; carried for a person, "
                      "drawn in 7.7"),
        ("config_revealed", "the panel infers it from `access` being present")],
    "GET /inventory/source/<list>": [
        ("config credential_list device_order filters refresh_interval role "
         "schema_version site tag",
         "the source's configuration; the panel draws its status only, and "
         "7.4 (Fleet, Networks) draws and sets the rest (reachability group a)")],
    "GET /monitoring/stack/<tool>": [
        ("name", "the tool's key; the card is keyed by it at the call site")],
    "POST /golden/capture/preview": [
        ("list", LIST)],
    "GET /golden/capture/preview/<job>": [("list", LIST)],
    "POST /golden/capture/apply": [("list", LIST)],
    "GET /netbox/status": [
        ("filename", "the list's legacy CSV name; nothing needs it on screen, "
                     "and 7.8 removes the legacy lists API"),
        ("config_template_id", "NetBox's internal id for the config template NMAS "
                               "installs; the template is named in NetBox itself"),
        ("last_sync", "the newest of the per-list timestamps, each drawn on its "
                      "own list's badge"),
        ("list", LIST)],
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
    "GET /remote/status": [("list", LIST)],
    "GET /settings/integrations/general": [
        ("tftp_server_ip", "carried and absent from the form's _GENERAL_MAP; "
                           "the TFTP server is set elsewhere (save_tftp_server). "
                           "7.7 gives it one home")],
    "GET /templates": [
        ("bindings overrides", "which template each device uses: 7.6 draws "
                               "and edits bindings (reachability group a)"),
        ("platforms", "the per-platform map; the library draws the flat list"),
        ("size", "the file size; the library lists names")],
    "GET /templates/approval/<path>": [
        ("path", "the path an approval covers; the badge states what it covers in words "
                 "(the fingerprint is READ: the row keeps it and Approve sends it, R12)"),
        ("ok", OK)],
    "GET /topology/service/status": [
        ("type url", "the service's type and address; the panel draws its state"),
        ("ok", OK)],
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
         "(the v1 rule), so it does not")],
    "POST /golden/restore/preview": [
        ("add intent_restored inventory_size mode partial ref un_onboarding",
         "structured forms of claims the drawn `summary` sentence makes (C23's "
         "coverage included); the component draws the per-device ones as parts"),
        ("advisory_diff approval_id", "the echo of an approval handoff; the "
                                      "client draws its own copy of what it sent"),
        ("scope", "drawn as the preview's `scope` what-not item; the adapter "
                  "takes it as an argument, so no `.get` reads it"),
        ("list", LIST)],
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
    "GET /identity/posture": [
        ("config_withheld_reason", "carried only when the Access values are "
                                   "withheld; the fixture's caller is a person")],
    "GET /monitoring/stack/<tool>": [
        ("detail link metrics", "carried only by a configured, reachable tool; "
                                "the fixture has none")],
    "GET /remote/status": [
        ("acknowledged acknowledgement_covers auto_push branch last_push "
         "last_push_failure managed_by_nmas owner_repo read_verified_at "
         "ssh_alias verified_at",
         "carried only when a remote is configured; the fixture has none")],
    "GET /templates/approval/<path>": [
        ("actor approved_at evidence", "carried only for an approved template; "
                                       "the fixture's is unapproved")],
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
    "GET /ai/agent_log entries": (R_, "no agent run in the fixture; the entry "
                                     "fields the panel draws were never examined"),
    "GET /ai/approvals entries": (R_, "no queued item in the fixture; the approval "
                                      "card has never been drawn from a real item"),
    "GET /golden/history/<host> history": (R_, "no golden commit for the device in "
                                               "the fixture; 7.3's History draws it"),
    "GET /golden/migrate/plan devices": (R_, "nothing to migrate in the fixture"),
    "GET /golden/migrate/plan merges": (R_, "no duplicate to merge in the fixture"),
    "GET /golden/migrate/plan staged_files": (S_, _STRINGS),
    "GET /golden/renames pending": (R_, "no pending rename in the fixture's manifest"),
    "GET /identity/posture service_allowed_operations": (S_, _STRINGS),
    "GET /identity/posture settings_read_failure": (R_, "the settings file reads; the "
                                                        "failure record is never exhibited"),
    "GET /inventory/source/<list> config.device_order": (S_, _STRINGS),
    "GET /inventory/source/<list> stale_devices": (R_, "a local list has no stale "
                                                       "NetBox devices; a map of records"),
    "GET /templates bindings.overrides": (R_, "no binding override in the fixture"),
    "GET /templates templates[].bound_devices": (S_, _STRINGS),
    "GET /templates/approval/<path> changes": (S_, _STRINGS),
    "POST /deploy/plan devices[].blocking_reasons": (S_, _STRINGS),
    "POST /deploy/plan devices[].expected_effects.up": (S_, _STRINGS),
    "POST /deploy/plan devices[].expected_effects.adjacencies_drop": (
        R_, "the fixture's program shuts no interface (C506 phase 2); an adjacency over a shut "
            "interface and a BGP session sourced from one are reached in "
            "tests/test_expected_effects_plan.py and drawn by the v2 deploy card"),
    "POST /deploy/plan devices[].expected_effects.may_form": (
        R_, "the fixture's program brings no interface up (C506 phase 2); reached in "
            "tests/test_expected_effects_plan.py"),
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
    "POST /templatize/seed/apply result.record.tags": (S_, "a seed takes no tag: tags mark a network snapshot, and an intent commit is not one"),
    "POST /golden/capture/apply result.did_not.items[].lines": (S_, "the first did-not item is r2's departure from intent, whose lines are drawn under its checks; the baseline item carries no lines"),
    "GET /deploy/receipts changes[].result.record.tags": (S_, "a receipt names the golden commit and not its tags, and the history's record statement says so"),
    "GET /deploy/receipts changes[].result.targets[].rollback.commands": (S_, "no device in the fixture was rolled back"),
    "GET /deploy/receipts changes[].result.targets[].rollback.not_undone": (S_, "no device in the fixture was rolled back"),
    "GET /deploy/receipts changes[].result.did_not.items[].lines": (S_, "the did-not items here are a refusal, which carries no lines"),
    "POST /deploy/apply result.did_not.items[].lines": (S_, "the fixture's FIRST target is the refusal (s3), and a refused device sent nothing, so its program, rollback and not-undone lines are empty by definition; the deployed s4 carries sent lines (test_deploy_receipts asserts them on screen)"),
    "POST /deploy/apply result.targets[].rollback.commands": (S_, "the fixture's FIRST target is the refusal (s3), and a refused device sent nothing, so its program, rollback and not-undone lines are empty by definition; the deployed s4 carries sent lines (test_deploy_receipts asserts them on screen)"),
    "POST /deploy/apply result.targets[].rollback.remaining": (S_, "no rollback in the fixture; an incomplete rollback's remaining lines are drawn in test_pipeline (TestARollbackSaysWhatItAchieved)"),
    "GET /deploy/receipts changes[].result.targets[].rollback.remaining": (S_, "no rollback in the fixture; an incomplete rollback's remaining lines are drawn in test_pipeline (TestARollbackSaysWhatItAchieved)"),
    "POST /deploy/apply result.targets[].rollback.not_undone": (S_, "the fixture's FIRST target is the refusal (s3), and a refused device sent nothing, so its program, rollback and not-undone lines are empty by definition; the deployed s4 carries sent lines (test_deploy_receipts asserts them on screen)"),
    "POST /golden/restore/preview devices[].excluded_unrenderable": (S_, _STRINGS),
    "POST /golden/restore/preview intent_restored": (S_, _STRINGS),
    "POST /golden/restore/preview un_onboarding": (S_, _STRINGS),
    "POST /onboard/plan host_vars": (R_, "the plan carries no intent for a device "
                                         "not yet onboarded; drawn in 7.4"),
    "POST /netbox/safety/import/preview preview.explain": (R_, "no concept is taught on the NetBox safety "
                                            "modal yet; the concepts harness names it"),
    "POST /netbox/safety/import/preview preview.targets[].program.authorised": (S_, "a NetBox write is sent to no "
                                            "device, so no line is authorised"),
    "POST /netbox/safety/import/preview preview.targets[].program.dangerous": (S_, "a NetBox write is sent to no "
                                            "device, so no line is dangerous"),
    "POST /netbox/safety/import/preview preview.what.targets[].select_data": (R_, "the one-shot token binds the plan's "
                                            "hash, carried beside the preview, not per target"),
    "POST /netbox/safety/import/preview preview.targets[].program.notes": (S_, "an import has no cascade; notes "
                                            "carry only a removal's"),
    "POST /netbox/safety/import/preview preview.what_not.items[].lines": (S_, "an import's what-not items are "
                                            "sentences; a removal's carry lines"),
    "POST /netbox/safety/import_all/preview preview.explain": (R_, "no concept is taught on the NetBox safety "
                                            "modal yet; the concepts harness names it"),
    "POST /netbox/safety/import_all/preview preview.targets[].program.authorised": (S_, "a NetBox write is sent to no "
                                            "device, so no line is authorised"),
    "POST /netbox/safety/import_all/preview preview.targets[].program.dangerous": (S_, "a NetBox write is sent to no "
                                            "device, so no line is dangerous"),
    "POST /netbox/safety/import_all/preview preview.what.targets[].select_data": (R_, "the one-shot token binds the plan's "
                                            "hash, carried beside the preview, not per target"),
    "POST /netbox/safety/import_all/preview preview.targets[].program.notes": (S_, "an import has no cascade; notes "
                                            "carry only a removal's"),
    "POST /netbox/safety/import_all/preview preview.what_not.items[].lines": (S_, "an import's what-not items are "
                                            "sentences; a removal's carry lines"),
    "POST /netbox/safety/remove/preview preview.explain": (R_, "no concept is taught on the NetBox safety "
                                            "modal yet; the concepts harness names it"),
    "POST /netbox/safety/remove/preview preview.targets[].program.authorised": (S_, "a NetBox write is sent to no "
                                            "device, so no line is authorised"),
    "POST /netbox/safety/remove/preview preview.targets[].program.dangerous": (S_, "a NetBox write is sent to no "
                                            "device, so no line is dangerous"),
    "POST /netbox/safety/remove/preview preview.what.targets[].select_data": (R_, "the one-shot token binds the plan's "
                                            "hash, carried beside the preview, not per target"),
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
    "POST /golden/restore/preview preview.targets[].program.prior.lines": (R_, "the "
        "preview's copy of the aggregate; reached in test_authorised_lines.py"),
    # C315 (2026-10-02): eighteen more the first-item-then-intersection walker
    # hid, each empty in one row and ABSENT from another, never held.
    **{f"{route} {base}.{k}": (S_, _DEPLOY_CHECKS)
       for route, base in (("GET /deploy/receipts", "changes[].result.targets[].checks"),
                           ("POST /deploy/apply", "result.targets[].checks"))
       for k in ("from_intent", "intent_unmet", "issues", "pending_convergence",
                 "unreadable")},
    "POST /deploy/apply results[].pending_convergence": (S_, _DEPLOY_CHECKS),
    "POST /deploy/apply results[].verify.issues": (S_, _DEPLOY_CHECKS),
    "GET /golden/baselines baselines[].credential_silent": (S_, "device names; empty by "
        "design on every path since C75 and C79 (a stale account is guarded, which this "
        "provider reaches for r1), and asserted empty on the real fleet configs"),
    "GET /golden/baselines baselines[].credential_refused": (S_, "device names; the intent "
        "guard refuses a ref whose intent names a secret the store lost, and no ref in "
        "this lab commits intent"),
    "GET /golden/baselines baselines[].missing_devices": (S_, "device names; every baseline "
        "here holds the whole inventory. A partial one is drawn in test_restore_scope.py"),
    "GET /golden/baselines baselines[].no_intent": (S_, "device names; every device here "
        "has a golden at every baseline it is counted in"),
    "GET /onboard/pending pending[].last_run.result.record.tags": (S_, "an onboarding run "
        "makes no tag"),
    "POST /golden/restore/preview devices[].prior_authorised.lines": (R_, "the restore "
        "plan's per-device copy of the aggregate, the state the deploy plan's own entry "
        "declares; reached through real receipts in test_authorised_lines.py"),
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
EMPTY_RECORDS_CEILING = 28


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
UNDRAWN_CEILING = 113  # +3: C506 phase 2, the plan's Expected effects (derived, expected, unexpected), drawn by the v2 deploy card only (the v1 page gains nothing) (2026-10-06). Before: +1: C460, in_force, drawn by the v2 page only (the v1 panel gains nothing) (2026-10-05). Before: -1: R12's client half reads the approval state's fingerprint (2026-10-04). Before: +1: clears.ways (2026-10-02), the machine form of clears.when, which both pages draw. Before: +3: C315, the Baselines provider reaches a stale credential, and credential_detail's form at the ref and at HEAD was never drawn (new coverage, not a regression). Before: -1: C310, the deploy result reads its golden's `refused` (a device whose golden was not recorded). Before: -1: P.9 (b)'s deploy wizard reads the plan's `list` (the scope carries it)
PHANTOM_CEILING = 18


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
        P._client().get("/")
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
        assert len(RENDERS) >= 20
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
        ("POST /deploy/plan", "from_this_edit"),
        ("POST /golden/restore/preview", "commands")])
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
