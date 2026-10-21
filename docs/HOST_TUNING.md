# Host and VM tuning log (C1485)

**Why:** since the one-file redeploy (2026-10-21 01:5x UTC) the lab stalls every 8 to 12
minutes. Each stall shows as every SNMP scrape failing at once, OSPF dead-timer drops on r1 Gi2,
missed pings and failed saves (C1485). The operator paused the labs for a tuning sprint
(2026-10-21 ~04:10 UTC): the server must stop stalling before the rehearsal, the recording and
Lab 9.

**Success:** 2 hours with zero OSPF dead-timer drops, no SNMP gauge step below 10, no missed
pings and no SSH auth timeouts. s3's heartbeat gaps should tighten toward its 300 s setting once
the host stops stalling.

**Rules (the operator, 2026-10-21):**
- One change at a time, each measured 60 minutes before and after with the same script
  (`stall_window.py`, read-only).
- Live and reversible changes first, each written with its revert command.
- Hypervisor writes are the operator's; lab-host writes need the operator's go.
- **Not doing:** router vCPU changes, removing routers, `mitigations=off`, a CPU purchase.

**The metrics, per window** (read through `<nmas-host>`):

| Metric | Source |
|---|---|
| SNMP gauge steps below the fleet (10) | Prometheus `count(up{job=~"cisco_8000v\|cisco_vios_l2"} == 1)`, 15 s steps |
| SNMP failed target-scrapes | Prometheus `sum(1 - up{...})` |
| OSPF dead-timer drops | Loki, the devices' syslog job, `"Dead timer expired"` |
| Missed-ping transitions | the app log, reachability's `answering=False` |
| SSH auth timeouts | the app log, `Authentication timeout` |
| s3 Gi1/1 output discards | Prometheus, `rate(ifOutDiscards[5m])` |
| s3's heartbeat gaps | Loki, its arrivals |

## Phase 1: the audit (read-only, 2026-10-21 03:37 to 04:10 UTC)

**Hardware:** Dell PowerEdge R630, BIOS 2.13.0 (2021-05-14).
- 2 × Xeon E5-2650 v3: 2 NUMA nodes, 10 cores and 20 threads each, 40 threads in all.
- 128 GiB DDR4-2133 in 6 of 24 slots.
- One NVMe ZFS pool (`vmdata`) holds every VM disk.
- `racadm` is absent, so the BIOS system profile is read in iDRAC.

**Guests:**

| Guest | State | Resources |
|---|---|---|
| VM 100, the lab | running | 24 vCPUs (`sockets 1`, `cores 24`, `cpu host`, `numa 1`), 80 GiB, balloon off, virtio-scsi-single with an iothread, no hugepages |
| VM 102, NMAS | running | 4 vCPUs, 16 GiB |
| LXC 101 (cloudflared), LXC 103 (minio-dr) | running | idle |
| VMs 201, 202, 203 | stopped | onboot off |

Nothing running can be stopped.

**The root cause the evidence points to (2026-10-21 04:24 to 04:35 UTC):**

**The vIOS switches lose timer ticks under the lab VM's CPU contention, so their clocks and
protocol timers run slow.**
- **No switch is NTP-synchronised** (stratum 16, "no reference clock"; a separate finding).
- **Every switch's clock has fallen behind real time since the redeploy:**

  | Switch | Behind real time | Rate, about |
  |---|---|---|
  | s1 | 685 s | 0.92× |
  | s2 | 708 s | 0.92× |
  | s3 | 5,118 s | 0.43× |
  | s4 | 3,516 s | 0.61× |

  s3's rate matches its heartbeat gaps of 755 to 830 s against 300 s.
- **Why only the switches:**
  - The switches keep time from the PIT. Each one's in-kernel PIT thread in the lab VM
    (`kvm-pit/<n>`) injects about 1,000 ticks a second and waits 2.5 to 3.4% of the time,
    averaging 24 to 33 µs a tick.
  - The routers' PIT threads are idle: IOS-XE keeps time with KVM's paravirtual clock.
