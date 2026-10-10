# Fidelity: Logs (C652)

The Logs view as built, compared region by region with its signed-off board (C650's step; the
operator, 2026-10-10: the sidebar's Logs opens "the queryable logs as approved on the canvas mock
up"). Read from shots of the board and the page side by side, in the same headless Firefox, the
page fed by the logs reader's value built from the real captures of the lab's Loki
(`tests/test_board_shots.py::test_logs`).

Boards: `AskLogs.dc.html` (History › Query board C, "Syslog by device", 1440 wide), signed off with History › Query A and B on canvas v31 (NSOT_STAGE7_PLAN 15.5 to 15.9). The board has no phone variant.
Shots: desktop 1440 (120 days, every severity, r4 opened); phone 390 (the page held to a 390 px column, and its first screen). Compared 2026-10-10.
Compared again 2026-10-10 after the host walk: Newest follows the severity asked (the exact time when seen, else the last day counted, the board's "09:41 today" and "2 Oct"); no region's verdict changed.
Templates compared: templates/v2/logs.html, templates/v2/_logs_view.html
Templates sha256: `2799ce937936d0bcfa9f613d4f41e27d14b7c94e747f4251b534987bd4427b50`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Where it sits | History › Query tabs (Timeline, Query, Baselines, Authorisations), breadcrumb "Query › Syslog by device" | the sidebar's Logs; breadcrumb "Logs › Syslog by device · the network" | **deviation** (log: Logs opens the queryable logs) |
| Title and actions | "Syslog by device"; Copy the link; Save this view…; How does this work? | "Syslog by device" with its info link; Copy the link | **deviation** (log: Logs without saved views) |
| Range | 24 h, 7 d, 30 d, 120 d | the same four | **same** |
| Severity | in the opened device's filters | the same, and beside the range for the table | **deviation** (log: Logs' severity beside the range) |
| Coverage notice | "Part of this range holds nothing yet: … keeps logs 2 years (its Logs retention setting, Settings), but its log store began on 7 Sep, so the first 93 days … never kept; nothing to show is not nothing happened" | the same words from the setting and the store's first day; also days still being counted, and Loki holding more than the setting says | **same** |
| The one-window note | "The 27 days since were asked in one window (one log query spans at most 30 days 1 hour)" | "Counted per day by Mercury's logs reader … a device's lines are asked from Loki when it is opened, at most 30 days at a time" | **deviation** (log: Logs counts per day in a reader) |
| Headline | "142 lines at error or worse, 4 devices · a row opens its lines" | the same, for the range and severity asked | **same** |
| Device table | Device (a button opening it), Lines, Newest, Most frequent (with the interface: "%LINK-3-UPDOWN Gi0/3 (61)") | Device, Lines, Newest, Most frequent by mnemonic ("%DBAL-4-DELAYED_BATCH (1826)") | **deviation** (log: Logs counts by mnemonic) |
| Opened device's filters | Severity, Mnemonic (with counts), From, To, Text contains | the same five, and Show | **same** |
| Trend | "Trend by mnemonic, lines per day": two series, y and x ticks, a key with "y: lines per day · x: date (UTC)" | the same, up to three series, from the first day counted | **same** |
| Lines | Received (UTC), Severity chip, Mnemonic, Message; newest first | the same, masked | **same** |
| Lines' foot | "Showing 3 of 61 matching lines · the next 50 · Open these lines on Logs" | "Showing 50 of 2295 matching lines … · the next 50 · Open r4's Logs tab" | **deviation** (log: Logs opens a device's own Logs tab) |
| Footnote | "A line's time is when the collector received it, never the device's clock. The heartbeat lines are left out." | the same | **same** |
| Phone | no board | each device a wrapped row, each line its time and severity over its message | **deviation** (log: Logs at phone width) |
