# Concurrency audit: several people, several tabs, several processes

This is the read-only audit for NSOT_PLAN P.15. Nothing in the program was changed. This
file is the only thing the audit wrote. Every finding below was read from the code by one
reader, then checked against the code by a second reader whose job was to refute it.
Nothing was run against the host or a device. Where a race is inferred from the code and
not reproduced, it says so.

**Audited at commit `2e46134`.** Every `path:line` below refers to that commit. The working
tree then also held uncommitted changes to the manual, its renderer (`modules/manual.py`), a
stylesheet and some templates. None of them moves a cited line. The one cited template among
them, `templates/v2/_apply_preview.html`, changed only at lines 1 and 129-130.

A review pass after the audit added nine write paths the first reading missed. Each is
marked **added on review** where it appears, and the reviewer checked it against the code.
Rows that contradicted their own evidence were corrected in the same pass.

## 1. The principle and the method

### The principle

In an enterprise, several people use the tool at once. With roles coming, that is assumed,
not hoped for. Every write path must be safe against three things:

- **another person**, acting on the same device, document or record;
- **another browser tab** of the same person, holding an older view;
- **another worker process**, after Stage 9's gunicorn. A host CLI (`nmas-retire`,
  `nmas-rotate-credential`, `nmas-golden-state`, `nmas-startup-check`, the `nsot_*` repair
  scripts) is already a second process today.

A lock held in memory, a module-level dict, or an in-process job registry protects nothing
across processes. A read-modify-write of a file without a cross-process lock loses updates.
A confirm not bound to what the person previewed applies something nobody read.

The principle is already recorded in two places: CLAUDE.md's bullet beginning "SEVERAL
PEOPLE USE THE TOOL AT ONCE" (in "Things to Keep in Mind"), and NSOT_PLAN P.15
(docs/NSOT_PLAN.md:4377). That bullet already requires a cross-process lock with a visible
owner and start time, a lease and a recorded admin release, and a document saved against
the version its editor opened. This audit did not edit either file. It proposes adding
these sentences to the existing bullet, because the findings below show each one is needed
and none is stated yet:

> Every commit to a list's repository is serialised across processes. Every confirm is
> bound to what was previewed. A store with more than one writer is locked and replaced
> atomically, and an unreadable store refuses a write instead of becoming empty. In-memory
> state that a second process needs (jobs, tokens, reachability, sessions) lives in a shared
> store. Nothing ends the process (a restart, an update, a worker recycle) while an
> operation holds a device.

### The method

Seven areas were read: the list's git repository, intent and other edited documents, file
stores, locks, preview and confirm, approvals, and live state (Socket.IO, readers, jobs).
Each finding names the path, what it writes, its protection today, whether that protection
holds across processes, what a second user sees, and what a collision does.

Outside services, stated so an absence is not read as unexamined:

- **Grafana**: no write path found. The client's one POST goes to `api/ds/query`, which is a
  read (modules/integrations/grafana.py:22-32).
- **Prometheus**: written only through the `file_sd` target files (R37, live-18).
- **Kea**: written only through `modules/nsot/ztp.py`'s fragment and its
  `kea.command("config-reload")` (:553; R22).
- **NetBox**: written by the NetBox tab, onboarding phase two, adopt, retire's mask and
  `scripts/nmas-netbox-mask-context` (R21, widened on review).
- **Oxidized**: written through the root helper that edits `router.db` (R40, added on
  review).

Verdicts:

- **SAFE**: holds for two users, two tabs and two processes.
- **UNSAFE-MULTI-PROCESS**: holds in one process, breaks with a second process. Some of
  these already break today, because a host CLI is a second process.
- **UNSAFE**: breaks with two users or two tabs in today's single process.

| Area | Paths | Not safe | Check: confirmed | Check: corrected | Check: refuted | Added on review |
|---|---|---|---|---|---|---|
| git repository | 20 | 16 | 13 | 7 | 0 | 0 |
| intent and edited documents | 20 | 18 | 19 | 1 | 0 | 0 |
| file stores | 32 | 22 | 25 | 4 | 0 | 3 |
| locks | 24 | 17 | 17 | 5 | 0 | 2 |
| preview and confirm | 32 | 20 | 27 | 2 | 0 | 3 |
| approvals | 20 | 16 | 16 | 4 | 0 | 0 |
| live state | 23 | 20 | 14 | 8 | 0 | 1 |
| **Total** | **171** | **129** | **131** | **31** | **0** | **9** |

The three check columns count the audit's 162 original paths. The nine added on review were
checked by the reviewer against the code: eight are unsafe and one is SAFE (confirms-32).

The areas overlap. One defect was often seen from several sides: the repository lock appears
in five areas. Section 2 consolidates the 129 unsafe paths into 41 ranked findings, each
naming its source ids from the appendix. R38 to R41 were added on review; they sit in the
table at their risk, and the earlier numbers were kept. Corrections are applied throughout.

## 2. Ranked findings

Ordered by risk, then verdict (UNSAFE before UNSAFE-MULTI-PROCESS). "Today" means the
finding affects the current single-process install, with two users, two tabs, or a host CLI
running beside the app. Section 6 lists the findings that reach even one person in one tab.

Risk is h, m or l. Where it differs once several workers run, the column says so ("m today;
h under workers"). A finding that cannot occur today carries the risk it has once its
condition (several workers, a fresh install, the roles stage) arrives.

| # | Risk | Area | Write path | Writes | Protection today | Cross-process | Verdict | Today | Fix |
|---|---|---|---|---|---|---|---|---|---|
| R1 | h | git | Every commit to a list's repository (`save_golden`, `_commit_paths`, renames, migrate); abandon and retire stage outside | index, commits, tags | `threading.Lock` per repo; `stage_exactly` checks once; `commit()` takes the whole index | no | FIXED 2026-10-02 (was UNSAFE; tests/test_repo_lock_across_processes.py) | yes | Cross-process lock held from first write to last tag, holder recorded; commit explicit paths; every stager inside |
| R2 | h | intent | Intent editor save | `host_vars/<dev>.yml`, one commit | none: no base, write before the lock, save not bound to preview | no | FIXED 2026-10-02 (was UNSAFE; tests/test_intent_editor_concurrency.py) | yes | Base blob from the open; compare at HEAD under the lock; 409 with three-way diff |
| R3 | h | stores, live | The server-wide active list (`device_lists.json` `current_list`) | the registry, and which list every derived write lands in | none; truncate in place; a torn read answers "Default" | no | STORE HALF FIXED 2026-10-04 (tests/test_list_registry_store.py); the per-session half UNSAFE, a decision (below) | yes | Active list per session; every write carries its list; locked atomic registry |
| R4 | h | approvals | Approval queue store | `approval_queue.json` | none; GETs write it; unreadable reads as `[]`; `resolve` saves a stale list twice | no | FIXED 2026-10-02 (was UNSAFE; tests/test_approval_queue_store.py) | yes | PathLock, atomic write, refuse unreadable, pure reads, compare-and-set; SQLite WAL candidate |
| R5 | h | locks, live | An operation interrupted by a process exit, including the two restart routes (added on review) | devices already pushed; no receipt, no golden, no rollback | none: Update gates and the restart routes ignore held devices; crash staging unread; leftover lock file unread | n/a | FIXED 2026-10-02 (was UNSAFE; tests/test_interrupted_operations.py, tests/test_pending_receipts.py): Update and `nmas-deploy` refuse while a device is held, both restart routes removed, an interrupted operation kept and drawn on Needs attention, each device's receipt written as it finishes, commit pending; not built: the per-device step under `deploy_max_workers > 1`, and the gunicorn half (9.S) | yes | Refuse Update, restarts and `nmas-deploy` while any device is held (or retire the restart routes); per-device receipts; draw the interrupted state |
| R6 | h (m today) | git, stores, locks | Manifest store | `.nsot/manifest.json` | `threading.Lock`, shared `.tmp`, unreadable becomes empty; rename rollback writes blind | no | FIXED 2026-10-04 (was UNSAFE; tests/test_manifest_store.py) | yes (CLI; rename rollback) | PathLock, `write_atomic`, `read_json_for_write`, inside the repo lock |
| R7 | h under workers | live | Background services start only under `__main__` | readers, drift, keeper, heartbeat, UDP listeners | started once by `__main__` | no | UNSAFE-MULTI-PROCESS | no | One designated service runner with a leader lock; web workers start nothing |
| R8 | h under workers | live | Socket.IO | announcements, heartbeat, terminal | no message queue; polling needs sticky sessions; terminal state per process | no | UNSAFE-MULTI-PROCESS | no | Sticky sessions plus a message queue, or one Socket.IO process |
| R9 | h under workers | live | Reachability `STATUS` | in-memory dict every consumer reads | per process | no | UNSAFE-MULTI-PROCESS | no | Read the stored reader value; absent means unknown |
| R10 | h under workers | live, locks, confirms | Job registries (capture preview, rotate, deploy job, `op_progress`) | in-memory job state and results | `threading.Lock` | no | UNSAFE-MULTI-PROCESS | no | Shared job store; "interrupted" from the recorded pid |
| R11 | m today; h under workers | locks, live | SSH session budget per device | vty lines | per-process count | no | FIXED 2026-10-04 (was UNSAFE; tests/test_ssh_slots_across_processes.py) | yes (host CLIs) | Cross-process session slots |
| R12 | m | approvals, intent, confirms | Template approve | `.approvals.json`, a commit | client sends `{}`; validates, then fingerprints the working tree | no | SERVER HALF FIXED 2026-10-04 (tests/test_approve_one_snapshot.py); the client half (the v1 editor sends what it reviewed) UNSAFE | yes | Approve carries the reviewed fingerprint; fingerprint one snapshot first |
| R13 | m | approvals, stores | `.approvals.json` record | approvals and tombstones | unlocked read-modify-write, shared `.tmp`, `{}` on unreadable; edits' revocations not committed; gate reads the working tree | no | FIXED 2026-10-02 (was UNSAFE; tests/test_approvals_record.py) | yes | PathLock and atomic write; commit tombstones with the template; read at HEAD |
| R14 | m | intent, approvals | Template and bindings editors | templates, `bindings.yml` | no base; truncate in place; bindings fall back to defaults silently | no | SERVER HALF FIXED 2026-10-04 (tests/test_template_store_writes.py); the client half (the v1 editor sends what it reviewed) UNSAFE | yes | Base blob; `write_atomic`; refuse an unreadable bindings file |
| R15 | m | intent, confirms | Hash-confirmed intent writers (bulk, profile propose, IP SLA) | `host_vars`, `profiles/monitoring.yml` | hash checked, then write, then commit, nothing spanning; no device holds | no | UNSAFE | yes | Repo lock across recompute, write and commit; hold devices |
| R16 | m | confirms | Deploy and restore confirm gaps | devices, commit | command hash optional; compared before the hold; list derived | partly | UNSAFE | yes | Require the hash; hold first; list in the hash |
| R17 | m | intent | Settings forms | `user_settings.json`, `.env` | file safe; forms resend every field; `.env` unlocked | yes (file) | UNSAFE | yes | Send changed fields only, with the value as loaded |
| R18 | m | git, stores, locks | `remote.json` and the post-commit push | the remote, `remote.json` | thread per commit; unlocked read-modify-write; unreadable reads as "no remote" | no | UNSAFE | yes | One publisher per repository; PathLock; push an explicit sha |
| R19 | m | stores, live, approvals | Drift state and overlapping drift runs | `drift_state.json`, queue items | one RLock in one function; truncate; legacy re-adoption; Check now overlaps | no | FIXED 2026-10-02 (was UNSAFE; tests/test_drift_state_concurrency.py) | yes | PathLock; refuse unreadable; one drift run at a time across processes |
| R20 | m | approvals | Restore rejects its own handed-off approval item | queue | unconditional | n/a | FIXED 2026-10-02 as C326 (was UNSAFE; tests/test_approved_revert_closes.py) | yes | Never reject the item named by `approval_id` |
| R21 | m | locks, confirms, live | Every NetBox writer: the tab's import and Remove, onboarding phase two, adopt, retire's mask, the mask script (widened on review) | NetBox, sync status | nothing refuses a second writer; status truncate; tokens in memory | partly | UNSAFE | yes | Per-list NetBox lock with holder, taken by every writer; shared token store |
| R22 | m | stores | Kea ZTP fragment | the fragment, Kea's running config | none | no | UNSAFE | yes | PathLock from read to read-back |
| R23 | m | git, confirms | Onboarding Create and Abandon | credential store, manifest, `host_vars`, NetBox, Kea | no hold; Abandon ignores phase two's hold | no | UNSAFE | yes | Hold the hostname; bind Abandon to its dry run |
| R24 | m | git | git's `index.lock` and tags | index, tags | readers take the optional lock; no retry; tag failures dropped; HEAD read apart from the commit | partly | FIXED 2026-10-02 (was UNSAFE; tests/test_repo_lock_across_processes.py) | yes | `GIT_OPTIONAL_LOCKS=0`; sha and tags under the lock; failures reported |
| R25 | m | git | `save_golden`'s compare and retire's undo | golden, `host_vars`, manifest working files | compares the working file; blind undo; retire resets whole trees | no | FIXED 2026-10-02 (was UNSAFE; tests/test_repo_lock_across_processes.py) | yes | Compare HEAD; undo only own writes and exact paths |
| R26 | m | locks, live | Device holds | lock files | exclusion SAFE; no lease, no admin release, key not canonical, probe race | yes | UNSAFE | yes | Lease, recorded release, canonical key, no flock probe |
| R27 | m | live, intent, approvals | Visibility of others' work | n/a | keys only in the caller's response; v2 pages show no live holder | partly | UNSAFE | yes | Broadcast mutations; live holder strip; previews subscribe |
| R28 | m | live | Reader runs overlap | reader stores, `git fetch` | store locked; runs not excluded; last store wins | partly | FIXED 2026-10-02 (was UNSAFE; tests/test_reader_runs_one_at_a_time.py) | yes | One run per reader at a time; never store an older value |
| R38 | m | stores (added on review) | Deleting a device list | the list's whole folder, the registry | NetBox records and credential dependents checked; running holds and jobs not | no | UNSAFE | yes | Refuse while any hold or job exists on the list; a list-level lock that list writers also take |
| R39 | m | locks (added on review) | Break-glass terminal input | devices | none: no device hold, outside the session budget and C101's guard | no | UNSAFE | yes | Hold the device for the shell's life and count it in the budget, or remove the terminal (7.8) |
| R40 | m | stores (added on review) | Persistence-chain host files: Oxidized `router.db` and the lab sync | `router.db`, lab startup files and their repositories | `router.db`: atomic replace, no lock; sync script: no lock | no | UNSAFE | yes | `flock` in the root helper and in the sync script |
| R41 | m | confirms (added on review) | Remote publication acknowledge | `remote.json` acknowledgement | typed kinds checked; values recorded at click time; list derived | no | UNSAFE | yes | Bind the confirm to the values fingerprint the card showed; carry the list |
| R29 | m under workers | live | Reader on-request registry ("Check again") | in-memory request record | per process | no | UNSAFE-MULTI-PROCESS | no | Request record in a shared file |
| R30 | m (fresh install, several processes) | stores | Key file creation | `key.key`, session key | check, then create with truncate | no | UNSAFE-MULTI-PROCESS | no (fresh install) | Exclusive create, or an install step |
| R31 | m (roles stage) | approvals | Four-eyes and the requester | n/a (missing control) | none | n/a | UNSAFE | no (roles stage) | Record the requester; host-side policy |
| R32 | l | stores | Deploy receipts written by two batches | `deploy_receipts.jsonl` | `O_APPEND`, but rows go through one buffered handle | partly | UNSAFE | yes | One unbuffered write per row; keep the strict read |
| R33 | l | stores, intent | Small stores with unlocked read-modify-write | variables, collector config, freshness authorisations, topology layout, agent and AI stores, `source.json`, retire's declaration, integration cards | none or in-process only | no | UNSAFE | yes | PathLock, `write_atomic`, `read_json_for_write` |
| R34 | l | approvals | Queue detail | queue | handoff ids not bound to the device; closures unattributed; freshness authorise derives its list | n/a | UNSAFE | yes | Bind ids to devices; record actor on every transition; carry the list |
| R35 | l | git, confirms | Repository housekeeping and the migration confirm | `index.lock`, `.gitignore`, migration marker | 120 s stale-lock window and its check-then-remove; readers append `.gitignore`; marker read before the lock; migrate's confirm is an unbound boolean | partly | UNSAFE | partly (not the migration on this host) | Clear and top up only under the write lock; re-check the marker inside it; bind the confirm to the dry run |
| R36 | l | confirms | Unbound low-impact confirms | NetBox record, onboarding commit | NetBox forget has no preview; Create not bound to the review | n/a | UNSAFE | yes | Preview and hash both |
| R37 | l | live, stores, locks | Per-process caches and helpers | redaction cache, NetBox inventory cache, sync status, keeper, heartbeat, agent, `op_progress` | in-process | no | UNSAFE-MULTI-PROCESS (some today) | partly | Single runner; caches keyed on file generation |

### High findings

**R1. The list repository is serialised only inside one process** (appendix git-1, git-4,
intent-6, locks-1, locks-2, confirms-8, approvals-17). `repo_lock()` returns a
`threading.Lock` per repository (modules/nsot/repo.py:43-44, 72-76; the docstring at
repo.py:22-23 says "in-process"). No `flock` exists in repo.py. `stage_exactly` checks the
index once (repo.py:236-266), then `save_golden` and `_commit_paths` commit the whole index
(repo.py:1077, 1307; `commit()` adds `-- paths` only when given, repo.py:1268-1270). Writers
stage outside the lock today, in one process: abandon runs `git add` and its commit with no
lock (modules/nsot/onboard.py:1796-1806), and retire runs `git rm` with no lock
(modules/nsot/retire.py:655-660). Host CLIs commit to the same repository from their own
process: `nmas-retire` (retire.py:671), `nmas-rotate-credential`
(credential_rotation.py:1795), `nmas-golden-state` (scripts/nmas-golden-state:145),
`nsot_dedupe_manifest.py` (:118), `nsot_reapprove_templates.py` (:131),
`nsot_fix_description_ifnames.py` (:311). Two outcomes follow. Another writer's staged file
rides into this commit under this person's `Actor:` and `Source:` (C175's defect,
recreated). Or `stage_exactly` refuses, naming the other person's in-flight file and telling
this person to `git reset` it (repo.py:250-258). On a failed commit `_undo_golden_writes`
puts back the old bytes (repo.py:1078-1081, 1192-1207) while HEAD may already hold the new
content under someone else's name. The only two-writer test uses threads
(tests/test_golden_repo.py:260-280). Correction applied: `nmas-inventory-role` does not
commit. Under one process, two browser users are serialised; the exposure today is a host CLI
or the unlocked abandon and retire stagers.

