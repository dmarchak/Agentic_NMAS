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

### NSoT / Phase 0–3c additions
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
- **[modules/nsot/repo.py](modules/nsot/repo.py)** — `save_golden()`, the one
  golden write path; trailers, tags, renames, CI notes, locking
- **[modules/nsot/manifest.py](modules/nsot/manifest.py)** — identity map
  (`nb:<id>` / `uid:<uuid>`), pending renames, `sync_platforms()`
- **[modules/nsot/normalize.py](modules/nsot/normalize.py)** — every
  config-line filter, one per job
- **[modules/nsot/migrate.py](modules/nsot/migrate.py)** — dry-run-first
  migration with duplicate merging; one-shot, guarded by `.nsot/migrated.json`
- **[modules/nsot/restore.py](modules/nsot/restore.py)** — re-apply a ref
  through the confirmed deploy path; device and intent as one unit
- **[modules/nsot/hooks.py](modules/nsot/hooks.py)**,
  **[archive.py](modules/nsot/archive.py)** — background post-commit push/archive
- **[modules/nsot/parsers/](modules/nsot/parsers/)** — config → host_vars, one
  module per platform (`cisco_ios.py`, `cisco_iosxe.py`)
- **[modules/nsot/roundtrip.py](modules/nsot/roundtrip.py)** — render vs. real,
  ordering policy, coverage report
- **[modules/nsot/hostvars.py](modules/nsot/hostvars.py)** — YAML staging,
  secret handoff
- **[modules/nsot/ifnames.py](modules/nsot/ifnames.py)** — canonical interface names
- **[modules/nsot/bootstrap_config.py](modules/nsot/bootstrap_config.py)** —
  the minimal config a new device boots with; one producer for the measurement
  probe and the Phase 4 wizard, ASCII-guarded over its whole output
- **[modules/nsot/render_artifact.py](modules/nsot/render_artifact.py)** — the
  deployability gate; frozen, computed, no override
- **[modules/nsot/templates_repo.py](modules/nsot/templates_repo.py)** — the
  per-network template library and bindings
- **[modules/nsot/approval.py](modules/nsot/approval.py)** — template approval
  keyed on a binding fingerprint
- **[modules/nsot/deploy.py](modules/nsot/deploy.py)** — the deploy contract,
  merge-only diff, transport, circuit breaker, batch orchestration
- **[modules/nsot/convergence.py](modules/nsot/convergence.py)** — per-protocol
  settle windows
- **[modules/integrations/](modules/integrations/)** — one client per external
  tool (NetBox, Prometheus, Grafana, Loki, Oxidized, Kea, topology service, NSoT
  git, S3). Phase 0 ships `test_connection()` only; Phase 5 adds read clients.
- **[routes/](routes/)** — Flask blueprints: `settings_integrations.py`,
  `netbox_safety.py`, `inventory.py`, `golden.py`, `templatize.py`,
  `templates.py`, `deploy.py`

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
- **Migration is one-directional and runs once.** `config_repo/golden/` is the
  golden store; `golden_configs/` survives as a deprecated **read-only**
  fallback, consulted by `_find_golden_config_file()` only when the manifest has
  no entry for a device. It is never an input to migration again, and nothing
  writes there. `apply()` refuses when `.nsot/migrated.json` exists (`409`), and
  independently of that guard cannot produce an empty commit.
- **One enumerator: `repo.list_goldens()`, keyed on the manifest** (Phase 3.3).
  `_list_golden_configs()` was `os.listdir(golden_configs/)` and nothing else,
  while `_load_golden_config_file()` resolved through the manifest —
  **enumeration and content came from different stores**, and 17 executable
  call sites across 9 modules asked the enumerator which devices have a
  golden. The nine reference devices were enumerable only because their
  pre-migration files still sat in the legacy directory: **that coverage was
  inherited, not designed.** A device onboarded after the migration was
  checked by nothing and reported by the event monitor as having no golden,
  while its config sat in `config_repo/`. `_list_golden_configs()` is now a
  thin adapter over `list_goldens()`, so every caller was fixed without being
  touched, and `saved_at` is the **commit** time rather than the file's mtime.
  Legacy-only devices are still returned, flagged `legacy`, and
  `legacy_only_goldens()` is the store's **retirement condition** — when it is
  empty for every list, the directory and the header scan go. `GET
  /golden/legacy_store` reports it on the Golden tab.
- **Platform lives in the manifest, sourced from the inventory.** The `platform`
  CSV column (local lists) or the NetBox platform slug (NetBox lists), resolved
  through `platform_for_device()` and refreshed by `manifest.sync_platforms()`
  on every inventory change — not only at migration.
- **AI read-first:** the agent checks golden configs and variables before opening
  any SSH session
- **Secrets are redacted at the provider boundary** (`modules/redact.py`),
  immediately before `messages.create()` — `system`, `messages` and `tools`.
  Not at the golden reader: `show running-config`, backups, drift diffs and any
  free-form command carry the same values, so per-reader redaction is N places
  that must each remember and a new tool inherits the gap. Values are replaced
  by `<redacted:<ref>>`, so the model still knows a secret is there. Values
  shorter than 8 characters are left alone — redacting `RO` wherever it
  appeared would corrupt every config and protect nothing.
- **Redaction is value-based AND positional, and the second does the work
  here.** Measured on the live fleet, **14 of 18** stored secrets fall under
  the 8-char value floor — every SNMP community (6) and every plaintext router
  password (7) — so value matching alone covered almost none of the real
  exposure. `redact_positional()` masks whatever occupies a secret's syntactic
  slot (`snmp-server community <X>`, `username … password|secret <X>`,
  `enable secret <X>`, `key-string <X>`, `tacacs/radius key <X>`, line
  `password <X>`, `ppp chap password <X>`) regardless of length, and regardless
  of whether the store has ever seen it — so an un-onboarded device is covered
  too. Fleet result: **0 unmasked secret-position lines across all nine**. The
  word "public" in an interface description is deliberately left alone; the
  community is already masked where it is a community.
- `credentials.device_credential_values()` decrypts CSV fields with
  `device.decrypt_field` (raw Fernet), **not** `secrets_store.decrypt_value`,
  which returns anything unprefixed unchanged — using it collected 100-char
  ciphertext that no device would ever echo.
- **Config push workflow:** backup → push → Jenkins CI → save golden → update
  variables. CI pass = auto-approve.
- **Approval queue:** destructive AI actions go through `approval_queue.py`.
  **Nothing resolves an item without a human**: the only callers of `resolve()`
  are three HTTP routes, expiry marks items `expired` and never executes, and
  neither `agent_runner` nor `event_monitor` nor any AI tool can approve — they
  only *add*. `revert_to_golden` **hands off to the confirmed restore path**
  instead of executing. It used to push a stored diff with no confirm hash, no
  mask check, no sendability check, and an unbounded `no <command>` per added
  line. Approving one now opens the restore preview for that device **at
  HEAD** — a single-device revert *is* a Mode A re-apply of its HEAD golden —
  and the operator confirms a program computed **now**, from the device as it
  is now.
