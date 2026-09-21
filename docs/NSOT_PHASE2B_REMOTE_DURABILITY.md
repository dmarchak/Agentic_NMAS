# Phase 2b — Remote durability: one private GitHub repository per device list

**Status: PLAN ONLY. Nothing in this document is built.**

Numbered 2b because it completes Phase 2 (the golden config repository): the
repo exists and is version-controlled, but lives on one server. "Phase 6" is
taken by GUI completeness.

## Sequencing

This plan subsumes much of queued item (1), backend fixes. It is **not** next.
Order:

1. **Forward-path secret masking** — queued (2). Stop *adding* plaintext to
   history before caring where history is published.
2. **Rest of the multi-network audit** — queued (3): write paths resolving the
   list at write time, and whether the credential store keys secrets by device
   name alone.
3. **Set-credential + convert r1–r5 to NEW type-9 secrets** — queued (4).
   The five plaintext router passwords stop being a live exposure, and the
   rotation is to *new* values, so the published-history problem shrinks to
   dead credentials.
4. **Adopt-first increment of this plan** — §1 + adoption + §5 + §7.
5. Phases 4, 5, 6.

Steps 1–3 are what make step 4's first push safe. That ordering is the point:
by the time anything is published, the plaintext in history is dead material.

Goal: **a list's configuration history survives the loss of this server, and
setting that up is as close to automatic as it can be made.** MinIO stays
available as optional DR; it is not on the critical path.

---

## 0. What is already true (verified, not assumed)

Measured on the live NMAS before writing this. These findings change the
design, so they come first.

### The default list is already configured, by hand

```
~/.ssh/config  (hand-edited, lines 19-23)
    Host github-nsot
        HostName github.com
        User git
        IdentityFile ~/.ssh/nsot_deploy
        IdentitiesOnly yes

ssh -T github-nsot
    Hi dmarchak/rcn-nsot-config! You've successfully authenticated
```

So the deploy key is live, scoped to `dmarchak/rcn-nsot-config`, and that repo
is **private and empty** (`ls-remote` succeeds via the key and returns no
refs). The key is at `~/.ssh/nsot_deploy`, **not** `~/.ssh/nsot_<slug>`.

**Consequence: the first thing this phase needs is an ADOPT path, not a create
path.** A wizard that assumes greenfield would either duplicate this setup or
overwrite a working one. Adoption is also the cheapest possible first
milestone — it makes the default list compliant with zero new SSH material.

Adoption must not move the existing `Host github-nsot` block out of
`~/.ssh/config`. Item 2 says NMAS never edits that file; it also must not
*relocate* what a human put there. Adopt = record "this list uses alias
`github-nsot`", verify it, and leave the file alone.

### `known_hosts` verification works, and is already correct here

`https://api.github.com/meta` returns both:

| field | contents |
|---|---|
| `ssh_keys` | 3 entries, `known_hosts`-ready (`ssh-ed25519 AAAA…`) |
| `ssh_key_fingerprints` | `SHA256_ED25519`, `SHA256_ECDSA`, `SHA256_RSA` (base64, no `SHA256:` prefix) |

Verified live: every `ssh_keys` entry's SHA256 fingerprint matches the
published `ssh_key_fingerprints`, and all three `github.com` entries already in
the NMAS `known_hosts` are authoritative.

**Design note.** Write from `ssh_keys` rather than comparing fingerprints after
a trust-on-first-use fetch — the material arrives over a CA-verified TLS
connection, which is the actual trust anchor. Cross-checking each key against
the `ssh_key_fingerprints` in the *same response* is still worth doing, but
it catches a truncated or corrupted download, **not** a hostile one. Saying so
plainly matters: a self-consistency check described as "verification" is the
kind of claim this project has already had to withdraw once.

### The push hook already pushes tags. It does not push notes.

Tested by cloning the live repo, pushing to a scratch bare remote with the
hook's exact command, and inspecting what landed.

