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

**As built (2026-10-09):** a service container is out of reach of the suite, which runs inside
its own loopback namespace (C46), so CI too runs the throwaway server the suite starts
(`tests/pg_instance.py`: unpacked binaries, a temporary folder, loopback, the superuser and the
role `mercury` owning `mercury`, scram-sha-256 over TCP, as 6a makes them). The workflow installs
`libpq5` and the server's libraries explicitly and unpacks `postgresql-18` from PGDG's
repository (the host's major; Ubuntu 24.04 ships 16, and the Test's version check is not
loosened for CI: the operator, 2026-10-09), fails its step if a library is missing, the server is
not 18 or psycopg cannot load, and sets `NMAS_REQUIRE_PG=1`, which turns the tests' skip into a
failure (a missing libpq fails the job). The gate sets it too, with the unpacked libpq on the
suite's library path. Locally the same unpacked PostgreSQL 18 (docs/TESTING.md, "CI's
interpreter here").

**The Test checks what 6a made, six checks** (board F2, the operator's condition, 2026-10-09):
signs in; the server is PostgreSQL 18; the role owns its database; the role is not a
superuser; Mercury reaches it on a loopback address (every address the host names); a temporary
row written and read back, rolled back. The first that fails is named with what the server
said; the rest are "not tried" (`records_db.TEST_STEPS`, `STEP_WORDS`).

**Rotating the role's password: the server first, then Mercury** (board F2). `scripts/host-steps/
postgres-rotate.sh` prompts for the new password (hidden, 6a's rules), sends the server a
SCRAM-SHA-256 verifier computed on the host, never the password (so it is in no statement log
and on no command line), replaces the env file's copy so the kept credential is the current one,
and proves the new password signs in and a wrong one is refused, with the interpreter the app
runs. Proved on the laptop against PostgreSQL 18 (2026-10-09): the server stored the verifier as
sent, the new password signed in, a wrong one and the old one were refused; a test recomputes
the verifier by RFC 7677's arithmetic. Then Mercury's half: Settings › Installation › Records
database › Replace…, the same password, and Test. Between the two, Mercury holds the old password
and cannot reach its records.

## 7. The first store: deploy receipts, and its count check (BUILT 2026-10-10; DRAFT 2026-10-08)

**As built** (under the Phase 7 operating mode; docs/STANDING_APPROVAL_LOG.md), where it differs
from the draft below:

- **The migration is a person's operation on v2, not a CLI.** Settings › Installation ›
  Connections gained **Record stores**: each store, where it is and its last check, with **Move
  to the database…** and **Move back to files…**, each a preview and a confirm bound to it
  (`modules/records_migrate.py`, `MOVE_STEPS` and `BACK_STEPS`; the manual's records-database
  page, #move and #back). Steps 2 to 6 below run as one operation, so the window between the
  copy and the switch is the operation's own, and the step-3 settings write is recorded as the
  person. `nmas-records-migrate` was not written: a host command would be a second home for the
  same action, and the operator's rule is no terminal steps.
- **A failed check after the switch switches back at once**, exporting any line written to the
  table in between, so the store is never left half-moved (rollback on failure).
- **The move back is `--export` and the switch together**: lines written since the move are
  appended to their files and only then removed from the table, in one transaction per network,
  and the merged receipts from the files must equal the table's.
- **Network** is the list's folder name (`config.list_slug`), and the population is every
  `deploy_receipts.jsonl` that exists (`receipts.files()`), registered list or not.
  `source_line` counts the file's non-empty lines from 1.
- **The check each cycle is the `records-check` reader** (every 300 s, and woken by a deploy or
  a move); a mismatch or a database that does not answer is a Needs attention row
  (`attention.records_source`, kinds `mismatch` and `unreachable`).
- Deleting the files (step 7) is still the host step for the release after.

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

## 8. The app's interpreter, a virtualenv built from the lock (PLANNED right after receipts; DRAFT, 2026-10-09)

**Why, and why now** (the operator, 2026-10-09, moving the boto3 decision's option C from a
long-term target to here): the app's interpreter imports from three installers. `flask-app`
runs `/usr/bin/python3` as the operator's user with the user site enabled, so it searches the
user's pip folder, then a root pip folder in `/usr/local`, then apt's (C606: 42 user-level
packages, among them anthropic, pydantic, httpx and requests; 10 shadowing an apt copy; 4 root
pip packages). The host is not really apt-managed for Mercury, and `requirements.lock` already
names exactly what it runs.

**Measured for it, read only on the host (via LAN):** `flask-app`'s unit is
`ExecStart=/usr/bin/python3 <checkout>/app.py`, `User=` the operator, no environment; `python3-venv`
and `ensurepip` are installed; neither the updater nor `nmas-deploy` runs pip; 68 of the lock's
69 pins equal what the app imports today, and the 69th, cffi 1.16.0, is apt's `_cffi_backend`
1.16.0 with no cffi metadata.

**Every entry point that runs Mercury's code** (the operator's review, 2026-10-09: `flask-app`
is not the only one, and a tool on another interpreter than the app's imports other versions,
the split this item ends). Surveyed read only on the host (via LAN): every systemd unit and
timer, root's helpers, cron (none) and user units (none); and in the repository, every file
with a python shebang (app.py and 79 scripts: 57 import Mercury's modules, 3 a locked library
only (PyYAML or packaging), 19 the standard library only) and every place the code starts
Python itself.

| Entry point | How it finds its interpreter | Decision |
|---|---|---|
| `flask-app.service` (app.py) | names `/usr/bin/python3` in ExecStart | **Switched**: its own drop-in sets ExecStart to the venv's interpreter, and PATH, so anything the app starts that names `python3` finds the venv's too |
| `nmas-heartbeat-check` (nmas-heartbeat-rules), `nmas-telemetry-check` (nmas-telemetry-rules), `nmas-startup-check`, `nmas-ztp-responder`: Mercury's modules, PyYAML, requests | `#!/usr/bin/env python3`, so the unit's PATH | **Switched**: one drop-in, `nmas-.service.d/mercury-venv.conf`, sets PATH with the venv first. systemd applies a `<prefix>-.service.d/` folder to every unit whose name begins with that prefix (systemd.unit(5)), a template's instances and units installed later included, so no list of units is kept to drift |
| `nmas-job-finished@`, the NetBox backup and the NetBox restore test: the standard library only | the same | **Switched** by the same drop-in. They import nothing locked today; one rule for every `nmas-` unit keeps a script that later imports a module on the app's interpreter without anyone remembering to move it |
| `nmas-update.service`: root's `/usr/local/sbin/nmas-update`, loading `/usr/local/lib/nmas-update/nmas-deploy`'s gate (PyYAML, reading ci.yml) | the same, as root | **Switched** by the same drop-in. Considered keeping it on the system interpreter so the updater stays independent of the venv; not kept, because a broken venv is repaired by step 3 (a host step), never by the updater, and kept it would import apt's PyYAML 6.0.1 where the venv imports the lock's (equal today, measured; free to drift once the lock moves). The venv is root-owned, so root runs nothing the service user can write |
| A script a person runs on the host (`nmas-deploy`, `nmas-tier2-probe`, `nmas-breakglass`, `nmas-persist-native`, `nmas-records-migrate` once it exists, and the rest of `scripts/`) | its shebang, `#!/usr/bin/env python3`, so the shell's PATH | **Switched by the script itself, never a shell** (the operator, 2026-10-09: no `/etc/profile.d` file, which would change `python3` for every login shell on the host and still differ between login and non-login shells). The mechanism is drawn below for sign-off (8.1) |
| Each command the app prints for a person to run (Job health's startup-check and break-glass rows, Retire's break-glass export) | it said `python3 scripts/...` | **Built** (2026-10-09): `config.script_command()` names the interpreter the app itself runs (`sys.executable`): `/usr/bin/python3` today, `/opt/mercury-venv/bin/python` after the switch, the link's path across every swap (measured: through the link, `sys.executable` names the link). The three were the only ones (searched: modules, routes, templates, scripts, the manual) |
| `scripts/nmas-lock-from-host` | whichever `python3` started it | **Reads the app's interpreter** until it retires with the authored lock (8.2): it reads `flask-app`'s ExecStart from systemd and re-runs itself under that interpreter when another started it, saying so on stderr (refusing, rather than looping, if the re-run still reports another prefix). `tests/test_requirements_lock.py` holds the decision against the host's captured ExecStart |
| `rcn-topology.service` (deploy/topology/rcn-topology.py) | its unit names `/usr/bin/python3`; the file's own shebang is `#!/usr/bin/env python3` (read on the host 2026-10-09: `/usr/local/bin/rcn-topology.py` is a link, first line that) | **Kept on /usr/bin/python3**: lab tooling, not Mercury; it imports no Mercury module, and needs networkx (from the user's pip folder, measured), which the lock does not carry. The unit is reached by neither drop-in (its name does not begin `nmas-`). Run by hand, its env shebang takes the shell's `python3`, which nothing here changes now that profile.d is dropped: the operator's reason for dropping it, confirmed |
| The host-step scripts' own `/usr/bin/python3 -c` lines (6a's psycopg check, venv-1's comparison) | name `/usr/bin/python3` | **Kept**: they measure the system interpreter on purpose |
| `clab-sync.service`, the lab sync scripts, the app's `run_sync` | bash; no Python | Not Python |
| The laptop's tools (the gate, the hooks, `nmas-host`, `nmas-config-read`) | the laptop | Not on the host: the gate runs CI's interpreter |

