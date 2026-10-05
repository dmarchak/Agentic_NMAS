# Cutover: every legacy route and action, and where it goes

The checklist for retiring today's interface (`/`, `/device/<ip>`), and the list of screens
the manual must cover (the operator, 2026-10-02). Measured from `app.url_map` on
2026-10-02: **265 routes**, of which **43 are the redesign's** (`/v2/...`, `/update/...`)
or are read by it. Every other route is listed below, by family, with one status:

- **BUILT**: a v2 screen does this today (named).
- **PLANNED**: a v2 home is decided, with the plan item that builds it
  ([NSOT_STAGE7_PLAN.md](NSOT_STAGE7_PLAN.md) section 8, [NSOT_GUI_BRIEF.md](NSOT_GUI_BRIEF.md)).
- **REMOVE**: decided to go, with the item that removes it (7.8 is last, so nothing goes
  before its replacement is on screen).
- **STAYS**: no screen by design; a named non-GUI consumer calls it.
- **UNDECIDED**: no recorded decision. Each is a question for the operator.

A row moves when its status changes; the legacy pages retire when no row reads PLANNED or
UNDECIDED.

## The redesign's own routes (43)

`/v2/` and every `/v2/...` route, `/update/...`, `/health`. Their screens: Needs attention,
Devices, the device page (Overview, Intent read-only, History, Monitoring, Logs, NetBox,
Neighbours), Monitoring (Dashboards, Coverage, the batch Apply), Help > About, Update.
**To be removed from them:** `/v2/monitoring/heartbeat` (and its apply) and
`/v2/monitoring/ip-sla` (and its policy and commit), replaced by the monitoring templates
(the operator's mockup review, 2026-10-02; C322), once the templates design is signed off
and built.

## Legacy routes by family

| Family | Routes | Status | Home or reason |
|---|---|---|---|
| Today's pages | `/` (index), `/device/<ip>` | REMOVE, 7.8 | Replaced by `/v2/` and `/v2/device/<name>`; they go when this table has no PLANNED row left |
| Needs attention data | `/attention`, `/jobs/health`, `/templatize/rolled-back`, `/freshness/report` | BUILT | Needs attention draws each (7.2) |
| Job wake-up | `/jobs/finished` | STAYS | `scripts/nmas-job-finished`, from each job's systemd unit |
| Clab map, freshness gate | `/clab/sync_targets`, `/freshness/gate` | STAYS | The clab host's sync and `nmas-oxidized-freshness` |
| Deploy | `/deploy/plan`, `/deploy/apply` | PLANNED, 7.3 and 7.4 | A device's deploy (Device, "Plan a deploy…") and a batch (Devices selection); the v2 batch Apply already uses the same apply |
| Deploy receipts | `/deploy/receipts` | BUILT | The device page's History tab |
| Capture, Save All | `/golden/capture/preview`, `/apply`, `/preview/<job>` | PLANNED, 7.4 (one device BUILT, 7.3) | The device page's Actions > Capture is built (2026-10-02, the same job and apply, through `/v2/device/<name>/capture/*`); Devices "Save All" (7.4) is not, so the routes stay until it is |
| Restore, baselines | `/golden/restore/preview`, `/apply`, `/golden/restore_points/<host>`, `/golden/baselines` | PLANNED, History (signed off 2026-10-02) and 7.3 | History > Baselines (re-apply); Device Actions "Restore from…" |
| Golden versions | `/golden/history/<host>`, `/golden/version/<host>`, `/golden/diff/<host>` | PLANNED, History | History's commit rows and the device page's History tab; revealing a version stays in the GUI (decided 2026-10-05): a person, recorded |
| Git | `/git/status`, `/git/log`, `/git/commit/<sha>` | BUILT | History > Commits (2026-10-02): the log, its filters and each commit's masked change |
| Remote | `/remote/push`, `/remote/verify` | BUILT | History's header (2026-10-02): the remote's sentence, Push now and Verify |
| Remote, auto-push | `/remote/status`, `/auto-push` | PLANNED, History | History's remote section: the status sentence and auto-push (brief 3.4, signed off 2026-10-02) |
| Remote, connect and the rest | `/remote/verify-write`, `/preview`, `/acknowledge`, `/adopt` | STAYS, CLI only (decided 2026-10-05) | Connecting a remote, acknowledging publication and the write probe are set-up acts a person does once from the host (`scripts/nmas-remote`, curl); no screen |
| Renames | `/golden/renames`, `/golden/renames/sync` | REMOVE, 7.8 (decided 2026-10-05) | Refresh Hostnames is cut: C465 removed its NetBox write, and a device's hostname comes from its captures |
| Legacy golden store, migration | `/golden/legacy_store`, `/golden/migrate/plan`, `/golden/migrate/apply` | REMOVE, 7.8 | Its retirement condition (`legacy_only_goldens()` empty) has held on the host since 2026-09-28 (plan 7.8) |
| Persist, rotate, retire | `/persist/*`, `/rotate/*`, `/retire/*` | PLANNED, 7.3 (persist and rotate BUILT on v2, 2026-10-03) | The device page's Actions > Persist and Rotate run on v2 (the same plans, confirms and jobs, through `/v2/device/<name>/persist` and `/rotate`); retire still links to today's page, so the routes stay until it is built |
| Seed, revert, retry | `/templatize/seed/*`, `/templatize/revert/*`, `/templatize/retry/*`, `/templatize/rolled-back/retries` | PLANNED, 7.3 | Device Actions, and History for revert |
| Intent editing | `/templatize/committed/<host>` (read, edit, preview), `/templatize/committed` | BUILT, 7.3 (board H's Document mode, 2026-10-05; not yet run on the host; Fields mode, board J, not built) | The Intent tab's Edit (`/v2/device/<name>/intent/*`), with acknowledging an unmodelled line (C481); one code path with today's routes (`modules/nsot/intent_edit.py`); the one editor the template editor reuses |
| Bulk intent | `/templatize/bulk/preview`, `/apply` | PLANNED, 7.4 | Devices selection |
| Monitoring profile | `/templatize/profile`, `/templatize/profile/propose/*` | PLANNED, the monitoring templates (board B, signed off) | Monitoring templates |
| Template coverage | `/templatize/report` | PLANNED, 7.6 | Templates |
| Templates | `/templates/*` (11: list, file, approve, revoke, approval, bindings, preview, refresh-capture, seed_status, validate) | PARTLY BUILT, 7.6 (approve and revoke: boards A to C, signed off and built 2026-10-05, `/v2/templates`, not yet run on the host; the rest PLANNED) | Source of truth > Templates; the template EDITOR reuses the intent editor H (decided 2026-10-05), bindings and coverage on their own boards |
| Onboard | `/onboard/*` (9) | PLANNED, 7.4 | Devices > Onboard; the v2 pending page shows a pending device today, its actions on today's page |
| Adopt | (no route; `modules/nsot/adopt.py`) | PLANNED, 7.4 | Devices > Adopt |
| NetBox import and remove | `/netbox/safety/*` (7), `/netbox/status`, `/netbox/test_connection` | PLANNED, 7.6 (a board to draw, decided 2026-10-05) | Source of truth > NetBox: import and remove as preview, confirm and result; bulk onboarding builds on it |
| NetBox queries | `/netbox/query/*` (6) | REMOVE, 7.8 | No page calls them (measured 2026-10-02); the device page's NetBox tab reads NetBox itself |
| Credentials | `/inventory/credentials/*` (3), `/inventory/dependents/<list>` | PLANNED, 7.6 | Source of truth > Credentials |
| Inventory source | `/inventory/source/<list>` (GET, POST), `/inventory/refresh/<list>` | PLANNED, P.8 (decided 2026-10-05) | Settings, the network's page (board I's pattern): networks live in Settings |
| Inventory order | `/inventory/order/<list>`, `/reorder` | REMOVE, 7.8 | Drag-reorder removed for sortable columns (the operator, 2026-09-29) |
| Device lists | `/device_lists` (3), `/select_device_list` | PLANNED, P.8 (decided 2026-10-05) | Creating, renaming and deleting a network: Settings (P.8, board I's pattern, a board to draw). Choosing one: the top-bar network picker (board N, signed off 2026-10-05), which only switches |
| List data | `/list/golden_configs`, `/list/drift_status`, `/list/change_log` | REMOVE, 7.8 | Superseded by Devices, Needs attention and History |
| List variables, compliance policy | `/list/variables` (4), `/list/compliance_policy` (2) | REMOVE, 7.8 | Superseded by intent, drift, group intent and the monitoring templates (the operator, 2026-10-02); Stage 8 re-establishes how the agent works |
| Refresh hostnames | `/refresh_hostnames` | REMOVE, 7.8 (cut 2026-10-05) | Cut: C465 removed its NetBox write (a direct PATCH that bypassed the write switch, the authority and the record), and a device's hostname comes from its captures. The NetBox sync carries a rename (it matches by serial before name) |
| Drift | `/drift/status`, `/drift/check`, `/drift/check/sync`, `/drift/settings` (2) | PLANNED, 7.7 | Results are Needs attention rows (built); the schedule and "Check now" go to Settings, the one Installation/Diagnostics board (decided 2026-10-05, a board to draw) |
| Freshness authorisations | `/freshness/authorisations` | BUILT | History > Authorisations (2026-10-02) |
| Authorise a divergence | `/freshness/authorise` | PLANNED, 7.6 | Source of truth, beside the divergence it authorises |
| Break-glass export | `/breakglass/preview`, `/export` | STAYS (2026-10-03, board 7) | Credentials › The break-glass record draws the export and posts to `/breakglass/export`, the one export; `/breakglass/preview` and today's modal (`static/js/nmas_breakglass.js`'s `openBreakglassExport`) REMOVE at 7.8: every opener, today's included, already goes to Credentials |
| Identity and posture | `/identity/status`, `/identity/posture`, `/identity/posture/ratify` | PLANNED, 7.7 | Settings, the Installation/Diagnostics board (decided 2026-10-05, a board to draw) |
| Settings | `/settings` (2), `/settings/integrations/*` (5), `/save_tftp_server` | PLANNED, P.8 (step 7a BUILT 2026-10-05: a network's groups, their switches and the mode) | Settings per network (`/v2/settings/network/<list>`, boards A to J); Installation (F), one field's Save and Default's warning (G) still to build |
| Server and session | `/server/restart`, `/session/pending-restart` | `/server/restart` REMOVED 2026-10-02 (with `/ai/restart`, CONCURRENCY_AUDIT R5: each ended the process with no check of held devices); `/session/pending-restart` REMOVE, 7.8 | No caller (measured 2026-09-27); the Update button restarts, gated on held devices |
| App log | `/logs/server` | PLANNED, 7.7 | Settings, the Installation/Diagnostics board (decided 2026-10-05, a board to draw) |
| In-flight operations | `/operations/in_flight` | PLANNED, 7.7 | Settings, the Installation/Diagnostics board (decided 2026-10-05, a board to draw); today's pages draw it, v2's pending page only |
| Reachability | `/status/<ip>`, `/connection_status/<ip>` | REMOVE, 7.8 | The reachability reader (C92) is what v2 draws |
| Device regions | `/devices/regions` | REMOVE, 7.8 | Today's device list; `/v2/devices` replaces it |
| Backups | `/device/<ip>/backup_config`, `/backup_history`, `/backup_stats`, `/compare_backups`, `/delete_backup/<f>`, `/download_backup/<f>` | REMOVE, 7.8 | The backup store retires after section 6a's prerequisite (no render reads a backup) |
| Device files | `/device/<ip>/refresh_files`, `/upload`, `/download_file`, `/delete_file`, `/download` | REMOVE, 7.8 | No arbitrary file transfer (the operator, 2026-10-02). Replaced by purpose-built operations: ZTP delivery in onboarding, and software image management (NSOT_PLAN P.13). **Before removing**: check what ZTP serves today (the lab's configs folder holds a TFTP-written file) and keep that path working |
| Bulk operations | `/bulk_execute`, `/bulk_status/<id>`, `/bulk_clear/<id>` | REMOVE, 7.8 (cut 2026-10-05) | Bulk read-only commands are cut; fleet-wide read questions are revisited with Stage 8's agent or History › Query |
| Bulk file actions | `/bulk_delete_file`, `/bulk_download_config`, `/bulk_tftp_upload`, `/bulk_tftp_download` | REMOVE, 7.8 | As device files |
| Reload | `/bulk_reload` | REMOVE, 7.8; replaced by P.14 (a board to draw, decided 2026-10-05) | Reload becomes a gated device-page operation (NSOT_PLAN P.14: unsaved changes, drift, the boot credential and image, no holder, the blast radius), its planned-restart window declared before it acts, built in |
| Ask the device | `/run_command/<ip>` | PLANNED, 7.3 | The device page's "Ask the device" tab (allowlisted) |
| Quick actions | `/add_quick_action`, `/delete_quick_action` | REMOVE, 7.8 | The terminal's companions; the terminal was removed 2026-10-05 (R39) |
| Configure | `/configure/*` (6) | REMOVE, 7.8 (decided 2026-10-05) | The Configure forms and the Ansible tab do not block cutover: the intent editor and deploy replace them (they already send nothing) |
| Legacy collectors | `/monitoring/config`, `/interfaces`, `/netflow` (2), `/snmp/poll`, `/snmp/traps` (2) | REMOVE, 7.8 | The in-app collector and SNMP Quick Poll are removed (the mockup review, 2026-09-29) |
| Monitoring stack panel | `/monitoring/stack/`, `/monitoring/stack/<name>` | REMOVE, 7.8 | The status bar and integration health replace it |
| Topology | `/topology/*` (11), `/topology_data` | REMOVE, 7.8 | Neighbours carries discovery per device (C126); the fleet map is P.11's Topology item |
| Topology service | `/topology/service/status`, `/svg` | PLANNED, P.11 | The Topology sidebar item |
| AI agent | `/ai/*` (27: chat, history, events, approvals, agent run/pause/resume/timers, providers, playbooks, reports, debug) | REMOVE, 7.8 (decided 2026-10-05) | They do not block cutover: Stage 8 redesigns the agent as an on-call responder, its approvals folded into Needs attention (drift items already are); the chat, agent, approvals, Ansible and usage screens go with today's pages |
| Favicon | `/favicon.ico` | STAYS | Browsers ask for it |

## Legacy actions that are not routes

| Action | Status | Home or reason |
|---|---|---|
| The terminal (socket events) | **REMOVED 2026-10-05** (R39, brought forward from 7.8 on the operator's decision, after the console drill proved the emergency path: docs/CONSOLE_DRILL.md) | NSOT_FEATURE_AUDIT 3b: the Device page's allowlisted command box is the one way to ask a device. Gone: the three socket events and their gates, `modules/terminal.py`, `modules/terminal_audit.py` (its data file stays on the host, readable by hand), the v1 device page's Terminal tab, and the vendored xterm. Kept: the `break_glass` gate kind and its two settings, until they retire |
| Today's Git tab, Remote card, Baselines panel | PLANNED, History | History (signed off) |
| The AI chat panel (every page) | REMOVE, 7.8 (decided 2026-10-05) | Stage 8 redesigns it |
| Bulk restore at HEAD (`bulkRestoreGoldenConfig`) | REMOVE, 7.8 (cut 2026-10-05) | A device's Restore from… and History's baseline re-apply remain |
| Settings modal | PLANNED, P.8 and 7.7 | Settings per network (built), Installation (F) and the Installation/Diagnostics board |

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
   in-flight panel, the posture.
7. Bulk restore and bulk read-only commands are cut (fleet-wide reads revisited with Stage 8's
   agent or History › Query).
8. Revealing a golden version stays in the GUI (a person, recorded); the remote's connect,
   acknowledge and write probe are CLI only.
9. Reload (P.14) gets a board, its planned-restart declaration built in.
10. Refresh Hostnames is cut (C465 removed its write; hostnames come from captures).

The boards for 3, 5, 6 and 9 are drawn after the intent editor and Templates A to C are built,
so they do not delay the throwaway session. The status of every v1 capability, counted, is
[TRANSITION_STATUS.md](TRANSITION_STATUS.md).

## What the manual must cover

Every BUILT and PLANNED home above is a screen, and each needs its manual section before it
is done (the operator, 2026-10-02): Needs attention, Devices, the device page and each of its
tabs, History and its tabs, Monitoring (Dashboards, Coverage), Settings > Monitoring
templates, Templates, NetBox, Credentials, Settings, Help, Update. The operations among them
each need a "How it works" section (docs/manual/how-it-works/).
