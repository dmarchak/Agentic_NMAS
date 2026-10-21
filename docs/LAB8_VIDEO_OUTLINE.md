# Lab 8: the recording outline (Saturday 2026-10-24)

**Status: revised 2026-10-21 (~16:3x UTC) after the operator's review, against what the host
runs (f14bd314, with ed58d33e to follow: C1442, C1450, C1460 part 1, C1476, C1477, C1479,
C1487, C1489, C1492, C1494, C1499, C1504 and C1506 are deployed or deploying; D3's template seed
is taken; P5, s3's IP SLA Retry, is done).** Friday's rehearsal (docs/LAB8_REHEARSAL_WALK.md)
proves the order and is recorded (its step i). Anything the rehearsal shows wrong is corrected
here before Saturday.

**The handout asks the video for three things** (docs/LAB_REQUIREMENTS.md, Lab 8, quoted there
as given). Where each is answered:

| The handout's ask | Scenes |
|---|---|
| What happens when the devices are added | 3 to 15: the subnet, Add device, the boot and fetch, Verify, Day 1, the lease, the checks, NetBox, the map |
| How the automation framework is implemented and updated | 1b (the parts; intent and goldens in git; CI's gate in 4 shards, the coverage ratchet, the gated deploy), 7–9 (intent committed, then the exact program), 16 (History: every change and who), 19 (a shipped template fix brought in and approved by hash) |
| Examples of the documentation | 20 (docs/LAB8_DOCUMENTATION.md: addressing, routing, Day 0/1/2), 2 and 14 (NetBox, the source of truth), 15 (Topology, drawn from the devices), 16 (History, the record that writes itself), and every screen's "How does this work?" page (shown once, in 4) |

**The length.** docs/LAB_REQUIREMENTS.md sets no limit for Lab 8's video (it names the three
asks and the due date, Mon 2026-10-26, only). The target is about 18 to 20 minutes: the table
below sums to **19:45**. Durations are targets for the edit, not measurements.

**Marks:**
- **live**: recorded and kept at speed.
- **time-lapse**: recorded whole, played fast in the edit, with the speed shown on screen (for
  example "×8"). A wait is never cut silently: it is time-lapsed or the cut is said.
- **cut**: done off camera, or recorded and left out. A cut step's result may still appear in a
  later scene (History, Needs attention).

**Rules for the recording:**
- Nothing in 08:30 to 09:10 UTC (02:30 to 03:10 UTC−6).
- No Mercury update during the sitting.
- Sign in through the access proxy as a person, so every confirm records who.
- No weekdays said: "in the first run" (2026-10-20, R6), "in the second run" (2026-10-21, R6's
  redo and R7).
- Finding numbers are shown on screen as a caption, never read aloud.
- Nothing on screen shows a bootstrap's contents, a one-time password, a console loading a
  configuration, or an unmasked program (the rehearsal's step i lists the frames that did, and
  how Saturday avoids each).

## Before recording (off camera)

- The walk's preconditions P1 to P9, P3 including the branch's NetBox site (D9).
- **R7, then R6, retired through Mercury's Retire** (walk b1 to b5). Retirement is shown later,
  as a History row, not as a scene: the video is about devices being added.
- **After each Retire, a `write erase` on its console** (R7's, then R6's; LAB), so each boots
  configless at its reload on camera. No reload off camera: the reload is in scenes 5–6 and 7–9.
- Subnet 257 (R7's link) removed (walk b1a), so Add device creates it on camera.
- The recovery-ZTP test (walk a) is not recorded. It is a measurement for a later design.
- Show commands: the saved set "Lab 8 checks" exists (walk f).

## The scenes

| # | Mark | Screen | Action | Say (one or two sentences) | On screen afterwards | Target |
|---|---|---|---|---|---|---|
| 1 | live | **Topology** | Open the map; select R4, then its link toward the empty port | "This is the course network, drawn from what the devices report. Lab 8 adds R6 behind R4 in OSPF area 10, R7 behind R6 over RIPv2, and a host on VLAN 10 behind R7, and they must configure themselves when they are connected." | the current fleet; R4's Gi5 up with no neighbour | 0:45 |
| 1b | live | **How the framework is built**: a one-slide diagram (Mercury, Kea and its TFTP responder, NetBox, the network's git repository, containerlab's lab); then the config repository's commit list; then the GitHub Actions run for the running commit; then **Settings › Installation** | Point at each part once; open the latest Actions run (4 test shards, the coverage job, all green); then Installation's running commit and its Update button | "Mercury holds the intent and the golden configs in git, renders them through templates, and is the only path to the devices. Kea and Mercury's TFTP responder do zero-touch onboarding; NetBox is the source of truth for devices and addresses; containerlab runs the lab. Mercury itself is updated the same careful way: every push runs more than 12,900 tests in four shards and a coverage job whose ratchet only rises, and the host installs only a commit whose CI run passed." | the Actions run green; Installation naming the running commit | 1:30 |
| 2 | live | **NetBox** (its own UI): IPAM › Prefixes; then Organization › Sites › Branch; then Devices | Show 10.255.4.0/30, 10.255.4.4/30 and 10.70.10.0/24; the Branch site with its VLAN group and VLAN 10; R6 and R7 as Planned in Branch | "NetBox is the source of truth for devices and addresses. R6 and R7 are planned here as Planned records, in a site of their own for the branch, and Mercury reads them when each is added. These records were made by hand in NetBox: Mercury cannot plan a device or a site yet." | caption: "Made by hand in NetBox: C1447, C1448, C1515"; the Planned records | 0:45 |
| 3 | live | **DHCP › Subnets**; then **r4 › Intent** | Subnet 256 (R6's link), marked ZTP and relayed; no subnet for R7's link yet; then R4's Gi5 with its helper address | "Each new link is a Kea subnet for zero-touch onboarding, relayed by the router in front of it. R6's link is here already; R7's is not, because adding R7 will create it. R4's relay toward R6 went in as an ordinary change: 12 lines, verified and saved." | the ZTP row, Held by Mercury; Gi5 in R4's intent | 0:30 |
| 3a | cut | *(R7's Retire)* | | | | 0:00 |
| 4 | live | **Devices › Add device…** | ZTP: `r6`, IOS-XE, router, 10.255.4.2/30, its MAC, Gi2, Route option (3) the relay's own address; **Review the plan** (its NetBox line names the Planned record); open "How does this work?" once and close it; **Create r6** | "Adding a device is one decision. Mercury writes the DHCP reservation with its boot file and the relay as its only route, checks nothing on the segment can answer DNS, and commits R6's bootstrap intent. Nothing is sent to any device. Every action has a page saying how it works." | the review's address line; the result naming the reservation; the pending row | 1:30 |
| 5–6 | live, then time-lapse | R6's console (LAB), then **r6's pending page**, then **Verify…** | `reload` on R6's console (LAB, 10 s on screen, the console closed before it boots); the stages advancing (time-lapse); the Verify preview, then **Verify r6**, its nine steps (time-lapse) | "In the lab, powering on a new router is a reload of a blank one. It asks for an address through R4, Kea answers with its reservation, and Mercury's TFTP responder serves its bootstrap only to that address, only while it is pending. Verify is Day 0's last step: Mercury replaces the one-time password with a device-generated secret, sends the monitoring profile, saves, commits the first golden and sets R6's NetBox record Active. In the first run, from the first fetch to this point took 9 minutes 21 seconds." | `reserved_not_leased` → `leased_not_fetched` → `fetched_not_reached` → "Answering: ready to Verify"; the nine steps done; "onboarding: r6 verified and recorded in NetBox" | 2:00 |
| 7–9 | live, the stepper time-lapsed | **r6 › Actions › Seed intent…**, **Intent › Edit**; then **Devices › Add device…** for R7 and R7's console (LAB); then **r6 › Actions › Plan a deploy…** | Seed and confirm (time-lapse); paste R6's stored Day 1 document; "What a deploy would send"; commit. Then Add device for `r7` (10.255.4.6/30, Gi2, option 3 the relay's own address): its review adds the link's subnet with the reservation; **Create r7**; `reload` on R7's console (LAB, 10 s). Then R6's plan: the exact program; confirm by hash; the stepper (time-lapse) | "Day 1 is the full service configuration, written as intent before R6 arrived; the editor checks it and shows exactly what a deploy would send. R7 is added now, between R6's commit and R6's deploy: its plan creates its link's subnet and its reservation together, and R7 is powered on, so it is asking by the time R6's relay goes live. This is R6's exact program, masked, bound to this hash: what is confirmed is what is sent. Verify says OSPF to R4 is up, and that RIP toward R7 is not up yet because R7 has no configuration; Needs attention keeps that until RIP forms." | the editor's diff, additions only; R7's subnet and reservation in one plan; Verify FULL: OSPF 0 → 1, OSPFv3 0 → 1; RIP and RIPng declared, not up yet (caption: C1450) | 2:45 |
| 10–11 | time-lapse, then live | **r7's pending page**; **Verify r7**; **r7 › Seed intent…, Intent › Edit, Plan a deploy…** | The stages advancing as R6 relays (time-lapse); Verify r7 (time-lapse); R7's Day 1: one deploy, its Gi3.10 block in order (live), its stepper (time-lapse) | "R7 has been booting since it was added, and asked as soon as R6's relay existed. In the second run, R7 asked 310 times over 25 minutes 46 seconds before a relay answered; here it was waiting only for R6's deploy. R7's Day 1 is one approved change, and Verify is green: RIP and RIPng are up both ways." | R7 promoted and recorded in NetBox; Verify green; RIP 1/1, RIPng 1/1 | 2:15 |
| 12 | live | **DHCP › Leases**; then H5's shell (LAB) | H5's lease in 10.70.10.0/24; from H5, `traceroute 8.8.8.8` and `curl` of the web server | "H5 leased its address through R7's relay and reaches the internet through R7, R6 and R4. The host is outside Mercury, so this last check is from its own shell." | the lease; the path R7 → R6 → R4 → R5; "hello world from RCN" | 0:45 |
| 13 | live | **Show commands** | Run the saved set "Lab 8 checks" on r4, r6 and r7 | "Every check is read through Mercury: R4 is the border router for areas 0 and 10, R6 and R7 hear each other over RIP, and R7's networks reach R4 as OSPF external routes." | per check, the answers; r4's routes O E2 via R6; R6's RIP database holding R7's networks | 1:00 |
| 14 | live | **r6 › NetBox › Import into NetBox…**, then r7's; then NetBox's own UI | The preview, **Import**; NetBox's devices in Branch, their interfaces, addresses and cables | "Onboarding recorded each device once. After Day 1, NetBox is brought up to the deployed intent through the same preview and confirm: each management address on its interface, R7's VLAN 10 subinterface with the branch's VLAN, and cables made only where both ends report each other over LLDP." | the import's card; R4–R6 and R6–R7 cables; Gi2's leased addresses; r7's Gi3.10 tagged VLAN 10 | 1:30 |
| 15 | live | **Topology** | The map with R6 and R7; select the R4–R6 and R6–R7 links; the weak points, each "Accepted" with its reason (walk d4) | "The map draws R6 and R7 from LLDP, OSPF and RIP, not from what NetBox says, so it shows what is true. It names the single points of failure; these are the handout's design, accepted by a person with that reason, and the map keeps them visible as accepted." | R6 and R7 on the map; the weak points Accepted: "the course handout's topology (Lab 8)" | 0:45 |
| 16 | live | **History › Timeline**, the last day; open one line | The expansion in order: the retirements, Add device with its subnet and reservation, served, rotated, verified, Day 1, the accepted weak points, the imports; open a deploy's line | "History is the documentation that writes itself: every change, who made it, which operation, and its record. In the second run, R6's and R7's Day 1 deploys sent 78 lines, each exactly as confirmed, each verified and saved, none rolled back." | the timeline; a receipt's detail | 1:00 |
| 17 | live | **Needs attention** | Read the rows left | "What remains is known and registered." Then name each row left, as Friday's rehearsal leaves it (walk h3): the heartbeat check failing on s3, and r1's OSPF adjacencies toward s3 and s4 going down, which is the host tuning in the next scene. | the walk's end state (LAB8_REHEARSAL_WALK h3), each row's finding as a caption | 0:30 |
| 18 | live | **docs/HOST_TUNING.md** (or a slide of its table, **as of Friday**); Grafana's fleet dashboard | The before and after | "Adding R6 and R7 made the lab stall every 8 to 12 minutes. The cause, measured: the emulated switches lose timer ticks under CPU contention, so s3's 10-second OSPF hello fired about every 23 seconds. Giving each switch its own CPU cut failed scrapes by 94% and OSPF drops by 86%. It is not finished: [READ Friday: the drops an hour and failed scrapes in HOST_TUNING's latest measured hour]." | the change-2 table and the latest row, captioned "as of Friday" | 0:45 |
| 19 | live | **Templates** | `_common.j2` Current; its bring-in and the base templates' approvals, with who and when | "The framework is updated the same way it changes devices: a shipped template fix was measured against every device, all ten rendering the same, brought in, and approved by hash before anything renders through it." | the row Current; the approvals | 0:45 |
| 20 | live | **docs/LAB8_DOCUMENTATION.md** | Scroll the addressing, the routing, and the Day 0/1/2 table | "Day 0 is zero-touch. Day 1 is one approved, verified change. Lab 9 moves that approval up front, before the device arrives." | the documentation | 0:45 |

**19:45 as listed** (1b, 19 and every live step kept). **Scene 19 stays in every cut.** If the
edit runs long, shorten in this order: 13 to its first two checks (−0:20), 12 to its traceroute
(−0:15), 16 to the timeline without the receipt (−0:15).

## Every walk step, and where it is in the video

| Walk step | What | Scene | Mark |
|---|---|---|---|
| P1 to P9 | preconditions (deploy, pinning, Planned records and the Branch site, the seed, s3's Retry, the break-glass export, Day 1 documents, before-reads, the capture) | before recording | cut |
| a1 to a3 | R7's recovery-ZTP "before" test | none (rehearsal only) | cut |
| b1 | Retire R7 | 16 (History row) | cut |
| b1a | subnet 257 removed | 3 (its absence) | cut |
| b1b | R7 `write erase` (Saturday; Friday's a2 did it) | none | cut |
| b2 | alert rules, removal path | none | cut |
| b3 | D4's measurement (skipped) | none | cut |
| b4 | Retire R6 | 16 (History row) | cut |
| b4a | R6 `write erase` | none | cut |
| b5 | alert rules, removal path | none | cut |
| c1 | Add device r6 | 4 | live |
| c2 | R6 reloaded | 5–6 | live (10 s) |
| c3 | R6 arrives | 5–6 | time-lapse |
| c4 | Verify r6 | 5–6 | live, steps time-lapsed |
| d1.1 | R6 Seed intent | 7–9 | time-lapse |
| d1.2 | R6's Day 1 document built | none | cut |
| d1.3 | R6 Intent › Edit, commit | 7–9 | live |
| c5 | Add device r7 (its subnet and reservation) | 7–9 | live |
| c5a | R7 reloaded | 7–9 | live (10 s) |
| d1.5 | R6's Day 1 deploy | 7–9 | live, stepper time-lapsed |
| d1.6 | reads after | none | cut |
| c6 | R7 arrives | 10–11 | time-lapse |
| c7 | Verify r7 | 10–11 | time-lapse |
| d2.1 | R7 Seed intent | 10–11 | time-lapse |
| d2.2 | R7's Day 1 document built | none | cut |
| d2.3 | R7 Intent › Edit, commit, deploy | 10–11 | live, stepper time-lapsed |
| d2.4 | reads after | none | cut |
| d3 | monitoring rules (Day 2) | 16 (History rows) | cut |
| d4 | Topology's weak points accepted | 15 | live |
| e1 | H5's lease | 12 | live |
| f | Lab 8's checks | 12 (H5's), 13 (the rest) | live |
| g1 | NetBox import | 14 | live |
| h1 | Save All | 16 (History row) | cut |
| h2 | break-glass export | none (a passphrase is typed) | cut |
| h3 | Needs attention | 17 | live |
| i | the rehearsal's recording reviewed (Friday only) | none | cut |

## What is said only if it is true on the day

- **"Its plan creates its link's subnet"** (7–9) only if Friday's run of C1460 worked (walk c5).
  Otherwise 3 shows subnet 257 added by hand before the recording, 7–9 says R7's reservation
  goes into it, and the caption names C1460.
- **"Verify is green"** for R6 is never said: R6's Day 1 has RIP unmet until R7 exists, and
  Needs attention says so until RIP forms (C1450).
- **No figure is rounded up or estimated.** The figures above are from docs/PITCH_METRICS.md
  sections 1, 2, 2b and 3 (the first and second runs, and the suite on 2026-10-20), and
  docs/HOST_TUNING.md as of Friday. Saturday's own figures (its receipts, its fetch-to-promotion
  times) are read into docs/PITCH_METRICS.md after the recording. They are said on camera only
  where the screen shows them.
