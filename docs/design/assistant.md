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
  read the thread; the one call is the press of **Ask**.
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

## Never

Applies a change, confirms, approves, writes to a device, reads a device by any path but
Mercury's read tools, or calls the model without a person's press.
