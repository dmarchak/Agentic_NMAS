"""What each confirm- or approve-gated route does at each stage of the device-changing
operation's lifecycle: preview, a hash binding the confirm to what was previewed, verify,
rollback, record (the operator, 2026-10-02; rules_audit check 3, the standing rule "every
device-changing operation: preview, confirm by hash, verify, rollback, record").

`tests/test_operation_stages.py` holds the population to `route_gates.GATES`' confirm and
approve endpoints EXACTLY, and resolves every reference:
- `preview`: an endpoint in the app's url_map;
- `hash`: a request field the view reads (`field`, or `field in module.function` when a helper
  reads it);
- `verify`, `rollback`, `record`: an importable `module.attribute`.
Any stage may instead be `n/a: <why>` (the stage does not apply, said in words) or
`MISSING: <why>` (a gap, named; the gaps are counted and only shrink). Most of the gaps are
today's onboarding and editor routes 7.8 removes, and the NetBox writes, which nothing reads
back.
"""

from collections import namedtuple

Stages = namedtuple("Stages", "preview hash verify rollback record")

NO_DEVICE = "n/a: changes no device"
FORWARD = "n/a: a commit, corrected by a forward commit"

STAGES = {
    # ---- Device changes through the deploy pipeline
    # Today's deploy wizard (deploy.apply, its preview deploy.plan) left at 7.8 (2026-10-17,
    # P7-25): device_v2.deploy_confirm and v2.profile_apply_confirm (the batch Apply) run THE
    # plan and apply.
    # Today's re-apply (golden.restore_apply, its preview golden.restore_preview) left at 7.8
    # (2026-10-17, P7-21): device_v2.restore_confirm below and v2.history_reapply_confirm.
    "v2.profile_apply_confirm": Stages(
        "v2.profile_apply_preview", "command_hashes", "modules.pipeline._stage_verify",
        "modules.pipeline._stage_rollback", "routes.deploy._write_receipts"),
    # The v2 device page's Deploy, with Mode B (7.3): the same plan and apply, as a job.
    "device_v2.deploy_confirm": Stages(
        "device_v2.deploy", "command_hash", "modules.pipeline._stage_verify",
        "modules.pipeline._stage_rollback", "routes.deploy._write_receipts"),
    # The v2 device page's Restore (7.3, boards 9 and 10): THE restore plan and apply, as a job.
    "device_v2.restore_confirm": Stages(
        "device_v2.restore_preview", "command_hash", "modules.pipeline._stage_verify",
        "modules.pipeline._stage_rollback", "routes.deploy._write_receipts"),
    # ---- Device operations of their own
    # Today's persist, rotate and retire routes (persist.apply, rotate.apply, retire.apply) and
    # templatize's seed, revert and retry applies left at 7.8 (2026-10-17, P7-24): the v2 device
    # page's confirms below, each over the same operation.
    # The v2 device page's Persist (7.3): persist_op's plan and apply, drawn as a card.
    # Tier 2, "Run a privileged command…" (boards T2-A to T2-D; NSOT_TIER2_PRIVILEGED): one
    # recoverable command on one device, its before-state read and kept, verified by the
    # measured rule.
    "privileged_v2.confirm": Stages(
        "privileged_v2.preview", "hash", "modules.nsot.privileged.verify",
        "n/a: what Tier 2 clears cannot be put back; the device rebuilds it (counters, ARP, "
        "the log buffer), and the preview says so", "modules.nsot.privileged.record"),
    "device_v2.persist_confirm": Stages(
        "device_v2.persist", "hash", "modules.nsot.onboard.persist_on_device",
        "n/a: a save cannot be undone; the preview says it carries the running config as it is",
        "modules.nsot.persist_op.apply"),
    # Out-of-band ZTP (O6b; modules/nsot/console_ztp.STAGES reads these two): the console
    # survey, read-only, and the kick-start's lines on a device its survey found factory-blank.
    "console_ztp_v2.survey_confirm": Stages(
        "console_ztp_v2.survey_preview", "hash", "modules.nsot.console_ztp.verify_survey",
        "n/a: the survey types no configuration and saves nothing; the pager setting and the "
        "privileged prompt end with the console session",
        "modules.nsot.console_ztp.record"),
    "console_ztp_v2.kickstart_confirm": Stages(
        "console_ztp_v2.kickstart_preview", "hash", "modules.nsot.console_ztp.verify_kickstart",
        "n/a: the kick-start saves nothing (no write memory), so a reload returns the device "
        "to its factory state; the preview says so",
        "modules.nsot.console_ztp.record"),
    # The one-decision out-of-band onboarding (routes/oob_onboard_v2.py): verify is the
    # read-back of every typed line and the copy's verdict (then SSH answering); the rollback
    # undoes what its Create made (the device keeps what was typed, unsaved: a reload returns
    # it to its factory state, which the review says).
    "oob_onboard_v2.confirm": Stages(
        "oob_onboard_v2.preview_view", "hash", "modules.nsot.oob_steps.readback_verdict",
        "modules.nsot.oob_onboard.undo_created", "modules.nsot.console_ztp.record"),
    # C1560: a console server's SSH host key, kept in place of the held one, from Settings ›
    # Installation › Console servers; the device page's re-key's code, keyed by the host.
    "console_servers_v2.rekey_confirm": Stages(
        "console_servers_v2.rekey_preview", "hash", "modules.nsot.rekey_op.verify",
        "n/a: nothing is sent to the console server; the old key stays in the record's "
        "history, and a person re-keys back to it the same way", "modules.host_keys.replace"),
    # Re-key (C906): the SSH host key a device answers with now, kept in place of the held one.
    # It changes no device; its record is Mercury's trust in what answers at the address.
    "device_v2.rekey_confirm": Stages(
        "device_v2.rekey", "hash", "modules.nsot.rekey_op.verify",
        "n/a: nothing is sent to the device; the old key stays in the record's history, and a "
        "person re-keys back to it the same way", "modules.host_keys.replace"),
    # Devices › Save (C593): persist's save and read-back on each device, then the capture's
    # record, one commit; a device whose read-back did not match is not recorded.
    "v2.save_confirm": Stages(
        "v2.save", "hash", "modules.nsot.onboard.persist_on_device",
        "n/a: a save cannot be undone; the plan says it carries each running config as it is",
        "modules.nsot.save_op.run"),
    # The v2 device page's Rotate (7.3): rotate_op's confirm, plan and job, drawn as a card.
    "device_v2.rotate_confirm": Stages(
        "device_v2.rotate_preview", "fingerprint",
        "modules.nsot.credential_rotation.verify_new_credential",
        "modules.nsot.credential_rotation.revert_commands",
        "modules.nsot.credential_rotation.record_outcome"),
    # Credentials › Profiles' Rotate due devices now (C724): the due list previewed and bound by
    # its hash; each device then runs the device page's rotation (its own plan's fingerprint,
    # verify, revert and record), and the run is recorded.
    "credential_profiles_v2.rotate_due_confirm": Stages(
        "credential_profiles_v2.rotate_due_preview", "hash",
        "modules.nsot.credential_rotation.verify_new_credential",
        "modules.nsot.credential_rotation.revert_commands",
        "modules.nsot.credential_rotation.record_outcome"),
    # Today's onboarding (onboard.verify, onboard.create, onboard.abandon, with their previews
    # onboard.verify_preview and onboard.plan) left at 7.8 (2026-10-17, P7-25), and with it
    # three MISSING gaps (Create's hash, Abandon's preview and hash): onboard_v2's below.
    # History › Baselines › Re-apply (2026-10-10): THE restore plan and job, every device a
    # baseline holds, as one batch.
    "v2.history_reapply_confirm": Stages(
        "v2.history_reapply", "command_hashes", "modules.pipeline._stage_verify",
        "modules.pipeline._stage_rollback", "routes.deploy._write_receipts"),
    # Reload (P.14, cutover blocker 6): the preview reads the device and judges six gates; the
    # run reads again and compares the fingerprint, declares the window, reloads, waits, and
    # verifies that it runs what it ran. A reload cannot be undone.
    "device_v2.reload_confirm": Stages(
        "device_v2.reload_start", "fingerprint", "modules.nsot.reload_op.run",
        "n/a: a reload cannot be undone; the preview says so and names the break-glass record "
        "and the console as the way in if it does not come back",
        "modules.nsot.reload_op.record"),
    # Adopt (board G): the preview reads the device over the supplied login and sends nothing;
    # the apply reads again and compares the fingerprint, adds the tool's account and proves it
    # on a fresh login, and removes it again (read back gone) when the proof fails.
    "adopt_v2.confirm": Stages(
        "adopt_v2.preview", "fingerprint",
        "modules.nsot.adopt._add_tool_account", "modules.nsot.adopt._remove_added",
        "modules.nsot.onboard.record_run"),
    # Onboarding on v2 (cutover blocker 3): today's cores, each confirm bound to its preview.
    "onboard_v2.verify": Stages(
        "onboard_v2.verify_preview", "fingerprint in routes.onboard.verify_run",
        "modules.nsot.onboard.verify_device",
        "n/a: a failed step stops the phase with the device pending and nothing promoted; the "
        "rotation reverts on its held session", "modules.nsot.onboard.record_run"),
    "onboard_v2.create": Stages(
        "onboard_v2.preview", "fingerprint in routes.onboard.create_run",
        "n/a: phase 1 reaches no device", "modules.nsot.onboard.abandon_onboarding",
        "MISSING: Create's run is read back from the pending row, never recorded as a run"),
    "onboard_v2.abandon": Stages(
        "onboard_v2.abandon_preview", "fingerprint", "n/a: nothing reached the device",
        "n/a: abandon is itself the undo of Create", "modules.nsot.onboard.record_run"),
    # DHCP › Reservations (C529 step 2, board B): the preview plans against Kea and Mercury's
    # file; the apply plans again under the file's lock and compares the hash, tests the
    # candidate with Kea's own check, reloads, reads every reservation back, and restores the
    # previous file when the read-back disagrees.
    "dhcp_v2.reservation_confirm": Stages(
        "dhcp_v2.reservation_preview", "hash",
        "modules.dhcp_reservations.every_reservation", "modules.nsot.ztp._replace",
        "modules.dhcp_reservations.record_commit"),
    # DHCP › Subnets (C529 step 3, board C): the same shape over Mercury's subnet file; the
    # read-back is refused unless exactly the changed subnet moved.
    "dhcp_v2.subnet_confirm": Stages(
        "dhcp_v2.subnet_preview", "hash",
        "modules.dhcp_subnets._moved", "modules.nsot.ztp._replace",
        "modules.dhcp_subnets.record_commit"),
    # DHCP › Exclusions (C529 step 3, board D): the subnet's write path, its own record.
    "dhcp_v2.exclusion_confirm": Stages(
        "dhcp_v2.exclusion_preview", "hash",
        "modules.dhcp_subnets._moved", "modules.nsot.ztp._replace",
        "modules.dhcp_exclusions.record_commit"),
    # DHCP › Leases, Release lease… (C1403): the preview reads Kea's leases and names the one;
    # the apply reads them again and compares the hash, sends lease4-del or lease6-del for
    # that address alone, and reads the leases back. A deleted lease cannot be put back (Kea
    # keeps no copy), and the preview says so.
    "dhcp_v2.lease_confirm": Stages(
        "dhcp_v2.lease_preview", "hash", "modules.dhcp_leases.release",
        "n/a: a lease Kea deleted cannot be put back (Kea keeps no copy of it); the client is "
        "answered afresh at its next request, and the preview says so",
        "modules.dhcp_leases.record"),
    "update.apply": Stages(
        "v2.update", "hash",
        "n/a: the root-owned updater (deploy/update/nmas-update) confirms the new version by identity",
        "n/a: the root-owned updater rolls back a version not up in 120 s",
        "modules.update_op._audit"),
    "update.step_done": Stages(
        "n/a: a person records that a host step is done", "n/a: nothing is previewed",
        "n/a: a step nothing can check is said done by a person", "n/a: a record only",
        "modules.host_steps.record_done"),
    # ---- The record: goldens and intent (no device changes)
    # The v2 device page's Capture (7.3), one device. Today's capture (golden.capture_apply,
    # its preview golden.capture_preview) and profile proposal (templatize.profile_propose_apply,
    # its preview templatize.profile_propose_preview; v2.profile_propose_commit below is its
    # home) left at 7.8 (2026-10-17, P7-27) with today's index.
    "device_v2.capture_confirm": Stages(
        "device_v2.capture_start", "hash",
        "n/a: records what the device holds; the apply re-reads it and refuses a moved capture",
        FORWARD, "modules.nsot.repo.save_golden"),
    # Devices › Change a setting on the ticked devices (7.4's board D): the same core.
    "bulk_intent_v2.apply": Stages(
        "bulk_intent_v2.preview", "hash", NO_DEVICE,
        "n/a: a failed commit puts every file back; one device reverts alone",
        "modules.nsot.bulk_intent.apply"),
    # Today's intent editor (templatize.edit_committed, its preview
    # templatize.preview_committed_edit) left at 7.8 (2026-10-17, P7-23) with its hash gap: the
    # Intent tab's commit below binds the base.
    "intent_v2.commit": Stages(
        "intent_v2.check",
        "base",   # the blob the editor opened; a moved intent is refused naming both
        NO_DEVICE, FORWARD, "modules.nsot.repo.save_host_vars"),
    # Feature 7's part 2: the draft's digest (device, patch, base) is on its call's use row,
    # and a commit handed anything else is refused before it writes.
    "intent_v2.words_commit": Stages(
        "intent_v2.words", "patch", NO_DEVICE, FORWARD, "modules.nsot.repo.save_host_vars"),
    # The v2 device page's Revert and Retry (7.3, board 11): intent_ops' applies, the list carried.
    "device_v2.revert_confirm": Stages(
        "device_v2.revert", "hash", NO_DEVICE, FORWARD, "modules.nsot.intent_ops.revert_apply"),
    "device_v2.retire_confirm": Stages(
        "device_v2.retire", "hash",
        "n/a: retirement changes no device; the NetBox mask and its record's Decommissioning "
        "are read back inside the apply, and each Kea removal reads Kea back",
        "n/a: one commit; a failed commit restores the tree", "modules.nsot.repo.commit"),
    "device_v2.seed_confirm": Stages(
        "device_v2.seed", "hash", NO_DEVICE,
        "n/a: a failed commit puts the file back; a seeded intent is corrected forward",
        "modules.nsot.seed.apply"),
    "device_v2.retry_confirm": Stages(
        "device_v2.retry", "hash", NO_DEVICE,
        "n/a: a retry is a recorded decision; a new rollback re-records the block",
        "modules.nsot.intent_ops.retry_apply"),
    "v2.ip_sla_commit": Stages(
        "v2.ip_sla", "fingerprint", NO_DEVICE, FORWARD, "modules.nsot.ip_sla_policy.apply"),
    # C718: Decline… and Undo decline…, one device's intent only.
    "v2.decline_confirm": Stages(
        "v2.decline_card", "hash", NO_DEVICE,
        "n/a: a failed commit puts the file back; a decline is undone by Undo decline…",
        "modules.nsot.decline.apply"),
    "v2.ip_sla_policy_set": Stages(
        "v2.ip_sla", "profile_hash", NO_DEVICE, FORWARD, "modules.nsot.ip_sla_policy.set_policy"),
    # ---- Templates
    # Today's Approve and template save (templates.approve, its preview templates.validate, and
    # templates.write_template) left at 7.8 (2026-10-17, P7-23) with their three gaps.
    # The v2 Templates page (7.6, boards A to C): the check is the preview, and the confirm is
    # bound to the fingerprint it showed AND the check's outcome as read (`seen`).
    "templates_v2.approve": Stages(
        "templates_v2.check", "seen in modules.nsot.approve_op.approve", NO_DEVICE,
        "modules.nsot.approval.revoke", "modules.nsot.approve_op.approve"),
    "templates_v2.revoke": Stages(
        "n/a: a withdrawal, recorded with its reason", "n/a: nothing is previewed", NO_DEVICE,
        "n/a: approve it again", "modules.nsot.approve_op.revoke"),
    # C566, board B: the diff and every bound device's measured change are the preview; the
    # confirm is bound to both blobs it showed (the network's copy and the shipped file).
    # C566, board A: Propose on v2, the preview card bound by the proposal's hash.
    "v2.profile_propose_commit": Stages(
        "v2.profile_propose_form", "hash", NO_DEVICE, FORWARD,
        "modules.nsot.profile_propose.apply"),
    "templates_v2.bring": Stages(
        "templates_v2.bring_form", "copy_blob",
        NO_DEVICE, FORWARD, "modules.nsot.template_write.commit"),
    # The template editor on v2 (cutover blocker 5): the check as typed is the preview (each
    # governed device's render against its golden, and what the commit revokes); the commit
    # is bound to the blob opened.
    "templates_v2.edit_commit": Stages(
        "templates_v2.edit_form", "base", NO_DEVICE, FORWARD,
        "modules.nsot.template_write.commit"),
    # Bindings on v2 (cutover blocker 5): the devices a change moves are the preview; the
    # commit is bound to the file committed then and to the change previewed.
    "templates_v2.bindings_apply": Stages(
        "templates_v2.bindings_preview", "fingerprint", NO_DEVICE, FORWARD,
        "modules.nsot.repo.save_templates"),
    # Seed the library on v2 (cutover blocker 5): the shipped files it adds are the preview,
    # the commit bound to the shipped library's signature; it never overwrites a file.
    "templates_v2.seed": Stages(
        "templates_v2.seed_form", "signature", NO_DEVICE, FORWARD,
        "modules.nsot.repo.save_templates"),
    # ---- NetBox
    # v2's NetBox page (cutover blocker 2), its preview a job, over `modules/netbox_ops.py`
    # (today's NetBox tab's three apply routes, the same core, left at 7.8, 2026-10-17).
    # Its Stop tracking (C954) is bound by the same token (`netbox_ops.forget` calls
    # `authorize`, the master switch aside), and recorded by `netbox_guard.record_removal`.
    "netbox_v2.confirm": Stages(
        "netbox_v2.preview", "token in modules.netbox_ops.authorize",
        "MISSING: NetBox is not read back after an import; write failures are counted (C8)",
        "n/a: NetBox writes are not transactional; recovery is the tested backup (P.2)",
        "modules.netbox_guard.record_modified"),
}

