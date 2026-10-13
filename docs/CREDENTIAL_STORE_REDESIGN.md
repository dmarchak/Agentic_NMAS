# Credential store redesign (a proposal; not built)

**A design item for AFTER Phase 7 (the operator, 2026-10-13), beside
[PUBLIC_RELEASE.md](PUBLIC_RELEASE.md). Register: C733. Nothing here is built until Phase 7
closes and the operator approves this design.** It replaces today's single-key Fernet store with
an industry-standard design: a dedicated secrets manager as the credential source of truth, and
envelope encryption under a key the host cannot copy for anything Mercury still keeps locally.

It folds in two earlier items:

- **C729**, the nightly VM image holding `data/key.key` beside every store it opens (deferred
  by the operator on 2026-10-13, risk accepted until this redesign; the startup guard that
  refuses to make a key for a sealed store stays as built).
- **The TPM-bound key**, formerly the first half of PUBLIC_RELEASE.md section g. The second
  half, the break-glass record's scrypt cost, stays there and is referred to below.

---

## 1. Today, measured from the code

**One key opens everything.** `data/key.key` is a single Fernet key (AES-128-CBC with
HMAC-SHA256), created by `config.read_or_create_fernet_key`, owner-only (0600), read at start by
`device.load_key()` and `secrets_store._get_fernet()`.

| Store | What it holds | Form |
|---|---|---|
| `credential_profiles.json` | credential profiles (username, password, enable secret), per-device overrides, template secrets | `enc:v1:` + Fernet token |
| `lists/<slug>/devices.csv` | each local-inventory device's `password` and `secret` columns | bare Fernet token |
| `user_settings.json` | the integration secrets in `secrets_store.SECRET_KEYS` (NetBox, Prometheus, Grafana, Loki, Oxidized, Kea, Git, S3, Proxmox, the records database: 14 keys) | `enc:v1:` + Fernet token |
| `lists/<slug>/settings.json` | a network's own values of the same keys (`list_settings`) | `enc:v1:` + Fernet token |
| `<config_repo>/.nsot/staging/credential/<device>.enc` | a rotation's new password, parked before the push (the crash window) | Fernet token |

**Not sealed, by design or by placement:** `.env` holds the AI key in plaintext (its file
mode is the control, docs/SECRETS.md); `data/secret.key` signs sessions; Oxidized's `router.db`
holds device credentials in plaintext, written only by the root-owned
`scripts/nmas-oxidized-cred`; goldens hold each device's type-9 hashes and SNMP communities
verbatim, in git and in the MinIO archives (C730).

**What the design lacks, stated as properties:**

1. **No key separation.** A process or a disk image that holds `key.key` opens every
   credential of every network, and every integration secret.
2. **No binding of a value to its place.** A token copied from r1's row to r2's opens as r2's
   password: nothing in the ciphertext says whose it is.
3. **No key versions.** Changing the key means re-encrypting every value at once, so it is
   never done; there is no rotation of the key itself.
4. **The key sits beside the stores.** The nightly VM image holds both (C729); so does any
   copy of the data directory.
5. **No access record.** Nothing records which process read which credential, and when.
6. **Two lists of where sealed values live.** The writers above put sealed values in five
   places; the break-glass key check (`breakglass.JSON_STORES` and the device CSVs) and the
   startup guard read three of them (C734).

## 2. The design in one paragraph

