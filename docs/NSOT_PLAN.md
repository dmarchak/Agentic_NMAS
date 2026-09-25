# Agentic NMAS → Network Source of Truth (NSoT): Implementation Plan

> **For Claude Code:** This is the governing spec for the NSoT work. Commit it to
> `docs/NSOT_PLAN.md`. Work **one phase at a time**. For each phase:
> (1) re-read this file and the relevant code, (2) post a short implementation
> plan and list anything in Section 3 that you found to be inaccurate,
> (3) wait for approval, (4) implement, (5) run and extend tests, (6) update
> `CLAUDE.md`, `docs/CHANGELOG.md`, and `docs/NSOT_WRITEUP_NOTES.md`, (7) stop and
> summarize. Do not start the next phase without explicit go-ahead.

---

> **Reading order as of 2026-09-22:** Part 1 is submitted. Sections 1–5 are the
> standing architecture and constraints. Section 6 describes what each phase
> *is*. **[Section 9](#9-completion-plan-after-part-1-submission-2026-09-22) is
> the order the remaining work happens in and what "done" means for each
> stage** — it supersedes Section 6's ordering.

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

#### Design rule: gate on template fidelity, never on intent drift

Not an implementation detail — a rule that governs every later gate built on
this model.

An artifact carries **two** measurements, and they answer different questions:

| | measured from | question it answers |
|---|---|---|
| `template_report` | render of the **capture's own parse** vs the capture | *Can this template faithfully reproduce this device as it actually is?* |
| `report` | render of **committed intent** vs the capture | *How far has intent drifted from the device?* |

**Gating uses `template_report`, always.** If the template cannot reproduce the
device as it stands, a render from intent is untrustworthy regardless of what
the intent says — the renderer has already demonstrated it does not model this
device. That is a statement about the tool, and it must block.

**Gating on intent drift is forbidden.** Drift is the change being deployed.
Blocking on it would make every change block itself: the difference you intend
to push is, by definition, a difference between intent and the device. A gate
with that property is not strict, it is inert — the same failure as a flow
whose diff is empty by construction, arrived at from the opposite direction.

The same rule fixes where **approval** is keyed. Approval is a claim about the
*template*, not about any one device's state.

**Correction to the 3b amendment (made during run 3A).** The original
amendment specified a binding fingerprint of *template hash + bound device set
+ a hash of each device's host_vars*. That third term keys the gate on the
**result of the work**: a successful deploy changes the device's captured
config, so its hash moves and the approval is revoked — by the very change it
authorised. On the live lab, deploying one interface description to s4 revoked
`cisco_ios/base.j2` for s1, s2 and s3, which had received nothing. It is this
section's own rule, broken in this section's own design.

The division of labour, corrected:

| | claim | revoked by | when measured |
|---|---|---|---|
| **approval** | validated against **this device set** | a template edit, or a device joining or leaving the set | once, recorded |
| **`template_report`** | reproduces **this device now** | nothing — it is recomputed | live, per device, every plan |

Drift is caught by the second, which already runs on every plan and already
gates, and which names the lines. The first answers a question that has a
durable answer, so freezing it is legitimate.

Fingerprint scheme 2 = `template_hash` + sorted bound **identities** (a rename
is the same device; onboarding is not). Records carry a `scheme` number and an
older one is **not** silently honoured — its fingerprint answered a different
question, and accepting it would be a gate that passes because nobody migrated
it. Re-approval after a scheme change is explicit and its own commit.

> A gate must be keyed on the property it claims to protect. Template fidelity
> protects against an untrustworthy renderer. Intent drift is the work, not a
> defect, and gating on the work means no work can ever be done.

#### Design rule: what the operator confirms is what is sent, byte for byte

Not a superset. Not a *safe* superset.

`_deploy_one()` originally set `rendered_commands` to the entire rendered
config, while the preview showed the merge diff. On the first real run that was
**one line confirmed, eighty-three sent** — including `hostname s4`,
`no service password-encryption`, and the SNMP community line.

"IOS treats a re-applied identical line as a no-op" is true, and it is an
argument about **blast radius, not correctness**. The confirm step exists to
make one specific claim — *this is what will happen* — and a push that exceeds
its preview falsifies that claim whether or not the excess is harmless. An
operator who cannot trust the preview has to audit the device afterwards, which
is the state the tool exists to remove.

Two consequences followed from the same defect:

- **`assert_merge_only()` was vacuous.** It checks that every pushed command
  appears in the intended config; when `to_push` *is* the intended config it
  cannot fail.
- **The previewed diff was not sendable.** `' description …'` has no parent
  line, so it would apply in global configuration mode. Pushing the whole
  config is what hid that, which is why both defects survived together.

`merge_commands()` produces the exact program: each added line preceded by its
**full ancestor chain in order** — a line under `address-family ipv4` inside
`router bgp 65001` gets both, because a partial chain applies it to the wrong
address family silently and successfully — with one `exit` per open level at
the end of each contiguous group, and **never** `end`. `end` leaves
configuration mode, and a command list that ends config mode part-way through
is a different program than the one confirmed.

The equality is enforced **at apply**, not only in tests: the command list is
recomputed from current state, compared against the confirmed fingerprint, and
refused with *"the device or intent changed since you confirmed"* on mismatch.
Same one-shot discipline as the Phase 0 plan token, applied to the program
rather than to the plan. The hash is recomputed server-side; one supplied by
the client proves only what the client saw.

> A preview is a promise. Sending more than it showed breaks the promise even
> when sending more is harmless.

#### A gate that cannot be cleared is not a control

The CI gate (stage 3) halts on `shutdown`, `no ip address`, `no router ospf`,
`reload`, `erase nvram` and `crypto key zeroize` unless the exact string is in
`params["allowed_dangerous"]`. That override has existed since Phase 0.
`_deploy_one()` hardcoded `params={"skip_route_check": True}`, so the
deploy-from-template path could never supply it — every one of those commands
was permanently unrunnable through Phase 3c, refused with an error naming an
override the caller had no way to reach.

A gate that cannot be cleared fails in the safe direction, which is why it can
sit unnoticed. Its real effect is to make a routine operation — shutting an
unused access port — impossible through the supported path, which pushes the
operator to an unsupported one.

The authorisation is shaped like every other deliberate action in this phase:

- **Confirmed at plan time, not added at apply.** The plan flags each dangerous
  line as the exact string the gate compares, and the authorisation is folded
  into the confirmation hash **with** the commands. "These lines, with these
  authorised" is one decision; changing either half after it was displayed
  makes the confirmation no longer describe what would happen.
- **Scoped per device** — `{"s4": [" shutdown"]}`. Authorising a line for one
  device never authorises it for another in the same batch.
- **Exact strings, and every authorisation must be used.** One matching nothing
  in the program is a typo or a leftover from an earlier plan, and a typo means
  the line it was meant to cover is not authorised.

**Rollback is exempt, structurally** — it never passes through stage 3. Undoing
an authorised `no shutdown` produces `shutdown`; a gate that blocked the repair
would leave the device in the state the rollback was called to fix, which is a
safety check causing the damage it exists to prevent.
`assert_rollback_provenance()` is the authorisation there: every rollback line
inverts something this deploy just pushed. Exempt lines are recorded in the
deploy result so the exemption is visible rather than implicit.

#### The bounded exception: rollback generates negations

"This tool never synthesises a `no` command" is the merge-only rule, and
rollback is its **one** exception. Recording it as such, with its bounds:

A config-mode replay of the pre-change snapshot cannot undo a change. It is a
merge — it re-applies lines and removes none. IOS omits `no shutdown` from an
up interface's running config, so a snapshot taken before a `shutdown` contains
no line to re-apply: the replay leaves the interface down, saves the config,
and reports success. Rollback would demonstrate itself working on the one
change it cannot reverse, and then persist it.

`rollback_commands(pushed, pre_config)` computes the inverse of **exactly what
was pushed**, inside each line's own header chain:

- the pre-change config set the same thing to a different value → re-send the
  old line
- it did not set it at all → negate the pushed line

Same `exit`-per-level and never-`end` rules as `merge_commands()`, and the
rollback program passes `assert_sendable()` too.

**Bounded means checkable.** `assert_rollback_provenance()` requires every `no
X` in a rollback to correspond to an `X` in the pushed list. A negation that
undoes nothing this deploy did is removing configuration nobody asked to
remove, and is refused. Merge-only's other half is unchanged: lines on the
device the template does not mention remain **warnings**, never actions.

The rollback program is reported verbatim in the deploy result, for the same
reason the forward program is — what was sent is not a summary of what was
sent.

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

---

## 9. Completion plan (after Part 1 submission, 2026-09-22)

Part 1 is submitted. Phases 0–3c and 2b are built; Phase 4 and 5 are not.
**This section supersedes the phase ordering in Section 6 for what happens
next.** Section 6 still describes what each phase *is*; this describes the
order the remaining work happens in, and what "done" means for each stage.

### Standing rules

These are not aspirations. Each one is here because ignoring it cost real
time in Part 1, and the cost is named.

1. **Measure on hardware; do not infer.** A reading of a launch script said
   r1–r5 would fail to boot their own credential. Booting one said the same
   thing — but only the boot could have been believed, and only the boot
   revealed that the node comes up *healthy* while holding the wrong
   credential.
2. **Every GUI feature ships with its entry point.** Four times, working
   backends shipped with no button. `tests/test_no_unreachable_ui.py` now
   fails on a fifth; it is not to be worked around by allowlisting a new
   entry.
3. **A check must verify the property, not a proxy.** The startup-file check
   asked "is the hash in the file" when the question was "does the file
   apply". The remote-relatedness check compared root commits to ref tips.
   Both passed. Both were asking something else.
4. **No redeploy of rcn-lab1** until Stage 2's checklist passes. Including
   `--reconfigure`. Including adding r6.
5. **Ask before changing shared infrastructure.** The lab host, the Oxidized
   container, the topology service and the clab topology are shared; the user
   runs those changes, or approves them first.
6. **A fixture that cannot fail is not a fixture.** Tests that build real git
   repositories found two traps in a single afternoon that stubbed SHAs would
   have hidden.

---

### STAGE 1 — the deadline-night bug batch (code only)

No infrastructure changes, no device contact. Seven items, each independently
committable.

**1.1 Remote Verify falsely refuses after the first push.**
*Status: **DONE**, verified on the deployed instance 2026-09-22.* All four
read-only checks green against `dmarchak/rcn-nsot-config`;
`repository_is_empty_or_related` reported *"53 shared commit(s) on this list's
history"*. The gated write probe passed at 17:21:54Z.
The reported hypothesis — peeled `refs/tags/x^{}` entries inflating the count —
was wrong. The count was a symptom. The check intersected the local **root
commit** with the remote's **ref tips**, which coincide only in a repository
with exactly one commit, so it passed on an empty remote and refused every
remote with history. It now tests ancestry over every advertised SHA this
clone holds.
*Acceptance:* Verify (read-only) passes against `dmarchak/rcn-nsot-config`
with all **four** read-only checks green, **on the deployed instance** — the
write probe is the gated fifth and is not part of a read-only verify, which
this criterion originally got wrong; a deliberately
unrelated repository is still refused with the "interleave" wording; the
real-git tests in `tests/test_remote_relatedness.py` stay green.

**1.2 Auto-push does not publish tag-only baselines.**
*Status: **DONE**, verified on the deployed instance 2026-09-22.* An unchanged
Save All reported *"no commit … baseline baseline/20260922T172405Z"*; the
remote went from 33 tags to 34, and the before/after difference was **exactly**
`refs/tags/baseline/20260922T172405Z`. Nothing else was published — the
property the explicit refspec exists for, measured rather than reasoned. `save_golden()`'s no-commit path (`repo.py`, the
`_baseline_wanted` branch at existing HEAD) tagged the baseline and
**returned without calling `run_post_commit` at all** — so the hook that
pushes never fired. That was the whole cause, and it was sufficient alone.

