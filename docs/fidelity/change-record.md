# Fidelity: a change record drafted in the deploy preview (2026-10-29)

Board: `ChangeRecordDraft.dc.html` (CR, 1440; the mockups canvas "NMAS v2 mockups", page
"PHASE8_PLAN 16.11 items 1 and 3", version 174), drawn 2026-10-28 and signed off under the
Phase 7 mode (docs/STANDING_APPROVAL_LOG.md, "Board CR"). Its grey notes are notes for the
builder; its page is r3 with a three-line program, the built page r2 with the deploy tests' lab.

Shots: `tests/test_board_shots.py::test_change_record` (2026-10-29 ~09:0x UTC; the board at 1440
and 390, the page at 1440, 1280 and 390), on tests/test_ai_change_record.py's world (r2's real
capture: `lldp run` and a dangerous `shutdown` on GigabitEthernet3 to send, the reason typed;
the provider's planted answer): `change-record-offered` (the card as Plan a deploy… opens it),
`change-record` (Draft a change record pressed in the page, the htmx request carrying the card's
form), `change-record-stale` (the residue line then ticked for removal, so the card is planned
again with another program). The states the shots do not reach (hosted AI off, each refusal)
are compared by the template and tests/test_ai_change_record.py, and the AI control's states by
`ai_controls_check.check_screen`; the draft is reached by tests/v2_context.py's `_change_record`.
Templates compared: templates/v2/_change_record.html, templates/v2/_deploy.html
Templates sha256: `052c3c83b90fcb6632fae9efdb21d43e6af59ccc23bf9e023bbffcf791cec650`

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step, named).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Where it is drawn | the deploy preview's part "Change record", between Checks and the confirm | the same part, after Checks and before the foot (outside the card's form, the draft's call carried by it with `form="deploy-form"`) | **same** |
| Offered (1) | the AI mark, "Draft a change record", the (i), and the line "One recorded AI call as you, from this preview's program (masked) and checks; sends nothing to r3, and Deploy below is unchanged by it." | the mark (the AI controls' one hover: the task, its pinned model and its cap), the button, the (i), and "One recorded AI call as you, from this preview's shape and checks: no configuration value leaves Mercury. It sends nothing to r2, and Deploy below is unchanged by it." | **deviation** (log: Board CR built: the model is sent the program's shape, never the program) |
| Drafting | busy on itself, "Drafting…" | the same (`op-busy`) | **same** |
| The draft's head | "DRAFT by AI", "Change record: r3, deploy committed intent"; trigger person (who), the model and the call's cost, "this call in History" | the same, and "Advisory (beta)" beside the chip | **deviation** (log: Board CR built: the draft is labelled Advisory (beta) beside DRAFT by AI) |
| Summary (AI) | the model's sentence | the model's words, marked AI | **same** |
| Scope (Mercury) | 1 device, its platform, the interfaces, the intent file and commit | 1 device, its platform, the interfaces, the intent commit, the lines removed (Mode B); the network on hover | **deviation** (log: Board CR built: every fact the draft carries is drawn) |
| Risk (Mercury, AI) | the level chip, "Mercury's rule: …" naming the line needing a reason, removals, protocols; the model's reading | the same chip and rule (its counts and the line, "1 interface shut" when one is), the model's reading under it | **same** |
| Implementation (Mercury) | program hash, the line count, merge-only, "the lines copied from the program, never from the model", the stated reason | the same, the program's lines in a block as the preview draws them, each stated reason | **same** |
| Verification (Mercury) | FULL or QUICK and what is watched | the scope and why, its management families, each derived effect, each verify check with when it reads | **deviation** (log: Board CR built: every fact the draft carries is drawn) |
| Rollback plan (Mercury) | "On a failed Verify, Mercury undoes what landed…", the rollback's lines, the manual back-out through the golden | the same: the lines from `deploy.rollback_commands` over the program and the captured configuration, masked; the golden's commit now | **same** |
| Window and approver | "[your change window] · [your approver]: Mercury does not know these" | the same words | **same** |
| Status | "A draft for program …, not reviewed by anyone. It is not the change", Copy as text, Download (.md), AI Draft again | the same, and "What left Mercury: the program's shape in keywords, N section(s)…" (the shape on hover); Was this right? under the draft | **deviation** (log: Board CR built: every fact the draft carries is drawn) |
| Stale (3) | the notice naming both hashes, "Its Implementation and Rollback plan no longer match", Draft again; "a reason typed, a removal ticked" move it | the notice and Draft again as drawn, the old draft kept muted below; a ticked removal marks it at once (shot `change-record-stale`); a typed reason at the card's next re-plan | **deviation** (log: Board CR built: a stale draft stays drawn, muted, under its notice; a typed reason marks it stale only at the next re-plan) |
| Hosted AI cannot answer (4) | the control disabled, "Not available now: hosted AI is off for this installation." | the AI controls' one state, each kind (tests/test_ai_change_record.py through `check_screen`); the preview's reason box and Deploy drawn as ever | **same** |
| Refused by Mercury's check (5) | "Couldn't draft: the answer named no shutdown on GigabitEthernet3, which the program does not touch." The call is in History | "Couldn't draft: the answer named GigabitEthernet1, which the program does not touch. The call is in History."; another device and a quoted line likewise; an interface or device the preview's checks name is allowed | **deviation** (log: Board CR built: the words may name what the preview's own checks name) |
| The foot | "Bound to program …: if r3 or its intent moves before you confirm, nothing is sent. The change record is not part of what you confirm." Deploy | the same sentence added to the card's note; Deploy bound to the same hash with or without a draft (tests/test_ai_change_record.py) | **same** |
| After the confirm: the receipt | the receipt names the draft's call drawn for the confirmed program's hash | not built: the receipt names no draft | **later** (PHASE8_PLAN 16.11 item 3's receipt link, a register row to open) |
| A batch's one record | "drawn only on the deploy preview of one device or a batch (one record for the batch…)" | the device page's deploy card only; the batch preview draws no control | **later** (PHASE8_PLAN 16.11 item 3 on the batch preview, a register row to open) |
| Phone | the parts and the draft's sections stack, the buttons wrap | the same (CSS at 900 px; shot `change-record-page-390`) | **same** |
