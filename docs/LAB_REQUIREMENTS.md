# Lab requirements: Labs 4 and 5 (the NSoT), and how to demo each objective

The course's objectives for Labs 4 and 5, where each is met in Mercury, and the demo script for
the video: the screen, the clicks, and one line to say, **in the order to record**. Part 1's
numbering is the Part I write-up's (2026-09-21); Part 2's is the operator's where given (1.2b
rotation, 2.1 the pipeline). The rest of Part 2 is named by its content, from NSOT_PLAN's
Part 2 scope; **check those numbers against the brief before recording.**

Before recording: sign in through the access proxy as a person (every confirm records who),
open the Default network, and check **Needs attention** is quiet enough to show. Nothing below
runs in 08:30 to 09:10 UTC (the nightly backup), and nothing is staged on s3.

| # | Objective | Met by |
|---|---|---|
| 1.1 | Version control | the per-network config repository (goldens, intent, templates), every change a commit with Actor and Source, pushed to GitHub |
| 1.2a(i) | GUI with monitoring | Monitoring (the fleet dashboard, Coverage, Profile), Logs, DHCP, NetBox, the device page's Monitoring and Logs tabs |
| 1.2a(ii) | GUI input for new devices and changes | Devices › Add device… (onboarding, ZTP), Adopt a device…, Plan a deploy… (preview, confirm by hash, verify, rollback) |
| 1.3 | Templatize existing configuration | intent (YAML) plus Jinja2 templates, round-tripped; Templates with approve |
| 1.4 | Golden configs with timestamp | Save (a commit and a timestamped tag per device), Save All, baselines |
| Extra | Multi-vendor templates | templates keyed by platform (IOS-XE, IOS) |
| Part 2 | IPAM | NetBox (import with a dry-run preview) and DHCP (Kea's subnets, reservations, leases) |
| 1.2b | Passwords changed automatically on a regular basis | scheduled credential rotation (C724) |
| Part 2 extra | 2FA | registered for the public release (docs/PUBLIC_RELEASE.md, section f): not built |
| 2.1 | Configuration changes automatically trigger a test | `nmas-config-check` before every Mercury commit, and GitHub Actions on every push (C725) |
| Part 2 | Health-check apps | Coverage, IP SLA, Neighbours, Show commands, the logging-path test |
| Part 2 | Config changes | the deploy operation, the batch apply on the one stepper |
| Part 2 | Troubleshooting | Show commands across devices, History › Query, the device's Logs and History |

---

## The demo script, in recording order

### 0. Opening (30 s)

1. **Needs attention** (the landing page). Say: "Mercury is the lab's network source of truth;
   this page lists only what needs a person, each row with its action."
2. **Devices.** Say: "Nine devices, five C8000v routers and four vIOS switches, each with its
   intent state, read from what Mercury already keeps."

### 1.1 Version control

1. **History › Timeline.** Say: "Every change is a commit in the network's own repository:
   goldens, intent and templates, with who did it and which operation."
2. Open one commit (a Save All). Say: "One Save All is one commit across the fleet, so history
   is network-wide snapshots."
3. **History › Query**, the Remote card: **Push now** (or show the last push). Say: "The
   repository is pushed to a private GitHub repository, scanned for secrets first."

### 1.4 Golden configs with timestamp

1. **Devices › r1**, Overview: **Save**. The one stepper runs: read, save, record. Say: "Save
   reads the running config, commits it as r1's golden and tags it with the time."
2. r1's **History** tab. Say: "Each golden is a timestamped tag; any two can be compared."
3. **History › Baselines.** Say: "A baseline is earned only when every device is saved and
   matches its intent."

### 1.3 Templatize existing configuration

1. r1's **Intent** tab. Say: "The running config was parsed into this YAML intent."
2. **Templates**: open r1's platform template. Say: "Jinja2 renders the intent back; the
   round trip reproduces the device's config, and a template is approved only when it does."

### Extra credit: multi-vendor templates

1. **Templates**: the IOS-XE and IOS folders side by side. Say: "Templates are keyed by
   platform, so a new vendor is a new folder, not a code change."

### 1.2a(i) GUI with monitoring

1. **Monitoring › Dashboards.** Say: "The fleet dashboard from the earlier labs, inside Mercury."
2. **Monitoring › Coverage.** Say: "What each device is monitored by, and the gaps with a fix."
3. **Logs**, then **DHCP**. Say: "Syslog from Loki and Kea's leases, read live, never copied."
4. r3's **Monitoring** and **Logs** tabs. Say: "The same data per device."

### 1.2a(ii) GUI input for new devices and changes

1. **Devices › Add device…** (walk the form to its review; Cancel). Say: "A new device is
   planned here: its identity, first-boot config and ZTP reservation."
2. **r2 › Actions › Plan a deploy…**: the preview, then Cancel (or confirm a harmless change).
   Say: "Every change is previewed as the exact program, confirmed by its hash, verified, and
   rolled back on failure."

### Part 2: IPAM

1. **NetBox**: the network's card. Say: "NetBox owns devices, sites and addresses; Mercury
   imports into it only after a dry-run preview."
2. **DHCP › Subnets** and **Reservations.** Say: "Kea's subnets and reservations, changed
   through the same preview, confirm and read-back."

### 1.2b Passwords changed automatically on a regular basis

1. **Credentials › Profiles.** The Rotation policy column. Say: "Each credential profile
   carries a rotation policy; Mercury rotates the devices that follow it when their password is
   older than the policy allows."
2. On the profile row the demo device follows: **Rotation policy…** → on a schedule, every
   **1** day, from 0 until 24 (UTC), at most **1** device → **Set the policy**. Say: "Changing a
   policy needs a verified person, and it is recorded."
3. The **Scheduled rotation** card: each device's credential age and next due date. Say: "A
   timer checks every five minutes; it never runs in the nightly backup window, never on a
   device another operation holds or one restarting, and it stops at the first failure."
4. **Rotate due devices now…** → read the preview (the device it takes, and those it leaves
   with why) → **Rotate 1 device**. The one stepper runs: plan, rotate, verify, record,
   persist. Say: "The same rotation a person runs from the device page, one device at a time."
5. **History**: the row "Scheduled rotation (policy set by …)". Then the device's **Overview**:
   its Credential line, rotated just now, next due tomorrow. Say: "Recorded like a manual
   rotation, and the next one is already due tomorrow."
6. **Needs attention**: "…'s break-glass record is out of date since …: export it again".
   Say: "After any rotation the offline break-glass copy is stale, so Mercury asks for a new
   export."

### Part 2 extra credit: 2FA

1. Say: "Two-factor device login, RADIUS with an OTP server for people and SSH keys for
   Mercury's own account, is designed and registered for the public release." (Show
   docs/PUBLIC_RELEASE.md section f, or skip.)

### 2.1 Configuration changes automatically trigger a test

*(Filled in once the pipeline is built: a refused bad change in Mercury, a good one committed,
its GitHub Actions run passing, a bad push failing.)*

### Part 2: health checks, config changes, troubleshooting

1. **Monitoring › Coverage**: **Suggest IP SLA probes for them…** opens the IP SLA page; tick
   the probes, **Commit the ticked probes to intent, then preview sending them**, then confirm:
   the one stepper runs per device. Say: "A health check across the fleet, committed as intent
   first and applied as one previewed, verified change." (Every lab device already has its
   probe: show the page and the earlier run on History rather than sending again.)
2. r1's **Neighbours** tab. Say: "Routing neighbourships, read from the device."
3. **Show commands**: `show ip route summary` on every router. Say: "One read across many
   devices, answers grouped where alike."
4. **History › Query**, a ready-made question (interface errors on a device). Say: "The
   network's history, asked in plain questions."

### Close (15 s)

1. **Needs attention.** Say: "Everything Mercury does is previewed, confirmed by a person,
   verified and recorded; this page is what is left for a person to do."
