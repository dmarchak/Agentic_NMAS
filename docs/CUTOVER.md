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
| Golden versions | `/golden/history/<host>`, `/golden/version/<host>`, `/golden/diff/<host>` | PLANNED, History | History's commit rows and the device page's History tab (reveal a version, a person, audited) |
| Git | `/git/status`, `/git/log`, `/git/commit/<sha>` | BUILT | History > Commits (2026-10-02): the log, its filters and each commit's masked change |
| Remote | `/remote/push`, `/remote/verify` | BUILT | History's header (2026-10-02): the remote's sentence, Push now and Verify |
| Remote, the rest | `/remote/status`, `/auto-push`, `/verify-write`, `/preview`, `/acknowledge`, `/adopt` | PLANNED, History | History's remote section: connect, acknowledge publication, the write probe, auto-push |
| Renames | `/golden/renames`, `/golden/renames/sync` | PLANNED, 7.4 | Devices, with Refresh Hostnames |
| Legacy golden store, migration | `/golden/legacy_store`, `/golden/migrate/plan`, `/golden/migrate/apply` | REMOVE, 7.8 | Its retirement condition (`legacy_only_goldens()` empty) has held on the host since 2026-09-28 (plan 7.8) |
| Persist, rotate, retire | `/persist/*`, `/rotate/*`, `/retire/*` | PLANNED, 7.3 | Device Actions (built on today's page; the v2 menu links there) |
| Seed, revert, retry | `/templatize/seed/*`, `/templatize/revert/*`, `/templatize/retry/*`, `/templatize/rolled-back/retries` | PLANNED, 7.3 | Device Actions, and History for revert |
| Intent editing | `/templatize/committed/<host>` (read, edit, preview), `/templatize/committed` | PLANNED, 7.3 | The Intent tab's editor (read-only today) |
| Bulk intent | `/templatize/bulk/preview`, `/apply` | PLANNED, 7.4 | Devices selection |
| Monitoring profile | `/templatize/profile`, `/templatize/profile/propose/*` | PLANNED, the monitoring templates | Settings > Monitoring templates (mockup awaiting sign-off) |
| Template coverage | `/templatize/report` | PLANNED, 7.6 | Templates |
| Templates | `/templates/*` (11: list, file, approve, revoke, approval, bindings, preview, refresh-capture, seed_status, validate) | PLANNED, 7.6 | Source of truth > Templates |
| Onboard | `/onboard/*` (9) | PLANNED, 7.4 | Devices > Onboard; the v2 pending page shows a pending device today, its actions on today's page |
| Adopt | (no route; `modules/nsot/adopt.py`) | PLANNED, 7.4 | Devices > Adopt |
| NetBox import and remove | `/netbox/safety/*` (7), `/netbox/status`, `/netbox/test_connection` | PLANNED, 7.6 | Source of truth > NetBox |
| NetBox queries | `/netbox/query/*` (6) | REMOVE, 7.8 | No page calls them (measured 2026-10-02); the device page's NetBox tab reads NetBox itself |
| Credentials | `/inventory/credentials/*` (3), `/inventory/dependents/<list>` | PLANNED, 7.6 | Source of truth > Credentials |
| Inventory source | `/inventory/source/<list>` (GET, POST), `/inventory/refresh/<list>` | PLANNED, 7.4 | Devices > Networks |
| Inventory order | `/inventory/order/<list>`, `/reorder` | REMOVE, 7.8 | Drag-reorder removed for sortable columns (the operator, 2026-09-29) |
| Device lists | `/device_lists` (3), `/select_device_list` | PLANNED, 7.4 | Devices > Networks |
| List data | `/list/golden_configs`, `/list/drift_status`, `/list/change_log` | REMOVE, 7.8 | Superseded by Devices, Needs attention and History |
| List variables, compliance policy | `/list/variables` (4), `/list/compliance_policy` (2) | REMOVE, 7.8 | Superseded by intent, drift, group intent and the monitoring templates (the operator, 2026-10-02); Stage 8 re-establishes how the agent works |
| Refresh hostnames | `/refresh_hostnames` | PLANNED, 7.4 | Devices |
| Drift | `/drift/status`, `/drift/check`, `/drift/check/sync`, `/drift/settings` (2) | PLANNED, 7.7 | Results are Needs attention rows (built); the schedule and "check now" go to Settings > Checks |
| Freshness authorisations | `/freshness/authorisations` | BUILT | History > Authorisations (2026-10-02) |
| Authorise a divergence | `/freshness/authorise` | PLANNED, 7.6 | Source of truth, beside the divergence it authorises |
| Break-glass export | `/breakglass/preview`, `/export` | PLANNED, 7.7 | Settings, and Needs attention's break-glass row (which links to today's page now) |
| Identity and posture | `/identity/status`, `/identity/posture`, `/identity/posture/ratify` | PLANNED, 7.7 | Settings > Diagnostics |
| Settings | `/settings` (2), `/settings/integrations/*` (5), `/save_tftp_server` | PLANNED, 7.7 | Settings, split |
| Server and session | `/server/restart`, `/session/pending-restart` | `/server/restart` REMOVED 2026-10-02 (with `/ai/restart`, CONCURRENCY_AUDIT R5: each ended the process with no check of held devices); `/session/pending-restart` REMOVE, 7.8 | No caller (measured 2026-09-27); the Update button restarts, gated on held devices |
| App log | `/logs/server` | PLANNED, 7.7 | Settings > Diagnostics |
| In-flight operations | `/operations/in_flight` | PLANNED, 7.3 | The v2 frame's running-operations panel (today's pages draw it; v2's pending page only) |
| Reachability | `/status/<ip>`, `/connection_status/<ip>` | REMOVE, 7.8 | The reachability reader (C92) is what v2 draws |
| Device regions | `/devices/regions` | REMOVE, 7.8 | Today's device list; `/v2/devices` replaces it |
| Backups | `/device/<ip>/backup_config`, `/backup_history`, `/backup_stats`, `/compare_backups`, `/delete_backup/<f>`, `/download_backup/<f>` | REMOVE, 7.8 | The backup store retires after section 6a's prerequisite (no render reads a backup) |
| Device files | `/device/<ip>/refresh_files`, `/upload`, `/download_file`, `/delete_file`, `/download` | REMOVE, 7.8 | No arbitrary file transfer (the operator, 2026-10-02). Replaced by purpose-built operations: ZTP delivery in onboarding, and software image management (NSOT_PLAN P.13). **Before removing**: check what ZTP serves today (the lab's configs folder holds a TFTP-written file) and keep that path working |
| Bulk operations | `/bulk_execute`, `/bulk_status/<id>`, `/bulk_clear/<id>` | PLANNED, 7.4 | Devices selection, read-only commands only (C61's allowlist) |
| Bulk file actions | `/bulk_delete_file`, `/bulk_download_config`, `/bulk_tftp_upload`, `/bulk_tftp_download` | REMOVE, 7.8 | As device files |
| Reload | `/bulk_reload` | REMOVE, 7.8; replaced by P.14 | Reload becomes a gated device-page operation (NSOT_PLAN P.14: unsaved changes, drift, the boot credential and image, no holder, the blast radius) |
| Ask the device | `/run_command/<ip>` | PLANNED, 7.3 | The device page's "Ask the device" tab (allowlisted) |
| Quick actions | `/add_quick_action`, `/delete_quick_action` | REMOVE, 7.8 | The terminal's companions; the terminal is removed (NSOT_FEATURE_AUDIT 3b) |
| Configure | `/configure/*` (6) | PLANNED, 7.9 | The Configure forms, a parallel track |
| Legacy collectors | `/monitoring/config`, `/interfaces`, `/netflow` (2), `/snmp/poll`, `/snmp/traps` (2) | REMOVE, 7.8 | The in-app collector and SNMP Quick Poll are removed (the mockup review, 2026-09-29) |
| Monitoring stack panel | `/monitoring/stack/`, `/monitoring/stack/<name>` | REMOVE, 7.8 | The status bar and integration health replace it |
| Topology | `/topology/*` (11), `/topology_data` | REMOVE, 7.8 | Neighbours carries discovery per device (C126); the fleet map is P.11's Topology item |
| Topology service | `/topology/service/status`, `/svg` | PLANNED, P.11 | The Topology sidebar item |
| AI agent | `/ai/*` (27: chat, history, events, approvals, agent run/pause/resume/timers, providers, playbooks, reports, debug) | PLANNED, Stage 8 | The agent becomes an on-call responder; approvals fold into Needs attention (drift items already do); playbooks, reports and the debug log are Stage 8's to keep or cut |
| Favicon | `/favicon.ico` | STAYS | Browsers ask for it |

## Legacy actions that are not routes

| Action | Status | Home or reason |
|---|---|---|
| The terminal (socket events) | REMOVE, 7.8 | NSOT_FEATURE_AUDIT 3b: the Device page's allowlisted command box is the one way to ask a device |
| Today's Git tab, Remote card, Baselines panel | PLANNED, History | History (signed off) |
| The AI chat panel (every page) | PLANNED, Stage 8 | |
| Settings modal | PLANNED, 7.7 | Settings |

## Decided 2026-10-02

The three undecided rows were answered by the operator: the generic file actions go,
replaced by purpose-built operations (ZTP delivery in onboarding; P.13's image
library, transfer and upgrade); reload stays as a gated device-page operation
(P.14); the list variables and the compliance policy go. No row is UNDECIDED.

## What the manual must cover

Every BUILT and PLANNED home above is a screen, and each needs its manual section before it
is done (the operator, 2026-10-02): Needs attention, Devices, the device page and each of its
tabs, History and its tabs, Monitoring (Dashboards, Coverage), Settings > Monitoring
templates, Templates, NetBox, Credentials, Settings, Help, Update. The operations among them
each need a "How it works" section (docs/manual/how-it-works/).
