# Phase 7 burn-down: every item between today and cutover

**The operator, 2026-10-15 ("Phase 7 first").** Cutover is the retirement of today's (v1) pages
(docs/CUTOVER.md) with Stage 7's acceptance criteria met (docs/NSOT_STAGE7_PLAN.md section 10).
Built from two read-only surveys at fcd1e4f6 (the plans, CUTOVER and the v1 families; the
register and the tests' shrinking lists), 2026-10-15. Each report from now on shows this list
with items checked off. Mutation testing is parked (docs/TESTING.md); Lab 7 is down to its fact
sheet.

**Where it stands.** CUTOVER.md's own rule (no PLANNED, PARTLY BUILT or UNDECIDED row) already
holds: what blocks removal is walks, decisions, harnesses that still measure v1, and a few v2
gaps. Four v1 families are gone today (the sixteen unreachable routes, bulk commands, the Drift
tab, the Settings modal with Logs and the status bar). Left: `templates/index.html` (Devices,
NetBox, Git tabs), `templates/device.html` (Utilities, Changes, 8 actions), `base.html`, 14
partials, 13 `static/js/gen` files.

Sizes: **S** under a day of agent work, **M** one to three days, **L** more. **Op** = needs the
operator (W walk, D decision, H host step, B board; boards are self-signed under the Phase 7
mode, so B means only that a board is drawn first).

## 1. The operator's items, batched (first)

### 1a. Decisions (one sitting)

| # | Decision | Recommended |
|---|---|---|
| D1 | `/identity/status` and `/settings/integrations/status`: the survey recommended removing them (accepted 2026-10-15), but they were kept as diagnostics (docs/LESSONS.md names the first; docs/DEPLOY_LINUX.md's Verify reads the second) | keep both, declared NON_GUI, out of the cutover count |
| D2 | C537: the every-page in-flight indicator (today's `base.html` panel is the only one) | build it on v2 from canvas v66 before `/` goes (it is the only signal a long job is running) |
| D3 | Stage 7's plan items that do NOT gate CUTOVER's rule: 7.10 (A3 at scale, the 900-device screens, the inventory-source switch), P.12 monitoring templates (C322, replaces `heartbeat.html` and `ip_sla.html`), P.7, P.8 step 9, P.9, P.11 step 3, P.15's rest | out of the cutover line: after cutover, as Stage 7's tail, except where a cutover item needs one |
| D4 | The Stage 9 security rows already scheduled (B9, B10, C144, C145, C161, C162, C211, C230, C248, C355, C407, C590, C438, C432, C455, C457, E3, E5, C745, C749, C753, C454, C404 to C406): the reset says a security issue (B) is fixed inside Phase 7 | leave them in Stage 9 as scheduled; pull one in only if a cutover change touches it |
| D6 | C730: the golden archives in MinIO hold each device's SNMP communities and type-9 hashes verbatim (the `s3-archive` hook copies committed goldens; the row says "an exposure to judge with the operator") | archive goldens masked, as every outbound path is; inside Phase 7 as a security item (S–M) |
| D5 | The "Now" rows from the 2026-10-07 triage that are v2 improvements, not cutover needs (C603, C589, C596, C582, C665) and the measurement and harness rows (C581, C597, C677, C627, C567, C592, C599, C641) | out of Phase 7 (section 4) |

### 1b. Walks (two or three sittings, the confirm-gated ones need a verified person)

The agent runs device operations under the mode, but a confirm by hash needs the operator's
Access session, so each of these is a sitting with the operator's browser. Batched by sitting
(docs/THROWAWAY_SESSION.md's numbering where it exists):

| Sitting | Walks | Clears |
|---|---|---|
| W1 Devices and device | a several-device deploy (s3.2); Re-apply (s3.4); bulk intent (s3.3); a golden reveal (s2.6); the Ask tab reading a device (C547); Capture's shrink reason (s2.5); Reload on r6 (s4); intent edit on v2 (C444, THROWAWAY Part 5) | CUTOVER rows 42, 44 to 46, 53, 54, 68, 69; C547, C444; unblocks P7-22, P7-24 |
| W2 Templates, NetBox, networks, remote | Templates approve, edit, bindings and seed (s2.7); NetBox (s2.10); networks new and delete (s2.9); Remote push, verify, set-up and auto-push (s2.11); inventory source; topology page; saved views save, pin, remove (C667); the settings Save (C811) | CUTOVER rows 48 to 50, 56, 57, 60 to 62, 70; C667; unblocks P7-20, P7-21, P7-23, P7-26 |
| W3 Onboarding and recovery | onboard a throwaway on v2 (s5) through deploy, break, roll back (C148's loop); adopt's first real run (board G); revert and retry (reconcile row 52 against THROWAWAY's 2026-10-05/06 runs) | CUTOVER rows 52, 58, 59; C148; unblocks P7-24, P7-25 |
| (any) | Needs attention clears at once after a Save All or rotation (C539); the logging-path test at the trap level (C587); Ask's label (C588); snap-to-grid (C691); DHCP confirms (C529) | C539, C587, C588, C691, C529 |

### 1c. Host steps and small acts

| Item | Op | Note |
|---|---|---|
| C549 (3): the Update confirm, in the root-owned updater | H | agent may run it under the mode; yours if you prefer |
| C722 (Loki `device` label), C553 (`clab-sync.path`) | H | agent may run them under the mode |
| C725: the config repository's pipeline | H + a token | the token is yours (a secret) |
| C663: move `scripts/nmas-host` | CLAUDE.md paste | your file |
| Update page: "It is done" for three host steps | click | yours |
| C296: batch preview empty bullets | screenshot or "not reproduced" | recommended: close as not reproduced |

## 2. The agent's items, in order (independent ones in parallel)

| ID | Item | Done means | Size | Deps | Op |
|---|---|---|---|---|---|
| **Harness: the checks move to v2 (they still measure today's pages)** | | | | | |
| P7-19 | Tests that render `/` or `/device/` move to v2 (route_references, test_blueprint_reachability, test_no_unreachable_ui, test_controls_do_something, test_tab_descriptions_are_true, test_cache_policy, test_csp, test_scale); app.py's HTML failure redirect to `index`; dead `_ping_host`, `_run_subnet_discovery`; `ON_TODAYS_APP` (logs, dhcp) emptied | each test reads v2; nothing references `index` | M | — | — |
| P7-03 | Criterion 3, the nine concepts drawn from v2 (`data-concept` in templates/v2; LIVE 4 now from v1 JS, PENDING 5) | tests/test_concepts_are_taught.py draws all nine from v2, its control fails | M | — | — |
| P7-04 | Criterion 4, payloads drawn: extend the check to v2's render context (UNDRAWN 93, PHANTOM 14, EMPTY 32 are v1 routes) | the check reads v2; the lists shrink to v2's real gaps | M–L | — | — |
| P7-06 | Criterion 6, one pattern: a v2 test that every preview and confirm draws one way (6 `confirm()` calls left are v1) | the test exists, reads v2, control fails | M | — | — |
| P7-05 | Criterion 5, invalidation: `NOT_YET_SUBSCRIBED` (active_list, lists, posture, breakglass) to 0 | each key has a v2 subscriber | S–M | P7-26 for `lists` | — |
| P7-07 | Criterion 10, the sidebar: an order test; the 37 findability questions walked | the test; the walk recorded | S + walk | — | W (first-click) |
| P7-08a | Criterion 11: tests/test_scale.py ported from `/` to v2 | it measures v2's pages | M | — | — |
| **v2 gaps cutover needs** | | | | | |
| C650 | Every built screen compared with its board: `UNCHECKED` 32 → 0 (devices, device and tabs, templates, netbox, pending, reapply, settings, history, credentials, apply, save, bulk_intent, …) | a docs/fidelity record each, deviations logged | L (32 × S) | — | — |
| C537 | the every-page in-flight indicator (D2), then C540's wording and C217's one row | built from canvas v66; `/operations/in_flight` has a v2 caller | L | D2 | B (self-signed) |
| C450, P7-08b | Devices and Coverage: summary, groups, filter (`EXCUSED` 4 → 0); then C704's server-side sort | the large-fleets test's EXCUSED empty | L, then M | the revised Devices board (15.1 B) | B |
| C472 | the remaining live regions keep state through another person's write (History diffs, remote Push/Verify) | each region's test | M | — | — |
| C855 | criterion 11: the v2 device page's per-device work (every device's last measurement read, a regex compiled per device) | test_scale's device-page calls-per-device pin at 0 per device | S–M | — | — |
| C850 | criterion 6 on v2: the four Alpine confirm components converted to the one pattern (`SECOND_IMPLEMENTATIONS` 4 → 0) | the one-confirm test's list empty | L (`applyConfirm`) + S–M | IP SLA's with P.12 (D3) | — |
| C543, C544 | Needs attention's action words (Persist; Revert and Retry) | the rows' tests | S | — | — |
| C487, C493 | Needs attention names each row's network; no reader falls back to a global store | survey and fix; per-row test | M | — | — |
| C532 | Devices list and device page agree on intent state (one comparison) | one function, both drawn from it | M | — | — |
| C342 | the device page's drift: masked diff and three choices | built from its board | M | — | B |
| C522 | the 8 lone (i) cards (`C503_KNOWN_GAPS` 8 → 0) | the browser test's list empty | S–M | — | — |
| C338, C337, C183, C179 | 390 px findings; the manual's gaps; notices that stop; subsets said | each named gap fixed | M | C450 for C338 | — |
| C7 | frozen settings defaults classified (current, frozen, chosen) | the classifier and its test | M | — | — |
| C820, C821 | the lab's syslog job in product code; an integration's 4xx reason | discovered job, wider scan; the body's first line masked | S each | — | — |
| C730 | the golden archives in MinIO masked (D6) | archived objects carry no secret value; a planted community is masked in the archive | S–M | D6 | — |
| P7-30 | boards owed: a designed v2 error page (CUTOVER:425) | drawn, built, `OTHER_GAPS` 1 → 0 | M | — | B |
| P7-09 | Criterion 14, the writeup: entries for 7.4 to 7.8, P.11, Show commands, Ask, Logs, DHCP, Update; 7.3 and 7.D closed | an entry per sub-task, forecasts checked | M | — | — |
| P7-16 | doc hygiene: CUTOVER's stale AI row; the plan's stale criteria 1 and 5 rows; moot rows closed (C620, C616, C48, C705, C765, C576, C626, C721, C176, D7, D9, C92, C38 per the plan) | rows corrected; register closed with reasons | S | — | — |
| **The v1 removals (each tagged first, walked, ceilings lowered, the ratchet run)** | | | | | |
| P7-20 | (4) the NetBox tab and `/netbox/safety/*`, `/netbox/status` | removed, walked | M | W2 (NetBox) | — |
| P7-21 | (5) Git, the Remote card, Baselines (`/git/*`, `/golden/history`, `/restore*`, `/remote/*` except push and verify) | removed, walked | M | W1, W2 | — |
| P7-22 | (7) today's device page (`/device/<ip>`, `/run_command`, `/deploy/receipts`; rows point at `/v2/device/<name>`) | removed; run_command's MISSING, HISTORY_MISSING, PENDING entries gone | M | W1 (C547), P7-19 | — |
| P7-23 | (8a) template and intent editors (`/templates*`, `/templatize/committed`; vendored CodeMirror) | removed | M | W2, C444, P7-03 | — |
| P7-24 | (8b) device-action JSON (capture, seed, revert, retry, profile, persist, rotate, retire; three route files whole) | removed | M | W3, P7-22 | — |
| P7-25 | (8c) deploy wizard, onboarding, inventory source | removed | M–L | W1, W3, P7-03 | — |
| P7-26 | (8d) networks (`/device_lists`, `/select_device_list`); the global active list frozen | removed | S | W2 | — |
| P7-27 | (9) the pages: `/` (302 to `/v2/`), `/attention`, `index.html`, `base.html`, the last partials and scripts, vendored Bootstrap; `test_no_new_v1_capability` becomes "nothing outside templates/v2"; CUTOVER's "Today's pages" row REMOVED | criteria 1, 2, 16 close; the v1 ceilings at 0 | M | all above | — |
| **Tracking** | | | | | |
| C836 | the readers' import deadlock: 3 of 5 clean restarts | 5 of 5, closed | S | deploys | — |

**Rough total:** about 6 L, 20 M and 12 S of agent work, plus three walk sittings and one decision
sitting. The removals (P7-20 to P7-27) run as their walks clear; the harness items and C650
start now.

## 3. The shrinking lists (distance to cutover)

| List | Now | At cutover |
|---|---|---|
| tests/test_board_fidelity.py `UNCHECKED` | 32 | 0 (C650) |
| modules/operation_stages.py `MISSING` / `HISTORY_MISSING` | 17 / 2 | run_command's go with v1; the rest stay until built (not a cutover condition) |
| tests/test_results_are_drawn.py `PENDING` | 8 | 0 (all v1 handlers) |
| tests/test_concepts_are_taught.py `PENDING` | 5 | 0 (P7-03) |
| tests/test_invalidation_map.py `NOT_YET_SUBSCRIBED` | 4 | 0 (P7-05) |
| tests/test_large_fleets.py `EXCUSED` | 4 | 0 (C450) |
| tests/test_v2_layout_in_a_browser.py `C503_KNOWN_GAPS` | 8 | 0 (C522) |
| tests/test_no_new_v1_capability.py controls / handlers / functions / fields | 43 / 31 / 333 / 20 | 0 (P7-27) |
| tests/test_payload_is_rendered.py `UNDRAWN` / `PHANTOM` / `EMPTY` | 93 / 14 / 32 (v1 routes) | re-based on v2 (P7-04) |
| tests/signed_off_screens.py `UNSIGNED` | 3 | 1 (not_found stays; heartbeat and ip_sla go with P.12, D3) |
| tests/todays_page_links.py `OTHER_GAPS` | 1 | 0 (P7-30) |
| modules/manual.py `ON_TODAYS_APP` | 2 (stale) | 0 (P7-19) |
| tests/test_route_reachability.py `KNOWN_UNREACHABLE` / `NON_GUI` | 0 / 8 | 0 / as D1 decides |

## 4. Out of Phase 7 (declared, not a backlog)

These open rows do not block cutover; they are explicitly after it, each with its home. A new
finding joins this list unless it blocks cutover or is a security issue (B).

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
  C829, C830, C831, C846, C847, C848, C849; the Assure proposals C799 to C801, C803 to C806.
- **The 2026-10-07 "Now" rows that are not cutover needs** (D5): C603, C589, C596, C582, C665;
  measurements C581, C597, C677, C627; harness C567, C592, C599, C641.
- **Harness and measurement only:** C546, C480, C206, C528, C782, C802, C810, C822, C843, C845,
  C763.
- **Mutation (parked):** C781, C842, C792, C834, C844, C796.
- **Lab tooling:** C93, C94, C218, C301, C518, C523, C525, C534, C535, C671, C673, C695, C703,
  E2, C451.
- **The Scheduled section's 7.x rows** not named above (C14, C58, C140, C164, C102, C105, C106,
  C178, C25, C461, D1, C181, D10, E1, A2, A4, C2, C133, C150, C171, C212, A3, C33, C88): each is
  read once during P7-16; one that a cutover item needs moves into section 2, the rest out.

## Checked off

(Each report adds the items finished, with the commit.)

- **P7-16, first part** (this commit): CUTOVER's stale AI chat row marked REMOVED; NSOT_STAGE7_PLAN's
  status rows 1, 2, 4 and 5 re-read to today's measured values; C616, C620, C626 and C576 closed
  as moot and C48 with C616 (each checked against the code), C721 closed as built. Left in
  P7-16: C705 and C765 (not clearly moot: read further), C176 (a read the config hook guards),
  and the Scheduled section's 7.x rows read once.
- **P7-03 done; P7-06's test done** (the next commit): all nine concepts drawn from v2 (PENDING
  5 → 0; four v2 gaps built in place), tests/test_v2_one_confirm.py (30 routes in the one
  pattern, 19 today's with a v2 home); criterion 6 itself waits on C850. C852 (NetBox's Remove
  preview) fixed on the way.
- **P7-19 and P7-08a done** (the next commit): the checks that rendered today's pages read v2
  through one helper (tests/interface_pages.py: 119 v2 pages followed from `/v2/`); app.py's
  failed navigations answered by v2 (no redirect to `index`); dead `_ping_host`,
  `_run_subnet_discovery` removed; `ON_TODAYS_APP` empty; tests/test_scale.py measures v2 at 9
  and 900 devices. The v1-only tests left for each removal commit are named in that commit's
  message. C857 (four v2 sentences sending to today's pages) fixed with a guard; C855 found.
