# One lab file: R6 to R8, the Lab 9 switch and H5 to H7 in rcn-lab1 (plan)

**The operator's decision, 2026-10-20 ~19:05 UTC:** R6, R7, R8, the Lab 9 switch and H5, H6, H7
move into `rcn-lab1.clab.yml` as configless nodes on direct links, deployed with the whole lab in
one declared full redeploy. They wait unprovisioned until each is onboarded by ZTP. The per-device
labs and the Linux bridges go away. **This is the plan, for the operator's review. Nothing in it
has run.** Lab tooling: real hosts and paths are `<lab-host>`, `<nmas-host>` and `<home>`.

Everything below was read on 2026-10-20 between 19:00 and 19:20 UTC, read-only, unless it says
otherwise.

## 0. What the reads found, and what they change

1. **The startup files are NOT today's goldens, and the pre-flight passes them anyway (C1454,
   B).** `nmas-startup-source` builds each device's file from the network's newest EARNED
   baseline (`baseline/20261020T001016Z`), taking only the credential lines from the current
   golden. `nmas-startup-source --check --list Default` prints "9 of 9 pass", yet the same
   output shows a newer committed golden for three devices:
   - r2: 1 newer, its rotation at 01:06. Credentials only, which the build already takes.
   - r4: 1 newer, today's Gi5 (step 4).
   - s3: 1 newer, today's step 4b (the stale route removed).

   A redeploy now would boot r4 without Gi5 and s3 with the stale route again. The lab host's
   `configs/r4.cfg` is from 00:10 UTC and `configs/s3.cfg` from 10-13, matching that. **The
   fix is in the procedure:** Save All takes a new baseline (section 1, step B3). It also earns
   one only if every device is at its committed intent. The newest decision is "denied" because
   r6's deploy did not cover the network, not because anything is wrong. **The check is also
   made to refuse** (S, built before the redeploy, through the gate): a device whose golden has
   a commit after the baseline FAILS unless that commit only changed credentials.
2. **The startup files on the lab host are mode 0664 (C1453, C).** They hold every device's
   account secret and SNMP community. The sync writes them with the default umask and
   `rsync -a` keeps the mode, and its `configs.bak-*` copies have it too. Not a blocker; it is
   in the procedure below (B4).
3. **AutoInstall's patience in the case the plan needs is NOT measured.** What is measured (P.6
   M4): DHCP answered, TFTP not answered, so AutoInstall gave up after about 2.5 minutes and nine
   requests. What is also measured (P-M2d): with DHCP unanswered, it "keeps asking on both
   interfaces", for the probe's short run. **Unmeasured: DHCP unanswered for 30 minutes to days,
   then answered.** That is R7's wait (until R6 relays) and R8's (until Lab 9). Section 4
   measures it.
4. **A ZTP device must not boot before its reservation exists.** Kea's relayed subnet for R6
   (10.255.4.0/30) has a one-address pool. With no reservation, R6 takes the pool's address
   with no option 67, asks for default files the responder refuses, and gives up: the measured
   M4 case. So **Add device runs BEFORE the redeploy** for every device that boots then: R6 now,
   and R7 once its subnet exists.
5. **The Lab 9 switch cannot boot configless yet.** Its vIOS configless launch patch is Lab 9's
   0a, which is not built: the stock launcher answers the setup dialog and sends RETURN, which
   ended discovery on the C8000v, and it restarts a quiet VM. See section 3's option for it.
6. **Staggering works within one deploy.** Both images declare a Docker healthcheck, and the
   configless R6 reports `healthy` at its prompt today. So `stages: create: wait-for: {node: r4,
   stage: healthy}` holds each new router until its relay router is up. The fleet then boots
   as it did in the measured 23.8 minutes, and the new nodes boot after it.
7. **containerlab 0.79 offers no way to add a node to a running lab that this lab can use**
   (LAB8_LAB9_PLAN section 12). The one full redeploy is the only path, which is why everything
   joins in one redeploy.

**zt-probe:** nothing in the repository, the lab host's labs or the register is named
"zt-probe" (searched 19:10 UTC). The question is in section 8.

## 1. The redeploy procedure (lab/REDEPLOY.md, extended)

Times are UTC, with the operator's UTC−6 beside them.

