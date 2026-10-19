"""route_gates — every mutating endpoint, declared with the gate it needs.

NSOT_PLAN P.3 step 1 (register B12). Before this, the identity gate was a
function each route had to remember to call, and of the routes that change a
device, one did. CLAUDE.md said they all did, and that sentence is why nobody
checked. The gate is now a TABLE, enforced by one ``before_request`` hook ahead
of any route's own input validation, and ``tests/test_route_gates.py`` fails
on any mutating endpoint the table does not declare. A route cannot be added
without somebody saying what it is.

**The kinds.** One per endpoint, chosen by what the act MEANS in the audit,
because ``service_allowed_operations`` and the ``require_*_for_<kind>``
settings are keyed on it and a grant must not reach further than the act it
was written for:

``confirm``
    Sends something to a device, or reverses something that did. A person
    must have read what will happen.
``approve``
    Records a decision that a later device change acts on: the approval
    queue, template approval, committed intent, goldens, templates, NetBox
    (which holds intent, NSOT_PLAN 4.1).
``configure``
    The tool's own settings, gates, inventory, credentials and local records.
``reveal``
    Exposes a secret or a device's configuration, to the caller or to a place
    the caller names (a TFTP copy off the device is a reveal).
``publish_remote``
    Publishes a network's history to a remote.
``break_glass``
    Was the terminal: typed commands with no plan, no hash and no rollback. The
    terminal was removed (R39, 2026-10-05), so no route or event uses this kind;
    it stays declared until its two settings retire.
``not_device``
    A read, a preview, a test, UI layout, or something the schedule does
    anyway. **Not gated**, and each one says why.

The table is keyed on the Flask ENDPOINT, not the URL: a blueprint's full
path appears nowhere in its source, and ``app.url_map`` is the authority.
Only mutating methods are gated here. A GET that reveals (the golden
``?reveal=1``, the onboarding bootstrap) still gates itself, because whether
it reveals depends on the request.

An endpoint missing from the table is REFUSED at run time as well as failing
the suite. Fail-closed is the runtime half; the test is what stops it
happening.
"""

import functools
import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

NOT_DEVICE = "not_device"

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


@dataclass(frozen=True)
class Gate:
    kind: str
    reason: str
    #: Passed to ``identity.require`` so a service grant keyed on an operation
    #: (``service_allowed_operations``) still works where one was named.
    operation: str = ""


def _g(kind, reason, operation=""):
    return Gate(kind, reason, operation)


C, A, K, R, P, N = ("confirm", "approve", "configure", "reveal",
                    "publish_remote", NOT_DEVICE)

