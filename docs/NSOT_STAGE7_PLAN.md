# Stage 7: the interface, rethought

Written 2026-09-26. **This document governs Stage 7.** It supersedes the
STRUCTURE of [NSOT_STAGE7_GUI.md](NSOT_STAGE7_GUI.md), whose measurements
still hold and are carried here:
- §0a, the interface is for an enterprise network: nothing does per-device
  work per request;
- §0b and §6c, script extraction and HTML caching: built as 7.2b;
- §6b, the invalidation rule: specified as 7.0.

It is written against three documents and P.3/P.4:
- [NSOT_TASKS.md](NSOT_TASKS.md): who the interface is for, what it must
  teach, and the task list;
- [NSOT_FEATURE_AUDIT.md](NSOT_FEATURE_AUDIT.md): what survives, and the
  operator's six decisions;
- [NSOT_CI.md](NSOT_CI.md): CI as state beside its trigger;
- **P.3** (every device path guarded or gone) and **P.4** (Jenkins cut) come
  BEFORE this stage (NSOT_PLAN.md).

## 0. What it is for

**The user is a network engineer** who knows networking, infrastructure as
code, intent-based networking, sources of truth, drift and CI, and **has
never seen this tool**. The interface teaches **this tool's model**, never
networking.

**It is organised around the task list, never around subsystems.** The
twelve tabs today (Devices, Topology, Ansible, Jenkins, History, NetBox,
Agent, Approvals, Monitoring, Configure, Git, Logs) map how the code grew. No
subsystem is a task: that was measured over 227 paths and every script, not
argued.

**Simple, and full-featured.** Every task a person sets out to do is
reachable, and grouped so a competent stranger finds it by intuition. The
curl-only tasks are defects, and this stage fixes all of them. The CLI-only
tasks divide between those the GUI owns and maintenance that stays CLI
(section 6).

## 1. Five destinations and one device page

**Renamed, 2026-09-29: the sidebar is the hybrid** (the operator, accepting
[NSOT_GUI_BRIEF.md](NSOT_GUI_BRIEF.md) section 2). The findability check counted twenty of
an operator's questions against three sidebars. Clicks barely separated them; the labels'
first-click scent did.
- **Fleet** is **Devices**.
- **Versions** is **History**.
- **Source of truth** is a sidebar HEADING over three items: **Templates**, **NetBox** and
  **Credentials**. A person arrives with three different questions there, not one.
- Help and Settings sit at the bottom.
- **OBSERVE is a sidebar heading** (brief section 14.1, signed off 2026-09-30) over
  **Monitoring**, **Logs**, **DHCP** and **Topology** (P.11, 2026-09-30: Topology is its own
  destination, never a tab of Monitoring). Built today: Monitoring (Dashboards, Coverage).
  Logs and DHCP open today's pages; Topology is not in the sidebar yet.

Each destination answers the question it answered before. Sections 1b, 1d and 1e keep their
old headings where their text was written, and are read as the new names. Confirmed by the
first-click test at the mockup review.

Each task group from NSOT_TASKS.md lands in exactly one place:

| Destination | Answers | Task groups |
|---|---|---|
| **Needs attention** (the landing page) | *Is anything wrong, and does anything need me?* | A; and the "needs a person" half of C, D and E |
| **Devices** (was Fleet) | *Which devices, and what do I want to do to many of them?* | C (many), E |
| **Device** (`/device/<hostname>`) | *What is going on with this one device, and change it* | B, C (one), D (one) |
| **History** (was Versions) | *What changed, who changed it, and can I go back?* | D (baselines), F |
| **Monitoring · Logs · DHCP · Topology** (under the heading OBSERVE, added 2026-09-30) | *How is it performing, what did it say, what holds an address, how is it connected?* | B (fleet-wide), and each service's one fleet-wide screen (brief section 14) |
| **Templates · NetBox · Credentials** (under the heading Source of truth) | *Are the templates, NetBox and credentials right?* | G, H (profiles), F (NetBox) |
| **Settings** | *How is the tool configured and connected?* | I, H (audits) |

**Superseded 2026-09-30, kept as the record below:** Monitoring IS a place again, under
the OBSERVE heading with Logs, DHCP and Topology. The app is the one place for every
integrated service (brief section 14), so each service has one fleet-wide screen and each
device page its slice. Grafana is drawn natively, never embedded (section 3).

**Why five and not the old two** (Fleet and Monitoring), as written 2026-09-26. Monitoring is no
longer a place. Per decision, Grafana is embedded where the device is, and
"is anything wrong" gathers the rest. Versions and Source of truth are
separate questions a person asks separately: *what happened* versus *is the
model right*. Folding them into Fleet recreates a tab that holds everything.

**Why not more.** Each extra destination must answer a question the others
cannot. "Approvals", "Jobs" or "Drift" as destinations would each be one
source of *needs attention*, which is the four-places failure the operator
named.

**The status bar, on every page:** integration health (NetBox, Loki,
Grafana, Oxidized, Kea, Proxmox), the deployed NMAS version and its CI
result, and who you are (the verified identity, or "not identified: you can
look, not change"). It is small, always visible, and every item links to its
cause. **Changed 2026-09-30 (mockup version 7):** the top bar keeps integration health and
who you are; the version and its CI verdict moved to Help > About, with a Needs attention
row when the running commit is not CI-verified or runs behind what is pushed. **Added
2026-10-02:** a quiet, neutral "Update available" while origin/main is ahead and CI passed
for it, which turns into that row when something is wrong (`attention.release_level()`).

### 1a. Needs attention (the landing page)

**One list, every source, each row the same shape:** what, which device or
job, since when, the cause in its own words, the operands, and the ONE
action that addresses it. Sources:
- `job_health`: the 9 rows today (systemd jobs, VM images, the thin pool,
  the ZFS pool);
- drift, per network, **with coverage** ("checked 7 of 9", never a bare
  "clean");
- freshness (Oxidized against approved);
- heartbeat alerts that are firing (Grafana's alert state, read by the
  integration);
- the approvals queue;
- pending onboardings;
- rollback-blocked devices, with the retry action (curl-only today);
- a failed or partial deploy, and a baseline that was not earned, with its
  reason;
- the agent's triage reports, attached to the alert they answer (Stage 8).

**Nothing on this page does per-device work to render (§0a).** Every row
comes from a stored or cached result, and each source states the time of the
value it shows. A source that could not be read is a row saying so, never an
absence. An empty page reads *"Nothing needs attention"*, with the time of
every source checked, because an empty list must say what was looked at.

### 1b. Fleet

- **A bounded list**: search, filter (state, platform, site, network, pending
  or promoted) and selection. Nothing renders every device; the §0a numbers
  are pinned by `test_scale.py`. **A row carries the device's status and a
  link to its page, and no action** (section 6a).
- **Actions on a selection**, each through the preview-then-confirm pattern:
  - change intent on many devices (bulk intent, CLI-only today);
  - plan a batch deploy (curl-only today);
  - capture as goldens (Save All);
  - reload.
- **Bring devices in and take them out**: onboard a new device; adopt an
  existing, already-configured one (absorbing Add and Discover); retire
  (CLI-only today). Delete is gone.
- **Networks** (device lists): create, switch, delete; set a network's
  inventory source (curl-only today).

### 1c. The device page

One page per device, **addressed by name** (section 6a), and the one home
for everything per-device. The header carries identity, platform, network, status,
and **the credential source it resolves to** (shown nowhere today). The page
has five sections:

1. **Overview: intent, device, and the difference, as three things.**
   - the committed intent (host_vars);
   - the device's latest capture;
   - the difference between them;
   - beside them, each check's state with its time: drift, freshness, the
     heartbeat window, and the last deploy's verification.
2. **Monitoring, NATIVE** (section 3; "EMBEDDED" until 2026-09-30): this device's panels
   drawn by the app from the device dashboard's own JSON, and its logs from Loki (the Logs
   tab), in place. Also its Oxidized fetch history and DHCP leases, rendered
   by the NMAS. **Built as tabs** (2026-09-30 to 10-01, `/v2/device/<name>`): Overview,
   Intent (read-only), History, Monitoring (with "Monitored by", Coverage's cells for the
   device), Logs, NetBox, Neighbours; Ask the device is not built.
3. **Neighbours**: CDP, OSPF, BGP, tunnels, and each link's state. Per device
   (built 2026-10-01, C38). The fleet's topology is P.11's Topology page under OBSERVE
   (research done 2026-09-30, not built), no longer deferred (section 9).
   **It carries C38** (moved from 7.2 by the operator, 2026-09-29): the
   EXPECTED adjacency set, derived from committed intent, against what the
   device reports, built once with two consumers, this section and a Needs
   attention row (the reader pattern). Beside C178: both ask how many
   neighbours a device should have against how many it has.
4. **History, one timeline**:
   - intent commits;
   - deploys and their results;
   - goldens, labelled **a record, not a target**;
   - captures;
   - restores.
