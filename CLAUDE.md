# CLAUDE.md — Agentic Network Management and Automation (NMAS)

## Project Overview

Flask-based web application for managing, automating, and monitoring Cisco IOS
network devices. Built by Dustin Marchak as a capstone/school project. The app is
a single-host management tool — not a multi-tenant SaaS — so there is no built-in
auth system.

**Stack:** Python 3.10+, Flask, Flask-SocketIO, Netmiko/Paramiko (SSH), Anthropic
Claude API (AI agent), vis.js (topology), Bootstrap 5, Jenkins CI integration,
NetBox (source of truth).

The project is mid-way through a planned conversion into a Network Source of
Truth (NSoT) framework. **[docs/NSOT_PLAN.md](docs/NSOT_PLAN.md) is the governing
spec for that work** — read it before starting any NSoT phase. Phase 0 is
complete; Phases 1–5 are not started.

## Module map

Line counts are accurate as of Phase 0 (2026-09-20). Everything listed is
tracked in git.

### Core
- **[app.py](app.py)** (5,301) — Flask routes and SocketIO handlers. Monolithic
  by design for pre-existing features; **new routes go in `routes/` instead**.
- **[modules/ai_assistant.py](modules/ai_assistant.py)** (7,195) — AI agent core:
  tool definitions, `run_chat()`, golden config management, read-first workflow
- **[modules/agent_runner.py](modules/agent_runner.py)** (1,363) — background
  autonomous agent daemon; pauses when the user opens chat
- **[modules/netbox_client.py](modules/netbox_client.py)** (3,231) — NetBox
  IPAM/DCIM client. Reads freely; **writes are gated** (see below)
- **[modules/topology.py](modules/topology.py)** (1,207) — CDP/OSPF/BGP/DMVPN
  discovery; vis.js graph with hub/spoke labels
- **[modules/jenkins_runner.py](modules/jenkins_runner.py)** (1,196) — Jenkins
  pipeline create/trigger/poll/diagnose
- **[modules/pipeline.py](modules/pipeline.py)** (1,159) — 9-stage
  `PipelineRunner` (NetBox query → render → CI gate → snapshot → diff → deploy →
  snapshot → verify/rollback → audit). **Built but not wired into the UI**: only
  its audit-log readers are called from `app.py`. Phase 3 wires it in.
- **[modules/configure.py](modules/configure.py)** (1,093) — IOS config generator
  for 10 feature types; also generates Jenkins verification scripts and pipeline XML
- **[modules/pipeline_builder.py](modules/pipeline_builder.py)** (745) — Jenkins
  pipeline XML builder for per-function verification

### Collectors and checks
- **[modules/snmp_collector.py](modules/snmp_collector.py)** (763) — SNMP v1/v2c
  trap receiver + OID polling
- **[modules/netflow_collector.py](modules/netflow_collector.py)** (381)
- **[modules/check_runner.py](modules/check_runner.py)** (618) — standalone
  verification entry point invoked by Jenkins
- **[modules/drift_check.py](modules/drift_check.py)** (415) — drift checker
  needing no Claude API; diffs against golden config
- **[modules/collector_config.py](modules/collector_config.py)** (238) — per-list
  collector settings, including trap/NetFlow ports

### NSoT / Phase 0–1 additions
- **[modules/settings_schema.py](modules/settings_schema.py)** (314) — settings
  defaults, JSON Schema validation, and forward migration
- **[modules/netbox_guard.py](modules/netbox_guard.py)** (276) — NetBox write
  gate, dry-run preview, and created-object provenance
- **[modules/secrets_store.py](modules/secrets_store.py)** (150) — Fernet
  encryption-at-rest for settings secrets
- **[modules/jenkins_shell.py](modules/jenkins_shell.py)** (61) — `bat` vs `sh`
  step selection for generated pipelines
- **[modules/netbox_authz.py](modules/netbox_authz.py)** — one-shot write
  authorization: plan hashing and single-use tokens
- **[modules/inventory/](modules/inventory/)** — per-list inventory source, the
  NetBox→device-dict adapter, and the cache that makes dispatch I/O-free
- **[modules/credentials.py](modules/credentials.py)** — encrypted credential
  profiles and the resolver
- **[modules/nsot/context.py](modules/nsot/context.py)** — `build_render_context()`,
  the single way templates get data
- **[modules/integrations/](modules/integrations/)** — one client per external
  tool (NetBox, Prometheus, Grafana, Loki, Oxidized, Kea, topology service, NSoT
  git, S3). Phase 0 ships `test_connection()` only; Phase 5 adds read clients.
- **[routes/](routes/)** — Flask blueprints: `settings_integrations.py`,
  `netbox_safety.py`, `inventory.py`

### Other
`approval_queue.py`, `config_git.py`, `device.py`, `connection.py`, `bulk_ops.py`,
`backups.py`, `variable_discovery.py`, `event_monitor.py`, `ccie_kb.py`,
`terminal.py`, `commands.py`, `agent_timers.py`, `ai_usage_log.py`, `quick_actions.py`,
`utils.py`, `config.py`

