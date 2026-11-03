# Tool (d), dead tests: the repository (2026-11-03)

`scripts/nmas-test-audit-dead`, run 2026-11-03 about 08:16 UTC in CI's interpreter (3.12.3) on
the checkout at `0d55a9aa`, with uncommitted edits by other writers in the tree.
- **The collection:** `nmas-test --collect-only -q -p no:cacheprovider
  --continue-on-collection-errors tests/`, confined.
- **What it lists:** suspects. It classifies none; that is the independent reviewer's.
- **Its canary passed first** (`canary.md`: 9 of 9 plants flagged, 0 of 3 clean tests).
- **The full rows:** `raw.tsv`.

**Totals:**
- **Collected:** 21,154 (pytest's own count line), 14,990 without parametrize ids.
- **Definitions found by `ast`:** 14,934. A further 62 tests were collected with no definition
  in their own file (inherited).
- **Collection errors:** none; every file collected.

| Pattern | Rows | Tests |
|---|---:|---:|
| uncollected | 4 | 4 |
| shadowed | 0 | 0 |
| always-skipped | 0 | 0 |
| always-xfail | 0 | 0 |
| conditionally-skipped (not dead; reported apart) | 511 | 427 |
| conditionally-xfail (not dead; reported apart) | 0 | 0 |

**The 4 uncollected:**
- two `test_*` functions defined inside another test function, in
  `tests/test_alert_band_acknowledge.py`;
- one defined inside a helper, in `tests/test_replace_secret.py`;
- `_Client::test_connection` in `tests/test_installation_settings.py`, a helper class whose
  name does not match `Test*`.

**The conditionally skipped, by form:**
- 280 from a `skipif` mark;
- 142 from a `pytest.skip` under an `if` in the body;
- 81 from a module-level `importorskip`;
- 8 from an `importorskip` in the body.

## Limits, as each detector states them

- **uncollected:**
  - The reasons are tried in this order:
    1. the file's collection error;
    2. a file newer than the collection;
    3. `__test__ = False`;
    4. a class name not matching `Test*`;
    5. a constructor;
    6. defined inside a function;
    7. `del`;
    8. decorated.

    Failing all of those, the reason reads "reason not found by the tool".
  - A deselecting conftest hook shows only as "reason not found".
  - A test inherited from another file is compared under its subclass's id only.
- **shadowed:**
  - Only direct statements of a module or class body are read; the two arms of an `if` are not
    shadowing.
  - The rebinding can be a `def`, a `class`, an assignment or an import.
- **skip and xfail:**
  - Marks are read on the function, its classes, the module's and classes' `pytestmark`, and
    one level through a module-level name assigned a mark.
  - `skipif` or `xfail` with no condition counts as always (pytest's own rule).
  - A skip raised by a fixture or helper is not read: one such parametrize case, in
    `tests/test_lab9_console_scripts.py`, is not listed.
  - No condition is evaluated.