#: The gaps, counted: the test pins this number, so it can only go down.
# 6 -> 2 2026-10-17, measured: today's onboarding took its four with it (7.8, P7-25: Create's hash and
# run record, Abandon's preview and hash); v2's Create keeps the shared run-record gap.
# 10 -> 6 2026-10-17, measured: today's template editor took its three gaps (Approve's hash, the
# save's preview and hash) and today's intent editor its hash gap with them (7.8, P7-23).
# 17 -> 10 2026-10-17, measured: today's /run_command took its four LEGACY gaps with it (7.8,
# P7-22), and the ceiling had not followed today's NetBox tab's three (14 measured before this).
# 21 -> 17 2026-10-15, measured: today's /bulk_execute took its four LEGACY gaps with it (7.8).
# 46 -> 21 2026-10-15, measured: today's /templates/bindings took its two gaps with it at 7.8,
# and the ceiling had not followed the 7.8 removals before it (23 measured before this one).
# +1 2026-10-10: v2's NetBox confirm shares today's import's missing read-back (C8); today's three
# NetBox entries leave at 7.8 and take theirs with them.
# +1 2026-10-10: v2's Create shares today's Create's missing run record (one core); v2's
# Create and Abandon bind their confirms, so today's two hash gaps and Abandon's preview gap
# leave with today's routes at 7.8.
MISSING_CEILING = 2


