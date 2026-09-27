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
from tests.payload_render import (lift, literal_keys, payload_keys, reads,
                                  root_reads, shipped)


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


DW, GR1, GR2, GR3 = ("partials__deploy_wizard.1.js", "partials__golden_repo.1.js",
                     "partials__golden_repo.2.js", "partials__golden_repo.3.js")
I1, I4 = "index.1.js", "index.4.js"

RENDERS = {
    "GET /onboard/pending": Render(
        lambda mp, tmp: P.onboard_pending(mp, tmp),
        {"partials__onboard_pending.1.js": ("loadOnboardPending", "pendingBannerHtml")},
        (("partials__onboard_pending.1.js", "pendingBannerHtml", "data"),)),
    "POST /deploy/plan": Render(
        lambda mp, tmp: P.deploy_plan(mp),
        {DW: ("openDeployPlan", "_renderDeployPlan", "_deviceCard", "_programHtml",
              "_attributionHtml", "_reauthoriseDevice", "applyDeploy")},
        ((DW, "openDeployPlan", "d"), (DW, "_renderDeployPlan", "plan"))),
    "POST /deploy/apply": Render(
        lambda mp, tmp: P.deploy_apply(mp),
        {DW: ("applyDeploy", "_renderDeployResult")},
        ((DW, "_renderDeployResult", "report"),), maps=("by_outcome",)),
    "POST /golden/restore/preview": Render(
        lambda mp, tmp: P.restore_preview(mp),
        {GR3: ("previewBaselineRestore", "_authoriseDangerous", "restorePreviewText")},
        ((GR3, "restorePreviewText", "d"),)),
    "GET /drift/status": Render(
        _get("/drift/status"),
        {I4: ("loadDriftStatus", "driftDetailHtml")},
        ((I4, "loadDriftStatus", "data"), (I4, "driftDetailHtml", "data"))),
    "GET /remote/status": Render(
        _get("/remote/status"),
        {GR2: ("loadRemotePanel",), GR3: ("_gLastPush",)},
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
        _get("/golden/baselines"),
        {GR3: ("loadGoldenRepoPanel",), GR1: ("_gBaselineCoverage", "_gCredWarning")},
        ((GR3, "loadGoldenRepoPanel", "bRes"),)),
    "GET /golden/history/<host>": Render(
        _get("/golden/history/r1"),
        {GR1: ("showGoldenHistory",)},
        ((GR1, "showGoldenHistory", "d"),)),
    "GET /golden/legacy_store": Render(
        _get("/golden/legacy_store"),
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
        _post("/onboard/plan", {"list_name": "Default", "hostname": "bp-x",
                                "platform": "cisco_iosxe", "mgmt_ip": "203.0.113.6"}),
        {"partials__onboard_wizard.1.js": ("onboardRefresh", "onboardReviewHtml",
                                           "onboardCanCreate")},
        (("partials__onboard_wizard.1.js", "onboardRefresh", "d"),)),
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
        {"partials__topology_service.1.js": ("topoSvcRefresh",)},
        (("partials__topology_service.1.js", "topoSvcRefresh", "d"),)),
    "GET /settings/integrations/status": Render(
        _get("/settings/integrations/status"),
        {"partials__settings_integrations.1.js": ("loadIntegrationStatus",)},
        (("partials__settings_integrations.1.js", "loadIntegrationStatus", "d"),)),
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
        {"partials__onboard_wizard.1.js": ("openOnboardWizard",)},
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
    "GET /netbox/status": Render(
        _get("/netbox/status"),
        {I4: ("loadNetboxTab",)},
        ((I4, "loadNetboxTab", "nbs"),)),
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
    "GET /netbox/status": [
        ("filename", "the list's legacy CSV name; nothing needs it on screen, "
                     "and 7.8 removes the legacy lists API")],
    "GET /onboard/pending": [
        ("counts total overdue stale thresholds",
         "the banner derives its counts from the rows; the server's counts "
         "and thresholds are unread duplicates, drawn or dropped in 7.4"),
        ("onboarded_at", "the banner draws the age (age_seconds), not the time"),
        ("stage", "a ztp row's stage word; the banner draws its summary sentence")],
    "GET /onboard/platforms": [
        ("dialect", "the config dialect beside the slug; the wizard offers slugs"),
        ("ok", OK)],
    "GET /remote/status": [("list", LIST)],
    "GET /settings/integrations/general": [
        ("tftp_server_ip", "carried and absent from the form's _GENERAL_MAP; "
                           "the TFTP server is set elsewhere (save_tftp_server). "
                           "7.7 gives it one home")],
    "GET /settings/integrations/status": [
        ("name", "each integration's key; the card is keyed by it")],
    "GET /templates": [
        ("bindings overrides", "which template each device uses: 7.6 draws "
                               "and edits bindings (reachability group a)"),
        ("platforms", "the per-platform map; the library draws the flat list"),
        ("size", "the file size; the library lists names")],
    "GET /templates/approval/<path>": [
        ("fingerprint path", "the closure hash and path an approval covers; "
                             "the badge states what it covers in words"),
        ("ok", OK)],
    "GET /topology/service/status": [
        ("type url", "the service's type and address; the panel draws its state"),
        ("ok", OK)],
    "POST /deploy/apply": [
        ("capture_confirmed capture_current confirmed_hash current_hash moved",
         "a refusal's operands: its `reason` sentence names them and which "
         "side moved, and that IS drawn (test_deploy_plan_apply_seam)"),
        ("by_outcome refused workers", "counts and groupings of the rows, "
                                       "which are drawn one by one with the total"),
        ("commit golden", "the batch's golden commit; 7.5 links it"),
        ("list", LIST)],
    "POST /deploy/plan": [
        ("adds removes differs reordered complete",
         "the diff's statistics; the wizard draws the PROGRAM itself, which "
         "is what is confirmed (D4)"),
        ("bootstrap excluded_unrenderable intent_drift masked_refs rolled_back "
         "stale_acknowledgements unacknowledged unmodeled unsendable",
         "each also reaches the screen as a sentence in blocking_reasons, which "
         "is drawn; 7.1's component draws each gate by name (section 2, part 5)"),
        ("deployable_count unchanged_count", "summary counts; each device is drawn"),
        ("modeled_coverage round_trip_fidelity", "fidelity figures; 7.1 draws "
                                                 "them beside the template gate"),
        ("attributable platform template_approved",
         "flags behind what is drawn (the split, the card, the gate)"),
        ("list", LIST)],
    "POST /golden/restore/preview": [
        ("add excluded_unrenderable intent_restored inventory_size mode partial "
         "ref un_onboarding unchanged_count",
         "structured forms of claims the drawn `summary` sentence makes (C23's "
         "coverage included); 7.1's component draws them as parts"),
        ("advisory_diff approval_id", "the echo of an approval handoff; the "
                                      "client draws its own copy of what it sent"),
        ("platform", "each device's platform; the preview is per device"),
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


def _flat(table):
    return {f"{route} {key}": reason for route, groups in table.items()
            for keys, reason in groups for key in keys.split()}


UNDRAWN_CEILING = 117
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


class TestAnchors:
    """The four recorded instances. Each key is carried AND read."""

    @pytest.mark.parametrize("route,key", [
        ("POST /deploy/plan", "commands"), ("POST /deploy/plan", "dangerous"),
        ("POST /deploy/plan", "attribution"), ("GET /onboard/pending", "list"),
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
