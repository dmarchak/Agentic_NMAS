# Fidelity: Needs attention, a self-healing proposal and its card (2026-11-04)

Board: `heal-to-intent.html`, artboards D (the proposal's row on its one line) and E (the row
opened: the program and its hash, what the reset does, Approve by hash with a reason, Decline),
docs/boards/heal-to-intent.html, approved by the operator 2026-11-03 (docs/STANDING_APPROVAL_LOG.md,
"Board H approved by the operator: heal to intent (Lab 10)"). Its yellow callouts are notes for
the builder; its teal "amendment, for review" regions are not approved and not built.

Shots: `tests/test_board_shots.py::test_heal_proposal` (`heal-proposal` at 1440, 1280 and 390:
Default in dry run, one real proposal on edge-b, R8's changed OSPF router-id, its reset measured
by the test record; Review the fix… pressed, the card read and drawn in the row, a reason
typed), NMAS_BOARDS_DIR set to docs/boards. The board is the HTML file itself, read region by
region beside the shots. The states the shot does not draw (a reset not measured, a refusal in
place with the reason kept, Approved, Declined, a proposal no longer held) are compared by the
template and tests/test_heal_proposal_v2.py.
Templates compared: templates/v2/_heal_proposal.html
Templates sha256: `25d325220732c92edb793543311273758c7f0a2a63888bbb2417d5d6539ea0d1`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Where it is | a Warning row on Needs attention, its line "A fix waits for a person: r6's OSPF router-id differs from intent · 9 min · Propose" with Review the fix… (artboard D) | the same place and level; the title "A fix waits for a person on <device>: <each unit's words>", the age in the row's corner, Review the fix… with its (i) | **deviation** (log: Board H E built: the proposal row's title from the decision's own words) |
| The tier on the line | "Propose, process reset" beside the age | not on the line: the line draws severity, title, age and its action (board NA-R); the tier is the card's Fix row, a Propose chip | **deviation** (log: Board H E built: the tier drawn on the card, not the line) |
| Review the fix… | opens the row | the same: it opens the row and every section holding the card, and focuses it; the card is read when the row opens | **same** |
| What to do | "Approve to set r6's router-id back to intent and reset its OSPF process. The reset drops every OSPF adjacency on r6 (2) …" | the same sentence from the proposal: the fix's kind, the device, the reset's command, what it drops, "so choose the moment"; the adjacency count is not drawn | **deviation** (log: Board H E built: no adjacency count in What to do) |
| The program | the lines, then "! then, measured: clear ip ospf 1 process (prompt answered: yes)" | the recorded program (masked when recorded), then "! then: <command> (its prompt measured on <device>, <when>)" or "(not measured)"; the prompt and its answer are the measurement record's, not shown | **deviation** (log: Board H E built: the reset line names where it was measured) |
| Program | "prog-e1c4772b · read at 18:12:30" | the program's hash, when it was proposed, its line count, the device and platform | **same** |
| Expected effects | the adjacencies that drop, and the blast radius | what the measured reset drops (every adjacency of the process) until it forms again; no blast radius (no topology read is made for a card) | **deviation** (log: Board H E built: Expected effects without the blast radius) |
| Verify reads | "both adjacencies FULL within 120 s; no duplicate router-id logged on r4" | the deploy's verify, then the neighbour table until the adjacencies formed before form again, within the measured bound; the symptom read again once released | **deviation** (log: Board H E built: Verify reads as the approved act verifies) |
| Rollback | "the router-id back; a reset cannot be undone" | the same, and "It will not": the reset changes no configuration and no other process | **same** |
| Mercury's diagnosis | the teal insert, "run before this was offered" | not drawn: an amendment for review, not approved | **later** (H17, the diagnosis on a Propose incident, once the amendment is approved) |
| Reason | the field, "at least three words" | the same; a refusal keeps what was typed | **same** |
| Approve and run on r6 | the primary button | the same words; bound to the proposal's hash in the form; drawn disabled with each refusal (a reset not measured, a stop, taken already) as its title and a Not confirmable line above; busy on itself ("Approving…") | **same** |
| Decline… | the button | **Decline**, posting the same reason at once; nothing is sent | **deviation** (log: Board H E built: Decline without its ellipsis) |
| Check drift now on r6 | the button | the same, opening the device's Check drift now card | **same** |
| The bound line | "Bound to this program's hash and to r6 as read at 18:12:30. If r6 changes, the proposal is withdrawn and made again. Clears when …" | who is confirming; bound to the proposal's hash; "If <device> has changed since it was proposed, the approved run refuses at its plan step and closes the proposal, sending nothing"; Clears when … is the row's own line | **deviation** (log: Board H E built: the bound line says what the code does when the device moved) |
| What Mercury found and tried | a link, "(5 steps)" | one level down in the card: the decision's words, its triggers, the change it would fix, the policy it was made under, the decision and incident, a link to the device's History; and What approving runs, the twelve steps | **deviation** (log: Board H E built: What Mercury found and tried opens in place) |
| Answers in place | not drawn | Approved by you (the job and the hash), Declined (the words, nothing sent, the records), Not done: <why> with the reason kept, Couldn't load the proposal: <why>; the row leaves on the next redraw, which the answer holds until Show it now | **deviation** (log: Board H E built: each answer drawn in the card) |
| The halted policy and Lift the halt | the second row of artboard E | not built: no route lifts a halt yet (`decisions.lift` has none) | **later** (H9's next piece: the `heal`/`halted` row and Lift the halt…) |
| Phone width | not drawn | the row's line wraps; the card's rows stack, the program scrolls inside its block, the buttons wrap | **deviation** (log: Board H E built: the card's phone width) |