| | result |
|---|---|
| `git push --follow-tags origin main` | **18 of 18** tags pushed |
| `baseline/*` (2) and `golden/<device>/*` (15) | all present; all are real annotated tag objects |
| plain `git clone` of the remote | gets all tags |
| `refs/notes/ci` after the hook's push | **0** — not pushed |
| explicit `git push origin 'refs/notes/*'` | works |
| plain `git clone` of a remote that has notes | fetches **0** notes without an explicit refspec |

So objective-1.4 tag evidence already travels; **this was not the first fix**,
contrary to the assumption in the question. Two real caveats:

- `--follow-tags` moves tags only when there are commits to push. Benign today
  (`save_golden` always commits before tagging), but a tag added with no new
  commit would not go.
- `_prune_device_tags` (retention 50) deletes local tags and **deletions do not
  propagate**. Remote and local tag sets diverge over time. For an archive
  that is arguably correct; it should be a stated decision, not an accident.

Notes are a real gap but **not yet a live one**: `add_ci_note()` has no caller,
so `refs/notes/` is empty. It becomes live the moment CI results are recorded.

### Auth today is deploy-key-only; the token setting is inert

`push_hook()` runs a bare `git push`; nothing injects a credential.
`nsot_git_auth_mode` and `nsot_git_token` are declared, encrypted at rest, and
shown in the UI — and **read nowhere**. Selecting `token` and pasting a PAT
changes nothing, and an HTTPS remote then fails with
`could not read Username for 'https://github.com'`.

Option A says the token is never stored. So this phase **deletes
`nsot_git_token` and `nsot_git_auth_mode`** rather than wiring them up. Leaving
an encrypted-at-rest secret field that the product promises never to store is a
contradiction in the settings schema.

`GIT_TERMINAL_PROMPT=0` is already set in `_git_env()`, so a credential-less
push fails fast instead of hanging a hook thread. Keep that.

### The remote settings are global; Option A needs them per list

`nsot_git_remote_url`, `nsot_git_branch`, `nsot_git_auto_push` live in
`data/user_settings.json` — one value for the whole installation. One repo per
list cannot be expressed. **This is the single largest structural change in the
phase**, and everything in items 1–6 depends on it.

Precedent exists: `data/lists/{slug}/source.json` already holds per-list
inventory config (`modules/inventory/source_config.py`). A sibling
`data/lists/{slug}/remote.json` follows an established pattern rather than
inventing one.

### What a push would publish

| material | count | recoverable |
|---|---|---|
| SNMP community | 18 (2 × 9 devices) | **yes, cleartext** |
| user password, type 0 | 5 — every C8000v router | **yes, cleartext** |
| user secret, type 9 | 4 — every switch | no (salted hash) |
| commits / touching `golden/` | 51 / 10 | history goes too |

`host_vars/` is clean: `secret_refs` only, no `secrets:` mapping, as
`write_committed()` enforces.

---

## 1. Per-list remote configuration (the foundation)

`data/lists/{slug}/remote.json`, absent = no remote:

```json
{
  "provider": "github",
  "ssh_alias": "github-nsot",
  "owner": "dmarchak",
  "repo": "rcn-nsot-config",
  "branch": "main",
  "key_path": "~/.ssh/nsot_deploy",
  "auto_push": false,
  "managed_by_nmas": false,
  "adopted_at": "2026-09-21T04:10:00Z",
  "verified_at": "",
  "acknowledged_secrets": null
}
```

- `ssh_alias` is **explicit per list**, as required. The default list keeps
  `github-nsot`; new lists get `nsot-<slug>`.
- `managed_by_nmas: false` marks an adopted setup. NMAS never rewrites the key
  or the SSH stanza for these — it only verifies and pushes.
- `auto_push` starts **false** always. Item 6 turns it on, after a successful
  push, never before.

Migration: if the global `nsot_git_remote_url` is set when this lands, copy it
into the current list's `remote.json` once and stop reading the global. Per the
settings rule, the old key is not deleted.

`push_hook()` changes from reading global settings to reading the committing
list's `remote.json`. The hook context already carries `list_name`.

