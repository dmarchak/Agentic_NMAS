# Fidelity: Devices

The Devices list as built, compared region by region with its boards (C650's step), after the
operator's walk W1 (2026-10-16, steps 13, 27 and 42). Read from shots of the boards and the page
side by side, in the same headless Firefox (`tests/test_board_shots.py::test_devices`), the page
fed by Save's lab (tests/test_save_v2.py's `lab`: r2's real capture as its committed golden, r3
answering and not in the manifest, r4 not answering at the last reachability read, s9 with no
driver recorded), the hourly startup check having read r2's accounts not saved and r3's saved.
Two states: the page as it opens, and with r2 and r3 ticked and the Actions menu open, ticked and
opened by real clicks as a person does. Read beside them: the operator's W1 captures 12 (nine
devices, s1 and s2 ticked, Actions open, at about half desktop width), 13 (the same at phone
width) and 29 (s1 and s2 at intent after the Mode B deploys), the screen as a person met it on
the host.

Boards: `FleetSelect.dc.html` (1440 wide) on the mockups canvas ("NMAS v2 mockups", page "7.4
Fleet"), board A, "A. Devices, one Actions menu (Save now does both), a Startup column", approved
2026-10-04 (C593); `redesign/Devices.dc.html` (1440, "Devices, with a selection") and
`redesign/DevicesPhone.dc.html` (390) on the first canvas ("NMAS redesign mockups", page
"Landing, devices, device"), the device list of NSOT_GUI_BRIEF section 13's mockup review, signed
off 2026-09-29. Board A is the later one: where the two differ, board A is compared and the first
board's region says so. `BatchDeploy.dc.html` (board B) is not drawn by this page: the Actions
menu's first row opens `/v2/devices/deploy`, the batch Apply's page (`templates/v2/apply.html`,
its own record), as the approval log's line of 2026-10-10 decided.
Shots: board A at 1440 and 1280, the first board at 1440, its phone board at 390; the page at
1440, 1280 and 390 (`devices-page-*`), and ticked with Actions open at 1440, 1280 and 390
(`devices-selected-page-*`), each phone shot also as its first screen.
Compared 2026-10-16.
Templates compared: templates/v2/devices.html, templates/v2/_devices.html
Templates sha256: `52c3023957423afdd19ee219d9c5502646409a0659677e227e1820e56d7e4e21`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | Devices current, under Needs attention; OBSERVE and SOURCE OF TRUTH groups | the same, current on this page; the groups carry the entries later boards added (Topology, Show commands, DHCP's move) | **same** |
| Top bar (first board) | the network chip, Go to device, the integrations line, Live, Assistant, the person | the same, the live state said as the socket's, a theme switch; no Assistant | **later** Phase 8 (docs/PHASE8_PLAN.md: AI returns as a responder) |
| Header | "Devices · 10" with its (i), the sub-line, Onboard devices… and Adopt a device…, each with How does this work? | the title, count and (i), the sub-line naming the network; Add device… (a card above the list), Discovered, Adopt a device… (a card), each operation's How beside it | **deviation** (log: Board E as built) |
| The header's How links | each beside its own button, on one row | at 1440 and 1280 the row wraps and Adopt a device…'s How does this work? lands under Add device…'s, away from Adopt (the shots); at the operator's half width (capture 12) each How stood beside its own button | **deviation** (log: Devices: Adopt's How does this work? wraps away from its button (a defect, register C650 follow-up)) |
| Views (first board) | List, Topology, Networks tabs under the header | not drawn: Topology is its own sidebar page (P.11) and the network is chosen in the top bar's picker | **deviation** (log: Devices: no List, Topology and Networks tabs) |
| Another operation's result (first board) | a banner, "Capture of 9 devices: partly done", View the result | not drawn: each operation draws its result in place on its own page, and Needs attention names what to act on | **deviation** (log: Devices: no banner for another operation's result) |
| Filters | search by name or address (rounded, padded, a search icon), Every state, Every platform | the same three, redrawing the list as typed or chosen; the search box drawn in the browser's own style (square, unpadded, no icon), unlike every other v2 field (the shots and capture 12) | **deviation** (log: Devices: the filters drawn in the browser's own style (a defect, register C650 follow-up)) |
| Selection bar | board A: a dark bar over the table once rows are ticked, "3 selected" with the names, their platform and reachability, Actions for 3 ▾, Clear selection | the first board's bar, inside the card over the rows it acts on, light: always drawn (its controls disabled until a row is ticked), "2 selected · s1, s2" (eight names, then "and N more"), Actions ▾, Clear selection; no platform or reachability summary (capture 12) | **deviation** (log: Devices: the selection bar) |
| An empty selection | not drawn (the bar appears with a selection) | "0 selected ·", a separator with nothing after it (the shots at 1440 and 1280; C901) | **deviation** (log: Devices: an empty selection reads "0 selected ·" (C901)) |
| Actions menu | Plan a deploy for 3…, Edit intent for 3…, Save (3)…, Apply the monitoring profile to 3…, each with its sub-line and its (i) | Plan a deploy for the ticked devices…, Save (2)… with its sub-line, Change a setting on (2)… (board D's own title) with its sub-line, and Save every device of Default (9)…, each with its (i) (capture 12, as the walk's step 13 named them) | **deviation** (log: Devices: the Actions menu's rows) |
| Actions the menu lacks | Apply the monitoring profile to 3…; Save's "2 of 3 not saved now" | neither drawn: the profile's apply (`/v2/monitoring/apply`) is reached from the devices ticked on Monitoring › Coverage, and Save's sub-line gives no count from the startup check | **deviation** (log: Devices: the Actions menu lacks Apply the monitoring profile and Save's not-saved count (a defect, register C650 follow-up)) |
| Plan a deploy (board B) | `BatchDeploy.dc.html`, a page of its own | the batch Apply's page with the `intent` scope, `/v2/devices/deploy` (compared in apply.html's record) | **deviation** (log: Batch deploy (board B, signed off 2026-10-04)) |
| Select every device shown | a checkbox in the table's head | not drawn: the head's first cell is the screen reader's "Select"; agreed as request R1 on 2026-10-16 (tri-state, "Select the <n> shown") | **later** C902 (the select-all checkbox, an agreed request, after cutover) |
| Columns | tick, Device (name · role), Status, Address, Platform, Intent, Startup, Last measured | the same eight, in the same order; at the operator's half width (capture 12) the table runs past the card and Last measured's header reads "Last" | **same** |
| Status | answering, not answering "since 09:41" | the same chips, "since 18 h ago" when the reader knows it; "not probed yet" for a device the reachability reader has not read | **same** |
| Intent | a chip: at intent, departs, unknown, no intent | the chip, and after it which measurement it was read at ("by Save All, no change, which earned a baseline" in capture 29; "by a save, golden changed" here), its reason on hover | **deviation** (log: Devices: the intent state says which measurement) |
| Startup | saved, not saved (its detail on hover), unknown | "accounts saved", "accounts not saved" (the check's detail on hover), "not checked", each with the reading's age | **deviation** (log: Devices: the Startup column names what it compares) |
| Last measured | "12 min ago" | the age, the golden's last change and the measurement's commit on hover | **same** |
| Pending onboarding | r7 with its chip, no tick, "not reached yet" | no tick for a pending row (compared by the template and tests/test_devices_v2.py's TestAPendingDevicesPage; the lab has none) | **same** |
| Footer | "Showing 6 of 10. Startup is the hourly startup check's last reading. A device pending onboarding has no tick." | "Showing N of M" above the table when a filter hides rows; the note adds "it compares the accounts only" and "Tick devices to plan a deploy for them (Actions › Plan a deploy for the ticked devices…)"; it names the hourly check while the rows show Save All's read-back ("52 min ago" in capture 12) | **deviation** (log: Devices: the footer names one source of the Startup column (C899)) |
| First board's selection actions | Plan a deploy… beside Actions; Add device ▾ as the primary | board A's one Actions menu replaces both, as built | **same** |
| Phone: rows | each device one line, its name and one state (Answering, Departs, Not answering) | each device a block with every column labelled (status, address, platform, Intent:, Startup:, Last measured:), as capture 13 | **deviation** (log: Devices: a phone row shows every column) |
| Phone: selection bar | pinned to the screen's foot: "3 selected", Clear, Plan a deploy… and a ⋯ for the rest | at the top of the card, scrolling with it; its Actions menu opens leftward from the button's right edge: whole in capture 13, where the bar kept one line, and past the screen's left edge in the 390 shot, where the bar wraps and the button sits at the left | **deviation** (log: Devices: on a phone the selection bar is not pinned and the Actions menu can run off the screen (a defect, register C650 follow-up)) |
