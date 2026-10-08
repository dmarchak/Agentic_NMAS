# Phase 4: Mercury's records in PostgreSQL (APPROVED by the operator, 2026-10-08; decisions in section 5)

The charter ("Mercury's own records"): receipts, acknowledgements, approvals, rollback blocks,
restart windows, runbook runs and the readers' stored values are the audit trail of Mercury's
actions; Mercury owns them, and they are consolidated into ONE store, a database of its own,
archived to MinIO past retention. This draft inventories every store Mercury writes outside git
today (surveyed from the code, read-only, 2026-10-08), sketches the schema, the migration order,
and the backup and restore-test job. Nothing is built until it is signed off.

## 1. Inventory: what Mercury keeps outside git today

About 30 file stores, in four places: the per-network `lists/<slug>/`, the installation-wide
`DATA_DIR`, `DATA_DIR/device_ops/<slug>/`, the gitignored `config_repo/.nsot/`, and root's
`/var/lib/nmas-update`.

**The audit trail (moves to PostgreSQL):**

| Store | Today | Scope | Safety today |
|---|---|---|---|
| Deploy receipts | `lists/<slug>/deploy_receipts.jsonl` | network | append, **no lock, several rows per handle (R32, unsafe)** |
| Acknowledgements | `acknowledgements.jsonl` | installation (rows carry devices) | locked append |
| Approval queue | `lists/<slug>/approval_queue.json`, one array | network | locked, atomic; expired items never removed |
| Rollback blocks, retry log | `config_repo/.nsot/rolled_back.json`, `retry_log.json` | network | locked, atomic |
| Restarts seen, planned windows | `restarts.jsonl`, `planned_restarts.jsonl` | installation | locked append |
| Rotation record | `rotation_audit.jsonl` | installation (rows name no network) | append, no lock |
| Break-glass exports, intact checks, checks, drills | four `breakglass_*.jsonl` | installation | append; salted digests (an oracle, owner-only) |
| Interrupted holds | `device_ops/<slug>/interrupted.jsonl` | network | append |
| Show commands runs | `lists/<slug>/reads/<run>.json` | network | one file per run; answers to MinIO after retention |
| Settings record, inventory edits, onboarding runs | three `*.jsonl` per network | network | append |
| Reveal audit, host steps done, heartbeat rules | three `*.jsonl` | installation | append |
| NetBox provenance and removals | `netbox_*.json[l]` | installation | locked |
| Update requests and history | `update_requests.jsonl`; root's `/var/lib/nmas-update/history.jsonl` | host | append / replace |
| Pipeline audit | `pipeline_audit/<config_id>.json` | installation | plain write |
| Reader stored values | `readers/<name>.json` (last good, last attempt, 20 runs) | installation | locked, atomic |

**Stays where it is:** the secrets and inventory (`key.key`, `devices.csv`, credential profiles,
`user_settings.json`, list settings: secrets stay behind the secrets interface, Stage 10's Vault
option), the device holds (`flock` files: a lock, not a record), files committed in git
(`.approvals.json`, `manifest.json`), the pre-change snapshots (they hold credentials and are a
device's latest only), and the AI assistant's stores (Stage 8 redesigns them).

**Gaps the move closes:** R32 (receipts), R33's unsafe stores among these, R4/R31/R34 (the
approval queue: two approvers, `requested_by`), and History reads most of them already; it does
not read the settings record, inventory edits, reveal audit, host steps, NetBox provenance, the
other three break-glass logs or the reader values (candidates once they are one store).

## 2. Schema sketch

