# Fidelity: History (the Timeline and Baselines tabs)

History as built, compared region by region with its approved boards (C650's step), after the
operator's walk W1 (2026-10-16, steps 6, 12, 40 and 45, the last reading the whole sitting back
from it). Read from shots of the boards and the page side by side, in the same headless Firefox
(`tests/test_board_shots.py::test_history`), fed twice: first the real records of
`tests/test_device_v2.py`'s lab written as `tests/test_device_history_v2.py` writes them (r3's
golden, an intent commit, a failed and a deployed receipt, and the repository's own commits:
shot `history-real`, the same rows as r3's tab in docs/fidelity/tab-history.md); then the
browser layout test's widest timeline (`tests/test_v2_layout_in_a_browser.py`'s `_timeline`: a
denied baseline decision's long words, a nine-device golden marked known wrong, the identity
line counting 52 commits of which 11 are not verified) and its `BASELINES` (one denied and
stale, one earned). Read beside them: the operator's W1 captures 08 (the logging test's row
opened), 11 (r4's and s4's layout rows from the topology drag), 34 and 35 (the sitting's rows,
top and bottom, "Showing the newest 50 of 316"), at about half desktop width.

Boards, on the "NMAS v2 mockups" canvas, page "Coverage (built), templates, stepper, History":
`HistoryTimeline.dc.html` (board D, 1280), History as one timeline (C369), signed off
2026-10-03 and built; `History.dc.html` (1280), the earlier History board (the Commits tab,
signed off 2026-10-02 with NSOT_GUI_BRIEF 3.4), which board D superseded; and
`HistoryIdentity.dc.html` (7.5, 1440), History's identity line in its four states and the
filter it adds, signed off 2026-10-11 under the Phase 7 mode (docs/STANDING_APPROVAL_LOG.md).
The Query tab is compared in its own records: docs/fidelity/history-query.md (board A,
AskLibrary), docs/fidelity/history-metric.md (board B), docs/fidelity/logs.md (board C,
Syslog by device), docs/fidelity/history-ask-logs.md and docs/fidelity/history-ask-metrics.md
(Ask your own); History › Remote set-up is a card drawn and counted as signed off on
2026-10-10 with no board file.
Shots: board D and the earlier board at 1280, the identity board at 1440; the page at 1280,
1440 and 390, its rows closed (`history-rows`) and the newest opened (`history-open`); the
Kind menu open (`history-kinds-menu`, 1280); Show only these (`history-unverified`, 1440,
the fixture's counts unfiltered); the Baselines tab (`history-baselines`, 1280 and 390); the
real records (`history-real`, 1280).
Compared 2026-10-16.
Templates compared: templates/v2/history.html, templates/v2/_history_body.html, templates/v2/_history_remote.html, templates/v2/_history_timeline.html, templates/v2/_timeline.html
Templates sha256: `3430aaeaa23b3f79a8d67a92b5467a6870bab538f714b5c3f01152854ddf6203`

Compared again 2026-10-16 (C522) after `_history_body.html`'s Baselines card gained a heading
row: the count of baselines ("2 baselines") and "How does this work?" in words (to the restore's
page, "Restore and re-apply a baseline"), C503's rule of one worded link per card; each row's
Re-apply… keeps its (i). `history-baselines` shot again at 1280 and 390 (the count and the link
on one row at both). Neither board draws the Baselines
tab's content (board D names the tab; the earlier board's Baseline column was superseded), so the
Baselines region's verdict is unchanged; no other region moved.

Compared again 2026-10-16 (C945) after `_history_remote.html` gained two states of its
uncommitted clause: "No repository yet: the network's first commit makes it." for a network
whose folder has no `.git`, and "The working tree could not be read: <git's error>." for any
other failure (it read "The working tree could not be read." for both). Neither state is on a
board or in a shot: board D draws the remote line in sync and committed. The header rendered
from the template as it was and as it is, in five states (in sync and clean, 7 and 2 paths
uncommitted, no remote and clean, ahead with a failed push): every byte the same. No region's
verdict changed.

Compared again 2026-10-16 (C957) after `_timeline.html` gained one state: a network with no
repository yet draws one muted notice above the rows, "No repository yet: the network's first
commit makes it. Until then the golden history, the intent history, the saves that measured
devices, the repository's other commits and the baseline decisions have nothing to show.", in
place of five warnings that each history "could not be read". The state is on no board or
shot: board D draws a network with a repository. The rows rendered from `timeline_rows` as it
was and as it is, in five states each with and without a device (the layout test's widest
timeline, a device's restart row, errors with a cut list, empty, empty with no repository
key): every byte the same. No region's verdict changed.

