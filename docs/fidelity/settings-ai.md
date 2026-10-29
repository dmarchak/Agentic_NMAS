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
Templates compared: templates/v2/_settings_ai.html, templates/v2/_settings_ai_bg.html, templates/v2/_settings_ai_on.html, templates/v2/_settings_ai_caps.html, templates/v2/_install_card.html
Templates sha256: `b6d669208a84fb722a83bb86a8125f434f3356644530c91deb75381a86ab6568`

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
| Hosted AI | the master switch with Turn off, the key with Test and Replace…, the day cap with Change…, the month figure, the prices | the AI (hosted) card, moved whole: its title and "every network"; the key with Replace…; the cap per day with No cap and the day's start, saved by Save; Hosted AI allowed with Turn off (or Allow with a reason); spent today; Save and Test; each task's model, prices and cap per call as a table, always drawn; no month figure | **deviation** (log: Settings › AI: the AI (hosted) card moved whole, its own layout) |
| No cap's confirmation and notice (2026-10-29) | not drawn (no cap was drawn without a board, 2026-10-27) | the confirmation asks for `no cap` typed and a one-line reason, kept with who and when and drawn on History; a press missing either refused in place naming each; the notice while no cap is set names who chose it, when and why | **deviation** (log: The AI card's no cap asks for a reason) |
| Features a person presses | a table with a switch per feature | not drawn | **deviation** (log: Settings › AI built: the features a person presses have no switches yet) |
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
| The estimate moved (C) | the refusal naming both estimates with their figures, ESTIMATE, NOW, Turn on again | the refusal naming both digests, the estimate now drawn in full, ESTIMATE, NOW | **deviation** (log: Settings › AI built: a moved estimate's refusal names both digests, not the shown figures) |
| A cap outside the installation's (D) | the field red with the reason, Turn on disabled | refused on press, in place, naming both amounts, what was typed drawn back | **deviation** (log: Settings › AI built: a cap out of range refused on press, not disabled before) |
| Turned on (E) | the notice: on for <network>, by whom, when, the estimate's digest and dollars, the caps, recorded | the same | **same** |
| The record line | "Records: alex@, the time, estimate 7c41e2a9 and its figures, and the caps" | the same, under the buttons | **same** |
| Change caps… | not drawn past the button | in the row's place: day and month caps with their current values, the approval's end unchanged, Save caps and Cancel | **same** |
| A fresh install (AI5) | its own board | not built | **later** (AI5, C1843) |
