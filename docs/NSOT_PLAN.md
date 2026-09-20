# Agentic NMAS → Network Source of Truth (NSoT): Implementation Plan

> **For Claude Code:** This is the governing spec for the NSoT work. Commit it to
> `docs/NSOT_PLAN.md`. Work **one phase at a time**. For each phase:
> (1) re-read this file and the relevant code, (2) post a short implementation
> plan and list anything in Section 3 that you found to be inaccurate,
> (3) wait for approval, (4) implement, (5) run and extend tests, (6) update
> `CLAUDE.md`, `docs/CHANGELOG.md`, and `docs/NSOT_WRITEUP_NOTES.md`, (7) stop and
> summarize. Do not start the next phase without explicit go-ahead.

---

## 1. Goal

Turn Agentic NMAS from a free-form management tool into an industry-style
**network automation framework** built around a Network Source of Truth. The
tool is the single web GUI and control point for every other tool: it reads intent
from NetBox, stores and renders Jinja2 templates, versions everything in git,
pushes config through code, and shows data from the monitoring stack.

This work satisfies **CSCI 5840 Labs 4 & 5, Part 1, Objective 1** (Dr. Perigo):

| Lab objective | Requirement | Phase |
|---|---|---|
| 1.1 Version control & change management | Repo for all existing configs/files and future programming modules | 2 |
| 1.2a(i) Web GUI | Incorporate the monitoring and visualization from previous labs | 5 |
| 1.2a(ii) Web GUI | Easy input for new devices/sites and changes (e.g. new device, vendor, WAN IP, routing protocol, which J2 template) | 4 |
| 1.3 Templatize existing config | Netcopa-style: existing config → YAML → J2 | 3 |
| 1.4 Golden configs | Save golden config **with timestamp** | 2 |
| Extra credit | Templates for different vendors | 3 (platform-keyed template dirs) |

Deliverables: a write-up of how the NSoT was built plus a demo video. Keep
`docs/NSOT_WRITEUP_NOTES.md` current with design decisions, trade-offs, and the
demo-worthy flows added in each phase.

**Part 2 (future, do NOT implement now, but do not design against it):** IPAM,
stored device credentials with **automatic periodic password rotation** (2FA as
extra credit), a DevOps pipeline (Jenkins) where code/config changes
automatically trigger tests, and network automation apps for health checks
(neighborships, route table, CPU, IP connectivity), config changes, and
troubleshooting. See Section 7.

---

## 2. Non-negotiable constraints

1. **Preserve every existing capability.** Existing device lists, routes, the AI
   agent and its tools, bulk ops, terminal, backups, drift, topology, Jenkins,
   SNMP/NetFlow collectors, the configure tab (`/configure/apply`), and the Git tab
   must keep working. The existing local-list mode stays the **default**. New
   behavior is opt-in per device list or via settings.
2. **Preserve styling.** Keep Bootstrap 5 and the existing visual language.
   New UI copies the existing card, tab, modal, badge, and button patterns, and
   dark mode if present. No new CSS framework.
3. **Network-agnostic.** No lab-specific addresses, hostnames, ports, metric
   names, Loki label names, or dashboard UIDs in code. Every external endpoint,
   credential, query template, and identity mapping is set by the user in
   **Settings**. Section 8 describes the reference lab for *testing only*.
   Add a pytest that scans the new packages (`modules/integrations/`,
   `modules/nsot/`, `routes/`) for IPv4 literals and fails if it finds any.
4. **Every integration is optional.** If a tool is unconfigured or unreachable,
   the UI shows "Not configured — set in Settings" or a clear error badge. Pages
   still render, and nothing raises into the request handler.
5. **Cross-platform.** Development stays on Windows 11. Deployment target is
   Ubuntu Linux (headless, systemd). Use `pathlib`/`os.path`, not hardcoded
   separators or drive letters.
6. **Secrets.** All tokens, passwords, and secret values are encrypted at rest
   with the existing Fernet key (`data/key.key`). They are never logged, never
   written to git, never sent to the AI provider, and masked in the UI
   (write-only fields with a "set/unset" indicator).
7. **Code organization.** `app.py` (5,247 lines) and `templates/index.html`
   (8,076 lines) do not grow beyond blueprint registration and `{% include %}`
   lines. New routes go in Flask Blueprints under `routes/`. New UI goes in
   partial templates under `templates/partials/`. New logic goes in
   `modules/integrations/` and `modules/nsot/`. Follow existing conventions:
   `{"ok": bool, "error": str, ...}` return dicts and module-level `log =
   logging.getLogger(__name__)`.
8. **Dependencies.** Keep them minimal, pin them in `requirements.txt`, and
   justify each new one in the phase plan. Expected additions: `PyYAML`, plus
   one schema validator (`pydantic` or `jsonschema`; pick one and say why).
   Keep using `subprocess` git as `config_git.py` does; don't add GitPython.
   Front-end libs (e.g. CodeMirror, Chart.js) are **vendored into `static/`**,
   not loaded from a CDN, so the tool works on air-gapped networks.
