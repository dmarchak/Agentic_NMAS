# Changelog

All notable changes to Agentic NMAS.

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
NSoT phases refer to [docs/NSOT_PLAN.md](NSOT_PLAN.md).

---

## [Unreleased] — NSoT Phase 0: Foundation, portability, and safety

Phase 0 adds no user-facing features. It makes the codebase safe to build the
rest of the NSoT work on: NetBox writes become fail-closed, secrets get
encrypted, the app becomes deployable on headless Linux, and the test suite
becomes runnable.

### Security

- **NetBox writes are now fail-closed.** `netbox_allow_writes` defaults to off.
  All writes funnel through three chokepoints (`_nb_post`, `_nb_patch`,
  `_nb_delete` in `modules/netbox_client.py`), each of which consults the new
  `modules/netbox_guard.py`. With the gate off, no code path can write.
- **Removal can no longer delete records NMAS did not create.**
  `remove_list_from_netbox` previously collected devices with `site_id=` and
  deleted everything it found — plus the site, region, and VRF — regardless of
  origin. It now deletes only objects that are both tagged `nmas-managed` and
  present in NMAS's own created-id record (`data/netbox_created_ids.json`).
  Anything else is reported as skipped.
- **Deleting a device list no longer cascades into NetBox.** That cascade
  previously ran silently on every list delete. It is now opt-in via the
  `netbox_remove_on_list_delete` setting or a `remove_from_netbox` flag on the
  request; without it, NMAS just stops tracking the objects.
- **Settings secrets are encrypted at rest** (`modules/secrets_store.py`) using
  the existing Fernet key at `data/key.key`. The NetBox API token was previously
  written to `data/user_settings.json` in plaintext; it is upgraded in place on
  first run. Secrets are never logged and are write-only in the UI.

### Added

- `modules/netbox_guard.py` — write gate, thread-local dry-run mode, and
  created-object provenance tracking.
- `modules/secrets_store.py` — Fernet encrypt/decrypt for settings values, with
  legacy-plaintext passthrough and a non-fatal path for an unreadable key.
- `modules/settings_schema.py` — defaults, JSON Schema validation, and a
  versioned forward migration. Every default reproduces prior behaviour.
- `modules/integrations/` — a shared `IntegrationClient` base plus clients for
  NetBox, Prometheus/Thanos, Grafana, Loki, Oxidized, Kea, an external topology
  service, the NSoT git repo, and an S3-compatible archive. Phase 0 ships
  `test_connection()` only; read clients land in Phase 5.
- `modules/jenkins_shell.py` — single source of truth for `bat` vs `sh` steps,
  the matching null device, and path separators.
- `routes/` — Flask blueprint package with `register_blueprints(app)`.
  - `routes/settings_integrations.py` — Integrations settings and status API.
  - `routes/netbox_safety.py` — dry-run preview and confirm/apply endpoints for
    import and removal.
- `templates/partials/settings_integrations.html` — the Integrations settings
  panel, plus server, collector, and monitoring-identity settings.
- `templates/partials/netbox_safety_modal.html` — preview-and-confirm modal.
- `pytest.ini` — sets `pythonpath = .`.
- Tests: `test_netbox_write_gate.py`, `test_settings_migration.py`,
  `test_integrations_base.py`, `test_portability.py`, `test_no_ip_literals.py`
  (89 new tests; 209 total, all passing).
- Docs: `docs/ARCHITECTURE.md`, `docs/DEPLOY_LINUX.md`,
  `docs/NSOT_WRITEUP_NOTES.md`, this changelog.

### Changed

- **"Sync to NetBox" is now "Import to NetBox (discovery)".** Clicking Import or
  Remove runs a read-only preview first and shows exactly what would change;
  confirming is what enables writes. The buttons are never disabled, so the gate
  never presents as a broken button.
- `modules/config.py`: bind host, port, browser auto-open, and TFTP root now
  resolve environment → user setting → OS-appropriate default. New env
  overrides: `NMAS_HOST`, `NMAS_PORT`, `NMAS_HEADLESS`, `NMAS_TFTP_ROOT`.
- Jenkins pipeline generators (`configure.py`, `pipeline_builder.py`,
  `config_git.py`) emit the configured step shell. **The default remains `bat`
  and generated XML is byte-identical to the previous output**, verified by test.
- `sync_list_to_netbox` and `sync_all_lists_to_netbox` accept `dry_run=`.
- `remove_list_from_netbox` accepts `dry_run=` and `forget_only=`.
- `get_netbox_config()` returns `allow_writes`; `save_netbox_config()` accepts it
  and no longer wipes a stored token when passed an empty one.
- `CLAUDE.md` rewritten — it claimed there was no test suite, listed stale line
  counts, described tracked modules as untracked, and omitted `pipeline.py`.

### Fixed

- **`requests` was missing from `requirements.txt`** despite being imported at
  module level by `netbox_client.py`. A clean install crashed on every NetBox
  path. Also pinned `PyYAML` (previously only transitive via netmiko) and added
  `jsonschema`.
- **`pytest tests/` failed to collect** with `ModuleNotFoundError: No module
  named 'modules'`. Only `python -m pytest` from the repo root worked. Both work
  now.
- **`config.py` created a directory named `C:` in the repo root on Linux.** It
  ran `os.makedirs(TFTP_ROOT)` at import time against the Windows default
  `C:/TFTP-Root`. The directory was present in the working tree and not
  gitignored. Removed, gitignored, and replaced with an explicit
  `ensure_tftp_root()` called at the point of use.
- Removed the hardcoded default TFTP server IP, which was one specific lab's
  address.
- The NetBox tab's remove handler read `deleted_devices` from a response that
  never contained that key; the field is now returned.

### Deferred

Verified during Phase 0 and scheduled for later phases — see
[docs/NSOT_WRITEUP_NOTES.md](NSOT_WRITEUP_NOTES.md):

- Device lookup takes the first `q=` fuzzy-search hit (Phase 1)
- Golden configs split across two unsynchronized stores; staged-not-committed
  (Phase 2)
- Volatile-line prefix list duplicated across six modules (Phase 2)
- IPv4-only regex in golden config header parsing (Phase 2)
- Pipeline stage 2 discards stage 1's interfaces; no `config_context` (Phase 1)
- AI prompts reference another project's topology (Phase 3)
