# Local CI: the repository's own workflows, run on the host under act (workstream 0)

**RESUMED** (the operator, 2026-11-03 ~20:2x UTC: in the first agent slot that frees, with no
third agent). It had been paused at ~20:0x the same day. **GitHub CI stays the deploy gate
until the operator's host step is in and the first measured run (section 12) has read back.**
Until the store exists on the host, `nmas-deploy` and the updater say nothing of a local
runner and use GitHub's verdict alone (tested).

**Where it stands (2026-11-03, 23:42 UTC):**
- **Built and tested in the repository:**
  - the act wrapper `scripts/nmas-local-ci`, now carrying the operator's five answers below;
  - the job image, `deploy/local-ci/runner.Dockerfile`;
  - the unit templates;
  - the deploy gate's two-runner rule, with `--override-ci-red`;
  - the ci-agreement reader and its Needs attention rows;
  - the Update page naming the runner;
  - the guard-list entries;
  - the three workflows' AppArmor sysctl step, skipped under act saying why (section 1).
- **Measured on the laptop with act 0.2.89** (section 10): act's real log format, now the
  tests' fixture; the seccomp profile, in a container; the job image, built and run; a
  two-job workflow in act's container mode with the runner's own flags.
- **Not done:**
  - act has never run on the host, and ci.yml has never run whole under act (section 12);
  - the scheduled jobs' cutover waits on a week of parallel runs (section 5);
  - the CPU and memory limits wait on the first measured run (answer 4).

**Since the host's first run (the operator's rulings, 2026-11-04):**
- **Only a test step's failure is red (C2503).** A failure in a setup step is "no verdict,
  run again": the record's state is `error`, naming the job and the step (section 2).
- **Push-triggered CI only (C2504).** The runner runs ci.yml for main's new tip and nothing
  else; the scheduled workflows stay on GitHub's schedule (section 5).
- **Capped by systemd.** The runner and every job container share one slice,
  `nmas-local-ci.slice`, whose caps bound them together (sections 9 and 11).
- **The job image holds PostgreSQL 18's libraries** (C2503's dpkg failure, section 9).
  Python 3.12.3 in its tool cache (C2503's setup-python failure) is built and measured, and
  waits on the operator's licence decision (section 9).

## The operator's five answers (2026-11-03), and how each is carried

| # | The answer | Where it is carried |
|---|---|---|
| 1 | **Confinement in act's containers: a seccomp profile, with least privilege.** | `nmas-local-ci seccomp-profile` derives the jobs' profile from Docker's own default, plus ONE rule: `unshare` may make a user namespace, a network namespace or both (the suite's `unshare -rn`), and no other namespace, without CAP_SYS_ADMIN. clone and clone3 keep the default's rules. act passes it as `--container-options "--security-opt seccomp=<profile>"`; never `--privileged`, no capability added. The self-test refuses a profile not root's, one allowing by default, or one allowing a namespace or mount syscall with no condition. Beyond the answer, by the same principle: the jobs are on Docker's bridge, never act's default `--network host`, and act's artifact and cache servers bind to the bridge's gateway, not act's default of the host's LAN address. |
| 2 | **The runner image: the derived image with Firefox and geckodriver (MPL).** | `deploy/local-ci/runner.Dockerfile` (section 9, "The runner image"); the deep self-test starts both in the image with no network; a browser test skipped for any of tests/browser.py's three reasons is a step not run, never a pass. |
| 3 | **pip and setup-python: online for now.** | The jobs reach the internet through Docker's bridge, as on GitHub. Every record says `"network": "online"`. Offline is later (section 9). |
| 4 | **CPU and memory limits: after the first measured run.** | Set 2026-11-04 from that run, on a systemd slice rather than per container: `deploy/systemd/nmas-local-ci.slice` (CPUQuota=200%, MemoryHigh=5632M, MemoryMax=6G, CPUWeight and IOWeight 20). The service runs in it (`Slice=`) and every job container is put in it (`--cgroup-parent=nmas-local-ci.slice`), so its caps bound all of CI together. Every record's `limits` names the slice, and the self-test refuses a run when the slice lacks its caps. |
| 5 | **The CI override: terminal only, with no in-app button.** | `nmas-deploy --override-ci-red "<reason of at least 3 words>"` is its one door. The updater calls the gate with no override, and nothing the app serves names it (both tested). |

**The licence rule, clarified** (the operator, 2026-11-03): the copyleft clause covers only what
is shipped with Mercury or its release. OS packages and development-only tools that are never
shipped are approved whatever their licence, and each is recorded in
`docs/THIRD_PARTY_DEV_TOOLS.md`, its licence read from its own release or package metadata
(read 2026-11-03 for act, the runner image's build files, Firefox, geckodriver, Docker's seccomp
profile, Docker Engine and python3-yaml).

**The operator's direction, 2026-11-03** (verbatim where quoted):
1. "A local CI runner equivalent to ci.yml ... writing a recorded verdict per sha ... Runs on
   the NMAS host as a root-owned service you can't modify (its install is my host step); its
   script and unit are protected guards. The scheduled jobs (coverage nightly, mutation weekly)
   move to it."
2. "The safe-deploy script and the in-app updater accept a green verdict from either the local
   runner or GitHub, and say which."
3. "GitHub CI keeps running on every push, but deploys don't wait for it."
4. "Deploy in batches (a few times a day) unless a fix is urgent."
5. Redirected the same day: "Local CI: don't replicate ci.yml in a separate script (two
   definitions drift). Use act (nektos/act) to run ci.yml itself in Docker, wrapped by the
   root-owned service ... Where a step can't run under act, the verdict names it as not run.
   Never a silent skip, never a pass. Cache the images so it runs offline; say how large they
   are. Not Jenkins (a heavy second definition)."
6. On disagreement: "keep refuse, scoped. Refuse only when a GitHub red is known at deploy
   time; never wait for a missing GitHub verdict. A GitHub red that arrives after a deploy
   raises a Needs attention row naming the step, with a rollback recommendation. A red may be
   rerun once: a green rerun clears it. My override, with a reason, is recorded on the deploy."

**What is measured, and what is still recalled.** Every claim below about act's own behaviour
is marked **(measured)** with where, or **(recalled)** when it still comes from act's
documentation as remembered. Section 12 settles the rest on the host.

## 1. The compatibility survey: ci.yml, coverage-nightly.yml and mutation-nightly.yml under act

The population is every job and step of the three workflow files at main ad202730 (rechecked
2026-11-03: since e93fe977, the survey's first base, one step was added, the premise check, a
range check that runs as the others do). The table groups steps that share one answer; a
"cannot run" is named, with why.