9. **Tests.** Extend `tests/` with pytest. Mock all HTTP and SSH calls; no test
   touches a live network. Existing tests must keep passing.

---

## 3. Current-state findings (verify before acting; report any that are wrong)

These come from a review of `main` at `92fcbc8`.

1. **The NetBox data flow is inverted.** `netbox_client.sync_list_to_netbox()`
   parses golden configs (`_scan_device_from_golden`) and **pushes** regions,
   sites, VRFs, devices, interfaces, IPs, and tunnels into NetBox.
   `remove_list_from_netbox()` deletes the list's region, site, VRF, and devices.
   The inventory itself lives in encrypted CSVs (`device.py`, fields `hostname,
   device_type, ip, username, password, secret, role`). The target model is the
   reverse: NetBox holds intent and the tool reads it.
2. **Data-loss hazard.** The reference NetBox was populated by hand from the
   design document. Running Sync or Remove against it could overwrite or delete
   curated records. Phase 0 must gate both.
3. **The Jinja2 pipeline is built but not wired in.** `modules/pipeline.py`
   implements a 9-stage `PipelineRunner` (NetBox query → Jinja2 render → CI
   gate → pre-snapshot → diff → deploy → post-snapshot → verify/rollback →
   audit). It is only called from `tests/test_pipeline.py`.
   `/configure/apply` calls `configure.generate_config_commands()` directly.
   `config_templates/` does not exist.
4. **The render context is incomplete.** `_render_jinja2()` passes only
   `params` and `netbox=` a compact device dict (`_compact_device`: includes
   `local_context_data`, but **not** the merged `config_context`). Stage 1
   fetches interfaces but never passes them to the template, and
   `_compact_interface` has no IP addresses.
5. **Device lookup can pick the wrong device.** `netbox_get_device()` falls
   back to `q=` fuzzy search and takes the first hit, so a partial match could
   render a template against the wrong device.
6. **Golden configs live in two unsynchronized stores.**
   `ai_assistant._save_golden_config_file` does two writes:
   - It **overwrites** `data/lists/{slug}/golden_configs/{hostname}.cfg`, with a
     header `! Golden config — <host> (<ip>)` / `! Saved: <local time>` /
     `! Source: ...`.
   - It then calls `config_git.write_and_stage()`, which writes a
     header-stripped copy to `data/lists/{slug}/config_repo/{hostname}.cfg` and
     **stages it without committing**.

   Commits happen only when a user commits manually from the Git tab (optionally
   linking a Jenkins pipeline via `pipeline_commits.json`). As a result:
   - The "current golden" and the latest commit can disagree indefinitely.
   - Golden history exists only if someone remembered to commit.
   - `_list_golden_configs` reports `saved_at` from **file mtime**, not from
     history.
   - Devices are found by **scanning file headers for the IP**
     (`_find_golden_config_file`).
   - The volatile-header prefix list is duplicated in `config_git.py`,
     `drift_check.py`, `pipeline.py`, `agent_runner.py`, `ai_assistant.py`
     (~L5281), and `app.py` (~L1521).
   - `golden_configs_save_all` calls `write_and_stage` a second time after
     `_save_golden_config_file` already did.
7. **The git layer is a good foundation.** `config_git.py` already has an
   idempotent `init -b main`, a subprocess wrapper with a timeout, commit log
   and commit diff readers, and a Git tab UI. Phase 2 **redesigns this module
   in place** rather than adding a second repo system. It has no remote, no
   structured metadata, no tags, and no locking, and multiple writers (UI
   routes, the approval queue, the background AI agent) can hit
   `.git/index.lock` concurrently.
8. **Hardcoded environment assumptions:**
   - `config.py`: `TFTP_ROOT = "C:/TFTP-Root"`, `_DEFAULT_TFTP_SERVER_IP =
     "192.168.0.30"`, `FLASK_HOST = "0.0.0.0"`, `FLASK_PORT = 5000`
   - `app.py`: `webbrowser.open()` at startup
   - Jenkins pipelines emit Windows `bat` steps (`jenkins_runner.py`,
     `pipeline_builder.py`, `check_runner.py` docstrings)
9. **No integration with external monitoring tools.** Nothing references
   Prometheus, Loki, Grafana, Oxidized, Kea, Thanos, or external topology
   services. The tool runs parallel implementations instead: a trap receiver
   (UDP 1162), a NetFlow collector (9996), a pysnmp poller, CDP/LLDP topology,
   and its own backup history.
10. **`CLAUDE.md` is stale.** It says there is no test suite, lists old line
    counts, describes committed modules as untracked, and doesn't mention
    `pipeline.py` or `pipeline_builder.py`.
11. **AI prompt examples use another project's topology.** `ai_assistant.py`
    examples reference PE/P/MPLS devices from a different project. This is
    harmless, but those examples should become generic when the prompts are
    next edited.

---

## 4. Target architecture

### 4.1 Data ownership (one owner per fact)

