# Handoff: the run of 2026-11-23, the operator's evening rulings done, Phase 1 in progress

Read CLAUDE.md, then this file, and nothing else to start (docs/handoff/START.md is the
standing prompt). Decisions: `docs/handoff/decisions-2026-11-23.md`. Today's report:
`docs/handoff/reports/2026-11-23.md`. The previous handoff: `docs/handoff/2026-11-22-stopped.md`.

## 1. State: RUNNING. An automatic session carries on with the plan (section 4); it does not exit

**On 2026-11-23 the operator decided the previous handoff's question: option (a), with the
agent making the rulings under their policy** (decisions-2026-11-23.md, first section).
Nothing the plan needs waits on the operator. What does wait on them is in section 3, and it
blocks only a deploy.

- **main is fdaec024** (pushed, branch `rulings/gui-kit`). It holds:
  - overnight/gui with merge/kit-into-main (40e88747);
  - the operator's evening rulings 1 and 2 (cfe043d8, bd09416f);
  - ruling 3's attempt, reverted (7d68fbf3, f68d4f18; C4204);
  - overnight/fastlane-retire, rulings-close-2 and rulings-words, merged after their
    device-write reviews passed (cb50b80a, 827ba673, d24cbdc4).
- **The full suite on d24cbdc4** (12 workers, 816 s): 32,219 passed, 4 failed, 68 skipped:
  - C3886 and C4090, which wait on the operator (rulings file);
  - C4081's modal, a known browser flake that passes alone;
  - test_device_names, fixed in fdaec024.
- **Nothing is deployed:** the suite is not fully green.
- A serial run of fdaec024 (Phase 1's counts) runs in `~/nmas-worktrees/serial`, its log
  `~/mercury-runs/suite/serial.log` (JUnit `serial.xml`). Compare its counts with
  `m.xml` (the 12-worker run of d24cbdc4) and remove the worktree once read.
- Suite logs: `~/mercury-runs/suite/`.

## 2. The operator's standing decisions of 2026-11-23

- **The ruling policy** for a failing test:
  - A behaviour change a record shows the operator decided: update or retire the test
    (Test-Weakened and a registered row, citing the record).
  - No record, and the change looks accidental: a regression, so fix the code.
  - Unclear, or it needs their words: leave it failing and list it in
    `docs/handoff/rulings-overnight-gui.md` (6 lines or fewer each).
  - Every ruling made is one line in the day's decisions file, with its record.
- **Main moves** (fast-forward and push) when the only failures left are the rulings file's.
  **No deploy until the suite is fully green** (then through nmas-deploy, never 02:30 to 03:30
  Denver).
- **The rulings block only the deploy, never the run:** keep working through the plan until
  the 02:30 handover; progress goes in the day's report file, not in chat (the operator,
  2026-11-23 evening).
- **Phase 2's reads:** the assistant uses the same read-only tools a person has, device reads
  included (show, show_config, ping, traceroute, and Mercury's own reads: `fixit_reads.FAMILY`'s
  operations).
  - They run through Mercury's tools, never directly.
  - They are never gated, and each is recorded in History as a person's would be.
  - Only device changes go through the gated hand-off flows.
  - `docs/design/assistant.md` says so (amended 2026-11-23).

## 3. Waiting on the operator (blocks only a deploy)

- `docs/handoff/rulings-overnight-gui.md`:
  - C3886's design, after its HIGH (C4204);
  - C4090's capture, blocked by the config-read hook;
  - the reviews' C4206 to C4208.
- All the owed device-write reviews are done (decisions-2026-11-23.md, ruling 5).
- Fix next (mine, not the operator's): C4205 (Save's "runs on" line should follow the
  Customize… ticks).

## 4. The plan (the operator's, 2026-11-22; word for word in section 2 of docs/handoff/2026-11-22.md)

**Now: Phase 1, fast suite, in progress.** The goal: under 10 minutes locally, with the same
pass, fail and skip counts serial and parallel (xdist; fix tests that share state).
- **Done** (branch `rulings/gui-kit`):
  - bd1cd9ae (C4201): `scripts/nmas-workers` `MAX_WORKERS` 4 to 12, CI's `--cap 4` sizing
    unchanged. test_ai_never parses each file once a run (627 to 11 worker-seconds).
  - 0b27eee9 (C4202): test_mercury_cli's load flake.
- **Measured:**
  - 4 workers: 1,516 s, 5,735 worker-seconds.
  - 11 workers: 913 s.
  - 12 workers, on bd1cd9ae: 846 s, 8,578 worker-seconds, lowest MemAvailable 5.5 GiB from
    about 16 GiB free.
  - More workers inflate each test's time, so the next lever is the slowest tests (worker
    seconds at 11 workers): test_v2_layout_in_a_browser 265, test_ai_intent_change 227,
    test_profile_apply_v2 177, test_live_merge 133, test_console_records_at_rest 117,
    test_source_index 108 (one test, 107 s), test_v2_context_is_drawn 92 (its floors 81 s),
    test_no_utc_drawn 80 and test_display_names_drawn 77 (each one walk test).
  - The scratch tool that reads a JUnit file's worker-seconds was not committed.
- **Next:**
  1. Read the serial run (section 1) against the 12-worker run's counts. Fix each test whose
     outcome differs (shared state; C4200 is a known case, its victims already isolated).
  2. Speed up the slowest tests above, without changing what they assert, until a full run
     is under 600 s. Measured on 2026-11-23:
     - test_source_index's walks survey takes 46 s. The cost is the analysis, re-run in three
       export rounds; the parse is cached since 88ea4887.
     - test_ai_intent_change's 116 s is about 1.4 s in each of 81 tests: a per-test fixture.
       Widening that fixture's scope risks shared state; measure what it builds first.
  3. Then Phase 2: the assistant to the amended design note.
- **ci.yml:** no change is needed. CI already runs five shards (`scripts/nmas-shards`) at
  `--cap 4`.
- A full run needs `NMAS_TEST_TIMEOUT` over its length: nmas-test's default session bound is
  300 s.

**Phase 2, the AI assistant**, **Phase 3, GUI usability**, **Phase 4, page performance**: as
section 2 of docs/handoff/2026-11-22.md states, with section 2 above for Phase 2's reads.
