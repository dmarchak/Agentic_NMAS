# Fidelity: the top bar's AI chip and the spend panel (C1843, 2026-10-28)

Boards: `AiChip.dc.html` (AI1, 1440: the chip's eight cases) and `AiSpendPanel.dc.html` (AI2,
1440: the panel opened from the chip, its Needs attention rows, the unreadable and amounts-hidden
panels), the mockups canvas's page "C1843: AI cost safety", versions 159 to 164, signed off
under the Phase 7 mode 2026-10-27 (docs/STANDING_APPROVAL_LOG.md, "Boards AI1 to AI5"). Their
grey notes are notes for the builder.

Shots: `tests/test_board_shots.py::test_ai_spend` on tests/test_settings_ai_v2.py's world (hosted
AI allowed, a $1.50 day cap, a key set, the fake feature on for Branch through the real route,
$0.80 spent today by the viewer, another person, an evaluation run and the feature): `ai-chip`
at 1440, 1280 and 390 beside AI1; `ai-spend` (the panel opened by a click) at 1440, 1280 and 390
beside AI2; and page shots alone of the chip red (80%), with no day cap, AI off, and the panel
with the record unreadable. Below 488 px a shot holds the page to the phone's width as a column
inside a wider window, so its media queries are the window's: the chip's phone forms and every
other item's are measured instead by tests/test_v2_layout_in_a_browser.py
(`test_the_ai_chip_fits_at_its_widest_and_its_panel_opens_on_the_screen`, 320 to 1280 px, with
In progress and Update available at their widest), and the words of every state by
tests/test_ai_spend_v2.py.
Compared 2026-10-28. Compared again ~11:2x UTC: the chip's mark renamed `ai-chip-mark` (the
same rules; `ai-mark` is the AI control mark's, and the two had collided, failing
test_ask_in_words_with_hosted_ai_off_in_a_browser in the gate); the shots taken again
(ai-chip-*, ai-spend-*), nothing moved.
Templates compared: templates/v2/_ai_chip.html, templates/v2/_ai_spend.html, modules/ai/spend_view.py
Templates sha256: `1466e1a955a6ae153f8352b0152c5eb4e0e39bf57db1eb59b78faca1c4620d9f`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Where the chip is (AI1) | in the top bar of every page, after the integrations strip and before Live | the same, in base.html's bar, so every v2 page carries it | **same** |
| Neutral (AI1 case 1) | the mono "AI" mark, "$0.42 today · 0 background on", neutral, a pill | the same | **same** |
| Its hover (AI1 case 1) | "$0.42 in 9 calls since 00:00 UTC (the day cap's boundary), of the day cap $5.00 (8%). Read from the record of AI calls 4 s ago, priced from Mercury's table as of 2026-10-01; the provider bills what is spent." | the same words, "since midnight <zone>" and the read's clock time in UTC in place of its age | **same** |
| Amber and red (AI1 cases 2 and 3) | amber from 50% of the day cap, red from 80% | the same thresholds (`spend.WARN_AT`), the same colours from the tokens, dark values included | **same** |
| No day cap (AI1 case 4) | neutral, "no cap" beside the figure | the same | **same** |
| AI off (AI1 case 5) | grey "AI off"; on hover who turned it off and when | grey "AI off"; on hover which is off (hosted AI not allowed, or no key), where it is turned on, and that nothing is sent | **deviation** (log: AI chip built: AI off's hover says why, not who turned it off) |
| The record cannot be read (AI1 case 6) | red "AI spend unknown", on hover why and that every call is refused, never $0 | the same | **same** |
| Amounts hidden (AI1 case 7) | "AI on · 1 background on", the colour kept | not drawn: every viewer sees the amounts | **deviation** (log: AI chip and spend panel built: amounts shown to every viewer) |
| Laptop and phone widths (AI1 case 8) | in full at 1280; the figure and its colour at 390, the count in the panel | in full above 1100 px; the figure at 1100 px and under; the mark alone in its colour at 400 px and under; Update available and In progress give way beside it | **deviation** (log: AI chip built: compact at 1100 px and under, the mark alone at 400 px and under) |
| How the chip stays current (AI1's lead) | read when a page loads and on each recorded call (`nmas:ai_calls`), never on a timer | read on load, on `ai_calls` (every route that calls the gateway declares it, and the SDN loop announces it after a classify) and on `settings` (Turn off, the master switch, the day cap) | **same** |
| The panel opens (AI2's lead) | under the chip on whatever page, Esc or the chip closes it; read when it opens and on each recorded call while open | the same, and the panel's × closes it too; read only while open (nmas_v2.js `aiSpendPanel`) | **same** |
| The panel's head (AI2) | "AI spend", How does this work?, × | the same; the link opens the manual's What AI is spending | **same** |
| Today (AI2) | the figure; "of the day cap $5.00 · 52% · 31 calls"; a bar marked at 50% and 80%; Yours today; People's presses; Background (1 feature); Evaluation runs (2) with each run and its amount | the same | **same** |
| The reset (AI2) | "resets at 00:00 UTC, in 18 h 23 m" | "resets <the viewer's time> (00:00 UTC)", the words every AI screen uses, no countdown | **deviation** (log: Spend panel built: the reset without a countdown) |
| Daily average (AI2) | the last 7 and the last 30 complete days, a day | the same | **same** |
| This month (AI2) | "(October, 26.2 of 31 days)"; the figure of $155.00, the cap's basis; a bar with the projection lighter; "At this rate, by 31 October" | the same | **same** |
| A background feature (AI2) | its words, its network, Turn off; its trigger with calls per finding; Today and This month against its caps with their shares; the estimate when turned on beside the actual over N days and their ratio; who turned it on, when | the same; Turn off with its (i), busy on itself | **same** |
| A stopped feature, a feature near a cap, none on, AI off (AI2) | a stopped feature with its chip, when it stopped and when it resumes, no This month row; the others not drawn | the stopped feature the same, its This month row kept; at 50% or 80% "at 50% of a cap"; with none on, where one is turned on; AI off said above what was spent | **deviation** (log: Spend panel built: states and answers the board does not draw) |
| Turn off (AI2) | one click | Settings › AI's own route and gate (`settings_v2.ai_off`, `?answer=panel`), its answer drawn in the panel: turned off, already off, or not changed with why | **deviation** (log: Spend panel built: states and answers the board does not draw) |
| The foot (AI2) | prices' date; "The provider bills what is spent; its own limit is the backstop."; "Every AI call, with spend by feature, person and day" · Settings › AI | the same words; "Every AI call (History)" · Settings › AI | **deviation** (log: Spend panel built: the History link names every AI call) |
| The record cannot be read (AI2) | the notice, never $0; the features on, each refused, with Turn off | the same, each feature on its own row with its Turn off | **same** |
| Amounts hidden (AI2) | "Amounts are shown to admins on network Default" | not drawn | **deviation** (log: AI chip and spend panel built: amounts shown to every viewer) |
| The panel at phone width (AI1 case 8) | full width beneath the bar | the screen's width under the bar at 860 px and under, scrolling within | **same** |
| Needs attention (AI2's second region) | installation-wide rows at 50% and 80% of the day cap with Open the spend panel; a feature stopped by its cap; a feature above 150% of its estimate; an approval expiring | each feature's rows at 50% and 80% of its caps and stopped by a cap, built before this (`attention.ai_spend_source`, acting in Settings › AI); the installation-wide day-cap rows, the estimate's 150% row and Open the spend panel are not built; the approval's is C1953's | **later** (the finding reported with this build for the register: Needs attention lacks the day cap's 50% and 80% rows and the estimate's 150% row, PHASE8_PLAN 18.3 rule 10c) |
