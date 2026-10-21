# Lab 8: the network's expansion, documented

**DRAFT for the operator, written 2026-10-21. Not reviewed.** The course handout asks that "the
documentation is appropriate" (docs/LAB_REQUIREMENTS.md, Lab 8, objective 1c). This page is that
documentation's draft: what changed in the network, how the devices were added, what the source
of truth now holds, and the host tuning the expansion forced. Every figure is measured and
cited: docs/PITCH_METRICS.md (PM) and docs/HOST_TUNING.md (HT), by section. Nothing is
estimated. A fact no record holds yet is marked `[READ: …]` for the operator.

The records it is written from are kept by Mercury itself and can be opened again:
- **History** (every commit, deploy, onboarding, retirement and NetBox import);
- each device's **receipts**;
- **NetBox** (devices, IPAM, cables);
- **Topology** (drawn from what the devices report).

---

## 1. What changed

| Added | What it is | Role |
|---|---|---|
| **R6** | Cisco C8000v, IOS-XE 17.6 | area-10 router behind R4; RIPv2 and RIPng toward R7; the ZTP relay for R7's link |
| **R7** | Cisco C8000v, IOS-XE 17.6 | RIP router at the far site; VLAN 10's gateway and DHCP relay for H5 |
| **H5** | Linux host | on VLAN 10 behind R7; DHCPv4 through R7's relay, IPv6 by SLAAC |

The handout's topology: R6 attached to R4 in OSPF area 10, RIPv2 between R6 and R7, and H5 on
VLAN 10 behind R7 (docs/LAB_REQUIREMENTS.md).

```
  existing network (OSPF area 0, BGP to the ISP router)
        |
       R4  Gi5 10.255.4.1/30  -- the ABR for areas 0 and 10; relays R6's DHCP
        |      OSPF area 10, OSPFv3 area 10
       R6  Gi2 10.255.4.2/30 (DHCP, Kea reservation)   Loopback0 10.255.1.16
        |  Gi3 10.255.4.5/30  -- relays R7's DHCP
        |      RIPv2, RIPng "RCN"
       R7  Gi2 10.255.4.6/30 (DHCP, Kea reservation)   Loopback0 10.255.1.17
        |  Gi3.10 10.70.10.1/24, VLAN 10 (dot1Q) -- relays H5's DHCP
       H5  10.70.10.0/24 (Kea pool), 2001:db8:70:10::/64 (SLAAC)
```

The lab node r8 also exists, configless, for Lab 9. It is not in Mercury.

## 2. Addressing

From docs/LAB8_LAB9_PLAN.md section 4, as approved by the operator on 2026-10-20.

| Segment | IPv4 | IPv6 | Notes |
|---|---|---|---|
| R4–R6, OSPF area 10 | 10.255.4.0/30: R4 Gi5 .1 (the relay), R6 Gi2 .2 (reserved in Kea) | 2001:db8:2:46::/64: R4 ::1, R6 ::2 | A /30, not the lab's usual /31: a relayed Kea subnet needs a client address beside the relay's. Kea subnet id 256 |
| R6–R7, RIPv2 and RIPng | 10.255.4.4/30: R6 Gi3 .5 (the relay), R7 Gi2 .6 (reserved in Kea) | 2001:db8:2:67::/64: R6 ::1, R7 ::2 | Kea subnet id 257 |
| VLAN 10 at R7's site | 10.70.10.0/24: R7 Gi3.10 .1; Kea pool .100 to .200, router option .1 | 2001:db8:70:10::/64: R7 ::1; hosts by SLAAC | VLAN ID 10 again at R7's site, its own subnet (confirmed by the course instructor, 2026-10-20); no DNS option on the subnet |
| Loopbacks | R6 10.255.1.16/32, R7 10.255.1.17/32 | 2001:db8:1::16/128, 2001:db8:1::17/128 | .16 was the retired r6's; addresses are not identity |

