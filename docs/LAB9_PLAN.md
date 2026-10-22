# Lab 9: the plan (an ordered checklist, kept current)

**The operator's direction, 2026-10-22 ~04:3x UTC:** Lab 8 is complete, write-up included. Lab 9
is the last official lab, due Wed 2026-11-04. It is submitted as soon as possible **on Lab 8's
path, with no Mercury improvements first**. Every gap found on the way is registered as a finding
for after submission, when priorities are reset. The work runs in the order below, one step at a
time, and the operator is told as each step completes. Every decision is the operator's, asked
with the agent's recommendation and recorded in the decisions table.

This plan supersedes `docs/LAB8_LAB9_PLAN.md` section 3 for Lab 9: Day 1 approval up front is not
built for this lab, and the narration says it is still planned. That document's section 4
(addressing), section 5 (the switch's default and fallback) and section 8 (capacity) stand, and
this plan cites them.

**The handout's objectives** (docs/LAB_REQUIREMENTS.md, Labs 8 and 9): add R8 and a "Switch"
through the same ZTP framework, with the full framework involved (ZTP, monitoring,
visualization, DevOps testing, documentation). The video covers:
- what happens when the devices are added;
- a general overview of unit testing and code coverage;
- examples of the tools being used and tested;
- examples of the documentation.

The topology is R8 behind R2 in OSPF area 20, and a switch (s5) behind R8 with H6 and H7 on VLAN 10.
The handout's diagram labels the second host H1; it is H7 here (LAB_REQUIREMENTS).

## Decisions

| # | Decision | Recommendation | Status |
|---|---|---|---|
| D1 | Commit tonight's uncommitted records (Lab 8's walk, outline, requirements, host tuning, the register with C1531 and C695's note) and this plan as one docs commit through the gate | yes: they are records, not Mercury improvements, and the register rule needs them committed | **yes** (the operator, 2026-10-22) |

## 1. Tonight's queue: only C1522 and R7's heartbeat rule

- [x] **1.1 Push C1522.** Pushed as `c895821c` 2026-10-22 04:44 UTC (CI run #1057); origin's head before it
  (`57cf7674`) was green. Test-only: no deploy needed.
- [ ] **1.1a C1522's CI run green.**
- [ ] **1.2 R7's heartbeat rule, from its measured window.** The 03:02 UTC check
  (`nmas-heartbeat-check.service`, failed) reads "PROVISIONAL READY r7: 29 gaps now, a measured
  window would be 751 s (installed 1382 s from an assumption) -- regenerate".
  - [ ] **[OPERATOR, DECISION M1]** Monitoring › Heartbeat › re-measure: tick **r7 only**, Write,
    confirm by hash.
  - [ ] **[AGENT, LABOUR M11]** on `<nmas-host>`:
    `bash <home>/python/Agentic_NMAS/scripts/host-steps/c1419-install-alert-rules.sh heartbeat`.
    Expected: PASS on every line; Grafana's r7 rule at the measured window.
  - [ ] **[AGENT]** the check run again
    (`sudo systemctl start nmas-heartbeat-check.service`): r7 "current". s3 stays INSEPARABLE
    (C1318), so the check's exit stays a failure until that is resolved; the run is read for r7's
    line, not for its exit code.
- **Deferred, unless Lab 9 needs them:**
  - B to E (C1521: the hold-queue removal shape and s1's hold queue);
  - the findings reconciliation;
  - C1513 (the narrow version).

## 2. The gating test: can a vIOS-L2 switch ZTP? (C1349)

The question: from a configless boot behind a relaying router, does a vIOS-L2 AutoInstall
(DHCP, bootstrap fetch, apply)? Which interface or VLAN does AutoInstall use, and how does Mercury
reach the switch for Verify? If it cannot, the fastest alternative.
- [ ] The test proposed, with what it measures and what it changes (on a throwaway, never s1 to
  s4, nothing in 08:30 to 09:10 UTC).
- [ ] The operator's approval.
- [ ] Run, the result recorded here and under C1349.
- [ ] If it cannot: the alternative (LAB8_LAB9_PLAN section 5's fallback, the switch onboarded by
  DHCP through R8's relay, the video saying why), sized.

## 3. s5's CPU placement

- [ ] A recommendation from 2026-10-21's per-CPU sampling for 8 routers, 5 switches and 7 hosts
  (for example routers on 0 to 18 and s5 on 19, or s5 sharing a switch's CPU), with its expected
  effect.
- [ ] The operator's decision.

## 4. The topology in the one-file lab

- [ ] s5, H6 and H7 added to the one-file lab: s5 behind R8, H6 and H7 on s5's VLAN 10.
- [ ] H6's and H7's DHCP clients renew, unlike H5's in Lab 8, whose client had to be started again
  by hand.
- [ ] The redeploy steps: startup from goldens, the restart rules (a planned-restart window
  declared first; no `containerlab restart` or `docker restart`, C1372), PASS lines.

## 5. Prep in Mercury (on Lab 8's path)

- [ ] R2's relay toward R8 as an ordinary intent change. `ip nat inside` on R2's new interface
  if R2 is a NAT router (R4's Gi5 needed it for Lab 8's branch). Which edge R8's traffic leaves
  by, and what that implies for NAT.
- [ ] NetBox: R8's site, VLAN group and VLAN 10 (10.80.10.0/24 and 2001:db8:80:10::/64), and
  the Planned records for R8 and s5, as in Lab 8. Each manual NetBox step registered as a finding.
- [ ] R8's and s5's Day 1 documents.
- [ ] The Kea subnets and reservations Add device will create.
- [ ] Lab 8's lessons applied:
  - no stale NetBox addresses or cables before Add device (C1525, C1529);
  - dangerous-line reasons worked out in advance;
  - reloads off camera;
  - the whole-network import for the new site's cables (C1530).

## 6. Run sheet, shot list and the testing segment

- [ ] The run sheet for the recorded run: no CLI on camera, and a dry look at every deploy's
  preview before the recorded one.
- [ ] The shot list.
- [ ] The testing segment the handout requires:
  - unit testing and code coverage, in overview;
  - the tools being used and tested: a CI run with its shards, the coverage ratchet, mutation
    testing, and a test that caught a real defect.
- [ ] The narration says that Day 1 approval up front is still planned (the Lab 8 video promised
  it for Lab 9).

## Findings registered on the way (for after submission)

None yet.
