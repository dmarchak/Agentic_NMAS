# Phase 7 burn-down: every item between today and cutover

**The operator, 2026-10-15 ("Phase 7 first").** Cutover is the retirement of today's (v1) pages
(docs/CUTOVER.md) with Stage 7's acceptance criteria met (docs/NSOT_STAGE7_PLAN.md section 10).
Built from two read-only surveys at fcd1e4f6, 2026-10-15; **revised the same day with the
operator's decisions** (D1 to D6 accepted; a trim to Stage 7's tail; C650 done during the walks;
section 1c re-checked against the host). Each report shows this list with items checked off.
Mutation testing is parked (docs/TESTING.md); Lab 7 is down to its fact sheet.

**Where it stands.** CUTOVER.md's own rule (no PLANNED, PARTLY BUILT or UNDECIDED row) holds:
what blocks removal is walks, harnesses that still measured v1 (moved, P7-19), and a few v2 gaps.
Four v1 families are gone (the sixteen unreachable routes, bulk commands, the Drift tab, the
Settings modal with Logs and the status bar). Left: `templates/index.html` (Devices, NetBox, Git
tabs), `templates/device.html` (Utilities, Changes, 8 actions), `base.html`, 14 partials, 13
`static/js/gen` files.

Sizes: **S** under a day of agent work, **M** one to three days, **L** more. **Op** = needs the
operator (W walk, H host step, B board; boards are self-signed under the Phase 7 mode).

## 1. The operator's items

### 1a. Decisions: ALL DECIDED 2026-10-15, as recommended

| # | Decision |
|---|---|
| D1 | `/identity/status` and `/settings/integrations/status` kept as non-GUI diagnostics, out of the cutover count |
| D2 | C537, the every-page in-flight indicator, built on v2 (canvas v66) before `/` goes |
| D3 | 7.10 (A3 at scale, the 900-device screens, the inventory-source switch), P.12 monitoring templates, P.7, P.8 step 9, P.9, P.11 step 3, P.15's rest: after cutover, Stage 7's tail |
| D4 | The scheduled Stage 9 security rows stay in Stage 9; one is pulled in only if a cutover change touches it |
| D5 | The 2026-10-07 "Now" rows that are v2 improvements, measurements or harness: out of Phase 7 |
| D6 | C730: the golden archives in MinIO masked, inside Phase 7 as a security item |

### 1b. Walks: each sitting handed over as a script the moment it is ready

A confirm by hash needs the operator's Access session, so each sitting is the operator's browser
following a script (`docs/walks/W<n>.md`). **C650's board comparisons happen IN the sitting:** each
step names the board to compare the screen with and what to look for, and the fidelity record is
written from the sitting's results. Screens no walk touches move to Stage 7's tail.

| Sitting | Walks | Clears | Ready |
|---|---|---|---|
| **W1 Devices and the device page** | several-device deploy (s3.2); Re-apply (s3.4); bulk intent (s3.3); a golden reveal (s2.6); the Ask tab reading a device (C547); Capture's shrink reason (s2.5); Reload on r6 (s4); intent edit on v2 (C444, THROWAWAY Part 5) | CUTOVER rows 42, 44 to 46, 53, 54, 68, 69; C547, C444; the fidelity records of the screens it touches; unblocks P7-22, P7-24 | **WALKED 2026-10-16** (23:20Z to 01:12Z): CUTOVER rows 42, 44 (Capture, Save All), 45, 46, 53, 54, 69 and C588, C547, C587, C444, C539 closed; section I (row 68) blocked by C881 and C691 held by C882, both into W2 |
| W2 Templates, NetBox, networks, remote | Templates approve, edit, bindings and seed (s2.7); NetBox (s2.10); networks new and delete (s2.9); Remote push, verify, set-up and auto-push (s2.11); inventory source; topology page; saved views (C667); the settings Save (C811); the 37 findability questions, clicks counted (P7-07; docs/NSOT_GUI_BRIEF.md 2.3's H column and 16); **from W1: r6's Reload (section I, CUTOVER row 68), C881's Reload… preview with no reload sent, a C691 drag re-check, and B1 to B5 (C882 to C886) walked on v2**; the host keys (C906); C532's intent state, C342's Drift row, C537's In progress chip, C954's Stop tracking preview | CUTOVER rows 48 to 50, 56, 57, 60 to 62, 68, 70; C667, C691; W1's A1 and B1 to B5 by the operator's eyes; their screens' records; unblocks P7-20, P7-21, P7-23, P7-26 | **WALKED 2026-10-16** (21:12Z to 2026-10-17 00:22Z, against ae8175bdbc): CUTOVER rows 49, 50, 56, 57, 61, 62, 68 and 70 and C691, C667, C941 closed; C881, C882, C884, C931, C811 and W1's B1 to B5 confirmed; P7-07 walked; rows 48 and 60 walked, closing with C1024, C1023 and C932; C1010's backfill confirmed (read-back pending). Found: A1 C1022, B1 to B8 C1023 to C1030, B9 C932 (section 2), and C1031 to C1073 (section 4) |
| ~~W3 W2's fixes~~ | **done 2026-10-17** (W4's script written the same day, docs/walks/W4.md) (05:16 to 06:18 UTC on fecab2f79e, docs/walks/W3.md): A1 and B1 to B9 walked on the host; CUTOVER rows 48 and 60 closed; C1018 and C677 settled; one B found (C1109, the settle period) | | |
| ~~W4 Onboarding and recovery~~ **DONE 2026-10-17 18:34 to 21:22 UTC** | onboard a throwaway on v2 (s5) through deploy, break, roll back (C148); adopt's first real run (board G); revert and retry (row 52 reconciled with THROWAWAY's 2026-10-05/06 runs); C553's clab-sync start; C529's DHCP confirms (docs/walks/W4.md) | CUTOVER rows 52, 58, 59 walked; C148, C553, C529 closed; their screens' records (C650) owed from the evidence folder; P7-24, P7-25 unblocked; six defects fixed forward in the sitting (C1148 to C1151, C1179, C1180) | after W3 |
| (in any sitting) | ~~C539, C587, C588~~ (walked in W1); ~~snap-to-grid (C691)~~ (walked in W2); DHCP confirms (C529, in W4) | those rows | W4 |

### 1c. Host steps and small acts (re-checked against the host's Update data, 2026-10-15)

Done and removed: C722 (the Loki `device` label, checked done), C725 (the config repository's
pipeline, said done by the operator), and the three steps without a check (the loki-writer
rotation, the ai-leftovers delete, the Backups archive and delete, said done by the operator).

