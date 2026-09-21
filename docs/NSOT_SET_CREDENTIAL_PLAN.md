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

**s3 is the single management gateway for the entire lab.** Stage 1 touches
routers only; s3 is converted in **stage 2 and goes LAST of all nine**, because
it is the one device whose loss isolates everything else.

Because the routers are reached by *routing* to their loopbacks, a credential
lockout is confined to the device it happens on — it does not isolate its
neighbours. Blast radius of a failure here is "lose management of one router",
not "lose the lab".

**Out-of-band recovery is the serial console on the containerlab host**, which
is `10.0.0.210` — **not** the NMAS. `docker exec` reaches the *container*, not
IOS; the network OS runs inside qemu behind a serial console on `:5000`. The
verified procedure is in **§GAP 3**, and it is *demonstrated* before it is
needed, not at the moment of need.

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

  out-of-band       serial console on the containerlab host (10.0.0.210):
                      ssh dmarchak@10.0.0.210
                      docker exec -it clab-rcn-lab1-r2 telnet localhost 5000
                      exit with  ^]  then  quit  — ONE session only
                    demonstrated on this device before this run ✓

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

## 8. Decisions taken

1. **The confirm-fingerprint departure (§2) is ACCEPTED**, as a *named
   exception* rather than a silent one: the operator confirms every property of
   the operation, and the tool guarantees the one value they may not see was
   freshly generated and never recorded. This is the only place in the system
   where "what you confirm is what is sent, byte for byte" does not hold, and
   it says so.

2. **s1–s4 (type 5, MD5) convert too** — as **stage 2**, after every router
   succeeds, and **before** Phase 2b's first GitHub push. **s3 goes LAST**: it
   owns `10.255.0.1` and is the lab's single management gateway, so it is the
   one device whose loss isolates everything else. OOB recovery is demonstrated
   on s3 *before* s3 is touched.

3. **OOB recovery is demonstrated on r2 before r2 is rotated**, not merely
   documented. See §GAP 3 — the path is verified and the procedure below.

---

## GAP 1 — Credential consumers

`admin` is not "the NMAS credential". It is **the** credential, shared by every
consumer, and a rotation that only updates `devices.csv` breaks the rest
silently.

### Inventoried on the NMAS (measured, not assumed)

| consumer | how it authenticates | scope | breaks how |
|---|---|---|---|
| **NMAS** | `devices.csv`, per-device row, Fernet-encrypted | all 9 | loudly — connection errors in the UI |
| **Oxidized** | **one global** `username`/`password` in `/opt/oxidized/config`; `router.db` maps only `name: 0` | all 9 | **silently** — see below |
| **`~/lab-configs/yang-push-sub.py`** | **hardcoded** `username="admin", password=…`, NETCONF :830 | ad-hoc, not a service | silently, next time it is run |

No Ansible inventory, no Jenkins device credentials, and `snmp-exporter` uses a
community rather than this account.

### Why Oxidized is the dangerous one

Oxidized failing to log in does not produce an error downstream. The sync reads
**Oxidized's git repo**, so a credential failure upstream looks exactly like
"no changes since last time". The startup files quietly stop tracking the
devices, and the first symptom is a redeploy booting stale configuration —
which is finding #1 in the write-up notes, arrived at by a different route.

So: **a rotation that breaks Oxidized also breaks redeploy persistence, and
neither failure announces itself.**

### The design question: per-consumer accounts

Today one account serves three consumers, so a rotation is an all-or-nothing
event across all of them. Two options:

**(a) Keep one account; the operation updates every consumer.** Simplest, and
what stage 1 must do regardless — but it means every future rotation has to
know the full consumer list, and the list is only correct until someone adds a
script.

**(b) Split by consumer** — `admin` (people), `oxidized` (harvest), and
optionally `nmas`. Each with its own type-9 secret, rotated independently.
Oxidized's CSV source supports per-device credentials
(`map: username:`, `password:`), so its account can differ per device rather
than being one global value.

