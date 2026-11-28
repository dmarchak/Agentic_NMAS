# Fidelity: the assistant as a continuous chat (2026-11-28)

Board: `docs/boards/assistant-chat.html` (artboards A empty, B a conversation, C working, D AI off,
E past conversations; F a change's plan presented for approval and G "Mercury has no tool for
this", added for the senior-engineer order of the same day), drawn 2026-11-28 for the operator's order of that day ("Assistant panel:
rebuild it as a continuous chat, like Claude's chat or Claude Code, not a form") and signed off
under the Phase 7 mode (docs/STANDING_APPROVAL_LOG.md, "Board assistant-chat"). Its yellow
notes are notes for the builder.

Shots: the panel open on Devices, light theme, at 1366x768 and 1920x1080, a planted conversation
of two exchanges (one answered from the manual; one with two source chips, a hand-off, two reads
with the first opened, two calls), before (HEAD's templates) and after, taken by a scratch shot
test in a throwaway worktree (scripts/nmas-control), no AI call. The working state, Stop, the
past conversations' list and the resize are compared by tests/test_assistant_chat_browser.py in
Firefox and by the templates, not by shots.
Templates compared: templates/v2/_assistant_panel.html, templates/v2/_assistant_place.html, templates/v2/_assistant_act.html, templates/v2/_assistant_turn.html, templates/v2/_assistant_answer.html
Compared again 2026-11-28 (the independent review): Stop's hover now says no call is made after it and a round of reads already running finishes first (it said nothing more is asked or read), and a question refused at once draws its turn with no id (it drew `asst-turn-refused`, repeated). No region moves; every verdict stands. Templates sha256 before: `82d364d46d25574b395e0c2188f9a9b65e5acca0a056a85fc93abd3249c23de0`.
Compared again 2026-11-28 (the full suite on 2c738990b): the working indicator is one status line, the earlier steps on its hover (Working (C), now a deviation below); Stop, New conversation and Reopen carry the configure gate; the act slot no longer asks for the AI control itself (the panel's is passed in); the head's Looking at is asked from `data-place-url`, which carries the page's network. Templates sha256 before: `e2cb87a31c622c0a0d5eb60f4bbe44b52e6d836ba3465cf60e2ad8784af56c61`.
Compared again 2026-11-28 (the model selector, the operator: "add a model selector to the chat"): the box's row gains the model selector between the keys line and Send, as the board's A and B now draw it ("Haiku 5.5 · default", the others "N× the cost"); after-shots at 1366 and 1920 taken by the same scratch shot test (the selector beside Send, the newest answer's model chosen). At the panel's default width of 440 px the keys line wraps onto two lines beside it (a deviation below). Templates sha256 before: `c5c87dcdcf868c64b04885873828eadd9843368f7e6bb76952c0f769c13e40f0`.
Compared again 2026-11-28 (the pre-gate on the selector): each option's rates on its hover are drawn by the `usd` filter (tests/test_money.py); the words and the region are unchanged. Templates sha256 before: `f40052b0c04c6c4541203e6c9659a1675e6e61c3f3f895ee48ae654e940fa77f`.
Compared again 2026-11-28 (the assistant as a senior network engineer, artboards F and G): an answer proposing a plan loads the plan's own card in place at once (`hx-trigger="load"` on the preview, the card's id the answer's call), where it offered Preview the plan…; an answer saying Mercury has no tool draws its box; About the assistant's "It changes nothing…" line now says a change is a plan you approve by its hash, or a hand-off, and that Mercury says what it has no tool for. Compared by the templates' diff and tests/test_assistant_engineer.py (the answer drawn through the chat's job, its card loaded), not by shots. Regions A to E stand; F and G are added below. Built beside the model selector (both of 2026-11-28, brought together on main); the templates as both left them. Templates sha256 before: `e66ab0ce212c9120cb434e83c152930fcc10625d54f7ce8eaae4c54067f891c8`.
Templates sha256: `3ac65e19c351e9367d95e30f9e39e021a648854b1aa9f0022b98305e79524d83`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Head, first row (A) | the AI mark and Assistant; New conversation; Past conversations; About the assistant (ⓘ); close | the same, in that order; New conversation a small text button, the other three icon buttons | **same** |
| Head, second row (A) | the Looking at chip ("Looking at: Devices · Default"), "Beta · advisory" at its right | the same; the chip's hover says what it reads; its "How does this work?" (ⓘ) beside it | **same** |
| Behind the ⓘ (A) | the beta notice in full, "It changes nothing…", masked and recorded, How does this work? | the same four, in a menu under the ⓘ | **same** |
| Empty conversation (A) | "Ask how to do something in Mercury, or about what is on this screen." and the calls line, centred | the same words, centred | **same** |
| The box (A, B) | one line, "Ask a question…" / "Ask a follow-up…", "Enter sends · Shift+Enter, a new line", Send with its (i) | the same; it grows to eight lines with the text | **same** |
| The model (A, B) | a select beside Send, "Haiku 5.5 · default", rates on hover, the keys line on one line | the select beside Send with the three models; at 440 px the keys line wraps onto two lines | **deviation** (log: Board assistant-chat: the model selector) |
| The person's message (B) | a bubble at the right, "on r2 (device) · Lab" under it | the same bubble, and the time it was asked after the place ("on r2 (device) · Lab · 18:02", the viewer's zone); the page's address on its hover | **deviation** (log: Board assistant-chat built: its five deviations) |
| The answer's words (B) | markdown: a paragraph, an ordered list, bold, inline code | the same, drawn by Mercury with every character escaped | **same** |
| Sources (B) | chips, each its words and Open | the same | **same** |
| Hand-off (B) | a box inside the answer: "To make this change:", Change it in words…, "nothing is drafted until you press there" | the box, its words and button; "nothing is drafted…" on the button's hover, not beside it | **deviation** (log: Board assistant-chat built: its five deviations) |
| Reads (B) | "▸ Ran 2 reads", opened: each read its line, one opened to "show version on r2 · Open the read on History › Reads" | "Ran 2 reads" closed; each read its line ("read:1, r2's version · read"), opened to its reason, its device and Open the read on History › Reads (or, for Mercury's own read, that nothing was sent to a device) | **deviation** (log: Board assistant-chat built: its five deviations) |
| Quiet line (B) | "Haiku 5.5 · $0.0031 · 9 s · History (2 calls)" | "Haiku 5.5 · $0.0031 · 9 s · Call 1 in History · Call 2 in History" (one call: "History") | **deviation** (log: Board assistant-chat built: its five deviations) |
| Was this right? (B) | under the answer | the same (`_ai_feedback.html`) | **same** |
| Working (C) | the question, then the dots and the step ("Running the 2 reads it asked for"), the earlier steps faint under it; New conversation dimmed | the question, the dots and the step it is on as one status line; the earlier steps on its hover, not drawn under it; New conversation dimmed | **deviation** (log: Board assistant-chat built: a sixth deviation, one status line) |
| Stop (C) | Stop in Send's place, "Stop closes the model's answer and runs nothing more" beside it | Stop in Send's place; what it does on its hover; the line beside the box stays "Enter sends · Shift+Enter, a new line" (no narration beside a control) | **deviation** (log: Board assistant-chat built: its five deviations) |
| AI off (D) | the box and Send greyed, the reason under them with Open Settings | the same (`ai.input_attrs`, `ai.attrs`, `ai.reason`) | **same** |
| Past conversations (E) | a menu: each first question, when, how many, Reopen; "Reopening keeps the current conversation here in its place." | the same; how many as "3 exchanges"; the newest 30 of N said when there are more | **same** |
| A change's words (F) | what the plan will do, read first, "it runs only once you approve it"; never that it is done | the same; an answer whose words say a change was made is refused by Mercury's check, never drawn | **same** |
| A change's plan (F) | the plan engine's card inside the answer, at once: its title on the network, its words, each step's own preview, the hash line, What its hash binds, the reason, Approve named for the work | the same card (`_plan_card.html`), loaded in place on the answer's arrival, "Proposed for your approval: <title>, on <network>. Previewing each step…" while it loads; its id the answer's call, its Approve its own card's | **same** |
| No tool (G) | a box inside the answer: "Mercury has no tool for this: <wanted>." bold, the why after it; recorded for review on its hover | the same (`data-no-tool`), the words masked | **same** |
| The edge (A) | a grip on the panel's left edge, drag or arrow keys | the same (`[data-asst-resize]`, a separator with its value) | **same** |
