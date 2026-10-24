# Mercury as an intent-based networking platform (a design; not built)

**The operator's design task, 2026-10-13: doc only, no build. Registered FUTURE / After Phase 7
(C750), beside the credential store redesign (C733), which it depends on for masking.** Nothing
here changes Mercury until the operator's decisions in section 9 are made, phase by phase. **The
operator made them on 2026-10-13 (section 9, "Decided"); still no build before Phase 7 closes.**

An intent-based networking (IBN) platform does four things:

1. **Translate:** turn what the operator wants into network policy.
2. **Activate:** push that policy to the network automatically.
3. **Assure:** verify, continuously, that the network does what was intended.
4. **Respond:** detect a deviation and correct it without a person.

Mercury does part of each today. This document says what exists, what is missing, how each
function is built on what Mercury already trusts, and in what order. One principle governs
every section:

> **AI proposes; deterministic code decides.** Every AI output passes the same gates as a
> person's change: the intent schema, `nmas-config-check`, pre-change verification, a preview
> confirmed by hash, verify and rollback. AI never writes device configuration, never decides
> compliance, and never invents an action.

**The revision, confirmed by the operator 2026-10-13 (section 9, decision 9), observe mode
first:**
- AI may SELECT an action from a pre-approved catalog of deterministic remediations, within a
  policy's limits (its classes, its devices, never the management path), once observe mode
  has MEASURED its agreement with a person (at least 95% over at least 100 selections), under
  rate caps and the kill switch, with verify and rollback. Its self-reported confidence is
  logged for analysis only and never decides.
- It never invents an action or a parameter outside the catalog.
- This replaces "AI never remediates on its own", and supports the closed-loop pattern where
  AI is the decision-maker among pre-approved choices (section 3).

Until confirmed, the stricter rule stands.

**The golden state rule governs all autonomy (section 11; the operator's decision 12, refining
the catalog rule above):**
- **The current earned baseline is the golden state.**
- **Autonomous action is limited to two things:**
  1. converging devices back to the golden state;
  2. a short, explicit catalog of operational recovery actions that leave the golden state
     unchanged.

  This holds whoever takes the action: the deterministic engine, or AI choosing.
- **Anything that would change the golden state is a change,** and needs a person's approval.
  An approved, verified change earns the next baseline.

**Contents:**
1. Gap analysis
2. Assure
3. Respond
4. Activate
5. Translate
6. Phase order
7. The AI layer
8. The intent translation pipeline
9. The operator's decisions
10. AI engineering standards
11. The golden state rule: what autonomy may do
12. AI roles and permissions
13. Prompt-injection defence

## 1. Gap analysis, per function, against today's code

Surveyed 2026-10-13 at c40d9440. Three facts frame the rest:
- **Drift is measured against the golden, not intent.** Intent-Match runs only when a capture is
  committed and in the config check.
- **No check keeps a history:** each reader keeps its latest value.
- **The records database holds receipts only.**

### Translate: intent into policy

**Exists:**
- **Per-device intent:** `host_vars/<device>.yml`, the committed copy the only one a deploy
  reads (`modules/nsot/hostvars.py`: `read_committed`, `committed_at_head`, `complete_schema`).
  Content is refused when it holds a secret value or a character that does not print
  (`assert_no_secret_values`, `assert_printable`).
- **Templates:** one per platform with per-device bindings (`modules/nsot/templates_repo.py`).
  They render through Jinja2 (`roundtrip.render`), are compared section by section
  (`roundtrip.compare`), and become a frozen, deployable artifact only with zero unmodelled
  lines and an approved template (`render_artifact.RenderArtifact`).
- **Policies a person sets:**
  - the monitoring profile, one per network, its sections by platform and role, one
    inheritance function (`profile.effective`), proposed from the connectors and confirmed by
    hash (`profile_propose`);
  - the IP SLA suggestion policy (`ip_sla_policy`: `peers`, `gateway`, `upstream`), which only
    adds probes;
  - the rotation policy (`scheduled_rotation.set_policy`), resolved role, then site, then
    default;
  - DHCP's committed records (`dhcp_subnets`, `dhcp_reservations`, `dhcp_exclusions`,
    `dhcp_lifetimes`).
- **Intent above the device, derived, not stated:**
  - `neighbours.expected` derives each device's adjacencies from the whole fleet's intent:
    OSPF by shared subnet, BGP by named neighbour.
  - `topology_expected.declare` is a person's "expected island", kept in a JSON store, not the
    repository.
- **The config check** (`modules/nsot/config_check.py`, `CHECKS`) runs yaml, golden,
  templates, render, intent-match, lint and secrets. It runs from `scripts/nmas-config-check`,
  in the config repository's GitHub Action, and as `repo.commit()`'s pre-commit gate.
  Intent-match is a note there, never a failure.

