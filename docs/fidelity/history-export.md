# Fidelity: History › Export (2026-11-10)

Board: `docs/boards/lab9-sdn.html` artboard H (1440), self-signed under the Phase 7 mode
2026-11-10 (docs/STANDING_APPROVAL_LOG.md, "Board lab9-sdn H (History › Export, Lab 9 B5)
self-signed"). Its yellow dashed notes are the board's annotations, not page text.

**Compared from the templates and their rendering, not from shots.** tests/test_board_shots.py
has no case for this tab yet, so the regions below were read from the built templates and the
HTML tests/test_history_export.py's lab renders (a person's call and a background job's call on
Lab; Every network; a range past 31 days; an empty range), beside the board's HTML. A shot at
1440, 1280 and 390 is the next step of this record.

Templates compared: templates/v2/_history_export.html, templates/v2/_history_body.html
Templates sha256: `d7b2a69641d9ce42946c57353591714d058ae3a71d064b3331edcd9b0718a654`

Compared again 2026-11-10 (C2942): only the "Not on <network>" line's words changed (a call
naming no network is now the installation's own, or one recorded before 2026-11-10). It is the
same line in the same place, and every region's verdict below is unchanged.

Compared again 2026-11-10 (C2943, C2945, C2946): only the failure card's words changed (the
planted issues each analysis missed, B3's detections on normal traffic, B4's analyst evaluation
misses and false positives), and Not recorded's words with them; the same lines in the same
places. The heading-and-words region's deviation is now the log's seventh line ("Board
lab9-sdn H built, 7", which adds to the fourth); In the range keeps its verdict, the fifth.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | History on | History on (the frame's sidebar) | **same** |
| Page head | "History › Export (i)" | "History (i)" and the network's sub-line, the remote's card, then the tabs Timeline, Query, Baselines, Export (on); the tab's (i) "About the export" under them | **deviation** (log: Board lab9-sdn H built, 1) |
| Network | a select: campus-sdn, Every network | a select: every network by name, then Every network; the page's network chosen | **same** |
| From and To | "2026-11-24 00:00 UTC", "2026-11-30 23:59 UTC" | From (UTC) and To (UTC) as whole days, the last 7 by default, and Show | **deviation** (log: Board lab9-sdn H built, 2) |
| AI calls and cost: heading and words | "AI calls and cost", the columns in words, a total per day and per feature | the same heading and words, and "How does the export work?" in the card's head | **same** |
| AI calls and cost: In the range | "412 calls · $0.38 · 3 refused by validation · 1 refused at the day cap" | "N calls · $X.XXXX" then each outcome there is: refused by validation, refused at a cap, refused by a gate, failed, presses joined | **deviation** (log: Board lab9-sdn H built, 3) |
| AI calls and cost: downloads | Download CSV (primary), Download JSON | the same, each a GET to `/v2/history/export/calls/<csv or json>` with the network and days | **same** |
| False positives and failures: heading and words | the kinds in words: dismissed, refused or failing the check, Verify failure, rollback, protected-flow refusal, evaluation misses | the same heading; the words add evaluation false positive, planted issue each analysis missed, detection on normal traffic in a false-positive run, analyst evaluation miss or false positive, and AI answer said wrong | **deviation** (log: Board lab9-sdn H built, 7) |
| False positives and failures: In the range | "9 dismissed (6 "normal traffic") · 2 refused classifications · 1 Verify failure, rolled back · 4 evaluation misses" | the kinds there are with their counts, the most given dismissal reason after the dismissals; then By kind (every kind, zero included) and Not recorded (the other case scripts' per-case misses) | **deviation** (log: Board lab9-sdn H built, 5) |
| False positives and failures: downloads | Download CSV (primary), Download JSON | the same, to `/v2/history/export/failures/<csv or json>` | **same** |
| Calls naming no network | not drawn | on one network's card, the calls in the range that name no network, and that Every network lists them | **deviation** (log: Board lab9-sdn H built, 5) |
| The note | "Both files carry their range, network, the time they were made and who made them in their first lines; amounts are the ledger's, summed by UTC day, never carried forward." | the same sentence, and the range's length against its 31 | **same** |
| States the board does not draw | not drawn | a refused range (its length, a From after its To, a network no one has) in place of the cards; a record that could not be read; nothing in the range, above the cards | **deviation** (log: Board lab9-sdn H built, 6) |
| Phone width | not drawn | the two cards one column under 340 px wide (`.hist-export-cols`), the filters wrapping as History's do | **same** |
| The callouts | yellow dashed notes | not page text | **same** |
