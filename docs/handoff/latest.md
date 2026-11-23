# Handoff: the run of 2026-11-23, Phase 0 done, Phase 1 in progress

Read CLAUDE.md, then this file, and nothing else to start (docs/handoff/START.md is the
standing prompt). Decisions: `docs/handoff/decisions-2026-11-23.md`. Today's report:
`docs/handoff/reports/2026-11-23.md`. The previous handoff: `docs/handoff/2026-11-22-stopped.md`.

## 1. State: RUNNING. An automatic session carries on with the plan (section 4); it does not exit

**On 2026-11-23 the operator decided the previous handoff's question: option (a), with the
agent making the rulings under their policy** (decisions-2026-11-23.md, first section).
Nothing the plan needs waits on the operator. What does wait on them is in section 3, and it
blocks only a deploy.

- **main is c9fe36a2** (pushed; Phase 0 moved it to 120abc10, Phase 1's first step to
  c9fe36a2): overnight/gui fast-forwarded, merge/kit-into-main merged on it
  (40e88747), the rulings and the merge's fix-forward on top (branch `rulings/gui-kit`).
- **The full suite on 120abc10** (4 workers, 1,516 s): 32,173 passed, 12 failed, 68 skipped.
  The 12 are exactly `docs/handoff/rulings-overnight-gui.md`'s. Every other test is green.
- **Nothing is deployed:** the suite is not fully green.
- Worktrees (outside the workspace): `~/nmas-worktrees/rulings-gui-kit` (the branch, clean),
  `~/nmas-worktrees/integrate-gui-kit` (40e88747, done with). Suite logs: `~/mercury-runs/suite/`.

## 2. The operator's standing decisions of 2026-11-23

- **The ruling policy** for a failing test:
  - A behaviour change a record shows the operator decided: update or retire the test
    (Test-Weakened and a registered row, citing the record).
  - No record, and the change looks accidental: a regression, so fix the code.
  - Unclear, or it needs their words: leave it failing and list it in
    `docs/handoff/rulings-overnight-gui.md` (6 lines or fewer each).
  - Every ruling made is one line in the day's decisions file, with its record.
- **Main moves** (fast-forward and push) when the only failures left are the rulings file's.
  **No deploy until the suite is fully green.**
- **Phase 2's reads:** the assistant uses the same read-only tools a person has, device reads
  included (show, show_config, ping, traceroute, and Mercury's own reads: `fixit_reads.FAMILY`'s
  operations).
  - They run through Mercury's tools, never directly.
  - They are never gated, and each is recorded in History as a person's would be.
  - Only device changes go through the gated hand-off flows.
  - `docs/design/assistant.md` says so (amended 2026-11-23).

## 3. Waiting on the operator (blocks only a deploy)

- `docs/handoff/rulings-overnight-gui.md`: 4 causes, 12 tests (C3970, test_heal_analysis_never_read,
  C3886, C4090).
- The device-write review of 9f456d31 (C4194: the conditions a saved fix may match), owed before
  any deploy.
- overnight/fastlane-retire's 21 later commits, rulings-words and rulings-close-2 (2026-11-18)
  are not merged. They hold device-write commits whose independent reviews are owed.

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
  1. Done: the full run of c9fe36a2 at 12 workers took 809 s (32,174 passed, the rulings
     file's 12 failed, 68 skipped), and main was fast-forwarded to c9fe36a2 and pushed.
  2. A serial run (`-p no:xdist`, about 100 minutes; start it before 00:20 Denver) and
     compare its counts with the parallel run's. Shared state found is fixed (C4200 is one
     case, its victims already isolated).
  3. Speed up the slowest tests above, without changing what they assert, until a full run
     is under 600 s.
- **ci.yml:** no change is needed. CI already runs five shards (`scripts/nmas-shards`) at
  `--cap 4`.
- A full run needs `NMAS_TEST_TIMEOUT` over its length: nmas-test's default session bound is
  300 s.

**Phase 2, the AI assistant**, **Phase 3, GUI usability**, **Phase 4, page performance**: as
section 2 of docs/handoff/2026-11-22.md states, with section 2 above for Phase 2's reads.
