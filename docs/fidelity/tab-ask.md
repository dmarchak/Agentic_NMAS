# Fidelity: the device page's Ask the device tab (C547) and Tier 2's card

Ask the device as built, compared region by region with its approved boards (C650's step), after
the operator's walk W1 (2026-10-16, steps 2 to 4 and 19, on s1). Read from shots of the boards
and the page side by side, in the same headless Firefox (`tests/test_board_shots.py::test_tab_ask`),
on `tests/test_device_v2.py`'s lab (r3, with r2's real configuration as its committed golden),
the device faked at the connection seam and answering from r3's real captures
(`tests/fixtures/operational/r3__show_ip_ospf_neighbor.txt`; the earlier answer the comparison
reads is that capture with one neighbour's state edited, FULL/BDR to 2WAY/DROTHER), each read run
through the real reads engine, its hold and its record; the held state by a deploy holding r3
(`device_ops.hold`). Tier 2's card on `tests/test_privileged.py`'s fixture: r2's measured
`show interfaces` before and after `clear counters`, the measured prompt, and r2's
`show debugging` with nothing on. Read beside them: the operator's W1 captures 02 (the tab idle,
its label "A read or diagnostic command (Tier 1)"), 03 and 04 (two answers in place), 21 and 22
(the long and short forms of one command, Compare offered only for the short), and 23 (the
comparison, Gi0/1 − blank and + "spare port"), all at about half desktop width.

