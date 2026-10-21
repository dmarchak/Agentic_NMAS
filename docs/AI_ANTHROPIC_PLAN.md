# The first AI release, on Anthropic (Phase 8, pulled forward): plan

**Status: a plan for the operator's review (2026-10-20). Nothing in it is built.** The operator
decided on 2026-10-20 to pull Phase 8's first features forward, ahead of Core 1.0's sign-off,
to a feature freeze around 11-20 (NSOT_PLAN section 9 records the decision and its
consequences). This is that release: its scope, its foundations, its order around Labs 8 and
9, and the decisions it needs. It builds on docs/PHASE8_PLAN.md, whose rules it keeps, and
names where it departs from them.

**Priority, standing (the operator, 2026-10-20):** Labs 8 and 9 come first, always: the ZTP
build, the walks, the recordings and the submissions. This work never takes a gate, a deploy
slot, a lab window or the operator's attention ahead of a lab step. When the two compete the
lab wins, and what slipped here is said.

## 1. The rules every feature keeps

1. **AI advises; it never acts.**
   - Nothing an AI feature produces reaches a device, Kea, NetBox or a store by itself.
   - A query it writes is read back by the deterministic builder before it runs (read-only
     queries only).
   - An action it proposes (the stretch, item 5.5) ends in the normal preview and confirm by
     hash, by a verified person. "Proposed by the AI, confirmed by <person>" is recorded (the
     charter's AI-assisted actions).
2. **No secret ever leaves.** Every payload passes the masking boundary before the call
   (section 3.3), and a red-team set fails the release on any known secret, any credential
   shape, or any instruction planted in device data reaching the request unmasked.
3. **Every answer cites the data it used.** Each citation is a link to the record in Mercury:
   a device's page, a History entry, a golden at its commit, a Needs attention row, a
   Topology island or a monitoring query.
   - An answer with no citation is drawn as unsupported, never as an answer.
   - Retrieved, never trained: Anthropic's commercial terms say customer content from the API
     is not used for training (section 3.6).
4. **Structured outputs only:**
   - shapes A, B and C (PHASE8_PLAN 13.4);
   - a strict schema per feature, sent as `output_config.format` (`json_schema`) or as strict
     tool use;
   - Pydantic validation of every response;
   - `stop_reason` `refusal` and `max_tokens` each handled as a named error, never a partial
     answer (Anthropic: a refusal can break the schema, and so can a truncated answer).
5. **An evaluation suite per feature gates it.** At least 30 golden cases, at least 10 of them
   real, with consistency over 5 runs (PHASE8_PLAN section 7 and 11.1). A feature, prompt or
   model change merges only at or above its threshold.
   - CI replays recorded responses and calls no model (the suite is confined to loopback).
   - The live suite runs on the host as a job, costed.
6. **Offline-first is a release gate.** Mercury without AI is complete: with no key, or AI off
   for a network, each AI control is drawn disabled with its reason ("AI is off: no provider
   key is set (Settings › AI)"). Nothing is possible only with AI, and a test holds the app
   whole with no key.
7. **Prompt caching where it pays:** the feature's fixed system prompt and schema as the cached
   prefix (at least 512 tokens on the 5.5 models), measured in the record (cache reads cost
   0.05x to 0.1x of input).
8. **Model per feature, chosen by its eval,** pinned by exact id and recorded with every call:
   - Haiku 5.5 first, as the cheapest;
   - Sonnet 5.5 where the eval needs it;
   - Opus 5.5 never by default (PHASE8_PLAN section 7);
   - Fable 5.1 not at all: its required 30-day retention excludes zero data retention, and
     it costs the most.

**Current Anthropic facts this plan relies on** (read 2026-10-20 from Anthropic's docs; checked
again before the build):

| Model | Id | Price per MTok, input / output |
|---|---|---|
| Haiku 5.5 | `claude-haiku-5-5` | $0.10 / $0.50 (prompts up to 100K) |
| Sonnet 5.5 | `claude-sonnet-5-5` | $2 / $10 |
| Opus 5.5 | `claude-opus-5-5` | $4 / $20 |
| Fable 5.1 | `claude-fable-5-1` | $10 / $50 |

All four have a 1M-token context.

**Structured outputs** are generally available on every current model, with no beta header.
Constrained decoding means no retries for schema violations, but its schema features are
limited:
- no `minimum`, `maximum`, `minLength` or `maxLength`;
- `additionalProperties` must be false.

Pydantic checks the rest.

**Prompt caching:** `cache_control`, at most 4 breakpoints, a 5-minute or 1-hour TTL. Writes
cost 1.25x or 2x of input. Changing the output format invalidates the cache.

## 2. Decisions for the operator (before any code)

1. **The masking boundary for this release.** PHASE8_PLAN 13.2 masks through C733's
   keyed-digest index, a Stage 10 redesign (L).
   - **Proposed:** mask through `redact.redact_payload`, which is known values plus positional
     rules and already exists and is tested (`tests/test_provider_redaction.py`). Close C745
     (the IOS credential shapes `redact_positional` misses) first, and add the red-team set.
     C733 replaces it at Stage 10.
   - Size: C745 M, the red-team set M.
2. **New package licences** (the operator's, CLAUDE.md).
   - **Pydantic** (MIT) for the schema library: proposed.
   - The **`anthropic` SDK** (MIT; 1.17.0 on 2026-10-20) or **none**:
     - **Proposed: none.** The two adapters (Anthropic now, OpenAI-compatible later) call HTTP
       through `requests`, already a dependency. That gives one HTTP stack, no SDK's
       dependency tree, and the provider layer owns retries and headers.
     - The SDK's `messages.parse` helper is the one thing given up. Pydantic's JSON Schema
       export replaces it.
3. **Where the AI-call record lives.** E18 (K31, the one records store) is not built.
   - **Proposed:** an append-only record per network, as the receipts are: masked prompt,
     model and version, tokens with cache reads and writes, cost, latency, structured output,
     verdict, one id.
   - Drawn in History as its own kind; moved into E18 when K31 lands.
4. **Caps.** PHASE8_PLAN section 7's numbers carry: $50 a month globally, $25 per network,
   $5 or $10 per feature, enforced in Mercury before each call. **Proposed besides:** a
   workspace spend limit in Anthropic's Console as a second, independent cap (outside the
   lab, so the operator's to set).
5. **Data posture.** Proposed:
   - **Retention:** state Anthropic's own wording on the Settings page (no training on API
     content; retention per their docs and privacy centre, which differ: "not retained by
     default" against "deleted within 30 days"; the stricter is shown).
   - **US-only inference** (`inference_geo: "us"`, 1.1x price) offered as a setting, off by
     default.
   - **Zero data retention** named as available by arrangement, not assumed.
6. **Who may use AI:** any verified person with the viewer role. No AI feature writes, so none
   needs `author`.

## 3. The foundations (P0)

| Piece | What | Size |
|---|---|---|
| 3.1 Provider layer | One interface: `ask(feature, shape, schema_model, parts, model) → validated object` or a named error (refusal, max_tokens, schema, rate limited, over cap, provider down, unmasked secret found). The Anthropic Messages adapter over `requests`. A second adapter type later (PHASE8_PLAN 14.1). Pinned model ids per feature; retries only on 429 and 529, honouring `retry-after`; a bounded queue per provider; per-feature concurrency. | M |
| 3.2 The key | `anthropic_api_key` joins `secrets_store.SECRET_KEYS` (encrypted at rest with `data/key.key`, owner-only). Set on Settings › AI by the operator, typed, never shown again (write-only, masked), never in the repository or a log. A "Test connection" that sends one cheap request and reports the model list and the rate-limit headers, never the key. | S |
| 3.3 The masking boundary | `redact.redact_payload` on every payload, after normalisation (PHASE8_PLAN 11.7), then `contains_known_secret` as a refusal check: a payload still holding a known secret is refused, never sent. C745 closed first. Device-sourced text (log lines, labels, descriptions) delimited as data, never instructions. | M (with C745) |
| 3.4 Caps and limits | The month's recorded spend per network and per feature, from each response's usage times the pinned price table (cache reads and writes priced). A call whose worst case (its input estimate and `max_tokens`) would cross a cap is refused before it is sent, naming both operands. Anthropic's `anthropic-ratelimit-*` headers recorded. | M |
| 3.5 The record and the usage view | The append-only record (decision 3). Settings › AI shows: this month's spend against each cap, calls, tokens, cache hit rate, errors by kind, the newest calls each linked to its record. | M (a board first) |
| 3.6 "What is sent" | Settings › AI states, per feature, exactly what leaves: the question, the retrieved records named, masked. It also states what never leaves (secrets, credentials, configuration lines in secret positions) and Anthropic's terms (decision 5). | S |
| 3.7 Schema library and shapes | Pydantic models per feature, exported to JSON Schema within Anthropic's supported subset (a test refuses a schema using an unsupported keyword); A, B and C per 13.4. | S |
| 3.8 Eval harness | Golden cases per feature in the repository; recorded responses replayed in CI; the live run as a host job, its result recorded with model, version, date and cost; the gate per feature. The red-team set inside it. | M |
| 3.9 Offline-first | Every AI control drawn disabled with its reason when no key is set or AI is off; a test of the app with no key. | S |

Boards (mockups) are drawn before any screen changes: Settings › AI, and each feature's control
(the rule on new screens).

## 4. The features, in order

| # | Feature | Shape | What it reads | What it gives | Size | Model to try first |
|---|---|---|---|---|---|---|
| F1 | **Natural language to PromQL or LogQL** (PHASE8_PLAN feature 1) | A | the question; the metric and label names retrieved for its terms (about 2K tokens, never the whole catalogue) | the builder's own query model. The builder reads it back and runs it: the query shown, then its result, never a query nobody can see | M | Haiku 5.5 |
| F2 | **Explain** a Needs attention row, a deploy preview, a failed Verify | B (rationale first, then fields) | the row, preview or receipt itself and the records it names | what it means, why it happened, what clears it, each sentence citing the record it rests on. It never proposes an action the row does not already offer | M | Sonnet 5.5 |
| F3 | **Ask Mercury**: read-only questions over Mercury's own data | B | through read-only retrieval tools only (strict tool use): inventory, intent, goldens masked, History, Needs attention, Topology, monitoring queries via F1. At most 8 tool calls and 60 s (PHASE8_PLAN section 7) | an answer citing every record it used ("why is r6 an island?", "what changed on r4 this week?") | L | Sonnet 5.5 |
| F4 | **Stretch, only if the intent actions framework (A1) lands:** natural language to action PARAMETERS, never YAML | A | the sentence and A1's action schema | the action's parameters, shown in A1's own form, then the normal preview and confirm by hash | M | Haiku 5.5 |

**Why this order:**
- F1 is the smallest whole path through every foundation, and PHASE8_PLAN's first feature.
- F2 reuses F1's machinery on records Mercury already draws.
- F3 adds retrieval tools and the loop, the riskiest part, so it comes last.
- F4 waits on A1.

**What each feature's eval measures (its card):**
- **F1:** 80% of queries run without an edit; 95% parse and pass the builder's read-back.
- **F2:** every sentence cites a record that holds what it says; no proposed action outside the
  row's own.
- **F3:** every claim cited; a refusal ("Mercury's records do not say") when the data is not
  there.
- **All:** consistency of 95% (translators) and 90% (analysts) over 5 runs; zero red-team
  leaks.

## 5. The calendar, fitted around the labs

| When | What | AI work allowed |
|---|---|---|
| now to 10-26 | **Lab 8:** tonight's redeploy, R6, R7, H5, the walk, the recording, the submission | **none** but this plan's review |
| 10-27 to 11-04 | **Lab 9:** 0a, 0b, the second redeploy (s5, H6, H7), R8, the switch, its testing segment, the recording, the submission | **only in gaps that take no gate, deploy or attention a lab step needs:** C745's survey, golden cases written as data, the Settings › AI board. Each item may slip, and a slip is said |
| 11-05 to 11-08 | The usability review (C1438) and the friction fixes the demo shows (C1412, C1460 part 2, the intent actions A1 if it lands) | P0 starts: provider layer, key, masking (C745), caps |
| 11-08 to 11-14 | P0 finished (record, usage view, eval harness); **F1** built, its eval run live | |
| 11-14 to 11-20 | **F2** (Explain on a Needs attention row first, then a deploy preview, then a failed Verify) | **F3 starts only if F1 and F2 pass their evals by 11-16** |
| ~11-20 | **Feature freeze** | |
| 11-21 to 11-25 | Recording the showcase (its own plan) | fixes only |

**What does not fit, said plainly:**
- **F3 at full breadth.** If it starts, it is narrowed to two or three question classes
  (an island, what changed on a device, why a row is open).
- **F4:** A1 is unlikely to land before 11-14.
- **Explain on a failed Verify,** if F2's first two take the week.
- **The usage view's polish:** a table, not charts.

**Cut first, in order:** F4; F3; F2 on a failed Verify. **The floor for the video is P0, F1 and
F2 on a Needs attention row**, all shipped and gated. That floor still meets every rule above.

**If the showcase's due date lands before 11-30:** the freeze moves to about 10 days before it,
and the floor above is the whole release. F3 and F4 move to the public release. Nothing moves
ahead of a lab step to make room.

**Pace caveat:** the sizes are the completion inventory's (S 1 to 2 h, M 2 to 8 h, L 8 to 24 h).
The first four capabilities ran at about a tenth of their mid size, and none touched a device;
AI work also needs live eval runs and the operator's review of each feature. The calendar is
re-forecast after P0, from P0's measured pace only.

## 6. What this release changes in the plans (recorded)

- **NSOT_PLAN section 9:** the decision and its consequences (Core 1.0 finishes later; masking
  through `redact_payload` until C733; the AI record until E18).
- **PHASE8_PLAN:**
  - 13.2's 8.0 is this release's P0, with F2 and F3 added after feature 1. 13.3's order put
    feature 7 second; feature 7 (natural language to intent) is this plan's F4, behind A1.
  - **The CSCI 5280 lessons:** PHASE8_PLAN holds only section 13.9's measurement plan
    (consistency, latency, tokens and cost, schema failures, refusals and truncations, shape A
    against B). No lesson from those labs is written into this repository yet. Their numbers
    are added to F1's card when the operator brings them, and no prototype code or prompt is
    copied.
  - Section 14 is the endpoint direction after the showcase.
- **The completion inventory:** K64 (8.0 and feature 1) and part of K65 (features 2, 3) move
  ahead of Core 1.0's remaining must-haves, by this decision.

## 7. Registered with this plan

- **C745** (open) becomes this release's first dependency.
- **Stale references,** each to correct when P0 starts (C783's provider boundary kept):
  - `modules/netbox_client.py`'s comment naming an AI tool layer;
  - `scripts/nmas-check-secret-storage`'s `.env` check for the old key;
  - the retiring `ai_enabled` and `background_agent_enabled` settings, which P0 reuses or
    replaces.
- **The AI-call record's home:** E18 / K31, moved there when built.
