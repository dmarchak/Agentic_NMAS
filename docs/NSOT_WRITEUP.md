# The NSoT conversion: the writeup

This is the writeup of NMAS's conversion into a Network Source of Truth, one
entry per phase and sub-task. [NSOT_WRITEUP_NOTES.md](NSOT_WRITEUP_NOTES.md)
is the notebook it draws on: raw findings, arguments and lessons, written as
they happened. This file is the account built from them.

## How it is kept

**An entry is written in the turn its stage or sub-task closes, while the
detail is still in hand** (the operator's requirement, 2026-09-29). Two
reasons. First, this project has already lost detail to summarisation: the
tenants-versus-regions exchange existed only in a conversation that was later
compressed, and it had to be reconstructed by measuring. Second, an entry
written at close carries the numbers (commits, time, findings, estimate versus
actual) that are hard to recover later, and the forecast corrections are part
of the story.

Every entry has the same parts:

1. **What it was**: the goal, in a paragraph.
2. **How it was implemented**: the design and the main mechanisms, not a
   commit list.
3. **Issues encountered**: the findings it produced, by register ID
   ([OPEN_FINDINGS.md](OPEN_FINDINGS.md)), including those outside its scope.
4. **How they were resolved**: fixed, deferred by decision, or withdrawn, with
   the reason.
5. **Numbers**: commits (with the rule that selected them, so a reader can
   check), elapsed time, findings, estimate versus actual, and the acceptance
   measurement.
6. **Where it left the product**: one sentence.

**A detail that cannot be recovered says so ("Not recoverable: …") and is
never filled in.** Every number carries its source in brackets.

**Closing a stage also checks its forecast against its actuals**, in the
entry, before the next forecast is made (the operator, 2026-09-29): 7.2's
forecast was never checked when it closed, so the next one would have been
built on an unexamined one. And a forecast is made from a finished stage of the
SAME KIND: the 7.1 multiplier, applied to Mode B, was about seven times too
high.

**This file is published once, at the end, as the deliverable** (the operator,
2026-09-29). Until then it lives only here: a published copy would be a second
owner of every fact in it, stale from the next entry on.

**Backfilled entries** (P.1 to P.6, 7.0 to 7.2) were drafted on 2026-09-29
from the plan, the register and the git history, after the fact, and each says
where its sources ran out. They are marked *backfilled*. Entries written at
close are marked *written at close*.

### Conventions

- **Dates and times.** Git records commit times in local time (UTC−6). The
  plan and the register appear to date events in UTC. This is an inference,
  not a recorded convention: three drafts reached it independently from the
  times. For example, the register puts C70's re-run at "23:42–23:45, at
  `d17d650`", and git dates `d17d650` 2026-09-27 17:28 −0600, which is 23:28
  UTC. So an evening event can carry the next day's date in the documents.
  Times below are as each source prints them.
- **Commit hashes.** Every hash cited below was checked against this
  repository on 2026-09-29. Six are not in it: `7fd0ac0`, `2fb07db`,
  `5055fe5`, `c7711d6`, `e1e8e49` and `be60f59`. These are commits in a
  list's `config_repo` on the deployment host (the golden and intent record),
  not in the code. They are cited from the documents that recorded them, and
  not verified here.
- **Commit counts depend on a selection rule**, because several threads often
  shared one window. Each entry states its rule.

## Status of every entry

| Part | Item | State |
|---|---|---|
| Before the P-items | Phases 0, 1, 2, 3a, 3b, 3c; Stage 2; 3.3; 4C; the branch site; Phase 2 (DHCP) | Not yet written in this form. The narrative is in NSOT_WRITEUP_NOTES.md, and the product state at each point is in "Where the product stood" below |
| P-items | P.1 to P.6 | Backfilled below |
| | P.7 (alert rules generated and tested), P.8 (per-list settings) | Decided, not built |
| Stage 7 | 7.0, 7.1, 7.2 | Backfilled below |
| | 7.3 | Open. Closed sub-tasks written below (seed intent, retire, Mode B, C188) |
| | 7.4 to 7.10 | Not started |
| Stage 8, Stage 9 | | Not started |
| Side campaigns | The store-hardening family (C20, C157, C158, C160), the Grafana rule audit (C166 to C168), the verify family (C62 to C68, C108, C114, C115, C178), Mode B's probe measurements | Mode B's measurements are in the 7.3 entry. The others' instances are in "Patterns" below; their own entries are not yet written |

## Part I. Before Stage 7: the P-items

### P.1 — Switch syslog, and a heartbeat that makes silence a signal

*Backfilled 2026-09-29.*

**1. What it was**

The Loki card showed 0 switch log lines during a demo, read as "switch syslog
stopped around 2026-09-09". P.1 was carved out of Stage 5 as a pipeline defect
and scheduled before Stage 7 by the operator's decision, not by dependency
[NSOT_PLAN.md P.1; git 4b72661]. Its acceptance: switch lines queried from
Loki, any device change made through intent, and a signal when a device stops
logging, so the next outage is not found by a count of 0 [NSOT_PLAN.md P.1].

**2. How it was implemented**

Every hop was measured first (device buffer, device send counter, rsyslog
files, Alloy, logrotate, Loki). Nothing had stopped: every device had run
`logging trap critical` since 8 Sep, so almost nothing left the devices. s3's
one severity-2 line, present in Loki, was the positive control [NSOT_PLAN.md
P.1 "MEASURED"]. So P.1 became a decision plus a heartbeat, not a repair.

- **Decided:** trap level `notifications`, set in intent. An EEM applet
  (`event timer watchdog time 300` → syslog `NMAS-HEARTBEAT`). Trap level,
  host, source-interface and heartbeat are ONE template block, whole or absent.
  Onboarding gives every device the block. Grafana rules on Loki are generated
  from the inventory, with NoData = alerting [NSOT_PLAN.md "P.1 DECIDED"].
- **EEM proven first** on a throwaway lab of both platforms (vIOS-L2, C8000v),
  60 s watchdog, polled until three firings [NSOT_PLAN.md; git cff842f].
- **Modelled:** the parser, `_common.j2` and host_vars carry the block. It
  round-trips at 100% on r1 and s1 from device captures. Whole-or-absent is
  enforced where intent is authored, not at extraction [NSOT_PLAN.md "BUILT";
  git cf18ecb].
- **rsyslog** files every message by source address, with no addressing plan
  in the host file (`deploy/rsyslog/10-network-devices.conf`).
- **P.1b bulk intent** (`modules/nsot/bulk_intent.py`, `scripts/nmas-bulk-intent`):
  one compare-and-set change over schema paths, applied to seven devices as one
  commit, `7fd0ac0` [NSOT_PLAN.md P.1b; git 05498fb].
- **Rules** (`scripts/nmas-heartbeat-rules`): one rule per device, anchored on
  the device's own origin-id. Each window is measured from that device's Loki
  arrivals (C16). An hourly `--check` job is watched by `job_health`.
- **Deploy order:** s4, r2, then a batch of six, then s3, then r6, each checked
  before the next. r5 was retired rather than deleted (C11).

**3. Issues encountered**

- C6: a seeded template never learns its source changed; the shipped `_common.j2` reached no network by itself.
- D3: the template editor's confirmations did not say what happened; `_common.j2` could not be opened from the library.
- C9: the vIOS clock runs at about 75% speed (s4: 300.0 s device time = 391–404 s real).
- A4: NetBox records every device's platform as `ios`, written by NMAS's import.
- C10: the batch circuit breaker counts verify failures, not push failures.
- C11: deleting a device left it half-managed in five places; there was no retire.
- C12: P.1 is add-only; the deploy path cannot remove the applet.
- C13: rsyslog names r6 by address, because `/etc/hosts` lists only the original nine.
- C14: `clab-sync.service` failed 72 runs in a row and nothing said so.
- C15: a sanitiser write whose commit failed was stranded, reported as success.
- C16: the per-platform heartbeat window failed three of four switches.
- C17: NMAS's Loki and Grafana integrations were unconfigured on the host.
- C18: r5's retire commit (`3592113`) never pushed; CLI commits exited under their own push.
- C21 (after completion): the query counted any line naming the applet, including its own error.
- Unregistered: the EEM probe's wait loop matched `healthy` inside `unhealthy`; the rule generator read the interval as 0 and wrote 60 s windows; r6 had no logging config (onboarding gave none); the rsyslog filter filed only `10.255.1.` sources; the conf file's name sent the operator to an empty directory; bulk intent's first version reported only the first refusal reason [NSOT_PLAN.md P.1, P.1b].
- Surfaced later: C71 (the test fleet fixtures predate P.1), C151 (a new device has no rule until someone regenerates them).

**4. How they were resolved**

- Fixed: D3, C11 (built; acceptance on r5), C14 at its cause, C15, C16, C18, C21 (anchored on the exact `%HA_EM-\d-LOG` form), and every unregistered item (exact match; interval under 60 refused; onboarding baseline; new rsyslog conf; runbook names the path; all reasons reported) [OPEN_FINDINGS.md Closed].
- Closed on measurement: C17, 2026-09-28 (both URLs found set).
- Closed by decision: C12, the operator, 2026-09-28: accept add-only until Mode B.
- Decided, deferred to Stage 9 (minor): C9 (measure whether NTP can correct it), C13 (key everything on origin-id), C6 (two of six kinds answered), C71.
- Scheduled: C14's surfacing into 7.2; C10 into 7.4; A4 into 7.6. C151 closed in 7.2 step 8.

**5. Numbers**

- **Commits:** 19 by subject. Rule: the subject names P.1 or P.1b, the heartbeat or its window, EEM, or a P.1 step (r5's exit, step 4/5). The list: 4b72661, bfa9752, cff842f, fad2bbb, cf18ecb, 374ac27, 437809f, 050bda4, 03f69bf, 659d050, 05498fb, cab9fcf, 7af138f, 6120900, 4890fcd, 65e17d2, 97dedaf, df79525, 7d65203. Plus 17111e3 for C21 after completion. 4b72661, cff842f and fad2bbb are shared with P.2. The full range 4b72661..7d65203 holds 26 commits, including C6, C14 and C15 work [git log].
- **First and last:** 4b72661, 2026-09-25 10:07 −0600 (P.1 scheduled). 7d65203, 2026-09-25 16:06 −0600 ("P.1 complete").
- **Elapsed:** 5 h 59 min, interleaved with P.2.
- **Findings:** 14 registered IDs in its window (C6, D3, C9, A4, C10–C18, C21), 6 unregistered, 2 more later (C71, C151).
- **Estimate vs actual:** Not recoverable. No time estimate was written (searched NSOT_PLAN.md and NSOT_STAGE7_PLAN.md).
- **Acceptance:** s4's last heartbeat was 21:21:22. Its timer was removed at 21:22:27, and the alert fired at 21:40:00 with the other eight silent. That is 1,118 s after the last heartbeat, between the second and third missed heartbeat. It came 122 s past s4's 996 s window, and that latency is "not measured". Nine rules loaded (750 × 5, 797, 799, 996, 1286). Nine of nine managed devices were heartbeating [NSOT_PLAN.md "P.1 COMPLETE"].

**6. Where it left the product**

Every managed device logs at `notifications` from committed intent. Each sends
a heartbeat whose absence alerts per device, on a window measured from that
device's own clock.

### P.2 — NetBox backup with a tested restore

*Backfilled 2026-09-29.*

**1. What it was**

NetBox was the one store NMAS writes to with no restore path (register A1).
P.2 was scheduled before Stage 7 so that Stage 7 work could be recovered if it
damaged NetBox [NSOT_PLAN.md "What blocks what"]. Scope: a scheduled backup, a
restore tested against a scratch instance, the configuration secrets carried
encrypted, a copy off the host, version checks, and a visible failed or stale
backup [NSOT_PLAN.md P.2].

**2. How it was implemented**

- **Sized first:** netbox-docker, a 30 MB database, empty media volumes
  [NSOT_PLAN.md P.2].
- **`scripts/nmas-netbox-backup`**, hourly: `pg_dump` on an exported snapshot,
  the media volumes, `env/` and `configuration/`, and a manifest. The manifest
  holds image tags, versions, per-table row counts from the same snapshot, and
  a sha256 per file. Hourlies are kept about 26 h, dailies about 15 days
  [NETBOX_BACKUP.md].
- **`scripts/nmas-netbox-restore-test`** restores the newest backup into a
  scratch postgres. It compares every table's row count with the manifest,
  because the census alone would pass a restore that lost field values.
- **Encryption:** everything leaving the VM is gpg-encrypted to a public key.
  The env file holds the API token pepper, so it must travel with the dump,
  and so nothing goes to git.
- **Proxmox:** a push account restricted by `rrsync -wo`, forced in two places
  (the key's `command=` and a `ForceCommand` block). The runbook explains why
  these are two ways to lose one restriction, not two layers [NETBOX_BACKUP.md 2c].
- **Off-box:** dailies go to B2 via rclone. Each push is confirmed by listing
  the object at its exact size (C22).
- **Status:** `--status` names an unconfigured destination. A failed or stale
  restore test fails it.
- **Scope decision (the operator):** B5 (key escrow) and B6 (VM images) were
  done before P.2's steps [NSOT_PLAN.md P.2].

**3. Issues encountered**

- A1: nothing backed up NetBox (the item itself).
- B4: NetBox's env files were world-readable (0664).
- B5: `data/key.key` was a single copy.
- B6: no VM on the Proxmox host was imaged (`/etc/pve/jobs.cfg` did not exist).
- B7 (found on B6): the thin-provisioned pool's real allocation was not watched.
- B8: the backups' decryption key existed only on the operator's laptop.
- B9: the "write-only" B2 key could HIDE files, and the lifecycle deletes hidden versions a day later.
- B10: nothing checks that lock retention covers the lifecycle window.
- C22: rclone exited 0 after ten refused `401` retries; the push trusted exit codes.
- C19 (same commit, wider scope): secret stores the checker could not see. It now declares rclone.conf, the NetBox env files and the push key.
- Unregistered: the first live restore test failed because `docker exec` lacked `-i`, which the mocked seam could not show. `--status` exited 0 beside that FAIL. The push needed `--no-check-dest`. The claim "the B2 key cannot delete" was made (git c830467) and withdrawn (git a5b85ea). B9's lock retention was first written as 15 days, a day short [NETBOX_BACKUP.md; OPEN_FINDINGS.md B9].
- Later: C106 (4), 2026-09-27: the prune ran before the ship and by age alone, so a failed run left fewer backups. C144 and C145, 2026-09-28: the restore test never covered the encrypted copies; the key export would not import.

**4. How they were resolved**

- Closed on evidence: A1 (2026-09-26). B4 (chmod 600 by the operator; the backup writes 0600 regardless). B5 (escrowed in the break-glass record; a restored clone's key fingerprint matched). B6 (nightly vzdump to a separate disk, restore tested). B8 (2026-09-28: gpg-agent's key files copied to Proxmox, proven by an empty-keyring decrypt of a real B2 backup).
- Fixed: B7 (job_health watches the pool), C22 (confirm by listing), C19, C106 (4) (ship first, prune only what shipped), and every unregistered item.
- Deferred to Stage 9 by the operator's 2026-09-28 split: B9 as hardening. Its row says Object Lock is enabled "by the operator's account; not re-measured". B10 and C145 as minor.
- C144: the honesty half is done (the job-health row says the test covers the plain local copy only). A row for "last proven readable" is deferred to Stage 9.

**5. Numbers**

- **Commits:** 15 by subject (the subject names P.2, A1, B4, B8, B9/B10, the B2 key or off-box): 4b72661, bfa9752, cff842f, fad2bbb, 8cd2c2e, c830467, f15399f, 413c5c7, 363ccf1, a5b85ea, 8ffb840, fa7359d, 4ba1b50, 980a76e, 1a369ce.
- **Prerequisite commits (B5/B6/B7):** 8 more: 56121d9, 940396e, 51bbca5, c324792, 17111e3, 3ac6a9d, 4b3a624, bc6d20b.
- **Follow-ups:** bb1b6ce, 2c2abf5, 74d3d67.
- **Shared commits:** four are shared with P.1 (4b72661, bfa9752, cff842f, fad2bbb), and 17111e3 is shared with C21.
- **First and last:** 4b72661, 2026-09-25 10:07 −0600. 1a369ce, 2026-09-25 20:53 −0600 ("A1 closed").
- **Elapsed:** 10 h 46 min to A1's closure, and 2 d 14 h 34 min to B8's closure (74d3d67, 2026-09-28 00:41 −0600).
- **Findings:** 10 registered IDs in the window, 5 unregistered, and 3 later IDs.
- **Estimate vs actual:** Not recoverable. No time estimate was written.
- **Acceptance:** backup 3.4 s, 198 tables, 3,142 rows, dump 1.29 MB (first run). The installed restore test ran PASS, 198 tables and 3,143 rows identical, in 20 s. Three copies of 363,799 bytes. The NMAS answers `No secret key`, and the laptop decrypted the B2 copy. A broken Proxmox target read `failing` in `nmas-jobs` and recovered to `ok` [NETBOX_BACKUP.md; NSOT_PLAN.md "P.2 ACCEPTANCE STATUS"].
- **Recorded as not met:** the unattended twice-in-a-row watch (PENDING), the rrsync refusal half (not reported), and `--status` exit 0 (not reported).

**6. Where it left the product**

NetBox is backed up hourly with a restore tested nightly. Encrypted copies sit
on Proxmox and B2, readable only with a key that now has a proven second copy.

#### Sources read (P.1, P.2)

- docs/NSOT_PLAN.md: "Scope of what remains", "What blocks what", P.1 (measured, decided, built, steps, COMPLETE), P.1b, P.2 (sizing, acceptance, acceptance status, what has a copy).
- docs/OPEN_FINDINGS.md: rows A1, A4, B4–B10, C6, C9–C19, C21, C22, C71, C106, C144, C145, C151, D3; the 2026-09-28 re-triage legend.
- docs/NETBOX_BACKUP.md: header, sections 1, 2c, 4, 5, 6f, 6g, "What this does not give".
- CLAUDE.md (P.1/P.2 paragraphs); modules/job_health.py (restore-test row wording).
- git: `git log --date=iso` over 2026-09-24 to 2026-09-27; `--grep` on P.1/P.2/heartbeat/backup terms; `--name-only` for bfa9752^..1a369ce; `-S` for each register ID's first appearance; messages of c830467, 7d65203, bb1b6ce.
- docs/NSOT_WRITEUP_NOTES.md was searched and holds no P.1/P.2 material.

#### Could not recover (P.1, P.2)

- A time estimate for either item. None is written in NSOT_PLAN.md or NSOT_STAGE7_PLAN.md.
- Whether the operator regenerated and reinstalled the heartbeat rules after C21's fix (its row names this as an operator step, and no later record says it was done).
- Whether P.2's three unmet acceptance items (the unattended watch, the rrsync refusal half, `--status` exit 0) were ever observed. No later record was found.
- Whether B9's Object Lock is enabled as measured. The register records it only "by the operator's account; not re-measured".
- Whether NMAS's NetBox API token is v1 or v2. The plan records it as "not measured".
- The alert detection latency beyond the window (122 s). The plan states it is not measured.
- A single exact commit count for either item: commits interleave (P.1, P.2, B5/B6, C6, C14/C15 on one day). The counts above follow stated subject rules.

### P.3 — Every path that changes a device is guarded or gone

*Backfilled 2026-09-29.*

**1. What it was**

B12 found that of 19 mutating routes that reach a device, one checked identity, while CLAUDE.md said all did [NSOT_PLAN.md P.3]. Stage 7 would move these controls, and must not re-home a control whose guard does not exist. So P.3 made one statement true and mechanical: every route or socket event that can change a device, a secret, or the tool's gates either requires a person, or is removed [NSOT_PLAN.md P.3]. Scope: B12, B11, D5, D4, C23, the audit's direct-push cuts, the terminal's audit trail, and the agent's push, commit and self-modification tools. Decided by the operator on 2026-09-26 [NSOT_PLAN.md P.3].

**2. How it was implemented**

A step 0 came first: the operator rotated the Anthropic key, since B11 had exposed it for the route's whole life (since `e729267`, 2026-04-12), and then revoked the earlier keys (B17) [NSOT_PLAN.md P.3].

1. One gate table, `modules/route_gates.py`: every mutating endpoint and terminal event declared with a kind (`confirm`, `approve`, `reveal`, `publish_remote`, new `configure` and `break_glass`) or `not_device` with a reason. A `before_request` hook enforces it before input validation; an undeclared endpoint is refused and fails the suite. Routes record the verified actor [step 1].
2. Eight direct-push routes removed (404), with their UI. `/bulk_execute` refuses config mode by name (400); `/ai/chat` refuses `run_playbook_id` (410). Configure's Apply became "Check this form", which sends nothing [step 2].
3. D5: both "Restore Golden Config" buttons open the guarded restore preview at HEAD; both replay routes removed [step 3].
4. D4: the deploy wizard draws the program, one authorise box per dangerous line (re-plans so the hash covers it), and the attribution split; restore can authorise too [step 4].
5. C23: the inventory-population rule moved into `build_targets()`, which preview and apply both call; `restore.coverage()` gives the denominator; `plan_restore()` deleted [step 5].
6. B11: secrets are write-only (`*_set` flags); an empty secret field saves nothing; a sweep of 86 argument-free GETs with planted secrets [step 6].
7. Terminal audit: `data/terminal_audit.jsonl` (0600) records opened, open_failed, closed and refused; never keystrokes [step 7].
8. Agent: 73 tools became 49; 24 removed from list and dispatch; the three `execute_*` tools allow only read-only verbs; auto-continue removed [step 8].
9. CLAUDE.md states the enforced gate with its measurements and its limits [step 9].
10. D10: `Actor-Verified: access | host-shell | none`, written in one place, `repo.git()` [step 10].
11. B14: one stored copy of a credential; `scripts/nmas-credential-dedupe` for stored rows [step 11].
12. B15/B2: a rotation succeeds only on the checker's SAFE verdict (`startup_safety()`), leads with the danger, and records every exit in `data/rotation_audit.jsonl` [step 12].

**3. Issues encountered**

Scoped: B12, B11, D5, D4, C23 [NSOT_PLAN.md P.3]. Pre-existing and closed here: B2 [OPEN_FINDINGS.md B2]; D6 (`/configure/apply`'s docstring promised guards its body lacked) [OPEN_FINDINGS.md D6].

Found during P.3. The writeup counts eleven unscoped findings: B13, B14, B15, B16, C24, C27, C28, C29, C31, D10, D12 [NSOT_WRITEUP_NOTES.md "What P.3 cost and bought"]. Also registered in P.3 commits: C25, C26, D9, C30, B17 [git log -S on OPEN_FINDINGS.md].

- B13: opening the terminal through the tunnel to verify step 1 put 27 of s1's 32 password characters on screen; the rotation that would retire it refused (`not_already_type_9`) [OPEN_FINDINGS.md B13; NSOT_PLAN.md P.3].
- B14: every device stored its login password twice [OPEN_FINDINGS.md B14].
- B15: s1's rotation completed on the device and store, and the boot file kept the exposed password [OPEN_FINDINGS.md B15].
- B16: `/run_command/<ip>` ran any exec-mode command from an ungated GET; the gate table was keyed on HTTP method [OPEN_FINDINGS.md B16].
- B17: keys before the rotated one may still have been valid [OPEN_FINDINGS.md B17].
- C24: `/deploy/apply` silently dropped a confirmed device whose artifact could not be built [OPEN_FINDINGS.md C24].
- C25: one device without a manifest identity makes Save All commit nothing [OPEN_FINDINGS.md C25].
- C26: the suite wrote into the app log of the checkout it ran in [OPEN_FINDINGS.md C26].
- C27: the restore preview's confirm never showed the lines to be added [OPEN_FINDINGS.md C27].
- C28: after the 2026-09-23 erasure, nothing re-checked which guard-gating settings were empty on this install [OPEN_FINDINGS.md C28].
- C29: every HTTP error except 404 went out as a 500 [OPEN_FINDINGS.md C29].
- C30: the agent's prompt names 24 removed tools, 77 times [OPEN_FINDINGS.md C30].
- C31: `yang_push_script` empty with a dead script; "nothing to set" read like "somebody forgot" [OPEN_FINDINGS.md C31].
- D9: a freshness authorisation had no path a person can use [OPEN_FINDINGS.md D9].
- D10: every `Actor:` trailer before P.3 is a claim; 5 of 92 commits carried a verified identity [OPEN_FINDINGS.md D10].
- D12: a device's terminal was one shell shared by everyone who opened it [OPEN_FINDINGS.md D12].
- No ID: `dangerous`/`authorised` are stripped strings while `commands` keeps indentation, so exact comparison never marked a line [NSOT_PLAN.md P.3 step 4].
- No ID: acceptance item 1's floor (131) was stale after the cuts; the population was 121 [NSOT_PLAN.md P.3 acceptance].

**4. How they were resolved**

- B12, B11, D5, D4, C23: fixed in steps 1/9, 6, 3, 4 and 5 [OPEN_FINDINGS.md].
- B2, B15: fixed, step 12 [OPEN_FINDINGS.md B2, B15].
- B13: fixed out of sequence (`abea5ca`, `0ca267e`: send, read, decide; preflight fix); closed on two measured conditions: s1 rotated (`e1e8e49`, ACCEPTED) and break-glass record replaced. Stage-level evidence unrecoverable (a lost scrollback) [OPEN_FINDINGS.md B13].
- B14: code fixed (step 11); running the dedupe on the host was left as the operator's step [OPEN_FINDINGS.md B14]. Not recoverable whether it ran: no record found.
- B16: fixed; now a gated POST [OPEN_FINDINGS.md B16].
- B17: closed by the operator; revoked at Anthropic [OPEN_FINDINGS.md B17].
- C24, C27: fixed in steps 4 and 3 [OPEN_FINDINGS.md].
- C25: deferred to 7.4 (latent: 9 of 9 devices have an identity) [OPEN_FINDINGS.md C25].
- C26: fixed; conftest detaches the handler [OPEN_FINDINGS.md C26].
- C28: fixed as a job, `job_health.settings_rows()` [OPEN_FINDINGS.md C28].
- C29: fixed; HTTP errors keep their status [OPEN_FINDINGS.md C29].
- C30: deferred to Stage 8.5, the prompt rewrite [OPEN_FINDINGS.md C30].
- C31: decided and built (`settings_not_applicable`) [OPEN_FINDINGS.md C31].
- D6: the route was removed in `863d103` [git log -S '/configure/apply' -- app.py]; the register row still sits in an open section pointing at P.3 step 2 [OPEN_FINDINGS.md D6].
- D9: deferred to Stage 7.6 (latent) [OPEN_FINDINGS.md D9].
- D10: trailer built in step 10; the count and marks deferred to 7.5 [OPEN_FINDINGS.md D10].
- D12: decided by the operator: per-connection shells, built (`e6d31ec`) [OPEN_FINDINGS.md D12]. The terminal was later decided to be removed entirely (2026-09-27) [NSOT_FEATURE_AUDIT.md 3b].
- The unnumbered two: renderers compare trimmed text; the floor set to 121 and the correction stated [NSOT_PLAN.md P.3].

**5. Numbers**

- Commits: 20. Rule: every commit from `c5a34c1` (the first "P.3 step" commit) to `690fa90` ("P.3 complete") inclusive, 21 in all, minus `955d6ee` (authorization design, not P.3). 15 of the 20 name P.3 in the subject; the other five are B13 (3), C28 and D12 fixes inside the window [git log c5a34c1^..690fa90]. The plan text itself was `e437b4e` (2026-09-25 22:04), not counted.
- First: `c5a34c1`, 2026-09-25 22:34:32 -0600. Last build step: `5b087c4`, 2026-09-26 01:57:36 -0600. Accepted: `8401b88`, 12:03:56. Complete: `690fa90`, 2026-09-26 12:15:31 -0600 [git].
- Elapsed: 3 h 23 min for the twelve steps; 13 h 41 min to "complete", including an overnight gap before the acceptance run [computed from git dates].
- Estimate versus actual: Not recoverable: no estimate for P.3 was found in NSOT_PLAN.md, NSOT_STAGE7_PLAN.md or the writeup notes.
- Findings: 11 unscoped per the writeup; 16 new register IDs in the list above; 2 unnumbered.
- Suite: 3781 passed at step 1 [NSOT_PLAN.md step 1] to 3950 passed, 0 failed, 0 errors at `5b087c4` [NSOT_PLAN.md P.3].
- 55 definitions removed or moved, none still called [NSOT_PLAN.md acceptance table].
- Acceptance, at `5b087c4`: 121 mutating endpoints classified; all 87 gated endpoints answer 403 with no identity and no view reached; 206 targeted tests passed before and after eleven controls, each failing its targeted test [NSOT_PLAN.md P.3 acceptance run]. On the host at `9c4cf07`: 403 `no_header` on `/deploy/apply`, `/golden/restore/apply`, `/ai/approvals/<id>/approve` (400, 400 and 404 before) [OPEN_FINDINGS.md B12]. Through the tunnel: `c7711d6` and `2fb07db` carry `Actor-Verified: access` [NSOT_WRITEUP_NOTES.md].
- The terminal: an unauthenticated socket was refused and recorded [step 9]; a person opening it through the tunnel was "NOT REPORTED" [step 1].

**6. Where it left the product**

Every route and socket event that can change a device, a secret or a gate now needs a verified person or is gone, enforced by one table and measured over all 87 gated endpoints.

### P.4 — Cut Jenkins; GitHub Actions CI; nmas-deploy gating

*Backfilled 2026-09-29.*

**1. What it was**

Decided by the operator on 2026-09-26: remove Jenkins before Stage 7, so Stage 7 does not draw a tab it is about to delete [NSOT_PLAN.md P.4]. The design audit found nothing was configured and "no working path depends on it": `jenkins_url` empty, the `Jenkinsfile` could not run, the webhook accepted forged SUCCESS posts, and the deploy's `ci_gate` check 4 was fail-open and keyed on the active list [NSOT_CI.md §0]. The goals: remove Jenkins and its 19 agent tools; make `ci_gate` say what it checks; run repo CI on GitHub Actions; make `nmas-deploy` refuse a commit whose CI failed or is pending, with `--offline` for an air gap; version `nmas-deploy` in the repo [NSOT_PLAN.md P.4; NSOT_CI.md §6].

**2. How it was implemented**

- **Step 1a, app surface:** the tab, wizard, settings section, workflow switches and 14 routes (6 mutating, so the gate table's floor went from 121 to 115); Save All's validation pipeline; `event_monitor`'s sync; `agent_runner`'s Jenkins task; unused decrypted credentials in `PipelineContext` [NSOT_PLAN.md P.4].
- **Step 1b, agent:** the 19 CI tools (tool list 49 to 30) and the prompt's Jenkins section [NSOT_PLAN.md P.4].
- **Step 1c, modules:** `jenkins_runner`, `check_runner`, `jenkins_shell`, `pipeline_builder`, the `Jenkinsfile` and `configure.py`'s generators deleted. Settings keys stay (keys are never deleted); `data/jenkins_checks.json` is a retired store the secret checker names until deleted [NSOT_PLAN.md P.4].
- **Step 2:** `_stage_ci_gate` is a local dangerous-command check and says so [NSOT_PLAN.md P.4].
- **Step 3:** `.github/workflows/ci.yml` installs `requirements.lock` with `--no-deps` (the host's exact set); coverage reported, never gated. Built on branch `p4-ci`, merged after green [NSOT_PLAN.md P.4; git branch -a]. Why GitHub Actions and not Jenkins: the NMAS already has an executor with history (systemd timers plus `job_health`); Actions needs no server; air-gapped installs run the suite locally [NSOT_CI.md §3].
- **Step 4:** `scripts/nmas-deploy`, versioned (it had been 25 lines of bash on the host only). It gates on the target commit before HEAD moves; exits 0 to 5; "no run" is never a pass except a docs-only change matching the workflow's own `paths-ignore`; every run is a row in `data/deploy_audit.jsonl` [NSOT_PLAN.md P.4]. Two refinements after the operator's first live run: `GET /health` reports the commit the running process loaded, and the restart is confirmed by identity (MainPID changed, `/health` answers from it, target loaded), not by time; `paths-ignore` is read from the last green commit, and a workflow change is never ignorable [NSOT_PLAN.md P.4; git 3b5c6df, 1319890].

**3. Issues encountered**

- C40: CI run 1 failed at install; the host's package set is not pip-resolvable (netmiko 4.3.0 with textfsm 1.1.2), and Ubuntu ships packages with no dependency metadata [OPEN_FINDINGS.md C40; git a2c83d6].
- C42: the operator's `--offline` control run failed a test on the host that CI passed; the host's ext4 1 ms timestamp tick [OPEN_FINDINGS.md C42].
- C43: a test errored when its file ran alone [OPEN_FINDINGS.md C43; registered in c923a26].
- C44 (the operator's): a manual `git pull` bypasses the deploy gate and systemd loads it at the next restart [OPEN_FINDINGS.md C44].
- C45 (the operator's): the suite takes about 5 minutes on the host [OPEN_FINDINGS.md C45].
- C46: a test asked the live NMAS for its map on every host run [OPEN_FINDINGS.md C46].
- C32, C33, C34, C35, C36, C37: found by running the suite from a pristine checkout for the first time (5 failed, 19 errors) [git d0d696c]. The commit does not say P.4 prompted it; it sits in P.4's window. C39 (the repository is public) and C41 were also registered in the window [git b20a5c9, aebc613].
- C30 extended: 17 scattered CI-tool mentions remain in prompts [OPEN_FINDINGS.md C30].
- No ID: "deployed" was recorded with from == to, and a 200 from `/` would pass a process that never restarted [git 3b5c6df].
- No ID: `/health`'s psutil start time read 0.66 s before systemd's start [git 1319890].
- No ID: `paths-ignore` read from the target would let a commit widen it and wave itself through [git 1319890].
- No ID: the first red commit `003a93d` got no CI run, because its message contained GitHub's skip directive [git 7be2c93].
- No ID: `--offline` tested a `git archive` with no `.git`, so it could not pass on any commit; its exit 3 on the red commit was right for the wrong reason [git 7502759].

**4. How they were resolved**

- C40: install the lock `--no-deps`; the lock regenerated on the host from Python and dpkg metadata, 54 to 64 pins [git a2c83d6]. Dropping stale pins and `openai`/`groq` decided by the operator 2026-09-27, minor [OPEN_FINDINGS.md C40].
- C42: the control fixed (backdated, simulated ext4); the kernel gap accepted by the operator and the row closed 2026-09-28 [OPEN_FINDINGS.md C42].
- C43, C46, C32, C34, C36: fixed [OPEN_FINDINGS.md]. C35 settled as a pin defect, closed by the lock (C37) [OPEN_FINDINGS.md C35, C37].
- C44: deferred by the operator's decision 2026-09-27: a deploy clone only `nmas-deploy` moves, Stage 6 [OPEN_FINDINGS.md C44].
- C45: measured; the operator approved the fixes, built in `5eef2df` (store initialised once, xdist in CI) [OPEN_FINDINGS.md C45; git 5eef2df].
- C33: deferred, each route as it is rebuilt [OPEN_FINDINGS.md C33].
- C39: deferred for the lab by the operator (Stage 9) [OPEN_FINDINGS.md C39].
- C30: deferred to Stage 8.5 [OPEN_FINDINGS.md C30].
- The unnumbered items: fixed in `3b5c6df`, `1319890` and `7502759`; the skip-directive case was used as the no-run test and a second red commit `7be2c93` made [git].
- After P.4 closed, the gate itself produced more: C106 (refuse before moving what cannot finish), C124 (a cancelled run read as the verdict; caused C44's first real bypass), C142, C170, and `--wait` [OPEN_FINDINGS.md; git 76d0f7a, 4f92b96, 995498a, bad759a, 70e0ca4].

**5. Numbers**

- Commits: 13. Rule: in `d25e3ff^..f29d402` (25 commits), those whose subject names P.4, `nmas-deploy`, `/health` or a CI run: `d25e3ff`, `ca9842a`, `721933a`, `0999659`, `a2c83d6`, `700d8bb`, `3b5c6df`, `dc7c7b0`, `1319890`, `003a93d`, `7be2c93`, `7502759`, `f29d402` [git]. The other 12 are harness and finding commits; the boundary is a judgement.
- First: `d25e3ff`, 2026-09-26 12:28:08 -0600. Last: `f29d402`, 2026-09-26 16:53:27 -0600. Elapsed 4 h 25 min [git].
- Estimate versus actual: Not recoverable: no estimate for P.4 was found.
- Findings: 6 register IDs attributable to the CI and deploy work (C40, C42 to C46), plus 5 unnumbered; 8 more registered in the window with a weaker link.
- Removed: 146 definitions gone, none still called (`d25e3ff^..HEAD`) [NSOT_PLAN.md P.4 acceptance 1].
- Suite: 3950 at P.3's end to 4020 passed, 0 failed, 0 errors at `f29d402` [git f29d402].
- Acceptance (NSOT_CI.md §7): 1 MET; 2 MET; 3 MET with operands: pending and failed exit 1 on `7be2c93`; code with no run exit 2 on `003a93d`; docs-only exit 0 (`1319890 -> 13a5011`); green deploy `13a5011 -> 5eef2df`, pid 268370 -> 361070; `--offline` red `5055fe5` exit 3, "1 failed, 4004 passed in 287.81s" [NSOT_PLAN.md P.4]. 4 NOT YET OBSERVED; 5 not applicable yet; 6 carried by Stage 7 [NSOT_PLAN.md P.4]. Not recoverable: any later observation of item 4; none was found.
- Undecided inside P.4: scheduled protocol regression (N13) and config-repo checks (R5-R10) [NSOT_PLAN.md P.4].
- Later measurement: over ~28 h, 90 push runs, median 201 s push to green; 35 deploys refused while CI ran; the operator kept the gate and added `--wait` [NSOT_CI.md "CI's cost"].

**6. Where it left the product**

Jenkins is gone, and the host moves only to a commit GitHub Actions passed, confirmed by the identity of the restarted process.

#### Sources read (P.3, P.4)

- docs/NSOT_PLAN.md: P.3 (steps 1-12, acceptance, acceptance run) and P.4 (steps, acceptance)
- docs/OPEN_FINDINGS.md: rows B2, B11-B17, C1, C23-C46, C106, C124, C142, C170, D6, D9, D10, D12
- docs/NSOT_CI.md: §0, §3-§7, "CI's cost, measured"
- docs/NSOT_FEATURE_AUDIT.md: §0, §7 (decisions 2, 3, 3b)
- docs/NSOT_WRITEUP_NOTES.md: "What P.3 cost and bought"
- CLAUDE.md
- git: `git log --format='%h %ad %s' --date=iso` for 2026-09-25 to 2026-09-27; full messages of d0d696c, a2c83d6, b20a5c9, c923a26, 7502759, eb70788, 003a93d, 7be2c93, f29d402, 1319890, 3b5c6df; `git log -S` on OPEN_FINDINGS.md for each ID's first commit; `git log -S '/configure/apply' -- app.py`; `git branch -a`

#### Could not recover (P.3, P.4)

- An estimate for P.3 or P.4: none found in the plan documents.
- B13's stage-level evidence: the rotation CLI's output was in a terminal scrollback that no longer exists [OPEN_FINDINGS.md B13].
- Whether the operator ran `nmas-credential-dedupe` on the host (B14) and deleted `data/jenkins_checks.json` (P.4): both are recorded as the operator's steps, and no record of either being done was found.
- P.4 acceptance item 4: recorded NOT YET OBSERVED; no later observation found.
- Whether P.4 prompted the pristine-checkout run behind C32-C37: the commit (`d0d696c`) does not say.
- Exact commit boundaries: both selections are rules stated above, not a recorded list.

### P.5 — Template approval, scheme 3 (D11, D2)

*Backfilled 2026-09-29.*

**1. What it was**

Template approval under scheme 2 bound an approval to the template AND to the set
of devices bound to it. So approval was all-or-nothing per platform: one device
the template could not reproduce blocked deploys to every other device on its
platform, and every device that joined the set revoked the approval for all
[OPEN_FINDINGS.md D11; NSOT_FEATURE_AUDIT.md 8c]. P.5 made an approval a claim
about the template only: its closure hash and the person who approved it.
Per-device fidelity stays where it already ran, per plan [NSOT_PLAN.md P.5].

**2. How it was implemented**

- The premise was measured before any change. `RenderArtifact.template_report`
  is computed on every plan, from the capture's own parse, and
  `blocking_reasons` already refused a device with missing, invented or
  reordered lines, whatever approval said. So a device the template could not
  reproduce was already blocked alone, and the device-set half of scheme 2
  repeated that check as a property of the inventory [git 61b98a2].
- `approval.template_fingerprint()` is the hash of the template's whole import
  closure, with no device in it. Editing the template, or any macro file it
  imports, still revokes every approval over it [git 61b98a2].
- `approve()` needs at least one bound device to round-trip, not all of them.
  It records every device's result as evidence: validated; failed, with the
  reason; or not validated, for want of a capture [git 61b98a2].
- A scheme-2 record is not honoured silently. Moving to scheme 3 is an explicit
  re-approval [NSOT_PLAN.md P.5].
- The operator's addition: the badge states what an approval covers AND what it
  does not. `approval_status()` carries `covers` and `does_not_cover`, and the
  template library draws both, with the evidence and the approver
  [NSOT_PLAN.md P.5].
- The approve route records a bound device with no capture as "not validated"
  instead of answering 400. `nsot_reapprove_templates.py` does the same, and
  records the OS user as the actor instead of the literal "operator"
  [git 61b98a2].
- The deploy plan stopped building a full artifact for every bound device on
  every plan. That work fed a fingerprint that no longer reads devices
  [NSOT_PLAN.md P.5].

**3. Issues encountered**

- **D11**: approval was all-or-nothing per platform, and its device-set half
  duplicated the per-device gate. Registered 2026-09-25 [git 863d103].
- **D2**: whether a never-reached device should bind to a template was
  undecided, because binding took its platform's deploy path offline. First
  confirmed from the code on 2026-09-23: onboarding revoked the platform's
  approval at Create, not at Verify [git b3c40cf]. Registered with the
  register's creation [git da4d479].
- **Ten tests pinned scheme 2 as correct**, and the D2 tests pinned the
  revocation [git 61b98a2].
- **The migration refuses every deploy until a person re-approves.** Observed on
  the host after deploying P.5: every deploy refused until the operator
  re-approved both templates, with all nine devices round-tripping [CLAUDE.md,
  "Approval is the TEMPLATE"; git 8ff6698].
- **The concept table still described scheme 2.** The Stage 7 concept
  `approval-binds-a-set` asked the screen to state something false after P.5.
  No register ID [NSOT_STAGE7_PLAN.md, concept table].

**4. How they were resolved**

- **D11**: fixed by scheme 3, as above. Closed in the register [git 61b98a2].
- **D2**: resolved by scheme 3. A pending device is still bound, but no device
  is in the fingerprint, so onboarding revokes nothing. The approve route
  records a device with no capture as not validated [OPEN_FINDINGS.md D2].
- **The scheme-2 pins**: rewritten as scheme-3 claims; the D2 pins flipped, with
  the reason [git 61b98a2].
- **The migration refusal**: kept, by design. The operator's reading: an older
  fingerprint answered a different question, so honouring it would be a gate
  that passes because nobody migrated it [CLAUDE.md]. The re-approval was the
  operator's step [git 61b98a2, Not-Done trailer].
- **The concept**: renamed to `approval-binds-the-template` [NSOT_STAGE7_PLAN.md;
  git 91c81fd].

Five negative controls, run confined, each failed its target: every device
required again; the device set back in the fingerprint; a scheme-2 record
honoured; the badge without what it does not cover; the route refusing a device
with no capture [git 61b98a2].

**5. Numbers**

- **Commits**: 2 [git 61b98a2, 2026-09-26 17:16:52; git 8ff6698, 2026-09-26
  17:26:57]. Rule: commits whose subject names P.5 or the scheme-3 migration.
  The decision trail is 3 more commits and is not counted as build: D11
  registered [git 863d103, 2026-09-25 23:08:14]; the P.5 plan section, placement
  proposed [git 303f6c6, 2026-09-26 00:02:08]; placement approved
  [git 0ca267e, 2026-09-26 00:18:42].
- **Elapsed**: from D11's registration to the build commit, about 18 hours of
  wall time [git 863d103 → 61b98a2]. Not recoverable: working time on the
  build. The build is one commit, and the previous commit, 9 minutes earlier, is
  unrelated P.4 work [git f1bcb28].
- **Scale of change**: 13 files, 485 insertions, 412 deletions [git 61b98a2].
- **Findings**: 2 register rows closed (D2, D11). Register open count after:
  34 [git 61b98a2].
- **Estimate versus actual**: none recorded for P.5.
- **Acceptance**: full suite 4038 passed, 0 failed, 0 errors, confined on 4
  workers in 24 s and plain in 60 s [git 61b98a2]. Five controls fired, as
  above. On the host, deploys refused until re-approval, then passed with all
  nine devices round-tripping [CLAUDE.md]. The re-approval commit, `be60f59`, is in the list's `config_repo` on the host,
  not in the code repository, so it is cited from CLAUDE.md and not verified here.

**6. Where it left the product**

An approval now claims only that a person approved this template text, and a
device the template cannot reproduce is blocked alone at its own plan.

### P.6 — ZTP as a third address source (Lab 8)

*Backfilled 2026-09-29.*

**1. What it was**

Zero-touch provisioning of one new device, as a third onboarding address source
beside `static` and `dhcp`. A device boots with no configuration, gets an
address the tool reserved for it, fetches its bootstrap config from the tool,
and is then reached and finished by the unchanged phase 2. It covered course
Lab 8, and it measured ZTP's states on a throwaway, `bp-ztp-a`, before Stage 7
would draw them [NSOT_PLAN.md P.6; P6_ZTP.md §0, §6].

**2. How it was implemented**

The host was measured first: Kea 2.4.1 had no `reservation-*` commands, its
config file could not be written back by Kea, and nothing served TFTP
[P6_ZTP.md §1]. Six decisions followed. Their D-numbers are local to
P6_ZTP.md, not register IDs.

- **D1**: the ZTP subnet takes its reservations from an include fragment the
  tool owns. The writer (`modules/nsot/ztp.py`) takes a set of devices and
  returns per-device outcomes. It refuses conflicts and D4 hits, tests the
  candidate with `kea-dhcp4 -t`, swaps it in by rename, reloads, restores on
  failure, and reads back from the running server [git 1b7e639].
- **D2, D5, D6**: a read-only TFTP responder in the tool
  (`modules/nsot/ztp_responder.py`), with no write path. A systemd socket
  binds port 69, so the process holds no capability. It renders per request,
  keeps no copy, and serves only a pending ZTP device, at its reserved
  address, the file option 67 names, after writing a reveal row
  [git 7416cbf; P6_ZTP.md D2, D5, D6].
- **D3**: the server address is derived from Kea's serving interface, never
  read from a setting [P6_ZTP.md D3].
- **D4**: a reservation never carries a route or a resolver, enforced as a
  check at plan time and as a job-health row [P6_ZTP.md D4].

`ztp` became a stated source in `build_plan()`, with the reservation last among
phase 1's fallible steps [git 8ae4faa]. The pending row derives ZTP stages from
Kea and the responder's audit rows [git 4095240]. Abandon removes the
reservation first [git ba2e23f].

**3. Issues encountered**

Measurements [P6_ZTP.md §8; P6_ZTP_PROBE.md]:

- **M1 (2 runs).** The image's install overlay held a saved startup config, so
  removing vrnetlab's day-0 ISO was not enough. PnP defers to any startup
  config. After an erase, qemu's network answered Gi1 first, and AutoInstall
  stopped at that first lease. Unpredicted: PnP sent Cisco a HELLO carrying
  the device's UDI.
- **M2** had no separate run; M1 and M3 answered its questions.
- **M5 (1 run).** The include is live, and a `config-set`-only reservation
  vanishes at a restart.
- **M3 (2 runs).** Run 1 measured the old launch script, through a stale bind.
  Run 2 held: Kea's reservation answered and the node asked for exactly the
  named file by TFTP. It also broadcast DNS queries for `tools.cisco.com`
  (8 sent, 0 replies).
- **M4 (3 boots).** Boot 1: the responder crashed on systemd's dual-stack
  socket, hiding a second defect (the peer matched no reservation), and
  AutoInstall gave up after about 2.5 minutes. Boot 2: the config applied, but
  SSH was refused because no RSA key was generated, and the GUI overwrote
  Verify's diagnosis. Boot 3: phase 2 promoted with a 200 while the device
  had no startup config.

Register rows:

- **C48**: `tftp_server_ip` names an address the host lacks.
- **C49**: a reservation could vanish at Kea's restart.
- **C50**: an unknown lab name resolves to rcn-lab1's paths, silently.
- **C51**: a GET with a list name created that list [git 23f3fb6].
- **C52**: a ZTP render used the weaker `password 0` form.
- **C53**: the CLI rotation never saved the device; `s1`'s NVRAM booted the
  credential B13 exposed [git d91f494].
- **C54**: job health kept a rotation row for a departed device.
- **C57**: the persist step had never run in a real onboarding
  [git dc3dec8, registered just after].

Without an ID: Kea's AppArmor profile held a root `kea-dhcp4 -t` to the file's
mode bits [P6_ZTP_PROBE.md, D1]; `RESERVED_INTERFACES` is keyed on the platform
[P6_ZTP_PROBE.md §11 Q2]; three controls first proved nothing [git 7416cbf,
8ae4faa, ba2e23f]; three observations recorded and not explained
[P6_ZTP_PROBE.md]. The operator named the class: a rule keyed on the platform
when it was really about the deployment [git 87df56c].

**4. How they were resolved**

- **M1**: the patch boots the base disk; passthrough silences Gi1; the HELLO
  became D4 [git 944876c, f7388b3].
- **M3**: the patch reports which disk it boots [git b69f8d1]. TFTP was
  decided, and D4 gained a second condition: nothing on the segment answers
  DNS [git 365a143].
- **M4**: one peer normalisation for identity and reply [git 4146a8e]; an
  `asked_not_served` stage and a responder health row [git c1471f7]; the key
  generated and the diagnosis kept [git 5ca02db]. Boot 3 was mitigated by the
  operator's hand `write memory`, then fixed for every source: phase 2 saves
  and reads back the startup config before promotion [git f94c41e].
- **C48**: deferred. The operator decided to derive the address; the work is
  in 7.4 [OPEN_FINDINGS.md C48].
- **C49**: fixed by D1, shown by M5 [git 1380b9e].
- **C50**: open. Bucket B, critical: it blocks 7.3's rotate and retire
  [OPEN_FINDINGS.md C50].
- **C51**: fixed in Stage 7.0 [git 61f74b7].
- **C52**: fixed [git 77e909a].
- **C53**: fixed, and nine of nine then carried their credential
  [git d433c5c].
- **C54**: the operator withdrew the heartbeat member, and a teardown step was
  added [git 732c3bc]. The rotation row was fixed on 2026-09-28
  [git 185a4d3].
- **C57**: closed by R1 on 2026-09-28 [git c98f2b7].
- **`RESERVED_INTERFACES`**: deferred to a permanent device; no register row
  found [P6_ZTP_PROBE.md §11 Q2].
- **P-M4f** (a promoted device refused on a second request): left open and
  placed first in the teardown [git d162c0c]. Not recoverable: whether it
  ran.

**5. Numbers**

- **Commits**: 21 by subject [git 1bdab6c, 2026-09-26 13:20:00 → git 77e909a,
  2026-09-26 22:16:18]. Rule: the subject contains "P.6". Six commits whose
  bodies tie them to P.6 make 27, ending at git 732c3bc (22:41:39). The
  selection is ambiguous.
- **Elapsed**: 8 h 56 m from plan to close, including P.4 and P.5 work until
  17:16; 4 h 50 m from scoping to close [git 21d5b1f → 77e909a].
- **Runs**: 8 [P6_ZTP.md §8; git 77e909a].
- **Findings**: 7 rows opened (C48 to C54), plus C57. Open count 34 → 39
  [git 61b98a2, f94c41e]. The count at close is not stated.
- **Suite**: 4038 → 4273 passed [git 61b98a2, 77e909a]. Only P.6 commits lie
  between.
- **Estimate**: none recorded [NSOT_PLAN.md P.6].
- **Acceptance (Lab 8)**: a configless device was leased from a reservation
  the tool wrote, fetched its config from the tool (each fetch a reveal row),
  was reached, rotated, saved and read back, recorded in NetBox, promoted, and
  rebooted into its saved config [P6_ZTP.md §8]. Teardown was clean: census
  exit 0, the reservation removed and read back, r1's route to r6 unchanged
  [P6_ZTP_PROBE.md, teardown]. The caveat: the node had to be persuaded to
  ask. Lab 9 was not demonstrated within P.6 [P6_ZTP.md §8].

**6. Where it left the product**

The tool can reserve an address, serve a bootstrap config and onboard a
configless device end to end, and every onboarding now saves the device before
promotion.

#### Sources read (P.5, P.6)

- docs/NSOT_PLAN.md: P.5 and P.6 sections.
- docs/P6_ZTP.md: all, including §8's ledger.
- docs/P6_ZTP_PROBE.md: predictions and observations for M1, D1, M5, M3 and M4,
  the teardown result, §9, §10 and §11 Q2.
- docs/OPEN_FINDINGS.md: rows D2, D11, C48 to C54, C57.
- docs/NSOT_FEATURE_AUDIT.md §8c.
- docs/NSOT_STAGE7_PLAN.md: concept table, 7.4 and 7.6 rows, R2.
- docs/NSOT_WRITEUP_NOTES.md and docs/WRITEUP.md: searched; no P.5 or P.6
  content.
- CLAUDE.md.
- git: log over 2026-09-26 12:00 to 2026-09-28 03:00; bodies of 61b98a2,
  8ff6698, 1b7e639, 7416cbf, 8ae4faa, 4095240, ba2e23f, 23f3fb6, 4146a8e,
  c1471f7, 87df56c, f94c41e, d91f494, d433c5c, d162c0c and 77e909a; `-S`
  searches for register-row origins.

#### Could not recover (P.5, P.6)

- Working time on P.5's build: it is one commit, with unrelated work
  immediately before it.
- The host's re-approval commit `be60f59`: a `config_repo` commit on the host,
  cited from CLAUDE.md, not verified here.
- Whether P-M4f (a promoted device refused on a second request) was run, and
  its result.
- The register's open count at P.6's close: no commit states it.
- Whether the documents' 2026-09-27 dates are UTC by convention. They are
  consistent with UTC, but no convention is recorded.
- Any time or effort estimate for P.5 or P.6: none was found.

### P.7 and P.8

Decided on 2026-09-28, not built: P.7 (alert rules generated and tested, its own item before 8.6) and P.8 (per-list settings: two lists are two networks) [NSOT_PLAN.md P.7, P.8]. Entries are written when they close.

## Part II. Stage 7

### 7.0 — The checks every later step is written against

*Backfilled 2026-09-29.*

**1. What it was.**
7.0 built the mechanical checks that the rest of Stage 7 would be measured by,
before any screen was rebuilt. There were four: every route reachable from a page
(or named as non-GUI, or allowlisted); every mutating route declaring what data it
invalidates, so panels re-fetch; "if a payload carries it, the screen shows it";
and the nine concepts taught where the action happens [NSOT_STAGE7_PLAN.md §8,
row 7.0]. Two register findings were gates that had to be fixed first: B1 and C51
[NSOT_STAGE7_PLAN.md "7.0 built"].

**2. How it was implemented.**
- **Reachability** (`tests/test_route_reachability.py`, with a shared reader,
  `tests/route_references.py`) reads the rendered pages and counts `url_for` in
  template source. It decides "read or write" per METHOD where one path mixes both
  [git 379b4d8; CLAUDE.md test table].
- **Invalidation** (`modules/invalidation.py`, client `static/js/nmas_invalidation.js`)
  gives each mutating route a list of data keys from a finite vocabulary. The
  response carries them in a header, and panels subscribed to a key re-fetch. A
  failed re-fetch marks the panel stale [git a8dce41; CLAUDE.md module map].
  This is the live-data contract's first half: it sees only changes a response
  announces. The server-sent half came in 7.2 (C58).
- **Payload to render** (`tests/test_payload_is_rendered.py`, `tests/payload_providers.py`,
  `tests/payload_render.py`) calls each declared route through the test client,
  records the keys of its real JSON, parses the shipped renderer for the keys it
  reads, and checks both directions, with floors and named anchors
  [git dca1071; NSOT_STAGE7_PLAN.md §5].
- **Nine concepts** (`tests/test_concepts_are_taught.py`) runs the shipped screen
  code in duktape against real payloads and asserts a visible, non-empty
  `data-concept` element, not text, which prose could match [NSOT_STAGE7_PLAN.md §4].
- Each check starts with a measured allowlist, pinned at a ceiling and compared
  exactly, so it can only shrink [NSOT_STAGE7_PLAN.md "7.0 built"].

**3. Issues encountered.**
Register rows introduced in 7.0's window (attributed by the commit that first adds
the row to OPEN_FINDINGS.md, `git log -S`):
- **C55**: `GET /monitoring/config` returned both SNMP communities in plaintext; the
  RW one was drawn nowhere. Found by the payload check [git dca1071; OPEN_FINDINGS.md C55].
- **C56**: four more GETs returned stored secrets, found when B11's sweep was
  re-planted over every store [git dc3dec8; OPEN_FINDINGS.md C56].
- **C57**: the ZTP phase-2 persist step had never carried a real onboarding.
  Registered in the same commit; acceptance 6's third case waits on it
  [git dc3dec8; NSOT_STAGE7_PLAN.md "7.0 built"].
- **C58**: response-keyed invalidation cannot see a change made after the
  response or on a schedule. Found reading the code behind acceptance 6
  [git 76f7ffa; OPEN_FINDINGS.md C58].
- Gates fixed at the start: **B1** (a drifted deploy returned the device's
  configuration) and **C51** (24 GETs created the list they were asked about)
  [git 9df50ed, 61f74b7; OPEN_FINDINGS.md B1, C51].

Found while building, not register rows [NSOT_STAGE7_PLAN.md "7.0 built"]: the
six `/netbox/query/*` routes had a claimed consumer and no caller; reachability
first split read/write per rule, and its control did not fail because
`/drift/settings` is two rules on one path; the invalidation hook keyed on the
endpoint alone, so a read or a refusal announced an invalidation; the concept
`approval-binds-a-set` described the retired approval scheme 2; one anchor named
`list_name` where the key is `list`; the GUI doc's route floors predated P.3 and
P.4's removals.

Defects in 7.0's own checks, found later in 7.1: **C87** (reachability counted
intent revert reached through a shared URL prefix), **C72** (fourteen empty record
collections in the payload fixtures), **C90** (a duplicate dict key hid a new
`RENDERS` entry) [OPEN_FINDINGS.md C72, C87, C90].

**4. How they were resolved.**
- B1, C51: fixed before the checks [git 9df50ed, 61f74b7].
- C55: fixed right after 7.0; communities are write-only on every route. The plan
  kept it out of 7.0 "because 7.0 changes no route's behaviour"
  [git dc3dec8; NSOT_STAGE7_PLAN.md "7.0 built"].
- C56: fixed before 7.1, as the operator decided [git 68d2739]. C57: closed on its
  marker by the operator's R1 run, 2026-09-28 [OPEN_FINDINGS.md C56, C57].
- C58: moved to 7.2; the server-sent announcement was built as 7.2 step 10, and
  some background jobs still do not announce [OPEN_FINDINGS.md C58].
- Hook keyed on method too [git 9264d97]; concept renamed
  `approval-binds-the-template`, and the harness now fails if the plan's table
  disagrees; `/netbox/query/*` to removal in 7.8; floors restated as 212 and 115
  [NSOT_STAGE7_PLAN.md "7.0 built"].
- C87 fixed [git c59eefd]; C90 fixed as a rule (`test_no_duplicate_dict_keys.py`)
  [git d987c02]; C72 open, bucket C/M [OPEN_FINDINGS.md C72].

**5. Numbers.**
- Commits: 5 core, `379b4d8` (2026-09-26 23:01:07 -0600) to `91c81fd` (23:32:19):
  the four "Stage 7.0 (n)" commits plus the hook fix `9264d97` the plan cites. With
  the two gates and acceptance 6's first run, 8 (`9df50ed` 22:44:08 to `76f7ffa`
  23:48:50). `dc3dec8` (C55's fix) is excluded: the plan puts it outside 7.0
  [git log; NSOT_STAGE7_PLAN.md "7.0 built"].
- Elapsed: 31 min for the core; 1 h 4 min with gates and the first acceptance run
  [git timestamps].
- Findings: register rows went from 92 to 96 across the window (C55 to C58)
  [row count at git 9df50ed^ and 76f7ffa].
- Measured at build: 212 routes, 218 (method, route) pairs, 54 unreachable;
  115 mutating endpoints, 32 data keys, 29 unsubscribed; 27 renderers, 118 carried
  and undrawn, 18 unreached reads; 4 concepts live, 5 pending
  [NSOT_STAGE7_PLAN.md "7.0 built" table].
- Estimate versus actual: Not recoverable: no estimate for 7.0 is recorded in the
  plan or the commit messages read.
- Acceptance: acceptance 6 (the three cases updating on the host without a reload)
  was NOT passed on its first run, 2026-09-27. The Remote card updated but could
  not be attributed (C58); the drift case could not test the mechanism; the device
  list after Verify was not measured [NSOT_STAGE7_PLAN.md "7.0 built"]. Not
  recoverable: any later passing run of acceptance 6; none is recorded in the plan
  or register.

**6. Where it left the product.**
Every later Stage 7 step had four shrinking allowlists to be measured against, and
the one mechanism for "the screen is now wrong" worked only for changes a response
announces.

### 7.1 — An operation, whole, from the interface

*Backfilled 2026-09-29.*

**1. What it was.**
7.1 began as "the preview-then-confirm component, retrofitted to deploy, restore,
onboarding, bulk intent and NetBox import/remove" [NSOT_STAGE7_PLAN.md §8, row
7.1]. It was reshaped mid-stage, when the operator stopped the first real restore
run (C70) because it needed a browser console, a fleet-wide Save All, the network
tab and an SSH session. The goal became: every operation that changes a device or
the record has one preview, one confirm, one result and one record, and none of
it requires a console [NSOT_STAGE7_PLAN.md "7.1 reshaped", "7.1 acceptance"].

**2. How it was implemented.**
- **The preview half.** `modules/preview_confirm.py` builds six parts (what, what
  will NOT happen, program, operands, gates, confirm), refusing a silent part
  (`PreviewIncomplete`); per-screen adapters (`deploy_preview()`,
  `restore_preview()`, `onboard_preview`, `netbox_import_preview`,
  `netbox_removal_preview`). One renderer, `static/js/nmas_preview_confirm.js`.
  Gates have five states; `at_apply` and `not_reached` are never drawn as pass
  [NSOT_STAGE7_PLAN.md "7.1, deploy retrofitted", "7.1 acceptance"].
- Because the server now builds what the screen draws, the payload check reads
  the adapter's source too, and gained anchors `preview`, `lines`,
  `from_this_edit` [NSOT_STAGE7_PLAN.md "7.1, deploy retrofitted"].
- **The receipt** (C60's first half, `modules/nsot/receipts.py`): one masked row
  per device per batch, written by deploy and restore after the golden commit,
  with the program's hash against the confirmed one, the checks that ran, and
  `follow_up: not_run` stated [git 639e192; OPEN_FINDINGS.md C60].
- **The result half.** `operation_result()` builds what happened from the receipt
  rows the apply just wrote, so the screen and the record are one computation.
  The level (colour) is computed on the server. `GET /deploy/receipts` and the
  Device page's Changes tab read it back [git a97de2d; NSOT_STAGE7_PLAN.md
  "Steps 2 and 3 BUILT"].
- **Capture as an operation** (C82, C89): preview reads each device now and shows
  its diff against the golden and its departure from committed intent; apply
  re-reads, refuses a moved hash, commits as the verified person
  (`Source: capture`). Save All became its fleet form; `/golden_configs/save_all`
  was removed. `save_golden()` writes a computed `Intent-Match:` trailer and takes
  a baseline only with coverage AND every capture matching
  [git 7910e09, e263ff6].
- **Scoped restore** (C80): the Device page's "Restore from…" and a Baselines
  re-apply whose device scope starts empty [git a5c1663].
- **Onboarding and NetBox** retrofits: Create drawn as "Partly done" and pending
  (C86); Remove drawn from a recorded row, `data/netbox_removals.jsonl` (C121);
  then both previews moved onto the component (C122) [git 48ff343, cd16440,
  7a3a66e, 9e1cba2]; Verify and Abandon drawn from an onboarding run record
  [git 763649e].
- **Constraints over lists**: `test_results_are_drawn.py` takes its population
  from the gate table; `GREEN_TOASTS` declares every green toast, found by parsing
  each `showToast(` call [NSOT_STAGE7_PLAN.md "7.1 reshaped", "onboarding and
  NetBox Remove retrofitted"].

**3. Issues encountered.**
Attribution: the plan counts every register row added across 7.1's commit span,
"69 C-rows (C60 to C128) and 2 E-rows", and names six as side work (C119, C120,
C123, C124, C125, C126) [NSOT_STAGE7_PLAN.md "The forecast, corrected"]. I checked
each ID with `git log -S "| Cnn |"`: every row C60 to C128 first appears in a
commit between `ff6fc24` and `763649e`, and E6 and E7 in `d11955d` and `c776d5c`.
Many came from threads running beside 7.1's screens (the verify sweep, Stage 8
design, concurrency); I group them by theme and do not claim all came from 7.1's
own screens.

*The component, the result and the record*
- C60: deploy receipt built; follow-up window not.
- C72: fourteen empty record collections in the payload fixtures.
- C73: residue drawn with no section.
- C84: a restore's result was a toast.
- C85: NetBox import outcome persisted, drawn nowhere, sync card green when partial.
- C86: Create said "Device onboarded." after phase 1.
- C87: reachability counted intent revert reached.
- C88: device text interpolated into HTML unescaped.
- C90: a duplicate dict key hid a `RENDERS` entry.
- C96: drift panel drew none of its last run.
- C109: an unselectable target greyed with no reason.
- C121: NetBox Remove drew a partial removal green.
- C122: "retrofitted" meant results, not previews.
- C125: "25 pending" was the ceiling; the count was 23.
- C127: capture preview said lines "will be sent".
- C128: NetBox previews sent the whole dry run to the browser.

*Restore and its gates (found building the gates part, or running C70)*
- C70: the baseline re-apply path had never carried a real restore.
- C75: a restore could change a held credential (it was live).
- C76: the merge program compared lines as text.
- C77: both previews returned stored config verbatim.
- C78: "re-read at apply" re-read the stored capture, not the device.
- C79: a restore could add back a rotated-away secret.
- C80: a baseline could be re-applied only to the whole fleet.
- C81: approving a drift item committed as `ai-agent`.
- C82: no per-device golden capture existed.
- C83: every golden commit subject said "baseline".
- C107: `Intent-Match` compared the raw capture.
- C108: verify took its protocol list from the before-state.
- C110: a restore was recorded `Source: pipeline`.
- C111: two paths wrote identical rotation records.

*Capture and the record*
- C89: capture promoted any device state to golden, baseline and remote.
- C91: a committing Save All took a baseline with a device skipped.
- C104: the manual commit, and readers taking uncommitted files.
- E7: a baseline recorded configuration, not a working network.

*Around the operation (C70's run and after)*
- C92: the online dot was one probe, and one miss drew "offline".
- C93: s3 misses probes while forwarding for the fleet.
- C94: the lab host is unmonitored.
- C97: NMAS leaked SSH sessions and locked itself out of r2.
- C98: a restore and a deploy ran on r2 at once.
- C99: a fifty-second restore showed nothing while it ran.
- C101: paths wrote to a device without holding it.
- C102: pre-model GUI controls reach undescribable states.
- C103: the template preview reads a second capture store.
- C105: three actions implemented twice.

*Verify and device-text readers*
- C61: the read-only allowlist checked the first word only.
- C62: verify read one protocol per device.
- C63: the dangerous-line check is a list of forms.
- C64: the BGP check expected eight fields; IOS prints ten.
- C65: the RIP check read the "application" table.
- C66: the route check read the Networks column.
- C67: the canary accepted Loopback0.
- C68: any count above zero was "progress".
- C69: two BGP summary readers, one wrong.
- C71: fleet fixtures predate P.1.
- C74: BGP judged on IPv4 only.
- C112: a failed rollback drawn as "rolled back".
- C113: "verify never failed" meant it was blind.
- C114: verify passed a device losing its only neighbour.
- C115: the route check was skipped and drawn as compared.
- C116: verify checks only loss.
- C117: the rollback path had never run.
- C118: s4 carried a rollback block for four days.

*Secrets, NetBox, tooling*
- C95: NetBox held every device's credentials in `local_context_data`.
- C100: NMAS's NetBox token is the operator's own account.
- C106: CLIs that stop half-way.
- C119: CI failure unreadable from here.
- C120: stale bytecode ran a mutated control.
- C123: four CDN libraries (a duplicate of D8).
- C124: `nmas-deploy` read a cancelled run as the verdict.
- C126: an unconfigured topology service drawn red.
- E6: no device logs its own config changes.

**4. How they were resolved.**
From each row's status column [OPEN_FINDINGS.md, by ID], with the fixing commit
where the subject names it [git log].
- **Fixed inside 7.1's window:** C61 [eecc900]; C62, C64-C68 [a8019b4]; C69
  [b2924e3]; C73 for deploy [94c9cf1], restore half [f22f8a3]; C74 [dc14f3b];
  C75, C76, C77 [f22f8a3; C77's sweep 6f6b917]; C78's false sentences only; C81
  [8533cb4]; C80 [a5c1663]; C82, C89 [7910e09, e263ff6]; C83 [5cce8f6]; C84
  [a97de2d, closed by C70's re-run]; C85 [d987c02]; C86 [48ff343]; C87 [c59eefd];
  C90 as a scan rule [d987c02]; C91 [7910e09]; C97 [3df10e3]; C98 [11ac30c]; C99
  [76d0f7a]; C101 [c865b4b]; C104 [4370619, 912e3f1, 6b79ab6]; C107 [d17d650];
  C108-C110 [9b39b3a]; C111 [1f6fee9]; C112 [d214f24]; C114, C115, C120 [224bb8f];
  C119 cause found [71401fe]; C121 [cd16440]; C122, C127, C128 [7a3a66e, 9e1cba2];
  C124 [4f92b96]; C123 closed by vendoring [bdea261]; C125 [1bf9a11]; E7 [9f49a33].
  C70 passed on its browser re-run at `d17d650`.
- **Fixed after 7.1 met:** C79, with C140's reason mechanism [e669cbd]; C95
  closed on measurement, 2026-09-28 [f441983]; C96 in 7.2.
- **Decided or closed by decision (the operator):** C88, (a) retire screen by
  screen plus (c) a CSP, built [0f3c61e]; C116 registered and left; C118 renamed
  "blocked change"; C126, Topology tab absorbed into 7.3, removed in 7.8.
- **Moved to a stage:** C58 and C92's reader to 7.2 (built); C92's drawing, C102,
  C103, C105, C106 (3) and C117 to 7.3 (C117 as seed intent's acceptance run);
  C63 to Stage 8.8.
- **Deferred, open:** C60's follow-up window (blocks Stage 8); E6 (blocks 8.7);
  C100 (blocks A3, with 6.2); C78's comparison (UNKNOWN until E6); C93 (UNKNOWN,
  needs C94's metrics); C71, C72, C94, C113, rest of C106 (minor).
- **Deferred by decision, not a finding:** bulk intent's retrofit, to 7.4, by the
  operator: it is fleet-shaped and its CLI works [NSOT_STAGE7_PLAN.md "7.1, deploy
  retrofitted"].

**5. Numbers.**
- Commits: **69**, `ff6fc24` (2026-09-27 00:38:22 -0600) to `763649e`
  (2026-09-27 21:19:05 -0600) [NSOT_STAGE7_PLAN.md "The forecast, corrected";
  confirmed by `git rev-list --count ff6fc24^..763649e`]. Rule: every commit in
  that span, which is the plan's rule; only 18 carry "7.1" in the subject
  [git log]. `df17b55` repeats `ff6fc24`'s subject over four design documents
  (CLAUDE.md conventions).
- Elapsed: **20 h 41 min** of wall time [NSOT_STAGE7_PLAN.md "The forecast,
  corrected"], including a 6 h 26 min gap between the first two commits [git
  ff6fc24, df17b55].
- Findings: register **97 rows to 168**, 69 C-rows and 2 E-rows; about one per
  commit; at `763649e` about 47 closed, 8 decided, about 14 open (a text
  classification) [NSOT_STAGE7_PLAN.md "The forecast, corrected"; row counts
  confirmed at git ff6fc24^ and 763649e].
- Estimate versus actual: measured partway, "13 hours and 32 commits". Actual was
  2.2x the commits and 1.6x the hours. The plan's lesson: an estimate from an
  unfinished stage is made from the part that went to plan [NSOT_STAGE7_PLAN.md
  "7.1 reshaped", "The forecast, corrected"]. The plan also says 7.1 "tripled"
  [NSOT_STAGE7_PLAN.md "7.1 reshaped"]; Not recoverable: the original pre-7.1
  estimate that "tripled" refers to.
- Acceptance: MET 2026-09-28 on the laptop suite, 5025 passed, 0 errors. Results:
  9 of 38 gated actions drawn by the result component, 21 pending (each homed in a
  later stage), 8 with no GUI; previews: five screens on the component, only bulk
  intent pending. The result survey began at 33 of 41 not drawn
  [NSOT_STAGE7_PLAN.md "7.1 acceptance"].
- Stated limit: only restore had run on the host. R1 (onboarding) and R2a/R2b
  (NetBox) closed it on 2026-09-28; R2b deleted exactly the 8 predicted objects and
  the census compare passed at 235 objects [NSOT_STAGE7_PLAN.md "7.1's stated
  limit"].

**6. Where it left the product.**
Deploy, restore, capture, onboarding and NetBox import and remove each had one
preview, a hash-bound confirm, a server-levelled result built from the record the
apply wrote, and a place to read that record again, with no console needed.

#### Sources read (7.0, 7.1)
- docs/NSOT_STAGE7_PLAN.md: §4, §5, §8 table, "7.0 built", "7.1, deploy
  retrofitted", "7.1, restore retrofitted", "7.1 reshaped", "7.1, onboarding and
  NetBox Remove retrofitted", "7.1 acceptance", "7.1's stated limit", "The forecast,
  corrected", §10.
- docs/OPEN_FINDINGS.md: rows B1, C51-C128, E6, E7 (titles and status columns;
  full text for C55-C58, C70, C75, C77, C79, C84, C122, C125).
- docs/NSOT_WRITEUP_NOTES.md: section headings; no 7.0 or 7.1 section found.
- CLAUDE.md: module map and test table entries for the named modules and tests.
- git: `git log --format='%h %ad %s' --date=iso` around 2026-09-26 to 28;
  `git show --stat` for 379b4d8, a8dce41, 9264d97, dca1071, 91c81fd, 76f7ffa;
  `git log -S` per register ID; `git rev-list --count`; register row counts at
  9df50ed^, 91c81fd, 76f7ffa, ff6fc24^, 763649e.

#### Could not recover (7.0, 7.1)
- Any estimate for 7.0.
- A passing host run of 7.0's acceptance 6; the plan records only the first,
  failing run.
- The original 7.1 estimate behind "7.1 tripled"; only the partway "13 hours and
  32 commits" is recorded.
- Which of the 71 rows in 7.1's span came from 7.1's own screens versus side
  threads, beyond the six the plan names; the theme grouping above is mine.
- Fixing commits for rows whose status names no commit and whose fix no commit
  subject names (for example C112's exact commit is inferred from its subject).

### 7.2 — Needs attention, the reader job, and the live-data contract

*Backfilled 2026-09-29.*

**1. What it was**

7.2 built the landing view that answers "what needs my attention", plus a status bar on every page [NSOT_STAGE7_PLAN.md table row 7.2]. Needs attention had to draw every source in the plan's section 1a: job health, drift with coverage, freshness, firing Grafana alerts, the approvals queue, pending onboardings, rollback blocks, a failed deploy, and an unearned baseline. It also leaves an empty slot for Stage 8 triage [NSOT_STAGE7_PLAN.md §1a]. The page could do no per-device work to render (§0a). A source that could not be read had to be a row, never an absence. The stage also carried C92: replace the one-probe "online" dot with a reader that counts consecutive misses [NSOT_STAGE7_PLAN.md table row 7.2; OPEN_FINDINGS C92].

**2. How it was implemented**

*The row and the source contract (step 1).* `modules/attention.py` has one constructor, `row()`. It refuses a row with no what, cause or action. Each row carries what, devices, since, cause, operands, one action, a level the server decides, and an empty `triage` slot [NSOT_STAGE7_PLAN.md 7.2 step 1]. `source_result()` records when a source was read, how long the read took and what it looked at. An unreadable source, or an adapter that raises, becomes a row [git 71ed99e]. Step 2 added `value_at`: a stored source is dated by its value (for example, the drift run), not by the read [NSOT_STAGE7_PLAN.md 7.2 step 2]. Step 3 added the attach rule: a queued drift approval folds into its device's drift row, so one event is one row [NSOT_STAGE7_PLAN.md 7.2 step 3].

*The sources on stored data.* Five sources read stored data:
- drift: the last stored run, never a re-check (step 2);
- approvals: through a new `read_pending()` that writes nothing, and pending onboardings (step 3);
- rollback blocks: through the one classifier the listing already used (step 4);
- deploys and restores: each device's latest receipt, judged by the result screen's own `result_level` (step 5);
- repeated authorisations: the same line authorised three or more times on one device (step 7).

For the baseline source, the operator chose to make the decision durable first. `save_golden()` now writes `Baseline: earned` or `Baseline: denied: <reasons>` into the commit it judged, and the source reads the newest decision [NSOT_STAGE7_PLAN.md 7.2 steps 5–6]. Step 8 moved each job-health row family's remedy out of the detail text and into the row's `action` field [NSOT_STAGE7_PLAN.md 7.2 step 8].

*The reader job (step 9).* `modules/reader_job.py` is one background read of an outside service. It stores its value dated by the value; a failed read keeps the last good one; an exactly-full page is refused as partial; its liveness is a job-health row; it announces its data keys when it finishes; and registration refuses a reader that does not declare its endpoints, its interval's measurement, or its keys [git f310e42]. The rules are written in the module's docstring. There were ten at first; two more followed: "a check stays live; only a report is cached" and "a reader's promise is about how fast NMAS notices, not how fast the source notices the world" [git 20483d6]. Step 19 extended rule 9: a reader that announces only on change must also send a keepalive, and registration refuses one without it [git 33a8041].

*The readers.* Built in 7.2:
- **Job health** (step 11), every 300 s. The operator measured the landing view on the host: job health took 9,797 ms, 99.4% of the page [NSOT_STAGE7_PLAN.md 7.2 step 11]. Its stored rows exclude the `reader:*` rows, so a stopped reader cannot freeze a cache that says it is fine [git a9377dc].
- **Grafana alerts** (step 14), every 60 s, from three named endpoints. It tells condition, no data and error apart, groups incidents on the onset (start minus window, within 360 s), and flags an evaluator that answers but has stopped [NSOT_STAGE7_PLAN.md 7.2 step 14].
- **Freshness** (step 15), every 300 s. Before this, the index page ran one Oxidized fetch per device on every load. The sanitiser's gate stays a live read on purpose [NSOT_STAGE7_PLAN.md 7.2 step 15].
- **Integration health** (step 16), every 60 s. Its probes run in parallel. It feeds both the status bar and Needs attention [NSOT_STAGE7_PLAN.md 7.2 step 16].
- **CI verdict** (step 17). It loads `scripts/nmas-deploy` and calls that script's own `ci_verdict()`. `GET /health/version` composes the answer and computes none of it [NSOT_STAGE7_PLAN.md 7.2 step 17].
- **Reachability** (step 19, C92), every 5 s, every list: per device the last result, which probe answered, the miss count against `miss_threshold()` (3), and since when. It owns the `device_status_cache` every consumer already read; `ping_worker` is gone [NSOT_STAGE7_PLAN.md 7.2 step 19].

A seventh reader, baseline usability, came after 7.2 was declared built and reused the same pattern [git 9c1037d].

*The live-data contract (steps 10 and 13).* `invalidation.announce()` sends a background job's data keys over Socket.IO. The client is loaded once, in `base.html`. The server sends a heartbeat every 30 s. A page that misses 2.5 beats marks every subscribed panel as not updating, on the panel's own data. Every value carries `value_at` and `stale_after_seconds`, judged on a local 15 s tick that makes no request. A reconnect re-fetches every subscribed panel once. There is no data polling, except Needs attention's 60 s poll, which stays until every sender announces [NSOT_STAGE7_PLAN.md 7.2 steps 10, 13].

*Presentation.* With no rows, the page is one line that still makes the positive claim (step 12). The operator then set Stage 7's rule: the screen answers the question the person came with, the evidence one level down; it was applied to four panels [git ca899db]. The status bar's three items are integration health, the version with its CI verdict, and who you are, read live from `/identity/status` [NSOT_STAGE7_PLAN.md 7.2 steps 16–18].

**3. Issues encountered**

*How I attributed findings.* A row counts if it was first written inside the 7.2 commit selection (C164–C174, by `git log -S` on OPEN_FINDINGS.md), or if a 7.2 step closed or advanced it. Findings with no ID are listed separately.

New register rows during 7.2:
- C164 — nine of ten job-health row families had no action a person could take from the interface.
- C165 — Grafana's rules view and its Alertmanager seemed to disagree on what was firing.
- C166 — two Grafana rules had been in no-data for days, and nothing surfaced it.
- C167 — `prometheus_url` appeared empty while Grafana queried Prometheus.
- C168 — the hand-built Grafana rules had never been verified. The SNMP scrape targets are also a hand-kept list.
- C169 — the ZTP responder sent a refusal before recording it (found by the commit gate; side finding).
- C170 — `nmas-deploy` refused a docs-only commit with a message describing a search it never made (side finding).
- C171 — the NSoT git probe described one global repository, and five of its settings are read by nothing (found from the status bar).
- C172 — an unreadable `remote.json` reads as no remote (found building C171's probe).
- C173 — lists separate devices, but settings are global. Latent defects include the status bar and the Grafana source (P.8 scoping, the operator's).
- C174 — NetBox tenants against regions (a deferral recorded out of P.8).

Existing rows 7.2 closed or advanced: C96, C151, C140 (1), C58, C92, C159, C163, C144. C38 was assigned to 7.2 and not built.

Findings with no register ID [git bodies]:
- The payload check sampled each list through its first item only, so nine `EMPTY_IN_FIXTURE` declarations were false [git 694d303].
- An unearned baseline's reason had no durable record [NSOT_STAGE7_PLAN.md 7.2 step 5].
- C58's premise was false: the index page held no Socket.IO connection [git f310e42].
- The reader rows' `since` was an ISO string where every other row used epoch seconds, so the first failing reader would have crashed the source. The subscription scan also never read `static/js/nmas_*.js` [git a9377dc].
- The commit gate read the previous run's result file, so e986e66 was committed on "5330 passed" when its suite never ran [git 6fc7b59].
- A plan note quoted C17 as open, taken from CLAUDE.md's restatement a day after the register had closed it [git dd87620].

*Gate runs before 7.2.* R1 (onboarding a throwaway) and R2a/R2b (the NetBox window) are recorded as closing **7.1's** stated limit. They were scheduled before 7.2 and listed as 7.2 gates [NSOT_STAGE7_PLAN.md "7.1's stated limit"; NSOT_PLAN.md dependency notes]. They are not part of 7.2's close, so their findings are not counted here: C130, C131, C133–C135 (R2a); C146–C154 and the C57 closure (R1, R2b). The other gates, C17, E4 and C54, closed or were fixed before step 1 [git 711dc74, 185a4d3].

**4. How they were resolved**

- **C96** — fixed in step 2. The drift panel draws what a run found. The payload fixture now reaches a real drift run [OPEN_FINDINGS C96].
- **C151** — closed in step 8. The heartbeat check's row carries "regenerate the rules" as its action [OPEN_FINDINGS C151].
- **C164** — 7.2's half fixed in step 8 (every row family's remedy is its action). The other half, persist as a Device action, was decided by the operator for 7.3 [OPEN_FINDINGS C164].
- **C140 (1)** — built in step 7. Part (2), one home for authorising, waits for the restore preview's re-planning [OPEN_FINDINGS C140].
- **C58** — mechanism built in steps 10 and 13. The remaining senders (post-commit push, drift run, NetBox refresh, another browser) stay open. Needs attention keeps its 60 s poll until they announce [OPEN_FINDINGS C58; NSOT_STAGE7_PLAN.md "What does not exist yet"].
- **C92** — split by decision. The reader was built in step 19. Drawing the claim and its age on the dot is 7.3's [OPEN_FINDINGS C92].
- **C165** — closed as a defect in the measurement. Both instances were `DatasourceNoData`. The design consequence (three kinds of instance, and a reader names its endpoint) went into the Grafana reader [OPEN_FINDINGS C165].
- **C166** — closed on measurement. The syslog rule was miscoded. The operator applied the attribution fix, and it was read back through the ruler [OPEN_FINDINGS C166].
- **C167** — closed on measurement. `prometheus_url` was set and answered. The class of the finding is the status bar's [OPEN_FINDINGS C167].
- **C168** — surveyed on the host, then scheduled into P.7 by decision: rules generated and tested [OPEN_FINDINGS C168].
- **C169** — fixed the same turn: record, then send [OPEN_FINDINGS C169].
- **C170** — fixed. Each ancestor is asked about by SHA, with a bound of 10 [OPEN_FINDINGS C170].
- **C171** — probe half fixed. Retiring the dead fields is scheduled into 7.7 [OPEN_FINDINGS C171].
- **C172** — deferred, sorted C/M [OPEN_FINDINGS C172].
- **C173** — decided by the operator as P.8, placed after 7.2 and before P.7 and 7.3 [OPEN_FINDINGS C173].
- **C174** — deferred by the operator to Stage 9, with both sides of the argument recorded [OPEN_FINDINGS C174].
- **C159** — extended: the approval queue saves on every read. Needs attention reads through `read_pending()` instead. The row stays deferred to Stage 9 [OPEN_FINDINGS C159].
- **C163** — a second unexplained error was added. Targeted runs are now saved whole [git a9377dc].
- **C144** — re-sorted to Stage 9, because "placed in 7.2" named a stage it was not in [git dd87620].
- **C38** — not built. The register still schedules an adjacency row into 7.2, and no adjacency source exists in `attention.py`.
- **Unnumbered findings:** all fixed in the commit that found them [git 694d303, 2a51799, a9377dc, 6fc7b59, dd87620].

**5. Numbers**

- **Commits: 37** [git 71ed99e^..33a8041]. The selection rule is every commit from the first "7.2 step" commit to the one declaring "7.2 is built". Of those, 19 carry "7.2 step N". The other 18 are register, P.7 and P.8 decisions, and C166–C171 measurements interleaved in the same window. The selection is ambiguous, because the interleaved commits are not all 7.2 work.
  - First: 71ed99e, 2026-09-28 12:31:21 −0600 [git 71ed99e].
  - Last: 33a8041, 2026-09-28 16:34:04 −0600 [git 33a8041].
- **Elapsed: about 4 h 03 min** between those two commits [git].
- **Findings: 11 new register rows** (C164–C174) [OPEN_FINDINGS; git -S]. Eight existing rows were closed or advanced. Six findings have no ID.
- **Estimate against actual:** the plan predicted 40 to 70 commits over about a day, with 30 to 50 findings, "to be checked when it closes" [NSOT_STAGE7_PLAN.md "The forecast, corrected"]. No check is recorded. Measured here: 37 commits in about 4 hours, and 11 new rows plus six without an ID.
- **Suite:** 5239 passed at step 1 and 5450 passed at step 19 (laptop, parallel) [git 71ed99e, 33a8041].
- **Host measurements taken during the stage:**
  - job health 9,797 ms per page load before it became a reader [NSOT_STAGE7_PLAN.md 7.2 step 11];
  - ten integrations answered in 266 ms [step 16];
  - Grafana's endpoints answered in 35–150 ms [git f310e42];
  - C92's threshold came from 2,946 offline runs, 93% of which ended at the next probe [OPEN_FINDINGS C92].
- **Acceptance:** Not recoverable. The plan records "7.2 is built" (step 19), and no whole-stage host acceptance of Stage 7 acceptance item 7 is recorded in the plan or in later commits.

**6. Where it left the product**

The landing page drew every section 1a source from stored or cached values, each dated and judged against its own promise, and the status bar read from the same readers. The reachability reader's claim and the adjacency rows (C38) were left undrawn.

**Reopened 2026-09-29: 7.2 was declared built without one of its scheduled sources.** C38 (nothing alerts on a protocol adjacency) was decided on 2026-09-27 as a Needs attention row and scheduled into 7.2, and `33a8041` declared 7.2 built with no adjacency source in `modules/attention.py`. Nothing recorded the omission; the backfill found it by reading the scheduled rows against the code. It is the same shape as C122 ("retrofitted" meaning half of each retrofit) and D6 (a row left in Scheduled three days after its work was done): a status claim ahead of the thing it describes. **The source moved to 7.3** (the operator, 2026-09-29), to be built with the Device page's Neighbours section: both need the expected adjacency set derived from committed intent, compared against what the device reports, so it is built once with two consumers (the per-device view and a Needs attention row), the reader pattern again. Built for the row alone in 7.2, the expected-set logic would have been built a second time for the page. It sits beside C178, since both ask how many neighbours a device should have against how many it has.

#### Sources read (7.2)
- docs/NSOT_STAGE7_PLAN.md (row 7.2, §1a, 7.1's limit, the forecast, steps 1–19, the presentation rule, §10); docs/NSOT_PLAN.md (gate notes, Stage 9); docs/OPEN_FINDINGS.md (the rows cited, Count); docs/NSOT_WRITEUP_NOTES.md; CLAUDE.md
- git: `log --grep='7.2'`, `log 71ed99e^..33a8041`, commit bodies, `log -S` per row, files added under `modules/readers/`

#### Could not recover (7.2)
- A whole-stage host acceptance of 7.2. None is recorded.
- A check of the 7.2 forecast against actuals. The plan says it would be checked at close, and none is written.
- Which interleaved commits the operator counts as 7.2 work. The subject lines do not settle it.
- Whether C189 (the WebSocket ERROR "that began today") was caused by 7.2 step 10's Socket.IO client. The register does not name the cause, so it is not attributed here.

### 7.3 — The Device page (open)

7.3 is open. The entries below are its sub-tasks that have closed, each written when it closed, or backfilled in the same session and marked as such. Commit times are the committer's local time (UTC-6). Host times are UTC.

#### 7.3 step 1 — Seed intent (C148)

*Backfilled 2026-09-29.*

1. **What it was.** Onboarding left a device with only a bootstrap intent. A device with no full committed intent is `bootstrap`, and it cannot be deployed. So nothing onboarded could ever be deployed to. Seeding closes that path: a device's first full intent is parsed from its committed golden, once.
2. **How it was implemented.** `modules/nsot/seed.py` parses the committed golden (`HEAD`, never the working file) into host_vars. It previews the document against the intent committed now and binds the confirm to a hash of the document and the golden. At apply it parses again and makes one commit of exactly the seeded files (`Source: seed`, a `Seeded-From:` trailer naming the golden). Only absent or bootstrap-only intent is seeded. What the template does not model is named in the preview and never blocks here. It is the Device page's "Seed intent" (`static/js/nmas_seed.js`), and it replaced four extraction routes, which now answer 404 [CLAUDE.md module map; `tests/test_seed_intent.py` row].
3. **Issues encountered.** C148 was the finding it fixed: it blocked the central loop, and the first triage had filed it as 7.3 work [CLAUDE.md "Open findings register"]. Not recoverable in this entry: whether building it surfaced other findings. This entry was backfilled from the commit and the docs, not written at close.
4. **How they were resolved.** C148 fixed by `195fdbe`.
5. **Numbers.** One commit, `195fdbe`, 2026-09-28 16:53: 27 files, +1,155 −196, and a 374-line test file [git 195fdbe]. Not recoverable: an estimate.
6. **Where it left the product.** An onboarded device can reach deployable intent from the interface.

#### 7.3 — Retire from the Device page

*Open: built 2026-09-28 and 2026-09-29, AWAITING a real retirement on the host. This entry is not closed, so its numbers are partial.*

1. **What it was.** Retiring a device (C11) existed only as `nmas-retire` on the host. The Device page needed the same operation, previewed and confirmed, with one implementation behind both entry points.
2. **How it was implemented.** `modules/nsot/retire.py` holds the whole exit. `routes/retire.py` serves `/retire/preview` (gated `not_device`) and `/retire/apply` (gated `approve`), and `static/js/nmas_retire.js` is the client. The browser cannot reach the break-glass record, which lives on a laptop. So the screen trusts the EXPORT LOG (`breakglass_logged`) and states that basis and its limit. The log records what was written and cannot show the file still exists, and the CLI's stronger check is to OPEN the record. Each refusal is keyed (`refused_by`), and every key the plan can produce is a gate by name. The apply refuses a rotation made after the preview, and a reason changed after it [`tests/test_retire_screen.py` row; the operator's decision, 2026-09-28].
3. **Issues encountered.**
   - C185: no page reaches a retired device's record once the modal closes.
   - C186: retire's failure paths carry two older shapes (whole-tree `checkout`/`reset`, C175's shape on the failure path).
   - C187: the plan told the operator to re-approve every bound template, an approval scheme 3 no longer withdraws.
4. **How they were resolved.**
   - C187 fixed in the same work: the step was replaced by a Not-Done line.
   - C185 scheduled into 7.3.
   - C186 registered, not fixed, under the sweep's stopping rule.
5. **Numbers.** So far: the screen in one commit, `47f8ecf`, 2026-09-28 18:30 [git]; the gaps overnight 2026-09-29 (commit named in the next entry update). Not recoverable: an estimate (none was written). Not yet run on the host.
7. **Overnight, 2026-09-29: r5's gaps.** Modelled on r5's retire commit (`3592113`). NetBox's stored credentials (C139) are now masked FIRST, with the same implementation as `nmas-netbox-mask-context` (moved to `modules/netbox_context_mask.py`), and read back; the legacy file (C176) is deleted only when its content survives in the repository; the heartbeat rule and the scrape targets, which NMAS does not own, are read and named. One decision waits on the operator: whether writes-off should refuse the retirement (recommended: no). 19 tests; three controls fired.
6. **Where it left the product.** A device can leave management from the interface, and the screen says what its break-glass check did and did not establish.

#### 7.3 step 2 — Mode B: removing a line the device has and intent lacks

*Written at close, 2026-09-29.*

1. **What it was.** Every deploy was merge-only and every restore additive, so the tool could not remove a line. A hand change became permanent in the record: it could be adopted into intent or left, never removed. It surfaced as C184. r2's `load-interval 30`, put on by hand for C70, blocked every baseline for two days. The only resolution the screen could name was the console, in a tool that had removed its terminal. The operator moved Mode B from "deferred" to early 7.3, with r2 as the acceptance.
2. **How it was implemented.**
   - **The computation (2a).** `modules/nsot/removal.py` offers removable units: residue leaves, and stanzas the target lacks. A person selects each unit, and there is never a "converge to intent". The program is the device's own line, negated verbatim in its stanza, or the positive form of a `no` line.
   - **Refusals (2a).** Each has its reason: IOS will not remove it, a physical interface, an account, the management path (the interface holding the tool's address, vty, ip ssh, aaa, static routes), or a named object still referenced.
   - **The measured gate (2a).** `no <line>` can remove more than the line. So a line is removable only where its SHAPE was measured, on its platform, to remove exactly itself. `scripts/nmas-removal-probe` makes that measurement, dry-run by default and never saving, and records it in `removal_measured.json`. Refusing by resemblance is safe and allowing by resemblance is not.
   - **The pipeline (2b).** One `with_removals()` builds the program for plan, apply and run, and each removal carries a reason in the confirm hash and the receipt. Verify reads each removal back gone. Rollback re-adds the device's own lines (`restore_program`), never a negation.
   - **The screen (2c).** Selection is BY ID (`unit_id`), because the plan is masked and a secret-position line's text could never be sent back. Each line shows when it was last rolled back, and why.
3. **Issues encountered.**
   - C191: the device-writer scan does not read `scripts/`, so the new probe script passed the suite unnamed.
   - C192: the probe's dry run printed an AS it would never use, and hid that the BGP shape changes the device's live process.
   - C193: the setting key reduces `no logging buffered` and `no logging console` to one key. Found when the probe's first real run (s4) could not undo its own change.
   - C194: the probe did not record whether its repair ran. So "the repair works" was read from a run it may never have touched.
   - C195: r3's run measured the probe, not the platform (IOS-XE displays ACLs normalised). A shape collision would also have let a destructive removal borrow a safe one's measurement.
   - C196: removing one entry from numbered ACL 97 is destructive or exact depending on which form is sent (IOS: the whole list goes).
   - C197: the acceptance run asked for one decision twice, and the receipt did not keep the removal's read-back.
   - Also measured, not a finding: `logging buffered` leaves the device off its default (`overrides_default`), so it was retired from the probe set.
4. **How they were resolved.**
   - C192, C194, C195 and C197 fixed.
   - C193 pinned by a test and registered (C); FIXED 2026-09-29 overnight (a `no` form keyed on its whole remainder, paired with its positive by prefix, in all three consumers; C200 and C201 registered from the same reading).
   - C196 open (UNKNOWN: does vIOS accept the list-form edit).
   - C191 registered.
   - The numbered-ACL global entry is refused on IOS, citing s4.
   - BGP is unmeasured by choice.
   - The platform record holds cisco_ios (s4) and cisco_iosxe (r3, 9 shapes exact).
5. **Numbers.**
   - Estimate, at costing (2026-09-28 18:35, `c92e8bf`): "about three days to build … so plan on about a week, and treat the three days as the part that goes to plan" [NSOT_STAGE7_PLAN.md, the Mode B bullet].
   - Actual: from costing to acceptance on the host, about 5.5 hours of continuous work. Costed at 00:35 UTC. r2's receipt at 05:53:33 UTC. `baseline/20260929T060249Z` earned at 06:02 UTC, the first earned baseline with a recorded decision.
   - 15 commits from `81007e7` (18:59) to `03aeabe` (00:09 09-29) [git; selection: the Mode B and removal-probe subjects between those shas, excluding `da6b687` (C190, a Save All button)].
   - 7 findings (C191 to C197).
   - Three probe runs on real devices (s4, r3, and r3 again) and one acceptance run, all by the operator.
   - Why the actual is so far under the estimate: the estimate was in days of ordinary work, and this was one continuous session with the operator running probes as each piece landed.
6. **Where it left the product.** The tool can remove a line it measured it can remove, with a reason, verified gone and undoable. The line it could not remove for two days is gone, and the network is at its committed intent.

#### 7.3 — C188: Save All's speed

*Written at close, 2026-09-29.*

1. **What it was.**
   - Starting point: a capture preview failed once in the browser while the app answered 200. Save All read nine devices one after another, twice, and the preview sat past Cloudflare's 100 s edge limit.
   - The operator's scope: concurrent reads with a bounded pool, and an asynchronous preview.
   - Measurement: before and after, per device and in total, naming the slowest.
2. **How it was implemented.**
   - Step 1: `_read_all` reads every device at once (a pool capped at 16), times each device, and names the slowest on the screen.
   - Step 2: the preview is a job (`modules/nsot/capture_job.py`). The POST answers 202 with its id, and the in-flight panel shows the reads. The job announces `capture_preview` (C58, declared in `invalidation.ANNOUNCERS`), and the modal reads the result by id, offering "Check now" while the live channel is down.
   - The apply stays a request, deliberately: after step 1 it takes about the slowest device's read.
   - After the host measurement, each read is split into connect, `show running-config` and disconnect, logged and drawn.
3. **Issues encountered.**
   - C198: the apply took a third of the preview's time for the same nine reads, and every device was faster.
   - C199: the concurrency sweep found 21 serial per-device loops, most with no stated reason.
   - Evidence on C93: s3 was slower under concurrency (23 to 24 s alone, 40.9 s beside eight others). That fits its forwarding every other device's session.
4. **How they were resolved.**
   - C188 closed on the host's measurement.
   - C198 is UNKNOWN: the split is built, and the next Save All reads it. The operator's warm-pool guess was ruled out from the code: every capture opens a fresh temporary session (C97).
   - C199 registered: none converted under the stopping rule, and every direct device-layer loop is declared with its reason by a test.
   - s3's resources stay in Stage 9 (C93, C94).
   - The operator's standing rule came out of it: reads across devices run concurrently, writes only where order does not matter, and a serial multi-device operation states why.
5. **Numbers.**
   - Three commits: `774f2df` (00:15), `5b75941` (00:27), `782fe05` (00:54), 2026-09-29 [git]; about 45 minutes.
   - Before and after, measured on the host by the operator:

     | | Before (serial) | After (concurrent) | Serial sum, after-run |
     |---|---|---|---|
     | Preview | 101 s | 40.9 s | 124.3 s |
     | Apply | 102 s | 13.7 s | 71.1 s |
   - The slowest device was s3 every time.
   - `baseline/20260929T063600Z` was earned, the second earned baseline, 30 minutes after the first.
   - Suite: 5,685, then 5,694, then 5,704.
6. **Where it left the product.** Save All is 2.5 times faster to preview and 7.4 times faster to apply, and no request waits on a device. Why identical reads vary threefold is being measured, not guessed.

## Part III. Across the stages

Collected from what the project already records, with citations in brackets. "CLAUDE.md" means its "Things to Keep in Mind" unless another section is named; "NOTES" is NSOT_WRITEUP_NOTES.md, "S7" NSOT_STAGE7_PLAN.md, "PLAN" NSOT_PLAN.md; register rows are cited by ID. *Backfilled 2026-09-29; kept current as stages close.*

### Patterns

#### 1. The proxy population

**Pattern.** A check's population is defined by something that usually
coincides with the property, not by the property itself, so it stops covering
the property when the proxy moves [CLAUDE.md "A GATE TABLE KEYED ON HTTP METHOD
MISSES A GET THAT CHANGES A DEVICE"].

**Instances, in order** (the operator's list, 2026-09-26, extended since):
- The drift checker enumerated the legacy golden store, not the inventory
  (Phase 3.3, fixed 2026-09-23) [CLAUDE.md "The drift check's population is the
  inventory"].
- The NetBox census compared identity (`id:display`), not assignment, so a
  moved address read as unchanged [CLAUDE.md, same list].
- Approval scheme 2 keyed on the bound device set, not the template (D11).
- The restore preview iterated the ref, not the inventory (C23, fixed by P.3
  step 5, 2026-09-26).
- The gate table was keyed on HTTP method, not on reaching a device (B16,
  2026-09-26).
- The agent's "read-only" tools meant "not config mode", not "cannot change
  anything" (P.3 step 8, the operator's sixth).
- B11's "no GET returns a secret" planted secrets only in stores it knew (C55,
  C56, 2026-09-27).
- C77: the same leak class in POSTs, missed because B11's population was GETs
  (2026-09-27).
- C121: "the false-green class is zero" was true of the list, false of the
  tool (2026-09-27).
- "The tool knows every change by construction" (8.7, 2026-09-27): changes
  through the tool standing in for changes to the device.
- The first store-hardening sweep listed JSON loaders and missed devices.csv
  (C160, 2026-09-28) [CLAUDE.md "A SURVEY SCOPED BY FORMAT FINDS WHAT SHARES
  THE FORMAT"].

**Corollary** (the operator's): a proxy population is a dependency on
something staying true that nobody is watching.

**Mechanical answers.** One gate table, checked both ways with floors
(`modules/route_gates.py`, `tests/test_route_gates.py`); the GET and POST
secret sweeps with stores tied to the storage checker's secret classes
(`test_no_get_returns_a_stored_secret.py`,
`test_no_post_returns_a_stored_secret.py`); an allowlist for read-only
commands (`modules/readonly_commands.py`, C61); the drift population test
(`test_drift_population.py`); a declared-green toast scan
(`test_results_are_drawn.py`). The general rule: "Constrain the shape; do not
only enumerate the instances" [CLAUDE.md, the operator's naming, 2026-09-27].

#### 2. The verify family

**Pattern.** The deploy's verify, which decides rollback, passed or reported
a check it never made, ten separate ways [NOTES "The deploy's safety check
was wrong in ten independent ways"].

**Instances:**
- C62 (2026-09-27): one routing protocol per device, the first found.
- C64 (2026-09-27): BGP pattern expected eight fields where IOS prints ten.
- C65: RIP read the empty `"application"` table.
- C66: route count read the Networks column (4 where r3 has 30).
- C67: canary passed on any "up"; Loopback0 is always up.
- C68 (2026-09-27): any count above zero was "progress".
- C108 (2026-09-27): protocol list taken from the BEFORE state.
- C114 (2026-09-27): losing a protocol's only neighbour was tolerated.
- C115 (2026-09-27): route check skipped on every deploy and restore, drawn
  as compared.
- C178 (2026-09-28): verify accepts the first healthy read at 10 s; IOS holds
  BGP to 180 s. Scheduled into 7.3.

Measured effect before the fixes: on eleven recorded deploys the routing check
was real on four devices and compared 0 with 0 on four [NOTES "The deploy's
verify, against real output"]. None was found by reading the code; each came
from asking the same code a new question [NOTES, ten ways]. A sibling: two
BGP summary readers, topology's right and the deploy's wrong (C69).

**Mechanical answers.** Real captures in `tests/fixtures/operational/`;
`tests/test_pipeline_reads_real_output.py`, with strict expected failures
confirmed by `--runxfail`; one BGP reader, pinned by AST
(`test_other_readers_real_output.py`). Rule: "A CHECK THAT ACCEPTS THE FIRST
HEALTHY READING MUST WAIT OUT THE SUBJECT'S OWN SETTLING TIME" [CLAUDE.md,
C178].

#### 3. A check satisfied by something other than its property

Also named the vacuous pass and the control that passes.

**Pattern.** "A TEST THAT PASSES IN BOTH CASES SHOWS NOTHING" [CLAUDE.md, B9];
its inverse, "a gate that always REFUSES is the same defect as one that always
passes" [CLAUDE.md, P.4 step 4].

**Instances, in order:**
- "Real checks positioned where they cannot fail", six numbered:
  `assert_no_negation` returned `None`; approval validated a different
  template directory; `assert_merge_only` compared `intended` with itself;
  rollback's two conditions; `_restore_config` as a merge;
  `assert_rollback_provenance` saw only `no` lines [NOTES "A family of its
  own"].
- Four controls that could not fail, in Stage 2 (a dry run returning before
  the chain; an `ssh` failing at key exchange printing PASS; a count
  matching a comment; a marker substring) [NOTES "Four controls that could not
  fail, in one stage"].
- A hand-rolled harness in 4C.8 that silently skipped tests; the first genuine
  run was 2,638 passed and 6 failed [NOTES "The harness that could not tell
  'passed' from 'never ran'"].
- B9 (2026-09-26): `rclone delete` exited 0 without touching the file.
- `nmas-deploy --offline` could not pass on any commit, and its red result was
  read as the acceptance (P.4, 2026-09-26) [CLAUDE.md].
- C110 (2026-09-27): "no commit carries `Source: restore`" could not have come
  out otherwise; C111 the second half.
- The integration status "never probes" control passed on the error handling
  (2026-09-28) [CLAUDE.md "A CONTROL THAT WORKS BY BREAKING SOMETHING MUST
  CHECK THE BREAK WAS OBSERVED"].
- C120 (2026-09-27): a control's mutation survived in bytecode.
- C194 (2026-09-28/29): the removal probe did not record whether its repair
  ran [CLAUDE.md "A clean result cannot prove a mechanism that was not
  exercised"].

**Mechanical answers.** Floors on every scan (`_the_scan_finds_something`)
[CLAUDE.md "An assertion over a set difference passes vacuously"]; about 180
built-in controls in 72 files, run every time, and about 330 one-off mutation
controls [TESTING.md "Negative controls"]; restore a mutation from a copy,
never git; `PYTHONDONTWRITEBYTECODE=1` in `scripts/nmas-test` (C120); a
control is valid only when the aimed tests fail, not by crashing [CLAUDE.md].

#### 4. Absent versus unreadable

**Pattern.** A reader that turns an unreadable store into an empty one lets
the next write persist the emptiness [CLAUDE.md "Absent and unreadable are
different facts, and collapsing them erased the settings file"].

**Instances:**
- The settings erasure, 2026-09-23: truncate in place, `{}` on unreadable,
  107 defaults reseeded, Cloudflare Access config blanked [CLAUDE.md "Five
  defensible mechanisms composed into an invisible failure"].
- The NetBox modification record would have been erased the same way;
  "Absent and unreadable are different facts, for the third time in this
  project" [CLAUDE.md, §21].
- `/onboard/pending` must answer `ok: false`, not an empty list [CLAUDE.md "A
  banner that renders 'none pending' because the query FAILED"].
- C130 (2026-09-28): a failed NetBox read treated as "gone", so a preview
  forgot provenance.
- C157 (2026-09-28): the credential store.
- C158 (2026-09-28): the created-object record and `rolled_back.json`.
- C172 (open): `remote.json` unreadable read as no remote.

**Mechanical answers.** `SettingsUnreadable`; `.corrupt-<ts>` preserved;
`read_json_for_write` refuses (`modules/filestore.py`, C158); `_nb_read_by_id`
answers `ok`, `gone` or `unreadable` (C130).

#### 5. The store-hardening family

**Pattern.** A store the program read-modify-writes without a cross-process
lock, a per-write temp file and a refusal on unreadable can lose data or
lift a guard [CLAUDE.md `modules/filestore.py`].

**Instances:**
- C20 (2026-09-25): settings; a shared temp name and no lock left the file
  unreadable in 2 of 2 runs. It was introduced by `4f8a0f1`, the fix for the
  erasure [CLAUDE.md "Every read-modify-write of `user_settings.json` holds
  `config.settings_lock()`"].
- C157 (2026-09-28): the credential store had the three erasure ingredients;
  without the flock, 37 to 47% of writes were lost [CLAUDE.md, `test_
  credential_store_integrity.py` row].
- C158 (2026-09-28): the NetBox created-object record and `rolled_back.json`.
- C160 (2026-09-28): devices.csv, truncated in place, five paths with no lock;
  found only by listing all 85 write sites.
- C161: found inside C160's fix and left, the stopping rule's first
  application [OPEN_FINDINGS "The stopping rule for a sweep"].

**Mechanical answers.** `PathLock`, `write_atomic`, `read_json_for_write`;
`test_settings_concurrency.py`, `test_credential_store_integrity.py`,
`test_store_integrity_c158_c160.py`. A side finding: re-entrancy belongs to
the path locked, not the lock object (C158) [CLAUDE.md].

#### 6. A fixture that cannot exhibit the case

**Pattern.** The assertions are exact, and the input can never reach them
[CLAUDE.md "A FIXTURE THAT CANNOT EXHIBIT THE CASE — a third variety"].

**Instances:**
- `TestMergeCommands.RUNNING` held every container, so the duplicate stanza
  header was unreachable (branch site, 2026-09-24).
- `FakeNetBox` had no foreign keys, so it could not cascade.
- `SourceFileLoader` hides a definition below the `__main__` guard.
- `nmas-seed-status`: tests used absolute paths, the host a relative one (C6).
- C64, C65 (2026-09-27): BGP and RIP samples typed from memory.
- The `/deploy/apply` payload provider only produced a refusal; the undrawn
  list rose 99 to 106 once it produced a deployed row [CLAUDE.md "A CHECK IS
  ONLY AS GOOD AS THE STATE ITS FIXTURE CAN REACH"].
- C72 (2026-09-27): fourteen empty record collections.
- C96 and C85: fixtures that never reached a drift run or a stored import.
- M4 (2026-09-27): tests built an AF_INET socket; systemd hands over a
  dual-stack IPv6 one.
- 7.1 step 5: a fixture that could not DISTINGUISH two states, r2's password
  equalling its account name [CLAUDE.md "A fixture can fail to DISTINGUISH
  two states"].

**Mechanical answers.** Parser tests from captures only; `EMPTY_IN_FIXTURE`
with a ceiling (C72); "build a renderer's test input from the route"; real
pieces allowed in a constructed arrangement [CLAUDE.md "A fixture sometimes
has to build a state the live fleet does not currently offer"].

#### 7. A gate keyed on something that moves for unrelated reasons

**Pattern.** The gate's key changes for reasons that are not the gate's
business, so it revokes or refuses what nobody changed [CLAUDE.md "A GATE
KEYED ON SOMETHING THAT MOVES..."].

**Instances:**
1. Phase 3c: gating deployability on intent drift (caught in design).
2. Approval scheme 1 hashed host_vars, so a deploy revoked its own approval.
3. Scheme 2 keyed on the bound device set, so onboarding revoked a platform's
   approval (D11, D2).
4. `not_already_type_9` refused every rotation after Stage 2 (B13,
   2026-09-26), found while a credential was exposed.

A related case: the onboarding approval gate that no first device could
satisfy (4C.8) [CLAUDE.md "Template approval is an ADVISORY on the onboarding
path"].

**Mechanical answers.** Scheme 3: the template closure hash, per-device
fidelity in `blocking_reasons` (P.5, built 2026-09-26) [PLAN P.5]. The
signature to watch: "something was revoked, or refused, that nobody had
changed".

#### 8. Computed, carried, drawn nowhere

**Pattern.** The server computes a value, the payload carries it, and nothing
draws it [CLAUDE.md "The edge caches HTML and not JSON"; "four defects of the
shape" in one night].

**Instances:**
- The drift scheduler wrote `next_ts`, which nothing read (the "`next_ts`
  shape").
- The agent panel's three client guards (Phase 3.3).
- `loadOnboardPending` had no caller outside its own banner (4C).
- The DHCP review branch (Phase 2 DHCP, "for the fifth time").
- C85 (2026-09-27): the NetBox import's C8 fields in the stored summary,
  drawn nowhere.
- C96: the drift panel drew none of its last run.
- C138 (2026-09-28): drawn but unreadable (light text on near-white).

C138 marks the stated limit of the mechanised checks [OPEN_FINDINGS C138;
TESTING.md "What is NOT tested"].

**Mechanical answers.** Executing the shipped JavaScript in duktape against
real payloads (`test_agent_panel_renders.py`); `test_payload_is_rendered.py`
(7.0 (3)); `test_results_are_drawn.py` (7.1 step 1).

#### 9. "Success" meaning no exception reached the top

**Pattern.** `ok` or `success` recorded that the code did not crash, not that
the work happened [CLAUDE.md "'Success' must mean something happened"].

**Instances, as counted by CLAUDE.md:**
1. The background agent: 27 runs, zero tool calls, one `success: true` with
   nothing in it.
2. `bind_credentials_step`.
3. `_sync_list_to_netbox_impl` (`ok` with every device in `failed`).
4. The sanitiser's exit code.
5. Kea's envelope, `ok: True` around `{"result": 1}` ("Fifth instance").

The colour form arrived later: green on a partial success (C85, C121, Save
All, onboarding Create) [CLAUDE.md "Colour is part of the result"].

The exit-code cousin: "An exit code that cannot distinguish the case it is
used to check proves nothing about it", three instances (`rclone delete`,
`rclone copy`, systemd `Result=success` for a missing unit) [CLAUDE.md].

**Mechanical answers.** An agent run's `outcome` of `ok` / `failed` /
`interrupted` / `inconclusive`; Kea's `ok` decided from Kea's per-service
result; `FALSE_GREEN` and `GREEN_TOASTS` in `test_results_are_drawn.py`.

#### 10. A rule keyed on the platform when it was about the deployment

**Pattern.** A rule true of every device that existed when it was written
fails for the first device that arrives by another route [CLAUDE.md "A RULE
KEYED ON THE PLATFORM WHEN IT WAS REALLY ABOUT THE DEPLOYMENT", P.6,
2026-09-27].

**Instances:**
- `RESERVED_INTERFACES` refuses Gi1 on `cisco_iosxe`.
- `clab_target_for()` resolves an unknown lab to rcn-lab1 (C50).
- The SSH key was skipped for `cisco_iosxe` (M4).
- `VRNETLAB_INJECTS_USER` gave a ZTP render `password 0` (C52).

ZTP was the first route to break all four [P6_ZTP.md §8].

**Answer.** A search method, not a test: "anywhere the code asks WHAT a
device is to answer HOW it got here", and grep the justifications for
"vrnetlab". C52 is fixed with the form as a deployment property, pinned both
ways. No structural check is recorded.

#### 11. A status claim ahead of the thing it describes

A document or a status says a thing is done, built or scheduled, and the thing it describes is not in that state. Instances: C122 ("onboarding and NetBox Remove retrofitted" meant their results, not their previews, 2026-09-27); D6 (a register row left in Scheduled for three days after P.3 step 2 had removed the route it described, found 2026-09-29); C38 (7.2 declared built without one of its scheduled sources, found 2026-09-29). The two later ones were found by the writeup's backfill reading the scheduled rows against the code, which is what a stage close now does: acceptance item 14 requires the entry, and the entry lists the stage's findings and what became of them, so a scheduled source left unbuilt is named when the stage closes, not days later. The general rule it joins: a document asserting a property the code does not have stops the next person looking [CLAUDE.md].

#### 12. Further named families (brief)

- **Coverage inherited, not designed.** Found by adding one member: drift over
  the legacy store, clab-sync and r6, the sanitiser's hardcoded `ROUTERS`
  list [CLAUDE.md; NOTES "Coverage that was never designed, only
  inherited"].
- **A rule that never reaches what already exists.** Five instances, the
  `.gitignore` top-up the cleanest [NOTES "Five times"]. Answer: rules applied
  on access (`ensure_repo_hygiene()`).
- **Prose about code is not code; a pattern that can appear in English needs
  an anchor.** At least seven instances of a scan matching the text written
  to explain it [NOTES "A named pattern"; CLAUDE.md]. Answer: parse, never
  grep; `check_removed_definitions.py` tells a use from a mention.
- **Matching a name, a prefix or a mention.** C61, C87, C101 (twice), C103, and
  the one-home check keyed on spelling [CLAUDE.md "When a check matches a
  NAME, a PREFIX or a MENTION"].
- **The seam.** "A test that constructs its own subject cannot notice that the
  caller does not", nine instances by Phase 2 DHCP [CLAUDE.md "Running the
  tool is how defects are found"]. Answer:
  `test_server_reads_nothing_the_form_cannot_send.py`, the entry-point sweep,
  `assert_dialect()`.
- **A silently wrong record from a transformation.** `version 2` stripped both
  sides, an invented `control-plane`, masked validation, stage-7 metrics
  [NOTES "The pattern, now three deep"].
- **A method defect: a test written after the implementation encodes it.**
  Four in one week, on the rolled-back block and its revert [NOTES "Method,
  not code"].
- **Two places answer the same question.** Drift checkers, golden enumerators,
  BGP readers (C64, C69) [CLAUDE.md "When two places answer the same question
  about a device"].
- **A preview runs the real code.** C130 and C134 [CLAUDE.md]. Answer:
  `TestNoPreviewWritesTheStore`.
- **The instrument is the variable.** `ugrep` file order (C20), bytecode
  (C120), a 420-character register dump (C106) [CLAUDE.md "An investigation's
  instrument can be the variable"].
- **A claim about all time from a short window.** Three instances; the first
  the operator's (2026-09-28), the third Claude's, the same day [CLAUDE.md "A claim about ALL TIME
  needs a window that covers all time"].
- **A message describing a state that did not occur.** The sixth in one
  session was DHCP's `bootstrap_artifact` [CLAUDE.md "COMPLETENESS IS JUDGED
  PER SOURCE"].

### Rate measurements

- **Findings per commit, 7.1.** 69 commits over 20 h 41 min (ff6fc24 to
  763649e). The register went from 97 rows to 168: 69 C-rows (C60 to C128) and
  2 E-rows. At least six came from side work. "Roughly one new finding per
  commit". "The rate did not fall as the stage went on." [S7 "The forecast,
  corrected (2026-09-28)"]
- **After 7.1.** R2a and the community branch: 21 commits over 2 h 34 min
  (763649e to 995498a), 14 rows (C129 to C142), "7.1's rate exactly". "The
  rate is a property of the WORK, not of a stage." [S7, same]
- **Findings per day.** 39 new on 2026-09-26, 43 on 2026-09-27; almost every
  one came from building and running [CLAUDE.md "In this project building is
  how surveying happens"].
- **Estimate against actual.** Measured partway through 7.1: "13 hours and 32
  commits", and the rest of Stage 7 "three to four more efforts that size"
  (about 110 commits). Actual 7.1: 2.2x the commits, 1.6x the hours, so the
  remainder was re-estimated at 200 to 280 commits. The operator's reading: an
  estimate from an unfinished stage is made from the part that went to plan
  [S7, same; CLAUDE.md].
- **7.2 prediction.** Made from the finished 7.1: 40 to 70 commits over about
  a day, 30 to 50 findings, "to be checked when it closes" [S7, same]. Nobody
  checked it when 7.2 closed. **Checked at backfill (2026-09-29)**: 37 commits
  in about 4 h 03 min, about 17 findings (11 new register rows plus six with
  no ID). Only 19 of the 37 were 7.2's own step commits; the rest were
  decisions and measurements made in the same window (see the 7.2 entry).
  **The operator's reading: the correction asked for after 7.1 overcorrected.**
  The rate assumption, about one finding per commit, held for 7.1 and not for
  7.2, because 7.2 read stores that 7.1 and that week's sweeps had already
  hardened. That is a result about where findings come from, not a forecasting
  failure. The prediction held the fact and read it the other way: "four of
  those were found this week in stores 7.2 draws from" was offered as a reason
  to expect findings in the sources [S7 "The forecast, corrected"].
  **An unchecked forecast is the base of the next one**, which is why closing a
  stage now includes checking its forecast against its actuals (acceptance
  item 14).
- **Mode B (7.3 step 2), 2026-09-28 to 29.** Estimated when costed at "about
  three days to build … plan on about a week". Actual, from costing to
  acceptance on the host: about 5.5 hours of continuous work, 15 commits and 7
  findings (C191 to C197), with four real runs by the operator (three probe
  runs and the acceptance) [the 7.3 entry]. The estimate was in days of
  ordinary work and the work was one continuous session, so the two are not
  like for like. **What it means for the method** (the operator, 2026-09-29):
  the "triple it" rule came from 7.1, a stage of unbounded screen work and
  first real runs. Applied to a well-bounded piece of work whose measurement
  campaign was already scoped, it produced a number about seven times too
  high. Forecasting from a finished stage is right; forecasting from a
  DIFFERENT KIND of stage is not.
- **C188 (7.3), 2026-09-29.** About 45 minutes, 3 commits, 2 new rows (C198,
  C199). The host measurement is the result: preview 101 s to 40.9 s, apply
  102 s to 13.7 s [the 7.3 entry].
- **Phase 2 (DHCP) ledger, 2026-09-24.** 9 commits fixed things found by
  running it, carrying 15 distinct defects; the suite caught none of the 15.
  Suite green throughout, 3,276 to 3,360 tests. 9 of 15 were written that
  day, 4 the day before, 1 four days earlier, 1 five months earlier. The suite
  caught three regressions by name while the fixes were made [CLAUDE.md
  "Running the tool is how defects are found"; docs/PHASE2_DHCP.md §10].
- **Stage 4C probe.** Seven defects live in code the suite passed; the suite
  had "2,700+ tests" [NOTES "What the Stage 4C probe found"].
- **The branch site, 2026-09-24.** "Ten defects surfaced walking the deploy
  path end to end for the first time", suite green throughout [CLAUDE.md "A
  path that has never carried anything fails on first use"].
- **P.3, 2026-09-26.** Scoped as five items; it found eleven more nobody had
  scoped [NOTES "What P.3 cost and bought"].
- **Verify.** Ten defects in two days (2026-09-27 and 28), none found by
  reading for correctness [NOTES "ten independent ways"].
- **"Three-for-three real runs."** S7 records it: "Three real runs, three sets
  of findings no test could reach (C70, R2a, R1): the rate has not dropped"
  (2026-09-28) [S7 "7.1's stated limit"].
  - **C70**, the restore. The first run found C82, C83, C84; the re-run
    (2026-09-27) found C108, C109, C110; and "the operation correct and its
    surroundings broken: C92, C97, C98, C99" [OPEN_FINDINGS C70].
  - **R2a**, the NetBox previews (2026-09-28). C130, C131, C133, C134, C135;
    25 of 39 import-preview lines were phantom [S7].
  - **R1**, onboarding on a throwaway (2026-09-28). C147, C148, C151, C152,
    C153, C154; closed C57; proved the reboot [S7 "R1's total"].
- **Register size over time** (counted from rows, each as recorded):
  - 59 open at 2026-09-27 [OPEN_FINDINGS "Count"].
  - 92 rows in the open sections before the 2026-09-28 triage, of which 31
    were already done [OPEN_FINDINGS "Triage"].
  - 61 open at 2026-09-28; 26 of 61 open rows were stage work [OPEN_FINDINGS
    rules].
  - 45, then 47 open at 2026-09-29, with 37 to 38 scheduled into stages
    [OPEN_FINDINGS "Count"].
- **Suite size and run time.**
  - Phase 0: 209. Phase 1: 307. Phase 2: 385. Phase 3a: 507 (all 2026-09-20)
    [NOTES Status lines].
  - "1133 tests passed" with a whole function deleted, and "1656 tests"
    parsing no JavaScript; dates Not recorded in those headings [NOTES].
  - 4C.8's first genuine run: 2,638 passed, 6 failed [NOTES].
  - Phase 2 DHCP: 3,276 to 3,360 [CLAUDE.md].
  - P.3, 2026-09-26: 3781 through 3950 passed at `5b087c4` [PLAN P.3].
  - TESTING.md, 2026-09-26: 3,942 tests in 137 files; CI about 4 minutes.
  - P.4 host `--offline`: 4004 passed plus one planted failure in 287.81 s
    [PLAN P.4].
  - 2026-09-28 laptop: 5025 passed, 42 s with `-n auto` on 24 cores against
    121 s serial; CI jobs 186 to 224 s [CLAUDE.md "Tests"].
  - 5344 passed on the tree of `e986e66` [CLAUDE.md "A CHECK THAT READS A FILE
    SOME EARLIER RUN WROTE"].
  - The first pristine-checkout run gave 5 failures and 19 errors (found
    2026-09-26) [TESTING.md].

### Where the product stood

- **Phase 0, 2026-09-20.** Foundation, portability and safety: NetBox writes
  fail-closed behind a master switch and a one-shot token; no user-facing
  features; 209 tests [NOTES "Phase 0"; git `eac9c5e`, `e7c3e66`].
- **Phase 1, 2026-09-20.** A device list could be sourced from NetBox through
  the single dispatch point, and the GUI read inventory intent from NetBox;
  307 tests [NOTES "Phase 1"; git `d9e868d`].
- **Phase 2, 2026-09-20.** Golden configs lived in a per-list git repository,
  one write path, one call one commit; 385 tests [NOTES "Phase 2"; git
  `4875e67`]. Phase 2b's remote followed on 2026-09-20 and 21 [git
  `651ac82`, `710f7d8`].
- **Phase 3a, 2026-09-20.** Config parsed to host_vars and round-tripped; r1
  92.2% modelled and s1 100%, both 100% fidelity; 507 tests [NOTES "Phase
  3a"]. Later: 100% modelled on all nine under the depth-aware comparison
  [CLAUDE.md "Templatization"].
- **Phase 3b, 2026-09-20.** (No summary was recorded at the time: composed at
  backfill from CLAUDE.md's description and the commit date.) A per-network template library with an approval
  gate and a computed deployability gate; nothing in 3b opened a socket
  [CLAUDE.md "Template library and the deploy gate"; git `6735f97`].
- **Phase 3c, 2026-09-20.** (No summary was recorded at the time: composed at
  backfill, likewise.) Deploy from committed intent, merge-only, confirmed
  by hash: "The only part of the NSoT work that reaches a device" [CLAUDE.md
  "Deploy from template"; git `3be6550`].
- **Stage 2, 2026-09-22.** The rcn-lab1 redeploy ban lifted by a successful
  redeploy [PLAN "STAGE 2 ... COMPLETE"].
- **Stage 3.3, 2026-09-23.** The first scheduled drift run since 2026-08-30:
  9/9 clean against committed goldens [PLAN "STAGE 3.3 COMPLETE"].
- **Stage 4C, 2026-09-23.** "Half-run": the wizard had not yet proved
  end-to-end onboarding or Remove, and had found seven defects [NOTES "What
  the Stage 4C probe found"]. A later clean run proved onboarding end to end
  and left its teardown unprovable; its date is Not recorded [CLAUDE.md "A
  teardown that cannot be measured has not passed"].
- **The branch site, 2026-09-24.** "The first configuration this tool
  AUTHORED": two devices, intent written by hand, previewed, confirmed,
  merge-only, verified [CLAUDE.md "The branch site landed"; git `8c948bd`].
- **Phase 2 DHCP, 2026-09-24.** Proven: a device the tool never addressed was
  found by its Kea lease, then reached, captured, rotated, cleaned, recorded
  and promoted [CLAUDE.md "PHASE 2 IS PROVEN"].
- **P.1, 2026-09-25.** Complete: switch syslog restored, nine devices
  heartbeating on per-device measured windows, a silenced s4 alerting alone
  [PLAN "P.1 COMPLETE"].
- **P.2, 2026-09-26.** A NetBox backup with a tested restore, "done except its
  unattended watch" [PLAN "P.2 ACCEPTANCE STATUS"; PLAN "Scope of what
  remains"].
- **P.3, 2026-09-26.** Complete: every device-changing path guarded or gone,
  one gate table, verified actors in commits; 3950 passed at `5b087c4` [PLAN
  "P.3 IS COMPLETE"].
- **P.4, 2026-09-26.** Jenkins removed; CI on GitHub Actions with the host's
  versions; `nmas-deploy` gates on the target commit. Acceptance items 1 to 3
  met; item 4 not yet observed [PLAN P.4 "ACCEPTANCE"].
- **P.5, 2026-09-26.** Built: approval is the template's closure hash and its
  approver; onboarding no longer revokes approvals [PLAN P.5].
- **P.6, 2026-09-27.** Complete: Lab 8 end to end; a configless device got its
  address from a reservation the tool wrote, fetched its config from the tool,
  and survived a reboot; teardown clean [PLAN P.6; P6_ZTP.md §8].
- **7.0, 2026-09-27.** Built, "awaiting the host check": reachability,
  invalidation, payload-to-render and nine-concept checks, each with an
  allowlist that only shrinks [S7 "7.0 built"]. The host check's result is Not
  recorded.
- **7.1, 2026-09-28.** Acceptance met on 5025 passing tests: every operation
  that changes a device or the record has one preview, one confirm, one result
  and one record, none needing a console. Its stated limit closed by R1 and
  R2b the same day [S7 "7.1 acceptance"; "7.1's stated limit"].
- **7.2, 2026-09-28.** "7.2 is built": Needs attention, the reader-job pattern
  (job health, Grafana, freshness, integration health, CI verdict,
  reachability) and the live-data contract [S7 "7.2 step 19"].
- **7.3 so far, 2026-09-28 to 29.** Built so far:
  - the retire screen;
  - seed intent (step 1), whose acceptance run remains;
  - Mode B removal (steps 2a to 2c), accepted on the host;
  - Save All reading its devices at once, with the preview a job that
    announces its result (C188, 2026-09-29: preview 101 s to 40.9 s, apply
    102 s to 13.7 s, and a second earned baseline, `baseline/20260929T063600Z`).

  The acceptance run removed r2's `load-interval 30` and earned
  `baseline/20260929T060249Z` [S7 "7.3's retire screen BUILT"; "7.3 step 1
  BUILT"; NOTES "The line the tool could not remove"; git `03aeabe`]. Rotate,
  persist and the Device page itself do not exist yet [S7 "What does not
  exist yet"].

#### Sources read (cross-cutting)

- CLAUDE.md (project instructions, including "Things to Keep in Mind" and
  "Open findings register")
- docs/NSOT_WRITEUP_NOTES.md: phase status lines, the named-family sections,
  and the dated sections from P.3 onward
- docs/NSOT_STAGE7_PLAN.md: 7.0 built, 7.1 acceptance and stated limit, "The
  forecast, corrected", 7.2 steps, 7.3 status, "What does not exist yet"
- docs/NSOT_PLAN.md: Stage 2, Stage 3.3, "Scope of what remains", P.1, P.2
  acceptance status, P.3, P.4 acceptance, P.5, P.6
- docs/OPEN_FINDINGS.md: rules, triage, Count, and the rows cited above
- docs/TESTING.md
- docs/P6_ZTP.md §8
- read-only `git log` for commit dates and hashes
