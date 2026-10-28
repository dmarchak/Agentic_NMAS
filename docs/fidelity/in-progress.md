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
Compared again 2026-10-16 for W2's A1, by reading `base.html`'s change against the regions
below, not from new shots: the top bar's network label is now its own element
(`templates/v2/_network_label.html`, the same `<strong>` and the same words; it reads
**deleted** in the warning colour once the page's network is deleted), and the picker's request
also sends the network the label names. No region of the chip, its list or the bar's layout
moves, so every verdict below stands; the picker at phone width (B5) is still unchanged.
Compared again 2026-10-23 (the one-decision out-of-band onboarding, board D of
`docs/boards/oob-onboarding.html`), by reading `_in_progress.html`'s change against the regions
below and tests/test_oob_onboard_v2.py, not from new shots: a console run's row (an out-of-band
onboarding, a console survey or kick-start) opens the run's own page, "Open its stepper", since
a device being onboarded has no page until its Create; its step is its run's stepper's own
words. Every other row and region is unchanged.
Compared again 2026-10-27 (PHASE8_PLAN 17.1 S11), by reading `base.html`'s change against the
regions below, not from new shots: the sidebar gains SDN under OBSERVE, after Topology (board
SdnControllers' sidebar; tests/test_v2_pages.py pins the order). Nothing in the top bar, the
chip or its list moves, so every verdict below stands.
Compared again 2026-10-28 (C1843, boards AI1 and AI2; docs/fidelity/ai-spend.md), by reading
`base.html`'s change against the regions below and from tests/test_v2_layout_in_a_browser.py's
measurements, not from new shots: the bar gains the AI chip and its spend panel after the
integrations strip and before Live. To keep every working item on the screen beside it, the
chip's words give way to its marks and counts up to 1100 px (they did under 860 px), its words
on hover and in its label; one row below records it. Nothing else in the chip or its list moves.
Compared again 2026-10-28 ~11:2x UTC, for base.html alone: the AI chip's mark renamed
`ai-chip-mark` (the same rules; `ai-mark` is the AI control mark's, and the two had collided)
and its details given `data-keep="ai-spend"` (C472's rule). The shots taken again
(in-progress-*, ai-chip-*), nothing in In progress moved.
Templates compared: templates/v2/_in_progress.html, templates/v2/base.html
Templates sha256: `5ed96ad348b4c6d7f319f90d6f982562d811dfa23a6d83772e46ae0fa364d263`
Hash rewritten 2026-10-23 at the Phase B merge: the run page's links name their network as `?list=` (they said `?list_name=`), and the run page's Devices link takes the page's network; no drawn text, region or control moved, every verdict stands.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Nothing running, nothing unopened (A1, B1) | no chip | no chip: the slot is empty and takes no room | **same** |
| The chip while operations run (A2, B2) | a blue pill with a dot, "2 running"; at phone width the dot and the count | the same, the count of rows below it; its words in its label and on hover at phone width | **same** |
| Running now (A2, B2) | "Running now · 2", a row each: device · operation, the step in the stepper's own words ("step 6 of 6"), who ("you"), since when | the same: one row per operation (C217, the job's own row folded into its device's), the step from the card's stepper where it has one, else the hold's own words; its network after the time; "no progress: may be stuck" when the hold has not moved for ten minutes | **same** |
| Open its card (A2, B2) | on every row, opening its card where it runs | on every device's row: it opens the device's page, which reopens the card (board C); a device held by an operation no card reopens says "Open <device>" | **same** |
| A console run's row (oob board D) | not drawn on canvas v66; board D: "Open its stepper" | "Open its stepper", opening the run's own page; its step in its run's stepper's words ("Copy the bootstrap: … · step 7 of 10") | **deviation** (log: A console run's In progress row opens the run's page) |
| An operation that holds no device (not drawn) | every row has its card | a NetBox preview or a Save of many devices is listed with its words and no button | **deviation** (log: C537: an operation that holds no device is listed without a button) |
| Finished, not opened yet (A2, A3, B3) | "Finished, not opened yet · N"; with none, "An operation that finishes while you are elsewhere stays here, with its outcome, until you open it." | the same words | **same** |
| A finished row (A3, B3) | its outcome chip ("rolled back", "persisted"), device · operation, what happened at when · who, Open the result | its outcome in its card's own words and colour ("rotated and persisted"), device · operation, done or failed at when · who · network, Open the result opening the device's page on the result | **same** |
| The chip's outcome (A3, B3) | red cross and count failed, green tick and count done, red wins | the same; a partial is amber and counted as partial (never green over a partial); a network whose holds could not be read is red and counted unread | **same** |
| The chip from 861 to 1100 px, beside the AI chip (not drawn) | board A draws the words at 1440 | its marks and counts, as under 860 px, its words on hover and in its label | **deviation** (log: AI chip built: compact at 1100 px and under, the mark alone at 400 px and under) |
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
