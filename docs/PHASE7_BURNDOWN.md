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
| W2 Templates, NetBox, networks, remote | Templates approve, edit, bindings and seed (s2.7); NetBox (s2.10); networks new and delete (s2.9); Remote push, verify, set-up and auto-push (s2.11); inventory source; topology page; saved views (C667); the settings Save (C811); the 37 findability questions, clicks counted (P7-07; docs/NSOT_GUI_BRIEF.md 2.3's H column and 16); **from W1: r6's Reload (section I, CUTOVER row 68) and a C691 drag re-check** | CUTOVER rows 48 to 50, 56, 57, 60 to 62, 68, 70; C667, C691; their screens' records; unblocks P7-20, P7-21, P7-23, P7-26 | after C881 (verified on r6) and C882 are deployed; the script written then |
| W3 Onboarding and recovery | onboard a throwaway on v2 (s5) through deploy, break, roll back (C148); adopt's first real run (board G); revert and retry (row 52 reconciled with THROWAWAY's 2026-10-05/06 runs) | CUTOVER rows 52, 58, 59; C148; their screens' records; unblocks P7-24, P7-25 | after W2 |
| (in any sitting) | ~~C539, C587, C588~~ (walked in W1); snap-to-grid (C691, into W2 after C882); DHCP confirms (C529) | those rows | W2 |

### 1c. Host steps and small acts (re-checked against the host's Update data, 2026-10-15)

Done and removed: C722 (the Loki `device` label, checked done), C725 (the config repository's
pipeline, said done by the operator), and the three steps without a check (the loki-writer
rotation, the ai-leftovers delete, the Backups archive and delete, said done by the operator).

| Item | Op | State |
|---|---|---|
| C794: Loki's own `detected_level` off (scripts/host-steps/c794-loki-detected-level-off.sh) | H | owed on the Update page; the operator's to run (their request) |
| C553: `clab-sync.path` on the lab host | H | not installed (read 2026-10-15); the agent may run it under the mode |
| C549 (3): the Update confirm, in the root-owned updater | H | waits on the operator's reading of what the page drew (the row) |
| C663: move `scripts/nmas-host` | CLAUDE.md paste | the operator's file |
| C296: batch preview empty bullets | — | recommended: close as not reproduced |

## 2. The agent's items, in order (independent ones in parallel)

