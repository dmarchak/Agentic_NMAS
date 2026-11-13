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
Templates compared: templates/v2/_heal_proposal.html, templates/v2/_heal_halt.html
Compared again 2026-11-13 (C3290, the words Python builds): in the proposal's record (`_heal_proposal.html`), Proposed and the reset's measured time are `_macros.clock`'s (date and seconds), in the viewer's kept zone with the UTC instant on hover, where they drew the raw ISO instant; the decision's words and what raised it are drawn through the `times` filter (routes/v2.py). No element moves and no region's verdict moved; compared by the template's diff and the walk's render (tests/test_no_utc_drawn.py), not by new shots; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times: the words Python builds"). Templates sha256 before: `dca9ac32a9dc6ca2f4dbf136852fd08fee86dfdb1e272d68e38b92ad031f5711`.
Compared again 2026-11-13 (the operator's approved rule, "raw UTC anywhere left"; C3290): `_heal_proposal.html` draws a diagnosis hypothesis's claim and next step, and a step's words, through `times` (routes/v2.py), so an instant in them is `_macros.clock`'s. No element moves and no region's verdict moved; compared by the template's diff, not by new shots; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times: the words Python builds"). Templates sha256 before: `c19404f2b3284e7a5bbc5faf50656e84875403060b50b136166763757cc414d6`.
Templates sha256: `10cec229b75fe4112b58389adfb7822c1e6ee8e5275a2ddb0ae720eb3214c103`

**Compared again 2026-11-11 (board E2a, display names):** by the template's diff against the
regions below, not from new shots. In `_heal_proposal.html`, each place that draws a person
(who confirmed the policy, in the foot and in the record; who ran or is running Mercury's
diagnosis) now draws them through the `people` filter, by display name (the name the person
set, else the part of their identity before the "@"), in the same element and position; the
confirm's "You are confirming as <name>." names the person the same way. No region is added,
removed or moved, and no other word changes. Where the board draws an identity the built
screen draws the name, a deviation logged once for every screen (log: Display names: a person
is drawn by display name on every screen). Every other verdict stands.

**Compared again 2026-11-09 (C2817 and C2823):** the card and its row are redrawn as the
operator's first template ("The three templates are right as drawn", 2026-11-09;
~/Documents/nmas-reports/2026-11-08T2000Z-human-readable-mocks.md, mock 1), which amends
artboards D and E. Compared by the template diff against mock 1's regions, the text board the
operator accepted. No new shot was taken: tests/test_heal_proposal_v2.py and
tests/test_heal_said.py draw each state through the real app, and tests/test_board_shots.py's
`test_heal_proposal` needs Firefox, which this overnight run did not use. Each region that moved
is in the table below, its deviation from board H logged (docs/STANDING_APPROVAL_LOG.md,
2026-11-09, "C2817 1" to "C2817 8", "C2817 14"). The halt's card (`_heal_halt.html`) is
unchanged. Templates sha256 before: `e85cfde2f33d2f869b2085bd5000486bd13542d782789fd3912c441a5c2a448b`.

**Compared again 2026-11-09 (C2839, the operator's rule of 2026-11-09; merged with C2817's card,
whose sha256 was `c85ff86d1ca807f426d82afd3213bd685d159f695c62455125842de5f22d0913`):** a
proposal whose fix is a security control removed or changed outside intent, or an ACL, draws a
block above "Does it need you?", "A security control changed outside intent: you decide." with both answers' words and
the lines (masked) as the record keeps them; its primary button reads **Remove it (back to
intent)** in place of Approve and run on <device> (the same post, hash and reason); and **Keep
it: add it to intent** sits beside Decline, opening the device's intent editor (its Intent tab),
with its (i). Every other proposal draws as before. Artboard E draws neither (it was drawn for
R8's process reset); the deviation is the operator's rule, logged in
docs/STANDING_APPROVAL_LOG.md (2026-11-09, "C2839 5"). Compared by the template diff against
artboard E's regions (no new shot: tests/v2_context.py's provider draws the security state, and
tests/test_heal_security.py its words); every other region is as C2817's card draws it.