| Data | Owner | Tool's role |
|---|---|---|
| Sites, devices, manufacturer/platform/device type, role, interfaces, IPs, VLANs, prefixes | **NetBox** | Read. Writes only through the onboarding wizard (Phase 4) and the explicit, gated import (Phase 0). |
| Protocol and service config (routing, SNMP, NTP, logging, AAA, VRRP, relays, …) | **NSoT git repo** (YAML `host_vars` / `group_vars`) | Read and write through the GUI; every save is a commit. |
| Jinja2 templates | **NSoT git repo** (`templates/<platform>/`) | CRUD through the GUI; every save is a commit. |
| Golden configs (timestamped via commits and tags) | **NSoT git repo** (`golden/<device>.cfg`) | Written by the pipeline, the GUI, and the AI via the approval queue. |
| Credentials and secret values referenced by templates | **Local encrypted store** | Never in git or YAML. |
| Metrics, logs, config history, leases, topology | **External tools** (Prometheus/Thanos, Loki, Grafana, Oxidized, Kea, topology service) | Read-only consumer. |

**Precedence rule:** if NetBox models a fact (hostname, interface IP,
description, VLAN membership), templates take it from NetBox, never from YAML.
YAML holds only what NetBox doesn't model. If the extractor (Phase 3) finds a
config value that conflicts with NetBox, it reports a reconciliation item. It
never silently writes either side.

### 4.2 Render context contract

`modules/nsot/context.py::build_render_context(device_name) -> dict` is the only
way templates get data. The pipeline, render previews, the onboarding wizard,
and the AI tools all use it.

```python
{
  "device":     {...},   # full NetBox device incl. rendered config_context,
                         # platform, role, site, primary_ip4/6, custom_fields, tags
  "interfaces": [...],   # NetBox interfaces, each with ip_addresses [...] (v4+v6),
                         # mode, untagged/tagged VLANs, enabled, description, lag, vrf
  "site":       {...},   # NetBox site
  "vars":       {...},   # merged YAML, lowest→highest precedence:
                         # group_vars/all → platform_<slug> → role_<slug>
                         # → site_<slug> → host_vars/<device>
  "params":     {...},   # operator inputs from the UI for this run
}
# plus a Jinja global:  secret("name")  → resolves from the encrypted store at
# render time; the rendered output is treated as sensitive and masked in UI/logs
```

Templates use `StrictUndefined`, `trim_blocks`, and `lstrip_blocks` (as
`pipeline.py` already does). Template errors surface to the UI with file name
and line number.

### 4.3 NSoT repository layout (the evolved per-list `config_repo`)

Each device list's existing `data/lists/{slug}/config_repo/` becomes that
network's NSoT repo. The repo path is overridable in Settings (e.g. to keep it
outside `data/`).

```
config_repo/
├── README.md                 # auto-generated index: device, platform, current golden
│                             # commit + timestamp, last drift result (regenerated per commit)
├── .gitattributes            # *.cfg *.j2 *.yml text eol=lf  (Windows dev, Linux deploy)
├── .nsot/
│   ├── manifest.json         # device name ↔ mgmt IP ↔ NetBox id ↔ platform
│   └── schema_version
├── golden/<device>.cfg       # approved baseline: ONE file per device,
│                             # history = git history (see Phase 2)
├── intended/<device>.cfg     # rendered from templates (Phase 3; secrets masked)
├── host_vars/<device>.yml    # Phase 3
├── group_vars/               # Phase 3: all.yml, platform_<slug>.yml, role_<slug>.yml, site_<slug>.yml
├── templates/<platform_slug>/   # Phase 3: base.j2, _ospf.j2, _rip.j2, _bgp.j2, _macros.j2, ...
└── infra/                    # user-managed: topology files, startup configs, Kea,
                              # Prometheus, Alloy, etc.; shown in the repo browser, not generated
```

**No timestamped copies of files.** In a git repo, `r1-2026-09-20.cfg`-style
copies duplicate what commits already do and make diffs useless. Timestamps
live in commits and tags (Phase 2).

The remote is optional: a local repo is a complete version control system, and
off-host durability comes from the S3 archive (Section 5, Phase 2). When a
remote is configured, push after commit (if enabled); on a non-fast-forward,
surface the conflict and stop. Never force-push.

### 4.4 Platform map (Settings, seeded with defaults, user-editable)

NetBox platform slug → `{netmiko_device_type, template_dir, deploy_transport
(ssh|netconf), config_normalizer, supports_netconf, prometheus_cpu_query}`.
Seed defaults for Cisco IOS-XE (router) and Cisco IOS (L2 switch). Unknown
platforms fall back to SSH with no templates and a visible warning. This map is
what makes multi-vendor templates (extra credit) a configuration change rather
than a code change.

---

## 5. Settings: the Integrations panel

Add an **Integrations** section to Settings via `routes/settings_integrations.py`
and `templates/partials/settings_integrations.html`. Back it with
`modules/integrations/base.py`, a shared client base class providing: config
load/save, a `requests.Session` with retry and timeout (default 5 s,
configurable), TLS verify toggle, `test_connection()`, and uniform
`{"ok", "error"}` results.

