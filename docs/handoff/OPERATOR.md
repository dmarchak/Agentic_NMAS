# Waiting on the operator

The one queue of everything waiting on the operator (the week plan's "How a session picks its
work", rule 3). Each entry: what is asked, the options, the recommendation, the file to open; 6
lines or fewer. A session adds its question here, marks the plan item `BLOCKED →
OPERATOR.md#<anchor>`, and moves on. When the operator answers, the answer goes under the entry
and the next session unblocks the item and moves the entry to Answered.

## Open

### s1-walk

**The s1 walk for C4090's records (about 15 min, tonight).** Two of the three missing records
come from it: `P.reads` (a Fixed incident whose proof is a command-plan run with its reads) and
`F.more` (an open incident with two Automatic saved fixes matching it). Default's self-healing
is in Dry run (read 2026-11-25 16:45 Denver), so no saved fix runs by itself: each runs only on
your press. Never s3; not between 02:30 and 03:30 Denver.

**The cause (the agent's, on the lab host):** one crafted BPDU from h1 into s1 Gi1/0, which BPDU
guard err-disables (the Lab 10 demo's frame, its before/after checks). The agent sends it when
you write "go 1" or "go 2" in chat, and says when Mercury has opened the incident (about 1 to 2
min: the alert, then the incident).

1. **"go 1".** Wait for the agent's "incident 1 open".
2. Open Incidents, then the new incident "s1 Gi1/0 err-disabled by BPDU guard". The card offers
   **Fix with saved script: BPDU guard recovery (access ports)**. Press it. Wait for the card to
   say Fixed (its run's verify takes about 30 s to 1 min). This is record 1: the agent captures it
   (the run's proof, "show proof", with its reads).
3. On the same card, **Save this fix so Mercury handles it automatically?** is offered. Open
   **Customize…**, untick **port role**, set the name to **BPDU guard recovery (any port)**, and
   press **Save**. It is saved Automatic (saving is the approval); the line above Save says what
   it runs on now (it should say no other open incident).
4. **"go 2".** Wait for the agent's "incident 2 open".
5. Open the new incident. The card offers **Fix with saved script: BPDU guard recovery (access
   ports)** and, beside it, **Fix with saved script: BPDU guard recovery (any port)**: the second
   is record 2. **Write "hold" in chat and wait** for the agent's "captured" before pressing.
6. Press either one. Wait for Fixed. The walk is done; the agent captures the last record and lands
   C4090.

**If something differs:** the card offers no saved script (the match did not hold), or a press is
refused: write what the card says in chat and stop; nothing is retried.

**The third record cannot be made by any walk, and needs your word:** `P.net_zero.lines` draws the
lines a command plan's run changed, inside a Fixed incident's proof. A run whose configuration
after differs from before is rolled back and refused (`command_plan_run`'s net-zero check), so no
Fixed proof ever holds such lines. **Options:** (a) your words to declare that loop in
`EMPTY_IN_FIXTURE` with that reason (a Test-Weakened trailer and its row); (b) remove the loop
from `_inc_proof.html` (the words stay, the lines go; a board record compared again).
**Recommendation:** (a): the card keeps drawing the lines if a future runner ever keeps a
differing run.

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

## Answered

### c4075-smoke

- **Asked (2026-11-25):** your ruling 8 has the deploy's smoke pass `--expect-local-account-off`,
  but `nmas-deploy` runs its smoke only on a fast-lane deploy, and the fast lane is retired. A
  `--wait` deploy runs no smoke of its own. **Options:** (a) `--wait` runs the smoke with the
  flag and reverts on red, as the fast lane did; (b) keep the hand-run check after a deploy.
  **Recommendation:** (a). It needs your words, because it changes how every deploy ends.
  File: C4075's row, docs/OPEN_FINDINGS.md.
- **Answered 2026-11-25 (16:37 Denver), the operator's words (for the commit's Approved-By):** "c4075-smoke: (a). I authorise changing scripts/nmas-deploy so that a --wait deploy runs the smoke check with --expect-local-account-off and reverts the deploy if it's red. No other change to nmas-deploy."

### gui-direction

- **Asked:** which GUI direction to build (the week plan's one big decision). Three drawn on the
  same six screens: A Workbench (list and detail), B Inbox (triage first), C Document (one
  readable page per object). Open `design/proposals/README.md` (the comparison), or the zip
  `design/proposals.zip` (mockups, shots at both sizes, the research and inventories).
- **Options:** A, B, C, or C with B's Needs attention queue and step timeline.
- **Recommendation:** C with B's queue and timeline (about 30 build days by its estimate).
- **Answered 2026-11-25 (16:37 Denver), the operator's words:** "gui-direction: C with B's Needs attention queue and step timeline. One change: the assistant is a side panel the page reflows around, not a drawer over a dimmed page. Build order, each step deployed when green: 1. the shared frame (layout, type, the side panel mount, the timeline component); 2. Settings; 3. home and Needs attention, with B's queue; 4. the incident page; 5. the device page; 6. the rest. Steps 1–5 by Nov 30 where you can. Add these to the week plan's Stage 5 in this order, ahead of Stage 6." Written into docs/plan/week-2026-11-23.md's Stage 5.

### c4135-age

- **Asked (2026-11-24):** C4135 (B, Lab 9: blocks): Analyse this network reads the latest kept
  snapshot whatever its age (one 9 days old on 2026-11-20); the bar shows "collected <time>" but
  never says it is old. The row leaves the age to you. **Options:** (a) older than the
  collection's own bound × 2.5 (measured: the agent proposes the number); (b) 1 hour; (c) 24 hours.
  Past it, the card says "collected N days ago: Collect now first" and Analyse offers Collect now.
  **Recommendation:** (b). File: templates/v2/_sdn_analyse.html, modules/sdn/analyst.py.
- **Answered 2026-11-25 (16:37 Denver), the operator's words:** "c4135-age: (b), 1 hour."

### c2518-runner

- **Asked (2026-11-24):** C2518 (A) layer 1, the local CI runner: act given no Docker socket
  (`--container-daemon-socket -`), empty `--env-file`/`--secret-file`/`--var-file`, and started in an
  empty folder so no `.actrc` from the commit is read. Built as `~/mercury-runs/c2518-runner.patch`
  (scripts/nmas-local-ci, 53 lines, not committed). scripts/nmas-local-ci is a guard path
  (scripts/nmas-guard-check, WHOLE), and the row holds your 2026-11-05 design only in paraphrase.
  **Options:** (a) your words for this change, quoted in its Approved-By; (b) leave it until layer 2.
  **Recommendation:** (a); the timer stays off either way.
- **Answered 2026-11-25 (16:37 Denver), the operator's words (for the commit's Approved-By):** "c2518-runner: (a). I authorise ~/mercury-runs/c2518-runner.patch's change to scripts/nmas-local-ci: no Docker socket, empty env, secret and var files, started in an empty folder. No other change. The timer stays off."

### ci-shards-gate

- **Asked (2026-11-24):** your 10-shard words cover ci.yml and scripts/nmas-shards, but the gate
  runs CI's shards argument for argument (C349): tests/test_nmas_gate.py holds
  `nmas-shards.matrix(...) == nmas-gate.SHARDS`, so ten shards also changes scripts/nmas-gate
  (`SHARDS`, `BROWSER_SHARDS`, the memory `WAVES`), a protected guard. ci.yml itself needs no
  edit (its matrix is nmas-shards' output; `-n auto` is already 4 on a 4-core runner).
  **Options:** (a) your words for nmas-gate's shard constants and waves too; (b) CI's ten split
  from the gate's five, which drops C349's parity (a guard test changed: your words as well).
  **Recommendation:** (a).
- **Answered 2026-11-25 (16:37 Denver), the operator's words (for the commit's Approved-By):** "ci-shards-gate: (a). I authorise changing scripts/nmas-gate's SHARDS, BROWSER_SHARDS and memory WAVES to match ten CI shards, keeping C349's parity. No other change to nmas-gate."

### c4090-confirms

- **Asked (2026-11-24):** C4090's records need two confirms only a verified person can give:
  a command plan's run approved by hash (its Fixed run with a net-zero difference and its reads),
  and two saved fixes matching one incident. The host takes identity only from the access
  proxy's assertion (no local exemption), and a confirm is a person's decision (CLAUDE.md), so
  the agent cannot press them. **Options:** (a) the agent writes a walk sheet for s1 (cause, the
  clicks, about 10 min), you press the confirms, the agent captures masked and lands C4090;
  (b) another way you name. **Recommendation:** (a). Meanwhile the agent does the CI shards.
- **Answered 2026-11-25 (16:37 Denver), the operator's words:** "c4090-confirms and c4090-records: (a). Write the s1 walk sheet in OPERATOR.md now (cause, the exact clicks, what to wait for, about 10 min). I'll press the confirms tonight. Then capture masked, land C4090, and deploy on a fully green CI." The sheet is below, under Open, as `s1-walk`.

### c4090-records

- **Asked:** C4090's three loops are the last red once the patches land (stacked suite, 2026-11-24);
  they need records no store holds (a Fixed command-plan run with a net-zero difference and its
  reads; two saved fixes matching one incident), and your ruling says real captures only.
- **Options:** (a) wait for them to occur; (b) the agent makes them on the sandbox device through
  Mercury, then captures them masked; (c) your words for EMPTY_IN_FIXTURE.
- **Recommendation:** (b), outside the backup window, never on s3. File: C4090's row, docs/OPEN_FINDINGS.md.
- **Answered 2026-11-25 (16:37 Denver):** with c4090-confirms, the same words ("c4090-confirms and c4090-records: (a)"): the records are made by the operator's walk on s1 (the sheet, `s1-walk`) and captured masked, which is this entry's option (b) in effect; s1 is the sandbox device, never s3.

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