#: Every mutating endpoint. Grouped by kind; within a group, by subsystem.
GATES = {
    # ---- confirm: sends to a device -------------------------------------
    # Today's re-apply (golden.restore_apply) left at 7.8 (2026-10-17, P7-21): v2's
    # device_v2.restore_confirm and v2.history_reapply_confirm run the same restore as a job.
    # Today's deploy wizard (deploy.plan, deploy.apply) and onboarding (onboard.plan, .create,
    # .verify_preview, .verify, .abandon) left at 7.8 (2026-10-17, P7-25): device_v2's and
    # v2's deploy, and onboard_v2's, below.
    "v2.history_view_save": _g(K, "saves a History › Query view (a link to a read) for the "
                                  "network, with a title, recorded (C667)"),
    "v2.history_view_pin": _g(K, "pins or unpins a saved History › Query view for everyone, "
                                 "recorded (C667)"),
    "v2.history_view_remove": _g(K, "removes a saved History › Query view; only the link goes, "
                                    "the history it asks is untouched, recorded (C667)"),
    "v2.history_reapply_confirm": _g(C, "re-applies a baseline to every device it holds, as one batch job (History › Baselines)"),
    "adopt_v2.confirm": _g(C, "adds the tool's account to a device the tool did not build and "
                              "brings it under management (board G)", "adopt"),
    "device_v2.reload_confirm": _g(C,"reloads the device, its planned-restart window declared first (P.14, cutover blocker 6), which sets a Grafana silence on its alerts as the person, with their reason (B3)", "reload"),
    "dhcp_v2.exclusion_confirm": _g(C, "adds or removes a DHCP exclusion: writes the subnet's "
                                       "pools as the pieces through the subnet's write, reloads "
                                       "Kea and reads it back, as a verified person with a "
                                       "reason (C529 step 3, board D)"),
    "dhcp_v2.subnet_confirm": _g(C, "changes a Kea subnet's pool, options or lease times: writes "
                                    "Mercury's subnet file, reloads Kea and reads it back, as a "
                                    "verified person with a reason (C529 step 3, board C)"),
    "dhcp_v2.reservation_confirm": _g(C, "adds, changes or removes a Kea reservation: writes "
                                         "Mercury's file for the subnet and reloads Kea, which "
                                         "clients then receive (C529 step 2, board B)",
                                      "dhcp_reservation"),
    "onboard_v2.verify": _g(C, "reaches the pending device and rotates its credential, from its "
                               "v2 page (`routes.onboard.verify_run`)", "onboard_verify"),
    "onboard_v2.abandon": _g(C, "deletes the pending device's records from NetBox and the "
                                "repository, from its v2 page", "onboard_abandon"),
    "device_v2.restore_confirm": _g(C, "re-applies a moment (its golden now, an older golden or a baseline) to one device from the v2 device page (7.3; THE restore plan and apply, run as a job, in the list its preview was drawn in, C396), merge-only, every line needing a reason (a dangerous line, an account added back) with its stated reason in the hash"),
    "device_v2.deploy_confirm": _g(C, "deploys a device's committed intent from the v2 device page (7.3; THE plan and apply (`routes.deploy.plan_devices`, `apply_batch`) the batch apply runs too, as a job), merge-only, with any line ticked for removal (Mode B) and every dangerous line's stated reason in the hash"),
    "device_v2.rotate_confirm": _g(C, "rotates a device's login credential from the v2 device page (7.3; rotate_op.confirm_and_start): the device then accepts only the new password"),
    "credential_profiles_v2.rotate_due_confirm": _g(C, "rotates every due device's login credential (C724, Rotate due devices now), one at a time through the device page's rotation, bound to the previewed list's hash"),
    "v2.profile_apply_confirm": _g(C, "deploys the monitoring profile's confirmed programs to the chosen devices, one after another (P.9 d2)"),
    "v2.save_confirm": _g(C, "saves the running config to startup on each chosen device, reads it back, and records the running config as golden in one commit (C593, Devices › Save): changes what the devices boot"),
    "device_v2.persist_confirm": _g(C, "saves the running config to startup on a device and reads it back, from the v2 device page (7.3; persist_op.apply)"),
    "device_v2.rekey_confirm": _g(C, "keeps the SSH host key a device answers with now in place of the one Mercury holds (C906): every later session signs in to whatever presents it, so a person confirms it, bound to both keys"),
    "privileged_v2.confirm": _g(C, "sends one Tier 2 command (Run a privileged command…, NSOT_TIER2_PRIVILEGED) to a device, holding it, bound to the previewed plan and a stated reason; verified and recorded"),
    "update.apply": _g(C, "requests the Update: the root-owned updater moves the app to a CI-passed commit and restarts it"),

    # ---- approve: a decision a later device change acts on ---------------
    # Today's template editor (templates.approve, templates.write_template, templates.validate)
    # and intent editor (templatize.edit_committed, templatize.preview_committed_edit) left at
    # 7.8 (2026-10-17, P7-23): Templates › Approve… and Edit… (templates_v2) and each device's
    # Intent tab (intent_v2). Today's device-action JSON routes (retire, persist and rotate's
    # preview and apply, templatize's seed, revert and retry) left at 7.8 (2026-10-17, P7-24):
    # each device page's Actions (the device_v2 entries).
    "v2.ip_sla_policy_set": _g(A, "commits the monitoring profile's IP SLA policy, which decides the probes suggested (P.9 d4)"),
    "v2.ip_sla_commit": _g(A, "commits suggested IP SLA probes into the devices' intent (P.9 d4)"),
    "v2.decline_confirm": _g(A, "commits a declined profile section (or its undo) to one device's intent, with a reason, as the verified person (C718)"),
    "v2.credentials_drill": _g(K, "records the offline drill's receipt, checked against a logged export (board 7, D)"),
    "v2.credentials_check": _g(K, "opens a kept break-glass file in memory and records the verdict per device; no value is shown, kept or logged (board 7, C)"),
    "v2.credentials_intact": _g(K, "records the browser's word on a break-glass download: its sha256 of the bytes received against the server's (board 7)"),
    "v2.heartbeat_apply": _g(K, "writes the re-measured heartbeat alert rules file (P.7); a person installs it on the host"),
    "templates_v2.approve": _g(A, "approves a template (7.6, board B), bound to the fingerprint and the check shown"),
    "templates_v2.revoke": _g(A, "withdraws a template approval with the person's reason (7.6, board C)"),
    "templates_v2.seed": _g(A, "commits the shipped template library into a network that lacks it, bound to the library previewed (cutover blocker 5)"),
    "templates_v2.bindings_apply": _g(A, "changes which template renders which device, bound to the file and the change previewed (cutover blocker 5)"),
    "templates_v2.edit_commit": _g(A, "commits a template edit bound to the version opened, revoking every approval over it (cutover blocker 5)"),
    "v2.profile_propose_commit": _g(A, "commits the network's profile proposed from the connectors on v2 (C566, board A), bound to the proposal shown"),
    "templates_v2.bring": _g(A, "commits the shipped template over the network's stale copy and revokes every approval over it (C566, board B)"),
    "reads_v2.ask_run": _g(R, "reads a device through the reads engine (C547): allowlisted "
                              "commands only, its answers shown to the person, every run "
                              "recorded"),
    "reads_v2.show_commands_run": _g(R, "reads many devices through the reads engine (C548): "
                                        "allowlisted commands only, their answers shown to the "
                                        "person, every run recorded"),
    "privileged_v2.preview": _g(R, "reads a device's before-state for a Tier 2 command through the "
                                 "reads engine (board T2-B); every run recorded"),
    "reads_v2.logging_path_run": _g(R, "tests the logging path (board F): one send log line "
                                     "to each device through the reads engine, then Loki "
                                     "watched; every run recorded"),
    "reads_v2.show_commands_ignore": _g(K, "records on a Show commands run the columns the "
                                          "person ticked to ignore when grouping (C580); asks "
                                          "no device"),
    "reads_v2.show_commands_save_set": _g(K, "commits a saved command set to the network's "
                                             "repository as the person (R3); sends nothing"),
    "intent_v2.commit": _g(A,"commits an edit to a device's intent (board H), bound to the version opened"),
    "bulk_intent_v2.apply": _g(A, "commits one change to the ticked devices' intent, from "
                                  "Devices (board D; routes.templatize.bulk_apply_of)"),
    "device_v2.revert_confirm": _g(A, "commits the inverse of one intent commit's change from the v2 device page (7.3, board 11; intent_ops.revert_apply, in the list its card carries)"),
    "device_v2.retry_confirm": _g(A, "lifts a blocked change so it may be sent again, with a stated reason, from the v2 device page (7.3, board 11; intent_ops.retry_apply, in the list its card carries)"),
    "device_v2.seed_confirm": _g(A, "commits a device's first full intent, parsed from its committed golden, from the v2 device page (7.3, board 8; seed.apply, in the list its card carries)"),
    "device_v2.retire_confirm": _g(A, "retires a device from the v2 device page (7.3, board 12; retire.apply, in the list its card carries): removes its intent and golden in a commit, declares its startup unmapped, clears its override and deletes its CSV row against the export log"),
    # Capture (7.1 step 4, C82, C89): Save All is its whole-fleet form, and
    # the old one-click route is gone, because nothing in it asked whether the
    # state being enshrined was the one intended. Today's capture routes (golden.capture_preview
    # and golden.capture_apply), the monitoring profile's (templatize.profile_propose_preview
    # and _apply) and the inventory refresh (inventory.refresh) left at 7.8 (2026-10-17, P7-27)
    # with today's index, their one caller.
    "device_v2.capture_confirm": _g(A, "commits a device's confirmed capture as its golden, from the v2 device page (7.3; routes.golden.apply_captures)"),
    "onboard_v2.create": _g(A, "commits a new device's identity and intent, from v2's Add device",
                            "onboard_device"),
    "netbox_v2.confirm": _g(A, "writes to or deletes from NetBox as previewed, or (Stop tracking, C954) has Mercury forget what it created, from v2's NetBox page"),

    # ---- configure: the tool's own settings, gates, inventory, records ---
    "settings_v2.group_switch": _g(K, "switches a network's settings group (inherit, its own with its values and secrets, not applicable), bound to its preview and recorded"),
    "settings_v2.mode_switch": _g(K, "switches a network between inheriting from Default and standalone, bound to its preview and recorded"),
    "settings_v2.group_save": _g(K, "saves a card's fields (Default's, or a network's own group) and their secrets, recorded"),
    "settings_v2.group_test": _g(K, "tests a card's integration with its saved values, for the person configuring it (the S3 archive's Test writes its probe object)"),
    "settings_v2.records_save": _g(K, "saves the installation's records database settings, recorded (board F2; works with the database down)"),
    "settings_v2.records_test": _g(K, "tests the records database (six checks, a temporary row rolled back) and keeps its answer"),
    "settings_v2.records_replace": _g(K, "replaces Mercury's copy of the records database password (a secret), recorded, then tests it"),
    "settings_v2.records_store_apply": _g(K, "moves a record store to the records database or back (copy, switch, check), bound to its preview, recorded (Phase 4)"),
    "settings_v2.network_source_apply": _g(K, "changes a network's inventory source as previewed, refreshes it, recorded"),
    "settings_v2.network_create": _g(K, "creates a network as previewed (its folder derived from its name), recorded (board I's pattern)"),
    "settings_v2.network_delete": _g(K, "deletes a network as previewed, its name typed: its folder moved aside, never erased, recorded"),
    "network_v2.choose": _g(K, "records the verified person's own network choice (board N): what their pages show, never anyone else's"),
    "settings_v2.install_save": _g(K, "saves an Installation card's settings (NetBox connection, Proxmox, Commit author, Server) for every network, recorded (board F3)"),
    "settings_v2.install_test": _g(K, "tests an Installation card's service (NetBox, Proxmox) with its saved settings; changes nothing"),
    "settings_v2.install_replace": _g(K, "replaces an Installation card's token (a secret; Proxmox's with its id), recorded, then tests it"),
    "settings_v2.platforms_preview": _g(K, "previews a platform or role map change: every device it moves, from each NetBox list's last inventory; writes nothing (board F4)"),
    "settings_v2.platforms_test": _g(R, "reads one device through the reads engine with a proposed driver, show version only (board F4's platform map Test)"),
    "settings_v2.platforms_apply": _g(K, "writes the platform or role map as previewed, bound to its fingerprint, recorded, and refreshes each NetBox list (board F4)"),
    "settings_v2.install_ratify": _g(K, "records a decision about an access or identity setting: writes the value already in force, never a change, recorded (board F4, C625)", "ratify_setting"),
    "settings_v2.diag_drift_interval": _g(K, "sets the drift schedule for every network, recorded (board F4, Diagnostics)"),
    "settings_v2.diag_drift_switch": _g(K, "turns a network's drift checks off or on, with who and when, recorded (board F4)"),
    "settings_v2.diag_drift_check": _g(N, "the schedule does this anyway; it only happens earlier (board F4's Check now)"),
    "settings_v2.network_source_preview": _g(N, "reads NetBox once with proposed filters for a source change's preview; writes nothing"),
    "settings_v2.network_source_refresh": _g(N, "reads NetBox for a NetBox network now; the schedule does this anyway"),
    "settings_v2.network_create_preview": _g(N, "checks a new network's name and the folder it derives; writes nothing"),
    "settings_v2.network_delete_preview": _g(N, "counts what a network holds and says where its data would go; writes nothing"),
    "settings_v2.records_store_preview": _g(N, "counts a record store's lines, network by network, in the files and the records database for a move's preview; writes nothing"),
    "settings_v2.install_writes_off": _g(K, "turns NetBox's master write switch off for every network, recorded; never turns it on"),
    "topology_v2.expected_declare": _g(K, "declares a device an expected island of its "
                                          "network, with a reason, recorded (P.11)"),
    "topology_v2.expected_withdraw": _g(K, "withdraws an expected-island declaration, "
                                           "recorded (P.11)"),
    "topology_v2.positions_save": _g(K, "saves the network's Topology layout after a person "
                                       "moved a device, for everyone, recorded (C661)"),
    "topology_v2.positions_reset": _g(K, "withdraws the network's arranged Topology layout, "
                                        "recorded (C661)"),
    "topology_v2.path_run": _g(R, "traces the path packets take from a device to an address "
                                  "(board D): each hop's forwarding answer read through the "
                                  "reads engine and shown to the person, every read recorded"),
    "credential_profiles_v2.save": _g(K,"saves a credential profile from Credentials › "
                                         "Profiles, recorded (who, which, the fields set)"),
    "credential_profiles_v2.delete": _g(K, "deletes a credential profile from Credentials › "
                                           "Profiles, recorded"),
    "credential_profiles_v2.policy_save": _g(K, "sets a credential profile's scheduled "
                                              "rotation policy (C724), a verified person's, "
                                              "recorded (who, when, what)"),

    # ---- reveal: device configuration or secrets leave the device --------
    "breakglass.export": _g(R, "every device's credential and the application key, sealed and sent to the browser"),
    "device_v2.golden_reveal": _g(R, "one golden version of a device, unmasked, drawn in place on History (decided 2026-10-05: a person, recorded)", "golden_config"),
    "onboard_v2.bootstrap": _g(R, "a pending device's bootstrap config, its one-time credential in "
                                  "the clear, drawn on its v2 page", "onboard_bootstrap"),
    "v2.history_ask_logs_reveal": _g(R, "one log line, unmasked, drawn in place under its row in "
                                        "History › Query's Lines view to a verified person who "
                                        "gave a reason (C818); recorded first (who, when, which "
                                        "line, the reason), never the value", "log_line"),

    # ---- publish_remote --------------------------------------------------
    "remote.push": _g(P, "publishes the repository, from History's header"),
    # Today's Remote card's auto-push, acknowledge and write probe (remote.auto_push,
    # remote.acknowledge, remote.verify_write) left at 7.8 (2026-10-17, P7-21): History ›
    # Remote set-up… (remote_v2.*, below) does each.
    "remote_v2.connect": _g(P, "binds the network to its existing remote, from History's set-up card (C631)"),
    "remote_v2.write_probe": _g(P, "writes a probe to the remote, from History's set-up card (C631)"),
    "remote_v2.acknowledge": _g(P, "acknowledges the history scan before first publication, from History's set-up card (C631)"),
    "remote_v2.auto_push": _g(P, "switches automatic publishing on, from History's set-up card (C631)"),

    # ---- not gated: reads, previews, tests, layout, the schedule's work --
    "device_v2.rotate_preview": _g(N, "reads the device's account line live for the rotation's plan, from the v2 device page (rotate_op.plan); changes nothing"),
    "device_v2.capture_start": _g(N, "starts the capture preview's read of one device, from the v2 device page (routes.golden.start_capture_preview); records nothing"),
    "templates_v2.coverage_check": _g(N, "measures how much of each device's golden its "
                                         "template reproduces, as a job; reads git, keeps the "
                                         "answer, reaches no device"),
    "adopt_v2.preview": _g(N,"reads the device over the supplied login; sends and writes "
                              "nothing"),
    "onboard_v2.preview": _g(N,"builds Add device's plan and review; creates nothing"),
    "onboard_v2.verify_preview": _g(N, "reads the pending device and computes what Verify would "
                                       "send; sends nothing"),
    "onboard_v2.abandon_preview": _g(N, "Abandon's dry run; removes nothing"),
    "device_v2.persist_read": _g(N, "starts Persist's preview read: the device's running and "
                                    "startup configurations, and `dir nvram:` when startup "
                                    "keeps a certificate there; sends nothing that changes it"),
    "device_v2.reload_start": _g(N, "starts Reload's preview: reads the device's running and "
                                    "startup configurations, image and boot variable; sends "
                                    "nothing that changes it"),
    "templates_v2.bindings_preview": _g(N, "names every device whose template a bindings change "
                                           "moves; writes nothing"),
    "templates_v2.edit_check": _g(N, "renders a template edit for its devices in a copy of the "
                                     "library outside the repository; writes nothing"),
    "bulk_intent_v2.preview": _g(N, "computes the change's preview for the ticked devices; "
                                    "writes nothing"),
    "intent_v2.check": _g(N, "checks and renders an edit as it is typed; writes nothing"),
    "intent_v2.acknowledge": _g(N, "rewrites the document in the editor (its unmodeled_ack block); writes nothing"),
    "intent_v2.reopen": _g(N, "opens the editor on what is committed now with the person's edit on it; writes nothing"),
    "update.step_done": _g(C, "records that a person did a host step the tool cannot check: the release's record of what was done on the host"),
    "attention.acknowledge": _g(K, "records that a person acknowledged one event row on Needs attention, with a reason; the row leaves the page and the event stays in its record"),
    "restarts.planned": _g(K, "records a planned-restart window, so the restarts it covers are not reported as unexpected, and sets a Grafana silence on its devices' alerts as the caller, with the reason (B3); a window covering a restart already seen needs a correction with its reason", operation="planned_restart"),
    "update.check": _g(N, "runs the app-pushed reader now: fetches origin and asks CI; moves nothing that runs"),
    "jobs.job_finished": _g(N, "a host job ended: runs the job-health reader now; reads systemd and the stores, moves nothing, and accepts only a declared job's unit"),
    "netbox_v2.preview": _g(N, "starts a dry run of an import or removal, or a read of what Stop tracking would forget, on a thread; writes nothing"),
    "remote.verify": _g(N, "read-only checks against the remote"),
    "remote_v2.publication": _g(N, "reads what a first push would publish: counts, kinds and fingerprints, never a value; writes nothing"),
}