| ID | Item | Done means | Size | Deps | Op |
|---|---|---|---|---|---|
| **From W1, first (the operator's sequence, 2026-10-16)** | | | | | |
| ~~C881~~ | ~~A1: Reload's startup gate on IOS-XE~~ **done, verified on r6** (see Checked off) | | | | |
| ~~C882~~ | ~~B1: Topology drag jumps~~ **done** (see Checked off); C691 re-checked in W2 | | | | |
| ~~C883, C888, C905~~ | ~~B2, C2 and R4: the batch preview's note, client-side order, drag and drop~~ **done** (see Checked off) | | | | |
| ~~C884, C885, C886, C913~~ | ~~B3, B4, B5 and adopt's comparison~~ **done** (see Checked off) | | | | |
| ~~C923~~ | ~~Adopt's card draws the lines startup gains and loses~~ **done**, with C930 (see Checked off) | | | | |
| **Security** | | | | | |
| ~~C730~~ | ~~the golden archives in MinIO masked (D6)~~ **done** (see Checked off) | | | | |
| C906 | Mercury checks each device's SSH host key (trust on first use, a changed key refused naming both fingerprints, a reviewed re-key operation; NETCONF too) | its tests; walked on a device | M | — | B (the operator's: the re-key's words) |
| **Harness: the checks on v2** | | | | | |
| ~~P7-04~~ | ~~Criterion 4, payloads drawn on v2~~ **done** (see Checked off); its gaps are C867 to C869 below | | | | |
| ~~P7-05~~ | ~~Criterion 5, invalidation~~ **done** (see Checked off) | | | | |
| P7-07 | Criterion 10, the sidebar: ~~an order test~~ (done); the 37 findability questions walked | the walk, in W2 | walk | W1 | W |
| **v2 gaps cutover needs** | | | | | |
| ~~C855~~ | ~~criterion 11: the v2 device page's per-device work~~ **done** to 19 (see Checked off) | | | | |
| ~~C876~~ | ~~the manifest's name lookup~~ **measured**: quadratic but 0.43 s at 900 devices inside requests whose per-device git reads cost more (C912); resolved to C, moved to the tail | | | | |
| ~~C850~~ | ~~criterion 6: the Alpine confirm components to the one pattern~~ **done**, 4 → 1 (IP SLA's with P.12, D3) (see Checked off) | | | | |
| C537 | the every-page in-flight indicator (D2), then C540's wording and C217's one row | built from canvas v66; `/operations/in_flight` has a v2 caller | L | — | B (self-signed) |
| ~~C867~~ | ~~v2's deploy card draws the plan's attribution~~ **done**, with C878 (the batch preview's) (see Checked off) | | | | |
| ~~C868, C869, C860~~ | ~~the restore chooser's message; the profile proposal's reads and skips; v2's Save's repeated-baseline warning~~ **done** (see Checked off) | | | | |
| ~~C543, C544~~ | ~~Needs attention's action words~~ **done** (see Checked off) | | | | |
| C487, C493 | Needs attention names each row's network; no reader falls back to a global store | survey and fix; per-row test | M | — | — |
| C532 | Devices list and device page agree on intent state (one comparison) | one function, both drawn from it | M | — | — |
| C342 | the device page's drift: masked diff and three choices | built from its board | M | — | B |
| C522 | the 8 lone (i) cards (`C503_KNOWN_GAPS` 8 → 0) | the browser test's list empty | S–M | — | — |
| C820, C821 | the lab's syslog job in product code; an integration's 4xx reason | discovered job, wider scan; the body's first line masked | S each | — | — |
| P7-09 | Criterion 14, the writeup: entries for 7.4 to 7.8, P.11, Show commands, Ask, Logs, DHCP, Update; 7.3 and 7.D closed | an entry per sub-task, forecasts checked | M | — | — |
| P7-16 (rest) | C705, C765, C176; the Scheduled section's 7.x rows read once | each closed or placed | S | — | — |
| **C650, during the walks** | each walked screen's fidelity record written from its sitting; `UNCHECKED` shrinks by the walked screens; the rest to the tail | records from W1 to W3 | S per screen | the sittings | W |
| **The v1 removals (each tagged first, walked, ceilings lowered, the ratchet run)** | | | | | |
| P7-20 | (4) the NetBox tab and `/netbox/safety/*`, `/netbox/status` | removed, walked | M | W2 | — |
| P7-21 | (5) Git, the Remote card, Baselines | removed, walked | M | W1, W2 | — |
| P7-22 | (7) today's device page (`/device/<ip>`, `/run_command`, `/deploy/receipts`) | removed; run_command's MISSING, HISTORY_MISSING, PENDING entries gone | M | W1 (C547) | — |
| P7-23 | (8a) template and intent editors | removed | M | W2, C444 | — |
| P7-24 | (8b) device-action JSON (capture, seed, revert, retry, profile, persist, rotate, retire) | removed | M | W3, P7-22 | — |
| P7-25 | (8c) deploy wizard, onboarding, inventory source | removed | M–L | W1, W3 | — |
| P7-26 | (8d) networks; the global active list frozen | removed | S | W2 | — |
| P7-27 | (9) the pages: `/` (302 to `/v2/`), `/attention`, `index.html`, `base.html`, the last partials and scripts, vendored Bootstrap; `test_no_new_v1_capability` becomes "nothing outside templates/v2" | criteria 1, 2, 16 close; the v1 ceilings at 0 | M | all above | — |

**Rough total after the trim:** about 3 L (C850's `applyConfirm`, C537, P7-04 at its upper end),
13 M and 14 S of agent work, plus three walk sittings (C650 inside them). The removals run as
their sittings clear. **Recomputed 2026-10-16 after W1:** done since: P7-04, P7-05, P7-07's
test, C730, C855, C860, C867, C868, C869 (about 1 L, 4 M, 5 S); added by W1: C881, C882 with
C888 and C905, C906 (3 M), C883 to C886 (5 S). Left: about 2 L (C850's `applyConfirm`, C537),
12 M and 14 S, plus W2 and W3.

## 3. The shrinking lists (distance to cutover)

| List | Now | At cutover |
|---|---|---|
| tests/test_board_fidelity.py `UNCHECKED` | **20** (W1's twelve recorded 2026-10-16) | the walked screens out; the rest to the tail |
| modules/operation_stages.py `MISSING` / `HISTORY_MISSING` | 17 / 2 | run_command's go with v1; the rest stay until built (not a cutover condition) |
| tests/test_results_are_drawn.py `PENDING` | 8 | 0 (all v1 handlers) |
| tests/test_concepts_are_taught.py `PENDING` | **0** (P7-03) | 0 |
| tests/test_v2_one_confirm.py `SECOND_IMPLEMENTATIONS` | **1** (C850, 2026-10-16) | 1, IP SLA's `ipslaPost` with P.12 (D3); 0 after |
| tests/test_invalidation_map.py `NOT_YET_SUBSCRIBED` | **0** (P7-05, 2026-10-16) | 0 |
| tests/test_v2_layout_in_a_browser.py `C503_KNOWN_GAPS` | 8 | 0 (C522) |
| tests/test_no_new_v1_capability.py controls / handlers / functions / fields | 43 / 31 / 333 / 20 | 0 (P7-27) |
| tests/test_payload_is_rendered.py `UNDRAWN` / `PHANTOM` / `EMPTY` | 93 / 14 / 31 (v1 routes) | 0 at P7-27 (the v1 check goes with today's pages) |
| tests/test_v2_context_is_drawn.py `UNDRAWN` (GAP) / `UPSTREAM` / `UNREACHED` | **358** (C868, C869's GAP gone) / **11** (C867) / 23 (2026-10-16) | met: the GAP entries cutover needs gone; `UPSTREAM` 11; the rest reasoned or the tail's |
| tests/signed_off_screens.py `UNSIGNED` | 3 | 1 (not_found stays; heartbeat and ip_sla go with P.12, D3) |
| modules/manual.py `ON_TODAYS_APP` | **0** (P7-19) | 0 |
| tests/test_route_reachability.py `KNOWN_UNREACHABLE` / `NON_GUI` | 0 / 8 | 0 / 8 (D1 keeps two) |
| Moved to the tail: tests/test_large_fleets.py `EXCUSED` 4 (C450); tests/todays_page_links.py `OTHER_GAPS` 1 (P7-30) | | after cutover |

## 4. Out of Phase 7 (declared, not a backlog)

These open rows do not block cutover; each has its home. A new finding joins this list unless it
blocks cutover or is a security issue (B).

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
  - C922 (UNKNOWN, an answer set aside mid-drag), C924 (UNKNOWN, the partial operation's row
    beside a usable baseline), C925 (Persist's read on each draw), C926 (a raw exception).
  - C921 (UNKNOWN): "Partly done" over 2 of 2 deployed with no verify result; C920 and C851
    go with P.12 (D3).
  - C914 to C919: W1's fidelity records' defects (the drill card's redraw, capture's stamp, a
    file path on the Overview, raw operands, the phone menu, the tagged regions).
  - C876 (the manifest's name lookup, measured), C912 (Coverage Apply's preview reads per
    device, with C450), C908 to C911 (Needs attention's edges found fixing C543).
  - C872 (the scope bar and `settings`), C873 (the top bar after a delete), C874 (the picker's
    mark; UNKNOWN): the network picker and scope bar's edges; choosing and deleting work.
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
- **The Scheduled section's 7.x rows** not named above (C14, C58, C140, C164, C102, C105, C106,
  C178, C25, C461, D1, C181, D10, E1, A2, A4, C2, C133, C150, C171, C212, A3, C33, C88): each is
  read once in P7-16's rest; one that a cutover item needs moves into section 2, the rest out.

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
