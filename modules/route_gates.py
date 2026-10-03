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
    (which holds intent, NSOT_PLAN 4.1), a freshness authorisation.
``configure``
    The tool's own settings, gates, inventory, credentials and local records.
``reveal``
    Exposes a secret or a device's configuration, to the caller or to a place
    the caller names (a TFTP copy off the device is a reveal).
``publish_remote``
    Publishes a network's history to a remote.
``break_glass``
    The terminal: typed commands with no plan, no hash and no rollback. Its
    own kind so its use is distinguishable from an ordinary deploy.
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
    "deploy.apply": _g(C, "pushes a confirmed program to devices"),
    "golden.restore_apply": _g(C, "re-applies a ref to devices through the deploy path"),
    "onboard.verify": _g(C, "reaches the device and rotates its credential",
                         "onboard_verify"),
    "onboard.abandon": _g(C, "deletes the device's records from NetBox and the repository",
                          "onboard_abandon"),
    "run_command": _g(C, "runs an exec-mode command a person typed on one device; exec mode "
                         "can copy, delete, reload and clear (B16: it was an ungated GET)"),
    "bulk_execute": _g(C, "sends ENABLE-mode commands to many devices (config mode cut in P.3 step 2); enable mode can still copy, delete, reload and erase"),
    "bulk_reload": _g(C, "reloads devices"),
    "bulk_tftp_upload": _g(C, "copies a file ONTO devices' flash (copy tftp: flash:)"),
    "bulk_delete_file": _g(C, "deletes files from devices' flash"),
    "upload_file": _g(C, "copies a file onto a device's flash"),
    "delete_file": _g(C, "deletes a file from a device's flash"),
    "rotate.apply": _g(C, "rotates a device's login credential: the device then accepts only the new password"),
    "device_v2.restore_confirm": _g(C, "re-applies a moment (its golden now, an older golden or a baseline) to one device from the v2 device page (7.3; THE restore plan and apply, run as a job, in the list its preview was drawn in, C396), merge-only, every line needing a reason (a dangerous line, an account added back) with its stated reason in the hash"),
    "device_v2.deploy_confirm": _g(C, "deploys a device's committed intent from the v2 device page (7.3; the same plan and apply as deploy.apply and the batch apply, run as a job), merge-only, with any line ticked for removal (Mode B) and every dangerous line's stated reason in the hash"),
    "device_v2.rotate_confirm": _g(C, "rotates a device's login credential from the v2 device page (7.3; the same confirm as rotate.apply): the device then accepts only the new password"),
    "v2.profile_apply_confirm": _g(C, "deploys the monitoring profile's confirmed programs to the chosen devices, one after another (P.9 d2)"),
    "persist.apply": _g(C, "saves the running config to startup on a device and reads it back: changes what the device boots"),
    "device_v2.persist_confirm": _g(C, "saves the running config to startup on a device and reads it back, from the v2 device page (7.3; the same apply as persist.apply)"),
    "update.apply": _g(C, "requests the Update: the root-owned updater moves the app to a CI-passed commit and restarts it"),
    "ai_chat": _g(C, "the assistant holds tools that push config until P.3 step 8 removes them"),
    "ai_agent_run": _g(C, "runs the background agent, which holds device tools until P.3 step 8"),

    # ---- approve: a decision a later device change acts on ---------------
    "ai_approval_approve": _g(A, "resolves an approval-queue item"),
    "ai_approval_approve_all": _g(N, "builds a capture handoff for the drift items; records nothing (C105): the capture apply, gated approve, does"),
    "ai_approval_reject": _g(A, "resolves an approval-queue item; a refusal is a decision too"),
    "templates.approve": _g(A, "approves a template for deployment"),
    "templates.revoke_approval": _g(A, "withdraws a template approval, with a recorded reason"),
    "templates.write_template": _g(A, "edits a template, which revokes every approval over it"),
    "templates.save_bindings": _g(A, "changes which template renders which device"),
    "retire.apply": _g(A, "retires a device: removes its intent and golden in a commit, declares its startup unmapped, clears its override and deletes its CSV row, the only stored copy of its credential"),
    "templatize.seed_apply": _g(A, "commits a device's first full intent, parsed from its committed golden"),
    "templatize.profile_propose_apply": _g(A, "commits the network's monitoring profile, intent every device inherits (P.9 step b)"),
    "v2.ip_sla_policy_set": _g(A, "commits the monitoring profile's IP SLA policy, which decides the probes suggested (P.9 d4)"),
    "v2.ip_sla_commit": _g(A, "commits suggested IP SLA probes into the devices' intent (P.9 d4)"),
    "v2.credentials_drill": _g(K, "records the offline drill's receipt, checked against a logged export (board 7, D)"),
    "v2.credentials_check": _g(K, "opens a kept break-glass file in memory and records the verdict per device; no value is shown, kept or logged (board 7, C)"),
    "v2.credentials_intact": _g(K, "records the browser's word on a break-glass download: its sha256 of the bytes received against the server's (board 7)"),
    "v2.heartbeat_apply": _g(K, "writes the re-measured heartbeat alert rules file (P.7); a person installs it on the host"),
    "templatize.edit_committed": _g(A, "commits an edit to intent"),
    "templatize.revert_apply": _g(A, "commits the inverse of one intent commit's change"),
    "templatize.bulk_apply": _g(A, "commits one change to many devices' intent"),
    "device_v2.revert_confirm": _g(A, "commits the inverse of one intent commit's change from the v2 device page (7.3, board 11; the same apply as templatize.revert_apply, in the list its card carries)"),
    "device_v2.retry_confirm": _g(A, "lifts a blocked change so it may be sent again, with a stated reason, from the v2 device page (7.3, board 11; the same apply as templatize.retry_apply, in the list its card carries)"),
    "device_v2.seed_confirm": _g(A, "commits a device's first full intent, parsed from its committed golden, from the v2 device page (7.3, board 8; the same apply as templatize.seed_apply, in the list its card carries)"),
    "templatize.retry_apply": _g(A, "lifts a blocked change (the lines a rollback undid) so it may be sent again"),
    "freshness.authorise": _g(A, "authorises one divergence past the freshness gate"),
    # Capture (7.1 step 4, C82, C89): Save All is its whole-fleet form, and
    # the old one-click route is gone, because nothing in it asked whether the
    # state being enshrined was the one intended.
    "golden.capture_apply": _g(A, "commits confirmed captures as the approved goldens"),
    "device_v2.capture_confirm": _g(A, "commits a device's confirmed capture as its golden, from the v2 device page (7.3; the same apply as golden.capture_apply)"),
    "refresh_hostnames": _g(A, "renames devices and records a pending golden rename"),
    "onboard.create": _g(A, "commits a new device's identity and intent", "onboard_device"),
    "netbox_safety.apply_import": _g(A, "writes to NetBox"),
    "netbox_safety.apply_import_all": _g(A, "writes to NetBox"),
    "netbox_safety.apply_removal": _g(A, "deletes from NetBox"),

    # ---- configure: the tool's own settings, gates, inventory, records ---
    "save_settings": _g(K, "writes settings, secrets included"),
    "settings_integrations.general_settings": _g(K, "writes settings"),
    "settings_integrations.save_integration": _g(K, "writes an integration's settings and secrets"),
    "identity.ratify_setting": _g(K, "records a decision about a gate", "ratify_setting"),
    "drift_settings_post": _g(K, "switches the drift checker and its interval"),
    "monitoring_config": _g(K, "writes collector settings"),
    "save_tftp_server": _g(K, "writes the TFTP server setting"),
    "ai_set_provider": _g(K, "switches the AI provider"),
    "ai_agent_timers_post": _g(K, "changes when the background agent runs"),
    "ai_agent_pause": _g(K, "pauses the background agent"),
    "ai_agent_resume": _g(K, "resumes the background agent"),
    "ai_delete_playbook": _g(K, "deletes a stored playbook"),
    "ai_events_clear": _g(K, "clears the event record"),
    "clear_netflow_flows": _g(K, "clears the collected flow record"),
    "clear_snmp_traps": _g(K, "clears the trap record"),
    "delete_backup_route": _g(K, "deletes a backup"),
    "reorder_devices": _g(K, "reorders the inventory"),
    "create_device_list_route": _g(K, "creates a device list"),
    "delete_device_list_route": _g(K, "deletes a device list"),
    "select_device_list_route": _g(K, "changes the active list, which every derived read and the ping worker follow"),
    "inventory.set_source": _g(K, "changes where a list's inventory comes from"),
    "inventory.set_order": _g(K, "reorders a list"),
    "inventory.credential_profiles": _g(K, "writes credential profiles"),
    "inventory.delete_credential_profile": _g(K, "deletes a credential profile"),
    "inventory.copy_inherited": _g(K, "copies inherited credentials into device overrides"),
    "list_variables_set": _g(K, "writes list variables"),
    "list_variables_delete": _g(K, "deletes a list variable"),
    "list_variables_discover": _g(K, "reads devices and WRITES list variables"),
    "list_compliance_policy_update": _g(K, "writes the compliance policy"),
    "add_quick_action": _g(K, "stores a canned command"),
    "delete_quick_action": _g(K, "deletes a canned command"),
    "golden.migrate_apply": _g(K, "one-shot migration of the golden store"),
    "golden.sync_renames": _g(K, "commits pending renames"),

    # ---- reveal: device configuration or secrets leave the device --------
    "bulk_tftp_download": _g(R, "copies files OFF devices to a TFTP server the form names"),
    "bulk_download_config": _g(R, "copies running or startup config to a TFTP server the form names"),
    "download_device_file": _g(R, "copies a file off a device to a TFTP server the form names"),
    "breakglass.export": _g(R, "every device's credential and the application key, sealed and sent to the browser"),

    # ---- publish_remote --------------------------------------------------
    "remote.push": _g(P, "publishes the repository"),
    "remote.auto_push": _g(P, "switches automatic publishing"),
    "remote.adopt": _g(P, "binds the list to a remote"),
    "remote.acknowledge": _g(P, "acknowledges the history scan before first publication"),
    "remote.verify_write": _g(P, "writes a probe to the remote"),

    # ---- not gated: reads, previews, tests, layout, the schedule's work --
    "deploy.plan": _g(N, "computes a program; sends nothing"),
    "golden.restore_preview": _g(N, "computes a restore program; sends nothing"),
    "device_v2.rotate_preview": _g(N, "reads the device's account line live for the rotation's plan, from the v2 device page (the same plan as rotate.preview); changes nothing"),
    "device_v2.capture_start": _g(N, "starts the capture preview's read of one device, from the v2 device page (the same job as golden.capture_preview); records nothing"),
    "golden.capture_preview": _g(N, "reads each device's running config and computes a "
                                    "capture preview; records nothing"),
    "golden.migrate_plan": _g(N, "a dry run"),
    "onboard.plan": _g(N, "builds a plan; creates nothing"),
    "onboard.verify_preview": _g(N, "reads the pending device and computes what Verify would "
                                    "send (P.9 step c); sends nothing"),
    "templatize.bulk_preview": _g(N, "computes a preview; writes nothing"),
    "templatize.preview_committed_edit": _g(N, "renders an edit; writes nothing"),
    "retire.preview": _g(N, "computes the retire plan and reads the export log; writes nothing"),
    "rotate.preview": _g(N, "computes the rotation plan and READS the device's account line; changes nothing"),
    "breakglass.preview": _g(N, "names the devices and the key's fingerprint an export would hold; reveals no value"),
    "persist.preview": _g(N, "computes the persist plan from the inventory and the startup check's record; contacts no device and writes nothing"),
    "update.step_done": _g(C, "records that a person did a host step the tool cannot check: the release's record of what was done on the host"),
    "attention.acknowledge": _g(K, "records that a person acknowledged one event row on Needs attention, with a reason; the row leaves the page and the event stays in its record"),
    "restarts.planned": _g(K, "records a planned-restart window, so the restarts it covers are not reported as unexpected; a window covering a restart already seen needs a correction with its reason", operation="planned_restart"),
    "update.check": _g(N, "runs the app-pushed reader now: fetches origin and asks CI; moves nothing that runs"),
    "jobs.job_finished": _g(N, "a host job ended: runs the job-health reader now; reads systemd and the stores, moves nothing, and accepts only a declared job's unit"),
    "templatize.seed_preview": _g(N, "parses committed goldens from git; writes nothing"),
    "templatize.profile_propose_preview": _g(N, "reads committed intent and compares stored values in memory; writes nothing"),
    "templatize.revert_preview": _g(N, "computes a revert from git; writes nothing"),
    "templatize.retry_preview": _g(N, "reads the rollback record and the retry log; writes nothing"),
    "templatize.report": _g(N, "reads goldens; opens no session and writes nothing"),
    "templates.preview": _g(N, "renders; writes nothing"),
    "templates.validate": _g(N, "validates; writes nothing"),
    "templates.refresh_capture": _g(N, "reads a device into a backup"),
    "netbox_safety.preview_import": _g(N, "a dry run"),
    "netbox_safety.preview_import_all": _g(N, "a dry run"),
    "netbox_safety.preview_removal": _g(N, "a dry run"),
    "netbox_test_connection": _g(N, "a connection test"),
    "settings_integrations.test_integration": _g(N, "a connection test"),
    "remote.verify": _g(N, "read-only checks against the remote"),
    "freshness.gate": _g(N, "a comparison; the clab sync calls it unattended"),
    "drift_check_trigger": _g(N, "the schedule does this anyway; it only happens earlier"),
    "drift_check_sync": _g(N, "the schedule does this anyway; it only happens earlier"),
    "inventory.refresh": _g(N, "the refresh interval does this anyway; it only happens earlier"),
    "backup_config": _g(N, "reads a device into a new local backup"),
    "compare_backups_route": _g(N, "compares two backups"),
    "refresh_files": _g(N, "lists a device's flash"),
    "monitoring_snmp_poll": _g(N, "an SNMP read"),
    "bulk_clear": _g(N, "clears a finished operation's on-screen result"),
    "ai_stop": _g(N, "stops a running request; refusing a stop is the unsafe direction"),
    "ai_clear": _g(N, "clears the caller's chat history"),
    "topology_save_positions": _g(N, "layout"),
    "topology_save_hidden": _g(N, "layout"),
    "topology_save_proto_positions": _g(N, "layout"),
    "topology_save_proto_hidden": _g(N, "layout"),
}

