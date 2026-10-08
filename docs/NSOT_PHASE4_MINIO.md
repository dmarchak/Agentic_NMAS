# Phase 4, step 1: Mercury's connection to MinIO (APPROVED by the operator, 2026-10-08; decisions in section 5)

The operator's decision (2026-10-08, NSOT_PHASE4_RECORDS_POSTGRES section 5): **the MinIO
connection comes first.** It serves three things: the Oxidized archive (Phase 3's P3-1, one git
bundle), the record database's nightly dumps, and the Show commands answers past their 30 days
(`reads.expire`). This draft says what exists, what was measured, what is proposed, and the
operator's host steps. Nothing is built until it is signed off.

## 1. What exists today (read from the code)

- **Settings, per network:** `s3_endpoint`, `s3_bucket`, `s3_access_key` and `s3_secret_key`
  (secrets, in the secrets backend: `secrets_store.py`), `s3_region`, `s3_prefix`,
  `s3_verify_tls` (`settings_scope.py`, the `s3_archive` group, NETWORK scope). The Settings
  page's S3 archive card edits them; its Test asks `bucket_exists` only.
- **Three places build a client, each its own way:** `integrations/s3_archive.py`
  (`test_connection`), `nsot/archive.py` (`s3_archive_hook`, a post-commit hook uploading each
  changed golden as `<prefix>/golden/<device>/<stamp>.cfg`), and `nsot/reads.py` (`_s3_put`, the
  answers past retention). None passes `s3_verify_tls` (C355). Three owners of one connection.
- **The SDK:** `minio>=7.2.0` is in `requirements.txt` and absent from `requirements.lock` by
  design (its header), so the host does not have it: measured 2026-10-08, the app's interpreter
  (from `flask-app.service`'s ExecStart) raises `ModuleNotFoundError: No module named 'minio'`.
  Every path above therefore says "the minio SDK is not installed" today.

## 2. The MinIO that exists (measured read-only, 2026-10-08, via LAN, through `mc` on the NMAS host)

- Server release `2025-04-22T22:12:26Z`. `mc` aliases on the host: `lab` (this MinIO, with its
  administrator credential), `dr` (the replica), and the client's defaults.
- **Buckets on `lab`: three**, each versioned with a lifecycle configuration:
  `loki` (18 MiB, 30,989 objects), `raw-telemetry` (5.6 GiB, 878 objects), `thanos` (1.6 GiB,
  211 objects). **No bucket for Mercury.**
- **Policies:** the built-ins (`consoleAdmin`, `diagnostics`, `readonly`, `readwrite`,
  `writeonly`) and one custom, `lake-archive-write` (C407's fix).
- **Users: two.** `lake-archive` (policy `lake-archive-write`) and `loki-writer` (policy
  `readwrite`, the built-in that grants every action on EVERY bucket: C584, below).
- Not measured: the `dr` side's buckets, and whether a new bucket would be replicated (C454's
  open question is the same mechanism).

## 3. Proposed

**One connection for the installation, inherited by every network.** The existing `s3_*` keys
stay the connection; their installation value (the Default layer, which every network already
inherits through `list_settings`) is the one the installation-wide uses read (the Oxidized
bundle, the record dumps), and a network may still name its own bucket or prefix for its goldens
and answers. No new setting: one place to configure, and a network that sets nothing archives
under the installation's connection (the safe-path rule: an inherited default, not a new
declaration).

**One client, one home:** `integrations/s3_archive.client(list_name=None)` builds the client
from the settings (the installation's when no network is given), passes `s3_verify_tls` (closing
C355), and is the only constructor; the hook, `reads.expire`, the Test and the new uses call it.
A missing SDK, an unset endpoint and an unreachable server are three different answers, each
named.

**The Test proves what the uses need:** `bucket_exists`, then a put, a get that compares the
bytes, and a stat of a probe object under `<prefix>/_probe/` (overwritten, never deleted, so the
key needs no delete right). It says which of the four failed, with what the server answered.

**Layout in one bucket, by purpose:**

