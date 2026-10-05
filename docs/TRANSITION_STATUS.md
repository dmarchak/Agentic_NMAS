# Transition status: every v1 capability, and where it stands on v2

One row per capability of today's interface (`templates/index.html`, `templates/device.html`,
`templates/partials/*`), with its state on v2. Surveyed read-only from the code and
[CUTOVER.md](CUTOVER.md) on 2026-10-05, then recounted the same day after the operator's ten
decisions (CUTOVER, "Decided 2026-10-05"). **A row moves the commit its state changes**, and the
counts below are recounted with it.

**States:**
1. **Proven:** built on v2 and run for real on the host (the evidence named).
2. **Built:** on v2, no real run yet.
3. **Signed off:** designed and approved (the board named), not built.
4. **Awaiting sign-off:** designed, not approved.
5. **No design:** no v2 board yet (its decided home named where there is one).
6. **Retired:** removed, or decided to go at 7.8 (REMOVE), or kept off the GUI (CLI only).

v1's own size is pinned by `tests/test_no_new_v1_capability.py` (202 controls, 194 handlers,
451 functions, 324 fields on 2026-10-05): it may fall and never rise.

## Counts (84 rows, 2026-10-05)

| State | Count |
|---|---|
| 1 Proven | **16** |
| 2 Built, not yet run | **7** |
| 3 Signed off, not built | **20** |
| 4 Awaiting sign-off | **0** |
| 5 No design | **14** (11 with a decided home, 3 without) |
| 6 Retired | **27** (4 removed, the server restart among them; 22 REMOVE at 7.8; 1 CLI only) |

