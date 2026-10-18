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
Templates compared: templates/v2/pending.html, templates/v2/_pending_progress.html, templates/v2/_onboard_pending.html, templates/v2/_pending_gone.html
Templates sha256: `e0c0a076701181fe43bcc5750f4045f11d1661b3c5b1e5411b11dadd61dac113`

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
| Abandon… | "What does abandon remove?" beside it | the dry run in place: each step "will run" or "would fail", Abandon <device> (danger) bound to it, its (i) and the confirm's statement | **same** |
| No longer pending | not drawn | the progress card, re-read on `pending`, says "<device> is no longer pending" with a link to its page (compared by the template and `tests/test_onboarding_progress.py`) | **deviation** (log: C1193: board M's pending page, its progress card) |
| Phone width | no phone board | at 390 the facts wrap, the stepper turns to a list, the actions wrap; nothing past the screen | **same** |
</content>
</invoke>
