# Lab 8: the morning walk and its drafts (2026-10-21)

**Status (2026-10-20 19:3x UTC):** steps 4b to 6 ran on 2026-10-20 (section 1a, the record).
From here the walk follows the one-lab-file model (section 1; docs/LAB_ONE_TOPOLOGY_PLAN.md),
reviewed by the operator; nothing of section 1 has run. Written first overnight 2026-10-20
as drafts; every value is from docs/LAB8_LAB9_PLAN.md section 4 or read from the host. A draft
that the walk shows wrong is corrected here before it is used.

**Read overnight (2026-10-20 09:11 UTC, read-only, Mercury's read path and the lab host):**
- **The lab reaches 8.8.8.8:** r4 and r3, `ping 8.8.8.8 source Loopback0`, 5 of 5 each.
  r4 holds no default route in its global table, so it reaches it by BGP from r5. R6's default
  will be R4's originated E2, and the traffic exits through R4's NAT (Gi5 inside, Gi2 outside).
- **s3 learns 10.255.4.0/30 inter-area from R4.** R6's replies need no host route on the NMAS
  host, unlike 0d's probe.
- **Step 4b's "before":** r1 and r4 hold 10.255.1.16/32 as OSPF extern 2 from s3 (10.255.1.23).
  s3 holds the static, `Redistributing via ospf 1`.
- **The lab host:** 80 GiB, 56.8 GiB available, swap 0 used, swap-in and swap-out 0 over 5 s.
  Management subnets 172.30.98.0/24, 172.30.99.0/24 and 172.30.100.0/24 are unused.
  `br-r4r6` and `br-r2r8` are up; `br-r6r7` and `br-r7h5` do not exist yet.

**Marks.** **[DEVICE]** changes a device (a Mercury operation: preview, confirm by hash, apply,
Verify, record). **[KEA]**, **[NETBOX]**, **[LAB]** and **[HOST]** change those systems.
**[READ]** changes nothing.

Contents:
1. The walk from 2026-10-20 evening: one lab file (A to E, R6 again, steps 7 to 10)
1a. The walk as run on 2026-10-20 (steps 4b to 6; the record)
2. Kea: the three subnets and two reservations
3. The lab files (RETIRED 2026-10-20: the one lab file replaced them)
4. R6's intent (draft)
5. R7's intent (draft)
6. H5
7. NetBox, for step 10
8. Lab 8's checks

---

## 1. The walk from 2026-10-20 evening: one lab file

**The operator's decision (2026-10-20 ~19:05 UTC):** R6, R7, R8 and H5 join `rcn-lab1.clab.yml`
as configless nodes on direct links in one declared full redeploy; s5, H6 and H7 join at one
more redeploy after Lab 9's 0a. The plan and its reasons are docs/LAB_ONE_TOPOLOGY_PLAN.md.
Steps 4b to 6 ran on 2026-10-20 under the old model and are kept in section 1a; R6 is redone
here from its kept intent.

**Who does what.** **[YOU]** is the operator: every Mercury screen action (it is the walk, and
the recording), every console step, and every "go". **[ME]** is the agent: host and lab-host
commands (sudo included, Phase 7 mode), reads, and the gate; never a Mercury action, never a
device console. A step marked **[ME, on your go]** waits for your word. Every step ends with
its **Expected** output; anything else is a stop, and the step's owner says so.

Times are UTC (yours, UTC−6, beside them). Nothing runs from 08:30 to 09:10 UTC, nor within
75 minutes before 08:30 once the window is declared.

### A. Before anything restarts

**A1 [ME, on your go]. The release.** `nmas-deploy --wait` on the NMAS host: 3d26c7a2 (C1421,
C1436), C1454's pre-flight refusal and the docs since. Then job health.
- **Expected:** "deployed <sha>" with CI's pass named; job health's not-ok rows the same as
  before (67 jobs, 3 not ok: break-glass out of date, `nmas-heartbeat-check`, and none new).

**A2 [ME]. R6's intent kept.** `nmas-config-read host_vars/r6.yml` (masked; it holds secret
references, never values) to `lab/lab8/r6-intent.yml`, committed through the gate. The file
says: Gi2's `ip dhcp client client-id ascii <serial>` is the boot's serial, new each boot, so at
re-use the NEW seed's Gi2 entry stays and everything else comes from this file.
- **Expected:** the commit's sha; the file's Gi2 holds `ipv4: dhcp`, Gi3 10.255.4.5/30 with its
  helper, Loopback0 10.255.1.16/32.

**A3 [YOU]. R7's subnet, while r6's intent still holds its relay** (this order is forced:
Add a subnet reads the relay from committed intent, LAB_ONE_TOPOLOGY_PLAN A5).
DHCP › Add a subnet with section 2.2's values (10.255.4.4/30, pool 10.255.4.6 - 10.255.4.6,
For ZTP onboarding ticked, no DNS). Preview, confirm.
- **Expected:** the relay line "relayed to <Kea> by r6 GigabitEthernet3 (intent)", relay
  `10.255.4.5`; D4's check: no DNS, no subnet-level route option; Kea's `-t` passes.

**A4 [ME]. The firewall host step** for the new relayed subnet:
`bash ~/python/Agentic_NMAS/scripts/host-steps/c1346-ztp-relayed-firewall.sh`.
- **Expected:** PASS, udp/69 admitted from 10.255.4.4/30 (and still from 10.255.4.0/30).

**A5 [YOU]. Add device › ZTP for R7** (section 2.2): `r7`, IOS-XE, router, 10.255.4.6/30, MAC
`aa:bb:cc:00:04:07`, management `GigabitEthernet2`, route option (3) the relay's own address.
- **Expected:** the result names the reservation `aa:bb:cc:00:04:07 -> 10.255.4.6` (C1441's
  wording may still say `-> ?`); a pending row "r7: reserved, not leased".

