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
Templates compared: templates/v2/_settings_ai.html, templates/v2/_settings_ai_bg.html, templates/v2/_settings_ai_on.html, templates/v2/_settings_ai_caps.html
Templates sha256: `c74afd89b38886c5c31c9ba9d2d926cf5731ecf7a38e3d06120a0c6ed751b59a`

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
| Hosted AI | the master switch with Turn off, the key with Test and Replace…, the day cap with Change…, the month figure, the prices | a card naming hosted AI's state, by whom, when and why, and the day cap, read-only, linking to the AI (hosted) card on Connections | **deviation** (log: Settings › AI built: the AI (hosted) card not moved yet) |
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
| The acceptance | "I have read the estimate. Approvals last 14 days; Mercury asks for this again before 10 Nov." | "I have read the estimate. An approval lasts 14 days: this one ends <date>, and the feature then stops until an admin turns it on again." | **deviation** (log: Settings › AI built: no Needs attention row before an approval ends) |
| Turn on and Cancel | "Turn on with this estimate" or "Turn on with no measured estimate", Cancel | the same | **same** |
| The estimate moved (C) | the refusal naming both estimates with their figures, ESTIMATE, NOW, Turn on again | the refusal naming both digests, the estimate now drawn in full, ESTIMATE, NOW | **deviation** (log: Settings › AI built: a moved estimate's refusal names both digests, not the shown figures) |
| A cap outside the installation's (D) | the field red with the reason, Turn on disabled | refused on press, in place, naming both amounts, what was typed drawn back | **deviation** (log: Settings › AI built: a cap out of range refused on press, not disabled before) |
| Turned on (E) | the notice: on for <network>, by whom, when, the estimate's digest and dollars, the caps, recorded | the same | **same** |
| The record line | "Records: alex@, the time, estimate 7c41e2a9 and its figures, and the caps" | the same, under the buttons | **same** |
| Change caps… | not drawn past the button | in the row's place: day and month caps with their current values, the approval's end unchanged, Save caps and Cancel | **same** |
| A fresh install (AI5) | its own board | not built | **later** (AI5, C1843) |
