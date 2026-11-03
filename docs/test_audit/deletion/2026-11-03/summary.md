# Tool (a), the deletion test: the repository (2026-11-03)

**The run:** `scripts/nmas-test-audit-deletion --reach <run #36's coverage-drilldown> --commit
e7494edc`, in CI's interpreter (3.12.3), `--jobs 2`, 2026-11-03 10:03:20 to 12:18:20 UTC, in six
shards of 2,000. Its root was a detached worktree of `ec8a7cf8` (HEAD at the time), so no other
writer's edit reached the run.

**What it lists:** suspects, the tests that still pass with every product function the map says
they run stubbed. It classifies none: that is the independent reviewer's.

**Its canary passed first** (`canary.md`): 9 of 9 plants with their expected result.

**The full rows:** `raw.tsv`.

## The map

- **The artifact:** the coverage nightly's `coverage-drilldown` of run #36, made at `e7494edc`
  (2026-11-02), read by `scripts/nmas_mutation.py`'s `load_reach`.
- **What it holds:** 20,879 tests and 6,799 functions in `modules/`, `routes/` and `app.py`.
- **Its age:** 20 commits older than the run's root.

## The scope run, and what was left out

- **The operator's named modules:**
  - deploy: `modules/nsot/deploy.py`, `modules/pipeline.py`, `modules/deploy_job.py`;
  - credentials and secrets: `modules/credentials.py`, `modules/secrets_store.py`,
    `modules/nsot/credential_rotation.py`, `modules/redact.py`;
  - drift and Needs attention: `modules/drift_check.py`, `modules/attention.py`;
  - Phase 8: `modules/ai/`, `modules/sdn/`.
- **The harness, left out:** `modules/redact.py::guard_new_handlers` and
  `modules/redact.py::install_log_redaction` are reached by every one of the map's 20,879 tests.
  - **Why every test reaches them:** the closure `guard_new_handlers` installs on
    `logging.Logger.addHandler` runs each time pytest's logging plugin adds its handler for a
    test.
  - **What counting them would do:** put every test in scope. They were not stubbed and put no
    test in scope.
  - **Measured** on six tests with them stubbed too (`--stub-harness`): two tests whose only
    mapped functions are these two passed. So a test that reaches no product code of its own
    would otherwise be listed.
- **In scope: 11,493 tests,** those the map says reach a function in a named module, the harness
  aside. Every one was taken, and every function each reaches was stubbed, in scope or not.
- **Left out:** the other 9,386 tests in the map, which reach no named module's function.

## The two stubs