*FIXED 2026-10-02 (tests/test_intent_editor_concurrency.py):* the GET hands out the blob at
HEAD as `base`, with the text read from that blob; the save sends it back and, under the
repository lock, a moved HEAD is refused (409) naming both blobs and who moved it, with both
changes against what was opened and nothing written. The save runs the preview's checks
(`_validate_edit`), writes inside the lock, and an unchanged save says nothing was committed.
The text below is the finding as audited.

**R2. Two people editing the same intent: the last writer wins, silently** (intent-1,
intent-2, intent-3, git-8, stores-3, confirms-1). The editor's GET returns only the text
(routes/templatize.py:261-274). The save sends `{yaml, summary}`
(static/js/gen/partials__intent_editor.1.js:172-176). The server checks only that intent
exists at HEAD (routes/templatize.py:499), writes the file with a truncate in place
(modules/nsot/hostvars.py:576-579), and only then commits under `repo_lock`
(repo.py:1292). A person who opened r2 before another person's commit replaces that commit's
change with their own whole document, and both see success. Because the write is outside the
lock, A's commit can carry B's text under A's summary and actor, while B's commit finds
nothing to commit and still reports `ok: true, commit: ""` (repo.py:1300-1303), drawn as
"Committed ." (intent_editor.1.js:183-185). The save is not bound to the preview: the
unknown-interface-key refusal runs only in the preview route (routes/templatize.py:350-366),
not in `write_committed_text` (hostvars.py:557-575). One concrete loss: a stale editor save
after a rotation puts back the old `secret_kind` and `secret_ref`, naming a secret the store
no longer holds (modules/nsot/credential_rotation.py:1761-1780). There is no device hold.

**R3. One person's list switch retargets everybody** (stores-2, intent-4, live-13,
confirms-7, approvals-3, locks-7). `current_list` is one value in `data/device_lists.json`.
`set_current_device_list` rewrites it for every session (modules/device.py:514-522), with a
truncate in place (device.py:481-484) and no lock. `get_current_list_name()` maps any
exception, a torn read included, to "Default" (modules/config.py:163-169). Writes that derive
their list from it: the intent editor and template routes (routes/templatize.py:27-30,
routes/templates.py:28-31), the deploy and restore previews and applies when the client
sends no list (routes/deploy.py:31-34; static/js/gen/partials__golden_repo.3.js:209-214,
278-283; static/js/nmas_capture.js:207-212), the approval queue (approval_queue.py:28-36),
`/reorder` (app.py:1050-1061), the collector config (collector_config.py:25-27), variables
(ai_assistant.py:866-868), and `device_ops.hold_device` (device_ops.py:374-384). A template
save while another person switches lists always lands in the other list. An intent save
lands there when that list holds the same hostname. Content hashes stop most wrong-list
deploys, but intent, templates and approvals carry no hash.

*The store half, FIXED 2026-10-04 (tests/test_list_registry_store.py):* every registry
mutation (switch, create, delete, rename) holds a cross-process `PathLock` on
`device_lists.json` from its read to its write, and the file is replaced atomically, so a read
never sees a torn file and no mutation erases another. Shown with real processes: a reader
beside a switching process saw only the two real lists, where truncating in place made it see
"Default" three runs of three; three processes creating lists lost none, where no lock lost
some three runs of three.

