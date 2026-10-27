# Fidelity: Monitoring › Alerts › History, past alerts and Build evidence (2026-10-26)

Board: `AlertsHistory.dc.html` (board P1-H, the alert history, the operator's order of
2026-10-26, item 4). It was drawn 2026-10-26 in the agent's copy of the mockups canvas's
project folder, to be published to the canvas "NMAS v2 mockups" on the page "P1, Monitoring ›
Alerts", and signed off under the Phase 7 mode (docs/STANDING_APPROVAL_LOG.md).

Shots: `tests/test_board_shots.py::test_monitoring_alerts_history` (`alerts-history-tab`,
`-open` and `-built` at 1440, 1280 and 390, beside `alerts-history-board` at 1440). They run on
test_device_v2's lab with tests/test_evidence_pack.py's inventory (r1, r2, r3). The data is the
captured state history of 21 Oct, 01:00 to 03:00 UTC (tests/fixtures/grafana/alert_history/),
backfilled by the real recorder and shown with **All** over all the history kept. The heartbeat
group is opened on r2's past alert, and Build evidence is pressed: its rebuilt pack is drawn over
the Loki and Prometheus captures. At 1280 and 390 the pack built at 1440 is kept, frozen, so the
row opens on the pack and not on Build evidence. The Loki capture is answered whatever the
window, so the shot's log lines are 15 Oct's, not 21 Oct's.
Templates compared: templates/v2/_alert_history.html, templates/v2/_evidence_pack.html, templates/v2/monitoring.html, templates/v2/_explain_block.html
Templates sha256: `7a8a6c425fc46ce1bde970bbd331f86f98e18ab6526c4dc75e92a9aeff22fe11`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Heading and tabs | "Monitoring · Alerts", the (i), its line, Dashboards, Coverage, Profile, Alerts (on) | the same, the line naming both views | **same** |
| Firing and History | a two-way switch, "Firing · 2" and "History" (on) | the same switch, History on; Firing carries its count only on the Firing view | **deviation** (log: P1-H: Firing's count on History) |
| The summary | "142 alerts fired and resolved in the last 7 days · 9 devices · 12 with an evidence pack" | the same words, from the range chosen ("in all the history kept"), and "in the N shown" under All | **same** |
| Counts by outcome | four chips: fired and resolved, pending never fired, read no data, could not evaluate | the same four, the same colours | **same** |
| Where it came from | the reader's start, Grafana's state history's oldest, "times are Grafana's" | "Transitions as Grafana timed them, never a device's clock: 93 kept, the oldest from 6 d ago" (the reader's start when it has recorded one; the moved count once retention moved any) | **same** |
| The filter | search, every rule, device, last 7 days, Fired or All, Show | the same six, in a row at 1440 and 1280, wrapping at 390 | **same** |
| Groups | each rule a closed card: its name, its count resolved, its devices | the same; "ended" in place of "resolved" under All, which includes alerts that never fired | **same** |
| A row | device, fired and resolved (duration), onset, the pack chip, the labels | device and network, fired (or began) and resolved (duration), an outcome chip when it did not fire, the pack chip, the labels; the onset is in its pack | **deviation** (log: P1-H: the row's onset in the pack) |
| A row with no pack | the notice, Build evidence, "How does this work?", the AI mark and Explain disabled with "build it first" | the same, the notice in plain words under the states line | **same** |
| The states it passed through | not drawn | the row's body opens on each state Grafana named, with its time | **deviation** (log: P1-H: a past alert's states listed) |
| Build evidence pressed | busy on itself; the rebuilt pack replaces the row's body | the same ("Building the evidence…"; the pack drawn in the row's body) | **same** |
| The rebuilt pack | its own card: title, "rebuilt afterwards", built when, as of when, by whom, hash; Explain on the right | the pack line in the row: "rebuilt afterwards", built, as of then, the trigger naming who and when, resolved, hash; Explain under it | **deviation** (log: P1-H: the rebuilt pack in its row) |
| Each section's mark | captured (quiet), rebuilt (chip, from what), cannot be rebuilt (chip, why) | the same, the words in full under the heading; the Intent check's commit named | **same** |
| The sections folded | each a closed disclosure | drawn open, as the Firing pack's are | **later** C1769 (the sections folded) |
| AI off | Explain disabled, the reason and the AI card's link | the same, on the row and in the pack | **same** |
| Nothing in range; unreadable | "No alert fired and resolved…" with counts; a danger notice naming why | compared by the template and tests/test_alert_history_packs.py (`test_an_unreadable_history_is_said_never_a_quiet_list`), not shot | **same** |
| The group's cap | "the newest 100 of a group are drawn: filter above" | the same words, at the group's foot | **same** |
| Phone | not drawn | at 390 the filter wraps, rows and the pack stack; no sideways scroll | **same** |

