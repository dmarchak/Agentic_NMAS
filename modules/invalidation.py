"""What each mutating route invalidates (Stage 7.0; NSOT_STAGE7_GUI.md 6b).

**An action that changes state leaves the page showing the new state.**
Onboarding's Verify promoted a device and the device list still read
`0 devices` until a manual reload; a golden commit left the Remote card
showing the previous push; a drift run left the badge showing the last one.
Each was fixed as its own bug, which is how the fourth ends up written into
whatever ships next.

So the rule is structural. Every mutating route declares the DATA it
changes, from a finite vocabulary, or `Nothing` with a reason, and its
response carries the declaration:
- in the ``X-NMAS-Invalidates`` header, on every response;
- as ``invalidates`` in the body when that body is a JSON object.

Panels subscribe to keys (`static/js/nmas_invalidation.js`) and re-fetch on
the RESPONSE, never on a timer: a response means the write is done.

**The declaration names data, not panels.** The panel that issued a call is
usually not the one that is now wrong (Verify lives in the pending banner;
what went stale was the device list). And **declaring too much costs one
spare re-fetch, while declaring too little is the defect**, so an uncertain
route declares the data it plausibly touches.

**A change the server makes AFTER a response, or on its own schedule, is
ANNOUNCED** (C58): a response header cannot carry it, because no response
is in flight when a background job finishes. `announce()` sends the same
keys over the page's Socket.IO connection, and the client dispatches them
through the same registry, so a panel subscribes once and hears both. The
keys come from the same vocabulary, checked at the call. The first caller is
the reader-job pattern (`modules/reader_job.py`, rule 9); an announcement is
never a timer's.

The population is `app.url_map`, not a list kept here: every rule with a
mutating method. `test_invalidation_map.py` fails on an undeclared one, on
a declaration for a route that no longer exists, and on a key outside the
vocabulary.
"""

import json
import logging
import time
from typing import NamedTuple

log = logging.getLogger(__name__)

HEADER = "X-NMAS-Invalidates"
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class Nothing(NamedTuple):
    """This route changes no displayed data. The reason is required, because
    "nothing" is a claim and an unexplained one cannot be checked."""
    reason: str


#: The data keys. A key names what changed, never where it is drawn.
VOCABULARY = {
    "inventory": "the devices in a list: rows, counts, online state",
    "lists": "the set of device lists",
    "active_list": "which list the page shows; everything on it",
    "goldens": "golden configs and their history",
    "intent": "committed intent (host_vars)",
    "staging": "extraction's staged host_vars",
    "templates": "the template library, bindings and template approvals",
    "baselines": "baseline tags",
    "remote": "the remote: its push state and verification",
    "drift": "the drift checker's state and last run",
    "approvals": "the approval queue",
    "pending": "pending onboardings",
    "rolled_back": "blocked changes (what a rollback undid) and retry authorisations",
    "credentials": "credential profiles and device overrides",
    "netbox": "the NetBox objects NMAS shows or counts",
    "settings": "settings and integrations",
    "posture": "the identity gates' recorded posture",
    "freshness": "Oxidized freshness authorisations",
    "backups": "stored backups of device configs",
    "device_state": "what a device runs: anything read live from it",
    "device_files": "a device's filesystem listing",
    "files": "files on this host from device transfers",
    "agent": "the background agent: status, log, timers",
    "chat": "the AI chat transcript",
    "playbooks": "AI playbooks",
    "quick_actions": "quick actions",
    "monitoring": "the SNMP and NetFlow collectors",
    "topology": "the topology layout",
    "variables": "the CSV-era variable store and compliance policy",
    "bulk_ops": "bulk operation records",
}

_COMMIT = ("goldens", "remote")        # a golden commit also moves the remote's state