**The second cause written here originally was wrong**, and measuring it is
what corrected the fix. It claimed `--follow-tags` pushes only tags reachable
from commits *being pushed*, so a tag-only baseline had nothing to ride on.
Against real repositories, git pushes annotated tags reachable from the pushed
ref whether or not the ref advanced; the tag goes out fine.

The measurement found the opposite problem. `--follow-tags` also published an
**unrelated older tag** in the same breath, because it carries every reachable
annotated tag the remote lacks. So the explicit refspec is still right — for
the reason below rather than the reason first written.
*Fix narrowly.* Push **exactly the new `baseline/<ts>` tag**, by explicit
refspec, through the same acknowledgement scan. **Not `git push --tags`**,
which publishes every local tag — including per-device tags that pruning is
supposed to keep local, and any tag a future feature creates for its own
purposes. A broad fix would satisfy "the tag is on the remote" while changing
what publishing means.
*Acceptance:* a Save All that changes nothing but earns a baseline results in
that `baseline/<ts>` tag existing on the remote; a test asserts the hook fires
on the no-commit path; a test asserts the push command carries **that one
tag's refspec and no other**, and specifically that neither `--tags` nor a
wildcard refspec appears; a test asserts a second unrelated local tag is
**not** published by that push. The acknowledgement gate still applies — a
tag-only push must not bypass the history scan.

**1.3 Preview diff is order-sensitive and whitespace-sensitive.**
*Status: **DONE** (`7ab6ac1`).* `roundtrip.canonical_lines()` /
`canonical_diff()` sort children only where `section_is_unordered()`
says order is insignificant; ACLs, prefix-lists, route-maps and `ip sla`
keep their sequence. The machinery already existed — `compare()` has
used it since Phase 3a — and the preview was the one comparison not
using it.
The `vs current golden` diff in Template preview reports differences for
reordered set-like sections and for indentation-only changes.
`roundtrip.configs_equivalent()` already knows both answers — it is
section-aware and consults `section_is_unordered()`. The preview does a flat
`difflib` over normalised lines instead.
*Acceptance:* a device whose golden differs from the render only by the order
of an unordered section (ACL entries are ordered; `snmp-server community`
lines are not) shows **no** diff; a device differing only in leading
whitespace within a block shows no diff; a genuinely reordered **ordered**
section (an ACL) still shows a diff. Tests for all three.

**1.4 `Gi` → `GigabitEthernet` expansion corrupts description text.**
*Status: **DONE**, verified on real data 2026-09-22.* Parser fix in
`447a72c`; committed intent corrected by `2443892` (9 files, 22
insertions / 22 deletions, every changed line a `description:`), which
is published. Template preview for s1 and r3 shows no description
differences.
`ifnames` canonicalisation rewrites interface references inside lines, which
is correct for `ip route ... Gi0/0` and wrong inside a `description` — a
description reading `link to Gi0/1 spare` is rewritten in `host_vars`, so the
render no longer matches the device and the difference is invisible in the
diff because both sides were canonicalised.
**The parser fix stops new damage; it does not undo the damage already
committed.** `host_vars` already carry expanded descriptions — s1 holds
`GigabitEthernet3` where the device says `Gi3`, and others are likely.
*Acceptance:* a fixture device with an interface reference inside a
`description` round-trips byte-identically; expansion still applies to the
lines that need it; the free-form keywords already recognised elsewhere
(`description`, `banner`, `remark`, `name` — see the rollback broad-key rule)
are the ones exempted, so there is one list rather than two. **Then the
committed intent is corrected by a reviewed commit — descriptions only, with
the diff shown before it is made — and Template preview for s1 shows no
description differences.** Proof on the real data, not only on a fixture: the
fixture was written by the same person as the fix.

**1.3b Masked lines cannot be compared, and the preview does not say so.**
*Status: **DONE**.* Masked lines are neutralised to
`<masked - not compared>` and counted; only the **value** is unknowable,
so `RO`→`RW`, a changed trap host and a changed privilege all still
report. The panel states the consequence and names where the real
comparison happens.
Raised while closing 1.3. The preview renders with secrets masked
(`render_artifact.MASK`, `••••••••`) while the golden holds real values, so
**every secret-bearing line shows as a difference for ever**. That is not a
defect in masking — `intended/` and previews are masked precisely so neither
can be a deploy source — but it means a device with an SNMP community can
never show a clean preview, and a permanent difference is one people learn to
scroll past.
*Acceptance:* a masked line is reported as **masked, not compared** rather
than as a difference; the count of them is shown, so "three lines could not be
compared" is visible rather than inferred; a genuinely changed *unmasked* line
on the same device still shows; and a masked line whose **surrounding text**
changed (a community moving to a different ACL, say) is still reported,
because only the value is unknowable, not the line.

**1.5 The three allowlisted functions with no caller.**
*Status: **DONE**.* All three deleted, each decided from evidence rather
than defaulted; `KNOWN_DEAD` is empty and a test asserts it stays empty.
`invalidateTopologyCache` turned out to be inside the chat panel's IIFE,
so the deploy code could never have called it — and the staleness it was
written to mitigate was fixed at the reader instead.
`_deployList`, `invalidateTopologyCache`, `loadJenkinsResults`, currently in
`KNOWN_DEAD` in `tests/test_no_unreachable_ui.py`. Each needs a decision, not
a default: wire it up or delete it. For `invalidateTopologyCache`
specifically: if the collapsed legacy discovery still keeps a cache, wire it
there; otherwise delete it through
`scripts/check_removed_definitions.py`.
*Acceptance:* `KNOWN_DEAD` is empty, and the test asserts it is empty rather
than merely consistent. Deleting a function goes through
`scripts/check_removed_definitions.py`.

**1.6 Stale Git-tab and NetBox-tab descriptions.**
*Status: **DONE**.* Both checked against the routes they call. The Git
tab described the pre-Phase-2 stage-then-commit flow — and so did the
route's own docstring, which is how the tab text kept agreeing with
something. The NetBox tab claimed import scans by SSH; it reads golden
configs and `_scan_device` has no callers, so **an offline device IS
imported** — the old text was wrong in the dangerous direction.
`test_tab_descriptions_are_true.py` pins each claim to the code.
Both tabs describe behaviour that predates the NSoT work.
*Acceptance:* every sentence on both tabs is true of the code as it is, checked
against the routes each tab calls — not rewritten from the plan, which is what
they were written from the first time.

**1.7 `ListRef`.**
*Status: **DONE**.* `modules/nsot/listref.py`. It is a **type** rather
than a convention because of defect 3: a list has two names, and passing
"the list name" as a string leaves every caller to decide which one it
meant. `matches()` compares identity, so the display-name/slug question
cannot be got wrong per site. A test walks the AST of the NSoT paths and
fails on any function that takes a list and then reads the active one.
A resolved list reference — slug, display name, data directory, repo path —
constructed once and passed, so a list name cannot be re-derived from global
state mid-operation. **Three defects had exactly this shape**: the pipeline
asking `get_current_list_name()` after the push, `plan_restore()` reading the
active list's inventory, and `check_right_repository()` comparing a display
name to a slug.
*Acceptance:* `ListRef` exists and carries slug, display name, data dir and
repo dir; the deploy, restore, remote and templates paths take it; a test
greps those modules for `get_current_list_name` / `get_current_device_list`
and fails on any call reached from a function that already has a list in hand.

**1.2b `last_push` is not recorded by auto-push.**
*Status: FIXED, pending confirmation on the deployed instance.* Found while
confirming 1.2: the baseline tag published at ~17:24Z left the Remote card
still showing `2026-09-21T19:57:47Z`. The card was not stale — it was
answering a narrower question than it appeared to. **Two code paths push**:
`remote.push()` (the button) recorded `last_push`, and
`archive.push_hook()` (auto-push) pushed without ever writing it, so the
field meant "when somebody last clicked", which reads as "nothing has been
published since".
*Acceptance:* one producer, `remote.record_push()`, called by both paths; a
successful push of either kind advances `last_push` and names what went out;
a **tag-only** push is recorded as such, because "pushed" is not one event —
with no new commit the branch push is a no-op and the tag is the entire
publication; a **failed** push writes `last_push_failure` and leaves
`last_push` pointing at the last thing that really went out, since a
timestamp on a push that did not happen reads as durability that does not
exist; a later success clears the failure; the card shows the tag and the
failure.

**Stage 1 is done when:** all eight acceptance criteria hold, the full suite
passes, and 1.1, 1.2 and 1.2b have been confirmed **on the deployed instance
against the real remote** — the ones that were only ever exercised in states
that no longer occur.

---

### STAGE 2 — lift the redeploy ban  ✅ **COMPLETE 2026-09-22**

Lifted by a successful redeploy. Every checklist item passed; the
result is recorded in the three former ban notices and in
`docs/NSOT_WRITEUP_NOTES.md`.

**A redeploy is now a normal operation, not a blocked one — and not a casual
one.** It is expensive and it touches every device at once, so it is done
deliberately, and **`docs/STAGE2_SESSION_CHECKLIST.md` is the verification
for any future redeploy**, not a record of this one.

Re-run it every time. Sections 1 (pre-items), 3 (the redeploy) and 4
(post-items) apply unchanged; section 2's applicability control applies
whenever the launch patch may have moved. The items that matter most are the
ones that were nearly wrong here:

* **4.7** — the credential check, which must use `nmas-check-credential` and
  not a shell `ssh`, and where `INCONCLUSIVE` is not a pass;
* **4.2** — per-device uptime, because a node can reload silently after
  `Startup complete` and report healthy throughout;
