# End of session: where Phase 7 stands

## EVENING, 2026-10-13 (19:00 to about 21:00 UTC; 13:00 to 15:00 UTC−6)

**Committed and pushed:** fb815743 (C741, C746, C747, C751; CI #742 green) and eae5c6c2 (C752,
C753, C754, the bind step, Phase 8's decisions recorded).

**The alias `dr` (the operator's URGENT item): nothing scheduled used it.**
- `dr` was the operator's mc alias for the replica MinIO, LXC 103 `minio-dr` on the
  hypervisor. The rotation removed it because the replica's own root user is also named
  `minioadmin` (its password is not the default). That was the script's defect (C752, fixed).
- Searched on all three hosts: crontabs, cron.d, systemd timers, scripts and units, `MC_HOST_`
  variables, shell histories and rclone. Nothing names `dr`.
  - The 08:30 UTC nightly job is the hypervisor's VM backup (VMs 100 and 102, to local
    storage). It touches no MinIO.
  - The hourly lake archive uses its own user, `lake-archive`, not the root.
  - rclone's only remote is B2.
- What does use the replica's credentials is this MinIO's own bucket replication (`loki`,
  `raw-telemetry`, `thanos` → dr).
  - It kept working after the rotation: 27 `loki` objects were written on each side since the
    19:42:24 UTC restart, and the newest object is identical on both.
- **Waiting on the operator:** moving each replication target onto a least-privilege
  `replicator` key on the replica (C753). Writing that step was refused to the agent by the
  auto-mode classifier as a secret-store write, so it is the operator's to allow or to write.

**Bind and firewall (C749's follow-up): DONE, run by the agent 20:51 UTC, PASS 13 of 13**
(the host runs 4e88889b).
- From the lab host, 9000 and 9001 now refuse, and ufw logs each attempt as `[UFW BLOCK]`.
- The console is reached through an SSH tunnel: `ssh -L 9001:127.0.0.1:9001 <nmas-host>`.
- Two earlier runs stopped and undid themselves: C755 (sudo reset the environment) and C756
  (the listener check ran before the console bound its port). Both are fixed.
- The step: `scripts/host-steps/minio-bind.sh`.
- Measured first:
  - every client of 9000 is this host over loopback, or Loki on docker0;
  - ufw's incoming default is ALLOW;
  - both ports answered from the lab host.
- The step:
  - the console goes to 127.0.0.1:9001;
  - ufw allows 9000 in on docker0, then denies 9000 and 9001 otherwise (logged);
  - an undo is built in.

**"bucket versioning: unreadable with this key" (the operator's question):** that read is made
with Mercury's OWN key, never the typed one. Mercury's policy (`mercury-rw`) holds no
`s3:GetBucketVersioning`. The wording named the wrong key (C754, fixed). Versions were always
listed, because `ListBucket` allows it.

**The archive objects (C754):**
- The two objects the C743 step named are gone: no version and no delete marker.
- The bucket holds `ai-family/20261013T161220Z` (16:12:21 UTC). It is clean under the fixed
  check: 39 files, 0 holding a maskable value.
- The C743 step now names that object.

**Phase 8:** the operator's decisions are recorded in IBN_DESIGN section 9 and PHASE8_PLAN
section 9, and applied to the class table, the catalog gate, section 7's numbers, 8.0's
prerequisite (E18), Translate's scope and the ranking.

## AFTERNOON, 2026-10-13 (16:20 to 18:50 UTC): the operator's answers, worked

The host runs c40d9440 (deployed 18:43:57 UTC, CI #740).

**Done and walked:**
- **C743 and C744** (1136827d): the two archive FAILs were false.
  - Masking was not idempotent: a second pass turned `secret 9 <redacted>` and
    `snmp-server host … version 2c <redacted>` into placeholders. Measured on both objects
    (counts only), nothing was unmasked.
  - Fixed, and an archive is now scanned BEFORE it leaves the host (`put_archive`).
  - c734's stray backslash fixed; the host runs Python 3.12.3, so the version was never the
    cause. Every host step's Python is now compiled by a test.
- **C745 registered:** masking does not know OSPF, BGP or SNMPv3 key shapes. Neither first
  archive held any.
- **E19 (C740, closed):** pool 4 h, reserved 7 d by the class `mercury-reserved`, management
  7 d (every ZTP-subnet client takes a class's lifetime), computed timers at 50%/80%.
  - Host step PASS 9 of 9.
  - h1's renewed lease measures 604800 / 302400.
- **C718 (closed):** Decline… and Undo decline…, built from the approved board and compared
  with it at 1440 and 390. r6's IP SLA declined on the host in the operator's words (commit
  7790304e); Coverage and the IP SLA page read it as declined.
- **C681 (closed):** 2001:db8:20::100 deleted after the interface check.
- **Break-glass and Save All:** confirmed from the records. The export was current, 16:33:25
  UTC, 9 devices, intact. The baselines are 03:08 and 03:24 UTC from `save_all`. Dropped from
  the waiting list.
- **The ten "partly" acceptance criteria:** reread against the code, and the table in
  NSOT_STAGE7_PLAN updated. 1, 2 and 16 close at cutover; 3, 4, 5, 6, 10, 11 and 14 each name
  what is left.
- **Canvas v127:**
  - E3 and F3 (and their phone boards) replace E2 and F2, for sign-off.
  - A, B and C have the live shell.
  - C718 is marked approved, and the stale FOR SIGN-OFF titles are fixed.

**Waiting on the operator, in order:**
1. **The archive steps, one at a time.** Step 1 is `c743-delete-archive-objects.sh` (a
   delete-capable MinIO key, typed hidden). Then c734's counts, the D15 archive and its
   delete, and Oxidized's archive and its delete, each with what PASS looks like.
2. **Sign-off on E3 and F3.** Measured for them:
   - Syslog reaches Loki as `network_syslog`, and SNMP traps as
     `loki.source.journal.snmptrapd`. A first read with Loki's short default window saw only
     syslog; it was corrected the same day.
   - Loki has no `severity` label.
   - Loki keeps 2 y and allows 30 d an ask; Prometheus keeps 90 d.
3. **Boards still waiting:** C589 AdjacencyTransient; C537/C538's TopBarDesktop, TopBarPhone,
   Reattach, FinishJob and BatchExpected.
4. **CLAUDE.md:** DONE 2026-10-13. The operator pasted the Environment line (and the D15
   lines), and the TFTP root's code left in the same commit (tag `pre-remove/tftp-root`).
5. **s3's manual rotation: CLOSED 2026-10-13.** Run by the operator, step by step:
   - a break-glass export first (22:13:01 UTC, intact);
   - the console fallback tested (`s3>` straight after the banner; no `enable` secret on s3,
     and `line con 0` has no settings);
   - the rotation from s3's device page at 22:28:56 UTC, verified, recorded, and persisted in
     the same job at 22:29:58;
   - a new export at 22:30:50, intact; the 22:13 record retired.

   Read back by the agent: the break-glass card says "Every device's credential in use is in
   the record exported 2026-10-13T22:30:50Z", and Needs attention holds no row.

   The records also show an earlier device-page rotation of s3 at 16:16:49 UTC, persisted at
   16:17:15, so the 09-21 password was already retired then. **The operator confirmed: they ran
   it (question closed, 2026-10-13).**
6. **D15's leftover stores (C1), step 1: PASS 2026-10-13, the operator's run.**
   - The archive is `s3://mercury/archives/ai-leftovers/20261013T232939Z.tar.gz`, sha256
     `ae94441010925cf3b913d732b73bc7fb23387c5dd3a414d156822076e30768e0`.
   - It reported 5 of 5 checks asked, PASS, and the delete check NOT ASKED.
   - **Its `--delete` waits until the AI family's code is gone** (that code recreates
     `chat_histories/` on every restart). Then run:
     `cd ~/python/Agentic_NMAS && bash scripts/host-steps/d16-archive.sh ai-leftovers --delete
     ae94441010925cf3b913d732b73bc7fb23387c5dd3a414d156822076e30768e0 lists/default/topology_cache.json
     lists/default/change_log.json lists/default/network_kb.json lists/default/compliance_policy.json
     lists/default/variables.json lists/default/playbooks chat_histories`.
7. **Lab 7 first (the operator, 2026-10-13):** "Unit Testing and Code Coverage", due Monday
   2026-10-19 at night, with the code done by Saturday. After it, in order:
   1. the AI family's shared pieces move out;
   2. the removal, tagged `pre-remove/ai-family`;
   3. the ai-leftovers `--delete` above;
   4. Backups (C632 first);
   5. today's pages;
   6. the stable trap-label host step, before F3 is built;
   7. C753's replicator key and replica root rotation.
6. **Next, by the operator's order:** D15's removal after its archive, Backups (C632 first),
   then today's pages.

## MORNING REPORT: THE OVERNIGHT RUN, 2026-10-13 (05:20 to 09:35 UTC; 23:20 to 03:35 UTC−6)

### Deployed and walked on the host

Every commit was gated, pushed and green on CI before its deploy; each deploy was `nmas-deploy
--wait`, outside 08:30 to 09:10 UTC, with no rotation or device operation running (checked
before each).

| Item | Commit | CI | Deployed (UTC) | The host walk showed |
|---|---|---|---|---|
| C12 (C735), Neighbours draws RIP and RIPng | 1fd8c20e | green | 05:42:16 | RIP and RIPng neighbours drawn up from the RIP reader's stored answer |
| 1, C734, the five sealed stores | e3b86d4a | #719 | 06:08:52 | the app came up through the widened startup guard, no key refusal in the journal; the deployed registry holds all five stores |
| 2, rotation writes no router.db | beace862 | #720 | 06:20:10 | router.db last written 2026-10-06 19:57 UTC, before rotation's last runs; the containers exited for 4 to 5 days. Rotation no longer runs the helper (a test holds it) |
| 3, C719, r6's target | c1d08e5a | #721 | 06:32:10 | r6's suggested target is 10.255.0.1 (s3's Vlan99), no longer 10.255.1.23 |
| 4, C736, RIP on Needs attention | 03b436d6 | #722 | 06:43:02 | the adjacencies reader run once: 64 adjacencies on 9 devices, RIP and RIPng among them, none failing, none unmeasured, no rows |
| 5, C737 (C14), hidden defaults | ee1a7a76 | #723 | 06:56:22 | the config check over Default: Intent-Match 9 of 9, nothing newly failing |
| 6, C738, criterion 13 | 00a650e3 | #724 | 07:17:22 | Settings › Installation and History served, gated controls drawn from `may`, the refused ones naming their reason |
| 7, D15 step 1, C739 | 4364e76d | #725 | 07:37:19 | the live drift source holds 0 rows (9 of 9 clean); the v2 page served with the drift row's two links |
| 7, D15 step 2 (script only) | 356bbc4c | #726/#727 | with c8d02a66 | a host step, not run (parked, below) |
| 8, D16 Quick actions | c8d02a66 | #728 | 07:59:01 | the routes gone; today's device page renders without the section; then the store archived and deleted (below) |
| 9 and 10, boards and E19 | cd148a78 | #729 | with 7111fec0 | docs and the canvas only |
| 8, D16 Device files, Bulk file actions, the TFTP setting | 12df1839, cb9ac2ec, 7111fec0 | #730/#731, #732/#733, #734 | 09:29:03, with 7065fff7 | the 12 removed routes (the file, bulk, TFTP and quick-action routes) answer 404, where the same walk before the deploy read 403 (refused at the gate) or 302; today's index and a device page render (200), the device page has no file tab and no TFTP mention; the index's three TFTP mentions are the TFTP root's field, kept (parked 7); `/v2/` 200; no app errors since the restart |
| 8, Oxidized's host step | 90bd8dbd; fixed by 1136827d, b418d11f (C757), 46599b01 (C758) | #735 RED, then #747 | 46599b01, 21:47:31 | **CLOSED 2026-10-13 (the operator's run):** archive `s3://mercury/archives/oxidized/20261013T210823Z.tar.gz` (sha256 be1dd23b…), PASS 7 of 7; then `--delete`, PASS 7 of 7 asked (2 not asked): both containers removed, the six router.db-named files shredded, /opt/oxidized removed, none left on the host. The archive is the only copy |
| 12, the stepper retakes; C742 (the red run's fix) | 7065fff7 | #736 | 09:29:03 | the shots compared (below) |

### Parked for the operator, in the order to take them

1. **C734's count (read-only, a minute):** `bash ~/python/Agentic_NMAS/scripts/host-steps/c734-sealed-store-counts.sh`
   on the NMAS host, as your own user (it refuses root). You asked for this one parked. It prints the number of sealed values per store, never a value. If a store
   holds sealed values the registry did not expect, that is a new finding.
2. **D15, the AI family's archive:** `bash ~/python/Agentic_NMAS/scripts/host-steps/d15-ai-archive.sh`,
   as your own user. It masks every text file of the AI stores, seals the provider config and the
   `ANTHROPIC_API_KEY` with the application key (never plaintext), uploads to
   `archives/ai-family/`, reads it back and checks its sha256. Then run it with `--delete <that sha256>`
   to delete the stores and the key's `.env` line. **Then the AI family's code can be removed**
   (it was not, because the archive comes first). The agent could not run it: the hook refuses
   reading those stores, and the key is a secret.
3. **Oxidized's retirement:** `sudo bash ~/python/Agentic_NMAS/scripts/host-steps/d16-oxidized-retire.sh`
   (archive: text masked, Oxidized's config files sealed, the git store's history as masked
   text, router.db and its four copies left out), then `--delete <its sha256>`, which removes the
   two exited containers (`oxidized`, `oxidized-pre-c143`), shreds router.db and every copy
   (`shred -u`), and removes /opt/oxidized. Needs root: the store is the container user's and
   router.db is 0600.
4. **Board sign-off, C718's Decline / Not applicable** (canvas v123, `CoverageDecline.dc.html`):
   approve or mark up; it is built once approved.
5. **Board sign-off, E2 and F2, History › Query** (canvas v124, `QueryBuilderMetrics.dc.html`,
   `QueryBuilderLogs.dc.html`, the history-q page): drawn with the real caps (1000 points per
   series, 200 series, 200 log lines, 30 days). Not built.
6. **E19's decisions** (C740, docs/DHCP_LIFETIMES_PROPOSAL.md, section on decisions): reserved
   addresses 1 day valid / 12 h preferred through the client class `mercury-reserved`, pools 4 h
   / 2 h, management 7 days, discovery's 300 s unchanged. Measured: every lease today lasts 365
   days.
7. **(DONE 2026-10-13, item 4 above.) A CLAUDE.md line, to retire the TFTP root:** its last readers left with the file families
   tonight (app.py imports `TFTP_ROOT` and `ensure_tftp_root` and uses neither). In Key
   architecture › Environment, replace
   `` `NMAS_HOST`, `NMAS_PORT` (5000), `NMAS_HEADLESS=1`, `NMAS_TFTP_ROOT`; `` with
   `` `NMAS_HOST`, `NMAS_PORT` (5000), `NMAS_HEADLESS=1`; ``. After that, `tftp_root` and
   `NMAS_TFTP_ROOT` leave the code in one commit.
8. **C733's five decisions** (docs/CREDENTIAL_STORE_REDESIGN.md section 9): after Phase 7, not
   urgent.
9. **Still waiting from before:**
   - the rotation policy: every 7 days, at most 5; clear the field if you want no cap;
   - the orphan lease 2001:db8:20::100 (C681): delete it on your word;
   - break-glass export and Save All.

### Removed tonight

| Family | Restore tag (the last commit with it) | Data |
|---|---|---|
| Quick actions | `pre-remove/quick-actions` (356bbc4c) | archived `s3://mercury/archives/quick-actions/20261013T075929Z.tar.gz`, sha256 `804eca43aa73ab12e323c9a18c0a14f1d39859ef49c6cec40c4fcb5b24cc9fa3`. Read back identical, nothing in it Mercury would mask, then the store deleted by that checksum |
| Device files | `pre-remove/device-files` (cd148a78) | none of its own |
| Bulk file actions | `pre-remove/bulk-file-actions` (12df1839) | none of its own |
| The TFTP setting | `pre-remove/tftp-setting` (cb9ac2ec) | `tftp_server_ip` stays declared RETIRING for one release (a rollback finds it); no file |

**Not removed tonight, and why:**
- **The AI family (D15):** waits on its archive (parked, 2 above).
- **Backups:** waits on today's template editor (C632). Its store is one the agent may not
  read, so its archive is a host step too.
- **Today's pages (`/`, `/device/<ip>`):** CUTOVER's condition holds (no PLANNED or PARTLY
  BUILT row), but the AI family and Backups "go with today's pages", and each needs its
  archive first. So today's pages come out after 2 above and Backups' archive, in one commit
  tagged `pre-remove/todays-pages`.
- **Oxidized:** its code left at Phase 3; its containers and store were removed 2026-10-13
  (the D16 row above, closed).

### What went wrong, and the state it was left in

- **One commit was stacked on a running CI:** c8d02a66 was committed while 356bbc4c's CI was
  still running. Both came back green, so nothing was left broken, but it broke "CI green
  before the next". After that, every commit waited for its CI.
- **CI #735 went red on 90bd8dbd (the Oxidized script).** A concurrency test timed its control
  with sleeps, and a loaded runner read 3 sessions at once where 4 were allowed; the commit
  touched no code that test runs. New work stopped. It was fixed forward in 7065fff7 (C742,
  opened and closed): the test now waits for its overlap. It is shown able to fail both ways,
  and the deploy waited for that commit's CI.
- **C700's 24-hour reading came late:** it was read and closed tonight (cd148a78): r1 had 1
  failure (p99 4.1 s), s3 had 5 (p99 6.7 s).
- **Hook refusals, none worked around:**
  - the inventory script named `checkpoints`;
  - the LISTS_DIR counting script;
  - a read of Proxmox's backup jobs;
  - a heredoc into python, redone through the Edit tool.

  Each refused read became a parked host step or was dropped.
- **The acceptance table in NSOT_STAGE7_PLAN still said "not met" for criterion 13.**
  Corrected tonight. Its other rows predate a lot of the work since, and need a reread at
  Phase 7's close.

### Item 11: do E17 (C556) and E18 belong to Phase 7's definition of done?

**No, neither does.**
- **E17 (C556)** is tier "NetBox Phase 1", bucket B. It blocks NetBox owning devices, not Stage
  7.
- **E18** is Phase 4 step 2 (docs/NSOT_PHASE4_RECORDS_POSTGRES.md, approved 2026-10-08). It
  would close C159, C156, C237, C360, C361, C364, C365 and C368, all tier "Phase 4".

Neither is one of Stage 7's 16 acceptance criteria, and neither is a CUTOVER condition.

### Phase 7's definition of done: still open

1. **Cutover:**
   - the AI family and Backups (each after its archive);
   - then today's pages;
   - Oxidized's host remains (3 above): done 2026-10-13, the D16 row closed.
2. **Acceptance:** criterion 13 is met as of tonight. Rows 1 to 6, 10, 11, 14 and 16 read
   "partly" in a table that predates much of the work. Several of them (1 reachability, 6 one
   pattern, 16 no duplicated function) close by construction when today's pages go. Each is to
   be reread against the code at close.
3. **The writeup:** 7.8's entry is owed when 7.8 closes (today's pages gone). Tonight's
   removals, C734 to C742 and the D15 and D16 host steps go into it then. The notebook's last
   entry is 2026-10-10.
4. **Item 12** (the stepper's board-fidelity retakes, desktop and phone): done. The shots
   were retaken at 1440, 1280 and 390, and every region's verdict in docs/fidelity/stepper.md
   stands. One wording defect was registered as C741 (C, not fixed, by the sweep rule): the
   running step's note says "(last done: read_back)", naming the step that is running as done,
   by its code name. On the phone the full shot is 488 px wide, but that is Firefox's narrowest
   window, not the page scrolling sideways.

## PHASE 7 LIST, A AND B DONE, 2026-10-13 (03:30 to about 05:00 UTC; 21:30 to 23:00 UTC−6)

**Deployed and walked on the host (running d21c450 since 04:45:49 UTC):**
- **A, rotation follow-ups:** C727 (the run's clock moves), C728 (a held run's one publish
  names every commit; the golden-event and Prometheus hooks read them all), C726 (a verify
  login's failure logged with its kind; a timeout is tried once more after 30 s before any
  revert), the halt's words (both ways it clears), the policy cell (8 in its scope, 1 outside,
  read on the host). A blank "at most" stores no cap (the live 5 was carried by the 02:53 save,
  whose field showed the stored 5).
- **A7, the key (C729, open):** MinIO holds no key; the nightly VM image holds the key beside
  the stores. Built: no key is ever made for a sealed store (a missing key, or a link to a key
  disk that did not mount, refuses by name and the app does not start); the host step
  `scripts/host-steps/c729-key-disk.sh`. Not run: it is the operator's (below).
- **B8 (C731, closed):** the config check judges goldens (save_golden's rule, also on a
  goldens-only commit), a top-level intent key holding something no template names, and
  password hashes by shape. Host: 59 pass, 0 fail. The config repository's pin moved to
  d21c450 (commit fcd17ab, pushed), so GitHub runs the same checks.
- **B9 (C732, closed):** a full deploy reads back every line it sent (no extra read); a line
  not read back makes verify not pass, no rollback.

**Waiting on the operator (replaces the list below):**
1. **C729 is DEFERRED (the operator, 2026-10-13), risk accepted:** folded into the credential
   store redesign (C733, docs/CREDENTIAL_STORE_REDESIGN.md, after Phase 7). Its host step
   refuses unless the deferral is lifted; the startup guard stays. The redesign's five
   decisions (its section 9) are the operator's, after Phase 7.
2. **The rotation policy:** now every 7 days with "at most 5"; clear the field and save if no
   cap is wanted.
3. **The config check's run on GitHub** for fcd17ab (the pin move): one run, green.
4. **Break-glass export and Save All**, as planned.
5. **The orphan lease** 2001:db8:20::100: delete on the operator's word (C681).

**Next, in order:** C12 (Neighbours: RIP and RIPng), C13 (C718 Decline, C719), C14
(platform defaults in comparisons), E18, D15, D16, C11, E17, E19.

## AFTER THE RECORDING, 2026-10-13 (about 03:30 UTC): the freeze lifted

The operator recorded the Labs 4 and 5 Part 2 video and lifted the freeze.

**Proven tonight on the host:**
- **The unattended rotation (C724, closed):** the timer's run at 01:41 to 01:47 UTC rotated
  r3, r4, r6, s2 and s4 with no person, each commit `Source: scheduled_rotation`,
  `Actor-Verified: none`, one push for the run. Nothing due after it.
- **The config pipeline (C725):** Mercury's pre-commit check over the whole repository passes
  (9 devices, Intent-Match 9 of 9, 1.7 s); the workflow's trigger fixed (acd67f2: `branches`
  beside `tags-ignore`; `tags-ignore` alone ran no branch push) and installed (4264c22).
- **DHCP:** h1's four orphaned IPv6 leases deleted with Kea's lease6-del (02:00 UTC); h1
  holds ::107 alone. ::104 predated the IAID pin.
- Deployed: f90e90c (one break-glass row), acd67f2 (the workflow), 4f09006 (the stepper's
  steps wrap). The run's frozen clock (C727) fixed after, in this commit's release.

**Waiting on the operator:**
1. **The rotation policy:** set `default` to every 30 days (the operator's plan after the
   recording) and clear "at most" again (the live cap is 5: the blank was saved before the
   release that reads blank as no cap). A policy is a person's to set.
2. **One more orphan lease:** 2001:db8:20::100 (a generated DUID left by the agent's slip on h2
   during the dhcpcd pinning; no reservation names it; h2 holds ::101). Delete it the same way
   on the operator's word; C681 closes then.
3. **The config check's run on GitHub for 4264c22:** one run, green, was not yet confirmed.
4. **Break-glass export and Save All** for a fresh baseline (the operator's plan).

**Open from tonight:** C726 (a host-shell rotation of s1 refused at verify; the 00:44 fleet-wide
SNMP drop makes load the likely cause, unproven), C728 (a held push's hooks see one commit),
and the fact-check's corrections to the write-up (given in the session, not filed).

## NIGHT, 2026-10-12 to 13 (22:30 to about 00:30 UTC): the Labs 4 and 5 Part 2 deadline

**FREEZE in force** (the operator): no AI-family removal, no stepper conversion, no query
builder, no 7.8 removals until the operator says the submission is in; only fixes for the demo
path.

**Built, deployed and walked on the host:**
- **C724, scheduled credential rotation** (8e8c799, b0869a1, b6a2951 and the slug fix): a policy
  per credential profile (every N days, a window, at most K a run, optionally only named
  devices), a timer (every 5 min, one scheduled run per policy in any 24 hours), Rotate due
  devices now, credential age and due date on Credentials and the device page, records,
  a CRITICAL row on the first failure, the break-glass staleness row.
  **The policy set by the operator:** `default`, every 1 day, any hour, at most 1, only r2, s1.
  **The first unattended run** rotated s1 at 23:56 UTC and its record's commit was refused (a
  malformed Source slug, fixed); it stopped as designed and raised the CRITICAL row. s1 was
  recovered (nmas-rotation-recover: recorded; nmas-persist-native: PERSISTED). Mercury logged
  in to s1 throughout. The timer starts nothing more until a person's run finishes cleanly:
  r2 stays due for the recording's Rotate due devices now, which also clears the row.
  **After the operator's recording: set the `default` policy to every 30 days (only r2, s1),
  as the operator asked.**
  **s1, 00:44 UTC:** a settle through the fixed code (the scheduled run's call, from the host
  shell) reverted at verify (C726, UNKNOWN): s1 is on its working credential, its golden still
  lacks the rotated secret (the drift row stands), the halt stands for the recording's Rotate
  due devices now, which takes r2 (a person's run is not held by the 24-hour rule).
- **C725, the config pipeline** (b0869a1, e1289df): `scripts/nmas-config-check` (no device, no
  secret) before every Mercury commit of intent, profiles, templates or DHCP, and GitHub Actions
  in the config repository on every push and pull request. Host step run: 7 of 7 PASS; the
  real repository passes every check (9 devices, Intent-Match 9 of 9, 1.6 s); the workflow and
  pin committed (239ca19) and pushed; **the operator saw its first Actions run green.**
- `docs/LAB_REQUIREMENTS.md`: the objectives and the demo script, in recording order.
- `docs/PUBLIC_RELEASE.md` section f: device-login 2FA, registered, not built.

**Held until the submission is in:** C722's host step (it restarts Alloy on the logs demo's
path; Needs attention lists it as owed until then). Reading the Actions verdict into Mercury
needs the operator's read-only token (Actions and Checks: read), not tonight.

## EVENING, 2026-10-12 (about 20:05 to 23:30 UTC; 14:05 to 17:30 UTC−6)

**The one stepper is done (C716 closed).** Every operation page draws its progress through the
one component, or is named with why not (docs/fidelity/stepper.md; tests/test_one_stepper.py):
- On it, as it runs: Save, the batch apply (every multi-device deploy: IP SLA's Send, the
  profile's Apply, Coverage's Deploy missing, Re-apply), Deploy, Restore, Reload, Rotate, Adopt,
  Capture, onboarding's lifecycle (the pending page), Update (its script sets each step as the
  updater reports), NetBox's preview and import (redrawn as each phase moves).
- One request each, so their RESULT draws the steps reached: Persist, Verify, Retire, the DHCP
  writes.
- Its bar and counts only: Show commands and the logging-path test (their rows are the answers).
- Does not fit: Template approve (no running state; its rows are the comparison's evidence).
- Found on the way, fixed: **C723**, a DHCP write that failed after Kea held the change said
  "Nothing was changed".

Also: **C720** (Ask your own at half a screen) deployed 21:25 UTC and checked. **C721** (the
query builder): found on the first mockups canvas, restored as boards E and F on History, Query,
your sign-off with changes recorded; to build. **C722** (a `device` label at Loki's ingest)
registered; to build.

**CI run #698 (951fe99) went red** on C567's flake (the suite-bound probe; this change touched
neither), its fourth firing, and the first with no stack in the report at all. Fixed forward
in the commit that finished the stepper: the report now says whether a stack file was absent or
empty, so the next firing tells the two apart. 951fe99 deploys with that commit once CI passes.

**Waiting on you:** as below (C718's board, C719, the AI agent's family, sitting 3, C700's
reading due 2026-10-13 05:06 UTC). Sitting 3 can now exercise every converted page. **178 open.**

## AFTERNOON, 2026-10-12 (about 12:00 to 19:30 UTC; 06:00 to 13:30 UTC−6)

Every commit went through the gate, was pushed and deployed once CI was green, and was checked
on the host. **One CI run went red** (c638aad, run #691): CLAUDE.md names `deploy/topology/`,
which the topology removal emptied; the laptop's leftover empty folder had passed the gate.
Fixed forward in 5cdd353 (the path check now asks git, C592's class; a README holds the folder
until your CLAUDE.md edit below). No device's configuration was changed; nothing ran on s3 or
between 08:30 and 09:10 UTC.

**Done, deployed, checked on the host:**
- Your morning items: the Reload citation committed (a40eb55); C673 rechecked (RIPng and every
  switch's management port: s1's one line is still the whole change, noted in sitting 2
  step 3); `/devices/regions` removed (d13c0be).
- C706 Neighbours' columns line up; C707 a chart reads out on hover; C708 History's
  Authorisations tab removed (an old link opens the Timeline); C710 Settings' grids fill the
  width; C712 switches can be onboarded (stage D run on throwaway nodes on the lab host; the
  SSH key line last).
- **C709, DHCP pool descriptions** (8d69e1f): board C revised (canvas v117), a Pool description
  on Add and Edit…, kept in Kea's `user-context`, drawn under each range. On the host: ZTP's two
  discovery pools say what they are for, and the five other pools Mercury holds say
  "no description: Edit… adds one".
- **C711, IP SLA for s1, s4 and r6** (8d53810): a fourth policy, `upstream` (the static default
  gateway, else the routing peers, now RIP's too, else the widest static route's next hop).
  Walked read-only on the host over committed intent: under today's `gateway` all three name
  nothing, as you saw; under `upstream`, s1 from r1, s4 from r2, r6 to s3's loopback.
- **The topology service retired** (c638aad + 5cdd353): the renderer left the repository, and
  the host step ran: 7 of 7 checks PASS (unit stopped, disabled, removed; link removed; nothing
  on 8088). Mercury's `topology-renderer-gone` check reads done; `/v2/topology` answers 200.

**Later the same afternoon (19:30 to 20:05 UTC):** C714 (c961204: the retired topology
service's integration removed, so Needs attention no longer draws it down; your two CLAUDE.md
lines committed; `deploy/topology/` and its references gone) and **C713** (c907cc7: the IP SLA
flow writes a probe as the device prints it, no frequency at the default, and a deploy that
sends IP SLA lines now fails verify unless the device equals its rendered intent, both ways).
Both deployed; on the host the `upstream` suggestions for s1, s4 and r6 carry no frequency line.

**Your walk, the evening of 2026-10-12 (as you reported it):**
- **C711's proof:** the IP SLA batch on r1 and r2 (s1 measured from r1's `ip sla 3`, s4 from
  r2's `ip sla 2`) both verified. **IOS-XE does NOT print `frequency 60`** (measured: the new
  both-ways verify passed), so C713's rule holds on both platforms. r6 not probed: your choice
  (it would probe s3).
- **s2's intent fix** (` frequency 60` removed) committed.
- **Save All: baseline EARNED.**
- Found: Coverage did not credit s1 and s4 (C717, fixed), r6 needs a "Decline…" (C718, open),
  the s4 sentence read backwards (C717, fixed); asked why r6's suggestion was s3's loopback
  (C719: the static route's next hop belongs to s3; the hop itself would be the closer target).

**Waiting on you:**
1. **C718's board** (Decline… for IP SLA) once drawn, and **C719**: the next hop itself as the
   static-route step's target, and whether the gateway step follows.
2. **The AI agent's family:** the answer is in the session reply of 2026-10-12 ~20:05 UTC
   (one v2 gap: approving or rejecting approval-queue items). Held until the steppers are done,
   as you asked.
3. **Sitting 3 (fleet writes)** exercises the pages converted to the one stepper (in progress).
4. As before: C700's 24 h reading is due 2026-10-13 05:06 UTC (23:06 UTC−6 tonight); C695 and
   C673's confirms are in the walk.

**Decisions I made for you** (each in STANDING_APPROVAL_LOG.md): board C's revision for C709;
C711 as a new policy rather than changing what `gateway` or `peers` means, with no board (one
more option in an existing select). **174 open.**

## MORNING REPORT: the overnight run, 2026-10-12 (03:20 to about 08:10 UTC; 21:20 to 02:10 UTC−6)

**Every item on your list is done or waits only on you**, except the AI agent's 7.8 family,
moved last (logged). Every commit went through the gate, was pushed with CI green before the
next, and each green release was deployed with `nmas-deploy --wait` and checked on the host.
No network device's configuration was changed. Nothing ran on s3 or between 08:30 and 09:10 UTC.

**Per item: built, deployed, checked**

1. **Your last message's items:** C681, dhcpcd on every lab host pinned to its lease, proved
   on h1 first (renewed ::107 under the same IAID across a restart) and rolled out to h2 to h4;
   C700, the routing modules ask with a 2 s timeout and walk only state (10 to 12 requests a
   scrape, was 55 to 66; **its 24 h timeout reading is due 2026-10-13 05:06 UTC**); C695 (a)
   written into the walk; C703 registered; C696 checked (8.8.8.8 leaves toward r5, which
   advertises it; 192.0.2.1 drops: no route); `docs/PUBLIC_RELEASE.md` with the roadmap note.
2. **7.8 removals, one family per commit**, each proved unreached (grep and the app's url_map)
   before it went and 404 on the host after its deploy: list data, refresh hostnames, renames,
   the legacy store and migration, bulk reload with the break-glass preview route (**two
   families in one commit**, logged), inventory order with the vendored SortableJS, the
   monitoring stack panel with the integrations' `monitor()`, Configure (about 160 kB off
   today's index), the legacy collectors' routes with today's Monitoring tab, the topology
   service's routes and panel, today's Topology tab with vis-network, reachability. CUTOVER.md's
   "Removed at 7.8" names each. **Left:** the AI agent's family (largest; next), `/devices/regions`
   (goes with today's index), the topology service unit (a host step), and the families blocked
   on today's device page and template editor (Backups, device files, bulk file actions, TFTP,
   quick actions).
3. **C667: nothing left to build.** Boards A to C are built, deployed and compared (three
   fidelity records); a save, a pin and a removal by you close it (sitting 2 step 13).
4. **The Logs tail (C675): nothing left to build**; compared and walked earlier.
5. **C673: prepared, the commit yours.** The intent editor's own preview, run on the host,
   gives exactly `passive-interface GigabitEthernet0/0` under `router rip`, against intent and
   the device. **My commit of the intent was refused by the session's permission check; I did
   not retry it**, so sitting 2 step 3 is your Edit, Preview, Commit and Deploy, as written.
6. **C691, Snap to grid: board E drawn and signed off (canvas v115), built (08e5382), compared
   at 1440, 1280 and 390, deployed**, and the host draws it. Your drag closes it (sitting 2
   step 16).
7. **Findings closed without you:** C702 (a script's commit lost its s3-archive hook at exit:
   the hooks now join before shutdown; proved on the host's interpreter), C698 (a connect whose
   SSH transport never came up is tried once more, never for authentication), C672
   (SETTINGS.md's false reason corrected), C674 (the capture tool no longer calls a session
   lock or an unchanged key a write; e3269cc, deployed, and a capture of `show clock` on s1
   on the host exited 0; it also showed the slot's lock listed as changed by the app, fixed in
   the report's own commit).
8. **The host health check (07:18 UTC): healthy.** The only failed unit is `openipmi.service`,
   which failed before too. Every service, timer, container and endpoint is up. The records
   database listens on 127.0.0.1:5433 only. Prometheus has 39 targets, 0 down, and all nine
   devices sent syslog in the last 15 minutes. **Needs attention: empty**, all 24 sources read.

**Decisions I made for you** (each a line in STANDING_APPROVAL_LOG.md): board E's design (a
toolbar switch in the address, a 40-unit grid, only what is moved snaps, off by default);
keeping board A's toolbar order where board E drew another; two 7.8 families in one commit;
the AI agent's family after items 6 to 8. Smaller, in the commits: SortableJS and vis-network
removed with their last pages; tests that used removed routes as examples moved to
`POST /remote/auto-push` and `git_status`; C698's retry pause 2 s and its two error texts; C674
excluding `ssh_slots/` and judging an open by whether the file changed.

**Skipped, and why:** the C673 intent commit (refused by the permission check, yours in the
walk); the AI agent's family (largest, after the rest); the topology service unit (needs a host
step, with the service's Settings card, as one family); CLAUDE.md's citation below (yours).

**Findings:** opened C704 (v2 Devices has no sortable columns, which drag-reorder's removal
assumed), C705 (the Grafana card's `grafana_device_dashboard_url` has no reader), C703 (the
edges' "always" defaults, a design note); closed C672, C674, C698, C702 (and C699, C701 earlier
in the night). **174 open.**

**CLAUDE.md, yours to paste** (the rule "Any operation that restarts devices declares its
planned-restart window", whose cited tests for the Reload's window went with today's bulk
reload): replace

```
  [the late refusal, the correction and the Reload's window: tests/test_restarts.py,
  tests/test_acknowledge.py; that every restarting operation declares one: not mechanised]
```

with

```
  [the late refusal and the correction: tests/test_restarts.py, tests/test_acknowledge.py;
  the Reload's window: tests/test_reload_v2.py; that every restarting operation declares one:
  not mechanised]
```

**The walk: one list, in ordered sittings, below ("THE WALK, IN ORDERED SITTINGS").**

- **Sitting 1** is read only, steps 1 to 14. Tonight adds today's thinner pages (13) and Snap
  to grid's switch (14).
- **Sitting 2** is single-device and single-record writes:
  - C673's confirm is step 3, s1's RIP passive on Gi0/0.
  - C695's confirms are step 15, the r3 and r4 peering /31s into OSPF, passive; the proof I
    run after is written there.
  - The C691 drag is step 16.
- **Sitting 3** is fleet-wide writes.
- **Sitting 4** is the Reload, on r6 only.
- **Sitting 5** is a first boot through Discovered.

Each step names its expected result and its undo.

**The rest of Phase 7, estimated** (from tonight's rate: thirteen 7.8 families and four findings in
about five hours):

- **The AI agent's family:** one long session. It covers the 26 routes, the chat panel on every
  page, three tabs, the collectors and `modules/topology.py`.
- **The topology service unit:** under an hour, with your host step.
- **The template-editor-blocked families:** they need today's template editor retired first.
- **Your walk:** about three hours across the five sittings. Sittings 2 and 4 must avoid
  08:30 to 09:10 UTC.

So: about two more agent sessions, plus your walk, before 7.8 closes and cutover's last
condition (no PLANNED row) holds.

## OVERNIGHT RUN 2026-10-12 (from 05:25 UTC; 23:25 UTC−6): status, kept current per item

Rules as given: no network-device config changes (intent changes prepared with their previews,
the confirm in the walk); read-only device commands through Mercury; lab-host changes allowed;
never s3; nothing on devices 08:30 to 09:10 UTC; CI green before each commit; each green
release deployed and checked on the host.

1. **Last message's items: DONE** (the status block below): C681 dhcpcd on every lab host (h1
   proved first), C700 installed (its 24 h reading due 2026-10-13 05:06 UTC), C695 (a) in the
   walk (sitting 2 step 15) and C703 registered, C696 checked (8.8.8.8 leaves toward r5 because
   r5 advertises it; 192.0.2.1 drops: no route), PUBLIC_RELEASE.md with the roadmap note.
2. **7.8 removals, in progress:** list data (e7f82f9), refresh hostnames (4daf00d), renames
   (5c49896), the legacy store and migration (94797a3, deployed 05:41 UTC), bulk reload with
   the break-glass preview route (3c3b1c7: two families in one commit, since the second was
   edited while the first's gate ran; deployed 05:57), inventory order (249f0e6, deployed
   06:06; C704 found: v2 Devices has no column sort), the monitoring stack panel with the
   integrations' `monitor()` (c6fba50, deployed 06:15; C705 found: the Grafana URL setting
   has no reader), Configure (eb64d5e, deployed 06:28), the legacy collectors' routes with
   today's Monitoring tab (76e5b83, deployed 06:41; the receivers go with the AI agent), the
   topology service's routes and panel (9cddf61, deployed 06:51), today's Topology tab with
   vis-network (54138a4, deployed 07:03), reachability (963eb8e). **Left:** the AI agent's
   family (the largest; taken after items 6 to 8, logged), `/devices/regions` (goes with
   today's index), the topology service unit (a host step), and the families blocked on
   today's device page and template editor (Backups, device files, bulk file actions, TFTP,
   quick actions).
3. **C667: checked 06:15 UTC, nothing left to build.** Every part the message names is built,
   deployed and walked read-only on the host (7f56d12, 2e45ab9, 482ad26), and each is in a
   fidelity record against its board: board A in `docs/fidelity/history-query.md` (Saved by
   your team, Ask your own), board B in `history-metric.md` (the editable query; routing
   neighbour changes, restarts and telemetry rates; Ask your own in B's layout, a logged
   deviation), board C in `logs.md` (Save this view…, compared again). What closes it is yours:
   a save, a pin and a removal (walk sitting 2 step 13).
4. **The Logs tail: checked, nothing left to build** (C675: built, compared in
   `docs/fidelity/logs-tail.md`, walked, db2e5f0).
5. **C673 intent preview: DONE 06:08 UTC** (the walk's sitting 2 step 3): the editor's own
   preview on the host gives the one line against intent and device. The agent's intent commit
   was refused by the session's permission check (not retried): the commit is the operator's
   in the walk, as the step already said.
6. **C691 snap to grid: board E drawn and signed off (canvas v115), built, compared** (next
   commit); the walk: a drag with the switch on.
7. **Findings closable without the operator: C702 (9307392, proved on the host), C698
   (95825e0), C672 (f721864, docs), C674 (e3269cc) closed.**
8. **The host health check: DONE 07:18 UTC, read only, on 963eb8e.** Failed units: only
   `openipmi.service` (failed before, 2026-10-09's check too). Active: flask-app, Prometheus,
   Grafana, the three Kea services, Docker, nmas-topology, Alloy; the ZTP responder socket
   listening; the five nmas timers armed (next runs 08:01 to 08:04, the NetBox restore test
   2026-10-13 04:35). Containers: mercury-postgres healthy, NetBox's five healthy, Loki and the
   SNMP exporter up; the two Oxidized containers stopped, as decided. Endpoints: Mercury,
   Prometheus, Grafana, Loki, the SNMP exporter and NetBox all 200. The records database on
   127.0.0.1:5433 only. Prometheus: 39 targets, 0 down (every device's jobs). Every managed
   device heartbeating: syslog from all nine (r1 to r4, r6, s1 to s4) in the last 15 minutes.
   **Needs attention: empty**, all 24 sources read, none unreadable. Disk 14% of 291G.

## STATUS: 2026-10-12, your picks (from 04:35 UTC; 22:35 UTC−6)

- **C681 (a), dhcpcd: DONE and proved.** On h1: the first start renewed ::107 under IAID
  657211943 with real lifetimes; a stop and start confirmed the same lease under the same IAID,
  no new lease; a forced renew moved Kea's record to 05:00:44 under the same IAID; the
  reservation matches. Then h2, h3, h4, each renewing its own address under its pinned IAID,
  and the lab's start-up (`host-net.sh`, the package bound into each host) carries it across a
  redeploy. Needed beyond the plan: an exit hook putting the /64 on-link (DHCPv6 has no prefix
  length). **My slip:** on h2 I started dhcpcd by hand before its pinned files were in place;
  it took ::100 with a generated DUID and turned h2's RA handling off: undone, the lease ::100
  is one more orphan. **Sitting 2 step 14 can proceed.**
- **C700 (a) and (b): installed 05:05 UTC.** 2 s per request and 3 retries (8 s worst, inside
  the 20 s scrape); the OSPF walks only the state column, since nothing reads another (the live
  dashboards and Mercury checked). Every OSPF target up, 10 to 12 requests a scrape (was 55 to
  66), 0.1 to 0.7 s. **The 24 h timeout rate is due 2026-10-13 05:06 UTC.**
- **C695 (a): sitting 2 step 15, for your confirm** (the intent lines, the expected program,
  and the proof the agent runs after). **C703** registered (the "always" defaults, a note).
- **C696 checked: the code already follows your rule.** 8.8.8.8 is not dropped at the edge:
  r5 advertises 8.8.8.8/32 over BGP and each edge's CEF forwards it out Gi2 toward r5 (raw
  answers in C696's row); 192.0.2.1, which r5 does not advertise, is "no route" and dropped. A
  test pins both.
- **Public release readiness:** `docs/PUBLIC_RELEASE.md` (items a to e), noted in NSOT_PLAN and
  beside Stage 10. C13 and C336 moved there; C663, C329, C396 and C333 listed and kept in their
  phases (each a defect here too).
- **Next:** the 7.8 removals (renames and the legacy store next), then C667.

## STATUS: 2026-10-12, your seven decisions (from 03:20 UTC; 21:20 UTC−6)

- **(1), (5) accepted, noted.** Snap to grid (C691) after the 7.8 removals.
- **(2) C690's caveat: done (C699, 14689b4, deployed 03:59 UTC).** The neighbours read takes
  the window's raw samples, so each value keeps its own scrape time; one older than 90 s is the
  last good report: Neighbours says "As of HH:MM UTC" above the protocol and on each row, and a
  Needs attention link says "(as of HH:MM UTC, its last good scrape)". **r1's OSPF scrape
  measured (C700):** 55 SNMP requests a walk, 0.5 s typical, 15 s at p99, 9 timeouts in 24 h;
  the exporter retries 0.94% of packets after its 5 s default per request. Proposed, yours to
  pick: (a) a 2 s per-request timeout on the routing modules; (b) the walk narrowed to
  ospfNbrState (about a tenth of the requests); (c) the job's timeout 20 s to 40 s. (a) and (b)
  remove the cause; (c) hides it.
- **(4) and (7) h1's reservation first, then the other six: DONE 04:00 UTC** through Mercury's
  write path, each read back from Kea and committed (22f233a to 548e2db, pushed). Found on the
  way and fixed first (C701, 14689b4): since the subnet move NO reservation could be written
  through Mercury, onboarding's ZTP reservation would have refused too, and the Kea check
  before both tested the live files instead of the candidate. Nothing was written unchecked
  in between (both refused before writing). Sitting 2 step 1 is done.
- **(3) the lab change: HELD, measured, your decision needed.** h1's busybox (1.31.1) gives
  its script no lifetime for the address, so "installed with the lease's real lifetimes"
  cannot be done with it. And the proof you asked for fails, measured on h1 with the
  reservation in place: a client restart draws a new IAID and Kea gave it ::104 from the pool,
  because ::107 stays leased to h1's old IAID. That test left one more orphan, ::104 (ends
  2027-10-12); h1 itself is unchanged and still uses ::107. Options (C681's row): (a) a client
  with a stable IAID that passes lifetimes (dhcpcd or odhcp6c): a new package, one of your
  four stops; (b) static IPv6 addresses on the lab hosts from the addressing plan, Kea's
  reservations recording them; (c) keep busybox and release the previous lease at each host
  start (C697 first). (b) is the smallest. Sitting 2 step 14 waits on this.
- **(6) C695 measured** (its row has every answer): neither edge holds a real default (both
  originate one "always"); r5 advertises 8.8.8.8/32, 10.255.1.15/32 and 203.0.113.0/31 to both
  and each holds all three; nothing r5 advertises is blackholed (traces and 5/5 pings); only
  the two peering /31s are (r1 to .1 0/5, to .3 5/5). Fixes, yours to pick: (a) the /31s into
  OSPF, passive: the smallest, fixes exactly this; (b) a conditional default: failover; (c)
  iBGP r3–r4 with next-hop-self: failover, and the /31s only with a `network` for each.
- **Found and fixed on the way:** C696 (bb57da7, deployed 03:43): Path… drew a hand-off to
  the ISP as "not delivered" in red; "leaves the network" is now its own grey outcome.
  **Registered:** C697 (release a lease, FUTURE), C698 (one SSH connect to r3 failed, UNKNOWN),
  C702 (a script's commit loses its s3-archive hook at exit; these held no golden, nothing lost).
- **Next:** the 7.8 removals, one commit each; then C667's remaining questions.

## STATUS: 2026-10-12 (from about 01:00 UTC; 19:00 UTC−6 the evening before)

- **Your reports, fixed, deployed and seen on the host:** Topology's double tooltip (C687) and
  the held note breaking the layout (C688); "Couldn't load this view" in the sidebar (C692,
  bf418d0, deployed 01:36 UTC); D4 now reads ok (C689: no option reaches subnet 255 through a
  class or the subnet; a planted routers option fails the check); r1's OSPF row (C690: about
  1.4% of r1's OSPF scrapes time out, unrelated to the evening's work; one lone failure no
  longer blanks the read). Read on the host 02:23 UTC: Needs attention holds 0 rows, every one
  of its 24 sources read.
- **Path… (C693, C694), 642f2a5, deployed 02:15 UTC, walked on the host.** Board D (canvas
  v114) drawn and signed off under the Phase 7 mode. Each hop's own `show ip cef` decides the
  next hop, read through the reads engine as a job; r5 is a destination by each peering
  address. Walked: r1 to r5's r3 peering splits over r3 (delivered) and r4 (dropped, no
  route), 7.2 s, 3 devices read; r2 to r4's peering the mirror; s1 to r4's loopback one path
  through r1, delivered. Each drew its card and lit the map.
- **Found by that trace: C695 (LAB, UNKNOWN).** r4 drops traffic for r3's ISP peering address
  (and r3 for r4's) while each advertises a default into OSPF, so the flows hashed to the
  other edge router are lost. The one measurement: r3's and r4's BGP tables, for what r5
  advertises beyond the peering addresses.
- **C681's page asks (8dfee66):** DHCP's Identity column shows each IPv6 lease's IAID; the
  page and the manual say a client installing "forever" keeps its address whatever Kea says,
  so a reservation is the fix. Sitting 2 step 1 is now the reservations for every lab host
  (h1's ::107 first, the table read from Kea at 02:20 UTC); step 14 is the lease-time change,
  after the lab change.
- **A correction to the plan you set, C681:** shortening the lease time will not clear h1's
  three orphans. Kea keeps each lease's own end (2027-10), and no client renews under those
  IAIDs. Your choice: a previewed release of the three through Mercury (a board first), or
  leave them to 2027. The pool has room either way (257 addresses per subnet).
- **Waiting on you:** the lab change in C681's row (udhcpc6 kept running), before step 14;
  the orphans' release, above; C691's snap to grid needs a board (next after the 7.8
  families, or before them if you say).

## STATUS: the continued run, 2026-10-11 (from 17:53 UTC; 11:53 UTC−6)

Your answers committed in 8224518 (deployed). Then, in your order:

- **C675, the Logs tail:** built, deployed (db2e5f0), walked on the host; closed.
- **C676, onboarding from a Planned NetBox record:** built, deployed (9631711), walked
  read-only; closed. Your "Mercury creates it as Planned" entry point is not what runs today
  (Verify creates the record Active): it is C556's unbuilt Planned → Active contract.
- **C667:** the last three questions (7f56d12), the editable PromQL and Ask your own
  (2e45ab9), saved views with pinning (482ad26): each deployed and walked on the host
  (saved views read-only; a person's save, pin and removal are in the walk).
- **Found and registered:** C677 (r6's restart on 10-09 missing from Mercury's restart record,
  UNKNOWN); C678 (the deploy's CI wait spent GitHub's 60-an-hour allowance: fixed, seen on the
  host, closed); C679 (the wait's bound 1.3x today's CI run: fixed, seen on the host, closed).
- **C529, DHCP:** measured first (a stranded address keeps its holder until the lease EXPIRES:
  Kea 2.4.1 answers its renewals with silence, on a throwaway Kea in its own namespace; Kea
  resolves a nested include). **The subnet move RAN on the host, 19:49 UTC, 9 of 9 PASS**: the
  fresh dated copy is **`/var/backups/kea/c529-step5-20261011T194937Z`**; every subnet now comes
  from Mercury's files; Kea's hash, configuration, reservations and every lease equal before
  and after. Then board C (the table against intent; edit, add and remove a subnet) and board
  D (exclusions and conflicts), each deployed and walked read-only on the host (89e5e4f last).
  Every confirm is yours: sitting 2 step 12.
- **C529 step 5, the report you asked for** (in full in C529's row):
  (1) the subnets live in `/etc/kea/nmas/subnets4.json` and `/etc/kea/nmas/subnets6.json`,
  included by `/etc/kea/kea-dhcp4.conf` and `/etc/kea/kea-dhcp6.conf`; each subnet still
  includes its step-2 reservations file (`/etc/kea/nmas/reservations-<id>.json`,
  `reservations6-<id>.json`). (2) Before and after, the step's own snapshots: IPv4 3 subnets
  (10, 20, 255), 2 pools, 6 options, 0 reservations, 3 leases; IPv6 3 subnets (10, 20, 30), 3
  pools, 4 options, 0 reservations, 6 leases; configuration, reservations and leases equal in
  both families, Kea's hash unchanged. (3) `kea-dhcp4 -t` and `kea-dhcp6 -t` pass on the live
  files; both reloaded at 19:49:39 UTC, Kea logging 3 subnets added each and no error; neither
  restarted. (4) No client had asked since the move (Kea's counters: 0 packets since its start
  on 10-09 03:20 UTC; 365-day leases), so h1 was made to ask at 20:39 UTC, its interfaces left
  as they were: IPv4, Kea renewed h1's own 10.10.10.100 (ACK, no NAK); IPv6, Kea answered
  with a NEW lease (::102) because busybox `udhcpc6` uses a new IA each run (C681, LAB): one
  unused lease left by the probe. (5) Restore: `sudo install -m 644 -o root -g root
  /var/backups/kea/c529-step5-20261011T194937Z/etc-kea/kea-dhcp4.conf /etc/kea/kea-dhcp4.conf`,
  the same for `kea-dhcp6.conf`, then `cd ~/python/Agentic_NMAS &&
  /opt/mercury-venv/bin/python scripts/nmas-kea-subnet-files reload` (undoes any board C or D
  change made since).
- **Board L, the discovery range: RUN on the host 2026-10-11 21:16 UTC (5cbb226), 10 of 10
  PASS.** Found first (C682): the classes as recorded would have cut every unreserved client's
  lease in every subnet to five minutes (Kea's classes are global; a class's lease time beats
  a subnet's, measured). They are confined to the ZTP subnet's own clients, measured safe on a
  throwaway Kea and then live: after the step, h1 and h2 renewed through their relays and
  still got 365 days. The range is 10.255.0.192/27 (two pools, ciscopnp's first), recorded
  through board C's write path. Dated copy: `/var/backups/kea/ztp-discovery-20261011T211641Z`
  (with before.json and after.json). Then the discovery reader and Devices › Onboard devices ›
  Discovered, with Pick… opening Add device with the MAC and the ZTP way.
- **C680, step 2's stale check:** fixed (it read the pre-move file); it now reads the shape the
  files have, so it stays true after later steps. Once deployed, the Update row reads done
  with no re-run.
- **Boards L and M:** redrawn from the measurements (canvas version 111, logged as signed
  off); the discovery range measured on a throwaway Kea (the two classes and pools work as
  drawn); the lab's ZTP subnet's .192 to .223 are free. Building L next.
- **Board L's page (8470511), walked on the host:** the discovery reader reads every 30 s, Kea
  runs the range, Devices › Onboard devices › Discovered draws it; no unknown device is asking
  (none is booting). Pick… opens Add device with the MAC and the ZTP way.
- **Board M: not built, a question for you.** Its "full config at first boot" needs a new
  device's whole intent committed before it boots, and serves secrets beyond the one-time
  credential over TFTP (section 16 says the first-boot file carries a one-time credential only).
  The bare-management way it also draws is what Add device does today.
- **7.5's identity line (dbc423c), walked on the host:** the region drawn first (canvas v112);
  the walk found a Save All's commit counted twice (C685, fixed and seen on the host: the last
  7 days hold 42 commits, 38 verified, 1 host login, 3 not verified); C686 (UNKNOWN) is those
  three, Save All commits of 10-09 that name a person and carry Actor-Verified none.
- **7.8:** template coverage's JSON route removed too (aee9a81).
- **7.8 started (37623c4):** the survey ranked every REMOVE family; the six /netbox/query routes
  are gone. Registered from the survey: C683 (the backup store is still read by v2's intent
  editor and bulk intent, so Backups is blocked), C684, C616's other readers.
- **Next:** the 7.8 families in the survey's order, one commit each.
- **Done by you (2026-10-11):** sitting 2 steps 1 and 2, the C663 host step and
  `netbox-role-kinds.sh` (router and switch set). NetBox also holds a `network-device` role
  with no kind: Mercury calls any device holding it "not classified" until it has one.
- **Waiting on you:** the CLAUDE.md script (then `scripts/nmas-host` moves to `lab/`); the
  walk's sittings (below); deleting NetBox's `network-device` role (no device holds it, read
  2026-10-12).
- **Answered (the operator, 2026-10-11 night) and done:** board M kept first boot bare and its
  intent as an ordinary deploy (redrawn, canvas v113, built 8ac3a6a); C686's cause found and
  fixed (every job carries its confirming person, a776224); C683 done (the intent editor and
  bulk intent off the backup store). C681: the DUID is already MAC-derived; the varying part is
  busybox's random IAID; the lab fix is a host image with ISC dhclient (its row). **Yours to
  decide first:** ISC dhclient is a new third-party package (MPL-2.0) in the lab hosts' image,
  one of the four stops. The alternative needs no new package: shorter IPv6 lease times on
  subnets 10, 20 and 30 (board C, your confirm) with the hosts' udhcpc6 kept running to renew.

## MORNING REPORT: the overnight run, 2026-10-11 (06:34 to about 11:00 UTC; 00:34 to 05:00 UTC−6)

**Built, deployed and checked, per item** (each commit gated in CI's interpreter, pushed, CI
green, deployed with `nmas-deploy --wait` and checked on the host before the next):

1. **C671 measured as a possible real fault:** none. Routing and traffic cross r1–s1 and r2–s2
   both ways; only LLDP fails, s1's and s2's Gi0/2 receiving no LLDP frame (details below).
2. **C670:** the spring layout in its grid variant, 2.47 s at 900 devices (was 32.8 s).
3. **C663 steps 2, 3a, 3b:** Mercury's side of the lab removed (its settings, routes, checks,
   rows, the rotation's boot-file stages), vrnetlab's boot rules out of the code (the device's
   environment from NetBox), the topology renderer renamed with its host step run (8 of 8
   PASS); the lab sync proved unchanged. **One entry left:** `scripts/nmas-host`, waiting on
   your CLAUDE.md paste (below).
4. **C665:** a role's kind read from NetBox (`mercury_kind`), the role map and hostname guess
   gone. NetBox refused setting the two roles' kinds (403: the token may not edit roles): walk.
5. **C667 steps 5a, 5b, 5c:** History › Query (board A), Syslog by device at its home (board C),
   the first metrics question (board B; on the host the data route answers 9 of 9 series), and
   "CPU and memory trend" in board B's layout (per device; memory only where a device's scrape
   carries a memory pool, which on the host is the routers).
6. **C662 (and C671):** RIP and RIPng read from the devices into Topology as layers and as the
   second witness. Walked: RIP and RIPng up both ways on r1–s1, r2–s2, s1–s2; r1–s1 and r2–s2
   drawn as intended with their LLDP row; "not as intended" empty (was 2). Both closed.
7. **C529 step 2:** DHCP reservations added, changed and removed (board B), through Mercury's
   file per subnet (ae306de, c672580). The one-time host step run at 10:58 UTC, 7 of 7 PASS:
   **the dated copy is `/var/backups/kea/c529-step2-20261011T105829Z`**, read back identical
   first; every subnet but ZTP's now takes its reservations from Mercury's file, and Kea's
   configuration hash is unchanged. Measuring first caught a bug that would have stopped it
   (Kea prints its hash upper-case), fixed in c672580. The first real reservation is yours.
8. **Cutover blockers:** none left to build; CUTOVER.md has no PLANNED row. Their walks are below.
9. **Nice-to-haves, 7.5 to 7.7:** C641 measured (the host's record holds no entry that crashes
   the census: re-bucketed C). The rest not started (below).

**C671's measurements** (06:34 to 06:45 UTC, read-only through Mercury, never s3): RIP's sources
and RIPng's next hops fresh both ways across each link; pings both ways 5 of 5, IPv4 and the
link's global IPv6; packets in on both ends between two reads, no input errors; no `lldp` or
`cdp` line disables anything; s1's and s2's Gi0/2 report LLDP Tx and Rx enabled, "WAIT FOR
FRAME", no neighbour; r1 and r2 run CDP on no interface. Not explained by platform; not fixed.

**Every decision** is one line in docs/STANDING_APPROVAL_LOG.md dated 2026-10-11, counted from
the log: C663 9 (one of them recording your own decisions), C665 3, C667 3, C662 and C671 5,
C529 step 2 7; the other six lines dated today were made before the run. The ones you may want to look at first:
the second witness is a routing adjacency both ends report on the link's own ports (CDP waits
on CDP running); a link whose far end is unpolled keeps its old drawing; DHCP reservations go
to a file of Mercury's per subnet BEFORE the subnet move (a one-time host step, the dated copy
first), and Kea's own check runs at confirm, not at preview.

**Skipped, and why:** C667's remainder (saved views, editing the PromQL, Ask your own, three
questions) and C529 steps 3 to 5 (boards C and D, the subnet move): not reached. Boards L and M,
7.5's "N of M commits carry a verified identity" claim on History (its board region is not one
I hold; it needs drawing first), the 7.8 removals: not reached. CDP as a witness: turning CDP on
is a configuration change, yours. Nothing ran on s3 or in 08:30 to 09:10 UTC.

**Slips, owned:** two prose edits made with `sed` (docs/CONSOLE_DRILL.md, docs/TESTING.md),
against "prose edits with the Edit tool"; two pointless heredoc calls, both refused by the hook.
Nothing was lost; the edits were the intended text.

**THE WALK LIST** (updated 2026-10-11 evening after your answers):
1. **CLAUDE.md:** run `python3 lab/claude-md-c663-nmas-host.py` on the laptop. It changes five
   lines: the three naming `lab/nmas-host`, and the prose rule's two lines, which now name the
   new hook (`claude-no-shell-prose-edits`) beside the heredoc one. It shows the diff, and
   refuses a duplicate or a moved anchor. Tell the agent to commit: `scripts/nmas-host` moves to
   `lab/` in that commit (until it does, the suite's CLAUDE.md citation check fails, by design).
2. **`l3-switch`:** Mercury has no such kind (router, switch, firewall; NetBox's field refuses
   anything else). Proposed: core-switch and distribution-switch → `switch`; Topology already
   badges a switch L3 when it routes. Say yes, or name another mapping, before sitting 2 step 2.
3. **Everything else, in the ordered sittings below:** the Update page's host step, the NetBox
   role kinds, C673's deploy, the C525 reservation, Save All, and every screen built
   2026-10-10 and never run on the host.

## THE WALK, IN ORDERED SITTINGS (the operator's, 2026-10-11)

Each step: what to click, what you should see, and how to undo it. Stop a sitting at the first
step that does not show what it says, and tell the agent the step's number. Times are UTC
(UTC−6 beside). Never inside 08:30 to 09:10 UTC (02:30 to 03:10).

### Sitting 1: read-only screens (nothing is written; nothing to undo)

1. **Needs attention** (`/v2/`): rows each name something wrong and an action. Expect no host
   step owed (C663's and the discovery range's are done), and no Topology row.
2. **Devices**: nine devices with counts by state at the top; search narrows; a device opens.
3. **A device, r1**: every tab opens; Neighbours shows OSPF and BGP; Monitoring draws the
   device dashboard; Intent shows the committed document; History lists its commits.
4. **Topology** (`/v2/topology`): chips `RIP up` and `RIPng up` on r1–s1 and r2–s2 (and RIPng
   on s1–s2); both links drawn solid. Hover r1–s1: an **LLDP** row "one end", "s1 Gi0/2 reports
   no neighbour, polled", "confirmed by RIP, RIPng heard both ways". Needs attention on the map
   lists nothing "not as intended".
5. **History › Query**: Syslog by device draws lines by severity; "Interface errors and
   discards over time" draws a chart and its query; "CPU and memory trend" for r1 draws two
   lines (CPU, memory), for s1 one (CPU), with the Covers line under it.
6. **History › Timeline and Baselines**: commits with who and how verified; under the filters,
   "N of M commits in this window carry a verified identity" (on 10-11: 38 of 42, 1 host
   login, 3 not verified); **Show only these** lists the 4 (the 3 are C686's Save All of 10-09),
   **Show every identity** undoes it. Baselines listed with whether each can be re-applied.
7. **DHCP** (SOURCE OF TRUTH › DHCP): Subnets 6 (3 IPv4 with ZTP's, 3 IPv6); Leases grouped;
   Reservations empty but for what onboarding wrote. Press **Add a reservation…**, fill any
   free address, **Preview**: the change, the checks (each "pass" or "at confirm") and the
   confirm button appear. Press **Cancel**: nothing is written.
8. **Show commands**: run `show version` on s1 and s2 (never s3): each answers; the run is
   recorded. **Ask the device** on r1's page: `show ip route summary` answers.
9. **Templates, Coverage, NetBox, Credentials › Profiles, Settings (Installation and Default)**:
   each opens and reads; nothing pressed.
10. **Devices › Discovered** (board L): the range 10.255.0.192/28 and .208/28 named, read every
    30 s; three groups, Asking now open and empty ("No device the tool doesn't know is asking
    now"), until a device boots on the ZTP segment (sitting 5).
11. **DHCP › Subnets and Exclusions**: board C's columns (gateway against intent, DNS, lease
    times, held by Mercury); ZTP's subnet shows the discovery pools; Exclusions empty.
12. **History › Query › saved views**: board A's list (empty until sitting 2 step 13).
13. **Today's pages after tonight's 7.8 removals (2026-10-12)**: today's index (`/`) shows seven
    tabs, Devices, Ansible, NetBox, Agent, Approvals, Git and Logs (Topology, Configure and
    Monitoring are gone, and the device list has no drag-reorder or Reload Devices button);
    today's device page has no "SSH Connected" badge. Every v2 page is unchanged. Expect no
    console error and no broken control on what is left. Nothing to undo.
14. **Topology with Snap to grid on** (`/v2/topology`, press **Snap to grid** beside Reset
    layout): a faint dot every 40 units appears and the button shows pressed; press it again and
    the dots go. Nothing is saved by the switch. Nothing to undo.

### Sitting 2: single-device and single-record writes (each previewed; you confirm)

The first list's steps 1 and 2 (the Update page's C663 host step; the NetBox role kinds) were
DONE by the operator, 2026-10-11. Step 1 is now C681's reservations (the operator, 2026-10-12:
first in sitting 2).

1. **DONE by the agent 2026-10-12 04:00 UTC (your decision (7)); to see:** DHCP ›
   Reservations lists the seven below, each expected to read "in use by it" (a client with its
   identity holds the address) once the DHCP reader has read again; Leases badges each held
   address "reserved". What was done:
   **Reservations for every lab host (C525's design, C681), h1's IPv6 first.** DHCP ›
   Reservations › **Add a reservation…** for each row below, in order. Each: **Preview** shows
   the subnet, the identity, the address and the checks, each "pass"; for h1's IPv6 the
   address is leased to the same DUID (under the IAID h1 uses), so the preview says it is
   leased to this client. Reason "C681: pin the lab hosts"; confirm. Expect each result card
   "added", read back from Kea, one commit of `dhcp/reservations.yml`, and at the next read (5
   min) the lease row badged "reserved" (the Reservations tab: "in use by it"). The leases
   below are as Kea held them, read 2026-10-12 02:20 UTC; each is the address the host holds
   now, so nothing moves.

   | Host | Family | Subnet | Identity | Address |
   |---|---|---|---|---|
   | h1 | IPv6 | 2001:db8:10::/64 | DUID `00:03:00:01:aa:c1:ab:99:f6:e2` | 2001:db8:10::107 |
   | h1 | IPv4 | 10.10.10.0/24 | MAC `aa:c1:ab:99:f6:e2` | 10.10.10.100 |
   | h2 | IPv6 | 2001:db8:20::/64 | DUID `00:03:00:01:aa:c1:ab:3e:11:70` | 2001:db8:20::101 |
   | h2 | IPv4 | 10.10.20.0/24 | MAC `aa:c1:ab:3e:11:70` | 10.10.20.101 |
   | h3 | IPv6 | 2001:db8:10::/64 | DUID `00:03:00:01:aa:c1:ab:b0:85:65` | 2001:db8:10::103 |
   | h3 | IPv4 | 10.10.10.0/24 | MAC `aa:c1:ab:b0:85:65` | 10.10.10.102 |
   | h4 | IPv6 | 2001:db8:30::/64 | DUID `00:03:00:01:aa:c1:ab:12:c6:03` | 2001:db8:30::103 |

   h4 has no IPv4 lease (VLAN 30 is IPv6-only). The Leases tab now shows each IPv6 lease's
   IAID: h1's four share one DUID under four IAIDs. Known limit (C525): the lab's hosts' MACs
   are not pinned in the topology, so a redeploy that gives a host a new MAC (and so a new
   DUID) leaves its reservation "unmatched", said on the page. Undo: **Remove…** on a row (the
   host keeps its address; what survives is said).
2. **DONE 2026-10-11** (the first list's steps 1 and 2): the Update page's C663 host step, and
   the NetBox role kinds (router and switch set).
3. **C673, s1's RIP passive on Gi0/0**: s1 › Intent › **Edit**; under `routing.rip.settings`, after
   `- passive-interface Vlan20`, add `- passive-interface GigabitEthernet0/0`; **Preview**: one
   line added against intent and against the device (**prepared 2026-10-12 06:08 UTC**: the same
   edit run through the editor's own preview on the host, against base `eb8c0e39de09`, gave
   exactly `+    passive-interface GigabitEthernet0/0` under `router rip` in both diffs, nothing
   unmodelled; the agent's commit of it was refused by the session's permission check, so the
   commit is yours here). **Checked again 2026-10-12 08:20 UTC on your question (RIPng, and
   every switch), from each switch's committed golden read masked:** every switch's Gi0/0 is
   `ip address dhcp` with no IPv6 address and no interface-level routing, so RIPng
   (`ipv6 rip RCN enable`, on s1's and s2's other interfaces only) cannot speak there and
   `passive-interface` under `router rip` needs no RIPng partner; s2's `router rip` already has
   `passive-interface GigabitEthernet0/0`; s3's and s4's only process is OSPF on
   10.255.0.0/16, which does not cover the address vrnetlab hands Gi0/0 (inside 10/8, outside
   that /16, as s4's live read showed on 2026-10-11). So s1's one line is the whole change. **Commit** with a reason ("C673"). Then
   s1 › Actions › **Deploy…**: the program is one line under `router rip`; confirm. Expect
   verify passed, a receipt, and on s1 `show ip protocols` (Show commands) listing Gi0/0 under
   Passive Interface(s). Undo: Intent › Edit to remove the line, commit, Deploy (merge-only
   cannot remove it: the deploy preview offers it as a Mode B removal with your reason).
4. **Folded into step 1:** C525's h1 IPv4 reservation is step 1's second row.
5. **Capture with a reason** (s2 › Capture…): if it shows a shrink, give the reason; expect a
   golden commit with the reason. Undo: none needed (a new golden; the previous stays in
   History).
6. **The golden reveal** (s2 › History › a golden › Reveal): you, verified; the masked lines
   unmask in place; the reveal is recorded. Undo: none (a read, recorded).
7. **Templates**: open one template, **Edit…** a comment line, commit; **Approve…** it (it
   checks each bound device). Undo: Edit… back, commit, Approve… again.
8. **Credentials › Profiles**: **Add a profile…** for a role nothing uses (e.g. firewall), save;
   **Delete…** it. Expect each recorded; nothing else changes.
9. **Networks** (top bar): **Create** a network `Walk`; switch to it (empty); switch back;
   **Delete** `Walk`. Expect each recorded and Default untouched.
10. **NetBox import and remove**: import one device (r6) and remove it again, each previewed.
    Expect NetBox to show r6's record created, then gone (only what Mercury created is deleted).
11. **The remote** (History's remote line): **Set up the remote…** with the existing private config
    repository; then a commit pushes on its own (auto-push). Undo: disconnect from the same card.
12. **DHCP subnets and exclusions (C529 step 3), on a subnet no client uses.** The subnet move
    ran (19:49 UTC, 9 of 9 PASS); every subnet but ZTP's now has Edit… and Remove….
    a. DHCP › Subnets › **Add a subnet…**: IPv4, prefix `10.10.99.0/24`, pool
       `10.10.99.100 - 10.10.99.199`; **Preview**: Kea id the next free, a "differs" check saying
       no interface in intent is on it (so Kea would answer nobody there: expected); reason "C529
       walk"; confirm. Expect "10.10.99.0/24 added", read back, a commit of `dhcp/subnets.yml`.
    b. Its **Edit…**: DNS `10.255.0.10`, valid lifetime `1 d`; Preview (renew and rebind set to
       half and 7/8), confirm. Expect "changed".
    c. DHCP › Exclusions › **Add an exclusion…**: subnet 10.10.99.0/24, range
       `10.10.99.150 - 10.10.99.159`, reason "C529 walk: keep a range out"; Preview: the pool split
       into two pieces; confirm. Expect it listed, "the pool is split around it", a commit of
       `dhcp/exclusions.yml`. Then its **Remove…**; confirm. Expect the pool one piece again.
    d. Back on Subnets, 10.10.99.0/24's **Remove…**: no lease, so no acknowledgement asked;
       confirm. Expect "removed", Kea's subnets as before the walk.
    Undo: each step's own Remove…; the history of every step stays in the repository (`dhcp/`).
    Not walked by the agent: every confirm needs your verified identity.
13. **History › Query, a saved view (C667)**: open "Interface errors and discards over time",
    **Save this view…** with a title; pin it; open it from board A's list; remove it. Expect each
    act recorded on History as you, and the list redrawn in other tabs. Undo: the remove.
14. **CAN PROCEED (2026-10-12 05:05 UTC): every lab host now runs dhcpcd pinned to its lease,
    renewing as a daemon with the lease's real lifetimes (C681's row; h1 proved first).** The
    "first approve the lab change" sentence below is done. As drawn:
    **IPv6 lease times on subnets 10, 20 and 30 (C681), ONLY after the lab change.** Measured
    2026-10-12: no lab host runs a DHCP client after its first lease, so a shorter lease would
    let Kea hand a host's address to another client while the host still uses it ("forever").
    First approve or refuse the lab change in C681's row (udhcpc6 kept running, the address
    installed with the lease's lifetimes). Then, for each of 2001:db8:10::/64, :20: and :30:,
    DHCP › Subnets › **Edit…**: valid lifetime `1 d`, preferred `12 h`; **Preview** (renew and
    rebind derived), reason "C681: shorter IPv6 leases"; confirm. Expect "changed", read back,
    a commit of `dhcp/subnets.yml`, and the next lease a host renews ending a day out.
    **What it will NOT do:** Kea's lease file holds each lease's own lifetime, so an existing
    lease keeps its end (expected from Kea's lease records, not yet measured), and h1's three orphans
    (::101, ::102, ::105, IAIDs no client uses again) keep their 2027 ends: nothing renews
    them. Shortening the lease time stops new orphans from living a year; the three need
    releasing (C681's row: a previewed release through Mercury, which you set aside on
    2026-10-12 on the expectation that they would expire). The read-back after this step
    shows it: ::101 still ends 2027-10-06. Undo: Edit… back to 365 days.
15. **C695 (a), your pick (2026-10-12): the ISP peering /31s into OSPF, passive.** Outside 08:30
    to 09:10 UTC; nothing on s3. Today r1 pings 198.51.100.1 0/5 (its flow hashes to r4,
    which has no route to it) and 198.51.100.3 5/5 (measured 03:25 UTC).
    a. **r3 › Intent › Edit**: under `routing.ospf` (process 1), add to `settings`
       `- passive-interface GigabitEthernet2` and to `networks`
       `- network 198.51.100.0 0.0.0.1 area 0`. **Preview**: two lines added against intent
       and against the device. **Commit** with the reason "C695: r3's peering /31 into OSPF,
       passive".
    b. **r3 › Actions › Deploy…**: the program is those two lines under `router ospf 1`
       (passive-interface before the network line, since the template renders `settings`
       before `networks`, so no hello leaves toward r5; if the preview shows another order,
       stop and tell the agent); confirm.
       Expect verify passed (OSPF's settle window waited out), a receipt, and on r3's
       Neighbours the same OSPF neighbours as before (none toward r5: Gi2 is passive).
    c. The same for **r4**: `- passive-interface GigabitEthernet2` and
       `- network 198.51.100.2 0.0.0.1 area 0`; reason "C695: r4's peering /31 into OSPF,
       passive"; Deploy….
    d. **The proof (the agent runs it after your confirms, read-only):** Path… from r1 to
       r5's 198.51.100.1 shows one branch, via r3, delivered (r1's CEF for it is now
       198.51.100.0/31 via 10.255.3.13 only); Show commands on r1:
       `ping 198.51.100.1 repeat 5 source Loopback0` 5/5, and the same for 198.51.100.3.
    Undo: Intent › Edit to remove the two lines, commit; the deploy preview offers them as a
    Mode B removal with your reason.
16. **C691, Snap to grid** (closes it): Topology at a desktop width with **Snap to grid** on;
    drag one device (e.g. s2) a little: a dashed ring marks the dot it will land on; let go.
    Expect it to land on that dot, the map redrawn with the switch still on, the line under the
    map naming you as the last to arrange it, and the move on History (Topology layouts). Undo:
    drag it back (it lands on a dot), or **Reset layout** (withdraws every person's moves, for
    everyone).

### Sitting 3: fleet-wide writes (each previewed; you confirm)

1. **Save All** (Devices › Save…): every device saved and read back, then one capture commit.
   Expect a baseline earned and, within seconds, the lab sync starting (the clab VM's sync log
   or the labs' repositories at the new baseline). **And (C686, fixed 2026-10-12):** History's
   line counts this commit as verified, as you; the three of 10-09 stay "not verified". Undo:
   none (saving running to startup).
2. **Deploy to several devices** (Devices › select r1 and r2 › Deploy…): with nothing pending the
   preview says it changes nothing; confirm to prove the batch path. Undo: none needed.
3. **Bulk intent** (Devices › select s1, s2, s4 › Change a setting…): choose a setting and set
   each device to the value it already has (the preview says nothing changes), or a harmless
   one you will set back. Undo: the same screen, the old value.
4. **History › Baselines › Re-apply** the newest baseline: the preview should say it changes
   nothing on any device (it is what they run). Confirm only if it does. Undo: none needed.

### Sitting 4: Reload, r6 only

Outside 08:30 to 09:10 UTC; nothing on s3. r6 › Actions › **Reload…**: the six gates pass (running
equals startup; startup carries Mercury's credential; the image exists). Give a reason; confirm.
Expect, in order: the planned-restart window declared FIRST (History › Restarts shows it before
the restart), the session dropping, SSH answering again within the bound (about 6.5 minutes for
an emulated IOS-XE), verify "runs what it ran", and the run recorded. Undo: none (a reload cannot
be undone); if r6 does not come back, its console and break-glass record.

### Sitting 5: a device's first boot through Discovered (boards L and M)

Needs a configless device booting on the ZTP segment: a throwaway C8000v on the lab host (the
agent can stand it up under the Phase 7 mode, outside 08:30 to 09:10 UTC; never s3). It also
measures the open question in NSOT_STAGE7_PLAN 16: what a configless C8000v does once it takes
a discovery lease.
1. **Devices › Discovered**: within a minute it is under Asking now, vendor class ciscopnp, an
   address from .192/28, its cadence once a second request is seen.
2. **Pick…**: Add device opens with its MAC and the ZTP way; name it (e.g. `r8`), platform,
   role, management address; **Review the plan**: the first-boot config is the management plane
   only (hostname, the one-time account, domain, address, SSH); **Create** as you.
3. **r8's page (pending)**: the five steps; step 4 moves through Kea's and the responder's
   sub-states as it reboots onto its reservation (a long-asking device may need the reload the
   picked group names).
4. **Verify…** when it answers: rotated, first golden, in the inventory. Its result names the
   next step: **Deploy its intent…** (or where to write its intent first).
5. **Deploy** its intent: an ordinary deploy, previewed, confirmed, verified.
Undo: Abandon… before Verify; after it, Retire.

**Answered (the operator, 2026-10-11 evening):** CDP no (RIP and RIPng are the witness; C671 kept
as an observation); C673 yes (surveyed: only s1's Gi0/0 sends, s2 already passive; the deploy is
sitting 2 step 3); the sidebar's Logs a live tail (C675); onboarding reads a Planned NetBox
record (C676).

**Phase 7, re-estimated 2026-10-12** (a 7.8 family took 20 to 40 minutes; a board step 40 to
90): the 7.8 removals left (about 16 families; today's device page and the AI agent the large
ones; Backups after today's template editor), about 7 to 10 hours; C681's lab image, about 1;
sitting 5's throwaway device, about 1; then the walk with you, about half a day of your time.
**About 9 to 12 agent hours plus the walk.**

## OVERNIGHT RUN, 2026-10-11 (the operator's list, items 1 to 9): status

Kept current after every item so the run can resume. Started 06:34 UTC on 2502f5c (deployed:
fbdc686; 2502f5c is documentation only). Device rule tonight: read-only commands only, never on
s3, nothing 08:30 to 09:10 UTC.

| # | Item | State |
|---|---|---|
| 1 | C671: measure r1–s1, r2–s2 as a possible real fault | **done** 06:45: no routing fault, traffic both ways; LLDP alone fails (s1/s2 Gi0/2 receive no LLDP); CDP off on r1/r2, so no second witness tonight (enabling it is a config change, the operator's). Raw captures: `~/Documents/nmas-reports/2026-10-11-c671-captures.txt` on the laptop |
| 2 | C670: the layout's grid version, timed | **done**: 0.17 / 0.45 / 1.34 / 2.47 s at 150 / 300 / 600 / 900 devices (was 0.48 / 1.90 / 7.82 / 32.82); deploy and host check with the commit |
| 3 | C663 steps 2 and 3: the lab out of the product | in progress. **Step 2 built** (suite green, 9906 passed): Mercury's lab settings, `/clab/sync_targets`, the lab-startup check, reader and rows, job health's clab-sync rows, the rotation's boot-file stages (persistence is the device's save, read back), retire's startup step, the startup-applies checker; `netbox_excluded_vrfs` empty by default, ratified on the host first. **Committed 0f6d480, CI #623 green, deployed 07:51 UTC and checked:** the host's `netbox_excluded_vrfs` ratified before the deploy (origin file, 1 VRF; the step's one action run from the old release, as `claude-agent (host shell)`); `/v2/` 200, job health has no clab-sync row, `/clab/sync_targets` 404, Needs attention reads (one row: step 1's host step awaiting the Update page's confirm, on the walk list). **The sync proved unchanged:** a baseline-earned event written through the product's hook at 07:52:11 started it the same second; 9 devices at the same line counts as the 07:38 run (152/147/181/181/105/192/192/139/119), every file "unchanged", "Both labs already hold baseline/20261009T044804Z; nothing to update", and no exit notice. **Step 3a built** (suite green): the bootstrap's vrnetlab platform tables became the device's environment read from NetBox (`mgmt_only` interfaces, the config context's `environment_owned_lines`; a device with none has none), recorded with the bootstrap parameters; the import never clears `mgmt_only`; the lab's change records to `lab/intent-changes/`; product wording generic. **Committed e42fb8c, CI #624 green, deployed 08:15 UTC and checked:** `/v2/`, Devices, History, Settings and `/v2/onboard/new` answer 200; the environment reader asked the real NetBox for r1 (found, id 5: nothing management-only, no owned lines, the lab having set none). **Step 3b: committed 733b136, CI green, deployed and its host step run by the agent** (`c663-step3b-topology.sh`, 8 of 8 checks PASS: the unit rendered from the installed one, `nmas-topology.service` active and answering on 8088, the old unit and link gone); the app's own check reads done. **Item 3 stands at one entry on tests/test_lab_specifics.py** (`scripts/nmas-host`, blocked on the CLAUDE.md paste below), plus the spent one-shot host step, removed with it. Inventory 7 files / 28 lines before 3b: the topology renderer's name (3b, a host step) and `scripts/nmas-host` (needs the operator's CLAUDE.md paste). Question for the operator: onboarding refuses a name NetBox holds, so a new device's environment is always none |
| 4 | C665: roles and platforms from NetBox | **done** (1421a66, CI #627, deployed 08:56, Settings › Platforms and roles, Topology and Devices checked 200), but for the two role kinds NetBox refused (walk list). Was in progress: surveyed (the kind drives behaviour in 10 places, the hostname guess is display only, NetBox 4.6.9's Platform has no driver field); step 1 (the `mercury_kind` field's reader and migration) committed ff76a59, CI #626, deployed 08:38 and run on NetBox: the field created, the two role writes REFUSED by NetBox (403: the token may not change device roles; walk list). Step 2 built (the inventory reads NetBox's kinds; the role map and its card gone; no hostname guess; the import never overwrites a role; suite 9940 green). The host's only network is local, so no behaviour moves there |
| 5 | C667: History › Query, boards A to C | in progress: 5a built (the Query tab, board A's coverage and questions; Syslog by device at its board's home, the sidebar's Logs drawing the same page; boards A and C compared, records written; 67d52bf, CI #628, deployed 09:20 and checked). 5b built (board B's metrics question, through Monitoring's Grafana path and chart; compared; 55793c0, CI #629, deployed 09:34 and checked on the host: the data route answers 9 of 9 series, an unknown device refused by name). 5c built (board A's "CPU and memory trend" in board B's layout, per device, measured first: the routers carry CPU and memory objects, the switches CPU only; c672580). Next: saved views, editing the PromQL, Ask your own, the other three questions. **For the operator:** what should the sidebar's Logs be? Board C's "Open these lines on Logs" implies a live log view (a tail of the network's lines); no board draws one, so nothing was built |
| 6 | C662: RIP and RIPng read into Topology | **done: 36b4439, CI #630, deployed 10:02 UTC, walked on the host; C662 and C671 closed.** The reader's first read 10:02:54 (four devices, 8.8 s, no error); Topology at 10:03:57: RIP and RIPng up both ways on r1–s1, r2–s2 and s1–s2, r1–s1 and r2–s2 witnessed, Needs attention's "not as intended" empty (was 2). Built: a RIP reader asking the RIP/RIPng devices every 300 s (two read-only show commands each); RIP and RIPng as layers; the second-witness rule (C671): r1–s1 and r2–s2 drawn as intended when RIP and RIPng are heard both ways, the card's LLDP row naming the silent end. Re-shot against the boards (templates unchanged). C673 registered (LAB: s1 speaks RIP on its management port) |
| 7 | C529 DHCP step 2 (then 3, 4; 5 only with a fresh copy) | **step 2 built, ae306de** (gate green, 10187 passed; CI and the deploy running): board B on DHCP › Reservations, each change previewed against Kea, confirmed by hash as a verified person with a reason, written to Mercury's file for the subnet, tested by Kea's own check, reloaded, read back across every place Kea holds reservations (subnets, shared networks, global; a hosts database refuses), restored when it disagrees, committed to `dhcp/reservations.yml`; compared with board B (docs/fidelity/dhcp.md). Deployed (ae306de, then c672580 with the host step's fix and its app check, CI #632). **The host step run by the agent at 10:58 UTC, 7 of 7 PASS:** the dated copy `/var/backups/kea/c529-step2-20261011T105829Z` (root's, 700: kea-dhcp4.conf, kea-dhcp6.conf, kea-ctrl-agent.conf, /etc/kea/nmas, all of /var/lib/kea) read back identical to the originals before anything changed; IPv4 subnets 10 and 20 and IPv6 10, 20 and 30 given their files, candidates passing Kea's own check; Kea reloaded; Kea's configuration hash unchanged in both families. **Walked:** the app's check reads done; a board B preview against the live Kea answers with every check and its hash; the form offers 5 subnets (ZTP's left out). The first real reservation is the operator's (walk list). Steps 3 and 4 (boards C and D) not started |
| 8 | The cutover blockers | **nothing left to build**: CUTOVER.md has no PLANNED row (re-read 10:40 UTC); all six blockers were built 2026-10-10, most "not run on the host", which needs a verified person for each confirm: they are the walk list below. No board was missing |
| 9 | Nice-to-haves, CUTOVER 7.5 to 7.7 | to do |

Logged blockers and stops:
- **C663, the last entry on tests/test_lab_specifics.py** (`scripts/nmas-host`, the operator's
  access helper, with its `clab` host name): it moves to `lab/nmas-host` once CLAUDE.md names
  the new home, and CLAUDE.md is the operator's. Paste, replacing the three lines as they are:
  - line 69: `- **Read-only measurement of lab services is the agent's to run**, through `lab/nmas-host`,`
  - line 402: `` (2026-09-29). `lab/nmas-host` reads it and refuses, naming the file, when it is ``
  - line 413: `` `lab/nmas-host <nmas|clab|pve> -- <command>`.** For scp and rsync, ``
  Then the agent moves the file, its hooks' and the lab sync's references and its tests, in
  one commit. The one-shot host step `c663-step3b-topology.sh` is on the list too, until it
  is removed after it has run.

**Status, 2026-10-10 (UTC).** The Phase 7 operating mode is ON: the operator ran
`scripts/host-steps/phase7-mode-on.sh` (about 02:23 UTC), and CLAUDE.md carries its section.
Done: receipts on the records database (d79ba34, not yet moved on the host); C630 (CUTOVER.md
re-measured and held to the route map) and C636 (b2b49cb); C631, the remote's set-up on History
(3cbd74a); cutover blocker 1, networks: the picker (eda63ea), create and delete (b3cee34), the
inventory source (6e73ac6); blocker 2, NetBox import and remove with turning writes on (C619,
65f87c3); blocker 3, onboarding on v2 (Add device, and the pending page's Verify, bootstrap
config and Abandon, each bound to its preview, 5f0c36c); blocker 4, Capture's reason for a
shrink and What next by direction (C486, b883fb6); blocker 5, Templates' Edit… (7e6efea),
Bindings… and Seed the library… (2e89ffc); blocker 6, Reload (P.14's plain form, its window
declared first, 4cf33e0). All six cutover blockers are built. Nice-to-haves done: batch deploy
(d8651d0), Re-apply (ec1f11b), C633 with C642 (a42d8df), the golden reveal (74b50a3), Adopt on
Devices (board G, f09ac7c, finished as the board ends it in 83fbb5a), bulk intent (board D),
Templates › Coverage (8250677), Credentials › Profiles. No v2 page sends a person to today's
pages any more. CUTOVER's rows still PLANNED: the topology service, P.11, in steps: step 1, its reader, is built and walked on the
host (629c7a8, C648 3f21f83 and 9571439; the host runs 9571439: physical 11 links as cabled,
OSPF 16, OSPFv3 7, BGP 4, r6 the one island); r5 drawn as one outside peer and islands
expected by declaration (30f8c1b); step 2, the page, first built from the
boards' written description (b79e335), did not match the signed-off boards (C649, the operator,
2026-10-10); REBUILT to TopoDesktop and TopoPhone (d720434): every link's ports and a chip per
protocol with its area or peer AS and state, line styles against intent, icons in measured
bands, Mercury's measured place, Needs attention on the map, the phone's tabs and sheet;
compared region by region in docs/fidelity/topology.md, 11 deviations logged. The host walk
found Mercury drawn attached through containerlab's shared address and as a path between
devices (C653, fixed 57883db); walked again on 57883db: s3 Mercury's only way into seven
devices, r6 apart on purpose (the operator marked it) and reached directly. C650's fidelity
step is in place (tests/test_board_fidelity.py; 32 signed-off screens still to compare, the
list only shrinks). The operator then found the map too busy (C654) and asked for it to be
arranged by people (C655); both were built (a597479, b8f3f0f) and, shown the after shots, the
operator sent Topology back to the approved board v34, Arrange out too (both WITHDRAWN, in the
register's Closed). The operator then pointed at the approved boards themselves: the build had
never matched them (13 regions logged as the agent's "deviations"). C658 drew the page to them
(840329e: the board's two-word chips per link, its toolbar, legend, times and phone list),
compared again at 1440, 1280 and 390 (7 regions still differ, each with its reason in
docs/fidelity/topology.md), deployed and walked on the host's own read 2026-10-11. Open from the
walk: C659, fixed and walked 2026-10-11 (222054b: no link drawn across a device, name or tag
it does not join, checked in a real browser). Wall view and Arrange stay later steps. DHCP
(C529) step 1 built 2026-10-11: the DHCP reader and the read-only page to board A, the sidebar's
DHCP under SOURCE OF TRUTH, docs/fidelity/dhcp.md; deployed and walked on the host the same
day (4f9a699: both families read, the capture's counts); C660 (the reader's reservations outside a
subnet, 81e3334, walked). The operator's queue since, in order: C661 (Topology arranged by
people, panned and zoomed, no bands: 335c0ee, walked), C664 (Settings › Installation's layout),
C666 (the drift check's Last column) and C668 (Topology's card closes, smaller): done together;
then C663 (the lab out of the product), C665 (roles and
platforms from NetBox), C667 (History › Query to boards A to C), C662 (RIP and RIPng on
Topology), then C529 step 2; next after those, step 2 (board B, with the one host step
that moves Kea's subnets into Mercury's files). Then time travel
and the wall (whose kiosk identity is a Cloudflare Access service token: stop 2, the operator's); C635 closed (the checker reads receipts
in the records database); Logs (C652, the operator 2026-10-10): the sidebar's Logs opens
the queryable logs, History › Query board C's "Syslog by device" (e9d4fbe, e112246 and the
Newest fix after them), counted per day by the `logs-summary` reader; compared with AskLogs in
docs/fidelity/logs.md; walked on the host (its first reads: 71 s, then 7.7 s after the first-line
search was fixed, the history filling 7 days a read; the lab's Logs retention set to 730 days,
from 90, through the settings write path, as NSOT_STAGE7_PLAN 14.15 said). Next: DHCP (C529)
steps 2 and 3 (boards B, C and D; step 1, the read-only page, is built), boards L and M, C641,
7.5 to 7.7, the 7.8 removals and the walk. Since 2026-10-10 each change is deployed and walked
on the host as it lands (Phase 7 mode); the walk at the end runs everything again.

**Next, in order** (the operator's, 2026-10-09): receipts (Phase 4, Mercury's records in
PostgreSQL); C630 (CUTOVER.md re-measured); C631 (the remote's set-up); the six cutover
blockers in dependency order (networks, NetBox import and writes on, onboarding, capture's
acknowledgement reason, the template editor, Reload); the nice-to-haves; 7.5 to 7.7; the 7.8
removals; then a walk of everything on the host.

**Waiting on the operator:** nothing. Stop 3 (NetworkX) was answered YES on 2026-10-10: pinned
at 3.6.1 (f829171), recorded in docs/THIRD_PARTY.json, and carried through Phase 4 section 8.4 on
the host the same day: the venv `f21256e61a35` built and proved beside the running one (15 of
15), the deploy swapped the link, `.previous` names `9d27674e53bf`, both kept, `/health` 200.
The overrides then came off in their own lock change (f9dc11e), carried the same way: the host
now runs f9dc11e on `mercury-venv-53a6aabdd2c2` (previous `f21256e61a35`), `pip check` clean,
the updater's root copies re-installed from this release. The three uv
overrides come off in the NEXT lock change, on their own, with `pip check` clean after it. Under
the mode only the four stops wait on the operator: a secret value, anything outside the lab, a new third-party
package licence, and deleting or rotating backups or snapshots.

**To resume:** read CLAUDE.md, then this file, then docs/OPEN_FINDINGS.md's Count, and
docs/STANDING_APPROVAL_LOG.md for what was decided under the mode.
