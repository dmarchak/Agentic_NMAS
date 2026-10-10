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
the legacy routes 7.8 removes, and the NetBox writes, which nothing reads back.
"""

from collections import namedtuple

Stages = namedtuple("Stages", "preview hash verify rollback record")

NO_DEVICE = "n/a: changes no device"
LEGACY = "MISSING: a legacy route with no preview or confirm, removed in 7.8 (docs/CUTOVER.md)"
FORWARD = "n/a: a commit, corrected by a forward commit"

STAGES = {
    # ---- Device changes through the deploy pipeline
    "deploy.apply": Stages(
        "deploy.plan", "command_hashes", "modules.pipeline._stage_verify",
        "modules.pipeline._stage_rollback", "routes.deploy._write_receipts"),
    "golden.restore_apply": Stages(
        "golden.restore_preview", "confirmations", "modules.pipeline._stage_verify",
        "modules.pipeline._stage_rollback", "routes.deploy._write_receipts"),
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
    "persist.apply": Stages(
        "persist.preview", "hash", "modules.nsot.onboard.persist_on_device",
        "n/a: a save cannot be undone; the preview says it carries the running config as it is",
        "modules.nsot.persist_op.apply"),
    # The v2 device page's Persist (7.3): the same plan and apply, drawn as a card.
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
    # Devices › Save (C593): persist's save and read-back on each device, then the capture's
    # record, one commit; a device whose read-back did not match is not recorded.
    "v2.save_confirm": Stages(
        "v2.save", "hash", "modules.nsot.onboard.persist_on_device",
        "n/a: a save cannot be undone; the plan says it carries each running config as it is",
        "modules.nsot.save_op.run"),
    "rotate.apply": Stages(
        "rotate.preview", "fingerprint", "modules.nsot.credential_rotation.verify_new_credential",
        "modules.nsot.credential_rotation.revert_commands",
        "modules.nsot.credential_rotation.record_outcome"),
    # The v2 device page's Rotate (7.3): the same confirm, plan and job, drawn as a card.
    "device_v2.rotate_confirm": Stages(
        "device_v2.rotate_preview", "fingerprint",
        "modules.nsot.credential_rotation.verify_new_credential",
        "modules.nsot.credential_rotation.revert_commands",
        "modules.nsot.credential_rotation.record_outcome"),
    "onboard.verify": Stages(
        "onboard.verify_preview", "fingerprint in routes.onboard.verify_run",
        "modules.nsot.onboard.verify_device",
        "n/a: a failed step stops the phase with the device pending and nothing promoted; the "
        "rotation reverts on its held session", "modules.nsot.onboard.record_run"),
    "onboard.create": Stages(
        "onboard.plan",
        "MISSING: Create rebuilds the plan from the same fields; no hash binds it to the preview "
        "(CONCURRENCY_AUDIT R36)",
        "n/a: phase 1 reaches no device", "modules.nsot.onboard.abandon_onboarding",
        "MISSING: Create's run is read back from the pending row, never recorded as a run"),
    "onboard.abandon": Stages(
        "MISSING: a dry run exists on the same route (`dry_run`), and no screen draws it as a "
        "preview", "MISSING: no hash binds the abandon to what was shown",
        "n/a: nothing reached the device", "n/a: abandon is itself the undo of Create",
        "modules.nsot.onboard.record_run"),
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
    "retire.apply": Stages(
        "retire.preview", "hash",
        "n/a: retirement changes no device; the NetBox mask is read back inside the apply",
        "n/a: one commit; a failed commit restores the tree", "modules.nsot.repo.commit"),
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
    "golden.capture_apply": Stages(
        "golden.capture_preview", "confirmations",
        "n/a: records what the device holds; the apply re-reads it and refuses a moved capture",
        FORWARD, "modules.nsot.repo.save_golden"),
    # The v2 device page's Capture (7.3): the same job and apply, one device.
    "device_v2.capture_confirm": Stages(
        "device_v2.capture_start", "hash",
        "n/a: records what the device holds; the apply re-reads it and refuses a moved capture",
        FORWARD, "modules.nsot.repo.save_golden"),
    "templatize.seed_apply": Stages(
        "templatize.seed_preview", "confirmations", NO_DEVICE,
        "n/a: a failed commit puts the file back; a seeded intent is corrected forward",
        "modules.nsot.seed.apply"),
    "templatize.bulk_apply": Stages(
        "templatize.bulk_preview", "confirmed_hash in routes.templatize.bulk_apply_of",
        NO_DEVICE, "n/a: a failed commit puts every file back; one device reverts alone",
        "modules.nsot.bulk_intent.apply"),
    # Devices › Change a setting on the ticked devices (7.4's board D): the same core.
    "bulk_intent_v2.apply": Stages(
        "bulk_intent_v2.preview", "hash", NO_DEVICE,
        "n/a: a failed commit puts every file back; one device reverts alone",
        "modules.nsot.bulk_intent.apply"),
    "templatize.edit_committed": Stages(
        "templatize.preview_committed_edit",
        "MISSING: the save is not bound to the version the person opened (CONCURRENCY_AUDIT R2)",
        NO_DEVICE, FORWARD, "modules.nsot.repo.save_host_vars"),
    "intent_v2.commit": Stages(
        "intent_v2.check",
        "base",   # the blob the editor opened; a moved intent is refused naming both
        NO_DEVICE, FORWARD, "modules.nsot.repo.save_host_vars"),
    "templatize.revert_apply": Stages(
        "templatize.revert_preview", "hash", NO_DEVICE, FORWARD,
        "modules.nsot.intent_ops.revert_apply"),
    # The v2 device page's Revert and Retry (7.3, board 11): the same applies, carrying the list.
    "device_v2.revert_confirm": Stages(
        "device_v2.revert", "hash", NO_DEVICE, FORWARD, "modules.nsot.intent_ops.revert_apply"),
    "device_v2.retire_confirm": Stages(
        "device_v2.retire", "hash",
        "n/a: retirement changes no device; the NetBox mask is read back inside the apply",
        "n/a: one commit; a failed commit restores the tree", "modules.nsot.repo.commit"),
    "device_v2.seed_confirm": Stages(
        "device_v2.seed", "hash", NO_DEVICE,
        "n/a: a failed commit puts the file back; a seeded intent is corrected forward",
        "modules.nsot.seed.apply"),
    "device_v2.retry_confirm": Stages(
        "device_v2.retry", "hash", NO_DEVICE,
        "n/a: a retry is a recorded decision; a new rollback re-records the block",
        "modules.nsot.intent_ops.retry_apply"),
    "templatize.retry_apply": Stages(
        "templatize.retry_preview", "hash", NO_DEVICE,
        "n/a: a retry is a recorded decision; a new rollback re-records the block",
        "modules.nsot.intent_ops.retry_apply"),
    "templatize.profile_propose_apply": Stages(
        "templatize.profile_propose_preview", "hash", NO_DEVICE, FORWARD,
        "modules.nsot.profile_propose.apply"),
    "v2.ip_sla_commit": Stages(
        "v2.ip_sla", "fingerprint", NO_DEVICE, FORWARD, "modules.nsot.ip_sla_policy.apply"),
    "v2.ip_sla_policy_set": Stages(
        "v2.ip_sla", "profile_hash", NO_DEVICE, FORWARD, "modules.nsot.ip_sla_policy.set_policy"),
    # ---- Templates
    "templates.approve": Stages(
        "templates.validate",
        "MISSING: the approval records the closure's fingerprint, but no hash binds the confirm "
        "to the validation the person saw", NO_DEVICE, "modules.nsot.approval.revoke",
        "modules.nsot.approval.approve"),
    "templates.revoke_approval": Stages(
        "n/a: a withdrawal, recorded with its reason", "n/a: nothing is previewed", NO_DEVICE,
        "n/a: approve it again", "modules.nsot.approval.revoke"),
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
    "templates.save_bindings": Stages(
        "MISSING: bindings are saved with no preview", "MISSING: no hash is bound", NO_DEVICE, FORWARD,
        "modules.nsot.repo.save_templates"),
    "templates.write_template": Stages(
        "MISSING: the editor saves with no preview of what the change revokes",
        "MISSING: no hash binds the save to the version opened (CONCURRENCY_AUDIT R14)",
        NO_DEVICE, FORWARD, "modules.nsot.repo.save_templates"),
    # ---- NetBox
    "netbox_safety.apply_import": Stages(
        "netbox_safety.preview_import", "token in modules.netbox_ops.authorize",
        "MISSING: NetBox is not read back after an import; write failures are counted (C8)",
        "n/a: NetBox writes are not transactional; recovery is the tested backup (P.2)",
        "modules.netbox_guard.record_modified"),
    "netbox_safety.apply_import_all": Stages(
        "netbox_safety.preview_import_all", "token in modules.netbox_ops.authorize",
        "MISSING: NetBox is not read back after an import; write failures are counted (C8)",
        "n/a: NetBox writes are not transactional; recovery is the tested backup (P.2)",
        "modules.netbox_guard.record_modified"),
    "netbox_safety.apply_removal": Stages(
        "netbox_safety.preview_removal", "token in modules.netbox_ops.authorize",
        "MISSING: deletions are counted, and the cascade is not re-read after (C150)",
        "n/a: a deletion; recovery is the tested backup (P.2)",
        "modules.netbox_guard.record_removal"),
    # v2's NetBox page (cutover blocker 2): the same core as today's routes, its preview a job.
    "netbox_v2.confirm": Stages(
        "netbox_v2.preview", "token in modules.netbox_ops.authorize",
        "MISSING: NetBox is not read back after an import; write failures are counted (C8)",
        "n/a: NetBox writes are not transactional; recovery is the tested backup (P.2)",
        "modules.netbox_guard.record_modified"),
    # ---- Decisions and the queue
    "ai_approval_approve": Stages(
        "n/a: approving hands off to the restore or capture preview, where the change is previewed",
        "n/a: the handoff's own confirm binds the hash", NO_DEVICE,
        "n/a: the handed-off operation rolls back", "modules.approval_queue.resolve"),
    "ai_approval_reject": Stages(
        "n/a: a rejection changes nothing", "n/a: nothing is previewed", NO_DEVICE, "n/a: nothing to undo",
        "modules.approval_queue.resolve"),
    "ai_agent_run": Stages(
        "n/a: starts an agent run whose tools are read-only (P.3 step 8)", "n/a: nothing is previewed",
        NO_DEVICE, "n/a: nothing to undo", "modules.agent_runner._append_activity"),
    "ai_chat": Stages(
        "n/a: a conversation whose tools are read-only (P.3 step 8)", "n/a: nothing is previewed",
        NO_DEVICE, "n/a: nothing to undo",
        "n/a: kept as the session's chat history, not an operation's record"),
    "refresh_hostnames": Stages(
        "MISSING: no preview of the renames it will record", "MISSING: no hash is bound",
        "n/a: reads hostnames; records a pending rename only", "n/a: a pending rename is undone by "
        "the next refresh", "modules.nsot.manifest.record_pending_rename"),
    # ---- Legacy device routes, removed or replaced at cutover
    "run_command": Stages(LEGACY, LEGACY, LEGACY, "n/a: a command is not undone", LEGACY),
    "bulk_execute": Stages(LEGACY, LEGACY, LEGACY, "n/a: a command is not undone", LEGACY),
    "bulk_reload": Stages(
        "MISSING: no gates or preview; reload becomes P.14's gated operation", LEGACY, LEGACY,
        "n/a: a reload cannot be undone", "modules.restarts.record_planned"),
    "upload_file": Stages(LEGACY, LEGACY, LEGACY, LEGACY, LEGACY),
    "bulk_tftp_upload": Stages(LEGACY, LEGACY, LEGACY, LEGACY, LEGACY),
    "delete_file": Stages(LEGACY, LEGACY, LEGACY, "n/a: a deleted file cannot be restored", LEGACY),
    "bulk_delete_file": Stages(LEGACY, LEGACY, LEGACY, "n/a: a deleted file cannot be restored",
                               LEGACY),
}

#: The gaps, counted: the test pins this number, so it can only go down.
# +1 2026-10-10: v2's NetBox confirm shares today's import's missing read-back (C8); today's three
# NetBox entries leave at 7.8 and take theirs with them.
# +1 2026-10-10: v2's Create shares today's Create's missing run record (one core); v2's
# Create and Abandon bind their confirms, so today's two hash gaps and Abandon's preview gap
# leave with today's routes at 7.8.
MISSING_CEILING = 46


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
NO_RECORD = ("MISSING: a legacy route that keeps no per-device record of what it did; "
             "removed in 7.8 (docs/CUTOVER.md)")

HISTORY = {
    # ---- confirm: sends to a device
    "deploy.apply": ("receipts", "golden"),
    "golden.restore_apply": ("receipts", "golden"),
    "v2.profile_apply_confirm": ("receipts", "golden"),
    "device_v2.deploy_confirm": ("receipts", "golden"),
    "device_v2.restore_confirm": ("receipts", "golden"),
    "persist.apply": ("rotation",),
    "device_v2.persist_confirm": ("rotation",),
    "v2.save_confirm": ("rotation", "golden"),
    "rotate.apply": ("rotation", "golden", "intent"),
    "device_v2.rotate_confirm": ("rotation", "golden", "intent"),
    "onboard.verify": ("onboarding", "golden"),
    "onboard.abandon": ("onboarding",),
    "onboard_v2.verify": ("onboarding", "golden"),
    "adopt_v2.confirm": ("onboarding", "golden"),
    "device_v2.reload_confirm": ("reloads", "restart_windows", "restarts"),
    "v2.history_reapply_confirm": ("receipts", "golden"),
    "onboard_v2.abandon": ("onboarding",),
    "bulk_reload": ("restart_windows", "restarts"),
    "update.apply": NOT_A_DEVICE,
    "update.step_done": NOT_A_DEVICE,
    "run_command": NO_RECORD,
    "bulk_execute": NO_RECORD,
    "bulk_tftp_upload": NO_RECORD,
    "bulk_delete_file": NO_RECORD,
    "upload_file": NO_RECORD,
    "delete_file": NO_RECORD,
    "ai_chat": ("MISSING: the assistant's device tools keep no per-device record; removed "
                "by P.3 step 8"),
    "ai_agent_run": ("MISSING: the agent's device tools keep no per-device record; removed "
                     "by P.3 step 8"),
    # ---- approve: a decision a later device change acts on
    "golden.capture_apply": ("golden", "measured"),
    "device_v2.capture_confirm": ("golden", "measured"),
    "ai_approval_approve": ("approvals",),
    "ai_approval_reject": ("approvals",),
    "onboard.create": ("intent",),
    "onboard_v2.create": ("intent",),
    "refresh_hostnames": ("golden",),
    "templatize.seed_apply": ("intent",),
    "templatize.edit_committed": ("intent",),
    "intent_v2.commit": ("intent",),
    "templatize.bulk_apply": ("intent",),
    "bulk_intent_v2.apply": ("intent",),
    "templatize.revert_apply": ("intent",),
    "templatize.retry_apply": ("retries",),
    "device_v2.revert_confirm": ("intent",),
    "device_v2.retry_confirm": ("retries",),
    "device_v2.seed_confirm": ("intent",),
    "device_v2.retire_confirm": ("n/a: a retired device has no History tab; its address shows its retired record, read from the retire commit (C185)"),
    "v2.ip_sla_commit": ("intent",),
    "retire.apply": ("n/a: a retired device has no page to hold a History tab; its record is "
                     "the retire commit, read by the legacy golden history (C185)"),
    "netbox_safety.apply_import": ("n/a: a NetBox object's record, kept per object with its "
                                   "provenance, which the device's NetBox tab draws"),
    "netbox_safety.apply_import_all": ("n/a: NetBox objects' records, kept per object with "
                                       "their provenance, drawn on each device's NetBox tab"),
    "netbox_safety.apply_removal": ("n/a: removes NetBox objects; the removal record is per "
                                    "object, drawn on the NetBox tab"),
    "netbox_v2.confirm": ("n/a: NetBox objects' records, kept per object with their provenance, "
                          "drawn on each device's NetBox tab and, for a removal, on the NetBox page"),
    "templatize.profile_propose_apply": PROFILE,
    "v2.ip_sla_policy_set": PROFILE,
    "templates.approve": TEMPLATE,
    "templates.revoke_approval": TEMPLATE,
    "templates_v2.approve": TEMPLATE,
    "templates_v2.revoke": TEMPLATE,
    "templates_v2.bring": TEMPLATE,
    "templates_v2.edit_commit": TEMPLATE,
    "templates_v2.bindings_apply": TEMPLATE,
    "templates_v2.seed": TEMPLATE,
    "v2.profile_propose_commit": PROFILE,
    "templates.save_bindings": TEMPLATE,
    "templates.write_template": TEMPLATE,
    # ---- configure
    # A saved command set (C548, R3): a commit as the person, read as one of the fleet's commits.
    "reads_v2.show_commands_save_set": ("commits",),
    # The columns ignored when grouping a run (C580): recorded on that run, drawn on its row.
    "reads_v2.show_commands_ignore": ("show_commands",),
    "privileged_v2.confirm": ("privileged",),
    "attention.acknowledge": ("acknowledgements", "restarts"),
    "restarts.planned": ("restart_windows",),
    "golden.migrate_apply": ("golden",),
    "golden.sync_renames": ("golden",),
    "inventory.copy_inherited": ("MISSING: a credential override is saved with no time or "
                                 "person (credentials.py keeps no audit)"),
    "inventory.credential_profiles": ("MISSING: a credential profile is saved with no time "
                                      "or person (credentials.py keeps no audit)"),
    "inventory.delete_credential_profile": ("MISSING: a deleted credential profile leaves no "
                                            "record of who or when"),
    "v2.credentials_intact": ("breakglass",),
    "v2.credentials_check": ("breakglass",),
    "v2.credentials_drill": ("breakglass",),
    "v2.heartbeat_apply": ("MISSING: the heartbeat windows' record "
                           "(heartbeat_rules.jsonl) has no History source yet"),
    "monitoring_config": "n/a: the collectors' settings, never one device's record",
    "inventory.set_order": NOT_A_DEVICE,
    "inventory.set_source": NOT_A_DEVICE,
    "reorder_devices": NOT_A_DEVICE,
    "add_quick_action": NOT_A_DEVICE,
    "delete_quick_action": NOT_A_DEVICE,
    "ai_agent_pause": NOT_A_DEVICE,
    "ai_agent_resume": NOT_A_DEVICE,
    "ai_agent_timers_post": NOT_A_DEVICE,
    "ai_delete_playbook": NOT_A_DEVICE,
    "ai_events_clear": NOT_A_DEVICE,
    "ai_set_provider": NOT_A_DEVICE,
    "clear_netflow_flows": NOT_A_DEVICE,
    "clear_snmp_traps": NOT_A_DEVICE,
    "create_device_list_route": NOT_A_DEVICE,
    "delete_backup_route": NOT_A_DEVICE,
    "delete_device_list_route": NOT_A_DEVICE,
    "drift_settings_post": NOT_A_DEVICE,
    "identity.ratify_setting": NOT_A_DEVICE,
    "list_compliance_policy_update": NOT_A_DEVICE,
    "list_variables_delete": NOT_A_DEVICE,
    "list_variables_discover": NOT_A_DEVICE,
    "list_variables_set": NOT_A_DEVICE,
    "save_settings": NOT_A_DEVICE,
    "save_tftp_server": NOT_A_DEVICE,
    "select_device_list_route": NOT_A_DEVICE,
    "settings_integrations.general_settings": NOT_A_DEVICE,
    "settings_integrations.save_integration": NOT_A_DEVICE,
    "settings_v2.group_switch": NOT_A_DEVICE,
    "settings_v2.mode_switch": NOT_A_DEVICE,
    "settings_v2.group_save": NOT_A_DEVICE,
    "settings_v2.group_test": NOT_A_DEVICE,
    "settings_v2.records_save": NOT_A_DEVICE,
    "settings_v2.records_test": NOT_A_DEVICE,
    "settings_v2.records_replace": NOT_A_DEVICE,
    "settings_v2.records_store_apply": NOT_A_DEVICE,
    "network_v2.choose": NOT_A_DEVICE,
    "settings_v2.network_create": NOT_A_DEVICE,
    "settings_v2.network_source_apply": NOT_A_DEVICE,
    "settings_v2.network_delete": NOT_A_DEVICE,
    "settings_v2.install_save": NOT_A_DEVICE,
    "settings_v2.install_test": NOT_A_DEVICE,
    "settings_v2.install_replace": NOT_A_DEVICE,
    "settings_v2.install_writes_off": NOT_A_DEVICE,
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
    "breakglass": "the break-glass export, a reveal route (routes/breakglass.py)",
    # The fleet's own records (C369, board D): about no one device, read by the one timeline.
    "commits": "a commit touching no device's golden or intent: the monitoring profile, the "
               "templates, a policy (every writer, through repo.commit())",
    "decisions": "a Save All's baseline decision, its commit's Baseline: trailer",
    "updates": "the app's updater (deploy/update), not a device",
    # Phase 3 removed the freshness gate and its writer; what it recorded stays readable.
    "freshness": "past authorisations past the retired freshness gate: written by nothing now",
    "show_commands": "a Show commands run's record (modules/nsot/reads.py), written by the two "
                     "reveal routes that read devices, Ask the device and Show commands",
}

#: The history gaps, counted: only down.
HISTORY_MISSING_CEILING = 12
