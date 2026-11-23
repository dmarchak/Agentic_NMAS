# Handoff: the week plan's Stage 1 in progress (2026-11-23)

Read CLAUDE.md, this file and the standing plan, `docs/plan/week-2026-11-23.md`, then
`docs/handoff/OPERATOR.md` (what waits on the operator). docs/handoff/START.md is the standing
prompt. Decisions: `docs/handoff/decisions-2026-11-23.md`. Today's report:
`docs/handoff/reports/2026-11-23.md`.

## 1. Where the plan stands

**Stage 1 (green main and deploy) is in progress.** Its first items are the operator's rulings
of 2026-11-23 (late evening), recorded in `docs/handoff/rulings-overnight-gui.md`. Take them in
the plan's order:
1. **C3886:** the masking placeholder carries a short keyed fingerprint of the secret (for
   example `<secret:7f3a>`), so running against startup tells different secrets apart. Reads
   stay recorded and masked, and the secret is never shown. Then the save check goes through
   the reads engine again: 7d68fbf3's shape, reverted in f68d4f18 for C4204. Its device-write
   review comes before any deploy.
2. **C4090:** extend `scripts/nmas-config-read` with a read-only, masked reader for heal and
   fix-it records (the operator authorised it), capture the ten loops' real records with it,
   and fix the test.
3. **C4207 and C4208:** the interim's can't-fix only stands and gives R1 its start; an
   attached tail's R1 start fires no scripts. **C4206:** the behaviour stands; correct the
   record's wording (9f456d31's claim, in the register).
4. Then the rest of Stage 1 (C4205, C4081, C4200, C4195, C4196), a fully green full suite,
   and the deploy.

**Stage 2's first item is already running:** a serial full run of fdaec024 in
`~/nmas-worktrees/serial`, logging to `~/mercury-runs/suite/serial.log` (JUnit `serial.xml`),
started 16:14 Denver, expected about 20:30. Compare its counts with `m.xml`, the 12-worker run
of d24cbdc4, then remove the worktree.

## 2. State

- **Branch `rulings/gui-kit`** (pushed) is main plus this handoff and two Phase 1 commits.
  - **main is e201a705**: overnight/gui with the kit's merge (40e88747), the evening rulings
    (cfe043d8, bd09416f), C3886's attempt reverted (f68d4f18), and the three reviewed branches
    merged (cb50b80a, 827ba673, d24cbdc4).
  - Work and commit in `~/nmas-worktrees/rulings-gui-kit`, outside the workspace.
- **The full suite on d24cbdc4** (12 workers, 816 s): 32,219 passed, 4 failed:
  - C3886 and C4090 (Stage 1 above);
  - C4081's modal, a known flake (Stage 1);
  - test_device_names, fixed in fdaec024.
- **Nothing is deployed.**
- **Suite runs:** at least 12 workers; `NMAS_TEST_TIMEOUT` over the run's length (nmas-test's
  default session bound is 300 s). Measured: 816 s at 12 workers, 1,516 s at 4.
- **The nightly loop script** (`tools/nightly/mercury-loop.sh`) is not added: its content
  never arrived (OPERATOR.md#loop-script). The crontab still runs `mercury-session.sh` at
  03:35.

## 3. The operator's standing decisions of 2026-11-23

- The ruling policy:
  - A behaviour change the operator decided, on record: update or retire the test, citing
    the record.
  - No record and accidental: fix the code.
  - Unclear: ask in OPERATOR.md and move on.
- Main moves when only the operator's open items fail. Deploy only on a fully green suite,
  through nmas-deploy, never 02:30 to 03:30 Denver.
- The assistant (Stage 4) uses a person's read-only tools, device reads included.
  - Through Mercury's tools, never gated, each recorded in History.
  - Only device changes go through the gated hand-offs (`docs/design/assistant.md`).
- Keep working until near the context limit or 02:30. Progress goes in the report.
- Write the STATE word on exit (START.md).
