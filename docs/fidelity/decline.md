# Fidelity: Decline… and Undo decline… (C718, 2026-10-13)

Board: `CoverageDecline.dc.html` (canvas page C603, "C718", APPROVED by the operator
2026-10-13), boards A to D at the desk's width. Shots: tests/test_board_shots.py `test_decline`
(`decline-page` and `decline-card-page` at 1440 and 390, beside `decline-board`). The page is
fed r2's real intent (tests/test_decline's lab): a section declined through the real apply (Mgmt
sources, which r2's golden does not configure), r2's IP SLA as a row not in intent (planted,
the lab having no IP SLA policy), then the Decline… card opened as its button opens it, its
reason typed. The board draws no phone width; at 390 the rows stack (label, why, then the
controls) and the card's parts sit one above the other, as every op card does.
Templates compared: templates/v2/_decline.html, templates/v2/_coverage.html, templates/v2/ip_sla.html
Templates sha256: `8a7ceabf2b09ce70cdbff184170f9c7dd79503e80850061994741ed3b5422690`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| The summary | "7 of 9 devices fully covered · 1 not in intent (add to intent, or decline)"; after, "· 1 declined" | the same words appended to Coverage's summary | **same** |
| A gap's row | its device, "Not in intent" and the section, why in the IP SLA page's words, "r6's intent has none" | the same, the why the IP SLA page's own suggestion for the device | **same** |
| Fix it here | Add to intent… and Decline…, each with its (i) | the same; Add to intent… opens the IP SLA page for the device, where its commit is | **same** |
| Where the rows sit | the rows are Coverage's table | under Coverage's grid and its legend, the grid being C603's to redraw | **deviation** (log: C718: the not-covered and declined rows sit under Coverage's grid) |
| The card's head | "Decline IP SLA on r6", How does this work?, Cancel | the same | **same** |
| Why | the reason, "recorded with the decline and shown wherever r6's IP SLA is drawn (three words or more)" | the same words over a full-width box; typing asks again | **same** |
| The intent change | `host_vars/r6.yml`, one commit as you; the entry section, reason, by, at | the same, the entry's keys in intent's sorted order (at, by, reason, section) | **deviation** (log: C718: the decline's intent lines in alphabetical order) |
| Nothing is sent | "Nothing is sent to r6: … no program, no hold and no verify. The decline lives in r6's committed intent, where the profile and Coverage already read exclusions." | the same words | **same** |
| Checks | a verified person; three words or more; no IP SLA operation in intent (refused, naming them, when there are) | the same three, each pass or fail; a failing one holds the confirm back and says why | **same** |
| The confirm | "Bound to r6's intent as previewed: if it moves before you confirm, nothing is committed." "Record the decline in r6's intent" | the same, after who is confirming | **same** |
| Declined on Coverage | "Declined", the section, "Declined by <operator>, <date> UTC: "<reason>". Not a gap: the summary counts it as declined, never as covered or missing." Undo decline… | the same words and control | **same** |
| Declined on the IP SLA page | a row of its probe table: "Declined by …" · Undo decline…, "no probe" | a line of the page's Not suggested list: Declined, who, when, why, Undo decline… | **deviation** (log: C718: the IP SLA page's declined device in its Not suggested list) |
| Undo decline… | the same preview with the entry removed, "Afterwards r6's IP SLA reads Not in intent again", the decline's commit kept, "Remove the decline from r6's intent" | the same | **same** |
