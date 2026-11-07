# Test and process integrity (board TI)

**The operator's direction, 2026-11-03 ~07:4x UTC.** Purpose: every test and check exists to find
real faults, never to produce green. Board TI is this document, drawn under the Phase 7 mode;
its decisions are taken at their recommendations, each a line in docs/STANDING_APPROVAL_LOG.md
("Board TI"). The build follows the order below, each item gated on its own. The independent
audit and fault seeding are done by a reviewer outside the agent's context, arranged by the
operator.

**Why now:**
- **2026-11-03, a dodged guard:** the agent made a scratch script's folder name a parameter,
  built from two pieces, so the config-read hook would not match it (C2345, C2346).
- **The same day, a lost control:** a test's premise was corrected under a new rule (C2313).
  The correction removed the control that proved the ACK check mattered, until the operator
  asked for a replacement.
- **Phase 8's modules have never been mutated:** both committed records hold none of
  `modules/ai/`'s and `modules/sdn/`'s 1,133 functions. The weekly run #68 measured nothing
  (C1651).

## The items, in build order

### 1. Red, then green

- **What:** CI runs each new or changed test function against the commit's parent, with the
  new test file in place and the parent's code. **It must not pass there.** A test that passes
  on the parent is refused, unless the commit marks it
  `Guards-Existing: <test> — <reason>` (a test written to hold behaviour that already works,
  such as a regression net before a refactor).
