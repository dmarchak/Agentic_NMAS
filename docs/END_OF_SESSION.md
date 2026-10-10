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
Devices (board G, f09ac7c, finished as the board ends it in 83fbb5a), bulk intent (board D),
Templates › Coverage (8250677), Credentials › Profiles. No v2 page sends a person to today's
pages any more. CUTOVER's rows still PLANNED: the topology service, P.11, in steps: step 1, its reader, is built and walked on the
host (629c7a8, C648 3f21f83 and 9571439; the host runs 9571439: physical 11 links as cabled,
OSPF 16, OSPFv3 7, BGP 4, r6 the one island); r5 drawn as one outside peer and islands
expected by declaration (30f8c1b); step 2, the page, first built from the
boards' written description (b79e335), did not match the signed-off boards (C649, the operator,
2026-10-10); REBUILT to TopoDesktop and TopoPhone (d720434): every link's ports and a chip per
protocol with its area or peer AS and state, line styles against intent, icons in measured
bands, Mercury's measured place, Needs attention on the map, the phone's tabs and sheet;
compared region by region in docs/fidelity/topology.md, 11 deviations logged. The host walk
found Mercury drawn attached through containerlab's shared address and as a path between
devices (C653, fixed 57883db); walked again on 57883db: s3 Mercury's only way into seven
devices, r6 apart on purpose (the operator marked it) and reached directly. C650's fidelity
step is in place (tests/test_board_fidelity.py; 32 signed-off screens still to compare, the
list only shrinks). Then shared recorded positions (step 3), then time travel
and the wall (whose kiosk identity is a Cloudflare Access service token: stop 2, the operator's); C635 closed (the checker reads receipts
in the records database); Logs (C652, the operator 2026-10-10): the sidebar's Logs opens
the queryable logs, History › Query board C's "Syslog by device" (e9d4fbe, e112246 and the
Newest fix after them), counted per day by the `logs-summary` reader; compared with AskLogs in
docs/fidelity/logs.md; walked on the host (its first reads: 71 s, then 7.7 s after the first-line
search was fixed, the history filling 7 days a read; the lab's Logs retention set to 730 days,
from 90, through the settings write path, as NSOT_STAGE7_PLAN 14.15 said). Next: DHCP (C529)
with its fidelity record (a draft Kea reader from 2026-10-10 was set aside uncommitted when the
Topology fidelity work came first; the read-only page is built from boards DhcpNetwork,
DhcpSubnets, DhcpReserve and DhcpExclusions, Kea measured through its control sockets), boards L and
M, C641,
7.5 to 7.7, the 7.8 removals and the walk. Since 2026-10-10 each change is deployed and walked
on the host as it lands (Phase 7 mode); the walk at the end runs everything again.

**Next, in order** (the operator's, 2026-10-09): receipts (Phase 4, Mercury's records in
PostgreSQL); C630 (CUTOVER.md re-measured); C631 (the remote's set-up); the six cutover
blockers in dependency order (networks, NetBox import and writes on, onboarding, capture's
acknowledgement reason, the template editor, Reload); the nice-to-haves; 7.5 to 7.7; the 7.8
removals; then a walk of everything on the host.

**Waiting on the operator:** nothing. Stop 3 (NetworkX) was answered YES on 2026-10-10: pinned
at 3.6.1 (f829171), recorded in docs/THIRD_PARTY.json, and carried through Phase 4 section 8.4 on
the host the same day: the venv `f21256e61a35` built and proved beside the running one (15 of
15), the deploy swapped the link, `.previous` names `9d27674e53bf`, both kept, `/health` 200.
The overrides then came off in their own lock change (f9dc11e), carried the same way: the host
now runs f9dc11e on `mercury-venv-53a6aabdd2c2` (previous `f21256e61a35`), `pip check` clean,
the updater's root copies re-installed from this release. The three uv
overrides come off in the NEXT lock change, on their own, with `pip check` clean after it. Under
the mode only the four stops wait on the operator: a secret value, anything outside the lab, a new third-party
package licence, and deleting or rotating backups or snapshots.

**To resume:** read CLAUDE.md, then this file, then docs/OPEN_FINDINGS.md's Count, and
docs/STANDING_APPROVAL_LOG.md for what was decided under the mode.
