# Heal to intent (board H): the design, reviewed, and what is built of it

**Status, 2026-11-12.** Most of this design is built, and the manual says what the code does
now; where this design and the manual differ, read the manual, which is checked against the
code. Self-healing's loop, its records, its five-stage card (Detected, Decided, Fixing,
Checking, Done) and History's **Open the card**: docs/manual/how-it-works/heal.md. A heal by the
policy is "by Mercury's self-healing · policy set by" the person who confirmed it, by display
name. A heal that re-applies the heartbeat applet waits for the device's next heartbeat, up to
2.5 times the sum of the applet's interval and the logs read's 120 s (1050 s for a 300 s
applet), and is healed only when it arrives. The can't-fix message, its steps as the stepper says them, its local times, display
names and the link to the incident's page: docs/manual/how-it-works/notifications.md. The
incident's page (/v2/incident/<id>, read-only, its first slice) and its times:
docs/manual/screens/incident.md and docs/manual/how-it-works/incident-timeline.md. Fault
drills: docs/manual/how-it-works/fault-drill.md. How the tests and their coverage are run:
docs/manual/concepts/testing.md. AI troubleshooting's section on the incident's page, with no
AI call (its attempts, the STOP, Retry with more information through Mercury's own diagnosis,
Cancel and Hand over, `modules/fixit/`, section 12's rule in force over them), and its mode and
per-incident cap on Settings › Installation › AI: docs/manual/how-it-works/fixit-troubleshoot.md.
**Not built yet:** the AI call itself, and the Slack, Teams and PagerDuty webhook formats
(section 10; C2387).
The sections below are the design as reviewed, kept for its reasons.

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
decisions this narrows, and rows to record · **19 the amendment of 2026-11-03, the course's
troubleshooting lecture's additions (for the operator's review, not approved).**

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
  promote past its ceiling. Tier 4 (credentials, Mercury's own management path, multi-device)
  is never automatic, whatever is configured; a security control removed or changed outside
  intent, and any ACL, is always a person's (Tier 2, C2839).
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
| **A duplicate router-id logged** (C2446) | The `adjacency-log` reader's second query (`%OSPF-4-DUP_RTRID_NBR`, `_AREA`, `_AS` and OSPFv3's, the last hour), and its critical Needs attention row | The same after-store step: each episode checks every device that logged it and the neighbour intent names by its address; R8's verify, "no duplicate router-id logged", reads it again (`act.duplicate_logged`: no line within 165 s of a read) |
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

