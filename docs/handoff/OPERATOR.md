# Waiting on the operator

The one queue of everything waiting on the operator (the week plan's "How a session picks its
work", rule 3). Each entry: what is asked, the options, the recommendation, the file to open; 6
lines or fewer. A session adds its question here, marks the plan item `BLOCKED →
OPERATOR.md#<anchor>`, and moves on. When the operator answers, the answer goes under the entry
and the next session unblocks the item and moves the entry to Answered.

## Open

### loop-script

- **Asked:** the nightly loop script, `tools/nightly/mercury-loop.sh`. The setup message of
  2026-11-23 said "with exactly this content", but its body read `<paste the script from my
  message>`, so no script was added and the crontab still runs `mercury-session.sh`.
- **Options:** paste the script (the next session adds it, makes it executable, commits it and
  moves the crontab line, 03:35 as now), or keep `mercury-session.sh`.
- **Recommendation:** paste it; until then the 03:35 session runs as today.

## Answered

- **2026-11-23 (evening), rulings on overnight/gui's standing failures** (the plan's Stage 1
  items): C3970 and test_heal_analysis_never_read fixed (cfe043d8, bd09416f); C3886, C4090,
  C4206, C4207 and C4208 as recorded in `docs/handoff/rulings-overnight-gui.md`, carried out by
  Stage 1.
