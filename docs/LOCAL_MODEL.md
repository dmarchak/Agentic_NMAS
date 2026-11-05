# Mercury's own local model for closed networks, its learning loop, and Mercury's controlled language (design)

**Design only** (the operator, 2026-11-04): a Stage 10 research track, built after Lab 10 and
Lab 9. Nothing here exists today. It is linked from
[GOVERNMENT_PROFILE.md](GOVERNMENT_PROFILE.md) (sections 10.7 and 11) and from
[PHASE8_PLAN.md](PHASE8_PLAN.md) section 10, the built-in local model. That section decides
three things this note keeps:
- the origin (US only, 10.2);
- one adapter per API shape (10.3);
- only models that pass the evaluation are offered (10.7).

What this note adds is a model of Mercury's own: small, fine-tuned for Mercury's narrow tasks,
and improved by the installation's own verified outcomes.

## 1. The need

- **The problem:** a closed network (SECRET, COLORLESS, an edge kit with no link) has no hosted
  model, and a general model large enough to answer well needs hardware most sites will not give
  a management tool.
- **How established tools meet it:** network management tools for these sites ship no AI, or a
  rule engine.
- **How Mercury meets it:** deterministic runbooks carry the diagnosis, as they do today. The
  model assists with four narrow tasks, each qualified on Mercury's own case sets, and a
  feature below its bar is simply not offered with the model. The controlled language (section
  8) makes most requests need no model at all.

## 2. The model

- **The target:**
  - 0.3 to 1.5 billion parameters;
  - 4-bit;
  - under about 1 GB of RAM;
  - CPU only.
- **Its tasks, each its own qualification:**
  - alert classification;
  - intent in words into fixed intent forms;
  - questions on the manual;
  - evidence-pack summaries.
- **US-origin base models only** (PHASE8_PLAN 10.2). The candidates to evaluate:
  - Gemma 3 270M and Gemma 3 1B (Google);
  - Llama 3.2 1B (Meta);
  - IBM's Granite small models.
- **The architecture:**
  - Deterministic runbooks carry the diagnosis, and the model assists.
  - It is served by llama.cpp's OpenAI-compatible server, inside the installation, through the
    generic OpenAI-compatible adapter (GOVERNMENT_PROFILE 5.3), with its output constrained by
    a grammar or a JSON schema made from the feature's committed schema.
  - It is qualified per feature on the recorded and blind sets (GOVERNMENT_PROFILE 5.2, item 4):
    a feature below its bar is not offered with it.
- **Its serving footprint** runs in its own systemd slice with caps, as local CI's does, so it
  can never starve the app.

## 3. Training data

- **Mercury's recorded cases** (tests/fixtures/ai_cases/), and the labels its deterministic code
  produces: a runbook's verdict, a detection rule's class, a resolved intent form.
- **Human-checked examples:** each with who checked it and when.
- **Commercial model outputs** only where that provider's terms allow training on them (an open
  question, 9.1).
- **Never the model's own unverified outputs** (section 4).

## 4. The continual-learning loop

The installation improves its model from what Mercury and its devices prove. This ties into
Phase 8's feedback loop, "Was this right?" (PHASE8_PLAN Appendix A.1, A2.1, built), whose marks
are one of the label sources below.

### 4.1 Only outcome-verified labels

- a heal verified by its post-check;
- a proposal approved or declined by a person;
- an alert's confirmed closing cause;
- an operator's correction of an AI answer ("Was this right?" and its correction);
- a deterministic runbook's verdict.

Never the model's own unverified outputs: a label is only what a check or a person settled.

### 4.2 Cold start

A base model is fine-tuned on Mercury's recorded cases and on labels from its deterministic code,
and ships as the installation's first model. The site's own verified data then improves it over
time.

### 4.3 Retraining and promotion

- **Retraining runs on a schedule, inside the installation,** in quiet hours and within its slice
  caps.
- **A candidate is evaluated** on the frozen case sets plus a held-out slice of the site's
  history. It is promoted only if:
  - it beats the current model;
  - it meets every feature's bar;
  - and it does not regress on the safety-critical classes (a threat called benign, a change
    misread).
- **The operator approves the promotion.** It is a decision, shown with the candidate's results
  beside the current model's (CLAUDE.md: people make decisions).
- **The previous model is kept, for rollback.**
- **Each version's per-feature results are shown over time,** so drift is seen.

### 4.4 Defences

| Threat | Defence |
|---|---|
| A poisoned label | provenance on every training record (its source, the check or person that settled it, when), and filtering of anomalous data before training |
| Forgetting rare events | a fixed replay set, including the rare events, in every training run |
| A secret in training data | the egress mask (`redact.redact_egress`) applied to every training record before it is kept |

### 4.5 A model inherits its training data's classification

- It never leaves its installation's domain and is never copied across stacks
  (GOVERNMENT_PROFILE section 1).
- It never flows into the public release, which ships only the cold-start model, trained on
  Mercury's own published cases.
- **Sharing happens only within the same marking,** and only down the edge hierarchy: a
  headquarters instance trains on its same-marking kits' verified data and pushes the model down
  (EDGE_ARCHITECTURE section 7), each push a signed bundle (GOVERNMENT_PROFILE 10.2).

### 4.6 Compute

- **An estimate, to be measured first (section 7):** LoRA fine-tuning of a 1B model costs about
  six times its parameters in floating-point operations per training token, about 6 × 10⁹.
  - The NMAS host's 4 vCPUs sustain perhaps 50 to 100 GFLOP/s in a training framework.
  - So a million training tokens (about 2,000 examples of 500 tokens) takes about 15 hours an
    epoch (8 to 30), and three epochs about two days.
  - A 270M model is about four times faster.
