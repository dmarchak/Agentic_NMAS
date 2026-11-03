# Tool (d), dead tests: the canary (2026-11-03)

`scripts/nmas-test-audit-dead --root <scratchpad>/ta-canary`, CI's interpreter (3.12.3): the
canary has no `scripts/nmas-test`, so its collection is `python -m pytest --collect-only -q -p
no:cacheprovider --continue-on-collection-errors tests/`, run in the canary under its own
`pytest.ini` (the repository's collection patterns). The canary's files are committed in
`docs/test_audit/canary/` as `<name>.txt`; `tests/test_test_audit_tools.py` copies them into a
temporary folder under their real names and runs this same check, with pytest's real
collection, on every run of the suite.

The plants for this tool are in `tests/test_dead_plants.py` and `tests/test_plant_broken.py`.

## Plants

| Plant (test id) | Expected | Result |
|---|---|---|
| `tests/test_dead_plants.py::test_plant_skip_decorator` (`@pytest.mark.skip`) | always-skipped | flagged |
| `tests/test_dead_plants.py::test_plant_skipif_true` (`@pytest.mark.skipif(True, ...)`) | always-skipped | flagged |
| `tests/test_dead_plants.py::test_plant_skip_first_statement` (`pytest.skip()` as the body's first statement) | always-skipped | flagged |
| `tests/test_dead_plants.py::test_plant_xfail_unconditional` (`@pytest.mark.xfail(reason=...)`, no condition) | always-xfail | flagged |
| `tests/test_dead_plants.py::test_plant_shadowed` (defined at line 33 and again at line 56) | shadowed | flagged (the line 33 definition) |
| `tests/test_dead_plants.py::TestPlantHasInit::test_plant_class_with_init` | uncollected (a class with `__init__`) | flagged, reason: the class has `__init__` |
| `tests/test_dead_plants.py::PlantNotATestClass::test_plant_method_outside_a_test_class` | uncollected (a class not matching `Test*`) | flagged, reason: the class name does not match `python_classes` |
| `tests/test_plant_broken.py::test_plant_in_a_file_that_does_not_collect` (its import fails) | uncollected (a file not collected) | flagged, reason: the file did not collect, with pytest's `ModuleNotFoundError` |
| `tests/test_dead_plants.py::test_plant_conditional_skip` (`skipif(sys.platform == ...)`) | conditionally-skipped, reported apart, with its condition | flagged, with `sys.platform == 'planted-no-such-platform'` |

9 plants, 9 flagged, each with its own pattern and no other.

## Clean tests (none may be flagged)

| Clean test | Result |
|---|---|
| `tests/test_dead_plants.py::test_clean_runs` | collected, not flagged |
| `tests/test_dead_plants.py::test_clean_parametrized` (two cases) | collected, not flagged |
| `tests/test_dead_plants.py::TestCleanCollected::test_clean_method` | collected, not flagged |

The plants for tool (c) in `tests/test_widget.py` (13 tests, all collected and none skipped) are
not flagged by this tool either. The canary's collection: 23 tests collected, 1 error (the
broken file); 22 without parametrize ids; 25 definitions found by `ast` (the shadowed name's two,
and the two uncollected methods).

## Runs, and what was fixed

1. **The first canary run:** 9 of 9 plants flagged, no clean test flagged. The broken file's
   reason read only "collection error": pytest's `-q` summary line (`ERROR tests/<file>.py`)
   carries no message. The parser now reads the first `E` line of that file's error section.
2. **The repository's first run:** a `test_*` method of a non-`Test*` helper class with a
   constructor (`tests/test_installation_settings.py::_Client::test_connection`) was given the
   constructor as its reason; the class name not matching `Test*` is now checked first.
3. **The repository's second run:** nine tests of a file another writer created in the checkout
   during the 40 s collection (`tests/test_sdn_watch_propose.py`) were listed as uncollected,
   "no test of this file was collected". The tool now records when the collection began, and a
   file written after it is said to be newer than the collection
   (`test_a_file_written_after_the_collection_began_is_said_to_be_newer`).
4. **Both tools' rows are committed:** a detail quoting a test's source can carry an address
   the test file is excused for (tool (c)'s first `raw.tsv` was refused by
   `tests/test_nothing_personal_is_published.py` for one). Every row now has address literals,
   emails and home paths replaced by `<address>`, `<email>`, `<home>`
   (`test_quoted_source_in_a_row_carries_no_address_or_email`). The fourth run, 08:16 UTC, is
   the one committed.
5. After each fix the canary ran again: 9 of 9 flagged, no clean test flagged.

## Controls (the tests shown able to fail)

In throwaway worktrees (`scripts/nmas-control`), the working tree untouched:
- `shadowed()` returning nothing: `test_dead_lists_every_plant_with_its_pattern_and_no_clean_test`
  failed by assertion, naming `test_plant_shadowed` (shadowed) as missed.
- the newer-file check off: `test_a_file_written_after_the_collection_began_is_said_to_be_newer`
  failed by assertion (the reason read "no test of this file was collected").
- `public()` returning its text unchanged: `test_quoted_source_in_a_row_carries_no_address_or_email`
  failed by assertion for both tools.