| Integration | Fields | Test action |
|---|---|---|
| NetBox (migrate existing keys) | URL, token (encrypted), auth scheme, verify TLS, **allow writes** (default off) | `GET /api/status/` |
| Prometheus / Thanos Query | URL, optional basic auth/bearer, verify TLS | `GET /api/v1/status/buildinfo` |
| Grafana | Base URL, per-view dashboard URL templates with `{hostname}` / `{ip}` placeholders, embed mode (link / iframe) | HEAD base URL |
| Loki | URL, auth, **LogQL selector template** with `{ip}` / `{hostname}` placeholders | `GET /ready` |
| Oxidized (oxidized-web REST) | URL, auth, node identity (name / IP) | `GET /nodes.json` |
| Kea Control Agent | URL, auth, services (dhcp4 / dhcp6) | `status-get` command |
| External topology service | URL, type (JSON graph / SVG / iframe) | GET |
| NSoT git repo | Local path, remote URL, branch, author name/email, auto-push toggle, token or "use host SSH key" | `git ls-remote` |
| S3-compatible archive (MinIO, AWS S3, etc.) | Endpoint, bucket, access key + secret key (encrypted), region, TLS verify, prefix | `bucket_exists` |
| Jenkins (migrate existing) | Existing fields plus **step shell: bat / sh** | existing |
| File transfer (migrate) | TFTP server IP, TFTP root (OS-appropriate default) | — |
| Server (migrate) | Bind host, port, auto-open browser (default: on for Windows interactive, off when `NMAS_HEADLESS=1`) | — |
| Built-in collectors | Enable/disable the trap receiver, NetFlow collector, and syslog monitor, each with its port | port-bind check |

**Monitoring identity mapping (global setting):** how a device matches its
series and streams in the external tools. Options: management IP, hostname, or
a NetBox custom field. Also set the Prometheus label name (default `instance`)
and whether a port suffix is stripped.

**Query templates are settings, not code.** Store PromQL for "device up",
"CPU by platform", and "interface oper status" with `{target}` placeholders,
seeded with generic snmp_exporter defaults. The user can edit them because
other networks use different exporters and MIBs.

Migrate the existing `user_settings.json` keys (and existing NetBox/Jenkins
config files) forward on first load. Add a `settings_schema_version` and keep
the old keys readable.

A dashboard strip shows one status badge per configured integration (green,
red, or grey for not configured), refreshed asynchronously.

---

## 6. Phases

### Phase 0: Foundation, portability, and safety (no user-facing features)

- Rewrite `CLAUDE.md` to be accurate. Add `docs/ARCHITECTURE.md` (modules,
  data flows, entry points), `docs/CHANGELOG.md`, and
  `docs/NSOT_WRITEUP_NOTES.md`.
- Blueprint scaffolding: `routes/__init__.py` with a `register_blueprints(app)`
  called from `app.py`.
- Build the integrations settings framework and panel (Section 5), including
  migrating existing settings. The client modules for each tool can be stubs
  with `test_connection()` only; full clients land in Phase 5.
- **Portability:** bind host/port, browser auto-open, TFTP root, and Jenkins
  step shell all come from settings or environment. Add
  `docs/DEPLOY_LINUX.md` with a systemd unit example and a note on binding to a
  specific address behind a reverse proxy or Zero Trust tunnel (the app has no
  auth layer).
- **NetBox write safety:**
  - Rename "Sync to NetBox" to "Import to NetBox (discovery)". It is disabled
    unless **allow writes** is on. It runs a **dry run first** and shows a
    create/update preview in a confirm modal.
  - Every object NMAS creates gets the tag `nmas-managed`, and NMAS records the
    IDs it created per list.
  - "Remove" deletes **only** objects that carry `nmas-managed` and appear in
    NMAS's own created-ID record. It never deletes a pre-existing region, site,
    VRF, or device.
- **Acceptance:** all existing tests pass. The app starts on Windows and
  headless on Linux. Settings round-trip. Existing lists behave identically.
  With allow-writes off, no code path can write to NetBox.

### Phase 1: NetBox as the source of truth for inventory

- **Inventory source per device list:** `local` (current behavior, default) or
  `netbox` (filters: site, role, tag, status).
  - A NetBox-sourced list is built through an **adapter** that yields the
    exact existing device-dict shape (`hostname, device_type, ip, username,
    password, secret, role`). That way bulk ops, the terminal, backups, drift,
    topology, and the AI tools work unchanged.
  - `ip` = primary IPv4 (address without prefix). `device_type` comes from the
    platform map.
  - Identity fields are read-only in the UI, with an "Edit in NetBox" link.
    The list refreshes on demand and on a configurable interval.
- **Credential store** (`modules/credentials.py`):
  - Encrypted credential profiles (username, password, enable secret) plus named
    template secrets (e.g. SNMP communities).
  - Resolution order: device override → role → site → default profile.
  - Local lists keep their inline CSV credentials (backward compatibility) but
    may opt into profiles.
  - Include `last_rotated` and `rotation_policy` fields, unused for now. They
    are the hook for Part 2's automatic rotation.