**Recommendation: (a) for stage 1, then (b) as its own item.** Splitting
accounts during a rotation means changing *what authenticates* and *what the
password is* in the same operation, and if the device becomes unreachable you
cannot tell which half did it. Do the rotation first, with the consumer list
explicit; split afterwards, when each move is individually reversible.

### What the operation does about it, in stage 1

Per device, after a successful rotation:

1. **NMAS** — `devices.csv` row rewritten (§7). Automatic.
2. **Oxidized** — its credential updated, then **an immediate fetch requested**
   and confirmed (§GAP 2). Automatic.
3. **`yang-push-sub.py`** — **not** updated automatically: it is an ad-hoc
   script with a hardcoded literal, and silently rewriting someone's source is
   worse than telling them. It is **listed in the result as broken**, by path
   and line number.

> Every consumer is either updated by the operation or named in the result as
> broken. There is no third category, and "we think that's all of them" is not
> one either — the inventory above is part of the plan so that adding a
> consumer means editing this table.

---

## GAP 2 — Redeploy persistence, and proving it

A rotation that does not reach the startup files produces a device that works
today and is **unreachable after the next `--cleanup`**, with the old password
in a file and the new one in `devices.csv`. That is strictly worse than not
rotating.

### The sequence, appended to §3 step 6b

```
 6b-vii.  UPDATE OXIDIZED's credential FOR THIS DEVICE  (router.db row)
 6b-viii. REQUEST A FETCH
            GET  http://127.0.0.1:8888/node/next/<node>
            node name = the device IP (router.db maps name: 0)
 6b-ix.   CONFIRM THE FETCH SUCCEEDED  ← not "requested", succeeded
            read the node status from oxidized-web and require a SUCCESSFUL
            fetch timestamped AFTER the rotation
 6b-x.    RUN THE SYNC
            /home/dmarchak/bin/clab-sync        ← see below
 6b-xi.   VERIFY ON THE CLAB VM  (10.0.0.210), not the NMAS's local copy
            ~/labs/lab/configs/<device>.cfg contains the NEW $9$ hash
```

**Step 6b-ix is a separate step for a reason.** Requesting a fetch and a fetch
succeeding are different events. If the sync runs on Oxidized's *previous*
copy, the clab-VM check at 6b-xi fails — and it fails for a reason that looks
nothing like its cause: the startup file simply does not contain the new hash,
with no indication that the harvest never happened. Confirming the fetch turns
a confusing downstream failure into an obvious upstream one.

**Step 6b-vii depends on stage 0 having already moved Oxidized to per-device
credentials.** Oxidized's credential is a *single global* value, so the moment
r2 has a different password from the other eight, one global value cannot serve
both. There is no ordering of stage 1 that avoids this — it breaks on the first
device.

**The verification must read the clab VM.** `~/lab-configs/configs/` on the
NMAS is the sanitiser's *staging output*; the file that actually boots the node
lives on `10.0.0.210`. Checking the local copy would confirm that we generated
something, not that it was delivered — a distinction this project has already
paid for once.

Only then does the result say **"survives redeploy"**. Until measured, it says
"not verified", not nothing.

### Permission to run the sync — a narrower answer than the one asked for

The request was for the narrowest sudoers rule allowing
`systemctl start clab-sync.service`. Checking first:

```
/etc/systemd/system/clab-sync.service   root:root  0644   User=dmarchak
/home/dmarchak/bin/clab-sync            dmarchak   0700
NMAS app process                        runs as dmarchak
```

**The unit runs as `dmarchak`, and the app already runs as `dmarchak`.** So the
app can simply execute `/home/dmarchak/bin/clab-sync` directly — same script,
same user, same `flock` (which is inside the wrapper, so a concurrent timer run
exits cleanly). **No sudoers rule, no polkit rule, no privilege boundary
crossed at all.**

**Recommendation: run the script directly.** The narrowest privilege is none.

