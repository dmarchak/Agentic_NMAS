# Mercury as an intent-based networking platform (a design; not built)

**The operator's design task, 2026-10-13: doc only, no build. Registered FUTURE / After Phase 7
(C750), beside the credential store redesign (C733), which it depends on for masking.** Nothing
here changes Mercury until the operator's decisions in section 9 are made, phase by phase.

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
> compliance, and never remediates on its own.

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

| Class | Examples | May ever auto-fix? |
|---|---|---|
| Monitoring lines missing | a logging host, an SNMP community or view, an NTP server, the heartbeat applet, a monitoring template's lines absent from the running config | yes, once observe mode measures it safe |
| A probe missing | an IP SLA operation intent declares, absent | yes, as above |
| Drift that adds | lines on the device that intent does not hold (a hand change) | no: a person decides whether to capture it as intent or remove it |
| Drift that removes | intent's lines missing from the device | only for classes already allowed (above); never for the rest |
| Routing | an adjacency down, a route missing, BGP not established | never: always a person |
| Interfaces | a port down, a description changed, a VLAN | never |
| The management path | anything on the path Mercury reaches devices by (the management interface, vty, credentials, the route to the manager), and anything on the switch that carries it (s3 in this lab) | never |
| Credentials | a rotation's failure | never (rotation has its own halt) |

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

## 6. Phase order

Each phase depends on the one before it. **Assure → Respond in observe mode → Respond per
class → automatic Activate → Translate upward.**

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
| Respond | a likely root cause and proposed fixes for a novel problem, approved by a person; a suggested remediation class; an incident record; a proposed new pipeline check whenever a problem slipped through | a person; never the automatic tier |

### Gaps that need deterministic redesign, not AI

The intent model and its compiler; pre-change verification; the activation engine; the
verifier model and compliance history; the remediation policy engine and its taxonomy. Each
must be testable, reproducible and explainable without a model.

### The AI layer's own design

- **A multi-provider gateway:** one module through which every model call goes. It has a
  per-network switch (off by default), cost caps per network and per day (a cap reached
  refuses the next call, by name), and a local-model option for air-gapped installs. Which
  providers, and whether a local model is required, are the operator's (section 9).
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
- **Middle:** Respond's proposals for a person; never its automatic tier.
- **Late:** Translate, once the intent model, compiler and validation exist for it to propose
  into.

## 8. The intent translation pipeline, mapped to Mercury

| Step | What happens | Exists today | New |
|---|---|---|---|
| 1. Input | plain-language intent; when ambiguous, the model asks a question and never guesses | Ask the device's typed reads, a person's reason fields | the request card, the clarifying turn |
| 2. Prompt construction (Python) | the intent model's schema; the affected devices' current intent from Git; NetBox's facts (roles, sites, interfaces, addresses); platform capabilities; a few examples from the repository; masked; only the context the request needs | committed intent readers (`hostvars.read_committed`), NetBox client, `redact_text` | the context selector, the examples, C733's index |
| 3. LLM translation | constrained to the intent model's JSON schema (structured output); it outputs intent, never device configuration or Jinja (template drafting is a separate workflow gated by round trip) | none | the gateway, the schema |
| 4. Validation | the schema; semantics (references exist in NetBox, no conflict with other intent, guardrails such as never the management path or s3); `nmas-config-check`; pre-change simulation (Batfish); the device-level diff and blast radius. On failure one bounded retry with the error fed back, then back to the operator | `nmas-config-check`, the render, `deploy.classify_diff`, the management-path rules | semantic checks, Batfish, the retry |
| 5. Confirmation | the operator's words; a plain-language read-back GENERATED FROM THE STRUCTURED OUTPUT (not the model's own description); the intent diff; the exact device commands; validation results; the risk. Approved by hash: exactly that artifact runs (the model is not deterministic) | preview and confirm by hash, the program masked | the read-back generator |
| 6. Execution | commit the intent to the config repository (its pipeline and GitHub Actions run on it), then deploy, verify, roll back | `save_host_vars`, the pipeline, the config repository's workflow | none |
| 7. Verification that the intent holds | Assure's verifiers prove the network now behaves as stated; roll back if not | verify (configuration) | the statement's verifier (behaviour) |
| 8. Logging | one id linking the words, the masked prompt, the model and version, the raw response, the structured output, validation's results, the approver, the deploy receipt, the verification; the only way to reproduce a translation | receipts, commits | the translation record (on E18's database) |

**Threat model: prompt injection.**
- **Untrusted data:** interface descriptions, log lines, NetBox fields and device output are
  untrusted. They reach the model only as data, delimited and masked, never as instructions.
- **No tools that change anything:** the model's tools are read-only. Its output counts only
  after validation, and validation never trusts the model's own claims: it recomputes every
  reference, diff and risk.
- **Containment:** a request whose context holds instruction-shaped text is still validated
  the same way. The worst an injection can do is propose something validation refuses or a
  person declines.

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
- Low temperature for translation and classification.
- "Ask, don't guess" is a field of the output schema, not a hope.

**Responses are constrained and validated.**
- Every response uses the provider's schema-constrained output (a tool-use schema or
  structured output), never prefill.
- Each is validated by a versioned Pydantic model. A failure gets one retry carrying the
  validator's error, then degrades gracefully: the workflow continues without AI and says so.
- Every finding cites evidence references, and a deterministic check confirms that each one
  was actually fetched in this run; a finding citing something never fetched is dropped.
- Every schema carries `needs_human`, `confidence` and `open_questions`.

**Tools are narrow, typed and read-only.**
- The reads: `query_prometheus`, `query_loki`, `get_intent`, `get_drift`, `netbox_lookup`, and
  `show_command` through the read-only allowlist.
- The only writing tools are `propose_*`: each returns a draft into preview, confirm and
  verify, never an action.
- Each run has budgets on tool calls, tokens and wall time. A tool's description is written as
  carefully as a prompt.
- Every tool is exposed through one MCP server.

**Network knowledge is retrieved, never trained.**
- No fine-tuning: NetBox, Git intent, Prometheus and Loki are read at question time.
- A network digest is regenerated automatically.
- Incident records (finding → cause → fix) are reviewed by a person and versioned.

**Security.**
- Masking before every prompt (section 7; C733's index, C745's shapes).
- Everything retrieved is untrusted data (section 8's threat model).
- Every prompt and response is recorded in History with who asked.
