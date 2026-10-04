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

---

## Surfaced in the UI

| Group | Where |
|---|---|
| `netbox_*` | Settings → NetBox |
| `prometheus_*`, `grafana_*`, `loki_*`, `oxidized_*`, `kea_*`, `topology_service_*`, `s3_*`, `nsot_git_*`, `proxmox_*` | Settings → Integrations |
| `flask_host`, `flask_port`, `auto_open_browser`, `tftp_root`, `tftp_server_ip` | Settings → Server |
| `collector_*`, `monitoring_*`, `promql_*` | Settings → Monitoring |
| `ai_enabled`, **`background_agent_enabled`**, `wf_*` | Settings → AI |
| `require_identity_for_*`, `require_person_for_*`, `service_allowed_operations`, `cf_access_*` | Settings → Security posture (**read-only**, see below) |

`grafana_token_expires` and `proxmox_token_expires` are the tokens' DECLARED expiries
(YYYY-MM-DD, or `never`), because neither token can read its own (P.21, C380). They are on
today's Settings → Integrations as a **recorded exception** to the no-new-v1 rule, named with
their reason in `tests/test_no_new_v1_capability.py`, and they move at cutover; a v2 Settings
page waits on P.8.

`background_agent_enabled` was added to the form in 3.2d. It had **no control
at all**: `/settings` accepted it and nothing ever sent it. See the warning
below.

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

## File-only, deliberately

Each with a reason. These are settable by editing
`data/user_settings.json` and restarting where noted.