*The per-session half is a DECISION (the operator's), recorded 2026-10-04.* One person's switch
still retargets every other session's derived writes. Options:
(A) **the active list per session**: the server-wide `current_list` becomes the default a new
session starts from; a switch changes the session's own; `get_current_list_name()` answers
the session's in a request and the default outside one. No v1 control changes and no v1
JavaScript; the derived writes follow the person who made them.
(B) **every write carries its list** (CLAUDE.md's rule, already true on v2 and in four modules):
the remaining v1 routes refuse a write without its list, and their JavaScript sends it. Churn on
pages that retire at cutover.
(C) **leave it until cutover**: v2 carries its list; v1 retires.
**Recommendation: (A)**, now. It removes the cross-person retargeting on today's pages without
touching v1 controls, and (B) then follows naturally as v2 replaces them.

**R4. The approval queue store loses and erases decisions** (approvals-1, approvals-2,
stores-1, live-12, confirms-22). `_save_queue` truncates in place with no lock
(modules/approval_queue.py:47-51). `_load_queue` returns `[]` when the file is unreadable
(approval_queue.py:39-44). Reads write: `get_pending()` and `get_all()` save on every call
(approval_queue.py:166-177), and the main page polls `GET /ai/approvals` on load and every
30 s from every tab (static/js/gen/index.4.js:152-162), which saves twice (app.py:3721,
3727). A torn read followed by that save erases the queue. `resolve()` loads, sets the
status, saves, runs `_execute`, then saves the same stale list again (approval_queue.py:205,
222, 236), overwriting whatever the drift run added in between. The drift run itself writes
from up to six threads at once (modules/drift_check.py:383, 370-374, 388-396). The decision
record (who approved, rejected or withdrew, and why) is not in git, so a lost update loses
it for good. `read_pending()` (approval_queue.py:141-163) is the one non-writing reader and
only Needs attention uses it.

*FIXED 2026-10-02 (tests/test_interrupted_operations.py).* Built:
`device_ops.held_anywhere()` reads every hold in every list by any process; the Update
preview has a gate, "no operation is running on a device", naming each holder, and a waiting
update keeps waiting while one runs; `GET /health/operations` lists the holds (never who), and
`nmas-deploy` asks it before it moves anything and refuses with exit 10 (a service that cannot
say does not stop a deploy: a deploy is how it is repaired); `/server/restart` and
`/ai/restart` are removed. An operation whose process ended is no longer silent: a non-empty
lock file nobody holds is listed by `device_ops.interrupted()`, kept in the list's
`interrupted.jsonl` when the next operation takes the device, and drawn on Needs attention
(one row per interrupted process, its devices and last step, acknowledged per event).
*Per-device receipts, FIXED 2026-10-02 (the operator's decision; tests/test_pending_receipts.py).*
Both apply paths (`apply_batch`, `run_targets`) write each device's receipt row the moment the
device finishes, `commit_state: pending`, with its outcome, program and checks
(`routes/deploy.py` `_pending_receipts`); after the batch's golden commit `_write_receipts`
appends one completion line per such row (`completes: <id>`, the commit or `no_golden`) and a
whole row for a device refused before it started, every row carrying the run's id. The file
stays append-only and `receipts.read()` merges each completion into its row. Every reader
draws a pending row as PENDING, never done or green: the result component
(`result_level` is partial, the target's words "sent; commit PENDING", a `commit_pending`
item), the device page's History (a warning badge), the landing's recent changes, the
in-flight panel and the running apply's stepper. Needs attention: a pending receipt whose
device is held (its batch is running) or whose process ended (the interrupted-operation row
names it, with the devices that finished and the one whose state is unknown) is no second row;
one named by neither (its completion could not be written) is a deploy row of its own.
**Not built:** the per-device progress step. With the default sequential batch the batch's last
step is the step of the one device in progress, and every device before it now has its
receipt; under `deploy_max_workers > 1` the step does not say which device it belongs to. The
gunicorn half (graceful restart and worker recycling) stays with 9.S, as section 6 says.

**R5. An operation interrupted by a process exit leaves a half-applied batch nobody is told
about** (locks-15, live-9, live-23). Receipts and the golden commit are written only after the whole
batch (routes/deploy.py:684-689, 905-913). Post-deploy captures are staged per device
(repo.py:467-483, called at pipeline.py:1973), but nothing reads them: `staged_post_deploy()`
and `staged_restored_intent()` have no caller (repo.py:486, 1488). The Update preview's
gates check pending requests, the updater, the update lock and the wait record, never held
devices (update_op.py:548-575). `release_deferred` requests an update on its own when CI
passes (update_op.py:813-830, run from readers/app_pushed.py:222). When the process exits,
the kernel releases every hold, and `holder()` reads a free `flock` as "no holder" whatever
the file says (device_ops.py:236-262). Nothing reads a non-empty, unlocked lock file. So the
devices already pushed carry no receipt, no golden and no rollback, and the next person may
start a new operation on a half-configured device at once. Rotation and adopt staging is
the exception: job health surfaces a staged credential (modules/job_health.py:795-816).
Gunicorn's graceful restarts and worker recycling add new ways to reach this.

*Added on review: two routes end the process outright.* `POST /server/restart` calls
`_os._exit(3)` one second after answering (app.py:3313-3322). `POST /ai/restart` calls
`os.execv(...)` two seconds after answering (app.py:3171-3179). Neither checks
`device_ops`, a running job or a commit in progress. Both are gated only by kind K
(modules/route_gates.py:140-141). So one person can end another person's deploy in the
middle of a batch, with the outcome above. An exit during a `git commit` can also leave
`.git/index.lock` behind, which makes every commit in that repository fail for up to 120 s
(R35). No rendered page calls either route (a grep of `static/js` and `templates` finds
neither path), so reaching them takes a direct POST from a verified person. The fix: refuse
both while any device is held or any job runs, naming the holders, or retire both routes.
The same refusal belongs in the Update preview's gates and in `nmas-deploy`.

**R6. The manifest store is in-process and erases on an unreadable read** (git-7, stores-8,
locks-3). Every writer holds a per-repo `threading.Lock` (modules/nsot/manifest.py:46-55).
`save()` writes a shared `path + ".tmp"` then `os.replace` (manifest.py:90-96). `load()`
returns an empty manifest when the file is unreadable (manifest.py:75-87), so the next save
writes a one-device identity map, which the next golden commit stages (repo.py:915). Two
processes share the `.tmp` and can install a mixed file. In one process today, a failed
rename commit writes the pre-rename bytes back under `repo_lock` but not the manifest lock
(repo.py:423, 442), erasing a concurrent `sync_platforms` or `mark_verified`. Host writers
today: `nsot_dedupe_manifest.py:114` and `nmas-retire` (retire.py:662). Onboarding's commit
does not stage the manifest (onboard.py:1440, repo.py:1402-1406), so a pending device's
identity lives only in the working tree until the next golden save.

*FIXED 2026-10-04 (tests/test_manifest_store.py):* every manifest writer holds the
repository's own lock (`repo.RepoLock`, cross-process, re-entrant per thread, so a writer inside
a commit path does not wait on itself, and a rename's rollback can no longer interleave with
`sync_platforms`); `save()` replaces the file atomically with its temp file beside the
repository; a writer refuses an unreadable manifest (`filestore.StoreUnreadable`), its bytes
preserved beside the repository, never inside it; `scripts/nsot_dedupe_manifest.py --apply`
re-reads under the lock and removes only its planned entries. Shown with real processes: three
writing at once lost nothing, where a per-process lock lost entries three runs of three.
Readers keep `load()` (absent and unreadable both read as empty, logged); onboarding's
uncommitted identity is unchanged by this.

**R7. Under gunicorn, the background services do not start at all, or start once per
worker** (live-2, locks-18). `_start_background_daemons()` runs only under
`if __name__ == "__main__"` (app.py:4155-4166, 4243-4245). Gunicorn imports `app`, so as
shipped no worker starts any service: no reachability probe, no reader, no drift scheduler,
no heartbeat, no keeper, no trap or NetFlow listener. Every device then reads offline (R9),
every stored value goes stale, and every page marks itself "not updating" after 75 s
(modules/invalidation.py:330-356). If a per-worker hook starts them instead, every service
runs N times, and the trap and NetFlow binds fail in all but one worker, logged inside the
listener thread (modules/snmp_collector.py:344-348; modules/netflow_collector.py:162-166).
This breaks at 9.S phase 2, which runs one gunicorn worker, not only at several workers.

**R8. Socket.IO has no message queue and no sticky sessions** (live-1). `SocketIO(app,
async_mode="threading", ...)` has no `message_queue` (app.py:140-142). A grep for
`message_queue`, `eventlet`, `gevent` and `gunicorn` over the program, scripts and deploy
finds nothing relevant. The client opens with `root.io()` and default transports
(static/js/nmas_invalidation.js:330): long-polling first. Without sticky sessions, polling
requests land on a worker that never issued the session id and the connection fails. That
also breaks the break-glass terminal, whose state lives in per-process dicts (app.py:467,
485). With sticky sessions but no queue, an announcement reaches only the clients of the
worker that made it. Flask-SocketIO's message queue needs a broker service such as Redis.
Neither Redis nor a client library for one is in `requirements.lock` or `requirements.txt`,
and a broker is one more service to install on an air-gapped host. So the cheaper answer
may be the other one: a single Socket.IO-serving process that the other workers publish to.

**R9. Reachability lives in each process's memory** (live-3). `STATUS` is a module dict
updated in place by the reader (modules/readers/reachability.py:48-49, 164-168), imported
as `device_status_cache` (app.py:97). Consumers default an absent entry to offline:
`device_status_cache.get(ip, False)` (app.py:1036, 1479, 2044, 2125, and also 619, 1469,
2918, 3882). In a worker without the reader, every device reads offline, Refresh Hostnames
skips every device, and topology collects nothing, while the reader's stored file says they
answer.

**R10. Job state lives in each process's memory** (live-5, locks-11, confirms-16,
confirms-27). `capture_job._jobs` (modules/nsot/capture_job.py:31-33), `deploy_job._progress`
(modules/deploy_job.py:39-40) and `op_progress._ops` (modules/op_progress.py:24-25) are
module dicts. Rotation runs through `capture_job` (modules/nsot/rotate_op.py:100-106). A GET
that lands on another worker answers that the job finished more than 30 minutes ago or the
server restarted (routes/golden.py:520-527; routes/rotate.py:96-103; routes/v2.py:652-653),
while the job is running. The person loses the preview they were about to confirm, or the
progress of a batch changing devices. Device holds still refuse a second run.

**R11. The SSH session budget counts one process** (locks-9, live-10). `_sessions` is a
per-process dict under a `threading.Lock` (modules/connection.py:268-271), and the code
says so (connection.py:251). Host processes already open their own sessions today:
`nmas-startup-check` reads every device at once through `fanout.read_each`
(modules/nsot/startup_check.py:65-70), as do `nmas-golden-state` and `nmas-capture-output`.
Together with the app's drift, captures and pools, they can take every vty line, including
the one kept for a person. With N workers the overshoot is N times. Risk is medium today
and high under workers. It is listed with the high findings for the second reason, and
section 6 places its fix with today's work because host CLIs already exceed the budget.

*FIXED 2026-10-04 (tests/test_ssh_slots_across_processes.py):* every session `open_ssh` opens
takes a slot, a `flock` on `<store>/ssh_slots/<ip>/<n>.lock` (n below the budget), holding the
owner and pid. A process holding the whole budget refuses another's session, naming each holder
and its pid; a close frees its slot for another process; a holder that dies frees its slots
(the kernel releases the lock); a slot this process holds for a session it no longer counts is
released before the next is taken. Shown with a real child process: without the lock the
parent opened past the child's budget; without the close freeing, the child could not take the
slots the parent had closed.

### Medium findings

**R12. A template approval can approve content nobody reviewed** (approvals-11, intent-8,
confirms-2, git-9). The client sends `{}` (static/js/gen/partials__template_editor.1.js:211-215).
`approve()` validates first, rendering each bound device from disk, then fingerprints the
closure from disk afterwards (modules/nsot/approval.py:309-323, 108-119). An edit saved in
that window yields an approval whose fingerprint is the edited closure, which no validation
ran against, and the edit's revocation tombstone is overwritten by the later save. Correction
applied: the edit-versus-approve race is not safe by design, and risk is medium, not high,
because the deploy plan still renders the actual template and a person confirms the program
by hash.

*The server half, FIXED 2026-10-04 (tests/test_approve_one_snapshot.py):* `approve()`
fingerprints the closure BEFORE validating and again under the record's lock just before
saving; if it moved, nothing is approved, the refusal names both fingerprints, and the edit's
revocation stands. Shown with an edit landing during the real validation: without the check
the edited closure was approved and the revocation erased. *The client half* (the editor sends
the fingerprint it reviewed) is the v1 template editor's JavaScript, recorded, not built.

*FIXED 2026-10-02 (tests/test_approvals_record.py):* every approve and revoke is a locked
read-modify-write (`<repo>.approvals.lock`, beside the repository) with a temp file per write;
an unreadable record refuses both, keeping the file and a `.corrupt-` copy; a template edit
commits its revocations with the template; the approve and revoke routes report a failed
commit. "Read at HEAD" is built as fail-closed both ways: the gate counts an approval only
when it is committed AND the working record still holds it, so an uncommitted approval is
not one and an uncommitted revocation already refuses. Found while building it: a damaged
record's preserved copy lands inside the repository, where seeding stages untracked files
(register C345, fixed the same day: both now go beside the repository, and seeding stages only what it provides).

**R13. The approvals record loses tombstones and can reopen the gate** (approvals-10,
approvals-12, intent-9, stores-7). `_load` returns `{}` on an unreadable file
(approval.py:153-162). `_save` writes a shared `path + ".tmp"` (approval.py:165-171). Approve
and revoke are unlocked load-modify-save (approval.py:325-329, 373-387). If one person
revokes template X by hand (content unchanged) while another approves Y, Y's stale copy
still holds X's approval, and because X's fingerprint still matches, `is_approved` passes and
the deploy gate reopens for a template a person withdrew. A host script writes this file
today too (scripts/nsot_reapprove_templates.py:58, 110, 131). Separately, every template
edit's revocations are left uncommitted: `write_template` writes tombstones
(routes/templates.py:301-309), then `save_templates` stages only the template
(repo.py:1340-1342). `is_approved` reads the working file (approval.py:181), and the approve
and revoke routes ignore the commit's result (routes/templates.py:508-511, 338-342).

**R14. Template and bindings edits overwrite each other** (intent-7, intent-10,
approvals-13, stores-18, confirms-3). The template GET returns the working file with no base
(routes/templates.py:265-274; templates_repo.py:136-141). The save writes with a truncate in
place and no lock (templates_repo.py:144-157). A render mid-write reads a truncated file.
`save_bindings` replaces the whole document (templates_repo.py:204-213), and `load_bindings`
returns the defaults on any error (templates_repo.py:188-201), so a read during a write
renders a device through the wrong template, silently.

*The server half, FIXED 2026-10-04 (tests/test_template_store_writes.py):* a template save and
a bindings save replace their file atomically (the temp file beside the repository), so a
reader beside 60 saves saw only whole templates, where truncating in place showed it a part;
an unreadable `bindings.yml` raises `BindingsUnreadable`, so no template is chosen by guess
for any device, and the template listing answers 409 naming it. *The client half* (the
editor's GET returns a base blob and its save is refused when the file moved since, with the
three-way diff, as R2 built for intent) is the v1 template editor's JavaScript, recorded, not
built: no new v1 capability while v2's template screen is drawn.

**R15. Intent writers that check a hash do not hold it to the commit** (git-10, intent-5,
intent-11, intent-12, intent-13, confirms-9, confirms-10). Bulk intent recomputes its plan
and compares (modules/nsot/bulk_intent.py:308-320), checks for a dirty `host_vars/`
(:328-333), writes (:336-338) and commits (:345), with no lock across them and no device
holds. An editor commit landing in that window passes the dirty check and is overwritten.
Profile propose (modules/nsot/profile_propose.py:598-640) and IP SLA
(modules/nsot/ip_sla_policy.py:332-363, 407-460) have the same shape;
`profile.commit_profile` restores the previous working file on failure, over any other
writer's bytes (modules/nsot/profile.py:395-409). Revert and seed hold the device
(intent_ops.py:167; seed.py:177), but that excludes only other holders. The editor, bulk,
IP SLA and profile writers never take a hold.

**R16. Deploy and restore confirms have three gaps** (confirms-5, confirms-6, confirms-7).
The binding itself is SAFE across processes (routes/deploy.py:575-646;
modules/nsot/deploy.py:1388-1393, 1590-1591). But the command hash is optional: with none,
only the capture hash is compared, so an intent or template change between plan and apply
is pushed unseen (routes/deploy.py:575-576, 648; run_targets the same). The shipped clients
send it, so the gap is latent, the bypass-by-omission shape. The compare runs before the
device hold (routes/deploy.py:561-660, then 666; run_targets 853-889, then 895). And the
list is derived when the client sends none (see R3).

**R17. A stale settings tab reverts another person's decision** (intent-14, intent-15,
intent-16). The file is safe (settings_lock, modules/config.py:283-336). But the Settings
form sends every field as loaded, including `netbox_allow_writes` and
`background_agent_enabled` (templates/index.html:2522-2541; app.py:1384-1432). A tab opened
before another person turned NetBox writes off can turn them back on when it saves an
unrelated field. Integration cards write one key at a time, validated outside the lock
(routes/settings_integrations.py:50-57; modules/integrations/base.py:84-89). Retire's
`clab_declared_unmapped` is read outside the lock (retire.py:644-650). The `.env` write is
an unlocked truncate (app.py:1333-1356).

**R18. Publication records and pushes race** (git-13, git-14, stores-5, locks-20). Each
commit starts its own hook thread (modules/nsot/hooks.py:104-140). `record_push` and its
siblings are unlocked read-modify-writes of `remote.json` (modules/nsot/remote.py:893-931,
943-990), through a shared `f"{path}.tmp"` (remote.py:75-84). A failure recording
`pending_tags` and a concurrent success that pops them loses a tag the C223 rule says is
kept. An unreadable `remote.json` reads as "no remote" (remote.py:62-72), and the push hook
then answers "no remote configured, nothing pushed" with `ok` (modules/nsot/archive.py:89-95):
publication stops with a success message. Two pushes of HEAD can arrive out of order and
be recorded as a divergence (archive.py:134-140). The S3 hook uploads the working file under
the hook's sha (archive.py:226-236).

