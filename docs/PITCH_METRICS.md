# Pitch metrics: measured, never estimated

**What this is.** The numbers the project's showcase may quote, each read from a record:
deploy receipts, History and the repository's commits, the ZTP responder's journal, CI's runs.
A number nobody read from a record is not here. A number the operator observed and no record
holds yet is marked *operator-reported*. A gap where a record should exist is said, with the
finding that closes it. **Kept current through the Lab 8 and Lab 9 walks**: each walk's
onboardings and deploys are added the day they run.

**How each is read** (read-only, so a later reader can repeat it):
- **Deploys:** `receipts.read(<network>, device=<d>)`, each row's `at`, `completed_at`,
  `program_lines`, `matches_confirmed`, `checks` (`verify_scope`, `neighbours`,
  `interfaces_up`, `routes`, `read_back`, `intent_unmet`), `rollback` and `saved_startup`.
  The program itself is never read for this page.
- **Onboardings:**
  - the network repository's commit subjects and times (`onboarding: <d>`, `credential: <d>`,
    `onboarding: <d> verified`);
  - the ZTP responder's journal (`journalctl -u nmas-ztp-responder`, "served <d>");
  - Kea's lease record;
  - the operator's own steps, as `docs/MANUAL_STEPS.md` classes them.
- **The suite:** `pytest --collect-only` in CI's interpreter; CI's coverage job for the line and
  function figures; `tests/coverage_baseline.json` for the ratchet.

## 1. Onboardings

### R6 (Lab 8, network Default, ZTP behind R4's relay), 2026-10-20

| Event | Time (UTC) | From | Note |
|---|---|---|---|
| Subnet 256 (10.255.4.0/30) added for ZTP | 16:48:47 | commit "dhcp: IPv4 subnet 256 (10.255.4.0/30) added" | a separate step today; C1460 folds it into Add device |
| Add device (Create): intent | 16:53:58 | commit "onboarding: r6" | |
| Add device (Create): Kea reservation | 16:53:59 | commit "ztp: r6 reserved aa:bb:cc:00:04:06 -> 10.255.4.2" | |
| Lab node started | ~18:14 | *operator-reported* | containerlab; no Mercury record |
| DHCP lease | 18:20:15 | *operator-reported* | Kea's lease record to be read for the next onboarding |
| First fetch of its bootstrap | 18:20:55 | responder journal, "served r6 to 10.255.4.2: 1 block(s), 468 bytes" | the operator observed 18:21:04 on the device |
| Last fetch | 18:21:01 | responder journal | 12 fetches in 6 s, each a full transfer (C1444) |
| Credential rotated to a device-generated secret | 18:29:13 | commit "credential: r6 rotated …" | onboarding's Verify |
| Promoted, recorded in NetBox | 18:30:16 | commit "onboarding: r6 verified and recorded in NetBox" | |

**Measured spans:**
- **From the first fetch to promotion:** 9 min 21 s (18:20:55 to 18:30:16). This includes
  Verify's 120 s key settle (C1400) and the operator pressing Verify (labour, M14).
- **From Create to promotion:** 1 h 36 min. This is the wait for the lab node to be started,
  not Mercury's time, and it is not a figure to quote.
- **From the lab node's start to promotion:** about 16 min (operator-reported start).

**Operator steps** (classed by `docs/MANUAL_STEPS.md`):

| Kind | Count | Steps |
|---|---|---|
| DECISION | 3 | Add device (M6); confirm the subnet (M1); confirm the Create (M1) |
| LABOUR | 4 | add the link's subnet (M9, removed by C1460); the firewall host step (M10); typing the address and MAC (M8); pressing Verify (M14) |
| LAB | 1 | starting the lab node (M24) |

**Gap:** a pending device's lease and boot are not in Mercury's record. History does not hold
the lease time, and the stop rule counts from Create, not boot (C1467). Once C1467 counts
from the first DISCOVER, "boot → lease → fetch → promoted" can be read from one record.

### R7 (Lab 8, network Default, ZTP behind R6's relay), 2026-10-21

| Event | Time (UTC) | From | Note |
|---|---|---|---|
| Capture started on the R6–R7 link | 02:02:26 | the lab host's capture file and its tcpdump process | read-only, the lab's own tooling |
| R7's first DHCP DISCOVER | 02:06:24.06 | the capture | about 4 min after the redeploy's window ended |
| Add device (Create): intent | 02:30:02 | commit "onboarding: r7" | its link's subnet already existed (C1460 part 1 not deployed) |
| Add device (Create): Kea reservation | 02:30:03 | commit "ztp: r7 reserved aa:bb:cc:00:04:07 -> 10.255.4.6" | |
| First OFFER, relayed by R6 | 02:32:10.01 | the capture | 40 ms after the DISCOVER it answered |
| Lease (ACK) | 02:32:10.09 | the capture | |
| First fetch of its bootstrap | 02:32:50 | responder journal, "served r7 to 10.255.4.6: 1 block(s), 468 bytes" | |
| Last fetch | 02:32:59 | responder journal | 12 fetches in 9 s, each a full transfer (C1444) |
| Credential rotated | 02:41:06 | commit "credential: r7 rotated …" | onboarding's Verify |
| Promoted, recorded in NetBox | 02:42:08 | commit "onboarding: r7 verified and recorded in NetBox" | |
| Seed intent committed | 02:42:29 | commit "host_vars: seed r7 from the committed golden" | |

