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
    "templates": "the template library, bindings and template approvals",
    "baselines": "baseline tags",
    "adjacencies": "the routing adjacencies intent implies, against what each device reports (C38)",
    "lab_startup": "each lab startup file against what its committed golden would produce",
    "restarts": "a device restart the restarts reader found, planned or not (modules/restarts.py)",
    "acknowledgements": "a person acknowledged a Needs attention event row (modules/acknowledgements.py)",
    "remote": "the remote: its push state and verification",
    "drift": "the drift checker's state and last run",
    "approvals": "the approval queue",
    "pending": "pending onboardings",
    "rolled_back": "blocked changes (what a rollback undid) and retry authorisations",
    "credentials": "credential profiles and device overrides",
    "netbox": "the NetBox objects Mercury shows or counts",
    "settings": "settings and integrations",
    "posture": "the identity gates' recorded posture",
    "freshness": "Oxidized freshness: the stored comparison and its authorisations",
    "backups": "stored backups of device configs",
    "device_state": "what a device runs: anything read live from it",
    "breakglass": "the break-glass export log, its intact checks and its drills (job health's "
                  "break-glass rows read them)",
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
    "job_health": "job-health rows, as the job-health reader last stored them",
    "alerts": "Grafana's alert rules and instances, as the grafana-alerts reader last stored them",
    "dashboards": "Grafana's dashboards and their models, as the grafana-dashboards reader last stored them",
    "reachability": "whether each device answers, as the reachability reader last stored it",
    "integration_health": "whether each integration answers, as the integration-health reader last stored it",
    "credential_health": "each credential's expiry or age, as the credential-health reader last stored it (P.21)",
    "coverage_reporting": "when each device's monitoring data last arrived, as the coverage-reporting reader last stored it (Coverage's not-reporting cells)",
    "ci_verdict": "the running commit's CI verdict, as the ci-verdict reader last stored it",
    "app_version": "whether the running commit is what is pushed (origin/main), as the "
                   "app-pushed reader last stored it",
    "capture_preview": "a capture preview's device reads: finished, and its preview ready to read by id",
    "reads": "a Show commands run (Ask the device, Show commands): finished, its answers ready by id",
    "rotation": "a credential rotation run from the Device page: finished, its result ready to read by id",
    "privileged": "a Tier 2 command run from the Device page (Run a privileged command…): finished, its record ready to read by id",
    "device_holds": "an operation the app ran released a device: a card refused because it was held reads again",
    "device_progress": "an operation the app ran on a held device reached its next step: a running card redraws its stepper (C370)",
    "deploy_job": "a batch deploy run as a job (the v2 profile Apply): a device finished, or the batch, "
                  "its progress and result ready to read by id",
}

