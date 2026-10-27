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
Compared again 2026-10-15 (C818, C819; the operator's decisions of that day): Reveal… built as the board draws it, and Edit as code from Counts ending in Code mode's chart. The page shot at 1440, 1280 and 390 as before, and two more states beside the board's Lines view: `history-ask-logs-reveal-ask-page-<width>` (the box open with a reason) and `history-ask-logs-revealed-page-<width>` (the line revealed), at 1440 and 390, fed by the lines capture with one planted secret-bearing line (tests/test_log_reveal.py). Each masked value is now marked as the board marks it; the bounds line says revealing is recorded, as the board's does.
Templates compared: templates/v2/history_ask_logs.html, templates/v2/_history_body.html, templates/v2/_history_ask_logs.html, templates/v2/_history_ask_head.html, templates/v2/_history_ask_parts.html, templates/v2/_history_ask_words.html, templates/v2/_ai.html
Templates sha256: `bdce9d617ea643c278ed6bf9650d15069714dba64923c2afd0fd303d8668d8a6`

Compared again 2026-10-15 (P7-03): `_history_body.html` gained a `data-concept` marker and one
sentence inside a Baselines row's detail (the block drawing each baseline's Re-apply… link); this
record compares Ask your own, logs, where Baselines is only a tab name (unchanged). No region here
changed; the hash written again.

Compared again 2026-10-16 (C522): `_history_body.html`'s Baselines card gained a heading row (the
count of baselines and "How does this work?" in words, C503's rule), inside the Baselines tab's
branch, which Ask your own never draws; the shots retaken (tests/test_board_shots.py). No region
here changed; the hash written again.

