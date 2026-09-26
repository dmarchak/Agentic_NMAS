# Feature audit: what survives into the redesigned tool

Written 2026-09-26, before the Stage 7 GUI plan, so the GUI is not built
around features that should not survive. **The test for each feature: is it
still the right way to do that thing, given what the tool has become?** It
began as a CSV device manager with encrypted credentials. It is now an
intent-based source of truth: intent in git, templates with approval gates,
preview-then-confirm-by-hash merge-only deploys, provenance-tracked NetBox,
drift, heartbeats, onboarding and retirement, and a backup chain.

**Constraint:** it stays a full infrastructure-as-code suite. The goal is
coherence, not cutting. A feature survives because it is the right way to do
that thing, not because it exists.

Classes: **KEEP** (still right), **ABSORB** (the capability survives inside
something else), **CUT** (a problem the model no longer has, or one it solves
better elsewhere), **UNDECIDED** (the operator's call, trade-off stated).
Sources: the task inventory (docs/NSOT_TASKS.md), the Jenkins audit and the
AI-tool and dead-code audit (docs/NSOT_CI.md), each verified in code where a
claim was load-bearing.

## 0. Found by the audit, before any classification

Five findings are defects on live paths regardless of what the redesign
keeps. They are in the register and CLAUDE.md, and they are proposed as
**P.3, before Stage 7**. Stage 7 moves controls and must not re-home a
control whose guard does not exist.

| Register | Finding | Why before Stage 7 |
|---|---|---|
| **B12** | The identity gate is not enforced on deploy, restore or approval. Of 19 device-reaching mutating routes, one is gated. CLAUDE.md said all were. | Stage 7 re-homes exactly these controls |
| **B11** | `GET /settings` returns the Anthropic key and the Jenkins secrets in cleartext, with no gate | A secret leaves the host on every Settings open |
| **D5** | Two GUI buttons run the unguarded golden replay; the guarded single-device restore has no button | Replace before the redesign draws either |
| **D4** | The deploy wizard shows the diff, not the program the hash covers, and cannot deploy a dangerous line | It is the confirm screen; 7.3 rebuilds it, but the defect is live now |
| **C23** | The restore preview's inventory-population fix is in a function no route calls | The preview a person confirms from states the wrong coverage |

## 1. The tabs

| Tab | Class | Reason |
|---|---|---|
| **Devices** | ABSORB into Fleet (list) and the device page | The capability is central. The row's seven controls move to the device page (§0a scale finding). |
| **Topology** | **UNDECIDED**, lean KEEP the capability and ABSORB it | It answers a real task (see a device's neighbours, and whether its links are up, as part of *why was it silent*). Live discovery is accurate when run and cached after, so a device that came or went is right after the next discovery and wrong before it. There are two renderings (four live-discovery views, and the topology-service SVG), and vis-network loads from a CDN (D8). **Trade-off:** a fleet topology view is costly to keep accurate and loses meaning at scale (§0a), while per-device neighbours on the device page are cheap and always relevant. **Lean:** per-device neighbours on the device page, one fleet view only if an embedded one is accurate (the plan's 7.9 already says this). |
| **Ansible** | **CUT** | It is not Ansible. It lists AI-saved command lists that `run_ansible_playbook` replays over Netmiko in config mode, the SIXTH unguarded push path, triggerable from `/ai/chat` even with AI disabled. "Run" only pre-fills the chat. The Configure-tab wizard emits a YAML download nothing consumes. Intent plus templates is this tool's IaC. |
| **Jenkins** | **CUT** | See docs/NSOT_CI.md: unconfigured, not load-bearing, broken in several places. CI becomes state beside its trigger. |
| **History** | **CUT**; the capability is ABSORBED into Versions | It shows only the AI change log, which only AI tools write (zero tool calls ever). Deploys, restores and intent edits are git commits. *What changed and who changed it* is `git log`, with `Actor:` and `Source:` trailers. |
| **NetBox** | ABSORB | The guarded Import and Remove previews survive, under keeping the source of truth correct. The legacy unguarded routes (`/netbox/sync`, `/sync_all`, `/remove`) are CUT: they skip the one-shot token half of the write gate. |
| **Agent** | **UNDECIDED** (section 5) | |
| **Approvals** | ABSORB into *Is anything wrong / needs you* | The queue is attention, not a place. Approve needs a person (B12). |
| **Monitoring** | ABSORB: the integration status into the status bar, per-device graphs and logs into the device page (Grafana embedded, 7.5); the legacy collectors CUT (7.5-e, decided) | |
| **Configure** | **UNDECIDED** (section 3) | |
| **Git** | KEEP as **Versions** (7.4) | commits, tags, baselines, per-device history, remote and push state, and CI results per commit |
| **Logs** | ABSORB into a diagnostics area (7.7) | |
| Settings | KEEP, split (7.7) | Secrets write-only (B11). |

## 2. The device page

| Feature | Class | Reason |
|---|---|---|
| Run a show command, quick actions, download output | KEEP | Investigation, the core of *why was this device silent*. |
| **Terminal** | **UNDECIDED**, lean KEEP, labelled and gated | **It complements the model rather than undermining it, if it is honest about what it is.** Engineers investigate at a CLI, and the model already assumes people touch devices: drift detection exists for exactly that. What undermines the model is a config change typed here being **invisible**. **Lean:** keep it; gate it on a person (B12); record who opened it; state on the page that *a change made here is drift until it is captured into intent*; and let drift report it. **Trade-off:** a read-only terminal (show commands only) is safer and loses break-glass use, which the console path covers. |
| Scripts tab (`/run_script`, multi-line config push) | CUT | An unguarded config push with no task the intent path or the terminal does not cover better. |
| Files (flash over TFTP, one device or bulk) | KEEP, gated | Image management is a real task outside intent. Gate it (B12). |
| Backups: take, compare, download | ABSORB into Versions as captures | A backup is an ad-hoc capture, and a golden is an approved one in git. Two stores of one kind of thing is the CSV-era shape. |
| Restore from a stored backup (`/device/<ip>/restore_backup`) | CUT | An unguarded whole-config push. Restoring means the guarded restore path, to a golden or a baseline. |
| **Restore Golden Config** (device and bulk) | **REPLACE** (D5) | The task is real; the mechanism is the unguarded replay. The button becomes the guarded single-device restore. |
| Save to startup (two buttons, both `write memory`) | KEEP one | Duplicate. |
| Delete (device row and device page) | CUT, replaced by **Retire** in the GUI | Delete removes the CSV row only and leaves a device half-managed (C11). Retire is the whole exit and is CLI-only today. |
| Ask AI about this device | depends on section 5 | |

## 3. Changing the network

| Feature | Class | Reason |
|---|---|---|
| Intent editor, preview, commit | KEEP | The model's way to change a device. |
| **Seed intent from a capture** (extract, review, commit) | KEEP, and **ADD the missing GUI** | The editor's own note tells the operator to do this, and only curl can. Every new intent document depends on it. |
| Bulk intent (`nmas-bulk-intent`, `/templatize/bulk/*`) | KEEP, and ADD a GUI | The model's way to make one change to many devices. |
| Deploy plan and apply | KEEP, and FIX D4 | Batch deploys and dangerous-line authorisation have no GUI (curl only). |
| Revert an intent commit; retry after a rollback | KEEP, and ADD GUI (7.1) | A device can enter the blocked state from the GUI and leave it only by curl. |
| **Configure tab (`/configure/apply`, about 90 feature forms)** | **UNDECIDED**, lean **ABSORB into intent authoring** | Today it pushes generated commands straight to devices, bypassing intent, so each use makes intent drift. Its docstring promises guards the body lacks (D6). **The forms themselves are valuable**: they encode how to express OSPF, BGP, VLANs, ACLs and QoS. **Lean:** keep the forms and change their output: a form produces a **host_vars change**, and the normal preview, confirm and deploy path sends it. That keeps "configure a feature from a form" as a task, and makes it an intent-authoring aid rather than a second push path. **Trade-off:** that is real work (each form's output mapped onto the intent schema), and features the schema does not model yet cannot be expressed. The cheaper alternative is CUT, leaving intent YAML as the only authoring path, which is harder for a newcomer. |
| Bulk execute in **enable** mode | KEEP | A fleet-wide show command is investigation. |
| Bulk execute in **config** mode | CUT | Bulk intent is the model's way. An unguarded fleet-wide config push is the widest bypass. |
| Remove all static routes (bulk) | CUT | A lab-reset action with no engineer task behind it, bypassing intent. |
| Reload devices (bulk) | KEEP, as preview-then-confirm, gated | A real operational action, and a dangerous one. |
| Credential rotation and persistence | KEEP, and ADD GUI later | A real task, CLI-only today. |
| Auto-Create Golden Configs | ABSORB into Save All | Overlaps it and commits separately. |

## 4. Devices in and out, records, the source of truth

| Feature | Class | Reason |
|---|---|---|
| Onboarding wizard (plan, create, verify, abandon, bootstrap download) | KEEP | The model's way in. |
| Add device form, Discover subnet then Add | **ABSORB** into onboarding as **"adopt an existing device"** | Bringing in an already-configured (brownfield) device is a real task. Today it adds a CSV row and nothing else: no manifest identity, no intent, no golden. Adoption should capture, extract intent, commit, and promote. |
| Retire (`nmas-retire`) | KEEP, and ADD GUI | The whole exit, CLI-only today. |
| Device lists (networks): create, switch, delete | KEEP | |
| Refresh hostnames | ABSORB into inventory refresh | |
| Save All (capture the fleet as goldens, one commit) | KEEP, in Versions | Fix its toast's false Jenkins text (docs/NSOT_CI.md §0). |
| Remote card (verify, preview, push, adopt) | KEEP, and ADD the adopt control | |
| NetBox guarded Import and Remove | KEEP | |
| Legacy-golden migration cards | KEEP until the retirement condition, then CUT | Self-retiring by design. |
| Template library: edit, validate, approve | KEEP, and ADD revoke and bindings (7.1) | |
| Variable store and compliance policy (`/list/variables`, `/list/compliance_policy`, AI tools) | **CUT**; compliance ABSORBED into CI | The variable store is the CSV-era predecessor of host_vars intent. Compliance rules as strings run in exec mode are superseded by required-block checks over intent (docs/NSOT_CI.md R7). |
| Legacy collectors (SNMP traps, NetFlow, OOB collector IP) | CUT (7.5-e, decided) | Replaced by Prometheus, Loki and Grafana. SNMP Quick Poll: CUT with them. |
| Integration status strip and service status | KEEP as the status bar (7.2) | |
| `/jobs/health` | KEEP, and ADD GUI in *Is anything wrong* | |

## 5. The agent

**Is it a feature or an aspiration?** Measured:
- **27 runs and 0 tool calls, ever**, with a workspace-id error since
  2026-08-28;
- **73 tools**, all sent to the model every turn, with nothing between the
  model and a tool;
- **six unguarded device-push paths**: three `execute_*` tools in config
  mode, `restore_golden_config`, `restore_pre_change_snapshot` and the
  "Ansible" replay;
- **self-modification**: it can patch any file under `modules/` or
  `templates/`, or `app.py` (the deploy guards, `identity.py` and
  `redact.py` included), restart, then commit and push;
- **auto-continue**: its own confirmation questions ("should I push?") are
  answered "Yes, please continue." by code;
- **a golden workflow that contradicts the model**: configure over SSH, then
  save startup-config as the golden, while host_vars is never touched;
- **its idea of intended state is wrong**: `nsot_get_device_context` calls
  the NetBox record "the intended state", and no tool reads host_vars,
  templates, approvals, plans or previews;
- **19 tools** point at an unconfigured Jenkins, and dozens of examples cite
  a PE/P/MPLS network that is not this one.

**Read: as built, it is an aspiration, and a dangerous one.** Every guard
this project built, it can go around or rewrite. That it never ran is the
only reason none of this has mattered.

**It is still UNDECIDED, because the project's name is *Agentic* NMAS.**
Cutting the agent outright removes the thing the coursework is named for.

**Lean: keep the AGENT as a concept, and cut its current library.** Stage 8
rebuilds it on this rule: **the agent proposes, a person confirms.**
- It reads everything: intent, goldens, plans, previews, the job, drift and
  freshness states, NetBox.
- It may draft an intent change, or queue an approval item.
- It never sends to a device, never commits a golden, never edits its own
  code, and never answers its own confirmation questions.
- Every device change it proposes arrives at a person as an ordinary plan
  with an ordinary confirm hash.

That makes the agent a second author of intent rather than a seventh push
path, and it fits the model instead of routing around it. **Trade-off:** it
cannot "fix things autonomously". That was the original pitch, and it is
exactly what the rest of the tool exists to prevent.

Tool-by-tool, for Stage 8 (group counts from the audit):

| Group (count) | Class |
|---|---|
| SSH execution (3) | Read-only show commands KEEP; config mode CUT |
| Device reads and captures (4) | KEEP; stop writing unmasked configs to the installation-wide `config_cache/` |
| Golden, baseline, rollback, drift (8) | Reads KEEP; `restore_golden_config`, `restore_pre_change_snapshot`, `save_golden_config`, `finalize_verified_config_change`, `capture_pre_change_snapshot` and `detect_config_drift` CUT (the guarded paths do these) |
| Change log and compliance (5) | CUT (git is the log; compliance moves to CI) |
| Variables (3) | CUT (host_vars) |
| Knowledge and notes (6) | UNDECIDED: the CCIE knowledge base and lab notes are study aids, not NSoT |
| Approval (1) | KEEP: the one tool routed through a person |
| Self-modification (4) | **CUT, without exception** |
| Jenkins (19) | CUT (docs/NSOT_CI.md §4) |
| "Ansible" replay (3) | CUT |
| Legacy collectors (7) | CUT (with 7.5-e) |
| Reports (4) | UNDECIDED, with the knowledge tools |
| NSoT and NetBox reads (6) | KEEP; `nsot_get_device_context` must read host_vars, not call NetBox "intended" |
| **New (Stage 8)** | Read plans, previews and job, drift and freshness states; draft an intent edit; queue an approval. |

## 6. Code nothing reaches

From the dead-code audit (verified where it mattered):

- **Wire, do not cut:**
  - `plan_restore()`, the restore-population fix (C23);
  - `staged_post_deploy` and `staged_restored_intent`, the only readers of
    the crash-recovery staging, whose recovery is manual today (UNDECIDED:
    automatic recovery or a documented manual step);
  - the `source.json` ordering route (D7).
- **Cut:**
  - `verify_and_promote` (the superseded phase 2, test-only);
  - `push_safe_lines`, since no whole-config replay should survive to need it;
  - the orphaned CLI parsers in `netbox_client` from `_scan_device`;
  - `generate_pipeline_xml` and `_build_check_script`;
  - `host_vars_fingerprint` (approval scheme 1);
  - four exception classes never raised;
  - the vestigial drift schedule inside `agent_runner`;
  - `/ai/events`, `/ai/tool_cache_snapshot`, `/bulk_clear`,
    `/list/golden_configs`, `/drift/check` (async), `/disconnect/<ip>`,
    `/execute_command` (an ungated config push with no caller) and
    `/device_lists` GET.
- **Keep, by design:** the `stop_*` shutdown hooks (harmless), and
  `/identity/status` (a diagnostic).
- **Fix separately:** the four CDN-loaded libraries (D8), vendored like the
  rest.

## 7. Decisions (the operator, 2026-09-26)

**Sequencing:** P.3 (every device path guarded or gone), then P.4 (cut
Jenkins), then Stage 7. Both are written into NSOT_PLAN.md.

### 1. The agent: an ON-CALL RESPONDER that triages and proposes, and never confirms

This changes the lean in section 5. The operator wants the thing the project
is named for: an alert fires (a device goes silent, a critical syslog line,
drift, a failed job), and the agent investigates, attempts a fix, and reports.
It is scoped in three verbs:
- **TRIAGE autonomously.** It reads everything and correlates the alert
  against drift, intent, goldens, job state, neighbours and logs, then writes
  a report a person can act on. This needs no guards, and it is most of the
  value at 3am.
- **PROPOSE** a fix as an ordinary plan: a drafted intent change, a deploy
  plan with its program and hash, or an approval item.
- **NEVER CONFIRM ITS OWN PLAN.**

The current 73-tool library is cut, and Stage 8 rebuilds on triage and
propose. P.3 removes the push, commit and self-modification tools now, and
P.4 the 19 CI tools.

**(a) Does triage and propose satisfy "automatically respond and attempt to
fix", or does it cut the thing asked for?** It satisfies it, and here is what
it costs.
- **The response is automatic:** triage starts within minutes of the alert,
  and the correlation a person would do at 3am is already done.
- **The attempt is real:** it produces the fix as a ready plan, with its
  program and hash, one confirm from done.
- **What is lost is the fix landing without a person.** Two facts say that
  loss is cheap:
  1. **Tonight's evidence.** No incident this session was fixed by a device
     push a program could have chosen alone:
     - s4 went silent because a person silenced it;
     - s4 became INSEPARABLE because of a query bug in the measurement;
     - clab-sync failed 72 times because of a helper's PATH, a code fix;
     - B9's hole needed a lock design;
     - B12 needed reading the code.

     Every real fix took judgement or code.
  2. **The gates.** An autonomous device fix would have to pass the same
     gates, and after P.3 those gates require a person by construction. So
     letting the agent act would mean granting it an exemption from the gate,
     which is B12 reintroduced on purpose.

  **So this cuts the part that would make it untrustworthy, not the thing
  asked for.**

**(b) The boundary: what could safely be autonomous.** A narrow class is
defensible. An action may be taken without a person **only if all five
hold**:
1. **It touches no device and no source of truth**: not git, NetBox,
   credentials, settings or gates.
2. **The schedule would do it anyway.** It is a declared job run EARLY, so it
   changes the timing and never the outcome.
3. **Every guard that job has still applies.** For example, a re-run
   clab-sync still meets the freshness gate.
4. **It is bounded and recorded.** Once per alert, never in a loop, written
   to the triage report. It is granted by name through
   `service_allowed_operations`, which starts EMPTY, so the operator grants
   each kind.
5. **It cannot hide the alert.** It never silences, acknowledges, disables,
   or changes a threshold or window. (The drift checker was silenced once;
   the agent must never be able to repeat that.)

**Inside that class:**
- re-run a failed timer job once (the NetBox backup, the restore test, the
  heartbeat check, clab-sync);
- run a check now (drift, freshness, the heartbeat window);
- refresh an inventory;
- re-test an integration's connection.

**Outside it, and why:**
- **"Re-send a known-good deploy already confirmed once" is an empty class.**
  A confirmed program is bound to its capture hash. If the device is still in
  that state, merge-only has nothing to add. If it has moved, the hash
  refuses. Either way, anything to send is a NEW plan, and a new plan needs a
  person. The deploy path's own design leaves this class empty.
- **"Restart a collector" is not the schedule's job, and it destroys
  evidence.** A restart changes running state, loses the in-memory cause, and
  is the move that hides C14-class failures: clab-sync refused correctly 72
  times, and a restart-until-it-works loop would have turned a named cause
  into silence. It is proposed, not taken. It can be granted by name later,
  if ever.
- **Never:**
  - any device configuration;
  - any commit;
  - any write to NetBox or credentials;
  - approving, confirming or rejecting anything;
  - changing settings or gates;
  - silencing or acknowledging an alert;
  - deleting anything (backups, jobs, logs);
  - editing its own code;
  - answering its own confirmation question.

**What makes the autonomous class different from the rest:** it contains
only actions whose worst outcome is **"it happened earlier than scheduled"**.

### 2. The Configure tab: absorb, phased

- The direct push is **CUT now**, in P.3: every use makes intent drift.
- The ~90 forms are **KEPT**. They encode how to express OSPF, BGP, VLANs,
  ACLs and QoS.
- They are **CONVERTED in batches**, starting with features the intent schema
  already models, so the first batch is mapping rather than schema work.
- A form whose feature the schema cannot express says so and offers nothing,
  rather than pushing.
- Stage 7 does not block on the conversion.

### 3. The terminal

**Keep it, gated, labelled, and as the LAST RESORT**, recording who opened it
and when (P.3 step 7). The page says two things: this is the break-glass path
and its use is recorded; and a change made here is drift until it is captured
into intent.

### 4. Topology

**Per-device neighbours on the device page only. No fleet view now.**
Recorded for later, not scoped: if a fleet view returns, it caps the devices
shown, and lists can be organised into groups, with the view showing one
group at a time. A topology of 200 devices is a picture nobody reads; one of
a single site is useful.

### 5. P.3 and P.4 before Stage 7 (see sequencing above)

### 6. Knowledge tools and reports: cut, and what that does to the assistant

The question was whether the knowledge base and lab notes feed the
assistant's context, or are standalone study aids. **Measured: they feed
it.** `ai_assistant.py` injects lab notes ("apply immediately"), the global
KB ("treat as standing rules") and the network KB ("confirmed facts about
this network") into every prompt's stable context.

**On the host they are empty**: no global KB, no lab notes, and a network KB
with one entry from 2026-09-01. The assistant has never built its memory,
since its tools have never run. **So cutting the self-writing tools costs
nothing today.**

**The need they were built for is real, though, and triage needs it most**:
facts about a network such as "s4's clock runs at 75%" or "r6 has no
`/etc/hosts` entry". What is wrong is the mechanism. A rule the model writes
for itself, injected as "apply immediately", is **self-modification at the
prompt layer**, the same concern as `patch_app_file`, one level up.
- **So: cut the self-writing knowledge tools.**
- **Stage 8 gives triage read access to CURATED, COMMITTED network notes.**
  People write them, or the agent PROPOSES them as a commit a person accepts,
  and they are versioned like intent.
- **The CCIE syntax knowledge base is cut.** The agent never writes IOS in
  this model; templates render it.
- **Reports are not cut as a capability: the triage report IS the on-call
  responder's output.** The current report tools (markdown files in `data/`)
  are cut. The triage report becomes a first-class record attached to its
  alert, shown in "Is anything wrong".

**If the operator wants the knowledge base back as it was**, the trade is
this: an assistant whose standing rules nobody reviewed, against an
assistant with no memory until curated notes exist.
