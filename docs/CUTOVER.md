# Cutover: every legacy route and action, and where it goes

The checklist for retiring today's interface (`/`, `/device/<ip>`), and the list of screens
the manual must cover (the operator, 2026-10-02). **Every route outside the redesign
(`/v2/...`, `/update/...`) is named by a row below, and every path a row names is a route:
`tests/test_cutover_rows.py` holds both against `app.url_map`, and each family's count**
(C630, 2026-10-10: this page had said 265 routes and named four removed ones). Each row has one
status:

- **BUILT**: a v2 screen does this today (named). **Walked** says it was run on the host; a
  BUILT row without it has not been.
- **PARTLY BUILT**: a v2 screen does part of it; the row names the part still missing.
- **PLANNED**: a v2 home is decided, with the plan item that builds it
  ([NSOT_STAGE7_PLAN.md](NSOT_STAGE7_PLAN.md) section 8, [NSOT_GUI_BRIEF.md](NSOT_GUI_BRIEF.md)).
- **REMOVE**: decided to go, with the item that removes it (7.8 is last, so nothing goes
  before its replacement is on screen).
- **STAYS**: no screen by design; a named non-GUI consumer calls it.
- **UNDECIDED**: no recorded decision. Each is a question for the operator.

A row moves when its status changes; the legacy pages retire when no row reads PLANNED,
PARTLY BUILT or UNDECIDED.

## The redesign's own routes

