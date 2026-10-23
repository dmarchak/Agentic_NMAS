# Fidelity: THE stepper (the one progress display, 2026-10-12)

The operator, 2026-10-12: "the stepper you built for Save All (C605: one row per device, its
steps with times, an overall bar, the commit as its own last row; horizontal on desktop, the
vertical step-by-step on phone) was agreed as THE progress display for every multi-step or
multi-device operation, but only Save All uses it." One component since: `modules/run_stepper.py`
(the model), `templates/v2/_run_stepper.html` (`run_stepper`, the one macro), `.run` in
`static/css/nmas-v2.css`, `static/js/nmas_stepper.js` (the running step's clock). Each operation
keeps its own step names beside its code and hands the component rows. tests/test_one_stepper.py
holds that every operation page uses it, or is named with why not, and that no page draws
progress any other way.

Boards: `SaveProgress.dc.html` (C605, the desk, 1440) and `StepperPhone.dc.html` ("the one
stepper at phone width: vertical", 390), on the mockups canvas. Shots: tests/test_board_shots.py
`test_stepper` (`stepper-save` at 1440 and 1280, `stepper-phone` at 390), Save's running card
built by the real code from rows marked as its job keeps them. Compared 2026-10-12.
Compared again 2026-10-12: the model gained `at_step` (an operation that knows its step and notes
no trail: Capture's read, onboarding's lifecycle); nothing the macro draws moved, so no region's
verdict changed.
Compared again 2026-10-12, with the last pages: the model gained `summary` and the macro
`run_summary` (the card's bar and counts alone, for Show commands and the logging-path test,
whose rows are their answers: the same `<progress>` bar and counts line as the card, so the
bar's and the counts line's verdicts stand), and `at_step` a `device` flag (a NetBox job's
subject is a list, drawn unlinked). Update draws the macro's markup and its script sets each
step's state as the updater reports it (the app restarts part way, so no redraw can); the
classes it sets are the macro's own.
Retaken 2026-10-13 (the operator's overnight list, item 12; `test_stepper` at 1440, 1280 and 390,
the templates unchanged since the hash below): every region's verdict stands. One defect in
the words, not the layout, registered as C741: the running step's note (drawn under the step on
the phone, the hover on the desk) ends "(last done: read_back)", the running step's own code
name said as done, and the counts line says "1 waiting their turn" where the board says "its
turn". The phone page's full shot is 488 px wide because that is Firefox's narrowest window; the
page is held to 390 as a column, not scrolling sideways.
Retaken 2026-10-13 for C741's fix (`test_stepper` at 1440, 1280 and 390): the counts line says
"1 waiting its turn" (one row its turn, several their turn, as the board), and the running
step's note says what it waits on with no "(last done: ...)" of its own name; a finished part
of a step noted as it ends is said in words ("last done: original session"). Nothing the macro
lays out moved; every region's verdict stands.
Compared again 2026-10-22 (C1541): the model's `finished` takes `partial_at`, the key of the
step that did not pass, so a deploy whose verify did not pass draws its Verify step partial and
every other step done (it drew the last step partial and Verify done). The step's partial state
and its class are the macro's own; nothing the macro lays out moved, so no region's verdict
changed. Read from the diff, not a new shot.
Compared again 2026-10-22 (C1579, the console survey and kick-start): the model's `single` takes
`device`, False for a row whose device has no page to link to yet (a survey before Create), and
`from_stepper` keeps the note of a step already in the card's shape (a route that hands its
template only what it draws). The row's name is drawn unlinked, as a non-device row's already
is; nothing the macro lays out moved, so no region's verdict changed. Read from the diff, not a
new shot.
Templates compared: templates/v2/_run_stepper.html, modules/run_stepper.py, static/js/nmas_stepper.js
Templates sha256: `8b51e27c3aaee9e3d0ac8931411e3d0d3fd42364e585fa3944ebd28bf85fa5e9`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| The bar | one bar: done green, running blue | one `<progress>` bar, done green: the strict CSP refuses an inline width, so the running segment cannot be drawn (as Save's bar already was) | **deviation** (log: the one stepper's bar is one colour) |
| The counts line | "2 through their turn · 6 running · 1 waiting · 0 failed", failed red when any | the same order and words (each operation may name its groups, Save's "through their turn, waiting for the commit"); a partial or a not-reached said only when there is one | **same** |
| A row | its mark, the device linked, its steps across, its time at the right | the same; the state also in words for a screen reader | **same** |
| Marks | a tick done, a turning ring running, an open ring waiting | the same; a failed row red, a partial one amber | **same** |
| A step | its bar, its words, its time | the same; times in whole seconds where the board has tenths (the step builder has always rounded) | **deviation** (log: the one stepper's times are whole seconds) |
| The running step's note | not drawn on the desk | on the desk it is the step's hover and for a screen reader, the row one line high; drawn under the step on the phone | **same** |
| A failed step | red on its row, with the device's own words | the same, the words under the steps | **same** |
| Waiting its turn | the row's one line, the cap named | the same, in the operation's words | **same** |
| The commit | its own last row: "waits for every device's turn", "not started" at the right | the same (any operation's own last row: Save's commit, the batch's goldens and receipts) | **same** |
| At scale | from 25 rows: groups (failed, running, waiting, done) collapsed, Find a device | the same, from 25, failed and running open, the search filtering rows and never counts | **same** |
| Phone: steps | down, the current one with what it waits on | the same, below 640 px | **same** |
| Phone: rows | a finished or waiting row is its one line; the running row opens; its time beside its name | the same; a failed row opens too, to show the step that failed | **same** |
| Phone: state words | a chip ("done", "running", "waiting its turn") before the name | the mark, with the state in words for a screen reader | **deviation** (log: the one stepper marks a row's state, as on the desk) |

## The survey (2026-10-12): every operation that runs steps or devices

| Operation | Page | Before | Now |
|---|---|---|---|
| Save (one or many) | `_save.html` | C605's stepper, its steps across at every width | the one stepper |
| Deploy, one device | `_deploy.html` | `job_stepper`, a list down at every width | the one stepper |
| Deploy several: Devices' Deploy, the monitoring profile's Apply, IP SLA's Send, Coverage's Deploy missing, History's Re-apply | `_apply_job.html` | one line per device, "being applied" | the one stepper: the pipeline's steps per device, their times kept when each ends |
| Restore | `_restore.html` | `job_stepper` | the one stepper |
| Reload, and Revert by reload | `_reload.html` | `job_stepper` | the one stepper |
| Rotate a credential | `_rotate.html` | `job_stepper` | the one stepper |
| Adopt | `_adopt.html` | `job_stepper` | the one stepper |
| Update | `_update.html`, `nmas_update.js` | its own stepper, drawn by script | the one stepper: the updater's steps (`update_op.STEPS`, `run_card`), each one's state set by the script from the updater's record (`drawSteps`), the row's group with them |
| Capture | `_capture.html` | "Reading now" | the one stepper: its declared steps (`CAPTURE_STEPS`), the read running for the job's time |
| Onboarding and first boot | `pending.html` | its own five-step list | the one stepper: board M's five steps (`onboard.LIFECYCLE`), "Waiting for it" running with the ZTP stage as its note; each step's explanation kept under it as text |
| Verify, onboarding's arrival | `_onboard_pending.html` | a busy button, then the result | one request; its result on the one stepper: phase two's nine steps (`onboard.PHASE_TWO_STEPS`, `phase_two_run`), the step it stopped at (`stopped_at`) failed with its reason, the rest not reached |
| NetBox import and removal | `_netbox_job.html` | "phase, n of m devices" in words | the one stepper: the phases `netbox_client` reports (`netbox_jobs.PHASES`, `run_card`), an import's re-check done first, the step's counts as its note; the card redraws as the phase moves (`op_progress.on_phase` announces `netbox`), never on a timer |
| Show commands runs | `_sc_result.html` | a bar and counts, then the answers grouped | the component's bar and counts (`run_summary`): devices answered, still reading, failed; the rows are the answers (below) |
| The logging-path test | `_lp_result.html` | two bars and counts | the component's bar and counts, "Lines sent" then "Lines received"; the rows are the arrivals (below) |
| Persist | `_persist.html` | a busy button, then the result | one request, so nothing to watch while it runs; its result on the one stepper: the stages it reached (`persist_op.STEPS`, the hold's trail kept), finished as its outcome says |
| Retire | `_retire.html` | the result, its done and remaining steps as lists | one request; its result on the one stepper: the plan's steps (`retire.STEP_WORDS`, `result_run`), already done, done, failed with its error, or not reached; a refusal before any step draws none |
| Template approve | `_template_op.html` | the result | does not fit (below) |
| DHCP writes (subnets, reservations, exclusions) | `_dhcp_subnet.html`, `_dhcp_reserve.html`, `_dhcp_exclusion.html` | the result, its steps in prose | one request; its result, done or refused, on the one stepper: the one write path's five steps (`dhcp_page.WRITE_STEPS`, `write_run`; each apply notes the step it reached), a failure with what the rollback did. The refusal's first words follow the step reached (C723) |

Not counted: a preview's program and gates, a settings card's Test results and setup steps
(`set-steps`: what a confirm will do, or a check's outcomes, not progress over time); Seed's,
Revert's and Retry's intent commits, template edits and bulk intent, which have no device step
to watch; today's (v1) operations, which retire at cutover; the background readers, which no
person starts.

## Where a stepper does not fit

Each is in tests/test_one_stepper.py with the same reason (`DOES_NOT_FIT`, `SUMMARY_ONLY`), and
in docs/STANDING_APPROVAL_LOG.md.

- **Template approve** (`_template_op.html`): Approve's check runs in its request, holds no
  device and sends nothing, so there is no running state to watch; its per-device rows are the
  comparison's evidence, every line that failed and where to clear it (board B), where one step
  per device would draw every row done beside a result that says pass or fail. Approve and
  Revoke are a commit each.
- **Show commands and the logging-path test: the bar and counts, not rows of steps**
  (`run_summary`). A Show commands run has one step per device (ask, read the answer), so a row
  of steps says nothing the bar does not; its rows are the answers, grouped where alike (boards
  C, D and C2). The logging-path test sends one line per device and then watches Loki for it:
  its rows are the arrivals with their delay (board F), and its two phases are the bar's two
  labels.