- **So training is planned where the compute is:** at headquarters for the kits, which receive
  the model down the hierarchy; on a standalone installation, in quiet hours over several
  nights, inside its slice's caps.

## 5. Licence

- **The base model ships with Mercury, so its licence is the operator's** (CLAUDE.md's Phase 7
  stops).
- Apache-2.0 Granite is the simplest.
- Gemma's and Llama's licences carry their own terms (use restrictions, attribution, a
  redistribution notice), each to be read in full before either is offered.

## 6. Government

- **A signed model shipped inside the installation,** with no egress, as the AI option on SECRET
  and COLORLESS (an open question, 9.2):
  - added only through the shipped provider list (GOVERNMENT_PROFILE 4.1) and a release;
  - subject to the site's accreditation.
- It is the only path by which a SECRET installation could have AI, because no hosted provider's
  accreditation covers it (GOVERNMENT_PROFILE 8.1).

## 7. Measurements first

1. **RAM and latency per candidate,** on the NMAS host (4 vCPUs, 15.5 GiB) and on the laptop:
   - resident memory at load and under a 2,000-token prompt;
   - the time to the first token, and tokens a second;
   - for each candidate at 4-bit, through llama.cpp's server.
2. **A first qualification on one narrow task:** alert classification, on its recorded set, the
   base model as shipped and then a first LoRA. That reads whether fine-tuning moves the bar
   before the rest is built.
3. **LoRA's real training time** for the 1B candidate on the NMAS host, against section 4.6's
   estimate.

## 8. Mercury's controlled language (every provider)

### 8.1 One grammar, the single source

**What it holds:** the verbs, the objects, the qualifiers, and the synonyms and aliases,
including interface shorthand.

**What it is the source for:**
- the prompt box's live checks (8.2);
- the generated manual page and the **?** help;
- the model's training targets and its constrained output (sections 2 and 3);
- the validator every request passes.

**Today's intent-in-words rules are folded in** (PHASE8_PLAN 15.16, part 1):
- **Shorthand,** canonicalised as the device names it, per platform (G, Gi, Gig to
  GigabitEthernet; Te, Fa, Po, Lo, Vl, Tu), and only when the interface exists on the device
  (C1891, C2206).
- **References,** from the network model and committed intent: "uplink", "trunk", "the VLAN 10
  ports", "host port". A host port is resolved structurally (an access port, enabled in intent,
  with no managed neighbour), never from a description.
- **"Which host port?"** when a singular reference matches several, each candidate a choice
  naming its neighbour.

### 8.2 Live checks

- **Unknown or invalid words are underlined,** with an underline and a tooltip, never colour
  alone.
- **Suggestions come from the live inventory:** NetBox's devices, and each device's real
  interfaces and protocols.
- **Ambiguity asks:** "which host port?", with each candidate.
- **A ? button lists what is valid at the cursor.**

### 8.3 Deterministic first

- **Input that already parses runs deterministically,** with no model call, so it works with AI
  off: a SECRET installation's whole interface.
- **The model only rewrites fuzzy input into a canonical sentence.** The sentence is shown for
  confirmation before anything runs.

### 8.4 Strictness

- **A change request must resolve to an exact canonical sentence,** confirmed, before any
  preview.
- **A question may stay free text;** its suggestions are warnings, never blocks.

## 9. Open questions for the operator

1. **Training on commercial models' outputs:** only where that provider's terms allow it. Which
   providers' terms to rely on is the operator's. Recommended: none at first; the cold start
   uses Mercury's recorded cases and deterministic labels only.
2. **A signed in-installation model as SECRET's and COLORLESS's AI option** (section 6):
   recommended as the route, decided only with a site's accreditation in hand.
3. **The base model's licence** (section 5): recommended, Granite (Apache-2.0) first, Gemma and
   Llama only after their terms are read.

## 10. The estimate

By the measured ratio (PHASE8_PLAN 0.3, C2380), 1 agent-day is about 1.3 h of one agent's wall
time and about 4M weighted tokens.

| Part | What | Days |
|---|---|---|
| L0 | The measurements of section 7 | 1.0 |
| L1 | The training-data pipeline: provenance, the egress mask, the anomaly filter, the replay set | 2.0 |
| L2 | The fine-tuning harness: LoRA, reproducible, its artefact signed | 1.5 |
| L3 | Serving: llama.cpp's server in its own capped slice, constrained output from the committed schemas, through the generic adapter | 1.0 |
| L4 | Qualification of the four tasks, on the recorded and blind sets | 3.0 |
| L5 | The loop: the schedule, the candidate's evaluation, the promotion screen (board first), rollback, the per-version history | 3.0 |
| L6 | The defences' tests | 1.0 |
| L7 | Classification: the domain-bound model store, the export refusal, same-marking sharing down the hierarchy | 1.0 |
| L8 | The controlled language: the grammar, the generated manual page and ? help, the live checks (board first), the deterministic path, the validator, feature 7's rules folded in | 6.0 |
| **Total** | | **19.5** |

**19.5 agent-days is about 25 h of wall time** (14 to 51) and about 78M weighted tokens. The last
stage of this kind ran about 75% long, so read 19.5 as up to about 34.

**Not in the estimate:**
- the training compute itself (section 4.6: days of CPU on the host);
- the operator's time for human-checked examples;
- each qualification's runs on the model.