**Approved by the operator, 2026-10-09:** the inventory and the `nmas-` prefix drop-in, with
two changes before anything runs: no profile.d (done: the drafts no longer install one), and
C607 designed now. **8.1 to 8.4 SIGNED OFF the same day, with notes:** 8.1 as ONE shared
standard-library helper every script calls first, never copied into each, silent where no
`flask-app` unit exists; 8.2 with a standard compiler (pip-tools' `pip-compile` or
`uv pip compile --generate-hashes`) considered in place of a custom `nmas-lock`, laptop and CI
only; the first venv changing WHERE the libraries live, not WHICH versions (textfsm 1.1.2 held
for it; 1.1.3, future and pycparser afterwards as the first ordinary lock change through 8.3 and
8.4); 8.3 keeping the current and previous venvs, the deploy removing older proved ones. Then
the host-step drafts redrafted to 8.3. No host change until the operator runs them.

### 8.1 How a person's script finds the app's interpreter (SIGNED OFF; BUILT 2026-10-09)

**Built:** `modules/app_interpreter.py` (standard library only), `adopt(__name__)`, called by 66
scripts at their top before any import outside the standard library, and by `nmas-deploy` as
the first statement of its `__main__` block (root's updater loads a copy of it as a module from
beside no checkout, and it imports nothing outside the standard library at its top).
`tests/test_app_interpreter.py` parses every python-shebang script under `scripts/` and refuses
one that does not call it first, with the exemptions below each named with its reason; planted
scripts show it fails, and so did a real one with its call removed. `nmas-lock-from-host`'s own
copy is gone. `nmas-deploy` hands its interpreter to `scripts/nmas-test` (a shell script that
runs `${PYTHON:-python3}`, found in this survey: `nmas-deploy --offline` runs the suite on the
host). Walked on the laptop with a stand-in `systemctl`: started by `/usr/bin/python3`,
`nmas-tier2-probe --help` re-ran under the named interpreter and said so; with no unit it ran
as started and said nothing. Exempt: the laptop's hooks, the gate, `nmas-stage-guard`,
`nmas-host`, `nmas-ci-log`, `nmas-host-step-check`, `check_removed_definitions.py`;
`nmas-config-read` (fed on stdin); `nmas-oxidized-cred` (a root-installed copy run
`/usr/bin/python3 -I`, never importing the checkout, found in this survey).

