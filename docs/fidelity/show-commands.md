# Fidelity: Show commands, the pick card (C548 boards B, F and C582)

Show commands' page as built, compared region by region with its approved boards (C650's step),
after the operator's walk W1 (2026-10-16, step 5: s1 and r1 filtered by name, then Test the
logging path). Read from shots of the boards and the page side by side, in the same headless
Firefox (`tests/test_board_shots.py::test_show_commands_pick`), on Show commands' lab
(tests/test_show_commands.py: test_device_v2's lab, r3 IOS-XE and r9 IOS, the sessions faked at
the connection seam answering from real captures, and board F's Loki stand-in): three commands
typed, the third `show tech-support`; two saved sets committed through the real code; Loki
configured, so Test the logging path is on; and board C582's two states, a `send log 2` line
typed without a reason, then its reason given beside a second level-2 line without TEST. The lab
has two devices and no roles, platforms or sites in its inventory where the boards draw nine.
Read beside them: the operator's W1 capture 06 (Default's nine devices filtered to "2 devices of
9, as filtered", s1 and r1 as chips, no saved set, Test the logging path on 2 devices, and the
network's recent runs), at about half desktop width.

Boards, on the NMAS v2 mockups canvas, page "C547/C548: Ask the device and Show commands"
(approved 2026-10-08, signed off in tests/signed_off_screens.py: "C548 boards B and E (canvas
page 'reads'), signed off 2026-10-08 with NSOT_READS.md and R1 to R5; named Show commands under
OBSERVE (R4)"): `ReadsFleetPick.dc.html` (board B, 1440: pick devices and commands, or a saved
set; its region 7, the running run, is the run's page, compared in show-commands-run.md),
`ReadsLogPath.dc.html` (board F, 1440: its region 6f, the card's footer gaining Test the logging
path; 7f to 8g are the run's page), `ReadsReasonC582.dc.html` (C582, 1440: the reason field;
its region 3 is the device page's Ask tab and region 4 the run's record, compared in
show-commands-run.md). `ReadsPhone.dc.html` (board E, 390) and `ReadsLogPathPhone.dc.html`
(board G, 390) draw no part of this page (the device's Ask tab, the run's result, C2 and F at
phone width), so the page at 390 is compared with no board.
Shots: `show-commands` (board B and the page at 1440 and 1280; the page at 390 and its first
screen), `show-commands-logpath` (board F and the page at 1440), `show-commands-reason` (board
C582 and the page at 1440 and 390), `show-commands-reason-given` (the page at 1440).
Compared 2026-10-16.
Templates compared: templates/v2/show_commands.html, templates/v2/_sc_pick.html, templates/v2/_sc_devices.html, templates/v2/_sc_check.html, templates/v2/_sc_reason.html, templates/v2/_sc_run.html
Templates sha256: `f86d1a8d93e9b401619b81286d40c96218ed014c83621fe39a016cfcdee95b3f`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | board B: "Reads" under OBSERVE; boards F and C582: "Show commands" | "Show commands" under OBSERVE, after Topology, current | **same** (as boards F and C582, R4's name) |
| Header | "Reads" (B) or "Show commands" (F, C582), its line, the network at the right | "Show commands" with the (i), "Default: ask many devices the same read-only commands … Nothing here changes a device." (capture 06); the network in the top bar | **same** |
| The card's head | "A new read", How does this work? at its right | "A new read"; the card's help is a link beside Run reading "How does show-commands work?", the slug in place of words (capture 06; C901) | **deviation** (log: Show commands: the How link reads How does show-commands work? (C901)) |
| Devices: filters | Name, Role, Platform, Site | the same four, each redrawing the devices alone as it changes ("s1, r1" typed in Name, capture 06) | **same** |
| Devices: the count and names | "4 devices · switch, any platform" (B), "5 devices of 9, as filtered" (F), the names as chips | "2 devices of 9, as filtered", s1 and r1 as chips (capture 06) | **same** |
| Devices: who is not answering | "A device not answering at the last reachability read is named before the run, and is asked anyway." | not drawn: no reachability read reaches the card; the line under the devices says each device is held while read, 6 at once, one held by another operation skipped and named | **deviation** (log: Show commands: a device not answering is not named before the run (a defect, register C650 follow-up)) |
| Commands: a row | the command, its verdict as a chip ("read-only", "not across devices", "needs a reason"), Remove | the same for a read ("read-only") and a send log at 0 to 3 ("needs a reason", "allowed, with your reason") | **same** |
| Commands: a refused row | the chip "not across devices" (or "not a test") beside the field, and the reason as a sentence under it | the chip carries its own word and the whole reason, "refused: Refused: `show tech-support` on 2 devices; …" and "not a test: `…`: REFUSED: …", wrapping under the field; a heavy command is also named in a notice under the commands | **deviation** (log: Show commands: a refused line's verdict repeats its word and carries the whole reason (a defect, register C650 follow-up)) |
| Add a command | under the rows | the same, up to ten | **same** |
| The reason field (C582) | under the first level 0 to 3 line: "Why send at level 2? Recorded with the run, at least three words", the level's words, TEST said | the same words and rule, one field under all the command rows, the level's words beside it; typing it redraws the verdicts and Run, never itself | **deviation** (log: Show commands: one reason field under every command row) |
| Or a saved set: the table | Set, Commands, Saved by (who, when), Use | Set (its description under it), Commands, Use; who saved a set and when are not drawn; "None saved in Default yet." on the host (capture 06) | **deviation** (log: Show commands: a saved set does not say who saved it or when (a defect, register C650 follow-up)) |
| Save as a set… | a button in the card's footer | "Save these commands as a set…" opening in place under the saved sets: Name, Description, Save the set, and where it is committed | **deviation** (log: Show commands: Save as a set opens in place under the saved sets) |
| The footer's words | "Every command must pass before any device is asked … Recorded in History as yours." (with the reason, C582); F: what Test the logging path sends and watches | the same sentences in one paragraph: the level read from each golden (C587) and Loki watched for 30 s per device (capture 06) | **same** |
| Test the logging path (F) | a button on the card's devices, its (i), beside Run; off with Loki not configured, why on hover | the same: "Test the logging path on 2 devices" and its (i) beside "Run on 2 devices" (capture 06); off with its why on hover (tests/test_show_commands.py `test_the_button_is_off_and_says_why_without_loki`) | **same** |
| Run | "Run on N devices", primary; off until every command passes | the same | **same** |
| Recent runs | not drawn on board B (board D draws runs as History's rows) | a card under the pick: When (each a link to its run), Who, Commands, Devices, Outcome | **deviation** (log: Show commands: the network's recent runs under the pick) |
| Recent runs at half width | not drawn | at the operator's half desktop width the narrow cells break mid-word: the person's address over two lines, "1 answered" and "2 min ago" wrapped (capture 06; C901's "Op/en") | **deviation** (log: Show commands: Recent runs' narrow cells break mid-word at half width (C901)) |
| Running (board B's region 7) | the run's progress | the run's own page | **same** (compared in show-commands-run.md) |
| Phone width | no board draws this page at 390 | the filters wrap two to a row, each command's verdict and Remove under its field, the footer's buttons stacked | **same** |