1. `raise NotImplementedError("deletion audit")`, the body replaced (the brief's stub).
2. If the test did not pass under that, `return None`, the body deleted.

A test passing under either is listed, and its row names which. Under the raising stub alone a
test that calls the function and asserts nothing fails by construction (the call raises), so that
stub on its own lists only tests that catch it. `--stubs raise` runs the first stub alone.

## The measured time and the projection

- **The first shard, 200 tests** (the first 200 of the sha256 order, 09:54:48 to 09:58:09 UTC):
  - 111 ran, 88 were stale and 1 not collected;
  - 170 s of wall at `--jobs 2`: 1.53 s per test run, 0.85 s per test taken.
- **The projection:** 11,293 more tests at 0.85 s each, about 9,600 s (2.7 hours). That was
  under the 3 hours set, so the rest ran.
- **The whole run:** 8,100 s of wall (2.25 hours) for 11,493 tests.
  - 6,195 ran, each under both stubs: 12,390 pytest runs, 15,068 s of runs, 2.43 s a test.
  - 1.31 s of wall per test run.

## Counts

| Result | Tests |
|---|---:|
| still passes (listed) | 325 |
| fails | 5,870 |
| stale (not run) | 5,247 |
| not collected | 51 |
| skipped | 0 |
| no outcome | 0 |
| timed out | 0 |
| not stubbable | 0 |
| **in scope** | **11,493** |

- **The 325 listed, by the stub they passed under:** all 325 under `return None`, none under the
  raising stub. All 325 are unit tier.
- **By the number of functions stubbed:** 137 one, 128 two to five, 45 six to twenty, 15 more
  (at most 53).
- **By test file, the largest:**
  - `tests/test_redact_ios_shapes.py` 175;
  - `tests/test_deploy_safety.py` 15;
  - `tests/test_ai_intent_screen.py` 12;
  - `tests/test_ai_nl_logs.py` 10, `tests/test_update_available.py` 10;
  - `tests/test_adopt_account.py` 8;
  - `tests/test_ai_presses.py`, `tests/test_pipeline.py` and `tests/test_vios_configless_patch.py`
    7 each;
  - `tests/test_credential_rotation.py` 6;
  - 40 other files, 1 to 4 each.
- **By the named module reached** (a test counts under each):

  | Module | Tests |
  |---|---:|
  | `modules/redact.py` | 229 |
  | `modules/credentials.py` | 39 |
  | `modules/nsot/deploy.py` | 31 |
  | `modules/secrets_store.py` | 28 |
  | `modules/pipeline.py` | 15 |
  | `modules/ai/intent_names.py` | 13 |
  | `modules/nsot/credential_rotation.py` | 11 |
  | `modules/attention.py` | 11 |
  | `modules/ai/nl_query.py` | 10 |
  | `modules/ai/presses.py` | 7 |
  | `modules/ai/anthropic_adapter.py` | 7 |
  | `modules/ai/who.py` | 4 |
  | `modules/ai/explain.py` | 3 |
  | `modules/ai/cases.py` | 2 |

  One each: `modules/ai/injection.py`, `modules/ai/intent_words.py`, `modules/drift_check.py`,
  `modules/sdn/closed_loop.py`, `modules/sdn/drivers/base.py`, `modules/sdn/flow_intent.py`,
  `modules/sdn/drivers/ryu.py`.
- **The 5,870 that fail, by how they failed:**

  | Phase | Under the raising stub | Under the deleted body |
  |---|---:|---:|
  | failed in the test's call | 3,435 | 4,297 |
  | errored in setup (a fixture reached a stubbed function) | 1,585 | 1,095 |
  | errored with no phase named (the test's file did not collect) | 850 | 478 |

  The stub's message was in the output of all but 2 (two tests in
  `tests/test_authorised_lines.py`, which failed with it absent).
- **Stale, 5,247:** each reaches at least one of the 71 functions whose text moved since
  `e7494edc`, or that is no longer defined (the 11 functions of the deleted
  `routes/bulk_intent_v2.py`, and `modules/manual_diagrams.py::bulk_intent`). They are named in
  `raw.tsv`'s `#` lines. All 225 in-scope browser-tier tests are among them.
- **Not collected, 51:**
  - 44 the copy's collection does not list, 40 of them parametrized cases whose ids have changed
    since;
  - 7 whose file is gone (`tests/test_bulk_intent_v2.py`).
- **The copy itself:** the first 200 were run again with `--baseline`, each test unstubbed in
  the copy first. 0 of 111 failed unstubbed, and the stubbed results matched the first shard's
  (6 still pass, 105 fail).

## Limits

- **In-process reach only.** The map holds what a test's own process ran (per-test contexts).
  - A function reached only in a child the test starts (the spawns tier) is not in the map and
    is not stubbed by name.
  - The stubs are written to the copy's files, so a child does run the stubs of the functions
    the map does name.
  - Of the in-scope tests, 36 are spawns-tier and 225 browser-tier, and none of either was
    listed: 11 spawns-tier failed and 25 were stale; all 225 browser-tier were stale.
- **Every phase counts.** A function a fixture runs is in the test's set, so a test can fail in
  setup without its own body needing the function. `fails` is not a verdict that the test checks
  the code.
- **The phase-less errors.** The run predates the tool naming the collection phase.
  - One of the 850 was rerun by hand and was a collection error: the test module calls a stubbed
    function at its import
    (`tests/test_adjacency_log.py::TestTheReader::test_up_lines_and_unmanaged_devices_make_no_entry`).
  - The rest are not each confirmed. The tool now says `in collection`.
- **The two stubs.** The deleted body (`return None`) passes a test that asserts nothing about
  the result, and also one whose expected value is None or falsy. Which applies to a listed test
  is the reviewer's reading.
- **Stale tests were not run:** 46% of the scope. A map made at the root's commit (the next
  coverage nightly) would let them run.
- **The harness exclusion is by a property** (reached by every test in the map). A function
  reached by nearly every test, by the suite's fixtures rather than any test's subject, is
  stubbed, and can fail tests that never meant to test it.
- **The copy has no git history.** A test reading the checkout's history (`git log`, `git show`)
  fails in the copy unstubbed too, so it would be `fails`, never listed. The baseline sample
  found none such among 111, and the full run made no baseline.
- **Stubbing:**
  - A generator so stubbed raises (or gives None) when called, not on its first item.
  - A function defined twice in one module is not stubbable (none in this run).
  - Methods are stubbed by qualname; nested functions go with their enclosing function.
- **Unconfined.** Each test ran as `python -m pytest <id>` in the copy, outside
  `scripts/nmas-test`'s loopback namespace. The suite's in-process network guard still held.
- **The committed `raw.tsv`'s format** is the tool's final one, applied to the run's rows after
  it, with no result or outcome changed:
  - every column through the same masking as tools (c) and (d): an address literal, an email or
    a home path is replaced. 343 test ids are so masked (a parametrized case carrying an
    address);
  - a row that is not listed gives its functions as counts;
  - a stale row names its moved functions, with their reasons in the `#` lines.
