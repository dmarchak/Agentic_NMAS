# Changelog

All notable changes to Agentic NMAS.

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
NSoT phases refer to [docs/NSOT_PLAN.md](NSOT_PLAN.md).

---

## [Unreleased] — NSoT Phase 3a: parsers → host_vars → round-trip validation

Read-only. No template UI, no deploy, **no commits** — extractions land in a
gitignored staging area. Lab objective 1.3 (templatize existing config).

### Coverage, measured against real sanitized configs

| Device | Platform | Modeled coverage | Round-trip fidelity | Unmodeled |
|---|---|---|---|---|
| s1 | vIOS-L2, IOS 15.2 | **100.0%** | 100.0% | 0 |
| r1 | C8000v, IOS-XE 17.6 | **92.2%** | 100.0% | 12 |

Mean modeled coverage **96.1%**, mean fidelity **100.0%**. Zero missing, zero
extra, zero reordered sections on both devices. The 12 remaining unmodeled
lines on r1 are seven device-unique constructs (`redundancy`,
`subscriber templating`, `call-home`, …), each appearing on one device — left
unmodeled per the agreed rule.

### Added

- `modules/nsot/parsers/` — `base.py` plus `cisco_ios.py` (IOS 15.x, vIOS-L2)
  and `cisco_iosxe.py` (17.x, C8000v) sharing a base class. **A new vendor is a
  new module plus a template directory**, not a change to the extraction engine.
- `modules/nsot/ifnames.py` — canonical interface names in both directions from
  one shared table, so the two pre-existing display maps cannot drift from it.
- `modules/nsot/hostvars.py` — deterministic YAML, staging-area writes, and the
  secret handoff.
- `modules/nsot/roundtrip.py` — hierarchical comparison, the ordering policy,
  and the coverage report.
- `modules/nsot/templates/` — seed templates per platform, rendering from
  structured fields only.
- `normalize.strip_for_roundtrip()` — the fifth filter job: removes what a
  template **cannot render** (certificate bodies, banners, boot markers, the
  show-version preamble), as distinct from what is merely volatile.
- `credentials.set_template_secret()` with a `secret_kind`, so a hash is never
  offered for rotation.
- `routes/templatize.py` — report, extract, staged, rendered. All read-only.
- Fixtures: `tests/fixtures/configs/` — two sanitized real golden configs.
- Tests: `test_roundtrip.py` (31), `test_parsers_cisco_ios.py` (33),
  `test_ifnames.py` (25), `test_hostvars_secrets.py` (18).
  **507 total, all passing.**

### Design decisions

- **Secrets are hashes.** `enable secret 9 $9$…` carries a per-hash salt and
  cannot be regenerated. The store holds the **hash string** and templates emit
  it verbatim. Holding plaintext would fail those lines on every round trip,
  permanently.
- **Ordered comparison by default.** A reordered ACL is a traffic-behaviour
  change, so it is reported as a failure, distinctly from missing/extra. The
  unordered allowlist is short and justified per entry: BGP neighbors, OSPF/RIP
  networks, SNMP/NTP/logging hosts (the device treats them as a set) and
  interface bodies (IOS reorders sub-commands itself).
- **Coverage counts `unmodeled` against it.** A line parked in a pass-through
  block round-trips but is not modelled. `round_trip_fidelity` is reported
  separately because "does it reproduce" and "do we understand it" are
  different questions.
- Interface entries keep **no raw copy** of claimed lines — a template
  re-emitting them would score a perfect round trip while modelling nothing.

### Fixed during 3a

- **`strip_for_roundtrip` ate `version 2` inside `router rip`.** The image
  version is unrenderable; RIPv2's version statement is real config. Version
  stripping is now top-level only. This would have silently dropped RIPv2 from
  every switch.
- **SNMP community strings leaked into YAML.** A community appears twice in an
  IOS config — in `snmp-server community` and again inside `snmp-server host …
  public`. Echoed secret values are now replaced with a reference before
  serialisation.
