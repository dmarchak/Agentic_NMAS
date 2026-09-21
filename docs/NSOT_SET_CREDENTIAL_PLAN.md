# Item (4) — `set_credential`: rotate r1–r5 to device-generated type-9 secrets

**Status: PLAN ONLY. Nothing in this document is built.**

Goal: the five plaintext router passwords stop being live credentials, and the
cleartext already in 51 commits of history becomes **dead material** — which is
the only thing that actually fixes it, and the prerequisite for Phase 2b's
first push.

---

## 0. Verified facts (measured, not assumed)

### Current state

```
r1–r5   username admin privilege 15 password <cleartext>     ← type 0
s1–s4   username admin privilege 15 secret 5 $1$…            ← type 5, MD5
```

No `aaa new-model` and no `enable secret` on r1. Privilege comes from the
`username` entry, so rotating it does not disturb a separate enable path.

**A finding outside this item's scope, recorded because it is the same class:**
s1–s4 are type **5** (MD5), which is crackable. This item converts the routers
from *plaintext* to type 9; the switches would still be on a weak hash
afterwards. Worth its own decision, not silently bundled here.

### The command, verified on the device

Probed on r2 (10.255.1.12) in config mode with `?`, applying nothing — the
username list was unchanged afterwards and no probe user was created.

```
Cisco IOS XE Software, Version 17.06.01a

username X privilege 15 algorithm-type ?
    scrypt  Encode the password using the SCRYPT hashing algorithm
    sha256  Encode the password using the PBKDF2 hashing algorithm

username X privilege 15 secret ?
    0/5/8/9, <0-9>, LINE
```

So the command is:

```
username admin privilege 15 algorithm-type scrypt secret <new>
```

`algorithm-type scrypt` is explicit and unambiguous. `secret 0 <plaintext>`
would rely on the image's default hash choice, which is exactly the kind of
implicit behaviour that differs between versions.

### The template needs no change — and approval survives

`_common.j2` renders `username {{ u.name }} privilege {{ u.privilege }}
{{ u.secret_kind }} {{ secret(u.secret_ref) }}`. **`secret_kind` is data, not a
branch**: it holds the *keyword* (`password` or `secret`), and the stored value
carries its own type digit. That is already how s1–s4 render `secret 5 $1$…`
through the same macro.

Converting r1–r5 therefore changes **host_vars**, not the template. The
template hash does not move, the bound device set does not move, so the binding
fingerprint does not move: **`cisco_iosxe/base.j2` keeps its approval.**

What *does* change is the ref name. `_h_username()` derives it from the
keyword — `user_{name}_{password|secret}` — so `user_admin_password` becomes
`user_admin_secret`. That rename is part of the operation, not a side effect.

### Management topology, and what a lockout actually costs

```
NMAS 10.255.0.10 → gateway 10.255.0.1 → device Loopback0s (10.255.1.11–15)
10.255.0.1 is on s3.
```

**s3 is the single management gateway for the entire lab.** It is not in scope
here, and that is worth stating plainly: this item touches routers only, and
the one device whose loss would isolate everything is deliberately untouched.

Because the routers are reached by *routing* to their loopbacks, a credential
lockout is confined to the device it happens on — it does not isolate its
neighbours. Blast radius of a failure here is "lose management of one router",
not "lose the lab".

**Out-of-band recovery must be confirmed before the first run**: containerlab
nodes are reachable with `docker exec` on the NMAS host, which bypasses SSH
entirely. That is the recovery path if both the push and the revert fail, and
it should be *demonstrated once* on the first device before it is needed.

---

## 1. Password generation

- **Length 32.**
- **Charset: 79 characters** — `A–Z a–z 0–9` plus ``- _ . + = : @ # % ^ & * , ; ~ $ !``
- **Entropy** ≈ 201 bits. Generated with `secrets.choice`, never `random`.

Excluded, each for a stated reason:

| excluded | why |
|---|---|
| `?` | IOS CLI treats it as a help request mid-command |
| space | token separator; also removes the leading/trailing-space question entirely |
| `"` `'` `\` `` ` `` | quoting and escaping |
| `\|` | the CLI filter operator |
| `[` `]` `<` `>` `(` `)` | **our own redaction guard.** `redact._VALUE` refuses to capture a token starting with these, so a password beginning with one would **not be positionally masked**. Excluding them from the charset entirely is simpler than a first-character rule, and costs ~2 bits |
| `/` | kept out for symmetry with path-like tokens; no entropy cost worth arguing |

The last row is the one to notice: a defensive measure added for D3 constrains
the charset here. The alternative — generating a password our own redactor
cannot mask — is exactly the kind of interaction that is invisible until it is
in a log.

