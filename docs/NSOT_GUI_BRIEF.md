# GUI redesign, step 2: the design brief

*Section 1g of [NSOT_STAGE7_PLAN.md](NSOT_STAGE7_PLAN.md). Written 2026-09-29 for the
operator's sign-off. It rests on the signed-off research in
[NSOT_GUI_RESEARCH.md](NSOT_GUI_RESEARCH.md), cited below as "R §n". Nothing here is built.
The mockups (step 3) follow sign-off, and building follows the mockups.*

## 0. Decisions taken in, and the one question answered here

**Four choices, decided by the operator at the research's sign-off (2026-09-29):**
1. **Settings** is in the sidebar, at the bottom. The user and identity stay in the top bar.
2. **Help** has two jobs:
   - a Help sidebar item opens the manual;
   - "info" links beside headings open a side help panel, in the Cloudscape style.

   No popover holds anything a person needs to read.
3. **Density** is set per component, with no global mode switch: tables compact, pages
   comfortable.
4. **Status and severity** are two separate vocabularies, as in PatternFly:
   - severity for Needs attention rows;
   - status for devices and operations.

**The question this brief answers with evidence (section 2):** task-based navigation has one
close precedent among the five products studied. Does it hold up on findability, or does a
hybrid do better?

## 1. Principles, and where each comes from

Each principle is either a rule this project already has or one all three design systems
state (R §11). Where the two meet, the project's rule governs and the research confirms it.

| Principle | Source |
|---|---|
| **The screen answers the question the person came with; the evidence is one level down.** Critical information is never behind a disclosure or a hover. | The project's presentation rule (Stage 7, 2026-09-28); R §4 and §8, all three systems |
| **One home per action.** Many devices and one device are different tasks: two entry points into one component, never two implementations. | Plan §6a; Appendix A's 24 duplicate groups, resolved in section 4 |
| **One primary action per page.** Secondary actions go behind an "Actions" menu, and destructive ones sit last, below a divider. | R §9 and §2, all three systems |
| **Bulk comes from selection, never from row buttons.** A row carries status and a link. | Plan §6a; R §2, and all four product lists |
| **Status is never colour alone:** an icon and a word, always. Colour is part of the result: a partial success is never green. | R §3; C121's FALSE_GREEN rule |
| **Preview, confirm, result**, unchanged: the six-part preview, the confirm bound to its hash, the result drawn from its record. Restyled only. | Plan §2.1; R §10 (CloudVision and Catalyst Center gate changes the same way) |
| **Every value states its age against its promise**, and a dead channel is marked on the data. Unchanged. | The live-data contract (7.2) |
| **A control a person may not use is disabled with its reason, never hidden.** This holds inside an Actions menu too. | Plan §2.6 |
| **An empty space names which of three facts it is:** nothing yet, nothing matches, or could not be read. | R §5; the project's "a failed read is not an empty list" |
| **A design layer over Bootstrap, not a rewrite** (section 9). | The operator's constraint; R §7 (Bootstrap's scale is already 4 px based) |

## 2. The findability check: task-first, object-first, or hybrid

### 2.1 The three layouts compared

All three share:
- the top bar (the device jump box of section 8, the status bar, identity);
- the same device page (section 3.3);
- a landing page that is the attention view (every product studied has one, R §10).

They differ only in the sidebar.

**T, task-first (the plan as written, §1):**
- Needs attention
- Fleet
- Versions
- Source of truth, holding page tabs for Templates, NetBox, Credentials and Oxidized
  authorisations
- (at the bottom) Help, Settings

**O, object-first (how four of the five products organise):**
- Overview (alerts)
- Devices
- Configurations (goldens, baselines, commits, the remote)
- Intent
- Templates
- NetBox
- Credentials
- Networks
- Jobs
- Integrations
- (at the bottom) Help, Settings

**H, hybrid (proposed):** the one task view first, then the objects a person looks for, named
by their nouns, with the plan's "Source of truth" kept as a group heading:

```
Needs attention
Devices
History
SOURCE OF TRUTH            (a heading, not a link)
  Templates
  NetBox
  Credentials
────────────
Help
Settings
```

### 2.2 How it was counted

- **Clicks:** counted from the landing page. Each click on a sidebar item, link, page tab,
  menu, filter, or a submitted jump box counts one. A read ends when the answer is on screen;
  a change ends when its preview is open (the confirm is identical in all three, so it is not
  counted). The best path is counted, without the jump box. A second column counts with it.
- **Scent:** whether the label of the FIRST click names the thing the question is about.
  ✓ means the noun itself, ~ a synonym or a concept word, ✗ a label that does not name it.
  This is the property that decides whether a newcomer's first click is right. It is a proxy,
  stated as one.
- **The limit, stated:** this is a paper exercise by the author, on layouts not yet drawn.
  The real test is a first-click test at the mockup review (section 11): the operator is
  given these questions and points at the first click, unprompted.

### 2.3 The twenty questions

Paths use `>` for a click. "Row" means a Needs attention row that exists when the condition
holds.

| # | The question | T: path, clicks, scent | O: path, clicks, scent | H: path, clicks, scent | With jump box (T / O / H) |
|---|---|---|---|---|---|
| 1 | What needs my attention? | landing, **0**, ✓ | landing, **0**, ~ ("Overview") | landing, **0**, ✓ | 0 / 0 / 0 |
| 2 | What changed on r3 this week? | Versions > filter r3, **2**, ~ | Configurations > Commits > filter r3, **3**, ~ | History > filter r3, **2**, ✓ | 2 / 2 / 2 (r3 > History tab) |
| 3 | Roll r2 back to its golden from before the last change | Fleet > r2 > Actions > Restore from… > the point, **5**, ~ | Devices > r2 > Actions > Restore from… > the point, **5**, ✓ | as O, **5**, ✓ | 4 / 4 / 4 |
| 4 | Is the break-glass record current? | landing > "what was checked", **1**, ✗ (or Settings > Break-glass, 2) | Credentials, **1**, ✓ | Credentials, **1**, ✓ (a stale record is a row: 0 in all) | 1 / 1 / 1 |
| 5 | Where is s1's config history? | Versions > filter s1, **2**, ~ | Configurations > filter s1, **2**, ~ | History > filter s1, **2**, ✓ | 2 / 2 / 2 |
| 6 | Onboard a switch | Fleet > Add device > Onboard, **3**, ~ | Devices > Add device > Onboard, **3**, ✓ | as O, **3**, ✓ | 3 / 3 / 3 |
| 7 | Change r2's intent and deploy it | Fleet > r2 > Intent > Edit > Commit > Plan a deploy, **6**, ~ | Intent > r2 > Edit > Commit > Plan a deploy, **5**, ✓ | Devices > r2 > Intent > Edit > Commit > Plan a deploy, **6**, ✓ | 5 / 5 / 5 |
| 8 | Deploy one change to every switch | Fleet > filter switches > select all > Deploy…, **4**, ~ | Devices > same, **4**, ✓ | as O, **4**, ✓ | 4 / 4 / 4 |
| 9 | Does r4 match its intent? | Fleet > r4, **2**, ~ | Devices > r4, **2**, ✓ | as O, **2**, ✓ | 1 / 1 / 1 |
| 10 | Edit the IOS-XE template, or see who approved it | Source of truth > Templates > cisco_iosxe, **3**, ✗ | Templates > cisco_iosxe, **2**, ✓ | Templates > cisco_iosxe, **2**, ✓ | 3 / 2 / 2 |
| 11 | Rotate s3's credential | Fleet > s3 > Actions > Rotate…, **4**, ~ | Credentials > s3 > Rotate…, **3**, ✓ | Devices > s3 > Actions > Rotate…, **4**, ✓ | 3 / 3 / 3 |
| 12 | Is NetBox in sync? Import the list | Source of truth > NetBox > Import…, **3**, ✗ | NetBox > Import…, **2**, ✓ | NetBox > Import…, **2**, ✓ | 3 / 2 / 2 |
| 13 | Is my history pushed to the remote? | Versions (the remote line), **1**, ~ | Configurations, **1**, ✗ | History, **1**, ~ (a row when behind: 0 in all) | 1 / 1 / 1 |
| 14 | Retire r5 | Fleet > r5 > Actions > Retire…, **4**, ~ | Devices > r5 > Actions > Retire…, **4**, ✓ | as O, **4**, ✓ | 3 / 3 / 3 |
| 15 | Adopt a device somebody else built | Fleet > Add device > Adopt, **3**, ~ | Devices > Add device > Adopt, **3**, ✓ | as O, **3**, ✓ | 3 / 3 / 3 |
| 16 | Why can't I deploy to r6? | a row names the block, **0**; else Fleet > r6 (Overview's gates), 2 | as T, **0** / 2 | as T, **0** / 2 | 0 / 0 / 0 |
| 17 | Ask r1 "show ip ospf neighbor" | Fleet > r1 > Ask the device, **3**, ~ | Devices > r1 > Ask the device, **3**, ✓ | as O, **3**, ✓ | 2 / 2 / 2 |
| 18 | Re-apply last week's baseline to the fleet | Versions > Baselines > Re-apply… > whole fleet, **4**, ~ | Configurations > Baselines > Re-apply… > whole fleet, **4**, ~ | History > Baselines > Re-apply… > whole fleet, **4**, ~ | 4 / 4 / 4 |
| 19 | Which integration is down? | status bar, **0**; details Settings > Integrations, 2 | Integrations, **1** | as T, **0** / 2 | 0 / 1 / 0 |
| 20 | Add a credential profile for a new site | Source of truth > Credentials > Add profile, **3**, ✗ | Credentials > Add profile, **2**, ✓ | Credentials > Add profile, **2**, ✓ | 3 / 2 / 2 |