- **The fixed-point test caught two parser/template asymmetries** that the
  comparison normalisation was hiding: routing blocks kept a redundant `raw`
  list carrying document order the template does not reproduce, and `unmodeled`
  entries carried a `lineno` that shifts when lines move.

## [Unreleased] — NSoT Phase 2: Golden config repository and version control

Golden configs become a proper version-controlled store. Lab objectives 1.1
(version control and change management) and 1.4 (golden config saved with
timestamp).

### Added

- **`modules/nsot/repo.py` — the one write path.** `save_golden()` replaces six
  separate golden-write sites. One call is **one commit**, even for a nine-device
  "Save All". An unchanged device creates no commit but is still reported.
- **Timestamps and metadata live in git.** Every commit carries `Source`,
  `Actor`, `Devices`, `Device-Id`, `Device-Name` and optional `Pipeline-Id`
  trailers, plus annotated tags: `golden/<device>/<UTC>` per changed device and
  `baseline/<UTC>` for a Save All. **These tags are the "golden config saved
  with timestamp" the lab asks for.**
- **Identity-keyed manifest** (`modules/nsot/manifest.py`). Devices key on
  `nb:<netbox_id>` or `uid:<uuid4>`, never on hostname. A rename becomes a
  `git mv` committed **alone**, which is what keeps
  `git log --follow -- golden/<new>.cfg` returning pre-rename commits.
- **Deferred renames.** An inventory refresh records `pending_rename` in the
  manifest and stops — the background thread never takes the repo lock or
  commits. The `git mv` happens at the next `save_golden` or via "Sync device
  names to repo". While pending, the manifest resolves **both** names so the
  config stays reachable.
- **CI evidence as git notes** (`refs/notes/ci`) attached to the exact commit.
- **`modules/nsot/restore.py`.** Restore queues per-device approvals and never
  pushes directly. Stale devices are **skipped and named** in the confirm
  dialog and the result — no silent partial restore.
- **`modules/nsot/migrate.py`** — dry-run by default, and the dry run is what
  the UI shows first. Detects **case-insensitive and IP-level duplicates**,
  merges keeping the newest content, and reports every merge with both sources,
  the winner, and whether content actually differed. Nothing is deleted;
  merged-away copies go to `.nsot/migration-backup/`. Backfills `device_uid`
  for every device in every local list in one pass.
- **`modules/nsot/hooks.py` + `modules/nsot/archive.py`** — post-commit
  callbacks (git push, S3 archive) on a background thread with short timeouts.
  They never hold the repo lock and never delay or roll back a commit. Push
  never force-pushes; a non-fast-forward surfaces the conflict and stops.
- Tag retention setting `nsot_device_tag_retention` (default 50, 0 = keep all).
  `baseline/*` tags are **never** pruned; commits retain full history regardless.
- `routes/golden.py`, `templates/partials/golden_repo.html`.
- Tests: `test_normalize_equivalence.py` (16), `test_golden_repo.py` (27),
  `test_golden_migration.py` (16), `test_golden_restore.py` (11).
  **385 total, all passing.**

### Changed

- `_save_golden_config_file` is now a thin wrapper over `save_golden`, which
  routes all six write sites at once. `config_git.write_and_stage` likewise —
  the stage-now-commit-later gap is gone for golden saves. The manual
  stage/commit flow in the Git tab is unchanged and still handles `infra/`.
- The golden file keeps **one stable header line**. `! Saved:` and `! Source:`
  are gone: they produced a diff on every save even when the config was
  identical.
- `_find_golden_config_file` resolves manifest-by-identity →
  manifest-by-IP → legacy header scan → None. The legacy scan is kept for the
  deprecation release, with a warning, so a device whose IP changed outside
  NMAS does not silently lose its golden config.
- `golden_configs_save_all` collects every device first and promotes them in
  one commit, and no longer stages each config twice.

### Fixed

- **Two saves in the same second collided on tag names**, silently losing the
  second one's tag. Colliding tags now get a short-sha suffix.