5. **Actions**, each through the preview-then-confirm pattern. **State 2026-10-02:** each
   built action (capture, persist, rotate, seed, restore, retire, revert and retry, deploy
   with Mode B) runs on TODAY's device page; the v2 page's Actions menu links there, each
   with its "How does this work?" link. Moving them onto the v2 page is open:
   - edit intent, or author it from a form (decision 2): the form is an
     input MODE of the one intent editor, committing through its route
     (section 6a);
   - **seed intent from a capture** (BUILT 2026-09-28, C148; the text below is the
     record of why. Was: no usable path today: the commit route
     needs a verified person, so a curl from the host is refused. **R1
     measured, 2026-09-28, that EVERY onboarding lands here**: phase 1
     commits a bootstrap-shaped intent (`bootstrap`, `hostname`, `logging`,
     `secret_refs`), so an onboarded device cannot be deployed to from the
     interface until this exists, and C117's rollback run waits on it);
   - deploy;
   - restore to a golden or a ref (guarded, P.3);
   - **revert one intent commit** and **re-send a blocked change** (C118; was "retry after a rollback"; BUILT
     2026-09-29, was curl-only);
   - rotate the credential (BUILT and accepted on the host 2026-09-29, was CLI-only);
   - persist (BUILT and accepted on the host 2026-09-29, C164);
   - ~~move files to or from flash~~: **REMOVED** (2026-10-02, docs/CUTOVER.md): no
     arbitrary file transfer; software images get their own operation (P.13, after
     Stage 7) and ZTP delivery is onboarding's;
   - save to startup (ONE save: today's two, Save Device Config and Save to
     Startup, are one `write memory` with two implementations);
   - ask the device a question: the allowlisted command box, with history
     (absorbing quick actions), rendering and completion;
   - reload, as a GATED operation (P.14, 2026-10-02): running against startup, drift,
     the startup credential, the boot image, no holder, and the blast radius, each drawn by
     name before the confirm;
   - retire;
   - ~~the terminal~~: **REMOVED** (NSOT_FEATURE_AUDIT 3b, 2026-09-27,
     superseding 3a's read-only lens). A source of truth has no pane that
     goes to the device directly; the command box above is the one way to
     ask a device a question, and the break-glass path is the console
     runbook.

### 1d. Versions

**Built as History, 2026-10-02** (`/v2/history`, `modules/fleet_history.py`, the mockup
signed off the same day): the remote's one sentence with Push now and Verify; Commits (one
bounded git read, filters by device, person, workflow and time, each row's actor with how it
was established, what its commit earned, a record exception beside it, the change masked);
Baselines from the reader's stored judgement, with re-apply; freshness Authorisations. Not
yet: the "N of M commits carry a verified identity" line (7.5), and C83's subjects.
**Rebuilt as ONE timeline, 2026-10-03** (board D, signed off that day; C369): Commits became a
kind of a Timeline holding every record across every device and the fleet's own, read by
`history_sources.timeline()`, which a device's History tab shares filtered to the device; a
check holds the two to the same rows (tests/test_history_one_timeline.py). `fleet_history.py`
was folded into `history_sources.py`: one module owns History.

- **Commits**, with their `Actor:` and `Source:` trailers. Filtering by
  person, workflow or device is how *who changed what* is answered; the
  History tab and the AI change log are gone.
- **Baselines**: each one shows whether it was earned, and why.
- **Re-applying a baseline**, through the preview-then-confirm pattern, with
  inventory coverage (C23).
- **The remote**: push state, verify, and connect (connect is curl-only
  today).
- **Fleet captures and per-device history.**

### 1e. Source of truth

- **Templates**:
  - edit, validate and approve;
  - **revoke with a reason**, and **change bindings** (both curl-only today);
  - seed status;
  - round-trip coverage for the fleet (curl-only today; C2 fixed as it moves).
- **NetBox**:
  - guarded import and remove previews;
  - the modification record;
  - census comparisons.
- **Credentials**:
  - profiles;
  - a network's designated credential list;
  - decoupling a network before its source is deleted.

  All three are curl-only today.
- **Oxidized freshness authorisations**: authorise one divergence, see the
  authorisations (curl-only today).

### 1f. Settings

- **Integrations**, with secrets write-only (P.3 / B11).
- **The identity posture**, read-only and with its reasons.
- **The file-only settings, listed**: Access, platform and role maps, labs,
  syslog. The page says they are file-only and why, rather than hiding them.
- **Diagnostics**: the app log (absorbing the Logs tab) and the redaction
  health.

## 1g. The GUI redesign: requirements and route (the operator, 2026-09-29)

**Recorded, not built.** It applies from the Device page onward (the rest of
7.3, and 7.4 to 7.9). Section 1's destinations are its input: the brief places
them in a sidebar and says where each current feature goes. It does not
re-decide the destinations.

**What is wanted:**

- **Easy to use, organised the way a person looks.** Things live where a
  person would look for them. The Remote card sitting under the device list,
  far from the Git history, is the kind of placement to eliminate.
- **Professional and polished**, following how major commercial products
  approach UI and UX, never invented from scratch.
- **A sidebar instead of tabs**, grouped by task.
- **A user manual reachable from the GUI.**
- **Minimalist:** no duplicated functions and no cluttered screens. Today's
  device list, with several buttons beside every device, is the example of
  what not to do.

**The route, in order, with the operator's sign-off between steps:**

1. **Research.** Study how established products do it:
   - network-management tools with a similar job: Meraki Dashboard, Juniper
     Mist, Arista CloudVision, Cisco Catalyst Center, NetBox;
   - the public design systems enterprise tools are built on: AWS Cloudscape,
     Red Hat PatternFly, IBM Carbon.

   Look for the patterns they share:
   - navigation structure;
   - how a list shows actions: one primary action per row, secondary actions
     behind a "⋯" menu, bulk actions through selection;
   - status at a glance;
   - progressive disclosure;
   - empty states;
   - forms, spacing and typography;
   - in-product help.
2. **A design brief, short.**
   - What was found, with sources.
   - The principles adopted, and why.
   - The sidebar's structure, with EVERY current feature placed in exactly one
     location: the full mapping from today's tabs and cards to the new layout,
     so nothing is lost and nothing is duplicated.
   - The component rules: buttons, tables, status, forms, colours, spacing.

   It reconciles with the rules already in force rather than restating them:
   - one home per action (section 6a);
   - the operator first, with debug one level down (the presentation rule);
   - the preview-confirm-result component (section 2);
   - the live-data contract (7.2).

   **The stack:** the app is server-rendered HTML with Bootstrap, and the
   expectation is a consistent design system on top of what exists, not a
   frontend rewrite. A rewrite is recommended only with its case and its
   costs.

   **Minimalism, made checkable:** the brief inventories every duplicated
   function in today's GUI and names the home each one keeps. A duplicate is
   the same action reachable from more than one place, or two controls doing
   one job. Section 6a's rule then has a list to enforce.
3. **Mockups of three screens**, approved before building: the landing page
   with the sidebar, the device list, and the Device page. Shown, not
   described: the operator is a visual learner.
4. **Then build, screen by screen**, each through the existing tests and
   controls.

**The manual:**

- Written in the repository (Markdown), rendered in the app under a Help item
  in the sidebar, and versioned with the code.
- Each screen links to its own section, so help is one click from where the
  question arises.
- Organised by task ("onboard a device", "deploy a change", "restore a
  baseline", "recover from a lockout"), never by screen.
- The same neutral voice, and the same publication check, as the writeup.
- It stays true. A stage is not closed until the screens it changed are
  documented (acceptance item 15). A check, with a floor, fails when a
  sidebar destination has no manual section, so a new screen without
  documentation fails the suite.
- **It TEACHES (the operator, 2026-09-30; brief section 10a):** this is a lab,
  so the tool explains what it is doing.
  - Every operation (Save All, re-apply a baseline, deploy, restore, capture,
    rotate, persist, seed, adopt, onboard, a Mode B removal) has a "How it
    works" section: what happens in order, what is read, sent and recorded,
    and why each step exists, in plain language.
  - The info link beside an operation opens that same section in the side
    panel: one source, two places.
  - A running operation shows its steps with the current one highlighted,
    generated from the steps the code declares, never a hand-written list
    (C218's four silent minutes).
  - Diagrams: the onboarding flow, what a baseline contains, and how intent,
    golden and the device relate.
  - The check: every operation has its section (floor eleven), and every step
    its code declares is named there.

**Where it lands in the order:** before the Device page's screen, the first
big screen.
- **Research and the brief start after adopt's step 2 (its apply)**, which
  draws nothing.
- **Mockups follow the brief's sign-off.**
- **Building starts with the landing page, the sidebar and the Device page**,
  after the mockups' sign-off.
- **While a sign-off is pending,** work that draws no screen continues: C216
  (seed keeps declared blocks), the C117 loop's lab staging, and adopt's
  recovery.
- **Every screen still to come is built in the new design:** adopt's screen,
  the rest of the Device page, and 7.4 to 7.9.

**Progress:**
- the research, [NSOT_GUI_RESEARCH.md](NSOT_GUI_RESEARCH.md): signed off 2026-09-29;
- the brief, [NSOT_GUI_BRIEF.md](NSOT_GUI_BRIEF.md): received 2026-09-29, its five decision
  points decided the same day (below);
- the mockups of the landing page, the device list and the Device page, at desktop and phone
  width: reviewed 2026-09-29.

**The mockup review (the operator, 2026-09-29; brief section 13):**
- **Impression:** much cleaner and more appealing than today's GUI.
- **Mobile is a first-class requirement.**
- **The first-click test is skipped:** the twenty-question counts stand as the sidebar's
  evidence, and the questions become an acceptance check on the BUILT screens.
- **Drag-reorder is removed;** the batch deploy preview shows and sets the rollout order.
- **IBM Plex is bundled locally.**
- **The legacy collector, its views and SNMP Quick Poll are removed.** The app still SHOWS
  traps and syslog from Loki and alerts from Grafana, reading and displaying and never
  collecting or storing.

**THE APP IS THE ONE PLACE FOR EVERY INTEGRATED SERVICE** (the operator, 2026-09-29; brief
section 14). A person should almost never need to open Grafana, Kea, NetBox, Loki,
Prometheus or Oxidized directly: fully realised screens, not status cards.
- **Each device page shows its slice of every service,** and each service has one fleet-wide
  screen.
- **They come AFTER P.8,** because each network can have its own service scope.
- **Reads follow the reader pattern and the live-data contract,** and masking applies to
  everything shown.

**What each connector may do is a RULE, five questions (brief section 15):** does it change
the network, change the record or evidence, hide a signal, reveal a secret, or overload the
service? What passes all five is added freely and generously. The classification was checked
against the code, and two claims were corrected:
- **Prometheus's scrape targets:** nothing generates them today (C229).
- **Oxidized's `router.db`:** the NMAS already writes it, through rotation's persistence
  chain.

**Step (a) signed off, with corrections (the operator, 2026-09-30; brief sections 10a, 14,
15.2, 15.3):**
- **The OBSERVE heading and the device tabs: approved, with one rule.** A tab with nothing
  to show for THIS device is not drawn; the Overview states the empty state in a line
  (NetBox for a device NetBox does not hold, Neighbours with none, Monitoring for a device
  Prometheus does not scrape). Eight tabs is the ceiling, not the norm.
- **NetBox drift is EXACT, so C100 is done now:** the NMAS gets its own NetBox account.
  The one-time steps are [SERVICE_ACCOUNTS.md](SERVICE_ACCOUNTS.md); the drift reader is
  built after the switch-over, and any change-log entry by another account is a Needs
  attention row naming the object and what changed.
- **Reservations beyond the ZTP subnet: yes, on a per-network list of subnets (after
  P.8).** D4's checks stay scoped to the ZTP segment. Elsewhere: inside the subnet, no clash
  with a pool or another reservation, and never a managed device's management address
  unless the reservation is for that device. Lease history is the NMAS's own observed record.
- **(SUPERSEDED 2026-09-30:** no `auth.proxy` and no iframe exist in the code, measured; the
  device page draws panels from `api/ds/query` with the NMAS's own token, and with sign-in
  moving to OIDC (Stage 9, 9.I), people author in Grafana through its own OIDC login.
  NSOT_STAGE10_PLAN.md section 11. The line below is kept as the record.)
- **Grafana, corrected: restrict who can ASSERT AN IDENTITY, never who can reach Grafana.**
  `auth.proxy`'s allowlist names the NMAS only; Grafana stays reachable for a direct login;
  job health checks that the header from any other address authenticates nothing. The app
  shows dashboards as Viewer, and dashboard authoring happens in Grafana directly.
  **Measured on 13.2.0 Open Source** (brief 15.3): the Editor role holds rule and silence
  permissions on `folders:*`, so folder permissions cannot keep rules from a direct-login
  Editor. File provisioning can (P.7 generates every rule so). The NMAS's own token has an
  Editor's permissions (C230); the Viewer role itself is measured once the Viewer token
  exists.
- **C229 is P.7's:** P.7 generates the scrape targets from the inventory beside the rules
  (NSOT_PLAN P.7).
- **The silence fetch is BUILT** (who and until when, on every silenced instance; the row
  keeps its level), and the capture that tests it is the first staged run below.
- **"How it works" (brief section 10a):** every operation gets a step-by-step explanation
  in the manual. The info link opens that same section in the side panel, a running
  operation shows its steps generated from the code with the current one highlighted,
  diagrams cover the ideas, and the manual check has a floor.

**Staged runs: the operator's, at the next lab session.** Each is written out, so the
session needs no reconstruction:
1. **The silenced-alert capture** (the operator, 2026-09-30; after this commit is deployed,
   because the capture script gains the silence list):
   1. On a managed device, trigger the syslog test alert: `send log 2 NMAS silence capture`.
   2. Wait until Grafana shows **Critical syslog received** firing for that device (its
      evaluation is 60 s, plus the rule's own wait), and until Needs attention shows its
      row.
   3. In Grafana: Alerting > Silences > **New silence**. Matchers
      `alertname = Critical syslog received` and `device = <that device>`; duration 15 min;
      comment `NMAS silence capture`.
   4. Within 60 s, Needs attention's row must end "(silenced in Grafana)", keep its level,
      and say "silenced in Grafana by <you> until <the end>".
   5. On the NMAS host: `scripts/nmas-capture-grafana-alerts --out /tmp/grafana-silenced`
      (read-only; never into the checkout).
   6. In Grafana, **Expire** the silence, then capture again into `/tmp/grafana-expired`.
      That gives the second real shape, an expired silence.
   7. After that, the test's provisional silence object is replaced by the captured one
      (a minimal edit, the fixture rule), and the fixture README records it.
2. **The NetBox account switch-over:** [SERVICE_ACCOUNTS.md](SERVICE_ACCOUNTS.md) part 1,
   closing C100 when 1.6 passes. Note the switch time: drift is measured from it.
3. **The Grafana Viewer token:** SERVICE_ACCOUNTS.md part 2, closing C230; its printed
   permission list becomes the measured Viewer role in brief 15.3.
4. **The monitoring profile's removal shapes** (the operator, 2026-09-30; P.9, after the
   commit adding `global.ntp-server` and `global.snmp-server-host` is deployed). `logging
   host` and `snmp-server community` are measured exact on both platforms already, so only
   these two. Each run changes the RUNNING config only, never saves, holds the device, and
   stops with NOT RESTORED as its first line if the device does not return to its start.
   1. On the NMAS host, from the checkout, the dry run (connects to nothing):
      `scripts/nmas-removal-probe --shape global.ntp-server --shape global.snmp-server-host`
   2. IOS-XE, on r2: `scripts/nmas-removal-probe --list Default --device r2 --shape
      global.ntp-server --shape global.snmp-server-host --apply --actor <operator> --out
      /tmp/removal-r2.json`. Exit 0 is measured, whatever the verdicts; exit 2 is NOT
      RESTORED: stop and read its first line.
   3. IOS, on s4: the same with `--device s4 --out /tmp/removal-s4.json`.
   4. Hand over both files. They hold no secret (the scratch names start `NMASPROBE`, the
      addresses are documentation addresses). Their verdicts go into
      `modules/nsot/removal_measured.json`, and a shape measured anything but `exact` stays
      refused, with its reason drawn beside the line.
5. **Which routing tables the devices answer over SNMP** (the operator, 2026-09-30;
   costing in PROMETHEUS_TARGETS.md). Read-only; on the NMAS host, which has `snmpwalk`. The
   community is read into a shell variable from the exporter's own file and never typed:
   1. `C=$(python3 -c 'import yaml; print(yaml.safe_load(open("/etc/snmp_exporter/snmp.yml"))["auths"]["public_v2"]["community"])')`
   2. For r3 (IOS-XE; OSPF, OSPFv3 and BGP) and s3 (vIOS; OSPF), each table's state column:
      ```bash
      for ip in 10.255.1.13 10.255.1.23; do
        for oid in 1.3.6.1.2.1.14.10.1.6 1.3.6.1.2.1.191.1.9.1.8 \
                   1.3.6.1.2.1.15.3.1.2 1.3.6.1.4.1.9.9.187.1.2.5.1.3; do
          printf '== %s %s\n' "$ip" "$oid"
          snmpwalk -v2c -c "$C" -On -t 5 "$ip" "$oid" | head -8
        done
      done > /tmp/routing-oids.txt; unset C; cat /tmp/routing-oids.txt
      ```
   3. Hand over `/tmp/routing-oids.txt`. It holds OIDs, addresses and state numbers, no
      community. "No Such Object" for a table means that device does not implement it,
      which is the answer, not a failure.
   DONE 2026-09-30: OSPF-MIB on both platforms, OSPFV3-MIB on IOS-XE only, cbgpPeer2Table
   for BGP (it sees r3's IPv6 peer).
6. **Does vIOS report memory in the old Cisco family** (the operator, 2026-09-30)? Read-only
   from the NMAS host, with the community read as in run 5:
   `snmpget -v2c -c "$C" -On -t 5 10.255.1.23 1.3.6.1.4.1.9.2.1.8.0` (OLD-CISCO-SYSTEM-MIB
   `freeMem`, the family of the `cisco_old_cpu` module the switches already use).
   - If it answers, `freeMem` goes into the vIOS module, the memory panel draws it for vIOS, and
     the memory rule in `panels.PLATFORM_FOLDS` is removed, so the panel stops folding on vIOS.
   - If not, the panel keeps folding on vIOS (2026-09-30: a panel that does not apply to the
     device folds into one line above the panels, its sentence unchanged: memory isn't
     available over SNMP on vIOS).
7. **Does re-delivering lost timer ticks fix a slow vIOS clock** (the operator, 2026-09-30; C9,
   C93)? On a THROWAWAY vIOS in its own lab, **never s3**, and nothing changes on s3 outside a
   planned redeploy. The hypothesis: under nested virtualisation a timer interrupt is expensive,
   classic IOS counts those interrupts to keep time, and QEMU drops the ones the guest could not
   take in time.
   1. **The positive control first.** Boot the throwaway unchanged (its own copy of the vIOS
      launch script bound into the node, never `~/labs/lab/patches/`; its own management subnet,
      declared in `RESERVED_MGMT_SUBNETS`) and measure its clock rate. Without SNMP: `show clock`
      twice, ten minutes apart by the lab host's clock, rate = device seconds / real seconds. At
      idle, then under one defined load (the same load in every variant, for example a
      `ping ... repeat` from the device itself), with `vmstat 5` on the lab host beside it. **If
      the unchanged throwaway keeps time, stop**: the experiment cannot show anything, and s3's
      slowness is its workload.
   2. **One change per boot**, each checked AT THE CONSUMER before it counts (the qemu command
      line read from `/proc/<pid>/cmdline` inside the container, never the staged file):
      - `-rtc base=utc,driftfix=slew` (the RTC's lost-tick policy);
      - `-global kvm-pit.lost_tick_policy=delay` (the in-kernel PIT's). If the node's command
        line shows it is already in force by default, this variant is already measured by step 1
        and is skipped, saying so.
   3. **Record** each variant's rate at idle and under load, with the lab host's idle and steal.
   4. **If a variant brings the rate near 1.00**, it becomes a change to the lab's vIOS launch
      script, applied at the next PLANNED redeploy of the switches, and the clock rate is read
      again after it. If none does, the explanation in C93 stays "most likely" and the switches
      stay chronic entries.
   Teardown: `containerlab destroy` of the throwaway lab; nothing else was touched.
8. **Can `cdp run` be removed on IOS-XE** (the operator, 2026-09-30, P.9)? r6 carries
   `cdp run` that its effective intent no longer has (the first profile pushed it; CDP was
   then dropped on IOS-XE because the line enables no interface there, C254), so r6 departs
   from intent by one line and every Save All's baseline is denied until it is resolved. The
   shape `global.cdp-run` exists and is refused until measured. On r2 directly, no throwaway
   needed: the probe changes the running config only, never saves, holds the device and
   restores it, and `cdp run` runs nothing on IOS-XE.
   1. Dry run on the NMAS host: `scripts/nmas-removal-probe --shape global.cdp-run`.
   2. `scripts/nmas-removal-probe --list Default --device r2 --shape global.cdp-run --apply
      --actor <operator> --out /tmp/removal-cdp-r2.json`. Exit 2 is NOT RESTORED: stop and
      read its first line.
   3. Hand over the file. `exact` (IOS-XE's default is off, so the line goes) makes the line
      removable through Mode B from r6's Device page, and then from r1 to r4 if CDP is
      dropped on IOS-XE fleet-wide. `overrides_default` (the default is on, so `no cdp run`
      stays behind) means removal is the wrong tool, and r6's line is recorded in its own
      intent instead, saying why.
   **DONE 2026-10-01, `exact`** (r2, 02:44:18Z): `no cdp run` removed the line with nothing
   left behind, and r2 was restored (`cdp run` re-added, no re-add or teardown error). So
   CDP is OFF by default on IOS-XE. Recorded in `removal_measured.json` and
   `platform_defaults.json`, the probe's file kept byte for byte as
   `tests/fixtures/operational/platform_defaults/staged8_2026-10-01T0244Z/`. `cdp run` is
   removable through Mode B on IOS-XE from the next deploy; IOS was not asked and still
   refuses it. Next: r6's removal from its Device page (C262), then r1 to r4 (C269).
9. **Can a running IP SLA operation be deleted exactly, so the tool can change it** (the
   operator, 2026-10-01: s3's probe to r1, every 10 s, slowed to 60 s, not a lab
   requirement, to take load off the management gateway, C93)? IOS refuses to modify a
   scheduled entry ("Entry already running and cannot be modified"), so the deploy now
   changes one by deleting it, re-creating it from intent and rescheduling it
   (`modules/nsot/recreate.py`): previewed as such with the definition it replaces,
   verified by reading the operation back, rolled back by restoring the old definition
   from the pre-change snapshot. The delete, `no ip sla N`, is the removal shape
   `global.ip-sla-operation`, refused until measured on the device's platform, so today
   every such change is blocked by name. The probe's exemplars are a scheduled operation
   to 192.0.2.13 and an unscheduled one to 192.0.2.14 (documentation addresses nothing
   answers), each deleted and read back; `exact` means the operation and its OWN
   `ip sla schedule` line went and nothing else. **NOT on s3**: it measures `cisco_ios`
   on s1, the least loaded switch (clock 0.94), and `cisco_iosxe` on r2 (r1 to r4 run IP
   SLA too, and the IP SLA policy, P.9 (d4), will change them). Running config only,
   never saved, the device held and restored, as every run of this probe.
   1. Dry run on the NMAS host: `scripts/nmas-removal-probe --shape global.ip-sla-operation`.
   2. `scripts/nmas-removal-probe --list Default --device s1 --shape global.ip-sla-operation
      --apply --actor <operator> --out /tmp/removal-ipsla-s1.json`, then the same with
      `--device r2 --out /tmp/removal-ipsla-r2.json`. Exit 2 is NOT RESTORED: stop and read
      its first line.
   3. Hand over both files. `exact` is recorded in `removal_measured.json` and allows the
      re-create on that platform; `broader` (something else went with the operation) keeps
      it refused, naming what went.
   4. **Then s3's change, through the tool**: in s3's intent (Device page, Intent tab),
      change the operation's `frequency 10` to `frequency 60` and commit it; open the
      deploy for s3. The preview's program is six lines (`no ip sla 1`, the operation as
      intent defines it, `exit`, its schedule) under "ip sla 1 is running ... What it
      replaces on the device", and nothing else; confirm it. Verify reads `ip sla 1` back
      as intent defines it; a read-back that differs fails verify and the rollback puts
      `frequency 10` back. The operation's counters and history start again.

**The Services mockups reviewed (the operator, 2026-09-30; brief 9b, 14.2, 15.1):**
- **Every Grafana panel, rendered from the dashboard's own JSON model,** never a chosen few:
  a panel added in Grafana appears with no code change, and a type with no native renderer
  falls back to that one panel embedded, labelled. Measured: 168 of the 170 panels in the
  five dashboards draw natively.
- **Which dashboard: two roles, by UID, per network (P.8).** The fleet dashboard is the
  Monitoring page's default (Default: `rcn-lab-overview`), with a selector over every
  dashboard Grafana holds. The device dashboard has a device variable (Default:
  `nmas-device`, `device`; it replaced the original `rcn-lab1-snmp` on 2026-09-30); only panels selecting the device are drawn, and a dashboard
  with no such variable says so. A missing UID is a Needs attention row.
- **Alerts get a fix:** now, a "How to fix" column from each rule's own declared remedy (P.7
  declares one per rule; none declared says so); at Stage 8, an Investigate action with
  read-only tools and labelled notes (NSOT_PLAN 8.6).
- **A query builder and saved queries** for PromQL and LogQL, showing the query as it forms.
- **DHCP in IPv4 and IPv6**, reservations by DUID, and pools created through a previewed
  writer in the tool's own fragment, never on the ZTP segment. Measured first: Kea 2.4.1
  with no subnet or host command hooks, so pools go through the file, as reservations do.
- **The heredoc habit is closed structurally:** a PreToolUse hook refuses a heredoc fed
  into an interpreter (`f46f0f6`).
- **Step (c), the stack costing, is brief 9b:** Option A (server-rendered Jinja, htmx,
  Alpine's CSP build, and two ES-module islands, no build step) is recommended. It rests on
  a spike: the device page's Overview and Monitoring tab, built in A and measured, before
  any commitment.

**Mockup version 7 reviewed (the operator, 2026-09-30; brief 3.1, 9b, 14.2):**
- **The top bar keeps integration health only;** the commit, its CI verdict and the version
  move to Help > About and Settings, and a Needs attention row appears when the running
  commit is not CI-verified or the host is behind what is pushed.
- **Custom time ranges,** relative and absolute, bounded by each backend's measured limit
  (Loki 30 days 1 hour, Prometheus 90 days), the step widening with the range, a range past
  a limit refused naming it.
- **A live topology on Monitoring, drawn natively** (option (b)) from the topology service's
  `graph.json`, with states and alerts on it. The dashboard panel's cause was measured: an
  `<img>` at the service's public hostname, not port 8088; that hostname serves the
  network's map to the internet with no login (C231).
- **The device page's dashboard selector** offers only dashboards with the device variable,
  and the panels left out are listed with why (4 of `rcn-lab1-snmp`'s 8, first counted as 3).
- **DHCP:** the tabs stay one set during a preview, with the pool context in the
  reservation preview.
- **9b corrected:** npm's absence and a lockfile's hashes removed as reasons; the front-end
  argument carries option A.
- **The spike is APPROVED:** the device page's Overview and Monitoring tab in A, judged first
  on look, smoothness and the phone, then on the technical measures. **BUILT 2026-09-30** at
  `/v2/device/<name>`; its measures are in NSOT_GUI_BRIEF 9b. **Option A APPROVED
  (2026-09-30)** after the operator used it on desktop and phone; the review's fixes are in the
  brief (9b). Step 4 (build) proceeds in A: the landing page (Needs attention) and Help >
  About built the same day, with the commit out of the top bar and a Needs attention row when
  the host runs behind what is pushed (the `app-pushed` reader).

**The order from here (the operator, 2026-09-29), each step waiting for sign-off:**
1. the brief updated with the integration screens, the rule and its classification, and the
   extended findability questions (done: sections 13 to 16; signed off with corrections
   2026-09-30, above);
2. mockups of the new screens at desktop and phone width: fleet-wide Monitoring, DHCP with
   reservation management, the NetBox browser, Logs with the Loki query screen, a Prometheus
   query screen, and the device page's service sections (delivered 2026-09-30 for review:
   nineteen boards on the mockup canvas's second page, "Services", with one info link open as
   the side help panel and one running stepper, and a device whose empty tabs fold);
3. the stack costing, accounting for those screens: htmx plus Alpine over the current pages,
   against a full framework, honestly (delivered 2026-09-30 for review: brief 9b, with the
   mockups revised the same day for the services review);
4. then build, starting with the landing page, the sidebar and the Device page. The
   integration screens follow P.8.

**THE FRONTEND DECIDES; THE BACKEND SERVES IT** (the operator, 2026-09-29, governing the
rest of the redesign). A person's opinion of this program rests almost entirely on whether it
is easy and enjoyable to use.
- **Backend rewiring is the cost of doing it right,** never a reason not to: new routes,
  reshaped data, restructured modules.
- **Tests are a cost to weigh, never a veto.** The brief's first stack decision kept
  Bootstrap partly because about 200 tests read the shipped pages: the backend's convenience
  deciding the frontend.
- **The stack is decided AFTER the mockups.** They are designed for the best experience,
  unconstrained by the stack. Then the question is whether the current stack builds them
  WELL, not merely possibly. Where a screen needs something it does badly, the brief names
  the alternative and costs the switch honestly, and the operator would "rather rewire than
  ship a compromise".

**The brief's five decision points, decided (the operator, 2026-09-29):**
1. **The hybrid sidebar: ACCEPTED** (section 1 above, acceptance item 10).
2. **The Agent tab's Pause: REMOVED.** "A switch that looks permanent and resets on restart
   is worse than none." One persistent control, in Settings > AI.
3. **Drag-reorder: to be removed in favour of sortable columns, UNLESS something depends on
   list order.** Measured (reported to the operator before any removal):
   - No batch order through today's GUI depends on it:
     - deploy from the GUI is one device;
     - restore orders its targets alphabetically (`sorted(at_ref)`);
     - capture reads concurrently;
     - bulk reload runs each device on its own thread.
   - **The deploy batch runs in the order its request lists** (`for hostname in
     confirmations`), sequentially, with the circuit breaker. The redesign's selection bar
     would build that order from the list's display order, which the drag handle sets: a
     hidden control over rollout order.
   - So the batch deploy preview states its ORDER and lets it be set there, visibly: the
     first device is the canary, and the breaker stops after the first device that fails
     verify.
4. **Typed confirmation (the device's name): Retire only. AGREED.**
5. **The legacy SNMP-trap and NetFlow views: REMOVE.** Traps and syslog live in Grafana and
   Loki; this is duplicate D19. Checked first:
   - no recorded lab deliverable depends on seeing them in the app. Labs 7 to 10 are recorded
     in NSOT_PLAN "Course labs against the plan", and Lab 10's troubleshooting set names
     Grafana's heartbeat alert, not the in-app views;
   - the plan had already decided the collector's retirement (7.3-e), and the feature audit
     marks SNMP Quick Poll as cut with them, so it does not move to the device page as the
     brief placed it.

   **The limit:** labs 1 to 6 are not recorded in this repository, so they were not checked.

## 1h. Decided since this plan's structure was written (2026-09-30 to 2026-10-02)

Each is a standing rule for every Stage 7 screen still to build. Where it is enforced is
named; "not mechanised" says so.

- **Monitoring is TEMPLATES, shown on the Coverage grid** (the operator's mockup review,
  2026-10-02). What each device must run for its integrations is the network's monitoring
  profile (P.9, built: propose from the connectors, apply as a scoped deploy, onboarding and
  adopt apply it), and the profile is P.12's FIRST feature template (one bundle of intent
  section, platform templates, verify checks, removal shapes and risk). Monitoring >
  Coverage is the grid of device against integration, every cell saying why. The Heartbeat
  and IP SLA pages are replaced by the monitoring templates once their design is signed off
  and built (C322; docs/CUTOVER.md). The Coverage redraw's mockup is owed first.
- **"How does this work?" beside every action** (the operator, 2026-09-30 and 10-02;
  NSOT_GUI_BRIEF 10a). Every operation has a How it works page in the manual with a diagram
  in the flow of its text; the link beside the action opens that section in the side panel.
  Enforced: `tests/test_manual.py` (every operation's page, every declared step named, every
  info link's page and section exist) and `tests/test_v2_layout_in_a_browser.py` (every
  info and how link CLICKED in a real browser, the panel filling with its own section).
- **Needs attention: every row names something wrong AND an action** (C323), **and says how
  it clears** (C344: the condition resolving, a person acknowledging, or time; drawn as
  "Clears when …"). An event row (an unplanned restart, a line authorised again and again)
  is acknowledged by a person with a reason, recorded, keyed on its event. Information is
  never a row: it is said in its source's finding under What was checked, or on its own
  page, or as a quiet indicator (the top bar's "Update available"). Enforced:
  `tests/test_attention_rows_act.py`, `tests/test_acknowledge.py`.
- **Unplanned restarts are detected** (2026-10-02, `modules/restarts.py`): where the SNMP
  uptime counter FELL, never now-minus-uptime (the vIOS clocks run slow); planned only when
  the tool reloaded the device or was told (`POST /restarts/planned`, a late window refused
  unless a correction with its reason); an unplanned one is a Needs attention row for 7
  days, DANGER with a crash file. Enforced: `tests/test_restarts.py`.
- **Several people at once** (P.15, 2026-10-02): every write path is safe against another
  person, tab and worker process; a lock counts only if it holds across processes; a
  document two people can edit is saved against the version that person opened; confirms are
  bound to what was previewed. The audit is docs/CONCURRENCY_AUDIT.md: R1, R4, R24 and R25
  fixed (2026-10-02, `tests/test_repo_lock_across_processes.py`,
  `tests/test_approval_queue_store.py`); the rest are ranked there and land before 9.S's
  multi-worker step.
- **The lab-tooling boundary** (the operator, 2026-10-02; NSOT_STAGE10_PLAN 6.0): nothing
  lab- or person-specific in the PRODUCT from the moment it is written. It is lab tooling
  (`lab/`, a client of the read-only API), an optional integration off unless configured,
  or a value in gitignored local configuration. Enforced: `tests/test_lab_specifics.py`
  holds every product file carrying a lab name or value to an exact inventory with its
  Stage 10 disposition.
- **No new screen without a mockup and the operator's sign-off**, the mockup showing every
  link and control the built screen will have. Not mechanised.

## 2. The shared patterns: built once, used everywhere

1. **Preview, then confirm.** One component, used by:
   - deploy and batch deploy;
   - restoring one device, and re-applying a baseline;
   - onboarding (create, verify, abandon), adopting, retiring;
   - bulk intent;
   - NetBox import and remove;
   - reload;
   - reverting intent and retrying after a rollback;
   - approving and revoking a template.

   It always has the same six parts, in the same order:
   1. **What will happen:** the counts, and each target named.
   2. **What will NOT happen:** residue that stays; devices skipped, and why;
      what Remove will not touch.
   3. **The exact program:** what is sent, byte for byte. Never a diff
      standing in for it (D4).
   4. **The operands:** capture time and hash, plan hash, intent commit,
      authorised lines.
   5. **The gates, each by name, with its state:** approval, deployability,
      credential unchanged, dangerous lines, blocked change. This is CI
      beside its trigger (NSOT_CI.md §5).
   6. **A person to confirm:** "You are confirming as <identity>". If there
      is no verified person, the button states the refusal instead of being
      greyed out.
2. **The attention row:** what, where, since, cause, operands, one action.
3. **A record versus a target:** a golden is always drawn as a record. The
   word "golden" never appears without it.
4. **The explanation, one expansion away:** every concept in section 4 has a
   short line in place and a longer one expanded. Dense by default, never in
   the way.
5. **Stale marking and invalidation (7.0):**
   - a mutating action's response names what it invalidates;
   - the panels showing that data re-fetch;
   - a failed re-fetch shows the time of the value still displayed.
6. **Authorization-aware controls** (decided 2026-09-26,
   [NSOT_AUTHORIZATION.md](NSOT_AUTHORIZATION.md) section 7). Roles are built
   later, and the screens are drawn for them NOW:
   - **every gated control's state comes from `may`**, the server's answer
     for this caller, never from a client-side guess at a role;
   - **a control the caller may not use is DISABLED, WITH THE REASON AND WHO
     CAN**, never hidden: a viewer must see that Approve exists and has not
     been pressed (the example "the terminal reads *break-glass: not granted to
     you*" is superseded: the terminal is removed in 7.8);
   - **approval screens show the separation-of-duties state** when that
     policy is on;
   - **the status bar shows the caller, their roles and their grants.**

   Until roles exist, the mode is `any_person`, and the same drawing code
   draws every control enabled for a person.
7. **Operations across devices run concurrently** (the operator's standing rule,
   2026-09-29, after C188: Save All read nine devices one after another in 101 s,
   and at once in 40.9 s):
   - **reads across devices run concurrently by default**: captures, drift,
     freshness, reachability, probes, previews. A serial read loop is a defect
     unless it states why;
   - **writes across devices run concurrently only where nothing depends on
     order.** The deploy batch is sequential on purpose: its circuit breaker stops a
     bad change after the first device it breaks, and a concurrent push would reach
     the whole fleet before anything could notice. Canary and staged rollouts are
     the same: the ordering IS the safety;
   - **a sequential multi-device operation states why**, the way a toast-only result
     must justify itself. `tests/test_device_loops_state_why.py` holds every loop
     that calls the device layer directly, each with its reason, and the loops the
     scan cannot see (the work behind a call) from the 2026-09-29 survey; the rest
     are C199;
   - **the read loops the sweep found are converted** (2026-09-29, through the one
     helper, `modules/fanout.py`), the rest carry their reasons, and the NetBox
     import's writes wait on a decision (C199). The persistent pool's single lock
     (C202) is why three loops over pooled sessions stay sequential;
   - **a long read is a job, not a request**: it answers at once, shows in the
     in-flight panel and announces its result (the capture preview, C188 step 2).

## 3. Grafana, drawn natively and central (was "embedded"; superseded 2026-09-30)

**What is true now (decided 2026-09-30, NSOT_GUI_BRIEF 9b and 14.2; NSOT_STAGE10_PLAN 11):
no iframe.** The app draws Grafana's panels NATIVELY from the dashboard's own JSON model,
asking Grafana's `api/ds/query` with the NMAS's own token, so a panel added in Grafana
appears with no code change (measured: 168 of 170 panels across the five dashboards draw
natively; a type with no native renderer keeps its place, saying Grafana draws it, linked
where Grafana's address is set).
- **Two dashboard roles, by UID, per network:** the fleet dashboard is the Monitoring page's
  default (`grafana_fleet_dashboard_uid`), with a selector over every dashboard; the device
  dashboard (`grafana_device_dashboard_uid`, variable `device`) draws only the panels that
  select the device, each at its own `gridPos`, and folds a panel that does not apply into
  one line saying why.
- **Logs** come from Loki on the device page's Logs tab, matched by the device's own
  origin-id (C13), heartbeats folded by their exact line form (C21).
- Built: `/v2/device/<name>` Monitoring and Logs tabs, `/v2/monitoring` (Dashboards,
  Coverage), under `csp.STRICT_POLICY`. Custom time ranges are bounded by each backend's
  measured limit.
- **People author dashboards in Grafana directly**, through its own login (OIDC with 9.I).

The text below is kept as the record of the iframe design and of what measuring it found.

The device page's Monitoring section embeds **this device's** Grafana panels
(interface counters, CPU, reachability) and **this device's logs**, in place.
- **One provisioned dashboard, templated on the device**, and generated from
  the inventory like the heartbeat rules, so a device added gets panels
  without a hand edit.
- **Logs select on the device's OWN origin-id, never rsyslog's hostname
  field** (C13), or r6's page shows nothing.
- **Prerequisites, named rather than assumed:** Grafana's `allow_embedding`,
  its `frame-ancestors` header, and a Cloudflare Access policy for the embed
  path if Access fronts Grafana. **The iframe test runs first**, as 7.3's
  first step.
- **If the embed fails, the page says which prerequisite failed.** A blank
  frame fails acceptance.
- **The iframe test's prerequisites, MEASURED 2026-09-29 (read via the tunnel,
  read-only): four, and the list above named three.**
  1. **Grafana refuses framing**: `X-Frame-Options: deny` on `/login`,
     `/api/health` and `/d/`, so `allow_embedding` is off. (`grafana.ini` is
     root-only; the header is the measurement.)
  2. **The NMAS knows Grafana only at a loopback address**
     (`grafana_url = http://127.0.0.1:3000`). Grafana listens on every interface,
     but a browser on the tunnel cannot reach the LAN, and an `http://` frame
     inside the `https://` page is mixed content, blocked by the browser. The
     address the NMAS reads Grafana at and the address a BROWSER reaches it at
     are two facts, the "management interface names two networks" shape: an
     embed needs a second setting, never a reuse of `grafana_url`.
  3. **No tunnel hostname for Grafana is visible from here**: nothing of
     cloudflared runs on the NMAS host, so the `homelab` tunnel's ingress is
     dashboard-managed and only the operator can say whether Grafana has one,
     with an Access policy (and, for a cross-site frame, Grafana's session
     cookie needs `cookie_samesite = none`, or the frame lands on a login page).
  4. **The NMAS's own Content-Security-Policy blocks it**, not named above:
     `modules/csp.py` sets no `frame-src`, so it falls back to
     `default-src 'self'` and refuses any other origin's frame before Grafana is
     asked. The fix is ours: `frame-src` naming exactly the browser-facing
     Grafana origin (the setting from 2), never a wildcard.
  **1 and 3 are the operator's** (root on the host, the tunnel dashboard); 2's
  setting and 4 are the tool's, once 3 names the origin. **An alternative that
  removes 2 to 4**: serve Grafana under the NMAS's own origin (a reverse proxy
  at a subpath, `root_url` and `serve_from_sub_path` set), so the frame is
  same-origin and needs no second Access application; its cost is the NMAS
  proxying Grafana's own authentication. The operator's choice. **DEFERRED TO P.8** (the
  operator, 2026-09-29), both options kept: its own hostname behind Access (simplest; the
  Access cookie in a cross-site frame may not work) or Grafana under the NMAS's origin
  (same-origin, more plumbing).
- **Oxidized fetch history and DHCP leases are rendered by the NMAS** from
  their own integrations: they are records, not graphs.

## 4. The nine concepts, as acceptance criteria

"Teach at the point of action" is an acceptance criterion, not a principle.
Each concept has a named screen. The screen marks its explanation with a
`data-concept="<name>"` element. **A test renders the screen (the shipped
code, in duktape, against a real payload) and asserts that element is
present, non-empty and visible without navigating away.** A data attribute,
because a text search would match the concept's name in prose (*a pattern
that can appear in English needs an anchor*).

| Concept | Screen | What the screen says |
|---|---|---|
| `intent-vs-device` | device Overview | intent, device and difference drawn as three things, each labelled with its source |
| `golden-is-a-record` | device History, Versions | *"A golden is an approved capture: a record of the device, not a target. The target is intent, rendered."* |
| `merge-only` | the preview-confirm component (deploy) | residue drawn as *"on the device, not in intent: will NOT be removed"* |
| `confirm-by-hash` | the preview-confirm component (every use) | *"You are confirming this exact program. If the device or intent moves first, it is refused."* |
| `approval-binds-the-template` | Source of truth, Templates | the approval badge states what an approval covers (the template and every file it imports) and what it does NOT (whether any one device is reproduced), and a revocation shows its reason. *Renamed 2026-09-27 from `approval-binds-a-set`, which described approval scheme 2: since P.5 an approval binds the template, never a device set, and the old text asked the screen to state something false.* |
| `provenance-limits-remove` | NetBox remove preview | what will be skipped, and *"NMAS did not create it"* |
| `pending-vs-promoted` | Fleet, and the device header | *"Created, not yet reached: not managed until verified"* |
| `revert-is-forward` | revert-intent preview | what the revert will NOT undo, and that removal needs Mode B |
| `baseline-is-earned` | Versions, Baselines | why a baseline was or was not earned, per device, and WHICH CLAIM it makes (the operator, 2026-09-27): *configured* (every device's config captured or measured, today's only kind) or *configured and working* (E7: the fleet's operational snapshot in the tag, every protocol intent declares up). The eleven baselines on the host can only make the first claim, and are drawn as that kind, never implying the second |

**Floor:** nine concepts, nine screens, and the test counts them.
**Control:** remove one marker, and the test fails.

## 5. "If a payload carries it, the screen shows it", made mechanical

Four instances of one failure are recorded:
- **D4:** the wizard dropped `commands`, `dangerous` and `attribution`;
- the pending banner dropped its `list_name`;
- `/jobs/health` had no view at all;
- **C27:** the restore preview computed and carried `commands` and never drew
  the lines to be added, while the confirm hash covered them.

The check that catches the fifth before it ships is modelled on
`test_server_reads_nothing_the_form_cannot_send.py`.
- **Each renderer declares the payload it renders**, in one registry:
  `RENDERS = {"/deploy/plan": "_renderDeployPlan", …}`. A renderer with no
  declaration is a finding.
- **Payload keys come from REAL responses:** each declared route is called
  through the test client against the fleet fixtures, and the keys of its
  JSON are recorded, nested ones included.
- **Renderer keys come from parsing the shipped renderer**: the property
  reads on the payload variable.
- **Both directions:**
  - a payload key no renderer reads is a finding, unless exempt;
  - a key a renderer reads that no payload carries is a finding: a panel
    drawing a field nothing sends.
- **Exemptions are named, reasoned and capped** (at most ten), exactly as the
  form check does, and a commented-out read does not count.
- **Floors**: at least 20 declared renderers, at least 150 payload keys.
- **Anchors:** `commands`, `dangerous` and `attribution` on `/deploy/plan`;
  `list_name` on `/onboard/pending`; and `commands` on
  `/golden/restore/preview` (C27; the operator's fourth anchor, 2026-09-26).
  Each must be read, and removing one fails the test. Four recorded
  instances are what make the floors not arbitrary.

## 6. Every task's home

**The curl-only tasks, which this stage fixes.** The GUI can put a device
into a state that only curl can take it out of, so each gets an entry point:

| Task | Home |
|---|---|
| Seed intent from a capture (extract, review, commit) | Device, Actions |
| Deploy several devices as one batch | Fleet, selection |
| Authorise a dangerous line | the preview-confirm component (P.3 adds it to the current wizard) |
| Re-send a blocked change (was "retry after a rollback", C118) | Device, Actions, and a Needs attention row |
| Revert one intent commit | Device, History |
| Restore one device to its golden, guarded | Device, Actions (P.3) |
| Revoke an approval with a reason; edit bindings | Source of truth, Templates |
| Round-trip coverage; seed status | Source of truth, Templates |
| Credential profiles; decouple; dependents | Source of truth, Credentials |
| Set a network's inventory source | Fleet, Networks |
| Connect a remote | Versions |
| Authorise an Oxidized divergence; see authorisations | Source of truth |
| Job, image and pool health (`/jobs/health`) | Needs attention |
| Rollback-blocked devices | Needs attention |
| Reveal a secret (a person, audited) | Device, History (golden version) |

**The CLI-only tasks the GUI OWNS** (decided):
- **retire** (Device and Fleet);
- **bulk intent** (Fleet);
- **credential rotation** (Device);
- **adopt an existing device** (Fleet). **No capability exists to give a
  home to** (no adopt CLI, no adopt function; measured 2026-09-26). Proposed
  as its own item after Stage 7 ([NSOT_FEATURE_AUDIT.md](NSOT_FEATURE_AUDIT.md)
  section 8). Undecided;
- **seed intent** (Device).

Each goes through the preview-then-confirm pattern, and the CLI stays as the
scripted path.

**The CLI-only tasks that STAY CLI**, because they are maintenance, not
operation:
- repository identity repairs;
- NetBox census, deletions, IP provenance, and the modification-record
  sanitiser;
- break-glass export, verify and restore of the key;
- the secret-storage audit and the settings diff;
- heartbeat-rule generation;
- the lab tunnel, runbook verification and the scale report.

Their RESULTS surface in *Needs attention* where they are scheduled checks.

**Removed** (the audit's CUT list, as 7.8):
- the Ansible, Jenkins (P.4) and History tabs;
- the Scripts tab;
- restore from backup;
- bulk config mode;
- remove static routes;
- Delete;
- the legacy NetBox routes (P.3);
- the dead code the audit lists.

## 6a. One home per action (minimalism), decided 2026-09-27

**The rule (the operator's):** everything serves a purpose, and no function
appears in two places. A task has exactly one home, and if there are two ways
to do something, one of them is wrong. **Acting on MANY devices and acting on
ONE are different tasks**, so Fleet and the Device page may both offer
deploy. Two ways to act on one device is a defect, and so is one task with
two implementations: the page's action for its one device goes **through the
same component** as the selection's action. Many-versus-one is two entry
points into one code path, never two code paths.

**The device page, settled: (a).** The page is the home for everything
per-device. A Fleet row carries the device's status and a link to its page,
and no action. The row's four buttons (Template preview, Deploy plan, Edit
intent, Golden history) move to the page's Overview, Actions and History, and
Manage becomes the link on the device's name. The selection keeps the
batch-shaped operations: deploy, capture, restore to a baseline, command,
push a file. (c) differs from (a) only in whether the row shows status, and
status is not an action. (b) loses linkability, which a Stage 8 triage
report, a Needs attention row and a receipt all need.

**Addressed by NAME, not by address.** `/device/<ip>` breaks when a DHCP or
ZTP device's address moves, and those are now supported ways for a device to
arrive, so the URL would rot for exactly the devices the tool is newest at
managing. The name is also what a triage report, a Needs attention row and a
receipt already carry. 7.3 moves the page to `/device/<name>`. Whether
anything stored carries the IP form is measured then; if nothing does, the IP
form is removed rather than kept as an alias, since an alias is two addresses
for one page.

**The size, stated honestly:** a smaller reduction than the terminal. Most of
today's tab functions MOVE rather than vanish:
- Utilities becomes the command box;
- Files becomes an action;
- Changes becomes History;
- capture and restore-from are already page actions (7.1).

What actually goes is **Backups and Utilities as tabs**, and **the duplicate
save** (Save Device Config and Save to Startup: one `write memory`, two
implementations, one page). "7.3 deletes four tabs" is not a large cut.

### The backup store's retirement: a PREREQUISITE, not a note

The feature audit folds Backups into Versions as captures. The backup store
cannot retire until the template preview stops reading it, and that is
blocking, or it will be discovered during 7.5:
1. `routes/templates.py` `_captured_running()` supplies the template
   preview's second diff, "rendered versus running config", from the newest
   file in `backups/`. That diff reads a capture (the capture operation's
   read), or goes, since the capture preview is already the live comparison
   and the golden is the approved one.
2. Three renders fall back from the golden to that backup when a device has
   no golden (`capture = golden or running`): the template preview, the
   intent editor's preview, and bulk intent's render. So an artifact can be
   built from a store other than the one deploy and restore use. Each must
   say instead that it has nothing to render against.
3. "Refresh capture" opens the capture operation, not the backup route.

**Measured 2026-09-27:** the host's `backups/` holds **0 files**, so on the
host the "versus running" half has never compared anything, and removing it
loses nothing observed there. The backup is also chosen by a PREFIX match on
the file name and by mtime rather than a commit time (register C103).

### The check: what is mechanised, and what cannot be

- **Effect level: MECHANISED** (`tests/test_one_home_per_action.py`). C101's
  command-string scan (the AST over every command string the program sends)
  already makes the population the commands themselves. So each
  device-changing command is required to have ONE implementation, with the
  measured duplicates in a list that only shrinks. First run:
  - `write memory`, twice: Save Device Config and Save to Startup (a true
    duplicate);
  - TFTP upload, file delete, file download and the command, each with two
    implementations (`app.py` for the page, `bulk_ops.py` for the
    selection). The many-versus-one affordance is allowed; two code paths
    are not.

  Records were already one path: `save_golden()` for goldens, and
  `repo.git()` for every commit (`test_actor_verified_trailer.py`).
- **Route level: measured, and NOT a test.** Of 112 mutating routes, 13 are
  sent from more than one JavaScript function. Three are real:
  - playbook delete, implemented twice (the chat panel and the AI tab);
  - quick actions beside the command box, one route and one task;
  - approve beside Approve-all, which is many versus one.

  The other ten are steps of one flow (a re-plan inside the deploy wizard, an
  automatic clear after a corrupt chat history, a new list selected after it
  is created), or the scan attributing a fetch to the wrong enclosing
  function. It is not a test because a person's entry point is a CONTROL,
  and control to function to fetch is a JavaScript call graph that this
  project has no parser for. The enclosing-function match is a NAME match,
  and a test built on it would carry ten exemptions for its own noise, which
  is a check people learn to override.
- **Not mechanisable: whether two things are the same TASK.** Two mechanisms
  can reach one outcome through different routes AND different effects. The
  Configure forms and the intent editor both "change a device's
  configuration": one sends nothing and the other commits intent. The check
  can offer candidates, and a person decides. Nor does it cover VIEWS: golden
  history is drawn by a row's modal, the Git tab and the Device page, and
  reads are the destination structure's job (section 1), not this check's.

### The retroactive pass (2026-09-27)

| Pair | Verdict | Action |
|---|---|---|
| Save All / capture one device | many versus one, one component (`previewCapture` with no selection) | none |
| Selection deploy / the row's Deploy plan | many versus one, one wizard | the row's button moves to the page |
| Save Device Config / Save to Startup | **duplicate**: one effect, two implementations, one page | one save (7.3) |
| The page's file upload, download and delete / the selection's | many versus one, **two implementations** | the page calls the selection's (7.3). **Superseded 2026-10-02:** both go (docs/CUTOVER.md, no arbitrary file transfer; images are P.13) |
| The command box / the selection's bulk command | many versus one, **two implementations** | one implementation (7.3) |
| Quick actions / the command box | **duplicate**: canned input to the same route | saved entries in the box's history (7.3) |
| Playbook delete in the chat panel / in the AI tab | **duplicate**: two implementations | one; Stage 8 decides whether playbooks survive (P.3 refused replay) |
| Approve / Approve all | many versus one | **DONE 2026-09-27:** both hand off to the capture operation (one preview, per-device confirm; an item closes when its device is recorded); Auto-Create is the capture operation's `no_golden` scope |
| The Configure forms / the intent editor | **duplicate task**, and the forms send nothing | section 7 revised: a form is an input MODE of the one intent editor; the tab goes in 7.8 |
| The TFTP server field on both pages | the stored copy of a derivable fact | goes with C48 (derive) |

## 7. The Configure forms (decision 2), a parallel track

P.3 removes the direct push. Stage 7 homes the forms as **"Author intent
from a form"** on the Device page, and on a Fleet selection for the same
change on many devices. **Revised by section 6a:** a form is an input MODE of
the one intent editor, writing the same committed intent through the same
route and preview, never a second authoring path; the Configure TAB goes in
7.8, since today its forms send nothing and duplicate the editor's task.
- Converted **in batches**, starting with features the intent schema already
  models, so the first batch is mapping, not schema work.
- A form whose feature the schema cannot express says so and offers nothing.
- **Stage 7 does not block on it.** 7.9 delivers batch 1, and later batches
  are their own work.

## 8. Sequencing

Each step ships alone and leaves the interface working. **P.3 and P.4 come
first.**

| Step | Work |
|---|---|
| **7.0** | The checks every later step is written against: per-route reachability (url_for-aware, per method where a path mixes read and write), the invalidation map (all mutating routes declare), **the payload-to-render check (section 5)** and **the nine-concept harness (section 4)**. Each starts with an allowlist that only shrinks. |
| **7.1** | The preview-then-confirm component, retrofitted to deploy (absorbing P.3's wizard fix), restore, onboarding, bulk intent and NetBox import/remove |
| **7.2** | The status bar, and **Needs attention** with every source in section 1a. **The reachability reader (C92)**: one job keeping, per device, the last probe, its time and the consecutive-miss count, with the threshold taken from the host's measured misses, read by the dot and by every action that now acts on a single probe |
| **7.3** | **SEED INTENT FIRST (C148, raised by the operator 2026-09-28): the step that makes onboarding useful, not one of five Device-page actions.** Every onboarding lands with bootstrap-only intent, and the extract-and-commit path has no GUI and refuses anything without a verified person, so no onboarded device can be deployed to from the interface; the tool did it once (r6, 2026-09-24) through the route before P.3 gated it. Seed intent is an operation (preview, confirm by hash, result, record), and its ACCEPTANCE is C117's loop on a fresh throwaway: onboard → seed → deploy → break (a dangerous line authorised with a reason) → roll back, with C112's read-back, after measuring whether IOS holds a BGP session to its hold timer when the update-source goes down (if it does, the break cannot fail verify inside the window and the test would pass either way). **Paired with C151 (in 7.2): onboarding's OUTPUT is incomplete in two directions** (the operator, 2026-09-28): the device cannot be deployed to (C148), and it heartbeats while nothing watches for its silence until a person regenerates the rules (C151). **A third, found by the reboot test and fixed (C152): its inventory row could not be opened by the tool's pooled-session paths** (an unencrypted empty secret). Both were invisible until somebody onboarded a device, and the loop's acceptance run is where both are shown closed. Then the Device page: the Grafana iframe test, then Overview (the reachability claim drawn with its age and which claim it is, never "offline" for a device nobody probed: C92), Monitoring, Neighbours, History and Actions, including seed intent, revert, retry, rotate, retire and PERSIST (C164); the row's actions move here and the page moves to `/device/<name>` (section 6a); the terminal is REMOVED (7.8), the command box absorbing its reads. **Neighbours absorbs the Topology tab's built-in discovery, per device** (C126, decided 2026-09-28). **Monitoring's acceptance is Stage 5's enumeration, 7.3-a…f** (NSOT_PLAN.md; renumbered from "7.5" on 2026-09-27), with 7.3-f already done by P.1 |
| **7.D** | **The redesign's design steps (section 1g), each signed off by the operator: research, the design brief (with the sidebar mapping and the duplicate inventory), mockups of the landing page, the device list and the Device page. Before the Device page's screen is built; no screen after it is built in the old layout.** |
| **7.4** | Fleet: the bounded list and selection, batch deploy, bulk intent, onboard, adopt and retire, networks, and the inventory source. **Onboarding is designed for N address sources** (static, dhcp, ztp: P.6 lands first): the source choice is a LIST, not a toggle, and the pending-device row carries a per-source PROGRESS column (for ZTP: reservation written, config fetched, first seen). Cheap to design now, expensive to retrofit. |
| **7.5** | Versions: commits by actor and source (stating once *"N of M commits carry a verified identity"*, drawn beside its caveat: history carries known misstatements, listed by hash in `modules/nsot/record_exceptions.py` (the eleven rotation commits recorded `Source: manual`, C104; the two restores recorded `Source: pipeline`, C110; and the measured ABSENCE of agent-recorded first goldens, a checked negative). **It is the honest history of what the record got wrong, and the Versions screen draws from it rather than treating git as ground truth** (the operator, 2026-09-27): with C110 fixed, restore trailers mean something for the first time, and the screen must say which of the older ones do not. A screen stating a claim about history draws those exceptions next to the claim, with the rest marked *"recorded, not verified"*: D10, P.3 step 10), baselines with their reasons, re-applying one, the remote with connect |
| **7.6** | Source of truth: templates (the scheme-3 approval badge saying what it covers and what it does not, P.5; revoke, bindings, coverage, seed status), NetBox, credentials, freshness authorisations |
| **7.7** | Settings split, file-only settings listed, diagnostics |
| **7.8** | Removals, each with `check_removed_definitions.py` and a recorded reason, last so nothing goes before its replacement is on screen. **The Topology tab** (its built-in discovery, once 7.3's Neighbours carries it, and the topology-service panel, which goes with the deferred fleet view; C126). **The backup store retires only after section 6a's prerequisite** (the template preview and the two other renders read no backup), which is blocking, not a note. **The legacy golden store (`golden_configs/`) and the header-scan fallback** (`_find_golden_config_file`'s last link and the legacy entries of `repo.list_goldens()`): their retirement condition, `legacy_only_goldens()` empty for every list, holds on the host since r5's file was deleted 2026-09-28, so this is removal work with no prerequisite left (a plan item, never a notice on the landing page) |
| **7.9** | Configure forms: batch 1 (a parallel track, not blocking) |
| **7.10** | What defers cleanly (opened 2026-09-27 by the scope decision in section 8's 7.1 notes; it was never added to this table). As opened: Stage 5's in-app monitoring views, adopt (A3), the 900-device list and selection screens (the no-per-device-work rule stays in force), switching a network's inventory source. **Since:** the monitoring views came back into Stage 7 natively (section 3, 2026-09-30), and adopt into 7.3 (2026-09-29, its two steps built). What remains here: adopting the nine reference devices at scale (A3), the 900-device screens, and the inventory-source switch |

**Where each step stands is section 11** (2026-10-02). The row texts above are the plan as
scoped; where a row conflicts with section 1h or a "superseded" note, those govern (for
example 7.3's "the Grafana iframe test" first step: the panels are native, section 3).

### 7.0 built, 2026-09-27 (awaiting the host check)

The gates came first: B1 (a drifted deploy returned the device's
configuration) and C51 (24 GETs created the list they were asked about,
refused now at one boundary). Then the four checks. Each has its measured
allowlist, pinned at a ceiling and compared exactly, so it only shrinks:

| Check | Test | Measured | Allowlist |
|---|---|---|---|
| Per-route reachability | `test_route_reachability.py` | 212 routes, 218 (method, route) pairs; 5 non-GUI with a verified consumer | 54 unreachable, each with its group and home |
| Invalidation | `test_invalidation_map.py` | 115 mutating endpoints, all declared, 32 data keys; three measured cases wired | 29 declared keys nobody subscribes to yet |
| Payload to render | `test_payload_is_rendered.py` | 27 renderers against real responses; five anchors | 118 carried and undrawn, 18 reads on branches no fixture reaches |
| Nine concepts | `test_concepts_are_taught.py` | 4 live, executed against real payloads | 5 pending, each naming its step |

**What building them found**, each recorded where it belongs:
- **The six `/netbox/query/*` routes were "the AI agent's", and nothing
  calls them.** The consumer was claimed and never checked. Group (d),
  removed in 7.8.
- **Reachability first decided "mixed read/write" per RULE.** Its method-blind
  control should have failed and did not, because `/drift/settings` is two
  rules on one path. Per PATH, three more halves showed as unreached.
- **The invalidation hook keyed on the endpoint alone**, so a READ of a panel
  whose endpoint also writes announced an invalidation, and a refusal did
  too. Both were found by the payload check's measurements, and fixed with
  tests (`9264d97`, `dca1071`).
- **C55: both SNMP communities on an argument-free GET**, the read-write one
  drawn nowhere. B11's sweep planted secrets only in stores it knew about.
  Registered, and not fixed here, because 7.0 changes no route's behaviour.
- **The concept `approval-binds-a-set` described approval scheme 2**, so the
  table asked the screen to state something false. Renamed
  `approval-binds-the-template`. The harness now reads this table and fails
  if the two disagree.
- **The plan's anchor "list_name on /onboard/pending"** names the fact; the
  key is `list`.

**Floors restated from measurement:** the GUI doc's "at least 220 routes" and
"131 mutating routes" predate P.3 and P.4's removals (212 and 115 now).

**Acceptance 6 is the operator's, on the host.** Each of the three measured
cases updates without a reload:
- after onboarding's Verify promotes a device, the device list shows it;
- after a commit, the Remote card shows the new push state;
- after a drift run, the badge shows it.

**Acceptance 6, first run (2026-09-27): not passed, and why each case says
what it says:**
- **The Remote card** updated after an intent commit and its auto-push. The
  result cannot yet be attributed: the push runs on a background thread
  after the response that triggers the re-fetch, so the card updating means
  the push won the race or something else refreshed it (register C58).
- **The drift badge** did not visibly change after Check Now. That run
  could not test the mechanism: Check Now re-fetches the badge in its own
  code, as it did before 7.0. The operator's reading generalises: a test
  whose pass and fail render the same is not a test. The card's "Last:"
  line changes on every run, to the second, and is the observable.
- **The device list after Verify** is NOT MEASURED, and is not recorded as
  passing. It needs a pending device. It is measured at the next onboarding,
  which is also the first real run of the phase-2 persist step (C57).
  Verify runs phase 2 inside the request, so this case IS one the response
  can carry.

**What changed after the run:** the registry records what fired, with the
URL, the keys, the panels refreshed and each outcome. `NMAS.log()` in the
browser console shows it, so the next run can tell "did not fire" from
"fired and redrew an identical value". **What it found:** response-triggered
invalidation cannot see a change made after the response, or on a
schedule. Two of the three measured cases are exactly that (C58, proposed
fix: a server-sent invalidation over the existing Socket.IO connection).

### 7.1, deploy retrofitted, 2026-09-27

**The contract (approved by the operator, 2026-09-27):** one Python helper
builds the six parts (`modules/preview_confirm.py`: `build()`, a
`PreviewIncomplete` floor, per-screen adapters such as `deploy_preview()`),
and one shipped renderer draws them (`static/js/nmas_preview_confirm.js`).
The six parts are a FLOOR, not a template: a part with nothing to say states
it, the builder refuses a silent one, and the renderer draws the sentence.
Gates have five states. `at_apply` and `not_reached` are separate from `pass`
because a check that ran later, or not at all, has not passed.

**Deploy is the first screen on it.** `/deploy/plan` returns `preview`
beside `devices`. The wizard draws it and supplies only wiring (which
function a tick calls, and which a dangerous line's box calls).
`_programHtml`, `_attributionHtml` and `_deviceCard` are deleted.
Authorising a line re-plans the batch with every box, redraws it, and leaves
unticked any device whose command hash moved.

**What it moved, measured.** Once the server builds what the screen draws,
the ADAPTER is the step that can drop a key: D4's failure, one step
upstream. So the payload-to-render check reads the adapter as well
(`python_reads`), and the anchors now include `preview`, `lines` and
`from_this_edit` as well as `commands` and `attribution`. The promise in
UNDRAWN ("7.1's component draws each gate by name") is kept. Gates now
cover committed intent, template fidelity (its gap counts, since a rounded
100.0% can hide a missing line), acknowledgement, printable ASCII,
dangerous lines, the blocked change and the two apply-time checks. As a
result, 18 keys left UNDRAWN (117 to 99).

**Controls, each restored from a copy:**
- an empty "what will not happen" omitted;
- the builder accepting a silent part;
- an apply-time gate drawn as pass;
- the adapter dropping the attribution;
- untrimmed dangerous-line matching.

Each failed the tests aimed at it, and nothing else.

**Room left for Stage 8.8** (decided 2026-09-27, not built): the
second reading is drawn in the gates part with advisory states that never
render the success style (`warns`, `no_warnings`, `not_reviewed`). When it
lands, those states join `GATE_STATES` with a test that none draws green.
Nothing in 7.1 draws them yet.

**Bulk intent is DEFERRED to Fleet (7.4)** (the operator, 2026-09-27): by the
minimalism rule it is fleet-shaped (it changes intent on many devices in one
commit), and a device-list button now would be the same action in two places
once 7.4 builds it; its CLI works and is the path in use, so nothing is
blocked. 7.1's acceptance states it as deferred, not done.

**Next, in the approved order:** restore, onboarding, NetBox import/remove,
then bulk intent. `test_preview_confirm.py`'s `RETROFIT_PENDING` lists them
and only shrinks. Bulk intent has **no screen**: its routes are reached by
curl, so its retrofit is the preview and the screen that draws it.

### 7.1, restore retrofitted, 2026-09-27

**Restore is the second screen on the component.** `/golden/restore/preview`
returns `preview`, built by `restore_preview()`. That adapter has its own
gates, never the deploy's template gates, because a restore has no
template. Its gates:
- `RestoreTarget.checks`: a stored config at the ref, printable ASCII, and
  credential unchanged;
- whether this ref's intent is usable today;
- dangerous lines;
- the capture check at apply.

The flow keeps the un-onboard question and the authorise modal. It then
draws the component in a modal, with the agent's diff above it as labelled
text (context, never part of what the server built). It confirms exactly
the targets the preview marks selectable. Before, it confirmed every
`deployable` device, including one with an unauthorised dangerous line.
`restorePreviewText` and `_confirmProgram` are deleted, and the residue is
drawn under its section (C73's restore half).

**Building the gates part found four defects before C70 ran** (register
C75-C78):
- a restore could rewrite a held credential;
- the merge program compared lines as text, so it sent nothing when
  another stanza carried the same line;
- both previews returned stored config verbatim;
- "re-read at apply" re-read the stored capture, not the device. That
  sentence was in the deploy adapter written above.

Each gate drawn by name had to be traced to the line of code that makes it
true, and three of them were not what they said.

**Left behind by the restore retrofit, found running C70 (register):** the
restore's RESULT is still a toast (C84, 7.1's), and there is no per-device
golden capture (C82, a Device-page action for 7.3).

**Next, in the approved order:** the C77 sweep (every `not_device` POST
that computes, driven with every store planted; scheduled by the operator
2026-09-27, first because the next retrofits each add such a POST), then
onboarding, NetBox import/remove, then bulk intent. Before any of them, C70 runs on r2 (the procedure is in the
register row) and exercises this screen, C76's fix and the receipt's
restore half on a real device.

### 7.1 reshaped, 2026-09-27: an operation, whole, from the interface

**Why** (the operator, stopping C70 rather than finishing it with
workarounds, because the workarounds ARE the finding). Restoring one
device needed:
- a browser-console call, because the only button is whole-fleet (C80);
- a fleet-wide Save All, because per-device capture does not exist (C82);
- the network tab, because the program and hash have no screen (C84);
- an SSH session, because the receipt has no screen either.

A preview leading to an action that cannot be scoped, from a state that
cannot be created, with a result that cannot be read, is not finished:
the GUI has delivered a TRIGGER for the capability, not the capability.
So those three are not separate register rows. Together they are "the
restore path is not usable from the interface", and they belong in 7.1.

**The survey the operator asked for: does any other completed path end in
a result with no screen?** The payload-to-render check covers responses
that renderers draw. It cannot see a response nobody draws, which is
`/jobs/health`'s original shape. The population is every route gated
`confirm`, `approve` or `publish_remote` in `route_gates.py` (41: the
routes that change a device or the record). Each handler was read by hand;
a script's first classification was only the starting list. **None of the
41 has a screen where its result can be read again later.** Receipts
record deploys and restores, and nothing draws them.

| Result | Count | Routes |
|---|---|---|
| **Drawn in place**, until the window closes | 16 | deploy apply (the result modal); bulk execute, delete file and TFTP upload (bulk results); run command, save config, save to startup, delete file and upload (the device page re-rendered); chat; git commit; auto-create; intent commit (a status line); remote push, auto-push and acknowledge |
| **Toast only** (gone in seconds) | 17 | **restore apply (C84)**; onboard verify on SUCCESS (failure is drawn), abandon and **create, whose toast "Device onboarded." is false: create is phase 1 (C86)**; bulk reload; agent run (its response is never read; the agent is off); approval approve, reject and approve-all (the commit an approval makes is never shown); Save All (a rich toast, green whenever a baseline tag was taken, whatever the moment); NetBox import, import-all and remove ("Import started": **the import's outcome, including C8's `write_failures`, `partial` and `complete`, is persisted and drawn nowhere, and the sync card shows a green badge when `failed` is empty, C85**); refresh hostnames; template approve (its per-device evidence) and template save; remote verify-write |
| **No GUI** (curl or CLI) | 8 | freshness authorise; template revoke and bindings; bulk intent apply; extraction commit ("seed intent from a capture"); intent revert and retry; remote adopt |

Two of the toasts also interpolate hostnames and reasons into HTML
unescaped (Save All, Auto-Create). A result renderer that escapes every
field closes that surface for everything it draws.

**What it does to 7.1's shape.** 7.1 was "retrofit five previews onto one
component". It becomes **"an operation, whole: prepare, preview, confirm,
result, record, from the interface"**. The component gains its second
half, and the Device page becomes the place a single-device operation
starts. In order:

1. **The constraint first, with the survey as its measured list** (7.0's
   pattern: an allowlist that only shrinks). Every `confirm`, `approve` and
   `publish_remote` route's response is drawn by the result component or a
   declared renderer, or is declared toast-sufficient with a reason (a
   reject that did nothing is one). The population is the gate table, so a
   new gated route fails the check until it is declared.
2. **The result half of the component** (C84, generalised). One builder, one
   renderer in `nmas_preview_confirm.js`, parts mirroring the preview:
   - **what happened**, per target;
   - **what did not**: skipped, refused, residue left, measured;
   - **what was sent**: the program as sent, its hash against the confirmed
     hash;
   - **the checks that ran**, before and after, or why none did;
   - **the record**: the commit, its tags and the claim they make, the
     receipt;
   - **what is not being watched**: the follow-up window, not built.

   The result is **built from the receipt rows the apply has just written**,
   so the screen and the record are one computation. Deploy's
   `_renderDeployResult` retires into it, and restore gets it for free.
3. **The receipt on screen, later**: a masked reader
   (`GET /deploy/receipts`, per device and per batch) and a Device-page
   "Changes" list drawn by the same result renderer. It covers what none of
   the 41 has.
4. **Per-device capture (C82)**, a Device-page action that is itself an
   operation:
   - **preview**: read the device and show the diff against its current
     golden, masked. What will NOT happen: no device change, and no baseline
     tag, since one device never earns one;
   - **confirm**: bound to the capture hash;
   - **apply**: re-read the device, refuse if it moved, and commit
     `Source: manual` with the verified person;
   - **result**: drawn by the component.

   The drift approval (C81) stays as the automated route.
5. **Scoped restore (C80)**: "Restore from…" on the Device page, choosing
   one of the baselines or this device's own golden tags. The Baselines
   panel's re-apply takes a device selection that defaults to NONE, so
   "the whole fleet" is chosen rather than inherited. Both open the same
   restore preview.

Then the C77 sweep, which now also covers capture's preview POST.
**C70 is 7.1's acceptance**, run entirely in the browser: capture r2 alone,
preview scoped to r2, confirm, then read the program, the hash, the receipt
and verify's result on screen. A console call exercises the function; this
exercises what a person actually does. After it: onboarding, whose result
half then comes with the component and ends the false toast; NetBox
import/remove, whose import outcome draws C8's fields; bulk intent.

**Capture must ask what the rest of the tool asks** (C89, the operator, 2026-09-27): a terminal change plus Save All became a golden, a baseline tag and a pushed commit in four minutes, and capture silences the drift checker. DECIDED by the operator for step 4 (2026-09-27), with the 7.2 row for a golden departing from intent weighted highest: capture previews each device's diff against its golden and against committed intent, and is confirmed per device (Save All joins it); a baseline tag needs every capture to match its committed intent (measured: this denies exactly `baseline/20260927T154517Z` today); and every golden commit carries a computed `Intent-Match:` trailer.

**Scope decided 2026-09-27 (the operator), after 7.1 tripled:** the test for the smallest Stage 7 is *every task has a home, every result is drawn, nothing requires a console*. Measured against it (the reachability check's 55 routes with no page: 27 removals, 12 homed in 7.6, 7 in 7.3, 4 in 7.4, 3 in 7.5, 2 in 7.2), and with **rotate and retire having NO ROUTE AT ALL** (host CLIs only, so by the no-console test the interface cannot manage its own credentials):
- **7.3 gains rotate and retire** as operations, beside the intent operations (seed intent, revert, retry), each with the treatment capture got in 7.1 step 4 (preview, confirm, result, receipt) and a real run on the host afterwards. Rotation is the riskiest operation in the tool. **Build it assuming a fourth failure mode exists** (the operator, 2026-09-27): three ways for a rotation to leave a device unmanageable were found in three days (B15, the boot file; C53, the device never saved; C106 1a, a failed record deleting the only copy of the new password). So every state between "the device changed" and "the tool holds it" is named, kept recoverable and drawn, and nothing the operation writes is removed until the record it protects is proven.
  **The rotate screen, step 1 BUILT 2026-09-29: the recovery path, before the screen**
  (C210). Designing the screen found the fourth failure mode before it happened: the
  password is staged before the push, so a process that dies between the push and the
  record (an app restart, which a deploy causes, and a web rotation runs inside the app)
  leaves the device on a password the inventory does not hold, the staged file its only
  copy, and nothing read that file. `nmas-rotation-recover` settles it by asking the
  device, removing nothing until the record it protects is written, and job health names
  every staged file nobody holds. Step 2 is the screen: a preview (the plan, its
  preflight read, the program masked), a confirm by the plan's fingerprint as a person,
  and an apply that runs as a BACKGROUND JOB (rotate then persist can pass the 100 s edge
  limit), announced when it finishes, its result drawn from the state it reached, every
  state named with its one action.
  **Step 2 BUILT 2026-09-29, awaiting a real run on the host.** `rotate_op` runs
  `credential_rotation` as one operation, holding the device across rotate AND persist.
  The job carries the confirming person's verified identity into its thread
  (`identity.carried`), since a commit on a background thread read `Actor-Verified: none`
  although the gate had verified the person. **Expect the real run to meet the sudo
  helper**: preflight asks whether the persistence helper runs without a password for the
  process that rotates (C106), and the app's service user may not have that rule, which
  the preview will show as a failed gate by name. **Acceptance**: rotate a throwaway, or a
  fleet device the operator chooses, from its page; the result reaches
  `rotated_and_persisted`, the commit reads `Actor-Verified: access`, the break-glass row
  names the device until it is exported again.
- **Revert and retry from the Device page: BUILT 2026-09-29, awaiting a real run.**
  `modules/nsot/intent_ops.py`: each previewed (reads git and the record only), confirmed
  by hash with the list carried, applied holding the device, drawn by the one component.
  Revert computes with `hostvars.plan_revert()` (one computation for preview and apply),
  commits `Source: revert` with a `Reverts:` trailer, puts the file back on a failed
  commit, and MEASURES the rollback block afterwards, clearing it only when it no longer
  blocks (C214). Retry needs a reason in the shape of one (C140's rule), says how often
  the device was retried before, and refuses on an unreadable retry log (C213). One
  classifier, `note_applicability()`, for the list and both screens. They replace two
  routes with no screen. C215 fixed with them. **Acceptance**: on a throwaway (C117's run
  engineers the rollback), retry a blocked change with a reason and see the next plan
  offer it; revert a commit and see the block measured.
- **The break-glass export from the browser: BUILT 2026-09-29, awaiting a real run**
  (the operator's request the same evening, placed after revert and retry and before
  adopt). The day's re-export took about ten manual steps across two machines, and the
  first attempt was LOST: the laptop half ran on the host and its cleanup deleted
  `/dev/shm/rcn-breakglass.bg` before it was copied, while the export was already logged
  (C221). `modules/breakglass_export.py` builds, seals and VERIFIES the record in memory:
  the passphrase entered twice and at least 12 characters, refused before anything is
  built; the plan recomputed and bound to the preview's hash (a rotation in between
  refuses); the sealed bytes OPENED with the passphrase and every device, every credential
  (by digest) and the escrowed key checked against what was put in, the key required to
  open what the live key opens; then a reveal row (who, when, the device count, the file's
  sha256; nothing is sent unrecorded) and the export log (`via: browser`, "downloaded by X
  at T"). The file never touches the host's disk. Gate `reveal` (a verified person). One
  client, `static/js/nmas_breakglass.js`, three entry points by `data-nmas-open`: the
  rotate result's new next-step slot (C219), Needs attention's break-glass row, the
  Settings page. The CLI stays for the host-side case, and the result names the laptop's
  verify as an optional check. **Acceptance**: export from the browser, verify the
  download on the laptop (`verify --against` the host's digests), and see job health read
  "current in the record downloaded by <person> at T".
- **The tool updates itself from the GUI (the operator's revision, 2026-09-29): BUILT
  2026-09-30** (the operator: "every commit you push creates this row, so it's the
  operation I'd use most"; placed before P.9 step (b)). docs/UPDATE.md is the design as
  built and the operator's one-time install, with its check (`scripts/nmas-update-check`,
  job health's `updater` row). Needs attention's "behind what is pushed" row opens it,
  and Help > About links to the same page. The row carries SINCE WHEN origin/main has
  been ahead, first seen by the `app-pushed` reader. The rollback bound, 120 s, is
  measured (C241 is the one restart past it). As scoped: The named exceptions become two, FIRST INSTALLATION and BREAK-GLASS;
  upgrading and restarting moves into the GUI. The principle holds: CI decides WHAT can
  deploy, a verified person decides WHEN, and a button that person presses keeps both;
  what was refused earlier was an unattended restart, which this is not.
  1. Preview and confirm through the shared component: current commit, target commit,
     the commits between, and the CI verdict for the target in the gate's own states
     (passed; PENDING, offering to wait and follow it; FAILED or CANCELLED, refused naming
     the run).
  2. **Never restart from inside the request, and the app holds NO privilege** (the
     operator's privilege decision the same evening). The app writes a REQUEST file
     (target commit, the requesting person, the time) and nothing else: no sudo rule, no
     polkit grant. A ROOT-OWNED `nmas-update.path` unit watches that file and starts
     `nmas-update.service`, which runs a ROOT-OWNED script in `/usr/local/sbin`, never
     `~/bin` and never anything in the repository. The script treats the file as a
     request, not an instruction: it re-derives the CI verdict for the target itself,
     refuses anything not passed, and refuses a malformed or stale request by name. So
     the most anything that can write the file can achieve is deploying a commit CI
     already passed. Git runs as the service user (`runuser -u <user>`); only the restart
     runs as root; nothing from the checkout is ever executed as root, or anyone who can
     edit the repository or `~/bin` has root. So the gate's logic (`nmas-deploy`'s
     verdict) gets a root-owned copy for this path; the CLI stays for the host-side case.
  3. **The browser waits on a fact, not a timer**: it polls `/health` until the running
     commit equals the target, then reloads, drawing "waiting for the new version (N s)"
     while the server is down rather than a Cloudflare error.
  4. **A new version that does not come up is rolled back**: if `/health` does not report
     the target within a bound derived from measured restart times (the timeout rule),
     the update job checks out the previous commit and restarts it, and the outcome
     (succeeded, rolled back, rollback failed) is written where the next page load shows
     it. Without it a bad release leaves no GUI to fix it from.
  5. **A release that needs a host step says so**: a new systemd unit, a sudoers change
     or a package install cannot be done by the button; a commit that needs one is
     marked, and the update refuses it naming the step rather than deploying code that
     cannot run.
  6. Person-gated like any confirm, recorded as who updated from what to what, and
     refused for the agent's identity.
  Installing the path unit, the service unit and the root-owned script is a one-time host
  step under the first-installation exception: written install steps, and a job-health
  check that the script and both units are root-owned and not writable by the service
  user, a DANGER row if they ever are. Placement: the operator's to set (it touches no
  device; its first real run is the operator's by definition).
- **Three questions about seed intent's consumers (the operator, 2026-09-29), answered,
  and DECIDED the same evening:** C216, seed keeps declared blocks (the bootstrap stays
  management-only); ADOPT as scoped below (a tool account added, nothing else changed,
  persist previews running against startup), placed after rotate's real run, which is
  done, so adopt is next after revert and retry; CLONE skipped, with GROUP INTENT (one
  owner, devices inherit) recorded as the principled answer, for Stage 9 or after 7.x;
  stage D (vIOS onboarding) waits until a vIOS onboarding is planned.
  1. **Seed on a freshly onboarded device, MEASURED on probe-r1a's real repository** (the
     host's `~/r1-probe-repo-2026-09-28.tgz`, read via the tunnel, driven through the real
     seed and plan routes on a scratch copy): **yes, it is the greenfield bridge.** From
     onboarding's bootstrap-only intent (`574d549`) and its golden (`105905a`), the seed
     committed full-model intent: two interfaces with their addresses and VRF, the
     account by secret reference, the five `line` stanzas, the management VRF and its two
     default routes, at 100% round-trip and 100% modelled. The deploy plan then accepted
     it (every gate passing, the program empty because intent equals the device), and one
     edit to the seeded intent produced a real program the plan would send. **Two things
     the run found, both C117's to know:** the device's template must be APPROVED first
     (the probe repo never approved one; scheme 3 approves on this device's own
     capture); and C216, the P.1 syslog block reaches onboarding's intent and never the
     device, and the seed drops it from intent too. A third came from the harness: C215,
     the plan reads the device's row from the active list, so it chose the IOS template
     until the row was where it looks. **So C117's onboard, seed, deploy loop is sound as
     designed**, with the approval as an explicit step and C216 decided first if the
     acceptance is to show a heartbeat.
  2. **ADOPT, for brownfield: BEING BUILT (2026-09-29). Step 1, the account, is built:** `modules/nsot/adopt.add_tool_account()` adds the tool's account (`nmas` by default, never the supplied name) with rotation's staging, push, fresh-login verify and record, reached through the SUPPLIED credential on a held session; an account by that name already on the device is refused as somebody's; a failed verify removes only what was added (`no username <tool>`, read back gone); a failed record keeps the staged copy and says it is the only one. Found building it: `nmas-rotation-recover` cannot settle an adoption's staged copy (it needs an inventory row an adopting device does not have), so adopt's apply carries its own recovery. **Settled before step 2 (the operator, 2026-09-29):** the SUPPLIED credential is never written anywhere (memory only, redacted and scrubbed; staging is for the tool's own credential), and a device whose SSH logins would never consult a local account (TACACS+ or RADIUS first, or a line password) is refused before anything is sent, naming the method list and what it would take; and the result's next action is the break-glass export, with job health naming the device missing from the record until then. **Step 2, the preview and the apply, is built (2026-09-29):**
     - **`adopt.plan()`** reads the device with the supplied credential and sends nothing. It
       states every gate by name:
       - the list, which is refused if unknown (never derived, C51);
       - the name and address, which must be in no inventory and no manifest;
       - the platform, and the device's own hostname;
       - local login, and whether the account is absent;
       - nothing staged, and NetBox writes on.

       It also shows persist as running against startup (the lines saving makes permanent and
       the lines it loses), the RW communities kept, and NetBox's objects that exist now (to be
       recorded as adopted). NetBox's changes come from the import's own dry run over the
       capture: the importer honours a supplied text in a DRY RUN only, and a real import
       still builds from what is committed. The fingerprint binds the list, device, address,
       platform, tool account, and the running and startup hashes.
     - **`adopt.apply()`** holds the device and plans again from the device as it is, refusing
       a moved fingerprint and naming both values. Then: the account, persist (read back), the
       identity and first golden (`Source: adopt`), NetBox, and promotion last. Before the
       import it reads what NetBox holds and records those objects in
       `data/netbox_adopted.json` (a third record: who, when, why, on what basis), never in
       the created record, so Remove cannot reach them. The result's next action opens the
       break-glass export. Job health's existing break-glass row already names a device the
       last export lacks ("has no entry for it"), now pinned for an adopted one. The run is
       recorded with onboarding's, kind `adopt`.
     - **A stopped adoption RESUMES:** the tool's account on the device, its credential in the
       store for that address, and a fresh login prove it, so a re-run adds nothing.
     - **Its own recovery:** `nmas-adopt-recover`, from a sidecar the account step writes
       beside the staged password (address, driver, account; no secret). Job health names that
       command for an adoption's staged file, and the rotation's for a rotation's.
     - **Found building it:**
       - **Reversible credentials and the golden: DECIDED (the operator, 2026-09-29) and
         built.** The golden records the device's config verbatim, so a local credential
         stored as `password 0` or `password 7` would reach the repository and its remote.
         Every such credential is checked, not only the supplied one: other accounts and an
         `enable password` are refused BY NAME (form, never value), with no conversion offered,
         because the tool does not know those passwords. SNMP communities are the named,
         accepted exception. The SUPPLIED account is refused by default, and the preview offers
         a named opt-in: "Store this account as a secret — same password; the device hashes
         it". Chosen, it is bound into the confirm, drawn in the program, and recorded in the
         receipt as its own step.
         - **How the conversion runs.** It uses rotation's program: delete-then-set for a
           `password` entry, because IOS-XE 17.06 refuses a secret over one (measured). It
           runs on the held supplied session, AFTER the tool's own account is proven, so a
           second way in exists first. A fresh login as the owner with the SAME password
           follows, and the stored form is read back.
         - **If that fails**, the original line goes back and is proven: on the held session,
           then once more as the tool. If neither can be proven, the result leads with DANGER
           and names the line's form.
         - **An account with more than one line is refused.** The delete removes every line
           for the account ("all username related configurations with same name"), an
           autocommand line included. Found by the test.
         - **Adopt never changes the supplied account unless the person ticks this.** The
           person does not need a console for it, and the real run's vrnetlab `admin`/`admin`
           exercises it on a real device.
       - C225: onboarding's NetBox record calls every device a router.

     Remaining: the screen (routes, the preview-confirm adapter and the Device page's client,
     built in the redesign, section 1g) and the real run. The scope as decided:
     Onboarding's phase 2 without phase 1:
     the person supplies list, address, platform and the device's CURRENT credential;
     the tool stages that credential exactly as phase 1 stages the bootstrap one (the
     device override, keyed on the address), verifies (reaching it is the
     verification), captures, then takes the device into management, persists, records
     NetBox, promotes, and the seed follows (seed already handles NEVER-committed
     intent). **Three design points that are the operator's:**
     - **ADD an account for the tool; never rotate the supplied one.** A brownfield
       device's account is usually a person's or a team's, and rotating it locks them
       out. Adding one is the deploy's own rule ("a deploy may ADD an account, never
       CHANGE one"), and it reuses rotation's machinery (stage before the push, verify on
       a fresh login, record, persist, and C210's recovery); only the program differs.
       The supplied credential is then used by nothing, and the result says so.
     - **No RW-community removal, and no change beyond the account.** Phase 2 removes a
       vrnetlab RW community because WE put it there; on a brownfield device something
       real may use it. Adopt names it and leaves it.
     - **Persist previews running against startup first.** A brownfield device's running
       config may carry unsaved changes, and saving makes them its boot config; the
       preview draws the difference and the confirm says so (C184's rule).
     **NetBox:** the device's objects usually exist, made by a person. The import's
     preview (the NetBox tab's, one-shot token) shows creates against updates; updates
     are already recorded with their before-state in the modification record, and
     creates are tagged and recorded as created (true). A NEW adoption record
     (`data/netbox_adopted.json`: object, who, when, why, the authority) holds the
     per-device objects that existed before (the device, its interfaces and addresses;
     never shared site, region or VRF objects, which stay the person's). Remove's
     intersection (tagged AND created) cannot reach an adopted object, so nothing a
     person made becomes deletable. **C100 does not have to come first.** It would let
     NetBox's own changelog tell the tool's writes from a person's; a first adopt needs
     only its own record, snapshotted at adoption, the same kind of self-written store
     the created record already is (C100's stated limit, not worsened: a lost file loses
     adoption facts, never makes an object deletable). The same record then answers A3:
     the nine reference devices are adopted, not recorded as created.
     **Cost**, from the finished same-kind stages: Mode B (5.5 h, 15 commits, the nearest
     multi-part operation over device and record) and Phase 2 DHCP (one real run, 15
     defects, 9 fix commits): about 6 to 10 hours and 12 to 20 commits, most of it the
     real run's findings, on a throwaway that boots vrnetlab's own config (admin/admin,
     no bootstrap: a device we did not configure). **Recommendation: pull adopt into
     7.3, after rotate's REAL RUN rather than straight after rotate's build**, because
     adopt reuses rotation's stage, verify, record and persist, and none of that has run
     on the host from the page yet (the sudo-helper gate is expected there). Revert and
     retry's remainder first (small, most of it written).
  3. **Clone intent ("start this device's intent from another's"): scoped, not built.**
     Cheap if it copies only the DEVICE-INDEPENDENT sections (logging, SNMP settings,
     NTP, services, lines, VLANs, banners) between devices of ONE platform, as one
     operation on seed's model (previewed diff, hash, `Source: clone`, `Cloned-From:`):
     about 2 to 3 hours with a real run. What it cannot copy, and why: interfaces and
     addresses (they are the device), accounts and secrets (a copied `secret_ref` would
     point at the other device's value, the C139 shape: one secret, two owners), and
     routing, whose identity is addresses (router-id, neighbours, networks). So it takes
     ZTP from "ends reachable" to "ends with the fleet's common settings", and the routing
     is still written by hand. **The catch is ownership:** a clone makes N copies of one
     fact that then drift apart, and bulk intent (P.1b) already applies one change to
     many devices. The principled form is GROUP intent (a role's shared settings with one
     owner, each device inheriting), a render-context change larger than a clone. The
     operator's choice between the cheap copy and the one owner.
- **7.3 gains PERSIST** (C164, the operator's decision, 2026-09-28): save on the device
  and read the startup config back, the operation `nmas-persist-native` runs today,
  with the same treatment (preview, confirm, result, receipt, a real run). It is the
  remedy the worst Needs attention row names (`not_safe_to_reboot`: the running config
  holds the only working credential), and no stage had given it a screen. **The first
  action added from the other direction**: seed intent, revert, retry, rotate and
  retire were chosen from what the device page had, before any page asked for an
  action per row; persist came from a row asking. Asked of the other six families
  without an action (running-version, image, the ZTP responder and posture, the
  clab-sync owner, SSH sessions): none is an in-tool operation. The nearest is SSH
  sessions, NMAS's own pool, and its remedy is an operation that is stuck, which C98
  names and by design never forces; the rest are host or Proxmox state, whose action
  is the host command (C164's restated promise).
  **BUILT and ACCEPTED 2026-09-29** (the operator, on r2, the first persist through the
  interface: sent `write memory`, read back the startup config carrying the running
  `username` line, recorded as the operator via the Device page). The Device page's Persist…
  opens a preview that contacts no device: each step (save, read back, record), what
  persist does NOT do (no running change, no rotation, no lab boot file or router.db,
  no golden), the inventory gates by name, the busy gate, the hourly startup check's
  last reading with its age, and a confirm whose effect says the save carries the
  running config AS IT IS, a change not in intent included. The apply recomputes the
  plan (a different hash refuses with nothing sent), holds the device, saves through
  `onboard.persist_on_device` (the one save implementation, C53), records as the
  verified person (`via: device page`), and the result leads with what the read-back
  found (`tests/test_persist_screen.py`, two controls fired). **Acceptance, awaiting
  the operator**: one persist on a real device from its page, read back SAFE, and the
  device's rotation row on Needs attention clearing. The Device page still offers the
  save two other ways, neither verified; C103 recommends Persist as the one.
- **The terminal is REMOVED, not split** (the operator, the same day, superseding "the split stays in 7.3"; NSOT_FEATURE_AUDIT 3b): a source of truth has no pane that goes to the device directly, and even read-only the affordance teaches the wrong habit. 7.3 loses the split, the FIRST reduction in scope found on 2026-09-27; 7.8 removes the terminal with its routes, socket events, session code and tab; 7.3's command box absorbs history, rendering, a running state for long reads and completion built from the allowlist. The `break_glass` gate kind retires with it.
- **7.10 is opened for what defers cleanly** (moved, not cut): Stage 5's in-app monitoring views (Grafana is their home meanwhile, by a link), adopt (A3, which C100 now also blocks), the 900-device list and selection screens (the architecture rule, no per-device work per request, stays in force), switching a network's inventory source, with 7.9's Configure forms already a parallel track and 7.8's removals last as before.
- **7.5 gains two blocking items** (C70's final step could not be completed in the interface): the commit detail view shows the TRAILERS (Source, Actor, Actor-Verified, Intent-Match), which with D10's attribution are the answer to "who changed it and can I trust that", and it lands with the planned "N of M commits carry a verified identity" line, which cannot be drawn from a screen that reads no trailers; and C83, every golden subject saying what happened (captured, restored, re-applied), with "baseline" only when a tag was taken. Measured in the list itself: `ed6548e golden: baseline 1 device(s) re-apply …` took NO baseline, two rows below `e63b2e6 golden: baseline 1 device(s) via save_all`, which DID, of the deliberately broken r2. Same words, opposite truth, adjacent rows.
- **The scheduling principle** (the operator): in this project building is how surveying happens, so every operation gets a real run on the host, and that run's findings are part of the operation's cost, budgeted rather than discovered. Estimate as first written, KEPT as a record: "7.1 took 13 hours and 32 commits; Stage 7 to a usable, console-free interface is about three to four more efforts that size, and 7.10 one to one and a half." **It was wrong by about half; see "The forecast, corrected" below.**

**C98 BUILT (2026-09-27):** one operation per device at a time, across processes, refused by name and never queued (register C98, closed). The preview does not yet say a device is busy before the confirm: that is C99's in-flight state, next with the standing rule's mechanisation.

**The C77 sweep BUILT (2026-09-27)**, `tests/test_no_post_returns_a_stored_secret.py`: every `not_device` POST, from the gate table, driven with a body that reaches its state, with every store planted. Its first real run found three leaks from two stores, fixed here: the backup compare and both NetBox import previews. The previews' community was a plain value, so `mask_payload` masks by key as well. The previews led to C95: NetBox holds every imported device's credential lines and communities (measured on all 10), which is the operator's decision. The sweep's drift check also exposed C96 (the drift panel draws none of its last run, for 7.2). **Next: C70 in the browser**, the first thing run after this lands (r2 is still broken on the host, and `baseline/20260927T154517Z` is still the newest baseline).

**Step 5 BUILT (2026-09-27): scoped restore (C80).** The server already scoped a restore (`build_targets` takes `devices`, and the apply takes exactly the confirmed devices), so C80 was a gap in the interface, and the fix is two choosers ending in the one guarded preview. **The Device page's "Restore from…"** (`static/js/nmas_restore_scope.js`) reads `GET /golden/restore_points/<host>`: the device's golden now, its own golden tags, and every baseline that holds it, newest first. A baseline predating the device is not listed, since re-applying it would leave the device as it is. Each point carries the device's credential state at that ref, measured as the Baselines panel measures it: `current`, `refused` (the restore's own guards stop it), `silent` (an account the ref has and the device lacks would be ADDED back, C79, and choosing it asks for a typed APPLY) or `no_golden`. The username lines never leave. A chosen point goes to `/?restore_head=<host>&restore_ref=<ref>`, the handoff the HEAD restore already used, now carrying the ref. **The Baselines panel's "Re-apply"** asks for a scope first: every device the baseline holds, none ticked, and "the whole fleet" as its own box, so the fleet is chosen rather than inherited. The credential acknowledgement then names only the chosen devices. `tests/test_restore_scope.py` runs against a real repository (r2's real config, a baseline earned by a whole-fleet capture at intent) and executes the shipped chooser against the route's response. **A fixture that reached the wrong case, caught by reading which state came back:** the first "rotation" in the test replaced the password value everywhere on the line, and the fixture's value equals the account name, so it renamed the ACCOUNT. The route answered `silent`, correctly for an account added back, and not for the rotation the test meant. Both cases are now tested from the same real line. The payload check found two fields the chooser carried and did not draw (`subject`, `list`); both are drawn. Next: the C77 sweep, then C70 in the browser.

**Step 4 BUILT (2026-09-27), both layers.** The record layer (`7910e09`): `save_golden()` compares every capture with committed intent (`modules/nsot/intent_match.py`, the deploy plan's own comparison), writes a computed `Intent-Match:` trailer on every golden commit, and takes a baseline only with coverage AND every capture matching (C91 found and fixed on the way). The operation layer: `POST /golden/capture/preview` reads each device NOW and returns only a masked preview, with each device's diff against its golden and, under what will NOT happen, where it departs from its committed intent and why no baseline tag will be taken. `POST /golden/capture/apply` re-reads each confirmed device, refuses one whose capture hash moved, and commits once (`Source: capture`, or `save_all` for the fleet) as the verified person. Its result is drawn by the component and is never green while a capture departs from intent. `static/js/nmas_capture.js` is the one client: the Device page's Capture button opens it for one device, and **Save All opens it for the fleet**, so `/golden_configs/save_all` (one click to golden, baseline and remote) is removed. It differs from the plan above in one way: the source is `capture`, not `manual`, so git can tell a person's capture from a hand edit. `tests/test_capture.py` drives it on r2's real configuration with the host's exact break. **Found while wiring it:** `tests/js_source.with_loaded_scripts` modelled only the page's own generated scripts, so a component loaded from `static/js/nmas_*.js` was invisible to every renderer test that reads the assembled page; it now includes them (Bootstrap, also vendored in `static/js`, is deliberately not matched).

**Steps 2 and 3 BUILT for deploy and restore (2026-09-27):** `preview_confirm.operation_result()` builds the six result parts from the receipt rows `_write_receipts` has just written, and `previewConfirmResultHtml` draws them; `_renderDeployResult` is now wiring, and a restore opens its result in a modal instead of a toast. The level (and so the colour) is computed on the server and only drawn. `GET /deploy/receipts` and the Device page's Changes tab read the record back, one device's row of a batch saying exactly that. The rule's PENDING list: 33 to 31. **C85 fixed in step 2 (2026-09-27)**: the NetBox import's outcome is a result on the sync card, levelled by `complete`, and the rule's PENDING list is 29. Then the remaining results as their operations are retrofitted.

**Step 1 BUILT (2026-09-27):** `tests/test_results_are_drawn.py`, with the survey as its measured list (33 pending, 8 with no GUI, 0 drawn by the component), `FALSE_GREEN` (3) and `UNESCAPED` (2). Writing it found C87: the reachability check had counted intent revert reachable because the editor's own fetch shared its prefix.

**The overlap with 7.3, stated:** capture and scoped restore are the first
Device-page ACTIONS. 7.3 builds the rest of that page around them rather
than beside them.


### 7.1, onboarding and NetBox Remove retrofitted, 2026-09-27

**Onboarding's Create (C86).** Drawn by the result component in place of the
review. A complete phase 1 is "Partly done" and PENDING, never green, with
the next step stated. The record is re-read from the device's pending row.

**NetBox Remove (C121).** Drawn by the component from the ROW that records
the removal (`data/netbox_removals.jsonl`, 0600, scanned for secrets like
the modification record). So the result at apply and the record read back on
the NetBox tab's Removals panel (`GET /netbox/safety/removals`) are one
computation. Its level comes from `complete`: NetBox refusing some deletes
is "Partly done", with each refusal and its reason under "What did not
happen". Nothing recorded a removal before this.

**The false-green class, and a correction to "now zero".** When
`FALSE_GREEN` emptied with C86, the claim was that the class of "colour
asserting more than the operation earned" was zero. It was not. The list
held what the result survey had found, and three more were green and on no
list:
- NetBox Remove over a partial removal;
- a bulk run with failed devices ("completed" means every device was
  tried);
- a NetBox inventory refresh that skipped devices.

All three are fixed. The class is now held by a CONSTRAINT rather than a
list: `GREEN_TOASTS` declares every green toast in the shipped pages with
why green is earned there, and a scan that parses each `showToast(` call
(the first line-based count missed six multi-line calls) requires the two
to match exactly, both ways. A new green toast fails until someone states
its reason. What it cannot see: a green badge or colour drawn other than
by a toast; `FALSE_GREEN`'s shape remains for those.


### 7.1 acceptance, stated 2026-09-28

**What it asserts** (the operator's wording): *every operation that changes a
device or the record has one preview, one confirm, one result and one record,
and none of it requires a console.* Concretely, for each operation in scope:
- the PREVIEW is drawn by the preview component (`nmas_preview_confirm.js`);
- the CONFIRM is bound by hash and made as the verified person;
- the RESULT is drawn by the result component from the record the apply
  wrote, so the screen and the record are one computation;
- the RECORD is read back later from a named route;
- no step needs a terminal, a network tab or the log.

**How it is measured.** Two checks, each a list that only shrinks, plus one real
run:
- `test_preview_confirm.py`: previews on the component (`RETROFITTED`) against
  those not yet moved (`RETROFIT_PENDING`);
- `test_results_are_drawn.py`: of the 38 actions gated `confirm`, `approve` or
  `publish_remote`, the results drawn by the component with a reader
  (`RESULT_COMPONENT`), the pending ones (`PENDING`, every entry naming what it
  draws today) and those with no GUI (`NO_GUI`, each homed by the reachability
  list);
- **C70**, the restore run for real on r2 in the browser, passed on its
  re-run with the result screen rendering (C84 closed).

**In scope, and where each stands:**

| Operation | Preview | Result and record |
|---|---|---|
| Deploy | component | component, from receipts; Changes tab |
| Restore (and its handoffs: an approval's revert, restore from a ref) | component | component, from receipts; Changes tab; C70 passed |
| Capture (Save All, one device, the "no golden" scope, a drift approval's handoff) | component | component; golden history |
| Onboarding: Create | component (`onboard_preview`; `onboardReviewHtml` removed) | component (C86); pending row |
| Onboarding: Verify, Abandon | none (one click each; Abandon asks first) | component, from the onboarding run record; the pending banner (each row's last run, and "finished recently" for a run that took its device off the list) |
| NetBox import, import-all | component (`netbox_import_preview`) | component; the sync card |
| NetBox remove | component (`netbox_removal_preview`, the cascade drawn in it) | component (C121); Removals panel |

**Explicitly NOT in 7.1** (each with its home, so the boundary is stated and not
implied):
- **rotate, retire and persist: 7.3.** They have no route at all; they are host CLIs.
- **bulk intent: 7.4, deferred by the operator.** It is fleet-shaped, and its CLI
  is the path in use.
- **The Device page's actions: 7.3.** Run command, save config, save to startup,
  upload and delete a file.
- **Bulk operations: 7.4.** Execute, upload, delete, reload; also refresh
  hostnames.
- **Template approve and save: 7.6.** Also the intent editor's commit, and
  revoke, bindings and extraction (NO_GUI).
- **Remote push, auto-push, acknowledge and verify-write: 7.5.**
- **The agent's run, chat, approval approve and reject: Stage 8.**
- **Freshness authorise (NO_GUI): 7.6.** Also intent revert and retry, and
  remote adopt (NO_GUI).

**The numbers, 2026-09-28, measured by the two checks (not counted by hand):**
- **Results:** **9 of 38 drawn by the result component**, each with a record read
  back: deploy, restore, capture, onboarding Create, Verify and Abandon, NetBox
  remove, import and import-all. **21 pending, every one homed in a later stage**
  (the list above: 7.3, 7.4, 7.5, 7.6, Stage 8), and 8 with no GUI. `TOAST_ENOUGH`
  is empty.
  - The survey began at 33 not drawn: 16 drawn until closed and 17 toasts, of a
    population of 41 before removals.
  - A figure of "25" reported on 2026-09-27 was the check's CEILING, not its
    count (C125); the ceiling is the count now, 21.
- **Previews:** deploy, restore, capture, onboarding and NetBox import/remove on
  the component. **Bulk intent is the one not moved, deferred to 7.4 by the
  operator**, and `RETROFIT_PENDING` holds it and nothing else.

**7.1 is met when:**
- onboarding's review and the NetBox safety modal draw with the preview
  component;
- onboarding's Verify and Abandon draw their results with the result component,
  with a reader (the pending row);
- `RETROFIT_PENDING` holds only bulk intent, marked deferred;
- `PENDING` holds nothing homed in 7.1.

**It is MET (2026-09-28), on the laptop suite (5025 passed, 0 errors, serial).**
Each condition is a check, not a sentence: `test_preview_confirm.py`
(`RETROFITTED` has five screens, `RETROFIT_PENDING` only bulk intent) and
`test_results_are_drawn.py` (`RESULT_COMPONENT` 9, `PENDING` 21, its ceiling
equal to its count). What it does NOT claim: C70's restore is the only one of
these operations run for real on the host since its retrofit. Onboarding's
review, Verify and Abandon, and the NetBox modal have been driven through their
REAL routes in the suite and not yet clicked on the host. Walking each once is
the next thing, by the rule that a path never run fails on first use.

### 7.1's stated limit, and the two runs that close it (before 7.2)

**The limit, stated as part of the acceptance** (the operator, 2026-09-28):
only RESTORE has been run for real on the host since its retrofit (C70's
re-run). Onboarding's review, Create, Verify and Abandon, and the NetBox
window (import, import-all, remove) have been driven through their REAL
routes in the suite and clicked by nobody. C70's lesson is why that is a gap
and not a formality: the operation was correct, and everything AROUND it
failed (C92, C97, C98, C99). A suite that drives the route cannot see a
session pool, a second mover, a status dot or a result that arrives late.

**Scheduled BEFORE 7.2**, because 7.2's landing page reads the stores these
operations write (the onboarding run record, the removal record, the sync
card's stored summary, the pending rows), so a defect in the writer surfaces
as a wrong row in the reader, one layer from its cause. Each run's findings
are budgeted as part of its cost (the scheduling principle), and each is
recorded the turn it is raised, after searching the register.

- **R1, onboarding, on a throwaway device, into a THROWAWAY LIST** (a probe
  lab, never a fleet device: a lost device must cost a `containerlab
  destroy`). Its own list (say `probe-r1`), so that the NetBox objects its
  phase 2 creates are recorded under a list whose Remove touches nothing
  else: that is R2's real target (below).
  0. Take the census baseline BEFORE anything writes (step 0a's rule):
     `python3 scripts/nmas-netbox-census --out /tmp/census-before-r1.json`
     on the host, fresh. The ZTP probe's `/tmp/census-ztp-a.json` is hours
     old and the fleet has moved since: a compare against it would attribute
     every change in between to this run.
  1. The review: the preview component draws the plan, the bootstrap config
     under its caption ("sent to no device"), every refusal first.
  2. Create: the result reads "Partly done" and PENDING, never onboarded.
  3. Verify BEFORE the node has booted: a real "did not answer" result, its
     causes in order and the recovery line, left on screen. **After a page
     reload, the pending row shows that failed run UNDER it** (the operator's
     addition): the causes and recovery are the parts nobody reads when
     things work, so this is their first real drawing.
  4. Boot it, Verify again: onboarded. **The row leaves the pending list and
     the device appears under "Finished recently" rather than vanishing**
     (the operator's addition): a successful Verify takes the row away, which
     is the whole reason the run record exists, so this transition is the
     thing to watch.
  5. A second device created and ABANDONED without booting (it needs no
     node): the result names every step and "the name is free", and it is
     read back under "Finished recently".
  The acceptance: each of the five results drawn by the component and read
  back after a reload, and the in-flight panel naming Verify while it runs.
- **R2, the NetBox window, in two halves** (revised 2026-09-28 after reading
  the host, read-only).
  **There are no ztp-a leftovers**: no `ztp-a` list, no `ztp-a` entry in the
  created-object record, no NetBox device matching "ztp", and the only
  objects tagged `nmas-managed` are r6 and its eight. The P.6 teardown removed
  its own. And the host's record holds a `lab` slug that is the suite's
  fixture, with ids pointing at REAL fleet objects (C131).
  - **R2a, now, previews only, after the C130 fix is deployed** (a preview
    used to forget the record of any object it could not read).
    1. Import preview on `Default`: each object by name, each update's
       fields, "nothing is deleted". Confirm nothing.
    2. Remove preview on `Default`, **read and NOT confirmed**: confirming it
       would delete r6, a managed device, from NetBox. What it should show,
       from the host's record and NetBox read 2026-09-28:
       - 9 deletes: `ipam/ip-addresses` 85 (10.255.0.32/24) and 87
         (10.255.1.16/32); `ipam/prefixes` 55 and 56 (both 10.255.1.16/32,
         in two VRFs, C133) and 57 (10.255.0.0/16); `dcim/interfaces` 62
         (Gi1), 63 (Gi2) and 66 (Loopback0); `dcim/devices` 11 (r6);
       - left alone: none, gone: none, could not be read: none;
       - the gate "every recorded object read from NetBox" PASS, and the
         cascade gate "asked";
       - "ALSO DELETED BY NETBOX" only if NetBox holds another object on
         r6's three interfaces: that would be a real finding, named, not a
         defect of the preview.
       A defect is anything else: a delete not in that list, a "Could NOT be
       read" line, or a gone line.
  - **R2a DONE 2026-09-28 (the operator), nothing confirmed.** Remove preview:
    exactly the expected nine, left alone 0, nothing gone or unreadable, the
    read gate passing, the cascade line drawn as fixed. Import preview, after
    C135: 39 lines down to 14, updates 38 down to 13, so **25 of 39 were
    phantom**, writes the real import never makes; what remains is one create
    (`ipam/prefixes 0.0.0.0/0`), nine devices that change `local_context_data`,
    three addresses that change `vrf` and one interface description. R2a's
    own findings: C130, C131, C133, C134, C135. The nine
    `local_context_data` changes are C95's field: the import's whole remaining
    device-level work was writing unmasked credentials, so no import is
    confirmed until C95 (a) is deployed.
  - **WHERE IT STOPPED, 2026-09-28 night (the operator), nothing half-applied.** On the host:
    probe-r1a is up and onboarded in the `probe-r1` list, its credential override (`10.255.0.33`)
    is still held, the throwaway lab (`~/labs/r1-probe` on the clab host) is up, and
    `rotation:probe-r1a` is LEFT in job health deliberately, as C54's real instance.
    **First, before any teardown step: reboot probe-r1a** (the product's persist step has never
    had its reboot run): reload it from the GUI, wait for `Startup complete`, then
    `show version | include uptime` through the command box. Pass: a short uptime, NMAS in on
    the credential it holds. Fail is A, and the teardown stops. **Then the teardown**: the
    evidence tarball (C147's `105905a`), delete the list, clear the override (read before and
    after), destroy the node without `--cleanup`, re-run the heartbeat check. **Then 7.2, from C54.**
  - **R1 and R2b DONE 2026-09-28 (the operator): 7.1's stated limit is CLOSED.** R1 ran all seven steps
    (onboarding's review, Create, Verify before and after the boot, and Abandon, each drawn by the
    component and read back) and found C147 and C148 and closed C57. R2b: the Remove preview for
    `probe-r1` listed exactly the 8 predicted objects, in dependency order, nothing left alone; the
    result, "NetBox accepted 8 delete(s) and refused 0", read back from the record; and the census
    compare was PASS at 235 objects and 9 tagged, identical to the baseline, with 0 modifications on
    objects that existed at it. The first real provenance-based removal deleted only what NMAS
    created, on a shared system, a person confirming. Restore (C70), onboarding (R1) and the NetBox
    window (R2a, R2b) have each been run by a person. Its one stated limit, the cascade not
    re-read after the removal, is C150. **Three real runs, three sets of findings no test could
    reach** (C70, R2a, R1): the rate has not dropped.
  - **R1's total, the run that kept paying (the operator, 2026-09-28):** onboarding one device and
    trying to USE it produced C147 (the golden committed by the rotation before `remove_rw`), C148
    (no path from onboarding to deployable), C151 (heartbeat config with no alert rule), C152 (a row
    the tool's session paths could not open, and a reload that said "sent" over nothing), C153
    (reload's success is the session dropping) and C154 (the plan rendered a bootstrap intent, and
    the shared handler said "check the logs"), closed C57, and PROVED THE REBOOT: probe-r1a came
    back from a GUI reload in a minute and NMAS logged in on the credential it holds.
  - **R2b, the real removal, after R1**: Remove `probe-r1` (the list R1
    onboarded into). Every delete named, what NetBox takes with them asked,
    then confirm, read the result, re-read it on the NetBox tab's Removals
    panel, and `nmas-netbox-census --compare /tmp/census-before-r1.json`.
    The acceptance: the preview's count is the executed count, the compare
    PASSes (its modifications status read, not assumed), and nothing a
    person curated moved.

### The forecast, corrected (2026-09-28)

*(Superseded by section 11's forecast, 2026-10-02; kept as the record.)*

**The estimate was about half the real number.** Measured partway through 7.1:
"13 hours and 32 commits", with the rest of Stage 7 "three to four more
efforts that size", which implied about 110 more commits. 7.1 finished at
**69 commits over 20 h 41 min of wall time** (ff6fc24 to 763649e): 2.2x the
commits and 1.6x the hours it was forecast from. So the rest of Stage 7 is
**about 200 to 280 commits**, not about 110.

**Why it was wrong, which is the useful part** (the operator's reading): an
estimate made from an unfinished stage is made from the part that went to
plan, because the findings that triple a stage have not happened yet. It is
the same shape as every measurement this week taken before the thing it
measures is complete. Estimates here are made from FINISHED stages only, and
say which stage they were made from.

**Roughly one new finding per commit, stated as measured, not softened.** The
register went from 97 rows to 168 across 7.1's 69 commits: 69 C-rows (C60 to
C128) and 2 E-rows. At least six came from side work rather than 7.1's own
screens (C119, C120, C123, C124, C125, C126). At 763649e about 47 were
closed, 8 decided and about 14 open (a text classification, so approximate).
The rate did not fall as the stage went on.

**The rate is a property of the WORK, not of a stage** (the operator,
2026-09-28). After 7.1 closed, R2a's run and the community branch that grew
out of it took 21 commits over 2 h 34 min (763649e to 995498a) and added 14
register rows (C129 to C142): about one finding per commit, 7.1's rate
exactly. So a stage's forecast carries its findings whether they come from
its own screens or from a run beside it. What changes the total is what the
findings are ALLOWED to claim: since 2026-09-28 a finding is triaged, and
only live exposure that matters here and real blockers interrupt the
functional path (NSOT_PLAN Stage 9).

**7.2, predicted from the finished 7.1, to be checked when it closes:** 40 to
70 commits over about a day, and 30 to 50 findings, most of them in the
SOURCES rather than the screen. 7.2 changes no device, so the confirm-hash and
concurrency findings that drove 7.1 should mostly be absent. It reads every
source, which is where the absent-versus-unreadable and wrong-thing-looks-right
families live, and four of those were found this week in stores 7.2 draws
from. R1 and R2 above are extra, and precede it.
**Checked 2026-09-29, a day late (at the writeup's backfill):** 37 commits in
about 4 hours (19 of them 7.2's steps) and about 17 findings (11 rows, six with
no ID). The operator's reading: the correction after 7.1 overcorrected. The
one-finding-per-commit rate held for 7.1 and not for 7.2, because 7.2 read stores
7.1 and that week's sweeps had already hardened: a result about where findings
come from. This paragraph used that same fact to expect MORE findings in the
sources. Checking a forecast at close is now part of closing (section 10, item
14).

**7.2 step 1 BUILT (2026-09-28): the row shape and the source contract, job
health first.** `modules/attention.py`: `row()` is the only constructor and
refuses a row with no cause or no action; every row carries what, devices,
since, cause, operands, the one action, a server-decided level and an empty
`triage` slot (NSOT_PLAN 8.6). `source_result()` records when each source
was read, how long the read took and what it looked at, and makes an
unreadable source a row. `GET /attention`, drawn by `static/js/nmas_attention.js`
at the top of the landing view. job_health's rows now carry `device` (or
`address`) as a field and `since` (a failing streak's first failure, or when
a success aged past its window), never parsed from the unit string. Job health
is read live, because its cost is per job and not per device; the read time is
on the page, so the host's measurement decides whether it moves to a cache.
Nine of ten job-health row families write their remedy into the detail and
have no separate action: the row says so (`known: false`) rather than
inventing one, and that set is pinned to shrink. Next: the other section 1a
sources, each through `source_result`.

**7.2 step 2 BUILT (2026-09-28): drift, with coverage (C96 closed).** The last
stored run, never a re-check: a row per device it did not clear (drifted, not
checked, unreachable) naming the device and the coverage, and rows for the
checker's own state (off, never run, failed, a stored run older than two
intervals). The contract gained `value_at`: a stored source is dated by its
VALUE (the run), a live one by its read, and the page draws both when they
differ. The drift panel draws what a run found. **When approvals join as a
source, a queued drift item ATTACHES to its drift row**, never a second row:
drift queues one item per drifted device, and two rows about one event is the
three-reports problem (NSOT_PLAN 8.6). **The actions:** 7.3 as scoped closes
none of the nine families without one (C164); persist is the remedy two of
them name and no stage puts it on a screen, a decision for 7.3's scope.
**Decided 2026-09-28: persist is a 7.3 Device action** (see 7.3's scope).

**7.2 step 3 BUILT (2026-09-28): approvals and pending onboardings.** The
attach rule is in the contract: a row names the row it is ABOUT
(`attach_to`), and the page folds it into that row, whose action becomes the
queued item's; a row whose target is absent stands alone and says so. A drift
item folds into its device's drift row, so one event is one row and the count
stays scannable. The queue is read through `read_pending()`, which writes
nothing: `get_pending()` saves on every read (C159, measured). Pending
onboardings list overdue, stale and an unfindable staged credential; a device
in its first day is counted, not listed, and ZTP progress is not asked (it
asks Kea per device). The response is masked on the way out, since rows quote
their stores.

**7.2 step 4 BUILT (2026-09-28): rollback blocks.** Through the ONE
classifier the listing uses (`routes.templatize.rolled_back_notes`, extracted
from the route): a note is a row only while the program a fresh plan would
send still contains what failed; a stale note is counted. Its work is per
NOTED device, bounded by the rollbacks on record. An unreadable record (C158)
is ONE row for the list and plans no device: asked per device it returned the
same blocking note for each and planned the whole fleet to say one thing.
Revert and retry have no screen (7.3), and each row says so. Remaining from
section 1a: freshness, Grafana alerts, a failed deploy, an unearned
baseline. (**Corrected the same day:** this note first said "C17: `grafana_url`
empty on the host". C17 had closed on measurement the day before, both URLs
set; the line was taken from CLAUDE.md's restated gate list without reading
the register.)

**The rest of 7.2, as it stands (2026-09-28, the operator's review).** One
shape, a background READER JOB, built once with the Grafana alert reader as
the first real one (8.6's constraints: each instance kept with its identity,
start and window; a row per incident with members; a triage slot): it runs on
a schedule, stores its result with `value_at`, records its own liveness as a
job-health row, and ANNOUNCES when it finishes (C58, part of the shape, not a
feature after). Freshness, the status bar's integration health, and C92's
reachability reader reuse it. **A reader names its endpoint and its time** (the
operator, C165): Grafana's rules view and its alertmanager disagreed on what
was firing (0 against 2), so a row says "read from alertmanager at T", never
"2 alerts firing". **And it tells three states apart** (C165, C166): the
condition fired, the datasource returned nothing (`DatasourceNoData`), and
the rule errored; the alertmanager presents all three as active instances. A
rule in no-data is itself a Needs attention row, since a monitor that is blind
(or whose quiet cannot be told from blindness) is what the page exists to
show. Precondition MEASURED 2026-09-28: NMAS's token holds
`alert.instances:read`, `alert.rules:read` and the full `alert.*` set; the
instances carry `fingerprint`, `labels` and `startsAt` (the precondition was
which Grafana role can read alert state, 8.6: measured, not assumed). Simple
sources on stored data: a failed or partial deploy (receipts), an unearned
baseline, a line authorised again and again (C140 (1)). The action work:
C164's host commands lifted into the action field, and C151's (generate the
rule). C38's adjacency rows. **C92 is SPLIT** (decided): the reader, its
liveness row and a Needs attention row are 7.2's LAST step; moving its six
consumers and drawing the dot are 7.3's, where the device list and Device
page are rebuilt. The reader is the only part of 7.2 that 7.3 needs.

**7.2 step 5 BUILT (2026-09-28): deploys and restores.** Each device's LATEST
receipt, judged by the one decision the result screen uses
(`preview_confirm.result_level`): a row unless it finished clean, so a later
clean run supersedes a failure and a device leaves the page by being deployed,
not by aging. Danger when a program was sent, warning when nothing was. Tested
on the receipts a real apply writes. **For the unearned-baseline source
(next): the denial's reason has no durable record.** `save_golden()` decides
the baseline AFTER the commit, and the reasons live only in its return value;
the `Intent-Match:` trailer is durable, the coverage reason is not. So the
source derives from git (the newest golden commit against the newest baseline
tag, with its Intent-Match trailer) and states the coverage reason as not
recorded, or the reason is made durable first; a decision for that step.

**7.2 step 6 BUILT (2026-09-28): the baseline decision, made durable, then
read.** The operator chose durable first. `save_golden()` decides the
baseline BEFORE the commit now (every input is known by then) and records it
IN the commit: `Baseline: earned`, or `Baseline: denied: <reasons>`. A caller
that decided itself (deploy and restore measure coverage, then pass
`baseline`) passes its reasons (`baseline_reasons`), which lived only in its
report. A save that never claimed the network (a one-device capture:
`baseline=False`, no reasons) records nothing, because it made no decision.
The source reads the NEWEST DECISION (one `git log --grep`), never the newest
commit, so a capture after a denial cannot hide it, and a later earned
baseline supersedes it. **Not recorded, stated:** the no-commit path (a Save
All that changed nothing) decides without a commit to carry the decision;
the earlier decision stands, and the result screen shows this one.
The row names the decision's OWN commit and time (the operator), so a reader
can see it predates a save that decided nothing.

**7.2 step 7 BUILT (2026-09-28): a line authorised again and again (C140
(1)).** From ONE read of the receipts, through the counting the preview's
aggregate already used (`receipts._authorisation_counts`, now shared; the
preview's shape unchanged): the same line on the same device authorised
three times or more is a row. Twice can be a retry; a third is a routine.
It blocks nothing; 8.8's point is that "ok" typed thirty times is the
finding.

**7.2 step 8 BUILT (2026-09-28): every row carries its action (C164's 7.2 half,
and C151).** Each job-health row family's remedy, which its builder wrote into
the detail, is its row's `action` field, built in the same place: persist for
rotation and startup rows (the command they name), verify the boot file, record
from the staging copy, recover on the console, set or declare a setting,
withdraw a contradicting declaration, match the sync owner, install or start
the ZTP socket, read its journal, the in-flight panel for SSH sessions, restart
for a mixed version, Proxmox's task log for the images. The heartbeat check's
remedy (regenerate the rules, P.1 step 5) is declared with the job itself, which
closes C151. Every command named was checked against the script's real
arguments. The page reads the row's own action first; a state with no remedy
(`unknown`: the check could not ask) says so rather than inventing one. Tested
on REAL rows from each family's own builder.

**7.2 step 9 BUILT (2026-09-28): the reader-job machinery**
(`modules/reader_job.py`). One background read of an outside service,
stored under `data/readers/<name>.json` with the time of its value, a failed
read keeping the last good one, its liveness a job-health row (`not_run`,
`failing` since the streak began, `never_succeeded`, `stale`, `unknown`),
and an announcement of its data keys when it finishes (C58, wired to the
page in the next step). A reader is refused at registration when it omits a
claim a consumer relies on: its endpoints, the measurement its interval
comes from, the keys it announces. The ten rules this thread produced are
its docstring, each naming its finding, because the next three readers
inherit them by reuse. Measured for Grafana before building: both rule
groups evaluate every 60 s, and the three endpoints answer in 35 to 150 ms.
C58's premise was false: the index page holds no Socket.IO connection.

**7.2 step 10 BUILT (2026-09-28): the announcement (C58's mechanism).**
`invalidation.announce(keys, by)` sends a background change's data keys over
the app's socket; the Socket.IO client loads once, in base.html, and the
registry dispatches an announcement exactly as it dispatches a response
header, so a panel subscribes once and hears both. A reader announces after
every run, a failed one too. A page whose socket dropped or never connected
says so in one element every page has, drawn only after a first attempt, so
a fresh page carries no warning. Needs attention subscribes to the keys its
sources read; its minute's poll stays for the sources nothing announces
(systemd units, receipts written by another process). The drift run, the
post-commit push and the NetBox refresh are C58's remaining members.

**7.2 step 11 BUILT (2026-09-28): job health is the first reader.** The
operator measured the landing view on the host: job health 9,797 ms, every
other source together under 60 ms, so job health was 99.4% of the page. The
page built to surface problems asked systemd, the journal and Proxmox on every
load: the section 0a violation in its own landing view. It is now a reader
(`modules/readers/job_health_reader.py`, every 300 s: the read costs 9.8 s, its
timers move hourly or daily, and the two rows that move in minutes are drawn
live elsewhere). Needs attention reads the stored value, dated by it.
**Its own liveness is not in its value:** the stored rows exclude every
`reader:*` row, and the page judges the readers from their stores at request
time. Otherwise a stopped job-health reader would freeze a cache whose own
row said ok for ever. A cache that holds no value yet is an unknown row
("not read yet"), never "nothing needs attention". `/jobs/health` stays the
live, ask-now read.

**7.2 step 12 BUILT (2026-09-28): the healthy page is one line.** The
operator's objection: eight lines of read times and provenance at the top of
the landing view, in the common case, and a line more with every source to
come. Decided as (a) with (c)'s forcing. With no rows and every source
answered, the panel is one line that still makes the positive claim:
*Nothing needs attention · 8 of 8 sources answered, read <time> · oldest
value: <source>, from <time>*. The full list is one click away, and a person
who opened it keeps it open across the minute's redraw. The OLDEST value is
named, with its source, because a summary is only as fresh as its weakest
source, and one old for a reason (a baseline decided days ago) reads as that
source's age. Any source that did not answer forces the full list open, even
with no row (an unreadable source is already a row; the guard holds if one
forgets). Stale sources are rows of their own, so a zero-row page already
means none is past its own bound. Grafana's reader is next.

**7.2 step 13 BUILT (2026-09-28): the live-data contract, decided once for
every Stage 7 panel.** The operator's standing requirement: a page showing
live information updates itself, and a panel that cannot tell whether it is
current SAYS SO. The absence of an update is otherwise indistinguishable from
nothing having changed: absent against unreadable, in the browser. Three
parts, each covering one way of looking current while not being:
- **the heartbeat proves the CHANNEL.** The server beats every 30 s (half the
  fastest reader's interval), and a page that misses 2.5 beats marks every
  subscribed panel ON ITS DATA as not updating, not only in a status area;
- **age against the source's own promise proves the SOURCE.** A heartbeat
  keeps arriving while a reader is dead, so every time-sensitive value
  carries `value_at` and `stale_after_seconds` (a reader's interval times
  three, stored with its value; a drift run's interval times two), and the
  page judges it on a local 15 s tick that makes NO request. A stamped panel
  shows its age and marks itself stale past the promise; a value with no
  promise says how long it stays current is not known; a value with no time
  says whether it is current cannot be told;
- **catch-up on reconnect** re-fetches every subscribed panel once, covering
  what was announced while the channel was down (not on the first connect).

**No data polling, and that answers the cadence question under section 0a.**
Every change to displayed data has a sender: a mutating route (its keys
broadcast to every OTHER page: another browser's deploy or push), a
background job in the app (it announces when it finishes: the drift run,
the post-commit push, the NetBox refresh; C58's remaining members), or
something outside NMAS (a reader, whose interval comes from how fast the
source changes). The browser's periodic work is the local tick, whose cost
is the same at nine devices or 900; server cost is per reader per
interval, never per open page. Needs attention keeps its 60 s poll until
every sender announces, because it is what catches a write from another
process; its own promise (150 s) marks the panel stale if those fetches
stop. **An announcement closes the delay in HEARING a result, not the
delay in PRODUCING one**: the page's freshness is bounded by the slowest
checker's schedule (drift, 30 min), which is the checker's to change.
Needs attention adopted it first: each source is judged against its own
promise, a stale source forces the full list open, and the panel redraws
from its last payload on the tick.

**Baseline history, confirmed as expected (the operator's note 3):** the
decision trailer is written from 2026-09-28, so the eleven older baselines
carry none and the source says so. Their tags ARE the earned half of that
history, so the line can name the newest baseline tag as the last decision
known to be earned, while a denial before 2026-09-28 stays unrecoverable.
Scheduled with the rest of the baseline source's work, not built now.

**7.2 step 14 BUILT (2026-09-28): Grafana's alerts, the reader pattern's second
instance** (`modules/readers/grafana_alerts.py`, every 60 s: both rule groups
evaluate every 60 s, measured). It reads three endpoints and names them on
every value: the ruler (configuration), the rules view (evaluated state and
health) and the Alertmanager (fingerprint and `startsAt`). Tested against a
real read-only capture (`scripts/nmas-capture-grafana-alerts`), every firing
case a minimal edit of a real instance. What it keeps, each from a finding:
- **condition, no data and error are three kinds** (C165: Grafana's own
  DatasourceNoData alerts made "0 against 2" read as a disagreement);
- **a rule in no data is a row**, with no alerting instance needed (C166,
  C168: rules sat in no data for days);
- **which device, and from where**: the rule's generated label, the line's
  origin-id by the ONE pattern (`ORIGIN_ID_PATTERN`, and a rule using another
  is named as not the definition), or the polled address, stored as an
  address and resolved against the inventory by the page, which says when no
  device holds it or the device has left;
- **an instance is rule, fingerprint and `startsAt`**, and incidents group on
  the ONSET (the start minus the rule's window), within 360 s: a heartbeat
  onset's own uncertainty (its 300 s period plus the 60 s evaluation). Every
  heartbeat alerting at once is ONE incident whose subject is the pipeline;
- **Grafana answering and not evaluating** is its own row (a group more than
  three intervals past its last evaluation), since 200 with nothing firing
  reads exactly like a healthy fleet;
- **completeness from Grafana's own counts**: a group or rule counting more
  than it lists, or a next-page token, refuses the read;
- **the floor**: an inventory device with no heartbeat rule the reader SEES is
  a row (a permission or provisioning gap);
- history is NOT read (capped at 100 rows; 8.6 reads it uncapped).
Needs attention draws each incident's members with where each device came
from and the onset's basis, subscribes to `alerts`, and judges the value
against the reader's promise (180 s) under the live-data contract.

**7.2 step 15 BUILT (2026-09-28): freshness, the pattern's third instance**
(`modules/readers/freshness_reader.py`, every 300 s). The signal (is what
Oxidized holds the approved state?) ran `freshness.check()` on EVERY index
page load: one Oxidized fetch and one committed-golden read per device, per
request, and its stamp was the fetch time, so an hour-old comparison looked
current. Now the reader compares every registered list and stores each
list's report (a list it could not answer about is stored with its reason,
never absent); `GET /freshness/report` serves the stored value with its time
and promise, 503 when nothing is stored ("not the same as nothing having
diverged"); the panel stamps the VALUE's age under the live-data contract and
hears the reader's announcement. Needs attention gains a Freshness source:
UNAPPROVED is a row (a redeploy would boot it), INCONCLUSIVE is a row, a poll
race and an authorised divergence are counted. The sanitiser's GATE stays a
live read on purpose: it compares the bytes its caller is about to write.
Measured for the interval: Oxidized's index 16 ms, a config about 4 ms per
device; the ten nodes' last polls spread over 44 min at one read, and
Oxidized's own interval is not served by its API.

**Integration health is its own reader, consumed by both the status bar and
Needs attention** (the operator's question, decided 2026-09-28, for the next
step). One producer, two consumers: "Prometheus is unreachable" is a Needs
attention row with a cause and an action, and the status bar is a colour
drawn from the same stored value. A tenth source would read integrations per
page load (the section 0a shape job health just left) and make the bar and
the list two answers to one question. An integration left unconfigured is a
state, not a row: where the emptiness switches a guard off, job health's
`unset_guard` row already says so.

**7.2 step 16 BUILT (2026-09-28): integration health, the pattern's fourth
instance, and the status bar's first item** (`modules/readers/
integration_health.py`, every 60 s). All ten integrations answered in 266 ms
on the host (measured); one that is down is bounded by its 5 s timeout and
two retries, so the probes run in PARALLEL and a read is bounded by the
slowest single probe, never the sum. `GET /settings/integrations/status`
serves the stored value (503 "not probed yet" with nothing stored); the
Settings strip reads it and no longer goes blank on a failed read; the
status bar (`static/js/nmas_status_bar.js`, in base.html on every page)
draws each integration's state with its message and probe time, its own age,
and STALE past the reader's 180 s promise (compact: `NMAS.stamp(..., {ownAge:
true})`); Needs attention makes a danger row per configured integration that
does not answer. Rule 11 held: the per-integration Test button
(`POST /settings/integrations/<name>/test`) stays a live check. The bar's
other two items (the deployed version and its CI result, and who you are)
are next, from sources already in-process.

**7.2 step 17 BUILT (2026-09-28): the status bar's version item, composed
from answers that each have ONE implementation** (the operator: two
implementations of "what is running" is the pattern this project keeps
removing). What is running is `routes.health._COMMIT`, what `/health` serves
`nmas-deploy`; whether it is the checkout's commit is job health's
running-version row (C129), read from the job-health reader's stored value;
its CI verdict is `nmas-deploy`'s own `ci_verdict()` (C170's walk included),
which the new ci-verdict reader (`modules/readers/ci_verdict.py`) LOADS from
the script and calls. `GET /health/version` composes the three and computes
none (counted in its test), and an AST test pins that no module defines a
second verdict. Every 15 min: GitHub allows 60 unauthenticated requests an
hour per address, shared with `nmas-deploy`, and a verdict costs one (up to
eleven walking back). A stored verdict for another commit is never this
commit's ("not judged yet"). Needs attention makes a row when the running
commit's CI failed (danger), was cancelled or is still going (warning), or
could not be asked (unknown).

**7.2 step 18 BUILT (2026-09-28): the status bar's third item, who you are.**
Read live for THIS request from `/identity/status`, the same verified answer
the gates act on (never a header): a person by email, a service by the name the
audit trail will use ("it can plan and queue, never confirm or reveal"), or
"not identified: you can look, not change" with the reason on hover. No reader:
it is about this request, in-process, a check rather than a report (rule 11).
The identity diagnostic stays reachable directly as well; a page now draws it.
The bar is complete: integration health, the deployed version and its CI
verdict, and who you are. C92's reader is 7.2's last step.

**7.2 step 19 BUILT (2026-09-28): C92's reachability reader, 7.2's last step.**
The online dot was one probe, and one miss drew "offline": 93% of 2,946
offline runs on the host ended at the next probe. `readers/reachability.py`
probes EVERY list's devices every 5 s and keeps, per device, the last result,
which probe answered (on the host ICMP is not permitted for the service user,
so the honest claim there is TCP 22), the consecutive-miss count, since when
the state has held, and the threshold it was judged against. "Answering" is
fewer misses than the threshold; one miss is "missed a probe".
- **One threshold function** (`miss_threshold()`, 3, from C92's measurement:
  195 runs at two misses, 99 at three), so P.8 makes it per network in one
  place.
- **It owns the answer every consumer already read**: `device_status_cache`
  IS its `STATUS`, updated key by key, so the dot, Refresh Hostnames,
  Auto-Create, the topology reads, the agent's context and the NetBox sync
  act on the thresholded answer with no edit. `ping_worker` is gone;
  `session_reaper` keeps the idle-session reaping it also did (C97).
- **Announcing on change needs a keepalive**, now part of rule 9: the value
  moves every cycle, so the reader announces when who answers CHANGES, and
  at least once a minute regardless. `register()` refuses an announce-on-
  change reader without one, because its silence would read as nothing
  having changed; the page's promise for such a reader is 2.5 keepalives.
- **Needs attention draws ONE row** naming every device not answering, each
  with its misses and since when: genuine outages came six to eight devices
  at once (the path from the NMAS), and nine rows would bury that.
- **Not built here:** the dot's own drawing of the claim and its age
  ("answering, checked 40 s ago"; "not answering for 3 probes, since
  18:04"; "not checked") is 7.3's, with the Device page. **7.2 is built.**

**7.3's retire screen has its model already: r5's retire commit** (the operator,
2026-09-28). `nmas-retire` recorded the reason, the actor, the tool and six
`Not-Done:` trailers: NetBox kept, Oxidized still polling, the startup config
frozen, the running config untouched, backups kept, a pooled session left to the
reaper. That list answers "what should retirement retain" empirically, so 7.3
does not design a policy: the screen draws exactly that list before the confirm
and again in the result, and 7.3 closes the gaps it names (C176's legacy file,
the heartbeat rules and scrape targets, C139's NetBox masking).

**7.3's retire screen BUILT (2026-09-28).** The Device page's Retire… asks for the
reason first (it is in the plan's hash), then previews `retire.plan()` through the
shared component: every step in order, the Not-Done list and the advisories, each
refusal as a gate by name (`RETIRE_GATES`, held equal to the plan's refusal keys), the
busy gate, and the confirm's effect saying what SURVIVES (intent and golden in history,
the credential only in the break-glass export). The result draws the Not-Done list
again. `POST /retire/preview` (a read, `not_device`) and `POST /retire/apply`
(`approve`, the list carried). **The break-glass basis differs by entry point, and each
says which** (the operator: "the screen trusts the export log, the CLI trusts the
record"): the page cannot open a record on a laptop, so it checks that the NEWEST
export of the list logged this device's current credential digest (C182), again at
apply, and states that the log records what was written and cannot show the file
still exists or that its passphrase is known. Building it found C187 (a re-approval
scheme 3 does not need, fixed), C186 (retire's failure paths) and C185 (no page reaches
a retired device's record).

**7.3's retire: r5's gaps closed or named (BUILT 2026-09-29, overnight; AWAITING A REAL
RETIREMENT ON THE HOST).** Modelled on r5's retire commit, whose `Not-Done:` list the
screen already drew. What that retirement left, and what retire does now:
- **C139, NetBox's stored credentials: masked, FIRST.** When NetBox writes are on and
  NMAS recorded writing the device's stored context, the first step masks it with the
  same implementation as `nmas-netbox-mask-context` (now `modules/netbox_context_mask.py`,
  both entry points), under the retire's own authority, and READS NetBox back. A failed
  mask stops the retirement with nothing else done. With writes off and a credential
  held, the retirement is REFUSED naming it (decided 2026-09-29, below); with a context
  NMAS never wrote, or one it could not check, the preview and the result say why it
  stays, with the command.
- **C176, the legacy file: deleted only when its content survives.** After the commit,
  the device's `golden_configs/` file is deleted when the golden panel's own survival
  check finds it in the repository (the migration's verbatim backup, or an equivalent
  committed golden), and the step says where. A file whose lines exist nowhere else is
  KEPT and named, with "keep a copy".
- **The heartbeat rule and the scrape targets: named, not written** (NMAS owns neither).
  The preview READS the generated rules file and says whether a rule names the device
  (it stays until the rules are regenerated on the host; the hourly check names it
  EXTRA meanwhile), and asks Prometheus which active targets still scrape its address,
  by job (hand-kept on the host, C168; P.7 generates them).
- **The result words every step**, and a test holds every step key the plan can make to
  its words.
**THE TWO OTHER STATES, DECIDED 2026-09-29 afternoon (the operator), and built:** a
context NMAS NEVER WROTE proceeds, named in Not-Done (NMAS cannot mask what it did not
write, and refusing would block the retirement with no path forward), and the exposure it
leaves is a Needs attention row from the new netbox-secrets reader, whose population is
what NetBox HOLDS, until someone removes it in NetBox; a context NMAS COULD NOT CHECK (the
record unreadable, or a configured NetBox that did not answer) REFUSES, naming why:
could not read is not nothing there. A NetBox that is not configured holds nothing and
proceeds (`tests/test_retire_gaps.py`, `tests/test_netbox_secrets_reader.py`).
**DECIDED 2026-09-29 (the operator): neither option as written.** Reads work with writes
off, so the preview checks whether the device's NetBox context holds an unmasked
credential. If it does, the retirement is REFUSED, naming it (the `netbox_mask` gate):
retiring past it is C139 recurring, since no import reaches the device afterwards. If
there is nothing to mask, it proceeds and says so. BUILT (`tests/test_retire_gaps.py`).
The two other states keep their Not-Done line and proceed: a context NMAS has no record of
writing (somebody's data, not NMAS's to mask), and one that could not be checked. **Open
for the operator**: whether the same refusal should apply to those two, since the same
reasoning (a credential left where no import reaches it) covers the first.
**Acceptance, awaiting the operator: a real retirement on the host.** Recommended on a
throwaway onboarded for the purpose (R1's shape), since which fleet device to retire is
itself a decision. r5's own leftovers are host actions, not code: its legacy file (the
golden panel names the `rm`), its NetBox context (`nmas-netbox-mask-context --device r5
--apply`), its heartbeat rule (regenerate) and its scrape targets (edit them).

**7.3 step 1 BUILT (2026-09-28): seed intent (C148), the path from onboarded to
deployable.** One operation where there were four routes with no screen:
`POST /templatize/seed/preview` parses each device's COMMITTED golden into the
intent document and draws it against what is committed now; the confirm is
bound to a hash of the document and the golden; the apply parses again,
refuses a device that moved, and makes ONE commit of exactly the seeded files
as the verified person (`Source: seed`, `Seeded-From:` per device). The Device
page's Seed intent opens it.
- **Only absent or bootstrap-only intent is seeded.** Over full intent a seed
  would replace what the device should be with what it is; that device is
  drawn, not selectable, and the apply checks again, because the hash cannot
  see intent committed between preview and apply.
- **What the template does not model is said, not blocked.** An unmodelled
  line round-trips verbatim and still blocks a deploy until acknowledged, so
  the preview names each one and the result is partial; the deploy's own
  per-device gate is where the block belongs.
- **The extract, staged, rendered and reviewed-commit routes are gone.**
  Reading them found that extraction took its device from the ACTIVE list.
- **Found building it: C175**, every other intent commit stages the whole
  `host_vars/` tree, so another device's uncommitted edit rides along. The
  seed stages its own files; the rest move with 7.3's intent operations.
- **Not done here: the acceptance**, C117's loop on a fresh throwaway
  (onboard, seed, deploy, break, roll back), which is the operator's run.

**THE PRESENTATION RULE FOR STAGE 7, decided 2026-09-28 (the operator): THE
SCREEN ANSWERS THE QUESTION THE PERSON CAME WITH, AND THE EVIDENCE FOR THE
ANSWER IS ONE LEVEL DOWN.** People want to know what needs their attention.
Everything working is the one line that still makes the positive claim;
something wrong is the rows, prominent, with what and what to do; a source
that is stale or did not answer IS something needing attention, so it is a
row, never a line in a provenance list. What was checked, and how (ages,
then absolute times, read costs and endpoints on hover), exists because we
needed to trust the page while building it: a debugging need, so it is
reachable and never first. **A NOTICE TELLS THE READER WHAT TO DO, OR IT DOES
NOT APPEAR** (the operator, 2026-09-28, after the legacy store's "can be retired"
stated a conclusion and stopped): a condition is drawn with its action, or with
a plain "nothing to do, because"; work the project will do later ("can be
removed", "eventually") is a plan item, never a notice on the page people come
to for what needs attention. C164 did this for Needs attention's rows; this is
the same rule for every other notice. Nothing is summarised away. The preview's operands
and the result's record already had this shape, which is why they read well.
Every screen after this inherits it. **Applied 2026-09-28 to the four built
panels**, each asked "does it lead with what's wrong or with what was
checked?":
- **Needs attention** (led with a provenance paragraph when rows existed, and
  a stale source was a red word in it): a stale source, or one that did not
  answer without making a row, is now a row of its own (not drawn twice when
  job health's reader row or drift's stale row covers it); the evidence is a
  table, one row per source with what it found and its value's age, behind
  "What was checked"; the debugger's part (endpoints, the reader's read time)
  is a `detail` field on hover; `since` is an age with the time on hover.
- **The status bar** (ten equal badges): one badge answers ("All 8
  integrations up") or the down ones are named first in red; the unconfigured
  are named; each integration's message and probe time are on hover.
- **Freshness** (the counts line and a standing explanation first): the
  unapproved and inconclusive devices first, or "No device holds a change
  nobody approved"; poll races, authorised divergences and the counts one
  level down; the explanation behind "About this check". The old clean
  sentence ("every device matches the approved config") was false beside a
  poll race, and its negative check would have passed vacuously on a
  reworded sentence: both moved together.
- **Drift** (the badge already answered first; the detail opened with the
  accounting): drifted, unreachable and not-checked devices first, then the
  accounting and the run.


### What does not exist yet (2026-09-28, the operator's request)

*(Superseded by section 11, 2026-10-02: C92's reader, seed intent, the retire screen and
most of 7.3's actions have been built since. Kept as the record of the order chosen then.)*

**MISSING** means the capability does not exist; that list is the plan.
**INCOMPLETE** means it works and could be better; that list is Stage 9, unless
something forces an item earlier.

**MISSING**
- **7.2**, which has one item left: C92's reachability reader. Per device, it
  keeps the last probe, its time and the consecutive-miss count, with the
  threshold taken from the host's measured misses. The version item (af10109)
  and who you are (1f49efb) are done.
- **P.8**, per-list settings (C173): decided, not built.
- **7.3 and its uninterfaced actions.**
  - **Seed intent (C148)** had NO path at all, not even a host command. The
    extract-and-commit route needs a verified person and has no GUI, so no
    onboarded device can be deployed to. It is the product's central loop.
    (BUILT 2026-09-28 as 7.3 step 1; its acceptance run remains.)
  - **Rotate, retire and persist** exist only as host commands:
    `nmas-rotate-credential`, `nmas-retire` and `nmas-persist-native`. (Retire has its
    screen since 2026-09-28; rotate and persist do not.)
  - The Device page itself does not exist: Overview with the reachability
    claim, Monitoring (7.3-a to e), Neighbours absorbing topology discovery,
    History, and the Actions (revert, retry and the four above).
- **P.7**: the generated alert rules and scrape targets. Only the heartbeat
  rules are generated today, and the scrape list is hand-kept (C168).
- **7.4 Fleet**:
  - the bounded list with selection;
  - batch deploy and bulk intent as screens;
  - onboarding as a list of address sources, with progress;
  - adopt, networks, and the inventory source.
- **7.5 Versions**: history by actor and source, drawn beside its known
  misstatements.
- **7.6 Source of truth**: templates with the approval badge, NetBox,
  credentials, freshness authorisations.
- **7.7 Settings**: the split, the file-only list, diagnostics, and C171's dead
  fields retired.
- **7.8 Removals**: the terminal, the Topology tab, the backup store after
  its prerequisite, and the legacy golden store with its header-scan
  fallback (retirable on the host since 2026-09-28).
- **7.9 Configure forms**, batch 1 (a parallel track).
- **Stage 8**: the agent has never executed a tool (27 recorded runs, zero
  calls). Every step is still to do: 8.1 models, 8.2 the tool library against
  today's program, 8.3 a real authority allowlist, 8.4 re-enabling it, 8.6 the
  triage (the Grafana reader it reads is built), 8.7 propose-only drift, 8.8 the
  second reading.

**INCOMPLETE (Stage 9 unless forced)**
- NetBox scoping, tenants against regions, and per-list NetBox containers (C174).
- Needs attention's 60 s poll, until C58's other senders announce: the
  post-commit push, the drift run, the NetBox refresh, another browser's
  action.
- The baseline source naming the newest baseline tag as the last decision
  known to be earned.
- C172 (`remote.json` read so that unreadable counts as absent) and the rest of
  the open register's C rows.
- The Stage 9 hardening rows, (L) and (M).

**7.3 is the most valuable remaining work, by a distance** (the operator's
instinct, agreed). The interface is the premise, and the loop the tool exists
for (onboard, seed, deploy) is broken at its middle step with no path at all.
One refinement of the order is recommended below.

**Recommended order:**
1. C92's reader, finishing 7.2.
2. Seed intent (C148), the first item of 7.3.
3. P.8.
4. The rest of 7.3.
5. P.7.
6. 7.4 onward.

**Why seed intent can go before P.8, without weakening P.8's placement.**
Seed intent reads no per-network setting: it extracts from the golden, reviews
and commits intent, in the list's own repository. What must wait for P.8 is the
Device page's monitoring (per-network Grafana, Loki and Prometheus), which is
exactly the screen that would otherwise show list A's Grafana beside list B's
device. C92's threshold is per network (the operator's own example), so it is
read through one function, and P.8 moves it without the reader changing.

## 9. Deferred, recorded rather than scoped

**Two of these are no longer deferred (2026-10-02), each kept below as the record:**
- **The fleet topology is P.11's Topology page**, its own destination under OBSERVE
  (decided 2026-09-30; the research is done, NSOT_PLAN P.11: NetworkX computes on the server,
  the app draws natively, from Prometheus's LLDP and routing series; NOT BUILT).
- **Mode B is BUILT and ACCEPTED**: 7.3 step 2d passed on the host on 2026-09-29 (r2's
  `load-interval 30` removed through the deploy path with a stated reason, read back gone,
  and the next Save All earned `baseline/20260929T060249Z`).

- **A fleet topology view** (as written before 2026-09-30). It EXISTS and WORKS today: the rcn-topology service's
  panel draws the fleet graph once `topology_service_url` is set (measured
  2026-09-28, `http://<lab-host>:8088`). It is removed in 7.8 because the fleet
  view is deferred, not because it failed (C126). If a fleet view returns, it
  reuses that service rather than building something new. If it returns, it caps the devices shown, and
  networks can be organised into groups, with the view showing one group at a
  time. A topology of 200 devices is a picture nobody reads; one site's is
  useful.
- **Configure batches 2 and later**, beyond what the schema models.
- **Mode B** (removals through intent). **What its absence costs, stated so it is not
  read as a missing convenience** (the operator, 2026-09-28): a hand change becomes
  permanent in the record until someone undoes it by hand. Deploys are merge-only and a
  restore is additive, so a line added on the device (r2's `load-interval 30`, C70's
  residue) leaves only by a person on the console, or is adopted into intent; until one of
  those, every capture departs from intent and no baseline can be earned (C184).
  **PLACED 2026-09-28 (the operator): 7.3 step 2, early, with r2's `load-interval 30` as
  its acceptance**, which the record now names as the exact blocker (`17239ae`'s
  `Baseline: denied:` trailer). C188's serial device reads go with it, because its preview
  reads devices the same way and would inherit the same 100 s ceiling.
  **Step 2a BUILT the same night: the computation** (`modules/nsot/removal.py`, nothing
  connects). `candidates()` offers residue leaves and whole stanzas the target lacks (one
  unit, children listed); `removal_program()` turns the SELECTED units into the exact
  program (verbatim `no`, a `no` line by its positive form, placed in its stanza) and
  refuses, with the reason, a construct IOS will not remove, a numbered ACL entry, the
  management path, an account and a named object something still uses (naming the
  user). On the real fleet: r2's program is `interface GigabitEthernet2` /
  ` no load-interval 30` / `exit`; r3's `NO-PRIVATE` prefix-list is refused naming its BGP
  neighbour.
  **And only where MEASURED** (the operator, 2026-09-28: `no <exact line>` can do more
  than undo the line, `no access-list 10 <entry>` deleting the whole list; "ask the
  platform rather than reason about it, because this is where being wrong destroys
  config"). A line is removed only if it matches a shape in `removal.SHAPES` that
  `scripts/nmas-removal-probe` measured on the device's PLATFORM removing exactly that
  line (`removal_measured.json`, absent until the first run, so today NOTHING is
  removable, r2 included). Every other line is refused as unmeasured, naming the probe.
  The shapes include the ones SUSPECTED of being broader, so the record shows why they
  are refused: numbered ACL entries; a route-map sequence; a community with an ACL or a
  view (the operator's list); a prefix-list entry and a named-ACL entry (entries in a
  list); a BGP neighbour's `remote-as` (suspected of removing the whole neighbour); and
  `logging buffered` (suspected of turning logging OFF rather than restoring the
  default). Refused outright, without a probe: banners and certificate bodies (lines the
  model cannot represent). Left unmeasured, so refused: `switchport trunk allowed vlan
  add` continuation lines, `ip nat` (it prompts when translations exist), and
  `ipv6 unicast-routing` / `ip routing` (they take every routing protocol with them).
  The probe adds a scratch instance of each shape (names `NMASPROBE`, RFC 5737
  addresses, Loopback199), sends what Mode B would send, compares the read-backs
  (`exact`, `broader`, `different`, `incomplete`, `refused`), takes the scratch away,
  puts back anything removed, and requires the device EQUIVALENT to its state before,
  or stops with that as its first line. RUNNING config only, never saved. **Its run is
  the operator's**: one device per platform (cisco_iosxe, cisco_ios). The BGP shape
  has no scratch (IOS allows one process), so it adds a neighbour to the device's LIVE
  process and runs only with `--allow-live-bgp` (C192). A shape the run could not ask
  about is `unmeasured` and never enters the platform record.
  **First record, 2026-09-29 (the operator's run on s4, cisco_ios):** four shapes exact
  (load-interval, description, snmp-server community with three examples including an ACL
  and a view, logging host). `logging buffered` was the prediction, confirmed: removing
  `logging buffered 16001` left `no logging buffered`, buffered logging OFF instead of at
  its default. It is its own class, `overrides_default` (anything whose absence means a
  default rather than nothing), refused by name citing the run, and retired from the
  probe so no run dirties a device to learn it again. The run's self-check stopped it
  there (NOT RESTORED): its repair took the residue calculation, which paired the
  leftover with s4's `no logging console` (C193), and now takes a plain difference.
  Still unmeasured on IOS: the numbered ACL entry and route-map sequence (the two most
  likely to destroy), the applet, the prefix-list and named-ACL entries.
  **IOS FULLY MEASURED (the operator's second run on s4, 2026-09-29):** 8 exact
  (load-interval, description, snmp-server community, logging host, route-map sequence,
  event-manager applet, prefix-list entry, named-ACL entry), 1 broader (the numbered ACL
  entry: removing `access-list 97 permit 192.0.2.1` also removed `... permit 192.0.2.2`, the
  case where an unmeasured Mode B would have destroyed config while reporting success), 1
  `overrides_default` (logging buffered), and BGP not applicable on a switch. Of the three
  "entry in a list" shapes, numbered ACLs are destructive and named ACLs and prefix-lists
  are exact: the obvious generalisation ("list entries are dangerous") would have refused
  two safe shapes. The run needed no repair past its teardowns and ended equivalent, and
  s4's Capture as golden confirmed it independently (matches its golden and its intent).
  **cisco_iosxe (the operator's run on r3, 2026-09-29): 7 exact**, including
  `interface.load-interval`, r2's residue shape, so **the acceptance is unlocked in the
  record**: r2's `interface GigabitEthernet2` / ` no load-interval 30` / `exit` passes
  every gate but the pipeline, which is 2b. BGP unmeasured by choice. Both ACL shapes
  "did not land", and both were the probe's own defects (C195), now fixed and to be
  re-run with the new `numbered-acl.list-entry` shape. r3 afterwards (the operator's
  control): the r5 session unchanged, no scratch anywhere, NAT-PRIVATE intact.
  **cisco_iosxe after the ACL re-run (r3, 2026-09-29): 9 exact** (load-interval,
  description, community with three examples, logging host, applet, prefix-list entry,
  route-map sequence, named-ACL entry, numbered-ACL LIST entry), BGP unmeasured by
  choice. Both numbered examples were filed under `numbered-acl.list-entry`, one sent as
  the top-level form and shown as the list, the `sent_as`/`shown_as` pair making the
  filing checkable. Every restore block reads teardown only, `extras_sent` and `readded`
  empty: this run PROVES the repair was not needed (C194's claim, now made). **The open
  question (C196):** one operation, two forms, two answers. IOS's top-level form removed
  the whole list, IOS-XE's list form removed one entry, and Mode B sends the displayed
  form, so the IOS refusal rests on one form's measurement. Left refused, since nothing
  needs it and the other form breaks verbatim.
  **Step 2b BUILT (2026-09-29): removals through the deploy path.** A plan takes
  `remove: {device: [{chain, line}]}`; ONE function (`removal.with_removals`, called as
  `_program` by plan, apply and `_deploy_one`) appends the selected removals after the
  additions, so the three computations cannot disagree. Every removal needs a stated
  reason, through the dangerous-line mechanism (`extra`), checked at plan and apply AND
  on the path that connects; the reason is in the confirm hash, and an apply that drops
  the selection computes another hash and is refused. A refused selection blocks the
  device, naming it. Merge-only applies to the additions only; the removal tail is held
  to its own provenance. The pipeline carries `ctx.removals`: verify reads back that
  each removed line is GONE (still there, or an unreadable read-back, fails verify and
  rolls back); rollback splits the pushed program (refusing when its tail is not its
  removals), undoes the additions as before and the removals by re-adding the device's
  own lines from the snapshot (`restore_program`), never by `rollback_commands`, which
  read `no X` as never applied and reported restored with X gone; the read-back after
  the undo counts a still-missing line as `incomplete`; the rolled-back block records
  the additions only. The preview draws each removal line with its own authorise box
  and reason, excludes selected lines from "will NOT be removed", and stops saying
  "merge-only, never removed" when a removal is selected.
  **Found building it, for 2c:** the plan comes back MASKED, so the browser can never
  echo a secret-position line's real text to select it (C139's old community could not
  be selected from a screen). 2c selects removals by a server-computed ID of stanza and
  line, never by the line's text. **Not yet:** the restore path's residue (the fourth
  case) is not wired; a removal that failed and rolled back is not blocked from being
  selected again (each selection is a fresh decision with a reason, which is the
  argument for leaving it); 2c the screen; 2d r2 on the host.
  **Step 2c BUILT (2026-09-29): the screen.** The Deploy plan lists every line the
  device has and intent lacks with a TICK BOX, selected BY ID (`removal.unit_id`: the
  stanza and line, hashed), because the plan is masked and a secret-position line's
  text could never be sent back. The ids are resolved against the capture (an unknown
  one refused by name, never guessed), folded into the confirm hash (only when there
  are any, so every other hash is unchanged) and recorded in the receipt. A box that
  cannot be ticked says why beside it. A ticked line joins the program, where its
  reason box is, and the wizard's apply sends the ids the RENDERED plan's hash covers
  (executed in duktape). The history beside a reason box says when that change was
  last ROLLED BACK and why: unblocked, but visible (the operator). **Found building
  it:** a stanza intent lacks is offered as one unit, so for a PHYSICAL interface
  (whose stanza cannot be removed) every line under it was unremovable; its header is
  now offered refused, saying why, and each line under it on its own. The capture
  preview's blocker now points the device-side resolution at the Deploy plan's tick,
  saying it is refused where the platform's removal is not measured. **Next: 2d**, r2
  on the host: tick ` load-interval 30` in r2's Deploy plan, give the reason, confirm;
  verify reads it gone; the next Save All earns the baseline.
  **Step 2d PASSED ON THE HOST (the operator, 2026-09-29): MODE B'S ACCEPTANCE.** r2's
  Deploy plan, ` load-interval 30` under GigabitEthernet2 ticked for removal, reason
  "Removing unnecessary configuration"; deployed 05:53:33 UTC, the receipt carrying the
  removal by id (`2d7f42a57dbd`), the reason, the three-line program matching its
  confirmed hash, and verify ok (neighbours and routes unchanged). Save All afterwards:
  all nine devices match their committed intent, r2's capture hash 1f85ec28 to
  35980cc3, and **baseline/20260929T060249Z EARNED** (nine devices, credentials
  current): the first earned baseline with a recorded decision. The chain from C70 is
  closed (docs/NSOT_WRITEUP_NOTES.md, "The line the tool could not remove").
  **Two things from the run, both fixed the same day:** the removal asked for ONE
  decision TWICE (the line's tick, then a second box in the program, because removals
  reused the dangerous-line authorisation wholesale): a removal's line now has only its
  reason field, and the reason authorises it, while a dangerous line keeps its box; and
  the receipt did not keep verify's removal read-back (it copies some of verify's
  fields), so it now records `removals_checked` and the result draws "removals read back
  gone". Save All's speed (C188, several minutes) is next.
  **C188, Save All's speed, built 2026-09-29 in two steps.** Measured before, from the
  host's log: the preview read nine devices in series (101 s of reads, about 107 s to
  its answer, past Cloudflare's 100 s), and the apply read them again (102 s, about
  113 s); s3 the slowest (23 to 24 s). Step 1: both read every device at once, timed,
  the slowest named on the screen. Step 2: the preview is a JOB; the POST answers at
  once, the in-flight panel shows the reads, and the job announces `capture_preview`
  when it finishes, so no request waits on a device. The apply stays a request (about
  the slowest device's read after step 1). **Accepted by the after-measurement**: the
  operator's next Save All, read from the same log lines, per device and in total.
  **Measured on the host, 2026-09-29 (the operator): C188 CLOSED.** Preview 101 s to
  40.9 s, apply 102 s to 13.7 s, s3 the slowest both times; `baseline/20260929T063600Z`
  earned 30 minutes after the first. The apply three times faster than the preview for
  the same reads is not explained (C198): each read is now split into connect and
  `show running-config`, logged and drawn, and the next Save All says where the time is.
  **Mode B's fourth case, a restore's residue: a DECISION, recorded overnight 2026-09-29
  (the operator's queue item 8: "if it fits cleanly; if it needs a design decision, write
  the options").** The server side fits: `routes/golden.restore_preview` and
  `routes/deploy.run_targets` would call the same `_program()`, `removable()` and
  fingerprint-with-ids the deploy plan does, and `_deploy_one` already takes `remove`.
  The CLIENT does not fit: the restore authorises lines in a SEPARATE modal before the
  program is shown (`_authoriseDangerous`, then `_confirmRestorePreview`), where the
  deploy wizard ticks a residue line in the preview and re-plans in place. And it
  changes what the Baselines panel's button, named "Re-apply this baseline" because a
  restore is ADDITIVE, means.
  - **(a) Removals inside the restore.** The residue rows get the tick and the reason in
    place, the restore modal re-plans with `remove`, and the hash, receipt and verify
    carry it as they do for a deploy. A restore could then EARN its baseline by removing
    the residue that denies it today. Cost: the restore client's two-modal flow is
    restructured to re-plan from inside the preview, and the button's name and the
    confirm's words change from "re-apply" to "re-apply, and remove what you ticked".
  - **(b) Restore stays additive; removal keeps ONE home, the Deploy plan** (section
    6a). A restore commits the ref's intent with the device ("device and intent as one
    unit"), so after it the Deploy plan's residue for that device is the lines the ref
    does not hold, and Mode B removes them there, measured and authorised as now. Cost:
    two operations where (a) is one, and the restore's residue item names the next step
    ("remove these through the Deploy plan"). EXPECTED, not measured: that the Deploy
    plan's residue after a restore equals the restore's (a template render of the ref's
    intent against the ref's golden, 100% round-trip on the fleet; unrenderable blocks
    such as banners are excluded from both).
  **Recommendation: (b)**, with the one-line pointer in the restore's residue item. A
  removal already has one measured, accepted home, and (a) would give it a second client
  flow with a different authorisation step: the minimalism rule's "two ways to do one
  thing means one is wrong". Nothing is built for either until decided.
  **DECIDED 2026-09-29 (the operator): (b).** Restore stays additive; removal lives in
  the Deploy plan, one home per action. BUILT: the restore preview's residue item points
  there ("Removal has ONE home, the Deploy plan (Mode B): <device>'s Deploy plan offers
  each line the device holds and its committed intent lacks, for removal with a stated
  reason. After this re-apply, that intent is the ref's wherever the ref carries one"),
  worded as what each mechanism does, since their equality is still EXPECTED, not
  measured (`tests/test_p3_restore_is_guarded.py`).
  **The gap Mode B has to get right** (the operator): every destructive or surprising
  result so far (the numbered ACL broader on IOS, `logging buffered` overriding its
  default, the ACLs unrecognised on IOS-XE) came from the gap between WHAT IS SENT and
  WHAT THE DEVICE STORES. So the probe measures the removal of the line as the device
  DISPLAYS it (the form the golden holds and Mode B builds from), files it under the
  shape that displayed line is, and records what the setup added. Which other forms
  IOS-XE normalises (sequence numbers, the list form, legacy `logging <addr>`, masks,
  wildcards) is answered by that evidence, per shape, rather than guessed in advance.
  **The repair for an `overrides_default` line, proven on s4 (the operator, 2026-09-29):
  THE DEFAULT IS DISCOVERABLE FROM A SIBLING ON THE SAME IMAGE.** s3 runs the same vIOS
  image and its committed golden has no `logging buffered` line, so it is at the default;
  its `show logging` gave `level debugging, Log Buffer (8192 bytes)`. `logging buffered
  8192 debugging` sent to s4, then `show running-config | include logging buffered`
  printed nothing (IOS hides a setting at its default), `show logging` matched s3, and the
  device logged `%SYS-5-LOG_CONFIG_CHANGE`. No reload. Setting the value explicitly is
  preferred to `default <command>` because the value sent can be verified. What the tool
  holds and what it does not: the sibling's GOLDEN says the sibling is at the default (no
  line); the VALUE came from a live read of the sibling. A built repair would need both.
  Next: 2b the pipeline (confirm hash over removals, per-line reasons, rollback
  that re-adds verbatim, read-back that each line is gone), 2c the preview, 2d r2 on the
  host.
  **Costed 2026-09-28** (the operator asked what it costs and whether
  it belongs in Stage 7: "the interface manages the network" is false while the only
  way to remove a line is a console). Four places wait on it: r2's `load-interval 30`
  (a leaf under an interface), C12's heartbeat block (a stanza plus logging leaves), C139's
  old community (a global leaf in a secret position) and a restore's residue (anything).
  - **What exists.** Residue is computed per section already (`classify_diff`,
    `residue_in_context`). The tool already generates bounded `no` commands inside their
    header chains, with a created stanza removed by one negation (`rollback_commands`,
    `created_containers`, `assert_rollback_provenance`). The preview component, the
    confirm hash, the device lock, the pipeline's snapshot, verify and receipts, and the
    authorisation-with-a-reason mechanism all carry over.
  - **Onboarding's verbatim removal is the principle, not most of the work.** It is one
    rule (`no` plus the device's own line, never a rebuilt one) for one construct at the
    top level, sent on a session outside the pipeline: no snapshot, no confirm hash, no
    read-back that the line is gone, no rollback.
  - **What is new.** (1) The negation per line, measured on real devices, not assumed:
    `no <line>` for most; a `no` line inverts to its positive form; some things cannot be
    removed at all (a physical interface is `default interface`; `hostname`, a `line`
    stanza). (2) Refusal classes: the management path (the repair path travels over the
    thing being changed), the tool's own account, and a named object something else
    references (an ACL, a route-map, a VRF, whose removal strips its interfaces'
    addresses). A conservative first version refuses any name used elsewhere in the
    running config. (3) Rollback of a removal re-adds the verbatim lines from the
    pre-change snapshot, under its own provenance rule. (4) Verify reads back that each
    removed line is gone. (5) The preview selects removals line by line, each with a
    stated reason, never "converge to intent" automatically.
  - **Estimate.** About three days to build (the computation and its safety classes, a day
    and a half; the pipeline, rollback and read-back, a day; the preview, half a day),
    then the first real run's findings. The branch site, the first deploy, found ten
    defects on one path, and 7.1 tripled its estimate. So plan on about a week, and
    treat the three days as the part that goes to plan. Its acceptance is r2: the tool
    removes `load-interval 30`, verify reads it gone, and the next Save All earns the
    baseline.
- **The agent's triage-and-propose UI** (Stage 8): its reports attach to
  Needs attention rows, and its proposals arrive as ordinary plans in the
  preview-confirm component. Stage 7 leaves the place for them.
  **How triage is triggered is decided** (NSOT_PLAN.md 8.6, 2026-09-27):
  Grafana writes alert state and NMAS reads it; there is no inbound route.
  That puts three constraints on 7.2, which are cheap now and expensive
  later:
  - the Grafana source is a reader job keeping each alert INSTANCE
    (fingerprint, `startsAt`, `window_seconds`), not a boolean "firing";
  - rows are per incident, with a member list;
  - each row has an empty slot for a triage.

## 10. Stage 7 acceptance

1. **Reachability:** every route is reachable from a page, non-GUI by a
   named, verified consumer, or allowlisted. The allowlist is **empty** at
   the end except for deliberate non-GUI routes.
2. **No curl-only task remains** (section 6's table). Each has an entry point,
   and a test asserts it is present in the rendered page.
3. **The nine concepts:** the harness passes with all nine, and its control
   fails.
4. **Payloads drawn:** the payload-to-render check passes with its floors and
   anchors, and its controls fail.
5. **Invalidation:** every mutating route declares what it invalidates, both
   directions hold with floors, and on the HOST the three measured cases
   update without a reload (7.0).
6. **One pattern:** every task listed in section 2.1 goes through the one
   preview-then-confirm component, and a test asserts no second confirm
   implementation exists.
7. **Needs attention shows every source in section 1a.** Each source's
   unreadable state is a row, and the empty page names what it checked.
8. **Grafana, natively** (restated 2026-10-02; was "the device page embeds that device's
   panels and logs, or names the prerequisite that failed. A blank frame fails", superseded
   by the native decision of 2026-09-30): the device page draws EVERY panel of the
   configured device dashboard that selects the device, from the dashboard's own JSON, each
   at its own `gridPos`, and the device's logs from Loki; the Monitoring page draws the fleet
   dashboard the same way. Each state is said in words, never a blank area: no dashboard
   set, a UID Grafana says is gone, no device variable, a panel type the app does not draw
   (its place kept, "Grafana draws this"), a range past the backend's limit, a panel that
   does not apply to this device (folded, with why), Grafana or Loki not configured or not
   answering. A panel added in Grafana appears with no code change.
9. **CI has no destination:** each CI state appears beside its trigger
   (NSOT_CI.md §5), and there is no CI tab.
10. **No subsystem tab:** the top-level navigation is the hybrid SIDEBAR
    (section 1, NSOT_GUI_BRIEF.md section 2), and a test pins it. In order:
    Needs attention, Devices, History, then the heading Source of truth over
    Templates, NetBox and Credentials, with Help and Settings at the bottom.
    Between History and Source of truth, the OBSERVE heading over Monitoring, Logs, DHCP
    and Topology (signed off 2026-09-30; Topology added by P.11 the same day). **The
    brief's thirty-seven findability questions are walked on the BUILT screens**
    (the first-click test on the mockups was skipped by the operator,
    2026-09-29), and a path longer than the brief's count is a finding.
11. **Scale:** nothing renders the whole inventory, and `test_scale.py` pins
    the page cost at 900 devices.
12. **Behaviour:** Stage 7 moves controls, adds entry points and performs the
    audit's removals. Any other change to what a control DOES belongs to
    another stage.

13. **Authorization-aware controls:** every gated control's state is read
    from `may`. A test asserts that no gated control is hidden or enabled by a
    client-side role check, and that a refused control renders its reason.
    Its control fails when a button is drawn without consulting `may`
    ([NSOT_AUTHORIZATION.md](NSOT_AUTHORIZATION.md) section 7).
14. **Every sub-task has its writeup entry** (the operator, 2026-09-29):
    [NSOT_WRITEUP.md](NSOT_WRITEUP.md) holds one entry per sub-task (what it
    was, how it was built, its findings by ID, how each was resolved, its
    numbers and where it left the product), written in the turn it closed.
    A stage is not closed while an entry is missing or says "to be written".
    **Closing also checks the stage's forecast against its actuals**, in the
    entry (the operator, 2026-09-29): 7.2's was never checked, and the next
    forecast would have been built on an unexamined one. Forecast from a
    finished stage of the same KIND (the 7.1 multiplier was about seven times
    too high for Mode B).
15. **The manual stays true** (the operator, 2026-09-29): every sidebar
    destination has a manual section, and each screen links to its own
    section. A test fails, with a floor, on a destination with no section. A
    stage is not closed until the screens it changed are documented, the same
    rule as the writeup entry.
16. **No duplicated function:** the brief's duplicate inventory (section 1g)
    is empty by the stage's close. Every entry keeps the home the brief named,
    and section 6a's check enforces the list.

## 11. Status, 2026-10-02 (rows updated 2026-10-03)

**Since 2026-10-02:** P.15's open fixes are all done (R2, R5, R13, R19, R20, R28). The device
page's four signed actions are built: capture, persist, rotate, and deploy with Mode B. Coverage
has its not-reporting reader and its grid and selection; its third step, the combined deploy, is
next. History became one timeline (C369, board D). Credentials carries the break-glass record
(board 7), which passed its first real run end to end on 2026-10-03.
**SIGNED OFF 2026-10-03 (the operator), boards 8 to 12:** seed, restore, revert and retry, and
retire on the v2 device page, with the Actions menu every action runs from. The changes asked
are redrawn:
- Seed shows device-owned lines as such, never blocking (C397).
- Retire's result says the generated watchers (scrape targets, heartbeat rules) are dropped at
  their next regeneration, and names the rest with how each is removed.
The two flagged choices are agreed:
- A stated reason replaces the typed confirmation for an account a restore adds back.
- A retired device's address shows its retired record, closing C185.
**Build order (the operator):** restore (as a job, carrying its list: C396), revert and retry,
seed, retire, then the combined deploy's arrival watch. Restore built 2026-10-03 (4c336be);
revert and retry built 2026-10-03, offered only while a block stands (d354cc2); seed built
2026-10-03, the device's own lines named and never intent (C397 closed).

Read from the code, the register, docs/CUTOVER.md (265 routes: 43 the redesign's; of the
legacy families, 5 BUILT, 32 PLANNED, 17 REMOVE, 3 STAYS, none UNDECIDED) and the
writeup. "Accepted" means a run on the host by the operator, with its date.

### The steps

| Step | State | Detail |
|---|---|---|
| 7.0 checks | **PARTLY** | Built 2026-09-27; the four checks run in every suite. Its host check (acceptance 5) is half done: the drift card and the Remote card were observed; the device list redrawing after Verify was never measured (it needs an onboarding: run A1 in section 12) |
| 7.1 an operation, whole | **DONE**, accepted on the host 2026-09-28 | Met on the suite 2026-09-28; C70's restore (2026-09-27), R1 onboarding and R2a/R2b NetBox (2026-09-28) run by the operator. Bulk intent's preview deferred to 7.4 by decision |
| 7.2 Needs attention, readers, live data | **DONE**, in use on the host since 2026-09-28 | 19 steps; no separate acceptance run was defined, and the page has been the operator's landing since. Since: every row has an action (C323) and says how it clears (C344), restarts, adjacencies, NetBox secrets, lab startup, host steps and the pushed release as sources |
| 7.D the redesign's design | **DONE** for the three first screens and the services | Research and brief signed off 2026-09-29, the mockups reviewed 2026-09-29, the services mockups and the stack (option A) 2026-09-30, the spike approved 2026-09-30. Owed per screen still to build: the Coverage redraw, the C342 drift panel and the monitoring templates mockups |
| 7.3 the Device page | **PARTLY** | Accepted on the host: Mode B (2d, 2026-09-29), C188's concurrent capture (measured 2026-09-29), persist and rotate (2026-09-29). Built, awaiting a real run: seed's C117 loop, retire, revert and retry, the browser break-glass export, C178's BGP hold watch (section 12). Built backend, no screen: adopt (steps 1 and 2). v2 page built (2026-09-30 to 10-01): 7 of 8 tabs. **Left:** the actions moved onto the v2 page (today they open the legacy page), Ask the device (the allowlisted command box), reload (P.14), adopt's screen |
| 7.4 Devices (Fleet) | **PARTLY** | Built 2026-10-01: the v2 list (search, filters, a fixed number of git reads, last measurement, pending rows), and the batch Apply as a job in a rollout order (P.9 d2). **Left:** the selection's own batch deploy, Save All and bulk intent screens on v2 (it opens today's deploy), onboarding on v2 with N address sources, adopt, networks |
| 7.5 History (Versions) | **PARTLY** | Built 2026-10-02 (commits, baselines with re-apply, authorisations, the remote); one timeline across every device and the fleet's own records, the device tab the same reader (C369, 2026-10-03). **Left:** the "N of M commits carry a verified identity" line, C83's subjects, the remote's connect (curl-only) |
| 7.6 Source of truth | **PARTLY** on v2 | Credentials: the break-glass record (board 7, built and accepted on the host 2026-10-03); its credential list and expiries are still today's. Templates and NetBox open today's pages; template revoke and bindings, freshness authorise and credential profiles still have no GUI |
| 7.7 Settings | **NOT STARTED** on v2 | The sidebar item opens today's page |
| OBSERVE: Logs, DHCP, Topology | **NOT STARTED** | Logs and DHCP open today's pages; Topology (P.11) is not in the sidebar. They follow P.8 (per-network services) |
| 7.8 removals | **NOT STARTED** | 17 REMOVE families in CUTOVER, the terminal and today's two pages among them; last by rule |
| 7.9 Configure forms | **NOT STARTED** | A parallel track |
| 7.10 | **NOT STARTED** | A3 at scale, the 900-device screens, the inventory-source switch |

### The plan items scheduled within Stage 7

| Item | State | Detail |
|---|---|---|
| P.7 alert rules generated | **PARTLY** | Built: the heartbeat generator with its 7-day lookback and its re-measure action (C300), the telemetry rules (C304), the generated scrape targets (C232). **Left:** the other hand-built rules generated and tested, the hand-built folder retired rule by rule |
| P.8 per-network settings | **NOT STARTED** (decided 2026-09-28) | Gates the OBSERVE screens and per-network Grafana |
| P.9 the monitoring profile | **BUILT**, (a) to (d4) | **Awaiting:** staged run 9 (changing a running IP SLA probe), C262 and C269 (the operator's `cdp run` steps) |
| P.11 Topology | **NOT STARTED** (research done 2026-09-30) | After P.8 |
| P.12 feature templates | **PARTLY** | The profile is the first instance; the monitoring templates' design (replacing the Heartbeat and IP SLA pages) is owed a mockup |
| P.14 reload, gated | **NOT STARTED** | One of 7.3's actions |
| P.15 several people at once | **PARTLY** | The audit is done; R1, R2, R4, R5, R13, R19, R20, R24, R25 and R28 fixed 2026-10-02; the rest before 9.S |
| C38 Neighbours, C92 reachability | **DONE** | Built 2026-10-01 and 2026-09-28; in use |

### The 16 acceptance criteria

| # | State | What would meet it |
|---|---|---|
| 1 Reachability | partly | The allowlist is at 49; homing the PLANNED rows and 7.8's removals empty it to the deliberate non-GUI routes |
| 2 No curl-only task | partly | Screens for the 8 NO_GUI actions (template revoke and bindings, bulk intent apply, freshness authorise, remote adopt, and the rest in `tests/test_results_are_drawn.py`) |
| 3 Nine concepts | partly | 4 live, 5 pending (`tests/test_concepts_are_taught.py`): each lands with its screen (7.4 to 7.6) |
| 4 Payloads drawn | partly | The check passes with its floors; its UNDRAWN list (ceiling 110) shrinks to its exemptions as screens draw their fields |
| 5 Invalidation | partly | Maps complete, live contract built; the host case of the device list after Verify (run A1) |
| 6 One pattern | partly | Bulk intent through the component (7.4); the legacy confirm paths go with 7.8 |
| 7 Needs attention, every source | met, except Stage 8 | The agent's triage reports are Stage 8's, by design |
| 8 Grafana, natively | met | Restated 2026-10-02 (section 10); the device and fleet dashboards and the logs are drawn and every state said. Its one gap is P.8's per-network dashboards |
| 9 CI has no destination | met | The CI verdict is on About, the Update page and a Needs attention row; no CI tab |
| 10 The sidebar | partly | The v2 sidebar matches, but Topology is absent and five items open today's pages; then the 37 findability questions walked on the built screens |
| 11 Scale | partly | v2 Devices does fixed reads at any size (tested at 60); the 900-device selection screens are 7.10's |
| 12 Behaviour | holding | Checked at close: no control changed what it does outside its stage |
| 13 Controls drawn from `may` | not met | A test that no gated control is drawn without `may`, and every v2 action drawn from it (NSOT_AUTHORIZATION section 7) |
| 14 A writeup entry per sub-task | partly | Entries for 7.3's remaining parts, 7.D's screens (Devices, History, Monitoring, Coverage, Update, the manual) and P.9 (d) |
| 15 The manual stays true | met so far | Holds for every built v2 screen (`tests/test_manual.py`, the click test); each new screen adds its page |
| 16 No duplicated function | partly | Today's pages duplicate the v2 screens until 7.8; the brief's inventory empties then |

### The order for the rest, and why

1. **The P.15 fixes still open (R2, R5, R13, R19, R20, R28).** Small, no screen, and every
   later write path builds on them.
2. **The v2 device page's actions**, starting with the ones accepted on the host (capture,
   persist, rotate, deploy with Mode B), then seed, restore, revert and retry, retire. They
   are whole on the server already, so this is porting with the shared component, and it
   takes the operator off the legacy page for per-device work. Reload (P.14) and Ask the
   device follow, new operations of the same kind. **Decided 2026-10-02 (the operator):**
   per-device receipts first (R5's open half; DONE 2026-10-02, tests/test_pending_receipts.py),
   then capture (DONE 2026-10-02 on the device page, tests/test_device_capture_v2.py; Save
   All waits for 7.4), persist (DONE 2026-10-03, tests/test_device_persist_v2.py), rotate
   (DONE 2026-10-03, tests/test_device_rotate_v2.py) and
   deploy with Mode B (the actions' mockup signed off
   2026-10-02).
   **Then Coverage, redrawn** (artboards A and A2 signed off 2026-10-02): the not-reporting
   reader first, starting with its read-only measurement on the host; then the grid and
   selection; then the combined deploy (one program per device, verified and rolled back as
   one). The Heartbeat and IP SLA pages retire when Coverage and the monitoring templates
   replace them (docs/CUTOVER.md).
   **The combined deploy, from artboard A2 (2026-10-03). BUILT: its scope, its page and
   Coverage's button; the stop at the first failure and the read-back of every line
   (tests/test_coverage_deploy.py). NEXT: arrivals, once decided.**
   - **Its scope** is the profile's lines plus the device's own IP SLA probes
     (`templates`), sending only what the device lacks. So a configured template is never in
     the program, and a not-reporting one is named beside it with its Diagnose link, as
     drawn.
   - **The batch stops at the first device that fails, of any kind.** Today's breaker stops
     after 2 verify failures and counts nothing else (C10).
   - **Every line of the program is read back,** quick or full, and a line that did not land
     rolls the device's program back as one.
   - **DECIDED (the operator, 2026-10-03): arrival is WATCHED for 15 minutes after the
     batch, never blocking and never rolling back.** The result reports each device's first
     scrape, line and heartbeat as it arrives. Anything still missing at 15 minutes says so
     and points to its diagnosis. The operator's next real Coverage deploy measures the
     real arrival times, and the 15 minutes is revisited against them. Built after the
     device actions below.
   - **The question as it was put:** A2 draws it as part of verify. Two things decide what it can be:
     - The heartbeat fires every 5 minutes, and the reader looks once a minute.
     - SNMP's scrape target exists only after the batch's golden commit regenerates the
       targets, which is after the last device.
     Waiting per device would add at least 5 to 6 minutes to each device and could never
     see SNMP.
     **Recommendation:** arrival is WATCHED after the batch, never a gate and never a
     rollback. The job watches each device's new templates for up to 15 minutes (about 2.5x
     the 6-minute worst case, a heartbeat and a reader cycle) and draws each cell as
     "arrived at hh:mm" or "not yet". A cell still waiting when the watch ends becomes
     Coverage's not-reporting state, with its diagnosis. The configuration that read back
     correctly stays; a missing scrape is not a reason to remove it.
     **Alternatively,** arrival gates each device and rolls back on a timeout. That is about
     6 minutes a device, and SNMP is excluded from the gate.
3. **7.4's selection** (batch deploy, Save All, bulk intent) and onboarding on v2, then adopt's
   screen and its real run.
4. **P.8**, because Logs, DHCP, Topology and per-network Grafana all read per-network
   settings; then **OBSERVE** (Logs, DHCP, P.11 Topology) and the monitoring templates.
5. **7.6 and 7.7** (Source of truth, Settings), which close the no-GUI list.
6. **7.5's remainder**, then **7.8's removals**, last by rule; 7.9 in parallel.

The real runs in section 12 run alongside, at the operator's lab sessions; none blocks the
next build step except adopt's (after its screen).

### The forecast, from finished stages of the same kind

Two kinds of work remain, each forecast from the finished stage it resembles:
- **Operations made whole on a screen** (the device page's actions, the selection, onboarding,
  adopt, reload, the Source of truth writers, Settings): the same kind as **7.1** (69 commits
  over 20 h 41 min, about one finding per commit, about 11 commits per operation retrofitted).
  About 18 such operations remain; most are already whole on the server, so between half and
  all of 7.1's cost per operation: **100 to 200 commits, 30 to 60 h, a finding per commit.**
- **Read-only screens over stored sources** (Logs, DHCP, Topology, the NetBox, Templates and
  Credentials views): the same kind as **7.2** (37 commits in about 4 h, about one finding per
  two commits). About 8 screens at 4 to 8 commits each: **30 to 60 commits, 8 to 16 h.**
- **7.8's removals**: no finished stage of this kind; P.4's Jenkins cut (removal with a
  checker) is the nearest, at about 2 commits per family: **about 35 commits** for 17.
- **P.8**: no finished stage of its kind (a settings migration across every reader); the
  settings work of 3.2 is the nearest, and too small to scale from. Stated as unknown.

**Total: about 165 to 295 commits, and 90 to 230 findings,** before P.8. The 2026-09-28
forecast (200 to 280 for the rest of Stage 7) was made from 7.1; 266 commits have landed
since, and how many of them were Stage 7's rather than P.9, the redesign's design work and
side campaigns is not recoverable from git without a classification nobody recorded.

## 12. The real runs owed to the operator, 2026-10-02

One list for lab sessions. Times are estimates from the nearest run already done (R1's
onboarding, the staged probe runs). Each run's full steps are where it points.

**Session 1: short, on the fleet (about 2 h).** (The planned-restart correction for the
2026-10-01 15:20 to 17:10 window is DONE, run by the operator on 2026-10-02: "as a
correction, covering 9 restart(s) already seen".)

| Run | Prerequisites | Time | Steps |
|---|---|---|---|
| Staged run 6: does vIOS answer `freeMem` | none (read-only snmpget from the NMAS host) | 5 min | section 1g, staged run 6 |
| Staged run 3: the Grafana Viewer token (C230) | Grafana admin | 15 min | SERVICE_ACCOUNTS.md part 2 |
| Staged run 2: the NetBox account switch-over (C100) | NetBox admin; note the switch time | 30 min | SERVICE_ACCOUNTS.md part 1 |
| Staged run 1: the silenced-alert capture | Grafana; a device to send the test log from | 30 min | section 1g, staged run 1 |
| Staged run 4: `global.ntp-server` and `global.snmp-server-host` measured | r2 and s4; the probe changes running config only | 20 min | section 1g, staged run 4 |
| Staged run 9: the IP SLA operation's delete measured, then s3's probe to 60 s | s1 and r2 for the probe (never s3); then s3 through the tool | 45 min | section 1g, staged run 9 |
| C262 and C269: `cdp run` | r6's Device page (Mode B), then r1 to r4's intent and one batch deploy | 40 min | the register rows |
| The browser break-glass export | the laptop holding `nmas-breakglass`; a passphrase | 15 min | 7.3's break-glass notes; verify `--against` the host's digests |

**Session 2: one throwaway C8000v, start to end (about 4 to 5 h).** One device, onboarded
for the purpose into its own list, carries four runs, retired at the end (R1's shape).
Prerequisites: the current main deployed; a probe lab on the lab host with the adopted launch
patch bound and its own management subnet; a census baseline taken BEFORE anything writes;
NetBox writes on; the template approved for the platform; never during the nightly backup.

| Run | Time | What it shows |
|---|---|---|
| A1, C117's loop: onboard, seed, deploy, break, roll back | 2 to 3 h | seed's acceptance; the rollback with C112's read-back; first, whether a filter on TCP 179 holds a BGP session to its hold expiry (C178's step 2); 7.0's device list redrawn after Verify |
| A2, revert and retry | 30 min | retry with a stated reason lifts the block and the next plan offers it; a revert measured against the block |
| A3, the retirement | 45 min | needs the break-glass export (session 1) to hold the throwaway's current credential; then Retire… from its page, the census compare, the teardown |

**Session 3: the lab host's clock (about 2 to 3 h), on its own.**

| Run | Prerequisites | Time |
|---|---|---|
| Staged run 7: does re-delivering lost timer ticks fix a slow vIOS clock | a throwaway vIOS in its own lab, never s3; the lab host's contention measured before and during; outside the nightly backup | 2 to 3 h |

**Not runnable yet:** **adopt's real run** (a throwaway booting vrnetlab's own `admin`
config, after adopt's screen is built; about 1 to 2 h then). P.19's SDN lab is the end of the
plan.
