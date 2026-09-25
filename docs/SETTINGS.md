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

---

## Surfaced in the UI

| Group | Where |
|---|---|
| `netbox_*` | Settings → NetBox |
| `prometheus_*`, `grafana_*`, `loki_*`, `oxidized_*`, `kea_*`, `topology_service_*`, `s3_*`, `nsot_git_*`, `proxmox_*` | Settings → Integrations |
| `flask_host`, `flask_port`, `auto_open_browser`, `tftp_root`, `tftp_server_ip`, `jenkins_step_shell` | Settings → Server |
| `collector_*`, `monitoring_*`, `promql_*` | Settings → Monitoring |
| `ai_enabled`, **`background_agent_enabled`**, `wf_*` | Settings → AI |
| `require_identity_for_*`, `require_person_for_*`, `service_allowed_operations`, `cf_access_*` | Settings → Security posture (**read-only**, see below) |

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
| `oxidized_router_db` | A path on the Oxidized host, set once at installation alongside the sudoers entry for `nmas-oxidized-cred`. |
| `oxidized_rest_url` | **DEPRECATED and read by nothing, and it gates nothing.** It named the same fact as `oxidized_url` — the oxidized-web base URL, which both used to fetch `nodes.json` from. `oxidized_url` is the one key; it has a form under Settings > Integrations. A value left here is not adopted: the persistence chain refuses and names the move, because a settings write nobody asked for would hide the rename. Kept only because schema keys are never deleted. |
| `clab_host`, `clab_configs_dir`, `clab_sync_script`, `clab_launch_patch` | Containerlab paths on the lab host, used by the redeploy tooling. They describe a machine, not a preference. |
| `yang_push_script` | Path to the telemetry helper; same. |
| `netbox_excluded_vrfs` | VRFs whose **addresses** the NetBox import does not model, default `["clab-mgmt"]`. It describes the emulator, not a preference — every containerlab node answers on the same internal management address, and NetBox enforces global uniqueness, so importing them is not representable rather than merely untidy (measured: one created, four refused with *"Duplicate IP address found in global table"*). A setting rather than a constant because another lab will name its management VRF something else. Belongs in a future "lab host" section with the `clab_*` group rather than as a field of its own. |
| `clab_declared_unmapped` | Startup-config files that are deliberately unmapped, per list, with who and why. **Written only by `nmas-retire`**, read by the clab sync map so `--reconcile` reports a retired device's frozen file as declared rather than as unmapped for ever. A form would let a person declare a file unmapped without retiring anything, which is how a declaration comes to hide a real gap. |
| `syslog_host`, `syslog_trap_level`, `syslog_origin_id`, `syslog_source_interface`, `syslog_heartbeat_seconds` | The syslog block onboarding gives every device (NSOT_PLAN P.1): collector address, trap level (default `notifications`), `logging origin-id` (default `hostname`, which the Grafana heartbeat rules key on), source interface (default `Loopback0`) and the EEM heartbeat interval (default 300 s, minimum 60). **`syslog_host` defaults to empty, and onboarding refuses while it is empty**, because a block with no host is silence nobody receives. **This is a gap, not a decision**: it belongs with the other network-wide defaults in 7.7's settings split. |

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

`anthropic_api_key` (`.env`) and the four `jenkins_*` fields
(`data/jenkins_checks.json`) are written by `/settings` into **other stores**.
They are not schema keys, `write_settings()` does not touch them, and
`SECRET_KEYS` deliberately does not list them — see [SECRETS.md](SECRETS.md).
