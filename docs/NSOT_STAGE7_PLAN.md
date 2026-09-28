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

Each task group from NSOT_TASKS.md lands in exactly one place:

| Destination | Answers | Task groups |
|---|---|---|
| **Needs attention** (the landing page) | *Is anything wrong, and does anything need me?* | A; and the "needs a person" half of C, D and E |
| **Fleet** | *Which devices, and what do I want to do to many of them?* | C (many), E |
| **Device** (`/device/<hostname>`) | *What is going on with this one device, and change it* | B, C (one), D (one) |
| **Versions** | *What changed, who changed it, and can I go back?* | D (baselines), F |
| **Source of truth** | *Are the templates, NetBox and credentials right?* | G, H (profiles), F (NetBox) |
| **Settings** | *How is the tool configured and connected?* | I, H (audits) |

**Why five and not the old two** (Fleet and Monitoring). Monitoring is no
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
cause.

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
2. **Monitoring, EMBEDDED** (section 3): this device's Grafana graphs and its
   logs, in place. Also its Oxidized fetch history and DHCP leases, rendered
   by the NMAS.
3. **Neighbours**: CDP, OSPF, BGP, tunnels, and each link's state. Per device
   only, by decision; a fleet topology is deferred (section 9).
4. **History, one timeline**:
   - intent commits;
   - deploys and their results;
   - goldens, labelled **a record, not a target**;
   - captures;
   - restores.
5. **Actions**, each through the preview-then-confirm pattern:
   - edit intent, or author it from a form (decision 2): the form is an
     input MODE of the one intent editor, committing through its route
     (section 6a);
   - **seed intent from a capture** (no usable path today: the commit route
     needs a verified person, so a curl from the host is refused. **R1
     measured, 2026-09-28, that EVERY onboarding lands here**: phase 1
     commits a bootstrap-shaped intent (`bootstrap`, `hostname`, `logging`,
     `secret_refs`), so an onboarded device cannot be deployed to from the
     interface until this exists, and C117's rollback run waits on it);
   - deploy;
   - restore to a golden or a ref (guarded, P.3);
   - **revert one intent commit** and **re-send a blocked change** (C118; was "retry after a rollback"; curl-only
     today);
   - rotate the credential (CLI-only today);
   - move files to or from flash, through the selection's implementation
     for one device (section 6a);
   - save to startup (ONE save: today's two, Save Device Config and Save to
     Startup, are one `write memory` with two implementations);
   - ask the device a question: the allowlisted command box, with history
     (absorbing quick actions), rendering and completion;
   - reload;
   - retire;
   - ~~the terminal~~: **REMOVED** (NSOT_FEATURE_AUDIT 3b, 2026-09-27,
     superseding 3a's read-only lens). A source of truth has no pane that
     goes to the device directly; the command box above is the one way to
     ask a device a question, and the break-glass path is the console
     runbook.

### 1d. Versions

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
     been pressed, and the terminal reads *"break-glass: not granted to
     you"*;
   - **approval screens show the separation-of-duties state** when that
     policy is on;
   - **the status bar shows the caller, their roles and their grants.**

   Until roles exist, the mode is `any_person`, and the same drawing code
   draws every control enabled for a person.

## 3. Grafana, embedded and central

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
| The page's file upload, download and delete / the selection's | many versus one, **two implementations** | the page calls the selection's (7.3) |
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
| **7.4** | Fleet: the bounded list and selection, batch deploy, bulk intent, onboard, adopt and retire, networks, and the inventory source. **Onboarding is designed for N address sources** (static, dhcp, ztp: P.6 lands first): the source choice is a LIST, not a toggle, and the pending-device row carries a per-source PROGRESS column (for ZTP: reservation written, config fetched, first seen). Cheap to design now, expensive to retrofit. |
| **7.5** | Versions: commits by actor and source (stating once *"N of M commits carry a verified identity"*, drawn beside its caveat: history carries known misstatements, listed by hash in `modules/nsot/record_exceptions.py` (the eleven rotation commits recorded `Source: manual`, C104; the two restores recorded `Source: pipeline`, C110; and the measured ABSENCE of agent-recorded first goldens, a checked negative). **It is the honest history of what the record got wrong, and the Versions screen draws from it rather than treating git as ground truth** (the operator, 2026-09-27): with C110 fixed, restore trailers mean something for the first time, and the screen must say which of the older ones do not. A screen stating a claim about history draws those exceptions next to the claim, with the rest marked *"recorded, not verified"*: D10, P.3 step 10), baselines with their reasons, re-applying one, the remote with connect |
| **7.6** | Source of truth: templates (the scheme-3 approval badge saying what it covers and what it does not, P.5; revoke, bindings, coverage, seed status), NetBox, credentials, freshness authorisations |
| **7.7** | Settings split, file-only settings listed, diagnostics |
| **7.8** | Removals, each with `check_removed_definitions.py` and a recorded reason, last so nothing goes before its replacement is on screen. **The Topology tab** (its built-in discovery, once 7.3's Neighbours carries it, and the topology-service panel, which goes with the deferred fleet view; C126). **The backup store retires only after section 6a's prerequisite** (the template preview and the two other renders read no backup), which is blocking, not a note |
| **7.9** | Configure forms: batch 1 (a parallel track, not blocking) |

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
reachable and never first. Nothing is summarised away. The preview's operands
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
    `nmas-rotate-credential`, `nmas-retire` and `nmas-persist-native`.
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
- **7.8 Removals**: the terminal, the Topology tab, and the backup store after
  its prerequisite.
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

- **A fleet topology view.** It EXISTS and WORKS today: the rcn-topology service's
  panel draws the fleet graph once `topology_service_url` is set (measured
  2026-09-28, `http://10.0.0.210:8088`). It is removed in 7.8 because the fleet
  view is deferred, not because it failed (C126). If a fleet view returns, it
  reuses that service rather than building something new. If it returns, it caps the devices shown, and
  networks can be organised into groups, with the view showing one group at a
  time. A topology of 200 devices is a picture nobody reads; one site's is
  useful.
- **Configure batches 2 and later**, beyond what the schema models.
- **Mode B** (removals through intent).
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
8. **Grafana:** the device page embeds that device's panels and logs, or
   names the prerequisite that failed. A blank frame fails.
9. **CI has no destination:** each CI state appears beside its trigger
   (NSOT_CI.md §5), and there is no CI tab.
10. **No subsystem tab:** the top-level navigation is exactly the five
    destinations plus Settings, and a test pins it.
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