Columns: **As is**, a step runs under act unchanged; **Flag**, it runs with an act flag or an
event file the wrapper passes; **Cannot**, it cannot run under act as written.

| Item (where) | Verdict | Why, and what settles it |
|---|---|---|
| `on: push`, `github.event.before`, `github.sha` (every range check, `scope`) | Flag | The wrapper writes the push event (`-e event.json`: `before`, `after`, `ref`, `repository`). act takes `github.sha` from the checkout's HEAD **(recalled)**, and the checkout is detached at the sha. Settled by the first range check's log line naming its range (section 12). |
| `on: schedule` (the two nightlies) | Not run here (C2504) | The runner runs push-triggered CI only; the scheduled workflows stay on GitHub's schedule, and the runner never reads a `schedule:` trigger (section 5). |
| `concurrency:` (all three) | As is (ignored) | act does not implement concurrency groups **(recalled)**. The wrapper runs one workflow at a time (a lock), so nothing overlaps. |
| `permissions:`, GITHUB_TOKEN | As is | ci.yml and coverage-nightly use no token (checkout with `persist-credentials: false`; the drill-down step asks the PUBLIC API with no token). The wrapper passes no secret, so act's `GITHUB_TOKEN` is empty. **mutation-nightly's "Download it" passes `github.token`**: see its row. |
| Secrets | As is | None of the three workflows reads a secret. |
| Service containers (`services:`, `container:`) | As is (none) | None of the three declares one (searched for both keys, 2026-11-03). The records tests' PostgreSQL is started by the suite itself (tests/pg_instance.py). |
| `runs-on: ubuntu-24.04` | Flag | `-P ubuntu-24.04=sha256:<the job image's ID>`, built on the host (section 11), with `--pull=false`. act still pulls an image that is absent even then **(measured, probe 3)**, so the per-run self-test refuses to start when it is absent. |
| `actions/checkout@v4` (every job) | Flag | When the workflow's own repository is checked out, act copies the local folder into the container instead of fetching **(recalled)**. So the wrapper's fresh, self-contained clone at the exact sha is what every job sees. `fetch-depth: 0` is moot: the clone holds the whole history the range checks read. A `git worktree` or a `--shared` clone would break inside the container, since their `.git` points outside it, so the clone is a full `--no-local` one. |
| `actions/setup-python@v5`, `python-version: "3.12.3"`, `cache: pip` (every test job) | Flag, online | The job image has no tool cache for Python (`/opt/hostedtoolcache/Python` absent; its own `python3` is 3.12.3) **(measured, the job image)**, so setup-python downloads 3.12.3 from GitHub's `actions/python-versions` on each run (online, answer 3). **On the host it failed in four of five test jobs (C2503):** act mounts one tool-cache volume (`act-toolcache`) into every job, and each job's install began by deleting the others' ("Deleting Python 3.12.3"). The fix, Python 3.12.3 already in the image's tool cache, waits on the operator's licence decision (section 9). |
| "Install the host's versions, exactly" (pip from PyPI, `--require-hashes`) | As is, online | pip reaches PyPI through Docker's bridge (answer 3). |
| Information steps (`nmas-env-facts`, `pip check`, the image key) | As is | `|| true`, and `ImageOS`/`ImageVersion` are unset under act, so the key reads `unknown-unknown`. The cache keys then differ from GitHub's, which is harmless. |
| `actions/cache@v4` (promtool, PostgreSQL's packages), `actions/cache/restore@v4` and `/save@v4` (mutation's record) | Flag, **unsettled** | act's own cache server (`--cache-server-path`, kept in the store between runs), bound to the bridge gateway. Whether it answers actions/cache v4 is not yet measured. A miss is safe: the download steps below run. Settled by the cache step's log on the second run (section 12, step 6). |
| The promtool and PostgreSQL download steps (`sudo apt-get`, PGDG's script, on a cache miss) | As is, online | The job's steps run as root **(measured, probe 4)**, inside a throwaway container. They need the network on a miss only. |
| "PostgreSQL 18 for the records tests" (`sudo dpkg -i`, the server unpacked) | As is, with the image's libraries | It installs into the throwaway container, never the host. **On the host it failed in shard b (C2503), reproduced on the laptop 2026-11-04:** the image's libraries were older than Ubuntu's archive, so the download step fetched their upgrades too (45 packages beside the server's), and `dpkg -i` in name order refused libpam-modules, whose pre-dependency libpam-modules-bin was unpacked and not yet configured. The job image now holds libpq5 and the server's libraries (section 9), so the step downloads only the server, and nothing is left to configure. |
| **"Allow a network namespace ..." (`sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`, all three)** | **Skipped under act, said why** | A job container's `/proc/sys` is read-only, and the setting is the HOST kernel's, never a job's to change. Each of the three workflows now carries `if: ${{ !env.ACT }}` on the step (act sets `ACT=true`), with `env: {NMAS_ACT_NOT_GATING: "<why>"}` beside it; GitHub runs it as before. The verdict lists it "not run (act)", non-gating. Skipping it cannot pass a run: the tests step still refuses unless the suite's namespace can be made (C46). With the jobs' profile, the namespace IS made inside a container with the host's restriction on **(measured, the laptop: `apparmor_restrict_unprivileged_userns=1`, section 10)**. |
| **The tests step's confinement** (`scripts/nmas-test`'s `unshare -rn` then `ip link set lo up`; mutation's `unshare -rn`; the red-green step's runs) | Flag (answer 1) | Docker's default profile refuses it **(measured)**; the jobs' profile allows it, and still refuses a mount or a PID namespace **(measured)**. `ip` was missing from act's medium image **(measured)**: the job image adds iproute2. |
| **The tests run as root** (GitHub's runner runs as `runner`, uid 1001) | **Unsettled** | The jobs' steps run as root **(measured, probe 4)**, and nmas-test maps its namespace back to the caller's uid, so the suite runs as root. A test that checks a refusal to read a mode-0000 file passes or fails differently as root. The first run's failures name them (section 12, step 5); the fix is `--container-options "--user 1001"` with sudo for the setup steps, if the image allows it **(recalled: unverified)**. |
| **The browser tests** (browser1 to browser3; tests/browser.py's `available()`) | Flag (answer 2) | The job image carries Firefox 158.0.1 and geckodriver 0.37.1; Firefox starts headless in it under the jobs' profile **(measured)**. A browser test skipped for any of `available()`'s three reasons is recorded NOT RUN, so a broken browser makes the verdict not green (tested). |
| `actions/upload-artifact@v4`, `actions/download-artifact@v4` within one run | Flag | act's artifact server (`--artifact-server-path`, the run's folder) answers v4 across jobs on the bridge **(measured, probe 4: one job uploaded, the next downloaded and read it)**. `include-hidden-files` and `merge-multiple` are not yet measured: the coverage job finding `.coverage.*` on the first run settles them. |
| The range checks (removed definitions, host steps, weakened tests, guards, bypasses, premises) | As is | Plain `python` over `BEFORE..AFTER` in the full clone. The red-green check also needs the confinement row's answer. |
| The coverage job's ratchet, `$GITHUB_STEP_SUMMARY`, `$GITHUB_OUTPUT`, annotations | As is | `$GITHUB_OUTPUT` works **(measured, probe 1: a job's output fed the next job's matrix)**; the summary file **(recalled)**. The summary is kept in the run's log, not drawn. |
| "Where the per-test drill-down is" (curl to the public API) | As is | `|| true`. |
| Dynamic matrix: `fromJSON(needs.scope.outputs.shards)` | As is | **(measured, probe 1: two shards from a needs output, each judged on its own)**. |
| `timeout-minutes` (jobs and steps) | As is, partly unsettled | act honours a step's `timeout-minutes` and a job's **(recalled)**. The wrapper's whole-run bound (180 min, killed and recorded red) is the backstop either way. |
| `if: ${{ !cancelled() }}`, `always()`, `hashFiles()`, `format()` | As is | `always()` after a failure runs, and a step after a failure is skipped **(measured, probe 2)**; the rest **(recalled)**. |
| mutation-nightly's `window` job (`date -u`) | As is | |
| mutation-nightly's "The newest coverage drill-down" (curl to the public API for coverage-nightly's newest green GitHub run) | As is, and it reads GITHUB's nightly | Once the nightlies move here (section 5), it should read the local coverage run instead, a workflow change at that cutover. |
| mutation-nightly's "Download it" (download-artifact with `run-id` and `github-token`: another GitHub run's artifact) | **Cannot** | act's artifact server holds only its own run's artifacts. The step already carries `continue-on-error: true`, GitHub's own non-gating declaration, so the wrapper records its failure as non-gating, said in the record, and the plan refreshes. |

