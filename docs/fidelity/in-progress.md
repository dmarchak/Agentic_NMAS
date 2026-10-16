# Fidelity: the top bar's In progress chip (C537, 2026-10-16)

The chip in every v2 page's top bar and its list, as built, compared region by region with its
boards. Boards: on the second canvas ("NMAS v2 mockups", v66), page "C537/C538: In progress,
Finish the job, the top bar": `TopBarDesktop.dc.html` (board A, 1440: idle, running, finished
unopened, the command box) and `TopBarPhone.dc.html` (board B, the bar at 390 px, drawn on a
1440 board), drawn and counted as signed off by the agent under the Phase 7 mode (2026-10-16,
docs/STANDING_APPROVAL_LOG.md). The device page's half of the same page (board C, `Reattach`) is
compared in `device.md`. Shots: tests/test_board_shots.py `test_in_progress` (`in-progress-idle`,
`in-progress-running` and `in-progress-finished` at 1440 and 390, beside `in-progress-board` and
`in-progress-phone-board`), on test_persist_screen's lab with the rotate tests' fakes
(tests/test_device_rotate_v2.py's `rot`): a real rotation of r2 confirmed on its page, held at
its first step while the person is on Devices, then let go. The fixtures hold one rotation, not
the boards' rotation and deploy, so one row runs and one finishes; the chip at its widest (two
running, one failed, one done) is measured beside every other item of the bar at 320 to 1280 px
by tests/test_v2_layout_in_a_browser.py (`test_the_in_progress_chip_fits_and_its_list_opens_on_the_screen`).
Compared 2026-10-16.
Templates compared: templates/v2/_in_progress.html, templates/v2/base.html
Templates sha256: `0ce6a41bdebd944b5ae7d222bb3056a3bd741d8a27e9f551a1c5d0dfcf26208e`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Nothing running, nothing unopened (A1, B1) | no chip | no chip: the slot is empty and takes no room | **same** |
| The chip while operations run (A2, B2) | a blue pill with a dot, "2 running"; at phone width the dot and the count | the same, the count of rows below it; its words in its label and on hover at phone width | **same** |
| Running now (A2, B2) | "Running now · 2", a row each: device · operation, the step in the stepper's own words ("step 6 of 6"), who ("you"), since when | the same: one row per operation (C217, the job's own row folded into its device's), the step from the card's stepper where it has one, else the hold's own words; its network after the time; "no progress: may be stuck" when the hold has not moved for ten minutes | **same** |
| Open its card (A2, B2) | on every row, opening its card where it runs | on every device's row: it opens the device's page, which reopens the card (board C); a device held by an operation no card reopens says "Open <device>" | **same** |
| An operation that holds no device (not drawn) | every row has its card | a NetBox preview or a Save of many devices is listed with its words and no button | **deviation** (log: C537: an operation that holds no device is listed without a button) |
| Finished, not opened yet (A2, A3, B3) | "Finished, not opened yet · N"; with none, "An operation that finishes while you are elsewhere stays here, with its outcome, until you open it." | the same words | **same** |
| A finished row (A3, B3) | its outcome chip ("rolled back", "persisted"), device · operation, what happened at when · who, Open the result | its outcome in its card's own words and colour ("rotated and persisted"), device · operation, done or failed at when · who · network, Open the result opening the device's page on the result | **same** |
| The chip's outcome (A3, B3) | red cross and count failed, green tick and count done, red wins | the same; a partial is amber and counted as partial (never green over a partial); a network whose holds could not be read is red and counted unread | **same** |
| The chip at phone width with more than one kind (B3) | "✕ 1 · ✓ 1" | the mark and count that leads (red, then amber, then running, then green); the rest in its list and its label | **deviation** (log: C537: at phone width the chip draws the mark that leads) |
| To finish (A3, B3, C538) | "2 to finish" on the chip; To finish · 2, each item with its button | not drawn: Finish the job is C538's | **later** |
| The list's foot (A2, A3, B2) | All recent operations (History); "Default · and 1 running in a network you cannot see"; Mark all opened | All recent operations (History) and How does this work? (the manual's What is running now) | **deviation** (log: C537: no Mark all opened) |
| Operations in a network you cannot see (A2's decision) | counted, never named | every person sees every network today, so the list is every network's and none is counted as unseen | **deviation** (log: C537: every network is visible to every person today) |
| Where the list opens (A2, A3, B2, B3) | under the chip, right of the bar; at phone width the screen's width under the bar | under the chip, its right edge at the chip's; below 860 px the screen's width under the bar | **same** |
| The go-to box at desktop width (A1 to A3) | the wide "Go to device by name" box replaced by "⌕ Go to… Ctrl K" | today's wide box stays | **deviation** (log: C537: the wide go-to box stays at desktop width) |
| The go-to box at phone width (B1 to B4) | the ⌕ button after the chip, opening the command box full width | the ⌕ button before the chip, opening today's go-to box the screen's width under the bar | **deviation** (log: C537: at phone width the go-to box is its button) |
| The command box (A4, B4) | devices and pages by name across your networks, ↑ ↓ Enter Esc, Stage 8's agent row hidden | not built | **later** |
| The network picker at phone width (B5) | unchanged | unchanged | **same** |
| How it stays current (A2's words) | not drawn | read on load and again when a job starts or ends, a result is opened, a device is released or a step is reached, over the live connection; never on a timer | **same** |
| A read that failed (not drawn) | not drawn | "Could not ask which operations are running … This is not the same as none running", the chip red | **same** |
