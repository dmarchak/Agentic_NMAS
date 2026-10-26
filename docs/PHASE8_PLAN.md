# Phase 8: AI, in service of an intent-based network (a plan; not built)

**2026-10-20 (the operator): Phase 8's first release is pulled forward,** before Core 1.0's
sign-off, on Anthropic only, to a feature freeze around 11-20. Its scope and order are
docs/AI_ANTHROPIC_PLAN.md, NSOT_PLAN section 9 records the decision and its consequences, and
section 14 below is the endpoint direction after it.

**2026-10-24 (the operator): the amendments of section 15.** Closed-loop execution leaves Phase 8
for Phase 9, the closed loop (15.2); Anthropic is the proof of concept (15.3); Pydantic v2 strict
is the one schema tool for AI input and output (15.4); runbooks are minimal declarative YAML
(15.5); analysis is a button until its cost is measured (15.6); three new feature cards (15.9);
data leaving the host in three classes, configuration off per network until an admin enables
it (15.11).

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
   *Added 2026-10-16 (the operator): **offline-first.** Every AI feature also works fully on the
   local profile with no network, and a cloud model is never a dependency (section 12).*
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
     `identity.identify`); *2026-10-16: offline, from the instance's own Keycloak, by the
     operator's decision (section 12.5, gap 9);*
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
| Industry need (the operator, 2026-10-25; a standing principle, MERCURY_CHARTER "The test for every feature") | the problem network engineers have; how established commercial tools address it; how Mercury meets or improves on it at enterprise scale. A feature without a stated industry need is questioned before it is built |
| Deterministic alternative | the rule, query, template or builder considered, and why it falls short |
| Inputs | the exact context, sized in tokens (the measured minimum, section 4); the tools (read-only, bounded); the output schema (Pydantic, versioned) |
| Success metric | a target (accepted-without-edit rate, time saved, findings confirmed true) and the eval set that measures it |
| Compared fields | the structured fields its consistency eval compares across N runs (11.1), never prose; and its pattern (11.12), which sets the floor: 95% Translator and Decision-maker, 90% Analyst (the operator, 2026-10-15) |
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
  `{"error": "ambiguous", "clarification_needed": "…"}`, surfaced to the operator; 1 or 2 of
  the examples end in that contract (a clarifying question, a refusal), not only successful
  commits (11.4, decided 2026-10-15).
