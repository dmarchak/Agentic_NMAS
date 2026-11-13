# Fidelity: Settings · <network> › Self-healing (2026-11-03)

Board: `heal-to-intent.html`, artboard A (1440), docs/boards/heal-to-intent.html, approved by the
operator 2026-11-03 ~19:5x UTC (docs/STANDING_APPROVAL_LOG.md, "Board H approved by the
operator: heal to intent (Lab 10)"). Its yellow callouts are notes for the builder.

Shots: `tests/test_board_shots.py::test_heal_tab` (`heal-tab` at 1440, 1280 and 390: Default
marked lab, in dry run confirmed with a reason, one Tier 1 kind allowed, a team told with every
event; `heal-tab-change` at the same widths: Change mode… pressed, Auto chosen, its expiry and a
reason typed, What this changes and the confirm drawn in place), NMAS_BOARDS_DIR set to
docs/boards. The states the shots do not draw (a network not marked lab, a refusal, Turn off's
answer, the kill switch stopped and its resume card, Who is told's refusals) are compared by
the templates and tests/test_heal_tab_v2.py.
Templates compared: templates/v2/_heal.html, templates/v2/_heal_change.html, templates/v2/_heal_preview.html
Compared again 2026-11-13 (C3290, the words Python builds): `_heal.html` is drawn under `{% filter times %}` (routes/v2.py), so the policy's Set time, AUTO's expiry and the analysis' "turned on …" and "approval ends …" are `_macros.clock`'s, in the viewer's kept zone with the UTC instant on hover, where modules/heal_page.py wrote "20 Nov 18:00 UTC" (it now writes the instant; the typed "Auto until" field keeps its own form); the change's preview (`_heal_preview.html`) draws its Mode row's before and after ("Auto until …, then dry run") through the `times` filter. No element moves and no region's verdict moved; compared by the template's diff and the walk's render (tests/test_no_utc_drawn.py), not by new shots; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times: the words Python builds"). Templates sha256 before: `e46799b907c6edc567067ac1793092456ddd9a3641c9e277111ce668a643d7d8`.
Compared again 2026-11-13 (the operator's approved rule, "raw UTC anywhere left"; C3158, the review's "…until 2026-11-18T11:49:00Z"): `_heal_preview.html`'s confirm button ("Turn on Auto for <network> until …") draws Auto's expiry through `_macros.clock` ('date'), in the viewer's kept zone with the UTC instant on hover; the preview's summary and a gate's detail (`_preview_parts.html`, not a compared template) through `times`. `_heal.html` is unchanged: the whole tab is drawn inside `times` already (C3290), so its Confirmed notice, Mode row and policy history draw the expiry by the clock as before. The preview's program still lists each stored value as stored, the instant among them: a program is quoted. No element moves and no region's verdict moved; compared by the template's diff and its render (tests/test_heal_tab_v2.py, through the real preview and confirm), not by new shots; logged once (docs/STANDING_APPROVAL_LOG.md, "Local times: the words Python builds"). Templates sha256 before: `53afc6031e7998bd65bac0bfe25f303331cac6822ace9ddb35922f3d69a591ba`.
Templates sha256: `0b3286ddf246cc4a610167e3fb313c7f5484b53c17f0d82a50683ecb9afa7aa9`

**Compared again 2026-11-12 for C3196 (the BGP session clear listed twice):** by the template's
diff against the Fix kinds region, not from new shots. The table and the change card draw a
kind in both policy lists once, at the tier its network gives it (Tier 1 on a network marked
lab, as the shots' Default is; Tier 2 elsewhere), where they drew it in both tiers; the change
card carries that kind's setting in the other list as a hidden field, drawn nowhere. The
board's table draws each kind once, so the region is closer to it; no region is added, removed
or moved, and every other verdict stands.

**Compared again 2026-11-11 (board E2a, display names):** by the template's diff against the
regions below, not from new shots. In `_heal.html`, each place that draws a person (who
confirmed the policy, who made each change in its history, and the words "stopped everywhere
by", "Now: … by" and "Turned off" that name one) now draws them through the `people` filter, by
display name (the name the person set, else the part of their identity before the "@"), in the
same element and position; no region is added, removed or moved, and no other word changes.
Where the board draws an identity the built screen draws the name, a deviation logged once for
every screen (log: Display names: a person is drawn by display name on every screen). Every
other verdict stands.

**Compared again 2026-11-07 for C2647:** Who is told's "AI analysis of a can't-fix" row, fixed
text written before H8 ("the advisory analysis is not built yet"), now draws the background
feature's state on the network (`heal_page._analysis`). Compared by the template diff against
artboard A's row (no new shot; tests/test_heal_auto_diagnose.py draws its off and on states).
One deviation, logged (the table's row below). Every other region is unchanged. Templates sha256
before: `e262f3db593745e410226930d83cc5e334fb3bbb51de8161a422ec0b71412edd`.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Where it is | a third tab, Self-healing, beside Integrations and Network, the page's subtitle adding "Self-healing is each network's own: no network inherits it." | the same tab and sentence, on Default's and every network's page | **same** |
| The scope bar | Network ▾ with Settings › Installation | the product's scope bar (Installation, Default, A network), as every Settings page draws it | **same** |
| The mode card's head | "Self-healing on Default" and the mode chip | the same; the chip reads off, dry run, Auto, not in force, stopped everywhere or cannot be read | **same** |
| Mode | "Dry run: every step but the apply…" | the same words, and under them the mode now in words from `heal.policy.current` ("Now: dry run, by …: <reason>") | **deviation** (log: Board H built: the mode's why in words under the Mode row) |
| Set and Network stage | when, by whom (verified), the reason; lab with the gate's words | the same | **same** |
| Would have healed | 7 · right 6 · wrong 0 · 1 unmarked | not drawn: no dry-run record is kept until the step log | **later** (H6, the step log and its dry-run records) |
| Production's bar | "2 days of 30 and 7 events of 100, at 1% wrong or fewer" | the bar's terms, "30 days and 100 dry-run events, at 1% wrong or fewer", without the counts | **later** (H6, the counts from the dry-run records) |
| Policy fingerprint | `pol-3f9c2a81` | the policy's 16-hex fingerprint, and the confirmed one beside it when they differ | **deviation** (log: Board H built: the policy fingerprint as the policy holds it) |
| The mode card's actions | Change mode…, Turn off, History of this policy (a link), How does this work? | Change mode… and Turn off (only while the mode stored is not off), each with its (i); History of this policy opens in place, the policy's own records | **deviation** (log: Board H built: History of this policy opens in place) |
| Fix kinds | the table with Tier chips, a toggle per kind, the Lab scenario column, Tier 3's tooltip | the table with the chips and each toggle drawn; Tier 3's and 4's why as a note in the row; no Lab scenario column | **later** (H6 and H11: a kind's lab scenario is its dry-run and AUTO records) |
| Change fix kinds… | the button | the button, opening the change card with a tick per Tier 1 kind ("Heal: …") and per Tier 2 kind ("Propose: …"), previewed and confirmed as a mode change | **deviation** (log: Board H built: the fix kinds changed by ticks in the change card) |
| The change card | Off, Dry run, Auto; Auto until; Reason | the same; Auto until is empty until typed, in UTC, with the board's hint; Auto drawn disabled with the callout's words on a network not marked lab | **same** |
| What this changes | Mode, kinds that heal, kinds proposed, devices it may act on (with a count) | the same rows, a row for each hard stop that moves, "(unchanged)" where now and after agree; the devices row without a count | **deviation** (log: Board H built: What this changes names no device count) |
| The confirm | "Turn on Auto for Default until 20 Nov 18:00 UTC", Cancel, the pipeline paragraph | the same words for its kind, the pipeline paragraph on Auto, each refusing check above it, who is confirming and the fingerprint, the six parts one level down; Cancel under the card | **deviation** (log: Board H built: the confirm with its refusals, statement and six parts) |
| Hard stops and guards | each guard's value, default and Edit… | each value with where it comes from (set, lab default, default) and its default; Edit… opens the change card for that stop; "two reads" not drawn (no setting holds it) | **deviation** (log: Board H built: each hard stop's source beside its value) |
| The always-on guards | planned work, held devices and windows; a rolled-back heal | the same | **same** |
| Who is told | the team named, its counts, the five events, the AI analysis chip, Save | the team chosen from a list (nobody, or a team), its counts, the five events, Save | **deviation** (log: Board H built: Who is told chooses its team) |
| The AI analysis of a can't-fix | "off for Default", Settings › Installation › AI | from the background feature's own switch on the network (C2647, 2026-11-07): "off for Default" and that an admin turns it on in Settings › Installation › AI after its estimate; "on for Default" with who turned it on and when, its caps, when its approval ends and its measured label; "approval ended", "on, hosted AI off" and "stopped at its cap" each said; then the link and its (i) | **deviation** (log: Board H built: the AI analysis line says its switch's state in words) |
| Stop self-healing everywhere… | the danger button, alone | the button; pressed, a card says what stopping does and asks why (never required) with Stop self-healing everywhere and Cancel; while stopped, every network's tab says so with Resume self-healing…, its preview and confirm with a reason | **deviation** (log: Board H built: the kill switch's ask, stopped notice and resume card) |
| Answers in place | not drawn | Confirmed…, Turned off, Not saved: … (what was typed kept), Saved for Who is told, each in its card | **deviation** (log: Board H built: each answer drawn in its card) |
| Phone width | not drawn | the two columns stack: the mode, the kinds, then the change card, the hard stops, Who is told and the kill switch; tables scroll inside their cards | **deviation** (log: Board H built: the tab's phone width) |
