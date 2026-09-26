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
    "save_config": _g(C, "runs write memory: changes the device's startup config"),
    "save_to_startup": _g(C, "copies running to startup: changes what the device boots"),
    "ai_chat": _g(C, "the assistant holds tools that push config until P.3 step 8 removes them"),
    "ai_agent_run": _g(C, "runs the background agent, which holds device tools until P.3 step 8"),

    # ---- approve: a decision a later device change acts on ---------------
    "ai_approval_approve": _g(A, "resolves an approval-queue item"),
    "ai_approval_approve_all": _g(A, "resolves every pending approval-queue item"),
    "ai_approval_reject": _g(A, "resolves an approval-queue item; a refusal is a decision too"),
    "templates.approve": _g(A, "approves a template for deployment"),
    "templates.revoke_approval": _g(A, "withdraws a template approval, with a recorded reason"),
    "templates.write_template": _g(A, "edits a template, which revokes every approval over it"),
    "templates.save_bindings": _g(A, "changes which template renders which device"),
    "templatize.commit_extraction": _g(A, "commits staged intent"),
    "templatize.edit_committed": _g(A, "commits an edit to intent"),
    "templatize.revert_committed": _g(A, "commits the inverse of an intent commit"),
    "templatize.bulk_apply": _g(A, "commits one change to many devices' intent"),
    "templatize.retry_rolled_back": _g(A, "lifts a rollback block so the change may be planned again"),
    "freshness.authorise": _g(A, "authorises one divergence past the freshness gate"),
    "golden_configs_save_all": _g(A, "commits captures as the approved goldens"),
    "golden_configs_auto_create": _g(A, "commits captures as the approved goldens"),
    "refresh_hostnames": _g(A, "renames devices and rewrites their goldens"),
    "git_commit": _g(A, "commits into the network's repository"),
    "onboard.create": _g(A, "commits a new device's identity and intent", "onboard_device"),
    "netbox_safety.apply_import": _g(A, "writes to NetBox"),
    "netbox_safety.apply_import_all": _g(A, "writes to NetBox"),
    "netbox_safety.apply_removal": _g(A, "deletes from NetBox"),
    "jenkins_webhook": _g(A, "records a CI result that the pipeline's CI stage consults; "
                             "unauthenticated, it could record a pass (P.4 removes it)"),
    "configure_pipeline_success": _g(A, "marks a change verified (Jenkins callback; P.4 removes it)"),

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
    "ai_restart": _g(K, "restarts the AI subsystem"),
    "server_restart": _g(K, "restarts the application"),
    "ai_delete_playbook": _g(K, "deletes a stored playbook"),
    "ai_events_clear": _g(K, "clears the event record"),
    "clear_netflow_flows": _g(K, "clears the collected flow record"),
    "clear_snmp_traps": _g(K, "clears the trap record"),
    "delete_backup_route": _g(K, "deletes a backup"),
    "add_device": _g(K, "adds an inventory row"),
    "add_discovered_devices": _g(K, "adds inventory rows"),
    "delete_device": _g(K, "removes an inventory row"),
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
    "jenkins_create_job_route": _g(K, "creates a Jenkins job (P.4 removes it)"),
    "jenkins_schedule_set": _g(K, "schedules a Jenkins job (P.4 removes it)"),
    "configure_build_pipelines": _g(K, "creates Jenkins pipelines (P.4 removes it)"),

    # ---- reveal: device configuration or secrets leave the device --------
    "bulk_tftp_download": _g(R, "copies files OFF devices to a TFTP server the form names"),
    "bulk_download_config": _g(R, "copies running or startup config to a TFTP server the form names"),
    "download_device_file": _g(R, "copies a file off a device to a TFTP server the form names"),

    # ---- publish_remote --------------------------------------------------
    "remote.push": _g(P, "publishes the repository"),
    "remote.auto_push": _g(P, "switches automatic publishing"),
    "remote.adopt": _g(P, "binds the list to a remote"),
    "remote.acknowledge": _g(P, "acknowledges the history scan before first publication"),
    "remote.verify_write": _g(P, "writes a probe to the remote"),

    # ---- not gated: reads, previews, tests, layout, the schedule's work --
    "deploy.plan": _g(N, "computes a program; sends nothing"),
    "golden.restore_preview": _g(N, "computes a restore program; sends nothing"),
    "golden.migrate_plan": _g(N, "a dry run"),
    "onboard.plan": _g(N, "builds a plan; creates nothing"),
    "templatize.bulk_preview": _g(N, "computes a preview; writes nothing"),
    "templatize.preview_committed_edit": _g(N, "renders an edit; writes nothing"),
    "templatize.extract": _g(N, "writes gitignored staging only"),
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
    "discover_subnet": _g(N, "probes a subnet and writes nothing; adding what it finds is gated"),
    "monitoring_snmp_poll": _g(N, "an SNMP read"),
    "jenkins_run": _g(N, "runs verification checks, which read (P.4 removes it)"),
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