**Marketplace actions:** none. Every `uses:` is GitHub's own (`actions/checkout`,
`actions/setup-python`, `actions/cache`, `actions/cache/restore`, `actions/cache/save`,
`actions/upload-artifact`, `actions/download-artifact`). act clones each once into its action
cache (`--action-cache-path`, in the store), and `--action-offline-mode` reuses them, so a run
reaches GitHub for an action only the first time **(measured, probe 4: fetched once)**.

**What the survey says, in one line:** ci.yml runs under act online, with the AppArmor step
skipped saying why and the suite confined by the jobs' profile; two things are unsettled until
the host's first run, running as root and act's cache server, and each is red or NOT RUN when
it fails, never green.

## 2. The wrapper: `scripts/nmas-local-ci`

**One definition (the operator's direction 5).** The wrapper knows no step. It does this:
1. fetches origin into a root-owned bare mirror;
2. makes a fresh, full clone detached at main's tip;
3. reads Docker's bridge gateway (`docker network inspect bridge`), and stops with an error
   record if Docker cannot name it;
4. runs `act push -W .github/workflows/ci.yml -e <event> -C <clone> -P <platform>
   --pull=false --action-offline-mode --action-cache-path ... --artifact-server-path ...
   --cache-server-path ... --network bridge --json --verbose --rm --artifact-server-addr <gw>
   --cache-server-addr <gw> --container-options "--security-opt seccomp=<profile>"`;
5. drops act's environment dumps from its log (act `-v` prints every step's environment; no
   secret is passed, but the store is world-readable);
6. reads act's own per-step results;
7. writes the verdict.

Why act, by practice: one pipeline definition is the configuration-as-code rule. A second
definition (a hand mapping, or a Jenkinsfile) drifts from the first. act runs the workflow
file itself, in containers, which are the standard isolation for CI jobs.
- **Not a GitHub self-hosted runner:** GitHub's own guidance is to use self-hosted runners
  only with private repositories, because a public repository's pull requests can run code
  on them. A self-hosted runner also needs GitHub to dispatch every job, which defeats
  "deploys don't wait for it".
- **Not Jenkins:** a heavy second definition (the operator).

