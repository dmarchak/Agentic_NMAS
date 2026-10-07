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
   **TRUE as of 2026-09-28, measured, after being stated and FALSE since Phase 0**
   (D8, recorded 2026-09-26; closed by C123). Until then four libraries loaded from
   public CDNs, xterm and socket.io UNPINNED, while this line stated the property:
   an assumption, checked only for CodeMirror. They are vendored from
   registry-verified tarballs (`static/js/vendor/MANIFEST.json`); the host serves
   each at its manifest size; the served page carries no CDN reference and a CSP
   that admits no host; and in the operator's browser `typeof vis` is "object" and
   `typeof Sortable` is "function". `test_csp.py` holds it for every template.
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
Actor: <user>               # or ai-agent
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
  - The NMAS host (Ubuntu 24.04) is `<nmas-host>` on the LAN, `10.255.0.10` on
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
read-only checks green against `<repo>`;
`repository_is_empty_or_related` reported *"53 shared commit(s) on this list's
history"*. The gated write probe passed at 17:21:54Z.
The reported hypothesis — peeled `refs/tags/x^{}` entries inflating the count —
was wrong. The count was a symptom. The check intersected the local **root
commit** with the remote's **ref tips**, which coincide only in a repository
with exactly one commit, so it passed on an empty remote and refused every
remote with history. It now tests ancestry over every advertised SHA this
clone holds.
*Acceptance:* Verify (read-only) passes against `<repo>`
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
| **5** — per-device monitoring | — | — | — | **FOLDED INTO 7.3 — DECIDED 2026-09-25, RENUMBERED 2026-09-27** (was "7.5"; NSOT_STAGE7_PLAN.md governs, and there monitoring is the Device page). Its six remaining items are 7.3's acceptance; switch syslog is carved out as **P.1** |
| **Before 7** — standalone | **2** (P.1, P.2) | 2 | 0 | P.1 switch syslog (a pipeline defect); P.2 NetBox backup (A1) |
| **6** — security | **5** (6.1–6.5) | 4 | 1 | infrastructure and device-side; touches no GUI. 6.5 added 2026-09-25 (C5) |
| **7** — the interface | **11** (7.0–7.9, incl. 7.2b) | 8 | 2 | **7.2b is DONE** — §0b's script extraction and §6c's cache headers both landed |
| **8** — AI and agent | **6** (8.0–8.5) | 4 | 2 | plus three named sub-findings inside 8.2/8.3 |
| **9** — hardening and cleanup | **9 (L) + 15 (M) register rows**, plus Stage 6's items (2026-09-28 re-triage), each entering by decision | — | — | **ADDED 2026-09-28 (the operator).** (L) is SAFE HERE BECAUSE IT IS A LAB and would come FIRST on a real network; (M) is minor anywhere. The functional path (R1, R2b, 7.2, 7.3, then 7.4 onward) is the plan; Stage 9 comes after it unless a trigger makes (L) urgent |

**⚠ Stage 5's seven was a different kind of number from the others**, and
the fold resolves it: the paragraph is now enumerated as 7.3's acceptance,
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
- **Grafana `allow_embedding` + an Access policy for the embed path → 7.3 →
  7.9.** Named blockers, not measured ones; the iframe test comes first.
- **P.1 and P.2 are scheduled ahead of Stage 7 by the operator's DECISION,
  not by dependency.**
  Nothing in Stage 7 needs them. P.1 is a defect in a running pipeline, and
  every day it waits is a day of switch logs that do not exist. P.2 is what
  makes the Stage 7 work recoverable if it damages NetBox. It is the one
  store NMAS writes to that has no restore path.
- Stage 6 blocks nothing and is blocked by nothing. **DECIDED 2026-09-27
  (the operator): Stage 6 does NOT close before Stage 7.** NSOT_STAGE7_GUI.md's
  "Nothing here starts before Stage 6 closes" predates P.3. It was written
  when the GUI stage would have re-homed ungated controls, and P.3 did that
  work, so Stage 7's screens are built against gates already enforced. The
  GUI doc now says so. Two conditions:
  - **6.1 is fixed on its own schedule**, independent of any stage. Docker
    publishing past ufw lets oxidized-web serve every device's running
    config to the LAN, which is a live exposure.
  - **6.2's per-consumer accounts come before Stage 8's agent work**, not
    before Stage 7.