- **Fix device lookup:** match by exact name first. For an IP, resolve via
  `ipam/ip-addresses/?address=` → assigned interface → device. If nothing
  matches, return a clear "not found" error; never take the first `q=` hit.
- **Render context builder** (Section 4.2): fetch the full device (including
  `config_context`) and interfaces **with IPs**. Refactor pipeline stage 1/2
  to use it; `pipeline.py` tests must still pass.
- **AI agent:** when the active list is NetBox-sourced, the read-first
  instructions consult NetBox and `host_vars` before golden configs and
  variables. Add a read-only tool `nsot_get_device_context`. All existing tools
  stay.
- **Acceptance:** pointing a NetBox-sourced list at a populated NetBox produces
  a working device list. Status ping, SSH command execution, a bulk op, a
  backup, and topology discovery all work on it, and the local lists are
  unaffected.

### Phase 2: Golden config repository and version control (Obj 1.1, 1.4)

Redesign `modules/config_git.py` **in place** into the golden config repo
service. Keep its public function names working (as thin wrappers if their
behavior changes) so the Git tab and existing routes keep functioning.

**2.1 One write path, committed immediately.**
- Add `nsot_repo.save_golden(list_name, devices: list[GoldenItem], source,
  actor, message, pipeline_id=None) -> CommitResult`.
- `_save_golden_config_file`, `golden_configs_save_all`,
  `golden_configs_auto_create`, the approval-queue golden updates, the pipeline,
  and the AI tool all route through it.
- One call = **one commit**, even for a 9-device "Save All" (a network-wide
  consistent snapshot, not nine commits).
- If nothing changed, create no commit, but still return "unchanged" per
  device.
- Remove the stage-now, commit-later gap for golden saves. The manual
  commit/stage flow in the Git tab remains for `infra/` and ad-hoc files.

**2.2 Timestamps and metadata live in git, not in the file.**
- The file keeps **one stable header line** so existing readers don't break:
  `! Golden config — <hostname> (<ip>)`.
- Drop `! Saved:` and `! Source:` from the file body; they create a diff on
  every save.