`/v2/` and every `/v2/...` route, and `/update/...`. Their screens: Needs attention, Devices,
the device page and its tabs, History, Monitoring (Dashboards, Coverage, the profile), Show
commands, Templates, Credentials, Settings (each network, Installation), Help, Update.
**To be removed from them:** `/v2/monitoring/heartbeat` (and its apply) and
`/v2/monitoring/ip-sla` (and its policy and commit), replaced by the monitoring templates
(the operator's mockup review, 2026-10-02; C322), once the templates design is signed off
and built.

## Legacy routes by family

| Family | Routes | Status | Home or reason |
|---|---|---|---|
| Today's pages | `/` (index), `/device/<ip>` | REMOVE, 7.8 | Replaced by `/v2/` and `/v2/device/<name>` (walked); they go when this table has no PLANNED or PARTLY BUILT row left. v2 links into them only through the labelled gaps in `tests/todays_page_links.py` |
| Needs attention data | `/attention`, `/jobs/health`, `/templatize/rolled-back` | BUILT, walked | Needs attention (`/v2/attention`) draws each (7.2); `/jobs/health` and `/templatize/rolled-back` have no page caller |
| Acknowledge a row | `/attention/acknowledge` | BUILT | v2's Needs attention posts to it (`_attention.html`) |
| Infrastructure | `/health`, `/health/operations`, `/static/<path:filename>`, `/favicon.ico` | STAYS | `/health`: the Update page and the root updater; `/health/operations`: `scripts/nmas-deploy`; the static files; browsers ask for the icon |
| Job wake-up, planned restarts, clab map | `/jobs/finished`, `/restarts/planned`, `/clab/sync_targets` | STAYS | `nmas-job-finished@` from each job's systemd unit; `scripts/nmas-planned-restart`; `scripts/nmas-clab-targets` |
| Deploy | `/deploy/plan`, `/deploy/apply` | PARTLY BUILT, 7.4 | One device: the device page's Deploy (walked, C428). Several ticked devices: boards A, B and K signed off, not built (gap `deploy_plan`) |
| Deploy receipts | `/deploy/receipts` | BUILT, walked | The device page's History tab; the receipts can move to the records database (Phase 4) |
| Capture, Save All | `/golden/capture/preview`, `/apply`, `/preview/<job>` | PARTLY BUILT | Device Actions › Capture (walked) and Devices › Save (C593). Missing: the reason for recording a structural shrink (C486, C310; gap `acknowledge`) |
| Restore, baselines | `/golden/restore/preview`, `/apply`, `/golden/restore_points/<host>`, `/golden/baselines` | PARTLY BUILT, History | Device Actions › Restore from… (walked) offers the baselines; History › Baselines is built. Missing: a network's Re-apply (gap `reapply`) |
| Golden versions | `/golden/history/<host>`, `/golden/version/<host>`, `/golden/diff/<host>` | PARTLY BUILT, History | The History tab and `/v2/history/commit/<sha>` (walked). Missing: revealing a version, which stays in the GUI (decided 2026-10-05: a person, recorded); no board yet |
| Git | `/git/status`, `/git/log`, `/git/commit/<sha>` | BUILT, walked | History › Commits: the log, its filters and each commit's masked change |
| Remote | `/remote/push`, `/remote/verify`, `/remote/status` | BUILT | History's header (Push now, Verify; no real run yet) and `/v2/history/remote` |
| Remote, auto-push | `/remote/auto-push` | BUILT (C631, 2026-10-10; not run on the host) | History › Remote set-up…: Turn on automatic pushing, offered after a successful push |
| Remote, connect and the rest | `/remote/verify-write`, `/preview`, `/acknowledge`, `/adopt` | BUILT (C631, 2026-10-10; not run on the host) | History › Remote set-up…: Connect, Run the write probe, What a first push publishes and its typed Acknowledge, each a verified person's (`routes/remote_v2.py`). They were to stay CLI-only through a command that never existed; a host command cannot carry the verified person they need |
| Renames | `/golden/renames`, `/golden/renames/sync` | REMOVE, 7.8 (decided 2026-10-05) | Refresh Hostnames is cut: C465 removed its NetBox write, and a device's hostname comes from its captures |
| Legacy golden store, migration | `/golden/legacy_store`, `/golden/migrate/plan`, `/golden/migrate/apply` | REMOVE, 7.8 | Its retirement condition (`legacy_only_goldens()` empty) has held on the host since 2026-09-28 |
| Persist, rotate, retire | `/persist/*` (2), `/rotate/*` (3), `/retire/*` (2) | BUILT, walked | The device page's Actions: Persist (C359), Rotate (C370), Retire (r5); the routes go with today's pages |
| Seed, revert, retry | `/templatize/seed/*` (2), `/templatize/revert/*` (2), `/templatize/retry/*` (2), `/templatize/rolled-back/retries` | BUILT | Device Actions; seed walked, revert and retry not yet run |
| Intent editing | `/templatize/committed/<host>`, `/templatize/committed/<host>/preview`, `/templatize/committed` | BUILT (board H's Document mode; not run on the host, C444) | The Intent tab's Edit (`/v2/device/<name>/intent/*`), one code path with today's routes (`modules/nsot/intent_edit.py`); Fields mode (board J) is not built |
| Bulk intent | `/templatize/bulk/*` (2) | PLANNED, 7.4 (board D signed off) | Devices selection; no v1 control calls it (`scripts/nmas-bulk-intent` calls the module) |
| Monitoring profile | `/templatize/profile`, `/templatize/profile/propose/*` (2) | BUILT, walked (C566) | `/v2/monitoring/profile` |
| Template coverage | `/templatize/report` | PLANNED, 7.6 | Templates; no board, no caller |
| Templates: list, approve, revoke | `/templates`, `/templates/approval/<path>`, `/templates/approve/<path>`, `/templates/revoke/<path>` | BUILT (boards A to C, `/v2/templates`; not run on the host) | Source of truth › Templates |
| Templates: edit and the rest | `/templates/*` (7) | PLANNED, 7.6 | The editor (file read and write), validate, preview, refresh-capture, bindings and seed status: the editor reuses the intent editor H (decided 2026-10-05), no board drawn. Preview and refresh-capture read the backup store, so they go before it (C632) |
| Onboard | `/onboard/*` (9) | PLANNED, 7.4 (boards E, L, M and F signed off 2026-10-04, not built) | Devices › Onboard; the v2 pending page links to today's for the actions (gap `onboard`), and is itself not signed off |
| Adopt | (no route; `modules/nsot/adopt.py`) | PLANNED, 7.4 | Devices › Adopt |
| NetBox import and remove | `/netbox/safety/*` (8), `/netbox/status` | PLANNED, 7.6 (a board to draw, decided 2026-10-05) | Source of truth › NetBox: import and remove as preview, confirm and result; turning NetBox writes on is part of it (C619) |
| NetBox connection test | `/netbox/test_connection` | BUILT | Settings › Installation › Connections, the NetBox card's Test |
| NetBox queries | `/netbox/query/*` (6) | REMOVE, 7.8 | No page calls them; the device page's NetBox tab reads NetBox itself |
| Credential profiles | `/inventory/credentials/*` (3), `/inventory/dependents/<list>` | PLANNED, 7.6 | Source of truth › Credentials; no board, and no v1 control calls them |
| Inventory source | `/inventory/source/<list>`, `/inventory/refresh/<list>` | BUILT (2026-10-10; not run on the host) | Every network's Settings › Network tab, Inventory source: its own list or NetBox through filters, a preview reading NetBox once with the new filters (how many devices, which skipped and why), a confirm bound to it, recorded; Refresh now for a NetBox network |
| Inventory order | `/inventory/order/<list>`, `/reorder` | REMOVE, 7.8 | Drag-reorder removed for sortable columns (the operator, 2026-09-29) |
| Networks | `/device_lists`, `/device_lists/<name>`, `/select_device_list` | BUILT, P.8 (2026-10-10; not run on the host) | Choosing one: BUILT (board N, 2026-10-10; not run on the host): the top bar's Network picker, the choice each verified person's own (`routes/network_v2.py`), so `/select_device_list`'s one choice for everyone has no v2 equivalent by design. Create and delete: BUILT (2026-10-10; not run on the host): Settings' New network… and a network's Delete this network…, each previewed and recorded; a deleted network's folder is moved aside, never erased. Rename: never offered by today's pages (C639), not built |
| List data | `/list/golden_configs`, `/list/drift_status`, `/list/change_log` | REMOVE, 7.8 | Superseded by Devices, Needs attention and History |
| List variables, compliance policy | `/list/variables`, `/list/variables/*` (2), `/list/compliance_policy` | REMOVE, 7.8 | Superseded by intent, drift, group intent and the monitoring templates (the operator, 2026-10-02) |
| Refresh hostnames | `/refresh_hostnames` | REMOVE, 7.8 (cut 2026-10-05) | C465 removed its NetBox write; a device's hostname comes from its captures |
| Drift | `/drift/status`, `/drift/check`, `/drift/check/sync`, `/drift/settings` | BUILT, 7.7 (board F4, 2026-10-10) | Results are Needs attention rows; the schedule and Check now are Settings › Installation › Diagnostics |
| Break-glass export | `/breakglass/preview`, `/export` | `/breakglass/export` STAYS; `/breakglass/preview` REMOVE, 7.8 (board 7) | Credentials › The break-glass record posts to the one export (walked); today's modal goes at 7.8 |
| Identity and posture | `/identity/status`, `/identity/posture`, `/identity/posture/ratify` | BUILT, 7.7 (board F4) | Settings › Installation › Access and identity, with Record this decision; `/v2/who` |
| Settings | `/settings`, `/settings/integrations`, `/settings/integrations/*` (4) | PARTLY BUILT, P.8 and 7.7 | Each network's Settings (boards A to J) and every Installation tab (boards F to F4). Missing: turning NetBox writes on (C619) |
| TFTP setting | `/save_tftp_server` | REMOVE, 7.8 (C616) | Its only readers are the device file routes below, and it points at nothing on this installation |
| Pending restart | `/session/pending-restart` | REMOVE, 7.8 | No caller; the Update button restarts, gated on held devices (`/server/restart` was removed 2026-10-02) |
| App log | `/logs/server` | BUILT, 7.7 (board F4) | Settings › Installation › Diagnostics, the app's log |
| In-flight operations | `/operations/in_flight` | BUILT, 7.7 (board F4) | Settings › Installation › Diagnostics, In flight |
| Version | `/health/version` | BUILT | Help › About |
| Reachability | `/status/<ip>`, `/connection_status/<ip>` | REMOVE, 7.8 | The reachability reader (C92) is what v2 draws |
| Device regions | `/devices/regions` | REMOVE, 7.8 | `/v2/devices` replaces today's device list |
| Backups | `/device/<ip>/backup_config`, `/backup_history`, `/backup_stats`, `/compare_backups`, `/delete_backup/<f>`, `/download_backup/<f>` | REMOVE, 7.8, after today's template editor | Section 6a's prerequisite (no render reads a backup) does not hold yet: Templates' preview and refresh-capture read the backup store (C632) |
| Device files | `/device/<ip>/refresh_files`, `/upload`, `/download_file`, `/delete_file`, `/download` | REMOVE, 7.8 | No arbitrary file transfer (the operator, 2026-10-02): ZTP delivery in onboarding and image management (P.13) replace them. ZTP is served by Mercury's own responder, which none of these routes touches (C616, checked 2026-10-09); `tftp_root` and `tftp_server_ip` leave with them |
| Bulk read-only commands | `/bulk_execute`, `/bulk_status/<id>`, `/bulk_clear/<id>` | BUILT (C548; not yet walked on the host) | Show commands (`/v2/show-commands`): devices by name, role or network, commands from the allowlist, results grouped and compared |
| Bulk file actions | `/bulk_delete_file`, `/bulk_download_config`, `/bulk_tftp_upload`, `/bulk_tftp_download` | REMOVE, 7.8 | As device files |
| Reload | `/bulk_reload` | PLANNED, P.14 (a board to draw, decided 2026-10-05); the route REMOVE at 7.8 | A gated device-page operation (unsaved changes, drift, the boot credential and image, no holder, the blast radius), its planned-restart window declared before it acts. The terminal is gone, so until it is built nothing on v2 restarts a device |
| Ask the device | `/run_command/<ip>` | BUILT (C547; not yet walked on the host) | The device page's Ask tab (allowlisted) |
| Quick actions | `/add_quick_action`, `/delete_quick_action` | REMOVE, 7.8 | The terminal's companions; the terminal was removed 2026-10-05 (R39) |
| Configure | `/configure/*` (5) | REMOVE, 7.8 (decided 2026-10-05) | The intent editor and deploy replace them (they already send nothing) |
| Legacy collectors | `/monitoring/config`, `/monitoring/interfaces`, `/monitoring/netflow`, `/monitoring/netflow/clear`, `/monitoring/snmp/poll`, `/monitoring/snmp/traps`, `/monitoring/snmp/traps/clear` | REMOVE, 7.8 | The in-app collector and SNMP Quick Poll are removed (the mockup review, 2026-09-29) |
| Monitoring stack panel | `/monitoring/stack/`, `/monitoring/stack/<name>` | REMOVE, 7.8 | The status bar and integration health replace it |
| Topology | `/topology/*` (9), `/topology_data` | REMOVE, 7.8 | Neighbours carries discovery per device (C126); the fleet map is P.11's Topology item |
| Topology service | `/topology/service/status`, `/svg` | PLANNED, P.11 (boards A to C signed off 2026-10-04, not built) | The Topology sidebar item |
| AI agent | `/ai/*` (26) | REMOVE, 7.8 (decided 2026-10-05) | Stage 8 redesigns the agent as an on-call responder; the chat, agent, approvals, Ansible and usage screens go with today's pages |

## Legacy actions that are not routes

| Action | Status | Home or reason |
|---|---|---|
| The terminal (socket events) | **REMOVED 2026-10-05** (R39, brought forward from 7.8 on the operator's decision, after the console drill proved the emergency path: docs/CONSOLE_DRILL.md) | The Device page's allowlisted Ask tab is the one way to ask a device. Kept: the `break_glass` gate kind and its two settings, until they retire |
| Today's Git tab, Remote card, Baselines panel | BUILT | History: Commits, the remote's sentence, Baselines |
| The AI chat panel (every page) | REMOVE, 7.8 (decided 2026-10-05) | Stage 8 redesigns it |
| Bulk restore at HEAD (`bulkRestoreGoldenConfig`) | REMOVE, 7.8 (cut 2026-10-05) | A device's Restore from… and History's baselines remain |
| Settings modal | PARTLY BUILT | Settings per network and every Installation tab are built; turning NetBox writes on is not (C619) |

## Decided 2026-10-02

The three undecided rows were answered by the operator: the generic file actions go,
replaced by purpose-built operations (ZTP delivery in onboarding; P.13's image
library, transfer and upgrade); reload stays as a gated device-page operation
(P.14); the list variables and the compliance policy go. No row is UNDECIDED.

## Decided 2026-10-05 (the operator, on the transition status)

1. The Stage 8 rows (AI chat, the agent, approvals, usage) do not block cutover: REMOVE at
   7.8; Stage 8 redesigns them.
2. 7.9 Configure and the Ansible tab do not block: REMOVE at 7.8; the intent editor and deploy
   replace them.
3. Networks live in Settings (P.8), board I's pattern: create, rename and delete a network
   there. The top-bar picker (N) only switches.
4. The template editor reuses the intent editor H.
5. NetBox import and remove get a v2 board (Source of truth › NetBox): preview, confirm,
   result; bulk onboarding builds on it.
6. One Installation/Diagnostics board: the drift schedule and "Check now", the server log, the
   in-flight panel, the posture. (Built as board F4, 2026-10-10.)
7. Bulk restore is cut. Bulk read-only commands were cut on 2026-10-05 and come back as a v2
   screen (the operator, 2026-10-06, C548): fleet-wide reads from the same allowlist, the
   evidence engine of Stage 8's agent. (Built as Show commands, 2026-10-08.)
8. Revealing a golden version stays in the GUI (a person, recorded); the remote's connect,
   acknowledge and write probe were set-up acts with no screen. (Revised 2026-10-10, C631,
   under the Phase 7 mode: the command named for them never existed and could not carry a
   verified person, so they are History's Remote set-up card.)
9. Reload (P.14) gets a board, its planned-restart declaration built in.
10. Refresh Hostnames is cut (C465 removed its write; hostnames come from captures).

"Authorise a divergence", once PLANNED for 7.6, is moot: the freshness gate and its routes
were removed with Oxidized (ba28d2b, 2026-10-08). The status of every v1 capability, counted,
was [TRANSITION_STATUS.md](TRANSITION_STATUS.md) (last measured 2026-10-07; this table is the
current one).

## Where v2 still sends a person to today's pages (the operator, 2026-10-08, C569)

No v2 page or result links to a v1 route unless the link says "today's" and names its gap
(`data-todays-page`). The gaps are listed in `tests/todays_page_links.py`, a list that only
shrinks, its ceiling equal to its count (C629); `tests/test_v2_links_stay_on_v2.py` holds every
v2 template and every rendered v2 page to it. On 2026-10-10 there were seven: Capture's
acknowledgement reason (C486), Plan a deploy for several ticked devices, History's Re-apply,
onboarding (Add, Verify, Abandon, the bootstrap config, onboard again), and the sidebar's Logs,
DHCP and NetBox (the Logs and DHCP links name screens today's page does not have: C633). A v2
request that fails says "Couldn't load" in place and never redirects to today's index; a
designed v2 error page is a further gap, pending a mockup.

## What the manual must cover

Every BUILT and PLANNED home above is a screen, and each needs its manual section before it
is done (the operator, 2026-10-02): Needs attention, Devices, the device page and each of its
tabs, History and its tabs, Monitoring (Dashboards, Coverage), Settings > Monitoring
templates, Templates, NetBox, Credentials, Settings, Help, Update. The operations among them
each need a "How it works" section (docs/manual/how-it-works/).
