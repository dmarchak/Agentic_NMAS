# Fidelity: Logs, the live tail (C675)

The sidebar's Logs as built, compared region by region with its board (C650's step). Read from
shots of the board and the page side by side, in the same headless Firefox, the page fed by the
logs-tail reader's value built from real lines of the lab's Loki (`tests/fixtures/loki/`,
`tests/test_board_shots.py::test_logs_tail`; the fixture's lines span several days, because the
test's Loki answers whatever window is asked, so the shot's times are not all inside 15
minutes; on the host they are).

Board: `LogsTail.dc.html` (board D, 1440 wide), on the canvas's "History, Query" page, drawn
2026-10-11 by the agent from the operator's design ("a LIVE TAIL") under the Phase 7 mode and
counted as signed off (docs/STANDING_APPROVAL_LOG.md). The board has no phone variant; the page
at 390 keeps the table whole and scrolls it in its box.
Shots: desktop 1440 (live; arrived from History › Query, filtered; paused); phone 390. Compared
2026-10-11.
Templates compared: templates/v2/logs.html, templates/v2/_logs_tail.html
Templates sha256: `cc865343c9bd0ab9755e745ae0b6432efe8bf7ed67fd4ab7b9101cdd6ce19e44`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | Logs under OBSERVE, current | the same | **same** |
| Heading | "Logs", the network | the same | **same** |
| The live state | "Live · read 2 s ago", Pause, How does this work? | "Live · checked every 5 s · the newest line 21:19:18 UTC" (the read's time on hover), Pause; the manual's link is the title's (i), as on every v2 page | **deviation** (log: The tail says it checks every 5 s) |
| Counts | lines in the last 15 minutes, by severity group, devices | the same, for the whole window whatever the filters | **same** |
| Filters | device, severity, mnemonic, text; Clear filters | the same four, Show to apply them (no script), Clear filters when any is set | **same** |
| Lines | received time, device (a link), severity, mnemonic, message, newest first | the same | **same** |
| A cut list | "The newest 200 of the 230 lines are drawn; filter to narrow them" | the same, and "N of M lines match" when filtered; more than the window keeps (1000) said | **same** |
| Older | "Older than 15 minutes: History › Query › Syslog by device, with the filters you set here" | the same | **same** |
| Arrived from History › Query | "Filtered as you came: device s3, error or worse, text Gi0/3. Clear filters to see every line." | "Filtered as you came from History › Query: device s3, error or worse (0 to 3), text Gi0/3. Clear filters to see every line.", the filters set | **same** |
| Paused | "Paused at 18:20:12 · 37 new lines since", Resume | the same; the window held at that second, the count still moving | **same** |
| The log store cannot be asked | "Loki did not answer at 18:20:17 (connection refused). Showing the lines read at 18:20:12; asked again in 5 s" | "The log store did not answer at 18:20:17 UTC (connection refused). Showing the lines read at 18:20:12; asked again every 5 seconds", the last good window drawn; never read, not configured and an unreadable store each their own words | **same** |
