# Fidelity: Logs (C652)

The Logs view as built, compared region by region with its signed-off board (C650's step; the
operator, 2026-10-10: the sidebar's Logs opens "the queryable logs as approved on the canvas mock
up"). Read from shots of the board and the page side by side, in the same headless Firefox, the
page fed by the logs reader's value built from the real captures of the lab's Loki
(`tests/test_board_shots.py::test_logs`).

Boards: `AskLogs.dc.html` (History › Query board C, "Syslog by device", 1440 wide), signed off with History › Query A and B on canvas v31 (NSOT_STAGE7_PLAN 15.5 to 15.9). The board has no phone variant.
Shots: desktop 1440 (120 days, every severity, r4 opened); phone 390 (the page held to a 390 px column, and its first screen). Compared 2026-10-10.
Compared again 2026-10-10 after the host walk: Newest follows the severity asked (the exact time when seen, else the last day counted, the board's "09:41 today" and "2 Oct"); no region's verdict changed.
Compared again 2026-10-11 after C667 moved the view to its board's home, History › Query (`/v2/history/query/syslog`; the sidebar's Logs draws the same page): History's heading, its four tabs with Query on, and the crumb "Query › Syslog by device" now as the board draws them; the shots at 1440 and 390 again; no other region's verdict changed.
Compared again 2026-10-11 (C675): the sidebar's Logs became the live tail (board D, its own record, docs/fidelity/logs-tail.md); this page is History › Query's alone, its template renamed `history_syslog.html`, and the drill-down's footer gains the board's "Open these lines on Logs", which opens the tail filtered; the title's (i) opens the manual's Syslog by device section (nothing drawn moved). No other region's verdict changed.
Compared again 2026-10-11 (C667's saved views): "Save this view…" beside Copy the link, as the board draws it; the title-and-actions row now the same. No other region's verdict changed.
Templates compared: templates/v2/history_syslog.html, templates/v2/_logs_view.html, templates/v2/_history_body.html
Compared again 2026-10-11 (7.5's identity line): `_history_body.html` gained the line under the timeline tab's filters, a branch the syslog view never draws; nothing on this board's page moved.
Compared again 2026-10-12 (C708): History's Authorisations tab left the shared `_history_body.html`; its branch drew only at `?tab=authorisations`, so nothing this board draws moved.
Compared again 2026-10-15 (board F3): `_history_body.html` gained the logs builder's branch, drawn only on its own page (`/v2/history/query/ask/logs`); the shots at 1440 and 390 retaken; nothing on this board's page moved.
Compared again 2026-10-15 (board E3): `_history_body.html` gained the metrics builder's branch, drawn only on its own page (`/v2/history/query/ask/metrics`); the shots at 1440 and 390 retaken; nothing on this board's page moved.
Templates sha256: `fa40e91b832453170ff5d22d740e80d54939fcf820cba3e1812894ebf63e0672`

Compared again 2026-10-15 (P7-03): `_history_body.html` gained a `data-concept` marker and one
sentence ("It claims: …") inside a Baselines row's detail, the block drawing each baseline's
Re-apply… link; this record compares History › Query's syslog view, where Baselines is only a tab
name (unchanged). No region here changed; the hash written again.

Compared again 2026-10-16 (C522): `_history_body.html`'s Baselines card gained a heading row (the
count of baselines and "How does this work?" in words, C503's rule), inside the Baselines tab's
branch, which this record's syslog view never draws; the History shots retaken
(tests/test_board_shots.py). No region here changed; the hash written again.

Compared again 2026-10-18 (the operator's walk of 2026-10-18, B): `_history_body.html` gained
the Kind choices one click away (All, Goldens, Intent, Deploys and restores, Measured,
unchanged, Restarts) under the Timeline tab's filters, inside the Timeline tab's branch, which
this record's syslog view never draws. The page rendered on test_device_v2's lab from the
templates as they were and as they are: every byte the same. No region here changed; the hash
written again. Templates sha256 before: `a5a617a0a1ec0a6eb699ae4933514f151891627437bb2bfef6aabd469ff0bc92`.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Where it sits | History › Query tabs (Timeline, Query, Baselines, Authorisations), breadcrumb "Query › Syslog by device" | History, its Query tab on, breadcrumb "Query › Syslog by device · the network" (C667; the sidebar's Logs draws the same page) | **same** |
| Title and actions | "Syslog by device"; Copy the link; Save this view…; How does this work? | "Syslog by device" with its info link; Copy the link; Save this view… (since C667's saved views, 2026-10-11) | **same** |
| Range | 24 h, 7 d, 30 d, 120 d | the same four | **same** |
| Severity | in the opened device's filters | the same, and beside the range for the table | **deviation** (log: Logs' severity beside the range) |
| Coverage notice | "Part of this range holds nothing yet: … keeps logs 2 years (its Logs retention setting, Settings), but its log store began on 7 Sep, so the first 93 days … never kept; nothing to show is not nothing happened" | the same words from the setting and the store's first day; also days still being counted, and Loki holding more than the setting says | **same** |
| The one-window note | "The 27 days since were asked in one window (one log query spans at most 30 days 1 hour)" | "Counted per day by Mercury's logs reader … a device's lines are asked from Loki when it is opened, at most 30 days at a time" | **deviation** (log: Logs counts per day in a reader) |
| Headline | "142 lines at error or worse, 4 devices · a row opens its lines" | the same, for the range and severity asked | **same** |
| Device table | Device (a button opening it), Lines, Newest, Most frequent (with the interface: "%LINK-3-UPDOWN Gi0/3 (61)") | Device, Lines, Newest, Most frequent by mnemonic ("%DBAL-4-DELAYED_BATCH (1826)") | **deviation** (log: Logs counts by mnemonic) |
| Opened device's filters | Severity, Mnemonic (with counts), From, To, Text contains | the same five, and Show | **same** |
| Trend | "Trend by mnemonic, lines per day": two series, y and x ticks, a key with "y: lines per day · x: date (UTC)" | the same, up to three series, from the first day counted | **same** |
| Lines | Received (UTC), Severity chip, Mnemonic, Message; newest first | the same, masked | **same** |
| Lines' foot | "Showing 3 of 61 matching lines · the next 50 · Open these lines on Logs" | "Showing 50 of 2295 matching lines … · the next 50 · Open r4's Logs tab · Open these lines on Logs" (the last opening the live tail filtered, since C675) | **same** |
| Footnote | "A line's time is when the collector received it, never the device's clock. The heartbeat lines are left out." | the same | **same** |
| Phone | no board | each device a wrapped row, each line its time and severity over its message | **deviation** (log: Logs at phone width) |