The comparison the sign-off rested on:

The operator named two shapes: a shebang naming the venv, or a `mercury-python` launcher. Both
were measured against where the scripts run, and a third is recommended.

| Shape | Where it fails |
|---|---|
| `#!/opt/mercury-venv/bin/python` | No laptop or CI has `/opt/mercury-venv`, so a host script run directly there fails "bad interpreter" (the suite runs scripts through `sys.executable`, so CI would never say so). On the host, from the release that changes the shebangs until the switch, every changed script fails the same way, so the release and the host step must land together. After the first switch's undo (step 3), the scripts still name a venv the app no longer runs: the split again. |
| `#!/usr/bin/env mercury-python`, a launcher installed on the host | Needs the launcher installed on every machine that runs a script (the laptop, CI, a fresh clone), or "env: mercury-python: not found". If the launcher chooses "the venv if it exists", it is wrong after the undo, as above. |
| **Recommended: the script re-runs itself under the app's interpreter** | Each host script's first statements (standard library only, before any other import) read `flask-app`'s ExecStart from systemd and, when another interpreter started the script, re-run it under that one, saying so on stderr. This is `nmas-lock-from-host`'s mechanism, built and walked on 2026-10-09 (the re-run, the no-re-run, the refusal). It is right in every state: before the switch (`/usr/bin/python3`), after it (the link), after any swap (the link), after the undo (`/usr/bin/python3` again). Where no `flask-app` unit exists (the laptop, CI) it runs as started and says nothing. Cost: about 12 ms per start (a systemd read, measured on the host: 11 to 14 ms), and two lines at the top of each script. |

