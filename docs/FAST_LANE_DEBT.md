# Checks skipped by the operator's decision of 2026-11-15

The operator, 2026-11-15, temporary until the operator says otherwise: "skip tests and checks to
get the feature working ... No test runs, no new tests, no red-green proofs, no boards/fidelity/
manual updates, no independent review. Write and deploy the code. Keep only: the commit hooks as
they run ... and the fast-lane deploy's smoke check with its automatic rollback ... Keep a debt
list: every change shipped this way, with the tests, boards and reviews it skipped. It's all
cleared in one full pass (tests, fidelity, full gate, CI green) before the Lab 10 recording and
before the demo."

Each change shipped this way is one row. **Cleared** only by the full pass: its tests run and
green (the written ones below are in the working tree, unshipped), its fidelity and manual
updated, a full gate and CI green on the final sha.

The tests, boards and fidelity records written for these changes before the decision are in the
working tree and in the saved combined patch; the full pass ships them.

| Shipped | Change | Skipped | Written but not shipped |
|---|---|---|---|
| item 4 | An alert instance with no device counts only at its device's own address (C3811); a standing incident closes on its plan run's verified device check, and an alert still firing 300 s after is its own Needs attention row (C3812); a close on a verified fix reads Fixed, its title "fixed and verified" | test runs, red-green, review of the close path, the manual (how-it-works/heal.md), register rows | tests/test_heal_verified_fix.py, tests/test_heal_act.py's corrected helper, docs/manual/how-it-works/heal.md |
| items 2, 5, 6, 7 and R5 | The card pushed after a press (`#inc-fixit` a live part, C3808); "AI plan approved by <person>, passed at <instant>" (C3809); severity follows impact in every open state (C3813); each save's result drawn from the store, Not now (C3810); R5 on Needs attention, Incidents and the incident page: the batch card holding its problems, the strip's labels, the live step (`ai_step`), the plan card, Fixed / Save / Not now, one Details per card (C3814) | test runs, red-green, the budget tests in CI, board fidelity records and shots, the manual pages, register rows; shipped together because 2, 5 and 7 share their templates with R5 | tests/r5_budget.py, tests/test_r5_budgets.py, tests/test_r5_incident.py, tests/test_fixit_section_v2.py, tests/test_saved_plans_v2.py, tests/test_incident_bluf.py and the other corrected tests, tests/v2_context.py, docs/boards/r5-simple-by-default.html, docs/fidelity/{landing,incidents,incident}.md, the manual pages, docs/STANDING_APPROVAL_LOG.md's R5 rows |
| Save is the approval | "Save" saves a verified fix's self-heal script as Automatic, promoted by the person saving it (the operator, 2026-11-15); Dry run a choice under Customize; the card's line "Mercury will handle this automatically when self-healing is on"; existing Dry-run scripts unchanged | test runs (tests/test_saved_plans_v2.py and tests/test_r5_incident.py assert Dry run by default: their premise changes), board R5's screens 5 and 5b, the manual, a register row | nothing |
| C3805 and the status-line rule | A save, a promote or self-healing switched on re-decides every open incident an Automatic script matches (`saved_plans.redecide`: in Auto the script fires through `fire`, guards asked, and verified closes the incident Fixed through `decide.end_standing`); otherwise the bottom line offers "Fix with saved script: <name>" (`fixit_v2.fix_with_script`, the runner as a job, bound to the preview's hash, no AI). The status line is the best current knowledge (`section._best_status`): a fix available, the AI's plan ready, the AI's latest real diagnosis, a failure only when nothing else; a press that never reached the AI never the headline; an AI answer a saved script overtakes labelled outdated | test runs (s2's exact record as the test: a diagnosis, a refused press, a matching script), review of the device path (a new route that runs a script), the route's manual section, a register row | nothing |
| deferred: item 1 | The runner measurement and the derived connect bound (C3741, C3762) | not shipped: the operator deferred it until after the demo walk | modules/nsot/port_connect.py, command_plan(_run).py, command_policy.py, waits.PORT_CONNECT, tests/test_port_connect.py, the fixtures |
