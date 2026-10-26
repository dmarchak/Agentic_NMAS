# Fidelity: the device page's History tab

The History tab as built, compared region by region with its approved board (C650's step), after
the operator's walk W1 (2026-10-16, steps 4 and 7, on s1 and s2). Read from shots of the board
and the page side by side, in the same headless Firefox, on `tests/test_device_v2.py`'s lab with
r3's records written by the real paths as `tests/test_device_history_v2.py` writes them: its
golden (r2's real configuration, Source: capture), an intent commit (the extraction), a failed
deploy receipt and a deployed one (`tests/test_board_shots.py::test_tab_history`). The same
records drawn on the History page are `history-real` in docs/fidelity/history.md, so the two are
compared on one set of rows. Read beside them: the operator's W1 capture 05 (s1's tab with the
walk's two reads at its top, among the fleet's measured, persist, intent, golden, receipt and
break-glass rows of the days before), at about half desktop width.

Boards: `HistoryTimeline.dc.html` (board D, 1280) on the "NMAS v2 mockups" canvas, page
"Coverage (built), templates, stepper, History", signed off 2026-10-03 and built (C369):
History as one timeline, "a device's History tab is this timeline filtered to the device: the
same reader, the same rows, the same drawing". The board draws the History page; this tab is
its rows. Before it: NSOT_STAGE7_PLAN 1g, step (a).
Shots: the board at 1280; the tab at 1280, 1440 and 390, its rows closed (`tab-history-rows`)
and the newest opened (`tab-history-open`).
Compared 2026-10-16.
Templates compared: templates/v2/_history.html, templates/v2/_timeline.html
Templates sha256: `7328da4f83c4c0e398c04f9df2ed1b076511aee627b6828f65fcd7847f861286`

Compared again 2026-10-16 (C957) after `_timeline.html` gained one state: on a network with no
repository yet, the tab draws one muted notice above the rows, "No repository yet: the
network's first commit makes it. Until then the golden history, the intent history and the
saves that measured devices have nothing to show.", in place of three warnings that each
"could not be read". The state is on no board or shot. The rows rendered from `timeline_rows`
as it was and as it is, in five states each with and without a device: every byte the same.
No region's verdict changed.

Compared again 2026-10-17 (B8, W2) after `_timeline.html` gained the NetBox kind: "NetBox" in
words, a failed or partial row in danger. The NetBox source is the network's own record, so no
device's tab draws a NetBox row (`history_sources.netbox` reads nothing for a device). The rows
rendered from `timeline_rows` as they were and as they are, for 648 rows (every kind drawn
before, each with eight outcomes and three marks, half with a device): every byte the same.
No region's verdict changed.
Templates sha256 before: `db142f8ca85199c4ea2711c17bbd123ae0f2abceb54ff78158b9d7e4fb3a434e`.

Compared again 2026-10-17 (C1089) after `_timeline.html` gained the Grafana kind: "Grafana" in
words, a refused write in danger. Mercury's Grafana writes are the network's or the
installation's record, so no device's tab draws one (`history_sources.grafana_writes` reads
nothing for a device). The rows rendered from `timeline_rows` as they were and as they are, for
672 rows (every kind drawn before, NetBox among them, each with eight outcomes and three marks,
half with a device): every byte the same. No region's verdict changed.

Compared again 2026-10-18 (the operator's walk of 2026-10-18, B: r2's tab showed the newest 30
of 162 rows, and its last golden, 6 days old, sat behind daily Save All rows; the tab replaced
today's golden-history panel, which P7-27 removed) after `_history.html` gained, under the tab's
(i) and its link to the History page, the Kind choices one click away: a segmented row, All,
Goldens, Intent, Deploys and restores, Measured, unchanged, Restarts, each a link to the device
page's address (`?tab=history&kind=golden`, the page's network kept), the chosen one pressed. The
reader keeps the kind before its newest-30 cut, so every golden of the device is reached under
Goldens. The live redraw, the link to the History page and Show more carry the kind; a kind with
no record says "No record of the kind chosen (Restarts) for r3" with Every kind; a kind not known
is not applied and said by name above the rows. None of it is on a board. The tab rendered on
test_device_v2's lab from the template as it was and as it is (r3's, r9's with nothing recorded,
the fragment and the whole page): the rows every byte the same, the Kind row the only addition.
No shot was retaken: Firefox could not start in the runner where this was compared
(tests/test_v2_layout_in_a_browser.py skipped), so the row's wrap at phone width is the
stylesheet's, not measured. One region added, The Kind choices; Nothing's Built amended; no
other region's verdict changed.
Templates sha256 before: `f31a10073c4d25bda457f183ae439b3ae1f1860d9a8b290e25bda3504ff17756`.

