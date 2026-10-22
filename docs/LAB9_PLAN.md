# Lab 9: the plan (an ordered checklist, kept current)

**The operator's direction, 2026-10-22 ~04:3x UTC:** Lab 8 is complete, write-up included. Lab 9
is the last official lab, due Wed 2026-11-04. It is submitted as soon as possible **on Lab 8's
path, with no Mercury improvements first**. Every gap found on the way is registered as a finding
for after submission, when priorities are reset. The work runs in the order below, one step at a
time, and the operator is told as each step completes. Every decision is the operator's, asked
with the agent's recommendation and recorded in the decisions table.

**One exception, allowed by the operator (2026-10-22 ~05:1x UTC):** if the only blocker to real
switch ZTP is Mercury's `cisco_ios` bootstrap (`no switchport` on an SVI; a default `ip route`
that needs `ip routing`, where a switch wants `ip default-gateway`), that one minimal fix is built
and gated before the first pass, since the handout requires the switch via ZTP.

This plan supersedes `docs/LAB8_LAB9_PLAN.md` section 3 for Lab 9: Day 1 approval up front is not
built for this lab, and the narration says it is still planned. That document's section 4
(addressing), section 5 (the switch's default and fallback) and section 8 (capacity) stand, and
this plan cites them.

**The handout's objectives** (docs/LAB_REQUIREMENTS.md, Labs 8 and 9): add R8 and a "Switch"
through the same ZTP framework, with the full framework involved (ZTP, monitoring,
visualization, DevOps testing, documentation). The video covers:
- what happens when the devices are added;
- a general overview of unit testing and code coverage;
- examples of the tools being used and tested;
- examples of the documentation.

The topology is R8 behind R2 in OSPF area 20, and a switch (s5) behind R8 with H6 and H7 on VLAN 10.
The handout's diagram labels the second host H1; it is H7 here (LAB_REQUIREMENTS).

## Decisions

| # | Decision | Recommendation | Status |
|---|---|---|---|
| D1 | Commit tonight's uncommitted records and this plan as one docs commit through the gate | yes: records, not Mercury improvements | **yes** (the operator, 2026-10-22); `2a7ed0d4` |
| D2 | The switch ZTP test | a throwaway lab with a C8000v relay and a configless vIOS-L2 | **approved, restructured by the operator:** no throwaway. The vIOS configless launch patch and its test are written (lab tooling); s5 goes into the Lab 9 redeploy configless under the patch, on its own CPU; the test is the real R8 and s5 in an unrecorded first pass, with P-S1 to P-S7 and the s3 stop rule. Fallback: the minimal configuration typed on s5's console, onboarded by DHCP, no second redeploy, the video saying why |
| D3 | When to run | 06:30 to 08:15 UTC | **the operator:** no fixed window; step by step as each piece is ready, never in 08:30 to 09:10 UTC. Add device and Verify are the operator's |
| D4 | Build the `cisco_ios` bootstrap fix (section 2) before the first pass | yes (section 2) | **yes, both parts, with tests and controls; gated after run 1059 is green, deployed before the first pass** (the operator, 2026-10-22) |
| D5 | s5's unused Gi0/0 | — | **the operator:** s5's Day 1 shuts Gi0/0 (Mercury reaches s5 on VLAN 1 through R8), its dangerous-line reason written into the Day 1 prep in advance, as for R6's Gi1. The first pass records where s5's DISCOVER actually went (P-S2) |
| D6 | s5's CPU (section 3) | s5 on CPU 19 alone; routers and hosts on 0 to 18; switches on 19 to 23 | **yes** (the operator, 2026-10-22). After the redeploy, one measured hour with the tuning checks (OSPF drops, failed scrapes, clock rates, s5's included) before the first pass: the go or no-go and the baseline. NUMA stays deferred unless the first pass is unreliable |

## 0. Tonight's queue: C1522 and R7's heartbeat rule (done)

- [x] **Push C1522:** `c895821c`, 04:44 UTC. Its CI run 1057 went red: the new module guard
  caught three tests leaving `app-pushed` and `remote-publication`, written by threads ending
  after their tests on CI's slower runners. Fixed forward in `a1af8eba` (the store redirect
  joins the late writers its test started); run 1059 **green** (05:20 UTC). The docs commit
  `2a7ed0d4`'s run 1058 failed on the same family.
- [x] **R7's heartbeat rule:** the operator's re-measure wrote r7 only at 05:02:37Z (750 s
  measured, replacing the provisional 1,382 s). The install step passed 8 of 8 at 05:04 UTC,
  with Grafana running all 10 heartbeat rules and `nmas-hb-r7` among them. The check at
  05:05 UTC reads `current r7: window 750 s inside (601, 899)`. Its exit stays a failure for
  s3 alone (INSEPARABLE, C1318).
- Deferred unless Lab 9 needs them: B to E (C1521), the findings reconciliation, C1513.

## 1. The vIOS configless launch patch and its test (done: `44738eff`)

- [x] `docs/bootstrap-probe/patches/patch-vios-configless.py`, lab tooling only. It makes three
  anchored edits to vrnetlab's vIOS launcher (`vrnetlab/cisco_vios:L2-20180619`, sha256
  794788bc..., read from s1's container, nothing bound over it there):
  1. a startup file refused;
  2. nothing typed on the console at the dialog, "Press RETURN" or a prompt, the VM marked
     running and the console released (for the fallback);
  3. the 300-spin watchdog never restarts the VM.
- What the reading found, correcting C1349's note: with no startup file the stock launcher does
  NOT stop. "Failed to find startup configuration file" is a log line, and the launcher still
  answers the dialog with `no` and presses RETURN three times, which on classic IOS can end
  AutoInstall.
- The image carries only its base disk (the overlay is made at first start), so the C8000v's
  disk edit is not needed. Management passthrough is the base class's `CLAB_MGMT_PASSTHROUGH`,
  set in the lab file. containerlab writes no startup file for a node naming none (r6's config
  folder is empty).
- [x] `tests/test_vios_configless_patch.py`, 17 tests against the hash-pinned real launcher,
  structurally and by RUNNING the patched `bootstrap_spin` against a stub console. Shown able to
  fail: without the console edit, 5 aimed tests fail; without the watchdog edit, 3.
- [x] Committed through the gate with step 2 as `44738eff` (2026-10-22 05:28 UTC; CI run 1060).

## 2. The `cisco_ios` bootstrap fix (built: `44738eff`; deploy is the run sheet's A1)

**Built 2026-10-22 ~05:1x UTC (D4):** `bootstrap_config.manager_interface_lines`.
- It writes `no switchport` only when the manager interface is not a `Vlan` SVI.
- For a layer-2 platform with a gateway, it writes `ip default-gateway <gw>` beside the default
  route.