* **4.9** — Save All against a **pre-redeploy** baseline taken in 1.4, which
  is what makes "every node came back as itself" a measurement rather than an
  impression.

A checklist that is run once is a record. One that is re-run is a test.


**The runbook is [docs/STAGE2_REDEPLOY.md](STAGE2_REDEPLOY.md)** — written
before the redeploy, including the checklist in full. This section states
what each item is *for*; that file is what gets followed at the machine.

The ban is lifted by a **successful redeploy**, not by the four items being
built. Built is not deployed; proven on a probe is not adopted here.

**2.1 Adopt the launch patch.** `docs/bootstrap-probe/patches/patch-skip-injected-user.py`
applies the user-skip to a copy of `~/labs/lab/patches/c8000v-launch.py` and
prints the real diff. **The user applies it** — shared infrastructure.
*Acceptance:* the diff is reviewed and applied; the adopted file differs from
stock by exactly `smp="2"` plus the skip helper; running nodes are unaffected
(binds are read at container start, so adoption changes nothing until a
redeploy).

**2.2 Wire the applicability check and break-glass.**
Both are built and tested (`verify_startup_applies()`, `modules/breakglass.py`)
and neither is called by the running app.
*Acceptance:* the persistence chain's `startup_applies` stage runs on a real
rotation and passes for a C8000v **because the launch script carries the
skip**, demonstrably failing if the skip is removed; a break-glass record for
r1–r5 exists on removable media, has been **opened with `verify`** on the
medium it lives on, and its location is recorded somewhere that is not the
NMAS.

**2.3 Generator fixes re-proven on the probe.**
`crypto key generate rsa` on vIOS and the per-platform domain keyword are
**unmeasured on a console-replayed platform**: key generation takes real time
and vrnetlab waits for a prompt after each typed line. This is stage D in
`docs/bootstrap-probe/README.md`.
*Acceptance:* a throwaway vIOS boots a generator-produced startup config,
reaches `Startup complete`, and **answers SSH** — the capture is taken over
SSH, not the console, which is the whole point of the key. A C8000v boots one
with `ip domain name` and logs no `%CVAC-4-CLI_FAILURE`.

**2.4 The planned redeploy, with a verification checklist.**
Written **before** the redeploy, not after. At minimum: every node reaches
`Startup complete`; every node answers SSH **with the credential NMAS holds**,
not `admin`; `show running-config | include ^username admin` shows `secret 9`
on all five routers; Oxidized fetches all nine; a Save All produces no
unexpected diff against the pre-redeploy goldens.
*Acceptance:* the checklist passes in full. **The redeploy is the proof.** If
any item fails, the ban stays and the failure is measured before anything is
changed. Only then are the three ban notices (CLAUDE.md, the probe README, the
Phase 4 plan) updated — and to "lifted, and here is what proved it", not
deleted.

---

### Queued from the Stage 2 session (2026-09-22)

Found while running the redeploy; none blocked it.

**Q1 — `nmas-check-credential` maps a connection timeout to REFUSED.**
*Status: **DONE**.* REFUSED is now earned: it requires an `error_type` in
`credential_rotation.AUTH_DENIED`, a strict subset of `_AUTH_REFUSED`
that excludes `SSHException` — which paramiko raises for KEX failures.
Everything else is INCONCLUSIVE. `classify_failure()` is untouched and a
test asserts the rotation still treats a post-rotation timeout as
attempted, plus one asserting the rotation never reaches for the narrower
list.
A transport failure must be **INCONCLUSIVE**. This is the same class as the
`ssh`/`sshpass` false pass the script was written to replace, surviving
inside the replacement.

The cause is a real distinction, not a typo. `classify_failure()` puts both
`_AUTH_REFUSED` **and** `_REACHABILITY` names in the `attempted=True` bucket,
and that is **correct for the rotation**, which the flag was built for: a
device that stops answering immediately after its credential was changed is
the alarming case, and treating it as "we never asked" would suppress a
lockout warning. For a credential *check*, the same flag means the opposite:
unreachable is not refused.

So the fix is not to change `classify_failure()` — that would weaken the
rotation's lockout defence. The check needs the finer distinction, keyed on
the error type rather than on `attempted` alone.
*Acceptance:* a timeout, a refused connection and a KEX failure all report
INCONCLUSIVE; an authentication failure reports REFUSED; the rotation's
lockout behaviour is unchanged, with a test asserting `classify_failure()`
still treats a post-rotation timeout as attempted.

**Q2 — the Baselines badge and red-line labelling.** The panel's colouring
does not match what the entries mean.
*Acceptance:* every badge states the claim its tag makes, and a red line says
which of the two staleness directions it is in — behind the network, or
naming credentials the fleet has rotated away from.

**Q3 — empty-command rejections at boot.** r3, r4 and r5 each logged two
rejections of an empty command during the redeploy. A blank line in the
startup config, harmless here, but it is config being sent that nobody
intends — and on a console-replayed platform a stray line is not always
harmless.
*Acceptance:* the source of the blank line is found (harvest, template, or
`clab-sync`) and either removed or recorded as expected with the reason. It
is **not** to be silenced by filtering the log.

---

### STAGE 3 — GUI correctness

**3.1 Can committed intent be edited from the GUI?**
*Status: **MEASURED, 2026-09-23. The answer is no.***

`/templatize` appears **zero times** in the rendered page — not as a fetch,
not in a built URL, not at all. All **twelve** routes in
`routes/templatize.py` are unreachable from the interface:

```
POST /templatize/extract/<host>              extract to staging
GET  /templatize/staged                      what is staged
POST /templatize/commit/<host>               staged -> committed
GET  /templatize/committed/<host>            read committed intent
POST /templatize/committed/<host>            EDIT committed intent
POST /templatize/committed/<host>/revert     revert one intent commit
GET  /templatize/rendered/<host>             render from intent
GET,POST /templatize/report                  round-trip coverage
GET  /templatize/rolled-back                 blocked devices
POST /templatize/rolled-back/<host>/retry    lift a rollback block
```

For contrast, measured the same way: `/netbox/` appears 8 times (all through
the gated `safety/*` path), `/ai/` 28, `/deploy/plan`, `/templates/preview`,
`/golden/history`, `/remote/status` and `/monitoring/stack` once each.

**What that means.** Phase 3c's central rule is that *a change is made by
editing committed intent and committing it, never by configuring the device
and re-extracting*. There is no GUI path to edit committed intent, so that
rule describes something reachable only by hand-editing YAML and committing,
or by `curl`.

The asymmetry is the sharp part: **the GUI can deploy intent onto devices but
cannot author it.** "Deploy plan" works (Stage 1.5 gave it a button) and
reads committed `host_vars`; a device with none is `bootstrap` and refused.
So the interface can push a change toward a target it has no way to set.

That is a larger gap than any of the legacy readers in 3.3, and it is a
**missing capability at the centre of the design** rather than a correctness
bug. Building it is the first build item of Stage 3.

*Status: **BUILT**.* `templates/partials/intent_editor.html` + `POST
/templatize/committed/<host>/preview`. Text via `write_committed_text()`,
CodeMirror with line numbers, refusal with line and column, the render diff
before the commit, and Commit disabled until a preview passes. Entry point on
the device row; `KNOWN_UNREACHABLE` is empty.

*Acceptance:* extract, review, commit, edit and revert are all reachable from
the device row or the Templates view, each shipping with its entry point and
passing `test_no_unreachable_ui.py`; the editor writes through
`hostvars.write_committed()` so the secret guards apply; `KNOWN_UNREACHABLE`
in `test_blueprint_reachability.py` is empty.

---

**3.1 (original wording, for the record.)**
The deploy path's stated rule is that a change is made by *editing committed
intent*, not by configuring the device. If there is no GUI path to edit
`host_vars`, that rule describes something only reachable by hand-editing YAML
and committing — which would make Phase 3c's central design claim untrue in
practice.
*Acceptance:* the answer is established by reading the routes and templates
(as with the three missing buttons — **not** from the plan or from memory) and
written down. If no path exists, building one is the first item of this stage
and ships with its entry point.

**3.2 Settings audit.** Dead controls; Test buttons that do not exercise the
path the feature actually uses; the duplicate Oxidized setting.
*Acceptance:* every control changes behaviour or is removed; every Test button
calls the same client the feature calls — a Test that passes while the feature
fails is worse than no Test; one Oxidized configuration, not two.

**3.4 `nmas-deploy` compares against a ref it never fetches.**
Measured 2026-09-22: the deploy host sat at `90af74d` and reported "already
up to date" while origin held `40e8a87`. A `git fetch` moved its `origin/main`
by two commits. The tool was reading a **local tracking ref**, which is a
cached answer, not the remote's answer — so it would have reported up to date
indefinitely however many commits landed.

Third instance of that shape in Stage 1 alone: `check_right_repository()`
compared local roots instead of asking the remote, and the Remote card read a
field only one code path wrote. `git ls-remote` is the only thing that asks.

The script lives on the NMAS, outside this repository.
*Acceptance:* `nmas-deploy` fetches (or uses `git ls-remote`) before deciding,
and says which commit it compared against — a tool that reports "up to date"
without naming the reference it used cannot be checked.

**3.3 Retire the legacy `golden_configs/` store.**
Remaining readers: `agent_runner.py`, `check_runner.py`,
`/list/golden_configs`. Template preview was the fourth and was fixed in
`2751e62`; it had been serving a six-day-old config while the repo held a
same-day commit.
*Acceptance:* no code path reads `golden_configs/` except
`_find_golden_config_file()`'s documented fallback; a test enumerates the
readers so a new one fails; the directory itself is left on disk — deleting it
is a separate, later decision.

**Two callerless functions belong to this stage, not to 1.5.** Both are
remnants of the systems Stage 3 is retiring, so deleting them in a tidy-up
would settle a design question by omission.

* **`netbox_client._scan_device`** — the SSH scanner the NetBox import used
  to run. Zero callers; import reads `_scan_device_from_golden` instead.
  **Its being callerless is *why* the tab text was wrong** (1.6): the
  description outlived the mechanism, promising that unreachable devices
  would be skipped when nothing was reaching out to find out. So 3.3 decides
  **explicitly whether NetBox import should ever do a live scan** — a live
  scan is the only thing that can report a device as unreachable, and today's
  golden-config path cannot make that claim at all. Deleting the function
  first would make "no" the answer nobody chose.
* **`config_git.write_and_stage`** — the stage-then-commit-later golden path.
  Zero callers; `migrate.py` mentions it only in a docstring. It is the other
  half of the Git tab's stale description, and its removal is part of
  retiring that flow rather than a separate cleanup.

