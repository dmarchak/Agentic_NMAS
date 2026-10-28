# Fidelity: Was this right? on every AI answer, and Answers said wrong (2026-10-28)

Board: `AiFeedback.dc.html` (FB, 1440; the mockups canvas "NMAS v2 mockups", page "PHASE8_PLAN
16.11 items 1 and 3", version 174), drawn 2026-10-28 and signed off under the Phase 7 mode
(docs/STANDING_APPROVAL_LOG.md, "Board FB"). Its grey notes are notes for the builder.

Shots: `tests/test_board_shots.py::test_ai_feedback` (2026-10-28 ~20:5x UTC; `ai-feedback` at
1440, 1280 and 390 beside the board at each, and `ai-feedback-open` at 1440 and 390, the newest
row opened), on tests/test_ai_feedback.py's world: the person's No through the control, another
person's Yes and a second No planted. The shots draw the review card. The control under each
answer is not shot (its five places are other screens' cards, each needing its answer planted):
it is compared by its template and tests/test_ai_feedback.py (Yes, No, the refusals, a service's
disabled buttons, the store unreadable, drawn under an Explain answer and never under a refused
one) and reached by tests/v2_context.py's `_ai_feedback`.
Templates compared: templates/v2/_ai_feedback.html, templates/v2/_ai_feedback_review.html, templates/v2/_ai_feedback_row.html, templates/v2/_ai_feedback_detail.html
Templates sha256: `e7c43a1cc1c4b4ea9fe36f3b8878d6bc57e7ebeb6da0b707ab596c0b197433ee`
(2026-10-28 ~21:4x UTC: each `<details>` given its `data-keep` key, so a live redraw keeps it
open (C472's rule, refused in the gate); nothing drawn changed, so no region was shot again.
Before: `a0ae8fe7abdffc9d1535aa780ec7e62b4f5320d9eb46fdc3351fdeb8735365ce`.)

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Where it is drawn | under Explain's answer, Ask in words' "Filled from your words" (both builders), an intent change in words' draft, and the SDN classification's AI box; none under a refused answer | the same five places, after each answer's History link or its "What left the host" line; none under a refused answer (tests/test_ai_feedback.py holds the four templates and the registry) | **same** |
| Asked (a) | "Was this right?", Yes, No…, (i); Yes's hover names the call and that nothing else changes | the same words and hover; the (i) after Yes | **deviation** (log: Board FB built: Was this right?'s control, three differences) |
| Yes pressed (b) | Yes reads "Recording…", busy on itself; No… disabled | Yes busy on itself ("Recording…"); No… stays pressable | **deviation** (log: Board FB built: Was this right?'s control, three differences) |
| Yes recorded (c) | the chip "you said right", the time, its record on hover | the same | **same** |
| The No form (d) | four kinds of wrong as radios, a sentence of at most 300 characters, Record as wrong, the one-answer note | the same, the first kind ticked, the sentence required; (i) after Record as wrong | **same** |
| No recorded (e) | "you said wrong", the kind and the words, the time, "a candidate case, to review in Settings › AI" | the same, the link to Settings › Installation › AI's card | **same** |
| Already answered (f) | the recorded state in place of the buttons; a stale press refused naming the first answer | the same; the refusal names the time as recorded | **deviation** (log: Board FB built: Was this right?'s control, three differences) |
| Not a verified person (g) | both buttons disabled, the reason beside them | the same | **same** |
| Store unreadable (h), call gone (i) | "Couldn't record: …", the buttons kept; "Not recorded: call … is not in the record of AI calls" | the same words | **same** |
| The card's head and lead | "Answers said wrong", How does this work?, the lead naming the reviewer, stricter only, no held-out set | the same, on Settings › Installation › AI below Background features | **same** |
| The summary and filter | counts by status, the status chips with counts, Every feature, the search, Show | the same | **same** |
| The rows | collapsed: feature, person, when, what was wrong, status chip; newest first; past 50, Older… | the same; an opened row holds the card's live redraw | **same** |
| An opened row | the call (id, feature, model, prompt, who asked, History link), what was asked (sha256, subject), the answer as kept (folded, masked, its size and sha256), what was wrong, others on this call | the same, and a Status field | **deviation** (log: Board FB built: an opened review row names its status) |
| Accept into a case draft… | the draft (no person in it), "expect" left for a maintainer, Accept bound to its hash | the same; Accept off with its reason while the call cannot be read (n) | **same** |
| Dismiss… | a reason, recorded with the name, Dismiss | the same, a few words at least | **same** |
| Accepted (j) | the chip, who, when, the draft's hash, the draft, Copy the draft, the feature's drafts as JSON, the maintainer's note | the same | **same** |
| Dismissed (k), empty (l), unreadable (m), settled first (o) | who, when, why; "No answer has been said wrong."; "Couldn't read …"; refused naming who settled it | the same | **same** |
| Phone | the row's summary and the opened row's fields stack, the filter wraps | the same (CSS at 900 px) | **same** |