#: endpoint -> keys, or Nothing(reason).
DECLARED = {
    # Inventory and lists.
    "reorder_devices": ("inventory",),
    "refresh_hostnames": ("inventory", "goldens"),   # a pending golden rename
    "inventory.refresh": ("inventory",),
    "inventory.set_order": ("inventory",),
    "inventory.set_source": ("inventory", "lists"),
    "create_device_list_route": ("lists",),
    "delete_device_list_route": ("lists", "active_list"),
    "select_device_list_route": ("active_list",),
    # Credentials.
    "inventory.copy_inherited": ("credentials",),
    "inventory.credential_profiles": ("credentials",),
    "inventory.delete_credential_profile": ("credentials",),
    # Goldens, the repository and the remote.
    # Capture (7.1 step 4): Save All is now the whole-fleet form of it.
    "golden.capture_apply": _COMMIT + ("baselines", "drift", "approvals"),   # closes handed-off drift items
    "golden.migrate_apply": _COMMIT,
    "golden.sync_renames": _COMMIT,
    "golden.restore_apply": ("device_state", "intent", "baselines", "drift",
                             "approvals", "rolled_back") + _COMMIT,
    "remote.acknowledge": ("remote",),
    "remote.adopt": ("remote",),
    "remote.auto_push": ("remote",),
    "remote.push": ("remote",),
    "remote.verify": ("remote",),
    "remote.verify_write": ("remote",),
    # Intent, templates and deploys.
    "templatize.extract": ("staging",),
    "templatize.commit_extraction": ("intent", "staging", "remote"),
    "templatize.edit_committed": ("intent", "remote"),
    "templatize.revert_committed": ("intent", "remote"),
    "templatize.bulk_apply": ("intent", "remote"),
    "templatize.retry_rolled_back": ("rolled_back",),
    "templates.write_template": ("templates", "remote"),
    "templates.approve": ("templates", "remote"),
    "templates.revoke_approval": ("templates", "remote"),
    "templates.save_bindings": ("templates", "remote"),
    "templates.refresh_capture": ("backups",),
    "deploy.apply": ("device_state", "baselines", "drift", "rolled_back",
                     "freshness") + _COMMIT,
    # Onboarding. Verify runs phase 2, which PROMOTES: the device list is the
    # first of the three measured cases.
    "onboard.create": ("pending", "intent", "credentials", "remote"),
    "onboard.verify": ("pending", "inventory", "credentials", "netbox",
                       "device_state", "baselines") + _COMMIT,
    "onboard.abandon": ("pending", "intent", "credentials", "remote"),
    # Drift. The badge after a run is the third measured case.
    "drift_check_sync": ("drift",),
    "drift_check_trigger": ("drift",),
    "drift_settings_post": ("drift",),
    # Approvals and the agent.
    "ai_approval_approve": ("approvals",),
    "ai_approval_approve_all": Nothing("builds a capture handoff and records nothing (C105); the capture apply closes the items"),
    "ai_approval_reject": ("approvals",),
    "ai_agent_run": ("agent", "approvals"),
    "ai_agent_pause": ("agent",),
    "ai_agent_resume": ("agent",),
    "ai_agent_timers_post": ("agent",),
    "ai_events_clear": ("agent",),
    "ai_restart": ("agent",),
    "ai_chat": ("chat", "approvals"),
    "ai_clear": ("chat",),
    "ai_stop": ("chat",),
    "ai_delete_playbook": ("playbooks",),
    "ai_set_provider": ("settings",),
    # NetBox.
    "netbox_safety.apply_import": ("netbox",),
    "netbox_safety.apply_import_all": ("netbox",),
    "netbox_safety.apply_removal": ("netbox",),
    # Measured: persists the auth scheme that worked when the stored token is
    # the one tested. A test that writes is declared as the write it is.
    "netbox_test_connection": ("settings",),
    # Settings, posture and the collectors.
    "save_settings": ("settings",),
    "save_tftp_server": ("settings",),
    "settings_integrations.general_settings": ("settings",),
    "settings_integrations.save_integration": ("settings",),
    "identity.ratify_setting": ("posture", "settings"),
    "freshness.authorise": ("freshness",),
    "monitoring_config": ("monitoring",),
    "monitoring_snmp_poll": ("monitoring",),
    "clear_netflow_flows": ("monitoring",),
    "clear_snmp_traps": ("monitoring",),
    # A device, its files and backups.
    "run_command": ("device_state",),
    "save_config": ("device_state",),
    "save_to_startup": ("device_state",),
    "bulk_execute": ("device_state",),
    "bulk_reload": ("device_state", "inventory"),
    "backup_config": ("backups",),
    "delete_backup_route": ("backups",),
    "upload_file": ("device_files",),
    "delete_file": ("device_files",),
    "refresh_files": ("device_files",),
    "bulk_delete_file": ("device_files",),
    "bulk_tftp_upload": ("device_files",),
    "download_device_file": ("files",),
    "bulk_download_config": ("files",),
    "bulk_tftp_download": ("files",),
    # The rest of the page's own state.
    "add_quick_action": ("quick_actions",),
    "delete_quick_action": ("quick_actions",),
    "topology_save_hidden": ("topology",),
    "topology_save_positions": ("topology",),
    "topology_save_proto_hidden": ("topology",),
    "topology_save_proto_positions": ("topology",),
    "list_variables_set": ("variables",),
    "list_variables_delete": ("variables",),
    "list_variables_discover": ("variables",),
    "list_compliance_policy_update": ("variables",),
    "bulk_clear": ("bulk_ops",),
    # Reads sent as POST: a body carries the question, and nothing is stored.
    "deploy.plan": Nothing("a plan reads and computes; its host_vars write was removed (C33)"),
    "golden.capture_preview": Nothing("reads each device's running config and computes a "
                                      "preview; it records nothing"),
    "onboard.plan": Nothing("a plan reads and computes; its templates write was removed (C33)"),
    "golden.restore_preview": Nothing("a preview computes the program a restore would send"),
    "golden.migrate_plan": Nothing("the migration's dry run; it writes nothing by design"),
    "templates.preview": Nothing("renders and diffs captured artifacts; opens no session"),
    "templates.validate": Nothing("validates a template against captures and reports"),
    "templatize.preview_committed_edit": Nothing("previews an intent edit against HEAD"),
    "templatize.bulk_preview": Nothing("previews a bulk intent change; the apply commits"),
    "templatize.report": Nothing("round-trip coverage computed from goldens; writes nothing"),
    "netbox_safety.preview_import": Nothing("a NetBox dry run: reads, and issues a one-shot token"),
    "netbox_safety.preview_import_all": Nothing("a NetBox dry run: reads, and issues a one-shot token"),
    "netbox_safety.preview_removal": Nothing("a NetBox dry run: reads, and issues a one-shot token"),
    "settings_integrations.test_integration": Nothing("tests an integration's connection and reports"),
    "compare_backups_route": Nothing("diffs two stored backups and returns the diff"),
    "freshness.gate": Nothing("the sanitiser's check: per-device verdicts, stored nowhere"),
    "server_restart": Nothing("no caller (reachability group d); the process restarts, so "
                              "nothing this process answers is left to act on"),
}


