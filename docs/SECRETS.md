# Where secrets live, and why

Three stores, deliberately. `scripts/nmas-check-secret-storage` reports all
three by name and never by value, and exits 1 on a finding.

| Secret | Store | At rest | Protected by |
|---|---|---|---|
| `netbox_token`, `prometheus_password`, `grafana_token`, `loki_*`, `oxidized_password`, `kea_password`, `topology_service_token`, `nsot_git_token`, `s3_*` | `data/user_settings.json` | **encrypted** (`enc:v1:` Fernet) | the key + file mode |
| `jenkins_api_key`, `jenkins_token` | `data/jenkins_checks.json` | **encrypted** (`enc:v1:` Fernet) | the key + file mode |
| `ANTHROPIC_API_KEY` | `.env` | **plaintext, by design** | file mode, and nothing else |
| Device credentials | `data/lists/<slug>/devices.csv` | **encrypted** (raw Fernet fields) | the key + file mode |
| The Fernet key itself | `data/key.key` | — | file mode, and nothing else |

**Required modes: `0600` for every file above, `0700` for `data/`.** These are
applied **at creation**, by `config.open_secure()` and `config.secure_dir()`.

---

## Why `ANTHROPIC_API_KEY` stays in `.env`, in plaintext

**Decision, 2026-09-23.** It stays where it is.

An env-style secret is a normal pattern for a process credential, and moving
it into the encrypted store would buy nothing. The app would decrypt its own
API key at startup, using a key that sits **in the same directory, readable
by the same user, protected by the same mode**. Anyone who can read the
ciphertext can read the key beside it. That is not encryption at rest; it is
a longer path to the same plaintext, with a startup dependency added.

So the file mode is the whole control, which means it has to be right and has
to be checked rather than assumed. `nmas-check-secret-storage` reports it as
*"plaintext by design, mode ok"* and **flags it only when the mode is wrong**
— a permanent warning about an accepted design is a warning that gets
ignored, and then the mode regression it exists to catch is ignored with it.

**What this decision does not cover:** rotation. A key readable for a period
stays exposed after a `chmod`, because anything that read it still has it.
Tightening the mode fixes the next three weeks; rotating fixes the last
three. Both, in that order.

## Why the Jenkins credentials *are* encrypted

Opposite conclusion, for a concrete reason: they were in a store that
encrypted nothing.

`/settings` routes them to `data/jenkins_checks.json`, not to
`user_settings.json`, so they never reached `secrets_store.SECRET_KEYS` and
`migrate_plaintext()` never saw them. Measured on the live install they were
**unset** — which is luck, not design. The next person to fill the field
would have landed in a store with none of the other store's guarantees, and
nothing would have said so.

`jenkins_runner.save_config()` now encrypts `SECRET_FIELDS` and
`load_config()` decrypts them. Legacy plaintext reads back unchanged and is
upgraded on the next save, the same contract `secrets_store.decrypt_value()`
already offers.

Unlike `.env`, there is no startup-dependency argument here: the value is
read when Jenkins is contacted, not when the process starts.

## `data/key.key` is the floor

Everything marked *encrypted* above is encrypted **with this key**. A
group-readable `key.key` means the ciphertext beside it was never
meaningfully protected — the encryption and the mode are not two independent
controls, they are one control and a filing convention.

The checker therefore tests `key.key` and `data/` **first and separately**,
and a failure there is reported as invalidating the rest rather than as one
finding among several.

`key.key` has **two producers** — `device.load_key()` and
`secrets_store._get_fernet()`, kept separate deliberately so settings code
does not import device-list side effects. Both create it owner-only, and
`device.load_key()` also tightens an existing file, because a key created
before this existed is the common case. A fix in one producer is not a fix.

## A second copy of `key.key`, and proving it is the right one

**Why it has to stay on the box.** NMAS decrypts secrets with nobody present:
the drift schedule, the redaction value table (every secret, every 30 s), the
NetBox inventory refresh and the freshness signal. So the key is readable by
the process, and whoever holds the disk holds every secret. The encryption
protects copies of `data/` that travel without the key, and nothing on the
live disk. Supplying the key at start-up (a passphrase or a TPM seal) was
considered and declined on 2026-09-25: it costs a person at every reboot and
buys nothing a deployment running unattended can use.

**Why a key copy alone is not a backup.** On 2026-09-25 no vzdump job existed,
so the key and everything it opens were single copies on one disk. After a
disk loss, the key without the ciphertext recovers nothing. The key copy and
a copy of `data/` (the VM image, B6) are one fix.

**The escrow is the break-glass record.** Its passphrase and scrypt are
independent of `key.key` by design, so the record can carry the key without
depending on it. On the NMAS host:

```bash
python3 scripts/nmas-breakglass export --list Default --out /tmp/rcn.bg   # outside the repo
python3 scripts/nmas-breakglass verify /tmp/rcn.bg --live                  # OPENS -- N of N
sha256sum /tmp/rcn.bg
```

Copy it to the laptop, check the sha256 matches, run `verify` there, and check
that the key fingerprint matches the one the host printed. Then delete the
host copy. `--live` decrypts the values actually stored on the host with the
key the RECORD carries, never the one on disk:

- `OPENS`: every stored value opened. This is the key.
- `WRONG KEY`: none opened. Restoring it would lose every secret.
- `MIXED`: some opened. Values under two keys exist; not proven.
- `UNPROVEN` (exit 2): nothing to test against, or a store was unreadable.
  Zero is what a wrong data directory looks like.

A fingerprint match says which file was copied. Only the decrypt says the
copy is of the right key.

**Re-export whenever a device credential rotates.** The device credentials in
the record go stale; the key does not.

**Restoring:** `nmas-breakglass restore-key <record> --out <data dir>/key.key`
writes the key owner-only and refuses to replace an existing file (a fresh
start may have generated one; moving it aside is a person's decision). Then
run `verify <record> --live`.

## Modes are set at creation, not by hand

Nothing in this program set a mode before 2026-09-23. `os.makedirs()` and
`open()` take the process umask; on the deployment host that meant `data/`
at `0755` and every file in it at `0644` — world-readable, including
`key.key` and `.env`.

Fixing modes by hand fixes one install. The creation sites fix every install,
which is why `config.open_secure()` exists and why the callers are:

- `config.save_user_settings()` → `user_settings.json`
- `jenkins_runner.save_config()` → `jenkins_checks.json`
- `secrets_store._get_fernet()` and `device.load_key()` → `key.key`
- `app.save_settings()` → `.env`

`open_secure()` applies the mode **before** writing, via `os.open(..., 0o600)`.
Creating at `0644` and chmod-ing afterwards leaves a window in which the
secret is on disk and world-readable, which is the original defect in
miniature.

On Windows `chmod` cannot express owner-only and the call is a no-op. It is
made anyway and its failure ignored: the deployment target is Linux, and a
development box raising here would be the tail wagging the dog. The checker
is what reports a mode that could not be set.

## What none of this covers

- **A secret in a store this list does not name is not reported as safe — it
  is not reported at all.** The table above is the whole claim.
- **Exposure already incurred.** See the rotation note above.
- **Backups.** A copy of `data/` taken before the modes were tightened has
  the old ones inside it.