- The stale comment is gone, and the device-name inventory lowered from 4 to 3 lines (it named
  s3).

Three tests went into `tests/test_bootstrap_manager_address.py`:
- an SVI (`Vlan1` and `Vl1`) gets no `no switchport` and keeps its address and `no shutdown`;
- a switch with a gateway gets both lines, a router the route only;
- a switch with no gateway gets neither.

Each control fails exactly its test: `no switchport` put back on SVIs, and the default gateway
removed (made on copies, restored). Every other test that renders or pins a bootstrap passes
(773).

**Gi0/0 (D5): nothing in the bootstrap or Verify depends on it.**
- The bootstrap writes the platform's own management port only when one is named in Add device,
  or when the device's NetBox record marks exactly one interface management-only
  (`device_environment.read`). s1, of the same IOSv-L2 type, has none; Mercury's token cannot
  read the type's interface templates (403). So step 5 checks s5's Planned record, and Add
  device's plan shows it ("management-only interfaces none" for R6).
- Verify reaches s5 at its VLAN 1 address.
- The monitoring profile's source interfaces are `Loopback0` (the network's
  `syslog_source_interface`), never Gi0/0.

**Sizing, as read before the build** (from `modules/nsot/bootstrap_config.py`:
`manager_interface_lines`, `render_bootstrap`):

Read from `modules/nsot/bootstrap_config.py` (`manager_interface_lines`, `render_bootstrap`):
- **The SVI problem is real.** On a layer-2 platform the manager-facing stanza is
  `interface <name>` / ` no switchport` / the address / ` no shutdown`. Under `interface Vlan1`,
  `no switchport` is an invalid line. On a fetched configuration IOS refuses that one line and
  applies the rest, so the switch is likely still reachable. But the file Mercury served would
  hold a line the device refused, and the function's own comment still says the shape is
  unmeasured and that `cisco_ios` is blocked (it has not been since stage D).
- **The gateway is probably not a blocker.** The generator writes `ip route 0.0.0.0 0.0.0.0
  <gw>`. s1 runs RIP on SVIs, and its golden carries no `ip routing` line; IOS shows that line
  only when it is not the default. So this image routes by default and the route works. P-S5
  measures it. `ip default-gateway <gw>` beside it costs one line, is ignored while routing is
  on, and is used if it is off.
- **The fix:**
  - `no switchport` is written only when the manager interface is not a `Vlan` SVI (about 3
    lines, and the stale comment corrected);
  - for `cisco_ios`, `ip default-gateway <gw>` is written beside the default route (about 2
    lines).
- **Its tests** go in `tests/test_bootstrap_manager_address.py`:
  - a `Vlan1` manager interface renders no `no switchport` and keeps its address and
    `no shutdown`;
  - a routed port keeps `no switchport` (the existing test stays);
  - with a gateway, `cisco_ios` renders both lines and `cisco_iosxe` only the route.

  About 3 tests and 40 lines, each shown able to fail. The other tests that render a bootstrap
  are run to see that nothing else pins the old text.
- **The cost:** about 30 minutes of work and a gate of about 25 minutes. It can be built, gated
  and deployed before the first pass, which needs steps 3 to 5 first anyway.

## 3. s5's CPU placement (decided: D6)

**What was read:**
- **2026-10-21's per-CPU reading** (HOST_TUNING.md, Phase 2): the routers' and hosts' CPUs 0
  to 19 at 66 to 77% busy each (14.5 CPUs' worth on average, 15.8 in the busiest minute, every
  CPU reaching 100% in some minute); the switches' CPUs 20 to 23 at 84 to 94%; no steal.
- **Re-read 2026-10-22 05:20 UTC** (`docker stats`, read-only): **r8 already runs**, configless,
  at 1.61 CPUs, because a C8000v's data plane polls whether or not it is configured. r5 runs at
  1.70. The eight routers total about 14.4 CPUs, the switches 0.83 to 0.95 each, the hosts
  about 0. The load average is 20.9 on 24.
- **So Lab 9 adds only s5** (a vIOS-L2 takes 0.76 to 0.96 of a CPU; s1 and s2 read 0.83 now)
  and H6 and H7 (about none). The routers' demand does not change. Phase 3's 2 × 12 layout is
  deferred (HOST_TUNING.md: after the recording, as an efficiency change), so the layout stays
  as it is.

**Recommended:** s5 on CPU 19, a CPU of its own, with the routers and hosts on 0 to 18 and the
switches on 19 to 23.
- **The routers:** about 14.4 CPUs of demand on 19 instead of 20, 76% on average instead of
  72%, about 83% in the busiest minute. More waits at peaks (a redeploy's boot storm, a Save
  All, a capture) are expected, not steady overload.
- **s5:** like s1, s2 and s4, about 0.85 of a CPU alone. Its clock should run as theirs do, so
  its heartbeat window can be measured rather than INSEPARABLE.
- **Measured after the redeploy:** the E checks and the stall script, as for Phase 2: each
  switch's gap rate, and the routers' OSPF drops against their CPUs' pressure. If the routers'
  drops return, the next lever is Phase 3's binding (more lab-VM vCPUs are ruled out).

**Not recommended:**
- **s5 sharing a switch's CPU.** Each switch already takes 83 to 95% of its own; two on one CPU
  is about 1.7 of demand on 1.0, and both clocks slow (C1318's mechanism). Shared with s3, it
  would put the fleet's management path at risk.
- **s5 in the routers' pool.** Its clock would follow the routers' load, as s3's did before
  Phase 2.

**What it changes** (step 4):
- the lab file: `cpu-set: "19"` for s5, `"0-18"` for the `cisco_c8000v` and `linux` kinds;
- `lab/pinning/pinning.conf`: `SWITCHES` gains `s5:19`, `SWITCH_SET=19-23`,
  `OTHERS_SET=0-18`, and `OTHERS` gains h6 and h7;
- `check-pinning.sh` reads PINNING HOLDS after the redeploy.

- [x] The operator's decision (D6): yes.

## 4. The one-file lab change and the redeploy (the run sheet)

**What was read first (2026-10-22 ~05:1x to 05:2x UTC, read-only):**
- **The lab file is unchanged since `33916b7`** (sha256 `c23c5d40…`), and the lab repository's
  newest commit is a startup sync (`da1c954`).
- **R6 and R7 are still configless** in it (`patches/c8000v-launch-configless.py`, `wait-for`
  stages). **Phase 3's option (b) was never applied**, so a redeploy as the file stands would
  bring R6 and R7 back blank and undo Lab 8.
- **Option (b)'s map change was never made either.** The startup sync's map
  (`data/lab_targets/Default.tsv` on `<nmas-host>`) still has r6 in the old separate lab
  (`labs/r6/configs r6`), and has no r7 and no r8.
- **The file already plans s5's links in a comment** (R8 Gi3 to s5 Gi0, the hosts on s5's Gi1
  and Gi2, with pinned MACs). The switches' kind sets `CLAB_MGMT_PASSTHROUGH: "false"` (needed
  for the existing switches' `ip address dhcp`), so s5 overrides it.
