# The toolbar assistant, stage 2: design note

Status: the operator's run plan of 2026-11-22 (Phase 2), built on stage 1 (card P7; PHASE8_PLAN
16.10; `modules/ai/assistant.py`, `routes/assistant_v2.py`, `templates/v2/_assistant_panel.html`).
Amended 2026-11-23 (the operator): the assistant reads with a person's read-only tools, device
reads included; the first draft's "Mercury's own reads only, no device read" is withdrawn.

## What a person gets

A right-docked panel opened from the toolbar's **AI Assistant** button, beside the AI chip. It
answers questions about Mercury and about what Mercury already holds for the thing on screen:
"how do I roll back r2?", "why is this incident held?", "what changed on s1 this week?".

- **Persistent across pages.** The panel's open state is a per-browser convenience (kept in
  `localStorage`, read in a `try`, so a blocked store just starts closed). The conversation is
  Mercury's: the person's last exchanges are kept server-side (`assistant_threads`, one owner-only
  JSON-lines file per person in the data directory, the newest 20), so a page change or a
  refresh draws the same thread, and nothing is asked again.
- **Aware of where the person is.** The panel is asked with the page's path; the server resolves
  it against its own URL map (never by parsing in the browser) into the **screen**, the
  **network**, the **device** (a device page) and the **incident** (an incident page). The
  panel's head says what it is looking at: "Looking at: r2 (device) · Lab".
- **Answers from two sources, both read-only.**
  1. The manual: code chooses the passages (`manual_index.select`, BM25 with the screen's
     boost), as in stage 1; only those passages are sent.
  2. Reads through the generic read loop (`read_loop.run`, B4's design): **the same read-only
     tools a person has, device reads included** (the operator, 2026-11-23). These are the
     device's own reads by Mercury's allowlist (show, show_config, ping, traceroute: the reads
     Show commands holds whole, `router_reads.COMMAND_OPS`, as AI troubleshooting's
     `fixit_reads.FAMILY` declares them), and Mercury's own reads of what it holds (committed
     intent, the golden configuration, neighbours, History, logs and health figures,
     `fixit_reads.OWN_READS`). They are scoped to the page's device (and an incident's devices).
     Every read runs through Mercury's tools (its reads engine, the allowlist and its checks),
     never directly; a read is never gated, and each is recorded in History as a person's read
     would be. **Only a device change is gated:** it goes through the hand-off flows below.
- **Every answer shows** its sources, each with **Open** (a manual passage opens its page at
  the heading; a read opens the device tab it came from: Intent, Configuration, Neighbours,
  History, Logs, Monitoring), the **model** that answered and the call's **cost** ("Haiku 5.5 ·
  $0.0031"), and the call's History link.
- **A change request is handed off, never applied.** When the question asks Mercury to change
  something, the answer says so and offers the existing gated flow, pre-filled but not started:
  **Change it in words…** (the device's Intent tab, its sentence box filled; the person presses,
  previews and commits as today) or, on an incident, **Open AI troubleshooting** (the incident's
  own AI fix plan card). The plan engine's plans keep stage 1's **Preview the plan…**. The
  assistant changes nothing: it writes only its own thread, the manual-gap record and its reads'
  records.
