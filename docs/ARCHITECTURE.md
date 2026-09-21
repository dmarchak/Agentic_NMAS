# Architecture

How Agentic NMAS is put together: entry points, modules, and the paths data
takes through them. See [NSOT_PLAN.md](NSOT_PLAN.md) for where it is heading.

---

## Entry points

| Entry point | Purpose |
|---|---|
| `app.py` | Flask app, SocketIO, all pre-existing routes. Creates `app`, registers blueprints, starts background daemons. |
| `routes/` | Blueprints for everything added from Phase 0 onward. |
| `modules/check_runner.py` | Standalone CLI invoked *by Jenkins*, not by the web app. |
| `modules/drift_check.py` | Scheduled drift comparison; needs no Claude API. |

`app.py` is monolithic by design for what predates the NSoT work. New routes go
in `routes/`; new UI goes in `templates/partials/`.

## Startup sequence

```
app.py import
  ├─ modules.config            paths, settings, env overrides
  ├─ ping_worker started       background online/offline tracking
  ├─ Flask app created         (PyInstaller-aware template/static paths)
  ├─ SocketIO attached         async_mode="threading", manage_session=False
  ├─ routes.register_blueprints(app)
  ├─ settings_schema.migrate() seed defaults, encrypt legacy plaintext secrets
  ├─ … all route definitions …
  └─ _start_background_daemons()
        ├─ SNMP trap receiver   (UDP 1162)
        ├─ NetFlow collector    (UDP 9996)
        ├─ event monitor
        └─ agent_runner         autonomous AI daemon
```

## Data ownership

| Data | Owner | Location |
|---|---|---|
| Device inventory + credentials | NMAS | `data/lists/{slug}/devices.csv`, Fernet-encrypted fields |
| Settings, integration config | NMAS | `data/user_settings.json`, secrets Fernet-encrypted |
| Encryption key | NMAS | `data/key.key` — **back this up** |
| Golden configs | NMAS | `data/lists/{slug}/golden_configs/` **and** `config_repo/` (two stores; Phase 2 unifies) |
| Sites, devices, interfaces, IPs | NetBox | remote; NMAS reads freely, writes are gated |
| NMAS-created NetBox object ids | NMAS | `data/netbox_created_ids.json` |
| Metrics, logs, config history | External tools | Phase 5 |

## Per-list data layout

```
data/lists/{slug}/
├── devices.csv              inventory; password/secret Fernet-encrypted
├── variables.json           discovered network facts
├── golden_configs/          <hostname>.cfg, 4-line NMAS header
├── config_repo/             git repo, header-stripped copies
├── backups/
├── approval_queue.json      human review for destructive AI actions
├── jenkins_pipelines.json
└── collector_config.json    SNMP/NetFlow ports, communities
```

## Principal flows

### Config push (`/configure/apply`)

```
generate_config_commands()   modules/configure.py
  → safety check             block dangerous commands before any SSH
  → pre-backup               rollback always possible
  → push                     canary device first, then fleet
  → save golden              per device
  → Jenkins verify           async; advisory, never blocks the response
  → audit log
```

`modules/pipeline.py` implements a stricter 9-stage version of this with
rollback and ordering enforcement. It is fully tested but **not yet wired into
the UI** — Phase 3 connects it.

### AI agent

```
run_chat()                   modules/ai_assistant.py
  → read-first               golden configs + variables before any SSH
  → tool loop                auto-continues until the task completes
  → destructive actions      routed through approval_queue.py
```

`agent_runner.py` runs the same machinery autonomously in the background and
pauses when a user opens the chat panel.

### NetBox import (gated)

```
Click "Import to NetBox (discovery)"
  → routes/netbox_safety.py  preview
      └─ sync_list_to_netbox(dry_run=True)
           └─ netbox_guard.dry_run()      thread-local
                └─ _nb_post/_nb_patch     record intent, return synthetic id
  → modal shows create/update preview
  → confirm (optionally enabling writes)
  → sync_list_to_netbox()                 background thread
       └─ _nb_post  → assert_writes_allowed()
                    → inject nmas-managed tag
                    → record created id
```

The dry run is the same code path as the real import, which is why the preview
is accurate.

### NetBox removal (provenance-gated)

```
remove_list_from_netbox(list_name)
  → read data/netbox_created_ids.json
  → for each endpoint, in referential-integrity order:
       fetch object → still tagged nmas-managed?
         yes → delete
         no  → report as skipped (operator-owned)
```

Both conditions are required. Neither alone is sufficient: a tag can be added by
hand, and the id record can go stale against a rebuilt NetBox.

## Write chokepoints

Every NetBox write in the codebase passes through one of three functions in
`modules/netbox_client.py`:

| Function | Gate behaviour |
|---|---|
| `_nb_post` | raises `NetBoxWriteBlocked`; tags and records on success |
| `_nb_patch` | raises `NetBoxWriteBlocked` |
| `_nb_delete` | logs and returns `False`; forgets the id on success |