One database, `mercury`, one schema per concern, every row carrying its network (or `NULL` for
the installation's own), its time in UTC, its actor and `actor_verified`, and its record as
JSONB beside the columns queries filter on:

- `audit.receipts (id, network, device, batch_id, at, actor, actor_verified, outcome, program_hash, body jsonb)`
- `audit.acknowledgements (id, network, devices text[], kind, at, actor, reason, clears jsonb)`
- `audit.approvals (id, network, device, status, requested_by, resolved_by, created_at, resolved_at, body jsonb)`,
  with `UPDATE ... WHERE id = $1 AND status = 'pending'` for two approvers
- `audit.rollback_blocks`, `audit.retries`, `audit.restarts`, `audit.restart_windows`,
  `audit.rotations`, `audit.breakglass (kind: export|intact|check|drill, ...)`,
  `audit.interrupted`, `audit.onboarding_runs`, `audit.settings_changes`, `audit.inventory_edits`,
  `audit.reveals`, `audit.host_steps`, `audit.netbox_provenance`, `audit.updates`,
  `audit.pipeline_runs`
- `reads.runs (id, network, by, actor, purpose, started_at, finished_at, state, commands text[], refused)`
  and `reads.answers (run_id, device, command, state, why, bytes, cut, sha256, answer text NULL, archived_key)`
- `readers.values (name, group, read_at, value_at, ok, value jsonb, error)` and `readers.runs`

Append-only tables are written by one INSERT per row (the R32 shape cannot recur); History reads
each by one indexed query per request (the enterprise-scale rule).

## 3. Migration order

1. **The store interface first:** each writer and reader already goes through one module per
   store (receipts, acknowledgements, approval_queue, restarts, ...). Each gains a PostgreSQL
   backend behind the same functions; the file backend stays, chosen per store for the whole
   installation (P4-2), so a store runs on files until it is moved.
2. **One store at a time, receipts first** (it is the one unsafe today and the one History reads
   most): copy every file row into the table (idempotent, by row hash), read both and compare,
   switch the backend, keep the file read-only for a release with the count check, then delete
   it (P4-4).
3. Then the approval queue (its concurrency fix), acknowledgements, restarts and windows,
   rollback blocks and retries, rotation and break-glass, the Show commands runs (answers past
   retention to MinIO as today), the readers' values, the rest.
4. History's sources move with their store; each keeps its "unreadable is said" contract.

## 4. Backup and the restore test

- **Backup:** `pg_dump` nightly, outside the hypervisor's 08:30 to 09:10 UTC window, to the
  network's S3/MinIO archive (the same integration the goldens use), kept by a retention setting;
  WAL archiving later if the recovery point needs it.
- **Restore test, a job:** nightly, restore the newest dump into a scratch database, count rows
  per table against the source, read the newest row of each table back, and drop the scratch
  database; a failure is a job-health row naming the table and both counts (the NetBox
  backup-and-restore-test timers are the pattern: `nmas-netbox-backup.timer`,
  `nmas-netbox-restore-test.timer`).

## 5. Decisions (APPROVED by the operator, 2026-10-08)

- **P4-1, a container on the NMAS host, separate from NetBox's database:** its own container,
  its own volume and its own backup; nothing shared with NetBox's PostgreSQL. A separate host is
  Stage 10's high-availability step.
- **P4-2, installation-wide, store by store:** one setting for the installation, and the move
  goes one store at a time (receipts first, section 3), never network by network. Section 3's
  per-network backend setting is replaced by a per-store switch.
- **P4-3, the AI assistant's stores stay out** (Stage 8 redesigns them).
- **P4-4, read-only for one release, counted, then deleted:** after each store moves, its old
  files stay read-only for one release; a count check shows the migration matches (rows per
  file against rows per table, by row hash, both numbers named); then the files are deleted in
  the release after.
- **Order:** after Phase 3. **Mercury's connection to MinIO comes first**; it serves the
  Oxidized archive (Phase 3's P3-1), the record dumps and the Show commands answers past 30 days.
- **Prerequisite: Mercury's connection to MinIO.** MinIO EXISTS (the data lake: raw telemetry,
  `mdt/` 30 days, `syslog/` 2 years; the operator, 2026-10-08); what is missing is Mercury's
  connection to it: its settings, its credentials and an S3 client (the per-network S3 archive
  integration is not configured on the host, and the minio SDK is not installed, measured
  2026-10-08). The same connection carries the dumps and the Show commands answers past their
  30 days (folded in here by the operator's decision; `reads.expire` is the hook), so it is this
  phase's first step.