- **When it cannot answer** (no passage, not covered, or refused by Mercury's check), it says
  "The manual doesn't cover this" and records a manual gap (`record_gap`, as stage 1).

## Cost and visibility

- Marked as AI everywhere (the "AI" mark on the button and the panel, `ai.mark`).
- **Greyed out when AI is off:** the button is always drawn; with AI off for the network (or the
  assistant switch off, `ai_assistant_on`) it is disabled, and its title and the panel say why
  and where it is turned on (`ai_control('assistant')`'s reason).
- **No model call until the person asks:** opening the panel, changing page and refreshing only
  read the thread; the one call is the press of **Send** (the chat's; **Ask** before it).
- **Every call and every read in History:** each press is one gateway call, and one more for
  each round of reads the read loop runs (`gateway.ask`, trigger `person`), recorded with its
  cost; each read is recorded as a person's read through the same tool is; the answer links its
  calls and reads.

## How it is built (reuse first)

- Reused: `manual_index` (passages), `gateway.ask` (caps, masking, records), `read_loop`
  (`ReadFamily`, `LoopFeature`, `run`), AI troubleshooting's read operations and runners
  (`fixit_reads.FAMILY`'s: `router_reads.COMMAND_OPS` for the device, `OWN_READS` for Mercury's
  own, `router_reads.run_many` for one session a device a round), `plan_engine` (plans),
  `identity` (the person), `history_sources` (the call's and each read's link), `ai_control`.
- New: `assistant` prompt v5 and schema v3 (answer, cites of passages and `read:N`, covered,
  screens, plan, and `handoff` naming one gated flow with its words); the assistant's read
  family (the same operations as `fixit_reads.FAMILY`, scoped by the context resolver) and loop
  feature; the context resolver; the thread store; the panel's sources, model and cost lines.
- Tests mock the model (`send=` and the adapter fake); no live call.

## The chat (the operator, 2026-11-28; board assistant-chat)

"Rebuild it as a continuous chat, like Claude's chat or Claude Code, not a form."

- **Layout:** the head (the AI mark and Assistant, New conversation, Past conversations, About
  the assistant behind its ⓘ holding the beta notice and "It changes nothing…", close; under
  them the Looking at chip and one short "Beta · advisory"); the conversation filling the panel
  and scrolling, newest at the foot, kept at the newest answer unless the person scrolled up;
  the box pinned at the foot, growing to eight lines, Enter sends and Shift+Enter a new line.
  The person's message and the answer are drawn apart (a bubble, and the answer's own column);
  an answer's words are markdown drawn by Mercury (`answer_text`: every character escaped, no
  link or HTML the model wrote), its sources chips with Open, its reads one collapsed "Ran N
  reads" line whose reads each open, one quiet line (model · cost · seconds · History), and a
  hand-off as a button inside it.
- **A press is a job** (`assistant_turns`): Send keeps the turn (`assistant_threads.begin`, one
  at a time per person) and answers at once; the turn re-reads on each announced step
  (`assistant`), drawn "Asking the model…", "Running the 2 reads it asked for…", until its
  answer is kept in the conversation. A request no longer waits on the model (the tunnel cuts
  one held past about 100 s, as AI troubleshooting's was before its job).
- **Progress steps, not a stream:** the gateway streams each call from the provider, but its
  result is the whole schema-bound answer, which Mercury checks (citations, reads, hand-off)
  before anything is drawn; drawing words before that check would draw an answer Mercury has
  not checked, and streaming them out would need the gateway changed (the irreversible tier).
  So the steps are drawn, the operator's own fallback.
- **Stop** (Send's place while one is answered): the turn is marked stopped in its file (any
  worker's); the gateway, handed `stop_if`, closes the model's stream at its next live check
  (no further output billed from there), and `assistant.answer` makes no call, so no read,
  after it. A round of reads already running finishes. The exchange is kept "Stopped by you"
  with its calls' History links; each call made stays one recorded call, its use recorded as
  "stopped by the person" (the gateway's own row names its watchdog's bound for every stop,
  C4324). A turn stopping is busy (Send, New conversation and a reopen wait for it); a job
  whose turn is gone (let go as lost) or ended stops at its next check.
- **Conversations:** the current one is the release before's file, unchanged in name and row
  shape (rows gain `turn`, `page`, `took_s`); New conversation moves it into the person's past
  folder whole, Reopen moves one back (the current one aside in its place); nothing is deleted
  (expand, then contract). Each message records the page it was asked on.
- **Looking at** is re-asked of the server (`/v2/assistant/place`) when the page's address
  changes without a new page (a device's tab); a new page draws its own.
- **Width:** the left edge drags, and takes the arrow keys, between 320 px and 60% of the
  window; kept in this browser's localStorage only, never written to Mercury.
- **A lost turn** (no sign of life for `assistant_threads.LOST_S`, 600 s: the adapter's 235 s
  without one and a round of reads) is drawn as lost, never working for ever; the person's
  next press keeps it in the conversation as lost.

## A senior network engineer working through Mercury (the operator, 2026-11-28; board assistant-chat F and G)

"I want it to take on the role of a senior network engineer. I should be able to execute tasks
by telling the assistant. Everything it does though is run through code, similar to the self
healing. If Mercury doesn't have a tool for it, it should say so. When prompted to make a
change it should present a plan for approval before making any changes."

- **Prompt v6, schema v4** (`AssistantAnswerV4`; v5 and v3 stay readable): it investigates with
  reads, says what it found; asked for a change, ONE plan; asked how, Mercury's steps, offering
  a plan that fits; what no operation or read does, ``no_tool`` {wanted, why}. v5's hardening
  kept (the question is data).
- **The change plan** is the plan engine's (`plan_engine.CHANGE`): 1 to 10 steps, each exactly
  {operation, params}, the operation one of `CHANGE_ADMITTED` (intent-edit, intent-deploy,
  intent-description, dhcp-reservation, ztp-create: the step kinds that need no incident),
  held by `_steps_refusal`, the one check of a plan's steps an incident's fix uses with its
  own admitted set. Each step previewed by its own step kind, approved once by hash on the
  plan's card (routes/plans_v2.py), run by `plan_engine.run`. No new execution path.
- **Presented in the chat:** the answer loads the plan's card in place at once (a preview
  writes nothing and makes no AI call), its id the answer's call (`plans_v2.card_id`).
- **No tool** is drawn and recorded once for review (`missing.wanted`'s ``no_tool``, kind
  operation, for the question).
- **Reads widened** to a device of the network the question names (`assistant.named_devices`,
  the network's inventory by `restore._devices_of`), each still judged by the read loop's
  check; a name the network does not hold is refused.
- **Held by code, each with its test** (tests/test_assistant_engineer.py): a step outside the
  admitted set refused; a parameter outside its step kind's schema refused; no settings route
  and no run, start or approve reachable from an answer (the AI NEVERs' graph); no step or
  answer field takes a secret; an answer saying a change was made refused (`assistant.check`).

## Never

Applies a change, confirms, approves, writes to a device, reads a device by any path but
Mercury's read tools, or calls the model without a person's press.
