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
Templates compared: templates/v2/_intent.html, templates/v2/_intent_edit.html, templates/v2/_intent_check.html, templates/v2/_intent_words.html, templates/v2/_intent_proof.html
Templates sha256: `9e9d8c6dbf2e7e96045faa0dcfb1d16a92c96b9501270e370d397e3602458092`

Compared again 2026-10-17 (C1023) after "Open (commit) with your edit on it" (`_intent_edit.html`)
and Write the ticked lines into the document (`_intent_check.html`) became busy on themselves
while their request is out ("Placing your edit…", "Writing them in…"). At rest the page draws
the same words. Compared by the template and the page the tests draw
(tests/test_v2_busy_on_itself.py), not a new shot; no region's verdict changed.

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

Compared again 2026-10-26 (feature 7, board F7, `IntentWords.dc.html`, signed off under the
Phase 7 mode): `_intent.html` includes **Change it in words** (`_intent_words.html`, which
joins the templates compared) above the committed document, for a device whose intent is not
bootstrap only. Shot `tab-intent-words` (`tests/test_board_shots.py::test_tab_intent_words`,
on the host's real committed s1): the board at 1440, and the page at 1440, 1280 and 390, the
row drawn and then a sentence drafted (hosted AI allowed, the adapter answering as planted).
- The row: the label with the AI mark, the box at the row's width, Draft the change (busy on
  itself), its (i); at 390 the button wraps under the box. **same** as F7.
- The draft: the notice with the model and cost; the changes in words; the editor's own check
  column (`_intent_check.html`, the same rows, pending lines and checks as an edit typed by
  hand); what left the host. As F7, but for the footer: F7 draws "Why, in one line" and Commit
  to s1's intent; built to the preview only (the overnight order), the notice says the draft
  is not committed and to make it with Edit. **later** (feature 7's commit step).
- Every other region of this record rendered as before; the row adds no control to the
  editor's own card. No other region's verdict changed.
Templates sha256 before: `5f031cd1606d366b6d41d2f97beeda3250dc19fd44cee44a1a584f56e26451b7`.

Compared again 2026-10-26 (feature 7's parts 1 and 2; board F7 redrawn under the Phase 7 mode,
canvas versions 146 and 147). `_intent_words.html` gained how the names were read, Mercury's
question with its candidates, a name the device lacks with its interfaces, "Already so"
(C1771), and the commit: Why, in one line; Commit this draft; Commit and plan deploy; Discard
draft; and the committed and refused results. Shots: `tests/test_board_shots.py::
test_tab_intent_words` on the host's real committed s1 (its walk: drafted from shorthand, a
name s1 lacks, which host port, the choice drafted, committed), at 1440, 1280 and 390, beside
F7 at 1440.
- **How your words were read** (F7 1): each phrase, the name it resolved to and how; and when
  the Topology read could not be used, that sentence too. **same**.
- **Which one** (F7 7): the question from s1's own intent, no call, the candidates as buttons
  named by their descriptions, and Both. **same**.
- **Not found** (F7 8): a name s1 lacks, its interfaces as buttons (every one, where F7 draws
  four and "…"), and s1's neighbours linked. **same**.
- **The footer** (F7 1): Why, in one line, starting from the sentence; Commit this draft and
  Commit and plan deploy, each with its (i); Discard draft. **same**; the earlier **later**
  closes.
- **Committed** (F7 1b): the commit, as whom, Source ai-draft with the call linked, nothing
  sent, Plan deploy… and its (i). The row keeps your words in the box, where F7 draws it
  empty. **deviation** (log: F7 committed: the words kept).
- **Not committed** (F7 1c), **Already so** (F7 1e): their tests are
  tests/test_ai_intent_change.py's (moved intent, a differing patch, the no-op draft); not
  shot. **same** by their rendered text.
- Board 5 now draws C1770's behaviour (another device's name is words; a draft changing it is
  refused, naming it). **same**.
Templates sha256 before: `91ee38590f13ff5f43224862e60ebe3b5d999643989b1730e746cafb31d93162`.

