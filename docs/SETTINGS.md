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
| `prometheus_*`, `grafana_*`, `loki_*`, `oxidized_*`, `kea_*`, `topology_service_*`, `s3_*`, `nsot_git_*` | Settings → Integrations |
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
| `oxidized_router_db`, `oxidized_rest_url` | Paths on the Oxidized host, set once at installation alongside the sudoers entry for `nmas-oxidized-cred`. Changing one without the other breaks the helper. |
| `clab_host`, `clab_configs_dir`, `clab_sync_script`, `clab_launch_patch` | Containerlab paths on the lab host, used by the redeploy tooling. They describe a machine, not a preference. |
| `yang_push_script` | Path to the telemetry helper; same. |

**Two of these are honest gaps rather than decisions**, and are recorded as
such so they are not mistaken for settled: `kea_services` should be in the Kea
card, and the `clab_*` group would be better as a small "lab host" section
than as four keys nobody can find.

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