**Compared again 2026-10-27 (C1849 to C1851, pack schema 5):** `_evidence_pack.html`, which this
record compares for the rebuilt pack drawn in its row, gained the other alerts section and the
health line's "network model as it is now" words; the regions above are unchanged, the pack's
own regions compared in docs/fidelity/alerts-explain.md ("Compared again 2026-10-27"), its
deviation logged there. Shot by `tests/test_board_shots.py::test_monitoring_alerts_history` at
1440, 1280 and 390: the rebuilt pack in r2's row draws both, and stacks at 390.

Templates sha256 before: `884ffcabec64bcb6ea029b2f008a329b7e9cfae2749988ba450f708e05f96e38`.

**Compared again 2026-10-27 (C1862, Build again):** `_evidence_pack.html`, drawn in a row's
body, offers Build again on a pack of an older schema and names the other pack of the same
alert (the regions are described in docs/fidelity/alerts-explain.md, "Compared again
2026-10-27 (C1862 ...)"); `_alert_history.html`'s pack chip names the pack's schema and when it
was built on hover.
- **Shots:** `tests/test_board_shots.py::test_monitoring_alerts_history_rebuild` (2026-10-27
  02:45 UTC, the list's redraw after the press waited for; `alerts-history-rebuild-older`, `-offered`, `-rebuilt` and `-kept` at 1440, 1280
  and 390, beside `alerts-history-rebuild-board` at 1440), on this record's lab with r2's past
  alert keeping a pack of schema 4. Offered: the row opens on the schema-4 pack, "Kept with
  schema 4; this release builds schema 5. It holds no other alerts around the onset, ..." then
  Build again, its (i) and its words, above Explain. Rebuilt: the pack built again in place,
  "built again from the alert history by test-person@example.invalid ... in place of pack
  ep-… (schema 4), which stays kept", "Built again from pack ep-… (schema 4, built just now),
  which stays kept" and Show it, and the other alerts section second. Kept: Show it draws the
  schema-4 pack again, "built again" and "Built again as pack ep-…-s5 (schema 5 ...)", no other
  alerts section. At 390 each stacks, no sideways scroll. `::test_monitoring_alerts_history`
  shot again at the same time: unchanged but the chip's hover.
- **Verdict:** **deviation** for the two new regions (the board draws no pack of an older
  schema and no second pack of one alert); their lines are in docs/STANDING_APPROVAL_LOG.md
  ("P1 Alerts and P1-H: Build again on a pack of an older schema", "P1 Alerts and P1-H: the two
  packs of one alert"). No other region's verdict changed.

Templates sha256 before: `b7fba315b8648fb0ecde6d529dd9b76ee31a43b7f5fc37cdab68f2dca52717e9`.

**Compared again 2026-10-27 (C1852 and C1853, the operator's Walk 2):** the list is no longer
redrawn under a person. While a row whose pack was loaded is open, or while Build evidence,
Build again or Explain is being answered, the alerts reader's redraw waits. The open row says
so under its summary, with **Show it now**; beside an action in flight, the row says the newer
data shows when the action answers. The pack's Explain moved into `_explain_block.html`
(compared in docs/fidelity/alerts-explain.md), so this record compares it too.
- **Shots:** `tests/test_board_shots.py::test_monitoring_alerts_history_rebuild` (2026-10-27
  05:03 UTC, at 1440, 1280 and 390 beside `alerts-history-rebuild-board` at 1440). Build
  again's response names `alerts`, so the list is asked again. The shot `-rebuilt` is taken
  once that redraw has been held. Under r2's summary, "Paused while you work: newer data is
  waiting." stands on one line with Show it now, an outline button, at its right; the pack
  built again sits below it in place. At 390 the words wrap and the button goes under them,
  with no sideways scroll. `::test_monitoring_alerts_history` was shot again at the same time,
  with its regions unchanged.

| Region | Board | Built | Verdict |
|---|---|---|---|
| The list paused while a row is open | not drawn (the board draws no redraw) | "Paused while you work: newer data is waiting." under the open row's summary, with Show it now (the newer list at once, the open rows opened again and their packs loaded again); closing the rows draws the newer list by itself | **deviation** (log: P1-H: the list paused while you work) |
| The list waiting on an action | not drawn | "Newer data is waiting; it shows when this answers." beside Build evidence, Build again or Explain while it is busy on itself; compared by tests/test_explain_kept.py's `test_a_refresh_mid_explain_keeps_the_row_and_the_answer_lands` in Firefox, not shot (it lasts only while the call is in flight) | **deviation** (log: P1-H: the list paused while you work) |

Templates sha256 before: `a925cd86203963b4018366e10c65bb932ad196e7d81abe616a267ad9a07caef8`
(over the three templates compared before `_explain_block.html` was added).