| Item | Op | State |
|---|---|---|
| ~~C794: Loki's own `detected_level` off~~ | H | **done by the operator, 2026-10-16 ~19:36 UTC: PASS (10 of 10)**; and C964's `nmas-device` re-import done, its JSON model free of lab names, r1's panels drawn with data in Grafana and on Mercury's Monitoring page |
| ~~C553: `clab-sync.path`~~ | H | **installed** on the NMAS host (read 2026-10-16: active, enabled, identical to a fresh render); the walk showing the sync start remains (W2's script did not carry it: W3) |
| C549 (3): the Update confirm, in the root-owned updater | H | **decided 2026-10-17:** closes at the operator's next Update from the page |
| ~~C663: move `scripts/nmas-host`~~ | — | **closed 2026-10-17**, the operator's decision: it stays where it is |
| ~~C296: batch preview empty bullets~~ | — | **closed 2026-10-17** as not reproduced, the operator's decision |

## 2. The agent's items, in order (independent ones in parallel)

| ID | Item | Done means | Size | Deps | Op |
|---|---|---|---|---|---|
| **From W2, first (the operator's order, 2026-10-17: A1 first, then the Bs, each with a test that fails before the fix)** | | | | | |
| ~~C1022~~ | ~~A1: a page's network is lost after its first render~~ **done** (every request a v2 page makes carries its network, `routes/page_network.py`; C873, C874 and C1077 with it; W3 walks it) | | | | |
| ~~C1023~~ | ~~B1: buttons that start slow work show nothing until the result~~ **done** (a form's submit button held busy and disabled until its answer draws; 117 pressed controls that post, each with its busy words; walked at W3) | | | | |
| ~~C1024~~ | ~~B2: read-only operations record "unauthenticated"~~ **done** (every recorder names its verified person; the first commit and NetBox job records too) | | | | |
| ~~C1025~~ | ~~B3: a declared planned-restart window silences nothing~~ **done** (two Grafana silences per window; no row inside it, "restarting as planned" under What was checked and in the header; walked at W3's reload) | | | | |
| ~~C1026~~ | ~~B4: no "Restarted as planned" on r6's History after its reload~~ **done** (a restart between two minute reads is found; walked at W3's reload) | | | | |
| ~~C1027~~ | ~~B5: the reload record is never committed~~ **done** (committed through `repo.commit()`; "not committed" in the header; walked at W3's reload) | | | | |
| ~~C1028~~ | ~~B6: a network's History draws another's rotation and persist rows~~ **done** (every shared store told by the network's own devices; an unreadable inventory said; walked at W3 on a non-default network) | | | | |
| ~~C1074~~ | ~~a read re-creates a deleted network's folder~~ **done** (the accessor never makes a deleted network's folder; the host's empty `lists/w2_walk` removed after the deploy) | | | | |
| ~~C1029~~ | ~~B7: a deleted network's Settings page stays live, with Save~~ **done** (410, when, by whom, where its data is, no actions; every write naming it refused; walked at W3) | | | | |
| ~~C1030~~ | ~~B8: the NetBox import is missing from History~~ **done** (a NetBox source: imports, removals, Stop tracking; walked at W3) | | | | |
| ~~C932~~ | ~~B9: Remove from NetBox offered over a `not_reached` reach~~ **done** (Remove only when every delete's reach is established; "Remove is not offered:" in words) | | | | |
| ~~C1097~~ | ~~Remove from NetBox is never offered on this lab~~ **demoted to C** (the operator, 2026-10-16 UTC−6: cutover does not need NetBox Remove; Stop tracking covers it, and Remove stays withheld while any cascade is unmeasured; no NetBox writes for it) | | | | |
| **From W1 (the operator's sequence, 2026-10-16)** | | | | | |
| ~~C881~~ | ~~A1: Reload's startup gate on IOS-XE~~ **done, verified on r6** (see Checked off) | | | | |
| ~~C882~~ | ~~B1: Topology drag jumps~~ **done** (see Checked off); C691 re-checked in W2 | | | | |
| ~~C883, C888, C905~~ | ~~B2, C2 and R4: the batch preview's note, client-side order, drag and drop~~ **done** (see Checked off) | | | | |
| ~~C884, C885, C886, C913~~ | ~~B3, B4, B5 and adopt's comparison~~ **done** (see Checked off) | | | | |
| ~~C923~~ | ~~Adopt's card draws the lines startup gains and loses~~ **done**, with C930 (see Checked off) | | | | |
| **Security** | | | | | |
| ~~C730~~ | ~~the golden archives in MinIO masked (D6)~~ **done** (see Checked off) | | | | |
| ~~C931~~ | ~~Seed on a network created on v2~~ **done**, with C943 (see Checked off); W2 section H walks it | | | | |
| ~~C948~~ | ~~the Stage 2 redeploy checklist brought to today's rules~~ **done, a dated revision** (the operator's decision; see Checked off) | | | | |
| ~~C944, C945~~ | ~~the unused `git init`; History's header~~ **done** (see Checked off) | | | | |
| ~~C957~~ | ~~History's timeline says "no repository yet"~~ **done** (see Checked off) | | | | |
| ~~C933 to C936~~ | ~~From writing W2 (B)~~ **done** (see Checked off) | | | | |
| ~~C1016~~ | ~~a failed Verify of the remote draws no fix~~ **done** (B, security; each failed check's own fix drawn under "To fix:") | | | | |
| ~~C1010~~ | ~~Mercury's prefixes in NetBox carry no site~~ **done, read back 2026-10-17: #55, #56, #57 each `dcim.site` / 1 / Default** (see Checked off) | | | | |
| ~~C954~~ | ~~v2's "stop tracking" for a NetBox removal~~ **done, built** (the operator's decision; see Checked off) | | | | |
| ~~C955~~ | ~~Retire's preview counts live approvals only~~ **done** (see Checked off) | | | | |
| ~~C906~~ | ~~Mercury checks each device's SSH host key~~ **done: deployed 1222a3f102, all nine devices' keys kept on the host** (see Checked off); the next redeploy declares `--new-host-keys` (lab/REDEPLOY.md) | | | | |
| ~~C940~~ | ~~onboarding at a reused address~~ **done** (see Checked off) | | | | |
| **Harness: the checks on v2** | | | | | |
| ~~P7-04~~ | ~~Criterion 4, payloads drawn on v2~~ **done** (see Checked off); its gaps are C867 to C869 below | | | | |
| ~~P7-05~~ | ~~Criterion 5, invalidation~~ **done** (see Checked off) | | | | |
| ~~P7-07~~ | ~~Criterion 10, the sidebar: an order test (done); the 37 findability questions walked~~ **walked in W2** (steps 8 to 11, 2026-10-16): 23 within the brief, 9 over it (C1070), 4 not found (Q23 in C759; Q24, Q32, Q37: C1071 to C1073), Q31 by design | | | | |
| **v2 gaps cutover needs** | | | | | |
| ~~C855~~ | ~~criterion 11: the v2 device page's per-device work~~ **done** to 19 (see Checked off) | | | | |
| ~~C876~~ | ~~the manifest's name lookup~~ **measured**: quadratic but 0.43 s at 900 devices inside requests whose per-device git reads cost more (C912); resolved to C, moved to the tail | | | | |
| ~~C850~~ | ~~criterion 6: the Alpine confirm components to the one pattern~~ **done**, 4 → 1 (IP SLA's with P.12, D3) (see Checked off) | | | | |
| ~~C537~~ | ~~the every-page in-flight indicator (D2), then C540's wording and C217's one row~~ **done: D2 met** (see Checked off); the command box and the rest stay in C537's row, to the tail | | | | |
| ~~C987~~ | ~~the In progress chip's holds read grows with every lock file ever made~~ **done** (see Checked off) | | | | |
| ~~C988~~ | ~~an unreadable lock folder reads as "nothing held"~~ **done** (see Checked off) | | | | |
| ~~C991~~ | ~~`nmas-deploy` continues on an unreadable holds store's 500~~ **done** (the operator's decision; see Checked off) | | | | |
| ~~C867~~ | ~~v2's deploy card draws the plan's attribution~~ **done**, with C878 (the batch preview's) (see Checked off) | | | | |
| ~~C868, C869, C860~~ | ~~the restore chooser's message; the profile proposal's reads and skips; v2's Save's repeated-baseline warning~~ **done** (see Checked off) | | | | |
| ~~C543, C544~~ | ~~Needs attention's action words~~ **done** (see Checked off) | | | | |
| ~~C487, C493~~ | ~~Needs attention names each row's network; no store falls back~~ **done** (see Checked off) | | | | |
| ~~C532~~ | ~~Devices list and device page agree on intent state (one comparison)~~ **done** (see Checked off) | | | | |
| ~~C342~~ | ~~the device page's drift: masked diff and three choices~~ **done, built from its board C342Drift** (see Checked off) | | | | |
| ~~C522~~ | ~~the 8 lone (i) cards~~ **done** (see Checked off) | | | | |
| ~~C820, C821~~ | ~~the syslog job; an integration's 4xx reason~~ **done** (see Checked off) | | | | |
| ~~C963, C964~~ | ~~the heartbeat rules and the device dashboard~~ **done** (see Checked off); the dashboard's re-import is the operator's, after the deploy | | | | |
| P7-09 | Criterion 14, the writeup: entries for 7.4 to 7.8, P.11, Show commands, Ask, Logs, DHCP, Update; 7.3 and 7.D closed. **Every sub-task has its entry (2026-10-16 and 17; NSOT_WRITEUP.md Part II), forecasts checked; 2026-10-18: 7.3 and 7.4 closed, 7.D's "where it stands" (it closes with C650's four records); later that day 7.8 closed, its entry written at P7-27's merge, and 7.D closed with About's record from the operator's P7-27 walk: P7-09 done** | an entry per sub-task, forecasts checked | M | — | W4 |
| ~~P7-16 (rest)~~ | ~~C705, C765, C176; the Scheduled section's 7.x rows read once~~ **done** (see Checked off) | | | | |
| ~~C981~~ | ~~Retire clears the override before its commit (C106 (3))~~ **closed, measured: deliberate** (see Checked off) | | | | |
| **C650, during the walks** | each walked screen's fidelity record written from its sitting; `UNCHECKED` shrinks by the walked screens; the rest to the tail. **W1 to W3 done 2026-10-17** (W1's twelve; W2 and W3's netbox, templates, settings, batch Apply, the device Logs tab). Left for W4: save, pending, retired, about (its pre-flight; a screenshot asked). To Stage 7's tail, no walk touching them: monitoring, help, monitoring_profile, coverage, coverage_deploy, update, settings_installation, reapply (walked in W1 with no screenshot or board), the device Monitoring, Neighbours and NetBox tabs | the four W4 screens' records, from its sitting | S per screen | W4 | W |
| **The v1 removals (each tagged first, walked, ceilings lowered, the ratchet run)** | | | | | |
| ~~P7-20~~ | ~~(4) the NetBox tab and `/netbox/safety/*`, `/netbox/status`~~ **removed 2026-10-17** (restore tag `pre-remove/v1-netbox`; walked by GETs on the host after its deploy) | | | | |
| ~~P7-21~~ | ~~(5) Git, the Remote card, Baselines~~ **removed 2026-10-17** (restore tag `pre-remove/v1-git`; today's re-apply and restore routes with it; C1132, C1133, C1135 (B) and C1134 fixed with it; walked by GETs on the host after its deploy) | | | | |
| ~~C1136~~ | ~~History's header names uncommitted paths without what each means~~ **done 2026-10-17** (each path with what it is and what clears it; history.md compared again) | | | | |
| ~~P7-22~~ | ~~(7) today's device page (`/device/<ip>`, `/run_command`, `/deploy/receipts`)~~ **removed 2026-10-17** (restore tag `pre-remove/v1-device`; run_command's MISSING, HISTORY_MISSING and PENDING entries gone; C1127 and C1128, receipts masked on the way out, fixed with it; walked by GETs on the host after its deploy) | | | | |
| ~~P7-23~~ | ~~(8a) template and intent editors~~ **removed 2026-10-17** (restore tag `pre-remove/v1-editors`; the vendored CodeMirror with them; C33 closed, the last GET that wrote; walked by GETs on the host after its deploy) | | | | |
| ~~P7-24~~ | ~~(8b) device-action JSON~~ **removed 2026-10-17 after W4** (restore tag `pre-remove/v1-actions`): persist, rotate, retire, seed, revert and retry's JSON routes and their five scripts; capture's and the monitoring profile's routes KEPT, with today's index's Save All, "capture devices with no golden" and Propose… their callers, so they go with P7-27 | | | | |
| ~~P7-25~~ | ~~(8c) deploy wizard, onboarding~~ **removed 2026-10-17 after W4** (restore tag `pre-remove/v1-onboarding`): POST /deploy/plan and /deploy/apply, the nine /onboard/* routes, today's deploy wizard, onboarding wizard and pending banner; C1161 fixed with it. **The inventory source stays** (today's banner, GET /inventory/source/<list> and POST /inventory/refresh/<list>) until C1160 (B: v2's card names no skipped or stale device; its template is fidelity-held) | | | | |
| ~~P7-26~~ | ~~(8d) networks; the global active list frozen~~ **removed 2026-10-17** (restore tag `pre-remove/v1-networks`; nothing sets the installation's `current_list` now; C1138, v2's delete guarding NetBox's record, fixed with it; walked by GETs on the host after its deploy) | | | | |
| ~~P7-27~~ | ~~(9) the pages~~ **removed: built 2026-10-18 on the branch `p7-27` (its files say 2026-10-17), merged into main as 4e631168 and deployed 2026-10-18 17:56 UTC (CI #931, its GET walk as expected); the operator's walk, docs/walks/P7-27.md, to come** (restore tag `pre-remove/v1-pages`; C1267): `/` answers 302 to `/v2/` keeping `?list=` (and today's two `?open=` links land on Credentials › export and Monitoring › Profile); GET `/attention`, `templates/index.html`, `base.html` and the six partials, today's last nine scripts and `static/js/gen/`, the vendored Bootstrap (CSS, JS, licence); today's routes behind them: capture's three, golden history, version and diff, the monitoring profile's three, the inventory source and refresh (C1160 open, removed anyway as scoped). `test_no_new_v1_capability` is "nothing outside templates/v2": every ceiling 0 (controls 6, handlers 3, functions 195, fields 1 before), no template or script outside v2, no route outside `/v2/` and `/update/` but fourteen declared non-GUI endpoints; `test_payload_is_rendered.py` left with its renderers (v2's is `test_v2_context_is_drawn.py`). Walk: docs/walks/P7-27.md after its deploy | criteria 1, 2, 16 close; the v1 ceilings at 0 | M | all above | — |

**Rough total after the trim:** about 3 L (C850's `applyConfirm`, C537, P7-04 at its upper end),
13 M and 14 S of agent work, plus three walk sittings (C650 inside them). The removals run as
their sittings clear. **Recomputed 2026-10-16 after W1:** done since: P7-04, P7-05, P7-07's
test, C730, C855, C860, C867, C868, C869 (about 1 L, 4 M, 5 S); added by W1: C881, C882 with
C888 and C905, C906 (3 M), C883 to C886 (5 S). Left: about 2 L (C850's `applyConfirm`, C537),
12 M and 14 S, plus W2 and W3. **Added by W2 (2026-10-17):** C1022, C1023, C1025 (3 M), C1024
(S to M), C1026 to C1030 and C932 (6 S); W2 itself done, W3 left. **Recomputed 2026-10-17
overnight:** W2's A1 and B1 to B9 fixed and walked in W3; W3 done (CUTOVER rows 48 and 60
closed); its B, C1109, fixed; C1121 and C1123 found and fixed; P7-20 removed; C650's W1 to W3
records written; P7-09's entries written. **Cutover-blocking rows: 3, each with its owner:**
C553 (A, the lab sync's start: W4 section H, then the agent's read of its event file); C650 (A,
the four W4 screens' records: W4, then the agent); C148 (B, onboarding through deploy, break and
rollback: W4 sections G to L). **Left:** P7-21, P7-22, P7-23, P7-26 (the agent, tonight); W4 (the
operator); after W4, P7-24 and P7-25 (waiting on W4 and the operator), then P7-27; the
closing entries of 7.3, 7.4, 7.D and 7.8. The operator's three: C549 (3), C663, C296 (section
1c). **Decided 2026-10-17 (morning):** C663, C296 and C1126 closed; C549 (3) closes at the
operator's next Update from the page; C1142 and C1130 after cutover; P7-24 and P7-25 go,
conditional on W4 passing their steps; P7-27 waits for the operator's word.
**After W4 (2026-10-17 21:22 UTC, the operator's "W4 done"):** W4 passed P7-24's and P7-25's
steps, so both are go. **Cutover-blocking rows: C650 (A, the four W4 screens' records) and the
Bs registered 2026-10-17:** C1153 (an instruction naming today's Save All scope), C1159
(a pending onboarding raises rotation-staged), C1160 and C1161 (P7-25's merge), C1165
(Abandon's preview), C1166, C1167 and C1171 (the Lab 7 audit's), C1181 (one Kea, one owning
network), C1182 (`bgp log-neighbor-changes`), C1183 (misplaced intent keys), C1187 to C1193
(W4's part 2). C148 and C553 closed.

## 3. The shrinking lists (distance to cutover)

| List | Now | At cutover |
|---|---|---|
| tests/test_board_fidelity.py `UNCHECKED` | **12** (W4's Save, pending and retired recorded 2026-10-18 from local board shots, About waiting on the operator's screenshot in the P7-27 walk; 15 after W2 and W3's five, 2026-10-17; 20 before, W1's twelve recorded 2026-10-16): 4 for W4, 11 to the tail | the walked screens out; the rest to the tail |
| modules/operation_stages.py `MISSING` / `HISTORY_MISSING` | **6 / 1** (P7-23, 2026-10-17: the editors' four gaps gone; 10 / 1 after P7-22, run_command's gone; only `v2.heartbeat_apply` lacks a history; 17 / 2 before) | run_command's go with v1; the rest stay until built (not a cutover condition) |
| tests/test_results_are_drawn.py `PENDING` | **0, met** (P7-23, 2026-10-17; 3 after P7-21; 7 after P7-22; 8 before) | 0 (all v1 handlers) |
| tests/test_concepts_are_taught.py `PENDING` | **0** (P7-03) | 0 |
| tests/test_v2_one_confirm.py `SECOND_IMPLEMENTATIONS` | **1** (C850, 2026-10-16) | 1, IP SLA's `ipslaPost` with P.12 (D3); 0 after |
| tests/test_invalidation_map.py `NOT_YET_SUBSCRIBED` | **0** (P7-05, 2026-10-16) | 0 |
| tests/test_v2_layout_in_a_browser.py `C503_KNOWN_GAPS` | **0** (C522, 2026-10-16) | 0 (met) |
| tests/test_no_new_v1_capability.py controls / handlers / functions / fields | **0 / 0 / 0 / 0, met** (P7-27, 2026-10-17; 6 / 3 / 195 / 1 after P7-25; 12 / 8 / 259 / 12 after P7-23, 2026-10-17; 19 / 13 / 281 / 15 after P7-26; 23 / 16 / 281 / 17 after P7-21; 25 / 18 / 312 / 17 after P7-22; 36 / 26 / 314 / 19 after P7-20; 43 / 31 / 333 / 20 before) | 0 (P7-27) |
| tests/test_payload_is_rendered.py `UNDRAWN` / `PHANTOM` / `EMPTY` | **gone, met** (P7-27, 2026-10-17: the v1 check left with today's pages; 17 / 0 / 3 after P7-25; 58 / 0 / 20 after P7-23, 2026-10-17; 64 / 3 / 21 after P7-21; 84 / 14 / 23 after P7-22; 90 / 14 / 26 after P7-20) | 0 at P7-27 (the v1 check goes with today's pages) |
| tests/test_v2_context_is_drawn.py `UNDRAWN` (GAP) / `UPSTREAM` / `UNREACHED` | **358** (C868, C869's GAP gone) / **11** (C867) / 23 (2026-10-16) | met: the GAP entries cutover needs gone; `UPSTREAM` 11; the rest reasoned or the tail's |
| tests/signed_off_screens.py `UNSIGNED` | 3 | 1 (not_found stays; heartbeat and ip_sla go with P.12, D3) |
| modules/manual.py `ON_TODAYS_APP` | **0** (P7-19) | 0 |
| tests/test_route_reachability.py `KNOWN_UNREACHABLE` / `NON_GUI` | 0 / 8 | 0 / 8 (D1 keeps two) |
| Moved to the tail: tests/test_large_fleets.py `EXCUSED` 4 (C450); tests/todays_page_links.py `OTHER_GAPS` 1 (P7-30) | | after cutover |

## 4. Out of Phase 7 (declared, not a backlog)

These open rows do not block cutover; each has its home. A new finding joins this list unless it
blocks cutover or is a security issue (B).

- **FUTURE designs (the operator, 2026-10-16), documents only, post-cutover:** C1003 sites
  (`docs/SITES_DESIGN.md`), C1004 flows (`docs/FLOWS_DESIGN.md`), C1005 the kit fleet
  (`docs/EDGE_ARCHITECTURE.md`, Phase 10 or later), C1006 the IPAM import
  (`docs/IPAM_IMPORT_DESIGN.md`), C1007 bring-up from provider documents
  (`docs/BRINGUP_FROM_DOCUMENTS.md`), C1008 offline operation (`docs/OFFLINE_OPERATION.md`);
  C1013, Phase 8 offline-first and the disconnected operator assistant (`docs/PHASE8_PLAN.md`
  section 12).
- **FUTURE designs (the operator, 2026-10-17), documents only, post-cutover (Phase 8 or
  later):** C1146 config to intent, a partner's configuration block added to a device's intent
  through the existing extractor, not-modelled lines reviewed, secrets moved to the store, the
  normal intent commit and deploy (`docs/CONFIG_TO_INTENT.md`); C1147 runbooks and procedures,
  saved parameterised reads, saved sequences of Mercury's own gated actions, and Ansible for
  interoperability only, Mercury never running playbooks (`docs/RUNBOOKS_PROCEDURES.md`).
  Found with them, measured the same day read-only and now C at the tail: C1009 (no device
  outside its network's site) and C1010 (Mercury's prefixes carry no site at all); with them,
  C1011 and C1012.
- **Stage 7's tail, after cutover (the operator, 2026-10-15), each with its reason:**
  - C450 and P7-08b, large-fleet Devices and Coverage (summary, groups, filter; `EXCUSED` 4):
    large-fleet scale, consistent with D3's 7.10; C704 (sortable columns) with them, since it
    builds on C450's board.
  - C472, live regions keeping state through another person's write: multi-user, after cutover.
  - C7, frozen settings defaults; C338 (390 px findings), C337 (the manual's gaps), C183 (notices
    that stop), C179 (subsets said): refinements of screens that already work.
  - P7-30, the designed v2 error page: the plain error answer serves until then.
  - C861, the batch deploy's "Back to Coverage" from every start: wording, leads nowhere wrong.
  - C870 (keys no interface ever drew; three missing icons) and C871 (the walk's lab lacks a
    break-glass record and a window): never drawn on today's pages either, or harness.
  - C877, the device Overview computing its hardware twice: a fixed waste, not per device.
  - C879, P7-04's upstream check comparing names: a check's blind spot, the case it missed
    anchored.
  - **From W1 (the operator's sequence, 2026-10-16: C and R after cutover unless they share an
    A or B fix):** C887 (queue wait in the stepper), C889 (Compare and abbreviations), C890
    (a 0.41 s read; UNKNOWN), C891, C892 (readers during and after a rotation), C893 (raw
    exceptions), C894 (Recent changes live), C895, C896, C897 (UNKNOWN), C898 (History's
    words and rows), C899 (Devices' footer), C900 (reveals' reasons), C901 (W1's copy and
    fidelity notes), C902 to C904 (R1 to R3), C907 (Fields mode). C888 and C905 go with C882,
    before cutover.
  - **From W2 (2026-10-17; the operator's severities, C after cutover unless they share an A or
    B fix):** host keys, devices and topology: C1031 (the startup check's "Who"), C1032
    ("Answering since" resets), C1033 (Trace already running; C1023's population), C1034 (the
    Path… popover), C1035 ("Apart on purpose" empty); C208 and C901 seen again. NetBox: C1036
    (the preview's values), C1037 (about 600 requests), C1038 (two operations at once), C1039
    (r6's mask), C1040 (Left alone), C1041 (a no-op plan), C1042, C1043 (layout); C759 and C133
    seen again. History and Query: C1044 (question-first), C1045 (Show), C1046 (the Kind
    select), C1047 (the diff box); C534 (known noise on Syslog by device) and C895 seen again.
    Settings: C1048 to C1056 (the refused card, "unset", keys and labels, the settle windows'
    JSON, back to inherited, the scope bar's label, the inventory source's fields, Connect's
    cleared fields). Devices and Needs attention: C1057 to C1059. Templates and intent: C1060
    to C1065 (C1065, a put-back read as changed, beside C977); C938 confirmed twice. Reload:
    C1066 to C1069. Findability (P7-07): C1070 (nine longer paths), C1071 to C1073 (not
    found).
  - C939 (NETCONF's undecrypted password, dormant), ~~C941~~ (closed: W2 measured a C8000v
    keeping its key across a reload), C942 (the re-key card's board).
  - C937 (UNKNOWN), C938 (W2's wording; two confirmed in W2). C932 moved to section 2 as W2's B9.
  - C922 (UNKNOWN, an answer set aside mid-drag), C924 (UNKNOWN, the partial operation's row
    beside a usable baseline), C925 (Persist's read on each draw), C926 (a raw exception).
  - C921 (UNKNOWN): "Partly done" over 2 of 2 deployed with no verify result; C920 and C851
    go with P.12 (D3).
  - C914 to C919: W1's fidelity records' defects (the drill card's redraw, capture's stamp, a
    file path on the Overview, raw operands, the phone menu, the tagged regions).
  - C876 (the manifest's name lookup, measured), C912 (Coverage Apply's preview reads per
    device, with C450), C908 to C911 (Needs attention's edges found fixing C543).
  - C872 (the scope bar and `settings`): the scope bar's edge; choosing and deleting work.
    C873 and C874 moved to section 2 with C1022 (W2's A1 measured them).
  - The board comparisons of screens no walk touches (C650's remainder).
  - D3's plan items: 7.10, P.12 (with C322, heartbeat and ip_sla), P.7, P.8 step 9, P.9, P.11
    step 3, P.15's rest.
- **Phase 2 (revert by reload):** C325, C334, C484, C563, C564, C618, C562.
- **Phase 3 leftovers:** C329, C333, C586.
- **Phase 4 records (E18):** C156, C159, C237, C360, C361, C364, C365, C368.
- **NetBox Phase 1, after cutover:** C556, C559, C552, C208, C186, C139, C216, C483, C469.
- **Phase 8 / Stage 8:** C60, E6, C623, C575, C750, C764, C759.
- **After Phase 7 (design or parked):** C733, C762, C561, C531, C551, C554, C196.
- **Stage 9, security** (D4): B9, B10, C144, C145, C161, C162, C211, C230, C248, C355, C407,
  C590, C438, C432, C455, C457, E3, E5, C745, C749, C753, C454, C404, C405, C406.
- **Stage 9, functional or minor:** C6, C13, C40, C41, C44, C45, C47, C71, C72, C113, C202,
  C220, C235, C238, C241, C322, C328, C336, C339, C348, C366, C367, C376, C427, C447, C448,
  C473, C488, C490, C499, C506, C517, C526, C530, C545, C697, C794, C812, C814, C816, C828,
  C829, C830, C831, C846, C847, C848, C849, C851, C853, C854, C856, C858, C859; the Assure
  proposals C799 to C801, C803 to C806.
- **The 2026-10-07 "Now" rows that are not cutover needs** (D5): C603, C589, C596, C582, C665;
  measurements C581, C597, C677, C627; harness C567, C592, C599, C641.
- **Harness and measurement only:** C546, C480, C206, C528, C782, C802, C810, C822, C843, C845,
  C763, C863, C865.
- **Mutation (parked):** C781, C842, C792, C834, C844, C796, C864, C866. The freshness rule
  (the last mutation commit) landed 2026-10-15; no nights run until the operator says Phase 7
  has settled.
- **Lab tooling:** C93, C94, C218, C301, C518, C523, C525, C534, C535, C671, C673, C695, C703,
  E2, C451.
- **The Scheduled section's 7.x rows, read once (P7-16's rest, 2026-10-16):**
  - Closed already: C14, C164, C102, C105, D10, C2, C171, C88; C178 in effect (C117's proof,
    efe09b2). Each one's row is moved to Closed when it is next touched.
  - Close with a v1 removal in section 2: C140 (2), C181 and E1 with P7-21; C461 and D1 with
    P7-25; C33 with P7-23 or P7-27.
  - Needed for cutover: C106's item (3), Retire clearing the override before its commit:
    C981, measured the same night and closed (deliberate). The rest of C106 is Stage 9's.
  - Out: C58 (Stage 7's tail, with C472); C25 (Stage 9, or D3's 7.10); A2, A4, C133, C150
    (NetBox Phase 1); A3 (D3's 7.10, waiting on C100); C212 (Lab tooling).

## Checked off

- **D1 to D6 decided** (the operator, 2026-10-15).
- **P7-16, first part** (a06c06ed): CUTOVER's stale AI row; the plan's status rows 1, 2, 4, 5;
  C616, C620, C626, C576 closed as moot and C48 with C616; C721 closed as built.
- **P7-03 done; P7-06's test done** (46c6224e): all nine concepts drawn from v2 (PENDING 5 → 0);
  tests/test_v2_one_confirm.py (30 routes in the one pattern, 19 today's with a v2 home);
  criterion 6 itself waits on C850. C852 (NetBox's Remove preview) fixed on the way.
- **P7-19 and P7-08a done** (d0c88463): the checks that rendered today's pages read v2 through one
  helper (tests/interface_pages.py, 119 v2 pages); failed navigations answered by v2; dead code
  removed; `ON_TODAYS_APP` empty; tests/test_scale.py measures v2 at 9 and 900 devices. C857 (four
  v2 sentences sending to today's pages) fixed with a guard; C855 found.
- **Section 1c re-checked against the host** (2026-10-15): C722, C725 and the three "It is done"
  steps done and removed.
- **W1's script written** (docs/walks/W1.md, with docs/walks/README.md): 45 steps in 12
  sections, targets s1's and s2's uncabled Gi0/1 (a description and its Mode B removal) and r6
  (the reload); nothing configured on s3 (Save All's `write memory` reaches it, flagged at step
  37). Found while writing it: C860 (into section 2) and C861 (the tail).
- **C836 closed** (5 of 5 clean restarts; the fifth d0c88463's deploy, 23:19:27 UTC). The host
  runs d0c88463, W1's release.
- **C730 done** (D6, the security item): every golden reaches MinIO masked, through one write
  that cannot be called unmasked. The pre-C730 plaintext versions stay (Mercury's key cannot
  delete; deleting is the operator's), counted by the read-only census
  `scripts/host-steps/c730-golden-archive-census.sh` after the release is deployed. C862 opened
  (UNKNOWN: whether the key reads older versions; the census settles it).
- **P7-04 done** (criterion 4 on v2): tests/test_v2_context_is_drawn.py records each v2 route's
  render context on a real walk (120 pages, 927 fragments, four providers) and parses what its
  templates read: 117 routes, 3,119 keys; `UNDRAWN` 357 each reasoned (17 GAP), `UPSTREAM` 16
  (the deploy card's adapter), `UNREACHED` 23. Found: C867 (A), C868, C869 (B), into this
  section; C870, C871 (C), the tail.
- **P7-05 done** (criterion 5 met): `NOT_YET_SUBSCRIBED` 4 → 0. `lists` and `active_list`
  heard by the network picker and Settings' scope bar, `posture` by Installation's Access card,
  `breakglass` by the break-glass record card. **P7-07's test done**: the sidebar's order
  pinned, and nothing but its items and headings; the 37 questions go into W2.
- **C855 done** (to 19 calls per device, from 460; the Devices list 1,298 → 627): the device
  page reads its one device's measurement and rotation state. The 19 left are the manifest's
  name lookup, C876 (UNKNOWN, into this section). C877 (C) to the tail.
- **C867 done, and C878 with it** (both A): the device deploy card and Devices › Plan a deploy
  draw where each added line comes from before the confirm, through one macro; `UPSTREAM`
  16 → 11. C879 (C) to the tail.
- **C860, C868, C869 done** (A, B, B): v2's Save says when it would repeat the last baseline
  (in words that claim only what it measured); the restore chooser draws each moment's message;
  the profile proposal says what it cross-checked and lists what it did not read. `UNDRAWN`
  362 → 358. Three board deviations logged. C880 (UNKNOWN; today's capture preview, moot at
  P7-27) opened.
- **C954 verified on the host** (deployed e63dbe57ff, 2026-10-16 18:00Z): the Stop tracking
  preview through its real route, for Default: "Deletes nothing in NetBox. Mercury forgets 10
  object(s) it created for Default …", "Deletes in NetBox 0", where the data survives; no
  confirm drawn for an unverified caller; nothing confirmed.
- **C954 done** (B, the operator's decision: build it): the Remove card's Stop tracking
  instead…, its own preview (deletes nothing in NetBox; each object forgotten named), confirmed
  by hash holding the network's writer, through today's one forget path given the confirmed
  entries. CUTOVER row 60 true. C1002 (C) to the tail.
- **C991 verified on the host** (deployed c889a844c4, 2026-10-16 17:37Z): the deploy's reader
  answers `clear` against the live service; the updater's copy re-installed (its Host-Step-After)
  and `nmas-update-check` reads ok, matching this release.
- **C948 done** (B, the operator's decision): the Stage 2 checklist rewritten as a dated
  revision, every device read a Mercury read or screen, the planned window and host keys its
  own items, section 2 withdrawn; two lab-host reads kept and labelled. C998 (UNKNOWN), C999 to
  C1001 (C) to the tail.
- **C991 done** (B, the operator's decision): the route's 500 says `holds: "unreadable"`, and
  `nmas-deploy` refuses on that field (exit 10, nothing moved); a service not answering still
  continues. C996 (C) and C997 (UNKNOWN: the gap between the ask and the restart) to the tail.
- **Deployed 1222a3f102 (2026-10-16 17:01Z) and every commit since f208e393 verified on the
  host:** no v2 page answers 5xx; C906 all nine devices' keys kept on first contact, the five
  routers' equal to the night's fingerprints (closed); C931 Default's repository is its own
  top; C487 the drift state is Default's own; C532 nine devices at intent, one state; C705's
  key gone from the schema; C765's module absent; C342 r2's Drift detail draws; C537 the chip
  answers htmx and is absent while idle; C987 three lock folders indexed (C995, C, found:
  `probe-r1` is not its own slug); C988 the holds read, `/health/operations` 200. C881 (A1)
  verified again on r6 with this release: a fresh Reload… preview, no reload sent, passes
  "running against startup" and every gate. C553's unit found installed.
- **C988 done** (B, overnight): only an absent holds store is "nothing held"; any other error
  raises naming the path, and every caller fails closed (Update refused, the wait kept, the list
  delete refused, the chip red, busy treated as held). C991 (B, the operator's decision:
  `nmas-deploy` continues on that 500) into section 2; C992 (C) to the tail.
- **C987 done** (B, overnight): the holds read probes only devices marked in the network's
  `holds/` folder (an empty marker per possible record, one writer each), 7.2 ms to 0.01 ms at
  900 lock files. C988 (B: an unreadable lock folder reads as nothing held) into section 2;
  C989 (measured on the host the same night: C, no interrupted log exists) and C990 (C) to
  the tail.
- **C537 built, D2 met** (overnight, boards A, B, C of canvas v66, self-signed): every v2
  page's In progress chip from `/operations/in_flight`, live; finished results until opened,
  per person; the device page reopens a running or unopened card, and a freed Rotate card shows
  its result. C540 and C217 closed with it. C537 stays open for the command box (Ctrl-K),
  results across a restart, and the operations that are not jobs: the tail. C987 (the chip's
  cost) measured the same night: it grows with every lock file ever made, so B, into section 2.
- **C342 done** (overnight, board C342Drift drawn and signed off under the mode, canvas v134):
  the Drift row opens in place onto the kept lines (masked), the device's own log since its
  golden, and Capture / Plan a deploy… / Remove lines (Mode B)…. C986 (fixed with it: unreadable
  drawn as no run); C983, C984, C985 (C) to the tail.
- **C981 closed** (overnight): the break-glass export does not hold an override, but the
  override must go before the commit (the manifest's release refuses while it references the
  device); a failed commit finishes on a rerun. A test pins the order.
- **P7-16's rest done** (overnight): C705's key retired the schema's way (no bump; the host's
  empty value kept, read by nothing); C765 measured dead by a parsed call graph and
  `configure.py` removed, the pipeline refusing a context with no confirmed list; C176 closed as
  built. The 7.x rows placed (section 4). C978 to C980 (C) and C981 (UNKNOWN, into section 2).
- **C532 done** (overnight): one function, `device_list.intent_state`, draws the Devices list's
  intent chip and the device page's Intent state row from one bounded read, so the two agree;
  intent changed since the last measurement is its own state, never green. C974, C975 (C, fixed
  with it); C976 (C, later: a header chip) and C977 (UNKNOWN: a template edit moves every
  device) to the tail.
- **C487, C493 done** (overnight): a network's store never adopts another's (one helper,
  `network_store`; the survey found drift state and the approval queue WRITING into the wrong
  network); every Needs attention row names its device's network. C972 (C), C973 (UNKNOWN; measured on
  the host the same night: C, no restart covered by another network's window).
- **C963, C964 done** (B, overnight): the heartbeat rules measure the syslog job and refuse
  without one; the device dashboard's job is a variable and its platforms a join, and the app
  carries a variable's declared All value. C969 (UNKNOWN), C970, C971 (C) to the tail.
- **C957, C820, C821 done** (B, overnight): the timeline says "No repository yet" by the one
  `.git` test; the syslog job is measured from Loki, not named in code (the lab-specifics scan
  widened); a plain-text integration refusal reaches the person masked. C963, C964 (B) into
  this section; C965 to C968 (C) to the tail.
- **C522 done** (overnight): every v2 card says "How does this work?" in words once;
  `C503_KNOWN_GAPS` 8 → 0. C962 (UNKNOWN) to the tail.
- **C940, C955 done** (B, overnight): Retire and Abandon forget the address's SSH host key
  (recorded; kept when another device holds the address); Retire's preview counts live
  approvals only, and the listing that counted tombstones is removed. C958, C959 (UNKNOWN),
  C960 (C) to the tail.
- **P7-09 done** (fc70b56e): 11 writeup entries backfilled from the record; 7.3 and 7.D stay
  open (Reload in W2; adopt, revert, retry in W3; 20 screens unchecked; C342's mockup, drawn
  and built 2026-10-16).
- **C944, C945 done** (B, overnight): the unused second `git init` removed; History's header
  says "No repository yet" by the folder, not git's words. C957 (B) into this section.
- **C933 to C936 done** (B, overnight 2026-10-16): NetBox counts each network from its own
  source; the write probe draws its remedy; the removal preview names only v2's choices; a
  revoked template's edit keeps its revocation. C954 (a decision), C955 (B), C956 (UNKNOWN).
- **C953 (CI #850) fixed forward**: a served page's request no longer outlives its test.
- **C931 done (A), with C943**: a network is born with its repository, and every git call on a
  network's repository is pinned to it, never climbing to the app checkout (measured on the
  host: nothing ever landed there). C944, C945 (B) into this section; C946 (C) to the tail.
- **C923 done, with C930** (Adopt's card draws what startup gains and loses through Persist's
  one drawing; its sentence names the monitoring profile's lines the save makes permanent).
- **C883, C888, C905 done** (B2: the "running" note hidden by a CSS rule that overrode
  `hidden`, fixed globally; C2: the rollout order moves in the page and the confirm route binds
  it, refusing any order that is not exactly the confirmed devices; R4: drag and drop on C882's
  guard). C928, C929 (C) to the tail.
- **C884, C885, C886, C913 done** (B3: a deletion-only edit's card says how the device departs,
  Mode B first; B4: a partial operation's baseline row names the commit and offers Save All;
  B5: Persist's preview lists what startup gains and loses, from Reload's comparison; Adopt's
  preview uses it too). C923 (B) into this section; C924 (UNKNOWN), C925, C926 (C) to the
  tail; C927 (A) fixed.
- **C882 (B1) done**: the drag's jump measured in a real browser (a redraw replaced the map
  under the pointer, and the drop saved the detached map's place); a shared guard holds a
  dragged region from every swap until release, and a drop more than one grid step from the
  pointer is refused. C922 (UNKNOWN) to the tail. The operator's re-check is W2's (C691).
- **C881 (A1) done and verified on r6** (4e670a36, 2026-10-16 02:10Z): a fresh Reload…
  preview, no reload sent, passes "running against startup" ("startup keeps r6's 2
  certificates as files in nvram: (both present), running shows them inline") and every gate;
  s1 (vIOS) passes too. r6's reload goes into W2.
- **C850 done** (criterion 6: Update's two and the batch Apply's confirm in the one pattern;
  `SECOND_IMPLEMENTATIONS` 4 → 1, IP SLA's with P.12). C920 (C) with P.12; C921 (UNKNOWN) to
  the tail.
- **C650 for W1 done**: twelve screens recorded from the boards, the operator's W1 captures and
  the board shots (landing, Devices, bulk intent, the device page and its Ask, History, Intent
  and Overview tabs, Show commands and its run, History, Credentials); `UNCHECKED` 32 → 20;
  121 deviation lines in STANDING_APPROVAL_LOG; C914 to C919 (C) to the tail.
- **C543, C544 done** (Needs attention's actions follow the outcome: an unsaved deploy offers
  Persist and clears on a save read back after it; a rollback offers Revert and Retry on v2).
  **C876 measured** and resolved to C (the tail), with C908 to C912 (C) to the tail.
- **W1 walked by the operator** (2026-10-16, 23:20Z to 01:12Z): C588, C547, C587, C444, C539
  closed; CUTOVER rows 42, 44, 45, 46, 53, 54, 69 walked; section I (row 68) and C691 into W2.
  27 findings registered (C881 to C907), sequenced above: C881 first, then C882 to C886 with
  C888 and C905, and C906 (security); the rest to the tail. **The host moved under the walk:**
  it began on ad769e08, and the agent deployed three times during it (dc3a051f at 23:54Z,
  cb2864ce at 00:28Z, d2d5778a at 00:41Z), each a restart with nothing in flight. The agent's
  deploy helper now refuses during a sitting and within 30 minutes of a person's operation.
- **W2 walked by the operator** (2026-10-16 21:12Z to 2026-10-17 00:22Z, against ae8175bdbc;
  evidence in the operator's report folder, `W2-2026-10-16/`): CUTOVER rows
  49, 50, 56, 57, 61, 62, 68 and 70 walked; C691, C667 and C941 closed (C941 measured: r6, a
  C8000v, kept its SSH host key across the reload); C881 by the operator's eyes, C882, C884,
  C931, C811 and W1's B1 to B5 confirmed; P7-07's 37 questions walked; C1010's backfill
  confirmed by the import. Rows 48 and 60 walked and held open by C1024, C1023 and C932. 52
  findings registered (A1 C1022; B1 to B8 C1023 to C1030; B9 is C932, raised; C1031 to C1073),
  sequenced above: C1022 first, then the Bs; the Cs to the tail.
- **W2's A1 and B1 to B9 fixed** (2026-10-17: ed75c7ec, 202ecb26, 977006fa, b9fe9c42, 24bf6922,
  cef98d32), deployed and walked in W3. C1089 measured (fecab2f7, the token writes as Editor);
  the reload's failure path never green (fecab2f7).
- **W3 walked by the operator** (2026-10-17 05:16 to 06:18 UTC, against fecab2f79e; evidence in
  `W3-2026-10-17/`): A1 and B1 to B9 walked on the host; CUTOVER rows 48 and 60 closed; C1018,
  C677 and C1108 closed; one B, C1109 (the settle period), fixed in 5c181256 and deployed; C1110
  to C1120 registered, the Cs to the tail.
- **Overnight, 2026-10-17:** W4's script (6ce34f13) with C1121 (B, DHCP's confirm) fixed; P7-20
  removed (f764fafd, tag `pre-remove/v1-netbox`, walked by GETs on the host: 10 paths as
  expected) with C1123 (B) fixed; C650's W1 to W3 records (5e1413d0, UNCHECKED 20 to 15);
  P7-09's entries (96c0b719).