*FIXED 2026-10-02 (tests/test_drift_state_concurrency.py):* every read-modify-write of a
list's state holds a cross-process `PathLock` and replaces the file atomically; only an
ABSENT state adopts the legacy file, and an unreadable one is never empty: writes refuse
(the file kept, a `.corrupt-` copy beside it), the scheduler reads it as paused and the panel
says "State unreadable" with why. One drift run per list at a time across processes
(`DATA_DIR/drift_runs/<list>.lock`): a second run raises `DriftRunning` naming the first,
Check now answers 409 naming it, the scheduled run retries in a minute, and the status shows
another process's run as running. A run whose result cannot be recorded says so, never in
the success colour. The queue's own check-then-append was R4's, fixed before.

**R19. Drift state is unlocked, and two drift runs can overlap** (stores-4, live-11,
approvals-20, locks-18). Only `answer_by_golden` takes the RLock
(modules/drift_check.py:48, 218). `_save_state` is an unlocked merge (:137-149), and
`_write_state` truncates in place (:152-157). A torn read makes `_load_state` adopt the
legacy installation-wide file and write it over the list's state (:108-134), which can
drop `disabled`. `POST /drift/check/sync` never sets `_running` (app.py:3208-3216; the
scheduler sets it only for itself, drift_check.py:607-613), so two people pressing Check now
run two full passes, and the queue's check-then-append dedupe
(approval_queue.py:103-136) can add two items for one device.

*FIXED 2026-10-02 as register C326 (tests/test_approved_revert_closes.py), before this row was
marked: the restore no longer rejects pending revert items, and an approved one closes as done.*

**R20. A restore rejects the very approval item it was handed** (approvals-4).
`restore_apply` calls `invalidate_queued_restores()` first (routes/golden.py:905), which
rejects every pending `revert_to_golden` item, with no actor, on the active list
(modules/nsot/restore.py:415-424). Approving such an item returns it to pending
(approval_queue.py:216-222), so it is among them. `mark_done(approval_id)` then fails
"already rejected" (approval_queue.py:262-263). With two people, B's unrelated restore
rejects A's item while A reviews its preview. The tests stub both calls
(tests/test_golden_restore.py:719, 767). Such items are creatable by the agent's
`request_approval` tool (modules/ai_assistant.py:2369, 3758-3775). Not in the register.

**R21. Two NetBox imports can run at once** (locks-21, locks-24, confirms-20, confirms-19, live-15).
The confirm starts a thread after its own token check (routes/netbox_safety.py:205-245).
`set_sync_running` is a spinner flag nothing reads before starting
(modules/netbox_client.py:3716-3726), and it truncates the status file in place, while other
writers use a shared `.tmp` (:3605-3609, 3681-3685), all under an in-process lock (:44). Two
people each with a valid preview can import the same list at once, racing get-then-create
in NetBox. Under several workers, tokens live in a module dict
(modules/netbox_authz.py:35-36), so a confirm reaching another worker is refused as a token
"this server never issued" (:162-164). That fails closed: medium, not high.

*Widened on review: the tab is not the only NetBox writer.* Onboarding phase two writes
through `sync_list_to_netbox` (modules/nsot/onboard.py:1325). Adopt imports the same way
(modules/nsot/adopt.py:666-668). Retire masks the stored context first
(modules/nsot/retire.py:207-214). `scripts/nmas-netbox-mask-context` writes from the host.
None of them takes a per-list NetBox lock, so any of them can race an import on the same
list's shared objects (site, region, VRF): get-then-create, inferred from the code, not
reproduced. The fix is the same lock, taken by every writer, not only by the tab's routes.

**R22. Two ZTP onboardings can lose a Kea reservation** (stores-6).
`write_reservations` reads the fragment, builds a candidate, tests, replaces, reloads and
reads back, with no lock (modules/nsot/ztp.py:463-585). The later replace drops the earlier
device's reservation. If the earlier run's read-back came first, it reported success and its
device later gets no address. A failed reload restores `previous_text` over another writer's
fragment. Onboarding holds only its own hostname (onboard.py:2888-2894).

**R23. Onboarding Create and Abandon are not serialised** (git-12, confirms-11,
confirms-12). Create rebuilds the plan and runs with no lock between the name check and the
mint (routes/onboard.py:526-536; onboard.py:623, 1431-1447). Two Creates for one name can
leave two identities. Abandon takes neither the repo lock nor a device hold
(onboard.py:1783-1812), and refuses only when `verified_at` is set (:1729-1735), which phase
two sets last. So an Abandon during phase two removes the manifest entry, the staged
credential, NetBox objects and the reservation under a running onboarding. Double Create is
plausible, not reproduced.

**R24. git's own locks surface as raw failures** (git-2, git-5). `git()` runs once with no
retry (repo.py:164-181). `_git_env` does not set `GIT_OPTIONAL_LOCKS=0` (repo.py:105-118), so
GET handlers running `git status` outside the lock (routes/v2.py:185;
modules/config_git.py:245-246; routes/templates.py:167) can hold `index.lock` while a save
needs it. The save fails with git's "File exists" text. `commit()` reads HEAD in a separate
call after committing (repo.py:1270-1273), and `save_golden` tags it (:1083, 1093-1111).
Abandon commits without the lock (onboard.py:1802-1806), so in one process `save_golden` can
tag and publish abandon's commit. `_unique_tag` is check-then-create (repo.py:1210-1215), and
a failed baseline tag is dropped while the commit already says `Baseline: earned`
(:1110-1111).

**R25. `save_golden` compares the working file, and retire's undo resets whole trees**
(git-6, git-11). `_content_changed` reads the working file, not HEAD (repo.py:363-370, 844).
Goldens are written with a truncate in place (:905-908). `_undo_golden_writes` restores
blindly (:1192-1207). Two processes saving one device can each report "unchanged" for a
capture that is committed nowhere. Retire's failure path runs `git reset` and `git checkout`
on all of `host_vars`, `golden` and the manifest, outside any lock (retire.py:682-684): it
discards every person's uncommitted change there and erases a pending device's identity.

**R26. Device holds exclude correctly, and have no lease and no release** (locks-5,
locks-6, locks-7, live-8). Exclusion is SAFE: an exclusive non-blocking `flock` per device,
released by the kernel on process death (device_ops.py:270-311). What is missing: a lease.
A suspended CLI or a deadlocked thread holds a device until its whole process ends, and
`describe()` says "There is no force" (device_ops.py:125-127). There is no admin release,
recorded or otherwise; `release()` returns unless the caller is the holder
(:318-320). The key is the lowercased list name with `-` and `.` kept
(device_ops.py:218-226), while list slugs collapse those to `_` (config.py:137-139), so a CLI
given the slug and the app given the display name take two locks for one device. The
holder probe takes a shared `flock` (device_ops.py:244-265), which can make a real acquire
fail and read the truncated file as operation "?" by "unknown", held for decades
(:229-238, 327). The in-flight panel polls that probe every 5 s, and 1.5 s during an apply
(static/js/nmas_in_flight.js:91-96).

**R27. Nobody is told what another person is doing** (live-4, live-14, intent-20,
approvals-18, locks-13). Invalidation keys go only in the mutating request's own response
(modules/invalidation.py:383-420). `announce()` is the only broadcast, used by readers and
three jobs (reader_job.py:321; capture_job.py:100; deploy_job.py:77). No route broadcasts
`intent` or `inventory`. The intent and template editors subscribe to nothing. The v2 device
page reads no hold: `nmas_in_flight.js` is loaded only by templates/base.html:27. The v2
apply preview names a holder once, at preview time (templates/v2/_apply_preview.html:62,
filled at routes/deploy.py:496-497), and redraws only on the person's own changes
(:21-22). The approvals list does learn within 30 s, because it polls. Template approvals
and freshness authorisations have no announcement and no poll.

*FIXED 2026-10-02 (tests/test_reader_runs_one_at_a_time.py):* `run_once` holds a per-reader
run lock across processes (`<store>.run`, a `PathLock`), so a run that starts while another
reads waits and reads after it stored; inside the store, a value whose read began after this
run's is never replaced by this run's older one (`last_good.read_started`), and the attempt is
still recorded. A run on request can now wait behind a scheduled run of the same reader before
its own read; its page's answer bound already allows 2.5x the slowest run.

**R28. Reader runs overlap in one process** (live-6). The scheduled loop
(modules/reader_job.py:509-517), `request_run` (:572-597) and the post-commit refresh
(modules/readers/remote_publication.py:288-292) can all run `run_once` for one reader at
once. The read happens before the lock (:356-363), and inside it `last_good` is replaced
with no check of when the read started (:365-404). A slower run that started first stores
last and overwrites a fresher value. Two `app-pushed` runs can `git fetch` one checkout at
once (modules/readers/app_pushed.py:163). The store file itself stays whole. Correction
applied: this is today, not only under workers.

**R29. "Check again" is in-process** (live-7). `_REQUESTS` is a module dict
(reader_job.py:553-554). On a worker without reader threads, Check again and `/jobs/finished`
answer 409 (routes/update.py:100-103; routes/jobs.py:53-56), and a busy button redrawn by
another worker reads idle (routes/v2.py:104).

**R30. Two processes starting on a fresh install can split the Fernet key** (stores-14).
`load_key` and `_get_fernet` check for the file, then create it with `O_TRUNC`, not
`O_EXCL` (modules/device.py:49-57; modules/secrets_store.py:72-85), and cache it. One process
can encrypt with a key no longer on disk: unrecoverable. The session key has the same shape
(app.py:120-131). Fresh install only.

**R31. No four-eyes rule exists, and nothing records a requester** (approvals-9). Template
edit and template approve are both gate kind A (modules/route_gates.py:103-106). The
approval record holds only the approver (approval.py:322-325). Queue items record no
requester (approval_queue.py:117-134). The design is written (NSOT_AUTHORIZATION.md
sections 5 and 6) and unbuilt. Not a race; a missing control for the roles stage.

**R38. Deleting a list removes it under running operations** (stores-30, added on review).
`delete_device_list` runs `shutil.rmtree(list_dir)` (modules/device.py:566-605). The route
checks NetBox records and credential dependents (app.py:1109-1173), never `device_ops` holds
or running jobs. A second person's deploy, restore, capture or commit on that list then
writes into a repository and stores that no longer exist, or half exist while the tree is
being removed. The fix: refuse while any hold or job exists on the list, naming them, and
take a list-level lock that every list writer also takes.

**R39. The break-glass terminal writes to devices with no hold** (locks-23, added on
review). `socket_terminal_input` sends each keystroke with `sess["chan"].sendall(raw)`
(app.py:572) on a raw paramiko shell (modules/terminal.py:86, `invoke_shell()`). Neither
`socket_connect_terminal` nor `socket_terminal_input` (app.py:532-575) calls `device_ops`.
C101's write guard covers only sessions opened through `connection.open_ssh`
(modules/connection.py:432-478), and the session budget counts only those (R11). So a person
typing configuration can interleave with another person's deploy or rotation of the same
device, and the shell takes a vty line nothing counts. Stage 7.8 removes the terminal. Until
it does, hold the device for the life of the shell and count it in the budget.

**R40. The persistence chain's host files have no lock** (stores-31, stores-32, added on
review). A rotation's persist stage `oxidized_row` (modules/nsot/credential_rotation.py,
around :2894) calls `update_oxidized_row` (:1816-1830), which runs the root helper
`scripts/nmas-oxidized-cred`. The helper reads the whole of `router.db`, replaces one row,
validates against what it read, and `os.replace`s a temporary file (:156-210). It takes no
`flock`. Two rotations of different devices each hold only their own device, so both can
rewrite the file at once, and the later replace puts the other device's row back to its old
password: Oxidized then fails to log in to that device. Two rotation jobs in the app, or the app and
`nmas-rotate-credential`, reach this today. The same chain's `clab_sync` stage (around
:2941) runs the configured `clab_sync_script` (:2339). `scripts/oxidized-to-config.sh` has
no `flock` either, so two persists, or a persist and the clab-sync timer, run two fleet-wide
syncs that copy into and commit to the lab repositories at once. The fix: an `flock` in the
helper and in the sync script.

**R41. The remote publication acknowledgement records values nobody was shown** (confirms-30,
added on review). `POST /remote/acknowledge` checks only that the typed text names the gated
KINDS (routes/remote.py:124-161). `remote.acknowledge` then records whatever values the scan
finds at click time, `"values": gated["values"]` (modules/nsot/remote.py:780-822). The
publication gate's unit is the value (C280: each live secret by a salted fingerprint). A new
secret value of a kind already named, committed between the card being drawn and the click,
is acknowledged without anyone seeing it: the same shape as R12. The list falls back to the
active list (routes/remote.py:22-29, R3). The fix: the card returns the fingerprint of the
values it drew, the confirm carries it and the list, and the route refuses when the scan's
values moved, naming the new ones.

### Low findings

**R32. Two batches' receipts can tear each other's lines** (stores-27). `receipts.write`
opens the file `O_APPEND` (modules/config.py:97) and writes every row of a batch through one
buffered text handle (modules/nsot/receipts.py:204-207). Python's buffer flushes in chunks
that can split a line, so two batches on different devices, which `device_ops` allows at
once, can interleave partial lines. `read` treats any line that fails to parse as the whole
file being unreadable (receipts.py:228-233), so one torn line hides every receipt from the
History tab and the authorisation aggregates. The read's strictness is deliberate, and
right. The fix is on the writer: one unbuffered write per row.

