# Fidelity: A plan of operations (the plan engine's page and card)

The plan engine's page (`templates/v2/plan.html`) and its card (`templates/v2/_plan_card.html`),
compared region by region with the plan card's board, drafted for the review sitting and
self-signed under the Phase 7 operating mode (the build's board draft, `board_plan_card.md`;
logged in docs/STANDING_APPROVAL_LOG.md, C3648). Compared 2026-11-14 by the templates and the
pages tests/test_plan_engine.py and tests/v2_context.py's `_plans` draw (each state: refused,
the preview, running, a job that ended with no record, the result), not by shots: the board is
words, not an artboard. The page is the frame around the same card the toolbar assistant's
panel draws in place.
Templates compared: templates/v2/plan.html, templates/v2/_plan_card.html

A verdict is **same**, **deviation** (its line in docs/STANDING_APPROVAL_LOG.md, named) or
**later** (a later step of the plan).

| Region | Board | Built | Verdict |
|---|---|---|---|
| Page head | (the board's card is in the panel; the page is the frame around it) | "A plan of operations" | **same** |
| Help | How does this work? beside the action | How this works in the head, and How does this work? beside Approve | **same** |
| Page lead | (none on the board) | "On <network>: each step through its own operation, in order, approved once." | **same** |
| The preview's lead | "<title>." and the plan's words: N steps, in order, stopping at the first that does not pass, nothing retried | the same, "<title>, on <network>." | **same** |
| The steps | an ordered list, one line a step: its words, its own preview's title and change, what it does not do muted | the same (the plan's program, not progress: `plan-program`) | **same** |
| The hash line | faint: "The plan is bound to <hash>: if any step's own preview moves before you approve, nothing runs." | the same | **same** |
| The reason | at least three words, recorded with your name | the same | **same** |
| Approve | primary, busy on itself ("Starting…"), named for the work | "Approve the plan on <network>: <title>", busy on itself | **same** |
| Refused | danger notice "This plan is not offered: <why>", no button | the same, the words masked | **same** |
| Not run | danger "Not run: <why>" above the preview, the reason kept | the same, the words masked | **same** |
| Running | "Running the plan: <title>", redrawing itself on the run's announcement | the same, on the network, and once the run has kept its record its steps on THE stepper (`run_stepper`): the running step's time counting, the rest waiting | **deviation**, THE stepper, tests/test_one_stepper.py (log: The plan card's steps on THE stepper) |
| A job with no record | (not on the board) | danger "The plan's job ended without a record: <why>", the redraw stopped | **same** (the review's addition: a run is never drawn running for ever) |
| The outcome | first, in its level: muted done, danger stopped | the same, and warning for a plan that passed and leaves its own approval (Add a device by ZTP), never green | **same** |
| The steps' ends | each step done, failed or did not run, with its own words | on THE stepper (`run_stepper`, from `plan_engine.run_card`): one row, the plan, each step's short label (its whole words on hover) done, failed or not reached (struck through), with its own words; Add a device by ZTP's Create amber as needing a person, never green; a step that broke while running "failed: whether it landed is unknown" | **deviation**, THE stepper (log: The plan card's steps on THE stepper) |
| The record line | who approved, when, the reason, the hash | the same | **same** |

Compared again 2026-11-14 when the run's steps moved onto THE stepper (CI #1720's
tests/test_one_stepper.py): the Running and The steps' ends regions.

Templates sha256: `75f51171da732c58aaa3b4208983f6b15bf2220f7f693b5c87e02d50dde9beaa`