# ---------------------------------------------------------------------------
# Where each operation's record is READ LATER (C359, the operator, 2026-10-03: a persist was
# readable now, on its result, and not later, in the device's History). Every gated route
# that can change a device or its record (confirm, approve, configure) names the
# `history_sources.SOURCES` that read its per-device record into the History tab, or says
# `n/a: <why>` (no device's record), or `MISSING: <why>` (a record nothing keeps; counted,
# only shrinking). tests/test_history_declared.py holds the population to the gate table and
# every named source to the registry History draws, so a new operation with no reader fails.
# ---------------------------------------------------------------------------

NOT_A_DEVICE = "n/a: changes the app, a list or its settings, never one device's record"
TEMPLATE = "n/a: changes a template or its approval, never one device's record"
PROFILE = "n/a: changes the network's monitoring profile, which no device's record holds"

HISTORY = {
    # ---- confirm: sends to a device
    "v2.profile_apply_confirm": ("receipts", "golden"),
    "device_v2.deploy_confirm": ("receipts", "golden"),
    "device_v2.restore_confirm": ("receipts", "golden"),
    "device_v2.persist_confirm": ("rotation",),
    "device_v2.rekey_confirm": ("host_keys",),
    "console_servers_v2.rekey_confirm": ("host_keys",),
    "console_ztp_v2.survey_confirm": ("console_ztp",),
    "console_ztp_v2.kickstart_confirm": ("console_ztp",),
    "oob_onboard_v2.confirm": ("console_ztp", "onboarding"),
    "v2.save_confirm": ("rotation", "golden"),
    "device_v2.rotate_confirm": ("rotation", "golden", "intent"),
    "credential_profiles_v2.rotate_due_confirm": ("rotation", "golden", "intent"),
    "onboard_v2.verify": ("onboarding", "golden"),
    "adopt_v2.confirm": ("onboarding", "golden"),
    "device_v2.reload_confirm": ("reloads", "restart_windows", "restarts"),
    "v2.history_reapply_confirm": ("receipts", "golden"),
    "onboard_v2.abandon": ("onboarding",),
    "update.apply": NOT_A_DEVICE,
    "dhcp_v2.reservation_confirm": ("n/a: changes a Kea reservation, never one device's record; "
                                    "the network's repository keeps it (dhcp/reservations.yml)"),
    "dhcp_v2.subnet_confirm": ("n/a: changes a Kea subnet, never one device's record; the "
                               "network's repository keeps it (dhcp/subnets.yml)"),
    "dhcp_v2.lease_confirm": ("n/a: releases a Kea lease, never one device's record; the "
                              "network's repository keeps it (dhcp/released-leases.yml)"),
    "dhcp_v2.exclusion_confirm": ("n/a: changes a Kea subnet's pools, never one device's "
                                  "record; the network's repository keeps it "
                                  "(dhcp/exclusions.yml)"),
    "update.step_done": NOT_A_DEVICE,
    # ---- approve: a decision a later device change acts on
    "device_v2.capture_confirm": ("golden", "measured"),
    "onboard_v2.create": ("intent",),
    "intent_v2.commit": ("intent",),
    "intent_v2.words_commit": ("intent", "ai_calls"),
    "bulk_intent_v2.apply": ("intent",),
    "device_v2.revert_confirm": ("intent",),
    "device_v2.retry_confirm": ("retries",),
    "device_v2.seed_confirm": ("intent",),
    "device_v2.retire_confirm": ("n/a: a retired device has no History tab; its address shows its retired record, read from the retire commit (C185)"),
    "v2.ip_sla_commit": ("intent",),
    "v2.decline_confirm": ("intent",),
    # B8: the network's own record of each removal (the removal record), and of each import,
    # Remove and Stop tracking confirmed on v2's NetBox page (its job record), on History.
    "netbox_v2.confirm": ("netbox",),
    "v2.ip_sla_policy_set": PROFILE,
    "templates_v2.approve": TEMPLATE,
    "templates_v2.revoke": TEMPLATE,
    "templates_v2.bring": TEMPLATE,
    "templates_v2.edit_commit": TEMPLATE,
    "templates_v2.bindings_apply": TEMPLATE,
    "templates_v2.seed": TEMPLATE,
    "v2.profile_propose_commit": PROFILE,
    # ---- configure
    # A saved command set (C548, R3): a commit as the person, read as one of the fleet's commits.
    "reads_v2.show_commands_save_set": ("commits",),
    # The columns ignored when grouping a run (C580): recorded on that run, drawn on its row.
    "reads_v2.show_commands_ignore": ("show_commands",),
    "privileged_v2.confirm": ("privileged",),
    "attention.acknowledge": ("acknowledgements", "restarts"),
    "restarts.planned": ("restart_windows",),
    "v2.history_view_save": ("saved_views",),
    "v2.history_view_pin": ("saved_views",),
    "v2.history_view_remove": ("saved_views",),
    "topology_v2.expected_declare": ("topology_expected",),
    "topology_v2.expected_withdraw": ("topology_expected",),
    "topology_v2.positions_save": ("topology_layout",),
    "topology_v2.positions_reset": ("topology_layout",),
    "credential_profiles_v2.save": ("credential_profiles",),
    "credential_profiles_v2.delete": ("credential_profiles",),
    "credential_profiles_v2.policy_save": ("credential_profiles",),
    "v2.credentials_intact": ("breakglass",),
    "v2.credentials_check": ("breakglass",),
    "v2.credentials_drill": ("breakglass",),
    "v2.heartbeat_apply": ("heartbeat_windows",),
    "console_servers_v2.port_save": ("n/a: changes Mercury's console-server store, never one "
                                     "device's record; the store logs every write with who "
                                     "and when, drawn on Settings › Installation › Console "
                                     "servers"),
    "console_servers_v2.port_remove": ("n/a: changes Mercury's console-server store, never "
                                       "one device's record; the store logs the removal with "
                                       "who and when, drawn on the Console servers tab"),
    "console_servers_v2.key_generate": ("n/a: stores a console server's key in the credential "
                                        "store, never one device's record; the key's user, "
                                        "fingerprint and time are drawn on the Console "
                                        "servers tab"),
    "settings_v2.group_switch": NOT_A_DEVICE,
    "settings_v2.mode_switch": NOT_A_DEVICE,
    "settings_v2.group_save": NOT_A_DEVICE,
    "settings_v2.group_test": NOT_A_DEVICE,
    # SDN's controller connections (PHASE8_PLAN 17.1 S2, S11): a network's settings and a
    # Test that reads a controller, no device's.
    "settings_v2.sdn_save": NOT_A_DEVICE,
    "settings_v2.sdn_remove": NOT_A_DEVICE,
    "settings_v2.sdn_test": NOT_A_DEVICE,
    "settings_v2.sdn_saved_test": NOT_A_DEVICE,
    "sdn_v2.controller_test": NOT_A_DEVICE,
    "settings_v2.records_save": NOT_A_DEVICE,
    "settings_v2.records_test": NOT_A_DEVICE,
    "settings_v2.records_replace": NOT_A_DEVICE,
    "settings_v2.records_store_apply": NOT_A_DEVICE,
    "network_v2.choose": NOT_A_DEVICE,
    "settings_v2.network_create": NOT_A_DEVICE,
    "settings_v2.network_source_apply": NOT_A_DEVICE,
    "settings_v2.network_delete": NOT_A_DEVICE,
    # The installation's settings record, drawn on History (the operator, 2026-10-27).
    "settings_v2.install_save": ("installation_settings",),
    "settings_v2.install_test": NOT_A_DEVICE,
    "v2.monitoring_alert_explain": "n/a: one AI call, kept in the fleet's ai_calls record, "
                                   "never one device's record",
    "v2.monitoring_alert_history_evidence": "n/a: a past alert's evidence pack, rebuilt and "
                                            "kept in the evidence pack record; reaches no "
                                            "device",
    "v2.history_ask_metrics_words": "n/a: one AI call, kept in the fleet's ai_calls record, "
                                    "never one device's record",
    "v2.history_ask_logs_words": "n/a: one AI call, kept in the fleet's ai_calls record, "
                                 "never one device's record",
    "intent_v2.words": "n/a: one AI call, kept in the fleet's ai_calls record (its subject the "
                       "device); its draft writes nothing, and its commit is intent_v2.commit's",
    "settings_v2.install_replace": ("installation_settings",),
    "settings_v2.install_writes_off": ("installation_settings",),
    "settings_v2.install_ai_allow": ("installation_settings",),
    "settings_v2.install_ai_off": ("installation_settings",),
    "settings_v2.install_ratify": NOT_A_DEVICE,
    "settings_v2.platforms_preview": NOT_A_DEVICE,
    "settings_v2.platforms_apply": NOT_A_DEVICE,
    "settings_v2.diag_drift_interval": NOT_A_DEVICE,
    "settings_v2.diag_drift_switch": NOT_A_DEVICE,
}