**R33. Small stores with an unlocked read-modify-write** (stores-9, stores-10, stores-11,
stores-13, stores-16, stores-17, intent-15, intent-16, confirms-23, approvals-14). Variables:
load and save each take an in-process lock separately (modules/ai_assistant.py:862-891), so
the routes' read-modify-write is unlocked (app.py:3426-3444). The collector config returns
`{}` on any read error and writes with no lock (modules/collector_config.py:30-49).
Freshness authorisations append and rewrite with `O_TRUNC` (modules/nsot/freshness.py:220-226,
282-290). Topology layout writes a shared `.tmp` (app.py:1944-1952). `source.json` loads
outside its lock (modules/inventory/source_config.py:108-132). Retire's declaration reads
outside `settings_lock` (modules/nsot/retire.py:644-650). Integration cards write one key at
a time (routes/settings_integrations.py:50-57; modules/integrations/base.py:84-89). The agent
and AI stores truncate in place (modules/agent_timers.py:63-76; modules/quick_actions.py:28-31;
modules/agent_runner.py:1292-1303). Each loses an update, and several erase on an unreadable
read. One fix for all: `PathLock`, `write_atomic`, `read_json_for_write`.

**R34. Queue detail** (approvals-6, approvals-7, approvals-15). `mark_done(entry_id, note)`
takes no device and never compares the item's `device_hostname`
(modules/approval_queue.py:249-270). The capture apply closes every id the client lists
under a recorded host (routes/golden.py:414-419), and the restore apply closes its
`approval_id` if any device succeeded (:929-937). Only `resolve()` records an actor
(approval_queue.py:204); `invalidate_queued_restores` rejects with none
(modules/nsot/restore.py:424). The freshness authorise route falls back to the active list
(routes/freshness.py:30-41), although its docstring says the list is carried.

**R35. Repository housekeeping, and the migration's confirm** (git-3, git-15, git-16,
confirms-31). `_clear_stale_lock` checks an `index.lock`'s age, then removes it
(modules/nsot/repo.py:90-100, `getmtime` at :94, `os.remove` at :99), on every `git()` call,
readers included (:170, :194). A killed git leaves a lock that wedges commits for up to
120 s, and a fresh lock created between another caller's check and its remove is deleted.
`ensure_repo_hygiene` appends to `.gitignore` from every `git()` call (:171, :195, :320-346),
so readers write. The migration reads its one-shot marker before the lock and not again
inside it (modules/nsot/migrate.py:321-334), and `POST /golden/migrate/apply` requires only
a boolean `confirm`, not bound to the dry run, on a derived list
(routes/golden.py:965-975). Two applies in one process both pass the marker on a list not
yet migrated. This host already holds the marker, so the migration half does not reach it.

**R36. Unbound low-impact confirms** (confirms-12, confirms-21). NetBox "forget" needs
neither the switch nor a token (routes/netbox_safety.py:391-394), so a click from a stale
page forgets whatever is recorded now. Onboarding Create rebuilds its plan from the form at
confirm and compares no hash with the reviewed plan (routes/onboard.py:526-536).

**R37. Per-process caches and helpers** (stores-12, stores-15, live-16 to live-19, live-21,
locks-12, locks-22). The redaction value table is cached 30 s per process and invalidated
only in the process that wrote a credential (modules/redact.py:161-167, 207-211), so a host
CLI's rotation is unmasked by value in the app for up to 30 s, positional masking still
applying. The NetBox inventory cache is per process with a shared `.tmp`
(modules/inventory/__init__.py:42-44, 72-77). The NetBox sync status is guarded by an
in-process lock (modules/netbox_client.py:44, 3716-3726). The Prometheus keeper's record is
written with no lock (modules/prometheus_targets.py:508, 555-568). The heartbeat
(modules/invalidation.py:330-356) and the agent loop (modules/agent_runner.py:76-77) are per
process. `op_progress` drops a running entry once 64 accumulate (modules/op_progress.py:38-43),
which can happen today.

## 3. The specific checks

### 3.1 Two people editing the same intent

**No optimistic concurrency exists on the intent editor, the template editor, bindings or
the Settings forms.** Four writers do bind a confirm to the document they read: bulk intent
(the blob is in the plan hash, bulk_intent.py:286-295), profile propose (the HEAD profile
blob, profile_propose.py:561-564), IP SLA policy (the profile hash, ip_sla_policy.py:340-342)
and revert (the current intent text). But none holds that check through the commit (R15).

The fix, the same idea as the hash-bound confirms:

1. The editor's GET returns the HEAD commit and the blob id of `host_vars/<dev>.yml`, and
   the list it read from.
2. The preview returns a hash of (base blob, submitted text), computed by the same validator
   the save runs.
3. The save carries the base, the preview hash and the list. Under the cross-process repo
   lock (R1), the server reads HEAD's blob. If it moved, the save is refused with 409,
   naming both blobs and the commits (with actors) between them, and a three-way diff:
   base to theirs, base to mine. Otherwise it writes with `write_atomic`, stages, commits
   and releases.
4. The same for templates (base blob of the template), bindings, and the profile.
5. Settings: send only changed fields, each with the value as loaded; refuse a field whose
   stored value moved, naming who changed it (`write_settings` records the actor). A gate
   such as `netbox_allow_writes` accepts only an explicit change.

### 3.2 Every lock

| Lock | Cross-process | Owner and start shown | Lease or expiry | Recorded admin release |
|---|---|---|---|---|
| Device hold, `device_ops` | yes (`flock`) | yes, in the holder file | no; wording only after 600 s | no ("There is no force") |
| Repository, `repo_lock` | no (`threading.Lock`) | no | no | no |
| Manifest, `_lock_for` | no | no | no | no |
| Settings, `settings_lock` | yes | no | no; blocking, no timeout | no |
| File stores, `filestore.PathLock` | yes | no | no; blocking, no timeout | no |
| Update lock, `data/update/lock` | yes | names the kind only | kernel on exit | no |
| SSH session budget | no | in-process only | idle reaper, per process | no |
| Reader runs and requests | no | no | no | no |
| NetBox import "running" | not a lock | no | no | no |
| NetBox tokens, jobs | no (memory) | no | token expiry, 5 min | n/a |
| Oxidized `router.db` helper, lab sync script (added on review) | none at all | no | no | no |
| Other in-process locks (below) | no | no | no | no |
| Approval queue | none at all | no | no | no |

The other in-process locks, each a `threading.Lock` or `RLock` that serialises only its own
process: drift's `_running_lock` and `_STATE_LOCK` (modules/drift_check.py:48, 467),
`_variables_lock` (modules/ai_assistant.py:862), the NetBox `_status_lock`
(modules/netbox_client.py:44), `source_config._lock` (modules/inventory/source_config.py:41),
the inventory cache's `_lock` (modules/inventory/__init__.py:43), the Prometheus keeper's
lock (modules/prometheus_targets.py:508), the reader requests' `_REQUESTS_LOCK`
(modules/reader_job.py:554), and `device_ops._mu` (modules/nsot/device_ops.py:215).
`device_ops._mu` is correct as it is: it guards the in-process map of holds, and the `flock`
beside it does the cross-process exclusion.

The send lock per pooled session (connection.py:176-187) is correctly in-process, because a
session object never crosses a process.

What a lock needs, in one module:

- **Cross-process**: a `flock` on a file, or a database row.
- **Owner and start time**: the holder record (actor, operation, pid, process start time,
  started, last progress), written by `pwrite` of the whole record then `ftruncate` to its
  length, never truncate-then-write. Read without taking the lock: the pid's liveness plus
  `F_OFD_GETLK` or `/proc/locks`, never a shared `flock` probe.
- **A lease**: the holder renews on every progress note. A hold is breakable only when its
  pid is gone, or its lease has expired and its progress is older than a bound derived from
  the slowest measured legitimate hold (a BGP device's deploy waits up to 180 s more for its
  hold time).
