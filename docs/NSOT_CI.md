# CI: what it checks, where it runs, what it can stop, where it shows

Written 2026-09-26, before the Stage 7 GUI plan, because the GUI is where CI
becomes visible and designing screens around an undecided CI means guessing.
Everything below is from the code and the live host, not from memory. The
sources are the Jenkins audit, the task inventory and the feature audit
(docs/NSOT_FEATURE_AUDIT.md), with file:line where it matters.

## 0. What is true today

- **Nothing is configured.** Measured on the host: `jenkins_url` is empty in
  `data/jenkins_checks.json`. There is no `.github/workflows/`. The repo's own
  `Jenkinsfile` has not run: it imports `_BGP_FLAP_TOLERANCE`, which does not
  exist; expects a `check.py`, which is absent; and is all `bat` steps.
- **Jenkins carries no weight on any path that changes a device.** It
  touches the deploy path at one point: check 4 of `PipelineRunner`'s
  `ci_gate` stage (`modules/pipeline.py:618-647`). That check reads the last
  result of jobs already registered to the ACTIVE list, and blocks only if
  one reads FAILURE. It is:
  - skipped **silently** when Jenkins is unconfigured (no `else`, nothing
    logged);
  - **fail-open** on any error;
  - keyed on the active list, not the deploy's `ctx.list_name`, which breaks
    "carried, never re-derived".

  The rest of the gate is LOCAL: a dangerous-command check and a
  "no check registered for 'template'" warning on every deploy. Its docstring
  calls that warning a syntax check, and no syntax check exists.
- **What would run inside Jenkins** is `modules/check_runner.py`. It SSHes to
  devices with `device_type` hardcoded to `cisco_ios` and reads
  `devices.csv`, so every job for a NetBox-sourced list fails. It decrypts
  with `data/key.key`, so the Jenkins agent must BE the NMAS checkout with
  its live `data/`. Its `--validate-all` mode exits 0 having checked nothing
  when the active list differs from `--list-slug`.
- **Broken or dead, verified:**
  - `event_monitor` reads the wrong JSON shape, so the `jenkins_failure`
    event never fires, and neither does the agent task it feeds;
  - the Jenkins wizard emits `workflow-csd` (should be `cps`) and runs four
    scripts that do not exist;
  - `/jenkins/run` answers `triggered: true` when unconfigured;
  - `/jenkins/webhook` accepts any unauthenticated POST, so a forged
    SUCCESS satisfies `/git/commit`'s pipeline check;
  - the step shell defaults to `bat` on an Ubuntu host.
- **The "Jenkins not configured — committed without a CI pipeline" line** is
  a toast from Save All (app.py:5411-5414), not a git message. It is also
  printed when Jenkins IS configured but job creation failed, and the toast's
  advice to "commit once it passes" arrives after the commit.

**Verdict: the Jenkins integration is a demonstration that does not work as
designed, and no working path depends on it.** Whatever is decided, nothing
that works today is lost by removing it.

## 1. The split, sharpened: "private state or reach" vs "only the repository"

The proposed split, network versus files, holds, but the reason is sharper
than "network". The real question is **whether the check needs something only
the NMAS has**:
- **reach:** devices, NetBox, Loki, Oxidized, Proxmox, the clab host;
- **private state:** `data/`, `key.key`, the credential store, systemd, file
  modes.

"Network" and "private state" both mean the check runs **on the NMAS**. A
check needing only what is committed can run **wherever the repository is**.

### 1a. The check inventory

**R — needs only a repository** (can run in repo CI):