Compared again 2026-10-18 (the operator's walk of 2026-10-18, B): `_history_body.html` gained
the Kind choices one click away (All, Goldens, Intent, Deploys and restores, Measured,
unchanged, Restarts) under the Timeline tab's filters, inside the Timeline tab's branch, which
Ask your own never draws. The page rendered on test_device_v2's lab from the templates as they
were and as they are: every byte the same. No region here changed; the hash written again.
Templates sha256 before: `bae7fb3468ed1abd511564d3cd771d79652bc80df9b74cf9e60a809434ddac2d`.

Changed 2026-10-25 (PHASE8_PLAN 8.1, feature 1's logs half): `_history_ask_logs.html` gained
one row at the top of the builder card, **Ask in words** (`_history_ask_words.html`, the row
the metrics builder has, now included by both: a question, Fill the builder, its "How does
this work?", and the result's notice beneath), which board F3 does not draw. Every other
region is as it was. The row's verdict is **later**: its board and comparison are batched
into the sprint's Saturday (PHASE8_PLAN 15.12); its browser test is tests/test_ai_nl_logs.py's
`test_ask_in_words_on_the_logs_builder_in_a_browser`. The included file joins the templates
compared. The hash written again.
Templates sha256 before: `4eeb3357744f3d6b3311086208d30f8123d8b8da924a0536eb6a471348a4cc1a`.

Changed 2026-10-25 again (PHASE8_PLAN 15.13, the AI controls' rule): the Ask in words row
gained the one AI mark beside its label (its hover the task, its pinned model and its per-call
cap) and, while hosted AI cannot answer (off, no key, the day cap reached, the record
unreadable), its box and Fill the builder disabled with the reason drawn under them and, for a
person who may configure, the link to the AI (hosted) card. The row draws them through
`_ai.html`, which joins the templates compared. Only `_history_ask_words.html` changed, and
only inside the row; every other region is as it was, and nothing in the builder is disabled
by AI's state (tests/test_ai_nl_logs.py's
`test_ask_in_words_on_the_logs_builder_is_an_ai_control_and_the_builder_stays_usable`). The
row's verdict stays **later** with 8.1's board (Saturday). The hash written again.
Templates sha256 before: `fdcd932bf6275b73e1b7fa21a6f1b3b46762e335b36197b9820dbf9813490a68`.

Changed 2026-10-25 again (C1700): `_history_ask_words.html` gained Mercury's own answer to a
question no metric matches, with the metrics builder's Start-from chips
(`_history_ask_chips.html`). Only the metrics half answers that way: the logs half never
returns it, so this page never draws it, and the chips' file is not among this screen's
templates. No region here changed; the hash written again.
Templates sha256 before: `4ee05a6cec06fd6e7005ac9b053e0d3f05de1bf3738bc76a87f6382a2ddd7dc3`.

Changed 2026-10-25 again (the gate's fixes):
- `_ai.html`'s `attrs` takes the control's route's kind (`ai.attrs(c, 'configure')`), which
  renders exactly `gate(kind)` while the control can answer.
- Mercury's unmatched words are joined, not looped.

Nothing drawn on this page changed; the hash written again.
Templates sha256 before: `b106ce9eaf710572ccecbdd30675a68f78a13b483fbb7c80d3168012585e0de7`.

Compared again 2026-10-27 (C1834, logs v4 matching text in any case): the Text row gained an
"any case" checkbox between contains and excludes (`anycase`, off by default; on, the contains
filter is `|~ "(?i)…"`, its words on hover), and the empty answer says "in any case" when it is
on. Shots: `history-ask-logs-page-1440` beside the board at 1440, the Text row region. The board
draws contains and excludes only: a **deviation**, logged ("History, Ask your own (logs): the
Text filter's any-case choice"). Every other region as before; the hash written again.
Templates sha256 before: `0f900cdfbb3c6186dc0718b6bb0c7e827d3bc3319bf9ef8870429c41c077c5e0`.

Changed 2026-10-25 again (C1724, C1740): `_history_ask_words.html` gained the metrics
builder's timezone inputs (`tz`, `tz_off`), drawn only when the including template sets
`words_tz`, and one sentence in the filled notice when a metrics answer's range is today's.
The logs builder sets no `words_tz` and its answers carry no `today`, so neither is drawn
here: the page rendered from the templates as they were and as they are is the same bytes.
No region here changed; the hash written again.
Templates sha256 before: `62b52a7e20d7effeeafeadbfe8a5c53c7e5dbff6a738ab28bd2a8f22943b715f`.

Changed 2026-10-26 (C1740's logs half, nl_logs v2): `_history_ask_logs.html` sets
`words_tz`, so the Ask in words row now carries the two hidden timezone inputs the metrics
builder's has. When an answer's range starts at a named span's midnight, the filled notice
gains its sentence ("'Yesterday' is counted from midnight America/New_York (…)"), as it does
on the metrics builder. `_history_ask_words.html`'s own change is its comment. The inputs
draw nothing; the sentence is inside the notice the row already draws. The row's verdict
stays **later** with 8.1's board; no other region changed. The hash written again.
Templates sha256 before: `abb2651183ddb8ab878259ae909a6899e3c8f40ab39dad50ae5609cac8231684`.

Compared again 2026-10-26 (15.14 part B, links both ways): `_history_ask_words.html`'s filled
notice reads "Filled from your words (<model>, $x, this call in History)", the last words a
link to the call's own row on History (`/v2/history?call=<id>`: that call, opened); the call's
row there links back to this builder as the answer filled it ("Open what it produced", the
address the fill pushes). `_history_body.html` gained Jump to in the Timeline tab's branch,
which this page never draws. No board draws Ask in words (its row stays **later** with 8.1's
board); nothing else on the page moved; the hash written again.
Templates sha256 before: `2f07e4738a293a07888e1575b4e542b29041ba8e1029ec100de39b8009bf8be2`.

Compared 2026-10-26 with 8.1's board (the overnight order's item 6): `AskWords.dc.html`, its
last state the logs builder's row. Shots: `tests/test_board_shots.py::test_history_ask_words_logs`,
on tests/test_ai_nl_logs.py's world (the stand-in Loki): the row and filled, at 1440 and 390.
The row's other states are the metrics builder's, the same template, compared in
docs/fidelity/history-ask-metrics.md. Drawn as the board draws it but the one deviation
there: the notice spans the card's width, and names the model's id. No template changed; the
hash stands.

Changed 2026-10-26 (the AI day cap's stated boundary): `_macros.html` gained `resets()`, the
AI cap's reset time drawn on Settings' AI card and an AI control's day-cap reason; this page
draws neither (the Ask in words row's reason is `_ai.html`'s, which draws it only when the cap
refuses). No region changed; the hash written again.
Templates sha256 before: `349c79d5fc231b26e745688fe88c841469002b80489f4da916c422becd603324`.

Compared again 2026-10-26 (the operator's Ask-in-words walk, C1804 and C1805): the "No lines in
range" state, when a text filter is set, gains one muted line, "No line contains “<text>”: this
may not match how the platform logs it. A mnemonic names an event as the device logs it.", and
no longer calls the empty answer "an answer, not a gap" (its range line keeps what Loki keeps);
with no text filter it reads as before. `_history_ask_words.html`'s filled notice says how the
words' period was read ("Read as … (7 days; … UTC)"), before the named span's midnight when
there is one. The page's shots at 1440, 1280 and 390 retaken
(`tests/test_board_shots.py::test_history_ask_logs`): the line sits under the state's first, as
its others do; nothing else moved. **Corrected the same evening:** the board shots this
paragraph first said were beside the page were the shot server's 404 page, as
`QueryBuilderLogs3*.dc.html` were missing from the canvas copy (the shots now refuse a missing
board, C1818), so this compared the page with this record's description only; the comparison
with board F3 itself is below. The empty state's new line is a deviation (log: F3 logs builder:
a zero resting on text).

Compared again 2026-10-26 (the operator's walk of History › Query that day, items 3 and 9 to
12). Shots: `tests/test_board_shots.py::test_history_ask_logs` (the counts question, the Lines
view, the three states, Reveal…, and a new state, `history-ask-logs-leftovers`, at 1440 and
390: a kind and a device the range does not hold, and LINK-3-UPDOWN chosen while the text
names OSPF-5-ADJCHG) and `test_history_ask_words_logs` (a new state, `left`, at 1440 and 390:
Ask in words refused after a fill). Board F3's files (`QueryBuilderLogs3*.dc.html`) were not
in the canvas copy the shots read, so the regions were compared with this record's own
description of the board (the Board column below) and with 8.1's `AskWords.dc.html`, which
was. What moved:
- **Scope first** (item 12): Range is the third row, after Start from, then Kind, Devices,
  Severity, Mnemonic, Text, Show and the query; the board draws Range after the query. The
  devices are read for the kinds chosen. A kind, device or mnemonic chosen that the range no
  longer holds is kept, its chip on, marked "not seen in this range".
- **Left from your previous question** (item 3): when Ask in words does not fill (refused, a
  question back), the builder is marked (a notice under the row with **Keep these choices**,
  the query box outlined and labelled) and Ask is off until kept or a choice changes.
- **Filters that cannot match together** (item 11): a warning row above the query, its first
  button dropping the leftover.
- **One zone per view** (item 10): every time on the page (the answer's title, its timing,
  the legend's last window, the Lines view's times under a Time head naming the zone, the hints' read
  times, the labels' first lines, the bounds' read) is written in the browser's zone, named,
  with UTC on hover; the chart's axis was already the browser's.
- **Counts over their windows** (item 9): each count is drawn over the window it counts, the
  title spans the whole windows to the range's last close, and a day's window names both
  dates; a point's lines name the window in the viewer's zone, UTC on hover.
Every other region is as it was. The hash written again.
Templates sha256 before: `55c06cb14689dd3673f9703d1e011c0920df4a35f828e48f9f4edadff08ae26a`.

Compared again 2026-10-26, against board F3 itself (the operator, the same evening: the boards
found and restored, never compared by description alone). `QueryBuilderLogs3.dc.html` and
`QueryBuilderLogs3Phone.dc.html` were never committed to git; they are in the mockups canvas's
`project/` folder, now copied whole into the shots' folder (the shots refuse a missing board,
C1818). Shots: `tests/test_board_shots.py::test_history_ask_logs`, the board at 1440, 1280 and
390 beside the page as merged (the walk's fixes and the builder's items 3 and 9 to 12), each
board shot opened and seen to be the board. Region by region, the verdicts below hold as the
two paragraphs above wrote them from the description: the board draws Range after the query
and the page third (log: History › Query: scope first); the board's Kind is syslog, SNMP traps,
both, and the page's the job values (log: F3 logs builder: the Kind row); the board's chart
title and Lines times are UTC, the page's the browser's zone (log: History › Query: one zone
per view); the board's legend ends "Last line", the page's "Last window with a line" (log:
History › Query: counts over their windows); the board has an Authorisations tab, the page none
(log: F3 logs builder: History's tabs); the board's Save…, the page's Save this view… (log: F3
logs builder: the actions' words). The board's States card draws "No lines in range" with
"an answer, not a gap" and a text filter set; the page now says the text may not be how the
platform logs it (log: F3 logs builder: a zero resting on text), and the States row's verdict
is a deviation from here on. The board's fidelity and shell notes are the board's annotations,
not regions. Nothing else differs.
Templates sha256 before: `a381aab442c1677d3ba86d6a2618d928a601aa2be6183f7f98c29468f65af1ce` (the
builder's items alone) and `a972426cedf78abb2e1b8e5bb6c5789b242f54442a13515215ddfe87abaf0ffd`
(the walk's fixes alone), each written before the two were merged.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Tabs | Timeline, Query, Baselines, Authorisations; Query on | Timeline, Query, Baselines; Query on | **deviation** (log: F3 logs builder: History's tabs) |
| Head | "Ask your own ‹ back to the questions"; Source (Metrics, Logs) and Mode (Builder, Code) switches | the same; Metrics opens the metrics builder (E3, shared head) | **same** |
| Ask in words | 8.1's board (`AskWords.dc.html`), its logs state: the row, its example a logs question, filled (model, cost, the call in History, the lines the test run matches) | a question, Fill the builder busy on itself, "How does this work?"; the result's notice under it; the AI mark; disabled with its reason (and the AI card's link) while hosted AI cannot answer; each notice the card's width, the model's id beside its name; not filled, the builder marked left from the previous question (Keep these choices, the query box outlined, Ask off until kept or changed) | **deviation** (log: 8.1 Ask in words: the notices); (log: History › Query: left from your previous question) |
| Start from | four chips, the one the choices match marked | the same four, each setting every choice; marked when the choices are exactly its own | **same** |
| Kind | syslog, SNMP traps, both; the job names and when read in the hint | the `job` label's values over the range as switches (one or more) and every job; how many and when read in the hint; after Range; a kind chosen the range does not hold kept on, marked "not seen in this range" | **deviation** (log: F3 logs builder: the Kind row); (log: History › Query: not seen in this range) |
| Devices | chosen chips with ×, + device, by role, all N; "by the device label, never a regex" | the same; + device asks a name from the values Loki holds; the hint says label or line, with the label's first line; read for the kinds chosen; a device chosen the range does not hold kept, marked "not seen in this range" | **deviation** (log: F3 logs builder: devices before the label began); (log: History › Query: not seen in this range) |
| Severity | "at or worse than" and a select | the same, any severity or 0 to 7; the hint says label or the mnemonic's digit | **same** |
| Mnemonic | chips from the store for the chosen devices, + more | the same, from Mercury's logs reader's counts, the most frequent four and + N more; a mnemonic chosen the range does not hold kept, marked "not seen in this range" | **deviation** (log: History › Query: not seen in this range) |
| Text | contains, excludes | contains, an "any case" checkbox, excludes | **deviation** (log: History, Ask your own (logs): the Text filter's any-case choice) |
| Show | Lines or Counts over time; per device or per mnemonic; every 5 minutes or 1 hour | the same switch; per device, per mnemonic or per any label Loki holds; every 1 minute to 1 day | **deviation** (log: F3 logs builder: the Show row's choices) |
| The query | the dark box, the last choice marked and repeated, the plain sentence | the same; Mercury's heartbeat stage drawn in it; above it, filters no line can match together warned, the first button dropping the leftover | **deviation** (log: F3 logs builder: the heartbeat stage); (log: History › Query: filters that cannot match together) |
| Edit as code | "Edit as code hands it to Code mode" | the link, to today's box with the LogQL; a count query drawn there on the same chart (C819) | **deviation** (log: F3 Edit as code: counts drawn in Code mode) |
| Range | 1 h, 24 h, 7 days, 30 days, From… to… (E3's picker) | the same chips; From… to… opens relative or absolute UTC with local beside, the fit line, Loki's and Mercury's limits, Apply, Cancel; the third row, after Start from, before Kind | **deviation** (log: History › Query: scope first) |
| Bounds | 200 a page; Loki's span, timeout, lines, series, retention, read from /config | the same, read from Loki's /config at the time drawn, ending "Lines are masked; revealing one is recorded" | **same** |
| Actions | Ask, Save…, Copy the link | Ask (busy on itself, "Asking Loki…"), Save this view…, Copy the link, the (i) | **deviation** (log: F3 logs builder: the actions' words) |
| Counts answer | title, series and timing, the step chart, legend with lines in range, most in a window, last line | the same title and timing; the Monitoring chart stepped, each count over the window it counts; the legend with lines in range, most in a window, last window with a line (both dates for a day's); every time in the browser's zone, named, UTC on hover | **deviation** (log: F3 logs builder: the counts chart); (log: History › Query: counts over their windows); (log: History › Query: one zone per view) |
| A point's lines | a tooltip over the chart with Show these lines | a box under the chart naming the series and window, with Show these lines | **deviation** (log: F3 logs builder: a point's lines) |
| Lines view | time, device, severity, kind, masked line (the masked value marked), Reveal… on a line with a masked value; 1 to 200 of N, Older › | the same columns and marks, Reveal… on each line with a masked value and on no other; Lines 1 to 200 of N, newest first, Older ›, and ‹ Newest once paged; each time in the browser's zone, the column's head naming it, UTC on hover | **deviation** (log: F3 Reveal: the Lines view's paging); (log: History › Query: one zone per view) |
| Reveal… | the button at the row's end; "asks for a reason, then shows that one line unmasked; who, when and which line are recorded in History" | the button opens a box under it asking why (Reveal, busy on itself, its (i), Cancel); the line read from Loki again, recorded, then drawn unmasked under its masked form and the box closed; a refusal said there; the record on the Timeline under Reveals (C837: every reveal kind, one filter); the hint adds the reason and "never the value" | **deviation** (log: F3 Reveal: the reason box and the revealed line) |
| States | refused by a bound, Loki not answering, no lines in range | the same three, each naming both operands, the wait, or what was sent, with its button; no lines in range with a text filter set says the text may not be how the platform logs it, never "an answer, not a gap" | **deviation** (log: F3 logs builder: a zero resting on text) |
| Phone | labels above controls, switches wrap, the chart full width, legend stacked, each line a card with its Reveal… | the same; Reveal…'s box opens inside the line's card, the revealed line under the masked one | **same** |
