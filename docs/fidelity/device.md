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
Templates compared: templates/v2/device.html, templates/v2/_actions_menu.html, templates/v2/_status.html, templates/v2/_drained_badge.html, templates/v2/_capture.html, templates/v2/_deploy.html, templates/v2/_attribution.html, templates/v2/_rotate.html, templates/v2/_persist.html, templates/v2/_persist_effect.html, templates/v2/_startup_effect.html, templates/v2/_seed.html, templates/v2/_restore.html, templates/v2/_revert.html, templates/v2/_retry.html, templates/v2/_retire.html, templates/v2/_diagnose.html, templates/v2/_held_banner.html, templates/v2/_declare_drill.html
Compared again 2026-11-05 (the main session, H16's gate): `_diagnose.html`'s "not offered"
`<details>` gains `data-keep` (C472: a live region's details keeps its state across a redraw),
an attribute no region draws; every region reads as before.
Compared again 2026-11-06 (P1b, C2606 and C2608): `_actions_menu.html` draws the changing rows
(Plan a deploy…, Restore from…, Remove lines (Mode B)…, Rotate credential…, Persist, Run a
privileged command…; and for a host Capture and Seed intent… too) greyed with "Not offered:
<why>" on hover and for a screen reader, and the menu's note names the state ("router is
observe (the device's local config context): nothing that changes it is offered"), only for a
device NetBox's config context marks observe-only or whose kind is host. A managed device's
menu is unchanged, row for row and word for word: every region below reads as before. No shot
was taken (tests/test_board_shots.py draws no observe-only device); compared by the template
and the menu tests/test_inventory_entry.py renders. The greyed rows are board 11's own pattern
for Revert and Retry; no board draws an observe-only device, so the state is a deviation, a
line in STANDING_APPROVAL_LOG.md. Templates sha256 before:
`3b2f0b7c4c55bc7cb018c02d6312ef9591e101e6b453f5c0a1564dc89bd299a6`.
Compared again 2026-11-07 (C2700, the operator's direction "make the deploy preview show
nesting visibly (indentation preserved in THE PROGRAM)"), by the template:
`_deploy.html` draws The program through `_macros.html`'s `program_lines`, the same lines in
the same `op-diff` block, each line inside a section led by a guide per level (│, CSS
generated content on an empty span, `.op-nest`), so a flat program is seen before the
confirm; each line's text is the program's bytes, leading spaces and all
(tests/test_unmodelled_children_depth.py). Restore's program is drawn as before. No board
draws a guide: a deviation, the line "Device: the deploy program draws a guide per level" in
STANDING_APPROVAL_LOG.md; the region "Deploy: The program" below says so. No other region
moved. Templates sha256 before:
`0336b633b878443964c6e90d21c8ad87d09aa90bcef690660692fc9374bb0d01`.
Hashed again 2026-11-11 for C2992 and the operator's work order from the Lab 9 sitting
(2026-11-10: "the capture picker default and re-confirm; 'Differs from intent' says NetBox
changed; the OVS preview shows its transaction and 'already as intended'; Retire on observe
devices says what it does; credential profile slug as a dropdown"; at the sitting, of Retire…
on the router and the 2960: "the button should say what it does"). Two templates moved.
`_actions_menu.html`: the Retire… row carries its own words on hover (its title, which a screen
reader reads as its description; the row's name stays "Retire…":
"Sends nothing to <device>: takes it out of management in Mercury's records and, where NetBox
writes are on, in NetBox's record of it. Its preview lists every change, and what survives and
where, before anything is done."), and on an observe-only device or a host the menu's note
adds "Retire… is offered: it sends nothing to <device>, and changes Mercury's records and,
where NetBox writes are on, NetBox's record of it."; a managed device's menu draws the same
rows and the same note as before. `_retire.html`: the card opens with a part "What Retire
does", above Why: nothing is sent to the device (and, on an observe-only device or a host, why
Retire is offered all the same); what changes in Mercury's records, with how many steps are to
do; NetBox's record of it in the plan's own words, with what the plan says it does not do
there; what survives and where. Every other part of the card is as compared. Compared by
reading the templates against board 12 and the card tests/test_device_retire_v2.py renders,
with no new shot (tests/test_board_shots.py draws no observe-only device); one deviation,
logged; the regions "Retire: what it does" and "Actions menu: Retire…'s own words" below.
Templates sha256 before:
`b5ba864e07ec64d0e41b26d8650f1e7914d58ffc3cfd69d0191e5ad31ae2bf38`.

**Hashed again 2026-11-11 for the operator's request of that day** ("While the run is in
progress, a page refresh offers 'Re-subscribe r7's telemetry' again. While a device is held by
a run, its actions must be disabled, saying 'running since <time>, by <who>', with a link to
the run."). `_actions_menu.html`: while a run holds the device (`in_flight.held_action`, the
hold the server refuses by), a second note under the menu's first says "<device> is held:
<run> running since <time>, by <who>. Nothing that changes <device> is offered until it ends;
reads stay offered." with **Open the run**, and every row that would change the device (Plan a
deploy, Capture, Seed intent, Restore from, Remove lines, Revert, Retry, Rotate, Persist, Run a
privileged command, Reload, Verify again, Re-key, Retire) is drawn greyed as an observe-only
device's rows are, "Not offered: <run> running since <time>, by <who>" on hover and to a
reader; Check drift now and Diagnose stay offered. With nothing held the menu is as compared.
`device.html`: the menu's container also listens for `in_progress` (a job's start), so the
rows grey and return without a reload; nothing drawn moved. Boards 8 to 12 draw no held
device: **deviation**, logged in STANDING_APPROVAL_LOG ("Device: the Actions menu greys every
changing row while a run holds the device"). Compared by the template diff and the menu
tests/test_held_actions.py draws, not a new shot. Templates sha256 before:
`1446343d05a0120b023505e25335e77b4d5fe5d97fa2aa0e8a831a9e0536567f`.

**Hashed again 2026-11-11 for where a run opens** (the operator, that day: "4. The result
opens on the device page for now; once the incident page exists, 'Open the result' goes to the
incident's URL."): `_actions_menu.html`'s "Open the run" takes its address from the one macro
that builds it (`run_href`, `_macros.html`), which gives the address it had. Nothing drawn
moved. Templates sha256 before:
`e5b302368775fadbc20a282051698820047a780a5f325a737f3ef7a95e6ee774`.

**Hashed again 2026-11-11 after the operator's test of the held actions on the host** ("1. The
held notice moves OUT of the Actions menu into a banner under the device's name, across the
page: 'r7 is held: <run> since <time>, by <name> · Open the run'. The menu keeps only its
items, greyed, each with a SHORT reason on hover. Move the menu's general explanation ('Every
action runs here…') to the ⓘ next to Actions."). `device.html` gains one region between the
device's name and the tabs, `#device-held`, which draws `_held_banner.html` (compared from
this hash on): while a run holds the device, a warning banner across the page, "<device> is
held: <run> since <time>, by <who> · Open the run"; nothing while it is free; read again on
`device_holds` and `in_progress`. `_actions_menu.html` loses its two paragraphs (the held note
of the hash before, and "Every action runs here…", now the manual's Actions section behind
the (i) beside the menu); a greyed item's hover is "Not offered: held by <run> since <time>".
An observe-only device's or a host's state note stays in the menu. Boards 8 to 12 draw the
menu with its first paragraph and no banner: **deviation**, logged in STANDING_APPROVAL_LOG
("Device: the held notice is a banner under the device's name"). Compared by the template
diff and the page tests/test_held_actions.py draws, not a new shot. Templates sha256 before
(without `_held_banner.html` in the list):
`9dbd158eb1321bc0b62b8f8daa6eaca0a876fc738918cdab42622d01a945de41`.

**Hashed again 2026-11-11 for Declare a fault drill…** (the operator's decision of that day,
built ahead of the evening's rehearsal): `_actions_menu.html` gains one row after Diagnose…,
always offered, opening `_declare_drill.html` (compared from this hash on) in place of the
tab, op `declare_drill`. Compared region by region with the incident page's board, section I1,
and the operator's words for the card, as tests/test_fault_drills.py renders it; no shot
(tests/test_board_shots.py has none of it yet): the table "Declare a fault drill… and its
card" below. Templates sha256 before (without `_declare_drill.html` in the list):
`a531441334dc4c48d11f06cae02ea99a262c2dbfc120276991f664b25d03ae8d`.

**Hashed again 2026-11-12 for End the fault drill** (the operator's overnight item 9 of that
day): while a drill is open on the device, `_actions_menu.html`'s fault-drill row reads "End the
fault drill (until HH:MM)", one press, in place of Declare a fault drill…, and greys Declare a
fault drill… with why when the drills cannot be read; `_declare_drill.html` draws the end's
answer where it draws the declaration's; `device.html`'s menu re-reads on `fault_drills`. No
board draws an early end: the two regions are rows in the table "Declare a fault drill… and its
card" below, each a deviation logged in STANDING_APPROVAL_LOG ("End the fault drill"). Every
other region as compared; compared by the templates' diff and the pages
tests/test_fault_drills.py draws, not a new shot. Templates sha256 before:
`90dbaf2c170cfd5ed895d9a2c75cbaa98093cac47300709390dde8727c0e221d`.
Templates sha256: `82f488b184b6275ca53f8b1212f51bde13fe2ce43644fe27f86837595b756202`

**Hashed again 2026-11-12 for the reopened card's banner** (the operator's F1 smoke test of r3,
"no "Reopened" label"; his words of 2026-11-11, "Your run, started 13:01"; C3162, C3122, and
C3121's one time zone; and "A self-heal is never "by <person>" or "started by you"", C3161):
`device.html`'s banner above a card the page reopened says whose run it is and when, "Your run,
started <time>" (another person's: "<name>'s run, started <time>"), and ", finished <time>
while you were elsewhere" once it has, each time the page's clock element (the viewer's zone,
UTC on hover), where it said "Reopened: started by you at HH:MM UTC" or "Finished at HH:MM UTC,
while you were elsewhere; started by you". A self-heal's card says who it is by itself, once
("by Mercury's self-healing · policy set by <name>"), so it carries no banner. Board C's
"Reopened" chip: **deviation**, logged in STANDING_APPROVAL_LOG ("A reopened card's banner
says whose run it is"). No other region moved. Compared by the template's diff and the pages
tests/test_in_flight.py, tests/test_run_outcomes.py and tests/test_heal_stages.py draw, not a
new shot. Templates sha256 before:
`61e0ce89028786ad01347c2e77a133efd1c6a86c0137bb16719dc4aa6b35be89`.

**Compared again 2026-11-11 (board E2a, display names):** by the templates' diff against the
regions below, not from new shots. In `_capture.html`, `_retire.html` and `_diagnose.html`,
each place that draws a person (who a capture was recorded by, a retirement step's words naming
who kept a host key, who a diagnosis was started by or asked for on demand) now draws them
through the `people` filter, by display name (the name the person set, else the part of their
identity before the "@"), in the same element and position; no region is added, removed or
moved, and no other word changes. The cards' "You are a verified person: <name>" check names
the person the same way (`device_actions`). Where the board draws an identity the built screen
draws the name, a deviation logged once for every screen (log: Display names: a person is
drawn by display name on every screen). Every other verdict stands.

**Compared again 2026-11-05 for H16's second part** (board H's amendment, artboards I and J),
by reading the artboards against `_diagnose.html` as tests/test_heal_diagnose_v2.py renders it
(no shot: C2583): Run is replaced by "<device> is in diagnosis dg-… (started … by …);
Diagnose… is offered when it ends" while a device the plan reads is in one (I's amendment
note: **same**); a hint from an alert or a can't-fix row that matches no offered adjacency is
said on the card (no board draws it: it is the subset saying so); Can't reach's hop table
(J's right) is drawn above the steps, its ping "not interpreted" where J reads "0 of 5 ·
fails" (**deviation**, under the log line "H16's Diagnose… card", its text amended as the
report proposes); Open in History opens the device's History tab on the kind Diagnoses and the
diagnosis's day, in its own network, where J's link names History (History reads the active
network only: the same deviation's line); the device page reopens a running or unread
diagnosis as it reopens every job card (C537; no board draws a reopened Diagnose card: the
reopened badge is board C's). The table's rows "One diagnosis per device", "Can't reach's
path", "The result's controls" and "Diagnose… on an alert's card" are written again below.
Templates sha256 before: `20e2078c26ed7a66598677f7499cd2fc7f1e5456a2c30d7e3b9ee7505b2e7560`.

**Compared again 2026-11-05 ~11:4x UTC for H16** (board H's amendment, artboards I and J): the
Actions menu gains **Diagnose…** after Check drift now…, always offered, opening its card in
place of the tab (`_diagnose.html`, op `diagnose`), which joins the templates compared. Compared
by reading the artboards against the rendered card, region by region, in "Board H's amendment,
artboards I and J (H16)" below; no other region moved. Templates sha256 before:
`49fac3323a4ab8c9875d0401423029cd5f35973e1d8df21c400cf316f9ec42b9`.

**Compared again 2026-11-03 ~05:3x UTC for C2336** (the operator's sessions 7 and 8: "Check drift
now" on the device's Actions menu and the drift row's Open…): the Actions menu gains **Check drift
now…** after Verify again, always offered, opening its card in place of the tab as every row's
card opens (`_drift_check.html`, op `drift_check`: what it reads, what will not happen, its
**Check drift now** busy on itself, the result in place); the drift card's What to do gains "Read
it again" first, opening the same card. Compared by reading against the device-actions boards'
menu and op-card pattern: one row, one card in the pattern, no other region moved. A deviation,
logged in docs/STANDING_APPROVAL_LOG.md ("C2336's Check drift now") and PHASE8_PLAN 19.1: no
board draws this row or card; built in the boards' own op-card pattern. Templates sha256
before: `835af3d490d19c0f3fad66a24769261a067892ff9224cdb6148d21e1430f81b5`.

Compared again 2026-11-02 (C2283, board FC's 22.1 (6)), by the template: the deploy preview's
"Where the added lines come from" (`_attribution.html`, C867's, which no deploy board draws)
gains a group per committed intent layer the device takes, "From the intent layer tag
blind-lab (<commit>): N line(s)", above the monitoring profile's, each layer's lines measured
by the render, never guessed (tests/test_deploy_layer_provenance.py). Board FC4 names the layer
on each line ("from tag blind-lab, layer commit 5a1e2f0"); a group a layer is the same
information in the shape the profile's lines already take. With no layer nothing is drawn, so
no region's verdict moved. Templates sha256 before:
`885cd8a00e19bcc08e199e20fd50844260128eb71bf863c0e0f11462cdaa6433`.

Compared again 2026-11-02 (C2268, PHASE8_PLAN 21), by the template: the Actions menu's wrapper
binds `data-editing` to whether it is open, so a live redraw is held while a person has it open
and happens once it closes (tests/test_live_refresh_holds.py, in a real browser). Nothing drawn
changed; no region's verdict moved. Templates sha256 before:
`3516941bcca531f4e8129aef428c8165fa4afb64513f3d9fb1fe9ffcfeb6bb31`.

Compared again 2026-11-02 (board PS, C2274, part 1) after `_status.html` drew the planned state
(`modules/planned_state.py`): under a running operation, "Reloading · by … · step 4 of 6 (wait) ·
back by ~…"; predicted out of reach by another device's operation and not answering,
"Unreachable as expected · r3 reloading · back by ~…"; either amber and linked to the page whose
card is the operation's; past its time, red, "Not answering · overdue after r3's reload". It
re-reads on a hold ending, a step and a window declared. Shots: `planned-device-r3-page-1440`,
`-1280`, `-390`, `planned-device-r4-page-1440`, `-390` beside `planned-board-board-1440`
(`PlannedState.dc.html`, region 1). The regions are in "Board PS" below. Templates sha256
before: `f799e90a3804314f0582cd2272760dfe3e78e5794f29bc9a567dc9974ea5059d`.

Compared again 2026-11-01 (C2280, the operator's finding 4), by the template: the Actions menu
gains **Verify again…** after Reload…, offered only while the device's last reload ended not
verified and otherwise drawn greyed with its reason (Re-key's pattern); it opens the Reload
card's Verify again offer in place. Board 7's ActionsMenu draws no such row: **deviation**,
logged in STANDING_APPROVAL_LOG. No other region changed. Templates sha256 before:
`4b1ab5edd8ed8c7cb0bfba61f5bdd899778c09280be6c6cb2bc84dd407b9adb5`.

Compared again 2026-11-01 (C2239, the overnight brief's item 1), by the template: the Actions
menu gains **Re-key…** after Reload…, offered only while Mercury holds a refused SSH host key
for the device and otherwise drawn greyed with its reason (Revert and Retry's pattern), and
the menu re-reads on `host_keys`. Board 7's ActionsMenu draws no Re-key row: **deviation**,
logged in STANDING_APPROVAL_LOG. No other region changed. Templates sha256 before:
`46f57eb3cb54da3c7f2c90636527e71f2d925b2fecd91b903c20215fb29f3ac2`.
(2026-10-29: `_deploy.html` gained the Change record part, compared with board CR in
docs/fidelity/change-record.md; its form an id, and the foot's note one sentence. Before:
`d33226f1c5dcfd1480130867aeb6b874a88b21b8498264c6c72db31eee13b94d`.)

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

Compared again 2026-10-26 (C1434, the operator's Walk 3) after `_deploy.html` gained the
board's disabled primary for a card waiting on a reason and its note gained each waiting line
by name, and the plan's reason check became one check, "lines needing a reason", covering a
line ticked for removal as well as a dangerous one (it read not applicable on a removal with
no dangerous line, and Deploy was offered). Shots: `device-deploy` at 1440 beside
`DevDeployPreview` at 1440 (tests/test_board_shots.py `test_device_deploy`), the card's foot
and Checks region by region.
- **The foot:** the same parts as the board. The primary is drawn disabled, "Deploy 7 line(s)
  to r2", and the note says what it waits on and that Deploy is offered once every reason is
  given. Two differences:
  - the note names the line and where its reason is typed ("waits on your stated reason for
    `shutdown` (in its reason box)"), where the board says "Waits on one reason";
  - the disabled button is at the left, where the live Deploy button stands, with "Preview it
    again" at the right; the board draws the button at the right and no second button.
- **Checks:** the board draws two checks, "Every dangerous line has a stated reason" and
  "Every ticked removal is a measured shape, with a reason". The page draws one, "lines needing
  a reason", failing with the line named. It is one check because the apply refuses on one
  list, dangerous lines and removals together (`assert_authorised`); the removal's measured
  shape stays its own refusal at the tick.
- **The row "A card that cannot be confirmed yet"** now reads **same** for the deploy card;
  the other cards it names are unchanged.

Deviations, each a line in STANDING_APPROVAL_LOG.md: "Device: the deploy card's waiting note
names each line" and "Device: one reason check for dangerous lines and removals".

Compared again 2026-10-27 (C1434's one click, the operator's order after Walk 3) after
`_deploy.html` let the page enable Deploy once every reason is typed, the press computing the
plan again with the reasons as typed. Shots: `device-deploy` and `device-deploy-ready` at
1440 beside `DevDeployPreview`, the foot region by region.
- **The waiting foot:** the same as compared on 2026-10-26: the disabled primary, the note
  naming the line. Its last sentence now says what the press does: "Type it above and Deploy
  is offered: pressing it computes the plan again with your reasons before anything is sent.
  Nothing is queued."
- **The ready foot:** unchanged, the bound program and Deploy.
- **Two states the shots do not reach,** read in the template and its tests
  (tests/test_device_deploy_v2.py, the browser tests):
  - **Reasons typed but not yet planned:** Deploy enabled in the page, its note saying the
    press computes the plan again.
  - **A press that finds the program moved:** a warning under The program, "Not sent: the
    program moved after this card drew it (…)", naming what moved.
  The board draws neither state. Both are within the board's parts, the confirm and its note,
  so they are **same** in kind.
- **The waiting Deploy is the one confirm pattern from the start,** drawn disabled
  (tests/test_v2_one_confirm.py refused a confirm route named any other way). It holds the
  same words as before, so nothing drawn moved.
No other region's verdict changed.

Compared again 2026-10-27 (C1847, the operator's Mode B re-walk) after `_deploy.html` gave
the checks, the operands and the authorisation note ids the page draws again as a reason is
typed, and marked the reason's check. Shots: `device-deploy` and `device-deploy-ready` at
1440 beside `DevDeployPreview`, the Program, Operands, Checks and foot regions.
- **At rest:** the same as compared on 2026-10-27 (C1434): the dangerous line's note, the
  Operands, the failing "lines needing a reason" and the disabled Deploy with its note. The
  note under The program is now always in the card, hidden when it is empty, so nothing drawn
  moved.
- **A state the shots do not reach, read in the template, the script and the browser tests**
  (tests/test_device_deploy_v2.py, `test_the_checks_follow_the_why_and_deploy_follows_the_checks`):
  while a typed reason is planned again, the reason's check reads "checking" and Authorised
  lines "checking", then the plan's answer; a check that cannot be read again says
  "Couldn't load" on it and Deploy waits. The board draws checks only as pass or fail; this is
  the check's own region, so it is **same** in kind.
No other region's verdict changed.

Compared again 2026-10-29 (PHASE8_PLAN 16.11 item 3, board CR) after `_deploy.html` gained the
part "Change record" between Checks and the foot (`_change_record.html`, compared region by
region in docs/fidelity/change-record.md), its form the id `deploy-form` (a drawn draft's call
is carried by it), and the ready foot's note the sentence "The change record is not part of what
you confirm.", board CR's words. Shots: `change-record-offered`, `change-record` and
`change-record-stale` (tests/test_board_shots.py `test_change_record`) at 1440, 1280 and 390:
every other part of the card as before. No other region's verdict changed.

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
| A card that cannot be confirmed yet | its primary button drawn disabled, with the note ("Waits on one reason…", "Not available while the deploy holds r3…") | the note ("Nothing to confirm: s2 matches its golden, so nothing would be recorded.", capture 09; "Not available: …, Nothing is queued.") and a "Preview it again" button where one helps; no disabled primary (capture, rotate held, restore, retry, retire); the deploy card waiting on a reason draws its disabled primary since 2026-10-26 (C1434) | **deviation** for the other cards (log: Device: a card that cannot be confirmed draws no disabled button); **same** for the deploy card waiting on a reason |
| Capture: result | Captured, Recorded; What happened with the commit linked, as the verified person, the time with the read on hover; Still true; What next: Edit intent…, Remove the line (Mode B)…; Open in History | the same, What next with two more: Deploy intent… and Restore from…, each with its (i) | **deviation** (log: Device: Capture's result offers four ways on) |
| Capture: result's colour | green, "Recorded", over r3 departing from intent by one line | amber, "Recorded; departs from intent" ("Recorded; intent not compared" where it was not compared); green "Recorded" only at intent (C1273) | **deviation** (log: Device: Capture's result is amber for a device departing from intent) |
| Prose naming code | code in its own type ("load-interval 30", "Source: seed") | raw backticks around it in the capture card's intent sentence, the capture result, persist, the seed result, the revert footer and result, the retire result ("(`load-interval 30`)") | **deviation** (log: Device: card prose shows raw backticks around code (a defect, register C650 follow-up)) |
| Capture: r2 moved | Not recorded, the read at confirm and the read confirmed, Preview it again | the same, Preview it again a button with its (i) | **same** |
| Capture at phone width | board 4: the card stacked, head controls under the title | the same | **same** |
| Deploy: The program | the lines in order with "needs your reason" and "Mode B" badges on their lines, the reason field under it, "Authorised on r3 before: never" | the lines in order ("Exactly these 3 line(s), in order", capture 27), no per-line badges, each line inside a section led by a guide per level (C2700, its own log line "Device: the deploy program draws a guide per level"); "Where the added lines come from" (C867: this edit's, the profile's and those already pending, `_attribution.html`), then the dangerous line's reason field inline, and the authorisations it needs | **deviation** (log: Device: the deploy and restore programs draw no per-line badges) |
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
| Retire: what it does | not drawn: the card opens on Why | a first part, "What Retire does": "Nothing is sent to <device>" (and, on an observe-only device or a host, why Retire is offered all the same), "In Mercury's records", "In NetBox's record of it" in the plan's own words with what it does not do there, and "What survives, and where" | **deviation** (log: Device: Retire says what it does before it is pressed) |
| Actions menu: Retire…'s own words | the row "Retire…" with its (i); no observe-only device drawn | the same row and (i), with its hover and screen-reader words saying it sends nothing and what it changes; on an observe-only device or a host the note adds "Retire… is offered: it sends nothing to <device>…" | **deviation** (log: Device: Retire says what it does before it is pressed) |
| Retire: the export check | "Export the record on Credentials…" (a link) | the same button, and the check's words name a host command (`…/python scripts/nmas-breakglass export --list Lab …`); the result names `nmas-retire --breakglass <file>` | **deviation** (log: Device: Retire's export check and result name host commands (a defect, register C650 follow-up)) |
| Retire: result | r5 is retired, Done; what happened; Dropped; Still to remove; "this address shows its retired record"; Back to Devices | the same, with the one stepper and Recorded; the header's Actions menu, re-read after the retire, draws "Couldn't load this view. Try again" | **deviation** (log: Device: after Retire the header's Actions menu draws Couldn't load this view (a defect, register C650 follow-up)) |
| A held device, its lease and takeover | HoldTakeover (R26): wait while it moves; after 10 minutes still, Take over r2's hold…, recorded | the refusal by name and the redraw when free; no lease, no takeover | **later** R26's lease and recorded takeover (docs/CONCURRENCY_AUDIT.md R26, approved 2026-10-04, not built) |
| Revert by reload | RevertChoose, RevertRun, RevertRed: the menu row, the moment, the outage, the boot file, the run and its red endings | no row and no card | **later** the charter's Phase 2, revert by reload (docs/PHASE7_BURNDOWN.md) |
| Changing a device's role | DeviceRoleEdit: Identity's Change…, the preview with what follows | not built | **later** the proposed role change (board proposed, never signed off) |

## Board PS (C2274): the header under a planned operation

| Region | Board | Built | Verdict |
|---|---|---|---|
| The operation's own device | "Reloading · by … · step 4 of 6 (wait) · back by ~01:12 UTC", amber, beside the name, opening the card | the same words beside the name, amber, linking to the device's page, which reopens the running card | **same** |
| A predicted device | "Unreachable as expected · r8 reloading · back by ~01:31 UTC" | "Unreachable as expected · r3 reloading · back by ~00:30 UTC", linking to r3's page | **same** |
| Overdue | red, "Not answering · overdue after r8's reload (back by 01:31)" | the same words, red, linked; tested, not shot (`tests/test_planned_state.py`, `TestOverdue`) | **same** |
| The chip's style | a dashed amber chip | the warning badge with the history icon | **deviation** (log: Board PS built, part 1) |
| Phone width | the chip wraps under the name | the chip wraps under the name | **same** |
| The operation's card: Expected effects (part 2) | a table: Effect, Predicted by, Now, Expected back by; six rows from the preview, the sources and the boot | the same four columns, a row per signal a source holds for this window now (`planned_state.expected_effects`), back by as a clock time; at phone width each a labelled block (`planned-reload-card-page-1440`, `-390`) | **same** |
| The card's Now column | "not answering since 01:05", "cleared 01:12", "firing since 01:12" | "held, not raised" for a held signal, "answering" for a predicted device back; no since or cleared time (the sources keep no history of a hold) | **deviation** (log: Board PS built, part 2) |
| The card's boot effect | a C8000v's `%PKI-2-NON_AUTHORITATIVE_CLOCK`, declared per platform | not built: no per-platform boot effects are declared yet | **later** PS's per-platform boot effects (C2274) |
| Unexpected during, Overdue | one line each, "none" | the same, each a notice naming the rows when there are some | **same** |
| A source not read | not drawn | named in a warning: "Not read, so what it would hold is unknown" | **deviation** (log: Board PS built, part 2) |
| A predicted device that answers | not drawn | drawn as answering | **deviation** (log: Board PS built, part 1) |
| What it re-reads on | not drawn | a hold ending, a step, a window declared, reachability | **same** |
| Hover | not drawn | the operation and who, or why it is held | **same** |
| Words of a window with no hold | "Restarting as planned" (20.3) | "Restarting as planned · by … · back by ~…" | **same** |

## Board H's amendment, artboards I and J (H16): Diagnose… and the diagnosis in place

Compared 2026-11-05 ~11:4x UTC by reading `docs/boards/heal-to-intent.html`'s artboards I ("Diagnose…
on a device and on an alert") and J ("A diagnosis, drawn in place") against `_actions_menu.html`
and `_diagnose.html` as rendered by tests/test_heal_diagnose_v2.py on the fleet's real intent (r2
and r3 in place of the board's r4). No shot was taken: tests/test_board_shots.py has no Diagnose…
shot yet, so the comparison is of the board's regions against the rendered card's words and
controls, region by region.

| Region | Board | Built | Verdict |
|---|---|---|---|
| Actions menu: Diagnose… | after Check drift now…, before the rule and Re-key… | after Check drift now…, before Re-key…, with its (i); always offered | **same** |
| The card's head | "Diagnose r4", How does this work? | "Diagnose r2", How does this work?, and Cancel in the head as every op card draws it | **deviation** (log: H16's Diagnose… card) |
| What is wrong | two radios: "An adjacency is down with both ends at intent", "Can't reach a device or an address from r4" | the same two, the card drawn again for the one chosen | **same** |
| Which adjacency | a select from intent: "r3 over GigabitEthernet4: OSPF, area 0 (intent)", a BGP neighbour | the same select, the interface as the network model names it ("r1 over Gi2: OSPF, area 0, OSPFv3, area 0 (intent)"), BGP neighbours with their AS; the adjacencies intent runs no protocol over listed under "N not offered" with why | **deviation** (log: H16's Diagnose… card) |
| Can't reach's target | one select: "a device of Default, or an IPv4 or IPv6 address, checked as one address" | a select of the network's devices by their loopback in intent, and an address field beside it, checked as one address; the card says Can't reach reads IPv4 forwarding only | **deviation** (log: H16's Diagnose… card) |
| What it reads | Device, Reads, At most; each read named; Loki, one query | the same columns, each command as it will be sent ("show interfaces GigabitEthernet2 (twice, 10 s apart)"), each device's count; Loki's row; for Can't reach, the reads at each hop as the path reaches it | **same** |
| The run's time | "about 40 s, at most 90 s (an estimate until it is measured)" | the reads' own bounds added (minutes on a full plan) and "the run's time is not measured yet (an estimate of 30 to 60 s)" | **deviation** (log: H16's Diagnose… card) |
| One diagnosis per device | the button replaced by "r4 is in diagnosis dg-41a7 …" before the press | (H16's second part) Run replaced by "r4 is in diagnosis dg-… (started HH:MM UTC by …); Diagnose… is offered when it ends", read from the lock's record without taking it, the card re-read when a diagnosis ends; still refused by name if one starts between the card and the press | **same** |
| Run the diagnosis | primary, busy on itself, then the diagnosis in its place; Cancel | the same, busy on itself ("Starting the diagnosis…"), then the card waiting on the job's announcement, then the diagnosis in its place | **same** |
| The diagnosis's head | "Diagnosis: r4 GigabitEthernet4 ↔ r3 GigabitEthernet4, OSPF down", times, on demand or automatic, reads count; the chip "3 hypotheses · the first decisive" | "Diagnosis: adjacency down with both ends at intent, r2 and r1", times, on demand by whom, commands against the cap, its id and whether it was recorded; the same chip | **deviation** (log: H16's Diagnose… card) |
| The hypotheses | #, Hypothesis, Layer · strength, Evidence (masked) with each read a link, Would rule it out; "evidence incomplete" chip | the same five columns; each read a link to its run on History › Reads; the chip with what it lacks | **same** |
| Ruled out | a details, open, the checks joined | a part "Ruled out (N)", the checks joined | **same** |
| Not checked | not drawn | a part "Not checked (N)", each with why | **deviation** (log: H16's Diagnose… card) |
| Can't reach's path | a hop table: Hop, Read, Against intent, the diverging hop marked; the chip "diverges at r6" | (H16's second part) "The path, hop by hop": Hop, Read, Against intent, each verdict a chip (as intent, diverges, not read), the diverging hop's claim in bold, the hops after it "not read"; hop 0 the ping, "not interpreted" where the board reads "0 of 5 · fails" (the ping has no capture, C2414); the chip "diverges at <device>"; every step still drawn below | **deviation** (log: H16's Diagnose… card) |
| The result's controls | Run again, Open in History, "16 reads on History › Reads", How does this work?; Open r6's can't-fix row | (H16's second part) Run again…, Open in History (the device's History tab on the kind Diagnoses and the day it ran, in the diagnosis's own network), a link to each reads run on History › Reads, How does this work? | **later** Open <device>'s can't-fix row: a diagnosis on demand names no incident |
| Diagnose… on an alert's card and on a can't-fix row | drawn (Monitoring › Alerts, Needs attention) | (H16's second part) drawn on both: docs/fidelity/alerts-explain.md and docs/fidelity/landing.md compare them | **same** |

## Declare a fault drill… and its card (the operator's decision, 2026-11-11)

Compared 2026-11-11 by reading the incident page's board, section I1 ("The declaration: before
the fault, through Mercury"; text only, kept with the operator's reports), and the operator's
words for the button ("on the device page's Actions menu, 'Declare a fault drill…' opening a
small card (device fixed, the expected fault, minutes 1 to 15 default 10, a reason optional),
one primary action 'Declare the drill', the result in place ... busy on itself, no toast")
against `_actions_menu.html` and `_declare_drill.html` as tests/test_fault_drills.py renders
them (edge-b of Default). No shot: the board is words, so the comparison is of its words
against the rendered menu and card, region by region.

| Region | Board | Built | Verdict |
|---|---|---|---|
| Actions menu: Declare a fault drill… | a row on the device page's Actions menu | after Diagnose…, before Re-key…, with its (i); always offered (it sends nothing) | **same** |
| The card's head | a small card | "Declare a fault drill on <device>", How does this work?, Close in the head as every op card draws it | **same** |
| The device | fixed | in the head and carried by the form, never a field | **same** |
| The expected fault | the fault in words, at least 3 words | a text field, "The expected fault", its placeholder "the EEM heartbeat applet removed on <device>"; under three words refused by the server, naming the count | **same** |
| Minutes | 1 to 15, 10 by default | a number field "Minutes (1 to 15)", 10 by default, 1 to 15 held by the field and by the server | **same** |
| Reason | optional | a text field "Reason (optional)" | **same** |
| The one primary action | "Declare the drill" | "Declare the drill", busy on itself ("Declaring…") until the answer arrives | **same** |
| The result in place | "Declared: a drill on r3 until HH:MM: <expects>. Inject the fault now; an incident on r3 before HH:MM is a drill." | the same words, green, HH:MM the page's clock element (UTC on hover), in place of the form; no toast | **same** |
| A refusal | a late declaration refused, naming both times (I1) | "Couldn't declare the drill: <why>." in red above the form, the form kept with what was typed: after the fault, a second open drill, a bound or words out of shape | **same** |
| Actions menu: End the fault drill (until HH:MM) | not drawn: the board's drill lasts its bound | (2026-11-12) while a drill is open on the device, in place of Declare a fault drill…: one press, no confirm (it sends nothing), busy on itself ("Ending the drill…"), its (i) opening Ending it early; drills that cannot be read grey Declare a fault drill… with why | **deviation** (log: End the fault drill) |
| The end's answer in place | not drawn | (2026-11-12) the card in place of the tab, its head "End the fault drill on <device>": "Fault drill fd-… ended at HH:MM; incidents from now are real." green where the declaration's answer is drawn, HH:MM the page's clock element; a refusal "Couldn't end the drill: <why>." in red; no toast | **deviation** (log: End the fault drill) |
| The route | `POST /fault-drills/declared` | `POST /v2/fault-drills/declared` (device_v2.fault_drill_declare), the card's form and a script's JSON body alike | **deviation** (log: Declare a fault drill…) |
| History | the kind "Fault drill declared" (I3) | History's kind filter "Fault drills declared" under What happened to a device, one row per declaration; a drill heal's row begins "Fault drill:" | **deviation** (log: Declare a fault drill…) |
| The chip on the page and the card, the list's filter | the Fault drill chip, Real / Fault drills / Both (I3, I4) | not built: the incident page is not on main yet | **later** the incident page's S9 rest: its chip, filter, strip and CSV |

Compared again 2026-11-12 after `_declare_drill.html`'s "Declare the drill" gained
`gate('configure')`, as every posting control carries (tests/test_controls_consult_may.py
refused it in the slice's first gate): an attribute the page reads to disable the control for
a viewer who may not configure; nothing drawn moves, and every region above is as compared.