### Templates
`base.html` (2,442 — layout + AI chat panel), `index.html` (8,045 — main
dashboard), `device.html` (1,239 — per-device page), and
`templates/partials/` for new UI.

## Key Architecture Decisions

- **Data storage:** `data/lists/{slug}/` per device list — devices.csv
  (Fernet-encrypted creds), variables.json, golden_configs/, backups/,
  approval_queue.json, jenkins_pipelines.json, config_repo/
- **AI read-first:** the agent checks golden configs and variables before opening
  any SSH session
- **Config push workflow:** backup → push → Jenkins CI → save golden → update
  variables. CI pass = auto-approve.
- **Approval queue:** destructive AI actions go through `approval_queue.py`
- **Connection pool:** Netmiko SSH connections reused via `modules/connection.py`;
  background ping worker tracks online/offline
- **Auto-continue:** the AI agent loops tool calls until the task completes
- **telnetlib shim:** `telnetlib.py` in root — Python 3.13 removed it from stdlib

### NetBox write safety (Phase 0)

NetBox reads are unrestricted. **Writes are fail-closed** and go through exactly
three chokepoints in `netbox_client.py`: `_nb_post`, `_nb_patch`, `_nb_delete`.

Two independent conditions must both hold before any write executes:

1. `netbox_allow_writes` — the **master switch**, meaning "this instance may
   write to NetBox at all". Defaults off. A persistent operator decision; it is
   never flipped as a side effect of confirming an operation.
2. A **single-use authorization token** (`modules/netbox_authz.py`) issued by a
   preview and bound to a hash of that exact plan.

- **Import and Remove still work.** Clicking either runs a read-only dry run
  (allowed regardless of the gate, since it writes nothing) and shows a preview
  of every object that would change.
- **Confirming is one-shot.** Execute consumes the token, recomputes the plan,
  and aborts with "NetBox changed since preview" if the hash differs. Tokens
  expire in 5 minutes and are burned even on a failed validation, so they cannot
  be replayed.
- **The preview count is the executed count**, including dependent objects under
  a device that does not exist yet (placeholder ids) and shared objects counted
  once rather than once per device.
- Every object NMAS **creates** is tagged `nmas-managed` and its id recorded in
  `data/netbox_created_ids.json`. Objects NMAS merely updates are never tagged —
  the tag is injected in `_nb_post` only, never `_nb_patch`.
- **Removal deletes only the intersection** of those two: tagged *and* in NMAS's
  own record. A region, site, VRF, or device a human curated is reported as
  skipped. Removal previously deleted everything in the site regardless of origin.
- Deleting a device list **no longer cascades into NetBox** unless
  `netbox_remove_on_list_delete` is on or the request opts in.

### Inventory sources (Phase 1)

A device list is either `local` (a CSV — the default, and what every
pre-existing list uses) or `netbox`, set per list in
`data/lists/{slug}/source.json`. An absent file means `local`.

- **`load_saved_devices()` is the single dispatch point.** It has ~79 call
  sites across 11 modules; routing the decision through it means bulk ops, the
  terminal, backups, drift, topology, the connection pool and the AI tools all
  work on a NetBox list without changes.
- **Dispatch never performs network I/O.** A background refresh queries NetBox
  and resolves + encrypts credentials once per refresh; dispatch serves finished
  dicts from memory. The adapter returns credentials **still Fernet-encrypted**,
  matching a CSV row, because callers decrypt at use.
- The last good inventory is persisted to `netbox_inventory_cache.json` —
  **identity only, never credentials** — so a restart during an outage still
  yields the last known list, badged stale. Credentials are re-resolved on
  rehydrate.
- **Identity is read-only.** CSV writers refuse, and the UI disables Add Device,
  Delete, Discover→Add and Refresh Hostnames with an "Edit in NetBox" tooltip.
  Drag-and-drop ordering still works, stored in `source.json`.

**Credential resolution** (`modules/credentials.py`), first match wins: device
override → the list's *designated* `credential_list` (one list, never a scan) →
role profile → site profile → default profile. Every device carries
`_cred_source` so the origin is visible. Deleting a designated credential list
warns about dependent lists; "Copy inherited credentials into device overrides"
decouples on demand.

**Incomplete NetBox data:** a device missing `primary_ip4`, an unmapped
platform, or unresolvable credentials is **skipped with a per-device reason**,
never failing the whole list. An unmapped *role* is only a warning — it resolves
to `""` and topology falls back to hostname inference. Set
`platform_default_netmiko_type` to trade a platform skip for a warning.

**Stale devices:** a device that vanishes from NetBox keeps its golden configs
and backups but becomes **inert** — the approval executor, drift checker, and AI
tools refuse to act on it, and its pooled SSH session is closed.

### Settings

All settings live in `data/user_settings.json` with a `settings_schema_version`.
`modules/settings_schema.py` seeds defaults and migrates forward; old keys are
never deleted. **Every new default reproduces the behaviour that predates the
setting** — `netbox_allow_writes` is the one deliberate exception.