**Management.**
- Mercury reaches R6 at 10.255.4.2 and R7 at 10.255.4.6, each on its Gi2. The address is leased
  by DHCP from a Kea reservation that ZTP wrote.
- The path is in band: Mercury → s3 → OSPF → R4 (→ R6 for R7).
- Each keeps the bootstrap's static default toward its relay (10.255.4.1 on R6, 10.255.4.5 on
  R7).
- ZTP and Kea's reservations are IPv4 only (C1245). The new links, loopbacks and VLAN 10 are
  dual-stack in intent, as the rest of the lab is.

## 3. Routing

| Protocol | Where | Configuration (from each device's committed intent) |
|---|---|---|
| OSPFv2 area 10 | R4 Gi5, R6 Gi2 and R6 Loopback0 | R4 is the area border router for areas 0 and 10. R6: `network 10.255.1.16 0.0.0.0 area 10`, `network 10.255.4.0 0.0.0.3 area 10`, router-id 10.255.1.16, Loopback0 passive |
| OSPFv3 area 10 | R4 Gi5, R6 Gi2 and R6 Loopback0 | `ospfv3 1 area 10` on each interface |
| RIPv2 | R6 Gi3, R7 Gi2 | version 2, passive by default, the link not passive, no auto-summary; R7 advertises 10.70.10.0/24 and its loopback |
| RIPng "RCN" | R6 Gi3, R7 Gi2, R7 Loopback0 and Gi3.10 | enabled per interface; R6 originates a default into RIPng |
| Redistribution on R6 | RIP into OSPF (`redistribute rip`, the form IOS-XE 17.6 prints for `redistribute rip subnets`), RIPng into OSPFv3 (`redistribute rip RCN include-connected`); a default originated into RIP and RIPng (`default-information originate`) | R7's networks reach the rest of the network as OSPF external routes. The rest of the network reaches R7 by R6's default. Nothing else is redistributed into RIP |
| Address translation | at R4 (and R3), whose NAT-PRIVATE list permits every RFC 1918 range | area 10's and VLAN 10's sources are translated there. R6 and R7 carry no NAT |

**R7's IPv4 default** is the bootstrap's static route via 10.255.4.5, kept by design, with the
same next hop as RIP's. R6's RIP default is present and loses to it. R7's IPv6 default is
RIPng's, from R6 (PM 2b).

**Measured, 2026-10-21 03:17:53 UTC through Mercury's read path (PM 2b):**
- R6 and R7 each name the other as their one RIP source.
- R6's RIP database holds 10.70.10.0/24 and 10.255.1.17/32 via 10.255.4.6.
- RIPng has one next hop each way. R6 installs 2001:DB8:1::17/128 and 2001:DB8:70:10::/64 from
  R7.
- R4 holds 10.70.10.0/24 and 10.255.1.17/32 as O E2, metric 20, via 10.255.4.2 on Gi5,
  advertised by 10.255.1.16 (R6).
- **Adjacencies (Prometheus):** r1 OSPF 5/5, OSPFv3 3/3; r2 the same; r3 BGP 2/2, OSPF 6/6,
  OSPFv3 4/4; r4 BGP 2/2, OSPF 7/7, OSPFv3 5/5 (one more of each, R6 on Gi5); r6 OSPF 1/1,
  OSPFv3 1/1; s3 OSPF 5/5; s4 OSPF 5/5. Each equals the reading before the expansion, apart
  from r4's added adjacency and r6's.
- **From r4's Loopback0, 5 of 5 each:** 10.255.1.16, 10.255.1.17, 2001:DB8:1::17 and
  2001:DB8:70:10::1.

**From H5** (operator-reported, PM 2b):
- a lease of 10.70.10.100 through R7's relay;
- a SLAAC address in 2001:db8:70:10::/64;
- `ping 8.8.8.8` 5 of 5, by the path R7 → R6 → R4 → R5 → 8.8.8.8;
- `curl` of the lab's web server returning "hello world from RCN";
- `ping 2001:4860:4860::8888` 3 of 3.

## 4. How the devices were added: Day 0, Day 1, Day 2

| Day | What | How it reaches the device | Lab 8 |
|---|---|---|---|
| **Day 0** | The management plane: hostname, a one-time account, the domain, the management address, SSH. Then the credential rotated, the first capture, the NetBox record and the monitoring profile | the bootstrap over TFTP, served by Mercury to the reserved address only; the rest over SSH at Verify | **automatic** once the device is added: ZTP, then onboarding's Verify |
| **Day 1** | The full service configuration: interfaces and addresses, routing, relays, the VLAN | over SSH, after the rotation, through the deploy path: the exact program previewed, confirmed by hash, applied, verified, rolled back on failure, recorded | **one approved, verified change** from a stored intent (two deploys for R7, below) |
| **Day 2** | Operating it: monitoring, heartbeat, IP SLA, saves, drift, Needs attention | the deploy path and Mercury's operations | built |

### 4.1 Day 0: ZTP through a relay

1. **The relay.** R4 Gi5 carries `ip helper-address` to Kea, deployed to R4 as an ordinary
   change on 2026-10-20 (12 lines, verified FULL, saved; PM 2). R6 Gi3 carries the same for R7's
   link, in R6's Day 1. Each link is a Kea subnet for ZTP onboarding (256 and 257), relayed by
   that interface. It carries no gateway or DNS option at subnet level.
2. **Add device › ZTP** (one preview, one confirm by hash, as a verified person):
   - Mercury stages a one-time credential and commits the device's bootstrap intent ("onboarding:
     r6").
   - It writes the Kea reservation and its record ("ztp: r6 reserved aa:bb:cc:00:04:06 ->
     10.255.4.2"). The reservation carries the hostname (option 12), Mercury's TFTP address
     (option 66), the file `<device>.cfg` (option 67), and option 3 as the relay's own address
     only. Relayed AutoInstall needs option 3 (docs/RELAY_PROBE.md), so the no-route rule (D4)
     allows exactly that, and never a DNS server.
3. **The device boots configless** and asks. The relay forwards the request to Kea, which
   answers with the reservation.
4. **Mercury's TFTP responder** serves the rendered bootstrap only:
   - to the reserved address;
   - for the file the reservation names;
   - while the device is pending.
   Each fetch is recorded as a reveal before anything is sent.
5. **Verify**, a preview and a confirm by hash. Mercury:
   - reaches the device;
   - rotates the one-time credential to a device-generated secret;
   - removes any read-write SNMP community;
   - sends the network's monitoring profile;
   - saves to startup;
   - commits the first golden;
   - records the device in NetBox;
   - promotes it into the inventory.

**Measured (PM 1):**

| | R6 (2026-10-20, behind R4) | R7 (2026-10-21, behind R6) |
|---|---|---|
| Add device: intent, then reservation | 16:53:58, 16:53:59 | 02:30:02, 02:30:03 |
| The request answered | lease 18:20:15 (operator-reported) | first OFFER 02:32:10.01, 40 ms after the request it answered; lease 02:32:10.09 |
| Bootstrap served | 18:20:55 to 18:21:01: 12 fetches in 6 s, each 1 block, 468 bytes | 02:32:50 to 02:32:59: 12 fetches in 9 s |
| Credential rotated | 18:29:13 | 02:41:06 |
| Promoted and recorded in NetBox | 18:30:16 | 02:42:08 |
| First fetch to promotion | 9 min 21 s | 9 min 18 s |

Each span includes Verify's 120 s key settle and the operator pressing Verify.

**R7 kept asking for 25 min 46 s:**
- 310 DHCP requests from 02:06:24, of which 309 went unanswered, because R6's relay did not yet
  exist;
- the 310th was answered in 40 ms;
- Mercury's own part, from the answered request to the lease, was 71 ms;
- from the lease to the first fetch, 40 s (PM 1).

**What a person did for R6** (PM 1, classed by docs/MANUAL_STEPS.md):
- 3 decisions: adding the device, confirming the subnet, confirming the Create;
- 4 labour steps: adding the link's subnet, the firewall host step, typing the address and MAC,
  pressing Verify;
- 1 lab step: starting the lab node.
Each labour step carries the finding that removes it.

### 4.2 Day 1: one approved, verified change

Day 1's intent was written before the device arrived:
- R6's is kept in the repository as `lab/lab8/r6-intent.yml`.
- R6's and R7's complete documents of 2026-10-21 are the operator's copies.

After Verify:
1. **Seed intent** records what the device runs as its intent.
2. The stored document replaces it. The seed's per-boot keys are kept: the management
   interface's DHCP client-id, the image's default lines.
3. One commit.
4. One deploy: the exact program previewed and masked, confirmed by its hash as a verified
   person, applied holding the device, verified, rolled back on failure, and recorded with a
   receipt.

**The deploys (PM 2):**

| Device, step | Receipt written (UTC) | Lines sent | Sent as confirmed | Verify | Rollback | Saved |
|---|---|---|---|---|---|---|
| r4, step 4 (Gi5 toward R6, area 10) | 2026-10-20 07:35:18 | 12 | yes | FULL: interfaces 5/5, routes 30/30, OSPF 6/6, OSPFv3 4/4, BGP 2/2 | none | yes |
| s3, step 4b (the retired r6's static route removed, a Mode B removal with its authorisation) | 2026-10-20 16:28:14 | 1 | yes | FULL: interfaces 9/9, routes 24 → 23, OSPF 5/5 | none | yes |
| r6, Day 1 (the redo after the one-file redeploy) | 2026-10-21 02:36:19 | 43 | yes | FULL: OSPF 0 → 1, OSPFv3 0 → 1; RIP and RIPng declared and not yet up (no R7 yet): amber | none | yes |
| r7, Day 1, deploy 1 | 2026-10-21 03:09:44 | 31 | yes | FULL, green: RIP 0 → 1, RIPng 0 → 1, routes 5 → 8 | none | yes |
| r7, Day 1, deploy 2 (Gi3.10's addresses and helper) | 2026-10-21 03:12:47 | 4 | yes | FULL, green: RIP 1/1, RIPng 1/1, interfaces 5 of 5 up, routes 8 → 10 | none | yes |

**Lab 8's routing in all** (PM 2b): 3 deploys, 78 lines, each sent exactly as confirmed, each
verified in full and saved, none rolled back.

Before s3's removal, three attempts were refused, sending nothing: the removal needed an
authorisation the preview had not asked for (C1434, PM 2). A refusal is part of the record.

**Why R7 took two deploys.** The template rendered a new subinterface's addresses before its
`encapsulation dot1Q`, which IOS refuses (C1478). The shipped template is fixed. The network
takes the fix when it brings in the shipped template (C1498).

### 4.3 Day 2: operating it

- **Monitoring:**
  - The monitoring profile (NTP, SNMP, syslog with Mercury's heartbeat, streaming telemetry,
    LLDP and IP SLA) reaches each device at Verify.
  - Each device's heartbeat rule is measured from its own arrivals and installed in Grafana.
    Its telemetry rules follow from its golden.
- **Every change** is a deploy with a receipt.
- **Save All** takes a baseline: every device's golden at once, earned only when every device
  matches its intent.
- **Drift** compares each device's running configuration with its golden.
- **Needs attention** lists what is wrong, with its action and how it clears.

## 5. The source of truth, updated

| Store | What the expansion wrote | Where to see it |
|---|---|---|
| **The network's git repository** (intent, goldens, templates) | per device: "onboarding: <d>" (the bootstrap intent and manifest entry), "credential: <d> rotated", the first golden, "onboarding: <d> verified and recorded in NetBox", "host_vars: seed <d> from the committed golden", the Day 1 intent commit, and the golden after each deploy, each commit naming who and which operation | History; each device's History and Intent tabs |
| **Kea** (owned by Kea, written through Mercury) | subnets 256 and 257 for ZTP, each relayed; the two reservations, recorded in `dhcp/ztp-reservations.yml` ("ztp: <d> reserved <MAC> -> <address>"); 10.70.10.0/24 for VLAN 10 | DHCP › Subnets, Reservations, Leases |
| **Receipts** | one per deploy: the program's hash, what was sent, Verify's checks, rollback, the save | each device's History; the deploy card |
| **NetBox** (devices, IPAM, cables) | R6's and R7's records from their first golden at Verify; then brought up to the deployed intent by **Import into NetBox…** (a preview and a confirm), with cables from both ends' LLDP | NetBox; each device's NetBox tab |
| **Monitoring** | Prometheus targets, generated from the inventory; heartbeat and telemetry rules | Monitoring; each device's Monitoring tab |
| **Topology** | drawn from what the devices report (LLDP, OSPF, BGP, RIP), never from NetBox's cables | Topology |

**NetBox's state now:** `[READ: NetBox › R6's and R7's records: interfaces, addresses, platform,
cables, after the last import]`. The operator's import on 2026-10-21 failed to write one
interface, r7's Gi3.10 (C1492). Three findings are open against what NetBox holds:
- **C1442:** the DHCP-leased management address lands on Loopback0, not Gi2, and the platform
  reads "IOS".
- **C1492:** a routed dot1Q subinterface (r7's Gi3.10) cannot be written.
- **C1494:** a retired record keeps the addresses the new device of the same name needs.
Until they are fixed, NetBox holds less than the deployed intent for R6 and R7, and Needs
attention says so.

**A retired name inherits nothing.** Before Lab 8, the old r6 was retired through Mercury's
Retire:
- its golden tags archived;
- its reservation, leases, rotation-policy membership, map place, heartbeat and telemetry rules
  and host key removed;
- its NetBox record renamed and set to Decommissioning.
The new R6, onboarded by ZTP under the same name, started with a new NetBox ID and none of the
old device's records. Members of that rule still open are C1476 and C1494.

## 6. The host, tuned (C1485)

**What stalled.** After the one-file redeploy that brought R6, R7 and r8 into the lab, the lab
stalled every 8 to 12 minutes:
- every SNMP scrape failed at once;
- r1 dropped OSPF adjacencies on its dead timer;
- pings were missed, and saves failed (HT, "Why").

**The cause, measured** (HT, Phase 1). The vIOS switches lose timer ticks under the lab VM's
CPU contention, so their clocks and protocol timers run slow.
- **Each switch's clock fell behind real time:** s1 685 s (about 0.92×), s2 708 s (0.92×), s3
  5,118 s (0.43×), s4 3,516 s (0.61×).
- **The switches keep time from the emulated timer (PIT).** Each one's timer thread injects
  about 1,000 ticks a second. The routers' timer threads are idle, because IOS-XE uses KVM's
  paravirtual clock.
- **The effect on OSPF:** s3's 10 s OSPF hello fired about every 23 s of real time, so a
  bunched loss passed r1's 40 s dead timer. r1's drops were only ever toward s3 and s4, the two
  slowest clocks.
- **The effect on management:** s3 is the management gateway. When it fell behind, its uplink's
  output discards rose, and every SNMP poll crossing it failed.
- **The correlation:** the failed scrapes tracked the lab VM's CPU pressure (r 0.56 to 0.58),
  not the host's NUMA balancing (r −0.03 to 0.22). Ruled out by measurement: KSM, memory
  watermarks, ZFS, interrupts, clocks, nested halt polling, Mercury's SSH logins (r −0.10 to
  0.07) and device polling.

**What was changed, one change at a time, each measured before and after with the same script**
(HT, Phase 2):

| Change | Before | After | Verdict |
|---|---|---|---|
| 1. The switches' emulator processes reniced to −5 | 03:17 to 03:47: 76 of 112 gauge steps below the fleet, 449 failed scrapes, 11 OSPF drops, 17 missed-ping transitions | 03:49 to 04:19: 60 of 112, 446 failed scrapes, 7 drops, 23 transitions | **No measurable gain; reverted** |
| 2. Each switch on a vCPU of its own (lab-VM CPUs 20 to 23), its timer thread with it; the routers confined to CPUs 0 to 19 | 97 minutes, scaled to an hour: 47% of gauge steps below the fleet, 669 failed scrapes, 14.8 OSPF dead-timer drops, 26.6 missed-ping transitions; s3's discards at most 26.9/s; s3's heartbeat gaps 562 to 830 s (median 774) | 04:38 to 05:38: **15 of 241 steps (6%)**, **38 failed scrapes (−94%)**, **2 drops (−86%)**, **0 missed pings**; discards at most 8.8/s; **gaps 569 to 623 s (median 604)** | **Kept: the largest gain measured** |

- **After change 2, Save All saved 10 of 10 at 05:13 UTC.** The same operation had failed on s3,
  s4 and r7 at 03:33, before the pinning (HT, Phase 2).
- **Change 2 made permanent** (HT, "Change 2 made persistent"):
  - The lab file declares each node's CPU set, and containerlab reapplies it on every deploy.
  - A systemd timer on the lab host pins the switches' timer threads every two minutes. They are
    kernel threads outside every container, and a redeploy makes new ones.
  - Its match is confirmed by behaviour: on 2026-10-21, s1 983 ticks/s, s2 1,001, s3 1,038, s4
    1,086; every router 0.
  - A read-only check reads PINNING HOLDS when all of it is in place.
- **Not yet at the success criteria** (two hours with zero OSPF drops, no gauge step below the
  fleet, no missed pings): 2 drops and 15 gauge steps remained in the hour after change 2, and
  the switches' clocks still run slow. The next levers, each measured the same way, are less
  work on s3 (its IP SLA probes, then its uplink's queue) and a planned host window (HT, Phase 3).
- **Ruled out by the operator:** removing routers, fewer router vCPUs, more lab-VM vCPUs, and
  mitigations off (HT, "Rules").

## 7. How the automation framework is built and kept honest

- **One way to change a device:** preview the exact program, confirm it by hash as a verified
  person, apply holding the device, verify, roll back on failure, record. Onboarding, Day 1,
  removals and retirement are all operations of that shape.
- **Intent and goldens live in git.** Templates render intent into configuration. A deploy sends
  only what the device lacks (merge-only), and a removal is a separate, reasoned choice.
- **The suite (PM 3, 2026-10-20):**
  - 12,910 tests collected;
  - line coverage 88.4% of the application code;
  - 2,806 of 2,914 automation functions (96.3%) reached by a unit test;
  - CI runs on every push, in 4 test shards and a coverage job;
  - the coverage ratchet only rises.
- **Found by the tool's own checks during Lab 8** (PM 3):
  - the redeploy pre-flight named three devices newer than their startup files (C1454);
  - Retire's guard refused an uncommitted manifest entry (C1468);
  - CI caught a test reading the wrong page (C1469);
  - Confirm refused a removal without its authorisation (C1434).

## 8. What is not done yet (each registered)

- **Day 1 is a separate step** (C1471). Lab 9 moves its approval up front (docs/DAY1_AUTOMATION.md).
- **Add device does not create the link's Kea subnet yet on the host** (C1460): a person adds it
  first (LABOUR).
- **NetBox lags the deployed intent** for DHCP-managed devices and for subinterfaces (C1442,
  C1492). A retired record keeps its addresses (C1494).
- **A deploy verified with intent unmet** shows as "done" on an amber card, and its row clears
  only by another deploy (C1450).
- **A managed ZTP device that boots blank** cannot be recovered without retiring it
  (docs/RECOVERY_ZTP.md, a design).
- **ZTP is IPv4 only** (C1245).
- **The host's stalls are reduced, not gone** (C1485).