If journal integration is wanted instead, the narrowest rule is:

```
dmarchak ALL=(root) NOPASSWD: /usr/bin/systemctl start clab-sync.service
```

— one verb, one unit, fully qualified. With a **caveat worth stating plainly**:
that rule is safe *only because* the unit has `User=dmarchak`. `ExecStart`
points at a script that `dmarchak` owns and can rewrite, so if the unit is ever
changed to run as root, this rule silently becomes a root escalation. If you
take the systemd route, that constraint belongs in a comment in the unit file,
not only here.

---

## GAP 3 — Out-of-band recovery, verified

The containerlab host is **`10.0.0.210`**, not the NMAS. `docker exec` on the
NMAS reaches nothing; the containers live there.

And for vrnetlab images, `docker exec` reaches the *container*, not IOS — the
network OS runs inside qemu behind a serial console.

### Verified on r2

```
dmarchak@10.0.0.210 is reachable from the NMAS by key; dmarchak is in the
docker group, so no sudo is needed.

Listeners inside clab-rcn-lab1-r2:   *:5000  and  *:4000   (qemu serial)
/usr/bin/telnet is present inside the container.

Probe:  docker exec -i clab-rcn-lab1-r2 telnet localhost 5000
        → "Connected to localhost."  and released cleanly
        → established sessions on :5000 afterwards: 0
```

`clab-rcn-lab1-s3` (vIOS-L2) exposes the **same** `*:5000` / `*:4000`, so the
procedure is identical on both platforms — which was not safe to assume.

### The procedure

```
ssh dmarchak@10.0.0.210
docker exec -it clab-rcn-lab1-<node> telnet localhost 5000
   <Enter> for a prompt
   ... recover ...
   ^]  then  quit          ← releases the console; it allows ONE session
```

Two properties to respect:

- **The console allows one session at a time.** An abandoned connection locks
  out the recovery path itself. Always exit with `^]` then `quit`; the probe
  above confirms release by counting established sessions afterwards.
- **It survives credential loss entirely** — the serial console bypasses SSH
  and the `username` database is irrelevant to reaching the prompt.

**Demonstrated before use, not at the moment of need**: once on r2 before
stage 1, and once on s3 before stage 2, each time reaching an IOS prompt and
releasing cleanly.

---

## 9. Revised sequencing

```
 STAGE 0   1. demonstrate OOB on r2 (GAP 3) — reach a prompt, release cleanly
           2. move Oxidized to PER-DEVICE credentials (router.db columns),
              every device still on its CURRENT password
           3. confirm how the installed Oxidized reloads its node list
           4. confirm a SUCCESSFUL fetch for all nine
           5. run clab-sync; clab-VM files unchanged except expected

 STAGE 1   r2  →  r1  →  r3  →  r4  →  r5      sequential, stop at first failure
           each: rotate → verify → commit → update consumers → prove redeploy

 STAGE 2   demonstrate OOB on s3
           s1  →  s2  →  s4  →  s3             s3 LAST: management gateway
           same operation, type 5 → type 9

 THEN      Phase 2b adopt-first increment; the cleartext in history is by
           then a dead credential, and the weak hashes are gone too
```

### Why stage 0 carries the Oxidized migration

Step 2 **changes how Oxidized stores credentials without changing any
credential.** Every device stays on its current password; only the place the
password is read from moves, from one global value to a per-device column. That
makes it independently reversible and independently provable — a normal fetch
cycle either works or does not, with no rotation in flight to confuse the
diagnosis.

Doing it during stage 1 instead would mean changing *where the credential comes
from* and *what the credential is* in the same step, on a device that is
temporarily unreachable if either goes wrong.

Steps 4 and 5 are the part most easily skipped: proving the
Oxidized→sync→clab-VM loop on devices **nothing has changed** separates "the
loop works" from "the rotation worked", which are otherwise discovered
together, at the worst moment.