- **How it shows:**
  - s3's 10 s OSPF hello fires about every 23 s of real time, so when tick loss bunches up a gap
    passes r1's 40 s dead timer. r1's dead-timer drops are only ever toward s3 (.23) and s4 (.24),
    the two slowest clocks.
  - s3 is the management gateway. When it falls behind, its Gi1/1 output discards rise and every
    SNMP poll crossing it fails.
- **The stalls track CPU contention inside the lab VM.** Against failed scrapes per 10 s over 25
  minutes:

  | Counter | r |
  |---|---|
  | Lab VM CPU pressure (PSI "some") | 0.56 to 0.58 |
  | Host CPU pressure | 0.31 |
  | Host NUMA migrations | −0.03 to 0.04 |
  | Host NUMA hint faults | 0.06 to 0.08 |
  | Host NUMA PTE updates | 0.14 to 0.22 |
  | Host memory pressure | −0.08 |

  There were no host compaction stalls in the window, so NUMA balancing is not supported as the
  cause.
- **The switches' vCPU threads** run 76 to 96% of real time and wait 1.7 to 3.2% (s3 96.3% and
  1.9%). Every node runs under KVM (`-enable-kvm`, `-cpu host`), with no TCG.

**Findings, ranked by evidence:**
1. **Host memory and CPU are split unevenly across the two sockets, with automatic NUMA balancing
   on.** This is real, but uncorrelated with the stalls (above), so it moves to Phase 3's binding.
   - Node 1 has 1.4 GiB free of 63 GiB; node 0 has 8.7 GiB free.
   - VM 100's memory sits 18.8 GiB on node 0 and 25.3 GiB on node 1, while a snapshot had 23 of
     its threads on node-0 CPUs and 11 on node 1.
   - `kernel.numa_balancing = 1`: scan period 1 to 60 s, 256 MiB per step.
   - Lifetime counters (32 days): 886 million pages migrated, 45 billion PTE updates, 323 million
     hint faults.
   - Function-call IPIs run at about 28,000 a second host-wide, the signature of remote TLB
     flushes.
   - **Correlation with the stall minutes:** pending, from the samplers (below).
2. **KVM's NX huge pages mitigation is on** (`nx_huge_pages = Y`). 9,676 of the guests' 2 MiB pages
   are split into 4 KiB pages (14,107 remain whole), and a recovery pass re-merges a slice every
   minute.
3. **Deep C-states:** C6 is enabled with a 133 µs exit latency; CPU 0 is in C6 about 65% of its
   uptime. C3 is already disabled, and C1E has a 10 µs exit.
4. **Ruled out, measured:**
   - KSM: `run 0`, `full_scans 0`, ksmd has used no CPU in 32 days.
   - Memory watermarks: node 1's free memory is 8.6 times its high watermark;
     `zone_reclaim_mode 0`; kswapd used about 2.6 minutes of CPU per node in 32 days.
   - ZFS: txg syncs every 5.1 s take 9 to 24 ms; the ARC holds 8.4 GiB at its 8 GiB cap with a
     90% hit rate; the scrub runs monthly.
   - IRQs: spread by MSI-X affinity; irqbalance is off on both hosts with no hotspot.
   - Clocks: governor `performance`, turbo on, 1.9 to 2.6 GHz under all-core load.
   - Nested halt polling in the lab VM: 0.08 CPU. On the host it is effectively off
     (`halt_poll_ns_grow 0`).
   - r5's container: its shim uses 0.1%, so C1354 is resolved.
   - Mercury's SSH logins against the failed scrapes per minute over 2 h: r = −0.10, 0.07 and
     0.03 at lags of 0, 1 and 2 minutes.
   - Device polling: on r2, IOSd is 5% over 5 minutes, of which IP SLA is 0.83% and SNMP
     0.24%.
5. **The C8000v data plane spins by design.** Cisco: data-plane cores "hot-spin", and it is
   "normal for Data Plane cores to show ~100% utilization even when traffic throughput is low".
   No setting to reduce it is documented. Each router takes 1.56 to 1.86 host CPUs; r8,
   configless, takes 1.76.
6. **The lab VM** is at 19.6 of 24 vCPUs (15.0 to 15.4 through 10-20, before r6, r7 and r8).
   Its own NUMA balancing is off, with one node, no compaction stalls and next to no memory
   pressure.

## Phase 2: one change at a time

