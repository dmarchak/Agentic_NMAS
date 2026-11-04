# The government profile: one installation per classification domain, its marking, and its AI provider (design)

**Design only** (the operator, 2026-11-04). It is built after Lab 10 and Lab 9, and nothing in it
exists today. The provider work (one gateway, an adapter per provider, GenAI.mil among them,
section 5) is placed in [PHASE8_PLAN.md](PHASE8_PLAN.md) (Appendix A.1);
the setup wizard, the markings, the banner, the egress rule and the manager link are placed in
[NSOT_STAGE10_PLAN.md](NSOT_STAGE10_PLAN.md) (sections 5.3 and 13).

**What it replaces.** [EDGE_ARCHITECTURE.md](EDGE_ARCHITECTURE.md) section 9 and PHASE8_PLAN 13.1
planned a marking per network that forced AI off with no override (C1720). In this design the
marking belongs to the installation, and every network inside it inherits it. A US Government
installation marked Unclassified may use one shipped provider, GenAI.mil (section 4). Everything
else in EDGE_ARCHITECTURE section 9 stands: the check at the point of export, values inheriting
their source's classification, and the survey of every path by which data leaves a host
(section 9.3), which section 4.4 below builds on.

## 0. The need

- **The problem.** A government network team runs several network stacks side by side:
  unclassified, secret, and the colourless transport that carries them. Each must be managed
  with no path between them.
  - The person at the console must see at a glance which domain they are working in.
  - Nothing may send a byte to a provider the domain's accreditation does not cover.
- **How established tools meet it.** Network management systems sold into these environments
  are installed once per enclave, never as one multi-domain server. Cross-domain transfer is the
  job of an accredited cross-domain solution, never of an application.
  - The marking is shown as a coloured banner at the top and bottom of every screen and on every
    printed or exported page. The colours follow the usual convention for system banners:
    green Unclassified, purple CUI, blue Confidential, red Secret, orange Top Secret, yellow
    TS//SCI.
  - Egress is default-deny, with each allowed flow named (NIST SP 800-53 AC-4 information flow
    enforcement, SC-7(5) deny by default).
  - The configuration that sets the boundary is locked, and changing it is a recorded,
    privileged act (CM-5, CM-7).
- **How Mercury meets it, and where it improves on it.**
  - One installation is one domain: the marking is set once, at setup.
  - The AI provider rule is enforced in the gateway itself, so no setting, hand-edited file or
    edited URL can widen it (section 4.2).
  - A change to the profile deletes the keys the new profile forbids instead of leaving them
    disabled on disk.
  - Two Mercury nodes refuse to link across domains, saying why on both sides (section 6).
- **What the banner does not do.** It marks the system and does not accredit it. The
  organisation's ATO (authority to operate) process governs what may be connected, and the
  wizard says so (section 2.4).

## 1. The deployment model

1. **One installation serves exactly one classification domain.**
   - A node runs a separate installation per network stack, typically one for unclassified, one
     for secret and one for colourless, with more added as stacks are added.
   - Each is installed, updated, backed up and administered on its own.
   - Nothing crosses between them: no shared store, key, repository, NetBox, monitoring stack,
     AI key or session.
2. **Every network (device list) inside an installation inherits the installation's marking.**
   There is no per-network override, up or down. A network that needs another marking belongs
   in another installation.
3. **Several installations run on one node at once, so Mercury's footprint is budgeted per
   installation and kept modest.**
   - The budget is measured, never guessed: the app's resident memory and CPU at rest and under
     a Check drift now across its fleet, plus the bundled services each installation brings.
     NetBox, Grafana, Prometheus, Loki and Kea are not shared across domains, so each
     installation's copy counts.
   - The budget is stated per installation beside NSOT_STAGE10_PLAN 7.4's hardware tiers, as "a
     node of tier T holds N installations".
   - Each installation's containers get their limits from that measurement (a bound at about
     2.5 times the measured peak, CLAUDE.md).
4. **Ports, names and paths are per installation:** its own data folder, its own TLS
   certificate and its own host port. The installer refuses a second installation that would
   reuse another's folder or port, naming both.

## 2. The setup wizard

The first-run wizard (NSOT_STAGE10_PLAN section 5) gains its first step, before the break-glass
administrator, because the profile decides what every later step may offer.

### 2.1 The use type

**Personal, Commercial or US Government.** Personal and Commercial behave as today. US Government
asks the classification next.

### 2.2 The classification (US Government only)

The presets, decided by the operator 2026-11-04 (8.2):

| Preset | Colour | Notes |
|---|---|---|
| **UNCLASSIFIED** | green | |
| **CUI** | purple | |
| **CONFIDENTIAL** | blue | |
| **SECRET** | red | |
| **TOP SECRET** | orange | |
| **TS//SCI** | yellow | |
| **COLORLESS** | grey | marks the transport network's instance and the devices that run it |
| **Other** | chosen with a colour picker | a free-text marking; the text is drawn exactly as typed |

A picked colour is checked for contrast against its banner text in both themes, and refused below
WCAG AA (4.5:1), naming both colours.

### 2.3 Locked after setup

- **The use type and the marking cannot be changed in Settings.** No setting, route or file edit
  changes either: the profile has no write path but the wizard's.
