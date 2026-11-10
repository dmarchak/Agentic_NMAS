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
    "device_v2.reload_verify": _g(K, "Verify again (C2240): holds the device, signs in within the reload's verify bound and compares what it runs with its committed golden, as a job, and records its row beside the reload's; sends nothing but its reads"),
    "device_v2.reload_confirm": _g(C,"reloads the device, its planned-restart window declared first (P.14, cutover blocker 6), which sets a Grafana silence on its alerts as the person, with their reason (B3)", "reload"),
    "dhcp_v2.exclusion_confirm": _g(C, "adds or removes a DHCP exclusion: writes the subnet's "
                                       "pools as the pieces through the subnet's write, reloads "
                                       "Kea and reads it back, as a verified person with a "
                                       "reason (C529 step 3, board D)"),
    "dhcp_v2.subnet_confirm": _g(C, "changes a Kea subnet's pool, options or lease times: writes "
                                    "Mercury's subnet file, reloads Kea and reads it back, as a "
                                    "verified person with a reason (C529 step 3, board C)"),
    "dhcp_v2.lease_confirm": _g(C, "releases one Kea lease (lease4-del or lease6-del through "
                                   "Kea's control agent), reads Kea's leases back and records "
                                   "it in dhcp/released-leases.yml, as a verified person with a "
                                   "reason (C1403, DHCP › Leases' Release lease…)"),
    "dhcp_v2.reservation_confirm": _g(C, "adds, changes or removes a Kea reservation: writes "
                                         "Mercury's file for the subnet and reloads Kea, which "
                                         "clients then receive (C529 step 2, board B)",
                                      "dhcp_reservation"),
    "onboard_v2.verify": _g(C, "reaches the pending device and rotates its credential, from its "
                               "v2 page (`routes.onboard.verify_run`)", "onboard_verify"),
    "onboard_v2.abandon": _g(C, "deletes the pending device's records from NetBox and the "
                                "repository, from its v2 page; a ZTP device's Kea reservation "
                                "is removed and its Kea leases released (C1403)",
                             "onboard_abandon"),
    "device_v2.restore_confirm": _g(C, "re-applies a moment (its golden now, an older golden or a baseline) to one device from the v2 device page (7.3; THE restore plan and apply, run as a job, in the list its preview was drawn in, C396), merge-only, every line needing a reason (a dangerous line, an account added back) with its stated reason in the hash"),
    "device_v2.deploy_confirm": _g(C, "deploys a device's committed intent from the v2 device page (7.3; THE plan and apply (`routes.deploy.plan_devices`, `apply_batch`) the batch apply runs too, as a job), merge-only, with any line ticked for removal (Mode B) and every dangerous line's stated reason in the hash"),
    "device_v2.rotate_confirm": _g(C, "rotates a device's login credential from the v2 device page (7.3; rotate_op.confirm_and_start): the device then accepts only the new password"),
    "credential_profiles_v2.rotate_due_confirm": _g(C, "rotates every due device's login credential (C724, Rotate due devices now), one at a time through the device page's rotation, bound to the previewed list's hash"),
    "v2.profile_apply_confirm": _g(C, "deploys the monitoring profile's confirmed programs to the chosen devices, one after another (P.9 d2)"),
    "v2.pair_apply_confirm": _g(C, "deploys both ends of a link as one change (C1908, C1909; board F7-Q): each device's confirmed program through the batch apply, the second end sent only when the first deployed, the link verified once both applied, and both rolled back if either end or the link fails"),
    "v2.save_confirm": _g(C, "saves the running config to startup on each chosen device, reads it back, and records the running config as golden in one commit (C593, Devices › Save): changes what the devices boot"),
    "device_v2.persist_confirm": _g(C, "saves the running config to startup on a device and reads it back, from the v2 device page (7.3; persist_op.apply)"),
    "device_v2.rekey_confirm": _g(C, "keeps the SSH host key a device answers with now in place of the one Mercury holds (C906): every later session signs in to whatever presents it, so a person confirms it, bound to both keys"),
    "privileged_v2.confirm": _g(C, "sends one Tier 2 command (Run a privileged command…, NSOT_TIER2_PRIVILEGED) to a device, holding it, bound to the previewed plan and a stated reason; verified and recorded"),
    "update.apply": _g(C, "requests the Update: the root-owned updater moves the app to a CI-passed commit and restarts it"),
    # PHASE8_PLAN 17.1 S8 and S16 (C1912): the flow-operation core, modules/sdn/flow_ops.py.
    "sdn_v2.flow_confirm": _g(C, "adds, edits or removes a flow (or a meter) on an SDN switch through its controller, holding the switch, bound to the previewed requests' hash; verified by reading the table back, rolled back on failure, recorded", "sdn_flows"),
    "sdn_v2.response_confirm": _g(C, "answers a detected threat on an SDN switch with a catalogue action (a drop, a rate-limit's meter and flow, or an unauthorised flow removed) through its controller, as a person's confirm (HITL), bound to the previewed requests' hash; verified, rolled back on failure, recorded", "sdn_response"),
    # Lab 9 Objective B2 (board lab9-sdn artboard E): SDN › Policies' Send, a policy through the
    # same flow-operation core.
    "sdn_policies_v2.confirm": _g(C, "applies a checked SDN policy on its source's ingress switch through its controller: every check run again on the carried policy and the same requests compiled (refused if they moved), then the flow-operation core holds the switch, sends the requests bound to the previewed hash, reads the table back, rolls back on failure, and records each flow in the flow intent as the policy", "sdn_flows"),
    # Lab 9 Objective 2 (C2902; board lab9-sdn artboard A): SDN › Switches' Configure from
    # NetBox…, the OpenFlow configuration (modules/sdn/openflow_config.py).
    "sdn_switches_v2.configure_confirm": _g(C, "configures OpenFlow on the previewed switches (Arista EOS, ArubaOS-Switch or Open vSwitch) from the committed NSOT export, bound to the preview's hash; each switch planned again and its own hash compared, held, its template's lines sent (refused unless the template is confirmed on the network), verified on the switch and in the controller's switch list, rolled back on failure, recorded", "openflow_config"),
    "sdn_v2.reapply_confirm": _g(C, "puts back a response's flows and meter that its SDN switch lost before their hard timeout (C2018, Re-apply… on SDN › Flows), each as recorded and for the time its hard timeout has left, as a person's confirm (HITL), bound to the previewed requests' hash; verified, rolled back on failure, recorded as a re-apply of the response", "sdn_reapply"),
    # Lab 9 Objective 4 (C2904; board lab9-sdn B): DHCP steering, compiled from the committed
    # NSOT export and written through the one flow path as feature:dhcp-unicast.
    "sdn_dhcp_v2.confirm": _g(C, "steers DHCP on a network's SDN switches through their controller as the verified person: the flows compiled from the committed NSOT export (each edge port's broadcast request rewritten to the server's MAC toward it, a transit flow on each switch on the way, server replies dropped on every edge port), bound to the previewed hash; one plan per switch through the flow-operation core as feature:dhcp-unicast, each holding its switch, verified, rolled back on failure (the switches already changed put back), recorded", "dhcp_steering"),
    "sdn_dhcp_v2.remove_confirm": _g(C, "removes exactly the DHCP steering flows Mercury recorded on a network's SDN switches, each by delete-strict on its table, priority, match and cookie, never a wildcard, as the verified person bound to the previewed hash; verified, rolled back on failure, recorded", "dhcp_steering"),
    # P6 (C2677; board controller-app-deploy): the controller app deploy, modules/apps/deploy_op.py.
    "sdn_v2.apps_confirm": _g(C, "deploys a network's managed controller apps to its SDN controller host as one operation, bound to the previewed plan's hash as a verified person: holds the controller, declares its planned-restart window, stages the files over SFTP as the deploy account, runs the one apply command (a restart, so every switch reconnects), post-checks every expected switch, link and app's /health, rolls back to the request before on a miss, and records the receipt", "controller_deploy"),
    # Out-of-band ZTP (O6b, routes/console_ztp_v2.py; docs/LAB9_PLAN.md section 8).
    "console_ztp_v2.survey_confirm": _g(C, "types on a device's console (the wake, the prelude to the privileged prompt, the pager off for the session and two reads), holding the device and its console-server port, bound to the previewed program's hash; records the run and its masked transcript", "console_survey"),
    "console_ztp_v2.kickstart_confirm": _g(C, "types the kick-start's configuration lines on a factory-blank device's console, holding the device and its console-server port, bound to the previewed lines' hash, as a verified person; records the run and its masked transcript", "console_kickstart"),
    "oob_onboard_v2.confirm": _g(C, "onboards a Planned device over its console in one run: holds the device and its console-server port, creates its static bootstrap and pending intent, types the static kick-start's lines, reads them back, copies the bootstrap from the responder and waits for SSH, bound to the review's hash, as a verified person with a reason; undoes what it created on a stop and records the run", "console_onboard"),
    "console_servers_v2.rekey_confirm": _g(C, "keeps the SSH host key a console server answers with now in place of the one Mercury holds (C1560): every later console session signs in to whatever presents it, so a person confirms it, bound to both keys"),

    # ---- approve: a decision a later device change acts on ---------------
    # Today's template editor (templates.approve, templates.write_template, templates.validate)
    # and intent editor (templatize.edit_committed, templatize.preview_committed_edit) left at
    # 7.8 (2026-10-17, P7-23): Templates › Approve… and Edit… (templates_v2) and each device's
    # Intent tab (intent_v2). Today's device-action JSON routes (retire, persist and rotate's
    # preview and apply, templatize's seed, revert and retry) left at 7.8 (2026-10-17, P7-24):
    # each device page's Actions (the device_v2 entries).
    "v2.ip_sla_policy_set": _g(A, "commits the monitoring profile's IP SLA policy, which decides the probes suggested (P.9 d4)"),
    "v2.ip_sla_commit": _g(A, "commits suggested IP SLA probes into the devices' intent (P.9 d4)"),
    # C2854 (board app-publish): a version's test run, and its publication, each kept with the
    # version's record in Mercury's copy of the code repository; neither changes a device.
    "sdn_v2.apps_version_test": _g(K, "runs one registered app version's own tests in the container harness on the network's controller Python, from its pinned blobs, and keeps the run with the version's record by its content hash, for a verified person; nothing is sent to a controller or a device"),
    "sdn_v2.apps_publish_confirm": _g(A, "publishes one registered app version as the verified person, bound to the previewed hash of its folder, its passing test run and the network's review policy, with the reason typed; checked again inside the record's lock and kept with the version's record, so a controller app deploy may stage it"),
    # The operator's decision of 2026-11-10 (board authoring-from-words D and F): Mercury's one
    # write path to a network's code repository, a NEW app folder only, as a Draft.
    "sdn_v2.apps_draft_confirm": _g(A, "adds one new app folder (apps/<name>/) to a network's code repository as a Draft, as the verified person, bound to the previewed hash of the base commit, every file, the commit message and its author; one commit built in a throwaway repository and pushed fast-forward only to a local-path location (a folder already there is refused), recorded in the code repository's record, then fetched so it registers as a Draft; Publish stays a person's review and a passing test run"),
    "sdn_switches_v2.template_confirm": _g(A, "confirms an OpenFlow template on a network against a saved capture of one of its devices (docs/LAB9_OPENFLOW.md section 3): commits openflow_confirmations/<template>.yml as the verified person, bound to the template's and the capture's hashes as previewed; a confirmed template is the only one Configure from NetBox… sends"),
    "sdn_v2.export_confirm": _g(A, "commits a network's NSOT export (NetBox's view of the network, which SDN › Apps and every controller app deploy read) into its configuration repository as the verified person, bound to the previewed hash of the export and of the committed file; NetBox is read again and a moved export or a commit made since is refused naming both; the commit is the record"),
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
    # C2765: the preview reads the controller host through the reads engine, so a person.
    "sdn_v2.apps_preview": _g(R, "previews a controller app deploy (P6): reads the controller "
                                 "host's three shaped reads through the reads engine (every "
                                 "run recorded) and the controller's switches and links, "
                                 "stages the chosen versions from their pins into a folder "
                                 "here that is removed before it answers, and renders the plan "
                                 "and its hash; sends nothing to the controller"),
    "reads_v2.logging_path_run": _g(R, "tests the logging path (board F): one send log line "
                                     "to each device through the reads engine, then Loki "
                                     "watched; every run recorded"),
    "reads_v2.show_commands_ignore": _g(K, "records on a Show commands run the columns the "
                                          "person ticked to ignore when grouping (C580); asks "
                                          "no device"),
    "reads_v2.show_commands_save_set": _g(K, "commits a saved command set to the network's "
                                             "repository as the person (R3); sends nothing"),
    "intent_v2.commit": _g(A,"commits an edit to a device's intent (board H), bound to the version opened"),
    "intent_v2.secrets_set": _g(A, "stores a typed value for one secret reference a device's committed intent names, write-only, for that device only, never the account Mercury signs in with (board H-S, C235; secret_refs.set_value), and commits its record (who, when, why; never the value); sends nothing to the device: a later deploy acts on it"),
    "intent_v2.words_commit": _g(A, "commits a change drafted in words to a device's intent (feature 7, part 2), as Source: ai-draft with its AI-Call:, bound to the drafted patch and the version it was previewed on; with plan, the deploy preview opens next, never confirmed for the person"),
    "device_v2.revert_confirm": _g(A, "commits the inverse of one intent commit's change from the v2 device page (7.3, board 11; intent_ops.revert_apply, in the list its card carries)"),
    "device_v2.retry_confirm": _g(A, "lifts a blocked change so it may be sent again, with a stated reason, from the v2 device page (7.3, board 11; intent_ops.retry_apply, in the list its card carries)"),
    "device_v2.seed_confirm": _g(A, "commits a device's first full intent, parsed from its committed golden, from the v2 device page (7.3, board 8; seed.apply, in the list its card carries)"),
    "device_v2.retire_confirm": _g(A, "retires a device from the v2 device page (7.3, board 12; retire.apply, in the list its card carries): masks NetBox's stored credentials, clears its overrides and staged credential, removes its Kea reservations, releases its Kea leases (C1403), removes its intent, golden and template override in a commit, archives its golden tags and rollback block, withdraws its approval items, rotation-policy memberships, Topology entries and heartbeat rule, sets its NetBox record Decommissioning, forgets its SSH host key and deletes its CSV row against the export log"),
    # Capture (7.1 step 4, C82, C89): Save All is its whole-fleet form, and
    # the old one-click route is gone, because nothing in it asked whether the
    # state being enshrined was the one intended. Today's capture routes (golden.capture_preview
    # and golden.capture_apply), the monitoring profile's (templatize.profile_propose_preview
    # and _apply) and the inventory refresh (inventory.refresh) left at 7.8 (2026-10-17, P7-27)
    # with today's index, their one caller.
    "device_v2.capture_confirm": _g(A, "commits a device's confirmed capture as its golden, from the v2 device page (7.3; routes.golden.apply_captures)"),
    "onboard_v2.create": _g(A, "commits a new device's identity and intent, from v2's Add device",
                            "onboard_device"),
    "netbox_v2.confirm": _g(A, "writes to or deletes from NetBox as previewed, or (Stop tracking, C954) has Mercury forget what it created, or (Free, C1504) frees the IP addresses of a Decommissioning record holding a device's management address, from v2's NetBox page and a device's NetBox tab"),
    # C2313's condition (the operator's decision of 2026-11-03, option (i)): a person's decision
    # that the later response confirm acts on, so a person is required (approve), never a service.
    "sdn_v2.watch_propose": _g(A, "Rate-limit this source… on a watched large-packet stream (C2313): makes it a response awaiting a person, the flood rule's rate limit at the catalogue's defaults, checked against the network's response policy for the flood rule and naming the verified person who proposed it; the watching row closed as proposed by a person; nothing is sent and no AI is asked: the response is previewed and confirmed by hash as any is, recorded"),

    # ---- configure: the tool's own settings, gates, inventory, records ---
    "settings_v2.group_switch": _g(K, "switches a network's settings group (inherit, its own with its values and secrets, not applicable), bound to its preview and recorded"),
    "settings_v2.mode_switch": _g(K, "switches a network between inheriting from Default and standalone, bound to its preview and recorded"),
    "settings_v2.group_save": _g(K, "saves a card's fields (Default's, or a network's own group) and their secrets, recorded"),
    "settings_v2.group_test": _g(K, "tests a card's integration with its saved values, for the person configuring it (the S3 archive's Test writes its probe object)"),
    # PHASE8_PLAN 17.1 S2's interface (board SdnSettings): a network's SDN controller
    # connections, each network's own (C1841).
    "settings_v2.sdn_save": _g(K, "saves a network's SDN controller connection (its credential encrypted in the credential store), refused until Test answered for the URL as typed, recorded"),
    "settings_v2.sdn_remove": _g(K, "removes a network's SDN controller connection and its stored credential, recorded"),
    "settings_v2.code_repo_save": _g(K, "sets one network's code repository (the location of its jobs and apps, a local path or an https URL with no user part, and the branch), as a verified person, refused when it moved since the card drew it, recorded in the network's settings record with the value before and after"),
    "settings_v2.code_review_save": _g(K, "sets who may publish one network's app versions (someone other than the author, or the author too, recorded as self-review), as a verified person, refused when it moved since the card drew it, recorded in the network's settings record with the value before and after"),
    "settings_v2.code_repo_fetch": _g(K, "fetches one network's code repository into Mercury's read-only copy (git's file and https transports only, no prompt, no hooks, bounded) and registers each app folder at the fetched commit as a Draft keyed by location, commit and content hash, for a verified person; nothing is written to the repository it copies, and every fetch is recorded, a failed one with why"),
    "settings_v2.sdn_stage": _g(K, "marks one network lab, pilot or production (C2009: SDN responses' AUTO is turned on, and runs, only on a network marked lab until the AUTO production-readiness gate is complete), as a verified person with a reason, refused when the stage moved since the card drew it, recorded in the network's settings record with the stage before and after"),
    "settings_v2.sdn_test": _g(K, "tests an SDN controller connection with the values as typed, its credential among them, for the person configuring it; saves nothing"),
    "settings_v2.sdn_saved_test": _g(K, "tests a saved SDN controller connection with its stored credential, for the person configuring it; changes nothing"),
    # Heal to intent's policy (board H, parts H1 and H9; routes/heal_v2.py), posted by each
    # network's Self-healing tab. The confirm and resume refuse anyone but a verified person
    # too, whatever configure's settings allow a service.
    "heal_v2.policy_confirm": _g(K, "sets one network's heal policy as previewed, bound to the preview's fingerprint, as a verified person with a reason (C2009: AUTO only on a network marked lab, at most 7 days, then dry run); recorded in the network's settings record with the values before and after; sends nothing to a device"),
    # The device state class (board H artboard N, H28; routes/ai_classes_v2.py): what AI may
    # send off the host for one network.
    "ai_classes_v2.device_state_on": _g(K, "turns the device state class on for one network (the AI read set's answers may then leave the host, masked), as a verified person with a reason of at least three words; recorded in the network's settings record; sends nothing to a device"),
    "ai_classes_v2.device_state_off": _g(K, "turns the device state class off for one network at once, one press, no confirm; recorded with who and when; sends nothing"),
    "heal_v2.turn_off": _g(K,"turns self-healing off for one network at once, one press, no confirm; recorded with who and when; a heal already applying finishes its own verify and rollback"),
    "heal_v2.notify_save": _g(K, "names the team told about one network's self-healing and the events that tell it (the Self-healing tab's Who is told), refused when the team does not exist or another person changed it since the card drew it; recorded in the network's settings record; sends nothing"),
    "heal_v2.stop_everywhere": _g(K, "stops self-healing on every network at once (the installation's kill switch), one press, no confirm; recorded with who, when and why"),
    "heal_v2.resume": _g(K, "resumes self-healing everywhere as previewed, bound to the preview's fingerprint, as a verified person with a reason; recorded in the installation's settings record"),
    # Heal to intent's Tier 2 (board H, parts H5 and H9, artboard E; routes/heal_proposal_v2.py),
    # posted by a proposal's card on its Needs attention row. Approve and decline refuse anyone
    # but a verified person too (modules/heal/propose.py), whatever a service is granted.
    "heal_proposal_v2.approve": _g(C, "approves one self-healing proposal (a Tier 2 fix, board H artboard E) bound to the proposal's hash as previewed, as a verified person with a reason: its program sent through THE apply as that person, holding the device, then the measured process reset it needs (refused until measured), verified, rolled back on failure and recorded", "heal_proposal"),
    "heal_proposal_v2.decline": _g(K, "declines one self-healing proposal as a verified person with a reason: recorded in the network's heal decisions and step log, its incident closed; sends nothing to a device"),
    # Lift the halt (board H artboard E's second row, C2471): refuses anyone but a verified
    # person too (modules/heal/decisions.lift), whatever a service is granted.
    "heal_proposal_v2.lift": _g(K, "lifts the halt in force on one network's self-healing (a rate cap, a repeat or a rolled-back heal), by its id, as a verified person with a reason of three words or more: recorded in the network's heal decisions with who, when and why; self-healing then runs under its policy again; sends nothing to a device"),
    # Right / Wrong on a dry-run record (board H artboard C, C2399): refuses anyone but a
    # verified person too (modules/heal/decisions.mark), whatever a service is granted.
    "heal_proposal_v2.mark": _g(K, "marks one self-healing dry-run record right or wrong, by its decision's id, as a verified person (Wrong with why it was wrong): recorded in the network's heal decisions with who, when and why, and counted per fix kind as the dry run's false-positive rate; sends nothing to a device"),
    # Settings › Installation › Notifications (board H, artboard B; H9; routes/notify_v2.py):
    # the relay's password, the teams and their destinations, codes and test sends.
    "notify_v2.relay_password": _g(K, "stores the email relay's password a person typed, encrypted in the credential store, never drawn back; recorded with who and when in the installation's settings record"),
    "notify_v2.relay_test": _g(K, "sends one test message through the relay as saved to one of the teams' addresses, the person who asked named in the delivery log"),
    "notify_v2.team_add": _g(K, "adds a notification team, recorded with who made it"),
    "notify_v2.email_add": _g(K, "adds an email address to a team, unverified and off, and sends it a verification code (only the code's salted hash is kept)"),
    "notify_v2.code_send": _g(K, "sends a destination a new verification code, replacing the last"),
    "notify_v2.code_verify": _g(K, "checks a verification code typed back: right and in time, verifies the destination and turns it on; wrong spends a try"),
    "notify_v2.dest_enabled": _g(K, "turns a destination off, or on (refused until it is verified)"),
    "notify_v2.dest_test": _g(K, "sends one test message to one destination, its outcome kept in the delivery log with who asked"),
    "notify_v2.dest_remove": _g(K, "removes a destination from a team, a webhook's signing secret erased with it; its delivery log rows stay"),
    "notify_v2.webhook_add": _g(K, "adds a webhook to a team, unverified and off, its signing secret typed by a person stored encrypted in the credential store, and sends it a verification code"),
    "notify_v2.webhook_edit": _g(K, "changes a webhook's name, URL or signing secret (a new URL is unverified and off again until its code is typed back)"),
    "sdn_v2.controller_test": _g(K, "tests a saved SDN controller connection with its stored credential from SDN › Controllers; changes nothing"),
    "sdn_v2.response_dismiss": _g(K, "dismisses an SDN response awaiting a person, with their reason; nothing is sent, recorded"),
    "sdn_v2.link_verify": _g(K, "Verify the reroute on an SDN link-failure card (Lab 9 B3, board F): traces every host pair over the controller's stored flow tables and keeps the outcome on the card as the person's; reads the stored read only, sends nothing"),
    "sdn_v2.link_dismiss": _g(K, "dismisses an SDN link-failure card with a person's reason; nothing is sent, recorded"),
    "sdn_v2.capabilities_read": _g(K, "reads again what each SDN switch can do (board F's capability matrix): each switch's description, meter features and table features through its controller, reads only, kept for the matrix and the responses' fallback"),
    "sdn_v2.mode_set": _g(K, "turns SDN responses' AUTO mode on (a verified person's reason, expiry and allowed risk) or off for one network (PHASE8_PLAN 17.4), recorded"),
    "sdn_v2.policy_set": _g(K, "sets one network's SDN response policy (each detection rule's allowed catalogue actions and its default; the Lab 8 walk's objective 3.1), each action checked against its rule, refused when the policy moved since the form drew it, recorded in the network's settings record"),
    "sdn_v2.loop_set": _g(K, "starts or stops the SDN closed loop's job on one network (PHASE8_PLAN 17.1 S10), recorded in its log; the job's classify step is a background AI call the gateway refuses unless the feature is on for the network"),
    "sdn_v2.response_classify": _g(K, "Classify a response awaiting a person: one recorded, capped AI call as the person who pressed it, reading the detection's stored evidence pack (modules/sdn/closed_loop.py, PHASE8_PLAN 17.1 S7); its answer checked in code and kept with the response, its catalogue action proposed; nothing is sent to a switch"),
    # Lab 9 B1 (board I of docs/boards/lab9-sdn.html): SDN › Flows' Analyse this network.
    "sdn_analyse_v2.collect": _g(K, "Collect now: starts the analyst's collection job on one network (modules/sdn/analyst.py), a read of its controllers (flows, port counters twice, port descriptions, links) kept as a snapshot under its own id, recorded with who asked; one at a time per network; nothing is sent to a switch"),
    "sdn_analyse_v2.ask": _g(K, "Analyse this network: one recorded, capped AI call as the person who pressed it over the network's latest collected snapshot (modules/sdn/analyst.py, Lab 9 B1); its findings checked against the snapshot in code and kept as the network's latest analysis; nothing is sent to a switch"),
    "sdn_analyse_v2.planted_add": _g(K, "adds a planted issue (its name, the evidence it should be found by, and why) to one network's planted-issue sheet, the analyst's evaluation record (Lab 9 B1); recorded with who added it; nothing is sent to a switch or a model"),
    "sdn_analyse_v2.planted_why": _g(K, "saves a person's note on why a planted issue was found or missed on one network's planted-issue sheet (Lab 9 B1), recorded with who saved it; nothing is sent to a switch or a model"),
    "sdn_v2.flow_preview": _g(N, "previews an SDN flow change: reads the switch's table and renders the exact requests and their hash; writes nothing"),
    "sdn_policies_v2.draft": _g(K, "Draft the policy on SDN › Policies (Lab 9 B2): the names resolved in code, then one recorded, capped AI call as the person who pressed, on the sdn_policy pin, its answer checked in code against the NSOT export, the switch's table, committed policies and the protected set (modules/sdn/policy_intent.py); nothing is sent to a switch"),
    "sdn_policies_v2.check": _g(N, "Drop instead… or Rate-limit at <switch> instead… on SDN › Policies: the drafted policy checked again in code with the person's choice, reading the switch's table and meter features; no AI call, writes nothing"),
    "sdn_policies_v2.preview": _g(N, "previews a checked SDN policy: compiles it to flows and plans them through the flow-operation core, reading the switch's table, rendering the exact requests and their hash; writes nothing"),
    "sdn_v2.apps_draft_preview": _g(N, "previews adding an uploaded app folder to a network's code repository as a Draft: checks the files, reads the branch's commit now (git ls-remote, and a fetch into a throwaway repository removed again) and draws the exact commit and the hash the confirm binds; writes nothing to the repository, Mercury's copy or its record"),
    "sdn_v2.apps_publish_preview": _g(N, "previews publishing one registered app version (C2854): its pin, author, newest test run, the network's review policy and whether this person may publish, and the hash the confirm binds; writes nothing"),
    "sdn_switches_v2.configure_preview": _g(N, "previews the OpenFlow configuration of the chosen switches (or every one not connected as intended): reads each switch's version and running configuration (its capture list's reads) and renders its exact program, undo and hash from the committed NSOT export; writes nothing"),
    "sdn_switches_v2.template_preview": _g(N, "previews confirming an OpenFlow template: draws its lines beside a saved capture's masked text and the two hashes the confirm binds; writes nothing"),
    "sdn_switches_v2.verify": _g(N, "Verify now on SDN › Switches: asks the SDN reader to read the network's controllers again now, as its schedule does anyway; sends nothing to a switch"),
    "sdn_v2.export_preview": _g(N, "previews a network's NSOT export (C2777): reads its records from NetBox (whole lists, never a write) and draws the export's hash and what it changes against the committed one; writes nothing"),
    "sdn_v2.response_preview": _g(N, "previews a response awaiting a person: reads the switch's table and renders the exact requests and their hash; writes nothing"),
    "sdn_v2.reapply_preview": _g(N, "previews putting back a response's lost flows and meter (C2018): reads the switch's table and meters and renders the exact requests and their hash; writes nothing"),
    "sdn_dhcp_v2.preview": _g(N, "previews DHCP steering (C2904): compiles the flows from the committed NSOT export, reads each switch's table and renders every request, its REST body and the hash; writes nothing"),
    "sdn_dhcp_v2.remove_preview": _g(N, "previews removing DHCP steering (C2904): reads each switch's table and renders the delete-strict of each flow Mercury recorded for it, and the hash; writes nothing"),
    "settings_v2.records_save": _g(K, "saves the installation's records database settings, recorded (board F2; works with the database down)"),
    "settings_v2.records_test": _g(K, "tests the records database (six checks, a temporary row rolled back) and keeps its answer"),
    "settings_v2.records_replace": _g(K, "replaces Mercury's copy of the records database password (a secret), recorded, then tests it"),
    "settings_v2.records_store_apply": _g(K, "moves a record store to the records database or back (copy, switch, check), bound to its preview, recorded (Phase 4)"),
    "settings_v2.network_source_apply": _g(K, "changes a network's inventory source as previewed, refreshes it, recorded"),
    "settings_v2.network_create": _g(K, "creates a network as previewed (its folder derived from its name), recorded (board I's pattern)"),
    "settings_v2.network_delete": _g(K, "deletes a network as previewed, its name typed: its folder moved aside, never erased, recorded"),
    "network_v2.choose": _g(K, "records the verified person's own network choice (board N): what their pages show, never anyone else's; with no verified person (the gate open, C2559) it makes the network the installation's current one, recorded in History"),
    # Settings › Installation › Console servers (O8, routes/console_servers_v2.py).
    "console_servers_v2.port_save": _g(K, "adds or replaces how Mercury reaches one console-server port (driver, host, container or TCP port, a credential REFERENCE; modules/nsot/console_servers.py), recorded with who"),
    "console_servers_v2.port_remove": _g(K, "forgets how Mercury reaches one console-server port; NetBox's port and the key stay, recorded with who"),
    "console_servers_v2.key_generate": _g(K, "generates a console server's SSH key pair: the private half stored encrypted under its reference in the credential store, only the public key shown"),
    "settings_v2.install_save": _g(K,"saves an Installation card's settings (NetBox connection, Proxmox, Commit author, Server) for every network, recorded (board F3)"),
    "v2.history_ask_logs_words": _g(K, "Ask in words on the logs builder: one recorded, capped AI call as the person who asked, turning a question into the logs builder's choices (modules/ai/nl_query.py); reads Loki, changes nothing else"),
    "assistant_v2.ask": _g(K, "the toolbar assistant's question (card P7, stage 1; modules/ai/assistant.py): one recorded, capped AI call as the person who asked, answered from the manual's passages code chose, its citations checked; a question the manual does not cover recorded as a manual gap; changes nothing else"),
    "v2.history_ask_metrics_words": _g(K, "Ask in words: one recorded, capped AI call as the person who asked, turning a question into the metrics builder's choices (modules/ai/nl_query.py); reads Prometheus, changes nothing else"),
    "intent_v2.words": _g(K, "Change it in words on a device's Intent tab: one recorded, capped AI call as the person who asked, drafting a patch to that device's intent and previewing it (modules/ai/intent_words.py); writes nothing, reaches no device"),
    # PHASE8_PLAN 16.11 item 1 (board FB): the routes refuse anyone but a verified person too,
    # whatever configure's settings allow a service (modules/ai/feedback.person).
    "ai_feedback_v2.say": _g(K, "records a verified person's Was this right? on one AI answer (yes, or no with what was wrong, masked), one per person per call, in the records store ai_feedback; no model call, nothing sent, the answer and its checks unchanged"),
    "ai_feedback_v2.review": _g(K, "a verified person accepts an answer said wrong into its case draft (bound to the draft's hash) or dismisses it with a reason, recorded in ai_feedback; Mercury writes no case file and makes no model call"),
    "device_v2.deploy_change_record": _g(K, "Draft a change record in a device's deploy preview (PHASE8_PLAN 16.11 item 3, board CR): the preview planned again from the card's form, one recorded, capped AI call as the person who pressed it, sending the program's shape in keywords and Mercury's own words, never a configuration value (modules/ai/change_record.py); an advisory document, it changes nothing, reaches no device and Deploy is unchanged by it"),
    "v2.monitoring_alert_explain": _g(K,"Explain an alert: one recorded, capped AI call as the person who pressed it, reading the alert's stored evidence pack (modules/ai/explain.py); changes nothing, runs nothing"),
    "v2.monitoring_alert_history_evidence": _g(K, "Build evidence for a past alert from the alert history: its evidence pack rebuilt as of its time, each section marked captured, rebuilt or missing, kept frozen in the pack store as the person who pressed it (modules/evidence_pack.build_for_episode); reaches no device, changes nothing else"),
    "v2.monitoring_alert_pack_rebuild": _g(K, "Build again: a kept evidence pack of an older schema built again from the alert history as of its alert's time, with this release's evidence, kept beside the one it replaces (never rewritten) as the person who pressed it (modules/evidence_pack.build_for_episode); reaches no device, changes nothing else"),
    "settings_v2.install_test": _g(K,"tests an Installation card's service (NetBox, Proxmox) with its saved settings; changes nothing"),
    "settings_v2.install_replace": _g(K, "replaces an Installation card's token (a secret; Proxmox's with its id), recorded, then tests it"),
    "settings_v2.platforms_preview": _g(K, "previews a platform or role map change: every device it moves, from each NetBox list's last inventory; writes nothing (board F4)"),
    "settings_v2.platforms_test": _g(R, "reads one device through the reads engine with a proposed driver, show version only (board F4's platform map Test)"),
    "settings_v2.platforms_apply": _g(K, "writes the platform or role map as previewed, bound to its fingerprint, recorded, and refreshes each NetBox list (board F4)"),
    "settings_v2.install_ratify": _g(K, "records a decision about an access or identity setting: writes the value already in force, never a change, recorded (board F4, C625)", "ratify_setting"),
    "settings_v2.diag_drift_interval": _g(K, "sets the drift schedule for every network, recorded (board F4, Diagnostics)"),
    "settings_v2.diag_drift_switch": _g(K, "turns a network's drift checks off or on, with who and when, recorded (board F4)"),
    "settings_v2.diag_drift_check": _g(N, "the schedule does this anyway; it only happens earlier (board F4's Check now)"),
    "device_v2.diagnose_run": _g(R, "Diagnose… (board H, H16): a runbook's reads through the "
                                    "reads engine as kind diagnosis, allowlisted reads only, its "
                                    "diagnosis (masked) shown to the person, every run recorded"),
    "device_v2.drift_check_now": _g(N, "Check drift now (C2336): one device's drift read, as the schedule's run makes it, of that device alone, recorded on its drift row; reads the device and sends nothing"),
    "settings_v2.network_source_preview": _g(N, "reads NetBox once with proposed filters for a source change's preview; writes nothing"),
    "settings_v2.network_source_refresh": _g(N, "reads NetBox for a NetBox network now; the schedule does this anyway"),
    "settings_v2.network_create_preview": _g(N, "checks a new network's name and the folder it derives; writes nothing"),
    "heal_v2.policy_preview": _g(N, "previews a change to one network's heal policy (its mode, AUTO's expiry, the kinds and the hard stops) in the six parts with the fingerprint its confirm sends; writes nothing and sends nothing to a device"),
    "heal_v2.resume_preview": _g(N, "previews resuming self-healing: each network's mode once resumed and the fingerprint its confirm sends; writes nothing"),
    "settings_v2.network_delete_preview": _g(N, "counts what a network holds and says where its data would go; writes nothing"),
    "settings_v2.records_store_preview": _g(N, "counts a record store's lines, network by network, in the files and the records database for a move's preview; writes nothing"),
    "settings_v2.install_writes_off": _g(K, "turns NetBox's master write switch off for every network, recorded; never turns it on"),
    "settings_v2.install_ai_allow": _g(K, "allows hosted AI for the installation with the person's reason, recorded (PHASE8_PLAN 15.8)"),
    "settings_v2.install_ai_off": _g(K, "turns hosted AI off for the installation, recorded"),
    # Settings › AI (board AI3, C1843): a background AI feature per network. The route refuses
    # anyone but a verified person too, whatever configure's settings allow a service.
    "settings_v2.ai_on": _g(K, "turns a background AI feature on for one network, bound to the "
                               "estimate the person was shown and accepted, with its day and "
                               "month caps; recorded with who, when and the estimate"),
    "settings_v2.ai_off": _g(K, "turns a background AI feature off for one network, its next "
                                "call refused at once; recorded"),
    "settings_v2.ai_caps": _g(K, "changes an on background AI feature's day and month caps on "
                                 "one network, within the installation's day cap; recorded with "
                                 "both values"),
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
    "credential_profiles_v2.read_account_save": _g(K, "sets a credential profile's read-only "
                                                    "account (H28: its name once, its password "
                                                    "typed by a verified person, sealed), "
                                                    "recorded (who, which, the fields set)"),
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
    "console_ztp_v2.survey_preview": _g(N, "reads the device's console path from NetBox and the console-server port's record, and computes the survey's program and hash; contacts no console and writes nothing"),
    "console_ztp_v2.kickstart_preview": _g(N, "reads the device's console path, its latest survey and the port's record, and renders the kick-start's exact lines and hash; contacts no console and writes nothing"),
    "oob_onboard_v2.preview_view": _g(N, "reads NetBox's Planned record, its console path, planned address and cable, Mercury's port record and committed intent, and computes the out-of-band onboarding's review and hash; contacts no device and writes nothing"),
    "console_servers_v2.rekey_preview": _g(N, "reads the SSH host key a console server presents now, in the key exchange only, with no credential; keeps nothing"),
    "device_v2.persist_read": _g(N, "starts Persist's preview read: the device's running and "
                                    "startup configurations, and `dir nvram:` when startup "
                                    "keeps a certificate there; sends nothing that changes it"),
    "intent_layers_v2.change_approve": _g(A, "approves a layer change's plan by its hash, as a verified person with a summary and a reason (board FC4, fleet_change.approve_and_run_start): the plan is made again and refused if it moved, the layer committed once, then the canary deployed through THE deploy (and every batch when the person chose not to pause), the first failure stopping it"),
    "intent_layers_v2.change_go_on": _g(A, "after a layer change's canary, as a verified person: runs every batch left from the paused run's own record through THE deploy, each device's program checked again, the first failure stopping it (board FC5, fleet_change.run_start)"),
    "intent_layers_v2.change_plan": _g(N, "starts a layer change's plan as a job (board FC4, fleet_change.plan_layer): renders each device the layer reaches with the change in memory and without it, through the deploy's own plan; sends nothing and writes nothing"),
    "device_v2.reload_start": _g(N, "starts Reload's preview: reads the device's running and "
                                    "startup configurations, image and boot variable; sends "
                                    "nothing that changes it"),
    "templates_v2.bindings_preview": _g(N, "names every device whose template a bindings change "
                                           "moves; writes nothing"),
    "templates_v2.edit_check": _g(N, "renders a template edit for its devices in a copy of the "
                                     "library outside the repository; writes nothing"),
    "intent_v2.check": _g(N, "checks and renders an edit as it is typed; writes nothing"),
    "intent_v2.acknowledge": _g(N, "rewrites the document in the editor (its unmodeled_ack block); writes nothing"),
    "intent_v2.reopen": _g(N, "opens the editor on what is committed now with the person's edit on it; writes nothing"),
    "update.step_done": _g(C, "records that a person did a host step the tool cannot check: the release's record of what was done on the host"),
    "v2.stall_capture": _g(K, "records a stall the viewer's own page captured as it showed its stale note (C2003): the page, its live connection's state and the app's view of it, a local record History reads; changes nothing a device, a setting or a decision reads"),
    "attention.acknowledge": _g(K, "records that a person acknowledged one event row on Needs attention, with a reason; the row leaves the page and the event stays in its record"),
    "restarts.planned": _g(K, "records a planned-restart window, so the restarts it covers are not reported as unexpected, and sets a Grafana silence on its devices' alerts as the caller, with the reason (B3); a window covering a restart already seen needs a correction with its reason; with `end`, ends a window early (an abandoned attempt's, C1389), recorded as the caller with the reason", operation="planned_restart"),
    "update.check": _g(N, "runs the app-pushed reader now: fetches origin and asks CI; moves nothing that runs"),
    "jobs.job_finished": _g(N, "a host job ended: runs the job-health reader now; reads systemd and the stores, moves nothing, and accepts only a declared job's unit"),
    "netbox_v2.preview": _g(N, "starts a dry run of an import or removal, or a read of what Stop tracking would forget or Free (C1504) would free, on a thread; writes nothing"),
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
    # PHASE8_PLAN 17.1 S12: a route that configures a device directly refuses one its SDN
    # controller manages, naming the controller (modules/sdn/authority.py).
    from modules.sdn import authority
    managed = authority.check_request(request)
    if managed is not None:
        log.info("route_gates: refused %s: %s is controller-managed", request.endpoint,
                 managed.get("device"))
        return _refusal_response(managed, 409)
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