**It keeps asking** (the capture, `udp port 67 or 68` on R7's uplink):
- **310 DISCOVERs** from 02:06:24 to 02:32:09, alternating two client identities in bursts of
  three about every 15 s: AutoInstall's MAC form (`cisco-aabb.cc00.0407-Gi2`) and the
  device's serial. **309 went unanswered**; the 310th was answered in 40 ms.
- **25 min 46 s** from the first DISCOVER to the relayed lease. The wait was the walk's order:
  nothing on R7's side changed while it waited. R6 had to be onboarded and its Day 1 deployed
  for the relay to exist on Gi3. Mercury's own part, from the answered DISCOVER to the lease,
  was 71 ms.
- **From the lease to the first fetch:** 40 s. **From the first fetch to promotion:** 9 min 18 s
  (02:32:50 to 02:42:08), including Verify's key settle and the operator pressing Verify (M14).

**What the record cannot show yet:** the same as R6's. Mercury does not hold the first
DISCOVER (C1467); this page reads it from a capture the lab ran. Which client identity was
answered decides whether R7's seed blocks its deploys (C1479).

## 2. Deploys

**The two time columns** (corrected 2026-10-21, C1481): "Receipt written" is the receipt's `at`,
stamped as the batch's rows are built, after apply, Verify and the golden capture. It is
**not** the apply. "To commit" is `at` to `completed_at`, the receipt to its commit. No record
holds when the program was applied or when Verify ended. R6's Day 1 had landed by 02:32:10
(R7 leased through its relay then), and its receipt reads 02:36:19.

| Device, step | Receipt written (UTC) | To commit | Lines sent | Sent as confirmed | Verify | Rollback | Saved |
|---|---|---|---|---|---|---|---|
| r4, Lab 8 step 4 (Gi5 toward R6, area 10) | 07:35:18 | 2 s | 12 | yes | FULL: interfaces 5/5, routes 30/30, OSPF 6/6, OSPFv3 4/4, BGP 2/2; 7 lines read back, 1 skipped | none | to startup |
| s3, Lab 8 step 4b (a stale static route removed, Mode B) | 16:28:14 | 2 s | 1 (1 removal, 1 authorised line) | yes | FULL: interfaces 9/9, routes 24 → 23 (the removed route), OSPF 5/5 | none | to startup |
| r6, Lab 8 step 6 (full intent) | 18:50:11 | 4 s | 42 | yes | FULL: interfaces 4/4, routes 5 → 25; 28 lines read back, 2 skipped (`no` lines); RIP and RIPng declared and not up, no neighbour yet (amber, C1450) | none | to startup |
| r6, Lab 8 R6 redo, Day 1 (2026-10-21) | 02:36:19 | 2 s | 43 | yes | FULL: OSPF 0 → 1, OSPFv3 0 → 1; RIP and RIPng declared and not up until R7's Day 1 (amber, C1450) | none | to startup |
| r7, Lab 8 step 7, Day 1 deploy 1 (2026-10-21; Gi3.10 without its address, C1478) | 03:09:44 | 2 s | 31 | yes | FULL, green: RIP 0 → 1, RIPng 0 → 1, interfaces 4 of 5 up, routes 5 → 8; 19 lines read back, 1 skipped (a `no` line) | none | to startup |
| r7, Lab 8 step 7, Day 1 deploy 2 (Gi3.10's address and helper) | 03:12:47 | 4 s | 4 | yes | FULL, green: RIP 1/1, RIPng 1/1, interfaces 5 of 5 up, routes 8 → 10; 2 lines read back | none | to startup |

**What these show:**
- Every deploy sent exactly the program confirmed (`matches_confirmed`).
- Every deploy was verified in full and saved.
- None needed a rollback.

**Before s3's deploy:** three earlier attempts at 16:23:12, 16:24:27 and 16:24:57 were
**refused, sending nothing**. The removal needed an authorisation the preview had not asked
for before Confirm (C1434). Refusals are part of the record, and a showcase can quote them.

**Gaps:**
- **Preview to verified:** the receipt records neither the apply nor the end of Verify (its
  `at` is when it was written, C1481), nor when the preview was drawn, so this span cannot be
  read yet. The preview's time is in the audit of
  the confirm; a row is to be registered when the first figure is wanted.
- **Rollback time to restore:** no rollback has run in Lab 8. The figure comes from the first
  one that does (Lab 9's testing segment, or an earlier lab's receipts).

## 2b. Lab 8's network, end to end (2026-10-21)

**From H5** (*operator-reported*, read on the lab host by the operator, after R7's Day 1 deploy 2
at 03:12:47 UTC):
- **DHCPv4:** H5 leased 10.70.10.100 from 10.70.10.0/24, through R7's relay (Gi3.10's helper).
- **IPv6:** SLAAC address in 2001:db8:70:10::/64, from R7's router advertisements.
- **Out to the internet:**
  - `ping 8.8.8.8`: 5 of 5;
  - traceroute: R7 → R6 → R4 → R5 → 8.8.8.8;
  - `curl` returns "hello world from RCN";
  - `ping 2001:4860:4860::8888`: 3 of 3.

**Through Mercury** (`reads.run`, the Ask tab's read path, recorded as the agent's run;
03:17:53 UTC):
- **R6 ↔ R7, RIPv2:** each names the other as its one RIP source (R6's gateway 10.255.4.6, R7's
  10.255.4.5). R6's RIP database holds 10.70.10.0/24 and 10.255.1.17/32 via 10.255.4.6.
- **R6 ↔ R7, RIPng RCN:** one next hop each way. R6 installs 2001:DB8:1::17/128 and
  2001:DB8:70:10::/64 from R7, and R7's IPv6 default is RIPng's, from R6.
- **Redistribution into OSPF:** R4 holds 10.70.10.0/24 and 10.255.1.17/32 as O E2 (metric 20),
  via 10.255.4.2 on Gi5, advertised by 10.255.1.16 (R6).
- **R7's IPv4 default:** the bootstrap's static via 10.255.4.5 (distance 1), not RIP. R6
  originates a RIP default (its database shows 0.0.0.0/0 "redistributed"). R7's RIP database
  holds no default, because the static, with the same next hop, is preferred. That is the
  design of section 5 of the walk, and it differs from the Lab 8 checks list's "by RIP" (the
  checks list says so).
