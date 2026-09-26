# What the test suite checks

Measured 2026-09-26, at the commit that added this file. Written for a reader
who does not know the project: what the tests protect, how strongly, and what
they cannot reach.

NMAS is a network source-of-truth tool. It holds each device's intended
configuration in git, renders it through templates, shows an operator the exact
commands a change will send, and pushes them only after that operator confirms
the list by hash. Most of what the tests protect is some version of *the tool
never does something nobody approved, and never claims something it did not
establish.*

## Size and organisation

- **3,942 tests in 137 files** (median 19 per file). They come from 3,552 test
  functions, some run with several inputs.
- Organised by **property, not by module.** Most files are named for what must
  stay true: `test_credential_never_changes_on_deploy`,
  `test_reads_write_nothing`, `test_server_reads_nothing_the_form_cannot_send`.
- **Nothing touches a live network, device, or data store.** Every SSH, NETCONF
  and HTTP call is mocked. The store rule is enforced, not assumed: the suite
  runs on a temporary directory, and a run FAILS if the checkout's `data/`
  changes at all (see *The suite had never run clean anywhere*, below).
- CI runs it on every push, on the deployment host's exact package versions
  (`requirements.lock`, generated on the host), in about 4 minutes including
  coverage.

## Where the weight sits

| Area | Tests | Share |
|---|---|---|
| Deploy path: plan, confirm by hash, merge-only push, verify, rollback | 574 | 14.6% |
| Intent and templates: parse, render, round-trip, approval, editing | 552 | 14.0% |
| Credentials: rotation, persistence to boot files, break-glass | 480 | 12.2% |
| Onboarding and retirement | 469 | 11.9% |
| Golden repository and history: commits, restore, remote | 441 | 11.2% |
| Rules about the code and the test harness itself | 353 | 9.0% |
| NetBox safety and provenance | 337 | 8.5% |
| Monitoring and health: drift, freshness, heartbeat, jobs | 325 | 8.2% |
| Identity, gates, secrets, redaction | 309 | 7.8% |
| Settings | 102 | 2.6% |

The single heaviest files are credential rotation (194 tests), deploy safety
(137) and NetBox update provenance (103). Almost a tenth of the suite checks the
code and the harness rather than the product: every script reaches its own
imports, no module computes the data path itself, no removed function is still
called, CI can read no other repository.

## Negative controls: 180 that run every time, ~330 that ran once

This is the number that separates this suite from one that merely runs code. A
test with a control that provably fails when its property is removed is a
different artefact from an assertion that happens to pass. There are two kinds,
and they must never be added together.

- **About 180 built-in controls and floors, in 72 of the 137 files, run on
  every execution.** These are tests that prove the check CAN see the case:
  - "the scan finds the population";
  - "a real tag change is still recorded", beside "an unchanged one is not";
  - "the fallback still uses a real enable secret".

  Counted by name and docstring; 11 of a random 12 were genuine.
- **About 330 mutation controls ran once, at commit time, and are NOT
  re-verified.** Before a commit, the property a test protects was removed from
  the code (a guard deleted, a comparison inverted, a branch forced), and the
  test was shown to FAIL, not crash, then the code was restored. They are
  counted from the numbers stated in 86 commit messages. They are not linked to
  their tests in a machine-readable way, and nothing re-runs them.

**The natural extension is mutation testing** (for example `mutmut`), which
would make the second kind repeatable. It is recorded, not scoped.

Two rules came out of running the controls, both recorded in the project's
rules:
- **A control that fires by CRASHING proves nothing.** A syntax error makes
  every test fail. A valid control fails the tests aimed at its property, with
  no collection errors.
- **A control that PASSES is either a missing test or a broken control.**
  Telling which is the work.

## The kinds of property the tests assert

Classified from test names, so read the shares as approximate:

