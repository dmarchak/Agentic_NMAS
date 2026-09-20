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

## Conventions

- Return dicts shaped `{"ok": bool, "error": str, ...}`
- Module-level `log = logging.getLogger(__name__)`
- Integrations never raise into a request handler; they return `ok: False`
- No IPv4 literals in `modules/integrations/`, `modules/nsot/`, `routes/`
- `pathlib`/`os.path` only — no hardcoded separators or drive letters