**Two lists must push only to their own remotes.** This is the property most
worth a test, because the failure is silent and catastrophic: one network's
history landing in another network's repo.

---

## 2. Notification and status (item 1)

- **Banner**: persistent, non-modal, on any list with no `remote.json` —
  *"This network's configuration history exists only on this server. Set up a
  private GitHub repository →"*. Dismissible per list per session, never
  permanently: the condition is still true tomorrow.
- **List creation**: final step offers setup, with **Later**. `Later` is a
  first-class outcome, not a nag deferral.
- **Git tab badge**, per list, from `remote.json` + last hook result:
  `No remote` · `Configured, never pushed` · `Pushed <relative time>` ·
  `Push failing — <reason>` · `Auto-push off`.

The badge must distinguish **"configured but never pushed"** from **"pushed"**.
There is no manual push route today, so a remote configured after the last
commit stays unpushed until the next commit — silently. Item 6's explicit
**Push now** is what closes that, and the badge is what makes it visible.

---

## 3. Local automation (item 2)

Per list, idempotent, each step reporting what it did or why it skipped:

1. **Key**: `ssh-keygen -t ed25519 -f ~/.ssh/nsot_<slug> -N '' -C "nmas nsot <slug>"`,
   mode 0600. Never overwrite an existing key — if the path exists, adopt or
   refuse with the path named.
2. **SSH alias**: write `~/.ssh/nsot_hosts.conf` (0600) containing only
   NMAS-managed `Host` stanzas, and ensure `~/.ssh/config` begins with
   `Include ~/.ssh/nsot_hosts.conf`.
   - Adding that one `Include` line is the **only** modification to
     `~/.ssh/config`, ever, and only if absent. `Include` must appear before
     any `Host` block to apply globally — so it is prepended, and the existing
     content is backed up to `~/.ssh/config.nmas-bak-<ts>` first.
   - Idempotent by stanza: rewriting regenerates only the `Host nsot-*` blocks
     it owns and preserves the rest of the file verbatim.
   - The existing hand-written `Host github-nsot` stays in `~/.ssh/config`
     untouched; the adopted default list points at it.
3. **known_hosts**: fetch `api.github.com/meta`, cross-check each `ssh_keys`
   entry against `ssh_key_fingerprints` in the same response, write to a
   dedicated `~/.ssh/nsot_known_hosts` referenced from the managed stanzas via
   `UserKnownHostsFile`. A dedicated file means NMAS never rewrites the user's
   `known_hosts`, and a stale GitHub key rotation is repaired by re-running
   this step rather than by hand-deleting a line.
   - `StrictHostKeyChecking yes` in the managed stanzas — with the keys
     pre-placed, strict is now the *usable* setting, and TOFU is never reached.

---

## 4. Repository and key provisioning (item 3)

### 4a. AUTOMATIC — token in memory only

**Required token permissions, verified against GitHub docs:**

| operation | fine-grained PAT | classic |
|---|---|---|
| `POST /user/repos` (create private repo) | **Administration: write** (account-level) | `repo` |
| `POST /repos/{owner}/{repo}/keys` (add deploy key) | **Administration: write** (repository-level) | `repo` |
| `GET /repos/{owner}/{repo}/keys` (list, for idempotency) | Administration: read | `repo` |

Note `public_repo` is **not** sufficient — creating a *private* repo needs full
`repo` on a classic token.

Flow: paste token → create private repo (`private: true`, `auto_init: false`)
→ `POST .../keys` with `read_only: false` and the generated public key → drop
the token. Held in a local variable for the duration of one request handler;
never written to settings, never logged, never in the audit trail, never in an
error message.