| Kind | Approx. share | Example |
|---|---|---|
| A refusal happens | 12% | a credential rotation still refuses when the account's form changed |
| A scan has a floor; a count has its denominator | 8% | every mutating route is declared, and the scan must find at least 115 |
| A refusal names its cause and both operands | 7% | a missing lab directory is reported as local, not remote |
| A secret never leaks and is stored safely | 6% | files are created owner-only; masked values never reach a comparison |
| It is recorded or audited | 5% | a golden commit carries its manifest; a terminal open is one audit row |
| Output is exact, or round-trips faithfully | 4% | a device's config re-renders to itself |
| A payload field is drawn on screen | 4% | the shipped JavaScript, executed against the real endpoint's payload |
| Order and sequence | 4% | promotion last; rollback exempt from the dangerous-line gate |
| Idempotent and stable, no churn | 2% | a repeat NetBox sync records nothing |
| Plain behaviour: this input, that output | 49% | |

## What is NOT tested

This is distinct from code that simply did not run. Line coverage is 57%
overall, and the low figures sit mostly in code being cut or rebuilt (the agent
15%, the old configure tab 5%, topology 6%, the collectors 14-21%), while
`modules/nsot`, the core that reaches devices, is at 87.8%. What follows is
untested in code that STAYS.

1. **The boundary with real devices and services.** Every SSH, NETCONF and
   HTTP call is mocked, and coverage shows the consequence:
   - **`pipeline.py` (67%)**, which every deploy runs: its stages that touch a
     device run almost none of their own statements (pre/post snapshot, the
     push, the NetBox query).
   - **`netbox_client.py` (35%)**: the importer's config parsers are 72 of 73
     statements untested, and the sync and removal bodies about 98%. What IS
     heavily tested there is the write chokepoints (the gate, provenance, the
     modification recorder).
   - **`credential_rotation.py` (81%)**: the live read of a device's user line
     is untested.

   The tests prove the PROGRAM is correct (what will be sent, in what order,
   under which refusals). They cannot prove a device ACCEPTS it. **The project
   has a measured count of the difference: 15 defects found by walking the
   onboarding path live that the suite missed** (docs/PHASE2_DHCP.md, section
   10), every one in a seam between two individually tested halves.
2. **The browser.** Render functions run in an embedded JavaScript engine
   against real payloads. Event handling, the order of fetches, and real DOM
   behaviour are covered only by source scans.
3. **The host.** systemd units and timers, file ownership, and the lab-host
   shell scripts (partly: one script's case block runs under bash).
4. **Concurrency beyond settings writes.** Nothing tests two simultaneous
   deploys or restores, drift racing a deploy, or the repository lock across
   processes (it is a lock within one process).
5. **Anything outside a fixture.** Parsers and round-trips are proven on nine
   real captured configs and whatever those contain.

## The suite had never run clean anywhere (found 2026-09-26)

The first run from a pristine checkout gave **5 failures and 19 errors**,
every one passing in the development checkout:
- **Tests wrote into the live `data/` directory.** The guard meant to stop
  that looked only for NEW paths, so directories left behind by earlier runs
  hid it.
- **Four tests had never tested their property.** Their patch missed its
  target, and they passed by reading the developer's own settings file.

Until then "N passed" had partly been a statement about one machine. The fixes:
- one owner of the data path, and a temporary store for every run;
- a run that fails if the real store changes, even by a file created and
  deleted;
- importing the application starts no services;
- CI on a clean runner, with the host's versions.

Two product defects surfaced the same way: a deploy PLAN and an onboarding
PLAN, both reads, were creating directories.

## Running it

```bash
scripts/nmas-test                 # confined: no process the suite starts can reach a network
scripts/nmas-test tests/test_x.py -k name
```

`scripts/nmas-test` runs pytest in a loopback-only network namespace (C46).
The first line says `network: CONFINED`, and the run stops if that is not
measured to hold. Plain `pytest` still works: its header says `NOT CONFINED`,
and the test process itself still refuses any non-loopback connect. The
deployment host cannot make the namespace (AppArmor), so `--offline` there
runs unconfined and says so in its verdict.

## Reproducing these numbers

```bash
python -m pytest --collect-only -q | grep -c '::'                  # tests
python -m pytest --cov=modules --cov=routes --cov=app --cov-report=term
```
The clusters, control counts and property kinds were computed by scripts over
the collected test list, test ASTs and `git log`. The figures above are from
2026-09-26 and will drift.
