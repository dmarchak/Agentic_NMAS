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
  - **Fail and error both count as red.** A collection error of the whole file is reported
    apart and needs a reason, since it shows nothing about the test.
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
  - **Not guards, so changeable without approval:**
    - `.github/workflows/ci.yml`, whose steps run these checks;
    - `scripts/nmas-test` and `scripts/nmas-control`;
    - the checks' own tests.

    Whether to add them is the operator's call (C2358).

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
    script. No linter runs in CI, so they excuse nothing today. Whether they need a reason is
    the operator's call (C2360).
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

### 6. The register's downgrades, reviewed

- **What:** each week's report lists every A row re-sorted down, or closed in part, with its
  evidence, for the operator's review.
- **How:** `scripts/nmas-register-weekly`, reading the register's history (each row's bucket
  at the week's start and end) and printing each such row and the commit that moved it.
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

- **D1. Red on the parent means fail or error.** A whole-file collection error is reported
  apart.
- **D2. A guard's approval is a quoted trailer** until the operator can sign. The limit is
  said in the item.
- **D3. TESTING.md's per-file table is not a guard;** its rule sections are.
- **D4. The bypass scanner parses where it can and matches text where it cannot,** and says
  which it did for each finding.
- **D5. Item 4 starts with an inventory** and converts by ratchet, never all at once.
- **D6. Each item lands in its own commit,** gated, with its own controls shown able to fail.
