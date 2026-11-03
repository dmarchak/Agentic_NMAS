# Tool (c), static patterns: the repository (2026-11-03)

`scripts/nmas-test-audit-static`, run 2026-11-03 08:15 to 08:16 UTC in CI's interpreter
(3.12.3) on the checkout at `0d55a9aa`, with uncommitted edits by other writers in the tree. It
lists suspects. It classifies none: whether a listed test fulfils its purpose is the independent
reviewer's call. The canary passed first (`canary.md`: 8 of 8 plants flagged, 0 of 5 clean
tests). The full rows are in `raw.tsv`.

**Parsed:** 829 files, 14,928 test functions.

| Pattern | Rows | Tests |
|---|---:|---:|
| tautology | 10 | 10 |
| assertion-free | 51 | 51 |
| mock-of-subject | 2,178 | 1,161 |
| swallowed-exception | 17 | 16 |
| status-only | 146 | 146 |
| any pattern | 2,402 | 1,376 |

## What the rows hold

- **tautology:** all 10 have a call on both sides.
- **assertion-free:** 32 are in `tests/test_board_shots.py`; the other 19 are spread over 12
  files.
- **mock-of-subject:** 117 files. 1,179 rows come from rule A (the file's name) and 999 from
  rule B (imported as the subject). By where the patch is: 324 in the test's own body
  (254 tests), 1,544 in a fixture the test names, 310 in an autouse fixture. All are `setattr`;
  none is `mock.patch`.
- **swallowed-exception:** 12 handlers are only `pass`, `...` or `continue`; 5 catch
  `Exception` and neither re-raise nor assert.

## Limits, as each detector states them

- **tautology:**
  - Asserts are read anywhere in the test, nested functions included.
  - `f() == f()` is listed, and the detail flags the call on both sides (it may be a
    determinism check).
  - unittest's `assertEqual(x, x)` is not read.
- **assertion-free:**
  - Helpers are resolved one level deep: a top-level function in the same file, a `self.` method
    of the test's class or its same-file base, or a name or module attribute imported from
    `tests.`.
  - A helper that only calls another asserting helper is not followed.
  - An unresolved call whose name starts with `assert` counts as asserting.
  - Fixtures, `conftest.py` and helpers reached through an object (a browser driver's
    `wait_for`) are not read.
- **mock-of-subject:**
  - **Rule A:** `modules/<x>.py`, `modules/*/<x>.py`, `routes/<x>.py`, and
    `modules/<a>/<b>.py` for `test_<a>_<b>.py`.
  - **Rule B:** an imported module under `modules/` or `routes/` whose last name is a whole
    `_`-separated part of the file's name.
  - Only a function or class the subject defines at its top level counts. A name it imports (a
    collaborator) or a constant does not.
  - Patches are read in the body and decorators, and one level into named fixtures and the
    file's or class's autouse fixtures.
  - `conftest.py` is not read, and a subject loaded through `importlib` (the scripts) is not
    seen.
- **swallowed-exception:**
  - A broad `contextlib.suppress` is read too.
  - A narrow handler with a real body is not listed.
  - What the test does after the `try` is not read.
- **status-only:**
  - Every `and`-ed part of every assert must compare only a status with constants.
  - An assert's message is not content.
  - A test with any other assertion form is not listed.
