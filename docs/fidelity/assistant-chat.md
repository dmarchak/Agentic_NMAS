# Fidelity: the assistant as a continuous chat (2026-11-28)

Board: `docs/boards/assistant-chat.html` (artboards A empty, B a conversation, C working, D AI off,
E past conversations), drawn 2026-11-28 for the operator's order of that day ("Assistant panel:
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
Templates sha256: `c5c87dcdcf868c64b04885873828eadd9843368f7e6bb76952c0f769c13e40f0`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Head, first row (A) | the AI mark and Assistant; New conversation; Past conversations; About the assistant (ⓘ); close | the same, in that order; New conversation a small text button, the other three icon buttons | **same** |
| Head, second row (A) | the Looking at chip ("Looking at: Devices · Default"), "Beta · advisory" at its right | the same; the chip's hover says what it reads; its "How does this work?" (ⓘ) beside it | **same** |
| Behind the ⓘ (A) | the beta notice in full, "It changes nothing…", masked and recorded, How does this work? | the same four, in a menu under the ⓘ | **same** |
| Empty conversation (A) | "Ask how to do something in Mercury, or about what is on this screen." and the calls line, centred | the same words, centred | **same** |
| The box (A, B) | one line, "Ask a question…" / "Ask a follow-up…", "Enter sends · Shift+Enter, a new line", Send with its (i) | the same; it grows to eight lines with the text | **same** |
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
| The edge (A) | a grip on the panel's left edge, drag or arrow keys | the same (`[data-asst-resize]`, a separator with its value) | **same** |