*Acceptance for these two:* the live-scan question is answered in writing
before either is touched; whatever is removed goes through
`scripts/check_removed_definitions.py` (both are Python, so it does cover
them — unlike 1.5's JavaScript).

**A third reader, and the one with consequences: `drift_check`.**
Measured while closing 1.3b. It diffs the golden against a live
`show running-config` **raw** — `_clean()` strips volatile and boilerplate
lines and nothing secret-related — so a hand-changed SNMP community *is*
detected. That part works.

But it enumerates devices with `ai_assistant._list_golden_configs()`, which
lists the **legacy directory**. Content resolves manifest-first, so what it
compares is current; **what it never compares is a device with no file
there** — and nothing writes there any more.

> Every device onboarded after the migration is outside drift detection,
> silently. The nine existing devices are covered **only because their legacy
> files predate the migration** — the coverage is accidental, not designed.

Same shape as 1.6's NetBox line: a protection that reads as present because
nothing says it is absent.

*Acceptance:* `drift_check` enumerates from the **manifest** — the same source
`save_golden` writes; a test asserts a device present in `config_repo/golden/`
and absent from `golden_configs/` is checked; the run reports **how many
devices it checked against how many the inventory holds**, so a device outside
the check is visible rather than absent.

**This makes 3.3 a prerequisite for Stage 4 by ordering rather than by
memory.** r6 onboarded before it is a device outside drift detection from
birth.

**And it is not running.** Measured 2026-09-23: the drift checker is
**Disabled** — the scheduled pass is off — and the clean 9/9 result came from
clicking *Check Now* on the Approvals tab. So today it covers the nine legacy
entries **and only when somebody presses a button**.

That is one decision, not two: *what it enumerates* and *whether it runs* are
both answers to "is drift detection a thing this system does". Deciding the
first while leaving the second off would produce a checker that enumerates
correctly and never fires.

---

### 3.3 — DONE (code) 2026-09-23. Re-enabling is the one item left.

**The premise was wrong and the finding is larger than the plan said.** Not
three readers: `_list_golden_configs()` has **17 executable call sites across
9 modules**, and it was `os.listdir(golden_configs/)` and nothing else while
`_load_golden_config_file()` resolved through the manifest. **Enumeration and
content came from different stores.** Two call sites were already correct
(`routes/deploy`, `routes/templatize._captured_config`), both fixed during
Stage 1 for this same reason.

Delivered:

* **3.3a — one enumerator.** `repo.list_goldens()` reads the manifest;
  `_list_golden_configs()` is a thin adapter with an unchanged return shape,
  so fifteen call sites were fixed without being edited. `saved_at` is the
  commit time, not the mtime. Legacy-only devices are still returned, flagged
  `legacy`. `golden_commit_times()` is one `git log` for the whole store, not
  one per device.
* **3.3b — drift's population is the inventory.** Every device lands in
  exactly one bucket; totals are checked against the inventory size and any
  remainder is reported as a defect rather than as a smaller number; the
  panel says "checked 7 of 9" and names the other two. The badge cannot read
  `Clean` when nothing was checked. `event_monitor` was fixed in the same
  pass — it read `devices.csv` by hand and fell back to `DATA_DIR/Devices.csv`,
  i.e. **another list's devices**, for any NetBox-sourced list;
  `_check_empty_variables` had the identical bug and is fixed too.
* **3.3c — scheduling.** Cause established by measurement: a **setting**,
  switched off 2026-08-30 02:41, three minutes after a run that flagged all
  nine devices against ad-hoc stale goldens. Correct then; the reason stopped
  holding weeks ago with nothing to prompt a re-evaluation. The three defects
  around it are fixed: state is per list (adopting the old file forward by
  copy, not move), `_save_state()` merges instead of replacing, and
  `set_disabled()` records `disabled_at`/`disabled_by` while the panel shows
  the note and the last run instead of blanking the line. `status()` reports
  `state` as disabled / idle / running.
* **3.3d — the live-scan question, answered in writing: no.**
  `netbox_client._scan_device` is **deleted** (140 lines). A live scan would
  make NetBox import depend on device reachability and would import observed
  state into the source of truth, which is the wrong direction; refreshing a
  golden and re-importing is one store and one direction. The test moved from
  "nothing calls it" to "it does not exist".
* **3.3e — a retirement condition.** `legacy_only_goldens()` +
  `GET /golden/legacy_store` + a Golden-tab card that says either "still holds
  N device(s)", naming them, or "can be retired". The header-scan warning now
  logs once per device per process.

Also: `approval_queue._exec_update_golden` reported a `golden_configs/` path
nothing had written since the migration; it now reports the path actually
written. And `scripts/check_removed_definitions.py` was taught to tell a use
from a mention — deleting a function and pinning its removal are the same
commit, so the old word-grep made the gate permanently unsatisfiable.

**`config_git.write_and_stage` is NOT done.** It is the other callerless
remnant named above and belongs to retiring the Git-tab flow. Carried
forward.

### STAGE 3.3 COMPLETE — 2026-09-23

The scheduler was re-enabled last, after 3.3a and 3.3b, and **the first
scheduled run landed on its own**: `scheduled 9 of 9` at 2026-09-23 04:03:14,
fired from the in-memory schedule re-armed when the toggle was enabled
(`now + interval`), not from the state file and not from a button.

**That is the first scheduled drift check since 2026-08-30** — the run three
minutes before the feature was switched off, which flagged all nine devices
against stale ad-hoc goldens. Same feature, same fleet, now measured against
committed goldens: **9/9 clean.**

The ordering was the point. Re-enabling first would have reproduced August: a
scheduled job producing alarms nobody trusts, whose fix is to switch it off
again. Re-enabling after the enumerator and the population were fixed made
the first run a measurement rather than an alarm.

Stage 3.3 closed on all five parts: inventory-based enumeration, coverage
reported per run, disabled distinguishable from idle, the legacy store given
a retirement condition, and the scheduler actually running.

*Acceptance, extended:* the scheduled pass is enabled with a stated interval,
or drift detection is deliberately recorded as manual-only with the reason —
not left off by default with nothing saying so.

---

### STAGE 4 — Phase 4 onboarding wizard, then r6

Per the decisions already recorded in `docs/NSOT_PHASE4_ONBOARDING.md`:
measured bootstrap profile, one commit per wizard run, a random one-time
bootstrap credential rotated at the end, `allow_new` minting confined to the
wizard and Add Device, and **the AI assistant can never mint**.

Additional item: **remove vrnetlab's RW public community.** The history scan
acknowledged nine read-only communities; anything RW arriving with a new node
is a different matter and is removed as part of onboarding, not after.

**r6's topology — DECIDED 2026-09-23. Management-only first; the eBGP branch
site is a separate, later change.**

Stage 4 is therefore three steps, in order:

1. **The wizard, proven on a throwaway probe node.** Implementation plan:
   **[NSOT_STAGE4C_PLAN.md](NSOT_STAGE4C_PLAN.md)** — six build steps, each
   with acceptance criteria and a negative control **in the suite**, plus the
   probe topology and its teardown. Two things are left open there for a
   decision: whether step C runs on a `local` or `netbox` list (it changes
   what drift enrolment can assert), and whether the probe's NetBox objects
   go into the real NetBox or the NetBox step is proven by dry-run only.
2. **r6 onboarded management-only** — no data link, so **no existing node is
   touched**.
3. **The branch site (eBGP to r5) as its own change**, afterwards.

Two reasons, and the second is the stronger one.

**The cost.** r5 has no free interface: Gi1 management, Gi2 eBGP to r3, Gi3
eBGP to r4, Gi4 the simulated-Internet host. Every router in the lab is at
four data interfaces. So peering r6 with r5 needs a fifth NIC on r5, which
means a topology edit and an **r5 redeploy** — and r5 is the eBGP hub for
both r3 and r4, so their peerings drop during the window. Bundling that with
the wizard's first real run makes a bad outcome ambiguous exactly when it
needs to be clear: the wizard or the topology change, and no way to tell
while two routers' BGP is down.

**The demonstration is better split.** Adding the branch site afterwards
exercises **edit committed intent → plan → deploy on the first device whose
intent was AUTHORED rather than extracted from an existing configuration.**
Every other device's `host_vars` was back-filled from a capture; r6's would
be written by a person for a device that has never had that configuration.
That is a new property of the system, and it is worth demonstrating on its
own rather than folded into onboarding.

**Stage D is not a prerequisite for r6.** Measured: r6 is a C8000v, and
`cisco_iosxe` is in neither `GENERATES_SSH_KEY` nor `CONSOLE_REPLAYED`, so
its bootstrap config contains **no `crypto key generate rsa` line at all**.
Stage D measures an intersection r6 is not in. It is still required **before
any vIOS is onboarded** — the switches are the platform it applies to — and
is run when convenient rather than as a blocker.

**`transport input` — DECIDED 2026-09-23: `ssh` on both platforms.**

The C8000v branch emitted `transport input all`, which includes telnet,
reproducing r1-r3. **The standing rule does not apply**, and the exception is
worth stating because the rule is otherwise near-absolute: "a new default
reproduces the behaviour that predates the setting" exists to stop a setting
silently changing something that already works, and **a bootstrap config is
written for a device that does not exist yet** — there is no behaviour to
preserve. Reproducing `all` inherits an accident of how those five routers
were first built, not a decision anyone made.

Telnet would put the credential on the wire in clear text in r6's first
minute, which is exactly when that credential is the bootstrap one being
rotated. Verified safe before changing it: both drivers in `platform_map` are
SSH (`cisco_xe`, `cisco_ios`, not the `_telnet` variants), vrnetlab reaches
the device over the serial console rather than the vty lines, and the root
`telnetlib.py` shim exists because Netmiko *imports* the module, not because
anything here telnets. A test pins that.

`docs/bootstrap-probe/configs/bp-c8k.cfg` still reads `transport input all`,
deliberately: it is a **record of what stage A actually booted**, not a
template, and editing it would rewrite a measurement. The divergence is
**declared** in `test_bootstrap_config.py` and the test fails both if another
appears and if this one disappears.

### Deferred — tighten `transport input` on r1-r5

They still carry `transport input all` in their own configurations. **Not
part of Stage 4**: changing five live routers is not a side effect of fixing
a generator.

It is an ordinary change through the normal loop — edit committed intent,
plan, confirm, deploy — and is worth doing **visibly**, one device at a time,
because that is what the loop is for. Best scheduled after r6's branch-site
change, which is the other planned exercise of authored-intent deploys.

Note the shape before doing it: this is a **merge-only** path, so replacing
`transport input all` with `transport input ssh` is a *replace* on an
existing line rather than an addition, and the plan will report it as such.
The switches (`transport input telnet ssh`) are the same question and the
same answer.

*Acceptance:* the wizard onboards a probe node end to end — NetBox objects,
identity minted once, startup config generated and ASCII-guarded, bootstrap
credential rotated to a stored value, golden captured, one commit; the same
run against r6 succeeds; `r6` appears in the inventory, the manifest, Oxidized
and the topology service; no RW community exists on it.

---

### Scope of what remains — measured 2026-09-25

Counted from what these stages actually say, not estimated. **This is scope,
not an order**; the ordering constraints are named below it.

| Stage | Items | Build | Decide | Note |
|---|---|---|---|---|
| **5** — per-device monitoring | — | — | — | **FOLDED INTO 7.5 — DECIDED 2026-09-25.** Its six remaining items are 7.5's acceptance; switch syslog is carved out as **P.1** |
| **Before 7** — standalone | **2** (P.1, P.2) | 2 | 0 | P.1 switch syslog (a pipeline defect); P.2 NetBox backup (A1) |
| **6** — security | **5** (6.1–6.5) | 4 | 1 | infrastructure and device-side; touches no GUI. 6.5 added 2026-09-25 (C5) |
| **7** — the interface | **11** (7.0–7.9, incl. 7.2b) | 8 | 2 | **7.2b is DONE** — §0b's script extraction and §6c's cache headers both landed |
| **8** — AI and agent | **6** (8.0–8.5) | 4 | 2 | plus three named sub-findings inside 8.2/8.3 |

**⚠ Stage 5's seven was a different kind of number from the others**, and
the fold resolves it: the paragraph is now enumerated as 7.5's acceptance,
six items plus P.1. The original note is kept below because it is why the
enumeration was needed.

**⚠ Stage 5's seven is a different kind of number from the other three.**
Stages 6, 7 and 8 carry numbered item lists and were counted. **Stage 5 is one
acceptance paragraph**, so its seven is a *reading* of that paragraph — the
per-device Prometheus, Loki, Oxidized and lease views, retiring the legacy
collector, restoring switch syslog, and putting `logging trap` into intent.
Quote it as an estimate, not a count, and **enumerating Stage 5 is itself the
first item of Stage 5**.

**There is no separate settings rebuild.** Stage 3.2a — `migrate()` never
seeds, `ratify()`, the v2 trap — is **built and shipped**. What remains is
**one line item, 7.7 (*Settings split; Logs tab dissolved*)**, inside Stage 7.
It has been carried in conversation as a fifth workstream and is a single step
of an existing one.

#### What blocks what

**Nothing blocks Stage 7.** The dependencies run the other way:

- **Stage 7 → Stage 8**, explicitly and deliberately: the tool library must
  describe a finished system rather than a moving one.
- **The CI decision (GitHub Actions vs Jenkins) → 8.0 → 8.2.** Eighteen of the
  seventy-three tools are `jenkins_*` — a quarter of the library classified
  against a system that may not survive.
- **7.0 → everything in Stage 7.** The reachability test plus the invalidation
  map is the checklist every later step is written against.
- **Grafana `allow_embedding` + an Access policy for the embed path → 7.5 →
  7.9.** Named blockers, not measured ones; the iframe test comes first.
- **P.1 and P.2 are scheduled ahead of Stage 7 by the operator's DECISION,
  not by dependency.**
  Nothing in Stage 7 needs them. P.1 is a defect in a running pipeline, and
  every day it waits is a day of switch logs that do not exist. P.2 is what
  makes the Stage 7 work recoverable if it damages NetBox. It is the one
  store NMAS writes to that has no restore path.
- Stage 6 blocks nothing and is blocked by nothing.

**The overlap worth knowing: Stage 5 and Stage 7.5 are the same screens.**
Stage 5's per-device Prometheus / Loki / Oxidized / lease views and Stage 7.5's
Monitoring destination are one surface. Doing 5 before 7 means building it
twice — which is the argument the plan already makes for putting Stage 8 last,
and does not make here.

**DECIDED 2026-09-25: Stage 5 folds into 7.5.** The views are built once,
inside the redesigned interface, rather than built into the current UI and
rebuilt by Stage 7. Enumerating Stage 5 becomes 7.5's acceptance criteria;
see *Stage 5*, below. **The exception is switch syslog**, which is not a
screen. Logs that stopped arriving on 2026-09-09 are a defect in a pipeline
that runs whether or not anyone looks at it, and folding it into a UI stage
would schedule a repair behind a redesign. It is **P.1**, before Stage 7.

---

### STAGE 5 — Phase 5: per-device monitoring — FOLDED INTO 7.5 (decided 2026-09-25)

**No longer a stage.** Building these views before Stage 7 builds them twice,
because 7.5's Monitoring destination is the same surface. The acceptance
paragraph below is kept as written, since it is the source. Its enumeration
is **7.5's acceptance criteria**:

| # | 7.5 acceptance item (from Stage 5) |
|---|---|
| 7.5-a | A device page shows **its own** Prometheus series |
| 7.5-b | ... its own Loki lines. Switch lines must be flowing first, which is **P.1** |
| 7.5-c | ... its own Oxidized fetch history |
| 7.5-d | ... its own Kea leases |
| 7.5-e | The legacy SNMP/NetFlow collector is **retired**, not collapsed |
| 7.5-f | `logging trap` level set deliberately and **recorded in intent**, through the deploy path, not configured by hand |

Carved out: **switch syslog restored** is **P.1**, below. Stage 5's derived
count was seven, and this is six plus P.1, so the enumeration agrees with the
reading. If P.1 finds that restoring syslog needs a logging change on the
switches, that change is 7.5-f made early, through intent. It is not a
hand edit.

Per Section 6's Phase 5, narrowed by what Part 1 built: the Integrations panel
already gives the fleet view. This stage is the **per-device** view.

*Acceptance:* a device page shows its own Prometheus series, its own Loki
lines, its own Oxidized fetch history and its own leases; the legacy
SNMP/NetFlow collector is retired rather than collapsed (it is currently
collapsed under "Built-in collectors (legacy)"); switch syslog is restored —
**it stopped around 2026-09-09 and the Loki card showed 0 lines during the
demo**; `logging trap` level is set deliberately and recorded in intent, not
configured by hand.

---

### STAGE 6 — security

**6.1 Docker publishes past ufw.** Measured on the deployment host: NetBox
`:8000`, Loki `:3100` and oxidized-web `:8888` are reachable from the whole
LAN despite ufw's default deny, because Docker's rules in `DOCKER`/`DOCKER-USER`
are evaluated ahead of ufw's chains. **oxidized-web serves every device's full
running configuration** and is the largest of the three by a wide margin. It
surfaced only by contrast: Grafana runs as a native process and *was* blocked.
*Acceptance:* the three ports are unreachable from another LAN host — verified
**from another host**, not by reading a rule table, which is the presence-check
mistake again. Bind to `127.0.0.1` or add `DOCKER-USER` rules.

**6.2 Per-consumer accounts.** One `admin` credential is shared by NMAS,
Oxidized and any future consumer, so a rotation moves the floor under all of
them at once and no audit trail distinguishes them.

**6.3 The `yang-push-sub` credential**, and **6.4 enable secret vs console
recovery** — the console is the break-glass path, and an enable secret nobody
holds turns a recoverable node into a rebuild.

**6.5 The NMAS service unit is unhardened and unversioned** (C5, measured
2026-09-25). The host runs `flask-app.service`: `Restart=always`, enabled,
journal. That part is right. It has **none** of
[DEPLOY_LINUX.md](DEPLOY_LINUX.md)'s hardening (`NoNewPrivileges`,
`ProtectSystem`, `ProtectHome`, `ReadWritePaths`) and sets **no `NMAS_HOST`**,
so the app binds every address. CLAUDE.md asks for a specific address as a
second layer independent of the firewall. The unit and `~/bin/nmas-deploy` live
only on the host, so the unit the repository describes and the unit that runs
have diverged in name, hardening and environment, and nothing notices.
*Acceptance:* the unit and deploy script are versioned in the repository with
one copy (the host file a symlink or an install step, never a second copy),
hardened, and bound to a named address. Verified **from another host** that
`:5000` answers only where intended. Measured before and after, like 6.1.
Whether to rename it `nmas` is part of 6.5. Renaming touches the unit,
`nmas-deploy` and every runbook line naming it, for no functional gain. The
lean is to keep `flask-app` and make the docs say so.

