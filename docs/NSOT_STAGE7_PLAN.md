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
     **COMMITTED 2026-09-27 (NSOT_FEATURE_AUDIT 3a):**
     replaced by a read-only LENS in the diagnosis area, line mode,
     allowlisted (C61 fixed first), masked, and not break-glass. Config mode
     is cut, and the break-glass path is the console runbook.

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
| **7.2** | The status bar, and **Needs attention** with every source in section 1a. **The reachability reader (C92)**: one job keeping, per device, the last probe, its time and the consecutive-miss count, with the threshold taken from the host's measured misses, read by the dot and by every action that now acts on a single probe |
| **7.3** | The Device page: the Grafana iframe test FIRST, then Overview (the reachability claim drawn with its age and which claim it is, never "offline" for a device nobody probed: C92), Monitoring, Neighbours, History and Actions, including seed intent, revert, retry, rotate, retire and the terminal last. **Monitoring's acceptance is Stage 5's enumeration, 7.3-a…f** (NSOT_PLAN.md; renumbered from "7.5" on 2026-09-27), with 7.3-f already done by P.1 |
| **7.4** | Fleet: the bounded list and selection, batch deploy, bulk intent, onboard, adopt and retire, networks, and the inventory source. **Onboarding is designed for N address sources** (static, dhcp, ztp: P.6 lands first): the source choice is a LIST, not a toggle, and the pending-device row carries a per-source PROGRESS column (for ZTP: reservation written, config fetched, first seen). Cheap to design now, expensive to retrofit. |
| **7.5** | Versions: commits by actor and source (stating once *"N of M commits carry a verified identity"*, with the rest marked *"recorded, not verified"*: D10, P.3 step 10), baselines with their reasons, re-applying one, the remote with connect |
| **7.6** | Source of truth: templates (the scheme-3 approval badge saying what it covers and what it does not, P.5; revoke, bindings, coverage, seed status), NetBox, credentials, freshness authorisations |
| **7.7** | Settings split, file-only settings listed, diagnostics |
| **7.8** | Removals, each with `check_removed_definitions.py` and a recorded reason, last so nothing goes before its replacement is on screen |
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
dangerous lines, the rollback block and the two apply-time checks. As a
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

**The C77 sweep BUILT (2026-09-27)**, `tests/test_no_post_returns_a_stored_secret.py`: every `not_device` POST, from the gate table, driven with a body that reaches its state, with every store planted. Its first real run found three leaks from two stores, fixed here: the backup compare and both NetBox import previews. The previews' community was a plain value, so `mask_payload` masks by key as well. The previews led to C95: NetBox holds every imported device's credential lines and communities (measured on all 10), which is the operator's decision. The sweep's drift check also exposed C96 (the drift panel draws none of its last run, for 7.2). **Next: C70 in the browser**, the first thing run after this lands (r2 is still broken on the host, and `baseline/20260927T154517Z` is still the newest baseline).

**Step 5 BUILT (2026-09-27): scoped restore (C80).** The server already scoped a restore (`build_targets` takes `devices`, and the apply takes exactly the confirmed devices), so C80 was a gap in the interface, and the fix is two choosers ending in the one guarded preview. **The Device page's "Restore from…"** (`static/js/nmas_restore_scope.js`) reads `GET /golden/restore_points/<host>`: the device's golden now, its own golden tags, and every baseline that holds it, newest first. A baseline predating the device is not listed, since re-applying it would leave the device as it is. Each point carries the device's credential state at that ref, measured as the Baselines panel measures it: `current`, `refused` (the restore's own guards stop it), `silent` (an account the ref has and the device lacks would be ADDED back, C79, and choosing it asks for a typed APPLY) or `no_golden`. The username lines never leave. A chosen point goes to `/?restore_head=<host>&restore_ref=<ref>`, the handoff the HEAD restore already used, now carrying the ref. **The Baselines panel's "Re-apply"** asks for a scope first: every device the baseline holds, none ticked, and "the whole fleet" as its own box, so the fleet is chosen rather than inherited. The credential acknowledgement then names only the chosen devices. `tests/test_restore_scope.py` runs against a real repository (r2's real config, a baseline earned by a whole-fleet capture at intent) and executes the shipped chooser against the route's response. **A fixture that reached the wrong case, caught by reading which state came back:** the first "rotation" in the test replaced the password value everywhere on the line, and the fixture's value equals the account name, so it renamed the ACCOUNT. The route answered `silent`, correctly for an account added back, and not for the rotation the test meant. Both cases are now tested from the same real line. The payload check found two fields the chooser carried and did not draw (`subject`, `list`); both are drawn. Next: the C77 sweep, then C70 in the browser.

**Step 4 BUILT (2026-09-27), both layers.** The record layer (`7910e09`): `save_golden()` compares every capture with committed intent (`modules/nsot/intent_match.py`, the deploy plan's own comparison), writes a computed `Intent-Match:` trailer on every golden commit, and takes a baseline only with coverage AND every capture matching (C91 found and fixed on the way). The operation layer: `POST /golden/capture/preview` reads each device NOW and returns only a masked preview, with each device's diff against its golden and, under what will NOT happen, where it departs from its committed intent and why no baseline tag will be taken. `POST /golden/capture/apply` re-reads each confirmed device, refuses one whose capture hash moved, and commits once (`Source: capture`, or `save_all` for the fleet) as the verified person. Its result is drawn by the component and is never green while a capture departs from intent. `static/js/nmas_capture.js` is the one client: the Device page's Capture button opens it for one device, and **Save All opens it for the fleet**, so `/golden_configs/save_all` (one click to golden, baseline and remote) is removed. It differs from the plan above in one way: the source is `capture`, not `manual`, so git can tell a person's capture from a hand edit. `tests/test_capture.py` drives it on r2's real configuration with the host's exact break. **Found while wiring it:** `tests/js_source.with_loaded_scripts` modelled only the page's own generated scripts, so a component loaded from `static/js/nmas_*.js` was invisible to every renderer test that reads the assembled page; it now includes them (Bootstrap, also vendored in `static/js`, is deliberately not matched).

**Steps 2 and 3 BUILT for deploy and restore (2026-09-27):** `preview_confirm.operation_result()` builds the six result parts from the receipt rows `_write_receipts` has just written, and `previewConfirmResultHtml` draws them; `_renderDeployResult` is now wiring, and a restore opens its result in a modal instead of a toast. The level (and so the colour) is computed on the server and only drawn. `GET /deploy/receipts` and the Device page's Changes tab read the record back, one device's row of a batch saying exactly that. The rule's PENDING list: 33 to 31. **C85 fixed in step 2 (2026-09-27)**: the NetBox import's outcome is a result on the sync card, levelled by `complete`, and the rule's PENDING list is 29. Then the remaining results as their operations are retrofitted.

**Step 1 BUILT (2026-09-27):** `tests/test_results_are_drawn.py`, with the survey as its measured list (33 pending, 8 with no GUI, 0 drawn by the component), `FALSE_GREEN` (3) and `UNESCAPED` (2). Writing it found C87: the reachability check had counted intent revert reachable because the editor's own fetch shared its prefix.

**The overlap with 7.3, stated:** capture and scoped restore are the first
Device-page ACTIONS. 7.3 builds the rest of that page around them rather
than beside them.

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