- **Changing either means running the wizard again,** as an installation administrator, with a
  reason. It is recorded in the installation's settings record: who, when, from what to what,
  and the reason.
- **Keys the new profile forbids are deleted, not disabled.** Each provider key the new profile
  does not allow is removed from the secret store (`secrets_store`), and the change record names
  each key removed, by provider, never by value.
  - A stored AI answer, analysis or pack made under the old profile stays where it is, under the
    record of the provider that made it.
  - The wizard says that what was sent before the change was sent under the old profile.
- **How a hand edit is caught.** The profile is written with a MAC under the installation's
  key (`data/key.key`), by the wizard only. A profile that fails its MAC, or is absent, reads as
  the most restrictive state for every check in this design:
  - AI off;
  - egress default-deny;
  - the banner showing "PROFILE UNREADABLE" in red;
  - a Critical Needs attention row naming the file and what failed.

  A hand edit therefore never widens anything; it fails closed.

### 2.4 What the wizard says

On the classification step, in plain words:

> The banner marks this system. It does not accredit it. Your organisation's authority to
> operate (ATO) process decides what may be connected to this system and what it may hold.

## 3. The classification banner

- **Top and bottom of every screen:** a full-width strip in the marking's colour, the marking in
  capitals, drawn by the v2 base layout so that no page can omit it. It uses colour tokens with
  dark-theme values, under `csp.STRICT_POLICY`. It is never covered: the toolbar sits below the
  top strip, and the bottom strip stays fixed.
- **On every export and printed report:**
  - the first and last line of every CSV or text export;
  - the header and footer of every page of a PDF or printed report (the print stylesheet repeats
    both strips on each page);
  - every email: a subject prefix (`[CUI] `, say) and a banner line at the top of the body, in
    the marking's words (decided 2026-11-04, 8.3);
  - every webhook payload: a `marking` field holding the installation's marking, beside the
    event (decided 2026-11-04, 8.3).
- **Personal and Commercial installations draw no banner.**
- **One composition:** the marking's text and colour come from the profile through one helper,
  read by the layout, the exports and the notifier alike.

## 4. The AI provider policy, enforced in the gateway

### 4.1 The rule

| Use type and marking | Providers |
|---|---|
| Personal, Commercial | every provider, as today (PHASE8_PLAN 15.3, NSOT_STAGE10_PLAN 13) |
| US Government, UNCLASSIFIED | **GenAI.mil only** |
| US Government, CUI | **GenAI.mil only** |
| US Government, CONFIDENTIAL, SECRET, TOP SECRET, TS//SCI | **AI is off;** GenAI.mil is refused |
| US Government, COLORLESS | **AI is off;** GenAI.mil is refused |
| US Government, Other | **AI is off;** GenAI.mil is refused |

**Decided by the operator, 2026-11-04 (8.1):** GenAI.mil is accredited for UNCLASSIFIED and CUI
only. The operator will give more detail later, and the table may widen then; any widening comes
through the shipped provider list and a release (below), never through Settings.

**The list is shipped in code, never set in Settings.**
- The government providers and the markings each one's accreditation covers are a table in
  Mercury's code, `GOVERNMENT_PROVIDERS`, beside the pins.
- A future government provider, for example one accredited for Secret, is added to that table
  through the normal release process, with its tests.
- No setting, route or file adds one.

### 4.2 Where it is enforced

- **In `modules/ai/gateway.py`, before any provider request,** beside the hosted-AI question
  (`hosted_allowed`) and the background switch (`background.admit`):
  1. the profile is read and verified (2.3);
  2. the call's provider is checked against the rule;
  3. its endpoint is checked against the shipped preset, by its whole URL.
- **What a refusal does.** It is recorded as every gateway refusal is (`profile_refused`, naming
  the profile, the marking, the provider and the endpoint compared), and no provider request is
  made. A refused call names both operands (CLAUDE.md).
- **What the screens show.** Every AI control is drawn disabled with the reason, through 15.13's
  one AI mark: "AI is off on a Secret installation: no provider's accreditation covers it."
- **The settings for other providers are not shown on a government profile.** An admin cannot
  add, enable or point Mercury at another endpoint. The routes that would save one refuse,
  naming the profile, whatever the form sends.
- **On a government profile the base URL is the shipped GenAI.mil preset,** compared whole. A
  settings value that differs (hand-edited or left from before) is refused, never used.

### 4.3 What the rule does not change

The existing AI rules stand inside the allowed provider:
- off by default;
- hosted AI allowed by an admin with a reason;
- the background switches and caps (PHASE8_PLAN 18);
- the egress classes and the egress mask (15.11, 15.16);
- the injection defence.

A government profile only narrows them.

### 4.4 Default-deny for every other egress

On a government profile every destination outside the installation is refused unless an admin
allows it, one destination at a time, each with a reason, recorded and shown in Settings with
who allowed it. From EDGE_ARCHITECTURE section 9.3's survey, the ones named by the operator:
- **Update checks:** the CI verdict read from GitHub (`ci_verdict`). On a government profile,
  updates come by the offline route (C2370) unless GitHub is allowed.
