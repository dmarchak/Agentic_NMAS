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
