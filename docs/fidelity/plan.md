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
| Page head | (the board's card is in the panel; the page is the frame around it) | the plan's title ("Describe the link"; "A plan of operations" only when neither its record nor its preview names one), the browser tab the same, since 93120b2f | **deviation** (log: A plan's own page is titled by its plan and names its devices) |
| Help | How does this work? beside the action | How this works in the head, and How does this work? beside Approve | **same** |
| Page lead | (none on the board) | "On <network>: each step through its own operation, in order, approved once."; once its steps name devices, "On edge1, edge2, network Default: …" | **deviation** (log: A plan's own page is titled by its plan and names its devices) |
| The preview's lead | "<title>." and the plan's words: N steps, in order, stopping at the first that does not pass, nothing retried | the same, "<title>, on <network>." | **same** |
| The steps | an ordered list, one line a step: its words, its own preview's title and change, what it does not do muted | the same (the plan's program, not progress: `plan-program`) | **same** |
| The hash line | faint: "The plan is bound to <hash>: if any step's own preview moves before you approve, nothing runs." | the same | **same** |
| The reason | at least three words, recorded with your name | the same | **same** |
| Approve | primary, busy on itself ("Starting…"), named for the work | "Approve the plan on <network>: <title>", busy on itself | **same** |
| Refused | danger notice "This plan is not offered: <why>", no button | the same, the words masked | **same** |
| Not run | danger "Not run: <why>" above the preview, the reason kept | the same, the words masked | **same** |
| Running | "Running the plan: <title>", redrawing itself on the run's announcement | "Running the plan: <title>, on <its devices>." (since 93120b2f no "This answer updates…"), redrawn on the run's and the device's progress, and once the run has kept its steps the incident card's stepper (`_inc_step.html`, `fixit.progress.plan_lines`; the operator's decision 7, 2026-11-18: "`_inc_step.html` is THE stepper" for plan runs): each step numbered, done ticked with its seconds, the running one live, the rest waiting | **deviation**, THE stepper, tests/test_one_stepper.py (log: The plan card's steps on THE stepper), and for the stepper it is drawn on, "A plan's run on the incident card's stepper" |
| A job with no record | (not on the board) | danger "The plan's job ended without a record: <why>", the redraw stopped | **same** (the review's addition: a run is never drawn running for ever) |
| The outcome | first, in its level: muted done, danger stopped | the same, and warning for a plan that passed and leaves its own approval (Add a device by ZTP), never green | **same** |
| The steps' ends | each step done, failed or did not run, with its own words | on the incident card's stepper (`_inc_step.html`, since 93120b2f, where it was `run_stepper`): one plain line a step, "✓ Set edge1 Gi1's description: step 1 of 2" done, "… step 2 of 2 not run" muted for a step after the stop, a failed step in its level with its own words (shot `debt-plan-result`) | **deviation**, THE stepper (log: The plan card's steps on THE stepper), and for the stepper it is drawn on, "A plan's run on the incident card's stepper" |
| What each step does (93120b2f) | not drawn | collapsed under the steps while running and in the result: each step's words and its device, and the lines its own run sent (masked) as a code block, else its parameters | **deviation** (log: A plan's own page is titled by its plan and names its devices) |
| The record line | who approved, when, the reason, the hash | the same | **same** |

Compared again 2026-11-14 when the run's steps moved onto THE stepper (CI #1720's
tests/test_one_stepper.py): the Running and The steps' ends regions.

Compared again 2026-11-14 (C3725, "everything the hash binds is shown in the preview"): one
region added under the hash line, collapsed, **What its hash binds** (the network, the plan,
each parameter, each step's operation and parameters, what its preview found, its own hash and
the plan's), drawn from the same hash's arguments (`plan_engine.bound_rows`); no other region
moves. Compared by the template diff and the card tests/test_plan_binds_drawn.py and
tests/v2_context.py's `_plans` draw, not by new shots. Templates sha256 before:
`75f51171da732c58aaa3b4208983f6b15bf2220f7f693b5c87e02d50dde9beaa`.

| Region | Board | Built | Verdict |
|---|---|---|---|
| What its hash binds (C3725) | (not on the board: the board draws the hash line alone) | collapsed under the hash line, one row a bound value, keys by their words, before Approve | **deviation** (log: Plan previews: what the hash binds) |

Compared again 2026-11-18 (the skip-mode debt, docs/FAST_LANE_DEBT.md; 93120b2f, "a plan's run is drawn on its incident's card, plain and numbered", and the operator's decision 7 of 2026-11-18): first shots of this page (the debt pass's `debt-plan-preview` and `debt-plan-result` at 1280 and 390, on the heal's lab with tests/v2_context.py's `_plans` preview of two steps planted and a run stopped at step 2 kept as its record), read region by region against this record's verdicts and the board's words. Moved: the page head and lead (the plan's title and its devices), Running and The steps' ends (the incident card's stepper, `_inc_step.html`, where they were on `run_stepper`), and one region added, What each step does; the preview's regions, Refused, Not run, A job with no record, The outcome and The record line stand. The board is words (`board_plan_card.md`), not an artboard, so there is no board shot. In progress reopens a run that is an incident's on its incident's card, not here (`plan_engine.run_page`). Logged (docs/STANDING_APPROVAL_LOG.md, "A plan's own page is titled by its plan and names its devices" and "A plan's run on the incident card's stepper"). Templates sha256 before: `3aab0145aed845b7a87f7c843ac13dd0fc79663749eebfce10463be4ec72af1a`.

Templates sha256: `d63bddda8507cfe12625a33cfcf12557d3ceae7ba507df48bd3b1ff4f05ca0ff`
