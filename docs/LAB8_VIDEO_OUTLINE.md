# Lab 8: the video outline (a 7:10 cut)

**Status: reworked 2026-10-21 (~20:3x UTC) for the submission format: 6 to 8 minutes**
(docs/LAB_REQUIREMENTS.md, Lab 8). Today's real run (docs/LAB8_REHEARSAL_WALK.md, the
timetable below) is the source footage. The operator records each scene as its own file during the run
(section 4, the shot list, in walk order) and the narration after the edit, from the script in
section 3.

**Out of this cut** (material for elsewhere): the host tuning, Needs attention, Topology's
accepted weak points. They still run in the walk (d4, h3); they are not shown.

**The handout's three asks, and where each is answered:**

| The handout's ask | Scenes |
|---|---|
| What happens when the devices are added | 3 to 9 |
| How the GENERAL network automation framework is implemented and updated | 2 (the platform diagram, the ZTP path emphasised; what the framework updates when devices are added; one sentence that Mercury's own changes pass CI before install), 6 and 7 (Day 1 as infrastructure as code), 10 (History), 11 (a template update approved by hash). No CI footage: Actions, shards and coverage are Lab 9's |
| Examples of the documentation | 3 and 9 (NetBox: the branch's site, prefixes, VLAN 10, devices, addresses and cables), 6 and 7 (each device's intent in git, the written-down design), 10 (History: every change, who, what was sent, how it was checked). The voice-over names them as the documentation; the Lab 8 write-up is separate (no file 12, the operator, 2026-10-22) |

## 1. Rules

- Nothing in 08:30 to 09:10 UTC. No Mercury update during the run.
- Sign in through the access proxy as a person, so every confirm records who.
- No weekdays and no finding numbers in the narration.
- Nothing on screen shows a bootstrap's contents, a one-time password, a console loading a
  configuration, or an unmasked program: each console is closed straight after its `reload`
  line.
- Waits are time-lapsed with the speed on screen ("×8"), never cut silently.

## 2. The scenes, and the footage each comes from

| # | Scene | Target | Mark | Footage (the timetable's steps, ~UTC) | On screen |
|---|---|---|---|---|---|
| 1 | Topology and the goal | 0:30 | live | before b1, ~21:25: Topology with R6 and R7 present | the course network; R4, R6, R7 |
| 2 | How the framework is built and updated | 0:45 | live | after h3: the platform diagram (`<reports>/2026-10-21-lab8-framework.svg`, full screen), the ZTP path in orange | the parts and what flows between them |
| 3 | NetBox's branch, and DHCP's ZTP subnets | 0:30 | live | before b1, ~21:27: DHCP › Subnets (256, 257), r4 › Intent (Gi5's helper); after b6, ~21:51: NetBox Prefixes filtered to site Branch, VLANs to Branch VLANs, the Planned r6 and r7 | the relayed subnets; the branch's prefixes and VLAN 10; the Planned records |
| 4 | Add device: R6 | 0:40 | live | c1, ~21:53: Add device for r6, Review the plan, Create r6 | the plan's reservation and NetBox lines; the pending row |
| 5 | R6 boots, fetches its bootstrap, Verify | 0:50 | live 10 s, then time-lapse | c2, ~21:57: `reload` on R6's console; c3: the pending page's stages; c4, ~22:09: Verify r6 and its nine steps | reserved → leased → fetched → answering; "verified and recorded in NetBox" |
| 6 | Day 1 for R6, R7 added, R6 deployed | 1:00 | live, steppers time-lapsed | d1.1 to d1.3, ~22:19 to 22:26: Seed, Intent › Edit, commit; c5 and c5a, ~22:29 to 22:33: Add device r7 (its subnet and reservation in one plan), `reload` on R7's console; d1.5, ~22:34: R6's plan, confirm, deploy | the editor's additions; R7's plan; R6's exact program; Verify: OSPF up |
| 7 | R7 arrives through R6, and its Day 1 | 0:40 | time-lapse, then live | c6 and c7, ~22:43 to 22:59: R7's stages and Verify; d2.3, ~23:07: R7's Intent › Edit, plan, deploy | R7 answering; Verify green, RIP up both ways |
| 8 | The host on VLAN 10, and Lab 8's checks | 0:45 | live | e1 and f, ~23:37 to 23:50: DHCP › Leases (H5), H5's traceroute; Show commands "Lab 8 checks" on r4, r6, r7 | H5's lease; the path R7 → R6 → R4 → R5; the answers |
| 9 | NetBox updated, and the map | 0:40 | live | g1, ~23:52: Import into NetBox for r6 and r7, NetBox's view; then Topology with R6 and R7 | the import card; addresses, VLAN 10 and cables in NetBox; the map |
| 10 | History | 0:30 | live | after h3: History › Timeline, the run's rows; one deploy's receipt | every change, who, and its record |
| 11 | Templates | 0:20 | live | after h3: Templates, `_common.j2` Current and its approvals | the row Current; who approved it |

**7:10 as listed** (file 12 dropped, the operator, 2026-10-22: the documentation is shown through NetBox, intent and History; the write-up is separate). The walk's steps not in any scene (the Retires, erases, subnet removal,
the Planned records' entry, the agent's reads, the monitoring rules, the weak points, Save All,
the break-glass export, Needs attention) are recorded or not as the run allows; none is in the
cut.

## 3. The voice-over (recorded after the edit)

1. **Topology and the goal.** "This is the course network, drawn from what the devices report.
   Lab 8 adds R6 and R7 and a host behind them, and they must configure themselves when they're
   connected. R6 and R7 are here now, so I'll remove them and add them back from nothing."
2. **The framework.** "Mercury sits in the middle: it keeps each device's intended and saved
   configuration in git, and is the only way changes reach the devices. In orange, zero-touch
   provisioning: Mercury writes a DHCP reservation, the new device gets its address and where to
   fetch, and Mercury's own TFTP server hands it its first configuration. Adding a device updates
   everything around it: NetBox's records, intent and saved configuration in git, the DHCP
   reservations and subnets, and the map. Monitoring targets are added automatically; alert
   rules are a follow-up step today. Mercury's own changes pass its automated tests before
   they're installed."
3. **NetBox and DHCP.** "Each new link gets a DHCP subnet for zero-touch provisioning, relayed by
   the router in front of it. NetBox, the source of truth, holds the branch as its own site, with
   R6 and R7 planned before they exist."
4. **Add R6.** "Adding a device is one decision: Mercury reserves its address, prepares its
   first configuration, and records the plan, without touching any device."
5. **R6 boots.** "Powering on a blank router: it asks for an address through R4, gets its
   reservation, downloads its first configuration, and Verify takes it over, replacing its
   one-time password with a new secret and recording it in NetBox."
6. **Day 1 and R7.** "R6's full configuration was written as code before the device existed,
   and goes in as its intent: kept in git, it is the device's documented design, and the editor
   shows exactly what will be sent. By design it's
   deployed after one approval; Lab 9 moves that approval up front. R7 is added before R6's
   change goes live, so its address is waiting. Then R6's change is sent exactly as approved,
   and checked: OSPF to R4 is up."
7. **R7.** "R7 has been asking since it was powered on, and is answered the moment R6 relays.
   Its configuration, also written as code in advance, follows with one approval, and RIP comes
   up in both directions."
8. **H5 and the checks.** "The host on VLAN 10 gets its address through R7 and reaches the
   internet. Every Lab 8 check is read through Mercury, on all three routers at once."
9. **NetBox and the map.** "NetBox is the network's documentation of record, and it is brought
   up to date the same careful way: previewed, then confirmed, with each address on its
   interface and cables only where both ends report each other. The map is drawn from what the
   devices report."
10. **History.** "History is the documentation that writes itself: every change, who made it,
    what was sent, and how it was checked."
11. **Templates, and the close.** "Templates are updated the same way: measured against every
    device, then approved before anything uses them. Zero-touch on day 0, one approved change on
    day 1, and every step written down: in NetBox, in each device's intent, and in History."

## 4. The shot list, in walk order (one file per scene, named by its number)

The operator records each scene as its own file, started and stopped by hand. "Keep rolling"
marks a wait recorded whole, for the time-lapse.

| File | When (walk step) | Start recording on | Show | Stop after | Keep rolling through |
|---|---|---|---|---|---|
| **1** | before b1 | Topology, the map loaded | R4, then R6, then R7 selected | R7's card | none |
| **3a** | before b1 | DHCP › Subnets | 256 and 257, their ZTP and relay marks; then r4 › Intent, Gi5's helper | Gi5's helper line | none |
| *(b1 to b6 not recorded)* | | | | | |
| **3b** | after b6 | NetBox › IPAM › Prefixes, filter site Branch | the four branch prefixes; IPAM › VLANs, group Branch VLANs; Devices: r6, r7 Planned in Branch | the Planned records | none |
| **4** | c1 | Devices › Add device… | the form for r6, Review the plan (its NetBox and reservation lines), Create r6 | the pending row | none |
| **5** | c2 to c4 | R6's console, the prompt | `reload`; "Save? [yes/no]" → **`no`**; Enter at `[confirm]`; then CLOSE the console and switch to r6's pending page; Verify…, its preview, Verify r6 | "verified and recorded in NetBox" | the pending page from leased to answering (about 9 min); Verify's nine steps |
| **6** | d1.1 to d1.5 | r6 › Actions › Seed intent… | seed and confirm; Intent › Edit, paste, "What a deploy would send", commit; Add device for r7 (its subnet and reservation), Create r7; R7's console: `reload`, "Save? [yes/no]" → **`no`**, Enter at `[confirm]`, then close it; r6 › Plan a deploy…, the program, confirm | R6's Verify result (OSPF up) | the seed card; R6's deploy stepper |
| **7** | c6 to d2.3 | r7's pending page | the stages advancing; Verify r7; r7 › Seed intent…, Intent › Edit, paste, commit; Plan a deploy… (Gi3.10's block), confirm | R7's Verify green (RIP up both ways) | R7's arrival (several minutes); Verify's steps; the deploy stepper |
| **8** | e1, f | DHCP › Leases | H5's lease; H5's shell: `traceroute 8.8.8.8`, `curl` of the web server; Show commands › "Lab 8 checks" on r4, r6, r7 | the last check's answers | the Show commands run |
| **9** | g1 | r6 › NetBox › Import into NetBox… | the preview, Import; the same for r7; NetBox's r7 (Gi2's address, Gi3.10 and VLAN 10, the cables); then Topology with R6 and R7 | the map | the imports |
| **2** | after h3 | the platform diagram, full screen (`2026-10-21-lab8-framework.svg` in the reports folder) | hold on it for the narration (about 45 s); no CI footage | the diagram | none |
| **10** | after h3 | History › Timeline | the run's rows from the Retires on; open one deploy's receipt | the receipt | none |
| **11** | after h3 | Templates | `_common.j2` Current; its approvals with who and when | the approvals | none |

## 5. Said only if it is true on the day

- **"Its subnet and its reservation in one plan"** (scene 6) only if R7's Add device created
  subnet 257. Otherwise scene 3's subnets show 257 added by hand again before R7's Add device,
  and the line is cut.
- **"Checked: OSPF to R4 is up"** for R6 (scene 6), never "everything is green": RIP waits for
  R7.
- **"Nearly thirteen thousand tests"** (scene 2): the suite counted 12,910 on 2026-10-20
  (docs/PITCH_METRICS.md section 3). Never rounded up.
- **No other figure is said.** The run's own times are read into docs/PITCH_METRICS.md after it.
