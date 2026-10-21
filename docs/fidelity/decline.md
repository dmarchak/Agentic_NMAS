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
Templates sha256: `471a9bc42cf0dbccd6342dc1b17640db8d44930d0be4766a448e790b837fa366`

Compared again 2026-10-21 (C1491, the tuning sprint): `ip_sla.html` gained a section above the
suggestions, "Probes off the policy's frequency". It lists each probe that intent holds at
another frequency than the policy's, with its own ticks and commit, posting to the same commit
route. Its subtitle no longer says changing a running probe waits on staged run 9 (the
re-create, C290, is built). No region of this board changed: the Decline… and Undo decline…
controls, the suggestions' legend and the Not suggested list are as before. The new section is
not on this board, so it is a deviation (below). It was compared by the template and
`tests/test_ip_sla_policy.py`'s `TestTheFrequencyPath`, not a new shot: words and a ticked list
in the page's existing form.

Compared again 2026-10-21 (C1499, the overnight run): `ip_sla.html` gained a section above the
frequency section, "Committed, not yet on the device". It lists each device whose committed IP
SLA intent its configuration does not run (a send that failed after the batch committed),
saying what intent holds and what the device runs, its last failed send's reason, and "Retry
<device>", a link to the same scoped preview for that device alone. No region of this board
changed. The new section is not on this board, so it is a deviation (below). Compared by the
template and `tests/test_ip_sla_policy.py`'s `TestACommittedProbeNotOnItsDeviceStaysListed`,
not a new shot: words and a link in the page's existing card style.

Compared again 2026-10-18 (C1305, the operator's walk): Coverage's grid draws a declined cell as
its own "declined" mark (who, when and why on hover) linking its row in this table, which now
carries the anchor `decl-<host>-<section>`; a not-applicable cell draws "n/a"; the legend
names both, no "blank". The board's rows are unchanged; the grid is C603's, and the link from
cell to row is a new region, a deviation (below). Compared by the template and
tests/test_decline.py's `test_coverage_draws_every_cell_s_meaning_and_the_profile_counts_the_decline`,
not a new shot: words and a link.

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
| A declined cell on the grid (C1305) | not drawn: the board draws the rows | its own "declined" mark, who and why on hover, linking its row here | **deviation** (log: Coverage: a declined cell is its own mark, linking its Undo decline row (the operator's walk, 2026-10-18)) |
| Committed, not yet on the device (C1499) | not drawn: the board predates it | a section above the frequency section, each device whose committed probes its configuration does not run: intent's frequency and target against the device's, its last failed send's reason, and Retry <device> to the scoped preview of that device alone | **deviation** (log: IP SLA: a committed probe its device does not run stays listed with Retry) |
| Probes off the policy's frequency (C1491) | not drawn: the board predates it | a section above the suggestions, each probe's frequency now and after with its cost, ticked, and its own commit; the preview's re-create refused until the delete is measured | **deviation** (log: IP SLA: probes off the policy's frequency get their own section) |
| Undo decline… | the same preview with the entry removed, "Afterwards r6's IP SLA reads Not in intent again", the decline's commit kept, "Remove the decline from r6's intent" | the same | **same** |
