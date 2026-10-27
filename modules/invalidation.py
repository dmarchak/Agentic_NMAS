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
usually not the one that is now wrong (Verify lives on the pending device's page;
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
    "device_state": "what a device runs: anything read live from it",
    "host_keys": "the SSH host key Mercury keeps for each device: kept on first contact, "
                 "refused when it changed, replaced by a re-key (modules/host_keys.py, C906)",
    "breakglass": "the break-glass export log, its intact checks and its drills (job health's "
                  "break-glass rows read them)",
    "topology": "the topology graph and its layout (P.11's reader, the brief's redefinition)",
    "logs": "the fleet's syslog counted per day (the Logs view's reader, C652)",
    "dhcp": "the network's Kea: subnets, reservations and leases (the DHCP reader, C529)",
    "path_trace": "a Topology path trace (board D): a hop read, or the trace finished, its "
                  "record ready to read by id",
    "ztp_discovery": "the devices asking on the ZTP segment that the tool does not know (the "
                     "discovery reader, board L)",
    "saved_views": "History › Query's saved views: their titles, who saved them, pinned or not "
                   "(modules/saved_views.py, C667)",
    "reveals": "the reveal record: who saw a masked value, when, which and why "
               "(modules/reveal_audit.py); History's timeline draws every kind (C818, C837)",
    "ai_calls": "the record of AI calls (modules/ai/calls.py): each call, its verdict and its "
                "cost; History's timeline draws it (Phase 8)",
    "job_health": "job-health rows, as the job-health reader last stored them",
    "alerts": "Grafana's alert rules and instances, as the grafana-alerts reader last stored them",
    "dashboards": "Grafana's dashboards and their models, as the grafana-dashboards reader last stored them",
    "reachability": "whether each device answers, as the reachability reader last stored it",
    "integration_health": "whether each integration answers, as the integration-health reader last stored it",
    "credential_health": "each credential's expiry or age, as the credential-health reader last stored it (P.21)",
    "records": "where each of Mercury's record stores is (files or the records database) and "
               "whether the moved ones still match their files, as the records-check reader "
               "last stored it (Phase 4)",
    "coverage_reporting": "when each device's monitoring data last arrived, as the coverage-reporting reader last stored it (Coverage's not-reporting cells)",
    "ci_verdict": "the running commit's CI verdict, as the ci-verdict reader last stored it",
    "app_version": "whether the running commit is what is pushed (origin/main), as the "
                   "app-pushed reader last stored it",
    "capture_preview": "a capture preview's device reads: finished, and its preview ready to read by id",
    "reads": "a Show commands run (Ask the device, Show commands): finished, its answers ready by id",
    "rotation": "a credential rotation run from the Device page: finished, its result ready to read by id",
    "privileged": "a Tier 2 command run from the Device page (Run a privileged command…): finished, its record ready to read by id",
    "reload": "a Reload's preview or run from the Device page (P.14): finished, ready to read by id",
    "persist_read": "Persist's preview read of what a device runs against what it boots (C886): "
                    "finished, ready to read by id",
    "device_holds": "an operation the app ran released a device: a card refused because it was held reads again",
    "device_progress": "an operation the app ran on a held device reached its next step: a running card redraws its stepper (C370)",
    "in_progress": "an operation run as a job started or finished, or a person opened a finished "
                   "one's result: the top bar's In progress chip reads again (C537)",
    "save": "a Save run from Devices (C593): finished, its result ready to read by id",
    "deploy_job": "a batch deploy run as a job (the v2 profile Apply): a device finished, or the batch, "
                  "its progress and result ready to read by id",
    "console_ztp": "a console survey or kick-start (out-of-band ZTP, modules/nsot/console_ztp.py) "
                   "ended: the console card reads its record by id",
    "sdn": "each network's SDN controllers, their switches, flows and meters, as the SDN reader "
           "last stored them (SDN › Controllers and Flows, PHASE8_PLAN 17.1 S11)",
    "console_servers": "Mercury's console-server store (modules/nsot/console_servers.py) and the "
                       "console servers' keys: Settings › Installation › Console servers reads "
                       "again",
}