| # | Check | Repo | Exists today as |
|---|---|---|---|
| R1 | The unit suite (3,738 tests; no test touches a network) | app | `pytest` |
| R2 | No removed definition is still called | app | `scripts/check_removed_definitions.py` (pre-commit hook) |
| R3 | Route reachability and the invalidation map (Stage 7.0) | app | to be built (7.0) |
| R4 | Static rules: no IPv4 literals, inline JS parses, scripts reach their imports | app | tests in R1 |
| R5 | Every committed host_vars document validates: known keys, printable ASCII, no `secrets:` mapping or resolved value | config | `hostvars.write_committed` refuses at write; nothing re-checks the repo |
| R6 | Every golden parses with its platform parser, with unmodelled constructs acknowledged | config + app code | `roundtrip` / parsers, run by tests on fixtures only |
| R7 | Required blocks present: every device whose intent should heartbeat carries the complete syslog block | config + app code | `hostvars.syslog_block_problems`; `nmas-heartbeat-rules` reads it |
| R8 | Manifest integrity: identities unique, no duplicate name or address, platforms resolve through `platform.py` | config + app code | partly in migration and `nsot_verify_migration.py` |
| R9 | Template approvals are current: each fingerprint matches its bound device set | config + app code | `approval.is_approved`, computed at plan time |
| R10 | Seed status: which list templates are stale copies of shipped ones | config + app history | `nmas-seed-status` |

**N — needs the NMAS** (reach or private state):

| # | Check | Needs | Exists today as |
|---|---|---|---|
| N1 | Drift: running config vs golden | devices + credentials | `drift_check` (scheduled, per list; off since 2026-08-30, E4) |
| N2 | Freshness: Oxidized's copy vs golden | Oxidized | `nmas-oxidized-freshness`, `/freshness/*` |
| N3 | Deployability of the TRUTHFUL render (the real secrets in memory: sendable bytes, credential-unchanged) | credential store + key | `render_artifact` + deploy guards, at plan time |
| N4 | A startup file applies and carries the current credential | clab host | `nmas-check-startup-applies` |
| N5 | A credential logs in | devices | `nmas-check-credential` |
| N6 | Heartbeat windows fit each device's measured rate | Loki | `nmas-heartbeat-rules --check` (timer) |
| N7 | NetBox census against a baseline | NetBox | `nmas-netbox-census --compare` |
| N8 | Scheduled jobs, VM images and pools succeed | systemd, Proxmox | `nmas-jobs` / `job_health` |
| N9 | Secrets stored where declared, at the right modes | host files | `nmas-check-secret-storage` |
| N10 | Orphaned credential overrides | credential store | `nmas-credential-overrides` |
| N11 | The NetBox backup restores | docker | `nmas-netbox-restore-test` (timer) |
| N12 | Post-deploy verification (OSPF/BGP/RIP settle windows) | devices | `PipelineRunner` stage 8, inside every deploy |
| N13 | Protocol regression (OSPF FULL, BGP established, ...) on a schedule | devices | `check_runner.py`, meant for Jenkins; **duplicates N12's checks** |

### 1b. The ambiguous ones, where the decision actually lives

- **R6 and R9 (round-trip and approval currency) need no network, and they
  are ALREADY computed at plan time on the NMAS.** A repo-CI copy would be a
  second implementation of one property, and *two checks of one property
  will diverge*. **Rule: a CI job imports and calls the same module function
  the NMAS uses; it never reimplements one.** Repo CI then gives the same
  answer earlier (at commit), not a different one.
- **N3 looks like a file check and is not.** Rendering from files works with
  masked secrets, but "deployable" is decided on the TRUTHFUL render
  (sendable bytes, credential unchanged), which needs the credential store
  and the key. So repo CI can say *"this renders"* and never *"this can be
  sent"*.
- **The config repository holds plaintext secrets by design** (goldens are
  stored verbatim, masked only on the way out). A GitHub-hosted runner
  reading it processes device credentials. They already sit in that private
  GitHub repository, so this adds no NEW exposure, but it is a reason to run
  config-repo checks on a runner the operator controls.
- **N13 duplicates N12.** `check_runner`'s protocol checks re-implement the
  deploy path's post-deploy verification, a third implementation of one
  question beside the AI's. Scheduled regression is a real need. **Its home
  is a job that calls the verify stage's own functions**, not `check_runner`.

## 2. What each check can STOP

This is what decides load-bearing versus advisory, and so how the GUI shows
it.