- **`host-net-lab89.sh` (H5, and H6 and H7 next) gets its lease with `udhcpc -n -q`,** which quits
  once it has a lease and never renews.
- **R8 already runs configless,** and keeps doing so: the first pass reloads it after its Add
  device, as Lab 8 did R6.

**The lab repository's changes, prepared and dry-run on the lab host (nothing written):**
- **Option (b)**, as prepared on 2026-10-21 (HOST_TUNING.md Phase 3 section 4):
  `lab/phase3/c8000v-launch-startup-only.diff` and `lab/phase3/option-b-labfile.diff`. R6 and R7
  boot from their goldens, with no stages.
- **`lab/lab9/patch-lab9.py`** (anchored, refuses a file that differs, the lab file re-parsed as
  YAML). Its diff was read on the lab host:
  1. the routers' and hosts' CPU set goes from 0-19 to 0-18 (D6);
  2. R8's `wait-for` stage goes (C1475), leaving the file with no stage;
  3. s5 becomes configless on CPU 19 under `patches/vios-launch-configless.py`, with
     `CLAB_MGMT_PASSTHROUGH: "true"`;
  4. H6 and H7 are added (management addresses .36 and .37);
  5. the three links: R8 Gi3 to s5 Gi0 (CLI Gi0/1); s5 Gi1 and Gi2 to H6 and H7;
  6. `host-net-lab89.sh` starts a client that stays (`udhcpc -b -t 0 -T 3 -A 5`) once the first
     lease is in, so leases renew.
- **`lab/pinning/pinning.conf`:** `SWITCHES` gains `s5:19`, `SWITCH_SET=19-23`,
  `OTHERS_SET=0-18`, and `OTHERS` gains h6 and h7.

**The window and its bound.**
- The window covers the ten devices Mercury holds: r1 to r4, r6, r7 and s1 to s4 (r5 is
  unmapped; r8 and s5 are not onboarded).
- The measured redeploy was 23.8 min for nine nodes (lab/REDEPLOY.md). Thirteen network nodes
  boot this time, all at once (no stages), so about 35 min is expected. The window is **90 min**,
  about 2.5 times that; the time it actually takes is recorded here.
- **Start condition:** 08:30 UTC is more than 105 min away (90 plus the 15-minute slack), or it
  is after 09:10 UTC. The measured hour (step E) also stays outside 08:30 to 09:10.
- **The operator's timing (2026-10-22 ~05:3x UTC, approving the run sheet):** A and B that
  night, with the operator up; C onward the next day when the operator is awake, since D2 and
  D3 are the operator's inside the window and the measured hour precedes the first pass anyway.
