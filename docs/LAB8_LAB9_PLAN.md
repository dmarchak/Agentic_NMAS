# Labs 8 and 9: the plan

**Written 2026-10-19 (UTC) for the operator's sign-off.** Nothing here has run on the lab's
devices, and nothing will until the operator signs it off. The handout's objectives are quoted in
docs/LAB_REQUIREMENTS.md. The surveys behind this plan were read-only. Their findings are rows
C1332 to C1351 of docs/OPEN_FINDINGS.md.

**Dates (the operator's):**

| Lab | Built by | Walked | Recorded | Due |
|---|---|---|---|---|
| Lab 8 | Thu 10-22 | Fri 10-23 | Sat 10-24 to Sun 10-25 | Mon 10-26 |
| Lab 9 | Sat 10-31 | Sun 11-01 | Mon 11-02 to Tue 11-03 | Wed 11-04 |

Sizes follow the completion inventory: S is 1 to 2 hours, M is 2 to 8, L is 8 to 24. The first
four capabilities ran at about a tenth of their mid size (docs/NSOT_WRITEUP.md). None of those
four touched a device, so the sizes are kept here as they are.

## 1. The answer in brief

- **Lab 8 can make its date, with two risks.**
  - **Relayed ZTP has never run, and Mercury refuses it by construction (C1346).** A throwaway
    proof comes first. Whether IOS-XE's AutoInstall fetches from an off-subnet server without
    option 3 is unmeasured. If it needs option 3, the charter's D4 rule (no `routers` option on a
    ZTP subnet) needs the operator's decision for relayed subnets.
  - **R4 has no spare interface (C1350).** A link added to a running node is never seen by its
    VM, so R4 restarts with the new link. A lab node is never restarted by containerlab or
    docker (the operator, 2026-10-19; lab/REDEPLOY.md), so R4 gets its link through a full
    redeploy: 23.8 minutes, a 60-minute window, and new host keys on every device.
- **Lab 9's largest unknown is the switch (C1349).** No vIOS has ever booted without a
  configuration under vrnetlab, or run AutoInstall here. The measurement is after Lab 8 is
  built, on 10-22 or 10-23. If it fails, section 5 sets out the fallback.
- **Retirement is far from complete (C1332 to C1342).** A new R6 under the same name would
  inherit r6's golden tags, rollback blocks, receipts, Kea reservation, rotation-policy
  membership, template override, heartbeat rule and NetBox record. These are fixed before r6 is
  retired: tonight's first build.
- **The NSoT on add is the bootstrap only (C1344).** NetBox gets the device once, from its
  bootstrap golden, and no path creates cables. "Updated appropriately" needs NetBox brought up
  to the deployed intent, with cables from LLDP.

## 2. Lab 8: steps, in the handout's order

Who: **M** is a Mercury operation (preview, confirm by hash, verify, record); **L** is the
operator's lab tooling; **C** is code to build first.

