# Lab 8: Friday's rehearsal walk (2026-10-23)

**Status: revised 2026-10-21 (~16:3x UTC) after the operator's two reviews, against what the
host runs (f14bd314, with ed58d33e to follow). Deployed: C1442, C1450, C1460 part 1, C1476,
C1477, C1479, C1487, C1489, C1492, C1494, C1499, C1504 (and C1506 with ed58d33e). D3's seed is
taken and P5 is done. Nothing in the walk itself has run.** It is the rehearsal of Saturday's
recording (docs/LAB8_LAB9_PLAN.md section 11, item 12): R7's
recovery-ZTP "before" test, then R6 and R7 retired and added again by ZTP, their Day 1 applied,
H5 leased, Lab 8's checks read, NetBox brought up to date, and Needs attention left in a known
state. Every value is from docs/LAB8_LAB9_PLAN.md section 4, docs/LAB8_MORNING_WALK.md sections
2, 4 and 5, docs/RECOVERY_ZTP.md section 5, docs/LAB_ONE_TOPOLOGY_PLAN.md sections 3, 4 and 6,
or docs/PITCH_METRICS.md. A live fact no document holds is a visible placeholder,
`[READ: <what, through which screen>]`, collected in section 4.

## The rules for the sitting

- **The nightly backup window, 08:30 to 09:10 UTC (02:30 to 03:10 UTC−6): no step in it.** The
  whole sitting runs outside it. Allow about 3 to 4 hours (an allowance from the 2026-10-21 redo,
  not a measurement): start at or after 09:10 UTC, or finish before 08:30 UTC with every
  declared window ended.
- **The planned-restart rule:** any restart of a device Mercury holds is covered by a
  planned-restart window declared BEFORE it acts. A window recorded after the restart is only a
  correction. Here that is R7's reload in step a2. A device Mercury does not hold (retired, or
  pending onboarding) needs no window (docs/LAB_ONE_TOPOLOGY_PLAN.md section 4), and its pending
  page says it restarted.
- **A lab node is never restarted by containerlab or docker** (lab/REDEPLOY.md). Only a reload
  from its own console or Mercury's Reload.
- **Nothing staged on s3.** s3's only change in this walk is the IP SLA retry (P5), before the
  sitting.
- **No Mercury update (`nmas-deploy`) from the walk's first step until the operator says the
  rehearsal is done.** Everything that should be on the host for Friday is deployed in P1.
- **One device-changing step at a time,** each read before the next. Anything other than the
  step's **Expected** is a stop: the step's owner says so, and nothing further runs until the
  operator decides.

## Marks

- **[OPERATOR]**: the operator. Every Mercury action that Saturday's recording will show is
  pressed by the hand that records it. Console steps and every lab-host command that changes
  something are the operator's.