- **The queued diff never reaches a device.** It was computed when the drift
  was noticed, which is not when the operator is looking; a program the
  approver never read is what the confirm hash exists to prevent. It travels as
  **advisory context** ("what the agent saw"), is displayed above the fresh
  program labelled *not what will be sent*, and is echoed by the route and
  nothing else — a test asserts the only line mentioning it is the echo.
- **Approving a confirm-ending item does not resolve it.** It stays pending
  with an "Awaiting confirmation" note, because marking it approved would have
  the queue claiming a change nobody has sent. `mark_done()` closes it when the
  restore succeeds, and **only** for devices that actually succeeded — an item
  closed on a failed push is the queue claiming work that did not happen.
  Without it, items linger and the operator learns to clear the queue by
  rejecting things, which is the habit that makes an approval queue worthless.
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

### Golden config repository (Phase 2)

`data/lists/{slug}/config_repo/` is the NSoT repo: `golden/<device>.cfg`,
`.nsot/manifest.json`, `infra/`, `.gitattributes`.

- **One write path.** Everything that promotes a golden config goes through
  `nsot.repo.save_golden()`. **One call is one commit**, even for a nine-device
  Save All. An unchanged device creates no commit but is still reported.
- **Identity is resolved, never minted by accident.** `resolve_identity()` takes
  the item's identity, else the manifest by IP, else by name — and mints only
  when `allow_new=True`. The pipeline passes `allow_new=False`: a deploy targets
  a device the inventory already knows, so arriving with no identity is a bug,
  not an onboarding. A function that creates identity when none is supplied
  always masks a caller that forgot to supply it.
- **Timestamps live in git**, not in the file. The file keeps one stable header
  line; `! Saved:` / `! Source:` are gone because they produced a diff on every
  save. Commits carry `Source`, `Actor`, `Device-Id`, `Device-Name` trailers,
  and annotated tags `golden/<device>/<UTC>` and `baseline/<UTC>`.
- **An `Actor:` trailer is WHO is accountable, never WHAT ran.**
  `repo.ACTOR_CONVENTION`. Three kinds: a **person** (email, or the OS user
  for a command run on the host); **`ai-agent`**, the exception that proves
  the rule since it genuinely decides without anyone typing a command; and
  **`service:<client-id>`**, matching the identity layer's own prefix. A
  one-off script is none of these — nobody is accountable to a program — so
  it records the person in `Actor:` and names itself in a `Tool:` trailer.
  `Source:` names the workflow (`manual`, `save_all`, `pipeline`, `approval`,
  `ai`, `onboarding`, `extraction`, `repair`) and is free text by design: an
  enum would have to be edited before any new workflow could commit. The
  first repair commit carries `Actor: description-repair` and predates this;
  it is left alone, and is why the convention is written down.
- **Identity, not filename.** The manifest keys on `nb:<netbox_id>` or
  `uid:<uuid4>`. A rename is a `git mv` committed **alone**, which is what keeps
  `git log --follow` working across it.
- **Refresh never writes to git.** An inventory refresh records
  `pending_rename` in the manifest only; the `git mv` happens at the next
  `save_golden` or via "Sync device names to repo". Both names resolve while
  pending.
- **Re-apply goes through the confirmed deploy path**, not the approval queue.
  Every read at a ref goes through `repo.RefSource`, whose allowlist is a
  **constructor argument** — restore declares `("golden/", "host_vars/")`, so
  asking for `templates/`, `bindings.yml` or `.approvals.json` raises
  `ScopeRefused`. Templates are code; rolling them back to restore a *network*
  would silently revert template fixes. `RestoreTarget` duck-types what
  `plan_batch()` reads, so the confirm hash, ASCII guard, provenance,
  `error_pattern`, failure capture, circuit breaker, staging and single golden
  commit all apply unchanged.
- **It is additive, and labelled as such.** The button says *Re-apply this
  baseline*; the confirm reports `add` / `replace` / `residue` per device and
  states that residue is **not** removed. Removals are Mode B, not built.
  Queued items from the old path are rejected with a reason on first use —
  executing one would push whole-config text through the unguarded executor.
- **Device and committed intent are one unit, per device.** Restoring the
  config alone leaves the next template plan offering to undo the restore, so
  the ref's `host_vars` are re-committed **verbatim** in the **same commit** as
  that device's golden capture — for devices whose push succeeded only, staged
  to `.nsot/staging/restored_intent/` across the crash window. Verbatim needs
  `repo.git_raw()`: `git()` strips stdout and drops the trailing newline, which
  would land a one-byte diff labelled "restore".
- **Intent restore is a forward commit.** Nothing is reset or force-pushed; the
  replaced intent stays reachable by `git log -- host_vars/<device>.yml`.
- **Un-onboarding is opt-in, never a default.** A ref predating a device's
  onboarding has no intent to restore, and deleting today's would un-do a human
  review — so the default outcome is **skip**. Ticking it re-runs the
  *preview*, because a skipped device has no command list and confirming
  commands nobody was shown is what the confirm hash exists to prevent.
- **`validate_restored_intent()` refuses at plan time** when a ref's intent no
  longer round-trips through today's templates, or names a secret the
  credential store no longer holds.
- **`baseline/<ts>` is earned by measurement, not granted by mode.** A skipped
  device counts only if it was **measured**, so a restore baseline requires
  *every inventory device measured equivalent to the ref, whatever path got it
  there*. A device with nothing to send is still read back
  (`_measure_unchanged`), because "nothing to change" was decided against a
  **stored** capture; an unreachable device contributes nothing and declines
  the tag. **Residue therefore denies a restore baseline** — merge-only cannot
  remove it, so the network is not at the ref. Deploy baselines stay
  coverage-only: their goldens *are* the post-deploy captures.
- **`save_golden()`'s empty-commit guard covers the whole commit**, not just
  `golden/`. A restore to a ref a device already matches changes no golden and
  still moves its intent; `extra_paths` staged content keeps the commit alive.
  A call with neither still creates nothing.
- Stale devices are skipped and **named** in the confirm dialog.
- **Migration is dry-run by default.** It merges case-insensitive and IP-level
  duplicates keeping the newest content, reports every merge, and backs up
  rather than deletes.
- **Every commit that moves a device carries `.nsot/manifest.json`.** The
  rename commit stages `.nsot` alongside `golden`, so a clone or bundle restore
  at that commit resolves the new name instead of falling through to the legacy
  header scan. `save_templates()` deliberately does not touch the manifest.
