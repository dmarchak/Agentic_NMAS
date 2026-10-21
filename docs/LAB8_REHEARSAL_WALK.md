# Lab 8: Friday's rehearsal walk (2026-10-23)

**Status: a draft for the operator's review, written 2026-10-21. Nothing in it has run.** It is
the rehearsal of Saturday's recording (docs/LAB8_LAB9_PLAN.md section 11, item 12): R7's
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
- **Today:** C1460's part 1 (Add device adds its link's ZTP subnet; Retire removes one it
  added) is built (c05330b0) and was not deployed when R7 was added on 2026-10-21 (PITCH_METRICS
  section 1, R7's table). Part 2 (the link's NetBox prefix) and the per-subnet firewall step are
  not built. Whether part 1 is on the host by Friday: `[READ: Settings › Installation, the
  running commit, against c05330b0]`.
- **If C1460 is not deployed:** subnets 256 and 257 stay as they are and are reused. Retire
  touches no subnet; Add device writes only the reservation into the existing subnet.
- **If C1460 is deployed and the subnets are kept:** per C1460's row, an existing matching
  subnet is used and recorded as not Mercury's, so Retire keeps it and says so. Nothing is
  removed or created. The run is today's, with the review's address line naming the subnet it
  uses.
- **If C1460 is deployed and the subnets are removed first** (DHCP › Subnets › the row's
  **Remove…**, after each device is retired, since onboarding's reservation blocks the removal):
  Add device creates each subnet in the same preview and hash as the reservation, which is the
  better video (one LABOUR step fewer, M9). The cost is one more first-time path that can fail
  live, plus the firewall host step for each new subnet (M10; the host's firewall admits by
  default today, C1435, so TFTP still arrives, but job health's `ztp-firewall` row reads the
  host step's record).
- **Recommendation: keep both subnets,** unless C1460 has been walked once on a throwaway link
  before Friday. Friday is a rehearsal of Saturday, not the first run of a path.

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

**D3. Default takes the shipped template seed before Friday (C1498), so R7's Gi3.10 can be one
deploy (C1478).**
- C1478 is fixed in the shipped template: `encapsulation dot1Q` now renders before every address
  line. Default renders through its own copy, `_common.j2`, which is two shipped versions
  behind. Until Default takes it, Default renders the old order, and R7's Day 1 stays two
  deploys, as it ran on 2026-10-21.
- **How:** Templates › the `_common.j2` row › **Bring in the shipped version…**. Its `measure`
  step renders every bound device both ways and lists what each one's render gains and loses. The
  confirm revokes the approval of every template that imports the file. No device deploys until
  each template is approved again: Templates › **Approve…**, a DECISION each
  (docs/manual/how-it-works/bring-template.md).
- **Recommendation:** the agent reads the `measure` step's per-device delta first (the card is a
  preview and writes nothing). Take the seed before Friday only if no device's render changes
  except by the two fixes it carries (K7's packs where intent uses them, `hold_queue` where intent
  uses it, and the encapsulation order), and both templates approve again cleanly. Otherwise
  leave it, and R7's Day 1 is two deploys. Both paths are written in step d2. The same seed also
  unblocks C1485's `hold_queue` lever.

**D4. C1432's measurement on R6, just before R6's Retire.**
- docs/LAB8_MORNING_WALK.md section 1a, step 5b (skipped on 2026-10-20) planned it there,
  because Retire then takes R6 away and nothing has to be removed. It is two intent edits and two
  deploys on R6, with the capture read before and after.
- **Recommendation: run it only if steps a and b1 finish on time;** otherwise leave it for the
  next re-add. It measures a B finding (C1432, which blocks C1426). It is not part of what
  Saturday records.

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

**D8. Topology's weak points (C1487), only if C1487 has landed.**
- r4, r6 and s3 as single points of failure, and r4 ↔ r6 as the only link, are the handout's
  design. With C1487 built, each is declared "Accepted: <reason>" by a verified person: a
  DECISION each, with a reason.
- **Recommendation:** accept each with the reason "the course handout's topology (Lab 8)".
  Accept any further weak point the map names (for example r6 ↔ r7) the same way
  `[READ: Topology › Single points of failure, after step d2]`. Without C1487 the map tags them
  as weak points, and the video says they are the handout's design.

---

## 2. Before the sitting (P1 to P9)

**P1 [AGENT]. Mercury on the host carries every fix that landed for Friday**, deployed by
`nmas-deploy --wait` (CI green) before the sitting, never during it. Whatever has landed of
C1442, C1460, C1476, C1479, C1487, C1492, C1494 and C1499 is named with the running commit.
- **Expected:** "deployed <sha>" with CI's pass named; job health's not-ok rows as before, none
  new. `[READ: which of C1442, C1460, C1476, C1479, C1487, C1492, C1494 have landed and are
  deployed]`.

**P2 [AGENT]. The host is not stalling.**
- Read-only, through `scripts/nmas-host`: `lab/pinning/check-pinning.sh` on `<lab-host>`, then the
  stall script for the last 60 minutes (docs/HOST_TUNING.md, the metrics table).
- **Expected:** PINNING HOLDS; failed scrapes and OSPF dead-timer drops at or below the change-2
  window's (38 failed scrapes and 2 drops in 60 minutes). Worse is a stop: a stalling host fails
  saves and Verify's reads (C1490), which is a rehearsal of the stall, not of Lab 8.

**P3 [OPERATOR, DECISION]. D2's Planned records, if chosen:** R6 and R7 planned in NetBox, in
Default's site, with role, platform and the device type the fleet's routers carry (LABOUR M22).
- **Expected:** both records Planned, and named `r6` and `r7`. If C1494 has not landed, the
  retired records keep their names `<name>-retired-<id>`, so the names are free.

**P4 [OPERATOR, DECISION]. D3's template seed, if chosen,** then each template approved again.
- **Expected:** Templates › `_common.j2` reads **Current**; the IOS-XE and IOS templates
  **approved** by the operator.

**P5 [OPERATOR, DECISION]. s3's IP SLA sent: Monitoring › IP SLA › Retry s3** (C1499's Retry:
"Committed, not yet on the device"), a new scoped preview and confirm for s3 alone.
- **Expected:** the deploy verified and saved; s3 runs its probe at the policy's frequency;
  Needs attention's "The last IP SLA send to s3: failed" gone. `[READ: C1499's Retry on the host
  (this draft's tree does not yet hold it)]`.

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
  1/1; s3 OSPF 5/5; s4 OSPF 5/5), and today's Needs attention rows (section h) less P5's.

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
   device created it and nothing else is in it (C1460, when deployed).
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
- **the retired record's IP addresses:**
  - **If C1494 has landed:** Retire's NetBox step deletes the addresses Mercury recorded as
    created and unassigns the rest, each with its before recorded. The retired record holds no
    address that the new device needs.
  - **Else:** the addresses stay assigned to `<device>-retired-<id>` (C1494: on 2026-10-21,
    10.255.4.2/30 stayed on `r6-retired-21` Loopback0), and the new device's import cannot be
    given them (step g).

