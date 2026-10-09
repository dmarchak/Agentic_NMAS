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
  phase's first step. Its draft is [NSOT_PHASE4_MINIO](NSOT_PHASE4_MINIO.md).

## 6. The PostgreSQL container: the operator's host step (DRAFT, 2026-10-08)

Measured read-only on the NMAS host, 2026-10-08 (via LAN): NetBox's database runs in
`netbox-docker-postgres-1`, PostgreSQL 18.6; the host has 4 CPUs, 15 GiB of memory (10
available) and 244 GiB free on `/`; the app's interpreter has no PostgreSQL driver (`psycopg`
and `psycopg2` both absent).

**What ships in the commit** (each a host-installed file, so the commit carries its
`Host-Step:`, rendered into a fresh `mktemp -d` and installed by name):

- `deploy/postgres/docker-compose.yml`: one service, `mercury-postgres`, image `postgres:18`
  pinned by digest (NetBox's major, so one major to patch), its own named volume
  `mercury-pgdata`, published on `127.0.0.1:<port>` only (never the LAN), `restart:
  unless-stopped`, a health check (`pg_isready`). Nothing shared with NetBox: its own network,
  volume and credentials (P4-1).
- `deploy/systemd/nmas-records-backup.{service,timer}` and
  `nmas-records-restore-test.{service,timer}`, templates rendered by `nmas-render-units`.
- `scripts/nmas-records-backup` and `scripts/nmas-records-restore-test`, NetBox's pair as the
  pattern: a dump `pg_dump -Fc` on an exported snapshot with per-table row counts taken in the
  same snapshot, a manifest with every file's sha256, complete-or-absent (`.partial` renamed
  last), shipped to MinIO `records/<date>.dump` (M-4's retention); the restore test restores the
  newest dump into a scratch database in the same container, compares every table's count with
  the manifest (both numbers named on a mismatch), reads the newest row of each table, and drops
  the scratch database. Both run outside 08:30 to 09:10 UTC.
- Settings: `records_db_host`, `records_db_port`, `records_db_name`, `records_db_user` and
  `records_db_password` (a secret, in the secrets backend), defaults empty: empty means every
  store stays on files, which is today's behaviour. A setting because no measurement can find a
  database's address and password.

**Step 6a, built (2026-10-09): the container and the driver, as a script the operator runs.**
`scripts/host-steps/postgres-6a.sh` installs `deploy/postgres/docker-compose.yml` and
`deploy/postgres/initdb/10-mercury.sh` by name from a fresh `mktemp -d` into
`/opt/mercury-postgres/`, writes the root-only env file (the superuser's password generated and
never shown, Mercury's PROMPTED, hidden), starts `mercury-postgres`, and installs the driver as
the host's apt package, `python3-psycopg` 3.1.17-2 (the boto3 decision's shape: no pip into the
system interpreter), after a dry run shows it changes no other package. Its checks: healthy,
PostgreSQL 18, `mercury` owns `mercury` and is not a superuser, 5433 on 127.0.0.1 only, NetBox's
container not restarted, the interpreter imports psycopg 3.1.17, psycopg signs in as `mercury`
on 127.0.0.1:5433 with the password entered, and a wrong one is refused. Measured for it, read
only on the host 2026-10-09 (via LAN): Ubuntu 24.04.4; NetBox's image `postgres:18-alpine` at
digest `d3e1620b…` (2026-08-13), its data volume at `/var/lib/postgresql` (PostgreSQL 18's
layout); `python3-psycopg` 3.1.17-2 available, `libpq5` 16.15 installed; nothing on 5433.
Walked on a throwaway copy of the image, 2026-10-09: the init script makes the role and the
database (ready in about 4 s); inside the container the image TRUSTS loopback, and through the
published port it asks for the password (scram-sha-256): the right one signs in, a wrong one is
refused. The backup and restore-test units and scripts below come with the receipts store,
when there is a record to dump; the lock is regenerated from the host once psycopg is there.

The run: `bash <checkout>/scripts/host-steps/postgres-6a.sh` on the NMAS host.

**The first run failed (C600, 2026-10-09):** the init folder was installed 0750 root-only, the
image's entrypoint lists it as `postgres` (uid 70) and stopped before `initdb`, and the
container restarted eleven times with its volume left empty. The walk above had mounted the
repository's world-readable folder, not the folder as installed. The script now installs it
0755, has the image's own `postgres` user list it as installed before the start, and recreates
the container on start (its volume kept). The re-run enters the same password: the env file
written by the first run is kept.

**Step 6a done (the operator, 2026-10-09, on 875cf27): PASS, 15 of 15.** PostgreSQL 18 healthy
on 127.0.0.1:5433 only, `mercury` not a superuser, NetBox's database not restarted, psycopg
3.1.17-2 from apt with `python3-typing-extensions` as its dependency, the operator's password
signs in and a wrong one is refused. The lock was then regenerated on the host by the deployed
`scripts/nmas-lock-from-host` (read only): it printed the committed lock exactly (82 lines,
nothing missing), because no deployed code imports psycopg yet; psycopg and typing-extensions
enter it after the release that does (boto3's order).

**The host's kernel reboot (2026-10-09, 6.8.0-139 to 6.8.0-142).** Before it, read only: every
container's restart policy and every unit's state, so what comes back on its own was known
(the two Oxidized containers stay stopped: `restart=no`, and a stopped `unless-stopped`).
After it, the operator's `post-reboot-check.sh`: PASS, 14 of 14 (the new kernel, every
service, timer, socket and container back and healthy, Oxidized stopped, the policies
unchanged, every health endpoint 200, Mercury's records database answering on 127.0.0.1:5433
only, no failed unit but `openipmi.service`, which had failed before). The fleet, read only
after the boot at 03:20:32 UTC: Prometheus up for all 9 devices (5 IOS-XE, 4 IOS) with no
target down; syslog in Loki from all 9 (r1 to r4, r6, s1 to s4; 23 lines in nine streams by
03:33). The check script, declared one-off, was removed once run.

**The host step as first drafted** (kept for the backup units' part, which ships with the
receipts store):

```bash
d=$(mktemp -d) && cp <checkout>/deploy/postgres/docker-compose.yml "$d/" \
  && sudo install -d -m 0750 /opt/mercury-postgres \
  && sudo install -m 0640 "$d/docker-compose.yml" /opt/mercury-postgres/docker-compose.yml
# The superuser's and Mercury's passwords, generated on the host into a root-only env file;
# Mercury's is then entered in Settings (v2), never echoed.
sudo docker compose -f /opt/mercury-postgres/docker-compose.yml up -d
sudo docker exec mercury-postgres pg_isready          # accepting connections
# The driver, then the lock regenerated from the host (requirements.lock's rule).
<venv>/bin/pip install --no-deps psycopg==<version> <its closure>
d=$(mktemp -d) && scripts/nmas-render-units --out "$d" deploy/systemd/nmas-records-backup.service \
  deploy/systemd/nmas-records-backup.timer deploy/systemd/nmas-records-restore-test.service \
  deploy/systemd/nmas-records-restore-test.timer \
  && sudo install -m 0644 "$d/nmas-records-backup.service" "$d/nmas-records-backup.timer" \
     "$d/nmas-records-restore-test.service" "$d/nmas-records-restore-test.timer" /etc/systemd/system/ \
  && sudo systemctl daemon-reload && sudo systemctl enable --now nmas-records-backup.timer \
     nmas-records-restore-test.timer
```

**What the operator checks afterwards:** `docker ps` shows `mercury-postgres` healthy and
NetBox's container untouched; Settings' records database Test connects and names the server
version; the first backup run's manifest lists every table with its count; the first restore
test reads "every table matches"; `ss -ltn` shows the port on 127.0.0.1 only.

**Decisions (APPROVED by the operator, 2026-10-08, with the receipts migration and its count
check in section 7):** **PG-1**, the port (measured 2026-10-08: NetBox's database publishes no port on the
host, and nothing listens on 5432 or 5433; `5433` recommended, so a person's `psql` on 5432
never reaches the wrong one); **PG-2**, the dump's
retention locally (3 days recommended; MinIO holds the rest, M-4).

**Testing (the operator's decision, 2026-10-08, option a):** a real PostgreSQL in CI (a
service container) and a throwaway instance started by the local suite inside its own
namespace, skipped with a named reason when the PostgreSQL binaries are absent; never a
stand-in database or fakes alone.

## 7. The first store: deploy receipts, and its count check (DRAFT, 2026-10-08)

**Measured on the host, 2026-10-08:** one network (`default`), `deploy_receipts.jsonl` 67 lines,
of which 26 are completions (a line filling in a pending row's commit) and 41 rows, 65,013
bytes, the first row 2026-09-27T18:53:37Z, mode 0600.

**The table keeps the file's shape exactly**, so the merge (`receipts._merged`) runs unchanged on
either backend and the comparison is line for line:

- `audit.receipt_lines (seq bigserial, network text, kind text ('row'|'completion'), id text,
  completes text, at timestamptz, body jsonb, line_sha256 bytea, source_line int NULL)`, unique
  on `(network, source_line)` for migrated lines (two identical lines in a file stay two lines);
  new lines have no `source_line`. `receipts.read` selects a network's lines in `seq` order and
  merges them as today; `receipts.write` inserts one line per row in one transaction (R32's
  several-rows-per-handle shape cannot recur).

**The switch is per store (P4-2):** a setting `records_store_receipts`, `file` (the default,
today's behaviour) or `postgres`, read at each call, so every process changes together.

**The migration, `nmas-records-migrate receipts`:**

1. `--dry-run`: reads every network's file and prints, per network, lines, rows and completions
   (today: default 67 = 41 + 26). Writes nothing.
2. `--apply`: inserts each file line with its `source_line`; a line already there (same network
   and line number, same sha256) is skipped, and one there with a DIFFERENT sha256 refuses,
   naming the network, the line and both hashes. Safe to run again.
3. The switch to `postgres` (a Mercury settings write, recorded as you).
4. `--apply` again: catches any line a deploy appended between steps 2 and 3.
5. `--check`, and the same check as a job-health row each cycle for the release that follows:
   per network, the file's line count against the table's migrated-line count (by line number),
   every line's sha256 equal, and `receipts.read(network, limit=all)` from each backend equal
   row for row. A mismatch is a Needs attention row naming the network, both counts and the
   first differing line; a match reads "receipts: file 67 lines, table 67, merged 41 = 41".
6. The file is made read-only (0400) for one release (P4-4); a line appended to it after the
   switch is itself a mismatch (the file's count moved), so a writer still on files is seen.
7. The release after: the files are deleted by a host step, only after the check has read
   "matches" since the switch.

**Rollback:** the switch back to `file` restores the old behaviour at once, but receipts written
to the table since the switch are not in the file; `nmas-records-migrate receipts --export`
appends them, so a rollback loses nothing. That is why the file stays for a release.

**Tests the build brings:** the merge equal on both backends over the real 67-line file's shape
(a fixture from a real capture, masked); two identical lines kept as two; a differing line
refused naming both hashes; the check failing on a moved count, a changed line and a merged
difference (each shown able to fail); `write` on PostgreSQL inserting a batch atomically.
