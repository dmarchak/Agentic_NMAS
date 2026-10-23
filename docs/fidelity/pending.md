# Fidelity: a pending device's page (board E's pending page, board M's progress)

A device onboarded and not yet reached, at its own address (`/v2/device/<name>`), as built,
compared region by region with its boards. Read from shots of the boards and the page side by
side, in the same headless Firefox (`tests/test_board_shots.py::test_pending_page`), fed the rows
the page's own tests build: `tests/test_onboard_v2.py`'s `TestAPendingDevice.PENDING` (bp1,
static) and `tests/test_onboarding_progress.py`'s ZTP row and probe answer. Its states, each
reached in the page as a person reaches it: bp1 by ZTP, fetched and answering; bp1 static,
overdue, its last Verify failed; Verify… pressed (that test file's preview model) and its confirm
pressed (its stepper test's phase-two steps, stopped at the rotation); Abandon… pressed, its dry
run from the real `abandon_onboarding` on `tests/test_onboard_abandon.py`'s repository; the (i)'s
help panel. The fixtures' rows are dated 2026-10-10, so the shots read "8 d ago"; the layout is
what is compared.

Boards: the sign-off names board E's pending page, drawn under the Phase 7 mode while the canvas
was not readable (docs/STANDING_APPROVAL_LOG.md, "Board E as built"). Of the Onboard boards on the
"NMAS v2 mockups" canvas, `OnboardPanel.dc.html` ("A pending device, How onboarding works open")
is the one that draws a pending device's page, and is compared here; `OnboardProgress.dc.html`
draws a list of pending devices ("Devices › Pending onboarding"), a page not built (Pending is
each device's own page: the 2026-10-11 line "board L's tabs"); `OnboardFull.dc.html` and
`OnboardList.dc.html` draw Add device and the discovery list. Board M (`ZtpPlan.dc.html`, canvas
v113, "Board M redrawn on the operator's decision and signed off", 2026-10-11) draws the page's
five steps and Verify's result naming the next step, and is compared too. There is no phone
board.
Shots: OnboardPanel at 1440 and 1280 (`pending-panel-board-*`), ZtpPlan at 1440
(`pending-plan-board-1440`); the page by ZTP at 1440, 1280 and 390 (`pending-ztp-page-*`), with
the help panel at 1440 (`pending-help-page-1440`); static and overdue at 1440 and 390
(`pending-static-page-*`); Verify's preview at 1440 and 390 (`pending-verify-page-*`), its result
and Abandon's dry run at 1440 (`pending-verified-page-1440`, `pending-abandon-page-1440`). The
operator's walk W4 (2026-10-17, steps 40 to 42) captured the page of the device onboarded by ZTP,
its Verify preview and its result (screenshots 60 and 61), read beside the shots: the same
regions.
Compared 2026-10-18.
Templates compared: templates/v2/pending.html, templates/v2/_pending_progress.html, templates/v2/_onboard_pending.html, templates/v2/_pending_gone.html, templates/v2/_console_kick.html
Templates sha256: `2e89efad4dc8a2b675e8b1386fa63d62c715257139874a763f13f98af1a84a74`
Hash rewritten 2026-10-23 at the Phase B merge: the run page's links name their network as `?list=` (they said `?list_name=`), and the run page's Devices link takes the page's network; no drawn text, region or control moved, every verdict stands.

Compared again 2026-10-23 (board C of `docs/boards/oob-onboarding.html`): the console offer
(`_console_kick.html`) gains one link under its button, "Open its newest console run's page"
(the run's own page, a read). Compared by the template, not a new shot; the Console row's
verdict stands.

Compared again 2026-10-22 (C1575, board F of `docs/boards/console-ztp.html`): the Onboarding
card at rest gains a Console part under its three actions, out-of-band ZTP's way back once Add
device's card is closed. A device whose console survey is recorded is offered the console card
(`templates/v2/_console_kick.html`, the macro Create's result in Add device draws too): "Kick-start
<device> through the console…" when the survey found it factory-blank, "Survey <device>'s console
again…" when not; with no survey recorded and a NetBox record from its onboarding, the part is
asked for as the page draws (`_console_offer.html` with `pending=1`): "Survey <device>'s
console…" when NetBox shows a console path, nothing when it shows none, an unreadable NetBox
said. The card opens in the part's place, as boards C to E draw it. OnboardPanel and board M
draw no console, so it is a deviation (below). Compared by the template beside board F, and by
tests/test_console_ztp_v2.py's `TestThePendingPage` and the interface walk's pending page
(tests/interface_pages.py, `PENDING`), not a new shot: one part added under the actions; every
other region unchanged, and `_console_kick.html` joins the templates compared.

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar and breadcrumb | Devices current; "Devices / sw-branch7" | the same | **same** |
| Header | the name in mono and a chip "Pending onboarding" | the same, the (i) beside the name, the chip naming the state: "Pending onboarding: pending", "…: overdue" (amber), "…: stale" | **deviation** (log: Pending: the header's chip names the onboarding's state) |
| Sub-line | "Onboarded 25 min ago · not reached yet, so it is in no inventory and nothing polls, backs up or checks it" | the same, with the network named | **same** |
| The facts | Address ("awaiting DHCP (Kea reservation → …)"), Address source with the MAC, Next | the same three, and the ZTP stage with its words, the last Verify or Abandon from its record, and a notice when overdue, stale or the staged credential cannot be found (today's banner's facts) | **deviation** (log: Pending: the facts carry the ZTP stage, the last Verify or Abandon, and the overdue notice) |
| The actions' place | inside the facts card, under Next: Verify…, How does this work?, Bootstrap config, Abandon…, What does abandon remove? | their own card, "Onboarding", under the progress: Verify…, Get the bootstrap config…, Abandon…, each busy on itself with its (i); each opens in place of the three | **deviation** (log: Board E as built) |
| Get the bootstrap config… | "Bootstrap config" (board M: "Get the bootstrap config… (a recorded reveal)") | a reveal in place, to a person and recorded; not shot (it draws the one-time credential), compared by the template and W4's step 10 | **deviation** (log: The bootstrap config on v2: drawn in place, or downloaded as a file) |
| How onboarding works | the panel open beside the page: the diagram, phase one done, phase two's nine steps | the (i) opens the help panel at the manual's onboarding page: the same diagram and phase two | **same** |
| Where it has got to | board M: "Where r8 has got to", five steps (Identity, First-boot config, Confirmed, Waiting for it, Arrival) | "<device> onboarding progress" with its ZTP, DHCP or static badge; the probe's answer ("Answering: ready to Verify", "Not answering yet", "Not probed yet"); the five steps on the one stepper; the stop rule for ZTP; the five lines | **deviation** (log: C1193: board M's pending page, its progress card) |
| The five lines' facts | First-boot config "23 lines, … hash 7f3a…5d18"; Confirmed "by operator@example.com" | First-boot config in words with no line count or hash; Confirmed with its time and what was reserved, naming nobody | **deviation** (log: Pending: the five steps name neither the first-boot config's lines and hash nor who confirmed it (a defect, register C650 follow-up)) |
| Waiting for it's time | "now", the lease and fetch times | the stepper's live clock in seconds since Create: "723110 s" for a device eight days pending | **deviation** (log: Pending: Waiting for it counts in seconds however long the wait (a defect, register C650 follow-up)) |
| Waiting's sub-states | each from Kea and the responder: reservation missing, reserved no lease, asked not served, leased not fetched, fetched not reached | the stage badge and its words in the facts and on the Waiting line | **same** |
| Verify's preview | not drawn on OnboardPanel (the sign-off: preview, confirm by fingerprint, in place) | in place of the actions: the summary, What will be sent, the operands, the checks now and at confirm, Verify <device> with its (i) and the confirm's statement; Cancel | **same** |
| Verify's result | board M: "Verified …", then "Next, its intent." with Deploy its intent…, or where to write it | phase two's nine steps on the one stepper (the failed one red, the rest not reached), the outcome notice, Open <device>'s page; the next step for a first-boot intent is Actions › Seed intent… (compared by the template and `tests/test_onboard_v2.py`) | **deviation** (log: C1188: Verify's result on the pending page, a first-boot intent) |
| Console (C1575) | not drawn: OnboardPanel and board M have no console; board F of `docs/boards/console-ztp.html` draws it | under the three actions at rest: the recorded survey's offer (the kick-start when it found the device blank, the survey again when not), or, with none, NetBox's console path asked for as the page draws (the survey offered, nothing when no path); the card opens in its place | **deviation** (log: Pending: the Onboarding card's Console part, compared with its boards) |
| Abandon… | "What does abandon remove?" beside it | the dry run in place: each step "will run" or "would fail", Abandon <device> (danger) bound to it, its (i) and the confirm's statement | **same** |
| No longer pending | not drawn | the progress card, re-read on `pending`, says "<device> is no longer pending" with a link to its page (compared by the template and `tests/test_onboarding_progress.py`) | **deviation** (log: C1193: board M's pending page, its progress card) |
| Phone width | no phone board | at 390 the facts wrap, the stepper turns to a list, the actions wrap; nothing past the screen | **same** |
</content>
</invoke>