**b1 [OPERATOR, DECISION M7, M1, M2]. R7's page › Actions › Retire…,** reason "Lab 8 rehearsal:
R7 reset to be added again by ZTP". Read the card, then confirm by its hash.
- **Expected card:**
  - every step listed with its work. Reservations: ZTP's for `aa:bb:cc:00:04:07` in subnet 257.
    Leases: 10.255.4.6.
  - With C1460 deployed: the `ztp_subnet` step says subnet 257 stays (a person added it).
  - What is generated and so dropped, and what survives.
  - No refusal. Retire needs no SSH, and P6's export holds R7's credential.
- **Expected result:** "Retired"; the name `r7` free; NetBox's record `r7-retired-<id>`,
  Decommissioning, its addresses as C1494's state says above. R7's page becomes its retired
  record. R7's window from a1 covers nothing more; it lapses at its end.

**b2 [AGENT]. The alert-rules install, removal path:**
`bash <home>/python/Agentic_NMAS/scripts/host-steps/c1419-install-alert-rules.sh heartbeat`,
then the same with `telemetry` (Retire's result prints each one's values) (LABOUR M11).
- **Expected:** PASS for each; Grafana holds no rule naming r7.

**b3 [OPERATOR and AGENT]. D4's measurement on R6, only if chosen:** docs/LAB8_MORNING_WALK.md
section 1a, step 5b, items 1 to 5 (R6's Gi3 helper and IPv6 address and the NTP list changed
twice, each a preview, a confirm by hash and Verify). Its item 6 is replaced by b4.
- **Expected:** C1432's prediction read in R6's capture: both values of each present. Each line
  is recorded in C1432.

