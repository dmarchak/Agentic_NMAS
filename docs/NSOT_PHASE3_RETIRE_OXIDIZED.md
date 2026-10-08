# Phase 3: retire Oxidized (APPROVED by the operator, 2026-10-08; decisions in section 6)

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
   **BUILT 2026-10-08:**
   - `scripts/clab-startup-sync.sh` reads no Oxidized store: no cross-check, and its reconcile
     no longer walks Oxidized's history (a write that is not this run's build is refused, named).
     The old name stays a link for one release.
   - `nmas-clab-targets` reads five columns.
   - `modules/nsot/baseline_event.py` writes `data/events/baseline-earned/<network>` on every
     commit that earns a baseline.
   - `deploy/systemd/clab-sync.path` (lab tooling) starts the sync when the lab's network's file
     moves.
   - Awaiting a walk: a Save All, and the sync starting within seconds.
   The path unit was installed by the operator (2026-10-08, active); the walk is still owed.
2. Rotation's persist chain without its three Oxidized stages (C333), and onboarding and adopt
   without `add_to_oxidized`; retire's finish card without its router.db step.
   **BUILT 2026-10-08:**
   - The persist chain goes from the device's own save straight to the lab target; rotation's
     preflight no longer checks the helper (installed, matching, sudo), so a network without
     Oxidized can rotate.
   - Onboarding's and adopt's last step is `promote`; `add_to_oxidized` is gone.
   - Retire has no router.db step, and the finish card and its route
     (`device_v2.retire_finish`) are removed: with nothing left to finish, the card had no
     work. "Oxidized's polling" is no longer a survivor.
   - Job health has no Oxidized helper row and no retired-devices router.db row (C398's).
     The helper's host-step checks (`oxidized-cred`, `oxidized-pin`) read done, "retired",
     so an old commit's step for them owes nothing; the registry keeps the helper's paths, so
     a commit still touching it names a host step until section 5 removes it.
   - Kept for step 3: the rotation's Oxidized functions (`update_oxidized_row`,
     `reload_oxidized`, `confirm_fetch`) and their tests, called by nothing in the product,
     removed with the integration.
3. Remove the freshness modules, routes and tests, the fetch hook, the integration, the settings
   (with the version bump and its record), the host helper rows and the monitoring tile.
   **BUILT 2026-10-08 as step 2b, the settings inert (P3-3):**
   - Removed: the post-commit fetch hook and `oxidized_fetch.py`; the freshness comparison
     (its four routes, reader, Needs attention source, invalidation key, script and the v1
     signal partial); the Oxidized integration, its Settings card and monitoring tile; the
     rotation's Oxidized functions; the sync map's Oxidized node column (the sync reads five);
     `oxidized_model_for_dialect`.
   - Kept: `freshness.authorisations` and its file read, so History still draws past
     authorisations. The keys stay declared, now in scope `retiring` (read by nothing, drawn
     on no Settings screen, stored values kept for a rollback). The release after removes
     them by a version bump.
   - `tests/test_oxidized_settings_inert.py` parses every tracked product file and fails on
     any read of an Oxidized key outside its declarations.
4. The operator's host steps (section 5), then the walk: a rotation, an onboarding, a Save All
   earning a baseline (the sync starts at once), a retire, all on v2.

Tests: about 308 in ten files pin Oxidized behaviour (test_oxidized_freshness 51,
test_oxidized_router_db 64, test_oxidized_helper_pin 28, test_oxidized_fetch 10,
test_onboarding_adds_to_oxidized 22, test_freshness_reader 11, test_clab_targets 49,
test_clab_sync_commit 35, test_clab_sync_runs 8, test_lab_startup 30); about 55 other files
mention it (rotation, retire, host helpers, job health). Removed with what they test, the rest
rewritten; churn is a stated cost (CLAUDE.md).

## 5. The operator's host steps (after the build, as a commit's Host-Step)

**Prepared 2026-10-08, not run.** Measured read-only on the NMAS host that day (via LAN):

- Containers: `oxidized` (image `oxidized/oxidized:latest`, up, restart `unless-stopped`, started
  by `docker run`, no compose project) and `oxidized-pre-c143` (exited), both mounting
  `/opt/oxidized` as Oxidized's config folder. No systemd unit or crontab line names Oxidized.
- `/opt/oxidized` holds `config` (and two older copies), `router.db` and four backups of it,
  `crash`, `logs`, `pid`, and `rcn-lab.git` (4.3 MiB, 233 commits).
