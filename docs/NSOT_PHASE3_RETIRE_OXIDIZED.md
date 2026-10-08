# Phase 3: retire Oxidized (DRAFT for the operator's sign-off, 2026-10-08)

The charter (MERCURY_CHARTER, "What goes"): **Oxidized is retired.** It is a second, redundant
configuration history; GitHub owns configurations, and Mercury's own scheduled read-and-compare
replaces its polling. This draft says what depends on Oxidized today (surveyed read-only,
2026-10-08), what replaces each, the order, and the operator's host steps. Nothing is built until
it is signed off.

## 1. What is already done

- **The freshness check is off** (2026-10-08, C555 closed): `reader_job.RETIRED`, no Needs attention
  or job-health row. The drift check covers a change made outside Mercury: on the host, every
  30 minutes, 9 of 9 devices read against their goldens.
- **The lab's startup files no longer come from Oxidized** (plan item 4, 2026-10-01): the clab
  sync builds each from the newest earned baseline (`nmas-startup-source`, `startup_source.py`),
  each device's credentials from its current golden. Oxidized's copy is only a cross-check the
  sync reports and never blocks on, and the freshness gate (`POST /freshness/gate`) has no caller.

## 2. What still depends on Oxidized, and what replaces it

| Where | What it does with Oxidized | Replaced by |
|---|---|---|
| `modules/integrations/oxidized.py` | the REST client (`nodes.json`, fetch, node times) | nothing: removed |
| `modules/oxidized_fetch.py` (a post-commit hook, `archive.py`) | asks Oxidized to fetch a device whose golden changed, waits, wakes freshness | the commit itself; for the lab, the event that starts the clab sync (C553, section 3) |
| `modules/nsot/freshness.py`, `routes/freshness.py`, `readers/freshness_reader.py`, `attention.freshness_source` | Oxidized's copy against the golden; authorisations | the drift check (`modules/drift_check.py`), device against golden |
| `modules/nsot/credential_rotation.py`, `rotate_op.py` (the persist chain's `oxidized_row`, `oxidized_reload`, `fetch_confirmed`) | keeps Oxidized's router.db credential current and waits for a fetch after a rotation | nothing: Mercury's golden from the rotation's commit is the record; the chain ends at the commit and the clab sync (C333) |
| `modules/nsot/onboard.py`, `adopt.py` (`add_to_oxidized`) | adds the device to Oxidized | nothing: the onboarding's golden commit is the backup |
| `modules/nsot/retire.py`, the retire finish card (C398) | removes the router.db row and reads it back | nothing: the finish card loses its Oxidized step |
| `modules/nsot/platform.py` `oxidized_model_for_dialect` | the device's Oxidized model | nothing |
| settings (`oxidized_url`, `_username`, `_password`, `_node_identity`, `_verify_tls`, `_router_db`) and the Settings card | how Mercury reaches Oxidized | nothing: the keys retire (a settings version bump that drops them, recorded) |
| host helper rows (`host_helpers.py`, `host_steps.py`, `nmas-host-step-check`) | the root helper `nmas-oxidized-cred` and its pin | nothing |
| `job_health.py` clab-sync row's words | "Oxidized configs into containerlab startup files" (stale since plan item 4) | reworded: "the newest earned baseline into the lab's startup files" |
| `routes/monitoring_stack.py` | Oxidized's tile | nothing |

The register rows it closes or makes moot: C553 (folded in, section 3), C558, C333, C489, C520,
C332, C512, C499, D9; C329 stays (the drift check is now the read-and-compare, its own row).

## 3. The clab sync, from GitHub only, with C553 folded in

- **The script** (`scripts/oxidized-to-config.sh`, renamed `clab-startup-sync.sh`; the name is
  referenced in `lab_startup.SANITISER`, DEPLOY_LINUX and CLAUDE.md): drop its read of Oxidized's
  git store (`REPO=/opt/oxidized/...`), the cross-check, and the reconcile that walked Oxidized's
  history. Each startup file is the newest earned baseline as committed in the network's
  repository on GitHub, as today.
- **Its cross-check is Mercury's own:** `lab_startup.py` already says how each lab file stands
  against the baseline from the record (`since_baseline`), so the lab startup row needs no
  Oxidized.
- **C553, folded in:** an operation that earns a baseline starts the sync, rather than the next
  30-minute run. Mercury touches a marker file on a baseline commit (a post-commit hook, product
  code naming no lab tool); a host path unit watching the marker starts `clab-sync.service`. The
  lab tooling subscribes; Mercury never names it (the updater's pattern). The timer stays as the
  fallback. The lab startup row reads "being written now" while it runs.
- **`nmas-clab-targets` loses its `oxidized_node` column.**

## 4. Order

1. The clab sync rewrite and its marker (lab tooling, `lab/` and `scripts/`), with C553.
2. Rotation's persist chain without its three Oxidized stages (C333), and onboarding and adopt
   without `add_to_oxidized`; retire's finish card without its router.db step.
3. Remove the freshness modules, routes and tests, the fetch hook, the integration, the settings
   (with the version bump and its record), the host helper rows and the monitoring tile.
4. The operator's host steps (section 5), then the walk: a rotation, an onboarding, a Save All
   earning a baseline (the sync starts at once), a retire, all on v2.

Tests: about 308 in ten files pin Oxidized behaviour (test_oxidized_freshness 51,
test_oxidized_router_db 64, test_oxidized_helper_pin 28, test_oxidized_fetch 10,
test_onboarding_adds_to_oxidized 22, test_freshness_reader 11, test_clab_targets 49,
test_clab_sync_commit 35, test_clab_sync_runs 8, test_lab_startup 30); about 55 other files
mention it (rotation, retire, host helpers, job health). Removed with what they test, the rest
rewritten; churn is a stated cost (CLAUDE.md).

## 5. The operator's host steps (after the build, as a commit's Host-Step)

- Stop and remove the `oxidized` container; keep `/opt/oxidized/rcn-lab.git` as an archive copy
  until the operator says otherwise (the history is GitHub's already).
- Remove the root helper `/usr/local/sbin/nmas-oxidized-cred`, its pin
  `/etc/nmas/oxidized-cred.conf` and its sudoers line.
- Repoint `~/bin/clab-sync` and `clab-sync.service` at the renamed script; install the path unit
  for the marker.
- `oxidized.<domain>` is already removed (C143).

## 6. Decisions for the operator

- **P3-1:** keep the Oxidized git store as an archive copy, or delete it after a month.
- **P3-2:** the sync started by a marker Mercury touches (the updater's pattern), or by
  Mercury calling the host (not proposed: Mercury would name lab tooling).
- **P3-3:** the settings keys dropped by a version bump now, or left inert for one release.