#: Announcers that are not reader jobs (C188 step 2): a background job a
#: request started, announcing when it finishes. Declared here so the keys
#: they send are senders to `keys_in_use`, exactly as a reader's are.
ANNOUNCERS = {
    "capture-preview": ("capture_preview",),   # modules/nsot/capture_job.py
    "show-commands": ("reads",),               # modules/nsot/reads.py: a run's end
    "rotation": ("rotation",),                 # modules/nsot/rotate_op.py
    "scheduled-rotation": ("rotation", "credentials"),  # modules/nsot/scheduled_rotation.py (C724)
    "netbox-job": ("netbox",),                 # modules/netbox_jobs.py: a preview or import landed
    # modules/nsot/save_op.py (C593): the run's end, its commit and what each device boots.
    "save": ("save", "goldens", "remote", "baselines", "drift", "device_state"),
    "privileged": ("privileged",),             # modules/nsot/privileged.py: a Tier 2 run's end
    "reload": ("reload", "restarts", "device_state"),  # modules/nsot/reload_op.py: a preview's or run's end
    "persist-read": ("persist_read",),         # modules/nsot/persist_op.py: the preview read's end
    # modules/nsot/template_coverage.py: a coverage check's end (Templates › Coverage).
    "template-coverage": ("templates",),
    "path-trace": ("path_trace",),             # modules/path_trace.py: a level read, and its end
    # routes/adopt_v2.py: an adoption's end (the inventory row, its first golden, NetBox).
    "adopt": ("inventory", "goldens", "netbox", "remote"),
    "device-ops": ("device_holds", "device_progress"),  # modules/nsot/device_ops.py: each release, each step
    # modules/nsot/capture_job.py (C537): every job's start and end, for the In progress chip.
    "in-progress": ("in_progress",),
    # modules/host_keys.py (C906): a device's key kept, refused or replaced, by any session.
    "host-keys": ("host_keys",),
    # modules/nsot/console_ztp.py (O6a): a console survey's or kick-start's end; the console
    # card (O6b, templates/v2/_console_ztp.html) hears its own key.
    "console-ztp": ("device_state", "pending", "console_ztp"),
    # modules/deploy_job.py: each device finishing, and at the end what a
    # deploy changes (the keys today's /deploy/apply declared until 7.8).
    # A restore run as a job (the v2 device page) also moves intent and approvals.
    # modules/arrival_watch.py: the combined deploy's watch, as each first arrival lands.
    "arrival-watch": ("deploy_job",),
    # modules/nsot/repo.save_templates: each template-library commit (C516).
    "template-library": ("templates",),
    # modules/drift_check.DriftChecker.record: each run recorded, scheduled or asked for
    # (board F4's Diagnostics card redraws when a Check now finishes).
    "drift-check": ("drift",),
    "deploy-job": ("deploy_job", "device_state", "baselines", "drift", "rolled_back",
                   "goldens", "remote", "intent", "approvals"),
}

_COMMIT = ("goldens", "remote")        # a golden commit also moves the remote's state

