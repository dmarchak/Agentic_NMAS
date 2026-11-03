# Tool (c), static patterns: the canary (2026-11-03)

`scripts/nmas-test-audit-static --root <scratchpad>/ta-canary`, CI's interpreter (3.12.3). The
canary's files are committed in `docs/test_audit/canary/`, each stored as `<name>.txt` so pytest
never collects them; `tests/test_test_audit_tools.py` copies them into a temporary folder under
their real names and runs this same check on every run of the suite.

The canary is a root of its own: `pytest.ini` with the repository's collection patterns, a
`modules/widget.py` (the module under test: it defines `helper`, `compute` and `wait`, and
imports `time`), an asserting helper `tests/helpers_plant.py`, and three test files. The plants
for this tool are in `tests/test_widget.py`, named for `modules/widget.py`.

## Plants

| Plant (test id) | Expected | Result |
|---|---|---|
| `tests/test_widget.py::test_plant_tautology_same_sides` (`assert x == x`) | tautology | flagged |
| `tests/test_widget.py::test_plant_tautology_constant` (`assert True`) | tautology | flagged |
| `tests/test_widget.py::test_plant_assertion_free` (calls `compute(2)`, asserts nothing) | assertion-free | flagged |
| `tests/test_widget.py::test_plant_mock_of_subject_object` (`monkeypatch.setattr(widget, "helper", ...)`) | mock-of-subject | flagged |
| `tests/test_widget.py::test_plant_mock_of_subject_string` (`mock.patch("modules.widget.helper")`) | mock-of-subject | flagged |
| `tests/test_widget.py::test_plant_swallowed_exception` (`except Exception: pass`) | swallowed-exception | flagged |
| `tests/test_widget.py::test_plant_status_only_code` (`assert r.status_code == 200`) | status-only | flagged |
| `tests/test_widget.py::test_plant_status_only_ok` (`assert body["ok"]`) | status-only | flagged |

8 plants, 8 flagged, each with its own pattern and no other.

## Clean tests (none may be flagged)

| Clean test | What it holds that the rules must not take for a pattern | Result |
|---|---|---|
| `tests/test_widget.py::test_clean_compute_value` | one assert on a value | not flagged |
| `tests/test_widget.py::test_clean_patches_a_collaborator` | patches `widget.time`, a name the subject imports, not one it defines | not flagged |
| `tests/test_widget.py::test_clean_uses_an_asserting_helper` | no assert of its own; calls `check_positive`, imported from `tests.helpers_plant`, whose body asserts | not flagged |
| `tests/test_widget.py::test_clean_narrow_handler_and_a_client_patch` | `except KeyError:` with a real body, and an HTTP client's `.patch("modules.widget.helper")` (not mock's) | not flagged |
| `tests/test_widget.py::TestCleanClass::test_clean_raises_and_reads_content` | `pytest.raises`, and a status asserted together with content | not flagged |

The tool's planted files for tool (d) (`tests/test_dead_plants.py`, `tests/test_plant_broken.py`)
are parsed too, and nothing in them is flagged by this tool. Test functions parsed: 25.

## Runs, and what was fixed

1. **Before the first run**, while the tool was written: a test's name was read as any
   `test` prefix; it now follows `pytest.ini` (`test_*`, `Test*`). A truthy-literal check had an
   operator-precedence slip; it is now `bool(value)`.
2. **The first canary run:** 8 of 8 plants flagged, no clean test flagged.
3. **After the repository's run:** the tautology detail's wording only, and a fifth clean test
   (`test_clean_narrow_handler_and_a_client_patch`) added to hold two rules the repository's
   run relies on (a `.patch` on an object that is not mock's is not a mock; a narrow handler
   with a body is not swallowed). The canary run again: 8 of 8 flagged, no clean test flagged.
4. **The first `raw.tsv` was refused by `tests/test_nothing_personal_is_published.py`:** a
   status-only detail quoted a test's address literal, which the test file is excused for and
   the output is not. Every row now has address literals, emails and home paths replaced by
   `<address>`, `<email>`, `<home>` (`test_quoted_source_in_a_row_carries_no_address_or_email`).
   The run at 08:15 UTC is the one committed; the canary again 8 of 8, no clean test flagged.

## Controls (the canary's test shown able to fail)

Each in a throwaway worktree (`scripts/nmas-control`), the working tree untouched:
- `tautologies()` returning nothing: `test_static_lists_every_plant_with_its_pattern_and_no_clean_test`
  failed by assertion, naming the two tautology plants as missed.
- `is_status()` answering yes for every expression: the same test failed by assertion, naming 19
  unexpected status-only rows, the clean tests among them.
- `public()` returning its text unchanged: `test_quoted_source_in_a_row_carries_no_address_or_email`
  failed by assertion.
