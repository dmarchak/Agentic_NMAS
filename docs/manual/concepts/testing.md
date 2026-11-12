# Run the tests and their coverage

{{product}}'s tests are in `tests/`, one file per property, and they run with pytest. This page
says how to run them the way the project and its CI do: the suite in its network namespace, the
gate that runs before every commit, and the coverage report that says which code the unit
tests reach. Every command runs from the top of a checkout. The full account of what the suite
checks is `docs/TESTING.md`.

![Running the tests and their coverage. scripts/nmas-test runs pytest in CI's Python inside a network namespace that holds loopback alone, with a temporary data folder, so no test reaches a device, a network or a real store. Each test's tier (unit, spawns or browser) is recorded, and coverage.py records the lines each tier ran. scripts/nmas-coverage report reads both: the functions a unit test reached, module by module, the lines, and the ratchet against the committed baseline, written as HTML and JSON where you name them. The baseline moves only when a person runs nmas-coverage baseline. scripts/nmas-gate runs the suite as CI runs it, then the ratchet, before it commits.](diagrams/testing.svg)

## Before the first run {#setup}

The suite runs in the Python version CI pins (`.github/workflows/ci.yml`, its
`python-version`), with exactly CI's packages. Build that environment once:

```
scripts/nmas-ci-env <a Python of CI's version>
```

It makes a virtual environment at `~/.local/share/nmas-py312` from `requirements.lock` (with
its hashes), `requirements-ci.txt` and `requirements-test.txt`, and refuses an interpreter of
any other version. `scripts/nmas-test` uses it from then on. Where to get CI's exact
interpreter without root is in `docs/TESTING.md`, "CI's interpreter here".

## Run the suite {#suite}

```
scripts/nmas-test                                   # the whole suite
scripts/nmas-test -n 2                              # in two worker processes
scripts/nmas-test tests/test_heal_act.py            # one file
scripts/nmas-test tests/test_heal_act.py -k symptom # the tests in it whose names match
```

Every argument but `--allow-unconfined` goes to pytest. What `scripts/nmas-test` does around
pytest:

- **It confines the run to loopback.** pytest runs inside a network namespace that holds a
  loopback interface and nothing else, as your own user, so no process a test starts can reach
  a device or any other network. The first line says `network: CONFINED`. Where no namespace
  can be made (an ordinary terminal on Ubuntu 24.04 needs a one-time AppArmor profile,
  `docs/TESTING.md`, "From an ordinary terminal"), it refuses, naming why; with
  `--allow-unconfined` it runs anyway and its first line says `NOT CONFINED`.
- **It runs CI's interpreter**: a `PYTHON` you give, else the environment above, else
  `python3` only when it is CI's version; anything else is refused, naming both versions. The
  second line names the interpreter it used.
- **`-n` is lowered to what the memory free now allows** (`scripts/nmas-workers`), and the
  run says so when it lowers it; `-n 0` is one process.
- **One full-suite run at a time.** A run that names no test file is the full suite: it takes
  the full-suite lock the gate takes, or refuses, naming the run that holds it. A run naming
  files takes no lock.
- **It is bounded.** `NMAS_TEST_TIMEOUT` (300 seconds by default) ends the run, naming each
  test that was running and printing its stack. A full run in two workers needs a larger bound:
  set it to about 2.5 times the run's measured time.
- **It writes no bytecode**, so a file a test changed and put back never runs from a stale
  cache.

The suite guards itself as well, inside the namespace: in the test process a connection to
anything but loopback is refused, and every process a test starts is refused the same way. Each run's data folder is a
temporary one, never the checkout's `data/`, and a run that changes the checkout's `data/`
fails. No test needs a credential, and no test touches a live device, network or store.

**Browser tests** drive a real Firefox. In the confined run they need a Firefox that starts
inside the namespace (`docs/TESTING.md`, "The browser tests"). Where none starts, each says so
in its skip reason; the gate refuses a run in which any browser test was skipped.

## What makes a test count {#what-counts}

- **Fixtures are real captures** from devices and services (in `tests/fixtures/`), edited as
  little as the case needs, never typed from memory.
- **Every new check is shown able to fail.** Its property is removed in a throwaway copy of
  the checkout (`scripts/nmas-control`), the aimed tests are seen to fail, and the copy is
  discarded. Many checks also carry a planted case that runs every time: a test that a
  missing step, a dead link or a stray value is found.
