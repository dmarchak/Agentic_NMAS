# Lab 8: the recording outline (Saturday 2026-10-24)

**Status: a draft for the operator, written 2026-10-21.** Friday's rehearsal
(docs/LAB8_REHEARSAL_WALK.md) proves the order. Anything the rehearsal shows wrong is corrected
here before Saturday.

**The handout asks the video for three things** (docs/LAB_REQUIREMENTS.md, Lab 8):
1. what happens when the devices are added;
2. how the automation framework is implemented and updated;
3. examples of the documentation.

The scenes follow the walk's order. The documentation the video points at is
docs/LAB8_DOCUMENTATION.md. Every figure said aloud is a measured one from docs/PITCH_METRICS.md
or docs/HOST_TUNING.md. A scene that depends on a fix not yet on the host is marked **(if
landed)** and is dropped, not faked, when it has not landed.

**Rules for the recording:**
- Nothing in 08:30 to 09:10 UTC (02:30 to 03:10 UTC−6).
- No Mercury update during the sitting.
- Sign in through the access proxy as a person, so every confirm records who.
- Durations are rough targets for the edit, not measurements. Waits (a boot, Verify's key settle)
  are cut in the edit, and the cut is said.

## Before recording (off camera)

- The walk's preconditions P1 to P9.
- R7, then R6, retired through Mercury's Retire (walk b1 to b5). Retirement is shown later, as
  a History row, not as a scene: the video is about devices being added.
- If the operator would rather show it, scene 3a below is a short Retire of R7.
- The recovery-ZTP test (walk a) is not recorded. It is a measurement for a later design.
- Show commands: the saved set "Lab 8 checks" exists (walk f).

## The scenes

| # | Screen | Action | Say (one or two sentences) | On screen afterwards | About |
|---|---|---|---|---|---|
| 1 | **Topology** | Open the map; select R4, then its link toward the empty port | "This is the course network, drawn from what the devices report. Lab 8 adds R6 behind R4 in OSPF area 10, R7 behind R6 over RIPv2, and a host on VLAN 10 behind R7, and they must configure themselves when they are connected." | the current fleet; R4's Gi5 up with no neighbour | 1:00 |
| 2 | **NetBox** (its own UI), IPAM › Prefixes; then Devices | Show 10.255.4.0/30, 10.255.4.4/30 and 10.70.10.0/24; **(if D2 chose Planned records)** R6 and R7 as Planned | "NetBox is the source of truth for devices and addresses. The new links and VLAN 10 are planned here first, and Mercury reads them; it writes to NetBox only through a previewed, confirmed import." | the prefixes; the Planned records | 1:00 |
| 3 | **DHCP › Subnets**; then **r4 › Intent** | Show subnets 256 and 257, marked ZTP and relayed; then R4's Gi5 with its helper address | "Each new link is a Kea subnet for zero-touch onboarding, relayed by the router in front of it. R4's relay toward R6 went in as an ordinary change: 12 lines, verified and saved." | the two ZTP rows, Held by Mercury; Gi5 in R4's intent | 0:45 |
| 3a | *(optional)* **r7 › Actions › Retire…** | The card: what Retire removes, what survives; confirm | "A device leaves only through Retire, which removes everything Mercury kept about it and frees its name. A new R7 inherits nothing from the old one." | "Retired"; the retired record | 0:45 |
| 4 | **Devices › Add device…** | ZTP: `r6`, IOS-XE, router, 10.255.4.2/30, its MAC, Gi2, Route option (3) the relay's own address; **Review the plan**; **Create r6** | "Adding a device is one decision. Mercury writes the DHCP reservation with its boot file and the relay as its only route, checks nothing on the segment can answer DNS, and commits R6's bootstrap intent. Nothing is sent to any device." | the review's address line; the result naming the reservation; the pending row | 2:00 |
| 5 | The lab host's console (LAB), then **r6's pending page** | Reload R6 from its console (a lab step, 10 seconds on screen); cut to the stages advancing | "In the lab, powering on a new router is a reload of a blank one. It asks for an address through R4, Kea answers with its reservation, and Mercury's TFTP responder serves its bootstrap, only to that address and only while it is pending." | `reserved_not_leased` → `leased_not_fetched` → `fetched_not_reached` → "Answering: ready to Verify" | 1:30 |
| 6 | **r6's pending page › Verify…** | The preview, then **Verify r6** | "Verify is Day 0's last step. Mercury signs in with the one-time password, replaces it with a device-generated secret, sends the monitoring profile, saves, commits the first golden and records R6 in NetBox. On Tuesday, from the first fetch to this point took 9 minutes 21 seconds, the key settle included." | the nine steps done; "onboarding: r6 verified and recorded in NetBox" | 2:00 |
| 7 | **r6 › Actions › Seed intent…**; then **Intent › Edit** | Seed and confirm; paste R6's stored Day 1 document; show "What a deploy would send"; commit | "Day 1 is the full service configuration. It was written as intent before R6 arrived, and the editor checks it and shows exactly what a deploy would send." | the editor's diff, additions only; the commit | 2:00 |
| 8 | **Devices › Add device…** | ZTP for `r7` behind R6 (10.255.4.6/30, Gi2, option 3 the relay's own address) | "R7 is added now, before R6's relay goes live, so its reservation is waiting when its first request arrives." | the reservation; R7's pending row | 1:00 |
| 9 | **r6 › Actions › Plan a deploy…** | The exact program; confirm by hash; the stepper | "This is the exact program, masked, bound to this hash. What is confirmed is what is sent. Verify comes back amber: OSPF to R4 is up, and RIP toward R7 is declared but cannot be up until R7 exists, so it is not shown green." | Verify FULL: OSPF 0 → 1, OSPFv3 0 → 1; RIP unmet, amber | 2:00 |
| 10 | **r7's pending page** (and, if it stopped asking, R7's console, LAB) | The stages advance as R6 relays; **Verify r7** | "R7 has been asking since it was powered on. On Wednesday it asked 310 times over 25 minutes 46 seconds; the moment R6's relay existed, Kea answered in 40 milliseconds." | R7 promoted and recorded in NetBox | 2:00 |
| 11 | **r7 › Seed intent…, Intent › Edit, Plan a deploy…** | R7's Day 1: one deploy **(if D3's template seed landed)**, else two | One deploy: "R7's Day 1 is one approved change, and Verify is green: RIP and RIPng are up both ways." Two deploys: "R7 takes two changes, because the template rendered a subinterface's address before its VLAN tag, which IOS refuses. The fix is shipped; this network takes it next." | Verify green; RIP 1/1, RIPng 1/1 | 2:00 |
| 12 | **DHCP › Leases**; then H5's shell (LAB) | H5's lease in 10.70.10.0/24; from H5, `ping 8.8.8.8`, `traceroute 8.8.8.8`, `curl` of the web server | "H5 leased its address through R7's relay and reaches the internet through R7, R6 and R4. The host is outside Mercury, so this last check is from its own shell." | the lease; 5 of 5; the path R7 → R6 → R4 → R5; "hello world from RCN" | 1:00 |
| 13 | **Show commands** | Run the saved set "Lab 8 checks" on r4, r6 and r7 | "Every check is read through Mercury: R4 is the border router for areas 0 and 10, R6 and R7 hear each other over RIP, and R7's networks reach R4 as OSPF external routes." | per check, the answers; r4's routes O E2 via R6; R6's RIP database holding R7's networks | 2:00 |
| 14 | **r6 › NetBox › Import into NetBox…**, then r7's; then NetBox's own UI | The dry run, **Import**; NetBox's device, interfaces, IPs and cables | "Onboarding recorded each device once. After Day 1, NetBox is brought up to the deployed intent through the same preview and confirm, with cables made only where both ends report each other over LLDP." | the import's card; R4–R6 and R6–R7 cables; **(if C1442, C1492 and C1494 landed)** every address on its interface and R7's VLAN 10 subinterface | 2:00 |
| 15 | **Topology** | The map with R6 and R7; select the R4–R6 and R6–R7 links | "The map draws R6 and R7 from LLDP, OSPF and RIP, not from what NetBox says, so it shows what is true." **(if C1487 landed)** "The single points of failure are the handout's design, accepted with a reason." | R6 and R7 on the map; **(if C1442 landed)** the links drawn as intended | 1:00 |
| 16 | **History › Timeline**, the last two days; open one line | The expansion in order: the retirement, Add device, the reservation, served, rotated, verified, Day 1, the imports; open a deploy's line | "History is the documentation that writes itself: every change, who made it, which operation, and its record. On Wednesday, R6's and R7's three Day 1 deploys sent 78 lines, each exactly as confirmed, each verified and saved, none rolled back." | the timeline; a receipt's detail | 1:30 |
| 17 | **Needs attention** | Read the rows left | "What remains is known and registered." Then name each row left by its finding: the amber deploy row (C1450), s3's heartbeat check, r1's adjacency to s4 (the host tuning, next scene). | the walk's end state (LAB8_REHEARSAL_WALK h3) | 0:45 |
| 18 | **docs/HOST_TUNING.md** (or a slide of its table); Grafana's fleet dashboard | The before and after | "Adding R6 and R7 made the lab stall every 8 to 12 minutes. The cause, measured: the emulated switches lose timer ticks under CPU contention, so s3's 10-second OSPF hello fired about every 23 seconds. Giving each switch its own CPU cut failed scrapes by 94% and OSPF drops by 86%, with no missed pings in the hour after. A renice was tried first and changed nothing, so it was reverted. It is not finished: two drops an hour remain." | the change-2 table | 1:30 |
| 19 | **Templates** **(if D3's template seed landed)** | `_common.j2` Current; the approval with who and when | "The framework is updated the same way it changes devices: a shipped template fix is measured against every device, brought in, and approved by hash before anything renders through it." | the row Current; the approval | 0:45 |
| 20 | **docs/LAB8_DOCUMENTATION.md** | Scroll the addressing and the Day 0/1/2 table | "Day 0 is zero-touch. Day 1 is one approved, verified change. Lab 9 moves that approval up front, before the device arrives." | the documentation | 0:30 |

**About 30 minutes as listed.** For a shorter cut, drop 3a and 19, merge 7 into 9, and keep
12's shell to its traceroute: about 24 minutes.

## What is said only if it is true on the day

- **"Add device created the link's subnet"** only if the operator removed the subnets and C1460
  ran on camera (rehearsal walk D1). Otherwise scene 3 shows the subnets as added by hand, and
  says that Add device will add them next.
- **"NetBox matches the deployed intent"** only if the import wrote every address and Gi3.10
  (C1442, C1492, C1494). Otherwise scene 14 shows what it wrote and names what it could not.
- **"Verify is green"** for R6 is never said: R6's Day 1 is amber by design until R7 exists
  (C1450).
- **No figure is rounded up or estimated.** The figures above are from docs/PITCH_METRICS.md
  sections 1, 2 and 2b (Tuesday's and Wednesday's runs, named as such), and docs/HOST_TUNING.md
  Phase 2. Saturday's own figures (its receipts, its fetch-to-promotion times) are read into
  docs/PITCH_METRICS.md after the recording. They are said on camera only where the screen shows
  them.
