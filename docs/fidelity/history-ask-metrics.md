# Fidelity: History › Query › Ask your own, the metrics builder (board E3)

The metrics builder as built, compared region by region with its approved boards. Read from
shots of the boards and the page side by side, in the same headless Firefox, Prometheus
answering through a stand-in with the real captures of the lab's Prometheus read on 2026-10-15
09:47 to 09:50 UTC (`tests/fixtures/prometheus/ask_*.json`, and `status_config.json`; instance
addresses mapped into 192.0.2.0/24), Loki's bounds from F3's captures and Grafana's data sources
from theirs (`tests/test_board_shots.py::test_history_ask_metrics`, the chart shot once drawn,
From… to… and the operation menu opened as the board draws them). The capture is the board's
question over 12 to 15 Oct (the lab's roles are router and switch, not core and access), so the
shot's numbers are the capture's; the layout is what is compared.

Boards: `QueryBuilderMetrics3.dc.html` (1440 wide) and `QueryBuilderMetrics3Phone.dc.html` (390
wide), canvas page "History, Query", approved by the operator with F3 on 2026-10-15. Shots: the
desktop board at 1440 and 1280 beside the page; the phone board at 390 beside the page held to a
390 px column; the three states (refused, Prometheus not answering, no data in range) at 1440.
Compared 2026-10-15. History's own page (heading, remote line) is board D's; the board's Code
mode panel is today's Ask your own box, Code on the Mode switch.
Templates compared: templates/v2/history_ask_metrics.html, templates/v2/_history_body.html, templates/v2/_history_ask_metrics.html, templates/v2/_history_ask_parts.html, templates/v2/_history_ask_head.html
Templates sha256: `e4ba3491dcf923a164f7678a65c33f2e6622075648ce2233da95593dd876d8c8`

Compared again 2026-10-15 (P7-03): `_history_body.html` gained a `data-concept` marker and one
sentence inside a Baselines row's detail (the block drawing each baseline's Re-apply… link); this
record compares Ask your own, metrics, where Baselines is only a tab name (unchanged). No region
here changed; the hash written again.

Compared again 2026-10-16 (C522): `_history_body.html`'s Baselines card gained a heading row (the
count of baselines and "How does this work?" in words, C503's rule), inside the Baselines tab's
branch, which Ask your own never draws; the shots retaken (tests/test_board_shots.py). No region
here changed; the hash written again.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Tabs | Timeline, Query, Baselines, Authorisations; Query on | Timeline, Query, Baselines; Query on | **deviation** (log: E3 metrics builder: History's tabs) |
| Head | "Ask your own ‹ back to the questions"; Source (Metrics, Logs) and Mode (Builder, Code) | the same, shared with F3; Metrics and Builder on | **same** |
| Start from | four chips, the one the choices match marked | the same four, each setting every choice; marked when the question is exactly its own; a chip whose metric Prometheus does not hold is drawn but no link | **same** |
| What | search box, the matching metrics with help, "per interface · counter · bytes", the count read | the same box and list; each with Prometheus's help and its type and unit; the count over the range, when read | **deviation** (log: E3 metrics builder: the metric list) |
| Devices | + device, by role: core, all 9; "the values the device label holds now" | the same, from the metric's `device` and `role` labels over the range | **deviation** (log: E3 metrics builder: devices, roles and interfaces) |
| Interfaces | all, three names, + 14 more | all, the first three of the `ifDescr` values, + 15 more (a field with the rest) | **deviation** (log: E3 metrics builder: devices, roles and interfaces) |
| Filters | the chip with ×, + filter, the editor: label, = != =~ !~, value, Add, Cancel, the values held, "would leave out 9 series" | the same, the count from Prometheus (9, as the board) | **deviation** (log: E3 metrics builder: the filter editor) |
| Operations | the numbered chain of selects with × and arrows, + operation's menu (Units, Group), the counter rule and the unit | the same; the menu adds Rate, Compare and count by | **deviation** (log: E3 metrics builder: the operation menu) |
| Top | only the top, 5 or 10, why off | the same control; the hint says what topk does | **deviation** (log: E3 metrics builder: Top) |
| The query | the dark box, the last choice marked and repeated, the plain sentence, Edit as code | the same, shared with F3 | **same** |
| Range | 1 h to 90 days, From… to… with relative or absolute UTC and local beside, the fit line, the limits by source, the step ladder, Apply, Cancel | the same; the picker opens under the row | **deviation** (log: E3 metrics builder: the range row) |
| Actions | Ask, Save…, Copy the link | Ask (busy on itself, "Asking Prometheus…"), Save this view…, Copy the link, the (i) | **deviation** (log: E3 metrics builder: the actions' words) |
| The answer | title, series and timing, the chart in bits per second, legend with now, highest, lowest | the same title, timing and legend; the Monitoring chart | **deviation** (log: E3 metrics builder: the answer's chart) |
| Code mode | the box with PromQL; "the builder can't read this back" | today's Ask your own box, Code on the switch, handed the query; its Builder opens the builder afresh | **later** (reading PromQL back into the builder, registered with this record) |
| Saved queries | the network's saved queries, each with its tag, query, pin and Run › | the same list from the saved views | **deviation** (log: E3 metrics builder: the saved queries) |
| Refused by a bound | "at most 1,000 points a series", with the step and the narrower range | the bounds the builder can pass, both operands, the choice that fits | **deviation** (log: E3 metrics builder: the refused state) |
| Prometheus not answering | Couldn't load, when; the last good read; Ask again | Couldn't load, when; the probe's last read; Ask again | **deviation** (log: E3 metrics builder: Prometheus not answering) |
| No data in range | no samples between; held from (90 days); not a zero rate; Start the range at | the same words and button | **deviation** (log: E3 metrics builder: no data in range) |
| Phone | labels above controls, switches wrap, the chain stacks, the chart full width, legend stacked | the same | **deviation** (log: E3 metrics builder: the phone's legend) |