- **Before 7.0 (the operator's decision, 2026-09-26): C1 alone, CLEARED 2026-09-26** (not reproduced in one controlled run; see the register)
  (`nmas-deploy` unconfirmed, one measurement). P.2 is done except its
  unattended watch. Every Stage 7 step is verified on the host, so a deploy
  that can report "already current" while behind would make each of those
  verifications suspect. **Gates on later steps**, proposed 2026-09-25 by
  the triage *which findings would make Stage 7's work untrustworthy or
  wasted*, and not yet confirmed: B3 before 7.1; C17 before 7.2; B1 and C2
  before 7.3; C10 before whichever step first makes a batch deploy a
  multi-select; C8 before 7.5's NetBox summary; E4 before 7.6; C7 before
  7.7. The other open findings are carried into Stage 7 with conditions
  (register).
- **The gate list, REVISED 2026-09-27 after P.6, and CONFIRMED by the
  operator the same day with two changes** (applied below: C53's hourly
  check before 7.2, and C50's fix as the map's `kind:` entry). Each gate is tied to the step whose screen
  would be wrong without it, read against NSOT_STAGE7_PLAN.md's steps and
  section 1a's sources:
  - **Both decisions are taken (2026-09-27).** Stage 6 does not close
    first (above). **NSOT_STAGE7_PLAN.md's numbering holds**, by its own
    first line: 7.5 is Versions and monitoring is the Device page, 7.3.
    Stage 5's six items move to 7.3 as 7.3-a…f, and 7.3-f is already done
    (P.1).
  - **Before 7.0: B1.** 7.0 writes the payload-to-render check, which
    requires every payload key to be drawn or allowlisted. `skipped_drifted`
    still carries a whole device config, so it would enter that allowlist on
    day one. Small to fix; fix it first. **C51** (a GET creating the list it
    names) belongs IN 7.0's harness, beside C33.
  - **Before 7.1: C8** (moved from "7.5's NetBox summary"). 7.1 retrofits
    NetBox import and remove into the preview-confirm component, and the
    import reports `failed=0` while 20 write paths log failures at DEBUG, so
    the component would present a false count.
  - **Before 7.2: C17, E4 (moved from 7.6), C54, and C53's check
    RUNNING** (the operator's change). Needs attention's sources include:
    - Grafana's alert state (C17: `grafana_url` and `loki_url` are empty);
    - drift with coverage (E4: the checker is off, so the source reads
      "disabled");
    - job health, which carries rows for devices that no longer exist
      (C54), and the startup-credential row. If `nmas-startup-check` reads
      `not_installed` when 7.2 draws the page, the landing view shows a
      check that is not running: C14's shape, the row's reason for
      existing. The same argument as C54's.
    - **and 7.1's two real runs, R1 (onboarding on a throwaway) and R2 (the
      NetBox window)** (the operator, 2026-09-28; NSOT_STAGE7_PLAN "7.1's
      stated limit"). Only restore has been clicked on the host since its
      retrofit, and 7.2 reads the stores these operations write, so a defect
      in a writer would surface as a wrong row in 7.2's reader.
  - **Before 7.3: C50, fixed as the map's `kind:` entry, not a narrower
    patch** (the operator's strengthening). The Device page offers Rotate
    as a button, so the wrong-lab write becomes a ONE-CLICK action rather
    than something only a CLI user reaches. And there are now two
    persistence kinds, `clab` and `native` (C53), and the map answers only
    the first. An unknown lab must be refused, and a non-containerlab device
    must be a declared `kind: native` whose persistence is the device's own
    save.
  - **Before 7.4: C10**, unchanged: 7.4's batch deploy is the first
    multi-select.
  - **Within 7.6, not before 7.3: C2** (the register already schedules it
    there: "fixed as it moves", with fleet coverage). **B3 moves to 7.6**
    too, where credentials are shown and the orphan action lives. Nothing
    in 7.1 depends on it. The live case is P.6's own `10.255.0.50` orphan,
    which the tool correctly refused to delete.
  - **Before 7.7: C7**, unchanged.

**The overlap worth knowing: Stage 5 and Stage 7.3 are the same screens** (renumbered 2026-09-27 from "7.5").
Stage 5's per-device Prometheus / Loki / Oxidized / lease views and Stage 7.3's
Monitoring destination are one surface. Doing 5 before 7 means building it
twice — which is the argument the plan already makes for putting Stage 8 last,
and does not make here.

**DECIDED 2026-09-25: Stage 5 folds into 7.3** (was "7.5"; renumbered 2026-09-27). The views are built once,
inside the redesigned interface, rather than built into the current UI and
rebuilt by Stage 7. Enumerating Stage 5 becomes 7.3's acceptance criteria;
see *Stage 5*, below. **The exception is switch syslog**, which is not a
screen. Logs that stopped arriving on 2026-09-09 are a defect in a pipeline
that runs whether or not anyone looks at it, and folding it into a UI stage
would schedule a repair behind a redesign. It is **P.1**, before Stage 7.

---

### STAGE 5 — Phase 5: per-device monitoring — FOLDED INTO 7.3 (decided 2026-09-25; renumbered from 7.5 on 2026-09-27)

**No longer a stage.** Building these views before Stage 7 builds them twice,
because 7.3's Monitoring tab on the Device page is the same surface. The acceptance
paragraph below is kept as written, since it is the source. Its enumeration
is **7.3's acceptance criteria**:

| # | 7.3 acceptance item (from Stage 5) |
|---|---|
| 7.3-a | A device page shows **its own** Prometheus series |
| 7.3-b | ... its own Loki lines. Switch lines must be flowing first, which is **P.1** (done 2026-09-25) |
| 7.3-c | ... its own Oxidized fetch history |
| 7.3-d | ... its own Kea leases |
| 7.3-e | The legacy SNMP/NetFlow collector is **retired**, not collapsed |
| 7.3-f | `logging trap` level set deliberately and **recorded in intent**, through the deploy path, not configured by hand. **DONE by P.1 (2026-09-25)**: `notifications` in the syslog block, in intent, deployed through the deploy path. Carried as done, not pending |

Carved out: **switch syslog restored** is **P.1**, below. Stage 5's derived
count was seven, and this is six plus P.1, so the enumeration agrees with the
reading. If P.1 finds that restoring syslog needs a logging change on the
switches, that change is 7.3-f made early, through intent. It is not a
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

**6.1 Docker publishes past ufw. STILL LIVE, re-measured 2026-09-28 from
the laptop (C143):** TCP 8888, 8000, 3100 and 9116 answer from another LAN
host, and oxidized-web's `/nodes.json` answers 200 with no credential. "On
its own schedule" had no date. **DEFERRED to Stage 9's (L) half the same
night (the operator: a lab, no hostile LAN)**, and COUPLED with the community
rotation: a rotation made first would serve the new value on the LAN the day
it lands.
Measured on the deployment host: NetBox
`:8000`, Loki `:3100` and oxidized-web `:8888` are reachable from the whole
LAN despite ufw's default deny, because Docker's rules in `DOCKER`/`DOCKER-USER`
are evaluated ahead of ufw's chains. **oxidized-web serves every device's full
running configuration** and is the largest of the three by a wide margin. It
surfaced only by contrast: Grafana runs as a native process and *was* blocked.
*Acceptance:* the three ports are unreachable from another LAN host — verified
**from another host**, not by reading a rule table, which is the presence-check
mistake again. Bind to `127.0.0.1` or add `DOCKER-USER` rules.

**6.2 Per-consumer accounts: Stage 6's FIRST item** (operator's decision,
2026-09-25). One `admin` credential is shared by NMAS, Oxidized and the
operator. A leak of it compromises everything, a rotation moves the floor
under all three at once, and **no log anywhere can tell which of the three
did something**. Separate accounts with separate passwords give most of what
SSH keys would, namely attribution and revoking one consumer, without a key
mode through every credential path and without 6.2b's SHA-1 question.
**A dependency 6.2 inherits (the operator, 2026-09-27):** every reader of a
device's `username` lines must match the account as a WHOLE WORD, because
6.2 is exactly the change that puts a second account with a shared prefix
on a device (`admin`, `admin-oxidized`). The rotation's live read matched a
prefix until C69 (`credential_rotation.users_line`), latent only because
every device held one account. Before 6.2 lands, sweep every other reader
of `username` lines for the same shape. `onboard.startup_carries` compares
whole lines and is already safe.

**6.2b SSH keys for device access, behind 6.2** (option C of the
2026-09-25 design review). With keys, a stolen credential store yields no
device passwords, goldens carry only public keys, and the device password
can live only in the break-glass record, since the console still needs one.
They do NOT protect against theft of the disk: the private key on it becomes
the most valuable file there. Costs: a key mode through rotation, the
persistence chain, the startup-file check, the deploy credential guard,
retire's break-glass check and onboarding phase 2; `transport input` without
telnet (the fixtures show `all` / `telnet ssh`); and a measurement first,
because vIOS may accept only SHA-1 `ssh-rsa` signatures, which current
paramiko and OpenSSH turn off by default.

**Declined: keeping the Fernet key off the disk** (a passphrase or a TPM
seal at service start). NMAS works unattended, so the key must be readable
with nobody present. The option costs a person at every reboot and buys
nothing this deployment can use. Recorded so it is not re-proposed without
new facts (CLAUDE.md, *Encryption at rest here protects COPIES THAT
TRAVEL*).

**6.3 The `yang-push-sub` credential: RETIRE THE SCRIPT** (decided
2026-09-26, register C31). It has not worked since 2026-09-22: its credential
is the vrnetlab factory default that every router refuses. Nothing runs it,
it is in no repository, and its mode is `0664`. **Operator's steps on the NMAS
host:** remove `~/lab-configs/yang-push-sub.py`, then run
`scripts/nmas-setting-not-applicable yang_push_script --reason "yang-push-sub.py
retired 2026-09-26 (C31): dead since the redeploy, nothing ran it"`. Job health
then reads `not_applicable` with who and when, and the rotation stops listing
it as a consumer. If a yang-push consumer ever returns, its check needs the
third state recorded in `_yang_push_consumer`'s docstring. And **6.4 enable secret vs console
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
that change goes through intent (7.3-f, done by P.1), not a hand edit. And the loss gets a
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

**P.1 COMPLETE 2026-09-25: acceptance passed end to end (operator).**
- **The silenced device alerted, alone, at the right time.** s4's last
  heartbeat was 21:21:22; its timer was removed at 21:22:27 (applet kept, `no
  event timer watchdog time 300`); the **alert fired at 21:40:00**. The other
  eight were silent throughout.
- 1,118 s after the last heartbeat is past s4's second missed heartbeat
  (≈2 × 400 s real) and before its third (≈3 × 388 s): **"alert after two
  missed", measured.**
- Its window (996 s) elapsed at 21:37:58, so detection took **122 s
  beyond the window**. That fits Grafana's 1-minute evaluation plus NoData
  handling, but it is **not measured**. The latency is window + about 2
  min until someone shows otherwise.
- s4's own syslog recorded the cause on the way out: `21:22:35
  %HA_EM-4-FMPD_NO_EVENT: No event configured for applet NMAS-HEARTBEAT`.
- Nine rules loaded in Grafana with per-device measured windows (750 × 5,
  797, 799, 996, 1286). `nmas-heartbeat-check` reads current for all nine
  and is a healthy job in `nmas-jobs`. s4's timer was restored at 22:04:32.
- **What P.1 delivered:** the block authored as intent; bulk-applied to
  seven devices in one commit (`7fd0ac0`); deployed to all ten; nine
  heartbeating (r5 retired as out of scope); the collector proven; rules
  generated from committed intent with each device's window measured from
  its own clock; and an alert that fires when a device stops, and only
  then.
- **Built on the way:** bulk intent (P.1b), retire (C11), declared-unmapped,
  job health (C14), the clab-sync fixes (C14/C15), and per-device windows
  (C16).

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
   7.2 (Needs attention) and 7.3 (the Device page) and does not run the check itself.
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

   **With P.1b: s1, s2, s3, r1, r3, r4, r5 in ONE intent commit, then one
   batch deploy of six.**
   1. `scripts/nmas-bulk-intent --list Default --devices
      s1,s2,s3,r1,r3,r4,r5 --change deploy/intent-changes/p1-syslog-block.json`
      must read **"7 device(s), 1 group(s)"**. Anything else, stop.
   2. `--apply <hash> --actor <you>` gives one commit.
   3. Batch-deploy s1, s2, r1, r3, r4, r5. Every device's preview is the same
      five-line program. s3 follows on its own; its intent is committed now,
      so until it is deployed s3 shows intent ahead of device, which is
      expected.
   4. **r6 through the editor.** Its file is hand-formatted and its logging
      is empty, so the bulk change correctly refuses it.

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
   - **Arrivals 18:15:12 → 18:21:43, 391 s apart.** First read as 91 s of
     delivery jitter, which moved the window from 2I + 60 = 660 s to
     2.5 × 300 = 750 s. **That reason was wrong.** At the operator's
     request it was re-measured over five intervals:
     - s4's own clock put every heartbeat **300.0 s** apart (299.87 to
       300.14), and Loki received them **391, 401, 398, 404 and 402.5 s**
       apart.
     - So the vIOS **clock runs at about 75% speed**, which also explains
       it reading ~16 h behind. The watchdog is exact in device time. It is
       a fact about the platform's clock, not about the network.
     - A single 750 s window would have alerted on ONE missed s4 heartbeat
       (a real gap of about 800 s).
     - **The window is now per dialect:** 2.5 × the platform's measured
       real interval. vIOS gets 999 s and IOS-XE 750 s (`HEARTBEAT_RATE`
       in `nmas-heartbeat-rules`, each entry carrying its measurement). An
       unmeasured dialect is refused.
     - The dialect comes from the NSoT manifest, not NetBox, which records
       all ten devices as `ios` (OPEN_FINDINGS A4).

   **r2 DONE 2026-09-25 (operator):**
   - Arrivals 18:40:20, 18:45:20, 18:50:20: 300.1 and 300.0 s apart. The
     device clock is one second behind arrival, consistently, so the C8000v
     clock is correct.
   - Loki returns all three through the anchored query.
   - Golden `7115632`, tagged `golden/r2/20260925T183535Z`, with the applet
     at lines 316-318, byte-identical.
   - `%SYS-5-CONFIG_I` arrived, so `notifications` took effect on IOS-XE
     too.
   - The device clock reads 02:02 while the wall clock read 18:15, so **the
     device's own timestamps cannot be used for arrival**. What the rule
     counts is Loki's timestamp.
5. **Operator:** generate the rules with the Loki datasource UID, install
   them into `/etc/grafana/provisioning/alerting/`, and reload Grafana.
   **Per-device windows BUILT 2026-09-25; step 5 is unblocked.** Live
   generation from Loki gave nine measured windows (r1–r4 and r6 750 s, s1
   797, s2 799, s3 1286, s4 996) and `--check` read current for all nine.
   To install:
   ```
   scripts/nmas-heartbeat-rules --datasource-uid <loki-uid> --loki-url http://127.0.0.1:3100
   sudo install -m 0644 deploy/grafana/provisioning/alerting/nmas-heartbeat.yaml /etc/grafana/provisioning/alerting/
   d=$(mktemp -d) && scripts/nmas-render-units --out "$d" deploy/systemd/nmas-heartbeat-check.service deploy/systemd/nmas-heartbeat-check.timer && sudo install -m 0644 "$d/nmas-heartbeat-check.service" "$d/nmas-heartbeat-check.timer" /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now nmas-heartbeat-check.timer
   ```
   Then reload Grafana's provisioning.

   **The original design, kept as the specification (it was blocked on
   C16):** The acceptance
   measurement (step 6) was run early, and it failed three of four switches
   against the per-platform window. The design, to be built before any rule
   is installed:
   - **The measurement comes from Loki**, through the same anchored query
     the rule uses. It takes the device's last N hours of arrivals and their
     consecutive gaps, excluding gaps over 1.8 × the median, so a real miss
     in the history does not widen the window that should catch the next
     one.
   - **Window = the midpoint of the device's own separable band,
     (2 × longest + 3 × shortest) / 2**, so it is quiet on one miss and
     fires on two. If the band is empty (2 × longest ≥ 3 × shortest), the
     device is reported **`inseparable`**, with its numbers, never given a
     window that merely looks correct.
   - **A device with too few arrivals** (fewer than 6 gaps; a new device,
     or a slow clock early on) gets a **provisional** window: 2.5 × the
     interval divided by the slowest rate measured anywhere in the fleet
     (s3's 0.55 gives ~1,364 s). It alerts on a dead device within ~23
     minutes, and the rule carries `window_basis: provisional` as a label
     and in its annotation. The generator lists every provisional device;
     it is never silently omitted.
   - **Rates move** (s3 varies by 10%), so `--check` re-measures and flags a
     device whose current band no longer contains its installed window.
     Declared in `job_health` as a job, so the check itself cannot stop
     quietly.
   - `HEARTBEAT_RATE` (per dialect) retires.

6. **Acceptance:**
   - Heartbeats from all **nine** devices in Loki. **r5 is out of scope,
     the operator's decision, 2026-09-25.** r5 is the eBGP PE in AS 65002,
     an ISP device outside the administrative boundary. It has no route to
     `10.255.1.10`, which is reachable only inside AS 65001, and has
     delivered nothing since logging started on 2026-09-22. The block
     deployed correctly (the applet is on the device and in `golden/r5.cfg`);
     the device cannot reach the collector by design. It leaves the Default
     list; console and containerlab access remain.
   - One deliberately silenced device alerting.
   - **STEP 4 COMPLETE 2026-09-25 (operator): nine of nine managed
     devices heartbeating**, counted from Loki over 20 minutes on each
     device's own origin-id: r1 4, r2 4, r3 4, r4 4, s1 4, s2 4, s4 3
     (the slow clock), s3 1 and r6 1 (both deployed minutes before).
     Deployed: s4 and r2 alone; s1, s2, r1, r3, r4 and r5 as one batch
     (golden `01d45b7`, six tags); s3 alone (`77a19c1`); r6 (`96b4352`).
     Intent for seven came from ONE bulk-intent commit (`7fd0ac0`) with the
     operation in its trailer. r5 is absent, correctly: no route to the
     collector, and it is being retired.
     r6's first heartbeat showed rsyslog naming it by address (C13). The
     rules key on origin-id and are pinned against both line shapes.
   - **Status 2026-09-25 (earlier):** eight of nine deployed (s4 and r2 alone, then
     s1, s2, r1, r3, r4 and r5 as batch golden `01d45b7`); seven
     heartbeating; s3 and r6 remain. **Leaving r5 is not the delete
     button**: that leaves r5 bound, mapped, alerting and half-present
     (OPEN_FINDINGS C11), and destroys the only copy of its credential.

   **r5's exit** (decided 2026-09-25: retire, not delete; NetBox device 9
   KEPT, since NetBox records what exists; heartbeat rules follow committed
   intent):
   1. Take the heartbeat block off by hand (C12), then save r5's golden.
      `nmas-retire`'s plan flags the applet until then.
   2. One clab sync **while r5 is still mapped**, so the frozen `r5.cfg`
      is the clean one.
      *Run 2026-09-25, and it found C14: `clab-sync.service` had failed 72
      runs in a row (helper not on systemd's PATH), and the r6 commit was
      reported as NOT VERSIONED when it lacked a git identity. Both fixed
      in `scripts/oxidized-to-config.sh`. **Deploy it as a symlink**, then
      re-run this step:*
      ```
      cd ~/lab-configs && mv oxidized-to-config.sh oxidized-to-config.sh.bak-2026-09-25
      ln -s ~/python/Agentic_NMAS/scripts/oxidized-to-config.sh oxidized-to-config.sh
      sudo systemctl start clab-sync.service; ~/python/Agentic_NMAS/scripts/nmas-jobs
      ```
   3. `scripts/nmas-breakglass export --list Default --out <file>` and
      `verify`.
   4. `scripts/nmas-retire --list Default --device r5 --reason "..."`, read
      its steps and its NOT-doing list, then `--apply <hash> --actor <you>
      --breakglass <file>`.
      **Live plan, 2026-09-25:** declare `labs/lab/configs/r5.cfg`; one
      commit removing `host_vars/r5.yml` and `golden/r5.cfg` and releasing
      its identity; withdraw `cisco_iosxe/base.j2` (re-approve against r1,
      r2, r3, r4, r6); then the row.
   5. Re-approve `cisco_iosxe/base.j2`.

   **r5 RETIRED 2026-09-25 (operator), and C11's acceptance passed:**
   - The plan read correctly, including the NOT-doing list.
   - Applied with the break-glass check: commit `3592113`; zero r5 in
     host_vars, golden, devices.csv and the manifest.
   - The approval was withdrawn naming its cause ("device 'r5' is no longer
     bound"); `cisco_iosxe/base.j2` binds r1–r4 and r6.
   - `--reconcile` on its first real use: `produced : 9`, `declared : 1`
     with who and when.
   - Freshness gate 9 of 9.
   - The break-glass record is on the operator's laptop (ten devices, r5
     included) and removed from the NMAS, hashes compared.
   - **Step 5 (Grafana rules) is unblocked:** r5's intent is gone, so the
     rule population is the nine.
   - **Every device's REAL interval measured:** over at least an hour of
     heartbeats, the shortest and longest inter-arrival gap per device. For
     its dialect's window W, **2 × longest < W < 3 × shortest**, or the
     window no longer separates one missed heartbeat from two. The vIOS
     rate is from s4 alone; s1–s3 may not run at the same speed, since an
     emulated clock's slowdown can depend on host load. A switch outside
     the band gets the band re-measured, not a guessed constant.

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

**P.1b BULK INTENT: one structured change to N devices' intent, as one
commit. BUILT 2026-09-25** (`modules/nsot/bulk_intent.py`,
`POST /templatize/bulk/preview` and `/apply`, `scripts/nmas-bulk-intent`, the
P.1 change committed as `deploy/intent-changes/p1-syslog-block.json`).
**Previewed live, read-only, against the real `default` repo:
"7 device(s), 1 group(s), 1 refused"**:
- The group is s1, s2, s3, r1, r3, r4, r5, and it renders
  `+ logging trap notifications`, `+` the applet and its two children, and
  `- logging trap critical`: exactly the program s4 and r2 received.
- **r6 refused, with every reason:** its file is hand-formatted (the branch
  site was hand-authored), and its intent is not what the change expects
  (`logging.settings` expected the three lines, has `[]`; `logging.hosts`
  expected `[10.255.1.10]`, has `[]`).
- The first version stopped at the formatting reason and never reported the
  before-state. It now reports every reason at once, pinned by a test.
- 17 tests, with a control shown failing for each refusal, the grouping, the
  one-shot hash, the dirty-tree guard and not creating a mistyped list.
- One commit; revert of one device from the shared commit leaves the others
  (pinned).

*Original scope, kept below as the specification the build was held to.* Batch *deploy* exists: `/deploy/plan`
takes `devices`, and `plan_batch`/`run_batch` account for every device. Batch
*intent* does not. So the same edit is typed into N host_vars files, as N
commits, with nothing but a render diff that "looks wrong on one device" to
catch a divergence. That is N chances to paste it differently.

*The operation* is a list of **compare-and-set steps over schema paths**,
never text: `(path, expected_before, after)`. It reuses the path walk that
"Revert intent" already uses (`hostvars._walk` / `_set_path`: named list
items keyed by name). For the P.1 move:

| path | expected before | after |
|---|---|---|
| `logging.settings` | `[trap critical, origin-id hostname, source-interface Loopback0]` | `[]` |
| `logging.hosts` | `[10.255.1.10]` | `[]` |
| `logging.syslog` | *absent* | the block |

A key the operation does not name is not touched, so `console` on the
switches and its absence on r2 are simply irrelevant. That is what "does not
apply" means structurally: a path the change is about, holding something
other than what the change expects.

*Refused, per device, with both operands named, never applied around:*
- **Before-state mismatch.** The interesting case. If s1's `settings` has
  drifted from the others', the same edit applied blindly makes s1
  different in a way nobody notices. It is refused with
  `logging.settings: expected [...], s1 has [...]`, and the operator decides.
- **An after-state a gate refuses**: `syslog_block_problems`, unknown
  interface keys, `assert_printable`, `assert_no_secret_values`, and **the
  render failing** against the device's bound template.
- **A path the schema does not know.** A typo in the operation is refused
  before any device is read.
- **A file that would be reformatted.** The write goes through `to_yaml`, so
  a hand-edited file carrying comments or its own layout would lose them
  silently. Refused if `to_yaml(from_yaml(current)) != current`, and named.
- **Stale or pending** devices, as everywhere else.

*Preview, then one-shot apply* (the Phase 0 token shape):
- The preview shows, per device, the intent diff and the **render delta**
  (lines the intended config gains and loses). It **groups devices whose
  render delta is identical**. The P.1 move should produce one group; a
  second group is a divergence made structural rather than spotted.
- Apply takes a hash over `(device, the file's blob at preview, the
  resulting text)` for every accepted device, and re-checks it. A file that
  moved since the preview refuses the whole apply, because the preview is
  what was confirmed.
- **One commit**, `host_vars: <operation> (N devices)`, with
  `Devices:` and `Operation:` trailers, and `Refused:` naming the rest.
  Per-device revert still works (see the CLAUDE.md correction beside "one
  device → one intent commit").

*Acceptance:*
- The P.1 move applied to s1, s2, r1, r3, r4, r5 and s3 as one commit, one
  render-delta group.
- r6 (logging empty) refused by the same operation with its before-state
  named. It gets the block through the editor.
- A planted drift on one device refused, with the rest still committable.

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

**WHAT HAS A COPY, measured 2026-09-25** (what P.2 covers, and what it
does not):

| Store | Copy today | After P.2 |
|---|---|---|
| NetBox (DB, media, env) | none | hourly on the VM, Proxmox, daily off-box (B2) |
| `config_repo` (goldens, intent, templates) | GitHub `<repo>` via the post-commit push, **one commit behind** (r5's retire, C18) | unchanged |
| `data/key.key` | **none: single copy, confirmed** (no vzdump job exists, B5) | **none** |
| `credential_profiles.json`, `devices.csv` | device credentials only, in the break-glass record on the laptop | unchanged |
| `user_settings.json` | `.bak-*` copies on the same disk | unchanged |
| the rest of `data/` (drift, approvals, AI history) | none | none |
| `/etc/kea` (config, API password) | none | none |
| clab host `~/labs/*` | local git, **no remote** for any of the eight; `labs/r6/r6.clab.yml` and `patches/` are **untracked** | none |
| Oxidized `rcn-lab.git` | unknown (needs sudo to read its remote) | unchanged |
| Grafana (`/var/lib/grafana`) | none; the heartbeat rules are regenerable from the repo | none |
| NMAS code | GitHub | GitHub |

**The vzdump question decides most of the "none" rows.** `/etc/pve/jobs.cfg`
holds `vzdump:` jobs. Each names a `schedule`, the VMs it covers (a `vmid`
list, or `all 1` with an `exclude`, or a `pool`), a `storage`, a `mode`
(snapshot / suspend / stop) and its retention.
- **If the NMAS VM is in an enabled job to storage off the VM's own disk**,
  every VM-local store above has a nightly whole-VM image. P.2 is still
  needed for what an image does not give: an **hour** rather than a day of
  loss, a **consistent** database dump rather than a crash-consistent disk,
  a restore of NetBox **alone** without rolling back `config_repo` and
  everything else, a restore **proven nightly**, and an encrypted copy
  **off the Proxmox host**.
- **If it is in a job to the same host's local storage**, the image
  survives a broken VM and not a lost host.
- **If it is in no job**, key.key, the credential store, `/etc/kea` and
  Grafana are single copies. The whole-VM gap is then larger than A1 ever
  was.
- The clab host is a separate machine (`<lab-host>`); the same question
  applies to it separately.

**ANSWERED 2026-09-25 (operator): the third case, for both VMs.**
`/etc/pve/jobs.cfg` does not exist, so nothing images the NMAS VM or the clab
host. Every "none" row above is a single copy. Two consequences are recorded
in the register. **B5**: a copy of `key.key` alone restores nothing after a
disk loss, because the ciphertext it opens has no copy either. **B6**: whether
to image the VMs is a Proxmox-side decision, separate from P.2. P.2 reads
nothing encrypted with `key.key` (checked: neither backup script references
it), so the order between P.2 and B5 is one of priority, not dependency.
**Decided 2026-09-25: B5 and B6 are one fix, done before P.2's steps.** The key
is escrowed in the break-glass record and verified by decrypting real stored
values (`nmas-breakglass verify --live`, built; docs/SECRETS.md). The image
goes to a 150 G volume on `sda`'s empty thin pool, a separate physical disk
from `vmdata`, and to nowhere else. The runbook is
[VM_IMAGES.md](VM_IMAGES.md).

**P.2 ACCEPTANCE** (written 2026-09-25; the section had a build record
and no acceptance). Every item is observed, not inferred:
1. **The installed timer backs up on its own.** `nmas-jobs` shows
   `nmas-netbox-backup` ok, with a last success under an hour old, twice in
   a row.
2. **The installed restore test passes.** `nmas-netbox-restore-test` ok,
   and `nmas-netbox-backup --status` reads `restore test: PASS`.
3. **The Proxmox copy is write-only from the VM.** A `.tar.gpg` lands in
   `/srv/nmas-netbox/hourly/`, and from the VM a read or delete over the
   push key is refused (`rrsync -wo`).
4. **The off-box copy decrypts only where the key lives.** A daily in B2,
   fetched to the key-holder's machine, `gpg -d | tar -tf` lists
   `netbox.pgdump`, `manifest.json` and `config/env/netbox.env`. On the VM
   the same file is refused (`No secret key`).
5. **A failed destination is visible, not silent** (the C14 rule): with
   the Proxmox target deliberately broken, the unit fails and `nmas-jobs`
   names the cause (`SHIP TO PROXMOX FAILED: …`). Then restore it.
6. **`--status` exits 0** with every configured destination fresh.
7. **The vzdump question answered** from `/etc/pve/jobs.cfg`: is the NMAS
   VM itself in a scheduled backup?

**P.2 ACCEPTANCE STATUS, 2026-09-26** (from the operator's reports; items not
reported are marked pending, not inferred):
1. Timer backs up on its own, twice in a row: **PENDING**, the unattended
   watch after 05:00 UTC (next backup 03:01, restore test 04:30).
2. Installed restore test passes: **MET**. The unit ran PASS, 198 tables and
   3,143 rows identical, in 20 s.
3. Proxmox copy write-only: **half MET**. `.tar.gpg` files land (two
   hourlies, 363,799 and 363,796 bytes, under `/mnt/vzdump/nmas-netbox`,
   the `sda` volume, not `/srv`). The refusal half (a read or delete from
   the VM over the push key is refused, runbook 2d) is **not reported**.
4. Off-box copy decrypts only where the key lives: **MET**. Fetched with the
   read key, decrypted on the laptop, and the NMAS answers `No secret key`
   (runbook 6f).
5. A failed destination is visible: **MET** (step 8). `nmas-jobs` read
   `failing` with `SHIP TO PROXMOX FAILED: rsync exited 255: … Permission
   denied (publickey,password)`, the local backup was written before the
   ship failed, and it recovered to `ok`.
6. `--status` exits 0 with every destination fresh: **not reported**
   (`nmas-jobs` 9 of 9 ok is a different check). Confirm with the watch.
7. The vzdump question: **MET**. There were no jobs; `nmas-nightly` now
   images VMs 100 and 102 (B6).

**Open beside it, not part of the acceptance:** B9 (the write key can hide;
Object Lock after tomorrow's lifecycle measurement), B10 (the
lock/lifecycle check, built after the lock exists) and B8 (the decryption
key is on one laptop).

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

### P.3 — Every path that changes a device is guarded or gone (before 7.0)

**Decided 2026-09-26 (operator), after B12.** Of 19 mutating routes that
reach a device, one checked identity, and CLAUDE.md asserted they all did.
That assertion is why nobody checked. Stage 7 moves controls, and must not
re-home a control whose guard does not exist. So P.3 makes one statement
true, and makes it mechanical: **every route or socket event that can change
a device, a secret, or the tool's gates either requires a person, or is
removed.**

**Scope** (register rows): B12, B11, D5, D4, C23; the direct-push paths the
audit cut; the terminal's audit trail; and the agent's push, commit and
self-modification tools, which are a push path no person gate can cover.

**DO THIS FIRST (the operator, 2026-09-26): rotate the Anthropic key.** It
was acceptance item 11 and is not a final step. B11 means `GET /settings`
has returned the key in cleartext to anyone who could reach the route, and
that exposure has already happened. Until the key is rotated, the old one is
valid wherever it went. The window is **the route's whole life**: it has
returned `anthropic_api_key` since `e729267` (2026-04-12). It is not the time
P.3 takes. Nothing in P.3 retires it; only rotation does.
**DONE (operator, confirmed 2026-09-26).** Rotation supersedes a key, and does
not revoke the ones before it. Every key that sat in `.env` since 2026-04-12
went out through the route and stays valid at Anthropic until deleted. So the
earlier keys are revoked in the Console, in every workspace, keeping only the
one NMAS uses (register B17).

**Steps**

1. **One gate, declared per endpoint.** `modules/identity.py` gains a table
   classifying every mutating endpoint:
   - an **action**: `confirm` (changes a device), `approve`, `reveal`,
     `publish_remote`, `configure` (a new kind, for writes to the tool's own
     settings and gates), or `break_glass` (a new kind, for the terminal);
   - **`not_device`**, with a reason;
   - removed.

   One `before_request` hook enforces the table, before any input
   validation, the order `/onboard/create` already has. The SocketIO
   terminal enforces `break_glass` at `connect_terminal` and on each
   `terminal_input`. **A mutating endpoint missing from the table fails the
   suite.** No route can be added without declaring what it is.

   **BUILT 2026-09-26** (`modules/route_gates.py`, `tests/test_route_gates.py`).
   - **All 131 mutating endpoints and all three terminal events** are declared,
     each with a kind and a reason. The kinds are defined once at the top of
     the module.
   - **The table lives in its own module, not in `identity.py`**, which stays
     about identity. `identity.GATED_ACTIONS` gains `configure` and
     `break_glass`, each with `require_identity_for_*` and `require_person_for_*`
     defaulting ON (read through the defaults, not seeded).
   - **The hook is installed by `register_blueprints`**, outside its
     try-block: an app that starts without it serves every route ungated, and a
     crash is the better outcome.
   - **An undeclared endpoint is REFUSED at run time** (`outcome: unclassified`)
     as well as failing the suite.
   - **The test checks the population in both directions with floors** (131 and
     3), anchors, and the table against all 11 in-view `require()` calls, kind
     and operation both. It checks refusal before input on eight routes, that
     a person passes and a service does not, and the terminal refused and
     then opened. Six negative controls were shown firing.
   - **Ratify moved from `approve` to `configure`**, since it acts on a gate.
   - **The audit now records the VERIFIED actor.** Fourteen routes recorded
     `data.get("actor", "user")`, a name the client typed. The deploy's golden
     commit recorded `Actor: pipeline`, and Save All `actor="user"`. All now
     use `identity.request_actor()`. One named exemption: template seeding's
     `actor="nmas"`, which no person caused.
   - **The harness supplies a verified person by default**
     (`tests/conftest.py`). Tests about identity opt out with
     `@pytest.mark.real_identity`. 3781 passed, 0 failed, 0 errors.
   - **Consequences for the host.** `nmas-bulk-intent` POSTed to the app and
     would now be refused, so it runs in-process like `nmas-retire`. The
     `curl` that `nmas-oxidized-freshness` printed as a remedy was always
     refused from the host (register D9), and it now says what is needed.
     **The clab sync keeps working**: it reads `/clab/sync_targets` (a GET)
     and posts to `/freshness/gate` (`not_device`).
   - **Not yet measured: acceptance item 2's host half** (a `curl` from the
     host gets 403, a real deploy through the tunnel succeeds), and **the
     terminal through the tunnel**. Whether Access sends
     `Cf-Access-Jwt-Assertion` on the Socket.IO handshake is unmeasured. If it
     does not, a person is refused the terminal, and that shows up as a
     refusal, not an open shell.
   - **MEASURED ON THE HOST 2026-09-26 (operator), two of three.**
     1. **A local unauthenticated `POST /deploy/apply` answers 403**, naming
        the cause: *"the request carried no Cf-Access-Jwt-Assertion header"*,
        with `outcome: no_header`.
     2. **Through the tunnel, the verified actor is recorded on three paths.**
        A real deploy completed, so the gate passes a person:
        - `13e5408` host_vars (`Source: extraction`);
        - `b0a345e` template approve (`Source: template`);
        - `7a43784` the deploy's golden commit (`Source: pipeline`).

        All three read `Actor: <operator>`. The last said
        `Actor: pipeline` before.
     3. **The terminal through the tunnel: NOT REPORTED** (the report's line
        read `[result]`). It is still unmeasured.
2. **Cut the direct-push paths the audit cut** (docs/NSOT_FEATURE_AUDIT.md):
   - `/execute_command`;
   - `/run_script/<ip>` and the Scripts tab;
   - `/device/<ip>/restore_backup`;
   - `/bulk_execute` in config mode (enable mode stays, gated);
   - `/bulk_remove_static_routes`;
   - `/configure/apply`'s push: the forms stay, the Apply button is removed,
     and each form says *"being converted into intent authoring"* (decision
     2);
   - the legacy unguarded `/netbox/sync`, `/netbox/sync_all` and
     `/netbox/remove`;
   - `/ai/chat`'s `run_playbook_id` replay.

   **BUILT 2026-09-26.**
   - **Eight routes are removed**, and each answers 404 by path.
   - **Their UI is removed**: the Scripts tab, the restore-backup modal and
     its button, Remove Static Routes, the bulk Config Mode radio, and every
     playbook Run button (drawer and tab).
   - **Two cuts keep a route and REFUSE by name rather than degrade.** A stale
     page (the edge caches HTML) would otherwise get a quieter behaviour than
     it asked for:
     - `/bulk_execute` refuses `command_mode=config` with 400. Enable mode
       stays, needs a person, and can still copy, delete, reload and erase.
       That is recorded in its gate reason.
     - `/ai/chat` refuses `run_playbook_id` with 410, **never** passing it to
       the model as a message, because the model still holds
       `run_ansible_playbook` until step 8.
   - **Configure: the Apply button became "Check this form"**. It validates
     and shows the parameters the form collected, and sends nothing. A note
     heads the tab. The button was not deleted: it also drives the per-device
     steps, and `collectParams` and `_cfgValidate` are what the conversion to
     intent authoring (7.9) reuses.
   - **Removed with them, having no other caller**: `run_ansible_direct` and
     its YAML loader, the dead `playbook_confirm` card (nothing had emitted it
     since keyword matching was disabled), and `_sendRaw`, which the
     unreachable-UI test caught.
   - **Left for P.4, recorded there**: `pipeline_builder.ensure_function_pipeline`
     and `check_runner`'s `--config-id` mode, whose only producer was the
     configure push.
   - **No test had ever named any of the eight.** `tests/test_p3_cuts.py`
     names them to assert their absence. Four negative controls were shown
     firing.
   - **`check_removed_definitions.py` learned one rule**: a string counts as a
     use only when it is shaped like a reference (a name, a dotted path, or
     `pkg.mod:attr`). A path in a 404 test and a sentence in the model's
     prompt are not. Tested both ways, with a control.
   - **Also fixed, found while answering C25**: the harness imports `app`,
     which attached the app's file log handler in whatever checkout the suite
     ran in (C26, closed).
   - 3803 passed, 0 failed, 0 errors.
3. **D5.** The device page's and bulk ops' "Restore Golden Config" open the
   GUARDED restore preview for those devices at HEAD (the client function the
   approval handoff already uses). `/device/<ip>/restore_golden_config` and
   `/bulk_restore_golden_config` are removed.

   **BUILT 2026-09-26.**
   - **Both buttons open `previewBaselineRestore('HEAD', null, {devices})`**,
     the path the approval queue already hands off to. Bulk ops calls it
     directly. The device page links to `/?restore_head=<hostname>`, and the
     index page opens the preview from that. The parameter is removed BEFORE
     the preview opens, so a reload cannot re-open one nobody asked for.
   - **Both replay routes are removed (404).** The AI's own
     `restore_golden_config` TOOL, the same replay, is step 8's.
   - **Routing two buttons into that preview exposed its own defect.** Its
     confirm dialog showed counts and at most three replace and three residue
     lines, and never the lines to be ADDED. `commands` was computed, carried
     to the browser and drawn nowhere, while the confirm hash covered it.
     - `restorePreviewText()` is now a pure renderer of every line that will
       be sent, every replacement, every residue line, blocked devices with
       their reasons, and skips. It is shown in a modal via `textContent`,
       never `innerHTML`.
     - It is executed in duktape against the route's real payload (the real
       `merge_diff` and `merge_commands`).
     - Dangerous lines are marked `!`, with the true consequence: the restore
       path sends no authorisation, so `run_targets` refuses such a device
       before sending (step 4's work, shared with the deploy wizard).
   - **Five negative controls.** The first ordering control was a dud (it left
     the original removal in place), and the re-aimed one fires.
   - **The pre-commit hook was bypassed ONCE, as it documents for a deliberate
     removal.** Its one GONE was a name collision: the model's tool is also
     called `restore_golden_config`, in `ai_assistant.py`, which never imports
     `app`.
   - 3815 passed, 0 failed, 0 errors.

4. **D4, in the current wizard** (7.1 later re-homes it in the shared
   component):
   - draw the PROGRAM (`commands`), not the diff;
   - draw each `dangerous` line with its own authorise checkbox, sent as
     `authorise` and folded into the confirm hash;
   - draw the `attribution` split (this edit vs already on the device).

   **BUILT 2026-09-26.**
   - **The wizard draws the PROGRAM**, every line in order, as the thing
     confirmed.
   - **Each dangerous line has its own checkbox.** Ticking one RE-PLANS that
     device with the authorisation, redraws its card with the new command hash
     and clears its tick, so what is confirmed is what is on screen.
   - **A device with an unauthorised dangerous line cannot be ticked.**
   - **Apply sends the authorisation the rendered plan's hash covers**, read
     from the plan payload, never from the boxes.
   - **The attribution split is drawn**: from this edit, and already pending.
   - **The restore path can authorise now.** `/golden/restore/preview`
     accepts `authorise` and folds it into `command_hash`. The client asks
     line by line before showing the program, then sends the authorisation on
     preview and on apply, and the text marks lines `A` (authorised) or `!`
     (refused).
   - **Tested end to end** against a real `/deploy/plan` payload:
     - an authorised `shutdown` deploys and reaches the pipeline;
     - withdrawing the authorisation after the plan is refused;
     - adding one the plan did not cover is refused, with both hashes.
   - **Found by the real payload: `dangerous` and `authorised` are STRIPPED
     strings, while `commands` keeps indentation.** Comparing them exactly,
     the line is never marked and never gets its box. Step 3's restore text had
     the same flaw, and its test passed only because the payload it was given
     was built by hand with the unstripped form: a fixture that could not
     exhibit the case. Both renderers now compare trimmed text. An
     authorisation is therefore `{"s4": ["shutdown"]}`, not the `" shutdown"`
     written elsewhere in this plan.
   - **C24 fixed in the same route**: a confirmed device that cannot be built
     at apply is a named refusal, not a dropped row.
   - Seven negative controls. One first fired for the wrong reason (a syntax
     error) and was redone cleanly.
   - 3841 passed, 0 failed, 0 errors.

5. **C23.** The restore preview's population is the inventory: devices absent
   from the ref are named with what will happen to them, and the denominator
   counts the inventory. That is `plan_restore()`'s logic, now called by the
   route.

   **BUILT 2026-09-26.**
   - **The population rule is in `build_targets()`**, which the preview AND
     the apply call:
     - a whole-baseline restore names every inventory device the ref
       predates (*"not in this baseline"*, with what will happen to it:
       left exactly as it is);
     - a scoped restore names a requested device the ref holds no golden for.
       Before, it vanished too: the loop iterated the ref and skipped anything
       not asked for, from the ref's side.
   - **`restore.coverage()` gives the denominator**: the inventory for a whole
     restore, the selection for a scoped one. The route's summary reads
     *"N of M device(s) in this list"* and says PARTIAL, naming the devices.
   - **`plan_restore()` is deleted.** It held the correct rule and nothing the
     operator reads called it. Its tests were rewritten against
     `build_targets()`, `coverage()` and the route, on a real repository
     rather than a mocked `devices_at`.
   - **Found on the way:** routing `coverage()` through the preview made a test
     that stubs the list name create `data/lists/lab/` in the checkout
     (`get_list_data_dir()` creates on read). The harness guard caught it. In
     production the list is the active one and exists, so those tests stub
     `coverage()` the way they already stubbed `build_targets()`.
   - **Controls.** The first "revert to iterating the ref" control fired by
     CRASHING (`set(None)` in the scoped branch). It was redone so the
     whole-restore branch does nothing, and then exactly the three population
     tests fail.
   - 3838 passed, 0 failed, 0 errors.

6. **B11.** `GET /settings` returns `*_set` flags for every secret and never a
   value. `POST /settings` treats an empty secret field as "unchanged". The
   Anthropic key is write-only in the form, like NetBox's token.

   **BUILT 2026-09-26.**
   - **`GET /settings` returns `anthropic_api_key_set`, `jenkins_api_key_set`
     and `jenkins_token_set`**, never the values.
   - **`POST /settings` treats an empty Jenkins secret as unchanged.** Without
     that, the write-only form would have erased the stored secret on every
     save, because it filled those fields from the values.
   - **The modal shows set/unset placeholders and sends a secret only if
     typed**, so neither end alone can erase one.
   - **Acceptance 4 is a sweep.** Planted secrets (the Anthropic key, both
     Jenkins secrets, the NetBox token), no network, and settings in a temp
     file; all 86 argument-free GET routes are called, and none carries a
     planted value. A floor of 80, and a control that finds one returned.
   - **Found by the sweep's survey: B16.** `/run_command/<ip>` was a GET that
     ran ANY exec-mode command (reload, delete, copy, clear) from a URL, with
     no identity check. The gate table's population was defined by HTTP
     method, so a GET that changes a device was outside it, and a link an
     operator logged in to Access followed would have run it. It is now a
     POST, gated `confirm`, like `/bulk_execute`'s enable mode; the Access
     cookie is not sent on a cross-site POST. Quick actions became buttons
     carrying their command. A test asserts no GET-only view sends text taken
     from the request to a device; the other nine GET views that connect send
     fixed `show` commands.
   - **Found by B16's test: C29.** Only 404 had an error handler, so every
     405, 400, 413 and 415 went out as a 500 "unexpected error, check the
     logs", with an ERROR log line. HTTP errors now keep their status.
   - Seven negative controls.
   - 3855 passed, 0 failed, 0 errors.
   - **Still P.3's first item, not confirmed in this record: the Anthropic
     key's rotation.** The fix stops future exposure. Only rotation retires
     the key that went out.

7. **The terminal is the break-glass path** (decision 3):
   - opening it requires a person (`break_glass`);
   - `data/terminal_audit.jsonl` records who opened it, for which device,
     when it opened and closed, and the peer. It never records keystrokes: a
     trail that copies what it records becomes a second place secrets live;
   - the page says: *"This is the break-glass path. Its use is recorded."*
     and *"A change made here is drift until it is captured into intent."*

   **BUILT 2026-09-26.** `modules/terminal_audit.py` writes
   `data/terminal_audit.jsonl`, 0600 at creation, one line per event.
   - **The events:** `opened`, `open_failed` (with the exception's class),
     `closed` (from the page, or when the browser disconnected) and
     `refused` (at the gate).
   - **Each row carries** the verified actor and kind, the device's address
     and hostname, the socket session, the peer, and the time.
   - **Never a keystroke or any output.** A test asserts the input handler
     never touches the record.
   - **A closed tab is a close.** There was no handler for the socket
     disconnecting, so a session ending that way would never have been closed
     in the record. The new handler records every terminal that connection had
     open, and leaves the shell as it was.
   - **A failed write never breaks the terminal.** It is logged at ERROR and
     counted in `terminal_audit.health()`.
   - **The secret-storage checker lists the file** as a no-secret store.
   - **The page now says "Its use is recorded"**, which is true, and that
     what is typed is never recorded.
   - **Found: a device's terminal is ONE SHELL shared by everyone who opens
     it** (register D12). Sessions are keyed by device address and output goes
     to a room named by the address, so two people see each other's typing
     and output, and one closing ends it for both. The record shows both
     opens; whether that should stay is a decision.
   - Five negative controls.
   - 3866 passed, 0 failed, 0 errors.

8. **The agent loses every tool that sends to a device, commits, or edits
   code**:
   - three `execute_*` tools in config mode;
   - `restore_golden_config` and `restore_pre_change_snapshot`;
   - `run_ansible_playbook`;
   - `save_golden_config` and `finalize_verified_config_change`;
   - `read_app_file`, `patch_app_file`, `restart_server` and `git_commit`;
   - the auto-continue that answers the model's own confirmation questions.

   It keeps its read tools until Stage 8 rebuilds the library (decision 1).
   The 19 CI tools go in P.4.

   **BUILT 2026-09-26.** 73 tools become 49.
   - **Removed from the tool list AND the dispatch (24):**
     - `restore_golden_config`, `restore_pre_change_snapshot`;
     - the three Ansible tools;
     - `save_golden_config`, `finalize_verified_config_change`, `log_change`;
     - `read_app_file`, `patch_app_file`, `restart_server`, `git_commit`;
     - the self-writing knowledge tools and `query_ccie_kb` (decision 6);
     - the four report tools (decision 6);
     - **beyond the step's list, under decision 1's "never settings or
       gates"**: `set_variable`, `delete_variable`,
       `update_compliance_policy` and `set_collector_ip`.
   - **Six writers left with no caller were deleted:** the change-log,
     lab-note, KB and playbook writers.
   - **The three `execute_*` tools became READ-ONLY, not just
     config-mode-free.** Exec mode is not a read (reload, delete, copy,
     clear), so `_read_only_refusal()` allows `show` (and `sh`, `sho`),
     `ping`, `traceroute`, `dir` and `more`, and refuses config mode, any
     other verb and a line break. It is the first statement of each branch,
     before any session opens. The `mode` parameter is gone from their
     schemas.
   - **The auto-continue is removed.** A question the model asks is for a
     person. The continuation of a reply the token limit CUT OFF is kept,
     since that answers a truncation, not a question.
   - **None of the 24 had a test.** `tests/test_p3_agent_tools.py` pins their
     absence, the read-only rule both ways, the check's position, and the
     auto-continue's absence (parsed, not grepped, since a comment explaining
     the removal quotes it). Two controls.
   - **Left, and recorded:** the Jenkins tools (P.4); the prompt naming the
     removed tools 77 times (C30, Stage 8.5); and no pre-execution
     allowlist, which is 8.3.
   - 3897 passed, 0 failed, 0 errors.

9. **CLAUDE.md's B12 correction** is replaced by the enforced statement, with
   the measurement that proves it.

    **BUILT 2026-09-26.**
    - **Local, the whole table**: `test_route_gates.py` sends a request with
      no identity to all 87 gated endpoints (121 mutating, 34 `not_device`),
      with every view replaced by a sentinel. All 87 answer 403 and no
      sentinel runs. The earlier test sampled eight paths; a statement about
      every route needs a measurement of every route. Control: letting
      `approve` through names each approve route that then reaches its view.
    - **On the host at `9c4cf07`**: 403 `no_header` on `/deploy/apply`,
      `/golden/restore/apply` and `/ai/approvals/<id>/approve` (400, 400 and
      404 before P.3), and on `/templatize/bulk/apply` and `/onboard/create`.
      404 on both removed golden replays.
    - **The live terminal**: an unauthenticated socket was refused before any
      shell, and one `refused` row went to `data/terminal_audit.jsonl`
      (`0600`). That row is the probe's own.
    - The CLAUDE.md paragraph now states the property, its measurements, and
      what it does not cover: the host CLI (authenticated by SSH, and its
      commits say `host-shell`) and the agent's tool gate (Stage 8.3).
10. **D10 (decided 2026-09-26): every commit says whether its actor was
    verified.** Each commit path writes `Actor-Verified: access` (a gated
    route: the identity the gate verified), `host-shell` (a CLI on the host,
    where SSH is the authentication) or `none`. The line is drawn by what the
    code WROTE, never by date: the host ran old code after `c5a34c1` was
    pushed, which is C1's race arriving as a data-integrity question. The
    display is 7.5's: Versions states once, *"N of M commits carry a verified
    identity"*, and marks the rest *"recorded, not verified"*. At the time of
    the decision that was 5 of 92, so the actor filter answers from claims
    for 95% of the history, and a muted style alone would not say that. It is
    a denominator, as drift's *"checked 7 of 9"* is.

    **BUILT 2026-09-26** (the trailer; the count and the marks stay 7.5's).
    - **One place writes it.** `repo.git()` adds `Actor-Verified:` to any
      commit message carrying an `Actor:` line, so every NSoT writer
      (`save_golden`, `save_templates`, `save_host_vars`, a rename, `retire`,
      the manifest dedupe script) gets it without being edited. A writer that
      has to remember is the proxy-population failure again.
    - **`identity.actor_verification(actor)`** decides it from what the code
      knows at that moment. In a request, `access` only when the gate verified
      THIS actor (`g.nmas_identity.actor == actor`), so a name that differs
      from the verified one is `none`. Outside a request, `host-shell` for a
      CLI and `none` for the app's own threads, told apart by
      `route_gates.installed()`: only the app process installs the gate.
    - **Measured, not assumed: every gated commit runs on the request
      thread.** The deploy pool defers its golden to the batch commit in the
      route (`defer_golden`), and the NetBox import threads never commit to
      git. The pipeline's non-deferred path names `Actor: pipeline`, so it
      records `none`, which is true.
    - **Two writers named nobody.** `abandon_onboarding` held the actor and
      committed without it; it now writes `Source`/`Actor`. The legacy Git
      tab (`config_git.commit_configs`) committed through its own transport,
      and wrote the verified `request_actor()` and the trailer itself.
      **Removed 2026-09-27 (register C104)**: it could commit only what a
      failed operation had left staged.
    - **A scan keeps it that way**: every git `commit` call in `modules/` and
      `scripts/` goes through `repo.git()` or is a named exemption (the Git
      tab, and its repository's empty first commit), with a floor and a
      no-ghosts check.
    - Tests: `test_actor_verified_trailer.py`, including one driven through
      the real app, whose gated route writes `access`. Seven negative
      controls, all failing on the targeted assertions.
    - 3948 passed, 0 failed, 0 errors.

**B13, found 2026-09-26 while verifying step 1, fixed out of sequence.**
Opening the terminal through the tunnel to check the gate put 27 of s1's 32
password characters on screen: `modules/terminal.py` sent `enable`, the
stored secret and a newline on fixed sleeps without reading, and every device
is already at `#`. **The gate was fine; the thing behind it had never been
examined.**
- The terminal is fixed (send, read, decide).
- `not_already_type_9`, which blocked every rotation of an already-rotated
  device, is fixed.
- The page states what the terminal is.
- Measured: the value is in neither the syslog files nor Loki.
- s1's password is rotated by the operator with the ordinary tool
  (register B13).

11. **One stored copy of a credential (register B14, the operator's point E).**
    The CSV `secret` column holds a second copy of the login password on every
    device, written deliberately by rotation (`credential_rotation.py`, the
    CSV branch) and by onboarding's override (`set_device_override(ip, user,
    pw, pw)`). No device has an enable secret, and Netmiko sends `secret=` only
    in answer to an enable prompt, so the copy does nothing the password does
    not. It is also why sending it looked harmless.

    The fix: store an enable secret only when a device has one. Otherwise the
    field is empty, and the connection falls back to the password at connect
    time (Netmiko's own semantics). Make that fallback explicit in
    `connection.py` and `enable_secret()`, rewrite the stored rows once, and
    correct the break-glass record's `has_enable_secret`, which reads the
    duplicate and claims every device has one. **A credential stored twice is
    a credential that leaks twice.**

    **BUILT 2026-09-26.**
    - **`connection_params` treats an empty secret like `None`**: the login
      password is used, which is Netmiko's own fallback. It is the one place
      every connection that passes a secret assembles it. Four direct
      `ConnectHandler` sites pass no secret at all and are unchanged.
    - **The writers stopped writing the copy.** Rotation's CSV branch stores
      an encrypted EMPTY string (every reader decrypts the column, and
      decrypting `""` raises); rotation's override and onboarding's staged
      override store `""`.
    - **The break-glass record's `has_enable_secret`** is true only for a
      secret that differs from the password. It read true for every device.
    - **`scripts/nmas-credential-dedupe` empties the copies already stored**,
      dry run first, in every list's CSV and in the credential store. It
      keeps a distinct enable secret, leaves anything it cannot decrypt, and
      prints names and counts only. **It refuses to write a store that does
      not parse**: the store's own loader reads an unreadable file as empty,
      and saving that would erase every credential.
    - **One test had pinned the duplicate as correct** (`got["secret"] ==
      secret`, in the onboarding credential test). It now asserts the
      property that matters: the connection's enable secret is the password.
    - Four negative controls.
    - 3915 passed, 0 failed, 0 errors.
    - **Operator's step: run it on the host** (`python3
      scripts/nmas-credential-dedupe`, read the dry run, then `--apply`). Then
      re-export the break-glass record, which still carries the copies.

12. **A rotation reports success only when the device's boot file is SAFE, and
    says which stage stopped it when it is not** (register B15, the operator's
    acceptance; with B2's rotation half).
    - **Success means the checker's verdict.** The chain's last stage calls the
      same function `nmas-check-startup-applies` uses and requires SAFE, so the
      rotation and the checker cannot disagree. It currently checks the new
      hash's presence with `verify_startup_file`, which is a second check of
      one property.
    - **A stage that does not run is named**, and the state is never success.
      This is already true of `ROTATED_UNVERIFIED`, and it stays true.
    - **The failure message leads with the danger**: *"s1: NOT SAFE TO REBOOT —
      its startup config still holds the PREVIOUS password"*. The success words
      (*"ROTATED and committed"*) no longer come first.
    - **The outcome is DURABLE (B2).** Each stage writes a row: names, outcomes
      and the reason, never a value. A device whose last rotation did not
      persist is a Needs-attention row until its boot file reads SAFE. A
      terminal scrollback is not a record.
    - **One owner for the sync script.** `clab_sync_script` has been empty since
      the 2026-09-23 erasure, while the timer's unit names
      `<home>/bin/clab-sync`. Until one source is chosen, job health
      compares the setting with the unit's `ExecStart` and names a mismatch.
    - **Acceptance:** with the sync stage broken, a rotation exits non-zero,
      names `clab_sync`, writes the durable row, and the device appears in
      Needs attention. With it working, the rotation reports success only
      after `nmas-check-startup-applies` reads SAFE. Controls: a success path
      that skips the SAFE check must fail the suite.

    **BUILT 2026-09-26.**
    - **One verdict function.** `credential_rotation.startup_safety()` is the
      checker's composite: carries-current first, then applies.
      `nmas-check-startup-applies` calls it, and the chain's new last stage,
      `startup_safe`, requires it. So a rotation reaches `ROTATED_PERSISTED`
      only when the checker would read SAFE. The old last check (the new
      hash present) was a second check of one property.
    - **The message leads with the danger**: *"s1: NOT SAFE TO REBOOT OR
      REDEPLOY. Its startup config does not hold the new password: persistence
      FAILED at clab_sync. …"*. The success words follow it.
    - **The record.** `rotate()` and `persist()` are thin wrappers around
      `_rotate()` and `_persist()` (signatures kept with `functools.wraps`),
      and they append one row to `data/rotation_audit.jsonl` on every exit.
      Each row holds the state, the failed stage, and every stage's name,
      outcome and reason, redacted and capped. Never a credential; 0600; a
      failure to record never breaks the rotation. The secret-storage checker
      lists it. The test harness sends it to a temp file.
    - **Job health reads it.** One row per device from its latest record:
      `not_safe_to_reboot` names the failed stage or "persistence NOT
      ATTEMPTED", and `revert_failed` flags a possible lockout. A later persist
      reaching SAFE clears it (`nmas-persist-credential` records one).
    - **One owner for the sync script:** a `clab-sync-owner` row compares
      `clab_sync_script` with the timer unit's `ExecStart`, and reads
      `unset_guard`, `mismatch` (both named) or `ok`.
    - **Both CLIs carry the list into `persist()`**, so its lab and its SAFE
      verdict are the list's, not the active one's.
    - **Tests.** The acceptance is tested on the case that happened: the sync
      stage broken, then fixed. Four structural tests followed the code into
      `_persist` and `startup_safety`. Six mutation controls; one was silent
      first (nothing asserted that `health()` includes the rotation rows,
      which was a missing test) and fires now.
    - 3929 passed, 0 failed, 0 errors.

**P.3 ACCEPTANCE** (each item observed, each with a control that must fail):
1. **Every mutating endpoint is classified**, and the classification test has
   a floor (at least 131 mutating rules) and anchors: `/deploy/apply` must be
   `confirm`, and one known settings route must be `configure`. **Control:**
   add an unclassified device-changing route, and the suite fails.
2. **Refused before input, for real.** Called with no identity, every gated
   route answers **403** before its own validation, shown for `/deploy/apply`,
   `/golden/restore/apply`, `/ai/approvals/<id>/approve`, `/bulk_reload`, a
   file transfer and `POST /settings`. On the HOST, `curl localhost:5000`
   without an Access assertion gets 403 on `/deploy/apply`. **Through the
   tunnel, as the operator, a real deploy still completes**, because the gate
   passes a person. Both measured, operands printed.
3. **The static scan finds zero ungated device-changing routes**, with a
   floor on the scan's own population and the anchor that failed on
   2026-09-26 now passing.
4. **No GET route returns a secret value.** Planted secrets (settings, the
   Jenkins fields, the Anthropic key) are searched for in every GET route's
   JSON. None appears. **Control:** return one, and it is found. A `POST
   /settings` with an empty secret field leaves the stored value unchanged.
5. **Every cut route answers 404**, `check_removed_definitions.py` reports
   nothing still called, and no template or script refers to them.
6. **Restoring one device from the GUI goes through the guarded preview**:
   program, residue, confirm hash, a person. The replay routes are gone.
7. **The wizard draws the program, `dangerous` and `attribution`**, executed
   in duktape against a real `/deploy/plan` payload. A program with an
   authorised `shutdown` deploys end to end in the test client, and changing
   the authorisation after the plan is refused.
8. **The restore preview counts the inventory.** Over a baseline older than a
   device, the device is named and the denominator is the inventory size.
   **Control:** revert to `build_targets`, and the test fails.
9. **Opening the terminal writes one audit row and no keystrokes**, and the
   page carries both sentences.
10. **The agent's tool list contains none of the removed tools**, with a test
    pinning the names, and no reply is auto-answered.
*(Item 11, the Anthropic key's rotation, moved to "Do this first" above,
2026-09-26.)*

**P.3 ACCEPTANCE RUN, 2026-09-26, at `5b087c4`: every item observed, and
every control FIRES.** One harness ran the ten items' tests clean (206
passed), then applied eleven controls. Each file was restored from a scratch
copy, and the same 206 passed again afterwards. A control counts only if it
fails its TARGETED test with 0 collection errors, so a crash cannot pass as
a control.

| # | Observed | Control, and what failed |
|---|---|---|
| 1 | 121 mutating endpoints, all classified; `/deploy/apply` is `confirm` | an unclassified POST route added: `test_every_mutating_endpoint_is_in_the_table` |
| 2 | all 87 gated endpoints 403 with no identity, no view reached (sentinels); on the host, 403 `no_header` on `/deploy/apply`, `/golden/restore/apply`, `/ai/approvals/<id>/approve` | the gate lets `approve` through: the exhaustive sweep plus three sampled paths |
| 3 | no GET-only view sends request text to a device (80+ views scanned) | such a view added: `test_no_get_only_view_does` |
| 4 | no argument-free GET carries a planted secret; an empty secret field saves nothing | GET /settings returns the Jenkins key: the planted-secret sweep. The empty-field guard removed: `test_empty_jenkins_secrets_leave_the_stored_values` |
| 5 | every cut route 404; `check_removed_definitions.py c5a34c1^..HEAD` exits 0 (55 removed or moved, none still called); nothing shipped names them | a cut route put back: `test_each_cut_route_is_404[POST-/bulk_restore_golden_config]` |
| 6 | both Restore buttons open the guarded preview at HEAD | bulk restore posts to the old replay: `test_bulk_ops_opens_the_guarded_preview_at_head` |
| 7 | the wizard draws every line, one authorise box per dangerous line, and an authorised `shutdown` deploys end to end | dangerous lines unmarked: `test_the_dangerous_line_has_its_own_authorise_box` |
| 8 | the restore preview's denominator is the inventory, and a ref older than a device is partial and names it | `partial` forced false: `test_the_denominator_is_the_inventory_and_the_ref_is_partial` and the route's sentence |
| 9 | opening the terminal writes one row, keystrokes never; the page states both sentences; the live terminal refused an unauthenticated socket and recorded it | the open is not recorded: seven audit tests |
| 10 | 24 removed tools absent from the list and the dispatch; only read-only verbs run; no reply is auto-answered | `reload` allowed: `test_anything_else_is_refused[reload]` |

**Two corrections to the criteria, stated rather than quietly met:**
- Item 1's floor said "at least 131 mutating rules". That was measured
  BEFORE steps 2-3 cut ten routes and step 7 removed `/disconnect`. The test's
  floor is 121, which is the population now. A floor that still read 131 would
  fail for the right code.
- Item 2's tunnel half ("a real deploy still completes, as the operator") was
  observed at step 1 on the host: the golden commit carried the operator's
  email. The host now runs `9c4cf07` (step 8), so steps 9-12 are not
  deployed there. **Re-observing it after the pull is the operator's step**,
  and the one thing P.3 still needs from the host.
  **OBSERVED by the operator, 2026-09-26, after the pull.** A real deploy
  through the tunnel: `c7711d6` (the deploy's golden) and `2fb07db` (an
  intent commit) both carry `Actor: <operator>` and `Actor-Verified:
  access`. So there are two paths, both verified through the gate. With step
  9's unauthenticated 403s, the gate refuses without a person and passes with
  one, on the real system.
- Item 1's correction, read the right way round: a floor set too HIGH fails
  correct code, loudly. The dangerous direction is a floor too LOW, which
  passes because the population shrank under it. Both are a number that has
  stopped describing its population.

**P.3 IS COMPLETE (2026-09-26).** It closed its five scoped items and found
eleven more that nobody had scoped; the ledger is in
[NSOT_WRITEUP_NOTES.md](NSOT_WRITEUP_NOTES.md), "What P.3 cost and bought".

**Full suite at `5b087c4`: 3950 passed, 0 failed, 0 errors.**

### P.4 — Cut Jenkins (before Stage 7)

**Decided 2026-09-26 (operator): before Stage 7**, so Stage 7 does not draw a
tab it is about to delete. The design, the check inventory and the reasons
are in [NSOT_CI.md](NSOT_CI.md). Its section 6 is the step list, and its
section 7 is the acceptance:
- remove Jenkins, including the 19 CI tools;
- correct the `ci_gate` stage to say what it checks;
- GitHub Actions on the app repository;
- `nmas-deploy` refuses a SHA whose CI failed or is pending, with `--offline`
  running the suite locally;
- `nmas-deploy` versioned into the repository (with 6.5).

Still **UNDECIDED** inside P.4: scheduled protocol regression (N13), and
config-repo checks (R5-R10) as a post-commit job on the NMAS. Neither blocks
Stage 7.

**Steps 1 and 2 BUILT (2026-09-26)**, in three commits:
- **1a, the app surface:**
  - the tab, badge, wizard, settings section and both workflow switches;
  - 14 routes. Six were mutating, so the gate table's floor went from 121 to
    115. One was the unauthenticated webhook that satisfied `/git/commit`'s
    "pipeline passed" check, which now refuses a `pipeline_name` by name
    (410);
  - Save All's validation pipeline, and its false "Jenkins not configured"
    line;
  - `event_monitor`'s sync and its timer;
  - `agent_runner`'s `jenkins_failure` task;
  - the `is_jenkins_building` deferrals;
  - `PipelineContext.check_devices`: decrypted credentials that nothing read.

  A page older than the server that still posts Jenkins fields is told they
  were removed.
- **1b, the agent:** the 19 CI tools (the tool list is 30, was 49); the
  prompt builder's Jenkins code; and the system prompt's Jenkins section.
  17 scattered mentions remain, on C30, for 8.5.
- **1c, the modules:**
  - deleted: `jenkins_runner`, `check_runner`, `jenkins_shell`,
    `pipeline_builder`, the stale `Jenkinsfile` and its test;
  - `configure.py`'s script, XML and job-metadata generators;
  - list deletion's job cleanup;
  - the step-shell control. `jenkins_step_shell`, `wf_run_jenkins` and
    `wf_save_golden` stay in the schema, read by nothing, because keys are
    never deleted;
  - `data/jenkins_checks.json` is a RETIRED store: the secret checker names it
    until it is deleted.
- **Step 2:** `_stage_ci_gate` is a local dangerous-command check, and says
  so. An unauthorised dangerous line is refused by name. A clean program passes
  with no "no check registered" warning.
- **Acceptance 1 and 2 observed:** `test_no_jenkins.py` (no file imports a
  removed module, with a floor and an anchor) fails when one import is re-added.
  `check_removed_definitions.py` reports nothing still called. It learned on the
  way that a filename (`"jenkins_results.json"`) is a mention.
- **Step 3 BUILT (2026-09-26):** `.github/workflows/ci.yml` on the host's
  versions (`requirements.lock`, `--no-deps`), coverage reported and never
  gated. Green on a clean runner at the second attempt: the first failed at
  install, which is how C40 was found. Merged after green.
- **Step 4 BUILT (2026-09-26):** `scripts/nmas-deploy`, versioned (it was 25
  lines of bash on the host only).
  - It gates on the TARGET commit before HEAD moves.
  - Exits: 0 deployed, 1 CI failed/cancelled/running, 2 could not ask or no
    run, 3 `--offline` suite failed, 4 local state, 5 no answer after restart.
  - "No run" is never a pass. The one legitimate no-run case, a docs-only push,
    passes only when every change since the last green commit matches the
    workflow's own `paths-ignore`, read from `ci.yml`.
  - Every run is a row in `data/deploy_audit.jsonl` (0600).
  - `test_nmas_deploy.py` drives it against a real bare origin and clone, and
    asserts HEAD unmoved on every refusal. Six controls, each failing its
    target.
  - **Refined after the operator's first live run (2026-09-26, `3b5c6df`).**
    Its row said "deployed" with from == to, and a 200 from `/` would have
    passed for a process that never restarted.
    - `GET /health` now reports the commit the running process LOADED and
      its OS start time.
    - `nmas-deploy` waits until both show the target and a start AFTER the
      restart was issued, and records them.
    - The verdict is "deployed a -> b", "already at a, restarted" or
      "... NOT restarted".
    - The row carries `started_at`, `restart_issued_at` and `ended_at` to
      the millisecond.
    - Three more controls, each failing its target.
  - **Second refinement, from the operator's measurements (2026-09-26).**
    - **The restart is confirmed by IDENTITY:** systemd's MainPID changed,
      `/health` answers from that new pid, and it loaded the target commit.
      The time comparison could false-fail a real restart. psutil's process
      start is `/proc/stat` boot time (whole seconds, truncated) plus ticks,
      and it measured 0.66 s BEFORE systemd's own start.
    - `/health`'s `started_at` is now the app's own `time.time()` at load.
      The row records systemd's `ExecMainStartTimestamp` at microsecond
      resolution, for display only.
    - **The no-run rule comes from a GREEN commit:** `paths-ignore` is read
      from the last green ancestor's `ci.yml`, never the target's. Otherwise
      a commit widening it to `**` would wave itself through.
    - **A change under `.github/workflows/` is never ignorable,** whatever
      any `paths-ignore` says.
    - A test starts the process 0.9 s before the restart and still passes
      on identity. Five controls, each failing its target.
  - **The red-commit test (2026-09-26).** Pending and failed both refused
    with exit 1 on `7be2c93`, naming the run; the run failed at the tests
    step, after the install passed. The first red commit, `003a93d`, got NO
    run: its message described the next step in words containing GitHub's
    skip directive, which GitHub honours anywhere in a message, so it became
    the no-run case (exit 2). **`--offline` was broken**: it tested a
    `git archive`, where `/health`'s test fails on every commit, so its exit 3
    on the red commit was right for the wrong reason. Fixed to test a
    checkout of the target; re-run on the host against a scratch clone with
    the restart replaced by a function that raises.
  - **Operator's steps, in order:**
    1. Deploy this commit with the OLD script.
    2. Replace it:
       `ln -sf ~/python/Agentic_NMAS/scripts/nmas-deploy ~/bin/nmas-deploy`.
    3. Say so. Only then does the red-commit test (acceptance 3) begin: a
       deliberately failing commit, the refusal, `--offline` refusing, a fix,
       and the deploy proceeding.
- **Operator's step:** delete `data/jenkins_checks.json` on the host. Measured
  2026-09-26, by field state only: all four fields are EMPTY and no per-list
  Jenkins file exists, so it holds no credential and deleting it is
  housekeeping. `nmas-check-secret-storage` names it until then.
- **ACCEPTANCE (NSOT_CI.md section 7), item by item, 2026-09-26.**
  1. **No Jenkins code remains: MET, re-checked against today's tree.**
     `check_removed_definitions.py` over all of P.4 (`d25e3ff^..HEAD`) exits
     0: 146 definitions gone, none still called. `test_no_jenkins.py` passes,
     and fails with one import of `jenkins_runner` re-added to
     `drift_check.py` (restored from a copy).
  2. **The gate says what it checks: MET.** An unauthorised dangerous line is
     refused by name, and a clean program passes with no "no check
     registered" warning (`test_pipeline.py`, both passing today).
  3. **A red CI run stops a deploy: MET, every case measured with its
     operands.**
     - Pending: exit 1, "CI is still in_progress" (the operator, on `7be2c93`).
     - Failed: exit 1, "CI failure for 7be2c93c53: …/runs/36270687451.
       Refused." (the operator, twice).
     - A code commit with no run: exit 2, "no CI run for 003a93d0cd, and it
       changes more than ignored paths since 1319890f8d, the last commit CI
       passed: ['tests/test_red_commit_probe.py']. Refused." This one was
       asserted and never run until the acceptance measured it (the verdict
       function against the real API).
     - A docs-only commit with no run: exit 0, reading `paths-ignore` from
       `eb70788`, the last commit CI passed, not from the target. Measured
       LIVE: the operator's 22:00 deploy, `1319890 -> 13a5011`.
     - The fix proceeds: the operator's 22:27 deploy, `13a5011 -> 5eef2df`,
       "CI passed", pid 268370 -> 361070, confirmed by identity.
     - `--offline`, one of each, on the host against a scratch clone with the
       restart stubbed: green `5eef2df` passed the full suite and reached the
       restart; red `5055fe5` (the green commit plus only a failing test,
       local) exit 3, "1 failed, 4004 passed in 287.81s; network: NOT
       CONFINED". Its FIRST version could not pass at all (a `git archive`
       has no `.git`), so its first red result proved nothing; the rule this
       produced is in CLAUDE.md as the inverse of "a test that passes in both
       cases shows nothing".
  4. **Every scheduled check names its cause when it fails: NOT YET
     OBSERVED.** It needs one scheduled check broken deliberately on the
     host, as P.2 step 8 did. Proposed: the heartbeat check, pointed at a
     closed loopback port through a RUNTIME drop-in (under `/run`, so a
     forgotten revert does not survive a reboot). Predicted, to be checked
     rather than assumed: `--check` exits 2 (`UNPROVEN: ConnectionError …`),
     systemd records a failure, and `nmas-jobs` names that line as the
     cause, because its cause scan matches `Error`.
  5. **No check implemented twice: NOT APPLICABLE YET.** Scheduled
     regression (step 5) is undecided and unbuilt, and the AI's
     `detect_config_drift` goes with Stage 8, as the item itself says.
  6. **The GUI shows each CI state beside its trigger: carried by the Stage 7
     GUI plan**, as the item itself says.

### P.5 — Template approval, scheme 3 (D11; decided 2026-09-26, placed after P.4)

**Approval becomes the template closure hash and the person who approved
it.** Per-device fidelity stays where it already runs, live, in
`blocking_reasons`. The argument is in
[NSOT_FEATURE_AUDIT.md](NSOT_FEATURE_AUDIT.md) 8c. The deciding point: the
device-set half repeats a check that already runs per device, so it is a
property of the inventory, not of the template.

- **Approving** shows the validation across the bound set, per device, as
  evidence. It requires at least one validated device, not all of them.
- **A template edit** still revokes every approval over it.
- **A scheme-2 record** is not honoured silently, so moving to scheme 3 is an
  explicit re-approval.
- **The operator's addition: the approval badge says what it covers AND what
  it does not.** It is a claim about the template. Each device is validated
  at its own deploy, and a device the template cannot reproduce is blocked
  alone. Without that sentence scheme 3 reads as weaker than scheme 2, to
  anyone who does not know why.
- **It resolves D2**, and onboarding stops revoking its platform's approval.

**Placement: APPROVED 2026-09-26 (operator)**, after P.4 and before 7.0. It
changes how a gate behaves, and 7.6 draws the badge, so the behaviour must
exist before the screen that explains it.

**BUILT 2026-09-26.**
- **The premise was measured before anything changed:**
  `RenderArtifact.template_report` is computed on every plan, unconditionally,
  from the capture's own parse, and `blocking_reasons` refuses a device with
  missing, invented or reordered lines whatever approval says. So a device
  the template cannot reproduce was already blocked alone.
- `approval.template_fingerprint()` is the template's closure hash, and no
  device. `approve()` needs at least one bound device to round-trip and
  records every device's result as evidence; `approval_status()` carries
  `covers` and `does_not_cover`, and the template library draws both, the
  evidence and the approver.
- The approve route records a bound device with no capture as not validated
  instead of answering 400 (D2's deadlock), and `nsot_reapprove_templates.py`
  does the same, recording the OS user as the actor instead of "operator".
- The deploy plan no longer renders every bound device to feed the
  fingerprint: `_bound_host_vars` built a full artifact for each, on every
  plan, for a hash that no longer reads them.
- Ten scheme-2 pins rewritten as scheme-3 claims, the D2 pins flipped with
  the reason. Controls, run confined, each failing its target: every device
  required again; the device set back in the fingerprint; a scheme-2 record
  honoured; the badge without what it does not cover; the route refusing a
  device with no capture.
- **Operator's step after deploying it:** every existing approval reads
  "approved under fingerprint scheme 2" and deploys stop until each template
  is re-approved, by design. From the Templates tab (Approve), or on the host:
  `python3 scripts/nsot_reapprove_templates.py <list>` (dry run), then with
  `--apply`.

### P.6 — ZTP as a third address source — COMPLETE 2026-09-27 (Lab 8 demonstrated end to end; teardown clean)

**Closed 2026-09-27.** Built in six steps. Proven by five measurements on
`bp-ztp-a`, which survived a reboot. The teardown was clean: census exit 0,
reservation removed and read back, r1's route to r6 unchanged. The ledger
of what the measurements found is in [P6_ZTP.md](P6_ZTP.md) section 8.

*(The original entry, kept for the reasoning:)*

The course's Labs 8 and 9 (ZTP, then ZTP + IaC) land on Phase 2's
foundation. ZTP fits the onboarding design as another address SOURCE, beside
`static` and `dhcp`.

**What exists:** reading Kea reservations and leases (Phase 2); the bootstrap
artefact re-derived from committed intent (`bootstrap_artifact()`); the
device-to-lab map.

**What does not:**
- writing Kea reservations;
- DHCP option 67 (the config file name);
- a config server that serves the bootstrap artefact;
- `ztp` as a source in `build_plan()`;
- assigning a device to a containerlab lab from the tool.

**Ordering, and why.** Build the BACKEND before Stage 7 designs onboarding.
Today's interface gets only one more option in the existing source selector.
- **Before 7.4:** a screen designed around states nobody has observed
  encodes guesses, and a path that has never carried anything fails on first
  use. The ZTP states (reservation written, config fetched, first seen) have
  to be measured before 7.4 draws them.
- **Not inside today's interface beyond one option:** Stage 7 re-homes
  onboarding, so more UI now is UI thrown away.
- **Proven on a throwaway first**, the way Phase 2 was proven on
  `bp-dhcp-a`.

Lab 9 (ZTP + IaC) is onboarding phase 1, then phase 2, then an intent
deploy: the shape that already exists.

**Timing:** the lab due dates are not known. If one is tight, the operator
pulls this forward.

**SCOPED 2026-09-26: [P6_ZTP.md](P6_ZTP.md).** Measured on the host first:
Kea 2.4.1 runs on the NMAS host with no `host_cmds` hook, so no
`reservation-*` command exists, and its config file is `root:root 0644`
while Kea runs as `_kea`, so a reservation added by `config-set` could not be
written back and would vanish at the next restart. Nothing serves TFTP. Three
decisions for the operator (how a reservation is written, how the config is
served, where the server's address comes from) and five measurements the
throwaway must make before anything is built, each with its prediction.

**DECIDED 2026-09-26 (operator): D1, D2 and D3 as recommended.** Runbook:
[P6_ZTP_PROBE.md](P6_ZTP_PROBE.md), measurement 1 ready to run. Prediction 1
held BY READING before any boot: vrnetlab always attaches a CVAC config ISO,
and its watchdog restarts a VM after 300 quiet console spins, so the probe
binds a configless variant (`patch-configless.py`, tested against the real
script). If the node asks only because the probe removed that config, Lab 8
demonstrates the TOOL's half against a persuaded node, and the write-up says
so.

### P.7 — Alert rules generated and tested (DECIDED 2026-09-28, its own item; placement before 8.6)

**Generated rules carry a per-series baseline (C433, the operator's decision of 2026-10-04).**
A rule fires on a series departing from its OWN history: above the larger of the rule's floor
and a multiple of the series' 7-day p95, from a recording rule. It never fires on a level the
port always runs at. The global threshold is not raised, because that would hide the same rate
on a port that never discards. Until P.7 builds it, the in-band acknowledgement on Needs
attention (built 2026-10-04) is how a chronic series is quieted without being hidden.

**Why** (C168, the operator's decision): of the seven hand-built Grafana rules, three were wrong in ways that
looked fine, and nothing would have caught any of them. `gRPC telemetry stream lost` resolves at exactly the
moment it should fire (a lost source's series vanishes rather than reading 0); `Critical syslog received` works
BY ACCIDENT, matching mnemonics whose NAME contains CRIT and missing real severity-2 messages; `Interface down`
reads a healthy network as no-data. The `nmas-heartbeat` group, generated by `nmas-heartbeat-rules` and tested,
is the only group that came out right. **A rule that fires sometimes, for the wrong reason, is harder to find
than one that never fires**: "it has alerted 9 times" would have satisfied anyone checking.

**The heartbeat generator is P.7's first, and its re-measure becomes an action in the app** (the operator,
2026-10-01, after "STALE RATE s3": the fix was a console command with a placeholder). Preview the installed
and the new window per device with what each is measured from, confirm as a person, write the rules file,
then a host step with every value filled in (the installed file is root's in `/etc/grafana/provisioning/
alerting/`, and the app's Grafana account is an Editor, which cannot reload provisioning: measured
2026-10-01). The STALE that prompted it was not a moved clock: C299, a reboot gap counted as an interval.
**For a device whose clock rate varies, RECOMMENDED: a fixed window from the observed SPREAD, never one
that follows the rate.** A window that follows the measured rate moves the alert to whatever the device
does, so a device slowing steadily (s3 overnight 0.57 to 0.52) would never page: the slowdown chased all
day would be invisible to the heartbeat, and each move is a write to root's provisioning. The window is
instead the midpoint of the band from the shortest and longest REAL gaps over a long lookback (7 days, from
6 h; misses, configuration changes and restarts excluded), labelled with the spread and its dates. s3's
24 h spread (474.8 to 639.8 s) gives the band (1280, 1424); its installed 1337 s is inside it. The check
then reads STALE only when the device leaves its recorded spread far enough that the installed window no
longer tells one miss from two: a real finding (C93's kind), drawn as a job-health row with the re-measure
as its action, never a page. And where the spread itself grows until no window separates one miss from
two, the rule says INSEPARABLE, which is the honest state. **DECIDED 2026-10-01 (the operator): a fixed
window from the spread, with a 7-day lookback. BUILT the same day**, with one correction measured on the
host before it was built: over 7 days the EXTREMES made s1 and s3 INSEPARABLE (s1 261.0 to 393.1 s, s3
412.4 to 639.8 s), and every extreme fell in the nightly backup window (08:35 to 09:01 UTC, C289), s3's
shortest a catch-up burst after a stall. So with 200 or more gaps the band runs from the 0.5th to the
99.5th percentile (s1 316.1 to 331.1 s, s3 472.7 to 609.0 s), and the rule says the trade in its own label:
how many gaps fall outside the band and how far, that one miss never fires even at the longest gap seen,
and that a double miss inside a burst of the shortest may go unseen. Fewer gaps and the extremes are the
band. A Loki read that returns its whole page (5000) is refused as cut. Read on the host with the built
code: all nine installed windows sit inside their 7-day bands, so nothing needs writing (s3: installed
1337 s, band (1218, 1418)).

**Scope:**
- a generator per rule KIND (device reachability, interface state, telemetry streams, syslog severity, IP SLA),
  each rule's no-data behaviour decided per kind and written in the rule (a count of zero is healthy: OK);
- the EXPECTED set from inventory where one exists (the gRPC sources, the syslog devices), so a member that
  vanishes is a firing, never a resolution;
- a syslog rule's device from the LINE, since the stream's `host` label is the collector (`nmas` on every
  line), each rule saying which (8.6's constraint). **ONE definition of "which device"**: the origin-id
  after the IOS sequence number (`719: s4: `), the field the heartbeat rules read, shared by every
  generator; a first regex took the sequence number and gave 11 "devices" that were message counters
  (C166). And a check that every device label a rule produces names an inventory device;
- **the check that would have caught all three: each generated rule can cross its own threshold against what
  the fleet actually produces.** In the suite, against real captured lines and series (the fixture rule: pieces
  real); on the host, probe 5 turned into a job: each rule's own query asked of its datasource over a window,
  its extreme against its own threshold, and a job-health row for a rule that cannot cross it;
- the hand-built folder retired rule by rule as each is replaced, never edited in place again;
- **every generated rule a PROVISIONED FILE** (measured 2026-09-30, NSOT_GUI_BRIEF 15.3): on
  Grafana 13.2.0 Open Source an Editor holds `alert.rules:write` on `folders:*` from the role
  itself, so no folder permission keeps a rule out of a direct-login Editor's reach, while
  Grafana refuses a UI or API edit of a file-provisioned rule for every role. The heartbeat
  group is provisioned so already (`provenance: file`); a rule the ruler reports without it
  is a Needs attention row;
- **Prometheus's scrape targets, generated from the inventory beside the rules** (C229; the
  operator, 2026-09-30: agreed earlier and never written into this scope, which is how the
  connector classification came to claim it). Per network (P.8), as file-based service
  discovery on the Prometheus host, so a device onboarded is scraped and a retired one is
  not with nobody editing a file there. Tested the way the rules are: every inventory
  device has a target, every target names an inventory device, and a device Prometheus does
  not scrape is a Needs attention row;
- **every generated rule declares its REMEDY** (the operator, 2026-09-30), in the rule's own
  annotations (`description`, `runbook_url` where a manual page exists), written with the rule
  by its generator: the same principle as Needs attention's action field. The Alerts screen
  draws it as a "How to fix" column. A rule with no declared remedy says "no remedy declared
  for this rule", never an invented one, and the generator's test refuses a kind without one;
- **UNREACHABLE RESTS ON A LIGHT SIGNAL; A SLOW POLL IS ITS OWN, LOWER RULE** (the operator,
  2026-10-01, after s3's reboot): s3 answered SNMP the whole time, and `Device unreachable
  (SNMP)` fired because the `cisco_vios_l2` interface-table walk (`if_mib` + `cisco_old_cpu` +
  `system`) ran past its 30 s scrape timeout ("context deadline exceeded" at exactly 30.0 s),
  which reads `up == 0`. A slow walk is not unreachability. The generated reachability rule
  reads a light signal: the app's reachability probe (C92, ICMP then TCP 22) or a small SNMP
  get (`sysUpTime`), never the heaviest job's `up`. "A poll is timing out" is its own kind, at
  a lower severity, naming the job and its scrape duration against its timeout;
- the evidence it must reproduce (C168): the two incidents the old rules missed (09-22 23:41, every
  telemetry source silent for about 20 minutes; 09-28 08:51, r1 and r3), each rule's history read
  uncapped (a capped read made "never alerted" out of a rule that had).

**The rule P.7 exists to enforce (the operator): A RULE IS NOT VERIFIED BY EVALUATING WITHOUT ERROR.** Six of
the seven evaluated cleanly for weeks and three were wrong; the only thing that told them apart was asking
each rule's own question of its own datasource and comparing it with its own threshold. Its history is read
uncapped: a page that comes back full is truncated, and a capped read made `Device unreachable` (38 alerts
in 30 days) look silent and `Interface output discards` (229) look quiet. A rule that alerts about eight
times a day is a defect of its own, found only once the history was read whole.
**Alert VOLUME is part of whether a rule is correct, not only whether it can fire** (the operator,
2026-09-28): a rule that alerts about eight times a day is on the drift checker's road, noisy until
someone switches it off, and then off when it matters. Each generated rule states its expected rate,
and the host check reads its real one from uncapped history.

**Placement:** before 8.6, whose triage reader consumes these rules and is only as good as they are. Where it
falls against 7.2 and 7.3 is the operator's to decide; nothing in 7.2 depends on it.

#### Which conditions reach Needs attention: Grafana measures, two tiers (the operator, 2026-09-30)

**Grafana is where conditions are measured.** A condition that needs a person becomes a GRAFANA ALERT
RULE, generated here with its declared remedy, and the existing reader (`readers/grafana_alerts.py`)
puts it on Needs attention. **The app never infers an emergency from a panel's colour**: a dashboard's
thresholds are a guide for the eye, and a colour nobody turned into a rule alerts nobody.

**Alerts are never silenced** (the operator's rule, 15.3 of the brief), so a condition that is real,
known and not going away needs somewhere to be that is not a permanent alert. Two tiers:
- **ACUTE: something changed.** A full alert rule. Either the HARM itself (a neighbour dropped, an
  interface down that should be up, a stream stopped) or a sharp departure from the device's OWN
  normal (a CPU well above its measured baseline), never a fixed line one device sits over for ever.
  A rule that fires continuously on a stable state is a defect in the rule (P.7's volume check finds
  it), and the answer is a per-device threshold from the device's measured normal, the heartbeat
  windows' method, never an exemption.
- **CHRONIC: known, stable, long-standing, with its cause and fix recorded.** Shown ONCE, folded under
  the Needs attention one-liner ("1 long-standing issue"), each entry linked to its register finding
  and its fix plan, and GONE when the fix lands. **Chronic only on evidence, never by assumption**:
  the condition measured stable over days (the query and its band recorded with the entry), and its
  cause recorded in the register. An entry whose metric leaves its recorded band is no longer
  chronic: the change is acute, and the acute rule is what fires.
- **A chronic entry never suppresses, silences or edits an alert rule.** It is a separate row from a
  separate declaration. It hides nothing, because nothing it covers was ever alerting: the acute rule
  for that device is written so that the stable state does not cross it, by construction, and any
  change does.
- **Where it lives:** a declaration per network beside the register finding it cites (the finding's
  ID, the device, the query, the band, measured-since), read by a Needs attention source that
  re-asks the query each cycle: still in band draws the folded entry; out of band says so and points
  at the acute alert; the finding closed removes it. The first entry is s3's clock (below).

#### P.7's input: every threshold in nmas-device, classified (2026-09-30)

For every coloured threshold on the NMAS device dashboard: whether it becomes an alert rule (ACUTE), a
chronic entry, an Overview check on the device page, or stays on the dashboard only, and why. An
Overview check is a line on the device page's Overview judged by the app from the same query (step 4
of the redesign adds a Prometheus reader for it); it is a status to read, never a notice.

| Panel (dashboard threshold) | Becomes | Why |
|---|---|---|
| Answering SNMP (red when not answering) | **Alert**, and an Overview check | The harm itself. The existing `Device unreachable` rule, regenerated by the reachability kind with the expected set from the targets (a device that vanishes fires). |
| IOS CPU, 1-minute (amber 70%, red 90%) | **Alert on departure from the device's own normal**, sustained 10 min | A fixed line either never fires for a router idling at 5% that jumps to 60%, or fires for ever on a device whose normal is high (s3 reads 68% via SNMP). The colours stay fixed as a reader's guide. A device whose normal is high becomes a **chronic** entry only after days of evidence and a recorded cause (s3 is the candidate, under C93). |
| Memory used (amber 80%, red 90%) | **Alert** above 90% sustained 10 min, if the fleet's measured extreme sits below it | Growth is the harm (a leak), and memory has no benign fast swing. The crossing check reads the fleet's real extreme first; vIOS has no reading (staged run 6). |
| Interfaces down that should be up (red from 1) | **Alert**, and an Overview check | The harm itself. The existing `Interface down` rule reads a healthy network as no data (C168); regenerated with a count of zero as OK. |
| Routing neighbours in a wrong state (red from 1) | **Alert**, sustained 2 min (longer than OSPF's 40 s dead timer, so a convergence is not an alarm) | The harm itself, per protocol. TWO-WAY is correct on a broadcast segment and never counted wrong. **Gap to close in the generator:** the panel counts wrong states among the neighbours PRESENT, so a neighbour that vanished is not in it; the rule compares with the neighbours committed intent declares (C108's rule: the expectation comes from the target). |
| Critical syslog, last 24 h (red from 1) | **Alert** | The existing rule, regenerated to match the severity FIELD, never a mnemonic containing CRIT (C168). |
| Reboots detected (amber from 1) | **Acute warning alert**, once per reboot (`resets(sysUpTime[15m]) > 0`), and an Overview check "last reboot" | Something changed; it resolves by itself, so it cannot become noise. `resets()` counts reliably however slowly the clock runs. |
| Device clock rate (red below 50%, amber below 90%) | **Per-device alert** below the strictest protocol ratio the device runs, times 1.5; an **amber Overview check** below 90%; **s3 a chronic entry** | See the clock rule below. The dashboard's red is BGP's line with the margin (0.33 x 1.5 = 0.5), the strictest protocol in the fleet; the alert is per device. |
| Telemetry stream (amber 90 s, red 5 min) | **Per-device alert** after 5 min, for the devices whose committed configuration subscribes (the expected set, NoData = alerting, C168), and an Overview check | The harm is the stream stopping; the fold already hides the panel for a device that never subscribes, and the expected set keeps a vanished source from reading as resolved. |
| IP SLA operations failing (red from 1) | **Alert** | The harm itself; an existing kind. |
| LLDP neighbours (no colour) | **Candidate** alert on a fall below the device's own normal; not in the first cut | A lost physical neighbour is real, and mostly caught already by interface down; added once the crossing check shows the count stable. |
| Errors in and out (no colour) | **Alert** on a sustained error rate (above 0 for 10 min) per interface | Errors are normally zero, so any sustained rate is a change. **Discards stay dashboard-only** until measured quiet: the hand-built discards rule alerted 229 times in 30 days. |
| Traffic, IOS CPU over time, platform CPU, SNMP collection time, syslog by severity, interface flaps, up for | **Dashboard only** | Context for a person already looking. Platform CPU is the forwarding engine's busy-poll (high and flat is normal). A slow SNMP collection matters only when it fails, and then Answering SNMP fires. A flap's harm is caught by interface down and the neighbour rule. |

#### The clock rule, from protocol timers (the operator, 2026-09-30)

A device whose clock runs at rate r sends its hellos every hello/r real seconds, and its neighbour
declares it dead after its dead timer. So a protocol drops below r = hello / dead:

| Protocol (default timers) | Fails below |
|---|---|
| BGP (keepalive 60, hold 180) | 0.33 |
| OSPF (hello 10, dead 40) | 0.25 |
| RIP (update 30, invalid 180) | 0.17 |

Per device, the rule alerts when the clock rate falls below **the strictest ratio among the protocols
the device runs, times 1.5**, the timers read from its COMMITTED configuration with the defaults where
absent (C178's precedence for BGP's hold time). s3 runs OSPF only, so its line is 0.25 x 1.5, about
0.38, and **s3 at 0.58 is correctly NOT an alert**. It is the first **chronic** entry (C93, C9: stable
over the measurement, cause recorded) and reads amber on the Overview. A router running BGP alerts
below 0.5. A device running no routing protocol has no protocol line; its rate is an Overview check
only. The rate is `deriv(sysUpTime[1h]) / 100`, which needs an hour of history before it answers.

### P.8 — Per-list settings: two lists are two networks (SCOPED and DECIDED 2026-09-28, not built; after 7.2, before P.7's generators and 7.3)

**The design (2026-10-04, for the operator's decision):** [NSOT_P8_DESIGN](NSOT_P8_DESIGN.md)
re-measures the keys (143 now), adds the migration (none: the global file is Default's layer),
every reader it touches, how the OBSERVE screens and Grafana roles depend on it, a nine-step
build and five decisions with a recommendation each. The counts below are 2026-09-28's.
**All five DECIDED 2026-10-04 (the operator)** (the design's section 7); among them the URL
carries the network and is authoritative, which also decides CONCURRENCY_AUDIT R3. P.8 is
built after the current queue, from the design.

**DECIDED 2026-09-28 (the operator), closing every ambiguity below: 71 keys per
network, 47 global, 11 read by nothing, none ambiguous; and one per-list key
to add, the NetBox scope.**

**ADDED 2026-09-30 (the operator, from the GUI's services review; NSOT_GUI_BRIEF 14.2),
per network, each new:**
- `grafana_fleet_dashboard_uid`: the Monitoring page's default dashboard, by UID (Default:
  `rcn-lab-overview`). The page's selector changes the view, never this;
- `grafana_device_dashboard_uid` and `grafana_device_variable`: the device page's
  dashboard, by UID, and the template variable the app sets (Default: `nmas-device`,
  `device`; `rcn-lab1-snmp` was the original device dashboard, replaced 2026-09-30). They supersede `grafana_device_dashboard_url`, kept and read by nothing;
- `kea_writable_subnets`: the subnets where the tool may write reservations and pools, by
  family (the ZTP segment keeps D4's checks, and is never offered a pool);
- saved queries (PromQL and LogQL), per network, pinnable to a device page.
A configured dashboard UID that Grafana no longer holds is a Needs attention row naming the
setting and the UID, never a blank panel.

**CORRECTED the same day (the operator): the NetBox CONNECTION is global, the
SCOPE is per list.** "One NetBox per network" answered the instance question,
while every list lives in ONE NetBox separated by region, which is how the
sync already behaves (`_ensure_region` and `_ensure_site`, one pair per list).
- **Global: the connection.** `netbox_url`, `netbox_token`, `netbox_verify_tls`
  and `netbox_auth_scheme`, beside `netbox_allow_writes`.
- **Per list: the scope,** which region (or, later, tenant) a list's objects
  belong to. It is DERIVED from the list's name today, and becomes a per-list
  key (`netbox_scope`, default the derived value), so a later tenant move
  changes a value rather than every writer.
- **The platform and role maps are GLOBAL, measured.** Both are keyed on
  NetBox's own platform and role slugs, instance-level objects every region
  shares, and map them to NMAS's vocabulary (driver, template directory,
  transport, device kind): a fixed vocabulary for the instance, and
  `platform_default_netmiko_type` with them. **One field inside
  `platform_map` is not**: `prometheus_cpu_query` belongs to a monitoring
  stack, and duplicates the per-network `promql_cpu`, two owners of one fact.
  P.8 moves it to the per-list store.
- **`netbox_excluded_vrfs` stays per network**: it names a lab's emulator
  VRF, and another lab names it differently.
- The per-instance question (a NetBox per network) is deferred with the
  tenant question (C174).

The first form of this decision, kept as the record of what changed:
- **One NetBox per network.** Sites, devices, interfaces, addresses, VLANs and
  prefixes are facts about a network, not about NMAS. A shared NetBox would put
  list B's devices in list A's source of truth, while the provenance record of
  what NMAS created for which list is already per list. So the five NetBox
  connection keys and the three platform and role maps are per network.
  **`netbox_allow_writes` stays GLOBAL**: a safety switch for the NMAS process,
  not a property of a network. Nothing changes today (one NetBox, one list,
  Default points at it), which is the right time to decide it.
- **Proxmox: GLOBAL.** It holds NMAS's own backups and VMs. A second lab on a
  second Proxmox host is a per-list override of a global default, which the
  inheritance model already supports.
- **Deploy tuning: PER NETWORK.** The settle windows were measured on this
  fleet, and another fleet converges differently: C92's reasoning for a probe
  threshold.
- **The collectors: PER NETWORK, and `collector_config.json` folds into the
  store.** The split was half done (ports per list, on/off switches global);
  finishing it in the same direction beats two mechanisms.
- **`settings_not_applicable`: per list.**
- **The group rule is a SECURITY PROPERTY, and is stated as one**: an
  integration inherits as a group, never key by key, so a list with its own
  URL cannot quietly inherit Default's credential, and NMAS never sends one
  service's credential to another. It gets its own test, with a control that
  inherits key by key and is shown sending Default's token to the list's URL.
- **"Deliberately none" never inherits**: C31's distinction carried into the
  new store, four states per key, not two.
- **Placement: after 7.2, before P.7 and 7.3**, on the correctness argument: a
  screen built on global settings shows list A's Grafana beside list B's device
  WITH EVERY CHECK PASSING. Rework is recoverable; a screen that lies with its
  checks green is not something a later refactor finds.

**The gap (the operator, 2026-09-28): lists separate devices, and settings are
global.** Every list is meant to be its own network, and the settings that
describe a network and the systems watching it are one flat store. It already
shows: the readers built in 7.2 store per-list values (freshness, drift) while
reading global settings for the services they talk to. Only one list exists, so
nothing is broken; two labs on one NMAS would share one Grafana view, one
scrape list and one Oxidized. Register C173.

**1. Every schema key classified, from what READS it** (129 keys, measured
2026-09-28 by listing each key's readers, not by its name):

- **Global, 32: NMAS itself and who may use it.**
  - The process: `flask_host`, `flask_port`, `auto_open_browser`.
  - Identity and authority: `cf_access_*` (5), `require_identity_for_*` (6),
    `require_person_for_*` (6), `service_allowed_operations`.
  - The agent: `ai_enabled`, `background_agent_enabled`, and `wf_*` (5 live).
  - The repositories' commit identity: `nsot_git_author_name`,
    `nsot_git_author_email`.
  - The host path `tftp_root`, and the store's own `settings_schema_version`.
- **Per network, 61: a network or a system watching it.**
  - Grafana (5), Prometheus (6), Loki (7), Oxidized (6 live), the topology
    service (4), Kea (7, including the ZTP fragment), the clab target (6).
  - The onboarding syslog block (`syslog_*`, 5): where a device sends its log
    and heartbeat.
  - The device to monitoring identity mapping (`monitoring_*`, 4; `promql_*`, 3).
  - `tftp_server_ip`: the address a network's devices fetch from; `tftp_root`
    is the host's directory, global.
  - The S3 archive (7): each list's repository already has its own remote, so
    its archive is its own too.
- **Ambiguous, 25, each with the question that decides it.**
  - **NetBox (6).** One NetBox holding every network as sites, or one per
    network? The inventory adapter, the import and `netbox_allow_writes` (a
    master switch, a safety decision about the instance, which argues global)
    all hang on it.
  - **`platform_map`, `platform_default_netmiko_type`, `role_map` (3).** Mapping
    NetBox's names to NMAS's: per NetBox, so they follow NetBox's answer.
  - **Proxmox (7).** The host the lab and NMAS run on: global today, per
    network if a second lab runs on a second Proxmox.
  - **Deploy tuning (5)**: `deploy_max_workers`, `deploy_verify_failure_limit`,
    `nsot_config_read_timeout`, `verify_settle_windows`,
    `nsot_device_tag_retention`. A property of the tool, or of the network's
    size and protocols? Settle windows are measured per protocol on THIS
    fleet, which argues per network.
  - **The collectors (3)**, `collector_*_enabled`. NMAS's own listeners, one
    process on one host (global), while the ports already live per list in
    `collector_config.json`: a split that exists and is half-done.
  - **`settings_not_applicable` (1).** A declaration about a key. If keys are
    per list, so are declarations (question 4 below).
- **Read by nothing, 11**: `jenkins_step_shell`, `wf_run_jenkins`,
  `netbox_remove_on_list_delete` (retired, C155), `oxidized_rest_url`
  (deprecated), `yang_push_script` (C31), and the six Phase 0 `nsot_git_*`
  location keys (C171). They need no split, only retirement (C171, 7.7).

**2. What already assumes global** (measured):

- **Readers.**
  - Grafana alerts: global Grafana, an unscoped value, and Needs attention
    resolves each alert against the ACTIVE list. With two lists, an alert for
    the other list's device would read "NOT in the inventory (a rule left
    behind by a device that left)". That is a false claim, latent today.
  - Freshness: per-list reports from one global Oxidized.
  - Integration health: global probes, one status bar for every list.
  - Job health and the CI verdict: genuinely global (the host and NMAS).
- **Needs attention sources.** Drift and freshness take the active list;
  Grafana and integrations are unscoped.
- **Integration clients.** All ten read the global store (the base class reads
  the URL and keys itself), and none can be given a list.
- **Call sites.** 69 name a per-network key, in 24 files; that undercounts,
  because the base class reads its keys generically.
- **Outside NMAS.**
  - Prometheus's scrape targets: hand-kept, C168.
  - The Grafana heartbeat rules: generated from NetBox for every device, with
    no list label.
  - The SNMP exporter's auths and `snmptrapd`: C139's consumers.
  - Oxidized's one `router.db`.
  - The Kea ZTP fragment and responder: one subnet for every list's ZTP
    devices.
- **Per-list configuration that already exists**, each file its own mechanism:
  - `source.json`;
  - `remote.json`, with C172's defects;
  - `collector_config.json`;
  - `drift_state.json`;
  - the clab lab through the manifest.

  A second store needs a second mechanism, and this is five. P.8's store should
  be the ONE per-list mechanism, and absorb them rather than add a sixth.

**3. Blocking, or can it follow?** Not blocking: one list exists and nothing
is wrong today. The honest costs:

- **Now.** The mechanism, before any more consumers are built on the global
  store:
  - a resolver `list_setting(list_name, key)` and a per-list store (filestore,
    0600, secrets through the secrets store per list);
  - inheritance and its states (question 4), and the origin drawn beside every
    value, as the posture panel already does;
  - integration clients constructed FOR a list (the base class takes one), and
    the 69 call sites carrying their list ("carried, never derived" on a WRITE;
    a read may derive the active list);
  - three readers looping lists, the unscoped sources scoped, and the status
    bar drawing the active list's integrations.

  From finished items of similar shape (C104's readers, C158's write sites,
  each a cross-cutting pass over one property), expect about 10 to 15 commits,
  and about as many register rows as commits (7.1's measured rate).
- **Later.** Every consumer built on the global store in the meantime is
  revisited, and the cost grows with each screen. 7.3's Device page embeds
  Grafana and Loki per device and is the largest single consumer of
  per-network monitoring settings. P.7's generators would emit rules and
  targets with no list label.

  The worse cost is not the rework. **A screen built global shows list A's
  Grafana beside list B's device with every check passing**: the wrong thing
  looking like the working thing, which is what this project exists not to
  build.

**4. What inheritance means.** "Unset inherits Default" collides with the
distinction C31 already made between nobody-decided and deliberately-none.
Four states per (list, key):
- **set here**: the list's own value;
- **not applicable here**: declared, with who, when and why. It stops the
  lookup: it NEVER inherits Default's value, because the list deliberately has
  none;
- **inherited**: unset here, so Default's value, drawn as inherited from
  Default;
- **unset everywhere**: the schema default, where an empty guard-gating value
  is job health's `unset_guard` for that list.

Two rules follow, and neither is the obvious one:
- **A declaration never inherits.** Default saying "we deliberately have no
  Grafana" is a fact about Default's network, not B's. B inheriting it would
  turn nobody-decided into somebody-decided, the distinction C31 exists to
  keep.
- **An integration inherits as a GROUP, never key by key.** URL, auth mode,
  credential and TLS belong together. A list that sets its own Grafana URL
  must not silently inherit Default's token, or NMAS sends one service's
  credential to another. Setting any key of a group here makes the group
  local, and the rest of it reads unset here, never Default's.

`settings_not_applicable` becomes per list with the store, and job health
judges each list's guards against its own resolved values.

**Where it goes (recommended): after 7.2 finishes (the "who you are" item and
C92's reader, neither of which reads a per-network setting), and before P.7's
generators and 7.3.** Both of those are built ON this split. P.7 generates
per-list rules and targets, and 7.3 embeds per-list monitoring. The
NetBox question in (1) is the operator's to answer first, because six keys and
the inventory adapter move with it.

### P.9 — The monitoring profile (DESIGNED and DECIDED 2026-09-30; steps (a) and (b) BUILT the same day; (c) onboarding and adopt BUILT 2026-10-01; NEXT: (d))

The operator's requirement (2026-09-30), after r6 was called "unreachable" by an SNMP alert
when its configuration simply has no SNMP: every device, new and existing, carries what its
integrations need, derived from the connectors the network uses, with ONE owner. The design is
[MONITORING_PROFILE.md](MONITORING_PROFILE.md):

- **The model:** one committed profile per network (`config_repo/profiles/monitoring.yml`),
  data in the parsers' `host_vars` shape, rendered by the platform templates. Each section is
  derived from a connector and absent without it. Secrets are references, with the profile's
  values under a profile-scoped key.
- **Inheritance:** effective intent is the profile overlaid by the device's own intent, through
  one function every reader calls. An override is drawn; an exclusion carries a reason; a value
  equal to the profile's is dropped at seed and extraction (one owner). C216 is subsumed, and
  onboarding's own block merge is removed.
- **New devices:** applied in onboarding's phase 2 over SSH, before the first capture, so the
  first golden records it; Verify becomes a preview and a confirm. The same step goes into adopt.
  Never in the bootstrap.
- **Existing devices:** "Apply monitoring profile", a deploy scoped to the `from_profile` lines.
  Its preview groups inherited, already in place, and superseded lines, and each superseded line
  can be removed through Mode B with its reason. A fleet Coverage page runs it as a batch.
- **IP SLA:** a policy in the profile (gateway, peers, none); operations are suggested from the
  device's own facts and committed into its intent.
- **Order, proposed:** (a) the model, (b) existing devices with r6 first, (c) new devices,
  (d) the screens inside step 4. It needs P.8 only for the connector settings to be per network.
- **Step (a) BUILT 2026-09-30:** `modules/nsot/profile.py` (the document, its reader at HEAD and at a ref, its one commit, the one merge `effective()`, overrides, one owner at seed `strip_inherited()`, the profile-scoped secret), wired into the deploy plan and apply, the plan's attribution (`from_profile`, drawn apart in the preview), `intent_match`, the intent editor, bulk intent and restore validation (the profile as at the ref). A scan requires every render of intent to merge the profile. Acceptance on r2's real intent: a profile holding what the device holds changes no plan; a line it supplies and the device lacks is sent and attributed to the profile. Not yet: the proposal from connectors, seed calling `strip_inherited`, and the screens.
- **Step (b) BUILT 2026-09-30, awaiting the operator's run on r6:**
  - **PROPOSE** (`modules/nsot/profile_propose.py`; routes `/templatize/profile/propose/preview`
    and `/apply`; client `static/js/nmas_profile.js`): a profile derived from what the fleet's
    committed intent agrees on.
    - A section is proposed only where its connector is configured.
    - Two versions are never reconciled by the tool: each is named with its devices.
    - A secret must be one value across the holders, compared in memory and never shown.
    - The proposal is confirmed by hash and committed as the verified person
      (`Source: profile`).
    - The result's next step opens the apply for the devices that inherit.
    - `GET /templatize/profile` reads the record back.
  - **APPLY** (`/deploy/plan` and `/deploy/apply` with `scope: profile`,
    `modules/nsot/profile_apply.py`): the deploy scoped to the profile's lines.
    - The preview groups what each section sends, what is already in place, what the
      device's own intent would add and this holds back, and what it supersedes (removable
      through Mode B with a reason).
    - The scope is recomputed at apply and on the path that connects.
  - **Needs attention:** the "not monitored" row's action is Apply where the profile covers
    the gap, else Propose; an excluded section is no row.
  - **Found by its own tests:** the proposal's effect called a section a device already held
    "gained". Fixed: only a section its own intent lacks is inherited.
  - **Found by the operator's review (C253):** LLDP and CDP were reported held by no device
    while eight held them; the detector read a key no parser writes. Fixed, with every
    detector now held to the real fleet's intent, and the platform defaults (C254) recorded
    as not measured until the operator's probe reads them.
  - **The operator's acceptance on the host:**
    1. Propose on the lab's network;
    2. Apply to r6 from its row;
    3. r6's SNMP warning clears once its next golden carries SNMP, and it becomes a
       Prometheus target.
  - r6's intent is still never hand-edited.
- **Step (c), onboarding, BUILT 2026-10-01** (MONITORING_PROFILE.md section 2): Verify is a
  preview (`POST /onboard/verify/<host>/preview`, `onboard.phase_two_plan`) and a confirm by
  fingerprint. The profile's program is computed from the device's CAPTURE
  (`profile_apply.for_capture`), sent as phase 2's `profile` step after the RW removal and
  before the save and the first golden, and read back. A device or profile that moved since the
  preview sends nothing at all. Adopt applies it the same way: computed from the capture its
  preview reads, in its program and fingerprint, sent as the apply's `profile` step after the
  accounts and before the save, read back. (d), the batch Apply from the coverage view, is next.
- **Step (d), the screens, BEGUN 2026-10-01** (MONITORING_PROFILE.md section 2): (d1)
  Monitoring > Coverage in v2, its cells from committed goldens and its form opening the batch
  preview for the ticked devices, BUILT. (d2) the batch preview, confirm and result in v2,
  drawn server-side from the six-part contract (today's renderer emits inline handlers, which
  v2's strict policy refuses), with the rollout order: **BUILT 2026-10-01**
  (`/v2/monitoring/apply`; MONITORING_PROFILE.md section 2), the plan and the apply extracted from
  the JSON views as `plan_devices` and `apply_batch` so both screens run one computation, the
  batch a job (`modules/deploy_job.py`) in the order the page set. (d3) the device page's
  "monitored by" section and its Apply: **BUILT 2026-10-01** (the Monitoring tab opens with
  Coverage's cells for the device alone, and "Apply monitoring profile…" opens the same preview
  for it). Next: (d4), the IP SLA policy, after staged run 9.
  - **The operator's review of (d1), 2026-10-01:** Monitoring opens on the FLEET dashboard
    (`grafana_fleet_dashboard_uid`; `rcn-lab-overview` for Default), every panel drawn by the
    device page's own renderer, the selector over every dashboard Grafana holds, and Coverage a
    tab beside it (`/v2/monitoring`, `/v2/monitoring/coverage`). Every cell says why in a
    person's words ("not applicable — vIOS doesn't support model-driven telemetry"; IP SLA "no
    probes configured — IP SLA targets are chosen per device; set a policy to add them").
  - **(d4) The IP SLA policy, placed here (decision 5):** the profile's `ip_sla` section holds
    a policy (probe the default gateway, probe the routing peers, or nothing); the tool SUGGESTS
    each device's targets from its committed configuration (the default route's next hop; the
    BGP neighbours and the far end of its routed point-to-point links), previewed per device and
    committed to that device's OWN intent, where the operator reviews them before any apply.
    After (d2), because its review and commit are the v2 preview-and-confirm component (d2)
    builds. Every device here supports IP SLA: probes were configured by hand on r1 to r4 and
    s3, and nobody chose targets for the others.
    **The ADD path is BUILT (2026-10-01; MONITORING_PROFILE.md section 6, "Built")**: the
    operator split adding from changing, so (d4) did not wait on run 9 for a NEW probe. The
    policy set on Monitoring > IP SLA, the suggestions (60 s by default; a switch's path placed
    on the router; a path already measured skipped; each with its expected CPU cost), one
    intent commit, then the batch Apply scoped to IP SLA lines (scope `ip_sla`). **Changing a
    running probe still waits on staged run 9** (the re-create, C290), and so does s3's probe
    to r1: r1 already probes s3 (`ip sla 2`), so the recommendation is to REMOVE s3's rather
    than slow it, which is the same delete run 9 measures.
- **Next, from the operator's r6 run (2026-09-30):**
  - **The connectors are the PRIMARY source** (the design's own words, which (b) did not
    follow: it proposed only what the fleet already agrees on, which is circular on a network
    the tool has never seen). Each section is derived from its connector's setting (syslog
    from Loki, SNMP from what the exporter expects, telemetry from the Telegraf endpoint, NTP
    from its setting, the heartbeat from its alert rules); fleet agreement becomes the
    CROSS-CHECK that names devices configured differently. Then Apply is one confirmed deploy
    per device, or a batch from the coverage view, and adopt applies it. **The derivation is
    BUILT (2026-09-30):** `connector_value()`, five new settings (`ntp_servers`,
    `telemetry_receiver`, `snmp_trap_host`, `snmp_exporter_config`, `snmp_exporter_auth`),
    and the cross-check drawn in the preview (MONITORING_PROFILE.md section 2). The batch
    from the coverage view is (d); adopt and onboarding are (c).
  - **The SNMP section's next change is SNMPv3** (Stage 9's (L) item, designed there).
  - **`ip domain name`** is a shared field, in a section of its own outside monitoring and
    never applied by "Apply monitoring profile": on IOS the SSH key's default label is the
    host's full name, so a change rides the path the tool reaches the device on. Measured per
    platform before it is proposed.
- **Built ahead of it, 2026-09-30:** a device is an SNMP target only when its committed golden
  configures SNMP, and a device missing an integration the network uses is a Needs attention row
  (`modules/monitoring_coverage.py`) whose action names this item. r6's intent is not hand-edited
  before the profile exists.

### P.10 — Validation before production, in layers (SCOPED 2026-09-30, the operator; NOT BUILT, placed after Stage 7)

**The goal (the operator's):** a change is validated before it reaches production, in
layers, and the pipeline learns from anything that slips through, so it never makes the
same mistake twice. The same program hash runs through every layer and then production,
so the change that passed validation is the change deployed (the confirm hash's rule,
extended). Post-deploy verify and rollback stay the last line.

**Why not a full test network, yet (measured by the operator, 2026-09-30):**
- The clab VM keeps about 17 of its 24 vCPUs busy.
- The host (2 x E5-2650 v3, 20 physical cores, 40 threads) sits at load about 18, with 75
  of 126 GiB RAM used.
- A permanent 1:1 twin would saturate every physical core and degrade production. s3's
  slow clock (C9) and the connect timeouts (C205) are contention already. It would also
  make the twin's own verify timings unreliable.

CPU, not RAM, is the limit. The full and the partial replica are recorded as LATER options
(below); **the hardware route is E5 v4 CPUs, which fit this socket**, and would make a
permanent twin realistic.

**Layer 1: a platform lint catalogue.** Rules built from MEASURED device behaviour, keyed
by platform. Each rule cites the captured device output that proves it, and all of them
run on every program before it is sent. **One catalogue gathered from where they are
scattered today, never duplicated:**

| Rule | Where it is today | Scope today |
|---|---|---|
| Printable ASCII, comments included | `deploy.assert_sendable` (modules/nsot/deploy.py) and `bootstrap_config` | the deploy path and the bootstrap |
| A user cannot hold both `password` and `secret` on IOS-XE (`%CVAC-4-CLI_FAILURE`) | `credential_rotation.verify_startup_applies` | the startup-applies check only: EXTEND to the deploy path |
| `ip domain name` (IOS-XE 17.6) against `ip domain-name` (vIOS 15.x) | `bootstrap_config` (lines 83 to 93, measured in stage C) | the bootstrap generator only |
| IOS's bare `ERROR:` and `% Invalid` refusal formats | `pipeline.IOS_ERROR_PATTERN` | push error detection |
| Removals that do more than they say | Mode B's `removal_measured.json` | removals only |
| Dangerous lines, credentials unchanged, merge-only | `deploy.dangerous_in`, `assert_credentials_unchanged`, `assert_merge_only` | the deploy path |

Candidates, each added only once MEASURED:
- **Order dependencies:** the domain name before key generation, and an SNMP view before
  the community that uses it.
- **Hidden side effects:** `vrf forwarding` silently deleting an interface's address;
  switchport changes; an OSPF process-ID change.
- **Commands that prompt.**
- **Management-path safety for ADDITIONS as well as removals:** an ACL added to the vty
  lines or to the management interface. Removals are checked today, in removal.py.

Two rules for the catalogue:
- A rule is trusted only once it has been shown failing on the thing it is meant to catch.
- Refusing by resemblance is safe; allowing by resemblance is not.

**Layer 2: a parser sandbox.** One spare C8000v and one spare vIOS, with no topology.
Before production, the exact program is sent to the matching spare, to learn whether IOS
accepts it. It catches the quirks nobody has written a rule for yet. Two nodes, so it can
run permanently or on demand. **First measurement: its CPU cost on the host**, one boot
and idle of each; the C8000v's boot was the lab's heaviest single cost in stage B.

**Layer 3: Batfish.** A config-level digital twin: whether OSPF and BGP adjacencies still
form, what each routing table would hold, and whether flows are still permitted, without
booting devices. Every Deploy plan is checked against it, with network invariants ("s1
can reach r4", "r3 keeps its eBGP session to r5"). **First measurement: how well Batfish
parses these IOS-XE and vIOS-L2 configs.** Its coverage of the fleet's constructs is
measured read-only on the laptop against the committed goldens: nothing is installed on
the lab host, and no device is involved.

**The learning loop is Stage 8 (8.9)**, since it needs the assistant calling tools, which
has never happened, and the layers above to exist.

**Later options, recorded with the measurement above:**
- a partial replica: the sites a change touches, booted on demand;
- a full permanent twin, after the CPU upgrade.

**Dependencies:**
- The deploy receipts (C60), to measure false positives against past programs.
- P.9, so validated programs include the inherited lines.
- Stage 7's preview component, where each layer's verdict is drawn as a gate.

**Placement, proposed:** after Stage 7, before Stage 8.
- **Layer 1 first:** mostly gathering what exists, and it tightens the deploy path at once.
- **Batfish's parse-coverage measurement** can run any time, since it is read-only.
- **Its build follows the lint.**
- **The sandbox last:** it waits on the CPU measurement and the operator's decision on
  capacity.

**Also used by Stage 10's multi-vendor item** ([NSOT_STAGE10_PLAN.md](NSOT_STAGE10_PLAN.md)
section 12). A new platform's WRITE capabilities (deploy, removal, rotation, bootstrap,
persist) are enabled only after they are measured on a sandbox device of that platform. The
second vendor's write tier and the assistant's pipeline (8.10) both wait on the sandbox.
- A container platform (Arista cEOS) is far cheaper to hold as a sandbox than another VM on
  this CPU-bound host, which is part of why it is recommended as the second vendor.

### P.11 — Topology: a page of its own, NetworkX for analysis, the app for drawing (SCOPED 2026-09-30, the operator; NOT BUILT)

**The brief (2026-10-04, for sign-off):** [NSOT_TOPOLOGY_BRIEF](NSOT_TOPOLOGY_BRIEF.md) answers
the research's open questions ([NSOT_TOPOLOGY_RESEARCH](NSOT_TOPOLOGY_RESEARCH.md), section 7)
with a recommendation each; its mockups are the canvas page "P.11 Topology" (desktop, phone,
wall). Nothing is built until both are signed off.

**The operator's requirement (2026-09-30).** NetworkX is used today to draw a static
picture, and drawing is its weakest part. Its strength is analysis. So it computes on the
server, and the app draws the map natively. **Topology is its OWN sidebar destination under
OBSERVE** (with Monitoring, Logs and DHCP), never a tab of Monitoring. Monitoring answers
"how is it performing"; Topology answers "how is it connected, what depends on what, where
is the weak point, how do I get from A to B". The map needs the whole screen, with its own
controls, and must stay usable on a phone. It is also a starting point for navigation:
people open it to find a device and go to it. This supersedes the "native interactive map on
the Monitoring page" of NSOT_GUI_BRIEF 14.2.

**Where the graph data comes from TODAY (measured 2026-09-30):**
- **Physical links:** Prometheus's LLDP-MIB series (`lldpRemEntry`, `lldpRemPortId`),
  scraped by the `lldp` job from the GENERATED targets (C232: every device whose golden
  configures SNMP). 18 rows over 8 devices, no device read.
- **One-sided reports are normal and are information:** s1 and s2 report only each other,
  while r1 reports s1 and r2 reports s2. So a link is the UNION of both ends' reports, and a
  link only one end reports is drawn as such.
- **State:** `up` per target job; `sysName`.
- **Routing:** the `ospf`, `ospfv3` and `bgp` jobs already scrape OSPF-MIB's neighbour
  table, OSPFV3-MIB and `cbgpPeer2Table` (staged run 5's modules). No new collection is
  needed for the layers.
- **Link facts:** `ifOperStatus`, `ifHighSpeed` and the octet counters (SNMP), and the
  telemetry stream where a device streams.
- **Intended topology:** NetBox's cables, from the import.
- **Who draws it today:** the topology service, `rcn-topology.py` (C256: an external script
  until 2026-09-30, now `deploy/topology/`). It reads the LLDP series, builds a NetworkX
  graph and serves an SVG and `graph.json`. The app fetches the SVG (`routes/topology_view.py`).
  The legacy Topology tab's `modules/topology.py` is a SECOND discovery, over SSH (CDP,
  OSPF, BGP, DMVPN); P.11 retires it (one home, section 6a).

**The architecture:**
- **ONE reader job** (`readers/topology_graph.py`, the 7.2 pattern, 60 s) reads the
  Prometheus series above and NetBox's cables. It builds one graph per layer and computes
  the analyses on the server with NetworkX. It stores the result with the time of its value
  and announces `topology` only on a change.
- **The routes serve the stored value**, never compute per request (plan §0a).
- **The page draws it** with vis-network (already vendored and hash-pinned), with positions
  pinned by node id so the map does not rearrange on every refresh.
- **The population is the inventory** (the drift checker's lesson):
  - a managed device the graph lacks is drawn apart, saying why ("not polled: its golden
    configures no SNMP", "no LLDP neighbours — not directly connected to any other managed
    device");
  - a graph node that is not managed (r5, retired) is drawn muted and labelled "not managed".
- **NetworkX joins `requirements.lock`** (the host has 3.6.1 from apt, read-only check).
- **The topology service stops drawing.** Once the page is built, the service, its SVG, the
  Grafana text panel and C231's public hostname go: one owner of discovery (the generated
  scrape) and one owner of the graph (the reader).

**What it shows, each with its cost** (small: a function and a renderer; moderate: a reader
or a store and a screen; large: a new collection or a new decision):

| Feature | How | Cost |
|---|---|---|
| **Layers**: physical (LLDP), OSPF, OSPFv3, BGP, switchable or overlaid | one graph per layer from the scraped tables; a layer mismatch (OSPF neighbours with no physical link, a link carrying no adjacency it should) drawn as its own state | moderate |
| **Each link**: both interfaces, speed, state, live traffic | `ifOperStatus`, `ifHighSpeed` and the rate of the octet counters, joined by `ifIndex`; telemetry primary where it measures the same thing (the device dashboard's rule) | moderate |
| **Islands**: disconnected components, labelled | `connected_components`; every component but the largest is an island, each with its reason (the rule C256 already ships in the service) | small |
| **Single points of failure** | `articulation_points` and `bridges`, highlighted | small |
| **Redundancy between two devices** | `local_node_connectivity` (independent paths); 1 reads "one failure from losing contact" | small |
| **Path trace**: two devices, hop by hop, with interfaces | `shortest_path` on the chosen layer, each hop's ports from the edge; on the routing layer it is the routing protocol's view, never a forwarding claim (*transit in the database is not transit in the forwarding table*) | small |
| **Criticality**: rank by how much must pass through a device | `betweenness_centrality`, measured at 900 devices with the scale fixture before it runs every 60 s (it is O(VE)) | small, plus that measurement |
| **Topology drift**: intended (NetBox cables) against observed (LLDP) | missing link, unexpected link, cable on the wrong port; surfaced like config drift, a Needs attention row with its action | moderate |
| **Change over time** | a snapshot per CHANGE (not per run), kept like the reader's value; a diff of two snapshots: links that appeared or went | moderate |
| **What-if impact in the deploy preview** | for a program that shuts an interface or removes a routing adjacency (a dangerous line, a Mode B removal), remove the edge from the graph and compute which managed devices lose their path to the MANAGER (its attachment point, s3's Vlan99 today); drawn as a gate, linking to Topology | moderate; ties into P.10's layer 1 |

**One home, several entry points, never a second copy of the map:**
- the Device page's **Neighbours** tab draws a small local view (the device and its direct
  neighbours, `ego_graph` radius 1) with "Open in Topology", centred on the device;
- an **alert** opens Topology with the affected device highlighted, and what is downstream
  of it (the devices whose only path to the manager crosses it);
- the deploy preview's **what-if** links to Topology showing which devices would lose their
  path.

**On a phone:** pan and pinch-zoom; under a set width the default is the list form (each
device with its links), because a full graph at 390 px is decoration. Path trace is a list
of hops.

**What it cannot see, stated on the page:** LLDP sees only directly connected neighbours that
speak LLDP. A device with LLDP off, or a link through a bridge that drops LLDP (r6's
management segment, deliberately), is not a link in the physical layer.

**Placement, proposed:**
- The page, the layers, islands, single points of failure, redundancy, path trace and
  criticality are ONE build, a screen of the redesign's step 4 with the other OBSERVE
  screens (after P.8, NSOT_GUI_BRIEF 14).
- Topology drift and change over time follow it.
- The what-if gate waits on P.10's layer 1, where it belongs.
- Nothing here waits on a new collection: every series is already scraped.

### P.12 — Feature templates: intent, template, verify, removals and risk as one unit (SCOPED 2026-10-01, the operator; NOT BUILT)

**The operator's requirement (2026-10-01).** The templates grow into FEATURES. Each feature is
one bundle of: its section of intent (the `host_vars` keys it owns), its template per platform,
its verify checks, its measured removal shapes, and its risk class. That bundle is what makes a
deploy and its verify scopable ("deploy only OSPF to r3"; an OSPF change runs OSPF's checks and
nothing else). It lets a feature be applied to a group of devices, and it is the natural unit
for multi-vendor drivers (9.P, Stage 10). **The monitoring profile (P.9) is effectively the
first one**: its own section, its own scope on the deploy (`scope: profile`, `ip_sla`), its own
proposal and apply.

**Granularity: about a dozen meaningful features, never hundreds.** A first cut, from what the
parsers already model: base (hostname, domain, services, flags); users and enable; lines
(console, aux, vty); management access (SSH, HTTP, NETCONF/RESTCONF); interfaces; VLANs and
switching; static routes; OSPF/OSPFv3; BGP; RIP/RIPng; ACLs and prefix lists; monitoring (SNMP,
syslog, NTP, telemetry, LLDP/CDP, IP SLA: the profile); FHRP (VRRP). The exact list is decided
against the fleet's real intent when built, by the same rule as modelling (2+ devices, or a
protocol in the design).

**Risk class drives verify** (this round's item 2, built first, without waiting for P.12): a
management-only feature (lines, users, logging, SNMP, NTP, banners) gets the quick verify; one
that can affect forwarding or routing (interfaces, ACLs used on interfaces, route maps, prefix
lists, VRFs, routing processes) keeps the full settle window. Unknown is full.

**Cross-feature references, with an explicit order.** An ACL is used by the vty lines and by
SNMP; OSPF runs on interfaces; a prefix list is used by BGP. Each feature declares what it
references and what references it. A scoped deploy of one feature REFUSES, naming the other
feature, when its program needs a line another feature owns (an SNMP ACL that does not exist
yet). The render order is fixed per platform (objects before their users), so the program a
scoped deploy sends is the same lines, in the same order, as the whole-device program would.

**The whole device still combines into ONE exact config.** Template fidelity (`template_report`),
the golden-versus-intent comparison and the replace-with-a-golden operation (decided 2026-10-01,
measured before allowed) all need the complete file. A feature is a scope over the one render,
never a second render. One template closure per platform stays the approval unit (P.5), or each
feature's closure is approved, decided when built.

**Placement:** after 7.3 and P.9 (d), alongside 9.P's platform layer, since a feature's per-platform
template and its measured removals ARE platform capabilities. Before Stage 10's drivers, which
consume it.

### P.13 — Software image management (DECIDED 2026-10-02, the operator; NOT BUILT; placed after Stage 7, before Stage 10's drivers)

**Why.** The generic file actions (upload, download, delete, TFTP browsing, on the device page
and the bulk selection) are removed (docs/CUTOVER.md): no arbitrary file transfer. Devices
still need files for two purposes, and each gets a purpose-built operation. ZTP delivery is
onboarding's own (P.6's responder serves a pending device its config, rendered per request).
Software images are this item.
- **An image library**: the approved images, each with its checksum, its platform and model,
  and who approved it. An image not in the library is never sent.
- **Transfer**: an operation (preview, confirm, result, record). It checks the device's free
  space first, copies the image, then verifies it ON THE DEVICE (`verify /md5` against the
  library's checksum). A copy that does not verify is removed and reported.
- **Upgrade**: sets the boot variable to a verified image, then reloads through P.14's
  gates.
- **Platform capabilities, like everything else**: how a platform copies, verifies and sets
  its boot image is declared per platform, measured on the lab's platforms first; a platform
  that declares none is refused, naming it.

### P.14 — Reload, as a gated device-page operation (DECIDED 2026-10-02, the operator; NOT BUILT; one of 7.3's device actions)

Reload stays, as an operation on the device page, offered only once its gates pass. Each
gate is drawn by name with what it found:
1. **Running against startup**: unsaved changes REFUSE the reload, or offer a save first
   (Persist, previewed). Nothing in running is lost.
2. **Running against the golden and against intent**: drift is shown, and must be resolved or
   acknowledged with a stated reason.
3. **The startup configuration carries the credential the tool holds** (the startup check).
4. **The boot image exists, and the boot variable points at it.**
5. **No operation holds the device.**
6. **BLAST RADIUS, shown prominently**: what else loses reachability while the device is down,
   from the management path and the topology (rebooting s3 cuts off everything behind it).

Then: a stated reason, the confirm, the reload (send, read, decide: C153), a wait bounded by
the device's measured boot times, and the checks that it is back: answering, its
configuration equal to its golden, its routing settled (verify's settle windows). Recorded
with the reason and who. Admin-only once Stage 9 has roles. The bulk reload (`/bulk_reload`) is
removed with the bulk file actions.

### P.15 — Several people at once: every write path safe across users, tabs and processes (DECIDED 2026-10-02, the operator; AUDIT RUNNING; the fixes land BEFORE 9.S's multi-worker step)

**The principle.** In an enterprise several people use the tool at once, and with roles
coming that is assumed, not hoped. Every write path must be safe against another person,
another browser tab, and, after 9.S's gunicorn, another worker PROCESS. A lock held in
memory, a module-level dict or an in-process job registry protects nothing across processes.

**The audit** ([CONCURRENCY_AUDIT.md](CONCURRENCY_AUDIT.md), read-only, each finding checked
against the code by a second reader) inventories every write path (git repository, JSON and
file stores, the credential store, NetBox, Kea, devices): what it writes, how it is protected,
whether that holds across processes, what a second user sees, what a collision does, marked
SAFE, UNSAFE-MULTI-PROCESS or UNSAFE and ranked. It answers specifically:
- two people editing the same intent: a save refused when intent moved since that person
  opened it, the difference shown (optimistic concurrency, the hash-bound confirm's idea);
- every lock cross-process, with a visible owner and start time, a lease so an abandoned
  operation cannot hold a device for ever, and a recorded admin release;
- the list's git repository, every commit strictly serialised across processes;
- file stores with more than one writer: atomic replace plus locking, or where a database
  (SQLite WAL first) is warranted;
- batches overlapping on devices: a defined lock order, no deadlock, no half-applied batch;
- every confirm bound to what was previewed (true for deploys; checked for every operation);
- approvals: two approvers at once, and four-eyes (requester is not approver) as a
  configurable policy for the roles stage;
- visibility: every page touching a device shows live who operates on it and for how long,
  and a person on a stale preview is told another user changed what they are looking at;
- Socket.IO, the readers and the in-memory job registries across workers.

**Tests:** a harness with two simulated users and two worker processes running conflicting
operations at once, and failure injection (a process killed mid-operation, a lock left behind,
a hung holder). **Placement:** the fixes land before 9.S runs more than one worker; findings
that affect today's single-process install (two users or two tabs) are scheduled now, by risk.

**Progress.** 2026-10-02: **R1, R24 and R25 fixed** (the list repository's lock is one
`flock` across processes, held from the first write to the last tag, staging and commit
refused outside it, a commit naming the paths it staged; readers take no optional git lock;
a failed tag reported; a save compares HEAD; retire's undo puts back only its own paths),
with a test that runs a real second process. **R4 fixed** the same day (the approval queue:
one lock across processes, an atomic replace, an unreadable queue refusing every write and
answering every read with its reason, reads that write nothing, `resolve` updating only its
own item after its execution). Then, in the operator's order, all fixed on 2026-10-02: R2 (the
intent editor saves against the version the person opened), R5 (nothing restarts the app under
a held device, an interrupted operation is drawn, and each device's receipt is written as it
finishes, commit pending), R13 (the template approvals record), R19 (drift state and one drift
run per list), R20 (as C326) and R28 (one run per reader). Not built: the per-device progress
step under `deploy_max_workers > 1`, the audit's other rows, and the multi-worker half (9.S).
The writeup's P.15 entry holds the commits.

### P.16 — Build or adopt the job machinery (DECIDED 2026-10-02, the operator; NOT STARTED; an evaluation, placed BEFORE Stage 10's release)

The stepper showed the tool has grown pieces of a job runner: systemd timers, job health,
device locks, run history, the finish wake-ups, in-memory job registries. **The OPERATIONS
stay ours**: preview, the hash-bound confirm, gates, verify, rollback, records, masked
secrets; they are the product. **The generic MACHINERY gets an honest evaluation**: queueing,
retries, scheduling, run history, concurrency, and an operation surviving an app restart
mid-run.

Candidates: Jenkins, AWX (Ansible Tower), Rundeck, Temporal, Celery or RQ, and "keep systemd
and what the tool has". Each costed against:
- a single-host install and air-gapped use;
- several users and concurrent operations (P.15's findings are an input);
- another credential store and another attack surface;
- progress and results kept on the tool's own pages (no second UI a person must open);
- what the tool would DELETE if it adopted it, and what it would have to keep anyway.

A recommendation with evidence, written before anything changes. Nothing is adopted or
removed by this item; a decision to adopt becomes its own plan item.

### P.17 — Onboarding classic IOS (DECIDED 2026-10-02, the operator; NOT BUILT; placed with Stage 10's multi-vendor item)

Register C332: classic IOS cannot be onboarded by ANY method today. The platform is blocked
pending a measurement of how a fresh classic-IOS node boots a bootstrap config, so static and
DHCP refuse it at plan time, and classic-IOS ZTP has no code at all (P.6 built IOS-XE's
AutoInstall only). It is placed with Stage 10's multi-vendor item because it is the same work
in miniature: a platform's boot path measured on a throwaway (the probe runbook's shape), its
bootstrap render, its ZTP mechanism if it has one, and the wizard's refusal lifted only for
what was measured. Until then the onboarding page says classic IOS is not onboardable, by
name, never by a silent absence (it does: docs/manual/how-it-works/onboard.md).

### P.18 — Phase two without the lab (DECIDED 2026-10-02, the operator; NOT BUILT; placed BEFORE Stage 10's release, with 10's lab-boundary work)

Register C332's other half, and C333's: onboarding's phase two rotates the bootstrap
credential through the persistence chain, whose preflight requires the lab's root-owned
Oxidized helper, and a rotation needs an Oxidized reload and fetch, a lab target and the clab
sync to call itself finished. So a network with no lab (any real one) cannot finish an
onboarding or a rotation: a LAB integration inside a PRODUCT workflow, which the Stage 10
rule forbids (docs/LESSONS.md#nothing-lab-specific-in-the-product, "Nothing lab- or person-specific in the PRODUCT"). The product's
definition of "persisted" is the device's own save read back (`onboard.persist_on_device`,
C53), which needs no lab. The Oxidized and startup-file stages become the OPTIONAL lab
integration: run when it is configured, said as not applicable when it is not, never a
reason a product operation stops. Placed with Stage 10's lab-boundary work
(NSOT_STAGE10_PLAN 6.0), and before the release, because the release is what a network with
no lab installs.

### P.20 — The rest of the CLAUDE.md audit's proposed checks (RECORDED 2026-10-02, the operator; NOT BUILT; ranked)

The CLAUDE.md consolidation (2026-10-02) marked each standing rule with where it is enforced and
ranked the checks worth building for those that are not. The first five are BUILT (2026-10-02):
CLAUDE.md citing real checks (`tests/test_claude_md.py`), one commit gate (`scripts/nmas-gate`),
every gated route declaring its five stages (`modules/operation_stages.py`), the signed-off
screens registry (`tests/signed_off_screens.py`), and the agent guards in `.claude/settings.json`.
The rest, in the order to build them:

1. **v2 population checks:** every `/v2/` route (page and fragment) answers under
   `csp.STRICT_POLICY` (today checked page by page); the "a write path carries its list, only a
   read derives the active one" scan extended from four modules and onboarding to every gated
   view.
2. **State that does not hold across processes** (P.15's follow-up): a scan for module-level
   mutable state and `threading` locks in the program, each declared (with why it is safe in one
   process, or the fix) or moved to a cross-process mechanism, so 9.S's workers inherit a list,
   not a surprise.
3. **Failures surfaced, operands named:** C8's rule (every handler around a NetBox write
   records, re-raises, retries or refuses) extended to `modules/integrations/` and
   `modules/readers/`; refusals built through one helper that requires both operands, so a
   guard cannot report a cause without what it compared.
4. **Interface states:** every v2 control that starts work declares its busy state (checked by
   the component rule, as `$el`/`$root` are); browser-test fixtures fill every column a test
   photographs or clicks (the C338 Baseline column was empty in the fixture that photographed it).
5. **Closed items have their writeup entries:** every item NSOT_WRITEUP.md's status table marks
   closed has an entry carrying all six parts (acceptance item 14).

**P.19, SDN controller support, is recorded at the END of this plan** (after Stage 10, whose
platform-driver layer it depends on).

### P.21 — Credential expiry and health (RECORDED 2026-10-03, the operator; DESIGN SIGNED OFF 2026-10-03; BUILT 2026-10-03 overnight except the declared Grafana expiry's field, which waits on the operator's decision: Settings has no v2 page and today's pages take nothing new)

**Signed off 2026-10-03, with the operator's decisions:**
- Thresholds: a warning 30 days and a danger row 7 days before an exposed expiry; an age of
  180 days from the last rotation for device credentials and SNMP communities.
- Grafana: the expiry is DECLARED in Settings when the token is entered, a REQUIRED field,
  never blank, rather than granting `serviceaccounts:read` (C230 moves the token down to
  Viewer, and Grafana OSS has no narrower role). Refusal detection covers a wrong or missing
  date: the first 401 or 403 is an immediate danger row naming the declared date.
- A credential expiring more than a year out is listed on Source of truth > Credentials with
  its date, and is no Needs attention row.
- C354 is built with it. C356 is measured as its row names. C357: the operator revokes the
  second NetBox token, and the row closes when the operator confirms.

**The problem.** The tool uses many connections, and an expired or revoked credential breaks
one silently or late. Measured: no product code reads any credential's expiry or age against a
threshold. The only expiry read anywhere is lab tooling's (`scripts/nmas-ci-log`, GitHub's
`github-authentication-token-expiration` header); `last_rotated` is stored on credential
profiles and template secrets and listed, never judged; and Grafana's probe counts a refused
token as reachable (C354).

**The inventory** (2026-10-03: the code read for every credential, and the host measured
read-only, metadata only: which settings are set, each service's token table or API for an
expiry field, the one TLS certificate's dates. No value was printed, logged or kept).

| Credential | Where it lives | Expiry exposed by the service? | Today, when it dies |
|---|---|---|---|
| NetBox API token | `netbox_token` (`enc:v1:` in `user_settings.json`) | **Yes**: the token's `expires` (`/api/users/tokens/`); set, with an expiry, on the host | sync and reads fail `raise_for_status`; the `api/status/` probe goes down |
| Grafana service-account token | `grafana_token` | **Yes**: service-account tokens carry `expiration` (`/api/serviceaccounts/<id>/tokens`), readable only with `serviceaccounts:read`, which a Viewer token lacks; NOT measured (Grafana's database is not readable by the service user) | shows UP (C354) until a Grafana reader raises 401 |
| Proxmox API token | `proxmox_token_id`, `proxmox_token_secret` | **Yes**: `expire` (`/access/users/<user>/token/<id>`); measured: set to never | probe and image-job rows go down or unknown |
| Kea, Oxidized, Loki, Prometheus, topology service | `*_username`/`*_password`/`*_bearer_token` (Loki, Prometheus, Oxidized and topology unauthenticated on the host; Kea set) | No: passwords and static bearers | the integration probe goes down (Loki's probe is unauthenticated, C354) |
| S3 archive keys | `s3_access_key`, `s3_secret_key` (empty on the host) | No (static keys; no expiry API) | the post-commit hook reports `ok: False` |
| Anthropic API key | `ANTHROPIC_API_KEY` in `.env` (plaintext by design) | No | a chat error event; the agent logs it; no row |
| GitHub, CI verdicts | none: the reader is unauthenticated | n/a | rate-limited or HTTP code: the CI source's unknown row |
| GitHub deploy key per list | `remote.json` names an SSH alias; the key is in the service user's `~/.ssh` | No (SSH deploy keys do not expire) | push failure recorded; the remote source's row |
| App origin access (Update) | the service user's SSH | No | the app-pushed reader fails |
| Cloudflare Access | none held: the app verifies assertions against the team's public JWKS | n/a (assertions carry `exp`, checked per request) | per request refusals; no row for a JWKS outage |
| TLS certificates | none held; one HTTPS service used (Proxmox), verified per `*_verify_tls` | **Yes**: the certificate's `notAfter`; measured on the host, about two years away | the probe fails when verifying, nothing when not |
| Device credentials | `devices.csv` (Fernet), `credential_profiles.json` profiles and overrides | No expiry; **age** from `last_rotated` and `rotation_audit.jsonl` | logins fail; the startup check; rotation's own rows |
| SNMP v2c communities | template secrets (`<list>:<host>:snmp_community_ro`, `@profile` refs) | No; age from `last_rotated` | polls fail per device |
| Fernet key `key.key`, session key `secret.key` | the data directory, mode 0600 | No; no rotation path exists | everything encrypted becomes unreadable |
| Break-glass record | the operator's sealed file; `breakglass_exports.jsonl` logs each export | No expiry; currency is already judged (`job_health.breakglass_rows`: digests against the devices now) | the stale row exists |

Outside the product, lab tooling only: the CI-log token (already warns at 14 days left), the
Cloudflare Access login for `nmas-host` (expiry detected, exit 75), the Access service token
two lab scripts send, and the NetBox backup's B2 and SSH keys (its failure is the backup job's
row).

**The design, for the operator's sign-off.** One reader, `credential-health`, hourly, reading
METADATA only, writing one stored value per credential: `{source, where_renewed, where_put,
expires_at | age_since, last_ok_use, state, why}`. It never reads, logs or returns a value.
- **An exposed expiry** (NetBox, Grafana, Proxmox, the TLS certificate): a Needs attention row
  **30 days ahead (warning) and 7 days ahead (danger)**, and immediately once expired. The row
  names the credential, its expiry, WHERE to renew it (the service's own page: NetBox's API
  tokens, Grafana's service accounts, Proxmox's API tokens, the node certificate) and WHERE to
  put the new value (Settings, that integration's field, which keeps a blank as unchanged). It
  clears when the reader sees an expiry beyond 30 days. Each service is asked with the app's
  own credential: NetBox's token list filtered to the integration's user; Proxmox's token
  record for the configured id (whether PVEAuditor may read it is measured at build);
  Grafana's needs `serviceaccounts:read` on the token, so **two choices for the operator**:
  grant it, or declare the expiry when the token is entered (a Settings field the reader
  trusts and says it trusts). The certificate's `notAfter` is read from the integration's own
  TLS handshake, verified or not.
- **No expiry, a free validity check**: the Anthropic key by `GET /v1/models` once a day (it
  costs no tokens); every other integration by its probe, made to ask an endpoint that NEEDS
  the credential (C354: Grafana `/api/user`, Loki a labels query), so a refused credential is
  a row naming 401 or 403 and the field to fix, never "down" in general.
- **A refusal seen in use** (401 or 403 from any integration call, or the AI client's
  authentication error) is recorded by the integration's own failure path and read by the
  reader at once: a danger row the same minute, not at the next probe.
- **The tool's own secrets with no expiry**: an age policy from the records already kept.
  Device credentials and SNMP communities from `last_rotated` and `rotation_audit.jsonl`
  against `rotation_policy` (stored and unused today; proposed default 180 days, a warning
  row naming Rotate on the device page). The Fernet and session keys are listed with their
  age and NO row: there is no rotation path, and a row needs an action (it becomes one when
  a key rotation exists).
- **Listed** on Source of truth > Credentials (7.6): every credential with its source, its
  expiry or age, its last successful use and its state, from the reader's stored value.

**Placement.** The reader and its rows need no new screen (Needs attention draws them), so
**before 7.6**, after the device actions now in progress (persist, rotate, deploy with Mode
B); 7.6's Credentials page draws its list from the same stored value. C354 is fixed with it.
**Lab tooling** is worth one thing only: the CI-log token already warns ahead, and the tunnel
login is detected when it fails; the Access service token the two lab scripts send has an
expiry Cloudflare shows on its dashboard, and a line in those scripts' failure naming it is
the most it is worth. Nothing outside the product becomes a row.

**Decided** (above): the thresholds, Grafana's declared expiry, and that an expiry beyond a year
is listed and draws no row.

### P.22 — Runbooks (DECIDED 2026-10-07, the operator; NOT BUILT; placed after Stage 7)

A drain is both a built-in action and an instance of custom procedures (vendors' maintenance
modes; Apstra's Drain state, CloudVision Change Control, Nautobot Jobs, NetBox scripts, AWX
job templates). Mercury's shape, in order:

1. **A runbook engine on the existing pipeline**: ordered, vetted steps, nothing a person
   could not do step by step. The steps are:
   - an intent change and its deploy (preview, confirm by hash, apply, verify, rollback,
     record);
   - wait for a measurement;
   - check a condition;
   - set a NetBox status;
   - record;
   - notify.

   A run plans across devices as one change set, with one preview and one confirm, and the
   change set is reverted as one.
2. **Drain and Return to service, the first BUILT-IN runbook** (the design and its mockup
   approved 2026-10-07: [NSOT_DRAINED_DESIGN](NSOT_DRAINED_DESIGN.md), canvas v71):
   - per-platform drain profiles, and neighbour-side steps from topology or declared;
   - NetBox's custom `drained` status set as the intended state;
   - success judged by measurement once the drained measurement exists (deferred by the
     charter, C551); until then by verify and the person reading the result.

   **Drain is AI-ASSISTED on top of the built-in runbook** (the charter, 2026-10-07; 8.17).
   The built-in runbook is the deterministic floor: the platform's profile, the declared
   neighbour steps. With the agent on, it PROPOSES the change set for this topology from that
   pattern (a neighbour's static route the profile does not know), with its expected effects,
   its verification and its reasoning; a person reviews, edits and confirms, and the same
   pipeline runs it. With the agent off, the built-in runbook alone, or manual intent edits.
3. **Custom runbooks per network**: declarative YAML of those steps, versioned in the
   network's repository and approved before use as templates are. Stage 8's agent may draft
   one for approval. Arbitrary scripts come later if ever, and only through the pipeline.

**Prerequisites:**
- Change sets across devices (C531 part 3); return to service by revert, through Phase 2's
  revert by reload until a no-reload revert exists (the removal-shape work is parked by the
  charter, its measurements kept).
- C553, folded into Phase 3: a job starts when an operation creates its work.
- The drained measurement is deferred (C551): NetBox's Drained status is the fact.

**Beside:** P.16 decides the machinery a run survives a restart on; the operations stay
Mercury's.

**Its first mockup covers:**
- Drain started from a device's Actions menu and from a Devices selection;
- the preview (profiles, neighbour steps, the change set's program, NetBox's status change and
  the `PUT` check, the measurement now);
- the confirm;
- the run's stepper with its bounded "waiting for Drained ✓" step;
- the result;
- Return to service;
- later, the Runbooks library.

### Course labs against the plan (decided 2026-09-26)

- **Lab 7, unit testing and coverage:** coverage is a MEASUREMENT, reported
  in CI, never a threshold, because a threshold invites tests written to
  move the number. Report it with its breakdown, because the shape of the
  number is the finding. At 2026-09-26 it was 57% of lines overall:
  `modules/nsot` 87.8%, while the low figures sit in code being cut or
  rebuilt (`ai_assistant` 15%, `configure` 5%, `topology` 6%, the
  collectors). The negative-controls ledger is the stronger artefact:
  coverage says code ran, and a control says the test would notice if the
  property disappeared.
- **Labs 8 and 9, ZTP:** P.6.
- **Lab 10, troubleshooting:** demonstrated with what already works:
  - drift with its coverage;
  - the freshness gate;
  - job health naming causes;
  - the heartbeat alert firing on a silenced device;
  - the rotation and persistence chain;
  - C38's adjacency alerting, if it has landed.

  **Stage 8 is NOT moved up for it** (operator): the agent has never made a
  tool call and its library is being rebuilt, and putting an untested agent
  on the network to meet a deadline is the shape P.3 spent a day removing.
  If Stage 8 lands first, its triage report is the closing act.

### AUTHZ — Roles and separation of duties (DECIDED 2026-09-26; built later, unscheduled)

The decision and its reasoning are in
[NSOT_AUTHORIZATION.md](NSOT_AUTHORIZATION.md).
- **Mechanism:** a verified identity carrying group names. Cloudflare Access
  groups first (whether its token carries them is unmeasured); OIDC against
  an IdP we run for a network without Cloudflare; no user table.
- **The gate kind `approve` splits into `author` and `approve`.** Today one
  kind covers both editing a template and approving it, so no role map could
  keep them apart.
- **Roles:**
  - **viewer** (none);
  - **operator** (`author` + `confirm`);
  - **approver** (`approve`);
  - **administrator** (`configure`).
- **Grants per named person:** `reveal`, `break_glass`, `publish_remote`.
- **Separation of duties is per ARTIFACT**, from verified attribution (D10):
  - the author of a revision may not approve it;
  - intent-author-versus-deploy-confirmer is a per-install policy, off by
    default.
- **The mode, the map and the grants are host-side**, like the gates. The
  default is `any_person`; in `roles` mode an empty map means nobody mutates.
- **Stage 7 draws every gated control from `may`**, disabled with its reason
  when refused (Stage 7 plan, pattern 6).

**Carried from P.3 step 2 (2026-09-26)**: `pipeline_builder.ensure_function_pipeline`
and `check_runner`'s `--config-id` mode have no producer since the configure
push was removed. They go with the rest of Jenkins.

---

### AFTER STAGE 7 — adoption at scale (PROPOSED 2026-09-26, not decided)

Raised by the operator. Analysed in
[NSOT_FEATURE_AUDIT.md](NSOT_FEATURE_AUDIT.md) section 8. In short:
- the wizard is for the exception, and the bulk path is a JOB;
- a reconcile job reads, then a one-shot commit creates, with devices in
  buckets and a bucket re-run as the retry;
- adoption is phase 2 of onboarding behind its own plan constructor, plus an
  extract-and-commit step;
- it records what is there, and brings a device to the baseline through the
  ordinary deploy path.

It is a build, so it is its own item and not part of a stage that moves
controls. **It changes Stage 7 in two places**, both undecided:
- 7.4 lists "adopt" as a GUI home for a capability that does not exist;
- ~~7.8 must not remove Add Device and Discover Subnet before it lands.~~
  **REVERSED deliberately, 2026-09-27 (the operator, register C102):** both
  were removed at once. The rule was written to protect a capability, and the
  capability turned out to produce broken devices: Add a half-managed one (a
  row and an identity, nothing else), Discover-then-Add one with no identity
  at all (C25). Until adopt lands, a device already configured cannot be
  brought in from the interface: an honest gap with a name, smaller than it
  sounds, because a NetBox-sourced list still brings devices in, and that is
  the model adopt should build from.

A scale finding rides with it: template approval is all-or-nothing per
platform.

### STAGE 7 — the interface, redesigned

**THE GUI PLAN: [NSOT_STAGE7_PLAN.md](NSOT_STAGE7_PLAN.md) governs this stage (2026-09-26).** The summary below predates it.

**Written first, 2026-09-26, and governing the GUI plan** (the operator's
order: the CI design and the feature audit, then the tasks, then the GUI):
- [NSOT_CI.md](NSOT_CI.md): what CI checks and where, what each check can
  stop, cutting Jenkins, and CI as state beside its trigger. Decided:
  **P.4, before Stage 7**.
- [NSOT_FEATURE_AUDIT.md](NSOT_FEATURE_AUDIT.md): every tab, feature and
  agent tool, classified KEEP / ABSORB / CUT / UNDECIDED, with six decisions
  left to the operator.
- [NSOT_TASKS.md](NSOT_TASKS.md): who the interface is for, what it must
  teach, and the task list the GUI is organised around.
- **P.3, before 7.0 (decided 2026-09-26)**: B12 (the identity gate is not enforced on
  deploy, restore or approval), B11 (secrets returned by `GET /settings`),
  D5 (the unguarded golden replay behind two buttons), D4 (the confirm
  screen shows the diff, not the program) and C23 (the restore preview's
  coverage fix is not wired in). Stage 7 moves controls, and must not
  re-home one whose guard does not exist.

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
embedded (`grafana.<domain>` and `nmas.<domain>` are both public
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

**8.5 The prompt examples, and the tools the prompt names (C30).** One job (the operator, 2026-09-26): both are instructions describing a system that does not exist. They reference another project's PE/P/MPLS
topology -- Section 3 finding #11, deferred from Phase 0 and still open.
`PE-1`, `P1`, `P4`, MPLS TE and LDP appear throughout
`ai_assistant.py`'s instructions, variable examples, Jenkins stage templates
and knowledge-base guidance. Make them generic, or match this lab (r1-r5,
s1-s4, OSPF/BGP/RIP/DMVPN). An example is an instruction: examples naming a
topology that does not exist teach the agent to look for devices that are
not there.

**8.6 How a Grafana alert reaches the agent's triage. DECIDED 2026-09-27,
design only** (the operator's proposal, argued rather than accepted).

**Grafana writes alert state, and NMAS reads it. There is no inbound
route.** One reader JOB (a timer, declared in `job_health`) reads Grafana's
alert state into a stored cache. Needs attention (7.2) renders that cache.
The agent is triggered by a TRANSITION in the cache, and **never polls
Grafana itself**. "The human and the agent look at the same thing" is only
true by construction if there is ONE read: two readers of one question
disagree, as the restore preview and `_baseline_earned()` did.

**An alert's DEVICE comes from its labels where they carry one, and from the LINE where they do not, and the
reader says which** (the operator, 2026-09-28, C168). Every syslog line carries the COLLECTOR as its `host`
label (`nmas` on all 3,151 lines in a day), so for the syslog class the attribution does not exist in the
labels; the heartbeat rules get it by matching the line. A parsed device is a WEAKER claim than a labelled one
(the line can be malformed, or name something else), so the reader's incident states the source of its
device, the way a reader states its endpoint and its time (C165).

**Why not a webhook, at its real strength:**
- **Reason 1 is the weaker one.** A webhook contact point can carry
  credentials, and could arrive through Access with a service token, so it
  is not unauthenticated by nature. What P.4 cut in `/jenkins/webhook` was a
  push whose BODY was trusted as a result. The agent could not trust an
  alert payload either, and would re-read everything it says. So the push
  carries one bit, "look now", and a poll gives that bit too.
- **Reason 2 is the decisive one.** The correlation is the work, and it
  needs the reads anyway.
- **If a faster class ever appears, the fallback is a DOORBELL, not a
  webhook.** A body-less POST, declared in the gate table as a service
  kind, which runs the reader early and never reads the request. Nothing
  needs one today.

**Latency.** Measured from the repository:
- The only rules NMAS generates are the heartbeat rules
  (`nmas-heartbeat-rules`: `for: 0s`, per-device windows, 750-1286 s as
  quoted). **Nothing here defines an adjacency or reachability alert.**
- A 60 s reader adds at most 60 s, under 8% of the shortest window.
- A webhook is not "seconds" end to end either: Alertmanager's
  `group_wait` (30 s by default) sits in front of every notification. So the
  comparison is about 60 s against about 30 s. This is predicted from
  Grafana's defaults, and to be measured on the host.

**No alert class needs faster, because this decision does not touch the
path to a PERSON.**
- Grafana's own contact point notifying a human stays, independent of
  NMAS. It is also the only alert path that survives NMAS being down.
- Triage is advice for a person who has already been notified. It is not
  the page.

**The latency risk that would matter is the evidence moving on, not the
delay.** So triage reads are anchored at the instance's ONSET, never at
"now". For a heartbeat alert the onset is `startsAt` minus the window: the
rule fires one window after the silence began, and the rule's own
`window_seconds` label carries the window. Loki, Prometheus and git keep
history, so a report written 60 s late describes the same window. A report
that queried "now" would describe the recovery and call it the incident.

**Newly firing: a state machine keyed on the INSTANCE, not the rule.**
- **An instance is the rule uid, the label fingerprint and `startsAt`.** A
  re-fire after a resolve has a new `startsAt`, so it is a new instance, and
  it is noticed rather than deduplicated.
- **The flap is the report loop.** A re-fire of the same fingerprint within
  a hold-down (proposed: 30 min after its last triage) does not call the
  model. It attaches to the existing report as "fired again, Nth time since
  HH:MM", and a flap count is a finding in itself. The limits:
  - one model call per fingerprint per hold-down;
  - a per-hour cap;
  - a cap reached is a job-health row, never a silent stop.
- **A triage that fails** (the model errored) is retried with backoff, and
  the failure streak is a row. The background agent's 27 silent failures
  had exactly this shape.
- **The store: absent and unreadable are different facts, again.**
  - **Absent** (a first run, a reset) must not triage everything already
    firing as new, which would be a report storm on the first start. It
    records the current set as *"firing when triage started; not
    triaged"*, as one row.
  - **Unreadable** refuses and is counted, and never writes over the
    history. The settings erasure was exactly that write.
- **A report is keyed on the instance it answers.** Shown against a later
  instance of the same rule, it would be a correct report about a different
  event: wrong, and looking right.

**What triage reads when an instance lands: an immediate drift measurement,
and who is working on the device** (the operator's refinement, 2026-09-27).
The drift check does not wait for its schedule. When an instance lands,
triage measures drift on the affected device and its neighbours at once:
seconds after the alert, not up to 30 minutes. That turns "something is
wrong with s3" into "here is exactly what changed on s3, against what a
person approved". It needs no authority: it is a read, and it passes the
autonomy test literally, since it is the scheduled check happening earlier
than scheduled.
- **Against BOTH references, named separately.** Against intent (the plan
  computed on a fresh capture: what a person approved as the target), and
  against the golden (the last record: what the device was). The drift
  checker compares only against the golden, so triage uses the plan's
  comparison for the first.
- **The capture is NOW, and the report says so.** A device can only be read
  in the present, which is the exception to anchoring at the onset. So the
  capture carries its time. The BEFORE comes from history: the golden, and
  Oxidized's copies with their times. Together they bracket the change:
  "landed between Oxidized's 03:00 poll and this 03:14 capture".
- **Neighbours come from stored adjacency, computed in code, one hop.** A
  burst whose subject is the pipeline (Loki or Alloy down: every heartbeat
  fires) runs no per-device drift at all. The fleet did not change, and
  reading nine devices to learn that would be triage's own storm.
- **Who is working on the device is an INPUT, read three ways, because no
  single source can say "nobody":**
  - **`show users`, in the same read session.** Who is logged in now, on
    which line, from where. It is live and positive. NMAS's own pooled
    session appears in it too, and is recognised by line and address.
  - **The terminal audit.** A break-glass session opened or closed in the
    window, with the verified actor. It covers only sessions through NMAS's
    terminal, and it appears in `show users` as NMAS's address, which is
    why both are read.
  - **The device's own log in Loki**: `%SYS-5-CONFIG_I` (and login events,
    if the device logs them) at `notifications` since P.1. Whether these
    reach Loki from every device is to be MEASURED before anything relies
    on it.

  A console session, a laptop's SSH before the window, or a log that did
  not arrive is not "nobody". So the absence of all three is reported as
  "no activity FOUND", never "no activity".
- **Recent human activity changes the row's ACTION, never what is reported.**
  Recent means a session present now, or any of the three within the window
  (proposed: from 60 minutes before the onset until now; set from real
  runs). Then triage proposes NO revert, and the row says why: *"A person is
  working on s3 (session from <addr> since 03:12). The difference is
  reported; no revert is proposed."* The person can ask for the plan from
  the row. This is not suppression, which 8.6 forbids: the event and the
  difference are both shown. What is withheld is the one-click restore,
  because a revert offered while somebody is mid-repair is still the wrong
  action, just slower, and the person most likely to click it at 3am is the
  one doing the repair.

**What triage needs to know, and which store already answers it** (the
operator's question, 2026-09-27: check what exists before building a
collector). Most of it exists. The real gap is OPERATIONAL STATE, not
configuration: the goldens say what a device is configured to do, not
whether it is doing it.

| Triage asks | Answered today by | Gap |
|---|---|---|
| What SHOULD this device be? | committed intent (`host_vars`) | none |
| What was it last approved as? | the golden, and its commits | none |
| When did its config change, and to what? | Oxidized's history (poll granularity) and golden commits; the immediate drift read gives NOW | none for WHAT; the time is bracketed, not exact |
| Who changed it? | the deploy record for the tool's own changes (C60, not built); the terminal audit for sessions | everything else: nothing witnesses a console, RESTCONF or NETCONF write (8.7's checklist: `archive log config` to syslog) |
| Identity, platform, addresses | the manifest, NetBox | none |
| Sites, interfaces, IPs, VLANs | NetBox (imported from goldens) | none |
| Which adjacencies SHOULD exist | intent and goldens (neighbour and network statements) | none |
| When did an adjacency or a link change state? | **Loki**: at `notifications` (P.1), `%OSPF-5-ADJCHG`, `%BGP-5-ADJCHANGE`, `%LINK-3-UPDOWN` and `%LINEPROTO-5-UPDOWN` are all sent. This is the "4 neighbours an hour ago, 2 now" comparison, event-sourced, with timestamps, and no SSH | **Measure first** that each form reaches Loki from every device (the heartbeat's method: count the exact form, per device, with a floor). C38 (nothing ALERTS on an adjacency) is a separate question |
| DHCP state | Kea leases, live through the API | none |
| Is it alive? | the heartbeat (Loki, Grafana), the ping worker | none |
| Metrics (CPU, counters) | Prometheus, but NMAS's client reads no device metric today (`test_connection` and `monitor` only); what it scrapes is listed on the host, not assumed | a read client, 5-a/7.3 |
| **What is it DOING right now:** routing table, adjacency states, interface status | **nothing stored** | **a live read at triage time** |

**Periodic or on-demand: ON-DEMAND, and no sweep now.** A periodic sweep is
stale exactly when it matters, and triage already reads live when it runs.
The two uses the operator separated each have a better source:
- **For comparison ("what changed since known-good"), the baseline already
  exists twice, with no new SSH:**
  - Loki's state-change events above: continuous, timestamped, collected
    anyway;
  - the post-deploy snapshot, which the pipeline takes after every deploy.
    It belongs in C60's receipt, so every deploy leaves a known-good
    operational baseline for free.
- **For context ("the network in general"),** the stores in the table
  answer it better than a sweep would.

A periodic snapshot is added only if those two prove insufficient on real
incidents. That is measured, not assumed.

**The live read reuses the pipeline's functions, and they are not ready to
be reused (C62, measured 2026-09-27).** Section 7 says to expose
`_capture_operational_snapshot` and `_detect_routing_neighbors` as
standalone functions. Read first:
- **It returns the FIRST protocol it finds** (BGP, then OSPF, EIGRP,
  IS-IS, RIP). r3 and r4 run OSPF and BGP, and r1 and r2 run OSPF and RIP,
  so each device is checked for one protocol only. OSPF is never read on
  r3 or r4, and RIP never on r1 or r2.
- **The BGP count's pattern matches no standard row.** It expects the
  address plus six numbers and one token, and a real row has seven numbers,
  Up/Down and State. Against a standard-format table it counts 0. So r3's
  and r4's verify compares 0 with 0 and passes, having checked nothing.
  Unconfirmed against r3's real output: nothing in the repository has ever
  fed that branch real output.

Exposing them as they are would carry both into triage. The standalone
version reads EVERY protocol intent says the device runs (intent knows),
reports each by name, and counts established sessions, not configured ones.

**One reader, one allowlist.** The live read runs through the shared
read-only allowlist (C61), the same function as the agent's tools and the
lens. Its cost is bounded: the affected device and one hop, and nothing
for a pipeline-subject burst.

**What the model is given: a stored picture it QUERIES, never a dump.** A
full config per device is a lot of context for a question about one
interface. Reading everything on every alert costs more and reads worse.
- **Triage computes the deterministic facts first, in code:**
  - the drift lines against intent and the golden;
  - the state-change events in the window;
  - the receipts and reviews;
  - the human-activity signals.

  It hands the model those, small.
- **The model asks for more through 8.2's read tools**, each answering a
  narrow question: this interface's section, this neighbour's state, this
  window's log lines. It gets the right thing, not everything.

**What was deployed, and what the second reading said about it, is triage
context** (the operator, 2026-09-27; 8.8 is the other half). When an
instance lands, triage reads the deploy receipts (C60) for the device and
its neighbours in a window before the onset (proposed: two hours). For each
receipt it reads 8.8's recorded review of that program's hash. The report
then starts from what was pushed, not from a diff:
- **"Warned about, confirmed anyway, and it broke":** the warning, the
  cited lines, who confirmed and when.
- **"Reviewed, NO warnings, and it broke":** stated just as plainly, with
  the same prominence. This is evidence about the REVIEWER, not only about
  the change. A report that mentions the review only when it warned would
  let the record flatter the gate: it could confirm its own value and
  never disconfirm it.
- **"Not reviewed":** the review did not run, with its reason.
- **"Warned, overridden, and the operator's stated reason was …":** quoted
  with who wrote it, when, and its until-when if any, labelled testimony.
  A device inside an unexpired stated reason is reported as *deliberately
  different, per the operator, until …*, and triage proposes nothing
  against it. An expired one is named as expired.
- **No receipt in the window:** stated, so "nothing was deployed" is
  never inferred from a missing record.

The join is on the COMMAND HASH, which is why it needs C60: without a
durable record of what a deploy sent, the incident has nothing to find its
way back to. It needs no authority; it is reads.

**The record first, the model reading it later, as separate decisions**
(the operator's split, 2026-09-27). The deploy record (C60: a receipt at
apply, closed by a follow-up window that states what was watching) is
deterministic, and triage uses it from the start as above: what was pushed
before this broke. **Handing that HISTORY to the model as context is a
separate, later decision**, for three reasons:
- **Small sample.** Nine devices and a few deploys a week. "The network
  was fine after X" is mostly evidence that nothing was going to break
  anyway. A model given that history will find patterns whether or not
  they are there, and a person will act on them.
- **Absence of alerts is weak evidence.** "Deployed X, nothing alerted"
  means something only if the alerting could have seen the failure. Today
  that is device liveness (the heartbeat) and the pipeline's verify. A
  deploy that degrades something unwatched looks identical to a clean one.
  So each closed row says what was WATCHING, and a quiet row is "quiet,
  watched by: …", never "fine".
- **It must be able to disconfirm.** A history that accumulates only
  "reviewed, cleared, quiet" flatters the gate. Triage surfaces
  "reviewed, cleared, then broke" PREFERENTIALLY: it is the row that
  teaches something.

**The test for adding it: a person reads the last fifty rows first.** If a
person cannot learn anything from them, neither can the model, and the
context is not added.

**The report states what it could NOT establish, always.** Beside what it
READ and what it CONCLUDES (below), a third part is required: what it could
not establish. It is never omitted and never empty without saying so. The
operator's example is the shape: *"s3 differs from intent by these lines;
the terminal was opened at 03:12 by <person>; I cannot tell whether that
change was deliberate."* Every source that could not be read is a line in
it ("could not read s3's log from Loki: cannot tell who changed it"). A
confident wrong conclusion and an unexplained diff are both worse at 3am
than a report that names its own limit.

**A burst: grouping is code, conclusions are the model's, and suppression
is nobody's.**
- **Grouping is deterministic, on the ONSET, never on `startsAt`.** This was
  found while recording the decision. Per-device windows mean one silence
  that began at one instant fires each device's rule up to 536 s apart. So a
  `startsAt` window of any sensible width would split a single Loki outage
  into several incidents. Instances whose onsets fall together form one
  incident. Later, topology adjacency from stored neighbour data can join
  them, also computed in code. **One incident, one model call, one report.**
- **The model's judgement is confined to the report's TEXT:** which members
  look like one cause, which look independent, and *"unexplained"* as an
  allowed answer. That is unattended judgement, and it is acceptable only
  because its output is advice, labelled as advice, and acts on nothing.
- **The model may NOT suppress.** "This one is a duplicate, no report" is the
  decision that must never be made unattended. Every firing instance belongs
  to exactly one incident, and the report has a line for every member
  ("every device accounted for", the batch rule). A wrong merge then costs a
  wrong sentence, visible beside the member it misdescribes, and never a
  missing event.
- **The burst this fleet will produce first is not the adjacency case.**
  - No adjacency rules exist, and a heartbeat breaks only when a failure
    cuts a device's path to rsyslog.
  - With `noDataState` and `execErrState` both Alerting, **a Loki or Alloy
    outage fires EVERY heartbeat rule.** The rule's own description says
    "the heartbeat cannot say which".
  - So a deterministic check runs before any model call: is the pipeline
    answering, and is ANY device's heartbeat arriving? Everything silent,
    with the datasource erroring, is one incident whose subject is the
    pipeline, not nine device reports.
  - Whether Grafana marks an error-state instance distinctly is measured on
    the host's version, not assumed.
- **An alert for a device not in the inventory** (a retired device whose rule
  was never regenerated: C54's shape, one store over) is named as that, and
  not triaged as a device fault.

**Grafana down: the reader has its own row, and "200" is not "evaluating".**
- **The reader is a declared job**, and every read records its outcome:
  - ok;
  - unreachable;
  - auth refused;
  - stale (no successful read in three intervals).

  A source that could not be read is a row saying so (Stage 7 §1a), never
  "nothing firing".
- **The wrong-and-looks-right state is a Grafana that answers and has
  stopped evaluating**: 200, with nothing firing. That is the Proxmox
  listing's 200 with 0 items, and it reads exactly like a healthy fleet. The
  reader checks each rule's last evaluation time and reports stale
  evaluation as its own state. That the rules API carries the evaluation
  time is to be measured on the host's version.
- **A floor on the population.** The reader expects at least as many
  heartbeat rules as the generated rules file holds. Fewer is a permission
  or provisioning gap (*a monitor's permissions can hide what it
  monitors*), and reads UNPROVEN rather than clean. Which Grafana role can
  read alert state is measured before 7.2, not assumed.
- **When NMAS is down, NMAS watches nothing.** Grafana's person contact
  point (above) is what remains. The pull design removes the push INTO NMAS,
  and keeps the push to a person.

**Where the report lands: ON the alert's row, never as a row of its own.**
- **A report row beside the alert row is two rows about one event**, the
  three-reports problem restated on the page. So Needs attention has one row
  per INCIDENT, in §1a's shape:
  - what;
  - device(s);
  - since;
  - cause;
  - operands;
  - the ONE action.

  The report attaches to that row as its triage, with the members listed.
- **The report separates what it READ from what it CONCLUDES.**
  - Each claim cites its query and time range.
  - Each conclusion is labelled a hypothesis.
  - What it could NOT establish is its own part (above), required.

  A guess that reads as a finding is the agent's version of *a message
  whose first words are good news*.
- **The action stays a person's**, and recent human activity on the device
  means no revert is proposed at all (above). If the agent proposed a fix, the row's
  action is *"Review the proposed plan"*: an ordinary plan in 7.1's
  preview-confirm component. The agent never confirms it, and that is
  structural, not a prompt instruction. The agent's actor is `ai-agent`, and
  `require_person_for_confirm` refuses anything that is not a verified
  person.
- **When the alert resolves, the row leaves Needs attention**, because it no
  longer needs attention. The report stays reachable from the device page's
  History with its instance identity and resolve time, because a report
  that vanishes with its alert cannot be checked afterwards.

**What Stage 7 must leave room for** (the reason to decide this now):
- **7.2's Grafana source is a reader job writing a cache**, which §0a already
  requires. It keeps each instance's identity (fingerprint and `startsAt`)
  and its `window_seconds`, not a boolean "firing". A cache that stored only
  "s3: firing" could not tell a re-fire from a continuation, or compute an
  onset, and Stage 8 would have to rebuild the source.
- **Needs attention rows are per incident, with a member list**, even while
  every incident has one member.
- **A row has a slot for an attached triage**, empty until Stage 8.
- **A row's action can be "a person is working on this device"**, with the
  plan one request away, rather than always a proposed plan (the human-activity
  rule above).

The *proposed* numbers (hold-down, cap) are starting points, to be set from
8.4's first real runs, the way the heartbeat windows came from measured
arrivals. Not built.

**Investigate, on each alert (the operator, 2026-09-30; NSOT_GUI_BRIEF 14.2).** The
Alerts screen and each Needs attention incident get an "Investigate" action, and a
new incident is investigated automatically. The AI's notes sit in the alert's row.
Conditions, each a requirement of the build:
- **The notes are labelled AI-generated**, and list every query and read the agent
  ran, so a person can repeat any of them.
- **Its tools are READ-ONLY**: it investigates and suggests, and never acts. A fix it
  suggests is an ordinary plan a person previews and confirms (the 8.7 rule).
- **Notes never hide, dismiss or downgrade the alert**: the row keeps its level,
  and a note cannot close it.
- **Cost is bounded**: one investigation per INCIDENT, grouped as the reader already
  groups them (on the onset), never one per member, with a per-day cap stated on
  the screen.
- **It sits behind Stage 8's first real tool run.** The agent has never called a
  tool in production (27 recorded runs, zero tool calls), so this is not "wire the
  tools to alerts": it is their first run, and it comes after the allowlist is real
  in code (8.3).

**8.7 The agent closing drift. DECIDED 2026-09-27: PROPOSE-ONLY. NOT YET,
rather than never: the second class is named, not granted, and the
conditions that would change that are listed below.** (The operator's proposal, argued
rather than accepted. Design only.)

**The proposal, restated correctly by the operator:** *the agent may close a
gap that a person already approved the closing of, and nothing else.* The
approved target is INTENT, not a golden: a golden is a record of what a
device was. The class, as narrowly drawn as possible:
- the program contains only lines present in committed intent;
- it is merge-only, so the agent never negates anything;
- it has no dangerous lines, whatever authorisation is on file;
- it is, line for line, a subset of a program a person previously confirmed
  for that device;
- the device is not rollback-blocked;
- the template's fidelity check passes live, as for any plan.

**It does not pass the autonomy test, and it is not the "empty class" the
audit ruled on.** The test (NSOT_FEATURE_AUDIT.md) is *"is the worst outcome
that it happened earlier than scheduled?"* The audit called re-sending a
confirmed deploy an empty class: nothing to add, or the hash refuses. This
is the case the hash refuses: the device moved, and a FRESH program is
computed against it. Its worst outcome is reverting a person's deliberate
change, which is not "earlier than scheduled". So it is either a second
class with its own test, or propose-only.

**Its own test would be: a re-assertion of a decision a person made, where
the tool can POSITIVELY attribute the undoing to something no person
decided.** The load-bearing word is *positively*: the absence of evidence
of a person must never count as evidence of no person.

**Why it is not granted: the one drift of this kind on record was
deliberate, and the class admits it.** P.1's acceptance test removed s4's
heartbeat timer BY HAND (`no event timer watchdog time 300`, 2026-09-25
21:22:27). That line reached s4 through the confirmed deploy path. Check the
restoring program against the six conditions:
- in intent: yes;
- merge-only: yes;
- no dangerous line: yes;
- a subset of a confirmed program for s4: yes;
- not rollback-blocked: yes;
- fidelity: passes.

All six hold. An agent holding this class would have re-added the timer
within one drift interval and destroyed the acceptance test while it ran.
That is the operator's 3am failure, and it is not hypothetical: it is the
only instance we have.

**What undid it: the stores cannot tell a deliberate change from a lost
one, and they cannot be made to in the direction that matters.** Measured:
- **The terminal audit** records open, close and refusal, with actor,
  device, peer and time. It never records keystrokes, by design (B13, P.3
  step 7). It can say that a person HAD a session open. It cannot say what
  they did.
- **The deploy record cannot say what was confirmed.** The pipeline's audit
  file deliberately omits `commands_to_add` and carries no command hash. The
  golden commit holds the post-deploy capture, not the program. So the
  fourth condition, "a subset of a confirmed program", has nothing to be
  checked against today. That is recorded as C60, because it is a gap in
  the audit of every deploy, agent or not.
- **The device's own log is the only positive source.** Since P.1, every
  device sends at `notifications`, so `%SYS-5-CONFIG_I: Configured from ...
  by <user> on vty0 (<addr>)` should reach Loki. That is expected, not
  measured, and it must be measured before anything relies on it. Even
  then: the NMAS terminal logs in with NMAS's own device account from NMAS's
  own address. So a person's change through the break-glass terminal and a
  deploy are the same line in the device's log, and telling them apart is
  inference from the terminal audit's window, never attribution.
- **"Lost to a reload" is nearly empty here, and each member is a symptom.**
  The deploy path saves every device after the push (`save_config()` in
  `_push_via_netmiko`). So a line that disappears across a reload was never
  in the startup config the device booted. The causes are:
  - a failed save (C57's shape);
  - a containerlab redeploy from a stale Oxidized copy (what the freshness
    gate exists for);
  - a replaced device.

  Each is a defect a person should see. An agent that quietly re-adds the
  line removes the evidence, which is the collector-restart exclusion's
  reason exactly: there the restart destroyed evidence, and here the repair
  does.

**The alert trigger makes it faster AND more dangerous, and the class does
not survive it** (the operator's refinement, argued 2026-09-27).
- **It removes the "late anyway" argument.** A restoration triggered by 8.6's
  immediate drift check would arrive in seconds, not 0 to 30 minutes later.
- **It also changes WHICH devices the check samples.** A scheduled check
  looks at a device at an arbitrary moment. An alert-triggered check looks
  at it at the moment of the incident, and the alert is often caused by the
  very change the agent would revert: someone acting to stop a problem. So
  the trigger selects for exactly the devices a person has just changed, in
  the window where they are still working on them. On the schedule, a
  revert would at least tend to land after the person had finished. On the
  alert, it lands during the repair.
- **Merge-only protects against one of the two emergency moves, and not the
  other.** Measured against the class as drawn:
  - **Adding a disabling line** (`shutdown`, `passive-interface`, a `deny`
    in an ACL) is never reverted. Restoring would need a negation, and the
    class never negates. The operator's own example, shutting an interface
    to stop a loop, is outside the class.
  - **Removing an enabling line** (`no redistribute static subnets`, `no
    neighbor`, `no network`, `no ip route`, or s4's `no event timer`) is
    reverted by an ADDITION, which is inside the class. Stopping a loop by
    withdrawing a redistribution is the other thing a person does at 3am,
    and the agent would put the loop back within seconds.
- **Honest read: the class does not survive, and the trigger is what
  settles it.** Positive attribution of a non-deliberate cause was already
  the only way to admit a member, and it shrinks the class to a few
  symptoms of other defects (above). The alert path adds a correlation that
  works against it: the trigger fires most often when a person is the cause.
  So:
  - **`reassert` is not granted on the alert path until the conditions
    below hold** (positive attribution is what would make it safe there);
  - on the schedule path, it stays ungranted, with the preconditions above
    as what any future grant would have to meet, **plus no human activity
    found within the window** (8.6's three sources), since the scheduled
    path is not immune to the same case, only less exposed to it;
  - **recent human activity withholds even the PROPOSAL of a revert** (8.6):
    the difference is reported and the person asks for the plan if they
    want it.

  The alert-triggered drift check stays, because as a READ it is the best
  triage input there is. It sharpens the argument against the restoration
  rather than settling it by fiat: the same speed that makes the report
  better makes the revert worse.

**The premise, argued (the operator's pushback, 2026-09-27): "once every
change goes through the pipeline, the tool knows every change by
construction".** Recorded so the answer can be revisited with evidence
rather than re-fought.

1. **The emergency case does not disappear, because the break-glass path is
   outside the pipeline BY DESIGN.** A person touches a device at 3am for
   reasons that are not deployment errors: a node that restarted, a link or
   peer that failed, a config that was right when deployed and is wrong now
   because something else moved. The fastest action is the device's CLI.
   Once the terminal is read-only, that path is the console and the
   break-glass record, and the break-glass path is deliberately
   independent of the tool. A path the tool can see is not break-glass. So
   the changes the tool cannot explain are concentrated exactly in the
   emergencies, which is where a revert does the most harm. Not
   hypothetical here:
   - every golden before r6 was a configuration typed by hand;
   - s4's timer was removed by hand for P.1;
   - the fleet has been redeployed twice from startup files (2026-08-30 and
     2026-09-22).
2. **The timing gap survives, and part of it can be seen.** A person who has
   decided on a pipeline fix and not yet deployed it leaves traces the tool
   holds:
   - an intent commit whose plan is not empty ("intent moved and has not
     landed");
   - a plan previewed for the device.

   Both belong in 8.6's human-activity input, beside `show users`, the
   terminal audit and `CONFIG_I`. The second is not recorded today (a plan
   is a POST that stores nothing), and recording it is cheap. What no
   signal covers: the person who has decided and not yet touched anything,
   and the person working around the tool through the console. **A
   restoration's speed and its danger are one property**: its value is
   acting inside the window where a person may be responding, and that
   window is exactly where it must not act.
3. **Is "the gates prevent it" the shape this project keeps removing? Yes.**
   A gate controls the TOOL's actions, and the claim needs a property of
   the NETWORK: every writer of a device's config is the tool. That is a
   proxy population ("changes made through the tool" standing in for
   "changes made to the device"). Measured on the live goldens, 2026-09-27,
   the writers that are not the pipeline:
   - **RESTCONF** is enabled on r1-r4 and r6, and **NETCONF-YANG** on those
     five and s1. Both accept config writes from any client holding the
     credential, and yang-push already rides NETCONF.
   - The console, and SSH from anywhere holding the credential (which the
     break-glass record exists to hand out).
   - The device itself: regenerated self-signed certificates (measured,
     2026-09-22), and any EEM applet that runs CLI.
   - A redeploy from a stale startup file (what the freshness gate exists
     for).
   - Until the split, the terminal and the free-text command runners (see
     the terminal decision, NSOT_FEATURE_AUDIT 3a).

   "If it happens, that is a defect in the gates" is true and does not
   help. Authority conditioned on a property has to CHECK the property at
   the moment it acts, not assume it from the design: *a gate keyed on
   something that moves*. The constraint-shaped fix is not to enumerate the
   writers. It is to make the DEVICE the witness, because the device sees
   every change whatever the path.

**So 8.7's answer is "no, NOT YET", and here is what would change it.** Each
condition is checkable, and a future review reads this list instead of
re-arguing the class:
- [ ] **The device records every config change itself, and it reaches the
      tool.** PULLED FORWARD by the operator, 2026-09-27 (register E6):
      it closes the gap whatever writes to the device. For example `archive` / `log config` with `notify syslog`, so
      each command arrives with its user and line. No device has it today
      (measured). Its arrival from every device is measured with a floor,
      as the heartbeat is.
- [ ] **The tool's device account is used by the pipeline alone.** People
      and break-glass use other accounts (6.2's per-consumer accounts), so
      a change by the tool's account outside a deploy is itself a defect,
      and a person's is attributable to that person.
- [ ] **Every config writer on the device is either the tool's account or
      logged by the device.** RESTCONF and NETCONF are disabled where
      unused, or their writes are attributable. SNMP RW stays absent
      (measured absent 2026-09-27).
- [ ] **Deploy receipts (C60)**: the confirmed program, its hash and its
      actor, recorded durably.
- [ ] **Human activity is recorded as an input:** plan previews, intent not
      yet landed, the lens's sessions, `show users`.
- [ ] **A stated reason, with its until-when, is an input** (8.8's written
      response to a warning). It ADDS an item rather than removing one: it
      makes deliberate changes legible when they went through the deploy
      path and were warned about. A change outside the pipeline, or one the
      reader did not warn about, still carries no reason. So it narrows the
      unexplained case and does not close it; the device-as-witness item
      (E6) is still what covers every path.
- [ ] **Free-text device inputs are allowlisted:** the terminal, the
      command runners, and the agent's tools, pipes included (C61).
- [ ] **The class's own limits:**
  - confirmed against the same intent commit and template closure;
  - an age backstop;
  - once per device per line set per window, a recurrence being a finding;
  - never while any human-activity signal is present;
  - never a negation.

**What they buy, stated so the list is not read as a formality.** With the
first three, a loss becomes POSITIVELY attributable. Every human change
carries a user, so a line that vanished with no logged command is
non-human (a stale boot, the device's own doing). Only then is "restore
what no person removed" a claim the tool can check. Even then, the alert
path needs the activity conditions, because a person may be seconds from
typing.

**Decided:**
1. **Propose-only.** The agent does everything but confirm. On drift from
   intent (computed as a plan against a fresh capture, never from the drift
   checker, which compares against the golden), it:
   - builds the plan;
   - attaches what it read: the device's `CONFIG_I` lines for the window,
     the terminal audit's sessions for the device, and whether the lost
     lines were in the last confirmed program;
   - queues it.

   A person confirms it in 7.1's component, one click from the row. That
   costs one human action per drift, and it is the same flow the approval
   queue's `revert_to_golden` hand-off already uses. **When 8.6 finds recent
   human activity on the device, not even the proposal is made**: the
   difference is reported, and the plan is one request away.
2. **The second class is NAMED, so a future grant cannot arrive under
   another name: `reassert`.** It is never `confirm`, and never a bypass of
   `require_person_for_confirm`. It is a new gate kind in
   `modules/route_gates.py`, refused by default, and granted, if ever, like
   `service_allowed_operations`: by kind, by a person, on the host.
3. **If it is ever granted, its audit stays unambiguous.** The commit
   carries:
   - `Actor: ai-agent`;
   - `Actor-Verified: delegated`, a fourth value beside `access`,
     `host-shell` and `none`, written only by the reassert path;
   - `Reasserts: <the confirm record's id>`;
   - `Originally-Confirmed-By: <the person, verified then>`.

   A person's confirm can never carry `delegated`, and a reassert can never
   carry `access`. Both are tested at `repo.git()`, the one place the
   trailer is written.
4. **The preconditions for ever granting it, each a thing to build or
   measure first:**
   - the confirmed program recorded durably (C60);
   - `CONFIG_I` measured reaching Loki from every device;
   - attribution that is positive for a non-deliberate cause, and refuses
     on unknown;
   - the confirmation made against the SAME intent commit and template
     closure hash as the fresh plan: a decision made against different
     intent is a different decision, so staleness is judged by what moved,
     not by the calendar alone;
   - an age cap as a backstop;
   - once per device per line set per window. A second loss of the same
     lines is proposed with "lost twice" as its finding, because recurrence
     is the signal and a silent repair hides it.
5. **Not built.** Stage 8.3's allowlist ships WITHOUT `reassert`.

**8.8 A second reading of the program before confirm. DECIDED 2026-09-27
as ADVISORY, design only** (the operator's proposal and framing).

**What it is for (the operator's framing, which is the standard it is
judged by).** It is not an authoritative check: those exist and are
deterministic (approval, deployability, credential unchanged, dangerous
lines, rollback block). It is one more layer between the network and human
error: a second pair of eyes on a program a tired person is about to
confirm at 2am. So:
- **Cheap and non-blocking.** It never stops a deploy. The rule "no answer
  is not a pass" becomes "no answer is not a REVIEW", and the screen says
  which.
- **Honest about confidence.** "This shuts the interface carrying your
  management address" is worth having. "Looks fine" is worth almost
  nothing, and is never drawn as reassurance.
- **Allowed to be wrong in the noisy direction.** A false warning costs
  five seconds of reading. A miss costs nothing the person was not already
  exposed to, since every other gate still runs.
- **Its value is asymmetric.** It pays for itself by occasionally catching
  the obvious-in-hindsight mistake that no deterministic rule can name,
  because the mistake is not a specific string.

**The earlier question, "would it have caught what we hit?", answered
honestly, and no longer the bar:**
- **The `transport input` replace (E3):** plausibly yes. A model knows that
  changing VTY transport on the only path can cut access.
- **The P.1 syslog block:** it would most likely say nothing useful, or add
  noise.
- **s4's `shutdown`:** that was a test fixture's spare port. A model would
  warn only if the interface carried management, and it did not.
- **The terminal's secret send (B13):** out of reach entirely. It was never
  a deploy program.

One plausible catch out of four is the expected shape for a layer judged
by asymmetric value.

**States: it is NOT a gate with a pass condition, and it can never draw
green.** It sits in the gates part of the preview-confirm component under its
own name ("second reading"), with three states that do not exist for any
other gate:
- **`warns`**: each warning drawn;
- **`no_warnings`**: drawn neutral and grey, in words: *"no warnings: not a
  clearance"*;
- **`not_reviewed`**: with its reason (unreachable, timed out, answer
  unreadable, disabled).

A test asserts no advisory state renders the success style, and that
`not_reviewed` is distinct from the deterministic `not_reached`. The confirm
button is never disabled by it.

**The schema is the confidence discipline.** The model returns warnings only.
Each warning carries:
- the program line(s) it is about, by index;
- the claim;
- the consequence.

There is no field in which to say "looks fine", so reassurance cannot be
expressed, only omitted. The server drops a warning whose cited lines are
not in the program, and counts it as a defect in the review.

**Non-blocking by construction.**
- `/deploy/plan` returns immediately.
- The review is a separate call keyed on the COMMAND HASH, with a short
  timeout and the cheapest adequate model.
- A re-plan (an authorisation ticked, a device moved) changes the hash, and
  a review of another hash is drawn as *"reviewed a different program"*,
  never carried over.

**Context, what it needs to be any good, and what is missing.** It already
has:
- the program;
- the capture, masked at the provider boundary;
- the intent diff and attribution;
- the rollback program (`rollback_commands()`, computable at plan time);
- the device's management address from the inventory, and the interface
  holding it, found by address in the capture.

**Missing, and each is data, not a prompt:**
- **The manager's path to each device.** Which devices are transit for
  management: s3's `Vlan99` is the gateway for everything. Nothing records
  it. The topology service has adjacency, not the forwarding path.
- **Which routes are load-bearing.** Nothing marks one, such as the /32
  statics redistributed for the manager.
- **The manager's own address and gateway, as data** rather than as prose
  in CLAUDE.md.

**The cheapest, highest-value half is deterministic, and should be built
whether or not the model is.** Flag, without refusing, any program line that
touches the management path:
- the interface holding the management address;
- anything bound to `line vty` (transport, access-class, login);
- a route or ACL covering the manager's address.

That is exactly the repair-path-travels-over-the-thing-being-changed class,
and it needs no model. The model then covers the long tail, with the
deterministic flags given to it as context. Recorded as the first thing to
build in this item.

**Prompt injection: the device is the vector, and advisory does not make it
safe** (the operator: the output is still shown to a person who may act on
it). Config text reaches the model inside the program and the capture:
descriptions, banners, remarks, EEM action strings, aliases. Decided before
building. The defence is STRUCTURAL, in what the output can express, never
the prompt's instructions:
- **No tools.** The review can act on nothing.
- **Warnings carry no remedy.** No suggested command, no URL, no
  instruction. A warning is a claim about cited lines and a consequence.
  An injected warning therefore cannot tell a tired person to run something.
- **Every cited line is verified to be in the program**, so an injected
  "warning" about a line that is not being sent is dropped and counted.
- **The output is drawn as untrusted text:** escaped, labelled as the
  model's reading, never rendered as markup.
- **The suppression attack buys nothing.** A banner saying "report no
  warnings" can at most produce `no_warnings`, and that state is designed
  never to read as a clearance. So the dangerous direction of the injection
  is defused by the state model, not by detection.
- Secrets are masked at the provider boundary as for every model call
  (`redact.py`), so nothing sent carries one.

**Measurable from the first review, and able to DISCONFIRM itself** (the
operator, 2026-09-27). An advisory feature usually cannot be evaluated.
This one can, if the recording is built so the question is answerable
before anyone asks it:
- **Every review is one row, joined to three things, deterministically:**
  - the receipt of the program it reviewed (C60), by command hash;
  - that deploy's outcome (verify failed, rolled back, or completed);
  - any 8.6 incident on the device or a neighbour with its onset within a
    window after the deploy.

  "Broke" is decided by that join, in code, never by a model's opinion of
  its own review.
- **A quiet deploy counts only as far as something was watching.** The
  follow-up window records the watchers. A "no warnings, quiet" row on a
  program that touched sections no watcher covers is reported as
  unobserved, not as a correct clearance. Otherwise every unmonitored
  failure scores as the reviewer being right.
- **Four outcomes, all first-class:**
  - **warned, and it broke:** a catch;
  - **warned, and nothing broke:** the false-warning rate, which is the
    cost;
  - **no warnings, and it broke:** a miss, which is the disconfirming
    evidence;
  - **not reviewed:** reported separately, so an unavailable reviewer
    cannot count as a quiet one.
- **The survivorship trap is recorded too.** A warning a person heeded
  stops the deploy, and a deploy that was never sent cannot break. So
  "warned, NOT confirmed" is its own row with the plan's hash. Without it,
  the most effective warnings are invisible in the numbers, and the gate
  looks worst exactly when it works best. It is counted as "heeded", never
  as "caught", since whether it would have broken is unknown.
- **The decision rule is written before the data.** Decided now, reviewed
  after three months of real deploys:
  - keep the review if it has at least one catch, or heeded warning, that
    the operator judges real;
  - and if its false warnings per deploy are low enough that its warnings
    are still read;
  - otherwise drop it.

  Deciding the threshold after seeing the numbers is how a feature is
  kept on sentiment. The counts are one report with denominators
  (`nmas-review-report`, CLI first).

**When the second reading warns, confirming requires a written reason**
(the operator, 2026-09-27; decided, design only). Not a checkbox: a sentence,
saved in the deploy record (C60) beside the warning, the program and its
hash. The deploy still proceeds and the person still decides, but the record
then holds *"warned about X; proceeded because Y"*.
- **Why it is more than friction.** 8.7's missing evidence was WHY a change
  was made, and no store answers it: the terminal audit records that a
  session opened, not what anybody intended. A reason attached to the
  program is that evidence, supplied by the only party who has it. At 3am
  triage reads *"a deploy 40 minutes ago was warned it would drop the
  adjacency, and the operator wrote 'replacing the cable at 04:00'"*
  instead of an unexplained diff.
- **Only when warned.** A reason asked of every deploy becomes "ok", and
  the field becomes noise. Asking only on a warning keeps the friction in
  proportion to the risk. `no_warnings` and `not_reviewed` ask nothing.
- **Testimony, not fact.** A reason is what the person believed at the
  time. The record and every triage report label it *the operator's stated
  reason*, never a cause: the same separation the reports already make
  between what was READ and what was CONCLUDED.
- **Reuse, do not rebuild (2026-09-28).** C140 needed this mechanism first:
  every authorised line (a dangerous line, or a secret a restore would add,
  C79) now carries a stated reason under exactly the three properties below,
  in `modules/nsot/authorisation.py` (shape rule, testimony, the aggregate
  from the receipts). The written override is a second use of that module,
  never a second implementation of what counts as a reason.
- **Where the minimum is drawn: shape, never quality.** The server refuses
  only what carries no statement at all:
  - an empty or whitespace-only reason;
  - fewer than a handful of words (proposed: three);
  - text identical to the warning it answers.

  It never judges whether a reason is a good one. A tool grading reasons is
  theatre, and teaches people to write for the grader. A reason like "ok"
  that passes the shape rule is exactly what the aggregate below exists to
  surface.
- **An optional UNTIL.** "Temporary, reverting at 06:00" is the most useful
  kind, and the kind that goes stale. The reason carries an optional
  until-when, so a device is *deliberately different, for now* or
  *deliberately different, with no end stated*. It feeds drift: a device
  with an unexpired reason is EXPECTED to differ in exactly the lines the
  warned program touched, and it is drawn that way, not as drift. An
  expired one is drawn as drift again, naming the reason that lapsed. So a
  temporary fix nobody reverted becomes a finding the moment its own stated
  deadline passes, which is the only deadline the tool can hold anyone to.
- **Who.** The verified person from `identity.request_actor()`, never a
  field in the request, so the 3am reader knows whom to call.

**Some controls exist to make behaviour VISIBLE rather than to prevent it**
(the operator's distinction, recorded because it is a different kind of
control). Every gate so far is technical: refuse, block, require a person.
This one accepts that a determined operator will proceed, and makes the
pattern legible to someone who can address it on a human level. One override
had a reason; thirty is a problem a tool cannot fix and a manager can. That
is why the ritual risk is accepted rather than disqualifying: **if someone
types "ok" thirty times, that is the finding.** The record working as
designed produces the evidence that it is not being taken seriously. What
follows:
- **The aggregate is the feature, not the row.** Overrides are countable
  and attributable: per person, per device, and over time. A row nobody
  aggregates is a row nobody reads.
- **It is drawn where a person already looks**: Needs attention (7.2)
  surfaces a repeated override pattern the way it surfaces drift and failing
  jobs, and Versions (7.5) lists the overrides with their reasons. Evidence
  that needs a grep works only after somebody already suspects.
- **The count states what it covers:** overrides of warnings the second
  reading produced, on deploys that went through the tool. It cannot see a
  change made outside the pipeline, and says so on the count itself, so
  the number is never read as the whole picture.
- **The outcomes become** warned-and-heeded, **warned-and-overridden with a
  reason**, cleared-and-broke, and not-reviewed. The second is the
  interesting one: over time it says whether the warnings are right and
  being ignored, or wrong and being worked around. Joined to what followed
  (the follow-up window), an overridden warning that then broke and one that
  did not are different findings, about the person and about the reviewer
  respectively.

**What it stands on: the attribution work, which now serves two purposes.**
D10's `Actor-Verified` and P.3's person-gated confirms were built as
SECURITY controls. They are equally the foundation for this ACCOUNTABILITY
control, because an override attributed to "user" or "pipeline" is
worthless. That second purpose is what justifies keeping attribution strict
even where the security argument alone might have relaxed it (register E5).

**What a review row holds.** It is `0600` and masked:
- the command hash and capture hash;
- the model and prompt version;
- the state, the warnings with their cited indices, and the latency;
- whether the person then confirmed, and the join keys above.

It is written at review time, and completed when the deploy's receipt
lands or the plan is abandoned.

**Not built.** The component leaves room for an advisory state in the gates
part (7.1). The deterministic management-path flag can land with or before
it; the model call belongs to Stage 8, after 8.1's model choice and 8.3's
authority gate.

*Acceptance:* every one of the 73 tools is classified with a reason; the
allowlist exists **in code** with a test that an unlisted tool is refused;
no tool reaches a device outside the confirmed deploy path; the prompt
examples name only devices in this lab; and the background agent is enabled
**last**, with one real run observed and reported -- the same bar drift
had to clear; and triage is triggered as 8.6 decides (a read, never an inbound push).

**8.9 The pipeline learns from what slips through (SCOPED 2026-09-30, the operator; NOT
BUILT; after 8.3 and 8.4, and after P.10's layers exist).**
1. Something slips through: verify fails, a rollback happens, or a device refuses a line.
2. The assistant DRAFTS a new check from the incident: the rule, the captured output as
   its evidence, and the layer it belongs in (a lint rule, a sandbox test, or a Batfish
   invariant).
3. It PROVES the draft before proposing it:
   - it catches the program that caused the incident;
   - it does NOT fire on the current fleet's intents, nor on past successful deploy
     programs (the false-positive rate is measured against the deploy receipts, C60);
   - where possible, it is reproduced on the sandbox.
4. A PERSON APPROVES it, like a template approval, recorded with who and why. The AI never
   adds a rule on its own. A rule that is too broad blocks legitimate work and gets
   overridden; one that is wrong in the allowing direction lets danger through while
   looking like coverage.
5. Each rule records its origin (incident, platform, image version), so it can be
   revisited when the platform changes.

**The honest expectation:** this makes the pipeline never repeat a mistake. A genuinely
new kind of failure stays possible, which is what verify and rollback remain for.

**8.10 The assistant adds platforms, through the platform pipeline (SCOPED 2026-09-30, the
operator; NOT built).** The design is [NSOT_STAGE10_PLAN.md](NSOT_STAGE10_PLAN.md)
section 12.4.
- **The steps:** on request ("add support for <platform>"), the assistant:
  1. captures real output READ-ONLY, from a command list a person approved first;
  2. drafts the platform DEFINITION (data, never code);
  3. proves it against the device's own output, never only against itself, including
     captures of broken states.

  A person approves it, as a template approval. Read features are enabled from the proven
  captures; write features only after their measurement on P.10's sandbox.
- **Its limit:** the assistant never enables a platform itself. Its role (VIEWER plus
  `author`, 9.I) cannot hold `approve`.
- **Numbered here because it is the agent's work, and RUN after** 9.P (the framework),
  P.10's sandbox, 8.3 (the enforced authority) and 8.4 (the agent's first real runs).
- **Acceptance:** a third platform added through it (Junos recommended), not a release
  blocker.
- **Size:** 30 to 60 commits.

**8.11 Many AI providers, configured at once and switched at will (SCOPED 2026-09-30, the
operator, with the same day's update; NOT built).** The principle, as for sign-in and access:
the people running it choose. Some prefer, or are required by policy to use, another AI than
Claude, and some networks (air-gapped ones) cannot send anything to a hosted AI at all.

**Today, measured 2026-09-30:**
- ONE client, Anthropic's (`messages.create` in `ai_assistant.py`).
- Its "providers" are three Claude presets (Sonnet, Opus, Haiku, the background agent on
  Haiku), chosen INSTALLATION-WIDE (`set_active_provider`), with no per-user choice.
- `requirements.txt` pins `openai` ("Used for Groq and Ollama") and `groq`, and nothing in
  the program imports either (C252).

**1. One internal interface; providers plug in.** A chat with tools: messages, tool schemas,
tool calls, tool results, token usage, the model version the provider RETURNED.
- **At minimum:**
  - Anthropic (native, today's);
  - OpenAI (native, and Azure OpenAI for enterprises);
  - Google Gemini (native);
  - xAI Grok;
  - ANY OpenAI-compatible endpoint (Mistral, DeepSeek, Qwen, OpenRouter, Groq and most
    others, with no per-vendor code);
  - LOCAL models through Ollama or vLLM, on the user's own hardware: **the air-gapped
    option**, which the design has always aimed at.
- **Recommendation: our own thin adapters, not LiteLLM.** The OpenAI-shaped API covers
  OpenAI, Azure (a base URL and API version), xAI, Groq, Mistral, DeepSeek, OpenRouter, Ollama
  and vLLM with ONE adapter on the `openai` SDK, and Gemini publishes an OpenAI-compatible
  endpoint too. So it is two adapters (Anthropic native, OpenAI-compatible), plus a native
  Gemini one only if a measured need appears.
  - **LiteLLM** would cover more names, at the cost of a large, fast-moving dependency tree
    (a supply-chain surface, and a lock generated on the host, C40).
  - **More important,** its normalisation of tool calls would HIDE the per-model differences
    the evaluation (point 6) exists to measure.
  - **The one real piece of work is ours either way:** translating tool calls between
    Anthropic's content blocks and OpenAI's `tool_calls`.
  - Revisit LiteLLM if a needed provider has no OpenAI-compatible endpoint.
- **An agent-disabled mode stays** (`ai_enabled` off).

**2. CONFIGURE MANY, SWITCH AT WILL.**
- **Configure:** Settings holds any number of provider configurations. Each has:
  - the provider;
  - the endpoint;
  - the model;
  - the key's reference in the credential store;
  - where data goes, in words;
  - its evaluation record.
- **Switch:** the person using the assistant selects among them at the time, in one click from
  the assistant panel, with a per-user default.
- **CONFIGURING and SELECTING are separate permissions:**
  - an INSTALLATION ADMINISTRATOR configures (keys and local endpoints, stored encrypted and
    revealed only through the reveal gate, like every credential);
  - any user selects among the configured ones, with no access to the keys.
  - Until 9.I's roles exist: configure is gated `configure`, and select is not a device
    action.

**3. Policy per network (after P.8).**
- An administrator can restrict which configurations a network may use ("local model only"
  for a sensitive network).
- The picker shows a restricted model as UNAVAILABLE THERE WITH THE REASON, never hidden: the
  visible-not-hidden rule of the roles.

**4. Every answer records its model.**
- In a conversation that switches, each reply is labelled with the provider and the model
  VERSION that produced it (the version the provider returned, not the configured name).
- The audit trail records which model proposed each action:
  - the approval queue's item;
  - the proposal a person confirms;
  - `ai_usage_log`.

**5. The safety gates are MODEL-INDEPENDENT.**
- Whichever model is chosen, it proposes, and the program's gates, previews and confirmations
  decide.
- The agent's permissions are its ROLE (VIEWER plus `author`, Stage 10's roles; 8.3's
  enforced allowlist at the tool dispatch, never in the prompt). **Changing the model never
  changes what the agent may do.**

**6. Models differ at tool use: MEASURE EACH.**
- **One evaluation suite runs against any configuration** (Stage 8's fixtures). It measures:
  - tool selection;
  - argument correctness;
  - refusing out-of-scope actions;
  - handling tool errors;
  - never inventing device output (a fixture whose right answer is "the tool failed").
- **A model gets the agent's TOOLS only after passing it.** A model that fails is still
  offered for read-only chat help, labelled so.
- **Each result is recorded with the model version.** When the version a provider returns
  changes under the same name, the record is drawn STALE with both versions, and a re-run is
  offered.
- **Tools stay on over a stale record**, because the gates bound what a tool can do whatever
  the model. The evaluation measures usefulness and correctness, never permission. The stale
  label is what a person reads.
- **Local models vary most.** The minimum capability is stated as the suite passing, with
  native tool calling and a context window large enough for the tool library plus one device
  configuration. No model is named as passing before it is measured.

**7. What leaves the network is the administrator's decision.**
- Secret masking and log redaction (`redact.py`, today at the one `messages.create` call)
  move to the provider interface, so they apply identically to every adapter.
- Settings states plainly where data goes for each configuration: hosted (which company,
  which region where the provider offers a choice), or local (nothing leaves).
- Providers' data-handling terms and jurisdictions are documented neutrally. No provider is
  preferred by default, except that local is highlighted for air-gapped networks.

**8. Cost and limits.**
- Token accounting per provider and model (`ai_usage_log` gains both and the version; a local
  model costs no tokens, said as such).
- A budget per installation and per user, with the existing prefer-fewer-calls rule.
- Rate-limit and error handling per adapter, with bounds from measurement.
- A FALLBACK configuration is optional and explicit, never silent: when one answers, the reply
  is labelled "fell back from X because Y".

**9. Context across a switch mid-conversation.**
- **The conversation is stored in a PROVIDER-NEUTRAL form:** text, tool calls and tool results,
  each with the model that produced it. The next request is rendered for the chosen model from
  that form, tool calls translated to its format.
- **Too long for the new model's window:** the existing history compression trims it (oldest
  turns summarised; the system prompt, the current task and the latest tool results kept), and
  the panel says "trimmed to fit <model>'s <N> tokens".
- **Switched to a model NOT allowed tools:** it is sent no tool schemas. Earlier tool calls and
  results are rendered to it as quoted text, so the conversation continues read-only.
- **Provider-bound content** (Anthropic's signed thinking blocks) cannot be carried to another
  provider. It is dropped at the switch, and the panel says so.

**10. Placement.**
- **Built in Stage 8,** so the agent is multi-provider from its first real tool run (8.4).
  Claude is the first provider exercised, and at least one other (ideally a local model)
  passes the evaluation before Stage 8 closes.
- **The per-user default and the configure/select split** need 9.I's users and roles; the
  network policy needs P.8.
- **Stage 10** carries the wizard's provider step (configure, Test, run the evaluation) and
  the documentation of where each provider sends data.
- **Size:** 40 to 80 commits (two adapters, the neutral transcript, the picker and policy, the
  evaluation runner, the accounting).
- **Depends on:** 8.3 (the enforced allowlist) and 8.4 (the agent's first real runs), 9.I for
  users and roles, P.8 for per-network policy.
- **It closes C252** (the unused `openai` and `groq` pins): used by the OpenAI-compatible
  adapter, or removed.

**8.12 How the agent gets domain knowledge (RECORDED 2026-10-04, the operator; designed in
Stage 8).**
- **The CCIE knowledge base is REMOVED.** `ccie_kb/`, `modules/ccie_kb.py`, the v1 configure
  page's 81 "topic/subtopic" config types filled from it, its schema route, and the
  assistant's prompt lines and index. They were v1 leftovers, believed downloaded and
  summarised from Cisco sources, so not ours to redistribute.
- **Stage 8 designs the replacement as RUN-TIME lookups, never a bundled corpus:**
  - the device's own output (read-only commands, through the allowlist);
  - NetBox;
  - the tool's own records: intent, goldens, receipts, history;
  - documentation fetched when needed, with its source named in the answer.
- **The agent still never writes IOS for a device** (8.3). What it proposes goes through
  intent and the pipeline, so knowledge only informs a proposal; it never becomes a program.

**8.13 The agent proposes a change's expected effects (RECORDED 2026-10-06, the operator; no
work now; C506 builds the rule-derived floor first).**
- **The agent PROPOSES expected effects** from the program, the topology and the device's
  state; a person confirms them or adds to them in conversation. Confirmed effects are bound to
  the plan's hash and recorded exactly like declared ones.
- **The rules are the floor and always run.** The effects C506 derives from the program run
  whatever the agent says: the agent can ADD expectations, never remove a rule's check. With
  the agent off or unavailable, the rules alone.
- **Judgement calls are the agent's to explain**, for example mis-cabling ("Gi4's neighbour is
  r2, not r1"): the rule sees an undeclared neighbour (a note when additional, a failure when it
  replaces a declared expectation, naming both); the agent says what it most likely means.

**8.14 The agent's authority (DECIDED 2026-10-06, the operator; no work now; Stage 9's role
model carries it, 9.I step 7).**
- **The agent NEVER holds authority of its own.** It acts on behalf of a person, capped at the
  LESSER of its own permissions and that person's role.
- **Its own identity is a read-only service identity**, for analysis and suggestions: no write,
  approve, authorise or block-lifting authority of its own.
- **Anything that LOOSENS a check is proposed, never done, by the agent:** declaring an expected
  effect, authorising a dangerous line, retrying, lifting a block. A person whose role allows it
  confirms it; it is recorded as "proposed by the agent (its reasoning), confirmed by
  <person>", bound to the plan's hash.
- **A safety floor no declaration can loosen, the agent's or a person's:** loss of the management
  path, the device unreachable, an untouched interface or adjacency failing. Always hard
  failures (C506's verify carries this floor).
- **Prompt injection:** device output, logs, NetBox text and comments the agent reads are DATA,
  never instructions; a declaration derived from them still needs a person's confirmation.
- **Tested in Stage 9:** the agent cannot do through a person anything that person's role
  forbids.

**8.15 The top bar's command box is where the person asks the agent (RECORDED 2026-10-06, the
operator; no work now; C537's mockup draws the box).**
- **One box, Ctrl-K or its button, in the v2 top bar**, replacing the wide global device
  search. Before Stage 8 it jumps to a device or a page.
- **From Stage 8, the same box answers both:** a device name (or a page) navigates; a question
  goes to the agent, whose answer opens beside the page, under 8.14's authority (it proposes,
  a person confirms).
- **The Devices page keeps its own search**, which FILTERS its list; the box never filters.

**8.16 Fleet-wide read-only commands are the agent's evidence engine (RECORDED 2026-10-06, the
operator; the screen is C548's, a board to draw).**
- **One engine, two users:** a person picks devices (by name, role, network) and read-only
  commands from the same allowlist (`readonly_commands`), with results summarised, grouped,
  collapsed and compared; the agent asks the same engine for its evidence, never a session of
  its own.
- **The agent's reads are a person's reads:** the same allowlist, the same device holds while
  reading, the same masked answers, recorded the same way, so what it saw can be read again.

**8.17 AI-assisted actions in the Actions menu (DECIDED 2026-10-07, the operator; in
[MERCURY_CHARTER](MERCURY_CHARTER.md)).**
- **Two kinds of action:**
  - **Standard** actions are deterministic, the same for every device: capture, deploy intent,
    revert by reload, rotate, onboard.
  - **AI-assisted** actions are reasoned per device and topology: drain and return to service,
    a revert without a reload, link moves, troubleshooting.
- **An AI-assisted action produces only a PROPOSAL:**
  - the change set across the devices involved;
  - its expected effects (8.13);
  - how success is verified;
  - its reasoning.

  It starts from a known pattern (the platform's drain profile) and fills in what is specific
  (a neighbour's static route), with 8.16's engine as its evidence.
- **A person reviews, edits and confirms.** The same pipeline runs it, recorded as "proposed by
  the agent, confirmed by <person>" (8.14's authority: the agent proposes, never confirms).
- **The safety floor applies:** never the management path; success judged by measurement.
- **With the agent off,** the action falls back to its built-in runbook (P.22) or to manual
  intent edits. Nothing is possible ONLY with AI.

---

### STAGE 9 — hardening and cleanup (ADDED 2026-09-28, the operator; reshaped the same night)

**Why it exists.** The register needs a place where a real finding can be
recorded, deferred and kept from competing with the stage in progress. Until
now every row argued for itself whenever it was looked at, and that is how
7.1's close became a dozen findings and no 7.2.

**The decision that shapes it (the operator, 2026-09-28): this is a lab, so
the work is features, functionality and design. Security is DEFERRED, not
abandoned.** The functional path is now the whole plan:
1. R1 and R2b (7.1's stated limit);
2. 7.2, from C54;
3. 7.3, with C50, where rotate and retire finally get an interface;
4. 7.4 onward.

The program is **shaped and functional** when three things hold:
- the operations work from the interface;
- the record is honest;
- nothing leaks that matters in this environment.

**Stage 9 is not "finish the program".** It is hardening and cleanup on top
of a working program. Never finishing its cleanup half is an acceptable end
state.

**TWO KINDS OF DEFERRAL, labelled separately.** A reader of "deferred to 9"
must be able to tell which kind it is, because only the first changes when
the environment does.
- **(L) SAFE HERE BECAUSE IT IS A LAB.** The exposure is real, and this
  environment makes it acceptable: a lab, no hostile party on the LAN,
  emulated and disposable devices. **On a real network these would come
  FIRST, not last.** They are:
  - the published community (C39, with C141 merged);
  - oxidized-web serving every config to the LAN (C143, which is 6.1);
  - the community rotation and its consumer work (C139);
  - 6.2's per-consumer accounts;
  - `transport input all` (E3). **Measured 2026-10-01** with the vty standardisation (C301): r1 to
    r4 run `transport input all` (telnet included) on `line vty 0 4`, and only r6 runs
    `transport input ssh`. The hardening is one bulk-intent change of the vty stanza's transport
    to `ssh` on r1 to r4, deployed through the normal path (C307 makes its rollback per line);
    the switches' vty lines to be read and decided with it;
  - **The switches, read 2026-10-04** (the operator's notes from s3's page; every committed
    golden on the host read, read-only, and Prometheus's LLDP table):
    - **vty transport:** s1 to s4 all run `transport input telnet ssh` on `line vty 0 4` AND
      `line vty 5 15`. The routers' item above extends to them: the same one bulk-intent change
      to `ssh`, both stanzas, all four switches. The routers' `line vty 5 15` is not in their
      goldens, so its transport is the platform default, unmeasured: read it before the change.
    - **`ip http server`:** all four switches run it, and nothing the tool runs uses it (the
      operator, for s3). Remove it on all four (a removal, so Mode B, one measured shape). The
      routers run only `ip http secure-server`, which RESTCONF uses: not this item.
    - **Unused ports:** no switch's Gi0/1 has an LLDP neighbour. On s1 and s2 it is an
      untouched default port, not shut down; on s3 and s4 it carries C428's leftover
      description (to become "spare"). **Candidates for `shutdown` come only from ports with
      no link in the topology, and LLDP alone is not the topology:** s3's Gi1/1 carries the
      manager's path and shows no LLDP neighbour, because the manager speaks no LLDP. So the
      candidate list is LLDP's silent ports minus every port NetBox cables or the management
      path name, read per device and confirmed by the operator before any shutdown;
  - **Thanos Query answers anyone on the LAN** (C438; the operator, 2026-10-04, after 14.13).
    It listens on `0.0.0.0:19193` (HTTP) and `0.0.0.0:19094` (gRPC) with no login, so the
    whole metrics history is readable from the LAN. Grafana and the tool reach it on
    localhost. The step: first read what else connects to both ports (read-only, on the
    host), then propose binding both to `127.0.0.1` as its own host step;
  - **No enable secret anywhere, so a console's `enable` needs no password** (C457; the
    operator's console drill on r2, 2026-10-05). With C455's console login in place, the
    next boundary is an enable secret per device, held in the break-glass record and
    rotated with the device credential. It is its own decision and its own step, never
    mixed into the console-login rollout;

  - SNMPv3 (C249, the operator, 2026-09-30): nothing the tool runs speaks it, so every
    device must run a community. REQUIRED before Stage 10's release. **Designed the same
    day, tied to the monitoring profile (P.9): the profile's SNMP section produces secure SNMP
    by default.** Our lab's v2c (one shared community, no view, no ACL) is exactly what the
    program must never generate for a real network. **It is also the real fix for the
    publication gate's community (C280, the operator, 2026-10-01):** that gate now holds a
    push only for a NEW secret value, so another copy of an acknowledged community passes,
    but the community is still in every golden and so in the published history. SNMPv3
    removes it from the configurations altogether; until then the acknowledgement is what
    stands between it and the remote.
    - **authPriv**: SHA-2 authentication where the platform accepts it, else SHA; AES
      privacy. **Measured per platform first** (IOS-XE 17 and vIOS 15 accept different
      sets), recorded with evidence the way `removal_measured.json` and
      `platform_defaults.json` are, and a platform with no measurement is refused, never
      defaulted.
    - **Generated names and credentials**, never defaults or guessable values. Held in the
      credential store under the profile's key, masked everywhere, revealed only through the
      reveal gate.
    - **A VIEW** limited to what the monitoring reads (IF-MIB, the CPU and memory tables,
      OSPF and BGP, LLDP, IP SLA, SNMPv2-MIB's system group), derived from the exporter's
      generated modules so the two cannot disagree; and **an ACCESS LIST** answering only
      the collector's address.
    - **Rotation as an operation**, with credential rotation's safety model: staged before
      the device changes, proven on the device and at the collector before the old one goes,
      recoverable at every state between.
    - **(i) The collector needs the same credentials.** snmp_exporter's `auths` and the trap
      receiver's users are GENERATED from the store, written for the service that reads them
      (the `0640` handoff rule), and never in the public repository.
    - **(ii) A v3 user does not appear in the running config** on Cisco, so a golden cannot
      show it and verify cannot read it there. What proves a user present and working is
      measured per platform (`show snmp user`, and an authenticated poll from the collector),
      and verify reads that.
    - **(iii) A staged switch-over, never a window with no working SNMP:** add v3 beside
      v2c; move the collector to v3; confirm data arrives for EVERY device; only then remove
      the community (its removal is already measured safe on both platforms). This closes
      C141, and with it the published value's last use.
    - **Order (the operator's lean, agreed):** r6 and r1 get today's v2c SNMP through the
      profile now, so monitoring is complete; SNMPv3 is the NEXT profile change, fleet-wide.
      It does not need to come before the re-proposal: step (iii) begins with v2c present on
      every device, so completing v2c first is the switch-over's starting state, not work
      thrown away. The per-device fields and the choice of version (C255) carry over: v3's
      shared fields are the view, the ACL, the algorithms and the user's group; the user
      name and its credentials are generated per network and rotated as one.

  Added by the triage for the operator to confirm: C44 (a manual pull
  bypasses the deploy gate), C100 (NMAS's NetBox token is the operator's
  account), B9 (the backup key can hide what it writes), E5 (roles and
  separation of duties) and E6 (the device as witness of its own changes).
  **Stage 6 (6.1 to 6.5) is this half's list**, so Stage 6's items are
  scheduled here rather than as a separate stage.
  **Its FIRST item is a sweep** (the operator, 2026-09-28): every plan
  document read for exposure that the register does not list. C143 was
  invisible to the register BY CONSTRUCTION, because it had a stage, so
  nothing but a sweep of the plans can find its siblings. It was not run
  when security was deferred; it is this half's entry task.
- **(M) MINOR.** Genuinely small, whatever the environment: C6, C7, C9, C13,
  C40, C45, C47, C71, C72, C93, C94, C113, B10 and E2, plus C41 (the
  device-boundary harness), the one large item in this half.

**COUPLED, recorded so that it is not forgotten: 6.1 (C143) and the
community rotation (C139).** Whichever happens first constrains the other.
Rotating while oxidized-web still serves configs to the LAN publishes the
new value there the day it lands. Closing 6.1 changes what reads Oxidized
and NetBox (NMAS reads NetBox at the LAN address `<nmas-host>:8000`, measured
2026-09-28), and the rotation's consumer work must match. Measured for 6.1
before it was deferred:
- oxidized and loki are `docker run` containers (restart `unless-stopped`),
  so a 127.0.0.1 bind recreates them;
- NetBox's port is in `~/netbox-docker/docker-compose.override.yml`;
- the SNMP exporter runs with host networking, so its bind is
  `--web.listen-address`;
- clab-sync reads Oxidized's git repository on disk, not port 8888;
- NetBox answers on 127.0.0.1;
- the only live peers seen were local (a snapshot, which cannot see an
  occasional consumer).

**WHAT MAKES STAGE 9 URGENT AGAIN, stated once.** If any of these becomes
true, the (L) half moves ahead of whatever stage is running:
- the tool manages anything real;
- the lab becomes reachable from beyond the operator's LAN;
- a device holds a credential that also works somewhere else.

**Rules, so it does not become a graveyard.**
- **An item enters by DECISION, not by deferral.** Its row records who
  decided, when, why it can wait, and which kind, (L) or (M). "Deferred to 9"
  with no reason is only a longer register.
- **Stage 9 is not the only exit.** A row is also CLOSED as won't-fix with
  its reasoning, MERGED into the stage that rebuilds its code (a row whose
  code 7.3 deletes is not fixed twice), or HOMED where a stage already owns
  it. The register shrinks by decision rather than growing by politeness.
- **Precondition: nothing in it is live exposure that matters here, and
  nothing in it blocks the functional path.** A row found to be either
  leaves for an earlier stage the day it is found. A finding's severity is a
  claim about the world, so an UNKNOWN is measured before it is placed
  ([OPEN_FINDINGS.md](OPEN_FINDINGS.md), the triage).
- **Data loss is never Stage 9.** B8 (the backups' only decryption key was on
  one laptop) is fixed by a copy the night it was measured, because a safe
  backup nobody can read is lost data, not a hardening gap.

**One item moves OUT, because doing it later means doing it twice:** C71's
sanitiser half goes with the (L) placeholder work, when that work is done.
The sanitiser produces the fixtures, so it is what must emit the
placeholders. Scrubbing eleven files by hand, then regenerating them
through a sanitiser that still leaks, would be the same repair made twice.

*Acceptance:* none for the stage. Each item carries its own. The standing
check is the precondition.

#### 9.I — Identity, roles and running with nothing in front (SCOPED 2026-09-30, the operator; not built)

**Why it is in Stage 9 and not Stage 10.** Stage 10's release depends on it, and the
operator's lab moves to it first, so it is tested on the operator before anyone else
depends on it. Its design is [NSOT_STAGE10_PLAN.md](NSOT_STAGE10_PLAN.md) sections 2 to 4
and 11. Unlike the rest of Stage 9, it is not a deferral but a feature: the program must be
secure ON ITS OWN, with nothing in front of it (Stage 10's principle, the installer
chooses).

**It supersedes part of AUTHZ** (above; [NSOT_AUTHORIZATION.md](NSOT_AUTHORIZATION.md)):
- LOCAL ACCOUNTS are built in and the default, reversing the rejected "user table", with
  the reason in NSOT_STAGE10_PLAN.md 2.2;
- the roles become two layers;
- AUTHZ's approver becomes the network administrator's permission;
- its separation of duties per artifact is kept.

**Steps, in order:**
1. **Classify every gate by role and scope.** The table (120 endpoints: configure 35,
   approve 19, confirm 16, not_device 41, publish_remote 5, reveal 4; measured 2026-09-30)
   gains a scope column (installation or network) and a required role. `approve` splits
   into `author` and `approve`. A test holds the table exact both ways, P.3's shape. No
   behaviour changes yet: `any_person` still answers.
2. **The provider interface.** `identify()` asks the configured provider. Cloudflare's
   verification becomes the first provider, its behaviour and tests unchanged; the
   trusted-peer check belongs to it alone.
3. **Local accounts:**
   - argon2id; the NIST 800-63B policy; TOTP with recovery codes (required for
     installation administrators);
   - server-side sessions with `Secure`, `HttpOnly`, `SameSite=Lax` cookies, rotated at
     login;
   - lockout by back-off per account and per address;
   - the break-glass local administrator, every use a Needs attention row;
   - the last installation administrator never removable;
   - the user screen in v2.
4. **Generic OIDC** (Authlib: discovery, code flow with PKCE, the ID token validated),
   with a Test sign-in that shows the claims and a group-to-role mapping.
5. **Roles:**
   - installation administrator; per network, network administrator, operator, viewer;
   - `strict_network_access` (off by default: an installation administrator holds every
     network implicitly, recorded as such);
   - `may()` answers from roles;
   - every control drawn from it, disabled with what it needs.
6. **The records.**
   - `Actor-Verified:` gains the provider's value (`local`, `oidc`, `access`, `api-token`,
     `break-glass`).
   - A new `Actor-Role:` trailer records the role and scope held.
   - The 20 record files that store an actor gain `provider`, `role` and `scope`, through
     one helper.
7. **API tokens** replace Cloudflare service tokens: scoped to a role on a network, hashed,
   shown once, expiring. The AI agent becomes an identity with its role (VIEWER plus
   `author`), the enforcement point Stage 8.3 needs.
   **The agent as a principal (DECIDED 2026-10-06, the operator; NSOT_PLAN 8.14):** the role
   model includes the agent with 8.14's limits: its own read-only service identity, and
   anything it does for a person capped at the LESSER of its own permissions and that person's
   role. **A test that the agent cannot do, through a person, anything that person's role
   forbids**, and none of the loosening actions on its own.
8. **Nothing in front** (C248). The production server, HTTPS, the loopback bind and
   the one trusted proxy hop are **9.S's** (gunicorn behind nginx, done FIRST). This step
   keeps the app's own half:
   - a CSRF token on every state-changing request;
   - Socket.IO restricted to the configured origin;
   - the app's OWN rate limits on sign-in, tokens and gated POSTs (nginx's are defence
     in depth, never the only layer);
   - trap and NetFlow sources allowlisted;
   - a test listing every place that assumed something in front, exact both ways.
9. **The operator's lab moves to Authentik** (the operator's host steps; NSOT_STAGE10_PLAN
   11):
   - Authentik runs as its own server;
   - NMAS, Grafana (`[auth.generic_oauth]`, a group to Editor for dashboard authors) and
     NetBox (python-social-auth OIDC) are its clients: one login for all three;
   - Cloudflare Access's identity provider points at Authentik, so the tunnel stays as
     transport only;
   - NMAS keeps its own service tokens for Grafana and NetBox;
   - no `auth.proxy`: the Stage 7 plan's embed design is superseded, measured absent from
     the code.

**Taking over a held device, by rank (the operator, 2026-10-04; R26's takeover once roles
exist; nothing to build before then):**
- **Rank:** a person may take over a hold only if their role includes the takeover
  permission AND ranks at least as high as the holder's.
- **A lower role is refused,** naming why and who can: "Held by an administrator: only an
  administrator can take it over. Ask <holder> or another administrator."
- **Every takeover is recorded** (who, why, from whom), AND it notifies the original holder.
- **Holds by the tool itself rank lowest:** scheduled jobs, and Stage 8's agent. Any person
  with the takeover permission may clear a stuck automated hold.
- **The test to write when roles land:**
  - a viewer cannot take over;
  - an operator cannot take over an administrator's hold (refused, naming the holder's role
    and who can);
  - an operator can take over another operator's;
  - anyone with the permission can take over a scheduled job's or the agent's;
  - each takeover writes the record with who, why and from whom, and notifies the holder;
  - each case also refused while the holder is still moving (the 10-minute lease, R26).

**Not in 9.I:**
- LDAP/AD (Stage 10, on demand: OIDC covers AD through Entra ID, AD FS or an IdP in
  front);
- SAML (not planned);
- the container delivery and the first-run wizard (Stage 10).

**Acceptance:**
- the operator signs in once through Authentik and reaches NMAS, Grafana and NetBox;
- a browser on the LAN reaches NMAS directly over HTTPS, with no tunnel, and every gate
  holds (P.3's unauthenticated sweep re-run, all refused);
- a viewer sees every mutating control disabled, saying the role it needs;
- the break-glass administrator signs in with Authentik stopped, and Needs attention says
  so;
- the in-front inventory test lists nothing assumed;
- C248 closes.

**Size:** 90 to 150 commits, 35 to 60 hours, estimated from P.3 (20 commits, the gate
table) and 7.1 (69 commits, an operation made whole across the app), which are the
closest finished stages. Checked against actuals when it closes.

**Depends on:**
- 9.S (HTTPS and the serving stack, which sessions and Secure cookies need);
- P.8 (a network role is scoped to what P.8 makes a network);
- Stage 7's v2 screens (the user screen, controls drawn from `may`);
- Stage 8.3 for the agent's role (step 7 provides the enforcement point either way).

#### 9.P — The platform layer: platforms as data, with declared capabilities (SCOPED 2026-09-30, the operator; not built)

The design is [NSOT_STAGE10_PLAN.md](NSOT_STAGE10_PLAN.md) section 12.
- **What it is:** one interface every platform satisfies (parse, render, push, save, facts,
  remove, rotate, bootstrap, errors, prompts, rollback). Each platform is a declarative
  DEFINITION: YAML validated by a schema, never code, executed by the program's tested
  engine.
- **What the engine holds:** the grammar families, the transports (line-merge, candidate
  commit), the rollback strategies, the probes and the judges.
- **IOS and IOS-XE are re-expressed as definitions**, the existing behaviour kept, every
  existing test green: that is the acceptance.
- **The seeds it gathers:** `platform_map`, bootstrap's sets, `removal_measured.json`,
  `PLATFORM_FOLDS`, `BLOCKED_PENDING_MEASUREMENT`, the parser `REGISTRY`.
- **It closes C250** (the ephemeral-line list in five copies).
- **Why Stage 9:** a refactor of the running program is proven on the operator's fleet
  before the release depends on it, the reason 9.I is here.
- **Size:** 60 to 110 commits.
- **Then:**
  - the second vendor (Arista EOS, cEOS) opens Stage 10;
  - the AI authoring pipeline is Stage 8's 8.10, run after this and P.10's sandbox.

#### 9.S — A production serving stack: gunicorn behind nginx (SCOPED 2026-09-30, the operator; not built)

**Why.** Every request is served by Werkzeug, Flask's development server
(`socketio.run(..., allow_unsafe_werkzeug=True)`, app.py). It is one process
and not hardened. That is survivable behind the operator's Cloudflare setup,
and not for software others expose on their own networks (Stage 10's
principle). **C189's cause, measured 2026-09-30 (via LAN, read-only):** the host
has no `simple-websocket`, so Flask-SocketIO's threading mode cannot serve a
WebSocket and the live channel stays on long-polling.

**1. Gunicorn, and the catch: the background work runs IN the web process.**
Measured 2026-09-30:
- **32 thread-start sites in 17 files.**
- **Started with the app, about 19 long-lived threads:**
  - the session reaper;
  - the event monitor;
  - the agent loop (6 thread sites in `agent_runner`);
  - the drift checker;
  - the Socket.IO heartbeat;
  - **11 reader threads:** app-pushed, baseline-usability, ci-verdict,
    freshness, grafana-alerts, grafana-dashboards, integrations, job-health,
    netbox-secrets, reachability, remote-publication;
  - the Prometheus targets keeper;
  - the SNMP trap receiver (UDP 1162);
  - the NetFlow receiver (UDP 9996).
- **Started by requests:**
  - capture and rotation jobs (`capture_job`'s registry);
  - the NetBox import and removal (`routes/netbox_safety.py`, 2);
  - the remote push (`routes/remote.py`);
  - the post-commit push and archive hooks (`hooks.py`, 2);
  - bulk operations (2);
  - the inventory refresh;
  - the terminal (retiring in 7.8);
  - Check again's run on request (`reader_job.request_run`).
- **In-memory state a second process would not share:**
  - `capture_job`'s registry (a job's result is read by id);
  - the reachability status (`device_status_cache`);
  - `reader_job`'s request registry and announcement times;
  - the SSH session pool and C97's per-device session budget;
  - the NetBox progress registry (C137);
  - the agent's pause event;
  - the Socket.IO connections the emitter announces to.
- **Already safe across processes**, because they are files with `flock`:
  - device holds (C98);
  - `filestore.PathLock` stores (C158);
  - the settings lock (C20);
  - the credential store (C157).

**Three phases (the operator, 2026-09-30, amended the same day for SCALE).**
- **Phase 1, today:** Werkzeug's development server, one process.
- **Phase 2, this item, the INTERIM step: ONE gunicorn worker with the threaded worker
  class (`gthread`).**
  - Flask-SocketIO stays in threading mode, with `simple-websocket` added to the lock,
    so WebSockets work.
  - **Not gevent or eventlet:** every device read here is a blocking Netmiko/Paramiko
    session on a thread. Monkey-patching a threaded program changes every one of them,
    and eventlet is in maintenance.
  - **One process:** every background job runs exactly once and every in-memory
    registry stays whole, which is what the program assumes today.
  - **Gunicorn adds:** a supervised worker, graceful restarts, and worker timeouts, in
    place of the development server.
- **Phase 3, the TARGET architecture for enterprise use: a web tier and a worker tier.**
  It is **Stage 10's item 10.W**, done BEFORE the release and aimed by 9.S's load test
  (step 6 below), never deferred as optional. **Why several gunicorn workers alone are not
  the answer:**
  - page loads are already cheap by design (the reader pattern: no per-device work per
    request), so more web workers help MANY USERS;
  - they do nothing for a large FLEET, whose cost is DEVICE WORK (reads, reachability,
    deploys, drift, rotation), which runs in background jobs.

**2. Nginx in front.**
- **TLS termination.** This is how "HTTPS built in" is delivered (it replaces
  the Caddy of NSOT_STAGE10_PLAN.md 4.1):
  - a certificate generated on first run;
  - or the installer's own;
  - ACME where the install is reachable for it. Nginx has no ACME client, so
    ACME is a companion (certbot on a timer, the HTTP-01 webroot or DNS-01),
    and the docs say so.
- **Limits:**
  - request size (`client_max_body_size`, from the largest legitimate upload,
    measured);
  - timeouts for slow clients;
  - **`limit_req` on sign-in and token endpoints.**
  - `proxy_read_timeout` is derived from the LONGEST MEASURED synchronous
    request, not guessed. The deploy apply waits out settle windows and BGP's
    hold time (up to 180 s more, C178), inside one request.
- **Security headers:** HSTS, `X-Content-Type-Options`, `Referrer-Policy`,
  `X-Frame-Options`.
  - **The CSP stays the app's:** it is per route (the v2 pages' strict policy),
    and nginx must never add a second.
- **Static assets served by nginx directly, with the app's existing rules:**
  - a versioned URL (the `?v=` `url_defaults` adds) is `public, max-age=30d,
    immutable`;
  - an unversioned one is `no-cache`;
  - HTML stays the app's (`no-cache` plus an ETag).

  A test compares nginx's rule with the app's, so the two owners cannot drift.
- **WebSocket proxying** (`Upgrade` and `Connection` headers, a long read
  timeout): closes C189, with `simple-websocket` in the lock.
- **The app binds 127.0.0.1** (an internal network in the release); only nginx
  faces the network.
- **Trusted-proxy headers, handled explicitly, never trusted by default:**
  - the app reads `X-Forwarded-For` and `X-Forwarded-Proto` ONLY when the peer
    is nginx's own address, one hop;
  - an installer's own reverse proxy in front of nginx is named in nginx's
    `set_real_ip_from`, and nothing else is believed;
  - the pinned no-ProxyFix test is rewritten to pin exactly this, including a
    forged header from anywhere else being ignored.

**3. Stated honestly: nginx is defence in depth, not the app's security.** It
can rate-limit sign-in and add headers. It cannot fix a missing permission
check. Both layers are required: 9.I's own rate limits, CSRF tokens and gates
stay in the app.

**4. What it touches, each named:**
- **How the app starts:** `flask-app.service`'s `ExecStart` becomes gunicorn,
  a host step, and nginx is installed and configured, another. In the release,
  containers.
- **The identity check after a restart (a CATCH):**
  - under gunicorn, systemd's `MainPID` is gunicorn's MASTER, and `/health`
    answers from a WORKER, another pid;
  - `nmas-deploy`'s `wait_for_running` and the updater (its root-owned copy of
    the same gate) decide "restarted" by the answering pid equalling
    `MainPID`, so both would refuse every restart;
  - `/health` also reports its parent pid, the identity rule becomes "answered
    by MainPID or a child of it", and both root-owned copies are re-installed:
    a `Host-Step:`.
- **The deploy gate's running-commit check:** unchanged. `/health` still
  reports the loaded commit, asked on loopback directly, not through nginx.
- **The Update button's updater:** its restart and `/health` confirmation, as
  above.
- **The cache-header logic** (`app.py`'s `after_request`): shared with nginx's
  static rule, as above.
- **The CSP:** unchanged, the app's alone.
- **The identity layer's peer (a CATCH):**
  - behind nginx every request's `REMOTE_ADDR` is 127.0.0.1;
  - the trusted-peer check (`cf_access_trusted_peers`, the replay defence)
    would then trust nothing or everything;
  - `identity.peer_address()` takes the client address from nginx's header,
    only when the peer is nginx.
- **Secure cookies and `url_for(_external=True)`:** they read
  `X-Forwarded-Proto` from nginx.
- **The log:** Werkzeug's access lines in `logs/device_manager.log` are
  evidence this project uses (they proved Check again's clicks reached the app,
  C244). Gunicorn's access log keeps that line.
- **The UDP listeners (traps, NetFlow) and the ZTP responder:** not behind
  nginx. In phase 2 they run once, in the one worker; in phase 3 (10.W) they move to the
  worker tier.

**6. MEASURE BEFORE THE REVAMP: a load test with a few hundred simulated devices**, the
last step of this item. It aims phase 3 (10.W) at where time actually goes, never at an
assumed bottleneck.
- **What it extends:** the existing scale work (`tests/fixtures/fleet_scale.py`,
  `scripts/nmas-scale-report`).
- **The simulator, on loopback (the suite's confinement allows it):**
  - an SSH simulator answering as IOS or IOS-XE devices from the REAL captured outputs in
    `tests/fixtures/operational/`, with a configurable connect latency and per-command
    time, including a slow device at the measured worst (s3's 13.7 s connect, C205);
  - FakeNetBox;
  - real git repositories holding hundreds of goldens.
- **Runs at 300 and 900 devices** (two points, so linear and worse-than-linear growth can
  be told apart), through the real code paths, recording wall time per step and where
  it goes. The steps:
  - a fleet capture (Save All);
  - a drift run;
  - one reachability cycle;
  - each reader's run;
  - a NetBox import;
  - a deploy batch;
  - a restore preview;
  - the git operations (a commit of N goldens, a history per device);
  - page loads with 1, 10 and 50 simultaneous users.
- **The numbers already measured, which it starts from:**
  - **at 900 simulated devices, one operation on every device:** 0.73 ms to read the
    inventory, 0.3 s to read every golden, **7.2 s for a `git log` on every device**, and
    **225 s for an SSH round trip to every device, one after another**;
  - the page: 647 KB fixed plus 2,239 bytes per device;
  - Save All on the real nine: **101 s** reading one device after another, **40.9 s** all
    at once (C188);
  - the slowest measured connect: 13.7 s (s3, C205).
- **Its report is the first input of 10.W**, stated in 10.W's plan before any of the split
  is built.

**5. Placement: Stage 9, BEFORE 9.I's sign-in work**, so the operator's lab
runs this way and is tested before Stage 10's release depends on it.
- 9.I's sessions and rate limits need HTTPS, which this delivers. 9.I's step 8
  keeps the app-side hardening (CSRF, the Socket.IO origin, the in-front
  inventory test), and its TLS and production-server parts are this item's.
- **In Stage 10's Compose file:** an nginx container, the web tier and the worker tier
  (10.W), with Redis (and a database where 10.W places state).
- **Size:** 25 to 45 commits, estimated from P.3's 20 (a change across the
  app's entry points), plus two host steps and the identity catches. Checked
  when it closes.
- **Depends on:** nothing unbuilt. It closes C189, and makes 9.I's HTTPS
  possible.

---

### STAGE 10 — A release other people can install and use (SCOPED 2026-09-30, the operator; not built)

**The scope is [NSOT_STAGE10_PLAN.md](NSOT_STAGE10_PLAN.md)**, governing as
NSOT_STAGE7_PLAN.md governs Stage 7. It comes after Stage 9, once functionality,
appearance, features and known defects are finished.

**The deliverable:** a clean public version someone else can download, install and use on
their own network, in a SEPARATE, NEW public repository, exported fresh (no history).
- This repository then goes private: that stops new viewers, not copies already cloned
  (nothing is forked).
- The instructor is added as a collaborator if the original is needed for grading.

**The principle: THE INSTALLER CHOOSES** how people reach it and sign in, so the program is
secure on its own with nothing in front. The operator's Cloudflare tunnel and Access are
one install's transport, not the design.

**Decided in the scope, each a recommendation for the operator to confirm:**
1. **Delivery:**
   - Docker images are the one artefact, run by Compose;
   - an install script (short, checksummed, published with its manual steps);
   - data in volumes, the key in its own;
   - per-feature networking: bridge for the app; host networking only for the optional ZTP
     responder and Kea;
   - optional bundled monitoring (Grafana, Prometheus, Loki, the exporter) and Oxidized,
     with NetBox and Kea connect-first;
   - a VM image only after the container route passes acceptance.
2. **Updates:**
   - the app NEVER holds Docker's socket;
   - a host-side root-owned helper (today's updater translated: request file, CI-signed
     images verified by digest, preview, a person confirms, roll back to the recorded digest,
     outcome shown);
   - the one command, with a copy button, where no helper is installed.
3. **Sign-in, pluggable:**
   - LOCAL accounts built in and the default (reversing AUTHZ's rejected user table, with
     the reason);
   - generic OIDC;
   - LDAP/AD later and on demand (OIDC covers AD through Entra ID, AD FS or an IdP in front);
   - SAML not planned;
   - Cloudflare Access an optional provider;
   - Authentik recommended and never bundled;
   - a break-glass local administrator, every use flagged;
   - API tokens for services.
4. **Roles in two layers:** INSTALLATION ADMINISTRATOR; per network, NETWORK ADMINISTRATOR,
   OPERATOR, VIEWER.
   - Implicit full rights for installation administrators by default, recorded, with a
     strict setting.
   - Every gate mapped to a role and scope.
   - Groups map to roles.
   - The AI agent is an identity with a role (VIEWER plus `author`).
   - Disabled controls say what they need.
   - Every action records the role and scope held (`Actor-Role:`).
5. **Secure with nothing in front:**
   - gunicorn behind nginx (Stage 9's 9.S): nginx terminates TLS (a certificate generated
     on first run, the installer's own, or ACME through a certbot companion), limits,
     headers, static assets, WebSockets; one gthread worker as the interim (phase 2), and
     the web tier and worker tier (10.W, phase 3) before the release, aimed by a load test
     of a few hundred simulated devices;
   - CSRF tokens, the Socket.IO origin, rate limits, headers, trap source allowlists;
   - a test listing everything that assumed something in front (C248).
6. **A first-run wizard over the existing Settings screens,** locked to a one-time setup
   code until the break-glass administrator exists. Its steps: sign-in with a test and group
   mapping, HTTPS, the key's backup made explicit, integrations (bundled or tested), the
   first network, devices, backups.
7. **Out or optional:**
   - containerlab and vrnetlab pieces;
   - the lab hosts;
   - the host systemd and sudoers pieces (replaced);
   - Proxmox and B2;
   - the lab's names;
   - 33 of 44 docs.
8. **Required first:**
   - 9.I;
   - SNMPv3 (C249);
   - C143;
   - no shipped community (C39, C141);
   - C139;
   - C248;
   - the AI off by default;
   - C71's sanitised fixtures;
   - C100.
9. **The repository:**
   - an allowlist export, CI that builds, scans, signs (cosign) and publishes images;
   - Apache-2.0 recommended (AGPL-3.0 if hosted improvements must come back; check the
     institution's policy first);
   - **the release repository becomes the only development repository at cut-over**, with a
     private lab repository for the operator's lab tooling.
10. **Acceptance:** a tester who has not seen the program installs it on a clean VM from
    the published docs alone, reaches it directly on the LAN, signs in by local and then
    OIDC, and manages a small example network through ten timed tasks. Every stuck point
    is a finding.
11. **Multi-vendor (its own item, section 12):**
    - the platform layer with platforms as DATA (9.P, in Stage 9);
    - Arista EOS proven by hand (early Stage 10);
    - the pipeline that adds a platform (capture, draft, prove against the device, a person
      approves, read tier then write tier after sandbox measurement), usable by a person and
      driven by the AI assistant in Stage 8's 8.10;
    - a third platform (Junos recommended) through the pipeline as its acceptance test, not
      a release blocker.

12. **AI providers, configured at once and switched at will (Stage 8's 8.11):**
    - the wizard's provider step (configure, Test, run the evaluation);
    - the documentation of where each provider sends data;
    - local models (Ollama or vLLM) highlighted as the air-gapped option.

**The Stage 9 part:**
- **9.S** (gunicorn behind nginx, first; it closes C189);
- **9.I** (identity, roles, running with nothing in front), in which the operator's lab
  moves to Authentik via OIDC: one login across NMAS, Grafana and NetBox, the tunnel kept
  as transport, and no `auth.proxy` (it does not exist in the code: NMAS draws Grafana's
  panels with its own token);
- **9.P** (the platform layer).

**Size, estimated from finished stages of the same kind, checked when each closes:**
- 9.S: 25 to 45 commits, plus its load test;
- 10.W, the web/worker split: 80 to 160 commits (no finished stage of its kind; aimed and
  re-sized by the load test);
- 9.I: 90 to 150 commits;
- 9.P: 60 to 110;
- 8.10: 30 to 60;
- Stage 10 proper, with the second vendor: 110 to 210, plus the acceptance run's findings.

No finished stage is of Stage 10's kind, so its range is the widest.

**10.W — The web tier and the worker tier: the target architecture for scale (SCOPED
2026-09-30, the operator; not built; done BEFORE the release, aimed by 9.S's load test).**
- **Why:** page loads are cheap by design, and a large fleet's cost is device work, which
  runs in background jobs.

**(1) A WEB TIER holding no background job:** many gunicorn workers, or several
containers, for many users. It serves pages and fragments from the stores and ENQUEUES
work; it never opens a device session.

**(2) A WORKER TIER running device work through a JOB QUEUE:**
- **What moves into the queue:**
  - captures, deploy and restore applies, rotations, persists, retirements, adoptions,
    onboarding's phase 2;
  - NetBox imports and removals;
  - drift runs, the reachability probes and the readers' reads;
  - the post-commit push.
- **The pool grows with the fleet.**
- **The per-device rules keep their owners:**
  - C97's session limit per device;
  - C98's one-operation-per-device hold;
  - a deploy batch stays SEQUENTIAL inside itself (its circuit breaker), while different
    devices' work runs at once;
  - a job's result is read by id from any web process.
- **Recommendation:** a small queue on Redis (RQ or Dramatiq), not Celery's weight, unless
  the load test says otherwise.

**(3) SHARED STATE both tiers use.** Today's files with `flock` are safe across processes
on ONE host (the C157 and C158 hardening), not across hosts.

| State | Today | Moves to |
|---|---|---|
| The job queue, job results (`capture_job`'s registry) | threads and memory | Redis |
| The announcement channel (C58) | the web process's Socket.IO emitter | Redis pub/sub (Flask-SocketIO's `message_queue`), so a worker's announcement reaches a browser on any web process |
| Device holds (C98) and the session budget (C97) | `flock`; in-process counts | Redis locks and counters with LEASES, so a holder that dies releases them, as the kernel does today |
| Reader values (`data/readers/*.json`), reachability status | files; memory | Redis (re-derivable, rule 10), or the database where a value must survive Redis |
| Audit trails and records (receipts, reveal, terminal, inventory edits, onboarding runs, rotation audit, update requests, the NetBox created, modified and removal records, break-glass exports) | append-only JSONL and JSON files | **a database** (PostgreSQL): many writers across hosts, and records are what must never be lost |
| Settings, the credential store, the inventory (`devices.csv`, `source.json`) | JSON and CSV files, `flock` | the database (secrets still encrypted with the Fernet key, which both tiers mount as a secret) |
| **The record: goldens, intent, templates, bindings, approvals, the monitoring profile, the manifest, tags and baselines** | **git, per list** | **STAYS IN GIT.** Versioned, pushed to the remote, restorable. The worker tier is its one WRITER (one queue lane per list's repository); the web tier reads committed state from reader values and the worker's answers, never from a shared network file system, where `flock` is unreliable |

**Its first step is 9.S's load-test report**, stated here before anything is built, so the
split targets the measured time (device I/O, git, NetBox, the readers).

**Supported shapes, stated:**
- one host running both tiers (the default install; the files' `flock` keeps working for
  what stays in files);
- several hosts once the state above has moved.

**Size:** 80 to 160 commits. No finished stage is of its kind; the load test re-sizes it.

**Depends on:** 9.S (phase 2, and the load test).

**Depends on:**
- Stage 9 (9.I and 9.P first for this purpose, and the required list);
- P.8 (a network role is scoped to a P.8 network);
- Stage 7 complete (the wizard reuses its screens and manual);
- Stage 8.3 (the agent's role), or the AI off;
- P.10's sandbox (the second vendor's write tier and 8.10).

### P.19 — SDN controller support (RECORDED 2026-10-02, the operator; NOT RESEARCHED, NOT BUILT; placed at the END of the plan)

**Placement:** last. After every current feature, after the AI work (Stage 8), and after
Stage 10's platform-driver layer (NSOT_STAGE10_PLAN 12), on which it depends. **Recorded
only:** no research and no building now, because controllers change, so the research is
done at the time it starts.

**The goal:** manage networks that include an SDN controller and its switches.

**Controllers to support:**
- Floodlight, ONOS, OpenDaylight, Ryu and Faucet;
- whatever the CSCI 5280 lab VMs run;
- as reference designs (not support targets): Cisco ACI/APIC, VMware NSX, Juniper Apstra,
  Arista CloudVision.

The research states each controller's maintenance status honestly (Floodlight's activity,
for one), so support is chosen knowingly rather than for a project nobody maintains.

**The model: the CONTROLLER is the managed device**, through its northbound API, and its
switches are its children.

| NSoT concept | For a controller |
|---|---|
| Intent | controller-level objects |
| Golden | an export of the controller's state |
| Drift | TWO layers: the controller against intent, and each switch's flow tables against the controller's view |
| Deploy | an object diff, previewed, confirmed by hash, verified by read-back, rolled back |

**One owner.** The controller owns the flows it programs; the tool never writes a flow to a
switch directly. The tool may manage a switch's OWN configuration (its controller address,
OpenFlow version, management) through OVSDB or NETCONF.

**Hybrid networks** (CLI devices plus an SDN fabric) appear in ONE inventory, one Device page
and one topology, with the controller's topology drawn as a layer (P.11).

**The architecture: not a parallel tool.** It rides on Stage 10's platform-driver layer,
generalised from line-oriented CLI to a STRUCTURED, API-driven model, in which a platform
declares whether it is managed by CLI or by API. The same generalisation serves API-driven
devices that are not controllers (Arista eAPI, NETCONF, gNMI), so it is built once for both.

**When it starts:**
1. **Research first.** Per controller: its API, object model, export, authentication,
   topology and statistics. Then the mapping in the table above, and a costing against the
   driver layer as it then exists.
2. **Then a lab plan**, on the course's Mininet and controller VMs (Proxmox VMs 201 and 202).
   - Measure the lab host's contention BEFORE and DURING the runs (the lab host is shared
     with the fleet, and C93's slow clocks are its symptom).
   - Never schedule a run that overlaps the nightly backup.

**The lab is course-specific; the product support is not** (NSOT_STAGE10_PLAN 6.0b's note):
the VMs, their names and the course belong to the lab-tooling area, and the controller
drivers belong to the product.

---

## Sequencing notes and deferred defects (moved from CLAUDE.md on 2026-10-02)

docs/NSOT_PLAN.md's "Open findings register" and "Known defects deferred to later phases"
sections, moved verbatim. They are a SNAPSHOT of decisions as each was recorded: their
status sentences ("7.1 next", "steps 3 and 4 are next") are superseded by this plan's
own sections and the register's Count. The register's rules live in OPEN_FINDINGS.md.

### Open findings register

**[docs/OPEN_FINDINGS.md](docs/OPEN_FINDINGS.md) is the list of things
measured, recorded and not fixed, with no line item in any stage.** Each was
written into prose beside the thing it was found next to — the right place to
explain *why* it is true and the wrong place to keep a list, because prose
accumulates invisibly and knowing what is outstanding required having been
present when each was recorded. **Its *Count* section is the ONE statement
of how many rows are open and in which bucket, and this file points there
rather than restating it** (the operator, 2026-09-28: a restatement goes
stale by construction; this file listed C17 as an open 7.2 gate a day after
the register closed it, and the line was quoted from here as fact). **The
open count is DEFERRED work**: a row a stage owns lives in *Scheduled*, and
`test_register_hygiene.py` refuses an open row placed in a stage (26 of 61
had been). Every live row opens its status with its bucket, and
`test_register_hygiene.py` refuses one without it: **a new finding gets its
bucket the turn it is recorded, with the criterion applied.** The first
triage was a one-time sort, and the functional/lab/minor split replaced the
severity axis for every later row, so C148 (blocking the central loop) was
filed as work for 7.3. B8 (the backups' only decryption key on one laptop)
closed on measurement. **The operator's decision, 2026-09-28: this is a lab, so the work is
features, functionality and design, and security is DEFERRED, not
abandoned.** The plan is the functional path (R1, R2b, 7.2 from C54, 7.3
with C50, then 7.4 onward). NSOT_PLAN's Stage 9 holds hardening, labelled
(L) "safe here because it is a lab" (FIRST on a real network) or (M)
minor, with the triggers that make (L) urgent again. Before the triage: **59 open at 2026-09-27**, counted from the rows: 53 recorded only in
prose, 6 in the plan without a stage. C3 and C4 are closed; A1 and C5 are
scheduled as NSOT_PLAN P.2 and 6.5. The earlier "15" was off by one,
because it adjusted a previous count instead of counting.

**Sequencing decided 2026-09-25** ([docs/NSOT_PLAN.md](docs/NSOT_PLAN.md)):
**Stage 5 is folded into 7.3** (renumbered from "7.5" on 2026-09-27:
NSOT_STAGE7_PLAN.md governs, and monitoring is the Device page), so the
views are built once, with its paragraph enumerated as 7.3-a…f, and 7.3-f
already done by P.1. Two standalone items come **before Stage
7**: **P.1** switch syslog (stopped 2026-09-09; a pipeline defect, not a
screen) and **P.2** NetBox backup with a tested restore (A1). The service
unit's hardening is **6.5**. **P.1 COMPLETE 2026-09-25**: a silenced s4 alerted alone, 1,118 s after its last heartbeat, between its second and third missed heartbeat as designed; nine devices heartbeating on per-device measured windows. **P.1 measured first**: nothing stopped. Every device
has run `logging trap critical` since 8 Sep, and the pipeline delivers
exactly what that level sends. It needs a trap-level decision and a
per-device EEM heartbeat, not a repair. **Decided**: `notifications` in
intent; an EEM 300 s watchdog heartbeat; heartbeat, trap level, host and
source-interface as ONE template block that onboarding gives every device;
Grafana alert rules generated from NetBox, with NoData = alerting. **P.2 is
built** ([docs/NETBOX_BACKUP.md](docs/NETBOX_BACKUP.md)); its first live
restore test failed correctly (`docker exec` without `-i`), which the mocked
seam could not have shown. An item leaves by being fixed,
scheduled or closed with a reason — never by being forgotten, and anything
recorded as *"not applied"*, *"noted, not yet addressed"* or *"left open"*
belongs there the same day it is written.

**Stage 7 is rethought, and P.3 and P.4 come first** (decided 2026-09-26).
[docs/NSOT_STAGE7_PLAN.md](docs/NSOT_STAGE7_PLAN.md) governs Stage 7. It is
organised around the task list
([docs/NSOT_TASKS.md](docs/NSOT_TASKS.md)), never around subsystems, and
written against the feature audit
([docs/NSOT_FEATURE_AUDIT.md](docs/NSOT_FEATURE_AUDIT.md)) and the CI design
([docs/NSOT_CI.md](docs/NSOT_CI.md)). **P.3** makes every device-changing
path guarded or gone (B12, B11, D5, D4, C23); **accepted 2026-09-26** at
`5b087c4`, every item observed and all eleven controls firing, and
**COMPLETE** once the operator's tunnel deploy committed with `Actor-Verified:
access` on two paths. **P.4** cuts Jenkins: steps 1 and 2 are built
(2026-09-26); steps 3 and 4 (GitHub Actions, `nmas-deploy` gating) are next. The
agent becomes an on-call responder (Stage 8): it triages autonomously,
PROPOSES fixes as ordinary plans, and never confirms its own.

**P.5 COMPLETE (template approval scheme 3). P.6 COMPLETE 2026-09-27: Lab 8
is demonstrated end to end** (ZTP: a reservation the tool wrote, a config
the tool served, a device reached, rotated, saved, promoted, and reboot-safe;
teardown clean). The ledger is in [docs/P6_ZTP.md](docs/P6_ZTP.md) section
8. **Stage 7.0 is BUILT (2026-09-27)**, awaiting its host check (the three
panels updating live): reachability, invalidation, payload-to-render and
the nine-concept harness, each with a measured allowlist that only shrinks
([docs/NSOT_STAGE7_PLAN.md](docs/NSOT_STAGE7_PLAN.md), "7.0 built"). 7.1
next. The gate list is **CONFIRMED 2026-09-27** and lives in
[docs/NSOT_PLAN.md](docs/NSOT_PLAN.md) (the Stage 7 dependency notes); each
gate's current state is its row in the register. **Neither is restated
here**: the copy that was here listed C17 and E4 as open 7.2 gates for a
day after both had closed on measurement, and was quoted as fact
(2026-09-28). Two records of one fact, the wrong one nearer to hand.
Stage 8's triage trigger is decided as a READ, never an inbound push
(NSOT_PLAN 8.6): one reader job caches Grafana's alert instances; the
page and the agent both consume it; grouping is on the ONSET
(`startsAt` minus the rule's window), because per-device windows fire one
Loki outage up to 536 s apart.
**Two agent designs argued and recorded 2026-09-27, neither built**
(NSOT_PLAN 8.7, 8.8):
- **8.7, the agent closing drift: PROPOSE-ONLY.** The class ("re-apply a
  program a person already confirmed") fails the autonomy test. The one
  instance on record, s4's timer removed by hand for P.1's acceptance, passes
  all six of its conditions. The alert-triggered drift check (now in 8.6)
  makes a revert arrive in seconds, during the repair that caused the alert.
  `reassert` is named, with `Actor-Verified: delegated`, so a grant cannot
  arrive under another name. The answer is **"not yet", with a checklist**
  (the device logs its own config changes to the tool, the tool's account
  is used by the pipeline alone, every other writer is attributable, deploy
  receipts exist), so a later review checks the list instead of re-arguing
  it. Recent human activity withholds even the proposal.
- **8.8, a second reading before confirm: ADVISORY.** It is cheap and never
  blocks. Its states can never draw green (`warns`, `no_warnings: not a
  clearance`, `not_reviewed`). Its warnings cite program lines and carry no
  remedy, which is the structural answer to injection through device text.
  The deterministic management-path flag is built first.
  Its warnings, and its CLEARANCES, are triage context (8.6): "reviewed,
  no warnings, then broke" is surfaced preferentially, and a quiet deploy
  counts only as far as something was watching.
- **C60, the deploy record, now gates 8.6, 8.7 and 8.8.** It is a receipt
  at apply (proposed for 7.1) plus a follow-up window that closes the row
  and states WHAT WAS WATCHING (a job behind 7.1). No model is involved.
  Handing that history to the model is a later decision, and the test for
  it is whether a person learns anything from the last fifty rows.
- **The terminal is REMOVED, not split** (decided 2026-09-27,
  NSOT_FEATURE_AUDIT 3b, superseding 3a's split). A source of truth has no
  pane that goes to the device directly: whatever happens in it happens to
  the network and not to the record, and even read-only the affordance
  teaches the wrong habit. Its audit log showed it was never used for a
  read, only for the one hand change that broke r2. It goes in 7.8 with its
  routes, socket events, session code and tab; the Device page's allowlisted
  command box (7.3) is the one way to ask a device a question; break-glass
  is the console plus the break-glass record; the `break_glass` gate kind
  retires with it. The C61 allowlist goes on `/run_command` and
  `bulk_execute` as planned.
Stage 6 does not close first. 6.1, a live exposure, is fixed on its own
schedule, and 6.2 comes before Stage 8. NSOT_STAGE7_PLAN.md's numbering
holds.

**Authorization is decided, and built later**
([docs/NSOT_AUTHORIZATION.md](docs/NSOT_AUTHORIZATION.md), 2026-09-26).
Today any verified person may do every gate kind.
- **Roles:** viewer; operator (`author` + `confirm`); approver (`approve`);
  administrator (`configure`). `reveal`, `break_glass` and `publish_remote`
  are grants to named people.
- **The gate kind `approve` must split into `author` and `approve`** before
  any role map, because today one kind covers both editing a template and
  approving it.
- **Separation of duties is per ARTIFACT** (a revision's author may not
  approve it), from VERIFIED attribution only.
- **The mode and the map are host-side**, like the gates.
- **Stage 7 draws every gated control from `may`**, disabled with its reason
  when refused, never hidden.

### Known defects deferred to later phases

Verified, deliberately not fixed yet. Recorded in full in
[docs/NSOT_WRITEUP_NOTES.md](docs/NSOT_WRITEUP_NOTES.md); the AI-side items
are **Stage 8** in [docs/NSOT_PLAN.md](docs/NSOT_PLAN.md), which is last by
design so the tool library describes a finished system.

- AI prompt examples reference another project's PE/P/MPLS topology (Stage 8.5)
- **The AI tool layer has no pre-execution authority gate.** `execute_tool()`
  dispatches on the tool name; `request_approval` is a tool the model
  *chooses* to call, not an interception. The agent cannot mint identities
  because `resolve_identity(allow_new=False)` enforces that at the identity
  layer — not because anything checks what the agent may do. Stage 8.3 makes
  the allowlist real in code (no credential rotation, no template approval,
  no remote push, no baseline re-apply, no deploy apply).
  **P.3 step 8 (2026-09-26) removed what it could reach meanwhile.**
  - **24 tools are removed from the list AND the dispatch:** device push,
    restore and replay, commits, self-modification, self-writing knowledge
    and the CCIE base, report files, and writes to the tool's own settings.
  - **The three `execute_*` tools run only read-only commands**
    (`_read_only_refusal`: show, ping, traceroute, dir, more). Config mode,
    every other verb and a line break are refused, checked before any
    session opens. **The check was the first word only until C61
    (2026-09-27)**: `| redirect tftp://` let a "show" send the device's
    config to another host, and `| redirect flash:` wrote to the device, so
    "cannot change a device" was false in two directions. It is the whole
    command now, in `modules/readonly_commands.py`.
  - The Jenkins tools are P.4's. The prompt still names the removed tools 77
    times (C30, Stage 8.5).
- **The unguarded golden replay was reachable from TWO GUI buttons, not only the AI** (register D5). **Fixed by P.3 step 3**: both buttons open the guarded restore preview at HEAD, and the two routes are gone. The AI's tool of the same name was removed by step 8.
- **(REMOVED by P.3 step 8.)** `restore_golden_config` was a fourth config-push path: whole golden
  replayed in config mode with no confirm hash, no merge-only check, no ASCII
  guard, no dangerous-line authorisation, no snapshot, no rollback, no
  breaker, and `device_ips: ["all"]` targets the fleet. The same shape was
  removed from the approval queue's `revert_to_golden`, which hands off to
  the confirmed restore path; the AI's copy was not part of that correction
  (Stage 8.3).
- **`detect_config_drift` is a third drift implementation**, carrying the
  pre-3.3b shape — no inventory accounting, no named skips (Stage 8.2).
- **The background agent was not dormant — it was FAILING, for four weeks.**
  Last recorded run 2026-08-28 23:26, `tool_call_count` 0, failing at the
  first API call with `anthropic-workspace-id is required…`. The record lived
  only in `data/agent_activity.json`; the log line was INFO with
  `success=False` inside the format string; and the badge said **Active, in
  green**, because the status logic had four states and none of them was
  *broken*. `background_agent_enabled` is now **false** in the settings file
  — set before the rotated API key (created in a workspace) could
  accidentally repair it and wake a month-old tool library against a rebuilt
  system. It stays off until Stage 8.
- **"Success" must mean something happened.** Measured across the agent's
  whole recorded history: **27 runs, `tool_call_count` zero in every one**,
  and the single `success: true` had no tools, no summary and no errors.
  `success` meant *"no exception reached the top of `run_background_task`"* —
  a fact about the interpreter, not about the network — and a backward
  failure streak stopped dead on that entry, which is why the badge showed
  nothing even after the route was fixed. **Diagnosed, not inferred:** the
  loop breaks on `_user_is_active()` **without appending anything**, while
  the model-side `interrupted` event a few lines below always appended. One
  exit path recorded and the other did not. Runs now carry an `outcome` —
  `ok` / `failed` / `interrupted` / `inconclusive` — with a reason; `success`
  derives from it; and the streak counts back to the last run that actually
  **worked**, so an interrupted or inconclusive run neither ends it nor
  inflates the failure count. Historical entries are classified from what
  they carry, and land in `inconclusive` rather than being guessed as
  interrupted.
- **Nothing in the AI tool library has ever executed in production** — zero
  tool calls across all 27 recorded runs, now reported as
  `health.tool_calls_total` and stated on the panel. **Stage 8 is therefore
  not "check the tools still fit"; it is their first run.**
- **Agent failures surface, like `last_push_failure`.**
  `agent_runner.failure_health()` computes the streak from the activity log;
  `get_status()` carries it plus `enabled`; a failed run logs at **ERROR**
  naming the error and the streak; the badge turns red with the count; the
  **tab** badge shows it so it is visible without opening the tab.
  **`same_error` is the load-bearing field** — one failure is an incident, a
  dozen identical ones is a configuration problem that will not fix itself.
- The `missing_golden_configs` trigger that fired the last failed run was
  **stale**: it came from the legacy enumeration, so the devices it named as
  missing a golden **had** one in `config_repo/`. Fixed by 3.3a; pinned by a
  test, because it is the trigger that fires first when the agent returns.
- **A test needle shorter than its haystack's noise is a coin, not a check.**
  `test_the_ciphertext_is_not_the_plaintext` asserted `b"r1"` — two bytes —
  absent from 953 bytes of ciphertext, and failed **1.40%** of runs against
  1.45% predicted by chance (measured, 2000 trials). Needles are now ≥4 bytes
  and the short ones are excluded deliberately, with a test pinning the
  exclusion. Same cause as `redact.py`'s 8-character floor from the other
  direction: there a short value corrupts, here it cries wolf.
