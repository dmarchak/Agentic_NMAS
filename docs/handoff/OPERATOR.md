# Waiting on the operator

The one queue of everything waiting on the operator (the week plan's "How a session picks its
work", rule 3). Each entry: what is asked, the options, the recommendation, the file to open; 6
lines or fewer. A session adds its question here, marks the plan item `BLOCKED →
OPERATOR.md#<anchor>`, and moves on. When the operator answers, the answer goes under the entry
and the next session unblocks the item and moves the entry to Answered.

## Open

### session-namespace

- **Asked:** a session the loop starts (systemd/cron, AppArmor label `unconfined`) cannot make a
  network namespace, so the commit hook's red-green (`scripts/nmas-red-green` → `nmas-test`)
  says COULD NOT ASK and refuses every commit that changes a test. VS Code's label grants it.
- **Options:** (a) install docs/TESTING.md's `nmas-test` AppArmor profile (sudo, yours), its
  path covering the checkout and `~/nmas-worktrees/*`; (b) start the loop from VS Code's
  terminal; (c) let red-green pass `--allow-unconfined` (a protected guard: your words).
- **Recommendation:** (a). C3886's finished work waits as `~/mercury-runs/c3886-keyed-placeholder.patch`.

## Answered

- **2026-11-23, loop-script:** the script arrived (3f9c6b0d) and the crontab runs it at 03:35.

- **2026-11-23 (evening), rulings on overnight/gui's standing failures** (the plan's Stage 1
  items): C3970 and test_heal_analysis_never_read fixed (cfe043d8, bd09416f); C3886, C4090,
  C4206, C4207 and C4208 as recorded in `docs/handoff/rulings-overnight-gui.md`, carried out by
  Stage 1.