- **A failing test reports a real problem.** The code is fixed, or the test's premise is shown
  wrong with evidence and corrected. A test removed, skipped or loosened needs a registered
  reason in the commit (`Test-Weakened:`), and `scripts/nmas-test-weakening-check` holds every
  pushed commit to it.

## The gate, before every commit {#gate}

```
git add <the files of the change>
scripts/nmas-gate --message <message file> --expect "<the message's first words>" --push
```

The gate judges the change exactly as you staged it, and each step can stop everything after
it:

1. **The stage guard** (`scripts/nmas-stage-guard`) refuses a secret or a stray file, and lists
   each new file.
2. **A snapshot** of the staged tree is checked out in a worktree of its own, where every later
   step runs, so your working tree is never locked.
3. **The suite as CI runs it**: CI's interpreter, CI's shards of the files, all at once,
   confined, coverage measured by tier, the workers chosen from the memory free.
4. **The verdict** is read from the run's own output and its exit status: the last line must
   read "N passed", with no failure, no error and no undeclared skip.
5. **The coverage ratchet**, as CI's coverage job runs it (below).
6. **The rest of CI**: the tests that read files owned by root, run outside the namespace, and,
   for a change that is not docs only, the container harness on each Python CI runs.
7. **The message**: its first line must start with what `--expect` says.
8. **The commit**, made in the snapshot; the branch moves only if it still points where the gate
   began, and only when the committed tree is the one tested. With `--push` the gate first
   refuses while CI's newest run on main is red, then pushes the commit and records its verdict
   on the remote.

## Coverage: which code the unit tests reach {#coverage}

**What is counted.** A function is covered when at least one line of its body ran while a
**unit** test ran. That is measured by coverage.py, never guessed from a test naming the
function. A test's tier is what it did, recorded as it runs:

- **unit**: it ran {{product}}'s code in its own process, offline. A test that calls the app
  through Flask's test client is a unit test: no socket, no server;
- **spawns**: it started a Python interpreter or a program of this checkout;
- **browser**: it drove a browser.

The report's headline is the unit tier. A second column counts every offline tier; where the
two differ, those functions are reached only through a child process or a browser. Beside
them stand line coverage (unit tier) and branch coverage (every tier, where the run measured
branches).

**What is in scope** is `tests/coverage_scope.py`: every module under `modules/` is automation,
`routes/` and `app.py` are support (the web layer), and the exceptions (support modules in
`modules/`, such as page models and settings) are listed, each with its reason. A module no rule places fails the tool (`scripts/nmas-coverage scope`).

**Run it.** The whole suite with coverage measured by tier, as CI and the gate measure it,
then the report:

```
py=~/.local/share/nmas-py312/bin/python; d=$(mktemp -d); mkdir "$d/tiers"
NMAS_COVERAGE_TIERS=1 COVERAGE_CORE=sysmon COVERAGE_FILE="$d/.coverage.all" \
  NMAS_TEST_TIERS="$d/tiers" NMAS_TEST_TIMEOUT=5600 \
  scripts/nmas-test -q -p no:cacheprovider -n 2 \
  --cov=modules --cov=routes --cov=app --cov-report=
$py -m coverage combine --keep --data-file="$d/.coverage" "$d"/.coverage.all*
$py scripts/nmas-coverage report --data "$d/.coverage" --tiers "$d/tiers" \
  --html coverage.html --json coverage.json
```

The bound, 5600 seconds, is about 2.5 times one such run's measured time: 2213 seconds in two
workers on a laptop (2026-11-12). The combine step is needed: the report reads the combined
file, not the run's own.

**Where the report lands.** The terminal prints the table: the top line, the modules with no
unit test, then every automation module lowest first (functions covered of total, unit,
every tier, lines, branches). `--html` and `--json` write the same report where you name them;
in the HTML each module opens to its functions. `--only modules/heal/` draws only the modules
under one folder; the ratchet is still judged on the whole report. On every push, CI's
coverage job writes the report to its run's summary and keeps it as the `coverage-report`
artifact.

**The ratchet.** `tests/coverage_baseline.json` holds each automation module's figure. The
ratchet fails when a module's uncovered function count rises, when a function the baseline
names as covered is no longer covered, when a new module has no unit test, or when a new test
asserts nothing (`scripts/nmas-coverage asserts`). There is no absolute threshold. The baseline
moves only when a person runs `scripts/nmas-coverage baseline` on a measurement and commits it.

**Per test, with branches.** Add `--cov-context=test --cov-branch` to the run and the report
names the unit tests that reach each function. It is slower: CI's nightly coverage run
measures this way.