Every candidate is checked against `assert_sendable()` and `assert_printable()`
before use, so the guard decides rather than the generator's author.

---

## 2. Why this is NOT a template deploy

The merge-only deploy path cannot carry this, for three independent reasons:

1. **The program contains a live secret.** The deploy contract records
   `commands` in the result, the audit entry and the log. A confirm hash over
   the literal string would mean the secret is hashed, stored and compared.
2. **`assert_no_mask()` refuses masked content on the deploy path** — correctly.
   So the operator cannot confirm a masked program and have it sent.
3. **The program is not derived from committed intent.** It is generated at
   apply time, and intent is *updated afterwards* from what the device produced.

So `set_credential` is its own operation, with its own confirmation:

- The operator confirms an **operation fingerprint**, not a command string:
  `sha256(device_identity, username, "algorithm-type scrypt", charset_id,
  length, capture_hash)`.
- The password is generated **after** the confirm, in memory, and never leaves
  it except as the CLI line to that one device.
- The plan, the result, the audit row and every log line show
  `username admin privilege 15 algorithm-type scrypt secret <generated>`.

This is a deliberate departure from "what you confirm is what is sent, byte for
byte" — and it is worth naming rather than quietly excepting. The operator
cannot confirm bytes they are not allowed to see. What they confirm instead is
**every property of the operation except the random value**, and the tool
guarantees the value was freshly generated and never recorded. The confirm hash
still binds the device, the user, the algorithm and the capture it was computed
against.

---

## 3. The sequence, per device

Every step names what happens if it fails.

```
 0. PRE-FLIGHT
    - out-of-band recovery demonstrated (docker exec) — first device only
    - require_person gates satisfied; no service path (see §6)
    - device reachable; original session opened and PROVEN with a read
    - current credential read from devices.csv, decrypted in memory
    - current `username` line captured verbatim, for the revert

 1. GENERATE  (in memory)
    - 32 chars from the 79-char set; assert_sendable + assert_printable

 2. STAGE THE NEW PLAINTEXT   .nsot/staging/credential/<device>.enc
    - Fernet-encrypted, mode 0600, BEFORE anything is pushed
    - the crash window: between the device accepting the password and the
      store being written, the new credential exists only in this process.
      A crash there leaves a device nobody can log into. The stage file is
      what makes that recoverable.

 3. invalidate_cache()   ← BEFORE any log line mentions the operation
    - so the very next record is redacted against the new value

 4. PUSH on the ORIGINAL session
      username admin privilege 15 algorithm-type scrypt secret <generated>
    - error_pattern armed; a rejected line aborts before step 5

 5. VERIFY on a FRESH connection, with the NEW credential
    - a new TCP session, new authentication — not the pooled one, and not the
      original. The original session is already authenticated; it would pass
      whatever the device now believes.
    - the check is a login plus one privileged read.

 6a. VERIFY FAILED  →  REVERT on the original session
    - re-send the captured original line verbatim
    - re-verify with the ORIGINAL credential on a fresh connection
    - report: reverted / revert-failed-device-may-be-locked-out
    - the original session is NOT closed until this resolves

 6b. VERIFY SUCCEEDED  →  COMMIT THE RESULT
    - capture `show running-config | include ^username admin` → the $9$ hash
    - template secret  user_admin_secret  ← the hash, kind=hash
    - devices.csv row  ← the new plaintext (Fernet), THIS device only
    - delete template secret user_admin_password (a dead credential)
    - host_vars: secret_kind password→secret, ref →user_admin_secret,
      secret_refs updated
    - golden + intent in ONE commit
    - evict the pooled connection (it holds the old credential)
    - clear the stage file

 7. POST-CHECK
    - round-trip still 100% for this device
    - template_report still clean; approval unaffected (§0)
    - a fresh plan for this device shows ZERO commands to send
```

**The original session is never closed before the new credential is proven.**
That is the whole lockout defence, and it is why the push and the revert both
run on a session that was authenticated before anything changed.

---

## 4. What the operator sees and confirms

```
Rotate login credential — r2 (10.255.1.12)

  user              admin (privilege 15)
  current form      username admin privilege 15 password <cleartext, type 0>
  new form          username admin privilege 15 algorithm-type scrypt secret …
                    → the device stores a type 9 (scrypt) hash

  new password      generated at apply time, 32 characters, never displayed,
                    never logged, never written to the audit trail
  stored where      this device's row in devices.csv (encrypted at rest)
                    the resulting $9$ hash → credential store as a hash secret
  replaced          the old plaintext is deleted from the credential store

  lockout defence   the current session stays open until the new credential is
                    proven on a separate, fresh login. If that fails, the
                    original line is restored on the still-open session and the
                    result is reported either way.

  out-of-band       docker exec on the NMAS host  (confirmed reachable ✓)

  NOT changed       the template (no approval revocation)
                    any other device
                    the shared credential profile — a per-device rotation
                    writes a per-device credential, never a shared one

  history           the old cleartext remains in 51 commits of git history.
                    After this it is a DEAD credential. Rotation is what makes
                    that true; nothing can remove it from history.

  Type the hostname to confirm:  [______]
```