- **Changed by the operator at ~05:5x UTC: continuing tonight.** The lab repository is pushed
  off-host to the NMAS host (`backups/lab.git`, `8d25fe6`; C1514's precondition met), and that
  night's vzdump job is disabled, so 08:30 to 09:10 UTC is free that night only (re-enabled the
  next day with C1514's schedule). No deploy after A1 until the first pass is done.

### The run sheet

**A. Mercury and the NMAS host, before anything restarts**

| # | Who | Step | PASS |
|---|---|---|---|
| A1 | agent | The bootstrap fix deployed: `nmas-deploy --wait` on `<nmas-host>` once the steps 1 and 2 commit's CI is green | it names CI's pass and the commit; Settings › About shows that sha. **PASS 05:49 UTC:** the first try (05:39) refused correctly, since the operator's Save All held six devices; then "deployed 9af8c3d406 -> 9b28607432 … running 9b28607432 since 05:49:10 UTC. CI passed for 9b28607432: run #1061". `9b286074` carries `44738eff`'s fix |
| A2 | operator | The startup sync's map, `<home>/python/Agentic_NMAS/data/lab_targets/Default.tsv` on `<nmas-host>`: r6's line becomes `r6 labs/lab/configs default <user>@<lab-host> cisco_iosxe`; add the same line for r7; add `# DECLARED-UNMAPPED r8 default configless until its ZTP in Lab 9` and the same for s5. The file is tab-separated: written with `sed` and `printf`, shown before and after with `cat -A` | **PASS 2026-10-22 05:35 UTC:** read back with tabs throughout, mode 600, the dated backup kept; the sync's own parser (`clab-targets --list Default --group`, exit 0) reads one group, `labs/lab/configs: r1 r2 r3 r4 r6 r7 s1 s2 s3 s4`, and r6 and r7 resolve to `labs/lab/configs default` |
| A3 | operator (DECISION) | **Save All** (Devices › Actions › Save All), with nothing else running. A single failure: that device's Save alone, once, then Save All again (C1520) | "10 of 10 saved", and a new `baseline/<ts>` holding r6 and r7. **PASS (the operator):** 10 of 10, `baseline/20261022T054021Z`, every golden already matching |
| A4 | agent | The startup sync that baseline starts: the lab repository's newest commit, and `configs/r6.cfg` and `configs/r7.cfg` present (if the sync ran before A2, `sudo systemctl start clab-sync.service` on `<nmas-host>` once) | a `startup from baseline/<ts>` commit naming r6 and r7; both files present, owner-only (C1453). **PASS:** the sync at 05:39:27 committed `9db387a` "startup from baseline/20261022T010828Z: r6 r7", both files mode 600. The run at 05:40:42 for `baseline/20261022T054021Z` found all ten unchanged ("The lab already holds baseline/20261022T054021Z; nothing to update"). It also named an unmapped file, `tw-ztp-a`, in its staging folder (it does not block; registered) |
| A5 | operator | The break-glass export (Credentials › break-glass export), kept offline | the file saved; Needs attention has no "break-glass record is out of date" row. **PASS (the operator):** exported 05:41:16Z, downloaded intact, the record current |

**B. The lab repository on `<lab-host>`**

| # | Who | Step | PASS |
|---|---|---|---|
| B1 | agent | The vIOS configless launcher: `docker exec clab-rcn-lab1-s1 cat /launch.py > ~/labs/lab/patches/vios-launch-configless.py`, then `python3 patch-vios-configless.py ~/labs/lab/patches/vios-launch-configless.py --write` (the patcher copied from the deployed checkout) | the copy's sha256 before the patch is `794788bc…`; "written:"; `python3 -m py_compile` passes. **PASS 05:42 UTC:** before `794788bc…`, three `CONFIGLESS (C1349)` marks, compiles, after `f654898c…`, byte-identical to the tested patcher's output from the pinned fixture |
| B2 | operator | Option (b): `git apply --check`, then `git apply`, for `c8000v-launch-startup-only.diff` and then `option-b-labfile.diff` (copied from the deployed checkout's `lab/phase3/`) | each `--check` silent with exit 0; `grep -c 'NMAS_STARTUP_ONLY: "true"' rcn-lab1.clab.yml` reads 2 (r6's and r7's env lines; a bare `grep -c NMAS_STARTUP_ONLY` reads 3, the option (b) comment included). **PASS 2026-10-22 (the operator):** both applied; `git diff --stat` patches/c8000v-launch.py +9, rcn-lab1.clab.yml +11/-10; the three occurrences are the comment and r6's and r7's env lines |
| B3 | agent | Lab 9's change: `python3 patch-lab9.py ~/labs/lab` (copied from the pushed commit `9b286074`: the deployed checkout may predate it), read the diff, then `--write` | the diff matches the dry run above; "written:" for both files. **PASS 05:46 UTC:** the diff was the dry run's, offset by option (b); no stage left; two `NMAS_STARTUP_ONLY: "true"` lines; the lab file parses with 22 nodes (21 containers and br-mgmt) and 24 links; s5 on CPU 19 with passthrough and the patched launcher; `host-net-lab89.sh` passes `sh -n` |
| B4 | operator | One lab-repository commit: `git add rcn-lab1.clab.yml configs/host-net-lab89.sh patches/c8000v-launch.py patches/vios-launch-configless.py && git commit -m "lab: Lab 9 - s5, h6, h7 and their links; r6 and r7 from their goldens (option b); CPU sets 0-18 and 19-23; no stages; renewing DHCP"` | `git status --short` lists none of the four |

**C. The redeploy (only when the start condition holds)**

| # | Who | Step | PASS |
|---|---|---|---|
| C1 | agent | The window, on `<nmas-host>` as `<user>`: `nmas-planned-restart Default r1 r2 r3 r4 r6 r7 s1 s2 s3 s4 --minutes 90 --new-host-keys --why "lab redeploy: Lab 9 - s5, h6, h7; r6 and r7 from their goldens" --by <operator>` | exit 0 and its three lines ("recorded: …", "window recorded <recorded_at> …", "expecting new SSH host keys …"); `<recorded_at>` kept. **PASS 05:54:26Z** (id `f23a1123ef631268`, until 07:24:26Z plus 15 min; Grafana's alerts on the ten silenced until 07:43:26Z). The `--why` reads "r6 and r7 boot from their saved configurations", because the read-only hook refuses a host command containing "golden" |
| C2 | agent | At once, on `<lab-host>`: `cd ~/labs/lab && containerlab deploy -t rcn-lab1.clab.yml --reconfigure`. Never `restart` or `start` a node (C1372). A capture runs in s5's own namespace from its creation (UDP 67 and 68, on Gi0 and on eth0) | exit 0; 21 `clab-rcn-lab1-*` containers Up (r1 to r8, s1 to s5, h1 to h7, web). **First run 05:54:44 (exit 0): 20 up, s5 "Exited (1)":** the patched launcher refused containerlab's default startup file for the vIOS kind (C1534, closed the same turn). The patch was corrected to name the file and never apply it, regenerated on the lab host (`6d1f16e0…`), and C2 re-run inside the same window. **PASS 05:56:59:** exit 0, 21 up; s5's log "CONFIGLESS: /config/startup-config.cfg exists (containerlab's default for this kind); it is never applied" and "the console is left to AutoInstall"; its capture running from 05:56:56 (`lab9-s5-dhcp-2.pcap` on `<lab-host>`). The corrected launcher is a lab-repository change after `8d25fe6`, for the operator's next lab commit |
| C3 | agent (sudo) | The pinning: `sudo bash install.sh` from a copy of `lab/pinning` (its `pinning.conf` as above) | "PINNING HOLDS": s5's qemu and kvm-pit thread on 19, the other switches on 20 to 23, every router and host on 0-18. **PASS ~05:58 UTC:** PINNING HOLDS; s5's kvm-pit on 19, s1 to s4's on 20 to 23; every router and host within 0-18, applied by its container |

If the attempt stops before C2 runs, end the window at once (lab/REDEPLOY.md): `nmas-planned-restart Default --end <recorded_at> --why "<what stopped it>" --by <operator>`.

**D. Within the window**

| # | Who | Step | PASS |
|---|---|---|---|
| D1 | agent | The ten devices answer (the Devices page, read through Mercury); the time from C2 recorded | all ten answering; the redeploy's duration written here |
| D2 | operator | Settings › Installation › Diagnostics › Drift checks › **Check now** for Default | History (`/v2/history?kind=hostkeys`): one "SSH host key kept under a planned window" row per device |
| D3 | operator | Needs attention: the one "10 new host keys accepted during …" row, reviewed in History, then **Acknowledge** | no "restarted unexpectedly" or "different SSH host key" row for the ten |
| D4 | agent | R6 and R7 at their goldens (drift clean); OSPF and RIP neighbours as before the redeploy (Show commands, read-only); H5 holds 10.70.10.x and runs a renewing `udhcpc` (`docker exec clab-rcn-lab1-h5 ps`) | drift clean for both; neighbour counts unchanged; H5's lease and its renewing client present. **First read: r6 and r7 drifted (image defaults, C1538) and r7's Gi1 and Gi3 were shut (C1537), so H5 had no lease.** r7's Gi3 fixed by a deploy (the operator, 07:16:53Z, golden `8fa06bb2b0ba`; the first try at 07:08 stopped at pre_snapshot, nothing sent, C1540, C1513). **PASS 07:22 UTC:** drift run of Default, 10 of 10 clean (comment lines and r1 to r4's regenerated certificates only); r7's receipt reads RIP and RIPng neighbours 1 and 1 before and after; H5 leased 10.70.10.102 at 07:16:46Z after 340 tries, its renewing `udhcpc -i eth1.10 -b -t 0 -T 3 -A 5` running, IPv6 `2001:db8:70:10:a8bb:ccff:fe00:7005/64` by SLAAC; at 07:19:11Z web answered HTTP 200 over IPv4 (8.8.8.8, 203.0.113.1) and IPv6 (2001:4860:4860::8888, 2001:db8:203::2), the gateway and the IPv6 web address 0% loss |
| D5 | agent | s5: its container log's `CONFIGLESS:` lines and the console at the setup dialog (P-S1's first half); its DISCOVER in C2's capture, its client hardware address and client id recorded (P-S2's first half, and **the MAC Add device must use**: VLAN 1's SVI may send from the switch's base MAC, not the pinned port's); R8 Up and configless; H6 and H7 logging "still no IPv4 lease", as expected until R8 and s5 are built | each recorded here |