> **The finding that shapes this path.** GitHub documents: *"If the deploy key
> is created with a personal access token, deleting the personal access token
> will also delete the deploy key."*
>
> A security-conscious user who pastes a token into a tool that promises not to
> store it will very reasonably delete that token afterwards — and that
> silently revokes the deploy key. Pushes then fail at some later commit, from
> a background hook, which is exactly this project's dominant failure mode.
>
> The UI must say this **before** the token is used, in plain words: *"Keep this
> token, or revoke it only after replacing the deploy key — deleting the token
> deletes the key GitHub uses to accept pushes."* The alternative — recommending
> the guided manual path for anyone who intends to discard the token — should be
> offered on the same screen.

`read_only: false` is required; a read-only key produces a push failure that
looks like a permissions bug. It is also worth **verifying** write access after
registration rather than trusting the flag, since that is the whole point of
the key. See §5.

### 4b. GUIDED MANUAL

No token ever. Prefilled links, copy buttons, then **Test connection**:

1. `https://github.com/new?name=<suggested>&visibility=private` — prefilled and
   private-selected.
2. `https://github.com/<owner>/<repo>/settings/keys/new` — direct to the
   deploy-key page.
3. Public key displayed with a copy button and an explicit **"Allow write
   access"** reminder, since that checkbox is off by default and is the single
   most common cause of a failed first push.
4. **Test connection** runs §5 in full.

This path must be as prominent as the automatic one, not a fallback — for a
one-off setup on a lab server it is arguably the better choice, and the deploy
key it produces has no token lifetime attached to it.

---

## 5. Pre-push verification (item 4) — refuse on failure, with the reason

All five must pass. Each reports the check that failed and the fix.

1. **Key authenticates**: `ssh -T <alias>` → `Hi <owner>/<repo>!`. The reply
   form is a free primitive: `Hi owner/repo!` means a **deploy key scoped to one
   repo**; `Hi username!` means an **account-wide key**, which would grant this
   list push access to every repo the account owns — refuse, and say so.
2. **Read works**: `git ls-remote <alias>:<owner>/<repo>` succeeds.
3. **Write works** — and the probe must publish **nothing**.

   A read-only deploy key passes checks 1 and 2 and fails only on a write, so
   the property has to be exercised rather than inferred from the `read_only`
   flag. But the obvious probe is a trap:

   > `git push <remote> HEAD:refs/nmas/writetest` pushes **HEAD**, and HEAD
   > carries all 51 commits and every blob under them — including the 10 golden
   > commits with plaintext passwords and SNMP communities. Deleting the ref
   > afterwards does not remove the objects from GitHub. **The verification step
   > would publish exactly what §6's acknowledgement exists to gate**, before the
   > operator had acknowledged anything.

   The probe therefore carries no history and no content:

   ```
   tmp=$(mktemp -d)                      # a throwaway repo, NOT config_repo
   git -C "$tmp" init -q
   tree=$(git -C "$tmp" hash-object -t tree /dev/null)      # the empty tree
   commit=$(git -C "$tmp" commit-tree "$tree" -m "nmas write probe")
   git -C "$tmp" push <remote> "$commit:refs/nmas/writeprobe"
   git -C "$tmp" push <remote> :refs/nmas/writeprobe        # clean up the ref
   rm -rf "$tmp"
   ```

   An orphan commit (no parents) with the empty tree: one commit object, one
   tree object, **zero blobs**, nothing reachable from `config_repo`. It proves
   the key can write and leaves the repository with no content in it.

   Run this **before** the privacy check is satisfied only if it is this
   probe — the old form had to run after §6, which would have meant asking the
   operator to acknowledge publication in order to test connectivity.
4. **Repository is PRIVATE** — anonymous, unauthenticated:
   - `GET https://api.github.com/repos/{owner}/{repo}` → **200 means public →
     refuse.**
   - `GET https://github.com/{owner}/{repo}.git/info/refs?service=git-upload-pack`
     → **200 means public → refuse.**
   - Measured on the real private repo: API `404`, git endpoint `401`. **The
     codes differ per endpoint, so this cannot be a single-code check**, and
     `404` alone is ambiguous between "private" and "does not exist" — which is
     why privacy is only established by the *conjunction*: the deploy key can
     read it (check 2) **and** an anonymous client cannot.
   - If the anonymous probe cannot run at all (no outbound HTTPS), **refuse**:
     "could not verify the repository is private". Fail-closed, matching
     `netbox_allow_writes`.
