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
| 1 | Renice the switches' qemu (s1 to s4, all 16 threads) to nice −5 on `<lab-host>` | 03:48:16, the agent, on the operator's go | 03:17 to 03:47: 76 of 112 gauge steps below 10, 449 failed scrapes, 11 OSPF dead-timer drops, 17 missed-ping transitions, 0 SSH auth timeouts, s3 discards every minute (max 23.8/s), s3 heartbeat gaps 775 to 829 s | 03:49 to 04:19: 60 of 112 steps, 446 failed scrapes, 7 drops, 23 transitions, 0 timeouts, discards every minute (max 26.9/s), gaps 755 to 830 s | **No measurable gain:** the failed scrapes are unchanged and the missed pings rose. These were 30-minute windows (about three stalls each); later changes take 60. **Reverted at 04:24:46 UTC by the agent, on the operator's go;** all 16 threads read back at nice 0. | on `<lab-host>`: `for n in s1 s2 s3 s4; do for p in $(docker top clab-rcn-lab1-$n -eo pid,comm \| awk '/qemu/{print $1}'); do for t in /proc/$p/task/*; do sudo renice --priority 0 -p ${t##*/}; done; done; done` (a redeploy also reverts it) |

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
3. **The switches' NTP:** find why they do not synchronise. This corrects their wall clocks, not
   their timers.
4. **Automatic NUMA balancing off** (uncorrelated; kept for completeness).
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

## Phase 3: one planned host reboot (designed, not scheduled)

- BIOS system profile set to Performance (read it first in iDRAC).
- VM 100 as `sockets 2`, `cores 12`, its guest NUMA nodes bound to host nodes 0 and 1, vCPU
  affinity to match.
- VM 100 at **64 GiB** (32 per node), backed by 1 GiB hugepages (the operator's choice (a),
  2026-10-21).
  - Inside the VM 44 GiB is available today, so 64 GiB leaves about 28 GiB of headroom.
  - Node 0 then holds about 55 GiB: 32 for VM 100, the NMAS VM's 16, about 4 of ARC and about 3
    for the host.
  - Node 1 holds about 40 GiB.
- Ballooning is already off on VM 100. The disk tuning has nothing to change: an iothread is
  already set, and txg syncs take 9 to 24 ms.
- Then the full redeploy with r6 and r7 booting from their goldens (option b), Save All green
  on all 10, the pre-flight's "0 newer" and a fresh break-glass export. Then 2 hours measured.