| # | Change | Applied (UTC), by | Before | After | Verdict | Revert |
|---|---|---|---|---|---|---|
| 1 | Renice the switches' qemu (s1 to s4, all 16 threads) to nice −5 on `<lab-host>` | 03:48:16, the agent, on the operator's go | 03:17 to 03:47: 76 of 112 gauge steps below 10, 449 failed scrapes, 11 OSPF dead-timer drops, 17 missed-ping transitions, 0 SSH auth timeouts, s3 discards every minute (max 23.8/s), s3 heartbeat gaps 775 to 829 s | 03:49 to 04:19: 60 of 112 steps, 446 failed scrapes, 7 drops, 23 transitions, 0 timeouts, discards every minute (max 26.9/s), gaps 755 to 830 s | **No measurable gain:** the failed scrapes are unchanged and the missed pings rose. These were 30-minute windows (about three stalls each); later changes take 60. **Reverted at 04:24:46 UTC by the agent, on the operator's go;** all 16 threads read back at nice 0. |
| 2 | Each switch on a vCPU of its own inside the lab VM, on `<lab-host>`: s1 to s4's qemu (every thread) and each one's `kvm-pit` thread pinned to CPUs 20, 21, 22 and 23; every router's qemu (r1 to r8, every thread) confined to CPUs 0 to 19 | 04:37:34, the agent, on the operator's go; read back: s1 to s4 at 20 to 23 (4 threads each), the routers at 0 to 19, the PIT threads 964075, 964184, 964235 and 964044 at 20 to 23 | 02:47 to 04:24 (the operator's choice: the renice changed nothing), 97 minutes, scaled to an hour:<br>- 47% of gauge steps below 10 (108 an hour), minimum 1;<br>- 669 failed scrapes an hour;<br>- 14.8 OSPF dead-timer drops an hour;<br>- 26.6 missed-ping transitions an hour;<br>- 0 SSH auth timeouts;<br>- s3 discards every minute, max 26.9/s;<br>- s3 heartbeat gaps 562 to 830 s (spread 267, median 774) | 04:38 to 05:38:<br>- **15 of 241 steps (6%)**, minimum 3;<br>- **38 failed scrapes (−94%)**;<br>- **2 drops (−86%)**;<br>- **0 missed pings**;<br>- 0 timeouts;<br>- discards every minute, max 8.8/s;<br>- **gaps 569 to 623 s (spread 54, median 604)**.<br>Clocks from 04:32 to 05:39: s3 at about 0.50× (from 0.43), s4 0.66× (from 0.61), s2 0.92× (unchanged), s1 not read.<br>In the window: the operator's Save All at 05:13 (10 of 10 saved, where it failed on s3, s4 and r7 at 03:33) and NetBox import at 05:22 (NetBox writes only). | **Kept: the largest gain measured.** Not yet the success criteria: 2 drops, 15 gauge steps and the discards remain, and the switches' clocks still run slow, so s3's own load is the next lever (IP SLA, then `hold_queue`). | on `<lab-host>`: `for n in s1 s2 s3 s4 r1 r2 r3 r4 r5 r6 r7 r8; do p=$(docker top clab-rcn-lab1-$n -eo pid,comm \| awk '/qemu/{print $1}'); sudo taskset -a -pc 0-23 $p; done; for t in 964075 964184 964235 964044; do sudo taskset -pc 0-23 $t; done` (a redeploy also reverts it) | on `<lab-host>`: `for n in s1 s2 s3 s4; do for p in $(docker top clab-rcn-lab1-$n -eo pid,comm \| awk '/qemu/{print $1}'); do for t in /proc/$p/task/*; do sudo renice --priority 0 -p ${t##*/}; done; done; done` (a redeploy also reverts it) |

**Change 2 made persistent (the operator, 2026-10-21):**
- **The lab file declares it:** `lab/pinning/cpuset.diff`, for the operator's commit to the lab
  repo.
  - The `cisco_c8000v` and `linux` kinds get `cpu-set: "0-19"`, and s1 to s4 `cpu-set: "20"`
    to `"23"`.
  - containerlab reapplies it on every deploy.
  - It covers each container's whole cgroup: qemu and every thread, the launcher and the hosts'
    processes.
- **Committed by the operator** on the lab host: `33916b7` (11 lines added); the lab file's
  sha256 now begins `c23c5d4014d5`. It applies at the next redeploy, and the hand pinning holds
  until then.
- **It does not cover the PIT threads.** `kvm-pit/<n>` are kernel threads (parent `kthreadd`,
  cgroup root, measured), and a redeploy makes new ones. So the pinning is automatic: the
  operator installs it once with `lab/pinning/install.sh` (sudo, on the lab host).
  - `lab-pin-pit.timer` runs `pin-pit-threads.sh` every two minutes, idempotent, logging to the
    journal (`-t lab-pin-pit`).
  - **The match is not guessed.** The kernel names each thread `kvm-pit/<the qemu's pid inside
    its container>`, which two containers can share. Each qemu, in pid order, takes the
    `kvm-pit/<n>` thread with the lowest tid above its own pid that no earlier qemu took.
  - **A switch's match is confirmed by behaviour:** a switch's PIT ticks about 1,000 times a
    second, a router's none. A match that does not tick is not trusted, and every PIT thread
    then goes to the switches' set, logged.
  - **Measured on all twelve, 2026-10-21:** every qemu matched a distinct thread; s1 983
    ticks/s, s2 1,001, s3 1,038, s4 1,086; every router 0.
  - A switch's PIT thread goes to its own CPU, a router's to 0 to 19.
  - lab/REDEPLOY.md's step 5a goes once it is installed.
- **The check:** `lab/pinning/check-pinning.sh` is read-only, on the lab host, with its values
  in `lab/pinning/pinning.conf`. It checks four parts, one line each:
  - the timer is active and its last run succeeded;
  - the lab file declares each node's cpu-set;
  - each container applies it, and where its processes run (a switch's on its own CPU,
    everyone else's within 0 to 19), saying "applied by the container" or "by hand";
  - each PIT thread is on its node's CPUs, matched as the timer matches it.

  **Second run, 05:5x UTC, before the install and the redeploy:**
  - the timer LOST (not installed);
  - the lab file declares all (ok);
  - every node "by hand", its launcher and shell processes still on 0 to 23;
  - the four switches' PIT threads on their own CPUs, the eight routers' floating.

  The true state. It reads PINNING HOLDS after the install and the next redeploy.
  - **First run, 05:4x UTC:** the four switches ok (by hand). Every router and host LOST: the
    hand `taskset` pinned their qemu but not their launcher and shell processes, which the
    declared cpuset will. The routers' idle PIT threads LOST. Exit 1, as it should be until the
    redeploy.
- **Mercury cannot run the check.** The lab host is not Mercury's, and the product carries
  nothing lab-specific, so it is lab tooling. A generic "declared host checks" source in job
  health is C1495.

**The CPU budget for Lab 9's full lab on 24 vCPUs** (the operator's question, measured
2026-10-21 05:4x UTC):
- **Now** (`vmstat`): guest 69%, system 9%, user 3%, idle 20%, so about 19.5 of 24 busy.
- **Per node:**
  - a C8000v takes 1.56 to 1.86 host CPUs: its data plane always one full vCPU, plus its
    control plane;
  - a vIOS switch takes 0.76 to 0.96 of its own CPU;
  - the Linux hosts take about 0;
  - the lab VM's kernel (nested exits) takes about 2.2, and helpers and captures about 0.7.
- **Lab 9** (8 routers, 5 switches, 7 hosts and web):
  - routers about 13.6;
  - 5 dedicated switch CPUs (about 4.4 used);
  - kernel and helpers about 2.9;
  - **about 21 of 24 on average.**
- **The routers' pool:** with the switches on 19 to 23, the routers and the VM's OS share 0 to
  18, needing about 16.5 of 19 (87%) on average. That is enough on average and tight at peaks
  (a redeploy's boot storm, a capture, a Save All).
- **What to measure when s5 joins:** the stall script, and the lab VM's CPU pressure on the
  routers' CPUs. If that pressure tracks the routers' OSPF drops, the levers are Phase 3's
  binding, then more lab-VM vCPUs (ruled out by the operator for now).

**Candidates, in order of evidence:**
1. **Give each switch a vCPU of its own inside the lab VM.** This acts on the correlated variable
   for the devices that lose time. A lab-host write, with the operator's go.
   - Pin s1 to s4's qemu threads and their `kvm-pit` threads to lab-VM CPUs 20 to 23, one switch
     each.
   - Confine every router's qemu threads to CPUs 0 to 19.
   - Expected: the switches' clocks approach the 0.92× s1 and s2 already show, or better.
   - Cost: the routers' threads (about 15.6 CPUs of demand) share 20 vCPUs instead of 24.
   - Revert: `taskset -a -pc 0-23 <pid>` for every qemu in the lab.
2. **Real-time priority for the four switches' `kvm-pit` threads,** so tick injection never waits.
   - Apply: `chrt -f -p 1 <tid>`.
   - Revert: `chrt -o -p 0 <tid>`.
3. **Less work on s3, through Mercury** (device configuration: a preview and a confirm each;
   measured 2026-10-21 ~04:40 UTC).
   - **How s3 spends its CPU:** it routes the routers' management traffic to the NMAS in
     software, 63% CPU with 0% at interrupt level:
     - the vIOS NIC driver ("IOSv e1000") takes 11.1% and IP Input 3.4%;
     - about 200 pps leave on Gi1/1, and the queue there has dropped 85,832 packets since the
       redeploy.
   - **What crosses Gi1/1 (2-minute capture):** gRPC telemetry 116 pps (692 kbit/s, about 58%),
     SNMP 20 pps (about 10%), SSH, mostly reachability's probes, 13 pps.
   - **What longer intervals would save on s3:**
     - its own IP SLA probes (12.7%, its largest process), 10 s to 60 s: about 10.5%;
     - being polled by SNMP (7.9%), 1 minute to 2 minutes: about 4%;
     - forwarding the routers' telemetry (about 5%), 10 s to 30 s: about 3.3%.
   - Together these take s3 from about 63% to about 45 to 48%.
   - On the routers the same polling costs under 1% (r2: IOSd 5% in all).
   - **No vrnetlab launch change for the PIT:** QEMU's in-kernel PIT defaults to
     `lost_tick_policy=delay`, which keeps KVM's tick reinjection on (`hw/i386/kvm/i8254.c`), and
     vrnetlab does not override it. The ticks are reinjected, not discarded; `discard` would lose
     more time.
4. **The switches' NTP:** find why they do not synchronise. This corrects their wall clocks, not
   their timers.
5. **Automatic NUMA balancing off** (uncorrelated; kept for completeness).
   - Apply: `sysctl -w kernel.numa_balancing=0`.
   - Revert: `sysctl -w kernel.numa_balancing=1`.
   - Risk: none to data; pages stay where they are.
2. **NX huge pages off.**
   - Apply: `echo N > /sys/module/kvm/parameters/nx_huge_pages`.
   - Revert: `echo Y > /sys/module/kvm/parameters/nx_huge_pages`.
   - The write zaps every VM's shadow page tables, a pause of seconds.
   - Risk: a malicious guest could crash the host (iTLB multihit). The guests are the operator's
     own.
3. **C6 off.**
   - Apply: `for s in /sys/devices/system/cpu/cpu*/cpuidle/state4/disable; do echo 1 > $s; done`.
   - Revert: the same with `echo 0`.
   - Cost: more power and heat, and some turbo headroom.
4. **s3 and s4's qemu pinned to dedicated vCPUs inside the lab VM.** A lab-host write, with the
   operator's go.

## Phase 3: the planned window (prepared 2026-10-21 ~05:10 UTC)

**Conditional (the operator, 2026-10-21):**
- **Go or no-go** is decided after tonight's IP SLA and hold-queue measurements.
- **If the stalls are gone,** Phase 3 moves after Saturday's recording, as an efficiency change.
- **If they remain,** it runs as one planned window on Wednesday.

**The host's real layout** (`lscpu -e` and `node*/cpulist`, read 2026-10-21):
- **Node 0:** CPUs 0, 2, 4, …, 38 (20 threads, socket 0).
- **Node 1:** CPUs 1, 3, 5, …, 39 (20 threads, socket 1).
- **The hookscript** reads this at run time and never assumes it.

**The repair route, before the window** (CLAUDE.md, a change to the path needs an independent
repair route):
- The iDRAC virtual console is opened and tested before anything changes: log in, see the
  host's console.
- `/etc/default/grub` is saved in step 0.
- GRUB's menu keeps the previous kernel entry. If the host does not come up with the new
  command line, the operator edits the entry at the GRUB menu from the iDRAC console (`e`,
  remove the hugepage arguments, Ctrl-X), then puts the saved `grub` back and runs
  `update-grub`.

Everything here is the operator's to run on `<hypervisor>`, except where a row says the agent.
Nothing is changed before the window.

### 0. Save what will change (first, before anything else)

```
D=/root/phase3-$(date -u +%Y%m%dT%H%MZ); mkdir -p $D
qm config 100 > $D/qm-100.conf; qm config 102 > $D/qm-102.conf
cp /etc/pve/qemu-server/100.conf /etc/pve/qemu-server/102.conf $D/
cp /etc/default/grub $D/grub
sysctl kernel.numa_balancing > $D/sysctl.txt
```

The BIOS's current System Profile is read in iDRAC and written down. It cannot be read from
the host: `racadm` is absent, and dmidecode does not show it.

### 1. The BIOS system profile: Performance (the operator, in iDRAC)

- **The steps:** iDRAC › Configuration › BIOS Settings › System Profile Settings › System
  Profile = **Performance** › Apply › "At next reboot". The job runs during the host's reboot.
- **Why:** the host runs the OS-controlled profile (the governor `performance` in
  intel_pstate's passive mode). C6 is enabled with a 133 µs exit, and CPU 0 spends about 65% of
  its uptime in C6.
- **Expected:**
  - deep C-states and C1E off, turbo held, memory and uncore at full speed;
  - no exit latency on a vCPU wake;
  - more power and heat.
- **Rollback:** the profile written down in step 0, set back the same way.

### 2. 1 GiB hugepages on the host's kernel command line (GRUB)

- **The change, on `<hypervisor>`:** in `/etc/default/grub`, set
  `GRUB_CMDLINE_LINUX_DEFAULT="quiet default_hugepagesz=1G hugepagesz=1G hugepages=64"`, then
  `update-grub`.
  - The host boots with GRUB, not `proxmox-boot-tool`, which has no `proxmox-boot-uuids`.
  - It runs Proxmox 9.2.2.
  - Boot-time 1 GiB pages are spread across the two nodes, 32 each.
- **Why:** VM 100's 64 GiB backed by 1 GiB pages means far fewer TLB misses for its nested
  guests (the C8000vs and vIOS). Cisco recommends hugepage backing for C8000v hosts.
- **Expected:** fewer page walks. The pages are reserved at boot, so compaction (80,721 stalls
  in 32 days) cannot touch them.
- **Rollback:** the saved `grub`, `update-grub`, and a reboot. If the host does not boot: the
  repair route above.

### 3. VM 100: 2 sockets × 12 cores, each guest node bound to a host node, 64 GiB on hugepages

```
qm set 100 --memory 65536 --balloon 0 --sockets 2 --cores 12 --numa 1 --hugepages 1024 \
  --numa0 cpus=0-11,hostnodes=0,memory=32768,policy=bind \
  --numa1 cpus=12-23,hostnodes=1,memory=32768,policy=bind
```

- **Why:**
  - Today VM 100's memory sits 18.8 GiB on node 0 and 25.3 GiB on node 1, while most of its
    threads run on node 0, and automatic NUMA balancing keeps migrating against it.
  - Node 1 has 1.4 GiB free.
  - Bound, each guest node's memory is on one socket, and the guest's scheduler sees the two
    nodes.
- **vCPU affinity:**
  - `qm set --affinity` pins a whole VM, not a vCPU to a node.
  - Per-vCPU placement is a post-start hookscript, `lab/phase3/vcpu-pin-hookscript.sh`, written
    for review. It reads, at run time:
    - each guest node's vCPUs and its host node from the VM's own `numaN: cpus=…,hostnodes=…`
      lines;
    - the host node's CPU set from `/sys/devices/system/node/nodeH/cpulist`;
    - each vCPU's thread from QEMU's monitor (`info cpus`).
  - It pins every vCPU of a guest node to that node's whole CPU set, not one CPU each, and
    logs what it did to the journal.
  - It needs storage with `snippets` content, which the host has none of today.
  - **The operator installs it:**
    `qm set 100 --hookscript <storage>:snippets/vcpu-pin-hookscript.sh`. Revert:
    `qm set 100 --delete hookscript`.
- **VM 102 (NMAS) on node 0:**
  `qm set 102 --numa 1 --numa0 cpus=0-3,hostnodes=0,memory=16384,policy=bind`. Optional; it
  keeps it off VM 100's node 1.
- **Fit:**
  - Node 0: 12 + 4 = 16 of 20 threads; memory 32 (VM 100) + 16 (NMAS) + about 4 (ARC) + about
    3 (host) = about 55 of 64 GiB.
  - Node 1: 12 threads; memory 32 + about 4 + about 3 + the containers = about 40 GiB.
- **Ballooning:** VM 100 is already `balloon: 0`.
- **The disk:** the audit found nothing to change. VM 100's `scsi0` is a ZFS zvol on the NVMe
  pool (`vmdata`, 16K volblocksize) on virtio-scsi-single with an iothread, `discard=on`,
  `ssd=1`, the default cache (none) and aio (io_uring). txg syncs take 9 to 24 ms, and the ARC
  hit rate is 90%.
- **Rollback:** `qm set 100` back to the values in `$D/qm-100.conf` (`--memory 81920
  --sockets 1 --cores 24 --delete numa0,numa1,hugepages`), the same for 102.

### 4. Option (b): r6 and r7 boot from their goldens

- **The lab's launch patch** (`~/labs/lab/patches/c8000v-launch.py`, in the lab's own repo)
  gains an opt-in startup-only mode, `lab/phase3/c8000v-launch-startup-only.diff`. With
  `NMAS_STARTUP_ONLY=true`, the day-0 ISO holds exactly the node's startup-config and not
  vrnetlab's bootstrap.
  - r4's golden carries that bootstrap (`vrf definition clab-mgmt`, Gi1 in the VRF, its
    routes, `restconf`), and r6's and r7's do not. Booted with the bootstrap, they would come
    up with lines their intent does not hold.
  - r1 to r5 are unchanged (the variable is absent).
  - The lab repo's commit is the operator's.
- **The lab file** (`rcn-lab1.clab.yml`), r6 and r7 only:
  - the bind goes from `patches/c8000v-launch-configless.py` to `patches/c8000v-launch.py`;
  - `env` adds `NMAS_STARTUP_ONLY: "true"`, and `CLAB_MGMT_PASSTHROUGH` stays;
  - `startup-config: configs/r6.cfg` (`configs/r7.cfg`) is added;
  - the `stages` block is removed: they DHCP through their relays and retry, and the stages
    delay every node's management link (C1475).

  r8 is unchanged (configless until Lab 9).
- **The startup sync's map** (`data/lab_targets/Default.tsv` on `<nmas-host>`, the
  operator's):
  - r6 moves from `labs/r6/configs r6` to `labs/lab/configs default` (C1473's cause);
  - r7 is added the same way (`r7 labs/lab/configs default <user>@<lab-host> cisco_iosxe`);
  - a `# DECLARED-UNMAPPED r8 default configless by ZTP until Lab 9` line is added.
- **Done before the window (2026-10-21):**
  - **Save All:** 10 of 10 saved at 05:13 UTC, `baseline/20261021T051351Z` (0fa9a2385e), the
    first baseline holding r6 and r7. The same operation failed on s3, s4 and r7 at about
    03:33, before the pinning.
  - **The pre-flight** read "0 newer" for all 10. s4 failed only "golden after its last
    rotation", C1472's false failure, fixed in the commit that carries this section.
  - **The dry ISO generation,** on the operator's go, at 05:13 UTC:
    - it ran in `vrnetlab/cisco_c8000v:17.06.01a` (r6's own image), with no network, removed
      after;
    - the stand-in was r6's golden as `nmas-config-read` masks it (250 lines);
    - **startup-only:** the ISO's config is 250 lines, identical to the startup-config, with
      no clab-mgmt VRF, `restconf` or clab-mgmt route;
    - **the standard launch** (the control): 292 lines, vrnetlab's 42-line bootstrap added,
      the clab-mgmt VRF, `restconf` and its route among them.

### 5. The run sheet (outside 08:30 to 09:10 UTC)

| # | Step | Who | Time |
|---|---|---|---|
| 0 | The iDRAC virtual console opened and tested (the repair route); step 0's saves; the layout read (`lscpu -e`, `node*/cpulist`) and written beside the hookscript's log | operator; the agent reads the layout | 10 min |
| 1 | Save All, all 10 green, with the gauge steady (not in a stall) | operator | 10 min |
| 2 | Pre-flight: `nmas-startup-source --check --list Default`, "0 newer" and every fact passing, for every device | agent | 2 min |
| 3 | The startup sync with the new map: r6 and r7 written to `labs/lab/configs`, read back | agent (host) | 3 min |
| 4 | A break-glass export | operator | 2 min |
| 5 | The BIOS profile staged in iDRAC (at next reboot); GRUB edited, `update-grub`; `qm set` for 100 (and 102); the hookscript installed | operator | 10 min |
| 6 | A planned-restart window declared for every device | operator | 1 min |
| 7 | Shut down VM 100 and VM 102 (`qm shutdown`), then reboot the host. The BIOS job runs on the way | operator | 10 to 15 min (an R630's POST) |
| 8 | Read back: the profile in iDRAC, `/proc/meminfo` HugePages_Total 64, `numastat` 32/32, VM 100's `qm config`, the hookscript's journal lines | agent | 5 min |
| 9 | Start VM 102 (Mercury), then VM 100; the redeploy with the new lab file (lab/REDEPLOY.md) | operator | 15 to 20 min (the C8000vs boot) |
| 9a | The CPU sets for the 2 × 12 layout (see below), set in the lab file before the redeploy: a lab-repo commit after `33916b7` (the file's sha256 at 33916b7 begins `c23c5d4014d5`), with `pinning.conf` set to the same values | operator (lab file and conf); agent (check) | 5 min |
| 10 | E checks: every device answering, the adjacency counts as at D4, r6 and r7 at their goldens (drift clean), the heartbeat and telemetry rules; `check-pinning.sh` reads PINNING HOLDS (the timer active, the file declaring, each container "applied by the container", each PIT thread on its node's CPUs) | agent | 15 min |
| 11 | 2 hours measured against tonight's final numbers | agent | 2 h |

**The outage:** Mercury is down about 15 to 20 minutes (host reboot to VM 102 up). The lab is
down about 45 to 60 minutes, from the shutdown to the E checks passing.

**The CPU sets for the 2 × 12 layout (step 9a).** Inside VM 100, guest vCPUs 0 to 11 are node 0
(host socket 0) and 12 to 23 node 1 (socket 1).
- **The switches, one per CPU and spread across the two sockets:**
  - s3 (the management gateway) on 11, node 0;
  - s4 on 23, node 1;
  - s1 on 10, node 0;
  - s2 on 22, node 1;
  - s5 (Lab 9) on 21, node 1.
- **Routers and hosts:** `0-9,12-20`.
- **Physical cores:** the hookscript pins each guest node's vCPUs to its host node's whole set,
  so a switch's vCPU is on its own socket but not alone on a physical core. Giving s3 and s4 a
  physical core each means pinning their guest vCPUs (11 and 23) to one hyperthread pair each,
  and keeping the others off both siblings. It is a change to the hookscript, measured after.
- **Verified after the redeploy:** `check-pinning.sh` with `pinning.conf` set to these values,
  and the hookscript's journal lines.

### 6. Live tonight instead?

- **1 GiB hugepages:** no. They are reserved at boot, and a runtime allocation on a host with
  80,721 compaction stalls behind it would fail or stall.
- **NUMA binding and the 2-socket topology:** no. Both need VM 100 restarted.
- **The BIOS profile:** no. It needs a reboot.
- **C6 off:** live, queued after `hold_queue`, only if the switches' clocks still lag.
- **Automatic NUMA balancing off:** live, but uncorrelated with the stalls; not queued.
