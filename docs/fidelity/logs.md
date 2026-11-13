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
Templates compared: templates/v2/history_syslog.html, templates/v2/_logs_view.html, templates/v2/_history_body.html, templates/v2/_logs_older.html
Compared again 2026-10-11 (7.5's identity line): `_history_body.html` gained the line under the timeline tab's filters, a branch the syslog view never draws; nothing on this board's page moved.
Compared again 2026-10-12 (C708): History's Authorisations tab left the shared `_history_body.html`; its branch drew only at `?tab=authorisations`, so nothing this board draws moved.
Compared again 2026-10-15 (board F3): `_history_body.html` gained the logs builder's branch, drawn only on its own page (`/v2/history/query/ask/logs`); the shots at 1440 and 390 retaken; nothing on this board's page moved.
Compared again 2026-10-15 (board E3): `_history_body.html` gained the metrics builder's branch, drawn only on its own page (`/v2/history/query/ask/metrics`); the shots at 1440 and 390 retaken; nothing on this board's page moved.
Compared again 2026-11-13 (C3290, the words Python builds): `_logs_older.html`'s line time is `_macros.clock`'s (`date-seconds`), in the viewer's kept zone with its UTC instant on hover, where it drew the stored UTC text with no zone named, as `_logs_view.html`'s lines already did; the message cell in both is marked `data-verbatim` (the device's line as sent, its own clock's "UTC" kept). No element moves and no region's verdict moved; compared by the templates' diff and the walk's render (tests/test_no_utc_drawn.py), not by new shots; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times: the words Python builds"). Templates sha256 before: `019be9d19542bd4c3d62104fe59e297686f393ff9c31fe6a452d3533d63b634b`.
Hashed again 2026-11-13 (C3466, Jump to's day is the viewer's): `_history_body.html`'s Jump to field, drawn on the Timeline tab alone (`tab == 'timeline'`), has its accessible name without "(UTC)"; no line this page draws changed. Compared by the template's diff, not by new shots; the Timeline's own record: history.md. Templates sha256 before: `10427bbcdece680ec2a97aa9d248f497c65c1396a8d6b316689fb7007605fbcf`.
Templates sha256: `ebf0df709f02d74abb7c1c02e6d02214f766fd0796c4974af0540cc2188e811a`
(2026-11-12, the two comparisons below merged: the tail slice's stale line and local times'
clock in the same `_logs_view.html` line pair, each kept; their own hashes were
`e82b7456ce24c06e6e712faabf681e0424e15c73f85b7e574c283c0001349b10` (the tail slice) and
`879e13f725ae802059f87228dc55fe5ebbf1bc0db49d2ce8bc5b0692087ba8e7` (local times).)
(2026-11-12, C3330, by the template diff and the pages tests/test_logs_held_stale.py draws, not
a new shot: once the logs-tail reader's last good read is older than its promise (its interval
times its stale factor, 15 s, as its job-health row judges it), an opened device's lines gain a
warning notice under their foot, "Held lines are <age> old: the logs reader has stopped (<its
last error>)", the foot drops "held by the logs reader, read <age>", and the failed-refresh
notice above the lines is not drawn then (each fact once); a fresh buffer draws as before. The
board draws no stale state: **deviation** (log: The Logs pages say when the held lines are past
the reader's promise). Every other region as compared. Before:
`6fea2a28da645e3f5d5fceaadf2db0a6f0c1622cd15f787a61df231427772d15`.)

