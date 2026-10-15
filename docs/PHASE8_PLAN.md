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
  `{"error": "ambiguous", "clarification_needed": "…"}`, surfaced to the operator. *Proposed
  (11.4):* 1 or 2 of the examples end in that contract (a clarifying question, a refusal), not
  only successful commits.
- **Added 2026-10-15 (section 11):** consistency measured over N runs (11.1); ambiguity decided
  by code (11.2); field provenance in every translation schema (11.3); input normalised before
  any prompt (11.7); context freshness at confirm (11.10).
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
| **8.0 Foundations** (no user-facing AI; **E18, the records database, is its prerequisite**, decision 8) | roles from sign-in and `TOOLS_BY_ROLE` (IBN_DESIGN section 12), every tool bound on behalf of the asking person and filtered to their scope; the change-request queue and its board (viewer asks → flagged → filed → approver's queue → approve or decline); the security row for repeated or injection-like attempts; separation of duties per network; the gateway (provider-agnostic, Anthropic first, exact model versions pinned; a per-network switch, cost caps; the built-in local model behind the same gateway, section 10); the prompt registry; the schema library; the MCP tool server; tracing (OpenTelemetry GenAI conventions); masking through C733's index (C745's shapes closed first); the eval harness (recorded in CI, live on the host) with a golden dataset from real lab incidents; the cost dashboard | the red-team set (IBN_DESIGN section 13: "I'm an admin", "ignore previous instructions", role-play, data-borne injections, link exfiltration) passes with zero unauthorised tool calls, proposals and external links, recorded in CI and live on the host; every tool re-checks `may` as the person and a denial is audited (shown by test); a viewer's session holds no `propose_*` tool and a misclassified change still changes nothing (shown by test); every tool call recorded as the asking person; no tool approves or reveals; the gateway refuses at a cap; masking shown on planted secrets of every shape; every tool read-only but `propose_*` (shown by test); a recorded and a live eval run end to end; the dashboard shows a test feature's cost per use |
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

*Proposed (11.9):* feature 1's pattern extended to Mercury's records (changes, rotations,
approvals) and NetBox's inventory, a builder's query read back before running, with the same
bounds. 11.12 maps each feature to the course's patterns (Analyst, Translator, Decision-maker).

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
| Model tiers | small by default (Claude Haiku 5.5); medium (Claude Sonnet 5.5) only where the eval shows the small tier misses its target; large (Claude Opus 5.5) never by default; **exact model versions pinned, and any model change re-runs the full eval suite** (decided 2026-10-13); Anthropic first behind the provider-agnostic client; the built-in local model (section 10) offered beside it, only where it passed the eval, its score shown beside the hosted one | the smallest that meets the target |
| Evals | at least 30 golden cases per feature before observe mode; labelled replayed or synthesised cases allowed, with **at least 10 real cases per feature** (decided 2026-10-13); a prompt or model change merges only when the live score stays at or above target | measured, not argued |
| Observe mode | at least 30 days AND the card's minimum uses (50 for frequent features, 20 for rare) | enough uses to measure a rate |
| Kill | below the card's floor after its uses, or cost per accepted output above 2× budget, or (for features 4 and 7) one out-of-scope result reaching execution or confirm | removed, not left running |
| Respond (deterministic) | a class is enabled only at a false-positive rate of 1% or less over at least 30 days and 100 "would have fixed" events; grace period 2 readings and 15 minutes; at most 6 fixes an hour per network and 1 per device per hour; the same deviation fixed twice in 24 hours halts its policy. **Lab-only drift drills** feed observe mode: deliberate, known deviations on non-critical devices, each labelled a drill and never counted as production evidence (decided 2026-10-13) | the rails of IBN_DESIGN section 3 |
| AI catalog selection (decision 9: yes, observe mode first) | at least 95% MEASURED agreement with a person over at least 100 observed selections before the tier is enabled; no self-reported confidence gate: confidence is logged for analysis only and never decides (decided 2026-10-13) | stricter than the deterministic classes |
| Activate | a canary soaks 30 minutes with its verifiers holding before the fleet; one device at a time after it | rotation's pattern |
| Context budgets | the measured minimum times 1.5 | headroom without waste |
| Consistency (11.1; N DECIDED, the floors PROPOSED) | each golden case run 5 times (a profile setting); the release gate's floor 95% consistent cases for Translator features, 90% for Analyst and Decision-maker | a translation that differs between runs is a different change; the floor is measured per model, never assumed from temperature (11.11) |
| The built-in model (PROPOSED, section 10) | a tier is admitted only if, with the model loaded at its profile's context, MemAvailable stays at or above 20% of the host's RAM (3.2 GiB on a 16 GiB host); the profile's context 8k tokens by default; CPU capped at all but one vCPU; one request at a time; unloaded after 10 minutes idle; cost per token zero, so the caps that bind are the latency budget and the one-at-a-time rule | the stack's measured swing over nine days was about 1.2 GiB (lowest 10.4 GiB available, highest daily mean 11.7 GiB), so a 20% reserve covers it about 2.6 times; the 8k context keeps the KV cache under 0.5 GiB on gpt-oss-20b (estimate, 10.8) |

## 8. Process

- **Voice never approves** (11.6, decided 2026-10-15): a voice request may query and ask; a
  change it asks for waits at the GUI's confirm by hash.
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
   (Answered 2026-10-14: a built-in local model ships with Mercury; section 10.)
7. **The ranking:** which of section 6's candidates proceed to boards and cards first
   (proposed: 1 and 2, in 8.1).
8. **The CLAUDE.md block:** paste it (the operator's file), or change it.
9. **The owner of each feature.**
10. **The built-in model's origin** (section 10.2).
11. **The multi-model design rule** (section 10.3).
12. **The built-in local model's proposals (section 10):** the engine, model delivery, the
    hardware tiers, reliability, isolation and the release gate, each marked PROPOSED there.
13. **The licence of each candidate model** (a new third-party licence is the operator's):
    gpt-oss-20b and Granite 4.0 are published under Apache-2.0; Gemma 4's terms are to be read
    from Google's release before it is offered.
14. **Section 11's PROPOSED additions:** 11.4 (few-shot clarification and refusal examples),
    11.5 (the review-gated feedback loop), 11.8 (the gateway's rate limits, busy state and
    parse-failure rate), 11.9 (feature 1 over records and inventory), 11.11 (temperature per
    model profile), 11.12 (the patterns table, the three placements the operator did not make,
    and the departures); and 11.1's floor numbers (95% Translator, 90% the others).

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

### Decided, 2026-10-14 (the operator)

| # | Decision |
|---|---|
| 6 (amended) | **A free local model ships with Mercury** ("Local (built-in)"), so AI works out of the box and offline, beside the paid providers; it replaces "a local model optional, later" (section 10). |
| 10 | **Model origin: US-only, operator's decision.** The built-in model's candidates are gpt-oss-20b (OpenAI), Gemma 4 26B MoE and Gemma 4 E4B (Google), Granite 4.0-H-Tiny and Granite 4.0-H-Small (IBM). No other origin is offered, and there is no setting to add one (section 10.2). |
| 11 | **The multi-model design rule:** one definition of every tool and one prompt structure for all models; an adapter per API shape (Anthropic Messages; OpenAI-compatible), never per model; per-model differences in a profile (data); no per-model prompt forks; no third-party multi-LLM abstraction library; a curated list of only the models that passed the eval (section 10.3). |

### Decided, 2026-10-15 (the operator)

From re-reading the course material (weeks 8 and 9) against this plan; each written in section 11
with the test that will enforce it.

| # | Decision |
|---|---|
| 11.1 | **Consistency eval:** each golden case runs N times (default 5, a profile setting), scored on identical structured output; a consistency rate per feature and model, with a floor in the release gate (the numbers proposed in 11.1); recorded responses in CI, live on the host. |
| 11.2 | **Deterministic ambiguity:** every reference in a structured output resolved by code against NetBox and intent; zero or several matches, code asks, whatever the model returned; the model's flag additive, never the safeguard. |
| 11.3 | **Field provenance:** every translation schema marks each field stated (with its words) or inferred; the read-back highlights the inferred fields before confirm. |
| 11.6 | **Voice never approves:** voice may query and request; approval is only the GUI's confirm by hash (IBN_DESIGN section 8 step 1, and section 13 item 9: speaker spoofing). |
| 11.7 | **Input normalisation before any prompt,** on the operator's text and retrieved data: NFKC; zero-width, bidirectional-override and control characters stripped; length caps per block; each removal flagged in the audit log; tested with planted hidden-instruction strings. |
| 11.10 | **Context freshness:** each translation records the NetBox and intent versions it used; at confirm, if either changed, validation re-runs before anything applies. |

**Noted 2026-10-14 (Lab 7):** the function-coverage report (`scripts/nmas-coverage`: per
automation module, unit and all-tier function coverage with line and branch beside it, and the
tests that reach each function) has no GUI page; it lives in the CLI, the Actions job summary
and an HTML artifact. It is a candidate tile for the Toolbox (C762) later, reading the last CI
run's report, not running the suite.

**Noted 2026-10-13 (the operator, with D15's removal):** today's Approvals screen leaves with the
AI family; a drift row points to its own Capture and Deploy (C739), and `approval_queue` stays
internally. **The AI change-request queue (8.0) therefore needs its own approvals view,
designed fresh then** (a board first), not today's screen revived.

The rest of IBN_DESIGN section 9, decided the same day: per-policy authority yes; auto-fix
only management-plane configuration (logging hosts, SNMP, NTP, IP SLA probes), never routing,
interface state, ACLs, AAA or credentials, or s3 and the management path; Translate's first
scope management-plane services; Batfish for routing-affecting changes, Mercury's IOS checks
kept; Loki's severity label and a stable trap label as a host step; history on E18, which
becomes an 8.0 prerequisite; voice deferred.

## 10. The built-in local model (added 2026-10-14)

**The operator's addition, 2026-10-14:** a free local model ships with Mercury, so AI works out of
the box and offline, beside the paid providers. Every rule in sections 2 to 4 applies to it
unchanged: the same features, cards, role-bound tools, masking, injection defences, red-team gate
and records. The model never changes permissions. Offline parity (non-negotiable 3) still holds:
with AI off, every workflow works. Each item below is marked **DECIDED** (the operator's, section
9) or **PROPOSED** (pending the operator, section 9 decision 12).

### 10.1 What the built-in model is for

A model that runs on the NMAS host itself, with no account, no per-token cost and no egress after
its file is in place. It is offered as "Local (built-in)" in the gateway's provider list, through
the same OpenAI-compatible adapter as a hosted OpenAI-compatible provider (10.3).

### 10.2 Model origin (DECIDED, the operator, 2026-10-14)

- **Model origin: US-only, operator's decision.**
- The candidates: gpt-oss-20b (OpenAI); Gemma 4 26B MoE and Gemma 4 E4B (Google); Granite
  4.0-H-Tiny and Granite 4.0-H-Small (IBM).
- No other origin is offered, and there is no setting to add one.
- Each catalog entry carries an `origin` field; the wizard lists only entries whose `origin` is
  `"US"` (test 1, 10.9).
- *PROPOSED:* the pinned file comes from the model publisher's own release where one exists. A
  quantisation made by someone else is a different artefact, and its entry names who made it.

### 10.3 The multi-model design rule (DECIDED, the operator, 2026-10-14)

- **One definition of every tool:** a JSON Schema with its role binding (`TOOLS_BY_ROLE`,
  IBN_DESIGN section 12), in one registry. **One prompt structure for all models** (IBN_DESIGN
  section 10: role, task, rules, output contract, tagged data blocks).
- **An adapter per API shape, never per model:**
  - Anthropic Messages;
  - OpenAI-compatible: OpenAI, Gemini's OpenAI-compatible endpoint, and llama.cpp's
    `llama-server` (the built-in model).
- **Per-model differences live in a profile, which is data:** the adapter, the context budget,
  strict-schema support, parallel tool calls, the maximum tools per request, reasoning settings,
  cost, and origin.
- **No per-model prompt forks.** A model that fails the eval with the shared prompt gets fewer
  features, not its own prompt.
- **No third-party multi-LLM abstraction library.** The two adapters are Mercury's own, and
  auditable.
- **The supported model list is curated:** only models that passed the eval (10.7) are offered.
- Every adapter imports tools and prompts from the one registry (test 2, 10.9).

### 10.4 The engine and model delivery (PROPOSED, pending the operator)

- **Engine:** llama.cpp's `llama-server`, as its own service or container, bound to 127.0.0.1,
  with no egress. Mercury reaches it through the OpenAI-compatible adapter as "Local (built-in)".
- **Model delivery:** a model file is never in the repository or an image. The first-run wizard
  either:
  - downloads a pinned file and checks its sha256 (and the publisher's `model.sig` for Granite);
    or
  - imports a file the operator supplies, for an air-gapped install, with the same checks.

  After that Mercury is fully offline. The download is the only network call, made by the
  operator's action in the wizard.

### 10.5 Hardware tiers, chosen by the wizard's hardware check (PROPOSED)

The wizard measures free RAM (MemAvailable with the whole stack running), the CPU's features
(AVX2, AVX-512, AMX) and its speed (a 30-second test of prompt and generation tokens per second),
then offers one tier:

| Tier | Candidates | Admitted when |
|---|---|---|
| Large | gpt-oss-20b (file about 13 GB), Gemma 4 26B MoE (about 16 GB), Granite 4.0-H-Small | the model's resident size, its KV cache at the profile's context and the server's own buffers fit, leaving the stack its reserve (section 7) |
| Small | Gemma 4 E4B, Granite 4.0-H-Tiny | the same test, for the smaller file |
| AI off | none | nothing fits; the wizard shows the measured numbers and the reason |

If no small-tier candidate passes the eval, the small tier is "AI off" with the reason shown,
never a weaker model.

### 10.6 Reliability, isolation and the release gate (PROPOSED)

- **Every tool call by JSON-schema constrained decoding** (`llama-server`'s grammar from the
  tool's schema), so a call that parses is a call that fits the schema.
- **Mercury preselects the tools for each request**, up to the profile's `max_tools`, from the
  role's tools (never widening them).
- **A context budget from the profile**, filled by 8.0's context selector (IBN_DESIGN section 8,
  step 2; it does not exist yet: the removed AI family's context code is not carried forward).
- **Isolation:** CPU and memory caps on the service; one request at a time (a second is refused
  by name, naming the request that holds it); the model unloaded when idle. It must never starve
  Loki, Prometheus or Mercury.
- **The release gate, per model and version:** Mercury's own task evaluation (10.7) plus the
  red-team set (IBN_DESIGN section 13, any non-zero result blocks). A feature card turns on for a
  model only where that model passed that feature's cases, including the card's latency budget.
  The eval result picks the local default.

### 10.7 The evaluation (PROPOSED)

Task cases are built from Mercury's real tools and data:
1. parse show output;
2. explain a drift;
3. choose the right tool;
4. refuse an out-of-role change;
5. translate an intent into a catalog entry;
6. decline to call a tool when none applies.

They run against every candidate on the NMAS host's real hardware, through `llama-server`, at Q4,
and against each paid model offered. Results are stored per model and version, so a vendor's
model update re-runs them (section 7: any model change re-runs the full suite). In CI they run on
recorded responses, as every eval does (section 4).

### 10.8 The lab's NMAS host, measured 2026-10-14 (read-only)

- **The host:** 4 vCPUs (a Haswell-generation Xeon: AVX2, FMA and F16C; no AVX-512, no
  AVX-VNNI, no AMX); 15.6 GiB RAM; 3.8 GiB swap, unused.
- **Free RAM with the whole stack running:** MemAvailable 11.3 GiB at 19:58 and 20:00 UTC. Over
  nine days of 10-minute samples (sysstat, 6 to 14 October): lowest 10.4 GiB, daily means 10.9
  to 11.7 GiB. CPU 15 to 19% busy on average, with no busy hour in the 10-minute averages.
- **Today it fits the small tier only** (estimated: a small model's file, about 4 to 5 GB, plus
  about 1 GiB of server and KV cache, inside about 7 GiB of usable headroom). The large tier needs
  the VM at 32 GiB.
- **Speed is unmeasured.** An order-of-magnitude estimate for 4 Haswell cores puts a 3,000-token
  prompt at minutes on the large tier, and tens of seconds on the small one. That misses section
  6's latency budgets (3 to 5 s) by a wide margin; the wizard's speed test settles it.
- **The hypervisor** (the same CPU generation, so no AMX anywhere in the lab) has 125.8 GiB of
  RAM. Its peak use over the week was 71.4 GiB. But the running guests' configured memory is
  98.5 GiB, plus an 8 GiB ZFS cache. Adding 16 GiB to the NMAS VM would bring that to 122.5 GiB,
  which is safe only while the stopped guests stay stopped, or with the lab VM's 80 GiB
  allocation lowered (it peaked at 41 GiB). That is the operator's capacity decision.
- **A single-node twin and the model share the same RAM** on a one-host install. A C8000v twin
  (about 4 GiB, IBN_DESIGN section 9) and a large-tier model do not both fit in 16 GiB. With a
  small-tier model loaded (about 5 to 6 GiB), a C8000v twin no longer fits beside it either
  (about 7 GiB usable). A vIOS twin (about 0.4 GiB) does. Until the RAM grows, the two take
  turns: the model is unloaded while a twin runs.

### 10.9 The build's required tests (named now; written with the code)

Neither the model catalog nor the tool registry exists yet, so neither test can be written yet.
Each is a required test of the 8.0 build, and must be shown able to fail:

1. **`tests/test_model_catalog_origin.py`:** every entry in the wizard's model catalog has
   `origin == "US"`, and the wizard lists only those. Planted case: a catalog entry with another
   origin fails the test. A population floor: the catalog has at least the five candidates in
   10.2.
2. **`tests/test_one_tool_registry.py`:** no tool or prompt is defined per model. Every adapter
   imports its tool definitions and prompts from the one registry. Checked by parsing the
   adapters and profiles: no tool schema, tool name list or prompt text defined in an adapter
   module or a profile, and no profile key naming a prompt. A profile holds only the fields in
   10.3. Planted case: a tool schema defined inside an adapter fails it.

Section 11 names the required tests of its additions, each in this form, beside the addition it
enforces.

## 11. Additions from the course re-read (2026-10-15)

**The operator, 2026-10-15:** twelve additions from re-reading the operator's course material on
AI in networking (weeks 8 and 9) against this plan and IBN_DESIGN. Documents only; nothing is
built. Each is marked **DECIDED** (the operator's, 2026-10-15) or **PROPOSED** (pending the
operator, section 9), and names the test that enforces it once built, in 10.9's form: written
with the code, shown able to fail, with a planted case. IBN_DESIGN points here where its text
touches an addition (sections 8, 10 and 13), so each rule has one home.

### 11.1 Consistency eval (DECIDED)

- Each golden case runs **N times** (default 5; N is a profile setting, 10.3), and the runs are
  compared on their **structured output**, canonicalised (key order, whitespace, list order where
  the schema declares a field unordered). Free-text fields (a cause sentence, a summary) are not
  compared; the fields a decision reads are.
- A case is **consistent** when all N structured outputs are identical. The **consistency rate**
  is consistent cases over cases, per feature and per model and version, stored with the eval's
  other results (10.7).
- **The floor in the release gate (PROPOSED numbers):** 95% for Translator features (11.12:
  natural language → query, natural language → intent), where a different output is a different
  change or a different answer; 90% for Analyst and Decision-maker features. A feature turns on
  for a model only where that model meets the floor, beside its accuracy target (section 6) and
  the red-team gate.
- **Recorded responses in CI** (all N per case, so CI scores consistency offline); **live on the
  host** as a job, as every eval runs (section 4). N times the live cost is counted on the cost
  dashboard as eval cost, apart from use.
- **Enforced by `tests/test_consistency_eval.py`:** the scorer marks a case consistent only when
  all N canonical outputs match; a feature below its floor is refused for that model by the
  release gate. Planted case: a recorded case whose fifth run differs in one decision field is
  inconsistent and drops the rate below the floor; a run differing only in a free-text field
  stays consistent. Population floor: every feature with a card has N recorded runs per case.

### 11.2 Deterministic ambiguity (DECIDED)

- **Every reference in a structured output** (a device, interface, site, role, VLAN, prefix, peer)
  is resolved by code against NetBox and the committed intent, never taken from the model.
- **Zero matches or several matches:** code asks the clarifying question (naming the reference
  and, for several, each candidate), whatever the model returned, including a model that set no
  ambiguity flag.
- **The model's ambiguity flag** (`{"error": "ambiguous", ...}`, section 4) is additive: it can
  raise a question code would not, never suppress one. It is not the safeguard.
- **Enforced by `tests/test_ambiguity_is_resolved_by_code.py`:** for each translation schema, a
  recorded output naming a reference that matches no NetBox object, and one matching two, each
  yield code's clarifying question though the recorded model output says it is unambiguous; a
  reference matching exactly one passes. Planted case: the resolver taught to trust the model's
  flag lets the two-match output through, and the test fails.

### 11.3 Field provenance (DECIDED)

- **Every translation schema marks each field `stated` or `inferred`**, a `stated` field carrying
  the words of the operator's request it came from (`source_words`).
- **The deterministic read-back (IBN_DESIGN section 8, step 5) highlights every inferred field**
  before confirm, so a person sees what the request did not say.
- *PROPOSED detail:* a field marked `stated` whose `source_words` do not occur in the request (after
  11.7's normalisation) is shown as inferred, by code; the model's marking is never trusted
  alone.
- **Enforced by `tests/test_translation_provenance.py`:** every translation schema's every leaf
  field has its provenance; the read-back marks each inferred field; a `stated` field whose words
  are absent from the request is drawn as inferred. Planted cases: a schema field without
  provenance fails the schema scan; a read-back that drops the inferred mark fails.

### 11.4 Few-shot includes clarification and refusal (PROPOSED)

- Every translation prompt's 2 or 3 examples (section 4) include **1 or 2 that end in the error
  contract**: a clarifying question (`{"error": "ambiguous", "clarification_needed": "..."}`)
  and a refusal (`{"error": "could not parse"}`, or a request outside the person's role), not
  only successful commits. The examples come from real history where it holds such a case;
  otherwise from the eval's labelled cases, marked as such.
- **Enforced by `tests/test_few_shot_carries_the_error_contract.py`:** every translation prompt in
  `prompts/` holds at least one success example and at least one error-contract example, each
  valid against the feature's schema. Planted case: a prompt with only successful examples fails.

### 11.5 A review-gated feedback loop (PROPOSED)

- **Accepted translations join the example pool only after a person's review** (who reviewed,
  when, which version of the pool).
- **Declined or edited translations become eval cases**: the request, the model's output, and the
  person's correction as the expected output, labelled with the reason.
- **Answers to clarifying questions are recorded** with the question and the translation that
  followed.
- **Everything is versioned:** the example pool and the eval set are files under version
  control, changed by commits. **Nothing enters a prompt automatically**; a prompt changes only
  by a reviewed commit, gated by its evals (IBN_DESIGN section 10).
- **Enforced by `tests/test_feedback_loop_is_review_gated.py`:** an accepted translation without a
  review record never appears in the example pool; a declined one appears in the eval set with
  its correction; the prompt builder reads only the committed pool. Planted case: an
  auto-append of an unreviewed translation to the pool fails.

### 11.6 Voice never approves (DECIDED)

- **Voice may query and request** (IBN_DESIGN section 8, step 1, the later input layer). **It never
  approves:** approval is only the GUI's confirm by hash (non-negotiable 5). A spoken read-back
  informs; it does not approve.
- **The threat it answers:** speaker spoofing (a recorded, synthesised or replayed voice). Voice
  identifies no one; the request still runs as the authenticated session that carries it, and a
  change it asks for waits at the GUI's confirm (IBN_DESIGN section 13, item 9).
- **Enforced by `tests/test_voice_never_approves.py`:** every confirm- and approve-gated route
  (`modules/route_gates.py`) refuses a request marked as voice-originated, naming the channel;
  the voice adapter's route table holds no confirm or approve route. Planted case: a
  voice-marked request to a confirm route that is accepted fails the test.

### 11.7 Input normalisation before any prompt (DECIDED)

- **On the operator's text and on retrieved data**, before either reaches a prompt:
  1. Unicode NFKC;
  2. strip zero-width, bidirectional-override and control characters (Unicode categories Cf
     and Cc, except newline and tab; Cf includes the tag characters U+E0000 to U+E007F, which
     can carry invisible text);
  3. a length cap per block (per feature, in its card);
  4. **each removal flagged in the audit log**: which block, which characters by code point and
     count, and whether a cap cut it, never silently.
- Masking (IBN_DESIGN section 10) runs after normalisation, so a secret split by an invisible
  character is still found.
- **Enforced by `tests/test_prompt_input_normalised.py`** with planted hidden-instruction
  strings: "ignore previous instructions" interleaved with zero-width joiners; a right-to-left
  override reversing a command; the same instruction in tag characters; fullwidth letters NFKC
  folds; and an over-cap block. Each reaches the prompt normalised, each removal is in the audit
  log, and the masked secret split by a zero-width space is masked. Planted case: the strip
  step removed, the zero-width string reaches the prompt intact and the test fails.

### 11.8 The gateway's load and failure handling (PROPOSED)

- **Provider rate limits:** on HTTP 429, back off as the provider's `retry-after` says (else
  exponential, bounded by the feature's latency budget); a bounded queue per provider; a
  per-feature concurrency limit. A request past its budget stops and says so (section 4's
  capped loops).
- **A visible "AI busy" or "AI degraded" state** wherever AI appears, naming the cause (queued
  behind N requests, rate-limited until a time, the provider not answering) and saying that the
  workflow continues without AI (non-negotiable 3).
- **The parse-failure rate per feature and per model** on the cost dashboard, beside tokens and
  cost.
- **Enforced by `tests/test_gateway_backs_off.py`:** a recorded 429 with `retry-after` is waited
  out and retried within the budget, then refused by name past it; the queue's bound refuses the
  next request naming the queue; and `tests/test_ai_state_is_drawn.py`: the busy and degraded
  states are drawn with their cause. Planted case: a retry that ignores `retry-after` fails.

### 11.9 Feature 1 extended to Mercury's records and NetBox inventory (PROPOSED)

- Natural language → **a builder's query, read back before running**, also over Mercury's records
  (changes, rotations, approvals, on E18's database) and NetBox's inventory. Same pattern as
  feature 1 (section 6): the AI turns a sentence into a deterministic builder's own query model,
  never free query text; the builder reads it back; a person runs it.
- **Same bounds:** read-only endpoints, a range and row limit, a timeout, masking on every result
  (the operator's bounds for Code mode, 2026-10-15, C817).
- *Deterministic first:* a records builder and an inventory builder exist before the AI front of
  them (section 2, rule 2).
- **Enforced by feature 1's own tests, extended:** every query the AI path produces is one the
  builder's own model can hold and reads back; no AI path sends text the builder did not build.
  Planted case: an AI output carrying raw SQL or a free filter string is refused by the builder's
  model.

### 11.10 Context freshness (DECIDED)

- **Each translation records the versions of the data it used:** the config repository's commit
  for the committed intent it read, and a digest of the NetBox objects it read (their ids and
  `last_updated`).
- **At confirm:** if either changed since the translation, **validation (IBN_DESIGN section 8, step
  4) re-runs before anything applies.** Confirm by hash pins the artifact, not its facts. A
  validation that now fails refuses the confirm, naming what changed (both versions); one that
  still passes proceeds, and the record says it re-ran.
- **Enforced by `tests/test_translation_context_freshness.py`:** a NetBox object changed between
  preview and confirm makes validation re-run (observed), and a reference the change invalidated
  refuses the confirm naming both versions; unchanged facts skip the re-run. Planted case:
  confirm that skips the version comparison applies over changed facts and the test fails.

### 11.11 Temperature is a per-model profile setting (PROPOSED)

- **Temperature is a field of the model's profile** (10.3's per-model differences), per feature
  where a feature needs its own.
- **Consistency (11.1) is what is measured; it is never assumed from temperature.** A low
  temperature that still gives inconsistent output fails the floor like any other.
- **Enforced by `tests/test_one_tool_registry.py`** (10.9, test 2), extended: temperature is read
  only from the profile, never set in a prompt or an adapter; and 11.1's test, which gates on the
  measured rate whatever the temperature. Planted case: a temperature hard-coded in an adapter
  fails.

### 11.12 The course's three patterns, and deliberate departures (PROPOSED)

**Section 6's features by the course's patterns** (the operator's placement; *proposed* for the
three the operator did not place):

| Pattern | Features (section 6's rank) | What it means here |
|---|---|---|
| **Analyst** (reads, explains, proposes; a person decides) | 2 alert correlation; 5 root cause; 3 incident drafts; 8 verifier drafts; *proposed:* 6 a pipeline check after an escape, 9 inferring higher-level intent | output is evidence-linked text and drafts; nothing acts |
| **Translator** (words → a structure deterministic code checks) | 7 natural language → intent (8.5); 1 natural language → query (and 11.9); *proposed:* 10 a template draft for a new platform (accepted only by round trip) | output is a schema-constrained structure, read back, validated, confirmed by hash |
| **Decision-maker** (chooses among pre-approved options) | 4 catalog selection, in observe mode | chooses only inside the catalog; enabled only on measured agreement (section 7), never on confidence |

**Deliberate departures from the course examples, each with its reason:**

| The course example | Mercury | Why |
|---|---|---|
| A confidence threshold gates an action | **confidence logged, never a gate** | self-reported confidence is uncalibrated; agreement is measured instead (section 7, decided 2026-10-13) |
| "Return only JSON" in the prompt | **constrained decoding** (the provider's structured output or tool schema; `llama-server`'s grammar, 10.6) | an instruction can be ignored; a schema-constrained decoder cannot emit what does not parse |
| A y/n prompt to approve | **confirm by hash** in the GUI | a y/n approves whatever is current; a hash approves exactly the previewed artifact (IBN_DESIGN section 8, step 5) |
| Jenkins runs the pipeline | **GitHub Actions** | Jenkins was removed in P.4; the config repository's workflow is the pipeline |

- **Enforced by `tests/test_feature_cards.py`:** every card in section 6 names its pattern; a
  Decision-maker card carries an observe threshold measured by agreement and no confidence gate;
  and `tests/test_confidence_is_never_a_gate.py`: no gateway, validator or policy code branches
  on `confidence` (by parsing). The other departures are held by tests that exist:
  confirm by hash by `tests/test_preview_confirm.py` and `tests/test_deploy_contract.py`;
  Jenkins' absence by `tests/test_no_jenkins.py`; constrained decoding by 8.0's adapter tests
  (every call passes a schema). Planted cases: a card with no pattern; an `if confidence` in a
  validator.