- **`.gitignore` rules are applied on repo access, not only at creation.**
  `ensure_repo_hygiene()` runs from `git()`; `GITIGNORE_RULES` is the list. A
  repo created before a rule existed is topped up on first touch.
- **Post-commit hooks register where the repo module is USED, not where the
  app starts.** `hooks.run_post_commit()` calls `ensure_default_hooks()`
  first. Registration lived in `app.py`, so a commit from any process without
  Flask — a CLI repair, a cron job, a maintenance script — met an empty
  registry and `run_post_commit()` returned silently: measured, a fresh
  interpreter reports `[]` until `app` is imported. The 1.4 repair commit went
  in that way and stayed local while the Remote card accurately showed the
  previous push. An empty registry on a list that **has** a remote is now an
  error and records `last_push_failure`, because "a commit that could have
  been published and was not" must never be silent. A list with no remote
  stays quiet, or the error stops meaning anything. Hooks run on a background
  thread with short timeouts and never block a commit. Push never
  force-pushes.
- `nsot_device_tag_retention` (default 50) prunes per-device tags only;
  `baseline/*` tags and all commits are kept.

**Config-line filters** live in `modules/nsot/normalize.py`. They are *not* one
list — four different jobs, and `push_safe_lines()` filtering `end` is a
truncation guard, not cleanup. `test_normalize_equivalence.py` pins each to its
prior behaviour.

### Templatization (Phase 3a)

Config → `host_vars` YAML → render → compare. **Read-only**: extractions go to
`config_repo/.nsot/staging/host_vars/` (gitignored); 3b adds the reviewed commit.

Current coverage across all nine reference devices (R1–R5, S1–S4):
**100% modeled, 100% round-trip fidelity, zero unmodeled constructs — under the
depth-aware comparison**, and `merge_commands()` against each device's own
capture is empty for all nine.

An earlier "100% across nine" was measured by a comparison that could not see
nesting depth. `split_blocks()` flattens every indented line into one list, so
`roundtrip._sections()` compared a two-level block as one level — and the
cisco_iosxe template, whose render hoists BGP networks and neighbor activations
out of their address-families to the top of `router bgp`, scored 100%. **The
fixtures contained the address-families all along; parse and render flattened
symmetrically, so both sides agreed with each other while both disagreed with
the device.** `scripts/nsot_metric_diff.py` reports flat vs depth-aware per
device and lists every nested construct in the corpus; the two now agree
everywhere.

- **BGP address-families own their contents.**
  `routing.bgp.address_families` is `[{afi, networks, neighbors, settings}]`.
  Nothing belongs at the top level of `router bgp` that the device puts inside
  a family. The old shape put `network 8.8.8.8 mask …` and
  `network 2001:DB8::/32` in one list and left the `address-family` headers in
  `settings` as ordinary text.
- The existing `test_bgp_address_families_on_r3_r4_r5` asserted
  `any("address-family" in s for s in bgp["settings"])` — **it pinned the
  flattening as correct**, under a name that made the construct look covered.

Decision rule for what to model: **any construct appearing on 2+ devices, or
any routing/redundancy protocol in the network design.**
`test_fleet_coverage.py` enforces it.

- **One parser module per platform** (`cisco_ios`, `cisco_iosxe`). A new vendor
  is a new module plus a template directory — that is the multi-vendor story.
- **Secrets are hashes.** `enable secret 9 $9$…` has a per-hash salt and cannot
  be regenerated; the store holds the hash string and templates emit it
  verbatim. `secret_kind: hash` marks values Part 2's rotation must skip.
- **Comparison is depth-aware.** `modules/nsot/sections.py` holds the
  indentation→ancestry algorithm; `_sections()` keys on a line's full container
  path (`router bgp 65002 > address-family ipv4`). A container is a key, never
  also a child of its parent — listing it in both counted it twice. The global
  scope `""` is a scope, not a section: it contributes no section-level match
  (a wholly unknown config scored 16.7% instead of 0 when it did) and is
  **unordered**, because a template emits globals in its own order and the flat
  comparison never checked that either.
- **Ordered comparison by default.** Reordered ACLs / prefix-lists / route-maps
  / `ip sla` fail. The unordered allowlist covers only what the device treats
  as a set, plus interface bodies (IOS reorders those itself). With paths,
  `section_is_unordered()` tests **every component** and
  **order-significant anywhere wins** — a route-map nested in an unordered
  block is still a route-map.
- **Interface names are canonicalized** on both sides (`Gi0/0` →
  `GigabitEthernet0/0`), including references inside lines.
- **Coverage is reported honestly**: `modeled_coverage` counts `unmodeled`
  against it; `round_trip_fidelity` is separate.
- `strip_for_roundtrip()` removes what a template *cannot render* — distinct
  from volatile.
- **Every volatile pattern anchors to column 0** unless listed in
  `NESTED_OK_PREFIXES`. `version 17.6` is the image version; `  version 2`
  under `router rip` is RIPv2. Stripping the latter from both sides of a
  comparison hid the loss entirely, so only extraction-side tests catch it.

### Template library and the deploy gate (Phase 3b)

`config_repo/templates/` holds the network's templates, seeded by copy from
`modules/nsot/templates/`. Templates are **per-platform**; per-device divergence
belongs in `host_vars`, with an explicit `bindings.yml` override as the
exception.

- **Nothing in 3b opens a socket.** Previews diff against captured artifacts
  only — a golden config and the newest stored backup, each labelled with its
  capture time. "Refresh capture" delegates to the existing backup route.
- **`deployable` is a computed property on a frozen dataclass.** A device with
  unmodelled constructs cannot reach a deployable render by any code path.
  `build_artifact()` is the only constructor and always validates.
- **`intended/` and previews are masked, so neither is ever a deploy source.**
  3c must re-render from the template with real secrets in memory;
  `assert_no_mask()` guards that path. Validation runs on the truthful render.
- **Unmodelled constructs can be acknowledged**, not dismissed: `unmodeled_ack`
  in `host_vars` must list the exact lines, is committed to git, and is
  invalidated by any new or removed unmodelled line.
- **Approval requires a clean round-trip against every bound device**, keyed on
  a binding fingerprint of **template hash + sorted bound identities**
  (scheme 2). The template hash covers the **whole import closure** — a
  template is `base.j2` plus every macro file it imports, and `_common.j2`
  holds the routing, interface and service macros for both platforms. Hashing
  only `base.j2` meant an edit to the shared macros changed what every template
  rendered while every approval stayed valid. Editing any file revokes every
  approval whose closure contains it. Revoked by a template edit or a change to the device set —
  onboarding or removal. A device's *configuration* changing does not revoke
  it: that is `template_report`, live on every plan, per device, gating there
  with the lines named. Scheme 1 also hashed each device's host_vars, which
  meant a successful deploy revoked its own template's approval. Records carry
  a `scheme`; an older one is never silently honoured.