- **`git tag --format` does not expand `%x1f`** (that is a `git log` feature),
  so the baseline listing parsed nothing and always returned empty.
- **The migration was not idempotent**: `last_seen` in the version-controlled
  manifest produced a one-line diff on every call. Freshness is runtime state
  and now lives only in the (gitignored) inventory cache.
- `golden_configs_save_all` gated its Jenkins validation pipeline on
  `has_staged_changes()`, which is always false now that saves commit — that
  would have silently stopped creating validation pipelines.
- The IPv4-only header regex is gone; IPv6-managed devices parse correctly.

### Note on the "duplicated" volatile-prefix lists

The plan called for consolidating six duplicated prefix tuples into one helper.
They are **not duplicates** — they do four different jobs, and merging them
would have changed drift results and broken config push. `config_git` keeps
`version ` and `upgrade fpd` where drift strips them; `app.py` also filters `!`
and `end`, which are not volatile at all — `end` mid-config silently truncates
a startup-config, so that filter is a **safety guard**. `modules/nsot/normalize.py`
holds every tuple, named and documented, and
`tests/test_normalize_equivalence.py` pins each one against its
pre-consolidation behaviour byte for byte.

## [Unreleased] — NSoT Phase 1: NetBox as the source of truth for inventory

A device list can now take its inventory from NetBox instead of a CSV. Local
lists remain the default and are untouched.

### Added

- **Per-list inventory source** (`modules/inventory/source_config.py`). An absent
  `source.json` means `local`, so every existing list keeps its exact behaviour
  with no migration.
- **NetBox adapter** (`modules/inventory/netbox_source.py`) yielding the exact
  device dict shape the rest of the codebase consumes — credentials included,
  still Fernet-encrypted, because callers decrypt at use.
- **Credential store and resolver** (`modules/credentials.py`). Order: device
  override → the list's *designated* credential list → role → site → default
  profile. Every device records `_cred_source`, so credential origin is visible
  rather than inferred. Profiles carry `last_rotated` / `rotation_policy` as the
  hook for Part 2's rotation.
- **Render context builder** (`modules/nsot/context.py`) — the single way
  templates get data: the full device including merged `config_context`,
  interfaces **with their IP addresses**, the site, and `vars` (empty until
  Phase 3).
- **`nsot_get_device_context`** read-only AI tool, and a NetBox-first read order
  in the system prompt for NetBox-sourced lists only.
- `routes/inventory.py` and `templates/partials/inventory_source.html`.
- Platform map and role map in Settings, plus an optional
  `platform_default_netmiko_type`.
- Tests: `test_netbox_inventory.py` (36), `test_device_lookup.py` (10),
  `test_render_context.py` (15). **307 total, all passing.**

### Changed

- `load_saved_devices()` is now the single dispatch point between a local CSV
  and a NetBox-sourced list. It has ~79 call sites across 11 modules; routing
  the decision through one function means none of them changed.
- **Dispatch never performs network I/O.** A background refresh resolves and
  encrypts credentials once per refresh; dispatch serves finished dicts from
  memory and returns a deep copy so a caller cannot corrupt the cache.
- The last good inventory is persisted to
  `data/lists/{slug}/netbox_inventory_cache.json` — **identity fields only,
  never credentials** — so a restart during a NetBox outage still yields the
  last known list with a stale badge. Credentials are re-resolved on rehydrate.
- `save_device` / `delete_device` / `write_devices_csv` refuse on a NetBox
  list; Add Device, Delete, Discover→Add and Refresh Hostnames are disabled in
  the UI with an "Edit in NetBox" tooltip. Drag-and-drop reorder still works,
  stored in `source.json`.
- Deleting a list that other NetBox lists inherit credentials from now returns
  409 with the dependent list names, unless acknowledged. "Copy inherited
  credentials into device overrides" decouples on demand.
- Pipeline stages 1–2 use the render context; `_render_jinja2` receives
  `device`, `interfaces`, `site` and `vars`, keeping `netbox` as an alias so
  existing templates render unchanged.