Counted from the rows below (the first survey had 86; three Installation rows, NetBox's connection, Proxmox and the server, are one row here). v1 retires when no row reads 2, 3, 4 or 5 and the REMOVE rows are gone (7.8).

## The rows

| v1 capability | Where in v1 | State | v2 home or board | Evidence |
|---|---|---|---|---|
| **Is anything wrong** | | | | |
| Needs attention panel | partials/needs_attention.html | 1 | `/v2/` | NSOT_STAGE7_PLAN §11: 7.2 done, the landing page since 2026-09-28 |
| Approved vs Oxidized (freshness) | partials/freshness_signal.html | 1 | Needs attention rows | read on v2 2026-10-05 (C489) |
| Drift results | index.html, drift panel | 1 | Needs attention rows | read on v2 2026-10-05 (C487) |
| Drift schedule and Check now | index.html, drift panel | 5 | Settings, the Installation/Diagnostics board (decided 2026-10-05, to draw) | |
| Integrations stack panel | partials/monitoring_stack.html | 6 REMOVE | the status bar | CUTOVER |
| **Devices and networks** | | | | |
| Device list | partials/device_table.html | 1 | `/v2/devices` | 7.0's acceptance 5 passed 2026-10-05 (THROWAWAY_SESSION, STOP 3) |
| Switch the active list | index.html, `/select_device_list` | 3 | the top-bar network picker, board N (2026-10-05) | |
| Create a network | index.html, create-list modal | 3 | Settings, board I (2026-10-05); rename and delete join it | |
| Delete a network | index.html | 5 | Settings, board I's pattern (decided 2026-10-05, to draw) | |
| Inventory source, filters, refresh | partials/inventory_source.html | 5 | Settings, the network's page (decided 2026-10-05, to draw) | |
| Inventory drag-reorder | `/inventory/order` | 6 REMOVE | sortable columns | CUTOVER |
| Refresh Hostnames | partials/device_toolbar.html | 6 REMOVE | cut 2026-10-05: hostnames come from captures | C465 |
| Save All, capture the uncaptured | partials/device_toolbar.html | 3 | board C (2026-10-04) | |
| Batch deploy | partials/deploy_wizard.html | 3 | boards A, B, K (2026-10-04) | |
| Bulk intent (CLI today) | (no v1 control) | 3 | board D (2026-10-04) | |
| Bulk read-only commands | device_table.html, `/bulk_execute` | 6 REMOVE | cut 2026-10-05 (fleet-wide reads revisited with Stage 8 or History › Query) | |
| Bulk restore at HEAD | device_table.html | 6 REMOVE | cut 2026-10-05 | |
| Reload devices | partials/device_toolbar.html, `/bulk_reload` | 5 | P.14, a gated device operation with its planned restart built in (decided 2026-10-05, to draw) | |
| Bulk file transfer, config downloads | device_table.html | 6 REMOVE | P.13 and ZTP delivery | CUTOVER |
| Regions, list data and variables, NetBox queries | `/devices/regions`, `/list/*`, `/netbox/query/*` | 6 REMOVE | superseded | CUTOVER |
| **Onboarding** | | | | |
| Onboard (static, DHCP, ZTP) | partials/onboard_wizard.html | 3 | boards E, L, M (2026-10-04) | |
| Pending: Verify, Abandon | partials/onboard_pending.html | 3 | board F (2026-10-04) | Verify ran on today's page 2026-10-05 |
| Adopt (no route yet) | `modules/nsot/adopt.py` | 3 | board G (2026-10-04) | |
| Add Device, Discover Subnet | (removed) | 6 removed | onboarding | C102 |
| **The device page** | | | | |
| Device page and its facts | templates/device.html | 1 | `/v2/device/<name>` | C342 |
| Changes (receipts) | partials/device_changes.html | 1 | the History tab (board D) | C369, C359 |
| Golden history (versions, diffs) | partials/golden_repo.html | 1 | the History tab | C369 |
| Reveal a golden version | golden_repo timeline | 5 | History, in the GUI (decided 2026-10-05: a person, recorded) | |
| Capture | device.html | 1 | Actions › Capture | THROWAWAY Part 7 (774ffeb) |
| Persist | device.html | 1 | Actions › Persist | C359 |
| Rotate | device.html | 1 | Actions › Rotate | C370 |
| Deploy, one device | device page, deploy plan | 1 | Actions › Plan a deploy… | C428 |
| Mode B removal | deploy wizard | 2 | Actions › Remove lines (Mode B)… | waits for THROWAWAY Part 5 |
| Restore from… | device.html | 1 | Actions › Restore from… | THROWAWAY Part 7 sent a line |
| Revert intent | device.html | 2 | Actions › Revert intent… | waits for THROWAWAY Part 6 |
| Retry a rolled-back change | device.html | 2 | Actions › Retry… | waits for THROWAWAY Part 6 |
| Seed intent | device.html | 1 | Actions › Seed intent… | THROWAWAY 3.3 (bdaa5eb) |
| Retire | device.html | 1 | Actions › Retire… | r5, 2026-10-04 |
| Intent editor | partials/intent_editor.html | 3 | board H (2026-10-04), with acknowledging an unmodelled line | C444, C481 |
| Template render preview | template_editor.html | 5 | Templates, through the intent editor H (decided 2026-10-05) | |
| Custom command | device.html, Utilities | 3 | the Ask the device tab (drawn disabled) | signed_off_screens `tab:ask` |
| Quick actions | device.html | 6 REMOVE | | CUTOVER |
| File Management | device.html | 6 REMOVE | P.13 and ZTP | CUTOVER (the ZTP TFTP path checked first) |
| Backups | device.html | 6 REMOVE | captures | CUTOVER (after section 6a's prerequisite) |
| Terminal | (removed) | 6 removed | the console and break-glass | R39, 2026-10-05 |
| Reachability routes | `/status`, `/connection_status` | 6 REMOVE | the reachability reader | CUTOVER |
| **Topology** | | | | |
| Built-in discovery | index.html, topology pane | 6 REMOVE | the Neighbours tab | C38 |
| Topology service panel | partials/topology_service.html | 3 | P.11 boards A to C (2026-10-04) | |
| **History** | | | | |
| Change History tab | index.html | 6 REMOVE | v2 History | CUTOVER |
| Git tab and commit view | index.html | 1 | the History timeline | C369 |
| Remote: Push now, Verify | golden_repo | 2 | History's header | no real run yet |
| Remote: auto-push | golden_repo | 3 | History (brief 3.4, 2026-10-02) | |
| Remote: connect, acknowledge, write probe, preview | golden_repo | 6 CLI only | decided 2026-10-05 | |
| Baselines list | golden_repo.html | 2 | History › Baselines | no real run yet |
| Baseline re-apply | golden_repo | 3 | History, Re-apply… (brief 3.4) | |
| Legacy store migration | golden_repo | 6 REMOVE | | CUTOVER |
| **Source of truth** | | | | |
| Template library and editor | partials/template_editor.html | 5 | Templates, reusing the intent editor H (decided 2026-10-05) | |
| Template approve | template_editor | 3 | Templates boards A to C (2026-10-05) | C481 |
| Template revoke (CLI today) | | 3 | Templates boards A to C (2026-10-05) | |
| Bindings, coverage, seed status | (CLI today) | 5 | Templates, boards to draw (no home decided beyond the page) | |
| Monitoring profile propose | static/js/nmas_profile.js | 3 | monitoring templates, board B | |
| NetBox import, write safety | index.html, netbox_safety_modal.html | 5 | Source of truth › NetBox (decided 2026-10-05, to draw) | |
| NetBox remove and its record | partials/netbox_removals.html | 5 | Source of truth › NetBox (decided 2026-10-05, to draw) | |
| Break-glass export | nmas_breakglass.js | 1 | Credentials (board 7) | THROWAWAY Part 4 |
| Credential profiles (CLI today) | | 5 | Credentials (brief 3.5; no board) | |
| Authorise a divergence (CLI today) | | 5 | Source of truth (7.6; no board) | |
| **The v1 Monitoring tab** | | | | |
| Collectors, SNMP poll, traps, NetFlow | index.html | 6 REMOVE | | CUTOVER |
| **Configure and AI** | | | | |
| Configure forms | index.html | 6 REMOVE | cut 2026-10-05: the intent editor and deploy replace them | |
| Ansible | index.html | 6 REMOVE | decided 2026-10-05; Stage 8 | |
| AI chat, Ask AI, reports | base.html, device.html | 6 REMOVE | decided 2026-10-05; Stage 8 redesigns | |
| Agent | index.html | 6 REMOVE | decided 2026-10-05; Stage 8 | |
| Approvals | index.html | 6 REMOVE | decided 2026-10-05; Stage 8 (folds into Needs attention) | |
| AI usage and spend | settings modal | 6 REMOVE | decided 2026-10-05; Stage 8 | |
| **Settings and the tool** | | | | |
| AI and workflow switches | settings modal | 3 | Settings, Installation (board F, 2026-10-05) | |
| TFTP server address | settings modal, device.html | 2 | Settings › the network's Network tab | built 2026-10-05, no real run |
| Integrations per network | settings_integrations | 2 | `/v2/settings/network/<list>` | built 2026-10-05, no real run |
| Edit a value, Default's warning | settings modal | 3 | boards B and G (2026-10-05) | |
| NetBox connection, Proxmox, server | settings_integrations | 3 | Installation (board F) | |
| Security posture and ratify | partials/security_posture.html | 3 | Installation (board F) and the Installation/Diagnostics board | |
| Twelve form-only settings | settings_integrations | 6 REMOVE | retired (P.8 decision 3) | |
| Server log | index.html | 5 | the Installation/Diagnostics board (decided 2026-10-05, to draw) | |
| In-flight operations panel | `/operations/in_flight` | 5 | the Installation/Diagnostics board (decided 2026-10-05, to draw) | |
| Server restart, pending restart | | 6 removed | the Update button | `/server/restart` removed 2026-10-02; pending restart REMOVE at 7.8 |
| Jenkins, CCIE knowledge base | | 6 removed | | P.4; 4f69e1c |

## Boards to draw (after the intent editor and Templates A to C are built)

1. Source of truth › NetBox: import and remove, preview, confirm, result.
2. Settings, the Installation/Diagnostics board: the drift schedule and Check now, the server
   log, the in-flight panel, the posture.
3. Reload (P.14), its planned-restart declaration built in.
4. Settings, a network's create, rename and delete, under board I's pattern.
Then: Templates' editor (through H), bindings and coverage; Credentials' profiles; authorise a
divergence.

## Known facts that are not rows

- Four v2 sidebar items open today's page: Logs, DHCP, Templates and NetBox
  (`templates/v2/base.html`). Templates and NetBox move with 7.6's boards; Logs and DHCP follow
  P.8 as OBSERVE pages.