Compared again 2026-10-27 (C1693, board H-N, `IntentNormalise.dc.html` version 165 on the
canvas page "C1693", signed off under the Phase 7 mode; its five proof lines as the operator
clarified them the same day). `_intent.html` offers Normalise the formatting… for a
hand-formatted document; `_intent_edit.html` opens on Mercury's formatting; `_intent_check.html`
draws the proof (`_intent_proof.html`, which joins the templates compared) and the editor's
Commit again, out of band; the refusal and the committed result say what Normalise did.
Compared by the templates against the board and by the page the tests draw on r2's real intent
laid out by hand (tests/test_intent_normalise.py: the client's fragments, and the real
browser's walk: offered, proved, a planted keyed-hash mismatch stopping it with Commit disabled,
proved again, committed in place, not offered after). **Shots owed** (log: Tab intent:
Normalise's shots owed (C1693)): board H-N and `tab-intent-normalise` at 1440, 1280 and 390
are taken with the next run of tests/test_board_shots.py.
Templates sha256 before: `83d13c05b9150e6145fd0e0df0f2da0705ddfe03d867747cdbf83b56f7aa9862`.

Compared again 2026-10-27 (C1907 and C1908's draft; board F7-Q, `IntentWordsAsk.dc.html`,
version 168, signed off under the Phase 7 mode; the hash above written again after the
two-device commit's hidden fields changed, its patches carried in `patch`, the field the
confirm is bound to, with `pair` marking it: nothing drawn changed). `_intent_words.html` gained Mercury's questions
with their controls (two-ended with no managed far end, alternatives, an OSPF network with no
area, a description with no text: buttons, a field and Continue, Cancel, each busy on itself,
"no AI call, $0"), the sentence as decided, one draft of both ends of a link side by side with
the ends' match said and Commit both devices' intent, the two-device commit's result, and the
ends' mismatch refused. The open quote, the typed placeholder and a change no operation makes
keep the notice for Mercury's own answer (`w.by == 'mercury'`), which has no buttons (board
F7-Q's closing note: a refusal that leaves no choice has no controls). **Compared by the
template and the pages the tests draw** (tests/test_ai_intent_change.py's question, answer,
two-device draft, mismatch and commit tests), **not by shots: the board and page shots at 1440,
1280 and 390 are owed** (tests/test_board_shots.py has no F7-Q walk yet). The rows "F7-Q …"
below; no other region's verdict changed.
Templates sha256 before: `e3215e27e5d968fc927fbb012dd9d835c4fcc8748c59f6285cb2f0d5d9e73fff`.

Compared again 2026-10-27 (C1933, the operator's decision: a two-device draft is refused only
for a mismatch it creates or changes). `_intent_words.html` draws, between the two-device
draft's notice and the sentence as decided, one warning per mismatch already in committed
intent that the draft leaves as it is: "The ends already differ:" with the mismatch and "this
change does not touch it", or "This change may fail:" when the draft changes the same link's
trunk, tunnel, OSPF or OSPFv3 settings (`intent_words.ends_judged`'s bearing rule). Board F7-Q
draws the refusal only (Q1b), which stays as built for a mismatch the draft creates or
changes. Compared by the template and the pages the tests draw (tests/test_ai_intent_change.py's
created mismatch refused on r2 and r2b, and an existing one said beside the offered draft on s1
and s2; tests/v2_context.py's walk on r3 and r4), not by shots, which stay owed with F7-Q's.
The row "F7-Q Q1: a mismatch already in committed intent" added and Q1b's built words
narrowed; no other region's verdict changed.
Templates sha256 before: `0dcda5f7a26ed1b010602152368694e12fa34f6e8a106a288dab247e09e9ac39`.

Compared again 2026-10-27 (C1909, the paired deploy; board F7-Q, version 168, Q1's footer:
"Then Deploy opens the plan for r3 and r4, both ticked: one preview, one confirm by hash. Verify
reads the link (adjacency up on both ends, or the trunk forwarding), and if either end fails,
both are rolled back, and the receipt says what each end achieved"). `_intent_words.html`: the
two-device draft's footer says that sentence, its verify words narrowed to what is read (the
link's line protocol on both ends, and the adjacency across it when the change touches OSPF or
OSPFv3: a trunk's forwarded VLANs are not read, no capture of `show interfaces trunk` existing to
build the parser on); the commit form carries the draft's link (`link`); and the two-device
commit's answer offers **Deploy both ends…** (its (i) opening the deploy page's paired-deploy
section), which opens Devices › Plan a deploy with both devices ticked and the link carried, in
place of "Deploy each device from its page; the paired deploy (C1909) is not built yet". Compared
by the template and the pages the tests draw (tests/test_ai_intent_change.py's two-device commit
and the paired plan it opens; tests/v2_context.py's walk on r3 and r4), not by shots, which stay
owed with F7-Q's. The rows "F7-Q Q1: the footer" and "F7-Q Q1: committed both" rewritten; no
other region's verdict changed.
Templates sha256 before: `0bbb08471c76ae886906208b8ceeb0cc6a51a3460a3c45920627664a849cdb95`.

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
| Phone | no phone board; the board's columns stack under 900 p| Normalise: the offer (H-N A) | a warning notice in the card, "This document is hand-formatted." and its words, Normalise the formatting… inside it; How does this work? in words in the card's head beside Edit | the same notice and words under the last commit's line, only for a document that does not round-trip, Normalise the formatting… inside it with its (i) beside it (the control's own link, C503's rule; the head keeps Edit's); for a viewer who may not commit, the notice says who may normalise it, with no button | **deviation** (log: Tab intent: Normalise's (i) beside its button (C1693)) |
| Normalise: the editor's head (H-N B) | "r6 · Intent · editing", opened at the commit, "Mercury's formatting loaded; nothing written" | "Editing r2's intent", the file, opened at its blob, "Mercury's formatting loaded; nothing written." in place of "Nothing is written until you commit" | **same** |
| Normalise: the document (H-N B) | the lines whose formatting changed highlighted, "Highlighted: lines whose formatting changed (41 of 333). The document's data is unchanged." | the plain text box (C901's deviation stands) with Mercury's formatting in it, and under it "Mercury's own formatting of the committed document: N of M lines changed formatting", the data's sameness left to the proof beside it | **deviation** (log: Tab intent: Normalise's changed lines counted, not highlighted (C1693)) |
| Normalise: the proof (H-N B) | "Formatting only: proved", five lines each with ✓: the parsed document equal; the render byte-identical (318 lines); the device diff empty against the committed golden; the masked lines compared by keyed hash, 3 of 3 identical, their kinds named, "No value is shown or kept"; the new text round-trips | "Formatting only: proved" with its badge, the five lines in the board's words each with a pass badge, the counts measured (the render's lines, N of N, the kinds from the masking's labels), and a line of counts under them; the editor's Checks and any unmodelled lines stay below it | **same** |
| Normalise: the reason and the commit (H-N B) | the Reason field and Commit the formatting only under the proof in the right column, "One commit on r6's intent, as you, with your reason…" | the editor's own footer: "Why, in one line" and the Commit, drawn again by the check as Commit the formatting only with the board's words, disabled until the proof passes | **deviation** (log: Tab intent: Normalise's reason and commit in the editor's footer (C1693)) |
| Normalise: stopped (H-N C) | "Stopped: this is not formatting only", the render's differing lines as a diff, a masked line named by its line and masked text, "Its value is not shown", every differing line listed, Commit disabled | "Stopped: this is not formatting only" with its badge, each failing line with a differs badge in its own words, the refusal's notice, every differing line under where it differs (the render, the device diff, the masked lines), a masked line by its number and masked text with "Its value is not shown. Committing this could change the device's credential.", Commit disabled | **same** |
| Normalise: refused at the server | not drawn (the board's button is disabled) | the commit refused by the server whatever the page showed: the editor again, its refusal naming each failing line, and the proof drawn as when stopped | **deviation** (log: Tab intent: Normalise refused by the server (C1693)) |
| Normalise: committed (H-N D) | "r6's intent: formatting normalised, commit … by … at …, '…'. The render is unchanged. Change it in words is available now."; History · the commit's diff | the editor's committed card (its commit, subject and person as for any edit) with a notice "r2's intent: formatting normalised, proved before it was written. The render is unchanged. Change it in words is available now."; Edit again · See it in History, no link to the commit's diff | **deviation** (log: Tab intent: Normalise's committed result (C1693)) |
| Every commit in Mercury's formatting | not drawn | the document's label says it is "opened as committed, byte for byte, and committed in Mercury's own formatting"; the Checks say "Committed in Mercury's own formatting" when the typed text is laid out otherwise; the committed card says the data was kept without its comments and layout | **deviation** (log: Tab intent: every commit in Mercury's own formatting, said (C1693)) |
| F7-Q Q1: one draft, both ends (notice) | "One draft, both ends of the link r3 GigabitEthernet4 ↔ r4 GigabitEthernet4 · the ends match: …", the model and cost | the same words, the link and the ends' facts as Mercury read them ("both trunks, VLANs 10, 20, 30, native VLAN 1"), the model and cost; the sentence as decided under it when a question came first | **same** |
| F7-Q Q1: the two ends side by side | each device, "intent at <sha>", its intent's YAML lines (- and +) | each device and "intent at <sha>", the changes in words and the configuration lines the change makes (the editor's rows), stacked under 900 px | **deviation** (log: F7-Q Q1: each end drawn as the editor's changes) |
| F7-Q Q1: the footer | Commit both devices' intent, Discard; "Then Deploy opens the plan for r3 and r4, both ticked …, both are rolled back" | Why, in one line; Commit both devices' intent (busy on itself, its (i)); Discard draft; "One commit, as you, with your reason. Then Deploy both ends opens the plan for s1 and s2, both ticked: one preview, one confirm by hash. Verify reads the link (its line protocol on both ends, and the adjacency across it when the change touches OSPF or OSPFv3), and if either end fails, both are rolled back, and the receipt says what each end achieved" (C1909) | **deviation** (log: F7-Q Q1: the footer says what the link's verify reads) |
| F7-Q Q1: Why, in one line | not drawn | the commit's one line, required, starting from the sentence, as on every draft | **deviation** (log: F7-Q Q1: Why, in one line before the two-device commit) |
| F7-Q Q1: committed both | not drawn (the board's note); its footer: "Then Deploy opens the plan for r3 and r4, both ticked" | "Committed to s1 and s2's intent: one commit, <sha>, as <person> (Source: ai-draft, with the AI call). Nothing was sent to either device. Deploy both ends opens the plan for s1 and s2, both ticked: one preview, one confirm by hash; verify then reads the link, and if either end fails, both are rolled back." and **Deploy both ends…** (primary, its (i) on the deploy page's paired-deploy section), opening Devices › Plan a deploy with both ticked and the link carried; nothing is started (C1909) | **deviation** (log: F7-Q Q1: committed both offers Deploy both ends…) |
| F7-Q Q1b: the ends do not match | "Not drafted: the two ends would not match." and the mismatch named, red | the same words and colour, each mismatch the draft creates or changes naming both ends' values (C1933) | **same** |
| F7-Q Q1: a mismatch already in committed intent | not drawn (the board draws the refusal only) | the draft offered, and beside it, under its notice, a warning per mismatch the draft leaves as it is: "The ends already differ: s1 GigabitEthernet0/3 allows VLANs 10, 20, 30 and s2 GigabitEthernet0/3 allows VLANs 10, 20, already in committed intent; this change does not touch it", or "This change may fail: …; this change touches the link's trunk settings and may fail because of it" when the draft changes that family | **deviation** (log: F7-Q Q1: a mismatch already in committed intent, said beside the draft) |
| F7-Q Q1c: a far end Mercury does not manage | "One question first (no AI call, $0): h1 is not a device Mercury manages, so only s1's end, GigabitEthernet1/0, can be drafted."; Draft s1's end only, Cancel | the same words and buttons, "from s1's own intent" in the head | **deviation** (log: F7-Q: the questions keep F7's "from <device>'s own intent") |
| F7-Q Q1c: an unknown far end | not drawn on version 168 (the version 167 sign-off decided a device picker when no read names the far end) | each device of the network a button beside Draft s1's end only | **deviation** (log: F7-Q Q1c: a device picker when the far end is unknown) |
| F7-Q Q2 and Q3: alternatives | the facts and Which one?; a button per VLAN that can be added (one when only one can), the interfaces with their description and state, and Both | the same buttons; the facts in Mercury's words; Cancel beside them | **deviation** (log: F7-Q Q2 to Q5: the questions' words, and Cancel on each) |
| F7-Q Q4: an OSPF network with no area | Area 0 as a button, "Another area" field checked before Continue is enabled | a button per area the device's OSPF holds, the field and Continue; the field's pattern refuses Continue with no valid area, the server checking again | **deviation** (log: F7-Q Q4: the area checked on Continue) |
| F7-Q Q5: a description with no text | the question with the current description, a text box, Continue, "The text typed here is the value: it reaches the model as a placeholder" | the same, the text quoted into the decided sentence and held as a placeholder | **same** |
| F7-Q: after any answer | "the sentence the draft uses is shown as decided", then the draft as board F7 draws it; Cancel leaves nothing drafted | "Your words, as decided: <q>…</q>" over the draft (or the next question), the box holding that sentence | **same** |
