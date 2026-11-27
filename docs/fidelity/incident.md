# Fidelity: one incident's own page (2026-11-11)

Board: incident-page (text only, kept with the operator's reports, incident-page-board.md),
parts B (the page), C (its addresses) and F (its states), with E1's sizes; signed off under the
Phase 7 mode 2026-11-11 (docs/STANDING_APPROVAL_LOG.md, "Board incident-page B (one incident's
own page"). The board is words and tables, with no drawing to shoot.

**Compared from shots of the built page beside the board's text.** tests/test_board_shots.py
`test_incident` shoots the page as built at 1920 (the board's E1), 1280 and phone width, on
the heal's lab with each incident planted by the heal modules' own writers: a heal done with no
human (`incident-healed`, the board's B2), a heal rolled back, its verify failed
(`incident-failed`, B3's shape), a can't-fix standing in dry run (`incident-open`, B1 without a
known fix) and an id no record holds (`incident-unknown`). The fold's line, a related incident,
an unreadable record and an incident past the ones kept were read from the HTML
tests/test_incident_page.py renders.

This is the page's first slice: a read-only page for a self-healing incident (an `hi-` id).
A region the board draws for a later slice is **later**, naming the slice of the build plan.

**Compared again 2026-11-12, brought onto main's five-stage stepper:** What Mercury has done
draws the heal's five stages through the card its device's page draws (`run_card.named_heal`,
else a decision's `run_card.steps_card`), and who the fix was by reads "by Mercury's
self-healing · policy set by <display name>"; the live region also redraws on each step of a
running heal. Compared by the template diff and the HTML tests/test_incident_page.py renders
(its stages byte for byte the device page's), and by the shots `test_incident` takes again.
Templates sha256 before: `7ba70d7de701cee06dff32e0c539ba8d86183cb5c9a493dfc397fbd213fb843f`.

**Compared again 2026-11-12, the AI troubleshooting section (the fix-it plan's S4):** board
recurring-fixes v2 (text only, kept with the operator's reports, recurring-fixes-board-v2.md),
every state but the AI's own, and its step 8's write-up on its own page, compared with the
section and the write-up's page as tests/test_fixit_section_v2.py renders them on r2's lab (a
self-healing incident from two lost-stream alerts, a real Re-subscribe run that read no data,
Mercury's diagnosis on its real captures): the nothing-tried, STOP, proposed (flagged),
cancelled, handed-over, capped and resolved states, the operation's card opened from the
proposal, and the write-up's page. The rows from "AI troubleshooting: the totals" down replace
the frame's one row. Templates sha256 before: `7aa81346a92e1720d612598579774f4e26de434d91dacaee2db881983819834c`.

**Compared again 2026-11-12, the AI's own states (the fix-it plan's S5):** board
recurring-fixes v2, steps 2 and 3 (Troubleshoot with AI, its figures and states in which
nothing is spent; the proposed, gap and answer-unchecked states), compared with the section as
tests/test_fixit_troubleshoot.py renders it on the same lab through the real gateway, the
provider answering a stand-in of the schema's shape: nothing tried with Add what you know and
Troubleshoot with AI, the STOP with Retry's two presses, an AI proposal flagged as a repeat, a
gap, an answer that could not be checked, the AI control's states (hosted AI off, no key, the
day cap, the provider's limit, the record unreadable) and the mode off. Compared by the
template diff and that HTML; no new shot was taken (the board is text). The rows Retry with
more information, The proposal, Nothing tried, The head and AI off are drawn again, and The
gap and Answer unchecked are added. Templates sha256 before: `ecfb220f7aa8d7f158980c24a3aa53a360889b79f59d88141a3949e76ca40264`.

**Compared again 2026-11-13, the operator's test of the page ("structure PASSES. Fixes, as
one slice before the full run"):** a declared fault drill's incident draws a "Drill" badge
beside its state, its hover the drill's `fd-` id, who declared it and the fault it expected;
the resolved span ends when the incident ended (a fixed one at its verify), and so does the
timeline's "the incident closed", never the act's start its store kept as the close; TIME TO
REPAIR's span and its hover's words (no time worded there: the times are the cells'). The
stepper's Fixing and Done sentences changed in the shared heal card, not in this page's
templates. Compared by the template diff and the page tests/test_incident_page.py draws and
opens in Firefox, not a new shot. Templates sha256 before:
`e1db7ab84d6ce006eda3411be83278ae90190fbb692b3285c9c28d187f04c0fa`.

**Compared again 2026-11-13 (C3290's last gap: local times on the incident page and its
hand-over):** `incident.html` is drawn under `{% filter times %}` and The record's values
through `times`, so every instant a builder wrote into the page's words (a step's "… · <instant>",
a decision's "at …", the store's close, a hand-over's time) is `_macros.clock`'s, the viewer's
own, its UTC on hover, in the same element and position; The record's names lose "(UTC)"
("Detected", "Verify failed", "Closed, by its act's record step"), and its note says the times
are the viewer's. Its identities stay as recorded (no `people`). `incident_handover.html` is
drawn under `{% filter times %}`: its builder (modules/fixit/handover.py) writes "Handed over
<instant>", "since <instant>" and "Attempt n, <instant>:", and the Markdown download and a
team's message, which leave Mercury, say them in UTC as before. Compared by the template diff
and the pages tests/test_incident_page.py and tests/test_fixit_section_v2.py draw, not a new
shot; no region moved. Templates sha256 before:
`b6b2551f696e627a64d33490d5cc6dd1037ec35eb4741dac13332038ccd57d99`.

Templates compared: templates/v2/incident.html, templates/v2/_fixit_section.html, templates/v2/incident_handover.html, templates/v2/_modal.html, templates/v2/_saved_plans_slot.html, templates/v2/_saved_plans_saves.html, templates/v2/_inc_story.html, templates/v2/_inc_step.html, templates/v2/_inc_proof.html
Compared again 2026-11-13 (the operator's approved rule, "raw UTC anywhere left"; C3290): `incident.html` draws Mercury's diagnosis words and What to do's words, and `_fixit_section.html` a step's words and a hypothesis's claim, through `times` (routes/v2.py), so an instant the lost-stream runbook writes is `_macros.clock`'s, in the viewer's kept zone with the UTC instant on hover. No element moves and no region's verdict moved; compared by the templates' diff, not by new shots; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times: the words Python builds"). Templates sha256 before: `caa59cdd04847e4a289f07d97ef83060314717f80291ef74e4876c74d2dfdae7`.
**Compared again 2026-11-13 (the GUI review's item 2, C3450, with C3487 and C3488; the operator, 2026-11-13: "Build review items 1, 2, 5, 6, 9 first (in that order)"): one state, and the page's own action.** The review measured the page in its planted states: 0 buttons on four of them, What to do sending the person back to Needs attention, and the lost-stream incident's header reading "Open · No person needed" above a section reading "Stopped … Nothing more runs unless you choose". Compared from shots at 1280 px, before and after, of the same planted incidents (kept with the operator's reports: `2-incident-cantfix`, `-rolledback`, `-healed`, `-proposal`, `-stream-ready`, `-stream-stopped`, each `-before` and `-after`, and `-proposal-after-pressed` and `-stream-stopped-after-pressed` with the action's card open), read beside the board's B1 to B4 and F, and at phone width by tests/test_incident_stream.py's real-browser test (the one button, its card under it, nothing scrolling sideways). Region by region: **the header**: the state badge is the one function's answer, and the level never reads "No person needed" beside "Needs a person" (a lost stream draws its item's own level, "Warning", as B1 does); no other cell moved. **What's wrong**: a lost stream leads with its item's sentence, whether the device answers and what Mercury cannot see; other incidents as before. **What Mercury has done**: Mercury's diagnosis in full under the stages, in place of one line. **What to do**: the state in words, what the item says to do, the item's one action as the one primary button (measured in the shots: 0 primary buttons before on every page; after, 1 on each page that needs a person and 0 on the healed one), its card under the button on its press, Diagnose… beside it, how the item clears, then the links. **AI troubleshooting**: carries the page's state; "What to do above says where one is started." only where a person is needed; a can't-fix's AI analysis in full above its advisory line. **Seen before**: a card of its own after Evidence, for a lost stream. **The record**: Tier, and a decision's own mode, fix kind and program hash where nothing has run. The rows The state, One state in every section, The level, What's wrong: a lost stream, Mercury's diagnosis in full, What to do, Nothing tried, Seen before and The AI analysis in full are drawn again or added; every deviation is logged (docs/STANDING_APPROVAL_LOG.md, "Incident page: one state for the whole page", "Incident page: What to do carries the item's one action", "Incident page: what the item kept under Details"). Templates sha256 before: `faf97cda35f17a4ffcaa22148501009d3686d1598a9a77b554bb1a4acf874c86`.
**Compared again 2026-11-13 (the GUI review's items 5 and 6, C3453 and C3454; the operator approved them 2026-11-13; provisional, operator review pending): titles in plain words, and each fact once.** The review measured the heading as the configuration line (95 characters, two lines at 1280 px, again as the breadcrumb's last crumb) and "verify failed" five times on the rolled-back page, with the can't-fix stepper's one stage "Decide failed" in red. Compared from the pages tests/test_incident_titles.py draws for thirteen planted incidents (before and after, read from the HTML: the titles went from 76 to 120 characters to 42 to 67, "verify failed" on the rolled-back page from 5 to 1) and its real-browser test at 1280 px (the longest title one line, the crumb one line, cut with an ellipsis at 500 px), not a new shot. Region by region: **the breadcrumb** and **the title** (one builder, `said.title`; the approved-fix ending ", put back by <name>"); **the four times**, **TIME TO REPAIR** and **one line per attempt** say their state's words, why on the cells' hover; **What's wrong** quotes the configuration line ("What changed on <device>: …" where no cause is kept); **What Mercury has done**'s stages each at most 12 words, a failure's why once, a can't-fix "Can't fix: needs a person" in amber (the stepper's own record, docs/fidelity/stepper.md). The timeline says each attempt's outcome by its mark. Logged (docs/STANDING_APPROVAL_LOG.md, "Incident page: titles in plain words", "Incident page: each fact once"). Templates sha256 before: `5cab3c461862c66492c2a31a7cf588f27ae2633bacb782fa650ea653d7dbb6cc`.
**Compared again 2026-11-13 (the GUI review's item 8, C3455; the operator approved it 2026-11-13; provisional, operator review pending): AI troubleshooting's three choices drawn alike, each a modal.** The review measured the section's three choices drawn three ways (two disclosures at either end, a button between them), What it found two paragraphs of addresses, ports and connection numbers per subscription, and the repeat flag naming the parameter hash. Compared from shots at 1280 px and 390 px of the planted ready, stopped and proposed states (tests/test_fixit_section_v2.py's lab), each choice's modal opened, read beside the board's STOP, Retry and Hand over regions, before (from the HTML) and after: **The STOP**: What it found is one line per subscription, its state in words and its flag's kind, opening to its checks; the three choices are three buttons in one row, alike and secondary. **Retry with more information** and **Hand over**: each its own modal, anchored to its button (just below it, or above it where the window has no room below), the focus inside it, closed by Cancel or Escape with the focus back on the button; a press in it answered in the section in place, the focus on the answer. **Cancel**: its modal is its confirm (Cancel troubleshooting, Keep troubleshooting). **The proposal**: Open the fix's card… secondary. **A repeated proposal**: no hash in the flag; the hash in **The record**. **Nothing tried**: Troubleshoot with AI secondary, Hand over… alone in the row. The section draws no primary button (the page's one is What to do's, C3450); `_modal.html`, v2's first modal, is compared here as the section's. Every deviation is logged (docs/STANDING_APPROVAL_LOG.md, "AI troubleshooting: three choices drawn alike, each a modal", "AI troubleshooting: the repeat's hash in The record"). Templates sha256 before: `542df2d201fde02d8e9be2003aef266e951189f6129db9db50306040ad02aeee`.
**Compared again 2026-11-13 (board T, the sidebar's Troubleshooting section; the GUI review's IN9; provisional, operator review pending): the breadcrumb leads from the incident's home.** Board T's part 2: "the breadcrumb becomes Incidents › Open (or Closed) › the title". Built: Incidents / Open (or Closed, for a resolved incident) / the title, each crumb a link to Troubleshooting › Incidents and its tab, in the app's crumb separator; an incident with no page yet reads Incidents / Incident <id>; the sidebar marks Incidents current on the page. The breadcrumb region: **same** as board T draws it (it said "Needs attention /", IN9). No other region moves; compared by the template's diff and the pages tests/test_incidents_list_v2.py draws, not by new shots; the list itself is compared in `incidents.md`. Templates sha256 before: `436e2d00c654bcfc921a51d7167e943b3b0f23c4ddba30a2ce4fb1def57e0d47`.
**Compared again 2026-11-14 (C3078; the Tier 1 review's item 10): What to do's opener names the collector step.** A proposal naming the re-subscribe with the collector step opens its card with the step on, and the opener says so: "Close the collector's stale session for <device>, then re-subscribe (<ids>)…", its How does this work? to the step's section; any other re-subscribe reads as before. What to do's region: **same** (one opener, its words the operation's). No other region moves; compared by the template's diff and the pages tests/test_fixit_section_v2.py draws, not by new shots; logged (docs/STANDING_APPROVAL_LOG.md, the collector step's line). Templates sha256 before: `9c5f0fa8b300ebec23b0545bc1cf145962731afad8d8e756dad13f7c58cd2702`.
Compared again 2026-11-15 (Gate 2): every sentence on the Fixing it card naming the automatic
troubleshooting switch links to it, the AI toggle on Needs attention's control strip for the
network (the operator, 2026-11-15: the status line's "automatic troubleshooting" and the
Costs line's "on/off for <network>"), and a hand-over's, the time to repair's and a held run's
person are drawn by display name (C3715). The words and their places are unchanged; compared
by the templates' diff and tests/test_fixit_start_spend.py's page, not by new shots; logged
(docs/STANDING_APPROVAL_LOG.md, "Records name people by display name on every v2 screen
(C3715)"). Templates sha256 before: `fbfb0238afafd6fa251ca6d09709a7a31c5930c04aa4cffdcd04d17fd79bbc13`.
Compared again 2026-11-15, the saved plans (Gate 1b; board saved-plans S, docs/boards/saved-plans.html, signed off under the Phase 7 mode, docs/STANDING_APPROVAL_LOG.md, "Board saved-plans S"): `_fixit_section.html` gains one include line at the foot of "Fixing it", `_saved_plans_slot.html`, which asks for `_saved_plans_saves.html` in place (`saved_plans_v2.card`). Compared by the templates and the HTML tests/test_saved_plans_v2.py renders beside the board, not by new shots; its regions are the last table below. Templates sha256 before: `1c2fb8376b40f5e83ca3d1c7f5510049ae6092dcf389962dbe5471c66f3651e9`.
Compared again 2026-11-15 (tests/test_display_names_drawn.py): `_saved_plans_saves.html` draws a right's refusal and a press's answer through the `people` filter, so a person is named by display name, never an identity (C3715); the words and their places are unchanged. Compared by the template's diff and tests/test_saved_plans_v2.py's page, not by new shots. Templates sha256 before: `ed9aee3efc4837238d8bc72e8c63b5a2cf1c27d4d9e66e4e9d2c25993f5a97ea`.
Compared again 2026-11-15 (the operator: "no red "Check guards failed" or red "can't fix"
chip for a decision working as designed; drop "heal_analysis not run: feature_off" and "not
diagnosed: no adjacency" noise from the default view (details only)"; C3738, C3540): What
Mercury has done's chip for a can't-fix is neutral (`level` "decision", its decision's words on
the hover), as a hold's is; its stepper draws the standing decision's steps, a held one
neutral (stepper.md, the `held` state); Mercury's diagnosis not made is one closed line, "Not
made", its why inside; an AI analysis not run (nothing sent) is one muted line inside The AI's
analysis, its summary "· not run", the recorded words on its hover. No element moves; compared
by the templates' diff and tests/test_incident_page_once.py (`TestADecisionWorkingAsDesignedIsNeverRed`,
`TestNoiseIsOneLevelDown`), not by new shots. In the same gate (the operator's items C and D):
the AI troubleshooting section's What the AI found is drawn collapsed under "Previous answer,
<time>, prompt v<n>" while a newer investigation stands, and an answer resting on another
incident's call is one muted line saying it is superseded, its content withheld; no element
moves (tests/test_fixit_answer_superseded.py).

Compared again 2026-11-15 (C3797, the investigation loop): How to fix it's primary, for an
answer with no plan that names the read it lacked, is the link "Run <read> in Show commands"
(Show commands opened with the command and the device filled in), Ask the AI again beside it
as secondary and Hand over… a link, where it drew Ask the AI again alone or, past the cap,
nothing to press; the AI's cost line says "at most 4 calls" (the investigation's worst case)
where it said two. No region moves and no element is added beyond the one link;
tests/test_fixit_lacked_read.py.
**Compared again 2026-11-18 (the skip-mode debt, docs/FAST_LANE_DEBT.md; becced07 to d9781394,
eighteen commits; board R5's screens 3 to 6 and the GUI redesign brief's board 4.1).** The page
since: board R5's one card, simple by default (docs/boards/r5-simple-by-default.html, approved by
the operator 2026-11-15 with four changes; becced07), Save the approval (6b91dc45), the live
stepper on the card while the AI investigates or a plan or saved script runs (bad52d54,
2f368606; `_inc_step.html`, THE stepper for these runs by the operator's decision 7), the plan's
exact commands (db800983), the preflight's reused reads with their age (55c8a8eb), a refused
plan's primary Ask the AI again (fb8be7e8), Fixed's proof and the AI's calls beside Approve
(00c70e0f; `_inc_proof.html`), Fixed on its verify with its tail (e400a31f), a saved fix as one
object (3a659d6b, a61bb071), folds kept open through a redraw (1e514200), the AI cost words
(7b0bb884), and above the card the story at a glance (aea00330; `_inc_story.html`, board 4.1,
design/incident-detail-proposed.html, self-signed under the Phase 7 mode 2026-11-18), whose
summary carries the next step (d9781394, the operator's decision 15). `_inc_story.html`,
`_inc_step.html` and `_inc_proof.html` join the compared list (they were in no record). Shots
from this tree: `incident-healed`, `-failed`, `-open`, `-unknown` at 1920, 1280 and 390
(tests/test_board_shots.py's `test_incident`), the debt pass's own `debt-incident-story` (the
can't-fix) and `debt-r5-incident` at 1920 or 1280 and 390, beside `debt-incident-story-board`
(design/incident-detail-proposed.html at 1920, 1280 and 390; its own shots in design/shots/) and
R5's file shot whole (`debt-r5-needs-attention-board`, screens 3 to 6). No shot reaches the AI's
states, a plan ready to approve or a run in progress (the shots' world holds no AI call); those
regions are read from the templates against the boards. Templates sha256 before:
`08728c041a801cb1c70abc7fec8f45456863d700d149192c0ec9d06dd3169570` (without the three).

| Region | Board | Built | Verdict |
|---|---|---|---|
| 4.1: the header | the title, the state chip ("FIX PROPOSED"), "open 6 m 49 s · opened … · live", severity, the AI's model and cost at the right | the breadcrumb (Incidents / Open / the title), then the lifecycle bar; the title, its level and its impact on R5's card below, the AI's model and cost in the rail's AI call | **deviation** (log: The incident page's story at a glance) |
| 4.1: the lifecycle bar | eight stages (Detected, Self-heal tried, Diagnosing, Fix proposed, Approved, Applying, Verifying, Healed), each its time and words, the next ringed | the same eight from their own records; a stage self-healing's own fix needs not dashed, "not needed: self-healing's own fix"; Applying "not fixed" and Healed "not healed" red for a rolled-back heal; its Verifying stage is drawn done (green) when the verify failed (shot `incident-failed`; registered by the debt pass) | **same** (the bar; Verifying's state is a finding) |
| 4.1: the summary | What, Likely cause, Evidence (chips), Next, the card's orange edge | the same four lines; Next the page's next step (decision 15), "Nothing to do: resolved in 1,118 s" on a healed incident (seconds, not the stepper's one duration; registered by the debt pass); a can't-fix's Next still names `scripts/nmas-removal-probe` (C3506, open) | **same** (the lines; their words are findings) |
| 4.1: the rail | Confidence, Related, AI call | Confidence with "needs: …" for a likelihood, a severity and a risk Mercury does not record; Related and AI call drawn when the incident has them (none in the shots' world) | **same** |
| 4.1: the plan card as a runbook view | the plan's code block, Approve, each step's state under it | R5's card's plan (its exact commands, "step n of N", Approve) | **later** (the log's "Not built tonight": the plan card as a runbook view) |
| 4.1: hypotheses | A chosen, B still open, C ruled out by Mercury, each with its reason | drawn from the proposal's hypotheses when the AI proposed one; "needs: the AI's own ruled-out hypotheses" | **same** |
| 4.1: phone (390) | the title and state chip, then the lifecycle bar vertical, then the summary | R5's card first (the title, its level and impact, its action), then the lifecycle bar vertical, then the summary | **deviation** (log: The incident page at phone width: R5's card first) |
| R5: the card (screens 3 to 5) | the title; one status line; one primary action plus at most one link; one Details | the same; the status line left out where the story's Next says it (decision 15); a fixed incident's title the incident's one title | **deviation** (log: R5 incident page: the title once fixed) |
| R5: the impact | "1 host offline (h1); the rest of the network is unaffected" | Mercury's impact table's words for the condition ("Not known: Mercury's table holds no impact for this kind of incident." where it has none) | **deviation** (log: R5 incident page: the impact's words) |
| R5: while the AI investigates (screen 3, change 3) | one live progress step from the job's step record | the incident card's stepper: done steps ticked with their seconds, the current one live with its step (`_inc_step.html`) | **deviation** (log: A plan's run on the incident card's stepper) |
| R5: the plan ready to approve (screen 4) | "The plan: on s1, in config mode, never saved: <lines>", Checks first, Then verifies, Approve, Modify or deny…, Details | the same: the exact commands as a code block from what the hash binds, "step n of N", the preflight's reads with their age, Approve; beside it the AI's calls; a refused plan's primary Ask the AI again | **deviation** (log: The incident card: Fixed's proof, the AI's calls beside Approve and a refused plan's Ask the AI again) |
| R5: after a verified fix (screen 5) | "Fixed at 14:29, verified; h1 is back online.", How it was fixed, Details | Fixed on its verify, its proof under it (`_inc_proof.html`: the reads that prove it), then the tail (the save, the full read, the golden, the read again) that flags any failure | **deviation** (log: The incident card: Fixed's proof, the AI's calls beside Approve and a refused plan's Ask the AI again) |
| R5: Save this fix (screen 5) | "Saves in Dry run: Mercury records what it would do the next time, until you promote it", Save, Not now, Customize… | "Mercury will handle this automatically when self-healing is on", Save (saved Automatic, promoted by the person saving it), Not now, Customize… holding How it runs with Dry run | **deviation** (log: Saving a verified fix is the approval) |
| R5: right after Save (screen 5b) | "Saved: BPDU guard recovery (access ports), Dry run. Promote…" | "Saved: <name>, Automatic when self-healing is on.", the name linking the fix's own page (Troubleshooting › Fixes) | **deviation** (log: Saving a verified fix is the approval) |
| R5: the saved card's Details and Not now (screens 5 and 6) | no Details on the saved card; Not now hides the offer | one Details (the optional reusable action, the scripts and shapes lists); "Not saved: put off by <name>." with Save this fix… | **deviation** (log: R5 incident page: the saved card's Details), and for Not now, "R5 incident page: Not now's line" |
| The unknown id | not drawn (board F: the states) | "No incident hi-000000000000 is recorded.", where it looked and why, Open Needs attention · Open History | **same** |

Hashed again 2026-11-23 for C3970 (the operator's ruling of 2026-11-23: the reason is stated
once, where it is; other places link to it): when a fix's own stage failed, the card's status
line says "It needs a person: its fix did not heal it. The stage that failed under What Mercury
has done says why", where it repeated that stage's sentence, and the card's links gain "Why:
the stage that failed" (`#inc-done`) before Open <device>. No element moves; the line keeps
its place and its state. Compared by the templates' diff and the tests' render
(tests/test_incident_titles.py `TestEachFactOnce`), not by new shots: the shots are owed in the
full pass (docs/FAST_LANE_DEBT.md). Templates sha256 before:
`c7874111c11285de3264ae2c4173e1326d1de16148692cdf6351026fe6f2e83d`.

Hashed again 2026-11-23 for the merge of rulings-words (ruling 3 of 2026-11-18, 33bf385f:
"Save names the count and the devices it will run on. No new confirm."): `_saved_plans_saves.html`'s
Save card's impact line and the Save's title gain the "runs on" words (how many other open
incidents it runs the fix on, and their devices). No region moves. Compared by the template
diff, not by new shots (owed in the full pass, docs/FAST_LANE_DEBT.md). Templates sha256
before: `468a48d7c485e7698a8d7eed5d4baf027cc551b7b94b5b8a0ef8a160085de783`.

Hashed again 2026-11-24 for C4205 (the review of 33bf385f, MEDIUM): the Save card's "runs on"
words move into `_saved_plans_runs_on.html`, included where they were, and are redrawn in place
when a Customize… tick or the Dry run box changes (`saved_plans_v2.runs_on`); the Save's title
names its words as the all-ticked case ("With every field ticked: …"). No element moves and no
region's verdict moves. Compared by the templates' diff and tests/test_saved_plans_v2.py's
render, not by new shots (owed in the full pass, docs/FAST_LANE_DEBT.md). Templates sha256
before: `138c42a817d7663a935de95fea42b16ca5b0fd0076e143f8c4a13eaa934943d9`.

Compared again 2026-11-24 (C4071): `_fixit_section.html`'s comment says the R5 budgets' test is
owed (it named tests/r5_budget.py, which was never written); a comment only, nothing drawn
changes, no deviation. Templates sha256 before:
`535b035d54df9bbe38164c7b71b93831f4d237440347af78da08e1398625e1d4`.
Compared again 2026-11-25 (C4057, Save bound to the card it drew): `_saved_plans_saves.html`'s
two Save forms each carry one more hidden field, `drawn` (what the card drew, as a digest).
Nothing drawn changes, no region's verdict moved, no deviation. Compared by the template's diff
and tests/test_saved_plans_v2.py's `test_a_save_is_bound_to_the_card_it_drew`, not by new shots.
Templates sha256 before:
`f1af136880b8e19abb2b71e3517d3861882941402587b393487ae90d1198bd03`.
Compared again 2026-11-25 (C4050, Save bound to the incidents its line named):
`_saved_plans_runs_on.html`'s line holds one hidden field, `runs_on` (the other open incidents
it names, as a digest), and the default Save's `hx-include` adds the line. Nothing drawn
changes, no region's verdict moved, no deviation. Compared by the templates' diff and
tests/test_saved_plans_v2.py's
`test_a_save_whose_other_incidents_moved_is_refused_and_starts_nothing`, not by new shots.
Templates sha256 before:
`692878743ef29c51d1b75590e0a4f02b76d645ea6e913db5b44b1d61af42b5ef`.
Compared again 2026-11-25 (C4261): the saved card's Promote… menu and each listed script's
Promote draw one line, what Promote runs on now ("Promote runs it now on N open
incidents, on <devices>", the card's own counted), the button carrying the digest its press is bound to. The boards drew
Promote with no such line: a deviation, logged (docs/STANDING_APPROVAL_LOG.md, "Promote and Set
Automatic name what they run on (C4261)"). No other region moved. Compared by the template's diff
and tests/test_saved_plans_v2.py's `test_promote_names_what_it_runs_on_and_is_bound_to_it`, not
by new shots. Templates sha256 before:
`5a384c73ead8b09ccb2e81ea5a6ceb41b06b5c4709baae86ff49e5ce6de0cd46`.
Compared again 2026-11-25 (Stage 5 step 4, slice 1; the operator's GUI pick of 2026-11-25: C, with B's step timeline): `_inc_story.html` draws the story as C's document. Its four facts with no box. One line for what Mercury does not score (confidence, severity, risk), each with what it needs, where the rail drew three dashed boxes. Then sections that open: Why Mercury thinks so (open, its line the chosen hypothesis), Timeline (its line the stages reached, "1 of 8 done" on the right; opened, the eight stages running down at every width, where they ran across) and AI call (its line the model, calls and latency). Shot in Firefox at 1366 and 500 (a can't-fix and a healed incident) and read against C's incident page: the facts, the sections and their lines as C draws them; C's title and actions at the top, its sentence and its other sections (the fix, evidence, what Mercury has done, seen before, the record) are still the incident's card below (the next slice): deviations, logged once (docs/STANDING_APPROVAL_LOG.md, "Stage 5 step 4, slice 1"). Templates sha256 before:
`f877272171b2a0626ca1114816e065f058a15ba31d48d9e0bc579a8a58468ea6`.
Compared again 2026-11-25 (Stage 5 step 4, slice 2; C: the title first): `incident.html` draws the story after the incident's card at every width (the phone drew it so already, board R2), and the card is the page's head with no box, its title at C's 30 px, so the page opens with the title, its impact and its one action; `_inc_story.html` draws What only where it says more than the title. Shot in Firefox at 1366 (a can't-fix and a healed incident) and read against C's incident page: the title, its line and the action first, then the facts and the sections, as C orders them; C's sentence, and the card's Details (timings, events, what's wrong, what Mercury has done, seen before, the record) still one disclosure under the action rather than C's sections: deviations, logged once (docs/STANDING_APPROVAL_LOG.md, "Stage 5 step 4, slice 2"). Templates sha256 before:
`4ab32b39f1cbc489970089a08796b7eead96820ff1811f5d1f7e67a32fe23757`.
Compared again 2026-11-25 (Stage 5 step 4, slice 3; C: the page's parts as sections): `incident.html` draws the timings, the events, What's wrong, What Mercury has done, Seen before and The record after the story, at the page's level, each a section with a hairline above and no box, its line its summary at 17 px, where they were inside the incident card's one Details; the events' line reads "Events" where it read "Timeline", the story's lifecycle being the Timeline; Timings' line says the time to repair in the stepper's one duration (C4267). The card's own Details keeps the header's facts and notes. Shot in Firefox at 1366 (a healed incident) and read against C's incident page: the sections and their lines as C draws them; C's sentence not drawn: logged once (docs/STANDING_APPROVAL_LOG.md, "Stage 5 step 4, slice 3"). Templates sha256 before:
`3cfbbefdefa1df0f60fd09a969783a20a7c5f115558a031a93e73aa6d9cdebe6`.
Compared again 2026-11-26 (Stage 5 step 4): with no impact in Mercury's table, the line under the incident's title says "Its impact is not known: Mercury's table holds none for this kind of incident.", where it said "Not known: ..." with no subject. Every region's verdict is unchanged. Templates sha256 before:
`1216de673caee944785341c9207e1c2b9cb8abba76155bfef5cf08e84cf9707a`.
Compared again 2026-11-26 (C4278): text drawn with a capital first letter goes through `capital` (`words.capital`), never Jinja's `capitalize`, which lowered every letter after the first (a person's reason, a network's or product's name). No region moves; every verdict is unchanged. Templates sha256 before:
`e0eb724956256afa3e349b88d3570993dace8b55dfa1b693800981872da00f28`.
Compared again 2026-11-26 (Stage 5 step 4, C: the answer first): the story's facts open with Next, then the likely cause and the evidence, where Next was their last line. One deviation logged (Stage 5 step 4: Next leads the incident's facts). Templates sha256 before:
`80e01f7314a19e620b7d9bafbbd6eec5a2ef2bd9719cdcec4124492ffac24baf`.
Compared again 2026-11-27 (Stage 5 step 4, C's order; the board design/proposals/C-document/worst-2.html, the operator's pick of 2026-11-25): the incident card's action row moved from under its impact and status lines to right under its title, as C draws "Review the fix… · Ask the assistant" under the title; the incident's id and span moved from the Details head to a line of its own under the card's lines (C's "Incident hi-0214 · open 14 min"), and Timings' heading says "not repaired yet" for an open incident instead of repeating the start. Shot at 1366 in the suite's world (a can't-fix incident): the title, Open edge-b, the impact line, "Incident hi-… · open since … (67 d ago)", Details. Deviation: C's line also says "updated 6 s ago", which is not drawn: the page redraws itself when its sources announce (the top bar's Live), so the age would only ever read seconds (log: Stage 5 step 4: the incident's action row under its title). Templates sha256 before:
`b0e996fd9cc5a0fee24e151a78f9e97ff3aeae109aa073259737140d1ffad8ad`.
Compared again 2026-11-27 (the operator's decision, C4090's third record, (b): "Remove the P.net_zero.lines loop from _inc_proof.html (keep the words)"): a Fixed incident's proof draws the net-zero check's words alone, without the lines a run changed; a run whose configuration after differs from before is rolled back and refused, so no Fixed proof holds such lines. Compared by the template's diff, not a new shot: no other region moves. Templates sha256 before:
`39b0f10e93fd1ecffaf2bceb61c0b785d207c5f38515f7b0efee69c57d6d1e31`.
Templates sha256: `2686965697cc597836be378b65846c2b41a982809b7d826ecf9e01fe3ebb17ab`
Templates sha256 before the saved plans card said a right's holders unset (2026-11-15, Gate 1b's review, item 7; the row "Rights not set" below): `770515ac382839dde54d1ae789920a7578375acf87fe6fb9d221961273361976`
Templates sha256 before C3725's session moved from a press to the proposal's record (2026-11-15, the operator; the session row below): `90974cd13f0f0f2aece5e005c3cc5e3c2c21726aa22192e6535bce1ca4953909`
Templates sha256 before the verify-speed gate's page fixes (2026-11-14, C3725, C3727, C3728, C3729, below): `b8969275f9560c0d423e154d881391989736eb6548a35bb27ab4020fa5542a6c`
Templates sha256 before the plan's step list was renamed (2026-11-15, CI #1733: `fixit-steps` and `fixit-step` read as a progress stepper to tests/test_one_stepper.py's scan, while the list is the plan's proposed steps with their preflight, never progress; renamed `fixit-plan-items` and `fixit-plan-item`, no region drawn differently, every verdict unchanged): `0ffee72b260f1231580df438c8fe235c57d24451decbd8f9947488daf0cf3545`
Templates sha256 before the refused plan in The record and Modify's drawn figures (2026-11-14, Part A's kept guarantees; no region moves: The record gains one line for a plan refused at its preflight, its hash and a repeating step's parameter hash with the attempt it is the same as, which the AI3 row above already says The record holds; Modify's modal carries the spend and cap it was drawn under as hidden fields, nothing drawn): `3da658fb88c10c11739d1bfb9d1abc1b73dca61ea1350ccb2b94479206faf6f2`
Templates sha256 before the bottom line's evidence and since, and Approve as THE confirm pattern (2026-11-14, below): `53743a81981f309ec52b05c41f74a943fa4612278a9943cce0e9d6a26567e746`
Templates sha256 before Approve's confirm gate (2026-11-14, the review's note; no region moves: an attribute): `0a8a8bfaba4aec501d89760ee52bf9417e4746b72118e61e464d038c8f8bf0dd`
Templates sha256 before Part A's review fixes (2026-11-14, below): `1bb2bfef4008a673a4284e25dbeab6564beac38b3bebc3424609f8cd943de33a`
Templates sha256 before the R2 comparison (2026-11-14, below): `35bfd2b6c245d362771ba87fdb7e9285e9483979f00efca16fbe7744a5b8319f`
Templates sha256 then (2026-11-12): `e1db7ab84d6ce006eda3411be83278ae90190fbb692b3285c9c28d187f04c0fa`
(2026-11-12, local times' comparison below and S5's section merged, each kept; their own
hashes were `fd015f548f9e98aca3ce23f8985f0233623ff2a173d6b8ba8d94f9984f8a9da1` (local times)
and `38b178a3941bf6b526b783769ed3ac5a711adde528041779d109b7c405c33e2f` (S5).)

**Compared again 2026-11-12 (local times, docs/UI_RULES.md "One time zone per screen"):** in `incident.html`, the header's and the timeline's times are drawn by the shared `_macros.clock` in place of the page's own element: the viewer's date and time to the second, the zone named once on the page rather than beside every time, the UTC instant on hover; The record's times stay UTC, as recorded. Compared by the template's diff and the page tests/test_incident_page.py opens in Firefox, not a new shot; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times"). Templates sha256 before: `ecfb220f7aa8d7f158980c24a3aa53a360889b79f59d88141a3949e76ca40264`.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| The breadcrumb | "Needs attention › <the title>" | Needs attention (a link), then the title on one line, cut with an ellipsis where the row is narrower, the whole on its hover (C3453) | **same** |
| The title | built from words, never a bare id; closed: "…, and Mercury put it back", "…, and it was put back by <name>", "…, and it cleared" | ONE builder (`said.title`, C3453): plain words, at most 70 characters, one line at 1280 px: what changed by its kind ("edge-b: static route added outside Mercury"), else the symptom by its own fields, else what opened it; never the configuration line, a mnemonic, a code key or an id (the line is What's wrong's); the endings "…, and Mercury put it back", "…, put back by <name>", "…, and it cleared", an action's "…, and Mercury's fix was verified"; 24px (E1) | **deviation** (log: Incident page: titles in plain words) |
| The state | open, needs a person, fixed, cleared, cancelled; F's table: a lost stream with a known fix and a fix whose operation failed need a person, an operation running is open | a badge in those five, from ONE function for the whole page (`incident_page.status`: the incident's records and its troubleshooting record's state), carried by every section (`data-inc-state`); a lost stream needs a person from the start, a fix a person ran that stopped needs one, one running or passed is open | **same** |
| One state in every section (C3450) | not drawn as a rule (B1 and B3 draw pages that agree) | the header's badge and level, What's wrong, What Mercury has done, What to do and AI troubleshooting each draw the one state; "No person needed", "Nothing yet" and "Mercury is still reading" are never drawn beside "Needs a person" or the section's "Stopped" | **deviation** (log: Incident page: one state for the whole page) |
| States of a closed heal | F: a failed verify is "needs a person", never "Fixed" | the same; and such an incident is not drawn "resolved: read-only" (it says when self-healing ended its own work on it); a heal refused at its apply reads "not fixed: nothing was sent"; a declined proposal is Cancelled | **deviation** (log: Board incident-page B built, 3) |
| The level | the level its Needs attention card has or had, from the index row; "No person needed" for one that never had a card; "was Warning" once resolved | Critical or Warning derived from the incident's own outcome, "was …" once resolved, "No person needed"; an incident that needs a person and has no outcome yet (a lost stream nothing decided on) takes its Needs attention item's own level, and draws none when that item is not held | **deviation** (log: Board incident-page B built, 9) |
| The device | the device (its page's link), its network, its attached members by name | the device's link, the network, and how many devices are attached; each by name in Evidence | **same** |
| Open for, or its span | "open 2 d 19 h"; "Nov 8, 14:30 to Nov 12, 10:21 · resolved: read-only" | "since <time> (2 d ago)", the age kept current by the page; "<time> to <time> · resolved: read-only", the span ending when the incident ended (a fixed one at its verify, never the act's start its store kept as the close) | **same** |
| The four times | Detected, Decided, Fixed, Verified, each from the record B0 names; "— not yet", "— not needed", "— not fixed: verify failed", "✗ verify failed 09:49" | the same cells, each time from the same record; a cell says its state's words alone, "— not fixed", "✗ failed 09:49", why on its hover (each fact once, C3454) | **deviation** (log: Incident page: each fact once) |
| How a time is drawn | "11:05:12", the viewer's zone, UTC on hover | "Nov 11 11:05:12 MST" by the page's clock element, UTC on hover | **deviation** (log: Board incident-page B built, 1) |
| TIME TO REPAIR | "212 s · no human"; "330,612 s (3 d 19 h 50 min) · approved by <name>"; "not repaired"; "not repaired: verify failed"; "cleared, no repair recorded"; 32px; its hover naming both records | the same figures, words and size (20px when there is no figure), the span in words from a minute up in the one format Done's duration uses too (one computation from the same two records), the hover saying what each of its two times is (the times are the Detected and Verified cells', UTC on their hover), and "How time to repair is measured" beside it; who it was by as the next row says; not repaired reads "not repaired" alone, why on its hover (C3454) | **deviation** (log: Incident page: each fact once) |
| Who took part | "no human" or "approved by <name>" in Decided, in TIME TO REPAIR and on the attempt's line | said once: beside TIME TO REPAIR when repaired, on the attempt's line when not, as "by Mercury's self-healing · policy set by <display name>" or "… · approved by <display name>" (the heal's card's and History's words); the no-person hover as the board words it, without the policy's date | **deviation** (log: Board incident-page B built, 2) |
| One line per attempt | "Attempt 1: … applied 09:39 · verify failed: <the run's own reason>" under the cells | the same line, green, red or blue at its edge; "applied <time> · verified <time>" for one that passed; a failed one "applied <time> · verify failed", its reason said once in the stage it failed in (C3454), whole in The record | **deviation** (log: Incident page: each fact once) |
| The timeline | B4: every recorded event, oldest first, on the resolved page | a card on every state, open when resolved and collapsed otherwise; the first five triggers and members said, the rest counted | **deviation** (log: Board incident-page B built, 4) |
| What's wrong | what happened, then Mercury's own account; "(was)" once resolved | the decision's cause, facts first with their times, then what it decided ("Decided then: …" once self-healing ended its work); "(was)" once resolved | **same** |
| What's wrong: a lost stream (C3488) | B1: "r7 has sent no telemetry to the collector since …; monitoring for r7 is blind until it does. Mercury's diagnosis: …" | the item's lead sentence, then whether the device answers (warning colour when the reading cannot say) and what Mercury cannot see, each from its Needs attention item; the diagnosis is under What Mercury has done | **deviation** (log: Incident page: what the item kept under Details) |
| Mercury's diagnosis in full (C3488) | B1: one sentence under What's wrong and "Mercury's diagnosis was read at 09:12, with no AI. [Open the diagnosis] (in Evidence)" | under What Mercury has done, its own small heading: the verdict's badge, the runbook, who ran it, its reads and time, every hypothesis with its strength and what to do, what it ruled out, where it stopped; a can't-fix with none says so | **deviation** (log: Incident page: what the item kept under Details) |
| What Mercury has done | the outcome, its span, the one stepper's steps on a line, the outcome's words, Open its History record, Download the change record (.md); "Nothing has run in this incident." | the outcome, then the heal's five stages (Detected, Decided, Fixing, Checking, Done), each its sentence, time and state, opening to its steps: the stages its device's page draws for Open the card, byte for byte; the outcome's words are Done's; no span of its own (each stage's time is its own, the incident's are the header's); the two links; each stage's sentence at most 12 words, the fix in plain words, a failure's why once, a can't-fix "Can't fix: needs a person" in amber (C3454) | **deviation** (log: Board incident-page B built, 5) (log: Incident page: each fact once) |
| What to do (C3450) | words, the fix's button and card, Does it need you?, Also: Diagnose now, Hand over…, Open the device; F: a can't-fix has no main action (Open), a proposal's card under What to do, a resolved page links only | the one state in words, what the item says to do in its own words, then the incident's Needs attention item's ONE action as the one primary button (Review the fix…, Re-subscribe…, Open the device, Open the likely cause's device, Open the run while a run holds the device, Go to the proposed fix when AI troubleshooting proposes one), its card read and drawn under the button on its press; Diagnose… beside it where the item offers it; how the item clears; links to the device and its History; no button on a page that needs nobody; an item that left Needs attention, or a list not read yet, said as itself; Hand over… stays in AI troubleshooting and Acknowledge on the item | **deviation** (log: Incident page: What to do carries the item's one action) |
| What Mercury has done beside an operation's attempt | not drawn (the board's B3 puts attempt 1 here and in the header) | "Self-healing ran nothing in this incident. The 1 fix a person ran is listed under AI troubleshooting, below.", never "Nothing has run" beside an attempt; the header and timeline leave the operation out (C3198) | **later** (C3198: the header's attempts from both stores) |
| AI troubleshooting: the totals | "this incident: AI $0.00 of $1.00 · today: $0.31 of $1.50" | "This incident: AI $0.00 of its cap of $1.00 · today: $0.00 of $1.50", each summed when drawn; a sum not known says so with why | **same** |
| The attempts | one line each: its time, the operation and its parameters, proposed by, approved by, its outcome, its AI cost, [Open the run] to its entry under What Mercury has done | the same line, at its outcome's colour, the approver by display name, "Re-subscribe r2's telemetry (101, 102)" and the outcome in the operation's short words (the run's whole words on hover), one line at 1920 (the real-browser check); Open the run opens the run's own card on its device's page | **deviation** (log: Board recurring-fixes v2 built, 1) |
| The STOP | "Stopped: r7's streams did not come back", What it found (a), (b), (c) and the flag, Undone, "Nothing more runs unless you choose.", Retry with more information…, Cancel, Hand over… | "Stopped: <the run's words> (attempt n, its time)", What it found from the run's record, one line per subscription with its state in words and its flag's kind ("Subscription 101: re-subscribed; the stream did not come back · flagged: stale half-open"), each opening to its three checks and the flag's whole words (addresses, ports and connection numbers one level down, C3455), the same sentence, and the three choices as three buttons in one row, drawn alike and secondary, each opening its modal anchored to it (C3455) | **deviation** (log: Board recurring-fixes v2 built, 2) (log: AI troubleshooting: three choices drawn alike, each a modal) |
| Retry with more information | the text box, Sent with it, the three cost figures, Ask the AI to re-plan · about $0.07, Back | the text box, "Mercury's diagnosis does not read words; the AI does…", one cost line (Mercury's diagnosis $0.00; the AI at most $0.2502, about its measured figure once one is measured; the incident so far and after; today), What the AI would be sent, Ask Mercury's diagnosis to re-plan and, beside it, Ask the AI to re-plan with the AI mark, alike and secondary, each busy on itself, and Cancel; a modal anchored to its button, the focus in its box, closed by Cancel or Escape with the focus back on the button (C3455) | **deviation** (log: Board recurring-fixes v2 built, 10) (log: AI troubleshooting: three choices drawn alike, each a modal) |
| The proposal | Proposed fix (the AI proposes; you decide), What's wrong (AI), Seen before, the operation's card drawn in the section | Mercury's: as before. The AI's: "What's wrong (the AI, checked against what was sent)", its hypotheses each with what it cites, why this fix, its calls, cost, prompt and the call on History, Was this right? under it, then Proposed fix (the AI proposes; you decide) with its repeat flag and Open the fix's card…, a secondary button (the page's one primary is What to do's, C3455); Seen before is sent to the model and cited, not drawn as its own block | **deviation** (log: Board recurring-fixes v2 built, 11) (log: AI troubleshooting: three choices drawn alike, each a modal) |
| The gap | "Proposed fix: none Mercury can run. … (recorded as a gap: C2838's fix (a))", Retry…, Cancel, Hand over…; the attempt line "2. gap 16:58 UTC · by the AI · AI $0.05" | "Proposed fix: none Mercury can run (<time>): No Mercury operation does what the fix needs yet (a gap): <the AI's words>", What's wrong (the AI), no Approve, Retry…, Cancel, Hand over…; no attempt line (an attempt is an operation's run) and no register row named (C3342) | **deviation** (log: Board recurring-fixes v2 built, 11) |
| Answer unchecked | "The AI's answer couldn't be checked, so it isn't shown: <why>. Spent: $0.05.", Retry…, Cancel, Hand over… | "Proposed fix: none Mercury can run (<time>): The AI's answer couldn't be checked, so it isn't shown: <why naming both operands>", its calls and cost counted in the incident's spend, the call on History; Retry…, Cancel, Hand over… | **same** |
| A repeated proposal (G2) | "⚠ Proposed before in this incident: attempt 1, failed: the stream did not come back (16:49 UTC)", the parameter hash both times, the reason saying what is different, Approve and run again… | the same flag in the section, without the hash ("The same operation with the same parameters as then"), the hash in The record as "Proposed fix's parameter hash" (C3455, the GUI review's AI3); the flag and hash on the card; the card asks What is different now as its own field, refused under three words | **deviation** (log: Board recurring-fixes v2 built, 4) (log: AI troubleshooting: the repeat's hash in The record) |
| A variation | "A variation of attempt 1: the same operation, one parameter changed (collector step: off → on)" | the same words, each changed parameter named | **same** |
| The cap reached (G1) | "Retry isn't available: this incident's AI spend would pass its cap. Spent …; the next retry costs at most …, which would make … against the cap of …", Cancel and Hand over… | the cap's own words (`policy.cap_state`) with where the setting is; Retry not offered; Cancel and Hand over…; a press from an older panel refused naming what moved | **same** |
| Cancelled | "cancelled at 17:20 UTC by <name> · this incident: AI $0.00 of $1.00", Attempts: 1, Hand over…, Troubleshoot with AI | "Troubleshooting cancelled at <time> by <name>; 1 attempt recorded. The incident stays open, and nothing more runs.", Retry with more information… and Hand over… | **deviation** (log: Board recurring-fixes v2 built, 5) |
| Hand over | the write-up, a note, Send to (the teams told about can't-fix, ticked), Send the hand-over, Open the write-up, Download as Markdown; then "Handed over at … by … to Network team · Open the write-up"; "Kept, not sent: …" with Send again | the same form in a modal anchored to Hand over… (C3455), its teams ticked by default, Send the hand-over its one primary and Cancel; the same line after, drawn in the section in place; Download on the write-up's page; Kept, not sent with Send again | **deviation** (log: AI troubleshooting: three choices drawn alike, each a modal) |
| The write-up's page | step 8's nine sections, reached from the section, the record and back, as Markdown | `/v2/incident/<id>/handover/<version>`: the nine sections, who and to whom, back to the incident's page, Download as Markdown; a version not kept is a 404 that says so | **same** |
| Nothing tried | the totals, "No fix has been tried in this incident. Mercury's diagnosis names one under What to do.", Add what you know, Troubleshoot with AI | "No fix has been tried in this incident.", and "What to do above says where one is started." only where the page needs a person (the one state), Add what you know first (optional), the cost line (the AI at most $0.2502, not measured yet; the incident and today), Troubleshoot with AI with the AI mark, a secondary button busy on itself ("Troubleshooting…"), Hand over… alone in the row of choices, opening its modal (C3455) | **deviation** (log: Board recurring-fixes v2 built, 12) (log: AI troubleshooting: three choices drawn alike, each a modal) |
| The head and a device with no identity | "AI troubleshooting" | the heading, a "beta" badge (its hover: not measured on recorded cases yet; every fix approved by its preview's hash); a device with no identity: "AI troubleshooting is not offered here: <why>" | **deviation** (log: Board recurring-fixes v2 built, 8) |
| Resolved | read-only: every attempt with its cost and outcome, the AI total, each hand-over | the same, with no control; a self-heal fixed with nothing tried: "Not needed: Mercury fixed it without AI. No AI call is recorded for this incident." | **same** |
| AI off, the day cap, the provider | "Not available now: hosted AI is off…", the day cap's and the provider's words | the AI control's own: the button disabled with "Not available now: …" in place (hosted AI off, no key, the day cap with when it resets, the record unreadable), the provider's limit in its shared words, Open Settings › Installation, AI (hosted) for a viewer who may configure; the mode off draws its own words and no AI button; Mercury's diagnosis and Hand over stay usable | **same** |
| The live region with the section | not drawn | the page redraws on self-healing's `drift` and an operation's `privileged`, the section with it | **deviation** (log: Board recurring-fixes v2 built, 6) |
| Evidence | collapsed, six parts: the alerts, the evidence pack, Mercury's diagnosis, the reading, the changes, members | collapsed: the triggers, the detect pass's reads, where the changes are recorded, and each member with why; a diagnosis is said under What Mercury has done | **later** (the build plan's S4: alert incidents bring the alerts, the pack and the reading) |
| Seen before (C3488) | B7: its own section after Evidence, up to three past incidents, each linked | its own card after Evidence, for a lost stream: the one past loss the alerts reader's stored value holds (when, what, how it ended, how long it held), Open that incident, Open that operation's record; a search that could not be made is said; nothing for any other incident | **deviation** (log: Incident page: what the item kept under Details) |
| The AI analysis in full (C3488) | B5: the frame; board H, H8 drew the answer on the Needs attention row | in AI troubleshooting, for a can't-fix, above the advisory line: the kept answer's label and score, its rationale, each hypothesis with what it cites and its next step, where it came from; pending, off, capped and not answered said in place (`_heal_analysis.html`, the row's own partial) | **deviation** (log: Incident page: what the item kept under Details) |
| The record | collapsed: ids, the store's state, triggers kept, members, decisions, the program's hash, every step with its result, words and UTC time, the raw times, the tag, the index row's id, who acted by identity | collapsed, the same lines but the tag and the index row's id; a failed verify's time is labelled "Verify failed"; every time the viewer's, its UTC on hover (C3290); each hand-over last, with Open the write-up; a proposed fix's parameter hash, its proposal and the attempt it repeats (C3455) | **later** (the build plan's S3 and S8: the index row's id and the tag) |
| A fold | the old address answers 302; the surviving page leads "Folded into this incident at 10:41: … was taken in because …" with Open the old record | the 302; the line with its time, the device, the old id and the reason; no link to the old record | **later** (the build plan's S4: the old record's own view) |
| Moved and promoted | "Related: hi-… (… both changed: a cause spanning devices)"; a promoted incident says when its device changed | the Related line, a link to the other incident's page; the promoted line is not drawn | **later** (the build plan's S4) |
| An unknown id | a 404 on the frame: "No incident <id> is recorded.", the index and the incidents list named | the 404 and its first sentence; then where it looked, and links to Needs attention and History; another kind of id says its page comes later | **deviation** (log: Board incident-page B built, 7) |
| An unreadable record | a 200 that says so, what was read, Read again | the same, drawing whatever could be read under it | **same** |
| The live fragment | the header with What Mercury has done, drawn again when its sources announce; never a poll | the whole incident, drawn again on self-healing's announcement, and on each step while its heal runs | **deviation** (log: Board incident-page B built, 8) |
| Phone width | not drawn | the times stack in one column, the stepper's steps run down (its own phone layout), nothing scrolls sideways | **same** |
| The presenter's view | `?view=present`, two columns, larger sizes | not drawn | **later** (the build plan's S12) |
| The fault drill chip | a chip beside the title, Retag… | a "Drill" badge beside the state, its hover the drill's `fd-` id, who declared it and the fault it expected; the same badge beside Open the incident on its Needs attention item; no Retag… | **deviation** (log: Board incident-page B built, 10) |

**Compared again 2026-11-14 (the operator's R1 and R2, MERCURY_CHARTER "Two standing rules";
the operator's spec is the board for this change): the bottom line up front, and one card.**
Compared region by region with the spec's words, by the template diff, the HTML
tests/test_incident_bluf.py, tests/test_fixit_section_v2.py and tests/test_incident_stream.py
draw (r2's lost-stream incident with Mercury's re-subscribe failed: r7's hi-22cfdc299000's
shape; and the section model's contract planted for the plan's states), and Firefox at 1280
and 390 px (the BLUF above the card above Timings, the one button inside the first screen,
nothing scrolling sideways, Modify…, Deny… and Hand over… each a modal anchored to its button).
Where they differ, the rows below supersede the rows above for the header's times, TIME TO
REPAIR, the attempt lines, What to do, AI troubleshooting's states and choices (the STOP,
Retry, Cancel, the proposal, the gap, the repeated proposal, the cap, nothing tried), What's
wrong, What Mercury has done and Seen before. Templates sha256 before:
`35bfd2b6c245d362771ba87fdb7e9285e9483979f00efca16fbe7744a5b8319f`.

| Region | Board | Built | Verdict |
|---|---|---|---|
| The BLUF's three lines (R2) | "The top is three plain lines: (1) what happened … (2) the impact … (3) how to fix it" | a card under the header: What happened, Impact (Mercury's own table; "not known" said where it holds none), How to fix it, in that order; the header keeps the title and the state line above it | **deviation** (log: Incident page: R2's bottom line and one card) |
| The one next action (R2) | "the one next action as a button, or the AI's proposal with Approve, Modify and Deny" | the section's `bluf.fix`: Approve (primary, by the plan's hash), Modify… and Deny…; Start AI troubleshooting; Ask the AI again; Hand over…; or the incident's own Needs attention action where the section names nothing to press; nothing to press said | **deviation** (log: Incident page: R2's bottom line and one card) |
| Never offer what failed (R2) | "Never offer, as the next action, anything that already failed on this incident. It appears only in Attempts … and under a collapsed 'Other actions'" | the same: a failed Re-subscribe in Attempts and Other actions only, the item's own Re-subscribe dropped once it failed here, a plan step repeating it refused at its preflight | **same** |
| Modify and Deny (R2) | "Modify: a text box … returns a revised plan with a new hash … Deny: records an optional reason" | Modify…'s box and Deny…'s optional reason in modals anchored to their buttons, each posting with the plan's id and hash; the answer drawn under the BLUF's buttons in place | **deviation** (log: Incident page: R2's bottom line and one card) |
| The one card (R2) | "'What to do' and 'AI troubleshooting' become one card under the BLUF: a status line …, then the proposal" | "Fixing it": the section's status line, then the plan, each step with its preflight (a refused step drawn refused with why, and Approve not offered) | **same** |
| Collapsed below (R2) | "Everything else sits below, collapsed: evidence, attempts, guards and holds, alert text, timings, costs, History links" | collapsed in the card: Attempts, What attempt n found, Other actions, Holds and guards, Why the AI proposes this, Costs (with automatic troubleshooting's state and estimate), the AI's analysis; on the page: Timings (the four times, TIME TO REPAIR, the attempt lines), Timeline, What's wrong, What Mercury has done (with the History links), Evidence, Seen before, The record | **deviation** (log: Incident page: R2's bottom line and one card) |
| A hold (R2) | "A guard or hold working as designed is not a failure: no red bar … one plain line in the details" | one plain line each under Holds and guards, in ink, never red, never "failed" | **same** |
| Cancel and Retry (R2) | "Cancel and 'Retry with more information' are removed (Deny and Modify replace them). Hand over stays as a secondary link" | neither drawn; Hand over… a link-styled button beside the next action, the primary where nothing else is left | **same** |
| Severity (R2) | "Severity follows impact: critical only for a network outage" | the header's level is the BLUF's severity while a person is needed | **deviation** (log: Incident page: R2's bottom line and one card) |
| The legacy incident (R1) | "r7's incident hi-22cfdc299000 shows its BLUF and one 'Start AI troubleshooting' button" | the page's one primary is Start AI troubleshooting, its cost under it and an optional Add what you know first box | **deviation** (log: Incident page: R2's bottom line and one card) |

**Compared again 2026-11-14 (Part A's review fixes: R4, the AI's answer, one first action):**
an answer that proposed no plan (a gap, no fix) draws its diagnosis and the missing capability
it names under What the AI found (`x.ai_answer`), as a plan's is drawn under Why the AI
proposes this; an item whose action is Start AI troubleshooting (`it.first` ``start``) draws
no second button, one line pointing at the bottom line's. No region moves; compared by the
templates' diff, not by new shots.

| Region | Board | Built | Verdict |
|---|---|---|---|
| An answer with no plan (R2) | "the AI's proposal with Approve, Modify and Deny" | What the AI found, collapsed: its rationale, hypotheses with their citations, the gap | **same** |
| The item's Start (R1, R2) | one next action | the bottom line's Start alone; the item's place says so | **same** |
| The problem's evidence (R4) | "the alerts are listed as evidence under it" | What happened, with its since in the viewer's time, and its evidence collapsed under it, each signal's words and time | **same** |
| Approve (THE confirm pattern) | Approve by the plan's hash | the same button and words, its route and the plan's hash carried by the press itself | **same** |

**Compared again 2026-11-14 (the verify-speed gate's page fixes; the operator's review of r7's
page after Part A, 2026-11-15, and R2 and R4): one title, the evidence once, a hold neutral,
and what the plan's hash binds.** Compared region by region with the operator's words in
C3725, C3727, C3728 and C3729, by the template diff and the pages tests/test_one_incident_title.py,
tests/test_incident_page_once.py, tests/test_plan_binds_drawn.py and tests/v2_context.py's
`_fixit_section` draw, not by new shots. These rows supersede the rows above for the title,
the problem's evidence, Evidence, What Mercury has done's outcome and The record's plan hash.

| Region | Board | Built | Verdict |
|---|---|---|---|
| The title (C3727, R4) | "titles the incident by it ... not "alert 'Critical syslog received' firing""; "the page draws one, the problem's" | the problem's title (`bluf.what_of`), the heading, the breadcrumb's last crumb, the window's title and the bottom line's What happened one string; a closed incident's heading adds how it ended | **same** |
| The problem's evidence (C3729, R2) | "one home, collapsed under the card" | one collapsed card, **Evidence (n)**, directly under the bottom line: each signal with its time, triggers seen beyond those kept, the detect pass's reads, the devices attached; the Evidence section below What Mercury has done removed, and What happened holds no evidence of its own | **deviation** (log: Incident page: the evidence's one home) |
| What Mercury has done's outcome (C3728, R2) | "A hold's stage drawn neutral, in its plain words; red only for what failed" | a hold's chip neutral ("Self-healing (dry run): held"), its plain line (`bluf.hold_line`) on the hover; a failure's red unchanged; the stages inside unchanged (THE stepper's, shared with the device's card) | **deviation** (log: Incident page: a hold drawn neutral) |
| What its hash binds (C3725) | "every value the hash binds is drawn in the plan's preview before Approve" | collapsed in the plan, one row a bound value (the incident, the proposal, each step's operation, parameters and own hash), keys by their words; a refused plan draws none (its hashes The record's alone, C3455's AI3) | **same** |
| The collector step's session (C3725) | "the session's both ends and ports drawn before Approve" | the session as read when the plan was proposed (the close helper's dry run, inside the job that made it) and kept with it, drawn beside Approve from that record, never read on a page draw: both ends and ports and how long it was quiet, when it was read on the hover; bound by the plan's hash and in What its hash binds; Approve reads it again and refuses when it moved, naming both; a plan whose read named none not approvable, saying why (the operator, 2026-11-15) | **same** |
| The record's plan hash | the plan's hash and each step's | kept for a plan that draws no What its hash binds (a planted or older model), and a refused plan's as before; each fact once | **same** |

**Compared 2026-11-15, the saved plans (Gate 1b; board saved-plans S).**

| Region | Board | Built | Verdict |
|---|---|---|---|
| Where it sits | at the foot of "Fixing it", asked in place once the card is drawn | the slot at the section's foot, asked once it loads (`saved_plans_v2.card`), a read of records | **same** |
| The verified run's line | "<plan> ran and passed its own verify. Save it, its parameters left open" | the same words, the run's title from its record, How does a saved plan work? beside it | **same** |
| Save as a self-heal script | name; the match's fields, the condition always, each other a tick; the match previewed on the open incidents; the parameters as they will be filled | the same: only the fields the problem holds, ticked; "n of the m open incidents' problems hold this match now"; each parameter's fill, a choice through its named map | **same** |
| Save as a reusable action | name, what it does, its parameters | the same | **same** |
| The scripts it matches, Promote | each with its mode and how often it fired; Promote while in Dry run | the same, an Auto one naming who promoted it | **same** |
| The shapes waiting on an admin | each shape with its dialect, who proposed it and why, its first run's measurement, Approve | the same | **same** |
| A right the viewer lacks (S2) | said beside its control, the control disabled | the refusal's own words beside it, the button disabled (Promote's and Approve's on their hover) | **same** |
| The answer (S3) | in place, above the card; "Nothing to save yet" when no run passed | the same; each button busy on itself until it answers | **same** |
| Rights not set (Gate 1b's review, item 7) | not drawn | one faint line at the card's head naming each right whose holders `access_rights` does not set: every verified person holds it until then | **deviation** (log: Board saved-plans S built, 3) |

**Compared again 2026-11-25 (C3919, the operator, 2026-11-17: "remove plan.py:41's
same-incident repeat refusal; the person decides"): a repeated step's risk.** By the template
diff, not by new shots. In `_fixit_section.html`, a plan step that repeats a failed attempt is
drawn passed, where it was drawn refused: on the plan card, under the step, "Its risk: it
already failed on this incident as attempt N (…): running it again is your decision", and in
Details' step list "· preflight passed · its risk: …". The plan keeps Approve as its one
primary. In `incident.html`, The record gains "The plan's repeats" (each repeating step's
parameter hash, the same as its attempt's) for an approvable plan, the line "The refused
plan" draws for a refused one. No other region moves.

| Region | Board | Built | Verdict |
|---|---|---|---|
| A repeated step (C3919) | board R5's plan card: each step, its preflight, Approve, Modify…, Deny… | the step drawn passed with its risk under it, Approve offered | **same** (the plan card's regions; the refusal R2 drew is withdrawn by the operator's C3919) |
| The record's repeats (C3919) | not drawn | "The plan's repeats" beside the plan's hash, for an approvable plan | **same** (The record's plan hash row above, one more line of it) |