### Fixed

- **Device lookup could return the wrong device.** `netbox_get_device` and
  `netbox_get_interfaces` fell back to a `q=` fuzzy search and took the first
  hit, so asking for "R1" could return "R10" — and a template would be rendered
  against, or config pushed to, the wrong device. Resolution is now exact name,
  then IPAM (`address=` → assigned interface → device), then a clear "not
  found". The docstring claiming an exact address match is now true.
- **Pipeline stage 2 discarded the interfaces stage 1 fetched**, reading only
  `["device"]`. Templates never saw an interface or an IP address.
- The render context now carries the merged `config_context` and
  `custom_fields`. `_compact_device` deliberately stays lean — it feeds AI tool
  payloads where size matters.

### Behaviour on incomplete NetBox data

A device missing `primary_ip4`, an unmapped platform, or unresolvable
credentials is **skipped with a per-device reason and a NetBox deep link**, and
the rest of the list loads normally. A skip is never fatal: nine good devices
out of ten still work. An unmapped *role* is a warning rather than a skip —
the role resolves to "" and topology falls back to hostname inference, exactly
as for a local list with a blank role.

### Stale devices

A device that disappears from NetBox drops out of the active list, but its
golden configs, backups and history stay on disk and stay browsable. It becomes
**inert**: the approval executor, the drift checker and the AI device tools
refuse to act on it with a clear message, and its pooled SSH session is closed.

## [Unreleased] — Phase 0 follow-up: one-shot write authorization

Hardening of the Phase 0 write gate after review. Addresses three issues, two of
which were real defects.

### Security

- **Confirming an operation no longer opens NetBox for writes.** The import and
  removal confirm actions previously called
  `set_user_setting("netbox_allow_writes", True)` — a *persistent* change
  smuggled in under a checkbox labelled "remember this choice". Authorization is
  now one-shot:
  - A preview issues a single-use token (`modules/netbox_authz.py`) bound to a
    SHA-256 hash of that exact plan, valid for 5 minutes.
  - Execute consumes the token, **recomputes the plan**, and aborts with
    "NetBox changed since preview" if the hash differs.
  - A token is burned even on a failed validation, so it can never be replayed.
  - `netbox_allow_writes` now means only "writes are permitted at all". It is a
    separate, explicitly-labelled operator decision, checked *before* the token
    is consumed so an unauthorized instance cannot burn one.

### Fixed

- **The dry run over-counted shared objects.** Get-or-create helpers could not
  see objects the dry run had already planned, so each device planned its own
  manufacturer, platform, and device type. A three-device import previewed three
  manufacturers and created one. The dry-run plan now keeps a virtual overlay of
  what it pretended to create, and `_nb_get` / `_nb_first` consult it — so
  preview counts equal executed counts exactly.
- **`_nb_patch` returned a synthetic id for objects that already exist.** Callers
  chain child objects off the returned id, so re-importing an unchanged device
  planned a spurious interface create. The dry run now returns the real id
  parsed from the PATCH path.
- `updates` entries in a plan now record the endpoint and object id separately,
  so `updates_by_type` groups by object type rather than by individual object.

### Verified (no change needed)

- **The `nmas-managed` tag is only applied to created objects.** Injection
  happens in `_nb_post` only, never `_nb_patch`, so an object NMAS updates but
  did not create stays untagged and therefore ineligible for deletion by Remove.
  Now covered by three tests including a structural check that no PATCH payload
  anywhere carries the tag.
- **Dependent objects are counted through placeholder ids.** Interfaces and IP
  addresses under a not-yet-created device appear in the preview, confirmed at
  1, 3, and 5 devices.

### Added

- `modules/netbox_authz.py` — plan hashing and single-use tokens.
- `tests/fake_netbox.py` — in-memory NetBox API for comparing a dry run against
  a real execution from identical starting state.
- `tests/test_netbox_authz.py` (23 tests), `tests/test_netbox_preview_fidelity.py`
  (11 tests). **243 tests total, all passing.**

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