**E. The measured hour (D6's go or no-go, and the baseline)**
- One hour after D1, read with the tuning's checks (HOST_TUNING.md's closing hour): OSPF
  dead-timer drops, failed SNMP scrapes, gauge steps, and each switch's clock rate from its
  heartbeats.
- **s5's clock cannot be read before it is onboarded** (its heartbeat starts with Verify's
  profile). For s5 the hour reads CPU 19's use and steal, and its clock rate is read after the
  first pass.
- **Go** if the hour is no worse than the tuning's confirmation hour (0 OSPF drops, 0 failed
  scrapes); **no-go** otherwise, with the numbers, before the first pass.
- NUMA (Phase 3's binding) stays deferred unless the first pass is unreliable (D6).
- **Started 07:25:02Z, ends 08:25:02Z** (the operator moved it to after r7's fix). The read at
  the end: the tuning's stall script (C1485's measures, as in HOST_TUNING.md) over the hour, and a
  per-minute `/proc/stat` sampler on `<lab-host>` (`~/lab9-E-procstat.log`, 62 samples, each
  CPU's busy and steal, and s5's qemu CPU time; s5's qemu read on CPU 19 at the start).
- **Before E, for context (D1 to 07:25, 76 minutes, with the boot settling, the drift checks,
  r7's two deploys and the agent's reads in it):** 103 of 304 gauge steps below 10 (minimum 1),
  356 failed scrapes, 16 OSPF dead-timer drops (all r1's, toward s3 and s4), 14 missed-ping
  events on 8 devices, s3 Gi1/1 discards in 74 of 75 minutes (max 21.7/s), s3 heartbeat gaps
  509 to 716 s; SSH sign-in medians about three times their pre-redeploy values (C1513's note).
  The confirmation hour (10-21) read 0 steps, 0 scrapes, 0 drops.
- **E's integrity (the operator's question, 07:3x):** the lab VM (100, 24 vCPUs) and the NMAS VM
  (102, 4 vCPUs) have no CPU affinity: both float over all 40 threads of `<hypervisor>` (2
  sockets, 10 cores, 2 threads each), so they can share physical cores. During E the agent runs
  nothing on either VM but the sampler (one `grep` a minute); its gate's suite runs on the laptop
  and CI on GitHub. From 06:32 to 07:30 (Proxmox's per-minute history): the host 50 to 56% busy,
  the lab VM 80 to 85% of its vCPUs, NMAS 23 to 34% (peak 58%); steal inside the lab VM 0.02 to
  0.07% on every CPU. The go/no-go reads the same history for E's hour.
- **The 16 drops before E:** 12 r1 to s3, 3 r1 to s4, 1 OSPFv3 r1 to r2's router ID, all on r1's
  Gi2. sysstat's 10-minute busy: s3's CPU 22 at 94 to 98% (94 to 95% before the redeploy), the
  routers' CPUs 0 to 18 at 73 to 82% on average (70 to 75% before, on 0 to 19; r8 takes 1.7 CPUs),
  s5's CPU 19 at 64 to 67%. 10 of the 16 fell while Mercury was busy (r7's capture, plan, deploys
  and reads, 06:57 to 07:10; a drift run, 07:21 to 07:22).

## 5. Mercury prep for R8 (on Lab 8's path)

- [ ] R2's relay toward R8 as an ordinary intent change. Whether R2, or the path to R3 and R4,
  needs `ip nat inside` (R4's Gi5 did for Lab 8's branch): which edge R8's traffic leaves by,
  and what that implies.
- [ ] NetBox: R8's site, VLAN group and VLAN 10 (10.80.10.0/24 and 2001:db8:80:10::/64), and
  the Planned records for R8 and s5. Each manual NetBox step registered as a finding.
- [ ] s5's Planned record holds no interface marked management-only (read before Add device).
- [ ] R8's and s5's Day 1 documents. s5's shuts Gi0/0 (D5), and its dangerous-line reason is
  written into the prep in advance, as R6's Gi1 was.
- [ ] Lab 8's lessons applied:
  - no stale NetBox addresses or cables before Add device (C1525, C1529);
  - dangerous-line reasons worked out in advance;
  - reloads off camera;
  - the whole-network import for the new site's cables (C1530).

## 6. The first pass (unrecorded): R8, then s5, measuring P-S1 to P-S7

**Read beforehand, from the code and earlier probes:**
- **Mercury's ZTP is platform-neutral at the DHCP and TFTP end.** A Kea reservation's option 67
  names `<host>.cfg`, and Mercury's responder serves only that file. Classic IOS AutoInstall also
  takes option 67 as its configuration file. Onboarding does not block `cisco_ios`.
- **s5's management belongs on VLAN 1's SVI.** Its uplink to R8 also carries VLAN 10 for H6
  and H7. Mercury reaches s5 for Verify over SSH to that address, routed by R8's connected /30
  in OSPF area 20 (R8's Day 1); s5 answers through its gateway, R8.
- **A configless vIOS once crashed in PnP Agent Discovery (SIGBUS)** on its first boot, seen
  only in its uptime (bootstrap-probe README).
- **Under passthrough, s5's Gi0/0 sits on the container's management network.** With no
  configuration it is a VLAN 1 switchport like the rest, so VLAN 1 reaches that network too
  until Day 1 configures Gi0/0. P-S2 reads where the DISCOVER goes.

**The s3 stop rule:** s3's gap rate is read before and during the pass. The pass stops if it
passes its measured ceiling (the relay probe's rule).

| # | Prediction | Measured by |
|---|---|---|
| P-S1 | The patched launcher boots s5 with no configuration and leaves its console untouched | the container log (`CONFIGLESS:` lines), the console at the setup dialog |
| P-S2 | AutoInstall sends DHCP DISCOVER on VLAN 1, out the port facing R8 | a capture on the lab host's link to R8 and on the management network (Gi0/0, a VLAN 1 port until Day 1 shuts it); the DISCOVER's client id and MAC; **recorded here: where it actually went** |
| P-S3 | Kea answers through R8's relay by giaddr, and s5 leases its reserved address | Kea's lease; Mercury's pending page |
| P-S4 | s5 fetches the file option 67 names (`s5.cfg`), not `network-confg` first | the responder's RRQ log |
| P-S5 | The bootstrap applies on VLAN 1, and the default route works (`ip routing` on) | Verify's first golden; `show ip route` and `show ip interface brief` through Mercury |
| P-S6 | Verify reaches s5 over SSH through R8 and promotes it | Verify's result |
| P-S7 | PnP discovery does not crash it | uptime before Verify |

**If s5 has stopped asking before R8's relay exists** (the operator, 2026-10-22). The order is
the redeploy, then R2's relay, then R8's ZTP, then R8's Day 1, so s5's first-boot AutoInstall may
give up long before anything answers it. If P-S2's capture shows s5 no longer asking, **reload
s5 right after its Add device, off camera, like R7's c5a in Lab 8.** s5 is pending, so no
planned-restart window is needed.
- **Its console**, on `<lab-host>`: `docker exec -it clab-rcn-lab1-s5 telnet 127.0.0.1 5000` (the
  patched launcher releases it).
- **The rule:** anything typed before `reload` concerns only the boot being thrown away, so any
  answer there is safe. Only two things can end the NEXT boot's AutoInstall: `yes` at Save
  (it writes a startup configuration), and anything typed after the reload starts.
- **What classic IOS shows, and what to type.** Not every screen appears, and they come in any
  order. The exact strings are read from s5's container log at the redeploy (P-S1); a screen not
  listed here means stop and tell the agent.

  | The screen shows | Type |
  |---|---|
  | `Would you like to enter the initial configuration dialog? [yes/no]:` | `no`, Enter |
  | `Would you like to terminate autoinstall? [yes]:` | Enter (it ends this boot's attempt only) |
  | `Press RETURN to get started!` | Enter |
  | `Switch>` (or another name, if a partial configuration landed) | `enable`, Enter. A configless switch has no enable password: a `Password:` prompt means stop |
  | `Switch#` | `reload`, Enter |
  | `System configuration has been modified. Save? [yes/no]:` | **`no`**, Enter. `yes` writes a startup configuration, and the switch never AutoInstalls again |
  | `Proceed with reload? [confirm]` | Enter |
  | the switch starts rebooting | **Ctrl+]**, then `quit` at `telnet>`. Nothing more is typed on s5's console until Verify |
- **Then:** the agent watches the capture for the new DISCOVER and the pending page for leased
  and fetched. If nothing arrives within 20 minutes, one second reload as above, recorded as a
  finding (as Lab 8's c5a allowed).

**If s5 cannot AutoInstall:** the operator types the minimal configuration on s5's console (a
user, and VLAN 1's SVI on DHCP). It is onboarded by DHCP through R8's relay, with no second
redeploy, and the video says why the switch is not zero-touch. The typed configuration is
LABOUR, a row in docs/MANUAL_STEPS.md and a finding.

## 7. Run sheet, shot list and the testing segment

**r6 and r7: the reseed and the clearing deploys (the operator, 2026-10-22 ~07:5x UTC).** Seed
intent cannot do it: it is offered only for absent or bootstrap-only intent, and it parses the
golden, which never prints `no shutdown`, so it would drop the `no_shutdown: true` that fixed r7's
Gi3. The agent prepares the documents with `lab/lab9/reseed_prepare.py` (the Intent editor's own
read and preview; writes nothing): each committed intent with only its `lines:` block replaced
by the blocks its golden holds (`vty 0`, `vty 1` with `length 0`, `vty 2 4`) and
`exec-timeout 15 0` on `con 0` (C1543, C1544).

| # | When | Who | Step | PASS |
|---|---|---|---|---|
| R1 | after E, no device touched | agent | `reseed_prepare.py r6 r7` on `<nmas-host>` | for each: the text diff touches only `lines:`; "no_shutdown declared … KEPT" (r7's list includes GigabitEthernet3); the preview ok; `vs_device` written here |
| R2 | after R1 | operator (DECISION) | each device's Intent editor: paste the printed `lines:` block over the old one, review the editor's two diffs against R1's, commit | the editor's diff shows only the vty split and the console timeout; every `no_shutdown` kept; one commit per device |
| R3 | after O9's deploy, before the recording | operator (DECISION) | r7: Plan a deploy, confirm, apply | the program as R1's `vs_device` predicted (written from the actual preview after R2); verify reads back every line; the receipt clean (`checks.ok` true, saved); Needs attention has no r7 deploy row (C1542 clears by its rule: the device's newest receipt succeeds) |
| R4 | with R3 | operator (DECISION) | r6: the same | as R3, without the C1542 row |

- [ ] The run sheet for the recorded run: no CLI on camera, and a dry look at every deploy's
  preview before the recorded one.
- [ ] The shot list.
- [ ] The testing segment the handout requires:
  - unit testing and code coverage, in overview;
  - the tools being used and tested: a CI run with its shards, the coverage ratchet, mutation
    testing, and a test that caught a real defect.

  This morning's CI run 1057 is a candidate: the C1522 guard caught three real leakers.
- [ ] The narration says that Day 1 approval up front is still planned (the Lab 8 video promised
  it for Lab 9).

## 8. Out-of-band ZTP for legacy devices (the second exception)

**The operator, 2026-10-22 ~06:2x UTC:** s5 gets no human interaction anywhere. Code solving it
is fine, but it must be a general Mercury feature, "out-of-band ZTP for legacy devices", not an
s5 or containerlab script. It is the second approved exception to the no-improvements rule.
R8's first pass goes ahead without it; this is built in parallel, and s5's first pass uses it.
Phase later (more console-server types and profiles, a full bootstrap over the console) is
C1536.

**Checked before building (read-only):**
- **Mercury reaching s5's console. The architecture's "the lab host is a raw-TCP console server
  via SSH jump" does NOT hold for s5.** Management passthrough redirects all traffic to s5's
  container management address into the VM (`mirred … to device tap0`), so `172.20.20.25:5000`
  does not answer from the lab host. qemu's console listens only inside s5's container
  (`*:5000`). A node without passthrough (s1) does answer at `172.20.20.21:5000`: the probe
  connected and closed, sending nothing. The lab host allows SSH TCP forwarding
  (`allowtcpforwarding yes`, `permitopen any`).
- **NetBox's console model: Mercury's token is refused (403)** on console ports, console-server
  ports and their templates (C1535, B). Cables and custom fields answer.
- **R8's Day 1 and the relay:** R8's Day 1 document is not written yet (step 5). It will hold
  Gi3 `10.255.4.13/30` with `ip helper-address 10.255.0.10`, the /30 in OSPF area 20, and
  Gi3.10 (VLAN 10, `10.80.10.1/24`, with its helper) for H6 and H7.

**The architecture, refined (the operator's seven pieces; changes in bold):**
1. **Source of truth: NetBox's console model** (console-server device, its port, the cable to
   the device's console port), read and created by Mercury once C1535's grant is in.
   **Per-port connection detail lives in Mercury's own console-server store, keyed by NetBox's
   console-server port id,** not in a NetBox custom field: creating a custom field is NetBox
   admin work, and the credential reference must never sit in NetBox anyway.
2. **Transport drivers behind one interface: three, not two:**
   - raw TCP or telnet, optionally through an SSH jump (direct-tcpip);
   - an SSH console server addressing a port by username (`user:port`);
   - **an SSH console server addressing a port by a per-port command whose stdin and stdout are
     the console** (Opengear's `pmshell` works this way).

   The lab host is the third, configured with `docker exec -i <container> …` bridging to
   `127.0.0.1:5000`: configuration, not code. Console-server credentials are in Mercury's
   credential store (the operator types them).
3. **Platform console profiles** as versioned, approved data (prompt states, factory-blank checks,
   kick-start templates), approved like templates. `cisco_ios` switch and router ship first.
4. **Addressing:**
   - **DHCP:** a read-only console survey learns the MAC and confirms the device is blank
     BEFORE Add device, so the plan and its hash hold the MAC as they do today ("what is
     confirmed is what is sent"). The kick-start then types the DHCP lines; the lease comes
     through the relay; the bootstrap is fetched from Mercury's gated TFTP.
   - **Static:** the planned address from NetBox IPAM. **The TFTP responder's gate gains a
     pending device's planned static address,** since it serves only what a reservation names
     today.

   The one-time credential never crosses the console: it is only in the fetched bootstrap.
5. **Trigger:** Add device offers console kick-start only when NetBox shows a console path,
   either at once or as the automatic fallback after N minutes without the device's own DHCP.
   The kick-start's exact lines are in the reviewed plan and its hash.
6. **Safety:**
   - refuse a non-blank device;
   - abort to Needs attention on any unexpected prompt, a password prompt included;
   - one session per console port, locked across processes;
   - bounded timeouts;
   - a masked transcript and receipt in History.
7. **Tests:**
   - the state machine against s5's real captured boot text and a router fixture;
   - every driver against a fake console server (0 bytes written outside the plan);
   - refuse-if-configured, the unexpected-prompt abort, masked transcripts, NetBox gating and
     the fallback timer;
   - the coverage ratchet holds, and CI is green before the deploy.

**Build order and rough size** (code plus tests; about 3 to 4 working days with gates):

| # | Piece | Size |
|---|---|---|
| O1 | Profiles (data, approval) and the session state machine, tested against s5's real boot text | ~500 lines + ~400 tests |
| O2 | The three drivers, each against a fake console server (bytes written counted) | ~400 + ~300 |
| O3 | The survey (blank check, MAC) and the kick-start's line rendering | ~250 + ~200 |
| O4 | NetBox console path: read, and create behind a declared write authority; Mercury's console-server store; credential references | ~400 + ~300; needs C1535's grant |
| O5 | The TFTP responder's static-mode gate | ~100 + ~150 |
| O6 | The operations: survey and kick-start with preview and confirm, operation stages, route gates, invalidation, receipts, masked transcript, Needs attention aborts | ~600 + ~500 |
| O7 | Add device's offer and the fallback timer (a job) | ~300 + ~250 |
| O8 | The interface: Add device's additions and a Console servers page (boards first), the manual's pages and diagrams | ~400 + docs |
| O9 | Gates, CI, one deploy after R8's first pass (no deploy until then) | — |

**Added by the operator (2026-10-22 ~07:5x UTC):**
- **O0, rides O9's one deploy:** C1541's read-back fix. `verify_scope.read_back` expands a
  `line` range into its members and matches each in whichever stanza the device prints it,
  tested on r7's real capture. It ships whether or not r7's clearing deploy needs it (any device
  that splits a range reads back falsely today).
- **In O3 (the survey):** a signed-in prompt (`#`) found on the console is NOT factory-blank as
  found. It is recorded as such, and the operation never proceeds silently from it (s5 was left
  at `Switch#` on 2026-10-22).
- **In O3 (the kick-start's lines):** the bootstrap delivered to a console-provisioned device
  sets a finite `exec-timeout` on `line con 0` (C1544's class).

**The operator's go, with a cut (2026-10-22 ~06:3x UTC).** The refinements above are accepted.
- **Lab 9's scope:**
  - O1;
  - O2 with two drivers, the command bridge and raw TCP via an SSH jump;
  - O3, O4 and O6;
  - O7's Add device offer only;
  - O8 minimal: a working page and a manual section, since documentation is a Lab 9
    deliverable;
  - O9.
- **Deferred to C1536:** O5 (static mode), the SSH port-by-username driver, the fallback timer,
  and O8's diagrams.

**The security addition (the operator):** the lab host's console access is a DEDICATED SSH key
with a forced command in `authorized_keys`. That command is a wrapper that only bridges stdin
and stdout to `127.0.0.1:5000` inside a container whose name is on an allowlist, and it rejects
anything else. Mercury's store holds only the container name per port: no free-form command is
stored or sent. Its tests: the wrapper rejects names not on the allowlist, and any injected
arguments.
- **Does it replace a stored secret? No.** The private half of that key still authenticates
  Mercury, so it stays a secret in Mercury's credential store.
- **What it changes:** the key's whole power becomes "bridge to an allowlisted console".
- **Recommended:** Mercury generates the key pair itself when the console server is set up. It
  keeps the private key encrypted, shows only the public key, and the operator installs that
  public key (`restrict,command="…" ssh-ed25519 …`). The operator then handles no secret, and
  none crosses the console.

**For s5's run:** s5 returns to factory state with no human typing. nvram's startup file is 0
bytes now, but PnP discovery was stopped by the diagnostic session, and s5's console sits at
`Switch#`. A reload from its own CLI, sent by the scripted session (in its planned window if
s5 is onboarded by then; it is not today), restarts it blank, and the kick-start's own
factory-blank check shows the 0 bytes again.

## Write-up: challenges (filled with evidence as each closes, not intent)

The operator, 2026-10-22: the Lab 9 write-up needs a "Challenges" section, and getting s5 to
boot blank past containerlab's default configuration is a required entry. Each entry records
what was seen. Excerpts carry no credentials, hashes or configurations. A fallback, when used,
is recorded as one, with its reason.

### 1. s5's configless boot (OPEN: out-of-band ZTP closes it at s5's first pass)

**The story, in the operator's order (2026-10-22):** the launcher patch, then containerlab's
default file, then PnP never asked (nvram 0 bytes, no DHCP in about 12 minutes; the diagnostic
session was a test touch), then out-of-band ZTP as a general bridge for legacy devices
(section 8).

**PnP never asked (evidence, 2026-10-22):**
- **nvram:** a scripted console session at 06:10:25 to 06:10:27 UTC sent RETURN, `enable` (no
  password asked) and `dir nvram:`, nothing more. It read `startup-config 0 bytes`,
  `private-config 0 bytes`, `udi 31 bytes`, `persistent-data 35 bytes` (262,144 total, 260,044
  free), so the image holds no startup configuration; the earlier indication was wrong. The
  session's planned erase was not sent.
- **PnP was running, and the touch stopped it.** The one-way reader recorded
  `%PNP-6-PNP_DISCOVERY_STOPPED: PnP Discovery stopped (Config Wizard)` after the session's
  input. The switch had been in PnP discovery, not idle.
- **No DHCP from s5 in about 12 untouched minutes** (05:58:02 to 06:10:25 UTC). Its capture held
  912 DHCP packets that were not H6's or H7's, and none was s5's own: R8's configless AutoInstall
  on Gi3 (`cisco-aabb.cc00.0418-Gi3`) flooding in from the R8 link, a router's emulator
  management port (`cisco-0c00.731d.df00-Gi1`), and a router's serial client id
  (`9S3JCNXDQQW`; s5's board id is `9MD0LDX81CK`).
- **P-S2 broke, by the operator's fixed rule:** no DISCOVER within 10 minutes of "Press RETURN".
  The operator's direction: no human at s5's console, so the fallback became a feature
  (section 8).

**The problem.** vrnetlab's vIOS launcher is built to configure a switch, so a blank switch
never gets to ask for its configuration:
- it answers the setup dialog (`no`) and presses RETURN three times at "Press RETURN to get
  started!", and on classic IOS console input can end AutoInstall;
- at the prompt it types its startup file through the console, then `write memory`;
- its watchdog stops and restarts a VM that stays quiet for 300 console reads.

**The change: `patches/vios-launch-configless.py`**, made from the image's stock launcher
(sha256 `794788bc…`) by `docs/bootstrap-probe/patches/patch-vios-configless.py`. It has three
anchored edits, refusing any launcher that differs:
1. a startup file is NAMED in the log and never applied. It was first refused, which stopped s5
   at the first redeploy, because containerlab writes a default startup file for the vIOS kind
   (C1534, closed);
2. nothing is typed at the dialog, "Press RETURN" or a prompt: the VM is marked running and the
   console released;
3. the watchdog never restarts the VM.

Lab repository: `8d25fe6` (first version), then `183aa5d` (the C1534 correction), both pushed to
the off-host remote.

**Its test:** `tests/test_vios_configless_patch.py`, 19 tests against the hash-pinned real
launcher. They check its structure, and RUN the patched console handling against a stub console
that records every keystroke, with and without containerlab's default file present. Shown able
to fail: without the console edit, 5 aimed tests fail; without the watchdog edit, 3.

**The switch bootstrap fix (D4):** Mercury's `cisco_ios` bootstrap no longer writes
`no switchport` under a VLAN SVI, and a switch given a gateway gets `ip default-gateway` beside
the default route. It has 3 tests, each control failing exactly its test. It was in `44738eff`
and deployed in `9b286074`.

**Evidence so far (2026-10-22):**
- **P-S1, held.** s5's launcher log, the second redeploy (05:56:56 UTC):
  `CONFIGLESS: /config/startup-config.cfg exists (containerlab's default for this kind); it is never applied`,
  then `CONFIGLESS: the console is left to AutoInstall`. The IOS banner and hardware lines
  follow (`Cisco IOS Software, vios_l2 Software (vios_l2-ADVENTERPRISEK9-M), Version
  15.2(CML_NIGHTLY_20180619)…`, `4 Gigabit Ethernet interfaces`,
  `256K bytes of non-volatile configuration memory.`). Then at 05:58:02:
  `CONFIGLESS: console state 1 after 0:01:05.454869 with no configuration; typing nothing, console released`.
- **What the console showed first: "Press RETURN to get started!", never the setup dialog.**
  The launcher logs every console chunk it does not match, and checks its prompts in order with
  the dialog first. The log of 119 lines holds no "System Configuration Dialog", no AutoInstall
  message, no `%SYS-5-CONFIG` and no configuration-load line, and the chunk it matched on held no
  dialog question (pattern 0 would have won). **s1 to s4, booted from fresh overlays of the same
  base image in the same redeploy, show the same:** each stock launcher met "Press RETURN" first
  ("Entering user EXEC mode"), with no dialog question. On classic IOS that suggests the base
  image already holds a startup configuration, and then AutoInstall does not start. A build that
  skips the dialog would look the same, so this is an **indication, not a measurement**.
- **P-S2, open: no DHCP request from s5 itself.** s5's capture (in its own namespace from
  05:56:56) held 812 packets by 06:03, all from H6 and H7 (`udhcp 1.31.1`, `aa:bb:cc:00:80:06`
  and `:07`). They come in on s5's host ports and are flooded out of every VLAN 1 port, the
  management port (eth0) and the R8 link (eth1) included: the exposure D5's Gi0/0 shutdown
  closes.
- **A one-way console reader** (`lab/lab9/console-reader.py`) has been attached since
  06:07:03Z, so anything s5 prints later is on record. It has no send call; a listener test on
  the lab host received 0 bytes from it while its stdin was flooded; it runs with stdin from
  `/dev/null`. Port 5000 had no client before it and one after. By 06:07 it had received only
  qemu's 12 bytes of telnet negotiation.

**The fallback rule, fixed by the operator (2026-10-22):** at the first pass's planned reload,
if no DHCP DISCOVER from s5 appears within 10 minutes of "Press RETURN", s5 gets the minimal
configuration typed on its console and is onboarded by DHCP. This entry then records that, and
why, including an image-held startup configuration if the evidence shows one.

**Still to record:**
- [ ] P-S2: the DISCOVER (client MAC and client id), or its absence within 10 minutes of the
  reload.
- [ ] P-S3: Kea's lease through R8's relay.
- [ ] P-S4: the TFTP fetch in Mercury's responder log.
- [ ] P-S5: the bootstrap on VLAN 1, read through Mercury.
- [ ] P-S6: Verify's result.
- [ ] P-S7: no PnP crash (uptime).
- [ ] The console reader's excerpt around the reload (non-sensitive lines only).

### 2. R6 and R7 boot from their goldens (option b) (OPEN: evidence from D4)

- [ ] D4: R6 and R7 answering after the redeploy at their goldens (drift clean), with OSPF and
  RIP neighbours as before.

### 3. H5, H6 and H7 renew their DHCP leases (OPEN: evidence from the measured hour)

- [ ] A renewal seen in the measured hour (E): the renewing client running in each host, and a
  lease renewed (Kea's lease time moving, or the client's own log).

### 4. s5 alone on CPU 19 (OPEN: evidence from E)

- [x] C3: "PINNING HOLDS", s5's kvm-pit thread on 19 (05:58 UTC).
- [ ] E: CPU 19's use and steal over the measured hour, and s5's clock rate once it is onboarded
  (its heartbeat starts with Verify's profile).

## Findings registered on the way (for after submission)

- C1522's closed row records the fix forward (CI run 1057).