Typing the hostname, rather than clicking OK, because this is the one operation
whose failure mode is *losing the ability to reach the device at all*.

After the run, the report states: pushed / verified / committed, or the exact
step that failed and what state the device is in — using the same
`device_changed: true|false|None` honesty as the deploy path, where `None`
means "could not be read, so not known".

---

## 5. Rotation kind — replacing the `rotatable` boolean (design only)

Today: `"rotatable": entry.get("secret_kind") != "hash"`, which says a hash
cannot be rotated. That is wrong, and this item disproves it: a type-9 secret
rotates perfectly well — you generate plaintext, push it, and capture the hash
the device produces. What differs is **how**, not **whether**.

Proposed, for Part 2's scheduler:

| `rotation_method` | meaning | example |
|---|---|---|
| `set_plaintext` | we choose the value; the device stores it verbatim | SNMP community |
| `set_and_capture_hash` | we choose plaintext, push it, and the **device** produces the stored value, which we must read back | `username … algorithm-type scrypt secret` |
| `manual` | cannot be rotated by this tool | PKI certificate chain, licence UDI |

The distinction that matters to a scheduler is whether the stored secret is
**knowable before the push** (`set_plaintext`) or **only afterwards**
(`set_and_capture_hash`). The second needs a read-back step and a commit, and
is therefore not idempotent-by-retry: a failed capture after a successful push
leaves the device rotated and the record stale, which is precisely what the
staging file in §3 exists to survive.

`rotatable` stays as a derived property (`rotation_method != "manual"`) so
nothing that reads it breaks.

---

## 6. Sequencing and who may run it

**First device: r2.** Reasons, in order:

1. Most successful deploy history — three completed runs through the confirmed
   path, so the transport, the settle windows and the golden commit are all
   proven on it specifically.
2. No BGP. If recovery needs a reload, no peering has to re-converge.
3. It is the device the syntax was probed on, so the verified command and the
   device it was verified against are the same.

It is **not** chosen for being least important — the routers are equivalent in
that respect, because a credential lockout is confined to one device (§0).

Then **r1, r3, r4, r5 sequentially**, stopping at the **first** failure. Not
parallel: the failure mode is lockout, and discovering a systematic problem
five times simultaneously is strictly worse than discovering it once.

**A person initiates and confirms.** `require_person_for_approve` and
`require_person_for_confirm` are both ON and `service_allowed_operations` is
empty, so `nmas-automation` cannot run this today — which is correct for a
first run. Part 2's scheduler adds `credential_rotation` to that allowlist **by
name**, and that is a separate, deliberate decision to take then, not now.

---

## 7. devices.csv, profiles, and overrides

Where the login credential lives depends on the list's source, and the rotation
must write back to **whichever source actually supplied it** — visible on every
device dict as `_cred_source`.

| source | where it lives | what the rotation writes |
|---|---|---|
| `local` (the default list) | that device's row in `devices.csv`, Fernet-encrypted | rewrite **that row only**, via `write_devices_csv()` |
| `netbox` + device override | `credential_profiles.json` → `device_overrides[ip]` | update that override |
| `netbox` + shared profile | a profile used by **many** devices | **write a new device override instead** |

The third row is the rule that matters. A per-device rotation must never
rewrite a shared profile: that would silently change the credential every other
device inherits, while only one device actually had its password changed. The
result would be a fleet that cannot be logged into, caused by an operation the
operator scoped to one device.

Both write paths already invalidate the redaction cache —
`credentials._save()` and `device.write_devices_csv()` — so the new value is
redacted from the next log record rather than at the next TTL expiry.

---

## 8. Open questions

1. **s1–s4 are type 5 (MD5).** Out of scope here; converting them to type 9 is
   the same operation with a different starting point. Worth deciding before
   Phase 2b's first push, since the same "dead material" argument applies less
   strongly to a weak hash than to cleartext, but it still applies.
2. **`enable secret` does not exist on these devices.** If one is added later,
   it is a second credential with its own rotation. Not created by this item.
3. **The confirm-fingerprint departure in §2** is the one place this operation
   deviates from the deploy contract. Flagging it explicitly for a decision
   rather than burying it in an implementation.
