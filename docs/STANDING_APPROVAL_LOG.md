# Standing approval log

Every decision the agent made for the operator under the Phase 7 operating mode (the operator's
decision, 2026-10-09; the section `scripts/host-steps/phase7-mode-on.sh` adds to CLAUDE.md): a board the agent drew and counts as
signed off, or the option it chose on a decision that is otherwise the operator's. One line each,
newest last: the date (UTC), what was decided, the option taken and why in a clause, and where
it is recorded (a commit, a register row, a board).

The operator's four stops are never decided here: a secret value, anything outside the lab, a new
third-party package licence, and deleting or rotating backups or snapshots.

| Date (UTC) | Decision | Taken, and why | Where |
|---|---|---|---|
| 2026-10-10 | Phase 4 section 7 (receipts on the records database), a draft | Approved as drafted, with the as-built changes below: it was the next item in the operator's order | docs/NSOT_PHASE4_RECORDS_POSTGRES.md section 7 |
| 2026-10-10 | The receipts migration: a CLI (`nmas-records-migrate`, the draft) or a v2 operation | A v2 operation, preview and bound confirm, on the Records database card: no terminal steps, one home per action, recorded as the person | modules/records_migrate.py |
| 2026-10-10 | Board: Record stores, below the Records database card (a store per row: where, last check, Move… / Move back…; the preview's counts per network; the result's steps) | Drawn and counted as signed off: it is a card on a signed-off tab (F2), with the same preview and result shapes as F4's | templates/v2/_records_stores.html |
| 2026-10-10 | A check that fails after the switch | Switch back at once, exporting what was written in between, rather than leave the store switched and flagged | records_migrate.move |
| 2026-10-10 | The count check's cadence and wakes | Every 300 s, woken by a deploy (`deploy_job`, `device_state`) and a move (`settings`): receipts change at deploy rate | modules/readers/records_check.py |
