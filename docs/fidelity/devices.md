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
Templates compared: templates/v2/devices.html, templates/v2/_devices.html, templates/v2/_onboard_add.html, templates/v2/_console_kick.html
Templates sha256: `b62dbde6ba883b8cbac7d8b82018a0f4a16905561347ec93b0185456d3e2421b`

Compared again 2026-10-22, later (C1575, board F of `docs/boards/console-ztp.html`): Create's
result draws its console offer through one macro the pending page draws too
(`templates/v2/_console_kick.html`, now among the templates compared), which names who ran the
recorded survey and, when it did not find the device blank, offers "Survey <device>'s console
again…" in place of the kick-start (a kick-start types only on a device its survey found blank).
Compared by the template and tests/test_console_ztp_v2.py's `TestTheOffer`, not a new shot; the
Console (O7) row's words below say so, its verdict unchanged.

Compared again 2026-10-22 (O7 of out-of-band ZTP, board B of `docs/boards/console-ztp.html`):
Add device's review gains a Console part under Create, a fragment it asks for as it draws
(`templates/v2/_console_offer.html`: "Kick-start through the console…" when NetBox shows the
device's console path, its absence said with why when not), and Create's result gains the
kick-start's offer for a device whose console survey is recorded; the Create form carries an id
the survey's "Use <MAC> in the plan" includes. Board E draws no console, so it is a deviation
(below). Compared by the template and tests/test_console_ztp_v2.py's `TestTheOffer`, not a new
shot: one part added under the review's foot and one under the result's; every other region
unchanged.

Compared again 2026-10-21 (C1477, the overnight run): a pending row's Intent chip reads where
its onboarding has got to, from the onboarding-progress reader's stored value as the device's
pending page reads it ("answering: ready to Verify", "ZTP: fetched its config; not answering
yet", "ZTP: no lease yet", "pending: not read yet"; the stage's summary and the probe's claim on
its hover), followed by "read <age>", the value's age; a ZTP device's address reads "awaiting
ZTP (<address>)" where it read "awaiting DHCP"; the list redraws on `pending` as well. The board
drew "not reached yet" on the chip and no age, so it is a deviation (below). Every other region
unchanged: one span added to the Intent cell and one key to the list's redraw, read from the
diff and drawn by `tests/test_devices_v2.py`'s `TestAPendingRowReadsItsProgress`, not a new
shot.

Compared again 2026-10-19 (C1346, 0e): Add device's card (`_onboard_add.html`, opened in place
above the list) joins the record, compared with board E for the first time since it was built
(the section "Board E: Add device" below); the page's own regions above are unchanged.

Compared again 2026-10-18 (the operator's walk, B; C902's agreed design, R1): the table's head
draws the select-all box the first board drew there, as C902 agreed it: "Select the <n> shown"
on its label and hover, ticking every row the search and filters show (a pending row has no
tick and is not counted), a dash (indeterminate) while only some are ticked, cleared with the
rows by Clear selection. Beyond the board: with every row shown ticked the selection is ALL
MATCHING, the bar reading "All <n> matching selected" under a search or filter and "All <n>
selected" without one, and the form carries the search and filters in place of the names, each
action resolving the devices itself (`device_list.matching`). The list has no pages (C450's
revised board owes them), so a separate "Select all <N> matching" offer across pages has no
case to draw and is not drawn. Compared by the template and the real browser
tests/test_devices_select_all.py drives (the box ticking r2, r3 and r4 under the search "r",
indeterminate with one unticked, cleared; Save opened on all matching), not a new shot: one
control in the head's first cell, where the board drew it, and the bar's words. A deviation
(below); the Selection bar's verdict stands, its words now including the all-matching lead.