- **The git remote:** the list repositories' push (`archive._push_locked`, `remote.push`), the
  remote's checks and the publication reader.
- **External assets** (fonts, CDNs). v2 vendors every library under its strict CSP (CLAUDE.md),
  so the work is a test that keeps it so on a government profile, plus the manual's and the
  exports' own assets.
- **Notifications** (decided 2026-11-04, 8.3): each mail relay and each webhook target is a
  destination under this rule, refused until an admin allows it with a reason. A notice to a
  destination not allowed is not sent, and the delivery log says why.

Every other path in 9.3's table (integrations, the golden archive, NetBox) is held by the same
allowlist. A destination is an exact scheme, host and port, never a pattern.

## 5. The providers: one gateway, an adapter per provider, GenAI.mil among them

A government profile needs a second provider, and that is the point at which Mercury's AI stops
being tied to one. This section is one design: what ties it today (5.1), the target (5.2), the
OpenAI-compatible adapter with GenAI.mil as its preset (5.3 to 5.7), and the estimate (5.8). It
is built after both labs.

### 5.1 How tied the AI is to Anthropic today (a read-only audit, 2026-11-04 ~20:2x UTC)

**The boundary is clean; the gateway is not.**
- **The boundary holds.** No provider SDK is installed or imported: requirements.txt says the SDK
  was dropped, and tests/test_ai_boundary.py enforces four rules over the parsed code:
  - only the adapter names the host and the key header;
  - only the gateway imports the adapter;
  - no SDK is imported;
  - only the gateway reads the key.
- **The gateway is not neutral.** It builds, prices and parses requests in the Messages API's
  shape, and the prices, the pins and every evaluation result name Claude models.

It touches about 98 files:
- 33 non-test files (28 in `modules/`, 4 scripts, 1 template);
- about 38 test files;
- 28 fixture files;
- PHASE8_PLAN.

Kinds:
1. a model name or ID outside the adapter;
2. the SDK outside the adapter;
3. a feature only Anthropic has;
4. a token budget on Anthropic's tokenizer;
5. a price table in USD per Anthropic model;
6. an evaluation result tied to one model;
7. one response shape assumed.

| Where | What is tied | Kind | The fix |
|---|---|---|---|
| `modules/ai/profiles.py:32` (11 hits; `DEFAULT_MODEL` :111) | `MODELS`, keyed by the three Claude models | 1 | the registry (5.2) |
| `modules/ai/pins/*.json` (8 files: 4 Haiku, 4 Sonnet) | each pin's `model` | 1, 6 | a pin per feature and model |
| `modules/ai/gateway.py:36, 77, 86` | `CALIBRATION["tightest"]["model"]` and its notes | 1, 4 | calibration per model |
| `modules/ai/explain.py:260`; `modules/ai/nl_query.py:59` | `MEASURED` and the v10 adoption name one model and its round | 1, 6 | qualification per model |
| `scripts/nmas-intent-cases:170`, `nmas-nl-cases:134`, `nmas-sdn-cases:317`, `nmas-pack-replay:308` | help text naming Haiku, Sonnet, Opus | 1 | neutral wording |
| `modules/ai/profiles.py:38, 40, 51, 66` | the `thinking_off` forms and `temperatures: [1]` | 3 | the registry's capabilities |
| `modules/ai/gateway.py:310-327` | the request body: system blocks with `cache_control`, `max_tokens`, `messages`, `output_config.format.json_schema`, `thinking` | 3 | the adapter builds the body |
| `modules/ai/gateway.py:430-431` | `anthropic_adapter.count_tokens`, `WorkspaceLimit` | 3 | the adapter interface |
| `modules/ai/gateway.py:503-505, 863-876, 908-916` | the answer read from `content[]` text blocks; cache-creation usage keys; `stop_reason` "refusal" and "max_tokens", `stop_details` | 3, 7 | the adapter normalises |
| `modules/ai/gateway.py:957-1011, 1286-1290` | the Message Batches path: its TTL, 100,000 requests and 256 MB, `custom_id`, result types, 24-hour expiry | 3 | batch as a capability (5.2) |
| `modules/ai/schemas.py:77-98` | `ANTHROPIC_UNSUPPORTED`; `schema_for` raises for any other provider | 3 | a schema rule per provider |
| `modules/history_sources.py:308, 343-353, 1195-1197`; `scripts/nmas-pack-replay:78-79` | stop words keyed on Anthropic's; the stored body read as `system[].text`; the four usage keys drawn | 3, 7 | a neutral stored record |
| `modules/ai/gateway.py:82, 331-341` | `CHARS_PER_TOKEN = 1.8` (calibrated on 10,395 Anthropic calls), `tokens_of_chars`, `prompt_tokens` | 4 | calibration per model |
| `modules/ai/pins/*.json` (all 8); `modules/ai/explain.py:1054-1136`; `nl_query.py:546-548` | `max_prompt_tokens` and `max_tokens` in Anthropic tokens; packs budgeted on Anthropic counts | 4 | budgets per model, counted by the adapter |
| `tests/fixtures/ai_calibration/calls_sample.tsv`; `tests/test_ai_token_count.py:241` | the calibration rows, by Claude model | 4 | calibration per model |
| `modules/ai/profiles.py:11, 26-72, 131-201` | USD per million tokens for input, cache write, cache read and output; the long-prompt tier; batch ×0.5; the 1-hour write ×2; `cap_per_call` | 4, 5 | a pricing model per provider |
| `modules/ai/gateway.py:344-351, 885-902, 989-995`; `modules/ai/calls.py:205-225` | worst-case cost (every prompt token priced as a cache write); cost and `cache_summary` from the four usage keys | 5, 7 | the adapter normalises usage; pricing per provider |
| `templates/v2/_install_card.html:156, 164` | "from Anthropic's pricing page" | 5 | the provider's own source |
| `modules/ai/profiles.py:204-228`; `modules/ai/cases.py:73-86`; the three case scripts | a recorded case's `model` must equal the pin's (`cases_off_pin`) | 6 | qualification per model (5.2, item 4) |
| `modules/ai/background.py:292-301` | the estimate reads rows on the pinned model | 6 | per-model history |
| `tests/fixtures/ai_cases/` (22 files), `tests/fixtures/blind_sets/` (2), `tests/fixtures/sdn/recorded/` (5) | recorded answers, blind keys and labels on one Claude model | 6 | kept, labelled by model; each new model qualifies afresh |
| `docs/PHASE8_PLAN.md` (38 hits) | tiers and results on Haiku or Sonnet | 6 | results per model |
| `modules/ai/gateway.py:617-618` | refuses any provider other than Anthropic | 7 | dispatch per provider |
| `modules/ai/gateway.py:710-714, 823-830, 907, 984, 1225-1235`; `modules/ai/provider_limit.py:3-5, 52-54` | the send bound from the adapter's constants; `anthropic-ratelimit-*` headers; "overloaded" (529); the workspace-limit text parsed | 7 | the adapter normalises to neutral kinds |
| `anthropic_api_key` (`modules/ai/gateway.py:286`, `settings_schema.py:139, 874`, `secrets_store.py:46` and 8 more) | one key setting, and "no Anthropic API key" wording | 7 | a key per provider (expand, then contract) |
| about 35 test files (e.g. `tests/conftest.py:548`, `tests/test_ai_gateway.py:27`) and 19 with model IDs (test_ai_gateway 24, test_ai_profiles 21) | the adapter's `send` mocked with Anthropic's shapes; model IDs in asserts | 1, 7 | a neutral fake provider |