#: endpoint -> keys, or Nothing(reason).
DECLARED = {
    # Inventory and lists. Today's inventory refresh (inventory.refresh), the capture's
    # (golden.capture_preview, golden.capture_apply) and the monitoring profile's
    # (templatize.profile_propose_preview and _apply) left at 7.8 (2026-10-17, P7-27) with
    # today's index: Settings › a network's Refresh now, the device page's Capture… and
    # Devices › Save, and Monitoring › Profile (their v2 entries).
    # Credentials.
    "v2.history_view_save": ("saved_views",),
    "v2.history_view_pin": ("saved_views",),
    "v2.history_view_remove": ("saved_views",),
    "v2.history_ask_logs_reveal": ("reveals",),
    # C837: History's timeline draws every reveal the record holds.
    "onboard_v2.bootstrap": ("reveals",),
    "topology_v2.expected_declare": ("topology",),
    "topology_v2.expected_withdraw": ("topology",),
    "topology_v2.positions_save": ("topology",),
    "topology_v2.positions_reset": ("topology",),
    "topology_v2.path_run": ("path_trace", "reads"),
    # C529 step 2: a reservation written to Kea and recorded in the network's repository.
    "dhcp_v2.reservation_confirm": ("dhcp",),
    "dhcp_v2.subnet_confirm": ("dhcp",),
    "dhcp_v2.exclusion_confirm": ("dhcp",),
    "dhcp_v2.lease_confirm": ("dhcp",),
    "credential_profiles_v2.save": ("credentials",),
    "credential_profiles_v2.delete": ("credentials",),
    "credential_profiles_v2.policy_save": ("credentials",),
    # Goldens, the repository and the remote.
    # Capture (7.1 step 4): Save All is now the whole-fleet form of it.
    "device_v2.capture_confirm": _COMMIT + ("baselines", "drift", "approvals"),   # routes.golden.apply_captures
    # Today's re-apply (golden.restore_apply) and the Remote card's acknowledge, auto-push and
    # write probe (remote.acknowledge, remote.auto_push, remote.verify_write) left at 7.8
    # (2026-10-17, P7-21): v2's restore and re-apply confirms and History › Remote set-up's
    # acts (remote_v2.*) are declared here and below.
    "remote.push": ("remote",),
    "remote.verify": ("remote",),
    "remote_v2.connect": ("remote",),
    # An import, a removal, or Stop tracking (C954: Mercury's created and removal records and
    # the network's last import, which the NetBox page draws); settings when writes come on.
    "netbox_v2.confirm": ("netbox", "settings"),
    "remote_v2.write_probe": ("remote",),
    "remote_v2.acknowledge": ("remote",),
    "remote_v2.auto_push": ("remote",),
    # Intent, templates and deploys.
    "v2.ip_sla_policy_set": ("intent", "remote"),
    "v2.ip_sla_commit": ("intent", "remote"),
    "v2.decline_confirm": ("intent", "remote"),
    "v2.heartbeat_apply": Nothing("writes the generated heartbeat rules file, which no panel reads; the page redraws itself, and nothing alerts differently until a person installs it on the host"),
    "intent_v2.commit": ("intent", "remote"),
    "intent_v2.words_commit": ("intent", "remote", "ai_calls"),
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
    "templates_v2.edit_commit": ("templates", "remote"),
    "templates_v2.bindings_apply": ("templates", "remote"),
    "templates_v2.seed": ("templates", "remote"),
    # Today's template editor's save and Approve (templates.write_template, templates.approve)
    # and intent editor's commit (templatize.edit_committed) left at 7.8 (2026-10-17, P7-23).
    # Today's device-action JSON routes (retire, persist and rotate's preview and apply,
    # templatize's seed, revert and retry) left the same day (P7-24): the device_v2 entries.
    "v2.profile_propose_commit": ("intent", "remote"),
    "bulk_intent_v2.apply": ("intent", "remote"),
    "device_v2.revert_confirm": ("intent", "remote", "rolled_back"),
    "device_v2.retry_confirm": ("rolled_back",),
    "device_v2.seed_confirm": ("intent", "remote"),
    # Retirement leaves nothing the name keeps (C1332 to C1342): its tags, template override,
    # queue items, rollback block, Kea reservations, Topology entries, NetBox record and key.
    "device_v2.retire_confirm": ("inventory", "goldens", "baselines", "intent", "templates",
                                 "credentials", "settings", "remote", "approvals",
                                 "rolled_back", "dhcp", "topology", "netbox", "host_keys"),
    # Onboarding on v2 (cutover blocker 3). Verify runs phase 2, which PROMOTES: the device list
    # is the first of the three measured cases. Today's onboarding routes and its deploy wizard
    # (onboard.*, deploy.plan, deploy.apply) left at 7.8 (2026-10-17, P7-25).
    # A pending onboarding is a wait the In progress chip lists (C1193), so each also says
    # `in_progress`.
    "onboard_v2.create": ("pending", "intent", "credentials", "remote", "in_progress"),
    "onboard_v2.verify": ("pending", "inventory", "credentials", "netbox",
                          "device_state", "baselines", "in_progress") + _COMMIT,
    # A ZTP device's abandon removes its Kea reservation and releases its leases (C1403).
    "onboard_v2.abandon": ("pending", "intent", "credentials", "remote", "in_progress", "dhcp"),
    # NetBox. Today's NetBox tab's import and removal routes (/netbox/safety/*) left at 7.8
    # (2026-10-17); v2's NetBox page's confirm (`netbox_v2.confirm`) is declared with v2's routes.
    # Today's NetBox Test (/netbox/test_connection), which persisted the auth scheme that
    # worked, left with today's Settings modal at 7.8 (2026-10-15); the NetBox card's Test
    # (settings_v2.install_test, below) keeps nothing.
    # Settings, posture and the collectors.
    "settings_v2.group_switch": ("settings",),
    "settings_v2.mode_switch": ("settings",),
    "settings_v2.group_save": ("settings",),
    "settings_v2.records_save": ("settings",),
    # A controller connection saved or removed: Settings' card and SDN › Controllers and Flows,
    # which draw the connection list beside the SDN reader's stored read.
    "settings_v2.sdn_save": ("settings", "sdn"),
    "settings_v2.sdn_remove": ("settings", "sdn"),
    # The Test keeps its answer, which the card draws for every viewer (board F2).
    "settings_v2.records_test": ("settings",),
    "settings_v2.records_replace": ("settings",),
    "settings_v2.records_store_apply": ("settings", "records"),
    "network_v2.choose": ("active_list",),
    "settings_v2.network_create": ("lists", "settings"),
    "settings_v2.network_source_apply": ("inventory", "settings"),
    "settings_v2.network_source_refresh": ("inventory",),
    "settings_v2.network_delete": ("lists", "settings", "active_list"),
    "settings_v2.install_save": ("settings",),
    "settings_v2.install_replace": ("settings",),
    "settings_v2.install_writes_off": ("settings",),
    "settings_v2.install_ratify": ("posture", "settings"),
    "settings_v2.platforms_test": ("reads",),
    "settings_v2.platforms_apply": ("settings", "inventory"),
    "settings_v2.diag_drift_interval": ("drift",),
    "settings_v2.diag_drift_switch": ("drift",),
    # The third measured case, a drift run's state (today's /drift/check/sync until 7.8).
    "settings_v2.diag_drift_check": ("drift",),
    # A device and its files.
    "device_v2.persist_confirm": ("device_state",),   # persist_op.apply
    # C906: the key Mercury holds for the device, read by Needs attention and History.
    "device_v2.rekey_confirm": ("host_keys",),
    # Out-of-band ZTP (O6b, routes/console_ztp_v2.py): the console survey and kick-start.
    "console_ztp_v2.survey_preview": Nothing("reads NetBox's console path and Mercury's stores "
                                             "and computes the survey's program and hash; it "
                                             "contacts no console and writes nothing"),
    "console_ztp_v2.kickstart_preview": Nothing("reads NetBox's console path, the latest survey "
                                                "and the stores and renders the exact lines and "
                                                "their hash; it contacts no console and writes "
                                                "nothing"),
    "console_ztp_v2.survey_confirm": Nothing("starts the survey as a job and answers at once; "
                                             "the run ANNOUNCES console_ztp, device_state and "
                                             "pending when it ends (ANNOUNCERS console-ztp)"),
    "console_ztp_v2.kickstart_confirm": Nothing("starts the kick-start as a job and answers at "
                                                "once; the run ANNOUNCES console_ztp, "
                                                "device_state and pending when it ends "
                                                "(ANNOUNCERS console-ztp)"),
    # The one-decision out-of-band onboarding (routes/oob_onboard_v2.py).
    "oob_onboard_v2.preview_view": Nothing("reads NetBox (the Planned record, its console path, "
                                           "address and cable), Mercury's stores and committed "
                                           "intent, and computes the review and its hash; it "
                                           "contacts no device and writes nothing"),
    "oob_onboard_v2.confirm": Nothing("starts the onboarding as a job and answers at once; the "
                                      "run ANNOUNCES console_ztp, device_state and pending when "
                                      "it ends (ANNOUNCERS console-ztp), and each step "
                                      "device_progress"),
    # Settings › Installation › Console servers (O8, routes/console_servers_v2.py).
    "console_servers_v2.port_save": ("console_servers",),
    "console_servers_v2.port_remove": ("console_servers",),
    "console_servers_v2.key_generate": ("console_servers",),
    "console_servers_v2.rekey_preview": Nothing("reads the key a console server presents now, "
                                                "in the key exchange only, and shows it beside "
                                                "the one held; it keeps nothing"),
    # C1560: the key Mercury holds for a console server, read by Needs attention and History.
    "console_servers_v2.rekey_confirm": ("host_keys", "console_servers"),
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
    "v2.save_confirm": Nothing("starts a job and answers at once; the Save ANNOUNCES save when it finishes, with the commit and what each device boots (ANNOUNCERS save)"),
    "device_v2.restore_confirm": Nothing("starts a job and answers at once; the restore ANNOUNCES deploy_job as it finishes, and what a restore changes (ANNOUNCERS deploy-job)"),
    "device_v2.deploy_confirm": Nothing("starts a job and answers at once; the deploy ANNOUNCES deploy_job as it finishes, and what a deploy changes (ANNOUNCERS)"),
    "device_v2.rotate_confirm": Nothing("rotate_op.confirm_and_start: starts the job and answers at once; the job ANNOUNCES rotation when it finishes (ANNOUNCERS)"),
    "credential_profiles_v2.rotate_due_confirm": Nothing("starts the run as a job and answers at once; the run ANNOUNCES rotation and credentials after each device and when it finishes (ANNOUNCERS)"),
    "device_v2.rotate_preview": Nothing("reads the device's account line live and computes the plan; it writes nothing"),
    # Reads sent as POST: a body carries the question, and nothing is stored.
    "device_v2.capture_start": Nothing("starts the same capture preview job for one device "
                                       "(routes.golden.start_capture_preview); it records nothing, and the "
                                       "job ANNOUNCES capture_preview when it finishes"),
    "device_v2.golden_reveal": Nothing("draws one golden version in place INSIDE History's "
                                       "timeline, the region `reveals` redraws: announcing it "
                                       "would wipe the version it just drew; the timeline "
                                       "lists the reveal (C837) when it is next drawn"),
    "v2.history_reapply_confirm": Nothing("starts the re-apply as a job and answers at once; "
                                          "the batch ANNOUNCES deploy_job as each device "
                                          "finishes, and what a restore changes at the end "
                                          "(ANNOUNCERS deploy-job)"),
    "device_v2.persist_read": Nothing("starts Persist's preview read as a job; the job "
                                      "ANNOUNCES persist_read when it finishes (ANNOUNCERS "
                                      "persist-read)"),
    "device_v2.reload_start": Nothing("starts the preview's read as a job; the job ANNOUNCES "
                                      "reload when it finishes (ANNOUNCERS reload)"),
    "device_v2.reload_confirm": Nothing("starts the reload as a job and answers at once; the "
                                        "run ANNOUNCES reload, restarts and device_state when "
                                        "it ends, and device_progress at each step "
                                        "(ANNOUNCERS reload, device-ops)"),
    "templates_v2.bindings_preview": Nothing("reads the bindings and the manifest and names the "
                                            "devices a change would move; writes nothing"),
    "templates_v2.edit_check": Nothing("renders the edit in a temporary copy of the library, "
                                       "removed after; the repository is not written"),
    "templates_v2.coverage_check": Nothing("starts the coverage check as a job and answers at "
                                           "once; the job keeps its answer and ANNOUNCES "
                                           "templates when it ends (ANNOUNCERS "
                                           "template-coverage)"),
    "adopt_v2.preview": Nothing("reads the device over the supplied login and computes the "
                                "adoption's plan; it sends nothing and writes nothing"),
    "adopt_v2.confirm": Nothing("starts the adoption as a job and answers at once; the job "
                                "ANNOUNCES inventory, goldens, netbox and remote when it ends, "
                                "and device_progress at each step (ANNOUNCERS adopt, "
                                "device-ops)"),
    "onboard_v2.preview": Nothing("builds Add device's plan and review; creates nothing (the "
                                  "same core as onboard.plan)"),
    "onboard_v2.verify_preview": Nothing("reads one pending device and computes what Verify "
                                         "would send; it writes nothing"),
    "onboard_v2.abandon_preview": Nothing("Abandon's dry run: names what it would remove and "
                                          "removes nothing"),
    "intent_v2.check": Nothing("checks and renders an intent edit as it is typed"),
    "intent_v2.acknowledge": Nothing("rewrites the editor's document; the commit writes it"),
    "intent_v2.reopen": Nothing("opens the editor again; writes nothing"),
    "update.check": Nothing("starts the app-pushed reader, which announces app_version itself "
                            "when it finishes"),
    "jobs.job_finished": Nothing("starts the job-health reader, which announces job_health "
                                 "itself when it finishes"),
    "bulk_intent_v2.preview": Nothing("previews the change for the ticked devices; the apply "
                                      "commits"),
    "settings_v2.group_test": Nothing("tests an integration's connection and reports in the card"),
    "settings_v2.sdn_test": Nothing("tests an SDN controller with the values as typed and answers beside Test; saves nothing"),
    "settings_v2.sdn_saved_test": Nothing("tests a saved SDN controller and answers on its row; changes nothing"),
    "sdn_v2.controller_test": Nothing("tests a saved SDN controller and answers on its card; the card's state stays the reader's"),
    "sdn_v2.flow_preview": Nothing("previews a flow change in its card; the confirm sends"),
    "sdn_v2.response_preview": Nothing("previews a response in its card; the confirm sends"),
    # PHASE8_PLAN 17.1 S8 to S10: a flow operation, a response, a dismissal, the mode and the
    # loop: SDN's region (Flows and Responses) reads again.
    "sdn_v2.flow_confirm": ("sdn",),
    "sdn_v2.response_confirm": ("sdn",),
    "sdn_v2.response_dismiss": ("sdn",),
    "sdn_v2.mode_set": ("sdn",),
    "sdn_v2.loop_set": ("sdn",),
    # PHASE8_PLAN 17.1 S7: a person's Classify is one recorded AI call, and its answer is kept
    # with the response awaiting them (its proposed action can change).
    "sdn_v2.response_classify": ("ai_calls", "sdn"),
    # A card's Test keeps nothing, but the AI card's is one recorded call (Phase 8).
    "settings_v2.install_test": ("ai_calls",),
    "v2.monitoring_alert_explain": ("ai_calls",),
    "v2.monitoring_alert_history_evidence": ("alerts",),
    "v2.monitoring_alert_pack_rebuild": ("alerts",),
    "v2.history_ask_metrics_words": ("ai_calls",),
    "v2.history_ask_logs_words": ("ai_calls",),
    "intent_v2.words": ("ai_calls",),
    "settings_v2.install_ai_allow": ("settings",),
    "settings_v2.install_ai_off": ("settings",),
    "settings_v2.platforms_preview": Nothing("previews a map change from each list's last inventory; writes nothing"),
    "settings_v2.network_source_preview": Nothing("reads NetBox with proposed filters for the preview; writes nothing"),
    "settings_v2.network_create_preview": Nothing("checks a new network's name and the folder it derives; writes nothing"),
    "settings_v2.network_delete_preview": Nothing("counts what a network holds and where its data would go; writes nothing"),
    "netbox_v2.preview": Nothing("starts a dry run on a thread; the job announces netbox when it lands (ANNOUNCERS netbox-job)"),
    "remote_v2.publication": Nothing("reads what a first push would publish; writes nothing"),
    "settings_v2.records_store_preview": Nothing("counts a record store's lines in the files and the table for a move's preview; writes nothing"),
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
        # C656: nor does any other refusal (4xx, 5xx): it wrote nothing, and its keys made the
        # page redraw the region that was showing the refusal's reason, wiping it.
        if response.status_code >= 400:
            return response
        keys = keys_for(request.endpoint or "")
        if not keys:
            return response
        response.headers[HEADER] = ",".join(keys)
        # C539: the readers whose answer this route's write changes are read again at once.
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
