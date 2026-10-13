# Phase 8: AI, in service of an intent-based network (a plan; not built)

**The operator's charter, 2026-10-13.** Phase 8 starts only after Phase 7 closes. **The operator
approves this plan, and every number in it, before any code.** **Approved 2026-10-13 with the
changes recorded in section 9 ("Decided") and applied in sections 5 to 7.** It builds on
[IBN_DESIGN.md](IBN_DESIGN.md) (C750): what each IBN function needs, the AI layer, and the
binding AI engineering standards (its section 10).

## 1. The goal

Mercury becomes an intent-based networking platform: Translate, Activate, Assure, Respond. AI is
a means to that, not the product. **Success is measurable operator value per token spent, with
the deterministic core unchanged and Mercury fully usable offline.**

## 2. The non-negotiables

1. **AI proposes, deterministic code decides.**
   - AI never writes device configuration, never decides compliance, and never invents an
     action.
   - Every AI output passes the gates a person's change does: the schema,
     `nmas-config-check`, pre-change verification, a preview confirmed by hash, verify and
     rollback.
   - *Pending the operator's decision 9 (IBN_DESIGN section 3):* AI may SELECT an action from a
     pre-approved catalog of deterministic remediations within a policy's limits. Until
     confirmed, AI never remediates on its own.
   - **The golden state rule governs all autonomy** (IBN_DESIGN section 11; the operator's
     decision 12, the rule and each sub-rule to confirm):
     - the current earned baseline is the golden state;
     - autonomous action (the deterministic engine, or AI choosing) is limited to converging
       devices back to it, and a short catalog of operational recovery actions that leave it
       unchanged;
     - anything that would change it is a change needing a person's approval, and an
       approved, verified change earns the next baseline.
2. **Deterministic first.** Before any AI feature, the card shows why a rule, query, template or
   builder cannot do it. If one can, that is built instead (section 6 lists the features this
   rule already removes).
3. **Offline parity.** Every workflow works without AI. AI is an accelerator, never a
   dependency: with the gateway off, every screen and operation works and says AI is off.
4. **No open-ended assistant.** There is no general chat. AI appears only inside a named
   workflow, with specific inputs, a schema-constrained output and a defined action for each
   result.
5. **The AI never enforces permissions; deterministic code does** (IBN_DESIGN section 12; the
   operator's decision 13):
   - the tools an AI session receives depend on the asking person's role (viewer, engineer,
     approver), from sign-in, scoped by network, site and device role;
   - every tool call runs on behalf of that person, and no AI identity is stronger;
   - approval is only the GUI's confirm by hash;
   - reveal stays a GUI action;
   - a change asked for by a role without propose permission changes nothing and is offered as
     a change request;
   - separation of duties is a per-network setting, off by default.