Rows per kind: 1 (6), 2 (0), 3 (13), 4 (6), 5 (8), 6 (12), 7 (16); a row may count in two.
Absent everywhere outside the adapter: `tool_use` blocks and `anthropic-beta` headers.

**Already provider-neutral, not redone:**
- the boundary test;
- a `provider` on every model (`profiles.py:23-24`), and `schema_for`'s provider argument;
- the adapter's neutral error kinds (`RateLimited`, `Overloaded`, `KeyRefused`, `BadRequest`,
  `ProviderDown`, `WorkspaceLimit`);
- the egress mask (`redact.egress_payload`, which walks any JSON tree);
- pins as data;
- the feature modules (Explain, Ask in words, the assistant, change records, the heal analysis,
  intent words), which see only `gateway.ask`'s validated Pydantic output;
- the spend caps and records, which sum `cost_usd` only;
- every prompt and schema file, which names no model or provider.

**Where change hurts most:**
1. **The evaluation results.** Every floor (90%, 95%) was earned on one Claude model, so a new
   model re-runs every set, at real cost.
2. **`build_request` and `_received`.** Caching, structured output, thinking, `stop_reason` and
   the usage keys are inline, and cost, verdicts and History depend on them.
3. **Pricing and the caps.** The per-call cap assumes the cache-write premium, the long tier and
   the batch discount, so another provider needs a pricing model, not new numbers.
4. **Token budgets.** All are calibrated on one tokenizer. Another could exceed a budget
   silently, or trim the context differently and change the answers.
5. **The batch path.** Every evaluation round runs on the Message Batches API.

The stored call records come next: old rows need a compatibility reader.

### 5.2 The target design

1. **One gateway, one adapter per provider.**
   - **The adapters:** `anthropic_adapter` as today, and one `openai_compat_adapter` covering
     GenAI.mil and self-hosted OpenAI-compatible servers (vLLM, Ollama's OpenAI endpoint).
   - **What each adapter owns:** it builds its provider's body from a neutral request (system,
     messages, the schema, the output bound, an optional cache hint), and sends it with its
     bound.
   - **What each adapter returns:** a neutral `Reply` holding:
     - `text`;
     - `stop`, one of `done`, `cut`, `refused` or `tool`;
     - `usage`: `input`, `output`, `cache_read` and `cache_write`, the last two zero where the
       provider has no cache;
     - `limits`: the provider's rate-limit state;
     - `kind` on an error, the existing neutral kinds.
   - **What the gateway keeps, unchanged:** the egress mask, the caps, the triggers, the
     recording, the checks and the profile rule (section 4).
   - The gateway's dispatch replaces `gateway.py:617-618`'s refusal.