Compared again 2026-10-16 (C1016) after `_history_remote.html`'s failed Verify gained each
failed check's remedy: the line "Last verified <when> (<who>): failed:" and under it one item
per failed check, its name and detail and "To fix:" with the check's own remedy (the words the
set-up card's write probe draws), where it was one line of names and details. The state is on
no board or shot: board D draws the remote line in sync, and no shot has a failed Verify. The
header rendered from the template as it was and as it is, in six states (in sync and clean, 7
paths uncommitted, ahead with a failed push, Verify passed read-only, Verify passed with the
write probe, no remote): every byte the same. No region's verdict changed.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | History, after Devices | the same, current | **same** |
| Heading | "History" (the identity board adds the (i) beside it) | "History" and its (i); the network's one line under it ("Default: what happened to the network and its devices, and when", capture 08) | **same** |
| The remote line | "in sync", "Everything is committed and pushed to the remote (checked 1 min ago)"; Push now and Verify the remote at the right | the state's chip and the remote's own sentence (`remote_publication.describe`: "in sync … and pushed to <repo> (checked 1 min ago)" in capture 08), its (i), Remote set-up… and Verify the remote with its (i); Set up the remote… when none is set (the shots); Push now when something is unpushed (the template) | **deviation** (log: Board: History › Remote set-up) |
| Tabs | Timeline, Baselines, Authorisations (D); Timeline, Baselines, Authorisations, Query, Remote (the identity board) | Timeline, Query, Baselines; the remote is the card above | **deviation** (log: History's Authorisations tab left its page with C708 (2026-10-12)) |
| Filters | Device ("Any device, and the fleet"), Person ("Anyone"), Kind, Since; Show on the identity board | the same four and Show (capture 34); every filter in the address, so a view is a link | **same** |
| The Kind menu | "Every kind except 2": the kinds in two columns under The repository, What ran on a device, What happened to a device, Decisions and records, Retries authorised and Freshness authorised off; Every kind · Commits only | one column under the same four headings, every kind by default (none ticked is every kind); the kinds recorded since (Privileged commands, Reloads, Credential profiles, Expected islands, Topology layouts, Saved views, Reveals, Show commands) in their groups, Freshness authorised not a kind; Every kind · Commits only | **deviation** (log: History: the Kind menu) |
| The count | "Showing the newest 12 of 41 · Show more" beside the filters | at the head of the timeline card, "Showing the newest 50 of 316 · Show more" when cut (capture 34), else "N records"; the card's foot says each store read its newest 50 (capture 35) | **same** |
| The identity line (7.5) | "41 of 52 commits in this window carry a verified identity (signed in through the access proxy)", chips 8 host login, 3 not verified, 0 before verification was recorded, Show only these 11 | the same words and chips ("39 of 62 commits … 16 host login, 7 not verified, Show only these 23" in capture 34), a kind with no commit not drawn (no "0 …" chip); Show only these wraps under the line at 1280 | **deviation** (log: History: the identity line draws no empty chip) |
| The identity line's other states | all verified in ok colour; a filter set says what is shown; no commit says so, never "0 of 0"; Show only these with Show every identity | the same four (the template; `history-unverified` shows the last, its counts the fixture's, unfiltered) | **same** |
| Rows | When, Kind, Device, What, Who; one line each | the same five; When as a v2 stamp with the UTC time on hover; a disclosure mark before each row; a long What cut with "…" on its one line (the layout rows, capture 35) | **same** |
| Kind | a chip per kind in words | the board's kinds in words; a kind recorded since and not in the chip table is drawn by its code name, and "show_commands" is cut to "show_comman" by the column (captures 08, 34, 35; C901) | **deviation** (log: History: a kind's chip shows its code name, cut to "show_comman" (C901)) |
| An update's colour | an "update" chip in the kind's own colour; red only for a failure | a successful update ("The app updated to <sha>: updated") is drawn red: `_timeline.html` reads any update outcome but "confirmed", "done" and "ok" as a failure; it was the sitting's only red row (capture 35; C901) | **deviation** (log: History: a successful update drawn red (C901)) |
| What | the record in words, its detail faint after " · " | the same; an intent edit made on v2 reads "Intent committed (extraction)" (C895), a rotation writes "rotated persistence not attempted" before "rotated and persisted" (C896), and a Save All adds a "persist" row per device under its own (C898; captures 34 and 35) | **deviation** (log: History: an intent edit on v2 reads as an extraction (C895)) |
| A decision and a known-wrong record | "decision", "baseline earned" with its tag; "corrected" on a persist | "decision" with the decision's words, its Baseline field in the opened row; " · record known wrong", its note in the opened row | **same** |
| An opened row | under the row at full width: who and how identified, via what, how long; the run's stages; Open r3's History · The commit | the detail and the commit's sha, By the person as identified, the record's fields (Run, Devices, Outcome for the logging test in capture 08), Show the change, Open <device>'s History for each device of several, and on a golden row "A golden is a record of what the device ran …" and Reveal <device>'s version… | **deviation** (log: History: an opened row's links) |
| How a row's person was identified | the identity board's table puts "host login" as a chip after the person in Who | in the opened row ("By … (host login, not verified)"), as the board's note says ("as today, in the expanded row") | **deviation** (log: History: how a row's person was identified) |
| The fleet's own records | rows with no device read "fleet"; a commit is one row naming its devices | the same; but a golden commit that also writes a path outside `golden/` and `host_vars/` (here r3's first, which adopts it into the manifest) is drawn twice, as r3's golden and again as a fleet commit, "golden: 1 device(s) via capture" (`history-real`) | **deviation** (log: History: a device's first golden drawn again as a fleet commit (a defect, register C650 follow-up)) |
| The earlier board (History.dc.html) | a Commits tab; a Workflow filter; a Baseline column; Re-apply this baseline… under a Save All | superseded by board D: Commits a kind (Commits only), Workflow folded into Kind, a baseline decision its own row; Re-apply… on the Baselines tab | **same** |
| Baselines | its own tab (board D: "Baselines and Authorisations keep their tabs") | headed by the count and "How does this work?" (C522); one line per baseline (tag, taken, earned, can be re-applied, Re-apply… with its (i)), why it was denied or withdrawn and what it claims opened under it, "Judged … in the background"; the walk's step 40 re-applied the newest from it | **same** |
| Query | board A's library (compared in docs/fidelity/history-query.md and its sibling records) | the same records | **same** |
| Phone | no phone board | the filters wrap to a second line, the identity chips wrap, each row's cells stack | **same** |