Credentials live in **OpenBao** (or Vault) **KV v2**, the source of truth, read by Mercury with
a short-lived token from an **AppRole bound to the host**, under a policy that grants each
Mercury process only the paths its job needs, every access in the manager's **audit log**.
Whatever Mercury must still keep on its own disk (the offline fallback, the rotation's staging,
any installation without a manager) is sealed by **envelope encryption**: a fresh AES-256-GCM
data key per value, the value's identity (network, device, field) bound as associated data,
the data key wrapped by a **master key that never leaves its keeper** (a TPM through
systemd-creds by default; OpenBao or Vault Transit, a cloud KMS or a PKCS#11 HSM by choice),
each wrapped key naming the **master-key version** that wrapped it, so rotating the master key
rewraps 32-byte keys and never touches a password.

## 3. The secrets manager as the source of truth

**Choice of manager.** OpenBao (MPL-2.0, the Linux Foundation's fork) is the default; HashiCorp
Vault is API-compatible for everything below. Vault's licence (BUSL-1.1 since 1.15) matters
for a public release; OpenBao's does not. Either is a new third-party licence, which is the
operator's decision (the Phase 7 stops).

**Layout (KV v2, mount `mercury/`).** One path per credential, scoped by network so a policy can
be scoped by network too:

| Path | Fields |
|---|---|
| `mercury/<network>/devices/<device>` | `username`, `password`, `enable_secret` |
| `mercury/<network>/profiles/<profile>` | `username`, `password`, `enable_secret` |
| `mercury/<network>/template-secrets/<name>` | `value`, `kind` |
| `mercury/installation/integrations/<key>` | `value` (each of the 14 integration secrets) |

KV v2 keeps versions: a rotation writes a new version with **check-and-set** (`cas` = the
version it read), so two writers cannot overwrite each other, refused by version number (the
refusal names both operands). Custom metadata carries `rotated_at`, `source` and the receipt id;
a retired device's path is soft-deleted (its versions kept), and destroying versions is a
person's act.

**Authentication: AppRole bound to the host.**
- The `role_id` is non-secret configuration. The `secret_id` reaches the service through
  systemd-creds (sealed to the host's TPM, section 5), never `user_settings.json`, and is bound
  to the NMAS host's address (`secret_id_bound_cidrs`, `token_bound_cidrs`).
- Tokens are short-lived (`token_ttl` 15 minutes, `token_max_ttl` 1 hour), renewed in the
  background, and replaced by a fresh login when renewal fails.
- There is no root token on the host and no long-lived token anywhere.

**Least privilege, one role per kind of process:**

| AppRole | Who uses it | Policy |
|---|---|---|
| `mercury-web` | the app's request workers | read on `mercury/data/*`; create/update on device, profile and template-secret paths (a person's confirmed change) |
| `mercury-rotation` | the scheduled rotation timer and the rotate CLI | read and update on `mercury/data/<network>/devices/*` only |
| `mercury-read` | readers, verify, the config check in Mercury | read only |
| `mercury-admin` | none by default: a person's own token, for import, destroy and policy changes | the rest |

**The audit log.** A file audit device, shipped to Loki like the host's other logs. Values in it
are HMAC'd by the manager, so the log names who read what without holding it. The manager fails
closed when its audit devices fail (it answers nothing it cannot record), and that is drawn as a
Needs attention row. Mercury's own receipts keep the person (the access proxy's identity); the
manager sees the AppRole. The two are joined by a request id Mercury sends with each call and
writes in its receipt.

**Availability.** The manager becomes a dependency of every deploy, rotation and read. Unreachable
or sealed: operations that need a credential refuse by name ("the secrets manager at <address>
answered 503: sealed"); nothing falls back silently to a stale local copy. Production runs three
nodes (integrated Raft storage) with auto-unseal through a KMS or HSM; the lab runs one node,
with the unseal shares typed by the operator after a restart (a secret value: the operator's).
**Decided 2026-10-13 (section 9):** OpenBao on Mercury's own host, unsealed by hand on a GUI
page by default; while sealed, the credential-free features keep working.

**Masking without listing every secret.** `redact.known_secret_values()` today decrypts every
credential into an in-memory table so it can mask by value; under least privilege the web role
should not read every path to mask a page. It becomes an index of keyed digests: at each write,
`HMAC-SHA256(k_mask, value) -> label`; masking scans a text's tokens (the same token boundaries
`_compile` uses today) and replaces any whose digest is in the index. `k_mask` is itself an
envelope-sealed local key (section 4). The plaintext table and its cache disappear.

## 4. Envelope encryption for what Mercury still stores locally

**What stays local:** the rotation's staging file (it must survive a crash with the manager
unreachable), the masking key, an installation without a manager (local mode, the
zero-dependency default), and the migration's transition copies.

**One record per value:**

```json
{"v": 2, "kid": "tpm-3", "dek": "<wrapped data key, base64>",
 "nonce": "<96-bit, base64>", "ct": "<AES-256-GCM ciphertext and tag, base64>"}
```

- **A data key (DEK) per value:** 32 random bytes, used for one encryption, so a nonce never
  repeats under a key.
- **Associated data (AAD) is the record's identity,** never stored, always rebuilt by the
  reader from where it is reading: `mercury/v2|network=<n>|device=<d>|field=password`. A
  value moved to another device's row, field or network fails its tag check and refuses to
  open, naming the identity it expected.
- **The DEK is wrapped** by the master key version `kid`, inside its keeper, with the same AAD.
- **Key versions:** the backend holds versions; one is primary for wrapping, the others only
  unwrap. **Rotating the master key** makes a new primary and runs a rewrap job: each record's
  DEK is unwrapped by its old `kid` and wrapped by the new one, under the store's lock, one
  record at a time, resumable. The password's ciphertext is untouched. A version no record names
  is retired, and kept disabled for at least the backups' retention so an old backup still
  opens; after that, destroying it makes those backups unreadable (crypto-shredding), which is a
  person's act (the stops: deleting key material is like deleting a backup).
- **Library:** `cryptography`'s `AESGCM`, already a dependency. No new licence for the local
  path.

## 5. A pluggable key backend

```text
class KeyBackend:
    name, kids(), primary_kid()
    wrap(kid, dek, aad) -> bytes          # the master key never leaves the backend
    unwrap(kid, wrapped, aad) -> bytes
    rotate() -> kid                       # where the backend can; else a person's step
    health() -> {"ok", "detail", "bound_to"}
```

| Backend | Master key held by | Rotation | Dependency |
|---|---|---|---|
| **systemd-creds (optional; NOT the default, decided 2026-10-13, section 9)** | the host's TPM2: an AES-256 key sealed with `systemd-creds encrypt --with-key=tpm2`, delivered to the unit by `LoadCredentialEncrypted=` into its private credentials directory | a new sealed key, a new `kid` | none (systemd 250 or later; the host runs 255 on Ubuntu 24.04, measured 2026-10-13) |
| **OpenBao / Vault Transit** | the manager (an `aes256-gcm96` key) | native: `transit/keys/<k>/rotate`, and `transit/rewrap` rewraps without Mercury seeing a DEK | the manager (section 3) |
| **Cloud KMS** | AWS KMS, Google Cloud KMS or Azure Key Vault | native (`ReEncrypt` and equivalents; the encryption context is the AAD) | the provider's SDK (AWS through `boto3`, already on the host) |
| **PKCS#11** | an HSM (YubiHSM 2, a network HSM; SoftHSM2 in tests) | a new key object, a new `kid` | a PKCS#11 binding (a new licence) |

**Honest limits of the default.** systemd-creds protects the key AT REST: a copied disk or image
without the same TPM cannot unseal it. A process running as the service while it runs holds
the unsealed key in memory; only an external keeper (Transit, KMS, HSM) keeps the master key out
of the process entirely. `--with-key=auto` silently falls back to a host-file key when no TPM is
present, which is the C729 shape again, so Mercury asks for `tpm2` explicitly and Settings ›
Installation names what the key is actually bound to.

**Measured for the lab, 2026-10-13:** the NMAS VM has **no TPM** (no `/dev/tpmrm0`, no
`tpmstate0` in its hypervisor configuration). The default backend needs a vTPM added on the
hypervisor first (the operator's). **To measure before relying on it:** whether the hypervisor's
nightly image includes the vTPM state. If it does, an image again carries both halves (the
sealed key and the TPM that unseals it), and the lab should use an external keeper (Transit on
the manager's node) instead.

**Selection** is one card in Settings › Installation (section 8), with a Test that wraps and
unwraps a probe, and a Migrate that rewraps every record to another backend, previewed (counts
per store and `kid`) and confirmed. A backend's own credential (an AppRole `secret_id`, a cloud
key) reaches the service through systemd-creds, never a settings file.

## 6. Migration from today's Fernet store, with no lockout window

**The property:** at every moment every value is readable by at least one path, and no device's
credential changes. Migration moves where a credential is kept, never what it is.

1. **Before:** an intact break-glass export (it escrows today's key), a Save All baseline, and a
   hypervisor snapshot (the operator's).
2. **A dual-reading release.** Readers open v1 (`enc:v1:` and the CSV's bare tokens) and v2
   records; writers still write v1. Deployed and walked.
3. **The backend is enabled** (a host step seals the master key; its health reads green).
4. **Writers switch to v2.** New and rotated values are v2 from here.
5. **The migration job,** per store and per record, under that store's lock: open v1, seal v2
   with the record's identity as AAD, write atomically, read back and compare digests, then the
   next. Resumable and idempotent; a record that fails stays v1 and readable, named in the
   result. A dry run first reports counts only. Scheduled rotation is held for the job's length
   (it refuses, naming the migration), so nothing changes under the copy.
6. **Proof:** every stored value opens as v2 under its expected identity; zero v1 remain, per
   store. The store inventory is one registry the writers use and the proof reads (C734 fixed
   here), so "every value" is measured over every store.
7. **Into the manager:** an import job writes each credential to KV (`cas=0`, create only),
   reads it back with Mercury's own role and compares digests; readers then take the manager
   first, and the local copy read-only, for one rotation period; then the local copies are
   removed, after a fresh break-glass export taken from the manager.
8. **Fernet retired:** `key.key` stays on disk (and escrowed) until one full backup retention
   has passed with zero v1 values; removing it is a host step, the operator's.

## 7. Break-glass afterwards, and what backups contain

**Break-glass.** Today the record escrows `key.key`. A TPM- or HSM-held master key cannot be
exported, which is the point, so the record stops escrowing a key and carries what it already
carries, each device's credentials, sealed by a passphrase. Recovery after losing the host or
its TPM is: a new host, a new master key, and the record's credentials imported and re-sealed.
The record's format moves to AES-256-GCM with the scrypt cost raised to N=2^17 and read from the
envelope (PUBLIC_RELEASE.md, section g).

**Shamir shares or the sealed export.**
- **The sealed export stays the device-console last resort in every mode:** offline,
  per network, dated, its currency tracked as now.
- **With a manager:** its own unseal (or recovery) keys are Shamir shares, k of n, held by
  different people. That is the manager's recovery, not the devices'.
- **A Shamir recovery key for the local tier** (a second wrapped DEK per record under a recovery
  `kid` whose key is split k of n) recovers without anyone holding the whole key. It is worth it
  only with several holders; for one operator it is ceremony without the property, and the sealed
  export is the honest choice. **Recommended:** the sealed export alone for the lab; the
  export plus a 3-of-5 recovery key, or the manager's own shares, for an organisation.

**Backups afterwards:**

| Backup | Holds | Opens with |
|---|---|---|
| The hypervisor's VM image | v2 records (wrapped DEKs, ciphertext) and the TPM-sealed master key blob | the same TPM; nothing else. Whether the image carries the vTPM state is measured first (section 5) |
| The manager's storage snapshot (to MinIO) | KV data under the manager's barrier key | the unseal shares or the auto-unseal KMS, held elsewhere |
| The break-glass record | device credentials, passphrase-sealed | the passphrase, offline |
| Goldens in git and the MinIO archives | type-9 hashes and SNMP communities verbatim | nothing: unchanged by this design, and still C730 |

## 8. What it changes

**Rotation** (`credential_rotation`, `scheduled_rotation`):
- The staging file becomes a v2 record whose AAD names its device and `staged-password`.
- The persist step writes a KV version with `cas`, so a concurrent writer is refused by version.
- The timer runs as `mercury-rotation`, able to change device credentials and nothing else.
- Receipts and commits carry the KV version written.
- The crash-window recovery reads the staged record as today.

**The config check** (`config_check`, `hostvars.assert_no_secret_values`):
- The value scan masks and checks through the HMAC index rather than a plaintext table.
- The bare-checkout path is unchanged: it never had values, and the hash-shape scan (C731) still
  needs none.

**Masking** (`redact`): `known_secret_values()` becomes the HMAC index. No plaintext table, no
cache of secrets, and its health counts index misses rather than a store it failed to decrypt.

**The interface:**
- **Credentials:** each credential shows where it lives (the manager path and version, or
  "local, sealed by <kid>"), its age and last rotation. Reveal stays a confirmed person's act and
  appears in the manager's audit log under the request id.
- **Settings › Installation** gains two cards, each needing a mockup and the operator's
  sign-off:
  - **Secrets manager:** address, auth method, token time to live, health, the audit device's
    state.
  - **Key backend:** the backend, what the key is bound to (TPM, KMS, HSM, or a host file,
    which is a warning), the primary `kid`, the versions in use with record counts, Test,
    Rotate master key (previewed: how many records to rewrap) and Migrate.
- **Needs attention rows:** the manager unreachable or sealed, token renewal failing, the audit
  device failing, v1 values remaining after migration began, a retired `kid` still named by a
  record, the key bound to a host file rather than a TPM.

**The tests:**
- Each backend against a fake, SoftHSM2 for PKCS#11 and a loopback OpenBao dev server where
  their licences are approved.
- AAD: a value moved to another row, field or network refuses, naming the identity expected.
- Rewrap: the ciphertext is unchanged, the wrapped DEK changes, the old `kid` still opens until
  it is retired.
- Migration: resumable, idempotent, every value readable after each step (the no-lockout
  property), the dry run writing nothing.
- `cas` refusals name both versions.
- One registry of sealed stores that every writer must name, held by a scan (C734).
- The secret-leak tests unchanged.
- `test_key_created_once` generalised: no master key is made for a store holding v2 records.

## 9. Size, order and the operator's decisions

**Order:** (R1) envelope encryption, the systemd-creds backend, the store registry and the
Fernet migration: large. (R2) the manager tier, AppRoles, audit and the HMAC masking index:
large. (R3) the Transit, cloud KMS and PKCS#11 backends: medium each.

**The operator's decisions before R1:**
1. OpenBao or Vault (and each new licence: the manager, any client binding, PKCS#11).
2. Where the lab's manager runs (its own container or VM, not the NMAS VM).
3. The lab's vTPM, and the measurement of whether the nightly image carries its state.
4. Sealed export alone, or a Shamir recovery key, for break-glass.
5. How long a retired master-key version is kept (at least the backups' retention).

### Decided, 2026-10-13 (the operator; queued, no build before Phase 7 closes)

These replace sections 3, 5 and 9 where they differ; the rest of the design stands.

- **The manager: OpenBao, on the SAME host as Mercury,** another container in the same stack.
  No extra hosts and no hypervisor connections; a one-host install for the public release.
  Decisions 1 and 2 above are answered. OpenBao's licence (MPL-2.0) is the operator's to confirm
  when the build starts, with any client binding's.
- **The root of trust: manual unseal by default.** In the lab, one key or 2-of-3 shares, kept off
  the host next to the break-glass record. **Optional auto-unseal** where the installer finds a
  real TPM, an HSM or a cloud KMS.
- **A TPM is NOT the default.** The NMAS VM has none (measured, section 5), and a hypervisor's
  vTPM state goes into the same backups as the disk it would protect. Section 5's
  "systemd-creds (default)" is therefore one optional backend, not the default; decision 3
  above falls away for the lab.
- **While sealed, Mercury keeps working where it needs no credential:** monitoring, logs,
  History, Needs attention and the NetBox views. Device operations wait, refused by name (section
  3's "Availability"). Needs attention shows **"Credentials are locked: unseal"**, and the GUI
  has an **unseal page**: the operator types the key or shares there, never at a terminal.
- **Measured for sizing, 2026-10-13:** the NMAS host has 16 GB RAM (11.8 GB available) and
  4 cores; one OpenBao node fits beside the app's containers.
- Still open: decision 4 (break-glass format) and decision 5 (retired key versions).
