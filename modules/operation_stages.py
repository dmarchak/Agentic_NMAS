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
    # ---- Device operations of their own
    "persist.apply": Stages(
        "persist.preview", "hash", "modules.nsot.onboard.persist_on_device",
        "n/a: a save cannot be undone; the preview says it carries the running config as it is",
        "modules.nsot.persist_op.apply"),
    # The v2 device page's Persist (7.3): the same plan and apply, drawn as a card.
    "device_v2.persist_confirm": Stages(
        "device_v2.persist", "hash", "modules.nsot.onboard.persist_on_device",
        "n/a: a save cannot be undone; the preview says it carries the running config as it is",
        "modules.nsot.persist_op.apply"),
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
        "onboard.verify_preview", "fingerprint", "modules.nsot.onboard.verify_device",
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
        "templatize.bulk_preview", "confirmed_hash", NO_DEVICE,
        "n/a: a failed commit puts every file back; one device reverts alone",
        "modules.nsot.bulk_intent.apply"),
    "templatize.edit_committed": Stages(
        "templatize.preview_committed_edit",
        "MISSING: the save is not bound to the version the person opened (CONCURRENCY_AUDIT R2)",
        NO_DEVICE, FORWARD, "modules.nsot.repo.save_host_vars"),
    "templatize.revert_apply": Stages(
        "templatize.revert_preview", "hash", NO_DEVICE, FORWARD,
        "modules.nsot.intent_ops.revert_apply"),
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
    "templates.save_bindings": Stages(
        "MISSING: bindings are saved with no preview", "MISSING: no hash is bound", NO_DEVICE, FORWARD,
        "modules.nsot.repo.save_templates"),
    "templates.write_template": Stages(
        "MISSING: the editor saves with no preview of what the change revokes",
        "MISSING: no hash binds the save to the version opened (CONCURRENCY_AUDIT R14)",
        NO_DEVICE, FORWARD, "modules.nsot.repo.save_templates"),
    # ---- NetBox
    "netbox_safety.apply_import": Stages(
        "netbox_safety.preview_import", "token in routes.netbox_safety._authorize",
        "MISSING: NetBox is not read back after an import; write failures are counted (C8)",
        "n/a: NetBox writes are not transactional; recovery is the tested backup (P.2)",
        "modules.netbox_guard.record_modified"),
    "netbox_safety.apply_import_all": Stages(
        "netbox_safety.preview_import_all", "token in routes.netbox_safety._authorize",
        "MISSING: NetBox is not read back after an import; write failures are counted (C8)",
        "n/a: NetBox writes are not transactional; recovery is the tested backup (P.2)",
        "modules.netbox_guard.record_modified"),
    "netbox_safety.apply_removal": Stages(
        "netbox_safety.preview_removal", "token in routes.netbox_safety._authorize",
        "MISSING: deletions are counted, and the cascade is not re-read after (C150)",
        "n/a: a deletion; recovery is the tested backup (P.2)",
        "modules.netbox_guard.record_removal"),
    # ---- Decisions and the queue
    "freshness.authorise": Stages(
        "freshness.report", "fingerprint", NO_DEVICE, "n/a: an authorisation expires in 24 h",
        "modules.nsot.freshness.authorise"),
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
MISSING_CEILING = 44
