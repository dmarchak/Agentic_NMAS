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
Templates sha256: `abb2651183ddb8ab878259ae909a6899e3c8f40ab39dad50ae5609cac8231684`

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

Changed 2026-10-25 again (C1724, C1740): `_history_ask_words.html` gained the metrics
builder's timezone inputs (`tz`, `tz_off`), drawn only when the including template sets
`words_tz`, and one sentence in the filled notice when a metrics answer's range is today's.
The logs builder sets no `words_tz` and its answers carry no `today`, so neither is drawn
here: the page rendered from the templates as they were and as they are is the same bytes.
No region here changed; the hash written again.
Templates sha256 before: `62b52a7e20d7effeeafeadbfe8a5c53c7e5dbff6a738ab28bd2a8f22943b715f`.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Tabs | Timeline, Query, Baselines, Authorisations; Query on | Timeline, Query, Baselines; Query on | **deviation** (log: F3 logs builder: History's tabs) |
| Head | "Ask your own ‹ back to the questions"; Source (Metrics, Logs) and Mode (Builder, Code) switches | the same; Metrics opens the metrics builder (E3, shared head) | **same** |
| Ask in words | (not drawn: 8.1 came after F3) | a question, Fill the builder busy on itself, "How does this work?"; the result's notice under it; the AI mark; disabled with its reason (and the AI card's link) while hosted AI cannot answer | **later** (8.1's board, the sprint's Saturday, PHASE8_PLAN 15.12) |
| Start from | four chips, the one the choices match marked | the same four, each setting every choice; marked when the choices are exactly its own | **same** |
| Kind | syslog, SNMP traps, both; the job names and when read in the hint | the `job` label's values over the range as switches (one or more) and every job; how many and when read in the hint | **deviation** (log: F3 logs builder: the Kind row) |
| Devices | chosen chips with ×, + device, by role, all N; "by the device label, never a regex" | the same; + device asks a name from the values Loki holds; the hint says label or line, with the label's first line | **deviation** (log: F3 logs builder: devices before the label began) |
| Severity | "at or worse than" and a select | the same, any severity or 0 to 7; the hint says label or the mnemonic's digit | **same** |
| Mnemonic | chips from the store for the chosen devices, + more | the same, from Mercury's logs reader's counts, the most frequent four and + N more | **same** |
| Text | contains, excludes | the same | **same** |
| Show | Lines or Counts over time; per device or per mnemonic; every 5 minutes or 1 hour | the same switch; per device, per mnemonic or per any label Loki holds; every 1 minute to 1 day | **deviation** (log: F3 logs builder: the Show row's choices) |
| The query | the dark box, the last choice marked and repeated, the plain sentence | the same; Mercury's heartbeat stage drawn in it | **deviation** (log: F3 logs builder: the heartbeat stage) |
| Edit as code | "Edit as code hands it to Code mode" | the link, to today's box with the LogQL; a count query drawn there on the same chart (C819) | **deviation** (log: F3 Edit as code: counts drawn in Code mode) |
| Range | 1 h, 24 h, 7 days, 30 days, From… to… (E3's picker) | the same chips; From… to… opens relative or absolute UTC with local beside, the fit line, Loki's and Mercury's limits, Apply, Cancel | **same** |
| Bounds | 200 a page; Loki's span, timeout, lines, series, retention, read from /config | the same, read from Loki's /config at the time drawn, ending "Lines are masked; revealing one is recorded" | **same** |
| Actions | Ask, Save…, Copy the link | Ask (busy on itself, "Asking Loki…"), Save this view…, Copy the link, the (i) | **deviation** (log: F3 logs builder: the actions' words) |
| Counts answer | title, series and timing, the step chart, legend with lines in range, most in a window, last line | the same title and timing; the Monitoring chart stepped; the legend with lines in range, most in a window, last window with a line | **deviation** (log: F3 logs builder: the counts chart) |
| A point's lines | a tooltip over the chart with Show these lines | a box under the chart naming the series and window, with Show these lines | **deviation** (log: F3 logs builder: a point's lines) |
| Lines view | time, device, severity, kind, masked line (the masked value marked), Reveal… on a line with a masked value; 1 to 200 of N, Older › | the same columns and marks, Reveal… on each line with a masked value and on no other; Lines 1 to 200 of N, newest first, Older ›, and ‹ Newest once paged | **deviation** (log: F3 Reveal: the Lines view's paging) |
| Reveal… | the button at the row's end; "asks for a reason, then shows that one line unmasked; who, when and which line are recorded in History" | the button opens a box under it asking why (Reveal, busy on itself, its (i), Cancel); the line read from Loki again, recorded, then drawn unmasked under its masked form and the box closed; a refusal said there; the record on the Timeline under Reveals (C837: every reveal kind, one filter); the hint adds the reason and "never the value" | **deviation** (log: F3 Reveal: the reason box and the revealed line) |
| States | refused by a bound, Loki not answering, no lines in range | the same three, each naming both operands, the wait, or what was sent, with its button | **same** |
| Phone | labels above controls, switches wrap, the chart full width, legend stacked, each line a card with its Reveal… | the same; Reveal…'s box opens inside the line's card, the revealed line under the masked one | **same** |
