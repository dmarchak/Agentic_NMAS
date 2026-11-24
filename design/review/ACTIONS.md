# Slow actions inventory (GUI usability review)

Every v2 action likely to take over about 1 second: it reaches a device, NetBox, Grafana, Loki,
Prometheus, Kea, an SDN controller, git (a commit, a push, a fetch), an AI call, a mail or webhook
send, a background job, or the updater. Read from the code on 2026-11-23. Nothing was run.

## How these rows were found

- **Scanned in `templates/v2/` (301 templates):** 304 `hx-post` attributes (284 distinct targets:
  272 resolve to a route by `url_for`, 12 are template variables, each resolved by hand), 523
  `hx-get` (250 distinct targets), 41 plain `<form action=>` and 5 `formaction=`.
- **Scanned in `static/js/nmas_*.js` (14 scripts):** 13 `fetch(` call sites. 9 of them post to a
  route a person presses (IP SLA and heartbeat, break-glass export, remote verify and push, update
  check, acknowledge). The rest are reads or diagnostics.
- **Routes:** 558 `@bp.route` functions parsed in `routes/*.py`. Each one's body, and the module
  functions it calls up to five levels deep, was searched for device access (`open_ssh`,
  `fanout`, connection helpers), NetBox (`netbox_client`, `_nb_*`), Kea, Loki, Grafana and
  Prometheus integrations, SDN drivers, git (`repo.commit`, `.push(`, `subprocess`), the AI
  gateway, and job starts (`capture_job.start`, `deploy_job.start`, threads). The scan only
  produced hints. Each row below was then judged from its route, its module and its busy words.
  `tests/test_no_page_waits.py` (`NOT_YET_CONVERTED`, `PRESSES`) was used for GETs that still
  wait on a source.
- **Judged slow:** 220 rows (182 POSTs, 38 GETs a person presses or a tab opens). 23 of them
  had no feedback on 2026-11-23 ("none" or "page load"). **Corrected 2026-11-24 (C4216):** the
  device Actions menu's four rows were busy already (C399's spinner on the menu row, read from
  the stylesheet); the tabs and the DHCP, SDN and NetBox links are now busy on themselves (one
  stylesheet rule for every pressed `hx-get` link or button, tests/test_v2_gets_busy_on_itself.py),
  and so is a press that loads another page, until that page replaces it (nmas_v2.js
  `markNavigating`). The panel and the console offer said so in place already. Not listed: posts that only
  write a local store or a setting (toggles, saved views, positions, display names, AI feedback,
  heal marks and lifts, acknowledge), and pages drawn from data the background already holds.

## Legend (Feedback column)

| Term | Meaning |
|---|---|
| **busy** | Busy on the control: the button is disabled and gets `htmx-request` and `aria-busy`, and its `op-busy` words replace `op-idle` until the answer is drawn (`nmas_v2.js` `holdSubmitter` for form submitters; htmx itself for a button that posts; Alpine `busy` for scripted posts). |
| **in-place** | The answer is swapped into the card or region the control is on (`hx-target`). |
| **stepper (live)** | THE stepper (`templates/v2/_run_stepper.html`, `run_stepper`), on a job card that redraws itself on the job's announcements. |
| **stepper (after)** | The same macro, drawn once in the finished result. There is no live progress while the request is in flight. |
| **compact stepper** | The incident card's stepper (`templates/v2/_inc_step.html`), redrawn on `nmas:ai_step` / `device_progress` / `in_progress`. |
| **live card** | A job card that redraws on `nmas:<key>` announcements, with its own progress words but no stepper. |
| **page load** | A plain form or link that navigates the browser. The only feedback is the browser's own loading. |
| **none** | No busy state on the control and no progress (for example, an action-menu link without `op-busy` words: the menu stays open until the answer arrives). |
| **unverified** | Could not be told from the code read. |

Routes are given as `METHOD /url` and `routes/<file>:<function>`.

## Device