- **A recorded admin release**: gated, a reason with the shape of one
  (`authorisation.py`'s rule), an audit row naming the hold it broke, the device marked
  "read back before the next operation", and a cancellation flag the holder checks before
  each send.
- **A bounded wait** where a lock is blocking (repository, stores), refusing with the
  holder named rather than hanging.

### 3.3 The list's git repository

**Commits are not strictly serialised across processes** (R1, R24, R25). Requirements:

1. One cross-process lock per repository (a `PathLock` on a file inside `.git`), re-entrant
   per thread, holder recorded.
2. Every operation that writes the index or refs runs inside it: working-tree writes,
   staging, commit, `rev-parse`, tags, prune, `gc`, renames, abandon, retire's `git rm` and
   its undo, migrate, the `.gitignore` top-up, and stale `index.lock` cleanup.
3. Commit explicit paths, so a commit can never carry a file it did not stage, even if
   something bypasses the lock.
4. Readers set `GIT_OPTIONAL_LOCKS=0` and read HEAD; they never write.
5. Take the commit's sha and create tags under the same lock; a failed tag is a reported
   failure.
6. One publisher per repository: pushes serialised, pushing an explicit sha, uploading
   `git show <sha>:<path>`.
7. A test with two processes, beside the existing two-thread test.

### 3.4 JSON and other file stores

`filestore` already has the right pieces: `PathLock` (an RLock plus `flock`, re-entrant per
thread and path), `write_atomic` (a temp per write, `fsync`, `os.replace`) and
`read_json_for_write` (an unreadable file refuses and is kept as `.corrupt-<ts>`).

| Store | Today | Recommendation |
|---|---|---|
| `user_settings.json`, credential store, `devices.csv`, NetBox provenance records, `rolled_back.json`, retry log, reader caches, backups index, Oxidized fetch record, Update wait | locked and atomic | SAFE; keep |
| Append-only audit JSONL (receipts, onboarding runs, rotation, inventory edits, break-glass, host steps, terminal, reveal) | `O_APPEND`, one row per write | SAFE on a local filesystem, except receipts (R32); keep `data/` local and say so |
| `manifest.json`, `.approvals.json` | in-process or no lock, shared `.tmp`, unreadable becomes empty | PathLock and atomic; they are committed in git, so they stay files |
| `remote.json`, `drift_state.json`, `device_lists.json`, `variables.json`, collector config, freshness authorisations, `source.json`, inventory cache, NetBox sync status, Kea fragment, topology layout, agent and AI stores, Prometheus keeper record | no lock, or in-process, or truncate in place | PathLock, `write_atomic`, `read_json_for_write` |
| Oxidized `router.db`, lab startup files and their repositories (added on review, R40) | atomic replace, no lock; sync script unlocked | an `flock` in the root helper and in the sync script |
| A list's whole folder, on list deletion (added on review, R38) | `rmtree` with no check of holds or jobs | refuse while held; a list-level lock every list writer takes |
| Approval queue | no lock, reads write | **SQLite WAL first**: one row per item, a transition is `UPDATE ... WHERE id=? AND status='pending'`, which gives the two-approver rule and a place for `requested_by` |
| Jobs, NetBox tokens, reader requests, session slots | memory | **SQLite WAL**: shared ephemeral state with expiry and an atomic consume |
| Deploy receipts, push events | JSONL, read whole | SQLite when they need querying, not before |

The backups index is locked and atomic (modules/backups.py:160-161, 174-181, the
`PathLock` blocks), and each backup file is created with `open(filepath, "x")`
(modules/backups.py:61), an exclusive create that is safe across processes.

SQLite in WAL mode is warranted where a record is a state machine with more than one actor,
or ephemeral state every process must see and consume once. Both need a local filesystem.

### 3.5 Batches overlapping on devices

**No deadlock is possible today**, because no device acquire waits: `acquire_many` takes
each device non-blocking and returns the refused ones (device_ops.py:387-400). Two
overlapping batches split the shared devices, and each reports the other's devices as
refused, per device (routes/deploy.py:661-692, 892-915). That half-application is by design
and stated.

**What is not safe**: a batch half-applied by a process exit is reported nowhere (R5), and
the lock key is not canonical (R26), so one device can be taken twice under two spellings of
its list.

A defined order, to hold as soon as any wait is introduced:

1. Device holds, sorted by (canonical list slug, hostname), non-blocking.
2. The repository write lock.
3. Store locks (manifest, approvals, remote, queue).
4. The settings lock.

Never take a device hold while holding the repository lock. The current seed, revert and
deploy paths already take holds first and commit second.

### 3.6 Previews and confirms

| Operation | Bound to | Recomputed under the hold | List carried | Verdict |
|---|---|---|---|---|
| Deploy apply, v2 batch apply, Mode B removals, dangerous-line authorisations | capture hash and command fingerprint (commands, reasons, removal ids) | no: compared before the hold | only when opened with a list; v2 always | SAFE binding; gaps R16 |
| Restore apply | the same | no | no | SAFE binding; gaps R16 |
| Capture apply | live re-read hash per device | yes | no | SAFE; carry the list |
| Seed, revert, retry | entry hash | yes | yes | SAFE |
| Rotate | plan fingerprint, rechecked inside `rotate()` | yes | yes | SAFE; result registry R10 |
| Persist | identity hash | after the check | yes | SAFE |
| Retire | plan hash | yes | yes | SAFE |
| Onboarding verify (phase two) | fingerprint of a fresh capture | yes | yes | SAFE |
| Onboarding create | rebuilt from the form, no hash | no | yes | UNSAFE low (R36) |
| Onboarding abandon | none; no hold | no | yes | UNSAFE medium (R23) |
| Bulk intent | plan hash including blobs | no lock to the commit | yes | UNSAFE medium (R15) |
| Profile propose, IP SLA policy, IP SLA commit | proposal hash, profile hash | no | yes | UNSAFE low (R15) |
| Intent editor save | nothing | n/a | no | UNSAFE high (R2) |
| Template save, bindings save | nothing | n/a | no | UNSAFE medium (R14) |
| Template approve | nothing from the client | n/a | no | UNSAFE medium (R12) |
| NetBox import, import all, Remove | one-shot token bound to plan hash and list | plan recomputed; no lock against a second import | yes | binding SAFE; R21 |
| NetBox forget | nothing | n/a | yes | UNSAFE low (R36) |
| Approval queue approve and reject | status check only | no | no | UNSAFE medium (R4) |
| Freshness authorise | divergence fingerprint, expiring | n/a | derived | binding SAFE; store and list R33, R34 |
| Break-glass export | plan hash, sealed bytes verified | n/a | n/a | SAFE |
| Update request and wait | preview hash; wait under `PathLock` | n/a | n/a | SAFE (a double click is harmless, below) |
| Heartbeat re-measure apply | measurement fingerprint | n/a | n/a | SAFE |
| Inventory role (CLI only) | fingerprint under the CSV lock | yes | yes | SAFE |
| Adopt | fingerprint under the hold; no route calls it | yes | yes | SAFE, unreachable |
| Device commands, reload, file actions | no preview: the request is the program | holds per device | n/a | SAFE |
| Remote publication acknowledge (added on review) | typed KINDS only; values recorded at click time | n/a | derived | UNSAFE medium (R41) |
| Migration apply (added on review) | a boolean `confirm`, not the dry run | marker read before the lock | derived | UNSAFE low (R35) |
| Server restart, AI restart (added on review) | nothing; no check of holds or jobs | n/a | n/a | UNSAFE (R5) |
| Refresh Hostnames, sync renames, revoke approval, Update "it is done" (added on review) | no preview by design: one-click writes | n/a | derived, or not list-scoped | SAFE as confirms; their stores are R6, R1, R13; "it is done" appends one row per click |

**The Update request, stated once.** No lock spans the plan's "nothing pending" gate and the
request write (modules/update_op.py:655-667, 708-731), so a double click can write two
request files and two audit rows. The root updater removes every entry and acts on the
newest (deploy/update/nmas-update:157-178), so one update runs. SAFE in effect. stores-19
and confirms-25 now say the same.

**The one-click writes, checked.** Refresh Hostnames (gate A) writes `devices.csv` under its
lock and records a pending rename in the manifest (R6). Sync renames (gate K,
routes/golden.py:992) commits under `repo_lock` (R1). Revoke approval (gate A,
routes/templates.py:319) requires a reason and writes the approvals record (R13). Update's
"it is done" (gate C, routes/update.py:59-84) accepts only an owed step no check can answer
and appends a row per click. None previews, by design, and none confirms anything a person
was shown, so there is nothing to bind. The table's population is every operation that
confirms, plus these four, listed so that their absence is not read as unexamined.

No binding records who previewed. Content binding means one person's confirm cannot consume
another's, and a moved state refuses. NetBox tokens are bearer tokens with no actor
(netbox_authz.py:115-122); add the actor.

### 3.7 Approvals

**Two approvers at once.** No device changes twice: every queued kind only opens a preview,
and the capture and restore applies re-read and hold the device (routes/golden.py:575-607;
device_ops.py:298). But the queue record is not safe (R4): `resolve()` is check-then-set
with no lock, a confirm-ending item returns to plain "pending" after approval
(approval_queue.py:216-227), so a second approver also gets a handoff, and the UI does not
draw `resolved_by`. Fix: a compare-and-set transition under the lock, an "in review" state
(by whom, since when, which preview hash), drawn as "A opened the preview 2 min ago". Also
bind the handed-off ids to their device (approval_queue.py:249-270), and record an actor on
every transition (`mark_done`, `withdraw`, `invalidate_queued_restores`).

**Four-eyes as a configurable policy for the roles stage.** Nothing exists (R31). Per
NSOT_AUTHORIZATION.md sections 5, 6 and 8:

1. Split the gate kind `approve` into `author` and `approve`.
2. Record `requested_by` on every queue item (the verified person, `ai-agent` or the drift
   check).
3. A host-side setting, file-only and shown read-only on the posture panel, for example
   `separation_of_duties: off | artifact | artifact+deploy`, defaulting to `off` so the
   default reproduces today's behaviour.
4. `artifact`: the approver differs from every verified author of the template revision
   (from `git log` over its closure, reading only `Actor-Verified: access`), and from a queue
   item's requester. Unverified authorship refuses rather than passes.
5. `artifact+deploy`: also the intent author differs from the deploy confirmer.
6. The approval screen says "You authored this revision" when the policy refuses.

### 3.8 Visibility

**Who is operating on a device, live.** Only the legacy page shows it, by polling
(templates/base.html:27; nmas_in_flight.js:91-96). No v2 page reads a hold. Fix: announce a
`device_holds` key with the device names on acquire, progress and release; draw "being
deployed by X for 2 min, step: verify" on the v2 device page, the devices list and every
preview; disable a confirm while another person holds the device; draw an interrupted
operation (R5) with its last step.

**A stale preview told of another person's change.** Not today (R27). Fix: after a
successful mutating response, also announce its keys, with the devices and the actor, to
every connection. Previews and editors subscribe to `intent`, `goldens` and `device_state`
for their own devices and say "r2's intent was committed by X at T; your preview is based
on an older version; preview again", with the confirm disabled. The hash-bound refusal stays
the backstop. Under several workers this needs R8's message queue first.

### 3.9 Socket.IO and readers across workers

What breaks with more than one process:

- **Socket.IO** (R8): connections fail without sticky sessions; announcements reach only
  one worker's clients without a queue; the terminal's state is per process. A queue needs a
  broker (Redis) that is not in `requirements.lock`, a new service on an air-gapped host.
- **Services** (R7): nothing starts under an import; per-worker starts run everything N
  times, and the UDP binds fail.
- **Reachability** (R9): every device reads offline in a worker without the reader.
- **Jobs** (R10), **reader requests** (R29), **NetBox tokens** (R21): answered by one worker
  only.
- **Reader runs** (R28): N times the reads, value regressions, concurrent `git fetch`.
- **Session budget** (R11): N times the vty lines.
- **Redaction cache**: a credential write in one process leaves other processes' value table
  stale for up to 30 s (modules/redact.py:161-167, 207-211); positional masking still
  applies. Host CLIs already do this today.
- **Heartbeat, keeper, agent loop, inventory cache, NetBox sync flag, `op_progress`**: per
  process.

Safe across workers: the reader stores themselves (`PathLock`, reader_job.py:366-404), the
Update wait release (update_op.py:816-850), the identity JWKS cache (each worker verifies on
its own), and the hook registry.

## 4. Appendix: the full inventory

Every write path read, SAFE ones included, with the verdict after the check. Risk is h, m or
l. "Today" is yes when two users, two tabs or a host CLI already reach it.

### git repository (20 paths, 16 not safe)

| id | Path | Writes | Protection | Cross-process | Verdict | Risk | Today |
|---|---|---|---|---|---|---|---|
| git-1 | `repo_lock` around every list-repo commit | index, commits, tags | `threading.Lock` (repo.py:72-76) | no | UNSAFE | h | yes |
| git-2 | every git call and `index.lock` | index | no retry; no `GIT_OPTIONAL_LOCKS=0` | partly | UNSAFE | m | yes |
| git-3 | `git()` timeout and `_clear_stale_lock` | `index.lock` removal | 120 s check-then-remove (repo.py:90-100) | partly | UNSAFE | l | yes |
| git-4 | `commit()` with no paths after `stage_exactly` | whole index | one check (repo.py:236-266) | no | UNSAFE | h | yes |
| git-5 | HEAD read and tags after commit | tags, published sha | separate `rev-parse`; abandon unlocked | no | UNSAFE | m | yes |
| git-6 | `save_golden` working-file compare and undo | golden files | in-process lock | no | UNSAFE-MULTI-PROCESS | m | yes (CLI) |
| git-7 | manifest `save()` and callers | `manifest.json` | `threading.Lock`, shared `.tmp`; rename rollback bypasses it (repo.py:423, 442) | no | UNSAFE | h (m today) | yes (CLI; rename rollback in one process) |
| git-8 | intent editor save | `host_vars` | none | no | UNSAFE | h | yes |
| git-9 | template, bindings, approve, revoke | templates, `.approvals.json` | none | no | UNSAFE | m | yes |
| git-10 | hash-confirmed intent writers | `host_vars`, profile | hash, then write, then commit | partly | UNSAFE | m | yes |
| git-11 | retire's `git rm` and failure undo | index, trees | device hold only | no | UNSAFE | m | yes |
| git-12 | onboarding Create and Abandon | credentials, manifest, `host_vars` | none | no | UNSAFE | m | yes |
| git-13 | post-commit push and S3 hooks | remote, S3 | thread per commit | no | UNSAFE | l | yes |
| git-14 | `remote.json` writers | `remote.json` | none, shared `.tmp` | no | UNSAFE | m | yes |
| git-15 | migration marker | migration commit | marker read before the lock, not re-read inside it | no | UNSAFE | l | no: two applies in one process pass the marker on a list not yet migrated, and this host already holds the marker |
| git-16 | `.gitignore` top-up on every git call | `.gitignore` | none | no | UNSAFE | l | yes |
| git-17 | tag prune and `gc --auto` | tags, packs | repo lock, git's own locks | partly | SAFE | l | no |
| git-18 | rolled-back record and retry log | `.nsot/*.json` | `PathLock`, `write_atomic` | yes | SAFE | l | no |
| git-19 | deploy and restore crash staging | `.nsot/staging/*` | one file per held device | yes | SAFE | l | no |
| git-20 | hook registry | memory | per process, filled lazily | n/a | SAFE | l | no |

### Intent and edited documents (20 paths, 18 not safe)

| id | Path | Writes | Protection | Cross-process | Verdict | Risk | Today |
|---|---|---|---|---|---|---|---|
| intent-1 | intent editor: no base | `host_vars` | existence check only | no | UNSAFE | h | yes |
| intent-2 | intent editor: write outside the lock | `host_vars` | lock only around the commit | no | UNSAFE | m | yes |
| intent-3 | intent editor: save not bound to preview | `host_vars` | client-side arming | n/a | UNSAFE | m | yes |
| intent-4 | editors derive the global active list | any list | none | n/a | UNSAFE | h | yes |
| intent-5 | bulk intent apply | `host_vars` x N | plan hash, no lock to commit | no | UNSAFE | m | yes |
| intent-6 | every list-repo commit | index, HEAD | `threading.Lock`; abandon unlocked (onboard.py:1796-1806) | no | UNSAFE | h | yes (host CLIs; abandon in one process) |
| intent-7 | template editor save | templates, tombstones | none | no | UNSAFE | m | yes |
| intent-8 | template approve | `.approvals.json` | none | no | UNSAFE | m | yes |
| intent-9 | `.approvals.json` read-modify-write | approvals record | none, shared `.tmp` | no | UNSAFE | m | yes |
| intent-10 | bindings save | `bindings.yml` | none | no | UNSAFE | l | yes |
| intent-11 | profile propose, IP SLA policy | profile, profile secret | hash, no lock to commit | no | UNSAFE | l | yes |
| intent-12 | IP SLA commit | `host_vars` | fingerprint, HEAD re-read | no | UNSAFE | l | yes |
| intent-13 | held versus unheld intent writers | `host_vars` | holds on some writers only | partly | UNSAFE | l | yes |
| intent-14 | Settings modal save | `user_settings.json` | file safe; every field resent | yes | UNSAFE | m | yes |
| intent-15 | integration card save | settings, secrets | per-key lock | yes | UNSAFE | l | yes |
| intent-16 | retire's unmapped declaration | settings key | read outside the lock | no | UNSAFE | l | yes |
| intent-17 | rolled-back and retry records | `.nsot/*.json` | `PathLock` | yes | SAFE | l | no |
| intent-18 | settings file integrity | `user_settings.json` | `settings_lock` | yes | SAFE | l | no |
| intent-19 | `GET /templates` seeds and commits | templates | in-process lock | no | UNSAFE-MULTI-PROCESS | l | no |
| intent-20 | no cross-session visibility | n/a | caller's response only | no | UNSAFE | m | yes |

### File stores (32 paths, 22 not safe)

| id | Path | Writes | Protection | Cross-process | Verdict | Risk | Today |
|---|---|---|---|---|---|---|---|
| stores-1 | approval queue | `approval_queue.json` | none | no | UNSAFE | h | yes |
| stores-2 | list registry and `current_list` | `device_lists.json` | none | no | UNSAFE | h | yes |
| stores-3 | intent editor | `host_vars` | none | no | UNSAFE | h | yes |
| stores-4 | drift state | `drift_state.json` | RLock in one function | no | UNSAFE | m | yes |
| stores-5 | publication record | `remote.json` | none | no | UNSAFE | m | yes |
| stores-6 | Kea ZTP fragment | fragment, Kea | none | no | UNSAFE | m | yes |
| stores-7 | template approvals record | `.approvals.json` | none | no | UNSAFE | m | yes |
| stores-8 | manifest | `manifest.json` | `threading.Lock` | no | UNSAFE | m | yes |
| stores-9 | variables | `variables.json` | separate lock holds for load and save | no | UNSAFE | l | yes |
| stores-10 | collector config | `collector_config.json` | none | no | UNSAFE | l | yes |
| stores-11 | freshness authorisations | per-list JSON | none, truncate | no | UNSAFE | l | yes |
| stores-12 | NetBox sync status | `netbox_sync_status.json` | in-process lock | no | UNSAFE-MULTI-PROCESS | l | no |
| stores-13 | `source.json` and inventory caches | per-list JSON | in-process, load outside the lock | no | UNSAFE | l | yes |
| stores-14 | key files | `key.key`, session key | check then `O_TRUNC` | no | UNSAFE-MULTI-PROCESS | m | no |
| stores-15 | tokens, jobs, redaction cache, requests | memory | in-process | no | UNSAFE-MULTI-PROCESS | m | partly: the redaction cache with host CLIs (live-19) |
| stores-16 | agent and AI stores | timers, activity, caches, histories | mostly none | no | UNSAFE | l | yes |
| stores-17 | topology layout, `.env` | layout JSON, `.env` | none, shared `.tmp` | no | UNSAFE | l | yes |
| stores-18 | template and bindings working files, profile | templates, profile | none, blind restore | no | UNSAFE | m | yes |
| stores-19 | collectors and small state (traps, flows, startup check, targets, coverage, migration, Update request) | small files | mixed | no | UNSAFE (migration, git-15); UNSAFE-MULTI-PROCESS (rest); the Update request is SAFE in effect (section 3.6, confirms-25) | l | partly |
| stores-20 | settings | `user_settings.json` | `settings_lock` | yes | SAFE | l | no |
| stores-21 | credential store | `credential_profiles.json` | `PathLock` | yes | SAFE | l | no |
| stores-22 | inventory CSV | `devices.csv` | `devices_csv_lock` | yes | SAFE | l | no |
| stores-23 | NetBox provenance records | created, modified, adopted, removals | `PathLock`, `O_APPEND` | yes | SAFE | l | no |
| stores-24 | rolled-back record, retry log | `.nsot/*.json` | `PathLock` | yes | SAFE | l | no |
| stores-25 | reader caches | one JSON per reader | `PathLock`, `write_atomic` | yes | SAFE | l | no |
| stores-26 | backups index, fetch record, Update wait, heartbeat rules | small files | `PathLock` (backups.py:160-161, 174-181; backup files by exclusive create, :61) or fingerprint and `write_atomic` | yes | SAFE | l | no |
| stores-27 | append-only audit JSONL | receipts and audit logs | `O_APPEND` | partly | SAFE (receipts UNSAFE, R32) | l | receipts yes |
| stores-28 | device hold files | `data/device_ops/*` | `flock`, holder writes | yes | SAFE | l | no |
| stores-29 | per-device staging | staged credential, captures, intent | one file per held device | yes | SAFE | l | no |
| stores-30 | list deletion (added on review) | the list's folder, the registry | NetBox and credential checks; holds and jobs not checked (device.py:566-605; app.py:1109-1173) | no | UNSAFE | m | yes |
| stores-31 | Oxidized `router.db` (added on review) | `router.db` | atomic replace, no `flock` (scripts/nmas-oxidized-cred:156-210) | no | UNSAFE | m | yes |
| stores-32 | lab sync during persist (added on review) | lab startup files, lab repositories | none (`scripts/oxidized-to-config.sh`, no `flock`) | no | UNSAFE | l | yes |

### Locks (24 paths, 17 not safe)

| id | Path | Writes | Protection | Cross-process | Verdict | Risk | Today |
|---|---|---|---|---|---|---|---|
| locks-1 | `repo_lock` | list repository | `threading.Lock` | no | UNSAFE | h | yes (CLI) |
| locks-2 | abandon stages outside the repo lock | index, commit | none | no | UNSAFE | m | yes |
| locks-3 | manifest lock | `manifest.json` | `threading.Lock`, shared `.tmp` | no | UNSAFE | h (m today) | yes |
| locks-4 | device hold exclusion | device holds | exclusive `flock` | yes | SAFE | l | no |
| locks-5 | device hold lifetime | device holds | no lease, no release | yes | UNSAFE | m | yes |
| locks-6 | holder probe | none (shared `flock`) | probe races acquire | partly | UNSAFE | l | yes |
| locks-7 | hold key | lock file path | list name, not slug | yes | UNSAFE | l | yes |
| locks-8 | `may_write` with ip-less holds | write guard | weakened, conservative | n/a | SAFE | l | no |
| locks-9 | SSH session budget | vty lines | per process | no | UNSAFE | m today; h under workers | yes (host CLIs) |
| locks-10 | send lock per pooled session | one session | in-process, correct scope | n/a | SAFE | l | no |
| locks-11 | job registries | memory | `threading.Lock` | no | UNSAFE-MULTI-PROCESS | m | no |
| locks-12 | `op_progress` purge | memory | drops running entries past 64 | no | UNSAFE | l | yes |
| locks-13 | in-flight visibility | none | holds from files; `op_progress` per process; no v2 live view | partly | UNSAFE (the v2 gap is single-process; `op_progress` is multi-process) | m | yes (v2 gap) |
| locks-14 | batch lock order | device holds | non-blocking acquires | yes | SAFE | l | no |
| locks-15 | batch half-applied on process death | devices, record | none | n/a | UNSAFE | h | yes |
| locks-16 | `settings_lock` | settings | RLock and `flock` | yes | SAFE | l | no |
| locks-17 | `filestore.PathLock` | stores | RLock and `flock` | yes | SAFE | l | no |
| locks-18 | reader and service singletons | reader stores, drift state | in-process; drift state unlocked | no | UNSAFE-MULTI-PROCESS | m | drift state yes |
| locks-19 | Update lock | the checkout | `flock`; probe can cause a spurious refusal | yes | SAFE | l | no |
| locks-20 | push hooks and the remote record | remote, `remote.json` | none | no | UNSAFE | m | yes |
| locks-21 | NetBox import "running" flag | NetBox, status | not a lock; tokens in memory | no | UNSAFE | m | yes |
| locks-22 | Prometheus keeper record | sync record | `write_atomic`, no lock | no | UNSAFE-MULTI-PROCESS | l | no |
| locks-23 | break-glass terminal input (added on review) | devices | no device hold, outside the session budget and C101 (app.py:532-575) | no | UNSAFE | m | yes |
| locks-24 | NetBox writers outside the tab (added on review) | NetBox | none: onboarding phase two, adopt, retire's mask, the mask script take no per-list lock | no | UNSAFE | m | yes |

### Preview and confirm (32 paths, 20 not safe)

| id | Path | Writes | Protection | Cross-process | Verdict | Risk | Today |
|---|---|---|---|---|---|---|---|
| confirms-1 | intent edit | `host_vars` | none | no | UNSAFE | h | yes |
| confirms-2 | template approve | `.approvals.json` | none | no | UNSAFE | m | yes |
| confirms-3 | template write | templates | none | no | UNSAFE | m | yes |
| confirms-4 | deploy and restore binding | devices, commit | capture and command hashes; holds | partly | SAFE | l | no |
| confirms-5 | command hash optional | devices | recompute only when sent | n/a | UNSAFE | m | yes |
| confirms-6 | compare before the hold | devices | hold taken after the check | no | UNSAFE | l | yes |
| confirms-7 | confirm list derived | devices, repo, queue | active-list fallback | n/a | UNSAFE | m | yes |
| confirms-8 | commit lock for confirms | repo | `threading.Lock`; abandon unlocked | no | UNSAFE | h | yes |
| confirms-9 | bulk intent | `host_vars` | hash outside the lock | no | UNSAFE | m | yes |
| confirms-10 | profile propose, IP SLA | profile, `host_vars` | hash outside the lock | no | UNSAFE | l | yes |
| confirms-11 | onboarding Abandon | NetBox, repo, credentials, Kea | identity gate only | no | UNSAFE | m | yes |
| confirms-12 | onboarding Create | credentials, repo, Kea | plan rebuilt, no hash | no | UNSAFE | l | yes |
| confirms-13 | onboarding Verify | device, records | fingerprint under the hold | yes | SAFE | l | no |
| confirms-14 | capture apply | repo, queue | re-read under the hold | yes | SAFE | l | no |
| confirms-15 | seed, revert, retry | repo, records | hash under the hold | partly | SAFE | l | no |
| confirms-16 | rotate | device, credentials, repo | fingerprint under the hold; job in memory | partly | UNSAFE-MULTI-PROCESS | m | no |
| confirms-17 | persist | startup config | identity hash, hold | yes | SAFE | l | no |
| confirms-18 | retire | repo, settings, CSV | plan under the hold | partly | SAFE | l | no |
| confirms-19 | NetBox tokens | NetBox | memory | no | UNSAFE-MULTI-PROCESS | m | no |
| confirms-20 | NetBox concurrent imports | NetBox | none | no | UNSAFE | m | yes |
| confirms-21 | NetBox forget | created record | none | n/a | UNSAFE | l | yes |
| confirms-22 | approval queue resolve | queue | none | no | UNSAFE | m | yes |
| confirms-23 | freshness authorise store | authorisations | none, truncate | no | UNSAFE | l | yes |
| confirms-24 | break-glass export | audit rows | plan hash, verified bytes | yes | SAFE | l | no |
| confirms-25 | Update request and wait | request files | hash; `PathLock` | yes | SAFE | l | no |
| confirms-26 | heartbeat apply | rules file | fingerprint, atomic | yes | SAFE | l | no |
| confirms-27 | v2 batch and job registries | devices, memory | hashes required; jobs in memory | no | UNSAFE-MULTI-PROCESS | m | no |
| confirms-28 | device commands, reload, files | devices | holds; no preview by design | partly | SAFE | l | no |
| confirms-29 | confirms not tied to a person | n/a | content hashes; bearer NetBox tokens | n/a | SAFE | l | no |
| confirms-30 | remote publication acknowledge (added on review) | `remote.json` | typed kinds only; values taken at click time (routes/remote.py:124-161; remote.py:780-822) | no | UNSAFE | m | yes |
| confirms-31 | migration apply (added on review) | golden, manifest, commit | boolean `confirm`, not bound to the dry run (routes/golden.py:965-975) | no | UNSAFE | l | no (marker held) |
| confirms-32 | one-click writes: Refresh Hostnames, sync renames, revoke approval, Update "it is done" (added on review) | CSV, manifest, repo, approvals, host-steps record | no preview by design; stores elsewhere (R1, R6, R13) | n/a | SAFE | l | no |

### Approvals (20 paths, 16 not safe)

| id | Path | Writes | Protection | Cross-process | Verdict | Risk | Today |
|---|---|---|---|---|---|---|---|
| approvals-1 | queue read-modify-write | queue | none | no | UNSAFE | m | yes |
| approvals-2 | queue reads write | queue | none | no | UNSAFE | m | yes |
| approvals-3 | queue follows the active list | queue | none | n/a | UNSAFE | m | yes |
| approvals-4 | restore rejects its own item | queue | unconditional | n/a | UNSAFE | m | yes |
| approvals-5 | two approvers, one item | queue, then a confirm | device effect guarded by holds and hashes | yes | SAFE | l | no |
| approvals-6 | handoff ids not bound to device | queue | status check only | n/a | UNSAFE | l | yes |
| approvals-7 | closures unattributed | queue fields | `resolve` only records an actor | n/a | UNSAFE | l | yes |
| approvals-8 | approve actor is the verified one | records, trailers | gate's identity | yes | SAFE | l | no |
| approvals-9 | no four-eyes | n/a | none | n/a | UNSAFE | m | no |
| approvals-10 | `.approvals.json` read-modify-write | record | none, shared `.tmp` | no | UNSAFE | m | yes |
| approvals-11 | approve not bound to what was validated | record | none | no | UNSAFE | m | yes |
| approvals-12 | uncommitted approvals govern | record | gate reads the working file | partly | UNSAFE | m | yes |
| approvals-13 | template edit last writer wins | templates | none | no | UNSAFE | m | yes |
| approvals-14 | freshness authorisations store | authorisations | none, truncate | no | UNSAFE | l | yes |
| approvals-15 | freshness authorise derives its list | authorisations | active-list fallback | n/a | UNSAFE | l | yes |
| approvals-16 | retry authorisation | retry log, rolled-back record | hold, `PathLock` | yes | SAFE | l | no |
| approvals-17 | approval commits share the in-process lock | repo | `threading.Lock` | no | UNSAFE-MULTI-PROCESS | m | yes (CLI) |
| approvals-18 | approval changes not announced | n/a | 30 s poll for the queue only | no | UNSAFE | l | yes |
| approvals-19 | queue expiry | queue status | never executes | n/a | SAFE | l | no |
| approvals-20 | drift dedupe | queue | check-then-append, unlocked | no | UNSAFE | l | yes |

### Live state (23 paths, 20 not safe)

| id | Path | Writes | Protection | Cross-process | Verdict | Risk | Today |
|---|---|---|---|---|---|---|---|
| live-1 | Socket.IO | events | no queue, no sticky sessions | no | UNSAFE-MULTI-PROCESS | h | no |
| live-2 | background services | readers, drift, keeper, listeners | `__main__` only | no | UNSAFE-MULTI-PROCESS | h | no |
| live-3 | reachability `STATUS` | memory | per process | no | UNSAFE-MULTI-PROCESS | h | no |
| live-4 | route mutations not broadcast | n/a | caller's response only | n/a | UNSAFE | m | yes |
| live-5 | job registries | memory | `threading.Lock` | no | UNSAFE-MULTI-PROCESS | h | no |
| live-6 | reader runs overlap | reader stores, `git fetch` | store locked, runs not | partly | UNSAFE | m | yes |
| live-7 | reader request registry | memory | per process | no | UNSAFE-MULTI-PROCESS | m | no |
| live-8 | device hold | lock files | `flock` | yes | SAFE for exclusion (its gaps are R26, which reach today) | l | no |
| live-9 | crash mid-operation invisible | none | none | yes | UNSAFE | m | yes |
| live-10 | SSH session budget | vty lines | per process | no | UNSAFE | m | yes |
| live-11 | drift state | `drift_state.json` | unlocked | no | UNSAFE | m | yes |
| live-12 | approval queue | queue | none | no | UNSAFE | m | yes |
| live-13 | installation-wide active list | `device_lists.json` | none | no | UNSAFE | h | yes |
| live-14 | no live holder on v2 | n/a | plan-time busy text | partly | UNSAFE | m | yes |
| live-15 | NetBox tokens | memory | per process | no | UNSAFE-MULTI-PROCESS | m | no |
| live-16 | NetBox inventory cache | memory, cache file | in-process; Refresh unguarded | no | UNSAFE | l | yes (dormant) |
| live-17 | agent runner | activity log, state | in-process | no | UNSAFE-MULTI-PROCESS | l | no |
| live-18 | Prometheus keeper wake | file_sd files, record | in-process wake | partly | UNSAFE-MULTI-PROCESS | l | no |
| live-19 | redaction cache | memory | per process, 30 s TTL | no | UNSAFE-MULTI-PROCESS | l | yes (CLI) |
| live-20 | identity JWKS cache | memory | per process, correct | n/a | SAFE | l | no |
| live-21 | heartbeat | events | per process | no | UNSAFE-MULTI-PROCESS | l | no |
| live-22 | Update wait release | wait record, request | `PathLock` | yes | SAFE | l | no |
| live-23 | server and AI restart routes (added on review) | ends the process | gate K only; no check of holds, jobs or a commit (app.py:3171-3179, 3313-3322) | n/a | UNSAFE | m (no page calls them) | yes |

## 5. Proposed test harness

### Two users and two worker processes

Built on the existing suite, never on the network: conftest's temporary store
(`NMAS_DATA_DIR`), the loopback-only confinement (`tests/network_guard.py`,
`scripts/nmas-test`), `tests/fake_netbox.py`, and the fake router transports the adopt and
rotation tests already use. `tests/test_device_ops.py:99` already proves a child process's
hold refuses the parent, and that its death releases it; that is the pattern to extend.

1. **Two worker processes.** A fixture starts two real processes with `multiprocessing`
   (`spawn`, so nothing is inherited by accident), each importing the app against the same
   temporary store and serving on its own loopback port through Werkzeug's `make_server`.
   The tests call both over HTTP. Host-CLI cases run the real script as a third process.
2. **Two simulated users.** Each request carries a verified identity built the way
   `tests/test_device_v2.py` signs an assertion through the real `identify()`, so every
   commit and record names the right person.
3. **Deterministic interleaving, never sleeps.** A pause point is a named hook (an
   environment-selected monkeypatch inside the child) that waits on a file-based barrier at
   an exact step: after `stage_exactly`'s check, after the editor's write and before its
   commit, after `approve()`'s validation and before its fingerprint, after `_load_queue`.
   The parent releases each side in a chosen order. A control whose timing is tighter than
   the clock tests the clock; a barrier does not.
4. **Every test has a control** that removes the fix and shows the test fails for the
   property, not by crashing, and reads which tests failed.

Cases, one per finding:

- R1: two processes commit different devices; then the same device; each commit carries
  only its own files and its own actor.
- R2: user A opens r2's intent, user B commits a change, A saves: refused with both blobs
  and the diff; nothing committed.
- R3: user B switches lists between A's open and save: A's write lands in A's list or is
  refused, never in B's.
- R4: approve in one worker while the other polls the list and a drift run adds an item:
  nothing lost; two approvers: the second refused, naming the first.
- R6, R13, R18, R19, R22, R33: two processes in a read-modify-write of each store: no lost
  update; a planted unreadable file refuses and is preserved.
- R12: an edit lands between validation and fingerprint: the approval is refused.
- R15, R16: a commit lands between the hash check and the write: refused.
- R20: approve a revert item, restore it: the item closes as done.
- R21: two imports confirmed at once: the second refused, naming the first.
- R23: Abandon during phase two: refused, naming the holder.
- R10, R29, R21 tokens: a preview on worker 1 and its GET or confirm on worker 2.
- R8: a client connected to worker 2 receives an announcement made in worker 1. If the fix
  is a message queue, this case needs a broker: Redis is not in `requirements.lock`, so the
  case either runs a broker the suite starts on loopback or tests the single Socket.IO
  process design instead.
- R11: two processes open sessions to one device: the budget holds across both.

Added on review, for findings the cases above do not reach:

- **R7 needs a real WSGI server.** `make_server` per process never takes gunicorn's import
  path, which is R7's whole failure. One case imports `app` under gunicorn (where it is
  installed; skipped, saying so, elsewhere) with one worker and then two, and asserts the
  background services start exactly once, from the process that owns them.