6. **The model is an untrusted component** (IBN_DESIGN section 13; the operator's decision 14).
   A fully compromised model can do nothing the person could not already do:
   - identity only from the verified Access assertion (verified server-side today:
     `identity.identify`);
   - tools fixed per role before the call, each re-checking `may` as the person and auditing
     denials;
   - approval only by confirm;
   - output validated by schema, then authorisation, then the change gates;
   - no acting tools against network data;
   - no external links or internet tools;
   - a red-team eval set whose any non-zero result blocks the release.

## 3. The AI feature card

Every AI feature has one, in this plan, before any code. A feature without a complete card is
not built.

| Field | What it says |
|---|---|
| Problem | the operator's task, how often it happens, and today's time and cost without AI: **measured** (8.0's observe period times the task as people do it), never guessed |
| Deterministic alternative | the rule, query, template or builder considered, and why it falls short |
| Inputs | the exact context, sized in tokens (the measured minimum, section 4); the tools (read-only, bounded); the output schema (Pydantic, versioned) |
| Success metric | a target (accepted-without-edit rate, time saved, findings confirmed true) and the eval set that measures it |
| Budgets | tokens and cost per use, latency, the monthly cap; the model tier and why |
| Observe mode | how long it runs alongside the deterministic path, and the threshold to leave it |
| Kill criteria | the measured result that removes it (for example acceptance below target after N uses, or cost per accepted output above budget). A feature that misses is removed, not left running |
| Owner | who answers for it |

## 4. Standards and token discipline

**The AI engineering standards** are IBN_DESIGN section 10, binding:
- prompts are versioned code in `prompts/`;
- schema-constrained output, validated by Pydantic, with evidence references checked
  deterministically;
- narrow read-only tools on one MCP server;
- retrieval, never fine-tuning;
- masking before every prompt;
- every prompt and response recorded in History.

Two of them come from the operator's course material on AI in networking and intent-based
networking:
- **Few-shot and an error contract** on every translation prompt: 2 or 3 real examples from the
  config repository's history, and the error shapes `{"error": "could not parse"}` and
  `{"error": "ambiguous", "clarification_needed": "…"}`, surfaced to the operator.
- **Minimum context, found by test:** the eval suite removes context blocks until the score
  drops, and records the smallest context that still passes. That number, times 1.5, is the
  feature's context budget (proposed), re-measured when its prompt changes.

**Token discipline, the anti-waste rules:**
- **Context budgets per feature.** Never send a whole config, log or metric series: summarise
  deterministically first, as the operator's Lab 6 formatter did, and retrieve only what the
  question needs.
- **Model routing:** the smallest model that meets the eval target. A larger model is used
  only where the eval proves the need, and the card says which.
- **Caching:** prompt caching for the stable prefix (system, schema, the network digest);
  result caching where the same question repeats (keyed by the masked question and the data's
  version).
- **Capped agent loops:** a run that hits its budget stops and reports what it had. It never
  silently continues.
- **A cost dashboard:** tokens and cost per feature, per use and per accepted output, with the
  monthly caps enforced in the gateway (a cap reached refuses the next call, by name).
- **Anti-patterns rejected in review:**
  - a general chat assistant;
  - AI doing what a query or rule can;
  - unvalidated free-text output;
  - a feature with no eval set, no kill criteria or no owner.

**Evals and the suite's rule of no live network.** The suite never reaches a live network or
service (CLAUDE.md), so CI cannot call a model. Evals run two ways:
- **In CI:** each feature's golden cases run against RECORDED responses. The schema, the
  validators, the evidence-reference check, the error contract and the deterministic scoring
  are all tested offline, and a prompt change must re-record.
- **On the host,** as a job: live evals through the gateway, recorded with their scores, cost
  and model version. A prompt or model change merges only when the live score does not fall
  below the feature's target.

## 5. The sequence, each sub-phase with exit criteria measured on the host

| Sub-phase | Builds | Exit criteria (measured on the host) |
|---|---|---|
| **8.0 Foundations** (no user-facing AI; **E18, the records database, is its prerequisite**, decision 8) | roles from sign-in and `TOOLS_BY_ROLE` (IBN_DESIGN section 12), every tool bound on behalf of the asking person and filtered to their scope; the change-request queue and its board (viewer asks → flagged → filed → approver's queue → approve or decline); the security row for repeated or injection-like attempts; separation of duties per network; the gateway (provider-agnostic, Anthropic first, exact model versions pinned; a per-network switch, cost caps; a local model optional, later); the prompt registry; the schema library; the MCP tool server; tracing (OpenTelemetry GenAI conventions); masking through C733's index (C745's shapes closed first); the eval harness (recorded in CI, live on the host) with a golden dataset from real lab incidents; the cost dashboard | the red-team set (IBN_DESIGN section 13: "I'm an admin", "ignore previous instructions", role-play, data-borne injections, link exfiltration) passes with zero unauthorised tool calls, proposals and external links, recorded in CI and live on the host; every tool re-checks `may` as the person and a denial is audited (shown by test); a viewer's session holds no `propose_*` tool and a misclassified change still changes nothing (shown by test); every tool call recorded as the asking person; no tool approves or reveals; the gateway refuses at a cap; masking shown on planted secrets of every shape; every tool read-only but `propose_*` (shown by test); a recorded and a live eval run end to end; the dashboard shows a test feature's cost per use |
| **8.1 Assure** | the deterministic verifier model and compliance status first (history on E18); then, where cards justify it, natural-language questions → PromQL or LogQL read back by the E3/F3 builder before running, and alert correlation over deterministically grouped alerts | the verifiers' statuses on the host match the readers'; each AI feature past its observe threshold, or killed |
| **8.2 Respond, observe** | the golden state rule's maintainer (IBN_DESIGN section 11): no baseline, no autonomy; convergence of the deviating lines only; the operational catalog; holds, windows and Capture-or-Revert for attributed drift; its state on Needs attention and each device page (a board first). All in observe mode ("would have converged"), on the deterministic policy engine (rotation's pattern). Plus AI root-cause proposals for novel deviations, approved by a person; incident record drafts; AI classification of deliberate vs unexplained drift, with evidence | each class's false-positive rate measured over its period; no convergence would have touched a secret line, the management path or routing; root-cause proposals' confirmed-true rate measured |
| **8.3 Respond, enabled per class** | convergence and catalog classes enabled once observe mode meets the threshold; a verified action re-earns the baseline; AI selection only among actions that leave the golden state unchanged, if decision 9 is confirmed, after its own observe period | each enabled class within its rate and with no rail breached for its period |
| **8.4 Activate** | commit-triggered deploys in change windows, canary then fleet (deterministic, on rotation's scheduler) | a canary failure stops the fleet (shown on the lab); a management-path commit waits for a person |
| **8.5 Translate** | the network intent model and its deterministic compiler, first scoped to management-plane services (decided 2026-10-13), the policy-conflict layer, intent authorisation (scopes: network, site, device role), pre-change verification (Batfish for routing-affecting changes, and Mercury's IOS checks for every change; a single-node containerlab twin booted with the candidate configuration for startup-configuration, credential and AAA, and platform-upgrade changes, queued 2026-10-13, IBN_DESIGN section 9); then the 8-step natural-language → intent pipeline (IBN_DESIGN section 8), AI writing intent only; template drafting for new platforms, accepted only by round trip | the compiler's round trip on the lab's real intent; a conflict and an unauthorised intent each refused by name; the pipeline's acceptance rate at target |

**The golden dataset's first cases**, from the register, each with its evidence and its
confirmed cause:
- the s3 management-path burst: s3 forwards for the fleet while failing to answer for itself
  (C93), and the backup window's nightly bursts (C289);
- a rotation reverted when verify was refused (C726);
- r4 dropping traffic for an ISP peering address while advertising a default (C695);
- LLDP lost on two switch ports while routing crossed (C671);
- each lab host start leaving another IPv6 lease, a random IAID (C681);
- the archive check's false leak from non-idempotent masking (C743);
- the host step's child-shell variable (C748);
- r1's OSPF scrape tail (C700).

More cases are added as incidents happen; each is the finding, its evidence, its cause and its
fix, reviewed by a person.

## 6. The candidate AI features, ranked by expected value per token

Each line is the card's summary. Every number is a proposal for the operator (section 7).
"Today's time" is measured in 8.0's observe period before any target is final.

| Rank | Feature (sub-phase) | Deterministic first | Inputs → output | Budget per use | Tier | Target | Observe → leave | Kill |
|---|---|---|---|---|---|---|---|---|
| 1 | **Natural language → PromQL or LogQL** (8.1) | E3/F3's builder (chips, filters, operations) answers most questions; AI only turns a sentence into the builder's own query model | the question, the metric names and labels retrieved for its terms (not the 963), about 2k tokens → the builder's query model, read back by the builder before it runs | 2k in, 200 out, 3 s | small | 80% run without edit, 95% parse and pass the builder's read-back | 30 days and 100 questions; 80% | below 70% after 100 |
| 2 | **Alert correlation** (8.1): grouped alerts → a likely common cause, evidence-linked | deterministic grouping by time window and topology (the same island, the same upstream) does the grouping; AI only names the likely cause over a group the rules formed | one group's alerts, the topology around them, the last change records, about 3k tokens → `{cause, evidence_refs[], confidence, needs_human}` | 3k in, 400 out, 5 s | small | 70% of named causes confirmed by a person, 0 claims without fetched evidence | 30 days and 50 groups; 70% | below 60% after 50, or cost per confirmed cause above 2× budget |
| 3 | **Incident record draft** (8.2): finding → cause → fix from a closed incident's record | the record's fields are filled deterministically from History (commits, receipts, rows); AI writes only the cause and fix sentences, citing the evidence | one incident's evidence summary, about 5k tokens → `{finding, cause, fix, evidence_refs[]}` | 5k in, 600 out, 15 s | small | 80% accepted with light edits | 20 incidents; 80% | below 60% after 20 |
| 4 | **AI catalog selection** (8.3; only if decision 9) | the deterministic class rules choose first; AI only where a deviation matches more than one catalog entry or none by rule | a deviation's evidence and the catalog's eligible entries, about 3k tokens → `{entry, params, confidence, evidence_refs[]}` | 3k in, 300 out, 5 s | small | 95% measured agreement with a person in observe mode (confidence logged, never a gate) | 60 days and 100 selections; 95% | any choice outside the catalog reaching execution (zero tolerance); agreement below 90% |
| 5 | **Root-cause proposal for a novel deviation** (8.2) | Respond's taxonomy handles known classes; AI only for a deviation no class matches | the deviation, the verifiers around it, recent changes and logs summarised deterministically, about 15k tokens → `{causes[], tests_to_confirm[], evidence_refs[], needs_human}` | 15k in, 1.5k out, 60 s | medium (where the eval shows the small tier misses) | 50% of top proposals confirmed true | 20 deviations; 50% | below 35% after 20 |
| 6 | **A proposed pipeline check after an escape** (8.2) | a person writes it today; the register's incident is the input | the incident record and the check catalogue (`nmas-config-check`, tests), about 8k tokens → `{check_kind, rule, planted_case}` | 8k in, 1k out, 30 s | medium | 50% become merged checks | 10 escapes; 50% | below 30% after 10 |
| 7 | **Natural language → intent** (8.5) | the intent editor and the network intent model's forms; AI only for the sentence → the model's structure | the sentence, the schema, the affected intent, NetBox facts, 2 or 3 examples, about 10k tokens (its measured minimum) → the intent model or the error contract | 10k in, 1.5k out, 20 s | small, then medium if the eval proves the need | 70% accepted without edit; 0 validated changes touching devices outside the request's scope | 30 days and 50 intents; 70% | below 55% after 50, or any out-of-scope change reaching confirm |
| 8 | **A verifier draft for review** (8.1) | a person writes verifiers; the statement model makes them short | a statement and the readers' fields, about 4k tokens → a verifier draft and its planted failing case | 4k in, 800 out, 15 s | small | 60% accepted after review, each shown able to fail | 20 drafts; 60% | below 40% after 20 |
| 9 | **Inferring higher-level intent from configs** (8.5) | `neighbours.expected` and the profile already derive some; AI proposes statements across devices | a device set's intent summarised, about 20k tokens → statements with evidence | 20k in, 2k out, 60 s | medium | 60% of proposed statements accepted | 10 runs; 60% | below 40% |
| 10 | **Template draft for a new platform** (8.5) | today a person writes it; accepted only by round trip | a platform's captured config and the nearest template, about 30k tokens → a template draft | 30k in, 6k out, 120 s | medium or large (the eval decides) | 50% pass the round trip within two revisions | 5 platforms | below 40%, or cost per accepted template above 3× budget |

**Removed by rule 2 (deterministic first), not built:**
- **Change summaries:** a deterministic diff summary (sections and line counts per device)
  answers it.
- **Explaining an intent in words:** section 8's read-back is generated deterministically from
  the structure, as it must be.
- **Log summaries:** the logs_summary reader's counts by device and severity, and the E3/F3
  builder.
- **Suggesting a remediation class:** the taxonomy is a lookup.
- **A general assistant:** non-negotiable 4.

## 7. The numbers proposed for the operator's approval

| Area | Number | Why |
|---|---|---|
| The gateway | AI off per network by default; a global monthly cap of $50 and $25 per network; per-feature monthly caps of $5 (features 1, 2, 3, 4, 8) and $10 (features 5, 6, 7, 9, 10) | lab scale; a cap reached refuses the next call, by name |
| Per-use budgets | as section 6's table, enforced by the gateway (a use over its token budget stops and reports) | each card's measured minimum context times 1.5 will replace the table's estimate |
| Agent loops | at most 8 tool calls by default, 60 s wall time and the feature's token budget per run; a feature may raise the 8 only where its eval shows the need (decided 2026-10-13) | a run that hits a cap stops and reports |
| Model tiers | small by default (Claude Haiku 5.5); medium (Claude Sonnet 5.5) only where the eval shows the small tier misses its target; large (Claude Opus 5.5) never by default; **exact model versions pinned, and any model change re-runs the full eval suite** (decided 2026-10-13); Anthropic first behind the provider-agnostic client, a local model optional and later, its eval score shown beside the hosted one | the smallest that meets the target |
| Evals | at least 30 golden cases per feature before observe mode; labelled replayed or synthesised cases allowed, with **at least 10 real cases per feature** (decided 2026-10-13); a prompt or model change merges only when the live score stays at or above target | measured, not argued |
| Observe mode | at least 30 days AND the card's minimum uses (50 for frequent features, 20 for rare) | enough uses to measure a rate |
| Kill | below the card's floor after its uses, or cost per accepted output above 2× budget, or (for features 4 and 7) one out-of-scope result reaching execution or confirm | removed, not left running |
| Respond (deterministic) | a class is enabled only at a false-positive rate of 1% or less over at least 30 days and 100 "would have fixed" events; grace period 2 readings and 15 minutes; at most 6 fixes an hour per network and 1 per device per hour; the same deviation fixed twice in 24 hours halts its policy. **Lab-only drift drills** feed observe mode: deliberate, known deviations on non-critical devices, each labelled a drill and never counted as production evidence (decided 2026-10-13) | the rails of IBN_DESIGN section 3 |
| AI catalog selection (decision 9: yes, observe mode first) | at least 95% MEASURED agreement with a person over at least 100 observed selections before the tier is enabled; no self-reported confidence gate: confidence is logged for analysis only and never decides (decided 2026-10-13) | stricter than the deterministic classes |
| Activate | a canary soaks 30 minutes with its verifiers holding before the fleet; one device at a time after it | rotation's pattern |
| Context budgets | the measured minimum times 1.5 | headroom without waste |

## 8. Process

- **Every AI feature goes through:**
  1. a board, showing where it appears in the GUI;
  2. its card;
  3. its eval set;
  4. observe mode;
  5. the operator's sign-off.

  The board-fidelity rules of Phase 7 apply.
- **Each sub-phase reports:** the value delivered (each card's metric), tokens and cost spent,
  evals passed, and features killed.
- **Register items:** one per feature (its card's link), and one per finding.

### A CLAUDE.md block, proposed for the operator to paste

```
## AI in Mercury (Phase 8 charter, binding)

- **AI proposes, deterministic code decides.** AI never writes device configuration, never
  decides compliance, never invents an action; every AI output passes the gates a person's
  change does (schema, nmas-config-check, pre-change verification, preview by hash,
  verify/rollback). Selection from a pre-approved remediation catalog only if the operator has
  confirmed it (IBN_DESIGN section 3). [not mechanised]
- **The golden state rule:** the current earned baseline is the golden state; autonomous action
  (deterministic, or AI choosing) only converges devices back to it, or runs a catalog
  recovery action that leaves it unchanged; anything that would change it needs a person's
  approval, and an approved, verified change earns the next baseline (IBN_DESIGN section 11,
  once the operator confirms it). [to be mechanised in 8.2]
- **The AI never enforces permissions; deterministic code does:** an AI session's tools come
  from the asking person's role (TOOLS_BY_ROLE), every call runs on their behalf, approval is
  only the GUI's confirm by hash, and reveal is never an AI tool (IBN_DESIGN section 12).
  [to be mechanised in 8.0]
- **The model is an untrusted component:** identity only from the verified session; tools fixed
  per role, each re-checking `may` as the person; no AI output approves; no AI tool reaches the
  internet; a red-team eval with any non-zero result blocks a release (IBN_DESIGN section 13).
  [to be mechanised in 8.0]
- **Deterministic first:** an AI feature's card shows why a rule, query, template or builder
  cannot do it; if one can, build that. [not mechanised]
- **Offline parity:** every workflow works with the AI gateway off. [to be mechanised in 8.0]
- **No open-ended assistant:** AI only inside a named workflow, with a schema-constrained
  output and a defined action per result. [not mechanised]
- **Every AI feature has its card in docs/PHASE8_PLAN.md before any code**: problem (measured),
  deterministic alternative, inputs and schema, success metric and eval set, budgets and tier,
  observe threshold, kill criteria, owner; a feature that misses its kill criteria is removed.
  [to be mechanised in 8.0: a feature with no card is refused by test]
- **The standards of docs/IBN_DESIGN.md section 10 bind every prompt, tool and response.**
  [to be mechanised in 8.0]
```

## 9. The operator's decisions, before any code

1. **Approve the plan and every number in section 7.**
2. **Decision 9 of IBN_DESIGN:** whether AI may select from a pre-approved remediation catalog.
3. **Decision 12 of IBN_DESIGN, the golden state rule:** the rule, and each of its seven
   sub-rules:
   1. no baseline, no autonomy;
   2. a verified policy action re-earns the baseline, and no secret is restored from an older
      one;
   3. convergence of the deviating lines only;
   4. operational deviations only by catalog;
   5. deliberate drift protected, attributed drift a Capture-or-Revert decision;
   6. scope limits;
   7. the lifecycle in the GUI.
4. **Decision 13 of IBN_DESIGN, AI roles and permissions:**
   1. the three roles and their scopes;
   2. on-behalf-of execution;
   3. approval only by the GUI's confirm;
   4. request kinds, the change-request offer, and the security row's threshold (proposed:
      three attempts in 24 hours, or an injection flag);
   5. separation of duties per network, off by default;
   6. the change-request board.
5. **Decision 14 of IBN_DESIGN, prompt-injection defence:** its eight items. The release gate:
   any non-zero red-team result blocks a release.
6. **Providers and a local model:** which hosted providers; whether a local model is required.
7. **The ranking:** which of section 6's candidates proceed to boards and cards first
   (proposed: 1 and 2, in 8.1).
8. **The CLAUDE.md block:** paste it (the operator's file), or change it.
9. **The owner of each feature.**

### Decided, 2026-10-13 (the operator)

| # | Decision |
|---|---|
| 1 | **The plan and section 7's numbers: approved, with these changes** (applied in sections 5 to 7): no self-reported confidence gate (catalog selection gated on measured agreement in observe mode, 95% over 100; confidence logged for analysis only); Respond's 100 events over 30 days kept, with labelled lab-only drift drills that never count as production evidence; labelled replayed or synthesised golden cases allowed, at least 10 real per feature; exact model versions pinned, any model change re-running the full eval suite; 8 tool calls by default, raised per feature only where its eval shows the need. |
| 2 | **IBN decision 9, AI catalog selection: yes, observe mode first.** |
| 3 | **IBN decision 12, the golden state rule and its seven sub-rules: approved.** |
| 4 | **IBN decision 13, AI roles and permissions: approved;** scopes network, site and device role (IBN decision 10). |
| 5 | **IBN decision 14, prompt-injection defence and the red-team gate: approved.** |
| 6 | **Providers: Anthropic first, behind the provider-agnostic client; a local model optional, later.** |
| 7 | **The ranking: natural language → PromQL or LogQL first, then alert correlation; the rest as proposed** (section 6, reordered). |
| 8 | Not yet decided: the CLAUDE.md block is the operator's to paste. |
| 9 | Not yet decided: the owner of each feature. |

The rest of IBN_DESIGN section 9, decided the same day: per-policy authority yes; auto-fix
only management-plane configuration (logging hosts, SNMP, NTP, IP SLA probes), never routing,
interface state, ACLs, AAA or credentials, or s3 and the management path; Translate's first
scope management-plane services; Batfish for routing-affecting changes, Mercury's IOS checks
kept; Loki's severity label and a stable trap label as a host step; history on E18, which
becomes an 8.0 prerequisite; voice deferred.