**How the verdict is judged** (`judge`; tests/test_local_ci.py):
- **Every job must be in act's log.** For each job the workflow defines, act must report it, and each matrix run it reports is judged on its own (`test (a)`). A job act reports nothing of is **NOT RUN**.
- **act's own "Set up job" is part of the job.** It is logged as `stepid` (lower case) **(measured)**; when it fails (the image absent, Docker refusing the container) the job has **NO VERDICT**, naming it, and its steps never started.
- **Every step needs a result.** Each step of each reported job must have one in act's log; one without is **NOT RUN**, named. A Post stage's failure counts. A step that failed counts unless the workflow declares it non-gating (`continue-on-error: true` on the step or the job, GitHub's own declaration), and then:
  - **a verdict step's failure is FAILED** (red), named with its job's log. The verdict steps are `VERDICT_STEPS` in the script, by their ci.yml names: the tests, the skip check, the range and commit checks, and the coverage job's ratchet. A test holds that each is a step of ci.yml, so a rename fails;
  - **any other step's failure is NO VERDICT** (the operator, 2026-11-04, C2503: "a failure in a job's setup steps is 'no verdict, run again', never red"). Such steps are checkout, setup-python, the caches, pip, the promtool and PostgreSQL installs, and the artifact uploads and downloads. A step added to ci.yml is a setup step until it is named a verdict step, so a new setup step can never turn a run red;
  - **a job whose needed job had no verdict has none either**, followed through `needs:`: the coverage job's ratchet after a test job's setup failed is no verdict.
- **"skipped" is act's answer to a step's `if:`, as on GitHub,** with one exception. act logs a skip only at debug level ("Skipping step ... due to ...", `stepResult: skipped`) **(measured)**, so act runs `--verbose`; without it a skipped step would read as not run. A step skipped by `if: ${{ !env.ACT }}` (skipped because it runs under act) is **NOT RUN**, unless its own `env:` carries `NMAS_ACT_NOT_GATING: "<why>"`. The declaration lives in the workflow, beside the step.
- **A browser test skipped for want of a working Firefox** (in the JUnit files act's artifact server kept) is **NOT RUN**.
- **The state.** `passed`: all ran, none failed. `failed`: a verdict step failed (whatever else did), or act past its bound. `error`, no verdict: a setup step failed and no verdict step did, or act reported no job, or the bridge could not be read. `incomplete`: nothing failed, something not run; never green.
- **No verdict, said as such.** A setup failure's record carries `infrastructure: {"job", "step"}` (the first; `infrastructure_failures` lists each, with its job's log) and the reason "NO VERDICT: infrastructure failure in `<job>`'s step `<step>`: run again". `run` prints that line and exits 75, the gate's code for a run that could not judge (scripts/nmas-gate, C2410); `tick` prints it to the journal. `scripts/nmas-deploy` reads `error` as no verdict: it never refuses a deploy on it, and never reads it green (section 4).
- **act's log format is in one table**, `F` in the script, as act 0.2.89 writes it **(measured: tests/fixtures/act/, the captured lines the tests read)**. A later act that differs is corrected in `F` alone.

**Practice that settles the rest:**
- **Trigger: polling, not a post-receive hook.** Pushes go to GitHub, whose server runs no hook of the operator's, and a webhook to the host would need a public endpoint (outside the lab: the operator's). Polling an origin is Jenkins' "Poll SCM" and GitLab's pull mirroring. `nmas-local-ci.timer` fires 2 minutes after the last run ENDED, so runs never overlap.
- **One commit at a time; the newest tip, intermediates skipped.** Buildkite calls this "skip intermediate builds" and GitLab "auto-cancel redundant pipelines". The range checks still cover every commit, since the event's `before` is the last tip the runner ran. GitHub keeps running every push, so an intermediate commit still has GitHub's verdict.
- **A fresh environment at the exact sha.** A fresh clone, and act's throwaway containers from an image pinned by content. Reproducible builds pin the build environment by content, not by tag.
- **Bounds.** The workflow's own `timeout-minutes`, and a whole-run bound of 180 minutes: ci.yml's job bounds summed (3 + 5 x 26 + 10 = 143 minutes, its jobs one after another here) plus a quarter for container starts. It is re-derived as 2.5 times the median of the host's recorded `duration_s` once a week of runs exists (CLAUDE.md, bounds from measurement).
- **Root-owned: the standard library and the system's python3-yaml only.** It runs as `/usr/bin/python3 -I`, by its shebang and by the unit's ExecStart, and never imports the user-writable checkout (the updater's rule, docs/UPDATE.md). git, act and docker run by absolute path, and root's git allows only the https and file transports. For that reason the runner does not take the app's interpreter or `repo.run_git`, as `scripts/nmas-oxidized-cred` does not. tests/test_app_interpreter.py exempts both from the app-interpreter rule and holds them to this one instead (`root_copy_problems`): the shebang and every unit running the copy name `/usr/bin/python3 -I`; every import, top-level or inside a function, is the standard library's or a declared system package's, never a name the checkout holds; and nothing adds to `sys.path` or loads a module by name or by file. A planted import from the checkout fails it. Docker access is root-equivalent, so the service runs as root, and the jobs' isolation is the containers.
- **A quiet window** (`NMAS_LOCAL_CI_QUIET`, in the unit's environment file; this lab sets 08:30-09:10 UTC, the nightly backup): no run starts inside it.

## 3. The verdict record, per sha and tree

`/var/lib/nmas-local-ci/verdicts/<sha>.json` (the store root 0755, records 0644, both root's).
Each record holds:
- schema 1, `kind: push`, the sha, its **tree**, the event's `before`;
- the state (queued, running, passed, failed, error, skipped, incomplete);
- when it started and ended, and its duration;
- the runner's own sha256 and the commit it was installed from;
- the platform (the job image's ID), and the workflow file and its sha256;
- `confinement` (the seccomp profile's path and sha256, the Docker network, the cgroup
  parent), `network` ("online") and `limits` (the slice whose caps bound the run);
- each job's matrix, result and steps (name, result, duration, non-gating);
- `failed`, `infrastructure_failures` and `not_run`, each naming the job, the step and the log
  (`runs/<sha>/<job>.log`; act's whole log is `runs/<sha>/act.jsonl`), and `infrastructure`,
  the first setup failure's job and step, or null.

How it is written and read:
- **Written whole, then renamed:** a temporary file in the same folder, synced, renamed, the
  folder synced. A record already there that cannot be read is refused, never overwritten.
- **Read by `scripts/nmas-deploy`'s `local_verdict`,** which trusts nothing it has not
  checked:
  - the store, its folder and the record must be root's and writable by nobody else, or the
    state is `untrusted`;
  - a link is not followed;
  - a record that does not parse, names another sha or has an unknown state is `unreadable`,
    never a pass;
  - the record's tree must equal git's tree for the sha, or the state is `other-tree`.
- **One shape at both ends:** tests/test_local_ci.py writes a record through the runner and
  reads it through the gate.

## 4. Who reads the verdicts

**`scripts/nmas-deploy`'s `ci_verdict`**, which the terminal deploy, the root-owned updater
(through its installed copy; a host step) and the ci-verdict and app-pushed readers all call:

| Local runner | GitHub | Outcome |
|---|---|---|
| passed | anything but FAILED: pending, no run yet, or cannot be asked | **deployed now**, "LOCAL CI passed ...", GitHub asked once, never waited for |
| passed | FAILED, known now | refused, "the two CI runners DISAGREE", naming both; rerun GitHub's run once, or `--override-ci-red "<reason>"` |
| failed | anything | refused, naming the step and its log, GitHub not asked; with an override, deployed only if GitHub PASSED it |
| queued or running | pending, cancelled or cannot be asked | PENDING: `--wait` follows whichever ends first, its bound 2.5 times the local runner's median run |
| none, absent, incomplete, error, untrusted, other-tree | any | GitHub's verdict as before (its walk and its rules), the local state said |

How the rest works:
- **A red from either runner, known at deploy time, refuses.** The operator's words ("Refuse
  only when a GitHub red is known at deploy time") were said of the case where the local runner
  is green; the local red is read the same way, since it is always known at deploy time and the
  rule is "keep refuse". The override deploys over either red when the other runner passed.
  This is the one reading of the rule the operator has not said in so many words.
- **Which runner is said:** `verdict_source` reads the sentence's opening words, the script's
  constants: `local`, `github`, `both` or `override`. The audit row records it as
  `ci_source`, and an override records the reason, the person and the verdict.
- **The Update page:** "CI passed this release (the local CI runner on this host)", or
  "(GitHub's CI)".
- **The safe-deploy script** calls `nmas-deploy --to`, so it takes all of this unchanged.
- **The same-tree reuse is kept.** A rollback whose tree is that of a commit this checkout
  ran takes that commit's verdict, GitHub's or the local runner's. The local twin works with
  GitHub unreachable (an offline rollback).
- **The override is the terminal's alone (answer 5):** `--override-ci-red "<reason of at least
  3 words>"`. The Update button has no override, and the updater's call passes none (tested).

## 5. The scheduled jobs stay on GitHub (C2504)

**The operator, 2026-11-04: the runner runs only push-triggered CI (ci.yml) for new shas.**
The coverage nightly and the weekly mutation run stay on GitHub's schedule, and the local
runner never starts them. This replaces direction 1's "the scheduled jobs move to it" and the
parallel-run plan that followed it.
- **Why:** its first tick on the host counted every scheduled workflow as due and started the
  coverage nightly and the mutation run at once (C2504). That was an unscheduled mutation run
  under the weekly rule (CLAUDE.md: no other run is dispatched).
- **What `tick` does:** fetch; run ci.yml at main's new tip, if that tip has no verdict;
  nothing else. It never reads a workflow's `schedule:` trigger, and it starts nothing on
  another branch's tip. A test holds both: a planted workflow whose cron is due every minute
  starts nothing, and only ci.yml runs, for main's tip.
- **Removed with it:** the cron matcher, the `scheduled/` record folder, and each schedule's
  last start in `state.json` (dropped the next time `tick` writes it). The host step removes
  the folder and the scheduled runs' logs (section 11, step 11).
- **What stays on GitHub:** ci.yml on every push and pull request (point 3), the nightlies on
  their crons, and their `workflow_dispatch`.

## 6. The disagreement row (the ci-agreement reader)

`modules/readers/ci_agreement.py`, every 15 minutes:
- **What it reads:** one GitHub request for main's last 50 push runs, with each commit's runs
  judged by `nmas-deploy`'s `verdict_of_runs`, and the local record judged by `local_verdict`.
- **Where a red failed** is asked once and kept while the run is the same.
- **The rows** are made at each read of the page, in `attention.ci_agreement_source`, one per
  commit at most:

| Kind | Level | When | Clears |
|---|---|---|---|
| `red-after-deploy` | danger | the running commit, deployed on the local green, failed by GitHub since; names where it failed, offers the one rerun (attempt 1), and names `scripts/nmas-rollback <the previous commit> --push`, then Update | GitHub's latest run for it passes (a green rerun), or the host runs another commit |
| `disagree` | warning | a commit the host does not run, one green and one red | the two agree, or a newer commit's two verdicts agree (superseded) |
| `unread` | warning | the local record for a listed commit is untrusted, unreadable or of another tree | the record reads, root's alone, for that commit's tree |

## 7. Batching (a statement of practice; no code)

**Deploy in small batches, a few times a day, unless a fix is urgent.** This is DORA's
small-batch practice and the release-train practice.
- **What a batch is:** the newest commit with a green verdict, deployed at a few fixed points
  in the day.
- **What goes out at once, outside a batch:** a fix to a broken deploy, to a security or data
  safety finding, or to an open A row.
- **What stays small:** each batch is small enough that its rollback (about 2.5 minutes,
  docs/TESTING.md, "The deploy bar") is cheap.
- **Deploys never wait for GitHub (point 3),** so a batch takes the local green as soon as it
  is recorded.

## 8. What stays separate: offline update (C2370) and an offline forge

- **The product's offline update (C2370) is not this workstream's.** An installed Mercury
  updates through gates that need GitHub. Its fix is signed release artifacts verified at
  install (Stage 10).
- **The local runner removes GitHub from the DEVELOPMENT loop's verdict only.** It still
  fetches from GitHub until an offline forge exists, which is Forgejo or Gitea Actions, a
  Stage 10 note.
- The note texts for docs/NSOT_STAGE10_PLAN.md are in the workstream's report, for the
  operator to place.

## 9. The decisions, answered (2026-11-03)

1. **The suite's confinement inside act's containers: a seccomp profile, least privilege.**
   Built as the table above says. CAP_SYS_ADMIN and an unconfined suite are not used.
2. **The runner image: the derived image.** See "The runner image" below.
3. **Offline pip and setup-python: online for now.** Offline later means a wheelhouse kept on
   the host with ci.yml's install step taking `--no-index --find-links` under act, and
   setup-python's 3.12.3 kept in a tool cache volume. That is the difference between "runs
   without GitHub" and "runs without the internet", and it is not this workstream's yet.
4. **CPU and memory caps: after the first measured run** (section 12, step 4). **Set
   2026-11-04, on a systemd slice** (the operator: "the runner shares the NMAS host with
   Mercury: cap it with systemd"):
   - **Why a slice:** the job containers are Docker's children, outside the service's cgroup,
     so caps on the service alone would bound nothing of CI. The host runs Docker 29.1.3 with
     the systemd cgroup driver on cgroup v2. The runner passes `--cgroup-parent=nmas-local-ci.slice`
     in act's `--container-options`, beside the seccomp option, so every job container is in
     the slice. The service runs in it too (`Slice=nmas-local-ci.slice`). The slice's caps then
     bound the runner and all its containers together **(measured on the laptop, Docker 29.1.3,
     systemd driver: a job container act started is in
     `/nmas.slice/nmas-local.slice/nmas-local-ci.slice/docker-<id>.scope`)**. systemd reads the
     dashes as nesting, so its parents `nmas.slice` and `nmas-local.slice` are made on demand,
     uncapped.
   - **The caps** (`deploy/systemd/nmas-local-ci.slice`, each with its reason there):
     CPUQuota=200% (two of the host's four CPUs); MemoryMax=6G and MemoryHigh=5632M (15.5 GiB
     less Mercury's 6.6 GiB, with about 2.9 GiB kept, and reclaim before a kill); CPUWeight=20
     and IOWeight=20. They start from the first run's peak (1.87 GiB and 1.5 CPUs together,
     a run whose setup failed in four of five jobs). The operator's measurement, Mercury's
     `/v2/` response time with a run in progress and without, may move them (section 12, step 4).
   - **Within the slice the runner yields:** `Nice=19`, `IOSchedulingClass=idle`.
   - **Never uncapped by accident:** Docker makes a missing slice on demand with no caps
     **(measured: `MemoryMax=infinity`, `CPUQuotaPerSecUSec=infinity` with no unit file)**, so
     the per-run self-test refuses a run unless systemd has the slice loaded with a MemoryMax
     and a CPUQuota.
5. **The override: the terminal's alone.** No in-app override is built; one would need its own
   board.

### The runner image

`deploy/local-ci/runner.Dockerfile`: act's medium Ubuntu 24.04 image, `catthehacker/ubuntu`,
pinned by its index digest (built 2026-08-15, image version 20260815), with:
- **Firefox 158.0.1 and geckodriver 0.37.1**, the versions the laptop's gate runs its browser
  tests with, each checked against its published sha256 (Mozilla's SHA256SUMS; the GitHub
  release asset's digest);
- **iproute2**, since scripts/nmas-test brings loopback up with `ip` and act's medium image
  has none **(measured)**;
- Firefox's shared libraries (GTK 3, ALSA) and two font packages;
- **PostgreSQL 18's libpq5 and the server's libraries** (C2503), from PGDG's repository as
  ci.yml's PostgreSQL step adds it, read the step's own way (every `lib...` that
  postgresql-18 depends on). Without them, the step's download also fetched upgrades of the
  image's older libraries, and its `dpkg -i` refused libpam-modules (section 1). With them
  the step downloads only the server's package and installs nothing **(measured on the
  laptop, 2026-11-04: the step's two commands in a container from the old image fail on
  libpam-modules; from the new one they pass, `postgres (PostgreSQL) 18.6`)**. A `dpkg -i`
  of the same versions over themselves, a cache hit's case, passes too **(measured)**.

**Held back for the operator: Python 3.12.3 in the tool cache (C2503's setup-python).**
- **What it is:** actions/python-versions' own build of 3.12.3 for Ubuntu 24.04, the file
  setup-python downloads. Release `3.12.3-11057844995`,
  `python-3.12.3-linux-24.04-x64.tar.gz`, 121,683,532 bytes, sha256
  `07ef2452a390e76505b5a26b37bae7f88bc260926ca70ae88cb679003ab42279`. The sha256 was
  computed from the download on the laptop, 2026-11-04; the release asset publishes no
  digest. It is installed by its own `setup.sh` into `/opt/hostedtoolcache/Python/3.12.3/x64`,
  with the `x64.complete` marker.
- **Why it waits:** its licence is PSF-2.0 (the tarball's `lib/python3.12/LICENSE.txt`; the
  build repository is MIT). Python is not yet listed in docs/THIRD_PARTY_DEV_TOOLS.md, and it
  is not an OS package. The licence is the operator's to approve.
- **Measured on the laptop with act 0.2.89 (2026-11-04), three jobs at once:**
  - **from an image without it:** each job found no 3.12.3 and downloaded it into act's
    shared tool-cache volume; two of the three failed after another's "Deleting Python
    3.12.3", the host's failure reproduced;
  - **from an image with it:** all three logged "Successfully set up CPython (3.12.3)" in
    about 0.2 s, with no download, and `python` was the tool cache's.
- **The host step it needs:** act mounts the named volume `act-toolcache` over
  `/opt/hostedtoolcache`, and Docker copies the image's files into it only while it is empty
  **(measured)**. The host's volume holds the first run's partial installs, so it is removed
  once (`sudo docker volume rm act-toolcache`) before the first run on the new image.
- **The block:** in the workstream's report, ready to add after the operator's decision.
  setup.sh upgrades pip from PyPI as it installs, as it does on GitHub's runner.

Sizes **(measured on the laptop, 2026-11-04)**: by `docker image inspect`'s Size, the job
image before this change is 720.7 MB, with PostgreSQL's libraries 749.2 MB (28.5 MB more),
and with Python 3.12.3 too 866.0 MB (116.8 MB more). `docker images` shows 3.01 GB on disk
for the image with PostgreSQL's libraries, the measure the 2.89 GB below was taken in. The
build took 58 s with the base cached.

Sizes **(measured on the laptop, 2026-11-03, Docker 29.1.3)**: the base downloads 567 MB
compressed (6 layers) and takes 2.3 GB on disk; the job image takes 2.89 GB. The build took
2 min 6 s with the base's download, 51 s without it. The image is built once on the host and
kept; every run uses it from Docker's store, and only a change to the Dockerfile rebuilds it.

Not the full act image (`catthehacker/ubuntu:full-24.04`), which carries GitHub's whole tool
set at tens of gigabytes: the job image adds only what the suite measurably needs.

## 10. The laptop measurements (2026-11-03, act 0.2.89, Docker 29.1.3)

None of these is the host's; each says what the host's first run should see.
1. **act's log format** (probes 1 to 3, act's self-hosted mode, no container): the fields
   `F` names; a skip only at debug level; `stepid` for act's own phases; times with the clock's
   offset; act exits 0 when the only failure is non-gating, 1 on a gating one. The captured
   lines are tests/fixtures/act/, with the probe workflows beside them.
2. **The seccomp profile** (`docker run --rm --network none`, ubuntu:24.04 and the job image;
   the laptop's `kernel.apparmor_restrict_unprivileged_userns` is 1, Docker's AppArmor
   profile in force): `unshare -rn` fails under Docker's built-in default and under moby's
   `seccomp/v0.1.0` file, and passes under the derived profile; the nested
   `unshare --map-user=1001` that nmas-test makes passes; `unshare -rnm` (a mount namespace)
   and `unshare -rnp` (a PID namespace) are refused. Firefox logs "Sandbox: CanCreateUserNamespace()
   clone() failure: EPERM" (its own sandbox uses clone, which the profile leaves refused) and
   still runs.
3. **The job image:** built, Firefox headless took a screenshot of about:blank under the
   derived profile, loopback came up inside `unshare -rn` once iproute2 was added, `python3`
   is 3.12.3 with no tool cache, and its steps run as root.
4. **act in container mode with the runner's flags** (probe 4: two jobs): the profile, the
   bridge and the gateway-bound servers accepted; the suite's confinement in a job; an
   artifact uploaded by one job and downloaded and read by the next (v4); the actions fetched
   once; 12 s in all.

## 11. The host step (the operator's; each command with its check and its undo)

Run from the host's checkout, at the deployed commit. Every value is written out or read from
the host itself; `<checkout>` below is the host's checkout path (the `checkout` value of
data/lab_hosts.json), and `<account>` the repository's owner, read from the checkout's origin.

1. **Docker and the YAML reader** (OS packages, approved by the dev-tools rule):
   `sudo apt-get install -y docker.io python3-yaml`.
   - Check: `docker version --format '{{.Server.Version}}'`, `/usr/bin/python3 -I -c 'import
     yaml'`, and the licences in `/usr/share/doc/docker.io/copyright` and
     `/usr/share/doc/python3-yaml/copyright` (Apache-2.0; Expat) for docs/THIRD_PARTY_DEV_TOOLS.md.
   - Undo: `sudo apt-get remove docker.io` (python3-yaml is harmless to keep).
2. **act 0.2.89, pinned and verified** (released 2026-06-01; the newest release at least two
   weeks old on 2026-11-03):
   `d=$(mktemp -d) && curl -fsSL -o "$d/act.tar.gz" https://github.com/nektos/act/releases/download/v0.2.89/act_Linux_x86_64.tar.gz && echo "0191d6f1f3b716b5c55820032605d05fc3c1cdbf581ebeff655019e5dd1524c0  $d/act.tar.gz" | sha256sum -c - && tar -xzf "$d/act.tar.gz" -C "$d" act LICENSE && head -1 "$d/LICENSE" && sudo install -o root -g root -m 0755 "$d/act" /usr/local/bin/act && rm -r "$d"`.
   - Check: `act --version` prints `act version 0.2.89`; the LICENSE's first line is `MIT License`.
   - Undo: `sudo rm /usr/local/bin/act`.
3. **The store:** `sudo install -d -o root -g root -m 0755 /var/lib/nmas-local-ci
   /var/lib/nmas-local-ci/verdicts /etc/nmas`.
   - Check: `stat -c '%U %a' /var/lib/nmas-local-ci` prints `root 755`.
   - Undo: `sudo rm -r /var/lib/nmas-local-ci`. The deploy gate then says nothing of a local
     runner and uses GitHub alone.
4. **The runner, root-owned, from the checkout's deployed commit:**
   `sudo install -d -o root -g root -m 0755 /usr/local/lib/nmas-local-ci`, then
   `sudo install -o root -g root -m 0644 <checkout>/scripts/nmas-local-ci /usr/local/lib/nmas-local-ci/nmas-local-ci`,
   then `git -C <checkout> rev-parse HEAD | sudo tee /usr/local/lib/nmas-local-ci/installed-from`.
   - Check: `sudo cmp <checkout>/scripts/nmas-local-ci /usr/local/lib/nmas-local-ci/nmas-local-ci`.
   - Undo: `sudo rm -r /usr/local/lib/nmas-local-ci`.
5. **The jobs' seccomp profile, from Docker's own default:** the laptop's Docker 29.1.3
   vendors moby/profiles `seccomp/v0.1.0` (moby's go.mod at `docker-v29.1.3`). If the host's
   `docker version` differs, read the `github.com/moby/profiles/seccomp` line of moby's go.mod
   at `docker-v<that version>` and use that tag; v0.1.0's file is below.
   `d=$(mktemp -d) && curl -fsSL -H "Accept: application/vnd.github.raw" -o "$d/default.json" "https://api.github.com/repos/moby/profiles/contents/seccomp/default.json?ref=seccomp/v0.1.0" && echo "01536f1d1df938ae611eba20d6349e0de7a99b6ecdee1549427a0b01b8301e28  $d/default.json" | sha256sum -c - && sudo /usr/bin/python3 -I /usr/local/lib/nmas-local-ci/nmas-local-ci seccomp-profile --from "$d/default.json" --out /etc/nmas/local-ci-seccomp.json && rm -r "$d"`.
   - Check: it prints "one rule added"; `stat -c '%U %a' /etc/nmas/local-ci-seccomp.json`
     prints `root 644`. From the laptop's v0.1.0 file the result's sha256 began `d5c2f4c6615a`.
   - Undo: `sudo rm /etc/nmas/local-ci-seccomp.json`.
6. **The job image, built once and pinned by its ID:**
   `d=$(mktemp -d) && sudo docker build -t "nmas-local-ci-runner:$(sha256sum <checkout>/deploy/local-ci/runner.Dockerfile | cut -c1-12)" -f <checkout>/deploy/local-ci/runner.Dockerfile "$d" && rmdir "$d"`,
   then `img=$(sudo docker image inspect --format '{{.Id}}' "nmas-local-ci-runner:$(sha256sum <checkout>/deploy/local-ci/runner.Dockerfile | cut -c1-12)")`.
   - Check: the build's last steps print `Mozilla Firefox 158.0.1` and `geckodriver 0.37.1`;
     `sudo docker image inspect --format '{{.Size}}' "$img"` (record it beside the laptop's).
   - Undo: `sudo docker image rm "$img"`, and the base:
     `sudo docker image rm catthehacker/ubuntu@sha256:c58e2b364da03b0c804c7d660f2ecbedf2f221a382b9baa0b344b0144780ff43`.
7. **Its settings**, root-owned, in `/etc/nmas/local-ci.env` (0644):
   - `NMAS_LOCAL_CI_ORIGIN=https://github.com/<account>/Agentic_NMAS.git`;
   - `NMAS_LOCAL_CI_PLATFORM=ubuntu-24.04=$img`, the ID from step 6, written out;
   - `NMAS_LOCAL_CI_SECCOMP=/etc/nmas/local-ci-seccomp.json`;
   - `NMAS_LOCAL_CI_QUIET=08:30-09:10`.
   - Check: `sudo /usr/bin/env $(cat /etc/nmas/local-ci.env) /usr/bin/python3 -I
     /usr/local/lib/nmas-local-ci/nmas-local-ci self-test` prints "self-test passed" (it also
     starts Firefox and geckodriver in the image).
   - Undo: `sudo rm /etc/nmas/local-ci.env`.
8. **The units and the slice that caps them**, rendered into a fresh folder and installed by
   name:
   `d=$(mktemp -d) && scripts/nmas-render-units --out "$d" deploy/systemd/nmas-local-ci.slice deploy/systemd/nmas-local-ci.service deploy/systemd/nmas-local-ci.timer && sudo install -o root -g root -m 0644 "$d/nmas-local-ci.slice" "$d/nmas-local-ci.service" "$d/nmas-local-ci.timer" /etc/systemd/system/ && sudo systemctl daemon-reload && rm -r "$d"`.
   - Check: `systemctl cat nmas-local-ci.service` shows `Slice=nmas-local-ci.slice`, `Nice=19`
     and `IOSchedulingClass=idle`; `systemctl show nmas-local-ci.slice -p LoadState -p
     CPUQuotaPerSecUSec -p MemoryHigh -p MemoryMax` prints `LoadState=loaded`,
     `CPUQuotaPerSecUSec=2s`, `MemoryHigh=5905580032` and `MemoryMax=6442450944`; step 7's
     self-test passes, since it refuses a slice without its caps. During a run, `systemd-cgls
     -u nmas-local-ci.slice` lists the service and each job's `docker-<id>.scope`.
   - Undo: `sudo rm /etc/systemd/system/nmas-local-ci.slice /etc/systemd/system/nmas-local-ci.service /etc/systemd/system/nmas-local-ci.timer && sudo systemctl daemon-reload`.
     To keep the units and lift only the caps, install the previous release's service (no
     `Slice=`) the same way. The runner of this release refuses to run without the slice.
9. **The first run, by hand (section 12), then the timer:** only once section 12 has read
   back, `sudo systemctl enable --now nmas-local-ci.timer`.
   - Check: `systemctl list-timers nmas-local-ci.timer`.
   - Undo: `sudo systemctl disable --now nmas-local-ci.timer`.
10. **The updater's copy of the gate** (this change touches `scripts/nmas-deploy`):
    `sudo install -o root -g root -m 0644 <checkout>/scripts/nmas-deploy /usr/local/lib/nmas-update/nmas-deploy`,
    as docs/UPDATE.md installs it.
    - Check: the About page's updater row reads installed.
    - Undo: install the previous release's file the same way.
11. **After C2504 (push-triggered CI only), once:** remove what the scheduled runs left in the
    store. `sudo rm -r /var/lib/nmas-local-ci/scheduled`, then each
    `/var/lib/nmas-local-ci/runs/<workflow>-<UTC stamp>` folder by name (`sudo ls
    /var/lib/nmas-local-ci/runs` lists them: a push run's folder is a 40-hex sha, a scheduled
    one starts `coverage-nightly-` or `mutation-nightly-`).
    - Check: `sudo ls /var/lib/nmas-local-ci` shows no `scheduled`.
    - Undo: none needed; nothing reads them.

## 12. The first measured run (the main thread's, on the host)

Outside 08:30 to 09:10 UTC (the nightly backup), with no walk in progress, after section 11's
steps 1 to 8.

**The command:**
`sudo systemctl start nmas-local-ci.service`, which runs `nmas-local-ci tick` (main's tip).
To run one named commit instead:
`sudo /usr/bin/env $(cat /etc/nmas/local-ci.env) /usr/bin/python3 -I /usr/local/lib/nmas-local-ci/nmas-local-ci run <sha> --before <sha~1>`.
In a second terminal while it runs: `sudo docker stats --no-stream` once a minute, and
`free -m`.

**What to measure:**
1. `journalctl -u nmas-local-ci.service -n 50`: the run's one line ("<sha> <state>").
2. The duration (`duration_s` in the record) against ci.yml's GitHub run for the same sha, and
   each job's steps' durations.
3. The settled rows: the range check's log line names `BEFORE..AFTER`; setup-python
   downloaded 3.12.3; the coverage job found `.coverage.*` and the tiers; the sysctl step
   reads "not run (act)".
4. **The limits (answer 4):** the peak CPU and memory of the job containers (`docker stats`),
   against what the host has free beside Mercury (`free -m`) and the app's own use. Set
   2026-11-04 as the slice's caps (section 9, answer 4). What may move them is the
   operator's measurement: Mercury's `/v2/` response time with a run in progress and without,
   and the slice's own peak (`systemctl show nmas-local-ci.slice -p MemoryPeak -p
   CPUUsageNSec` after the run).
5. **Running as root:** every failure the record names, each read against GitHub's run of the
   same sha. A test that passes on GitHub and fails here as root is the root-against-`runner`
   row, fixed by the `--user` option or by the test.
6. A second run, on the next commit main gets: the caches hit (the cache step's log says
   "Cache restored"), and nothing is fetched but the commit, the PyPI packages and Python
   3.12.3 (online, answer 3).
7. act's real log from ci.yml: copy the lines with a result (`stepResult`, `jobResult`) from
   `runs/<sha>/act.jsonl` into tests/fixtures/act/ by the same selection the probe fixtures
   used, and check `F` against them.

**Where the verdict lands:** `/var/lib/nmas-local-ci/verdicts/<sha>.json` (`nmas-local-ci
status` prints the newest ten), act's whole log in `/var/lib/nmas-local-ci/runs/<sha>/act.jsonl`
and each job's output in `runs/<sha>/<job>.log`. `nmas-deploy --to <sha>` then says "LOCAL CI
passed ..." or names what failed or did not run.

## 13. The controls (2026-11-03, each in a throwaway worktree by scripts/nmas-control)

Each removed one property from the worktree's copy and ran tests/test_local_ci.py there; every
one failed the tests aimed at it, by assertion, never a crash:

| The property removed | Tests that failed |
|---|---|
| "Firefox could not start" counted as not run | 2 (the skip itself; every reason tests/browser.py gives) |
| the profile's mask lets the two namespaces through (left at the default's) | 1 (only a user and a network namespace) |
| the profile's mask lets every namespace through | 1 (the same) |
| act run verbose | 1 (the containers' flags) |
| the jobs on Docker's bridge (set to host) | 2 (the bridge; the bridge unread) |
| act's own phases read (`stepid`) | 1 (a job whose set-up failed) |
| act's time offset honoured | 1 (the offset) |
| act's environment dumps dropped | 1 (the dumps not kept) |
| the profile's default action checked | 1 (the self-test's profile checks) |
| the deep self-test's browser start | 1 (the deep self-test) |
| the seccomp option passed to act | 1 (the containers' flags) |
| no limit before the measurement | 2 (the containers' flags; the record says unset) |
| the updater calling the gate with no override | 1 (the updater never passes one) |
| iproute2 in the job image | 1 (what the confinement runs) |
| ci.yml's sysctl step skipped under act | 2 (every kernel step says why; the real ci.yml then passed) |

## 14. The estimate, revised (agent-days; the operator's host time apart)

| Part | State | Agent-days |
|---|---|---|
| The survey and this design | done | 0.5 |
| The deploy gate's two verdicts, the scoped rule, the override, the audit row, their tests | done | 0.5 |
| The act wrapper (fetch, clone, act, the verdict, schedules, the store, self-test) and its tests | done | 1 |
| The ci-agreement reader and its rows; the Update page's source; the units; the guards | done | 0.5 |
| The five answers: the profile, the job image, the bridge, the limits unset, the terminal override; act's log captured; the workflows' act guards | done | 0.5 |
| The first host run (section 12) and what it settles: running as root, act's cache server, the limits | to do | 0.5 to 1 |
| The scheduled jobs' parallel week, then the cutover (crons file, scheduled-jobs reader on the local store) | to do | 0.5 to 1 |
| **Total** | 3 done | **4 to 5**, against "about a day" |

The day became more than four because of three things:
- act is a second execution environment with gaps that must each be named, not a copy of
  GitHub's runner;
- the suite's network confinement does not survive a default container;
- the deploy gate now reads two verdicts with a scoped refusal rule.
