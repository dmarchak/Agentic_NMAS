# Heal to intent (board H): a design for the operator's review, not built

**The operator's direction, 2026-11-03, for Lab 10 (automating network troubleshooting).** A
self-healing application in Mercury: deterministic code, no AI in the loop, the Respond function
of IBN (docs/IBN_DESIGN.md section 3). Restoring committed intent is maintenance of an approved
state, not a change. **This board is architectural and is the operator's to review before
anything is built.** It is not self-signed under the Phase 7 mode. The mockups are
`docs/boards/heal-to-intent.html`. Drawn 2026-11-03 ~18:0x UTC (12:0x, UTC−6) over HEAD
e93fe977. **Enabling AUTO on Default stays the operator's decision** (section 9).

**The operator's review, 2026-11-03 ~18:4x UTC.** All three findings are agreed:
1. A heal plans against a fresh read, bound by hash.
2. R3's demo runs on the r3–r4 link.
3. Any firing alert on a device is a trigger.

N13 is agreed, refined (section 18). The kill switch is kept and goes last in the cut order
(section 17).

**Board H approved by the operator, 2026-11-03 ~19:5x UTC, with these answers** (section 18
holds each):
- **N1, N2, N4, N5, N6, N7, N9, N10:** as recommended.
- **N3:** 60 minutes on a network marked lab, and 4 hours as the production default (the risk
  register's figure).
- **N8:** agreed. Default is marked lab, and AUTO is enabled there for at most 7 days per
  enablement, expiring to dry run. Tier 1 kinds are enabled one at a time, each after its
  dry-run scenario passes.
- **N12:** agreed, plus maintenance mode:
  - **"Hold this device from healing for N hours":** one click on the device page.
  - **"Keep this change"** in the heal notice: it holds the device and raises a
    Capture-or-Revert row.
  - **The window:** production's 15-minute grace is the window for both.
- **The narrowings:** agreed, on lab-marked networks only. Production keeps section 7's bar and
  17.7's gate.
- **The kill switch:** the per-network one-click Turn off meets the operator's condition, so the
  installation-wide switch stays last in the cut order.
- **V1:** checked, and it stays (section 15).

**The build starts as soon as its prerequisites are done** (local CI, then this board's commit),
never waiting for a date (the operator's correction, 2026-11-03: "every date in the roadmap is an
expectation, used to raise a concern early when an item is behind; never a reason to wait").

**The addition of the same day (the operator's, decided):** a can't-fix notification carries an
AI analysis. It is advisory only, and nothing in the heal loop reads it (section 12). It is the
one AI part of this design. Its AI cost rules are CLAUDE.md's "AI cost safety", and section 12
holds them.

**Register rows searched first** (none covers this): C750 (IBN, none of the four functions end
to end); C2128 (no on-call or notifier integration); C1999 (notification of SDN incidents);
C2009 to C2016 (17.7's AUTO gate); C2274 (the planned state, its drift re-run); C1720 (the
classification marking, which keeps the configuration egress class off). Each new row this
design needs is listed in section 18, for recording once the operator has reviewed it.

**Contents:** 1 the industry need · 2 the principle · 3 triggers · 4 the flow · 5 the tier
table · 6 hard stops and guards · 7 dry run and enablement · 8 the step log and records ·
9 settings and screens · 10 notifications · 11 the lifecycle rule for an automatic heal ·
12 the AI analysis of a can't-fix · 13 the never list · 14 tests and coverage · 15 the demo
plan · 16 the build estimate · 17 the schedule shift · 18 decisions for the operator, earlier
decisions this narrows, and rows to record.

---

## 1. The industry need

**The problem.** Most outages are caused by changes, and many of those changes are made outside
the change process: a line typed at a console during an incident, a copy-paste error, a
"temporary" ACL nobody removed. The engineer on call finds out from a downstream symptom (a
device unreachable two hops away, a probe failing). They then spend most of the time finding
which device changed and what. After that they put the line back by hand, which is itself an
unrecorded change. The documentation (the golden, the CMDB, the ticket) is updated late or
never.

**How established commercial tools address it:**
- **Configuration-drift remediation in intent-based and NetDevOps products.** Controllers and
  orchestrators keep an intended configuration and flag a device whose running configuration
  departs from it. Typical examples are compliance and "sync to intent" in network
  orchestrators, configuration anomalies in intent-based fabric managers, and drift jobs in
  NetDevOps automation platforms. Some re-apply the intended configuration on a schedule;
  agent-based configuration management re-converges every interval regardless of who made the
  change. Most stop at "out of compliance" and leave the remediation to a person, or push a
  whole configuration back, which on Cisco IOS is a replace with a large blast radius.
- **Event-driven automation.** Rulebooks and runbooks fire a remediation when an event matches,
  such as a syslog line, an alert or a webhook. They are fast, and only as safe as each
  rulebook's author makes them: the guards are per rulebook, not per platform.
- **ITIL standard changes.** A pre-authorised, low-risk, repeatable change runs without a CAB,
  because the authorisation was given once for the change type. The record is still kept.
- **Auto-remediation risk registers.** Site-reliability practice classes each automatic action
  by blast radius and reversibility. Low-risk actions run automatically; medium-risk ones are
  proposed for a person; high-risk ones alert only; some never run automatically. Every class
  has rate limits, a kill switch and a dry-run period before it is trusted.

**How Mercury meets or improves on it, at enterprise scale:**
- **It heals only toward committed intent that the device last held.** It never pushes intent
  the device never ran (section 2). A tool that re-applies "intent" after an intent edit is
  deploying an unreviewed change; this one cannot.
- **Line-level, merge-only, measured.** A missing line is re-applied by merge. An added line is
  removed by Mode B only where `no <line>` was measured on that platform to remove exactly that
  line (`modules/nsot/removal.py`, `removal_measured.json`). There is no whole-configuration
  replace and no guessed `no` form.
- **The device-operation lifecycle every person's deploy has:** the exact program masked, its
  hash, the device held, verify scaled to what the program touches, rollback of what landed,
  and a receipt and a golden commit (CLAUDE.md, "Operations and safety"). An automatic heal is
  not a second, weaker path. It is the deploy pipeline (`modules/pipeline.py`) run by a policy.
- **The risk register is code.** Each fix kind has a tier (section 5) that the policy cannot
  promote past its ceiling. Tier 4 (security ACLs, credentials, Mercury's own management path,
  multi-device) is never automatic, whatever is configured.
- **It knows planned work and its blast radius** (PHASE8_PLAN 20.2 and 20.3). A heal never
  fights a reload, a deploy or a planned window, and a downstream symptom is folded into the
  incident of the change that caused it, not raised as its own.
- **The engineer gets the troubleshooting already done.** A can't-fix notification lists each
  check Mercury made and what it found, with a link to the incident and the device's own
  evidence. It is not a bare alert.
- **Documentation is updated and tested on every heal:** the golden is committed, then read
  back from the device and compared; the change record, History and the NetBox journal are
  written.
- **Scale:** triggers ride on readers that already read the whole fleet once per interval
  (`modules/reader_job.py`). A heal is a per-device job, never per-request work. Rate limits
  are per device and per network, and a fleet-wide event (more than 3 devices departing at
  once) is a hard stop that escalates instead of healing a rollout gone wrong.

---

## 2. The principle

**Heal to committed intent; maintenance of an approved state, not a change.**

- **The approved state** is the device's committed intent (`host_vars/<device>.yml`, rendered
  through the network's templates) as the device last held it: its last golden that matched
  intent. That is the golden whose commit carries `Intent-Match: yes` for the device, per
  `modules/nsot/intent_match.py` (C89).
- **A heal touches only lines that departed from both.** A line is healed only if it is in
  the drift (the running configuration against the golden) and also departs from intent (the
  render against the running configuration). Two consequences:
  - **An intent edit not yet deployed is never pushed by a heal.** Its lines are in intent and
    not in the golden, so they are not in the intersection. It is a change, Activate's, and a
    person's deploy (IBN_DESIGN section 4).
  - **A departure already recorded is never healed.** A golden captured with an out-of-band
    change in it (`modules/nsot/out_of_band.py`, C1819) disagrees with intent, so the device is
    marked **heal off for this device: its golden departs from its intent**, and a person
    resolves it first.
- This is IBN_DESIGN section 11's golden state rule, sub-rule 3 ("config convergence re-applies
  only the deviating lines, merge-only"), with the golden state read as "the last golden that
  matched intent". It does not need a `baseline/<ts>` tag (section 18, N5).

---

## 3. Triggers

Event-driven, plus the schedule. **Each trigger asks one question: check this device now.**
None of them heals by itself.

| Trigger | Where it is seen today (existing) | What is new |
|---|---|---|
| **A `%SYS-5-CONFIG_I` not from Mercury** | The `logs-tail` reader (`modules/readers/logs_tail.py`, every 5 s, every device's lines, masked on the way in); the mnemonics in `modules/device_logs.py` (`CHANGE_MNEMONICS`); the line's account and terminal parsed by `modules/ai/who.py` (`config_change`) | An after-store step on `logs-tail` (`reader_job.after_any_store`, the pattern `evidence_pack.after_alerts_read` uses), and the attribution rule below |
| **An interface down** | The Grafana rule "Interface down" (port down while admin up), stored by the `grafana-alerts` reader (`modules/readers/grafana_alerts.py`) | An after-store step on `grafana-alerts`: a firing "Interface down" checks its device and the far end intent names for that link |
| **An adjacency down** | The `adjacencies` reader (`modules/readers/adjacencies.py`, `PERSIST_READS` = 2, Prometheus) and the `adjacency-log` reader (`modules/readers/adjacency_log.py`, logged drops) | After-store steps on both: both ends of the link are checked |
| **The scheduled drift check** | `drift_check.DriftChecker` (every 4 h by default, per network; `DriftChecker.record`) | Its drifted devices enter the same decision |
| **(Recommended addition, N2) any firing alert on a managed device** | `grafana-alerts`, for example "NMAS heartbeat missing" (C2174) | It catches M4, where removing the logging host means its own CONFIG_I never reaches Mercury (section 15) |

**The attribution rule: is this CONFIG_I Mercury's?** It is Mercury's when a Mercury operation
held that device at the line's receive time, within the window the adjacency log already uses
for a deploy (`attention.DEPLOY_WINDOW_S`, 600 s before a receipt to 60 s after). The hold is
read from `device_ops.holder` and `device_ops.in_flight`, and receipts from
`modules/nsot/receipts.py` (`read`). **It is never attributed by the account the line names:**
a person may sign in with the account Mercury uses (the lab's accounts are shared), and an
account name is a resemblance, which is not evidence (CLAUDE.md, "Refusing by resemblance").
This is the CONFIG_I case of PHASE8_PLAN 20.2's `restarts.explained_by` question, asked of
Mercury's own holds and receipts.

**One incident per cause** (PHASE8_PLAN 20.5). Downstream symptoms fold into the incident of the
device that changed:
- **The fold.** A device unreachable, or alerting, while it is inside the blast radius of a
  device with an open incident (`modules/nsot/blast_radius.py`, `radius`) is attached to that
  incident.
- **Examples.** r7's "Device unreachable" in R3, R8 and C4; s5's in C1.
- **The attached device is still checked, and is not healed on its own.** The incident's
  verify waits for it to come back (section 4, step 5).

---

## 4. Detect → decide → act → verify → record → notify

One job per incident (`capture_job.start`'s pattern, as `deploy_job.start` uses it). One
incident per device at a time, under a per-network lock across processes, the pattern
`modules/nsot/scheduled_rotation.py` uses (`LOCK_FILE`, refused by name). Each step is a line
in the step log (section 8).

**1. Detect.**
- **Reused:** the trigger (section 3); `drift_check.check_device`, the same read and
  comparison as "Check drift now" (C2336; docs/manual/how-it-works/drift-check.md, "Check drift
  now, one device"). Its read is judged before it is compared: a stitched read is refused and
  its session is closed. The result is merged into the network's stored run, so the drift row
  says what this read found.
- **New:**
  - `check_device` also returns the read it compared, in memory only (never stored raw), so the
    heal plans against the very read the check made: one read, not two.
  - The grace period: a second read at least `heal_grace_seconds` after the first, with no
    outside CONFIG_I in between. A deviation that does not persist is not healed. This is
    IBN_DESIGN section 3's grace period, and PHASE8_PLAN section 7's "2 readings and 15
    minutes".

**2. Decide.**
- **Reused:**
  - `intent_match.intent_match`: the render of committed intent against the read, through
    `build_artifact(...).intent_drift`, the deploy plan's own comparison;
  - `routes.deploy._program(intended, captured, selected, device, platform)`: the one program
    computation, which is merge (`deploy.merge_commands`), then IP SLA re-creation
    (`recreate.plan`), then the selected removals (`removal.with_removals`);
  - `removal.candidates` and `removal.removable`, which give each unit its measured verdict and
    its refusal (the management interface, vty, SSH, AAA, accounts, numbered ACLs, routes that
    may be the manager's path, unmeasured shapes);
  - `pipeline.dangerous_commands`;
  - `expected_effects.for_device`, which includes `reach_lost` from
    `blast_radius.radius_of_shutdowns`;
  - the planned state: `restarts.explained_by`, `restarts.holding`, `planned_state.read`,
    `device_ops.held` and `change_windows.holding`.
- **New:**
  - each unit of the departure is classed into a fix kind (section 5);
  - the incident's tier is the strictest tier among its units, so a device is healed whole or
    not at all, and never partly;
  - the hard stops (section 6) are checked in a stated order, the first that applies named with
    both operands;
  - the program and its hash are computed (`deploy.command_fingerprint`) and written to the step
    log before anything is sent.
- **The outcomes:**
  - **heal** (Tier 1 in AUTO);
  - **would heal** (dry run);
  - **propose** (Tier 2);
  - **can't fix**, with its reason (Tier 3, Tier 4 or a hard stop);
  - **nothing to heal** (the device is at intent).

**3. Act** (AUTO, Tier 1 only, or a person's approval of a Tier 2 proposal).
- **Reused:** `routes.deploy.apply_batch`, the one apply every deploy runs, called the way
  scheduled rotation calls `rotate_op.run`. It runs as the policy's setter, with
  `actor_kind="policy"` and via "heal to intent (policy set by <person>)"
  (`scheduled_rotation`, around its `rotate(...)` call). It holds the device through
  `device_ops` (one operation per device across processes, refused by name), and runs the
  nine stages of `pipeline.PipelineRunner`: the CI gate, `pre_snapshot`, deploy, verify,
  rollback and audit.
- **New:**
  - **The heal plans against its own read, not the stored capture.** Today a deploy and a
    restore refuse a device that moved since its capture (C78:
    `deploy.device_against_capture`, `device_moved_reason`). A drifted device has moved, by
    definition, so today the only paths are capture-then-restore or capture-then-remove, both a
    person's. The heal passes its read as the "capture" for `plan_devices` and `_program`. At
    stage 4 the pipeline compares the device with that read (`roundtrip.stored_is_device`), so
    C78's property is kept: if a person changes the device again between the heal's read and
    its apply, the heal is refused with nothing sent ("the device changed during the heal"),
    and a later read starts over.
  - **No golden of the drifted state is committed.** The read lives only in the step log,
    masked, and in the receipt's pre-change record (`pipeline._record_pre_change`).

**4. Verify.**
- **Reused:** `pipeline._stage_verify`, unchanged: neighbours (tolerance 0, the settle window,
  `_await_neighbour_convergence`), route retention, interfaces, BGP hold
  (`_watch_bgp_hold`), and the read-back of the program's lines (`verify_scope.read_back`,
  QUICK for management sections and FULL otherwise, `verify_scope.classify`). On failure,
  `pipeline._stage_rollback` undoes what landed (`deploy.rollback_commands`) and says per
  device what it achieved.
- **New, after the pipeline passes:**
  - **(a) the symptom.** The trigger's own source is read again: `reader_job.request_run` for
    `adjacencies`, `grafana-alerts` or `reachability`, within the symptom's settle bound,
    which is about 2.5 times its measured time (the adjacency's dead timer plus two scrapes;
    the heartbeat's 300 s interval). The devices attached to the incident must come back.
  - **(b) intent.** `intent_match` on the post-change read gives `match` for the healed units.
- **Symptom still present, configuration at intent:** the heal is **kept**, not rolled back.
  Rolling back would re-apply the unauthorised change. The incident becomes **healed
  configuration; symptom remains** (amber, never green) and notifies as a can't-fix:
  configuration was not the whole cause.

**5. Record.**
- **Reused:**
  - the receipt: `routes.deploy._write_receipts`, `receipts.rows_for` with the `actor_kind`
    and the scope;
  - the golden commit: `pipeline._stage_save_golden` and `routes.deploy._commit_batch_golden`,
    through `repo.commit()`, published;
  - startup is saved: `pipeline._stage_save_startup`.
- **New:**
  - the golden re-check, "documentation tested": `drift_check.check_device` reads the device
    again and finds it at its new golden;
  - the step log store and its History source;
  - the deterministic change record;
  - the NetBox journal entry (section 8).

**6. Notify.** Section 10: a Needs attention row, email and webhooks. A can't-fix notification
also carries the AI analysis (section 12).

---

## 5. The tier table, per fix kind

The tiers are the operator's (Lab 10's decision 1). **A kind's tier is a ceiling in code:** the
policy may allow a Tier 1 kind to run automatically, or keep it in dry run, but it can never
move a kind to a lower-numbered tier. Tiers 3 and 4 are not settings.

| Fix kind | Example scenario | Tier | What is done | Verify reads | Rollback | Why that tier |
|---|---|---|---|---|---|---|
| **missing line** (intent and the last golden have it; the device lacks it) | M4 (the syslog destination removed, r2); M6 (the EEM heartbeat applet removed, r3); C1 (an OSPF `network` statement removed, r8) | **1** | Mode A: merge re-applies the line or stanza (`deploy.merge_commands`) | the pipeline's verify; the read-back of each line; the symptom: the heartbeat back within 300 s, the adjacency or the route back, the attached device (s5) reachable | `deploy.rollback_commands` removes what landed | Additive, merge-only, and restores a state the device ran and was verified in. The standard change in ITIL's sense |
| **changed line**, single-valued (a description, an OSPF cost, a logging level) | none in the set; a description typed at the console | **1** | Mode A: merge sets intent's value | read-back; the pipeline's verify | the prior value back, from the pre-change read | As above: one setting returned to its last verified value |
| **added line**, one section, a measured shape | C3 (a static route with a wrong next hop, r4: `global.ip-route`, measured exact on both dialects); R3 (OSPF authentication added on one end of a link: two new shapes, measured first, section 15) | **1** | Mode B: `no` plus the device's own line, a shape measured exact on the platform (`removal_measured.json`), one removal unit (`heal_max_removed_units`, guard 12) | read-back: each removed line gone (`removal.still_present`); the symptom (the IP SLA probe passing; the adjacency FULL) | `removal.restore_program`: the device's own line back from the pre-change read | Reversible and verifiable, measured on the platform: "remove one added line not in intent" |
| **admin down where intent says up** | admin shut on an interface (the operator's list) | **1** | Mode B's measured `interface.shutdown` shape (exact on both dialects): `no shutdown` | the interface up; `expected_effects`' `may_form` adjacencies form | `shutdown` back | Restores a verified state; refused on the management interface (Tier 4) |
| **a fix that takes effect only through a process reset** | R8 (r6 given r4's OSPF router-id, then the OSPF process reset) | **2** | Proposed: merge sets intent's `router-id`, then a measured "reset the OSPF process" command (new, `modules/nsot/privileged.py`'s pattern, section 16, H5), one hash, a person's confirm | the adjacencies re-form; no duplicate router-id logged | the router-id back; a reset cannot be undone, and the preview says so (`privileged`'s pattern) | A reset drops every adjacency on the device, so a person decides the moment |
| **QoS policy** (`service-policy`, `policy-map`, `class-map`) | I1 (a class shaper on r2's egress) | **2** | Proposed; its removal shapes are unmeasured today, so until they are measured it is **can't fix: unmeasured removal shape** | the queue's drops; read-back | `removal.restore_program` | A shaper's effect depends on traffic, and its verification needs load, which a heal cannot know |
| **a line in a secret position, added back** (an SNMP community, a routing key intent holds) | none in the set | **2** | Proposed: CLAUDE.md, "a dangerous line or re-added secret needs a stated reason", a person's | read-back, masked | removed again | A secret is introduced only with a person's reason |
| **physical or link down while admin up**, configuration at intent | I5 (r4 Gi4 ↔ r3 Gi4 flapping) | **3** | Nothing sent. Can't fix: notify with the step log | not applicable | not applicable | Configuration cannot fix a cable, an optic or a far end |
| **unknown cause**: a symptom with both ends at intent | an adjacency down, both routers matching | **3** | Nothing sent. Can't fix: notify | not applicable | not applicable | No departure to heal; guessing is not a fix |
| **security ACL drift** (any ACL definition, entry, or `access-group`, `access-class` or `ipv6 traffic-filter` binding) | C4 (an inbound ACL on r6 Gi2 permitting TCP and UDP only) | **4** | Never automatic. Can't fix: notify | not applicable | not applicable | A security control's removal is a security decision; removing an attacker's or an auditor's ACL automatically is the worst failure an auto-remediation can have |
| **credentials and AAA** (`username`, `enable secret`, `aaa`, `snmp-server community`, keys and key chains, `crypto`) | none in the set | **4** | Never. Can't fix: notify | not applicable | not applicable | CLAUDE.md: a deploy may add an account, never change one; rotation and break-glass have their own operations (`modules/nsot/credential_rotation.py`, `modules/breakglass.py`) |
| **Mercury's management path** (the management interface's stanza, vty, `ip ssh`, a route that may be the manager's, any program with a non-empty `reach_lost`) | C4 too (Gi2 carries r6's management address); R3 as the sheet draws it (section 15) | **4** | Never. Can't fix: "the fix would cut Mercury's path" | not applicable | not applicable | CLAUDE.md: a change to the path the tool reaches a device on needs a repair route independent of that path, and none is built (`removal._refusal`, `_management_routes`) |
| **multi-device**: the cause spans devices (both ends of a link departed in one incident window; a duplicate shared by two devices) | none in the set (R8's duplicate is one device's departure) | **4** | Never. Can't fix: notify | not applicable | not applicable | A multi-device change has an ordering and a partial state no single-device heal can verify |
| **unmeasured removal shape** (an added line with no `exact` measurement on the platform) | I1's lines; R3's until measured | as its kind, and **can't fix** until measured | Can't fix, naming `scripts/nmas-removal-probe` | not applicable | not applicable | "Allowed only where measured" (removal.py): being wrong here destroys configuration |

**Mixed incidents:** a device whose departure holds units of several kinds takes the strictest
tier among them. C4's ACL stanza and its binding are both Tier 4, so the incident is Tier 4.
A Tier 1 missing line beside a Tier 4 ACL is not healed alone: a partial heal leaves a state
nobody verified.

---

## 6. Hard stops and guards

All are per network and **the network's own, never inherited from Default**
(`settings_scope.OWN_ONLY`, as `network_stage` and `sdn_controllers` are). Enabling healing on
Default must not enable it on every network that inherits. A guard that cannot be read refuses
the heal and says so: it fails closed, never open. The order below is the order of the checks;
the first that applies is named in the step log with both operands.

| # | Guard | Setting (default) | Why |
|---|---|---|---|
| 1 | **The kill switch:** self-healing stopped everywhere | installation `heal_stopped` (off), with who, when and why | IBN_DESIGN section 3's global kill switch, and 17.7 item 8. One control stops every policy at once |
| 2 | **The network's mode** | `heal_mode`: `off`, `dry_run` or `auto` (`off`) | Off by default. AUTO only on a network marked lab (C2009's guard, `sdn.modes.stage`) until 17.7's gate, with a reason and an expiry (N8) |
| 3 | **Planned work**: a planned window, a device held, a no-change window | none; always on | `restarts.explained_by` and `holding`, `device_ops.held`, `change_windows.holding`. A deviation seen inside a window is checked again after the window's end plus `restarts.SETTLE_SECONDS` (PHASE8_PLAN 20.2 item 4) |
| 4 | **The device's golden departs from its intent** | none; always on | Section 2: nothing approved to heal to |
| 5 | **A recent change** to the device or a device intent names as its neighbour: a Mercury receipt (deploy, restore, rotation), an onboarding or retirement in the network, or a change in the observed link set (the `topology-graph` reader) | `heal_topology_hold_minutes` (60; N3) | A heal must not fight a rollout or a re-cabling in progress |
| 6 | **Many devices at once**: more than N devices of the network departing within one grace period | `heal_max_devices_drifting` (3) | A fleet-wide departure is a bad rollout, a template or a systemic event: escalate and do not heal (the operator's hard stop) |
| 7 | **A person working**: N or more outside CONFIG_I lines on the device in M minutes | `heal_person_working_changes` (3) in `heal_person_working_minutes` (10) | Protects active work (IBN_DESIGN 11, sub-rule 5). The device is held, with "a person appears to be working on r4", and notified |
| 8 | **The grace period** | `heal_grace_seconds` (900 by default; 120 on a network marked lab, N1) | A deviation must persist: PHASE8_PLAN section 7's "2 readings and 15 minutes" |
| 9 | **Rate: per device** | `heal_max_per_device_hour` (1) | Section 7's rail. Past it: **stop and escalate**, "flapping beyond the rate limit" |
| 10 | **Rate: per network** | `heal_max_per_network_hour` (6) | Section 7's rail. Past it, the network's policy halts until a person lifts it |
| 11 | **The same deviation healed twice** | `heal_repeat_halts_hours` (24) | Section 7: the same deviation fixed twice in 24 hours halts its policy. Something keeps re-applying it |
| 12 | **The program's size** | `heal_max_removed_units` (1), `heal_max_units` (one section) | **A removal is one added line** (the operator's Tier 1: "remove one added line not in intent where reversible and verifiable"): at most one removal unit a heal. A re-applied missing section (a merge) may be several lines of one section (M6's applet is 3), since a merge only restores what intent holds. **R3 adds two lines** (the authentication mode and its key): decision N13 says how it is counted |
| 13 | **The tier** (section 5) | `heal_kinds_auto` (none), `heal_kinds_propose` (every Tier 2 kind) | Each Tier 1 kind is allowed on its own, after its lab scenario passes (section 7) |
| 14 | **A rolled-back heal** | none; always on | IBN_DESIGN section 3: a rolled-back fix halts the policy until a person lifts it (**Lift the halt…**, with a reason) |

**Halts and stops are themselves Needs attention rows** (section 9). Each names the guard, both
operands and its one action.

---

## 7. Dry run, and the enablement path

**Dry run** is IBN_DESIGN section 3's observe mode, built for the first time here; NSOT_PLAN
section 9's "would have converged" records are not built yet.
- **Every step runs except the apply:** detect, decide, the program and its hash, the guards.
- **The record:** "would have healed r4: remove 1 line (added line, Tier 1), program
  <hash>; verify would read: IP SLA 1 passing, the line gone". Its kind is **dry run**, on
  History.
- **The device's ordinary drift row carries it** (`attach_to`), so a person resolving the drift
  sees what the heal would have done.
- **Right or wrong:** a person marks each record right or wrong (one control on the record). The
  marks are counted per fix kind, as the false-positive rate.

**The enablement path, per fix kind** (Lab 10's decision 1):
1. **Dry run on the lab network,** each kind's lab scenario run (section 15). The record must
   name the right units, the right tier and the right verify.
2. **AUTO for that kind on a network marked lab,** its scenario run again: healed, verified,
   golden re-checked, recorded, notified.
3. **Only then may that kind be allowed on Default,** which is the operator's decision (N8).
   Each kind is allowed on its own; one passing kind never allows another.
4. **Production needs a longer dry run:** PHASE8_PLAN section 7's bar for a Respond class (1%
   false positives or fewer over at least 30 days and 100 "would have fixed" events), and
   17.7's gate (C2009 to C2017). **Lab drills never count as production evidence** (section 7).
   The Self-healing tab says so beside the mode, and the dry-run counter shows days and events
   against that bar.

---

## 8. The step log and the records

**The step log is one record per incident.** It is append-only, owner-only, and kept in
Mercury's records store beside receipts. It uses the records database where it is on, with the
file fallback (`receipts.on_database`'s pattern), so one store holds Mercury's records
(MERCURY_CHARTER, "Mercury's own records").
- **Each step:** what was checked, what was read (named, never the raw text), its result, and
  the time, in the words a person reads (section 9, artboard C).
- **Configuration lines are masked** (`redact.redact_text`). The program is held as masked
  lines and its hash.

**History:** a new source in `modules/history_sources.py`, kind **heal**, its marks **healed**,
**would heal**, **proposed**, **can't fix**, **held** and **halted**.
- A device's History tab draws the same rows (tests/test_history_one_timeline.py's rule).
- An incident's line expands to its step log.
- The receipt and the golden commit stay their own rows, linked from the step log.

**Commit and receipt.**
- **Trailers:** `Source: heal_to_intent` (a slug, `repo.SOURCE_SLUG`); `Actor:` the policy's
  setter (who is accountable); `Actor-Verified:` a new value, **`policy`**, naming the policy
  record the authority stands on.
- **Why the new value:** today a background job's commit reads `none`
  (`identity.actor_verification`), which is true and says nothing about the authority. Adding it
  touches tests/test_actor_verified_trailer.py.
- **A Tier 2 approval** is the person's, with `Actor-Verified: access`.

**The golden re-check ("the documentation, tested").**
- After the golden commit, `drift_check.check_device` reads the device again. It must find it
  at the new golden, and `intent_match` must find it matching.
- Both results are steps in the log: "golden <sha> committed; read again 14:07:12: at its
  golden; intent: matching".
- A re-check that differs makes the incident partial (amber): the documentation is not true.

**The change record.**
- **Deterministic, no AI call:** the format of board CR (Summary, Scope, Risk, Implementation,
  Verification, Rollback plan, Window and approver, Status).
- **Filled from code:** `change_record.facts`, `change_record.risk` and
  `change_record.markdown` (`modules/ai/change_record.py`, its fact functions, which make no
  call). Mercury's code writes the Summary from the step log's words.
- **Window and approver** name the policy, who set it and when, and its fingerprint.
- **Downloadable from the incident** as .md.

**The NetBox journal entry.**
- **It does not exist today.** No code writes `extras/journal-entries/` (searched: `journal`
  appears only for systemd's journal).
- **New:** `netbox_client.add_journal_entry(session, base, device_id, kind, comments)`,
  through the `_nb_post` chokepoint, under `netbox_guard.for_list(list, actor=…,
  authority="heal policy <id>")` (C155's declared authority) and the master switch
  `netbox_allow_writes`.
- **When writes are off, or the network's inventory is local** (no NetBox device id), the step
  says "not written: <why>". The heal is not failed for it.
- **The entry's text:** the incident's summary in words, its kind (success, warning or danger),
  and a link to the incident. Never a configuration value.
- **Never deleted.** A journal entry is recorded as created, and deleting a list never deletes
  NetBox objects (tests/test_list_delete_never_touches_netbox.py).
- **Before building:** whether `_with_managed_tag` applies to a journal entry is read from the
  lab's NetBox API first (`netbox_client.missing_views`'s pattern), never assumed.

---

## 9. Settings (per network) and the screens

**No new screen without a signed-off mockup** (CLAUDE.md). The mockups are
`docs/boards/heal-to-intent.html`, artboards A to G. Every new screen gets a manual page and a
"How does this work?" link.

| Artboard | Screen or card | What it holds |
|---|---|---|
| A | **Settings · <network> › Self-healing** (a new tab beside Integrations and Network) | The mode (Off, Dry run, Auto) with the stage guard, its reason and expiry; the tier table per fix kind, each Tier 1 kind's Auto allowed or dry run, Tier 2 proposed, Tiers 3 and 4 drawn fixed with why; the hard stops, each value with its default and Edit; the dry-run counter against section 7's bar; who receives the network's notices; **Stop self-healing everywhere** (the installation's kill switch). A change opens its preview ("What this changes"), confirmed by hash as a verified person with a reason |
| B | **Settings › Installation › Notifications** (a new tab) | The email relay, the webhooks, the teams (section 10), each with Test send, a verification code for each address, and the delivery log's link |
| C | **History, a heal incident's step log** | The summary head (counts by outcome, grouped, filterable: the large-fleet rule); an incident expanded: the trigger, each step, the program (masked) and its hash, verify's checks, the records (receipt, golden commit, the re-check, the change record, the NetBox journal, the notifications sent); a dry-run record with Right / Wrong |
| D | **Needs attention: a can't-fix row** (C4) | One line; opened: What to do first, then Mercury's facts (detected, steps tried, results), then the AI analysis, advisory (section 12) |
| E | **Needs attention: a Tier 2 proposal waiting** (R8), and a halt | The program and its hash, what it resets, **Approve…** and **Decline…**; the halted policy's **Lift the halt…** |
| F | **The email and the webhook** as received | Facts first, then the advisory block; the "analysis pending" message and its follow-up; the failed state |
| G | **Settings › Installation › AI, the background feature's switch** | "Self-healing: AI analysis of what it could not fix", per network, with its labelled estimate, its caps and Turn on (the existing switch, board AI3's pattern) |

**New Needs attention row kinds** (`attention.ROW_KINDS`, with each `CLEARS` entry):

| Kind | What is wrong | Action | Clears when |
|---|---|---|---|
| `heal`/`cant_fix` | self-healing could not fix a device's problem | read what Mercury tried, then the action the reason names (adopt into intent, capture, check the link, or approve or decline the proposal) | resolves: a later check finds the device at intent and the symptom gone; or acknowledged with a reason |
| `heal`/`proposal` | a fix that needs a person waits (Tier 2) | Approve… (confirm by hash, a reason) or Decline… | resolves: approved and verified, or the device back at intent; acknowledged: declined with a reason |
| `heal`/`halted` | self-healing stopped on a network (a rate cap, a repeat, a rollback, the kill switch) | read why, then **Lift the halt…** with a reason | resolves: lifted |
| `heal`/`held` | a device is held from healing (a person working, its golden departs from intent, many devices drifting) | resolve what the hold names | resolves: the condition clears at a later check |
| `notify`/`failed` | a notification could not be delivered | read the delivery log's error, fix the relay or the webhook, Test send | resolves: the next delivery to that channel succeeds; or acknowledged |
| `heal`/`analysis_capped` (section 12) | the AI analysis stopped at its cap | raise the cap in Settings › AI, or leave it off | resolves: the cap's period ends or a person changes it |

**A healed incident is not a row.** It is History, plus a notice (section 10). Needs attention
holds only what a person can act on (20.5).

**Never let a wrong thing look like a working thing** (each state, and what makes it visible):
- **Dry run believed to be Auto.** The mode chip is on every heal record and row, and the drift
  row says "self-healing: dry run on Default".
- **Healing off believed on.** The drift row says "self-healing is off for Default".
- **Configuration healed, symptom still there.** Amber, "symptom remains", never green.
- **Healed, but its golden commit or re-check failed.** Partial, amber.
- **Healed, but its notice not delivered.** The `notify`/`failed` row.
- **An analysis that did not run.** Its state said in the message: off, capped, failed or
  refused.

---

## 10. Notifications: the lean first slice of PHASE8_PLAN 20.7

**Not a second design.** It is 20.7's model with only the parts Lab 10 needs:
- teams, each a named group with its own addresses and webhooks;
- several recipients per team;
- every address verified by a code before use, each enabled on its own;
- test send;
- the egress mask, minimal detail and a link;
- each channel's delivery log in History;
- a failure to notify raised;
- a storm sent as one message per incident, with a resolve notice.

Left for 20.7's full build, unchanged: per-person contacts, phones and SMS, ntfy, routing by
severity and device group, quiet hours, on-call schedules and escalation chains. **SMS and
phone come later, through those services** (Lab 10's decision 2).

**Email.**
- **The relay:** a minimal SMTP client, Python's standard `smtplib`, so there is no new
  third-party package or licence. It sends through the installation's relay: host, port, TLS
  required (STARTTLS or implicit; plain only to a relay on this host's loopback), a username,
  and a password the operator types (the Phase 7 mode's secrets rule). The password is stored
  through `secrets_store` and never drawn back.
- **Recipients:** several addresses per team.
- **Messages:** one per incident event (opened, proposal, halted, cleared). A follow-up carries
  `In-Reply-To` and `References`, so mail clients thread it.

**Webhooks**, several per team, with four formats:
- **Generic, signed:** JSON with the incident's id, network, device, kind, outcome, step
  summary and link. Its headers carry `X-Mercury-Timestamp` and an HMAC-SHA256 signature over
  the timestamp and the body (`X-Mercury-Signature: sha256=…`), its secret typed by the
  operator. A receiver refuses a timestamp older than 5 minutes.
- **Slack-compatible:** an incoming webhook's `text` and blocks.
- **Teams-compatible:** a message card.
- **PagerDuty Events v2:** a `trigger` on can't-fix, an `acknowledge` on approval, a `resolve`
  on clear, deduplicated by the incident's id.
- The URL of a Slack, Teams or PagerDuty webhook, or its routing key, is its secret, typed by
  the operator and drawn masked.

**What a message carries.** It is masked by `redact.egress_payload` on every byte.
- **Mercury's facts first:** detected what and when; each step tried and its result; the
  outcome; what to do.
- **Then, on a can't-fix, the AI analysis** (section 12).
- **Then the link.**
- **Configuration lines are never in a message:** each unit is said by kind ("inbound ACL added
  on Gi2, 2 lines, content withheld"). The full masked lines are one click away in Mercury.
  This is 20.7's minimal detail plus a link, and data minimisation.

**Which events notify** (per network, `heal_notify_*`, each on by default where a team is set):
- can't fix;
- a proposal waiting;
- halted or held;
- **every automatic heal**: 17.7 item 6, "notification of every autonomous action", short,
  "healed, verified";
- a cleared incident, as the resolve notice.

**Delivery.**
- **The log:** each attempt is a row in History, kind **notification**, with its channel,
  recipient (masked to its domain), outcome and error.
- **Retries:** three, at about 2.5 times the measured send time.
- **A last failure** raises `notify`/`failed`.
- **Egress is data off the host.** That is the irreversible tier: its hand check, with the
  changed lines' mutants applied by hand, a must-die canary and docs/TIER_HAND_CHECK.md's log,
  comes before its deploy (CLAUDE.md, "Mutation is a weekly measurement", the sprint's rule).

**Outside the lab.** Choosing a relay or a chat workspace, and the addresses, are the operator's
(the Phase 7 mode's stop 2). The walks use the operator's relay.

---

## 11. The device-operation lifecycle rule, for an automatic heal

CLAUDE.md: "preview (the exact program, masked) → confirm by hash as a verified person → apply
holding the device → verify → rollback on failure → record". For a heal it holds like this:

| Stage | A person's deploy | An automatic heal |
|---|---|---|
| **Preview** | the deploy card's program, masked | the heal's own program from its own read (`routes.deploy._program`), masked, written to the step log before anything is sent |
| **Confirm by hash, as a verified person** | the person presses Deploy, bound to the program's hash | **Two hashes. The decision is the operator's standing policy:** a verified person previewed and confirmed the network's policy by its fingerprint (the mode, the kinds allowed, the guards), recorded with who, when, the reason and the expiry. Each heal records its program's hash (`deploy.command_fingerprint`) before the apply, and the apply recomputes it from the stage-4 read and refuses if it moved (tests/test_deploy_contract.py's property). A Tier 2 heal is a person's confirm by hash, as today |
| **Apply, holding the device** | `apply_batch` holding it (`device_ops`) | the same call, the same hold |
| **Verify** | `pipeline._stage_verify` | the same, plus the symptom and the intent re-check (section 4) |
| **Rollback** | `pipeline._stage_rollback` | the same, and the policy halts |
| **Record** | receipt, golden commit, History | the same, plus the step log, the change record, the golden re-check and the NetBox journal |

"Mercury automates labour; people make decisions": the decisions are setting the policy,
allowing each kind, approving a Tier 2 fix, lifting a halt and acknowledging a can't-fix. The
labour is the manual revert at the console, the capture-then-restore, and writing the ticket.
docs/MANUAL_STEPS.md gains the heal's rows when it is built.

`modules/operation_stages.py` holds confirm routes. The Tier 2 approve route is declared there.
The automatic heal has no route, so a new table there (`JOBS`) names its five stages, held by
tests/test_operation_stages.py.

---

## 12. The AI analysis of a can't-fix (the operator's addition, 2026-11-03)

**What it is.** When a heal stops at can't fix, the engineer's notification includes an AI
analysis: a hypothesis and a recommended next step, cited from the evidence. **It advises
only.**
- **Nothing in the heal loop reads its output.** Detect, decide, act, verify and record never
  import or read the analysis.
- **No fix is ever chosen or run from AI text.**
- **Mechanised:** a test parses `modules/heal/` and refuses any reference from the loop's
  modules to `modules.ai` or to the incident's `analysis` field. Only the notifier and the
  pages draw it.

**A background AI call under CLAUDE.md's "AI cost safety" rules** (PHASE8_PLAN 18.3):
- **Its trigger is named:** `triggers.background("heal_analysis", job, network,
  "heal_incident", <incident id>)`.
- **The finding is the deterministic one:** the heal loop stopped at can't fix (rule 5). Nothing
  else triggers it: not a healed incident, not a dry-run record, not a proposal.
- **Its feature,** `heal_analysis`, is a new entry in `background.FEATURES`: its task pin, its
  words ("Self-healing analyses what it could not fix"), its trigger words ("a heal stops at
  can't fix"), `findings` `("heal_incident",)`, `calls_per_finding` 1, and its frequency
  measured from the heal's own incident record (can't-fix incidents a day, for the network).
- **Off by default per network.** It is turned on only in Settings › Installation › AI, by an
  admin, after `background.estimate` has shown the labelled estimate: calls a day, and dollars a
  day and a month, from the measured cost per call. It records who, when and the estimate.
  `background.turn_on` refuses if the estimate moved. **The operator turns it on for Default for
  the lab.**
- **Its own budget class:** daily and monthly caps within the installation's cap
  (`background.over_cap`). A cap reached stops the feature and raises `heal`/`analysis_capped`.
  The 50% and 80% warnings, and the approval's 14-day end (`APPROVAL_DAYS`), are the existing
  rules. **Proposed caps:** $1.00 a day and $10.00 a month on Default. At Explain's measured
  $0.0257 an answer (PHASE8_PLAN 0.5), that is about 38 analyses a day. The lab walks expect
  about 5 a day.
- **Shown in the spend tracker** (`spend.feature_summaries`): the chip's "N background on"
  counts it, and the panel shows its trigger, its estimate against actual, and Turn off.
- **The gateway refuses it, recorded, with no provider request,** when the feature is off for
  the network, past a cap, or hosted AI is off (`gateway.hosted_allowed`).

**Its input.**
- **The incident's evidence pack:** `evidence_pack`'s sections as built for an alert. A
  can't-fix that started from a CONFIG_I or the schedule has no alert, so a pack is built for
  the incident (new, `build_incident`, as `build_detection` builds one for an SDN detection),
  captured at the incident's time.
- **A new section, "what Mercury tried"** (new, `tried`), with each step and its result from the
  step log. Every piece has its own reference (`tried:<step>`), so the analysis cites it and
  Explain's check resolves it.
- **The prompt and the check are Explain's** (`modules/ai/explain.py`):
  - shape B, a rationale then `{hypotheses: [{claim, evidence_refs, confirm_with}],
    needs_human}`;
  - every reference must resolve to what was sent;
  - every `confirm_with` must be a read on the read-only allowlist (`readonly_commands`);
  - uncited devices are refused (C1897).
  It runs as its own task and prompt version, so its measurement is its own.

**Egress, by kind.**
- **The step log's configuration lines never leave as text.** Each is sent masked and by kind:
  "inbound ACL added on Gi2, 2 lines, content withheld", "static route added, 1 line, content
  withheld". The configuration class (15.11) is off on every network until C1720, so the
  by-kind form is the only form for now. Once a network enables the configuration class, the
  lines go as 15.11's conditions allow: masked, a secret's line dropped whole.
- **The pack's own sections go as Explain's do,** under the allowed and topology classes
  (`egress_classes.topology_allowed`). That includes the intent section's masked intent-diff
  lines, at most 20, decided 2026-10-29 and hand-checked. **This is the one place a masked
  configuration line can leave in this feature: N10 asks the operator to confirm it, or to
  withhold it too.**
- **The gateway's egress mask** (`redact.egress_payload`) covers every byte. That is the
  irreversible tier: its hand check, logged in docs/TIER_HAND_CHECK.md.

**Never delaying the notification.**
- **The wait:** the notifier waits up to `heal_analysis_wait_seconds` (60, the operator's
  bound) for the analysis.
- **Back in time:** the message carries it.
- **Not back:** the message goes without it, saying **"AI analysis: pending"**. When the
  analysis arrives, a follow-up goes on the same thread (email `In-Reply-To`; a webhook's
  second event with the incident's id).
- **A failure or refusal is stated in place:**
  - "AI analysis: not run, off for this network";
  - "not run, its cap for today is reached";
  - "couldn't analyse: <the check's reason>";
  - "the provider did not answer within <bound>".
  A failure is never a silent absence.
- **The 60 s against Explain's measured answer time:** Explain's answer time on the host is
  measured before the build (an existing recorded figure is not assumed), and the wait is
  checked against it. If the median is above 60 s, most messages will carry "pending", and the
  board says so.

**What is stored, and where.**
- **The analysis is stored with the incident:** the call's id (History's AI calls, 15.14), its
  state, its answer and its beta label.
- **It is shown under Needs attention's can't-fix row** in the order the operator set:
  - What to do;
  - Mercury's facts (detected, steps tried, results);
  - "AI analysis: Advisory (beta), a person should confirm", with its measured score, the
    hypothesis and the recommended next step.
- **Kept until regenerated:** **Analyse again** is a person's press (trigger `person`, behind
  its cost confirm, 15.13's AI mark). It replaces the stored analysis, and the old one stays in
  History.

**The beta label and the measurement.**
- **The label:** "Advisory (beta)" until measured. It never claims Explain's score: Explain's
  `MEASURED` is of Explain's prompt and recorded alerts, and `explain.beta` already refuses a
  figure measured on another prompt.
- **The recorded cases, three, captured in the build's lab runs:**
  - C4, won't fix: a security ACL on the management interface;
  - I5, physical: a link flapping, the configuration at intent;
  - V1, a failed verify rolled back (section 15).
- **The bar:** each case reliable over 10 runs, and none confidently wrong (15.12's
  definitions). Measured before the video, about $1 (3 cases × 10 runs at about $0.03).
- **What three cases show:** that the feature works on its three shapes. They do not show 15.12's
  done bar (about 20 recorded and a blind set of about 30 at 85%), so the label stays beta,
  with its measured figure ("3 of 3 recorded cases reliable, 10 runs each"), until the bar is
  met.

---

## 13. The never list

Never, whatever the policy says:
- **Never AUTO on a network not marked lab** until 17.7's gate is complete (C2009's guard).
- **Never during planned work,** a held device, or a no-change window.
- **Never break-glass,** and never a credential: no account, enable secret, AAA, SNMP community,
  key or key chain, crypto key, or anything rotation owns (`credential_rotation`,
  `scheduled_rotation`).
- **Never Mercury's management path,** never a program with a non-empty `reach_lost`, never the
  switch that carries the management path (s3 in this lab).
- **Never a security ACL**, its entries or its bindings.
- **Never a multi-device fix,** never more than `heal_max_units` units, never a partial heal.
- **Never an unmeasured removal shape,** never a guessed `no` form, never `default interface`.
- **Never a whole-configuration replace or a reload.**
- **Never intent the device never held** (section 2).
- **Never a heal decided, chosen or run from AI text** (section 12).
- **Never an IPv4-only path:** an IPv6 static route (`global.ipv6-route`, measured exact) and
  an OSPFv3 adjacency are healed and tested like their IPv4 forms. A webhook or relay at an IPv6
  address works (CLAUDE.md's IPv6 rule).
- **Never a staged run or probe on s3, nor inside 08:30 to 09:10 UTC** (the standing facts):
  the walks and the removal probe follow them.

---

## 14. Tests and coverage

- **A new package, `modules/heal/`,** placed as automation by `tests/coverage_scope.py`'s rule
  for `modules/`: counted, and in the coverage ratchet from its first commit.
- **Red, then green, from the start** (board TI item 1, `scripts/nmas-red-green`). Every test
  is written before its code and committed failing on its parent. No `Guards-Existing` except
  where a test pins behaviour the heal reuses unchanged (say, `drift_check.check_device`'s
  merge).
- **Unit tests, one per module:**
  - triggers: the attribution, the grace period, the fold;
  - classification: every row of section 5, each with a planted case;
  - every guard in section 6's order, each shown able to fail;
  - the program against the read, and the stage-4 refusal when the device moves;
  - verify's symptom and intent re-check, and kept-not-rolled-back;
  - the step log and the History source;
  - the change record;
  - the journal write behind the chokepoint;
  - the notifier: formats, the signature, the mask, retries, failure;
  - the AI analysis: the trigger, the precondition, by-kind egress, the 60 s pending and the
    follow-up, failure states, and the loop never reading the analysis.
- **Captured fixtures, never typed** (CLAUDE.md): each demo scenario's device reads, logs and
  reader values are captured from the dry-run walk and replayed through the whole loop, one test
  per scenario.
- **IPv6 beside IPv4** for every address the heal parses (routes, adjacencies, relay and
  webhook hosts).
- **No live network** (the three layers, C46). SMTP and webhooks are tested against loopback
  servers the test starts.
- **The coverage report for the video:**
  - `scripts/nmas-coverage report --html` over a run with contexts, filtered to
    `modules/heal/`: per function, which unit tests reached it;
  - beside it, `--summary` for the totals;
  - a red-then-green run shown on one commit (its parent red, its commit green).
- **Mutation:** the notifier's egress and the analysis's egress are the irreversible tier, so
  their hand check is logged before deploy. The heal's other modules join the weekly
  measurement.

---

## 15. The demo plan, from sessions 6 to 8's scenarios

Each scenario is the operator's sheet (outside the repository), run as written except where
this table says. **The change is made at the device's CLI by the operator, as the sheet's.** The
revert is the heal's, not the sheet's, except where nothing is healed. A planned order respects
the rails (one heal per device per hour, six per network per hour), never on s3, never inside
08:30 to 09:10 UTC.

| # | Scenario (sheet) | Device | What the heal detects | Tier | What it does | What verify reads | What the person sees |
|---|---|---|---|---|---|---|---|
| 1 | **M4**: the syslog destination removed | r2 | No CONFIG_I arrives: its own line is logged after the destination is gone. The heartbeat-missing alert (about T0 + 8 to 13 min, Alerting NoData) triggers it, which needs N2. Without N2, the scheduled check finds it | 1, missing line | merge re-adds the exact `logging host` line from intent | read-back; r2's next heartbeat within 300 s; the alert resolves | History: healed; the email "healed, verified"; r2's Logs carry its lines again |
| 2 | **M6**: the EEM heartbeat applet removed | r3 | CONFIG_I at T0, not Mercury's; after the grace period r3 lacks the applet stanza | 1, missing line | merge re-adds the stanza and its two children | read-back; the next heartbeat; the episode resolves | healed before the heartbeat alert fires (T0 + 2 min with the lab's 120 s grace) |
| 3 | **C3**: a static route with a wrong next hop | r4 | CONFIG_I at T0; one added `ip route` (shape `global.ip-route`, measured exact); not the manager's path (`_management_routes`) | 1, added line | Mode B: `no` plus the device's own line | read-back (the line gone); IP SLA 1 on r4 passing again; r1's probe too (folded) | healed; the probe alert may fire and resolve; the change record downloadable |
| 4 | **C1**: an OSPF `network` statement removed | r8 | CONFIG_I on r8; s5's "Device unreachable" folds in (s5 is in r8's blast radius) | 1, missing line | merge re-adds the statement under `router ospf` | read-back; s5 reachable (the attached device); r8's adjacency to r2 unchanged | one incident, r8, with s5 under it; never a separate s5 can't-fix |
| 5 | **R3**: OSPF authentication added on one end. **Changed (N7):** run on the r3–r4 link's Gi4, which carries no management (I5's sheet says so), not r6 Gi2, which carries r6's management address (C4's sheet) | r3 or r4 | CONFIG_I; two added lines on one interface (`ip ospf authentication message-digest`, `ip ospf message-digest-key … md5 <masked>`), each a shape measured first by `scripts/nmas-removal-probe` on r2 (IOS-XE) | 1, added line (a routing key removed, N9) | Mode B: both lines' `no` forms, the key's masked in every record | read-back; the adjacency FULL on both ends | healed; the key never drawn |
| 6 | **R8**: r6 given r4's router-id, the process reset | r6 | CONFIG_I; `router-id` changed (a changed line), effective only through a process reset | **2, propose** | the proposal: merge sets intent's router-id, then the measured OSPF reset, one hash | on approval: adjacencies re-form; no DUP_RTRID logged | Needs attention: "A fix waits for a person: r6's OSPF router-id"; the email "proposal waiting"; Approve… by hash, then healed |
| 7 | **C4**: an inbound ACL permitting TCP and UDP only, on r6 Gi2. **The "won't fix, notifies" demo** | r6 | CONFIG_I; an extended ACL stanza and its `ip access-group … in` on Gi2; r7's unreachable folds in | **4** (a security ACL, and Gi2 is Mercury's path to r6) | nothing sent | not applicable | Needs attention: "Self-healing will not fix r6: a security ACL was added outside intent, on the interface Mercury reaches r6 by". Opened: What to do; Mercury's facts (the 7 steps); then the AI analysis, advisory. The email in the same order |
| 8 | **I5**: a link flapping, made from r4's side by its Tcl loop. **The can't-fix (physical)** | r3, r4 | r3's "Interface down" (port down, admin up) checks r3, at intent: physical. r4's repeated CONFIG_I from the loop hold r4 ("a person appears to be working", guard 7) | **3** | nothing sent | not applicable | one incident on the link: r3 physical, r4 held; the email "can't fix: Gi4 down while administratively up, configuration at intent"; the AI analysis, advisory |
| 9 | **V1**, new: **a failed verify, rolled back** (the third recorded case for the analysis) | an IOS-XE router chosen from the lab's committed intent | an OSPF `network` statement added outside intent for a link whose far end already runs OSPF, so an adjacency forms that intent does not describe (shape `ospf.network`, measured first) | 1, added line | Mode B removes it | verify sees the adjacency drop (tolerance 0, settle window) and rolls back; the policy halts | **An unpredicted side effect, so Mercury undid its own fix: the safety behaviour.** Needs attention: "Self-healing rolled back on <device>: removing the added line dropped an OSPF adjacency it did not predict"; the halt's row; the analysis. **Checked in review (2026-11-03):** `expected_effects.for_device` predicts an OSPF drop only for an interface the program takes down (`adjacencies_drop`, from intent's adjacencies via the interfaces in `down`). Removing a `network` statement takes no interface down, and the adjacency it formed is not in intent, so nothing predicts the drop, and verify rolls back. Its sheet is written after reading the lab's intent for a link that fits; if none does, it is said, not staged |

**The video's beats** (Nov 20 to 22): two heals (C3 and M6), with History's step log and the
golden re-check; the R8 proposal and its approval; C4 won't fix, its row and email with the AI
analysis; I5 physical; V1 rolled back; the unit tests and the coverage report; the
documentation examples (the golden commit, the change record, the NetBox journal entry and
History).

---

## 16. The build estimate, in days

Agent-days, each part's tests written with it, red then green.

**Through the measured ratio** (C2380, the operator, 2026-11-03): one agent-day is about 1.3
wall-clock hours for one agent (0.7 to 2.6) and about 4M weighted tokens (2.5M to 9M).
- **The 16.25 days:**
  - stream A (9.25) is about 12 hours, and stream B (7.0) about 9;
  - with about 13 parts × 1.5 gates × 17 minutes, the critical path is 14 to 18 hours (8 to 28
    across the range);
  - about 65M weighted tokens (40M to 150M), roughly 5% of a week's usage (3 to 12%).
- The ten-day window below is therefore not the limit.

| Part | What | Days |
|---|---|---|
| H1 | The policy store and settings (OWN_ONLY), the mode with C2009's guard and its expiry, the change previewed and confirmed by hash, the kill switch | 1.0 |
| H2 | Triggers: after-store steps on `logs-tail`, `grafana-alerts`, `adjacencies`, `adjacency-log` and the drift record; the CONFIG_I attribution; the grace period; one incident per cause (the blast-radius fold); the per-network lock | 1.25 |
| H3 | Decide: units into fix kinds, the tier table, the intersection rule, the guards in order, the dry-run record and its Right / Wrong | 1.5 |
| H4 | Act and verify: planning against the heal's read (the capture source for `plan_devices` and `_program`, the stage-4 comparison), `apply_batch` as the policy, the symptom re-read, the intent and golden re-checks | 1.5 |
| H5 | Tier 2: the proposal, its approve and decline routes (gated, declared, invalidated), and the measured OSPF process reset (privileged's pattern, measured on r2 and s1) | 1.25 |
| H6 | Records: the step log store, the History source, the trailers (`Actor-Verified: policy`), the deterministic change record, the NetBox journal write | 1.5 |
| H7 | Notifications: relay, webhooks in four formats (generic signed), teams, verification codes, test send, the delivery log, `notify`/`failed`, the egress mask, the irreversible-tier hand check | 2.0 |
| H8 | The AI analysis: the background feature, the incident pack and its `tried` section, the task, prompt and schema, the check, the 60 s wait with pending and follow-up, the store, its blocks on the row and in the email, the loop-never-reads test, the egress-by-kind hand check | 2.0 |
| H9 | Screens: the Self-healing tab, Installation › Notifications, the History step log, the Needs attention rows; fidelity records and board shots at 1440, 1280 and phone width | 1.75 |
| H10 | The manual: how-it-works pages for the heal and for notifications, their diagrams, "How does this work?" links, the MANUAL_STEPS rows | 0.75 |
| H11 | Lab measurements: the removal probe for the OSPF authentication shapes and `ospf.network` (r2, s1); the dry-run walk of each kind, capturing the fixtures | 0.5 |
| H12 | The scenario replays as tests (one per demo scenario through the whole loop) and the coverage report | 0.75 |
| H13 | The AI analysis's measurement: 3 recorded cases × 10 runs (about $1) | 0.5 |
| | **Total** | **16.25** |

**Against the window.** The build window is Nov 5 to 14, ten calendar days: an expectation, not
a start date. The build starts as soon as local CI and this board's commit are done, and
finishing early is the goal. 16.25 agent-days
fits only as **two code agents in parallel** (the standing limit, at most two):
- **stream A:** H1 to H6, H11, H12;
- **stream B:** H7, H8, H9, H10, H13.

They share H4's apply and H6's step log, so B starts with H7 (independent), and H8 takes the
step log after H6 lands. **Applied only when an item is actually behind, and said in the report
when it is** (the operator, 2026-11-03). The build is on track, so H7's Slack, Teams and
PagerDuty formats are deferred to after Lab 10, not cut (C2387), and built early if H8 or H9
finish early. **The cut list, in order, if the build runs behind** (each said where
it is cut):
1. the webhook formats: Teams', PagerDuty's, Slack's, then the generic one (email alone meets
   the lab);
2. verification codes (test send only, its absence said on the card);
3. the measured OSPF reset (R8's proposal applies the router-id and offers Mercury's Reload in a
   planned window instead);
4. last, the installation's kill switch. **Each network's Turn off is already a one-click stop
   for all healing on that network:** one press, no confirm, effective at once and recorded with
   who and when. A heal already applying finishes its own verify and rollback; nothing new
   starts. Turning a network back on is previewed and confirmed by hash. (The operator, 2026-11-03:
   "keep the kill switch. If the per-network enable is already a one-click stop for all healing on
   that network, say so, and then the installation-wide switch may go last.")

The heal loop, its guards, its records and C4's notification are never cut.

**Spend:** about $1 for H13, and about $2 for the analyses during the walks and the video,
inside the $161 left (PHASE8_PLAN 0.5).

---

## 17. The schedule shift (PHASE8_PLAN 0.3's weeks)

**The dates.** Lab 10 is due **Mon 2026-11-23 23:59 MT (2026-11-24 06:59 UTC)**. The operator's
schedule: board Nov 3 to 5; build Nov 5 to 14; walks Nov 15 to 19; video Nov 20 to 22.

**The rules that decide the order:**
- a course lab's due date is a dependency (CLAUDE.md, "Sequence by dependency");
- a lab step wins over video and AI work;
- the credit expires 11-29, so the AI measurement rounds must land before it (0.5);
- no deploy during a sitting; nothing in 08:30 to 09:10 UTC.

**Superseded in review (2026-11-03): the operator's roadmap through 2026-11-30 replaces
PHASE8_PLAN 0.3's schedule.** Its order is: workstream 0, local CI, first; Lab 10 (this board),
with its build Nov 5 to 14, walks Nov 15 to 19, and video and submission Nov 20 to 23; Lab 9,
the final SDN lab, due Nov 30, beside it; C2305 right after this board; board TI items 4 to 7
and the test audit at low priority; the rest of Phase 8 behind both labs. Sessions 9 to 11 come
after both labs. The table this section held is withdrawn. N11 (Phase 8's end) is no longer
this board's to propose.

**The risk, said early:**
- **The load:** this board's build is 16.25 agent-days (section 16), in a 10-day window shared
  with Lab 9's laptop install, C2305 and the multi-vendor drivers (Nov 5 to 14).
- **What fits:** both fit only with the two code agents working both labs in parallel from Nov
  5, and the build is tight.
- **The cut order if it runs behind** (the operator, 2026-11-03; section 16):
  1. the webhook formats (email alone meets the lab);
  2. the verification codes;
  3. the measured OSPF reset (R8 stays a Tier 2 proposal that Mercury cannot run);
  4. last, the installation-wide kill switch, since each network's Turn off is a one-click stop.

  Each cut keeps the lab's requirements.
- **Usage:** two parallel agents roughly double it. The two-agent work is front-loaded into
  Nov 5 to 7, before the weekly reset on Sunday Nov 8, and each report's schedule line carries
  the usage (the operator, 2026-11-03).

---

## 18. Decisions for the operator

Only what industry practice does not decide, each with a recommendation. The tiers, notification
channels, dates, the AI analysis and its order are the operator's, decided.

| # | Decision | Recommendation |
|---|---|---|
| N1 | **The grace period.** Section 7's approved Respond number is "2 readings and 15 minutes" | **900 s by default; 120 s on a network marked lab** (two reads at least 120 s apart, no outside change between). 15 minutes would make each demo heal wait out the downstream alerts. Production keeps 15 |
| N2 | **Triggers beyond the three named** | **Add "any firing alert on a managed device"** (the alert's device is checked). M4's own CONFIG_I never arrives, so without it M4 heals only at the 4-hour schedule. Cost: one drift read per alert episode, under the same rails |
| N3 | **The topology-change window** (`heal_topology_hold_minutes`) | **60 minutes** after any Mercury change record on the device or an intent neighbour, or an observed link-set change. **Decided by the operator:** 60 minutes on a network marked lab; **4 hours as the production default** (the risk register's figure) |
| N4 | **Which ACLs count as security** | **All of them:** every ACL definition and entry, and every `access-group`, `access-class` and `ipv6 traffic-filter` binding, with no per-ACL exception in the first slice. A "non-security ACL" list is a later setting, with its own reason |
| N5 | **What "the approved state" is** | **The last golden that matched intent** (`Intent-Match: yes`), not a `baseline/<ts>` tag. The lab's baselines are earned rarely, and the golden-and-intent intersection is what makes a heal maintenance rather than a change (section 2) |
| N6 | **N per hour** | **Section 7's approved rails:** 1 heal per device per hour, 6 per network per hour, the same deviation twice in 24 hours halts the policy. The demo plan's order respects them |
| N7 | **R3's scenario on r6 Gi2**, which carries r6's management address (C4's sheet), so the heal refuses it as Mercury's management path | **Run R3's heal on the r3–r4 link's Gi4**, which carries no management (I5's sheet), and keep the management-interface refusal. A measured, management-path-neutral class of interface lines is later work |
| N8 | **AUTO's expiry, and marking the lab's network lab** | **An expiry required, at most 7 days, after which the mode returns to dry run** (never to off: the record keeps running). AUTO needs the network marked lab (C2009). **Marking Default lab, and turning AUTO on there, are the operator's**: marking it also lets SDN AUTO run there, if it ever has controllers. **Decided by the operator:** Default is marked lab and AUTO enabled there, at most 7 days per enablement, expiring to dry run; Tier 1 kinds are enabled one at a time, each after its dry-run scenario passes |
| N9 | **A line in a secret position** (R3's key) | **Removing a routing-protocol key returns to intent: Tier 1,** the line masked everywhere, the policy's words its stated reason. **Adding any secret back: Tier 2. Accounts, AAA and SNMP communities: Tier 4** |
| N10 | **The AI analysis's pack carries the intent section's masked intent-diff lines** (at most 20, the allowed class decided 2026-10-29) | **Send them, as Explain does**: without them the analysis cannot see what was added. The step log's own lines stay by kind |
| N11 | ~~Phase 8's end~~ | **Withdrawn in review:** the operator's roadmap of 2026-11-03 sets the schedule (section 17) |
| N12 | **A person's named CONFIG_I.** IBN_DESIGN 11 sub-rule 5 made it a Capture-or-Revert decision for a person | **Heal after the grace period, the person named in the record and notified;** guard 7 holds a device a person is actively working on. This is what Lab 10 asks ("no human interaction"), and agent-based configuration management works the same way. **Decided by the operator, plus maintenance mode:** a one-click "Hold this device from healing for N hours" on the device page, and "Keep this change" in the heal notice, which holds the device and raises a Capture-or-Revert row; production's 15-minute grace is the window for it |
| N13 | **How "one added line" counts R3** (added in review, 2026-11-03). R3 adds two lines on one interface, the authentication mode and its key, which only work together | **Count a removal by its unit, one feature on one interface:** R3's pair is one unit, removed together and restored together. Practice treats a configuration change as one atomic unit of intent, not as text lines (NETCONF's candidate commit, and the ITIL standard change's one pre-approved change). Otherwise R3 is Tier 2, proposed and waiting, and the lab's Tier 1 removal demo is C3's one line alone. **Decided by the operator, 2026-11-03:**
- **Tier 1 removes one feature on one interface:** the lines the parser groups as one feature on that interface, not by guesswork.
- **Verify reads the feature's effect** (the adjacency up), not just the lines' absence.
- **The removed lines are kept,** so a failed verify re-adds them. |

**Earlier decisions this design narrows** (the operator's own, listed so that confirming the
board confirms these readings):
- **IBN_DESIGN decision 2** said only management-plane lines may auto-fix: never routing,
  interface state or ACLs. **Narrowed for a network marked lab:** Tier 1 includes routing lines
  (C1, C3, R3) and admin state; ACLs stay never.
- **IBN_DESIGN 11, sub-rule 5:** see N12.
- **PHASE8_PLAN 15.2** made closed-loop execution Phase 9's, and **section 7** set the enabling
  bar. **Narrowed:** heal AUTO runs on a network marked lab only, under C2009's guard, for Lab 10.
  Production keeps section 7's bar and 17.7's gate.
- **PHASE8_PLAN 15.6** made automatic analysis a button until its cost per accepted analysis is
  measured, then a per-rule opt-in. **Narrowed:** the can't-fix analysis is automatic on one
  finding kind, per network, off by default. Its cost per call is Explain's measured figure; its
  cost per accepted analysis is not measured yet.
- **removal.py's "Selected, never inferred"** (a person chooses each unit). **Narrowed:** the
  policy, set by a verified person per fix kind, selects in advance, measured shapes only, every
  refusal unchanged.
- **PHASE8_PLAN 17.7**, the AUTO gate. **Built in lean form for the heal:** its guard, limits
  and breaker (item 2), shadow mode as dry run (item 3), notification (item 6) and the kill
  switch (item 8). The rest of the gate stays.

**Rows to record once the operator has reviewed this** (the register is not edited by this
board):
- the heal itself (A or B, "Phase 8: blocks" Lab 10's 0.1.5, area operations);
- Mercury cannot remove a line on a device's management interface: no repair route
  independent of that path is built (C4's can't-fix names it);
- the OSPF authentication and `ospf.network` removal shapes, unmeasured;
- a measured OSPF process reset (Tier 2 privileged command);
- `Actor-Verified: policy`;
- the NetBox journal write;
- the notifier (C2128's first slice);
- the AI analysis feature (its measurement, the beta label).