2. **A model registry** (`modules/ai/registry.py`), the one place a model ID is written, each
   model declaring:
   - **structured output:** strict schema, JSON only, or none;
   - **tools:** yes or no;
   - **context size, vision, streaming, batch:** batch is the provider's batch API, or none;
   - **its price:** USD per token in its pricing model (Anthropic's with its cache and batch
     terms), or credits with input and output multipliers;
   - **its tokenizer calibration:** chars per token, measured from its own usage, as 1.8 was;
   - **its provider and lane.**

   Features declare what they need (a pin names a capability set and a default model), and only
   models that meet it are offered for that feature, in Settings › AI and in the setup wizard.
   - A strict-schema feature is never offered a model with no structured output.
   - A plain question-and-answer feature may take an assist model.
3. **Mercury's own validation, with a bounded retry, where a provider offers only JSON mode.**
   - Every answer is validated by the committed strict Pydantic model, as now (PHASE8_PLAN 15.4).
   - A JSON-only model gets the schema in its prompt and its answer parsed and validated.
   - A failure is retried once, with the validation error named, inside the same call's caps and
     counted in spend; a second failure is "couldn't answer", recorded as today.
   - A strict-schema model is never retried for shape.
4. **Qualification per feature and model, on the recorded and blind sets.**
   - Settings › AI shows each feature's models as **qualified** (at its 15.12 bar on both sets,
     with the run named), **below the bar** (with the figures) or **untested**.
   - Only a qualified model is a feature's default.
   - The other states may be chosen by an admin with a reason, the feature then labelled as such.
   - A case file records the model it was measured on. `cases_off_pin` becomes "measured on this
     model", so a set is re-run per model and the old results stay, labelled.
   - The blind-set rules stand: a set decides once per model.
5. **A fitness test** (extending tests/test_ai_boundary.py): no provider SDK import, and no model
   ID outside the adapters, the registry and the labelled fixtures. It finds IDs by the
   registry's own list and by the providers' ID shapes, and is shown able to fail on a planted
   ID in a feature module.

### 5.3 The OpenAI-compatible adapter, and GenAI.mil as its preset

- **The adapter:** `POST /v1/chat/completions`, with a Bearer key and a configurable base URL.
  It sits beside `modules/ai/anthropic_adapter.py`, through the same gateway.
  - It is one adapter per API shape (PHASE8_PLAN 14.1): any OpenAI-compatible server uses it on
    a Personal or Commercial profile.
  - GenAI.mil (`https://api.genai.mil/v1`) is a shipped preset. On a government profile it is
    the only base URL, fixed and not editable.
- **Schemas:** `schema_for(model, provider)` (PHASE8_PLAN 15.4) derives what this provider is
  sent from the committed schemas, and CI checks every committed schema against its strict
  subset.
- **The request shape**, from the portal's own example (2026-11-04), its key replaced:

  ```
  curl -X POST https://api.genai.mil/v1/chat/completions \
    -H "Authorization: Bearer <key>" \
    -H "Content-Type: application/json" \
    -d '{"model": "gemini-3.5-flash-lite-withtools", "messages": [{"role": "user", "content": "Hello!"}]}'
  ```

  A key is never stored or shown in an example, a document or a test: `<key>` stands for it.

### 5.4 The models, by what they can do

The portal's model table, 2026-11-04: a snapshot, not a contract. It ships as the preset's
default in the registry (5.2). The model list is refreshed from `GET /v1/models` where the
endpoint answers it; a model the endpoint no longer lists is drawn unavailable, never removed
from the record of calls that used it.

| Model | Lane | Input | Output | Capabilities |
|---|---|---|---|---|
| `gemini-3.1-flash-lite-withtools` | standard | 1x | 1x | tools, vision, streaming, structured output |
| `gemini-3.5-flash-lite-withtools` | standard | 1x | 1x | tools, vision, streaming, structured output |
| `gemini-3.8-flash-withtools` | standard | 1x | 2x | tools, vision, streaming, structured output |
| `gemini-4-argon-withtools` | standard | 1x | 2x | tools, vision, streaming, structured output |
| `gemini-3.8-flash` | assist | 0x credits | | vision, streaming |
| `gemini-4-argon` | assist | 0x credits | | vision, streaming |
| `gemini-embedding-2` | standard | 1x | 0x | embeddings |

**The multipliers are kept in the shipped table,** because the API may not report them. An admin
may correct one on the Credentials page, recorded with who and why, and the spend tracker uses
the corrected value from then on.

**Feature routing**, within the registry's rule (5.2, item 2):