5. **Right repository**:
   - not this application's own source repo (compare against `git remote get-url`
     of the NMAS checkout);
   - not already claimed in another list's `remote.json` (owner/repo compare);
   - empty, **or** its history shares a root commit with this list's
     `config_repo`. An unrelated non-empty repo is refused — pushing into it
     would either fail as a non-fast-forward or, worse, succeed and interleave
     two networks' histories.

---

## 6. First-push preview and acknowledgement (item 5)

Shown before the first push to a given remote, counts only, **never values**:

```
This will publish to github.com/dmarchak/rcn-nsot-config (private)

  51 commits          10 touching golden/
  18 tags             2 baseline/, 15 golden/<device>/, 1 batch/
   0 notes            refs/notes/ci is empty

Recoverable secrets in golden/ history, per device:
  r1 r2 r3 r4 r5   plaintext admin password     1 each   <-- acknowledgement required
  all 9 devices    SNMP community               2 each   <-- acknowledgement required
  s1 s2 s3 s4      type-9 secret (salted hash)  1 each   not recoverable

Rotating these AFTER pushing does not unpublish them: history is published too.
```

- Scan **history, not just HEAD** — the push publishes every commit.
- Plaintext passwords and type-7 (reversible) require an explicit typed
  acknowledgement, recorded in `remote.json` as
  `acknowledged_secrets: {at, by, counts}`. Hashed secrets are reported, not
  gated.
- Re-acknowledge if a **new kind** of plaintext material appears later. Same
  rule as `unmodeled_ack`: acknowledgement names what was acknowledged, and a
  new finding invalidates it.

---

## 7. Push, report, enable (item 6)

1. **Push now** — an explicit route, which does not exist today. `git push
   --follow-tags`, then `git push origin 'refs/notes/*'` when any note ref
   exists.
2. **Report** — refs pushed, tags pushed, notes pushed, duration, remote URL.
3. **Enable auto-push** — offered only after a success, writing
   `auto_push: true`.

### The notes fix

Two halves, and the second is easy to forget:

- **push**: `git push origin 'refs/notes/*'` after the main push. Skip silently
  when no note ref exists — today that is always.
- **fetch**: a plain clone gets no notes. Set
  `remote.origin.fetch += +refs/notes/*:refs/notes/*` in the repo config so a
  clone made *by NMAS* round-trips; and document the refspec for a human
  cloning by hand, because nothing NMAS does can fix their clone.

Both are cheap and neither is urgent until `add_ci_note()` acquires a caller —
which is Phase 4/5 business. Worth doing here anyway, because the phase that
starts writing notes will not think about transport.

---

## 8. Error translation

Raw git/SSH output is the worst part of this workflow. Map, don't echo:

| symptom | message |
|---|---|
| `Permission denied (publickey)` | The deploy key is not registered on this repository, or the wrong key is being offered. Public key: `<path>.pub` — add it at `github.com/<o>/<r>/settings/keys` with **Allow write access**. |
| push rejected, read-only key | The deploy key is registered but read-only. Delete it and re-add with **Allow write access** ticked. |
| `Repository not found` | Either the repository does not exist or this key has no access. With a deploy key both look identical — check the name at `github.com/<o>/<r>`, then the key. |
| `Host key verification failed` | GitHub's host keys changed or are missing. Re-run *Refresh GitHub host keys* (fetches `api.github.com/meta`). |
| non-fast-forward / rejected | The remote has commits this repo does not. NMAS never force-pushes. Resolve manually. *(already implemented)* |
| `could not read Username for 'https://…'` | HTTPS remote with no credential. This phase uses SSH deploy keys — reconfigure the remote as `<alias>:<owner>/<repo>`. |
| `403 rate limit` / `401` from the API | Token rejected or exhausted. Nothing was stored; paste a new token or use the guided manual path. |