`router.db` holds plaintext credentials, so it must be **owner-only (0600) and
owned by the user Oxidized runs as** — it is gaining eight more secrets than it
had.

---

## STAGE 0 — COMPLETE (2026-09-21)

Executed and measured. Nothing was rotated; no device credential changed.

### 1. OOB recovery demonstrated on r2

```
ssh dmarchak@10.0.0.210 → docker exec -i clab-rcn-lab1-r2 → 127.0.0.1:5000
  received 22 bytes,  prompt reached: r2>
  established sessions on :5000 afterwards: 0
```

The console lands in **user EXEC, unauthenticated** (`r2>`). With no
`enable secret` configured, `enable` then gives privilege 15 without a
password. That is the recovery path working — and worth stating plainly that
the serial console is a complete authentication bypass, acceptable only because
reaching `10.0.0.210` needs an SSH key.

### 2–3. Oxidized moved to per-device credentials

`router.db` `ip:model` → `ip:model:username:password`, nine rows, **every
device still on its current password**. Config map gained `username: 2`,
`password: 3` (indentation detected, not guessed — see below). Node list
reloaded with `GET /reload` → HTTP 200. Oxidized 0.37.0.

`router.db` is now **0600 `oxidized:oxidized`**; it was 0644 and has gained
eight more secrets.

### 4. Fetches confirmed — and the global credential removed to prove it

A successful fetch with the global credential still present would prove
nothing: it could be the fallback. So the global `username`/`password` were
**removed from the config entirely**, making a successful fetch possible *only*
via `router.db`.

```
fresh successes with NO global credential: 9 / 9
```

Net effect beyond the migration: the live `config` (0644, world-readable) no
longer contains a plaintext password at all. Rollback copies that do were
tightened to 0600.

**Pre-existing condition recorded before any change:** `s1` (10.255.1.21) was
`no_connection`, timing out at 30.9s, with `mtime` of 19 Sep — while NMAS
logged into it fine with the same credentials. That is the direct cause of the
stale `s1` startup file in write-up finding #1. It fetched successfully in both
rounds afterwards, so it is intermittent rather than broken. **Not caused by
this work**, and worth its own look.

### 5. Sync run and verified on the clab VM

Run **directly** as `/home/dmarchak/bin/clab-sync` — no sudoers, no polkit
(§GAP 2). Validation passed on all nine, copied, committed.

```
clab VM ~/labs/lab/configs, before → after:
  all nine files CHANGED, +1 / -1 lines each
  the only difference in every file:
    - ! <dev> - from Oxidized HEAD b774547
    + ! <dev> - from Oxidized HEAD 14efa84
  non-header changed lines across all nine: 0
```

Exactly the expected change — the header carries Oxidized's commit sha, and the
fetches produced a new commit. **The loop is proven end to end on devices
nothing has changed**, which is what stage 0 exists for.

### A mistake worth recording

Patching the Oxidized config by regex destroyed two lines — a `sub` that
matched nothing reported success, and a follow-up `gsub` deleted `model: 1` and
`username: 2`. Restored from the pre-edit backup and redone **line-based**:
locate `map:`, walk its indented children, insert after them, then **prove it
by parsing the YAML** rather than by reading a diff.

This is the fourth scripted-edit destruction in this project, and the first
outside the repository — where `scripts/check_removed_definitions.py` and the
pre-commit hook do not reach. The countermeasure that worked here is the same
one: make the edit assert its own effect (`abort unless it applied`, then parse
and compare), rather than trusting that a pattern matched.

---

## 10. Still open

1. **Per-consumer account split** (GAP 1 option b) — recommended as its own
   item after stage 1, not during it.
2. **`yang-push-sub.py` holds a hardcoded credential.** Out of scope to fix
   here beyond reporting it, but it is a plaintext password in a source file
   and belongs in the credential store like everything else.
3. **The pipeline is not version-controlled** (`docs/ARCHITECTURE.md`). The
   truncation guard is exactly the kind of logic whose history matters.