- R5 and the restart routes: a pause point after the first device of a batch, then
  `POST /server/restart` (and `/ai/restart`) from the second user: refused, naming the
  holder.
- R30: two processes start on a store with no `key.key`: both end up encrypting with the one
  key on disk, and a value one encrypts the other decrypts.
- R24: a reader runs `git status` at a pause point inside a save's staging: the save
  succeeds, with `GIT_OPTIONAL_LOCKS=0` in force.
- R26's canonical key: one process holds a device under the list's display name, another
  asks under its slug: refused.
- R38: a second user deletes the list while a deploy holds one of its devices: refused,
  naming the hold.
- R39: a terminal session is open on a device and a deploy confirms it: refused, naming the
  terminal's holder (or the terminal refused while the deploy holds it).
- R40: two rotations of different devices reach the `router.db` helper at once, through a
  pause point after its read: both rows hold their new passwords. The same for two lab syncs.
- R41: a new secret value of an already-named kind is committed between the card's draw and
  the acknowledgement: refused, naming the new value's fingerprint.

### Failure injection

- **A process killed mid-operation.** `SIGKILL` a worker after it has pushed one device of
  a three-device batch (a pause point after the first device). Assert: the hold is free, the
  device is drawn as interrupted with its last step, the next operation on it requires a
  read-back, and a receipt exists for the device that was pushed.