*Why here and not ahead of Stage 6:* what C5 actually cost was a **log
channel named wrongly**, and that is fixed. The docs and the CLI name
`logs/device_manager.log`, and the CLI reads it. What remains is posture
(privileges, bind address), which is Stage 6's subject and uses its method:
measure from another host.

*Acceptance:* each is measured before and after; 6.2 ends with a rotation that
changes one consumer's credential without disturbing another's.

---

### BEFORE STAGE 7 — two standalone items (the operator's decision, 2026-09-25)

*Recorded with who made it, because a decision recorded without an owner
reads as a scheduling fact, and the next reader cannot tell a choice from a
constraint. Nothing in Stage 7 depends on these. The operator put them first:
P.1, P.2, then 7.0.*

**P.1 Switch syslog stopped around 2026-09-09.** The Loki card showed 0 lines
during the demo. It is a pipeline defect, not a view, so it is carved out of
the Stage 5 fold. *First measurement:* find where the chain breaks, hop by
hop. Does a switch emit (`show logging`, the `logging host` line)? Does the
receiver get packets (a capture on its port)? Does the shipper forward? Does
Loki hold switch-labelled streams? Every hop gets checked, not just the most
likely one. *Acceptance:* switch lines queried **from Loki**, from all four
switches, with a timestamp after the fix. If it needs a device-side change,
that change goes through intent (7.5-f), not a hand edit. And the loss gets a
signal: a switch that stops logging must show up somewhere other than a
count of 0, or the next outage is found the way this one was.

**P.1 — MEASURED 2026-09-25: nothing stopped. The pipeline is working, and
the devices are configured to say almost nothing.** Each hop was checked
against the store that would hold its evidence:

| Hop | Evidence | Result |
|---|---|---|
| Device generates | `show logging` buffer, per severity, since the 22 Sep boot | s1/s2/s4: **zero** messages at severity 0-2. s3: one. r1: two, both before its logging-host session started |
| Device sends | `Logging to 10.255.1.10 … N message lines logged` | s1/s2/s4/r1: **0**. s3: **1** |
| rsyslog files | `/var/log/network/<src>.log` (filter: source starts `10.255.1.`) | s3's one line present (`Sep 22 23:44:05`) |
| Alloy reads | runs as `alloy`, groups include `adm`; files are `0640 syslog:adm` | readable. **Permission hypothesis refuted** |
| logrotate | `postrotate` restarts `alloy` | inode tracking is reset each rotation. **Refuted as today's cause** |
| Loki holds | `count_over_time` per `filename`, daily since 1 Sep | matches the files exactly; s3's line is there on 22 Sep |

