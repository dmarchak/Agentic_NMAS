# Handoff: the run of 2026-11-23, Phase 0 done, Phase 1 next

Read CLAUDE.md, then this file, and nothing else to start (docs/handoff/START.md is the
standing prompt). Decisions: `docs/handoff/decisions-2026-11-23.md`. Today's report:
`docs/handoff/reports/2026-11-23.md`. The previous handoff: `docs/handoff/2026-11-22-stopped.md`.

## 1. State: RUNNING. An automatic session carries on with the plan (section 4); it does not exit

**On 2026-11-23 the operator decided the previous handoff's question: option (a), with the
agent making the rulings under their policy** (decisions-2026-11-23.md, first section).
Nothing the plan needs waits on the operator. What does wait on them is in section 3, and it
blocks only a deploy.

- **main is 120abc10** (pushed): overnight/gui fast-forwarded, merge/kit-into-main merged on it
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

**Next: Phase 1, fast suite.** Under 10 minutes locally, with the same pass, fail and skip
counts serial and parallel (xdist; fix tests that share state). ci.yml is protected: write the
change it would need here for the operator. The lever, as measured:
- About 6,000 worker-seconds a run at 4 workers (1,516 s on 2026-11-23, 32,253 tests).
- `scripts/nmas-workers` caps local runs at 4 (`MAX_WORKERS`). It is not a protected guard,
  but `scripts/nmas-test`, which asks it, is.
- Its memory formula allows about 17 on a free laptop (24 CPUs, 30 GiB); about 15 workers
  would reach 10 minutes if the run scales.
- A full run needs `NMAS_TEST_TIMEOUT` over its length: nmas-test's default session bound is
  300 s.
- C4200 (a test leaving an incident in a worker's state) is one shared-state case already known.

**Phase 2, the AI assistant**, **Phase 3, GUI usability**, **Phase 4, page performance**: as
section 2 of docs/handoff/2026-11-22.md states, with section 2 above for Phase 2's reads.