- **Adjacencies** (Prometheus, up of all):
  - r1: OSPF 5/5, OSPFv3 3/3;
  - r2: OSPF 5/5, OSPFv3 3/3;
  - r3: BGP 2/2, OSPF 6/6, OSPFv3 4/4;
  - r4: BGP 2/2, OSPF 7/7, OSPFv3 5/5;
  - r6: OSPF 1/1, OSPFv3 1/1;
  - s3: OSPF 5/5;
  - s4: OSPF 5/5.

  Each equals the redeploy's D4 reading (01:4x UTC), except r4, which has one more of each (R6
  on Gi5), and r6, which is new.

- **Reachability from r4** (the same path, 03:2x UTC), each 5 of 5:
  - R6's loopback 10.255.1.16 and R7's 10.255.1.17, from r4's Loopback0;
  - 2001:DB8:1::17;
  - 2001:DB8:70:10::1, R7's VLAN 10 address.

**Count of Mercury operations for Lab 8's routing** (receipts, 2026-10-21): 3 deploys (R6 Day 1,
R7 Day 1 in two parts), 78 lines sent, each sent as confirmed, each verified FULL and saved,
none rolled back.

## 3. The suite and its checks (2026-10-20)

| Measure | Value | From |
|---|---|---|
| Tests collected | 12,910 | `pytest --collect-only`, CI's interpreter, 21:4x UTC |
| CI jobs per push | 4 test shards (browser1, browser2, a, b), `-n auto` each, plus the coverage job | `.github/workflows/ci.yml` |
| Line coverage | 88.4% of `modules/`, `routes/`, `app.py` | CI #1031's coverage job |
| Automation code | 180 modules, 2,914 functions; unit tests reach 2,806 (96.3%), every offline tier 2,811 (96.5%) | CI #1031's coverage job |
| The ratchet | holds (coverage only rises; `tests/coverage_baseline.json`, 159 modules) | the gate and CI |
| CI on main, 2026-10-20 | 10 runs listed from #1022, 1 red (#1028, a browser test's race, C1469), fixed forward in the next commit | `scripts/nmas-ci-log runs` |
| Findings recorded | 1,468 numbered rows, 629 open | `docs/OPEN_FINDINGS.md` and its Count |

**Found by the tool's own checks, today** (each a refusal or a reading that a person did not
have to notice):
- **C1454:** the redeploy pre-flight's own figures showed three devices newer than their startup
  files.
- **C1468:** Retire's clean-tree guard refused an uncommitted manifest entry.
- **C1469:** CI caught a test reading the wrong page.
- **C1434:** Confirm refused a removal without its authorisation.

A count over all time needs each row's "found by" read as a property; it is not estimated here.

## 4. To fill through Lab 8 and Lab 9

- H5's lease time, read from Kea's record (R6, R7 and H5's end to end are in sections 1, 2
  and 2b).
- R8 and the switch (Lab 9).
- The first rollback's time to restore.
- The first onboarding with C1460's subnet created by Add device: one LABOUR step fewer.