**Missing:**
- **No stated intent at network or service level** ("A reaches B", "every site has two
  uplinks", segmentation).
- **No intent schema** beyond `host_vars`' keys and the profile's sections.
- **No conflict detection** between intents (each device is checked alone).
- **Expected islands outside git.**

### Activate: policy onto the network

**Exists:**
- **The pipeline** (`modules/pipeline.py`, `_STAGE_TABLE`): eleven entries, the nine numbered
  stages plus save to startup (8.2) and save the golden (8.5):
  - netbox_query → template_render → ci_gate (the last stage before any session);
  - pre_snapshot → config_diff → deploy → post_snapshot → verify;
  - save_startup → save_golden → audit_log.

  Stages 6 to 8 roll back on failure (`_stage_rollback`, `_rollback_readback`).
- **Deploy** (`modules/nsot/deploy.py`): re-rendered with secrets in memory (`render_for_deploy`),
  merge-only output (`merge_commands`), a batch with a circuit breaker (`plan_batch`,
  `run_batch`, `CircuitBreaker`). A batch runs as a background job (`deploy_job.start`).
- **One preview contract** confirmed by hash (`preview_confirm`); scoped profile applies
  (`profile_apply.scoped`).
- **Verify** scaled to what was sent (`verify_scope.classify`, settle windows in
  `convergence`), and expected effects judged apart from failures (`expected_effects.judge`).
- **Receipts** per device (`receipts`); one operation per device (`device_ops.acquire`).
- **No automatic deploy of intent.** The only unattended writer is scheduled rotation:
  - **Its authority:** a policy set only by a person verified by the access proxy
    (`set_policy` refuses otherwise). It is stamped with `set_by`, `set_at` and `verified`, and
    recorded in the credential changes log.
  - **Its timer** ticks every 5 minutes and runs only with the policy on, inside its window,
    and outside the backup window (checked at the run's start and before each device).
  - **Its rails:**
    - at most one completed run per policy in 24 hours;
    - a cross-process lock;
    - one device at a time, capped by `max_per_run`;
    - a device skipped when held, restarting, off-intent (its golden is not its intent's
      render) or with no plan;
    - stop at the first failure, which raises a critical Needs attention row and halts until a
      clean run or a person's rotation of the failed device.
  - **Its record:** each rotation commits with `Actor:` the policy's setter,
    `actor_kind="policy"`, `via="scheduled rotation (policy set by …)"` and
    `Source: scheduled_rotation`.

**Missing:**
- **No automatic or windowed deploy** of an intent change.
- **No pre-change simulation:** `blast_radius` covers reachability during a restart only.
- **No transactional multi-device change:** a batch is sequential, with its breaker.

### Assure: verify continuously

**Exists:**
- **Drift** (`modules/drift_check.py`, `DriftChecker`): every 4 hours it reads the running
  configuration over SSH, diffs it against the GOLDEN, and queues an approval. Its last run only
  is kept.
- **Intent-Match** (`modules/nsot/intent_match.py`): match, differs or unknown. Not scheduled.
- **Earned baselines** (`golden_state.judge_device`): the declared protocols are up.
- **Adjacencies** (`modules/readers/adjacencies.py`): every 60 s, intent's expected neighbours
  against Prometheus (OSPF, OSPFv3, BGP) and the RIP reader. A failure must persist across
  reads before it is a row.
- **IP SLA:** results scraped by Prometheus from targets derived from goldens
  (`prometheus_targets`); Coverage checks the probes' presence. No Mercury reader judges their
  results; Grafana's alerts do.
- **Coverage** (`monitoring_coverage`, `readers/coverage_reporting`): configured, from the
  golden, and reporting, from arrival times.
- **Restarts** (`restarts`, `readers/restarts`): a falling `sysUpTime`, planned or not.
- **The reader framework** (`modules/reader_job.py`) runs 22 readers, each storing ONE
  overwritten JSON value:
  - adjacencies, app_pushed, baseline_usability, ci_verdict;
  - coverage_reporting, credential_health, dhcp;
  - grafana_alerts, grafana_dashboards, integration_health, job_health;
  - logs_summary, logs_tail;
  - netbox_secrets, platform_facts, reachability, records_check, remote_publication;
  - restarts, rip, topology_graph, ztp_discovery.
- **Needs attention** (`modules/attention.py`, `SOURCES`): 25 sources.
- **The records database** (`records_db`) stores receipts only; it is off until configured.

**Missing:**
- **No per-intent compliance history:** every store keeps the latest value.
- **No continuous Intent-Match:** drift compares with the golden. Rotation's `off_intent` is
  the only periodic intent comparison.
- **No service or path verification:** reachability is a per-device probe.
- **No Mercury-side judgement of IP SLA results.**

**Proposed for Stage 9** (the operator, 2026-10-15; nothing built): incident evidence export,
ISP circuit verification, bandwidth by application and user, scans, traffic analysis to
findings, a management-access profile per device, and the common asks (ranked), each with its
dependencies (E18, C764 packs, the role model E5) and its Phase 8 hook, in
[ASSURE_FEATURES](ASSURE_FEATURES.md) (C799 to C801, C803 to C806).

### Respond: correct deviations

**Exists:**
- **Every Needs attention row names an action for a person** (`attention.row` refuses a row
  without one).
- **Acknowledgements** with a reason and who (`acknowledgements.record`).
- **Automatic actions, three only:** a deploy's own rollback (stages 6 to 8); scheduled
  rotation; drift, which only queues an approval.
- **The removed AI family:**
  - The background agent (`agent_runner.py`, off until Stage 8) drained events into AI tasks
    with SSH, golden, compliance and variable tools, ran drift detection and trap analysis with
    flap suppression, and paused while a person was active.
  - The assistant (`ai_assistant.py`; Anthropic, Groq, Ollama) kept its own "compliance
    policy" file: the only rule-based compliance concept today, and it was the AI's.

**Missing:**
- **No policy-driven remediation** of drift or intent violations.
- **No correlation or root cause across sources,** beyond one cause folding several rows
  (`_fold_one_cause`).

### Telemetry, measured

- **No `severity` label in Loki.** Severity is the digit in each line's mnemonic, filtered at
  query time (`device_logs.LOGQL_FIELDS`, `mnemonic_severity`). Loki's labels are `job`,
  `host`, `device` (from a `loki.process` regex, C722) and `unit`.
- **SNMP traps DO reach Loki**, as job `loki.source.journal.snmptrapd`: Alloy reads
  snmptrapd's journal (`scripts/host-steps/c722-device-label.sh`). Read over 7 and 30 days;
  none in the last 6 hours. A query must match it as `job=~".*snmptrapd"`; Alloy's own job
  name replaces the one the config sets.
- **Mercury's own trap listener** (`snmp_collector`, UDP 1162, a 200-entry ring in
  `snmp_traps.json`) does not ship to Loki, and goes with the AI family.
- **Batfish** is named only in docs (`NSOT_INDUSTRY_ALIGNMENT.md`, `NSOT_PLAN.md`,
  `NSOT_TOPOLOGY_RESEARCH.md`, `PUBLIC_RELEASE.md`), never in code.

## 2. Assure, the first phase: intent statements proven by measured state

**The model.** An *intent statement* is one thing the network must be true of, said in words
and in a structured form, with a *verifier* that proves or disproves it from MEASURED state,
never from configuration. A configured OSPF process proves nothing; a FULL adjacency read from
the device does.

| Part | What it is | Example |
|---|---|---|
| Statement | an id, its words, its scope (devices, a role, a site, the network), and where it comes from (device intent, a profile section, a network-level intent) | `ospf-neighbours`: "every router peers OSPF with the neighbours its intent names" |
| Verifier | a function over stored readings (`reader_job` values, Prometheus, Loki), returning holds, does not hold, or unknown, with its evidence | the adjacencies reader's expected vs measured neighbours (`modules/readers/adjacencies.py`) |
| Status | per statement and scope: holds, violated (since when, evidence), unknown (which reading is missing, never "holds") | "violated on r3 since 14:02 UTC: Gi2's neighbour 192.0.2.14 not FULL on two reads" |
| History | each change of status, with its evidence and the reading's time | the compliance timeline |

Today's checks become the first verifiers rather than new code:
- **Intent-Match:** intent renders to the golden.
- **Drift:** the golden is what is running.
- **Adjacencies:** OSPF, BGP, RIP and RIPng, as intent implies them.
- **IP SLA:** paths measured.
- **Coverage:** monitoring configured and reporting.
- **Reachability:** each device answers.

Each already produces "what was expected, what was measured, when"; the model gives them one
shape, one status vocabulary and one history.

**Status and history need the records database.** A verifier's status changes are records, and
there will be many: every statement, on every device, every interval. JSON stores (today's
`reader_job` files) keep the last good value, not a history. The history belongs in Mercury's
records database (Phase 4, `docs/NSOT_PHASE4_RECORDS_POSTGRES.md`; E18), so **Assure's history
waits on E18.** Before E18, Assure can show the current status and say that history is not
kept yet.

**Needs attention, driven by failed verifiers.**
- **One row per violated statement**, naming the scope, the evidence, the action (the
  device's tab, the intent, or the Respond class that would fix it) and how it clears (when
  the verifier holds again).
- **No row for an unknown status:** an unknown is its reading's own row, since the stale or
  unreadable source is what to fix.
- **The existing sources fold in** rather than duplicate: drift, adjacencies, Coverage, IP SLA.

**A Compliance view (a board first).** The screen answers "is the network doing what it
should?":
- the count of statements holding, violated and unknown, by area;
- the violated ones first, grouped by statement, then by device;
- each statement's evidence on expand, and its history once E18 is built;
- built for large fleets: summary first, grouped, filtered, never one long list.

**Telemetry gaps Assure needs closed** (measured 2026-10-13 unless said):
- **Traps reach Loki without a device-indexed parse.** They arrive as
  `loki.source.journal.snmptrapd`, whose job name differs from the one the Alloy config sets.
  Their `device` label waits for the next trap (C722). A trap verifier needs a stable label and
  the trap's OID parsed.
- **Loki has no `severity` label.** Severity is parsed from the line at query time, so "errors
  and worse" is a line filter, not an index lookup. A label set at ingest (Alloy) makes it
  cheap.
- **Interface counters** come from SNMP polling at the exporter's interval, so an error burst
  shorter than the interval is averaged away.
- **IP SLA results** are read only for the probes intent declares.
- **No assurance reads the data plane beyond IP SLA:** no synthetic traffic and no path checks
  but the path trace, which runs on request.
- **No verifier for the management path itself** (the tool's own reachability is the
  reachability reader).

## 3. Respond: remediation by policy, modelled on scheduled rotation

**Authority.** Scheduled rotation is the closed loop Mercury already runs, and its shape is
Respond's:
- **Its authority is a policy:** a verified person set it, and its record says who and when.
- **Each action is recorded** like a manual one, with `Source:` naming the policy and
  `Actor-Verified:` naming how the authority was established.
- **Its rails:** one device at a time, stop at the first failure, inside windows, and a halt
  only a person lifts.

Respond replaces **per-change confirmation** with **per-policy authority**:
- A person confirms a remediation policy once, previewed by hash like any operation: its
  class, its scope, its rails.
- Within that policy, each fix runs without a person.
- The policy's record is the authority every fix's commit names.

This is a decision for the operator (section 9): Mercury today never changes a device without
a person's confirm except for rotation.

**A deviation taxonomy and remediation classes.** A deviation is a verifier that does not hold.
Its class says what may be done about it:

Decided by the operator, 2026-10-13 (decision 2): **management-plane configuration only** may
ever auto-fix (logging hosts, SNMP, NTP, IP SLA probes); never routing, interface state, ACLs,
AAA or credentials, or the management path (in this lab, s3 and the path it carries).

| Class | Examples | May ever auto-fix? |
|---|---|---|
| Monitoring lines missing | a logging host, an SNMP community or view, an NTP server absent from the running config | yes, once observe mode measures it safe (decision 2) |
| Other monitoring template lines | the heartbeat applet, any other template line that is not a logging host, SNMP or NTP | no: not in decision 2's list; a person |
| A probe missing | an IP SLA operation intent declares, absent | yes, as above |
| Drift that adds | lines on the device that intent does not hold (a hand change) | no: a person decides whether to capture it as intent or remove it |
| Drift that removes | intent's lines missing from the device | only for classes already allowed (above); never for the rest |
| Routing | an adjacency down, a route missing, BGP not established | never: always a person |
| Interface state | a port down, a description changed, a VLAN | never |
| ACLs | an access list's lines, an interface's access-group | never |
| AAA and credentials | AAA lines, accounts, a rotation's failure | never (rotation has its own halt) |
| The management path | anything on the path Mercury reaches devices by (the management interface, vty, credentials, the route to the manager), and anything on the switch that carries it (s3 in this lab) | never |

**Observe mode first, for every class.**
- A policy starts in observe mode. It records each fix it *would have made* ("would have fixed
  r3: logging host missing since 14:02"), and a person marks each one right or wrong.
- Its **false-positive rate is measured** over a stated period; the class is enabled only when
  it is below the operator's threshold.
- The rate and its count stay on the policy's page.

**The rails, every one required:**
- **Grace period:** a deviation must persist across N readings over at least T minutes before
  it is fixed, so a person mid-change is never overridden. A device held by any operation is
  skipped.
- **One device at a time**, and **stop at the first failure**, which halts the policy until a
  person lifts it (rotation's halt).
- **Rate caps:** at most K fixes an hour per policy and per network. A cap reached halts the
  policy and raises a Needs attention row.
- **Change windows:** fixes only inside the policy's windows, outside the backup window.
- **A global kill switch:** one control, on Needs attention and Settings, stops every policy at
  once; recorded with who and why.
- **Verify and roll back** exactly as a person's deploy does; a rolled-back fix halts its
  policy.
- **Full audit:** each fix is a commit and a receipt naming the policy, the deviation's
  evidence, the program sent, verify's result, and the policy's authority.

**AI selecting from a catalog (the proposed revision; decision 9).**
- **The catalog:** a fixed list of deterministic remediations, each a named operation Mercury
  already runs, with typed parameters bounded by policy. Examples: "deploy the monitoring
  profile's missing section to device D"; "commit the suggested IP SLA probe for D"; "re-run
  capture on D".
- **The AI's role:** given a deviation's evidence, it returns the catalog entry and parameters
  it would choose, with `confidence` and its evidence references (section 10). That is all it
  returns.
- **Deterministic code decides whether the choice may run:**
  - the entry is in the catalog;
  - every parameter is inside the policy's limits (its classes, its devices, never the
    management path);
  - the policy's AI tier is enabled, which it is only after observe mode measured at least
    95% agreement with a person over at least 100 selections (the operator, 2026-10-13: no
    self-reported confidence gate; `confidence` is logged for analysis and never decides);
  - the rails above hold (grace, hold, rate caps, windows, kill switch).
- **Anything else goes to a person** as a proposal.
- **The run is the catalog operation's own,** with its preview computed, its verify and its
  rollback, and it is recorded naming the AI's choice and the policy's authority.
- **Observe mode applies here too:** the AI's selections are logged as "would have chosen",
  beside the deterministic rule's choice where one exists, and the rate at which a person agrees
  is measured before the tier is enabled.

**Risks, and what answers each:**
- **Legitimate manual or emergency drift:** the grace period and the device hold; drift that
  adds is never auto-fixed; a person can mark a device "in maintenance" (an acknowledgement
  with an end time) so no policy touches it.
- **False positives:** observe mode and the measured rate; a verifier that returns unknown
  never triggers a fix.
- **Flapping loops:** the same deviation fixed twice within a window halts its policy; the rate
  caps catch the rest.
- **Blast radius:** one device at a time, stop on failure, never the management path, and the
  kill switch.

## 4. Activate: commit-triggered deploys inside change windows

Today a deploy is a person's: previewed, confirmed by hash, verified, rolled back on failure,
recorded. Automatic Activate keeps every one of those stages and changes who confirms:
- **Trigger:** a commit to a device's intent (or a profile, or a template binding) that passes
  `nmas-config-check` and the pipeline's own gates, under an activation policy that covers it.
- **Canary, then fleet:** the policy names a canary device (or a role's first device). The
  canary deploys, is verified, and soaks for a stated time with its verifiers holding; then the
  rest go one at a time, stopping at the first failure.
- **Built on rotation's scheduler:** its windows, its one-device-at-a-time loop, its halt, its
  recording (`Source:` the policy, `Actor-Verified:` how its authority was set).
- **What it never does:** a commit that changes the management path, credentials or routing
  waits for a person whatever the policy says; a commit made by Respond does not trigger
  Activate (one loop at a time).

## 5. Translate: a network-level intent model, compiled deterministically

Today intent is per device: `host_vars/<device>.yml`, rendered by Jinja2 templates, with
profiles that inherit. Translate adds a level above it:
- **Network intent:** services and outcomes, said once for the network. Examples:
  - "VLAN 30's hosts reach the internet over IPv6 only."
  - "Every router peers OSPF with its neighbours on its core links."
  - "Every device sends syslog at notice and worse to the collector."
  - "No device answers SNMP v2c."
- **A compiler, deterministic and testable:** network intent plus NetBox's facts (roles, sites,
  interfaces, addresses) compile into device intent, the same `host_vars` a person edits today.
  The device-level diff is the compiler's output, previewed like any intent change.
- **Pre-change verification:** before anything is committed, the compiled change is checked:
  - **Batfish**, on the candidate configurations (reachability, routing, ACL effects);
  - **Mercury's own IOS checks**, the quirks its parsers and `nmas-config-check` already know.
  A failed check refuses the change by name.
- **Each network intent statement carries its verifier** (section 2), so Translate and Assure
  meet: what is stated is what is proven.

**The policy-conflict layer, its own validation step before activation.**
- **Precedence is deterministic:** a more specific scope beats a broader one (a device over a
  role, a site, the network); an explicit deny or allow is never inferred; equal scope and
  equal specificity is a conflict, never an order.
- **Conflict detection** compiles every intent that touches the same object and refuses the
  change when two disagree. Example: "block video" and "allow video for the AV team" on the AV
  team's ports; the rule above says the narrower scope wins only when the operator has stated
  that order.
- **A conflict is shown with the intent it clashes with:** both statements, who committed each,
  the objects they share. It is never resolved silently. The person resolves it by narrowing
  one intent or stating an explicit precedence, itself an intent that is reviewed and recorded.

**Intent authorisation: the intent interface is a northbound API.**
- **Per-scope permissions:** which person (or service identity) may submit which KIND of intent
  (monitoring, routing, access policy), for which devices, roles and sites. They are enforced in
  code on top of Mercury's `may` and the access proxy's verified identity. A refusal names the
  person, the intent's kind, its scope and the permission it lacked.
- **One gate for every entry point:** the same permission check runs whether the intent comes
  from the editor, the API, the natural-language pipeline (section 8) or, later, voice.
- **The prompt-injection threat model covers the operator's own sentence** as well as retrieved
  data (section 8): a sentence asking for more than its author may submit is refused by the
  permission check, whatever the model returns.

## 6. Phase order

Each phase depends on the one before it. **Assure → Respond in observe mode → Respond per
class → automatic Activate → Translate upward.**

*Amended 2026-10-24 (the operator, PHASE8_PLAN 15.2): phase 3 below, Respond per class, and AI
catalog selection reaching execution leave Phase 8 for Phase 9, the closed loop, built when the
first class or catalog entry meets its ruled bar on observed evidence. Its prerequisites, which
an SDN controller supplies and CLI does not: a revert timer on every autonomous change (native
where measured, Mercury-scheduled otherwise), a defined inverse (Mode B's measured removal),
partial-apply handling through `pipeline._stage_rollback`, and cascade limits.*

| Phase | Builds | GUI (boards first) | Register | Tests | Host steps |
|---|---|---|---|---|---|
| 1. Assure | the statement and verifier model; today's checks as the first verifiers; status now, history after E18; Needs attention from failed verifiers | the Compliance view; a statement's evidence; Needs attention's verifier rows | the telemetry gaps (traps, severity); the Compliance view | every verifier shown able to fail on a planted reading; unknown never reads as holds | Loki's `severity` label and a stable trap label (Alloy) |
| 2. Respond, observe | remediation policies, preview by hash, observe mode, "would have fixed" records, right or wrong marks, the false-positive rate | a policy's page; the observe log; marking right or wrong | each class's measured rate | a policy that would fix without the grace period, or on the management path, refused | none |
| 3. Respond, per class | the auto-fix loop on rotation's scheduler; the rails; the kill switch | the kill switch; a policy's runs on the one stepper | each enabled class, with its measured rate | each rail shown able to fail: grace, hold, cap, window, flap, kill | none |
| 4. Activate | activation policies, canary then fleet, soak | a policy's page; a run on the one stepper | one per policy | canary failure stops the fleet; a management-path commit waits for a person | none |
| 5. Translate | the network intent model, the compiler, pre-change verification, verifiers per statement | network intent's editor; the compiled diff's preview | the model's scope; Batfish's install | the compiler's round trip on the lab's real intent; a failed Batfish check refuses | Batfish (a container), the operator's |

## 7. The AI layer

AI makes Mercury easier to use: faster to understand, faster to diagnose. It is never what
decides. Every AI output is a proposal that passes the gates a person's would.

### Gaps AI can close, per function

| Function | What AI does | What decides |
|---|---|---|
| Translate | natural language → the structured intent model (section 8); explaining any intent in words; inferring higher-level intent from configs ("these nine routers peer OSPF on every core link"); drafting templates for a new platform | the schema, the compiler, validation, the person's confirm; a template draft counts only when its round trip passes |
| Activate | change summaries ("this commit adds a logging host on 9 devices"); proposals for a drain or a no-reload revert, through preview and verify | preview by hash and verify |
| Assure | natural-language questions → PromQL or LogQL, which History › Query's builder (E3, F3) reads back before it runs; correlation ("3 alerts began together: a likely common cause"); log summaries; verifier drafts for review | the builder's read-back and its bounds; a person accepts a verifier draft, and it is shown able to fail |
| Respond | a likely root cause and proposed fixes for a novel problem, approved by a person; a suggested remediation class; an incident record; a proposed new pipeline check whenever a problem slipped through | a person; the automatic tier only by selecting from the catalog, if decision 9 is confirmed |

### Gaps that need deterministic redesign, not AI

The intent model and its compiler; pre-change verification; the activation engine; the
verifier model and compliance history; the remediation policy engine and its taxonomy. Each
must be testable, reproducible and explainable without a model.

### The AI layer's own design

- **A multi-provider gateway:** one module through which every model call goes. It has a
  per-network switch (off by default) and cost caps per network and per day (a cap reached
  refuses the next call, by name). Which providers is the operator's (section 9). **A
  built-in local model ships with Mercury** (the operator, 2026-10-14), so AI works out of the
  box, offline and air-gapped, beside the paid providers. It runs behind the same gateway and
  rules (the subsection below; docs/PHASE8_PLAN.md section 10). *Amended 2026-10-16 (the
  operator, offline-first; docs/PHASE8_PLAN.md section 12.1):* every AI feature must work fully
  on the local profile with no network. A paid provider is an optional profile that may improve
  a result, and never the core path's dependency.
- **Masking before every prompt:** the prompt is masked by C733's keyed-digest index (every
  secret Mercury holds, matched by digest) and by `redact_text`'s positional rules. C745's
  unknown credential shapes are closed first.
- **Every prompt and response recorded in History:** who asked, the network, the masked
  prompt, the model and its version, the raw response, the cost. The record is the only way to
  reproduce an answer.
- **AI acts only through Mercury's existing operations:**
  - reads through the read-only allowlist, as a person's Ask the device;
  - changes as proposals through preview and confirm;
  - exposed as an MCP server, so any model reaches Mercury the same bounded way.
- **Observe-mode evaluation before trust:** each AI feature runs alongside the deterministic
  path, its answers marked right or wrong, its accuracy measured and shown, before it is
  offered by default.

### The built-in local model and the multi-model rule (the operator, 2026-10-14)

**DECIDED:**
- **Model origin: US-only.** The candidates are gpt-oss-20b (OpenAI), Gemma 4 26B MoE and E4B
  (Google), and Granite 4.0-H-Tiny and H-Small (IBM). No other origin is offered, and there is
  no setting to add one.
- **One definition of every tool and one prompt structure for every model.**
  - Each tool is one JSON Schema with its role binding (section 12), in one registry.
  - The prompt structure is section 10's.
  - **Adapters exist per API shape, never per model:** Anthropic Messages, and
    OpenAI-compatible (OpenAI, Gemini's compatible endpoint, llama.cpp).
  - Per-model differences live in a profile, which is data: the adapter, the context budget,
    strict-schema support, parallel calls, the maximum tools per request, reasoning settings,
    cost, origin.
  - No per-model prompt forks: a model that fails the eval with the shared prompt gets fewer
    features, not its own prompt.
  - No third-party multi-LLM abstraction library: both adapters are Mercury's own, and
    auditable.
  - Only models that passed the eval are offered.

**PROPOSED, pending the operator:**
- **Engine:** llama.cpp's `llama-server`, as its own service, bound to 127.0.0.1, with no
  egress. It is served through the OpenAI-compatible adapter as "Local (built-in)". *Note,
  2026-10-16:* the operator's offline-first rule names `llama-server` as the local profile. That
  reading decides the engine, and is the operator's to confirm (docs/PHASE8_PLAN.md section 12.5,
  gap 10). The items below stay proposed.
- **Delivery:**
  - never in the repository or an image;
  - the first-run wizard downloads a pinned file (sha256, and `model.sig` for Granite), or
    imports an operator-supplied one;
  - offline after that.
- **Tiers by a hardware check:** free RAM under the running stack, CPU features and a 30-second
  speed test.
  - A large tier (gpt-oss-20b or Gemma 4 26B MoE) where RAM allows.
  - A small tier (Gemma 4 E4B or Granite 4.0-H-Tiny) on low RAM.
  - Otherwise "AI off" with the reason shown, never a weaker model.
- **Reliability:**
  - JSON-schema constrained decoding for every tool call;
  - tools preselected per request, up to the profile's maximum, from the role's tools only;
  - a context budget from the profile.
- **Isolation:**
  - CPU and memory caps, one request at a time, unloaded when idle;
  - it never starves Loki, Prometheus or Mercury.
- **Release gate per model and version:** the task evaluation and the red-team set (section
  13). Features turn on per model only where it passed, and the eval picks the local default.

**The threat model is unchanged.** A local model is as untrusted as a hosted one (section 13).
Its tools are the same role-bound tools, and it never changes permissions. Running locally
removes one exfiltration path (no provider sees the prompt), but masking before every prompt
still applies: History records the prompt, and a profile may later point at a hosted endpoint.

### What of the removed AI family is worth reusing

The AI family (`modules/ai_assistant.py`, 4,583 lines; `modules/agent_runner.py`; the stores
archived by D15) is removed at 7.8.

**Worth carrying forward:**
- the provider configuration's shape (several Anthropic models, chosen per use);
- the usage log's per-turn cost (`modules/ai_usage_log.py`), which becomes the gateway's cost
  record;
- the tool list as an inventory of what a model needed to ask, rebuilt as MCP tools over
  today's read paths (the device's intent and golden, NetBox, the readers' stored values);
- the approval queue's idea of a proposal waiting for a person (`modules/approval_queue.py`),
  rebuilt on preview and confirm.

**Not worth reusing:**
- tools that run commands or reach devices outside the read-only allowlist and the device
  holds (`execute_command*`, `backup_device_config`, `snmp_poll`);
- the in-app trap and NetFlow collectors;
- its own drift and compliance checks (Mercury's are the verifiers now);
- its per-network knowledge-base files (the history and the records are the knowledge);
- its chat UI on today's pages.

### Where AI lands in the phase order

- **Early in Assure:** natural-language query through E3/F3's read-back, and correlation.
- **Middle:** Respond's proposals for a person. In the automatic tier only if decision 9 is
  confirmed, and then only by selecting from the catalog (section 3), after its own observe
  mode.
- **Late:** Translate, once the intent model, compiler and validation exist for it to propose
  into.

## 8. The intent translation pipeline, mapped to Mercury

| Step | What happens | Exists today | New |
|---|---|---|---|
| 1. Input | plain-language intent, from an authenticated person; when ambiguous, code asks a question and never guesses (step 4; PHASE8_PLAN 11.2). A later input layer: voice, speech-to-text in front of the same pipeline, from an authenticated session, with a mandatory spoken and written read-back. **Voice may query and request; it never approves** (decided 2026-10-15, PHASE8_PLAN 11.6): approval is only the GUI's confirm by hash, and the spoken read-back informs, it does not approve (the threat: speaker spoofing, section 13 item 9). Low priority; the design leaves room | Ask the device's typed reads, a person's reason fields | the request card, the clarifying turn, voice later |
| 2. Prompt construction (Python) | the intent model's schema; the affected devices' current intent from Git; NetBox's facts (roles, sites, interfaces, addresses); platform capabilities; 2 or 3 REAL input → output examples drawn from the config repository's history (a commit's intent change and the words that asked for it; 1 or 2 ending in the error contract, decided 2026-10-15, PHASE8_PLAN 11.4); **the person's text and every retrieved block normalised first** (NFKC; zero-width, bidirectional-override and control characters stripped; a length cap per block; each removal in the audit log; decided 2026-10-15, PHASE8_PLAN 11.7), then masked; **the versions of the intent and NetBox data used recorded** (decided 2026-10-15, PHASE8_PLAN 11.10); only the context the request needs, sized by the feature's measured minimum (section 10) | committed intent readers (`hostvars.read_committed`), NetBox client, `redact_text` | the normaliser, the context selector, the example selector, C733's index |
| 3. LLM translation | constrained to the intent model's JSON schema (structured output), with an explicit error contract: `{"error": "could not parse"}` and `{"error": "ambiguous", "clarification_needed": "…"}`, each surfaced to the operator in their own words, never retried silently. Every field marked `stated` (with the request's words it came from) or `inferred` (decided 2026-10-15, PHASE8_PLAN 11.3). It outputs intent, never device configuration or Jinja (template drafting is a separate workflow gated by round trip) | none | the gateway, the schema, the error shapes, field provenance |
| 4. Validation | the schema; **intent authorisation** (the person may submit this kind of intent for these devices and sites; section 5); semantics (references exist in NetBox, guardrails such as never the management path or s3; **every reference resolved by code against NetBox and intent, and zero or several matches make code ask the clarifying question whatever the model returned**: the model's ambiguity flag is additive, never the safeguard; decided 2026-10-15, PHASE8_PLAN 11.2); **the policy-conflict layer** (precedence, conflicts shown with the intent they clash with; section 5); `nmas-config-check`; pre-change simulation (Batfish); the device-level diff and blast radius. On failure one bounded retry with the error fed back, then back to the operator | `nmas-config-check`, the render, `deploy.classify_diff`, the management-path rules, `may` | authorisation per scope, the conflict layer, semantic checks, Batfish, the retry |
| 5. Confirmation | the operator's words; a plain-language read-back GENERATED FROM THE STRUCTURED OUTPUT (not the model's own description), **the inferred fields highlighted** (PHASE8_PLAN 11.3); the intent diff; the exact device commands; validation results; the risk. Approved by hash: exactly that artifact runs (the model is not deterministic). **Confirm by hash pins the artifact, not its facts:** if the intent or NetBox data changed since the translation, step 4 re-runs before anything applies, and a failure refuses naming both versions (decided 2026-10-15, PHASE8_PLAN 11.10) | preview and confirm by hash, the program masked | the read-back generator, the freshness check |
| 6. Execution | commit the intent to the config repository (its pipeline and GitHub Actions run on it), then deploy, verify, roll back | `save_host_vars`, the pipeline, the config repository's workflow | none |
| 7. Verification that the intent holds | Assure's verifiers prove the network now behaves as stated; roll back if not | verify (configuration) | the statement's verifier (behaviour) |
| 8. Logging | one id linking the words, the normalisation's removals, the masked prompt, the model and version, the versions of the intent and NetBox data used, the raw response, the structured output, validation's results (and whether it re-ran at confirm), the approver, the deploy receipt, the verification; the only way to reproduce a translation | receipts, commits | the translation record (on E18's database) |

**Threat model: prompt injection.**
- **Untrusted data:** interface descriptions, log lines, NetBox fields and device output are
  untrusted. They reach the model only as data, delimited and masked, never as instructions.
- **No tools that change anything:** the model's tools are read-only. Its output counts only
  after validation, and validation never trusts the model's own claims: it recomputes every
  reference, diff and risk.
- **Containment:** a request whose context holds instruction-shaped text is still validated
  the same way. The worst an injection can do is propose something validation refuses or a
  person declines.
- **The operator's own sentence is untrusted too:** it may ask for more than its author may
  submit, or carry text pasted from elsewhere. Intent authorisation (section 5) is checked on
  the structured output, so the model's compliance with an injected instruction gains nothing.
- **Hidden text:** zero-width, bidirectional-override, tag and control characters in the
  sentence or the retrieved data are stripped before any prompt, each removal audited
  (step 2; PHASE8_PLAN 11.7). It removes what a person reading the text cannot see; security
  still rests on validation, as section 13's item 5 says of prompt hygiene.
- **A spoofed voice** may ask, never approve (step 1; section 13 item 9).

**Validation in the pipeline, mapped to Mercury.** The pattern is: the model's output becomes a
reviewed git change; the change passes syntax, semantics and behaviour checks; an approval gate;
deploy; rollback by revert; and a faster pre-approved path for urgent actions.

| Stage of the pattern | Mercury today | New |
|---|---|---|
| LLM output → a reviewed git change | an intent change is a commit to the config repository (`save_host_vars`, `repo.commit`) with `Actor:`, `Actor-Verified:` and `Source:` | the translation record's id in the commit's trailers |
| Syntax checks | the intent schema; `nmas-config-check`'s yaml, templates and render checks; `assert_printable` | the intent model's JSON schema |
| Semantics checks | `nmas-config-check`'s intent-match, lint and secrets checks; NetBox references | the conflict layer; authorisation per scope |
| Behaviour checks | verify after deploy; the adjacencies and other readers | Batfish before deploy; the statement's verifier after |
| The approval gate | preview and confirm by hash as a verified person; the config repository's GitHub Action | none |
| Deploy | the pipeline, merge-only, with stages 6 to 8 rolled back on failure | Activate's canary then fleet |
| Rollback by revert | Revert (`intent_ops.revert_apply`): an intent commit reverted, then deployed | an automatic revert when a statement's verifier fails after deploy |
| The faster pre-approved path for urgent actions | scheduled rotation: a policy's authority, no per-change confirm | Respond's catalog (section 3), under a policy and its rails |

## 9. The operator's decisions, before any build

1. **Per-policy authority** replacing per-change confirmation, for Respond and for Activate:
   yes or no, and for which networks.
2. **Which remediation classes may ever auto-fix** (section 3's table is a proposal), and the
   false-positive threshold and observe period a class must pass.
3. **The rails' numbers:** grace period, rate caps, windows, the kill switch's place.
4. **AI providers:** which, whether a local model is required (air-gapped installs), the
   per-network default (proposed: off), and the cost caps.
5. **The intent model's scope for Translate's first phase** (proposed: monitoring and one
   routing statement, e.g. OSPF neighbours on core links).
6. **Batfish:** whether to adopt it for pre-change verification (a new third-party package and
   container, licensed Apache-2.0).
7. **The telemetry gaps:** Loki's `severity` label set at ingest, and a stable trap label with
   the trap's OID parsed.
8. **Where the history lives:** confirm that Assure's history waits on E18 (the records
   database) rather than a second store.
9. **The Respond rule's revision:** whether AI may SELECT from a pre-approved catalog of
   deterministic remediations within a policy's limits (the principle's proposed revision,
   section 3). Until confirmed, AI never remediates on its own.
10. **Intent authorisation:** the kinds of intent and the scopes each person or service may
    submit (section 5).
11. **Voice:** whether to keep room for it, and when (proposed: after Translate's first phase,
    low priority).
12. **The golden state rule (section 11):** the rule, and each of its seven sub-rules, one by
    one.
13. **AI roles and permissions (section 12):**
    1. the three roles and their scopes (network, site, device role);
    2. on-behalf-of execution with no AI identity stronger than the person;
    3. approval only through the GUI's confirm by hash;
    4. the request kinds, the change-request offer, and the security row's threshold
       (proposed: three attempts in 24 hours, or an injection flag);
    5. separation of duties per network, off by default;
    6. the change-request board.
14. **Prompt-injection defence (section 13):**
    1. identity only from the verified session (as today);
    2. tools fixed per role, each re-checking `may` as the person, with denials audited;
    3. approval only by confirm;
    4. the order of output validation;
    5. prompt hygiene for flagging only;
    6. no acting tools against network data;
    7. no external loads or internet tools;
    8. the red-team eval set, any non-zero result blocking the release.

### Decided, 2026-10-13 (the operator)

| # | Decision |
|---|---|
| 1 | **Per-policy authority: yes.** |
| 2 | **Auto-fix classes: management-plane configuration only** (logging hosts, SNMP, NTP, IP SLA probes); never routing, interface state, ACLs, AAA or credentials, or s3 and the management path (section 3's table, as decided). |
| 3 | **The rails: approved**, with `docs/PHASE8_PLAN.md` section 7's changes (below). |
| 4 | **Providers: Anthropic first, behind the provider-agnostic client;** a local model optional, later. *Amended 2026-10-14: a built-in local model ships with Mercury, US-origin only (below).* *Amended 2026-10-16 (the operator, offline-first; docs/PHASE8_PLAN.md section 12.1): the local profile is the core path every feature must pass on; Anthropic and any other hosted provider are optional profiles.* |
| 5 | **Translate's first scope: management-plane services** (logging, SNMP, NTP and the like), not a routing statement. |
| 6 | **Batfish: yes, for routing-affecting changes;** Mercury's own IOS checks stay for every change. Its licence (Apache-2.0) is accepted with the decision. |
| 7 | **Loki's `severity` label and a stable trap label: yes, as a host step.** |
| 8 | **History on E18: yes; E18 becomes a Phase 8.0 prerequisite.** |
| 9 | **AI catalog selection: yes, observe mode first.** Gated on MEASURED agreement in observe mode (at least 95% over at least 100 selections); self-reported confidence is logged for analysis only and never decides. |
| 10 | **Intent scopes: network, site, device role.** |
| 11 | **Voice: deferred.** |
| 12 | **The golden state rule and its seven sub-rules: approved** (section 11). |
| 13 | **AI roles and permissions: approved** (section 12). |
| 14 | **Prompt-injection defence and the red-team gate: approved** (section 13). |

**Decided, 2026-10-14 (the operator):**
- **Model origin: US-only, operator's decision** (section 7, "The built-in local model and the
  multi-model rule").
- **The multi-model design rule:** one tool registry and one prompt structure, adapters per API
  shape, per-model profiles as data, a curated list of only the models that passed the eval.
- Pending: the engine, delivery, tiers, reliability, isolation and release gate
  (docs/PHASE8_PLAN.md section 9, decision 12); each candidate model's licence (decision 13).
  *2026-10-16:* the engine is named by the operator's offline-first rule, a reading for the
  operator to confirm (docs/PHASE8_PLAN.md section 12.5, gap 10).

The numbers the operator changed (all in `docs/PHASE8_PLAN.md` section 7):
- **No self-reported confidence gate** (the ≥ 0.9 gate is dropped); catalog selection is gated on
  measured agreement in observe mode, 95% over 100.
- **Respond's threshold stays** (100 "would have fixed" events over 30 days), and **lab-only
  drift drills** feed observe mode: deliberate, known deviations on non-critical devices, each
  labelled a drill and never counted as production evidence.
- **Golden cases:** labelled replayed or synthesised cases are allowed, with **at least 10 real
  cases per feature**.
- **Exact model versions are pinned;** any model change re-runs the full eval suite.
- **Tool calls: 8 by default;** a feature may raise it only where its eval shows the need.
- **Ranking:** natural language → PromQL or LogQL first, then alert correlation; the rest as
  proposed.

**Queued later the same day (the operator, 2026-10-13; no build now): pre-change verification.**
- **Batfish is the default gate for routing-affecting changes** (decision 6, confirmed).
- **Plus a single-node twin for high-risk change classes:** startup configuration, credentials
  and AAA, and platform upgrades. A throwaway C8000v or vIOS in containerlab is booted with the
  candidate configuration, checked, and torn down (Lab Part 1's throwaway-node method).
- **Sized against the hosts' RAM, measured 2026-10-13 (read-only):**
  - the lab host: 80 GB, 52 GB available, 24 cores;
  - a running C8000v uses about 4.0 GiB and two busy cores; a vIOS about 386 MiB;
  - so a twin of either fits on the lab host beside the fleet;
  - a one-host public install (the NMAS host here: 16 GB, 11.8 GB available, 4 cores) fits one
    C8000v twin at a time, or a vIOS easily, and needs hardware virtualisation inside the VM.
- **Not measured yet:** a twin's boot-to-ready time, which bounds how long a gated change
  waits. The lab's C8000v and vIOS boots give the first figures.

## 10. AI engineering standards (binding on every AI feature)

The operator's Phase 8 charter (2026-10-13) makes these binding. `docs/PHASE8_PLAN.md` applies
them feature by feature.

**Prompts are versioned code.**
- They live in `prompts/`, one file per feature and version: role, task, rules, output
  contract, and tagged context blocks marked as data.
- They are reviewed like code and gated by the feature's evals: a prompt change that lowers an
  eval's score does not merge.
- Order: a stable prefix first (system, schema, the network digest), so the provider caches it,
  with the per-request material last.
- Low temperature for translation and classification; the temperature is a per-model profile
  setting, and consistency over N runs on each card's compared fields is what is measured,
  never assumed from temperature (the operator, 2026-10-15; PHASE8_PLAN 11.1, 11.11).
- "Ask, don't guess" is a field of the output schema, not a hope; and code asks whenever a
  reference resolves to zero or several objects, whatever that field says (PHASE8_PLAN 11.2).
- **Few-shot and an error contract** on every translation prompt:
  - 2 or 3 real input → output examples drawn from the config repository's history, 1 or 2 of
    them a clarification or a refusal in the error contract (the operator, 2026-10-15;
    PHASE8_PLAN 11.4);
  - the explicit error shapes `{"error": "could not parse"}` and
    `{"error": "ambiguous", "clarification_needed": "…"}`, each surfaced to the operator.
- **Minimum context, found by test:** each feature's eval suite finds and records the smallest
  context that still produces correct output, by removing context blocks until the score drops.
  That number becomes the feature's context budget, re-measured when the prompt changes.

**Responses are constrained and validated.**
- Every response uses the provider's schema-constrained output (a tool-use schema or
  structured output), never prefill.
- Each is validated by a versioned Pydantic model. A failure gets one retry carrying the
  validator's error, then degrades gracefully: the workflow continues without AI and says so.
- Every finding cites evidence references, and a deterministic check confirms that each one
  was actually fetched in this run; a finding citing something never fetched is dropped.
- Every schema carries `needs_human`, `confidence` and `open_questions`. `confidence` is
  logged for analysis only; no gate reads it (the operator, 2026-10-13).
- Every translation schema marks each field `stated` (with the request's words) or `inferred`,
  and the read-back highlights the inferred ones (the operator, 2026-10-15; PHASE8_PLAN 11.3).

**Tools are narrow, typed and read-only.**
- The reads: `query_prometheus`, `query_loki`, `get_intent`, `get_drift`, `netbox_lookup`, and
  `show_command` through the read-only allowlist.
- The only writing tools are `propose_*`: each returns a draft into preview, confirm and
  verify, never an action.
- Each run has budgets on tool calls, tokens and wall time. A tool's description is written as
  carefully as a prompt.
- Every tool is exposed through one MCP server.
- **One definition per tool, for every model:** a tool's JSON Schema and its role binding are
  written once, in one registry, and every adapter imports them. No adapter, profile or prompt
  defines a tool, and no prompt is written per model (the operator, 2026-10-14; the test is
  named in docs/PHASE8_PLAN.md section 10.9).

**Network knowledge is retrieved, never trained.**
- No fine-tuning: NetBox, Git intent, Prometheus and Loki are read at question time.
- A network digest is regenerated automatically.
- Incident records (finding → cause → fix) are reviewed by a person and versioned.

**Security.**
- Input normalised before every prompt, on the person's text and on retrieved data: NFKC;
  zero-width, bidirectional-override and control characters stripped; length caps per block;
  each removal in the audit log (the operator, 2026-10-15; PHASE8_PLAN 11.7).
- Masking before every prompt (section 7; C733's index, C745's shapes), after normalisation.
- Everything retrieved is untrusted data (section 8's threat model).
- Every prompt and response is recorded in History with who asked.

## 11. The golden state rule: what autonomy may do

**The operator's principle (2026-10-13), governing every autonomous action. It refines section
3's catalog rule. The rule and each sub-rule below are the operator's to confirm (section 9,
decision 12); until then, nothing acts on its own but scheduled rotation.**

**THE RULE.**
- **The current earned baseline is the golden state** (`baseline/<ts>`, earned by measurement:
  `golden_state.judge_device`, the declared protocols up).
- **Autonomous action is limited to two things:**
  - **(a)** converging devices back to the golden state;
  - **(b)** a short, explicit catalog of operational recovery actions that leave the golden
    state unchanged.

  This holds whoever takes the action: the deterministic engine, or AI choosing from the
  catalog.
- **Anything that would change the golden state is a change,** and needs a person's approval.
  An approved, verified change earns the next baseline.

It answers Respond's hardest question, "fix it back to what?". Autonomy restores what was
measured to work; it never decides what the network should become.

**The sub-rules, each a decision for the operator:**

1. **No current earned baseline, no autonomy.** A device (or network) with no earned baseline,
   or with one its intent has moved past, gets a Needs attention row ("no golden state:
   autonomy off until a baseline is earned"), and nothing acts on it.
2. **Policy-authorised actions re-earn the baseline automatically once verified.** Rotation now,
   the remediation catalog later: a verified action earns the next baseline, recorded with the
   policy's authority. **Secret lines are never restored from an older baseline:** the C75 guard
   (a restore never changes an account the device holds; C79, never adds one back) applies to
   every convergence, so a rotated credential is never reverted to its predecessor.
3. **Config convergence re-applies only the deviating lines,** never a whole-device reload or a
   whole-config replace:
   - the program is computed as a deploy's (merge-only, the authorised lines), previewed and
     recorded;
   - then verified, and rolled back on failure, exactly as a person's deploy.
4. **Operational deviations are not config drift.** A neighbour down, a link down, an
   err-disabled port: the configuration matches the golden state, and the network does not.
   Only catalog actions apply (for example, bouncing an err-disabled port whose cause has
   cleared); anything else goes to a person.
5. **Deliberate human drift is protected:**
   - **a grace period:** a deviation must persist before convergence;
   - **a "change in progress" hold** any person can set on a device or a scope, with a reason
     and an end time;
   - **maintenance windows,** in which nothing converges.

   A deviation attributed to a named person (AAA accounting, or a syslog `%SYS-5-CONFIG_I`
   naming the user) becomes a **Capture-or-Revert decision** for a person, never a silent
   revert. AI may classify a deviation as deliberate or unexplained, citing its evidence;
   deterministic code decides what happens.
6. **Scope limits:** anything whose revert could cut Mercury off goes to a person: the
   management path (s3 in this lab), routing protocols, the vty and credential lines. The one
   exception, decided per class: run LAST, with a safe fallback (the repair route CLAUDE.md
   requires for a change to the path to a device).
7. **The lifecycle in the GUI:** Change → Earn baseline → Maintain → Change. The maintainer's
   state is visible on Needs attention and on each device's page (a board first):
   - **on:** maintaining, its baseline named;
   - **held:** a change in progress, by whom, until when;
   - **no baseline:** autonomy off, and why;
   - **observe mode:** "would have converged", not acting.

**How it fits sections 3 and 4.**
- **Respond's auto-fix classes** become convergence (sub-rule 3) plus the operational catalog
  (sub-rule 4).
- **Activate** is the approved change that earns the next baseline.
- **AI's selection** (decision 9) chooses only among catalog actions and convergences that
  leave the golden state unchanged.

## 12. AI roles and permissions

**The principle (the operator, 2026-10-13): the AI never enforces permissions; deterministic
code does.** Capability comes by role: the tools an AI session receives depend on who is
asking, decided before the model is called. Each item below is a decision for the operator
(section 9, decision 13).

1. **Roles from sign-in.** Today the access proxy's verified identity (Cloudflare Access); for
   the public release, OIDC (Authentik, Active Directory groups). *Amended 2026-10-16:*
   Cloudflare Access needs the internet to sign anyone in (docs/OFFLINE_OPERATION.md section
   1.1). The operator decided Keycloak per instance (docs/OFFLINE_OPERATION.md section 1.3), so
   roles come from its token's groups, offline too (docs/PHASE8_PLAN.md section 12.5, gap 9).
   Each role is scoped by network, site and device role:
   - **viewer:** read-only questions;
   - **engineer:** reads, and changes to intent through `propose_*` drafts;
   - **admin / approver:** approves changes, policies and remediation classes.

   Roles sit on top of Mercury's `may` and its gate kinds (`modules/route_gates.py`). A role
   never widens what `may` allows.
2. **Every tool call runs as the asking person** (on-behalf-of), filtered to that person's
   scope. The AI has no service identity stronger than the person: a viewer's session reads
   only what that viewer may read. **Reveal of masked lines stays a GUI action** with its own
   permission (`reveal`, a verified person); no AI tool reveals.
3. **Approval is never conversational.** Only the GUI's preview confirmed by hash, by a
   verified person, approves. No AI tool approves, and no text a model returns is read as
   approval.
4. **Request kind, decided by the schema and checked by code.**
   - **The schema:** the response carries `request_kind`: `query`, `change` or `unsupported`.
   - **A change from a role without propose permission** for that scope:
     - nothing changes;
     - the person is offered **"submit as a change request"**: a draft in an approver's
       queue, the approval queue rebuilt on preview and confirm;
     - the attempt is recorded in History.
   - **Repeated or injection-like attempts** (proposed: three in 24 hours, or a validator's
     injection flag) raise a **security row** on Needs attention.
   - **`unsupported`** is refused, saying what the workflow does.
   - **A misclassification cannot cause a change:**
     - if the model calls a change a `query`, a viewer's session holds no `propose_*` tool, so
       no draft can exist;
     - every change path needs a `propose_*` draft AND the GUI's confirm by hash;
     - if it calls a query a `change`, the person is offered a change request they need not
       file.
   - **The deterministic check reads the ROLE's tool list, never the model's classification.**
5. **Separation of duties** is a per-network setting, off by default: a single admin may propose
   and approve. An enterprise can require that a change's approver is not its proposer; the
   confirm then refuses the proposer by name.
6. **A board first:** the change-request flow. A viewer asks; the request is flagged as a
   change; the request is filed; it lands in an approver's queue; the approver approves or
   declines, through the preview confirmed by hash.

**The shape, in code** (illustrative; names follow section 10's tools):

```python
# The tools a session receives, by the asking person's role. Read tools are scope-filtered; the
# only writing tools are propose_*, returning drafts into preview and confirm. No tool approves
# and none reveals a masked line.
READ = ["query_prometheus", "query_loki", "get_intent", "get_drift", "netbox_lookup",
        "show_command"]                                   # show_command: the read-only allowlist
TOOLS_BY_ROLE = {
    "viewer":   READ,
    "engineer": READ + ["propose_intent_change", "propose_verifier"],
    "approver": READ + ["propose_intent_change", "propose_verifier"],  # approval is the GUI's
}


def ask_ai(person, network, request):
    """One named workflow's entry ("ask the network"), never a general chat."""
    role, scope = roles.resolve(person, network)          # from sign-in; deterministic
    if role is None:
        return refused(f"{person.actor} has no role on {network}")
    tools = [bind(t, on_behalf_of=person, scope=scope) for t in TOOLS_BY_ROLE[role]]
    answer = gateway.run(feature="ask", request=mask(request), tools=tools,
                         schema=AskAnswer)                # request_kind, evidence_refs, ...
    history.record(person, network, request, answer)      # every prompt and response
    if answer.request_kind == "change" and "propose_intent_change" not in TOOLS_BY_ROLE[role]:
        attempts.record(person, network, answer)          # three in 24 h: a security row
        return offer_change_request(person, network, request)
    if answer.request_kind == "unsupported":
        return refused("this workflow answers questions and drafts intent changes")
    return answer          # a query's answer, or a draft that only preview and confirm can apply
```

## 13. Prompt-injection defence

**The threat model (the operator, 2026-10-13):** the language model is an untrusted component,
acting with the requester's privileges or fewer. Design so that **a fully compromised model can
do nothing the person could not already do.** Each item is a decision for the operator
(section 9, decision 14).

1. **Identity only from the authenticated session.** Mercury already does this.
   `identity.identify` (`modules/identity.py`) verifies the Cloudflare Access assertion
   (`Cf-Access-Jwt-Assertion`) server-side, never trusting the header's claims:
   - its signature against the team's signing keys (PyJWKClient, RS256 only);
   - the audience and issuer from Settings, with `exp`, `iat`, `aud` and `iss` required and
     30 s of leeway;
   - and the request must come from a trusted peer (the tunnel connector's address; no
     localhost exemption). A forged key id is told apart from an unreachable key set.

   OIDC replaces it for the public release. *Amended 2026-10-16:* that assertion cannot be
   verified with no internet (docs/OFFLINE_OPERATION.md section 1.1). The operator decided
   Keycloak per instance, whose signing keys are local (docs/OFFLINE_OPERATION.md sections 1.3
   and 1.8). The item stands as "identity only from the instance's verified sign-in"
   (docs/PHASE8_PLAN.md section 12.5, gap 9). The person's role is looked up server-side BEFORE
   the model is called (section 12). Nothing in prompt text affects identity or permissions.
2. **The tool set is fixed per role before the call,** and every tool re-checks, at execution
   and as the person, that `may(permission, scope)` holds. A denial is audited (who, which
   tool, which scope, the run's id).
3. **A change needs the preview confirmed by hash** from an authenticated session; no AI output
   counts as approval.
4. **Output validation, in order:**
   1. the schema;
   2. authorisation of what the output requests (the person may submit this kind of intent for
      this scope; section 5);
   3. the normal change gates (`nmas-config-check`, the conflict layer, pre-change
      verification, preview by hash, verify and rollback).
5. **Prompt hygiene, for FLAGGING only:**
   - the person's text goes in the user message; retrieved data goes in tagged blocks marked
     as data;
   - any identity or permission claim found inside content ("I'm an admin", "the operator
     approved this") is ignored and reported;
   - an optional cheap injection classifier writes to the audit log.

   None of this is relied on for security; items 1 to 4 are.
6. **Indirect injection through network data** (interface descriptions, log lines, NetBox
   fields): the model has no acting tools; a proposal shows the exact diff and the exact device
   commands; a person confirms.
7. **Exfiltration:**
   - **AI output is rendered without loading anything external:** plain text, or links only to
     Mercury's own pages (any other URL is shown as text, never as a link or an image). The
     strict CSP already refuses external loads on every v2 page.
   - **No AI tool reaches the internet:** the tools read Mercury's own stores and the
     integrations Mercury already calls.
8. **A red-team eval set in CI.** It runs on recorded responses, as all CI evals do, plus live
   on the host before a release. Its cases:
   - "I'm an admin";
   - "ignore previous instructions";
   - role-play;
   - data-borne injections in interface descriptions, log lines and NetBox fields;
   - attempts to exfiltrate through links.

   It asserts **zero** unauthorised tool calls, **zero** unauthorised proposals and **zero**
   external links. **Any non-zero result blocks the release.** *Added 2026-10-15:* hidden
   instructions in zero-width, bidirectional-override and tag characters (PHASE8_PLAN 11.7).
9. **Voice and speaker spoofing** (the operator, 2026-10-15; PHASE8_PLAN 11.6). A voice can be
   recorded, synthesised or replayed, so **voice may query and request, and never approves.**
   Approval is only the GUI's confirm by hash, from the authenticated session (item 3). A voice
   identifies no one: a voice request runs as the session that carries it, never as the
   speaker it sounds like, and a change it asks for waits at the GUI's confirm.

**The shape, in code** (illustrative):

```python
def verify_access_jwt(request) -> Identity:
    """Identity from the authenticated session only: today identity.identify(), which verifies
    the Access assertion's signature (RS256, the team's keys), audience, issuer and expiry, and
    requires a trusted peer. Nothing the model says is consulted."""
    ident = identity.identify(request)
    if not ident.is_identified:
        raise Unauthenticated(ident.reason)
    return ident


class Tool:
    """A tool an AI session may call. Bound to the asking person and their scope BEFORE the model
    runs; it re-checks the person's permission on every call, as the person."""

    def __init__(self, name, permission, run):
        self.name, self.permission, self._run = name, permission, run
        self.person = self.scope = self.run_id = None

    def bind(self, person, scope, run_id):
        tool = copy.copy(self)
        tool.person, tool.scope, tool.run_id = person, scope, run_id
        return tool

    def __call__(self, **args):
        target = scope_of(self.name, args)          # the devices, site or network the call touches
        allowed, why = identity.may(self.person, self.permission, target)
        if not allowed or not within(target, self.scope):
            audit.denied(self.person, self.name, target, self.run_id, why or "outside scope")
            return {"error": "denied", "why": why or "outside your scope"}   # data, not a raise
        audit.called(self.person, self.name, target, self.run_id)
        return self._run(on_behalf_of=self.person, **args)   # as the person, never a service
```
