# Lab requirements: Labs 4 and 5 (the NSoT), Labs 8 and 9 (expansion by ZTP), and how to demo each objective

## Labs 8 and 9: the handout's objectives

Quoted exactly as the operator gave them from the handout, 2026-10-19. Both deliverables are
videos only, with no written report. Lab 8 is due Mon 2026-10-26; Lab 9 is due Wed 2026-11-04.
The plan for each is written separately, after the surveys; nothing runs on the lab's devices
until the operator signs it off.

- Prerequisite: "your network automation code, NSOT, and CI/CD pipeline in order".
- Lab 8, Objective 1: add R6 and R7 by ZTP.
  (a) The devices get their config automatically after connecting to the network.
  (b) The NSoT is updated appropriately when the new devices are added.
  (c) The documentation is appropriate.
  Video: what happens when the devices are added, how the automation framework is implemented
  and updated, and examples of the documentation. **Length: 6 to 8 minutes** (the submission
  format; the operator, 2026-10-21). The cut is docs/LAB8_VIDEO_OUTLINE.md (about 7:10).
  **How the video answers it** (the operator, 2026-10-21, from the handout):
  - **"How the GENERAL network automation framework is implemented and updated"** (the
    prerequisites: automation code, NSoT, CI/CD): the platform diagram (Mercury, NetBox, git,
    Kea DHCP, Mercury's TFTP responder, monitoring, the lab), the ZTP path emphasised, about 45
    s. "Updated" is what the framework updates when devices are added: NetBox's records and
    import, intent and golden commits in git, Kea's reservations and subnets, Prometheus's
    scrape targets (automatic: a golden commit wakes the targets keeper), Topology; the
    heartbeat and telemetry ALERT RULES are a follow-up step today (the walk's d3: the
    re-measure, then the host install steps), narrated as such; plus one sentence that Mercury's own changes pass CI
    before install. **No CI footage in Lab 8:** Actions, shards and coverage are Lab 9's
    deliverables ii and iii.
  - **(a) "Config automatically after connecting":** Day 0 is zero-touch (address, bootstrap,
    Verify); Day 1 is narrated as infrastructure as code: written as code before the device
    existed, deployed after one approval by design. Lab 9 moves that approval up front.
  - **(b) the NSoT updated:** NetBox's Planned records taken over at Verify, then the import
    after Day 1; intent and goldens committed in git.
  - **(c) the documentation:** shown and named in the voice-over as NetBox (the documentation
    of record: site, prefixes, VLAN, devices, addresses, cables), each device's intent in git
    (its documented design) and History (every change, who, what was sent, how it was checked).
    The Lab 8 write-up (docs/LAB8_DOCUMENTATION.md) is separate, not filmed (the operator,
    2026-10-22: no file 12).
- Lab 8 topology: R6 attached to R4 in OSPF area 10; RIPv2 between R6 and R7; H5 on VLAN 10
  behind R7.
- Lab 9, Objective 1: add R8 and a "Switch" through the same ZTP framework, with the full
  framework involved: ZTP, monitoring, visualization, DevOps testing, documentation. Video: what
  happens when the devices are added; a general overview of unit testing and code coverage;
  examples of the tools being used and tested; examples of the documentation.
- Lab 9 topology: R8 attached to R2 in OSPF area 20; a switch behind R8 with H6 and H7 on
  VLAN 10. The diagram labels the second host H1; call it H7 and note the label.

**The handout's diagram labels Lab 9's second host H1.** It is H7 here, in Mercury and in the
lab, so that it does not collide with the existing H1; the video says so once.

---

## Labs 4 and 5

The course's objectives for Labs 4 and 5 Part 2, where each is met in Mercury, and the demo
script for the video: the screen, the clicks, and one line to say, **in the order to record**,
after a 60-second recap of Part 1. Part 2's numbering is the write-up's (the operator,
2026-10-13).

Before recording: sign in through the access proxy as a person (every confirm records who),
open the Default network. Nothing below runs in 08:30 to 09:10 UTC (the nightly backup), and
nothing is staged on s3.

| # | Objective | Met by |
|---|---|---|
| 1.1 | IPAM | NetBox owns devices, sites and addresses (imported only after a dry-run preview); DHCP: Kea's subnets, reservations and leases |
| 1.2a | Usernames and passwords stored | Mercury's encrypted credential store and profiles, never displayed; the offline break-glass export |
| 1.2b | Passwords changed automatically on a regular basis | scheduled credential rotation (C724) |
| 1.2c | 2FA (extra credit) | designed and registered for the public release (docs/PUBLIC_RELEASE.md, section f); not built |
| 2.1 | Configuration changes automatically trigger a test | `nmas-config-check` before every Mercury commit, and GitHub Actions on every push and pull request (C725) |
| 3.1a | Health checks | neighbourships, route table, CPU, IP connectivity |
| 3.1b | Configuration changes | preview, confirm by hash, apply, verify, rollback, record |
| 3.1c | Troubleshooting (a later lab) | Show commands across devices, History › Query, each device's Logs and History |

---

## The demo script, in recording order

### Part 1 recap (60 s)

1. **History › Timeline.** Say: "Part 1 built the source of truth: every golden, intent and
   template change is a commit with who did it and which operation, pushed to a private GitHub
   repository" (the **Remote** card shows the last push).
2. **Devices › r1 › Save.** The one stepper runs: read, save, record. Say: "A Save commits the
   running config as r1's golden, tagged with the time."
3. r1's **Intent** tab, then **Templates** (the IOS-XE and IOS folders). Say: "The config is
   parsed into YAML intent and rendered back through Jinja2 templates keyed by platform."
4. What Part 1's write-up left to finish, now done (one line each, while showing it):
   **Devices › Add device…** (the onboarding wizard, to its review, then Cancel); r3's
   **Monitoring** and **Logs** tabs (per-device monitoring; switch syslog reaches Loki again,
   every sending device labelled); the whole interface is the redesigned one. Say: "The
   onboarding wizard, per-device monitoring and the redesigned interface from Part 1's list
   are finished."

### 1.1 IPAM

1. **NetBox**: the network's card. Say: "NetBox is the IPAM: devices, sites and addresses;
   Mercury writes to it only after a dry-run preview."
2. **DHCP › Subnets**, then **Reservations** and **Leases**. Say: "Kea's subnets, reservations
   and leases, changed through the same preview, confirm and read-back."

### 1.2a Usernames and passwords stored

1. **Credentials › Profiles.** Say: "Usernames and passwords are stored in Mercury's encrypted
   credential store, never displayed or returned; each device resolves its login from its own
   override, its role, its site or the default profile, and an offline break-glass export
   (Credentials) is the copy for when Mercury itself is down."

### 1.2b Passwords changed automatically on a regular basis

1. **Credentials › Profiles**, the Rotation policy column; on `default`, **Rotation policy…**
   (every **1** day, any hour, at most **1** a run, only **r2, s1**); Cancel. Say: "A policy
   per credential profile; changing it needs a verified person and is recorded. This one is
   limited to two pilot devices."
2. The **Scheduled rotation** card: s1 "rotated … ago, next due …"; r2 "due now". Say: "A timer
   checks every five minutes and takes at most one device a day under this policy. It rotated
   s1 on its own at 23:56 UTC, and never runs in the nightly backup window or on a device
   another operation holds or one restarting."
3. **Needs attention**: the CRITICAL row "Scheduled credential rotation stopped: s1 failed at
   commit". Say: "Its first unattended run rotated s1, then could not record it, so it stopped
   at the first failure and raised this; s1 was recovered with Mercury's own recovery and
   persisted. The timer starts nothing more until a person's run finishes cleanly."
4. **Credentials › Profiles › Rotate due devices now…** → the preview takes **r2** → **Rotate
   1 device**. The one stepper runs: plan, rotate, verify, record, persist. Say: "The same
   rotation a person runs from the device page, one device at a time; this clean run clears
   the stopped row."
5. **History**: "Scheduled rotation (policy set by …)" for r2; **Devices › r2 › Overview**: its
   Credential line, rotated just now, next due in a day. Say: "Recorded like a manual
   rotation."
6. **Needs attention**: the stopped row gone; "r2's break-glass record is out of date since …:
   export it again". Say: "After any rotation the offline copy is stale, so Mercury asks for a
   new export."

### 1.2c 2FA (extra credit)

1. Say: "Two-factor device login is designed and registered for the public release: people
   log in with password plus OTP through RADIUS, with a local fallback; Mercury's own account
   uses an SSH key restricted to Mercury's address." (Optionally show docs/PUBLIC_RELEASE.md
   section f.)