**Compared again 2026-11-08 (C2804, the operator's decision 4):** in dry run, a confirmable card
draws one warning notice above Reason, Approve and Decline: "This sends, although <network> is
in dry run: approving runs the program (and its reset) on <device> as you. Dry run holds only
what Mercury would do by itself." Artboard E draws no such notice (it was drawn for a network
in Auto); the deviation is the operator's decision, logged in docs/STANDING_APPROVAL_LOG.md
(2026-11-08, "C2804"). Compared by the template diff against artboard E's regions (no new shot:
tests/test_heal_proposal_v2.py draws it in dry run and out of it); every other region is
unchanged. Templates sha256 before: `2abbcd1bd30323b0c68ae4df67278e73a8c84dc3b56343bdd987ae2d81b6ec5e`.

**Compared again 2026-11-07 for H17** (board H's amendment, artboard E's teal insert, approved
with section 19 on 2026-11-04): the card gains Mercury's diagnosis under its table, before the
refusals and Reason, where the insert sits. Compared by the template diff against the insert
(no new shot: the walk's provider in tests/v2_context.py draws its done state, and
tests/test_heal_auto_diagnose.py the rest). One deviation, logged (the table's "Mercury's
diagnosis" row below). Every other region is unchanged. Templates sha256 before:
`8d29086cb75f0da05ebd0bbf1174640007cc64c4c8dd31039a19455568ab16eb`.

**Compared again 2026-11-04 ~17:3x UTC (C2472):** the card's `<form>` became a `div` of the same
class, so Enter in the reason field submits nothing (measured first in a real browser: on a form
it posted Approve). Approve and Decline each post themselves, with the hash and the reason by
`hx-include`, Approve carrying the hash it confirms in its own `hx-vals` (an attribute nothing
draws). The shots were taken again at 1440, 1280 and 390, and every region draws as
before; only the proposal's hash and decision id differ, as they do in every run. Templates
sha256 before: `25d325220732c92edb793543311273758c7f0a2a63888bbb2417d5d6539ea0d1`.

**Compared again 2026-11-04 ~17:3x UTC** (C2470 and C2471): the bound line now says what the
code does, as the board says it (a proposal is withdrawn and made again when its device
changes), and a withdrawn proposal's card says so, naming why (compared by the template and
tests/test_heal_proposal_v2.py's withdrawn case; the shot does not draw it). Artboard E's
second row is built: the `heal`/`halted` row and its Lift the halt card
(`templates/v2/_heal_halt.html`), shot as `heal-halt` at 1440, 1280 and 390 (the same test:
Default halted by guard 14 on edge-b, Lift the halt… pressed, a reason typed; then Lift the
halt pressed in the browser and its answer read). Templates sha256 before:
`25d325220732c92edb793543311273758c7f0a2a63888bbb2417d5d6539ea0d1`; on its own branch, at
`bbe60feebedf22f01e06b8340edec15ce341160f56c0f5063f63876beaf232d0`.

**Merged 2026-11-04 ~19:2x UTC:** C2472's no-form card and C2470's bound line and withdrawn
notice were compared apart; the merged card holds both unchanged (the `div`, Approve's
`hx-vals`, and the board's bound line), so the record compares both templates at the merged
hash, the shots taken again from the merged tree.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Where it is | a Warning row on Needs attention, its line "A fix waits for a person: r6's OSPF router-id differs from intent · 9 min · Propose" with Review the fix… (artboard D) | a Critical row (mock 1), its line "<device>: <what changed>. Mercury has a fix that restarts <process> on <device>: it needs your decision", the age in the row's corner, Review the fix… with its (i) | **deviation** (log: C2817 1) |
| The tier on the line | "Propose, process reset" beside the age | not on the line: the line draws severity, title, age and its action (board NA-R); the tier is the card's Fix row, a Propose chip | **deviation** (log: Board H E built: the tier drawn on the card, not the line) |
| Review the fix… | opens the row | the same: it opens the row and every section holding the card, and focuses it; the card is read when the row opens | **same** |
| What to do | "Approve to set r6's router-id back to intent and reset its OSPF process. The reset drops every OSPF adjacency on r6 (2) …" | mock 1's four questions in order: What happened (the decision's cause, its facts each at its time in the viewer's zone, then a likely cause labelled as a hypothesis where both ends are held, C2823), Does it need you? Yes (why, and a "Tier 2: a person decides" chip), The fix Mercury proposes (the fix in plain words, as intent says, then the reset) | **deviation** (log: C2817 2) |
| The program | the lines, then "! then, measured: clear ip ospf 1 process (prompt answered: yes)" | under **Show the commands**, a button that opens inline: the recorded program (masked when recorded), each line at its depth, then "Then <command>, its prompt measured on <device> at <time>" or "not measured" | **deviation** (log: C2817 3) |
| Program | "prog-e1c4772b · read at 18:12:30" | under Details for the record: the program's hash, its line count, the device and platform; when it was proposed in the card's "Mercury proposed this at <time>" line | **deviation** (log: C2817 2) |
| Expected effects | the adjacencies that drop, and the blast radius | **What it affects**: what the measured reset drops until it forms again, "Measured on <device>: back within about N s" from the record, what it does not change; no names and no blast radius | **deviation** (log: C2817 6) |
| Verify reads | "both adjacencies FULL within 120 s; no duplicate router-id logged on r4" | **How Mercury checks it worked**: the deploy's verify and each part read at intent, every neighbour forming again within the bound, each symptom read again once released; one Mercury does not read again "can't tell" | **deviation** (log: C2817 7) |
| If you don't | mock 1: "r6 keeps r4's ID: r4 and r6 stay unpeered …" | **If you don't**: the device keeps the change, its first symptom is not put right, and the proposal is withdrawn if the device changes again | **same** |
| Times | not drawn | each time in the viewer's zone (the browser's), UTC on hover; Details for the record keeps UTC | **deviation** (log: C2817 14) |
| Rollback | "the router-id back; a reset cannot be undone" | the same, and "It will not": the reset changes no configuration and no other process | **same** |
| Mercury's diagnosis | the teal insert, "run before this was offered (16 reads on r6, r4 and r7, 18:12:10): 1. … (decisive; …); 2. … The fix proposed addresses hypothesis 1. The diagnosis" | built (H17, 2026-11-07), under the card's table: "Mercury's diagnosis, run before this was offered: <runbook>, N read(s) on <devices>, <when>", its chip, each hypothesis whole with its strength, layer and what to do, what was ruled out, where it stopped, and a link to the device's History with its (i); running ("it is drawn here when it ends. Approving does not wait for it"), not made (its words), unreadable and not yet recorded each said. It runs once the fix is proposed, in its own thread, so the card can be opened while it runs. It never says a fix addresses a hypothesis: only that the fix does not change a decisive physical or link first hypothesis | **deviation** (log: Board H built: the proposal's diagnosis runs once it is offered, and says only what a fix cannot change) |
| Reason | the field, "at least three words" | the field, "optional to approve, needed to decline" (or "needed to approve" where a line needs a stated reason); a refusal keeps what was typed | **deviation** (log: C2817 4) |
| Approve and run on r6 | the primary button | the same words; bound to the proposal's hash in the form; drawn disabled with each refusal (a reset not measured, a stop, taken already) as its title and a Not confirmable line above; busy on itself ("Approving…") | **same** |
| Decline… | the button | **Decline**, posting the same reason at once; nothing is sent | **deviation** (log: Board H E built: Decline without its ellipsis) |
| Check drift now on r6 | the button | not on the card (mock 1's buttons); the device page keeps it | **deviation** (log: C2817 5) |
| The bound line | "Bound to this program's hash and to r6 as read at 18:12:30. If r6 changes, the proposal is withdrawn and made again. Clears when …" | "Mercury proposed this at <time> under <network>'s policy, confirmed by <who>. Approving sends exactly the commands shown, recorded as approved by you"; then who is confirming and "If <device> changes before you approve, the proposal is withdrawn and made again; if it changes after, the run refuses at its plan step and closes the proposal, sending nothing"; the hash itself under Details for the record | **deviation** (log: C2817 2) |
| A security control's two answers | not drawn | on a security control's or an ACL's proposal only: "A security control changed outside intent: you decide." with the lines (masked), **Remove it (back to intent)** as the primary button, and **Keep it: add it to intent** (the device's intent editor) | **deviation** (log: C2839 5) |
| Withdrawn | not drawn | "Withdrawn, no longer waiting: <device> read back at its golden … / changed since it was proposed (read at …, departure …); it was bound to <device> as read at … (departure …)", when it was recorded, nothing sent, a link to the device's History; Approve not drawn, and an approval sent anyway refused naming the hash confirmed and both states | **deviation** (log: Board H E built: a withdrawn proposal's card says why) |
| What Mercury found and tried | a link, "(5 steps)" | **Details for the record**, collapsed, last on the card: the proposal and incident (links to the device's History), the proposal's hash, the program's hash, the fix type and tier, the reset's measurement, the policy, when it was proposed (UTC), the decision's words, the change's person, what raised it, and what approving runs, the twelve steps | **deviation** (log: C2817 2) |
| Answers in place | not drawn | "You approved it. Mercury is applying it on <device> now, recorded as approved by you" (the job and the hash under Details for the record), Declined (the words, nothing sent; the records and steps under Details for the record), Not done: <why> with the reason kept, Couldn't load the proposal: <why>; the row leaves on the next redraw, which the answer holds until Show it now | **deviation** (log: C2817 8) |
| The halted row's line | a Critical row, "Self-healing halted on Default: a heal on r2 failed its verify and was rolled back · 3 min" | a Critical row, "Self-healing halted on <network>: <the halt's name>" (a rolled-back heal, the same fix twice, a network's rate), its age, and **Lift the halt…** on the line, which opens the row to its card | **deviation** (log: Board H E built: the halted row's title from the halt's own name) |
| The halted row's What to do | "Removing the OSPF network statement … The line was put back … Decide whether the statement belongs in r2's intent, then lift the halt. No device on Default is healed until then; dry-run records continue." | the action's words ("Read why …, then lift the halt with a reason") and Why this happened: the guard, its name and its words with both operands, then "No device on <network> is healed, and no dry-run record is made, until a person lifts the halt; a proposal waiting cannot be approved until then" | **deviation** (log: Board H E built: a halt stops dry-run records too) |
| Reason and Lift the halt | the Reason field ("at least three words") and **Lift the halt**, primary | the same field (outside any form, so Enter submits nothing, C2472) and **Lift the halt**, primary, busy on itself ("Lifting…"), with its (i) | **same** |
| Edit r2's intent… and Open the incident | two buttons beside Lift the halt | **Edit <device>'s intent…** (the device's Intent tab) and **Open the incident** (the device's History, where the heal's steps are: no incident page exists), drawn when the halt names a device | **deviation** (log: Board H E built: Open the incident opens the device's History) |
| Clears when | "Clears when a person lifts the halt. Other halts read the same way, each naming its guard and both operands …; "stopped everywhere by operator@example.com"" | "Clears when a person lifts the halt on this item with a reason (Lift the halt), recorded …"; each halt names its guard and operands in Why this happened; the kill switch is a Critical row of its own, "Self-healing is stopped everywhere: the installation's kill switch, by <who>", whose way out is Resume self-healing… on the Self-healing tab, never Lift the halt | **deviation** (log: Board H E built: the kill switch's row resumes, not lifts) |
| Lifted, or refused, in place | not drawn | "Lifted by you: self-healing on <network> runs again under its policy …, with your reason …"; or "Not lifted: <why>" naming both operands (the halt in force and the one sent, and who lifted it first), the reason typed kept; an answered card holds the list's live redraw until Show it now | **deviation** (log: Board H E built: Lift the halt's answer drawn in the card) |
| The halted row's AI analysis | "AI analysis: Advisory (beta) … Drawn as in artboard D" | not drawn on a halted row | **later** (H8's analysis is for a can't-fix incident; on a halt it waits for its own part) |
| Phone width | not drawn | the row's line wraps; the card's rows stack, the program scrolls inside its block, the buttons wrap | **deviation** (log: Board H E built: the card's phone width) |