#: SocketIO events, which never reach ``before_request``. Empty since the break-glass
#: terminal's three events left with it (R39, 2026-10-05); a new socket event that mutates
#: is declared here and wrapped in `socket_gated`.
SOCKET_GATES = {}


def gate_for(endpoint: str):
    return GATES.get(endpoint)


def _refusal_response(refusal: dict, status: int = 403):
    from flask import jsonify
    return jsonify(refusal), status


def enforce():
    """``before_request``: refuse a mutating request its gate does not pass.

    Runs before the route, so before its input validation: an unidentified
    caller learns nothing about what a valid body would have been. That is
    the order today's onboarding Create (left at 7.8) already had.
    """
    from flask import g, request
    from modules import identity

    if request.method in SAFE_METHODS or request.endpoint is None:
        return None
    gate = GATES.get(request.endpoint)
    if gate is None:
        log.error("route_gates: %s %s is not classified; refused",
                  request.method, request.endpoint)
        return _refusal_response({
            "ok": False, "outcome": "unclassified",
            "error": (f"'{request.endpoint}' is not declared in the gate table "
                      "(modules/route_gates.py), so it is refused. Declaring it "
                      "is a code change, not a setting.")})
    if gate.kind == NOT_DEVICE:
        return None
    ident, refusal = identity.require(request, gate.kind, operation=gate.operation)
    if refusal is not None:
        log.info("route_gates: refused %s (%s): %s", request.endpoint, gate.kind,
                 refusal.get("outcome"))
        return _refusal_response(refusal)
    g.nmas_identity = ident
    return None


def socket_gated(event: str):
    """Decorator for a SocketIO handler: the same gate, by event name.

    A refusal is told to the requesting connection only, never to the room,
    and the handler does not run.
    """
    gate = SOCKET_GATES[event]

    def wrap(fn):
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            from flask import g, request
            from flask_socketio import emit
            from modules import identity

            if gate.kind != NOT_DEVICE:
                ident, refusal = identity.require(request, gate.kind,
                                                  operation=gate.operation)
                if refusal is not None:
                    log.info("route_gates: refused socket %s (%s): %s", event,
                             gate.kind, refusal.get("outcome"))
                    emit("gate_refused", {"event": event, "error": refusal.get("error")})
                    return None
                g.nmas_identity = ident
            return fn(*args, **kwargs)
        return inner
    return wrap


#: True once the gate is installed on an app, i.e. in the APP process. A CLI
#: on the host never installs it, which is how `identity.actor_verification`
#: tells a host shell from the app's own background threads.
_installed = False


def installed() -> bool:
    return _installed


def install(app) -> None:
    global _installed
    app.before_request(enforce)
    _installed = True
