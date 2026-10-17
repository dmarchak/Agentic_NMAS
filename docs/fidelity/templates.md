# Fidelity: Source of truth › Templates

The Templates page as built, its Configuration templates tab (the network's library, and each
action's card below it: Approve…, Revoke…, Edit…, Bindings…, Seed the library…), compared
region by region with its boards (C650's step), after the operator's walks W2 (2026-10-16,
steps 38 and 41 to 50: the seed on the throwaway network W2 walk, then on Default a revocation,
three approvals, two edits and two bindings commits) and W3 (2026-10-17, steps 12 and 16 to 19:
the seed on W3 walk, a revocation and an approval on Default reached from another network's
page, and step 47's read). No shot test exists for this page (tests/test_board_shots.py has
none), so the page as built is the operator's captures: W2's 28 and 29 (the seed's preview and
result), 40 and 41 (the library at desktop and phone width), 42 (revoked), 43 (the Approve
card), 44 (approved), 45 and 46 (the editor, unchanged, then with a comment line), 47 (the
edit committed), 48 to 50 (approved again), 51 to 54 (Bindings, an override added and
removed); W3's 15 to 17 and 52. The boards were rendered in the same headless Firefox at 1440
from the local copy of the canvas (no shot test to run them).

Boards: on "NMAS v2 mockups", page "7.6 Source of truth, Templates", `TemplatesApprove.dc.html`
(boards A to C, signed off 2026-10-05): A, the library; B, Approve… with the comparison device
by device; C, the result in place and Revoke… with its reason. On page "C566",
`C566Template.dc.html` (board C, approved 2026-10-07): the column "Against the shipped version"
and Bring in the shipped version…. No board file exists for Edit…, Bindings… or the seed: the
2026-10-10 lines "Board: Templates › Edit…", "Board: Templates › Bindings…" and "A network
with no templates on v2" are their boards, drawn under the Phase 7 mode. `Templates.dc.html`
on the same canvas is the Monitoring templates tab, which the built page does not have (row
"Tabs").
Shots: the operator's captures above; the boards `TemplatesApprove` and `C566Template` at
1440.
Compared 2026-10-17. The Coverage tab (`_template_coverage.html`) was not opened in either
walk and is not compared here (row "Coverage tab").
Templates compared: templates/v2/templates.html, templates/v2/_templates_lib.html, templates/v2/_templates_table.html, templates/v2/_template_op.html, templates/v2/_template_result.html, templates/v2/_template_edit.html, templates/v2/_template_check.html, templates/v2/_template_bindings.html
Templates sha256: `cfdace4c45de2294752e4edcc7dc5929f757fb7931b9dfa661746b5016fad009`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | Templates current under SOURCE OF TRUTH | the same (every capture) | **same** |
| Page head | "Templates · throwaway", the sub-line on what an approval covers, "What does an approval cover?" at the right | "Templates · Default" with its (i), the same sub-line; at the right Bindings… with "How does bindings work?" (W2 capture 40) | **same** |
| Tabs | Configuration templates · Monitoring templates | Configuration templates · Coverage (W2 capture 40) | **deviation** (log: Board: Templates › Coverage) |
| The counts line | at fleet scale, a summary first ("approved 12 · not approved 3 · revoked 1") | "approved 2 · not approved 0 · revoked 0 (1 shared macro file, counted in each template's imports)" above the table at every size (W2 capture 40) | **deviation** (log: Templates: the counts line is drawn at every size) |
| The library card | the table in a card; C566: "The network's library" with How does this work? | "The network's library" with How does this work? (W2 capture 40) | **same** |
| Columns | Template (with its imports), Platform, Devices bound, Approval; C566 adds Against the shipped version | Template "+ 1 import", Platform, Devices bound ("▸ 4 devices", the names on expand, as the board's fleet note asks), Against the shipped version ("current", "edited here, on purpose; the shipped file has not moved since" after an edit, W2 capture 47), Approval (W2 capture 40) | **same** |
| The approval cell | "not approved", "not approved · nothing bound to validate it", approved | "approved by <who>, <age>", "not approved · nothing bound to validate it" on a seeded network (W2 capture 29), "revoked" with the reason and who (W2 capture 42); a revoked row does not say when (C1061) | **deviation** (log: Templates: a revoked row shows who and why, not when (C1061)) |
| The row after an edit | not drawn | "revoked · 'cisco_ios/base.j2' was edited, and this template imports it; re-approval must validate the new content…" for the template's own edit (W2 capture 47), a reason written for an imported file | **deviation** (log: Templates: a template's own edit reads as an import's (a defect, register C650 follow-up)) |
| Row actions | one per row: Approve… (primary on a not approved row) or Revoke… | Edit… on every row (the Edit board line), then Approve… (primary when revoked) or Revoke…, each with its (i); Approve… greyed where nothing is bound, its reason on hover (W2 captures 29, 40, 42) | **same** |
| Phone width | not drawn | the table kept as a table: template names, "devices" and the approval words broken mid-word in narrow columns (W2 capture 41; C1060) | **deviation** (log: Templates: at phone width the table breaks words mid-word (C1060)) |
| Approve… (board B) | "Approve <template> for <network>": THE COMPARISON, each device's counts (missing, extra, reordered, unmodelled) and failing lines, WHAT IT COVERS with the fingerprint, CHECKS, the confirm bound to the fingerprint, Cancel | the same parts and words, s1 to s4 each "0 missing, 0 extra, 0 reordered", "4 of 4", "You are confirming as <you>. Bound to the fingerprint shown…", Approve with its (i), How and Cancel (W2 capture 43) | **same** |
| Busy on Approve | not drawn | "Checking…" on the button itself until the card drew (W3 step 18; C1023 fixed after W2's capture 44, which showed nothing while it worked) | **same** |
| The result (board C) | in place of the row: the template badged approved, DONE with who, when, the fingerprint and what was validated; "can now be deployed to" | a card below the table, the row redrawn in the table: badged approved, DONE with who, the fingerprint, the commit, Validated, Failed, Not validated, each device a link; and a STILL TRUE part repeating what an approval does not say (W2 capture 44) | **deviation** (log: Templates: a result is a card below the table, the row redrawn in place) |
| Revoke… (board C) | WHY, the note that every deploy is blocked until approved again, Revoke the approval, Cancel | the reason field, the note naming who approved it, "A revocation is the only record of why…", Revoke the approval (W2 step 42); the result badged revoked with the reason and the commit (W2 capture 42) | **same** |
| The library drawn twice | not drawn | after the edit's commit, the counts line and the library table drawn twice above the result (W2 capture 47; C1062) | **deviation** (log: Templates: after a template commit the library table was drawn twice (C1062)) |
| Edit… (the Edit board line) | intent editor H's layout below the table: the template, the check as typed beside it, the reason and Commit; the result with Approve… for each approval it revoked | "Editing <template>", opened at its commit, Discard the edit; the text as committed, the check beside it ("parses", "4 of 4 reproduce", each device "reproduces"); "Why, in one line…" and Commit with what it revokes; the result badged committed, WHAT HAPPENED and NEXT with Approve… (W2 captures 45 to 47) | **same** |
| Bindings… (the Bindings board line) | a card below the table: each platform's template, per-device overrides with one to add; the preview naming every device that moves; the reason and the commit | "Bindings: which template renders which device in <network>": EACH PLATFORM'S TEMPLATE as selects, DEVICES WITH THEIR OWN TEMPLATE with "Give a device its own template", Preview the change, "A preview writes nothing." (W2 capture 53); the result badged committed (W2 capture 52) | **same** |
| Removing an override | an override's own removal | chosen in the override's drop-down, "its platform's (remove this override)"; no Remove beside it (W2 captures 53 and 54; C1063) | **deviation** (log: Templates: an override is removed through its drop-down, with no Remove (C1063)) |
| Seed the library… (the 2026-10-10 seed line) | a network with no templates: Seed the library…, previewed and committed as the person | "Seed <network>'s library from the shipped one": what it adds, what it does not overwrite, the confirm as <you>; the result badged seeded with the commit and the files, and "Approve each template on its row before a deploy renders through it." (W2 captures 28 and 29; W3 step 12) | **same** |
| Bring in the shipped version… (C566 board C) | the row "behind" with Bring in the shipped version…; its card: what changes, on the devices, approval, checks, the commit; the result with Approve… and Open Coverage | not on the host in either walk (every row "current"); `_template_op.html`'s bring card draws the same parts, and the landing's C566 row was compared in landing.md | **same** |
| Coverage tab | the Templates › Coverage line (no board file) | not opened in either walk | **later** Stage 7's tail: C650's comparison of the screens no walk reached (tests/test_board_fidelity.py, UNCHECKED's comment) |