| # | Step | Who | Built? | Size | When |
|---|---|---|---|---|---|
| 0a | Retirement completeness: every per-device artefact removed or archived, each with a planted leftover test (C1332 to C1342) | C | **built** (73770853, deployed) | L | done 10-19 |
| 0b | The device-name scan with its exact inventory (the lifecycle rule) | C | **built** (fa322848, deployed) | M | done 10-19 |
| 0c | Feature packs for OSPF (areas, ABR), RIPv2 and redistribution, rendered from intent for IOS and IOS-XE, with round trips on captured configs | C | **built** (K7's commit, 10-19); IOS-XE 17's display of `subnets` unmeasured | L | done 10-19 |
| 0d | The relayed-ZTP proof on a throwaway pair (a relay node, a configless C8000v behind it, with and without option 3) | L/measure | **done** 10-19, 20:57 to 23:18 UTC, through Mercury's own path (docs/RELAY_PROBE.md, "Results"): relayed ZTP works and **needs option 3, the relay's own address**; without it DHCP through the relay completes and the device never asks for its file. Its costs registered: C1399 to C1405 | M | done 10-19 (deferred from the night before: s3's gaps were widening; run with s3's gap rate under its 6.5% gate before and after) |
| 0e | Relayed ZTP in Mercury: the plan and writer for a relayed subnet (server address, a fragment per relayed subnet, option 3 as the relay's own address if 0d needs it, the DNS check on the relayed path), and the firewall's udp/69 rule widened by a host step (C1346) | C | **built** (5920f15d; its cards compared with boards E and C in 13b50e30; deployed and run in 0d): Add device's Route option (3), DHCP › Add a subnet's For ZTP onboarding. Before R6's run: C1403 (an old lease blocks a redone onboarding), C1404 (a deploy leaves the ZTP responder on old code), C1400 (a transient first-contact key) | M to L | done 10-19 |
| 0f | NetBox on add: after a device's intent is deployed, its record brought up to the golden through Import's preview and confirm; cables from both ends' LLDP (C1344) | C | **built** (0f's commit, 10-19; not deployed): the device tab's one-device Import into NetBox…, a Needs attention row while NetBox holds less than the golden, cables from the Topology reader's stored LLDP | M | done 10-19 |
| 0g | DROPPED (the operator, 2026-10-19): a lab node is never restarted by containerlab or docker (lab/REDEPLOY.md), so there is nothing to measure | | | | |
| 1 | r6 retired through the GUI (Device page › Retire), then its separate lab (`clab-r6`) destroyed | M, then L | **done** 10-20: retired by the operator ~06:38 UTC (5452e316, 16 steps green, the heartbeat host step PASS); every Mercury artefact read gone on the host; `clab-r6` destroyed with `--cleanup` 06:48. Left: Grafana's live rules for r6 (C1419, its stopgap host step), NetBox's `r6-retired-11` (deleted by the operator) | S | 10-20 |
| 2 | R6 and R7 planned in NetBox as Planned devices, addresses from NetBox's prefixes (section 4) | M (NetBox) | NetBox's own screens; no Mercury screen plans a device | S | 10-22 |
| 3 | R4's new link: the lab topology gains R4 GiN to R6 (host bridge br-r4r6) and R2 GiN to R8 (br-r2r8), the lab redeployed (lab/REDEPLOY.md), a planned-restart window declared first | L | the window is built; the redeploy's pre-flight passes | S to M | 10-22 |
| 4 | R4's side deployed first: the area-10 interface and `ip helper-address` to Kea, through preview, confirm by hash and verify | M | built (intent edit, deploy); the area through the pack (0c) | S | 10-22 |
| 4b | s3's static route to the retired r6's loopback (`ip route 10.255.1.16 255.255.255.255 10.255.0.32`, C1422) removed: the intent entry deleted, then the line ticked under "Left on the device" (Mode B, `global.ip-route`, measured exact on IOS) with its reason, confirmed by hash; s3's console the repair route. Before and after: `show ip route 10.255.1.16` on r1 and r4 (the E2 route there, then gone). Right after step 4 verifies, before R6's subnet and ZTP (the operator, 2026-10-20) | M | built (Mode B) | — | 10-20 |
| 5 | R6 by ZTP through R4's relay: Add device › ZTP, reservation in Kea, R6 boots configless, fetches its bootstrap; Verify promotes it | M | no (0e) | — | 10-22 |
| 6 | R6's full intent deployed: OSPF area 10, RIPv2 toward R7, redistribution, a relay facing R7 | M | packs (0c) | S | 10-22 |
| 7 | R7 by ZTP through R6's relay, then its intent (RIPv2, VLAN 10 gateway for H5, its relay) | M | as 5 and 6 | S | 10-22 |
| 8 | H5 on VLAN 10 behind R7: DHCP subnet added on the DHCP page (relay from intent), the host container added | M, L | the relayed subnet is built (DHCP screen) | S | 10-22 |
| 9 | The NSoT updated: NetBox's R6 and R7 records and cables, History's commits, the repository's intent and goldens | M | 0f | — | 10-22 |
| 10 | The documentation shown: NetBox (devices, IPAM, cables), Topology (R6 and R7 drawn from LLDP and OSPF), History (the timeline of the expansion) | M | built; a single documentation view (C1351) is optional, M | — | 10-23 walk |

**The walk (10-23), the operator's draft order:** r6 retired through the GUI. The new R6 (a new
NetBox ID) is onboarded by ZTP under the same name and inherits nothing. Each of these is shown
empty or new: golden, intent, receipt, host key, reservation, target, policy membership and
Needs attention row. Then R7, then H5 reaching the network, then the NSoT and the documentation.

**r6's retirement, planned on the host (read only, 2026-10-19 07:3x UTC, after 0a was
deployed).** The plan refuses nothing. Of its 15 steps, 9 have work to do, and 6 have nothing
to do (no NetBox credential to mask, no staged credential, no Kea reservation, no rollback
block, no approval item, no legacy file). The 9:
1. clear the credential override at its address;
2. one commit removing its intent and golden and releasing its identity;
3. archive its 12 golden tags under `retired/r6/<identity>/`;
4. remove it from the default credential-rotation policy's device list;
5. withdraw its island declaration and its place on the map;
6. remove its heartbeat rule (window 750 s) from the generated rules file, with the host step
   named;
