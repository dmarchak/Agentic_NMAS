# End of session: where Phase 7 stands

## OVERNIGHT RUN, 2026-10-11 (the operator's list, items 1 to 9): status

Kept current after every item so the run can resume. Started 06:34 UTC on 2502f5c (deployed:
fbdc686; 2502f5c is documentation only). Device rule tonight: read-only commands only, never on
s3, nothing 08:30 to 09:10 UTC.

| # | Item | State |
|---|---|---|
| 1 | C671: measure r1–s1, r2–s2 as a possible real fault | **done** 06:45: no routing fault, traffic both ways; LLDP alone fails (s1/s2 Gi0/2 receive no LLDP); CDP off on r1/r2, so no second witness tonight (enabling it is a config change, the operator's). Raw captures: `~/Documents/nmas-reports/2026-10-11-c671-captures.txt` on the laptop |
| 2 | C670: the layout's grid version, timed | **done**: 0.17 / 0.45 / 1.34 / 2.47 s at 150 / 300 / 600 / 900 devices (was 0.48 / 1.90 / 7.82 / 32.82); deploy and host check with the commit |
| 3 | C663 steps 2 and 3: the lab out of the product | in progress. **Step 2 built** (suite green, 9906 passed): Mercury's lab settings, `/clab/sync_targets`, the lab-startup check, reader and rows, job health's clab-sync rows, the rotation's boot-file stages (persistence is the device's save, read back), retire's startup step, the startup-applies checker; `netbox_excluded_vrfs` empty by default, ratified on the host first. **Committed 0f6d480, CI #623 green, deployed 07:51 UTC and checked:** the host's `netbox_excluded_vrfs` ratified before the deploy (origin file, 1 VRF; the step's one action run from the old release, as `claude-agent (host shell)`); `/v2/` 200, job health has no clab-sync row, `/clab/sync_targets` 404, Needs attention reads (one row: step 1's host step awaiting the Update page's confirm, on the walk list). **The sync proved unchanged:** a baseline-earned event written through the product's hook at 07:52:11 started it the same second; 9 devices at the same line counts as the 07:38 run (152/147/181/181/105/192/192/139/119), every file "unchanged", "Both labs already hold baseline/20261009T044804Z; nothing to update", and no exit notice. **Step 3a built** (suite green): the bootstrap's vrnetlab platform tables became the device's environment read from NetBox (`mgmt_only` interfaces, the config context's `environment_owned_lines`; a device with none has none), recorded with the bootstrap parameters; the import never clears `mgmt_only`; the lab's change records to `lab/intent-changes/`; product wording generic. **Committed e42fb8c, CI #624 green, deployed 08:15 UTC and checked:** `/v2/`, Devices, History, Settings and `/v2/onboard/new` answer 200; the environment reader asked the real NetBox for r1 (found, id 5: nothing management-only, no owned lines, the lab having set none). **Step 3b: committed 733b136, CI green, deployed and its host step run by the agent** (`c663-step3b-topology.sh`, 8 of 8 checks PASS: the unit rendered from the installed one, `nmas-topology.service` active and answering on 8088, the old unit and link gone); the app's own check reads done. **Item 3 stands at one entry on tests/test_lab_specifics.py** (`scripts/nmas-host`, blocked on the CLAUDE.md paste below), plus the spent one-shot host step, removed with it. Inventory 7 files / 28 lines before 3b: the topology renderer's name (3b, a host step) and `scripts/nmas-host` (needs the operator's CLAUDE.md paste). Question for the operator: onboarding refuses a name NetBox holds, so a new device's environment is always none |
| 4 | C665: roles and platforms from NetBox | **done** (1421a66, CI #627, deployed 08:56, Settings › Platforms and roles, Topology and Devices checked 200), but for the two role kinds NetBox refused (walk list). Was in progress: surveyed (the kind drives behaviour in 10 places, the hostname guess is display only, NetBox 4.6.9's Platform has no driver field); step 1 (the `mercury_kind` field's reader and migration) committed ff76a59, CI #626, deployed 08:38 and run on NetBox: the field created, the two role writes REFUSED by NetBox (403: the token may not change device roles; walk list). Step 2 built (the inventory reads NetBox's kinds; the role map and its card gone; no hostname guess; the import never overwrites a role; suite 9940 green). The host's only network is local, so no behaviour moves there |
| 5 | C667: History › Query, boards A to C | in progress: 5a built (the Query tab, board A's coverage and questions; Syslog by device at its board's home, the sidebar's Logs drawing the same page; boards A and C compared, records written). Next 5b, board B (the metrics answer), then saved views and Ask your own. **For the operator:** what should the sidebar's Logs be? Board C's "Open these lines on Logs" implies a live log view (a tail of the network's lines); no board draws one, so nothing was built |
| 6 | C662: RIP and RIPng read into Topology | to do |
| 7 | C529 DHCP step 2 (then 3, 4; 5 only with a fresh copy) | to do |
| 8 | The cutover blockers | to do |
| 9 | Nice-to-haves, CUTOVER 7.5 to 7.7 | to do |

Logged blockers and stops:
- **C663, the last entry on tests/test_lab_specifics.py** (`scripts/nmas-host`, the operator's
  access helper, with its `clab` host name): it moves to `lab/nmas-host` once CLAUDE.md names
  the new home, and CLAUDE.md is the operator's. Paste, replacing the three lines as they are:
  - line 69: `- **Read-only measurement of lab services is the agent's to run**, through `lab/nmas-host`,`
  - line 402: `` (2026-09-29). `lab/nmas-host` reads it and refuses, naming the file, when it is ``
  - line 413: `` `lab/nmas-host <nmas|clab|pve> -- <command>`.** For scp and rsync, ``
  Then the agent moves the file, its hooks' and the lab sync's references and its tests, in
  one commit. The one-shot host step `c663-step3b-topology.sh` is on the list too, until it
  is removed after it has run.

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
list only shrinks). The operator then found the map too busy (C654) and asked for it to be
arranged by people (C655); both were built (a597479, b8f3f0f) and, shown the after shots, the
operator sent Topology back to the approved board v34, Arrange out too (both WITHDRAWN, in the
register's Closed). The operator then pointed at the approved boards themselves: the build had
never matched them (13 regions logged as the agent's "deviations"). C658 drew the page to them
(840329e: the board's two-word chips per link, its toolbar, legend, times and phone list),
compared again at 1440, 1280 and 390 (7 regions still differ, each with its reason in
docs/fidelity/topology.md), deployed and walked on the host's own read 2026-10-11. Open from the
walk: C659, fixed and walked 2026-10-11 (222054b: no link drawn across a device, name or tag
it does not join, checked in a real browser). Wall view and Arrange stay later steps. DHCP
(C529) step 1 built 2026-10-11: the DHCP reader and the read-only page to board A, the sidebar's
DHCP under SOURCE OF TRUTH, docs/fidelity/dhcp.md; deployed and walked on the host the same
day (4f9a699: both families read, the capture's counts); C660 (the reader's reservations outside a
subnet, 81e3334, walked). The operator's queue since, in order: C661 (Topology arranged by
people, panned and zoomed, no bands: 335c0ee, walked), C664 (Settings › Installation's layout),
C666 (the drift check's Last column) and C668 (Topology's card closes, smaller): done together;
then C663 (the lab out of the product), C665 (roles and
platforms from NetBox), C667 (History › Query to boards A to C), C662 (RIP and RIPng on
Topology), then C529 step 2; next after those, step 2 (board B, with the one host step
that moves Kea's subnets into Mercury's files). Then time travel
and the wall (whose kiosk identity is a Cloudflare Access service token: stop 2, the operator's); C635 closed (the checker reads receipts
in the records database); Logs (C652, the operator 2026-10-10): the sidebar's Logs opens
the queryable logs, History › Query board C's "Syslog by device" (e9d4fbe, e112246 and the
Newest fix after them), counted per day by the `logs-summary` reader; compared with AskLogs in
docs/fidelity/logs.md; walked on the host (its first reads: 71 s, then 7.7 s after the first-line
search was fixed, the history filling 7 days a read; the lab's Logs retention set to 730 days,
from 90, through the settings write path, as NSOT_STAGE7_PLAN 14.15 said). Next: DHCP (C529)
steps 2 and 3 (boards B, C and D; step 1, the read-only page, is built), boards L and M, C641,
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