Boards, all on the "NMAS v2 mockups" canvas, page "C547/C548: Ask the device and Show commands":
`ReadsAsk.dc.html` (board A, 1440: pick or type, refused as typed, the answer in place, compare,
the device held) and `ReadsPhone.dc.html` (board E, 390), approved 2026-10-08;
`ReadsReasonC582.dc.html` (C582, its part 3 is this tab's reason field), approved 2026-10-08;
`Tier2Privileged.dc.html` (T2-A to T2-D, Run a privileged command…), approved 2026-10-08 and built
but the soft BGP refresh. `Tier2Phone.dc.html` is a draft, never signed off: not compared.
The fleet result on `ReadsPhone.dc.html` and parts 1, 2 and 4 of C582's board are Show commands'
(their own records), not this tab.
Shots: `tab-ask-board-1440`, `-1280` beside `tab-ask-page-1440`, `-1280` (idle);
`tab-ask-refused-page-1440`; `tab-ask-answer-board-390` (E) beside `tab-ask-answer-page-1440`,
`-390`, `-390-first`; `tab-ask-compare-page-1440`, `-390`; `tab-ask-held-page-1440`;
`tab-ask-reason-board-1440` beside `tab-ask-reason-page-1440`, `-390`;
`tab-ask-t2-choose-board-1440`, `-390` beside `tab-ask-t2-choose-page-1440`, `-390`, then
`tab-ask-t2-preview-page-*`, `tab-ask-t2-result-page-*` and `tab-ask-t2-nothing-page-1440`.
Compared 2026-10-16.
Templates compared: templates/v2/_ask.html, templates/v2/_ask_check.html, templates/v2/_ask_reason.html, templates/v2/_privileged.html
Templates sha256: `c426a916faa1e2b5045208103d630a2761263f6045f436b7a5d2339e9b8ac3f7`

Compared again 2026-10-17 (C1023) after Run (`_ask_check.html`) became busy on itself from the
press until the run's card draws ("Starting the read…"); the card's own running state, "Reading…"
and disabled, is unchanged. At rest the page draws the same words. Compared by the template and
the page the tests draw (tests/test_v2_busy_on_itself.py, tests/test_show_commands.py), not a
new shot; no region's verdict changed.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| The card's head | "Ask r2", How does this work? at the right | "Ask s1" (capture 02) with the (i) at the right, as every v2 card | **same** |
| The help beside Run | none | "How does show-commands work?": the manual's slug drawn as the operation's words (the `how()` macro's `op` given a slug, where every other card gives words; captures 02 to 04; C901) | **deviation** (log: Ask the device: the help beside Run names a slug (C901)) |
| The command box | "A read-only command", Run disabled until a command passes | "A read or diagnostic command (Tier 1)" (C588: Tier 1 also takes `send log`; capture 02, as the walk's step 2 quoted it), the placeholder "show ip route", checked as typed, Run off until it passes, "read-only" beside it (capture 03) | **deviation** (log: Ask the device: the box named for Tier 1) |
| Saved sets | Routing health (4), VRRP and MAC (3), Time (2) | the network's committed sets, each opening Show commands with its commands on this device; neither the lab nor the host holds one, so the row is not drawn (compared by the template) | **same** |
| Common reads | "Common on IOS-XE", eight commands | "Common reads", the same eight, one list for every platform (`reads.COMMON`; capture 02 on an IOS switch) | **deviation** (log: Ask the device: one list of common reads) |
| Recent on r2 | the device's recent commands as chips to pick | not drawn: the recent reads are the table below, each run re-opened by Open | **deviation** (log: Ask the device: the answer's actions and the recent chips are not drawn (a defect, register C650 follow-up)) |
| Refused as typed | the box red; "Not a read: \| redirect writes …" in a red box under it, the filters allowed, "Nothing was sent" | the box red; under Run, "Refused:" then the command policy's own refusal (it begins "REFUSED:" again), the filters allowed, "Nothing will be sent"; Run disabled | **deviation** (log: Ask the device: the refusal in the command policy's words) |
| The answer in place | the answer in a scrolling box; "Read just now · 0.9 s", answered | the same: "just now · 0.69 s", answered (capture 03), who on hover | **same** |
| The answer's actions | Compare with the last answer, Save as a set…, Ask the same of other devices… | Compare with the last answer only, and only when the same text was asked before: `show interface description` offered none where `show int description` did (captures 21 and 22; C889, the command not normalised) | **deviation** (log: Ask the device: the answer's actions and the recent chips are not drawn (a defect, register C650 follow-up)) |
| Recent reads | When, Who, Command, Outcome, Open; "(6 this week)" | the same columns, "(5)", "(10, the latest 10)" when cut (captures 02 and 23); open once a run is shown | **same** |
| Recent reads at half width | the table at the desk's width | at the operator's half desktop width the Open column is too narrow and "Open" breaks to "Op" over "en" on every row, the person's address breaking over two lines (captures 02, 03, 21, 23; C901) | **deviation** (log: Ask the device: Open breaks as Op/en at half width (C901)) |
| Compare | "show vrrp brief on r2: now against 2 h ago", Close, "2 lines changed. The read 2 h ago was <operator>'s.", the lines marked − and + | the heading ("show int description: now against 42 min ago", capture 23) and the marked lines (context kept around them), who on hover; no Close and no count of lines changed | **deviation** (log: Ask the device: the comparison has no Close and no count (a defect, register C650 follow-up)) |
| The device held | "Not read: r2 is being deployed to by <person>, since 02:11 UTC …", Open the deploy; the card says when the deploy ends | the notice in the hold's words (who, the operation, since, the process); no Open the deploy, and the card is not redrawn when the hold ends | **deviation** (log: Ask the device: the held notice opens nothing and is not redrawn (a defect, register C650 follow-up)) |
| C582's reason field | under the box, a full-width field under its label; "Level 1 is alert: it can fire alert rules and page someone"; Ask off until given | under the box, the label and a narrow field on one line; "Level 1 is alerts (1) …", the TEST sentence; Run off until three words | **deviation** (log: Ask the device: the reason field drawn narrow beside its label (a defect, register C650 follow-up)) |
| Phone (E) | the box, the common reads, Run full width, the answer scrolling sideways in its box | the box full width, Run beside its help, the answer scrolling in its box; the recent reads table squeezed, Open broken letter by letter | **deviation** (log: Ask the device: Open breaks as Op/en at half width (C901)) |
| T2-A, the card | five commands, each with its words; On: r2's interfaces; Preview | four offered; `clear ip bgp <peer> soft` drawn disabled, "not measured yet"; the interface list starts at "(none: for clear logging and undebug all)" and never offers Loopback0, the management interface (C583); Cancel in the head | **deviation** (log: Ask the device T2: the soft BGP refresh not offered and the management interface never offered) |
| T2-B, the preview | Read now (the counter lines), What it affects, Rollback, Reason, the binding sentence, Cancel and "Clear Gi2's counters on r2" | the whole read (masked), What it affects, Rollback, The device asks (the measured prompt and its answer), Reason, "Bound to plan <hash> …", one button naming the command | **deviation** (log: Ask the device T2: the device's question shown, the button names the command) |
| T2-C, the result | done, verified; Before and after (the counter lines); Recorded | done, verified; What happened (sent, answered, verified in words); Before (kept) and After as whole reads; Recorded with who, when and the reason; Close | **deviation** (log: Ask the device T2: the result says what happened) |
| T2-D, changes nothing | Read now, "This changes nothing: no debug is on on r2", one decision, one button: Cancel, Run undebug all anyway (records it) | the same, and Rollback and a Reason, as on every Tier 2 run | **deviation** (log: Ask the device T2: a reason on every run) |
