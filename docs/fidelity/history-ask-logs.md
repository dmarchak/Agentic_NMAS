# Fidelity: History › Query › Ask your own, the logs builder (board F3)

The logs builder as built, compared region by region with its approved boards. Read from shots
of the boards and the page side by side, in the same headless Firefox, Loki answering through a
stand-in with the real captures of the lab's Loki read on 2026-10-15
(`tests/fixtures/loki/ask_*.json`, `config_limits.yaml`; addresses mapped into 192.0.2.0/24,
lines masked) (`tests/test_board_shots.py::test_history_ask_logs`, the chart shot once drawn).
The capture's counts are every line per device, counted hourly (not the board's OSPF lines
every 5 minutes), so the shot's numbers are the capture's; the layout is what is compared.

Boards: `QueryBuilderLogs3.dc.html` (1440 wide) and `QueryBuilderLogs3Phone.dc.html` (390 wide),
canvas page "History, Query", approved by the operator with E3 on 2026-10-15. Shots: the desktop
board at 1440 and 1280 beside the page; the phone board at 390 beside the page held to a 390 px
column; the page's Lines view (1440, 390), and its three states (refused, empty, Loki not
answering) at 1440. Compared 2026-10-15. History's own page (heading, remote line) is board D's.
Compared again 2026-10-15: each `<details>` keyed (`data-keep`, C472) so a redraw keeps it open; the shots retaken, nothing drawn moved.
Compared again 2026-10-15 (board E3): the go links, the query box, the range chips and picker, the actions and the three states moved into `_history_ask_parts.html`, which the metrics builder shares (the rendered page the same but for whitespace, every state rendered before and after and compared); the head's Metrics switch now opens the metrics builder, and Code mode's Builder is a link. The shots at 1440, 1280 and 390 retaken; nothing drawn moved. Two fixes found on the way, neither a region's verdict: the bounds line says no log store is configured where none is (it raised an error page before, reading Loki's unread limits), and the heartbeat stage writes the marker as an RE2 literal, `NMAS-HEARTBEAT` (Python's escape wrote `NMAS\\-HEARTBEAT`, the same lines matched).
Templates compared: templates/v2/history_ask_logs.html, templates/v2/_history_body.html, templates/v2/_history_ask_logs.html, templates/v2/_history_ask_head.html, templates/v2/_history_ask_parts.html
Templates sha256: `cb299325a3e2248c203f694d7680f347a6969aba5a7ef16ed2ab30661306480a`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Tabs | Timeline, Query, Baselines, Authorisations; Query on | Timeline, Query, Baselines; Query on | **deviation** (log: F3 logs builder: History's tabs) |
| Head | "Ask your own ‹ back to the questions"; Source (Metrics, Logs) and Mode (Builder, Code) switches | the same; Metrics opens the metrics builder (E3, shared head) | **same** |
| Start from | four chips, the one the choices match marked | the same four, each setting every choice; marked when the choices are exactly its own | **same** |
| Kind | syslog, SNMP traps, both; the job names and when read in the hint | the `job` label's values over the range as switches (one or more) and every job; how many and when read in the hint | **deviation** (log: F3 logs builder: the Kind row) |
| Devices | chosen chips with ×, + device, by role, all N; "by the device label, never a regex" | the same; + device asks a name from the values Loki holds; the hint says label or line, with the label's first line | **deviation** (log: F3 logs builder: devices before the label began) |
| Severity | "at or worse than" and a select | the same, any severity or 0 to 7; the hint says label or the mnemonic's digit | **same** |
| Mnemonic | chips from the store for the chosen devices, + more | the same, from Mercury's logs reader's counts, the most frequent four and + N more | **same** |
| Text | contains, excludes | the same | **same** |
| Show | Lines or Counts over time; per device or per mnemonic; every 5 minutes or 1 hour | the same switch; per device, per mnemonic or per any label Loki holds; every 1 minute to 1 day | **deviation** (log: F3 logs builder: the Show row's choices) |
| The query | the dark box, the last choice marked and repeated, the plain sentence | the same; Mercury's heartbeat stage drawn in it | **deviation** (log: F3 logs builder: the heartbeat stage) |
| Edit as code | "Edit as code hands it to Code mode" | the link, to today's box with the LogQL; counts said to be drawn as lines only there | **deviation** (log: F3 logs builder: Edit as code and Code) |
| Range | 1 h, 24 h, 7 days, 30 days, From… to… (E3's picker) | the same chips; From… to… opens relative or absolute UTC with local beside, the fit line, Loki's and Mercury's limits, Apply, Cancel | **same** |
| Bounds | 200 a page; Loki's span, timeout, lines, series, retention, read from /config | the same, read from Loki's /config at the time drawn; "revealing one is recorded" dropped | **deviation** (log: F3 logs builder: the Lines view's paging and Reveal) |
| Actions | Ask, Save…, Copy the link | Ask (busy on itself, "Asking Loki…"), Save this view…, Copy the link, the (i) | **deviation** (log: F3 logs builder: the actions' words) |
| Counts answer | title, series and timing, the step chart, legend with lines in range, most in a window, last line | the same title and timing; the Monitoring chart stepped; the legend with lines in range, most in a window, last window with a line | **deviation** (log: F3 logs builder: the counts chart) |
| A point's lines | a tooltip over the chart with Show these lines | a box under the chart naming the series and window, with Show these lines | **deviation** (log: F3 logs builder: a point's lines) |
| Lines view | time, device, severity, kind, masked line, Reveal…; 1 to 200 of N, Older › | the same columns but Reveal…; Lines 1 to 200 of N, newest first, Older ›, and ‹ Newest once paged | **deviation** (log: F3 logs builder: the Lines view's paging and Reveal) |
| Reveal… | asks a reason, shows one line unmasked, recorded | not drawn: no reveal operation for a log line exists yet | **later** (a reveal operation for one log line, registered with this record) |
| States | refused by a bound, Loki not answering, no lines in range | the same three, each naming both operands, the wait, or what was sent, with its button | **same** |
| Phone | labels above controls, switches wrap, the chart full width, legend stacked, each line a card | the same | **same** |
