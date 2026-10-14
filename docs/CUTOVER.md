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
| Job wake-up, planned restarts | `/jobs/finished`, `/restarts/planned` | STAYS | `nmas-job-finished@` from each job's systemd unit; `scripts/nmas-planned-restart`. (The lab's map, `/clab/sync_targets`, left the product with C663: the lab reads its own file.) |
| Deploy | `/deploy/plan`, `/deploy/apply` | BUILT, 7.4 (several devices 2026-10-10, not run on the host) | One device: the device page's Deploy (walked, C428). Several ticked devices: Devices › Plan a deploy for the ticked devices… (board B), the batch Apply's page with scope `intent` (the whole committed intent): one preview in a rollout order, one confirm, the run a job on the one stepper (the `deploy_plan` gap closed) |
| Deploy receipts | `/deploy/receipts` | BUILT, walked | The device page's History tab; the receipts can move to the records database (Phase 4) |
| Capture, Save All | `/golden/capture/preview`, `/apply`, `/preview/<job>` | BUILT (the reason for a shrink 2026-10-10, not run on the host) | Device Actions › Capture (walked) and Devices › Save (C593); the card takes the reason for recording a structural shrink (C486, C310; the `acknowledge` gap closed), and its What next follows the departure's direction |
| Restore, baselines | `/golden/restore/preview`, `/apply`, `/golden/restore_points/<host>`, `/golden/baselines` | BUILT, History (a network's Re-apply 2026-10-10, not run on the host) | Device Actions › Restore from… (walked) offers the baselines; History › Baselines › Re-apply… restores every device a baseline holds as one batch, through THE restore plan and a device Restore's job (the `reapply` gap closed) |
| Golden versions | `/golden/history/<host>`, `/golden/version/<host>`, `/golden/diff/<host>` | BUILT, History (the reveal 2026-10-10, not run on the host) | The History tab and `/v2/history/commit/<sha>` (walked); a golden row's Reveal <device>'s version… draws it unmasked in place, a person, recorded first (decided 2026-10-05) |
| Git | `/git/status`, `/git/log`, `/git/commit/<sha>` | BUILT, walked | History › Commits: the log, its filters and each commit's masked change |
| Remote | `/remote/push`, `/remote/verify`, `/remote/status` | BUILT | History's header (Push now, Verify; no real run yet) and `/v2/history/remote` |
| Remote, auto-push | `/remote/auto-push` | BUILT (C631, 2026-10-10; not run on the host) | History › Remote set-up…: Turn on automatic pushing, offered after a successful push |
| Remote, connect and the rest | `/remote/verify-write`, `/preview`, `/acknowledge`, `/adopt` | BUILT (C631, 2026-10-10; not run on the host) | History › Remote set-up…: Connect, Run the write probe, What a first push publishes and its typed Acknowledge, each a verified person's (`routes/remote_v2.py`). They were to stay CLI-only through a command that never existed; a host command cannot carry the verified person they need |
| Persist, rotate, retire | `/persist/*` (2), `/rotate/*` (3), `/retire/*` (2) | BUILT, walked | The device page's Actions: Persist (C359), Rotate (C370), Retire (r5); the routes go with today's pages |
| Seed, revert, retry | `/templatize/seed/*` (2), `/templatize/revert/*` (2), `/templatize/retry/*` (2), `/templatize/rolled-back/retries` | BUILT | Device Actions; seed walked, revert and retry not yet run |
| Intent editing | `/templatize/committed/<host>`, `/templatize/committed/<host>/preview`, `/templatize/committed` | BUILT (board H's Document mode; not run on the host, C444) | The Intent tab's Edit (`/v2/device/<name>/intent/*`), one code path with today's routes (`modules/nsot/intent_edit.py`); Fields mode (board J) is not built |
| Bulk intent | `/templatize/bulk/*` (2) | BUILT (board D, 2026-10-10; not run on the host) | Devices › Actions › Change a setting on (N)… (`routes/bulk_intent_v2.py`, `/v2/devices/change`): the change typed as settings, the preview grouped by what changes with the refused drawn, one commit as a verified person bound to the preview, then Plan a deploy for exactly the changed devices. One core with the JSON routes and `scripts/nmas-bulk-intent` (`routes/templatize.bulk_plan_of`, `bulk_apply_of`) |
| Monitoring profile | `/templatize/profile`, `/templatize/profile/propose/*` (2) | BUILT, walked (C566) | `/v2/monitoring/profile` |
| Templates: list, approve, revoke | `/templates`, `/templates/approval/<path>`, `/templates/approve/<path>`, `/templates/revoke/<path>` | BUILT (boards A to C, `/v2/templates`; not run on the host) | Source of truth › Templates |
| Templates: edit and the rest | `/templates/*` (7) | BUILT, 7.6 (2026-10-10, not run on the host) | Templates › Edit… (intent editor H's pattern, drawn under the Phase 7 mode): the file read and committed bound to the version opened, validate and preview as one check as typed (each governed device's render against its committed golden, never a backup, C632), refresh-capture as Capture… on the device's page; Bindings… (each platform's template and per-device overrides, previewed by the devices that move, bound to the file and the change); Seed the library… for a network with none (today's page seeded on a read); seed status is the Against the shipped version column |
| Onboard | `/onboard/*` (9) | BUILT, 7.4 (board E and the pending page's actions, 2026-10-10; not run on the host). Boards L (the discovery list) and M (serial pre-provisioning) are new capabilities, not v1 parity: nice-to-haves | Devices › Add device… (static, DHCP, ZTP by MAC; Create bound to its review) and a pending device's page: Verify… (preview, confirm), Get the bootstrap config… (a recorded reveal), Abandon… (its dry run, confirm bound to it); a retired device's Onboard it again…. The same cores as today's routes (`routes/onboard.py`) |
| Adopt | (no route; `modules/nsot/adopt.py`) | BUILT (board G, 2026-10-10; not run on the host) | Devices › Adopt a device… (`routes/adopt_v2.py`): the preview reads over the supplied login and sends nothing, the confirm (a verified person, the password typed again, bound to the preview's fingerprint) runs `adopt.apply` as a job on the stepper |
| NetBox import and remove | `/netbox/safety/*` (8), `/netbox/status` | BUILT, 7.6 (2026-10-10; not run on the host) | Source of truth › NetBox (`/v2/netbox`): every network's Import into NetBox… and Remove from NetBox…, Import every network…, each a preview job and a confirm that may turn writes on (C619), its result and recorded removals; the same core as today's routes (`modules/netbox_ops.py`) |
| NetBox connection test | `/netbox/test_connection` | BUILT | Settings › Installation › Connections, the NetBox card's Test |
| Inventory source | `/inventory/source/<list>`, `/inventory/refresh/<list>` | BUILT (2026-10-10; not run on the host) | Every network's Settings › Network tab, Inventory source: its own list or NetBox through filters, a preview reading NetBox once with the new filters (how many devices, which skipped and why), a confirm bound to it, recorded; Refresh now for a NetBox network |
| Networks | `/device_lists`, `/device_lists/<name>`, `/select_device_list` | BUILT, P.8 (2026-10-10; not run on the host) | Choosing one: BUILT (board N, 2026-10-10; not run on the host): the top bar's Network picker, the choice each verified person's own (`routes/network_v2.py`), so `/select_device_list`'s one choice for everyone has no v2 equivalent by design. Create and delete: BUILT (2026-10-10; not run on the host): Settings' New network… and a network's Delete this network…, each previewed and recorded; a deleted network's folder is moved aside, never erased. Rename: never offered by today's pages (C639), not built |
| Drift | `/drift/status`, `/drift/check`, `/drift/check/sync`, `/drift/settings` | BUILT, 7.7 (board F4, 2026-10-10) | Results are Needs attention rows; the schedule and Check now are Settings › Installation › Diagnostics |
| Break-glass export | `/breakglass/export` | STAYS (its preview route removed 2026-10-12, 7.8) | Credentials › The break-glass record posts to the one export (walked); today's modal goes at 7.8 |
| Identity and posture | `/identity/status`, `/identity/posture`, `/identity/posture/ratify` | BUILT, 7.7 (board F4) | Settings › Installation › Access and identity, with Record this decision; `/v2/who` |
| Settings | `/settings`, `/settings/integrations`, `/settings/integrations/*` (4) | BUILT, P.8 and 7.7 | Each network's Settings (boards A to J) and every Installation tab (boards F to F4); NetBox writes are turned on by an authorised NetBox confirm on Source of truth › NetBox (C619, closed 2026-10-10) |
| App log | `/logs/server` | BUILT, 7.7 (board F4) | Settings › Installation › Diagnostics, the app's log |
| In-flight operations | `/operations/in_flight` | BUILT, 7.7 (board F4) | Settings › Installation › Diagnostics, In flight |
| Version | `/health/version` | BUILT | Help › About |
| Backups | `/device/<ip>/backup_config`, `/backup_history`, `/backup_stats`, `/compare_backups`, `/delete_backup/<f>`, `/download_backup/<f>` | REMOVE, 7.8, after today's template editor | Section 6a's prerequisite (no render reads a backup): the v2 intent editor and bulk intent render against the committed golden only since 2026-10-11 (C683); today's template preview and refresh-capture still read the backup store (C632), and go with today's template editor, the last prerequisite. Today's device page also names these routes by `url_for` |
| Bulk read-only commands | `/bulk_execute`, `/bulk_status/<id>`, `/bulk_clear/<id>` | BUILT (C548; not yet walked on the host) | Show commands (`/v2/show-commands`): devices by name, role or network, commands from the allowlist, results grouped and compared |
| Reload | (no route of today's; its /bulk_reload removed 2026-10-12) | BUILT, P.14 (2026-10-10, the board drawn under the Phase 7 mode; not run on a device) | Device Actions › Reload…: a preview job reads the device and judges the six gates (running against startup, its golden and intent, startup carrying Mercury's credential, the boot image, no holder, the blast radius from committed intent and this host's subnets); a reason; the run declares its planned-restart window before it sends anything, reloads, waits within the platform's measured bound, verifies it runs what it ran, and records (History's Reloads). P.14's plain form: the device boots the startup it holds; booting a moment from history is revert by reload (the charter's Phase 2) |
| Ask the device | `/run_command/<ip>` | BUILT (C547; not yet walked on the host) | The device page's Ask tab (allowlisted) |
| Topology service | (no route of today's; its two routes and panel removed 2026-10-12) | BUILT for boards A and B (P.11 steps 1 and 2, 2026-10-10; the reader walked on the host, the page not yet); the service itself REMOVED at 7.8 (2026-10-12: the renderer from the repository, the unit and link by its host step, `topology-service-removal.sh`), and its integration with it (C714: no client, no probe, no Settings card; its keys `retiring` for one release) | OBSERVE › Topology (`routes/topology_v2.py` over the `topology-graph` reader): the layers, outside peers, islands (expected by a recorded declaration, or warned, and "became"), single points of failure, criticality, path trace, search, the list first at phone width. Still to come: saved shared positions (step 3), time travel and the wall (board C; its kiosk identity is the operator's) |
| AI agent | (no route of today's; its 26 routes under /ai/ removed 2026-10-14, tag `pre-remove/ai-family`) | **REMOVED 2026-10-14** (D15, decided 2026-10-05, after its stores were archived) | Stage 8 redesigns the agent as an on-call responder (docs/PHASE8_PLAN.md). The chat panel, the Agent, Approvals queue, Ansible and usage screens, v2's AI and workflow tab, the in-app SNMP trap and NetFlow receivers (`modules/snmp_collector.py`, `modules/netflow_collector.py`) and `modules/collector_config.py` went with it; the shared pieces stayed, moved out first (`modules/goldens.py`, `modules/bgp_summary.py`, `modules/drift_interval.py`). Today's drift panel stays, in a tab named Drift, until today's pages retire |

## Removed at 7.8

Each family leaves the table above in the commit that removes it, named here with that commit's
date (the order is the 7.8 survey's, 2026-10-11: no caller first, the smallest change first).

- **The TFTP setting** (/save_tftp_server), 2026-10-13 (D16; restore point tag
  `pre-remove/tftp-setting`; C616): its last readers, the device and bulk file routes, left the
  same day. Today's device table lost its TFTP server row and script, today's Settings its
  Network section (the one field), and the integrations payload the field; `tftp_server_ip` is
  RETIRING (declared one release, as Oxidized's keys). **`tftp_root` stayed** until the
  operator's CLAUDE.md change (C616), then left the same day (restore point tag
  `pre-remove/tftp-root`): `config.TFTP_ROOT` and `ensure_tftp_root()` (app.py imported both
  and used neither), today's Settings field "TFTP root" and its payload key; `tftp_root` is
  RETIRING beside `tftp_server_ip`. Proved before removal: nothing read either (the host's
  unit sets no `NMAS_TFTP_ROOT`, and `/srv/tftp` does not exist on the host).
- **Bulk file actions** (/bulk_tftp_upload, /bulk_tftp_download, /bulk_download_config,
  /bulk_delete_file), 2026-10-13 (D16; restore point tag `pre-remove/bulk-file-actions`): as
  device files. Today's device table lost its upload, download, config-download and delete
  cards and their script; the bulk worker its four file modes and their `_execute_*` senders.
  The TFTP server input and its Save stay on the table until the TFTP setting's own removal.
  No data of their own on this host.
- **Device files** (/device/<ip>/refresh_files, /upload, /download_file, /delete_file,
  /download), 2026-10-13 (D16; restore point tag `pre-remove/device-files`): no arbitrary file
  transfer (the operator, 2026-10-02); ZTP delivery and image management (P.13) replace them.
  Today's device page's File Management tab went with them, with its TFTP server input and the
  command output's Download link (the last output's download was `/download`). They kept no
  data of their own on this host. `tftp_root` and `tftp_server_ip` leave with the bulk file
  routes, their last readers.
- **Quick actions** (/add_quick_action, /delete_quick_action), 2026-10-13 (D16; restore point
  tag `pre-remove/quick-actions`): the terminal's companions, the terminal gone since R39. Today's
  device page's Quick actions section, its script and style, `modules/quick_actions.py` and
  `config.QUICK_ACTIONS_FILE` went with them. The store, `quick_actions.json`, is archived to the
  bucket (`scripts/host-steps/d16-archive.sh`) and deleted only after its read-back matches.
- **NetBox queries** (the six /netbox/query routes), 2026-10-11: no page called them, and the
  device page's NetBox tab reads NetBox itself. Their one helper only they used,
  `netbox_client.netbox_get_ip`, went with them.
- **Template coverage's JSON route** (/templatize/report, GET and POST), 2026-10-11: no page
  called it. Its home is Templates › Coverage (`routes/templates_v2.py`,
  `modules/nsot/template_coverage.py`): every committed golden rendered through its own template
  and compared, as a job a person starts. The route read the ACTIVE list's inventory beside the
  named list's templates and did per-device work per request. Its helpers `_platform_for`,
  `_public` and `_summarise` went with it.
- **Credential profiles' JSON routes** (the three /inventory/credentials routes and
  /inventory/dependents), 2026-10-12: no page called them. Their home is Credentials › Profiles
  (`routes/credential_profiles_v2.py`): each profile with what it covers, set or not set, never
  a value; Add, Edit, Delete, each a verified person's and recorded. `dependents`' warning lives
  in v2's Delete network preview (C645). `copy-inherited` had no caller and no v2 home; it went
  with `credentials.copy_inherited_to_overrides`, which only it used (Delete network names what
  would break instead).
- **Pending restart** (/session/pending-restart), 2026-10-12. The row said "no caller"; today's
  chat panel called it after a lost connection (C684), but nothing wrote the marker it read, so
  its auto-resume never fired. The route and that one fetch went; the chat still says "Server
  is back online". The Update button restarts, gated on held devices.
- **List variables and the compliance policy** (/list/variables and its two children,
  /list/compliance_policy, GET and POST each), 2026-10-12: no page called them; superseded by
  intent, drift, group intent and the monitoring templates (the operator, 2026-10-02).
  `ai_assistant._save_compliance_policy`, which only they used, went with them. The variable
  store's readers that remain (the agent's tools, the hostname refresh) are today's agent's and
  go with it.
- **List data** (/list/golden_configs, /list/drift_status, /list/change_log), 2026-10-12:
  superseded by Devices, Needs attention and History. The first two had no caller; the change
  log was today's index page's History tab, which went with it (its button, pane and loader).
  The change log's store and `ai_assistant._list_golden_configs` stay: today's agent reads them
  and goes with its own family.
- **Refresh hostnames** (/refresh_hostnames), 2026-10-12 (cut 2026-10-05): C465 had removed its
  NetBox write; a device's hostname comes from its captures. Its button on today's device list
  and its handler went with it, as did its gate, invalidation and stage entries, and its own
  test file (the manifest's pending rename it recorded is still tested in
  `tests/test_golden_repo.py`).
- **Renames** (/golden/renames, /golden/renames/sync), 2026-10-12 (decided 2026-10-05): today's
  Git tab drew pending renames and a Sync button. A rename the NetBox inventory refresh
  notices is still recorded in the manifest and committed alone by the next golden save
  (`repo.save_golden` runs `apply_pending_renames` first), so nothing is stranded. The two
  inventory helpers only these routes used (`sync_device_names_to_repo`, `pending_renames`)
  went with them; the manifest's own `pending_renames` stays.
- **The legacy golden store's report and the one-shot migration** (/golden/legacy_store,
  /golden/migrate/plan, /golden/migrate/apply), 2026-10-12: the store's retirement condition
  (`legacy_only_goldens()` empty) has held on the host since 2026-09-28, and the migration ran
  on every network. Today's Git tab drew both cards; its loader now reads the baselines alone
  and says when they cannot be read. The survival check retire uses for a device's file in the
  old store moved from `routes/golden.py` to `modules/nsot/retire.py` (`legacy_survives`), its
  only remaining user (a product module no longer imports a route file). Kept: the store's
  read-only fallback in the readers and `modules/nsot/migrate.py`, which two scripts use
  (`nsot_verify_migration.py`, `nsot_adopt_marker.py`). Proved before removal: none of the
  five paths is in the app's url_map, and nothing in templates, scripts, routes, modules or
  tests names them.
- **Today's bulk reload** (/bulk_reload), 2026-10-12: its home, Device Actions › Reload…
  (P.14), is built: gates judged by a preview job, a reason, the planned-restart window
  declared before anything is sent, the wait bounded by the platform's boot time, verify, the
  record. Today's device list's Reload Devices button and handler went with the route, and so
  did the two tests that read the route's body for "the window before the send"; that property
  is tested on v2's Reload (`tests/test_reload_v2.py`), and `device_reload.reload_device` stays
  (v2's `reload_op.run` calls it, holding the device). Proved before removal: not in the
  url_map; nothing but count comments names it.
- **The break-glass preview's JSON route** (/breakglass/preview), 2026-10-12: Credentials draws
  the preview itself (`routes/v2.py`, board 7) and posts to `/breakglass/export`, which stays.
  The route's only caller was today's modal in `static/js/nmas_breakglass.js`, which nothing
  opened since board 7 sent every opener to Credentials; the modal went, the two redirects
  stay. v2's passphrase checks are `nmas_credentials.js`'s, tested in
  `tests/test_credentials_v2.py`; the export tests now compute the preview the way
  Credentials does. Proved before removal: not in the url_map; nothing but comments names it.
- **Inventory order** (/reorder, /inventory/order/<list>), 2026-10-12: drag-reorder was
  removed in favour of sortable columns (the operator, 2026-09-29). v2's Devices is searched
  and filtered by state and platform, and has no column sort yet (C704). /inventory/order's
  one caller, `saveInventoryOrder`, was itself called by nothing; /reorder's was today's device
  list's drag binding, which went with it, and so did the vendored SortableJS (its files, its
  manifest and licence entries: `tests/test_csp.py` holds every vendored file to a page that
  loads it). The C160 test that held /reorder to keeping an unnamed device went with the route
  (`write_devices_csv`'s own tests stay). A NetBox list's stored order is still applied when
  the list loads (`source_config.apply_device_order`), so nothing reorders on the host. Proved
  before removal: today's index and the inventory partial were the only callers.
- **The monitoring stack panel** (/monitoring/stack/, /monitoring/stack/<name>), 2026-10-12:
  every v2 page's status strip (`device_v2.strip`, redrawn on `integration_health`) says which
  integrations answer, and Settings › Integrations tests each one. The panel was today's
  Monitoring tab's top card, its one caller. The five integrations' `monitor()` methods (NetBox,
  Prometheus, Loki, Kea, Grafana), which only it called, went with it, as did their tests: the
  Kea card's family-by-family counts (`tests/test_kea_dual_stack.py` keeps the active-lease rule
  `lease_for` reads) and the two card tests in `tests/test_onboard_dhcp_source.py` (Kea's
  EMPTY-is-success rule keeps its own test there). Today's Monitoring tab keeps the legacy
  collectors, their own family. Proved before removal: not reached by any v2 page, job or
  script; after it, neither path is in the url_map.
- **Configure** (/configure/devices, /configure/interfaces, /configure/networks,
  /configure/audit_latest, /configure/audit/<id>), 2026-10-12 (decided 2026-10-05): a device's
  Intent › Edit and Deploy… replace it, and the tab already sent nothing (P.3 cut its apply).
  Today's Configure tab went whole: its nav button, its pane with the wizard and the
  client-side Ansible playbook generator's modals, and its inline script (about 160 kB of the
  index's fixed cost). `/configure/interfaces` and `/configure/networks` opened a session to
  each device a request named (fixed show commands); the two audit routes read the pipeline's
  audit files, and their readers in `modules/pipeline.py` (`load_audit_entry`,
  `list_audit_entries`) went with them. Kept: `modules/configure.py`, whose generator the
  pipeline's render stage still imports, and the pipeline's audit files themselves (stage 9
  still writes them under the data directory, readable on the host; History's receipts are the
  record a person reads). Today's Ansible tab (the playbook list, `/ai/playbooks`) was the AI
  agent's family, and went with it (D15, 2026-10-14). Proved before removal: nothing outside the tab's own pane and script named
  its functions or ids, and no v2 page, job or script reaches the five paths; after it, none is
  in the url_map.
- **The legacy collectors' routes** (/monitoring/config GET and POST, /monitoring/interfaces,
  /monitoring/snmp/poll, /monitoring/snmp/traps and its clear, /monitoring/netflow and its
  clear), 2026-10-12: the in-app collector and SNMP Quick Poll were removed at the mockup
  review (2026-09-29); monitoring is Prometheus's, Loki's and Grafana's, drawn on
  `/v2/monitoring` and each device's Monitoring tab. Today's Monitoring tab, their one caller,
  went whole (its nav button, pane and script), and with it the `monitoring` invalidation key
  (no writer left). The protection the routes carried stayed where it then mattered: a device's
  SNMP community was resolved only from its own secret (`collector_config.community_for_address`,
  tested with the agent's tool in `tests/test_community_has_one_owner.py`). Kept then, for
  today's agent, their only reader: the trap and NetFlow receivers `app.py` started and the
  collector configuration; they went with the AI agent's family (D15, 2026-10-14; its row
  says so), the resolver and its tests with them, and `tests/test_community_has_one_owner.py`
  keeps only the rule that no community parameter has a default. Two tests
  that used `monitoring_config` as an example moved to another endpoint of the same shape
  (`settings_integrations.general_settings` for a GET-and-POST endpoint, `git_status` for a
  v1 navigation). Proved before removal: today's Monitoring tab was the only caller; after
  it, none of the paths is in the url_map.
- **The topology service's routes and panel** (/topology/service/status,
  /topology/service/svg), 2026-10-12: OBSERVE › Topology (`routes/topology_v2.py`, over the
  `topology-graph` reader) is the fleet map. The panel was the top of today's Topology tab, its
  one caller; the route file, the partial, its script and its test file
  (`tests/test_topology_service_view.py`, every test the panel's or the routes') went. Not done
  here: the service itself (the `nmas-topology` unit and `deploy/topology/nmas-topology.py`,
  host-installed, so its removal carries a host step) and the integration's Settings card;
  the Topology service row above keeps them. Proved before removal: the panel was the only
  caller; after it, neither path is in the url_map.
- **The topology service itself** (the `nmas-topology` unit and its renderer,
  `deploy/topology/nmas-topology.py`), 2026-10-12: nothing in Mercury read it once the panel
  went (no reader of `graph.json` or port 8088 in the product). The renderer and its test file
  (`tests/test_topology_renderer.py`) left the repository; its registry entry stays, retired,
  for its removal check, `topology-renderer-gone` (the link and the unit file both absent).
  The host step, `scripts/host-steps/topology-service-removal.sh`, stops and disables the
  unit, then removes the unit file and the link by name. Measured on the host first: the unit
  active and enabled, answering on 8088, its link into the checkout. Its integration went
  next (C714, the same day: its probe drew a CRITICAL row for the retired service): the
  client and its registration, the Settings card on both pages; the four keys stay declared
  as `retiring` for one release (`tests/test_retired_integrations.py`).
- **Today's Topology tab** (/topology_data, /topology/state, /topology/positions,
  /topology/hidden, /topology/link_status, /topology/proto_link_status,
  /topology/protocol_data, /topology/protocol_state, /topology/proto_hidden,
  /topology/proto_positions), 2026-10-12: Neighbours carries discovery per device (C126) and
  OBSERVE › Topology is the fleet map (P.11). The tab went whole: its nav button, pane (the
  legacy CDP/LLDP, OSPF, BGP and tunnel views), `static/js/gen/index.3.js` (all of it the tab's)
  and the vendored vis-network it alone loaded (files, manifest and licence entries). The two
  routes that opened a session per device (link status, protocol link status) went with it.
  Kept then: `modules/topology.py`, whose `discover_topology` today's agent still called; it
  went with the AI agent's family (D15, 2026-10-14). Four invalidation-map tests that used the layout save as their
  example mutating route now use `POST /remote/auto-push` (one key, a JSON answer), shown
  able to fail by moving that route's key. Proved before removal: nothing outside the tab's
  pane and script named its functions or ids; after it, no `/topology` path of today's is in
  the url_map.
- **Reachability** (/status/<ip>, /connection_status/<ip>), 2026-10-12: the reachability
  reader (C92) is what v2 draws (Devices, each device's status, Needs attention).
  `/status/<ip>` was polled every 5 s for each row of today's device list; the polling
  (`deviceIps`, `updateStatus` in `static/js/gen/index.2.js`) went, so today's list shows each
  device's reachability as of the page's load, and the AI device cache that file seeds keeps
  being seeded from the page. `/connection_status/<ip>` drew today's device page's "SSH
  Connected" badge and, every 5 s while that page was open, asked the device for its prompt
  on a persistent session: the badge, its script and the session went. Proved before removal:
  those two scripts were the only callers; after it, neither path is in the url_map.
- **Device regions** (/devices/regions), 2026-10-12 (the operator asked for it next): `/v2/devices`
  replaces today's device list, and redraws itself when `inventory` is announced (v2's
  relay). The route re-rendered today's list in place for the same announcement
  (`routes/devices_view.py`, Stage 7.0); its client (`applyDeviceRegions`,
  `refreshDeviceRegions` in `static/js/gen/index.1.js`) and the two app extensions only it read
  (`nmas_device_status`, `nmas_tftp_server`) went with it. Today's list now shows what it held
  when the page loaded; a reload redraws it. The two partials stay (today's index renders
  them). The subscription floor's device-list case is v2's relay now. Proved before removal:
  that client was its only caller; after it, the path is not in the url_map.

## Legacy actions that are not routes

| Action | Status | Home or reason |
|---|---|---|
| The terminal (socket events) | **REMOVED 2026-10-05** (R39, brought forward from 7.8 on the operator's decision, after the console drill proved the emergency path: docs/CONSOLE_DRILL.md) | The Device page's allowlisted Ask tab is the one way to ask a device. Kept: the `break_glass` gate kind and its two settings, until they retire |
| Today's Git tab, Remote card, Baselines panel | BUILT | History: Commits, the remote's sentence, Baselines |
| The AI chat panel (every page) | REMOVE, 7.8 (decided 2026-10-05) | Stage 8 redesigns it |
| Bulk restore at HEAD (`bulkRestoreGoldenConfig`) | REMOVE, 7.8 (cut 2026-10-05) | A device's Restore from… and History's baselines remain |
| Settings modal | BUILT | Settings per network and every Installation tab are built; NetBox writes come on by an authorised confirm on the NetBox page (C619, closed 2026-10-10) |

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
DHCP and NetBox (the Logs and DHCP links name screens today's page does not have: C633).
NetBox, onboarding and Capture's reason closed the same day (cutover blockers 2 to 4), then
the batch deploy and Re-apply, and the sidebar's Logs and DHCP now say what is there (C633):
**the list is empty**, so no v2 page sends a person to today's pages. A v2
request that fails says "Couldn't load" in place and never redirects to today's index; a
designed v2 error page is a further gap, pending a mockup.

## What the manual must cover

Every BUILT and PLANNED home above is a screen, and each needs its manual section before it
is done (the operator, 2026-10-02): Needs attention, Devices, the device page and each of its
tabs, History and its tabs, Monitoring (Dashboards, Coverage), Settings > Monitoring
templates, Templates, NetBox, Credentials, Settings, Help, Update. The operations among them
each need a "How it works" section (docs/manual/how-it-works/).
