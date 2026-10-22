# Fidelity: the batch Apply (Devices › Plan a deploy)

The batch Apply's page as built (`/v2/devices/deploy`, the `intent` scope: the preview with its
rollout order and each device's program, the confirm, the job card that follows the batch, its
result), compared region by region with its boards (C650's step), from the operator's walk W1
(2026-10-16, steps 16 to 18: Plan a deploy for s1 and s2 from Devices, the order changed with
Later, the batch run and its result). W1's records left this page out (devices.md names it "its
own record"); it is recorded here from that sitting. The same template draws the monitoring
profile's apply from Monitoring › Coverage, which no walk ran; its regions are this page's. No
shot test exists for this page (tests/test_board_shots.py has none; the stepper's own shot is
`test_stepper`, docs/fidelity/stepper.md), so the page as built is the operator's W1 captures:
16 (the plan, before the confirm), 17 (after Later: s2 first), 18 and 19 (the batch running, s2
then s1) and 20 (done).

Boards: `BatchDeploy.dc.html` (board B, "Deploy 500 devices: the order, the programs grouped,
the job, the result", on "NMAS v2 mockups", page "7.4 Fleet", signed off 2026-10-04, built as
this page by the 2026-10-10 line "Batch deploy (board B, signed off 2026-10-04)"), and
`Stepper.dc.html` (the stepper mockup, "Applying to 3 devices… in the order you set", signed
off 2026-10-02, this page's own sign-off). The stepper inside the job card is THE stepper,
compared in docs/fidelity/stepper.md. Not compared: `BatchExpected.dc.html` (C506 phase 4's
Expected effects for the batch preview), marked FOR SIGN-OFF on the canvas with no sign-off in
docs/STANDING_APPROVAL_LOG.md.
Shots: the operator's captures above; the boards `BatchDeploy` and `Stepper` at 1440, rendered
in the same headless Firefox (no shot test to run them).
Compared 2026-10-17.
Compared again 2026-10-18 (C1270): in the result's per-device evidence, under the verify line,
one paragraph per line of what verify read (`t.verify_words`): its scope and why, how many new
lines it looked for and read back, each line not read back (in the refused style) and each it
did not look for with why; drawn only when the receipt recorded them, so a result without them
is drawn as before. No board draws these lines (today's renderer did, which P7-27 removes); the
deviation is a line in STANDING_APPROVAL_LOG.md. Every other region unchanged: one line added
to `_apply_job.html`, read from the diff.
Compared again 2026-10-21 (C1499, the overnight run): a finished batch's card draws, under its
stepper, a "Retry <device>" link for each device the batch did not deploy, opening a new preview
of that device alone on the batch's scope. Board B draws the same control on its result ("Retry
the 1 rolled back"); the built one covers every device not deployed, not only a rolled-back one,
so it is a deviation (below). Every other region unchanged: one paragraph added to
`_apply_job.html` and the `how` macro imported, read from the diff and drawn by
`tests/test_profile_apply_v2.py`'s retry test, not a new shot.
Compared again 2026-10-22 (C1541): the result's per-device verify line is the receipt's own
decision, `checks.ok`, through `preview_confirm.verify_verdict` (the `verify_verdict` filter):
"Verify passed" only when it is true, else "Verify did NOT pass" in the refused style with each
cause beneath it, masked, the read-back's misses among them ("3 sent line(s) did not read back:
…") where no issue already says them. It read `c.ok` before, and listed issues, unmet protocols
and unreadable reads, never a read-back miss outside Coverage's combined deploy. The same
region, the same words when verify passed; the stepper's Verify step drawn partial when verify
did not pass is data (`run_stepper.finished`'s `partial_at`), not this template. Every other
region unchanged: the verify line and its causes' loop in `_apply_job.html`, read from the diff
and drawn by `tests/test_verify_verdict_follows_receipt.py`, not a new shot.
Templates compared: templates/v2/apply.html, templates/v2/_apply_preview.html, templates/v2/_apply_job.html
Templates sha256: `079a9e82b4e4f38c476d7f85d8ea672bf255fc4b09f69b8f08981ce13716c4d1`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Sidebar | Devices current | the same (capture 16) | **same** |
| Crumbs | Devices › Deploy 500 devices | Devices / Plan a deploy (capture 16) | **same** |
| Page head | "Deploy committed intent to 500 devices" with How does this work? | "Deploy committed intent" with its (i), and the sub-line "To the devices ticked on Devices, one at a time in the order below…" (capture 16); the count is in the headline below, not the title | **same** |
| Summary | four count tiles: a program to send, at intent, wait on a reason, not answering: left out | one headline sentence, "Deploy to the devices you tick, merge-only: 2 of 2 can be deployed now, and for each, exactly the program shown is sent, in order." (capture 16) | **deviation** (log: Batch deploy: the summary is a sentence, not count tiles) |
| The running note before a confirm | not drawn | "The batch is running in the order you confirmed…" drawn before anything was confirmed (capture 16; C883, fixed 2026-10-16 after the sitting) | **same** |
| The order | a rule, not rows: canaries, then by site, then by role within a site, each with Change… or Reorder…; "See all 486 in order" | one row per device with its state ("can be applied"), Earlier, Later and Leave out (capture 16; a drag grip since C905), and the note on why the first devices matter | **deviation** (log: Batch deploy: the order is a row per device, not a rule (a defect, register C650 follow-up)) |
| The programs | grouped by what they send ("Group A · 412 devices · 2 lines"), each group collapsed, a device on expand | one section per device, "1. s1 can be applied", "The program: exactly these 3 line(s), in order", its lines, "Where the added lines come from" and Gates and operands collapsed (capture 16): two identical programs drawn twice | **deviation** (log: Batch deploy: each device's program drawn in full, not grouped (a defect, register C650 follow-up)) |
| A device waiting on a reason | its group first, "One reason for the three (or open each to give its own)" | a superseded line ticked for removal asks "Why (your stated reason…)" on its device's section (compared by the template; W1's devices had none) | **same** |
| What will not happen | not drawn | "Nothing is held back from a device that can receive it." and the merge-only sentence naming Mode B (capture 16; "Mode B" in a sentence a person reads is C901) | **same** |
| The confirm | "Bound to these programs, reasons and this order (plan <hash>)…", Deploy to 486 devices, in this order | "You are confirming as <you>.", Deploy to 2 device(s) in this order with How does this work? (capture 16); the plan's hash and what happens if it moves are not said beside it | **deviation** (log: Batch deploy: the confirm does not say what it is bound to) |
| The job (Stepper board) | "Applying to 3 devices", "Started 14:02 by you", running · 1 of 3 done; each device a row, done with its summary and Receipt, running with the stepper and what it waits on, waiting "next after s5" | "Applying, one device at a time", the bar, "0 done · 1 running · 1 waiting its turn · 0 failed", each device the one stepper with its steps' times, waiting "its turn: one device at a time, in the rollout order", the Commit as its own last row, "Started 4.0 s ago. This page follows it; it keeps running if you leave." with Check now (captures 18 and 19) | **same** |
| The job at fleet scale (board B) | count tiles, Find a device and Every outcome, the devices grouped by outcome and collapsed (running open, rolled back with Retry and Revert, done and waiting folded) | every device a row drawn open, with no search, no outcome filter and no grouping (captures 18 to 20) | **deviation** (log: Batch deploy: the job draws every device open, with no search or outcome groups (a defect, register C650 follow-up)) |
| The result | "486 devices: 485 deployed and verified, 1 rolled back", partial, one golden commit linked, a receipt per device, Retry the 1 rolled back, Open in History | badged Done, "2 of 2 device(s) deployed. 2 device(s) accounted for: every device in the batch appears here."; each device "what was sent and what was checked" open; the golden commit as text, not a link; no Open in History (capture 20) | **deviation** (log: Batch deploy: the result's commit is text and it has no link to History) |
| The result's words | not drawn | "No baseline tag: 7 device(s) not targeted: ['r1', 'r2', …]", a raw list, and "the follow-up window … is a job behind 7.1 (register C60), not built yet", an internal note (capture 20; C901) | **deviation** (log: Batch deploy: the result prints a raw list and an internal note (C901)) |
| Retry (C1499) | "Retry the 1 rolled back" on the result | "Retry <device>" under the stepper for each device the batch did not deploy (failed, refused, rolled back), each a new preview of that device alone on the batch's scope, with How does this work?; none while it runs | **deviation** (log: Batch deploy: Retry for every device the batch did not deploy) |
| The way back | Open in History | "Back to Coverage: it redraws from the new goldens." after a deploy from Devices (capture 20; C861) | **deviation** (log: Batch deploy: the result ends Back to Coverage after a Devices deploy (C861)) |
