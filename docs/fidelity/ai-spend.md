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
Compared again 2026-10-28 ~11:5x UTC for C2056 (AI2's second region, Needs attention): the
installation-wide day-cap rows, the estimate's 150% row and Open the spend panel built
(`attention.ai_spend_source`, `_attention.html`'s `ai_spend_panel` control, nmas_v2.js
`aiSpendOpen`). `spend_view.py` changed only in reading "AI off" from `spend.hosted_on`, the one
answer the chip, the panel and Needs attention share; nothing it draws moved. A new shot,
`ai-attention-page-1440` and `-390` (Needs attention in the same world, $0.80 of the $1.50 day
cap: the 53% warning row, its Open the spend panel pressed and the panel open over the page),
read beside `ai-spend-board-1440`'s Needs attention region; the other shots taken again, nothing
moved. The region split in two below: the AI spend rows (a deviation) and an approval expiring
(still later, C1953's).
Templates compared: templates/v2/_ai_chip.html, templates/v2/_ai_spend.html, modules/ai/spend_view.py
Templates sha256: `e7e4b2ca297a7d871ebdbfae9868e786dfa8d819838f864a841b4d75b5ec7476`

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
| Needs attention: the AI spend rows (AI2's second region) | "AI spend is at 52% of the day cap" (warning) and "at 82%" (critical), each with both amounts and Open the spend panel, clearing at the day's reset (the 50% one "or when acknowledged"); a feature stopped by its day cap, with Settings › AI; a feature "running at 367% of the estimate it was approved at" with both amounts a day, with Review, clearing under 150%, when accepted again or turned off | "AI spend is at 53% of the day cap ($0.80 of $1.50)" (warning from 50%, critical from 80%: `spend.WARN_AT`, the chip's), its cause both amounts to four places, since midnight in the cap's zone, and what happens at the cap; "AI spend reached the day cap ($1.50 of $1.50)" (critical) at or over it; "<feature> on <network> is running at 150% of the estimate it was approved at ($0.1500 a day against $0.1000)" (warning, from `spend.OVER_ESTIMATE_AT`); each feature's 50%, 80% and stopped rows as before; every one with Open the spend panel (in place, the page unmoved), a feature's with Settings › AI's Open… beside it; the day's rows clear at the cap's midnight or when the cap or hosted AI moves them, never by an acknowledgement | **deviation** (log: Needs attention's AI spend rows built: no acknowledgement, a cap-reached row, and Settings › AI beside the panel on a feature's rows) |
| Needs attention: an approval expiring (AI2's second region) | "The approval of SDN classification on Lab expires in 3 days", with Settings › AI | not built: C1953's (an approval's end three days ahead) | **later** (C1953) |