- **[AGENT]**: the agent, under the Phase 7 operating mode. Reads through Mercury (a device
  page's **Ask the device**, **Show commands**, the screens), read-only measurement on the hosts
  through `scripts/nmas-host`, host commands and host steps on `<nmas-host>`, and the Day 1
  documents. The agent never types a secret and never reads one.
- **DECISION**: a person's decision (docs/MANUAL_STEPS.md): a confirm by hash, a reason, a
  window, which device joins or leaves.
- **LABOUR (M<n>)**: a step Mercury cannot yet do, with its row in docs/MANUAL_STEPS.md.
- **LAB (M24)**: lab tooling, outside Mercury: a console `write erase` and `reload`, a capture,
  a host's shell.

---

## 1. Decisions for the operator before Friday

Each with the recommendation. The walk below is written for the recommended option, with the
other option's difference named at the step it changes.

**D1. Kea subnets 256 (R6's link) and 257 (R7's link): keep them, or remove them so Add device
creates them (C1460).**
- C1460's part 1 (Add device adds its link's ZTP subnet; Retire removes one it added) is
  deployed. An existing matching subnet is used and recorded as not Mercury's, so Retire keeps
  it. Part 2 (the link's NetBox prefix) and the per-subnet firewall step are not built (M10; the
  host's firewall admits by default today, C1435).
- **DECIDED (the operator, 2026-10-21 morning): walk C1460 on R7 on Friday.** Subnet 257 (R7's link) is removed first, after R7's Retire
  (DHCP › Subnets › its **Remove…**), and R7's Add device creates it in the same preview and
  hash as its reservation. Subnet 256 (R6's link) is kept and reused. **If Add device's subnet
  creation fails**, fall back to the manual path: DHCP › **Add a subnet…** for 10.255.4.4/30
  as on 2026-10-20 (For ZTP onboarding, Route option (3) = R6's 10.255.4.5), then Add device
  again. Saturday's recording uses C1460's path if Friday's run works, else the manual one.

**D2. NetBox Planned records for R6 and R7 (docs/LAB8_LAB9_PLAN.md section 11, item 8: due
Thursday).**
- **With Planned records:** NetBox declares R6 and R7 before they boot. Create reads the Planned
  record (its site, role, platform, tags, config context), and Verify's NetBox step updates that
  record and sets it Active (C1421, fixed and deployed with 3d26c7a2; it has not yet run on a
  device). Each record is made in NetBox's own screens, in the network's site (LABOUR M22: no
  Mercury screen plans a device, C1447), before Add device.
- **Without:** Verify's NetBox step creates each record Active from the bootstrap golden, as on
  2026-10-20 and 2026-10-21.
- **Recommendation: rehearse with Planned records on Friday.** It is the stronger
  source-of-truth story, and the operator leaned toward it. Friday is where its first real run
  belongs. If it fails, Saturday records the plain path, which ran twice.
- **DECIDED (2026-10-21, the recommended option taken under the Phase 7 operating mode;
  docs/STANDING_APPROVAL_LOG.md): Planned records, made in the branch's own site (D9), not in
  Default's.**

**D3. Default takes the shipped template seed before Friday (C1498), so R7's Gi3.10 is one
deploy (C1478). TAKEN.**
- The operator brought in `_common.j2` and re-approved `cisco_ios/base.j2` and
  `cisco_iosxe/base.j2` on 2026-10-21. The render check after it: every one of the 10 devices
  renders the same as before (r7's three lines are its intent's own serial-form client-id, the
  operator's intent edit, C1479). `encapsulation dot1Q` now renders before every address line,
  so R7's Day 1 is one deploy.

**D4. C1432's measurement on R6, just before R6's Retire. DECIDED (the operator, 2026-10-21):
skipped in the rehearsal.** It is not recorded, and it would add two deploys before R6's
Retire. It waits for the next re-add of a device (C1432, which blocks C1426).

**D5. r1's flapping OSPF adjacency to s4 (10.255.1.24): acknowledge it within its band, or leave
it.**
- The row is C1485's remaining symptom: after the switch pinning, 2 OSPF dead-timer drops an
  hour remained (docs/HOST_TUNING.md, Phase 2, change 2).
- **Recommendation: leave it.** It is a real, known, measured fault. The video's tuning segment
  says what it is. Acknowledge it only if the operator judges the cause understood and the band
  right; the reason names C1485.

**D6. R7's IPv4 default route: keep the bootstrap's static route.**
- Lab 8's check 3 asked for R7's default by RIP. R7's IPv4 default is the bootstrap's static via
  10.255.4.5, which the design keeps, with the same next hop as RIP's (LAB8_MORNING_WALK section
  5). Removing the static is a Mode B removal on R7's management path, with the console as its
  repair route.
- **Recommendation: keep it,** and say so at check 3. R7's IPv6 default is RIPng's from R6.

**D7. HOST_TUNING's Phase 3, option (b) (r6 and r7 boot from their goldens): not before Saturday's
recording.**
- That option gives R6 and R7 a day-0 ISO holding their goldens. Whether a `write erase` and a
  reload still boot them configless with that ISO present is unmeasured. The rehearsal's reset
  depends on it.
- **Recommendation:** Phase 3's option (b) after the recording, as HOST_TUNING's Phase 3 already
  allows when the stalls are gone.

**D8. Topology's weak points (C1487, deployed). DECIDED (the operator, 2026-10-21): walk step
d4, after d2.** Each weak point the map names is accepted with the reason "the course handout's
topology (Lab 8)", Topology read before and after.

**D9. The branch (R6, R7 and H5's VLAN 10) as its own NetBox site. DECIDED (2026-10-21, the
recommended option taken under the Phase 7 operating mode; docs/STANDING_APPROVAL_LOG.md).**
- **The collision:** every device is in NetBox's one site, Default, and Default's only VLAN 10
  is the core's (`VLAN10`, in no VLAN group; read 2026-10-21 ~16:1x UTC). NetBox holds no VLAN
  group and no location. R7's Gi3.10 takes its VLAN from a VLAN group scoped to its record's
  site (C1492), so in Default the import refuses it ("no VLAN group is scoped to the device's
  site"), and a branch VLAN 10 added to Default would sit beside the core's.
- **A site, not a location:** the import looks for VLAN groups scoped to a site only
  (`netbox_client._site_vlan`); a location-scoped group would need code, and Mercury never sets
  a device's location.
- **What Mercury does with it, already built:** onboarding reads a Planned record by name in any
  site (C676); Verify's NetBox step sets that record Active in place (C1421); an update never
  moves a record's site; the import gives Gi3.10 the VLAN 10 of the record's own site's group
  (C1492). The Default list's inventory is local, so no NetBox site filter drops a device.
- **What Mercury cannot do (LABOUR, by hand in NetBox, before Friday, P3):** create the site,
  its VLAN group and VLAN 10 (C1448), plan a device in it (C1447), or scope the branch's
  prefixes to it (C1515: the import scopes every prefix it creates to the network's site).
- **What has to land first (Mercury): C1009.** The import passes no NetBox ID for a device of a
  local list (read 2026-10-21: none of Default's 10 devices carries one), so it matches by a
  unique serial, else by name within Default. A branch record whose serial is shared would not
  be found, and the import would create a second record in Default. The fix takes the ID from
  the committed manifest, which holds r6's and r7's (22 and 23 today). Built, gated and deployed
  before Friday (P1).

---

## 2. Before the sitting (P1 to P9)

**P1 [AGENT]. Mercury on the host carries every fix that landed for Friday**, deployed by
`nmas-deploy --wait` (CI green) before the sitting, never during it. The host runs f14bd314
(read 2026-10-21 ~16:2x UTC); ed58d33e (C1506) deploys at 17:08 UTC; the commit carrying C1009's
fix (D9) and C1516's (no host prefix per loopback) is the one more that must land.
- **Expected:** "deployed <sha>" with CI's pass named, the sha carrying C1009's and C1516's
  fixes; job health's not-ok rows as before, none new.

**P2 [AGENT]. The host is not stalling.**
- Read-only, through `scripts/nmas-host`: `lab/pinning/check-pinning.sh` on `<lab-host>`, then the
  stall script for the last 60 minutes (docs/HOST_TUNING.md, the metrics table).
- **Expected:** PINNING HOLDS; failed scrapes and OSPF dead-timer drops at or below the change-2
  window's (38 failed scrapes and 2 drops in 60 minutes). Worse is a stop: a stalling host fails
  saves and Verify's reads (C1490), which is a rehearsal of the stall, not of Lab 8.

**P3 [OPERATOR, DECISION; LABOUR M22, C1447, C1448, C1515]. The branch's NetBox site (D9),** in
NetBox's own screens, before the sitting. Its Planned records (step 4) wait for the Retires,
which free the names: they are walk step b6.
1. Organization › Sites › Add: `Branch`, region `Default`, status Active.
2. IPAM › VLAN Groups › Add: `Branch`, scope type `dcim.site`, scope `Branch`. Then IPAM › VLANs
   › Add: VID 10, name `H5 LAN`, group `Branch`, status Active.
3. IPAM › Prefixes, all in **VRF `Default`** (RD `ndm:default`, the network's VRF; the import
   finds a prefix by prefix and VRF, so one in another VRF gets a duplicate):
   - 10.255.4.4/30 (R6–R7, id 62): rescoped to `Branch` (done, the operator, 2026-10-21);
   - 2001:db8:2:67::/64 (R6–R7, id 63, scoped to Default): rescope to `Branch`;
   - 10.70.10.0/24 (VLAN 10): added with site `Branch` and VLAN `VLAN10` (Branch VLANs) (done,
     the operator, 2026-10-21);
   - 2001:db8:70:10::/64 (VLAN 10, not in NetBox, read ~16:58 UTC): add with site `Branch`.
   None of it moves anything Mercury reads (the import never rescopes a scoped prefix; no reader
   reads a prefix's site). 10.255.4.0/30 and 2001:db8:2:46::/64 (R4–R6, ids 59 and 60) join the
   two sites and stay where they are.
4. **The loopback pools (C1516), after C1516's fix is deployed:** IPAM › Prefixes › Add:
   10.255.1.0/24 and 2001:db8:1::/64, role Loopback, VRF Default (where the loopback addresses
   sit). Then delete the 22 host prefixes "Seen on <device> Loopback0" (a /32 and a /128 for each
   of r1 to r7 and s1 to s4; Mercury cannot remove them, C1516). The three static-route host
   prefixes stay.
- **Expected:** the site, its VLAN group holding one VLAN 10, and the two prefixes scoped to it;
  the two loopback pools, and no "Seen on … Loopback0" host prefix.
- **Before Friday, once, [AGENT]:** Mercury's own read of the Branch site's VLAN groups
  (`_site_vlan`'s query, read-only on the host) finds VLAN 10, exactly one.

**P4 [OPERATOR, DECISION]. D3's template seed. Done 2026-10-21:** `_common.j2` Current; both
base templates approved again by the operator.

**P5 [OPERATOR, DECISION]. s3's IP SLA sent: Monitoring › IP SLA › Retry s3. Done 2026-10-21
~16:05 UTC:** golden dc5d57fca06f, 5 lines, Verify ok; its receipt took 76 s to read before, 38 s
to read after and 41 s to save (s3's slowness, HOST_TUNING's change 4). Needs attention's "The
last IP SLA send to s3: failed" is gone (read ~16:20 UTC).

**P6 [OPERATOR, DECISION and LABOUR M4]. A break-glass export holding R6's and R7's current
credentials:** Credentials › the break-glass record › **Export the record…**. The operator types
the passphrase, carries the file off the host and deletes the copy.
- **Why:** Retire deletes each inventory row only against an export holding the device's
  current credential. R7 was rotated at 02:41:06 UTC on 2026-10-21, and R6 at its redo's Verify
  (PITCH_METRICS section 1).
- **Expected:** Needs attention holds no break-glass row. `[READ: Credentials, the newest export's
  time, against R6's and R7's last rotation]`.

**P7 [AGENT]. The Day 1 documents are where the walk needs them:** `2026-10-21-r6-day1.yml` and
`2026-10-21-r7-day1.yml` in the operator's reports folder on `<laptop>`, the complete Day 1
documents committed on 2026-10-21.
- **Expected:** both present. Each holds secret references only, never a value.

**P8 [AGENT]. Before-reads for the record** (each through Mercury):
- Needs attention's rows, by title;
- each router's **Neighbours** tab (r1 to r4, r6, s3, s4): the adjacency counts;
- DHCP › Subnets: 256 (10.255.4.0/30), 257 (10.255.4.4/30) and 10.70.10.0/24 present;
- DHCP › Leases: R6's 10.255.4.2, R7's 10.255.4.6 and H5's lease.
- **Expected:** as docs/LAB8_MORNING_WALK.md section 8, check 4 (r1 OSPF 5/5, OSPFv3 3/3; r2 the
  same; r3 BGP 2/2, OSPF 6/6, OSPFv3 4/4; r4 BGP 2/2, OSPF 7/7, OSPFv3 5/5; r6 OSPF 1/1, OSPFv3
  1/1; s3 OSPF 5/5; s4 OSPF 5/5), and Needs attention's rows as section h3 reads them today.

**P9 [OPERATOR, LAB]. The capture on R7's uplink,** for step a: on `<lab-host>`, the command in
docs/LAB_ONE_TOPOLOGY_PLAN.md section 4 for r7 (read-only, no container touched).
- **Expected:** the capture file growing, with no packets until R7 asks.

---

## 3. The walk

### a. R7's recovery-ZTP "before" test (docs/RECOVERY_ZTP.md section 5)

Recovery ZTP is a design and is not built. This step measures today's behaviour, the design's
"before". It is the first part of R7's reset, so it costs nothing extra.

**a1 [AGENT, on the operator's go; DECISION M3]. The planned-restart window for R7.**
- **The gap:** no v2 control declares a window except a device's own Reload (C1361). So the
  agent runs the host's script on `<nmas-host>` as `<user>`:
  `scripts/nmas-planned-restart Default r7 --minutes 60 --why "Lab 8 rehearsal: R7's
  recovery-ZTP before test (write erase, reload), then Retire" --by <operator>`.
- **The bound, 60 minutes:** R7's reload to its first DHCP request is a C8000v boot (8.8 minutes
  to a lone C8000v's first answer, lab/REDEPLOY.md), the observation about 10 minutes, and Retire
  about 5. That is about 24 minutes, and 2.5 times that is 60.
- **Expected:** exit 0, `recorded: r7 in Default may restart from <from> until <until> (and up to
  15 min after) …` and `window recorded <recorded_at>`. Keep `<recorded_at>`: if the test is
  abandoned, the agent ends the window at once (`--end <recorded_at>`, lab/REDEPLOY.md). The
  window must not reach 08:30 UTC.

**a2 [OPERATOR, LAB M24]. On R7's console: `write erase`, confirm; `reload`, do not save,
confirm.** Mercury has no `write erase` operation and no recovery operation (RECOVERY_ZTP
section 1).
- **Expected:** R7 reloads. Its RIP routes leave R6 once RIP's timers expire. H5 loses its
  gateway.

**a3 [AGENT]. Read, about 10 minutes after the reload. What is expected today** (RECOVERY_ZTP
section 5, step 3):
- **DHCP › Leases:** R7 leases 10.255.4.6 through R6's relay, marked **reserved**: its
  reservation stands, since promotion never touches Kea.
- **The responder** (journal on `<nmas-host>`, read-only): R7 asks for `r7.cfg`. It is refused:
  "no pending ZTP device holds the reservation aa:bb:cc:00:04:07 -> 10.255.4.6 (promoted, …)".
  The audit row carries target `?`.
- **History, filtered to r7:** none of those refusals. They show only on a pending device's page
  (RECOVERY_ZTP section 1).
- **Devices:** r7 "Not answering". **Needs attention:** "r7 is not answering" (danger). Drift's
  "r7 could not be checked" follows at its next run.
- **r6's page › Neighbours:** RIP and RIPng to R7 "not heard". **Ask the device** on r6,
  `show ip rip database`: no 10.70.10.0/24 once RIP's timers expire.
- **Nothing names the blank boot or offers a recovery:** no row says R7 booted without its
  configuration, and R7's page has no Recover action. This is the gap the design closes.
- **The capture (P9):** how often R7 asks for its file, and whether AutoInstall stops asking
  after the refusals (the manual says about 2.5 minutes; R7's unanswered DHCP on 2026-10-21 went
  on for 25 min 46 s, PITCH_METRICS section 1).
- The agent writes these results into RECOVERY_ZTP section 5 after the sitting, as the
  measured "before".

### b. Retire R7, then R6

**The order, and why.** R7 sits behind R6's relay: Mercury reaches R7 through R6, R7's link
subnet (257) is relayed by R6's Gi3, and Add device for R7 needs that relay in R6's committed
intent (C48). So the devices leave in the reverse of the order they joined: R7 first, while
R6 still stands, then R6. Retiring R6 first would leave a managed R7 behind a parent that is
gone. And R7's re-add would still have to wait for R6.

**What Retire removes** (docs/manual/how-it-works/retire.md, 16 steps; nothing is sent to the
device):
1. NetBox's stored credentials, masked if Mercury wrote them.
2. The credential overrides at every address the device was known by.
3. The staged credential.
4. Kea's reservations, the device's Kea leases (C1403), and its link's ZTP subnet ONLY when Add
   device created it and nothing else is in it (C1460).
5. One commit removing intent, golden and template override, with `Retired-Device:` and
   `Not-Done:` trailers.
6. Its golden tags, archived as `retired/<device>/<identity>/<time>`.
7. Its rollback block.
8. Its queued items.
9. Its rotation-policy memberships.
10. Its Topology entries.
11. Its heartbeat rule.
12. Its telemetry rules (each with a delete file, C1419).
13. Its NetBox record, set to Decommissioning and renamed `<device>-retired-<id>`.
14. The legacy file.
15. Its SSH host key.
16. Its inventory row, last, against the break-glass export.

**What it leaves today:**
- the NetBox record (Decommissioning, renamed);
- the heartbeat applet on the device;
- a Kea subnet a person added (256, 257);
- the parent's relay in its intent;
- the link's NetBox prefix;
- **not the retired record's IP addresses:** Retire's NetBox step deletes the addresses Mercury
  recorded as created and unassigns the rest, each with its before recorded (C1494). The retired
  record holds no address the new device needs. One a person made and Mercury cannot free is
  named on the import's card with its **Free <address>** action (C1504).

**b1 [OPERATOR, DECISION M7, M1, M2]. R7's page › Actions › Retire…,** reason "Lab 8 rehearsal:
R7 reset to be added again by ZTP". Read the card, then confirm by its hash.
- **Expected card:**
  - every step listed with its work. Reservations: ZTP's for `aa:bb:cc:00:04:07` in subnet 257.
    Leases: 10.255.4.6.
  - the `ztp_subnet` step says subnet 257 stays (a person added it, 2026-10-20);
  - what is generated and so dropped, and what survives;
  - no refusal. Retire needs no SSH, and P6's export holds R7's credential.
- **Expected result:** "Retired"; the name `r7` free; NetBox's record `r7-retired-<id>`,
  Decommissioning, holding no address. R7's page becomes its retired record. R7's window from a1
  covers nothing more; it lapses at its end.
- **R7 stays erased:** a2's `write erase` left its startup configuration empty, so its reload at
  c5a boots it configless. On Saturday, with no step a, this is step b1b: `write erase` on R7's
  console after its Retire, no reload (LAB M24).

**b1a [OPERATOR, DECISION]. Subnet 257 removed (D1, decided: C1460 is walked on R7).** DHCP ›
Subnets › 10.255.4.4/30 (Kea id 257) › **Remove…**, reason "Lab 8 rehearsal: R7's link subnet,
for Add device to create (C1460)". Confirm by hash.
- **Before it:** R7's Retire (b1) removed its reservation and released its lease, so no
  reservation or lease is left in the subnet. If the removal is refused naming one, read DHCP ›
  Leases and Reservations for 10.255.4.4/30 first; do not force it.
- **Expected:** "removed", Kea's subnets without 257, one commit of `dhcp/subnets.yml`. Subnet
  256 (R6's link) stays.

**b2 [AGENT]. The alert-rules install, removal path:**
`bash <home>/python/Agentic_NMAS/scripts/host-steps/c1419-install-alert-rules.sh heartbeat`,
then the same with `telemetry` (Retire's result prints each one's values) (LABOUR M11).
- **Expected:** PASS for each; Grafana holds no rule naming r7.

**b3. Skipped (D4).**

**b4 [OPERATOR, DECISION M7, M1, M2]. R6's page › Actions › Retire…,** reason "Lab 8
rehearsal: R6 reset to be added again by ZTP". Confirm by hash.
- **Expected:**
  - as b1, for `aa:bb:cc:00:04:06`, 10.255.4.2 and subnet 256;
  - "Retired"; NetBox's record `r6-retired-<id>`.
- Subnet 257 was removed at b1a, so no row names its relay as in no intent.

**b4a [OPERATOR, LAB M24]. On R6's console: `write erase`, confirm. No reload.** R6 keeps
running its configuration (and so its relay and its route to R4) until c2's reload, which then
boots it configless. R6 is retired, so no window is needed.
- **Expected:** `[OK]`; R6's adjacencies unchanged.

**b5 [AGENT]. The alert-rules install again,** heartbeat then telemetry, as b2.
- **Expected:** PASS for each; Grafana holds no rule naming r6.

**b6 [OPERATOR, DECISION; LABOUR M22, C1447]. The Planned records (D2, D9),** in NetBox's own
screens: Devices › Add, twice: `r6` and `r7`, status **Planned**, site `Branch`, role and device
type as the fleet's routers carry them, platform the fleet's IOS-XE routers' or none.
- **Expected:** both Planned in `Branch`; NetBox holds no other device named `r6` or `r7` (the
  retired records are `<name>-retired-<id>`).

### c and d. R6 and R7 added again by ZTP, each with its Day 1

**The order is interleaved, as on 2026-10-21:**
- R6 is added, boots and is promoted.
- R6's Day 1 intent is **committed**.
- Then R7 is added. R6's committed Gi3 now names the relay, and R7's reservation must exist
  before R6's helper is live, or R7 takes the pool's address with no boot file.
- Then R6's Day 1 is **deployed**, R7 is relayed and promoted, and R7's Day 1 follows.

**Day 0 is automatic; Day 1 is one approved, verified change; Day 2 is operating it** (docs/DAY1_AUTOMATION.md section 5; C1471: Day 1 is a separate step today).

**c1 [OPERATOR, DECISION M6, M1; LABOUR M8]. Devices › Add device… › ZTP for R6:**
- the values: `r6`, platform IOS-XE, role router; address 10.255.4.2/30; MAC
  `aa:bb:cc:00:04:06`; management interface `GigabitEthernet2`; gateway 10.255.4.1; **Route
  option (3): The relay's own address**; no DNS;
- then **Review the plan**, then **Create r6** (confirm by hash).
- **Expected:**
  - The review's NetBox row names the Planned record it read (b6): `r6`, site `Branch`.
  - The review's address line names the reservation with option 3 = 10.255.4.1, the relay's
    own address, and DHCP's D4 checks passing.
  - The review says it uses subnet 256 as it stands (C1460) `[READ: the review's exact words for
    an existing subnet]`.
  - The result names the reservation `aa:bb:cc:00:04:06 -> 10.255.4.2` (C1441's wording may
    print `-> ?`).
  - A pending row "r6: reserved, not leased"; r6's pending page shows no earlier device's "Last
    verify" (C1476).
- **[AGENT] reads:** Default's repository is clean, and the commit "onboarding: r6" holds both
  `host_vars/r6.yml` and `.nsot/manifest.json`.
- **Known wrong thing that looks right:** the stop notice appears 15 minutes after Create,
  counting from Create, not boot (C1467). On camera it does not appear: c2's reload follows
  Create at once.

**c2 [OPERATOR, LAB M24]. On R6's console: `reload`, do not save, confirm** (b4a erased it). R6
is not Mercury's now (retired, and its new onboarding is pending), so no window is needed. On
camera: the `reload` line only, about 10 s, and the console is closed before R6 boots (step i).
- **Expected:**
  - R6 boots configless and asks through R4 Gi5's relay.
  - Whether a `write erase` and a reload give the same configless boot as a fresh disk is
    measured here for the first time (LAB_ONE_TOPOLOGY_PLAN section 6). If R6 never asks, stop.
    The fallback is the next declared full redeploy: the operator's decision.
  - R4 logs its OSPF and OSPFv3 adjacencies to R6 down. Whether Needs attention raises them as
    rows is `[READ: Needs attention, r4's adjacency rows, after c2]`; see section h.

**c3 [AGENT]. R6 arrives:** R6's pending page, and DHCP › Leases.
- **Expected:**
  - the ZTP stage moves from `reserved_not_leased` to `leased_not_fetched` to
    `fetched_not_reached`, then "Answering: ready to Verify";
  - the lease 10.255.4.2 marked **reserved**;
  - the responder's journal: "served r6 to 10.255.4.2: 1 block(s), 468 bytes", repeated (12
    fetches in 6 s on 2026-10-20, C1444).

**c4 [OPERATOR, LABOUR M14; DECISION M1]. R6's pending page › Verify… › Verify r6.** The preview
waits until 120 s after the last fetch (C1400) and says until when.
- **Expected:**
  - the nine steps done, in this order: verify, capture, rotate, remove RW, profile, persist,
    golden, NetBox, promote;
  - the commit "onboarding: r6 verified and recorded in NetBox";
  - the Planned record from b6 set Active in place, in `Branch`, its ID the manifest's (C1421,
    its first run on a device).
- The result names the next step: "Intent can't be checked yet … Next: Actions › Seed intent…".
- On 2026-10-20, the first fetch to promotion took 9 min 21 s (PITCH_METRICS section 1).

**d1. R6's Day 1.**
1. **[OPERATOR, DECISION M1]. R6's page › Actions › Seed intent…**, confirm.
   - **Expected:** the card's intent document, the template reproducing R6, and no unmodelled
     line: AutoInstall's client-id, in either form, is the device's own (C1479).
2. **[AGENT]. The complete Day 1 document,** `2026-10-23-r6-day1.yml` in the reports folder.
   - The agent reads the new seed masked (`scripts/nmas-config-read host_vars/r6.yml`).
   - From the new seed it keeps the per-boot keys: Gi2's entry (`ipv4: dhcp`),
     `unmodeled_ack`, `call_home` and the image's default lines.
   - Everything else comes from `2026-10-21-r6-day1.yml`.
   - **Expected:** the diff against 2026-10-21's document holds only those per-boot lines.
3. **[OPERATOR, LABOUR M15]. R6's page › Intent › Edit:** replace the document with that file
   whole, and commit with the reason "Lab 8 Day 1: R6, from its stored intent".
   - **Expected:**
     - the editor's checks pass;
     - "What a deploy would send" holds additions only;
     - the commit lands;
     - R6's Gi3 (10.255.4.5, with its helper) is in committed intent, so subnet 257's relay
       reads again, and b4's relay row clears.
4. **c5 [OPERATOR, DECISION M6, M1; LABOUR M8]. Add device › ZTP for R7, HERE, before R6's
   deploy:**
   - the values: `r7`, IOS-XE, router; 10.255.4.6/30; MAC `aa:bb:cc:00:04:07`;
     `GigabitEthernet2`; gateway 10.255.4.5; Route option (3) The relay's own address; no DNS.
   - **Why here:** once R6's deploy puts the helper on Gi3, R6 relays R7's requests. Without the
     reservation, R7 takes the pool's address (10.255.4.6) with no boot file, asks for default
     files the responder refuses, and AutoInstall gives up.
   - **C1460 (D1, decided):** the review's plan now holds the link's subnet too: 10.255.4.4/30,
     the relay R6's Gi3 (10.255.4.5, from R6's committed intent, d1.3 above), the pool the far
     end's 10.255.4.6, option 3 on the reservation, no DNS, recorded as created by Add device,
     in the same hash as the reservation. Read that line before confirming. **If the review
     refuses or the subnet's write fails:** stop, note the refusal's words for C1460, then the
     manual fallback: DHCP › **Add a subnet…** for 10.255.4.4/30 (For ZTP onboarding, Route
     option (3) = 10.255.4.5), and Add device again, which now reuses that subnet.
   - **Expected:**
     - the review's NetBox row names the Planned record `r7` in `Branch` (b6);
     - the subnet 10.255.4.4/30 created (C1460's path) with Kea's own check passing;
     - the reservation `aa:bb:cc:00:04:07 -> 10.255.4.6`, with option 3 = 10.255.4.5;
     - a pending row "r7: reserved, not leased";
     - **[AGENT]** the repository clean, and "onboarding: r7" holding both files.
   **c5a [OPERATOR, LAB M24]. Right after Create r7: on R7's console, `reload`, do not save,
   confirm** (answer `no` to any dialog first). R7 is pending, so no window is needed. On
   camera: the `reload` line only, about 10 s; the console is closed before R7 boots (step i).
   - **Why now:** a C8000v boots in about 7 minutes (8.8 minutes to a lone C8000v's first
     answer, lab/REDEPLOY.md); R6's deploy (d1.5) takes about 3. So R7 is asking by the time
     R6's relay goes live, with its AutoInstall fresh, instead of waiting out a3's refusals and
     a give-up.
   - **Expected:** R7 reloads; until R6's deploy lands, its requests reach no relay, and its
     pending page stays `reserved_not_leased`.
5. **[OPERATOR, DECISION M1]. R6's page › Actions › Plan a deploy…**, read, confirm by hash.
   - **Expected preview:**
     - Loopback0 created;
     - Gi2's description, IPv6 address and OSPFv3;
     - Gi3 addressed, with its helper and RIPng;
     - `router ospf 1` with two networks in area 10 and `redistribute rip`;
     - `router rip`;
     - `ipv6 router ospf 1` and `ipv6 router rip RCN`;
     - the flags.
     - Additions only. Nothing under "Left on the device". No authorisation or declaration
       asked.
     - The line count: 43 on 2026-10-21 `[READ: the preview's count]`.
   - **Expected run:**
     - sent as confirmed;
     - Verify FULL: OSPF 0 → 1, OSPFv3 0 → 1;
     - RIP and RIPng declared and not up, since R7 has no configuration yet; saved to startup;
     - Needs attention: "The last deploy to r6 landed, and RIP, RIPng declared by its intent
       was not up after it", its action "Build or check r6's RIP, RIPng peer". It clears when the
       adjacency reader sees both up after the deploy (C1450), so after d2.
6. **[AGENT] reads after**, through Ask the device and Show commands:
   - r4 and r6, `show ip ospf neighbor`: FULL, r4 Gi5 to r6 Gi2;
   - s3, `show ip route 10.255.1.16`: O IA, no static.

**c6 [AGENT]. R7 arrives through R6's relay.**
- **[AGENT]** reads r7's pending page from d1.5's Verify until R7 is answering. R7 booted at c5a,
  so it reaches its first DHCP request about 7 minutes after it, around when R6's relay goes
  live. A configless R7 asking sends a burst about every 15 s, and Mercury's part from the
  answered request to the lease was 71 ms on 2026-10-21 (PITCH_METRICS section 1).
- **Expected:** `leased_not_fetched`, then `fetched_not_reached`, then "Answering: ready to
  Verify". On 2026-10-21 the lease came 40 ms after the request it answered, and the first fetch
  40 s after the lease.
- **If R7 is still `reserved_not_leased` 20 minutes after c5a** (about 2.5 times the 8.8-minute
  boot to a first answer), **or `asked_not_served`:** it stopped asking. **[OPERATOR, LAB
  M24]** a second `reload` on R7's console, as c5a; R7 asks again within its boot. A second
  reload is a finding for the record (why AutoInstall gave up), and Saturday's c5a timing is
  reread.

**c7 [OPERATOR, LABOUR M14; DECISION M1]. R7's pending page › Verify… › Verify r7.**
- **Expected:**
  - as c4: promoted, "onboarding: r7 verified and recorded in NetBox", the Planned record from
    b6 set Active in `Branch`;
  - the first fetch to promotion took 9 min 18 s on 2026-10-21 (PITCH_METRICS section 1);
  - Mercury reaches R7 over two relays' worth of routing: Mercury → s3 → OSPF → R4 → R6 → R7.

**d2. R7's Day 1.**
1. **[OPERATOR, DECISION M1]. Seed intent…**, confirm.
   - **Expected:** no unmodelled line: R7's serial-form client-id is its own serial, so the
     capture drops it (C1479).
2. **[AGENT].** `2026-10-23-r7-day1.yml`, built as d1.2 from `2026-10-21-r7-day1.yml` and the new
   seed's per-boot keys, without the serial-form client-id line the 2026-10-21 document carried.
3. **One deploy [OPERATOR, LABOUR M15, M16; DECISION M1]:**
   - Intent › Edit, paste the complete document, commit ("Lab 8 Day 1: R7, from its stored
     intent").
   - Then Plan a deploy…, and check Gi3.10's block: `encapsulation dot1Q 10` straight after
     `description`, before `ip address`, `ip helper-address` and `ipv6 address` (D3's seed).
   - **In any other order, do not confirm:** IOS refuses an address on a LAN subinterface before
     its encapsulation (C1478). Cancel; it is a stop.
   - **Expected:** `[READ: the preview's line count]` (2026-10-21's two deploys together sent
     31 + 4 = 35); Verify FULL, green:
     RIP 0 → 1, RIPng 0 → 1, interfaces 5 of 5 up; saved. r6's C1450 row clears at the
     adjacency reader's next read.
4. **[AGENT] reads after:**
   - r6, `show ip rip database`: 10.70.10.0/24 and 10.255.1.17/32 via 10.255.4.6;
   - r4, `show ip route 10.70.10.0`: O E2 via 10.255.4.2 on Gi5.

**d3. R6's and R7's monitoring rules (Day 2), once, for both.**
- **[OPERATOR, LABOUR M12; DECISION M1]** Monitoring › Heartbeat › re-measure: tick r6 and r7
  only, then Write and confirm.
  - Untick any device the check calls INSEPARABLE, s3 among them (C1489).
- **[AGENT, LABOUR M11, M13]** on `<nmas-host>`:
  - the install step `c1419-install-alert-rules.sh heartbeat` with the values the page prints;
  - `nmas-telemetry-rules`;
  - the install step `telemetry`.
- **Expected:** PASS for each; Grafana holds r6's and r7's heartbeat rules and their two
  telemetry rules each. The re-measure takes each window from the new device's own arrivals,
  not the retired one's (C1476) `[READ: the windows it proposes for r6 and r7]`.

**d4 [OPERATOR, DECISION each]. Topology's weak points accepted (D8; C1487).**
- **[AGENT] before:** Topology › Single points of failure: each weak point the map names, by
  key, after d2 `[READ: the list; expected r4, r6 and s3 as single points, and r4 ↔ r6 and
  r6 ↔ r7 as only links]`.
- **[OPERATOR]** for each: its **Accept…**, reason "the course handout's topology (Lab 8)",
  confirm.
- **[AGENT] after:** Topology again: each one in the weak group marked "Accepted: the course
  handout's topology (Lab 8)", counted apart from the open ones; none left open; History holds
  one row per acceptance, naming who.

### e. H5's lease on VLAN 10 through R7's relay

**e1 [AGENT]. DHCP › Subnets and Leases.**
- **Expected:**
  - 10.70.10.0/24 still present (Retire touches no host subnet).
  - In its leases, H5 (`aa:bb:cc:00:70:05`) holds an address from 10.70.10.100 to 10.70.10.200
    through R7's relay (10.70.10.100 on 2026-10-21).
  - **Ask the device** on r7, `show ipv6 interface GigabitEthernet3.10`: 2001:DB8:70:10::1/64 and
    router advertisements on.
- **If no lease appears within a few minutes of R7's Gi3.10 address landing:** whether H5's
  script asks again after its first lease is `[READ: the lab repository's
  configs/host-net-lab89.sh, whether it renews after the first lease]`.
  - **[OPERATOR, LAB]** H5's DHCP run again from H5's shell on `<lab-host>`. Mercury does not
    manage hosts.

### f. Lab 8's checks (docs/LAB8_LAB9_PLAN.md, "Lab 8's checks")

**[AGENT]** reads each through Mercury: a device page's **Ask the device** for one device, or
**Show commands** for several (a saved set "Lab 8 checks" is worth committing once, so the
recording can run it in one press). H5's own checks are **[OPERATOR, LAB]** from H5's shell,
because Mercury does not manage the Linux hosts. The expected answers are 2026-10-21's
(LAB8_MORNING_WALK section 8; PITCH_METRICS section 2b).

| # | Check | Read | Expected |
|---|---|---|---|
| 1 | R4 an ABR for areas 0 and 10 | r4: `show ip ospf` | "an area border and autonomous system boundary router"; areas 0 and 10 |
| 2 | R4–R6 OSPF and OSPFv3; R6–R7 RIPv2 and RIPng | r4 and r6: `show ip ospf neighbor`, `show ipv6 ospf neighbor`; r6 and r7: `show ip rip database`, `show ipv6 rip RCN database`; or each Neighbours tab | FULL on r4 Gi5 / r6 Gi2, both families; R6's and R7's one RIP source is each other (10.255.4.6 and 10.255.4.5); R6 holds 10.70.10.0/24, 10.255.1.17/32, 2001:DB8:70:10::/64 and 2001:DB8:1::17/128 from R7 |
| 3 | Redistribution as designed | r4: `show ip route 10.70.10.0`, `show ip route 10.255.1.17`; r7: `show ip route 0.0.0.0`, `show ipv6 route ::/0` | r4: both O E2, metric 20, via 10.255.4.2 on Gi5, from 10.255.1.16. R7's IPv4 default is the bootstrap's static via 10.255.4.5 (D6: by design, not RIP); its IPv6 default is RIPng's from R6 |
| 4 | Adjacency counts as before, plus R6 | each device's Neighbours tab | r1 OSPF 5/5, OSPFv3 3/3; r2 the same; r3 BGP 2/2, OSPF 6/6, OSPFv3 4/4; r4 BGP 2/2, OSPF 7/7, OSPFv3 5/5; r6 OSPF 1/1, OSPFv3 1/1; s3 OSPF 5/5; s4 OSPF 5/5 |
| 5 | R6 and R7 reachable | Devices (both Answering); r4: `ping 10.255.1.16 source Loopback0`, `ping 10.255.1.17 source Loopback0`, `ping 2001:DB8:1::17 source Loopback0` | each 5 of 5 |
| 6 | H5's Kea lease through R7's relay | DHCP › Leases | step e's lease |
| 7 | H5 reaches 8.8.8.8 | **[OPERATOR, LAB]** from H5: `ping 8.8.8.8`, `traceroute 8.8.8.8`, `curl` of the web server; through Mercury, r7: `traceroute 8.8.8.8 source GigabitEthernet3.10` | 5 of 5; R7 → R6 → R4 → R5 → 8.8.8.8; "hello world from RCN". R7's own traceroute `[READ: never run before; its hops]` |
| 8 | IPv6 | **[OPERATOR, LAB]** H5's SLAAC address and `ping 2001:4860:4860::8888`; r4: `ping 2001:DB8:70:10::1 source Loopback0` | an address in 2001:db8:70:10::/64; 3 of 3; 5 of 5 |

### g. NetBox brought up to the deployed intent (Lab 8 step 9)

**g1 [OPERATOR, DECISION M1]. r6's page › NetBox › Import into NetBox…:** the dry-run card, then
**Import**. Then the same for r7. Or use NetBox › Default › **Import into NetBox…** for the
whole network.
- **Expected card:** every object it would create or change. It shows the cables from LLDP
  between managed devices (R4 Gi5 – R6 Gi2, R6 Gi3 – R7 Gi2) and each other LLDP neighbour
  reported, not made: R7 Gi3 to H5, since H5 is not managed.

**What it writes** (each fix deployed):
- **The records:** r6's and r7's, found by the NetBox ID the manifest holds (C1009's fix, D9),
  in `Branch`; no second record in Default.
- **Management addresses (C1442):** 10.255.4.2/30 on r6's Gi2 and 10.255.4.6/30 on r7's Gi2;
  Loopback0 holds only the loopback. The platform the fleet's IOS-XE routers carry (C1442, and
  C1506 for a record Mercury wrote as "IOS").
- **The retired records' addresses (C1494):** none left on them, so the new records take
  10.255.4.2/30, 10.255.4.6/30 and the loopbacks 10.255.1.16/32 and 10.255.1.17/32. One a
  person made is named on the card with **Free <address>** (C1504).
- **r7's Gi3.10 (C1492):** a virtual interface under Gi3, with 10.70.10.1/24 and
  2001:db8:70:10::1/64, 802.1Q tagged with VLAN 10 from the Branch site's VLAN group (P3). A
  refusal naming the site's groups is a stop: read P3's VLAN group first.
- **Prefixes it creates** are scoped to Default, the network's site (C1515); P3 scoped the two
  branch prefixes by hand. **No loopback becomes a prefix** (C1516): 10.255.1.16/32,
  10.255.1.17/32 and their IPv6 /128s are addresses on Loopback0, inside P3's loopback pools.

- **Cables (built):** R4 Gi5 – R6 Gi2 and R6 Gi3 – R7 Gi2. A cable from R7 Gi3 to H5, if
  wanted, is LABOUR in NetBox (M22).
- **[AGENT] reads after:** each device's NetBox tab ("NetBox holds …", or **What NetBox lacks**),
  and the import's History row (kind NetBox).

### h. Needs attention at the end

**h1 [OPERATOR, DECISION M1]. Save All** for Default, after every device is at its intent (P5
put s3 there).
- **Expected:** every device captured, and `Baseline: earned` with a new `baseline/<ts>`.
- A save failing in a stall names its device and cause (C1488). Retry it alone (C1490).

**h2 [OPERATOR, DECISION and LABOUR M4]. A break-glass export** holding R6's and R7's new
credentials. Saturday's Retire needs it, as P6 did.

**h3 [AGENT]. Needs attention, read and compared with the target below.** A row names something
wrong, an action, and how it clears. A row that is expected to remain is one whose cause is
known, registered and not fixed. It is never acknowledged away to make the page look clean.

**Today's rows** (8, read on the host at ~16:20 UTC, 2026-10-21, after P5):

| Row | At the end | Why | How it clears |
|---|---|---|---|
| "nmas-heartbeat-check is failing" (since 2026-10-18) | **remains** | s3 is INSEPARABLE: its heartbeat gaps (569 to 623 s after the pinning) exceed the 300 s setting (C1318; HOST_TUNING, change 2) | the hourly check reads ok |
| "r1's OSPF adjacency to 10.255.1.23 went down 40 times in the last day" (s3) | **remains** while C1485's drops continue (D5); Friday's count `[READ]` | s3's vIOS clock runs slow under the lab VM's contention (C1485) | a day with no drop, or acknowledged within its band (D5) |
| "r1's OSPF adjacency to 10.255.1.24 went down 13 times in the last day" (s4) | **remains**, as the row above; Friday's count `[READ]` | s4's clock, the same cause | as above |
| "r1's OSPF adjacency to 10.255.1.13 went down 1 time in the last day" (r3, at 08:52 UTC) | **gone** a day after its drop; **present** if Friday's backup window drops it again | the nightly backup's load (C1514) | a day with no drop, or acknowledged with that cause |
| "The last commit earned no baseline: a deploy to s3 did not cover the network" | **gone** | h1's Save All earns one | a later save that earns a baseline |
| "9 new host keys accepted during 'lab host reboot … and lab redeploy …'" (2026-10-19) | **gone** once the operator acknowledges it (the morning plan's step 6) | the 2026-10-19 redeploy's new keys, under its declared window | acknowledged after reviewing each key in History |
| "NetBox holds less than r7's committed configuration: 1 interface, 2 addresses, 0 cables to add" | **gone** | the old r7's row; b1 retires it, and g imports the new r7 with Gi3.10 (C1492) | the import lands Gi3.10 |
| "2 alerts began together" (since 12:01 UTC) | **gone** unless the alerts still fire `[READ]` | two Grafana alerts with one onset | the alerts stop firing |

**Rows the walk raises, which must be gone at the end:**
- r7's "not answering" and drift rows (a3): they go with R7's Retire (b1);
- r6's and r7's pending onboarding rows, including C1467's stop notice: gone at promotion
  (c4, c7);
- r6's C1450 row, "The last deploy to r6 landed, and RIP, RIPng … was not up after it" (d1.5):
  gone when the adjacency reader sees RIP and RIPng up after d2;
- any "NetBox holds less than r6's …" or "… r7's …" row for the new records: gone after g;
- heartbeat and telemetry rules missing or extra for r6 and r7, through job health: gone after
  b2, b5 and d3;
- each weak point Topology names: Accepted at d4, so none is open;
- the break-glass record out of date after R6's and R7's rotations: gone after h2.

**Event rows, a DECISION each (M5):**
- r4's OSPF and OSPFv3 adjacencies to 10.255.1.16 logged down when R6 was erased (c2), if raised.
  **Recommendation:** acknowledge each with the reason "Lab 8 rehearsal: R6 reset by write erase
  and reload". Without an acknowledgement they clear a day after the drop.
- R7's reload (a2) was inside its window, so it is counted under What was checked and raises no
  row. A "restarted unexpectedly" row for r7 means the window did not cover it: a stop, read
  before acknowledging.

**The target:** the heartbeat check (C1318) and r1's adjacencies toward s3 and s4 (C1485),
plus r1's toward r3 only if Friday's backup window dropped it again (C1514). Each is shown with
its finding as a caption, so the recording can say why it is there (scene 17).

### i. The rehearsal's recording, reviewed (Friday only)

**i1 [OPERATOR, LAB]. Record the whole sitting** with Saturday's capture setup, from c1 to h3.

**i2 [OPERATOR, with the AGENT]. List every frame that shows any of these, with its time in the
recording:**
- a bootstrap's contents (the file the TFTP responder serves, or its lines in a preview);
- a one-time password, in any form;
- a console loading a configuration (AutoInstall's file load and the lines after it);
- an unmasked program (a deploy or Verify program, or Ask the device's answer, with a secret
  in clear).

Where they can appear, for the review to check first:
- **c2 and c5a (the consoles):** the boot after the `reload`, where AutoInstall loads the
  bootstrap;
- **c3, c4, c6, c7 (the pending pages and Verify):** the served-file lines and Verify's preview;
- **d1.3 and d2.3 (the intent editor):** secret references only, never a value;
- **d1.5 and d2.3 (Plan a deploy):** the program, masked;
- **f (Show commands):** any command whose answer carries configuration.

**i3 [AGENT]. Afterwards, one line per frame: what showed, and how Saturday avoids it** (the
console closed after the `reload` line, a panel left collapsed, a cut in the edit, or a
finding where Mercury itself showed a secret). Written into docs/LAB8_VIDEO_OUTLINE.md's rules
before Saturday.

---

## 4. Placeholders to fill (`[READ: …]`)

**Open, read on the day:**
1. Settings › Installation: the running commit carries C1009's and C1516's fixes (P1, D9).
2. Credentials: the newest break-glass export's time against R6's and R7's last rotation (P6).
3. Add device's review: its exact words for an existing subnet (c1).
4. Needs attention after c2: whether r4's adjacency drops to R6 are raised as rows (c2, h3).
5. R6's Day 1 preview: its line count (d1.5); R7's (d2.3).
6. The heartbeat re-measure's proposed windows for r6 and r7 (d3).
7. Topology › Single points of failure: the weak points the map names after d2 (d4).
8. The lab repository's `configs/host-net-lab89.sh`: whether H5 renews after its first lease (e1).
9. R7's `traceroute 8.8.8.8 source GigabitEthernet3.10`: its hops (f, check 7).
10. Needs attention at h3: r1's flap counts toward s3 and s4, and whether the 12:01 incident
    still fires.

**Filled 2026-10-21:**
- **The running commit (~16:2x UTC):** f14bd314, carrying C1442, C1450, C1460 part 1, C1476,
  C1477, C1479, C1487, C1489, C1492, C1494, C1499 and C1504; ed58d33e (C1506) deploys at
  17:08 UTC.
- **C1499's Retry:** deployed, and used for P5 (~16:05 UTC).
- **`_common.j2`:** Current since the operator took the seed (D3).
- **R7's first Gi3.10 keys:** no longer needed; R7's Day 1 is one deploy (D3).
- **NetBox's VLAN groups (~16:1x UTC):** Mercury's token reads them (no 403); NetBox holds none
  yet, one site (Default) and one VLAN 10 (the core's, in no group). P3 makes the Branch group.
- **`nmas-heartbeat-check`:** fails on INSEPARABLE s3 (C1318); it remains.
