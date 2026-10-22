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

### The run sheet

**A. Mercury and the NMAS host, before anything restarts**

| # | Who | Step | PASS |
|---|---|---|---|
| A1 | agent | The bootstrap fix deployed: `nmas-deploy --wait` on `<nmas-host>` once the steps 1 and 2 commit's CI is green | it names CI's pass and the commit; Settings › About shows that sha |
| A2 | operator | The startup sync's map, `<home>/python/Agentic_NMAS/data/lab_targets/Default.tsv` on `<nmas-host>`: r6's line becomes `r6 labs/lab/configs default <user>@<lab-host> cisco_iosxe`; add the same line for r7; add `# DECLARED-UNMAPPED r8 default configless until its ZTP in Lab 9` and the same for s5 | the agent reads it back: r6 and r7 under `labs/lab/configs default`, r8 and s5 declared |
| A3 | operator (DECISION) | **Save All** (Devices › Actions › Save All), with nothing else running. A single failure: that device's Save alone, once, then Save All again (C1520) | "10 of 10 saved", and a new `baseline/<ts>` holding r6 and r7 |
| A4 | agent | The startup sync that baseline starts: the lab repository's newest commit, and `configs/r6.cfg` and `configs/r7.cfg` present (if the sync ran before A2, `sudo systemctl start clab-sync.service` on `<nmas-host>` once) | a `startup from baseline/<ts>` commit naming r6 and r7; both files present, owner-only (C1453) |
| A5 | operator | The break-glass export (Credentials › break-glass export), kept offline | the file saved; Needs attention has no "break-glass record is out of date" row |

**B. The lab repository on `<lab-host>`**

| # | Who | Step | PASS |
|---|---|---|---|
| B1 | agent | The vIOS configless launcher: `docker exec clab-rcn-lab1-s1 cat /launch.py > ~/labs/lab/patches/vios-launch-configless.py`, then `python3 patch-vios-configless.py ~/labs/lab/patches/vios-launch-configless.py --write` (the patcher copied from the deployed checkout) | the copy's sha256 before the patch is `794788bc…`; "written:"; `python3 -m py_compile` passes |
| B2 | operator | Option (b): `git apply --check`, then `git apply`, for `c8000v-launch-startup-only.diff` and then `option-b-labfile.diff` (copied from the deployed checkout's `lab/phase3/`) | each `--check` silent with exit 0; `grep -c NMAS_STARTUP_ONLY rcn-lab1.clab.yml` reads 2 |
| B3 | agent | Lab 9's change: `python3 patch-lab9.py ~/labs/lab`, read the diff, then `--write` | the diff matches the dry run above; "written:" for both files |
| B4 | operator | One lab-repository commit: `git add rcn-lab1.clab.yml configs/host-net-lab89.sh patches/c8000v-launch.py patches/vios-launch-configless.py && git commit -m "lab: Lab 9 - s5, h6, h7 and their links; r6 and r7 from their goldens (option b); CPU sets 0-18 and 19-23; no stages; renewing DHCP"` | `git status --short` lists none of the four |

**C. The redeploy (only when the start condition holds)**

| # | Who | Step | PASS |
|---|---|---|---|
| C1 | agent | The window, on `<nmas-host>` as `<user>`: `nmas-planned-restart Default r1 r2 r3 r4 r6 r7 s1 s2 s3 s4 --minutes 90 --new-host-keys --why "lab redeploy: Lab 9 - s5, h6, h7; r6 and r7 from their goldens" --by <operator>` | exit 0 and its three lines ("recorded: …", "window recorded <recorded_at> …", "expecting new SSH host keys …"); `<recorded_at>` kept |
| C2 | agent | At once, on `<lab-host>`: `cd ~/labs/lab && containerlab deploy -t rcn-lab1.clab.yml --reconfigure`. Never `restart` or `start` a node (C1372). A capture runs in s5's own namespace from its creation (UDP 67 and 68, on Gi0 and on eth0) | exit 0; 21 `clab-rcn-lab1-*` containers Up (r1 to r8, s1 to s5, h1 to h7, web) |
| C3 | agent (sudo) | The pinning: `sudo bash install.sh` from a copy of `lab/pinning` (its `pinning.conf` as above) | "PINNING HOLDS": s5's qemu and kvm-pit thread on 19, the other switches on 20 to 23, every router and host on 0-18 |

If the attempt stops before C2 runs, end the window at once (lab/REDEPLOY.md): `nmas-planned-restart Default --end <recorded_at> --why "<what stopped it>" --by <operator>`.

**D. Within the window**

| # | Who | Step | PASS |
|---|---|---|---|
| D1 | agent | The ten devices answer (the Devices page, read through Mercury); the time from C2 recorded | all ten answering; the redeploy's duration written here |
| D2 | operator | Settings › Installation › Diagnostics › Drift checks › **Check now** for Default | History (`/v2/history?kind=hostkeys`): one "SSH host key kept under a planned window" row per device |
| D3 | operator | Needs attention: the one "10 new host keys accepted during …" row, reviewed in History, then **Acknowledge** | no "restarted unexpectedly" or "different SSH host key" row for the ten |
| D4 | agent | R6 and R7 at their goldens (drift clean); OSPF and RIP neighbours as before the redeploy (Show commands, read-only); H5 holds 10.70.10.x and runs a renewing `udhcpc` (`docker exec clab-rcn-lab1-h5 ps`) | drift clean for both; neighbour counts unchanged; H5's lease and its renewing client present |
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

**If s5 cannot AutoInstall:** the operator types the minimal configuration on s5's console (a
user, and VLAN 1's SVI on DHCP). It is onboarded by DHCP through R8's relay, with no second
redeploy, and the video says why the switch is not zero-touch. The typed configuration is
LABOUR, a row in docs/MANUAL_STEPS.md and a finding.

## 7. Run sheet, shot list and the testing segment

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

## Findings registered on the way (for after submission)

- C1522's closed row records the fix forward (CI run 1057).
