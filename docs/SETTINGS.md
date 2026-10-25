# Settings: where each one is set, and why

Stage 3.2d. **Every schema key gets a decision — surfaced, or file-only with
a stated reason.** Ambiguity is what this document exists to remove: a setting
that is neither in the UI nor recorded as deliberately file-only is a setting
nobody knows the status of, which is the state all 107 of them were in.

Companion documents: [SECRETS.md](SECRETS.md) for the three secret stores,
[NSOT_PLAN.md](NSOT_PLAN.md) §3.2 for the stage itself.

---

## How a setting is written

One path: `settings_schema.write_settings()`. **A key the schema does not
declare is refused, not stored.** A validation failure writes nothing at all —
a half-applied settings write is worse than a rejected one.

`migrate()` **never seeds a default.** An absent key means *nobody decided*,
and writing it destroys that distinction irrecoverably. A version bump seeds
only the keys it declares in `SEEDS_BY_VERSION`, whose default is nothing.

Recording a decision is `ratify()`: it writes the value **already in force**,
with an actor. It cannot change a value, which is what lets the read-only
security panel offer it.

So each setting is in one of three states, visible in the posture panel:

| State | Means |
|---|---|
| **defaulted** | absent from the file; nobody has considered it |
| **ratified** | present, equal to the default; somebody agreed |
| **chosen** | present, different from the default; somebody decided otherwise |
| **retired** | declared in the schema, defaulted, and read by NOTHING (the operator's name for the fourth state, 2026-09-28). Kept only because `write_settings()` refuses a key the schema does not declare, and an install's file may hold it; listed below with why it was retired. Not "not applicable", which is for a guard-gating setting whose default is empty |

### One owning network per Kea (C1181)

The operator's design, 2026-10-17. A Kea server has **one owning network: the one where its
connection is set**, never one that inherits it. No setting declares the owner: it is measured
from the settings layers by `list_settings.kea_owner(list_name)`. A network whose Kea group is
its own (set here, its own and not configured, or not applicable) owns its own; a network that
inherits Kea is owned by Default, whose layer every inheriting network reads.

- **Every DHCP change records in the owner's repository** (`dhcp/reservations.yml`,
  `dhcp/subnets.yml`, `dhcp/exclusions.yml`) and so publishes with the owner's remote. When it
  was made from another network, the commit says which in a `From-Network:` trailer.
  Exclusions are read from the owner's record, on the owner's page and on every page that
  inherits it.
- **A DHCP preview or confirm on a network that does not own its Kea is refused**, naming both
  networks: the change is made on the owner's DHCP page.
- **Two networks may not each set the same Kea as their own.** Saving a Kea URL (a card's Save,
  or the switch to "its own" with the URL entered) is refused when another network already sets
  the same one, naming that network; Default included. The same Kea is the Control Agent's URL
  normalised: host (lower case, an IP address in its canonical form), port (the scheme's
  default when none is written) and path, with the scheme, any user part, query and trailing
  slash dropped. A hostname and an address of one machine are not measured as the same Kea,
  because that would need a DNS read on a save. A network whose settings cannot be read
  refuses the save, rather than being read as owning nothing.

---

## Surfaced in the UI

