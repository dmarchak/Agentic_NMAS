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
| 2026-10-10 | C631: write `scripts/nmas-remote`, or give the remote's set-up a v2 home | A v2 home: the acts need a verified person (`publish_remote`), which a host command cannot carry; revises the operator's decision 8 of 2026-10-05 | docs/CUTOVER.md; routes/remote_v2.py |
| 2026-10-10 | Board: History › Remote set-up (opened from the header; no remote: Connect with each field's shape; connected: the record's facts, Run the write probe, What a first push publishes with the gated fingerprints and the typed Acknowledge, Turn on automatic pushing after a push) | Drawn and counted as signed off: a card on History (signed off), the same preview and result shapes as the Settings cards | templates/v2/_remote_setup.html |
| 2026-10-10 | Board N's "remembered per verified person": where the choice takes effect | In `listref.active()` on v2 requests only: the address's `?list=`, then the person's choice, then the installation's list; background jobs and today's pages keep the installation's list, so no job follows a person | modules/nsot/listref.py; modules/network_choice.py |
| 2026-10-10 | The picker's contents and where a choice goes | Only networks that exist (the base marked); a device's page goes to that network's Devices; any address that is not a v2 path goes to `/v2/` | routes/network_v2.py |
| 2026-10-10 | The count check's cadence and wakes | Every 300 s, woken by a deploy (`deploy_job`, `device_state`) and a move (`settings`): receipts change at deploy rate | modules/readers/records_check.py |