**An incident stands while its cause stands** (C2813, built 2026-11-08 after H11's W2, W3 and
W7: an incident closed at its decision, so a symptom arriving a minute later opened its own
incident and its own decision). `modules/heal/incidents.py` holds the states:
- **watching** (read until the grace period settles it), **ready** (settled, for the
  decision), **claimed** (the decision's, or H4's and H5's for a heal or a proposal);
- **standing**: decided, and its cause still stands: a dry run's would-heal, a can't-fix, or a
  hold a person resolves (guards 4, 6 and 9, no until). It stays open, so the fold holds for it:
  a symptom later on another device folds in (blast radius, far end) within
  `incidents.FOLD_STANDING_S` of its decision (250 s, 2.5 times W7's 99 s; later, it is judged
  on its own, so a decision that stood for days never swallows an unrelated fault), a symptom
  on its own device joins it, and a drift record of THE departure its decision judged (the
  fingerprint compared) joins it with no second decision;
- **back to watching** on any other cause (a configuration change from outside Mercury, a
  person's revert, a drift record of another departure): judged again after the grace period,
  as a ready incident is. For a departure, only the triggers from that change on are judged
  (`decide.judged_triggers`): the symptoms before it were the departure's, so a revert to the
  golden is nothing to heal, never a can't-fix on a symptom the reverted change caused. Read
  again with the same departure, it stands on its decision again (`incidents.restand`);
- **closed**, naming why: a later decision of nothing to heal; a drift run that READ the device
  at its golden after its decision (`clean_devices`, each device read clean by name with its
  read time; a run naming none ends nothing, since absence is not evidence; guard 4's hold is
  not ended by a read at the golden it departs from); for a can't-fix at its golden on a
  symptom, every symptom read gone from its stores and quiet for the flap window (the detect
  pass's `standing` step, and the can't-fix notice's diagnosis, C2825); and self-healing turned
  off. Each end is one decision of nothing to heal on the incident (`decide.end_standing`), so
  History keeps one row per incident and its Needs attention item leaves.

**One incident per device and one per cause still hold:** a standing incident is open
(`incidents.OPEN_STATES`), so its device and its members are in no other incident. Not built:
a cause arriving after a symptom-only incident was decided does not absorb it (only a watching
one is absorbed: a decided incident keeps its decision); an act's own end (healed, symptom
remains, rolled back) still closes its incident.

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
- **Never for what cleared by itself** (C2825, built 2026-11-08 after H11 W5, where a can't-fix
  and its email went out for an adjacency Mercury's own diagnosis read up at both ends):
  - at the decision, a symptom read gone inside the flap window is checked again once the
    window has passed (`decide`, deferred once: a link still flapping is a can't-fix after one
    window), and past it is nothing to heal, "cleared by itself at HH:MM UTC, nothing to do"
    (C2813's wording, the operator: "at HH:MM" for a time Mercury measured, "by HH:MM" only for
    an estimate or a deadline);
  - at the notice, a diagnosis that reads the symptom gone (`auto_diagnose.symptom_gone`: the
    adjacency runbook's "up now at both ends", the reach runbook's every probe answered, no
    hypothesis, no cap reached) is waited out to the flap window; still standing, no trigger
    since, and read gone from its stores, the incident ends cleared, with no message and no
    analysis (`heal_notice._cleared`);
  - an incident whose newest decision is nothing to heal when it would be told is not told
    (`heal_notice._withheld`); a can't-fix is told once per incident, however often a standing
    incident is judged again.

---

## 5. The tier table, per fix kind

The tiers are the operator's (Lab 10's decision 1). **A kind's tier is a ceiling in code:** the
policy may allow a Tier 1 kind to run automatically, or keep it in dry run, but it can never
move a kind to a lower-numbered tier. Tiers 3 and 4 are not settings.

| Fix kind | Example scenario | Tier | What is done | Verify reads | Rollback | Why that tier |
|---|---|---|---|---|---|---|
| **missing line** (intent and the last golden have it; the device lacks it) | M4 (the syslog destination removed, r2); M6 (the EEM heartbeat applet removed, r3); C1 (an OSPF `network` statement removed, r8) | **1** | Mode A: merge re-applies the line or stanza (`deploy.merge_commands`) | the pipeline's verify; the read-back of each line; the symptom: the heartbeat back within 300 s, the adjacency or the route back, the attached device (s5) reachable | `deploy.rollback_commands` removes what landed | Additive, merge-only, and restores a state the device ran and was verified in. The standard change in ITIL's sense |
| **changed line**, single-valued (a description, an OSPF cost, a logging level) | none in the set; a description typed at the console | **1** | Mode A: merge sets intent's value | read-back; the pipeline's verify | the prior value back, from the pre-change read | As above: one setting returned to its last verified value |
| **added line**, one section, a measured shape | C3 (a static route with a wrong next hop, r4: `global.ip-route`, measured exact on both dialects); not R3 (OSPF authentication added on one end of a link) since C2839: a security control, Tier 2 below | **1** | Mode B: `no` plus the device's own line, a shape measured exact on the platform (`removal_measured.json`), one removal unit (`heal_max_removed_units`, guard 12) | read-back: each removed line gone (`removal.still_present`); the symptom (the IP SLA probe passing; the adjacency FULL) | `removal.restore_program`: the device's own line back from the pre-change read | Reversible and verifiable, measured on the platform: "remove one added line not in intent" |
| **admin down where intent says up** | admin shut on an interface (the operator's list) | **1** | Mode B's measured `interface.shutdown` shape (exact on both dialects): `no shutdown` | the interface up; `expected_effects`' `may_form` adjacencies form | `shutdown` back | Restores a verified state; refused on the management interface (Tier 4) |
| **a fix that takes effect only through a process reset** | R8 (r6 given r4's OSPF router-id, then the OSPF process reset) | **2** | Proposed: merge sets intent's `router-id`, then a measured "reset the OSPF process" command (new, `modules/nsot/privileged.py`'s pattern, section 16, H5), one hash, a person's confirm | the adjacencies re-form; no duplicate router-id logged | the router-id back; a reset cannot be undone, and the preview says so (`privileged`'s pattern) | A reset drops every adjacency on the device, so a person decides the moment |
| **QoS policy** (`service-policy`, `policy-map`, `class-map`) | I1 (a class shaper on r2's egress) | **2** | Proposed; its removal shapes are unmeasured today, so until they are measured it is **can't fix: unmeasured removal shape** | the queue's drops; read-back | `removal.restore_program` | A shaper's effect depends on traffic, and its verification needs load, which a heal cannot know |
| **a line in a secret position, added back** (an SNMP community, a routing key intent holds) | none in the set | **2** | Proposed: CLAUDE.md, "a dangerous line or re-added secret needs a stated reason", a person's | read-back, masked | removed again | A secret is introduced only with a person's reason |
| **physical or link down while admin up**, configuration at intent | I5 (r4 Gi4 ↔ r3 Gi4 flapping) | **3** | Nothing sent. Can't fix: notify with the step log | not applicable | not applicable | Configuration cannot fix a cable, an optic or a far end |
| **unknown cause**: a symptom with both ends at intent | an adjacency down, both routers matching | **3** | Nothing sent. Can't fix: notify | not applicable | not applicable | No departure to heal; guessing is not a fix |
| **security ACL drift** (any ACL definition, entry, or `access-group`, `access-class` or `ipv6 traffic-filter` binding; an object-group; `ntp access-group`), `security_acl` | C4 (an inbound ACL on r6 Gi2 permitting TCP and UDP only); H11 W7 (an ACL and its `ip access-group` on r6 Gi2, one unit, C2822) | **2** (was 4; C2839, the operator, 2026-11-09) | Always proposed, never a setting (`policy.SECURITY_KINDS`): **Remove it (back to intent)**, Mode B's measured removal of the ACL and its application together, approved by hash with a reason; or **Keep it: add it to intent**, the device's intent editor, nothing sent. A removal not measured on the platform is can't fix yet, naming the probe | read-back: each removed line gone; the symptom | `removal.restore_program` | A security control's removal is a security decision, a person's; removing an attacker's or an auditor's ACL automatically is the worst failure an auto-remediation can have, and keeping it is a decision too |
| **a security control removed or changed** (`security_control`: a line outside intent in a class the platform pack declares by line shape, `modules/nsot/platform_heal.json`: routing authentication and key chains, AAA, crypto and SSH, SNMP restrictions, control-plane policing, port security and 802.1X, `transport input`) | H11 W6 (OSPF authentication and its key added on one end of r3 Gi4, the adjacency down) | **2** (C2839; it was Tier 1 as an added line) | Always proposed, as above: Remove it (back to intent) or Keep it: add it to intent. **Adding back a missing control stays Tier 1** (a missing line; a routing key, Tier 2 as a secret added back) | read-back; the symptom | `removal.restore_program` | Mid-rollout, one end is configured before the other: stripping it in Auto undoes a person's security change with nobody in the loop |
| **a one-sided security change that broke an adjacency** (`security_revert`; only where the network answers yes to C2839's question, `heal_security_revert_adjacency`, **no by default**) | W6 on a network that says yes | **1** | As an added line: Mode B's measured removal, or merge for a changed value; AUTO only where `heal_kinds_auto` names `security_revert` (N8, one kind at a time) | read-back; the adjacency back | `removal.restore_program` | The network decided that a one-sided change breaking an adjacency is a fault to undo: the unit is a removal or change on an interface or a routing process, the incident holds an adjacency down, and no other device is in it (both ends changed is multi-device, Tier 4) |
| **credentials and AAA** (`username`, `enable secret`, `aaa`, `snmp-server community`, keys and key chains, `crypto`) | none in the set | **4** | Never. Can't fix: notify | not applicable | not applicable | CLAUDE.md: a deploy may add an account, never change one; rotation and break-glass have their own operations (`modules/nsot/credential_rotation.py`, `modules/breakglass.py`) |
| **Mercury's management path** (the management interface's stanza, vty, `ip ssh`, a route that may be the manager's, any program with a non-empty `reach_lost`) | C4 too (Gi2 carries r6's management address); R3 as the sheet draws it (section 15) | **4** | Never. Can't fix: "the fix would cut Mercury's path" | not applicable | not applicable | CLAUDE.md: a change to the path the tool reaches a device on needs a repair route independent of that path, and none is built (`removal._refusal`, `_management_routes`) |
| **multi-device**: the cause spans devices (both ends of a link departed in one incident window; a duplicate shared by two devices) | none in the set (R8's duplicate is one device's departure) | **4** | Never. Can't fix: notify | not applicable | not applicable | A multi-device change has an ordering and a partial state no single-device heal can verify |
| **unmeasured removal shape** (an added line with no `exact` measurement on the platform) | I1's lines; R3's until measured | as its kind, and **can't fix** until measured | Can't fix, naming `scripts/nmas-removal-probe` | not applicable | not applicable | "Allowed only where measured" (removal.py): being wrong here destroys configuration |

**Mixed incidents:** a device whose departure holds units of several kinds takes the strictest
tier among them. C4's ACL stanza and its binding are one unit (C2822) of `security_acl`, Tier 2,
so the incident is a proposal. A Tier 1 missing line beside a Tier 4 account is not healed
alone: a partial heal leaves a state nobody verified.

**The order of the checks** (`kinds.kind_of`), the first that applies: multi-device,
management path, credentials and AAA (Tier 4); an ACL (`security_acl`); a security control
removed or changed (`security_control`), or `security_revert` where the network says yes; QoS;
a process reset; a secret added back; admin down; otherwise missing, changed or added. Tier 4
stays where it was: the operator's rule moved Tier 1 removals to Tier 2 and named
`security_acl` from Tier 4 to Tier 2, nothing else (an account, `aaa`, `crypto` and a `key
chain` stanza stay credentials, Tier 4; docs/STANDING_APPROVAL_LOG.md, 2026-11-09, "C2839 3").
A platform with no security classes declared treats every removal or change on it as
`security_control` (fail closed).

**Dependents are one unit (N13, C2822, approved 2026-11-08 as proposed).** A definition of the
departure that only ONE other unit of the same departure references by name is one unit with
it, transitively: an ACL and its `ip access-group`, `access-class`, `ipv6 traffic-filter` or
`match` use; a route-map's match lists (prefix-list, access-list, community-list, AS-path list);
class-map, policy-map and `service-policy` (a chain of three); a key chain and its use; a
prefix-list and its `neighbor … prefix-list`; an object-group and its ACL; a track and its
static route or HSRP use; an IP SLA (its operation and its schedule line) and its track. The
objects and shapes are the platform pack's ``references``. A definition an unchanged line also
uses stays its own unit, and so does one two units use (docs/STANDING_APPROVAL_LOG.md,
"C2822 1"). Guard 12 counts the joined unit once, its section the use's.

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

**What each guard counts with a standing incident** (C2813, section 3):
- **6, many devices at once:** the devices whose own change opened an incident within one grace
  period, by the incident's opening. A standing incident counts once, when it opened; being
  judged again does not reopen it.
- **7, a person working:** the device's outside changes its incident holds in the window. A
  standing incident's changes are its device's, so they count (and they count for a far end's
  guard too, `actions.outside_changes_on`).
- **9, 10 and 11, the rates:** the decisions that heal (Auto's heals; dry run's would-heals,
  counted as Auto counts heals). A drift record of the same departure joins a standing incident
  and makes no decision, and a read of the same departure stands it again, so neither is
  counted twice; a new departure is a new decision and counts, as a new incident did. **They are
  not counted for an incident settled at its golden** (C2840): its read, after every outside
  change, found nothing to heal, and its only outcomes (nothing to heal, a Tier 3 can't-fix)
  send nothing, so a person's revert is never held by the rate the change's own would-heal
  used. Chosen over reading the device again before the rates: the settling read IS a fresh
  read (the same pass), and a second read would cost a device session per incident for no new
  fact.

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

**Auto on Nov 15: the gate** (the operator's decision 3, 2026-11-08, after H11's walks).
- **Default's first Auto kinds:** `missing_line` (Tier 1), and `added_line` for lines that are
  not a security control. Excluded: every security class of C2839 (routing authentication and
  key chains, ACL application, AAA, crypto and SSH, SNMP restrictions, control-plane policing,
  port security and 802.1X, `transport input`), `security_acl` and `process_reset`. Built
  2026-11-09 (C2839): those classes are `security_control` and `security_acl`, Tier 2 and
  always proposed, so no Auto list can include them; `added_line` no longer holds a security
  control; `security_revert` (only where a network answers yes, default no) is not among the
  first Auto kinds either.
- **The condition** (narrowed by the operator, 2026-11-09, to what is live): Auto turns on only
  if C2821, C2813, C2825 and C2824 are deployed (all are, since 7b4a9271 and 37d882b7), AND
  W1, W3 and W4 (H11's sheet) re-run clean in dry run that morning. Otherwise Auto waits for the
  Nov 23 review, and dry run continues. **C2818 moved to after Nov 30:** in the Lab 10 demo,
  faults are injected by the `lab` account, so the change's person is named unambiguously
  without Mercury's own account.
- **The supervised window, Nov 13 to 16** (the operator, 2026-11-09): Auto on for
  `missing_line` only, with `heal_mode_until` set to the window's end, so it returns to dry run
  by itself; three or four real heals and one can't-fix recorded for the video.
- **The checklist:** ~/Documents/nmas-reports/2026-11-15-auto-checklist.md, each item with its
  PASS line.

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
- **Tagged `nmas-managed`** (C2437, read before building: the lab NetBox 4.6.9 answers OPTIONS
  on `extras/journal-entries/` with a writable, optional `tags`, 2026-11-04), so
  `_with_managed_tag` applies (`netbox_guard.TAGGABLE_ENDPOINTS`) and an entry it cannot tag
  is never sent.
- **Its first line names the heal**, `Mercury heal <decision id>` (`journal.HEAL_LINE`), and
  the NetBox census reconciles the journal with the step log: every entry added between two
  snapshots matches a heal step on the same device with the same heal, and every heal step
  in the window that wrote the journal has its entry (`scripts/nmas-netbox-census`,
  docs/SERVICE_ACCOUNTS.md 1.6).

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
| `heal`/`proposal` | a fix that needs a person waits (Tier 2) | Approve… (confirm by hash; a reason optional unless a line needs one, the operator, 2026-11-09, C2817) or Decline… (a reason required) | resolves: approved and verified, or the device back at intent; acknowledged: declined with a reason |
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
- **No fix runs from AI text.** The AI may propose one operation from Mercury's catalog, with
  its parameters; code validates it against intent and the guards, and a person approves it
  before it runs. The AI never composes commands, never runs anything itself, and never retries
  on its own. (The operator's words, 2026-11-11, replacing "No fix is ever chosen or run from AI
  text".)
- **A saved fix is the operation a person saved from a verified run, never the AI's words.**
  (The operator, 2026-11-11.)
- **Mechanised:** a test (tests/test_heal_analysis_never_read.py) parses `modules/heal/` and
  refuses any reference from the loop's modules to `modules.ai` or to the incident's
  `analysis` field. Only the notifier and the pages draw it. The fix rule is held by
  tests/test_ai_fix_rule.py: an AI answer becomes a proposal only through one door
  (`modules/ai/fix_proposal.py`), which takes exactly one operation of the catalog
  (`modules/heal/catalog.py`) with the parameters its schema names, returns that operation's
  own preview and hash, and refuses and records any other shape; each catalog operation's
  run refuses without the previewed hash and a verified person; no module of `modules/ai/`
  references a function that sends, holds a device or starts an operation; and no run is
  called from a loop or a failure's handler.

**AI troubleshooting on the incident's page, its parts with no AI call (2026-11-12, the
operator's overnight item 6).** `modules/fixit/` holds the incident's own record of proposals
and choices, its attempts derived from the operations' run records, the mode (Manual by
default, or off; no automatic mode) and the per-incident cap ($1.00), the check every proposal
passes whoever made it (the catalog's schema, the incident's scope, the guards, committed intent
through the operation's own preview; a repeat of a failed fix flagged), Mercury's own proposer
from the lost-stream diagnosis, what a model would be sent (every person a stable label), and
the hand-over. This section's rule holds over all of it: nothing in `modules/heal/` imports
`modules/fixit/` (tests/test_heal_analysis_never_read.py), and nothing there calls a model,
holds a device or starts a job. The page's section, its controls and the AI call are not built
yet (docs/manual/screens/incident.md, "AI troubleshooting").

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
- **Never a staged run or probe on s3, nor inside 02:30 to 03:30 America/Denver (the nightly backup window, C2613)** (the standing facts):
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
  - `scripts/nmas-coverage report --html <file> --only modules/heal/` over a run with
    contexts (`--cov-context=test`): per function, which unit tests reached it; over a run
    measured by tier, as a push's is, per function whether a unit test reached it
    (docs/manual/concepts/testing.md has the commands);
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
02:30 to 03:30 America/Denver (the nightly backup window, C2613).

| # | Scenario (sheet) | Device | What the heal detects | Tier | What it does | What verify reads | What the person sees |
|---|---|---|---|---|---|---|---|
| 1 | **M4**: the syslog destination removed | r2 | No CONFIG_I arrives: its own line is logged after the destination is gone. The heartbeat-missing alert (about T0 + 8 to 13 min, Alerting NoData) triggers it, which needs N2. Without N2, the scheduled check finds it | 1, missing line | merge re-adds the exact `logging host` line from intent | read-back; r2's next heartbeat within 300 s; the alert resolves | History: healed; the email "healed, verified"; r2's Logs carry its lines again |
| 2 | **M6**: the EEM heartbeat applet removed | r3 | CONFIG_I at T0, not Mercury's; after the grace period r3 lacks the applet stanza | 1, missing line | merge re-adds the stanza and its two children | read-back; the next heartbeat; the episode resolves | healed before the heartbeat alert fires (T0 + 2 min with the lab's 120 s grace) |
| 3 | **C3**: a static route with a wrong next hop | r4 | CONFIG_I at T0; one added `ip route` (shape `global.ip-route`, measured exact); not the manager's path (`_management_routes`) | 1, added line | Mode B: `no` plus the device's own line | read-back (the line gone); IP SLA 1 on r4 passing again; r1's probe too (folded) | healed; the probe alert may fire and resolve; the change record downloadable |
| 4 | **C1**: an OSPF `network` statement removed | r8 | CONFIG_I on r8; s5's "Device unreachable" folds in (s5 is in r8's blast radius) | 1, missing line | merge re-adds the statement under `router ospf` | read-back; s5 reachable (the attached device); r8's adjacency to r2 unchanged | one incident, r8, with s5 under it; never a separate s5 can't-fix |
| 5 | **R3**: OSPF authentication added on one end. **Changed (N7):** run on the r3–r4 link's Gi4, which carries no management (I5's sheet says so), not r6 Gi2, which carries r6's management address (C4's sheet) | r3 or r4 | CONFIG_I; two added lines on one interface (`ip ospf authentication message-digest`, `ip ospf message-digest-key … md5 <masked>`), each a shape measured first by `scripts/nmas-removal-probe` on r2 (IOS-XE) | 2, `security_control` (C2839, the operator 2026-11-09: a security control added outside intent is a person's decision; the demo shows R3 as a proposal the operator approves, "Remove it (back to intent)"; it was 1, added line) | Mode B: both lines' `no` forms, the key's masked in every record, sent once the operator approves by the proposal's hash | read-back; the adjacency FULL on both ends | proposed, then healed on approval; the key never drawn |
| 6 | **R8**: r6 given r4's router-id, the process reset | r6 | CONFIG_I; `router-id` changed (a changed line), effective only through a process reset | **2, propose** | the proposal: merge sets intent's router-id, then the measured OSPF reset, one hash | on approval: adjacencies re-form; no DUP_RTRID logged | Needs attention: "A fix waits for a person: r6's OSPF router-id"; the email "proposal waiting"; Approve… by hash, then healed |
| 7 | **C4**: an inbound ACL permitting TCP and UDP only, on r6 Gi2. **The "won't fix, notifies" demo** | r6 | CONFIG_I; an extended ACL stanza and its `ip access-group … in` on Gi2; r7's unreachable folds in | **4** (a security ACL, and Gi2 is Mercury's path to r6) | nothing sent | not applicable | Needs attention: "Self-healing will not fix r6: a security ACL was added outside intent, on the interface Mercury reaches r6 by". Opened: What to do; Mercury's facts (the 7 steps); then the AI analysis, advisory. The email in the same order |
| 8 | **I5**: a link flapping, made from r4's side by its Tcl loop. **The can't-fix (physical)** | r3, r4 | r3's "Interface down" (port down, admin up) checks r3, at intent: physical. r4's repeated CONFIG_I from the loop hold r4 ("a person appears to be working", guard 7) | **3** | nothing sent | not applicable | one incident on the link: r3 physical, r4 held; the email "can't fix: Gi4 down while administratively up, configuration at intent"; the AI analysis, advisory |
| 9 | **V1**, new: **a failed verify, rolled back** (the third recorded case for the analysis) | an IOS-XE router chosen from the lab's committed intent | an OSPF `network` statement added outside intent for a link whose far end already runs OSPF, so an adjacency forms that intent does not describe (shape `ospf.network`, measured first) | 1, added line | Mode B removes it | verify sees the adjacency drop (tolerance 0, settle window) and rolls back; the policy halts | **An unpredicted side effect, so Mercury undid its own fix: the safety behaviour.** Needs attention: "Self-healing rolled back on <device>: removing the added line dropped an OSPF adjacency it did not predict"; the halt's row; the analysis. **Checked in review (2026-11-03):** `expected_effects.for_device` predicts an OSPF drop only for an interface the program takes down (`adjacencies_drop`, from intent's adjacencies via the interfaces in `down`). Removing a `network` statement takes no interface down, and the adjacency it formed is not in intent, so nothing predicts the drop, and verify rolls back. Its sheet is written after reading the lab's intent for a link that fits; if none does, it is said, not staged |

**Row 8 (I5) is revised in the amendment, for review:** bounced once, still flapping, dampening
proposed (section 19.6), a draft sheet until the operator's lab-host trial is measured; row 8
stands as written until then. Row 7 (C4) gains an on-demand diagnosis there too.

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
- **With the amendment (section 19, for review):** H14 to H31 add 21.5 days, so board H is
  37.75 days: about 49 hours (26 to 98) and about 151M weighted tokens (94M to 340M), roughly
  12% of a week's usage (7 to 26%). Lab 10's part, all but H29 to H31 (Lab 9's B4), is 34.25
  days. Section 19.7 holds the parts, their streams and what each
  depends on.

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
| H14 | *Amendment, for review (19.3):* the diagnosis engine, the "adjacency down with both ends at intent" runbook, the ranking table, one diagnosis per device and 70 commands per diagnosis | 2.0 |
| H15 | *Amendment (19.3):* the "A can't reach B" runbook, on the path trace, its IPv6 form | 1.5 |
| H16 | *Amendment (19.3):* Diagnose… on a device and on an alert, the result card, the manual pages | 1.0 |
| H17 | *Amendment (19.3):* the diagnosis run automatically on an Alert incident before it notifies and on a Propose incident before it is offered; its pack section for H8 | 0.75 |
| H18 | *Amendment (19.3):* the runbooks' captured fixtures and scenario replays | 0.5 |
| H19 | *Amendment (19.4):* the four action kinds, their guards, flap detection | 1.0 |
| H20 | *Amendment (19.4):* the port bounce, and the OSPF adjacency reset through it (one neighbour only), refused on Mercury's management path and on a device's only path, run inside the device's revert timer and confirmed only after Mercury is back in; shipped only once the operator's trial is measured | 1.75 |
| H21 | *Amendment (19.4):* the BGP clears (a hard clear of one named neighbour, a soft clear), measured privileged operations; Auto on a lab network, Propose elsewhere | 1.0 |
| H22 | *Amendment (19.4):* the dampening proposal: intent's dampening field, its measured shapes, one hash for the intent commit and its deploy; intent's configuration archive field (`archive.path`) | 2.0 |
| H23 | *Amendment (19.4):* the actions' records, rows, manual and replays; I5's sheet written from the operator's trial | 1.0 |
| H24 | *Amendment (19.5):* the AI read set, the allow-list the tool enforces, matching the whole command | 1.0 |
| H25 | *Amendment (19.5):* the read loop: pass 1's requests, the check, the reads, pass 2 | 1.25 |
| H26 | *Amendment (19.5):* the loop in History, every send logged, and its egress hand check | 0.75 |
| H27 | *Amendment (19.5):* the loop's measurement, 3 cases × 10 runs at two passes (about $2) | 0.5 |
| H28 | *Amendment (19.5):* item 3's prerequisites: the read-only device account (moved from after Lab 10) and the device state egress class | 2.0 |
| H29 | *Amendment (19.12):* the SDN read set, GET only, every write endpoint refused in code, its tests and canary (Lab 9's B4) | 1.75 |
| H30 | *Amendment (19.12):* the SDN reads in History, and their replay from captured packs (Lab 9's B4) | 0.75 |
| H31 | *Amendment (19.13):* B4's evaluation against its frozen plan (Lab 9's B4) | 1.0 |
| | **Total with the amendment** | **37.75** (Lab 10's part 34.25) |

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

**The amendment revises this cut order (section 19.8, for review):** the diagnosis runbooks
and the AI read loop (Lab 10's item 3 and Lab 9's B4) are never cut. Verification codes
and the installation's kill switch are built (commit 24aef7b6, H1 and H7), so they leave the
list.

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
- no deploy during a sitting; nothing in 02:30 to 03:30 America/Denver (the nightly backup window, C2613).

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

  Each cut keeps the lab's requirements. **Revised by the amendment, for review: section
  19.8.**
- **The amendment's load, said early:** section 19 adds 21.5 agent-days (about 28 hours, 15
  to 56), 18.0 of them Lab 10's. The streams hold about 15.0 and 16.25 days of Lab 10's work,
  then stream B's 3.5 days of Lab 9's B4 (19.7).
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
| N9 | **A line in a secret position** (R3's key) | **Removing a routing-protocol key returns to intent: Tier 1,** the line masked everywhere, the policy's words its stated reason. **Adding any secret back: Tier 2. Accounts, AAA and SNMP communities: Tier 4.** *Superseded in part 2026-11-09 (C2839, the operator): removing a routing-protocol key, or any line outside intent in a security class, is Tier 2, a person's decision; adding back a missing ACL application is Tier 2; the rest of N9 stands.* |
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

---

## 19. Amendment, 2026-11-03: the troubleshooting lecture's additions (for the operator's review)

**The operator's direction, 2026-11-03, from the course's troubleshooting lecture.** Five items:
1. diagnosis runbooks as code, read-only and deterministic, run automatically on a Tier 3
   incident before it notifies and on demand;
2. action remediations, the lecture's "good candidates": one bounce of a port, dampening
   proposed if it still flaps, and one clear of a stuck routing session;
3. a bounded, read-only loop for the can't-fix AI analysis;
4. rows to register for after Lab 10 (given in the agent's report, not written here);
5. for the video and the write-up, board H's tiers mapped to the lecture's, and Mercury placed
   on the L0 to L5 maturity ladder.

**Approved by the operator, 2026-11-04** (commit `c94d8b08`'s `Approved-By`: "Approved: board H
amendment section 19 with N14 to N24 as revised …", and "Section 19 approved as revised, with one
addition to N17 before you commit"); the notes below are the draft as it was put for review.
**As drafted:** not approved, not built. This was a draft for the operator's review, not
self-signed under the Phase 7 mode, like the board it amends. Drafted 2026-11-03 ~23:4x UTC (17:4x, UTC−6) over
HEAD ad202730. The board's new regions (artboards I to M, and inserts in A and G) are each marked
"amendment, for review" in `docs/boards/heal-to-intent.html`. Sections 1 to 18 stand as
approved, except where this section says it revises them (16's parts and 17's cut order).

**Register rows searched first:**
- **C762** (a Toolbox page, absorbing C1310's packet capture), open, C, after Phase 7;
- **C1004** (flow export, NetFlow), open, C, Phase 8: after;
- **C230** (Grafana's token is an Editor's), open, the least-privilege precedent;
- **C589** (an adjacency that drops and recovers inside two reads raises nothing), open;
- **C1810** (a console change seen only at the next drift run), open;
- C2128 and C2387 (the notifier and its deferred formats).

None covers a diagnosis runbook, an action remediation or an AI read loop. The new rows this
section needs are listed in 19.11, for recording once the operator has reviewed it.

**The operator's review, 2026-11-03 (after the first draft), from the lecture's slides.** Its
corrections are applied throughout this section: the lecture's three tiers and its own L0 to L5
ladder (19.9), N15, N16, N17 and N20 as the operator set them (19.10), and the read-only device
account moved from after Lab 10 into item 3's prerequisites (19.5, H28).

**Three numberings, kept apart.** "Tier" means three things here, and each is named when used:
- **board H's tier,** numbered 1 to 4 in code and in this document (sections 5 and 6) and **shown
  by name on every screen:** Tier 1 is **Auto**, Tier 2 **Propose**, Tier 3 **Alert**, Tier 4
  **Never**. The code's numbers are not changed (the operator's decision);
- **the command policy's tier** (`modules/readonly_commands.py`: 1 non-destructive, 2
  recoverable, 3 destructive), written "command-policy Tier N";
- **the lecture's tier:** three tiers numbered by rising autonomy, written "lecture T1" to "T3"
  (the crosswalk, 19.9).

### 19.1 The industry need

**The problem.** Most of an outage's time goes on isolation, not repair. An engineer paged for
"r3 Gi4 down" runs the same dozen reads every time: both ends' interface state and errors, the
neighbour's view, MTU, timers, area, authentication, the path hop by hop. They do this before
they know whether the fault is a cable, a far end, a typo or an ACL. A transient fault (a port
that will come back if bounced, a routing session that will form if cleared) waits for that
engineer, though the fix is mechanical.

**How established practice and commercial tools address it:**
- **Troubleshooting methods.** Cisco's documented methods include follow-the-path, bottom-up and
  compare-configurations (its CCNP troubleshooting curriculum). Google's SRE book, "Effective
  Troubleshooting" (chapter 12), describes the hypothetico-deductive loop: triage, examine,
  diagnose, test, treat. A ranked hypothesis list with its evidence is that loop's diagnose step,
  written down.
- **Executable runbooks.** Network automation platforms run a stored diagnosis against the live
  network and show its findings in place (NetBrain's executable runbooks). Incident platforms
  run automated diagnostics when an incident opens, before or as the on-call is paged, and
  attach the output to the incident (PagerDuty's process automation, Rundeck). Path analysis
  products answer "can A reach B" from forwarding state and point at the hop that drops it
  (Forward Networks, IP Fabric).
- **Bounded automatic actions.** Devices recover an err-disabled port themselves after an
  interval (`errdisable recovery` on Cisco IOS). IP event dampening suppresses a flapping
  interface (the interface `dampening` command), as BGP route flap damping does for routes (RFC
  2439). Container platforms restart a failed process and back off before escalating (the
  restart back-off of an orchestrator's liveness probe). Each acts once, verifies, and then
  stops and asks.
- **Bounded tool loops for a model.** The model asks for a tool, and the application decides
  whether and how to run it and returns the result: the ReAct pattern (Yao et al., 2022) and
  Anthropic's tool use. OWASP's Top 10 for LLM Applications (2025) names the risks: LLM06
  Excessive Agency (limit what a model can call, its permissions and its autonomy), LLM01
  Prompt Injection, and LLM02 Sensitive Information Disclosure.

**How Mercury meets or improves on it:**
- **Diagnosis compares each hop with committed intent, not with "what usually works".** A
  divergence is a fact about this network's own intent, with the read that shows it.
- **Every read goes through the one reads engine:** allowlisted whole, the device held, masked,
  capped, recorded on History › Reads. No new device path is opened.
- **The ranking is a rule table in code.** The same reads give the same ranking, which a test
  can hold and a person can audit.
- **An action runs only when the diagnosis's top hypothesis is that action's own precondition.**
  It runs once and is verified. When it does not take, it escalates to a person's proposal
  (dampening) and never a second try.
- **The AI asks; code decides.** The model may ask for up to 3 reads. Each is checked against a
  narrower AI read set than a person's allowlist, run by the reads engine as a read-only device
  account, masked, sent only under a device state class a network turns on, recorded, and
  charged to the feature's caps. Nothing in the heal loop reads the answer (section 12).

### 19.2 What changes, item by item

| Item | Where it lands in this design | Parts | Board |
|---|---|---|---|
| 1, diagnosis runbooks | 19.3: a new step between decide's Tier 3 outcome and notify (section 4); Diagnose… on a device and an alert | H14 to H18 | artboards I and J; A's Tier 3 row |
| 2, action remediations | 19.4: four new fix kinds in section 5's table (port bounce, session clear, OSPF adjacency reset, dampening proposal), their guards beside section 6's | H19 to H23 | artboards K and L; A's kinds and guards |
| 3, the AI read loop | 19.5: section 12's analysis gains one bounded read round and a second pass; its prerequisites are the read-only device account and the device state egress class; extended to the SDN Analyst and Responder (19.12) and evaluated as Lab 9's B4 (19.13) | H24 to H31 | artboards M, N and O; G's estimate |
| 4, rows after Lab 10 | the agent's report (the register is not edited here); the read-only account left this item for item 3 | none | none |
| 5, the tier crosswalk and the ladder | 19.9 | none (documents) | every artboard: tiers by name |

### 19.3 Item 1: diagnosis runbooks, read-only and deterministic

**What a runbook is.** It is a fixed list of steps in code (`modules/heal/diagnose.py`, new).
Each step is a read, or a comparison of what was read with committed intent. A runbook sends no
command that is not a read, changes nothing, and calls no model. Its output is a **diagnosis**:
the steps with their results, a ranked list of hypotheses with their evidence, and the checks
that passed ("ruled out").

**Its two entry points:**
- **Automatic, on a Tier 3 incident, before it notifies** (the operator's direction): decide's
  outcome is can't fix at Tier 3 (physical or link down while admin up; unknown cause). The
  incident runs the runbook that fits its trigger. An interface or adjacency trigger runs
  "adjacency down with both ends at intent". "Device unreachable", or a reachability probe,
  runs "A can't reach B", where A is the device the failing probe runs from, or the device
  Mercury reaches B through, and B is the unreachable device's address. Then item 2's actions
  are considered (19.4), and then the notice is sent, carrying the diagnosis.
- **Automatic, on a Propose (Tier 2) incident, before it is offered for approval** (the operator,
  N14): the runbook that fits the incident's trigger runs first, and its diagnosis is attached
  to the proposal. The Needs attention row, its email and its Approve… show it, so the person
  approving sees what Mercury read. A proposal whose diagnosis finds a decisive cause the
  proposed fix does not address says so on the row: "the diagnosis's first hypothesis is
  <claim>, which this fix does not change". It is never withdrawn by the diagnosis alone.
- **On demand, Diagnose…, everywhere:** on the device page's Actions menu, beside Check drift
  now…; on an alert, beside Explain on its evidence card (Monitoring); and on every Needs
  attention row the heal raises, of any tier, Never included. A person picks the runbook and its target from what intent and
  NetBox hold (a device, an intended neighbour, an address of the network), never free text. An
  address is checked as one IPv4 or IPv6 address. The dialog lists every read it will make, and
  on which devices, with the worst-case time. The press is busy on itself, and the diagnosis
  draws in place (artboards I and J).

**Its guards:**
- **Reads only.** Every command passes `readonly_commands.refusal` with no extras (a new
  reads-engine caller kind, `diagnosis`, whose `reads.EXTRAS` entry is empty). No `send log`,
  no `verify`, no `terminal` setting.
- **One diagnosis per incident.**
- **At most one diagnosis at a time per device** (the operator, N24). A diagnosis lock per
  device across processes, refused by name and never queued, is held beside the reads engine's
  per-read hold. A second diagnosis touching that device says "not diagnosed: r4 is in
  diagnosis <id>", with Diagnose… offered once it ends. A device held by another operation is
  skipped by name: its step says "not read: r4 is held by <operation>", and any hypothesis
  that needed it is marked **evidence incomplete**, never guessed.
- **At most 3 automatic diagnoses at once per network** (N24). The rest say "not diagnosed: 3
  diagnoses already running on Default", with Diagnose… offered on their rows.
- **At most 70 device commands per diagnosis** (`diagnose.MAX_COMMANDS`, N24), about 2.5 times
  the longest runbook's own count. The counts, from 19.3's table:
  - **"adjacency down"** on a dual-stack OSPF and BGP link is 14 commands per end:
    - `show interfaces` twice;
    - `show ip interface`, `show ip ospf interface`, `show ip ospf neighbor detail`;
    - `show ipv6 ospf interface`, `show ospfv3 neighbor detail`;
    - CDP, LLDP;
    - the link ping and the df-bit ping;
    - `show ip bgp summary`, `show ip bgp neighbors`, the update-source ping.

    So it is **28 commands for both ends: the longest of the two runbooks' fixed counts,**
    and 2.5 × 28 = 70.
  - **"A can't reach B"** is 3 commands (ping, traceroute and the return route), plus about 7 a
    routed hop (`show ip cef`, `show ip route`, `show interfaces` twice, ARP or ND, `show ip
    interface`, an ACL's counters). It usually stops at the first divergence, and at 70 it
    covers 9 hops. A longer path stops at the cap and says so: "stopped at the 70-command cap
    after hop 9; hops after it not read". It never stops silently.
- **Bounded:**
  - at most 14 reads per device per run (the adjacency runbook's own count);
  - both ends read concurrently (`fanout.read_each`);
  - each ping or traceroute inside `readonly_commands.BOUND_SECONDS`;
  - the whole run's bound is about 2.5 times its measured time, measured in H18 (an estimate
    before then: 30 to 60 s).
- **Never `clear counters`.** It erases the evidence a diagnosis reads, and it is
  command-policy Tier 2. Error counters are read twice, 10 s apart (to be measured), and the
  difference is the evidence.

**What a Diagnose… run reads.** Every command below was put through
`readonly_commands.refusal` over HEAD ad202730 on 2026-11-03, and **every one passed**. Each
bound is `readonly_commands.bound_seconds`. "Captured" names a real capture in the suite today
(`tests/fixtures/operational/`, `tests/fixtures/endpoints/`, `tests/fixtures/path/`). One not
captured is captured in H18 before its parser is written, because fixtures are real captures.

| Runbook | Step | Command (IPv4) | IPv6 form | Bound | Captured today |
|---|---|---|---|---|---|
| both | interface state, MTU, errors (twice) | `show interfaces <if>` | the same | read timeout | Loopback0 only (r2, s1); a physical port not yet |
| both | address, subnet, ACL bindings | `show ip interface <if>` | `show ipv6 interface <if>` | read timeout | the whole table (r1, r3, s1, s3) |
| both | who is cabled there | `show cdp neighbors <if> detail`; `show lldp neighbors <if> detail` | the same | read timeout | yes (detail, whole table) |
| adjacency | OSPF on the interface: area, network type, hello and dead, authentication, passive | `show ip ospf interface <if>` | `show ipv6 ospf interface <if>` | read timeout | H18 (2026-11-07, `tests/fixtures/diagnose/`): r2 both; s1 "OSPF not enabled", its IPv6 form refused; not yet parsed |
| adjacency | the neighbour's view, each end | `show ip ospf neighbor <if> detail` | `show ospfv3 neighbor detail` | read timeout | yes (r1, r3, s1, s3; OSPFv3 without detail) |
| adjacency | MTU across the link, don't fragment | `ping <far address> size <intent's MTU> df-bit repeat 2 timeout 2` | none (IPv6 never fragments in transit: the interface MTUs are compared instead) | 34 s | H18: r2; not yet compared by the adjacency rules |
| adjacency | the far end reachable on the link | `ping <far address> source <if> repeat 5 timeout 2` | `ping ipv6 <far address> source <if> repeat 5 timeout 2` | 40 s | H18: r2 (IPv4); not yet compared by the adjacency rules |
| adjacency | BGP: the session's state | `show ip bgp summary`; `show bgp all summary` | `show bgp ipv6 unicast summary` | read timeout | yes (r3, r4, s1, s3) |
| adjacency | BGP: last reset reason, hold time, update source | `show ip bgp neighbors <peer>` | `show bgp ipv6 unicast neighbors <peer>` | read timeout | **no** |
| can't reach | does A reach B | `ping <B> [source <if>] repeat 5 timeout 2` | `ping ipv6 <B> ...` | 40 s | H18: r2, s1, both families (answered, timed out, `X`, `H`) |
| can't reach | the forwarding path, hop by hop (the path trace's own read) | `show ip cef <B>` | `show ipv6 cef <B>` | read timeout | IPv4 yes (`path/cef_fleet.json`); IPv6 H18: r2, r4, s1 (link-local next hops, Null0) |
| can't reach | past the managed devices | `traceroute <B> numeric timeout 2 probe 1 ttl 1 16` | `traceroute ipv6 <B> numeric timeout 2 probe 1 ttl 1 16` | 62 s | H18: r2 both; s1 (vIOS-L2) refuses every option after the address, both families (C2681) |
| can't reach | each hop's route and its source | `show ip route <B>` (`show ip route 0.0.0.0` where CEF forwards by the default: IPv4's lookup by address never matches it, measured on both) | `show ipv6 route <B>` (matches the default) | read timeout | H18: r2, r4, s1, both families |
| can't reach | the next hop resolved | `show ip arp <next hop>` | `show ipv6 neighbors <address>` (the AI's shape; `<if>` measured too) | read timeout | yes (r1, s1); H18: by address on r2 and r4, refused by s1 (vIOS-L2, C2681); by interface on r2, s1 |
| can't reach | a switch between two routed hops: where the next hop's MAC is learned, and its port's spanning-tree state | `show mac address-table address <mac>`; `show spanning-tree interface <port>` | the same | read timeout | H18: s1, read where a hop's own egress is an SVI; a separate switch between two hops is not yet read |
| can't reach | an ACL's match counters, when one is bound | `show ip access-lists <name>` | `show ipv6 access-list <name>` | read timeout | H18: entries (r2, r4, s1, IPv6 on s1); no capture printed a match count |
| both | the device's logs: ADJCHG and its reason, ERRRCV, BGP notifications, UPDOWN, CONFIG_I | Loki, through `device_logs`, not a device read | the same | the Loki reader's bound | yes (`tests/fixtures/loki/`) |

**What the allowlist lacks, and what is missing besides** (each a row in 19.11):
- **No read the runbooks need is refused.** The allowlist is shaped by verb, so every `show`
  passes, and ping and traceroute pass inside their bounds.
- **Captures and parsers are missing** for the reads marked **no** above. H18 captures them on
  r2 (IOS-XE) and s1 (IOS), never on s3, never inside 02:30 to 03:30 America/Denver (the nightly backup window, C2613).
- **The path trace reads IPv4 only:** `path_trace.refusal` says "the trace reads IPv4
  forwarding only". The IPv6 form of "A can't reach B" needs `show ipv6 cef` parsed and
  followed. That is H15's, under the IPv6 rule (a capability that cannot serve IPv6 says so by
  name), and part of C1245's epic until built.
- **The allowlist is too wide for a model.** `show running-config` passes, so item 3 has its own
  narrower set (19.5).
- **The actions are not reads, correctly.** `clear ip bgp <peer>` is refused as command-policy
  Tier 3 ("a hard reset"). `clear ip bgp <peer> soft` is command-policy Tier 2, and
  `privileged.NOT_MEASURED` holds it. `clear ip ospf process` is command-policy Tier 3. Item 2
  adds measured operations for what it needs (19.4, N16).

**"Diverges from intent," at each hop.** The comparison is against the network model compiled
from committed intent (`modules/network_model.py`): links and their subnets, expected
adjacencies, each interface's intended admin state and address, OSPF's area, network type,
timers and authentication where intent holds them, the MTU where intent holds it, and the ACL
bindings intent holds. Where intent is silent, the platform's measured default is the expected
value (`modules/nsot/interface_defaults.json`, `platform_defaults.json`), and the step says so.
- **"A can't reach B":**
  - A pings B. If it succeeds, the result is "A reaches B now", and the runbook stops.
  - The path is followed with `path_trace.trace`'s hop-by-hop `show ip cef`, then the hops past
    the managed devices with a traceroute.
  - At each routed hop, in order, the runbook reads:
    - the egress interface's state and errors (two reads);
    - the next hop's resolution (ARP or ND);
    - on each switch between two routed hops, where the next hop's MAC is learned and that
      port's spanning-tree state, against the cabling intent and the observed links name;
    - the route's source against intent: a connected subnet, an expected adjacency's protocol,
      or a static route intent holds; anything else is "a route intent does not explain", C3's
      shape;
    - the ACL bindings on the egress interface and on the next hop's ingress, against
      intent's.
  - **It stops at the first hop that diverges, and reports it,** with "hops after r6 not read"
    said, never implied.
  - If the forward path holds at every hop, it reads the return path from B's device, when B
    is managed. A missing return route is the divergence.
- **"Adjacency down with both ends at intent":**
  - Both ends are read concurrently, and each parameter is compared three ways: end against
    end, each end against intent, and each end against the platform's default.
  - **Both ends at intent, yet the ends disagree, is its own finding:** intent disagrees with
    itself, or a platform default differs between the two platforms. The finding says which.

**How the hypotheses are ranked** (a rule table in code, `diagnose.RULES`, each rule with a
planted case in its test):
1. **By the strength of the evidence:**
   - **decisive:** a read that alone explains the symptom, such as a parameter that must match
     and differs;
   - **strong:** a state that usually explains it;
   - **circumstantial:** a log line or a timing.
2. **Within a strength, bottom-up by layer:** physical, then link, then network, then the
   routing protocol, then policy. This is the bottom-up method: a lower layer's fault explains
   the layers above it.
3. **Then by the number of independent reads that agree,** both ends counting as two.
4. **A hypothesis whose evidence is incomplete** (a read skipped or failed) ranks below every
   complete hypothesis of its strength, and says which read is missing.
5. **At most 5 are shown.** The checks that passed are listed as "ruled out", each with its
   read.
6. **No rule fires:** "no cause found in what Mercury reads", followed by the ruled-out list.
   It never guesses.

| Rule (examples; the table is complete in H14) | Layer | Strength | Evidence it cites |
|---|---|---|---|
| interface down while administratively up, far end up | physical | decisive | both ends' `show interfaces`; the far end's CDP or LLDP |
| CDP or LLDP names a neighbour intent does not cable there | physical | decisive | `show cdp neighbors <if> detail` against intent's link |
| input errors or CRC rising across the two reads | physical | strong | the two `show interfaces` reads and their difference |
| MTU differs between the ends, and the neighbour is stuck in EXSTART or EXCHANGE | link | decisive | both `show interfaces`; `show ip ospf neighbor detail`; the df-bit ping |
| addresses on different subnets | network | decisive | both `show ip interface` |
| OSPF area, hello or dead, network type or authentication differs | protocol | decisive (network type: strong) | both `show ip ospf interface` |
| passive on one end | protocol | decisive | `show ip ospf interface` ("No Hellos") |
| one-way: one end lists the other in INIT, the other lists nothing | protocol | strong | both ends' neighbour view |
| a BGP session not Established, its peer unreachable from the update source | network | decisive | the ping from the update source; `show ip bgp neighbors <peer>` |
| a BGP peer in Idle (Admin), administratively shut, or with a configuration mismatch (a wrong remote AS in its last reset reason) | protocol | decisive (no clear follows: drift or Alert) | `show ip bgp neighbors <peer>`; intent's remote AS |
| a BGP session not Established, its peer reachable, no configuration cause | protocol | strong (item 2's precondition) | as above, and the last reset reason |
| an ACL bound that intent does not hold, on the path or the link | policy | decisive (and Tier 4 for the heal) | `show ip interface <if>`; the ACL's counters |
| no route to B at a hop | network | decisive | `show ip route <B>`, `show ip cef <B>` |
| next hop unresolved (ARP or ND incomplete) | link | strong | `show ip arp <next hop>` |
| the next hop's MAC learned on a port intent does not cable toward it, or that port blocking | link | strong | `show mac address-table address <mac>`; `show spanning-tree interface <port>` |
| a configuration change outside Mercury on either end in the window | policy | circumstantial | the CONFIG_I lines (Loki) |

**Each hypothesis carries:**
- its claim, in Mercury's words;
- its layer and strength;
- its evidence: each read referenced by its reads run (`read:<run>:<device>:<command>`), the
  masked line that fired the rule, and the intent value it was compared with;
- the read that would rule it out;
- what to do. That is never an action Mercury runs from this list, except item 2's two
  actions, and only on their own preconditions.

**The industry practice it follows:**
- a deterministic rule table for fault isolation, the way event-correlation and assurance
  products rank a probable cause with its evidence;
- the bottom-up and follow-the-path methods for the order;
- the hypothetico-deductive loop for the shape: hypotheses, each with the test that would
  refute it.

**Where the step log records it** (H6's store, section 8):
- **Each runbook step is a step:** what was checked, each read named by device and command with
  its reads run (History › Reads holds the masked answer; the step log never holds raw text),
  the intent value compared, and the result.
- **The diagnosis itself** (the ranked list and the ruled-out list) is one record in the same
  store.
- **Automatic:** it is attached to the incident, and the incident's step log shows it as
  "Diagnosis: 4 hypotheses, the first decisive" with the list expanded.
- **On demand:** it is its own record. History gains the kind **diagnosis**
  (`modules/history_sources.py`), drawn on the device's History tab too (the one-timeline
  rule).
- **"Diagnosed" is not a fix.** A diagnosis that finds a cause clears nothing.

**What the notice and the AI analysis receive:**
- **The notice,** under Mercury's facts: "Mercury's diagnosis" with each hypothesis in words,
  its strength, and the hop or end it names. Values are by kind only, as section 10's messages
  are ("MTU differs: r4 Gi4 against r3 Gi4", never a configuration line). The screens name
  the tier ("Alert, diagnosed"), never its number.
- **The wait:** the notice waits for the diagnosis up to the runbook's bound. If the bound
  fires, the notice says "diagnosis not finished within <bound>; its result follows on this
  thread", using the AI analysis's follow-up mechanism (section 12).
- **The AI analysis (H8)** receives the diagnosis as a pack section, `diagnosis`, each
  hypothesis a piece `diag:<n>`. What it may carry off the host is decision N23.
- **The heal loop may read the diagnosis:** it is deterministic code, not AI text. Section 12's
  test still refuses any reference from the loop to `modules.ai` or to the `analysis` field.

### 19.4 Item 2: action remediations

**Not heal to intent, and said so.** Section 2 heals a configuration back to intent. These
actions change no configuration line (a bounce, a clear), or they propose a change to intent
(dampening). So they are **actions**, under the same tiers, guards, lifecycle and records, and
each is named as an action wherever it is drawn.

**The new fix kinds** (section 5's table gains these rows):

| Fix kind | Example scenario | Board H tier | What is done | Verify reads | Rollback | Why that tier |
|---|---|---|---|---|---|---|
| **port bounce** (`port_bounce`): a port down while admin up, its far end admin up and up, configuration at intent on both ends | I5 revised (19.6) | **1**, once per port per hour | one program, `interface <if>` / `shutdown` / `no shutdown`, in one batch through the deploy pipeline as the policy | the port up within its settle bound (measured), then **stable** for the stability window (no UPDOWN transition); the adjacency formed; the running configuration **did not move** against the pre-read | if the read after shows `shutdown` (the second line never landed), `no shutdown` alone, and the record says so | Reversible in seconds, configuration unchanged, verifiable; the lecture's first candidate. Never twice: a second need is a proposal |
| **session clear** (`session_clear`), BGP: one neighbour intent holds, **not Established in two reads in a row** (the adjacencies reader's `PERSIST_READS`, 2), its peer answering from the update source, no configuration cause found | none in the set (its proof is a replay test) | **Auto on a network marked lab; Propose by default** (the operator, N16); once per neighbour per incident | a **hard clear of that one named neighbour**, `clear ip bgp <peer>`, measured, through `privileged.py`'s lifecycle as the policy (or as the approving person, when proposed) | the session Established within about 2.5 times its measured time | does not apply: a session that was not Established had nothing to lose; the preview and record say so (`privileged`'s rule) | Only a session not Established is hard-cleared, so it carries no routes to lose. **An Established session gets only a soft clear** (`clear ip bgp <peer> soft`, today in `privileged.NOT_MEASURED`, measured first), proposed when the diagnosis finds it Established and receiving fewer routes than intent expects. **`clear ip bgp *` is Never.** **No clear at all** (the operator) for a peer in **Idle (Admin)**, an **administratively shut neighbour** (`neighbor … shutdown`), or a **configuration mismatch** such as a wrong remote AS (the last reset reason in `show ip bgp neighbors <peer>` naming a bad peer AS): those raise drift, when the device departs from intent, or an Alert with the diagnosis, when both ends are at intent, never a clear |
| **OSPF adjacency reset** (`ospf_reset`): one OSPF adjacency intent holds, not FULL in two reads in a row, the neighbour reachable on the link, no configuration cause found, and **the interface has exactly one OSPF neighbour** (read with `show ip ospf neighbor <if>`, and intent naming one), so a bounce resets that one adjacency and no other | none in the set (replay test) | **as the port bounce:** Auto, with every one of its guards (13a to 13e) | **the port bounce on that interface** (N17): one adjacency reset, nothing else on the router touched | as the port bounce, and the adjacency FULL | as the port bounce | Resets exactly one adjacency. **`clear ip ospf process` stays Alert,** since it drops every adjacency on the router, **unless the router has exactly one OSPF adjacency,** when it resets only that one and is H5's measured reset under the same guards. R8's router-id proposal (Propose) is unchanged |
| **dampening proposal** (`dampening_proposal`): the port still flapping after its one bounce, or needing a second within 24 h | I5 revised | **2**, a change to intent, proposed | proposed: intent gains `dampening` on that interface (the platform's defaults); Approve… commits that intent edit and deploys it under one hash, as the approving person | the line read back; `show interfaces dampening` shows the interface tracked | `removal.restore_program` of the measured `interface.dampening` shape | A change to intent is a person's (section 2: a heal never pushes intent the device never held), so it is a proposal, never a heal |
| **physical, link or unknown cause** (existing Tier 3 rows) | I5 as today's sheet; an adjacency down at intent | **3** | unchanged, plus **the diagnosis runs first** (19.3) and its result rides in the notice | not applicable | not applicable | unchanged |

**When an action is chosen.** It is chosen only from the deterministic diagnosis, never from AI
text, by a fixed table (`diagnose.ACTIONS`). An action runs only when the diagnosis's
**top-ranked complete hypothesis** is that action's own rule:
- "interface down while administratively up, far end up" → port bounce;
- "a BGP neighbour not Established in two reads in a row, its peer reachable, no configuration
  cause, not Idle (Admin) and not administratively shut" → session clear, a hard clear of that
  neighbour. A wrong remote AS, Idle (Admin) or a shut neighbour is a decisive diagnosis rule
  of its own (protocol, decisive), so no clear follows;
- "an Established BGP session receiving fewer routes than intent expects, no configuration
  cause" → a soft clear of that neighbour, proposed;
- "an OSPF adjacency not FULL in two reads in a row, the neighbour reachable on the link, no
  configuration cause, exactly one OSPF neighbour on the interface" → OSPF adjacency reset, the
  port bounce on that interface (with two or more, Alert).

A decisive finding above it (an MTU mismatch, a cabling mismatch, an ACL) means no action: the
action could not fix it.

**The guards each action meets.** Section 6's fourteen guards apply in their order. Kinds are
allowed in AUTO one at a time, after their dry-run scenario (N8). These are added after guard
13, in this order:

| # | Guard | Setting (default) | Why |
|---|---|---|---|
| 13a | **The precondition is read fresh, and again just before the send.** If it no longer holds: "the port came back by itself", and nothing is sent | none; always on | C78's property for an action: what was decided on is what is acted on |
| 13b | **The far end is up and not held.** It is read on the far device. Guard 7, a person working, applies to **both ends**: a bounce never fights a person working the far end. An unmanaged far end cannot be read, so there is no action | none; always on | The lecture's "its far end up"; protects active work |
| 13c | **Never Mercury's path, never the only path** (the operator). Any bounce, the port bounce and `ospf_reset` alike, is refused when: (1) the interface carries the address Mercury reaches the device on; or (2) **Mercury's route to that address leaves out of that interface:** the device's own `show ip cef <Mercury's source address>` (and `show ipv6 cef` for an IPv6 manager) names it as the egress; or (3) **it is the device's only path:** `blast_radius.radius_of_shutdowns` for its shutdown has a non-empty `reach_lost`, the device itself or any device behind it. Each refusal is Never (Tier 4), as in section 5, in words naming the read and both operands: "Not bounced: r4 reaches Mercury (192.0.2.250) out of GigabitEthernet4 (`show ip cef 192.0.2.250` on r4), so a bounce would cut Mercury's own session to r4"; "Not bounced: GigabitEthernet4 is r4's only path: shutting it leaves r4 and 2 devices behind it unreachable (blast radius)". A session whose loss would withdraw the manager's route is Never too | none; always on | CLAUDE.md, "Operations and safety": a change to the path the tool reaches a device on needs a repair route independent of that path |
| 13d | **Once.** A port is bounced at most once an hour (the lecture's), and a second need within `heal_repeat_halts_hours` (24) is the dampening proposal instead. A session is cleared once per incident, and a second need is can't fix, Tier 3, with its diagnosis | `heal_bounce_per_port_hour` (1) | The lecture's "once"; guard 11's repeat rule, applied per port |
| 13e | **A flap is measured, not felt.** At least N UPDOWN transitions of one interface in M minutes, from `logs-tail` (a new after-store step; `%LINK-3-UPDOWN`, `%LINEPROTO-5-UPDOWN`) | `heal_flap_transitions` (3) in `heal_flap_minutes` (10); the stability window is the same M (N18) | Separates a flapping port from a port that went down once |
| 13f | **A device-side repair route** (the operator, N17). 13c's CEF check covers only the device's return path: it cannot see the interface Mercury's packets arrive on, and in-band routing can be asymmetric. So 13c stays the first refusal, and every bounce and `ospf_reset` also runs inside `configure terminal revert timer <n>`; `configure confirm` is sent only after Mercury reaches the device again and the post-check passes. If the session is lost, the device reverts on its own. It needs the configuration archive (`archive` with a `path`) in the device's intent. Without it the bounce is refused: "Not bounced: r4 has no configuration archive in its intent, so it cannot revert a bounce by itself if Mercury's session is lost. Add the archive's path to r4's intent (host_vars, `archive.path`) and deploy it." | `<n>` (unmeasured): about 2.5 times the bounce's measured settle time (the port up, Mercury's session back, the post-check), in the timer's own unit, rounded up | CLAUDE.md, "Operations and safety": a change to the path the tool reaches a device on needs a repair route independent of that path. The device's own timer is that route |

**The bounce's program, and the lifecycle** (section 11's table, for an action):
- **Preview.** The fixed program and its hash go in the step log before anything is sent:
  `configure terminal revert timer <n>`, then `interface <if>` / `shutdown` / `no shutdown`,
  then `end`. `shutdown` is one of `pipeline._DANGEROUS_PATTERNS`, so the program carries its
  authorisation: the policy's reason for the `port_bounce` kind, in the hash and the receipt.
- **Confirm.** The policy's fingerprint names the kind, and the program's hash is recomputed at
  apply from the stage-4 read.
- **Apply, holding the device.** `routes.deploy.apply_batch` as the policy, inside the revert
  timer, the three lines in one batch: a cut session cannot leave `shutdown` alone, because the
  device receives the batch whole, and the timer reverts it if it does. That is measured in H20
  on r2 and s1, never on s3, together with the time the port takes to come up.
- **Confirm on the device.** Mercury opens a new session to the device. Only when it is in, and
  the post-check passes (the port up, the running configuration equal to the pre-read), does it
  send `configure confirm`. Otherwise it sends nothing more, and the device reverts when the
  timer ends. The step log names which happened and when.
- **Verify.** It reads the port up, the stability window, and the adjacency. The read-back is
  stronger than a deploy's: the running configuration must equal the pre-read, line for line.
  A bounce changes nothing that stays.
- **Rollback.** It ensures `no shutdown`, and says what it achieved. The device's revert is the
  rollback when Mercury cannot reach the device.
- **The never list's "never a whole-configuration replace" is narrowed here, and said so.** The
  revert is the device returning itself to its own archive, taken as this bounce began, which
  is the state Mercury had just read. Mercury sends no configuration of its own. PHASE8_PLAN
  15.2 names the same mechanism as Phase 9's first prerequisite ("a revert timer on every
  autonomous change").
- **Not shipped until measured** (the operator). H20 builds the wrapper, and the bounce stays
  refused ("the revert timer is not measured on <platform>") until the operator's trial below
  has run on that platform.

**The operator's step: one revert-timer trial on r4, before H20 ships the bounce.** It is a
measured probe (preview and record, `scripts/nmas-removal-probe`'s pattern). It runs outside
02:30 to 03:30 America/Denver (the nightly backup window, C2613), not on s3, and restarts no node. Before it, `archive` with a path is in r4's
intent and deployed.
1. **The revert path.** Enter `configure terminal revert timer 1` on r4, bounce Gi4 (no
   management on it), send no confirm, and wait past the timer. Record:
   - whether IOS-XE accepts both commands, and the timer's unit;
   - whether the revert happens, and the lines it logs;
   - whether Gi4 ends `no shutdown` and up;
   - how long each step takes.
2. **The confirm path.** Bounce Gi4 again inside a timer and send `configure confirm` within it.
   Record that no revert follows.
3. **The bounce's settle time** from both runs (the port up, a new session in, the post-check),
   which sets `<n>`.

The IOS dialect's answer needs the same trial on s1. Until then, devices of that dialect have
the bounce refused, naming the unmeasured timer.
- **Record.** Receipt, step log, change record ("port bounced; configuration unchanged") and
  the NetBox journal. **No golden is committed:** the configuration did not change, and the
  golden re-check finds the device at its golden.

**The session clear's lifecycle** is `privileged.py`'s six steps, with two changes:
- **The policy is a caller.** T2-3's "the agent never runs one" is about the AI agent and stays
  true. The heal policy runs as its setter, with `actor_kind="policy"`, as the heal's apply
  does. This rides on H5's policy path for the measured OSPF reset.
- **Two new `COMMANDS` entries,** `clear-bgp-peer` (`clear ip bgp {peer}`) and the existing
  `clear-bgp-soft` measured and moved out of `NOT_MEASURED`. The peer is taken from intent's
  sessions, never typed, and never `*`. Each prompt is measured on r3 or r4. The before-state
  (`show ip bgp neighbors {peer}`, the last reset reason) is kept, under T2-4. The verify rule
  is "Established within the measured bound" (and, for the soft clear, the received routes
  read again).

**The command policy changes for one shape only** (the operator, N16): a hard clear of one named
neighbour whose session was not Established in two reads in a row. Every other hard clear stays
command-policy Tier 3, and `clear ip bgp *` is Never.

**The dampening proposal:**
- **Intent can express dampening.** It cannot today: no hostvars field, template line, parser or
  measured removal shape holds `dampening`. H22 adds the field (`interfaces.<if>.dampening`,
  true for the platform's defaults, N19), its template line, its parser's round trip, and its
  removal shape, measured on both dialects with `scripts/nmas-removal-probe`. **Built
  (H22's first part, 2026-11-07):** the field, its template line, its parser's round trip and
  the shape `interface.dampening` with its probe exemplar. **Measured 2026-11-08:** `exact` on
  both dialects (the IOS switch and the IOS-XE router, Loopback199, the agent's run under the
  Phase 7 mode), so Mode B removes the line. **Built (H22's second part, 2026-11-08,
  `modules/heal/dampening.py`):** the proposal, raised in AUTO only, after a bounce still
  flapping or 13d's second need, one waiting per port; intent's patch `set_dampening`
  (`intent_patch`) and the deploy it renders bound by one hash; the act as the approving person
  (the intent commit, then THE apply, then `show interfaces dampening` on the deploy's own
  session, a read not listing the port rolled back by the pipeline's rollback and the intent
  put back); its `CLEARS` entry (`heal`/`dampening`); its Approve refused by name on a platform
  whose record holds no `exact` row for `interface.dampening` (measured above).
  `dampening_proposal` left `actions.NOT_BUILT`. The verify read's parser is shaped from
  Cisco's documented output for a port with dampening; the answer with none is captured (both
  platforms print nothing, C2761). The first part also built intent's `archive.path` (13f),
  parsed only
  from `archive` with exactly `path <url>`; an intent committed before it keeps its archive as
  an unmodelled block, which renders as before, and a document holding both is refused
  (`hostvars.archive_problems`).
- **The proposal** is an intent patch (`modules/nsot/intent_patch.py`) and the deploy program it
  renders, **bound by one hash**. Approve… (a verified person, a reason) commits the intent edit
  as that person (`Actor-Verified: access`) and deploys it through the pipeline, as the person's
  own deploy. It is never `apply_batch` as the policy, and it is not counted in the heal rails.
- **It clears when** the change is approved and verified; or it is declined with a reason; or
  the interface has been stable for 24 hours (resolved by time, with that said). A new
  `CLEARS` entry, `heal`/`proposal`'s.

**Records and History.** Section 8's marks gain **bounced**, **cleared**, **bounced, still
flapping** and **diagnosed**. Every automatic action notifies (17.7 item 6): "r4 Gi4 bounced
once: still flapping; a dampening change waits for a person". Dry run records "would have
bounced r4 Gi4 (program <hash>)" on the drift row and in History, with Right / Wrong, as section
7 does. **Built (H23's first part, 2026-11-08):** History names each action by its port or
neighbour with its family's marks (`steplog.ACTION_MARKS`: "would bounce", "cleared, not
verified", "dampening proposed"), and opens to its planned window, the far end the window named
(C2749; the row is on the far end's History too), what was sent, verify's result, its rollback
and its own records; every act keeps a deterministic change record (`change_record.build_action`,
board CR's sections); the session clear's held and failed ends are one Needs attention row
(`heal`/`clear`), and every row's action is its notice's What to do (`heal_notice.action_todo`);
each action's end is told once on its incident's thread (`heal_notice.run_actions`: can't fix,
halted, or an automatic success as ``action`` under "every automatic heal"). The NetBox journal
entry for an action, the change record's download, the scenario replays (H12's fixtures) and I5's
sheet (the operator's trial) wait.

**The industry practice it follows:**
- device-native recovery, then suppression (`errdisable recovery`, then IP event dampening);
- an orchestrator's restart with back-off, then escalation;
- the ITIL standard change for the pre-authorised action, and a normal change (a person's) for
  the intent edit.

### 19.5 Item 3: the agentic read-only loop for the can't-fix AI analysis

**The shape.**
- **Pass 1 is section 12's analysis call,** shape B unchanged, plus one optional field: `reads`,
  at most 3 entries, each `{device, command, why, hypothesis}`.
- **Code checks each request** (below). The ones it allows run through the reads engine.
- **Pass 2 is one more call** with the results. Its schema has **no `reads` field**, so it
  cannot ask again.
- Its answer passes Explain's check (`explain.check`), extended so a reference to `read:<n>` must
  name a read that was run and sent.
- **If pass 1 asks for nothing, there is no pass 2.** That is never more than two calls.

**Its two prerequisites (the operator's corrections):**
1. **The read-only device account (H28)** comes before the loop runs on any device. Every AI
   read runs as that account. A device where it does not resolve is refused by name ("no
   read-only account for r4"), never read with the deploy account. It moved here from item 4's
   "after Lab 10" rows.
   - **The credential chain gains a read role.** `modules/credentials.py`'s resolution (device
     override → designated list → role → site → default profile) resolves a second account per
     device for reads. The Credentials profile card gains it (artboard N).
   - **The account reaches each device as an intent change:** an account added, never changed
     (CLAUDE.md, "Operations and safety"), deployed by a person.
   - **It is the operator's credential operation.** The operator types its password; the agent
     never sees it (the Phase 7 mode's secrets stop).
   - **Its device-side shape is measured first** on r2 (IOS-XE) and s1 (IOS): a low privilege
     level, or a role-based CLI view, that runs exactly the AI read set and nothing that
     changes state.
   - **Credential health, retirement and the startup check** cover it, as they cover the deploy
     account.
   - Industry practice: least privilege for service accounts (NIST SP 800-53, AC-6), and a
     separate read account for collection, as monitoring and NetDevOps tools use. Diagnosis,
     collection and drift reads may move to it later (19.11).
2. **The device state egress class (N20)** must be on for the network before any read answer
   leaves the host. It is off by default. With it off, the loop's reads are not asked: pass 1
   is the whole analysis, and it says why.

**The AI read set (`AI_READS`, new; H24).** It is an allow-list the tool enforces, narrower than
a person's allowlist. A request is run only when it passes both checks:
- **`readonly_commands.refusal(command)`, with no extras;**
- **it parses as one of `AI_READS`' command shapes.** Each argument is one token of its shape,
  taken from what Mercury holds: an interface in the device's golden, an address in the
  network's intent or prefixes, a BGP peer intent names, a MAC in MAC shape. Matched by
  parsing, never as a resemblance.

**How the allow-list matches (the operator, N21; OWASP LLM06:2025, Excessive Agency):**
- **The whole command is matched,** verb, words and arguments, against one shape. A command
  with any word the shape does not name is refused.
- **Output modifiers are limited to `include`, `exclude`, `begin`, `section` and `count`:** one
  list for a person's reads and the model's, `readonly_commands.SAFE_MODIFIERS`, which `AI_READS`
  (H24) reuses rather than holding a second (the operator, 2026-11-04, C2423: `count` only
  counts lines and writes nothing). `| redirect`, `| tee`, `| append` and any other modifier
  are refused, because on IOS they write the output to flash or another host.
- **Arguments match strict patterns:** an interface name in the platform's interface-name shape
  that the device's golden holds; one IPv4 or IPv6 address, checked by `ipaddress`; one prefix,
  checked the same way; a peer address intent names; a MAC in dotted MAC shape.
- **Newlines and control characters are refused,** with `?` and any URL.

**What `modules/readonly_commands.py` does today** (probed over HEAD ad202730, 2026-11-03):
- **It already refuses:**
  - `| redirect`, `| tee` and `| append`, naming that they write (`WRITING_MODIFIERS`);
  - `| format` and any other non-filter modifier;
  - a later segment that could be one of them (`| include a|redirect x`);
  - newlines ("one command per entry, no line breaks") and control characters;
  - `?` and any URL.
- **It allows `| count`,** as `AI_READS` now does too: `SAFE_MODIFIERS` holds begin, count,
  exclude, include and section, the one list (C2423).
- **It does not check a `show` command's arguments.** It is verb-shaped by design (C61), and
  only ping, traceroute, dir, more and verify have their arguments checked. So `show interfaces
  GigabitEthernet4 extra junk words`, `show interfaces Gi4; reload` and `show ip route
  999.1.1.1` all pass it. IOS treats `;` as no separator, so the probe shows a wrong argument,
  not a write. For a person's Show commands this is the existing design. For a model's request,
  N21 needs the stricter matcher, `AI_READS` (H24), on top of `refusal`: both must pass.

**The Diagnose… runbooks (item 1) take the same pipe rule now, as a test, not a second path.**
- Their commands are code templates whose arguments come from intent, never typed.
- A test (H14's) renders every command every runbook can produce, for each platform, and holds
  each to `AI_READS`' matcher with `SAFE_MODIFIERS`' five modifiers. The only exceptions are the reads the AI
  set leaves out on purpose, which the runbooks never use.
- **Cost:** one test. **Prevents:** a runbook template gaining `| count` or a writing modifier
  unseen.

**The read loop's required tests** (H25's, written before its code, red then green; each planted
request is refused, and each allowed form passes):

| Planted request | Expected |
|---|---|
| `show interfaces GigabitEthernet4 \| redirect flash:x` | refused: a modifier that writes |
| `show interfaces GigabitEthernet4 \| tee flash:x` | refused: a modifier that writes |
| `show interfaces GigabitEthernet4 \| append flash:x` | refused: a modifier that writes |
| `show interfaces GigabitEthernet4 \| count up` | allowed: `count` is one of `SAFE_MODIFIERS`, one list for people and the model (the operator, 2026-11-04, C2423) |
| `show interfaces GigabitEthernet4 \| format x` | refused: not one of `SAFE_MODIFIERS`' five |
| `show version \| include a\|redirect x` | refused: a later segment that could be a writing modifier |
| `show interfaces GigabitEthernet4` with a newline, then `show running-config` | refused: a newline |
| `show interfaces GigabitEthernet4` with a control character | refused: a control character |
| `show interfaces GigabitEthernet4 extra words` | refused: a word the shape does not name |
| `show interfaces Gi4; reload` | refused: not an interface the device's golden holds |
| `show ip route 999.1.1.1` | refused: not an address |
| `show ip bgp neighbors 192.0.2.99` (a peer intent does not name) | refused: not a peer intent names |
| `show running-config` on a network whose configuration class is off | refused, naming the class |
| `show interfaces GigabitEthernet4 \| include line protocol\|errors` | passes |
| `show ip ospf neighbor GigabitEthernet4 detail \| section Neighbor` | passes |
| `show ip route 192.0.2.5`, `show ipv6 route 2001:db8::5` | pass |
| `ping 192.0.2.4 source GigabitEthernet4 repeat 5 timeout 2`, `ping ipv6 2001:db8::4 repeat 5 timeout 2` | pass |

Each refusal's words are asserted as well as its verdict, so a refusal for the wrong reason
fails. The planted cases are shown able to fail (the property removed in a throwaway worktree,
the aimed tests failing).

The set is the diagnosis's state reads (19.3's table): interfaces, the IP interface,
CDP and LLDP, the OSPF interface and neighbours, BGP summary and neighbours, route, CEF, ARP and
ND, the MAC table by address, spanning tree by interface, and ping (repeat ≤ 5, timeout ≤ 2) and
traceroute (ttl ≤ 16, probe 1, timeout ≤ 2) to an address of the network.

**`show running-config` goes through the existing configuration masking** (the operator, N20).
It and its section forms (`show running-config interface <if>`, `| section <name>`) are
configuration, so they are the configuration class's, never the device state class's:
- they are sent only where a network has the configuration class on, under 15.11's
  conditions: masked by `redact.redact_egress`, a secret's line dropped whole, the smallest
  slice the question needs;
- while the configuration class is off (every network until C1720's marking is built), they are
  refused, naming the class.

**Left out on purpose,** each refused with its reason:
- a secret's position: `show key chain`, `show snmp`, `show users`;
- configuration printed in other forms: `show startup-config`, `show archive`, `show
  access-lists` and `show ip access-lists` (their entries are configuration), `show
  tech-support`;
- `more` and `dir` (files may be configuration);
- `show logging`: the logs reach the model only from Loki, masked, in the pack.

**Mercury's other checks on a request** (each refusal names its comparison and both operands,
and goes to pass 2 as "refused: <why>", so the model sees it):
- the device is one the incident or the pack as sent names, in the incident's network, never
  another network's;
- the device is not held; a held device is skipped by name, never queued;
- at most 3 requests; a fourth is refused "past the 3 reads a pass may ask for";
- **on behalf of a person, as the read-only account:** the reads are recorded as "the AI
  analysis of incident <id>, turned on by <admin>", and they sign in with the device's read-only
  account (IBN_DESIGN section 12 item 2: no AI identity stronger than the person; section 13:
  a fully compromised model can do nothing the person could not already do). The AI read set is
  a strict subset of what that admin may read, and the account enforces it on the device too.

**The reads themselves:**
- run by `reads.run` with a new caller kind, `ai_analysis`, with no extras: held, masked by
  `redact.redact_text`, recorded on History › Reads;
- concurrent across devices, each inside its bound; the loop's reads bounded at 60 s in all,
  about 2.5 times the expected measure (to be measured in H27);
- **each answer capped at 4 KiB for the model** (`AI_READ_CAP`), saying "cut" with the whole
  answer's hash, as the reads engine does. The record keeps the reads engine's own cap.

**Masking and egress** (15.11; the irreversible tier):
- A read's output is not one of 15.11's classes today: it is neither an alert label, a metric
  series, a masked log line nor an intent diff. **A new class, device state** (the operator,
  N20), holds the AI read set's answers (operational state, by command shape):
  - off by default on every network;
  - turned on per network by an admin, with a reason, recorded with who and when (the
    configuration class's pattern, 15.11 and 13.1), in Settings › the network's AI data
    classes (artboard N);
  - off is one click, and it stops new sends at once;
  - a classification marking forces it off, as every class (C1720);
  - `egress_classes.device_state_allowed(network)`, new, beside `topology_allowed`.
- **Every send is logged:** each answer's bytes after masking, its lines dropped and withheld,
  in History's AI calls (15.14), beside the reads run it came from.
- Every answer is masked by `redact.redact_egress`: by position and by known value, then every
  secret, password, key and hash shape.
- **A line with a secret's shape is dropped whole,** not masked, and counted (15.11's condition
  2, applied here).
- Every answer passes `injection.withhold_parts` (`modules/ai/injection.py`). Device text is
  writable by others: descriptions, BGP neighbour descriptions, CDP device ids.
- The gateway's `redact.egress_payload` covers every byte. The hand check (changed lines'
  mutants by hand, a must-die canary, `docs/TIER_HAND_CHECK.md`'s log) comes before the deploy
  (H26).
- **injection.py's premise changes, and is said.** Its docstring says "the model has no acting
  tool". A read request is not an action, and code decides whether it runs. When built, the
  docstring says "the model may ask for reads from a fixed set; code decides", and its test
  names the loop.

**Cost (PHASE8_PLAN 18.3's rules):**
- **Trigger:** each pass is a gateway call with `trigger background`, the analysis job's id,
  under the feature `heal_analysis` (section 12). The gateway checks the feature's switch for
  the network, and the caps, **before each pass**.
- **A cap reached between the passes:** pass 2 is refused and recorded with no provider
  request. The answer shown is pass 1's: "second pass not run: the day's cap for this feature
  is reached".
- **`calls_per_finding` becomes 2.** The estimate shown at Turn on uses it (board G's insert).
- **The cost per finding, estimated:** pass 1 at about Explain's measured $0.0257, and pass 2
  that plus up to 3 × 4 KiB of answers (about 3,000 input tokens), so **about $0.06 a finding**.
  At worst it is $0.16, two calls at the $0.08 per-call cap.
- **The caps are unchanged** ($1.00 a day, $10.00 a month on Default). That is about 16
  analyses a day at the estimate. The lab walks expect about 5, about $0.30 a day.
- The measurement round (H27) replaces the estimate with the measured figure, which the board
  shows.

**Timing.** Section 12's 60 s wait is kept. The notice carries what is ready (decision N22,
recommended):
- pass 1's answer, if it is back within 60 s, labelled "first pass: Mercury is running the 2
  reads it asked for";
- otherwise "AI analysis: pending".

The follow-up on the same thread carries the final answer. That is at most one follow-up, as
section 12 already allows.

**History (15.14's AI calls).** Each pass is its own row: trigger, cost, and the check's
verdict. Between the two passes, each read request is a row, linked to both:
- what was asked (device, command, why, the hypothesis it tests);
- the verdict, run or refused, with the reason and both operands;
- the reads run on History › Reads;
- the bytes sent after masking, and any lines dropped or withheld.

The incident's step log gets one step: "AI analysis: asked for 3 reads; 2 run, 1 refused;
second pass answered". Nothing in the heal loop reads the steps or the answer. Section 12's
mechanised test is extended to the loop's module.

**The relation to Lab 9's tool-calling candidate** (docs/LAB9_SDN_GAP.md, its section 4,
candidate 3, estimated there at 4 to 5 agent-days because it adds provider tool turns to the
gateway). This loop uses no provider tool turns (N21). If candidate 3 is built later, it reuses
this check and this record, one home for "a model asks for a read".

**The industry practice it follows:**
- ReAct, and the provider's own pattern: the model requests, the application runs;
- OWASP LLM06: a fixed function set, read-only permissions, a bounded number of calls, and
  nothing high-impact without a person;
- LLM01's mitigations: untrusted content flagged and withheld, and the model's output never
  executed;
- LLM02: masking at the boundary;
- agent frameworks' bounded iterations: here exactly one round.

### 19.6 The revised I5 demo: bounced once, still flapping, dampening proposed (a draft sheet)

**The guard stays; the sheet changes** (the operator, N15). The bounce's precondition keeps "far
end up": the flapping port down while administratively up, the far end administratively up and
up, and neither end held. A guard is never loosened to make a sheet pass. Today's sheet makes
the flap with a Tcl loop on r4, which shuts r4 Gi4 in each down phase and logs a CONFIG_I each
time, so r4 is "a person working" (guard 7, and 13b on both ends). **On that sheet the bounce is
refused, correctly.** The automatic diagnosis's first hypothesis is then "r4 Gi4
administratively down, by a person on r4 (decisive)", which is the right answer.

**The revised sheet is a draft until the operator's trial is measured.** The flap moves below
the configuration: the lab host takes r4 Gi4's virtual link down and up at the hypervisor
process (believed available through the vrnetlab container's QEMU monitor, `set_link`;
unmeasured). Neither router then logs a CONFIG_I. This is lab tooling under `lab/`, never the
product.

**The operator's step: one trial on the lab host, before the sheet is written.**
1. Outside 02:30 to 03:30 America/Denver (the nightly backup window, C2613), not on s3, with no restart of any node (the standing facts),
   take r4 Gi4's virtual link down once at the hypervisor process, for about 15 s, then up.
2. Record **what r4 sees:** whether Gi4 reads "down, line protocol is down" while
   "administratively up", the UPDOWN lines it logs, and the time each takes.
3. Record **what the far end, r3, sees:** whether r3 Gi4 stays up and line protocol up, or goes
   down too, and what it logs (the OSPF adjacency's drop on its dead timer).
4. The result decides the sheet (the operator confirmed: r4 is the toggled side, r3 the far
   end, and the bounce is on r4 Gi4):
   - **r4 down while admin up, r3 up:** the bounce's precondition holds, and the draft rows
     below become the sheet (the cycle, 15 s down and 45 s up for 10 minutes, is the operator's
     to confirm);
   - **both ends go down:** the far end is not up, so **the bounce stays refused,** and I5 needs
     another staging. It is never run with a looser guard (the operator);
   - **anything else:** that is said, I5 runs as today's sheet (Alert, diagnosed, not bounced),
     and the bounce's proof is its replay test alone.

This trial is the operator's step, not the agent's. The agent writes the sheet from its result.

**The draft rows** (for the operator's trial to confirm; the tiers by name, as the screens show
them):

| # | Scenario | Device | What Mercury detects | Tier | What it does | What verify reads | What the person sees |
|---|---|---|---|---|---|---|---|
| 8 (draft) | **I5 revised:** r4 Gi4 flapping, made at the lab host, both ends at intent | r4 (r3 the far end) | r4's "Interface down" (port down, admin up), and 3 UPDOWN transitions on r4 Gi4 in 10 minutes (13e); r4 at intent; Alert, so the **diagnosis runs first**: r4 Gi4 down while admin up, r3 Gi4 up and admin up, CDP last saw r3 on r4 Gi4 as intent cables it, no CONFIG_I on either end, no input errors. First hypothesis: physical on r4 Gi4 (decisive) | **Auto**, port bounce (allowed in Auto mode on Default after its dry run) | the precondition read again (13a), then `interface GigabitEthernet4` / `shutdown` / `no shutdown` on r4, one batch, its hash first | up within its settle bound; then the stability window: **2 more transitions within 10 minutes, so still flapping**; the configuration did not move | History: "r4 Gi4 bounced once, still flapping" (amber); Needs attention: **"A change waits for a person: dampening on r4 Gi4"** (Propose) with the intent edit and one hash; the email: can't fix, Mercury's diagnosis, the bounce and its result, the proposal waiting, then the AI analysis (its reads, for example `show interfaces GigabitEthernet4` on r4 and r3, in History) |
| 8b (draft) | **The proposal approved** (a person) | r4 | — | **Propose**, a person's change | Approve…: the intent edit committed as the person, then deployed (`dampening` on Gi4) | the line read back; `show interfaces dampening` lists Gi4 | the flap suppressed while the lab host's cycle runs; the proposal row clears (approved and verified) |
| 7+ | **C4 plus Diagnose… on demand:** from r7's "Device unreachable" | r6 | a person presses Diagnose… on the alert: "Can't reach r7" from r6's neighbour on the Gi2 link | none (reads only) | "A can't reach B": the ping fails; the path trace reaches r6; **the first divergent hop is r6**: an inbound ACL on Gi2 that intent does not hold (decisive), which the heal had classed Never | not applicable | the diagnosis card: the hop, the binding, the ACL's counters, the read that confirms it; History, kind diagnosis |

**The rails hold.** The bounce is r4's one action that hour, and the dampening deploy is a
person's, not a heal. Section 15's row 8 (r3's trigger, today's sheet) stands until the trial is
measured.

**The video's beats gain:**
- I5's "bounced once, still flapping, dampening proposed";
- C4's Diagnose… finding the hop;
- the AI analysis's reads in History.

### 19.7 The estimate, in agent-days and in the measured ratio

Each part's tests are written with it, red then green (section 14). **The measured ratio**
(PHASE8_PLAN 0.3, C2380): one agent-day is about 1.3 wall-clock hours for one agent (0.7 to
2.6), and about 4M weighted tokens (2.5M to 9M).

| Part | What | Days | Stream | Depends on |
|---|---|---|---|---|
| H14 | The diagnosis engine (`modules/heal/diagnose.py`): steps, reads through the reads engine as kind `diagnosis`, the comparison with the network model, `RULES` and the ranking; the "adjacency down" runbook (OSPF, OSPFv3, BGP); the per-device diagnosis lock, `MAX_COMMANDS` (70) and the runbooks' pipe-rule test | 2.0 | B | H6 (the step log store, for its records); the reads engine and network model (built) |
| H15 | The "A can't reach B" runbook on `path_trace`; per-hop interface, ARP and ND, MAC and STP, route source and ACL checks; the return path; **the IPv6 form** (`show ipv6 cef` parsed and followed) | 1.5 | B | H14 |
| H16 | Diagnose… on the device page's Actions menu, on an alert's card and on a can't-fix row (gated, declared, invalidated, busy on itself); the result card; the manual's how-it-works pages and their diagrams | 1.0 | B | H14, H15; H9's screens |
| H17 | The automatic run on an Alert incident before notifying, and on a Propose incident before it is offered for approval (the diagnosis on the proposal's row, email and Approve…); the storm bound; the notice's diagnosis block and its follow-up; the `diagnosis` pack section for H8 | 0.75 | B | H3 (the Tier 3 outcome), H14, H7 (built), H8 |
| H18 | The runbooks' captures (the reads marked **no** in 19.3, on r2 and s1) and one scenario replay per runbook | 0.5 | B | H14 to H17; H11's walk |
| H19 | The four action kinds in the tier table; guards 13a to 13e; flap detection (an after-store step on `logs-tail`); `diagnose.ACTIONS` | 1.0 | A | H2 (triggers), H3 (classification), H14 |
| H20 | The port bounce, and the OSPF adjacency reset through it: the fixed program and its authorisation, `apply_batch` as the policy, verify with the stability window and the configuration-did-not-move read-back, its rollback; guard 13c's management-path and only-path checks (`show ip cef` toward Mercury, the blast radius) and their refusals; `ospf_reset`'s exactly-one-neighbour read; **13f's revert timer**: the wrapper, the new session and the post-check before `configure confirm`, the no-archive refusal, the per-platform "not measured" refusal until the operator's trial; measured on r2 and s1 | 1.75 | A | H4 (act and verify), H19 |
| H21 | The BGP clears (N16): `clear-bgp-peer` (hard, one named neighbour, not Established in two reads) and `clear-bgp-soft` (an Established session), each measured on r3 or r4, run through `privileged.py` by the policy on a lab network and as a proposal elsewhere | 1.0 | A | H5 (the policy path), H19 |
| H22 | The dampening proposal: intent's `dampening` field, template line, parser round trip, the measured `interface.dampening` shape, the one-hash intent commit and deploy, its `CLEARS` entry; **intent's configuration archive** (`archive.path`): its field, template line and parser round trip, which 13f needs | 2.0 | A | H5 (the proposal routes), H6; the intent editor (built) |
| H23 | The actions' History marks, rows, notices, change records and manual; the scenario replays; I5's sheet written from the operator's trial (19.6) | 1.0 | A | H20 to H22, H9, H11, H12; the operator's trial |
| H24 | `AI_READS`: the allow-list matching the whole command (N21): its shapes, `SAFE_MODIFIERS`' five modifiers (C2423), strict argument patterns (interfaces, addresses, prefixes, peers, MACs), the device scope, each refusal's words; `show running-config` routed to the configuration class | 1.0 | B | the allowlist (built); can start first |
| H28 | **The read-only device account, item 3's prerequisite:** the credential chain's read role, the Credentials card, the device-side account in intent (an account added), its shape measured on r2 and s1, credential health, retirement; the reads engine signs AI reads in with it and refuses a device without one; the device state egress class (N20) and its per-network switch | 2.0 | B | the credential chain and the reads engine (built); the operator's credential operation for the password |
| H25 | The loop: pass 1's `reads`, the check, the reads as kind `ai_analysis`, the cap per answer, pass 2's schema and the extended check, the cap check before each pass, `calls_per_finding` 2; **the required tests of 19.5** (each planted refused form refused, each allowed form passing), written first | 1.25 | B | H8, H24, H28 |
| H26 | The loop's History rows (15.14), every send logged, the step-log step, the loop-never-read test, the egress hand check | 0.75 | B | H25, H6 |
| H27 | The measurement: H13's 3 recorded cases × 10 runs at two passes (about $2), plus the planted refusals as tests | 0.5 | B | H25, H26, H13 |
| H29 | **The SDN read set (19.12):** the operation table, `ReadOnlyDriver` (GET only, every write endpoint refused), arguments against the current topology, the new `port_desc` read for `link_state`, the Analyst's and Responder's pass-1 field, the device state class for SDN reads; its required tests and the canary | 1.75 | B | H25, H26 (the loop); the Ryu driver (built); Lab 9's trace for `path_trace` |
| H30 | The SDN reads in History, and the replay of reads from a case's captured pack for the evaluation ("not captured" counted) | 0.75 | B | H29 |
| H31 | **B4's evaluation (19.13):** the paired comparison, its intervals, both arms' batch runs, the live-path timing subset, the report against the frozen pass rule | 1.0 | B | H29, H30; the ledger read first |

**Per item, and in total:**

| Item | Agent-days | Wall-clock for one agent (× 1.3 h; 0.7 to 2.6) | Weighted tokens (× 4M; 2.5M to 9M) |
|---|---|---|---|
| 1, diagnosis runbooks (H14 to H18) | 5.75 | about 7.5 h (4.0 to 15.0) | about 23M (14M to 52M) |
| 2, action remediations (H19 to H23) | 6.75 | about 8.8 h (4.7 to 17.6) | about 27M (17M to 61M) |
| 3, the AI read loop for the routers (H24 to H28), **with its read-only account** | 5.5 (3.5, plus H28's 2.0) | about 7.2 h (3.9 to 14.3); H28 alone about 2.6 h (1.4 to 5.2) | about 22M (14M to 50M); H28 alone about 8M (5M to 18M) |
| 3, the SDN read set (H29, H30; Lab 9's B4) | 2.5 | about 3.3 h (1.8 to 6.5) | about 10M (6M to 23M) |
| 3, B4's evaluation (H31; Lab 9's B4) | 1.0 | about 1.3 h (0.7 to 2.6) | about 4M (2.5M to 9M) |
| **The amendment** | **21.5** | **about 28 h (15 to 56)** | **about 86M (54M to 194M)** |
| **Board H with the amendment** (16.25 + 21.5) | **37.75** | **about 49 h (26 to 98)** | **about 151M (94M to 340M)**, roughly 12% of a week's usage (7 to 26%) |
| of which Lab 10's (all but H29 to H31) | 34.25 | about 45 h (24 to 89) | about 137M (86M to 308M) |

**The growth since the first draft:**
- **The six changes:** H14 (+0.25: the per-device lock, the command cap, the pipe-rule test),
  H17 (+0.25: diagnosis on Propose rows), H20 (+0.25: the management-path and only-path checks)
  and H24 (+0.25: the whole-command matcher), 1.0 day in all.
- **The revert timer:** H20 (+0.5) and H22's archive field (+0.5), 1.0 day.
- **The SDN read set and B4's evaluation:** H29 to H31, 3.5 days.

**The streams.** H1 and H7 are built (commit 24aef7b6). What is left:
- **stream A:** H2 to H6, H11 and H12 (8.25), plus item 2's H19 to H23 (6.75), so **15.0
  days**, about 19.5 h (10.5 to 39.0);
- **stream B, Lab 10's parts:** H8, H9, H10 and H13 (5.0), plus item 1's H14 to H18 (5.75) and
  item 3's H24 to H28 (5.5), so **16.25 days**, about 21.1 h (11.4 to 42.3);
- **stream B, then Lab 9's:** H29 to H31 (3.5), so **19.75 days** in all, about 25.7 h (13.8 to
  51.4).
- **Stream B's order:** H24 and H28 first (they depend on nothing unbuilt), then H8. H14 is
  written against H6's store once it lands. H29 to H31 come after Lab 10's parts (the
  operator's order).
- **The critical path:**
  - **For Lab 10,** stream B's 16.25 days plus its 14 parts × 1.5 gates × 17 minutes (about 6
    hours) is **about 27 hours (17 to 48)**. Stream A, 15.0 days and 12 parts, is about 25
    hours (16 to 44).
  - **For B4,** stream B continues: 19.75 days and 17 parts (about 7 hours of gates) is
    **about 33 hours (21 to 59)**.
- **Spend:** about $2 for H27, about $1 more in the walks at two passes, and about $1.5 to $1.9
  for B4's evaluation (19.13), inside the $161.19 left (PHASE8_PLAN 0.5's latest figure).

**The date risk, said early:**
- **Lab 10 (due 2026-11-23 23:59 MT):** not threatened at the estimate.
  - **The agent-time arithmetic:** its critical path is about 27 hours of one stream's agent
    time. Over the build window (Nov 5 to 14) that is about 2.7 hours a day, and 4.8 hours a
    day at the range's top. The walks (to Nov 19) and the submission days (Nov 20 to 23) are
    the margin.
  - **The real risk is not agent hours. It is the operator's steps in the chain:**
    - the lab-host I5 trial;
    - the r4 revert-timer trial (and s1's);
    - the read-only account's password and its deploy;
    - turning the device state class on.
  - The bounce cannot ship before its trial, and item 3 now cannot be cut, so the read-only
    account's credential operation should be scheduled early in the window.
  - If the trials slip, the bounce is the last cut (19.8) and I5 runs as today's sheet. Lab 10
    still meets its requirements.
- **Lab 9 (due 2026-11-30):** B4 is the most exposed item, because it sits at the end of the
  chain (Lab 10, then item 3 for the routers, then the SDN read set, then the evaluation).
  - At the estimate, H29 to H31 need about 4.6 hours after Lab 10's stream B. If Lab 10's
    build lands by about Nov 19, that leaves about a week.
  - **The threat is the dependencies,** not the build:
    - Lab 9's trace (for `path_trace`): without it, that operation is refused "not built" and
      the others run;
    - the fresh blind set (the operator's capture session), without which B4's blind result
      rests on 11 to 13 spent-set cases;
    - the hardware's arrival (the Arista and HP models on Thursday), for the drivers' reads.
  - Lab 9's own build shares the same two agent slots (docs/LAB9_SDN_GAP.md, section 3), so a
    slip in Lab 10's stream B moves B4 day for day. That is said in each report's schedule
    line.

If a stream runs behind, 19.8's cut order applies, and the report says which part and why.

### 19.8 The revised cut order (sections 16 and 17, merged)

**Never cut** (the operator's directions):
- the heal loop, its guards, its records and C4's notification (section 16);
- **item 1,** both runbooks, automatic on Alert and Propose incidents and on demand (H14 to H18);
- **item 3, the AI read loop, whole: H24 to H28 with the read-only device account and the device
  state class, and H29 to H31.** It now carries Lab 10's item 3 and Lab 9's B4.

docs/LAB9_SDN_GAP.md's usage-cut order (its section 5) still names "B4 as candidate 1" as its
second cut. Since B4 is now the read loop, that line is the operator's to restate there.

**Built, so off the list:** verification codes (H7) and the installation's kill switch (H1),
both in commit 24aef7b6.

**Applied only when an item is actually behind, and said in the report when it is** (section
16). In order:
1. **The webhook formats:** already deferred to after Lab 10, not cut (C2387). Nothing is left
   to cut here.
2. **Item 2's BGP clears (H21).** No demo scenario needs them. A stuck session stays Alert,
   with its diagnosis.
3. **"The process clear": `clear ip ospf process`, measured (H5's).** This is the whole-process
   reset, used in two places only: R8's router-id proposal (Propose), and a router with exactly
   one OSPF adjacency (N17). If it is cut, R8's proposal applies the router-id and offers
   Mercury's Reload in a planned window instead, as section 16 says, and the single-adjacency
   router stays Alert. It is **not** step 5's bounce.
4. **Item 2's dampening proposal, to its lean form (H22's one hash).** The proposal drafts the
   intent edit and opens it in the intent editor, for the person's own commit and deploy. The
   field, the template line, the parser and the measured shape stay. So does the archive field,
   which 13f needs.
5. **"The bounce": the port bounce, and `ospf_reset` through it (H20), last of item 2.** This
   is the interface bounce (`shutdown` / `no shutdown` on one interface, inside the revert
   timer), which also resets one OSPF adjacency on an interface with exactly one OSPF
   neighbour. It never sends `clear ip ospf process`, and it is **not** step 3's process clear.
   If it is cut, or its revert-timer trial has not run, I5 runs as today's sheet (Alert,
   diagnosed, notified), and a stuck single-neighbour adjacency stays Alert.

Each cut keeps Lab 10's requirements. A cut part is deferred with a row, never dropped. The
critical path is 19.7's: about 27 hours for Lab 10 (stream B), then about 33 hours to B4's
evaluation.

### 19.9 Item 5: the crosswalk to the lecture's tiers, and its maturity ladder (for the video and the write-up)

**The crosswalk** (the operator, 2026-11-03, from the lecture's slides). The lecture has three
tiers, numbered by rising autonomy. Board H keeps its four tiers and their numbers in code, and
every screen shows them by name.

| The lecture's tier | Its meaning | Board H's tier: its name on screen (its number in code) | What Mercury does there | The lecture's examples and this amendment's kinds, placed |
|---|---|---|---|---|
| **T1, read-only diagnosis** | the tool gathers and analyses; a person fixes | **Alert (3), plus diagnosis** | sends nothing; runs the diagnosis runbook (item 1), then notifies with it | physical or link down while admin up, an unknown cause; `clear ip ospf process` on a router with several adjacencies |
| **T2, a suggested fix a person approves** | the tool proposes the change; a person approves it | **Propose (2)** | the program and its hash on a Needs attention row; Approve… by a verified person, with a reason | dampening when still flapping; a soft clear of an Established BGP session; a hard BGP clear on a network not marked lab; R8's router-id and process reset; QoS; a secret added back |
| **T3, auto-remediate low-risk, well-understood cases** | the tool fixes it, verifies, records and notifies | **Auto (1)** | heals or acts under a person's standing policy, once, verified, rolled back on failure, recorded, notified | the four configuration kinds of section 5; the port bounce; the OSPF adjacency reset through it; a hard clear of one named BGP neighbour on a network marked lab |
| **the lecture's "poor candidates"** | what should never be automated | **Never (4)** | never automatic; notifies, with Diagnose… offered | security ACLs, credentials and AAA, Mercury's own path, multi-device causes, `clear ip bgp *` |

**Mercury on the lecture's L0 to L5 ladder** (the lecture's own, the operator's source; it
replaces the first draft's TM Forum placement):

| Level | The lecture's meaning | Mercury | Evidence in the code or the plan |
|---|---|---|---|
| L0, manual CLI | a person at the device's prompt | **left behind** | no terminal steps (CLAUDE.md, "Operations and safety"); the break-glass terminal removed (R39); every read through the reads engine (`modules/nsot/reads.py`) |
| L1, scripted collection | scripts gather state from devices | **has** | the readers (`modules/reader_job.py`, `modules/readers/`); Show commands across devices (`modules/nsot/reads.py`, `fanout.read_each`); captures (`modules/capture_job.py`); the drift reads (`modules/drift_check.py`) |
| L2, parsing and correlation | the output is parsed and events are correlated | **has** | the parsers (`modules/nsot/parsers/`, `platform_reads.json`); the network model (`modules/network_model.py`); the evidence pack correlating alerts, logs, neighbours and changes (`modules/evidence_pack.py`); the blast-radius fold (`modules/nsot/blast_radius.py`); attribution and one row per cause (PHASE8_PLAN 20.2, 20.5) |
| L3, rules-based diagnosis: runbooks as code | stored, deterministic runbooks find the cause | **the gap: item 1 fills it** | no runbook exists today. The nearest are the path trace (forwarding only, IPv4, `modules/path_trace.py`), the drift check and intent match (configuration comparisons), and Explain (AI, advisory, not rules). H14 to H18 build the two runbooks |
| L4, approved or automated remediation | the fix is applied, with a person's approval or automatically | **approved: has; automated: board H, being built** | approved: the deploy pipeline (preview, confirm by hash, verify, rollback: `modules/pipeline.py`), restore, Mode B removal, privileged commands (`modules/nsot/privileged.py`), Reload. Automated: the heal policy (H1, built: `modules/heal/policy.py`) and the loop (H2 to H6), on networks marked lab only (C2009's guard); item 2's actions |
| L5, AI-assisted | AI helps analyse and propose | **has, in beta** | Explain (`modules/ai/explain.py`), Ask in words, Change it in words; the can't-fix analysis (H8) and its read loop (item 3). Advisory only: no fix runs from AI text (section 12) |

**So Mercury has L0 to L2, approved L4, and L5 in beta. L3, rules-based diagnosis, is the gap
the lecture's ladder exposes,** and item 1 fills it. That is why item 1 is never cut (19.8).
Automated L4 arrives with board H's build.

### 19.10 Decisions for the operator (one line each: the decision, the recommendation, the practice it rests on)

N15, N16, N17 and N20 are as the operator set them in review; the others are recommendations
for the operator to approve.

- **N14, diagnosis on which tiers:** automatic on Alert (Tier 3) incidents before they notify and on Propose (Tier 2) incidents before they are offered for approval, the diagnosis attached to the proposal, and Diagnose… on demand everywhere, Never included (the operator); practice: incident platforms run automated diagnostics when an incident opens and attach them before or as a person is asked to act (PagerDuty Process Automation, Rundeck), the triage-before-treatment step of Google's SRE book, chapter 12, and a change approver sees the evidence before approving (ITIL change evaluation).
- **N15, I5's staging:** keep "far end up" and never loosen a guard to make a sheet pass; the flap moves to the lab host, the operator's one trial records what r4 sees and what the far end, r3, sees, and the I5 sheet stays a draft until it is measured (the operator); practice: test the safety control against a real fault rather than relaxing it, the Principles of Chaos Engineering (a hypothesis about steady state, real-world events injected, the blast radius kept small).
- **N16, the BGP clears:** a hard clear of one named neighbour only when it was not Established in two reads in a row, a soft clear for an Established session, `clear ip bgp *` Never, and no clear at all for a peer in Idle (Admin), an administratively shut neighbour or a configuration mismatch such as a wrong remote AS, which raise drift or Alert instead; Auto on a network marked lab, Propose by default (the operator); practice: route refresh resets nothing that works (RFC 2918, RFC 7313), so a soft clear is the first resort for an Established session; a hard reset is kept to one peer that RFC 4271's state machine shows is not Established; and a reset never fights a cause it cannot fix (a shut neighbour or an AS mismatch comes back down at once, RFC 4271's OPEN message error, Bad Peer AS).
- **N17, a stuck OSPF adjacency:** `ospf_reset` resets that one adjacency through the port bounce on its interface, only when the interface has exactly one OSPF neighbour, with every one of the bounce's guards; any bounce is refused when the interface is on Mercury's management path to that device (the address Mercury reaches it on routes out of it, by the device's own CEF lookup, the first refusal) or is the device's only path; because that check sees only the return path and in-band routing can be asymmetric, every bounce and `ospf_reset` also runs inside `configure terminal revert timer <n>`, with `configure confirm` only after Mercury reaches the device again and the post-check passes, so a lost session reverts on the device; it needs the configuration archive (`archive` with a path) in intent, and a device without it has the bounce refused, naming the intent field; `<n>` is about 2.5 times the bounce's measured settle time, unmeasured until the operator's r4 trial, and H20 does not ship the bounce until that trial has measured the revert timer, the confirm and the restored `no shutdown`; `clear ip ospf process` stays Alert, unless the router has exactly one OSPF adjacency (the operator); practice: the smallest blast radius that clears the fault, since RFC 2328's InterfaceDown event (sections 9.3 and 10.2) resets only the neighbours on that interface while a process reset drops every one; a change to the tool's own path needs a repair route independent of it (CLAUDE.md, "Operations and safety"); and a change that can cut the tool's own path needs a device-side rollback timer (the IOS configuration archive's revert, Junos `commit confirmed`).
- **N18, the flap threshold and the stability window:** 3 transitions in 10 minutes to call a flap, and the same 10 minutes to call a bounce stable, revisited from the lab's recorded flaps; practice: IP event dampening (Cisco IOS `dampening`) and BGP route flap damping (RFC 2439) both define a flap as repeated transitions inside a decaying window.
- **N19, dampening's parameters:** the platform's defaults (bare `dampening`), measured on both dialects, with parameters a later intent field; practice: vendor defaults first, tuned only on measurement, and CLAUDE.md, "If the safe path is tedious, people route around it" (inherited defaults over settings).
- **N20, the egress of device state:** a new class, device state, off by default and turned on per network by an admin with a reason; the AI's show commands come from an allow-list the tool enforces; `show running-config` goes through the existing configuration masking, under the configuration class; every send is logged (the operator); practice: default-deny information-flow control (NIST SP 800-53 AC-4) and OWASP LLM02:2025, Sensitive Information Disclosure (restrict and sanitise what reaches the model).
- **N21, how the AI asks for reads, and what it may ask:** a field of pass 1's strict schema, not the provider's tool use, so pass 2's schema cannot ask again; the read allow-list matches the whole command, its output modifiers only include, exclude, begin and section, `| redirect`, `| tee`, `| append` and any other modifier refused because on IOS they write to flash, its arguments matched against strict patterns (interface names, addresses, prefixes), and newlines and control characters refused; the build's required tests plant each refused form and see it refused, and see the allowed forms pass (the operator); practice: OWASP LLM06:2025, Excessive Agency (minimise the functions, permissions and autonomy a model can reach), schema-validated output (OWASP LLM05:2025) and the bounded request-then-run loop of ReAct (Yao et al., 2022).
- **N22, the notice while the loop runs:** pass 1's answer in the notice if back within 60 s, labelled "first pass", and the final in the one follow-up on the same thread; practice: incident platforms page at once and add context as updates to the same incident, and mail threads by In-Reply-To and References (RFC 5322).
- **N23, what the diagnosis may carry to the AI:** its hypotheses in Mercury's words as the allowed class, the values it compared only where the device state class is on, never an ACL's entries, a key or a configuration line; practice: data minimisation, the smallest slice the question needs (15.11's condition 3; OWASP LLM02:2025).
- **N24, how many diagnoses, and how large:** at most one diagnosis at a time per device, at most 3 automatic diagnoses at once per network, and at most 70 device commands per diagnosis (`diagnose.MAX_COMMANDS`, about 2.5 times the longest runbook's own 28, "adjacency down" on a dual-stack OSPF and BGP link), a run that reaches the cap saying where it stopped; the rest offer Diagnose… on their rows (the operator); practice: the bulkhead pattern (concurrency bounded so one failure cannot exhaust the whole; Nygard, *Release It!*), alert grouping into one incident per cause (Prometheus Alertmanager's `group_by`), and a bound about 2.5 times the measured size (CLAUDE.md, "Bounds are about 2.5x a measured time").

### 19.11 Rows to record once the operator has reviewed this (the register is not edited here)

- the diagnosis runbooks themselves (Lab 10: blocks, area NSoT/devices);
- the reads with no capture or parser: `show ip ospf interface`, `show ip bgp neighbors`, the
  df-bit and sourced pings, traceroute, `show ip route <prefix>`, `show ipv6 cef`, `show mac
  address-table address`, `show spanning-tree interface`, `show ip access-lists <name>`;
- **the path trace reads IPv4 only** (`path_trace.refusal`): the IPv6 form of "A can't reach B"
  (C1245's epic);
- **intent cannot express interface dampening:** no field, template line, parser or measured
  removal shape;
- `clear ip bgp <peer>` and `clear ip bgp <peer> soft` unmeasured, and the command policy's one
  new shape (N16);
- the I5 sheet a draft until the operator's lab-host trial is measured (N15);
- **show output is in no egress class:** the device state class to build (N20);
- **the read-only device account,** item 3's prerequisite (H28), with diagnosis, collection and
  drift reads moving to it later;
- injection.py's "no acting tool" premise, to restate when the loop is built;
- **a `show` command's arguments are not checked by `readonly_commands.refusal`:** `show
  interfaces Gi4; reload` and `show ip route 999.1.1.1` pass it (probed 2026-11-03). That is
  harmless on IOS, which has no command separator, but a person's Show commands accept words
  no shape names. UNKNOWN, its one measurement: whether any show argument on either dialect
  does more than print. The AI's reads are covered by `AI_READS` (N21);
- `| count` is a safe modifier for a person and refused for the model (N21).

- **UNKNOWN until measured, its one measurement the operator's r4 trial (19.4):** whether
  IOS-XE and vIOS both support `configure terminal revert timer` and `configure confirm`, and
  whether a revert restores `no shutdown` on the bounced interface. PHASE8_PLAN 15.2 item 1
  holds the same unknown;
- **UNKNOWN: the revert timer's `<n>`,** unmeasured; its one measurement is the bounce's settle
  time in the same trial;
- **intent holds no configuration archive** (`archive` with a `path`): the field, its template
  line and its parser are H22's;
- **the SDN read set's link state needs a read the driver lacks** (`GET /stats/portdesc/<dpid>`),
  and its path trace needs Lab 9's trace (19.12).

The rows for item 4 (a read-only MCP server, NetFlow and IPFIX, and packet capture) are in the
agent's report, with the existing rows each one was searched against (C1004 for flows, C762 for
capture). The read-only device account left item 4 for item 3's prerequisites.

### 19.12 The SDN read set: item 3 extended to the SDN Analyst and Responder (Lab 9's B4, approved)

**The operator's approval, 2026-11-03.** B4, Lab 9's advanced technique, is built as a Mercury
feature: the bounded read loop of item 3, for the SDN Analyst (Lab 9's B1, the live analyst) and
the Responder (the loop's classification, `sdn_classify`, PHASE8_PLAN 17.1). It supersedes the
Lab 9 board's recommendation of candidate 1 (docs/LAB9_SDN_GAP.md, its section 4: candidate 3,
"tool calling into the trace", estimated there at 4 to 5 agent-days with a new gateway path for
provider tool turns). Here it reuses item 3's check, record and egress, so it costs less.

**The same loop, the same limits.**
- The model asks for reads through the same pass-1 schema field (N21), one round, then pass 2.
- It is bounded by N24's limits: at most 3 reads a pass, one diagnosis at a time per device (a
  switch, by its dpid), at most 3 at once per network, and the command cap.
- The egress is N20's device state class, off by default, turned on per network.
- The controller is read through the network's connection (`modules/sdn/connections.py`) and its
  driver.

**The allowed operations: an allow-list of named controller operations, each mapped to a GET.**
"Exists" means the driver reads it today; "to build" means it needs code. Ryu's `ofctl_rest`
and `rest_topology` are the only built driver (`modules/sdn/drivers/ryu.py`). The other drivers
are declarations that refuse every call (`modules/sdn/drivers/declared.py`: ONOS, OpenDaylight,
ACI, NSX, and the rest). The Arista and HP switches due Thursday, and OVS on Linux, join through
Lab 9's multi-vendor drivers (its item 1). Each driver adds its own GET for each operation when
built, and an operation a driver does not declare is refused, naming the driver.

| Operation | Arguments (checked against the current topology) | Ryu endpoint | Method | Driver method | State |
|---|---|---|---|---|---|
| `topology` | none | `/v1.0/topology/switches`, `/v1.0/topology/links`, `/v1.0/topology/hosts`; `/stats/switches` | GET | `topology()`, `switches()`, `links()`, `hosts()` | **exists** |
| `switch_flows` | `dpid`: a switch the topology lists | `/stats/flow/<dpid>` | GET | `flows(dpid)` | **exists** |
| `port_stats` | `dpid`, and optionally `port`: a port that switch lists | `/stats/port/<dpid>` (one port is filtered from it in code) | GET | `port_stats(dpid)` | **exists** |
| `link_state` | `dpid` and `port`, or a link the topology lists | `/stats/portdesc/<dpid>` (a port's state and config flags), with `/v1.0/topology/links` | GET | `port_desc(dpid)`, new | **to build** (ofctl_rest offers it; the driver does not read it) |
| `path_trace` | two hosts the topology lists (MAC or address) | none of its own: Mercury's trace over the GETs above (each hop's flows, the links) | GET only, through the reads above | Lab 9's trace by dpid and its ports (docs/LAB9_SDN_GAP.md, item 3) | **to build, in Lab 9** (refused "not built" until then) |

**Only GET is ever sent; every write is refused in code, whatever the request:**
- **A read-only driver view.** The loop's executor holds a read-only view of the driver
  (`ReadOnlyDriver`, new). Its HTTP call refuses any method but GET before a byte leaves. Any
  path among the driver's write endpoints is refused too:
  - `FLOW_ADD`, `FLOW_MODIFY_STRICT` and `FLOW_DELETE_STRICT` (`/stats/flowentry/add`,
    `/stats/flowentry/modify_strict`, `/stats/flowentry/delete_strict`);
  - Ryu's other flow, meter and group writes (`/stats/flowentry/modify`, `/stats/flowentry/delete`,
    `/stats/flowentry/clear`, `/stats/meterentry/*`, `/stats/groupentry/*`, `/stats/portdesc/modify`).
- **Two checks, two layers:** the operation table names only reads, and the method check holds
  even if a write were added to the table by mistake.
- **No write method is reachable through the view:** the driver's `add_flow`,
  `modify_flow_strict`, `delete_flow_strict`, `add_meter`, `delete_meter` and `apply` are absent
  from it, not merely unused.
- **Arguments are checked against the current topology,** read from the controller at the
  request's time: a dpid the switch list holds, a port that switch lists, a host the hosts list
  holds. Anything else is refused, naming what was compared ("dpid 0000000000000009 is not a
  switch the controller lists: it lists 1 to 4").
- **Least privilege at the controller.** Ryu's REST has no accounts, so the method check is the
  boundary. A driver whose controller has roles signs in with a read-only role, the read-only
  device account's analogue (H28).

**Required tests** (the SDN read set's part, written first, red then green):

| Planted request | Expected |
|---|---|
| each write endpoint above, asked by name or by path | refused: a write endpoint; nothing sent (the test's controller fake records no request) |
| a write method (POST, PUT, DELETE) on a read path | refused: only GET is sent |
| `switch_flows` with a dpid the topology does not list | refused, naming the dpids it lists |
| `port_stats` with a port the switch does not list | refused, naming the switch's ports |
| `path_trace` with a host the controller does not list | refused, naming the hosts' count |
| `topology`, `switch_flows`, `port_stats`, `link_state` with listed arguments | pass; one GET each, answered from captured controller answers (`tests/fixtures/sdn/`) |

**The canary:** the method check is removed in a throwaway worktree (`scripts/nmas-control`),
and the write-refusal tests must fail, not crash. The run is kept with its output.

**The laptop install (Lab 9)** touches this part only in where the controller runs. Its facts
belong in docs/LAB9_SDN_GAP.md.

### 19.13 B4's evaluation plan (written before anything is built; the expectations frozen)

**What is compared:**
- **The baseline:** today's single pass (the Responder's `sdn_classify` call and the Analyst's
  call as each is live when B4's build starts, its prompt version named in the report).
- **The technique:** the read loop.
- Same model, same prompts otherwise. The only differences are the `reads` field, the read
  results and pass 2's instruction, which are the technique.

**The cases, their sizes read 2026-11-03** (`tests/fixtures/ai_cases/sdn_classify/`,
`tests/fixtures/blind_sets/sdn_classify/`):

| Set | Cases | Role |
|---|---|---|
| `recorded.json` | 12 | recorded |
| `recorded_from_blind.json` | 26 | recorded: blind cases whose misses the prompt's author read, moved by the operator's rule |
| `recorded_walk.json` | 8 | recorded (the Lab 8 walk) |
| `held_out.json` | 12 | held out (never tuned on) |
| `blind_cases.json` | 11 | **blind: all that is left of the spent blind set** |
| `blind_normal_cases.json` | 2 | normal traffic (N1, N2), scored with the blind set if its key holds them |

- **The blind set is spent apart from 11 cases** (PHASE8_PLAN 0.2's SDN row: 10 of 36 cases
  reliable; the 26 whose misses were read moved to the recorded set). A fair blind measure of
  B4 needs **a fresh blind set, which is the operator's capture session** (PHASE8_PLAN 0.3:
  about 20 scenarios drawn by a recorded seed, the key locked first, three sittings of about 50
  to 55 minutes).
- **That session must also capture each allowed operation's GET answer at detection time,** so
  the loop's reads replay.
- **On today's recorded and blind cases, a read is answered from the case's own captured pack.**
  The pack's `sdn` section holds the flow and port pieces. A read the pack did not capture
  (topology, link state, a path trace) answers "not captured at the case's time", and the
  report counts how often that happened.

**Frozen rules:**
- the blind keys stay locked (`blind_answer_key.md`, `blind_draw.json` with its sha256);
- no tuning on a blind case;
- a blind case whose failures are read beyond their categories moves to the recorded set, as
  before;
- each case's expectation is the one in its file now. None is edited for B4.

**The measures**, each reported for the baseline, the technique, the difference and its
uncertainty:

| Measure | How it is scored | Uncertainty |
|---|---|---|
| **Correct diagnosis** | the case passes its expectation (threat detected, type, source, severity, action), each case reliable at 10 of 10 runs, by `scripts/nmas-sdn-cases` | paired by case: the count of cases that flip each way, with McNemar's exact test; a 95% bootstrap interval for the difference in the share reliable |
| **False positives** | runs answering a threat on a benign case (C2305's class) | the same, on the benign cases |
| **The sources named** | the answer's citations against each case's `cites_any` | the mean share of cases, with its 95% bootstrap interval |
| **Tokens and cost per answer** | from the ledger (`data/ai_calls.jsonl`; `scripts/nmas-ai-ledger`), both passes counted | the mean and its 95% interval |
| **Time to an answer** | wall time from the request to the final answer, on the live path (a batch's latency is not the loop's): the recorded set at 1 run per case, both arms | the median and its interquartile range |

**The pass rule, decided now** (the operator): B4 "improves results" only if blind accuracy
rises without more false positives:
- **rises:** more blind cases are reliable with the loop than without it;
- **without more false positives:** no more benign-case runs are answered as a threat.

The interval is reported beside the result. With 11 to 13 blind cases one case is about 8
points, and the report says that power is low. A cost increase is reported, never hidden. The
recorded and held-out results are reported too, labelled as not blind.

**The spend, estimated before running** (the measured batch rate: $0.000326 a call,
PHASE8_PLAN 0.5, `sdn_classify`'s blind round of 2026-11-02):

| Run | Calls | Estimate |
|---|---|---|
| Baseline, all 71 cases (58 recorded and held out, 13 blind and normal) × 10 runs, batch | 710 | about $0.23 |
| The loop, the same × 10, batch: pass 1 at the measured rate, pass 2 at about 2.2 times (up to 3 × 4 KiB more input) | 710 × 2 | about $0.74 (at most about $1.16 if pass 2 costs 4 times) |
| Time to an answer: the recorded 58 × 1 run per arm, live path (about twice the batch price) | about 174 | about $0.12 |
| **Both runs** | | **about $1.1 (at most about $1.5)** |
| The fresh blind set later (about 20 cases × 10 runs, both arms) | about 600 | about $0.30 (at most $0.40) |

- **Against the budget:** PHASE8_PLAN 0.5's latest figure is **$161.19 left** (read on the host
  2026-11-03 ~06:5x UTC, `--since 2026-10-29 --budget 190`). No later reading is in the plan,
  so the ledger is read again and the figure recomputed before the run (that section's rule).
- **About $1.5 to $1.9 in all,** about 1% of what is left, inside the $15 day cap.

**The order** (the operator):
1. Lab 10 first.
2. Item 3 for the routers, within board H (H24 to H28).
3. Then the SDN read set (H29, H30).
4. Then B4's evaluation (H31).
