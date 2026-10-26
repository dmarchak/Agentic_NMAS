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
Templates compared: templates/v2/history_ask_metrics.html, templates/v2/_history_body.html, templates/v2/_history_ask_metrics.html, templates/v2/_history_ask_parts.html, templates/v2/_history_ask_head.html, templates/v2/_history_ask_words.html, templates/v2/_ai.html, templates/v2/_history_ask_chips.html
Templates sha256: `165c2477d3c2b4b29b239e6d420d8c6337d234821c18fad25c863b6ce62b5e01`

Compared again 2026-10-15 (P7-03): `_history_body.html` gained a `data-concept` marker and one
sentence inside a Baselines row's detail (the block drawing each baseline's Re-apply… link); this
record compares Ask your own, metrics, where Baselines is only a tab name (unchanged). No region
here changed; the hash written again.

Compared again 2026-10-16 (C522): `_history_body.html`'s Baselines card gained a heading row (the
count of baselines and "How does this work?" in words, C503's rule), inside the Baselines tab's
branch, which Ask your own never draws; the shots retaken (tests/test_board_shots.py). No region
here changed; the hash written again.

Compared again 2026-10-18 (the operator's walk of 2026-10-18, B): `_history_body.html` gained
the Kind choices one click away (All, Goldens, Intent, Deploys and restores, Measured,
unchanged, Restarts) under the Timeline tab's filters, inside the Timeline tab's branch, which
Ask your own never draws. The page rendered on test_device_v2's lab from the templates as they
were and as they are: every byte the same. No region here changed; the hash written again.
Templates sha256 before: `e4ba3491dcf923a164f7678a65c33f2e6622075648ce2233da95593dd876d8c8`.

Changed 2026-10-25 (PHASE8_PLAN 8.1, feature 1): `_history_ask_metrics.html` gained one row
at the top of the builder card, **Ask in words** (a question, Fill the builder, its "How does
this work?", and the result's notice beneath), which board E3 does not draw. Every other
region is as it was. The row's verdict is **later**: its board and its comparison are batched
into the sprint's Saturday (PHASE8_PLAN 15.12, "Each screen ships with its browser tests and a
short manual page; its board and its fidelity record are batched into Saturday"); its browser
test is tests/test_ai_nl_query.py's `test_ask_in_words_in_a_browser`. The hash written again.
Templates sha256 before: `6357e667ba5601243738d5fe301506067d339162be1aa01bcf88be7d98c1619d`.

Changed 2026-10-25 again (the operator's recorded cases: a question back, never a guess): the
Ask in words row's result gained a third notice, "One question first: …", drawn as information
(the muted notice, never the warning), the person's words kept in the box. Its verdict stays
**later** with the row (8.1's board, Saturday). The hash written again.
Templates sha256 before: `6e78140fd539a30094b6e5a8d6ac720d9eba7794d2a151e8742c3e2104735897`.

Changed 2026-10-25 again (8.1's logs half): the Ask in words row moved, byte for byte the
same markup, into `_history_ask_words.html`, which both builders include (one home); that file
joins the templates compared, so a change to it is compared again. No region here changed;
the hash written again. Templates sha256 before: `f31e221fd21162962e924384046eb44e2e0bb566163c03851ca2fb002c3f3930`.

Changed 2026-10-25 again (PHASE8_PLAN 15.13, the AI controls' rule): the Ask in words row
gained the one AI mark beside its label (its hover the task, its pinned model and its per-call
cap) and, while hosted AI cannot answer (off, no key, the day cap reached, the record
unreadable), its box and Fill the builder disabled with the reason drawn under them and, for a
person who may configure, the link to the AI (hosted) card. The row draws them through
`_ai.html`, which joins the templates compared. Only `_history_ask_words.html` changed, and
only inside the row; every other region is as it was, and nothing in the builder is disabled
by AI's state (tests/test_ai_nl_query.py's
`test_ask_in_words_is_an_ai_control_and_the_builder_stays_usable`; in Firefox at 1440 and 390,
`test_ask_in_words_with_hosted_ai_off_in_a_browser`). The row's verdict stays **later** with
8.1's board (Saturday). The hash written again.
Templates sha256 before: `634fba84df494aab18a4d3c1580cd9200ba238380e68ac14056add4d6c82c05f`.

Changed 2026-10-25 again (C1700, approved by the operator for the sprint):
- **Ask in words gains a fourth notice.** A question no metric matches is answered by Mercury
  itself, with no AI call: "Mercury answered this itself, with no AI call ($0)". It says what
  could not be matched among how many, what to name and which devices, then gives the
  Start-from chips as links. It is drawn as information, the muted notice and never the
  warning, and the person's words stay in the box. Its verdict stays **later** with the row
  (8.1's board, Saturday). Its test is tests/test_ai_nl_offer.py's.
- **The Start-from chips moved, byte for byte the same, into `_history_ask_chips.html`.** The
  builder's own row and that answer draw it (one home), and it joins the templates compared.
  The Start from region is drawn as it was; its verdict stays **same**.

The hash written again.
Templates sha256 before: `44add06d08bb11d0795a5be383c7b169a11a6d526a4cc600e48bf0106ecf4a43`.

Changed 2026-10-25 again (the gate's fixes):
- `_ai.html`'s `attrs` takes the control's route's kind (`ai.attrs(c, 'configure')`), which
  renders exactly `gate(kind)` while the control can answer.
- Mercury's unmatched words are joined, not looped: the same words drawn.

No region changed; the hash written again.
Templates sha256 before: `c1890ebd8fc6acb68d7b63d46ea375a2216afb0efb3a8d49a65a1e8bb5313903`.
Changed 2026-10-25 again (PHASE8_PLAN 15.13, the operator's ruling on case 13): the Operations
row gained **changes**, a first step for a gauge (or a metric Prometheus gives no type): an
option in the first operation's select, "changes: times the value changed", its window select
offering a rate's four windows and the ranges' lengths (1 day to 90 days), each row offering
only its own windows; a **Changes** heading and item in + operation's menu, before Units; and
the gauge's hint gains "changes counts how often it changed" (the untyped one's "and changes,
for a gauge"). Compared by rendering the page from the templates and module as they were and
as they are, the stand-in answering (the board's question asked and not, its op3 marked, the
Start-from chips' errors, CPU and BGP questions, a counter's increase, nothing chosen): the
board's own question, and every counter's, is the same bytes but the run's temporary folder;
a gauge's page differs only by the menu's Changes item and the hint. The board draws a
counter's chain, so no region of the shots moves. The Operations region stays a
**deviation**, its log line widened (log: E3 metrics builder: the operation menu, with
changes). The hash written again. Templates sha256 before: `74389e8daf7572290fae2e4abe0e794acacb361b07104a01e0b0fec8e491282b`.

Changed 2026-10-25 again (C1724, the operator's ruling on prompt v6; C1740): "today" runs from
midnight in the viewer's browser's timezone, as no installation timezone exists. The Ask in
words form gains two hidden inputs, `tz` and `tz_off`, which static/js/nmas_logq.js fills
(drawn by `_history_ask_metrics.html` setting `words_tz`), and the filled notice gains one
sentence when the answer's range starts at today's midnight: "'Today' runs from midnight
<zone> (your browser's timezone; no installation timezone is set)", or the offset's, or
UTC's with why. Compared by rendering the page from the templates as they were and as they
are, the stand-in answering (nothing chosen, a metric chosen, filled with a range not today's,
filled with today's): the pages differ only by the two hidden inputs, which draw nothing, and
the today's fill by that one sentence inside the notice. No region of the shots moves; the
row's verdict stays **later** with 8.1's board (Saturday). Its tests are
tests/test_ai_nl_query.py's "today" section, in Firefox
`test_the_timezone_is_filled_and_sent_in_a_browser`. The hash written again.
Templates sha256 before: `65002398e8dd65f73e7a2ca9c12e2d7ea4b1de399a313796d1e4cc4bfed83bc2`.

Changed 2026-10-26 (C1740's logs half): `_history_ask_words.html`'s comment now says both
builders set `words_tz`. Only the comment changed, and it renders nothing: this page draws the
same bytes. No region changed; the hash written again.
Templates sha256 before: `1e69029e69320f998cfa45dd1080705a932d6905312e0d09de738ecd332739a2`.

Compared again 2026-10-26 (15.14 part B, links both ways): `_history_ask_words.html`'s filled
notice reads "Filled from your words (<model>, $x, this call in History)", the last words a
link to the call's own row on History (`/v2/history?call=<id>`: that call, opened); and the
call's row there links back to this builder as the answer filled it ("Open what it produced",
every choice in its address, the address the fill pushes). `_history_body.html` gained Jump to
in the Timeline tab's branch, which this page never draws. No board draws Ask in words (the
row stays **later** with 8.1's board); nothing else on the page moved; the hash written again.
Templates sha256 before: `2724e7ee9f0a0f96951c790c101037d33dee6f462bcdb4c31799b674459ef356`.

Compared 2026-10-26 with 8.1's board (the overnight order's item 6): `AskWords.dc.html`, canvas
page "History, Query", drawn under the Phase 7 operating mode after the row was built, nine
states of the one row. Shots: `tests/test_board_shots.py::test_history_ask_words`, on
tests/test_ai_nl_query.py's site (the stand-in Prometheus, hosted AI allowed, the adapter
answering as planted): the row, filled, a question back, Mercury's own answer and refused at
1440, 1280 and 390, then hosted AI off at 1440 and 390; the board at 1440. Every state is drawn
as the board draws it but two ways, one deviation: each notice spans the card's width, edge to
edge, where the board insets it under the row, and the filled notice names the model's id
beside its name. The busy state is not shot (it lasts as long as the call);
tests/test_v2_busy_on_itself.py holds it. "Today"'s sentence is compared from the rendered
page by tests/test_ai_nl_query.py's "today" section, not a shot. No template changed; the
hash stands.

Changed 2026-10-26 (the AI day cap's stated boundary): `_macros.html` gained `resets()`, the
AI cap's reset time drawn on Settings' AI card and an AI control's day-cap reason; this page
draws neither (the Ask in words row's reason is `_ai.html`'s, which draws it only when the cap
refuses). No region changed; the hash written again.
Templates sha256 before: `94a252f672da1286af07698c19a651d40dc8f641a97bca7c482b56ac2af60533`.

Compared again 2026-10-26 (the operator's Ask-in-words walk, C1805): `_history_ask_words.html`'s
filled notice says how the words' period was read, every time: "Read as Wed 14 Oct 03:48 to
Thu 15 Oct 03:48 America/Denver (24 hours; 2026-10-14 09:48 to 2026-10-15 09:48 UTC)", before a
named span's midnight when there is one. The shots at 1440, 1280 and 390 retaken
(`tests/test_board_shots.py::test_history_ask_words`): the notice is one sentence longer and
wraps inside its box at 390; nothing else moved. A deviation (log: 8.1 Ask in words: the period
read). `_history_ask_logs.html`'s empty state changed too, which this page never draws
(docs/fidelity/history-ask-logs.md).

Compared again 2026-10-26 (the operator's walk of History › Query that day, items 3, 9, 10
and 12). Shots: `tests/test_board_shots.py::test_history_ask_metrics` (the board's question,
the phone, the three states, and a new state, `history-ask-metrics-unseen`, at 1440: a device
chosen that the range does not hold) and `test_history_ask_words` (its question back,
Mercury's own answer and refused states now drawn after a fill, so each shows the builder
left from the previous question). Board E3's files (`QueryBuilderMetrics3*.dc.html`) were not
in the canvas copy the shots read, so the regions were compared with this record's own
description of the board (the Board column below) and with 8.1's `AskWords.dc.html`, which
was. What moved:
- **Scope first** (item 12): Range is the third row, after Start from and before What,
  Devices and Interfaces, which are read over it; the board draws it after the query. A
  metric, device or interface chosen that the range no longer holds is kept in the address,
  its chip on, marked "not seen in this range"; a metric not held forms no query, and Ask says
  so (it was dropped from the address before, with a "Not taken" notice).
- **Left from your previous question** (item 3): after Mercury's own $0 answer, a question
  back or a refusal, the builder is marked (a notice with **Keep these choices**, the query
  box outlined and labelled) and Ask is off until kept or a choice changes.
- **One zone per view** (item 10): the answer's title, its timing, the legend's Now head, the
  empty state's span, the metric list's and the limits' read times are written in the
  browser's zone, named, with UTC on hover; the chart's axis was already the browser's, and
  its hover now names the zone with UTC under it.
- **Each point at its own instant** (item 9, checked): a rate or increase over [w] at t covers
  (t − w, t] and is drawn at t, a line through the instants, never a step held over the next
  window; nothing moved here (tests/test_history_ask_metrics.py,
  `test_a_point_is_drawn_at_the_instant_prometheus_answered_for`).
Every other region is as it was. The hash written again.

Compared again 2026-10-26, against board E3 itself (the operator, the same evening: the boards
found and restored). `QueryBuilderMetrics3.dc.html` and `QueryBuilderMetrics3Phone.dc.html`
were never committed to git; they are in the mockups canvas's `project/` folder, now copied
whole into the shots' folder (the shots refuse a missing board, C1818). Shots:
`tests/test_board_shots.py::test_history_ask_metrics` and `test_history_ask_words`, the board at
1440, 1280 and 390 beside the page as merged (the walk's fixes and the builder's items), each
board shot opened and seen to be the board. Region by region, the verdicts below hold as written
from the description, but one: the board draws From… to…'s picker open inline at the bottom,
under a Range that follows the query; with Range now the third row, the page's picker opens
over What, Devices and Interfaces until Apply or Cancel (the Range row's verdict, and log: E3
metrics builder: the range picker over the scope rows). The chart title and the legend's Now are
the browser's zone where the board's are UTC (log: History › Query: one zone per view); Ask in
words is 8.1's row, which E3 predates (its log lines). The board's fidelity and shell notes are
its annotations. Nothing else differs.
Templates sha256 before: `c9f18041accccf75419f186a6c8350718c384715f542342a8d1c840a76c10a24` (the
builder's items alone) and `99af8181cc6bbd6f4df3e92de102e8ffc95c3f450d406aea489fdcfd742bfc7f`
(the walk's fixes alone), each written before the two were merged.
Templates sha256 before: `d18c51cf3a8a68efe8ad28dc9c2bbdbdaa00e83c3728df837c81f3c72e26047e`.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Tabs | Timeline, Query, Baselines, Authorisations; Query on | Timeline, Query, Baselines; Query on | **deviation** (log: E3 metrics builder: History's tabs) |
| Head | "Ask your own ‹ back to the questions"; Source (Metrics, Logs) and Mode (Builder, Code) | the same, shared with F3; Metrics and Builder on | **same** |
| Ask in words | 8.1's board (`AskWords.dc.html`): the row, busy, filled (model, cost, the call in History, the test run), a named day's midnight, a question back, Mercury's own answer with the chips, refused, hosted AI off | a question, Fill the builder busy on itself, "How does this work?"; the result's notice under it (saying whose midnight "today" began, when the range is today's); the AI mark; disabled with its reason (and the AI card's link) while hosted AI cannot answer; each notice the card's width, the model's id beside its name; not filled, the builder marked left from the previous question (Keep these choices, the query box outlined, Ask off until kept or changed) | **deviation** (log: 8.1 Ask in words: the notices); (log: History › Query: left from your previous question) |
| Start from | four chips, the one the choices match marked | the same four, each setting every choice; marked when the question is exactly its own; a chip whose metric Prometheus does not hold is drawn but no link | **same** |
| What | search box, the matching metrics with help, "per interface · counter · bytes", the count read | the same box and list; each with Prometheus's help and its type and unit; the count over the range, when read; after Range; a metric chosen the range does not hold kept, marked "not seen in this range" | **deviation** (log: E3 metrics builder: the metric list); (log: History › Query: not seen in this range) |
| Devices | + device, by role: core, all 9; "the values the device label holds now" | the same, from the metric's `device` and `role` labels over the range; a device chosen the range does not hold kept, marked "not seen in this range" (an interface the same) | **deviation** (log: E3 metrics builder: devices, roles and interfaces); (log: History › Query: not seen in this range) |
| Interfaces | all, three names, + 14 more | all, the first three of the `ifDescr` values, + 15 more (a field with the rest) | **deviation** (log: E3 metrics builder: devices, roles and interfaces) |
| Filters | the chip with ×, + filter, the editor: label, = != =~ !~, value, Add, Cancel, the values held, "would leave out 9 series" | the same, the count from Prometheus (9, as the board) | **deviation** (log: E3 metrics builder: the filter editor) |
| Operations | the numbered chain of selects with × and arrows, + operation's menu (Units, Group), the counter rule and the unit | the same; the menu adds Rate, Compare and count by, and, for a gauge, Changes | **deviation** (log: E3 metrics builder: the operation menu, with changes) |
| Top | only the top, 5 or 10, why off | the same control; the hint says what topk does | **deviation** (log: E3 metrics builder: Top) |
| The query | the dark box, the last choice marked and repeated, the plain sentence, Edit as code | the same, shared with F3 | **same** |
| Range | 1 h to 90 days, From… to… with relative or absolute UTC and local beside, the fit line, the limits by source, the step ladder, Apply, Cancel | the same; the third row, after Start from, before What; the picker opens over the rows under it (What, Devices, Interfaces) until Apply or Cancel, where the board draws it inline at the bottom | **deviation** (log: E3 metrics builder: the range row); (log: History › Query: scope first); (log: E3 metrics builder: the range picker over the scope rows) |
| Actions | Ask, Save…, Copy the link | Ask (busy on itself, "Asking Prometheus…"), Save this view…, Copy the link, the (i) | **deviation** (log: E3 metrics builder: the actions' words) |
| The answer | title, series and timing, the chart in bits per second, legend with now, highest, lowest | the same title, timing and legend; the Monitoring chart; every time in the browser's zone, named, UTC on hover | **deviation** (log: E3 metrics builder: the answer's chart); (log: History › Query: one zone per view) |
| Code mode | the box with PromQL; "the builder can't read this back" | today's Ask your own box, Code on the switch, handed the query; its Builder opens the builder afresh | **later** (reading PromQL back into the builder, registered with this record) |
| Saved queries | the network's saved queries, each with its tag, query, pin and Run › | the same list from the saved views | **deviation** (log: E3 metrics builder: the saved queries) |
| Refused by a bound | "at most 1,000 points a series", with the step and the narrower range | the bounds the builder can pass, both operands, the choice that fits | **deviation** (log: E3 metrics builder: the refused state) |
| Prometheus not answering | Couldn't load, when; the last good read; Ask again | Couldn't load, when; the probe's last read; Ask again | **deviation** (log: E3 metrics builder: Prometheus not answering) |
| No data in range | no samples between; held from (90 days); not a zero rate; Start the range at | the same words and button | **deviation** (log: E3 metrics builder: no data in range) |
| Phone | labels above controls, switches wrap, the chain stacks, the chart full width, legend stacked | the same | **deviation** (log: E3 metrics builder: the phone's legend) |
