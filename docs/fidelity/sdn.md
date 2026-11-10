# Fidelity: SDN › Controllers, Flows and Responses (2026-10-27)

**Compared again 2026-10-27 ~09:5x UTC (PHASE8_PLAN 17.1 S8 to S10, S16):** the Responses tab
beside `SdnResponses.dc.html` (1440, 1280 and 390, from the same test's `sdn-responses` shots: one
scan awaiting a person, a loop log line), and Flows again with Add flow…, Edit… and Remove…
(SdnFlowEdit's controls on SdnFlows' rows). The operation card (`_sdn_op.html`, board
SdnResponse) and the flow editor (`_sdn_flow_form.html`, board SdnFlowEdit) are drawn by a
click in place, which the board-shot harness does not shoot (it shoots pages): their regions are
**later**, compared when a click-driven shot exists; their behaviour is held by
tests/test_sdn_ops_v2.py and the v2 walk's provider (tests/v2_context.py `_sdn_operations`).

Boards: `SdnControllers.dc.html` (1440), `SdnFlows.dc.html` (1440) and `SdnPhone.dc.html` (390),
PHASE8_PLAN 17.5 boards 1, 2 and 7, drawn in the agent's copy of the mockups canvas's project
folder and signed off under the Phase 7 mode 2026-10-27 (docs/STANDING_APPROVAL_LOG.md, "SDN
boards S1 to S7"). Their grey notes are notes for the builder, not page text.

Shots: `tests/test_board_shots.py::test_sdn` (`sdn-controllers` and `sdn-flows` at 1440, 1280
and 390 beside their boards; `sdn-phone` at 390 beside SdnPhone; `sdn-responses` at 1440, 1280
and 390 beside SdnResponses, `sdn-responses-suspended` at 1440 and 390 with no board, C2009; `sdn-responses-held` at 1440
and 390 with no board, C2001; `sdn-responses-stale` at 1440 and 390 and `sdn-responses-stale-held`
at 1440 beside SdnResponses' states section, C2003). The data is tests/test_sdn_v2.py's
lab: Default's `lab-controller` answered by Ryu 4.34's captured answers through the real Ryu
driver (one switch, `s1`, its nine captured flows, one meter), its flow intent recorded as a
response would record it (the meter flow, cookie ...0002, recorded; the drop flow in Mercury's
range, ...0001, not; an IPv6 drop, ...0003, recorded and not installed, its hard timeout past),
and `branch-controller` at another address refusing every connection, read twice by the SDN
reader 12 minutes apart. The board's four switches, 61 flows and ONOS second controller are
board data; the capture has one switch, and an ONOS connection cannot be saved (its driver is
not built), so the second controller is a Ryu one that does not answer.
Compared again 2026-10-28 ~18:0x UTC, for one attribute: the incident's "Seen also" list
carries `data-keep` (C472's rule, found by test_live_details_keep in C1999's gate), so an
open list survives a live redraw; nothing drawn moves.
Hashed again 2026-11-08 ~10:3x UTC for C2765, for one argument in three controls: SDN › Apps'
Preview deploying…, the redeploy's preview and Preview a rollback… post to the preview, a reveal
now (it reads the controller host as the person), so `_sdn_apps.html` and `_sdn_app_deploy.html`
carry `gate('reveal')` where they carried `gate('confirm')`. `gate()` draws nothing when `may`
allows the kind (`preview_confirm.control_gate`: "a person's page is byte for byte what it
was"), and a verified person may both, so nothing drawn moves for a person; a service sees the
three drawn disabled with the reveal's reason, as before with the confirm's. Compared by reading
the diff against `control_gate`, with no new shot.
Hashed again 2026-11-08 for C2760 (decision 8, D8-A 4): `_sdn_app_deploy.html`'s plan card
draws each app's compiled start-time config after the files (the region row "C: each app's
start-time config" below) and marks a changed or new config in the set's Files cell; nothing
else moves. Compared by reading the template against artboard C, with no new shot (the
templates then hashed `f996aa466fd13f7e0c4e915154739eecc3d43b8d1b0f9b17acf050be75d38c92`).
**Compared 2026-11-10 ~04:3x UTC for C2904 (Lab 9 Objective 4): SDN › Apps' DHCP steering
card**, beside docs/boards/lab9-sdn.html artboard B's DHCP steering card (self-signed
2026-11-10, docs/STANDING_APPROVAL_LOG.md, "Board lab9-sdn B"), **by reading the template
against the artboard, region by region, with no new shot** (the board-shot harness has no case
for the card's states yet; tests/test_dhcp_steer_v2.py and tests/v2_context.py `_dhcp_steering`
draw each). `_sdn_apps.html` changed only to include `_sdn_dhcp.html` (new, in the compared list
below) under the Add an app as a Draft control, for a network whose devices are NetBox's.
The regions whose names begin "D:".

| Region | Board B | Built | Verdict |
|---|---|---|---|
| D: the card's place | B: a card of its own on SDN › Apps (beside the DNS card, now superseded) | a card of its own, under Add an app as a Draft… and above the controllers | **same** |
| D: the head | B: DHCP steering, the chip "on 5 switches" | the same; "not steered" when nothing is recorded, "can't compile" when the NSOT refuses | **same** |
| D: the server | B: router, address, MAC on switch port n (NetBox Service dhcp, protected) | the same, with the switch's interface name, and "protected: the NSOT's dhcp classes name feature:dhcp-unicast", or NOT protected with why | **deviation** (log: C2904 B 3) |
| D: client requests, server replies | B: the two lines | the same, the requests line naming the hosts and edge switches | **deviation** (log: C2904 B 3) |
| D: IPv6 | B: not covered, DHCPv6 (UDP 546 and 547) is not steered: it floods as before | the same | **same** |
| D: the counts | B: Last hour, requests steered and replies dropped | Counted, the same two numbers since each flow was installed, with the read's time | **deviation** (log: C2904 B 1) |
| D: the actions | B: Edit settings…, Preview steering…, Remove steering…, How does this work? | the same, each preview busy on itself, a compact (i) beside each preview; Remove steering… disabled, its reason on hover, when nothing is recorded | **same** |
| D: settings, the preview, a refusal, the result | no artboard for DHCP (the DNS card's settings and preview are drawn) | drawn after the DNS card's: Steer on every edge switch or chosen ones with Preview…; the preview's rows (switch, what, priority, REST body) with Steer DHCP on <N> switch(es); Remove <N> steering flow(s); a refusal with Close; the result per switch | **deviation** (log: C2904 B 2) |
| D: phone width | no artboard | the tables stack by their labels as the Apps tab's do; not shot | **later** (C2858: the card's board shot at 390) |

**Compared 2026-11-08 ~19:0x UTC for C2777 (the operator's decision 8): SDN › Apps' NSOT export
card**, beside docs/boards/nsot-export.html (drawn and counted as signed off under the Phase 7
mode, docs/STANDING_APPROVAL_LOG.md "D8-R 2"), and the Apps tab's two registry notices beside
docs/boards/code-repository.html artboard E ("D8-R 1"), **by reading the templates against each
artboard, with no new shot**: tests/test_board_shots.py has no case for them yet (C2858). Their
states are held by tests/test_nsot_export_op.py and tests/test_code_repo_v2.py, which draw each.
`_sdn_view.html` changed only to redraw the Apps region on `nsot_export` and `code_repo`;
`_sdn_apps.html` only to include the card above the controllers and draw the two notices with
their link. Every other verdict stands. The regions whose names begin "X:" below.
Templates sha256 before: `f996aa466fd13f7e0c4e915154739eecc3d43b8d1b0f9b17acf050be75d38c92`
(C2760's plan card, above; the card was built beside it on `5866d4f6…`, and the two builds
were integrated on main together).

| Region | Board | Built | Verdict |
|---|---|---|---|
| X: the card's place | A: above the controller cards on SDN › Apps | the same | **same** |
| X: at rest | A: NSOT export, committed chip; Committed (hash, commit, when, who, NetBox's version), Holds (each kind's count), Read by; Export from NetBox… with its (i) and what it does | the same lines; the words of what it does on the button's hover | **same** |
| X: none committed, not NetBox's | B: the notice and Export from NetBox… primary; for a network not NetBox's the control disabled, its reason on hover | the same | **same** |
| X: a committed export that can't be read | no artboard | the card says it can't be read and why, and that exporting again replaces it | **deviation** (log: D8-R 5) |
| X: the preview | C: title, the changes chip, This export, The committed one, Goes to, the table by kind with each kind's names folded, the unchanged kinds in one row | the same, each kind with its count now, each fold keeping its state across a live redraw (`data-keep`); This export says "read from NetBox now" | **deviation** (log: D8-R 6) |
| X: the preview's actions | C: Commit the export, Cancel, (i) | Commit the export, How does this work?, Cancel; busy on itself ("Committing…") | **deviation** (log: D8-R 6) |
| X: nothing to commit | D: the words and Close, no confirm | the same | **same** |
| X: refusals | E: NetBox unreadable; the export moved; the committed file moved; Close and Preview again | the same, each naming both values; Preview again primary when something moved | **same** |
| X: the result | F: Export (was), Commit as who and how verified, Changed, Close; Open it on History | the same, with Open History's commits | **deviation** (log: D8-R 7) |
| X: the live redraw | C's note: held while the card is open | the preview, refusal and result cards carry `data-holds-live`, as the deploy's card does | **same** |
| X: the registry's notices | code-repository E: No app version can be listed (the registry's own words) and the folders not registered, each with Open the code repository's card | the same | **same** |
| X: phone width | G: the table stacked, the confirm at the card's foot | the table's cells stack by their labels as the Apps tab's do; not shot | **later** (C2858: the card's board shot at 390) |

**Compared 2026-11-10 ~03:3x UTC for Lab 9 B1 (C2903): SDN › Flows' Analyse this network**,
beside docs/boards/lab9-sdn.html artboard I (self-signed 2026-11-10 under the Phase 7 mode),
**by reading the template against the artboard, with no new shot**: tests/test_board_shots.py
has no case for the region yet. Its states are held by tests/test_sdn_analyst.py and the v2
walk's `_sdn_analyse` provider, which draw each. `_sdn_view.html` changed only to include
`_sdn_analyse.html` (new, in the compared list) above Flows' filter. The regions whose names
begin "I:" below. Templates sha256 before: `94c428ab196518687ff4258e4c5f6b8109a94c9096d27a844efafc018ed3904d`.

| Region | Board | Built | Verdict |
|---|---|---|---|
| I: the row's place | I: under the tabs, above the two cards | under the summary and granularity notes, above the filter: the same row, the cards under it | **same** |
| I: Analyse this network | I: an AI-marked button | the AI mark (its hover the task, model and cap), the button busy on itself ("Analysing…"), disabled with the reason in place while hosted AI cannot answer, off while no snapshot is kept, with How does this work? | **same** |
| I: the collection's line | I: "5 switches, collected 14:05 UTC · Haiku 5.5 · about $0.003" | the same shape from the latest snapshot (its id, who collected it, links not up, ports down and parts not read on hover), "partly read" when it was | **same** |
| I: Collect now | not drawn | Collect now, busy on itself, with its (i); "Collecting since …" while the job runs | **deviation** (log: Board lab9-sdn I built (Lab 9 B1), 1) |
| I: Trace a packet…, Add a flow… | I: in the row | Trace a packet… beside the filter, Add flow… on each switch, as Flows draws them | **deviation** (log: Board lab9-sdn I built, 2) |
| I: the findings card's head | I: "3 findings", "answered 14:05 UTC · the call · Was this right? Yes No" | the count; answered when, by which model, for whom, "the call" to History; Was this right? the shared control under the note | **deviation** (log: Board lab9-sdn I built, 4) |
| I: the findings table | I: Finding (a severity chip and the finding), Why, Evidence as ids | the same columns; ids the collection's own, an id the snapshot does not hold said as removed | **deviation** (log: Board lab9-sdn I built, 3) |
| I: the check's note | I: "a claim citing nothing is dropped by the check, and the answer says how many were" | the same words with the count and what each dropped one did, and the removed ids and shortened texts counted | **deviation** (log: Board lab9-sdn I built, 7) |
| I: the planted sheet | I: Planted, Found (found or missed), Why; Add a planted issue…, Download the sheet | the same columns; each issue's evidence under its name; Why a field with Save; Add a planted issue… opening its form in place; Download the sheet (Markdown) and "as CSV" | **deviation** (log: Board lab9-sdn I built, 5) |
| I: states the board does not draw | not drawn | no collection yet, collecting, past its bound, couldn't collect, couldn't analyse, a newer snapshot than the answer, the sheet unreadable: each said in place | **deviation** (log: Board lab9-sdn I built, 6) |
| I: phone width | not drawn at 390 | the two cards stack under 900 px and each table's cells stack by their labels under 700 px, as Flows' table does; not shot | **later** (a board shot of the region at 1440, 1280 and 390) |

Templates compared: templates/v2/sdn.html, templates/v2/_sdn_view.html, templates/v2/_sdn_answer.html, templates/v2/_sdn_responses.html, templates/v2/_sdn_op.html, templates/v2/_sdn_flow_form.html, templates/v2/_sdn_log.html, templates/v2/_sdn_apps.html, templates/v2/_sdn_app_deploy.html, templates/v2/_sdn_export.html, templates/v2/_sdn_app_publish.html, templates/v2/_sdn_app_draft.html, templates/v2/_sdn_tabs.html, templates/v2/_sdn_analyse.html, templates/v2/_sdn_dhcp.html
Templates sha256: `ed2efe67e329b44e454d2ca838bb8739de5d6c3a4b2e83fc1d561e83af82d94b`
Hashed again 2026-11-10 for Lab 9 B1 (board lab9-sdn I, the "I:" regions above):
`_sdn_analyse.html` (new, in the compared list) draws Analyse this network, its findings and the
planted-issue sheet; `_sdn_view.html` only includes it on Flows.
Hashed again 2026-11-10 for Lab 9 Objective 2 (C2902; board lab9-sdn A): the SDN tabs moved into
their own partial, `_sdn_tabs.html`, which every tab's region draws, and gained Switches between
Controllers and Flows (its own record, docs/fidelity/sdn-switches.md). The tabs' row is
otherwise as compared: the same classes, order and current tab; no other region moved. The
same day's Add an app as a Draft (`_sdn_app_draft.html`, board authoring-from-words F) is in the
list too. The three were merged and hashed together.
Hashed again 2026-11-10 for C2904 (board lab9-sdn B's DHCP steering card, its regions "D:"
above): `_sdn_apps.html` includes `_sdn_dhcp.html` (new, in the compared list); nothing else on
the tab moves (the templates before it hashed `d5029510ce1c9ce2095a4056a92cfec6258ca1927d0231b91fe3079febb97ef8`).
Merged with B1's and Objective 2's changes the same day and hashed with them, over the union.
Hashed again 2026-11-09 for C2854 (board app-publish A to D, self-signed, docs/STANDING_APPROVAL_LOG.md
"C2854 P 1"): an app's Versions row draws a Draft's test state with Run its tests and Review and
publish…, and a Published one's self-review; `_sdn_app_publish.html` (new, in the compared list)
draws the run's answers, the preview with its one confirm, and Publish's answers. Compared by
reading the templates against the board's artboards, with no new shot; tests/test_app_publish.py
and tests/v2_context.py draw each state (the templates then hashed
`51d2180eb5e7d0dd38bc8ca5d371def5a54f533fffb4b0f0183e800d9a41f624`).
Hashed again 2026-11-09 for C2776 (the export's end hosts): `_sdn_export.html`'s kind names
gain "End hosts", so the preview's changes table and the result's Changed line name the new
kind; nothing else moves. Compared by reading the template against docs/boards/nsot-export.html,
with no new shot (the templates then hashed `00d1e7b9472f8e6a17fac85e5ce3ae41cd9f1ed3d240930b2c3719a7d93cbab3`).
Hashed again 2026-11-09 for C2852 (SDK option A, the operator's go of 2026-11-09): the plan card
draws the app SDK the request names after the files and before the configs ("The app SDK,
staged to /opt/ryu-apps/.sdk/<sha256>/", its hash and its one file), the region row "C: the
app SDK" below; nothing else moves. Compared by reading the template against artboard C, with
no new shot (the templates then hashed `cbb06ccd24311cf33aaad064e6545526cbdf7601b0a3e5c5853885cfb17f0d06`).
Hashed again 2026-11-09 for C2578 (board D of docs/boards/sdn-trace.html, artboard A's "SDN ›
Flows: the way in"): `_sdn_view.html`'s Flows filter gains **Trace a packet…** after Show, a link
to Topology › Path… on the Flow tables layer with its form open, its How does this work? beside
it; the board draws it beside the search, and the trace is compared in docs/fidelity/topology.md,
"The SDN trace (board D, sdn-trace.html)". Nothing else moves. Compared by reading the template
against artboard A, with no new shot (the templates then hashed
`3335260fc1f3d0be28248bba24d7f7d52847dfa283cb4c94d7f49396bccae9fc`, after C2854's Publish).
Hashed again 2026-11-10 for the operator's decision of 2026-11-10 (board authoring-from-words,
artboards D and F, revised and self-signed, docs/STANDING_APPROVAL_LOG.md "I-2 W 2"):
`_sdn_apps.html` includes, under the NSOT export card, `_sdn_app_draft.html` (new, in the
compared list): Add an app as a Draft… at rest with its (i) and where it adds to (or drawn
disabled, its reason beside it, for an https location or none set); the folder picker with
Preview adding it and Cancel; the preview (To, On top of, The folder, Files with each path,
bytes and sha256, The commit, Author, Then) with Add <name> as a Draft and Cancel and the hash
it is bound to; a refusal with Choose the folder again and Close; the result, registered (Open
<name>'s page) or not yet (Open the Code repository's card), with Close. Compared by reading
the template against artboards D and F, region by region, with no new shot (the board-shot
harness shoots pages, and the card's states are drawn by a click; tests/test_draft_write.py
and tests/v2_context.py draw each). Every region is the same but two: F draws the picker's
button as "Choose folder…" with the folder's name beside it, and the built card draws the
browser's own file input, whose words are the browser's (the board's note says so: same); D's
preview lists files with " · " between path, bytes and hash, and the built card draws them as a
table, as the Apps tab's tables are (a deviation of layout only, no control or field moves;
log: I-2 W 3). Nothing else on the tab moves.

**Compared 2026-11-08 ~06:1x UTC for P6 (C2677): SDN › Apps**, beside the operator's signed board
`docs/boards/controller-app-deploy.html` (artboards A to L, signed 2026-11-07; copied into the
shots' boards folder and shot whole at 1440, 1280 and 390). Shots: `tests/test_board_shots.py::
test_sdn_apps` (`sdn-apps` at 1440, 1280 and 390 beside the board; `sdn-apps-app` (B) and
`sdn-apps-plan` (C, opened by a click on the app's page) at 1440 and 390; `sdn-apps-receipt` (H)
at 1440; `sdn-apps-drift` (J) at 1440 and 390). The data: Default with `deploy_op.Sources`
faked at its seam (tests/test_controller_deploy_op.py's `FakeSources`: one controller `ctl`,
two switches, one link, and a code repository with of_versions 1.0.0 and 1.1.0 Published),
after one deploy confirmed through the real routes, post-check and receipt store. The board's
data (ctl-1, five switches, four apps) is board data. `_sdn_view.html` changed only to add the
Apps tab, its heading and its region's arguments; the other tabs draw as before. The cards drawn
from a POST that the shots do not reach (D's refusals and the plan that changes nothing, E's
running card, F and G's results) are **later**: their behaviour is held by
tests/test_sdn_apps_v2.py and the v2 walk's provider (tests/v2_context.py `_sdn_apps`).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Apps tab | Controllers, Flows, Apps, Responses; Apps marked new | the same four tabs, Apps between Flows and Responses | **same** |
| Apps heading and line | "SDN · Apps" with its (i), "The apps the network's controller runs, deployed by Mercury from the network's code repository. Each deploy restarts the controller." | the same words; the (i) opens the manual's SDN page at Apps | **same** |
| A: the controller card's head | name, "runs Mercury's record" chip; Ryu version, unit, User, listen address and its NetBox Service, "5 of 5 expected switches connected" | name and chip (runs Mercury's record, differs from Mercury's record, can't tell, not read, no deploy through Mercury); unit and listen address only | **deviation** (log: P6 A: the controller card's line without Ryu's version, User and switch count) |
| A: the card's actions | Preview a deploy…, Read again, "read 40 s ago", How does this work? | Preview a deploy… (disabled, its reason on hover, while Mercury holds no record), the read's age, How does this work?; no Read again | **deviation** (log: P6 A: no Read again until the controller read is wired) |
| A: Last deploy | outcome chip, when, who, what changed, the slowest switch, its receipt, every deploy on History | the same | **same** |
| A: Rolls back to, on a miss | "the request before the last deploy" | what the controller runs by Mercury's record (the request a next deploy's miss rolls back to), or the drop-in before when none is recorded | **deviation** (log: P6 A: Rolls back to names the record's request) |
| A: Code repository and The host | the repository at its commit with Fetch now and its Settings link; the host with Open its device page and Open in NetBox | the repository line only when the registry gives it, no Fetch now; the host with Open its device page, no Open in NetBox | **deviation** (log: P6 A: no Fetch now and no Open in NetBox) |
| A: summary line | apps enabled, /health failing, a newer Published version, Drafts | the same counts, and how many differ from the record | **same** |
| A: the apps table | grouped by what to do, each row opening its app's page; no row buttons | the same columns and groups, with two more groups when they have rows (Differs from Mercury's record; Registered, not in the set) | **same** |
| B: versions and the one action | radio per version, Draft disabled with its reason, pins, On ctl-1, "Preview deploying 1.3.0…" disabled for the running version with its reason on hover, Compare, Open the review | the same, but no Compare and no Open the review | **deviation** (log: P6 B: no Compare and no Open the review) |
| B: what the version declares | controllers, OpenFlow, requires, REST, owns flows, egress, the compiled config | the same; Config says no start-time config is compiled yet | **later** (C2760, the config compiler) |
| C: the target, the set, the files | as drawn | the same, from the plan | **same** |
| C: each app's start-time config (C2760) | not drawn: the set's Files column says "its config file"; B's Config line names the compiled tables and links "the compiled config" | after the files, per app with a config: "<app> <version>'s start-time config, staged to /opt/ryu-apps/<app>/<version>.config.json" with a chip (new, changed, or the same as now against the record's last), the sha256 in the request, each switch's tables and the profile they were placed from, and the JSON masked; the Files cell adds "(changed)" or "(new)". Compared by reading the template against artboard C, not shot (tests/test_app_compile.py renders it) | **deviation** (log: D8-A 4: the plan draws each app's compiled start-time config) |
| C: the app SDK (C2852) | not drawn: the board predates the SDK's staging | after the files: "The app SDK, staged to /opt/ryu-apps/.sdk/<sha256>/", the hash in the request, on every app's import path, and its file with mode, bytes and blob. Compared by reading the template against artboard C, not shot (tests/test_controller_deploy_op.py builds the plan it draws) | **deviation** (log: C2852 A 1: the plan draws the app SDK it stages) |
| C: conformance | per switch: profile entry, switch speaks, refuses a hello above, common, verdict | per switch: common, refuses a hello above, verdict | **later** (C2710, F6: conformance's rows carry neither the profile entry nor the switch's own versions) |
| C: the drop-in, before and after | the render with the removed lines struck and the new ones marked | the same, the lines diffed | **same** |
| C: the restart and what must come back | bounds with their placeholder chips; expected switches, links and apps with a From column and Back when; what already fails | the same, without the From column | **deviation** (log: P6 C: the expected table without its From column) |
| C: before, and if it misses; the confirm | window, holds, sends, the rollback, the plan hash; Deploy…, Cancel, How does this work? | the same; How does this work? sits right after the confirm, before Cancel | **deviation** (log: P6 C: How does this work? before Cancel) |
| D: refusals, the moved plan, nothing to deploy | as drawn | built (the refusals in the plan's own words, the moved plan naming each moved part with both hashes, the redeploy offered); not shot | **later** (a shot of a card a POST draws) |
| D: the first deploy | a card of its own with "no rollback target" | the plan itself: a first deploy's rollback is the put-back of the drop-in before (K3 as the operator changed it), and with no drop-in before the plan and its confirm say "with no rollback" | **deviation** (log: P6 D: the first deploy is the plan with its put-back, K3 as changed) |
| E: running | the stepper and a per-switch Coming back table | the one stepper (tests/test_one_stepper.py) with the post-check's counts on its step; no Coming back table; not shot | **deviation** (log: P6 E: no per-switch Coming back table while running) |
| F and G: results | each outcome's card with its controls | each outcome's card from the receipt, green only for deployed; Open the receipt, Back to Apps, Preview again, Preview a rollback… (on Unknown, the set before), Open its Needs attention row; no Read the outcome again, Read ryu-manager.service's log or Open of-hp-1 on SDN › Switches; not shot | **deviation** (log: P6 F and G: the results' read and open controls not built) |
| H: the receipt | the receipt with its sub-links (its receipt, the list, both texts, its outcome whole, the steps with their times) and Download, Open the controller | the receipt with its receipt-before link, Download the receipt (JSON) and Open the controller; the other sub-links not drawn | **deviation** (log: P6 H: the receipt's sub-links not drawn) |
| H: History | the deploys listed by day with a kind filter | History's own list, its kind filter "Controller app deploys" | **same** |
| I: Needs attention | the rows this operation raises and clears | the unknown-outcome row and a red row for a controller not back (rollback failed, not rolled back), each from the receipts and opening its receipt; the /health, switch, link, waiting-planned and drift rows wait on the controller's reads | **later** (C2677's rest: the rows drawn from the controller's reads) |
| J: drift | the card's chip, a table of both sides, Preview the redeploy…, Read again, can't tell | the same, without Read again | **same** |
| L: phone width | the plan full-screen, its confirm pinned; tables stacked | tables stacked, the confirm pinned at the bottom; the plan opens in place below the app's page | **deviation** (log: P6 L: the plan opens in place at phone width, its confirm pinned) |

**Compared again 2026-11-03 ~07:2x UTC for C2313** (a flood is a high packet rate of small
packets, the operator's decision, option (a)):
- **A watching row of one large-packet stream** draws "Why it is not called a flood: <its mean
  packet against the flood's size> (C2313). A large-packet flood is left to you: it is watched,
  and nothing is proposed. If another source sends to the same host, it is called one attack."
  This is where board S-HR's rate-only "Why it is not called a scan or a flood" stands, as a
  transfer's row does (C2278).
- **The rules table's Flood row** names the small packets and the large-packet exception
  beside its threshold, with the network's size line.
- **The same row draws Rate-limit this source…** (the operator's condition, option (i), the
  same day), before Dismiss. It is drawn disabled, saying why, when the network's response
  policy allows no rate limit for the flood rule, or when the stream names no source to act on.
  Pressing it makes the stream a response awaiting a person, drawn open.

Nothing else moves. Compared by reading the template against board S-HR's opened row (its order:
Detected, Why, What happens next, Proposed, Dismiss) and against the rules table's row, with no
new shot (no shot plants a large-packet stream). Its words are held by
tests/test_sdn_large_packets.py. A deviation: docs/STANDING_APPROVAL_LOG.md, "C2313 built".
Templates sha256 before: `bc0cb2fef244dde93643d613ad4acee2afc3c3528f79059082d5c034f5c33ec1`
(and `5cdaf423ea3d0f5e00664d6ba11d6e4dbe5cecbd90c5fffab2823102d89348fb` between the row's
words and its control, never committed).

**Compared again 2026-11-03 ~02:3x UTC for C2325** (SDN on a network with no controller): the
empty state's notice (board SdnControllers' "No SDN controller is connected to this network")
gains, where another network has a controller, "N other network(s) has one: Open <network>'s
SDN", a link to the same tab there; the Responses tab draws the same notice above its empty
loop. Compared by reading against the board's empty state: words and links in its one notice,
no new control, nothing else moves. Held by tests/test_sdn_v2.py and the v2 walk. Templates
sha256 before: `500b13123b9af7f70a3bc510a958cafb9e469e63fa8594189de1b70dfcd72f26`.

**Compared again 2026-11-02 ~23:5x UTC for C2279** (one attack on one target, PHASE8_PLAN
17.10): an opened incident that is a member of an attack draws "Part of the attack on <target>
with N other incidents (K sources: …), classified once on its first incident; each source's
response is confirmed or dismissed on its own." above its Ingress line; the rows are not
regrouped, and nothing else moves. Compared by reading the template against SdnResponses'
opened incident (its order: the title, Detected, Ingress, Source, the AI box, Proposed, the
actions), no new shot (no shot plants an attack; its words are held by tests/test_sdn_attack.py).
A deviation: docs/STANDING_APPROVAL_LOG.md, "C2279 built". Templates sha256 before:
`2006c910920997b6ab9655bb567382872f5482a26361a6657ad41b05291de260`.

**Compared again 2026-11-02 ~23:2x UTC for C2278** (a transfer is not a flood, PHASE8_PLAN
17.9): a watching row of a flood candidate with a transfer's shape draws "Why it is not called
a flood: <the transfer's words> (C2278). A transfer can still crowd a link: it is watched, and
nothing is proposed." where the board's "Why it is not called a scan or a flood" stands; every
other row is as compared above. Compared by reading the template against board S-HR's opened
row (its order: Detected, Why, What happens next, Proposed, Dismiss), no new shot (no shot
plants a transfer; its words are held by tests/test_sdn_transfer.py). A deviation:
docs/STANDING_APPROVAL_LOG.md, "C2278 built". Templates sha256 before:
`ad1864d30a8937ad5c5d5cb822852cb9be9958d716ec7d4094a2f152d4967c6b`.

**Compared again 2026-11-02 ~22:3x UTC for S-HR (C2238, PHASE8_PLAN 17.8 (b))**, beside
`SdnHighRate.dc.html` (board S-HR, canvas version 183, approved under the Phase 7 mode
2026-11-01) at 1440, 1280 and 390, from the new shot `sdn-responses-watching` (a High packet rate
from 192.0.2.2 on s2's port 2 at 1,240 packets a second, opened, and the IPv6 flood marked as
begun as one). `_sdn_responses.html` changed, region by region:
- **The summary line**: "N awaiting approval · N watching · …" **same**.
- **The counts**: the "1 watching" chip beside the severity counts **same** (a chip, not a
  filter link: a watching row has no severity to filter by).
- **The watching row**: Watching, High packet rate, the source, switches, age, "not asked",
  "nothing: a rate alone names no threat" **same**; above the incidents, as the board draws it.
- **Opened**: the title, the lower-confidence chip, the Detected line, Why it is not called a
  scan or a flood, What happens next, Proposed: nothing, Dismiss with this reason, the Needs
  attention line **same, with deviations**: the words say "flows that name no transport ports"
  where the board says L2-only or Ethernet-only (the rule fires on L3 flows too); "the flood
  rule has not fired for this port or source (its 30 s hold)" where the board says the hold
  "has not yet passed" (a hold can pass with no flood); "began as High packet rate" without
  "30 s earlier" (the gap is not known before the flood fires); "ends", the store's word, where
  the board says "clears"; the how-it-works link is the page's compact icon.
- **The flood row**: "Flood · began as High packet rate" **same**; opened, it adds "Began as High
  packet rate <time> (watching row <id>, joined into this incident when the flood rule fired)",
  where the board says only that its history says so.
- **Detection rules**: the High packet rate row **same**, its "Fires when" as above, and its
  Responses allowed column (the page's, which the board lacks) "none: watched, never answered";
  the scan's Needs is "L4 flows" alone **same**. The board's threshold inputs are board S3's
  form, as before.
- **Phone width**: the page's rows stack inside the card (390 shot), where the board's table
  overflows its box; **better than the board**.
Deviations logged: docs/STANDING_APPROVAL_LOG.md, "Board S-HR built". Templates sha256 before:
`d1cf77a86b143123c759e1298950c63f7062e87099f461ef066ee25da924ea30`.

**Compared again 2026-10-29 ~10:5x UTC for C2021** (an unauthorised flow's severity floor):
`_sdn_responses.html`'s AI box, after "severity <s>", says "(raised in code from the model's
<m>: the flow's effect sets the floor)" when the effect's floor raised the model's rating
(`closed_loop.apply_floor`), the floor's words on its hover; a severity the model gave is drawn
as before. The board draws the severity as the model's alone; the addition is a deviation
(docs/STANDING_APPROVAL_LOG.md, "SDN C2021: a severity the effect's floor raised is said on the
AI box"). Compared by reading the template against the board's AI box, no new shot (the
region stays **later**: no shot plants a classification); the rendered states are held by
tests/test_sdn_classify.py (`test_the_card_says_a_severity_the_floor_raised_and_the_model_s_own`).
Templates sha256 before: `5687d4f59d35ebe382829ad59398ad287c6dbe1fe7974d2d9db0f6ace13dc6e0`.

**Compared again 2026-10-28 ~22:1x UTC for C2002** (a port's detection names its source from
the controller's topology, and a person chooses among the port's hosts when there are
several): `SdnResponses.dc.html` revised in the agent's copy (scratchpad `boards-c2002/`,
based on C1999's revision; not yet on the canvas) with a states section, "Revised 2026-10-28 for
C2002", drawing the opened incident's **Source:** line in four states: one host on the port
(named, no picker), several (the picker, a required select limited to them, beside Preview),
none to act on (why, no Preview) and not read when it fired (the preview looks it up);
signed off under the Phase 7 mode (docs/STANDING_APPROVAL_LOG.md, "SDN C2002: SdnResponses
revised for a port's source and its picker"). Two templates changed: `_sdn_responses.html`
(the Source column's "one of N" and hover, the Source line, the picker in the preview's form,
the preview's form left out with none to act on) and `_sdn_op.html` (the preview's source
followed by how it was found or chosen). Compared by reading each template against the board's
four states, line for line (the words, the order under Ingress / Proposed at, the select's
placeholder and options, no hours field and no Preview with none to act on); the rendered states
are held by tests/test_sdn_source_from_topology.py (`test_the_card_draws_the_picker_one_host_
named_and_none_with_no_preview`), not shot: no `test_sdn` shot plants a port's detection.
Nothing else drawn moves: the incident shots' detections name their sources from their flows, so
no Source line is drawn on them. Row added below: A port's source (C2002). Templates sha256
before (with board FB's Was this right? below already in them):
`799e75516fa9c3b91247ab3bbc658e2ee32bf2eb9d6ae83ccc6c7a65d8989310`.

**Compared again 2026-10-28 (PHASE8_PLAN 16.11 item 1, board FB):** `_sdn_responses.html`
includes Was this right? (`_ai_feedback.html`) at the foot of the AI's classification box, a
person's or the loop's; not under "Couldn't classify". The control is board FB's and is compared
in its own record, docs/fidelity/ai-feedback.md; no region of this record changed, so none was
shot again. Templates sha256 before:
`f5de25c7c12e37b99af4efee2874b3208d4528ebed6eb8667d7b113a68193fe8`.

**Compared again 2026-10-28 ~17:1x UTC for C1999** (incidents: one attack on many switches is
one incident, one response at its ingress, the others seen also): `SdnResponses.dc.html` revised
in the agent's copy of the project folder (the per-response card replaced by "Incidents awaiting
a person": severity chips, a search, a compact table by severity then age, the first incident
opened, and a states section for the ingress not told, a filtered subset and the Needs attention
row; signed off under the Phase 7 mode, docs/STANDING_APPROVAL_LOG.md "SDN C1999: SdnResponses
revised for incidents"). The `sdn-responses` shots (1440, 1280 and 390) now plant two incidents:
the scan from 192.0.2.1 seen on three switches, its ingress s1 told from the topology, opened by
`?incident=<id>`; and a flood from 2001:db8:8::3 on one switch, its ingress not told.
`sdn-responses-held` and `sdn-responses-stale-held` open the same incident before pressing its
Preview, so the held card is drawn inside it. Read beside the board at 1440: the summary, the
card's head and words, the chips and search, the column heads, the row and the opened detail
line for line; one deviation, the opened incident's chip (below). At 390 the header row is
hidden and each row wraps in three lines. The stale and suspended shots are otherwise
unchanged. Rows changed below: Responses' summary, the incidents card and the opened incident
(new), the head, its actions, Needs attention, and the ingress-not-told and subset states (new).

**Compared again 2026-10-28 ~15:0x UTC for C2082** (the every-carried-field check sees the SDN
payload, `g`): one template line changed, `_sdn_responses.html`'s Allowed risk select, whose
options are now drawn from the view's `risks` (`modes.RISKS`, carried and drawn nowhere) instead
of written out; for low and medium the select renders byte for byte as before (checked by
rendering both), so no pixel moves. The payload trims (the stored read without its raw `value`,
the mode as `mode` and `words`, no `remove_why`, no expired count) change no drawing. Every
`test_sdn` shot taken twice, this change and the commit before it (8e01c4b6, through
scripts/nmas-control), and the page shots compared pixel by pixel: the only differences are the
run's own data (the log's and the stamps' times, "read 1 min ago" against "just now", a
response's cookie, wrapping one line in `sdn-responses-held`), and the top bar's AI chip caught
reading or read. No region's verdict changes.

**Compared again 2026-10-28 ~14:1x UTC for C2077** (a lost response a newer response already
answers: `_sdn_view.html` draws it **Answered**, naming the newer response, with no
Re-apply…): `SdnFlows.dc.html` revised in the agent's copy of the project folder (s2 draws a
Not in force line with Re-apply… and an Answered line, the newer response's flow installed and
the lost ones missing in its table, and a builder's note; signed off under the Phase 7 mode,
docs/STANDING_APPROVAL_LOG.md "SDN C2077"), and a new shot beside it, `sdn-flows-answered`
(1440, 1280 and 390): the lab above with the `sdn-flows-lost` data, then the awaiting scan
confirmed by a person as a newer drop of 192.0.2.1, recorded 30 s before the read for 600 s and
in the capture's table, read again. The shot refuses to run unless the page draws the answered
line and no Re-apply… form (its data once drew Not in force: the shot's lost record named no
rule, so nothing could cover it; both records now carry the scan rule, as every response's
does). At 1440 the Answered line sits under Add flow… where the board draws it, the newer
response's id with its operation beside it in faint, its action and source, its clock time in
UTC, "Nothing to re-apply." and the (i); at 390 it wraps above the table. The `sdn-flows-lost`
shots were taken again: unchanged (Not in force with Re-apply…). The page's Needs attention count
fell from 17 to 16 between the two (the lost response's row resolved, C2070; the confirmed scan
no longer awaits). The board draws both lines on s2 of four switches; the capture has one switch
and one lost response, so each state is shot on its own (`sdn-flows-lost`, `sdn-flows-answered`).

**Compared again 2026-10-28 ~09:3x UTC for C2003** (never a frozen page shown as current:
`_sdn_view.html` draws a hidden note under the tabs on every tab, which static/js/nmas_v2.js
`staleNote` shows past the region's promise, the SDN reader's page promise of 90 s, or while the
live channel is down): `SdnResponses.dc.html` revised with a states section drawing the note's
three states (signed off under the Phase 7 mode, docs/STANDING_APPROVAL_LOG.md "SDN C2003"), and
two new shots beside it, `sdn-responses-stale` (1440 and 390: past the promise, nothing open)
and `sdn-responses-stale-held` (1440: a preview open, a redraw held, then past the promise).
Each shot sets the note's stale moment in the past instead of waiting 90 s, so its "Last
updated" reads "just now" where the board reads "2 min ago". The `sdn-responses` shots are
otherwise unchanged (the note is hidden while the page is current); the board's states section
sits below its rules card as a section of states, not a place on the page: the page draws the
note where the section's note says, between the tabs and the summary.

**Compared again 2026-10-28 ~04:0x UTC, the three changes below merged** (C2001's hold and
C2018's re-apply each changed `_sdn_op.html`, compared apart in their own trees): the SDN shots
taken again from the merged tree (`tests/test_board_shots.py -k test_sdn`, 1 passed), and
`sdn-responses-held` (1440) and `sdn-flows-lost` (1440) read: the hold's note with Show it now
above the open preview, the Mode card's stage line and Turn AUTO on drawn disabled with its
reason, and the Not in force line with Re-apply… above s1's flow table, each as its region
below says; nothing else moved.

**Compared again 2026-10-28 ~03:1x UTC for C2001** (an announcement never takes an open card
away: `_sdn_op.html` and `_sdn_flow_form.html` carry `data-holds-live`, which static/js/nmas_v2.js
reads to hold the region's live redraw): a new shot, `sdn-responses-held` (1440 and 390, no
board), the scan's preview opened in place and the SDN announcement dispatched, the redraw held.
The markup otherwise draws nothing new (the attribute is not drawn), so the `sdn-responses` shots
are unchanged; the hold's note is one region, below, a deviation. The operation card itself
stays **later** against SdnResponse (this shot is the first click-driven one, and is not a
region-by-region comparison with that board).

**Compared again 2026-10-28 ~02:5x UTC for C2009** (AUTO only on a network marked lab,
PHASE8_PLAN 17.7's guard; `_sdn_responses.html`'s Mode card): the `sdn-responses` shots again
(1440, 1280 and 390, beside `SdnResponses.dc.html`), Default not marked, and a new shot,
`sdn-responses-suspended` (1440 and 390, no board: AUTO turned on while Default was marked lab,
then Default marked production). The three regions below are what changed; SdnResponses draws
no stage, so each is a deviation. The rest of the Mode card is as its row says.

**Compared again 2026-10-28 ~03:3x UTC for C2018** (a lost response: `_sdn_view.html`'s Not in
force line with Re-apply… on its switch, and `_sdn_op.html`'s re-apply card): Flows shot again
beside `SdnFlows.dc.html` at 1440, 1280 and 390 from the same test's new `sdn-flows-lost` shots.
The data is the lab above, plus a drop of 192.0.2.1 recorded two minutes before the read for 600
s and absent from the captured table, as after a switch restart, read again by the SDN reader.
The `sdn-flows` shots without it were compared too: unchanged, with no line drawn when nothing
is lost. The page's Needs attention count rose by the response's row (16 to 17 in the header).
The re-apply card is drawn by a click, as the other operation cards are: **later**, held by
tests/test_sdn_reapply.py and the v2 walk's provider (tests/v2_context.py `_sdn_reapply`).

**Hashed again 2026-10-27 for PHASE8_PLAN 17.1 S7** (the AI's classification and Classify on an
awaiting response, `_sdn_responses.html`): the two regions below compared by reading the
template against SdnResponses' region list, with no new shot; the classification's region is
**later** until a shot plants one, and Classify is a deviation.

**Hashed again 2026-10-27 for C1968** (the Lab 8 walk's step 10: a response stays awaiting a
person when its threat stops, and a refused classification is said with its call): the two
regions below compared by reading `_sdn_responses.html`'s awaiting card against SdnResponses'
region list, with no new shot; both are additions the board does not draw, each a deviation.

**Compared again 2026-10-27 ~18:0x UTC for C1971** (the loop's log, `_sdn_log.html`, added to
the templates compared, and its include in `_sdn_responses.html`): the loop's region read
against SdnResponses' log, with no new shot; its scroll, Run and Download log are a deviation.

**Hashed again 2026-10-27 ~19:1x UTC for the Lab 8 walk's objective 3.1** (the response policy:
each rule's allowed responses drawn in the rules table and set under it; a response proposed
with no action when the policy could not be read; `_sdn_responses.html`): the two regions below
compared by reading the template against SdnResponses' region list, with no new shot; both are
additions the board does not draw, each a deviation. The loop's log region is unchanged here
(its lines' words changed, not its markup).

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | SDN under OBSERVE, between Topology and Logs | SDN between Topology and Show commands (Show commands, absent on the board, stays before Logs), with its icon | **same** |
| Heading and line | "SDN · Controllers" / "SDN · Flows" and the board's line | the same words, with the page's (i) to the manual's SDN page | **same** |
| Tabs | Controllers, Flows, Responses, each a link | Controllers, Flows and Responses, each a link (S8 to S10 built) | **same** |
| Controllers' summary | "2 controllers · 1 connected · 1 not answering · 4 switches · read 18 s ago" | the same shape, counted from the read ("1 switch"); the age on hover too | **same** |
| A connected card's head | name, connected chip, Test connection, Edit connection, (i) | the same; the (i) is beside Test connection, whose manual section it opens (the rule: "How does this work?" right after its control) | **deviation** (log: SDN S11: the card's info link beside Test connection) |
| Driver, Northbound, Southbound | "Ryu (ofctl_rest) · built", the URL and "TLS not used", the southbound and "informational" | the same | **same** |
| Version | "Ryu 4.34" | "not reported (Ryu's ofctl_rest reports no version)": the driver reads none | **deviation** (log: SDN S11: Version "not reported", Ryu's REST reports none) |
| Cluster role | "standalone (this driver reports no cluster)" | "not reported (this driver reports no cluster)": nothing read says standalone | **deviation** (log: SDN S11: Cluster role "not reported", never assumed standalone) |
| Switches | N connected, each DPID a link, "discovered via this controller, not adopted" | the same; each DPID opens its flows on Flows (`?q=<dpid>`), since the switch's own device page (board 5) is a later step; past 12, "and N more, on Flows" | **deviation** (log: SDN S11: a DPID opens its flows on Flows until the switch's device page) |
| Can | the capability chips, "read topology: not offered by this driver" | the same | **same** |
| Controller's own flows | "cookie 0", the note | the same | **same** |
| Last read | "18 s ago · flows, port stats and meters of 4 switches, 0 failed" | the same shape | **same** |
| Not answering | notice: since when, what failed, reads in a row, "flows below are as last read", "a row on Needs attention until it answers"; Driver; Switches at the last good read | the same, but no Needs attention sentence: that row is a later S11 step and the page does not claim it | **later** S11's Needs attention rows (controller unreachable) |
| Empty state | "No SDN controller is connected to this network. Add one in Settings › Integrations." with the link, nothing else | the same (tests/test_sdn_v2.py `test_the_empty_state_is_the_board_s`, not shot) | **same** |
| Not read yet | not drawn | a connection saved before the reader's next run: "Not read yet. The SDN reader reads every 30 seconds"; the store never read, or its last attempt failed, said above the cards | **deviation** (log: SDN S11: "not read yet" and the reader's own failures said) |
| Flows' summary | "4 switches · 61 flows: 3 Mercury's · 57 the controller's own · 1 unauthorised · 1 of Mercury's missing · 1 meter · lab-controller, read 18 s ago" | the same shape over the capture ("1 switch · 9 flows …"), every controller named | **same** |
| Granularity note | under the summary, once, when it limits a rule | under the summary, per switch whose flows are L2 or L3 only, in closed_loop's words (shot with the capture's L2 flows alone in tests/test_sdn_v2.py, not at 1440) | **same** |
| Filter | text, "Hide the controller's own flows" ticked, Show | the same | **same** |
| Trace a packet… (C2578; sdn-trace.html, artboard A) | beside the search, opening Topology › Path… on Flow tables with the form open | the same, after Show, with its How does this work? | **same** |
| Switches folded | a `<details>` per switch, the wrong ones open, chips (unauthorised, missing, as expected), counts | the same, kept open across redraws (`data-keep`) | **same** |
| A flow row | owner chip, priority, match, actions, packets, timeouts, cookie, Remove… (SdnFlowEdit: Edit… and Remove… on each flow row) | the same columns; the unauthorised row's why under its chip; Remove… on every flow and Edit… on Mercury's, each with its (i), each opening the editor in a row under the flow | **same** |
| Add flow… | SdnFlowEdit: "Add flow… sits on each switch in the list" | Add flow… with its (i) at the top of each opened switch | **same** |
| Mercury's flow | "Mercury's installed as expected", "Its response" link | the same chip and words; no response link (a flow's operation is read on History, not yet linked from its row) | **later** S11 (a flow's response linked from its row) |
| A lost response (C2018) | revised for C2077: s2's "Not in force" line, "Rate-limit the source (192.0.2.40): 1 flow (…0b) and meter 3 missing, 6 min 40 s of its hard timeout left (until 10:46 UTC)", Re-apply… and How does this work? | under Add flow…, one line per response the switch lost before its hard timeout: "Not in force", the response's action and source, what is missing (its flows' cookies, its meter), the time left and the expiry's clock time, then Re-apply… with its (i); the switch opens, as one with something wrong does; at 390 the line wraps above the table | **same** (drawn first as a deviation, log: SDN C2018; the revised board draws it) |
| A lost response answered by a newer one (C2077) | s2's "Answered" line (neutral): the lost response's action and source and what is missing, "and a newer response answers the same threat on this switch: response resp-… (operation sdnop-…), <its action and source>, in force until 10:52 UTC. Nothing to re-apply.", How does this work?; no Re-apply… | the same words and place (shot `sdn-flows-answered` at 1440, 1280 and 390): the badge muted, the operation in faint only when it differs from the response's id, the clock time with its full UTC time on hover, the lost response's operation and expiry on hover of its name; the (i) opens the re-apply section; its flows stay "Mercury's, missing" in the table with the reader's words, as the board's do | **same** |
| A record not installed | "Mercury's, missing" for one expired at its hard timeout, "nothing to do" | expired is "Mercury's, expired", neutral, not counted missing (S5's classify tells expired from missing); missing stays warn | **deviation** (log: SDN S11: an expired flow is "expired", never "missing") |
| The board's departure note | the unauthorised flow a Needs attention row | not drawn: that row is a later S11 step | **later** S11's Needs attention rows (unauthorised flows) |
| Meters | switch, meter, rate, packets in band, owner chip and "its response" | the same columns; the owner from the flows that use the meter; no response link | **same** |
| Phone width | each tab stacked: summary, cards, a flow row a block, tables scrolling in their box | the same; a controller's card keeps its whole list, stacked, where SdnPhone draws a one-line card | **deviation** (log: SDN S11: the phone's controller card keeps its fields) |
| Responses' summary | revised for C1999: "4 awaiting approval · 4 incidents seen on 56 switches · mode HITL · the loop running every 10 s" | "2 awaiting approval · 2 incidents seen on 4 switches · mode HITL · the loop stopped", counted from the shot's two incidents | **same** |
| Incidents awaiting a person (C1999) | a card headed "Incidents awaiting a person" with "by severity, then the longest waiting · one response each, at the switch the source enters by"; severity counts as filter chips, a search and Show; a table: Severity, Rule, Source, Switches, Age, AI verdict, Proposed; rows by severity then age | the same card, words and columns (1440 and 1280); the chips link to the filtered tab and redraw the region; each row a closed `<details>` whose summary is the row, opened by a click; at 390 the header row is hidden and each row wraps, its switch count saying "3 switches" | **same** |
| An incident, opened (C1999) | the detail under its row: "SDN scan from <source>, seen on 50 switches", the detection line "Detected … on <dpid>: …", "Ingress: the ingress switch is <dpid>: the controller's topology (read …) lists <source>'s host on its port 1. Grouped within 60 s, …", "▸ Seen also on 49 other switches · nothing is proposed there; …", the AI box, "Proposed: … on <dpid> …", the actions | the same lines in the same order, opened by `?incident=<id>` (Needs attention's link) in the shot; the seen-also list opens to one line per switch (its DPID, port, controller, time and words) in a box that scrolls; the AI box as the row above | **same** |
| An awaiting response's head | revised for C1999: the incident's title with "seen on N switches" and a red severity chip "high" | the title as the board's; the chip beside it is the detection rule's confidence, labelled "confidence high" (its hover says it is not the threat's severity), since the severity is the row's first column and an unclassified incident has none | **deviation** (log: SDN C1999: the opened incident's chip names the rule's confidence) |
| The AI's classification | an AI-marked box: threat, severity, model and cost, evidence ids, the recommendation | when a classification is kept (S7, 2026-10-27): a box marked AI with the threat or "No threat", its kind and severity, by whom (the loop or a person) and when, the model and cost (the call's id on hover), the reasoning, the recommendation with its catalogue action, the devices named and the evidence ids cited; with none, one line naming who chose the action (the catalogue's default, chosen in code, and why no AI classification was made). Compared by reading the template against the board's list, not yet shot: the harness's `sdn-responses` shot plants no classification | **later** a shot with a kept classification (tests/test_board_shots.py) |
| A severity the effect's floor raised (C2021) | not drawn: the box's severity is the model's | after "severity high", "(raised in code from the model's medium: the flow's effect sets the floor)", the floor's words ("at least high: the flow diverts (its effect, decided in code from the switch's table)") on its hover; nothing added when the model's rating stands. Read from the template and tests/test_sdn_classify.py's rendered card, not shot | **deviation** (log: SDN C2021: a severity the effect's floor raised is said on the AI box) |
| Its actions | revised for C1999: Classify again, "for 600 s", Preview the drop traffic from the source…, a reason field and "Dismiss the incident (50 switches) with this reason", How does this work? | Classify (AI-marked) on its own line, then "for N s", Preview the <action>…, a reason field and "Dismiss the incident (3 switches) with this reason" ("Dismiss with this reason" on an incident of one switch), each with its (i); no control acts on more than its incident | **same** |
| A response whose threat stopped (C1968) | not drawn: the board's response awaits while its threat runs | "Inactive" and "Threat no longer active since <time>: the detection resolved, and this response still awaits your approval or dismissal", under the detection's line; the card otherwise unchanged, its classification kept | **deviation** (log: SDN C1968: a response stays awaiting when its threat stops) |
| A refused classification (C1968) | not drawn | the card's classification line says "AI classification refused: <why>; proposed by the catalogue default, <action> (AI call <id>)" and links "The refused answer in History" (the call) | **deviation** (log: SDN C1968: a refused classification said, its call linked) |
| Classify | not drawn: the board's box is filled by the loop | **Classify** (AI-marked, its hover the task, model and cap; disabled with the reason while AI cannot answer), and "Classify again" once a classification is kept, before Preview, with its (i) | **deviation** (log: SDN S7: a person's Classify on an awaiting response) |
| Mode | HITL and AUTO as radio rows, Reason, Until (a date), Allowed risk, Turn AUTO on… | the mode chip and its words; Reason, For (hours, at most 24), Allowed risk, Turn AUTO on; while on, who, why and until when, and Turn AUTO off | **deviation** (log: SDN S9: AUTO for N hours, not until a date) |
| Mode: the network's stage (C2009) | not drawn: the board's Mode card has no stage | one line under the mode's words: "This network is marked lab.", or "This network is not marked" (or "is marked pilot", "is marked production", or why its stage cannot be read); "AUTO is turned on only on a network marked lab until the AUTO production-readiness gate is complete" with a link to the stage on Settings › Integrations › SDN controllers (shot at 1440, 1280 and 390: not marked; at 1440 and 390: marked production) | **deviation** (log: SDN C2009: the Mode card says the network's stage) |
| Mode: Turn AUTO on off lab (C2009) | "Turn AUTO on…", pressable | on a network not marked lab, drawn disabled with its reason on the control, "Turn AUTO on (Not available: this network is not marked lab)", the server refusing it anyway, naming the stage and the gate; at 390 the button's words and its reason wrap side by side inside the card (shot at 1440, 1280 and 390) | **deviation** (log: SDN C2009: Turn AUTO on drawn disabled on a network not marked lab) |
| Mode: AUTO suspended (C2009) | not drawn | AUTO recorded on while the network is not marked lab: the AUTO chip and its words, the stage line, an amber notice "AUTO is suspended: it is recorded on, and nothing runs unattended while this network is not marked lab; each response awaits a person. Turn AUTO off, or mark the network lab.", and Turn AUTO off (shot `sdn-responses-suspended` at 1440 and 390) | **deviation** (log: SDN C2009: AUTO drawn suspended on a network marked otherwise) |
| A refresh held while a card is open (C2001) | not drawn: the board does not say what a refresh does to an open preview | while a preview, its result or refusal, or the flow editor is open in place, an announcement's redraw of the region is held; the card says at its top "Paused while you review this: newer data is waiting." with **Show it now** (busy on itself, "Showing…"; it closes the card and redraws, sending nothing); a typed reason holds as every page's field does (C459). Shot `sdn-responses-held` at 1440 and 390 | **deviation** (log: SDN C2001: a refresh held while an operation card is open) |
| Not current (C2003) | the states section: between the tabs and the summary, an amber notice "Last updated 2 min ago: no update has arrived in the 90 s it promises, so this page may be out of date." with Reload; "live updates stopped" in place of the cause while the channel is down; with a card open, no Reload and "a reload would close the card open below. Send or close it first.", or "newer data is waiting, held for the card open below" when a redraw was held; nothing while current | the same words and places on every SDN tab (shot on Responses: `sdn-responses-stale` at 1440 and 390, Reload wrapping under the words at 390; `sdn-responses-stale-held` at 1440, the note above the summary and the card's own "Paused while you review this" note kept); Reload a link to the tab's own page, Flows' filter kept | **same** |
| The loop | its state chip, "every 10 s · detect, classify, respond", Stop, the log | the same; stopped, "every N s" and Start | **same** |
| The loop's log | the latest lines, newest first, each line's time, step and words | one run whole (from its start line), newest first, in a box that scrolls; above it **Run** (each run by its job id, start time in UTC and line count) and **Download log** (the run as text); a line naming the lines drawn of the run's and its first and last times; past 2,000 lines the newest 2,000, said (C1971) | **deviation** (log: SDN C1971: the loop's log scrolls over the whole run, with Run and Download log) |
| Detection rules | the table with each threshold editable, Save thresholds…, the timeout line | the same table read-only, and the timeout line with the ceiling; no Save thresholds… | **later** S8's thresholds edited on this tab (until then written by `list_settings.write`) |
| Response policy (objective 3.1) | not drawn: the board's response takes the catalogue's action for its rule | a "Responses allowed" column in the rules table (each rule's allowed actions, its default marked), and under it **Response policy**: where it comes from, per rule a default select and a tick per other action that answers the rule, **Save the response policy** with its (i), refusals said beside it; a red notice when the policy cannot be read | **deviation** (log: SDN 3.1: each rule's allowed responses on the rules card) |
| A response with no action proposed (objective 3.1) | not drawn | "No action is proposed: the network's response policy could not be read when this was detected", in place of the Proposed line | **deviation** (log: SDN 3.1: a response proposed with no action when the policy is unreadable) |
| Needs attention | revised for C1999: the states section's row, one per incident: "SDN scan from 192.0.2.31 on Default, seen on 50 switches, awaits a person.", its incident, severity and ingress, and Open the incident | built (`attention.sdn_responses_source`) in the same words, DANGER when classified high or critical; compared by reading the row tests/test_sdn_responses_attention.py renders against the board's, not shot (no board-shot test renders Needs attention with SDN data) | **later** a landing shot with an SDN incident (tests/test_board_shots.py) |
| A port's source (C2002) | revised for C2002: the states section's four: "Source: 192.0.2.2, from the controller's topology: the one host on port 2, …" with no picker; "Source: not named: the controller's topology lists 2 hosts on port 2 (…). Choose which one beside Preview below; the preview refuses any other." with a required select "one of the 2 hosts on port 2…" listing exactly them, the Source column "one of 2"; "No source to act on: …" (amber) with no Preview and no hours field; "Source: not named: the controller's topology could not be read (…); the preview looks up the host on port 2 in the controller's topology now." | the same words, places and controls, compared by reading `_sdn_responses.html` against the board (the rendered page held by tests/test_sdn_source_from_topology.py); the preview card's source followed by "(chosen from the 2 hosts …)" or "(from the controller's topology: …)", as the board's note on state 2 draws it | **later** a shot of an opened port's detection in each state (tests/test_board_shots.py plants none) |
| Ingress not told, a filtered subset (C1999) | the states section: "Proposed at: the ingress switch cannot be told: …; proposed at <dpid>, the switch that saw it first."; "Showing 1 of 4 incidents, severity high. Show all" | the same words (`incidents.ingress`; the template's subset line); the shot's flood is an incident whose ingress was not told, drawn closed; neither state is shot opened or filtered | **later** shots of an opened ingress-not-told incident and a filtered table |
| The response's preview and result (SdnResponse) | the card in place: what it does, exactly these requests, what will not happen, Verify, checks, bound hash, Send N requests | drawn in place by a click: what it does, the detection and its checked parameters, exactly these requests, what will not happen, the warnings, Verify (its limit said), the bound hash, Send N requests; the result: outcome, what was sent, Verify, counters, rollback, the record | **later** a click-driven shot (the harness shoots pages) |
| The flow editor (SdnFlowEdit) | the form, the prerequisite refusal, the preview, Edit's and Remove's words, Explain this flow table (AI) | the form, the refusal naming the field, the preview card; Edit's and Remove's words; no Explain (S19, after cost safety) | **later** a click-driven shot; Explain is S19 |
| Responses at phone width | stacked | the card's fields and buttons wrap inside it (390 shot) | **same** |