| Group | Where |
|---|---|
| `netbox_url`, `netbox_token`, `netbox_auth_scheme`, `netbox_verify_tls`, `netbox_allow_writes` | v2: Settings › Installation › Connections, the NetBox connection card (board F3, 2026-10-09). The token is a secret, shown only as set and changed by Replace… (then tested); `netbox_allow_writes` is shown with **Turn off** only: turning it on is an authorised NetBox write's confirm with writes permitted (Source of truth › NetBox's Import and Remove, C619). Each Save writes only the fields the person changed, and refuses a changed field another person moved since, naming both values (CONCURRENCY_AUDIT R17). The Test asks in the card's auth scheme, with NetBox's own reason for a refusal and each type the tool reads (C468), keeping nothing. Today's Settings → NetBox left at 7.8 (2026-10-15). |
| `proxmox_url`, `proxmox_node`, `proxmox_token_id`, `proxmox_token_secret`, `proxmox_token_expires`, `proxmox_verify_tls`, `proxmox_backup_vmids`, `proxmox_backup_storage` | v2: Settings › Installation › Connections, the Proxmox card (board F3). `proxmox_token_id` and `proxmox_token_secret` are replaced together by Replace… (a token is the pair), then tested. |
| `nsot_git_author_name`, `nsot_git_author_email` | v2: Settings › Installation › Connections, the Commit author card (board F3). |
| `flask_host`, `flask_port` | v2: Settings › Installation › Server, the Server card (board F3): read at start-up, so a Save says the change waits for the next restart. |
| `auto_open_browser` | **Retiring** (C815, the operator's decision, 2026-10-15): read by nothing, declared for one release so a rollback finds it. Whether `python app.py` opens a browser at start is the environment's alone: `NMAS_AUTO_OPEN_BROWSER` (on unless set to something else than 1, true, yes or on) and `NMAS_HEADLESS=1`, which forces it off (`modules/config.py`). |
| `platform_map`, `platform_default_netmiko_type` | v2: Settings › Installation › Platforms and roles (board F4, decision B, 2026-10-10; they were file-only, C622). **`role_map` was removed** (C665, 2026-10-11): a device's kind is its NetBox Device Role's `mercury_kind` custom field (`scripts/nmas-netbox-role-kind` creates it and copies a stored map onto NetBox's roles); a stored map stays in the file, read by nothing else. What made them file-only is answered by the screen's shape, the operator's validation: a driver is CHOSEN from the drivers Mercury supports and a config dialect from the dialects it knows (C628), never typed; every change is a **preview** naming each device whose driver or role it moves, a **Test** of one read-only session to one of them through its new driver, and a **confirm** bound to the preview, recorded in the installation's settings record, each NetBox network refreshed. A platform or role a device uses cannot be removed. The default driver, set, still trades a skip for a guess, and the card says so. |
| `tftp_root`, `tftp_server_ip` | RETIRING (declared one release so a rollback finds them): their readers, today's device file and bulk file routes, left at 7.8 (D16, 2026-10-13; C616); `tftp_root`'s field and `NMAS_TFTP_ROOT` left the same day (tag `pre-remove/tftp-root`). |
| `prometheus_url`, `prometheus_auth_mode`, `prometheus_username`, `prometheus_password`, `prometheus_bearer_token`, `prometheus_verify_tls`, `prometheus_targets_dir`, `grafana_url`, `grafana_token`, `grafana_token_expires`, `grafana_verify_tls`, `grafana_fleet_dashboard_uid`, `grafana_device_dashboard_uid`, `grafana_device_variable`, `grafana_device_variable_value`, `loki_url`, `loki_auth_mode`, `loki_username`, `loki_password`, `loki_bearer_token`, `loki_verify_tls`, `loki_selector_template`, `kea_url`, `kea_username`, `kea_password`, `kea_verify_tls`, `s3_endpoint`, `s3_bucket`, `s3_access_key`, `s3_secret_key`, `s3_region`, `s3_prefix`, `s3_verify_tls` | v2: Settings › Default and each network's cards (P.8, boards A to J), each group inherited as a whole; a card's Save writes only the fields the person changed, and refuses a changed field another person moved since, naming both values (CONCURRENCY_AUDIT R17). Today's Settings → Integrations left at 7.8 (2026-10-15). |
| Every v2 Installation card's Save, Replace and Turn off | recorded in the installation's `settings_record.jsonl`: who, when, the card and the names of what changed, never a value |
| `collector_trap_enabled`, `collector_netflow_enabled`, `collector_syslog_enabled`, `monitoring_identity_mode`, `monitoring_identity_field`, `monitoring_prom_label`, `monitoring_strip_port`, `promql_device_up`, `promql_cpu`, `promql_interface_oper` | **RETIRING, read by nothing** (scope `retiring`, group `form_only`, P.8 decision 3): today's Settings modal wrote them and nothing read them; the trap receiver and NetFlow collector the `collector_*` switches named left with the AI family (D15, 2026-10-14). Their switches and fields left with today's Settings modal at 7.8 (2026-10-15); the keys stay declared for one release, so a rollback finds them. |
| `grafana_device_dashboard_url` | **Removed (C705, 2026-10-16)**: its one reader, Grafana's "Open Grafana" link on the monitoring stack panel, left at 7.8; the device page's Monitoring tab draws its dashboard by UID (`grafana_device_dashboard_uid`). Removed the way the schema removes a key (`SEEDS_BY_VERSION` in `modules/settings_schema.py`): gone from `DEFAULTS`, its scope and the Grafana integration's keys, with no version bump, since a bump only seeds. A value an older build stored stays in the file, read by nothing (the host's file held it, empty, measured 2026-10-16); a write naming it is refused, and a write of any other key succeeds beside it (`TestARemovedKeyStaysInTheFileReadByNothing` in tests/test_settings_write_path.py). |
| `grafana_embed_mode`, `nsot_git_repo_path`, `nsot_git_remote_url`, `nsot_git_branch`, `nsot_git_auto_push`, `nsot_git_auth_mode`, `nsot_git_token` | **DEAD, read by nothing** (scope `dead` in `modules/settings_scope.py`): Grafana's device dashboard is by UID (`grafana_device_dashboard_uid`), and each network's record is its own `config_repo/` with its remote set on History › Remote set-up…. Today's Settings → Integrations still drew their fields until it left at 7.8 (2026-10-15). |
| `ai_enabled`, `background_agent_enabled`, `wf_read_first`, `wf_auto_backup`, `wf_update_vars`, `wf_require_approval` | **RETIRING with the AI family (D15, 2026-10-14), read by nothing.** The assistant, the background agent and the switches that only changed the assistant's prompt were removed (tag `pre-remove/ai-family`), with v2's AI and workflow tab and today's Settings → AI. The keys stay declared for one release (scope `retiring`), so a rollback finds them; today's `/settings` refused them by name until it left at 7.8 (2026-10-15), and no v2 card reads them. Phase 8 brings AI back as a responder with its own settings (docs/PHASE8_PLAN.md). |
| `require_identity_for_*`, `require_person_for_*`, `service_allowed_operations`, `cf_access_*` | v2: Settings › Installation › Access and identity (board F4, 2026-10-10), **read-only** (see below), with Record this decision, recorded in the installation's settings record (C625). Today's Settings → Security posture left at 7.8 (2026-10-15). |
| `records_db_host`, `records_db_port`, `records_db_name`, `records_db_user`, `records_db_password` | v2: Settings › Installation › Connections, the Records database card (board F2, 2026-10-09). The installation's, never a network's (Phase 4, P4-2). Host empty: every store stays on its files, today's behaviour; the name, role and port default to what host step 6a makes (`mercury`, `mercury`, 5433). The password is a secret (`secrets_store.SECRET_KEYS`), shown only as set and changed by Replace…, after the server's by `scripts/host-steps/postgres-rotate.sh`. Save and Replace are recorded in the installation's `settings_record.jsonl`; the last Test's answer is kept in `records_db_test.json`. |
| `credential_rotation_policies` | v2: Credentials › Profiles, each profile's **Rotation policy…** (C724, 2026-10-12): `{profile: {state, days, window_start, window_end, max_per_run, set_by, set_at, verified}}`, the scheduled credential rotation its devices follow (docs/manual/how-it-works/rotate.md, "On a schedule"). Empty (the default) is no policy: nothing rotates on a schedule, the behaviour before it existed. Set only by a verified person, and each change recorded in `credential_changes.jsonl` (History's Credential profiles source): who, when and the policy in words. |
| `records_store_receipts` | v2: Settings › Installation › Connections, Record stores (Phase 4, section 7, 2026-10-10). Where deploy receipts are kept: `file` (the default, today's behaviour) or `postgres`, read at each call so every process follows a switch. Never set by hand: **Move to the database…** copies every file line, switches it, copies again and checks, and **Move back to files…** exports what was written since and switches back; each is recorded in the installation's `settings_record.jsonl` (`records_store_move`, `records_store_back`). Any other value stored reads as `file`. |
| `records_store_acknowledgements` | v2: the same card (K31, 2026-10-19). Where Needs attention's acknowledgements are kept (`acknowledgements.jsonl`, one file for the installation): `file` (the default, today's behaviour) or `postgres`. Moved and moved back exactly as receipts are, by the card's own row for it; never set by hand. |
| `records_store_restarts`, `records_store_restart_windows`, `records_store_restart_window_ends` | v2: the same card (K31, 2026-10-19). Where the restarts seen (`restarts.jsonl`), the planned-restart windows (`planned_restarts.jsonl`) and the windows ended early (`planned_restart_ends.jsonl`) are kept, each one file for the installation: `file` (the default, today's behaviour) or `postgres`. Each moves on its own, by its own row; never set by hand. |
| `records_store_reveals`, `records_store_host_steps_done`, `records_store_heartbeat_rules`, `records_store_netbox_removals` | v2: the same card (K31, 2026-10-19). Where the reveal record (`reveal_audit.jsonl`), the host steps said done (`host_steps_done.jsonl`), the heartbeat windows' re-measures (`heartbeat_rules.jsonl`) and NetBox's removals (`netbox_removals.jsonl`) are kept, each one file for the installation: `file` (the default, today's behaviour) or `postgres`. Each moves on its own, by its own row; never set by hand. |
| `records_store_network_settings_record`, `records_store_onboarding_runs`, `records_store_inventory_edits` | v2: the same card (K31, 2026-10-19). Where each network's settings changes (`settings_record.jsonl`), onboarding runs (`onboarding_runs.jsonl`) and inventory edits (`inventory_edits.jsonl`) are kept, one file per network in its list folder: `file` (the default, today's behaviour) or `postgres` (one table each, every network's rows by network). Each moves on its own, for every network at once, by its own row; never set by hand. |
| `records_store_approval_queue` | v2: the same card (K31 part 3, 2026-10-19). Where each network's approval queue (`approval_queue.json`, one document per network) is kept: `file` (the default, today's behaviour) or `postgres` (one row per network, the document as copied beside the document now). Moved by its own row; never set by hand. |
| `records_store_rollback_blocks`, `records_store_retry_log` | v2: the same card (K31 part 3, 2026-10-19). Where each network's rollback blocks (`config_repo/.nsot/rolled_back.json`) and authorised retries (`config_repo/.nsot/retry_log.json`) are kept, one document per network: `file` (the default, today's behaviour) or `postgres`. Each moves on its own, by its own row; never set by hand. |
| `records_store_netbox_created`, `records_store_netbox_modified`, `records_store_netbox_adopted` | v2: the same card (K31 part 3, 2026-10-19). Where Mercury's NetBox bookkeeping is kept (`netbox_created_ids.json`, half of Remove's `tagged AND recorded`; `netbox_modified.json`; `netbox_adopted.json`), each one document for the installation: `file` (the default, today's behaviour) or `postgres`. Each moves on its own, by its own row; never set by hand. |
| `records_store_interrupted_holds` | v2: the same card (K31, 2026-10-19). Where the operations interrupted while they held a device are kept (`device_ops/<list>/interrupted.jsonl`, one per list folder): `file` (the default, today's behaviour) or `postgres`. Moved by its own row; never set by hand. |
| `records_store_reader_values` | v2: the same card (C1330, 2026-10-19). Where each reader's stored value is kept (`readers/<reader>.json`, one document per reader's store, `<reader>@<configuration>` for one read per configuration): `file` (the default, today's behaviour) or `postgres`, read and written through the process's pool of records-database connections. On a database that does not answer, every stored value reads as unreadable and no run stores over it. Moved by its own row; never set by hand. |
| `records_store_ai_calls` | The same switch (Phase 8, 2026-10-25). Where the record of every AI call is kept (`ai_calls.jsonl`, one for the installation; `modules/ai/calls.py`): `file` (the default) or `postgres`. The gateway's day cap sums it, so an unreadable record refuses the next call. |
| `anthropic_api_key`, `ai_hosted`, `ai_cap_usd_per_call`, `ai_cap_usd_per_day` | Phase 8's gateway (`modules/ai/gateway.py`, PHASE8_PLAN 13.1, 15.8, 15.12), the installation's (scope `host`, group `ai_gateway`). v2: Settings › Installation › Connections, the **AI (hosted)** card (8.0b, 2026-10-25; its board owed Saturday, the operator's ruling): the key by Replace…, the caps by Save, the allowance by Allow (with the person's reason) and Turn off, each recorded in the installation's settings record; its Test is one recorded call. `anthropic_api_key` is a secret (`secrets_store.SECRET_KEYS`), empty until a person types it, never shown. `ai_hosted` is the admin's allowance, `{"by", "at", "reason"}` (the `settings_not_applicable` pattern), empty by default: with no reason recorded the gateway refuses every call (`ai_off`). The day cap, `ai_cap_usd_per_day` (`1.50` US dollars, under PHASE8_PLAN 7's $50 a month), is the installation's: today's spend plus a call's worst case, refused before sending with both operands named. **`ai_cap_usd_per_call` is retiring** (the operator, 2026-10-25): a call's cap is its task's, derived from its pinned model's worst case at the task's bounds (`modules/ai/profiles.py`, `TASKS`, drawn read-only on the card with each model's prices from Anthropic's pricing page and their date), so the key is read by nothing from this release and stays declared one more (scope `retiring`; expand, then contract), then is removed. |
| `records_store_evidence_packs` | v2: the same card (PHASE8_PLAN 15.9, P1, 2026-10-25). Where the alerts' evidence packs are kept (`evidence_packs.jsonl`, one file for the installation, one line per pack; Monitoring › Alerts draws them): `file` (the default) or `postgres`. On a store that cannot be read, no pack is built and the tab says so. Moved by its own row; never set by hand. |
| `records_store_rotations` | v2: the same card (K31, 2026-10-19). Where the rotation and save record (`rotation_audit.jsonl`, one file for the installation; job health's rotation rows, History's rotations and persists) is kept: `file` (the default, today's behaviour) or `postgres`. Moved by its own row; never set by hand. |
| `records_store_breakglass_exports`, `records_store_breakglass_intact`, `records_store_breakglass_checks`, `records_store_breakglass_drills` | v2: the same card (K31, 2026-10-19). Where the break-glass logs are kept (`breakglass_exports.jsonl`, `breakglass_intact.jsonl`, `breakglass_checks.jsonl`, `breakglass_drills.jsonl`; digests and verdicts, never a value; each one file for the installation): `file` (the default, today's behaviour) or `postgres`. Each moves on its own, by its own row; never set by hand. |

`grafana_token_expires` and `proxmox_token_expires` are the tokens' DECLARED expiries
(YYYY-MM-DD, or `never`), because neither token can read its own (P.21, C380). They were on
today's Settings → Integrations as a **recorded exception** to the no-new-v1 rule until it left
at 7.8 (2026-10-15); they are fields of Settings › Default's Grafana card and Settings ›
Installation's Proxmox card.

---

## Read-only in the UI, by design

The security gates and the Cloudflare Access values are **shown but not
editable**, and the panel says why in words rather than greying a field:

> Changing them from a browser would let a compromised session lower its own
> gate — the session would use the very permission it was editing. The
> Cloudflare Access values especially: a wrong team domain or AUD either locks
> everyone out or admits everyone, and neither failure announces itself.

Edit them in `data/user_settings.json` on the host. The panel shows each one's
**effective value and origin** so an unrecorded decision is visible, and
offers *record this decision*, which ratifies and cannot change.

---

## Waiting for their screen

Declared, read, and not yet on any page: each names the screen it waits for. Until then they are
set by editing `data/user_settings.json` (the secret through the secrets store), which an
installation that wants today's behaviour never needs to.

| Setting | Waits for |
|---|---|
| `no_change_windows` | C1317 (the operator, 2026-10-18): the installation's daily spans, in UTC, in which no scheduled change starts, `[{"start": "HH:MM", "end": "HH:MM", "reason": "..."}]` (`modules/change_windows.py`; the schema refuses any other shape). **None by default: nothing is held**; what an installation sets is its own (a nightly hypervisor backup, a freeze), and nothing in the product names one. A window is `[start, end)`; a start after its end wraps past midnight; a start equal to its end holds nothing and says so. The scheduled credential rotation reads it today: no run starts inside a window, a run that reaches one stops there, and Credentials › Profiles names each window set. It waits for a Settings › Installation card, drawn with the bulk actions' windows (docs/BULK_ACTIONS.md, question 5); until then it is written through `write_settings` on the host. |

## File-only, deliberately

Each with a reason. These are settable by editing
`data/user_settings.json` and restarting where noted.

| Setting | Why not in the UI |
|---|---|
| `verify_settle_windows` | Per-protocol convergence timings, nested. Changed when a protocol's behaviour is *measured*, not adjusted by feel — a slider would invite the second. Its `unexpected` window (C506; default 2 s first wait, 10 s in all, re-read every 2 s) is the short settle before an interface the change did not touch, gone down, fails verify at once: one installation-wide value every network inherits, to be measured per platform from the devices' flap-to-recovery history. |
| `cf_access_service_labels` | A mapping of service Client ID → human label, edited when a service token is issued, which is already a host-side operation. |
| `cf_access_jwks_ttl` | Cache lifetime for Cloudflare's signing keys, **300 s to a day** (C621, 2026-10-10; default 3600). Never 0: Cloudflare rotates its signing keys, and a key it retires stays trusted here until the cache is read again (a new key is fetched when first seen, PyJWT 2.7). The schema refuses a value outside the bounds; one put in the file by hand is not used (the default is, and the app log and the Access and identity tab say why). The default is correct and there is no operational reason to change it. |
| `deploy_max_workers` | Deploy concurrency, default 1. Raising it changes the blast radius of a bad plan. Deliberately awkward. |
| `deploy_verify_failure_limit` | Circuit-breaker threshold: the failed devices (a rejected push, a refusal, or a verify that did not pass; C10) after which a batch stops. The key keeps its older name. Same reasoning. |
| `nsot_config_read_timeout` | Measured against real device behaviour (5.5s idle, >16s after `write memory`). Tuned from evidence, not preference. |
| `nsot_device_tag_retention` | Tag pruning depth. Housekeeping; no operational decision attached. |
| `reads_answer_cap_kib` | Per network. Show commands' cap on one answer, 32 KiB: about three times the largest answer measured (a 9,972-byte running configuration, the nine goldens read 2026-10-08). A longer answer is kept to the cap and says it was cut. Measured, not a preference. |
| `reads_max_workers` | Per network. Devices Show commands reads at once, 6: the drift check's measured load on these devices (nine full configurations in 47 to 55 s, s3 included). Raising it loads more devices at once. |
| `reads_retention_days` | Per network. Days Show commands' answers are kept here (30, the operator's R2) before they move to the network's S3/MinIO archive; with none configured they stay, and the engine says so. Who, when and what are kept for good. |
| `kea_services` | A list (`dhcp4`, `dhcp6`). Belongs in the Kea card as a multi-select; **not yet built** — this is a gap, not a decision. |
| `grafana_history_datasource_uid` | C406: the Grafana datasource (by UID) whose PromQL endpoint keeps metrics past the live store's retention (Thanos Query, Mimir, ...). Empty (the default) means none: a panel range past the live store's retention is refused naming it, as before. Set at installation, alongside Grafana's datasources; no form yet, because a new control belongs on a v2 Settings screen with a signed-off mockup. When set, the device and Monitoring panels read a longer range from it and say so in the panel's foot line. |
| `logs_retention_days` | C652: per network, how long its Loki keeps logs, in days; default 90, Loki's value before NSOT_STAGE7_PLAN 14.15's host step (the lab's Loki keeps 730 since, so the lab sets 730). The Logs view reads it to say what its range can hold: a range past it says how many days were deleted; Loki holding lines older than it says the setting may be lower than what Loki keeps. It describes the store, so it changes when the store does. |
| `metrics_live_retention_days` | C406: how long the LIVE PromQL store (the dashboards' own datasource) keeps metrics, in days; default 90, the value measured on the host 2026-09-30. A panel range longer than this reads `grafana_history_datasource_uid`. It describes the store, so it changes when the store's retention changes. |
| `oxidized_url`, `oxidized_username`, `oxidized_password`, `oxidized_node_identity`, `oxidized_verify_tls`, `oxidized_router_db` | **Retired with Oxidized (Phase 3, the operator's decision P3-3, 2026-10-08), read by nothing.** Mercury no longer talks to Oxidized: no Settings card, no monitoring tile, no fetch after a commit, no freshness comparison, no router.db row. The keys stay declared for one release (scope `retiring` in `modules/settings_scope.py`), so a rollback to the release before finds them; the release after removes them with a settings version bump. `tests/test_oxidized_settings_inert.py` holds that nothing else reads them. |
| `topology_service_url`, `topology_service_type`, `topology_service_token`, `topology_service_verify_tls` | **Retired with the topology service (7.8, 2026-10-12), read by nothing.** OBSERVE › Topology, over Mercury's own `topology-graph` reader, replaced the service; its renderer and unit were removed by a host step. No Settings card, no health probe (the integration is in `modules.integrations.RETIRED`, never registered), no Needs attention row. The keys stay declared for one release (scope `retiring`), so a rollback finds them, then go with a settings version bump. `tests/test_retired_integrations.py` holds that nothing probes, draws or reads them. |
| `oxidized_rest_url` | **DEPRECATED and read by nothing, and it gates nothing**, since before Phase 3: it named the same fact as `oxidized_url`. Kept only because schema keys are never deleted; it goes with the rest of Oxidized's keys. |
| `clab_host`, `clab_configs_dir`, `clab_sync_script`, `clab_launch_patch`, `clab_labs`, `clab_declared_unmapped` | **Removed (C663, the operator's decision, 2026-10-11): the lab is test infrastructure, not the product.** The lab's startup sync reads its own map (`data/lab_targets/<network>.tsv`, beside the checkout, `lab/clab-sync/`). A host that stored them keeps the values in its file, read by nothing: the schema allows a stored key it does not declare (measured: a write and a ratify succeed beside them), and Mercury has no delete path for a settings key. |
| `yang_push_script` | Path to the telemetry helper; same. **Its script was retired on 2026-09-26 (C31)**, so on the deployment host it is declared not applicable rather than left empty. |
| `jenkins_step_shell` | **DEPRECATED and read by nothing** (P.4 removed Jenkins, and with it the pipeline generators that chose `bat` or `sh`). Its control is gone from Settings → Server; kept only because schema keys are never deleted. |
| `wf_run_jenkins`, `wf_save_golden` | **DEPRECATED and read by nothing** (P.4 removed Jenkins; the agent's prompt, their last reader, left with the AI family, D15). They told the agent whether to run Jenkins after a push and whether to save a golden after CI passed. Their switches are gone from the form; kept only because schema keys are never deleted. |
| `settings_not_applicable` | Guard-gating settings declared NOT APPLICABLE on this host, with who, when and why (C31). **Written only by `scripts/nmas-setting-not-applicable`**, on the host, like the identity gates: a declaration changes what a check means, so a browser session must not be able to make one. Job health reads it as `not_applicable`; a key both set and declared is a `contradiction`. |
| `netbox_excluded_vrfs` | VRFs whose **addresses** the NetBox import does not model, **empty by default** (C663, 2026-10-11; it named one emulator's VRF until then, and a host relying on that ratified it first, `scripts/host-steps/c663-step2-pin-vrfs.sh`). It describes an emulator, not a preference: where every emulated node answers on the same internal management address, NetBox's global uniqueness makes importing them not representable rather than merely untidy (measured: one created, four refused with *"Duplicate IP address found in global table"*). A read that fails refuses, naming the setting, and the import names the device it was writing as failed: with an empty default there is no fallback that keeps a declared exclusion. |
| `netbox_remove_on_list_delete` | **DEPRECATED and read by nothing** (C155, the operator's decision, 2026-09-28). Deleting a device list never deletes NetBox objects: removal has one home, the NetBox page's previewed and confirmed Remove from NetBox…, and a list that still owns recorded objects is refused until they are removed. The switch was removed from Settings → NetBox, and its branch deleted NMAS-created objects with no preview and no confirmation token. Still declared. Removing the declaration would not break the host's file: the schema allows a stored key it does not declare (`additionalProperties`), so the stored value would stay in the file, read by nothing, and `write_settings()` and `ratify()` would still work (measured 2026-10-11, C672). Whether the deprecated keys' declarations go is the cutover's settings tidy. **Nothing to do on the host**: its default is `False` and nothing reads it. It is NOT declared not applicable: that record is for guard-gating settings whose default is EMPTY, and `nmas-setting-not-applicable` refuses this one, correctly ("has a non-empty default, so it is never unset; there is nothing to declare"). |
| `kea_ztp_fragment`, `kea_dhcp4_config` | P.6 D1: the reservation fragment NMAS owns and the kea-dhcp4 config that includes it. Host paths set once with the host change in [DEPLOY_LINUX.md](DEPLOY_LINUX.md) (the Kea section); they describe a machine, not a preference. **`kea_ztp_fragment` defaults to empty and a `ztp` plan refuses while it is**, because a reservation written anywhere else lives in Kea's memory until its next restart (C49, demonstrated by M5). |
| `kea_dhcp6_config` | C529 step 2: the kea-dhcp6 configuration whose subnets take their reservations from Mercury's files (`nmas/reservations6-<id>.json` beside it); DHCP's reservation writer tests each IPv6 candidate against a copy of it with `kea-dhcp6 -t`, as `kea_dhcp4_config` is used for IPv4. A setting because Kea's `config-get` does not name the file Kea was started with (measured 2026-10-11); the default is Kea's own path. A host path, not a preference. |
| `syslog_host`, `syslog_trap_level`, `syslog_origin_id`, `syslog_source_interface`, `syslog_heartbeat_seconds` | The syslog block onboarding gives every device (NSOT_PLAN P.1): collector address, trap level (default `notifications`), `logging origin-id` (default `hostname`, which the Grafana heartbeat rules key on), source interface (default `Loopback0`) and the EEM heartbeat interval (default 300 s, minimum 60). **`syslog_host` defaults to empty, and onboarding refuses while it is empty**, because a block with no host is silence nobody receives. On the Monitoring profile card since 2026-09-30. `syslog_source_interface` is also the management interface: SNMP traps leave from it, and since 2026-10-07 the profile's management section derives TFTP's and the SSH client's source from it (Phase 2, P1), where `syslog_host` is configured. |
| `ntp_servers`, `telemetry_receiver`, `snmp_trap_host`, `snmp_exporter_config`, `snmp_exporter_auth` | The monitoring profile's CONNECTORS (NSOT_PLAN P.9, decision 4, 2026-09-30): the proposal derives NTP, telemetry and SNMP from these first, and uses what the fleet agrees on only as a cross-check (a device configured differently is named). `telemetry_receiver` is Telegraf's model-driven listener as `<address>:<port>`; `snmp_exporter_config` is snmp_exporter's file, from which the community of the `snmp_exporter_auth` module is read in memory and never shown. Set in **Settings > Integrations > Monitoring profile** since 2026-09-30 (the operator: they had to be edited into the file by hand, a console step), with the five `syslog_*` keys beside them: validated by the schema on save, and a Test that reads the exporter's auth module (never its value), connects to Telegraf's listener and asks each NTP server, and says one-way syslog and traps are not testable. Empty by default: the proposal falls back to the fleet for a section whose connector is empty, as it did before, and says so. An empty `snmp_exporter_config` is a job-health `unset_guard` row (it is in `GUARD_GATING_EMPTY_DEFAULTS`), so the fallback is visible beyond the preview. |

**One of these is an honest gap rather than a decision**, and is recorded as
such so it is not mistaken for settled: `kea_services` should be in the Kea
card. (The `clab_*` group was the other, and left the product with C663.)

**`syslog_host` is the third deliberate exception to that rule.** Before
P.1, onboarding gave a device no logging at all, which is how r6 came to have
none. Reproducing that by default would reproduce the gap. So an unset host
is a named refusal at plan time ("syslog_host is not configured"), recorded in
`GUARD_GATING_EMPTY_DEFAULTS`, and never a device onboarded silent.

**`netbox_excluded_vrfs` was the second deliberate exception to "every new
default reproduces the behaviour that predates the setting"**, after
`netbox_allow_writes`: it defaulted to one emulator's VRF, because the prior
behaviour was an error NetBox returns. C663 (2026-10-11) made the default
empty, since a network with no emulator has no such VRF and the product names
no lab; the host that relied on the old default ratified its value first, so
nothing there moved.

---

## Settings that are not in the schema at all

`anthropic_api_key` (`.env`) was written by `/settings` into **another
store**; since the AI family's removal (D15, 2026-10-14) `/settings` refuses
it by name, and D15's host step deleted the key's `.env` line. The four
`jenkins_*` fields used to be written to `data/jenkins_checks.json`; since
P.4 `/settings` refuses them by name.
They are not schema keys, `write_settings()` does not touch them, and
`SECRET_KEYS` deliberately does not list them — see [SECRETS.md](SECRETS.md).