**A. Before anything restarts: R6 out, the reservations in, the intent kept**

**The order run is docs/LAB8_MORNING_WALK.md section 1** (reviewed 2026-10-20): R7's subnet,
firewall step and Add device (A5 here) come BEFORE Retire (A3), each step there with its
expected output and its owner. The steps below are the reasons.

- **A1.** Deploy the pending release (3d26c7a2, C1421 and C1436; the docs since). Run job health
  afterwards. This is the first deploy since the sitting began, so it waits for the operator's
  word.
- **A2.** Keep R6's intent for re-use: its committed `host_vars/r6.yml` at HEAD goes to
  `lab/lab8/r6-intent.yml` in this repository, as lab tooling. It holds secret references,
  never values, and the publication test reads it. **Gi2's
  `ip dhcp client client-id ascii <serial>`** is the boot's serial, which vrnetlab makes again
  each boot. The kept file says so, and at re-use the NEW seed's Gi2 entry is kept and
  everything else comes from the file.
- **A3. Retire r6 in Mercury** (the lifecycle rule; Friday's rehearsal, done early).
  - Retire's heartbeat and telemetry steps write their delete files.
  - Then `bash <home>/python/Agentic_NMAS/scripts/host-steps/c1419-install-alert-rules.sh
    heartbeat` and the same with `telemetry` (sudo; the page prints the values). This is C1419
    install step's first real run, and it proves the removal path.
  - Retire releases R6's leases and removes its reservation (C1403).
  - NetBox: `r6-retired-<id>` is left Decommissioning, deleted by the operator if wanted.
- **A4. Add device › ZTP for R6** again: name `r6`, MAC `aa:bb:cc:00:04:06`. This recreates the
  reservation (10.255.4.2, option 67 `r6.cfg`, option 3 10.255.4.1). The Kea subnet
  10.255.4.0/30 stays. The pending row reads "reserved, not leased" until R6 asks.
- **A5. R7 too, and BEFORE A3** (the operator's correction, 2026-10-20): DHCP › Add a subnet for
  10.255.4.4/30 (pool 10.255.4.6 to 10.255.4.6, for ZTP), the firewall host step, and Add
  device › ZTP for `r7`, MAC `aa:bb:cc:00:04:07`. **The order is forced:** Add a subnet reads
  the relay from committed intent, and a subnet declared for ZTP is refused unless its relay is
  an interface, with a helper, of a device Mercury manages (`dhcp_subnets._plan_add`,
  `_declare_for_ztp`). R7's relay is r6 Gi3 (10.255.4.5), which exists only in r6's intent,
  and A3's Retire removes that intent. **Retire leaves both subnets in place:** its steps remove
  the device's reservations and leases, never a subnet (`retire.STEPS`). 10.255.4.0/30's relay
  is r4 Gi5, which stays. 10.255.4.4/30 keeps relay 10.255.4.5 in Kea while r6 is gone, and
  R6's redo puts that address back. A job-health or Needs attention row about a relayed subnet
  whose relay is in no intent may appear between A3 and R6's step 6; it is expected and named
  in the walk.

**B. The startup files: today's goldens, credentials handled**

- **B1. Save All** for Default (Actions › Save All). It captures r1 to r4 and s1 to s4 and earns
  `baseline/<now>` if each is at its committed intent. If it is denied, its record names the
  device and the lines; stop there and resolve that first.
- **B2.** The baseline commit fires the `baseline-earned` event, and `clab-sync.path` starts
  the sync. It builds each file from the new baseline with credentials from the current
  golden, sanitises it and copies it to `<lab-host>`. It takes a timestamped backup first, and
  commits each file in the lab's own repository there. Run by the service, it prints no diff.
  The full diff is printed only when the operator runs it by hand, in the operator's terminal.
  **Credentials:**
  - the files are built on `<nmas-host>` at 0600, copied over SSH and never printed;
  - the agent reads only the sync's result lines (each device's `REMOVED <device> <rule>` count,
    `sources.tsv`'s ok/refused rows, the commit outcome), never a file;
  - nothing is exported or shown, as the break-glass rules require;
  - the credentials are the ones Mercury holds now, which is what the check's "credentials
    current" proves.

  The lab repository's history, the backups and the files themselves all hold those
  credentials on `<lab-host>` (C1453).
- **B3. The pre-flight, read for its numbers:** `nmas-startup-source --check --list Default`.
  It must print `baseline <the new tag>` and, for every device, `0 newer` (r2 may show its
  rotation only if the new baseline predates it, which it will not), `credentials current:
  True`, `golden after last rotation: True` and `read by drift: True`. With the C1454 fix, any
  newer golden is a FAIL.
- **B4. On `<lab-host>`:** `chmod 600 <home>/labs/lab/configs/*.cfg` and the `configs.bak-*`
  copies (C1453). containerlab reads them as the lab's owner. The sync's umask fix is C1453's
  code change. Then read each file's date: r1 to r4 and s1 to s4 newer than B1. r5's stays the
  lab repository's (DECLARED-UNMAPPED).

**C. The lab host: the new file in place, the old labs out**

- **C1.** Copy `c8000v-launch-configless.py` from `<home>/labs/lab8/patches/` to
  `<home>/labs/lab/patches/` and compare sha256s. Write `configs/host-net-lab89.sh` (section 3)
  and the new `rcn-lab1.clab.yml`. Commit both in the lab's repository: it already has
  uncommitted changes to `rcn-lab1.clab.yml` and `configs/host-net.sh`, so commit those first,
  separately.
- **C2. Validate without deploying:** copy the file to `/tmp/check/` with `name: rcn-lab1-check`,
  then `containerlab deploy -t /tmp/check/rcn-lab1.clab.yml --dry-run`. In 0.79's code
  (`core/apply.go`), an initial deploy's dry run returns after parsing and planning, before
  creating anything. It parses the stages, interface aliases and MACs. Not run yet: read the
  output for "DryRun: true" and nothing created (`docker ps` count unchanged).
- **C3.** `containerlab destroy -t <home>/labs/lab8/lab8-r6.clab.yml --cleanup` (R6 is already
  retired in Mercury). Then `docker network ls | grep clab-lab8-r6`; if it is left,
  `docker network rm clab-lab8-r6`.
- **C4. Bridges, in this order:** `br-r6r7` and `br-r7h5` now have nothing attached. Check with
  `ip -br link show master br-r6r7` (empty) before `sudo ip link del br-r6r7`, and the same for
  `br-r7h5`. `br-r4r6` and `br-r2r8` still hold r4's and r2's ends until the redeploy; they are
  removed in E3.

**D. Pre-checks, then the window, then the redeploy**

- **D1. Time:** not within 75 minutes before 08:30 UTC (02:30), nor before 09:10 UTC (03:10).
- **D2. Memory and swap on `<lab-host>`:**
  - `free -g` shows at least 20 GiB available: 51 today, and the plan needs about 13 (section 5);
  - `vmstat 5 5` shows `si` and `so` at 0 in every row;
  - load, `st` (steal) and `gu` (guest) noted. At 19:06 the load was 13.5 on 24 vCPUs, `st`
    0 and `gu` 46: the routers' nested VMs, which is the lab running, not contention. (An
    earlier draft read the 46 as steal; the operator's own 18:14 vmstat showed `st` 0.)
- **D3. The hypervisor** (read-only): `free -g` shows at least 20 GiB available (50 today), and
  `uptime`'s load is noted against its 40 cores. VMs 201 and 202 are shut down (the
  operator's, for the redeploy and the build days): `qm list` shows them stopped.
- **D4. Before counts, through Mercury:**
  - each device's OSPF, OSPFv3 and BGP neighbour counts, from the adjacency reader (66 reports
    over 9 devices at 18:56);
  - Needs attention's rows;
  - Drift › Check now: 8 of 8 read.
- **D5. Declare the window** (REDEPLOY.md step 1), naming r1 to r4 and s1 to s4 (r6 is retired;
  r5 is unmapped), `--minutes 60 --new-host-keys --why "lab redeploy: rcn-lab1 one file,
  Labs 8 and 9 nodes added configless"`. 60 minutes still holds: the new nodes wait for the
  fleet's routers to be healthy, so the fleet's own boot is the measured 23.8 minutes.
- **D6. At once:** `cd <home>/labs/lab && containerlab deploy -t rcn-lab1.clab.yml --reconfigure`
  in tmux. It blocks while the stages wait, about 25 minutes, then the new nodes boot.

**E. Post-checks**

- **E1. The fleet** (REDEPLOY.md steps 3 to 5; STAGE2_SESSION_CHECKLIST section 4):
  - every device Answering on the Devices page;
  - Drift › Check now: 8 of 8 read, and none drifted, so each is at its intent (the goldens
    from B1);
  - the host keys accepted under the window, with one Needs attention row to acknowledge;
  - the neighbour counts equal D4's, device by device: r4 and r2 each have one more port up
    and no new neighbour, since R6 and R8 are configless;
  - no "restarted unexpectedly" row.
- **E2. "Verify" for a redeploy:** a deploy-free check that the network is what intent says. That
  is Drift's 8 of 8 clean plus E1's counts. No device-changing operation runs in the window.
- **E3. The old bridges:** `ip -br link show master br-r4r6` and `master br-r2r8` both empty,
  then `sudo ip link del br-r4r6` and `sudo ip link del br-r2r8`. `br-mgmt` stays.
- **E4. The new nodes:** each container `healthy` (`docker inspect`'s health only, no restart).
  The capture (section 4) shows R6's DISCOVERs leaving Gi2, Kea's lease to 10.255.4.2 and the
  fetch of `r6.cfg`. Mercury's pending row then advances to onboarding.

**Abandoned:** end the window at once (REDEPLOY.md, C1389).

## 2. R6 again, after the redeploy

R6 then follows Lab 8's steps 5.4 to 6 as today, from the pending row:

1. onboarding's Verify promotes it;
2. Seed intent…, then the kept intent (A2) applied as edits to the seed, keeping the new
   seed's Gi2;
3. deploy and Verify;
4. step 6's reads: R6 and R4 OSPF Full, s3's route to 10.255.1.16 as O IA;
5. the heartbeat re-measure and the C1419 install step for heartbeat, then
   `nmas-telemetry-rules` and the install step for telemetry. This is the install's first real
   run on the ADD path; A3's was the removal path, and the pair closes C1419.

The earlier "c1419 sequence for R6 now" is dropped: R6's rules would be removed at A3 within
the hour.

**Time:** today's R6 took about 2 hours from 5.3 to step 6's Verify, including the walk's
corrections. A redo from a kept intent should take about 1 hour: onboarding about 15 minutes
after the redeploy (6.3 min to boot alone, slower with the lab), then about 45 minutes for the
seed, deploy, Verify and the reads.

## 3. The new rcn-lab1.clab.yml

**Nodes** (mgmt addresses in the lab's 172.20.20.0/24, after the pattern routers .1x, switches
.2x, hosts .3x):

| Node | Kind | mgmt | Launch | Waits for |
|---|---|---|---|---|
| r6 | cisco_c8000v | 172.20.20.16 | configless patch, passthrough | r4 healthy |
| r7 | cisco_c8000v | 172.20.20.17 | configless patch, passthrough | r4 healthy |
| r8 | cisco_c8000v | 172.20.20.18 | configless patch, passthrough | r2 healthy |
| s5 (the Lab 9 switch; name proposed) | cisco_vios | 172.20.20.25 | **vIOS configless patch: 0a, not built** | r2 healthy |
| h5 | linux | 172.20.20.35 | `host-net-lab89.sh h5`: VLAN 10 tagged on eth1 | — |
| h6, h7 | linux | 172.20.20.36, .37 | `host-net-lab89.sh h6/h7`: untagged | — |

**Links** (direct; the c8000v's GiN is CLI GigabitEthernet N, and vIOS ports are four to a
slot):

| Link | Segment | MACs (pinned) |
|---|---|---|
| r4 Gi5 – r6 Gi2 | 10.255.4.0/30, R4 .1 relay | r6 Gi2 `aa:bb:cc:00:04:06` (Kea's reservation) |
| r6 Gi3 – r7 Gi2 | 10.255.4.4/30, R6 .5 relay | r6 Gi3 `aa:bb:cc:00:04:16`, r7 Gi2 `aa:bb:cc:00:04:07` |
| r7 Gi3 – h5 eth1 | VLAN 10 tagged, 10.70.10.0/24 | r7 Gi3 `aa:bb:cc:00:04:17`, h5 `aa:bb:cc:00:70:05` |
| r2 Gi4 – r8 Gi2 | 10.255.4.8/30, R2 .9 relay | **r8 Gi2 `aa:bb:cc:00:04:08` (proposed)** |
| r8 Gi3 – s5 Gi0 (CLI Gi0/1) | 10.255.4.12/30, R8 .13 relay | r8 Gi3 `aa:bb:cc:00:04:18`, **s5 Gi0/1 `aa:bb:cc:00:04:25` (proposed)** |
| s5 Gi1 (CLI Gi0/2) – h6 eth1 | VLAN 10 access, 10.80.10.0/24 | h6 `aa:bb:cc:00:80:06` |
| s5 Gi2 (CLI Gi0/3) – h7 eth1 | VLAN 10 access | h7 `aa:bb:cc:00:80:07` |

**s5's reservation key is not its port MAC.** The switch asks on VLAN 1's SVI, whose MAC comes
from the chassis base MAC, not from a port. 0a measures what s5 sends (hw-address and
client-id), and Kea's reservation is keyed on that.

**The switch: three options** (the operator's choice; the recommendation first):

1. **(recommended) This redeploy carries r6, r7, r8 and h5. s5, h6 and h7 join at ONE more
   declared full redeploy after 0a is measured,** before Lab 9's walk (10-30). Every shape in
   this redeploy is measured: the C8000v configless launch, and Linux hosts. R8 waiting from
   now to Lab 9 is the long version of section 4's measurement.
2. Build and measure 0a first (M; planned 10-22 or 10-23), then one redeploy with everything.
   This delays R6's redo, R7 and H5, which the Lab 8 build needs by Thursday 10-22.
3. s5 in the file now with the stock vIOS launcher and no startup file. It boots blank, and
   its launcher answers the setup dialog, which ends discovery, so it would not run ZTP.
   Changing that is 0a anyway, and it costs a redeploy.

**The diff against today's file** (r1 to r5, s1 to s4, h1 to h4, web and br-mgmt unchanged; the
two bridge nodes and their two links removed). The full proposed file and the hosts' script
are held for review outside this repository; the lab's own repository receives them at C1. The
added lines, condensed (the real file uses block style, as today's):

```yaml
    r6:
      kind: cisco_c8000v
      mgmt-ipv4: 172.20.20.16
      env: {CLAB_MGMT_PASSTHROUGH: "true"}
      binds: [patches/c8000v-launch-configless.py:/launch.py]
      stages: {create: {wait-for: [{node: r4, stage: healthy}]}}
    # r7 the same (.17, waits for r4); r8 the same (.18, waits for r2)
    s5:                                     # option 1: added at the next redeploy, after 0a
      kind: cisco_vios
      mgmt-ipv4: 172.20.20.25
      env: {CLAB_MGMT_PASSTHROUGH: "true"}  # 0a decides
      binds: [patches/vios-launch-configless.py:/launch.py]
      stages: {create: {wait-for: [{node: r2, stage: healthy}]}}
    h5:
      kind: linux
      mgmt-ipv4: 172.20.20.35
      binds: [configs/host-net-lab89.sh:/etc/host-net-lab89.sh]
      exec: ['sh -c "nohup /etc/host-net-lab89.sh h5 > /tmp/host-net.log 2>&1 &"']
    # h6 (.36) and h7 (.37) the same, with their own name
  links:
    - type: veth
      endpoints: [{node: r4, interface: Gi5}, {node: r6, interface: Gi2, mac: "aa:bb:cc:00:04:06"}]
    - type: veth
      endpoints: [{node: r6, interface: Gi3, mac: "aa:bb:cc:00:04:16"}, {node: r7, interface: Gi2, mac: "aa:bb:cc:00:04:07"}]
    - type: veth
      endpoints: [{node: r7, interface: Gi3, mac: "aa:bb:cc:00:04:17"}, {node: h5, interface: eth1, mac: "aa:bb:cc:00:70:05"}]
    - type: veth
      endpoints: [{node: r2, interface: Gi4}, {node: r8, interface: Gi2, mac: "aa:bb:cc:00:04:08"}]
    - type: veth
      endpoints: [{node: r8, interface: Gi3, mac: "aa:bb:cc:00:04:18"}, {node: s5, interface: Gi0, mac: "aa:bb:cc:00:04:25"}]
    - type: veth
      endpoints: [{node: s5, interface: Gi1}, {node: h6, interface: eth1, mac: "aa:bb:cc:00:80:06"}]
    - type: veth
      endpoints: [{node: s5, interface: Gi2}, {node: h7, interface: eth1, mac: "aa:bb:cc:00:80:07"}]
```

Removed: the nodes `br-r4r6` and `br-r2r8` and the links `["r4:Gi5", "br-r4r6:r4-r6"]` and
`["r2:Gi4", "br-r2r8:r2-r8"]`. With option 1, s5, h6, h7 and their three links wait for the
second redeploy.

**The hosts' script, `configs/host-net-lab89.sh`:** one script for H5, H6 and H7, each named on
its exec line. It retries DHCPv4 with no give-up: rcn-lab1's `host-net.sh` stops after 60 tries
(5 minutes), and these hosts wait for days. It notes every 60 tries that it is still waiting,
then takes IPv6 by SLAAC from the router's RA. H5 makes eth1.10 (VLAN 10 tagged), and H6 and H7
use eth1 untagged on s5's access ports. It replaces lab8's `host-net-h5.sh`, whose loop stopped
at 60 tries.

## 4. "Keeps asking", measured for free

While R7 and R8 wait after the redeploy, a capture on each uplink records every DHCP and TFTP
packet. On `<lab-host>` (sudo, read-only, no container touched), one per node in tmux:

```sh
sudo ip netns exec clab-rcn-lab1-r7 tcpdump -ni eth1 -w /var/tmp/r7-asks-%Y%m%d%H.pcap -G 3600 -W 72 \
  'udp port 67 or udp port 68 or udp port 69'
sudo ip netns exec clab-rcn-lab1-r8 tcpdump -ni eth1 -w /var/tmp/r8-asks-%Y%m%d%H.pcap -G 3600 -W 240 \
  'udp port 67 or udp port 68 or udp port 69'
```

- **What it answers:** DISCOVERs per hour, from the first until the lease. If they continue at a
  steady rate for hours, the wait model holds. If they stop, the time of the last one is
  AutoInstall's patience with DHCP unanswered, which is new evidence for P.6. A summary each
  morning: counts per hour, and the gap since the last packet.
- **The bound:** 72 hourly files for R7 (its lease comes within days), 240 for R8 (to Lab 9),
  each tiny.
- **If AutoInstall gives up:** a reload from the node's own console. That is allowed by the
  restart rule; containerlab and docker restart stay forbidden.
  - Attach to vrnetlab's console port and answer `no` to the dialog. Any input ends
    discovery, and the reload restarts it.
  - Then `reload` and confirm.
  - These are the operator's console steps, since the device is not yet Mercury's. Each is
    recorded in the walk's log with its time. A planned-restart window is not needed for a
    device Mercury does not hold, but the pending row says the device restarted.

## 5. Resources

Measured per node now: a C8000v holds about 4.05 GiB and 1.8 cores steady; a vIOS-L2 about
0.4 GiB and 0.8 to 1.2 cores; a Linux host under 10 MiB.

| | Memory | Steady CPU |
|---|---|---|
| Added by option 1 (r6, r7, r8, h5) | 12.2 GiB | about 5.4 cores |
| Freed (lab8-r6's R6, which r6 replaces) | 4.05 GiB | 1.8 cores |
| **Net, option 1** | **+8.1 GiB** | **+3.6 cores** |
| Later, s5, h6 and h7 | +0.4 GiB | +1 core |
| **All of the operator's list** | **about +12.6 GiB gross, +8.5 net** | **+4.6 cores** |

The operator's +14 GB is the gross figure, with a margin.

- **Memory:** the lab VM has 51 GiB available and the hypervisor 50. Both have room. There has
  been no swap.
- **CPU is the constraint, and the question is the hypervisor's:** the lab VM's load is 13.5
  on 24 vCPUs with no steal (`st` 0; `gu` 46 is its routers' nested VMs). The
  hypervisor's 40 cores also carry VMs 201 and 202 (the operator's, running at 19:15), which
  the operator shuts down for the redeploy and the build days. +3.6 to +4.6 cores of steady
  load is a further 15 to 20% of the lab VM; D3 reads the hypervisor's load beside its memory.
  s3 was CPU-starved once
  (C93). Watch the fleet's heartbeats and IP SLA after the redeploy. If heartbeats go missing,
  R8 (idle until Lab 9) is the first to leave, at the next redeploy.
- **All booting at once:** avoided by the `wait-for` stages (section 0, item 6). The fleet's
  nine VMs boot as measured, then r6, r7 and r8 together (r8 on r2, the others on r4). Three
  C8000v booting together on an idle fleet: about 6 to 10 minutes. `--max-workers` limits only
  how many containers are created at once, not the boots.

## 6. The walk and the rehearsal for this model

**Lab 8's walk from here** (LAB8_MORNING_WALK.md is rewritten to this after review):

1. A1 to A5, B, C, D, E (section 1): one sitting, about 3 hours.
2. R6's redo (section 2).
3. **Step 7, R7:** already reserved (A5) and asking since the redeploy (section 4's capture).
   - R6's step 6 intent includes the helper on Gi3, so R7's next DISCOVER is relayed.
   - Its onboarding runs from the pending row. No lab step: no `bridges.sh`, no lab file.
4. **Step 8, H5:** already running, retrying DHCP. Its lease arrives once R7's intent holds
   Gi3.10 and its helper. No lab step.
5. Steps 9 and 10 as written.

**Friday's rehearsal reset, no containerlab** (for R7 first, then R6):

1. **Retire** the device in Mercury. Its reservation is removed and its leases released.
2. **Add device › ZTP** again with the same MAC, so the reservation is back before it asks.
3. **From the device's console** (the operator; the device is no longer Mercury's): `write erase`,
   confirm, then `reload`, confirm. Do not save.
4. It boots with no startup configuration and runs AutoInstall, relayed as before. H5 keeps its
   loop and leases again once R7 is back.

**Unmeasured:** whether `write erase` and a reload give the same configless boot as a fresh
disk. The configless patch removed the image's install overlay with its saved config. After a
`write erase`, NVRAM is empty, so it should. The rehearsal's first reset measures it. If PnP
or AutoInstall then behaves differently, the fallback is the next declared full redeploy.

C1432's measurement (step 5b) stays planned on R6 before Friday's Retire.

## 7. Timing

**Now: 19:20 UTC (13:20).** The pieces:

| Piece | Size |
|---|---|
| C1454's check (S) through the gate | about 1 h |
| A1 to A5 | about 45 min |
| B1 to B4 | about 30 min |
| C1 to C4 | about 30 min |
| The redeploy and E | about 60 to 75 min |
| R6's redo | about 1 h |

- **Earliest safe window today:** the redeploy starting about 22:00 UTC (16:00), if the C1454
  check and A to C start at once. The fleet is back by about 23:00 UTC and R6 redone by about
  00:30 UTC (18:30). That ends well before the backup window (08:30 UTC).
- **Tomorrow:** any start from 09:10 UTC (03:10). Realistically from 14:00 UTC (08:00), with R6
  redone by about 18:00 UTC (12:00).
- **Recommendation:** tomorrow from 14:00 UTC. Today's sitting is still open (step 6 done, the
  deploy of 3d26c7a2 held), and a 3-hour sequence starting at 22:00 UTC runs into the evening.
  Lab 8's Thursday date holds either way: R7 and H5 need only R6's step 6, then their own
  onboarding.

**What moves in LAB8_LAB9_PLAN:**
- section 2's item 3 (R4's new link) is done by this redeploy;
- Lab 9's 0c (R2's new link) is done too, folded into this redeploy;
- section 10's lab-tooling list loses the per-device labs, bridges and `clab-r6`;
- section 11's item 10 (a re-add) becomes section 6's reset;
- section 12, the why, is rewritten to this decision;
- section 13 is withdrawn: the one file is the one description.

## 8. Open for the operator

1. The switch: option 1, 2 or 3 (section 3).
2. **zt-probe:** which experiment is it? Nothing in the repository or on the lab host is named
   so. If it is the `link-apply-mode: live` experiment section 12 named as untried, it was
   never planned to run.
3. The name `s5` and the MACs proposed for R8 and s5.
4. Today or tomorrow (section 7).