- **Repo CI cannot block a merge here**, because there are no merges. The
  NMAS commits straight to `main` (`save_golden`, `write_committed`, the
  post-commit push), and so does development. **Where repo CI CAN gate is
  `nmas-deploy`**: it can refuse to fast-forward the host to a SHA whose CI
  failed or is still running, printing the operands. That is the one
  load-bearing use of repo CI in this system, and it needs GitHub reachable,
  which a deploy that pulls from GitHub needs anyway.
- **On the NMAS, three kinds of consequence already exist:**
  - **Gates at plan time** (they block a deploy, by name, before anything
    connects): not approved, not deployable (N3), a credential would change,
    a dangerous line unauthorised, rolled-back and not retried. These are
    load-bearing today, and they are CI in all but name.
  - **Gates at a write**: the freshness gate (N2) stops the clab sanitiser
    writing an unapproved startup file; the credential-unchanged guard stops
    a deploy mid-plan.
  - **Reports**: everything scheduled (N1, N6-N11). They cannot stop
    anything, because nothing is happening when they run; what they can do
    is **raise attention**. Drift already queues approval items; the rest
    show in `nmas-jobs`.
- **A scheduled report must never pose as a gate**, and a gate must never be
  silently skipped: the `ci_gate` Jenkins check does both at once.

## 3. Jenkins, GitHub Actions, and the air gap

**Recommendation: cut Jenkins. Run the NMAS-side checks as systemd timers
watched by `job_health`, which already works. Run repo CI on GitHub Actions
for the app repository, gating `nmas-deploy`, with a local fallback for an
air-gapped install.**

- **Jenkins's unique value was being an executor with history.** The NMAS
  now has one: systemd timers, their journals, and `job_health` naming each
  job's state and cause (P.1, P.2 and B6 built exactly this). Four timers
  already run that way. Jenkins would be a second executor, needing
  `data/key.key` on its agent and duplicating the deploy path's own checks.
- **GitHub Actions** needs no server and is already where the code lives.
  For the app repository it runs R1-R4 on every push, and `nmas-deploy`
  reads the result.
- **The air gap is real** (the operator's other project is an air-gapped
  platform). GitHub-hosted Actions and a self-hosted Actions runner both
  need GitHub. So on an air-gapped install the repo checks run **locally**:
  `nmas-deploy` runs the suite before restarting and refuses on failure. It
  takes 65 s. Forgejo or Gitea Actions (self-hosted, Actions-compatible
  syntax) is the option if repo CI must exist air-gapped. **Recorded, not
  chosen.**
- **apt availability and PyPI availability are different questions**
  (2026-09-26, C40). The host's environment comes from Ubuntu's packages, and
  pip alone cannot reproduce it: PyPI's netmiko 4.3.0 refuses the host's
  textfsm 1.1.2. So an air-gapped rebuild needs either an apt mirror with the
  same Ubuntu release, or a wheelhouse of `requirements.lock`
  (`pip download --no-deps -r requirements.lock`) installed with `--no-deps`.
  Mirroring PyPI with a resolver would reproduce neither.
- **The lock pins Python and packages, and nothing pins the kernel** (C42,
  2026-09-26). A test passed on GitHub's runner and failed on the host
  because the host stamps ext4 times from a 1 ms tick. Every run now prints
  `scripts/nmas-env-facts` as an annotation, the same probe the operator
  runs on the host, so the two lines can be compared. Closing the gap needs a
  runner on the host's kernel. On a PUBLIC repository a self-hosted runner
  runs pull-request code on the NMAS host, so it is not a default. **Open,
  the operator's call.**
- **D8 matters here**: four front-end libraries load from CDNs, so an
  air-gapped NMAS loses its topology view, drag-and-drop and terminal. The
  air-gap question is broader than CI.

