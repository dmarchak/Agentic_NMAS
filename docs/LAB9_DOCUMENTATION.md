# Lab 9: R8 and the Switch, added by ZTP, documented

**SKELETON for the operator, written 2026-10-22 overnight. Not reviewed.** The handout asks that
"the documentation is appropriate" (docs/LAB_REQUIREMENTS.md, Lab 9, objective 1). This page is
that documentation's skeleton, in Lab 8's format (docs/LAB8_DOCUMENTATION.md): what changed, how
the devices were added, what the source of truth holds, the lab's load, and how the framework is
tested. Every figure is measured and cited when filled; a fact no record holds yet is marked
`[READ: …]`. The plan and its evidence: docs/LAB9_PLAN.md (LP), by section.

The records it is written from are kept by Mercury and can be opened again: History, each
device's receipts, NetBox, Topology.

---

## 1. What changed

| Added | What it is | Role |
|---|---|---|
| **R8** | Cisco C8000v, IOS-XE 17.6 | area-20 router behind R2; the DHCP relay and gateway for the Switch's segment and VLAN 10 |
| **Switch (s5)** | Cisco vIOS-L2 | behind R8; VLAN 10 for H6 and H7; onboarded by out-of-band ZTP (section 4.2) |
| **H6, H7** | Linux hosts | VLAN 10 behind the Switch; DHCPv4 through R8's relay, IPv6 by SLAAC |

The handout's diagram labels the second host behind the Switch "H1 VLAN 10"; it is built as H7,
since H1 already exists.

## 2. Addressing

| Link or segment | Addresses | Source |
|---|---|---|
| R2 Gi4 to R8 | `10.255.4.8/30` (R2 `.9`); IPv6 `2001:DB8:2:28::/64` | R2's intent (LP step 5) |
| R8 Gi3 to the Switch | `10.255.4.12/30` (R8 `.13`, relay to `10.255.0.10`) | R8's Day 1 (LP step 5) |
| VLAN 10 (H6, H7) | `10.80.10.0/24` (R8 Gi3.10 `.1`, relay) | R8's Day 1 |
| The Switch's management | `[READ: the lease s5 takes through R8's relay]` | Kea, at s5's first pass |

## 3. Routing

OSPF area 20 between R2 and R8 (IPv4 and OSPFv3); `[READ: R8's neighbours and routes after Day
1, from its receipt]`.

## 4. How the devices were added

### 4.1 R8: Day 0 ZTP through R2's relay, Day 1 approved

`[READ: R8's first pass, P-checks and receipts: LP step 6]`.

### 4.2 The Switch: out-of-band ZTP for legacy devices

Why it was needed (challenge 1, LP "Write-up: challenges"): the vIOS-L2 image never asks DHCP on
its own. The feature (LP section 8): a read-only console survey (blank check, the MAC, a
signed-in prompt recorded as not blank), a reviewed kick-start whose exact lines are in the plan
and its hash, then DHCP through R8's relay and Mercury's gated bootstrap. The console server's
access is a dedicated key whose only power is bridging to an allowlisted console.
`[READ: s5's first pass, its transcript and receipt]`.

### 4.3 Day 2: operating them

`[READ: monitoring, Topology, History after both]`.

## 5. The source of truth, updated

NetBox (devices, IPAM, cables, the console path), intent and goldens in git, Kea's reservations,
Prometheus's targets. `[READ: the commits and NetBox objects at the end]`.

## 6. The lab's load (C1547)

The Lab 9 redeploy brought s3's stalls back: one hour at rest read 3 OSPF drops and 158 failed
scrapes where the same lab before it read 0 to 1 and 0 (LP step 4, E). The cause, measured: r1's
telemetry stream, dead since 2026-10-21 (C1523), came back, and each router's CPU subscription
sends every process's counters (~146 KiB every 10 s) through s3, which routes it in software and
has no output buffer on its uplink. The fix and its measured hour: `[READ: T1, E2; LP sections 9
and 11]`.

## 7. How the framework is built and kept honest

The suite (`[READ: the count at submission]` tests in four CI shards), function and line
coverage per push with a ratchet that only rises, branch coverage nightly, mutation runs with a
bar of 0 VERDICT survivors on the feature's safety code, and the tests that caught real defects
(LP section 7). `[READ: before and after figures]`.

## 8. Challenges

1. The Switch's configless boot (LP challenge 1): `[READ: its first pass closes it]`.
2. R6 and R7 booting from their saved configurations (option b): `[READ: LP challenge 2]`.
3. H5, H6 and H7 renewing their DHCP leases: `[READ: LP challenge 3]`.
4. The Switch alone on CPU 19: s5 held 60 to 69% of its own CPU throughout the measured hour and
   is not in the stalls (LP step 4, E).

## 9. What is not done yet (each registered)

`[READ: the register's Lab 9 rows at submission: C1536 (out-of-band ZTP's later phase), C1537
to C1550 as they stand]`.
