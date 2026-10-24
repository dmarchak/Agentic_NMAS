# C1579: Verify's stepper drawn from the confirm and filled live (design note, not built)

The register's row C1579: a long operation shows no progress until it is nearly or wholly
done. The console survey, the kick-start and the one-decision out-of-band run were built
this way from the start: the confirm answers with THE stepper at once, and each step fills on
`device_progress`. Verify (onboarding's phase two) is not built this way. Its confirm runs
phase two inside the POST and draws the nine-step stepper only from the finished result, so
Lab 9's R8 recording showed only "Verifying…" on the button, then the stepper already
complete. Written 2026-10-24 by the overnight run, which judged the move unsafe to
half-build in one night (below), for the operator's review.

## What moves

1. **The run becomes a job.** `onboard_v2.verify` (today `routes/onboard.verify_run`, then
   `onboard.verify_device`, in the request) starts `capture_job.start(...)` with
   `work = verify_run(...)`. It answers at once with the pending card in a new `running` state:
   Preview and Confirm done, Hold running from the confirm, every one of `PHASE_TWO_STEPS` not
   yet run. Each job announces `ANNOUNCE_KEYS`, and `invalidation.ANNOUNCERS` declares it, as
   the console runs' does.
2. **Each step notes itself on the hold.** `verify_device` notes each of `PHASE_TWO_STEPS` as
   it begins (`device_actions` `note`, as `console_ztp` does). A `run_steps` helper reads the
   hold's progress into the stepper's rows (`device_actions.stepper(..., starts=True)`), as
   `routes/console_ztp_v2.run_steps` does.
3. **The card listens.** `_onboard_pending.html`'s running state redraws on `device_progress`
   (its own key) and on the job's end. It then reads the run's recorded result: the job
   first, then the record (C642's order). It shows the result as today's `verified` state
   draws it, with the next step (`_next_intent`) computed then.
4. **What stays the same.** The hold is taken inside `verify_device`, across processes, as
   today. The route's gate stays a verified person's confirm (`route_gates`), the invalidation
   map keeps the same keys, and the preview is unchanged.

## Why not tonight

- **The hold in a thread.** The job runs on its own thread, and the device's hold must be
  taken there and released however it ends. A thread that dies between the rotation and the
  persist leaves a device rotated and pending; today the request's own failure handling
  covers that. The job's failed state must name the step it stopped at and what to do,
  which the record already carries but nothing draws yet.
- **Test churn, stated as a cost:** about 120 tests across tests/test_onboard_v2.py,
  test_onboard_run_results.py, test_ztp_onboarding.py, test_record_not_written_is_drawn.py,
  test_every_recorder_names_its_person.py and test_onboard_board_m.py post Verify and read its
  result in the same answer. Each must wait for the job (the `_wait(job)` pattern
  tests/test_console_ztp_v2.py uses), and their premises must be corrected one by one, never
  loosened.
- **The pending page is board-built** (docs/fidelity/pending.md). The Verify-result region
  changes from "the finished stepper" to "the stepper from the confirm", so it needs a new
  shot (tests/test_board_shots.py `test_pending_page`) and a fresh comparison.

## Tests it needs

- The confirm's answer draws THE stepper before the first step finishes: a job held at
  `verify`, then at `rotate` (as tests/test_console_ztp_v2.py `TestTheStepperFromTheConfirm`).
- Every declared step is a note the code makes (that class's AST check).
- A job that fails mid-run is drawn failed, naming its step, and the device stays pending;
  a lost job (no record) is said.
- The busy-control and swap checks for the new running state.

## Size

**M to L.** The job and the notes take about half a day; the card's running state and its
redraw, about half a day; the tests' premises, about a day; the shot and the comparison,
half a day; the manual's Verify section, an hour. The NetBox import's re-check (moved into
its thread) is a separate, smaller piece (S); Save All, Retire and Seed intent are unchecked.