7. set NetBox device 11 to Decommissioning and rename it `r6-retired-11`;
8. forget its SSH host key;
9. delete its inventory row (a current break-glass record is required first).

One advisory: r6's golden still carries Mercury's heartbeat applet, which the deploy path cannot
remove (C12).

**The management path for R6 and R7.** Chained ZTP puts R6's and R7's management in band, behind
R4. The rule "a change to the path the tool reaches a device on needs a repair route independent
of that path" applies to R4's step 4 and R6's step 6. The repair route is the console reader
(read-only) and the lab host's own console access, which is the operator's.

## 3. Lab 9: steps

| # | Step | Who | Built? | Size | When |
|---|---|---|---|---|---|
| 0a | vIOS-L2 with no configuration under vrnetlab: a configless launch patch with its own test (the C8000v's needed six changes and management passthrough; the vIOS launcher types on the console and restarts a quiet VM), DISCOVER captured, the file names it asks for (C1349) | L/measure, C | no | M | 10-22 or 10-23 |
| 0b | Classic-IOS ZTP (P.17, K61) sized from 0a: what the responder must serve (option 67's file, or `network-confg` and `<hostname>-confg`), the switch's management on its VLAN 1 SVI | C | no | M to L | 10-27 to 10-30 |
| 0c | R2's new link (as Lab 8's step 3, R2 restarted) | L | — | S | 10-29 |
| 1 | R8 by ZTP through R2's relay (area 20), then its intent: OSPF area 20, the relay facing the switch | M | Lab 8's | S | 10-30 |
| 2 | The switch by ZTP through R8's relay, then its intent: VLAN 10, the access ports for H6 and H7 | M | 0b | — | 10-30 |
| 3 | H6 and H7 on VLAN 10 behind the switch, by DHCP through R8's relay | M, L | built | S | 10-30 |
| 4 | Monitoring: each new device's heartbeat in Loki (W5, folded in here), its SNMP targets, Grafana's device dashboard | M | built; W5's wording waits for the handout's objectives | S | 10-31 |
| 5 | Visualization: Topology and the dashboards | M | built | — | 11-01 walk |
| 6 | DevOps testing: CI and the config check on the expansion's commits, the pre-change checks at each preview | M | built (C725's local check; its GitHub half is the operator's token) | — | 11-01 walk |
| 7 | Unit testing and coverage: a short segment reusing Lab 7's | — | built | S | recording |
| 8 | The documentation, as Lab 8's | M | as Lab 8 | — | 11-01 walk |

## 4. Addressing (proposed; from NetBox's prefixes, to be planned there in step 2)

Read from NetBox on 2026-10-19: 56 prefixes, all "Seen on" a device. Loopbacks run 10.255.1.11
to .16 for routers and .21 to .24 for switches. Point-to-point links are /31s in 10.255.2.0/24.
Host VLANs are 10.10.<vlan>.0/24 and 2001:db8:<vlan>::/64. VLAN 10's Kea subnet id 10 is taken,
so each new VLAN 10 segment is its own prefix with its own id. Nothing new may sit in `<LAN>`.

**Revised 2026-10-20 by the operator** (against rcn-lab1-design.md: routers are .1x, switches
.2x), before step 4:

| Segment | IPv4 | IPv6 | Notes |
|---|---|---|---|
| R4–R6, OSPF area 10 | 10.255.4.0/30 (R4 Gi5 .1, the relay; R6 .2, reserved: its management address) | 2001:db8:2:46::/64 (R4 ::1) | A /30, not the lab's usual /31: a relayed Kea subnet needs a client address besides the relay's |
| R6–R7, RIPv2 | 10.255.4.4/30 (R6 .5, the relay; R7 .6, reserved) | 2001:db8:2:67::/64 (RIPng) | |
| VLAN 10 at R7's site (H5) | 10.70.10.0/24 (R7 .1; Kea pool .100 to .200, router .1, through R7's helper) | 2001:db8:70:10::/64 | VLAN ID 10 used again at R7's site, not H1/H3's 10.10.10.0/24 (it ends at s1/s2's SVIs): in NetBox, a VLAN group for R7's site holding VID 10, attached to the prefix (C1424: Mercury's token cannot read VLAN groups). H5's DNS server: **none** (the operator, 2026-10-20: no DNS option on the subnet; 10.255.0.10 answers no DNS, by D4 on the ZTP segment it sits on, and the subnets that carry it today are C1425) |
| R2–R8, OSPF area 20 | 10.255.4.8/30 (R2 .9, the relay; R8 .10) | 2001:db8:2:28::/64 | |
| R8–switch, the switch's management (VLAN 1, untagged) | 10.255.4.12/30 (R8 .13, the relay; switch .14) | — | AutoInstall runs on VLAN 1's SVI (to confirm in Lab 9's 0a) |
| VLAN 10 behind the switch (H6, H7) | 10.80.10.0/24 (R8 Gi.10 .1; pool .100 to .199) | 2001:db8:80:10::/64 | A VLAN group for R8's site, as R7's |
| Loopbacks | R6 10.255.1.16, R7 .17, R8 .18, the switch .25 | 2001:db8:1::16, ::17, ::18, ::25 | .16 was the retired r6's: addresses are not identity, so reuse is allowed. Read 2026-10-20: no host key, Kea lease or reservation, Prometheus target or series, or Grafana rule is recorded against 10.255.1.16 or 2001:db8:1::16; NetBox's `r6-retired-11` and its two addresses deleted by the operator (2026-10-20); **s3 routes 10.255.1.16/32 to 10.255.0.32** (C1422), redistributed as an OSPF E2 route to every router: removed by Mode B in step 4b. The search of every network's intent for r6's old addresses found no other reference |

Read in NetBox's IPAM 2026-10-20: 10.255.4.0/24 and 10.70.0.0/16 hold no prefix and no address.
10.255.3.0/24 is NOT free: it is an existing segment in area 0 (r1 to r4 .11 to .14, s3 .23,
s4 .24). Site `relay-probe` (0d's) is still in NetBox.

**IPv6 (the operator's question, 2026-10-20):** the pack renders OSPFv3 and RIPng from intent
(K7). Dual-stack costs, beyond the IPv4 work: R4 Gi5's address and `ipv6 ospf 1 area 10` (in
step 4's edit); R6 and R7's link and loopback addresses, OSPFv3 area 10 on R6, RIPng between R6
and R7 and its redistribution into OSPFv3 on R6, written in the same intent as their IPv4; H5 by
SLAAC from R7's VLAN 10 interface (no Kea DHCPv6). Under an hour of intent and verification;
the untested part is RIPng on IOS-XE devices (the pack is tested on captures only). If it does not
converge on build day, R7's side and H5 fall back to IPv4 and the screen and manual say why.

ZTP is IPv4 only (C1245). The new links and VLANs are dual-stack in intent, as the lab's are.

## 5. Lab 9's switch: the default and the fallback

The default is a vIOS-L2, like s1 to s4 (the operator, 2026-10-19), if 0a shows that it boots
with no configuration and runs AutoInstall.

**What P.6 needed for the C8000v, and whether it applies.** The C8000v needed:
1. the base disk;
2. the install overlay with its saved configuration deleted;
3. no configuration ISO;
4. IOS-XE's own prompt accepted;
5. that prompt treated as running and the console released;
6. no restart of a quiet VM;
7. management passthrough (qemu's own DHCP answered first and stopped AutoInstall).

On the vIOS-L2, 1 to 3 are moot: there is no ISO, and the image has no install overlay. With no
startup file the launcher types no configuration, which was measured in stage A. But it still
answers the setup dialog and sends RETURN three times, and any console input ended discovery on
the C8000v. Its watchdog also restarts a quiet VM. So 4 to 7 apply, and they need a vIOS patch of
their own.

**If the vIOS-L2 cannot run AutoInstall:** EOS only if the dialect contract's size fits
10-27 to 10-31 (the operator). Section 9 finds that it does not. **The operator's fallback
(2026-10-19):** the switch is onboarded by DHCP through R8's relay (Mercury's DHCP onboarding of
classic IOS is measured), and the video says why the switch is not zero-touch.

## 6. Lifecycle: what retirement leaves today (C1332 to C1345)

Retirement does six things:
1. it masks NetBox's context;
2. it clears the credential override at one address;
3. it removes intent and the golden in one commit;
4. it removes a legacy golden that git holds;
5. it forgets the host key;
6. it deletes the inventory row.

Everything else stays, keyed by name. A same-name device inherits:

| Left behind | Effect on a new R6 | Row |
|---|---|---|
| Golden tags `golden/r6/*`, and baselines holding `golden/r6.cfg` | offered as R6's restore points | C1332 |
| Rollback blocks | R6's plans blocked by r6's failed commands | C1333 |
| Deploy receipts | r6's prior authorisations and Needs attention deploy rows | C1334 |
| Kea reservations (ZTP, DHCP) | R6's reservation at that address refused | C1335 |
| Rotation-policy device lists; rotation age by name | R6 in r6's policies, with r6's credential age | C1336 |
| The template override in `bindings.yml` | R6 rendered through r6's template | C1337 |
| The Grafana heartbeat rule | R6 judged by r6's window | C1338 |
| Approval-queue items | R6's item at the address suppressed | C1339 |
| Staged credential, adopt sidecar, the override at the reserved address | inherited | C1340 |
| Topology island declaration and map position | R6 drawn where r6 was, declared an island | C1341 |
| NetBox record kept Active, and Mercury's created-id entry | R6 refused, or onboarded onto r6's record and id | C1342 |

- **Not inherited:** the intent and golden files, the manifest entry, the inventory row and the
  host key.
- **Kept as history, read under the retired identity:** restarts, the rotation record, reveals,
  onboarding runs, inventory edits, the retry log, acknowledgements and Show commands runs.
  Moving these to identity by NetBox ID is C1343, a design.

**Device names in the product** (the lifecycle rule): 444 lines in 132 files name a lab device.
- **Logic keyed on a name:** two places. `scripts/nsot_first_runs.py` holds a fleet list.
  `record_exceptions.ROW_EXCEPTIONS` is keyed by `(device, at)`.
- **The rest:** measurement provenance (for example `platform_defaults.json`,
  `removal_measured.json`), dated incident comments, docstring examples and UI placeholders.
- **The scan (tonight):** every file declared with its count and kind, and a new hard-coded
  name fails. r6's examples become example names; its dated provenance stays.

## 7. The NSoT and the documentation

**On add today:**
- **Phase 1** writes the manifest's pending entry and intent's bootstrap block in one commit, plus
  the Kea reservation and its record for ZTP.
- **Phase 2** writes:
  - the rotation commit;
  - the first golden and its tag;
  - the manifest's address and NetBox ID;
  - the inventory row;
  - Prometheus targets;
  - NetBox's record from the bootstrap golden: device, platform, the management interface and
    address. There are no cables.
- **Never written by itself:** NetBox after the device's intent is deployed. Since 0f (C1344),
  a device whose NetBox record holds less than its committed golden is a Needs attention row,
  and its NetBox tab's Import into NetBox… brings it up to the golden, cables from both ends'
  LLDP included, through the import's preview and confirm.

**On leave today:** NetBox's record stays Active (C1342).

**What updates by itself:**
- the device list;
- History (every commit and run);
- Topology, once Prometheus scrapes the device and LLDP runs: it is drawn from SNMP's LLDP,
  OSPF and BGP tables and a RIP reader, never NetBox's cables;
- Prometheus targets;
- the DHCP page, every 5 minutes.

Topology does not draw the Linux hosts. NetBox's IPAM is as current as the last import. No
single documentation view or export exists (C1351). Composing one from the existing readers is M.

## 8. Capacity

Measured read-only 2026-10-19, 06:09 to 07:12 UTC, inside the containerlab VM and on the Proxmox
host (C1318).

**Per node, measured inside the containerlab VM (24 vCPUs, 78.5 GiB):**

| Node | Allocation | Memory | CPU |
|---|---|---|---|
| C8000v (each router) | 2 vCPUs, 4 GiB | 4.5 GiB | 1.86 to 1.89 CPUs: one vCPU at 100% always (the data plane polls), the other about 93% |
| vIOS-L2 (each switch) | 1 vCPU, 768 MiB | 0.38 GiB | 0.82 to 1.01 CPUs |
| Linux host | — | under 10 MiB | about none |

**Today:** 28.0 GiB used (51.1 GiB available), about 15.0 CPUs busy (64%).

**Adding R7, R8, the switch and H5 to H7:** R6 replaces r6, so it is net zero. The rest adds about
9.6 GiB and 4.7 CPUs, giving 37.6 GiB used and about 19.7 of 24 vCPUs busy (82%).

**The Proxmox host:**
- **Hardware:** 2 × Xeon E5-2650 v3, so 20 physical cores (40 threads). 125.8 GiB of RAM, 58.1
  available.
- **Running guests:** 31 vCPUs.
- **This week:** node CPU 45 to 50%. Steal inside the lab and NMAS VMs is about 0.03%. CPU
  pressure is about zero.
- **With the expansion:** the lab VM uses about 22.6 host CPUs. That is about 24 busy threads on
  20 physical cores, so some vCPUs share a core with a hyperthread sibling. That slowdown does not
  show as steal.
- The stopped VMs 201 to 203 must stay stopped.

**The answer: there is room.**
- Memory has ample room at both levels.
- CPU fits inside the VM, but the hypervisor goes past its physical cores.
- The measured lever is the C8000v's data plane. A router at 1 vCPU, or a lighter profile, could
  save about 0.9 CPU each. That is untested: it would be measured on r2 first, never s3, keeping
  the 10 Mbit/s throughput level in view.

**s3 is not a capacity question.**
- Its gaps widen during short bursts of emulation work on its own single thread, which already
  runs at 95 to 100% of a CPU. The bursts are more frequent each day since 10-14.
- The host's load is not the cause. Neither is steal, and s3's wait for a CPU is under 1%.
- More vCPUs or pinning will not help it. A fifth vIOS-L2 adds the same kind of work.
- Separately, r5's container (retired from Mercury, still in the topology) has been spinning since
  10-18 ~10:25 UTC and adds about 1 to the load. Repairing it, or removing r5, is lab tooling.

## 9. Multi-vendor (survey only)

The standing direction (the operator, 2026-10-19): Mercury must not force Cisco. Multi-vendor is
required for the public release, and the debt stops growing now, as with IPv6. This survey is
read-only. Its working files are in the session's scratch folder, not the repository.

**The dialect layer today.**
- **Platform selection:** `modules/nsot/platform.py` picks the dialect (`cisco_ios`,
  `cisco_iosxe`; an unknown one raises).
- **Per dialect:** parsers (`modules/nsot/parsers/`), templates (`modules/nsot/templates/`), and
  the round-trip and normalise rules.
- **The read allowlist** (`readonly_commands.py`) and the measured removal shapes
  (`removal_measured.json`).

**What is not in the layer.** No module answers "what is the command to do X on this dialect":
the engine modules write IOS commands directly.

**Vendor-specific strings outside the layer, by operation.** About 270 true dependency sites in
about 45 files, out of 497 Cisco-vocabulary string constants in code across 84 files (an AST
census). 285 of 613 test files hold Cisco CLI strings.

| Operation | Sites | Where most are |
|---|---|---|
| Get running/startup | ~34 | `config_read`, `pipeline`, `onboard`, `adopt`, `credential_rotation` (filtered `\| include` reads) |
| Save | 1 send (Netmiko's `save_config`), 6 callers | `onboard.persist_on_device` |
| Plan (render/diff) | ~60 | `deploy.merge_commands` and its negation grammar, `verify_scope.MANAGEMENT`, `removal` shapes, `ifnames` |
| Apply | ~12 | `pipeline` (`IOS_ERROR_PATTERN`, `send_config_set`, the IOS-XE NETCONF path) |
| Verify | ~25 | `pipeline`'s routing reads and parsers, `convergence`, `readers/rip` |
| Roll back | ~10, structural | `deploy.rollback_commands` and its provenance check |
| Set credential | ~35, safety-critical | `credential_rotation`, `adopt`, `bootstrap_config`, `redact`'s positional masks |
| Read neighbours | ~30 | `netbox_client` (CDP/LLDP), `prometheus_targets`; the BGP MIB is Cisco's |
| Monitoring lines | ~45 | `monitoring_coverage`, `logging_path`, `ip_sla_policy`, the Cisco CPU and memory MIBs |
| Reload | ~12 | `device_reload`, `reload_op`, `restarts` |
| Other | ~25 | `privileged` (Tier 2), `reads.COMMON`, the platform map's defaults |

**A dialect contract (proposed).**
- **Shape:** one module per dialect behind a `Dialect` protocol, with a capability map in which
  each operation is measured, not measured or unsupported. An operation that is not measured is
  drawn disabled with its reason.
- **Operations:**
  - `get_running` and `get_startup`, with the config's shape judged;
  - `parse`, `render` and `normalise`;
  - `plan`, which returns the exact ordered program and its mode: line merge, session commit or
    NETCONF;
  - `apply`, which returns per-line evidence and what landed;
  - `rollback`, which must pass provenance;
  - `removal`, for measured shapes only;
  - `save`, with its read-back;
  - the credential program and its masked form;
  - monitoring lines;
  - `facts`, `interfaces` and `neighbours` (IPv4 and IPv6), and the route total;
  - `restart_reason` and `reload`;
  - the read policy and Tier 2;
  - the secret shapes, which the redactor applies as a union across dialects (fail-closed).
- **Three rules:**
  - A read returns a value or Unreadable, never an empty list for "could not read".
  - A write says what landed.
  - A refusal names both operands.
- **The guarantee is unchanged.** The hash covers the program's lines, plus the dialect and mode.

**The contract suite.** It runs over every registered dialect, on real captures, each case planted
and shown able to fail. It checks:
- truncated and stitched configs refused;
- round trips;
- an empty plan for equal configs;
- a one-leaf change gives exactly its ancestors;
- determinism of bytes and fingerprint;
- apply's refusal transcripts;
- rollback provenance;
- no secret in a masked credential program;
- a canary per secret shape, redacted;
- the dialect's writing modifiers refused;
- reads healthy, broken and garbage, giving Unreadable not empty;
- save, reload and capability refusals;
- an exact-inventory ratchet: no CLI literal outside the dialects.

**Sizes (the survey's own estimates, in agent-hours).**

| Work | Estimate |
|---|---|
| Moving IOS and IOS-XE onto the contract (a behaviour-preserving move, each group pinned by characterisation tests first) | 110 to 165 |
| Its riskiest parts | redaction, rollback provenance, the refusal vocabulary |
| An EOS dialect after the contract | 100 to 150, plus one or two measurement sittings |

**NAPALM, as read functions only.**
- **Licence and weight:** Apache-2.0. About 8 to 10 new packages beyond what the lock already
  holds: junos-eznc, pyeapi, ttp, netutils, netaddr and their tail.
- **Getters it lacks:** OSPF, OSPFv3, RIP, EIGRP, IS-IS, CDP, IP SLA, the route total and the
  restart reason.
- **Fragility:** its IOS getters parse text the way Mercury's parsers do, without Mercury's
  captures, and a failed parse can come back empty.
- **Sessions:** it opens its own, outside Mercury's device hold, host-key pinning and recording.
- **Recommendation: take nothing from NAPALM now.**
  - EOS's `| json` output makes Mercury's own readers small.
  - IOS reads Mercury lacks can use ntc-templates, already installed.
  - Reconsider at a third vendor (Junos), and then only `get_facts`, the LLDP detail,
    `get_interfaces_ip` and `get_environment`, behind the contract.

**EOS natively.**
- **Configure sessions:**
  - each line is checked as it is entered;
  - `show session-config diffs`;
  - `commit` is atomic, and `abort` lands nothing;
  - `commit timer` reverts on the device unless confirmed;
  - checkpoints;
  - JSON from `show ... | json`, or eAPI.
- **How it meets the contract:**
  - **Confirmed is still Mercury's exact program:** the session's framing, its lines, the commit
    mode and the timer, all in the hash.
  - **The session diff is checked at apply, before `commit`:** the diff may hold only the
    program's leaves, otherwise `abort` and refuse naming both. The preview stays device-free.
  - **Gains:** a refused line lands nothing, and `commit timer` is a device-side repair route for
    management-path changes.
- **In the lab:** cEOS-lab runs in containerlab (`arista_ceos`, about 1 to 1.5 GB a node). Its
  image comes free after registering an Arista account, and the operator downloads it.

**EOS for Lab 9's switch: no.** Even at the first four's measured pace (a tenth of their sizes),
the contract and EOS would take about 21 to 32 hours of agent work. That work moves deploy,
rotation and redaction code during the lab's build week (10-27 to 10-31). The vIOS-L2 stays the
default. If it fails, section 5's fallback is a decision for the operator, not EOS.

**Found by the survey:**
- docs/NSOT_STAGE10_PLAN.md section 12 plans NAPALM as EOS's candidate transport and has a person
  confirm the device's diff. That contradicts the operator's direction of 2026-10-19 (NAPALM for
  reads only; the exact program confirmed).
- Its section 12.1 survey cites modules that no longer exist.

Both are registered. The plan's section 12 is rewritten when the contract is designed after
Lab 8.

## 10. The lab-tooling steps that are the operator's

- The lab topology's new links on R4 (Lab 8) and R2 (Lab 9), and each restart, with its
  planned-restart window declared first.
- A new lab file for R6, R7 and H5 (and later R8, the switch, H6 and H7), joined to rcn-lab1 by
  host bridges, as r6's lab joins `br-mgmt`.
- The configless launch for R6, R7 and R8 (P.6's patch and passthrough), and the vIOS patch for
  the switch once 0a has measured it.
- `clab-r6` destroyed after r6 is retired in Mercury.
- The hosts' containers (H5, H6, H7) and their DHCP client setup, as `configs/host-net.sh` does
  for h1 to h4. That file lives in the lab repository on the lab host.

## 11. The operator's decisions (signed off 2026-10-19)

1. **The plan is approved as written.**
2. **D4 restated for relayed subnets, only if 0d shows AutoInstall needs it.** Option 3 is
   allowed as the relay's own interface address and nothing else. Option 6 is never sent. D4's
   second condition is checked on every relayed segment by the job-health row. Recorded in
   docs/P6_ZTP.md under D4. **0d showed that AutoInstall needs it (2026-10-19, docs/RELAY_PROBE.md),
   so the allowance is in force for relayed subnets:** Lab 8's R6 and R7 are added with Route
   option (3) "The relay's own address".
3. **R4:** `containerlab restart -n r4` if 0g proves R4 comes up alone with its new link. If a
   full redeploy is needed, it is done the evening before the build day in a 60-minute window,
   with the nine host keys re-keyed through the GUI. **Not r5's interface:** R4–R5 is the lab's
   BGP link to the web server in the handout's topology, and it stays. **Superseded the same
   day:** a lab node is never restarted by containerlab or docker (lab/REDEPLOY.md). R4 and R2
   get their new links through one full redeploy, and 0g is dropped.
4. **The addressing in section 4 is approved as proposed.**
5. **Lab 9's switch fallback, if the vIOS-L2 fails:** DHCP onboarding through R8's relay, and the
   video says why the switch is not zero-touch.
6. **Timing (0g since dropped, decision 3):** 0d and 0g start on 10-19, not 10-20. 0e (relayed ZTP's plan and writer) and 0f
   (NetBox brought up to the deployed intent, cables from LLDP) start in code on 10-19 too,
   since they are needed whatever 0d shows.
7. **Before the throwaway:** r5's spinning container (C1354) is restarted, not removed (R5 stays
   in the lab's topology), with its health check read before and after. 0d runs only if s3's gap
   rate is no worse than its 10-19 baseline, reported before and after.
8. **(2026-10-20) Step 2's path, and NetBox's Planned records.** For the build: no Planned
   record; Verify's NetBox step creates R6's and R7's records, Active, from the bootstrap golden,
   and 0f's Import brings each up to the deployed intent after step 6. For the video the
   operator leans toward Planned records (NetBox declares R6 before it boots, then Planned →
   Active) and decides by Thursday; Friday's rehearsal uses that path. **The difference, read in
   the code:** Create reads a Planned record (its site, role, platform, tags, config context) and
   Verify's NetBox step updates that same record (found by name AND site, so the Planned record
   must be in the network's site, or a second device is created beside it); the update keeps
   NetBox's role, site and platform and writes the interfaces, addresses and context from the
   golden, but **never sets status**, so the record stays Planned after Verify (C1421, size S:
   Verify sets a record it took over from Planned to Active through the write gate). With no
   Planned record, the record is created Active. A Planned record is made in NetBox's own
   screens; no Mercury screen plans a device.
9. **(2026-10-20) Break-glass:** one export after R6 and R7 are verified, before Friday's
   rehearsal (their retirement deletes their inventory rows only against a record holding their
   current credentials). The operator types the passphrase.
10. **(2026-10-20) What a re-add (Friday's rehearsal, Saturday's recording) needs that a first add
   does not:** the R6/R7 lab destroyed with `--cleanup` before each re-add, so each boots
   configless; the break-glass export above; a Planned record made again each time, if that path
   is chosen (Retire leaves `<name>-retired-<id>` Decommissioning); C1418 (an open page switches
   to the retired view), C1419 (Grafana keeps a retired device's rules; until its fix, the host
   step `c1419-retired-device-rules.sh <device>` after each retirement) and C1420 (a re-added
   name's History starts at its retirement) fixed before Friday; Verify waits 120 s after the
   fetch (C1400), and Retire releases the device's leases (C1403).
11. **Capacity:** VMs 201 to 203 are the operator's lab VMs for another course. Those sessions run
   only when the containerlab lab is quiet. The 1-vCPU C8000v lever is measured on r2 (never s3)
   when a window allows, keeping the 10 Mbit/s level in view.