#: Sources whose records no gated route above writes: a process that ended holding a device,
#: and the break-glass export's reveal route. Each says which.
WRITTEN_ELSEWHERE = {
    "interrupted": "a process that ended while it held the device (device_ops)",
    "grafana_writes": "every write Mercury sends to Grafana, recorded by the integration that "
                      "sends it (modules/integrations/grafana.py: a silence set, moved or "
                      "expired), whoever it was for",
    "breakglass": "the break-glass export, a reveal route (routes/breakglass.py)",
    # The fleet's own records (C369, board D): about no one device, read by the one timeline.
    "commits": "a commit touching no device's golden or intent: the monitoring profile, the "
               "templates, a policy (every writer, through repo.commit())",
    "decisions": "a Save All's baseline decision, its commit's Baseline: trailer",
    "updates": "the app's updater (deploy/update), not a device",
    "approvals": "the drift check queues an item (modules/drift_check.py) and a capture of the "
                 "device closes it (device_v2.capture_confirm, routes.golden.apply_captures); "
                 "the approve and reject routes left with the AI family (D15)",
    "show_commands": "a Show commands run's record (modules/nsot/reads.py), written by the two "
                     "reveal routes that read devices, Ask the device and Show commands",
    "ai_calls": "the AI gateway's record (modules/ai/calls.py), one row per call, written by "
                "modules/ai/gateway.ask whoever calls it: the connection check "
                "(modules/ai/connection.py) and each Phase 8 feature",
    "reveals": "the reveal record (modules/reveal_audit.py), written by the reveal routes: a "
               "golden version (device_v2.golden_reveal), a bootstrap config "
               "(onboard_v2.bootstrap, onboard.bootstrap, the ZTP responder) and a log line "
               "(v2.history_ask_logs_reveal); today's golden version and diff (golden.version, "
               "golden.diff) left at 7.8 with today's index (P7-27)",
}

#: The history gaps, counted: only down (12 -> 9, 2026-10-12: the three credential profile JSON
#: routes removed at 7.8; 9 -> 7, 2026-10-13: Device files' upload and delete removed at 7.8;
#: 7 -> 5 the same day: Bulk file actions' upload and delete; 5 -> 3, 2026-10-14: the assistant's
#: chat and agent run, removed with the AI family, D15; 3 -> 2, 2026-10-15: today's bulk
#: commands, /bulk_execute, removed at 7.8; 2 -> 1, 2026-10-17: today's /run_command, removed
#: at 7.8 with today's device page, P7-22; 1 -> 0, 2026-10-19: the heartbeat windows'
#: re-measure has its History source, C360, K31).
HISTORY_MISSING_CEILING = 0