#: SocketIO events, which never reach ``before_request``.
SOCKET_GATES = {
    "connect_terminal": _g("break_glass", "opens a live device shell"),
    "terminal_input": _g("break_glass", "types into a live device shell"),
    "disconnect_terminal": _g(N, "closes a shell; refusing a close is the unsafe direction"),
}


def gate_for(endpoint: str):
    return GATES.get(endpoint)


def _refusal_response(refusal: dict, status: int = 403):
    from flask import jsonify
    return jsonify(refusal), status


def enforce():
    """``before_request``: refuse a mutating request its gate does not pass.

    Runs before the route, so before its input validation: an unidentified
    caller learns nothing about what a valid body would have been. That is
    the order ``/onboard/create`` already had.
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
                    if gate.kind == "break_glass":
                        # An attempt on the break-glass path is a fact too.
                        from modules import terminal_audit
                        payload = args[0] if args and isinstance(args[0], dict) else {}
                        terminal_audit.record(
                            terminal_audit.REFUSED,
                            device_ip=str(payload.get("ip", "")),
                            actor=getattr(ident, "actor", ""),
                            kind=getattr(ident, "kind", ""),
                            sid=getattr(request, "sid", ""),
                            peer=identity.peer_address(request),
                            reason=str(refusal.get("outcome", "")))
                    emit("terminal_output",
                         {"output": f"\r\n[refused: {refusal.get('error')}]\r\n"})
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