- **Revocation is a recorded finding, not a deletion.** `approval.revoke()`
  requires a reason and writes a tombstone carrying it, the actor, and what was
  withdrawn. Popping the record made a withdrawal indistinguishable from "never
  approved" — both block a deploy, so the gate was never wrong, but the finding
  was thrown away. `is_approved()` refuses a `revoked` record **first**, ahead
  of the scheme and fingerprint checks, so no later computation can overturn
  the decision. `POST /templates/revoke/<path>` is the reachable path.
- Template commits use their own namespace (`template:`) and create **no tags**.
  **Seeding commits itself** (`template: seed library`), so an approval's diff
  is the approval rather than the whole library.

### Deploy from template (Phase 3c)

The only part of the NSoT work that reaches a device.

- **Intent is committed, never inferred.** `config_repo/host_vars/<device>.yml`
  is the only intent source on the deploy path; `.nsot/staging/host_vars/` is
  gitignored scratch. A device with no committed intent is `bootstrap` and
  **not deployable** — deriving intent from the device's own capture makes the
  diff empty by construction. A change is made by editing committed intent and
  committing it (`host_vars: <device> <summary>`), not by configuring the
  device and re-extracting.
- **Design rule — gate on template fidelity, never on intent drift.**
  `template_report` (render of the capture's own parse vs the capture) answers
  "can this template reproduce this device as it is"; if not, a render from
  intent is untrustworthy whatever the intent says, so it gates. `report`
  (render of committed intent vs the capture) is *drift* — the change being
  deployed — and gating on it would make every change block itself. Approval is
  keyed on capture-parsed host_vars for the same reason: it is a claim about
  the template, not about one device's intent.
- **Every pushed line is attributed before the confirm.** Merge-only pushes
  every line the render has and the device lacks, so anything that drifted on
  the device since the capture rides along. The plan renders the *previous*
  committed intent against the same capture and splits `to_add` into
  `from_this_edit` and `pre_existing`.
- **Secrets are scoped to their device list.** The credential-store key is
  `<list-slug>:<hostname>:<ref>`, built **only** by
  `credentials.template_secret_key()`. It used to be `<hostname>:<ref>`, built
  by four f-strings in three modules over one installation-wide store, so two
  lists each holding an `r1` shared a key: the second list's extraction
  silently replaced the first's, and the first network then deployed the
  second's SNMP community with every guard on the deploy path satisfied.
  `set_template_secret()` refuses to replace a secret another list owns, which
  covers a caller that builds the key by hand. Legacy keys migrate on startup.
  `assert_no_secret_values()` deliberately scans **every** list's secrets,
  narrowed only by device — it is a leak guard, and narrowing it by list would
  make a wrong derivation silently check nothing.
- **Masking is OUTBOUND, never at rest.** Golden configs are stored verbatim.
  Masking them would make `golden/` depend on `data/key.key`, which is not in
  the repository — so a private remote would hold configs nobody can restore a
  network from, defeating the point of having one. Secrets are redacted on the
  way *out* instead (provider payloads, API responses, logs). Rotation is what
  kills plaintext already in history; masking new commits does nothing about
  it.
- **Secrets:** committed host_vars hold `secret_refs`; values live in the
  credential store. `write_committed()` refuses a `secrets:` mapping or any
  resolved value, checked structurally and by value. `hydrate_secrets()` is the
  only place names become values, in memory, at deploy time.

- **The 3b contract, in order**: refuse a non-deployable artifact → re-render
  with **real** secrets in memory → `assert_no_mask()` → only then connect.
  `intended/` is masked and is never read on this path.
- **Merge-only.** Missing lines are added; lines on the device the template does
  not mention are **removal warnings**, never negated. `assert_merge_only()`
  checks provenance rather than grepping for `no`, because a template may
  legitimately contain `no ip http server`.
- **What the operator confirms is what is sent, byte for byte** — not a
  superset, not a safe one. `merge_commands()` builds the exact program: each
  added line preceded by its full ancestor chain in order, one `exit` per open
  level at the end of each contiguous group, never `end`. The list is
  recomputed at apply and compared against the confirmed fingerprint; a
  mismatch is refused with "the device or intent changed since you confirmed".
  `PipelineContext.rendered_commands` **derives** from `confirmed_commands`
  when one is set — assigning over it raises `ConfirmedCommandsOverwritten`, so
  no stage can substitute its own render. `test_deploy_contract.py` runs the
  full pipeline with a spy transport and asserts the list reaching the wire is
  the list the plan published.
- **The target list is carried, never re-derived.** `PipelineContext.list_name`
  is set once by the originating request. The pipeline asked
  `get_current_list_name()` at three points *after* the push, including the
  golden commit — and that function reads a file on disk, so a list switch
  during a 45–90s convergence window committed one network's captures into
  another's repository. `allow_new=False` hid it until two networks shared a
  device name or address, i.e. exactly the multi-network case. `restore`'s
  `_devices_of()` is the same correction: a function taking `list_name` must
  not read its inventory from the active list.
- **Transport is per platform.** `supports_netconf: false` goes straight to SSH
  with no attempt — not a fallback after a timeout.
- **`deployable` subsumes sendability.** `build_artifact()` measures
  non-printable bytes on the truthful render (never the masked one — the mask
  is U+2022) and `blocking_reasons` carries them, so there is one answer to
  "can this go out" rather than an artifact saying yes and `merge_commands()`
  saying no later.
- **Dangerous commands are authorised at plan time, per device.** The CI gate's
  `allowed_dangerous` override existed since Phase 0 but `_deploy_one()` could
  not supply it, so any program containing `shutdown`, `no ip address`,
  `no router ospf`, `reload`, `erase nvram` or `crypto key zeroize` was
  unrunnable. The plan flags each dangerous line as an exact string; the
  authorisation is `{device: [lines]}`, is folded into the confirmation hash
  alongside the commands, and apply recomputes both. An authorisation matching
  nothing in the program is refused — a typo means the line it was meant to
  cover is *not* authorised.
- **Rollback is exempt from that gate, structurally** — it never passes through
  stage 3. Undoing an authorised `no shutdown` is `shutdown`, and a gate that
  blocked the repair would leave the device in the state the rollback was
  called to fix. `assert_rollback_provenance()` is the authorisation; exempt
  lines are recorded in the deploy result.
- **Anything that reaches a CLI is printable ASCII — comments included.**
  `assert_sendable()` refuses any other byte before connecting, and
  `hostvars.assert_printable()` refuses it at commit. An em dash is three UTF-8
  bytes; IOS consumes the first, loses sync, and truncates the line, which
  surfaces as a Netmiko echo timeout rather than as an invalid character. The
  rule is **not** "the deploy path": the same character later hung a vIOS boot
  from a *comment* in a startup config, because vrnetlab types that file into
  the console line by line and waits for a prompt after each one. The C8000v
  booted the identical content, since it loads its startup config as a file —
  so one platform can never reveal the property. Everything
  `modules/nsot/bootstrap_config.py` emits goes through `assert_sendable()`
  over the **whole** rendered text, and on console-replayed platforms it emits
  no prose comments at all.
- **Rollback undoes what LANDED, not what was pushed.** On a partial push those
  differ by definition, and with `error_pattern` live a rollback line answering
  a rejected push line can itself be refused and take the repair down. Rejected
  lines are reported as *not undone — never applied*. An unreadable capture
  means everything pushed is undone, which is the conservative answer.
- **The broad command key applies only to free-form values** (`description`,
  `banner`, `remark`, `name`). Everything else needs a precise-key match; a
  miss means there is no prior value and the answer is to negate. Searching
  harder is what matched `ip mtu 20000` to `ip address …`.
- **Rollback is computed, not replayed.** `rollback_commands()` inverts exactly
  what was pushed — re-send the old line where the pre-change config set the
  same thing differently, negate where it did not set it at all. A replay is a
  *merge* and cannot remove a line, so it could never undo a `shutdown`.
  `assert_rollback_provenance()` bounds the one place this tool generates `no`.
- **Rollback restores the device; the intent is separate.** A rollback records
  `.nsot/rolled_back.json` against the device's current intent commit, which
  blocks the next plan — otherwise it would propose exactly what just failed.
  The block is **containment, not equality**: it stands while the failed lines
  (each within its header chain) are still among the lines that would be sent,
  so an unrelated edit that adds its own sent line cannot bundle the failed
  change back out. Lifting it deliberately is `authorise_retry()`, an explicit
  recorded action. "Revert intent"
  (`POST /templatize/committed/<host>/revert`) applies the **inverse of that
  commit's own diff** onto current intent as a forward commit — keeping later
  unrelated commits, and refusing with the paths named when a later commit
  touched the same settings. A snapshot restore would either bring the
  rolled-back change back or discard the unrelated edit.
- **Reads never commit.** `ensure_repo_hygiene()` appends `.gitignore` rules on
  every `git()` call; only `init_repo()` commits the top-up, and it is reached
  solely from write paths.
- **Rollback fires whenever a push was attempted**, and targets every device
  not explicitly skipped — including one whose push failed mid-stream, which is
  the state most in need of restoring.
- **A failed push reports what landed** over a **fresh** connection, never the
  pooled one — that path runs only after something went wrong on the pooled
  session, so it is the most likely to be handed a broken instrument. A failed
  capture drops the pooled connection too. The read timeout is
  `nsot_config_read_timeout` (default 120s): `write memory` leaves an emulated
  device slow for tens of seconds, measured at 5.5s idle and >16s straight
  after a save, and Netmiko's 10s default sits inside that window.
- **A failed push reports what landed.** `_capture_failure_state()` reads each
  attempted device back and diffs against the pre-change snapshot before any
  rollback. "The push failed" and "the device is unchanged" are different
  claims; a device that cannot be read reports `device_changed: None`.
- **Verification uses settle windows** (OSPF 45s, BGP 60s, RIP 90s) and reports
  *not yet converged* distinctly from *failed*. RIP is checked via the Routing
  Information Sources table; it was previously not checked at all.
- **Stage 8.5 saves golden** after verify, on partial success, from the
  post-deploy config stage 7 now captures.
- **Batch**: sequential by default, circuit breaker on repeated *verify*
  failures, drift skips rather than aborts, every device accounted for.
- **Each path's baseline is keyed on the claim its tag makes.** A *deploy*
  baseline says "this commit's goldens are the network" — the goldens are the
  post-deploy captures, so it is true by construction for devices that
  succeeded, and only coverage remains (all targeted devices succeeded, whole
  inventory targeted). A *restore* baseline says "the network is back to the
  ref's state", which is a content claim and is measured per device with
  `roundtrip.configs_equivalent()` — section-aware, over `strip_for_diff`, so
  bare `!` and ordering cannot decide it.
- **A batch is an event: one golden commit, one baseline.** Stage 8.5 hands its
  capture back (`defer_golden`) instead of committing, so `save_golden`'s "one
  call is one commit" is preserved rather than special-cased. The subject and
  `Devices:` name the successful subset, `Failed-Devices:` the rest.
  `save_golden` no longer needs `len(changed) > 1` to tag — a baseline marks a
  moment, not a device count — but **coverage still governs**, so a batch
  targeting one device out of nine is denied the tag with the other eight
  named. A batch where every device fails commits nothing and tags nothing. Captures are staged to
  `.nsot/staging/post_deploy/` as each device completes, so a crash between
  8.5 and the commit is recoverable without re-reading devices that may have
  changed since.

`/configure/apply` is untouched and remains the quick path.

### Settings

All settings live in `data/user_settings.json` with a `settings_schema_version`.
`modules/settings_schema.py` seeds defaults and migrates forward; old keys are
never deleted. **Every new default reproduces the behaviour that predates the
setting** — `netbox_allow_writes` is the one deliberate exception.

**A version bump seeds only the keys it declares.** `SEEDS_BY_VERSION` is a
whitelist and the default is *nothing*: a key added to `DEFAULTS` between
releases is read through its default and **left absent from the file** until
some version deliberately claims it. A denylist ("a bump must not seed a
`require_*` key") would protect the keys somebody thought of and leave the
next security-relevant setting unprotected. Measured before the change: a
bump to v2 seeded **98 keys on a v1 install, including all eight identity
gates**, silently rewriting every "defaulted" as "set explicitly" everywhere.
v1 is recorded as `"*"` rather than rewritten — changing what a released
migration did is a lie about history.

**`migrate()` never writes a value nobody chose.** Absence is information:
`origin: default` means nobody has considered this setting, and writing it
destroys that irrecoverably. A default is also a live link to the project's
judgement — an explicit value wins for ever, so a seeded install silently
stops receiving a considered change to a default.

**Recording a decision is `ratify()`, and it can only ratify.** It writes
`get_setting(key)` — the value already in force — so the act cannot alter
behaviour, which is what lets the read-only posture panel offer it: a
compromised session cannot lower a gate through a control that can only write
the value already applying. It requires an actor, because a ratification with
nobody behind it is a seeded default wearing a better name. Three states
result: **defaulted** (nobody decided), **ratified** (written, equals the
default), **chosen** (written, differs).

**`write_settings()` is the one path into `user_settings.json`, and a key the
schema does not declare is refused rather than stored.** A validation failure
writes nothing at all — a half-applied settings write is worse than a
rejected one. Eight keys the Settings form had always written
(`ai_enabled`, `background_agent_enabled`, six `wf_*`) were undeclared and are
now in the schema; every default reproduces the value the code fell back to
before.

**Secrets are in three stores, not one.** `user_settings.json` holds the ones
`secrets_store.SECRET_KEYS` covers, encrypted. `anthropic_api_key` goes to
`.env` and the four `jenkins_*` fields to `data/jenkins_checks.json` — neither
is in `SECRET_KEYS`, so neither is encrypted at rest or masked by the settings
API. `scripts/nmas-check-secret-storage` reports where each secret lives and
whether it is plaintext, by name and never by value.

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
pytest                    # 756 tests
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
| `test_golden_repo.py` | one-call-one-commit, tags, `git log --follow` across renames |
| `test_golden_migration.py` | dry run, duplicate merging, idempotence |
| `test_golden_restore.py` | restore: stale devices named, intent as one unit |
| `test_normalize_equivalence.py` | each config filter pinned to prior behaviour |
| `test_roundtrip.py` | fidelity, fixed point, ordering policy, coverage maths |
| `test_parsers_cisco_ios.py` | both platform parsers against real fixtures |
| `test_ifnames.py` | interface name canonicalization |
| `test_hostvars_secrets.py` | hash handling, YAML staging, no secret leakage |
| `test_fleet_coverage.py` | all nine devices; enforces the decision rule |
| `test_unmodeled_path.py` | the fallback path: unknown constructs, no invented lines |
| `test_render_artifact.py` | deployability gate, masking, unmodelled acknowledgement |
| `test_template_approval.py` | template library, bindings, binding fingerprint |
| `test_codemirror_assets.py` | vendored asset paths, load order, no CDN |
| `test_deploy_contract.py` | refuse → real secrets → mask check, before any socket; route→wire seam |
| `test_deploy_safety.py` | merge-only, transport short-circuit, breaker, settle windows |
| `test_deploy_batch.py` | drift skip, breaker, every device accounted for |
| `test_rip_verify.py` | RIP neighbours; a RIP device never passes vacuously |
| `test_bootstrap_config.py` | ASCII over the whole output, comments included; probe fixtures == generator |
| `tests/fixtures/configs/` | sanitized real configs; `fleet/` holds all nine |
| `tests/fake_netbox.py` | in-memory NetBox API (not a test module) |
| `test_settings_migration.py` | schema, secret encryption, forward migration |
| `test_integrations_base.py` | optional-integration behaviour, secret masking |
| `test_portability.py` | Jenkins step shell, TFTP root, env overrides |
| `test_no_ip_literals.py` | fails if an IPv4 literal appears in the new packages |
| `test_golden_enumeration.py` | one enumerator; repo-only devices; commit time not mtime; legacy retirement condition |
| `test_drift_population.py` | the inventory is the population; every device in exactly one bucket |
| `test_drift_scheduling.py` | per-list state, merge-not-replace, what a silenced check records |
| `test_check_removed_definitions.py` | the checker tells a use from a mention |
| `test_drift_routes.py` | the routes exercised over HTTP; a crash is JSON+500, never 302; wrapper signatures |
| `test_security_posture.py` | effective value vs origin; Access values withheld; the recorded posture still holds |
| `test_settings_write_path.py` | positive seed declaration; unknown keys refused; ratify-never-change |

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
- **Scan a diff for definitions it did not mean to remove** before committing:
  `python scripts/check_removed_definitions.py` (staged by default; takes a ref
  or `A..B`). Install it as a hook with
  `ln -sf ../../scripts/hooks/pre-commit .git/hooks/pre-commit`. It exits 1 when
  a removed definition is still called — three edits in this project have
  destroyed adjacent code, and all three show that shape.
- Fernet key at `data/key.key` — back it up; losing it makes stored credentials
  and secrets unrecoverable
- `.env` holds `ANTHROPIC_API_KEY`; excluded from git

## Things to Keep in Mind

- **The rcn-lab1 redeploy ban was LIFTED on 2026-09-22**, by a successful
  redeploy rather than by the fix being built. Kept here because the
  reasoning is what stops the hazard being recreated.

  **The hazard:** vrnetlab's patched launch script concatenates its own
  `username admin privilege 15 password admin` **before** the startup config,
  and IOS-XE refuses a secret for a user that already has a password. Stage B
  measured it on a throwaway C8000v: `%CVAC-4-CLI_FAILURE`, the node came up
  on `admin/admin`, reached `Startup complete`, reported healthy and answered
  SSH — a startup file that read correctly and did not apply. Five routers
  would have been silently unreachable.

  **What lifted it:** the stage-C user-skip adopted into
  `~/labs/lab/patches/c8000v-launch.py`; a break-glass credential record
  verified on the laptop it lives on; stage D2 proving a vIOS boots a real
  `secret 9` startup line (the switches were unproven too — nothing had ever
  fed a pre-computed `$9$` hash back to the platform that emits it); and the
  redeploy itself: all nine `Startup complete`, **no username line rejected**,
  the skip firing exactly once per router, `secret 9` on all nine and
  `password 0` on none, the credential NMAS holds accepted on all nine, and
  `admin`/`admin` refused on all five routers. Save All produced certificate
  bodies on r1–r5 and **zero other changed lines**.

  **The guard that keeps it lifted** is `verify_startup_applies()`, the
  persistence chain's `startup_applies` stage: a `secret` line written into a
  startup file on a platform whose launch path injects a password first is
  refused **at the moment it would be created**, not discovered at the next
  boot. It tests the **call site** — the unpatched concatenation absent and
  the helper actually called — because its first version searched for the
  helper's *name* and passed while the property was false.

- Jenkins pipelines default to Windows `bat` steps; switch to `sh` in Settings for
  a Linux Jenkins agent. Generated XML is byte-identical to pre-Phase-0 output
  while the default is unchanged.
- `telnetlib.py` shim must stay in the root for Python 3.13+ compatibility
- The app has no auth layer of its own. It sits behind a Cloudflare tunnel, and
  **identity comes from a verified assertion, never from a header**
  (`modules/identity.py`). `Cf-Access-Authenticated-User-Email` is an ordinary
  HTTP header — measured before the firewall was closed, a LAN laptop sent a
  forged one and got HTTP 200. What is verified is `Cf-Access-Jwt-Assertion`:
  RS256, against `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`,
  with `aud` and `iss` checked; the email is read from the verified claims.
  **Two independent conditions**: a valid assertion *and* a raw-socket peer on
  `cf_access_trusted_peers`. The peer check is not redundant — an assertion
  captured from a browser and replayed from elsewhere on the LAN satisfies the
  first — and it is the layer that survives a firewall rule being edited later.
  `X-Forwarded-For` is never consulted and `ProxyFix` is never installed, both
  pinned by tests. Nothing logs a value: only header presence, the validation
  outcome, and the actor **kind**.
- **Reveal, approve and confirm all require a verified identity** by default.
  Reveal exposes a secret; approve and confirm put configuration on a device.
  **There is no localhost exemption** — an exemption for requests from the box
  is an exemption for anything that has reached the box, which is exactly where
  an audit trail matters most. A test asserts no loopback address appears in
  `identity.py`.
- **A verified service is still not a person.** `require_person_for_approve`
  and `require_person_for_confirm` default ON: approve and confirm are where a
  human is supposed to have read an exact command list before it reaches a
  device, and the confirm hash is only worth something because somebody looked
  at what it covers. `require_person_for_reveal` is ON too: the service
  credential lives in a file on a workstation, and if it leaks, reveal is the
  largest blast radius it has — and nothing planned needs it, since Part 2's
  rotation runs in-process and never calls the HTTP reveal route. **Services
  authenticate, plan and queue; anything that exposes a secret or changes a
  device has a person behind it.** The exception is
  `service_allowed_operations`, a list of operation **kinds** that **starts
  empty** — Part 2 adds `credential_rotation` by name. A list, not a boolean:
  "services may rotate credentials" and "services may deploy" are different
  grants.
- **Config is masked by default on the way out.** `/golden/version/<host>` and
  `/golden/diff/<host>` return `redact_text()` output unless `?reveal=1`, which
  **requires a person** and is recorded in `data/reveal_audit.jsonl`. A diff
  carries the same secrets as either config on its `-`/`+` lines, so both go
  through one helper rather than each remembering. A refused reveal returns the
  **masked** text, not the secret with an error beside it.
- **`data/reveal_audit.jsonl` stays local, for now.** It is the only gated
  action whose audit trail is **not** in git: golden saves, deploys, restores
  and intent edits are all commits, and Phase 2b will push those to a private
  remote. Reveals are not. That is a deliberate deferral, not an oversight —
  revisit in Part 2, when there is somewhere to put it that does not make the
  trail itself a secondary exposure.
- **The reveal trail records what was looked at, never what was seen** — device,
  ref, actor, kind, time, peer. A trail that copies the secret it records has
  become a second place the secret lives. Masked reads record nothing; the trail
  logs reveals, not requests.
- **The app log is redacted on EVERY handler** — `redact_all_handlers()` at
  startup, plus `guard_new_handlers()` so handlers attached later inherit it.
  Not the root *logger*: a record from a child logger reaches ancestor
  **handlers** without ancestor logger filters being consulted. Not the file
  handler alone either — it exists only when `app.debug` is false, and a
  StreamHandler to stdout is the systemd journal. Arguments are redacted as
  well as format strings (a secret is far more often in an arg) and so is
  exception text.
- **Coverage is proven by a canary, not by inspecting filters.**
  `redact.canary(handler)` runs a synthetic secret-bearing record through a
  handler's **real filter chain** and checks it comes out masked. Reading
  `handler.filters` answers a weaker question — a filter can be shadowed by an
  earlier one, attached to a handler since replaced, or raising.
  `GET /identity/status` reports `canary_leaking` and names where a leaking
  handler writes. The canary is filtered, never handled, so no canary line ever
  reaches a log.
- **A config keyword with nothing after it is a mention, not a setting.**
  `_VALUE` refuses to capture a token starting with `[ ] | < > ( )`. Found live:
  `show running-config | include snmp-server community [in /home/…:2613]` — an
  operator *searching* for the community, where the token the pattern ate was
  the log formatter's own `[in`. Masking it corrupted the line and protected
  nothing.
- **The mask string is `<redacted:<label>>`.** `render_artifact.MASK`
  (`••••••••`) is a **different** mechanism, for template previews — grepping
  logs for bullets will never find redactor output.
- **It fails open, and the failure is visible.** A record that cannot be
  redacted is written unredacted rather than dropped — a log that silently
  loses entries is the worse failure in the file an operator reaches for when
  something has already gone wrong. That is only defensible while the failure
  is *visible*, so failures are counted and reported by `redact.health()` in
  `GET /identity/status`; a log line announcing that the log is unreliable is
  written in the medium that just became unreliable. An unreadable credential
  store counts too, since the filter itself never raises in that case.
- **The filter is re-entrant-guarded and the secret table is cached.**
  `known_secret_values()` logs on failure, and that record re-enters the
  filter — unbounded recursion that can hang the process. A thread-local guard
  skips the **value lookup** (the part that recurses) but still applies
  **positional** redaction, which needs no store: the reentrant record is a
  credential-store failure whose exception text can quote a config line or a
  ciphertext, so the one record most likely to carry a secret must not be the
  one written in the clear.
- **The secret table is cached 30s, and every credential write invalidates it.**
  The invalidation lives in `credentials._save()` — the one chokepoint every
  profile, override, deletion, template secret and scope migration passes
  through — plus `device.write_devices_csv()`, since device passwords live in
  the CSV rather than the store. Six call sites would be six chances to add a
  seventh and forget. This is what item (4)'s rotation depends on: a brand-new
  router password must be redacted on the very next record, not at the next TTL
  expiry, because rotation logs its commands and its verify output immediately.
- `GET /identity/status` reports **`may`** — what *this caller* can do, with a
  reason when false — not which gates are enabled. The earlier `gates` field
  reported configuration, and `gates: {reveal: true}` reads as permission while
  meaning the gate is *closed*; it was misread within minutes of first being
  shown. Computed through `identity.may()`, the same function the gates use, so
  the diagnostic cannot drift from the gate.
- **Automation sends an honest User-Agent** (`nmas-automation/1.0`). Measured:
  Cloudflare's integrity check accepts it and rejects `Python-urllib` with
  403/1010. No browser impersonation was needed.
- **Automation uses a Cloudflare Access service token**, not an exemption:
  `CF-Access-Client-Id` / `CF-Access-Client-Secret` through the tunnel, Access
  issues an assertion, and the identity layer verifies it like any other.
  Cloudflare issues the **same shape** for people and services — `type: "app"`
  either way, so `type` is not a discriminator. A person carries `email` with a
  UUID `sub`; a service carries `common_name` (its Client ID) with `sub: ""`
  and no `email`. `_actor_from_claims()` handles that explicitly, and the
  service actor is prefixed `service:` so no reader mistakes a Client ID for a
  person. The audit row records `kind`, because "a person approved this" and
  "a script approved this" are different facts about a change.
- `GET /identity/status` is the end-to-end diagnostic: not gated by identity
  (a diagnostic that hides behind identity is useless when identity breaks),
  echoes no configuration, and returns the email only to the requester.
- **`GET /identity/posture` shows every gate's EFFECTIVE value and its
  ORIGIN** (Phase 3.2c). The keys are built by f-string with a default of
  `True`, so *unset* and *set to the default* are indistinguishable by
  reading the file — and `migrate()` returns early once the stored
  `settings_schema_version` has caught up, so **a key added to `DEFAULTS`
  after an install reached v1 is never written to that install's file**
  (measured; `added_keys` is empty and `get_setting()` returns the default
  anyway). Until this panel the gates deciding whether a human must authorise
  a reveal, an approval, a confirm or a publish were visible only by reading
  JSON over SSH — the shape that lost the drift checker for 24 days. Values
  come from `identity.posture()`, which reads through the same `_setting()`
  the gates call, so the panel cannot drift from the gate.
- **The panel is read-only and says why, in words.** A greyed field says "you
  can't" and never says why: changing a gate from a browser would let a
  compromised session lower its own gate, using the very permission it was
  editing. **Gate states are shown to anyone** — "a person is required to
  reveal a secret" is a posture statement, and hiding it protects nothing
  while making it uncheckable. **The Access team domain and AUD are not**:
  they are what an assertion is validated against, so they go to a verified
  person only, the AUD abbreviated to its ends, peers counted rather than
  listed, and the refusal is stated rather than the fields silently omitted.
- Bind `NMAS_HOST` to a specific address rather than `0.0.0.0`, as a second
  layer independent of the firewall — note this stops `localhost:5000` working
  on the host. The firewall must cover **both address families**: port 5000 is
  closed over IPv6 only because no `[::]` listener exists, not because anything
  blocks it.
- **The drift check's population is the inventory, not the golden store**
  (Phase 3.3). It iterated the enumerator above, so a device with no legacy
  file was never checked and appeared in no count — not an error, not a skip,
  simply absent, and "all 9 device(s) clean" over a ten-device inventory is
  textually identical to the same sentence over nine. A device with no golden
  at all was a bare `return`. Every device now lands in exactly one bucket
  (`checked` / `no golden` / `stale` / `unreachable`), the totals are checked
  against the inventory size with any remainder reported as a defect, and the
  panel says **"checked 7 of 9"** with the other two named. The badge cannot
  read `Clean` when nothing was checked.
- **A silenced check must say what it silenced.** Drift scheduling was
  switched off on 2026-08-30, three minutes after a run that flagged all nine
  devices against ad-hoc, stale goldens — correct then. Six months on, the
  reason had been fixed for weeks and nothing anywhere prompted a
  re-evaluation: the state file was the only record the checker had ever been
  on, and it recorded neither who switched it off nor when. `set_disabled()`
  now records `disabled_at` / `disabled_by`, the panel shows the note and the
  last run it saw instead of blanking the line, and `status()` reports
  `state` as **disabled / idle / running** — a scheduler alive and waiting
  used to look exactly like one switched off.
- **The drift state file records; memory decides.** Three keys, read at three
  different times: `disabled` is **live** (re-read every pass of the loop, so
  an edit takes effect within a minute), `last_check_ts` is read **once at
  process start** to rebuild the schedule across a restart, and `last_result`
  is a record. **The schedule itself is `DriftChecker._next_ts`, in memory,
  and the file cannot move it** — it is set at construction from
  `last_check_ts + interval`, then only by a completed run, `trigger()`,
  re-enabling (`now + interval`), or an interval change. The scheduler used
  to *write* a `next_ts` key that nothing anywhere read; an operator set it,
  waited, and nothing fired. It is no longer written, `status()` reports
  `next_from: "memory"`, and the panel says so on the next-run time. Editing
  one key in that file works and editing the one below it did nothing, with
  no indication which — the same shape as the toggle that silently reverted.
- **Drift state is per list** (`data/lists/{slug}/drift_state.json`), adopting
  the old installation-wide file forward by **copy, not move**. One switch
  governing several networks tells you nothing about the one you are looking
  at. `_save_state()` merges rather than replacing: the scheduler's `finally`
  wrote a fresh three-key dict that would have dropped `disabled`.
- **`netbox_client._scan_device` is deleted** (Phase 3.3): 140 lines of SSH
  scanner with no callers. The NetBox import runs from golden configs by
  design — it works for an offline device, and importing observed state into
  the source of truth is the wrong direction. Refreshing a golden and
  re-importing is one store and one direction.
- `scripts/check_removed_definitions.py` **tells a use from a mention.** It
  parses rather than greps: a docstring or comment naming a deleted function,
  and `assert not hasattr(mod, "x")`, are not references — deleting something
  and pinning its removal are the same commit, and a gate that cannot be
  satisfied gets run with `--no-verify`. Whole-word, because
  `"_scan_device" in "_scan_device_from_golden"`. An unparseable file still
  counts as a reference.
- **An unhandled exception must never present as a successful redirect.**
  `@app.errorhandler(Exception)` redirected *everything* to the index, so
  every JSON route in the app answered a crash with `302 /`: the `fetch`
  followed it, got a page of HTML, and the caller either failed to parse it
  or swallowed it. Measured on `POST /drift/settings` — a `TypeError` reached
  the operator as a toggle that flicked back, with nothing on screen. The
  handlers now redirect a **navigation** and return JSON with a real status
  to anything else, decided on the literal `Accept` header: werkzeug's
  `accept_mimetypes` cannot tell `*/*` from an explicit preference, so any
  quality comparison picks a winner by tie-break. Error detail goes through
  `redact_text()` — unlike the log, this leaves the host.
- **A route reports what was STORED, not what was asked for.**
  `/drift/settings` echoed its own input, so a save that did nothing returned
  success and the panel reverted the control on the next poll.
- **A wrapper method's signature is pinned against what it wraps.**
  `DriftChecker.set_disabled` shadows the module-level `set_disabled` by name
  and delegates to it; 3.3c added `actor` to one and not the other, and the
  shared name is what made it look edited. Seventeen tests passed because all
  of them called the module function while the route calls the method.
  `test_drift_routes.py` exercises the route over HTTP and compares the two
  signatures — a test asserting the *shape* of a call cannot see a signature
  that does not exist.
- Silent failure is the dominant failure mode in this stack. Every integration
  call must log and surface its failures rather than swallowing them.
- `modules/pipeline.py` and `modules/pipeline_builder.py` are real, tested, and
  mostly unused. Don't mistake them for dead code — Phase 3 depends on them.

## Known defects deferred to later phases

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
- **`restore_golden_config` is a fourth config-push path**: whole golden
  replayed in config mode with no confirm hash, no merge-only check, no ASCII
  guard, no dangerous-line authorisation, no snapshot, no rollback, no
  breaker, and `device_ips: ["all"]` targets the fleet. The same shape was
  removed from the approval queue's `revert_to_golden`, which hands off to
  the confirmed restore path; the AI's copy was not part of that correction
  (Stage 8.3).
- **`detect_config_drift` is a third drift implementation**, carrying the
  pre-3.3b shape — no inventory accounting, no named skips (Stage 8.2).
- **The background agent has been disabled throughout the NSoT work**, so
  `agent_runner.py` is the least-exercised code in the program. It is
  re-enabled **last**, after the tool library and the authority gate, with
  one real run observed — the same bar drift had to clear (Stage 8.4).