Secrets (API tokens, passwords, access keys) are encrypted at rest with the
existing Fernet key via `modules/secrets_store.py`. They are never logged, never
committed, and masked in the UI as write-only fields with a set/unset badge. The
NetBox token was previously stored in plaintext and is upgraded in place on first
run.

### Portability

Development is Windows 11; the deployment target is headless Ubuntu. See
[docs/DEPLOY_LINUX.md](docs/DEPLOY_LINUX.md).

| Setting | Env override | Default |
|---|---|---|
| Bind host | `NMAS_HOST` | `0.0.0.0` |
| Port | `NMAS_PORT` | `5000` |
| Auto-open browser | `NMAS_HEADLESS=1` disables | on |
| TFTP root | `NMAS_TFTP_ROOT` | `C:/TFTP-Root` on Windows, `/srv/tftp` elsewhere |
| Jenkins step shell | — | `bat` |

`config.py` no longer creates the TFTP root at import time. Call
`config.ensure_tftp_root()` at the point of use instead.

## Running the App

```bash
pip install -r requirements.txt
python app.py                      # opens http://127.0.0.1:5000
NMAS_HEADLESS=1 python app.py      # headless (no browser)
```

Settings (API key, integrations, Jenkins, TFTP, server bind) are all configurable
from the UI Settings panel — no restart needed except for bind host/port.

## Tests

```bash
pytest                    # 307 tests
pytest tests/test_netbox_write_gate.py -v
```

`pytest.ini` sets `pythonpath = .`, so both `pytest` and `python -m pytest` work
from the repo root. (Before Phase 0 only the latter did.)

| File | Covers |
|---|---|
| `test_pipeline.py` | 9-stage pipeline, stage ordering, CI gate |
| `test_pipeline_builder.py` | Jenkins pipeline XML generation |
| `test_netbox_write_gate.py` | write gate, dry run, provenance-based removal |
| `test_netbox_authz.py` | one-shot tokens, plan hashing, stale-plan abort |
| `test_netbox_preview_fidelity.py` | preview counts == executed counts; tag scope |
| `test_netbox_inventory.py` | NetBox-sourced lists: shape fidelity, skips, stale devices |
| `test_device_lookup.py` | exact-name → IPAM resolution; never a fuzzy first hit |
| `test_render_context.py` | render context, interface IPs, template rendering |
| `tests/fake_netbox.py` | in-memory NetBox API (not a test module) |
| `test_settings_migration.py` | schema, secret encryption, forward migration |
| `test_integrations_base.py` | optional-integration behaviour, secret masking |
| `test_portability.py` | Jenkins step shell, TFTP root, env overrides |
| `test_no_ip_literals.py` | fails if an IPv4 literal appears in the new packages |

All HTTP and SSH is mocked; **no test touches a live network.**

## Conventions

- New routes → `routes/` blueprints, registered by `routes.register_blueprints(app)`.
  `app.py` and `index.html` must not grow beyond registration and `{% include %}`.
- New UI → `templates/partials/`, Bootstrap 5 only, matching the existing card /
  tab / modal / badge patterns. No new CSS framework. Front-end libraries are
  vendored into `static/`, never loaded from a CDN (air-gapped networks).
- Return dicts shaped `{"ok": bool, "error": str, ...}`
- Module-level `log = logging.getLogger(__name__)`
- Use `pathlib` / `os.path`, never hardcoded separators or drive letters
- **No IPv4 literals** in `modules/integrations/`, `modules/nsot/`, or `routes/` —
  `test_no_ip_literals.py` enforces this
- Fernet key at `data/key.key` — back it up; losing it makes stored credentials
  and secrets unrecoverable
- `.env` holds `ANTHROPIC_API_KEY`; excluded from git

## Things to Keep in Mind

- Jenkins pipelines default to Windows `bat` steps; switch to `sh` in Settings for
  a Linux Jenkins agent. Generated XML is byte-identical to pre-Phase-0 output
  while the default is unchanged.
- `telnetlib.py` shim must stay in the root for Python 3.13+ compatibility
- The app is intended for a trusted lab/management network — no auth layer. When
  exposing it, bind to a specific address behind a reverse proxy or tunnel.
- Silent failure is the dominant failure mode in this stack. Every integration
  call must log and surface its failures rather than swallowing them.
- `modules/pipeline.py` and `modules/pipeline_builder.py` are real, tested, and
  mostly unused. Don't mistake them for dead code — Phase 3 depends on them.

## Known defects deferred to later phases

Verified during Phase 0, deliberately not fixed yet. Recorded in full in
[docs/NSOT_WRITEUP_NOTES.md](docs/NSOT_WRITEUP_NOTES.md).

- Golden configs live in two unsynchronized stores; `config_git.write_and_stage`
  stages without committing, so "current golden" and the latest commit can
  disagree indefinitely (Phase 2)
- The volatile-config-line prefix list is duplicated across six modules (Phase 2)
- `_list_golden_configs` parses IPs with an IPv4-only regex, so a device reached
  over IPv6 mis-parses (Phase 2)
- AI prompt examples reference another project's PE/P/MPLS topology (Phase 3)