- The helper `/usr/local/sbin/nmas-oxidized-cred`, its pin `/etc/nmas/oxidized-cred.conf` and
  `/etc/sudoers.d/nmas-oxidized-cred` are present; `sudo -n -l` lists the helper once.
- `~/bin/clab-sync` is a script (not a link) that calls `oxidized-to-config.sh`, now a link to
  `clab-startup-sync.sh` (kept one release); `clab-sync.service` runs `~/bin/clab-sync`;
  `clab-sync.path` is installed and active.

**The steps, in order, each checked before the next:**

1. **Stop Oxidized and keep its store read-only** (P3-1: the bundle waits for MinIO), only once
   the release with step 2b runs on the host (before it, every golden commit's fetch hook asks
   Oxidized and fails):
   ```bash
   sudo docker stop oxidized && sudo docker update --restart=no oxidized
   sudo chmod -R a-w /opt/oxidized/rcn-lab.git
   ```
   Check: `docker ps` no longer lists `oxidized`; a Save All on v2 still commits and the lab
   sync still starts (nothing in Mercury asks Oxidized after step 2b).
2. **Remove the helper, its pin and its sudoers entry:**
   ```bash
   sudo visudo -c && sudo rm /etc/sudoers.d/nmas-oxidized-cred && sudo visudo -c
   sudo rm /usr/local/sbin/nmas-oxidized-cred /etc/nmas/oxidized-cred.conf
   ```
   Check: `sudo -n -l | grep -c oxidized-cred` prints 0; Needs attention shows no helper row.
3. **Repoint the clab sync at its new name:** edit `~/bin/clab-sync` so it calls
   `clab-startup-sync.sh`, then `sudo systemctl start clab-sync.service` once.
   Check: `journalctl -u clab-sync.service -n 20` shows a run naming no Oxidized and writing
   the lab's startup files; the lab startup row on Needs attention reads current.
4. **Remove the containers** (after a week with Oxidized stopped and nothing missed):
   ```bash
   sudo docker rm oxidized oxidized-pre-c143 && sudo docker image rm oxidized/oxidized:latest
   ```
5. **The archive, then the delete** (after Phase 4's MinIO connection, P3-1):
   ```bash
   d=$(mktemp -d) && git -C /opt/oxidized/rcn-lab.git bundle create "$d/oxidized-rcn-lab.bundle" --all \
     && git bundle verify "$d/oxidized-rcn-lab.bundle"
   mc cp "$d/oxidized-rcn-lab.bundle" lab/mercury/archive/oxidized/oxidized-rcn-lab.bundle
   e=$(mktemp -d) && mc cp lab/mercury/archive/oxidized/oxidized-rcn-lab.bundle "$e/" \
     && git clone -q "$e/oxidized-rcn-lab.bundle" "$e/clone" \
     && git -C "$e/clone" rev-list --all --count          # 233, as measured
   ```
   Only when the clone's count matches the store's: `sudo rm -r /opt/oxidized`.
6. **The settings keys** go in the release after this one (P3-3), by a settings version bump that
   records them dropped.

`oxidized.<domain>` is already removed (C143). The helper's source `scripts/nmas-oxidized-cred`,
its registry entry (`host_helpers.py`) and its host-step checks are removed in the commit after
step 2 is done, so no older commit's step reopens.

## 6. Decisions (APPROVED by the operator, 2026-10-08)

- **P3-1, archive, then delete:** Oxidized's git store stays on the host read-only until
  Mercury's MinIO connection exists (Phase 4's first step). Then its history is exported ONCE as
  a git bundle into MinIO, the archive is verified to open (the bundle fetched back and cloned),
  and only then is the local copy deleted. The deletion is a host step after that verification,
  never before it.
- **P3-2, the marker and a path unit:** Mercury touches a marker (the updater's pattern) and a
  systemd path unit on the host starts the sync; Mercury never calls the host or names lab
  tooling.
- **P3-3, inert for one release:** the Oxidized settings keys stay in the schema, read by
  nothing, for one release (so a rollback to the previous release finds them), and are removed
  by a version bump in the release after.

**Order (the operator, 2026-10-08):** after Tier 1 of the command policy, "Test the logging
path" and the Tier 2 draft (NSOT_READS.md section 11); before Phase 4. P3-1's export waits for
Phase 4's MinIO connection; everything else in section 4 does not.