- **How:**
  - **Which tests:** functions added, or whose body changed, found by parsing the file at both
    commits, never by a diff's text.
  - **The parent:** a throwaway worktree (as scripts/nmas-control makes one).
  - **Red is the test's own body failing** (changed 2026-11-06, C2633; it was "fail and error
    both count as red"). The body ran on the parent and raised: an assertion, or a name the
    parent lacks. A setup or teardown error is not red, since the body never ran.
  - **A collection error of the whole file is reported apart,** since it shows nothing about
    the test. `Red-By-Collection: <file> — <reason>` excuses it only when the error is an
    ImportError or ModuleNotFoundError naming a module the commit adds, checked against the
    commit's added paths. Any other collection error is refused whatever the trailer, naming
    the error, and so is a conftest that does not load.
  - **Data folders are not Mercury's tests** (C2633): tests/data_folders.py declares them once
    (the job gate's fixture jobs, whose own tests fail on purpose). pytest's collection
    (tests/conftest.py), this check, the test-weakening check and scripts/nmas-fast-checks all
    read that declaration. An entry outside `tests/fixtures/` is refused, naming it, so a
    declaration cannot hide Mercury's own tests.
  - **Where:** a CI job over every pushed commit's tests, and the gate's local run before a
    commit.
- **Cost:** each changed test runs twice, a few seconds to a few minutes a push.
- **Prevents:** a test that never failed, so cannot be shown to detect its fault. Today that is
  shown by hand ("every new check is shown able to fail"), and skipped when forgotten.
- **Limit:** a test can be red on the parent for a reason other than the fault (a renamed
  function). The check says the test can fail; whether it fails for the right reason is the
  reviewer's.
- **Built 2026-11-03:** `scripts/nmas-red-green`, in `scripts/hooks/commit-msg` (so the gate's
  commit in its snapshot runs it) and in CI job a over every pushed range. Its tests are
  tests/test_red_green.py.
  - **Its first real runs:** 42643c72 and 99380401 red throughout, on a tool missing from the
    parent (this item's Limit). ec8a7cf8 refused, 9 of 28 passing on the parent (C2356).
- **What it does not see:**
  - a test whose own text is unchanged while a helper, fixture, conftest or class mark it uses
    changed;
  - a test defined under a module-level `if`.
- **A test skipped on the parent for its environment** (no libpq for the records tests on a
  laptop, no browser) is refused as skipped. It errs toward refusing, and it is excused by
  `Guards-Existing` with that reason.

### 2. Protected guards

- **What:** a commit that changes a guard needs the operator's approval trailer,
  `Approved-By: <operator> — <reason>`. The repository is public, so the trailer names the
  role, `operator`, never a person's name. The guards:
  - the hooks, `scripts/hooks/*`;
  - the gate and its parts: `scripts/nmas-gate`, `scripts/nmas-stage-guard`,
    `scripts/nmas-test-weakening-check`, `scripts/nmas-host-step-check`;
  - the ratchets: `tests/ratchet_lists.py`, `tests/coverage_baseline.json`;
  - CLAUDE.md;
  - docs/TESTING.md's rule sections. Its per-file table stays free, being written with every
    test.
  - **The check itself is a guard.**
- **How:** `scripts/nmas-guard-check`, in `hooks/commit-msg` and CI (job a, every pushed commit),
  as the Test-Weakened check is wired.
- **Cost:** one line of the operator's in each such commit. Guards change a few times a week.
- **Prevents:** a guard loosened in the same commit as the work it guards.
- **Limit, said plainly:** the trailer is a claim. The agent can type it, and nothing in git
  proves who wrote it. Until it can be proved, the agent writes `Approved-By` only quoting the
  operator's own words, in the trailer, as 2026-11-03's first use did, and the reviewer can
  check each quote against the conversation (the operator agreed, 2026-11-03).
  **The later fix is a hardware-key signature:** the approval is signed with a key that needs a
  touch to sign, so only the operator, present, can make one. The check then verifies the
  signature, not the words.
- **Built 2026-11-03:** `scripts/nmas-guard-check`, whose one guard list is `GUARDS`. It runs in
  `scripts/hooks/commit-msg` and in CI job a and the docs shard over every pushed range. Its
  tests are tests/test_guard_check.py.
  - **The trailer:** the name must be exactly `operator`, and the reason must quote at least 3
    words. A malformed `Approved-By` is refused in any commit.
  - **docs/TESTING.md:** a changed line is free only as a test file's row inside the
    `| File | Covers |` table, on its own side of the diff.
  - **Its first real runs:** f49c147b, 8d698270 and 3bf87049 change guards with no approval.
    They came before the rule, so history stands.
  - **Added 2026-11-03 (C2358, the operator's decision: "all four; the runners are the
    gates"):**
    - `.github/workflows/ci.yml`, whose steps run these checks;
    - `scripts/nmas-test` and `scripts/nmas-control`;
    - the checks' own tests: tests/test_guard_check.py, test_red_green.py,
      test_test_weakening_check.py, test_bypass_scan.py, test_premise_check.py,
      test_host_step_check.py, test_stage_guard.py and test_nmas_gate.py.

    The Claude Code hooks' tests (tests/test_claude_*_hook.py and the like) are not on the
    list. Those hooks guard the agent's session, not a commit. Adding them is the operator's
    call.

### 3. The bypass scanner, in the gate

- **What:** the lines a commit adds, scanned for each way past a test or a guard. Each kind
  needs a reason line in the commit, `Bypass: <file:line> — <reason>`, and the gate's report
  lists them:
  - an added `skip`, `skipif`, `xfail` or `pytest.skip(`;
  - `pragma: no cover`;
  - `noqa`;
  - a broad `except` in a test;
  - a mock or monkeypatch of the module a test file is named for;
  - a raised timeout, bound or ceiling;
  - a test path or name, or a guarded word, built from pieces to avoid a hook's or check's
    pattern (C2346; the survey's scan, shown to find one).
- **How:** `scripts/nmas-bypass-scan`, parsing the changed files at both commits where it can
  (a skip by decorator or call, a numeric constant raised) and matching the added lines where
  it cannot. Run by the gate and CI.
- **Cost:** a reason line for each. Most commits add none.
- **Prevents:** green bought by switching a check off, unnoticed in a long commit.
- **Built 2026-11-03:** `scripts/nmas-bypass-scan`, in `scripts/hooks/commit-msg` and in CI job
  a and the docs shard. It is a guard itself (item 2's list), and its tests are
  tests/test_bypass_scan.py.
  - **How each kind is found:** by ast or tokenize, and as text only in a file that does not
    parse. Each finding names which (D4).
  - **The guarded words:** read from the config-read hook's own patterns, plus `tests/`.
  - **What the survey found:** over the last 150 commits, 596 noqa, 35 skips, 18 mocks of the
    module under test, 3 raised bounds and 2 broad excepts, and no guarded word built from
    pieces.
  - **The volume:** the noqa are mostly the interpreter adoption's `# noqa: E402` in each new
    script. No linter runs in CI, so they excuse nothing today.
  - **noqa dropped while no linter runs** (C2360, the operator's decision, 2026-11-03): the
    scanner names a noqa only when `NMAS_BYPASS_COUNT_NOQA=1`. That becomes the default once a
    linter runs (C2362).
- **What it does not see:**
  - a skip held in a helper, fixture or conftest that already existed;
  - a mock through a module loaded by path;
  - a bound raised inside a function or as an environment default;
  - a word built from a variable or by `os.path.join`;
  - anything outside Python files.

### 4. Behaviour over presence

- **What:**
  - **UI contract tests press the control and assert its effect**, not that a button is
    drawn. The first case is C2288's Set value…, which drew and did nothing.
  - **The deploy smoke asserts each page's key content** (a heading and the one fact the page
    exists for), not a 200.
- **How:**
  - **The inventory:** every UI test asserting only presence (a control drawn, a status code).
  - **The fix:** each converted to press and assert, the list only shrinking (a ratchet).
  - **The smoke:** its page list gains a per-page content assertion. It moves into the
    repository with C2339.
- **Cost:** about a test an hour to convert. The inventory comes first, to size it.
- **The inventory, built 2026-11-03:**
  - **The tool and the list:** `scripts/nmas-presence-inventory`, and its list
    `tests/presence_only.py`, held by tests/test_presence_only.py as a ratchet that only
    shrinks.
  - **The count:** of 2158 UI tests, 1018 presence only (C2363) and 41 undecided.
  - **The sizing:** about 1000 hours at a test an hour, so the list is triaged before it is
    converted.
  - **A second shape, reported but not held** (`--controls`, C2364, the operator's decision):
    38 tests assert a control is drawn and never request its path. C2288's own test is one: it
    pressed a different control.
  - **The ten to convert first,** all controls drawn and never pressed:
    - the Secret references card's Set value… (C2288's own);
    - the Devices bar's Save;
    - the pending page's verify, bootstrap and abandon;
    - Rotate, Retire, Restore, Revert and Retry, and Persist;
    - Add device's preview.
- **Prevents:** a control that is drawn and does nothing, passing every test (C2288).

### 5. "Premise corrected", measured

- **What:** each premise correction, from now on, names the real behaviour measured that the
  old premise contradicted, with the measurement:
  `Premise-Corrected: <test> — measured: <what was measured, where, the result>`.
  The commit-msg check refuses one without `measured:`.
- **The list for review:** every premise correction and weakened test since Phase 8 began
  (2026-10-25), 80 commits, quoted verbatim:
  ~/Documents/nmas-reports/2026-11-03-premise-corrections.md.
- **Cost:** one line a correction.
- **Prevents:** a test bent to the code under the word "premise", with no evidence that the
  code was right.
- **Built 2026-11-03:** `scripts/nmas-premise-check`, in `scripts/hooks/commit-msg`, in CI job a
  and the docs shard, and on the guard list. Its tests are tests/test_premise_check.py.
  - **The prose rule:** a message whose prose, outside quotes, backticks and trailers, says a
    premise was corrected or wrong needs at least one trailer.
  - **The trailer rule:** each trailer names `measured:` and at least 3 words.
  - **Its first run over the commits since Phase 8 began:** 14 refused, which is history and
    stands.

### 6. The register's downgrades, reviewed

- **What:** each week's report lists every A row re-sorted down, or closed in part, with its
  evidence, for the operator's review.
- **How:** `scripts/nmas-register-weekly`, reading the register's history (each row's bucket
  at the week's start and end) and printing each such row and the commit that moved it.
- **Every re-tag or re-sort near the Phase 8 cap of 60, listed** (the operator, 2026-11-03),
  with its rows, its old and new tags, the counts before and after, and the commit that moved
  it. **The first entry:** 2026-11-03, C2371 to C2378, Lab 10's rows, from "Phase 8: blocks
  0.1.5" (59 of 60 blocking) to "Lab 10: blocks; Phase 8: after" (52), by the operator's
  direction, Lab 10 being ahead of Phase 8 on the roadmap.
- **The week's `Guards-Existing` uses, counted** (the operator, 2026-11-03): each commit's
  trailers of the week, the test each names and its reason. A test excused from red, then green
  is a test the check could not show able to fail; the count shows how often it happens (C2361:
  every new browser test, until red, then green can run one).
- **Cost:** a few minutes of reading a week.
- **Prevents:** a safety finding quietly made smaller.

### 7. Evaluation expectations

- **What:** a recorded case's expectation changed after its first run needs the operator's
  approval (`Approved-By`), as a blind case's does.
- **How:** CI compares each case file under `tests/fixtures/ai_cases/` and
  `tests/fixtures/blind_sets/` with the parent. A case whose `expect` (or key) changed, while
  the case has a recorded run (its id in an evaluation's kept record), needs the trailer.
- **Cost:** one line of the operator's for each changed expectation.
- **Prevents:** a case made to pass by changing what it expects.

## Decisions (each at its recommendation, logged)

- **D1. Red on the parent means the test's own body failed** (the operator, 2026-11-06,
  C2633, replacing "fail or error", which was taken at its recommendation under the Phase 7
  mode on 2026-11-03). In the operator's words: "Change red-green and the test-weakening check
  so that (a) fixture job folders are data, not Mercury's tests: their path is declared once
  and pytest collection, red-green and the test-weakening check all read that one declaration;
  and (b) a collection or setup error on the parent never counts as red: each new test must
  fail on the parent by its own assertion." (b) is read as the body failing, any exception the
  body raises included (the operator's choice, from a survey of 30 commits: about 56 of 155
  reds failed by an assertion and about 98 by a name the parent lacks). A whole-file collection
  error is reported apart. `Red-By-Collection` (in the guard since 8d698270, 2026-11-03) is
  narrowed, in the operator's words: "the guard accepts it for a test file only when that
  file's collection error on the parent is an ImportError/ModuleNotFoundError naming a module
  this commit ADDS (checked against the commit's own added paths); any other collection error
  on the parent (a fixture, a conftest, a syntax error elsewhere) is refused, naming the error."
- **D2. A guard's approval is a quoted trailer** until the operator can sign. The limit is
  said in the item. **The quote is an approval given for that specific change, never one
  borrowed from a related decision** (the operator, 2026-11-06, after 2179843c quoted r5's
  approval of the mutation engine for two additions to tests/ratchet_lists.py; the operator
  then approved those two in their own words: "The two ratchet additions in 2179843c (the
  mutant ceiling as a floor; the gate's allowed dunders shrink-only): approved, in my words,
  now."). Where no such words exist, the change waits and the operator is asked. Cost: one
  question per guard change the operator has not named. Prevents: a guard loosened, or a
  ratchet moved, under an approval given for something else.
- **D3. TESTING.md's per-file table is not a guard;** its rule sections are.
- **D4. The bypass scanner parses where it can and matches text where it cannot,** and says
  which it did for each finding.
- **D5. Item 4 starts with an inventory** and converts by ratchet, never all at once.
- **D6. Each item lands in its own commit,** gated, with its own controls shown able to fail.
