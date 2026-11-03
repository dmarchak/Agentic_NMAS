# The existing-test audit (workstream TA)

**The operator's direction, 2026-11-03 ~07:5x UTC.** Goal: an honest count of tests that do not
fulfil their purpose. The agent builds the mechanical part. A reviewer outside the agent's
context classifies the results, and nothing is fixed until then. The workstream runs alongside
Phase 8, not after it (PHASE8_PLAN 0.3).

## The tools

Each tool is committed, and each run's raw output is committed beside it under
`docs/test_audit/<tool>/<UTC date>/`. A tool counts only once its canary has passed (below).

| Tool | What it lists | How |
|---|---|---|
| **(a) Deletion** | every test that still passes with the product functions it covers stubbed out | for each test, the functions its run executes (the coverage nightly's per-test contexts, `scripts/nmas_mutation.py`'s `load_reach`); each replaced by a stub raising `NotImplementedError`, in a throwaway worktree; the test run alone |
| **(b) Mutation, per test** | each test that kills zero mutants of the code it covers, with every test's kills | mutmut, one mutant at a time, each mutant's killing tests recorded. **Full** on deploy, credentials and secrets, drift, Needs attention, SDN detect and respond, egress, and every Phase 8 module (`modules/ai/`, `modules/sdn/`); **sampled** elsewhere (a recorded seed, a stated share) |
| **(c) Static patterns** | tautologies, assertion-free tests, mocks of the module under test, swallowed exceptions, status-only asserts | parsing each test file (`ast`), never matching text |
| **(d) Dead** | always skipped or xfail, uncollected, shadowed names | pytest's own collection (`--collect-only`) against the parsed definitions; a skip read from its decorator or call |
| **(e) Fakes** | each fake whose answers differ from a recording of the real service it stands for | each fake (`tests/*fake*`, the classes and functions tests use in place of a client) asked the recording's requests, its answers compared field by field |

## The canary, first

A throwaway branch, never pushed, plants at least one known-bad test of each shape the tools
look for, at least 8 in all:
- a tautology (`assert x == x`);
- an assertion-free test;
- a test mocking the module it tests;
- a swallowed exception (`try: … except Exception: pass`);
- a status-only assertion;
- an always-skipped test;
- a shadowed name (two functions of one name);
- a test that passes with its product function stubbed;
- a test that kills no mutant of its function;
- a fake diverging from its recording.

**Every tool must flag its own plants before its results count.** The canary's result (each
plant, the tool that should flag it, flagged or missed) is reported first and committed with
the tool. A tool that misses a plant is fixed before its results are read.

## Suspects named before any tool runs

- **40 tests coupled to one recording's label** (the operator, 2026-11-03, from C2313): the
  Lab 8 walk's floods (walk-flood-1 and walk-flood-2), recorded as "flood", were the fixture of
  40 tests across six files. When the label's meaning changed (one large-packet sender
  watched, option (i)), all 40 failed together:
  - tests/test_sdn_source_from_topology.py (11);
  - tests/test_sdn_auto_confirm_refused.py (8);
  - tests/test_sdn_incidents.py (7);
  - tests/test_sdn_auto_preview_failed.py (5);
  - tests/test_sdn_auto_inferred_source.py (5);
  - tests/test_sdn_classify_walk_cases.py (4).

  Each test's own id is in C2313's commit, under its `Test-Weakened:` trailer. The question for
  the reviewer is how many of them test a flood's handling at all, rather than borrowing a
  flood as a fixture.

## The output

No classification and no fixes:
- **one table per tool:** test id, module, what it shows;
- **a combined suspects list:** each test any tool flagged, and which tools;
- **the total test count** (pytest's collection), so each count has its denominator.

## What it costs, measured before each run

- **(c), (d), (e):** minutes.
- **(a):** one run a test with its functions stubbed. On about 20,000 tests, at a measured
  seconds each, hours. It is sharded and reported on its first shard's measured time.
- **(b), full on the named modules:** thousands of functions. The last weekly run (#67) needed
  about 2 hours for 30 functions and 1,806 mutants. Its estimate is measured on a first module
  and stated before the rest runs. The weekly run has not completed a measurement since 10-25
  (C1651), so its clean run is fixed first.

## The independent review

A snapshot of the repository at a named commit is made for the reviewer
(`~/Documents/nmas-reports/snapshots/<sha>/`, by `git archive`, no history). The audit's
committed outputs are under `docs/test_audit/`.
