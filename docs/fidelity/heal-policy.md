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
Templates sha256: `3931d9d31667763c08ddcf713c27d783bb7525aa4773466bf156040a4f1aabb3`

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