**A6 [YOU]. Retire r6** (R6's page › Retire…). Read the preview: every step, including
reservations (ZTP's for `aa:bb:cc:00:04:06`), leases, heartbeat and telemetry (their delete
files). No step touches a Kea subnet. Confirm with the reason "one lab file: R6 rebuilt
configless by ZTP (LAB_ONE_TOPOLOGY_PLAN)".
- **Expected:** "Retired"; the name `r6` free; NetBox's record renamed `r6-retired-<id>`,
  Decommissioning. Between here and R6's step 6, a row about 10.255.4.4/30's relay being in no
  intent may appear: expected, it clears at R6's step 6.

**A7 [ME]. The C1419 install step, removal path:**
`bash ~/python/Agentic_NMAS/scripts/host-steps/c1419-install-alert-rules.sh heartbeat` then
the same with `telemetry` (the retire result prints each one's values).
- **Expected:** PASS for each (8 of 8); Grafana shows no rule naming r6. The first real run of
  the install step.

**A8 [YOU]. Add device › ZTP for R6** (section 2.1's values; the subnet 10.255.4.0/30 stayed):
`r6`, `aa:bb:cc:00:04:06`, 10.255.4.2/30, route option (3) the relay's own address.
- **Expected:** the reservation `aa:bb:cc:00:04:06 -> 10.255.4.2`; a pending row "r6:
  reserved, not leased". **R6 must not boot before this exists** (without it R6 takes the pool
  address with no boot file, and AutoInstall gives up: M4).

### B. The startup files: today's goldens

**B1 [YOU]. Save All** for Default (Actions › Save All).
- **Expected:** 8 of 8 captured (r1 to r4, s1 to s4), and `Baseline: earned` with a new
  `baseline/<ts>`. Denied means a device is not at its intent: the record names it and the
  lines; stop and resolve that first.

**B2 [ME]. The sync,** started by the baseline event (`clab-sync.path`): its journal for the run.
- **Expected:** "committed" for the lab's `configs/`; per device, the `REMOVED` counts as in its
  last run (the sanitiser's rules, never the lines). I read result lines only, never a file.

**B3 [ME]. The pre-flight:** `nmas-startup-source --check --list Default`.
- **Expected:** `baseline <B1's tag>`, and for each of the eight `ok | ... 0 newer |
  credentials current: True ... | golden after last rotation: True | read by drift: True`;
  last line `8 of 8 pass`. Any "a redeploy would undo" line is a stop (C1454's refusal).

**B4 [ME]. The files' mode on the lab host:** `chmod 600` on `configs/*.cfg` and the
`configs.bak-*` copies (C1453), then `ls -l --time-style=+%FT%T configs/`.
- **Expected:** r1 to r4 and s1 to s4 `-rw-------`, each dated after B1; r5's unchanged (the lab
  repository's own, DECLARED-UNMAPPED).

### C. The lab host

**C1 [ME]. The new file and its pieces** (LAB_ONE_TOPOLOGY_PLAN section 3, option 1: r6, r7,
r8, h5): the configless patch copied to `~/labs/lab/patches/` (sha256 equal to lab8's), and
`configs/host-net-lab89.sh`; the lab repository's own uncommitted changes committed first,
then the new file and the script in a second commit.
- **Expected:** both commits' shas; `git status` clean in `~/labs/lab`.

**C2 [ME]. A dry run** of a renamed copy (`name: rcn-lab1-check`, in `/tmp/check/`):
`containerlab deploy -t /tmp/check/rcn-lab1.clab.yml --dry-run`.
- **Expected:** a dry-run result and no container created (`docker ps` count unchanged, 16).
  A parse error names the line: fix it in C1 and run again.

**C3 [ME, on your go]. R6's old lab out:** `containerlab destroy -t ~/labs/lab8/lab8-r6.clab.yml
--cleanup`, then `docker network rm clab-lab8-r6` if it is left.
- **Expected:** `clab-lab8-r6-r6` gone (`docker ps` 15); the network gone.

**C4 [ME]. Its two bridges:** `ip -br link show master br-r6r7` and `master br-r7h5` each
empty, then `sudo ip link del` each.
- **Expected:** `ip -br link show type bridge` lists `br-mgmt`, `br-r4r6`, `br-r2r8` and
  docker's own; not `br-r6r7` or `br-r7h5`.

### D. The redeploy

**D1 [ME]. Time:** start only if 08:30 UTC is more than 75 minutes away, or after 09:10.

**D2 [ME]. The lab host:** `free -g`; `vmstat 5 5`; `uptime`.
- **Expected:** at least 20 GiB available; `si` and `so` 0 in every row; `st` 0 (`gu` is the
  routers' nested VMs).

**D3 [ME]. The hypervisor** (read-only): `free -g`; `uptime`; `qm list`.
- **Expected:** at least 20 GiB available; VMs 201 and 202 stopped (yours).

**D4 [YOU, I read]. Before:** Drift › Check now for Default; Needs attention's rows. I read the
adjacency reader's per-device neighbour counts.
- **Expected:** 8 of 8 read, none drifted; the counts recorded (as at 10-20: r1 2/2, r2 2/2,
  r3 6/4, r4 7/5 with R6 retired, so its R6 neighbour gone, s3 2, s4 2).

**D5 [ME, on your go]. The window, then at once the redeploy:**
`scripts/nmas-planned-restart Default r1 r2 r3 r4 s1 s2 s3 s4 --minutes 60 --new-host-keys
--why "lab redeploy: rcn-lab1 one file, Labs 8 and 9 nodes added configless" --by <operator>`,
then on the lab host in tmux `cd ~/labs/lab && containerlab deploy -t rcn-lab1.clab.yml
--reconfigure`.
- **Expected:** `recorded: r1, r2, r3, r4, s1, s2, s3, s4 ...` with its `<recorded_at>` (kept:
  it names the window if the attempt stops); the deploy blocks about 25 minutes on the stages
  while the fleet boots, then creates r6, r7 and r8 and finishes. If it stops before it runs,
  end the window at once (REDEPLOY.md).

### E. After

**E1 [YOU, I read]. The fleet:** Devices page; Drift › Check now inside the window; History's
host keys; Needs attention.
- **Expected:** all eight Answering (about 24 minutes); 8 of 8 read, none drifted; eight "SSH
  host key kept under a planned window" rows, then one Needs attention row to acknowledge; the
  neighbour counts equal D4's (r4 and r2 each have one more port up, no new neighbour); no
  "restarted unexpectedly" row.

**E2 [ME]. The old bridges:** `master br-r4r6` and `master br-r2r8` empty, then `sudo ip link
del` each.
- **Expected:** only `br-mgmt` and docker's bridges remain.

**E3 [ME]. The new nodes and the captures:** each of r6, r7, r8 `healthy` (docker's health
state, read only); the two captures started (LAB_ONE_TOPOLOGY_PLAN section 4) on r7's and r8's
uplinks, and a short one on r6's.
- **Expected:** R6's DISCOVERs leave Gi2, Kea's offer of 10.255.4.2 with options 66, 67 and 3
  arrives through R4, and the fetch of `r6.cfg` follows; R7's and R8's DISCOVERs repeat with
  no answer.

### R6, again (steps 5.5 to 6)

**R1 [YOU]. Onboarding** runs from the pending row: Verify waits out the key settle (C1400) and
promotes R6.
- **Expected:** about 10 to 15 minutes after R6's container was created: answered, captured,
  credential rotated and persisted, NetBox records written; the pending row gone.

**R2 [YOU]. Step 6 again** (section 1a's step 6): Seed intent…, commit, then the kept intent
(A2) applied as edits to the seed, KEEPING the new seed's Gi2 entry; commit; plan; confirm;
Verify.
- **Expected:** the plan as section 1a's step 6 (Loopback0 created; Gi3 with its helper, RIP
  and RIPng; router ospf with two networks in area 10). Verify amber with RIP and RIPng unmet
  until R7 forms (C1450). After [I read]: R6 and R4 OSPF Full; s3's route to 10.255.1.16 O IA.

**R3 [YOU, then ME]. R6's monitoring:** Monitoring › Heartbeat › re-measure [YOU]; the install
step `heartbeat` [ME]; `nmas-telemetry-rules` and the install step `telemetry` [ME].
- **Expected:** PASS for each; Grafana shows R6's heartbeat rule and its two telemetry rules.
  With A7's removal run, this closes C1419.

### Step 7: R7 (no lab step)

**7.1 [I read].** R7 has been asking since the redeploy; once R6's Gi3 helper is deployed (R2),
its next DISCOVER is relayed. The capture shows the first answered one.
- **Expected:** Kea's offer of 10.255.4.6; R7's fetch of `r7.cfg`; the pending row advancing.
  **If the capture shows R7 stopped asking** (AutoInstall gave up): **[YOU]** R7's console,
  answer `no` to the dialog, `reload`, confirm. R7 asks again within its boot time.

**7.2 [YOU]. R7's onboarding, then its intent** (section 5): seed, edit, commit, plan, confirm,
Verify.
- **Expected:** as section 1a's step 7.5: Loopback0, Gi3 up, Gi3.10 10.70.10.1/24 and
  2001:db8:70:10::1/64 with its helper, router rip, ipv6 rip RCN. After [I read]: on R6,
  `show ip rip database` holds 10.70.10.0/24; on R4, `show ip route 10.70.10.0` is O E2 via R6.

### Step 8: H5 (no lab step)

**8.1 [YOU]. DHCP › Add a subnet** 10.70.10.0/24 (section 2.3).
**8.2 [I read].** H5 has been retrying since the redeploy (`host-net-lab89.sh`, no give-up).
- **Expected:** the DHCP page shows H5's lease in .100 to .200; on R7, `show ipv6 interface
  GigabitEthernet3.10` holds the /64; H5's own log line "done after N tries" (read on the lab
  host).

### Steps 9 and 10, and Friday

- Steps 9 and 10 as section 1a's.
- **The break-glass export** after R6 and R7 are verified, before Friday.
- **Friday's rehearsal reset, no containerlab** (LAB_ONE_TOPOLOGY_PLAN section 6), R7 then R6:
  [YOU] Retire; [YOU] Add device › ZTP again with the same MAC; [YOU] the device's console:
  `write erase`, confirm, `reload`, confirm, do not save. It boots configless and asks again.
  C1432's measurement (section 1a's 5b) runs on R6 just before its Retire.

---

## 1a. The walk as run on 2026-10-20 (steps 4b to 6; kept as the record)

Times are UTC. Nothing runs between 08:30 and 09:10. One device-changing step at a time, each
verified before the next. A Mercury update to the host happens only between steps, never
during one.

### Before step 4b
- **[READ] Needs attention.** Expect the break-glass row (r2 rotated 01:06 on 10-20), the
  heartbeat check (s3's jitter), r1's adjacency drop, no baseline, and NetBox lagging r4's Gi5
  (step 9 clears it). `nmas-telemetry-check` had cleared by 09:27 UTC on 10-20 (job health: 67
  jobs, 3 not ok, none new).
- **[READ] The lab host's memory** (C1380): `free -m` and `vmstat 1 5` on the lab host, read
  only. Go on when swap-in and swap-out read 0 and available memory is above about 6 GiB, as
  measured overnight (section 3). Two C8000v nodes take about 8 GiB more.

### Step 4b: s3's stale route [DEVICE: s3]
- **Repair route:** s3's console through the lab host (the operator's). The change does not
  touch the management path.
- **Before [READ]:** Show commands › Devices `r1, r4` › command `show ip route 10.255.1.16` ›
  Run on 2 devices. Expected on each: `Routing entry for 10.255.1.16/32`, `Known via "ospf 1"`,
  `type extern 2`, from s3's redistribution.
- **The plan:** s3's page › Deploy › Plan a deploy. Intent already lacks the route (86f3fc4).
  Expected:
  - nothing to add;
  - under **Left on the device**, `ip route 10.255.1.16 255.255.255.255 10.255.0.32` with a
    tick box;
  - `ip route 10.255.1.10 255.255.255.255 10.255.0.10` is NOT in the list, since intent holds
    it. Had it been residue, its box would be disabled: "the management path: its destination
    10.255.1.10/32 holds 10.255.1.10, an address of this host".
  - `ipv6 route ::/0 2001:DB8:3::13` is not residue either (intent holds it).
- **Tick and reason:** tick the .16 line; reason "the retired r6's loopback; the new R6 reuses
  10.255.1.16 (C1422)". **What will not happen** should say no other line is removed.
- **Confirm by hash.** The program is exactly one line,
  `no ip route 10.255.1.16 255.255.255.255 10.255.0.32`, plus `end`/save per the platform.
- **Verify:** QUICK or FULL by scope; the removal's read-back says the line is gone.
- **After [READ]:** the same Show commands. Expected: `% Network not in table` on r1 and r4, or
  a shorter prefix only (no /32, no E2).
- Save to startup as the plan offers.

### Step 5: R6's subnet, onboarding and boot
1. **[KEA] DHCP › Add a subnet** for R6's link (section 2.1). Preview, confirm. Read the D4
   check line: no DNS option, no route option at subnet level.
2. **[HOST] The firewall host step** for the relayed subnet, AFTER the subnet exists (it reads
   the relayed ZTP subnets from Mercury's own subnet file):
   `bash ~/python/Agentic_NMAS/scripts/host-steps/c1346-ztp-relayed-firewall.sh`. Expected:
   PASS, and udp/69 admitted from 10.255.4.0/30. **Read 2026-10-20 16:31 UTC:** the NMAS
   host's ufw has default incoming ALLOW, with no rule for udp/67 or udp/547. So DHCP from
   every relay (10.255.4.1, 10.255.4.5, 10.70.10.1) and TFTP from the ZTP subnets already
   reach Kea and the responder. Neither R6, R7 nor H5 needs another host step; this one
   records the TFTP admission for job health's `ztp-firewall` row. The default-allow itself is
   C1435.
3. **[DEVICE: none yet] Add device › ZTP** in Default, as in section 2.1's reservation: Create
   writes the reservation (options 66 and 67, option 3 = 10.255.4.1, no 6).
4. **[LAB] The bridges, then R6's lab** (section 3), after the memory read:
   `bash ~/labs/lab8/bridges.sh` (it makes `br-r6r7` and `br-r7h5` when absent and prints PASS;
   `lab8-r6` references `br-r6r7`, and neither bridge survives a lab-host reboot), then
   `sudo containerlab deploy -t lab8-r6.clab.yml`. R6 boots configless, sends a
   DISCOVER through R4 Gi5 (giaddr 10.255.4.1), gets 10.255.4.2 with 66, 67 and 3, and fetches
   its bootstrap over TFTP routed through R4.
5. **Onboarding's Verify** waits out the key settle (C1400, 120 s after the last fetch), then
   promotes R6: answered, captured, credential rotated and persisted, NetBox records written.
   Expected time from deploy: about 10 to 15 minutes (C8000v boot about 6 to 8, AutoInstall,
   Verify).
- **Repair route:** R6's console through the lab host. If AutoInstall gives up (about 2.5 min
  without an answer, M4), destroy R6's lab with `--cleanup` and deploy it again. Never a
  restart.

### Step 5b: C1432's measurement on R6, out of service [DEVICE: R6] (the operator, 10-20)

**SKIPPED (2026-10-20 18:3x UTC): it cannot be undone cleanly through Mercury.** No Mode B
shape exists for an `ip helper-address`, an `ipv6 address` or a virtual interface's stanza, and
a second `ntp server` is never offered for removal, because C1432 itself reads the profile's NTP
server as its setting-key mate. **The alternative:** run the measurement on R6 at Friday's
rehearsal, just before R6 is retired. Retirement then takes R6 away, so nothing needs removing.
C1432's fix stays after Lab 8. The steps below are kept for that run.

R6 carries no traffic yet, so it measures what the planner gets wrong about multi-valued
commands (C1432: it reads a new value as REPLACING the old, while IOS keeps both). Values are
documentation addresses that reach nothing.
1. **[READ] Before:** R6's capture after Verify, masked: its `ntp server`, `logging host`,
   `snmp-server host`, `ip helper-address` and `ipv6 address` lines (the agent reads them).
2. R6's page › Intent › **Seed intent…**, commit.
3. **Edit A** [DEVICE]: Gi3 `helper_addresses: [192.0.2.1]` and `ipv6: [2001:DB8:2:67::1/64]`;
   top level `ntp_servers: [10.255.1.10, 192.0.2.123]` (a device's own list replaces the
   profile's whole). Commit, plan (three lines added), confirm, Verify.
4. **Edit B** [DEVICE]: the same three values changed to `192.0.2.2`,
   `2001:DB8:2:67::9/64` and `192.0.2.124`. Commit, plan. **Record what the plan says under
   "Left on the device"**: C1432 predicts nothing for the three old values. Confirm, Verify.
5. **[READ] After:** R6's capture. C1432 predicts both values of each present: helper .1 and
   .2, both IPv6 addresses, NTP .123 and .124. Each line is recorded in C1432.
6. **Back to the bootstrap state:** Mode B cannot remove these lines (`global.ntp-server` is
   unmeasured on IOS-XE, and no shape exists for a helper or an IPv6 address), so R6 goes back
   by Friday's own path: a break-glass export first (it now holds R6), then Retire R6, then
   `containerlab destroy -t lab8-r6.clab.yml --cleanup`, then step 5 again (the reservation
   is made again by Add device). This is also the first real run of C1418, C1419 and C1420.

### Declarations and authorisations at each step (the operator's 3e)

A plan asks for an authorisation with a reason for every dangerous line it sends (`shutdown`,
`no ip address`, `no router …`, `crypto key zeroize`, `erase nvram`, `reload`) and for every
Mode B removal (`removal.removal_keys`). Step 4b's removal of s3's route was one; C1434 is why
the plan did not say so before Confirm. The "Routes are expected to change" declaration is
consulted only when the route table shrinks by more than 10%. Read against each step's drafted
program:

| Step | Authorisation | Declaration |
|---|---|---|
| 4b, s3's route (done) | the removal (`no ip route …`) | not needed (one /32 of many) |
| 5b, edits A and B on R6 | none: the lines are additions | none |
| 6, R6's intent | none: no dangerous line (` no shutdown`, `no passive-interface`, `no auto-summary` are not), no removal | none: routes are added |
| 7, R7's intent | none, while Gi3 keeps `no_ip_address: true` (the device already prints ` no ip address`, so it is not sent) | none |
| 5b's return and the rehearsal: Retire | none in a plan; Retire's own preview takes its reason | none |

If a plan asks for one anyway, stop and read it before confirming.

### Step 6: R6's full intent [DEVICE: R6]
- **C1432 at this step:** R6's bootstrap renders none of the multi-valued lines (hostname,
  account, domain, `ip address dhcp` on Gi2, SSH key, vty). NTP, logging host and
  SNMP host arrive from Default's profile at onboarding, with the same values the draft
  inherits (the draft sets none of them). The helper and the IPv6 addresses are new, with no
  old value. So nothing is replaced, and C1432 does not bite, provided step 5b's "before" read
  shows the profile's values. The agent reads R6's capture after step 5 to confirm.
- **Repair route:** R6's console. Gi2 keeps `ip address dhcp` exactly as the bootstrap left it
  (the operator, 2026-10-20: switching the management interface from DHCP to static
  mid-session would change the path the tool reaches R6 on). Its address, 10.255.4.2, is
  Kea's reservation. The bootstrap also wrote a static `ip route 0.0.0.0 0.0.0.0 10.255.4.1`
  (read in R6's capture at 18:31 UTC), which stays: distance 1, so it remains R6's default
  after OSPF's E2 default from R4 arrives (the same next hop). The draft does not touch Gi2's
  address, the static default, the vty lines, SSH or the account.
- R6's page › Intent › **Seed intent…**, commit. Then edit the SEED IN PLACE (section 4's
  "Step 6 as edits to the seed"); never replace the seed's Gi2 entry, which holds
  `ipv4: dhcp` and the DHCP client-id line. Commit. Plan a deploy.
- **Expected preview:**
  - Loopback0 created;
  - Gi3 addressed, with its helper, RIP and RIPng;
  - router ospf 1 with two networks in area 10 and `redistribute rip`;
  - router rip, version 2, passive default, Gi3 not passive, default-information originate,
    no auto-summary;
  - ipv6 router ospf 1 and ipv6 router rip RCN;
  - **What verify checks:** Gi3 comes up; an OSPF adjacency may form on Gi2 (to R4), not
    required. Verify counts each neighbour table's rows, so a lost adjacency fails it
    (C1427, read in the code overnight).
- **Verify** FULL. After it [READ]:
  - on R6 and R4, `show ip ospf neighbor`: Full, R6 to R4 on Gi2 and R4 to R6 on Gi5;
  - on R4, `show ip route 10.255.1.16`: intra-area O;
  - on s3, `show ip route 10.255.1.16`: O IA via OSPF, no static.
- Save to startup.

### After step 6: R6's monitoring [HOST]
- The heartbeat rules: Monitoring › Heartbeat › re-measure (R6 joins the population once its
  committed intent holds the syslog block the profile gives it), then the install step it
  names: `bash ~/python/Agentic_NMAS/scripts/host-steps/c1419-install-alert-rules.sh heartbeat
  <written> <installed>` (the page prints every value).
- The telemetry rules: `nmas-telemetry-rules` on the host (R6's golden now holds the profile's
  subscriptions 101 and 102), then the same install step with `telemetry`.
- Each step's first real run: C1419's install step replaces the per-device stopgap; its PASS
  line is the evidence.

### Step 7: R7 by ZTP through R6, then its intent
1. **[KEA]** DHCP › Add a subnet for R7's link (section 2.2).
2. **[HOST]** The firewall host step again, after the subnet exists (10.255.4.4/30).
3. Add device › ZTP for R7 (section 2.2).
4. **[LAB]** Deploy R7's lab (section 3; the bridges exist from step 5, or run
   `bash ~/labs/lab8/bridges.sh` again). Onboarding's Verify promotes R7 over two relays'
   worth of routing: Mercury → s3 → OSPF → R4 → R6 (RIP into OSPF) → R7.
5. **[DEVICE: R7]** R7's intent (section 5): seed, paste, commit, plan, confirm, Verify.
   - Repair route: R7's console.
   - Expected: Loopback0, Gi3 up, Gi3.10 with 10.70.10.1/24, 2001:db8:70:10::1/64 and its
     helper, router rip, ipv6 rip RCN.
   - After [READ]: on R6, `show ip rip database` holds 10.70.10.0/24; on R4,
     `show ip route 10.70.10.0` is O E2 via R6.

### Step 8: H5
1. **[KEA]** DHCP › Add a subnet 10.70.10.0/24 (section 2.3).
2. **[LAB]** Deploy H5's lab (section 3). H5 tags VLAN 10 and asks DHCP through R7's helper.
3. **[READ]:**
   - the DHCP page shows H5's lease from .100 to .200;
   - on R7, `show ipv6 interface GigabitEthernet3.10` holds the /64 and RA;
   - H5's SLAAC address, read on the lab host by the operator.

### Steps 9 and 10: the NSoT and the documentation
- NetBox sync from Mercury for R6 and R7. Section 7's checklist for what Mercury does not write.
- **The break-glass export** after R6 and R7 are verified, before Friday (the plan's item 9),
  on Credentials. It also clears the r2 row.
- Lab 8's checks (section 8), each read through Mercury.

---

## 2. Kea

### 2.1 R6's link (step 5)

**DHCP › Add a subnet:**
- Subnet: `10.255.4.0/30`
- Relay: `10.255.4.1` (R4 Gi5, from R4's intent)
- Pool: `10.255.4.2 - 10.255.4.2`, the device's one address. **Corrected 2026-10-20 16:3x
  UTC:** the draft said "no pool", and the preview never runs for an Add without a pool. It
  re-renders the form unchanged and says nothing (C1436). The tested ZTP shape is a pool of
  the device's own address, with Kea's reservation by MAC inside it.
- For ZTP onboarding: ticked. That gives `match-client-id: false` on a relayed ZTP subnet
  (C1403 part 2, `dhcp_subnets._match_by_mac`).
- No DNS option (D4). No subnet-level route option: option 3 goes on the reservation.

**Add device › ZTP (Default):**
- Hostname `r6`; platform IOS-XE (cisco_iosxe); role router.
- Address from ZTP: `10.255.4.2/30`; MAC `aa:bb:cc:00:04:06` (pinned in R6's lab file, R6's
  Gi2 = eth1).
- Management interface `GigabitEthernet2`.
- Route option (3): **The relay's own address** (10.255.4.1). It is required: 0d measured that
  AutoInstall fetches nothing without it (docs/RELAY_PROBE.md, Results).
- DNS: none.

### 2.2 R7's link (step 7)
- Subnet `10.255.4.4/30`, relay `10.255.4.5` (R6 Gi3), pool `10.255.4.6 - 10.255.4.6`, For ZTP
  onboarding ticked, no DNS.
- Add device › ZTP: `r7`, IOS-XE, router, `10.255.4.6/30`, MAC `aa:bb:cc:00:04:07` (R7's Gi2 =
  eth1), management interface `GigabitEthernet2`, Route option (3) the relay's own address
  (10.255.4.5).

### 2.3 H5's subnet (step 8)
- Subnet `10.70.10.0/24`, relay `10.70.10.1` (R7 Gi3.10), pool `10.70.10.100` to
  `10.70.10.200`, router option `10.70.10.1`, **no DNS option** (the operator, 2026-10-20; C1425).
- For ZTP onboarding: not ticked (a host subnet).
- IPv6: none in Kea. H5 takes SLAAC from R7's RA.

---

## 3. The lab files (lab host, `<home>/labs/lab8/`) — RETIRED 2026-10-20

**Replaced by the one lab file** (the operator's decision, 2026-10-20; docs/LAB_ONE_TOPOLOGY_PLAN.md
section 3): R6, R7, R8 and H5 are nodes of `rcn-lab1.clab.yml`, and `bridges.sh` and the
per-device files below are no longer used. `lab8-r6` is destroyed at section 1's C3. Kept as
the record of what step 5 ran.

**Names that cannot collide:** labs `lab8-r6`, `lab8-r7`, `lab8-h5`; containers
`clab-lab8-r6-r6`, `clab-lab8-r7-r7`, `clab-lab8-h5-h5`. The old `clab-r6` lab is destroyed.

Each node is its own lab, because each must boot only after its relay, subnet and reservation
exist (AutoInstall gives up after about 2.5 min), and no node is ever restarted to make it ask
again. A re-add for Friday's rehearsal is `containerlab destroy -t <file> --cleanup` then
`deploy` (lab/REDEPLOY.md's rule).

**Host bridges: `~/labs/lab8/bridges.sh`** (the operator's lab tooling; run at step 5 before
`lab8-r6`, and first in the rehearsal script, since a lab-host reboot drops them; `br-r4r6`
and `br-r2r8` come with rcn-lab1's redeploy):
```sh
#!/bin/sh
# Lab 8: the host bridges R6, R7 and H5 join (not persisted). Idempotent: a bridge that
# exists is left as it is. Run before lab8-r6 (it references br-r6r7).
set -u
fail=0
for br in br-r6r7 br-r7h5; do
  if ! ip link show "$br" >/dev/null 2>&1; then
    sudo ip link add "$br" type bridge stp_state 0 forward_delay 0 || fail=1
  fi
  sudo ip link set "$br" up || fail=1
  ip link show "$br" | grep -q "[<,]UP[,>]" || { echo "FAIL: $br is not set up"; fail=1; }
done
[ "$fail" -eq 0 ] && echo "PASS: br-r6r7 and br-r7h5 exist and are set up" || exit 1
```
A bridge with nothing attached reads state `DOWN` (no carrier) though it is set up; the script
checks the `UP` flag, not the state, and the state turns `UP` when the first veth joins.

**Management subnets:** 172.30.98.0/24, 172.30.99.0/24 and 172.30.100.0/24. Check they are
unused before deploying: `ip -br addr | grep -c 172.30.9[89]\|172.30.100` should print 0. The
overnight read is in the morning report.

### `lab8-r6.clab.yml`
```yaml
name: lab8-r6
# Lab 8 step 5: R6, CONFIGLESS (P.6's patch and management passthrough, as 0d's zr6), Gi2 on
# br-r4r6 beside R4 Gi5, its MAC pinned for Kea's reservation (aa:bb:cc:00:04:06 -> 10.255.4.2).
# Gi3 (eth2) on br-r6r7 for R7. Destroyed with --cleanup and deployed again for a re-add; never
# restarted.
mgmt:
  network: clab-lab8-r6
  ipv4-subnet: 172.30.98.0/24
topology:
  kinds:
    cisco_c8000v:
      image: vrnetlab/cisco_c8000v:17.06.01a          # identical to the fleet's routers
  nodes:
    r6:
      kind: cisco_c8000v
      mgmt-ipv4: 172.30.98.16
      env:
        CLAB_MGMT_PASSTHROUGH: "true"
      binds:
        - patches/c8000v-launch-configless.py:/launch.py
    br-r4r6:
      kind: bridge
    br-r6r7:
      kind: bridge
  links:
    - type: veth
      endpoints:
        - node: r6
          interface: eth1
          mac: aa:bb:cc:00:04:06
        - node: br-r4r6
          interface: r6-r4
    - type: veth
      endpoints:
        - node: r6
          interface: eth2
          mac: aa:bb:cc:00:04:16
        - node: br-r6r7
          interface: r6-r7
```

### `lab8-r7.clab.yml`
```yaml
name: lab8-r7
# Lab 8 step 7: R7, CONFIGLESS, Gi2 on br-r6r7 beside R6 Gi3 (aa:bb:cc:00:04:07 -> 10.255.4.6),
# Gi3 (eth2) on br-r7h5 for VLAN 10 (H5).
mgmt:
  network: clab-lab8-r7
  ipv4-subnet: 172.30.99.0/24
topology:
  kinds:
    cisco_c8000v:
      image: vrnetlab/cisco_c8000v:17.06.01a
  nodes:
    r7:
      kind: cisco_c8000v
      mgmt-ipv4: 172.30.99.17
      env:
        CLAB_MGMT_PASSTHROUGH: "true"
      binds:
        - patches/c8000v-launch-configless.py:/launch.py
    br-r6r7:
      kind: bridge
    br-r7h5:
      kind: bridge
  links:
    - type: veth
      endpoints:
        - node: r7
          interface: eth1
          mac: aa:bb:cc:00:04:07
        - node: br-r6r7
          interface: r7-r6
    - type: veth
      endpoints:
        - node: r7
          interface: eth2
          mac: aa:bb:cc:00:04:17
        - node: br-r7h5
          interface: r7-h5
```

### `lab8-h5.clab.yml` (section 6)

**Commands (the operator's, on the lab host), in the walk's order:**
```
mkdir -p ~/labs/lab8/patches ~/labs/lab8/configs
cp ~/labs/ztp-a/patches/c8000v-launch-configless.py ~/labs/lab8/patches/
cd ~/labs/lab8
free -m && vmstat 1 5                                  # C1380: no swap pressure
ip -br addr | grep -c '172.30.9[89]\|172.30.100'       # 0: the management subnets are free
bash bridges.sh                                        # PASS: br-r6r7 and br-r7h5 (section 3)
sudo containerlab deploy -t lab8-r6.clab.yml           # step 5, after the reservation
sudo containerlab deploy -t lab8-r7.clab.yml           # step 7, after R6's intent and R7's reservation
sudo containerlab deploy -t lab8-h5.clab.yml           # step 8, after R7's intent and H5's subnet
# a re-add (Friday): destroy with --cleanup, never restart
sudo containerlab destroy -t lab8-r7.clab.yml --cleanup
```

---

## 4. R6's intent (draft, today's model)

**How it is applied:** after onboarding, R6's intent is bootstrap-only. **Seed intent…** it from the
capture on the Intent tab, then replace or add the sections below. Leave unchanged everything
the seed holds for:
- **Gi1** (vrnetlab's management passthrough);
- **Gi2's `ipv4: dhcp`**, the management path from the bootstrap: R6 is reached at its leased
  address (Kea's reservation, 10.255.4.2), and its default route is the bootstrap's static
  `ip route 0.0.0.0 0.0.0.0 10.255.4.1` (the seed's `static_routes`; read in the capture
  18:31 UTC). Both stay as they are (corrected 2026-10-20, the operator: the draft had written
  the address static, a mid-session change of the management path). R6's management therefore rests on its lease renewing through R4's relay. Kea's
  reservation keeps the address, and C1410 (DHCP for bootstrap only) is the Core 1.0 answer;
- **the vty lines, SSH and the account** onboarding made.

Monitoring comes from Default's profile, so it is NOT in the draft: NTP, SNMP, syslog with
heartbeat, telemetry, LLDP, IP SLA and the Loopback0 source interfaces (read 2026-10-20).

**Step 6 as edits to the seed** (written 2026-10-20 18:3x UTC from R6's capture after
onboarding: Gi2 `ip address dhcp` with `ip dhcp client client-id ascii <serial>`; Loopback0, Gi1
and Gi3 each `no ip address`, no `shutdown` on any; the static default via 10.255.4.1; the
profile's lines; no `cdp run`, `ipv6 unicast-routing` or `netconf-yang`):
- **Loopback0:** delete the seed's `no_ip_address: true` (C1429 refuses it beside an address);
  add `description`, `ipv4`, `ipv6` and `ospfv3` as drafted below.
- **Gi2:** leave `ipv4: dhcp`, the client-id line and every other seed key; change only the
  `description`, and add `ipv6` and `ospfv3` as drafted.
- **Gi3:** delete the seed's `no_ip_address: true`; add `description`, `ipv4`, `ipv6`,
  `helper_addresses`, `ripng` and `no_shutdown: true` as drafted (Gi3 is not shut, so
  ` no shutdown` is held at its default and nothing is sent for it).
- **Gi1:** unchanged.
- **flags:** add `cdp run`, `ipv6 unicast-routing` and `netconf-yang` (the seed has `lldp run`).
- **routing:** add the four blocks as drafted (the RIP `network` line copied from r2's intent).
- **static_routes:** unchanged (the bootstrap's default).
- **services and login:** unchanged (the seed's own).
- **Expected plan:** additions only. Nothing under "Left on the device", and no authorisation
  or declaration asked. Loopback0 now holds the address the profile's sources (logging, SNMP
  traps, SSH, TFTP) point at.

**Traps, each marked `# TRAP`:**
- Gi3 (and Loopback0) on R6 print ` no ip address` and no ` shutdown` (read 18:31 UTC). The
  seed then holds `no_ip_address: true`, which must be removed when the address is added
  (C1429 refuses the pair); there is no `shutdown` key to remove.
- `redistribute rip subnets` prints as `redistribute rip` on 17.6 (r2's intent holds the
  printed form). Write the printed form, or every later plan sends it again.
- The RIP `network` line is a placeholder (the public repository holds no lab address
  block): copy r2's `routing.rip.networks` entry in its place, in R6's and R7's drafts both.
- Do not copy `users` or `secret_refs` from r4. A device's secret refs resolve under
  `<network>:<device>:<ref>`, and none is set for r6 (C235). Onboarding's account is the one.
- Do not change `ssh` or the vty lines in this deploy (the path rule). The fleet's
  `transport input all` (telnet) is C1431's, not something to copy.
- NAT: R6 has no outside interface and needs no `ip nat`. Area 10's sources are translated at
  R4 and R3, whose NAT-PRIVATE permits every RFC 1918 range (read 2026-10-20).

```yaml
interfaces:
- name: Loopback0
  description: mgmt identity
  ipv4: 10.255.1.16 255.255.255.255
  ipv6:
  - 2001:DB8:1::16/128
  ospfv3:
  - 1 area 10
- name: GigabitEthernet2            # from the seed: KEEP ipv4: dhcp (the management path)
  description: to R4 Gi5 - OSPF area 10 uplink (management)
  ipv4: dhcp                         # as the bootstrap set it (10.255.4.2 by reservation); unchanged
  ipv6:
  - 2001:DB8:2:46::2/64
  ospfv3:
  - 1 area 10
  negotiation: auto
  mop: [no mop enabled, no mop sysid]
- name: GigabitEthernet3
  description: to R7 Gi2 - RIPv2 and RIPng, R7's ZTP relay, 10.255.4.4/30
  ipv4: 10.255.4.5 255.255.255.252   # TRAP: remove the seed's no_ip_address: true
  ipv6:
  - 2001:DB8:2:67::1/64
  helper_addresses:
  - 10.255.0.10
  ripng:
  - RCN enable
  - RCN default-information originate
  negotiation: auto
  mop: [no mop enabled, no mop sysid]
  no_shutdown: true                  # the seed has no shutdown key on R6 (read 18:31)
flags:
  cdp run: true
  ipv6 unicast-routing: true
  lldp run: true
  netconf-yang: true                 # the profile's telemetry needs it
routing:
  ospf:
  - process: '1'
    networks:
    - network 10.255.1.16 0.0.0.0 area 10
    - network 10.255.4.0 0.0.0.3 area 10
    settings:
    - router-id 10.255.1.16
    - redistribute rip               # TRAP: the printed form of `redistribute rip subnets`
    - passive-interface Loopback0
  ospfv3:
  - process: '1'
    raw:
    - router-id 10.255.1.16
    - redistribute rip RCN include-connected
  rip:
    networks:
    - <r2's routing.rip.networks entry, copied as it stands>   # the fleet's one classful network
    settings:
    - version 2
    - passive-interface default
    - no passive-interface GigabitEthernet3
    - default-information originate
    - no auto-summary
  ripng:
  - name: RCN
services:
- service timestamps debug datetime msec
- service timestamps log datetime msec show-timezone
login:
- on-success log
```

**The design's pattern, as drafted:**
- RIP is redistributed into OSPF (and RIPng into OSPFv3), and R6 originates a default into RIP
  and RIPng. Nothing is redistributed back into RIP.
- R7 reaches everything by R6's default.
- R6's own default is the bootstrap's static route via 10.255.4.1 (distance 1), which stays;
  OSPF's E2 default from R4 arrives behind it with the same next hop.

---

## 5. R7's intent (draft, today's model)

Applied the same way: seed, then edits to the seed in place. Leave unchanged Gi1, Gi2's
`ipv4: dhcp` (the bootstrap's; 10.255.4.6 by Kea's reservation) and its DHCP client-id line, the
bootstrap's static default via 10.255.4.5 (as R6's holds, read 18:31; it stays preferred over
RIP's default from R6, distance 120, with the same next hop), the vty lines, SSH and the
account.

**Traps:** Gi3, the dot1Q parent, carries no address: **keep its `no_ip_address: true`**
(the device prints ` no ip address` on a parent without one, and dropping the key leaves that
line as residue on every plan). Remove only the seed's `shutdown: true`, and set
`no_shutdown: true` (the operator's correction, 2026-10-20). Gi3.10 is new, so the seed has no
entry for it; it has its address and no `no_ip_address`.

**VLAN 10** is a dot1Q subinterface (`GigabitEthernet3.10`, `encapsulation dot1Q 10`), so
VLAN 10 is on the wire and H5 tags it. The untagged fallback: put the address on Gi3 itself and
H5 on plain eth1; the NetBox VLAN then documents the segment only. **SLAAC:** IOS sends router
advertisements on an interface with a global IPv6 address unless suppressed, and the /64 is
autoconfigurable. No DHCPv6.

```yaml
interfaces:
- name: Loopback0
  description: mgmt identity
  ipv4: 10.255.1.17 255.255.255.255
  ipv6:
  - 2001:DB8:1::17/128
  ripng:
  - RCN enable
- name: GigabitEthernet2            # from the seed: KEEP ipv4: dhcp (the management path)
  description: to R6 Gi3 - RIPv2 and RIPng uplink (management)
  ipv4: dhcp                         # as the bootstrap set it (10.255.4.6 by reservation); unchanged
  ipv6:
  - 2001:DB8:2:67::2/64
  ripng:
  - RCN enable
  negotiation: auto
  mop: [no mop enabled, no mop sysid]
- name: GigabitEthernet3
  description: VLAN 10 trunk to H5
  negotiation: auto
  mop: [no mop enabled, no mop sysid]
  no_ip_address: true                # KEEP: the parent has no address
  no_shutdown: true                  # remove a seed shutdown: true if there is one (R6 had none)
- name: GigabitEthernet3.10
  description: VLAN 10 - H5, 10.70.10.0/24 (DHCP through Kea, SLAAC)
  encapsulation: dot1Q 10
  ipv4: 10.70.10.1 255.255.255.0
  ipv6:
  - 2001:DB8:70:10::1/64
  helper_addresses:
  - 10.255.0.10
  ripng:
  - RCN enable
flags:
  cdp run: true
  ipv6 unicast-routing: true
  lldp run: true
  netconf-yang: true
routing:
  rip:
    networks:
    - <r2's routing.rip.networks entry, copied as it stands>   # the fleet's one classful network
    settings:
    - version 2
    - passive-interface default
    - no passive-interface GigabitEthernet2
    - no auto-summary
  ripng:
  - name: RCN
services:
- service timestamps debug datetime msec
- service timestamps log datetime msec show-timezone
login:
- on-success log
```

10.70.10.0/24 sits inside the classful network the `network` statement above names, so RIP
advertises it, passive on Gi3.10 (no RIP toward H5). No `ip nat` on R7: H5's traffic is translated at R4 or R3.

---

## 6. H5

**Lab file `lab8-h5.clab.yml`:**
```yaml
name: lab8-h5
# Lab 8 step 8: H5 on VLAN 10 behind R7 (tagged), DHCPv4 through R7's helper, SLAAC for IPv6.
mgmt:
  network: clab-lab8-h5
  ipv4-subnet: 172.30.100.0/24
topology:
  nodes:
    h5:
      kind: linux
      image: ghcr.io/hellt/network-multitool    # the fleet's hosts' image
      mgmt-ipv4: 172.30.100.35
      binds:
        - configs/host-net-h5.sh:/etc/host-net-h5.sh
      exec:
        # VLAN 10 tagged on eth1, then DHCP on it the way h1 and h3 run it (its own script)
        - ip link add link eth1 name eth1.10 type vlan id 10
        - ip link set eth1 up
        - ip link set eth1.10 up
        - sh -c "nohup /etc/host-net-h5.sh > /tmp/host-net.log 2>&1 &"
    br-r7h5:
      kind: bridge
  links:
    - type: veth
      endpoints:
        - node: h5
          interface: eth1
          mac: aa:bb:cc:00:70:05
        - node: br-r7h5
          interface: h5-r7
```

**`host-net.sh` gains an `h5` case** (lab tooling, the operator's file, `configs/host-net.sh`).
It is a draft: VLAN 10 tagged, DHCPv4 on `eth1.10`, SLAAC on `eth1.10`, Docker's default routes
removed as for h1 to h4:
**Superseded (the operator, 2026-10-20 16:30):** the shared `host-net.sh` is NOT changed (it
lives at `~/labs/lab/configs/host-net.sh`, rcn-lab1's, for h1 to h4, and a slip there breaks
them on the next redeploy). H5 binds its own script, `~/labs/lab8/configs/host-net-h5.sh`:
```sh
#!/bin/sh
# H5 (Lab 8): VLAN 10 tagged on eth1, DHCPv4 through R7's relay as h1 and h3 run it, SLAAC
# for IPv6 (R7's RA on Gi3.10). Its own script: rcn-lab1's host-net.sh is never touched.
# Safe to re-run.
IF=eth1.10
V4="10.70.10."
log() { echo "host-net-h5: $*"; }
# 0. VLAN 10 (the lab file's exec makes it too; this is idempotent).
ip link show "$IF" >/dev/null 2>&1 || ip link add link eth1 name "$IF" type vlan id 10
ip link set eth1 up
ip link set "$IF" up
# 1. Docker's default routes off: eth0 stays reachable on its own subnet.
ip route del default dev eth0 2>/dev/null
ip -6 route del default dev eth0 2>/dev/null
# 2. IPv6 by SLAAC: accept R7's RA (2 accepts it even if forwarding is on).
echo 2 > /proc/sys/net/ipv6/conf/$IF/accept_ra 2>/dev/null || log "accept_ra not set"
echo 1 > /proc/sys/net/ipv6/conf/$IF/autoconf 2>/dev/null || log "autoconf not set"
# 3. IPv4: h1's retry loop, on eth1.10: until the address is in 10.70.10.0/24 with a default.
i=0
until ip -4 addr show dev "$IF" | grep -q "inet $V4" && ip route | grep -q "^default .*dev $IF"; do
  ip -4 addr flush dev "$IF" scope global 2>/dev/null
  udhcpc -i "$IF" -n -q -t 3 -T 3 >/dev/null 2>&1
  i=$((i+1)); [ "$i" -ge 60 ] && { log "no IPv4 lease in ${V4}0/24 after 60 tries"; break; }
  [ "$(ip -4 addr show dev "$IF" | grep -c "inet $V4")" -gt 0 ] || sleep 5
done
log "done: $(ip -4 addr show dev "$IF" | grep -o 'inet [0-9.]*') $(ip -6 addr show dev "$IF" scope global | grep -o 'inet6 [0-9a-f:]*')"
```
`mkdir -p ~/labs/lab8/configs` first (section 3's commands). Make it executable
(`chmod +x configs/host-net-h5.sh`), since the exec runs `/etc/host-net-h5.sh` directly.

---

## 7. NetBox, for step 10

**What Mercury writes on onboarding and sync:**
- R6's and R7's devices, at the site onboarding names;
- their interfaces;
- their IP addresses, from the captured configuration;
- cables only where LLDP and CDP see both ends (C1407's leaving half is Core 1.0).

**What the operator checks or adds in NetBox:**
- [ ] **R6 and R7 records** (status Active once Verify promotes them; C1421 if a Planned
      record was used).
- [ ] **Cables:**
  - R4 Gi5 to R6 Gi2;
  - R6 Gi3 to R7 Gi2;
  - R7 Gi3 to H5 eth1 (H5 as a device of role host, or the cable's B end left as a circuit
    note).
- [ ] **R7's site:** a VLAN group (scope: that site) holding VLAN 10 "H5", and the prefix
      10.70.10.0/24 with that VLAN, status Active. The VLAN group waits for step 10 (the
      operator, 2026-10-20).
- [ ] **Prefixes:**
  - 10.255.4.0/30 (R4 to R6) and 10.255.4.4/30 (R6 to R7), role "link";
  - 2001:db8:2:46::/64 and 2001:db8:2:67::/64;
  - 2001:db8:70:10::/64 with VLAN 10.
- [ ] **The relay-probe site** (read 2026-10-20):
  - device 18 `zr4-retired-18` (decommissioning; Gi1 to Gi3; 10.255.0.94/24);
  - the region and the VRF `relay-probe`;
  - device 20 `probe-zr6-retired-20` (decommissioning) is another leftover.

  Delete them or keep them as the probe's record. If deleted: the device, then its IP, then
  the site, region and VRF. Mercury does not react (as device 11's deletion showed).
- [ ] **C1424, the token's permissions to grant** (NetBox › Admin › Permissions, on Mercury's
      token's user):
  - view on `ipam.iprange`, `ipam.vlangroup`, `dcim.rack`, `dcim.location` and
    `circuits.circuit` (each read 403 on 2026-10-20);
  - add and change on `ipam.vlangroup` only if Mercury should write the VLAN group (not needed
    for Lab 8).

---

## 8. Lab 8's checks

Each is read through Mercury (a Show commands run, or Verify's own reads):
1. R4 an ABR for areas 0 and 10 (done 10-20: `show ip ospf`).
2. R6 adjacent to R4 (OSPF area 10, OSPFv3 area 10); R6 to R7 RIPv2 and RIPng
   (`show ip rip database`, `show ipv6 rip RCN database`).
3. The redistribution, as designed (RIP into OSPF one way, a default into RIP the other):
   - R4 holds 10.70.10.0/24 and 10.255.1.17/32 as O E2;
   - R7 holds 0.0.0.0/0 by RIP.
4. Every router's adjacency counts as at 10-20 07:0x, plus R4's and R6's new one:
   r1 2/2, r2 2/2, r3 6/4, r4 7/5, s3 2, s4 2.
5. R6 and R7 reachable from Mercury by their management addresses, and their loopbacks
   reachable by `ping` from r4.
6. H5 holds a Kea lease from 10.70.10.0/24 through R7's relay (the DHCP page).
7. **H5 reaches 8.8.8.8** (the operator, 2026-10-20). The lab itself reaches it: r4 and r3, 5 of
   5 each from their loopbacks (read 2026-10-20 09:11 UTC). H5's path is R7's RIP default, then
   R6's OSPF default from R4, then R4's NAT out of Gi2. Read it from H5 (the operator, on the lab
   host) and, through Mercury, `traceroute 8.8.8.8 source GigabitEthernet3.10` on R7.
8. IPv6: H5's SLAAC address in 2001:db8:70:10::/64. `ping 2001:DB8:70:10::1` from r4.