- **Added 2026-10-15 (section 11, all decided):** consistency measured over N runs on each
  card's compared fields (11.1); ambiguity decided by code (11.2); field provenance in every
  translation schema (11.3); a review-gated feedback loop (11.5); the gateway's rate limits and
  busy state (11.8); temperature per model profile (11.11); input normalised before
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
| **8.0 Foundations** (no user-facing AI; **E18, the records database, is its prerequisite**, decision 8). ***Amended 2026-10-18 (the operator, section 13.2):* 8.0 shrinks to what feature 1 needs end to end; each other piece below arrives with the first feature that needs it. Whether feature 1 needs E18 is reported in 13.2, not decided.** | roles from sign-in and `TOOLS_BY_ROLE` (IBN_DESIGN section 12), every tool bound on behalf of the asking person and filtered to their scope; the change-request queue and its board (viewer asks → flagged → filed → approver's queue → approve or decline); the security row for repeated or injection-like attempts; separation of duties per network; the gateway (provider-agnostic, Anthropic first, exact model versions pinned; a per-network switch, cost caps; the built-in local model behind the same gateway, section 10; *2026-10-16, offline-first: the local profile first and required, a hosted provider optional, section 12*); the prompt registry; the schema library; the MCP tool server; tracing (OpenTelemetry GenAI conventions); masking through C733's index (C745's shapes closed first); the eval harness (recorded in CI, live on the host) with a golden dataset from real lab incidents; the cost dashboard | the red-team set (IBN_DESIGN section 13: "I'm an admin", "ignore previous instructions", role-play, data-borne injections, link exfiltration) passes with zero unauthorised tool calls, proposals and external links, recorded in CI and live on the host; every tool re-checks `may` as the person and a denial is audited (shown by test); a viewer's session holds no `propose_*` tool and a misclassified change still changes nothing (shown by test); every tool call recorded as the asking person; no tool approves or reveals; the gateway refuses at a cap; masking shown on planted secrets of every shape; every tool read-only but `propose_*` (shown by test); a recorded and a live eval run end to end; the dashboard shows a test feature's cost per use |
| **8.1 Assure** | the deterministic verifier model and compliance status first (history on E18); then, where cards justify it, natural-language questions → PromQL or LogQL read back by the E3/F3 builder before running, and alert correlation over deterministically grouped alerts | the verifiers' statuses on the host match the readers'; each AI feature past its observe threshold, or killed |
| **8.2 Respond, observe** (***moved in part, 2026-10-18 (the operator):*** *the deterministic observe-mode part moves into Core 1.0's tail: the maintainer's "would have converged" records, the false-positive count per class, and lab-only drift drills labelled as drills (NSOT_PLAN section 9, "The path after Phase 7", item 3). What stays here is the AI part: root-cause proposals, incident drafts and drift classification. Enabling a class stays in 8.3.*) | the golden state rule's maintainer (IBN_DESIGN section 11): no baseline, no autonomy; convergence of the deviating lines only; the operational catalog; holds, windows and Capture-or-Revert for attributed drift; its state on Needs attention and each device page (a board first). All in observe mode ("would have converged"), on the deterministic policy engine (rotation's pattern). Plus AI root-cause proposals for novel deviations, approved by a person; incident record drafts; AI classification of deliberate vs unexplained drift, with evidence | each class's false-positive rate measured over its period; no convergence would have touched a secret line, the management path or routing; root-cause proposals' confirmed-true rate measured |
| **8.3 Respond, enabled per class** (***moved, 2026-10-24 (the operator, section 15.2):*** *closed-loop execution leaves Phase 8 for Phase 9, the closed loop, built when the first class or catalog entry meets its ruled bar on observed evidence; Phase 8 keeps observe-mode logging only*) | convergence and catalog classes enabled once observe mode meets the threshold; a verified action re-earns the baseline; AI selection only among actions that leave the golden state unchanged, if decision 9 is confirmed, after its own observe period | each enabled class within its rate and with no rail breached for its period |
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
| 10 | **Template draft for a new platform** (8.5; *2026-10-24, 15.11: requires the network's configuration class, its secret-bearing lines dropped*) | today a person writes it; accepted only by round trip | a platform's captured config and the nearest template, about 30k tokens → a template draft | 30k in, 6k out, 120 s | medium or large (the eval decides) | 50% pass the round trip within two revisions | 5 platforms | below 40%, or cost per accepted template above 3× budget |

**Each card's pattern and compared fields** (11.1, 11.12; the operator, 2026-10-15). The pattern
sets the consistency floor; the compared fields are what its N runs must agree on, never prose:

| Rank | Pattern (floor) | Compared fields |
|---|---|---|
| 1 | Translator (95%) | the builder's query model, whole (metric or stream, filters, operations, range) |
| 2 | Analyst (90%) | cause category, `evidence_refs`, `needs_human` |
| 3 | Analyst (90%) | `evidence_refs`, `needs_human` (finding, cause and fix are prose) |
| 4 | Decision-maker (95%) | `entry`, `params`, `evidence_refs` |
| 5 | Analyst (90%) | each cause's category, `tests_to_confirm`, `evidence_refs`, `needs_human` |
| 6 | Translator (95%) | `check_kind`, `rule`, `planted_case` (the artifact a deterministic test accepts) |
| 7 | Translator (95%) | the intent model, whole, or the error contract's kind |
| 8 | Analyst (90%) | the verifier's statement kind, the readers' fields it reads, its planted failing case's kind |
| 9 | Analyst (90%) | each proposed statement's kind and the devices it covers, `evidence_refs` |
| 10 | Translator (95%) | the template draft's rendered output on the platform's captured config (the round trip's input) |

Each card may refine its compared fields with its eval; the card scan (11.1's test) requires
them. Feature 1's pattern extends to Mercury's records (changes, rotations, approvals) and NetBox's
inventory: a builder's query read back before running, with the same bounds (11.9).

**Candidates 11 to 14** (added 2026-10-16, PROPOSED): document extraction, plain question to Tier
1 reads, what is wrong in plain words, and a playbook proposal at the kit, with their cards in
section 12.3. Every candidate, these and the ten above, must pass offline-first (section 12.1);
section 12.2 audits the ten.

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
| Model tiers | small by default (Claude Haiku 5.5); medium (Claude Sonnet 5.5) only where the eval shows the small tier misses its target; large (Claude Opus 5.5) never by default; **exact model versions pinned, and any model change re-runs the full eval suite** (decided 2026-10-13); Anthropic first behind the provider-agnostic client; the built-in local model (section 10) offered beside it, only where it passed the eval, its score shown beside the hosted one. *Amended 2026-10-16 (the operator, offline-first, section 12.1): every feature must pass on the local profile; a hosted tier is optional and may improve a result, never the only working path.* **Amended 2026-10-18 (the operator, section 13.1):** features are built and accepted on Anthropic, Haiku 5.5 by default and Sonnet 5.5 where the eval shows the need, exact versions pinned. The local profile is the release gate (Stage 10), never a build condition | the smallest that meets the target |
| Evals | at least 30 golden cases per feature before observe mode; labelled replayed or synthesised cases allowed, with **at least 10 real cases per feature** (decided 2026-10-13); a prompt or model change merges only when the live score stays at or above target | measured, not argued |
| Observe mode | at least 30 days AND the card's minimum uses (50 for frequent features, 20 for rare) | enough uses to measure a rate |
| Kill | below the card's floor after its uses, or cost per accepted output above 2× budget, or (for features 4 and 7) one out-of-scope result reaching execution or confirm | removed, not left running |
| Respond (deterministic) | a class is enabled only at a false-positive rate of 1% or less over at least 30 days and 100 "would have fixed" events; grace period 2 readings and 15 minutes; at most 6 fixes an hour per network and 1 per device per hour; the same deviation fixed twice in 24 hours halts its policy. **Lab-only drift drills** feed observe mode: deliberate, known deviations on non-critical devices, each labelled a drill and never counted as production evidence (decided 2026-10-13) | the rails of IBN_DESIGN section 3 |
| AI catalog selection (decision 9: yes, observe mode first) | at least 95% MEASURED agreement with a person over at least 100 observed selections before the tier is enabled; no self-reported confidence gate: confidence is logged for analysis only and never decides (decided 2026-10-13) | stricter than the deterministic classes |
| Activate | a canary soaks 30 minutes with its verifiers holding before the fleet; one device at a time after it | rotation's pattern |
| Context budgets | the measured minimum times 1.5 | headroom without waste |
| Consistency (11.1; decided 2026-10-15) | each golden case run 5 times (a profile setting), compared on the card's structured fields, never prose; the release gate's floor 95% consistent cases for Translator and Decision-maker features, 90% for Analyst features | a Translator's different output is a different change; an inconsistent catalog pick is a different remediation; the floor is measured per model, never assumed from temperature (11.11) |
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
14. ~~Section 11's proposed additions and 11.1's floors.~~ **Closed 2026-10-15:** every one
    decided, as written, with the floors and placements the operator ruled ("Decided,
    2026-10-15" below).
15. **11.3's proposed detail:** a field marked `stated` whose words do not occur in the request
    is drawn as inferred, by code.
16. **Section 12 (added 2026-10-16):**
    - what each feature failing offline-first needs (12.2);
    - candidates 11 to 14, their cards and ranking (12.3);
    - the grounding design (12.4);
    - the resolutions of gaps 1 to 8 (12.5);
    - the reading that 12.1 decides 10.4's engine (gap 10);
    - the stricter reading of "never a dependency" for a host that admits no local tier (12.1).

    **APPROVED by the operator, 2026-10-16, with one change to 12.1:**
    - A host that cannot run a local model has AI off BY DEFAULT.
    - An installation setting may allow hosted-only AI, set by an admin with a recorded reason.
    - A network carrying a classification marking forces it off with no override (planned,
      not built: C1720).

    Item 1's consequences are accepted:
    - the gateway becomes local-first, with hosted adapters optional and off unless configured;
    - time budgets are re-derived from local measurement;
    - a feature that does not fit the local profile's context is split or not built, never
      offered hosted-only.

    Gap 10 is confirmed: `llama-server` is the engine.

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

**The operator's rulings on 1705edfc, the same day** (closing decision 14):

| # | Decision |
|---|---|
| 11.1 (floors) | **Translator and Decision-maker features: 95%** (catalog selection picks an action that runs, so an inconsistent pick is a different remediation). **Analyst features: 90%, on the structured fields only** (for example cause category, `evidence_refs`, `needs_human`), never prose. **The compared fields are part of each card** (section 3; section 6 names them), and `tests/test_consistency_eval.py` carries the planted case of two runs with different prose and identical structured fields scoring consistent. |
| 11.12 (placements) | **Feature 6** (a pipeline check after an escape) **is Translator:** it produces an artifact accepted only by a deterministic test, like template drafts. **Feature 9 is Analyst. Feature 10 is Translator.** |
| 11.4 | **Few-shot includes 1 or 2 clarification and refusal examples** in the error contract: decided as written. |
| 11.5 | **The review-gated feedback loop:** decided as written. |
| 11.8 | **The gateway's rate-limit handling, busy or degraded state and parse-failure rate:** decided as written. |
| 11.9 | **Feature 1 over Mercury's records and NetBox inventory:** decided as written. |
| 11.11 | **Temperature a per-model profile setting; consistency measured, never assumed:** decided as written. |
| 11.12 | **The patterns table and the deliberate departures:** decided as written, with the placements above. |

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

*Note, 2026-10-16:* the operator's offline-first rule names `llama-server` as the local profile
(section 12.1). That reading decides the engine; the operator is to confirm it (section 12.5, gap
10). The delivery below stays PROPOSED. A kit has only the import path.

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

*Note, 2026-10-18 (the operator):* the installation's tiers are the charter's: Minimum (4 vCPU,
8 GiB), Standard (4 to 8 vCPU, 16 GiB) and Large (16 or more vCPU, 32 GiB or more). **The local
model belongs to Large.** The model tiers below are which model a Large host admits. A Minimum or
Standard host admits no local tier. It follows 12.1's rule for such a host: AI off by default,
and hosted AI allowed by an admin's recorded setting. Hosted AI adds no hardware.

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
built. **All twelve are DECIDED** (the operator, 2026-10-15: six with the additions, the other
six and 11.1's floors in their rulings on 1705edfc), and each names the test that enforces it
once built, in 10.9's form: written with the code, shown able to fail, with a planted case. One
detail stays proposed, marked where it stands (11.3's check of a stated field's words). IBN_DESIGN points here where its text
touches an addition (sections 8, 10 and 13), so each rule has one home.

### 11.1 Consistency eval (DECIDED)

- Each golden case runs **N times** (default 5; N is a profile setting, 10.3), and the runs are
  compared on their **structured fields**, canonicalised (key order, whitespace, list order where
  the schema declares a field unordered). **Prose is never compared** (a cause sentence, a
  summary, an incident's fix); only the fields a decision or a person's action reads.
- **The compared fields are part of each feature's card** (section 3's "Compared fields" row;
  section 6's table names them per feature). A card without them is incomplete, and its feature
  is not built.
- A case is **consistent** when all N runs' compared fields are identical. The **consistency
  rate** is consistent cases over cases, per feature and per model and version, stored with the
  eval's other results (10.7).
- **The floors in the release gate (decided, the operator, 2026-10-15):**
  - **Translator and Decision-maker features: 95%.** A Translator's different output is a
    different change, query or artifact; catalog selection picks an action that runs, so an
    inconsistent pick is a different remediation.
  - **Analyst features: 90%,** measured on the structured fields only (for example cause
    category, `evidence_refs`, `needs_human`), never on prose.

  A feature turns on for a model only where that model meets its floor, beside its accuracy
  target (section 6) and the red-team gate.
- **Recorded responses in CI** (all N per case, so CI scores consistency offline); **live on the
  host** as a job, as every eval runs (section 4). N times the live cost is counted on the cost
  dashboard as eval cost, apart from use.
- **Enforced by `tests/test_consistency_eval.py`:** the scorer compares only the card's compared
  fields and marks a case consistent only when all N canonical values match; a feature below its
  pattern's floor is refused for that model by the release gate; every card names its compared
  fields. Planted cases: (1) a recorded case whose fifth run differs in one compared field is
  inconsistent and drops the rate below the floor; (2) **two runs with different prose but
  identical structured fields score consistent** (the operator, 2026-10-15); (3) a card with no
  compared fields fails the card scan. Population floor: every feature with a card has N
  recorded runs per case.

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

### 11.4 Few-shot includes clarification and refusal (DECIDED)

- Every translation prompt's 2 or 3 examples (section 4) include **1 or 2 that end in the error
  contract**: a clarifying question (`{"error": "ambiguous", "clarification_needed": "..."}`)
  and a refusal (`{"error": "could not parse"}`, or a request outside the person's role), not
  only successful commits. The examples come from real history where it holds such a case;
  otherwise from the eval's labelled cases, marked as such.
- **Enforced by `tests/test_few_shot_carries_the_error_contract.py`:** every translation prompt in
  `prompts/` holds at least one success example and at least one error-contract example, each
  valid against the feature's schema. Planted case: a prompt with only successful examples fails.

### 11.5 A review-gated feedback loop (DECIDED)

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

### 11.8 The gateway's load and failure handling (DECIDED)

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

### 11.9 Feature 1 extended to Mercury's records and NetBox inventory (DECIDED)

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

### 11.11 Temperature is a per-model profile setting (DECIDED)

- **Temperature is a field of the model's profile** (10.3's per-model differences), per feature
  where a feature needs its own.
- **Consistency (11.1) is what is measured; it is never assumed from temperature.** A low
  temperature that still gives inconsistent output fails the floor like any other.
- **Enforced by `tests/test_one_tool_registry.py`** (10.9, test 2), extended: temperature is read
  only from the profile, never set in a prompt or an adapter; and 11.1's test, which gates on the
  measured rate whatever the temperature. Planted case: a temperature hard-coded in an adapter
  fails.

### 11.12 The course's three patterns, and deliberate departures (DECIDED)

**Section 6's features by the course's patterns** (the operator's placement, 2026-10-15; the
pattern sets the consistency floor, 11.1):

| Pattern (floor) | Features (section 6's rank) | What it means here |
|---|---|---|
| **Analyst** (90%; reads, explains, proposes; a person decides) | 2 alert correlation; 5 root cause; 3 incident drafts; 8 verifier drafts; 9 inferring higher-level intent | output is evidence-linked text and drafts; nothing acts |
| **Translator** (95%; words or evidence → an artifact deterministic code checks) | 7 natural language → intent (8.5); 1 natural language → query (and 11.9); 10 a template draft for a new platform (accepted only by round trip); 6 a pipeline check after an escape (accepted only by a deterministic test, like template drafts) | output is a schema-constrained structure or artifact, read back or tested, validated, confirmed by hash |
| **Decision-maker** (95%; chooses among pre-approved options) | 4 catalog selection, in observe mode | chooses only inside the catalog; enabled only on measured agreement (section 7), never on confidence |

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

## 12. Offline-first, and the disconnected operator assistant (the operator, 2026-10-16)

**The operator's request, 2026-10-16.** Documents only: nothing is built, no model was downloaded
and no device was touched. It sits here, after sections 10 and 11, because that is where this plan
adds a dated rule that crosses every feature; non-negotiable 3 (section 2) points here. No
existing section number moves.

**What is whose.** 12.1's rule and the requirements in 12.3, 12.4 and 12.7 are the operator's
words (**DECIDED**, 2026-10-16). Everything else here (the audit's needs, the four cards, the
gaps' resolutions, the numbers) was this plan's proposal. **The operator approved it on
2026-10-16 (decision 16, section 9), with one change to 12.1.** The numbers remain to be measured
(12.6) before any code, as section 9's rule requires. Gap 9 is answered by the operator's own
decision of 2026-10-16 (12.5).

**The six design notes it draws on**, all FUTURE and written 2026-10-16:
- [EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md) sets the case: a Mercury instance per fly-away
  kit, offline by design, run by minimally trained kit operators.
- [BRINGUP_FROM_DOCUMENTS.md](BRINGUP_FROM_DOCUMENTS.md) is the document extraction, and its
  section 16 names the gaps that 12.5 decides.
- [OFFLINE_OPERATION.md](OFFLINE_OPERATION.md) covers identity, updates and packages with no
  internet.
- [IPAM_IMPORT_DESIGN.md](IPAM_IMPORT_DESIGN.md) holds the staged plan that extracted values are
  compared with. Its only AI use is BRINGUP_FROM_DOCUMENTS section 15's optional column-mapping
  proposal, a headquarters use of feature 11's engine.
- [SITES_DESIGN.md](SITES_DESIGN.md) and [FLOWS_DESIGN.md](FLOWS_DESIGN.md) plan no AI feature.

Words used here, as in those notes: the **kit operator** is the person on site, **headquarters
NetOps** builds the standard every kit runs, and **the operator** is this project's.

### 12.1 The rule: offline-first is an acceptance rule for all of Phase 8 (DECIDED, the operator, 2026-10-16)

> **Amended 2026-10-18 (the operator; section 13.1): from a build rule to a RELEASE GATE.**
> Phase 8's features are built and accepted on Anthropic. Every feature must pass on the local
> profile before the public release (Stage 10), never before it is built. The rest of this
> section stands as the gate's content. The gateway stays provider-neutral, and the
> OpenAI-compatible adapter for `llama-server` stays in the design.

- **Every AI feature works fully with the local profile and no network.** The local profile is
  llama.cpp's `llama-server` reached through 10.3's OpenAI-compatible adapter, serving a US-origin
  model only (10.2). Its file is in place by 10.4's import path, and the server is bound to
  127.0.0.1 with no egress (10.4).
- **A cloud model is an optional profile that may improve a result.** It is never a dependency
  of the core path.
- **Each feature's tests run against the local profile.** CI calls no model (section 4), so this
  means two things:
  - each feature's recorded responses include runs recorded from a local-profile model;
  - its live evals on the host run through the local profile.
- **A feature whose only working path is a cloud model does not pass.**

**How it sits with non-negotiable 3.** Offline parity says every workflow works with AI off.
Offline-first says every AI feature works with the network off. Both hold:
- with AI off, the deterministic path answers;
- with AI on and no network, the local profile answers.

**What it changes for every card (section 3):**
- The Tier and Budgets rows name a local candidate, its quantisation, and a context that fits the
  local profile's context (8k by default, section 7, PROPOSED).
- The latency budget is one the local profile meets on named reference hardware:
  - the lab's NMAS host (10.8) for the lab;
  - a representative kit compute unit for a kit (12.6).
- The Success metric, the consistency floor (11.1) and the red-team gate (10.6) are met on the
  local profile. A hosted score is shown beside the local one, never instead of it.
- A feature that misses on the local profile is not built, on any profile.

**A host that admits no local tier** (DECIDED, the operator, 2026-10-16, approving decision 16
with this change):
- AI is **off by default** (10.5).
- An installation setting may allow **hosted-only AI**, set by an admin with a recorded reason
  (the course's own labs call hosted APIs). It is never on by default and never set by Mercury.
- A network carrying a **classification marking** forces AI off with no override
  ([EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md) section 9). **Planned, not built** (C1720, a
  public-release blocker): no marking exists today, so it is no current safeguard.

Offline-first stays the rule for the core path: no feature may depend on a hosted model. A
feature that does not fit the local profile's context is split or not built, never offered
hosted-only.

### 12.2 Item 1's audit: every feature this plan names, against the rule

**Read 2026-10-16, against sections 2 to 11 as written.** One failure is common to every AI
feature in section 6, and the plan as written allows it:
- section 7 makes the hosted tiers the default ("small by default (Claude Haiku 5.5)"; "Anthropic
  first"), and offers the local model "beside it, only where it passed";
- 10.6 turns a card on per model.

So a feature may turn on having passed on a hosted model alone, and no card is required to pass
on the local profile. **Every row marked "fails" fails on that ground, plus what its own row
adds.** The local-profile figures that matter:
- the local profile's context is 8k tokens by default (section 7, PROPOSED);
- the lab host fits the small tier only (10.8, estimated);
- 10.8 estimates tens of seconds for a 3,000-token prompt on the small tier, where section 6's
  shortest budgets are 3 to 5 s. Speed is unmeasured.

Every feature's inputs and tools are already local:
- Prometheus, Loki, NetBox and the config repository are on-premises services
  (OFFLINE_OPERATION section 5);
- E18 is on loopback;
- no tool reaches the internet (non-negotiable 6).

**The data path is therefore never what fails. The model path and the budgets are.**

*Amended 2026-10-18 (the operator; section 13.1):* each row once marked "fails" is now a
**release-gate row**. The feature is built and accepted on Anthropic. What its last column names
must pass on the local profile before the public release (Stage 10), never before the feature is
built.

| Feature (where planned) | In and out vs the local context (8k) | Latency budget vs 10.8's estimate | Against offline-first | What it needs to pass the release gate |
|---|---|---|---|---|
| 1. Natural language → PromQL or LogQL (section 6; 8.1), and its extension to Mercury's records and NetBox inventory (11.9) | 2k + 200: fits | 3 s: far below the estimate | **release gate** | a latency budget the local small tier meets, measured (12.6, measurement 1); its eval, consistency and red-team runs on the local profile |
| 2. Alert correlation (8.1) | 3k + 400: fits | 5 s: far below | **release gate** | the same as 1 |
| 3. Incident record draft (8.2) | 5k + 600: fits | 15 s: unmeasured | **release gate** | a measured local latency; its eval on the local profile |
| 4. AI catalog selection (8.3) | 3k + 300: fits | 5 s: far below | **release gate** | the same as 1. Section 7's 95% agreement over 100 selections is measured on the local model itself; a hosted model's agreement does not carry over |
| 5. Root-cause proposal (8.2) | 15k + 1.5k: **exceeds** | 60 s: unmeasured | **release gate** | one of: a measured minimum context (section 4) small enough to fit; or a larger local context, its memory measured against section 7's 20% reserve. Plus a local candidate meeting 50% confirmed-true. Its tier is "medium" (a hosted Sonnet), and the large local tier does not fit the lab host (10.8) |
| 6. A proposed pipeline check (8.2) | 8k + 1k: **exceeds** | 30 s: unmeasured | **release gate** | the same as 5 |
| 7. Natural language → intent (8.5) | 10k + 1.5k: **exceeds** (its few-shot examples count) | 20 s: unmeasured | **release gate** | the same as 5 |
| 8. A verifier draft (8.1) | 4k + 800: fits | 15 s: unmeasured | **release gate** | a measured local latency; its eval on the local profile |
| 9. Inferring higher-level intent (8.5) | 20k + 2k: **exceeds** | 60 s: unmeasured | **release gate** | the device set split deterministically (by role or site) so each part fits the local context, or the larger local context as in 5 |
| 10. Template draft for a new platform (8.5) | 30k + 6k: **far exceeds** | 120 s: unmeasured | **release gate** | drafted section by section, since the round trip already compares section by section (`roundtrip.compare`, IBN_DESIGN section 1), each section within the local context; or a large local tier with a long context, which the lab host cannot admit (10.8) |
| AI classification of deliberate vs unexplained drift (section 5, 8.2) | no card | no card | **release gate** (no card, so not built: section 3) | a card, written offline-first from the start |
| 8.0's gateway | n/a | n/a | **release gate** ("Anthropic first") | the local profile as the first and required profile; each hosted adapter optional and off unless configured; 11.8's busy and degraded states naming the local model's own states (not admitted, unloaded, one request at a time) |
| 8.0's eval harness and red-team set | n/a | n/a | **release gate** ("live on the host" names no profile) | the live runs, and the exit criteria's red-team run, made through the local profile, with hosted runs optional beside them |
| 8.0's prompt registry, schema library, MCP tool server, masking, cost dashboard | n/a | n/a | passes | none. The dashboard shows zero cost per token for the local profile, and latency and the one-at-a-time queue as its binding budgets (section 7) |
| 8.0's tracing (OpenTelemetry GenAI conventions) | n/a | n/a | passes, if exported on-premises | an on-premises collector or none; never an external exporter (non-negotiable 6) |
| 10.7's evaluation | n/a | n/a | passes | none: it already runs every candidate locally through `llama-server` |
| Voice (11.6; deferred, IBN_DESIGN decision 11) | n/a | n/a | not assessable: deferred, and no speech-to-text engine is named | when it returns, a local speech-to-text model under 10.2's origin rule and its licence read, or voice off with no network |
| The optional injection classifier (IBN_DESIGN section 13, item 5; approved with decision 14) | n/a | n/a | not assessable: no engine named | deterministic, or a local model under 10.2; never a hosted call |
| The deterministic work: verifiers, the Respond engine, Activate, the intent compiler, Batfish, the single-node twin (8.1 to 8.5) | no model | no model | passes | none for this rule. Batfish's and the twin's images reach an offline host as OFFLINE_OPERATION section 4 says |
| 11. Document extraction (new; 12.3) | measured per node region (BRINGUP_FROM_DOCUMENTS section 6.1) | from the kit measurement | passes by design: local by necessity and by rule (BRINGUP_FROM_DOCUMENTS section 6) | its measurements (12.6) |
| 12 to 14. The disconnected operator assistant (new; 12.3) | estimated within 8k (12.3) | target 30 s | passes by design | its measurements (12.6) |

**The list for the operator: the features that fail offline-first today, and what each needs.**

Common to all of them:
- (a) a card naming a local candidate, its quantisation and a context that fits the local
  profile;
- (b) its eval, consistency floor and red-team gate met on the local profile, on reference
  hardware;
- (c) not built if (b) fails, rather than offered on a hosted model alone.

Beyond that:
1. **Natural language → PromQL or LogQL** (with 11.9's records and inventory) **and alert
   correlation:** budgets of 3 and 5 s, against 10.8's estimate of tens of seconds on the small
   tier. Each needs a latency budget re-derived from the local measurement.
2. **Incident record draft and verifier draft:** they fit the context, but their 15 s budgets are
   unmeasured locally. Each needs the local measurement.
3. **AI catalog selection:** a 5 s budget, as 1. Its 95% agreement must also be measured on the
   local model; a hosted model's agreement does not carry over.
4. **Root-cause proposal, the proposed pipeline check and natural language → intent:** 15k, 8k and
   10k tokens of input exceed the local 8k context, and they are tiered "medium" (hosted). Each
   needs one of: a measured minimum context that fits; or a larger local context with its memory
   measured against the 20% reserve and a large-tier host (the lab host needs 32 GiB).
5. **Inferring higher-level intent:** 20k tokens. It needs the device set split
   deterministically into parts that each fit, or the larger context as in 4.
6. **Template draft for a new platform:** 30k + 6k tokens. It needs drafting section by section
   (the round trip already compares by section), or a large local tier with a long context.
7. **AI drift classification (8.2):** it has no card. It needs one, offline-first from the start.
8. **8.0's gateway:** "Anthropic first". The local profile must be first and required, and
   hosted adapters optional and off unless configured.
9. **8.0's eval harness and red-team exit criteria:** their live runs must name the local profile.

### 12.3 The disconnected operator assistant: section 11.12's three patterns, no new one

**The case** ([EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md) sections 1 and 11):
- minimally trained kit operators, offline, bringing a satellite link up;
- the reduced, plain-language mode, selected by the token's group;
- "Call headquarters with code <X>" wherever a decision is not theirs.

**It is not a general assistant (non-negotiable 4).** It is four named workflows, each with its
own input, a schema-constrained output and a defined action for each result. Each is reached from
a screen the reduced mode already draws: status, Needs attention, and the guided bring-up's
stepper. Each needs a board and the operator's sign-off (section 8). There is no chat box.

**The kit operator's tools,** fixed by role before any call (non-negotiable 5; IBN_DESIGN section
12):
- the agent's Tier 1 reads: [NSOT_READS.md](NSOT_READS.md) section 11's reads, plus `verify` alone
  of the extras (`modules/nsot/reads.py` `EXTRAS["agent"]`), and never `send log`;
- retrieval from the signed runbook store (12.4);
- one proposing tool, `propose_playbook`.

There is no `propose_intent_change`, and nothing that approves or reveals. The kit operator never
holds `approve` (OFFLINE_OPERATION section 1.7).

**Translator, two workflows:**
- **Feature 11: provider documents into values.** BRINGUP_FROM_DOCUMENTS's card (its section
  6.3), unchanged:
  - the parser profile is the deterministic path, and the local model is the fallback for a
    format with no profile;
  - it reads only text code has scoped to this node's region, and never a secret field;
  - its output is locations and values, which code reads back from the text layer.
- **Feature 12: a plain question into Tier 1 reads only.** "Is the satellite link up?" becomes the
  read-only commands, read back, run and summarised.
  - *Deterministic first:* headquarters' named checks answer the questions headquarters
    foresaw, and a person picks them from a list. These are saved command sets
    ([NSOT_READS.md](NSOT_READS.md) section 5), each with a deterministic verdict, plus the
    guided bring-up's checks. The model maps a sentence onto one of them; only where none fits
    does it compose Tier 1 reads.
  - *The pattern is feature 1's (11.9):* the output is a structure, never free text. The engine's
    allowlist refuses the whole command first (`readonly_commands`, for the agent). The commands
    are read back in plain words, and the person runs them with one control.
  - *The reads run as "the agent, for <person>"* through `reads.run(..., by="agent")`, which
    opens no session of its own (NSOT_READS section 2).
  - *The summary* answers yes, no or cannot tell, citing the read lines it rests on.
  - *It can never produce a change:* its schema holds no change, its tools hold no `propose_*`,
    and the engine refuses anything outside Tier 1 for the agent.

**Analyst, one workflow:**
- **Feature 13: what is wrong, in plain words.** It draws on the kit's Needs attention rows, the
  readers' stored values they cite, its live reads, and headquarters' runbooks retrieved from the
  signed store (12.4).
  - *Deterministic first:* a lookup from each row's source and kind to its runbook section and
    call-in code is built first, as section 6 removed "suggesting a remediation class" because
    the taxonomy is a lookup. The model is for several rows at once, and for the operator's own
    question about them.
  - *Every claim names its source:* field provenance (11.3, extended to documents by 12.5's
    gap 1), and evidence references checked deterministically (IBN_DESIGN section 10: a claim
    citing something never fetched is dropped).
  - *The Analyst floor applies:* 90% on structured fields (11.1).

**Decision-maker, narrowed at the kit:**
- **Feature 14: a playbook proposal.** It may only PROPOSE one of headquarters' signed standard
  playbooks ([EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md) section 6.1), with its bounded inputs
  filled, for the kit operator to confirm.
  - *Code decides whether it may be shown:* the playbook's signature verifies; its id is in the
    signed catalog; every input is inside its bounds.
  - *Anything else is refused before the operator sees it, never offered:* the model never
    proposes outside a playbook's bounds, and never proposes an emergency change. An emergency
    change stays the kit operator's own, with a reason (EDGE_ARCHITECTURE section 6.3).
  - *The run is the playbook's own lifecycle:* preview, confirm by hash, verify, rollback,
    record. It never acts and never approves.
  - *The Decision-maker floor applies:* 95% (11.1).

**The four cards, in section 6's shape.** They join section 6's list as candidates 11 to 14, and
their ranking is the operator's (decision 7's form). Every number is a proposal. "Tier" means the
local profile's admitted tier, and a hosted profile is optional (12.1).

| # | Feature | Pattern (floor) | Inputs → output | Budget per use | Target | Observe → leave | Kill | Compared fields |
|---|---|---|---|---|---|---|---|---|
| 11 | Document extraction (BRINGUP_FROM_DOCUMENTS section 6.3) | Translator (95%) | one node region's text layer, the schema and the error contract → each non-secret field's value and cited location | tokens measured per region (12.6, measurement 7); latency from the kit measurement | 98% per-field exact match on the synthetic corpus; 0 values from outside the node's region reaching the confirm | at headquarters, beside parser profiles on formats that have one; 100 regions; 98% | below 95% after 100 regions; one out-of-region value reaching the confirm (zero tolerance) | each non-secret field's canonical value and its location; the error contract's kind |
| 12 | Plain question → Tier 1 reads | Translator (95%) | the question (normalised, 11.7), the kit's device names and roles, the named checks and the platform's common reads, about 2k tokens → a named check, or reads per device, or the error contract; then the reads' answers, summarised deterministically first, about 3k tokens → `{answer, evidence_refs[], words}` | 2k in and 200 out, then 3k in and 300 out; 30 s of model time (the reads' own bounds apart, NSOT_READS section 11) | 80% of questions answered by a named check or a read set a person marks right; 0 commands the engine has to refuse | on the synthetic scenarios at headquarters, then on the lab's Ask the device; 30 days and 50 questions; 80% | below 65% after 50; any command the engine refused (it measures the model's discipline, since the engine already stops it) | the named check or the commands per device, whole; `answer`; `evidence_refs` |
| 13 | What is wrong, in plain words | Analyst (90%) | the kit's Needs attention rows, the values they cite, the reads, the retrieved runbook passages, about 4k tokens → `{explanation, evidence_refs[], runbook_steps[], covered, call_in_code, needs_human}` | 4k in, 500 out, 30 s | 80% of explanations marked right by headquarters NetOps on the scenario set; 0 procedure steps from outside the store (by construction, 12.4) | at headquarters on the scenario set, then in the lab on Needs attention; 50 scenarios; 80% | below 65% after 50 | `evidence_refs`, `runbook_steps`, `covered`, `call_in_code`, `needs_human` (the explanation is prose) |
| 14 | Playbook proposal at the kit | Decision-maker (95%) | the rows and reads, and the signed catalog's playbooks with each input's bounds, about 3k tokens → `{playbook, inputs, evidence_refs[], needs_human}` or "none fits", with its call-in code | 3k in, 300 out, 30 s | 95% measured agreement with headquarters NetOps' choice over at least 100 scenarios (section 7's rule for selection; confidence logged, never a gate) | at headquarters only, before any kit receives it; 100 scenarios; 95% | agreement below 90%; one proposal outside a playbook's bounds reaching the confirm (zero tolerance; code refuses it earlier, so reaching the confirm is a defect) | `playbook`, `inputs`, `evidence_refs` |

**Owners:** headquarters NetOps is proposed for all four (decision 9 names owners). **The
Problem row** of each card is measured, never guessed: a timed headquarters exercise on the
synthetic scenarios (12.6, measurement 8).

### 12.4 Grounding is the safety mechanism (DECIDED, the operator, 2026-10-16; the design PROPOSED)

**The runbook store.**
- Headquarters' runbooks and troubleshooting guides are a local, signed document store,
  distributed with the build standard. They join the items listed in
  [EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md) section 4.
- The kit verifies the store with section 10.2's one verifier before using it, and refuses a
  store that does not verify, in plain words with a code.
- Every passage carries an id, its step ids where it is a procedure, and headquarters' call-in
  code.

**The assistant answers only from that store and the kit's own data:** its Needs attention rows,
the readers' stored values, its Tier 1 reads' answers, and its records.

**It never improvises a procedure. This is enforced by construction, not by instruction:**
- An answer's steps are `runbook_steps`: step ids retrieved in this run.
- Code renders each step in the runbook's own signed words. The model writes no step text.
- A step id that was not retrieved in this run is dropped, by IBN_DESIGN section 10's
  evidence-reference rule applied to steps.

**When nothing covers the question, it says so** ("This is not covered. Call headquarters with
code <X>."). There are three such cases:
- retrieval returns nothing, and then no model is called at all;
- every step of the answer drops;
- the model returns the error contract.

The code is the store's code for the row or read that prompted the question, or the store's
general code. A code is headquarters' data, never generated.

**Retrieval is chosen by measurement on the kit's hardware** (12.6, measurement 6), under the same
rules as the model:
- **Keyword search** (a ranked term index): no model, so no origin question. Any library it needs
  is a licence decision.
- **Local embeddings:** an embedding model is a model, so 10.2's US-origin rule and its own
  licence apply.
- Deterministic first (section 2, rule 2) makes keyword search the baseline that embeddings must
  beat on the measurement.

**Plain words on every answer the kit operator sees** ([EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md)
section 11's two audiences):
- the kit operator reads the answer in plain words;
- headquarters NetOps reads the evidence one level down: the references, the retrieved passages,
  the reads.

The eval's labelled cases carry a person's judgement of the plain words. No automatic readability
score is relied on.

**The red-team set (IBN_DESIGN section 13, item 8) gains two cases:** instructions planted in a
runbook passage, and in a device's answer to a Tier 1 read. A signed store is still data, never
instructions.

### 12.5 The ten gaps, decided or deferred

[BRINGUP_FROM_DOCUMENTS.md](BRINGUP_FROM_DOCUMENTS.md) section 16 names the first nine. The tenth
came with this section's brief. "Decided" here was this plan's position; the operator approved
it on 2026-10-16 (decision 16). Gap 9 is answered by the operator's own decision.

| # | Gap | Resolution | Status |
|---|---|---|---|
| 1 | **Document provenance** (page, line, region): 11.3 covers words from the request only | 11.3 is extended to document inputs. A field read from a document carries `source_location`: the document's sha256, the page and line (or table cell), and the region id. Code reads the value at that location from the text layer, and refuses one that does not occur there or lies outside the region. For document input, 11.3's PROPOSED detail (a `stated` field's words must occur in the source) is a requirement. Feature 13's claims cite a runbook passage id or a kit datum the same way | decided |
| 2 | **Value-level normalisation** (7, 07, N-007) | 11.7 stays character-level. A value's written forms are reduced by the feature's own deterministic parser, declared as data (the parser profile's node forms, in the build standard), after 11.7 and before any matching. Each reduction is recorded, as 11.7 records a removal. A model never normalises a value | decided |
| 3 | **Ambiguity inside a document**, with a refusal and a call-in code | 11.2 is extended to document regions. Zero or several matching regions is code's question, whatever the model returned. **Who receives code's question is a property of the role:** a role that may not decide (the kit operator) gets a refusal naming a call-in code, never the question | decided |
| 4 | **No card for document extraction** | It joins section 6's list as candidate 11, Translator (95%), with BRINGUP_FROM_DOCUMENTS section 6.3's card and 12.3's numbers. Its pattern placement is the operator's (11.12's form) | decided (placement for the operator) |
| 5 | **Real cases versus classified documents** (section 7's "at least 10 real cases", section 4's recorded responses in CI) | For a feature whose real inputs may be classified (11, 12, 13 and 14 on a marked network), the real-case minimum is met inside the secure environment, by a run that records only numbers and sha256 values (BRINGUP_FROM_DOCUMENTS section 14's "Test this profile" shape). CI's recorded responses are of synthetic cases only. The release gate reads both. Section 7's rule is unchanged for features whose real cases can be published (the lab's) | decided |
| 6 | **Few-shot examples from the config repository's history** would be classified | Shipped prompts carry synthetic examples only, marked as such (11.4 already allows labelled eval cases where real history holds none). An enclave may add its own reviewed examples under 11.5's review gate. They stay inside the enclave (EDGE_ARCHITECTURE section 9) and are data, so there is no per-model or per-site prompt fork (10.3) | decided |
| 7 | **No document, scan or OCR input type** | A document reaches a prompt only as a text layer with coordinates, made by code before any prompt (BRINGUP_FROM_DOCUMENTS section 3). OCR is a deterministic step whose per-word confidence floor refuses unclear words. No image reaches a model, so every candidate in 10.2 can serve and every location can be checked. **Deferred:** the PDF, Word and OCR libraries, each a new third-party licence and so the operator's | the shape decided; the libraries deferred to the operator |
| 8 | **Kit hardware tiers and a kit latency budget** (10.5 and 10.8 cover the lab host only) | 10.5's hardware check and section 7's 20% reserve apply unchanged on a kit: the wizard runs on whatever host the instance is. The interactive target for features 12 to 14 is a useful answer within 30 s (the operator's number); feature 11's budget comes from the kit measurement. **Deferred:** the kit's tiers and numbers, until 12.6's measurements are taken on a representative kit unit at headquarters staging | deferred to the measurement |
| 9 | **Offline approval** (2.6 takes identity only from the access assertion) | **Answered by the operator's decision of 2026-10-16:** Keycloak per instance ([OFFLINE_OPERATION.md](OFFLINE_OPERATION.md) section 1.3), with smart card, "Log in with HQ" and local TOTP. 2.6's principle stands as "identity only from the instance's verified sign-in" (OFFLINE_OPERATION section 1.5's verified person), never from prompt text. Confirm by hash works offline. A kit operator confirms a standard playbook (EDGE_ARCHITECTURE section 6.1) and never holds `approve` (OFFLINE_OPERATION section 1.7) | DECIDED (the operator, 2026-10-16) |
| 10 | **llama.cpp (10.4) is still PROPOSED**; only the origin rule (10.2) is decided | 12.1 quotes the operator naming `llama-server` as the local profile, which decides the engine; 10.4 carries a note. The model's delivery stays PROPOSED. A kit has only 10.4's import path: a supplied file with its sha256 and signature checked at staging, never a download. Tiers, reliability, isolation and the release gate also stay PROPOSED (decision 12). **Confirmed by the operator, 2026-10-16: `llama-server` is the engine.** Each candidate's licence is read in 12.7 | DECIDED (the operator, 2026-10-16) |

### 12.6 Measurements owed before any choice (none taken)

| # | Measurement | Method | Where it runs |
|---|---|---|---|
| 1 | **Seconds per answer and tokens per second** for gpt-oss-20b, Gemma 4 E4B and 26B MoE, and Granite 4.0-H-Tiny and H-Small, against a useful answer within 30 s | `llama-server` at Q4 (10.7), first 10.5's 30-second speed test. Then every scenario's question end to end at the profile's context, recording prompt and generation tokens per second, time to first token, and seconds per answer (median and 95th percentile). Each candidate is run where its tier is admitted | **CPU-only:** the lab's NMAS host for the small-tier candidates (10.8; the large tier needs the VM at 32 GiB, the operator's capacity decision), and a representative kit compute unit at headquarters staging. **Small GPU:** a representative kit unit with its GPU, at headquarters staging (10.8 records no GPU in the lab) |
| 2 | **Memory** against the kit's budget | MemAvailable with the whole stack running and the model loaded at the profile's context, sampled for at least a day (10.8's sysstat method), against section 7's 20% reserve. Also `llama-server`'s resident size and KV cache at each context tried, and with the kit's C8000v if it shares the unit (BRINGUP_FROM_DOCUMENTS section 6.1) | the lab host for the method; the kit unit at headquarters staging for the numbers |
| 3 | **Power** against the kit's budget | the unit's draw at its supply (a meter), idle, during one answer and during a sustained eval run, against the power budget in the kit's build (read at headquarters) | the kit unit at headquarters staging |
| 4 | **Heat** against the kit's budget | the unit's temperature sensors and its CPU (or GPU) clock through a sustained eval run at the kit's rated ambient temperature, noting whether it throttles; measurement 1 repeated while throttled | the kit unit at headquarters staging |
| 5 | **The consistency eval on a synthetic bring-up scenario set** | 11.1's eval, run N=5 times per case and compared on each card's compared fields (features 11 to 14), per candidate and quantisation, against the pattern's floor. The set is synthetic and public: BRINGUP_FROM_DOCUMENTS section 14's corpus, plus synthetic Needs attention states, reads, runbooks and questions, using documentation addresses only | recorded responses in CI; live on the lab host (small tier) and on the kit unit at headquarters |
| 6 | **Retrieval: keyword search against local embeddings** | recall at k (the labelled passage among the top k) on a labelled synthetic question set over a synthetic runbook store; also seconds per query, memory and index build time | the lab host for the method; the kit unit for the choice |
| 7 | **The minimum context of each assistant card** (section 4) | the context-removal run on the scenario set, against the local profile's 8k (section 7, PROPOSED) | CI (recorded) and live on the lab host |
| 8 | **Today's time without AI** (each card's Problem) | a timed headquarters exercise on the synthetic scenarios: kit operators with paper runbooks and the deterministic screens. For the lab's features, 8.0's observe period | headquarters staging; the lab |
| 9 | **Accuracy on real documents and runbooks** | "Test this profile"'s shape (BRINGUP_FROM_DOCUMENTS section 14): numbers and sha256 values only, never text | inside the secure environment |

BRINGUP_FROM_DOCUMENTS's own "Measurements still owed" (its items 1 to 7) stand beside these and
are not repeated here.

### 12.6a Measurement 1 on the NMAS host at the Minimum shape: the host procedure (written 2026-10-18; NOT RUN)

**The operator's instruction, 2026-10-18:** written as a procedure, and not run. The model's
download and its licence are the operator's (CLAUDE.md, stop 3), and so is the inference
server's binary. The Minimum tier is 4 vCPU and 8 GiB (docs/MERCURY_CHARTER.md). The NMAS host
has 4 vCPU and 15.6 GiB (10.8).

**Before it starts (the operator's):**
1. **Choose the model.** It comes from 10.2's US-origin list. The smallest are Granite 4.0-H-Tiny
   and Gemma 4 E4B, so they are the candidates at this shape. Read its licence on the pinned
   file (12.7), and record the file's sha256.
2. **Get the binary:** a pinned `llama-server` (llama.cpp, MIT), with its version and sha256
   recorded.
3. **Shape the host.** Either:
   - **(a)** set the NMAS VM to 8 GiB in Proxmox (the operator's change there), restart it, and
     check `nproc` is 4 and `MemTotal` about 8 GiB; or
   - **(b)** keep 15.6 GiB and judge Minimum by arithmetic: what the stack uses
     (`MemTotal - MemAvailable`) plus what the model uses must leave 20% of 8 GiB (1.6 GiB)
     free (section 7's reserve). Option (a) measures the shape; option (b) only estimates it,
     and the record says which was used.
4. **Pick a time** outside the backup window (08:30 to 09:10 UTC) and outside a walk. Nothing
   in the procedure touches a device.

**The steps (on the NMAS host; every number recorded with its UTC time):**
1. **The stack's baseline:**
   - `MemAvailable` from `/proc/meminfo`, every 30 s for 10 minutes, with the whole stack
     running (Mercury, Prometheus, Loki, Grafana, NetBox, Kea);
   - `sar -u 30 20` for CPU.
2. **Start the server:** bound to loopback, with all but one vCPU, the profile's 8k context, and
   capped so it cannot starve the stack (10.6):
   `systemd-run --scope -p MemoryMax=<limit> -p CPUQuota=300% llama-server -m <file> --host 127.0.0.1 --port 8081 -t 3 -c 8192`.
   - The limit is 8 GiB minus the stack's lowest measured use, minus the 1.6 GiB reserve. If
     that is under the model's file size, stop: it does not fit Minimum, and that is the
     result.
   - Record the server's resident size (`ps -o rss`) once it reports ready.
3. **Prompt and generation speed:**
   - `llama-bench -m <file> -t 3 -p 512,2048 -n 128`, three repetitions, giving prompt and
     generation tokens per second;
   - the same from the server: its `timings` on `/completion` (`prompt_per_second`,
     `predicted_per_second`).
4. **Memory with the model loaded:**
   - `MemAvailable` every 30 s, idle for 5 minutes, then during step 5;
   - the lowest value against the reserve: 1.6 GiB at the Minimum shape, or under (b), the
     arithmetic.
5. **Feature 1's prompt, end to end:**
   - **The prompt:** its card's shape (section 6, rank 1). That is the system text, the query
     model's JSON schema, the metric names and labels retrieved for the question's terms from
     the host's Prometheus (`/api/v1/label/__name__/values`, filtered to the terms), and the
     question. About 2,000 tokens in, at most 200 out. It is written as a file under `lab/`
     (lab material, never the product's) before the run, with its token count recorded.
   - **The run:** five runs of `POST /v1/chat/completions` with the schema as the response
     format.
   - **Record for each run:** time to first token, total seconds, prompt and generation tokens
     per second, whether the output parses against the schema, and whether the five structured
     outputs are identical (11.1's consistency).
6. **Stop the server.** Check `MemAvailable` returns to the baseline.

**The result is a row in 12.6's measurement 1**, with:
- the model and its sha256, the binary's version, and the shape used, (a) or (b);
- tokens per second (prompt, generation);
- seconds per answer (median and 95th percentile);
- the lowest `MemAvailable`;
- whether it fits Minimum.

The expected reading, from 10.8, is an estimate only: the stack used about 4.3 GiB on
2026-10-14 (15.6 GiB less 11.3 GiB available), and a small model needs about 5 to 6 GiB. That
sum, 9.3 to 10.3 GiB, already exceeds 8 GiB before the reserve. If the measurement agrees, the
local model does not fit Minimum, which is consistent with the charter placing it in Large. The
measurement decides; the estimate does not.

### 12.7 Governance (DECIDED, the operator, 2026-10-16)

**Each candidate's licence is read from its own terms, on the pinned file.** The licences are
never assumed to match one another (decision 13):

Read 2026-10-16 from each one's own published terms, and recorded with its source in
`docs/STANDING_APPROVAL_LOG.md`. A pinned file's own terms are read again when it is pinned.

| Candidate | Licence, as read |
|---|---|
| gpt-oss-20b | Apache 2.0 (its model card). Its repository's `USAGE_POLICY` adds one obligation: comply with all applicable law |
| Gemma 4 E4B (`google/gemma-4-E4B-it`) | Apache 2.0 (its model card, linking Google's Gemma 4 licence page, which is the plain Apache License 2.0). The same site links a "Prohibited use" policy that states no scope; whether it binds Gemma 4 is an open question for the organisation |
| Gemma 4 26B MoE (`google/gemma-4-26B-A4B-it`) | as Gemma 4 E4B |
| Granite 4.0-H-Tiny | Apache 2.0 (its model card) |
| Granite 4.0-H-Small | Apache 2.0 (its model card) |
| `llama-server` (llama.cpp) | MIT (its `LICENSE`) |
| an embedding model, if retrieval uses one | not chosen; read from its own terms when chosen; US origin (10.2) |

A quantisation made by someone other than the publisher is a different artefact (10.2,
PROPOSED). Its terms are read on that file.

**Authorisation to operate.** The model files, the inference server and Mercury would each need
the organisation's authorisation to operate on a government network. That authorisation is the
organisation's, outside this project. US origin is one input to it, not a substitute for it.

**Shipped signed, evaluated first.**
- What ships: the models (each file with its sha256, its profile and its eval result), the
  runbooks and the eval set. All ship signed with the build standard
  ([EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md) sections 4 and 10.2).
- Each is evaluated at headquarters against the synthetic scenarios before any kit receives it.
  This is 10.6's release gate per model and version, including the red-team set and 12.3's
  cards.
- A kit verifies every signature before loading anything. Its prompts, responses and records
  stay inside the enclave (EDGE_ARCHITECTURE section 9).

### 12.8 Proving it in the lab first

**The same capabilities run on the NMAS host's small tier** (10.8: 4 vCPU, 15.6 GiB; the small
tier only, its speed unmeasured):
- **Ask the device's plain-question reads:** feature 12, on the device page's Ask the device tab
  ([NSOT_READS.md](NSOT_READS.md) section 3), a board first (section 8);
- **Runbook-grounded explanations on Needs attention:** feature 13, against a lab runbook store
  signed with a lab key. The store holds the manual's pages (`docs/manual/`) and runbooks written
  for the lab's Needs attention sources. The lab's runbooks are lab material under `lab/`, never
  the product's;
- **Document extraction against the synthetic corpus:** feature 11 (BRINGUP_FROM_DOCUMENTS section
  14).

The lab runs keep the lab's standing rules: Tier 1 reads never on s3, and no run in the backup
window. The model is unloaded while a single-node twin runs (10.8).

**The kit is later the same capabilities on different hardware, not a separate build.** The code,
prompts, tools, cards and evals are the same. Only the profile (data, 10.3) and the tier the
wizard admits (10.5) differ.

### 12.9 What this changes elsewhere in this plan

A dated note points here from each sentence the rule changes:
- non-negotiable 3 (section 2);
- non-negotiable 6's identity item (section 2; gap 9);
- section 5's 8.0 row ("Anthropic first");
- section 6's candidate list (candidates 11 to 14);
- section 7's Model tiers row;
- 10.4 (gap 10).

Section 9 gains decision 16. IBN_DESIGN carries the same dated notes where it states a dependency
on a hosted model or on the internet (its sections 7, 9, 12 and 13).

### 12.10 The required tests (named now; written with the code)

Each is written in 10.9's form: shown able to fail, with a planted case.

1. **`tests/test_offline_first.py`**
   - Checks:
     - every card names its local-profile result (candidate, quantisation, score, consistency,
       latency), beside any hosted one;
     - every feature's recorded eval set holds runs from a local profile (the OpenAI-compatible
       adapter to `llama-server`, origin `"US"`);
     - the gateway answers every feature with every hosted adapter unreachable.
   - Planted cases:
     - a card whose recordings are all hosted fails;
     - a gateway that refuses because a hosted provider is down while the local profile is
       loaded fails.
2. **`tests/test_assistant_reads_only.py`**
   - Checks:
     - feature 12's output reaches `reads.run` only as commands `readonly_commands` passes for
       the agent;
     - `send log`, configure mode, Tier 2 and Tier 3 are refused before any device is asked;
     - the kit operator's tool set holds no `propose_intent_change` and nothing that approves
       or reveals.
   - Planted case: a recorded output carrying `configure terminal` that reaches the sender fails.
3. **`tests/test_answers_are_grounded.py`**
   - Checks:
     - an answer's steps render only from step ids retrieved in this run, in the store's signed
       words;
     - an unretrieved id is dropped;
     - with nothing retrieved, the answer is "not covered" with the store's code, and no model
       is called;
     - an unsigned or altered store is refused at load.
   - Planted case: a recorded answer whose free-text steps are drawn as a procedure fails.
4. **`tests/test_playbook_proposal_bounds.py`**
   - Checks: feature 14's proposal is refused when its playbook is not in the signed catalog or
     an input is outside its bounds, whatever the recorded output says, and it reaches only that
     playbook's preview.
   - Planted case: an out-of-bounds input that reaches the preview fails.
5. **11.3's and 11.2's tests, extended** (gaps 1 and 3)
   - Checks:
     - a document value whose location lies outside its region, or whose value does not occur
       there, is refused;
     - two matching regions refuse with a call-in code for the kit operator's role.
   - Planted cases: a resolver that takes the first region, and one that trusts a cited
     location without reading it.

## 13. The amendments of 2026-10-18 (the operator; documents only)

**The operator's message of 2026-10-18 (evening), "the path after Phase 7", part 4.** Documents
only: nothing is built. Phase 8 comes after Core 1.0 (NSOT_PLAN section 9, "The path after Phase
7"). A dated note points here from each sentence these amendments change: sections 5, 7, 10.5,
12.1 and 12.2.

### 13.1 Built on Anthropic; offline-first is the release gate (4a)

*Amended 2026-10-24 (the operator, 15.3): Anthropic is the proof of concept behind the
provider-neutral gateway, and more providers follow; "built and accepted on Anthropic" means
first, never only.*

- **Phase 8's features are built and accepted on Anthropic,** in the plan's tiers:
  - Claude Haiku 5.5 by default;
  - Claude Sonnet 5.5 where the eval shows the need;
  - exact model versions pinned, and any change re-running the full eval suite (section 7).
- **Every feature must pass on the local profile before the public release** (Stage 10), never
  before it is built. 12.1 is the gate's content. 12.2's rows once marked "fails" are its
  release-gate rows.
- **The gateway stays provider-neutral:** one adapter per API shape (10.3). The OpenAI-compatible
  adapter for `llama-server` stays in the design. Only its build waits for the release work.
- **What stays from 12.1:** with AI off, the deterministic path answers (non-negotiable 3). A
  host that admits no local tier has AI off by default, with hosted AI allowed by an admin's
  recorded setting. A classification marking forces it off with no override (planned, not
  built: C1720).

### 13.2 8.0 shrinks to what feature 1 needs (4b)

**8.0 is only what feature 1 (natural language to PromQL or LogQL) needs, end to end:**
1. **The gateway:**
   - the Anthropic adapter;
   - the model profile (data, 10.3);
   - the pinned model version;
   - the cost cap: a cap reached refuses the next call, by name (section 7).
2. **The prompt registry:** prompts are versioned code in `prompts/` (section 4).
3. **The schema library** (Pydantic). *Amended 2026-10-24 (the operator, 15.4): Pydantic v2,
   strict (`strict=True`, `extra="forbid"`), the only schema tool for AI input and output; its
   generated schemas committed as files; `schema_for(model, provider)` derives what each
   provider is sent; a CI test checks each against every enabled provider's strict subset.*
4. **Masking** before every prompt (C733's index).
5. **The eval harness:** recorded responses in CI, live runs on the host (section 4).
6. **History's record of every prompt and response:**
   - the masked prompt;
   - the model and its version;
   - the raw response;
   - the structured output;
   - validation's verdict;
   - IBN_DESIGN's logging row (one id linking them).
7. **The red-team cases that apply to a read-only feature,** data-borne injection included:
   instructions planted in metric labels, label values and log lines that the retrieval returns.
   The rest of IBN_DESIGN section 13's set arrives with the first feature that can act.

**Arriving later, each with the first feature that needs it:**
- roles from sign-in;
- the change-request queue and its board;
- the MCP tool server;
- OpenTelemetry tracing;
- the cost dashboard.

**`TOOLS_BY_ROLE` stays data from the start.** Even feature 1's single read-only retrieval is
bound through it, so a role model added later changes data, not code.

**Does feature 1 really need E18? Reported, not decided** (the operator: "report whether
feature 1 really needs it, with the reason. Don't decide it").
- **What E18 is today, measured 2026-10-18:** the records database (Phase 4) exists.
  `modules/records_db.py` runs PostgreSQL 18, with its connection test and the Records database
  card on Settings › Installation. But its `STORES` holds one store only, `receipts`
  (`records_db.STORES = ("receipts",)`). Acknowledgements, approvals, restart windows, runbook
  runs and the readers' values are still files.
- **Why decision 8 made E18 a prerequisite:** IBN_DESIGN decision 8, "History on E18: yes; E18
  becomes a Phase 8.0 prerequisite", is about **Assure's history**: the verifiers' statuses over
  time (IBN_DESIGN, Assure "waits on E18"). That is 8.1's verifier work, not feature 1.
- **What feature 1 itself reads:** Prometheus's metric names and labels, and Loki's stream
  labels. What it produces is the E3/F3 builder's query model, read back by the builder (built,
  History › Query). **None of that touches E18.**
- **Where feature 1 does meet E18:**
  - (a) **The record of every prompt and response** (item 6 above) needs a store. The charter
    says Mercury's own records consolidate into ONE store, the database. That points to E18,
    and E18 can take a new store as it took `receipts`. A file store that History reads (as
    `credential_changes.jsonl` is today) would also work, and would be a second home to migrate
    later.
  - (b) **11.9's extension** of feature 1, to Mercury's records (changes, rotations,
    approvals), needs those records queryable. In E18 they are not yet: it holds receipts only.
- **So:** feature 1's first slice, PromQL and LogQL, does not need E18 to work. It needs a home
  for its prompt record, which the charter's one-store rule would put in E18. 11.9's extension
  needs E18 holding the record kinds it queries. Which way to go is the operator's.

### 13.3 The order (4c)

1. **Feature 1:** natural language to PromQL or LogQL.
2. **Feature 7:** natural language to intent.
   - **Then, after the sprint: card P5, Plan with AI and the action library** (16.7; the
     operator, 2026-10-26).
3. **The Analysts:** features 2 (alert correlation), 3 (incident drafts) and 5 (root cause).
4. **Respond's classes, enabled one at a time** as each class's observe data qualifies: 1% false
   positives or fewer over at least 30 days and 100 events. The observe period itself runs in
   Core 1.0's tail. *Moved 2026-10-24 (the operator, 15.2): enabling a class is Phase 9, the
   closed loop; the order is otherwise unchanged (15.1).*
5. **The rest, as ranked** (section 6).

### 13.4 An output shape on every feature card (4d)

Section 3's card gains a row, **Output shape**:

| Shape | What it is | Features |
|---|---|---|
| **A** | plain JSON: translators and choices, and enums such as drift classification | 1, 4, 7 |
| **B** | JSON whose FIRST field is a short rationale, then the answer fields; never step-by-step reasoning | the Analysts: 2, 5, 9 |
| **C** | JSON metadata, plus the artifact in a delimited raw block, so code is never escaped inside JSON; the deterministic test or round trip accepts the artifact | 6, 8, 10 |

- **Feature 3's human prose** stays in string fields, and is never compared (11.1 compares
  structured fields only).
- **The evidence:**
  - Tam et al. 2024, "Let Me Speak Freely?" (arXiv 2408.02442): restricting the format hurts
    reasoning; an answer-before-reason key order turns the reasoning into guessing; JSON helps
    classification. Hence shape B's rationale first, and shape A for choices.
  - Aider, 2024-08-14, "LLMs are bad at returning code in JSON": models write worse code when
    asked to return it inside JSON. Hence shape C's raw block.
- **Enforced by `tests/test_feature_cards.py`, extended** (11.12): every card names its output
  shape. A shape B schema's first property is the rationale. A shape C card names its delimiter
  and the deterministic test that accepts the artifact. Planted cases: a card with no shape, and
  a shape B schema with the rationale last.

### 13.5 Anthropic's structured outputs (4e)

- **The API carries the schema:**
  - responses use `output_config.format` with a `json_schema`;
  - tools use `strict: true`.
  The prompt never asks for JSON. This replaces 11.12's "constrained decoding" row for the
  Anthropic adapter. On the local profile the same row is `llama-server`'s grammar (10.6).
- **Pydantic still validates what the API schema cannot express:**
  - number ranges;
  - string lengths;
  - item counts beyond 0 or 1.
- **Enums:**
  - enum values are compared case-insensitively;
  - no two values of one enum may differ only in case, enforced by the schema library's own
    test with a planted pair.
- **A refusal** (`stop_reason` `"refusal"`) and a hit on **`max_tokens`** each land in the
  error contract (11.4), never in a parser crash. Each has its own error kind, counted on the
  card's evals (13.9's incidence).
- **Few-shot and the error contract stay** (11.4).
- **References are still resolved by code** (11.2). This is a deliberate departure from the
  course's W9 example, where the model maps names to addresses: here code resolves every name
  against NetBox and intent, and a zero or several match is code's question.

### 13.6 Every feature's eval set is a versioned, reusable dataset (4f)

- Each case holds its inputs, the expected structured output, and its provenance: real (its
  source and date), replayed, or synthesised (section 7).
- Each set is versioned with the feature's prompt and schema, so a change to either names the
  set version it was scored on.
- **Why:** the same set later serves as a local model's test set, for the release gate (13.1) and
  for any 13.7 question. It is never a training set unless 13.7's question is answered yes.

### 13.7 Fine-tuning: unchanged, with one open question for Stage 10 (4g)

- **IBN_DESIGN section 10's "retrieved, never trained" is unchanged.**
- **Open for Stage 10, decided on local eval data:** whether task adapters are allowed that teach
  format and skill only, never the network's facts.
- **If they ever are allowed,** their training data comes only from Mercury's deterministic
  tools and labelled cases. It never comes from Claude's outputs: Anthropic's commercial terms
  bar using outputs to train competing models.

### 13.8 Planning discipline (4h)

- **The plan details only the next feature,** feature 1 (13.2).
- **Later cards keep their numbers** (section 6). No further design is written for them until
  the slice before them has its measurements.
- Sections 10 to 12's designs for later features stand as written. They are not extended.

### 13.8a Batfish is an optional add-on (the operator, 2026-10-18; the Core 1.0 triage)

- **Batfish (8.5's pre-change verification for routing-affecting changes) stays in Phase 8,
  as an OPTIONAL add-on:** Standard tier and up, never required.
- **A Minimum install validates with Mercury's own checks alone:**
  - `nmas-config-check`;
  - template approval;
  - the intent editor's checks;
  - deploy's preview, verify and rollback.
- Where Batfish is installed, it is an additional check beside these, never a replacement for
  them.

### 13.9 What the CSCI 5280 prototype brings back (part 6)

**The operator's CSCI 5280 Labs 7 and 8** (a natural-language controller, and a closed loop) are
Phase 8's prototype. They are built in their own repository, with no Mercury code. **They
bring back numbers, not code**, for each pattern they exercise:
- **Translator:** Lab 7's natural-language controller;
- **Decision-maker:** Lab 8's closed loop;
- **Analyst:** the operator's Lab 6 formatter and summariser, already done.

| What | Measured how | Why Phase 8 needs it |
|---|---|---|
| **Consistency** over 5 runs on the structured fields | 11.1's method: the same input 5 times, identical structured output counted | the 95% and 90% floors are set without a measurement on a real task |
| **Latency** | time to first token and total seconds per call, median and 95th percentile | section 6's budgets (3 to 5 s) are estimates |
| **Tokens and cost per use** | input and output tokens per call, and the cost at the pinned model's price | section 7's caps ($5 and $10 a month per feature) are estimates |
| **Schema failures** | outputs that fail validation, per 100 calls, with structured outputs on (13.5) | how often the error contract fires on valid inputs |
| **Refusal and max_tokens incidence** | `stop_reason` counts per 100 calls | sizes 13.5's error kinds |
| **Shape A against shape B, for one task** | the same task, the same cases, scored both ways (13.4) | whether a rationale-first field changes accuracy or consistency on Mercury's kind of task |

- **Recording:** each number comes with its model and pinned version, its date and its case
  count. Each lands in feature 1's card as a prototype measurement, distinct from the card's own
  eval.
- **No prototype code or prompt is copied into Mercury.**

## 14. The endpoint direction, after the showcase (the operator, 2026-10-20; docs only)

**Status:** a direction for the public release (Stage 10), recorded before any of it is built.
The first AI release (docs/AI_ANTHROPIC_PLAN.md) is Anthropic only. Its provider layer is
shaped so that what follows is a second provider type, not a rewrite.

### 14.1 AI is an optional service at an endpoint, never bundled

- **Where:** Settings names one endpoint, either Anthropic or an OpenAI-compatible server
  (vLLM, llama.cpp's `llama-server`, Ollama).
- **Never bundled:** Mercury ships no model and runs no inference engine in its own process or
  on its own host.
- **This supersedes 10.4's "Local (built-in)"** (`llama-server` beside Mercury, bound to
  127.0.0.1). The engine moves to a **reference AI host** (14.3), which Mercury reaches as any
  other OpenAI-compatible endpoint. 10.2's origin rule, 10.5's tiers and 10.7's evaluation
  carry over to that host.
- **One adapter per API shape, never per model** (10.3): Anthropic Messages, and
  OpenAI-compatible. **The provider layer hides each server's schema mechanism.**
  - Anthropic's structured outputs (13.5).
  - Each OpenAI-compatible server's own: `response_format` with a JSON schema where the
    server supports it, or a grammar or guided-decoding option where it does not, each
    measured by the conformance suite (14.2).
  - A feature asks for a shape (A, B or C, 13.4) and a Pydantic model, never for a server's
    mechanism.
- **The redactor runs before every endpoint, local ones included.** A self-hosted model is
  still outside Mercury's process, and its logs are not Mercury's.

### 14.2 "Test connection" runs a conformance suite

Pressing **Test connection** on an endpoint runs, against that endpoint and model:
- **the shapes:** A, B and C, each schema-valid over N runs;
- **the eval cases:** each feature's golden cases (section 7: at least 30 per feature);
- **latency:** time to first token and total, median and 95th percentile;
- **context:** the largest prompt the endpoint accepts and answers correctly.

**Each feature is enabled only above its own threshold** (its card's target, section 3). A
feature below it is disabled, naming the measured figure and the threshold. The suite's
result is recorded with the endpoint, model, version and date. **A model change at the
endpoint is detected** (the model id or version it reports, and a canary case's answer), and
the suite runs again before any feature uses it.

### 14.3 The reference AI host

- **What it is:** a VM image or a compose file, built and published with each release, that
  runs one pinned engine and one pinned model. 10.2 holds: the reference model Mercury ships is
  of **US origin**, with no setting to change that for the reference.
- **Air-gapped sites self-host it:** the image and its model file arrive through the offline
  update path (K58, docs/OFFLINE_OPERATION.md), never a download from the site.
- **Hardware tiers:**
  - Minimum and Standard are Mercury alone, with hosted AI or none.
  - Large is Mercury plus the AI host, on the same hardware class or beside it (the charter's
    tiers; 10.5's model tiers apply to the AI host).

### 14.4 What Mercury does with an endpoint

- **Any endpoint, monitored:**
  - availability and latency;
  - error rate, including schema failures, refusals and truncations;
  - conformance drift: a canary case answered differently, or the model's identity changed;
  - cost, for a priced endpoint.

  Each is a job-health row and, when wrong, a Needs attention row with its action.
- **Only the reference host, managed.** Its upgrades are a Mercury operation with the usual
  lifecycle:
  1. **preview:** the bundle's manifest, the engine and model versions, and what the
     conformance suite will run;
  2. **confirm by the bundle's hash**, as a verified person;
  3. **install beside** the running version, never over it;
  4. **verify** by the conformance suite against the new version;
  5. switch, with **instant rollback** to the version kept beside it;
  6. **record** the whole run.

  Mercury acts on that host only through a **least-privilege update agent** there. The agent
  accepts only bundles signed by the release key, runs only the install, switch and roll-back
  verbs, and answers to Mercury's request alone. At air-gapped sites the bundle comes through
  the offline update path.
- **A site's own endpoint** (its vLLM, its Ollama) is monitored and never managed: Mercury
  neither upgrades nor restarts what it does not own.

### 14.5 What stays the same

- The release gate of 12.1 and 13.1.
- The model as an untrusted component (non-negotiable 6), and the red-team set blocking any
  release.
- AI advising and never confirming: the charter's AI-assisted actions.
- Masking before every call.
- An endpoint's feature off, with its reason, when the endpoint is absent or below
  threshold: Mercury without AI is complete.

## 15. Amendments of 2026-10-24 (the operator; documents only)

**Source:** the Phase 8 course-review addendum of 2026-10-24, an addendum to this plan and to
IBN_DESIGN, kept with the operator's reports outside the repository. Its section 8 lists the
decisions the operator ruled on 2026-10-24; the rulings below are recorded as ruled. Nothing is
built. The rulings of 2026-10-13 to 2026-10-20 stand wherever this section does not name them.

### 15.1 The order is unchanged (13.3)

- **Natural language to PromQL or LogQL stays first.** It is read-only and builds the whole 8.0
  foundation at the lowest risk. 13.3 stands, as the first release applies it
  (docs/AI_ANTHROPIC_PLAN.md section 4, F1 first; adopted 2026-10-20).
- **The evidence pack with no AI (P1's deterministic part, 15.9) may be built alongside** as
  ordinary Core work: it calls no model, so it needs no 8.0 piece.

### 15.2 Closed-loop execution leaves Phase 8: Phase 9, the closed loop

- **Cut from Phase 8:** every execution without a person's confirm. That is 8.3 (Respond's
  classes enabled per class), AI catalog selection reaching execution (feature 4, decision 9),
  and 13.3's item 4.
- **Phase 8 keeps observe-mode logging only:** the "would have converged" records, each class's
  false-positive count and feature 4's selections logged beside a person's, none executed.
  The deterministic observe mode itself already runs in Core 1.0's tail (NSOT_PLAN section 9,
  "The path after Phase 7", item 3).
- **8.4 Activate is not a closed loop** (a person's commit starts it, and a management-path
  commit waits for a person), so it stays in Phase 8.
- **Phase 9, the closed loop, is named in the plan** (NSOT_PLAN section 9, the path, under item
  4; docs/COMPLETION_INVENTORY.md's homes). **It is built when the first catalog entry or
  Respond class meets its ruled bar on observed evidence:** 95% measured agreement over at
  least 100 observed selections for catalog selection (section 7), or 1% false positives or
  fewer over at least 30 days and 100 events for a Respond class (section 7). Lab drift drills
  never count as production evidence (section 7).
- **Why it waits** (the addendum, section 5): one operator and a few events a week will not
  reach 100 real events for a long time.
- **Phase 9's prerequisites, which a CLI-driven network needs and an SDN controller supplies**
  (the addendum, section 5):
  1. **Expiry: a revert timer on every autonomous change.** Native where measured on the
     platform; Mercury-scheduled otherwise. IOS-XE is believed to offer
     `configure terminal revert timer` with `configure confirm`, which needs `archive`
     configured; vIOS-L2 15.2 is unmeasured. Neither is measured yet.
  2. **A defined inverse for each catalog entry:** Mode B's measured removal
     (`modules/nsot/removal.py`), never a guessed `no` form.
  3. **Partial-apply handling:** a remediation lands device by device over CLI, never
     atomically, so a half-applied one is undone through `pipeline._stage_rollback`, which
     undoes what landed.
  4. **Cascade limits:** section 7's rails (at most 6 fixes an hour per network and 1 per device
     per hour; the same deviation fixed twice in 24 hours halts its policy), the kill switch
     (IBN_DESIGN section 6, phase 3), and a dead-man's switch.

### 15.3 The provider: Anthropic is the proof of concept

- **Anthropic is the proof of concept behind the provider-neutral gateway; more providers
  follow** behind the same gateway (10.3, 14.1: one adapter per API shape).
- **What this amends in 13.1:** its heading and first bullet read as if Anthropic were the
  product's provider. They mean the proof of concept: features are built and accepted on
  Anthropic first. The rest of 13.1 stands (the release gate, the provider-neutral gateway,
  AI off where no local tier is admitted).

### 15.4 The schema tool: Pydantic v2, strict

- **Pydantic v2 in strict mode** (`strict=True`, `extra="forbid"`) is the only schema tool for
  AI input and output. This makes 13.2's "the schema library (Pydantic)" exact.
- **Generated JSON schemas are committed as files,** one per model and version.
- **`schema_for(model, provider)`** derives what each provider is sent from the committed
  schema (Anthropic's supported subset, 13.5; an OpenAI-compatible server's, 14.1).
- **Limits are enforced by Pydantic in Mercury:** ranges, lengths and counts the provider's
  subset cannot express (13.5).
- **A CI test checks every committed schema against each enabled provider's strict-mode
  subset.**
- **The licence:** Pydantic is MIT, and the `anthropic`, `openai` and `google-genai` SDKs all
  require it, so the choice keeps every provider open. The operator's licence decision for
  Pydantic and the `anthropic` SDK is recorded 2026-10-24 (the register); each enters the lock
  with the first feature that needs it.
- **Settings keep `jsonschema`** (`modules/settings_schema.py`, the settings file, NSOT_PLAN's
  validator choice): this ruling is about AI input and output only.

### 15.5 The runbook format: minimal, declarative YAML

- **A runbook is minimal declarative YAML:** `show` steps, `parse` through `ntc-templates`
  (already in the lock, through Netmiko), `assert_equal`, and a `conclusion`. No branches or
  loops until a real runbook needs one.
- **Stored in the network's config repository,** run only through `reads.run`, with fixtures
  from real captures under the publication rules (documentation addresses).
- **Python stays the escape hatch for human-written registered checks only,** never for a
  runbook.
- **What this refines:** docs/RUNBOOKS_PROCEDURES.md's runbooks (C1147; `runbooks/<slug>.yml`,
  reads inside Show commands' allowlist, parsers and a report). Its section 5 stands: Mercury
  never runs arbitrary or AI-generated playbooks.

### 15.6 Automatic analysis: a button only, until its cost is measured

- **An AI analysis runs only when a person presses its button,** until the cost per accepted
  analysis is measured (section 4's cost dashboard, per accepted output).
- **After that, a per-rule opt-in:** a person enables automatic analysis for one alert rule at a
  time, never fleet-wide.

### 15.7 Day 1 up front before feature 7

- **Day 1 at onboarding (C1471) is built deterministically before feature 7** (natural language
  to intent). Feature 7 then reuses its change-set work: an intent patch per device fed into
  `intent_edit.preview` and the deploy route's plan and apply (docs/designs/C1471-day1-at-onboarding.md).

### 15.8 Hosted AI on the lab's NMAS host

- **AI is off by default on the lab's NMAS host,** which cannot run a local model (10.8).
- **Using AI there needs the admin's hosted-only setting, with a recorded reason** (13.1's
  "hosted AI allowed by an admin's recorded setting", applied to this host).

### 15.9 New candidates: three cards now, five listed

**Cards now (section 3's format, 13.4's output shape):** P1, P2 and E1 below. **Listed as
candidates, no card yet:**
- **P3, change review on the existing preview:** reads the program with Topology and flags
  changes such as "removes the only path to Mercury"; read-only, beside `deploy.dangerous_in`.
- **P4, save as runbook:** a resolved incident becomes a 15.5 runbook, accepted by replaying its
  fixtures. Its card must meet RUNBOOKS_PROCEDURES section 5 (no AI-generated playbook runs).
- **E2, register closure assistant:** proposes closures from each row's "closes when", with
  links; `tests/test_register_hygiene.py` checks the edit.
- **E3, failure to finding:** a failed gate, CI run, verify or mutation run drafts a register row
  in house style, the register searched first.
- **E4:** flake triage across JUnit results; documents checked against the code they cite;
  MANUAL_STEPS LABOUR rows drafted into automation proposals; manual drafts for new screens.
- **Pseudonymised addresses and hostnames** (15.11): a reversible map held in Mercury, applied
  before a payload leaves; a candidate, never a condition of any class.

**E1 and the E candidates are AI applied to Mercury's own engineering,** not product features:
they run in the development loop, never on an installation, so offline parity and the
installation's caps do not apply to them. Each still meets non-negotiables 1, 2 and 4 in kind:
its output is accepted only by a deterministic check.

#### Card P1: the evidence pack, then one "Explain" call

| Field | P1 |
|---|---|
| Problem | When an alert fires, the person gathers the evidence by hand: the alert, the device's recent History (deploys and receipts), its Intent check, its expected and reported neighbours, and the logs around the onset. **Unmeasured:** how often, and how long the gathering takes. The incidents it would have served: C1547 (the Lab 9 redeploy's s3 stalls: OSPF drops and failed scrapes, its cause found by hand from several sources) and C1647 (the VLAN 10 advertisement's path, still UNKNOWN). |
| Deterministic alternative | **The pack itself is deterministic and is built first, with no AI:** triggered by `readers/grafana_alerts.py` seeing an alert transition (no inbound webhook: C1656); built from `history_sources.timeline`, `intent_match.intent_match`, `neighbours.for_device` and the E3/F3 LogQL builder; it mints its own reference ids and hashes itself, because History rows and reader values carry none (C1657). One card per firing alert, useful with AI off. **What the pack cannot do:** say which of its pieces explains the alert, in words, citing them. That one step is the Explain call. |
| Inputs | The pack, masked by the egress mask (C1654), as data delimited from instructions; no tools. Context: **unmeasured** until packs exist; sized by section 4's method (the measured minimum times 1.5). Output schema: Pydantic v2 strict (15.4), versioned. |
| Output shape | B (13.4): a short rationale first, then `{hypotheses: [{claim, evidence_refs[], confirm_with}], needs_human}`. Each `evidence_refs` entry must resolve to a pack reference; each `confirm_with` names a runnable read (`reads.run`'s allowlist), so a claim can be proven before it is shown (the addendum, 7.4). |
| Success metric | 70% of top hypotheses confirmed true by a person (feature 2's target, proposed); 0 references that do not resolve to the pack (a refusal: "couldn't analyse"). Eval set: replayed Lab 9 incidents (C1547, C1647) first, at least 30 cases with 10 real before observe mode (section 7). |
| Compared fields | Analyst (90%, 11.12): each hypothesis's `evidence_refs`, `needs_human`. |
| Budgets | **Proposed by analogy with feature 2** (an Analyst over one group's evidence), until measured: 3k tokens in, 400 out, 5 s, Haiku 5.5; $5 a month (section 7's Analyst cap). A button only (15.6). |
| Observe mode | 30 days and 20 analyses (a rare feature, section 7); the threshold to leave: 70% confirmed. |
| Kill criteria | Below 60% confirmed after 20 analyses, or cost per confirmed hypothesis above 2× budget, or one claim shown with a reference that does not resolve. |
| Owner | The operator. |
| Relation | AI_ANTHROPIC_PLAN's F2 ("Explain a Needs attention row") is the same machinery on a different record; P1's Explain reuses F2's prompt registry entry shape and schema rules. |
| Test plan | The addendum's 7.3: the pack from real stored captures and History, IPv4 and IPv6; a planted secret in every input never in the adapter's outbound bytes; an injection line planted in an interface description changes nothing, and no tool is offered; with AI off, the pack and every screen work; a schema failure and a missing reference refused as "couldn't analyse"; the recorded-response evaluation; a browser test of the card. |

#### Card P2: the "differs" explainer

| Field | P2 |
|---|---|
| Problem | The Intent check says a device "differs" from its intent, and the person works out why. On s5 the cause was that a VTP-server switch keeps its VLANs in vlan.dat and never prints them (C1646, found 2026-10-24 after s5's Day 1 deploy at 00:42 UTC; C1649, measured ~17:4x UTC the same day, s3, s4 and s5). Other causes of the same symptom in the register: a regenerated self-signed certificate (C302). **Unmeasured:** how often a "differs" is not a real drift, and how long each takes to explain. |
| Deterministic alternative | **Most classes are rules, built first:** a VLAN line on a VTP server or client switch (the switch's `show vtp status`, C1649); a difference of order only (the same lines as a set); a line the extractor does not model (its not-modelled list, `unmodeled_ack`); a certificate block (`normalize.strip_self_signed_certs`). **The AI step is only for a difference no rule classifies,** which it labels as one of those classes or "unexplained", citing the lines. |
| Inputs | The unclassified difference's lines (masked by C1654's egress mask; configuration lines, so the network's configuration class must be enabled, 15.11, its secret-bearing lines dropped), the device's platform and VTP mode, the rule classes' definitions; no tools. Context: **unmeasured**. Output schema: Pydantic v2 strict, versioned. |
| Output shape | A (13.4): `{class, lines[], why}` with `class` an enum (`vtp_database`, `platform_default`, `order_only`, `unmodelled`, `unexplained`). |
| Success metric | 80% of labels a person accepts; a difference a rule classifies never reaches the call (a rule's class always wins, shown by test). |
| Compared fields | Translator floor (95%, 11.12) on `class` and `lines`, since a label decides how a difference is shown. |
| Budgets | **Proposed:** 2k in, 200 out, 3 s, Haiku 5.5 (feature 1's shape), $5 a month. A button only (15.6). |
| Observe mode | 30 days and 20 unclassified differences; the threshold: 80% accepted. |
| Kill criteria | Below 65% accepted after 20, or the rules leave fewer than 20 unclassified differences in 60 days (the deterministic classes did the job: the feature is removed, not run). |
| Owner | The operator. |

#### Card E1: the mutation-survivor assistant

| Field | E1 |
|---|---|
| Problem | Mutation runs leave survivors a person must kill with a test or argue equivalent. Counted 2026-10-24: `tests/mutation_debt.json` holds 366 known survivors across 17 functions; C1652 registered 355 pre-existing survivors in the verify and post-snapshot stages for a kill campaign; `tests/mutation_equivalent.py` holds 281 argued equivalent mutants, each read and judged by a person. **Unmeasured:** the time per survivor killed or argued. |
| Deterministic alternative | mutmut generates and runs the mutants, and the coverage map names the tests that reach each function; neither writes a killing test or an argument. A template test cannot: each kill needs the input that tells the mutant from the original. |
| Inputs | One survivor: its function's source, the mutant's one-line diff, the tests that reach the function (the coverage map), and the nearest existing test as an example; no network data. Context: **unmeasured**. Output schema: Pydantic v2 strict. |
| Output shape | C (13.4): JSON metadata (`{verdict: "test" or "equivalent", test_name, why, the_test_that_would_have_to_fail}`), then the test in a delimited raw block. |
| Success metric | **Accepted only by the mutant:** a drafted test is accepted only if it fails with the mutant applied and passes on the original (each mutant applied as mutmut writes it, the tests run, the file restored from a copy). An argued equivalence is never accepted by the assistant; it goes to the operator, as every equivalent does. Target: 50% of drafted tests accepted by that check. |
| Compared fields | Translator (95%, 11.12): `verdict`, and whether the drafted test kills the mutant. |
| Budgets | **Proposed:** 6k in, 1.5k out, 30 s, Sonnet 5.5 where the eval shows Haiku misses; a cap per campaign set by the operator. Runs in the development loop, never on an installation. |
| Observe mode | The first campaign's 50 survivors, every draft checked by the mutant and reviewed. |
| Kill criteria | Below 30% of drafts accepted after 50 survivors, or one accepted test that a reviewer finds asserts nothing (the coverage tool's "asserts nothing" check). |
| Owner | The operator. |

### 15.10 Alert silencing: the rule gains one exception

**Ruled:** "Mercury never silences an alert, except inside a planned-restart window declared
before it acts." The window's silence is what a declared window already sets
(`integrations/grafana.py::put_silence`, behind the `reload_confirm` gate; the manual's Needs
attention page). The rule's two statements are amended to say so: NSOT_PLAN's "Alerts are never
silenced" (Grafana's tiers) and NSOT_GUI_BRIEF section 15's question 3.

### 15.11 Data leaving the host: three classes (the operator, 2026-10-24)

The addendum's egress ruling, as resolved by the operator the same day: a third class,
**configuration**, sits between what may leave and what never does.

| Class | What a cloud model may receive | Default |
|---|---|---|
| **Allowed** | alert labels, metric series, masked log lines, intent diffs | on wherever AI is on for the network |
| **Topology** (the operator, 2026-10-25) | the compiled network model's slice (15.15): devices, roles, sites, platforms, links with their subnets, expected and observed adjacencies; no configuration lines, no secrets | **on by default** wherever AI is on for the network; an admin turns it off per network |
| **Configuration** | configuration lines: goldens, a deploy's program, a captured configuration, the stanzas they touch | **off per network**; an admin enables it per network with a recorded reason (the hosted-only setting's pattern, 13.1 and 15.8) |
| **Never** | credentials, host keys, NetBox secrets, even masked | no setting enables it |

**The configuration class's conditions, each before any configuration line leaves:**
1. **The stricter egress mask ships first** (C1654) and passes the planted-secret outbound test:
   a planted secret in every input never appears in the adapter's outbound bytes.
2. **A line carrying a secret is dropped, never masked:** any line with `secret`, `password`,
   `key N`, `community` or a hash-shaped token is left out of the payload whole, and the
   payload says how many lines were dropped.
3. **The smallest slice a feature needs:** a feature sends only the lines its question needs,
   never a whole golden by default (F2: the program and the stanzas it touches; F3: the diff
   and its context before any full golden).
4. **A classification marking forces AI off,** whatever the class settings say (13.1).
   **Planned, not built** (C1720): until it exists this is no current safeguard, and the
   configuration class stays off on every network.

**The features that now require the configuration class** (each is off on a network until an
admin enables the class there, and says so beside its control):
- **AI_ANTHROPIC_PLAN F2 "Explain"**, for a deploy preview and a failed Verify: the program and
  the stanzas it touches. Explain on a Needs attention row stays in the allowed class unless the
  row's evidence is configuration.
- **AI_ANTHROPIC_PLAN F3 "Ask Mercury"**, for any question whose retrieval reaches a golden:
  the diff and its context first, a full golden only where the question needs it.
- **Section 6's feature 10** (template draft for a new platform): the platform's captured
  configuration, its secret-bearing lines dropped.
- **15.9's P2** (the "differs" explainer): the unclassified difference's lines. P1's pack stays
  in the allowed class: it carries the Intent check's state, never its lines.

**The topology class (the operator's egress ruling, 2026-10-25).** It holds what the network
context model (15.15) sends:
- devices, roles, sites, platforms;
- links with their computed subnets;
- expected adjacencies (OSPF, BGP), and observed ones with their read times.

It holds no configuration lines and no secrets. It is on by default wherever AI is on for the
network, with a per-network off switch. A classification marking is to force AI off
whatever the class settings say (13.1); it is **planned, not built** (C1720), so today the
per-network off switch is the only control. Full intent documents and configurations stay in the
configuration class: the model sends what intent means for the topology (an address on an
interface, a VLAN, OSPF and BGP membership), never the intent document or a configuration
line.

**A candidate, not a condition:** pseudonymising addresses and hostnames before a payload leaves
(a reversible map held in Mercury), listed with 15.9's candidates; nothing above waits for it.

### 15.12 The Phase 8 sprint, Sun 2026-10-25 to Sat 2026-10-31 (the operator, 2026-10-25)

**The goal:** the sprint's Phase 8 features working, deployed and usable on the lab; no video
work. **A feature is done** when it is deployed, its about 20 recorded cases pass in CI, and the
operator has used it on the lab. A deploy every evening (CI green on the exact sha and the
change's own tests; the Update button).

**The sprint's rulings:**
1. **Findings freeze:** a finding is registered, and worked only if it blocks a sprint feature.
   The 2026-10-18 condition "no open A or B" (NSOT_PLAN, Core 1.0) is suspended for the sprint.
2. **Roles move to before the public release;** feature 7 runs for the verified operator only.
3. **11.1's consistency floors are measured daily** during the sprint, and gate only before the
   public release.
4. **Standing delegation:** the agent decides anything inside this plan. It escalates only a new
   licence, egress, anything irreversible, CLAUDE.md, and a change to a ruling.
5. **Reports:** a status of about 10 lines each day; a full report only when a ruling is needed.

**The scope, in order:**

| Day | Item |
|---|---|
| Sun | **8.0, minimal** (13.2): the gateway's Anthropic adapter (the pinned model, timeouts, a cap per call and a cap per day); Pydantic v2 strict schemas, `schema_for` and the committed schema files (15.4); the stricter egress mask (C1654; the irreversible tier, so its targeted mutation run before its deploy); the `ai_calls` store and its History row; the hosted-only admin setting with a recorded reason (13.1, 15.8); the API key in the secrets store, typed by the operator. Prompts are versioned files (section 4). **Beside it:** P1's evidence pack, no AI (15.1, 15.9). |
| Mon | **8.1: natural language to PromQL or LogQL** (feature 1): a deterministic catalogue of metrics and labels, its schema, validation (allowlisted metrics and labels, a time-limited test run), the screen. |
| Tue | **P1's Explain** on the alert cards: one schema-bound call, its references checked against the pack. |
| Wed to Thu | **Feature 7, constrained:** natural language to an intent patch for interface descriptions and shutdown, VLANs and OSPF network statements; checked by the intent editor's validator; through the existing preview, confirm by hash, deploy and verify. |
| Fri | **P2's rules only** (below). |
| Sat | The buffer: evaluation runs, fixes for escapes, a full walk of every sprint feature, and the batched boards and fidelity records (below). |

**Item 9, added (the operator, 2026-10-25; small).** Every Analyst task's recorded cases
include healthy baselines that must report nothing wrong, measured for consistency like the
rest. P1 Explain's come first. **Started 2026-10-25, against prompt v3, now v4 (the network context
and the health figures):** `tests/fixtures/ai_cases/explain/recorded.json` holds C1547's
replay (case 1, the operator's judging rule word for word) and three healthy baselines (the
same rule on r1, output discards on r2, the error-rate rule on s1, each a quiet window of
2026-10-24 outside the backup window). Each case is a replay (`scripts/nmas-pack-replay`):
`cases.explain_unready` says first whether its pack holds what it is judged on (case 1's
evidence measured; a baseline's window shows none of case 1's symptoms, else it is not a
baseline and fails the check, never the model); `cases.explain_misses` judges the answer on
structured fields (outcome, needs_human, what is cited and together, the leading hypothesis
not s3's CPU alone, no percentage the pack does not hold; a baseline no fault found, checking its device's
figures), and
each case's `flag` names what a person judges in the prose. Not recorded yet: nothing has been
asked, and the recorder (each case's pack built, asked five times, judged) is the next step.
Explain had no answer that says nothing is wrong; the operator's ruling (2026-10-25, C1742,
built the same day): schema `explain` v2 and prompt v4 add "no fault found", citing the
healthy evidence it checked (no free-text guess), and the baselines pass on that answer,
measured like the rest: the roadmap's false-positive check. Prompts v1 to v3 keep schema v1,
so a replay asks them as they were.

**Decided at the sprint's start (the operator, 2026-10-25, on the agent's estimate):**
- **Labs first stands:** CSCI 5840's Labs 8 and 9 are submitted (8 on 2026-10-21, 9 on
  2026-10-23). A future lab's step pre-empts a sprint item, and the agent names what slipped.
- **C1471 is a sprint item, unfrozen:** it blocks feature 7 (15.7). Its patch-per-device step is
  feature 7's first piece (Wednesday).
- **Licences:** Pydantic v2 is approved (pydantic, pydantic-core, annotated-types,
  typing-inspection; MIT). **The Anthropic SDK is not taken now:** the adapter is a thin one over
  `requests` (already locked), behind the gateway's interface, with retries and backoff, typed
  errors, rate-limit handling, timeouts, the caps and the pinned model, so taking the SDK later
  changes one module. No PromQL or LogQL parser: feature 1 produces History › Query's builder
  choices (13.2), checked by the builders' own rules and by Prometheus's or Loki's parser in a
  time-limited test run.
- **P2 is rules only this sprint** (the VTP database, order only, a line not modelled, a
  certificate block); its AI step and the configuration egress class (15.11) come after it.
- **`ai_calls` is a records store** with the per-store file or database switch, as the other
  stores are (`modules/records_db.py`, `STORES`). Cost caps, no cost dashboard (13.2).
- **The egress mask's targeted mutation run is within the egress exception** (docs/TESTING.md,
  "Mutation testing", the rule of 2026-10-25): two mutation runs this week, the scheduled weekly
  run and the mask's dispatched one.
- **Each screen ships with its browser tests and a short manual page;** its board and its
  fidelity record are batched into Saturday.

**An exception, and its expiry (the operator, 2026-10-25 ~07:2x UTC; CLAUDE.md's Working
method: an exception names its expiry):**
- **8.0 deploys before its tier run, with hosted AI off.** The irreversible tier's targeted run
  comes before **Allow** (the first hosted call), not before this deploy: nothing the mask and
  the gateway touch can leave the host until a person allows hosted AI with a reason.
- **It expires at the first clean tier run.** Clean: every survivor in `redact_egress`,
  `egress_payload` and the gateway (`modules/ai/`) killed or ruled by the operator. The
  operator does not press Allow until the agent reports it clean.
- **The run:** the first tier run, #62, was invalid (C1677: mutmut's copy lacked `prompts/` and
  `schemas/`, so 17 of the gateway's tests could not run in it); its re-run, dispatched once
  C1677's fix lands, replaces it, and is not a third run this week (the operator). It names the
  key's write path too, `installation_settings.replace_secret`, changed in 8.0b.
- **The final run (the operator, 2026-10-25 ~08:0x UTC: part of #63, not an extra campaign).**
  #63 finishes; its results stand for every function unchanged since its commit (aea2bb76):
  `redact_egress`, `egress_payload`, `replace_secret`, and every gateway function the price
  table's commit did not touch. The final run, on that commit, names only the `modules/ai/`
  functions its diff changed or added: `gateway.ask`, `caps`, `worst_case_usd` and
  `prompt_tokens`; `profiles.cost_usd`, `prices_for`, `cap_per_call`, `task`, `profile`,
  `table`, `prices_age_days` and `cases_off_pin`; `connection.check`.
  `installation_settings.card` changed too, only to draw the read-only table, and is outside the
  tier (it writes, stores and masks no secret). **Clean, for Allow:** #63's unchanged functions
  and the final run's, every survivor killed or ruled by the operator.
- **Amended (the operator, 2026-10-25 ~08:2x UTC): the final run is on the 8.1 commit,** one
  run, so "clean" covers 8.1, whose deploy waits for it; e086407f deploys after 09:10 UTC under
  this exception. The run names the functions above and `gateway.build_request` (its docstring
  changed in 8.1); `nl_query`'s are outside the tier (below). **And `redact.redact_positional`**
  (the operator, 2026-10-25 ~08:5x UTC: C1685, a sealed value masked, fixed now as a sprint
  exception because it is the masking path; the fix rides in the 8.1 commit, so the one run
  measures it).
- **The night of 2026-10-25 (the operator's pre-approval: survivors killed by a test, or the
  dead code that made a mutant unkillable removed; a continuation run and one confirming run,
  at most two):** #64, the final run, measured nothing (C1696), so its 15 functions run again
  as the continuation (label `tier-64b`); #63's other 13 functions with survivors, each killed
  by a test or restructured and every current mutant of it checked by hand first, are
  confirmed by the second (label `tier-63b`). Each summary is read for mutants run (C1683).
  A true equivalent is listed for the operator's ruling, never marked approved by the agent.
  #65 (tier-63b) came back clean: 523 mutants run, 523 killed. #66 (tier-64b) measured nothing
  (C1697): a family of tests fails in mutmut's copy.
- **The sprint's tier proof (the operator's ruling, 2026-10-25 ~15:0x UTC; it expires Sat 31
  Oct, and Stage 10 restores the run bar): no third run.** For Allow, the tier's proof is the
  hand check with a canary and a recorded log. For each of #64's 15 functions:
  - every mutant is applied by hand and the tests run;
  - a planted must-die canary per function must be killed by the tests (a surviving canary
    voids the result);
  - a committed log records each mutant, the test that killed it, and the canary's outcome.
  C1697 is fixed after the sprint. Workflow runs are the weekly measurement only. The held
  batch deploys with hosted AI off: cfa0822b was live at 15:08:23 UTC.
  **Done, 2026-10-25 ~16:4x UTC, at cfa0822b:** 858 mutants, 858 killed; all 15 canaries
  killed; every baseline passed; every file restored identical (docs/TIER_HAND_CHECK.md).
  With #65's 13 functions, the tier is **clean for Allow**, with no equivalent to rule.
- **A change to tier code (the operator's sprint ruling, 2026-10-25 ~23:0x UTC; the same
  expiry, Sat 31 Oct):** the hand check covers the mutants on the lines changed since the
  last proved commit, plus a must-die canary per changed function, logged as before.
  - cfa0822b's full check stands for every other line while their tests are unchanged.
  - The cost: minutes, not the full check's hours (`ask` alone has 535 mutants, about
    100 minutes).
  - The defect class it prevents: an unproved change to the tier reaching the host because
    its proof took too long to run before the deploy.
  - **Its first use** is the batched gateway change and the pin files.
- **A task's request settings are its pin file's** (the operator, 2026-10-25):
  `modules/ai/pins/<task>.json` holds each task's model, bounds, `thinking` and
  `temperature`, with each setting's reason. `profiles.load_pins` reads the files, and
  `gateway.build_request` reads the settings from the pin. Tuning a task is therefore an
  edit to its file, not to the tier's code, and needs no tier check.
  - `ask` still refuses, before anything is sent, a setting the pin's model cannot take: a
    thinking it has no off form for, or a temperature its profile does not list. Haiku 5.5
    and Sonnet 5.5 each list only 1, the default.

**The tier's boundary for the rest of the sprint (the operator, 2026-10-25 ~08:2x UTC; it
expires at the sprint's end, Sat 31 Oct, and at Stage 10 the GO bar returns everywhere,
features included):**
- **The irreversible tier is the single egress path:** the gateway's payload builder
  (`gateway.build_request`, and `ask`'s path from the mask to the send), the egress mask
  (`redact.redact_egress`, `redact.egress_payload`) and the adapter's send
  (`anthropic_adapter.send`), plus the secret-value code docs/TESTING.md's table already lists.
  A change to the egress path gets its targeted run before its deploy.
- **The AI features (`nl_query`, P1's Explain, feature 7) are outside it.** Each reaches the
  model only through the gateway, which `tests/test_ai_boundary.py` holds: no module but the
  adapter names Anthropic's API or its key header, none but the gateway imports the adapter,
  and none imports an Anthropic SDK. Each feature's own tests assert that its prompt carries
  only its allowed-class fields, and that a planted secret (a secret's shape in data an
  exporter or a device wrote, and a stored secret's value in the person's words) is masked in
  the bytes sent. A feature's change needs no tier run.

**The AI day cap is $10.00 for the rest of the sprint (the operator, 2026-10-26; expires Sat
31 Oct, when the operator sets it back to $1.50).**
- The measurements the work needs run without asking about spend: Explain's cases on v4
  once C1754's bound is live, and v5's re-proof in the background, adopted when it is
  scored.
- AI spend is reported in each status update.
- Mercury cannot raise the reminder to set it back (C1751), so END_OF_SESSION.md carries it.

**Tuning pauses for the rest of the sprint (the operator, 2026-10-26; expires with the sprint,
Sat 31 Oct).**
- **The pause.** After Explain v5's proof and the Sonnet comparison, no more tuning of Ask in
  words or Explain in the sprint. Their floors gate the release (sprint ruling 3), not the
  sprint. The one exception is a pin change the Sonnet comparison decides.
- **Its cost:** C1724 (held-out set 2 below its floor) and C1750 stay open past the sprint.
- **The defect class it prevents:** the sprint's days spent chasing a floor while the
  features behind it wait.
- **The order, started as soon as those two measurements are scored** (the operator's
  correction, 2026-10-26: not a day, but after the measurements):
  1. Explain's recorded cases on the adopted prompt, five runs each. That closes C1744 and
     item 9's baselines.
  2. History's record of AI calls (15.14).
  3. C1740's logs half: the logs builder's named days in the viewer's timezone, as the
     metrics half's.
  4. **Feature 7 begins:**
     - its card's egress-class question answered first: full intent, or changed keys only;
     - C1471's patch step reused;
     - pinned to Sonnet;
     - its recorded cases, and a held-out set written before its first measurement.

**Explain v4 against v5, decided by the operator's rule (2026-10-26 ~07:4x UTC: "adopt v5 only
if it fails no case that v4 passes AND costs no more per call than v4; otherwise keep v4"):
v4 kept, and Explain's tuning closed for the sprint.**
- **The measurement:** the six shared packs (three replays including the one-device control,
  three healthy baselines). Both prompts were asked on the same pack in each of five rounds, on
  2026-10-26 (explain-v4.sh's run).
- **Where they differ:** case 5 only, the 8-device scrape stall. v4 missed rounds 2 and 5
  ("no fault found" where an answer is expected); v5 missed round 3. So v5 fails a run v4
  passes.
- **Totals:** v4 28 of 30, v5 29 of 30. Outcome consistency is 5 of 6 for both; analyst
  consistency 3 of 6 for both.
- **Cost per call:** v4 $0.0365 with 1,492 output tokens on average; v5 $0.0370 with 1,512. So
  v5 costs more.
- Either condition alone keeps v4. Explain stays pinned to v4.

### 15.13 AI controls: one mark, and shown disabled when AI cannot answer (the operator, 2026-10-25)

A design rule built in the sprint, holding for every AI surface (docs/NSOT_GUI_BRIEF.md
section 6, "AI controls"):
- **One mark.** Every control that needs AI carries one shared **AI** mark: Ask in words,
  Explain, the intent change in words, the AI card's Test, and any later one. The mark's
  tooltip names the task, its pinned model and its per-call cap.
- **Shown disabled, never hidden.** When hosted AI is off, no key is set, or today's cap is
  reached, the control is shown disabled, with its input not fillable, and gives the reason in
  place. For an admin it also links to Settings › Installation, the AI (hosted) card. It is
  never hidden, and never an error after the fact.
- **Offline parity.** The path beside it that needs no AI stays fully usable: the builder, the
  evidence pack, the intent editor.
- **One registry.** One registry of AI controls. A test fails if a route draws an AI-calling
  control without the mark, or leaves it enabled while hosted AI cannot answer.

**The recorded cases' first live run (the operator, 2026-10-25).** The first live answer
collapsed every device into one line (case 3, "Average CPU usage over the past 7 days":
`avg(cpmCPUTotal5minRev)` over all 9, $0.0009). It guessed the scope instead of asking. The
rule: when the device or role scope is unstated, either return a clarifying question or
default to one line per device; never collapse different devices into one line unprompted.
The prompt is versioned (`nl_metrics` v2), and the judge holds the rule over every case
(`cases.misses`).

**Per-task thinking is deferred (the operator, 2026-10-25).** `gateway.build_request` carries
no thinking setting, so every call runs its model's default (Haiku 5.5: adaptive, effort
medium). The request builder is not changed now. If feature 7 needs a gateway change, a
per-task thinking setting is batched into that one change, under one hand check; otherwise it
waits until after the sprint. Ask in words' latency is reported as p50 and p95 per case, from
v3's five-run measurement.

**v3's five runs and the operator's rulings (2026-10-25).** v3 measured 87 of 100 case-runs
passing and 12 of 20 cases consistent (60%, against 11.1's Translator floor of 95%). Its p50
was 3.59 s and its p95 5.25 s, for $0.0004 a case-run. The rulings:
- **v4** fixes the defaults the runs alternated between: the 5-minute CPU variant, the 64-bit
  counters, a 5m rate window, and no group when one device is named. **It carries worked
  examples** (the operator: a prompt is role, context slice, schema and examples). v1 to v3
  had none. Five examples, each a question and the right fill, demonstrate those defaults: the
  5-minute CPU by device, a 64-bit counter at a 5m rate, one named device ungrouped, an
  unstated scope answered per device, and a total asked for. Each uses device, role and metric
  names no recorded case uses (`edge1`, `edge2`, `edge`, invented CPU names and IF-MIB's
  unicast packets), so the cases still test generalisation, not recall.
- **v4's five runs (on fc1d1f7c):** 90 of 100 pass; 15 of 20 consistent (75%); p50 3.01 s,
  p95 5.04 s. The remaining variance was in the operations. **v5 (the operator):**
  - a gauge is grouped by avg (max when the question says highest or peak), never summed;
  - one interface label, `ifName`: RFC 2863's name as the device's console shows it, the same
    meaning on every vendor, where `ifDescr` is vendor free text;
  - a rate unless a count of events is asked for.

  v5 is measured five times together with `changes`, once it is live.
- **The recorded cases' expectations are checked against the live catalogue before every
  measurement** (`cases.stale`, run by `nmas-nl-cases --check` and first in `--record`). Each
  case's expected metric must be carried by its named devices, else its role, else the
  network's devices. A stale expectation fails the check, before anything is spent, never as
  the model's miss. Cases 11, 13 and 15 were stale: 15 and 11 were corrected from the
  measurement (no switch carries a memory series), and 13 awaited `changes`.
- **v5's five runs (on fad95c6c):** 100 of 100 pass, 16 of 20 consistent (80%); p50 3.23 s,
  p95 5.12 s (C1724). **v6 (the operator)** adds four defaults:
  - a top N only when the question says "top" or a number;
  - no group when the series are already one per interface asked;
  - bits only when the question says bits or bandwidth;
  - "today" a custom range from midnight in the installation's timezone. No such setting
    exists (registered), so the viewer's browser timezone is used, and the drawn result says
    which.
- **The overfitting guard (the operator):** a held-out set of 10 new questions
  (`tests/fixtures/ai_cases/nl_query/held_out.json`), written before v6 was measured and never
  tuned on:
  - its devices are r6, s2 and s5, which the 20 name none of;
  - each case has a metric of its own, which no prompt names;
  - two are ambiguous and one is healthy-nothing;
  - its expectations come from the live catalogue, behind the stale check.

  v6 is measured on the 20 and on the 10, five runs each, reported apart. **The held-out
  consistency is the score that counts for C1724.**
- **v6 measured (774ee1bf, 2026-10-25 21:1x to 21:2x UTC):**
  - the 20: 99 of 100 pass, 19 of 20 consistent (95%, at the floor);
  - the held-out 10: 45 of 50 pass, 8 of 10 consistent (80%, below the floor). This is
    the score that counts. Case 7's five misses are Mercury's no-match answer, not the
    model's (C1743).
  - $0.0516 for the 150 case-runs.

  Not tuned on; no v7 until the operator has seen v6 (C1724).
- **The operator, having seen v6 (2026-10-25):** C1724 stays open.
  - **v7** carries C1740's spans ("yesterday", "this week" and "last week" as calendar
    spans in today's timezone, each start given as data) and only general defaults from the
    20, never from held-out misses: one, the per-CPU MIB over the older average (case 3).
  - **Held-out set 1** is seen and retired as a test.
  - **Held-out set 2** (`held_out_2.json`) is ten new questions, written before v7 is
    measured. No lab device is new to both sets, so it uses r6, s2 and s5 (which the 20 never
    name), with metrics new to both sets and no prompt names, and asks the named spans.
  - **Scoring (ruled after set 1 was seen):** on a case expecting a question back, Mercury's
    own guidance counts as a pass (C1743).
  - **The batched gateway change, now:** thinking per task (`profiles.THINKING`; a model's
    own form, `disabled` on Haiku 5.5, `between_tools` on Sonnet 5.5), with a run able to ask
    either (`nmas-nl-cases --thinking`).
    - The API rule, confirmed first (the claude-api reference, Haiku 5.5's breaking change
      2): its temperature must be 1, so a lower one is a 400, thinking on or off; only
      thinking off is built.
    - Proved by the tier's hand check.
    - v7 is measured with and without it on the 20 and on set 2. **Set 2's consistency
      decides** the pin.
- **v7 measured (8e49b197, 2026-10-26 00:50 to 01:1x UTC), five runs each:**

  | Thinking | The 20: pass | The 20: consistent | Set 2: consistent | Set 2: pass (as written / corrected) | p50 | Cost |
  |---|---|---|---|---|---|---|
  | adaptive | 99/100 | 95% | **70%** | 29/50 / **38/50** | 3.06 s | $0.055 |
  | off | 84/100 | 60% | 40% | 37/50 / 45/50 | 1.44 s | $0.030 |
  | Sonnet 5.5, adaptive (set 2 only, a comparison) | not run | not run | **90%** | 39/50 / 39/50 | 2.72 s | $0.26 (about 13x a question) |

  - **The Sonnet comparison** (3fd1ff4f, `nmas-nl-cases --model`; no pin change):
    - Sonnet misses case 7 five times out of five, answering "flapped" as
      `changes(ifOperStatus[1h]) > 0`, counted. The 20's case 13 expects `changes` on
      ifOperStatus, so whether set 2's case 7 accepts it is the operator's ruling, as cases 2
      and 3 were.
    - It refuses case 8 (C1750) every time, and case 1 once.
    - The pin decision is the operator's.
- **Explain v5's proof is void (C1754):** 50 of its 60 calls stopped at the pin's 1,024
  output tokens (v4 answered 6 of 30, v5 4 of 30; $1.92). It is re-run once the provisional
  8,192 bound is deployed.

  - **Adaptive stays the pin; nothing changes in `pins/nl_query.json`.** Set 2's consistency
    decides, and is still below the floor, so C1724 stays open.
  - **Set 2's cases 2 and 3 were corrected** after the first runs, by the operator's ruling:
    the 64-bit counter is the prompt's own default and the right one, as 32-bit counters
    wrap. The corrected score counts, and both are shown once.
  - Case 8, a refusal on an unknown role, is C1750: registered, not tuned on.
- **The offer** is narrowed by a named role's devices as well as by named devices.
- **Case 15** expects `cpuAvgBusy5`, as measured: s3 and s4 carry no `cpmCPUTotal` series.
- **Case 13:** the metrics builder gains a `changes` operation (PromQL `changes()` over the
  range; deterministic, outside the tier, tested like the other operations). Case 13 then
  expects `changes(ifOperStatus{device="s1"}[1d])` or the builder's equivalent. If it cannot
  land this sprint, the expectation is the `ifOperStatus` graph for today instead; never a
  refusal.
- **Sprint ruling 3:** 11.1's floors are measured and gate before release. Ask in words stays
  on, since every answer only fills the builder for the person to check.
- **The batched gateway change** (only if one happens anyway): per-task thinking off for
  `nl_query`, measured against v4. The API's rule, confirmed: Claude Haiku 5.5 returns 400 for
  any non-default `temperature` or `top_p`, with thinking on or off. So no lower temperature
  can be sent to it (11.11's per-model temperature has no effect on Haiku 5.5).
  `thinking: {type: "disabled"}` is accepted at effort high or below.

**A truncated answer is refused whole (the operator, 2026-10-25; 2 of the first 24 live calls
ran past `max_tokens`).** The gateway reads the stop reason before the answer. A
`max_tokens` stop is recorded as `max_tokens`, even when the answer is complete and valid,
and nothing is filled or shown. The builder is redrawn as the person's form carried it, with
"Not filled: the answer ran past max_tokens (N)", and the alert card says "Not explained: …".
The cause was the bound, not the prompt. Haiku 5.5's adaptive thinking is on by default, and
the answers of about 100 tokens used 346 to 978 in all. `nl_query`'s bound is now 2,560
(C1698). The Sonnet tasks' bounds are C1699.

### 15.14 History's AI calls (the operator, 2026-10-25; 13.2's History record; built after 15.13)

**One home.** AI calls stay in the main timeline as their own kind (`ai_call`), behind the
kind filter. There is no separate tab.
- **Each row:** when; who, or "scheduled"; the feature and its subject (the device, the alert
  or the query); the model; tokens in and out; cache write and read; the cost; and the
  outcome (accepted, refused by validation with the reason, or used or not).
- **Expanded:** the prompt exactly as it was sent (the masked bytes that left the host, never
  the unmasked form) and the response as received, verbatim, with the prompt's and the
  schema's versions. A large prompt is collapsed, with a note of its size.
  - **Its form (the operator, 2026-10-26):** "the exact wording of the prompt that was
    given and the exact structured response from the AI when expanded, similar to how device
    configuration changes have a window in their history record to show what was changed".
  - So it mirrors a commit's change window (`/v2/history/commit/<sha>`, drawn when the row is
    opened): the opened row fetches `/v2/history/ai-call/<id>` and draws two windows.
  - **Sent:** the instructions' text, each context block and each data block by its name,
    with the model, `max_tokens`, thinking, and the schema's name and version.
  - **Received:** the structured answer, its fields laid out for reading, with the raw bytes
    kept in the record.
  - Both are masked again on the way out. A secret shows only as its mask, because the
    unmasked prompt never left the host and is never stored.
- **Links both ways.** The feature's own "filled from your words … $x" line links to its row,
  and the row links to what it produced.
- **Recorded at the source.** The subject is written with the call. The use is its own
  append-only row, keyed by the call's id. Old rows stay readable (expand, then contract).
- **The test.** A secret planted in a question never appears in the stored prompt or the
  drawn one.
- **A device's History tab** shows the AI calls whose subject is that device.
- **Retention (the operator's ruling).** The metadata is kept like the rest of History: when,
  who, feature, subject, model, tokens, cost, verdict and use. The request and response bodies
  are pruned after 90 days by default, a setting. The pruning ships in a release later than
  the field (expand, then contract).
- **Built 2026-10-26 (part A):**
  - the subject written with the call (`gateway.ask(subject=)`) and the use rows
    (`calls.record_use`, from Explain and Ask in words);
  - the row, its record and the device tab's filter;
  - Show the prompt and the answer, with its window. The window gives the request's bound,
    thinking and why the answer stopped, then each part sent and the answer received (shots
    and fidelity records: docs/fidelity/history.md, tab-history.md);
  - a failed call, or one whose answer its feature refused, is drawn in danger.

- **Built 2026-10-26 (part B):**
  - the links both ways: Explain's answer ("This call in History") and Ask in words' filled
    notice ("this call in History") link to `/v2/history?call=<id>`, that one call opened
    however old; the row's "Open what it produced" opens its last use row's page and anchor
    (only a page of Mercury's own), Ask in words' fill recording the builder's address with
    every choice it filled;
  - the paging below, for History and a device's History tab (which draws 50 now, 30
    before): each row's id (an AI call's own id; any other the sha1 of its kind, time,
    commit, devices and words), Load more's cursor `before=<time>~<id>`, Jump to's `on=`,
    and the filters, all in the address (shots and fidelity records: docs/fidelity/history.md,
    tab-history.md; tests/test_history_paging.py).

  **Not yet:**
  - the bodies' retention setting and its pruning (a later release, as above).

**The timeline's paging (the operator, 2026-10-25), for History and for a device's History
tab alike:**
- **Paging.** The timeline loads 50 rows. "Load more", at the bottom, fetches the next 50
  older than the last one shown, by a keyset cursor on the time and the id: never an offset or
  page numbers, so rows that arrive meanwhile do not shift it.
- **Jump to date.** A "jump to date" control starts the timeline at a chosen day.
- **Filters.** The filters (kind, device, who, AI calls) apply on the server and combine with
  both.
- **The URL.** The cursor and the filters live in the URL, so Back and a shared link return
  to the same place.
- **Scale.** At large-fleet scale, a test with many thousands of events checks that each load
  stays bounded, in time and in rows.
- **As built (2026-10-26):**
  - **The cursor.** Rows of one time keep their stores' order (git's, for commits within one
    second), and the cursor resumes after its row's id among the rows of its time, so no
    second's rows are lost or drawn twice at a page's edge.
  - **Each source is asked for rows older than the cursor.** It keeps its rows at or before
    the place before its newest-N cut (`_recent`, git's `--until`), so one read reaches any
    depth. The five whose store's reader takes only a count (`UNPAGED`: receipts, app updates,
    Show commands, Tier 2 and console runs) are read again for more when a page needs it: at
    most 4 reads a source a load, 3,200 rows a read. A page past that names them under its
    rows.
  - **A kind filter reads only the sources that can hold its kinds** (`SOURCE_KINDS`).
  - **Scale is measured as work counted, never time** (CLAUDE.md's performance rule): 6,000
    events in each of two stores, every load 50 rows and at most 4 reads a source.

### 15.15 The network context model (the operator, 2026-10-25; in the sprint: it improves P1 Explain, and feature 7 needs it)

- **A compiled network model, with no model call to build it.**
  - **Its sources:** NetBox (devices, roles, sites, platforms, cables) and committed intent
    (interfaces, addresses, VLANs, OSPF and BGP membership). It reuses `topology_expected`
    and `neighbours.ospf_links`.
  - **What it holds:** nodes, and links with their computed subnets and expected adjacencies.
  - **Its version** is the intent's commit sha and NetBox's change. It is rebuilt only when
    either changes.
- **`context_for(subject, hops=1)`** gives the subgraph around a subject.
  - It is overlaid with the observed neighbours, each with its read time.
  - It is compact YAML, with stable ids the model must cite.
  - A source that could not be read is stated as such, never omitted.
- **Prompts put the stable context first** (the network summary, the notes when they exist,
  the schema) for caching. The event or the question comes last.
- **P1 Explain uses it now; feature 7 next.** What it sends is the topology class (15.11).
- **The pack carries its own context (the operator's ruling of 2026-10-25, built as part of
  P1: C1712, C1714).**
  - **The observed overlay is captured into the pack when it is built** (its `observed`
    section, hashed with it), "as of" the alert's time; Explain overlays that capture and
    never reads live state for a past alert. A pack without one says so.
  - **Health figures over the incident's window** for the alert's device and every device
    within two hops (a shared segment's members are one hop): CPU, heartbeat gaps, failed
    scrapes, interface discards, each with its read time and an id the answer must cite
    (`health:<device id>:<figure>`). **The operator's correction (2026-10-25): they summarise
    the window from 15 minutes before the onset to the alert's time, never one instant,** each
    as min, avg and max with the peak's time (heartbeat: the longest gap and when it ended;
    scrapes: when the failures were), so a spike during the trouble shows even when it has
    passed by the alert; one compact line per device per figure.
    Topology detail stays at one hop. They are the allowed class (metric series). With the
    topology class off, only the alert's device's own go: which devices sit within two hops
    of it is topology (a reading of 15.11 taken when building it, the closed direction;
    confirmed by the operator, 2026-10-25: neighbours' names with their figures would reveal
    adjacency, which is topology).
  - **Explain's prompt v3** tells the model to cite figures by id, never to state one the pack
    does not hold, to say when a device's own figures do not explain it, and to offer an
    unevidenced cause only as such, with what would confirm it.
  - **The replay** is `scripts/nmas-pack-replay`: the pack built as of a past time from
    Prometheus and Loki as they held it, and Explain asked as v1 and as v3, each call's tokens
    and cost printed.
- **Reported:** tokens and cost per Explain call, before and after, on a replayed Lab 9
  incident.
- **The replay is C1547** (Lab 9, hour E, 2026-10-22 07:25 to 08:25 UTC: the routers' OSPF
  drops while s3 stalled; still within Prometheus's and Loki's retention). Its known cause
  (the lab host's CPU 22 at about 96%) is in no store Mercury reads. **Explain is judged on
  honest reasoning at the edge of its evidence (the operator, 2026-10-25):**
  - it ties the routers' OSPF drops to s3's symptoms: the heartbeat gaps, failed scrapes and
    discards;
  - it notes that s3's own CPU peaked at 57%, so the device does not explain itself;
  - it offers resource contention beneath s3 (the host or hypervisor, or the link) as an
    unevidenced hypothesis, with what would confirm it;
  - it never invents a figure.

  A confident "s3 CPU overload" is a fail. This is P1 Explain's first recorded case, beside
  item 9's healthy baselines (15.12), in `tests/fixtures/ai_cases/explain/recorded.json`.
- **Measured, 2026-10-25 ~21:2x UTC** (774ee1bf; the pack built as of 08:20:00 with every
  section read; Claude Sonnet 5.5, no cache read on either call):

  | Call | Input | Cache write | Output | Cost |
  |---|---|---|---|---|
  | v1 (the six sections, no topology, no health) | 5,542 | 1,519 | 1,005 | $0.0249 |
  | v3 (the topology, 7 devices; health for 11 devices within two hops) | 16,283 | 3,711 | 908 | $0.0509 |

  **Judged by the operator's rule, v3 meets two tests, partly meets one and misses two
  (C1744):**
  - Met: it invents no figure (every one it states verified in the pack), and it never
    calls s3's CPU overloaded.
  - Partly met: it offers the host or hypervisor beneath the devices as "not in the
    evidence", but its confirming read is a device log read, which cannot show a host's
    contention (the allowlist offers device reads only; C1722).
  - Missed: it ties r1's drop to s4, the neighbour the log names, and offers s3's
    disturbed segment (discards to 23.1/s, a 668 s heartbeat gap) only as a second, hedged
    hypothesis.
  - Missed: it never cites s3's own CPU (57.0, peaking at 07:44:25), so it never says the
    device does not explain itself.

  v1 misses the same two and offers no host hypothesis. The case judge
  (`cases.explain_misses`) misses both on the same two checks.
- **The operator's revision (2026-10-25, after reading the pack):** every router's CPU
  peaked near 08:12 (r1 66, r2 67, r4 71, r6 67), with failed scrapes everywhere. That is a
  shared-host signature, and the real cause. An answer citing those simultaneous peaks as a
  common cause beneath is better than one pinned on s3 (57%, the lowest).
  - Case 1 accepts either line (`one_of`): a common cause (one hypothesis citing the CPU or
    scrape figures of three or more devices), or the drops tied to s3 with its CPU cited.
  - **Under it, v3 passes the judge** on its third hypothesis's scrape figures (r1, r2, r3).
    On the CPU peaks alone it would miss, as it cites only r1's. v1 still misses.
  - The verdict stands once the operator has read both answers' text.
- **The operator's ruling, 2026-10-26, having read both answers:** the s3-centred check is
  replaced.
  - The case now asks that r1's drop be tied to its neighbour s4's symptoms (the heartbeat
    gap, the failed scrape).
  - It asks for a shared cause beneath (the host or hypervisor), offered as a hedged
    hypothesis citing cross-device evidence (scrape failures, heartbeat gaps or CPU peaks
    across devices), and for no invented figure.
  - **v3 passes; v1 misses both.**
- **Explain v5 candidate** (general Analyst guidance, never C1547-specific): "when symptoms
  appear on several devices in the same window, consider a common cause beneath them early,
  citing the cross-device evidence". It is proved only on two or three newly replayed
  incidents plus the healthy baselines, never on C1547.
- **A trim of the health section, approved by the operator (2026-10-26): one line per
  device, every device kept** (C1547's pack, 11 devices).
  - The health section is about 5,600 of v3's roughly 20,000 input tokens. That is an
    estimate: the sizes at 2.12 characters a token, measured on v1's call.
  - **One line per device**, each figure in a few words with its id implied
    (`health:<device id>:<figure>`), is about 810 tokens. That takes v3 from 16,283 input
    tokens and $0.0509 to about 11,500 and $0.041. Nothing cited is lost: the pack keeps the
    pieces, and the check resolves against them.
  - **Health only for devices whose figures moved** saves little here: 9 of 10 devices moved,
    as on any shared-host incident. It would also drop the healthy evidence a no fault found
    answer must cite (C1742), so it is not proposed.

**Gaps made explicit, and the endpoint layer (the operator, 2026-10-26 ~06:5x UTC; after
feature 7's parts 1 and 2, by the operator's ruling the same morning).** Industry need:
endpoint location is a core NetOps capability, the "where is this host?" question every
NetOps platform answers from the MAC and ARP tables. Flows remain roadmap. In this order:
1. **Coverage.** Every `context_for()` bundle carries a coverage header listing each layer
   (inventory, intent, adjacency, performance, events, endpoints, flows) as present, partial or
   not_collected, with its source and age. The prompts tell the model to say when an answer
   depends on a layer that is not_collected, rather than infer it.
2. **The endpoint layer.**
   - Per device, the MAC table and ARP, read through the drivers (platform-pack entries, not
     IOS-only code).
   - DHCP leases through an optional integration (Kea first, the interface generic).
   - Each entry with its last seen.
   - Observed endpoints are stored as MAC, IP, hostname if leased, device, interface, VLAN and
     last seen, versioned like the rest of the model.
   - Entries learned on trunks or uplinks are ignored for location.
   - Feature 7's "port to X" then prefers observation over description, and reports a
     disagreement between them as drift (C1772, pulled forward).
3. **Needs.**
   - Each AI answer schema gains an optional `needs` list, its kinds from a fixed enum
     (endpoint_location, interface_state, neighbour, route).
   - **The round lives once, in a shared module (`modules/ai/needs.py`), which every feature
     calls; features never loop themselves.** It owns the enum's validation, the read-only
     lookups through the existing readers, the hard cap of one follow-up, and the parent and
     child link.
   - The follow-up is a second, ordinary `gateway.ask`; the gateway is untouched (frozen this
     sprint). An unknown kind and a second round are refused. A lookup that fails is reported
     as unfulfilled, never retried.
   - Lookup results enter the follow-up prompt through the context builder, so their egress
     class applies. Endpoints (MAC, IP, hostname) are the topology class, so with a network's
     topology switch off the need is unfulfilled (egress), and the answer says so.
   - Needs, fulfilled or not, are recorded in ai_calls. History shows the two rows linked, the
     round's combined cost on the parent, with a filter and a "context gaps" count by kind.
4. **Tests:** the coverage header present and accurate per layer; a needs round capped, and
   refused for an unknown kind; endpoint location ignoring trunk-learned MACs; drift reported
   on a mismatch. Recorded cases for Ask in words and Explain with endpoints present and with
   them not_collected; the stale-expectation check first. Read path only: no device changes,
   nothing on s3 beyond reads, nothing in 08:30 to 09:10 UTC.

- **Built 2026-10-26 (1, coverage; C1777):** `network_model.coverage`, in every
  `context_for()` bundle and its answer: each layer present, partial or not_collected, with
  source, age and why. Performance and events are as the caller carries them (Explain: the
  pack's health and logs). Endpoints are not collected until 2 lands; flows are roadmap.
- **Built 2026-10-26 (2, the endpoint layer; C1772):** `modules/endpoints.py`,
  `modules/readers/endpoints.py`, `modules/lease_sources.py`, the platform-pack entries
  `modules/nsot/platform_reads.json`. MAC table, ARP and IPv6 neighbours are read per device
  through its dialect's entries, each command only when the read-only allowlist takes it.
  Leases come through the generic source (Kea's first). A trunk's or uplink's MAC locates
  nothing; each endpoint keeps its last location and when. Feature 7's "the port to X" prefers
  observation and says drift.
  - **Measured first:** an idle host's MAC is forgotten in minutes (s1, 2026-10-26), so
    location is passive with last-seen. Active refresh is the operator's decision (C1779).
  - **Not yet:** the evidence pack's capture of endpoints, and the endpoint cases (C1778).
- **Built 2026-10-26 (3, the needs helper):** `modules/ai/needs.py`, outside the gateway.
  - `validate`: a kind not in `NeedKind`, or a malformed need, is refused, naming it, and never
    looked up.
  - `lookup`, read-only, once: endpoint_location from the endpoint store (with last-seen),
    neighbour from the network's neighbours, interface_state from committed intent. Route is
    unfulfilled ("the route layer is not collected"). A lookup that raises is unfulfilled,
    "not retried". With the topology class off, every need is unfulfilled, "egress: <why>",
    and nothing is looked up.
  - `run`: refused for a call that is itself a follow-up (its subject names a parent) or that
    had its round already. Otherwise the needs, fulfilled or not, are recorded on the parent's
    use row (`calls.record_use(..., needs=...)`), and the feature's own `gateway.ask` is called
    once, its subject linked `{"parent": <call id>}`.
  - **Not yet (C1780):** no answer schema carries `needs` and no follow-up prompt takes the
    lookups through the context builder. Each is a new prompt version, the operator's decision
    while Explain's tuning is closed. History's link, combined cost, filter and "context gaps"
    count need a board.
- **Not yet (1):** the prompt line ("say when an answer depends on a layer that is
  not_collected"). It is a new Explain prompt version, so it waits on the operator: Explain's
  tuning is closed for the sprint by the operator's rule of the same day.

### 15.16 Feature 7's egress: the touched sections' current values, never the intent document (the operator, 2026-10-26)

The order's item 4 asked first: does feature 7 send a device's **full intent**, or **only the
keys the change is about**? **The operator's ruling (2026-10-26, the overnight order):** "send
only the schema of allowed keys and the current values of the intent sections the request
touches (e.g. that interface, those VLANs, those OSPF statements) for the named devices; never
a full intent document, never secret-bearing keys. Treat these as the topology class." With
it: "any change outside the devices/keys the request names is refused before preview".
- Full intent stays where 15.11 put it, the configuration class, off on every network until
  C1720. An earlier draft of this section (the agent's, the same night) sent every interface's
  name and state but no description text; the ruling replaced it before anything was built on
  it.

**What feature 7 sends** (`modules/ai/intent_words.py`):
- **The schema of allowed keys,** in the cached prefix: `interfaces[].description`,
  `interfaces[].shutdown`, `vlans[].id` and `.name`, `routing.ospf[].networks` by process,
  with the operations and their fields.
- **For each device in scope, the sections the sentence touches, with their current values:**
  - each interface it names (name, description, shut state);
  - each VLAN it names (id, name);
  - when it names a network, each OSPF process by its number with the named statements and
    their areas;
  - what it names that the device does not hold (`not_held`), and the platform and role.
- **What the sentence touches is read by code, never by the model** (`touched`): interface
  names in their written forms (`ifnames.canonical`: Gi0/1, GigabitEthernet 0/1), VLAN numbers
  after "vlan" ("Vlan10" is an interface), network prefixes (an address and wildcard or mask
  read as its prefix; an IPv6 prefix kept, for the patch to refuse by name).
- **Scope:** on a device's Intent tab, that device alone; another device's name in the sentence
  is only words (a description names its neighbour, "uplink to r1"), and an answer changing
  that device is refused by the scope check before any preview. Elsewhere, the devices the
  sentence names. (Until 2026-10-26 a sentence naming another device was refused before any
  call; the first measurement showed it refusing two valid descriptions every run, C1770.)

**It never sends:** the intent document; any section the sentence does not touch; any key
outside the allowlist (`READS`), so no address, account, AAA, SNMP, NTP, logging, banner or
secret reference.

**How it is held:**
- The slice is an allowlist over the committed document, tested on the host's real committed
  r2 and s1: every other leaf (at least 150 checked), a planted description on an untouched
  interface and a planted secret reference are absent from its bytes; keys planted inside a
  touched section are not read (tests/test_ai_intent_words.py).
- **Refused before preview** (`to_patches`): an operation on a device out of scope, or on an
  interface, VLAN or network the sentence did not name; one filling a field its op does not
  use. The patch's own rules then hold (`intent_patch.parse`), and `intent_patch.apply`
  refuses what the intent lacks.
- **Mercury answers itself, no call:** a sentence naming no device in scope, or no interface,
  VLAN or network (C1770 removed "another device than the tab's").
- Every operation then goes through the intent editor's preview. The commit and the deploy
  after it are the existing paths, unchanged (feature 7 is built to the preview tonight).

**What this costs:** "shut the uplink" names no section, so Mercury asks for the interface's
name rather than sending the device's interfaces for the model to choose from. Part 1 below
answers it.

**Feature 7, parts 1 and 2 (the operator, 2026-10-26 ~06:4x UTC), in this order:**

*Part 1, how people name things*, resolved in the pre-check, by code, before any call; the
model receives resolved names only:
- **Shorthand**, canonicalised as the device names it, per platform (G, Gi, Gig, gi to
  GigabitEthernet; Te, Fa, Po, Lo, Vl, Tu), reusing the existing normaliser, and only when the
  interface exists on the device.
- **References**, from the network model (cables and observed links) and committed intent:
  - "uplink(s)", "the uplink to r1": ports toward a router or the management path;
  - "trunk(s)"; "the VLAN 10 ports";
  - "host port(s)", "the port to h1": see the ruling below.
  - A plural word ("host ports", "all host ports") means every match.
- **One match:** used. **Several, with a singular reference:** Mercury asks before any call,
  each candidate a button naming its neighbour, plus "Both" or "All N"; the choice continues
  the same draft. **No match, or a name the device lacks:** said, the device's real interfaces
  as buttons, and a link to Neighbours.
- **The draft shows every resolution** ("host port -> GigabitEthernet1/0 (by role)", "G1/0 ->
  GigabitEthernet1/0"). The resolved interfaces are the request's scope; anything else is
  refused before preview.
- **Host ports (the operator's ruling of 2026-10-26, measured first: Mercury's inventory, NetBox
  and the Topology read hold no host, and s1's host-facing ports have no cable or LLDP
  neighbour):**
  - "Host port" resolves structurally and never from a description: an access port, enabled in
    intent, with no managed neighbour (no cable, no observed link). An access port shut in
    intent is not a host port unless named directly, so unused ports never inflate the
    candidates.
  - The description is only the button's label and the match for "the port to h1", by word
    boundary (h1 never matches h10).
  - The preview says which: "host port -> GigabitEthernet1/0 (by role)", "port to h1 ->
    GigabitEthernet1/0 (by description 'h1 - VLAN 10')".
  - Observed endpoints (MAC table and ARP read per device, DHCP leases through an optional
    integration, with last seen) come after the sprint, C1772. When present, "port to X"
    prefers observation over description, and a disagreement is reported as drift.
- **Cases:** shorthand in several forms; a one-match reference; a several-match singular
  (asks); a several-match plural (changes all); "both" chosen; none matching; a name that does
  not exist; an injection inside a reference.

*Part 2, commit a drafted change:*
- **"Commit this draft"** on the draft card: a verified person commits the drafted patch as an
  intent commit through the existing write path (`repo.commit`), with trailers `Source:
  ai-draft` and `AI-Call: <call id>`, the person as Actor. Refused if the intent moved since
  the draft (the existing at-commit check) or if the patch differs from the drafted one.
- **"Commit and plan deploy"**, one step to the existing preview; the deploy path after it is
  unchanged (preview, confirm by hash, apply, verify, rollback on failure). Never
  auto-confirmed. **"Discard draft"**; an uncommitted draft never persists past the page.
- **History links both ways:** AI call, intent commit, deploy receipt.
- Tests: refused on moved intent, on an unverified person, on a differing patch; the trailers
  present; the links drawn.

*With them:* a **stale-expectation pre-check** for feature 7's cases, as nl_query's: each
expectation validated against the committed intent and the network model, run first in every
recording; a stale one stops the run before any call. Then parts 1 and 2's new cases, five
runs each, reported for pass, consistency and cost. When both parts are live, the operator
walks it on s1.

- **Built 2026-10-26 (the stale-expectation check, a0165710):** `intent_words.stale`, each
  case's expected change put through the real path with no call; first in every recording
  (exit 5), alone with `--check`.
- **Built 2026-10-26 (parts 1 and 2):**
  - **Part 1:** `modules/ai/intent_names.py` resolves shorthand and references on the tab's
    device before any call. A port's neighbours are the model's point-to-point subnets and the
    Topology read's physical links; a shared segment names no neighbour. References mean
    ports, never an SVI, loopback or tunnel. The resolution step is the operation's `resolve`
    step. The draft lists how the words were read; Mercury's own question carries the
    candidates and Both; a name the device lacks lists its interfaces and links Neighbours.
  - **Part 2:** `intent_words.commit_draft` and `intent_v2.words_commit`. Each draft's digest
    (device, patch, base) is on its call's use row, and a commit handed anything else is
    refused. The commit goes through `intent_patch.commit`, with `Source: ai-draft` and
    `AI-Call:`. Commit and plan deploy opens the deploy preview. A draft that changes no
    configuration line offers no commit (C1771).
  - **History:** the call's use row "committed to intent" names the commit, and the commit's
    row links the call (its `AI-Call:` trailer).
  - Board F7 was redrawn (canvas versions 146 and 147); 16 part 1 cases are in
    `tests/fixtures/ai_cases/intent_patch/names.json`.
- **Built 2026-10-26 (C1775):** a deploy's receipt records the intent commit it rendered;
  History links AI call, intent commit and deploy receipt both ways (`?commit=<sha>`).
- **Live 2026-10-26 09:10 UTC (13505da8).** Confirmed on the host as the operator, in-process:
  - the Intent tab draws Change it in words;
  - the host-port ask draws Mercury's question with no call ($0);
  - a chosen port drafts Commit this draft and Commit and plan deploy ($0.0081, nothing
    committed);
  - the deploy preview draws "nothing to send".
- **Part 1 measured live, 2026-10-26 09:1x UTC** (13505da8, five runs; the stale-expectation
  check first, 0 stale): **80 of 80 runs pass, 16 of 16 cases consistent**, latency p50 4.0 s,
  **$0.1261** (65 calls, about $0.0019 each; case 16, the injection, the dearest at $0.0036 a
  run).
  - Cases 10 (the host port, choose), 14 (the port to an unknown host) and 15 (no such
    interface) made **no call** in any run: no call id, $0. The record grew by exactly 65 rows
    (1,301 to 1,366), the runs that called.
- **Observed endpoints** were built afterwards (C1772, 0c23bf99), with the network context's
  order above.

## 16. Industry-readiness roadmap (2026-10-25)

**The source:** the CSCI 5280 Lab 8 review, read as evidence of what industry needs, not as a
lab to complete (the operator, 2026-10-25; docs and register only). These are post-sprint
candidates. Each gets a feature card in section 3's format, its industry need included, before
any code. The order is the operator's.

### 16.1 Straight after the sprint: the foundations Phase 9 depends on

1. **An action catalogue with risk classes.** Every action Mercury can take, whether a person
   or automation triggers it, is classified on three axes:
   - **Blast radius:** a port or host, a device, a path, the network.
   - **Reversibility:** self-expiring, golden-restorable, manual.
   - **Plane:** management, control, data.

   The classes drive approvals, the GUI's warnings and, later, autonomy. They replace
   "management plane only" as the autonomy boundary.
2. **Time-bound changes.** A change may carry an expiry, for people and automation alike.
   - **The revert:** the platform's own revert where it has one and it is measured (IOS-XE's
     revert timer, Junos's commit confirmed); otherwise a revert Mercury schedules.
   - **The list:** "active temporary changes", each with its countdown and four actions:
     extend, make permanent (promoted to intent), revert now.
   - Every change and revert is recorded in History.
3. **An environment class per network:** production, staging or lab-disposable.
   - Policy attaches to the class: autonomy, change windows, approvals, AI egress.
   - Staging gives the pre-deployment test network a first-class home: deploy to staging,
     verify, promote.

### 16.2 Phase 9, the closed loop, redesigned on 1 to 3 and piloted on a lab-disposable network

4. **Autonomy per action class, trigger and environment.**
   - Reversible, narrow, time-limited actions come earliest; returning to the golden state
     next; broad or lasting actions stay human-only.
   - It starts in observe mode, with budgets, a kill switch and a dead-man's switch.
   - Human-in-the-loop stays the default everywhere.
   - It supersedes the single promotion bar for the Respond classes.
5. **Event-driven detection.**
   - Deterministic detectors (thresholds, baselines, rate of change), then dedupe and
     correlation; the model is called only on flagged events.
   - Each rule graduates from button-only to automatic analysis by its measured cost per
     useful analysis.
7. **Assure beyond configuration:** expected against observed for any managed state. For
   example, a controller's expected flow table, where a rogue flow is drift.

### 16.3 Toward Stage 10

6. **A device access model:** a per-platform capability matrix (CLI, API, controller) for
   reads, writes, the configuration model, telemetry and expiry support. Part of multi-vendor.
   - The CLI stays the baseline.
   - The first API driver is IOS-XE's NETCONF.
   - Controller drivers cover OpenFlow controllers and vendor controllers (for example
     Meraki and Catalyst Center).
   - **A prerequisite: the Driver contract** (the operator, 2026-10-26; C1753). It holds
     connect, read, capture, apply, commit (with an optional confirm), rollback, and the
     driver's declared capabilities. There is one driver per paradigm (IOS-style CLI,
     set/commit CLI, NETCONF/YANG, REST/JSON device APIs, controller APIs). Each is code,
     reviewed in development and shipped in signed releases. Platform packs (16.8) are data
     choosing a driver.
8. **Traffic and security analytics, by integration.**
   - Flow telemetry ingest (NetFlow, IPFIX, sFlow) for network-level detectors.
   - Events in from IDS and SIEM tools, and Mercury's events out to them.
   - Mercury acts on the network; it is not a SIEM.
10. **Host and hypervisor telemetry for virtual network functions** (the operator, 2026-10-25;
    C1722, linked to C1547 and item 5).
    - What it reads: per-host and per-VM CPU, steal time, per-core load and pinning, and
      memory pressure.
    - Where from: the hypervisor's API (Proxmox first, behind a vendor-neutral interface), or
      node_exporter on the hosts.
    - Who uses it: Assure, the detectors and the evidence packs, so a virtual device's
      control-plane flaps can be traced to contention on its host.

### 16.4 What Mercury will not adopt from lab-style designs

- **The model in a polling loop.** Detection is deterministic, and the model is called on a
  flagged event (item 5).
- **The model as the only detector.**
- **Executing a model's free-text action.** Every action is a catalogued action (item 1),
  previewed and confirmed by hash as today.
- **Unbounded autonomy.** Autonomy is per class, trigger and environment, budgeted, with a kill
  switch (item 4).

### 16.5 In the sprint: item 9

Every Analyst task's recorded cases include healthy baselines that must report nothing wrong,
measured for consistency like the rest; P1 Explain's first (15.12).

**Measured 2026-10-26, 03:23 to 03:42 UTC** (Explain's recorded cases on prompt v4, five runs
each, Claude Sonnet 5.5, under the provisional `max_tokens` of 8,192; v5 beside it on cases 2
to 7, the re-proof; 65 calls, $2.40; none stopped at the bound, the largest output 2,286
tokens, so the pin is now 5,760, C1754):

| Case | Kind | v4 pass | v5 pass | Outcome the same every run (v4) |
|---|---|---|---|---|
| 1 (C1547) | incident | 5/5 | not run (v5 was written after it) | yes, answer |
| 2 | baseline | 5/5 | 5/5 | yes, no fault found |
| 3 | baseline | 5/5 | 5/5 | yes, no fault found |
| 4 | baseline | 5/5 | 5/5 | yes, no fault found |
| 5 | incident | 3/5 | 4/5 | no: answer 3, no fault found 2 |
| 6 | incident | 5/5 | 5/5 | yes, answer |
| 7 | control | 5/5 | 5/5 | yes, answer |
| **all** | | **33/35** | **29/30** | **6 of 7 cases** |

- **Item 9's baselines:** all three reported nothing wrong, five times of five, with the same
  answer every run under 11.12's Analyst consistency (outcome, needs_human, evidence). The
  recording is in `tests/fixtures/ai_cases/explain/recorded.json`, held by
  tests/test_ai_explain_cases.py.
- **Consistency under 11.12's whole definition:** 3 of 7 cases on v4, 3 of 6 on v5. The
  baselines are exact; the incidents keep their outcome but vary in which evidence each
  hypothesis cites.
- **Case 5** is the one miss, on both prompts: twice on v4 (once on v5) it found no fault in an
  SNMP-unreachable incident.
- **v5's re-proof, scored, not adopted (the operator decides):** on cases 2 to 7, v5 29/30
  against v4's 28/30, the same consistency on both measures, and about the same cost
  ($1.11 against $1.10 for the same 30 calls).

### 16.6 Linked from the register

- **Item 5 (event-driven detection):** C93, C1547 and C1682, the lab's load and cadence
  findings.
- **Item 10 (host and hypervisor telemetry):** C1722, linked to C1547 and item 5.
- **Item 3 (environment class policy):** C1720, the classification marking.

### 16.7 Card P5: Plan with AI, and the action library (after the sprint; the operator, 2026-10-26)

In 13.3's order after feature 7. **It depends on:**
- 16.1 items 1 and 2: the action catalogue with risk classes, and time-bound changes;
- feature 7 (natural language to intent) and C1471 (Day 1 at onboarding), whose change-set
  work the executor reuses;
- the network model (15.15).

**New screens need mockups and the operator's sign-off before any build (the standing
rule).** Its open questions are C1747, C1748 and C1749.

#### The workflow: "Plan with AI"

An entry on the Actions menu, carrying the AI mark (15.13). The principle: **"AI advises,
validation decides, Python executes."**

1. **The goal.** The person states a goal in words.
2. **The draft.** The AI drafts a plan as structured steps, chosen only from the action
   catalogue (16.1 item 1). Each step carries:
   - its parameters;
   - a verifier;
   - the action's own rollback.

   No free text is a step.
3. **The validation.** Mercury validates the plan deterministically:
   - every step is in the catalogue, and its parameters are the action's own;
   - impact analysis on the network model: alternate paths, cut vertices, VRRP and HSRP
     masters, single-homed links, BGP sessions;
   - the change windows;
   - the plan's risk is its highest step's class.
4. **The decision.** The person approves, declines, or edits in a structured editor (no free
   text; C1747).
5. **The run.** Mercury's executor runs the plan step by step, each through the normal
   pipeline (preview, apply, verify, rollback). It stops if a step's program differs from what
   was approved. A drain is time-bound (16.1 item 2).
6. **On failure** it stops. The AI may explain, or propose a revised plan, which needs fresh
   approval. The model never acts mid-run.
7. **The record.** Each step is reported, and the run is recorded in History.
8. **Save as action.** The plan, with its parameters, becomes a named action in the network's
   repository:
   - versioned, with its first run kept as the reference;
   - re-runnable with no AI (offline parity).

**P4 (save as runbook, 15.9)** becomes the read-only case of the same format.

#### The action library, built for 100 or more saved actions

- **The Actions menu stays short, about 10 entries:**
  - Plan with AI…;
  - the built-in operations;
  - Pinned (personal and team);
  - Suggested for this device: the top few saved actions that apply to it by platform, role
    and site, never one that cannot run here (C1748);
  - Recently used;
  - All actions….
- **A command palette (Ctrl+K)** searches every action by name, tag and description, from
  anywhere, phone included.
- **An Action library page:**
  - categories: maintenance, troubleshooting, onboarding, security;
  - applicability filters;
  - each action's owner, version, risk class, last run, success rate and approval state;
  - built for large fleets: summary counts, grouping, search, never one long list.
- **Governance:**
  - an action moves from draft (its author only), to reviewed (an approver checked it, and it
    is shared), to retired;
  - an edit is a new version, and every run records the version it ran;
  - actions are network-scoped by default, and export and import share them across networks;
  - who may approve before roles exist is C1749 (decision 13).
- **Read-only diagnostic runbooks (P4)** live in the same library, marked as such.

#### The card (section 3's format)

| Field | P5 |
|---|---|
| Problem | A maintenance or change (a device drained for an upgrade, a link moved, a site's VLAN added) is planned by hand: the steps chosen, the impact reasoned over the topology, the order and the rollback written down, then the steps run one by one. The procedures that work live in people's heads or wiki pages. **Unmeasured:** how often, and how long planning and running take; 8.0's observe period measures it before the card is accepted. |
| Industry need | Network engineers plan changes against the impact they will have: what loses its alternate path, which first-hop redundancy master moves, which BGP sessions drop. Then they run the steps in order with a way back. They also need tribal procedures turned into repeatable automation. Established tools split this: change-management systems hold a method of procedure and an approval; impact-verification and network-modelling tools answer "what breaks if"; automation platforms run playbooks or job templates. Few join a plan's impact analysis to its own verified execution. Mercury does both in one path: a plan of catalogued, risk-classed actions; an impact analysis on its own network model before approval; execution through its preview, verify and rollback pipeline, stopping when a program differs from what was approved; and the plan kept as a versioned action that runs again with no AI, scaled by a short menu, a palette and a library rather than a long list. |
| Deterministic alternative | The person composes the steps from the catalogue by hand in the same structured editor, and the validation, impact analysis and executor are identical. That path is built and works with AI off. What it cannot do: turn a stated goal into a first draft of steps and parameters. That one step is the AI's. |
| Inputs | The goal (masked), the action catalogue's entries and their parameter schemas, and the network model's part around the devices named (the topology class, 15.11), as data. No tools. Context: **unmeasured**, sized by section 4's method. Output schema: Pydantic v2 strict, versioned: steps chosen from the catalogue's identifiers only. |
| Output shape | A (13.4): structured steps, each `{action_id, parameters, verifier, rollback}`, or one question back, or a refusal saying why. Every `action_id` resolves to the catalogue, every parameter validates against its action's schema; one that does not is "couldn't plan", and nothing is shown. |
| Success metric | Plans approved without edit (target **proposed**: 60%), and 0 approved plans whose run stops on a program differing from what was approved. Eval set: recorded cases of goals over the lab's network, with healthy baselines (a goal with nothing to do says so: item 9). |
| Compared fields | Decision-maker (95%, 11.12): the steps' `action_id`s, their order and their parameters. |
| Budgets | **Unmeasured;** proposed by analogy with feature 7 once its cost is measured. A button only (15.6). |
| Observe mode | Drafts shown beside the hand-composed path. The threshold to leave is the success metric over 20 plans. |
| Kill criteria | Approved-without-edit below 40% after 20 plans; one approved plan whose run met a program differing from what was approved; or cost per approved plan above 2× budget. |
| Owner | The operator. |
| Relation | P4 (save as runbook) is the read-only case of the same saved-action format. Feature 7 supplies the intent-patch path the executor's intent steps use. |
| Test plan | A drafted plan citing an action not in the catalogue, or a parameter out of its schema, is refused. The impact analysis is planted on the network model: a cut vertex, a single-homed link, a VRRP master, a BGP session. A run stopping when a step's program differs from the approved one. Rollback per step on a planted failure. A saved action re-run with AI off gives the same programs. The library tested at 100+ actions on test_scale's fleet, with summary counts and no long list. A browser test of each signed-off screen. |

### 16.8 Card P6: AI-assisted platform packs (after the sprint; the operator, 2026-10-26)

It extends section 6's feature 10 (a template draft for a new platform) from one template to
the whole platform. **It depends on:**
- 16.3 item 6 (the device access model), with Mercury's parsers and drivers made
  data-driven. They are Python today (`modules/nsot/parsers/`), and making them rule-driven
  is a prerequisite, registered as C1752;
- 16.1 item 3 (an environment class, staging);
- 15.11's configuration class (a captured configuration, its secret-bearing lines dropped);
- the action library (16.7).

#### The workflow

1. **The platform.** A person names its make, model and OS version.
2. **The draft.** The AI drafts a platform pack **as data only**: no code, and nothing
   that runs on its own. The pack holds:
   - the connection type;
   - the allowlisted reads;
   - the capture command and its normalisation;
   - the masking rules and the parser rules;
   - the Jinja templates;
   - the deploy semantics: merge, and commit, rollback and commit-confirmed where the OS has
     them;
   - the removal shapes and the verify reads;
   - the monitoring profile and the credential rotation sequence.

   It prefers existing open-source parsers. Any new third-party licence is the operator's.
3. **The acceptance, by measurement, level by level.** Every level is measured on a real
   device in a staging or lab network, and a person approves each one:

   | Level | Name | What is measured |
   |---|---|---|
   | 0 | read | the allowlisted reads, parsed |
   | 1 | capture | a capture normalised |
   | 2 | intent | a round trip, exact |
   | 3 | deploy | a staged deploy verified, then rolled back |
   | 4 | full | each removal shape, and the rotation sequence |

4. **The pack.** It is versioned and shareable (export and import), and it runs with no AI.
   A platform is supported at the level its pack has passed, and the screens say which.

#### Drivers are code; packs are data (the operator, 2026-10-26)

- **A driver is code, one per paradigm:**
  - IOS-style CLI;
  - set/commit CLI;
  - NETCONF/YANG;
  - REST/JSON device APIs;
  - controller APIs.
- **Every driver meets one contract:** connect, read, capture, apply, commit (with an
  optional confirm), rollback, and its declared capabilities. A driver is written and
  reviewed in development, and shipped in signed releases.
- **A pack is data choosing a driver.** It never carries code.
- **The installation's AI never writes or changes code.**
- **When no driver fits,** the pack is accepted at the levels the existing driver can prove.
  The AI then produces a structured driver request for the maintainers: the capability
  missing, the device evidence, and the levels it blocks.
- The driver contract is a prerequisite, in 16.3 item 6 (C1753).

#### A shared pack library (the operator, 2026-10-26)

- **Signed, with provenance and proof.** A pack carries:
  - its signature;
  - its provenance: the author and the OS versions it was measured on;
  - its proof records: each level measured, and how.
- **An imported pack is untrusted** until its levels are proven again on the importing
  network's own staging devices. Nothing reaches production on another network's proof
  alone: the proof records travel with the pack as evidence, not as acceptance.
- **Industry precedent:** NetBox's device-type library and Ansible collections, both shared
  catalogues of platform definitions or automation, reused across installations.
- **The release message is guided onboarding with measured proof, not instant support:** a
  new platform is drafted in hours, then accepted on the network's own devices level by
  level, and supported only at the level it has passed there.

#### The card (section 3's format)

| Field | P6 |
|---|---|
| Problem | Supporting a new platform means writing its connection, reads, capture normalisation, parsers, templates, deploy and removal semantics, verify reads and rotation by hand, and proving each on a device. **Unmeasured:** the engineering time per platform (the IOS and IOS-XE packs are the only measured precedent, built over Phases 1 to 7). |
| Industry need | Vendor onboarding takes weeks of engineering in today's tools: a new platform needs its drivers, parsers, templates and change semantics written and tested before a tool can manage it. That cost is why multi-vendor support stays narrow. Multi-vendor is a release goal. Mercury improves on that by drafting the platform as data, then accepting it only level by level on a real device: read, capture, intent, deploy, full. Each level is approved by a person, so a draft is never trusted. The pack is versioned and shareable, so one installation's measured work serves another, with no AI at run time. |
| Deterministic alternative | A person writes the pack in the same data format, and the same acceptance measures it. That path works with AI off. What it cannot do: draft the pack's many parts from the platform's documentation and a captured configuration in hours, where writing them takes weeks. That drafting is the AI's. A driver is never drafted: drivers are code from the maintainers, and where none fits, the AI drafts a structured driver request instead. |
| Inputs | The make, model and OS version; a captured configuration in 15.11's configuration class, its secret-bearing lines dropped; the existing packs' format and the nearest pack as examples. Context: **unmeasured**, sized by section 4's method. Output schema: Pydantic v2 strict, versioned: the pack's data, every field validated, no executable content. |
| Output shape | A (13.4): the pack as structured data, or one question back (for example, which OS train), or a refusal saying why. |
| Success metric | Packs reaching level 2 (an exact round trip) within two revisions (target **proposed**: 50%, feature 10's), and 0 packs approved at a level whose measurement did not pass. Eval set: the lab's IOS and IOS-XE devices, their packs drafted blind and compared with the measured ones, then one new platform. |
| Compared fields | Translator (95%, 11.12): the pack's structured fields (the reads, the parser rules, the templates' rendered output on the captured configuration). |
| Budgets | **Unmeasured;** feature 10's 30k in and 6k out per template is the floor, and a pack is several of those. A button only (15.6). |
| Observe mode | Each drafted pack measured beside a hand-written one on the lab's platforms before a new platform is attempted. |
| Kill criteria | Below 40% of packs reaching level 2 within two revisions after 5 platforms; or one pack approved at a level whose measurement failed; or cost per accepted level above 3× budget. |
| Owner | The operator. |
| Relation | Feature 10 (the template draft) becomes one part of a pack. The action library (16.7) carries the pack's verify reads and removal shapes as actions. The device access model (16.3 item 6) is the pack's runtime. |
| Test plan | A drafted pack with executable content, or a read off the allowlist, is refused. A masking rule is planted with a secret and must never leave. Each acceptance level runs on a lab device: the read parsed, the capture normalised, the round trip exact, a staged deploy verified and rolled back, each removal shape and the rotation sequence measured. A level cannot be approved without its measurement passing. Export and import carry a pack between networks unchanged, its signature checked. An imported pack runs at no level until each is proven again on the importing network's staging devices, and a production deploy with only the exporter's proof is refused. A pack is run with AI off. |

### 16.9 Long horizon: device-resident AI (a roadmap note, no card; the operator, 2026-10-26)

**What to expect.** Devices will run local agents:
- summarising their own telemetry;
- detecting anomalies locally;
- diagnosing themselves;
- a natural-language CLI.

Later, they will take bounded local actions.

**Mercury's stance:**
- **A device agent's output is evidence:** structured findings, never instructions. It
  enters an evidence pack as data, as any reader's value does, and nothing in it is
  followed.
- **Mercury is the policy authority.** It may grant a device agent narrow, reversible,
  time-limited actions by the action catalogue's classes (16.1 items 1 and 2), each grant
  with:
  - a budget;
  - an expiry;
  - full audit in History.
- **Agent protocols (for example MCP) arrive as drivers** (16.3 item 6's contract), never as
  a second path around it.

**Reviewed yearly against vendor reality**, the first review by 2027-10-26: what devices
actually ship, and whether the stance still holds.
