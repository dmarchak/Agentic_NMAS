# The combined suspects list (2026-11-03)

`scripts/nmas-test-audit-suspects`, 2026-11-03 ~13:0x UTC, merging the tools' committed outputs
of 2026-11-03.
- **What it is:** every test any tool flagged, and which tools.
- **What it is not:** a classification. Whether a listed test fails its purpose is the
  independent reviewer's.
- **The rows:** `suspects.tsv`, one row per test, the most-flagged first.

**Out of 21,154 tests collected** (tool (d)'s count), **1,730 are listed**: 1,715 by one tool,
15 by two or more.

| Source | Tests listed | What counts |
|---|---:|---|
| (c) static patterns | 1,376 | every row: tautology, assertion-free, mock-of-subject, swallowed exception, status-only |
| (d) dead tests | 4 | uncollected, shadowed, always skipped, always xfail (a conditional skip is not dead, and is left out) |
| (a) deletion | 325 | "still passes" with its covered functions stubbed (stale and not-collected rows are left out) |
| named by the operator | 40 | C2313's 40 tests coupled to the Lab 8 walk flood's recorded label, from ec8a7cf8's `Test-Weakened:` trailers whose reason reads A or B |

**Not in this list:**
- **(e) fakes** lists fakes, not tests: its 111 fakes and 198 differing fields are their own
  table (`docs/test_audit/fakes/2026-11-03/`).
- **(b), mutation with per-test kills,** is not built yet. Its first real run's score is
  C2354.
- **(a)'s 5,247 stale tests** were not run, so they could not be listed.

**Each source's limits** are in its own `summary.md`, beside its raw output.
