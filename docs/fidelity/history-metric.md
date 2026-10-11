# Fidelity: History › Query, a metrics question (C667, board B)

The metrics answer as built, compared region by region with its signed-off board (C650's
step). Read from shots of the board and the page side by side, in the same headless Firefox,
Grafana answering with a real capture (`tests/fixtures/grafana/dsquery/throughput.json`; a
different question's series, so its legend names labels the board's would not)
(`tests/test_board_shots.py::test_history_metric`, shot once the chart has drawn).

Board: `AskMetric.dc.html` (History › Query board B, "Interface errors and discards over time",
1440 wide), signed off with boards A and C on canvas v31. The board has no phone variant.
Shots: desktop 1440; phone 390. Compared 2026-10-11. History's own page is board D's and is not
compared here.
Templates compared: templates/v2/history.html, templates/v2/_history_body.html, templates/v2/_history_metric.html

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Crumb and title | "Query › Interface errors and discards over time"; the title | the same, with the network | **same** |
| Actions | Copy the link; Save this view…; How does this work? | Copy the link; the title's info link | **later** (saving a view is C667's next step) |
| Device, interface | two selects (s3; Every interface, Gi1/1) | the same two, Every device first; an interface asked of one device only, its names read from the series | **same** |
| Range | 24 h, 7 d, 30 d, 180 d, 1 y, beside the selects | the same five, on their own row under them | **deviation** (log: the range row) |
| Chart | the Monitoring chart component: title, step and points, labelled axes with units, the crosshair with each series' value, a shaded "no data before …" | the Monitoring chart component (uPlot, the same island): title, axes in the unit, the cursor; the step and points and the read time in its foot | **deviation** (log: the chart is Monitoring's as it is; the shaded first day waits on the metrics' first sample being read) |
| Coverage | where the range starts, the history's first day, which store answers which part | which store answers (the live store's days; past them the long-term store, or a refusal naming the setting when none is set) | **deviation** (log: no first sample is read yet) |
| Source | the counters, every 60 s, Prometheus and Thanos | the counters, every 60 s, read from Prometheus through Grafana | **same** |
| The query | "The query (PromQL), editable" | "The query (PromQL), editable": the question's PromQL in a box with Run; your query is drawn by the same chart, carried in the address, the title chipped "edited" with the question's own shown beside it and a way back (compared again 2026-10-11) | **same** |

## Board A's "CPU and memory trend", in board B's layout (2026-10-11)

No board draws this answer; board A lists the question and board B draws a metrics answer, so
it takes board B's layout with what differs: per device, no interface select; two series per
device (CPU, and memory's Processor pool share) on one percent axis; a **Covers** line saying
memory is drawn only where a device's scrape carries a memory pool (measured on the host: the
routers carry one, the switches none). Shot at 1440 and 390 (`history-metric-cpu`, the same
Grafana capture standing in for the answer). **deviation** (log: CPU and memory in board B's layout).

## Board A's last three questions, in board B's layout (2026-10-11)

Routing neighbour changes, Restarts and Telemetry rates take the same layout as CPU and memory:
per device, no interface select, a **Covers** line saying what each counts. Neighbours draws
the established adjacencies per protocol (OSPF full, OSPFv3 full, BGP established); Restarts
the uptime counter's falls per step, with **Mercury's restart record** under the chart (each
restart planned or not, its window and the device's reason, and the record's first day);
Telemetry the IOS-XE telemetry series each device holds, by YANG model for one device. The
neighbour question's "per neighbour" (board A) is per protocol on one device. Not shot
separately: the layout is the CPU shot's, and the record's region is a list in the card style.
**deviation** (log: the last three questions in board B's layout).

## Board A's "Ask your own (PromQL or LogQL)…", in board B's layout (2026-10-11)

Board A draws only the dashed card. It opens board B's layout with no question: no device or
interface select, the range row, a query card first (the language, the query, Run, its
bounds said), then PromQL drawn by the same chart, or a LogQL line query drawn as board C's
lines table (received time, the stream's labels, the line, masked; the newest 200 over at most
30 days). Nothing is asked until a query is written. **deviation** (log: Ask your own in board
B's layout).