### 8.2 The lock becomes authored (SIGNED OFF; BUILT 2026-10-09)

**Built:** `requirements.txt` rewritten as the authored input (25 direct distributions at the
host's versions, colorama held for the first venv only: nothing on Linux needs it, and the host
had it from apt); `requirements-overrides.txt` (the three below); `requirements.lock` compiled by
uv 0.12.24: the same 70 `name==version` pins as the host-read lock, now with 1,006 hashes. CI
and `scripts/nmas-ci-env` install it `--require-hashes --no-deps`. Proved on the laptop: a fresh
venv on Python 3.12.3 installed it in 8 s (181 MB), and `pip check` named exactly the three
overrides' complaints. `scripts/nmas-lock-from-host` is retired; its import mapping and scan
moved into `tests/test_requirements_lock.py`, whose new checks were each shown to fail (an
extra unsatisfied dependency; a pin with its hashes removed).

Today the lock is READ from the host (`nmas-lock-from-host`), because CI had to test what apt
and pip had put there. With a venv the direction reverses: the host is BUILT from the lock, so
the lock is the authority and is made where it can be tested.

**The compiler: `uv pip compile`, not pip-tools and not pip's own resolver.** Measured
2026-10-09 on the laptop (uv 0.12.24 and pip-tools 7.6.2, each in its own tool folder, never
CI's interpreter), on today's 70 pins: the first venv must hold netmiko 4.3.0 WITH textfsm
1.1.2, and netmiko 4.3.0's PyPI metadata declares `textfsm>=1.1.3`. pip's resolver and
`pip-compile` (which uses it) both refuse that combination (ResolutionImpossible), and neither
can override a dependency's declared requirement. uv can (`--override`): with three overrides
it produced exactly today's 70 `name==version` pins, identical to the host-read lock, with
1,006 hashes (every file PyPI publishes for each release). So the custom `nmas-lock` is not
built; uv runs on the laptop only (CI checks the lock it produced, 8.2's last points).

- **`requirements.txt` is the authored input:** one line per distribution the code or the suite
  imports, pinned `==` at the version the host runs today, with its reason where one is known.
- **`requirements-overrides.txt` holds each override with its reason and when it goes:**
  `textfsm==1.1.2` (the host's version; netmiko 4.3.0 asks for `>=1.1.3`); `future` and
  `pycparser` excluded by a marker that is never true (PyPI's textfsm metadata asks for future,
  but its code imports `builtins`, Python 3's own module, as `future` only backports it to
  Python 2: CI has run it without future all along; cffi asks for pycparser, which only its
  build-time `cdef` parsing needs, and neither CI nor the host has it). All three go in the
  first ordinary lock change.
- **The command**, recorded by uv in the lock's own header: `uv pip compile requirements.txt
  --override requirements-overrides.txt --generate-hashes --python-version 3.12
  --python-platform x86_64-unknown-linux-gnu -o requirements.lock`. With `-o` naming the
  existing lock, uv keeps its pins unless something forces a move; `--upgrade-package <name>`
  moves one named distribution.
- **CI installs it as the host will:** `pip install --require-hashes --no-deps -r
  requirements.lock`, then the suite. A test runs `pip check` (offline) and holds its complaints
  to exactly the overrides' (each override names the one it causes), so a dependency that stops
  being satisfied for another reason fails; another holds the lock to satisfy every line of
  `requirements.txt`, and the existing test to cover every import.
- **`nmas-lock-from-host` retires** with the authored lock (and C37's host-reading with it);
  the host's proof that it runs the lock is 8.3's build checks.
- **A new dependency** is a line in `requirements.txt` and the command above on the laptop; it
  reaches the host only through 8.3 and 8.4. That is C607's second half.
- `requirements-test.txt` (pytest-xdist, execnet: on the host and in CI) stays as it is,
  installed `--no-deps` beside the lock; the venv's identity covers it (8.3).

### 8.3 The host builds beside, swaps a link, never rebuilds in place (SIGNED OFF; host steps redrafted 2026-10-09, not run)

Measured on the laptop, 2026-10-09: a venv reached through a linked folder reports the LINK as
`sys.prefix` and `sys.executable`; a running process's `/proc/<pid>/maps` names the REAL folder
its extension modules came from; a rename over the link (`ln -s new tmp && mv -T tmp link`)
swaps it atomically, and the next process takes the new venv. A venv is about 207 MB (CI's, with
its test tools); the host has 244 GB free on `/opt`.

```
/opt/mercury-venv              -> mercury-venv-<h>       the link every drop-in names
/opt/mercury-venv.previous     -> mercury-venv-<h0>      what a rollback points back to
/opt/mercury-venv-<h>/         <h> = the venv's identity: the first 12 hex of the sha256 of
                               requirements.lock then requirements-test.txt, both installed
                               in it (modules.app_interpreter.venv_id, the one computation)
    .mercury-proved            written last, only when every build check passed:
                               the identity, the commit, the time
```

**Kept: the current venv and the previous one** (the operator, 2026-10-09). Older proved ones
are removed by the deploy once it carries the swap (8.4); until then by `venv-swap.sh`, after a
swap it has proved, each loaded by no process (`/proc/*/maps`, read as root) and named as it
goes. A build removes nothing but an unproved folder of its own identity.

The host steps, redrafted to this shape (`scripts/host-steps/`, each the operator's, none run):

1. **Build** (`venv-1-build.sh`, run from the checkout of the release to be deployed): computes
   `<h>` from that checkout. Refuses when `<h>` is the link's target or `.previous` (never
   rebuilds in place: it names the folder and what points at it). A proved folder of that
   identity is reported and left, PASS; an unproved one (an earlier build that failed) is
   removed and rebuilt. Builds with `pip install --require-hashes --no-deps -r
   requirements.lock`, then `requirements-test.txt` with `--no-deps`, and checks: Python
   3.12.3; nothing from outside it; every pin installed at its version; `pip check`'s
   complaints exactly the overrides'; psycopg loading libpq; every Python program on the host
   importing in the new venv all it imports under the app's CURRENT interpreter (whatever
   `flask-app`'s ExecStart names now). **The first build only** (no link yet) also proves every
   pinned distribution at the version the app imports today: the first venv changes where the
   libraries live, not which versions. Only then `.mercury-proved`. Nothing that runs changes.
2. **First switch** (`venv-2-switch.sh`): creates the link to a proved build, installs the two
   drop-ins naming the link, and proves what it proved before, plus that the app's process
   loads from `mercury-venv-<h>` (its maps). **Its undo** (`venv-3-undo.sh`) removes the
   drop-ins and leaves the link: the system interpreter again.
3. **Later lock changes** (`venv-swap.sh`, from the release's checkout): refuses without
   `.mercury-proved` for that checkout's `<h>`; records the link's current target as
   `.previous`; swaps the link atomically; restarts the app (and the ZTP responder if running);
   proves the app's process maps `mercury-venv-<h>`, `/health` 200, and runs the heartbeat and
   telemetry checks once. **On any failed proof it swaps back to `.previous` itself, restarts,
   and proves the old venv answers**, ending FAIL with what failed: rollback on failure, as
   every Mercury operation does. After a proved swap it removes older proved venvs (above).
   Until 8.4 is built, a swap and its release's deploy are run in one sitting by the operator.
4. **Rollback by hand** (`venv-rollback.sh`): points the link at `.previous` (refusing when it
   is absent or unproved), records the venv left as the new previous, restarts, and proves as
   the swap does. It never swaps back on its own; `venv-3-undo.sh` is the way to the system
   interpreter.

**Walked on the laptop, 2026-10-09, in a sandbox** (the scripts copied with `/opt` moved into a
scratch folder; stand-ins for `sudo`, `systemctl`, `curl` and `sleep`; real venvs with PyYAML's
compiled module, so `/proc/<pid>/maps` is real): a healthy swap passed 12 of 12, recorded the
previous venv, and removed the older one no process held; a swap whose new venv's `/health`
failed pointed the link back itself, the app loaded from the old venv again, and the result
stayed FAIL at that check; a rollback to an unproved previous venv was refused before anything
moved, and to a proved one passed 10 of 10 with the two venvs exchanged; and (the retention
branch, walked after the switch at the operator's request) a swap with two older venvs, one
loaded by a running process and one by none, kept the first, named why, removed the second, and
passed 12 of 12.

**The first switch, run by the operator 2026-10-09:** `venv-1-build.sh` failed on its first run,
on pypi.org read timeouts, though curl answered in about 0.15 s afterwards over IPv4 and IPv6;
pip had reported "No matching distribution" (C608: the build now checks that the index answers
first and names a timeout in those words). The re-run removed its unproved build itself and
PASSED 14 of 14; `venv-2-switch.sh` PASSED 18 of 18 (`/health` in about 4 s; the heartbeat and
telemetry checks succeeded from the venv). The operator's v2 walk: the pages load, 9 devices
heartbeating, Show commands on r1 and s1 normal, a deploy preview normal. Read on the host
afterwards (via LAN, 16:41 UTC): the link names `mercury-venv-9d27674e53bf`, the app's process
loads from it, and every `nmas-` unit has the venv first on its PATH. The walk found nothing
in the scripts; venv-1's pin and `pip check` checks, run against scratch venvs, had found a
normalisation that rewrote versions, fixed before the commit. `lib.sh` gained `ON_FAIL` (the
undo a failed step or check runs before the summary), tested with planted scripts and shown
able to fail.

### 8.4 A release that changes the lock (SIGNED OFF; BUILT 2026-10-09, its first host run owed)

A swap without the release, or the release without the swap, runs one release's code on the
other's packages. So the deploy carries the swap:

- `nmas-deploy` and the updater compute `<h>` from the TARGET commit's lock and compare it with
  the link's target. Equal: today's deploy, unchanged. Different: refused, naming both hashes,
  unless `/opt/mercury-venv-<h>/.mercury-proved` exists; then the deploy swaps the link in the
  same restart as the checkout moves, and its existing rollback (a release that does not come
  up) puts BOTH back: the commit and the link.
- After a proved swap, the deploy removes proved venvs older than the previous one (8.3).
- **Built:** the functions live in `scripts/nmas-deploy` (`venv_id_from`, `venv_plan`,
  `swap_venv`, `unswap_venv`, `prune_venvs`), because root's updater loads that file's root
  copy and never imports the user-writable checkout; the identity is computed there from the
  target's files as `git show` bytes (a text read strips a trailing newline and names another
  venv), and a test holds it equal to `modules.app_interpreter.venv_id`. `nmas-deploy` (as the
  operator, through the sudo it authorises before anything moves) and the updater (as root,
  every program by absolute path: `ln`, `mv`, `rm` and `grep` joined its table, measured on
  the host root:root 755) both: refuse an unbuilt venv before the move, naming both
  identities and the build from a clone of the release; move the link just before the
  restart, so the old process imports from the new venv only in that gap; put the checkout
  back unrestarted when the link cannot move; and, after the target came up, prune. The
  updater's rollback moves the link back with the commit; a terminal deploy that does not come
  up says which venv the link names and how to point it back (it never rolls back code
  either). `tests/test_venv_deploy.py`: the plan's four states on real links, the swap, the
  pruning (unproved and loaded venvs kept), the deploy end to end (refused, then moved in the
  same restart), the updater's order (refuse before the move; swap after it and before the
  restart; prune on success; swap back on rollback; a link that cannot move). The refusal and
  the rollback's swap-back were each removed from a copy and their tests failed. Before the
  switch there is no link, and nothing is compared (the release's files are not even read).
- **Its first host run** is the first ordinary lock change: networkx 3.6.1 added for P.11,
  nothing else moved (the operator, 2026-10-10, who amended the earlier plan: the three
  overrides, textfsm 1.1.3, future and pycparser, come off in the NEXT lock change, on their
  own, and `pip check` must then come back clean). Build that venv from a clone of the release
  (the refusal prints the command), then deploy. The updater's two root copies must be re-installed from the release that
  carries this (docs/UPDATE.md, "Re-install") before the Update button carries a swap.
- Settings › Installation (F2) can show the running venv's `<h>` beside this release's: a
  release whose lock is not yet built is visible before anyone presses Update. Not in F2's
  signed board; a later board if wanted.

**Not changed by this item:** the user and root pip folders (removing them is a later decision,
once nothing reads them; rcn-topology still reads the user's).