Gating these three gates the entire surface — which is what makes
`test_netbox_write_gate.py` a meaningful proof rather than a spot check.

## Settings

```
data/user_settings.json
  ├─ settings_schema_version
  ├─ plain values
  └─ secrets, stored as  enc:v1:<fernet-token>
```

`modules/settings_schema.py` owns defaults, validation, and migration.
`modules/secrets_store.py` owns encryption. Resolution order for portability
settings is **environment → user setting → OS-appropriate default**.

## Outside this repository: the config-persistence pipeline

**Not part of this codebase, and the NSoT depends on it being true.** Documented
here because the repo should at least say it exists, what it guarantees, and
where it connects.

### Why it exists

Containerlab nodes are ephemeral. `write memory` saves to the *container's*
NVRAM, but `containerlab deploy --cleanup` boots every node from the
**startup-config files on the containerlab VM** (`10.0.0.210`,
`~/labs/lab/configs/`). Anything not in those files is lost on redeploy.

So there are two different claims, and only one of them was ever guaranteed:

| claim | guaranteed by |
|---|---|
| "this is what the device is running" | the NSoT golden repo |
| "this is what the device will boot as" | **nothing, until this pipeline** |

### The pieces

| path (on the NMAS, `10.0.0.211`) | what |
|---|---|
| `~/lab-configs/oxidized-to-config.sh` | the sanitiser/sync, 318 lines |
| `~/bin/clab-sync` | `flock -n` wrapper, runs it with `--yes` |
| `/etc/systemd/system/clab-sync.service` | `Type=oneshot`, **`User=dmarchak`** |
| `/etc/systemd/system/clab-sync.timer` | `OnBootSec=10min`, `OnUnitActiveSec=30min`, `Persistent=true` |

### What it does

Reads Oxidized's stored configs from its git output backend
(`/opt/oxidized/rcn-lab.git`, files named by **device IP** per `router.db`) and
sanitises them into replayable startup-configs:

- strips PKI certificate chains, the `clab-mgmt` VRF and `GigabitEthernet1` on
  routers, banners, `license`/`platform` lines, `call-home`;
- **re-injects `no shutdown`** into any interface carrying an address that does
  not explicitly say `shutdown`. A running-config records `shutdown` but never
  `no shutdown`, so harvesting a working device and replaying it brings every
  routed port up administratively down. This cost a full rebuild on 2026-08-30.

Then validates every file before anything is copied — a failure copies nothing
and fails the unit:

- exactly one `end`, exactly one `hostname` (an empty file has neither, and the
  older check could not tell that from a good one);
- no management-interface, certificate or banner leakage;
- no addressed interface missing `no shutdown`;
- a **truncation guard**: interface and `router` block counts in Oxidized's copy
  must survive into the output. Proven by fault injection — a simulated
  truncation at the first `router` block passed every older check on all nine
  devices, and the guard refused all nine.

On success: rsync to a stage dir on the clab VM, diff, timestamped backup, copy,
and commit in `~/labs/lab` (identity `clab-sync`). The file header carries
Oxidized's **commit sha**, not a timestamp — a timestamp made every run "change"
every file.

**No manual approval, by design.** Validation is the gate, and the output only
affects the *next* redeploy — it never touches a live device.

### How it connects to the NSoT

```
device ──SSH──> Oxidized ──git──> /opt/oxidized/rcn-lab.git
                                        │
                              oxidized-to-config.sh (sanitise + validate)
                                        │
                              10.0.0.210:~/labs/lab/configs/*.cfg
                                        │
                              containerlab deploy --cleanup
```

Two consequences the NSoT must respect:

1. **Oxidized logs into the same devices with the same account NMAS uses.** Its
   credentials are a *single global* `username`/`password` in
   `/opt/oxidized/config`; `router.db` maps only `name: 0` (the IP). So rotating
   that account breaks Oxidized for every device at once unless Oxidized is
   updated too — see `docs/NSOT_SET_CREDENTIAL_PLAN.md` §GAP 1.
2. **If Oxidized's login fails, the startup files silently stop updating.** The
   sync reads Oxidized's repo, so a credential failure upstream looks like "no
   changes" downstream, not like an error.

### It should be version-controlled

The script, the wrapper and the units live only on the NMAS filesystem. They are
load-bearing — the truncation guard above is the kind of logic whose history
matters — and they have no history at all. Once Phase 2b lands, `infra/` in the
per-list config repo is the natural home, which also means they reach the
private remote with everything else.

## Conventions

- Return dicts shaped `{"ok": bool, "error": str, ...}`
- Module-level `log = logging.getLogger(__name__)`
- Integrations never raise into a request handler; they return `ok: False`
- No IPv4 literals in `modules/integrations/`, `modules/nsot/`, `routes/`
- `pathlib`/`os.path` only — no hardcoded separators or drive letters
