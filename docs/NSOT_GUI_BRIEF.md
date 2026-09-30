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
  - the **status bar**: integration health and the live channel. **The running commit and its
    CI verdict left it on 2026-09-30** (the operator: the bar was cramped). They live under
    **Help > About** and in **Settings**, with the version. Their reason stays, as rows:
    **quiet when fine, loud when not.** Needs attention draws a row when the running commit
    is not CI-verified (the `ci-verdict` reader's failed or cancelled verdict, which is
    already a source), and a row when the host runs behind what has been pushed (the
    running commit is an ancestor of `origin/main` and not its tip, named with the count of
    commits behind and the deploy command). A mixed version stays the running-version row
    it is today;
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
- **Long-standing issues fold under the one line** (the operator, 2026-09-30; NSOT_PLAN P.7's
  two tiers): "Nothing needs attention · 1 long-standing issue", or beside the rows. Opened, each
  entry says what, which device, measured stable since when, its cause, and a link to its
  register finding and fix plan. It is shown once, never as a row competing with acute ones, and
  it disappears when the finding closes. An entry whose measurement leaves its recorded band says
  so and points at the acute alert. Monitoring conditions reach this page only as Grafana alert
  rules (acute) or these declared entries (chronic), never from a panel's colour.
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
- **A control that starts work shows it is busy ON ITSELF, and the result updates in place**
  (the operator, 2026-09-30, on About's Check again, the rule for every v2 control):
  - The button's own label says it is working ("Checking…"), and it stays disabled until the
    work reports back, never on a timer.
  - Nothing is narrated beside the control while it runs.
  - The result is the confirmation: the row's timestamp reads "just now".
  - The row carries no provenance ("checked on your request") unless it changes what the
    person should do. The cause and the duration stay recorded (the store's run history, the
    log line) and are on hover (the timestamp's title) for diagnosis.
  - Words appear beside a control only when the person must act: a refusal, a failure, or an
    answer later than its bound.
  - A multi-step operation's progress display (the Update page's stepper) is its result drawn
    in place, not narration.
- **A toast only ANNOUNCES; it never holds a result** (the operator, 2026-09-30):
  - A toast is for a result the person might miss: something finishing where they are not
    looking.
  - It always links to a result that stays (the in-flight panel's finished row, a receipt,
    the page the result is drawn on).
  - A toast never duplicates something already visible in place.
  - **A failure is never toast-only** (C84): it is drawn where the person can read it again.
  - Measured 2026-09-30: the v2 screens make no toast call at all. The 138 `showToast` calls
    are in 21 of today's scripts, which the redesign replaces; C121's declared-green scan
    governs those until then. A test holds the v2 screens to this rule, so the first v2
    toast must arrive with its link.
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

### 9b. The costing, after the mockups (step c, 2026-09-30)

**The question** (the operator): does the current stack build the mockups WELL, not merely
possibly? And if not, what does the alternative cost, honestly? Three options, judged
against the screens the mockups actually hold.

**What was measured first (2026-09-30):**
- **Front end today:** 41 script files, 9,552 lines, plus 8,406 lines of templates. 67 test
  files read or EXECUTE the shipped JavaScript, most of them in duktape, which runs
  ECMAScript 5.1 only.
- **The Content-Security-Policy** (`modules/csp.py`): `script-src 'self' 'unsafe-inline'`,
  with no `unsafe-eval`. Inline handlers keep `unsafe-inline` there (about 300 to migrate).
- **Node:** absent on the laptop and in CI. On the host, node 18.19.1 from apt, with no npm.
- **Vendoring:** every front-end library is hash-pinned in `static/js/vendor/MANIFEST.json`
  and checked against its registry (C123). Nothing loads from a CDN.

**The screens, sorted by what they demand of a stack:**
- **Server-shaped (the large majority):** Needs attention, Devices, History, the NetBox
  browser, the DHCP lists, Templates, Credentials, Settings, the manual and its side panel,
  every preview-confirm-result, the running stepper, and the device page's tabs other than
  Monitoring. These are lists, filters, paged tables, forms and fragments that change when
  the server announces something (the live-data contract).
- **Client-shaped (two islands):**
  - **the native panel renderer:** uPlot charts, stat, gauge, bar gauge, table and logs
    panels, the variables bar, units, thresholds and overrides, lazy rendering for a
    124-panel dashboard;
  - **the query builder:** a form whose state produces query text live, with templates and
    saved queries.

**Option A: server-rendered Jinja components, htmx for fragments, Alpine for local state,
and two ES-module islands. No build step.**
- **How each screen is built:**
  - **Server-shaped screens:** a Jinja macro per component rule (section 6). htmx swaps
    fragments, and a filter or a page is a URL. A panel re-fetches its fragment when the
    socket announces its key: `nmas_invalidation.js` stays, and dispatches a DOM event htmx
    listens for. The side help panel is an htmx fetch of a manual section.
  - **The stepper:** a server fragment, re-rendered on each progress announcement, so its
    steps come from the code's own list by construction, with no client model to drift.
  - **Menus, tabs, disclosure, the selection bar:** Alpine.
  - **The islands:** vanilla ES modules over uPlot. The builder is an Alpine component with
    a small query model.
- **What it adds:** htmx, Alpine (its CSP build), uPlot and the IBM Plex fonts, each
  vendored and hash-pinned.
- **The honest costs:**
  1. **CSP:** Alpine's standard build evaluates expressions with `new Function`, which
     needs `unsafe-eval`. Its CSP build does not, and restricts attributes to names
     registered with `Alpine.data`, so it is more verbose. htmx is configured with
     `allowEval: false` and without `hx-on`. The other side: because every page is rebuilt,
     the inline handlers go page by page, so `script-src` can finally drop
     `unsafe-inline`. That is a security gain the current pages cannot reach cheaply.
  2. **The mechanised checks change readers.** The payload-to-render, results-drawn,
     invalidation and concepts checks read JavaScript renderers today. With rendering on the
     server they read HTML fragments from the test client instead. That is stronger (the
     test sees what the browser gets, with no duktape stub), but each check's reader is
     rewritten, and its floors and controls re-proven. That is the largest cost in A.
  3. **The islands need a modern engine to test.** Duktape cannot run ES2015 modules or
     uPlot. Node goes into CI and onto the laptop; the host has it. The islands' pure parts
     are tested in node: unit formatting, threshold colours, variable interpolation, and the
     builder's model-to-text. Drawing is the library's, and is judged by a person.
  4. **Bootstrap:** the mockups' design system does not need it, and its CSS fights the
     tokens. It is retired page by page, with Alpine and the `<dialog>` element in place of
     its modals and dropdowns. CLAUDE.md's "Bootstrap 5 only" convention is rewritten when
     this is decided.
- **The islands' size, from the measured dashboards:**
  - **The panel renderer:** seven panel types, dashboard variables (319 of 343 queries use
    one), units, thresholds and overrides, the `gridPos` layout and its phone collapse, lazy
    rendering, and the embedded fallback. A few thousand lines of JavaScript, plus a Python
    route that builds each `api/ds/query` request from the stored dashboard model (the
    browser names a dashboard and a panel, never a raw query, on this path), with its bounds.
  - **The dashboard models:** a reader job, as every outside read is.
  - **The builder:** smaller, because it never parses hand-written PromQL back into controls.
    It says which parts it no longer understands.

**Option B: a single-page framework (React, Vue or Svelte) with a build step.**
- **What it buys:** a component model on the client, client-side navigation without a
  round trip, and a larger ecosystem of components.
- **What it costs:**
  1. **Every screen rewritten as components,** and the back end made JSON-only where it
     renders pages today.
  2. **The guarantees rebuilt in a second test stack.** The 67 test files that read or
     execute the shipped pages are retired. The mechanised checks built on them (payload to
     render, reachability, requests resolve, results drawn, concepts taught) are rebuilt for
     components, or lost. They are where C55, C85, C121 and others were caught.
- **What it does better, for these mockups:** tab changes without a round trip (htmx's
  partial swap is one LAN request), and richer client state in the two islands. The islands
  are the same work in either option, because uPlot is imperative and the renderer is its
  own logic either way.

**Option C: server rendering, with the islands as Preact and htm ES modules, no build step.**
Like A, but the islands get a component model with no bundler (both vendored, about 10 KB).
It is worth choosing only if the builder's state outgrows an Alpine component. The spike
below decides.

**Corrected by the operator (2026-09-30): two reasons removed from B's costs, because they are
not the kind that decide a front end.** "None of the machines has npm" is an environment
convenience; npm can be installed. And "a bundler's dependency tree cannot be hash-pinned"
was wrong: npm's lockfile records an integrity hash for every package. Neither weighs
against B any longer.

**Recommendation: A**, with C held for the islands if the spike shows the builder needs it.
The argument that carries it is the front-end one:
- **The large majority of the screens are server-shaped** (lists, forms, paged tables and
  fragments that change when the server announces), and A builds exactly those well.
- **The two client-heavy pieces, the panel renderer and the query builder, are separate
  modules in every option,** so a framework's component model buys little where the
  screens are hard.
- **Nothing in the mockups is built worse by A,** so "rather rewire than ship a compromise"
  does not argue for B.

Secondary, and not deciding: A keeps the mechanised checks reading what the browser gets,
and it is the route to `script-src` without `unsafe-inline`.

**The spike: APPROVED (the operator, 2026-09-30).** Build the device page's Overview and its
Monitoring tab in A, in the real app with real data, rendering `rcn-lab1-snmp`'s device
panels natively. **It is judged FIRST on what the operator judges it on:**
- does it look like the mockup;
- do the menus and the live updates feel smooth;
- does it work well on the operator's phone.

**Then on the technical measures:** page weight, the CSP (no `unsafe-eval`), lines of code,
and whether the tests catch a planted defect. The operator uses it and decides before the
rest of the redesign commits to A. If A builds it badly, the spike says where, and B or C is
costed against that screen rather than argued in general.

**No time forecast yet, deliberately.** A forecast is made from a finished stage of the same
kind (NSOT_WRITEUP's rule), and no front-end rebuild has finished here. The spike is the
first measurement, and the forecast follows from it.

**The spike, BUILT (2026-09-30), awaiting the operator's use.** At `/v2/device/<name>`, beside
today's page, which it does not replace. The Overview (answering, committed intent and golden,
the four checks) and the Monitoring tab (the dashboard selector, 1h/6h/24h/7d and a typed
relative range, each Monitoring state in its own words, the device panels drawn natively
with uPlot, the rest listed with why). The other six tabs are drawn disabled; the Actions menu
and "Plan a deploy" open today's device page. Live updates: the reachability badge, the
Overview's checks, the top bar's integration strip and the Monitoring tab re-fetch when their
reader announces; the panels re-read every 30 s while the page is visible. Not in the spike:
the absolute from-to range (relative only), Help > About, and the dark theme.
**The technical measures:**
- **Page weight:** first load 192 KB compressed (the fonts 98 KB of it), of which 2 KB is
  re-sent on each load and the rest cached; today's `/` is 558 KB compressed, 70 KB re-sent
  each load.
- **CSP:** `script-src 'self'` and `style-src 'self'`, no `unsafe-inline`, no `unsafe-eval`,
  on the page and every fragment (`csp.STRICT_POLICY`); a test finds no inline script, style
  or handler in anything rendered.
- **Lines:** about 1,830 of program (Python 850, templates 300, CSS 260, JavaScript 425),
  500 of tests, and a 110-line vendoring script; htmx, Alpine (CSP build), uPlot and the IBM
  Plex fonts vendored with each tarball's sha512 checked against the registry.
- **Planted defects: 10 of 10 caught**, each failing only the tests aimed at it: every panel
  drawn, a panel served that the page does not draw, an inline style, a gap drawn as zero,
  the policy dropped, C232's notice removed, an unapproved copy read as fine, a value drawn as
  markup, an over-long range trimmed, the chosen range ignored. The last was first caught only
  by accident (through the refusal test), so a direct test was added and it now fires on its
  own.
**What the operator sees first on the host:** the device dashboard setting is empty, so
Monitoring says "No device dashboard is set" until `grafana_device_dashboard_uid` is set to
`rcn-lab1-snmp`; after that, "the variable lists no devices at all" (C232) until either fix
lands, and the panels answer empty.

**OPTION A: APPROVED (the operator, 2026-09-30, after using the spike on desktop and phone: "it
feels good", the deciding check).** The redesign is built in A. The review's fixes:
- **Identity:** the page drew the operator as `unauthenticated` (C233). The chip read the
  gate-only actor, and a GET page is never gated. Every v2 page and fragment now draws
  `identity.viewer()`, the same `identify()` as `/identity/status`, tested with the refusal
  cases. This had to hold before any gated action moves to v2.
- **Model and platform** under the name, each with its source: the model from the committed
  golden's own header (`Chassis type: C8000V`; a vIOS switch reports none, so its image line,
  `vios_l2`, said as such); the platform from the inventory. NetBox is not read for it: its
  import records `Unknown` for a model built from a golden.
- **Layout:** each panel at its own `gridPos` (column, width, height) under its Grafana row
  heading, collapsing to one column only at phone width. Nothing is invented. In
  `rcn-lab1-snmp` every device panel is full width in Grafana too, and "Devices offline"
  keeps its place beside the panel left out.
- **The selector** says "1 of 5 dashboards can show a single device", and its menu lists the
  others with why (no `device` variable).
- **C232, at the source:** the scrape targets generated from the inventory with `device` and
  `role` (docs/PROMETHEUS_TARGETS.md), pulled forward from P.7.

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
- **Native panels: EVERY panel of every dashboard, rendered from the dashboard's own
  definition** (the operator, 2026-09-30, replacing "the key ones only"). Nothing is
  hand-drawn and no chart set is chosen by us. The app reads each dashboard's JSON model from
  Grafana (`api/dashboards/uid/<uid>`) and renders every panel from it, so a panel added in
  Grafana appears in the app with no code change.
  - **Measured on the host (2026-09-30, read-only):** 5 dashboards, 170 panels.
    | Panel type | Panels | Drawn |
    |---|---|---|
    | timeseries | 125 | natively (uPlot) |
    | stat | 19 | natively |
    | gauge | 7 | natively |
    | bargauge | 6 | natively |
    | table | 3 | natively |
    | logs | 3 | natively, by the Logs component (masked, question 4) |
    | alertlist | 1 | natively, by the Alerts component |
    | state-timeline | 1 | embedded, labelled |
    | text | 1 | embedded, labelled (a text panel can hold HTML; rendering it in the app's origin is a script-injection surface) |
    So 168 of 170 draw natively, and the two that do not fall back to that one panel
    embedded (`/grafana/d-solo/...`), labelled "shown by Grafana: this panel type has no
    native renderer".
  - **The queries run through Grafana, never around it.** Each panel's targets go to
    Grafana's own query endpoint (`api/ds/query`) with the Viewer token, exactly as
    Grafana's front end runs them. So a panel's data source, its UID and its query need no
    second configuration in the NMAS, and C167 (`prometheus_url` empty) stops mattering.
    Measured: the data-source proxy answers the token for all three sources (Loki, and
    two Prometheus instances, one of them Thanos). The usual bounds apply per query: range
    cap, minimum step, series and point limits, a timeout.
  - **What the renderer must handle, from the same measurement:**
    - **dashboard variables:** 319 of the 343 queries use a `$variable` (data source,
      query, ad hoc and text-box variables). A query variable is resolved by its own
      query, and the variables bar is drawn above the panels. This is the largest part;
    - **units and thresholds:** 141 panels carry thresholds and 55 carry field overrides,
      which decide colours and units. Read and applied, never ignored, or a stat reads the
      wrong colour;
    - **transformations:** 1 panel. Declared unsupported and embedded, until a second
      panel needs one;
    - **layout:** each panel's grid position (`gridPos`) and its rows, collapsed or not.
      At phone width the grid becomes one column in the same order.
  - **Why native at all, when the embed shows every panel:** it works at phone width,
    matches the design, carries the live-data contract's age stamp, masks log lines, and
    is the ONE renderer the device page's Monitoring tab reuses (the same dashboards,
    filtered by the device variable).
  - **Cost:** costed in section 9b, as a real renderer.
- **WHICH dashboards: two roles, two settings, by UID** (the operator, 2026-09-30: never
  specified until then).
  - **What each piece of work used, stated because it was asked.** The inventory probe read
    all five dashboards (the 170 panels above). No fixture holds a dashboard. The first
    Services mockups drew no dashboard at all: their charts were chosen by hand, which
    is what this section replaces. The revised mockups draw Monitoring from
    `rcn-lab-overview`'s real panels and the device page from `rcn-lab1-snmp`'s, read on
    the host.
  - **The FLEET dashboard, for the Monitoring page.** A per-network setting names the
    default by UID (for Default: `rcn-lab-overview`, "RCN Lab — Monitoring, Telemetry,
    Alerting and Data Lake"). The page carries a selector listing every dashboard Grafana
    holds, from its search API (`api/search?type=dash-db`, five today). Choosing one
    changes the VIEW, never the default.
  - **The DEVICE dashboard, for the device page's Monitoring section.** A dashboard with a
    device template variable, named by UID (for Default: `rcn-lab1-snmp`, "RCN Lab 1 -
    SNMP per device"), and a second setting naming the VARIABLE the app sets (for Default:
    `device`, whose values come from `label_values(ifOperStatus{role=~"$role"}, device)`).
    - **Only panels whose queries use the variable are drawn** (4 of `rcn-lab1-snmp`'s 8:
      Devices offline, throughput, interface state, errors and discards; first counted as
      3, missing the regex form, and corrected the same day). A panel that does not select one
      device shows the fleet, and drawing it under one device's name would be a wrong thing
      that looks right. The count left out is stated, and they are on Monitoring.
    - **A device dashboard with no such variable** draws no panels and says so on the
      device page, naming the dashboard, the variable it lacks, and Settings. It never
      falls back to the whole fleet.
    - **A device the variable's values do not list** (Prometheus has never seen it) is its
      own state: "Prometheus holds no series for r7", never an empty chart.
    - **A selector on the device page too** (the operator, 2026-09-30), listing ONLY the
      dashboards that have the configured device variable, defaulting to the setting, and
      changing the view, never the default: the Monitoring page's behaviour.
    - **The excluded panels are listed, each with its reason** ("this panel's query does not
      select by device", naming the query), so the operator can fix them in Grafana; a
      fixed panel then appears on every device page with no change here. For
      `rcn-lab1-snmp`, measured: Devices online, Interface History, CPU Utilization (5 min
      avg) and LinkDown Logs. The rule is mechanical: a panel is drawn when a query
      references the variable (`device="$device"`, or `device=~"$device"`, which with one
      device set selects that device).
  - **By UID, never by title**, so a rename in Grafana breaks nothing. A configured UID that
    Grafana no longer holds is a **Needs attention row** naming the setting, the UID and the
    dashboards it does hold, never a blank panel.
  - **Both are per-network settings after P.8**, since another lab's Grafana has its own
    dashboards. They replace `grafana_device_dashboard_url` (today a link template with
    `{hostname}`, read only by the integration card's link), which is kept in the schema
    as keys always are and read by nothing once the device dashboard is set.
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
  - **At phone width the embed is not offered:** the native panels are the phone's
    monitoring, and a panel that only embeds says so in its place.
- **Alerts:** every firing instance with its rule, device, onset and state, and its silence
  (question 3 below). Needs attention stays the place a person is told; this is the full
  list.
  - **A "How to fix" column, now (the operator, 2026-09-30).** Every rule P.7 generates
    declares its own remedy in its annotations (`description`, and `runbook_url` where a
    manual page exists), written with the rule by its generator: the same principle as
    Needs attention's action field. The reader already reads the ruler, so the column
    costs a field. A rule with no declared remedy says **"no remedy declared for this
    rule"**, never an invented one; today that is every hand-built rule, and it is drawn
    so.
  - **"Investigate", at Stage 8 (8.6).** An action on each alert, and automatic
    investigation of a new incident, with the AI's notes in the alert's row. The notes are
    labelled AI-generated and list the queries the agent ran; its tools are read-only (it
    suggests, never acts); a note never hides, dismisses or downgrades the alert; one
    investigation per incident, grouped as the reader groups them. **It sits behind Stage
    8's first real tool run**: the agent has never called a tool. The mockup draws the
    column as Stage 8's, empty.
- **Query, for PromQL and LogQL (the operator, 2026-09-30):**
  - **A builder for a person who does not know the syntax,** populated from the real names:
    metric names, label names and label values from Prometheus's metadata API (755 metric
    names, measured) and Loki's (labels `filename`, `host`, `job`, `service_name`,
    measured), both read through Grafana's data-source proxy.
    - **Loki has no `device` label** (the stream's `host` is the collector, C166), so the
      builder's "device" is the ONE origin-id filter (`ORIGIN_ID_PATTERN`), never a label it
      does not have.
  - **Templates for common questions:** "CPU of device X", "interface errors on device X",
    "syslog severity 0 to 2 from device X", "which devices stopped heartbeating".
  - **The query is SHOWN as it is built,** beside the controls, updating on each choice, so a
    person learns the syntax by watching it form; it can be edited by hand at any point, and
    the builder then says which parts it no longer understands rather than silently
    discarding them.
  - **Saved queries,** per network after P.8, runnable in one click and pinnable to a device
    page (they appear in that device's Monitoring or Logs tab).
  - **Both pass all five questions:** a query reads; masking applies to log lines; every
    query is bounded (range, step, series and line limits, a timeout).
- **Time ranges: presets, plus a custom range** (the operator, 2026-09-30: 15 min / 1 h /
  24 h / 7 d is not enough). One picker serves the dashboards, the query screens and the
  device page.
  - **Relative:** "last N minutes, hours or days", typed (`last 90 minutes`, `last 3 days`).
  - **Absolute:** a from and a to, each a date and a time, shown in UTC with the browser's
    local time beside it.
  - **Bounded, with the limits said on the picker, measured on the host (2026-09-30):**
    | Backend | Longest range it serves | Other limits |
    |---|---|---|
    | Loki 3.3 | 30 days 1 hour (`max_query_length: 30d1h`); logs are kept 30 days (`retention_period: 30d`) | 5,000 lines a query (`max_entries_limit_per_query`), 500 series, a 1-minute timeout, split by the hour |
    | Prometheus 2.45 | its retention, 90 days or 100 GiB | 50,000,000 samples a query, a 2-minute timeout, and Prometheus's own 11,000 points per series |
    | Thanos 0.37 (the data lake) | its retention, not measured (the compactor's configuration is not readable through Grafana) | a 2-minute timeout |
  - **The step widens with the range,** so a long range never asks for an unmanageable
    series: step = the range divided by at most 1,000 points, rounded up to a readable unit
    (15 s at 1 hour, 2 minutes at 24 hours, 15 minutes at 7 days, 1 hour at 30 days, 3 hours
    at 90 days), never below the data source's scrape interval. The step in use is shown
    beside the range.
  - **A range past a limit is REFUSED, naming the limit** ("Loki serves at most 30 days 1
    hour; this range is 45 days"), never silently trimmed: a trimmed answer reads as the
    whole range.
- **Live topology, on the Monitoring page (the operator, 2026-09-30).**
  - **Why the dashboard's topology panel does not render, measured.** `rcn-lab-overview`'s
    "Live topology (NetworkX / LLDP)" is an HTML text panel. Its `<img>` points at the
    topology service's PUBLIC tunnel hostname (`topology.<domain>/topology.svg?cb=$__to`),
    not at port 8088. From outside the LAN that URL answers 200 with the SVG and no login,
    so the reachability guess was not the cause. It does not render in the app for two
    reasons of the app's own: text panels are never run in the app's page (the renderer's
    rule above), and the app's CSP (`img-src 'self' data: blob:`) would refuse the
    cross-origin image anyway. If it is also blank inside Grafana itself, the discriminator
    is opening that image URL alone in the same browser. The public URL is its own finding
    (C231: the network's map on the internet, no login).
  - **The two options, costed:**
    - **(a) The service's SVG, fetched server-side through the reader pattern.**
      `/topology/service/svg` already fetches it on the LAN per request; as a reader job
      (every 60 s) it gains an age stamp and stops costing a request. Small: a reader
      declaration and a stamp. What it cannot do: no click to a device, no alert on a node,
      the service's dark palette inside the design system, and a 1100 x 720 picture whose
      labels are unreadable at phone width.
    - **(b) A native, interactive map drawn by the app.** The data already exists without a
      single device read: the topology service's `/graph.json` (measured: nodes with
      addresses, and 11 edges with the port on each end, discovered by LLDP, with the time it
      was generated), Prometheus's `ifOperStatus` for each link's state (73 series), the
      reachability reader's `STATUS`, and the Grafana reader's incidents. So the service stays
      the ONE owner of discovery (the reason `topology_view.py` exists: a second
      implementation of discovery is the wrong move), and the app draws.
      - **What it shows:** each node's answering state, its firing alerts as a count badge, and
        each link's state from both ends' `ifOperStatus`, the ports named on hover or tap.
        Click or tap a node to open its device page.
      - **The population is the inventory, not the graph** (the drift checker's lesson). A
        managed device the graph lacks (r6 and edge1 today) is drawn apart, labelled "no LLDP
        neighbour seen"; a graph node that is not managed (r5, retired) is drawn muted and
        labelled "not managed".
      - **At phone width** it becomes a list of devices with their links, since a graph at
        390 px is decoration. The same data, drawn as rows.
      - **Cost:** a reader job for `graph.json` (60 s), one route composing the four sources,
        and the drawing on vis-network, which is already vendored and hash-pinned, with a
        layout pinned by node id so the map does not rearrange on every refresh. Moderate:
        the library, the data and the discovery already exist.
  - **Recommendation: (b),** for the reasons the operator gave: it is the one-stop shop
    (a click reaches the device, an alert shows where it is) and it is drawn in the design
    system. (a)'s reader is not built separately, because (b) reads the same service.
- **Hosts:** Proxmox VMs (the existing read-only client) and containerlab nodes, whose status
  needs a new read-only reader (section 15.2).

**Logs (Loki):**
- **Fleet-wide:** time range, device, severity, facility, traps or syslog, and text.
- **Per device:** selected by the device's OWN origin-id, never rsyslog's hostname (C13,
  C166).
- **A LogQL query screen, with the builder** (the Query item under Monitoring, above): the
  same builder and saved queries, for LogQL.
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
  is observed, not Kea's. (Kea's legal-log hook would be the alternative, and the host's
  package does not ship it: measured 2026-09-30, the hooks directory holds bootp,
  flex_option, ha, lease_cmds, mysql_cb, pgsql_cb, run_script and stat_cmds.)

**The DHCP page's tabs are one set, present while a preview is open** (the operator,
2026-09-30): Subnets, Active leases, Reservations, Pools, Lease history. A reservation's
preview opens beside them, and shows the POOL CONTEXT its checks are about: the subnet's
pools as a strip, where the address falls against them, and the nearest pool named ("::20 is
below the pool ::100 to ::200; no clash").

**IPv6 alongside IPv4, everywhere (the operator, 2026-09-30).** The first mockup drew IPv4
alone, and that was a gap: VLAN 30 is IPv6-only and Kea's DHCPv6 is running. Measured on the
host the same day: kea-dhcp6 2.4.1 serves `2001:db8:10::/64`, `2001:db8:20::/64` and
`2001:db8:30::/64`, each with a pool and relayed, and listens on the management interface.
- Subnets, pools, utilisation and leases are drawn for both families in one list, each
  labelled IPv4 or IPv6; a filter narrows to one.
- **Reservations by DUID for IPv6** (a client's DHCPv6 identity), by MAC for IPv4. The
  checks are the same per family: inside the subnet, no clash with a pool or another
  reservation, never a managed device's address unless the reservation is for it.
- **The ZTP segment has no IPv6 subnet today** (measured), so ZTP stays IPv4, and the
  screen says so rather than offering an IPv6 ZTP reservation.

**Creating and editing POOLS: yes, with gates (the operator, 2026-09-30).** A pool changes
the network's addressing, so under question 1 it goes through preview, confirm and result,
recorded as the person, never a plain form.
- **The checks:**
  - the pool is inside its subnet;
  - it overlaps no existing pool, no reservation, and no statically assigned address (read
    from NetBox's IP addresses and every managed device's golden: a range someone
    configured by hand on an interface is the case a DHCP server cannot see);
  - **NEVER a pool on the ZTP segment.** That segment deliberately has none, so only a
    device the tool reserved gets an address there (D4). The screen offers no Add there,
    and the writer refuses it by name if asked anyway;
  - the subnet is on the network's list of subnets the tool may write (the same setting as
    reservations, after P.8).
- **Where the tool's pools live: its own fragment file, as reservations do.** Pools already
  in Kea's main config stay visible, marked, and read-only.
- **How Kea's include mechanism supports that** (measured and read, 2026-09-30):
  - **What is there today:** the reservation fragment is included as a VALUE:
    `"reservations": <?include "/etc/kea/nmas/reservations-255.json"?>` in
    `kea-dhcp4.conf`. Nothing else in either config uses an include; `kea-dhcp6.conf` uses
    none.
  - **What the include is:** Kea's `<?include "path"?>` is a TEXTUAL inclusion done before
    parsing. It can stand wherever the included text makes valid JSON: as a whole value (a
    subnet's `"pools": <?include ...?>`), or spliced into a list beside elements written
    in the main file.
  - **The API route is closed on this package:** no `subnet_cmds` hook (so no
    `subnet4-delta-add`), no `host_cmds`, and no config backend configured
    (`config-control` absent). So a pool is written the way a reservation is: the candidate
    tested with `kea-dhcp4 -t` / `kea-dhcp6 -t` before the live fragment is touched, then
    `config-reload`, then a read-back of the running config naming both operands, and the old
    fragment restored on failure.
  - **Two shapes, and the choice waits on a measurement:**
    1. **A tool-owned subnet's pools as a whole value** (`"pools": <?include
       "nmas/pools-<family>-<id>.json"?>`). Safe to parse, and the file is the whole list.
       But it means the subnet has no main-config pools, so a subnet with existing pools
       must have them moved into the fragment once, by the operator, as the reservation
       include was put in once.
    2. **Tool pools spliced beside main-config pools** (`"pools": [ {...}, <?include ...?> ]`).
       Keeps main-config pools where they are, and depends on how Kea's parser treats the
       join: an empty fragment leaves a trailing comma.
- **What to measure first:**
  - whether kea-dhcp4 and kea-dhcp6 2.4.1 accept a trailing comma inside a list, and an
    empty spliced fragment: a candidate file tested with `kea-dhcp4 -t` and `-t` for v6,
    never the live config;
  - which subnets carry main-config pools the operator would rather keep in the main file
    (today: 10, 20 on v4; 10, 20, 30 on v6);
  - `kea-dhcp6 -t` under AppArmor with a `0644` fragment, as D1 measured for v4 (a confined
    root process is held to the mode bits);
  - that `config-reload` on dhcp6 picks a changed fragment up, as M5 measured for v4.

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

### 14.3 The monitoring profile's screens (designed 2026-09-30; NSOT_PLAN P.9)

The design is [MONITORING_PROFILE.md](MONITORING_PROFILE.md). What a person sees:

- **The device page's Monitoring section opens with what the device is monitored by:** SNMP,
  syslog, the heartbeat, telemetry and IP SLA, each read from its committed golden. It shows
  "excluded, because ..." where the device's intent excludes a section, and "Apply monitoring
  profile..." when anything is missing.
- **The profile's preview has three groups:**
  - inherited from the profile, and will be sent (each line with the section and connector it
    comes from);
  - already in place;
  - superseded on the device: each old monitoring line the profile replaces, with a box to
    remove it (Mode B) and a reason field. A shape not measured on the platform has its box
    disabled, with the reason beside it.
  The result is the deploy's.
- **Onboarding's Verify and adopt's preview** draw the same groups for a new device, before
  the confirm.
- **Monitoring > Coverage:** devices by integration, the cells from committed goldens. Select
  several and "Apply monitoring profile" opens one batch preview with the rollout order drawn.
- **The intent editor** draws inherited values in their own style, labelled "from the
  profile". An override reads "overrides the profile", and an exclusion shows its reason.
- **Needs attention:** one row per device not covered, "r6 is not monitored by SNMP: its
  configuration has no SNMP community", with the profile as its action (built, and until P.9
  exists it says the action is planned).

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
| Prometheus, Loki | The query builder, its templates, saved queries (per network, pinnable to a device page) | **Freely** | passes all five (the operator, 2026-09-30) | Names from the metadata APIs through Grafana's data-source proxy; the same bounds; log lines masked |
| Grafana | Every dashboard panel, rendered natively from its JSON model | **Freely** | passes all five | Queries through Grafana's `api/ds/query` as Viewer, bounded; an unrenderable type embedded, labelled |
| Grafana | A rule's declared remedy ("How to fix") | **Freely** | passes all five | Written only by P.7's generator; none declared says so |
| Prometheus | Scrape targets | Not in the app | Q2 (they decide what evidence exists) | **Corrected:** nothing generates them today. They are Prometheus's own config on its host, hand-maintained, and retire only warns about a target still scraping an address (C229). **Decided 2026-09-30: P.7 generates them from the inventory beside the alert rules**, so a new device is scraped and a retired one is not, with nobody editing a file on the Prometheus host |
| Grafana | Dashboards; alert state, including silences | **Freely** | passes all five | Embedded as Viewer (section 14.2), through `auth.proxy` whose allowlist names only the NMAS (15.3) |
| Grafana | Creating and editing dashboards | Not in the app: **in Grafana directly**, by a direct login | Q3: on 13.2.0 the role that edits dashboards also silences and edits rules (15.3) | Grafana's own authentication |
| Grafana | Silencing, acknowledging to hide | Not in the app | Q3 | - |
| Grafana | Editing alert rules | Not in the app | Q2, Q3 (C168: the hand-built ones were wrong) | Generated only by P.7's generators, **as file-provisioned rules**: Grafana refuses a UI or API edit of those for every role (the heartbeat rules are provisioned so today, measured). A folder permission cannot do this on 13.2.0 (15.3) |
| Grafana | A silence set INSIDE Grafana | Shown, never hidden | Q3 | The alert stays on screen as active, marked "silenced in Grafana", with who and until when: **built 2026-09-30** (15.2) |
| Kea | Subnets, pools, utilisation, leases, lookups by MAC, address or hostname | **Freely** | passes all five | Q5: paged reads |
| Kea | Add, edit, remove a reservation | **With gates**, on the subnets a per-network setting lists (after P.8) | Q1 (it decides a device's address) | The existing writer: its own fragment file only (`<?include?>`), a candidate tested with `kea-dhcp4 -t`, reload, a read-back naming both operands, restore on failure. The D4 posture checks on the ZTP segment only; elsewhere, inside the subnet, no clash with a pool or reservation, and never a managed device's management address unless the reservation is for that device (14.2). Preview, confirm and result, recorded as the person |
| Kea | Reservations in Kea's main config | Shown, marked, read-only | Q2 | - |
| Kea | IPv6: subnets, pools, leases, reservations by DUID | As IPv4, row by row | the same questions as each IPv4 row | Added 2026-09-30: kea-dhcp6 serves three subnets (measured) |
| Kea | Creating and editing POOLS | **With gates** (moved 2026-09-30 from "not in the app") | Q1: it changes the network's addressing, so it takes the gates, not a refusal | The tool's own fragment file only; inside the subnet; no overlap with a pool, a reservation or a statically assigned address; **never on the ZTP segment** (D4); a subnet on the network's list; candidate tested (`kea-dhcp4 -t` / `kea-dhcp6 -t`), reload, read-back, restore on failure; preview, confirm and result, recorded as the person (14.2) |
| Kea | Pools already in Kea's main config | Shown, marked, read-only | Q2 | - |
| Kea | Editing Kea's main config (subnets, options) | Not in the app | Q1 (the network's design) | Pools moved out of this row, above |
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