**Compared again 2026-10-26 (PHASE8_PLAN 15.14):** `_timeline.html`, which this tab draws as
History does, gained an AI call's "Show the prompt and the answer" and its window, the kind in
words ("AI call"), and danger for a call that failed or whose answer its feature refused.
docs/fidelity/history.md's comparison of the same date holds the detail and the width defect
the first shot found and fixed.
- The tab shows the calls whose subject names the device (`history_sources.ai_calls`), with
  no "Open r1's History" link, since the tab is r1's own.
- Shot `tab-history-ai-call` at 1280 (r1's tab, the call opened and pressed): 1,268 px wide,
  the window inside the row.

Rows without a call render as before, but for the separator after a row's last device link.
Templates sha256 before: `e7d401c1a170eb7175b634fd212b32b48daa3281ac70e612c4c96179b585b80c`.

**Compared again 2026-10-26 (15.14 part B: paging for History and a device's History tab
alike):** the tab draws 50 rows (30 before), and both templates changed.
- `_timeline.html` as on History (docs/fidelity/history.md's comparison of the same date):
  each row's id, Load more at the foot of the rows, "No older record than these.", a store
  read only by its newest rows that a page could not reach named under them, Open what it
  produced on an AI call.
- `_history.html`: under the Kind choices, **Jump to** (a date field) and **Go**, a form to
  the device page's own address keeping the kind (`on=`); Load more's fragment is
  `/v2/device/<name>/history/more` and the address it pushes the device page's
  (`?tab=history&before=<time>~<id>`); at a place, "Showing the 50 before <stamp>" with Back
  to the newest; "Showing the newest 50 of N read · Load more, at the foot, reads the next 50"
  replaces "Showing the newest N of M · Show more on the History page", since the tab now
  reads further back itself. Its redraw keeps the place.

Board D draws "Showing the newest 12 of 41 · Show more" beside the filters and no date control.
No board shot was retaken (the canvas's copy was not to hand); the tab's Load more was
requested as a person's click would (tests/test_history_paging.py, `TestTheDeviceTab`: the next
50 drawn, the pushed address opening at the same place), and the browser row-overflow check
passed on `/v2/device/r2?tab=history` at its widths. "Show more" amended and a region added,
Jump to; no other region's verdict changed.
Templates sha256 before: `2934e519314ab53e8176939aaa571d6213519f0fb52d0cac0e41f1b17ebb0da2`.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| One reader, two entry points | the tab is the page's timeline filtered to the device | the same reader (`device_page.history` calls `history_sources.timeline` with the device) and the same macro (`_timeline.html`'s `timeline_rows`); the tab's (i) and "The fleet's timeline, filtered to s1" above the rows (capture 05) | **same** |
| Columns | When, Kind, Device, What, Who | the same five, a disclosure mark before each row | **same** |
| When | "03 Oct 10:52" | a v2 stamp ("1 min ago", "20 h ago"), the UTC time on hover | **same** |
| Kind | a chip per kind in words (golden, rotation, persist, restart, window, decision, update, acknowledged, commit, break-glass) | the same chips and colours for the kinds the board drew; a kind recorded since and not in the chip table is drawn by its code name, and "show_commands" is cut to "show_comman" by the column (capture 05; C901); a failed or stopped record drawn danger whatever its kind | **deviation** (log: History: a kind's chip shows its code name, cut to "show_comman" (C901)) |
| An update's colour | an "update" chip in the kind's own colour; red only for a failure | an "update" row is drawn danger whenever its outcome is not "confirmed", "done" or "ok", so a successful update ("updated") is red, the only red row of the walk (`_timeline.html`'s `failed` test; the operator's W1 capture 35; C901) | **deviation** (log: History: a successful update drawn red (C901)) |
| Device | the record's device, "fleet" for none, "r1–r4" for several | the device; a record of several says how many ("9 devices", capture 05) | **same** |
| What | the record in words, its detail faint after " · " | the record in words, its marks faint after " · ", its detail in the opened row; an intent edit made on v2 reads "Intent committed (extraction)", the extraction's words, not the edit's (C895) | **deviation** (log: History: an intent edit on v2 reads as an extraction (C895)) |
| Who | the person, shortened | the person; how they were identified only in the opened row | **same** |
| An opened row | under the row at full width: "By operator@example.com, verified by Access · via the device page · 58 s"; the run's stages; Open r3's History · The commit | under the row at full width: the detail and the commit's sha, "By" the person as identified, the record's fields (Program, Commit), Show the change; on a golden row the sentence "A golden is a record of what the device ran when it was captured, not a target" and Reveal r3's version…; other devices' History links on a record of several; on an AI call whose subject names the device (15.14), the call's record and Show the prompt and the answer, its window as on History (`tab-history-ai-call`) | **deviation** (log: History: an opened row's links) |
| The fleet's rows | choosing a device keeps its rows and drops the fleet's | none on the tab: the fleet's own commits are read only without a device (`history_sources.fleet_commits`); records of several devices that include this one stay (the Save All's "measured" and the break-glass rows in capture 05) | **same** |
| Show more | "Showing the newest 12 of 41 · Show more" | "Showing the newest 50 of N read · Load more, at the foot, reads the next 50" above the rows, and Load more under the last, appending the next 50 in place and pushing the device page's address with the place; at a place, "Showing the 50 before <stamp>" with Back to the newest (15.14 part B; tests/test_device_history_v2.py's `test_a_cut_timeline_says_where`, tests/test_history_paging.py) | **deviation** (log: History: Load more by keyset and jump to date (15.14 part B)) |
| Jump to (15.14 part B) | not drawn | under the Kind choices, a date field and Go: the tab from the end of that day, UTC, the kind kept (`on=`); a day with nothing on or before it says "Nothing is recorded for r3 on or before <day>" with Back to the newest | **deviation** (log: History: Load more by keyset and jump to date (15.14 part B)) |
| The Kind choices | none: the tab is the timeline's rows, filtered to the device only | under the tab's (i), one segmented row of links: All, Goldens, Intent, Deploys and restores, Measured, unchanged, Restarts, each the device page's address with its `kind`, the chosen one pressed; kept by the reader before its newest-50 cut (30 until 15.14 part B), carried by the live redraw, the link to the History page, Load more and Jump to (the operator's walk, 2026-10-18, B; tests/test_history_kind_filter.py) | **deviation** (log: History tab: Kind choices one click away, Goldens first, the operator's walk of 2026-10-18) |
| Nothing, or a store unreadable | not drawn | "Nothing is recorded for r3 yet: no golden, no intent commit, no deploy"; under a kind with none, "No record of the kind chosen (Restarts) for r3" and Every kind; a kind not known is a notice above the rows, "Not applied: …"; a store that cannot be read is a notice above the rows (tests/test_device_history_v2.py, tests/test_history_kind_filter.py) | **same** |
| Phone | no phone board | each row's cells stacked in the row, the opened detail under them | **same** |
