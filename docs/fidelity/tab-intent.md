# Fidelity: the device page's Intent tab (H, the one intent editor)

The Intent tab as built, compared region by region with its approved boards (C650's step), after
the operator's walk W1 (2026-10-16, steps 20 to 22 and 25, which edited s1's and s2's intent on
it and committed both; C444). Read from shots of the boards and the page side by side, in the
same headless Firefox, on the browser layout test's lab (`tests/test_profile_apply.py`'s: r2's
real captured configuration, its committed intent parsed from it by the real extraction, given
its syslog heartbeat first as a person does in `tests/test_intent_editor_v2.py`'s browser walk)
(`tests/test_board_shots.py::test_tab_intent`). The walk is a person's: the read-only card,
Edit, Loopback0's description edited (the deploy's other pending lines are the extraction's
heartbeat applet, never on r2's golden), an error typed and removed, the commit; then, apart,
another person committing a different line between the open and the commit. Read beside them:
the operator's W1 captures 24 (Editing s1's intent, opened at the bulk commit), 25 (Gi0/1's
description deleted: the diff, the Mode B notice, the checks) and 26 (Committed to s1's intent),
at about half desktop width.

Boards: on the "NMAS v2 mockups" canvas, page "7.4 Fleet" (A to M approved 2026-10-04):
`DevIntentEdit.dc.html` (H, THE intent editor in Document mode, signed off 2026-10-04, 1440),
`DevIntentFields.dc.html` (H's Fields mode, approved 2026-10-04, 1440),
`DevIntentStates.dc.html` (H's states: the read-only tab with Edit, an error, committed,
intent moved; approved 2026-10-04, 1440) and `DevIntentDiffs.dc.html` (H revised, C500,
approved on canvas v52 and built: every diff line its own row, one diff when they are equal,
both when they differ). The tab itself was approved with the device tabs on 2026-09-30
(NSOT_STAGE7_PLAN 1g). The boards draw r3 on 192.0.2.x; the lab here is r2.
Shots: each board at 1440; the page at 1440, 1280 and 390 in six states (`tab-intent-view`,
`-open`, `-edited`, `-error`, `-fixed`, `-done`), and `tab-intent-moved` and
`tab-intent-departs` (C884) at 1440.
Compared 2026-10-16.
Templates compared: templates/v2/_intent.html, templates/v2/_intent_edit.html, templates/v2/_intent_check.html
Templates sha256: `a44a26693226c656effb48d8c386bbf4058c3ffcc52b4dfbd330dc2e2531f2fc`

Compared again 2026-10-16 (C522) after `_intent_edit.html` gave each of its cards one "How does
this work?" in words, in its head (C503's rule): editing (before Discard the edit, where board H
draws it), committed (beside the title, as board States draws it) and intent moved (before
Discard the edit, not drawn there on the board); the buttons inside keep the (i) alone. Every
`tab-intent-*` shot taken again at 1440, 1280 and 390 beside the boards. The editor's head and
the committed result rewritten, intent moved now a deviation; no other region's verdict changed.

Compared again 2026-10-16 (C884) after `_intent_edit.html`'s committed result changed: what a
deploy would send is drawn as rows (the lines it sends), and the lines only the device holds
apart, with Remove lines (Mode B)…. `tab-intent-done` shot again at 1440, 1280 and 390, and a
new shot, `tab-intent-departs` (1440): Loopback0's description deleted and committed. The two
committed regions rewritten and one added; no other region's verdict changed.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Tabs | Overview, Intent (on), History, Monitoring, Logs, NetBox, Neighbours | the same, Intent on, and Ask the device after Neighbours (tab:ask, its own sign-off of 2026-10-08, after this board) | **same** |
| The read-only card (H's state 0) | "Committed intent", Edit and How does this work?; last changed by the commit; what the network's monitoring profile adds | the same, the document drawn under it as the tab signed off on 2026-09-30 draws it, "Read from the repository at HEAD"; the tab's (i) above the card as on every v2 tab. The lab commits no profile, so the profile's line is compared by the template (`iv.profile.applies`, the board's words) | **same** |
| Who may edit | Edit only for a person who may commit; a bootstrap-only device offers Seed intent from Actions | the same, each said in words under the card when Edit is not drawn | **same** |
| The editor's head | "Editing r3's intent", the file, opened at the commit with its subject as a link and its age, "Nothing is written until you commit"; the mode toggle, How does this work?, Discard the edit | the same words, How does this work? and Discard the edit ("host_vars/s1.yml, opened at fe30bbd (host_vars: W1 walk: …, 28 min ago)" in capture 24); the opened commit's subject in words, not a link; Commit to s1's intent keeps an (i) beside it (C522: until then the head had no worded link and the card only that (i)) | **deviation** (log: Tab intent: the editor's head, its link in words (C522)) |
| Document or Fields | a two-way toggle in the head | not drawn: Document mode alone is built | **later** C907 (H's Fields mode, board J, not built; after cutover) |
| Fields mode (board Fields) | the fields intent models per interface, Add a setting from the platform's catalog, raw lines with their round-trip check | not built | **later** C907 (H's Fields mode, board J, not built; after cutover) |
| The document | a line-numbered editor, the changed lines marked, "valid · checked as you typed" above it, the label, the note on errors and secrets | a text box with the label and the note; no line numbers or marked lines (capture 25: finding Gi0/1's item meant scrolling a plain box); the validity is the check column's (the error, or the diffs and checks) | **deviation** (log: Tab intent: the document is a plain text box with no line numbers (C901)) |
| An error as you type (state 1) | the line and column as a chip in the title, the card red, the line marked in the editor, the message under it, the diffs kept dimmed, Commit disabled "waits on line 15, column 13" | the check column becomes the error: "Line 3, column 10:" with the parser's words, the line quoted with a caret under the column, "The commit waits until the document is valid"; Commit stays drawn, and a commit then is refused naming the line and column, the chip in the title and the card red | **deviation** (log: Tab intent: an error is drawn in the check column) |
| What your edit changes | the section and its − and + lines | the same, each line its own row (board Diffs): `interface GigabitEthernet0/1`, `- description spare port` (capture 25) | **same** |
| The two diffs equal (Diffs 1) | one diff, "the same", "A deploy would send exactly this change", the golden and its age, nothing else pending | the same words; not reached by the lab (its extraction's heartbeat applet is pending on r2), compared by the template and tests/test_intent_diffs.py's `test_equal_diffs_are_one_with_the_line_saying_so` | **same** |
| The two diffs differ (Diffs 2) | both: from this edit with its count; "not from this edit" with each pending line labelled from the golden history; where each came from; against the golden, merge-only, the total | the same layout and labels ("never on r2: not yet deployed", each with its section) | **same** |
| The counts in Diffs 2 | 1 from this edit, 2 not from it, "3 lines in all" | "From this edit: 1 line", "not from this edit 3 lines", "3 lines in all": the pending count counts the new applet's header line, which the total leaves out | **deviation** (log: Tab intent: the pending count counts a section's header (a defect, register C650 follow-up)) |
| A deletion a deploy keeps | "A deploy will not remove what this edit deletes" with the line, and a link to Actions › Remove lines (Mode B)… | the same notice and lines (capture 25); "Actions › Remove lines (Mode B)…" is words, not a link, and "Mode B" is said to a person (C901) | **deviation** (log: Tab intent: the Mode B removal is named, not linked (a defect, register C650 follow-up)) |
| Lines not compared | "1 line not compared", which on hover | "3 secret-bearing lines could not be compared", in words | **same** |
| Checks | six: parses and names r3; the schema; no secret and every character accepted; the template renders it, approved; at commit, the version opened; a verified person | three: the first three as one row; the template renders it ("not yet" with a deploy's blocking reasons); at commit (captures 24 and 25). Who commits is the footer's: Commit is drawn only for a person who may commit, else the footer says so | **deviation** (log: Tab intent: the checks) |
| Lines intent does not model | not drawn | the lines a template cannot render, each with a tick box, "Write the ticked lines into the document" into its `unmodeled_ack` block (C481) | **deviation** (log: Tab intent: lines intent does not model, ticked to acknowledge) |
| Footer | "Why, in one line", "Commits the document as you, with its reason. Nothing is sent to r3.", Commit to r3's intent | the same, the reason required, Commit busy on itself ("Committing…") | **same** |
| Committed (state 2): the result | "Committed to r3's intent · done" and How does this work? (board States); the commit as a link, "as operator@example.com (verified), just now"; "Nothing was sent", a Departs from intent chip; Edit again · See it in History; Plan a deploy of these 2 lines… with How does this work? | the same title and links, How does this work? in the head (C522), Plan a deploy… with its (i) alone (C503's rule: words once per card); the commit's sha in words; the person without "(verified)" or a time; "it now departs from intent until a deploy sends the lines beside" in words, or, when the device also holds lines intent no longer has, that a deploy keeps them until they are removed (Mode B); Plan a deploy… without a count (capture 26; shots `tab-intent-done`, `tab-intent-departs`) | **deviation** (log: Tab intent: the committed result's words) |
| Committed: what a deploy would send now | the program: the section and the line it sends | the lines a deploy sends, each its own row under its section's line, marked +, and "Against its golden, merge-only, 3 lines" (shot `tab-intent-done` at 1440, 1280 and 390: the heartbeat applet and Loopback0's description). Until C884 a unified diff of the golden against the render, whose deletions read as sent (capture 26) | **same** |
| Committed: what a deploy keeps (C884) | not drawn (the committed state draws a deploy to plan) | the lines only the device holds, which a merge-only deploy never removes, apart under "What a deploy keeps: only r2 holds these" with Remove lines (Mode B)… beside them, Plan a deploy… staying primary (shot `tab-intent-departs`: Loopback0's description deleted). When a deploy would send nothing, the card is headed "How s1 now departs from its intent", those lines its only rows, "A deploy sends nothing: it is merge-only", and Remove lines (Mode B)… is its primary action, opening the device page's deploy card at the removal: the operator's fix (tests/test_intent_committed_departs.py on s1's real capture; not shot, this lab always has lines to send) | **deviation** (log: Tab intent: what a deploy keeps, with Remove lines (Mode B)… (C884)) |
| Intent moved (state 3) | "not saved"; you opened, it is now (a link), by whom, when and its subject, "Nothing was written"; your edit kept and their change side by side; Open with your edit on it, or Open alone when both change one line | the same, the new commit in words (shot `tab-intent-moved`; both forms: tests/test_intent_editor_v2.py's `TestCommitting`); How does this work? in the head before Discard the edit, which the board does not draw there, the Open button keeping its (i) (C522) | **deviation** (log: Tab intent: intent moved's head carries How does this work? (C522)) |
| Phone | no phone board; the board's columns stack under 900 px | the columns stack, the document first, then the check column and the footer | **same** |