Compared again 2026-10-18 (C1232): the Actions menu gains a last row under Save every device of
<network>, "Save the devices of <network> with no golden…" with its sub-line ("decided from the
network's repository; the plan names the ones left out") and its (i), opening Save's plan for
the no-golden scope (today's toolbar's "Capture devices with no golden", which P7-27 removes).
Compared by the template and the menu tests/test_save_v2.py's `TestTheNoGoldenScope` draws, not
a new shot: one row in the menu, as its neighbours are drawn. No board draws it, a deviation
(below); no other region's verdict changed.

Compared again 2026-10-16 (C532) after `_devices.html` drew the intent state from the one
function the device page draws too (`device_list.intent_state`): a new chip, "intent changed
since measured" (info colour; what moved, when, and what the measurement read on its hover), where a commit to the device's
intent, the monitoring profile or the template library follows its last measurement; the list
redrawn on intent and template commits as well; the badge colours from `_macros.html`'s one
table. Shots `devices-page-1440`, `-390-first`: r2 in Save's lab reads "intent changed since
measured by onboarding, golden changed" (its intent was committed after its onboarding golden).
The Intent region rewritten; no other region's verdict changed.

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
| Save the devices with no golden (C1232) | not drawn | the menu's last row, "Save the devices of Lab with no golden…", its sub-line and (i) (`TestTheNoGoldenScope.test_the_devices_page_offers_it`) | **deviation** (log: Devices: the Actions menu offers Save the devices with no golden (C1232)) |
| Actions the menu lacks | Apply the monitoring profile to 3…; Save's "2 of 3 not saved now" | neither drawn: the profile's apply (`/v2/monitoring/apply`) is reached from the devices ticked on Monitoring › Coverage, and Save's sub-line gives no count from the startup check | **deviation** (log: Devices: the Actions menu lacks Apply the monitoring profile and Save's not-saved count (a defect, register C650 follow-up)) |
| Plan a deploy (board B) | `BatchDeploy.dc.html`, a page of its own | the batch Apply's page with the `intent` scope, `/v2/devices/deploy` (compared in apply.html's record) | **deviation** (log: Batch deploy (board B, signed off 2026-10-04)) |
| Select every device shown | a checkbox in the table's head | the box there, as R1 agreed it (2026-10-16): "Select the <n> shown", ticking the rows the search and filters show (no pending row), indeterminate while some are ticked; every row shown ticked, the selection is all matching ("All <n> matching selected"), carried as the search and filters and resolved by each action; no "Select all <N> matching" offer, the list having no pages (`tests/test_devices_select_all.py`) | **deviation** (log: Devices: a select-all box, all matching across pages (the operator's walk, 2026-10-18)) |
| Columns | tick, Device (name · role), Status, Address, Platform, Intent, Startup, Last measured | the same eight, in the same order; at the operator's half width (capture 12) the table runs past the card and Last measured's header reads "Last" | **same** |
| Status | answering, not answering "since 09:41" | the same chips, "since 18 h ago" when the reader knows it; "not probed yet" for a device the reachability reader has not read | **same** |
| Intent | a chip: at intent, departs, unknown, no intent | the chip, and after it which measurement it was read at ("by Save All, no change, which earned a baseline" in capture 29; "by onboarding, golden changed" here), its reason on hover; since C532 a fifth chip, "intent changed since measured", where what the measurement judged against has moved since (r2 here) | **deviation** (log: Devices: the intent state says which measurement), and since C532 (log: Devices: a fifth intent chip, intent changed since measured) |
| Startup | saved, not saved (its detail on hover), unknown | "accounts saved", "accounts not saved" (the check's detail on hover), "not checked", each with the reading's age | **deviation** (log: Devices: the Startup column names what it compares) |
| Last measured | "12 min ago" | the age, the golden's last change and the measurement's commit on hover | **same** |
| Pending onboarding | r7 with its chip, no tick, "not reached yet" | no tick for a pending row (compared by the template and tests/test_devices_v2.py's TestAPendingDevicesPage; the lab has none); since C1477 its chip reads its onboarding's progress as its page does, with the value's age, and a ZTP device's address says ZTP (`TestAPendingRowReadsItsProgress`) | **same**, and since C1477 **deviation** (log: Devices: a pending row reads its onboarding's progress (C1477)) |
| Footer | "Showing 6 of 10. Startup is the hourly startup check's last reading. A device pending onboarding has no tick." | "Showing N of M" above the table when a filter hides rows; the note adds "it compares the accounts only" and "Tick devices to plan a deploy for them (Actions › Plan a deploy for the ticked devices…)"; it names the hourly check while the rows show Save All's read-back ("52 min ago" in capture 12) | **deviation** (log: Devices: the footer names one source of the Startup column (C899)) |
| First board's selection actions | Plan a deploy… beside Actions; Add device ▾ as the primary | board A's one Actions menu replaces both, as built | **same** |
| Phone: rows | each device one line, its name and one state (Answering, Departs, Not answering) | each device a block with every column labelled (status, address, platform, Intent:, Startup:, Last measured:), as capture 13 | **deviation** (log: Devices: a phone row shows every column) |
| Phone: selection bar | pinned to the screen's foot: "3 selected", Clear, Plan a deploy… and a ⋯ for the rest | at the top of the card, scrolling with it; its Actions menu opens leftward from the button's right edge: whole in capture 13, where the bar kept one line, and past the screen's left edge in the 390 shot, where the bar wraps and the button sits at the left | **deviation** (log: Devices: on a phone the selection bar is not pinned and the Actions menu can run off the screen (a defect, register C650 follow-up)) |

## Board E: Add device (the card above the list; C1346)

Board: `OnboardList.dc.html` (board E, 1440, "E. APPROVED 2026-10-04, with ZTP's three ways in"),
its "The devices" section and the plan's line under it; the discovery list above it is board L's
(docs/fidelity/onboard.md). The card was built under the Phase 7 mode while the canvas could not
be read (the approval log's "Board E as built", 2026-10-10) and is compared with the board here
for the first time, after 0e (C1346) added Route option (3) and the Gateway's second clause. Shots
(`tests/test_board_shots.py::test_onboard_add_relayed`, on Save's lab): the board at 1440 and
1280 (`onboard-add-board-*`); the card opened from Devices by a click and ZTP chosen
(`onboard-add-ztp-page-*`, 1440, 1280 and 390), the relayed device's fields filled with "The
relay's own address" chosen (`onboard-add-relay-page-*`, 1440 and 390), its review planned
behind the relay as tests/test_ztp_relayed.py plans it (`onboard-add-review-page-*`, 1440 and
390, Create offered), and Static chosen, the control (`onboard-add-static-page-1440`: Route option
(3) hidden). Compared 2026-10-19. The 1280 shots draw what the 1440 ones do; there is no phone
board.

| Region | Board | Built | Verdict |
|---|---|---|---|
| Entry point | Devices › Onboard devices, a page of its own, with Add a row and Paste rows (CSV)… | Add device… on Devices opens the card in place above the list; Discovered's Pick… and a retired device's Onboard it again… open the same card | **deviation** (log: Board E as built) |
| Header | "The devices", Add a row, Paste rows (CSV)… | "Add device to <network>", Close | **deviation** (log: Board E as built) |
| Rows | a table, one row per device, each with Remove; several planned at once | one device per card; Add another after its result | **deviation** (log: Board E as built) |
| Fields | Name, Platform, Role, Address source, Serial, MAC, Address / prefix, Management interface | Network (the page's, said), Name, Platform, Role, Address from, Management address, Mask, MAC address, Management interface, Gateway, Route option (3), Platform management port, Domain; each label beside its field and its message under it | **deviation** (log: Board E as built) |
| Role | the role map's template and credential profile named under the role, and The role map | "asked, never guessed from the platform: it becomes the monitoring role label, the topology icon and the NetBox role"; the template and credential source in the review | **deviation** (log: Board E as built) |
| Address source | seven ways: ZTP by MAC, by serial, by serial and MAC, discovered; DHCP, any address; DHCP reservation; Static | three: Static (in the config), DHCP (a Kea reservation someone made), ZTP (the tool reserves it and serves the config); discovered is Discovered's Pick… | **deviation** (log: Board E as built) and **later** board M (the serial ways) |
| Interface | a drop-down of the platform's interfaces | typed, its spelling checked | **deviation** (log: Board E's interface dropdown) |
| Field messages | each on its own reserved line, so a message never moves the field | each under its field; a refusal is the review's, every reason together | **same** |
| Gateway | not drawn | Gateway, optional: "blank when this host is on the device's subnet; behind a relay, the relay's own address" (the second clause C1346's) | **deviation** (log: Add device: Route option (3) and the Gateway's relay clause, compared with board E (C1346)) |
| Route option (3) | not drawn: board E's ZTP rows carry no route option (D4 as decided) | a select under Gateway, "None (D4)" by default or "The relay's own address", with "ZTP behind a relay only: offered when AutoInstall needs a route to fetch its config off its subnet; never a DNS server"; drawn only while Address from is ZTP (the Static shot) | **deviation** (log: Add device: Route option (3) and the Gateway's relay clause, compared with board E (C1346)) |
| Plan and Create | the plan's line under the rows ("Plan 0b3e7c21: 1 device can be created; …") and Preview r8's first-boot config, then Create | Review the plan ("A review creates nothing."), then the review in place: the summary (behind a relay its Management IP line, "ZTP behind the relay … offering option 3 (routers) …, the relay's own address …", or "with no option 3"), the configuration folded, the checks, What it does not do, Create <device> and Change the fields | **deviation** (log: Board E as built) |
| Refusals | under the field: a serial five devices report, an address another device holds | the review's reasons together above the plan; behind a relay, a gateway that is not the relay's own address, or "The relay's own address" chosen on a subnet this host is on, is one of them | **deviation** (log: Board E as built) |
| Phone | not drawn (no phone board) | at 390 each label above its field in one column, Route option (3) and its message whole (`onboard-add-relay-page-390`) | **deviation** (log: Board E as built) |
| Console (O7) | not drawn: board E has no console | the review's Console part, read as it draws: "Kick-start through the console…" when NetBox shows the device's console path, "No console kick-start: <why>" when not; Create's result offers "Kick-start <device> through the console…" once its survey is recorded, or "Survey <device>'s console again…" when that survey did not find it blank (boards B and F of `docs/boards/console-ztp.html`) | **deviation** (log: Add device: the review's Console part, compared with board E) |
