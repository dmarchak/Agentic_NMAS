"""The folders under tests/ that hold DATA, never Mercury's own tests (C2633; the operator,
2026-11-06: "fixture job folders are data, not Mercury's tests: their path is declared once and
pytest collection, red-green and the test-weakening check all read that one declaration").

A job's folder holds its own `test_*.py` and `conftest.py`, some failing or asserting nothing
on purpose (the job gate's planted cases), run by Mercury's job runner and, in a copy, by pytest;
they are the job gate's fixtures, not tests of Mercury.

Read by: tests/conftest.py (`collect_ignore`, so pytest never collects them),
scripts/nmas-red-green and scripts/nmas-test-weakening-check (which never select or count a file
in them), and scripts/nmas-fast-checks (which never names one to pytest). The three scripts
PARSE this file at the commit they judge (`ast`, never an import), so they read the same tuple
the commit's own collection reads.

**Each entry must lie under `tests/fixtures/`,** and each script refuses one that does not,
naming it: a folder declared data is one the guards stop looking at, so the declaration cannot
reach Mercury's own tests. A literal tuple of literal strings, each ending in "/", or the
scripts refuse it, naming why.
"""

DATA_FOLDERS = (
    "tests/fixtures/jobs/",
    # The app fixtures: each holds an app's own tests the same way (tests/test_mercury_cli.py,
    # the authoring guide's worked app).
    "tests/fixtures/apps/",
)