| Need | Allowed models | Default |
|---|---|---|
| strict-schema output (Explain, the SDN Responder, the heal analysis, Change it in words and the rest) | the `-withtools` models | `gemini-3.5-flash-lite-withtools` (the cheapest, 1x and 1x), until qualification (5.2, item 4) names another |
| plain question and answer (the toolbar assistant's how-to answers) | the `-withtools` models, or an assist model (0x credits) | an assist model, once qualified |
| embeddings (the toolbar assistant's manual retrieval, 16.10) | `gemini-embedding-2` | none, until measured against today's retrieval |

- **The admin picks a model per feature,** within those rules. The gateway refuses a pin that
  asks an assist model for structured output, naming the model and the feature.
- **A `-withtools` model's structured output is strict-schema or JSON-only,** as the probe
  results show (5.7). If JSON-only, 5.2's item 3 applies: Mercury's own strict validation, with
  one bounded retry.

### 5.5 The budget: a credits mode for the spend tracker

- **Credits, not dollars:** the spend tracker (PHASE8_PLAN 18.3) gains a credits mode for this
  provider.
  - **The portal's Tier 1 Builder limits** (a Tier 2 exception can be requested): 5.0M credits
    a day on a 24-hour window with a stated reset time.
  - **The table:** the budget and its reset time, and each model's input and output
    multipliers, kept as a dated table in code, like today's prices.
  - **What the screens show:** the chip and the panel show credits used today against the
    budget, the time of the next reset, and each feature's credits. Screens say the portal
    accounts what is spent.
  - **The thresholds:** the 50% and 80% warnings and the stop at the cap work as today, in
    credits.
- **The AI budget QoS** (PHASE8_PLAN Appendix A.1, the 2026-11-01 brief's item 10) applies to
  the credit budget: its classes and reservations are measured in credits on this provider.
- **Client-side limits at the portal's own:**
  - 500K tokens per minute and 120 requests per minute, each a token bucket in the gateway,
    shared across worker processes;
  - backing off on a 429, honouring `Retry-After`;
  - recorded through `provider_limit` as today, so a held limit is said, never retried blind.

### 5.6 The connection test and the key

- **Settings' connection test tells the two failures apart:**
  - **"Blocked by network":** a 503 answered with an HTML "Unauthorized Access" page, which is
    what a network outside the government's gets. Recognised by status and body together, and
    said as such.
  - **"The key was rejected":** a 401 or 403 with the service's JSON error.
  - Anything else is shown as received: status, content type and the first line, masked.
- **The key is entered on the Credentials page only,** stored in the secret store, owner-only
  from creation (`config.open_secure`). It is never printed, logged or returned (CLAUDE.md), and
  is deleted, not disabled, when a profile change forbids it (2.3).

### 5.7 Its tests use a fake built from measured probes

The adapter's tests use a fake service built from the operator's measured probe results, which
are to follow. The fake must refuse what the real service refuses, and each refusal is a planted
case:
- a bad key;
- the network block's 503 page;
- a 429 with `Retry-After`;
- an assist model asked for tools or structured output;
- a request over the token limit.

No refusal shape is typed from memory (CLAUDE.md: fixtures are real captures).

### 5.8 The estimate

By the measured ratio (PHASE8_PLAN 0.3, C2380), 1 agent-day is about 1.3 h of one agent's wall
time (0.7 to 2.6) and about 4M weighted tokens (2.5M to 9M). Each part's tests come first, red
then green, and each new check is shown able to fail.

| Part | What | Days |
|---|---|---|
| P1 | The adapter interface and the neutral `Reply`: the body built, the answer, stop, usage and limits normalised in `anthropic_adapter`; the gateway's dispatch; Anthropic behaviour unchanged, held by today's tests | 1.5 |
| P2 | The registry (5.2, item 2): the three Claude models and the GenAI.mil table moved in; pins name a capability set; the per-model tokenizer calibration | 1.0 |
| P3 | Pricing per provider: Anthropic's model (cache, long tier, batch) and the credits model (multipliers, daily budget, reset); the caps and the spend tracker's credits mode | 1.0 |
| P4 | The OpenAI-compatible adapter (5.3): the body, strict or JSON-only output, the token buckets, 429s, the connection test's two failures, the fake from the probes | 1.0 |
| P5 | JSON-only validation with its one bounded retry (5.2, item 3) | 0.5 |
| P6 | Batch as a capability: a provider with no batch API runs an evaluation as paced single calls under its limits | 0.75 |
| P7 | Qualification per feature and model (5.2, item 4): case files keyed by model; qualified, below the bar or untested, in Settings › AI | 0.75 |
| P8 | The neutral stored call record, with a reader for old rows (expand, then contract, CLAUDE.md) | 0.5 |
| P9 | A key per provider: `anthropic_api_key` kept readable, a key per provider added (expand, then contract) | 0.25 |
| P10 | The fitness test (5.2, item 5) | 0.25 |
| P11 | The profile rule in the gateway (section 4.2): the shipped `GOVERNMENT_PROVIDERS`, the base URL compared whole, the refusals | 0.5 |
| **Total** | | **8.0** |

**8.0 agent-days is about 10.4 h of wall time** (5.6 to 21) and about 32M weighted tokens (20M
to 72M). The last stage of this kind ran about 75% long, so read 8.0 as up to about 14. The
wizard, the banner, egress and the manager link are NSOT_STAGE10_PLAN 5.3's, estimated with it.

**Not in the estimate: qualifying the GenAI.mil models.**
- Each feature's recorded and blind sets are re-run on each model offered: ten runs a case, as
  15.12 asks, at the portal's credits.
- They can run only from a network that reaches GenAI.mil; anywhere else the portal answers 503
  (5.6). So the runs are the operator's sittings, or a runner on an authorised network.
- They are the irreversible tier's egress, so their hand check comes first (CLAUDE.md).

## 6. The edge-fleet manager and subordinate link

The link of EDGE_ARCHITECTURE section 7 gains a marking exchange.
- **When a manager and a subordinate connect, they exchange their profiles** (use type and
  marking), each signed with its node identity (EDGE_ARCHITECTURE section 3).
- **A mismatch is refused, on both sides, with the reason shown on each:** "this node is SECRET;
  the subordinate kit-07 is COLORLESS: no link across domains". It shows as a Critical Needs
  attention row on the manager's Subordinate nodes page and on the subordinate's Upstream
  manager card.
- **Nothing is exchanged before the profiles match:** no summary, no playbook, no record.
- **A profile that changes on either side** (the wizard rerun) drops the link until the profiles
  match again.

## 7. Required tests (written when it is built)

Each test is shown able to fail by a control that removes its property (CLAUDE.md).
1. **On a government profile, a call to any provider other than GenAI.mil is refused in the
   gateway,** with no provider request made. That includes after a hand-edited setting naming
   another provider, and after an edited base URL. The control: the profile check removed, and
   the planted calls go through.
2. **A Secret installation refuses GenAI.mil,** and its AI features are drawn off with the
   reason, on every page with an AI control (15.13's census).
3. **A profile or marking change outside the wizard is refused:**
   - by every settings route;
   - by a hand-edited profile, which fails its MAC and reads as most restrictive;
   - by an import of settings.
4. **The banner appears top and bottom on every v2 page,** by the route census used by
   tests/test_route_reachability.py. It also appears on every export and printed report: the
   CSV first and last lines, and each PDF page's header and footer.
5. **A SECRET manager refuses a COLORLESS subordinate, and the reverse,** with the reason drawn
   on both sides and nothing exchanged.
6. **A profile change deletes the keys the new profile forbids,** each named in the change
   record; the secret store holds none of them afterwards.
7. **Default-deny egress:** on a government profile each of 4.4's paths is refused until an
   admin allows that destination with a reason.
8. **The adapter's fake refuses each refusal of 5.7,** and the gateway reports each as 5.6 says.
9. **The fitness test of 5.2, item 5:** no provider SDK import and no model ID outside the
   adapters, the registry and the labelled fixtures, shown able to fail on a planted ID.
10. **A JSON-only answer that fails validation is retried once, and a second failure is
    "couldn't answer";** a strict-schema model is never retried for shape.
11. **A feature is offered only the models whose declared capabilities meet its need,** and an
    unqualified model is drawn as untested or below the bar, never as qualified.
12. **A CUI installation allows GenAI.mil:** a call under the CUI marking reaches the GenAI.mil
    adapter (its fake), recorded under the profile.
13. **A COLORLESS installation refuses GenAI.mil:** the call is refused in the gateway, no
    provider request is made, and the AI controls are drawn off with the reason.
14. **Every email and every webhook carries the installation's marking:** the subject prefix and
    the body's banner line on each email the notifier sends, and the `marking` field in each
    webhook payload, over every notice kind the notifier has; and on a government profile a relay
    or target not allowed under 4.4 sends nothing, its delivery log saying why.

## 8. The operator's answers (2026-11-04)

1. **GenAI.mil's accreditation: UNCLASSIFIED and CUI only.** On a government profile GenAI.mil is
   allowed when the installation is marked UNCLASSIFIED or CUI. AI is off on every other marking:
   CONFIDENTIAL, SECRET, TOP SECRET, TS//SCI, COLORLESS and Other (4.1).
   - **Recorded as decided.** The operator will give more detail later, and the policy table may
     widen then.
   - **Any change goes through the shipped provider list (`GOVERNMENT_PROVIDERS`) and a release,**
     never through Settings.
2. **The presets:** UNCLASSIFIED (green), CUI (purple), CONFIDENTIAL (blue), SECRET (red), TOP
   SECRET (orange), TS//SCI (yellow), COLORLESS (grey), and Other (free text and a colour
   picker) (2.2).
3. **Emails and webhooks carry the marking** (3 and 4.4):
   - every email: a subject prefix and a banner line in its body;
   - every webhook payload: a `marking` field;
   - on a government profile, mail relays and webhook targets fall under default-deny egress.

   Tests 12 to 14 in section 7 hold these.

## 9. Air-gapped mode (the operator, 2026-11-04; design only, built after both labs)

**The requirement.** On a classified network, public sites, GitHub included, are unavailable and
must never be attempted, not even by a DNS lookup, because an attempt is logged as a security
event. Default-deny that refuses after trying (4.4) is not enough: the attempt itself is the
event.

**Who has it.**
- A US Government profile turns air-gapped mode on, set by the wizard and locked like the
  marking (2.3).
- Any profile may choose it: the edge-kit case (EDGE_ARCHITECTURE), a lab, a commercial enclave.
  Turning it off needs the wizard rerun, as the marking does.

**Why it is safe to rely on.** Interconnected systems on separate classification domains are
expected to send nothing but what their accreditation names (NIST SP 800-53 SC-7, boundary
protection, and AC-4, information flow enforcement). A refusal made after a resolve or a connect
attempt has already crossed the boundary, so the check must come before any name is resolved.

### 9.1 One outbound door

- **The client.** Every outbound connection Mercury makes goes through one client, the outbound
  door. Before it resolves any name or opens any socket, it checks the destination against the
  installation's allow-list of configured hosts.
  - **The allow-list holds:**
    - the integrations' configured URLs (NetBox, Grafana, Prometheus, Loki, Kea, the mail
      relay, webhook targets);
    - the AI provider's preset where 4.1 allows one;
    - the managed networks' prefixes, for device sessions, pings and traceroutes;
    - the internal NTP server, the internal DNS resolver, and the internal registry or mirror
      (9.4).
  - **Each entry is exact:** a scheme, host and port, or an address prefix; never a pattern.
- **A refusal is immediate and clear,** never a timeout. For example: "air-gapped: <host> is not
  on this installation's allow-list; nothing was sent, not even a DNS lookup". It is recorded as
  every refusal is, and shown in place on the screen that asked.
- **Subprocesses go through it too.** git, ssh, ping, traceroute and the update runner each take
  their destination from the door, which refuses it the same way before the process starts.
  - The git remote is a configured internal server, or none.
  - The CI-verdict reader asks GitHub only where the allow-list names it, which it never does in
    air-gapped mode.
- **A fitness test fails if any code opens a socket, an HTTP session or a subprocess network call
  outside the door.**
  - It parses the code for `socket`, `requests`, `urllib`, `http.client`, `httpx`, `smtplib`,
    `paramiko`, `netmiko` sessions, and `subprocess` calls whose program is a network one (git
    with a remote, ssh, scp, curl, ping, traceroute).
  - It is shaped like tests/test_ai_boundary.py, with planted cases.
  - The door's own module, and the test harness's guard (tests/test_network_guard.py), are its
    only exceptions.

### 9.2 The stack's phone-homes are off

On an air-gapped install, every phone-home in the stack Mercury bundles is turned off in the
configuration the install writes, and checked by its own test. Among them:
- NetBox's release check;
- Grafana's update checks, usage reporting, plugin catalogue and news feed;
- any other the inventory (9.7) finds: Loki's usage report, the base images' package
  managers, and so on.

A setting the stack cannot turn off is named, and its traffic is refused at the namespace (9.6),
never left to chance.

### 9.3 No runtime fetches

- Every JavaScript, CSS and font asset is served by Mercury itself, with no CDN and no Google
  Fonts.
- Every v2 page already runs under `csp.STRICT_POLICY`, whose `script-src`, `style-src` and
  `font-src` are `'self'`, and libraries are vendored (CLAUDE.md).
- What remains is the rest of the stack's own pages, the manual's and the exports' assets, and a
  test that fails on any external URL in a served asset.

### 9.4 Install and update only from signed bundles

- **The source:** images, wheels and releases come only as signed bundles: on media, or from an
  internal registry or mirror the allow-list names. Nothing is pulled from the internet.
- **This ties in C2370,** an offline Mercury that cannot update today because the update gates on
  GitHub's CI verdict. Air-gapped, the verdict comes with the bundle:
  - a signed record of the CI run that passed the release;
  - and, where the installation keeps one, its own local runner's verdict (docs/LOCAL_CI.md).
- **The bundle's signature** is checked against a key the installation pins at setup. An unsigned
  or mismatched bundle is refused, naming both keys.

### 9.5 Trust, time and telemetry

- **A configurable CA bundle:** for example the DoD PKI roots, used by every TLS connection the
  door makes; the system's public roots are not trusted unless the admin keeps them.
- **Internal NTP only:** the host's time source is the configured internal server, and a public
  pool is never asked.
- **No external telemetry or crash reporting,** from Mercury or its stack. Mercury sends none
  today, and a test keeps it so.

### 9.6 The acceptance test

- **The setup:** Mercury and its stack run in a lab network namespace with no route out. A
  logging rule records any packet, or any DNS query, to a destination not on the allow-list.
- **The walk:** every page and every feature, the manual's list of screens and operations
  (docs/manual/) as the checklist, including an update from a bundle and a notification to an
  allowed relay.
- **PASS is zero logged attempts.**
  - Any logged attempt fails it, named by its source and destination.
  - The fix goes through the door or the stack's configuration, never by widening the rule.

### 9.7 The inventory of outbound call sites and phone-homes

To be filled by a read-only survey, once an agent slot is free: every outbound call site in
Mercury's code (file and line, and what it contacts), and every phone-home in its stack's
configurations (NetBox, Grafana, Prometheus, Loki, Kea, and the containers' base images; the
setting, and what it contacts). EDGE_ARCHITECTURE section 9.3's table of the paths by which data
leaves a host is its starting point.

### 9.8 Required tests (written when it is built)

1. The door refuses a destination not on the allow-list before any resolve or connect: a planted
   call under a resolver and a socket stub that record any use sees neither used, and the
   refusal's words name the host.
2. The fitness test of 9.1, with planted sockets, sessions and network subprocesses outside the
   door.
3. Each phone-home of 9.2 is off in the configuration an air-gapped install writes.
4. No served asset names an external URL (9.3).
5. A bundle that is unsigned, or signed by another key, is refused (9.4).
6. The acceptance test of 9.6, as a recorded walk with its packet and DNS log.
