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
  are pinned by `test_scale.py`.
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

One page per device. The header carries identity, platform, network, status,
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
   - edit intent, or author it from a form (decision 2);
   - **seed intent from a capture** (curl-only today);
   - deploy;
   - restore to a golden or a ref (guarded, P.3);
   - **revert one intent commit** and **retry after a rollback** (curl-only
     today);
   - rotate the credential (CLI-only today);
   - move files to or from flash;
   - save to startup;
   - reload;
   - retire;
   - **the terminal, LAST**: labelled as the break-glass path whose use is
     recorded, and a change made there is drift until captured into intent
     (decision 3).

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
      credential unchanged, dangerous lines, rollback block. This is CI
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
| `approval-binds-a-set` | Source of truth, Templates | the approval badge names the device set it covers, and a revocation shows its reason |
| `provenance-limits-remove` | NetBox remove preview | what will be skipped, and *"NMAS did not create it"* |
| `pending-vs-promoted` | Fleet, and the device header | *"Created, not yet reached: not managed until verified"* |
| `revert-is-forward` | revert-intent preview | what the revert will NOT undo, and that removal needs Mode B |
| `baseline-is-earned` | Versions, Baselines | why a baseline was or was not earned, per device |

**Floor:** nine concepts, nine screens, and the test counts them.
**Control:** remove one marker, and the test fails.

## 5. "If a payload carries it, the screen shows it", made mechanical

Three instances of one failure are recorded:
- **D4:** the wizard dropped `commands`, `dangerous` and `attribution`;
- the pending banner dropped its `list_name`;
- `/jobs/health` had no view at all.

The check that catches the fourth before it ships is modelled on
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
- **Anchors:** `commands`, `dangerous` and `attribution` on `/deploy/plan`,
  and `list_name` on `/onboard/pending`, must be read. Removing one fails
  the test.

## 6. Every task's home

**The curl-only tasks, which this stage fixes.** The GUI can put a device
into a state that only curl can take it out of, so each gets an entry point:

| Task | Home |
|---|---|
| Seed intent from a capture (extract, review, commit) | Device, Actions |
| Deploy several devices as one batch | Fleet, selection |
| Authorise a dangerous line | the preview-confirm component (P.3 adds it to the current wizard) |
| Retry after a rollback | Device, Actions, and a Needs attention row |
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
- **adopt an existing device** (Fleet);
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

## 7. The Configure forms (decision 2), a parallel track

P.3 removes the direct push. Stage 7 homes the forms as **"Author intent
from a form"** on the Device page, and on a Fleet selection for the same
change on many devices.
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
| **7.2** | The status bar, and **Needs attention** with every source in section 1a |
| **7.3** | The Device page: the Grafana iframe test FIRST, then Overview, Monitoring, Neighbours, History and Actions, including seed intent, revert, retry, rotate, retire and the terminal last |
| **7.4** | Fleet: the bounded list and selection, batch deploy, bulk intent, onboard, adopt and retire, networks, and the inventory source |
| **7.5** | Versions: commits by actor and source, baselines with their reasons, re-applying one, the remote with connect |
| **7.6** | Source of truth: templates (revoke, bindings, coverage, seed status), NetBox, credentials, freshness authorisations |
| **7.7** | Settings split, file-only settings listed, diagnostics |
| **7.8** | Removals, each with `check_removed_definitions.py` and a recorded reason, last so nothing goes before its replacement is on screen |
| **7.9** | Configure forms: batch 1 (a parallel track, not blocking) |

## 9. Deferred, recorded rather than scoped

- **A fleet topology view.** If it returns, it caps the devices shown, and
  networks can be organised into groups, with the view showing one group at a
  time. A topology of 200 devices is a picture nobody reads; one site's is
  useful.
- **Configure batches 2 and later**, beyond what the schema models.
- **Mode B** (removals through intent).
- **The agent's triage-and-propose UI** (Stage 8): its reports attach to
  Needs attention rows, and its proposals arrive as ordinary plans in the
  preview-confirm component. Stage 7 leaves the place for them.

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