Rule: every message names **the file, the URL, or the setting to change**.

---

## 9. Tests

The list requested, plus what the findings above make necessary:

| test | asserts |
|---|---|
| public repo refused | anonymous API 200 **or** git endpoint 200 → refuse; both probe shapes covered |
| privacy unverifiable refused | anonymous probe raising → refuse, not "assume private" |
| repo reused across lists refused | same `owner/repo` in another `remote.json` → refuse, naming the other list |
| unrelated history refused | non-empty remote with no shared root commit → refuse |
| empty remote accepted | `ls-remote` rc=0 with no refs is the normal first-setup case |
| account-wide key refused | `ssh -T` → `Hi username!` → refuse; `Hi owner/repo!` → accept |
| read-only key caught | write probe fails → refuse with the read-only message, not a generic failure |
| **write probe publishes nothing** | the objects the probe pushes contain **no blob** — one orphan commit, one empty tree. Guards against reintroducing `HEAD:refs/...`, which would publish all 51 commits and every secret in them |
| write probe leaves no ref | `refs/nmas/writeprobe` absent from the remote afterwards |
| write probe never touches config_repo | the probe runs in a throwaway repo; `config_repo` gains no ref, no remote, no object |
| **token never persisted** | after the automatic path: absent from `user_settings.json`, every `remote.json`, all log output, and the audit trail. Asserted by **value search**, not by key name |
| SSH include file idempotent | run twice → one `Include` line, one stanza per list, unmanaged content byte-identical |
| SSH config never otherwise edited | only the `Include` line may differ from the original; a backup exists |
| hand-written alias preserved | adopting `github-nsot` leaves `~/.ssh/config` unchanged |
| **two lists push only to their own remotes** | commit in list A → hook pushes only A's remote; B's is untouched |
| known_hosts written from meta | keys match published fingerprints; a mismatched key is refused, not written |
| notes pushed when present | note exists → `refs/notes/*` on the remote; none → no spurious push |
| tags still pushed | `baseline/*` and `golden/<device>/*` land (guards the existing `--follow-tags`) |
| secrets preview counts, never values | no secret value appears in the preview payload or the DOM |
| plaintext requires acknowledgement | push refused without it; allowed after; new plaintext kind invalidates it |
| hook reads per-list config | global `nsot_git_remote_url` is not consulted once `remote.json` exists |

All GitHub API and SSH interaction mocked — **no test touches github.com**,
matching the existing "no test touches a live network" rule.

---

## 10. Decisions taken

1. **Phase number** — 2b, completing Phase 2. "Phase 6" is GUI completeness.
2. **Adopt-first increment** — agreed. Ship §1 + adoption + §5 + §7 Push now as
   a self-contained increment; key generation and repo provisioning (§3, §4)
   follow.
3. **Tag divergence kept.** `_prune_device_tags` trims locally; the remote keeps
   everything. The remote is an **archive**, and an archive should not forget.
   Recorded here so it is a decision rather than an accident.
4. **`nsot_git_token` and `nsot_git_auth_mode` are deleted** — a recorded
   exception to the settings rule that old keys are never removed. The rule
   exists so a downgrade does not lose configuration; here the keys are read
   nowhere, and Option A promises the token is never stored, so an
   encrypted-at-rest field for it contradicts the product. `settings_schema.py`
   must carry the exception in a comment naming this document, otherwise the
   next person restores them for consistency with the rule.
5. **GUIDED MANUAL is the default path; AUTOMATIC is secondary.** Because
   deleting the PAT deletes the deploy key: the manual path produces a key with
   no token lifetime attached, which is the more durable artefact. The
   automatic path stays for convenience and says plainly what the token's
   deletion would do.

## 11. Still open

1. **Secrets in existing history.** Not a plan question — it is sequencing
   step 3 above. 18 SNMP communities and 5 plaintext router passwords across 51
   commits. Rotating after a push does not unpublish anything, which is why the
   rotation comes first and goes to *new* values.