### 2.1 and 3.1b: a configuration change, tested, deployed and verified (one sequence on r4)

Use **r4**, never r2 or s1 (the rotation's devices).

1. **Devices › r4 › Intent › Edit.** Misspell one interface key (`description:` →
   `descripton:`) → **Commit to r4's intent**. Mercury refuses, naming the check, the file and
   the line. Say: "Every change to the config repository is tested before Mercury commits it:
   the same check the pipeline runs."
2. In the same box, put the key back AND make a real change: Loopback0's description, today
   `mgmt identity`, to `mgmt identity, managed by Mercury` → **Commit to r4's intent**:
   committed and pushed.
   Say: "A correct change passes and is published."
3. **GitHub › the config repository › Actions › nmas-config-check**: the run for that push,
   green (r4's intent is now ahead of its golden; Intent-Match is reported in the run, never a
   failure). Say: "On every push GitHub Actions checks out Mercury at the pinned commit and runs
   the same check: YAML and schema, every device's intent rendered through its template, each
   golden round-tripped, no plaintext secret."
4. **r4 › Actions › Plan a deploy…**: the preview names exactly `interface Loopback0` and its
   description → confirm. The stepper runs: apply, verify, record. Say: "The change is
   previewed as the exact program, confirmed by its hash, verified on the device and rolled
   back if it fails."
5. **r4 › Save**. Say: "The golden now matches the intent." Then **Actions**: the run for that
   push, green, Intent-Match yes. **Needs attention**: nothing for r4.
6. **A change that fails on GitHub:** in the config repository, edit `host_vars/r4.yml` on a
   NEW BRANCH (never main) with the typo, and open a pull request. Its check runs and goes red;
   open it to show the FAIL line with the file and line; close the pull request and delete the
   branch. Say: "A change that bypasses Mercury is caught on GitHub the same way."

Rehearse steps 1 and 2 once before recording: if Mercury's intent editor catches the typo
itself before the commit, its words differ from the pipeline's (still refused before commit).

### 3.1a Health checks

1. **Neighbourships:** r1's **Neighbours** tab. Say: "Routing neighbours, read from the
   device, each in its expected state."
2. **Route table:** **Show commands**, `show ip route summary` on every router → Run. Say: "One
   read across the routers, answers grouped where alike."
3. **CPU:** r1's **Monitoring** tab, "IOS CPU, 1-minute average" and "IOS CPU over time". Say:
   "IOS's own control-plane CPU, from telemetry on IOS-XE and SNMP on IOS."
4. **IP connectivity:** the same tab, "IP SLA round-trip time" and "IP SLA operations
   failing" (r1's probe to s1). Say: "Each IP SLA probe's round-trip time and whether any
   probe is failing."

### 3.1c Troubleshooting (a later lab; brief)

1. **History › Query**, "Interface errors and discards over time"; r3's **Logs** tab. Say:
   "The network's history in plain questions, and each device's own log lines."

### Close (15 s)

1. **Needs attention.** Say: "Everything Mercury does is previewed, confirmed by a person,
   verified and recorded; this page is what is left for a person to do."