**Compared again 2026-11-12 (local times, docs/UI_RULES.md "One time zone per screen"):** in `_logs_view.html`, each line's received time and the no-match line's window are `_macros.clock`'s: the viewer's own date and time, the zone named once on the screen, the UTC instant on hover; the lines' column reads "Received" without its "(UTC)"; the chart's day axis, built in Python, stays UTC days (C3290). Compared by the template's diff, not a new shot; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times"). Templates sha256 before: `6fea2a28da645e3f5d5fceaadf2db0a6f0c1622cd15f787a61df231427772d15`.
(2026-11-12, C3166 slice 2, by the template diff against the regions below and the pages
tests/test_logs_buffer.py draws, not a new shot: an opened device's lines are those the
logs-tail reader holds, drawn at once, with its read time in the lines' foot ("held by the logs
reader, read <age>") and a failed refresh's notice above them; a range reaching before them
gains one more body in the lines' table, "Loading older lines: those before <time>, older than
the logs reader holds, from Loki", which `_logs_older.html` (now compared here) replaces in
place with those lines, when Loki was asked for them and "the next 50"; the one-window note says a device's lines are the
reader's last 24 h and older ones asked once the view has drawn. The board draws no read time,
no loading row: **deviation** (log: The Logs pages draw the logs-tail reader's buffer). Every
other region as compared. Before: `525374eae31677bfc480c89199b4e6bb9a28b3b8460ba70d50f8248ec0f6b01d`.)
(2026-11-10, Lab 9 B5: `_history_body.html`'s tabs gain Export, its body drawn only on its own
tab (docs/fidelity/history-export.md); nothing else on this page moved. Before:
`a1c0c8448fc3c0adf67b4df0c828bc19f516a9b7a639bcee835fea73966dbbe0`.)
(2026-11-08 ~20:5x UTC, C2810: each device row of `_logs_view.html` and its opened lines' row
carry `data-key`, their stable keys, which the live merge matches rows by; nothing drawn moves.
Hashed again by reading the diff, with no new shot. Before:
`b8de5798017a759672219f70bf99452f0675922d4eb0bc55185be56b2298d108`.)
(2026-11-04, board H, H6: `_history_body.html`'s identity line counts a commit made under a
confirmed policy under its own words; nothing on this page moved. Before: `faa38c11db29e16fa3171d08c115f59ab48294e15a0c11facf78437799eaf2be`.)
(2026-11-02, C2268: `_history_body.html` draws a hidden answer slot under History's remote
header, where Verify and Push say their answer; nothing on this page moved. Before:
`4c2281d4d47ec4208b53b0b0c9d200ca9ce30cc4fa3a5b1048cac9bcca403b10`.)

Compared again 2026-11-01 (the overnight brief, item 6), by the template: `_history_body.html`'s identity line is not drawn when the kinds chosen show no commit ("No commit shown (kinds: ai_calls)…" counted nothing); no region of this record changed. Templates sha256 before: `e2e6dbe76b6d98a38ca182ea13ce5df2d0ed95c671fa5c16e9b473e85bf4df0f`.

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

Compared again 2026-10-26 (15.14 part B): `_history_body.html` gained Jump to (a date field)
in the Timeline tab's filter bar, and its Kind choices and Kind menu links keep the day (`on=`),
all inside the Timeline tab's branch, which this record's syslog view never draws. Nothing
this board's page draws moved; no region here changed; the hash written again.
Templates sha256 before: `fa40e91b832453170ff5d22d740e80d54939fcf820cba3e1812894ebf63e0672`.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Where it sits | History › Query tabs (Timeline, Query, Baselines, Authorisations), breadcrumb "Query › Syslog by device" | History, its Query tab on, breadcrumb "Query › Syslog by device · the network" (C667; the sidebar's Logs draws the same page) | **same** |
| Title and actions | "Syslog by device"; Copy the link; Save this view…; How does this work? | "Syslog by device" with its info link; Copy the link; Save this view… (since C667's saved views, 2026-10-11) | **same** |
| Range | 24 h, 7 d, 30 d, 120 d | the same four | **same** |
| Severity | in the opened device's filters | the same, and beside the range for the table | **deviation** (log: Logs' severity beside the range) |
| Coverage notice | "Part of this range holds nothing yet: … keeps logs 2 years (its Logs retention setting, Settings), but its log store began on 7 Sep, so the first 93 days … never kept; nothing to show is not nothing happened" | the same words from the setting and the store's first day; also days still being counted, and Loki holding more than the setting says | **same** |
| The one-window note | "The 27 days since were asked in one window (one log query spans at most 30 days 1 hour)" | "Counted per day by Mercury's logs reader … a device's lines are those the logs reader holds (its last 24 h), and older ones are asked from Loki once the view has drawn, at most 30 days at a time" (C3166) | **deviation** (log: Logs counts per day in a reader) |
| Headline | "142 lines at error or worse, 4 devices · a row opens its lines" | the same, for the range and severity asked | **same** |
| Device table | Device (a button opening it), Lines, Newest, Most frequent (with the interface: "%LINK-3-UPDOWN Gi0/3 (61)") | Device, Lines, Newest, Most frequent by mnemonic ("%DBAL-4-DELAYED_BATCH (1826)") | **deviation** (log: Logs counts by mnemonic) |
| Opened device's filters | Severity, Mnemonic (with counts), From, To, Text contains | the same five, and Show | **same** |
| Trend | "Trend by mnemonic, lines per day": two series, y and x ticks, a key with "y: lines per day · x: date (UTC)" | the same, up to three series, from the first day counted | **same** |
| Lines | Received (UTC), Severity chip, Mnemonic, Message; newest first | the same, masked | **same** |
| Lines' foot | "Showing 3 of 61 matching lines · the next 50 · Open these lines on Logs" | "Showing 50 of 2295 matching lines … · the next 50 · Open r4's Logs tab · Open these lines on Logs" (the last opening the live tail filtered, since C675) | **same** |
| Footnote | "A line's time is when the collector received it, never the device's clock. The heartbeat lines are left out." | the same | **same** |
| Phone | no board | each device a wrapped row, each line its time and severity over its message | **deviation** (log: Logs at phone width) |
