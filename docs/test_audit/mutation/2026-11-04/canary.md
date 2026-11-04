# Tool (b), mutation per test: the canary (2026-11-04)

`scripts/nmas-test-audit-mutation --root <canary> --reach <canary>/reach --then
<canary>/reach/then --mutants <canary>/mutants.json --scope canarypkg/fees.py --canary
canarypkg/fees.py::must_die=tests/test_fees.py::test_plant_must_die --null-canary
canarypkg/fees.py::untested=tests/test_fees.py`, in CI's interpreter (3.12.3), `--jobs 2`.

**What the canary is.** It is a package of its own, not the repository's tests:
- `canarypkg/fees.py`: three functions.
  - `fee`, the audited function: four mutants.
  - `must_die`, the run's canary: every mutant of it must be killed.
  - `untested`, the null canary: no test calls it, and every mutant of it must survive.
- `tests/test_fees.py` and `tests/test_plant_import_time.py`: the plants.
- its own `pytest.ini`.
- a reach map in the coverage nightly's JSON shape (`reach/coverage.json`), with the sources as
  that map measured them (`reach/then/`).
- the mutants file (`mutants.json`).

Its files are committed in `docs/test_audit/canary/mutation/` as `<name>.txt`.
`tests/test_test_audit_mutation.py` copies them into a temporary folder under their real names
and gives that folder an index (`tests.source_index.track_all`). It runs this same check on
every run of the suite.

**The mutants are mutmut 3.8.0's**, the generator the weekly run and the irreversible tier's
hand check use. `--generate` makes them by running `python -m mutmut run` as a program:
- in a throwaway folder holding only the modules, the other functions fenced off as the weekly
  run fences them;
- mutmut's copy of each module is read back from `mutants/`;
- the tool imports nothing of mutmut or libcst (tests/test_requirements_lock.py).

The first version called mutmut's generator in-process. Generating again through the program
gave a file identical to the committed one, byte for byte (`cmp`, 2026-11-04). It also gave
the same 204 mutants for the narrowed target. `fee`'s four:

| Mutant | Was | Now |
|---|---|---|
| `canarypkg.fees.x_fee__mutmut_1` | `if amount < 100:` | `if amount <= 100:` |
| `canarypkg.fees.x_fee__mutmut_2` | `if amount < 100:` | `if amount < 101:` |
| `canarypkg.fees.x_fee__mutmut_3` | `return 3` | `return 4` |
| `canarypkg.fees.x_fee__mutmut_4` | `return 0` | `return 1` |

## Plants

| Plant (test id) | Expected | Result |
|---|---|---|
| `tests/test_fees.py::test_plant_fee_kills_all` (asserts `fee(99) == 3` and `fee(100) == 0`) | kills 1, 2, 3, 4 | kills 1, 2, 3, 4 |
| `tests/test_fees.py::test_plant_fee_kills_one` (asserts `fee(50) == 3`) | kills 3 | kills 3 |
| `tests/test_fees.py::test_plant_fee_in_a_child_kills_three` (reads `fee(100)` from a child process) | kills 1, 2, 4 | kills 1, 2, 4 |
| `tests/test_plant_import_time.py::test_plant_killed_in_collection` (its module asserts `fee(100) == 0` at import) | kills 1, 2, 4, in collection | kills 1, 2, 4 |
| `tests/test_fees.py::test_plant_fee_kills_none` (asserts `fee(500) >= 0`) | kills none, **listed** | kills none, listed; judged against 4; the reach check failed it, so it reaches `fee` |
| `tests/test_fees.py::test_plant_fee_fails_unmutated` (asserts `fee(100) == 3`) | fails unmutated, never judged | fails unmutated |

6 plants, 6 with their expected result and no other. The planted weak test is the only test
listed.

**Each mutant's killing tests are all named**, which mutmut's stop at the first failure cannot
give. Mutants 1, 2 and 4: the test that kills all, the child, and the import-time plant. Mutant 3:
the test that kills all, and the test that kills one.

**The canaries.** Both held:
- `must_die`: 2 mutants, both killed by `test_plant_must_die`.
- `untested`: 1 mutant, killed by none of the 5 tests of `tests/test_fees.py` that pass
  unmutated.

Two runs show that each canary stops the run when it breaks, with no result:
- the must-die canary given a test that never calls `must_die`;
- the null canary pointed at `must_die`.

**Measured:**
- the canary's run: 11 pytest runs, about 0.15 s of start-up a run;
- this laptop's, the repository's start-up: about 1.2 s a run (tool (a)'s measurement).

## Runs, and what was fixed

1. **The first run, with the five tests of `tests/test_fees.py`:** every result was as expected.
2. **The import-time plant added:**
   - **What happened:** under mutants 1, 2 and 4, no other test had an outcome.
   - **Why:** pytest given a test id whose file does not collect prints "found no collectors"
     and runs nothing at all, even with `--continue-on-collection-errors`. Reproduced by hand in
     the canary.
   - **The fix:** the asked tests that run left without an outcome, outside the files that did
     not collect, now run again in a second process.
   - **Also corrected:** the plant's own test had asserted `fee(99) == 3`, which kills mutant 3
     as well. It now asserts nothing any mutant changes.
3. After the fix, the canary ran again: 6 of 6 plants with their expected result.

## Controls (the tests shown able to fail)

Each ran in a throwaway worktree (`scripts/nmas-control`) against the final files, the
working tree untouched. Each made its aimed test fail by assertion:

| Control | The test that failed | What it showed |
|---|---|---|
| pytest's `-x` (mutmut's stop at the first failure) | `test_every_test_gets_its_exact_kills_and_only_the_weak_one_is_listed` | the baseline stopped at the failing-unmutated plant, so every test had no verdict |
| only a mutant's first failing test credited | the same | `test_plant_fee_kills_one` was listed as killing none |
| no second process after a collection error | the same | the child plant was listed as killing none |
| the null canary unchecked | `test_a_null_canary_that_is_killed_stops_the_run` | no breakage was reported |
| the mutants' staleness unchecked | `test_a_function_whose_text_moved_since_its_mutants_is_stale` | nothing was stale |
| the estimate without the baseline and the reach check | `test_the_estimate_is_mutants_times_tests_times_seconds_and_runs_nothing` | the seconds came out wrong |

## The narrowed first target, estimated (nothing run)

**The target:** `modules/sdn/detect.py::mark_replies`, `modules/sdn/detect.py::transfer` and
`modules/ai/gateway.py::mask_typed`. These are the weakest functions in C2354's run #69.

**`--estimate` against run #36's map (`--commit e7494edc`) leaves all three out:**
- `mask_typed` and `mark_replies`: their text moved since the map was made;
- `transfer`: not in the map.

So the estimate needs a coverage nightly made after their last change.

**Mutants generated** (by `--generate`, nothing run): `mask_typed` 53, `mark_replies` 137, all
VERDICT.

**The arithmetic, with the staleness set aside:**
- **Covering tests in run #36's map:** `mask_typed` 657, `mark_replies` 60.
- **Test times:** CI's browser-shard JUnit holds 127 and 36 of these tests, at 93.4 s and 9.0 s
  in all.
- **`mark_replies`:** 139 runs x 60 tests = 8,340 test executions. That is about 0.6 h serial
  at the timed tests' mean, about 1.6 h with the untimed ones at 1.31 s each.
- **`mask_typed`:** 55 runs x 657 tests = 36,135 executions. That is about 7.4 h, or 12.1 h on
  the same two bases.
- **With `--jobs 2`:** about half of each.