#: Announcers that are not reader jobs (C188 step 2): a background job a
#: request started, announcing when it finishes. Declared here so the keys
#: they send are senders to `keys_in_use`, exactly as a reader's are.
ANNOUNCERS = {
    "capture-preview": ("capture_preview",),   # modules/nsot/capture_job.py
    "show-commands": ("reads",),               # modules/nsot/reads.py: a run's end
    "rotation": ("rotation",),                 # modules/nsot/rotate_op.py
    "privileged": ("privileged",),             # modules/nsot/privileged.py: a Tier 2 run's end
    "device-ops": ("device_holds", "device_progress"),  # modules/nsot/device_ops.py: each release, each step
    # modules/deploy_job.py: each device finishing, and at the end what a
    # deploy changes (as /deploy/apply declares).
    # A restore run as a job (the v2 device page) also moves intent and approvals.
    # modules/arrival_watch.py: the combined deploy's watch, as each first arrival lands.
    "arrival-watch": ("deploy_job",),
    # modules/nsot/repo.save_templates: each template-library commit (C516).
    "template-library": ("templates",),
    "deploy-job": ("deploy_job", "device_state", "baselines", "drift", "rolled_back",
                   "freshness", "goldens", "remote", "intent", "approvals"),
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
    "device_v2.capture_confirm": _COMMIT + ("baselines", "drift", "approvals"),   # the same apply
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
    "retire.apply": ("inventory", "goldens", "intent", "credentials", "settings", "remote"),
    "templatize.seed_apply": ("intent", "remote"),
    "templatize.profile_propose_apply": ("intent", "remote"),
    "v2.ip_sla_policy_set": ("intent", "remote"),
    "v2.ip_sla_commit": ("intent", "remote"),
    "v2.heartbeat_apply": Nothing("writes the generated heartbeat rules file, which no panel reads; the page redraws itself, and nothing alerts differently until a person installs it on the host"),
    "templatize.edit_committed": ("intent", "remote"),
    "intent_v2.commit": ("intent", "remote"),
    # A read writes only its run's record; its end is the job's announcement (`reads`).
    "reads_v2.ask_run": ("reads",),
    "reads_v2.show_commands_run": ("reads",),
    # A saved set is drawn by Show commands' pick card, which the response redraws itself.
    "reads_v2.logging_path_run": ("reads",),
    "privileged_v2.preview": ("reads",),
    "privileged_v2.confirm": ("privileged",),
    "reads_v2.show_commands_ignore": ("reads",),
    "reads_v2.show_commands_save_set": ("reads",),
    "templates_v2.approve": ("templates", "remote"),
    "templates_v2.revoke": ("templates", "remote"),
    "templates_v2.bring": ("templates", "remote"),
    "v2.profile_propose_commit": ("intent", "remote"),
    "templatize.revert_apply": ("intent", "remote", "rolled_back"),
    "templatize.bulk_apply": ("intent", "remote"),
    "templatize.retry_apply": ("rolled_back",),
    "device_v2.revert_confirm": ("intent", "remote", "rolled_back"),
    "device_v2.retry_confirm": ("rolled_back",),
    "device_v2.seed_confirm": ("intent", "remote"),
    "device_v2.retire_confirm": ("inventory", "goldens", "intent", "credentials", "settings", "remote"),
    "device_v2.retire_finish": ("job_health",),
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
    "settings_v2.group_switch": ("settings",),
    "settings_v2.mode_switch": ("settings",),
    "identity.ratify_setting": ("posture", "settings"),
    "freshness.authorise": ("freshness",),
    "monitoring_config": ("monitoring",),
    "monitoring_snmp_poll": ("monitoring",),
    "clear_netflow_flows": ("monitoring",),
    "clear_snmp_traps": ("monitoring",),
    # A device, its files and backups.
    "run_command": ("device_state",),
    "persist.apply": ("device_state",),
    "device_v2.persist_confirm": ("device_state",),   # the same apply
    # The Update button: a request is written now; the version moves when the
    # root-owned updater acts, and the page waits on /health for it.
    "update.apply": ("app_version",),
    "update.step_done": ("app_version",),
    "attention.acknowledge": ("acknowledgements",),
    "restarts.planned": ("restarts",),
    # C539: each writes a log job health's break-glass rows read, so it wakes that reader.
    "v2.credentials_drill": ("breakglass",),
    "v2.credentials_check": Nothing("appends the check's verdict to its own log, which History "
                                    "reads; the answer is the verdict, drawn in place"),
    "v2.credentials_intact": ("breakglass",),
    "breakglass.export": ("breakglass",),
    "v2.profile_apply_confirm": Nothing("starts a job and answers at once; the batch deploys and ANNOUNCES deploy_job as each device finishes, and what a deploy changes at the end (ANNOUNCERS)"),
    "rotate.apply": Nothing("starts a job and answers at once; the job changes the credential and ANNOUNCES rotation when it finishes (ANNOUNCERS)"),
    "device_v2.restore_confirm": Nothing("starts a job and answers at once; the restore ANNOUNCES deploy_job as it finishes, and what a restore changes (ANNOUNCERS deploy-job)"),
    "device_v2.deploy_confirm": Nothing("starts a job and answers at once; the deploy ANNOUNCES deploy_job as it finishes, and what a deploy changes (ANNOUNCERS)"),
    "device_v2.rotate_confirm": Nothing("the same confirm as rotate.apply: starts the job and answers at once; the job ANNOUNCES rotation when it finishes (ANNOUNCERS)"),
    "device_v2.rotate_preview": Nothing("reads the device's account line live and computes the plan; it writes nothing"),
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
    "golden.capture_preview": Nothing("starts a job that reads each device's running config "
                                      "and computes a preview; it records nothing, and the "
                                      "job ANNOUNCES capture_preview when it finishes "
                                      "(ANNOUNCERS, C188)"),
    "device_v2.capture_start": Nothing("starts the same capture preview job for one device "
                                       "(golden.capture_preview); it records nothing, and the "
                                       "job ANNOUNCES capture_preview when it finishes"),
    "onboard.plan": Nothing("a plan reads and computes; its templates write was removed (C33)"),
    "onboard.verify_preview": Nothing("reads one device and computes what Verify would send; "
                                      "it writes nothing"),
    "golden.restore_preview": Nothing("a preview computes the program a restore would send"),
    "golden.migrate_plan": Nothing("the migration's dry run; it writes nothing by design"),
    "templates.preview": Nothing("renders and diffs captured artifacts; opens no session"),
    "templates.validate": Nothing("validates a template against captures and reports"),
    "templatize.preview_committed_edit": Nothing("previews an intent edit against HEAD"),
    "intent_v2.check": Nothing("checks and renders an intent edit as it is typed"),
    "intent_v2.acknowledge": Nothing("rewrites the editor's document; the commit writes it"),
    "intent_v2.reopen": Nothing("opens the editor again; writes nothing"),
    "breakglass.preview": Nothing("names the devices and the key's fingerprint an export "
                                  "would hold; writes nothing"),
    "rotate.preview": Nothing("computes the rotation plan and reads the device's account line; writes nothing"),
    "persist.preview": Nothing("computes the persist plan from the inventory and the "
                               "startup check's record; contacts no device and writes nothing"),
    "update.check": Nothing("starts the app-pushed reader, which announces app_version itself "
                            "when it finishes"),
    "jobs.job_finished": Nothing("starts the job-health reader, which announces job_health "
                                 "itself when it finishes"),
    "retire.preview": Nothing("computes the retire plan from the repository, the CSV, the credential store, the settings and the export log; writes nothing"),
    "templatize.revert_preview": Nothing("computes the revert of one intent commit from git; "
                                         "writes nothing"),
    "templatize.retry_preview": Nothing("reads the rollback record and the retry log; writes "
                                        "nothing"),
    "templatize.seed_preview": Nothing("parses committed goldens from git and computes the "
                                       "intent a seed would commit; writes nothing"),
    "templatize.profile_propose_preview": Nothing("computes the network's monitoring profile "
                                                  "from committed intent; writes nothing"),
    "templatize.bulk_preview": Nothing("previews a bulk intent change; the apply commits"),
    "templatize.report": Nothing("round-trip coverage computed from goldens; writes nothing"),
    "netbox_safety.preview_import": Nothing("a NetBox dry run: reads, and issues a one-shot token"),
    "netbox_safety.preview_import_all": Nothing("a NetBox dry run: reads, and issues a one-shot token"),
    "netbox_safety.preview_removal": Nothing("a NetBox dry run: reads, and issues a one-shot token"),
    "settings_integrations.test_integration": Nothing("tests an integration's connection and reports"),
    "compare_backups_route": Nothing("diffs two stored backups and returns the diff"),
    "freshness.gate": Nothing("the sanitiser's check: per-device verdicts, stored nowhere"),
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
            | {k for r in reader_job.readers() for k in r.invalidates}
            | {k for keys in ANNOUNCERS.values() for k in keys})