| Prefix | What | Written by | Retention |
|---|---|---|---|
| `goldens/<network>/<device>/<stamp>.cfg` | each changed golden at its commit (today's hook; its key moves under `goldens/`) | post-commit hook | kept (git is the record; this is the archive) |
| `reads/<network>/<run>.json` | Show commands answers past `reads_retention_days`, one object per run (the run's results) | `reads.expire` | kept |
| `records/<date>.dump` | the record database's nightly `pg_dump` (Phase 4 step 2) | the backup job | a retention setting (section 5) |
| `archive/oxidized/<name>.bundle` | Oxidized's history, once (P3-1) | the operator's host step, once | kept |

**The connection on Needs attention:** the integrations reader (every 60 s) asks the S3
archive's `status()`, which asks only whether the bucket answers: a read writes nothing, and
the four-step Test every minute would leave 1,440 versions a day of its probe in a versioned
bucket. A bucket that does not answer is the integrations source's row, naming what the server
answered, cleared by the next good read. The four-step Test is a person's (Settings' Test).
(Corrected 2026-10-08 while building: the draft had the reader asking all four steps.)

**The SDK:** `minio` added to `requirements.lock` at the version Ubuntu or PyPI gives the host,
by the operator's host step (section 4) and `scripts/nmas-lock-from-host`, so CI installs what
the host runs.

**BUILT 2026-10-08 (Mercury's side):** `integrations/s3_archive.py` holds the one client
(`S3ArchiveIntegration.client`, `cert_check` from `s3_verify_tls`: C355), `key()` under the
prefix, `put()`, the four-step `test_connection()` and the read-only `status()`; the golden
hook and `reads.expire` use it; goldens are written at `goldens/<network>/<device>/<stamp>.cfg`;
`deploy/minio/mercury-rw.json` is the policy section 4 installs (list, read, write and
multipart; no delete). Not built: the installation's own uses (the Oxidized bundle is a host
step; the record dumps come with PostgreSQL). Waiting on the host steps below and a walk.

## 4. The operator's host steps (when signed off; on the NMAS host, with the `lab` alias)

As scripts (the operator's request, 2026-10-08): `scripts/host-steps/c584-loki-writer.sh`
first, then `minio-4a-4b.sh`, `minio-4c.sh` (prompts for the secret, input hidden) and
`minio-4d-4e.sh` (refuses a non-virtualenv interpreter or a dry run that changes an installed
package; writes `/tmp/requirements.lock.new` for the session to commit).

Every value below is filled when the step is written into its commit, from a read made then
(C434); `<…>` here marks what the commit fills.

```bash
# 1. The bucket, versioned like the other three.
mc mb lab/mercury && mc version enable lab/mercury
# 2. A policy that can list, read and write the bucket and nothing else: no delete, no other
#    bucket. It ships in the commit as deploy/minio/mercury-rw.json (s3:ListBucket and
#    s3:GetBucketLocation on arn:aws:s3:::mercury; s3:GetObject and s3:PutObject on
#    arn:aws:s3:::mercury/*), installed by name from the checkout.
mc admin policy create lab mercury-rw <checkout>/deploy/minio/mercury-rw.json
# 3. Mercury's own user, its secret generated on the host and never shown in a terminal log.
mc admin user add lab mercury                  # prompts for the secret
mc admin policy attach lab mercury-rw --user mercury
# 4. The SDK in the app's venv, then the lock regenerated from the host.
<venv>/bin/pip install --no-deps minio==<version> <its dependencies from the lock step>
```

Then, in Mercury's Settings (v2), the S3 archive card at the installation level: endpoint,
bucket `mercury`, the access key `mercury` and its secret (stored by the secrets backend), and
Test. **What the operator checks afterwards:** Test reads four passes; `mc admin trace --path
'mercury/*' lab` during a Test shows only `mercury`; `mc ls lab/mercury/_probe/` holds the probe.

## 5. Decisions (APPROVED by the operator, 2026-10-08)

- **M-1, one bucket `mercury` with prefixes by purpose.** One bucket is one policy and one key;
  the prefixes keep purposes apart.
- **M-2, Mercury's key cannot delete.** Nothing Mercury archives is deleted by Mercury;
  expiry is MinIO's bucket lifecycle (a rule on `records/` only), never Mercury. A compromised
  Mercury cannot erase its own archive.
- **M-3, replicate to `dr` only if it is a separate machine; otherwise defer to Stage 10's
  HA.** Measured 2026-10-08, read-only: `lab` and `dr` are different addresses and different
  MinIO deployments, but the hypervisor has one node, and `dr` is its LXC 103 (`minio-dr`);
  both servers' uptimes differ by 33 s. Same machine, so **no replication now**: deferred to
  Stage 10.
- **M-4, the record dumps' retention:** 30 dailies and 12 monthlies, as a lifecycle rule on
  `records/`.
- **M-5, the connection's scope:** the existing `s3_*` settings, their installation value
  inherited by every network; no new setting.
- **Before the bucket exists:** C584's host step (`loki-writer` scoped to `loki`).

## 6. Found while surveying

- **C584** (registered 2026-10-08): MinIO's `loki-writer` user holds the built-in `readwrite`
  policy, which grants every action on every bucket, so Loki's credential could read, overwrite
  or delete `raw-telemetry`, `thanos`, and Mercury's bucket once it exists. The same defect as
  C407 for another writer.
