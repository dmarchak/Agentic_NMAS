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

Templates compared: templates/v2/incident.html, templates/v2/_fixit_section.html, templates/v2/incident_handover.html
Compared again 2026-11-13 (the operator's approved rule, "raw UTC anywhere left"; C3290): `incident.html` draws Mercury's diagnosis words and What to do's words, and `_fixit_section.html` a step's words and a hypothesis's claim, through `times` (routes/v2.py), so an instant the lost-stream runbook writes is `_macros.clock`'s, in the viewer's kept zone with the UTC instant on hover. No element moves and no region's verdict moved; compared by the templates' diff, not by new shots; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times: the words Python builds"). Templates sha256 before: `caa59cdd04847e4a289f07d97ef83060314717f80291ef74e4876c74d2dfdae7`.
Templates sha256: `faf97cda35f17a4ffcaa22148501009d3686d1598a9a77b554bb1a4acf874c86`
Templates sha256 then (2026-11-12): `e1db7ab84d6ce006eda3411be83278ae90190fbb692b3285c9c28d187f04c0fa`
(2026-11-12, local times' comparison below and S5's section merged, each kept; their own
hashes were `fd015f548f9e98aca3ce23f8985f0233623ff2a173d6b8ba8d94f9984f8a9da1` (local times)
and `38b178a3941bf6b526b783769ed3ac5a711adde528041779d109b7c405c33e2f` (S5).)

**Compared again 2026-11-12 (local times, docs/UI_RULES.md "One time zone per screen"):** in `incident.html`, the header's and the timeline's times are drawn by the shared `_macros.clock` in place of the page's own element: the viewer's date and time to the second, the zone named once on the page rather than beside every time, the UTC instant on hover; The record's times stay UTC, as recorded. Compared by the template's diff and the page tests/test_incident_page.py opens in Firefox, not a new shot; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times"). Templates sha256 before: `ecfb220f7aa8d7f158980c24a3aa53a360889b79f59d88141a3949e76ca40264`.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| The breadcrumb | "Needs attention › <the title>" | Needs attention (a link), then the title | **same** |
| The title | built from words, never a bare id; closed: "…, and Mercury put it back", "…, and it was put back by <name>", "…, and it cleared" | what changed from the newest decision's units, else the symptom its cause states, else the first trigger's words; the three endings; an action's fix "…, and Mercury's fix was verified"; cut at 160 characters; 24px (E1) | **same** |
| The state | open, needs a person, fixed, cleared, cancelled | a badge in those five, from the incident's records | **same** |
| States of a closed heal | F: a failed verify is "needs a person", never "Fixed" | the same; and such an incident is not drawn "resolved: read-only" (it says when self-healing ended its own work on it); a heal refused at its apply reads "not fixed: nothing was sent"; a declined proposal is Cancelled | **deviation** (log: Board incident-page B built, 3) |
| The level | the level its Needs attention card has or had, from the index row; "No person needed" for one that never had a card; "was Warning" once resolved | Critical or Warning derived from the incident's own outcome, "was …" once resolved, "No person needed" | **deviation** (log: Board incident-page B built, 9) |
| The device | the device (its page's link), its network, its attached members by name | the device's link, the network, and how many devices are attached; each by name in Evidence | **same** |
| Open for, or its span | "open 2 d 19 h"; "Nov 8, 14:30 to Nov 12, 10:21 · resolved: read-only" | "since <time> (2 d ago)", the age kept current by the page; "<time> to <time> · resolved: read-only", the span ending when the incident ended (a fixed one at its verify, never the act's start its store kept as the close) | **same** |
| The four times | Detected, Decided, Fixed, Verified, each from the record B0 names; "— not yet", "— not needed", "— not fixed: verify failed", "✗ verify failed 09:49" | the same cells and words, each time from the same record | **same** |
| How a time is drawn | "11:05:12", the viewer's zone, UTC on hover | "Nov 11 11:05:12 MST" by the page's clock element, UTC on hover | **deviation** (log: Board incident-page B built, 1) |
| TIME TO REPAIR | "212 s · no human"; "330,612 s (3 d 19 h 50 min) · approved by <name>"; "not repaired"; "not repaired: verify failed"; "cleared, no repair recorded"; 32px; its hover naming both records | the same figures, words and size (20px when there is no figure), the span in words from a minute up in the one format Done's duration uses too (one computation from the same two records), the hover saying what each of its two times is (the times are the Detected and Verified cells', UTC on their hover), and "How time to repair is measured" beside it; who it was by as the next row says | **same** |
| Who took part | "no human" or "approved by <name>" in Decided, in TIME TO REPAIR and on the attempt's line | said once: beside TIME TO REPAIR when repaired, on the attempt's line when not, as "by Mercury's self-healing · policy set by <display name>" or "… · approved by <display name>" (the heal's card's and History's words); the no-person hover as the board words it, without the policy's date | **deviation** (log: Board incident-page B built, 2) |
| One line per attempt | "Attempt 1: … applied 09:39 · verify failed: <the run's own reason>" under the cells | the same line, green, red or blue at its edge; "applied <time> · verified <time>" for one that passed; the reason cut at 200 characters, whole in The record | **same** |
| The timeline | B4: every recorded event, oldest first, on the resolved page | a card on every state, open when resolved and collapsed otherwise; the first five triggers and members said, the rest counted | **deviation** (log: Board incident-page B built, 4) |
| What's wrong | what happened, then Mercury's own account; "(was)" once resolved | the decision's cause, facts first with their times, then what it decided ("Decided then: …" once self-healing ended its work); "(was)" once resolved | **same** |
| What Mercury has done | the outcome, its span, the one stepper's steps on a line, the outcome's words, Open its History record, Download the change record (.md); "Nothing has run in this incident." | the outcome, then the heal's five stages (Detected, Decided, Fixing, Checking, Done), each its sentence, time and state, opening to its steps: the stages its device's page draws for Open the card, byte for byte; the outcome's words are Done's; no span of its own (each stage's time is its own, the incident's are the header's); the two links | **deviation** (log: Board incident-page B built, 5) |
| What to do | words, the fix's button and card, Diagnose now, Hand over… | words and links only (Needs attention, the device, its History, its Intent) | **later** (the build plan's S5: the page's controls) |
| What Mercury has done beside an operation's attempt | not drawn (the board's B3 puts attempt 1 here and in the header) | "Self-healing ran nothing in this incident. The 1 fix a person ran is listed under AI troubleshooting, below.", never "Nothing has run" beside an attempt; the header and timeline leave the operation out (C3198) | **later** (C3198: the header's attempts from both stores) |
| AI troubleshooting: the totals | "this incident: AI $0.00 of $1.00 · today: $0.31 of $1.50" | "This incident: AI $0.00 of its cap of $1.00 · today: $0.00 of $1.50", each summed when drawn; a sum not known says so with why | **same** |
| The attempts | one line each: its time, the operation and its parameters, proposed by, approved by, its outcome, its AI cost, [Open the run] to its entry under What Mercury has done | the same line, at its outcome's colour, the approver by display name, "Re-subscribe r2's telemetry (101, 102)" and the outcome in the operation's short words (the run's whole words on hover), one line at 1920 (the real-browser check); Open the run opens the run's own card on its device's page | **deviation** (log: Board recurring-fixes v2 built, 1) |
| The STOP | "Stopped: r7's streams did not come back", What it found (a), (b), (c) and the flag, Undone, "Nothing more runs unless you choose.", Retry with more information…, Cancel, Hand over… | "Stopped: <the run's words> (attempt n, its time)", What it found per subscription from the run's record with the stale flag, the same sentence and the three choices | **deviation** (log: Board recurring-fixes v2 built, 2) |
| Retry with more information | the text box, Sent with it, the three cost figures, Ask the AI to re-plan · about $0.07, Back | the text box, "Mercury's diagnosis does not read words; the AI does…", one cost line (Mercury's diagnosis $0.00; the AI at most $0.2502, about its measured figure once one is measured; the incident so far and after; today), What the AI would be sent, Ask Mercury's diagnosis to re-plan and, beside it, Ask the AI to re-plan with the AI mark, each busy on itself; opened and closed by its summary | **deviation** (log: Board recurring-fixes v2 built, 10) |
| The proposal | Proposed fix (the AI proposes; you decide), What's wrong (AI), Seen before, the operation's card drawn in the section | Mercury's: as before. The AI's: "What's wrong (the AI, checked against what was sent)", its hypotheses each with what it cites, why this fix, its calls, cost, prompt and the call on History, Was this right? under it, then Proposed fix (the AI proposes; you decide) with its repeat flag and Open the fix's card…; Seen before is sent to the model and cited, not drawn as its own block | **deviation** (log: Board recurring-fixes v2 built, 11) |
| The gap | "Proposed fix: none Mercury can run. … (recorded as a gap: C2838's fix (a))", Retry…, Cancel, Hand over…; the attempt line "2. gap 16:58 UTC · by the AI · AI $0.05" | "Proposed fix: none Mercury can run (<time>): No Mercury operation does what the fix needs yet (a gap): <the AI's words>", What's wrong (the AI), no Approve, Retry…, Cancel, Hand over…; no attempt line (an attempt is an operation's run) and no register row named (C3342) | **deviation** (log: Board recurring-fixes v2 built, 11) |
| Answer unchecked | "The AI's answer couldn't be checked, so it isn't shown: <why>. Spent: $0.05.", Retry…, Cancel, Hand over… | "Proposed fix: none Mercury can run (<time>): The AI's answer couldn't be checked, so it isn't shown: <why naming both operands>", its calls and cost counted in the incident's spend, the call on History; Retry…, Cancel, Hand over… | **same** |
| A repeated proposal (G2) | "⚠ Proposed before in this incident: attempt 1, failed: the stream did not come back (16:49 UTC)", the parameter hash both times, the reason saying what is different, Approve and run again… | the same flag and hash in the section and on the card; the card asks What is different now as its own field, refused under three words | **deviation** (log: Board recurring-fixes v2 built, 4) |
| A variation | "A variation of attempt 1: the same operation, one parameter changed (collector step: off → on)" | the same words, each changed parameter named | **same** |
| The cap reached (G1) | "Retry isn't available: this incident's AI spend would pass its cap. Spent …; the next retry costs at most …, which would make … against the cap of …", Cancel and Hand over… | the cap's own words (`policy.cap_state`) with where the setting is; Retry not offered; Cancel and Hand over…; a press from an older panel refused naming what moved | **same** |
| Cancelled | "cancelled at 17:20 UTC by <name> · this incident: AI $0.00 of $1.00", Attempts: 1, Hand over…, Troubleshoot with AI | "Troubleshooting cancelled at <time> by <name>; 1 attempt recorded. The incident stays open, and nothing more runs.", Retry with more information… and Hand over… | **deviation** (log: Board recurring-fixes v2 built, 5) |
| Hand over | the write-up, a note, Send to (the teams told about can't-fix, ticked), Send the hand-over, Open the write-up, Download as Markdown; then "Handed over at … by … to Network team · Open the write-up"; "Kept, not sent: …" with Send again | the same form in place, its teams ticked by default; the same line after; Download on the write-up's page; Kept, not sent with Send again | **same** |
| The write-up's page | step 8's nine sections, reached from the section, the record and back, as Markdown | `/v2/incident/<id>/handover/<version>`: the nine sections, who and to whom, back to the incident's page, Download as Markdown; a version not kept is a 404 that says so | **same** |
| Nothing tried | the totals, "No fix has been tried in this incident. Mercury's diagnosis names one under What to do.", Add what you know, Troubleshoot with AI | "No fix has been tried in this incident. What to do above says where one is started.", Add what you know first (optional), the cost line (the AI at most $0.2502, not measured yet; the incident and today), Troubleshoot with AI with the AI mark, busy on itself ("Troubleshooting…"), Hand over… | **deviation** (log: Board recurring-fixes v2 built, 12) |
| The head and a device with no identity | "AI troubleshooting" | the heading, a "beta" badge (its hover: not measured on recorded cases yet; every fix approved by its preview's hash); a device with no identity: "AI troubleshooting is not offered here: <why>" | **deviation** (log: Board recurring-fixes v2 built, 8) |
| Resolved | read-only: every attempt with its cost and outcome, the AI total, each hand-over | the same, with no control; a self-heal fixed with nothing tried: "Not needed: Mercury fixed it without AI. No AI call is recorded for this incident." | **same** |
| AI off, the day cap, the provider | "Not available now: hosted AI is off…", the day cap's and the provider's words | the AI control's own: the button disabled with "Not available now: …" in place (hosted AI off, no key, the day cap with when it resets, the record unreadable), the provider's limit in its shared words, Open Settings › Installation, AI (hosted) for a viewer who may configure; the mode off draws its own words and no AI button; Mercury's diagnosis and Hand over stay usable | **same** |
| The live region with the section | not drawn | the page redraws on self-healing's `drift` and an operation's `privileged`, the section with it | **deviation** (log: Board recurring-fixes v2 built, 6) |
| Evidence | collapsed, six parts: the alerts, the evidence pack, Mercury's diagnosis, the reading, the changes, members | collapsed: the triggers, the detect pass's reads, where the changes are recorded, and each member with why; a diagnosis is said under What Mercury has done | **later** (the build plan's S4: alert incidents bring the alerts, the pack and the reading) |
| Seen before | up to three past incidents, each linked | not drawn | **later** (the build plan's S4, from the incident index) |
| The record | collapsed: ids, the store's state, triggers kept, members, decisions, the program's hash, every step with its result, words and UTC time, the raw times, the tag, the index row's id, who acted by identity | collapsed, the same lines but the tag and the index row's id; a failed verify's time is labelled "Verify failed"; every time the viewer's, its UTC on hover (C3290); each hand-over last, with Open the write-up | **later** (the build plan's S3 and S8: the index row's id and the tag) |
| A fold | the old address answers 302; the surviving page leads "Folded into this incident at 10:41: … was taken in because …" with Open the old record | the 302; the line with its time, the device, the old id and the reason; no link to the old record | **later** (the build plan's S4: the old record's own view) |
| Moved and promoted | "Related: hi-… (… both changed: a cause spanning devices)"; a promoted incident says when its device changed | the Related line, a link to the other incident's page; the promoted line is not drawn | **later** (the build plan's S4) |
| An unknown id | a 404 on the frame: "No incident <id> is recorded.", the index and the incidents list named | the 404 and its first sentence; then where it looked, and links to Needs attention and History; another kind of id says its page comes later | **deviation** (log: Board incident-page B built, 7) |
| An unreadable record | a 200 that says so, what was read, Read again | the same, drawing whatever could be read under it | **same** |
| The live fragment | the header with What Mercury has done, drawn again when its sources announce; never a poll | the whole incident, drawn again on self-healing's announcement, and on each step while its heal runs | **deviation** (log: Board incident-page B built, 8) |
| Phone width | not drawn | the times stack in one column, the stepper's steps run down (its own phone layout), nothing scrolls sideways | **same** |
| The presenter's view | `?view=present`, two columns, larger sizes | not drawn | **later** (the build plan's S12) |
| The fault drill chip | a chip beside the title, Retag… | a "Drill" badge beside the state, its hover the drill's `fd-` id, who declared it and the fault it expected; the same badge beside Open the incident on its Needs attention item; no Retag… | **deviation** (log: Board incident-page B built, 10) |