**Why it looks like "stopped around 9 Sep":** syslog was first configured on
**7 Sep**, and every device has been at **`logging trap critical`** since
**8 Sep 01:33** (Oxidized history; s1 briefly ran `debugging`). Critical passes
severity 0-2 only. Link up/down (3/5), OSPF adjacency (5), config change (5)
and login events never leave the device. So the Loki card read 0 during the
demo **correctly for the configured level**. The positive control is in the
data: s3 generated one severity-2 line, sent it (counter 1), and Loki holds
it.

**Therefore P.1 is a trap-level decision plus a heartbeat, not a repair.** It
also finds two coverage gaps:
- **r6 has no logging configuration at all.** Onboarding never gives a device
  syslog, so every device added after the reference nine is silent by
  construction.
- **The rsyslog filter files only sources in `10.255.1.`.** A device logging
  from any other address (r6's management `10.255.0.32`, if it has no
  `source-interface Loopback0`) lands in `/var/log/syslog`, and Alloy never
  sees it.

**Freshness needs a source of expected non-silence.** At `critical`, silence
is the normal state, so "no switch lines for N minutes = failure" would fire
permanently. At `notifications` it would still fire on any quiet hour. The
signal only means something if every device emits on a clock. The proposal:
an **EEM timer applet** per device (`event timer watchdog time 300` →
`action syslog priority critical msg "NMAS-HEARTBEAT"`). It emits *at* the
trap level, so it exercises every hop from the device to Loki, whatever level
is chosen. The failure signal is then **no heartbeat from device X in Loki
for 2 intervals**, per device, named. **EEM is not modelled**: no parser,
template or fixture carries `event manager`. Putting it into intent means a
parser + template + round-trip change and a deploy to every device, through
the confirmed path.

**P.1 DECIDED 2026-09-25**, and what is built so far:
1. **Trap level `notifications`, through intent.**
2. **Heartbeat:** EEM `event timer watchdog time 300` →
   `action syslog priority notifications msg "NMAS-HEARTBEAT"`; alert after
   2 missed. **Heartbeat, trap level, logging host and source-interface are
   ONE template block**, so a device cannot carry some of the block and not
   the rest.
3. **Onboarding gives every device that block as part of its baseline.** r6
   gets it through that path, not by hand.
4. **Alerting: Grafana alert rules on Loki, generated from the NetBox
   inventory** (one expected heartbeat per device), **NoData = alerting**,
   provisioned from the repository. NMAS displays Grafana's alert state in
   7.5 and does not run the check itself.
5. **The rsyslog address filter is fixed, not registered.**
   [deploy/rsyslog/10-network-devices.conf](../deploy/rsyslog/10-network-devices.conf)
   binds the UDP input to its own ruleset and files every message by source
   address, so no addressing plan lives in a host file. It passes
   `rsyslogd -N1` on the host (8.2312.0). Installing it needs sudo, so it is
   not yet live.

**EEM measured on both platforms: `docs/bootstrap-probe/nmas-eem-probe.clab.yml`**
(a throwaway lab on the clab host, 172.30.70.0/24, same images as the fleet,
60 s watchdog):
- **vIOS-L2 executes it.** Four firings exactly 60 s apart (16:33:44 through
  16:36:44), each recorded in `show event manager history events` as
  `success`. The line is `%HA_EM-5-LOG: NMAS-HEARTBEAT: NMAS-HEARTBEAT`, so
  its severity (5) passes `notifications`, and the logging-host counter moved
  (7 lines sent).
- **C8000v executes it too.** Three firings exactly 60 s apart (16:37:54,
  16:38:54, 16:39:54), each `success`, the same `%HA_EM-5-LOG` line, and the
  host counter moved 15 → 19. Its first firing came 60 s after the applet
  registered (16:36:53), and the same holds on vIOS.
- **One firing was not taken as proof of a timer.** The C8000v's first
  measurement showed exactly one, so the probe was polled until there were
  three.
- Torn down with `--cleanup`: 0 probe containers, 0 probe networks, lab
  directory removed, and the clab host back to its 16 production containers.

**Two findings on the way:**
- **NMAS's Grafana integration is not configured** (`grafana_url` is empty),
  so generating the rules needs the Loki datasource UID from Grafana
  itself. Whether this is another casualty of the 2026-09-23 settings
  erasure is not established.
- **The probe's own wait loop passed on the opposite state.** It matched the
  substring `healthy`, which `unhealthy` contains. Caught because the first
  measurement found neither node up. The check is now an exact comparison.

**BUILT 2026-09-25 (P.1 code, all mocked or offline; nothing deployed):**
- **The block is modelled.** The parser puts trap, origin-id,
  source-interface, hosts and the exact `NMAS-HEARTBEAT` applet into
  `logging.syslog`. Any other applet, or a near-miss body, stays
  `unmodeled`. The template renders the block together.
  - **Round-trips at 100%** on r1 (C8000v) and s1 (vIOS-L2) with the lines
    **captured from the devices themselves**. Probe run 2 captured
    `show running-config` on both platforms, and every line renders
    identically.
  - The fleet round-trip is unchanged, and each pre-P.1 device parses to a
    **partial** block (no heartbeat).
- **Whole-or-absent is enforced where intent is AUTHORED**: the editor gate
  (`routes/templatize.py` step 2c) and `write_committed_text()`, both
  through `hostvars.syslog_block_problems()`.
  - **Not** at `write_committed()`. That path takes extracted intent, and
    refusing a pre-P.1 device's true, partial block blocked Extract → Commit
    for the whole fleet when it was tried. Both directions are pinned.
- **Onboarding's baseline:** `build_plan()` merges the block from five
  `syslog_*` settings, and refuses by name while `syslog_host` is empty (the
  third deliberate exception to the defaults rule). The block reaches the
  committed intent (tested through `commit_step`).
- **`scripts/nmas-heartbeat-rules`:** one Grafana rule per NetBox device,
  NoData = Alerting, window = 2 intervals + 60 s, hostname match anchored
  (`\s<host>:\s`, a LogQL backtick string), `--check` for staleness.
  - Run against live NetBox from `/tmp`: 10 rules, r1–r6 and s1–s4.
  - **That run found a defect.** The live checkout lacked the setting, the
    interval read as 0, and the generator wrote ten rules with a **60 s**
    window, every device alerting every minute from a file that looked
    right. An interval below 60 is now refused.
- Controls shown failing for every refusal above.

**What remains, and whose it is:**
1. **Operator:** pull, then install `deploy/rsyslog/10-network-devices.conf`
   and restart rsyslog. **It writes `/var/log/network/<source-ip>.log`**, the
   same directory as before. The conf file's name is not a path, and on
   2026-09-25 the name sent the operator to look in an empty
   `/var/log/network-devices/`, which made a working install look broken.
   **Positive control:** `logger -n 127.0.0.1 -P 514 test` must create
   `/var/log/network/127.0.0.1.log` immediately. Delete it afterwards.
   *DONE 2026-09-25 by the operator: 45 bytes, immediately; removed.*
2. *(Step 2 DONE 2026-09-25: `syslog_host = 10.255.1.10`, the other four at
   their defaults.)*

   **Why P.1, in one listing** (the operator, 2026-09-25): every current
   device log is 0 bytes. The last content per device: s1 7 Sep, s2 8 Sep,
   s3 22 Sep, s4 7 Sep, r1 22 Sep, r2/r3/r4 15 Sep, and r5 has no file at
   all. Nine devices effectively silent for weeks, which is exactly what
   `logging trap critical` produces when nothing is critical, and nothing
   distinguishes it from a collector that stopped. The heartbeat makes
   silence a signal rather than the normal state.
2. **Operator:** set `syslog_host` in `data/user_settings.json`. It is
   file-only for now, a recorded gap for 7.7.
