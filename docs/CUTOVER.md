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
| Today's pages | `/` (index); today's device page (/device/<ip>) removed 2026-10-17, restore tag `pre-remove/v1-device` | The index: REMOVE, 7.8 (P7-27). The device page: **REMOVED 2026-10-17** (7.8, P7-22; under Removed at 7.8) | Replaced by `/v2/` and `/v2/device/<name>` (walked; the device page in W1, C547 for its Ask tab); the index goes when this table has no PLANNED or PARTLY BUILT row left. v2 links into it only through the labelled gaps in `tests/todays_page_links.py` (none). Today's device list's Manage opens the device's v2 page |
| Needs attention data | `/attention` | BUILT, walked | Needs attention (`/v2/attention`) draws each (7.2). The job-health and rolled-back JSON reads (/jobs/health, /templatize/rolled-back), which no page called, were removed 2026-10-15 (7.8): Needs attention reads the job-health reader's stored rows and `rolled_back_notes`, and `nmas-jobs` asks job health live on the host |
| Acknowledge a row | `/attention/acknowledge` | BUILT | v2's Needs attention posts to it (`_attention.html`) |
| Infrastructure | `/health`, `/health/operations`, `/static/<path:filename>`, `/favicon.ico` | STAYS | `/health`: the Update page and the root updater; `/health/operations`: `scripts/nmas-deploy`; the static files; browsers ask for the icon |
| Job wake-up, planned restarts | `/jobs/finished`, `/restarts/planned` | STAYS | `nmas-job-finished@` from each job's systemd unit; `scripts/nmas-planned-restart`. (The lab's map, `/clab/sync_targets`, left the product with C663: the lab reads its own file.) |
| Deploy | `/deploy/plan`, `/deploy/apply` | BUILT, 7.4; **WALKED 2026-10-16** (W1 steps 13 to 18: s1 and s2 in one batch, Done, verified) | One device: the device page's Deploy (walked, C428). Several ticked devices: Devices › Plan a deploy for the ticked devices… (board B), the batch Apply's page with scope `intent` (the whole committed intent): one preview in a rollout order, one confirm, the run a job on the one stepper (the `deploy_plan` gap closed) |
| Deploy receipts | (no route of today's; /deploy/receipts removed 2026-10-17 with today's device page, restore tag `pre-remove/v1-device`) | **REMOVED 2026-10-17** (7.8, P7-22; under Removed at 7.8). BUILT, walked before it | The device page's History tab (`history_sources.receipts`), which masks each row's texts again on the way out, as the removed route did; the receipts can move to the records database (Phase 4) |
| Capture, Save All | `/golden/capture/preview`, `/apply`, `/preview/<job>` | BUILT; **Capture and Save All WALKED 2026-10-16** (W1 section E: s2's card, "Nothing to confirm"; section J: Save All earned baseline/20261016T010219Z); the shrink's reason not producible on this fleet, proven by its tests | Device Actions › Capture (walked) and Devices › Save (C593); the card takes the reason for recording a structural shrink (C486, C310; the `acknowledge` gap closed), and its What next follows the departure's direction |
| Restore, baselines | (no route of today's; its four, /golden/restore/preview and /apply, /golden/restore_points/<host> and /golden/baselines, removed 2026-10-17, restore tag `pre-remove/v1-git`) | **REMOVED 2026-10-17** (7.8, P7-21; under Removed at 7.8). BUILT, History; **Re-apply WALKED 2026-10-16** (W1 steps 40 and 41: all nine "already as the baseline holds it", nothing to re-apply); a re-apply that sends lines proven by its tests | Device Actions › Restore from… (walked) offers the baselines; History › Baselines › Re-apply… restores every device a baseline holds as one batch, through THE restore plan (`routes/golden.restore_plan`, which stays) and a device Restore's job (the `reapply` gap closed). Today's device page's Restore from…, which sent the device to the index page's re-apply dialog, went with them |
| Golden versions | `/golden/history/<host>`, `/golden/version/<host>`, `/golden/diff/<host>` | BUILT, History; **the reveal WALKED 2026-10-16** (W1 steps 7 and 8, s2) | The History tab and `/v2/history/commit/<sha>` (walked); a golden row's Reveal <device>'s version… draws it unmasked in place, a person, recorded first (decided 2026-10-05) |
| Git | (no route of today's; its three, /git/status, /git/log and /git/commit/<sha>, removed 2026-10-17, restore tag `pre-remove/v1-git`) | **REMOVED 2026-10-17** (7.8, P7-21; under Removed at 7.8). BUILT, walked | History › Commits: the log, its filters and each commit's masked change (today's commit view returned it unmasked); History's header names what is not committed |
| Remote | `/remote/push`, `/remote/verify` | BUILT; **STAYS for History's header**, which posts to both (Push now, Verify the remote; `templates/v2/_history_remote.html`, each answering for the page's network, `listref.PAGE_ROUTES_OUTSIDE_V2`). Today's Remote card's /remote/status, which only the card read, **REMOVED 2026-10-17** (7.8, P7-21). **WALKED 2026-10-17** (W3, steps 24 and 25, ~05:50Z on fecab2f79e: Verify the remote "Last verified just now (<operator>)", every check passed, C1024 walked; the write probe busy "Probing…", all 5 checks passed, its ref removed clean; the reload's record commit c4f55e0 pushed by automatic pushing, the header "in sync"). Before it, **run on the host in W2, not closed** (2026-10-16, steps 21 and 22: Verify the remote ran ~23:02Z and every check passed, but its record names "unauthenticated", C1024, the operator's B2; Push now is not drawn while auto-push leaves nothing to push, and the push itself ran by auto-push, row 49). Closes with C1024 | History's header (Push now, Verify) and `/v2/history/remote` |
| Remote, auto-push | (no route of today's; /remote/auto-push removed 2026-10-17, restore tag `pre-remove/v1-git`) | **REMOVED 2026-10-17** (7.8, P7-21). BUILT (C631, 2026-10-10); **WALKED 2026-10-17** (W2 step 53, ~00:04Z: after sections J and K's commits History's header read "Last push 2 min ago by auto-push"; screenshot 61) | History › Remote set-up…: Turn on automatic pushing, offered after a successful push |
| Remote, connect and the rest | (no route of today's; its three, /remote/verify-write, /remote/preview and /remote/acknowledge, removed 2026-10-17, restore tag `pre-remove/v1-git`) | **REMOVED 2026-10-17** (7.8, P7-21). BUILT (C631, 2026-10-10); **WALKED 2026-10-16** (W2 steps 23 to 25 and 38, the operator's PASS: What a first push publishes ~23:05Z gated only `snmp_community` (af5580a277e2), acknowledged as the operator; the write probe passed all 5 checks, its ref removed clean (shown nothing while it ran: C1023, the operator's B1); Connect's shape check refused the alias "-probe" on W2 walk ~23:35Z, though it cleared every field, C1056) | History › Remote set-up…: Connect, Run the write probe, What a first push publishes and its typed Acknowledge, each a verified person's (`routes/remote_v2.py`). They were to stay CLI-only through a command that never existed; a host command cannot carry the verified person they need. Today's connect route (/remote/adopt), which no page called, was removed 2026-10-15 (7.8); Connect calls the same `remote.adopt`. Carried over from today's Remote card before it left (2026-10-17): the card lists each acknowledged secret by kind, fingerprint and devices, and its Last push says how (manual or auto) and what went out (the commit and its tags, or tag only) |
| Persist, rotate, retire | `/persist/*` (2), `/rotate/*` (3), `/retire/*` (2) | BUILT, walked | The device page's Actions: Persist (C359), Rotate (C370), Retire (r5); the routes go with today's pages |
| Seed, revert, retry | `/templatize/seed/*` (2), `/templatize/revert/*` (2), `/templatize/retry/*` (2) | BUILT | Device Actions; seed walked, revert and retry not yet run. The retry record's JSON read (/templatize/rolled-back/retries), which no page called, was removed 2026-10-15 (7.8): each retry is a row on the device's History |
| Intent editing | `/templatize/committed/<host>`, `/templatize/committed/<host>/preview` | BUILT (board H's Document mode); **WALKED 2026-10-16** (W1 steps 20 to 27, C444 closed); Fields mode C907 | The Intent tab's Edit (`/v2/device/<name>/intent/*`), one code path with today's routes (`modules/nsot/intent_edit.py`); Fields mode (board J) is not built. The list of devices with committed intent (/templatize/committed), which no page called, was removed 2026-10-15 (7.8) |
| Bulk intent | (no route of today's; its two JSON routes, /templatize/bulk/preview and /apply, removed 2026-10-15) | BUILT (board D); **WALKED 2026-10-16** (W1 steps 13 to 15); today's routes **REMOVED 2026-10-15** (7.8) | Devices › Actions › Change a setting on (N)… (`routes/bulk_intent_v2.py`, `/v2/devices/change`): the change typed as settings, the preview grouped by what changes with the refused drawn, one commit as a verified person bound to the preview, then Plan a deploy for exactly the changed devices. Its core is `routes/templatize.bulk_plan_of` and `bulk_apply_of`; `scripts/nmas-bulk-intent` shares its inputs and render (`_bulk_inputs`, `_bulk_render_and_eligible`) |
| Monitoring profile | `/templatize/profile`, `/templatize/profile/propose/*` (2) | BUILT, walked (C566) | `/v2/monitoring/profile` |
| Templates: list, approve, revoke | `/templates`, `/templates/approval/<path>`, `/templates/approve/<path>` | BUILT (boards A to C, `/v2/templates`); **WALKED 2026-10-16** (W2 steps 41 to 43, ~23:47Z: `cisco_ios/base.j2` revoked, a6a1f8a504; approved, 983a3b40ef, fingerprint 3036f36bcf76, s1 to s4 0/0/0; Approve shows nothing while it runs, C1023) | Source of truth › Templates. Today's revoke route (/templates/revoke/<path>), which no page called, was removed 2026-10-15 (7.8); Templates › Revoke… calls the same `approve_op.revoke` |
| Templates: edit and the rest | `/templates/*` (4) | BUILT, 7.6 (2026-10-10); **WALKED 2026-10-16** (W2 steps 44 to 50, ~23:50Z to 23:56Z: an edit committed, 59cc64bc65, approved bb4025a604 at fingerprint cd2eed997358; the edit removed and approved f4efff8aca, back to 3036f36bcf76; Bindings… committed b5a60075b3, s1's override and its removal d2dc1f914e; and step 38's Seed the library… on W2 walk, c5768aea50, ~23:31Z) | Templates › Edit… (intent editor H's pattern, drawn under the Phase 7 mode): the file read and committed bound to the version opened, validate and preview as one check as typed (each governed device's render against its committed golden, never a backup, C632), refresh-capture as Capture… on the device's page (today's refresh-capture route removed 2026-10-14 with the backup store it wrote to, and today's preview renders against the committed golden only, C632); Bindings… (each platform's template and per-device overrides, previewed by the devices that move, bound to the file and the change); Seed the library… for a network with none (today's page seeded on a read); seed status is the Against the shipped version column. Removed 2026-10-15 (7.8), no page calling them: today's bindings save (POST /templates/bindings), seed status (/templates/seed_status) and the preview's POST half (its GET stays for today's editor) |
| Onboard | `/onboard/*` (9) | BUILT, 7.4 (board E and the pending page's actions, 2026-10-10; not run on the host). Boards L (the discovery list) and M (serial pre-provisioning) are new capabilities, not v1 parity: nice-to-haves | Devices › Add device… (static, DHCP, ZTP by MAC; Create bound to its review) and a pending device's page: Verify… (preview, confirm), Get the bootstrap config… (a recorded reveal), Abandon… (its dry run, confirm bound to it); a retired device's Onboard it again…. The same cores as today's routes (`routes/onboard.py`) |
| Adopt | (no route; `modules/nsot/adopt.py`) | BUILT (board G, 2026-10-10; not run on the host) | Devices › Adopt a device… (`routes/adopt_v2.py`): the preview reads over the supplied login and sends nothing, the confirm (a verified person, the password typed again, bound to the preview's fingerprint) runs `adopt.apply` as a job on the stepper |
| NetBox import and remove | (no route of today's; its nine routes, the eight under /netbox/safety/ and /netbox/status, removed 2026-10-17, restore tag `pre-remove/v1-netbox`) | **REMOVED 2026-10-17** (7.8, P7-20; under Removed at 7.8). **WALKED 2026-10-17** (W3, steps 13 and 20 to 23 on fecab2f79e: Default's import previewed "NetBox already matches", confirmed once with "Starting the import…" busy (C1023), 05:43:33 to 05:45:25Z, 9 of 9; its History row names the confirmer and "previewed by" (C1024, C1030); Remove from NetBox… on W3 walk and on Default "Remove is not offered:", the reach "not established" in words, no Remove button (C932); Stop tracking instead… previewed, forgetting 10, not confirmed; Remove itself is not needed for cutover, the operator's decision on C1097). Before it, walked in W2 (2026-10-16, steps 16 to 20: the import's preview "create 0, change 13", confirmed, complete 9 of 9 at 22:53:18Z, the re-preview "NetBox already matches"; Remove and Stop tracking previewed, not confirmed, as scripted), with C1023 (B1) and C932 (B9) fixed after it | Source of truth › NetBox (`/v2/netbox`): every network's Import into NetBox… and Remove from NetBox…, Import every network…, each a preview job and a confirm that may turn writes on (C619), its result and recorded removals, over `modules/netbox_ops.py` (the core today's routes shared). Today's Just stop tracking (`forget_only`, unbound) is the Remove card's Stop tracking instead… (C954): its own preview, read from Mercury's created record alone (deletes nothing in NetBox; the objects Mercury forgets, each named, counted by type, collapsed past 20; where the data survives), confirmed as a verified person by the hash of exactly those entries and refused if the record moved, holding the network's NetBox writer, done through `netbox_ops.remove`'s `forget_only` given exactly the confirmed entries, and recorded in the removal record with each entry forgotten |
| Inventory source | `/inventory/source/<list>`, `/inventory/refresh/<list>` | BUILT (2026-10-10); **WALKED 2026-10-16** (W2 steps 36 and 37, ~23:29Z, on W2 walk: NetBox filtered by status `planned` (the script's `decommissioning` matched r5), previewed, saved, refreshed, 0 devices, and put back to its own list; screenshots 26 and 27; the NetBox fields left editable, C1055) | Every network's Settings › Network tab, Inventory source: its own list or NetBox through filters, a preview reading NetBox once with the new filters (how many devices, which skipped and why), a confirm bound to it, recorded; Refresh now for a NetBox network. Today's `/inventory/source/<list>` is its GET (the panel's read); its POST, which no page sent, was removed 2026-10-15 (7.8) |
| Networks | (no route of today's; its three, POST /device_lists, DELETE /device_lists/<name> and POST /select_device_list, removed 2026-10-17, restore tag `pre-remove/v1-networks`) | **REMOVED 2026-10-17** (7.8, P7-26; under Removed at 7.8; the installation's active list FROZEN with it). BUILT, P.8 (2026-10-10); **WALKED 2026-10-16** (W2 steps 33 to 35 and 40: W2 walk created, chosen in the top bar's picker, Devices·0, ~23:21Z; deleted at 23:41:31Z, moved to `lists_removed/w2_walk-20261016T234131Z`, 2 commits; screenshots 25 and 38), and **again in W3** (2026-10-17, steps 38 to 43: W3 walk deleted, its deleted page, created again under the same name and deleted again). C1022 (A1, the page's network lost after its first render) and C1029 (B7, a deleted network's Settings still live), found in W2, fixed and walked in W3 | Choosing one: BUILT (board N, 2026-10-10; walked in W2): the top bar's Network picker, the choice each verified person's own (`routes/network_v2.py`), so `/select_device_list`'s one choice for everyone has no v2 equivalent by design: the installation's list it set is frozen, read as the default where no network is named and its person has chosen none, and by today's index and the host scripts. Create and delete: BUILT (2026-10-10; walked in W2 and W3): Settings' New network… and a network's Delete this network…, each previewed and recorded; a deleted network's folder is moved aside, never erased. Carried over from today's delete before it left (2026-10-17): a network Mercury's record says created NetBox objects, or whose record cannot be read, is refused, naming them (C155; v2's delete had no such guard). Rename: never offered by today's pages (C639), not built. Today's GET /device_lists, the list of lists as JSON that no page called, was removed 2026-10-15 (7.8) |
| Break-glass export | `/breakglass/export` | STAYS (its preview route removed 2026-10-12, 7.8) | Credentials › The break-glass record posts to the one export (walked); today's modal goes at 7.8 |
| Identity diagnostic | `/identity/status` | STAYS (a question for the operator, 7.8) | The end-to-end identity diagnostic, not gated by identity (docs/LESSONS.md, the route-gates section), read with curl; the posture is Settings › Installation › Access and identity (board F4), and who you are is every v2 page's top bar and `/v2/who`. Today's status bar read it until it left at 7.8 (2026-10-15) |
| Integration health | `/settings/integrations/status` | STAYS (a question for the operator, 7.8) | docs/DEPLOY_LINUX.md's Verify reads it with curl on a new install; every v2 page's strip and Needs attention read the same stored value in-process. Today's status bar and Settings strip read it until they left at 7.8 (2026-10-15) |
| In-flight operations | `/operations/in_flight` | BUILT, 7.7 (board F4) | Settings › Installation › Diagnostics, In flight. The route stays while today's index does: today's in-flight panel (`templates/base.html`, today's index since the device page left at 7.8, 2026-10-17) reads it; v2 has no in-flight indicator on every page yet (C537's top bar) |
| Backups | (no route of today's; its six routes, backup_config, backup_history, backup_stats, compare_backups, delete_backup and download_backup, removed 2026-10-15, a8acc2a1) | **REMOVED 2026-10-15** (7.8, C632, C335) | Section 6a's prerequisite met first: the v2 intent editor and bulk intent render against the committed golden only since 2026-10-11 (C683), and today's template preview since 2026-10-14 (C632: its fallback to the newest backup, its "versus running config" diff and its refresh-capture route went). Today's device page's Backups tab, `modules/backups.py` and the manual's Backups page went with the routes. No code deleted or migrated the stored files; the operator archived them masked (`s3://mercury/archives/backups/20261015T040957Z.tar.gz`, lists/default's 2 files; no legacy folder existed) and deleted them by checksum with `scripts/host-steps/d16-archive.sh`, 2026-10-15. The follow-ups (the operator's decisions 6 to 9): retire no longer says backups are kept, onboarding's results name drift and heartbeats only, the legacy migration of a data-root backups folder is gone, and the concurrency audit marks the index REMOVED. A capture is the device's page's Capture…, recorded as a golden |
| Reload | (no route of today's; its /bulk_reload removed 2026-10-12) | BUILT, P.14; **WALKED 2026-10-17** (W2 steps 54 to 58 on r6: the preview ~00:05Z, every gate passing (C881 by the operator's eyes); the reload pressed ~00:06:47Z, its window declared before it until 00:27:47Z, answered after 452 s, "Reloaded and verified" ~00:14:26Z, the window closed at verify; the host key kept, C941. W1 section I had been refused by C881). Found there and open: C1025 (B3, the window silences nothing), C1026 (B4, no "Restarted as planned"), C1027 (B5, the reload record not committed) | Device Actions › Reload…: a preview job reads the device and judges the six gates (running against startup, its golden and intent, startup carrying Mercury's credential, the boot image, no holder, the blast radius from committed intent and this host's subnets); a reason; the run declares its planned-restart window before it sends anything, reloads, waits within the platform's measured bound, verifies it runs what it ran, and records (History's Reloads). P.14's plain form: the device boots the startup it holds; booting a moment from history is revert by reload (the charter's Phase 2) |
| Ask the device | (no route of today's; /run_command/<ip> removed 2026-10-17 with today's device page, restore tag `pre-remove/v1-device`) | **REMOVED 2026-10-17** (7.8, P7-22; under Removed at 7.8). **WALKED 2026-10-16** (W1 steps 2 to 4, C547 closed) | The device page's Ask tab (allowlisted, through the reads engine, `modules/nsot/reads.py`) |
| Topology service | (no route of today's; its two routes and panel removed 2026-10-12) | BUILT for boards A and B (P.11 steps 1 and 2, 2026-10-10); **the page WALKED 2026-10-16** (W2 steps 12 to 16, ~22:36Z to 22:41Z, the operator's PASS: the map at desktop and phone width, the path trace r1 to r3 delivered, snap to grid with rapid re-grabs one row per drop (C691 closed); its C findings C1033 to C1035); the service itself REMOVED at 7.8 (2026-10-12: the renderer from the repository, the unit and link by its host step, `topology-service-removal.sh`), and its integration with it (C714: no client, no probe, no Settings card; its keys `retiring` for one release) | OBSERVE › Topology (`routes/topology_v2.py` over the `topology-graph` reader): the layers, outside peers, islands (expected by a recorded declaration, or warned, and "became"), single points of failure, criticality, path trace, search, the list first at phone width. Saved shared positions are BUILT (C661: a layout saved for everyone on the network, each move recorded on History; snap to grid C691, its drag fixed by C882, walked in W2). Still to come: time travel and the wall (board C; its kiosk identity is the operator's) |
| AI agent | (no route of today's; its 26 routes under /ai/ removed 2026-10-14, tag `pre-remove/ai-family`) | **REMOVED 2026-10-14** (D15, decided 2026-10-05, after its stores were archived) | Stage 8 redesigns the agent as an on-call responder (docs/PHASE8_PLAN.md). The chat panel, the Agent, Approvals queue, Ansible and usage screens, v2's AI and workflow tab, the in-app SNMP trap and NetFlow receivers (`modules/snmp_collector.py`, `modules/netflow_collector.py`) and `modules/collector_config.py` went with it; the shared pieces stayed, moved out first (`modules/goldens.py`, `modules/bgp_summary.py`, `modules/drift_interval.py`). Today's drift panel stayed, in a tab named Drift, until it left at 7.8 (2026-10-15, under Removed at 7.8) |

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
  pipeline's render stage still imported (removed with that fallback on 2026-10-16, C765: no
  route, job or script ran the pipeline without a confirmed list), and the pipeline's audit files themselves (stage 9
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
  able to fail by moving that route's key (and `POST /remote/push` since auto-push left at
  7.8, 2026-10-17). Proved before removal: nothing outside the tab's
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
- **The sixteen routes no page reached** (the route-reachability test's whole allowlist,
  `KNOWN_UNREACHABLE`, now empty and its ceiling 0), 2026-10-15. Each was checked for a caller
  outside the tests (pages, v2 templates, scripts, modules, the lab) and had none; each has a
  v2 home or was superseded:
  - /templatize/committed (GET): Devices draws each device's intent state; the per-device
    read and edit (/templatize/committed/<host>) stay for today's editor. Its one helper only
    it used, `hostvars.list_staged`, went with it.
  - /templatize/rolled-back and /templatize/rolled-back/retries (GET): Needs attention draws
    the blocked devices from `rolled_back_notes`, which stays, and the device's History draws
    each retry (`history_sources`).
  - /templatize/bulk/preview and /apply (POST): Devices › Change a setting
    (`routes/bulk_intent_v2.py`) over the same `bulk_plan_of` and `bulk_apply_of`, which stay.
  - /templates/revoke/<path> and POST /templates/bindings: Templates › Revoke… and Bindings…
    (`routes/templates_v2.py`), over `approve_op.revoke` and `template_bindings`.
  - /templates/seed_status (GET): the Templates table's Against the shipped version column,
    and `scripts/nmas-seed-status` on the host; `templates_repo.seed_status` stays.
  - POST /templates/preview/<host>: the same read as its GET with a JSON body; the GET stays
    (today's template editor calls it).
  - /jobs/health (GET): Needs attention reads the job-health reader's stored rows, and
    `nmas-jobs` asks live on the host; `job_health.health()` stays.
  - POST /inventory/source/<list>: each network's Settings › Network tab, Inventory source
    (`modules/network_source.py`, previewed, confirmed and recorded); the GET stays.
  - /remote/adopt (POST): History › Remote set-up…'s Connect, over the same `remote.adopt`.
  - /bulk_clear/<id> (POST): on the audit's CUT list; `bulk_ops`' `clear_operation`, which
    only it called, went with it, and so did the `bulk_ops` invalidation key, which only it
    declared.
  - POST /drift/check (the async run): Check now is Settings › Installation › Diagnostics,
    and today's panel uses /drift/check/sync; the checker's `trigger` stays (Diagnostics calls
    it).
  - GET /drift/settings and GET /device_lists: duplicate reads; /drift/status and the
    server-rendered page carry the same. Their POST halves stay.

  Their gate, invalidation and operation-stage entries left with them. Tests that drove a
  property through one were rebased onto the core or the v2 route that does it now.
- **Today's bulk commands** (/bulk_execute, /bulk_status/<id>), 2026-10-15 (C548's home
  built; C798 moot): Show commands (`/v2/show-commands`) runs reads across devices, by name,
  role or network, from the same allowlist, results grouped and compared. The worker
  (`modules/bulk_ops.py`, whose finished runs nothing cleared, C798), today's device list's
  bulk panel (the command box, the selection checkboxes and Select all that fed it) and its
  results modal went with the routes, and so did their gate, invalidation and two
  operation-stage and history entries, and `readonly_commands.refusal_for`, which only
  /bulk_execute called (the allowlist itself, `refusal`, stays: `/run_command` and the reads
  engine use it). Proved before removal: index.1.js's `executeBulkCommand` and
  `showBulkResults` were the routes' only callers.
- **Restore Golden Config at HEAD** (`bulkRestoreGoldenConfig`, the bulk panel's button, and
  today's device page's Restore Golden Config link), 2026-10-15 (cut 2026-10-05): a device's
  Restore from…, whose first point is its golden now, and History's baselines remain. Both
  only opened the guarded preview through the index; that handoff (`_restoreHeadFromUrl` in
  `partials__golden_repo.3.js`, read from `?restore_head=&restore_ref=`) stays, because
  Restore from… (`nmas_restore_scope.js` `restoreFromUrl`) still sends the device there.
- **Today's Drift tab** (/drift/status, POST /drift/check/sync, POST /drift/settings),
  2026-10-15: Settings › Installation › Diagnostics, the Drift checks card (board F4), is
  their home: one schedule for every network, each network's Turn off or Turn on with who and
  when, and Check now; the results are Needs attention rows. The tab, its panel and
  `index.4.js`'s drift section went with the routes, and so did their gate, invalidation and
  operation-stage entries and the two helpers only they used (`drift_check.network_for`,
  `approval_queue.get_pending_count`). The checker (`modules/drift_check.py`,
  `modules/drift_interval.py`) is unchanged. Carried over first: Check now refuses a run
  another process holds, naming it (the card had refused only its own process's), the card
  says who holds a running check, and an unreadable network reads "unknown" and "paused",
  never "never". Needs attention's drift rows, which named "the Drift panel" with no link,
  now link the card. The manual's Check drift page left today's-app marking: v2's Check now
  carries its link. Proved before removal: index.4.js's `loadDriftStatus`,
  `saveDriftSettings` and `runDriftCheck` were the routes' only callers.
- **Today's Settings modal, Logs tab and status bar** (GET and POST /settings,
  /netbox/test_connection, /settings/integrations and its save, Test and general block,
  /identity/posture and /identity/posture/ratify, /logs/server, /health/version), 2026-10-15.
  Their homes: NetBox's connection is Settings › Installation › Connections' NetBox card,
  NetBox writes are turned on by an authorised NetBox confirm (C619) and off on that card;
  each network's integrations are Settings › Default and a network's own cards; Proxmox, the
  commit author and the server's bind and port are Installation's cards; the posture and
  Record this decision are Installation › Access and identity; the app's log is Installation ›
  Diagnostics; the running version is Help › About; integration health and who you are are
  every v2 page's top bar. The modal, its two partials (`settings_integrations.html`,
  `security_posture.html`) and their scripts, index.4.js's NetBox test, the Logs tab and its
  script, and the status bar (`static/js/nmas_status_bar.js`, base.html, so today's device page
  too) went with the routes, as did their gate, invalidation and operation-stage entries.
  `routes.health.version_facts()` stays (About draws it), and so do `/identity/status` and
  `/settings/integrations/status` (their rows above). Carried over first, each found by
  rebasing a removed path's property test onto v2: a card's Save writes only what the person
  changed and refuses a changed field another person moved since, naming both values
  (CONCURRENCY_AUDIT R17: v2's cards had resent every field as drawn); the NetBox card's Test
  names a token's missing views and NetBox's own reason (C468: it had asked `api/status/`
  only); the strip says STALE past its reader's promise and names the unconfigured on hover;
  the Monitoring profile card has its Test (it had none on v2). Not carried over:
  `auto_open_browser`, the desktop app's switch (not drawn on v2 by board F3; `NMAS_HEADLESS`
  and `NMAS_AUTO_OPEN_BROWSER` set it), and the retiring `collector_*`, `monitoring_*` and
  `promql_*` fields, read by nothing. Proved before removal: index.html's `openSettingsModal`,
  `saveSettings` and `loadLogsTab`, the two partials' scripts and the status bar were the
  routes' only callers; the updater, the host scripts and the monitoring configs call none.
- **Today's NetBox tab** (/netbox/status, and /netbox/safety/import/preview and /apply,
  /import_all/preview and /apply, /remove/preview and /apply, /progress/<op_id> and /removals),
  2026-10-17 (P7-20; restore point tag `pre-remove/v1-netbox`; CUTOVER's row walked and closed
  in W3). Its home is Source of truth › NetBox (`/v2/netbox`, `routes/netbox_v2.py`): each
  network's last import and its recorded removals, and Import into NetBox…, Import every
  network…, Remove from NetBox… and Stop tracking instead…, each a preview job and a confirm
  over `modules/netbox_ops.py`, which stays (the one core both had called). The tab's pane
  and button, its two partials (`netbox_safety_modal.html`, the import and removal dialog, and
  `netbox_removals.html`, the removals panel) and their scripts
  (`partials__netbox_safety_modal.1.js`, `nmas_netbox_removals.js`, which base.html loaded on
  both of today's pages), and index.4.js's NetBox section went with the routes, as did their
  gate, invalidation and operation-stage entries. Code whose only caller left with them:
  `netbox_ops.list_devices`'s active-list fallback (today's Import Current List; a write path
  carries its list), and the removal preview's wording for today's "Just stop tracking".
  Carried over first, found by rebasing the removed paths' tests onto v2: v2's result card
  drew a partial removal's "Not deleted" sentence and not the objects NetBox refused or its
  reason for each (C121's half: today's dialog drew them); the result component's parts now
  draw each item's lines, as the preview's What it does not do does. Proved before removal:
  index.4.js's `loadNetboxTab` and the `netbox*` handlers, the dialog's script and
  `nmas_netbox_removals.js` were the routes' only callers; no v2 template, host script,
  updater or monitoring config calls any of them (`scripts/nmas-verify-runbook` names
  /netbox/safety only in its history).
- **Today's device page** (/device/<ip>, its command box /run_command/<ip>, and its Changes
  tab's read /deploy/receipts), 2026-10-17 (P7-22; restore point tag `pre-remove/v1-device`;
  the device page walked in W1, its Ask tab with C547). Its home is the v2 device page
  (`/v2/device/<name>`): Actions holds every button the page had (Restore from…, Capture,
  Seed intent…, Revert intent…, Retry rolled-back change…, Rotate credential…, Persist,
  Retire…), the Ask tab reads through the reads engine from the same allowlist (a write
  refused before any device, the run recorded), and the History tab draws each deploy's and
  restore's receipt. The page (`templates/device.html`), its Changes partial
  (`partials/device_changes.html`) and that partial's script went with the routes, as did
  their gate, invalidation and operation-stage entries (run_command's four LEGACY stage gaps
  and its history gap). Code whose only caller left with them: `device.get_device_context`
  and `parse_file_systems` (the page's flash listing), app.py's session pool (`connections`,
  `lock`), which only /run_command used, and with it the inventory's sweep of that pool for a
  stale device's session; `preview_confirm.receipt_history` and `operation_result`'s
  read-back form (`from_receipt`). Today's device list's Manage now opens the device's v2
  page. **Kept, each with its caller:** the device-action JSON routes the page's buttons
  opened through base.html's scripts (/golden/capture/*, /templatize/seed/*, /revert/*,
  /retry/*, /persist/*, /rotate/*, /retire/*) and those scripts (`nmas_seed.js`,
  `nmas_persist.js`, `nmas_rotate.js`, `nmas_retire.js`, `nmas_intent_ops.js`,
  `nmas_capture.js`), P7-24's, with nothing on today's pages opening Seed, Persist, Rotate or
  Retire any more; and `nmas_restore_scope.js` with /golden/restore_points/<host>, whose one
  opener was the page's Restore from…, with the Restore, baselines row. Carried over first,
  found by rebasing the removed paths' tests onto v2: the History tab drew a receipt's reason,
  removed lines and authorised lines as stored, where /deploy/receipts had masked them again
  on the way out (`mask_payload`); `history_sources.receipts` now masks each. Not carried
  over: the receipt's verify checks (neighbours, routes and interfaces before and after),
  its save to startup and its rollback's remaining lines, which the Changes tab drew through
  the result component; v2's History draws the program's size and hash, whether it matched
  what was confirmed, the removals, the authorisations, the rollback's state and the commit.
  Proved before removal: index.html's device table (Manage) was the page's one link, the
  page's own form was /run_command's one caller, and its Changes partial was /deploy/receipts'
  one caller; no v2 template, host script, updater or monitoring config calls any of them.
- **Today's Git tab, its Remote card and its Baselines** (/git/status, /git/log,
  /git/commit/<sha>; /remote/status, /remote/verify-write, /remote/preview,
  /remote/acknowledge, /remote/auto-push; /golden/baselines, /golden/restore_points/<host>,
  /golden/restore/preview and /golden/restore/apply), 2026-10-17 (P7-21; restore point tag
  `pre-remove/v1-git`; CUTOVER's rows walked in W1 to W3, row 48 closed 2026-10-17). Their
  home is History: Commits and each commit's change, masked (today's commit view returned
  it unmasked); the header's sentence, what is not committed, Push now and Verify the remote
  (`POST /remote/push` and `POST /remote/verify`, which STAY: the header posts to them);
  Remote set-up… (connect, the write probe, what a first push publishes and its
  acknowledgement, automatic pushing); Baselines and Re-apply…; and each device's Restore
  from…. The tab's button, pane, commit dialog and inline script, `index.4.js` (its load on
  switch), the Remote card and the Baselines panel (`partials__golden_repo.2.js`, `.3.js`
  and the panel's rows in `.1.js`), the re-apply dialog, and `nmas_restore_scope.js` went
  with the routes, as did today's device page's Restore from…, which only sent the device
  to that dialog, and their gate, invalidation and operation-stage entries. Code whose only
  caller left with them: `config_git`'s log, diff, status and publication readers, and
  `golden._last_baseline_decision`. Kept: `partials/golden_repo.html`'s per-device timeline (today's
  device table's History; /golden/history, /version and /diff are row 46's), THE restore
  plan and `restore_points_for` (`routes/golden.py`, the v2 device page's and Re-apply's),
  `remote.verify` and `remote.push`. Carried over first, found by rebasing the removed
  paths' tests onto v2: Needs attention's remote rows sent a person to "the Remote card (the
  Devices tab, below the device list)", and the held clause to acknowledge "on the Remote
  card": both name History's header and Remote set-up… now, and link to History for the
  row's network; the set-up card lists each acknowledged secret by kind, fingerprint and
  devices, and says how and what the last push published (today's card drew both); and
  History's header named an uncommitted tracked path without its first letter
  (`olden/r1.cfg`: a fixed-column slice of stripped `git status` output, the defect
  `config_git.get_repo_status` had fixed), now parsed. Proved before removal: index.html's
  inline Git script and `index.4.js`, the two `golden_repo` scripts, the panel's rows and
  `nmas_restore_scope.js` were the routes' only callers; no v2 template, host script,
  updater or monitoring config calls any of them.
- **Today's network management, and the installation's active list frozen** (POST
  /device_lists, DELETE /device_lists/<name>, POST /select_device_list), 2026-10-17 (P7-26;
  restore point tag `pre-remove/v1-networks`; CUTOVER's row walked in W2 and W3). Their home:
  Settings' scope bar, Choose a network › New network…, and each network's Delete this
  network… (`modules/network_admin.py`), each previewed, confirmed and recorded; which network
  a person sees is their own choice, the top bar's Network ▾ (`routes/network_v2.py`). Today's
  index lost its list bar (the Device List select, + New List, Delete List), the New List
  dialog and their script (`index.1.js`'s list section); it says which network it shows, the
  installation's, in a line. Their gate, invalidation and operation-stage entries went with
  them, and so did `device.set_current_device_list`, whose only caller was the switch: the
  installation's `current_list` is FROZEN, set by nothing; it moves only when the network it
  names is deleted (`device.delete_device_list` moves it to the earliest-registered network
  left). Every
  reader of it is unchanged and reads that frozen value where it read the switched one: a v2
  request reads the network its address names, else its person's choice
  (`network_choice`), else this (History's Verify the remote and Push now, outside /v2/, are
  given the page's network in their address by `routes/page_network`); today's index, the
  host scripts given no list (`scripts/nsot_*.py`, `scripts/host-steps/c725-config-pipeline.sh`),
  the start-up template-secret migration, and today's routes when a page of today's sends no
  list (capture, deploy, persist, rotate, retire, seed, revert and retry previews, the template
  editor, onboarding's pending banner, the in-flight panel and `/attention`: P7-23 to P7-25 and
  P7-27, each the same list today's index shows) read it; no scheduled job does (each runs
  every network, C491; the drift checker's, the approval queue's and the pipeline's fallbacks
  to it are reached by no caller). Carried over first, found by rebasing
  the removed delete's tests onto v2: today's delete refused a network for which Mercury's
  record holds created NetBox objects, or whose record cannot be read (C155), and v2's had no
  such check; Delete this network… now refuses both, in the preview and again at the confirm,
  naming the objects, and drops the network's empty entry. Proved before removal:
  `index.1.js`'s list section was the three routes' only caller, and the switch
  `set_current_device_list`'s; no v2 template, host script, updater or monitoring config
  calls any of them (`docs/STAGE4C_PROBE.md`, a dated probe runbook, names `/device_lists`
  for a probe network: a probe now creates its network on Settings).

## Legacy actions that are not routes

| Action | Status | Home or reason |
|---|---|---|
| The terminal (socket events) | **REMOVED 2026-10-05** (R39, brought forward from 7.8 on the operator's decision, after the console drill proved the emergency path: docs/CONSOLE_DRILL.md) | The Device page's allowlisted Ask tab is the one way to ask a device. Kept: the `break_glass` gate kind and its two settings, until they retire |
| Today's Git tab, Remote card, Baselines panel | **REMOVED 2026-10-17** (7.8, P7-21; under Removed at 7.8) | History: Commits, the remote's sentence and its header's Push now and Verify, Remote set-up…, Baselines and Re-apply… |
| The AI chat panel (every page) | **REMOVED 2026-10-14** (D15, with the AI family; the "AI agent" row above) | Stage 8 redesigns it (docs/PHASE8_PLAN.md) |

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
