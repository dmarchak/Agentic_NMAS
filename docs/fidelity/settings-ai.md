# Fidelity: Settings › Installation › AI, the background features (2026-10-27)

Boards: `SettingsAi.dc.html` (AI3, 1440) and `SettingsAiOn.dc.html` (AI3b, 1440), the mockups
canvas's page "C1843: AI cost safety", versions 159 to 164, signed off under the Phase 7 mode
2026-10-27 (docs/STANDING_APPROVAL_LOG.md, "Boards AI1 to AI5"). Their grey notes are notes for
the builder.

Shots: `tests/test_board_shots.py::test_settings_ai` (`settings-ai` at 1440, 1280 and 390,
Branch with the fake feature on and `sdn_classify` off; `settings-ai-on` at 1440 and 390, Turn
on… pressed on `sdn_classify`, its frequency unknown; `settings-ai-on-refused` at 1440 and 390,
a day cap of $8.00 against the installation's $1.50), on tests/test_settings_ai_v2.py's world.
The states the shots do not draw (stopped by a cap, approval ended, a moved estimate, Turn
off's and Change caps' answers) are compared by the templates and that file's tests.
Templates compared: templates/v2/_settings_ai.html, templates/v2/_settings_ai_bg.html, templates/v2/_settings_ai_on.html, templates/v2/_settings_ai_caps.html, templates/v2/_install_card.html, templates/v2/_settings_ai_troubleshoot.html, templates/v2/_settings_ai_audit.html
Compared again 2026-11-13 (the operator's approved rules: "“Manual” capitalised", "money shown as $", "“The day begins at” as a time-zone picker"): in `_install_card.html`, the AI troubleshooting card's AI mode draws "Manual" and "Off" (the option's value stays the stored `manual` or `off`; a choice with no words is drawn as stored, as before); a field that takes an amount (Cap per day, AI spend per incident) draws its "$" inside the field and its value to the cent ("1.50" where it drew "1.5"); the prices table and Spent today draw through the `usd` filter ("$0.10 / $0.50" where it drew "$0.1 / $0.5", "$0.00" where it drew "$0.0000"); and The day begins at is the one zone picker (`_macros.zone_picker`: the viewer's own zone first, then UTC, then every zone the host holds) with "midnight in <zone>: next <the instant>" beside it, through `clock`. `_settings_ai_bg.html`, `_settings_ai_caps.html` and `_settings_ai_on.html` draw each cap, estimate and spend through the same filter, and their cap fields carry the "$". Boards AI3 and AI3b draw the amounts their own way and the day's start as typed text: **deviation**, logged (docs/STANDING_APPROVAL_LOG.md: "Money through one formatter", "AI mode reads Manual and Off", "The day begins at is the zone picker"). No element moves but the picker's line, and no region's verdict in the table moved; compared by the templates' diff and from new shots at 1280 (~/Documents/nmas-reports/captures/gui-overnight-2/fixes/1-settings-ai-before.png and -after.png). Templates sha256 before: `4be2bd09e581b39d075af5be18677488dccf781d43c3e8d0a85bf0fae47a4efe`.
Compared again 2026-11-15 (C3748): Turn on…'s form for automatic AI troubleshooting opens in
place under the control strip's AI switch as well, posting the same route with
``answer=strip``, its Cancel redrawing the strip; the offered caps' amounts are said beside
"offered" ("twice the estimate ($X a day)", the month's). Compared by the template's diff and
tests/test_heal_batch.py's strip, not by new shots; logged once (docs/STANDING_APPROVAL_LOG.md,
"Board G2: the control strip and Turn on self-healing and fix all (C3748, C3749, G6)").
Templates sha256 before: `71d377d15402ab7bf8c14c57bb4e6342bebb311e63f2a3133a16200e5d1e37f2`.
Compared again 2026-11-15 (Gate 2, C3769; board G2b): the AI troubleshooting card for one
network, `_settings_ai_troubleshoot.html`, joins the compared templates, drawn at the top of
`_settings_ai_bg.html`'s section; automatic AI troubleshooting's row leaves the list (its Turn
on… form opens in the card for audit, the same form) and the retired analysis's row is drawn
only while on. Compared by the templates' diff and tests/test_ai_troubleshoot_control.py's
pages, not by new shots. Templates sha256 before (without the card):
`61170c38df4e5ee1ff677024522a43dee4028acd6bb50c62d3bdf86c53c32553`.
Compared again 2026-11-15 (Gate 2's follow-up, C3769): automatic AI troubleshooting's list
for audit is its own read-only template, `_settings_ai_audit.html` (no tick, no cap typed, no
Turn on; Close), the catch-up block leaves `_settings_ai_on.html`, Turn on…'s answer no longer
lists a catch-up, and the card's estimate says the calls a day are unbound and the cost per call
acknowledged. Compared by the templates' diff and tests/test_ai_troubleshoot_control.py's
pages, not by new shots; logged (docs/STANDING_APPROVAL_LOG.md, "The list Automatic would
start on is read-only (C3769)"). Templates sha256 before:
`4cc8bd32d8dd46cca723eb4d03dfa0013f00036ffc7e0f0390912c05263582ac`.
Compared again 2026-11-15 (the combined gate's review fixes): the templates' one change is the
AI troubleshooting card's comment, naming the control's module where it now lives
(modules/troubleshoot_control.py); nothing drawn changed. Compared by the templates' diff, not
by new shots; every region's verdict unchanged. Templates sha256
before: `4b67b9c4c81588d474078206c80d8d091d617f7454c3666c5a3e6947acc7fc65`.
Compared again 2026-11-15 (the manual's check of controls named only by data): each of the
AI troubleshooting card's Off, Manual and Automatic buttons says on hover what it sets, "AI
troubleshooting: Automatic, …" where it said "Automatic: …"; and Turn on…'s form names its
route in its own `action` and `hx-post` again, where a variable held it (the same address, so
tests/test_route_reachability.py sees the page reach it). Nothing drawn moved. Compared by the
templates' diff, not by new shots; every region's verdict unchanged. Templates sha256 before:
`8f939df5d3d38ce3b1caa5b0cb4f82691b308211730287ee98cd344d1444b6ba`.
Compared again 2026-11-18 (the skip-mode debt, docs/FAST_LANE_DEBT.md; 7b0bb884, C3890, "Mercury sets no AI size limit of its own"): in `_install_card.html` the prices table's last column is "Typical cost per call (measured)", each amount the task's measured typical cost with "(not measured yet)" beside it until measured, its hover the basis and "no call has a cap of its own: the spending limits are the only governor", and the model's hover its context window and maximum output, where the column was "Cap per call", the worst case at the task's prompt bound; `_settings_ai_audit.html` carries the least cost, not the worst, to its fit line (a data attribute, nothing drawn). Shot again from this tree (`settings-ai` at 1440, 1280 and 390; `settings-ai-on` and `settings-ai-on-refused` at 1440 and 390, tests/test_board_shots.py's `test_settings_ai`) and read region by region against this record's verdicts: the Hosted AI row's Built moves (the column) and stays a deviation, now naming its second log line; every other verdict stands. The boards are the canvas's, not on disk, so they were not re-shot. Findings in the words, not the layout (registered by the debt pass): the cap per day's note still says "each call's own cap is its task's", and the AI troubleshooting estimate's cost per call "its pin's 27,000 prompt tokens and 5,760 answer tokens stand in", each a per-call bound 7b0bb884 removed. Logged (docs/STANDING_APPROVAL_LOG.md, "AI cost words: a call's typical cost, not a per-call cap"). Templates sha256 before: `489c620f8efa0996c539f6e2a04bf7e217d5459fb539fba1fc08c0be903981f8`.
Compared again 2026-11-18 (the skip-mode debt's carried-fields pass, 07239059): in `_install_card.html` the prices table's last column header is drawn from the rows' `cap_label` (`profiles.PER_CALL_LABEL`, "typical cost per call (measured)", capitalised), where the same words were typed into the header. It falls back to those words when there is no row. The header reads "Typical cost per call (measured)" as before, nothing drawn moves, and no region's verdict changes. This was compared by the template's diff and the label's value, not from new shots. Templates sha256 before: `1e7d60accc8653364803adfd2c643b7dd2da321964c652efd4688d5699ea74cd`.
Compared again 2026-11-24 (the week plan's Stage 5, every setting's description): `_install_card.html` draws one line under each field (a switch, a choice, the zone picker, an amount), under the secret's Replace… row and under the Hosted AI and Writes allowed rows, what the setting does in plain words, from `settings_schema.DESCRIPTIONS` through `_macros.setting_desc`; `_settings_ai_bg.html` draws the per-network background features' line under its heading. Nothing else moves and no region's verdict changed. Boards AI3 and AI3b draw no such line: a deviation, logged once (docs/STANDING_APPROVAL_LOG.md, "Settings: every setting's description"). Compared by the templates' diff and tests/test_settings_descriptions.py's render, not by new shots. Templates sha256 before: `2a31b01f4f0505a7119b0a1bd39542d8681052b937fa43415ca255cd698bbaaa`.
Compared again 2026-11-24 (C2820's survey, item 25, the human-readable pass): `_settings_ai_bg.html`'s turned-on, turned-off, already-off and caps notices ("On for Branch: Self-healing analyses what it could not fix", "Turned off for Branch: …", "Caps set on Branch for …: now $1.00 a day …") and `_settings_ai_on.html`'s heading ("Turn on: <words> · network Branch") name the feature by its words (the `ai_feature` filter over `background.FEATURES`' words, the ones each feature's row already draws), its key on hover, where they drew the key as the text or in monospace. No element moves and no region's verdict changed; compared by the templates' diff, not by new shots (the boards are not on this machine). Logged once (docs/STANDING_APPROVAL_LOG.md, "C2820 item 25: Settings › AI names features, not keys"). Templates sha256 before: `a93ad76e66abe46921d7bbae1eeee58d37d0d580abd52520068b0887d62d0465`.
Compared again 2026-11-26 (C4278): text drawn with a capital first letter goes through `capital` (`words.capital`), never Jinja's `capitalize`, which lowered every letter after the first (a person's reason, a network's or product's name). No region moves; every verdict is unchanged. Templates sha256 before:
`7cb5d5f6cdac07f65705905aff36ce1f6a440d1671eb9e14dddf2599f54e8f9e`.
Templates sha256: `23196ccfcb7d9500e2b6e639328d1d168ae5453fe4702f95fd7c79340ef9c85f`

**Compared again 2026-11-15 (C3745, every cap counted at the catch-up):** in `_settings_ai_on.html`, the list's region adds one line under the incidents: what fits under the caps ("2 of the 4 ticked fit under the caps; the later 2 would pass this feature's day cap: …", or "All 4 ticked fit under every cap.") and the room under each (the day cap left today, this feature's day and month caps as typed), redrawn as the ticks or the typed caps change; each checkbox carries whether its incident's cap allows it, and the note under the list names the feature's caps. No region moved; the list's row above stands as a deviation, logged with it. Compared by the template's diff and tests/test_fixit_catch_up.py's real-browser test of the typed caps. Templates sha256 before: `c497a3b6b25cb90b66a46c1473c8b7dbe75b72e7d38e625326ab0ece2c3edb24`.

**Compared again 2026-11-15 (C3732, the operator's catch-up at turn-on):** in `_settings_ai_on.html`, Turn on… for `fixit_auto` only draws a new region inside its form above the caps: the open incidents it starts on, each a ticked row with its device, title (a link to its page), why and estimate, the line "Starts on these N open incidents, about $X" redrawn by the ticks (nmas_apply.js `catchUpSelect`), and the caps' note; "No open incident to start on" when none; the record line adds "and which open incidents you ticked and left unticked". In `_settings_ai_bg.html`, the turned-on notice adds what started, what a cap stopped, and how many were left unticked. Every other feature's Turn on… is unchanged, and no other region moved. Board AI3b draws no list: **deviation**, logged (docs/STANDING_APPROVAL_LOG.md: "Settings › AI: Turn on… for automatic AI troubleshooting lists the open incidents it starts on (C3732)"). Compared by the templates' diff and tests/test_fixit_catch_up.py's real-browser test of the ticks and the total, not a new shot. Templates sha256 before: `dd8481d59c02e2bc0cfc746590f0d2234b9c3456799c4b607290cda7bfb4b518`.

**Compared again 2026-11-12 (local times, docs/UI_RULES.md "One time zone per screen"):** in `_settings_ai_bg.html`, `_settings_ai_caps.html` and `_settings_ai_on.html`, an approval's end, the estimate's measured time and an approval's end day are `_macros.clock`'s: the viewer's own time (or day), drawn by the server in their kept zone, the zone named once on the screen, the UTC instant on hover, in the same element and position; the day cap's reset keeps its UTC and the boundary zone's time on its hover in place of "(… UTC)" beside it. Compared by the templates' diff, not a new shot; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times"). Templates sha256 before: `56f1640c85c6296c15d7eb814dde4956d93f947af49d32bcf8077455800007c5`.

**Compared again 2026-11-11 (board E2a, display names):** by the templates' diff against the
regions below, not from new shots. In `_settings_ai_bg.html` and `_install_card.html`, each
place that draws a person (who turned a feature on or off or changed its caps, who allowed or
turned off hosted AI, who saved, replaced or chose a card's value) now draws them through the
`people` filter, by display name (the name the person set, else the part of their identity
before the "@"), in the same element and position; no region is added, removed or moved, and no
other word changes. Where the board draws an identity the built screen draws the name, a
deviation logged once for every screen (log: Display names: a person is drawn by display name
on every screen). Every other verdict stands.

**Compared again 2026-10-29 (the operator's order of that day, item 5: no cap asks for a
reason):** `_install_card.html`'s no-cap confirmation adds a one-line Reason field beside the
typed words and says the reason is kept; a refused press names each part missing; the Saved
notice ends with the reason; the notice while no cap is set names who chose it, when and why.
None of these states is in a shot (the shots' world has a $1.50 cap): they are compared by the
template and tests/test_ai_day_cap.py, and a row is added below. Shots `settings-ai` at 1440,
1280 and 390 and `settings-ai-on` taken again from this tree: the card with a cap set is
unchanged. Templates sha256 before:
`24fb5260b3c1bde4518dcaa461de14377e3ba6eb9695776b0f944c8ef5f21e8e`.

**Compared again 2026-10-28 (C1953 part 1, decision 1: the AI (hosted) card moved here
whole):** the read-only Hosted AI card is gone, and the AI (hosted) card is the tab's first
card, drawn by `_install_card.html` as on Connections (now a compared template here, since this
tab draws it); Connections keeps one line linking to it (`settings_installation.html`, on the
UNCHECKED list). The hosted-off notice in Background features names "the AI (hosted) card
above". Shots `settings-ai` at 1440, 1280 and 390 (`settings-ai-page-390-first.png`: the card
stacks at phone width, nothing past the width). The Hosted AI row below is re-judged; the other
regions are unchanged in the shots. Templates sha256 before:
`c74afd89b38886c5c31c9ba9d2d926cf5731ecf7a38e3d06120a0c6ed751b59a`.

**Compared again 2026-10-28 ~22:5x UTC (C1953 part 6, decision 5: an approval asked for again
3 days before it ends):** the acceptance in Turn on… now says "this one ends <date>. Mercury
asks for it again in Needs attention 3 days before; unless an admin turns it on again, it then
stops." (shot `settings-ai-on-page-1440` and `-390`), which is the board's sense, so its row
below is now **same**. An on or stopped feature's row, from 3 days before its approval ends,
adds ", within 3 days: turn it on again to approve it for another 14, or it stops then" after
"approval until" and **Turn on again…** before Change caps…, which board AI3 does not draw (a
row added below). The shots' world has a fresh approval, so Turn on again… is not in a shot; it
is compared by the template and tests/test_settings_ai_v2.py
(`test_turn_on_again_is_on_the_row_only_within_three_days_and_renews`). The other shots taken
again, nothing else moved. Templates sha256 before:
`80932fba152fc46500163d11c9baedd1e0a0225b1bf400c95970caac7990c742`.

**Compared again 2026-10-28 (PHASE8_PLAN 16.11 item 1, board FB):** `_settings_ai.html`
includes the card Answers said wrong (`_ai_feedback_review.html`) below Background features, as
board FB draws it. The card is compared in its own record, docs/fidelity/ai-feedback.md, from
`tests/test_board_shots.py::test_ai_feedback` (which shoots this tab); the tab's other regions
are unchanged in those shots. Templates sha256 before:
`5fdbced7cfbf8530f9ae1db626f5c64c518f300c4d0b69b0614ec8633fa0f118`.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Where it is | "Settings · AI", a tab beside Installation, Integrations and Networks | Settings › Installation's last tab, AI, under the scope bar | **deviation** (log: Settings › AI built: the AI tab is a tab of Settings › Installation) |
| Hosted AI | the master switch with Turn off, the key with Test and Replace…, the day cap with Change…, the month figure, the prices | the AI (hosted) card, moved whole: its title and "every network"; the key with Replace…; the cap per day with No cap and the day's start, saved by Save; Hosted AI allowed with Turn off (or Allow with a reason); spent today; Save and Test; each task's model, prices and measured typical cost per call as a table, always drawn ("(not measured yet)" until measured; it was the cap per call until 7b0bb884); no month figure | **deviation** (log: Settings › AI: the AI (hosted) card moved whole, its own layout), and for the column, "AI cost words: a call's typical cost, not a per-call cap" |
| AI troubleshooting (2026-11-12, C3193) | not drawn (the incident's AI troubleshooting came later, board recurring-fixes v2) | a second card under AI (hosted), drawn by the same card template: AI mode (manual or off) and AI spend per incident ($1.00 by default, a positive amount, no "no cap"), each with its note, saved by Save and recorded old and new; the templates are unchanged (one more entry in the cards' table) | **deviation** (log: Board recurring-fixes v2 built, 9) |
| No cap's confirmation and notice (2026-10-29) | not drawn (no cap was drawn without a board, 2026-10-27) | the confirmation asks for `no cap` typed and a one-line reason, kept with who and when and drawn on History; a press missing either refused in place naming each; the notice while no cap is set names who chose it, when and why | **deviation** (log: The AI card's no cap asks for a reason) |
| Features a person presses | a table with a switch per feature | not drawn | **deviation** (log: Settings › AI built: the features a person presses have no switches yet) |
| AI troubleshooting on a network (Gate 2, C3769) | board G2b (g2-control-strip.html part 5): Off / Manual / Automatic, the spending limits with the estimate beside them and its acknowledgement, "What would Automatic start, and why…" | the same, `_settings_ai_troubleshoot.html`, at the top of the background section; the three levels one segmented control | **deviation** (log: Settings › AI's AI troubleshooting card built from board G2b (C3769)) |
| Background features' head | "Background features", Network ▾, "How does this work?" | the same; the (i) opens the manual's section | **same** |
| Their lead | the board's sentence | the same sentence, with the approval's 14 days added | **same** |
| A feature's row | a table row: the feature with its state chip, who, when and "approval until"; trigger; caps with today and the month; estimate against actual; Change caps…, Turn off or Turn on… | the same five parts as a row of a list, each control busy on itself with its (i), stacked at phone width | **deviation** (log: Settings › AI built: each feature a row of five parts, stacked at phone width) |
| States | on, off; stopped by a cap in a notice for another network | off, on until its date, stopped by its day or month cap, approval ended; the other network's stopped feature in a notice under the list | **same** |
| Who sees amounts | a per-network choice | not drawn | **deviation** (log: Settings › AI built: who sees amounts not built) |
| Spend history | a card linking to History › AI calls | not drawn | **deviation** (log: Settings › AI built: the spend history card and the first-install steps not drawn) |
| Turn on…: head and trigger | "Turn on <feature> · network <name>", the trigger, the model, nothing calls until turned on | the same, the feature's key before its words | **same** |
| The estimate | ESTIMATE, calls a day, cost per call, dollars a day and a month, where each comes from, prices' date, the provider bills, the digest | the same, each basis Mercury's own words, the label "an estimate, not a measurement of this feature's spend" | **same** |
| An unknown frequency (B) | "unknown", the cost's worst case, "the caps below are the bound", $0.50 and $5.00 filled in | the same words; the cap fields empty with "type a cap" | **deviation** (log: Settings › AI built: no caps offered with no measured estimate) |
| The caps | day cap "within the installation's $5.00", month cap "within $155.00 this month" | day cap within the installation's day cap; the month cap "US dollars in a month, this feature on <network> only" | **deviation** (log: Settings › AI built: the month hint names only the feature's own month) |
| The acceptance | "I have read the estimate. Approvals last 14 days; Mercury asks for this again before 10 Nov." | "I have read the estimate. An approval lasts 14 days: this one ends <date>. Mercury asks for it again in Needs attention 3 days before; unless an admin turns it on again, it then stops." (the board's sense, with the date in full) | **same** |
| An approval ending | not drawn on the row (the board's acceptance says Mercury asks again before it ends) | from 3 days before the end, "within 3 days: turn it on again…" after "approval until", and Turn on again… on the row, opening the current estimate in place | **deviation** (log: Settings › AI: Turn on again… on a feature whose approval ends within 3 days) |
| Turn on and Cancel | "Turn on with this estimate" or "Turn on with no measured estimate", Cancel | the same | **same** |
| Turn on… for automatic AI troubleshooting: the open incidents it starts on (2026-11-15, C3732) | not drawn (the catch-up came later, the operator's 2026-11-15 design) | above the caps, each open incident R1 would have started on, ticked, with its device, title, why and estimate; "Starts on these N open incidents, about $X" following the ticks; "No open incident to start on" when none; the turned-on notice says what started and what a cap stopped | **deviation** (log: Settings › AI: Turn on… for automatic AI troubleshooting lists the open incidents it starts on (C3732)) |
| The estimate moved (C) | the refusal naming both estimates with their figures, ESTIMATE, NOW, Turn on again | the refusal naming both digests, the estimate now drawn in full, ESTIMATE, NOW | **deviation** (log: Settings › AI built: a moved estimate's refusal names both digests, not the shown figures) |
| A cap outside the installation's (D) | the field red with the reason, Turn on disabled | refused on press, in place, naming both amounts, what was typed drawn back | **deviation** (log: Settings › AI built: a cap out of range refused on press, not disabled before) |
| Turned on (E) | the notice: on for <network>, by whom, when, the estimate's digest and dollars, the caps, recorded | the same | **same** |
| The record line | "Records: alex@, the time, estimate 7c41e2a9 and its figures, and the caps" | the same, under the buttons | **same** |
| Change caps… | not drawn past the button | in the row's place: day and month caps with their current values, the approval's end unchanged, Save caps and Cancel | **same** |
| A fresh install (AI5) | its own board | not built | **later** (AI5, C1843) |