3. **Operator:** update the network's own `templates/_common.j2` to the
   shipped version, in the Templates editor. **Seeding never overwrites, so
   the shipped change reaches no existing network by itself**
   (OPEN_FINDINGS C6). That edit revokes both approvals, and re-approving is
   a person's act. **Check it:** `scripts/nmas-seed-status --list Default
   --no-netbox` reads `_common.j2` **stale** (at `4771a4c`) before the edit,
   and must read **current** after it. Anything else, such as `edited`,
   means the pasted text is not byte-identical to the shipped file.
   *DONE 2026-09-25 17:55 (operator): `_common.j2` committed as `d1057dc`,
   and both templates re-approved with no changes, against r1–r6 and s1–s4.
   The approval gate caught the edit from the fingerprint, not from the
   editor: `/templates/approval/<path>` read `approved: false`, "the template
   was edited", with previous timestamps kept. **Correction to this step's
   wording:** `_common.j2` could not be opened from the Template library,
   which hid every `_`-prefixed file, so the edit was made in the shell. From
   the commit after `dd9d6ac` the panel lists it as a shared file, with what
   editing it revokes and Edit only (it has no approval of its own).
   `GET /templates` carries NO approval field; `/templates/approval/<path>`
   is the only answer.*
4. **Per device, one at a time:** complete the block in committed intent
   (trap `notifications`, heartbeat 300; r6 needs the whole block), then plan
   and confirm through the deploy path. Confirm needs a person.

   **The edit, for the nine existing devices** (switches also keep
   `console: false`):
   ```yaml
   logging:
     hosts: []
     settings: []
     syslog:
       trap: notifications
       origin_id: hostname
       source_interface: Loopback0
       hosts:
       - 10.255.1.10
       heartbeat: 300
   ```
   The three `settings` lines and the `hosts` entry MOVE into the block. The
   editor refuses the same fact in two places ("one owner per fact").
   **r6** has `logging: {hosts: [], settings: []}` and gets the same block
   whole. It reaches the collector through its `10.255.0.0/16 via 10.255.0.1`
   route, sourcing from Loopback0 (`10.255.1.16`).

   **The program the plan must show**, computed with `merge_commands()`
   against the fleet fixtures for s4 and r2:
   `logging trap notifications`, then `event manager applet NMAS-HEARTBEAT`
   with its two children, then `exit`. Nothing else. Rollback: `logging trap
   critical` and `no event manager applet NMAS-HEARTBEAT`. For r6, also
   `logging origin-id hostname`, `logging source-interface Loopback0` and
   `logging host 10.255.1.10`. **Any other line in the preview means the
   device or its secrets drifted: stop.**

   **Order**, and why:
   1. **s4** (vIOS-L2 leaf, not the manager's gateway) proves the switch
      path end to end.
   2. **r2** proves IOS-XE.
   3. s1, s2, r1, r3, r4, r5.
   4. **s3** after those: it is the manager's L2 gateway (Vlan99). A logging
      change does not touch reachability, but s3 is the one device where a
      surprise costs the whole lab.
   5. **r6** last: the only full-block deploy, in its own lab.

   **Check each before the next.**
   - The deploy result verifies, and one golden commit is written.
   - `show logging` reads `Trap logging: level notifications`.
   - Within one interval (first firing ~300 s after the applet registers,
     measured on the probe),
     `grep NMAS-HEARTBEAT /var/log/network/<loopback-ip>.log` has a line,
     and Loki `{job="network_syslog"} |= "NMAS-HEARTBEAT" |~ "\s<host>:\s"`
     returns it. That is the same anchored match the Grafana rule uses.

   **s4 DONE 2026-09-25 (operator), every check:**
   - `Trap logging: level notifications`.
   - The applet is on the device and in the captured golden, byte-identical
     including the leading space. Golden commit `b222441`, tagged
     `golden/s4/20260925T180857Z`.
   - Two `%HA_EM-5-LOG` heartbeat lines in `10.255.1.24.log`, and Loki
     returned both through the rule's own anchored query. The deploy's own
     `%GRUB-5-` messages arrived too, and severity 5 is proof by itself that
     `notifications` took effect.
   - Device clock 02:02:37.298 → 02:07:37.311, exactly 300 s: the watchdog
     re-arms, it does not fire once.
   - **Arrivals 18:15:12 → 18:21:43, 391 s apart: 91 s of jitter between
     the device's timer and the collector.** That measurement changed the
     alert window from 2I + 60 = 660 s (which one missed heartbeat plus 91 s
     would already exceed) to 2.5I = 750 s. That is quiet on one miss and
     firing on two, for any jitter below I/2
     (`nmas-heartbeat-rules`, `WINDOW_MULTIPLIER`).
   - The device clock reads 02:02 while the wall clock read 18:15, so **the
     device's own timestamps cannot be used for arrival**. What the rule
     counts is Loki's timestamp.
5. **Operator:** generate the rules with the Loki datasource UID, install
   them into `/etc/grafana/provisioning/alerting/`, and reload Grafana.
6. **Acceptance:**
   - Heartbeats from all ten devices in Loki.
   - One deliberately silenced device alerting.
   - **The fleet's arrival spread re-measured:** over at least an hour of
     heartbeats, the largest deviation of any device's inter-arrival gap
     from 300 s. It must stay below 150 s (I/2), or the 2.5I window no
     longer separates one missed heartbeat from two. The 91 s behind the
     window is one device over one interval.

**Remaining P.1 build, in order (as first written):**
1. The logging block into the parser, the templates and host_vars (a new
   modelled construct: EEM applet + logging settings), with a round-trip
   against the fleet fixtures.
2. The block into onboarding's baseline.
3. The rule generator: from NetBox, keyed on **hostname** (from
   `logging origin-id hostname`), not on the file name, because a device
   sourcing from Loopback0 is filed under an address that is not NetBox's
   primary IP.
4. Deploy per device through the confirmed path, one device, one commit.
5. The P.1 acceptance: heartbeats from all ten devices in Loki, and one
   deliberately silenced device alerting.

**P.2 NetBox backup and a tested restore path (closes the core of A1).**
Sized on the host, 2026-09-25. NetBox is `netbox-docker` under
`~/netbox-docker`, image `netboxcommunity/netbox:v4.6-5.0.2`,
`postgres:18-alpine`. The database is **30 MB**. The `media`, `reports` and
`scripts` volumes are **empty** (4 KB each). The root filesystem has 259 GB
free.
- **Backup:** a scheduled `pg_dump -Fc` of the NetBox database plus a tar of
  the media volume, run on a timer. Nightly at 30 MB costs nothing, and
  retention is a count, not a disk question.
- **Restore path:** `pg_restore` into a **scratch** NetBox (a second compose
  project on another port, same image tag, same postgres major), never into
  the live one. It is tested by **comparing** the restored instance with the
  live one at dump time: `nmas-netbox-census` identity-per-type **and** a
  per-table row count. The census alone compares identity, not contents, so
  it would pass a restore that lost every field value.

**Does it close A1? The core, yes; four things remain, and they are part of
P.2, not later:**
1. **Configuration is not in the database.** `~/netbox-docker/env/netbox.env`
   holds `SECRET_KEY` and `API_TOKEN_PEPPER_1`, which
   `configuration/configuration.py` reads into `API_TOKEN_PEPPERS` (names
   confirmed on the host, values not read). Restoring the database without
   the pepper invalidates every v2 API token. Whether NMAS's own token is v1
   or v2 is not measured. They are
   secrets, so they go into the backup encrypted, never into git.
2. **Same host is not a backup of the host.** A dump beside the database it
   dumps survives a bad write and not a lost disk. At least one copy goes off
   the host.
3. **The versions are part of the restore.** A dump records the NetBox image
   tag and the postgres major beside it, and a restore refuses a mismatch
   rather than migrating silently.
4. **A backup job that fails silently is A1 again with a false sense of
   safety.** The age of the last successful dump is surfaced, and a missing
   or old one is a named state. A timer that stopped is a backup that does
   not exist.

**BUILT 2026-09-25**: `scripts/nmas-netbox-backup`,
`scripts/nmas-netbox-restore-test`, `deploy/systemd/*`. Install and the
Proxmox-side setup are in [NETBOX_BACKUP.md](NETBOX_BACKUP.md). Measured on
the VM from `/tmp`:
- backup: 198 tables, 3,142 rows on the dump's own snapshot;
- encryption: decrypts with the key, refuses without it;
- restore test: **PASS**, all counts identical.

The first live restore **failed correctly**: the count query reached
`docker exec` without `-i`, and the mocked seam could not see it.

Decided: the off-box copy is dailies only, via rclone, ~14 days, gpg. There
is no git copy. The units are system units, with no linger.

**Proposal (2026-09-25):** `pg_dump -Fc` **hourly** (retain ~24), promoted
to **daily** (retain ~14). Each backup is one directory: the dump, a media
tar, `env/` + `configuration/`, and a manifest (image tag, postgres major,
NetBox `VERSION`, per-table row counts taken on the **same snapshot** as the
dump via `pg_export_snapshot()` + `pg_dump --snapshot`, and sha256 of each
file).
- **On the host** (`0700`, plaintext): the restore-test source.
  `env/netbox.env` already sits on this host in the clear, so this adds no
  new exposure there.
- **Proxmox storage, outside the NMAS VM:** the same set,
  **gpg-encrypted to a public key**. The VM holds only the public key and
  cannot decrypt its own backups. A compromise of the VM cannot read what it
  has shipped.
- **Off the box:** the encrypted set again. The private key is kept off
  both the VM and the Proxmox host.
- **Not GitHub:** the env secrets have to travel with the dump for a restore
  to work.
- `age` is not installed; `gpg` is, and does the job.

What P.2 does **not** give: point-in-time recovery. A nightly dump loses up
to a day of **human** NetBox edits. NMAS's own writes in that window are
recoverable from the modification record and the golden configs, but hand
curation between dumps is not. That limit is stated here rather than left to
be discovered.

---

### DECISION TO MAKE — GitHub Actions or Jenkins for Part 2's pipeline

**Not decided.** Recorded before Stages 7 and 8 because the Jenkins tab's
fate in the redesign depends on the answer, and deciding it inside a UI
stage would be deciding it by omission.

Current lean: **GitHub Actions**, since commits already reach GitHub and
auto-push works.

**For Actions**

* No server to run. Jenkins is a process to keep alive, patch and back up,
  for a lab whose whole point is that the source of truth is a git
  repository.
* **The pipeline definition lives in the repo it tests.** A workflow file is
  reviewed, versioned and reverted like any other change — which is the same
  argument the NSoT work makes about configuration, applied to CI.
* Push-triggered fits the model directly: a config change *is* a commit, so
  "a config change triggers tests" needs no glue.

**Against Actions**

* **Cloud runners cannot reach the lab.** Anything that touches a device
  needs a self-hosted runner inside the network — which is an agent on the
  NMAS again, just a different one. Jenkins is already inside the network and
  already has the credentials.

**Likely answer: split by what the check needs.**

| Check | Where | Needs a device? |
|---|---|---|
| Schema validation | cloud | no |
| Jinja renders / template lint | cloud | no |
| Round-trip against committed goldens | cloud | no |
| Secret scanning | cloud | no |
| `assert_sendable` / ASCII over rendered output | cloud | no |
| Deploy verification, health, reachability | self-hosted | yes |

**Most of what a CI gate should catch is repo-only**, which is the strongest
argument for the split: the majority of the value needs nothing inside the
network, and the minority that does is exactly the part that already has a
home.

**Two things need rethinking either way.**

1. **CI results are recorded as git notes on the commit** (`refs/notes/ci`,
   `repo.add_ci_note()`), so a workflow that records its own result needs
   **write access to the repository** — and `remote.py` pushes `refs/notes/*`
   through the same path as everything else. That interacts with the publish
   gate: `publish_remote` requires a verified **person** by default, and the
   HTTP publish routes enforce it. Note that the post-commit hook does *not*
   go through that gate — it is unattended by design, and
   `nsot_git_auto_push` defaults off — so there is already an asymmetry
   between operator-initiated publishing and automatic publishing, and a CI
   writer would be a third kind. **Measured while recording this:
   `add_ci_note()` has no callers.** Notes are a built capability, not a
   current practice, which makes this cheaper to decide now than later: there
   is no existing behaviour to preserve.
2. **`jenkins_step_shell` becomes moot for anything that moves.** The
   `bat`/`sh` setting exists because a Windows Jenkins agent and a Linux one
   need different step syntax. A workflow file declares its own runner, so
   the setting covers only whatever stays on Jenkins — and if nothing does,
   it is a setting with no subject.

**What the decision gates.** Stage 7's redundancy pass currently folds the
Jenkins tab into Fleet → Changes as a CI strip on the deploy record. That
holds either way — the strip shows *a* CI result — but what it links to, and
whether Jenkins pipeline management survives at all, follows from this.
`modules/pipeline.py` and `pipeline_builder.py` stay regardless: the 9-stage
pipeline is NMAS's own and is not Jenkins.

---

### STAGE 3.2a — migrate() does NOT write a value nobody chose

Decided 2026-09-23, after 3.2c made the state visible. On the real install
**one of eight gate decisions had ever been recorded**; the other seven were
correct because the defaults matched, which is a different claim from
configured.

**`migrate()` will not seed a default.** Writing one would make *defaulted*
and *chosen* indistinguishable again, which is the defect 3.2c exists to
remove — and it would do it to every install at once, permanently, since
nothing afterwards could tell which writes were decisions.

Three reasons beyond that one:

1. **A seeded default freezes an install at the default-of-the-day.** The
   standing rule is that every new default reproduces the behaviour that
   predates the setting; changing one later is therefore a deliberate act
   with a reason. An install whose file was seeded would silently **not**
   receive that change, because an explicit value wins. Seeding converts
   "follows the project's judgement" into "pinned to whatever it was on the
   day you upgraded", invisibly.
2. **Absence is information.** `origin: default` says nobody has considered
   this. That is worth knowing and cannot be recovered once written.
3. **It would be a write with no author.** Everything else gated in this
   system records who decided — `Actor:` trailers, the reveal audit, the
   approval queue. A settings write attributed to a migration is the one
   decision in the program with nobody behind it.

**Instead, recording a decision becomes an action.** The posture panel gains
*Record this decision*, which writes the **currently effective value** with
an actor and a timestamp. Writing then means somebody decided.

**It can only ratify, never change** — it writes the value already in force.
That keeps 3.2c's constraint intact: a browser session still cannot lower a
gate, because the only value the control can write is the one already
applying. Changing a gate stays a host-side edit, for the reason written on
the panel.

The panel then shows three states rather than two: **defaulted** (nobody
decided), **ratified** (written, equals the default — somebody agreed), and
**chosen** (written, differs from the default).

**The v2 trap is part of this item.** `migrate()`'s v0→v1 block seeds every
absent key and is reached whenever `current < SCHEMA_VERSION`. Measured: a
bump to v2 seeds **98 keys on a v1 install, including all eight identity
gates** — silently rewriting every "defaulted" as "set explicitly" across
every install, in a release that will look like an unrelated chore. Seeding
must be scoped to the keys a bump is actually about, and a test must fail if
a version bump would seed a `require_*` key.

---

### STAGE 7 — the interface, redesigned

**Scope changed 2026-09-23: this is a GUI redesign, not a tab cleanup.**
Written up in full as **[NSOT_STAGE7_GUI.md](NSOT_STAGE7_GUI.md)**, posted
early so that Stages 3.2 and 4-6 can land in the new structure rather than be
rearranged twice. That document governs; this is the summary.

The premise: the program's scope changed and the interface is a record of how
it grew. Twelve tabs named after subsystems are a map of how the program is
built, useful only to somebody who already knows. Almost nothing a person
does here is "use NetBox" -- it is *look at this device*, *change this
device*, *is the network healthy*, *what changed and who changed it*.

Measured before proposing anything: **217 routes, 48 of them reachable from
no page at all.** Nine are Phase 3 features with no entry point, including
`authorise_retry()` -- a device can enter a rollback-blocked state from the
GUI and can only leave it from a terminal -- and `approval.revoke()`, whose
tombstone exists so a withdrawal is a recorded finding. Four are credential
management, which is configurable only over HTTP.

**Scale is a constraint on the architecture, not a later feature** (§0a,
recorded 2026-09-23): the interface is for an enterprise network, not for
nine devices. Measured — the device row emits 7 interactive elements, so 900
devices is 6,300 on one page; `index()` loads the whole inventory with no
bound; there are **52 unbounded `load_saved_devices()` calls** and **no
pagination parameter anywhere in `routes/`**. So: selection replaces
enumeration, fleet health is the landing view and the device list is where
you arrive after clicking a number, per-device actions leave the row,
everything is bounded and every fleet-wide operation is a job with progress
and a targetable subset — and **nothing may do per-device work to render a
page, including the landing counts**. An interface that assumes you can see
every device is a different interface from one that assumes you cannot.

**The fixture corrected the premise before it was built against.** Measured
at 900 devices, the whole read is **0.73 ms** and one per-device `git log` is
**7.2 s** — so the constraint is *not* "don't read everything" but **"don't
do per-device work per request"**, which is a different design: far fewer
sites, and the ones that decide whether the interface works. Separately
(§0b), the page is **647 KB fixed plus 2,239 B per device** — the fixed cost
is an `index.html` problem that exists at nine devices and is not a scale
item at all.

Shape: two destinations (**Fleet**, **Monitoring**) plus a per-device page at
`/device/<hostname>`, and a service-status bar on every page.
**Monitoring becomes a destination rather than a status board**: Grafana
embedded (`grafana.dmarchak.dev` and `nmas.dmarchak.dev` are both public
through Cloudflare, so no proxy is needed -- but Grafana needs
`allow_embedding` plus `frame-ancestors`, and Access, if it fronts Grafana,
blocks framing and needs a policy for the embed path; **both are named
blockers, not measured ones, and the iframe test comes first**), Kea lease
detail including expired leases, Loki made queryable, NetBox reduced to a
summary. **The Git tab becomes the version-control home** -- commits, tags,
baselines, per-device history, remote and push state, which are today
scattered across Devices. **Topology's removal is not scheduled**: the
NetworkX view stays until an embedded view actually shows the topology.

A redundancy pass gives every pre-NSoT feature keep / fold in / remove with a
reason. `/configure/apply` is deliberately left open pending a usage
measurement -- deciding it from the plan would be deciding by omission.

*Acceptance:* per-route reachability, with an allowlist that only shrinks;
every inventoried action has exactly one home and a test asserting its entry
point exists; every consequence line is pinned to what the code does; the
Grafana embed either renders or names the blocker it hit; no behaviour
changes -- Stage 7 moves controls and adds entry points.

---

### STAGE 8 — the AI assistant and the background agent

**Deliberately last, after Stage 7.** The tool library has to describe the
finished system rather than a moving one; reviewing it against an
architecture still being reorganised means doing it twice and believing the
first answer.

Recorded now so it is not rediscovered. **Plan when we get there** -- but the
measurements below were taken 2026-09-23 while recording it, because two of
them change how urgent this is.

**8.0 Prerequisite:** the CI decision recorded above (GitHub Actions vs
Jenkins) should be settled before the tool review, because eighteen of the
seventy-three tools are `jenkins_*` — a quarter of the library classified
against a system that may not survive.

**8.1 Models.** `ai_assistant.py` carries three: `claude-sonnet-5`,
`claude-opus-5`, `claude-haiku-4-5`. Confirm each is current, and check
whether any prompt assumes an older model's behaviour -- output-length
habits, tool-use style, or instructions written around a limitation that no
longer exists.

**8.2 The tool library against what the program has become.**
**73 tools.** Each gets *correct*, *stale*, or *missing*.

**None of them has ever run.** Measured 2026-09-23 across the agent's entire
recorded history: 27 runs, `tool_call_count` **zero in every one**. Every
attempt since 2026-08-28 failed at the first API call, and the one entry that
was not a failure was a run stopped before it did anything.

That changes what 8.2 is. It is not "check the tools still fit a system that
moved" — it is **their first execution in production**, on a library written
against an architecture that has since been rebuilt underneath it. Every
"correct" verdict in the review is a prediction, not an observation, and
should be written as one. The first real agent run is a measurement, and
8.4's "observe one real run" is the only evidence any of this ever produces.

The known-stale shape is already visible. `list_golden_configs` was one of
the seventeen legacy-enumerator callers found in Stage 3.3; it is correct now
only because the enumerator underneath it was fixed. The read-first
instructions -- check golden configs and variables before opening a session
-- predate committed intent entirely. **An agent told to read goldens and
variables, in a system where `host_vars` is the source of truth, is
reasoning from the wrong artifact**: a golden is what the device *was* at the
last capture, and intent is what it is *supposed to be*. Those differ exactly
when it matters.

Missing tools worth considering: **read committed intent**, **read a deploy
plan** (the program, the attribution split, the blocking reasons), **read
drift coverage** (`checked N of M` and who was skipped), and **read the
integrations' data** (Prometheus, Loki, Kea) so the agent can answer from
measurement rather than from a config file.

**8.3 Authority, stated positively -- and there is currently no place to
state it.**

Measured: `execute_tool()` dispatches on the tool name directly. **There is
no pre-execution gate.** `request_approval` is a tool the model *chooses* to
call, not an interception, so the agent's authority is bounded by prompt
instruction and by nothing in code. "The AI assistant must never be able to
mint identities" holds because `resolve_identity(allow_new=False)` enforces
it *at the identity layer* -- not because anything checks what the agent is
allowed to do.

So 8.3 is a code change, not a documentation change: **a written allowlist
with an enforcement point**, so a new tool does not inherit permission by
being added. The position, to be encoded: **no credential rotation, no
template approval, no remote push, no baseline re-apply, no deploy apply.**
Read and propose; destructive actions go through the approval queue as today.
A tool not on the allowlist is refused, and adding one is a deliberate edit
to the list rather than a side effect of writing a handler.

**Two findings that may not wait for Stage 8** -- both measured while writing
this, both pre-dating the NSoT work:

* **`restore_golden_config` is a fourth config-push path.** It opens a
  session, enters config mode and replays the whole golden line by line, with
  **no confirm hash, no `assert_merge_only`, no `assert_sendable`, no
  dangerous-line authorisation, no pre-change snapshot, no rollback and no
  circuit breaker** -- and it accepts `device_ips: ["all"]`, so one call
  targets the fleet. This is the exact shape removed from the approval
  queue's `revert_to_golden`, which now hands off to the confirmed restore
  path. The AI's copy was not part of that correction. Either it hands off
  the same way, or it goes.
* **`detect_config_drift` is a third drift implementation**, after
  `drift_check.run_drift_check` and the `agent_runner._run_drift_check`
  deleted in Stage 3.3. It carries the pre-3.3b shape: no inventory
  accounting, no named skips.

`restore_pre_change_snapshot`, `execute_commands_on_device` and
`execute_command_on_multiple_devices` need the same read before 8.3 is
designed, for the same reason.

**8.4 Re-enabling the background agent.** It has been **disabled throughout
the NSoT work**, which makes its paths the least exercised code in the
program -- `agent_runner.py` is 1,363 lines that nothing has run while five
stages changed the things it calls. Stage 3.3 already found one consequence:
a 172-line duplicate drift checker inside it, superseded and never removed.

Treat re-enabling exactly like re-enabling drift, and in that order: **fix
what it does first, enable deliberately second, observe one real run third.**
Re-enabling before 8.2 and 8.3 would put the least-tested component in the
program back on the network with the stale tool library and no authority
gate. Enabling it is the last act of the stage, not the first.

**8.5 The prompt examples.** They reference another project's PE/P/MPLS
topology -- Section 3 finding #11, deferred from Phase 0 and still open.
`PE-1`, `P1`, `P4`, MPLS TE and LDP appear throughout
`ai_assistant.py`'s instructions, variable examples, Jenkins stage templates
and knowledge-base guidance. Make them generic, or match this lab (r1-r5,
s1-s4, OSPF/BGP/RIP/DMVPN). An example is an instruction: examples naming a
topology that does not exist teach the agent to look for devices that are
not there.

*Acceptance:* every one of the 73 tools is classified with a reason; the
allowlist exists **in code** with a test that an unlisted tool is refused;
no tool reaches a device outside the confirmed deploy path; the prompt
examples name only devices in this lab; and the background agent is enabled
**last**, with one real run observed and reported -- the same bar drift
had to clear.