**UNDECIDED, the operator's call:** whether to run R5-R10 (the config
repository) as repo CI at all, and if so, on a runner the operator controls
(see 1b's plaintext note) or on the NMAS as a job at each commit. The
recommendation is the latter: the NMAS makes every commit, and a post-commit
check there is the same functions, the same secrets domain, and no new
runner.

## 4. The agent's 19 CI tools

**Cut all 19** (16 named `jenkins_*`, plus `run_jenkins_checks`,
`run_jenkins_job` and `build_network_pipelines`). They administer a system
this document removes, and several are unsafe even with Jenkins present:
creating jobs from arbitrary XML, deleting jobs and builds, and a
`build_network_pipelines` that decrypts every device password it does not
use. **Stage 8 replaces them with at most three READ tools** over what
replaces Jenkins: `job_health` states, drift and freshness results, and the
last CI result for the deployed SHA. The agent reads CI state; it never
administers CI. The rest of the agent's library is the feature audit's
subject.

## 5. The GUI: CI has no destination

**CI is state shown beside the thing it checks** (the operator's option b).
There is no CI tab, and each result has one home:

| Result | Where it shows |
|---|---|
| Plan-time gates (approval, deployability, credential, dangerous, rolled-back) | the deploy plan, per device, each gate named with its operands |
| Post-deploy verification (N12) | the deploy result, per device |
| The repo CI result for a SHA | Versions (git history) beside the commit, and in the host's "deployed version" line |
| Scheduled reports (drift, freshness, heartbeat windows, jobs, images, pools, census) | "Is anything wrong", one row each, with the cause |
| The freshness gate's refusal | the sync's own output, and "Is anything wrong" |

**A result a payload carries is drawn.** Every CI state above already exists
in some payload. The GUI plan's rule (*if a payload carries it, the screen
shows it*) applies to CI first.

## 6. P.4 (proposed): what this document builds

| Step | Work |
|---|---|
| 1 | Remove Jenkins: routes, tab, wizard, settings section, `event_monitor` sync, `ci_gate` check 4, `agent_runner`'s Jenkins task, the 19 AI tools, `check_runner.py`, `pipeline_builder`'s Jenkins XML, `jenkins_shell`, the stale `Jenkinsfile`. Fix `drift_check`'s bare import first. Keep `data/jenkins_checks.json` readable until removed, then declare its removal to the secret checker. |
| 2 | Correct the `ci_gate` stage to say what it does: a dangerous-command check. Remove the "syntax check" claim and the per-deploy "no check registered" warning. |
| 3 | GitHub Actions workflow on the app repository: R1, R2 and R4 on every push to `main`. |
| 4 | `nmas-deploy` reads the CI result for the target SHA and refuses a failed or pending one, printing HEAD, target and result. `--offline` runs the suite locally instead (the air-gap path). Versioned into the repository (6.5). |
| 5 | Scheduled protocol regression (N13) as a timer that calls the verify stage's functions, declared in `job_health.JOBS`. **UNDECIDED** whether it is wanted at all, beside drift. |
| 6 | Config-repo checks (R5-R10) as a post-commit job on the NMAS calling the same module functions: **UNDECIDED** (section 3). |

## 7. Acceptance

1. **No Jenkins code remains** (step 1): `check_removed_definitions.py`
   reports nothing still called, the suite passes, and a test asserts no
   module imports `jenkins_runner`. **Control:** re-add one import and the
   test fails.
2. **The deploy path's gate says what it checks.** A deploy with an
   unauthorised dangerous line is refused by name, and a deploy without one
   passes with no "no check registered" warning.
3. **A red CI run stops a deploy.** Push a commit that fails R1, then run
   `nmas-deploy`: it refuses, naming the SHA and the failed run. Push a fix,
   and it proceeds. `--offline` runs the suite locally and refuses on
   failure. Measured in one run each, operands printed.
4. **Every scheduled check names its cause when it fails** (the C14 rule),
   shown by breaking one deliberately, as P.2 step 8 did.
5. **No check is implemented twice.** Scheduled regression, if built, calls
   the verify stage's functions, and a test pins it. The AI's
   `detect_config_drift` is gone with Stage 8 (feature audit).
6. **The GUI shows each CI state beside its trigger, with no CI
   destination** (the GUI plan's acceptance carries this).