def keys_for(endpoint: str) -> tuple:
    declared = DECLARED.get(endpoint)
    if declared is None or isinstance(declared, Nothing):
        return ()
    return tuple(declared)


#: The event name the page listens for. One name, read by the client
#: (static/js/nmas_invalidation.js) and pinned by a test against it.
ANNOUNCE_EVENT = "nmas_invalidate"

_emitter = None

#: The channel's heartbeat. The page names a dead socket when none arrives
#: for 2.5 intervals. 30 s is half the fastest reader's interval (60 s,
#: Grafana's rule evaluation): the channel is judged faster than the fastest
#: data it carries, so "live updates stopped" is drawn within 75 s.
HEARTBEAT_EVENT = "nmas_heartbeat"
HEARTBEAT_SECONDS = 30


def heartbeat_message() -> dict:
    return {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "interval_seconds": HEARTBEAT_SECONDS}


def heartbeat_loop(sleep, beats: int = None) -> int:
    """Send the heartbeat for ever (or *beats* times, for tests). A beat that
    cannot be sent is logged and the loop goes on: the page names the
    silence, which is the point. Returns the beats sent."""
    sent, n = 0, 0
    while beats is None or n < beats:
        n += 1
        sleep(HEARTBEAT_SECONDS)
        try:
            if _emitter is None:
                raise RuntimeError("no emitter")
            _emitter(HEARTBEAT_EVENT, heartbeat_message())
            sent += 1
        except Exception as exc:                        # noqa: BLE001
            log.error("heartbeat not sent: %s; open pages will mark themselves "
                      "as not updating", exc)
    return sent


def set_emitter(emit) -> None:
    """The app hands over its socket's emit once, at import (no thread)."""
    global _emitter
    _emitter = emit


#: How a reader names itself announcing (`reader_job.announce_via_page`): never a wake.
READER_BY = "reader:"


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
    # C539: a job that changed a store re-reads, at once, each reader that reports on it, so a
    # Needs attention row it resolved clears for every viewer. A READER's own announcement
    # wakes nothing: it changed no store, and some readers announce keys the wake table holds
    # (baseline-usability announces `baselines`, which wakes it), so waking on it would loop.
    if not str(by).startswith(READER_BY):
        from modules import reader_wakes
        reader_wakes.wake(keys, by)
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
        # C539: the readers whose answer this route's write changes are read again at once.
        if response.status_code < 400:
            from modules import reader_wakes
            reader_wakes.wake(keys, request.endpoint or "")
        if response.mimetype == "application/json" and not response.direct_passthrough:
            try:
                body = json.loads(response.get_data(as_text=True))
            except ValueError:
                return response
            if isinstance(body, dict) and "invalidates" not in body:
                body["invalidates"] = list(keys)
                response.set_data(json.dumps(body))
        return response