**b4 [OPERATOR, DECISION M7, M1, M2]. R6's page › Actions › Retire…,** reason "Lab 8
rehearsal: R6 reset to be added again by ZTP". Confirm by hash.
- **Expected:**
  - as b1, for `aa:bb:cc:00:04:06`, 10.255.4.2 and subnet 256;
  - "Retired"; NetBox's record `r6-retired-<id>`.
- From here until R6's Day 1 intent is committed (d1.3), a row may name 10.255.4.4/30's relay as
  in no intent (D4's check on subnet 257). It is expected, and it clears at d1.3.

**b5 [AGENT]. The alert-rules install again,** heartbeat then telemetry, as b2.
- **Expected:** PASS for each; Grafana holds no rule naming r6.

### c and d. R6 and R7 added again by ZTP, each with its Day 1

**The order is interleaved, as on 2026-10-21:**
- R6 is added, boots and is promoted.
- R6's Day 1 intent is **committed**.
- Then R7 is added. R6's committed Gi3 now names the relay, and R7's reservation must exist
  before R6's helper is live, or R7 takes the pool's address with no boot file.
- Then R6's Day 1 is **deployed**, R7 is relayed and promoted, and R7's Day 1 follows.

**Day 0 is automatic; Day 1 is one approved, verified change (two for R7 without D3); Day 2 is
operating it** (docs/DAY1_AUTOMATION.md section 5; C1471: Day 1 is a separate step today).

**c1 [OPERATOR, DECISION M6, M1; LABOUR M8]. Devices › Add device… › ZTP for R6:**
- the values: `r6`, platform IOS-XE, role router; address 10.255.4.2/30; MAC
  `aa:bb:cc:00:04:06`; management interface `GigabitEthernet2`; gateway 10.255.4.1; **Route
  option (3): The relay's own address**; no DNS;
- then **Review the plan**, then **Create r6** (confirm by hash).
- With D2: the review's NetBox row names the Planned record it read.
- **Expected:**
  - The review's address line names the reservation with option 3 = 10.255.4.1, the relay's
    own address, and D4's checks passing.
  - With C1460 deployed, the review also says it uses subnet 256 as it stands
    `[READ: the review's exact words for an existing subnet]`.
  - The result names the reservation `aa:bb:cc:00:04:06 -> 10.255.4.2` (C1441's wording may still
    print `-> ?`).
  - A pending row "r6: reserved, not leased".
- **[AGENT] reads:** Default's repository is clean, and the commit "onboarding: r6" holds both
  `host_vars/r6.yml` and `.nsot/manifest.json`.
- **Known wrong things that look right, until their fixes land:**
  - r6's pending page shows the retired r6's "Last verify" (C1476, member 1);
  - the Devices list says "awaiting DHCP · pending: not reached yet" while the page moves on
    (C1477);
  - the stop notice appears 15 minutes after Create, counting from Create, not boot (C1467).

**c2 [OPERATOR, LAB M24]. On R6's console: `write erase`, confirm; `reload`, do not save,
confirm.** R6 is not Mercury's now (retired, and its new onboarding is pending), so no window is
needed.
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
  - a new NetBox ID, Active (with D2, the Planned record set to Active).
- The result names the next step: "Intent can't be checked yet … Next: Actions › Seed intent…".
- On 2026-10-20, the first fetch to promotion took 9 min 21 s (PITCH_METRICS section 1).
- **Without C1494:** the new record lacks 10.255.4.2/30, which the retired record still holds.
  Verify still promotes R6, as on 2026-10-21, when the new r6 became NetBox 22 with primary
  10.255.1.16/32 (C1494's row).

**d1. R6's Day 1.**
1. **[OPERATOR, DECISION M1]. R6's page › Actions › Seed intent…**, confirm.
   - **Expected:** the card's intent document, and the template reproducing R6.
   - **Unmodelled lines:** none if AutoInstall's MAC-form client-id was the one answered, as for
     R6 on 2026-10-21, whose relay was already up when it booted. One line if the serial form was
     answered (C1479, unless it has landed).
2. **[AGENT]. The complete Day 1 document,** `2026-10-23-r6-day1.yml` in the reports folder.
   - The agent reads the new seed masked (`scripts/nmas-config-read host_vars/r6.yml`).
   - From the new seed it keeps the per-boot keys: Gi2's entry (`ipv4: dhcp` and its
     client-id line), `unmodeled_ack`, `call_home` and the image's default lines.
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
   - **Expected:**
     - the reservation `aa:bb:cc:00:04:07 -> 10.255.4.6`, with option 3 = 10.255.4.5;
     - a pending row "r7: reserved, not leased";
     - **[AGENT]** the repository clean, and "onboarding: r7" holding both files;
     - without C1476, r7's pending page shows a "Last verify" or "Last abandon" that is not
       this onboarding's.
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
     - RIP and RIPng declared and not up, since R7 has no intent yet: amber, drawn "done" (C1450);
     - saved to startup.
6. **[AGENT] reads after**, through Ask the device and Show commands:
   - r4 and r6, `show ip ospf neighbor`: FULL, r4 Gi5 to r6 Gi2;
   - s3, `show ip route 10.255.1.16`: O IA, no static.

**c6 [AGENT, then OPERATOR if needed]. R7 arrives through R6's relay.**
- **[AGENT]** reads r7's pending page within about 2 minutes after d1.5 verified. A configless R7
  still asking sends a burst about every 15 s, and Mercury's part from the answered request to
  the lease was 71 ms on 2026-10-21 (PITCH_METRICS section 1).
- **Expected:** `leased_not_fetched`, then `fetched_not_reached`. On 2026-10-21 the lease came
  40 ms after the request it answered, and the first fetch 40 s after the lease.
- **If R7 is still `reserved_not_leased` after about 2 minutes, or `asked_not_served`:** it has
  stopped asking. That is likely, since the refusals in a3 and any pool lease taken between b1
  and c2 each send AutoInstall down its give-up path.
  - **[OPERATOR, LAB M24]** on R7's console: answer `no` to any dialog, `reload`, confirm. No
    window is needed: R7 is pending.
  - **Expected:** R7 asks again within its boot, and the stages advance.

**c7 [OPERATOR, LABOUR M14; DECISION M1]. R7's pending page › Verify… › Verify r7.**
- **Expected:**
  - as c4: promoted, "onboarding: r7 verified and recorded in NetBox", a new NetBox ID;
  - the first fetch to promotion took 9 min 18 s on 2026-10-21 (PITCH_METRICS section 1);
  - Mercury reaches R7 over two relays' worth of routing: Mercury → s3 → OSPF → R4 → R6 → R7.

**d2. R7's Day 1.**
1. **[OPERATOR, DECISION M1]. Seed intent…**, confirm.
   - **Expected:** if the serial-form client-id was answered, the seed flags one unmodelled line
     (C1479, unless it has landed). R7 asked long before its relay answered on 2026-10-21, and the
     serial form won then.
2. **[AGENT].** `2026-10-23-r7-day1.yml`, built as d1.2 from `2026-10-21-r7-day1.yml` and the new
   seed's per-boot keys.
   - **Without D3, also `2026-10-23-r7-day1-part1.yml`:** the same document with Gi3.10's
     `ipv4`, `ipv6` and `helper_addresses` taken out. That matches 2026-10-21's second deploy
     sending 4 lines: the interface line and those three
     `[READ: History › r7, the intent commit before 03:12 UTC on 2026-10-21, "Show the change":
     which Gi3.10 keys the first deploy held]`.
3. **Which path:** `[READ: Templates › _common.j2 › "Against the shipped version"]`.
   **Current** (D3 taken) is one deploy; **Behind** is two.
4. **One deploy [OPERATOR, LABOUR M15, M16; DECISION M1]:**
   - Intent › Edit, paste the complete document, acknowledge the client-id line if the editor
     lists it, commit ("Lab 8 Day 1: R7, from its stored intent").
   - Then Plan a deploy…, and check Gi3.10's block: `encapsulation dot1Q 10` straight after
     `description`, before `ip address`, `ip helper-address` and `ipv6 address`.
   - **In any other order, do not confirm:** IOS refuses an address on a LAN subinterface before
     its encapsulation (C1478). Cancel, and take the two-deploy path.
   - **Expected:** Verify FULL, green: RIP 0 → 1, RIPng 0 → 1, interfaces 5 of 5 up; saved.
5. **Two deploys [OPERATOR, LABOUR M15, M16; DECISION M1 twice]:**
   - **Part 1:** paste `…-part1.yml`, commit, plan, confirm.
     - **Expected, as 2026-10-21's first deploy:** 31 lines; Verify green; RIP 0 → 1, RIPng
       0 → 1; interfaces 4 of 5 up; routes 5 → 8; saved.
   - **Part 2:** paste the complete document, commit, plan, confirm.
     - **Expected, as the second:** 4 lines; Verify green; RIP 1/1, RIPng 1/1; interfaces 5 of
       5 up; routes 8 → 10; saved.
6. **[AGENT] reads after:**
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
  telemetry rules each.
- **Without C1476's member 14:** the re-measure takes each window from the name's arrivals over
  7 days, which include the retired device's. `[READ: the windows the re-measure proposes for r6
  and r7, against 2026-10-21's]`.

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

**What it should write, by what has landed:**

| Finding | If landed | Else (as on 2026-10-21) |
|---|---|---|
| **C1442** (where a DHCP-leased management address goes) | 10.255.4.2/30 on r6's Gi2 and 10.255.4.6/30 on r7's Gi2; the platform as the fleet's routers carry it; Loopback0 holds only the loopback | the management address lands on Loopback0, and the platform reads "IOS"; Topology draws r4 Gi5 ↔ r6 Gi2 as "not in committed intent" and no RIP edge R6–R7 |
| **C1494** (the retired records' addresses) | the new records take 10.255.4.2/30, 10.255.4.6/30 and the loopbacks 10.255.1.16/32 and 10.255.1.17/32 | the retired records still hold them, and the import cannot give them to the new records. The remedy today is LABOUR in NetBox's own screens (M21): delete `r6-retired-<id>` and `r7-retired-<id>`, as `r6-retired-11` was on 2026-10-20, or unassign their addresses, then import again |
| **C1492** (a routed dot1Q subinterface) | r7's Gi3.10 as a virtual interface under Gi3, with 10.70.10.1/24 and 2001:db8:70:10::1/64, its VLAN R7's site's VLAN 10 from its VLAN group. The import refuses, naming it, when the group holds none `[READ: NetBox › R7's site › VLAN groups: the group and VLAN 10 exist, and Mercury's token can read VLAN groups (C1424)]` | POST 400 "untagged_vlan: Interface mode does not support untagged vlan"; r7 lacks Gi3.10, and the row "NetBox holds less than r7's committed configuration: 1 interface, 2 addresses" stays |

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

**Today's rows** (read on the host at 06:37 UTC, 2026-10-21):

| Row | At the end | Why | How it clears |
|---|---|---|---|
| "The last deploy to r6: done" | **remains**, as the new r6's row, unless C1450 has landed | R6's Retire cuts the old r6's receipts (C1334). But the new R6's Day 1 (d1.5) is amber again, with RIP and RIPng unmet until R7 exists (C1450) | another deploy or restore of r6 (C1450 changes this) |
| "The last IP SLA send to s3: failed" | **gone** | P5 sent s3's probes (C1499's Retry) | s3's golden carries the committed intent |
| "nmas-heartbeat-check is failing" | `[READ: Job health › nmas-heartbeat-check, its last run's reason]`; expected to **remain** if it is s3's jitter (C1318) | s3's heartbeat gaps were 569 to 623 s after the pinning, against a 300 s setting (HOST_TUNING, change 2) | the hourly check reads ok |
| "r1's OSPF adjacency to 10.255.1.24 went down 10 times in the last day" | **remains** while C1485's drops continue (D5) | s4's vIOS clock runs slow under the lab VM's contention; 2 drops an hour remained after change 2 | a day with no drop, or acknowledged within its band (D5) |
| "The network's last baseline was not earned (pipeline)" | **gone** | h1 earned one | a later decision that earns a baseline |
| "NetBox holds less than r7's committed configuration: 1 interface, 2 addresses" | **gone** if C1492 has landed and g ran; else **remains** | Gi3.10 and its two addresses (C1492) | the import lands Gi3.10 |

**Rows the walk raises, which must be gone at the end:**
- r7's "not answering" and drift rows (a3): they go with R7's Retire (b1);
- the relayed subnet's relay "in no intent" (b4): gone at d1.3;
- r6's and r7's pending onboarding rows, including C1467's stop notice: gone at promotion
  (c4, c7);
- any "NetBox holds less than r6's …" or "… r7's …" row for the new records: gone after g, if
  C1494 has landed or M21 was done;
- heartbeat and telemetry rules missing or extra for r6 and r7, through job health: gone after
  b2, b5 and d3;
- the break-glass record out of date after R6's and R7's rotations: gone after h2.

**Event rows, a DECISION each (M5):**
- r4's OSPF and OSPFv3 adjacencies to 10.255.1.16 logged down when R6 was erased (c2), if raised.
  **Recommendation:** acknowledge each with the reason "Lab 8 rehearsal: R6 reset by write erase
  and reload". Without an acknowledgement they clear a day after the drop.
- R7's reload (a2) was inside its window, so it is counted under What was checked and raises no
  row. A "restarted unexpectedly" row for r7 means the window did not cover it: a stop, read
  before acknowledging.

**The target:** at most rows 1, 3 and 4 of the first table, plus row 6 if C1492 has not landed.
Each is named with its finding, so the recording can say why it is there.

---

## 4. Placeholders to fill (`[READ: …]`)

1. Settings › Installation: the running commit, and which of C1442, C1460, C1476, C1479, C1487,
   C1492, C1494 it carries (D1, P1).
2. C1499's Retry on the host (P5).
3. Credentials: the newest break-glass export's time against R6's and R7's last rotation (P6).
4. Add device's review: its exact words for an existing subnet once C1460 is deployed (c1).
5. Needs attention after c2: whether r4's adjacency drops to R6 are raised as rows (c2, h3).
6. R6's Day 1 preview: its line count (d1.5).
7. History › r7: the intent commit before 03:12 UTC on 2026-10-21, which Gi3.10 keys the first
   deploy held (d2.2).
8. Templates › `_common.j2`: Current or Behind (d2.3).
9. The heartbeat re-measure's proposed windows for r6 and r7 (d3).
10. The lab repository's `configs/host-net-lab89.sh`: whether H5 renews after its first lease (e1).
11. R7's `traceroute 8.8.8.8 source GigabitEthernet3.10`: its hops (f, check 7).
12. NetBox: R7's site's VLAN group and VLAN 10, and whether Mercury's token reads VLAN groups
    (g, C1424).
13. Job health › `nmas-heartbeat-check`: its last run's reason (h3).
14. Topology › Single points of failure: the weak points the map names after d2 (D8).
