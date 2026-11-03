# Tool (a), the deletion test: the canary (2026-11-03)

`scripts/nmas-test-audit-deletion --root <canary> --reach <canary>/reach --then
<canary>/reach/then --scope canarypkg/calc.py`, CI's interpreter (3.12.3), `--jobs 2`. The
canary is a package of its own, not the repository's tests: `canarypkg/calc.py` (the functions),
`tests/test_calc.py` and `tests/test_plant_import_time.py` (the plants), `tests/conftest.py`
(an autouse fixture every test runs),
its own `pytest.ini`, and a reach map in the coverage nightly's JSON shape
(`reach/coverage.json`) with the sources as that map measured them (`reach/then/`). Its files
are committed in `docs/test_audit/canary/deletion/` as `<name>.txt`;
`tests/test_test_audit_deletion.py` copies them into a temporary folder under their real names,
gives that folder an index (`tests.source_index.track_all`), and runs this same check on every
run of the suite.

## Plants

| Plant (test id) | Expected | Result |
|---|---|---|
| `tests/test_calc.py::test_plant_double_value_fails_when_stubbed` (asserts `double`'s result) | fails, not listed | fails (raise: failed in call, the stub's `NotImplementedError` reached; none: failed in call) |
| `tests/test_calc.py::TestPlantCounter::test_plant_bump_value_fails_when_stubbed` (asserts a method's result; stubbed by its qualname `Counter.bump`) | fails, not listed | fails (both stubs) |
| `tests/test_calc.py::test_plant_double_asserts_nothing_still_passes` (calls `double`, then `assert True`) | still passes, listed | still passes (raise: failed in call; none: passed) |
| `tests/test_calc.py::test_plant_double_caught_broadly_still_passes` (`try: double(2) except Exception: pass`) | still passes, listed | still passes (raise: passed) |
| `tests/test_plant_import_time.py::test_plant_fails_in_collection_when_stubbed` (its module calls `double` at import) | fails, not listed | fails (raise: error in collection; none: failed in call) |
| `tests/test_calc.py::test_plant_label_value_is_stale` (reaches `label`, whose text in `reach/then/` differs) | stale, not run | stale (`moved since the map: canarypkg/calc.py::label`; the `#` lines: `its text moved (cb52e8ce897a in the map, d0fc7b3861b2 now)`) |
| `tests/test_calc.py::test_plant_pick_is_not_stubbable` (reaches `pick`, defined in both arms of an `if`) | not stubbable, not run | not stubbable (`defined 2 times in the module`) |
| `tests/test_calc.py::test_plant_removed_since_the_map` (in the map, not in the file) | not collected | not collected (`the copy's collection does not list it`) |
| `tests/test_plant_file_removed.py::test_plant_in_a_file_removed_since_the_map` (in the map, its file gone) | not collected | not collected (`its file is not in the copy`) |

9 plants, 9 with their expected result and no other.

**The harness.** `canarypkg/calc.py::harness`, which the canary's conftest runs for every test
and which the map therefore gives to every test, is named in the output and not stubbed. With
`--stub-harness` (stubbing it too), all five tests that run fail: four in setup, at the
conftest's call, and the import-time plant in collection
(`test_stubbing_the_harness_fails_every_test_that_runs`).

## Runs, and what was fixed

1. **The first canary run, the raising stub only:** three of the four tests that ran were
   recorded as `fails` with pytest's exit 4 and no test outcome. The two jobs shared one
   cache of the modules' original text, filled on first use from the first job's copy, so a
   job could take a text that copy held stubbed for the original (the cause found by reading
   the code; the exit 4 itself was not traced further). The originals are now all read before
   any job starts, and exit 4 has not recurred in the canary's runs since. A run with no test
   outcome is now `no outcome`, never `fails`.
2. **The assertion-free plant failed under the raising stub, every run:** a test that calls the
   function directly receives the `NotImplementedError` and fails, whatever it asserts. A raising
   stub on its own can never list such a test. A second stub, the body deleted (`return None`),
   now runs when the first does not pass; under it the plant passes and is listed, and the test
   asserting the result still fails. `test_the_raising_stub_alone_fails_the_test_that_asserts_nothing`
   pins the reason.
3. **Every counted function of all 373 modules in run #36's map, stubbed at once with each
   stub (a check outside the canary):** 8 of 746 stubbed modules did not compile, in
   `modules/csp.py`, `modules/invalidation.py`, `routes/list_param.py` and
   `routes/page_network.py`: a body whose first statement is a decorated function was cut at its
   `def` line, leaving its `@` lines. The cut now starts at the first decorator, and a stubbed
   module must also hold exactly one more stub body per function chosen, or the test is not
   stubbable. After the fix: 746 of 746 compile and hold their stubs.
4. **The repository's first full shard:** a test file the map names was deleted since
   (`tests/test_bulk_intent_v2.py`), and pytest given a path it cannot find collects nothing at
   all, so all 2,000 tests of the shard were `not collected`. Only files the copy holds are now
   collected, a test whose file is gone says so, and a collection whose output names a missing
   path is refused (exit 1). Plant 8 was added for it.
5. **The repository's whole run:** 850 failures under the raising stub (and 478 under the
   other) were errors with no phase named. One, rerun by hand
   (`tests/test_adjacency_log.py::TestTheReader::test_up_lines_and_unmanaged_devices_make_no_entry`),
   was `ERROR collecting tests/test_adjacency_log.py - NotImplementedError: deletion audit`:
   the test's own module calls a stubbed function at its import. The tool now names that phase
   (`in collection`), and the import-time plant was added for it. The committed `raw.tsv` is
   that run's, made before this fix: its phase-less errors are not each confirmed as
   collection errors (summary.md, the limits).
6. After each fix the canary ran again: 9 of 9 plants with their expected result.

## Controls (the tests shown able to fail)

In throwaway worktrees (`scripts/nmas-control`), the working tree untouched, the canary's
untracked files added to `tracked()`'s listing by a shim plugin outside the repository (they
are in no index until the gate stages them), each against the final files:
- `stale_functions` returning nothing: `test_every_plant_gets_its_own_result_and_the_harness_is_named`
  failed by assertion (the stale plant ran and was `fails`), and
  `test_stubbing_the_harness_fails_every_test_that_runs` failed by assertion (6 tests ran, not 5).
- the decorator fix undone (the cut at the statement's own line):
  `test_the_stub_keeps_signature_decorators_and_docstring` failed by assertion
  (`Holder.cached`: the stubbed module does not compile, invalid syntax).
- the collection phase not named: both canary tests failed by assertion (`'raise: error (1
  error) in collection' in "raise: error (1 error), ..."`).
- the second stub removed (`STUBS` holding `raise` only):
  `test_every_plant_gets_its_own_result_and_the_harness_is_named` failed by assertion (the
  assertion-free plant `fails`), and `test_the_stub_keeps_signature_decorators_and_docstring`
  failed (`STUBS["none"]` missing).