- Consolidate the duplicated volatile-prefix lists (Section 3 #6) into one
  helper, e.g. `modules/nsot/normalize.py::strip_volatile()`, used everywhere.
- Every golden commit carries git trailers:

```
golden: baseline 3 devices via pipeline cfg-7f3a

Source: pipeline            # manual | save_all | pipeline | approval | ai | onboarding
Actor: dustin               # or ai-agent
Pipeline-Id: cfg-7f3a
Devices: R1,R3,S3
```

- Each golden promotion also creates **annotated tags**:
  - `golden/<device>/<YYYYMMDDTHHMMSSZ>` for each device changed
  - `baseline/<YYYYMMDDTHHMMSSZ>` for Save All (the whole-network restore
    point)

  Tag names use UTC basic ISO format, with no colons. These tags *are* the
  "golden config saved with timestamp" the lab asks for.
- Reading history:

```python
# per-device golden timeline: timestamp, commit, source, actor, message
fmt = "%H%x1f%cI%x1f%(trailers:key=Source,valueonly)%x1f%(trailers:key=Actor,valueonly)%x1f%s"
rc, out, _ = _git(repo, "log", f"--format={fmt}%x1e", "--", f"golden/{name}.cfg")
# version at a point in time:   git show <sha-or-tag>:golden/<name>.cfg
# diff two versions:            git diff <a> <b> -- golden/<name>.cfg
```

**2.3 Identity via manifest, not header scanning.**
- `.nsot/manifest.json` maps device name ↔ mgmt IP ↔ NetBox id ↔ platform.
- `_find_golden_config_file(ip)` and `_golden_config_path` resolve through it
  (same signatures), and `_list_golden_configs` takes `saved_at` from the last
  commit touching the file (one `git log` call for all devices, not one per
  device).
- Hostname changes are a `git mv` in the same commit, so history follows the
  device.

**2.4 CI evidence attaches to the exact commit.**
- When a Jenkins run (or the pipeline's verify stage) finishes for a golden
  commit, record the result as a **git note** on that commit
  (`refs/notes/ci`: job, build number, result, URL).
- The Git tab shows a badge per commit.
- The existing "commit with a selected pipeline" flow and
  `pipeline_commits.json` keep working for manual commits.

**2.5 Robustness.**
- A per-repo `threading.Lock` serializes all git operations in-process.
- Detect a stale `index.lock` older than N seconds, then log it and remove it.
- `git gc --auto` after commits.
- Pass commit identity via environment variables as today, but make it
  configurable, with `Actor` in trailers.
- Never pass secrets on the command line.

**2.6 One-time migration (idempotent, logged).**
1. Commit any currently staged changes as
   `migration: commit previously staged configs`.
2. Move `config_repo/<host>.cfg` → `golden/<host>.cfg` with `git mv`
   (history preserved).
3. Import any `golden_configs/<host>.cfg` newer than the repo copy.
4. Build `manifest.json` and add `.gitattributes`.
5. Tag the result `baseline/<ts>-migrated`.

After migration, `golden_configs/` is no longer written. Keep reading it as a
fallback for one release and log a deprecation warning.

**2.7 UI.**
- **Device page, Golden tab:** a timeline of promotions (timestamp, source,
  actor, message, CI badge), diff any two versions, diff version vs. running
  config, "Restore this version to device" (through the existing approval
  flow), and "Download".
- **Dashboard:** a "Baselines" list of `baseline/*` tags with a whole-network
  diff between any two, plus "Restore network to baseline". Restore creates
  per-device approval items; it never pushes directly.
- **Git tab:** existing views, plus tags, notes, a file browser (so `infra/` is
  visible), the remote/push status, and archive status.

**2.8 Off-host durability (optional, when configured).**
- Push to the git remote if one is set.
- **S3 archive** via the `minio` SDK, which works against any S3-compatible
  endpoint:
  - After each golden commit, upload `golden/<device>.cfg` as
    `<prefix>/golden/<device>/<tag-timestamp>.cfg`, with commit SHA, source,
    and actor as object metadata. Skip the upload if that sha256 already
    exists.
  - On a schedule and on demand, upload `git bundle create --all` to
    `<prefix>/repo-bundles/<ts>.bundle`, keeping the last N. A bundle restores
    with `git clone <file>.bundle`.
- Git is the system of record; S3 is the archive. Archive or push failures
  show in the integration badge and are logged. They never block or roll back
  a commit.
- Register archive/push, Jenkins triggering (Part 2), and README regeneration
  as post-commit hooks through a small callback registry.

**Acceptance:**
- Migration preserves existing history.
- Saving golden for three devices twice (with one device changed the second
  time) produces exactly two commits. The first carries three per-device tags
  and one baseline tag; the second carries one per-device tag, plus a baseline
  tag if it was a Save All.
- The Golden tab shows both timestamps, and the diff between them shows only
  the change.
- Drift and restore use HEAD's `golden/<device>.cfg`, and all existing callers
  work.
- With no remote and no S3, everything works. With S3 configured, versions and
  a bundle appear in the bucket, and the bundle clones to identical history.
- Tests cover concurrent `save_golden` calls from two threads without an
  index-lock failure.

### Phase 3: Templatize existing config: config → YAML → J2 (Obj 1.3, extra credit)

- **Parsers:** move the existing `_parse_*_from_config` functions
  (`netbox_client.py`) and `variable_discovery.py` logic into
  `modules/nsot/parsers/<platform>.py`, leaving import shims at the old names.
  Extend them to cover at least:
  - hostname, local users (as secret refs), `enable secret` (secret ref)
  - interfaces: description, IPv4/IPv6, shutdown, access/trunk switchport,
    SVIs, VRRP, `ip helper-address` / DHCPv6 relay
  - VLANs
  - OSPF: process, router-id, `network` statements and/or interface areas,
    passive interfaces, `default-information originate`
  - RIPv2: `version 2`, networks, `no auto-summary`, passive interfaces,
    default origination
  - BGP: ASN, router-id, neighbors/remote-as, networks, IPv4/IPv6
    address-families
  - static routes, SNMP (community as secret ref, trap hosts, enabled traps),
    logging hosts, NTP, SSH/vty lines, `ipv6 unicast-routing`
  - NETCONF / telemetry blocks (IOS-XE only)
- **Nothing is dropped.** Lines the parser doesn't model go into an
  `unmodeled:` block of raw lines (in section context), which the templates
  re-emit. The **modeled coverage %** is reported per device.
- **Secrets never land in YAML.** The extractor replaces secret values with
  references (`secret("snmp_ro")`), stores the values in the credential store,
  and lists what it moved.
- **Extraction output:** per-device `host_vars` YAML, a NetBox reconciliation
  report (Section 4.1 precedence rule), and an optional "suggest group_vars"
  action that promotes values shared by all devices of a platform or role.
- **Seed templates:** generate `templates/<platform>/base.j2` plus feature
  partials for the two reference platforms from the parser schema. They are
  per-platform, not per-device. Platform-keyed directories are the multi-vendor
  mechanism.
- **Round-trip validation (the key demo):** render(template, context) vs. the
  normalized running (or golden) config.
  - Normalize with the existing `_sanitise_config`, extended to strip ephemeral
    lines (build banners, "Current configuration", timestamps, crypto PKI
    certificate bodies, `ntp clock-period`, etc.).
  - Compare hierarchically: parent line → set of child lines, order-insensitive
    within a section where IOS order doesn't matter.
  - Report matched / missing-from-render / extra-in-render. The target for the
    reference devices is zero missing and zero extra, with the `unmodeled`
    fallback allowed.
- **Templates UI** (new tab, via a partial):
  - Platform tree and template editor (CodeMirror, vendored) with Jinja
    syntax check on save.
  - `host_vars` / `group_vars` YAML editor with schema validation.
  - "Render preview" for a chosen device, with a diff against running / golden.
  - "Templatize device" (extract → review diff → save = commit).
- **Wire in `PipelineRunner`:** add a new "Deploy from template" flow (a
  blueprint route plus UI) that runs the 9 stages, with stage 2 using the
  context builder and the template library. `/configure/apply` stays as is,
  so both paths exist.
  - Transport comes from the platform map; platforms with
    `supports_netconf: false` go straight to SSH.
  - **Deploy semantics:** push the **merge diff** (intended lines missing from
    running). Lines present in running but absent from intended are reported as
    **removal warnings**, not auto-negated. Full `configure replace` is
    documented as a future option, not built now.
- **Acceptance:** for each reference device, extract → YAML → render yields a
  round-trip report with no missing or extra lines. Editing a YAML value and
  deploying from template changes only that line on the device. The pipeline
  audit log records the run.

#### Amendment (during 3c first runs): intent is committed, never inferred

The first real deploy plan returned `to_add=0, unchanged=82` for a device the
gate reported as fully deployable. The flow was complete and its effect was
structurally zero, because `_artifact_for()` derived `host_vars` by parsing the
device's own captured config. Intent was a function of current state, so the
render reproduced the capture exactly and the diff was empty **by
construction** — the same error as validating a masked render against itself:
both sides come from one source, so the comparison cannot say anything.

- `config_repo/host_vars/<device>.yml` is **committed intent** and the only
  intent source on the deploy path. `.nsot/staging/host_vars/` stays gitignored
  scratch: a proposal, not a decision.
- A device with **no committed intent** is `bootstrap` and **not deployable**,
  reason: *"no committed intent for this device — review and commit extracted
  host_vars first."* A device whose intent is its current state has nothing to
  deploy toward, and treating the status quo as the goal is how a tool
  confidently pushes nothing and reports success.
- `repo.save_host_vars()` — built and tested in Phase 2, callerless until now —
  is the promotion step: staged → committed.
- A change is expressed by **editing committed intent** and committing it
  (`host_vars: <device> <summary>`), never by configuring the device and
  re-extracting. The render diff is then the change.

**This changes what round-trip validation means.** It now measures the template
rendered *from committed intent* against the captured config, so a difference
is not a defect — it is drift, and the three-way relationship the plan always
wanted becomes visible: template, committed intent, captured reality. A
non-empty drift is work to do, and the deploy closes it.

Deployability therefore cannot be judged on that comparison, or every change
would block itself: the difference you intend to push is, by definition, a
difference between intent and the device. The artifact carries two reports —
`report` from intent (drift, informational) and `template_report` from the
capture's own parse (template fidelity, gating). Approval stays keyed on
capture-parsed host_vars, because approval is a statement about the *template*
reproducing every bound device, and one device's intent edit must not silently
revoke it.

**Masking contract unchanged.** Committed host_vars hold `secret_refs`; the
credential store holds values. Preview masks; deploy resolves in memory and
calls `assert_no_mask()`. `write_committed()` refuses any document carrying a
`secrets:` mapping or a resolved value, checked structurally *and* by value —
the structural check alone would miss a value pasted into an unrelated field by
a hand edit, which is exactly what the editor route makes possible.

### Phase 4: Onboarding wizard for a new device or new site (Obj 1.2a(ii))

- **Wizard steps:**
  1. Site (existing, or new)
  2. Device name, manufacturer (vendor), platform, device type, role
  3. Management IP and WAN interface + WAN IP/prefix, with a NetBox IPAM
     availability check and an optional "next available in prefix"
  4. Routing protocol: OSPF (area, passive interfaces), RIPv2, BGP (local AS,
     neighbor IP, remote AS), or static
  5. Template, filtered by platform
  6. Credential profile
  7. **Review:** the NetBox objects to be created, the `host_vars` YAML, and
     the rendered config preview (secrets masked)
- **On confirm:** create the NetBox objects (device, interfaces, IPs, primary
  IP) through the gated write path, tagged `nmas-managed`. Write and commit
  `host_vars`.
- **Then offer both:**
  - **Download rendered config**, for bootstrapping a node that doesn't exist
    yet (e.g. a startup-config file).
  - **Deploy now** through the pipeline, if the device is reachable.
- **New site** = a NetBox site plus `group_vars/site_<slug>.yml`.
- **Change flows:** "Change routing protocol settings" and "Add interface"
  forms that edit YAML/NetBox and then run render → diff → deploy.
- **Acceptance:** adding a router through the wizard creates it in NetBox,
  commits its YAML, and produces a downloadable config. Deploying to a running
  node applies it and saves a timestamped golden config.

### Phase 5: Monitoring and visualization integration (Obj 1.2a(i))

*Independent of Phases 1–4 after Phase 0; it may be done earlier if needed.*

- **Full clients in `modules/integrations/`:**

  | Client | Endpoints / behavior |
  |---|---|
  | `prometheus.py` | `/api/v1/query`, `/api/v1/query_range`; works against Thanos Query unchanged |
  | `loki.py` | `/loki/api/v1/query_range` |
  | `grafana.py` | Deep-link builder; iframe only when embed mode is on (document that Grafana needs `allow_embedding` and that auth proxies may block iframes, which is why links are the default) |
  | `oxidized.py` | `/nodes.json`, `/node/fetch/<node>`, `/node/version.json?node_full=` and version diff; handle 404 cleanly when the versioning backend isn't git |
  | `kea.py` | Control Agent JSON commands `status-get`, `lease4-get-all`, `lease6-get-all` with `service` |
  | `topology_service.py` | Generic JSON graph / SVG / iframe |

  Each client has short timeouts and a small TTL cache.
- **Dashboard:** a "Network Health" panel set showing devices up/down, CPU (from
  the platform's query template), interfaces down, recent log events (Loki),
  and DHCP lease counts. Each card deep-links to Grafana. Load all panels
  **asynchronously** via fetch so external slowness never blocks page render.
- **Device page tabs:**
  - Health: metrics plus a sparkline (vendored Chart.js if no chart lib
    exists)
  - Logs: Loki, with time range and a text filter
  - Config history: Oxidized versions and diffs, shown alongside golden
    history
  - DHCP: optional, leases for subnets on this device's interfaces
- **Topology:** keep the built-in CDP/LLDP/OSPF/BGP discovery. Add an optional
  "External topology" sub-tab fed by the configured service. Optionally color
  built-in topology links using Prometheus interface status.
- **Built-in collectors:** add the enable/disable toggles (Section 5); defaults
  stay as today. On a bind failure, show a clear "port in use — another
  collector owns it; disable the built-in one in Settings" message.
- **AI agent:** add read-only tools `prometheus_query`, `loki_query`,
  `oxidized_get_config_version`, and `kea_get_leases`, following existing tool
  schema conventions.
- **Acceptance:** with every integration configured, the dashboard and device
  pages show live data. With none configured, everything shows "Not configured"
  and no errors are logged per request.

---

## 7. Part 2 compatibility (do not implement)

- **Credential rotation:** credential profiles carry `rotation_policy` and
  `last_rotated`. Part 2 adds a scheduler that pushes new credentials to
  devices, verifies login, then commits the new values to the store.
- **IPAM:** NetBox, already the owner.
- **Jenkins on change:** use the NSoT repo's post-commit callback registry and
  the Jenkins webhook. The Jenkins step shell setting from Phase 0 applies.
- **Health-check apps:** reuse `pipeline._capture_operational_snapshot` and
  `_detect_routing_neighbors`. Expose them as standalone functions
  (neighborships, route table, CPU via Prometheus, IP connectivity) rather than
  keeping them private to the pipeline.

---

## 8. Reference lab (for testing only; never hardcode any of this)

- **Topology:** R1–R5 routers (Cisco C8000v, IOS-XE 17.6) and S1–S4 switches
  (Cisco vIOS-L2, IOS 15.2), running in containerlab.
- **Routing:**
  - RIPv2 on R1, R2, S1, S2 (`no auto-summary` mandatory)
  - OSPF area 0 on R1–R4, S3, S4
  - eBGP between R3/R4 (AS 65001) and R5 (AS 65002)
  - R3/R4 originate a default into OSPF; R1/R2 originate a default into RIP
  - VRRP on S1/S2 SVIs; DHCP relay to Kea
  - Dual-stack IPv4/IPv6
- **Management:**
  - Device loopbacks are `10.255.1.11–.15` (R1–R5) and `10.255.1.21–.24`
    (S1–S4).
  - The NMAS host (Ubuntu 24.04) is `10.0.0.211` on the LAN, `10.255.0.10` on
    management VLAN 99, and `10.255.1.10` as its loopback identity.
  - NetBox is on the NMAS at `:8000`. The Kea Control Agent is on `:8001`. The
    topology service (Flask) is on `:8088` (`/graph.json`, `/topology.svg`).
    The Telegraf Prometheus exporter is on `:9273`. MinIO (the existing data
lake, already replicated to a DR node) is the S3 archive target; the user
creates an `nsot` bucket and enters its endpoint and keys in Settings.
  - Prometheus, Grafana, Loki, Thanos Query, and Oxidized URLs will be entered
    in Settings by the user.
- **Platform facts that must drive behavior through the platform map:**
  - vIOS-L2 has **no NETCONF and no telemetry**, so it is SSH only.
  - The two platforms use different CPU MIBs: C8000v uses
    `cpmCPUTotal5minRev`; vIOS-L2 uses `OLD-CISCO-CPU-MIB::avgBusy5`. That is
    why CPU queries are per-platform settings.
  - R5 (the PE) has no route to the collectors, so missing R5 telemetry is
    expected, not an error.
  - Devices need legacy SSH algorithms with OpenSSH 9.x clients. Don't change
    SSH negotiation code that currently works.
- **Pitfalls:**
  - A bare `end` in the middle of a config silently truncates everything after
    it when used as a startup-config, so templates must never emit `end`
    except as the final line.
  - Containerlab nodes are ephemeral. Pushed config doesn't survive a redeploy
    unless it's written back to the startup files (an external Oxidized-based
    workflow owns that), so golden configs are the durable record.
  - Silent failures are the dominant failure mode in this stack. Every
    integration call must log and surface its failures, never swallow them.