| Setting | Why not in the UI |
|---|---|
| `platform_map` | A nested mapping of platform → driver, template dir, transport, NETCONF support. A form for it would be a worse JSON editor. Editing it wrongly breaks every deploy, and it changes when a **vendor** is added, not when an operator changes their mind. |
| `role_map` | Same shape, same reasoning: NetBox role slug → internal role. |
| `verify_settle_windows` | Per-protocol convergence timings, nested. Changed when a protocol's behaviour is *measured*, not adjusted by feel — a slider would invite the second. |
| `cf_access_service_labels` | A mapping of service Client ID → human label, edited when a service token is issued, which is already a host-side operation. |
| `cf_access_jwks_ttl` | Cache lifetime for Cloudflare's signing keys. A wrong value degrades verification silently; the default is correct and there is no operational reason to change it. |
| `deploy_max_workers` | Deploy concurrency, default 1. Raising it changes the blast radius of a bad plan. Deliberately awkward. |
| `deploy_verify_failure_limit` | Circuit-breaker threshold. Same reasoning. |
| `nsot_config_read_timeout` | Measured against real device behaviour (5.5s idle, >16s after `write memory`). Tuned from evidence, not preference. |
| `nsot_device_tag_retention` | Tag pruning depth. Housekeeping; no operational decision attached. |
| `platform_default_netmiko_type` | Trades a platform **skip** for a warning. Setting it makes unknown platforms deploy with a guessed driver — an explicit, considered risk, and an easy one to click past in a form. |
| `kea_services` | A list (`dhcp4`, `dhcp6`). Belongs in the Kea card as a multi-select; **not yet built** — this is a gap, not a decision. |
| `grafana_history_datasource_uid` | C406: the Grafana datasource (by UID) whose PromQL endpoint keeps metrics past the live store's retention (Thanos Query, Mimir, ...). Empty (the default) means none: a panel range past the live store's retention is refused naming it, as before. Set at installation, alongside Grafana's datasources; no form yet, because a new control belongs on a v2 Settings screen with a signed-off mockup. When set, the device and Monitoring panels read a longer range from it and say so in the panel's foot line. |
| `metrics_live_retention_days` | C406: how long the LIVE PromQL store (the dashboards' own datasource) keeps metrics, in days; default 90, the value measured on the host 2026-09-30. A panel range longer than this reads `grafana_history_datasource_uid`. It describes the store, so it changes when the store's retention changes. |
| `oxidized_router_db` | A path on the Oxidized host, set once at installation alongside the sudoers entry for `nmas-oxidized-cred`. The same path is pinned for the helper in the root-owned `/etc/nmas/oxidized-cred.conf` (C414): as root the helper edits only that file, so changing this setting also needs the pin changed, and until they agree the helper's job-health row and the rotation's preflight name both. |
| `oxidized_rest_url` | **DEPRECATED and read by nothing, and it gates nothing.** It named the same fact as `oxidized_url` — the oxidized-web base URL, which both used to fetch `nodes.json` from. `oxidized_url` is the one key; it has a form under Settings > Integrations. A value left here is not adopted: the persistence chain refuses and names the move, because a settings write nobody asked for would hide the rename. Kept only because schema keys are never deleted. |
| `clab_host`, `clab_configs_dir`, `clab_sync_script`, `clab_launch_patch` | Containerlab paths on the lab host, used by the redeploy tooling. They describe a machine, not a preference. |
| `clab_labs` | The device → lab map: per lab, its configs directory, launch patch and host, read only by `clab_target_for()`. A nested mapping edited when a LAB is set up, on the host, like the four keys above; a form would be a worse JSON editor. Recorded here on 2026-09-28: until then it was "documented" only by mentions elsewhere in `docs/`, which the coverage check counted (C155). |
| `yang_push_script` | Path to the telemetry helper; same. **Its script was retired on 2026-09-26 (C31)**, so on the deployment host it is declared not applicable rather than left empty. |
| `jenkins_step_shell` | **DEPRECATED and read by nothing** (P.4 removed Jenkins, and with it the pipeline generators that chose `bat` or `sh`). Its control is gone from Settings → Server; kept only because schema keys are never deleted. |
| `wf_run_jenkins`, `wf_save_golden` | **DEPRECATED and read by nothing but the agent's prompt text** (P.4 removed Jenkins). They told the agent whether to run Jenkins after a push and whether to save a golden after CI passed. Their switches are gone from the form; kept only because schema keys are never deleted. Stage 8.5 removes them from the prompt. |
| `settings_not_applicable` | Guard-gating settings declared NOT APPLICABLE on this host, with who, when and why (C31). **Written only by `scripts/nmas-setting-not-applicable`**, on the host, like the identity gates: a declaration changes what a check means, so a browser session must not be able to make one. Job health reads it as `not_applicable`; a key both set and declared is a `contradiction`. |
| `netbox_excluded_vrfs` | VRFs whose **addresses** the NetBox import does not model, default `["clab-mgmt"]`. It describes the emulator, not a preference — every containerlab node answers on the same internal management address, and NetBox enforces global uniqueness, so importing them is not representable rather than merely untidy (measured: one created, four refused with *"Duplicate IP address found in global table"*). A setting rather than a constant because another lab will name its management VRF something else. Belongs in a future "lab host" section with the `clab_*` group rather than as a field of its own. |
| `netbox_remove_on_list_delete` | **DEPRECATED and read by nothing** (C155, the operator's decision, 2026-09-28). Deleting a device list never deletes NetBox objects: removal has one home, the NetBox tab's previewed and confirmed Remove, and a list that still owns recorded objects is refused until they are removed. The switch was removed from Settings → NetBox, and its branch deleted NMAS-created objects with no preview and no confirmation token. Kept only because schema keys are never deleted (removing it would make `write_settings()` refuse the host's file, which holds it). **Nothing to do on the host**: its default is `False` and nothing reads it. It is NOT declared not applicable: that record is for guard-gating settings whose default is EMPTY, and `nmas-setting-not-applicable` refuses this one, correctly ("has a non-empty default, so it is never unset; there is nothing to declare"). |
| `clab_declared_unmapped` | Startup-config files that are deliberately unmapped, per list, with who and why. **Written only by `nmas-retire`**, read by the clab sync map so `--reconcile` reports a retired device's frozen file as declared rather than as unmapped for ever. A form would let a person declare a file unmapped without retiring anything, which is how a declaration comes to hide a real gap. |
| `kea_ztp_fragment`, `kea_dhcp4_config` | P.6 D1: the reservation fragment NMAS owns and the kea-dhcp4 config that includes it. Host paths set once with the host change in [DEPLOY_LINUX.md](DEPLOY_LINUX.md) (the Kea section); they describe a machine, not a preference. **`kea_ztp_fragment` defaults to empty and a `ztp` plan refuses while it is**, because a reservation written anywhere else lives in Kea's memory until its next restart (C49, demonstrated by M5). |
| `syslog_host`, `syslog_trap_level`, `syslog_origin_id`, `syslog_source_interface`, `syslog_heartbeat_seconds` | The syslog block onboarding gives every device (NSOT_PLAN P.1): collector address, trap level (default `notifications`), `logging origin-id` (default `hostname`, which the Grafana heartbeat rules key on), source interface (default `Loopback0`) and the EEM heartbeat interval (default 300 s, minimum 60). **`syslog_host` defaults to empty, and onboarding refuses while it is empty**, because a block with no host is silence nobody receives. On the Monitoring profile card since 2026-09-30. |
| `ntp_servers`, `telemetry_receiver`, `snmp_trap_host`, `snmp_exporter_config`, `snmp_exporter_auth` | The monitoring profile's CONNECTORS (NSOT_PLAN P.9, decision 4, 2026-09-30): the proposal derives NTP, telemetry and SNMP from these first, and uses what the fleet agrees on only as a cross-check (a device configured differently is named). `telemetry_receiver` is Telegraf's model-driven listener as `<address>:<port>`; `snmp_exporter_config` is snmp_exporter's file, from which the community of the `snmp_exporter_auth` module is read in memory and never shown. Set in **Settings > Integrations > Monitoring profile** since 2026-09-30 (the operator: they had to be edited into the file by hand, a console step), with the five `syslog_*` keys beside them: validated by the schema on save, and a Test that reads the exporter's auth module (never its value), connects to Telegraf's listener and asks each NTP server, and says one-way syslog and traps are not testable. Empty by default: the proposal falls back to the fleet for a section whose connector is empty, as it did before, and says so. An empty `snmp_exporter_config` is a job-health `unset_guard` row (it is in `GUARD_GATING_EMPTY_DEFAULTS`), so the fallback is visible beyond the preview. |

**Two of these are honest gaps rather than decisions**, and are recorded as
such so they are not mistaken for settled: `kea_services` should be in the Kea
card, and the `clab_*` group would be better as a small "lab host" section
than as four keys nobody can find — `netbox_excluded_vrfs` belongs in that
same section when it exists.

**`syslog_host` is the third deliberate exception to that rule.** Before
P.1, onboarding gave a device no logging at all, which is how r6 came to have
none. Reproducing that by default would reproduce the gap. So an unset host
is a named refusal at plan time ("syslog_host is not configured"), recorded in
`GUARD_GATING_EMPTY_DEFAULTS`, and never a device onboarded silent.

**`netbox_excluded_vrfs` is the second deliberate exception to "every new
default reproduces the behaviour that predates the setting"**, after
`netbox_allow_writes`, and for a different reason. The prior behaviour is not
a behaviour anybody chose: it is an error NetBox returns. Defaulting the
exclusion to empty would preserve that error on every install in the name of
a rule written to prevent surprises.

---

## ⚠ Pause is not disable

`pause_agent()` sets an **in-memory** `threading.Event`. It persists nothing,
so a pause is lost on the next restart and the background agent resumes.

`background_agent_enabled` is the persistent switch, defaults **True**, and
until 3.2d had no control in the interface.

The two look like one switch in the UI and only the invisible one survives a
restart. **If the agent was "disabled" by the Agent tab's Pause button, it has
been running again after every restart since.** That is worth checking against
the Stage 8.4 premise, which assumes the background agent has been off
throughout the NSoT work — it is the same shape as the drift scheduler's
in-memory `next_ts`, where state that looked persistent was not.

---

## Settings that are not in the schema at all

`anthropic_api_key` (`.env`) is written by `/settings` into **another
store**. The four `jenkins_*` fields used to be written to
`data/jenkins_checks.json`; since P.4 `/settings` refuses them by name.
They are not schema keys, `write_settings()` does not touch them, and
`SECRET_KEYS` deliberately does not list them — see [SECRETS.md](SECRETS.md).