- **A lock left behind.** A holder file whose pid is gone, non-empty, unlocked: drawn as
  interrupted, never as "no holder" and never as "being ? by unknown".
- **A hung holder.** `SIGSTOP` a holder. Assert: refused with the holder named and "may be
  stuck" after the bound; the lease expires; the admin release is refused without a reason,
  succeeds with one, writes an audit row, and the holder, resumed, stops before its next
  send.
- **A worker restart during a job.** Kill the worker running a capture preview: the job's
  GET says interrupted, from the recorded pid, not "the server restarted".
- **A torn store.** Truncate each store mid-write (a pause point inside the write): readers
  refuse or wait, writers refuse, nothing is erased.

Every test runs under the suite's hard bound, so a deadlock names the test that hung rather
than stalling the run.

## 6. Placement

The fixes land before 9.S runs more than one worker. Two things must land even before 9.S
phase 2's single gunicorn worker, because one worker already breaks them.

### Even one person in one tab

These findings need no second person, tab or CLI. The program races itself, or one person's
own actions collide:

- **R4**: a drift run's six threads (modules/drift_check.py:383, 392) add and withdraw queue
  items while that person approves one, and their own tab's 30 s poll rewrites the queue.
- **R5**: pressing Update during their own batch, or `release_deferred` requesting an update
  on its own when CI passes (modules/update_op.py:813-830), ends the batch mid-run. The
  restart routes (added on review) do the same.
- **R13**: every template edit that revokes an approval leaves the tombstones uncommitted
  (routes/templates.py:301-313; repo.py:1340-1342), and the gate reads them from the working
  file.
- **R19**: their own Check now overlaps the scheduled drift run, because the route never
  sets `_running` (app.py:3208-3216).
- **R20**: restoring their own approved revert item rejects it (routes/golden.py:905;
  modules/nsot/restore.py:415-424).
- **R28**: the scheduled reader loop races the post-commit refresh their own commit starts
  (modules/readers/remote_publication.py:288-292), and an older value can overwrite a newer.

Every other finding marked "Today: yes" needs a second actor: a person, a tab or a host CLI.

### Now: affects today's install (two users, two tabs, or a host CLI)

In order of risk:

1. **R1 and R24, R25**: the cross-process repository lock, explicit-path commits, every
   stager inside it, `GIT_OPTIONAL_LOCKS=0`, sha and tags under the lock. Most other git
   fixes depend on this one.
2. **R2**: optimistic concurrency on the intent editor (base blob, refuse with the diff),
   then **R14** for templates and bindings with the same mechanism.
3. **R4 and R20, R34**: the approval queue on a locked store (or SQLite WAL), pure reads,
   compare-and-set transitions, carried list; fix the restore handoff.
4. **R3**: every write carries its list; the active list becomes per session.
5. **R5**: gate Update, nmas-deploy and both restart routes (`/server/restart`,
   `/ai/restart`) on held devices and running jobs, or retire the restart routes;
   per-device receipts; draw an interrupted operation. **R38** in the same change: refuse a
   list deletion while any hold or job exists on the list.
6. **R6, R13**: manifest and approvals record on `PathLock`; commit tombstones with the
   template; read approvals at HEAD. Then **R12**: approve carries the reviewed fingerprint.
7. **R15, R16, R17, R23**: hold the lock and devices across check, write and commit; require
   the command hash; acquire before comparing; Settings sends changed fields only; hold the
   hostname for Create and Abandon.
8. **R18, R19, R22, R21, R41**: remote record and one publisher; drift state and one drift
   run at a time; the Kea fragment lock; one per-list NetBox lock taken by every NetBox
   writer; the acknowledgement bound to the values it showed.
9. **R40**: an `flock` in the `router.db` helper and in the lab sync script.
10. **R26, R27, R28, R39**: lease and recorded admin release, canonical key, no `flock`
    probe; broadcast mutations and a live holder on v2 pages; one run per reader at a time;
    the terminal holds its device (until 7.8 removes it).
11. **R11**: cross-process session slots (host CLIs already exceed the budget).
12. The low findings (R32 to R37), in any order.

### Before 9.S phase 2 (one gunicorn worker)

1. **R7**: start the services from one designated place that a WSGI import reaches,
   exactly once, with a test that importing `app` under a WSGI server starts them once.
2. **R5** again: gunicorn's graceful restart and worker timeout end a running job thread;
   disable worker recycling (`max_requests`) and set the graceful timeout from the slowest
   measured operation, or move jobs to a runner that survives a restart.

### Before more than one worker (10.W, or any multi-worker step)

1. **R8**: sticky sessions and a Socket.IO message queue, or one Socket.IO process.
2. **R7**: a leader lock so the service runner exists once; web workers start nothing.
3. **R9, R10, R29, R21 tokens**: reachability from the stored value; jobs, reader requests
   and NetBox tokens in a shared store (SQLite WAL).
4. **R30**: exclusive key creation, or keys made by an install step before workers fork.
5. **R37**: caches keyed on file generation (redaction, inventory); keeper, heartbeat and
   agent only in the service runner.

Items 3 and 4 of "now" and R26's lease also feed P.16's build-or-adopt evaluation: the
shared job store, leases and interrupted-operation detection are the machinery it costs.

## Withdrawn on checking

No finding was refuted outright. These parts of findings were withdrawn or corrected by the
second reader, or on review where the entry says so, and the text above uses the corrected
form:

- **`nmas-inventory-role` commits to git**: withdrawn. It writes `devices.csv` and an
  audit row only (modules/inventory_edit.py).
- **The template edit-versus-approve race is safe by design**: withdrawn. `approve()`
  fingerprints after validating, so an edit in between is approved unvalidated (R12).
- **Template approve is high risk**: lowered to medium. The deploy plan still shows the
  program a person confirms by hash.
- **The stale-lock remover can delete a live `index.lock` held by this program**: narrowed
  on review, not withdrawn. It cannot delete a lock held by a slow git of this program:
  every git call is killed at 30 s and the remover waits 120 s. But the remover is
  check-then-remove (`getmtime`, then `os.remove`, repo.py:90-100). A fresh `index.lock`
  created by this program's own git between another caller's age check and its remove is
  deleted. That race needs a stale lock to exist first, and it stays in git-3 and R35 as
  UNSAFE, low.
- **NetBox tokens in memory are high risk**: lowered to medium. Under several workers they
  fail closed, refusing, never writing wrongly.
- **Several findings were "multi-process only"**: corrected to affecting today, because a
  host CLI is a second process or an unlocked in-process writer exists: the HEAD and tag
  race (abandon), the hash-confirmed intent writers (two tabs), the `.gitignore` top-up
  (readers), reader overlap (three
  in-process entry points), the redaction cache (host CLIs), the NetBox inventory refresh
  (a synchronous route bypasses the guard), drift dedupe (Check now overlaps the scheduler),
  and the manifest rename rollback.
- **The approval list is told nothing about another person's decision**: corrected. The
  main page polls the queue every 30 s; template approvals and freshness authorisations
  have no poll.
- **The v2 apply preview never names a holder**: corrected. It names one at preview time;
  what is missing is a live view.
- **Append-only audit files are all safe**: corrected for deploy receipts, which write a
  batch's rows through one buffered handle (R32).
- **The migration marker is "multi-process only"**: corrected to UNSAFE, because two
  applies in ONE process both pass a marker read before the lock and not again inside it.
  It does not affect this host, which already holds the marker (git-15, R35).
- **The trap and NetFlow bind failure is logged by app.py**: corrected. It is logged inside
  each listener thread.
- **Verdicts that contradicted their own evidence**, corrected on review: git-7 (the manifest)
  and intent-6 (every list-repo commit) are UNSAFE, not multi-process only, because an
  in-process writer bypasses the lock (the rename rollback; abandon). locks-9 (the session
  budget) is UNSAFE today through host CLIs. locks-13's v2 gap is single-process, so it is
  UNSAFE. confirms-2 is medium, as R12 says. live-8 is SAFE with Today "no"; its gaps, which
  are today, are R26. stores-15's Today is "partly", because the redaction cache reaches
  today through host CLIs (live-19). The Update request is SAFE in effect, stated once in
  section 3.6.
- **The CLAUDE.md wording was "not applied"**: corrected. The principle was already recorded
  in CLAUDE.md and NSOT_PLAN P.15; section 1 now offers additions to the existing bullet.
