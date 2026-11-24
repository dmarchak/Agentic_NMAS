# Waiting on the operator

The one queue of everything waiting on the operator (the week plan's "How a session picks its
work", rule 3). Each entry: what is asked, the options, the recommendation, the file to open; 6
lines or fewer. A session adds its question here, marks the plan item `BLOCKED →
OPERATOR.md#<anchor>`, and moves on. When the operator answers, the answer goes under the entry
and the next session unblocks the item and moves the entry to Answered.

## Open

### claude-md-0230

- **Asked:** CLAUDE.md is yours (the `claude-no-claude-md-edits` hook refuses the agent's edits), so
  the 02:30 rule waits for you to paste it. Put these lines first under "### Working method"
  (checked: tests/test_claude_md.py's `unenforced` finds none unenforced, its paths exist):

  ```
  - **Sessions run until 02:30 Denver (the operator, 2026-11-24): never end a turn before 02:30
    America/Denver, and never stop to report, summarise or ask. Progress goes in the day's
    report file; a question goes in docs/handoff/OPERATOR.md, its plan item marked BLOCKED, and
    the next item is taken. At 02:30 stop at a clean point, update docs/handoff/latest.md and the
    day's report as the morning session's handoff, then end the turn. Cost: no progress shown in
    chat until the handoff. Prevents: work stopping for a report, or for an answer nobody is
    there to give.** [not mechanised]
  ```
- **Also:** the fast lane is retired (2026-11-24), so the two rules "Temporary fast lane" and
  "Temporary skip mode within the fast lane" under "### Git, the gate and deploys" are stale: delete
  them both. After you paste, the agent commits CLAUDE.md as you left it.

### gui-direction

- **Asked:** which GUI direction to build (the week plan's one big decision). Three drawn on the
  same six screens: A Workbench (list and detail), B Inbox (triage first), C Document (one
  readable page per object). Open `design/proposals/README.md` (the comparison), or the zip
  `design/proposals.zip` (mockups, shots at both sizes, the research and inventories).
- **Options:** A, B, C, or C with B's Needs attention queue and step timeline.
- **Recommendation:** C with B's queue and timeline (about 30 build days by its estimate).

### c4090-records

- **Asked:** C4090's three loops are the last red once the patches land (stacked suite, 2026-11-24);
  they need records no store holds (a Fixed command-plan run with a net-zero difference and its
  reads; two saved fixes matching one incident), and your ruling says real captures only.
- **Options:** (a) wait for them to occur; (b) the agent makes them on the sandbox device through
  Mercury, then captures them masked; (c) your words for EMPTY_IN_FIXTURE.
- **Recommendation:** (b), outside the backup window, never on s3. File: C4090's row, docs/OPEN_FINDINGS.md.

## Answered

### session-namespace

- **2026-11-24:** no longer blocking. The operator retired the overnight loop,
  and a session from VS Code (whose label makes the namespace) landed every waiting patch,
  eac546ae to d030f04a, the hook's red-green run on each. Its option (a), the AppArmor profile,
  stays open only if a session outside VS Code is wanted again.

- **2026-11-23, loop-script:** the script arrived (3f9c6b0d) and the crontab runs it at 03:35.

- **2026-11-23 (evening), rulings on overnight/gui's standing failures** (the plan's Stage 1
  items): C3970 and test_heal_analysis_never_read fixed (cfe043d8, bd09416f); C3886, C4090,
  C4206, C4207 and C4208 as recorded in `docs/handoff/rulings-overnight-gui.md`, carried out by
  Stage 1.
