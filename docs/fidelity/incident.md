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

Templates compared: templates/v2/incident.html
Templates sha256: `7aa81346a92e1720d612598579774f4e26de434d91dacaee2db881983819834c`

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
| Open for, or its span | "open 2 d 19 h"; "Nov 8, 14:30 to Nov 12, 10:21 · resolved: read-only" | "since <time> (2 d ago)", the age kept current by the page; "<time> to <time> · resolved: read-only" | **same** |
| The four times | Detected, Decided, Fixed, Verified, each from the record B0 names; "— not yet", "— not needed", "— not fixed: verify failed", "✗ verify failed 09:49" | the same cells and words, each time from the same record | **same** |
| How a time is drawn | "11:05:12", the viewer's zone, UTC on hover | "Nov 11 11:05:12 MST" by the page's clock element, UTC on hover | **deviation** (log: Board incident-page B built, 1) |
| TIME TO REPAIR | "212 s · no human"; "330,612 s (3 d 19 h 50 min) · approved by <name>"; "not repaired"; "not repaired: verify failed"; "cleared, no repair recorded"; 32px; its hover naming both records | the same figures, words and size (20px when there is no figure), the span in words from a minute up, the hover with both times in UTC and what each is, and "How time to repair is measured" beside it; who it was by as the next row says | **same** |
| Who took part | "no human" or "approved by <name>" in Decided, in TIME TO REPAIR and on the attempt's line | said once: beside TIME TO REPAIR when repaired, on the attempt's line when not, as "by Mercury's self-healing · policy set by <display name>" or "… · approved by <display name>" (the heal's card's and History's words); the no-person hover as the board words it, without the policy's date | **deviation** (log: Board incident-page B built, 2) |
| One line per attempt | "Attempt 1: … applied 09:39 · verify failed: <the run's own reason>" under the cells | the same line, green, red or blue at its edge; "applied <time> · verified <time>" for one that passed; the reason cut at 200 characters, whole in The record | **same** |
| The timeline | B4: every recorded event, oldest first, on the resolved page | a card on every state, open when resolved and collapsed otherwise; the first five triggers and members said, the rest counted | **deviation** (log: Board incident-page B built, 4) |
| What's wrong | what happened, then Mercury's own account; "(was)" once resolved | the decision's cause, facts first with their times, then what it decided ("Decided then: …" once self-healing ended its work); "(was)" once resolved | **same** |
| What Mercury has done | the outcome, its span, the one stepper's steps on a line, the outcome's words, Open its History record, Download the change record (.md); "Nothing has run in this incident." | the outcome, then the heal's five stages (Detected, Decided, Fixing, Checking, Done), each its sentence, time and state, opening to its steps: the stages its device's page draws for Open the card, byte for byte; the outcome's words are Done's; no span of its own (each stage's time is its own, the incident's are the header's); the two links | **deviation** (log: Board incident-page B built, 5) |
| What to do | words, the fix's button and card, Diagnose now, Hand over… | words and links only (Needs attention, the device, its History, its Intent) | **later** (the build plan's S5: the page's controls) |
| AI troubleshooting | "Not built yet: AI troubleshooting will be here (the fix-it path's board v2)", today's advisory under it; B2: "Not needed: Mercury fixed it without AI. No AI was spent in this incident." | "Not built yet: AI troubleshooting will be here."; the kept AI analysis labelled advisory; "Not needed: Mercury fixed it without AI. No AI call is recorded for this incident." | **deviation** (log: Board incident-page B built, 6) |
| Evidence | collapsed, six parts: the alerts, the evidence pack, Mercury's diagnosis, the reading, the changes, members | collapsed: the triggers, the detect pass's reads, where the changes are recorded, and each member with why; a diagnosis is said under What Mercury has done | **later** (the build plan's S4: alert incidents bring the alerts, the pack and the reading) |
| Seen before | up to three past incidents, each linked | not drawn | **later** (the build plan's S4, from the incident index) |
| The record | collapsed: ids, the store's state, triggers kept, members, decisions, the program's hash, every step with its result, words and UTC time, the raw times, the tag, the index row's id, who acted by identity | collapsed, the same lines but the tag and the index row's id; a failed verify's time is labelled "Verify failed (UTC)" | **later** (the build plan's S3 and S8: the index row's id and the tag) |
| A fold | the old address answers 302; the surviving page leads "Folded into this incident at 10:41: … was taken in because …" with Open the old record | the 302; the line with its time, the device, the old id and the reason; no link to the old record | **later** (the build plan's S4: the old record's own view) |
| Moved and promoted | "Related: hi-… (… both changed: a cause spanning devices)"; a promoted incident says when its device changed | the Related line, a link to the other incident's page; the promoted line is not drawn | **later** (the build plan's S4) |
| An unknown id | a 404 on the frame: "No incident <id> is recorded.", the index and the incidents list named | the 404 and its first sentence; then where it looked, and links to Needs attention and History; another kind of id says its page comes later | **deviation** (log: Board incident-page B built, 7) |
| An unreadable record | a 200 that says so, what was read, Read again | the same, drawing whatever could be read under it | **same** |
| The live fragment | the header with What Mercury has done, drawn again when its sources announce; never a poll | the whole incident, drawn again on self-healing's announcement, and on each step while its heal runs | **deviation** (log: Board incident-page B built, 8) |
| Phone width | not drawn | the times stack in one column, the stepper's steps run down (its own phone layout), nothing scrolls sideways | **same** |
| The presenter's view | `?view=present`, two columns, larger sizes | not drawn | **later** (the build plan's S12) |
| The fault drill chip | a chip beside the title, Retag… | not drawn | **later** (the build plan's S8 and S9) |
