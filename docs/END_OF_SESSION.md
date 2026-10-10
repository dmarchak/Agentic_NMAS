# End of session: where Phase 7 stands

**Status, 2026-10-10 (UTC).** The Phase 7 operating mode is ON: the operator ran
`scripts/host-steps/phase7-mode-on.sh` (about 02:23 UTC), and CLAUDE.md carries its section.
Done: receipts on the records database (d79ba34, not yet moved on the host); C630 (CUTOVER.md
re-measured and held to the route map) and C636 (b2b49cb); C631, the remote's set-up on History
(3cbd74a); cutover blocker 1, networks: the picker (eda63ea), create and delete (b3cee34), the
inventory source (6e73ac6); blocker 2, NetBox import and remove with turning writes on (C619,
65f87c3); blocker 3, onboarding on v2 (Add device, and the pending page's Verify, bootstrap
config and Abandon, each bound to its preview, 5f0c36c); blocker 4, Capture's reason for a
shrink and What next by direction (C486, b883fb6); blocker 5, Templates' Edit… (7e6efea),
Bindings… and Seed the library… (2e89ffc); blocker 6, Reload (P.14's plain form, its window
declared first, 4cf33e0). All six cutover blockers are built. Nice-to-haves done: batch deploy
(d8651d0), Re-apply (ec1f11b), C633 with C642 (a42d8df), the golden reveal (74b50a3), Adopt on
Devices (board G). No v2 page sends a person to today's pages any more. CUTOVER's rows still
PLANNED: bulk intent, template coverage, credential profiles, the topology service; then DHCP (C529), boards L and M, C635, C641,
7.5 to 7.7, the 7.8 removals and the walk. Nothing deployed since the mode began: the walk at
the end deploys and runs each.

**Next, in order** (the operator's, 2026-10-09): receipts (Phase 4, Mercury's records in
PostgreSQL); C630 (CUTOVER.md re-measured); C631 (the remote's set-up); the six cutover
blockers in dependency order (networks, NetBox import and writes on, onboarding, capture's
acknowledgement reason, the template editor, Reload); the nice-to-haves; 7.5 to 7.7; the 7.8
removals; then a walk of everything on the host.

**Waiting on the operator:** nothing. Under the mode only the four stops wait on the operator:
a secret value, anything outside the lab, a new third-party package licence, and deleting or
rotating backups or snapshots.

**To resume:** read CLAUDE.md, then this file, then docs/OPEN_FINDINGS.md's Count, and
docs/STANDING_APPROVAL_LOG.md for what was decided under the mode.
