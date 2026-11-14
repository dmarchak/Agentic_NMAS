# Fidelity: Credentials › Profiles › Read-only account on the devices (board R)

**Provisional, operator review pending** (the operator, 2026-11-13: "GUI boards: approved
provisionally for initial implementation and testing (board R, …)"). The card as built,
compared region by region with board R (`~/Documents/nmas-reports/boards/board-r-read-only-account.html`,
frames R1 to R7, drawn 2026-11-13), by the templates against the board's frames and the pages
tests/test_read_account_fleet.py draws (the held coverage on r2's lab, Add's preview, the
rollout's preview and run), not from board shots: the board is not on the mockups canvas, so
tests/test_board_shots.py has no file for it yet. A shot comparison at 1440, 1280 and 390 is the
operator's review's.
Templates compared: templates/v2/_read_account_fleet.html, templates/v2/_read_account_coverage.html, templates/v2/_read_account_op.html
Templates sha256: `d3c622656118f7a4e6a24c5f96c65e0caa82b84fa3c77da0441451f7cd261f19`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| R1: Where it is | a region "On the devices" inside the Read-only account card | its own card, "Read-only account on the devices", directly below the Read-only account card | **deviation** (log: Board R built: the coverage is its own card) |
| R1: The summary | "12 devices:" then a badge per state, then the probe's counts, "checked 40 s ago" | the same: the total, a badge per state with its count, the probe's counts, "checked" with the held value's age | **same** |
| R1: Filter and search | Search devices, Network, Platform, Result | the same four, and Search; a filtered view says "a subset: N match" | **same** |
| R1: Add the read-only account… | primary, How does this work? beside it | the same | **same** |
| R1: Roll it out… | only under an Add's result (R4) | also on the coverage's bar beside Add | **deviation** (log: Board R built: Roll it out… beside Add) |
| R1: The groups | by state, the states to act on first, "hold it at level 3" open | by state in the same order, each closed until opened | **deviation** (log: Board R built: every coverage group closed at rest) |
| R1: A device's row | Device, Network, Platform, Intent says, Device holds, Level, Last probe, Result (the probe's result) | the same columns; the probe's result a badge in Last probe, Result the account's state with why and the profile | **deviation** (log: Board R built: the probe's result beside its time) |
| R1b: 900 devices | every group closed; an open group lists its first rows and says how many are shown | the same, 50 rows, "50 of N shown: search or filter to narrow" | **same** |
| R2: Pick | All not yet (N), a network's and a platform's selects, Clear, a search, devices by network, a reason, Preview the intent change, Cancel | All not yet (N), a button per network and per platform, Clear, devices by network (a group open up to 50), the reason, Preview the intent change (busy on itself), Cancel; no search inside the picker | **deviation** (log: Board R built: Add's quick ticks are buttons) |
| R3: The preview | summary; per platform group the intent change and the lines with each line's effect, masked; the ping choice's notice; refused by name; reason and hash; Add to N devices' intent, Back, Cancel | the same | **same** |
| R4: The result and the rollout's form | the commit per network, nothing sent, recorded; Network, Canary, Wave size, Preview the rollout | the same, and each device to deploy ticked, untickable | **same** |
| R4: The rollout's preview | planned when, its hash; the summary; the canary, waves and the management-path device last with its warning; each program on expand; lines besides the account's named; send nothing; Deploy the canary, Cancel | the same; "Planned in N s" in place of "planned N s ago"; when the Topology read cannot tell, a notice says so and holds no device back | **same** |
| R5: Paused after the canary | each wave's devices and state in place, a receipt link per device, "Go on: wave 2 (1 device)" | the rollout engine (the operator, 2026-11-14): no pause unless the plan chose one; with it, "Continue the rollout", then every wave by itself; while running, the wave it is on and each device done so far | **deviation** (log: Board R's R10: the rollout engine replaces Go on and the carrier's confirm) |
| R5 to R7: Receipts | a receipt link beside each device | the card names each device's History | **deviation** (log: Board R built: no receipt link per device on the run) |
| R6: The management-path device | its warning, naming how many devices Mercury reaches through it; Deploy <device> (the management path) | its warning on the plan; no confirm of its own: the run reaches it by itself, last, after every device reached through it (dependency order); a carrier whose program is accounts and privilege lines only joins the normal waves, the plan saying so | **deviation** (log: Board R's R10: the rollout engine replaces Go on and the carrier's confirm) |
| R10: The engine's options and the stopped run | the plan's options before the confirm (a pause after the canary, off; a settle between waves); one confirm; a stop rolling the failed device back, naming the rest not started and telling the team; the preview and the run under In progress, reopenable | the same: the form's Settle between waves and Pause after the canary for my Continue, the plan's words for them, part of its hash; the stopped card naming the devices not started and whether the team was told; In progress's Open its card and Open the result reopening the card on Credentials (`ra_job`) | **same** |
| R11: Update the read-only account's lines | the coverage's Intent says column and Add's ticks naming the lines in another form; Add's preview's In another form with Update the read-only account's lines…; the update's preview (summary, each line old → new per group, the lines a deploy will send, masked), Update N devices' intent, Back, Cancel; the result "Updated in intent" with Source read-account-update | the same; a group per platform and the same change; the refused and the current named | **same** |
| R10: The probe in each device's verify | each program on expand ends with its probe (whom it signs in as, how many reads and refused commands, what is not measured); each device's state in the run with its probe's verdict | the same: `data-ra-plan-probe` under each program, its probe's hash on hover; the run's rows with "probe" and its verdict's badge, its why on hover | **same** |
| R7: Stopped | the failed device and why, the rest not attempted, Preview the rollout again | the same, "Preview the rollout again…" | **same** |
| R4b: The management path not measured | "Not offered:" naming the comparison and both operands; no Deploy the canary; Preview the rollout again…; the form's devices named by you as the management path | the same; a confirm sent anyway is refused with the same words; a named device drawn "named by you as carrying Mercury's management path", last and alone | **same** |
| R8: Probe… on a row | Probe… with How does this work? where intent names the account or the device holds it | the same, in the Last probe cell | **same** |
| R8: The preview | whom it signs in as, every command in order with what is expected, not measured and not asked with why, the hash; Probe <device>, Cancel; refused now named | the same: the probe's own preview words in one block, the hash beside the confirm; a refusal now (the backup window, a device held) drawn and the button not offered | **same** |
| R8: The result | the verdict and why, recorded on History as whom; the commands by result, collapsed | the same, with the record's file name and the proposal when a read is refused | **same** |
| C3427 | not on board R | not built | **later** a replaced read-only password reaching every device (plan-before-video 1.4) |