def mutating_endpoints(app) -> set:
    """Every endpoint with a mutating method, from the app's own map."""
    return {r.endpoint for r in app.url_map.iter_rules()
            if (r.methods or set()) & MUTATING_METHODS and r.endpoint != "static"}


def undeclared(app) -> list:
    """Mutating endpoints with no declaration: the finding this exists for."""
    return sorted(mutating_endpoints(app) - set(DECLARED))


def ghost_declarations(app) -> list:
    """Declarations for endpoints the app no longer serves."""
    return sorted(set(DECLARED) - mutating_endpoints(app))


def keys_in_use() -> set:
    """Keys a route declares or a reader job announces (C58): both are
    senders, and a panel subscribed to either hears it."""
    from modules import reader_job
    return ({k for v in DECLARED.values() if not isinstance(v, Nothing) for k in v}
            | {k for r in reader_job.readers() for k in r.invalidates})


def keys_for(endpoint: str) -> tuple:
    declared = DECLARED.get(endpoint)
    if declared is None or isinstance(declared, Nothing):
        return ()
    return tuple(declared)


#: The event name the page listens for. One name, read by the client
#: (static/js/nmas_invalidation.js) and pinned by a test against it.
ANNOUNCE_EVENT = "nmas_invalidate"

_emitter = None


def set_emitter(emit) -> None:
    """The app hands over its socket's emit once, at import (no thread)."""
    global _emitter
    _emitter = emit


def announce(keys, by: str, ok: bool = True) -> dict:
    """Tell every open page that the data under *keys* changed, and who
    changed it. Raises when it cannot: the caller counts it (a reader counts
    a failed announcement and keeps its value), and nothing pretends it was
    heard. The message carries key NAMES only, never data, because it goes
    to every connection."""
    keys = list(keys)
    unknown = [k for k in keys if k not in VOCABULARY]
    if not keys or unknown:
        raise ValueError(f"announce({by!r}): keys outside the vocabulary: {unknown or 'none given'}")
    if _emitter is None:
        raise RuntimeError("no emitter: announcements need the app's socket, and this process "
                           "has none")
    msg = {"keys": keys, "by": by, "ok": bool(ok),
           "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    _emitter(ANNOUNCE_EVENT, msg)
    return msg


def install(app) -> None:
    """Attach the declaration to every response of a declared route."""

    @app.after_request
    def _declare_invalidations(response):
        from flask import request

        # By METHOD as well as endpoint: one Flask endpoint can serve both a
        # read and a write (`monitoring_config` is GET and POST), and keying
        # on the endpoint alone made every READ of that panel announce an
        # invalidation and changed its response (found measuring payloads
        # for 7.0 (3); a read-only endpoint could not show it).
        if request.method not in MUTATING_METHODS:
            return response
        # An identity refusal is made by the gate BEFORE any view runs, so
        # nothing can have changed, and a refusal announcing an invalidation
        # is a claim about a write that did not happen (found by the payload
        # check, whose fixture was refused and carried `invalidates`).
        if response.status_code in (401, 403):
            return response
        keys = keys_for(request.endpoint or "")
        if not keys:
            return response
        response.headers[HEADER] = ",".join(keys)
        if response.mimetype == "application/json" and not response.direct_passthrough:
            try:
                body = json.loads(response.get_data(as_text=True))
            except ValueError:
                return response
            if isinstance(body, dict) and "invalidates" not in body:
                body["invalidates"] = list(keys)
                response.set_data(json.dumps(body))
        return response
