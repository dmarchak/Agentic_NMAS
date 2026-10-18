# Fidelity: the device page, its shell and its actions

The device page as built (the shell: crumbs, header, Actions menu, tabs; and each action's card
in place of the tab), compared region by region with its approved boards, after the operator's
walk W1 (2026-10-16, which ran Capture on s2, the Mode B deploys on s1 and s2, Persist and
Reload… on r6 and the rotation on s1 from this page). The tabs' contents are the tab records
(`tab-overview.md` and the rest). Read from shots of the boards and the page side by side, in the
same headless Firefox, each card opened as its control opens it (the menu row clicked, or the
control's own htmx request into `#tab-body`), each confirm clicked, the result arriving in place
by the job's announcement where the operation is a job (`tests/test_board_shots.py::test_device_page`,
`test_device_deploy`, `test_device_rotate_persist`, `test_device_seed`, `test_device_restore`,
`test_device_revert_retry`, `test_device_retire`). Each test feeds the page from its action's own
tests: test_capture's lab (r2's REAL configuration and committed intent, the read replaced by r2
with `load-interval 30` on Gi2, `tests/test_device_capture_v2.py`); the deploy and restore labs
(`tests/test_device_deploy_v2.py`'s `deploy`, `tests/test_device_restore_v2.py`'s `history`, on
test_profile_apply's lab), their device path spied as those tests spy it and held until the
running card was shot; test_persist_screen's lab with the rotate tests' fakes
(`tests/test_device_rotate_v2.py`'s `rot`); the seed lab (`tests/test_device_seed_v2.py`); the
intent-ops lab with a rollback block on change A (`tests/test_device_revert_retry_v2.py`); the
retire world (`tests/test_device_retire_v2.py`). The fixtures hold r2 (r5 for Retire), not the
boards' r3, and no reachability reader, so the header's chip reads "Not probed yet"; the deploy
and restore results are the spy's receipt, not a device's. Read beside them: the operator's W1
captures 02 (the shell on s1: "Answering since 18 h ago", the sub line, Actions and its (i)),
09 (Capture s2 as its golden, nothing to confirm), 27 and 28 (the Mode B deploy's card on s1,
top and bottom) and 31 (Rotate s1's credential), at about half desktop width.

Boards: on the first canvas ("NMAS redesign mockups", page "Landing, devices, device", the device
page signed off 2026-09-29 with NSOT_GUI_BRIEF section 13, the spike approved 2026-09-30):
`redesign/Device.dc.html` ("Device page: r3, Actions open", 1440) and
`redesign/DevicePhone.dc.html` ("Phone: r3", 390); `redesign/PersistRunningHelp.dc.html` (page
"Services", "Persist running: the stepper, and How it works open", 1440) and
`redesign/DeviceRoleEdit.dc.html` (page "Device dashboard and role (proposed)", 1440, proposed,
never signed off). On the second canvas ("NMAS v2 mockups"): page "Device actions on v2" (boards
1 to 7 signed off 2026-10-02, 8 to 12 on 2026-10-03, 6 revised 2026-10-04 to the one stepper):
`DevCapturePreview` (1), `DevCaptureResult` (2), `DevRotateHeld` (3), `DevCapturePhone` (4, 390),
`DevDeployPreview` (5), `DevDeployResult` (6), `DevSeed` (8), `DevRestore` (9),
`DevRestoreResult` (10), `DevRevertRetry` (11), `DevRetire` (12; its last card is
`retired.html`'s, not compared here), `HoldTakeover` (R26, approved 2026-10-04) and
`DeployExpected` (C506, approved 2026-10-06); page "manual": `ActionsMenu.dc.html` (board 7,
every action row with its (i)); `RevertChoose`, `RevertRun` and `RevertRed` (page "Phase 2:
Revert by reload", approved 2026-10-07). Built here: every board but HoldTakeover, the three
Revert by reload boards and DeviceRoleEdit (each a **later** row below).
Shots: `device` (board 1440 and 390; page 1440, 1280, 390), `device-menu` (board 1440; page 1440,
1280, 390), `device-capture` (boards 1440 and 390; page 1440, 1280, 390), `device-capture-result`
(board 1440; page 1440, 390), `device-capture-moved` (1440); `device-deploy` (board 1440; page
1440, 1280, 390), `device-deploy-expected` (board 1440), `device-deploy-ready`,
`device-deploy-running`, `device-deploy-result` (board 1440; page 1440, 390),
`device-deploy-rolledback` (1440); `device-rotate-held` (board 1440; page 1440, 390),
`device-rotate`, `device-rotate-result`, `device-persist` (board PersistRunningHelp 1440),
`device-persist-result` (1440, 390); `device-seed-menu`, `device-seed` (board 1440; page 1440,
1280, 390), `device-seed-result` (390); `device-restore-choose`, `device-restore` (board 1440;
page 1440, 1280, 390), `device-restore-before`, `device-restore-running`,
`device-restore-result` (board 1440; page 1440, 390), `device-restore-moved` (1440);
`device-revert-menu`, `device-retry`, `device-retry-ready`, `device-revert` (board 1440; page
1440, 390), `device-revert-result`, `device-retry-none` (1440); `device-retire-refused`,
`device-retire` (board 1440; page 1440, 390), `device-retire-result` (1440).
Compared 2026-10-16.
Compared again 2026-10-18 (C1268, an A): the Deploy and Re-apply cards' result headline badge
draws `c.rollback_badge` where it drew the literal "Rolled back"; for a rollback that restored
the device (`restored`, `nothing_to_undo`) the words are the same, so the boards' rolled-back
result (board 11) is drawn as before; for one that did not, the badge names its state
("Rollback incomplete", "Rollback not read back", "Rollback failed", "Rollback not
attempted"), which no board draws: the deviation is a line in STANDING_APPROVAL_LOG.md. Every
other region unchanged: one expression in each of `_deploy.html` and `_restore.html`, read
from the diff.
Compared again 2026-10-18 (C1273, a B): Capture's result for a device that departs from its
committed intent is amber, its chip "Recorded; departs from intent" ("Recorded; intent not
compared" where intent was not compared), where board 2 (`DevCaptureResult`) drew green
"Recorded" over r3 departing by one line: green over a partial, which CLAUDE.md forbids and
which `preview_confirm.capture_result` already calls "partial". A capture at its intent is
drawn as the board drew it. The deviation is a line in STANDING_APPROVAL_LOG.md. No template
changed: the level and chip come from `device_actions.capture_result_card`.
Templates compared: templates/v2/device.html, templates/v2/_actions_menu.html, templates/v2/_status.html, templates/v2/_drained_badge.html, templates/v2/_capture.html, templates/v2/_deploy.html, templates/v2/_attribution.html, templates/v2/_rotate.html, templates/v2/_persist.html, templates/v2/_persist_effect.html, templates/v2/_startup_effect.html, templates/v2/_seed.html, templates/v2/_restore.html, templates/v2/_revert.html, templates/v2/_retry.html, templates/v2/_retire.html
Templates sha256: `7dbf73e139c967c7dc143312b7a7a4953669ec56d4ac7d5b35cd8f9b1a53b251`

Compared again 2026-10-16 (C537, C540) after `device.html` gained the line a reopened card
carries and `_rotate.html` its running card's and held preview's changes (C540's words, and
the held preview's redraw carrying when it was drawn, `since`), beside a third board on the
second canvas (v66, page "C537/C538: In progress, Finish the job, the top bar"):
`Reattach.dc.html` (board C, 1440: the confirm's words, the running card reopened, the result
reopened), drawn and counted as signed off by the agent under the Phase 7 mode. Shots:
`reattach-running` and `reattach-result` (1440 and 390, beside `reattach-board`) from
tests/test_board_shots.py `test_in_progress`; `device-rotate-held`, `device-rotate` and
`device-rotate-result` from `test_device_rotate_persist` again at 1440 and 390 (the held card
redrawn by a deploy hold's release still draws a fresh preview: no rotation ran meanwhile).
Five regions added below (the confirm's words, the running card reopened, the result reopened,
a card freed by a rotation, Finish the job); no other region's verdict changed.

Compared again 2026-10-16 (C886) after `_persist.html` gained its part "What saving changes in
what it boots", drawn by the new `_persist_effect.html` (now among the templates compared):
`device-persist` shot again at 1440 and 390 beside PersistRunningHelp, r2 answering with r1's
real pair, one logging line changed in running. The Persist region rewritten and its part
recorded as a region of its own; no other region's verdict changed.

Compared again 2026-10-16 (C923) after the part's lines, certificate files and the "not a
difference" note moved into the macro `startup_lines` in the new `_startup_effect.html` (now
among the templates compared), so that Adopt's card draws them with the same drawing; the
leading sentences stay `_persist_effect.html`'s. The part rendered in ten states (reading,
failed, a refused list, no startup, the same with two files, one file listed and one not,
gains and losses with two files, gains only, losses only, a missing file only) before and
after: every byte the same. `device-persist` shot again at 1440 and 390 beside
PersistRunningHelp: the part as its region says. No region's verdict changed.

Compared again 2026-10-17 (C1025, the operator's B3 from W2) after `_status.html` gained a
third state: inside a planned-restart window a device that is not answering reads "Restarting as
planned (until …, by …)" (warn, the history icon, its title saying Needs attention raises it only
if it is still down when the window ends), drawn by the real `device_page.answering` from a
reader row that says not answering and a window covering it. Shots: `device-planned` at 1440,
1280 and 390 (tests/test_board_shots.py `test_device_page`) beside `Device` and `DevicePhone`,
and `device` again. At 390 the long chip ran past the screen's edge; `.status` now wraps and its
badge may break its line, inside the page, and a short chip draws as before (`device` at 390 the
same as before). One region added below; no other region's verdict changed.

The running cards draw the one stepper, compared with its boards in docs/fidelity/stepper.md.
Reload… (`_reload.html`; the walk's section I, capture 30) and Run a privileged command…
(`_privileged.html`, compared in tab-ask.md) are cards of later sign-offs: Reload has no board
file on either canvas, only the 2026-10-10 lines of the approval log, so it is not compared here.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Crumbs | Devices / r3 | Devices / r2; Devices / s1 (capture 02) | **same** |
| Header's chips | the name, then "Answering · 4 s ago" and the intent state ("At intent", "Departs (+1)", "Change blocked: rolled back"), or "Busy: deploy, 3 min 4 s" while held, on every board | the name and the answering chip alone ("Answering since 18 h ago", capture 02; "Not probed yet" here); no intent-state chip, and no Busy chip while another operation holds the device (shot `device-rotate-held`) | **deviation** (log: Device: the header draws no intent-state or Busy chip (a defect, register C650 follow-up)) |
| Header's chip inside a planned-restart window (C1025) | not drawn (every board's device answers) | "Restarting as planned (until 2026-10-17T00:27:47Z, by person@example.invalid)" in warn with the history icon, then "since 2 h ago"; the Overview's Answering row the same words; at 390 the chip breaks its line inside the page (shot `device-planned`) | **deviation** (log: C1025: the header's chip inside a planned-restart window) |
| Header's sub line | platform (model), the network, the address, "signs in as nmas, from its device override"; the action boards add "last measured 2 h ago" | model and platform each with its source on hover, the address, "signs in as admin", the network (capture 02); no credential source and no last-measured age (the Overview tab's table carries the age) | **deviation** (log: Device: the header's sub line names no credential source or last-measured age (a defect, register C650 follow-up)) |
| Header's controls | "Plan a deploy…" a primary button, "How does this work?", then "Actions ▾" | one primary "Actions", Plan a deploy… its first row, as board 6's revision draws it ("Plan a deploy… is its first row") | **deviation** (log: Device: Plan a deploy… is the Actions menu's first row) |
| Header's help | "How does this work?" beside the buttons | the (i) beside Actions, "How the Actions menu works", as on every v2 page | **deviation** (log: Device: the header's help is the info mark beside Actions) |
| Tabs | Overview, Intent, History, Monitoring, Neighbours, Ask the device (canvas 1); Logs and NetBox on the action boards | Overview, Intent, History, Monitoring, Logs, NetBox, Neighbours, Ask the device (every capture) | **same** |
| Actions menu: rows | canvas 1: RECORD, CHANGE, DEVICE groups with each unavailable row's reason in grey, Files…; boards 7 and 8: Plan a deploy…, Capture, Seed intent…, Restore from…, Remove lines (Mode B)…, Revert intent…, Retry rolled-back change…, Rotate credential…, Persist, Retire…, rules between groups | boards 7 and 8's rows and rules (the later sign-off), with Run a privileged command… and Reload… from their later boards; Files… not built | **same** (as boards 7 and 8) |
| Actions menu: each row's (i) | every row its (i) at the right edge, Revert and Retry included | every offered row its (i) (its tooltip and accessible name say which operation); Revert and Retry, not offered here, greyed with the why on hover and for a screen reader, and no (i) | **deviation** (log: Device: a menu row not offered carries no info mark) |
| Actions menu: the note | "Every action runs here. Revert and Retry are offered only while a rollback blocks…", under the rows | the same words, above the rows | **same** |
| Revert and Retry offered | while a block stands, both rows live | both live with their (i) on the blocked lab (shot `device-revert-menu`) | **same** |
| Phone shell | board DevicePhone: Plan a deploy… and Actions side by side at full width, the tabs scrolling | the Actions button alone, its (i) wrapped onto a line of its own under it; the tabs scroll | **deviation** (log: Device: at phone width the Actions info mark wraps onto its own line (a defect, register C650 follow-up)) |
| A card's place and width | in place of the tab's content, the tabs kept; held to the content column | in place of the tab, the tabs kept, Overview still marked current under the card (captures 09 and 31); the card spans the tab | **deviation** (log: C793: the device page's operation cards) |
| A card's head | the title, "How does this work?", Cancel (Close on a result) | the same ("Capture s2 as its golden", How does this work?, Cancel, capture 09) | **same** |
| Capture: What, What will not happen | reads now and records as golden, one commit, Source: capture, as you, "Read just now" with the read timings on hover; nothing sent, intent not changed, no baseline | the same three; but the stamp drawn in place of "Read just now" is the bare relative time, so the sentence ends "as you. just now" (capture 09) | **deviation** (log: Device: Capture's What ends "as you. just now" (a defect, register C650 follow-up)) |
| Capture: The difference | from the golden now, the section and its one added line | a unified diff of the golden against this read (hunk header and context lines), then the comparison with committed intent in a sentence; "None: s2's running configuration equals its golden …" when equal (capture 09) | **deviation** (log: Device: a card's difference is a unified diff with context) |
| Capture: Operands | golden now with its time, this read, committed intent with "departs (+1)" | golden now, this read, committed intent at its commit (capture 09; its departure said in the difference) | **same** |
| Checks, on every card | each check in plain words ("The device was read reliably: one configuration, its own hostname, no echoed command", "No other operation holds r3") | each card's own gates by name, with its detail ("device read"; "no other operation holds this device: nothing holds it now; the apply takes the device…"), more of them, the at-confirm ones marked "at confirm" (captures 09, 28, 31) | **deviation** (log: Device: each card's checks are its operation's gates by name) |
| A card that cannot be confirmed yet | its primary button drawn disabled, with the note ("Waits on one reason…", "Not available while the deploy holds r3…") | the note ("Nothing to confirm: s2 matches its golden, so nothing would be recorded.", capture 09; "Not available: …, Nothing is queued.") and a "Preview it again" button where one helps; no disabled primary (capture, deploy, rotate held, restore, retry, retire) | **deviation** (log: Device: a card that cannot be confirmed draws no disabled button) |
| Capture: result | Captured, Recorded; What happened with the commit linked, as the verified person, the time with the read on hover; Still true; What next: Edit intent…, Remove the line (Mode B)…; Open in History | the same, What next with two more: Deploy intent… and Restore from…, each with its (i) | **deviation** (log: Device: Capture's result offers four ways on) |
| Capture: result's colour | green, "Recorded", over r3 departing from intent by one line | amber, "Recorded; departs from intent" ("Recorded; intent not compared" where it was not compared); green "Recorded" only at intent (C1273) | **deviation** (log: Device: Capture's result is amber for a device departing from intent) |
| Prose naming code | code in its own type ("load-interval 30", "Source: seed") | raw backticks around it in the capture card's intent sentence, the capture result, persist, the seed result, the revert footer and result, the retire result ("(`load-interval 30`)") | **deviation** (log: Device: card prose shows raw backticks around code (a defect, register C650 follow-up)) |
| Capture: r2 moved | Not recorded, the read at confirm and the read confirmed, Preview it again | the same, Preview it again a button with its (i) | **same** |
| Capture at phone width | board 4: the card stacked, head controls under the title | the same | **same** |
| Deploy: The program | the lines in order with "needs your reason" and "Mode B" badges on their lines, the reason field under it, "Authorised on r3 before: never" | the lines in order ("Exactly these 3 line(s), in order", capture 27), no per-line badges; "Where the added lines come from" (C867: this edit's, the profile's and those already pending, `_attribution.html`), then the dangerous line's reason field inline, and the authorisations it needs | **deviation** (log: Device: the deploy and restore programs draw no per-line badges) |
| Deploy: Expected effects (C506) | derived effects, the declare buttons, what is unexpected, What verify checks (check, expects, read) | the same parts (capture 27: "None derived …", the three declare buttons, the two checks); the lab's program derives one (GigabitEthernet3 goes down) | **same** |
| Deploy: Left on the device | each line with its box, "will be removed", its reason in a field wide enough to read, a measured shape said; an IP SLA entry that cannot be removed | the ticked line, "will be removed" and its reason, a list bullet beside the box; the reason's field is narrow, so the walk's reason showed as "W1 walk: remove the spare p" (captures 27 and 28; C901) | **deviation** (log: Device: the Mode B reason box is too narrow to read (C901)) |
| Deploy and restore: What will not happen, Operands | three plain lines; operands captured from, intent, template, program hash, Verify scope | one paragraph on Mode B; the plan's own fields (capture hash, command hash, intent commit, authorised lines, template, platform, intent vs capture, lines already on the device, removals, secrets masked; capture 28); no Verify scope line | **deviation** (log: Device: the deploy and restore cards draw the plan's own fields) |
| Deploy: the confirm | "Deploy 5 lines to r3", "Bound to program e81f07c2: if r3 or its intent moves before you confirm, nothing is sent." | "Deploy 3 line(s) to s1" with its (i), "Bound to program cc1074a3f1d0: if s1 or its intent moves before you confirm, nothing is sent." (capture 28) | **same** |
| Deploy: running | board 6's stepper, "verify, waiting out BGP's hold time" | the one stepper (docs/fidelity/stepper.md), the device row and its steps | **same** |
| Deploy and restore: result | "Deployed to r3 Verified": what was received and verified, Removed (Mode B), Still true, Open in History | the receipt's words: the outcome's chip, what happened, Recorded, Open in History (fed by the spy here, so "done"; on the host "s1: done. It received 3 line(s)", the walk's step 24) | **deviation** (log: Device: the deploy and restore results are the receipt's words) |
| Deploy: rolled back | Rolled back; what happened and the rollback's result; What next: Revert intent…, Retry with a reason… | the same, each way out with its (i), and Recorded | **same** |
| Rotate: held | the card with "No other operation holds r3" failing by name, the holder, its start and last step; "reads again when it finishes; nothing is queued" | the same, the holder and process named; redrawn by the hold's release (shot `device-rotate` after the release) | **same** |
| Rotate: What is sent | the account line masked and `write memory` | the account line masked ("username admin privilege 15 algorithm-type scrypt secret <generated>"), then the steps in order (verify, record, persist; capture 31); its operand "Who else logs in as it: Mercury: updated automatically" claims more than the readers do, which tried the old password for minutes after the walk's rotation (C892) | **deviation** (log: Device: Rotate's "Who else logs in as it" claims every reader is updated at once (C892)) |
| Rotate: result | (not drawn on board 3) | rotated and persisted, what next: Export the break-glass record… | **same** |
| Rotate: the confirm's words (C540; Reattach 1) | "It runs as a job, so this page can close: the In progress chip in the top bar keeps it in front of you while it runs, and its result until you open it; Needs attention keeps it there if it stops before it is persisted." | the same words on the confirm and on the running card (shot `device-rotate`); today's rotate page keeps naming its in-flight panel | **same** |
| A running card reopened (Reattach 2) | the device's page opened again while the rotation runs: the running card in place of the tab, its stepper where the job is, "reopened: started by you at 21:03 UTC" in its head; nothing offers a second rotation | the same card and stepper in place of the tab (shot `reattach-running`), "Reopened: started by you at 08:34 UTC" on a line above the card | **deviation** (log: C537: the reopened card says so on a line above it) |
| A result reopened (Reattach 3) | finished while the person was elsewhere: the result in place of the tab, "finished 21:04 UTC, while you were on Devices", "Kept in History; the chip's row clears now that you have opened it" | the result card as its job draws it (shot `reattach-result`), "Finished at 08:35 UTC, while you were elsewhere; started by you" on a line above it, the chip's row gone; the card's own footer kept | **deviation** (log: C537: the reopened card says so on a line above it) |
| A card freed by a rotation (Reattach 3) | a card refused while s1 was held shows the same result once freed, never a fresh "Rotate s1" preview; Rotate again… stays in Actions | the same for Rotate: a held preview freed by a rotation that ended since it was drawn shows that rotation's card (tests/test_in_flight.py); a Plan a deploy… or Restore card freed keeps its form and plans again (C473) | **same** |
| Finish the job (Reattach 3, C538) | the result's checklist (board D) | not drawn | **later** C538's Finish the job |
| Persist | `PersistRunningHelp`: "Persist is running, step 4 of 7" (save, read back, the lab host's startup file, Oxidized's list and copy, record) beside How it works open | the card (what is sent, what will not happen, operands, checks), the confirm busy on itself while the device saves; the result on the one stepper (save, read back, recorded); How does this work? opens the manual's panel | **deviation** (log: Device: Persist saves on the device alone, within its request) |
| Persist: what saving changes in what it boots (C886) | not drawn (the board's persist is a run in progress) | a part of its own between What and What will not happen, read on load as a job by Reload's own reads and compared as Reload's gate compares: "Saving makes startup what r2 runs: startup gains 1 line and loses 1", "Startup gains, held only by running" (`+ logging trap informational`), "Startup loses, held only by startup: gone at the next reload" (`- logging trap notifications`), and the 2 certificates startup keeps as files said to be no difference (shot `device-persist`, 1440 and 390); "Reading r2's startup and running configurations…" until its job announces; when the two are the same, what Persist still does; a read that fails, "Couldn't load:" with why. The confirm does not wait on it | **deviation** (log: Device: Persist's preview reads what saving changes, as a job (C886)) |
| Seed | board 8: What, What will be committed (the first lines and the whole document folded), Reproduced, Device-owned, What it will not do, Operands, Checks, the confirm; the result: commit linked, Still true, What next | the same parts; the document's change a unified diff; the result's commit plain text | **same** |
| A result's commit | linked (capture, seed, revert, retire) | linked on Capture's result; plain text on the seed, rotate, revert and retire results | **deviation** (log: Device: a result's commit is plain text, not a link (a defect, register C650 follow-up)) |
| Restore: choose the moment | each moment a radio with its tag, its words and its credential state; show N more | the same rows and states, each with the message its tag records ("· golden r2 via capture", C868), each radio with a list bullet beside it (as the deploy's ticked line is, capture 27) | **deviation** (log: Device: a card's choice list draws a bullet beside each radio or box (a defect, register C650 follow-up)) |
| Restore: the dangerous line | "no shutdown on GigabitEthernet3 brings a link up. Why…", a fitting placeholder | "shutdown a dangerous line. Why…" (no verb), its placeholder "the account is needed again" | **deviation** (log: Device: Restore's reason line reads "shutdown a dangerous line" with an account's placeholder (a defect, register C650 follow-up)) |
| Restore: before onboarding | Its intent: leave it, or un-onboard it too | the same two choices | **same** |
| Restore: moved | "Not sent: r3's capture is a2d81f30 now, and the program you confirmed was computed from 7c1e04aa", Preview again | (a confirm carrying a changed hash, as the test sends it) "refused: nothing was sent. the device changed since you confirmed", said three times, neither hash named and no Preview again | **deviation** (log: Device: a refused restore names no hash and guesses the cause (a defect, register C650 follow-up)) |
| Revert | which change (the rolled-back commit chosen), what will be committed (each setting now and after), what it will not do, checks, the confirm | the same, the document's diff above the settings; the commit list's times in the commit's own offset ("2026-10-15T15:55:42-06:00"), not UTC | **deviation** (log: Device: Revert's commit list draws times in the commit's offset, not UTC (a defect, register C650 follow-up)) |
| Revert: result | Block still stands; the block after; Revert another commit…, Plan a deploy… | the same | **same** |
| Retry | the blocked program, the reason, what it will not do, checks; waits on the reason | the same, the reason field inline; the confirm offered once a reason is typed (shot `device-retry-ready`) | **same** |
| Retry when no block stands | "Nothing to retry", why not; the menu row says the same on hover | the menu rows greyed with the why on hover (tests/test_device_revert_retry_v2.py's `test_no_block_offers_neither_and_says_why_on_each`); the lab's block stood after the revert, so the card was not reached | **same** |
| Retire: the card | why (the reason), what retire changes in order (six steps, the lab startup frozen), generated so dropped, what survives, checks, refused until the break-glass record holds the credential | the same parts and the refusal, the steps the plan's own (NetBox masked, override cleared, one commit, the legacy file, the CSV row: no lab step), a Not changed part, an advisory line when the golden carries Mercury's heartbeat applet | **deviation** (log: Device: Retire's steps are the plan's own, with no lab step) |
| Retire: the export check | "Export the record on Credentials…" (a link) | the same button, and the check's words name a host command (`…/python scripts/nmas-breakglass export --list Lab …`); the result names `nmas-retire --breakglass <file>` | **deviation** (log: Device: Retire's export check and result name host commands (a defect, register C650 follow-up)) |
| Retire: result | r5 is retired, Done; what happened; Dropped; Still to remove; "this address shows its retired record"; Back to Devices | the same, with the one stepper and Recorded; the header's Actions menu, re-read after the retire, draws "Couldn't load this view. Try again" | **deviation** (log: Device: after Retire the header's Actions menu draws Couldn't load this view (a defect, register C650 follow-up)) |
| A held device, its lease and takeover | HoldTakeover (R26): wait while it moves; after 10 minutes still, Take over r2's hold…, recorded | the refusal by name and the redraw when free; no lease, no takeover | **later** R26's lease and recorded takeover (docs/CONCURRENCY_AUDIT.md R26, approved 2026-10-04, not built) |
| Revert by reload | RevertChoose, RevertRun, RevertRed: the menu row, the moment, the outage, the boot file, the run and its red endings | no row and no card | **later** the charter's Phase 2, revert by reload (docs/PHASE7_BURNDOWN.md) |
| Changing a device's role | DeviceRoleEdit: Identity's Change…, the preview with what follows | not built | **later** the proposed role change (board proposed, never signed off) |