| Where | Route | What it does | Feedback today | Steps a person would want |
|---|---|---|---|---|
| Device › Actions, Plan a deploy… (also Remove lines (Mode B)…) | `GET /v2/device/<name>/deploy` · `device_v2.py:deploy` | Renders intent, diffs against the golden, builds the program ("local but slow") | busy on the menu row (C399's spinner); the re-plan form has no busy | Render intent · Compare golden · Build program · Ready to confirm |
| Device › Deploy card, Deploy (confirm) | `POST /v2/device/<name>/deploy/confirm` · `device_v2.py:deploy_confirm` | Recomputes the program, starts the deploy job (9-stage pipeline) | busy · in-place · stepper (live) | Recompute · Hold device · Send · Verify · Record |
| Device › Deploy card, Draft change record | `POST /v2/device/<name>/deploy/change-record` · `device_v2.py:deploy_change_record` | AI drafts the change record | busy · in-place | Gather facts · Ask AI · Draft ready |
| Device › Capture, Start | `POST /v2/device/<name>/capture/start` · `device_v2.py:capture_start` | Starts the capture-preview job (reads the running config) | busy · stepper (live) | Connect · Read config · Parse · Preview |
| Device › Capture, Record | `POST /v2/device/<name>/capture/confirm` · `device_v2.py:capture_confirm` | Reads the device again and commits the golden | busy · in-place · stepper (after) | Read again · Compare · Commit golden · Done |
| Device › Save…, Read the effect | `POST /v2/device/<name>/persist/read` · `device_v2.py:persist_read` | Job reading what a save would change | busy · live card | Connect · Read running · Read startup · Compare |
| Device › Save…, Save | `POST /v2/device/<name>/persist/confirm` · `device_v2.py:persist_confirm` | write memory on the device, then reads it back | busy · in-place · stepper (after) | Hold · Save · Read back · Record |
| Device › Actions, Re-key… | `GET /v2/device/<name>/rekey` · `device_v2.py:rekey` | Reads the device's SSH host key live | busy on the menu row (C399's spinner) | Connect · Read host key · Compare |
| Device › Re-key, Keep the new key | `POST /v2/device/<name>/rekey/confirm` · `device_v2.py:rekey_confirm` | Reads the key again and records it | busy · in-place | Read key · Match preview · Keep |
| Device › Reload…, Preview | `POST /v2/device/<name>/reload/start` · `device_v2.py:reload_start` | Starts the reload preview (reads the device) | busy · in-place · live card | Connect · Read state · Plan window |
| Device › Reload, Reload (confirm) | `POST /v2/device/<name>/reload/confirm` · `device_v2.py:reload_confirm` | Declares the window, reloads, waits, verifies | busy · in-place · stepper (live) | Declare window · Reload · Wait for return · Verify |
| Device › Reload, Verify again | `POST /v2/device/<name>/reload/verify` · `device_v2.py:reload_verify` | Job re-verifying after a reload | busy · stepper (live) | Connect · Read · Verify |
| Device › Rotate credential, Preview | `POST /v2/device/<name>/rotate/preview` · `device_v2.py:rotate_preview` | Plans the rotation (reads the device) | busy · in-place | Connect · Read accounts · Plan |
| Device › Rotate, Rotate (confirm) | `POST /v2/device/<name>/rotate/confirm` · `device_v2.py:rotate_confirm` | Job: sends the new credential and proves it | busy · in-place · stepper (live) | Read again · Send · Log in with new · Record |
| Device › Restore, choose a version | `GET /v2/device/<name>/restore/preview` · `device_v2.py:restore_preview` | Plans the restore program (local; unverified slow) | busy (form button) · in-place | Load version · Compare · Build program |
| Device › Restore, Restore (confirm) | `POST /v2/device/<name>/restore/confirm` · `device_v2.py:restore_confirm` | Deploy job restoring a golden | busy · in-place · stepper (live) | Recompute · Hold · Send · Verify · Record |
| Device › Actions, Retire… | `GET /v2/device/<name>/retire` · `device_v2.py:retire` | Preview reads NetBox and Kea live | busy on the menu row (C399's spinner); busy on the re-plan form | Read NetBox · Read Kea · List artefacts |
| Device › Retire, Retire (confirm) | `POST /v2/device/<name>/retire/confirm` · `device_v2.py:retire_confirm` | Removes per-device artefacts (NetBox, Kea, Prometheus targets, git) | busy · in-place · stepper (after) | Plan again · NetBox · DHCP · Monitoring · Archive files |
| Device › Seed intent, Commit | `POST /v2/device/<name>/seed/confirm` · `device_v2.py:seed_confirm` | Parses the golden and commits intent | busy · in-place | Parse golden · Write intent · Commit |
| Device › Revert, Commit | `POST /v2/device/<name>/revert/confirm` · `device_v2.py:revert_confirm` | Computes a revert of intent and commits it | busy · in-place | Compute revert · Commit · Ready to deploy |
| Device › Retry, Record | `POST /v2/device/<name>/retry/confirm` · `device_v2.py:retry_confirm` | Reads the block again and records a retry | busy · in-place | Read block · Record |
| Device › Drift, Check now | `POST /v2/device/<name>/drift/check/now` · `device_v2.py:drift_check_now` | Reads the device and compares it with the golden | busy · in-place | Connect · Read config · Compare · Result |
| Device › Diagnose, Run | `POST /v2/device/<name>/diagnose/run` · `device_v2.py:diagnose_run` | Starts the diagnosis job (device reads) | busy · in-place · live card | Reach · Read interfaces · Read neighbours · Verdict |
| Device › History, Reveal | `POST /v2/device/<name>/golden/reveal` · `device_v2.py:golden_reveal` | Reads a golden from git and records the reveal (unverified slow) | busy · in-place | Read commit · Record reveal |
| Device › Actions, Privileged… | `GET /v2/device/<name>/privileged` · `privileged_v2.py:privileged` | Opens the privileged-read card (plan) | busy on the menu row (C399's spinner) | Plan · Ready |
| Device › Privileged, Start the read | `POST /v2/device/<name>/privileged/preview` · `privileged_v2.py:preview` | Job: runs the read before the send | busy · in-place · live card | Connect · Read · Preview |
| Device › Privileged, Send | `POST /v2/device/<name>/privileged/confirm` · `privileged_v2.py:confirm` | Job: sends the privileged commands | busy · in-place · live card | Hold · Send · Read back · Record |
| Device › Ask, Run | `POST /v2/device/<name>/ask` · `reads_v2.py:ask_run` | Starts an allowlisted read on the device | busy · in-place · live card | Check command · Connect · Read · Answer |
| Device › Re-subscribe, open | `GET /v2/device/<name>/resubscribe` · `resubscribe_v2.py:preview` | Plans the telemetry re-subscribe | busy (its button); none when opened by a toggle | Read sources · Plan |
| Device › Re-subscribe, Confirm | `POST /v2/device/<name>/resubscribe/confirm` · `resubscribe_v2.py:confirm` | Job re-subscribing telemetry | busy · in-place · stepper (live) | Hold · Remove · Re-add · Verify stream |
| Device › Re-subscribe, Close collector session | `POST /v2/device/<name>/resubscribe/close` · `resubscribe_v2.py:close_confirm` | Job closing the stuck session | busy · in-place · stepper (live) | Hold · Close · Verify |
| Device › Re-subscribe, Re-add | `POST /v2/device/<name>/resubscribe/readd` · `resubscribe_v2.py:readd` | Job re-adding the subscription | busy · in-place · stepper (live) | Hold · Re-add · Verify stream |
| Device › Intent, Check | `POST /v2/device/<name>/intent/check` · `intent_v2.py:check` | Renders the edited intent (unverified slow) | busy · in-place | Parse · Render · Diff |
| Device › Intent, Commit | `POST /v2/device/<name>/intent/commit` · `intent_v2.py:commit` | Commits the intent edit to git | busy · in-place | Check again · Commit · Publish |
| Device › Intent, Draft from words | `POST /v2/device/<name>/intent/words` · `intent_v2.py:words` | AI drafts an intent change from text | busy · in-place | Ask AI · Draft · Check |
| Device › Intent, Commit the draft | `POST /v2/device/<name>/intent/words/commit` · `intent_v2.py:words_commit` | Commits the AI draft | busy · in-place | Check · Commit |
| Device › Intent secrets, Store | `POST /v2/device/<name>/intent/secrets/set` · `intent_v2.py:secrets_set` | Stores a secret value (unverified slow) | busy · in-place | Encrypt · Store |
| Device › Overview tab | `GET /v2/device/<name>/overview` · `device_v2.py:overview` | git log and intent render (in `NOT_YET_CONVERTED`) | busy on the tab (C4216's spinner) | Read history · Render |
| Device › NetBox tab | `GET /v2/device/<name>/netbox` · `device_v2.py:netbox` | Three NetBox reads | busy on the tab (C4216's spinner) | Read NetBox · Compare |
| Device › Monitoring tab | `GET /v2/device/<name>/monitoring` · `device_v2.py:monitoring` | Grafana dashboard variables | busy on the tab (C4216's spinner) | Read dashboard · Draw panels |
| Device › Monitoring, a panel | `GET /v2/device/<name>/panel/<uid>/<panel_id>` · `device_v2.py:panel` | Grafana panel data | in-place words while it loads ("Reading from Grafana…") | Query · Draw |
| Device › History tab | `GET /v2/device/<name>/history` · `device_v2.py:history` | git log and about 50 stores | busy on the tab (C4216's spinner) | Read git · Read records · Merge |
| Device › Saved actions, Run | `POST /v2/saved-plans/device/<device>/run` · `saved_plans_v2.py:device_run` | Runs a saved fix on a port (job) | busy · in-place · live card | Preview · Hold · Send · Verify |

## Fleet / devices list

| Where | Route | What it does | Feedback today | Steps a person would want |
|---|---|---|---|---|
| Devices › ticked, Save… | `GET /v2/devices/save` · `v2.py:save` | Plans Save All for the ticked devices | page load; busy on the pressed control until the page replaces it (C4216) | Plan · Ready |
| Devices › Save, Save N devices | `POST /v2/devices/save/confirm` · `v2.py:save_confirm` | Job: write memory and capture golden, per device | busy · in-place · stepper (live) | Plan again · Save · Read back · Commit |
| Devices › ticked, Deploy… | `GET /v2/devices/deploy` · `v2.py:devices_deploy` | Plans a fleet deploy ("local but slow") | page load; busy on the pressed control until the page replaces it (C4216) | Render each · Compare · Order · Ready |
| Devices › ticked, Change across… | `GET /v2/intent/change` · `intent_layers_v2.py:change` | Opens the fleet change form | page load; busy on the pressed control until the page replaces it (C4216) | Load layers · Ready |
| Fleet change, Plan | `POST /v2/intent/change/plan` · `intent_layers_v2.py:change_plan` | Job planning the change on each device | busy · live card | Render each · Diff · Plan |
| Fleet change, Approve and run | `POST /v2/intent/change/approve` · `intent_layers_v2.py:change_approve` | Commits and starts the run | busy · in-place · live card | Commit · Canary · Waves · Verify |
| Fleet change, Go on | `POST /v2/intent/change/go-on` · `intent_layers_v2.py:change_go_on` | Continues after the canary | busy · live card | Next wave · Verify · Done |
| Show commands, Run | `POST /v2/show-commands/run` · `reads_v2.py:show_commands_run` | Starts reads across devices | busy · in-place · live card with `run_summary` | Check · Connect each · Read · Group |
| Show commands, Test the logging path | `POST /v2/show-commands/logging-path` · `reads_v2.py:logging_path_run` | Sends a log line and looks for it in Loki | busy · in-place · live card with `run_summary` | Send line · Wait · Ask Loki · Result |
| Topology, Trace a path | `POST /v2/topology/path` · `topology_v2.py:path_run` | Starts a path-trace job (device reads) | busy · in-place · live card | Read routes · Hop by hop · Draw path |

## Onboarding (including NetBox import and Adopt)

| Where | Route | What it does | Feedback today | Steps a person would want |
|---|---|---|---|---|
| Onboard › Add, Review | `POST /v2/onboard/preview` · `onboard_v2.py:preview` | Plans the onboarding (NetBox and Kea reads) | busy · in-place | Check name · Read NetBox · Read DHCP · Plan |
| Onboard › Add, Create | `POST /v2/onboard/create` · `onboard_v2.py:create` | Creates the device in NetBox and the reservation in Kea | busy · in-place | NetBox device · Address · Reservation · Intent |
| Onboard › Add, console offer (on load) | `GET /v2/onboard/console/offer` · `console_ztp_v2.py:offer_view` | Reads NetBox's console path | in-place words while it loads ("Reading NetBox's console path…", aria-busy) | Read console path |
| Onboard › Add, out-of-band source | `GET /v2/onboard/oob/source` · `oob_onboard_v2.py:source_view` | Reads the planned device from NetBox | busy (select) · in-place | Read NetBox · Eligibility |
| Onboard › Pending device, Verify (preview) | `POST /v2/onboard/<name>/verify/preview` · `onboard_v2.py:verify_preview` | Reaches the device with its staged credential | busy · in-place | Reach · Log in · Read · Fingerprint |
| Onboard › Pending device, Verify | `POST /v2/onboard/<name>/verify` · `onboard_v2.py:verify` | Phase two: reads, compares intent, commits | busy · in-place · stepper (after) | Reach · Read · Match intent · Commit |
| Onboard › Pending device, progress | `GET /v2/device/<name>/pending/progress` · `device_v2.py:pending_progress` | The pending stage, from Kea | stepper (live) | Lease · First boot · Reachable · Verified |
| Onboard › Pending, Abandon… | `POST /v2/onboard/<name>/abandon/preview` · `onboard_v2.py:abandon_preview` | Dry run of removal (NetBox, Kea, git) | busy · in-place | NetBox · DHCP · Files |
| Onboard › Pending, Abandon | `POST /v2/onboard/<name>/abandon` · `onboard_v2.py:abandon` | Removes what onboarding created | busy · in-place | NetBox · DHCP · Files · Done |
| Onboard › Pending, Get the bootstrap config | `POST /v2/onboard/<name>/bootstrap` · `onboard_v2.py:bootstrap` | Renders and reveals the bootstrap config (unverified slow) | busy · in-place | Render · Record reveal |
| Onboard › Out-of-band, Review | `POST /v2/onboard/oob/preview` · `oob_onboard_v2.py:preview_view` | Reads NetBox for the console plan | busy · in-place | Read NetBox · Plan |
| Onboard › Out-of-band, Start | `POST /v2/onboard/oob/confirm` · `oob_onboard_v2.py:confirm` | Job over the console server | busy · in-place · stepper (live) | Console · Bootstrap · Settle · Reach · Verify |
| NetBox › Import, Preview | `POST /v2/netbox/preview` · `netbox_v2.py:preview` | Job reading NetBox (dry run) | busy · in-place · stepper (live) | Read NetBox · Compare · Plan |
| NetBox › Import, Import | `POST /v2/netbox/job/<job_id>/confirm` · `netbox_v2.py:confirm` | Import job | busy · in-place · stepper (live) | Read again · Write list · Done |
| NetBox › removals link | `GET /v2/netbox/removals` · `netbox_v2.py:removals` | Reads recorded removals | busy on the link (C4216's spinner) | Read record |
| Devices › Adopt, Review | `POST /v2/adopt/preview` · `adopt_v2.py:preview` | Plans the adoption (reads) | busy · in-place | Reach · Read · Plan |
| Devices › Adopt, Adopt | `POST /v2/adopt/confirm` · `adopt_v2.py:confirm` | Adoption job | busy · in-place · stepper (live) | Read · Capture golden · Intent · Commit |

## Templates / Intent

| Where | Route | What it does | Feedback today | Steps a person would want |
|---|---|---|---|---|
| Templates, Approve… | `GET /v2/templates/approve` · `templates_v2.py:check` | Approve's preview, `approve_op.check` ("local but slow") | busy · in-place | Import closure · Render · Ready |
| Templates, Approve | `POST /v2/templates/approve` · `templates_v2.py:approve` | Records the approval in git | busy · in-place | Check again · Commit |
| Templates, Revoke | `POST /v2/templates/revoke` · `templates_v2.py:revoke` | Revokes the approval in git | busy · in-place | Commit |
| Templates, Seed | `POST /v2/templates/seed` · `templates_v2.py:seed` | Commits the seeded library | busy · in-place | Copy · Commit |
| Templates, Bring | `POST /v2/templates/bring` · `templates_v2.py:bring` | Commits brought templates | busy · in-place | Measure · Commit |
| Templates, Bindings preview | `POST /v2/templates/bindings/preview` · `templates_v2.py:bindings_preview` | Checks bindings against devices | busy · in-place | Match devices · Preview |
| Templates, Bindings commit | `POST /v2/templates/bindings` · `templates_v2.py:bindings_apply` | Commits bindings | busy · in-place | Check · Commit |
| Templates › Edit, Check | `POST /v2/templates/edit/check` · `templates_v2.py:edit_check` | Renders the edit (unverified slow) | busy · in-place | Parse · Render |
| Templates › Edit, Commit | `POST /v2/templates/edit` · `templates_v2.py:edit_commit` | Commits the template edit | busy · in-place | Check · Commit |
| Templates, Coverage check | `POST /v2/templates/coverage` · `templates_v2.py:coverage_check` | Job comparing renders with goldens | busy · in-place · live card | Render each · Compare · Summary |

## Fixes / Heal / Incidents

| Where | Route | What it does | Feedback today | Steps a person would want |
|---|---|---|---|---|
| Incident › Fix it, Investigate | `POST /v2/incident/<id>/fixit/start` · `fixit_v2.py:start` | Starts the AI troubleshooting job | busy · in-place · compact stepper | Gather evidence · Read device · Ask AI · Propose |
| Incident › Fix it, Ask again | `POST /v2/incident/<id>/fixit/ask_again` · `fixit_v2.py:ask_again` | New AI investigation | busy · in-place · compact stepper | Gather · Ask AI · Propose |
| Incident › Fix it, Modify | `POST /v2/incident/<id>/fixit/modify` · `fixit_v2.py:modify` | AI revises the proposal | busy · in-place · compact stepper | Ask AI · Revise |
| Incident › Fix it, Deny | `POST /v2/incident/<id>/fixit/deny` · `fixit_v2.py:deny` | Records a denial (AI marker; unverified slow) | busy · in-place | Record |
| Incident › Fix it, Approve | `POST /v2/incident/<id>/fixit/approve` · `fixit_v2.py:approve` | Preflight and start of the approved plan | busy · in-place · compact stepper | Preflight · Hold · Send · Verify |
| Incident / Fix page, Run the fix | `POST /v2/incident/<id>/fixit/script` · `fixit_v2.py:fix_with_script` | Runs a saved fix script (job) | busy · in-place · compact stepper | Preview · Hold · Send · Verify |
| Incident › Hand over, Keep and send | `POST /v2/incident/<id>/fixit/handover` · `fixit_v2.py:handover` | Writes the handover and sends it to teams | busy · in-place | Draft · Send · Done |
| Incident › Hand over, Send | `POST /v2/incident/<id>/fixit/handover/<v>/send` · `fixit_v2.py:handover_send` | Sends the handover (mail or webhook) | busy · in-place | Send · Delivered |
| Assistant › Plan, open | `GET /v2/plans/preview` · `plans_v2.py:preview` | Plan preview | busy · in-place | Bind rows · Preview |
| Assistant › Plan, Approve | `POST /v2/plans/approve` · `plans_v2.py:approve` | Runs the approved plan (job) | busy · in-place · compact stepper | Preflight · Each step · Verify |
| Needs attention › Heal proposal, Approve | `POST /v2/network/<n>/heal/proposal/<d>/approve` · `heal_proposal_v2.py:approve` | Starts the heal act as a job | busy · in-place; its run shows a stepper (live) on its heal run card | Detect · Decide · Apply · Verify · Record |
| Control strip, Self-healing on/off | `POST /v2/control/<n>/heal` · `control_v2.py:heal` | Turns Auto on and may start a heal batch | busy · in-place · stepper (live) on the strip | Turn on · Batch · Each device · Verify |
| Needs attention, Run the check again | `POST /v2/attention/recheck` · `v2.py:attention_recheck` | Runs the row's reader once on its thread | busy · in-place (202 busy until the value is assembled) | Run reader · Assemble · Row redrawn |
| Saved plans, Promote | `POST /v2/saved-plans/<i>/promote` · `saved_plans_v2.py:promote` | Promotes and schedules a run (unverified slow) | busy · in-place | Save · Schedule |
| Saved plans, Save script | `POST /v2/saved-plans/<i>/save-script` · `saved_plans_v2.py:save_script` | Saves the script, may run it soon (unverified) | busy · in-place | Save · Schedule |
| Fix page, Automatic | `POST /v2/fixes/<key>/automatic` · `fixes_v2.py:automatic` | Turns the fix automatic, runs pending soon (unverified) | busy · in-place | Save · Schedule |
| Fixes › New / Edit, Save | `POST /v2/fixes/new`, `/v2/fixes/<key>/edit` · `fixes_v2.py:new_save`, `edit_save` | Commits the fix (git) | busy · in-place | Check · Commit |

## SDN

| Where | Route | What it does | Feedback today | Steps a person would want |
|---|---|---|---|---|
| SDN, Read capabilities | `POST /v2/sdn/capabilities/read` · `sdn_v2.py:capabilities_read` | Asks the controller what it supports | busy · in-place | Connect · Read · Draw |
| SDN, Test a controller | `POST /v2/sdn/controller/<name>/test` · `sdn_v2.py:controller_test` | Tests the saved connection | busy · in-place | Connect · Authenticate · Answer |
| SDN › Flows, Preview | `POST /v2/sdn/flow/preview` · `sdn_v2.py:flow_preview` | Plans a flow change (controller read) | busy · in-place | Read switch · Plan · Ready |
| SDN › Flows, Send | `POST /v2/sdn/flow/confirm` · `sdn_v2.py:flow_confirm` | Sends the flow to the controller | busy · in-place | Send · Read back · Record |
| SDN, Re-apply preview | `POST /v2/sdn/reapply/preview` · `sdn_v2.py:reapply_preview` | Reads the switch for a re-apply | busy · in-place | Read switch · Diff |
| SDN, Re-apply send | `POST /v2/sdn/reapply/confirm` · `sdn_v2.py:reapply_confirm` | Re-sends flows | busy · in-place | Send · Read back |
| SDN › Responses, Preview | `POST /v2/sdn/response/<rid>/preview` · `sdn_v2.py:response_preview` | Reads the switch for a threat response | busy · in-place | Read switch · Plan |
| SDN › Responses, Send | `POST /v2/sdn/response/confirm` · `sdn_v2.py:response_confirm` | Sends the response flow | busy · in-place | Send · Read back · Log |
| SDN › Responses, Classify again | `POST /v2/sdn/response/<rid>/classify` · `sdn_v2.py:response_classify` | AI classifies the threat | busy · in-place | Gather · Ask AI · Class |
| SDN › Watch, Tripwire | `POST /v2/sdn/watch/<wid>/tripwire` · `sdn_v2.py:watch_tripwire` | Plans a tripwire flow (reads) | busy · in-place | Read switch · Plan |
| SDN › Watch, Propose | `POST /v2/sdn/watch/<wid>/propose` · `sdn_v2.py:watch_propose` | Proposes a response from a watch (unverified slow) | busy · in-place | Read · Propose |
| SDN › Links, Verify | `POST /v2/sdn/link/<lid>/verify` · `sdn_v2.py:link_verify` | Traces the link now | busy · in-place | Trace · Compare · Result |
| SDN, Loop start/stop | `POST /v2/sdn/loop` · `sdn_v2.py:loop_set` | Starts or stops the closed loop | busy · in-place | Start · First pass |
| SDN, Mode on/off | `POST /v2/sdn/mode` · `sdn_v2.py:mode_set` | Turns SDN mode on or off (unverified slow) | busy · in-place | Switch · Confirm state |
| SDN › Export to NSoT, Preview | `POST /v2/sdn/export/preview` · `sdn_v2.py:export_preview` | Reads NetBox for the export | busy · in-place | Read NetBox · Diff |
| SDN › Export, Commit | `POST /v2/sdn/export/confirm` · `sdn_v2.py:export_confirm` | Writes NetBox and commits | busy · in-place | NetBox · Commit |
| SDN › Apps, Preview a deploy | `POST /v2/sdn/apps/preview` · `sdn_v2.py:apps_preview` | Reads the controller and app sources | busy · in-place | Read controller · Read app · Plan |
| SDN › Apps, Deploy | `POST /v2/sdn/apps/confirm` · `sdn_v2.py:apps_confirm` | App deploy job | busy · in-place · stepper (live) | Upload · Start · Health · Done |
| SDN › Apps, Add a draft (preview) | `POST /v2/sdn/apps/draft/preview` · `sdn_v2.py:apps_draft_preview` | Reads the app repository | busy · in-place | Read repo · Check files |
| SDN › Apps, Add a draft (commit) | `POST /v2/sdn/apps/draft/confirm` · `sdn_v2.py:apps_draft_confirm` | Commits and pushes the draft | busy · in-place | Write files · Commit · Push |
| SDN › Apps, Publish preview | `POST /v2/sdn/apps/version/publish/preview` · `sdn_v2.py:apps_publish_preview` | Reads the version to publish | busy · in-place | Read version · Check |
| SDN › Apps, Publish | `POST /v2/sdn/apps/version/publish/confirm` · `sdn_v2.py:apps_publish_confirm` | Publishes the version | busy · in-place | Tag · Publish |
| SDN › Apps, Run its tests | `POST /v2/sdn/apps/version/test` · `sdn_v2.py:apps_version_test` | Runs the app's tests | busy · in-place | Check out · Run tests · Result |
| SDN › Switches, filter | `GET /v2/sdn/switches` · `sdn_switches_v2.py:page` | Reads the switches | busy · in-place | Read switches · Draw |
| SDN › Switches, Configure preview | `POST /v2/sdn/switches/configure/preview` · `sdn_switches_v2.py:configure_preview` | Reads the switch for OpenFlow config | busy · in-place | Read switch · Plan |
| SDN › Switches, Configure | `POST /v2/sdn/switches/configure/confirm` · `sdn_switches_v2.py:configure_confirm` | Configures OpenFlow on the switch | busy · in-place | Hold · Send · Verify |
| SDN › Switches, Template preview | `POST /v2/sdn/switches/template/preview` · `sdn_switches_v2.py:template_preview` | Plans the template | busy · in-place | Render · Diff |
| SDN › Switches, Template commit | `POST /v2/sdn/switches/template/confirm` · `sdn_switches_v2.py:template_confirm` | Commits the template | busy · in-place | Commit |
| SDN › Switches, Verify | `POST /v2/sdn/switches/verify` · `sdn_switches_v2.py:verify` | Asks the reader to run now | busy · in-place | Run reader · Redraw |
| SDN › DHCP steering, Edit settings… | `GET /v2/sdn/dhcp/settings` · `sdn_dhcp_v2.py:settings` | Reads the switches | busy on the link (C4216's spinner) | Read switches |
| SDN › DHCP steering, Preview | `POST /v2/sdn/dhcp/preview` · `sdn_dhcp_v2.py:preview` | Reads the switches for steering | busy · in-place | Read switches · Plan |
| SDN › DHCP steering, Steer | `POST /v2/sdn/dhcp/confirm` · `sdn_dhcp_v2.py:confirm` | Sends the steering flows | busy · in-place | Send · Read back |
| SDN › DHCP steering, Remove preview | `POST /v2/sdn/dhcp/remove/preview` · `sdn_dhcp_v2.py:remove_preview` | Reads the switches | busy · in-place | Read switches · Plan |
| SDN › DHCP steering, Remove | `POST /v2/sdn/dhcp/remove/confirm` · `sdn_dhcp_v2.py:remove_confirm` | Removes the steering flows | busy · in-place | Remove · Read back |
| SDN › Policies, Draft | `POST /v2/sdn/policies/draft` · `sdn_policies_v2.py:draft` | AI drafts a policy from words | busy · in-place | Ask AI · Draft · Check |
| SDN › Policies, Check | `POST /v2/sdn/policies/check` · `sdn_policies_v2.py:check` | Checks the policy against the network | busy · in-place | Read · Check |
| SDN › Policies, Preview | `POST /v2/sdn/policies/preview` · `sdn_policies_v2.py:preview` | Plans the flows | busy · in-place | Read switches · Plan |
| SDN › Policies, Send | `POST /v2/sdn/policies/confirm` · `sdn_policies_v2.py:confirm` | Sends the policy's flows | busy · in-place | Send · Read back · Record |
| SDN › Analyse, Ask | `POST /v2/sdn/analyse/ask` · `sdn_analyse_v2.py:ask` | AI analysis of a snapshot | busy · in-place | Snapshot · Ask AI · Check answer |
| SDN › Analyse, Ask with tools | `POST /v2/sdn/analyse/ask-tools` · `sdn_analyse_v2.py:ask_tools` | AI analysis with tool calls | busy · in-place | Ask AI · Tool calls · Answer |
| SDN › Analyse, Collect | `POST /v2/sdn/analyse/collect` · `sdn_analyse_v2.py:collect` | Starts a collection job | busy · in-place | Connect · Collect · Seal snapshot |

## DHCP / ZTP

| Where | Route | What it does | Feedback today | Steps a person would want |
|---|---|---|---|---|
| DHCP, Add a reservation… / Edit | `GET /v2/dhcp/reservation` · `dhcp_v2.py:reservation_preview` | Preview reads Kea live | busy on the link (C4216's spinner); busy on the form's re-ask | Ask Kea · Plan |
| DHCP, Reserve (confirm) | `POST /v2/dhcp/reservation` · `dhcp_v2.py:reservation_confirm` | Writes, reloads Kea, reads back | busy · in-place · stepper (after) | Write · Reload Kea · Read back |
| DHCP, Add subnet… | `GET /v2/dhcp/subnet` · `dhcp_v2.py:subnet_preview` | Preview reads Kea live | busy on the link (C4216's spinner); busy on the form | Ask Kea · Plan |
| DHCP, Subnet (confirm) | `POST /v2/dhcp/subnet` · `dhcp_v2.py:subnet_confirm` | Tests, writes, reloads Kea, reads back | busy · in-place · stepper (after) | Test · Write · Reload Kea · Read back |
| DHCP, Exclude a range… | `GET /v2/dhcp/exclusion` · `dhcp_v2.py:exclusion_preview` | Preview reads Kea live | busy on the link (C4216's spinner); busy on the form | Ask Kea · Plan |
| DHCP, Exclude (confirm) | `POST /v2/dhcp/exclusion` · `dhcp_v2.py:exclusion_confirm` | Tests, writes, reloads Kea, reads back | busy · in-place · stepper (after) | Test · Write · Reload Kea · Read back |
| DHCP, Release a lease… | `GET /v2/dhcp/lease` · `dhcp_v2.py:lease_preview` | Preview reads Kea live | busy on the link (C4216's spinner) | Ask Kea · Plan |
| DHCP, Release (confirm) | `POST /v2/dhcp/lease` · `dhcp_v2.py:lease_confirm` | Releases and reads back | busy · in-place · stepper (after) | Release · Read back |
| Onboard › Console ZTP, Survey preview | `POST /v2/onboard/console/<id>/survey/preview` · `console_ztp_v2.py:survey_preview` | Reads NetBox's console model | busy · in-place | Read NetBox · Plan |
| Onboard › Console ZTP, Survey | `POST /v2/onboard/console/<id>/survey` · `console_ztp_v2.py:survey_confirm` | Console survey job | busy · in-place · stepper (live) | Console · Read device · Record |
| Onboard › Console ZTP, Kick-start preview | `POST /v2/onboard/console/<id>/kickstart/preview` · `console_ztp_v2.py:kickstart_preview` | Reads NetBox | busy · in-place | Read NetBox · Plan |
| Onboard › Console ZTP, Kick-start | `POST /v2/onboard/console/<id>/kickstart` · `console_ztp_v2.py:kickstart_confirm` | Kick-start job over the console | busy · in-place · stepper (live) | Console · Boot ZTP · Lease · Reachable |

## Monitoring / History / Logs

| Where | Route | What it does | Feedback today | Steps a person would want |
|---|---|---|---|---|
| History › Syslog, Ask Loki | `GET /v2/history/query/syslog` · `v2.py:history_query_syslog` | Queries Loki | busy · in-place | Ask Loki · Group · Draw |
| Logs, Filter | `GET /v2/logs` · `logs_v2.py:page` | Filters the tail (unverified slow) | busy · in-place | Filter · Draw |
| History › Ask logs, Ask | `GET /v2/history/query/ask/logs` · `v2.py:history_ask_logs` | Loki query (`ask=1`) | busy (`#lq-ask` via `hx-indicator`, `hx-disabled-elt`) · in-place | Build query · Ask Loki · Draw |
| History › Ask metrics, Ask | `GET /v2/history/query/ask/metrics` · `v2.py:history_ask_metrics` | Prometheus and Loki queries | busy (`#lq-ask`) · in-place | Build query · Ask Prometheus · Draw |
| History › Ask logs, Reveal | `POST /v2/history/query/ask/logs/reveal` · `v2.py:history_ask_logs_reveal` | Reads the raw Loki line and records the reveal | busy · in-place | Ask Loki · Record · Show |
| History › metric | `GET /v2/history/query/metric/<key>` · `v2.py:history_query_metric` | Grafana or Loki query | unverified | Query · Draw |
| History page (filters, export) | `GET /v2/history` · `v2.py:history_page` | git log and about 50 stores | page load; busy on the pressed control until the page replaces it (C4216) | Read git · Read records · Merge |
| Monitoring › Alerts history, Build the evidence | `POST /v2/monitoring/alerts/history/<ep>/evidence` · `v2.py:monitoring_alert_history_evidence` | Builds an evidence pack (Grafana, Loki, Prometheus) | busy · in-place | Alerts · Logs · Metrics · Seal pack |
| Monitoring › Evidence pack, Build again | `POST /v2/monitoring/alerts/pack/<id>/rebuild` · `v2.py:monitoring_alert_pack_rebuild` | Rebuilds the pack | busy · in-place | Alerts · Logs · Metrics · Seal pack |
| Monitoring › Heartbeat (page) | `GET /v2/monitoring/heartbeat` · `v2.py:heartbeat` | Loki and Prometheus per device | page load; busy on the pressed control until the page replaces it (C4216) | Read arrivals · Measure · Draw |
| Monitoring › Heartbeat, Apply | `POST /v2/monitoring/heartbeat/apply` · `v2.py:heartbeat_apply` | Re-measures and writes rules (JS `ipslaPost`) | busy (Alpine label) · in-place or reload | Measure again · Write rules · Host step |
| Monitoring › IP SLA, Set policy | `POST /v2/monitoring/ip-sla/policy` · `v2.py:ip_sla_policy_set` | Commits the profile's policy (JS) | busy (Alpine label) · in-place | Check · Commit |
| Monitoring › IP SLA, Commit suggestions | `POST /v2/monitoring/ip-sla/commit` · `v2.py:ip_sla_commit` | Commits into devices' intent (JS) | busy (Alpine label) · redirect to Apply | Check · Commit · Open Apply |
| Monitoring › Coverage, Apply… | `GET /v2/monitoring/apply` · `v2.py:profile_apply` | Plans the monitoring apply ("local but slow") | page load; busy on the pressed control until the page replaces it (C4216) | Plan each · Order · Ready |
| Monitoring › Apply, Leave out / Move | `GET /v2/monitoring/apply/preview` · `v2.py:profile_apply_preview` | Re-renders the apply preview | busy · in-place | Re-plan · Draw |
| Monitoring › Apply, Deploy | `POST /v2/monitoring/apply/confirm` · `v2.py:profile_apply_confirm` | Batch deploy job | busy · in-place · stepper (live) | Order · Each device · Verify · Record |
| Monitoring › Apply, Deploy the pair | `POST /v2/monitoring/apply/confirm-pair` · `v2.py:pair_apply_confirm` | Paired batch deploy job | busy · in-place · stepper (live) | Both ends · Verify link · Record |
| Monitoring › Profile, Commit proposal | `POST /v2/monitoring/profile/propose` · `v2.py:profile_propose_commit` | Commits the profile change | busy · in-place | Check · Commit |
| Monitoring, Decline (commit) | `POST /v2/monitoring/decline/confirm` · `v2.py:decline_confirm` | Commits a decline | busy · in-place | Commit |
| History, Re-apply… | `GET /v2/history/reapply` · `v2.py:history_reapply` | Plans the re-apply ("local but slow") | unverified | Plan · Ready |
| History › Re-apply, Start | `POST /v2/history/reapply/confirm` · `v2.py:history_reapply_confirm` | Restore deploy job | busy · in-place · stepper (live) | Plan again · Each device · Verify |
| Monitoring › Coverage (page) | `GET /v2/monitoring/coverage` · `v2.py:coverage` | `monitoring_coverage.fleet` ("local but slow") | page load; busy on the pressed control until the page replaces it (C4216) | Compute · Draw |

## Settings / Installation (including Credentials, Notify, Remote, Console servers)

| Where | Route | What it does | Feedback today | Steps a person would want |
|---|---|---|---|---|
| Settings › Network › integration card, Test | `POST /v2/settings/network/<n>/group/<g>/test` · `settings_v2.py:group_test` | Tests the integration's connection | busy · in-place | Connect · Authenticate · Answer |
| Settings › Installation card, Test | `POST /v2/settings/installation/card/<name>/test` · `settings_v2.py:install_test` | Asks the integration now (AI card: one gateway call) | busy · in-place | Connect · Authenticate · Answer |
| Settings › Records database, Test | `POST /v2/settings/installation/records/test` · `settings_v2.py:records_test` | Connects to PostgreSQL | busy · in-place | Connect · Check schema |
| Settings › Records stores, Move | `POST /v2/settings/installation/records/stores/<dir>` · `settings_v2.py:records_store_apply` | Moves a records store (unverified slow) | busy · in-place | Copy · Check counts · Switch |
| Settings › SDN, Test (unsaved) | `POST /v2/settings/network/<n>/sdn/test` · `settings_v2.py:sdn_test` | Tests a controller connection | busy · in-place | Connect · Authenticate · Answer |
| Settings › SDN, Test (saved) | `POST /v2/settings/network/<n>/sdn/<name>/test` · `settings_v2.py:sdn_saved_test` | Tests the saved connection | busy · in-place | Connect · Answer |
| Settings › Code repository, Fetch | `POST /v2/settings/network/<n>/code-repository/fetch` · `settings_v2.py:code_repo_fetch` | git fetch of the code repository | busy · in-place | Connect · Fetch · Done |
| Settings › Network source, Preview | `POST /v2/settings/network/<n>/source/preview` · `settings_v2.py:network_source_preview` | Reads NetBox | busy · in-place | Read NetBox · Compare |
| Settings › Network source, Refresh | `POST /v2/settings/network/<n>/source/refresh` · `settings_v2.py:network_source_refresh` | Reads NetBox again | busy · in-place | Read NetBox · Draw |
| Settings › Network source, Save | `POST /v2/settings/network/<n>/source` · `settings_v2.py:network_source_apply` | Switches the source (unverified slow) | busy · in-place | Save · Reload list |
| Settings › Networks, Create | `POST /v2/settings/networks/new` · `settings_v2.py:network_create` | Creates the list and its repository | busy · in-place | Folder · Repository · Commit |
| Settings › Network, Delete | `POST /v2/settings/network/<n>/delete` · `settings_v2.py:network_delete` | Deletes the list (unverified slow) | busy · in-place | Count · Remove · Done |
| Settings › Platforms, Preview | `POST /v2/settings/installation/platforms/preview` · `settings_v2.py:platforms_preview` | Reads NetBox platforms | busy · in-place | Read NetBox · Diff |
| Settings › Platforms, Save | `POST /v2/settings/installation/platforms/apply` · `settings_v2.py:platforms_apply` | Writes platforms | busy · in-place | Write · Read back |
| Settings › Platforms, Test | `POST /v2/settings/installation/platforms/test` · `settings_v2.py:platforms_test` | Starts a version read on a device | busy · in-place · live card | Connect · Read version · Match |
| Settings › Diagnostics, Check drift now | `POST /v2/settings/installation/diagnostics/drift/<n>/check` · `settings_v2.py:diag_drift_check` | Starts the drift check | busy · in-place | Read each · Compare · Summary |
| Notify, Send code | `POST /v2/settings/installation/notify/teams/<t>/<d>/code` · `notify_v2.py:code_send` | Sends a verification code (mail or webhook) | busy · in-place | Send · Delivered |
| Notify, Add email | `POST /v2/settings/installation/notify/teams/<t>/email` · `notify_v2.py:email_add` | Adds and sends a code | busy · in-place | Save · Send code |
| Notify, Add webhook | `POST /v2/settings/installation/notify/webhooks` · `notify_v2.py:webhook_add` | Adds and sends a code | busy · in-place | Save · Send code |
| Notify, Test a destination | `POST /v2/settings/installation/notify/teams/<t>/<d>/test` · `notify_v2.py:dest_test` | Sends a test message | busy · in-place | Send · Delivered |
| Notify › Relay, Test | `POST /v2/settings/installation/notify/relay/test` · `notify_v2.py:relay_test` | Sends through the mail relay | busy · in-place | Connect relay · Send · Delivered |
| Console servers, Re-key preview | `POST /v2/settings/installation/console-servers/port/<id>/rekey/preview` · `console_servers_v2.py:rekey_preview` | Reads the console server's SSH key | busy · in-place | Connect · Read key |
| Console servers, Keep the key | `POST /v2/settings/installation/console-servers/port/<id>/rekey` · `console_servers_v2.py:rekey_confirm` | Reads the key again and keeps it | busy · in-place | Read key · Keep |
| Console servers, Save port | `POST /v2/settings/installation/console-servers/port` · `console_servers_v2.py:port_save` | Writes the port (NetBox) | busy · in-place | Check · Write NetBox |
| Console servers, Remove port | `POST /v2/settings/installation/console-servers/port/<id>/remove` · `console_servers_v2.py:port_remove` | Removes the port (NetBox) | busy · in-place | Remove · Done |
| History › Remote setup, Connect | `POST /v2/history/remote/setup/connect` · `remote_v2.py:connect` | Adopts the existing git remote (unverified slow) | busy · in-place | Reach remote · Record |
| History › Remote setup, Probe | `POST /v2/history/remote/setup/write-probe` · `remote_v2.py:write_probe` | Pre-push checks and a write probe | busy · in-place | Checks · Write probe · Result |
| History › Remote setup, What would publish | `POST /v2/history/remote/setup/publication` · `remote_v2.py:publication` | Reads what a first push publishes | busy · in-place | Read commits · Read tags · List |
| History › Remote setup, Auto-push on | `POST /v2/history/remote/setup/auto-push` · `remote_v2.py:auto_push` | Turns on auto-push after a push (unverified slow) | busy · in-place | Check push · Turn on |
| History › Remote, Verify the remote | `POST /remote/verify` · `remote.py:verify` | Pre-push checks (JS `remotePost`) | busy (Alpine label) · in-place line | Reach · Checks · Result |
| History › Remote, Push now | `POST /remote/push` · `remote.py:push` | git push on a thread (JS `remotePost`) | busy (Alpine label) · in-place line | Push · Verify · Done |
| Credentials › Read account, Check each device | `POST /v2/credentials/profiles/read-account/add/preview` · `credential_profiles_v2.py:read_account_add_preview` | Preview per device (unverified slow) | busy · in-place | Each device · Plan |
| Credentials › Read account, Commit | `POST /v2/credentials/profiles/read-account/add` · `credential_profiles_v2.py:read_account_add` | Commits the read account into intent | busy · in-place | Commit |
| Credentials › Read account, Probe | `POST /v2/credentials/profiles/read-account/probe` · `credential_profiles_v2.py:read_account_probe_confirm` | Probe job on one device | busy · in-place · live card | Connect · Log in · Read |
| Credentials › Read account, Plan rollout | `POST /v2/credentials/profiles/read-account/rollout/plan` · `credential_profiles_v2.py:read_account_rollout_plan` | Plans waves | busy · in-place | Plan each · Waves |
| Credentials › Read account, Deploy | `POST /v2/credentials/profiles/read-account/rollout` · `credential_profiles_v2.py:read_account_rollout_confirm` | Rollout job (canary then waves) | busy · in-place · live card | Canary · Settle · Waves · Verify · Save |
| Credentials › Read account, Go on | `POST /v2/credentials/profiles/read-account/rollout/go-on` · `credential_profiles_v2.py:read_account_rollout_go_on` | Continues the rollout | busy · live card | Next wave · Verify |
| Credentials › Profiles, Rotate due now | `POST /v2/credentials/profiles/rotate-due` · `credential_profiles_v2.py:rotate_due_confirm` | Scheduled-rotation run | busy · in-place · stepper (live) | Each device · Send · Prove · Record |
| Credentials › Break-glass, Export | `POST /breakglass/export` · `breakglass.py:export` | Encrypts the export (KDF), then the intact check (JS) | busy (Alpine) · in-place | Encrypt · Download · Check intact |
| Credentials › Break-glass, Check the file | `POST /v2/credentials/check` · `v2.py:credentials_check` | Opens the upload in memory and compares (unverified slow) | busy · in-place | Open · Compare · Result |
| Credentials › Break-glass, Drill | `POST /v2/credentials/drill` · `v2.py:credentials_drill` | Checks a drill receipt against the exports (unverified slow) | busy · in-place | Read receipt · Compare · Record |

## Update / About

| Where | Route | What it does | Feedback today | Steps a person would want |
|---|---|---|---|---|
| Update panel, Update | `POST /update/apply` · `update.py:apply` | Requests the root updater | busy · in-place · stepper (live, `nmas:app_version`) | Request · Fetch · Install · Restart · Smoke check |
| Update chip, Check again | `POST /update/check` · `update.py:check` | Runs the version reader now (JS `check`) | busy (Alpine) · panel redraw | Fetch · Compare · Answer |
| About › Installation card | `GET /v2/help/installation` · `v2.py:installation_card` | Version facts, CI verdict, a git `subprocess` | live card (`nmas:ci_verdict`) | Read version · Read CI · Draw |

## AI / Assistant

| Where | Route | What it does | Feedback today | Steps a person would want |
|---|---|---|---|---|
| Assistant panel, Ask | `POST /v2/assistant/ask` · `assistant_v2.py:ask` | AI answer | busy · in-place | Read context · Ask AI · Answer |
| Monitoring › Evidence pack, Explain | `POST /v2/monitoring/alerts/pack/<id>/explain` · `v2.py:monitoring_alert_explain` | AI explains the pack | busy · in-place | Read pack · Ask AI · Answer |
| History › Ask logs, In words | `POST /v2/history/query/ask/logs/words` · `v2.py:history_ask_logs_words` | AI turns words into a log query | busy · in-place | Ask AI · Fill query |
| History › Ask metrics, In words | `POST /v2/history/query/ask/metrics/words` · `v2.py:history_ask_metrics_words` | AI turns words into a metric query | busy · in-place | Ask AI · Fill query |

AI calls listed under other areas: Device › Draft change record, Device › Intent Draft from words,
Incident › Investigate / Ask again / Modify, SDN › Responses Classify, SDN › Policies Draft,
SDN › Analyse Ask and Ask with tools.

## Existing stepper

- **Templates:** `templates/v2/_run_stepper.html` holds THE stepper. Its macros are `run_stepper`
  (rows of devices or subjects, declared steps across, an overall bar and counts, groups with Find
  from 25 rows, vertical below 640 px, and a record card drawn as five *stages* via `_stages`) and
  `run_summary`, a one-line summary used by `_sc_result.html` and `_lp_result.html`. A second,
  compact stepper is `templates/v2/_inc_step.html`, the incident card's step line with a spinner
  on the running step, used by `_fixit_section.html`, `_plan_card.html` and
  `routes/incident_v2.py:step`. `tests/test_one_stepper.py` holds that operation pages draw
  progress only through the macro.
- **Model:** `modules/run_stepper.py` decides every row, group, count and stage (`from_stepper`,
  `from_record`, `stages`, `at_step`). Each operation declares its own step tuples beside its code
  (`pipeline.STEPPER_STEPS`, `save_op.DEVICE_STEPS`, `reload_op`, `rotate_op`, `adopt`, the heal's
  `heal_stage_table`, `RESUB_STAGES`). They are handed over through `device_actions.stepper` /
  `job_steps`.
- **What drives it:** everything is rendered on the server. A job announces its key over
  SocketIO. `nmas_v2.js` turns that into an `nmas:<key>` event on `<body>`, and the card's
  `hx-get` with `hx-trigger="nmas:<key> from:body"` re-fetches and swaps itself. There is no
  polling. `static/js/nmas_stepper.js` only ticks the running step's seconds (`data-run-since`)
  and a declared wait's countdown (`data-run-wait-*`) once a second. The compact stepper's clock
  is `time[data-elapsed]` in `nmas_v2.js`.
- **Already using it, live:** device Deploy, Restore, Reload, Rotate and Capture; Save All;
  Adopt; out-of-band onboarding; console ZTP survey and kick-start; onboarding pending progress;
  NetBox preview and import; scheduled credential rotation; the control strip's heal batch;
  the heal run card and incident page; telemetry re-subscribe; SDN app deploy; monitoring and
  history apply (`_apply_job.html`); Update.
- **Already using it, after the fact:** Persist (Save), Retire, Capture's record, onboarding
  Verify, the four DHCP writes. Show commands and logging-path use `run_summary` only. The
  incident Fix it, approved plans and fix scripts use the compact stepper.
- **Could reuse it (now busy + in-place, or a live card with its own words):**
  - Device: Drift check now, Re-key (read and keep), Seed, Revert and Retry commits, Diagnose
    run, Privileged read and send, Ask, Rotate preview, Reload preview, Save's effect read,
    Saved action run.
  - Fleet: fleet change plan, approve and go on; read-account rollout and probe, which today
    write their own wave line; Show commands and logging-path (full rows in place of
    `run_summary`); Topology path trace; Template coverage check.
  - Onboarding: Create (NetBox, address, reservation, intent) and Abandon. Persist, Retire,
    Verify and the DHCP writes already draw the stepper afterwards and could draw it live if they
    ran as jobs.
  - SDN: flow, re-apply, response, policy and DHCP-steering sends; switch Configure; app draft
    (commit and push) and publish; Export (NetBox and commit); Collect.
  - Monitoring: evidence pack build and rebuild.
  - Settings and history: records store move; network create; remote write probe and push;
    platforms test; notify relay test.
  - The slow previews that have no feedback today (action-menu links, DHCP opening links,
    device tabs) need only busy words. A stepper would be too much for them.
