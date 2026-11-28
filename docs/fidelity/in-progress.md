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
Hashed again 2026-11-10 for base.html alone: one more deferred script, `js/nmas_draft.js` (SDN
› Apps' Add an app as a Draft…, which sends a chosen folder's files with their paths), loaded
after `nmas_credentials.js`. It draws nothing, so nothing in the top bar or In progress moves;
compared by reading the diff, with no new shot (the templates then hashed
`41f236b3a625127c6c2f9fc4a3c85e59f1f13f086506e709ef09e3636b73b1a4` before it).
Templates compared: templates/v2/_in_progress.html, templates/v2/base.html
Compared again 2026-11-13 (C3290, the words Python builds): the panel's "since" and a finished run's "at" (`_in_progress.html`) are `_macros.clock`'s, in the viewer's kept zone with the UTC instant on hover, where they drew the "21:03 UTC" modules/in_flight.py wrote (`_clock` now writes the instant). No element moves and no region's verdict moved; compared by the template's diff and the walk's render (tests/test_no_utc_drawn.py), not by new shots; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times: the words Python builds"). Templates sha256 before: `888e40eb8be1876169b741a4d4b5b02a4d75424ccc04fa788c2fa9706b8d1994`.
Compared again 2026-11-13 (board T, the sidebar's Troubleshooting section; provisional, operator review pending): `base.html`'s sidebar gains TROUBLESHOOTING above OBSERVE, Incidents (its tabs' row and its count) and Self-healing (its mode), compared in `incidents.md`. Nothing in the top bar, the In progress chip or its list moves, so every verdict below stands; compared by the template's diff, not by new shots. Templates sha256 before: `44f5831d2bca7341a81b044edbc2f4847f406bad908d54c62d28b5f701b2e531`.
Compared again 2026-11-14 (the operator: the sidebar's "Open · Closed" row under Incidents removed): `base.html`'s sidebar only; nothing in the top bar, the In progress chip or its list moves, so every verdict below stands; compared by the template's diff. Templates sha256 before: `a053fbb72978322118860ca14b21fe5373526bc745e771e954ff53c9b3007720`.
Compared again 2026-11-14 04:2x UTC (the operator's notes on board T; provisional, operator review pending): the sidebar's two chips removed ("the sidebar is navigation only"), and the top bar gains `#nmas-heal-auto` between the integrations strip and the AI chip, empty (and not drawn, `:empty`) unless a network's self-healing runs in Auto, then the amber "Self-healing: Auto until <time>" chip (compared in `incidents.md`). While the chip is drawn, the AI chip and everything after it keep their widths (its room comes from the items before it), and on a phone, where the bar is packed from the left, the chip sits just after the AI chip; at 1440, 1280 and 500 px the AI chip's box is the same with and without it (tests/test_incidents_list_v2.py, `TestTheAutoChipInARealBrowser`). Nothing in the In progress chip or its list changes. Templates sha256 before: `3587a9f3bf6aea98f18e1b3122e2a776a0b28b2c29cf340713be855a57ab7948`.
Compared again 2026-11-15 (C3715): each row's who drawn by display name; no element moves.
Compared by the template's diff (tests/test_actors_drawn_by_name.py); logged once
(docs/STANDING_APPROVAL_LOG.md, "Records name people by display name on every v2 screen
(C3715)"). Templates sha256 before: `d0f8e61239301dd6827171e7d3943d2af19615d229a25051b4b3b8354a487ae2`.
Compared again 2026-11-15 (the combined gate's tree): `base.html` as committed, without the
toolbar assistant's Assistant button and chat panel shell, which are not in this tree (they land
with the assistant's own change); nothing in the In progress chip or its list moves, so every
verdict below stands; compared by the template's diff. Templates sha256 before (base.html with
them): `6545a4dcc80cdee007762f2b64fe63665aa82f0851c48892655724614020d43e`.
Compared again 2026-11-15 (the operator: "The status popover: one line per item ("Failed:
request rejected. Details on the card"), never overflowing"): each line of a running and a
finished row is one line (`.ip-line`: no wrap, cut with an ellipsis by the stylesheet), its
whole words on its hover, the row's text taking the room beside its buttons; an AI
troubleshooting row's badge says its outcome in a word or two (`troubleshoot_job.outcome`:
failed, plan proposed, no plan) and its line the reason's first clause and "Details on the
card", where a plan it proposed drew red "failed" before. Nothing else in the chip or its list
moves and no element is added; compared by the template's diff and tests/test_fixit_job.py
(`TestTheFinishedRow`), not by new shots.
Compared again 2026-11-18 (the skip-mode debt, docs/FAST_LANE_DEBT.md; 93120b2f and a61bb071): `_in_progress.html`'s chip carries `data-draws-state` (a live redraw never holds it under the pointer; nothing drawn moves) and its list's row opens a run's own home where it has one (93120b2f); `base.html`'s sidebar gains Fixes under TROUBLESHOOTING, after Incidents (a61bb071, Troubleshooting › Fixes, board fixes-list), and the top bar's Assistant button and panel are drawn only while the Assistant is on (Settings › Installation › AI, off by default; the operator, 2026-11-16). Shot again from this tree (`in-progress-idle`, `-running`, `-finished` at 1440 and 390, `reattach-running` and `-result` at 1440 and 390; tests/test_board_shots.py's `test_in_progress`) and read region by region against this record's verdicts: every verdict stands; the chip, its list and the go-to box are where they were, and the top bar without the Assistant is the bar before P7 (the Assistant's own verdicts above are of its button while on). The v66 boards are the canvas's, not on disk, so they were not re-shot. The sidebar's Fixes is compared in docs/fidelity/fixes.md; the Assistant off by default is logged once (docs/STANDING_APPROVAL_LOG.md, "The Assistant is drawn only while it is on"). Templates sha256 before: `b4aae21918542f36a93719ad970f3832a09ef4ac0ffecceda8320932fc939ef1`.
Compared again 2026-11-24 (the week plan's Stage 4, docs/design/assistant.md as amended 2026-11-23, "Greyed out when AI is off"): `base.html`'s Assistant button is drawn on every page again, where board P7 draws it: while the Assistant is off, disabled with where to turn it on as its title; while it is on and hosted AI is off, greyed (`asb-off`) and still opening the panel, whose Ask says why. Its panel's shell is drawn only while the Assistant is on, as before. Nothing in the In progress chip, its list or the go-to box moves, so every verdict below stands, and the Assistant's verdicts above (its button while on) stand; the off state is a deviation from P7, which draws none (log: "The Assistant's button is drawn disabled while it is off", which supersedes "The Assistant is drawn only while it is on"). Compared by the templates' diff and tests/test_ai_assistant_stage2.py's pages, not by new shots. Templates sha256 before: `c73e23a9f59f85ed40d60dd46c1f7b5b787f197c116f4fb88ea1cdb4c1751acb`.
Compared again 2026-11-25 (the shared frame, Stage 5 step 1; the operator's GUI pick: "the assistant is a side panel the page reflows around, not a drawer over a dimmed page"): `base.html`'s body carries `side-open` while the assistant's or the help's side panel is open, and at 1100 px and wider the page's frame gives up the panel's width, so the page reflows beside the panel and nothing is under it; narrower, the panel covers the page's edge as before. No region of this screen moved while no panel is open, and none is drawn under an open one; no deviation. Compared by the template's diff and tests/test_ai_assistant_stage2.py's `test_the_page_reflows_around_the_open_panel_never_under_it` in Firefox at 1366 wide, not by new shots. Templates sha256 before:
`b55d6874713c89f30d62e79cba460324553c970ee95f6b75c272c2eb6355b5c3`.
Compared again 2026-11-28 (the assistant as a continuous chat, board assistant-chat): `base.html`'s assistant panel shell gains its left edge's resize handle (a separator inside the panel, drawn only while the panel is open) and the page loads `nmas_assistant.js`; the frame gives up the panel's own width (`asst-open`, the width the person dragged it to) in place of the help panel's. Nothing in the In progress chip, its list or the go-to box moves, and no region of the bar changes; every verdict stands, no deviation. Compared by the template's diff, not by new shots; the panel itself is docs/fidelity/assistant-chat.md's. Templates sha256 before: `d4ed16032e9782973588de07ac0b22c9b4a0fb60cbd03b76586b1885f3b13e30`.
Compared again 2026-11-28 (the same change's follow-up): `base.html` loads `nmas_assistant.js` only where the Assistant's panel is drawn (the Assistant on). Nothing drawn changes; every verdict stands. Templates sha256 before: `3e45e31dd49fef69cdc9f794c25b81d4da77ad6e76114972a17779e097945aa8`.
Compared again 2026-11-28 (the operator: "Remove it from the sidebar"): the sidebar's Self-healing item left Troubleshooting; this page's regions are unchanged and every verdict stands (docs/STANDING_APPROVAL_LOG.md, "Sidebar: Self-healing removed"). Templates sha256 before: `7876c2bba36749e12a9386d33e426407fb5b69648c458f6b6b2b679c0b233ecc`.
Templates sha256: `2dc3cc71dd782fb7f4b00f28269369051e4513031f5c9cefce6b4323f47744eb`

**Compared again 2026-11-12 (local times, the viewer's time zone):** `base.html`'s `<body>` carries `data-tz-first` (where a verified person's first visit sends the browser's zone) only while no zone is kept for them: an attribute nothing draws, so no region moves and no shot was taken again; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times"). Templates sha256 before: `3f16fde7e5fd13c20f80a9f26cf6f655f44abfdc15e43294b340cb4820966390`.

**Hashed again 2026-11-12 for the operator's report of that day** (C3081: ""Finished, not
opened yet" keeps r7's two failed runs (16:49 and 20:12 UTC) after I press "Open the result";
they're back on every page, and the "2 failed" chip stays. Opening a result must mark it seen
PERSISTENTLY (per person, stored), so it leaves the list and the chip; add a "Dismiss" on each
entry too."). Compared region by region by the template diff, not a new shot:
- the chip and its counts: **same** (laid out as before; the counts now leave out what the
  person looking has opened or dismissed, which the model decides);
- Running now: **same**;
- a Finished row: its badge, its name and its small line **same**; on its right, Open the
  result (the same `btn btn-small`, now the submit of a small form that keeps the mark and then
  opens the page on that run's result) and, beside it, **Dismiss** (`btn-outline`, secondary),
  both in `.ip-acts`, which keeps them side by side and, at phone width, under the row's words
  as the single button was: **deviation** (boards A and B draw Open the result alone), logged
  in STANDING_APPROVAL_LOG ("In progress chip: each entry under Finished, not opened yet has two
  controls");
- the list's head: a refused mark ("Not marked dismissed: <why>.") and an unreadable store
  ("What you have opened could not be read (<why>): every finished run is listed …") drawn in
  the unread line's danger style, as "Could not read what runs in …" is: **deviation**, the
  same line (the boards draw no refusal);
- the empty list's note: "until you open it or dismiss it": wording.
The two buttons' form posts to `/v2/operations/seen` (a v2 route, `v2.seen_run`); the address
draws nothing. The browser check (tests/test_v2_layout_in_a_browser.py's chip at its widest, 320 to 1280 px)
was run with the two buttons on each finished row. Templates sha256 before:
`a2c1502cf47dfe2d48b38321b54cae60ca439bef45c988e6e3866c366369f654`.

**Hashed again 2026-11-11 for where a result opens** (the operator, that day: "4. The result
opens on the device page for now; once the incident page exists, 'Open the result' goes to the
incident's URL."): `_in_progress.html`'s "Open the result" takes its address from the one
macro that builds it (`run_href`, `_macros.html`), which gives the address it had: the device's
page. Nothing drawn moved. Templates sha256 before:
`49241666d3bfd9117c63bad30b7aa46eda4d5acc0c3d2b69f7ec8f233c7189a0`.

**Hashed again 2026-11-11 for the operator's request of that day**, after a re-subscribe of r7
that "disappeared from 'running' with NO outcome shown, the row unchanged, and nothing under
'Finished, not opened yet'" ("Every operation and heal ends with a visible outcome on its card
and under 'Finished' (success / partial / failed, with the steps taken)"). `_in_progress.html`
gains one phrase on a finished row's small line, "· N steps recorded", drawn only for a run
that keeps its steps (a self-healing run, a telemetry re-subscribe); the rows themselves, the
chip and its counts are laid out as before. What the list holds changed in the model, not the
template: such a run is one running row named for the run, and is listed under Finished (a
re-subscribe also from its record, after a restart). The step count is not on boards A and B:
**deviation**, logged in STANDING_APPROVAL_LOG ("In progress chip: a self-healing run and a
telemetry re-subscribe are listed"). Compared by the template diff and the list
tests/test_run_outcomes.py draws, not a new shot. Templates sha256 before:
`91825ece62deac298aab68538f922efbd1804a937f050db1604671b3cbf75cef`.

**Compared again 2026-11-03 ~01:3x UTC, P7's top bar measured** (test_v2_layout_in_a_browser's
top bar at 320 to 1280 px, every item at its widest): with the word, Assistant ran the bar 64 px
past 1280, 52 past 1024 and 17 to 24 past 768, and the mark alone 21 past 430 and 33 past 320.
Now below 1366 px it is the AI mark alone, its name on hover and to a reader, as board P7's 1f
draws it at phone width and as Update available is "Update" there; laptops (861 to 1366 px)
take 12 px gaps for 16; phones 6 px (640 and under) and 2 px (360 and under), nothing hidden.
At 1440 the bar is unchanged and the word is drawn, as 1a draws it. One deviation, logged in
docs/STANDING_APPROVAL_LOG.md ("P7's Assistant at laptop width") and PHASE8_PLAN 19.1: the
board draws laptops with nothing; the built bar shows the mark alone there. The panel's shell
is all base.html carries; its head and body are drawn when it first opens
(routes/assistant_v2.panel), unchanged as drawn. The in-progress slot is untouched.
Templates sha256 before: `b85ecf999bebf4284fa4bc921b523fe3cd18a5072309c3fcf29081ce80cabada`.

**Compared again 2026-11-03 ~00:5x UTC for card P7's stage 1** (board P7, part 1a): the top bar
gains **AI Assistant** after the AI chip and before Live, as board P7 draws it, and the frame its
panel, in the help panel's place (one of the two at a time; Esc closes either). The in-progress
slot this record compares is untouched. Compared by reading against board P7's 1a. One
deviation, logged in docs/STANDING_APPROVAL_LOG.md ("P7 stage 1 built"): the board greys the
button with its reason when the assistant cannot answer (1b to 1e); the built button always
opens the panel, whose Ask is the AI control and draws the reason in full. That is the AI
controls' rule, a control's state drawn by its own template. Templates sha256 before:
`7d57f40dc4dbcf397013bd1b2ee46dc711ac9bc57cc8718daa376d4b0d8f005d`.
(2026-11-02, C2283, board FC's FC2: the sidebar gains Intent, first under SOURCE OF TRUTH as
the board draws it (tests/test_v2_pages.py pins the order); read against the regions below,
nothing in the top bar, the chip or its list moves, every verdict stands. Before:
`a8f93ae1dc59e0c4e84b8504fe0947e0b0283f307c40fc966d9ff289c9adf451`.)
(2026-11-02, C2268: `base.html`'s AI spend panel also listens for `nmas:ai_spend`, its re-read on
a recorded call, so the page-wide hold applies to it; nothing drawn changed. Before:
`5ed96ad348b4c6d7f319f90d6f982562d811dfa23a6d83772e46ae0fa364d263`.)
Hash rewritten 2026-10-23 at the Phase B merge: the run page's links name their network as `?list=` (they said `?list_name=`), and the run page's Devices link takes the page's network; no drawn text, region or control moved, every verdict stands.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Nothing running, nothing unopened (A1, B1) | no chip | no chip: the slot is empty and takes no room | **same** |
| The chip while operations run (A2, B2) | a blue pill with a dot, "2 running"; at phone width the dot and the count | the same, the count of rows below it; its words in its label and on hover at phone width | **same** |
| Running now (A2, B2) | "Running now · 2", a row each: device · operation, the step in the stepper's own words ("step 6 of 6"), who ("you"), since when | the same: one row per operation (C217, the job's own row folded into its device's), the step from the card's stepper where it has one, else the hold's own words; its network after the time; "no progress: may be stuck" when the hold has not moved for ten minutes | **same** |
| Open its card (A2, B2) | on every row, opening its card where it runs | on every device's row: it opens the device's page, which reopens the card (board C); a row whose run has its own home (an approved plan's step: its incident's card, since 93120b2f) opens that home; a device held by an operation no card reopens says "Open <device>" | **same** |
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