### 2.4 What the count shows

| | T | O | H |
|---|---|---|---|
| Clicks, best path, twenty questions | **53** | **50** | **50** |
| The same, with the jump box | **47** | **45** | **44** |
| First-click scent ✓ / ~ / ✗, over the 18 questions with a first click (16 and 19 are answered on the landing page or the status bar) | 1 / 13 / 4 | 13 / 4 / 1 | **16 / 2 / 0** |
| Sidebar items (excluding Help and Settings) | 4 | 10 | 6 (5 links and 1 heading) |
| Items that are a second home for something the device page already holds | 0 | **1** (Intent: every device's intent, beside the device page's Intent tab) | 0 |

1. **Clicks barely separate the layouts:** 53, 50 and 50, and 47, 45 and 44 with the jump
   box.
   Six of the twenty best paths end on a device page (questions 3, 7, 9, 11, 14 and 17),
   and eight with the jump box (2 and 5 then reach the device's History). For those, the
   device page and the jump box decide the path, and the sidebar only its first click.
2. **Scent separates them sharply.**
   - Of eighteen first clicks, T names four with a word that does not say what is there, and
     thirteen with a synonym or a concept word. "Source of truth" hides three things a person looks for by
     name (templates, NetBox, credentials), and costs a click and a guess each time.
     "Versions" and "Fleet" are synonyms a network engineer will usually decode, but not on
     the first try.
   - The research's risk is real, and it sits in the labels, not in the task principle.
3. **Object-first has its own cost.** Ten items, and one of them (Intent) is a second home for
   what the device page's Intent tab holds: plan §6a's defect, reintroduced by the navigation.
   It also gives up the task view as the sidebar's first item: its "Overview" lands on alerts
   only by convention.
4. **The hybrid takes both strengths.**
   - It keeps the one task view (Needs attention, the landing page).
   - It names every other item by its noun (16 of 18 first clicks name their thing, none
     misleads).
   - It keeps "Source of truth" as a heading, so the plan's idea is still on the screen.
   - It adds no second home.

   Its one lost click against O (question 7, intent via the device page rather than an Intent
   item) is the price of not having two homes for intent.

**Recommendation: H, the hybrid.** Objects in the sidebar, tasks as the actions inside them,
and the one cross-cutting task (Needs attention) first. It also answers the plan's own "why
five and not more" test (plan §1): each item answers a question the others cannot. Templates,
NetBox and Credentials were one question in the plan ("are they right?"). The count shows a
person arrives with three different questions.

**What changes in the plan if H is accepted:**
- plan §1's names: Fleet becomes **Devices**, Versions becomes **History**, and Source of
  truth becomes a heading over **Templates**, **NetBox** and **Credentials**;
- acceptance item 10, which pins "exactly the five destinations plus Settings and Help", is
  restated as the sidebar above;
- the destinations' contents are unchanged.

## 3. The layout

### 3.1 The frame (every page)

- **Top bar**, left to right:
  - a menu button (narrow screens only, section 7);
  - the product name;
  - **the network switcher**: the current device list, and which other list to show;
  - **the device jump box** (section 8);
  - the **status bar**: integration health, the running version and its CI verdict, and the
    live channel;
  - the **AI assistant** button;
  - **identity**: who you are, or "not identified: you can look, not change". The theme toggle
    lives in this menu.
- **The sidebar** (section 2, H): the current page is marked, and Help and Settings sit at the
  bottom.
- **The in-flight panel**, as now, above every modal.
- **The help panel**, a side panel opened by an "info" link, closed by default.
- **The page header:**
  - a breadcrumb where the page is below a sidebar item (a device page reads "Devices / r3");
  - the title, with a one-line description beside it and an "info" link;
  - at the right: the one primary action, then the Actions menu.

### 3.2 The landing page: Needs attention

- **One line that answers:**
  - when all is well: "Nothing needs attention", with the time of every source checked;
  - otherwise: the rows.
- **Each row,** as built in 7.2: severity, what, which device or job, since when, the cause
  in its words, its operands, and ONE action.
- **The evidence behind a disclosure:** what was checked, each source's age against its
  promise.
- **Its home for conditions that today are notices elsewhere:**
  - devices with no golden (was "Capture devices with no golden");
  - pending renames (was "Sync device names to repo");
  - an AI key not set while AI is on (was a banner);
  - overdue onboardings.

### 3.3 Devices, and the device page

**Devices (the list):**
- **The page header:**
  - its title and the count ("Devices · 10");
  - the inventory source and its age for a NetBox-sourced list (was the banner below the
    table);
  - the primary action **Add device ▾**: Onboard a new device, or Adopt one already built.
- **Page tabs:**
  - **List**;
  - **Topology** (the topology service's map, read-only);
  - **Networks** (create, delete, the inventory source).
- **The list:**
  - columns: a checkbox; the name as the link to its page; status; address; platform; intent
    state (at intent / departs / no intent / no golden); last capture's age;
  - pending onboardings are rows in the list, with the status "Pending onboarding";
  - search, and filters by state and platform;
  - compact density.
- **Selecting rows raises the selection bar:**
  - the count selected;
  - **one primary** (Plan a deploy…);
  - an Actions menu, holding:
    - Capture as goldens;
    - Restore to golden…;
    - Ask the devices…;
    - Files…;
    - Download configs;
    - Ask the assistant;
    - then, below a divider, Reload….

**The device page:**
- **The header:**
  - the name, platform, network, status with its age, and the credential source it resolves
    to;
  - **the primary: Plan a deploy…**;
  - **Actions ▾**, grouped:
    - *Record*: Capture as golden, Seed intent;
    - *Change*: Restore from…, Revert an intent commit…, Re-send a blocked change…;
    - *Device*: Rotate credential…, Persist…, Reload…, Files…;
    - below a divider: Retire….
  - An action that does not apply is disabled with its reason, for example "Seed intent: this
    device has full intent (committed a1b2c3d)".
- **Page tabs:**
  - **Overview:** intent, the device, the difference, and each check with its time;
  - **Intent:** the editor and its form mode, and the render;
  - **History:** one timeline of commits, deploys and their receipts, captures, restores and
    rotations, and Compare;
  - **Monitoring:** Grafana embedded, the logs, Oxidized's fetches;
  - **Neighbours** (with C38's expected adjacencies);
  - **Ask the device:** the allowlisted command box, quick actions and history.
- **Pending devices:** a pending device's page shows its onboarding state, with Verify,
  Abandon and "Bootstrap config" as its actions.

### 3.4 History

- **The page header:**
  - the remote's state, in the sentence the reader already draws ("Everything is committed · 1
    commit not pushed…");
  - Push now, Verify and Push automatically (was the Remote card);
  - the remote's URL and branch stay in Settings > Integrations.
- **Page tabs:**
  - **Commits:** filter by device, person, workflow and time; a row opens the commit and its
    diff;
  - **Baselines:** each with what it earned; Re-apply…;
  - **Authorisations:** Oxidized divergences authorised, and freshness;
  - **Repository:** the migration and the legacy store, shown only while they apply.

### 3.5 Templates, NetBox, Credentials

- **Templates** (was the template library under the device list):
  - the library;
  - Edit, Validate, Approve and Revoke;
  - bindings;
  - round-trip coverage;
  - seed status.
- **NetBox** (was the NetBox tab):
  - the connection's state;
  - Import…, previewed;
  - lists and regions;
  - Remove…, previewed;
  - removals, the modification record and census comparisons.
- **Credentials:**
  - profiles and a network's designated credential list;
  - **the break-glass record: its currency and Export…** The Settings entry point moves here.
    The rotate result's next step and the Needs attention row stay as entry points into the
    same component.

### 3.6 Settings (bottom of the sidebar)

Page tabs:
- **Integrations:** the ten cards, the status strip, NetBox write permission, and the remote's
  URL and branch.
- **AI:** the master switch, the background agent, the provider and key, usage, the workflow
  switches, the agent's timers and its log (until Stage 8 decides its home).
- **Checks:** the drift schedule and Check now; the collectors.
- **Network:** the TFTP server, the one home of three today.
- **Server:** bind, port, auto-open, TFTP root.
- **Security posture**, read-only.
- **Diagnostics:** the app log (was the Logs tab) and redaction health.

### 3.7 Help (above Settings)

- The manual, rendered, organised by task (section 10).

## 4. Every current feature, placed once

This section follows Appendix A of the research, tab by tab. "Removed (7.8)" is the plan's
existing CUT list (plan §6). Nothing is placed twice; entry points into one component are
named as such.

**Global chrome**

| Today | New home |
|---|---|
| Status bar | Top bar (unchanged) |
| Theme toggle | Top bar, identity menu |
| AI Assistant button and panel | Top bar (the panel is unchanged; Stage 8) |
| The AI panel's Playbooks drawer | Removed with the Ansible tab (7.8) |
| API-key banner | A Needs attention row with its action |
| Ansible progress overlay | Removed (7.8) |
| In-flight panel | Unchanged |
| Device List select | Top bar network switcher |
| New List, Delete List | Devices > Networks |
| Settings button | Sidebar, Settings |

**Devices tab**

| Today | New home |
|---|---|
| Needs attention panel | The landing page |
| Onboard a device | Devices, Add device ▾ > Onboard |
| Save All Configs | Devices, select all > Capture as goldens |
| Capture devices with no golden | A Needs attention row whose action captures them |
| Reload Devices | Devices, selection > Actions > Reload… |
| Refresh Hostnames | Devices > Networks (list-level). The pending renames it records become a Needs attention row |
| Search | Devices list search |
| Bulk: Ask AI about selection | Selection > Actions > Ask the assistant |
| Bulk: Execute | Selection > Actions > Ask the devices… (the allowlist, C61) |
| Bulk: TFTP server field | Settings > Network (D10) |
| Bulk: Upload, Download, Delete file | Selection > Actions > Files… (one component with the device page's Files…, D11) |
| Bulk: Download startup/running configs | Selection > Actions > Download configs |
| Bulk: Restore Golden Config | Selection > Actions > Restore to golden… (the one restore component, D3) |
| Bulk results modal | The result component |
| Row: Manage | The device's name, as a link |
| Row: Template preview | Device page > Intent (the render) |
| Row: Deploy plan | Device page, primary: Plan a deploy… |
| Row: Edit intent | Device page > Intent |
| Row: Golden history | Device page > History |
| Drag-reorder (local lists) | Devices list, kept for local lists (decision point, section 12) |
| Inventory source banner | Devices page header |
| Remote card | History page header (D5) |
| Migration card, legacy store card | History > Repository (shown only while they apply) |
| Sync device names to repo | A Needs attention row with its action |
| Baselines | History > Baselines |
| Template library | Templates |
| `#deployWizard` (empty) | Removed |
| Onboard pending banner | Rows in the Devices list ("Pending onboarding"), their pages, and Needs attention when overdue |
| Device arrival note | Removed (the device page is the one home) |

**Other main-page tabs**

| Today | New home |
|---|---|
| Topology: service card | Devices > Topology; the service's settings in Settings > Integrations |
| Topology: built-in discovery (legacy) | Device page > Neighbours, per device (plan 1c, C126); the fleet-wide legacy view is removed (7.8) |
| Ansible tab | Removed (7.8) |
| History tab (change log) | Removed (7.8); History > Commits answers "who changed what" |
| NetBox tab | NetBox |
| NetBox safety modal's "Permit NetBox writes" checkbox | Removed; the one home is Settings > Integrations (D15), and the modal states the switch's state with a link to it |
| Agent tab: Pause/Resume | Removed: one control, the persistent switch in Settings > AI (D6). The pause was in memory only and lost on restart (decision point, section 12) |
| Agent tab: timers, trigger, activity log | Settings > AI |
| Approvals tab: approval cards | Needs attention rows (an approval is one source) |
| Approvals tab: Approve All | Needs attention: the drift source's row action ("Capture all drifted devices…") |
| Approvals tab: drift check (interval, enabled, Check now) | Settings > Checks, together with the drift timer that was on the Agent tab (D7) |
| Monitoring: Integrations cards | Settings > Integrations (D17: the status bar summarises, Settings details) |
| Monitoring: Oxidized freshness | Needs attention (rows) and the device Overview (per device); authorisations under History |
| Monitoring: legacy collectors (OOB IP, snippets, SNMP poll, traps, NetFlow) | **Removed** (decision 5, and the plan's 7.3-e retirement): traps and syslog live in Grafana and Loki. SNMP Quick Poll goes with them (feature audit: CUT) |
| Configure tab: the forms | The device page's Intent editor, form mode (plan 1c, the parallel track 7.9) |
| Configure tab: Ansible Wizard | Removed with Ansible (7.8) |
| Git tab | History > Commits |
| Logs tab | Settings > Diagnostics |
| Settings modal | Settings, as a page (section 3.6); its break-glass export moves to Credentials |

**The device page**

| Today | New home |
|---|---|
| Restore Golden Config (navigates away) | Actions > Restore from…; the golden at HEAD is its first option, and it runs in place (D3; misplacement 13) |
| Restore from… | Actions > Restore from… |
| Capture as golden, Seed intent | Actions > Record |
| Revert intent…, Retry rolled-back change… | Actions > Change |
| Rotate credential…, Persist… | Actions > Device |
| Retire… | Actions, below the divider |
| Ask AI | Top bar AI assistant |
| Back to Devices | The breadcrumb |
| Utilities tab (quick actions, custom command) | Ask the device (D12) |
| File Management tab | Actions > Files… (D11) |
| Terminal tab | Removed (7.8) |
| Backups tab: Backup Config | Removed with the backup store's retirement (plan §6a's prerequisite); a capture is the one read into a store (D2) |
| Backups tab: Compare Backups, history rows | History > Compare, over the timeline (D4) |
| Changes tab (receipts) | History (the timeline carries each deploy's receipt) |

## 5. The duplicate inventory, resolved

For each group in the research's Appendix A: the home it keeps, and what goes.

| # | Function | The one home | What goes |
|---|---|---|---|
| D1 | Capture a golden | One component. Entry points: Devices selection (many), device Actions (one), Needs attention rows (drifted, no golden) | Nothing: allowed entry points into one component |
| D2 | A config read into a store | **Capture** | Backup Config, the template preview's "Refresh capture" (the render reads the latest capture), the Ansible backup (7.8), the `wfAutoBackup` setting (with the backup store's retirement). Download configs stays: it writes a file for the person, not a store |
| D3 | Restore to a golden | One component. Entry points: selection (many), device Actions (one), History > Baselines (a baseline), a Needs attention approval row | The device page's second control "Restore Golden Config" (folded into Restore from…) |
| D4 | History and compare | **Device page > History** (one device) and **History** (the fleet), one timeline component, filtered | The row's Golden history modal, the History tab, Compare Backups, the Changes tab |
| D5 | The remote | **History's header** (state and actions); Settings holds the URL and branch only | The Remote card; auto-push's second control |
| D6 | Background agent | **Settings > AI**, the persistent switch | `#bgAgentEnabled` (removed, C226); the in-memory Pause (decision point) |
| D7 | Drift schedule | **Settings > Checks** | The Agent tab's copy of the drift timer |
| D8 | Playbooks | Removed with Ansible (7.8) | Both |
| D9 | Playbook generation | Removed with Ansible (7.8) | The Ansible Wizard |
| D10 | TFTP server | **Settings > Network** | The bulk panel's field; the device page's field and its second `saveTftpServer` |
| D11 | File transfer | One component, **Files…**. Entry points: selection (many), device Actions (one) | The second implementation (the bulk routes and the per-device routes become one path) |
| D12 | Run a command | **Ask the device** (one) and **Ask the devices…** (many): one allowlisted component | The terminal (7.8); Ansible's custom commands (7.8). SNMP Quick Poll moves to Monitoring as a different protocol, not a command |
| D13 | Open the assistant | **Top bar**; selection > Ask the assistant (carries the selection as context) | The device page's Ask AI button (the top bar is always there) |
| D14 | NetBox import of this list | **NetBox > Import…** (one preview for one list or all) | The row "Sync" that duplicated Import Current List |
| D15 | Permit NetBox writes | **Settings > Integrations** | The safety modal's checkbox (the modal states the switch and links to it) |
| D16 | NetBox connection | **Settings > Integrations** (test and configure); the NetBox page shows the state | The Monitoring tab's NetBox card |
| D17 | Integration health | **The status bar** (summary), **Settings > Integrations** (detail and Test) | The Monitoring tab's Integrations cards |
| D18 | Topology | **Devices > Topology** (the service); **Neighbours** (one device) | The legacy discovery's fleet view (7.8) |
| D19 | Collectors | **Settings > Checks > Collectors** | The Monitoring tab's OOB block |
| D20 | Break-glass export | One component. Home: **Credentials**; entry points: a Needs attention row, the rotate result's next step | The Settings entry point |
| D21 | Open Settings | **The sidebar** | The five buttons (a "Configure…" link inside a not-configured state stays; it is navigation, not a second control) |
| D22 | Refresh identity | **Devices > Networks**: Refresh hostnames (local lists), Refresh from NetBox (NetBox lists) | "Sync device names to repo" becomes a Needs attention row's action, not a control of its own |
| D23 | Configure form types | The form mode of the Intent editor lists each type once | The duplicated `ipv6/dhcpv6` entry and label |
| D24 | Intent authoring | **Device page > Intent** (editor and form mode) | The row's Edit intent; the Configure tab |

## 6. Component rules

**Buttons and actions**
- One primary per page, filled. Secondary actions are outlined. Everything else goes in the
  **Actions ▾** menu.
- Menu items are grouped, and destructive ones sit last, below a divider.
- An item that does not apply is disabled with its reason on the item, never hidden.
- A danger-coloured button appears only inside a confirm.
- **Typed confirmation, for Retire only:** type the device's name before the preview's
  confirm enables. It is the one action that takes a device out of management (R §6).
  Everything else keeps the preview's hash-bound confirm, which is already stronger than a
  typed word.

**Tables**
- The count beside the title.
- The name is the first column and the link; status is the second.
- `-` for an empty value.
- Sorting and filtering only above five rows.
- The selected count in the selection bar, and selection cleared when a filter changes.
- Compact density.
- No row buttons (plan §6a).
- Pagination at the bottom once a list exceeds a page (the §0a scale constraint:
  nothing renders every device).

**Status, for devices and operations: an icon and a word, always**

| Kind | States |
|---|---|
| A device's reachability | Answering · Not answering · Not yet probed · Pending onboarding · Left the inventory |
| A device's record | At intent · Departs from intent · No intent · No golden · Blocked (a rolled-back change) |
| An operation | Running · Succeeded · Partly done · Failed · Nothing to do · Refused. These are the result component's `RESULT_LEVELS` plus Running and Refused |

**Severity, for Needs attention rows only:** a word and a left-edge bar, never the status
icons.

| Level | Meaning |
|---|---|
| **Critical** | Was `danger`: something is broken or at risk now |
| **Warning** | Was `warning`: it needs a person, and nothing is broken yet |
| **Unknown** | Was `unknown`: a source could not be read. It is never counted as fine |

The code's `LEVELS` do not change; only the words drawn do.

**Page header**
- The breadcrumb, then the title, then a one-line description.
- An "info" link beside the title and beside each section heading.

**Empty states:** three forms, each with one next action, and never a primary button.

| State | Example |
|---|---|
| **Nothing yet** | "No devices in this list yet." > Add device |
| **Nothing matches** | "No devices match 'r9'." > Clear the filter |
| **Could not be read** | "The inventory could not be read at 14:02: <reason>. This is not an empty list." > Retry |

**Forms**
- Single column, with labels above the fields.
- **Only the optional fields are marked:** most fields here are required.
- Validation runs when a field loses focus, never on first view.
- **The submit is never disabled.** A refusal is stated on the button and above it (plan
  §2.1.6; Cloudscape's rule).
- A server's errors are summarised above the submit.

**Help**
- An "info" link opens the side help panel at the manual section for that heading, with
  "Open in the manual" at its foot.
- Tooltips only name an icon or show truncated text.
- Nothing a person must read to act is in a hover. Today's `title=` reasoning moves into the
  page or the help panel.

**Icons:** today's emoji go. A subset of **Bootstrap Icons** (MIT) is vendored as one inline
SVG sprite, listed in `static/js/vendor/MANIFEST.json` with its hash (C123), and holds only
the icons the pages use.

**Colour, spacing, type**
- **Tokens** are CSS custom properties layered over Bootstrap 5.3.3's own `--bs-*` variables,
  with a light and a dark value each (the theme toggle already switches `data-bs-theme`).
- **Spacing** uses Bootstrap's scale (4, 8, 16, 24, 48 px) and nothing else: no pixel values
  in templates.
- **Type:** body 14 px, page title 24, section 20, sub-section 16. Bootstrap's system font
  stack stays: no web fonts, since the tool is air-gapped.

## 7. Accessibility, and narrow screens

### 7.1 Accessibility

**The target is WCAG 2.2 level AA,** which all three design systems target:
- Carbon names WCAG 2.1 AA and the IBM checklist;
- PatternFly names 2.2 AA;
- Cloudscape follows WCAG.

The sources, read as search summaries of their accessibility pages:
[Carbon](https://carbondesignsystem.com/guidelines/accessibility/overview/),
[PatternFly](https://www.patternfly.org/accessibility/patternflys-accessibility/),
[Cloudscape](https://cloudscape.design/foundation/core-principles/accessibility/),
[Cloudscape focus management](https://cloudscape.design/foundation/core-principles/accessibility/focus-management-principles/).
The criteria themselves: [WCAG 2.2](https://www.w3.org/TR/WCAG22/) 1.4.3, 1.4.11, 2.1.1 and
2.4.7.

**Contrast is a CHECK, not a guideline** (the operator; C138 shipped light text on
near-white):
1. **A test computes the WCAG contrast ratio of every token pair the design layer declares,**
   in both themes:
   - text on its backgrounds: at least 4.5:1, or 3:1 at 24 px and above;
   - borders, focus rings and status icons against their backgrounds: at least 3:1.

   A pair below its threshold fails the suite, naming both colours.
2. **A scan fails any template or script that sets a colour other than through a token**
   (a hex value, `rgb(`, or a named colour in a `style` attribute or a stylesheet outside the
   token file). Without it, the ratio test covers the tokens and not what is drawn, which is
   how C138 got through: a code block took Bootstrap's own colours on a background someone
   else set.
3. **The control:** C138's own pair, planted, fails the first; a planted inline colour fails
   the second.

**Keyboard:**
- Every action is a `<button>` or an `<a href>`. A scan fails a clickable `<div>` or `<span>`
  (`onclick` on anything else), because those take no focus.
- A visible focus ring at 3:1 on every control.
- A "Skip to content" link first on each page.
- The sidebar is `<nav aria-label="Main">`, with `aria-current="page"` on the current item.
- Modals take focus, keep it until closed, close on Escape and return focus to the control
  that opened them (Bootstrap does this; the scan asserts every dialog is a Bootstrap modal).
- The Actions menus open with Enter and move with the arrow keys (Bootstrap's dropdown).
- **Checked by hand at each screen's acceptance:** every screen walked with the keyboard
  alone, because what a scan cannot see is the order. The result is recorded in the stage's
  writeup entry.

### 7.2 Narrow screens (the tool on a phone through the tunnel)

Bootstrap 5.3.3's own breakpoints and components; nothing new is vendored.

**Below 992 px:**
- **The sidebar becomes an off-canvas panel** behind the top bar's menu button, and closes
  when an item is chosen.
- **The top bar keeps** the menu button, the network name, one status dot with a count (a tap
  opens the status bar's detail) and the identity icon.
- The jump box becomes a search icon that expands.

**Below 768 px:**
- **Tables keep their priority columns:**
  - the Devices list shows the checkbox, the name and the status;
  - address, platform and intent state appear on the device page.
- **The selection bar docks to the bottom of the screen,** its primary still one tap away.
- **Previews, confirms and results open full-screen** (`modal-fullscreen-md-down`), and the
  confirm button stays pinned at the bottom.
- **Wide content scrolls inside its own box, never the page:** programs, diffs, configs and
  Grafana panels.
- **The device page's tabs become a strip that scrolls sideways.** Actions stays in the
  header.

**Checks:**
- A scan asserts every modal carries the full-screen class.
- The mockups (step 3) include phone width, for the landing page, the Devices list and one
  device page.
- Each screen's acceptance includes a walk at 375 px.

## 8. Global search: a device jump box, not a full-text search

**Decided in this brief: build a "go to device" box in the top bar. Do not build a full-text
search.**

- **Why the jump box earns its place:**
  - Six of the twenty best paths end on a device page, and the box saves a click on each of
    those six (section 2.4).
  - At the plan's scale target (§0a: 900 devices and more), the list becomes a filter hunt,
    and the box does not change with scale.
  - Its cost is small: the inventory index is already in memory, and dispatch does no I/O.
  - It matches names and addresses, is keyboard-first (`/` focuses it), and Enter opens the
    device page.
- **Why not full-text search across commits, configs and NetBox:**
  - it would be a second home for History's filters (plan §6a);
  - it would be a new surface returning stored configuration, which is a masking surface
    (C77);
  - every product that has one studied is larger than this tool's scope.
- **Revisit it when** a question in section 2's set needs more than four clicks after the
  redesign, or when questions that cross objects appear ("where is this address used").

## 9. The stack: REOPENED, decided after the mockups

**Superseded 2026-09-29** by the operator's principle: the frontend decides and the backend
serves it, and tests are a cost to weigh, never a veto (NSOT_STAGE7_PLAN section 1g). The
mockups are designed first for the best experience, unconstrained by the stack. The
assessment of whether the current stack builds each screen WELL follows them, with an
alternative named and costed wherever it would not. The first reasoning is kept below,
because its costs are still costs.

### 9a. The first reasoning: a design layer over Bootstrap

**What gets built:**
- `static/css/nmas.css`: the tokens, the type scale and the component classes;
- Jinja macros in `templates/components/`, one per rule, so each rule has one implementation:
  the page header, status, severity, empty state, the Actions menu, the info link, the
  selection bar;
- the sidebar in `base.html`;
- the icon sprite.

There is no build step and no new framework, as CLAUDE.md's conventions require.

**Why not a rewrite:**
- About 200 tests execute the shipped JavaScript in duktape and read the rendered pages
  (payload-to-render, reachability, invalidation, results drawn). They carry the project's
  guarantees about what the screen shows, and a new front-end framework would retire them and
  the checks built on them.
- The pages are server-rendered with vendored, hash-pinned assets for an air-gapped network.
- The users are one operator and the people after them.

Nothing studied requires what Bootstrap lacks.

**The cost that stays:** `index.html` (8,045 lines) is split into page templates, one per
sidebar item. That is the same work 7.x does screen by screen, now done in the new frame
rather than the old tabs.

## 10. The manual

- **Where it lives:** Markdown in `docs/manual/`, versioned with the code, in the same
  neutral voice, and under the same publication check as every document.
- **How it is organised:** by task.
  - **Getting started:** the model: intent, a golden as a record, preview-confirm-result.
  - **Tasks:**
    - onboard a device; adopt a device;
    - deploy a change; deploy to many;
    - restore a device or a baseline;
    - revert and retry;
    - recover from a lockout;
    - rotate a credential; export the break-glass record;
    - retire a device;
    - import into NetBox;
    - approve a template;
    - read what changed.
  - **Screens:** one section per sidebar item and per device-page tab, which the info links
    open.
- **Rendered at `/help/<page>`,** server-side.
  - **The cost:** a Markdown renderer. Python-Markdown is packaged for Ubuntu as
    `python3-markdown`, so the host installs it with apt and `requirements.lock` is
    regenerated there (C37, C40).
  - The manual is the repository's own text, and it is rendered with raw HTML disabled.
- **Checks:**
  - every sidebar destination and every info link resolves to an existing manual anchor
    (floor: the eight sidebar items);
  - a planted link to a missing anchor fails;
  - a stage is not closed until the screens it changed are documented (plan §10, item 15);
  - every operation has its "How it works" section (section 10a), with a floor.

### 10a. How it works: the tool teaches what it does (the operator, 2026-09-30)

This is a lab, so the tool should teach what it is doing, not only do it. The footprint in
the interface stays small, and it is built on what this brief already has: the manual, the
info links, and the steps the code already declares.

- **Every operation gets a "How it works" section in the manual.**
  - **The operations:** Save All, re-apply a baseline, deploy, restore, capture, rotate,
    persist, seed, adopt, onboard, and a Mode B removal.
  - **What each section says:** what happens, in what order, what is read, what is sent,
    what is recorded, and why each step exists.
  - **Written for someone learning,** in plain language, one step per paragraph.
- **One source, two places.** The info link beside an operation opens THAT SAME manual
  section in the side help panel (section 3.7). Never a second copy of the words: two
  copies drift apart, as the plan's gate list did.
- **While an operation runs, its steps are shown, with the current one highlighted.**
  - **The steps are GENERATED from the steps the code runs**, never a hand-written list.
    The definitions exist already: persist's preview draws "what persist does, in order"
    from the module, and adopt's `APPLY_STEPS`, rotation's states and phase two's steps are
    each a declared sequence.
  - **The current step comes from the operation's own progress note** (the in-flight
    panel's `op_progress`, C99), so the stepper and the in-flight panel say the same thing.
  - **Each step carries its elapsed time** once it has run longer than a few seconds, and
    what it is waiting on. This fixes the persist run where four minutes showed only
    "persisting" (C218).
  - **A step list with no declared source is refused** by the manual check below, so a
    stepper can never be a drawing of what somebody thought the code did.
- **Diagrams for the ideas that are hard to hold in words.** The operator learns best
  visually. The first three:
  1. **The onboarding flow:** the ZTP bootstrap, Verify, seeding intent, the first deploy.
  2. **What a baseline contains:** every golden and every device's intent, at one commit,
     and the tag that names it.
  3. **How intent, golden and the device relate:** what should be, what was recorded, what
     is; which operation moves which (deploy moves the device toward intent, capture moves
     the golden toward the device, seed moves intent from the golden).

  Diagrams are SVG in `docs/manual/`, drawn with the design tokens, with a text description
  beside each (accessibility, section 7.1).
- **The check, extended:**
  - every operation in a declared list has a "How it works" section, floor eleven;
  - every step an operation's code declares is named in its section;
  - an info link opens an anchor that exists;
  - a stepper's steps come from a declared code source (planted: a hand-written list
    fails).

## 11. What the mockups (step 3) will show

- **Three screens at desktop width:**
  - the landing page with the sidebar;
  - the Devices list with a selection active;
  - r3's device page, with the Actions menu open.
- **The same three at phone width.**
- **Drawn with real content:** the fleet's names, one row of each severity, a partly-done
  result, and a disabled action with its reason.
- **Published as a page to look at,** not a document (the operator asked for visuals).
- **At the review, the first-click test:** section 2's twenty questions, the operator
  pointing at the first click on the mockup without being told. Any miss is a finding for the
  layout, recorded before building.

## 12. Decision points for the operator

**Decided 2026-09-29.** The decisions and the measurements behind 3 and 5 are recorded in
NSOT_STAGE7_PLAN section 1g:
1. The hybrid sidebar: accepted.
2. Pause: removed.
3. Drag-reorder: to be removed in favour of sortable columns, reported to the operator
   before removal. Nothing depends on list order today. The redesign's selection would have
   made list order the deploy batch's rollout order, so that order is drawn and settable in
   the batch deploy preview instead.
4. Typed confirmation for Retire only: agreed.
5. The legacy trap and NetFlow views: removed.

The recommendations as they were put:

1. **The sidebar: H, the hybrid (section 2).** Accepting it renames Fleet, Versions and
   Source of truth in plan §1 and restates acceptance item 10.
2. **The Agent tab's Pause:** removed, leaving the persistent switch in Settings > AI as the
   one control. The pause was in memory only and lost on a restart, two controls that looked
   like one switch.
3. **Drag-reorder of a local list:** kept on the Devices list. The alternative is sorting
   only, which is simpler and removes a feature somebody may use.
4. **Typed confirmation for Retire:** the one action to get it.
5. **The legacy collectors (SNMP traps, NetFlow buffers):** kept under Settings > Checks
   until Grafana's views replace them, or removed now with the other legacy blocks.

## 13. The mockup review, decided (the operator, 2026-09-29)

- **Impression:** much cleaner and more appealing than today's GUI. **The mobile layout is a
  first-class requirement,** not an afterthought.
- **The first-click test is skipped:** the twenty-question counts (section 2) stand as the
  evidence for the hybrid sidebar. The questions are kept as an **acceptance check on the
  BUILT screens.**
- **Drag-reorder is removed** in favour of sortable columns. The batch deploy preview shows
  and sets the rollout order.
- **Fonts: IBM Plex,** bundled locally so the tool works air-gapped (the SIL Open Font
  License allows it). This replaces section 6's system font stack.
- **The legacy in-app collector, its views and SNMP Quick Poll are removed.** The app still
  SHOWS traps and syslog, read from Loki, and alerts from Grafana. Those stay the one place
  such data originates: the app reads and displays, and never collects or stores it.

## 14. The app as the one place: every integrated service

**The requirement (the operator, 2026-09-29):** a person should almost never need to open
Grafana, Kea, NetBox, Loki, Prometheus or Oxidized directly. That means fully realised
screens, not status cards.
- **Each device page shows its slice of every service.**
- **Each service has one fleet-wide screen.**
- **Every read follows the reader pattern** (plan §0a: no per-device work per request) and
  the live-data contract (7.2).
- **Masking and redaction apply to everything shown** (section 15, question 4).
- **Order: these screens come AFTER P.8,** because each network can have its own Grafana,
  Kea and NetBox scope (C173).

### 14.1 The sidebar, extended

A second heading, **OBSERVE**, holds the fleet-wide service screens. It stays one level deep,
and each item is named by the noun a person arrives with (section 2's rule):

```
Needs attention
Devices
History
OBSERVE
  Monitoring   charts, alerts, the PromQL query, hosts and the lab
  Logs         syslog and traps from Loki, the LogQL query
  DHCP         subnets, pools, leases, reservations
SOURCE OF TRUTH
  Templates
  NetBox       the browser, then import and remove
  Credentials
────────────
Help
Settings
```

**Where each service lives:**
- **Oxidized has no item of its own:** its config versions are History's (fleet) and the
  device page's (one device), always labelled as Oxidized's copies.
- **Proxmox and the containerlab nodes** are Monitoring > Hosts. They are status, not a
  destination.

**The device page's tabs become:** Overview · Intent · History · Monitoring · Logs · NetBox ·
Neighbours · Ask the device.
- **Monitoring:** this device's charts and alerts.
- **Logs:** its syslog and traps.
- **NetBox:** its record, with interfaces, addresses and cables linked into the browser.
- **The DHCP lease** is one line of the Overview's facts: the address, its reservation, the
  lease's expiry. A device takes an address from DHCP or does not, and a tab for one line
  would be a tab that is usually empty.

On a phone the tab strip scrolls sideways (section 7.2).

**Signed off, with one rule (the operator, 2026-09-30): a tab with nothing to show for THIS
device is not drawn.** The DHCP lease's reasoning, applied to every tab:
- **NetBox**, for a device NetBox does not hold: no tab. The Overview's facts say "not in
  NetBox" in one line.
- **Neighbours**, on a device with none: no tab. The Overview says "no CDP or LLDP
  neighbours seen" with the time of the read.
- **Logs**, for a device Loki holds nothing from in the range: the tab stays, because "no
  lines in 24 hours" is itself a finding about a device that should be sending heartbeats.
- **Monitoring**, for a device Prometheus does not scrape: no tab. The Overview says "not
  scraped by Prometheus", which after C229's fix inside P.7 is a defect, and is a Needs
  attention row.
- **Intent, History, Ask the device:** always there, because every managed device has them.

**So most devices show five or six tabs, and eight is the ceiling, not the norm.** Whether a
tab is drawn is decided from the readers' stored values (never a live read on page load,
plan §0a), and the fold is stated in the Overview, so a missing tab never reads as a
missing feature.

### 14.2 The screens

**Monitoring (Grafana and Prometheus): both, for different jobs.** The operator asked for
both, with costs.
- **Native charts, drawn in the design system:** the key ones only.
  - **Which:** reachability, CPU, memory, interface throughput and errors, and heartbeat
    arrivals.
  - **How:** drawn from bounded PromQL range queries through the NMAS's Prometheus client.
  - **Why:** they work at phone width, match the look, and carry the live-data contract's
    age stamp.
  - **Cost:**
    - a vendored time-series library (uPlot, MIT, about 45 KB, fast at thousands of
      points), hash-pinned (C123);
    - one bounded read route per chart family;
    - defining the chart set, which is ours to own.
  - They never try to be Grafana: a chart links to its Grafana dashboard on desktop.
- **Full Grafana dashboards, embedded, for desktop deep dives.**
  - **The route (the operator's preference): Grafana under the NMAS's own origin:**
    - a reverse proxy at `/grafana/`, with Grafana's `root_url` and `serve_from_sub_path`
      set;
    - `auth.proxy` enabled, trusting ONLY a header the NMAS proxy sets from the verified
      identity. The proxy strips any client-supplied copy, because an unverified header is
      the forgery `modules/identity.py` exists to refuse;
    - users auto-created with the **Viewer** role, which by Grafana's default role
      permissions cannot create silences or edit rules, so question 3 below holds inside
      the embed too. That is confirmed on the host's Grafana version before the embed is
      accepted.
  - **Corrected by the operator (2026-09-30): restrict who can ASSERT AN IDENTITY, never who
    can reach Grafana.** The operator creates and edits dashboards, and does it in Grafana
    directly. So:
    - **Grafana stays reachable for a direct login,** with its own authentication.
    - **`auth.proxy`'s address allowlist names the NMAS host only.** The trusted header is
      honoured from the NMAS and ignored from anywhere else.
    - **The hard, verified condition:** a request carrying the header from any address other
      than the NMAS is NOT authenticated by it. Job health checks it keeps holding (section
      15.3).
    - **The app shows dashboards read-only, as Viewer. Dashboard AUTHORING happens in Grafana
      directly, never through the NMAS.** On the installed version the role that edits
      dashboards can also silence and edit rules (measured, section 15.3), so authoring
      through the app would reopen silencing.
    - **The proxied users are their own users.** `auth.proxy` logs in an EXISTING user with
      that user's role, so the NMAS asserts a name in its own namespace (`nmas:<email>`),
      never a direct-login name: those carry Editor or Admin (the ruler shows rules last
      edited by accounts named `admin` and `nmas-automation`), and asserting one would give
      the embed that role. A new name is created as Viewer.
    - The full design, with what job health checks, is section 15.3.
  - **What that removes:** the frame is same-origin, so plan §3's blockers 2 to 4 go (the
    loopback address, a second Access application, `frame-src`). Blocker 1 stays:
    `allow_embedding` must be on, which is the operator's, as root on the host.
  - **Cost:**
    - the proxy, including Grafana Live's websocket;
    - header hygiene, with a test that a client-supplied identity header never reaches
      Grafana;
    - the settings on the host.
  - **At phone width the embed is not offered:** the native charts are the phone's
    monitoring.
- **Alerts:** every firing instance with its rule, device, onset and state, and its silence
  (question 3 below). Needs attention stays the place a person is told; this is the full
  list.
- **Query:** a PromQL box, results as a chart and a table, bounded (question 5).
- **Hosts:** Proxmox VMs (the existing read-only client) and containerlab nodes, whose status
  needs a new read-only reader (section 15.2).

**Logs (Loki):**
- **Fleet-wide:** time range, device, severity, facility, traps or syslog, and text.
- **Per device:** selected by the device's OWN origin-id, never rsyslog's hostname (C13,
  C166).
- **A LogQL query screen.**
- **Bounded:** a range cap, a line limit and a timeout.
- **Masked:** a log line can quote a config line or a credential, so the same redaction
  applies, and unmasking is the reveal gate.
- **Traps are shown as Loki stores them.** Which stream and labels the trap pipeline writes
  is measured when this is built, never assumed.

**DHCP (Kea):**
- subnets and pools, with their utilisation (Kea's `statistic-get-all`, a read);
- active leases, filterable by address, MAC and hostname;
- reservations: those in the NMAS's own fragment, which are editable (section 15), and those
  in Kea's main config, shown **marked and read-only**;
- ZTP reservations marked as such.
- **Where the NMAS may write reservations (the operator, 2026-09-30): a per-network setting,
  after P.8, listing the subnets.** A subnet not on the list shows its reservations and
  offers no Add. The checks, per subnet kind:
  - **The ZTP segment:** D4's posture checks (no route or resolver option at any level, and
    nothing answering broadcast DNS), unchanged and scoped to that segment only.
  - **Every other listed subnet:**
    - the address is inside the subnet;
    - it clashes with no pool range and no other reservation (by address, and by MAC);
    - it is not a managed device's management address, unless the reservation is FOR that
      device (matched by the device's recorded MAC).
  - **Every write:** the existing writer's candidate test (`kea-dhcp4 -t`), reload and
    read-back naming both operands, restore on failure; previewed, confirmed and recorded as
    the person.
- **Lease history per device:** Kea's API returns current leases only, so history is the
  reader's own record. Each read's leases are kept with a bounded retention, stating that it
  is observed, not Kea's. (Kea's legal-log hook would be the alternative; whether the host's
  Kea ships it is unmeasured.)

**NetBox, a browser:**
- sites, devices, interfaces, prefixes, VRFs, VLANs, IP addresses and cables, each linked to
  the others;
- filtered and paged on the server;
- `local_context_data` masked (C95, C139);
- no edit and no link out (question 2);
- the import and remove previews stay, as this item's tabs.

**Oxidized:**
- **Config versions and diffs, per device**, beside the golden history, labelled "Oxidized's
  copy, fetched at T".
- **Diffs against the golden are the freshness signal made visible.**
- **Measured when built:** oxidized-web lists versions only when Oxidized's output is git.
- **"Fetch now"** (section 15.2).

**Also integrated, and placed:**
- **The topology service:** Devices > Topology.
- **The NSoT git remote:** History's header.
- **The S3 archive:** History > Repository, its listing read-only.

The Anthropic API and Cloudflare Access have no screens: the assistant panel, and identity
in the top bar.

## 15. What each connector may do: a rule, not a list

**The five questions (the operator, 2026-09-29).** Every capability is judged by what it
could change, never by which service it belongs to:
1. **Does it change the network or a device?** Then only through the NMAS's own operations
   and their gates.
2. **Does it change something the NMAS treats as its RECORD or EVIDENCE?** That covers
   NetBox, goldens, Oxidized's copies, stored logs and metrics, alert rules and audit
   trails. They are never edited directly: written only by the NMAS's operations, or
   generated from the inventory.
3. **Does it HIDE a signal the safeguards depend on?** Silencing an alert, disabling a rule
   and deleting logs are NOT ALLOWED.
4. **Can it REVEAL a secret?** Then the reveal gate and redaction apply, even to a read:
   query results can carry config lines.
5. **Can it OVERLOAD the service?** Then it is bounded: time ranges, row limits, timeouts.

**A capability that passes all five is added freely,** and generously.

### 15.1 The classification

Checked against the code and the services on 2026-09-29. Corrections to the agreed version
are marked **Corrected**.

| Service | Capability | In the app? | Decided by | Gate or bound |
|---|---|---|---|---|
| Loki | LogQL queries; per-device and fleet logs and traps | **Freely** | passes all five | Q4: masked, reveal gate to unmask. Q5: range cap, line limit, timeout |
| Loki | Deleting logs | Not in the app | Q3 (hides a signal), Q2 (evidence) | - |
| Loki | Editing alert rules | Not in the app | Q2, Q3 | Rules are Grafana's, generated by P.7 |
| Prometheus | PromQL queries, charts | **Freely** | passes all five | Q5: range cap, minimum step, series limit, timeout |
| Prometheus | Scrape targets | Not in the app | Q2 (they decide what evidence exists) | **Corrected:** nothing generates them today. They are Prometheus's own config on its host, hand-maintained, and retire only warns about a target still scraping an address (C229). **Decided 2026-09-30: P.7 generates them from the inventory beside the alert rules**, so a new device is scraped and a retired one is not, with nobody editing a file on the Prometheus host |
| Grafana | Dashboards; alert state, including silences | **Freely** | passes all five | Embedded as Viewer (section 14.2), through `auth.proxy` whose allowlist names only the NMAS (15.3) |
| Grafana | Creating and editing dashboards | Not in the app: **in Grafana directly**, by a direct login | Q3: on 13.2.0 the role that edits dashboards also silences and edits rules (15.3) | Grafana's own authentication |
| Grafana | Silencing, acknowledging to hide | Not in the app | Q3 | - |
| Grafana | Editing alert rules | Not in the app | Q2, Q3 (C168: the hand-built ones were wrong) | Generated only by P.7's generators, **as file-provisioned rules**: Grafana refuses a UI or API edit of those for every role (the heartbeat rules are provisioned so today, measured). A folder permission cannot do this on 13.2.0 (15.3) |
| Grafana | A silence set INSIDE Grafana | Shown, never hidden | Q3 | The alert stays on screen as active, marked "silenced in Grafana", with who and until when: **built 2026-09-30** (15.2) |
| Kea | Subnets, pools, utilisation, leases, lookups by MAC, address or hostname | **Freely** | passes all five | Q5: paged reads |
| Kea | Add, edit, remove a reservation | **With gates**, on the subnets a per-network setting lists (after P.8) | Q1 (it decides a device's address) | The existing writer: its own fragment file only (`<?include?>`), a candidate tested with `kea-dhcp4 -t`, reload, a read-back naming both operands, restore on failure. The D4 posture checks on the ZTP segment only; elsewhere, inside the subnet, no clash with a pool or reservation, and never a managed device's management address unless the reservation is for that device (14.2). Preview, confirm and result, recorded as the person |
| Kea | Reservations in Kea's main config | Shown, marked, read-only | Q2 | - |
| Kea | Editing Kea's main config (subnets, pools, options) | Not in the app | Q1 (the network's design) | - |
| Kea | Releasing a lease (`lease4-del`) | Not in the app | Q1 (a device in the inventory loses its management address) | - |
| NetBox | Browsing and searching everything | **Freely** | passes all five | Q4: `local_context_data` masked (C95). Q5: paged |
| NetBox | ANY edit, or an "edit in NetBox" link out | Not in the app | Q2: the NMAS is NetBox's only writer, through deploys, onboarding and imports | A change made directly in NetBox is DRIFT, **measured exactly** once the NMAS has its own account (C100, decided 2026-09-30, 15.2) |
| Oxidized | Config versions and diffs | **Freely** | Q4 applies | Masked, reveal gate to unmask |
| Oxidized | "Fetch now" (queue the node with oxidized-web's `node/next/<name>`; its method is checked against the host's version when built) | **With gates** | Q1: it reads the device and changes nothing. Q2: Oxidized writes its own new version, which is its evidence, written by it | A verified person, recorded (who, when, which node); bounded to one node per request |
| Oxidized | Editing its copies | Not in the app | Q2 | - |
| Oxidized | Its device list (`router.db`, which holds credentials) | Not in the app **as an edit** | Q2, Q4 | **Corrected:** the NMAS already WRITES it, through an operation. Rotation's persistence chain updates a device's credential there with the `nmas-oxidized-cred` helper, then reloads Oxidized. That fits question 2 (written only by the NMAS's operations), and it stays the only writer |
| Proxmox | VM status, backups (read-only token, four paths) | **Freely** | passes all five | - |
| Containerlab | Node status | **Freely** | passes all five | Needs a new read-only reader (15.2) |
| Proxmox, containerlab | Deploying or destroying VMs or nodes | Not in the app | Q1 (the physical world) | - |
| Topology service | The map, its status | **Freely** | passes all five | - |
| NSoT git remote | History, push state | **Freely** | passes all five | - |
| NSoT git remote | Push | **With gates** | Q2 (publishes the record) | `publish_remote`, a person. Never force-pushed |
| S3 archive | Listing | **Freely** | passes all five | - |
| S3 archive | Deleting an archive | Not in the app | Q2, Q3 | Written only by the post-commit archive hook |
| Anthropic API | Sending context to the model | Outbound only | Q4 | Redaction at the provider boundary (`modules/redact.py`) |
| Jenkins | (none) | - | - | Removed in P.4: nothing left to classify |

### 15.2 What the checks found

**Grafana silences: what the API returns, and what the reader does today.**
- **What the API returns.** The reader asks Grafana's Alertmanager
  (`api/alertmanager/grafana/api/v2/alerts`) with no filter. That API's defaults return
  active, silenced and inhibited alerts alike, and a silenced one carries
  `status.state: "suppressed"` and `status.silencedBy: [<silence id>, …]`.
- **What the reader keeps.** The silence IDs, per instance.
- **What the screen draws.** The instance stays a Needs attention row, and its member line
  reads "silenced by <id>". Silencing does not remove it, because Grafana's rules view still
  reports the alert as firing: a silence stops notifications, not the alert.
- **The gaps:**
  - **The row shows the silence's ID, never who set it or until when.** Those come from the
    silence itself (`api/v2/silence/<id>`: `createdBy`, `endsAt`, `comment`), which the
    reader does not read.
  - **The recorded fixture holds no silenced alert,** so this path has never met real
    output. Capturing one needs a silence to exist, which is a write to Grafana: the
    operator's.
- **To build:**
  - the reader reads each referenced silence;
  - the row reads "silenced in Grafana by <createdBy> until <endsAt>: <comment>";
  - a test from a real captured silence.
- **BUILT 2026-09-30** (the operator: build it now, so the capture tests it):
  - the reader reads the silence LIST (`api/v2/silences`, one request per cycle rather than
    one per id), and puts each silence's author, end, comment, state and matchers on the
    instances it suppresses;
  - an id the list does not hold is kept and drawn as unresolved, never dropped;
  - the Needs attention row KEEPS its level, its title ends "(silenced in Grafana)", and its
    cause names who and until when;
  - the silence list read on the host was **empty**, so the test's silence object is the
    Alertmanager v2 API's documented shape, provisional until the operator's staged capture
    (plan, "Staged runs": the syslog test alert, `send log 2`, silenced briefly).

**NetBox drift: what is measurable today.**
- **The modification record** holds every write the NMAS made, with its before-state.
- **The census** compares object identity per type against a baseline, so it sees objects
  created or destroyed. It does not see an edit, because an in-place change alters neither
  id nor display.
- **The secret-storage reader** sees credentials in a stored context.
- **What none of them does:** see a person's EDIT made directly in NetBox. NetBox's own
  change log does record every edit, with user, time, object and before/after, and
  `nmas-netbox-untagged` already reads it. But **C100: the NMAS's token belongs to the
  operator's own account**, so the change log cannot tell the NMAS's edits from a person's
  by user.
- **Two ways to build the drift signal:**
  1. **Approximate, available today:** a change-log entry for an object the NMAS never
     recorded writing (no modification or created entry for that object within seconds of
     the change) is a write the NMAS did not make. Named on Needs attention with the object
     and what changed. It can misattribute a person's edit made in the same seconds as one
     of the NMAS's.
  2. **Exact:** give the NMAS its own NetBox account and token (C100, and 6.2's
     per-consumer accounts). Then any change-log entry by another user is drift, by
     construction.

  The screen draws either one the same way. The first is buildable now; the second is the
  clean end.

  **Decided (the operator, 2026-09-30): EXACT, never approximate.** A drift signal that cries
  wolf is how the drift checker was lost for 24 days, and guessing from timing will. So C100
  is done now: the NMAS gets its own NetBox account and token (the one-time steps are
  [SERVICE_ACCOUNTS.md](SERVICE_ACCOUNTS.md)). Then:
  - **drift is any change-log entry made by an account other than the NMAS's**, from the
    switch-over onwards (every earlier entry was made by one account for both, so it cannot
    be classified and is not);
  - **the NMAS's account name is ASKED of NetBox** (`api/authentication-check/`, measured on
    4.6.9), never stored in a setting that could go stale;
  - **each entry is a Needs attention row** naming the object, the fields that changed with
    both values (masked, C95), who changed it and when. Its one action: accept it as the new
    record (recorded with who and why), or, where the next import would overwrite the field
    from the golden, say so and offer the import's preview;
  - **the reader reads the change log whole** (paged to the end, a partial answer refused,
    rule 5 of the reader pattern), and NetBox's retention (`CHANGELOG_RETENTION`, 90 days by
    default) is the window it states;
  - **what it also buys:** the change log finally tells the NMAS's writes from the
    operator's, which adopt's records and C149's attribution both want.

**Kea: is anything beyond reservations worth doing?**
- **Reads:** yes. Pool utilisation (`statistic-get-all`), and lease lookups by MAC, address
  and hostname (`lease4-get-by-hw-address` is already used by onboarding).
- **Writes:** none. Subnets, pools and options are the network's design and live in Kea's
  main config (question 1). Releasing a lease can cut a managed device off (question 1).
  Clearing a stale lease for a host outside the inventory has one real use and the same
  risk if the host is misidentified: not worth it.
- **Reservation management needs one widening.** Today's writer serves ZTP onboarding, and
  the D4 posture check (no route or resolver options) belongs to the ZTP segment only. A
  reservation for a host on another subnet takes the writer's test, reload, read-back and
  restore, without D4's ZTP-specific conditions. Which subnets the NMAS's fragment may hold
  is a setting, per network (P.8). **Decided 2026-09-30, with the checks for the other
  subnets: section 14.2's DHCP list.**

**Containerlab node status:** no reader exists. The NMAS host has no SSH path to the lab host
by design (host commands are the operator's). The shape that fits:
- the lab host's own timer runs `containerlab inspect --format json`;
- it sends the result to the NMAS, as the clab sync already talks to it;
- a reader keeps it with its age.

### 15.3 Grafana: what the installed version allows, measured (2026-09-30)

Read-only, through the NMAS's own Grafana integration on the host: `api/health`,
`api/frontend/settings`, `api/access-control/user/permissions` for the NMAS's token,
`api/folders` and the silence list.

**The installed version:** Grafana **13.2.0, Open Source**. `auth.proxy` is off,
anonymous access is off, and the login form is on.

**The NMAS's own token has an Editor's permissions (C230).** 75 permissions, including:
- `alert.silences:create` and `:write`;
- `alert.rules:create`, `:write` and `:delete`;
- `dashboards:create`, `:write` and `:delete`;
- `folders:create`, `:write` and `:delete`.

There are no user, team or data-source-write permissions, which is the Editor's shape, not
the Admin's. The reader only reads, so the token should be a Viewer's. The switch is one of
the operator's one-time steps ([SERVICE_ACCOUNTS.md](SERVICE_ACCOUNTS.md)).

**Can folder permissions keep alert rules away from a direct-login Editor? No, not on this
version.** The scopes say why:
- `dashboards:*` and `folders:*` are granted ONLY per folder (`folders:uid:<x>`, from each
  folder's permissions), so a folder permission does govern dashboards.
- `alert.rules:*` and `alert.silences:*` are granted per folder AND on `folders:*`. The
  wildcard comes from the Editor role itself, not from any folder's permissions, so taking
  a folder's Edit away from the Editor role leaves every rule and silence permission in
  place.
- Changing what a basic role holds needs custom roles, which are Enterprise, not Open
  Source.

**What does keep rules out of reach: file provisioning.** Grafana refuses a UI or API edit
of a file-provisioned rule for every role. The nine heartbeat rules are provisioned that way
today (the ruler reports `provenance: file`). The seven hand-built ones are not, and were
last edited by accounts named `admin` and `nmas-automation`.
- **So P.7 generates every rule as a provisioned file**, and a rule the ruler reports
  without `provenance: file` is a Needs attention row.
- **Silences cannot be kept from an Editor on Open Source,** which is why a silence set in
  Grafana is shown, marked, with who and until when (15.2).

**The Viewer role's permissions on 13.2.0: not measured yet.** No Viewer credential exists.
When the operator's Viewer token for the NMAS exists,
`scripts/nmas-integration-accounts` prints its whole permission list: that list IS the
Viewer role on the installed version. It also names every create, write or delete it holds,
expected none. Until that has run, "Viewer cannot silence" is Grafana's documentation, not a
measurement.

**The `auth.proxy` design, for the embed (built after P.8):**
- **`grafana.ini`, the operator's, as root on the host:**
  - `[auth.proxy]`: `enabled = true`, `header_name = X-NMAS-Grafana-User`,
    `header_property = username`, `auto_sign_up = true`, `whitelist = <nmas-host>`;
  - `[users]`: `auto_assign_org_role = Viewer`;
  - `[server]`: `root_url` under the NMAS's `/grafana/`, and `serve_from_sub_path = true`;
  - `[security]`: `allow_embedding = true`.
- **The allowlist is the peer address Grafana sees.** Whether anything sits between the
  NMAS and Grafana (a reverse proxy on the monitoring host, which would make ITS address the
  peer) is measured when this is built, never assumed.
- **The NMAS proxy:** it strips any client-sent copy of the header, and sets
  `nmas:<verified email>`. That is a name in the NMAS's own namespace, so `auto_sign_up`
  creates a new Viewer and never logs in a direct-login account with its own role.
- **What job health checks, every cycle:**
  1. **The header from an address the allowlist does not name is NOT authenticated.** A
     canary request carries the header from a second source address. Which address can
     reach Grafana and is not on the allowlist is measured at build: the NMAS host has more
     than one address, and failing that the lab host's timer sends the canary.
  2. **A proxied identity holds no write.** The canary name's own permission list, asked
     through the proxy, contains no create, write or delete on alerts or dashboards. This
     is the Viewer role, re-verified on whatever version is running.
  3. **The NMAS's own token holds no write** (after C230's switch).
  4. **Before an embed is served to a person,** that person's proxied identity is asked the
     same question, and an embed is refused, naming the permission, if an administrator has
     raised the role inside Grafana since.

## 16. The findability questions, extended

Paths in the extended sidebar (14.1), counted as in section 2.2 (clicks from the landing
page; scent is the first click's label).

| # | The question | Path | Clicks | Scent |
|---|---|---|---|---|
| 21 | Show r3's CPU for the last day | Devices > r3 > Monitoring (the jump box: r3 > Monitoring) | 3 (2) | ✓ |
| 22 | What lease does h1 have? (a host, not a managed device) | DHCP > filter h1 | 2 | ✓ |
| 23 | Which prefixes are in the core VRF? | NetBox > Prefixes > filter VRF core | 3 | ✓ |
| 24 | Show the traps s2 sent today | Logs > filter s2, traps | 3 | ✓ |
| 25 | Is any alert firing, and which? | a Needs attention row each (0); the full list: Monitoring > Alerts | 0 (2) | ✓ |
| 26 | Reserve an address for a new host | DHCP > Reservations > Add reservation… | 3 | ✓ |
| 27 | What did Oxidized last fetch for r4, and does it differ from the golden? | Devices > r4 > History (Oxidized's copies beside the goldens) | 3 (2) | ✓ |
| 28 | Run a LogQL query | Logs > Query | 2 | ✓ |
| 29 | Run a PromQL query | Monitoring > Query | 2 | ✓ |
| 30 | Which cable connects r1 to s1? | NetBox > Cables > filter r1 | 3 | ✓ |
| 31 | Is the containerlab VM up? | Monitoring > Hosts | 2 | ~ ("Monitoring" for a host's status) |
| 32 | Who silenced the heartbeat alert, and until when? | its Needs attention row (0); Monitoring > Alerts | 0 (2) | ✓ |

**All thirty-two questions are the acceptance check on the built screens** (section 13):
- each built screen is walked with the questions it answers;
- the clicks are counted;
- any path longer than this brief's count is a finding, recorded before the screen is
  accepted.
