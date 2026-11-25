# Fidelity: Troubleshooting in the sidebar, and Troubleshooting › Incidents (board T)

**Provisional, operator review pending** (the operator, 2026-11-13: "GUI boards: approved
provisionally for initial implementation and testing (board R, board T the Troubleshooting
sidebar, review items)"). The sidebar's Troubleshooting section and the incidents list as
built, compared region by region with board T
(`~/Documents/nmas-reports/boards/troubleshooting-nav.html`: part 1, the sidebar before and
after; part 2, what each item opens; part 3, where every screen goes; part 4, Incidents › Open
as it would first draw), the GUI review's proposal 17 and finding IN9
(`~/Documents/nmas-reports/gui-review.md`). Compared by the templates against the board's
parts and the pages tests/test_incidents_list_v2.py draws (the incident page's three planted
fixtures together on one network, and 900 incidents), not from board shots: the board is not
on the mockups canvas, so tests/test_board_shots.py has no file for it yet. A shot comparison
at 1440, 1280 and 390 is the operator's review's. The incident page's breadcrumb is compared
in `incident.md`.
Compared 2026-11-13.
Templates compared: templates/v2/incidents.html, templates/v2/_heal_auto_chip.html, templates/v2/base.html, templates/v2/_control_strip.html, templates/v2/_incidents_board.html
Compared again 2026-11-15 (Gate 2, C3748, with board G2,
`~/Documents/nmas-reports/boards/g2-control-strip.html`): the control strip above the tabs,
the top bar's chip opening Needs attention's strip and saying when AI troubleshooting starts by
itself, and a closed incident's "fixed by" drawn by display name (C3715). Compared by the
templates' diff and tests/test_incidents_list_v2.py's and tests/test_heal_batch.py's pages, not
by new shots. Templates sha256 before: `8cd0ac4bce918c2a737dbb069716bb223297755ed6e5f00acf4f39ea5018205e`.

| Region | Board | Built | Verdict |
|---|---|---|---|
| The control strip | board G2 part 1; board T draws none | the strip, for the page's network, above the tabs | **deviation** (log: Incidents: the control strip above the tabs (C3748)) |
| The top bar's chip | board T: Auto alone, opening Settings › Self-healing | Auto or AI on, opening Needs attention's strip | **deviation** (log: The top bar's status chip opens the control strip, and shows the AI toggle (C3748)) |
| A row's AI investigation (Gate 2) | board T draws none | "AI investigating since HH:MM", then its one-line outcome, under the row's device line | **deviation** (log: Incidents' and Needs attention's rows say "AI investigating since HH:MM", then the AI's one-line outcome (Gate 2)) |

Compared again 2026-11-15 (Gate 2, C3769): the strip's AI switch as board G2 part 3 amends it,
and a row's AI investigation line. Compared by the templates' diff and
tests/test_ai_troubleshoot_control.py's pages, not by new shots. Templates sha256 before:
`345e3a9c6172ca187c7ac0e60c0e5545e5aae7fd597a29771e23a5cb9d61d27c`.

Compared again 2026-11-15 (Gate 2's follow-up): the strip no longer opens Turn on…'s form
under its AI switch. Compared by the template's diff. Templates sha256 before:
`89d9cada0ab00fdefc455f6c463d547110d7cb1a08b868e3473ef11504acb1b2`.

Compared again 2026-11-15 (the combined gate's tree): base.html as committed, without the
toolbar assistant's Assistant button and chat panel shell, which are not in this tree (they
land with the assistant's own change, and are no region of this page's board). Compared by the
templates' diff: no region drawn differently. Templates sha256 before (base.html with them):
`22b8b5eb98b52ae5846010c1c771c7b958d08ae15ab6c69ba74e6e35677a4ced`.

Compared again 2026-11-15 (tests/test_v2_layout_in_a_browser.py's help links): the control
strip is a card for its help links, one in words ("How does the Self-healing toggle work?"),
the AI switch's the (i) alone, its padding, gap and corner kept as the strip's
(`.ctl-strip.card`); no region moves. Compared by the template's diff and the browser's
help-link measurement, not by new shots. Templates sha256 before:
`7887822430135b8b536f95de82bff6c7a4aeb2d794fb98659401da2c50ae9b86`.

Compared again 2026-11-15 (the operator's item 2, C3789: "keep it only on Incidents"): the
strip is this page's alone, drawn as compared; its template gains the run part Needs attention
draws (no element of this page moves), its toggle records this page as where it was pressed,
and the top bar's chip opens this page's strip. Compared by the templates' diff and
tests/test_heal_batch.py's and tests/test_incidents_list_v2.py's pages (the chip pressed in a
real browser lands on this page's switch), not by new shots; every region's verdict unchanged
(log: The control strip on Troubleshoot › Incidents alone; Needs attention keeps its run part
(C3789)). The hash below is over the working tree, which also holds the concurrent edit to
base.html (the assistant's chat panel), compared by its own build. Templates sha256 before:
`9319bd3d534aca97b6b2d01e5ed848ef23424b2fe8da9cadacbe8da22081700a`.

**Compared again 2026-11-18 (the skip-mode debt, docs/FAST_LANE_DEBT.md; becced07 to 962b2baf,
fifteen commits; board R5's artboard 2 and the GUI redesign brief's board 4.2):** the page as
board R5 (docs/boards/r5-simple-by-default.html, approved by the operator 2026-11-15 with four
changes) draws it, and the fleet view above R5's list (board 4.2, design/incidents-board.html,
self-signed under the Phase 7 mode 2026-11-18; docs/STANDING_APPROVAL_LOG.md, "The Incidents
page's fleet view"), whose template `_incidents_board.html` joins the compared list (it was in
no record). Also since the last comparison: the strip's Self-healing On may last until someone
turns it off (cd0aa4cc), every switch flips at once and its work runs after (8f1d8006), Fix all
and the batch card are gone (70e89a47, d8614a4d), a row shows the live step while Mercury works
on it (bad52d54, 2f368606), the tabs' counts redraw with the list (8f1d8006), and the top bar's
Auto chip says "until turned off" for an Auto with no expiry (962b2baf). Shots: the debt pass's
own `debt-incidents` at 1920, 1280 and 390 (the heal's lab with tests/test_incident_page.py's
healed and can't-fix incidents) beside `debt-incidents-board` (design/incidents-board.html at
1920, 1280 and 390; the board's own shots are in design/shots/), and R5's file shot whole
(`debt-r5-needs-attention-board`, its screen 2 this page). Templates sha256 before:
`22671d63f0fea528ab83b514243ff0f0acd1adbd5b898275bfe558e31c64f0c2` (without
`_incidents_board.html`).

| Region | Board | Built | Verdict |
|---|---|---|---|
| R5: the page's sub-heading | dropped | dropped | **same** |
| R5: the strip's labels (change 2) | "Self-healing: Off (dry run)" / "On until HH:MM"; "Automatic AI troubleshooting: Off" / "On" | "Self-healing: Off (dry run)", "On" (until turned off) or "On until …" by the clock; "Automatic AI troubleshooting: Off" / "On" | **same** |
| R5: the strip's one line | "While it's off, a person starts the AI. …" | the same sentence, its second part the catch-up line when there is one | **same** |
| R5: the strip's (i) | none beside the switches | the (i) beside each switch | **deviation** (log: R5: How does this work? kept beside each switch and button) |
| R5: the strip's Details | the settings, the three levels, who changed each | each switch's state in words and its settings link | **same** |
| R5: tabs, summary and Search or filter… | tabs, "3 open · 3 warning", one "Search or filter…" link | tabs "Open · N" and "Closed · N" redrawn with the list, "1 open · 1 needs a person", the search and device filter behind the link | **same** |
| R5: the batch card (changes 1 and 4) | as on Needs attention | not drawn: guard 6 holds nothing (9ffa279d), each incident its own row | **deviation** (log: Needs attention: no batch card since guard 6 holds nothing) |
| R5: a row's three lines | badge, title link, impact, status, since | the same; its device and id on the title's hover; while Mercury works on it the status is the live step with its seconds | **same** |
| R5: a row's badge | its severity, "Warning" | its state, "Needs a person", and under it the row's autonomy ("Manual", "Self-heal", "AI + approval", board 4.2) | **deviation** (log: R5: Incidents' rows keep their state badge) |
| R5: a row's words | the board's sample words | Mercury's own tables (a can't-fix's status still names `scripts/nmas-removal-probe`, C3506, open) | **deviation** (log: R5: rows' words are Mercury's own tables, not the board's samples) |
| R5: phone (390) | lines wrap rather than cut | the title is cut with an ellipsis ("edge-b: access list added on GigabitEthernet2 ou…"), whole on hover | **deviation** (log: R5: some of a row's lines are cut at phone width, whole on hover) |
| 4.2: the head | "Incidents", "Default network · live · 17:58:40 UTC", "Self-healing On (since …) · Automatic AI Off" at the right | the heading and its (i); the network in the top bar; the switches in the control strip under the heading, "checked just now" beside the tabs | **deviation** (log: The Incidents page's fleet view: the 30-day outcome strip, category tiles with their trend, and each row's autonomy) |
| 4.2: the category tiles | seven: Interfaces, Config drift, Routing, Telemetry, Reachability, Syslog and alerts, SDN, each its open count, "N opened since Nov 7" and a 30-day line; SDN "needs: SDN detections as incidents" | a tile only for a category the store holds an incident of ("Config drift · 1 open · 0 in 30 days", no line drawn for a window with no detection), and SDN and Telemetry each a "needs: …" tile | **deviation** (log: The Incidents page's fleet view: the 30-day outcome strip, category tiles with their trend, and each row's autonomy) |
| 4.2: the outcome strip | a card: "Nov 11 – now · 63 incidents", "77% of the 56 closed self-healed", then 43 self-healed, 9 AI-fixed, 0 human-fixed, 7 open now, 3 not a fault, 1 closed unfixed | one line: "Last 30 days: 0 self-healed · 0 AI-fixed (approved) · 0 person-fixed · 0 open", those closed without a fix beside them when there are any; no share; "open" counts the incidents detected in the 30 days, so the shot reads "0 open" beside "Open · 1" and the tile's "1 open" (registered by the debt pass: the board's figure is "open now") | **deviation** (log: The Incidents page's fleet view: the 30-day outcome strip, category tiles with their trend, and each row's autonomy) |
| 4.2: the filters | state chips (All open, Detected, Self-healing, Diagnosing, Fix proposed, Needs a person, Closed), a search box, Export CSV | R5's Open and Closed tabs and "Search or filter…"; no state chips, no Export CSV | **later** (the log's "Not built tonight": CSV export; the chips are R5's tabs and groups) |
| 4.2: the table | one sortable table: Device, Issue, Lifecycle, Action, Age, Autonomy, Recurred, grouped by Needs a person and Self-healing now, Closed today folded | R5's grouped rows (Needs a person, Mercury working, watching), each its three lines with the autonomy badge; no Lifecycle, Recurred or sorting | **later** (the log's "Not built tonight": column sorting and "recurred ×N") |
| 4.2: phone (390) | the head, the chips wrapping, the search, Export CSV, each row a stacked card | the strip, the tabs, the outcome line, the tiles two to a row, the summary, the rows | **deviation** (log: The Incidents page's fleet view: the 30-day outcome strip, category tiles with their trend, and each row's autonomy) |
| Fix all and the switch-on batch | board G2 parts 1 and 2: the strip's run on THE stepper | the switch flips at once and answers "Starting N fixes…" in the strip; the run is each incident's own row and card | **same** (board G2's run part, its words the operator's of 2026-11-16) |
| The top bar's Auto chip (962b2baf) | board T: "Self-healing: Auto until <time>" | the same, "until turned off" for an Auto with no expiry, sorted after every Auto with one | **same** |

Compared again 2026-11-24 (the week plan's Stage 4, docs/design/assistant.md as amended
2026-11-23): `base.html`'s toolbar Assistant button is drawn on every page, disabled while the
Assistant is off and greyed while hosted AI is off (compared in docs/fidelity/in-progress.md;
log: "The Assistant's button is drawn disabled while it is off"), and its panel names the page
it opened on. The button and the panel are no region of this page's boards, and nothing of the
page, its strip or its fleet view moves; every verdict above stands. Compared by the templates'
diff, not by new shots. Templates sha256 before:
`ad1623beabe78426a9b62742731020cecad0e1ba928682bfc5d39275fda962d7`.

Compared again 2026-11-24 (C3969): `_control_strip.html`'s two comments say the Self-healing
switch turns Auto on until someone turns it off (it had said "for the default duration");
comments only, nothing drawn changes, no deviation. Compared by the template's diff, not by
new shots. Templates sha256 before:
`560f2e016be7ea1c4245b0cb5a36db2df6725daa2db474f47761304b6c199ef8`.
Templates sha256: `825fd90a945d27a478b1c5d6578e4e4aecf552e5f484799c867e7c7d1d720e0b`

Compared again 2026-11-14 04:2x UTC (the operator's notes on board T, 2026-11-14; provisional,
operator review pending): "1. Remove the "N open" chip from Incidents in the sidebar. Needs
attention is the one inbox and its badge the one count", and "no Self-healing chip in the
sidebar at all; the sidebar is navigation only. Instead, a status chip in the top bar beside
the AI chip, shown only while Auto is in force: amber "Self-healing: Auto until <local time>",
opening Settings › Self-healing. Nothing in the normal state". The sidebar's two items are
their icon and label alone; `_incidents_chip.html` is gone and `_heal_auto_chip.html` draws
the top bar's chip (compared in the region added below and, for the bar, in `in-progress.md`).
Compared by the templates' diff and the pages and the browser boxes
tests/test_incidents_list_v2.py draws (the chip at 1440, 1280 and 500 px beside the AI chip,
which does not move), not by new shots. Templates sha256 before (the list beside the old chip
template): `61bb0a94c5d75b2c47520af91babbfc299218c60770d966a6aef3b42b766b7b0`.

Compared again 2026-11-14 03:0x UTC: the sidebar's "Open · Closed" row under Incidents removed
(the operator, 2026-11-14: "remove the "Open · Closed" sub-links under Incidents in the
sidebar; they duplicate the Incidents page's tabs. The sidebar keeps Incidents with its "N open"
chip"); the sidebar region below says so; every other region unchanged.

Compared again 2026-11-14 00:5x UTC: each group's disclosure gained its `data-keep` key (so a
live redraw keeps an opened group open, C472) and a template comment's words; no region drawn
differently, every verdict below unchanged (provisional, operator review pending).

Compared again 2026-11-14 18:0x UTC (C3701, the operator's "acknowledged ones shown as
acknowledged on both"): an Open row gains an **Acknowledged** badge beside its state when a
person acknowledged its Needs attention row, who and why on its hover; compared by the
template's diff and the page tests/test_incidents_and_needs_attention_agree.py draws, not by new
shots. One region added (Incidents: an acknowledged Open row, a deviation); every other verdict
unchanged. Templates sha256 before: `e29f14af964c1849d12616ab0e78bb32a878176ce016ea96c14d55f0145d4827`.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar: the section's place | TROUBLESHOOTING above OBSERVE, after History | the same | **same** |
| Sidebar: Incidents | the item, its count of open incidents outlined ("3 open"), Needs attention keeping the one red badge | the item alone, no count: Needs attention's badge is the one count (the operator, 2026-11-14) | **deviation** (log: Board T: no chip in the sidebar) |
| Sidebar: Incidents' tabs row | "Open · Closed · Problems" under the item | none: Open and Closed are the page's own tabs (the operator, 2026-11-14) | **deviation** (log: Board T: no tabs row under Incidents in the sidebar) |
| Sidebar: Self-healing | the item, the network's mode as its chip ("Dry run"), moving the policy to its own page | the item alone, no chip (the operator, 2026-11-14: "the sidebar is navigation only"), opening the network's Self-healing tab in Settings (its own log line: "Board T built: Self-healing opens Settings' Self-healing tab") | **deviation** (log: Board T: no chip in the sidebar) |
| Top bar: Self-healing in Auto | not on the board (the operator's note of 2026-11-14) | before the AI chip, only while a network's self-healing runs in Auto: amber, "Self-healing: Auto until <the viewer's time>" by the clock (UTC on hover), "on N networks" naming the soonest, opening that network's Self-healing tab; "Auto" alone up to 1366 px (its words on hover), just after the AI chip on a phone; nothing in dry run or off; read again once at its expiry | **deviation** (log: Board T: Self-healing in Auto is a top-bar chip) |
| Sidebar: Self-healing's sub-pages row | "Overview · Fix kinds · Saved fixes · Runs · Holds" | not drawn | **deviation** (log: Board T built: only what has a page is drawn) |
| Sidebar: Drills and Reports | two items, "suggested" | not drawn | **later** each with its own page, on the operator's decision (d) |
| Incidents: the bar | "Incidents", tabs "Open · 3", "Closed · 41", "Problems · 2", "checked 20 s ago" | the heading with its (i), tabs "Open · N" and "Closed · N", "checked" with the read's age | **deviation** (log: Board T built: only what has a page is drawn) |
| Incidents: the summary | "3 open · 1 needs a person · 1 Mercury working · 1 watching" | the same words, each group's count, the empty ones left out | **same** |
| Incidents: the rows' arrangement | one flat list, a row per incident | one closed-or-open details per group, 50 rows each, the rest counted | **deviation** (log: Board T built: Incidents' rows grouped and collapsed) |
| Incidents: an Open row | the state's dot and word, the title and its next step, since, Open incident | the state's badge (Drill beside it for a drill), the title as the link, the device and what it waits for, since | **deviation** (log: Board T built: a row's title opens the incident, and its next step is what it waits for) |
| Incidents: an acknowledged Open row | not drawn | an **Acknowledged** badge beside the state, muted, who and why on hover | **deviation** (log: Board T built: an acknowledged incident says so) |
| Incidents: a Closed row | how it closed, time to repair, by whom | the group says how it closed; the row its state, title, device, fixed by whom, time to repair and when it ended | **same** |
| Incidents: filters | Closed: filter by device, kind, outcome | a search over title, device and id and a device filter, on both tabs; the outcome is the groups | **deviation** (log: Board T built: Closed filters by device and words, its outcome the groups) |
| Incidents: Problems | the suggested third tab, recurring faults by fingerprint | not built | **later** the Problems tab, on the operator's decision (b) |
| Incidents: nothing acts | "nothing on this list acts on a device" | the same: two GET routes, links only | **same** |
| Incident detail: its address | `/v2/incident/<id>?list=<net>`, unchanged | the same | **same** |
| Incident detail: its breadcrumb | Incidents › Open (or Closed) › the title | Incidents / Open (or Closed) / the title, in the app's crumb separator; the sidebar marks Incidents current on it | **same** |
| Needs attention | stays the inbox, its items linking each incident's page | unchanged; every incident that needs a person is to have its item there (tests/test_incidents_on_needs_attention.py) | **same** |
| Device pages' Incidents tab | the device's incidents, the same rows filtered | not built | **later** a device-page tab, its own mockup |
