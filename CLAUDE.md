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
- **[modules/nsot/freshness.py](modules/nsot/freshness.py)** — is Oxidized's
  copy of a device the approved one; the gate, the signal, and the
  authorisation path
- **[modules/integrations/](modules/integrations/)** — one client per external
  tool (NetBox, Prometheus, Grafana, Loki, Oxidized, Kea, topology service, NSoT
  git, S3). Phase 0 ships `test_connection()` only; Phase 5 adds read clients.
- **[routes/](routes/)** — Flask blueprints: `settings_integrations.py`,
  `netbox_safety.py`, `inventory.py`, `golden.py`, `templatize.py`,
  `templates.py`, `deploy.py`, `freshness.py`

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

**Secrets are in three stores, not one** — see [docs/SECRETS.md](docs/SECRETS.md).
`user_settings.json` holds the ones `secrets_store.SECRET_KEYS` covers;
`data/jenkins_checks.json` holds the Jenkins credentials, now encrypted via
`jenkins_runner.SECRET_FIELDS` (**a second store needs a second mechanism** —
adding them to `SECRET_KEYS` would encrypt nothing while making it look
covered); `.env` holds `ANTHROPIC_API_KEY` in **plaintext by design**, since
encrypting it would have the app decrypt its own key at startup using a key
in the same directory with the same mode. `scripts/nmas-check-secret-storage`
reports all three by name and never by value. `scripts/nmas-settings-diff` lists
what in the file **differs from its default** — the only surviving signal for "what somebody chose" once a re-seed has written every key, since
`origin_of()` then answers `file` for all of them. Names only; a secret reads
`set`, and re-entering one means going back to the system that issued it.

**Modes are set at CREATION, at `0600`/`0700`, by `config.open_secure()` and
`config.secure_dir()`.** Nothing in the program set a mode before 2026-09-23:
`os.makedirs()` and `open()` take the process umask, so on the deployment host
`data/` was `0755` and every file in it `0644` — world-readable, including
`key.key` and an `.env` holding the Anthropic API key, for three weeks.
Fixing modes by hand fixes one install; the creation site fixes every install.
`open_secure()` applies the mode **before** writing (`os.open(..., 0o600)`),
because creating `0644` and chmod-ing after leaves a window with the secret on
disk and world-readable.

**`data/key.key` is the floor.** Everything "encrypted" is encrypted with it,
so its mode and the encryption are one control, not two — a group-readable key
means the ciphertext beside it was never protected. It has **two producers**
(`device.load_key`, `secrets_store._get_fernet`), deliberately separate, so
both create it owner-only and `device.load_key` also tightens an existing one.
The checker tests it first and separately.

**Tightening a mode does not undo exposure.** Anything that read a secret
while it was readable still has it; rotation is what makes past exposure moot.

**`0600` is right for a file the APP owns, and wrong for a handoff.** A file
one service writes and another reads has to name the reader — measured the
hard way: `chmod 600` on Kea's password file, root-owned, stopped the Control
Agent (running as `_kea`) from reading its own password. `0640` owned by the
service user is the target there. `scripts/nmas-oxidized-cred` already has the
right shape and is the one place NMAS writes for another service: it
preserves the original's mode and owner rather than asserting its own.

**A trailing newline is part of the password.** Kea includes it; `$(...)`
strips it; the result is a 401 that reads as a wrong password and is a
one-byte difference. Anything writing a credential to a file another service
reads writes it with no trailing newline and says so at the write site.
`nmas-oxidized-cred` refuses a newline outright rather than stripping one —
silently stripping would store something other than what was supplied.

**Every schema key is surfaced or documented file-only with a reason**
([docs/SETTINGS.md](docs/SETTINGS.md)), and a test fails on a key that is
neither. **`pause_agent()` persists nothing** — it sets an in-memory Event, so
a pause is lost on restart while `background_agent_enabled` (the persistent
switch, which had no control until 3.2d) survives. Two controls that look like
one switch, and only the invisible one survives a restart.

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
| `test_oxidized_freshness.py` | the raw config is the artefact; the gate can reach its own finding; an authorisation covers one divergence; only exit 1 is drift |
| `test_credential_never_changes_on_deploy.py` | a deploy adds an account and never changes one; the refusal names the form, never the value |
| `test_inventory_dispatch_refuses.py` | the no-argument form resolves the active list; a name where a path was wanted refuses; a correctly built path never does |
| `test_new_container_programs.py` | a stanza the device lacks: emitted once, undone by a single negation, and a fixture that can actually contain the case |
| `test_deploy_plan_apply_seam.py` | plan driven into apply: the capture-hash handshake, and the command_hashes the wizard does not send |
| `test_authoring_schema.py` | omitting an interface key is fine and misspelling one is refused; filling changes no output |
| `test_onboard_dhcp_source.py` | dhcp is a source not an absence; the reservation refuses at plan time; the review claim is checkable |
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
| `test_secret_file_modes.py` | every secret file created 0600 by its creator; Jenkins credentials encrypted at rest |
| `test_agent_failure_surfaces.py` | failure streak, same-error, ERROR log, red badge; the stale trigger stays fixed |
| `test_disabled_is_a_state.py` | a disabled read still carries its history; every degraded GET classified |
| `test_agent_panel_renders.py` | the shipped JS executed in duktape: what RENDERS while disabled, not what the endpoint carries |
| `test_netbox_census.py` | identity per type, tagged separately, and the comparison can say no |
| `test_onboard_plan.py` | `build_plan` the only constructor; every refusal at once; a check that did not run has not passed |
| `test_onboard_bootstrap_credential.py` | the crash window survives; one staging mechanism; a failed rotation does not report success |
| `test_onboard_ordering.py` | no commit CREATED on failure — count, sha, reflog, orphan, hook; the commit last among the fallible |
| `test_onboard_wizard_renders.py` | the shipped renderer executed: every blocking reason on screen with Create disabled |
| `test_onboard_snmp.py` | RW removed verbatim; the nine RO communities untouched, against the fleet fixtures |
| `test_platform_keying.py` | every consumer declares its namespace; one translation table; the boundary refuses a slug |
| `test_onboard_drift_enrolment.py` | a device is covered the moment it is in the inventory; named before its first capture |
| `test_scale.py` | 900 devices: the page cost pinned as a NUMBER, so bounding the list must update it |
| `test_probe_topologies.py` | every `cisco_c8000v` probe node binds a launch patch, from its own copy |
| `test_bootstrap_manager_address.py` | the bootstrap config reaches the manager AND stays a bootstrap: address emitted, no IGP/loopback/route |
| `test_inline_javascript.py` | every parser available, one input: the RENDERED page; raw-Jinja control pinned |
| `test_onboard_abandon.py` | release refuses while named; abandon reverses creation; a partial abandon never reclaims |
| `test_onboard_pending.py` | pending has an exit; 24h/7d; promotion refuses the bootstrap credential |
| `test_onboard_phase2.py` | reaching is the verification; silence is not a cause; the banner tells error from empty |
| `test_onboard_phase_two.py` | the full phase: every step reported, promotion last, the first golden a true record |
| `test_settings_file_integrity.py` | absent vs unreadable; a write on defaults refused; the save is atomic |
| `tests/fixtures/fleet_scale.py` | a fleet of any size with a realistic state mix (not a test module) |

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
- **"Disabled" is a STATE to report, not a reason to withhold.**
  `GET /ai/agent_log` returned `{"entries": [], "status": {}}` with a 503 the
  moment AI was switched off — so disabling the agent **suppressed the 26
  failures and the workspace-id error that were the reason for disabling
  it**. The health surface built so a dead component could not look quiet
  went silent exactly when its history mattered most. The mechanism is worth
  naming: **the guard was correct for an older payload.** When the route
  returned only a log, "AI is disabled" plausibly meant "nothing to say";
  adding `health` changed what it carries and nobody revisited the guard. A
  guard ages against its own payload.
  **A read reports; an action refuses** — `/ai/agent_run`, `/ai/agent_pause`,
  `/ai/agent_resume` and the timer POST still 503, because a disabled agent
  must not be made to act. Surveyed: 18 routes short-circuit on a
  disabled/unconfigured state, 15 are actions and correct, and of the three
  GETs only this one was withholding. `test_disabled_is_a_state.py` scans for
  every GET that *names* a degraded state in a return and requires each to be
  classified **reports** or **fetches** — a list that must not grow silently
  and must not keep ghosts.
- **The client has its own guards, and server tests cannot see them.**
  Three guards in one feature each hid the same data, and **every test passed
  at each stage while the screen said nothing**: the route's 503, then
  `success` meaning "no exception reached the top", then `loadAgentTab`'s own
  *"AI is disabled — enable it in Settings"* branch. The boundary kept being
  drawn above the last remaining guard. The render is now two **pure**
  functions — `agentHealthBanner`, `agentBadgeState` — and
  `test_agent_panel_renders.py` **executes the shipped source in duktape**
  against the payload the deployed endpoint returns, asserting what lands in
  a stub DOM. Duktape parses `async` but has no event loop, so the test
  strips the asynchrony **and only that** — no branch is touched, and it
  asserts the strip applied. Swept the templates: `loadAgentTimers` blanked
  its panel and is fixed; `loadRemotePanel`, `topoSvcRefresh` and
  `_stackRender` all render a reason and are correct; `base.html`'s single
  `_aiEnabled` guard is on an auto-troubleshoot `setInterval`, an action,
  correctly skipped.
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
- **A blueprint route's full path appears nowhere in its source** — the
  `url_prefix` is applied at registration, so grepping for
  `/netbox/safety/remove/preview` cannot succeed however correct the route
  is. `app.url_map` is the only authority;
  `scripts/nmas-verify-runbook <file>` resolves every `curl localhost:5000/…`
  in a runbook against it, method included. Same family as a dict `.get()`
  returning its default: **a lookup that misses is a fact about the query,
  not about the system.**
- **A pattern that can appear in English needs an anchor.** Match a code
  construct at the start of a line, or parse it — never as a bare substring
  of a file that also contains prose about that construct. Four instances so
  far: a test matching a docstring, a checker matching a docstring, a test
  matching its own explanatory comment, and a test whose `{% if devices %}`
  search found the comment explaining why the button sits above that block.
  **The better the comment, the more likely it quotes the code it explains**,
  so the places most likely to carry an explanatory quotation are the places
  most likely to have a test asserting something subtle.
- **The interface is for an enterprise network, not for nine devices**
  ([docs/NSOT_STAGE7_GUI.md](docs/NSOT_STAGE7_GUI.md) §0a) — a constraint on
  the Stage 7 architecture, not a later feature. Measured with
  `scripts/nmas-scale-report` against `tests/fixtures/fleet_scale.py`: the
  page is **647 KB fixed plus 2,239 bytes per device**, linear and unbounded
  — 2.7 MB at 900 devices, a projected **23 MB at 10,000**. The 100×→4×
  ratio is reassuring and wrong; the marginal figure is the one to quote.
  **The 647 KB fixed cost is a separate finding** (§0b), true at nine devices
  today: 97% of the current page, re-sent on every load before a single
  device row, and fixed by moving inline script into cacheable files rather
  than by bounding anything.
- **The fixture corrected the premise it was built to test.** The constraint
  was first written as "nothing may load the whole inventory"; measured, the
  read is 0.73 ms and a per-device `git log` is 7.2 s, so it is **"nothing
  may do per-device work per request"** — a different design, and one that
  does not send Stage 7 through 75 call sites that mostly do not matter. A
  call site reading the whole inventory is not evidence of a problem; what
  follows the read is.
- **Bounding the read fixes almost nothing; bounding the per-device
  operation is the whole job.** Measured at 900 devices: `load_saved_devices()`
  costs **0.73 ms** and a lookup after it 0.01 ms, while *one operation per
  device* costs 0.3 s for a golden read, **7.2 s for a `git log`** and
  **225 s for an SSH round trip**. So the 75 unbounded call sites are not 75
  equal work items — a site that reads and looks one device up is fine at any
  size; a site that then touches git, a file or a device per row is a **job,
  not a request**. The landing counts must not come from a full read not
  because the read is slow, but because *"is this drifted, is its template
  approved, when was it rotated"* are per-device questions.
- **A suite of "nothing is wrong" assertions cannot distinguish a healthy
  system from an absent one.** Every scan needs a companion that names
  something concrete it expects to find. The slug/dialect gate was caught by
  a test asserting *"the blocked platform IS LISTED"*, written for an
  unrelated reason — while the refusal's own test, the reachability check,
  the removed-definition check and every "no offenders" scan all passed. **A
  gate that silently opens produces no offenders**, which is exactly what
  makes it invisible to negative-space testing. The set-difference floor is
  the mechanical form of this rule; `_the_scan_finds_something` is the
  pattern's name in this suite.
- **Three platform namespaces, and only `platform.py` translates between
  them.** `platform_map` and NetBox are keyed on **slugs** (`cisco-ios-xe`);
  `bootstrap_config`, the parsers and the template directories are keyed on
  the **config dialect** (`cisco_iosxe`). A dictionary lookup that misses
  returns the default, so looking a slug up in a dialect table is a **gate
  that silently opens** — measured: `/onboard/platforms` reported every
  platform unblocked, including the one stage D blocks. Call
  `platform_for_device()`; a second copy of the mapping is how the two come
  to disagree, and a test asserts there is exactly one. `assert_dialect()`
  refuses a slug or a driver at a boundary that needs the canonical form.
  **There is no `PlatformRef`**: `ListRef` exists because a list's name and
  slug are *both stored and compared*, whereas a platform has one stored form
  (the dialect) and two input formats — a translation problem, not an
  identity one. `test_platform_keying.py` records which keying each of the
  eighteen files carrying a platform literal means, because three namespaces
  overlapping on `cisco_ios` cannot be told apart from the value.
- **The RW community a vrnetlab node arrives with is removed during
  onboarding**, and the pattern **requires the access mode**: over-broadening
  would propose removing the fleet's nine `public RO` communities and take
  Prometheus, the SNMP collector and the trap receiver with them. The removal
  is the device's own line **verbatim** — a rebuilt line drops the ACL, and
  `no snmp-server community public RW` against a device whose line reads
  `… RW 99` is a command that does not match. The plan reports what is
  **kept** as well as what is removed.
- **NEVER LET A WRONG THING LOOK LIKE A WORKING THING.** The governing
  design requirement, and the one this tool can actually keep.
  **What infrastructure-as-code here genuinely protects:** drift between
  intent and reality, and the recurrence of a fixed mistake — the deploy
  path's preview *is* what is sent byte for byte, merge-only never negates,
  and the program is recomputed at apply and refused if anything moved.
  **What it cannot protect:** a value that is wrong at the source. A
  mistyped interface for a device that does not exist yet is faithfully
  recorded, rendered and deployed. *IaC guarantees you did what you said; it
  cannot know that what you said was wrong.* Stating the limit is part of
  the principle — a tool that implies more is itself a wrong thing looking
  like a working one.
  **Apply it as a design test, not a slogan:** for each new feature, name
  the state in which it would be **wrong and look right**, and say what
  makes that state visible. **If the answer is "nothing", that is the gap to
  build.** Every mechanism that has earned its place here has this shape —
  `inconclusive` rather than `failed` when nothing was established,
  *"checked 7 of 9"* rather than a number that reads as complete,
  *"nothing has been created yet"* printed only while it is still true, an
  advisory that informs without blocking, a rollback that reports what
  **landed** rather than what was pushed, and a device that must answer SSH
  before it counts as onboarded.
  The two rules below are this same principle stated as its failures: a
  vacuous assertion and a silently-opening gate are both a wrong thing
  wearing a passing result.
- **An assertion over a set difference passes vacuously when either set is
  empty — it needs a floor on its inputs.** `assert not (A - B)` proves
  nothing until `A` is known non-empty, and a scan that found no offenders is
  indistinguishable from a scan that could not run. The floor need not be
  exact: `assert len(used) >= 12` against a measured 15 guards the failure
  that matters, which is the regex matching *nothing*. Same family:
  `assert all(...)` over an empty iterable, `assert expected.issubset(found)`
  with an empty `expected`, and any "no offenders" list comprehension.
  `test_blueprint_reachability.py` and `test_disabled_is_a_state.py` both
  carry a `_the_scan_finds_something` test for this reason.
- **A `cisco_c8000v` probe node that binds no launch patch does not boot
  here, and the worse half is silent.** Three times this one per-node line
  has been the difference, each time measured on the lab host: the first
  bootstrap probe (stock script, 1 vCPU, never completed in ~40 minutes),
  stage B, and `nmas-onboard-c.clab.yml` on 2026-09-23 — shipped with no
  `binds:`, launched *"with 1 SMP/VCPU"*, 112% CPU, **grinding rather than
  stalled**, which is the first probe's failure exactly. The patch does two
  things and **the second is the one a probe cannot show you**: `smp="2"`
  fails loudly and costs 40 minutes, while a missing user-skip *succeeds* —
  vrnetlab injects `username admin privilege 15 password admin` ahead of the
  startup config, IOS-XE refuses a secret for a user that already has a
  password, and the node boots on `admin`/`admin` **reporting healthy**. In
  the Stage 4C onboarding probe that would mean the probe **passes by
  reproducing the hazard stage 2 exists to prevent**, inside the wizard's
  first run. `test_probe_topologies.py` asserts it instead of remembering
  it, with floors on both the file and node counts and a negative control
  driving the same function against a topology built to fail.
- **The bind is the probe's own copy, never `~/labs/lab/patches/`** — a
  throwaway lab whose teardown can reach into production is not throwaway.
  Staged by runbook step 3a and named `c8000v-launch-adopted.py`, because
  `c8000v-launch.py` in that directory is the stage-A/B copy that
  **deliberately predates the user-skip**: it is what makes
  `nmas-bootstrap-probe.clab.yml` reproduce the hazard, and writing the
  adopted script over it would silently retire the probe that measured the
  thing.
- **"Management interface" names two different networks, and conflating
  them made the generator emit a config nothing could reach** (4C.8).
  `mgmt_interface` is the **containerlab-facing** one — the `clab-mgmt` VRF,
  the docker bridge, and nothing off the containerlab host has a path to it.
  `manager_interface` / `manager_address` is the **manager-facing** one: a
  data interface in the global table, on a segment the NMAS can reach.
  Measured 2026-09-23 — the NMAS reaches the lab on `enp6s19` at
  `10.255.0.10/24`, s3's `Vlan99` is the gateway at `10.255.0.1`, and every
  device's `10.255.1.x` is a **`/32` loopback advertised into OSPF**, so
  `dummy0` holding `10.255.1.10/32` on the NMAS is an identity and not a
  segment. `render_bootstrap()`'s docstring had claimed "what remains is what
  makes the device reachable"; what remained made it **boot**.
- **In an in-band-managed network there is no config that is both minimal and
  sufficient.** The bootstrap/deploy split assumes management reachability
  that does not depend on the configuration being deployed; where management
  is in-band, "reachable" and "configured" are the same event. Reproducing
  how r1–r5 are reached would need a `Loopback0`, a core-segment address and
  `router ospf 1` in a config whose whole point is to have no routing. The
  way out is a segment the manager is **L2-adjacent to** (`Vlan99`), which
  needs one interface stanza and **no route at all** — the NMAS shares the
  `/24` and always initiates. Both of those are **conditionals, written at
  the emit site** in `manager_interface_lines()`, because they hold only
  while the manager shares the segment.
- **The interface for a management address is chosen, never defaulted.** On a
  C8000v vrnetlab owns Gi1; an address landing there fights it. The generator
  raises `ManagementAddressRequired` rather than guessing, and `build_plan()`
  makes it a blocking reason — a default is how a guess becomes a silent one.
  The two coexist: r1–r5 run Gi1 in `vrf forwarding clab-mgmt` and their data
  interfaces in the global table at once.
- **A route that rebuilds a plan at confirm must read the request the same
  way it did at preview.** `/onboard/create` sent `body: '{}'` from the
  client, so the deliberate rebuild produced a plan with no hostname and no
  address and could only answer 409 — **create had never succeeded.** One
  `_plan_args()` on the server and one `onboardFormPayload()` on the client
  now serve both calls. Neither the renderer test (executes the render, not
  the fetch) nor the ordering test (calls `run_onboarding` directly) could
  see it: **it lived in the seam between them**, the same shape as the three
  guards in the agent panel.
- **A refusal must name the right cause.** A bootstrap render failure was
  being reported through `unsendable`, so a missing netmask was announced as
  "lines contain characters an IOS CLI cannot accept" and sent the reader
  looking for an em dash. `render_error` is its own field and its own reason.
- **Two checks of one property will diverge, and the older one reported a
  defect in correct code.** `test_inline_javascript.py` held a `node --check`
  over **raw templates** beside a dukpy check over the **rendered page**. The
  dukpy one was written later and its docstring names the exact reason —
  `window.applyAiEnabled({{ ai_enabled | tojson }})` is valid Jinja and, read
  as JS, an object literal where a property name belongs. The older check
  stayed green only because **node was installed on neither machine**;
  installing it to run the suite turned the check on for the first time and
  it failed on the two blocks its sibling's docstring had named in advance
  (`base.html:885`, `index.html:6628`), both correct and both working in a
  browser. Merged to one input and several parsers — dukpy always, node when
  present — because what differed was not the parser but **what it was
  pointed at**. The raw-Jinja form failing and the rendered form passing is
  now an assertion, not a docstring.
- **A failure report that omits the failure costs a diagnosis and looks like
  one.** That check printed `stderr.splitlines()[-1]`, which on node 18 is
  the version banner: a real syntax error reported `Node.js v18.19.1` and
  named no file, line or token. Take the first line containing `Error`.
- **A refusal must never report that nothing failed.** Phase 2's second live
  run returned `failed_checks: []` beside state `failed_before_any_change` —
  "something stopped me and nothing failed", which is worse than the state
  alone, because the state alone did not claim to know. Three causes, each
  of which alone produces that output: the exit was the **confirmation
  fingerprint**, compared *after* preflight passes, so every check was `ok`
  and the empty list was truthful; `finish_bootstrap` read
  `result["error"]`, a key `rotate()` never sets, over the `reason` it does
  set; and the reporting read one field. `_rotation_refusals()` merges
  `steps` and `preflight_checks` rather than choosing, so neither has to be
  canonical, and an empty answer is **impossible** — reason, then state,
  then plainly that the refusal was unattributed, which is a defect report
  rather than a blank. A **successful** rotation returns `[]`: the
  never-empty rule is about refusals, and applying it to every result made a
  success report a defect in its own reporting — the invariant eating the
  distinction it was built to protect, caught by the one control that asked
  whether a success returns nothing.
- **`SELF_CONFIRMED` is an exemption that is RECORDED, not a check skipped.**
  Onboarding's phase 2 is one click running seven steps: no separate plan
  step, so no window between plan and apply for the fingerprint to protect.
  The first version invented `sha256("onboard-confirmation|host|ip")`, which
  can never equal `fingerprint_for(pre)` — **verbatim the defect that
  function's docstring describes** — so every phase-2 rotation refused,
  permanently and safely. `rotate()` records honouring the sentinel as a
  step, because a check that passed because it did not run is exactly what
  the fingerprint was added to stop. The second version called `preflight()`
  inside `run_phase_two()`: correct about the function, and it put a **live
  SSH session** inside a function whose collaborators are otherwise all
  injected — ten seconds per call, 221 seconds across the suite. A socket
  spy pins it.
- **A control that passes is either a missing test or a broken control, and
  telling which is the work.** Deleting the `SELF_CONFIRMED` branch from
  `rotate()` — which *is* the live failure — left the whole suite green:
  phase 2's tests stub `rotate` and cannot reach the comparison, and the
  rotation suite never sent the sentinel. **The seam between two tested
  halves**, third this stage after `body: '{}'` and the agent panel's three
  guards. The missing test is `TestSelfConfirmationAtItsOwnSite`, and it
  carries its own control that the exemption is not the check removed —
  widening it to `if confirmed_fingerprint:` fails seven tests, four of them
  pre-existing.
- **A pass count that cannot distinguish "passed" from "never ran" is not a
  pass count.** With no pytest available, 4C.8's test bodies were executed
  through a hand-rolled driver that ran only `Test*` classes and fixtureless
  `test_*` functions and **silently skipped the rest** — the vacuous-pass
  failure inside the tool built to hunt vacuous passes, and with no
  `_the_scan_finds_something` floor of its own. The tell was visible and
  unread: one file reported **0 passed** under one driver and **4** under
  another, the same file at the same moment. Every "N passed" claimed during
  that stage was harness-only; the first real run was 2,638 passed / 6
  failed.
- **The onboarding target list is carried, never derived.** `_active_list()`
  fell back to `get_current_list_name()` — the same shape as
  `PipelineContext.list_name`, which was corrected after a list switch during
  a convergence window committed one network's captures into another's repo.
  The asymmetry is what makes it worth a refusal rather than a default:
  onboarding into the wrong list leaves a **commit, a NetBox object and a
  CSV row** in a live network, and the repair is the provenance-based Remove
  — **the mechanism Stage 4C exists to prove, and which has therefore never
  run.** The list also decides what every other field *means* (collision
  checked in that manifest, credential from that resolver, NetBox objects
  under that slug) and was the only one inherited rather than stated.
  `_target_list()` raises `NoTargetList`; the wizard sends it as an ordinary
  field. Note `/onboard/create` answers **403 before 400** — identity gates
  ahead of input validation, which is the right order.
- **Merging two of three copies is not a partial fix; it concentrates the
  divergence in the one left behind.** The onboard form's field list lived in
  `_plan_args()`, `onboardFormPayload()` and a hardcoded array of element ids
  bound to re-validation listeners. The first two were merged, the third was
  not, and 4C.8's three new fields were **read and sent correctly while being
  watched by nothing** — so filling in the netmask left "no network mask" on
  screen. Nothing was wrong with the payload, which is why neither end showed
  it: the defect existed only in the relationship. `ONBOARD_FIELDS` is now the
  one list. **A tool that looks broken while working is worse than one that
  fails** — it teaches the operator to stop reading the panel that is the last
  thing between them and a commit.
- **Template approval is an ADVISORY on the onboarding path, not a gate**
  (4C.8). Measured: `approval.approve()` refuses an empty device set —
  correctly, that being the assertion-over-an-empty-set failure — so a fresh
  list cannot approve a template, cannot therefore onboard, and cannot
  therefore acquire the device the approval needs. **The wizard could not
  onboard the first device of a network.** Only a genuinely fresh list
  exposes it; a probe against a populated list sails past. The gate was also
  keyed on the wrong property: `run_onboarding`'s steps are credentials →
  netbox → commit → render, `render_step` returns `render_bootstrap()`'s
  output, and **no step reads `plan.template`**. Phase 3c's rule generalised:
  **gate on what the artefact actually depends on.** What it protected is
  checked where it belongs — the deploy path validates approval per plan, per
  device, with the lines named. `OnboardPlan.advisories` is computed beside
  `blocking_reasons`, never merged, its own key in `summary`, and reads as a
  next step ("…which needs a captured device to validate against"): a warning
  about nothing trains the reader to skip warnings. The failure mode is an
  advisory list that swallows a refusal, so the controls assert a genuine
  blocker still blocks *and* is drawn above the note.
- **A docstring that explains why an ORDERING exists, then names the ordering
  as a SOURCE.** `render_step` said "the downloadable artefact, from
  **committed** intent"; it returns `plan.bootstrap_config`, rendered from
  hostname, secret, domain and address. Running after the commit is
  deliberate — nobody should download an artefact for a device the NSoT has
  no record of — but that is not where the bytes come from. Third this stage,
  after `manifest.py`'s slug example and `render_bootstrap`'s "what remains
  is what makes the device reachable". All three were confident prose beside
  correct code, which is what lets them survive review.
- **Onboarding is two phases, and a device is onboarded when the tool has
  REACHED it.** Phase 1 (credentials -> NetBox -> commit -> render) touches
  no device and leaves it **pending**: in the manifest, in NetBox, in git,
  and deliberately **not in the inventory** — a device in the inventory is
  one the program polls, backs up, drift-checks, pools a connection for and
  offers in bulk ops, and one that has never answered would read as
  unreachable in nine places and mean nothing in any of them. Phase 2
  reaches it and `promote_device()` adds the row. `writes_devices_csv` used
  to report **yes** while no step wrote one.
- **Reaching the device is what verifies the management interface**, and
  there is no earlier moment: the name is checked for spelling and never
  against the device, because the device did not exist when the config was
  generated. So the UI says *unverified until reached* rather than implying
  the field was validated.
- **Three verification states, not two.** `answered` is a fact about the
  device. `answered_but_refused_the_credential` rules out the interface and
  the address, because something is there. `did_not_answer` **proves nothing
  about why** and must never be recorded as "wrong interface" — the causes
  are offered as possibilities, most-worth-checking first, each with the
  console command that settles it and the staged-credential recovery command
  **with the real repo path**. Same distinction as `inconclusive` is to
  `failed`; the rotation path already had to correct a classifier reading a
  connection failure as a device verdict.
- **A pending state nothing renders is the defect the state was built to
  avoid**, so the banner shipped with the flag and `promote_device()` was
  written before either — a state an operator cannot clear is a name that
  cannot be released, wearing a new name. `in_flight` (<24h) is listed
  quietly, `overdue` (>=24h) is flagged, `stale` (>=7d) offers abandon
  inline. 24h because the gap is one human action against a 6m30s boot: an
  hour is normal and must not draw attention, or the flag stops meaning
  anything.
- **A banner that renders "none pending" because the query FAILED is the
  banner's own wrong-and-looks-right state.** `pendingBannerHtml` checks
  `ok !== true` **first** and draws an error that says *this is not the same
  as none being pending*; `/onboard/pending` answers `ok: false` rather than
  an empty array. Same correction as "all 9 clean" over ten devices and the
  agent panel's disabled read returning `[]`. Control: with the error branch
  removed, a failed query renders the empty string.
- **An empty allowlist must never mean "everyone".** `identify()` computed
  `peer_trusted = (not allowed) or (peer in allowed)`, so an unset
  `cf_access_trusted_peers` trusted **every** peer — a blank silently
  removing the layer that survives a firewall rule being edited later. It
  was masked because the other two Access values were also blank, so
  `is_configured()` refused first: **the dangerous kind of safe**, since
  restoring the team domain and AUD *without* the peer list would have
  turned verification on with the peer check off. `is_configured()` now
  requires all three, an unset value is a **named** refusal
  (`missing_access_values()`), and `peer_trusted` is `bool(allowed) and peer
  in allowed`. A test had pinned the fail-open as intended, with a docstring
  that said *"blank means not configured"* beside an assertion that the
  caller **is** identified — the third test in this project to pin a defect
  as correct.
- **There is no way to configure Cloudflare Access through the application.**
  No route, form or function writes `cf_access_*`; the only code that ever
  writes them is `migrate()` seeding blanks. The posture panel exists because
  those gates were *"visible only by reading JSON over SSH"* — and setting
  them still is. A posture you can see and cannot set.
- **`get_list_data_dir()` calls `os.makedirs()`, so resolving a path creates
  a list.** Tests must patch **`modules.config.LISTS_DIR`**, not only the
  function: a module that did `from modules.config import get_list_data_dir`
  at import time holds its own binding, while `LISTS_DIR` is read at call
  time by every caller. Ten such tests passed locally and errored elsewhere
  because `data/lists/probe/` already existed here — the conftest guard
  snapshots before and after, so **pre-existing residue makes the check
  vacuous**, exactly as a month-old `C:/TFTP-Root` did for
  `test_portability`. Deleting the residue reproduced all ten.
- **A pass count is not a run result.** "2,736 passing" was quoted from a
  tail reading `2736 passed` with no error line, while the same commit
  produced ten errors on another machine. State error counts explicitly.
- **Absent and unreadable are different facts, and collapsing them erased
  the settings file.** `load_user_settings()` caught `JSONDecodeError` and
  returned `{}`, so an unreadable file looked like a first run and the next
  write persisted the empty dict — taking `settings_schema_version` with it,
  which made the file read as v0 so the next panel GET seeded **107
  defaults**, materialising the Cloudflare Access config as blanks. It became
  reachable because `save_user_settings()` opened the real path with `"w"`
  (truncate in place), leaving a window in which the file is a fragment; two
  settings requests 10 ms apart is enough. **A read on defaults is
  survivable; a WRITE on defaults destroyed the file** — so the loader raises
  `SettingsUnreadable`, `set_user_setting()` propagates it,
  `get_user_setting()` catches it, the save is temp-then-`os.replace`, and
  the damaged file is preserved as `user_settings.json.corrupt-<ts>` at
  `0600`. **The failure is drawn on the posture panel above every gate row**,
  because if the file cannot be read each row shows its default and looks
  deliberate.
- **Five defensible mechanisms composed into an invisible failure.** Truncate
  in place → a read catches the fragment → `{}` returned as if empty → the
  next write persists it → the file reads as v0 → a GET seeds 107 defaults →
  and the peer check, fail-open on a blank list, stops protecting against
  replay. Nothing announced any step. It surfaced only because the onboarding
  wizard refused to create a device.
- **Severity, both halves.** The gates were real: exactly one path to a person
  identity exists, `is_configured()` is checked first, and
  `_actor_from_claims()` runs only on claims `jwt.decode()` verified — so
  reveal/approve/confirm/publish_remote were **never satisfiable by an HTTP
  header**. The exposure was **replay of a genuine assertion from any LAN
  host** while the peer list was blank, not forgery.
- **NetBox creation is phase 2, not phase 1.** A NetBox device record is a
  **claim that the device exists**, written into the source of truth about
  something nobody has seen — the claim `pending` was built not to make. The
  name-reservation argument does not hold: the manifest already reserves the
  name and `build_plan()` already checks NetBox for a collision, and two
  reservations in two stores is how they come to disagree. **Phase 1 now
  creates nothing external**, so a failed onboarding is a commit plus a
  staged credential, both removable without touching NetBox — which matters
  because the failure path is the one that has never worked. `STEPS` is
  three: credentials → commit → render, and 4C.3's rationale survives
  unchanged, now cheaper to hold.
- **`sync_list_to_netbox` is an IMPORTER, and onboarding had nothing to
  import.** Every object is built from the device's golden config by
  `_scan_device_from_golden`, and a device being onboarded has none by
  definition — so it landed in the sync's `failed` list and was skipped,
  while the region, site and list-level VRF, built **unconditionally before
  that loop**, were created. Measured on the live NetBox: **3 objects tagged
  `nmas-managed` and no device**, and the run reported *"Device onboarded."*
  `create_netbox_record()` runs after promotion, when a capture exists, and
  **defers rather than guessing** when one does not — calling the importer
  with nothing to import is what created scaffolding for a device that never
  followed.
- **`ok` meant "the sync ran", not "the devices landed".**
  `_sync_list_to_netbox_impl` returns `{"ok": True, …, "failed": [...]}` with
  every device in `failed`, and the caller checked only `ok`. Third instance
  of `success` meaning *no exception reached the top*, after the background
  agent's 27 runs and `bind_credentials_step`.
- **Two fields declared and never written, one of them on a review screen.**
  `netbox_objects` counted `netbox_plan`, a tuple the route never filled, so
  the review always read **0** — while three objects were being created.
  `netbox_id` was never mentioned in the onboarding path at all:
  `create_netbox_step` collected the created ids and `commit_step` never
  received them. Both are the `next_ts` shape; the review now states what
  phase 2 will do, and `netbox_id` is written from the created record.
- **Remove must never delete its own tag, and the rule was enforced only by
  omission.** `extras/tags` IS in the created-object record — NMAS creates
  the `nmas-managed` tag — and removal requires **tagged AND recorded**, so a
  Remove that deleted the tag would strip the marking from every object
  carrying it and make the whole fleet of NMAS-created objects permanently
  unremovable *and* indistinguishable from operator-owned ones. It was true
  because `_REMOVAL_ORDER` and `_PER_DEVICE_ORDER` are **allowlists** that do
  not mention it, and stated only in `nmas-netbox-census`'s prose. **A rule
  living in one file's docstring and another file's omission is a rule
  nothing would notice being broken** — now named at the site and pinned by
  `test_netbox_write_gate.py`, including a floor so two empty tuples cannot
  satisfy it and a check that the census's prose and the tuples still agree.
- **Abandon is offered on every pending device, not only at `stale`.** It was
  gated at seven days on the reasoning that a destructive action beside a
  five-minute-old row invites use. That is wrong in the direction that
  matters: **the operator who has just onboarded the wrong thing is the one
  who needs abandon**, and the window in which they are certain it was a
  mistake is minutes. Gating it left `curl` or waiting a week as the only
  recovery for a fresh mistake — the flow's own recovery path unreachable
  exactly when it is most useful. The confirm dialog is what stops a
  misclick; an age gate never was.
- **A renderer whose only callers are its own children is unreachable.**
  `loadOnboardPending` was called from exactly two places — the Verify and
  Abandon buttons **inside the banner it draws** — so the banner could only
  appear after using a control that only exists once it has appeared. The div
  sat in the DOM, empty, while the manifest held a pending device and the
  Template library listed it as bound. **The state `pending` was built to
  prevent**, with the banner's own design test (*"pending for ever and nobody
  notices"*) defeated before it ever ran. Not client-side suppression like
  the agent panel, and not two readers disagreeing — no caller at all.
  `test_onboard_phase2.py` executed `pendingBannerHtml` directly, which tests
  the render and **not the wiring**: the same seam as `/onboard/create`
  sending `body: '{}'`, and the fourth defect to live between two tests that
  each did their own job. Pinned now by a test asserting a caller outside the
  banner exists, shown failing with the entry point removed.
- **A READ may derive the active list; a WRITE may not.** `/onboard/pending`
  falls back to `get_current_list_name()` because a listing leaves nothing
  behind and "what is pending here" means the list the page is showing. The
  carried-never-derived rule exists because onboarding into the wrong list
  leaves a commit and a NetBox object — so the test that pins it is **scoped
  to the write path** (`_plan_args`, `_target_list`, `plan`, `create`) with a
  floor asserting those functions were found. A module-wide scan would have
  forced a read to carry a list the page does not always know.
- **A stale premise runs in both directions.** Two were caught in one
  session by believing something was **done** when it was not — the manifest
  identity (trusted because the function was called `adopt_identity`) and the
  Access values (trusted because they had been *given* in conversation). The
  counterpart is believing something is **unresolved** when the evidence has
  already resolved it: the Create blocker was restated twice after the
  operator had set the values and `identity/status` reported
  `access_configured: true`. The sharp form is that the refuting evidence had
  **already been used** — the NetBox diagnosis was derived from the run
  reporting *"Device onboarded"*, which presupposes Create passed its
  identity gate. A fact consumed for one conclusion and not propagated to
  another. **Before restating a blocker, ask what exists downstream of it**:
  "Create is blocked" is refuted by "a device exists that Create made", and
  that refutation needs no new measurement.
- **The pending banner's own actions dropped the list they had in hand.**
  `onboardVerify` and `onboardAbandon` read `#obList` — the **wizard's**
  select, which is empty until `openOnboardWizard()` populates it — so from
  the banner both sent `list_name: ''` and every action it offers was
  refused. `carried, never derived` failing in the direction the rule is
  **for**: `/onboard/pending` echoes the list it answered for, that response
  drew the row, and the value was dropped on the way to the call. Same shape
  as `loadOnboardPending` having no caller — the feature renders and nothing
  it offers works. Both now take `listName` from the row, and a test asserts
  the parameter exists so a fallback cannot make it work by accident once
  the wizard has been opened.
- **A refusal on a shared helper names the CALLER's operation.**
  `_target_list()` is used by plan, create, verify and abandon, and its
  message explained why *onboarding* carries its list — to an operator who
  had pressed Abandon. **A correct refusal describing a different action
  reads as a bug in the tool**, and sent the reader looking for a wizard they
  had not opened. Each caller now passes its own name and gets its own
  consequence clause (onboarding: what a wrong list *leaves behind*;
  abandon: what it would *remove*), pinned by an AST test that every call
  site supplies one — a route left on the default would give the onboarding
  message for something else, which is the defect itself.
- **Phase 1's entire product was rendered, validated and thrown away.**
  `render(plan)`'s return value was discarded, the create response carried no
  config, and the bootstrap artefact appeared only on the review screen
  **before** Create — so the one thing phase 1 exists to produce was gone the
  moment the toast cleared, and the only way back was abandon-and-re-create,
  which mints a new credential. **The credential was durable and the config
  carrying it was ephemeral**, leaving the recoverable half the one you
  cannot use. Two halves of one thing must not have different lifetimes.
  `bootstrap_artifact()` re-derives the config from committed intent plus the
  staged credential, so it exists **exactly while it is usable** — after
  rotation the device holds a different credential and producing the old file
  would hand over something that looks usable and is not. A test asserts the
  re-render is **byte-identical** to the original.
- **Not `intended/`, and the reason cuts both ways.** That directory is
  committed, so writing the bootstrap config there would put the one-time
  credential in git in the clear on a repo that may have a remote — and
  masking it would make the file useless for its one purpose, since a node
  cannot boot a masked password. Wrong unmasked and wrong masked, which is
  what makes re-derivation the answer rather than a preference.
  `GET /onboard/bootstrap/<hostname>` is a **reveal**: gated on a person and
  recorded in `data/reveal_audit.jsonl`, like `?reveal=1` on a golden, and a
  refusal returns no config at all because a masked bootstrap config is the
  one thing this artefact must never be.
- **Phase 2 connected with an empty password while the credential sat in the
  store.** The route took `password` from the request body and the banner
  sends only `{list_name}` — correctly, a browser must not carry a
  credential — so `""` reached Netmiko and the device refused it. Measured:
  Netmiko with the **staged** password returned
  `bp-onboard-c uptime is 7 minutes` on the first try, so the device, the
  store, `resolve()` and the transport were all correct. `verify_device()`
  now resolves when the caller supplies none, and reports
  `credential_source` — the source, never the value. **Which store matters**:
  the device override is keyed on the management IP, so `resolve()` finds it
  **without a `devices.csv` row**. A pending device has none by design, and
  resolving through `load_saved_devices()` would be the approval deadlock
  again — phase 2 needing the row only phase 2 writes. A test parses
  `verify_device` to assert it never reaches the inventory.
- **A diagnosis can be right about the evidence and wrong about the cause.**
  `answered_but_refused_the_credential` correctly ruled out the interface and
  the address — something answered SSH, so both were right, and the inference
  was sound. But the credential was *also* right and simply never reached the
  connection, which no cause covered, so the operator was sent to check a
  device with nothing wrong with it. Fourth cause added and offered **first**
  when the tool resolved nothing: *"the tool did not use the credential it
  holds"*, with `nmas-check-credential` as the command — the one cause the
  tool can answer about itself, and a control asserts it is **not** offered
  when a credential was in fact used.
- **`rotate()` is parameterised on WHERE it reads the device and records the
  result — never on its ordering**, which is the lockout defence. A device
  being onboarded has no `devices.csv` row (promotion writes it, last), so
  `preflight`'s `device_in_inventory` refused it and its
  `golden_config_present` looked for a file onboarding deliberately does not
  write until the RW community has been removed. **Both were proxies** — for
  *"we know this device's address"* and *"we know what it looks like"* — and
  a caller holding the device dict and the capture has better answers than
  the stores. `record="override"` writes the new credential to the **device
  override store, keyed on management IP**: the same place phase 1 put the
  bootstrap value, and the place `resolve()` reads without a CSV row.
- **What is atomic is "the device holds a new password" and "the tool has
  written it where it can read it".** Promotion is not part of that unit: it
  claims something different — *this device is finished and belongs in the
  inventory* — so it happens last and reads the credential back out of the
  override rather than being handed it. **No step passes a credential to
  another step, so none can pass an empty one**, which is the empty-CSV
  password bug fixed at its cause rather than its symptom.
- **A parameterisation can collapse to one behaviour and still pass**, so it
  is proven in both directions: a pending device records to the override and
  writes **no** CSV row, and an inventory device **still** writes one.
  Controls run both ways — forcing `override` for everyone fails one test,
  forcing `csv` for everyone fails a different one, and a single-direction
  suite would have passed one of the two.
- **Onboarding saves its golden after the RW community is removed, not
  before.** Capture → remove RW → rotate → save once. The golden is the
  approved record of what a device should look like, and writing one that
  contains a read-write community and then removing it makes the
  repository's **first** record of the device a state we deliberately do not
  want, preserved in history where a remote may publish it. The deploy path
  saves after verify because the device *changed*; onboarding saves after
  removal because the first record should be the one you would want
  restored — an analogy worth not drawing.
- **Phase 2 runs seven steps and `ok` means all of them**: verify → capture
  → rotate (+record) → remove RW → golden → NetBox → **promote**. Promotion
  is last for two independent reasons, which is why it is not a preference:
  4C.3's rule (the visible, durable change goes last among the fallible),
  and rotation forcing it anyway (the CSV row must carry the **rotated**
  credential). A partial run therefore leaves the device **pending** with a
  named reason and every step that did not run listed — *"the phase failed"*
  is not actionable, *"rotate failed and these four therefore did not run"*
  is. A control moves promotion earlier and the suite notices.
- **The first golden is a true record, and the order is what makes it one.**
  The capture is held **in memory** until the RW community has been removed
  and the credential rotated, then the device is **re-read** and saved once.
  A golden written earlier and corrected later leaves the state we
  deliberately do not want in history, where a remote may publish it — and
  re-reading rather than filtering matters too: a config with the RW lines
  stripped out is a claim about the device, not a record of it. Asserted on
  the **file**: no `RW`, no bootstrap credential, the RO community intact,
  one commit.
- **No step passes a credential to another step**, so none can pass an empty
  one. Each reads it from the device override — where phase 1 put it and
  where rotation replaces it — which is how the empty-CSV password is fixed
  at its cause. Promotion re-reads it last, so the row carries the rotated
  value.
- **Two of five negative controls did not fire on the first pass**, and both
  were findings. `ok` forced True passed the suite because every failure
  returned through `_stop`, which set `ok` itself — so the computation from
  the step rows was never load-bearing; `ok` is now decided in one place,
  from the rows, and asserted as a **relationship** (`ok` and the steps can
  never disagree) rather than as a value. The other was a **dud control, not
  a dud test**: the mutation left an earlier post-rotation read in scope and
  so reintroduced nothing. **A control that passes is either a missing test
  or a broken control, and telling which is the work.**
- **A device dict carries its credentials Fernet-encrypted, like a CSV
  row** — the shape the inventory adapter already established, "because
  callers decrypt at use". `run_phase_two` built one without them, so
  `preflight`'s `live_user_line_read` connected with `""` and the device
  refused it: rotation returned `failed_before_any_change` and phase 2 
  stopped with nothing half-done. **The deadlock reappearing at a check the
  parameterisation did not reach** — `device`, `capture` and `record`
  covered where the device comes from and where the credential is written,
  and not the credential the device dict itself carries. `live_user_line()`
  opens a session because the program depends on whether the account holds a
  `secret` or a `password` **on the device now**, not in a stored capture.
- **The state is not the reason.** `failed_before_any_change` is the safety
  property and covers **every** preflight refusal, while preflight runs a
  dozen named checks — so reporting the state alone is the background
  agent's *"failed at: {stage}"* with no reason attached: enough to know it
  stopped, not enough to act. `rotate()` now carries `preflight_checks`
  always, and phase 2 puts the failing check into the step row **and into
  the reason**, which is what the skipped steps quote — otherwise all four
  of them repeat a state that names nothing.
- **A teardown that cannot be measured has not passed.** The Stage 4C probe's
  clean run proved onboarding end to end — rotated credential in the CSV, a
  device-generated `secret 9`, no `snmp-server` line in the first golden,
  `nmas-check-credential … --expect` ACCEPTED — and left its **teardown
  unprovable**, because step 2's census baseline was never taken: creating
  the list through the GUI does not prompt for one, and the `--out` command
  was lost when the method moved to the UI path. **It is not recoverable
  after the fact**, which is the whole shape of it — a baseline taken now
  contains the probe's own objects, so the teardown would measure clean
  while leaving them behind, which is worse than having none. There is
  exactly one truthful moment and it is before the first step that can
  write, so the baseline is now **step 0a**, ahead of enabling NetBox
  writes, and step 12 checks for the file **before** the Remove rather than
  at the `--compare` when the objects are already gone.
  **`--compare` has three exit codes**: 0 pass, 1 differs, **2 UNPROVEN**. A
  missing baseline used to raise `FileNotFoundError` and exit 1 — the code
  for *"the teardown left objects behind"* — so the two most different
  outcomes the probe can have shared one. An empty baseline
  (`{"types": {}}`) is refused for the same reason in its own words: every
  comparison against it passes. Both floors are in the tests, because a
  `read_baseline()` that refused everything would satisfy every refusal test
  and leave the probe with no acceptance at all.
- **An action that changes state must leave the page showing the new state**
  ([docs/NSOT_STAGE7_GUI.md](docs/NSOT_STAGE7_GUI.md) §6b). Verify ran the
  whole of phase 2 and the device list still read `0 devices` until a manual
  refresh. **The tool knows and the screen does not**, and what that leaves
  the operator with is not a stale number but *not knowing whether the
  action worked* — so they press it again or go to the shell. Third instance
  in one session, each previously fixed as its own bug (the Remote card's
  last-push, the drift badge, now the device list), which is why it is a
  **rule for the redesign and not a fourth per-button fix**: every mutating
  action names what it **invalidates**, and the panels displaying that data
  re-fetch. The action names the *data*, not the panel — the panel that
  issued the call is usually not the one that is now wrong. Its own
  wrong-and-looks-right state is an invalidation declared and subscribed to
  by nothing (the `next_ts` shape), so the check is a set difference in both
  directions with a floor on each; and a **failed** re-fetch marks the panel
  stale with the time of the value it shows, because confidently wrong is
  worse than behind.
- **An IP address lookup is keyed on the INTERFACE, never on the address.**
  `_ensure_ip_address()` used to match `{"address": cidr}` narrowed by VRF
  and nothing else, and PATCH `assigned_object_id` when the hit sat
  elsewhere. Measured on the real NetBox 2026-09-24: **one object passed
  between six devices.** All five Lab 1 routers carry the identical
  `GigabitEthernet1 / vrf forwarding clab-mgmt / ip address 10.0.0.15`
  (vrnetlab's internal address, the same inside every container), so each
  import took the object from whoever held it — leaving five routers with an
  unaddressed management interface in NetBox for weeks, reported by nothing.
  **Two devices must be able to hold the same value and that is not a
  compromise**: the address genuinely is duplicated and each instance
  genuinely belongs to its device. One value, many interfaces, each its own
  object. VRF narrowing reads like the fix and never was — r3's address is
  in `clab-mgmt` and so is every other router's. **No interface is a
  refusal** (`UnscopedAddressLookup`), not a wider search, because the
  fallback *is* the defect. Addresses are compared as addresses, not text:
  `2001:DB8::2/64` and `2001:db8::2/64` are one address. The scope is the
  one `_upsert_device`'s `primary_ip4` read has always used, 160 lines
  below — **careful in the place where being wrong picked a wrong primary
  IP, absent from the place where being wrong moved another device's
  address.**
- **Provenance protects an OBJECT; a cascade travels a RELATIONSHIP, and
  nothing checked relationships.** The Stage 4C teardown deleted its eight
  objects — each tagged, each recorded, every check passing — and the
  database removed two more that NMAS did not create, because they were
  assigned to an interface it deleted. The gate was never wrong and its
  claim was false. **The preview simulated NMAS's own loop and asked NetBox
  nothing about the consequence**, so it listed eight while ten
  disappeared — the deploy path's rule (*what is confirmed is what
  happens*) broken in the one place it had never been stated.
  `modules/netbox_cascade.py` answers it: `CASCADES` is **measured from the
  changelog, not inferred from Django's `on_delete`**; a type absent from it
  is **unknown, never "takes nothing"**, with `UNMEASURED` listing the rest
  explicitly and a test checking both against `_REMOVAL_ORDER`; an empty
  tuple means *measured to take nothing*, a different claim from absence; a
  **failed** dependents query reports unproven rather than empty. The modal
  names each foreign object, and a clean proven preview renders **nothing at
  all** — a renderer that always warns trains the operator to click through.
- **git is versioned and NetBox is not, and that asymmetry is
  architectural.** `config_repo/` is committed, tagged, pushed and
  restorable to any point; NetBox is a live database this tool writes to
  with **no history, no baseline and no rollback**. Baselines are commits of
  `golden/*.cfg` — device configuration — and version nothing in NetBox.
  The 2026-09-24 damage was bounded **only because NetBox's contents are
  derivable from the golden configs**, which is a property of what happened
  to be damaged rather than a guarantee: anything hand-curated (a site
  description, a custom field, a tenant, a rack) has nothing to restore it
  from, and Phase 0's note that the reference NetBox *"was populated by hand
  from the design document"* says the risk existed from the start. **Plan
  item: what backs up NetBox.** Its own export plus
  `scripts/nmas-netbox-census`'s identity-per-type snapshot is most of one
  already, and would have made that night a **diff rather than an
  investigation**. The repair is therefore a golden-driven **re-import**,
  not a restore — and `scripts/nmas-netbox-repair-addresses` refuses to run
  while the lookup is still address-keyed, because a re-import with the old
  code reproduces the damage.
- **`load_saved_devices()` takes a PATH, not a list name**, and the fifth
  inferred-signature defect this stage came from forgetting it. A repair
  script passed the name, the lookup fell through to a CSV that is not
  there, `[]` came back, and the loop ran zero times — so *"Nothing to
  create"* was **honest and empty**. The tell was visible in the output:
  `default` and `Default` produced identical results, which means nothing
  downstream depended on the argument. Resolve through the registry
  (`get_device_lists()`), never `get_list_data_dir()`, which calls
  `os.makedirs()` — a typo would otherwise create a list.
  **The floor matters more than the defect**: a tool that examined nothing
  must refuse, naming the list and the path, because *"nothing to create,
  examined 0"* is a vacuous pass wearing a careful parenthetical, and for a
  **repair** script the wrong conclusion is *"the fleet is already
  correct"* — which ends the investigation. Check the argument **before**
  the integration, so a wrong name is not reported as a configuration
  problem.
- **NetBox enforces global IP uniqueness, so the emulator's addresses are
  not modelled at all.** Five identical `10.0.0.15/24` cannot be
  represented — measured: one created, four refused with *"Duplicate IP
  address found in global table"*. Three honest options (disable the
  uniqueness check / do not model them / accept NetBox is wrong about four
  interfaces), decided by the stage's own test: **would this make sense on
  a network the tool did not build.** No real device has that address, it
  is unreachable from anywhere, and NMAS reaches the fleet on a different
  range — importing it teaches NetBox about the emulator's plumbing rather
  than the network, and disabling the check would weaken the one constraint
  that made the duplication visible. `netbox_excluded_vrfs` (default
  `["clab-mgmt"]`) is a **setting, not a constant**, because another lab
  will name its management VRF something else. It is the **second
  deliberate exception** to "every new default reproduces prior behaviour",
  after `netbox_allow_writes`: the prior behaviour is not a behaviour
  anybody chose, it is an error NetBox returns. Read through
  `settings_schema.get_setting()` (which falls back to `DEFAULTS`), never
  `config.get_user_setting()` (which reads only the file, so a key no
  install has written excludes nothing, silently). **The interface is still
  modelled** — `vrf forwarding clab-mgmt` really is on the device; it is the
  addresses inside it that describe the emulator — and the skip is counted
  in `ipam_stats`, never silent.
- **Residue in an excluded scope is removed, not left**, because the
  exclusion makes it unreachable: nothing will ever update, correct or
  remove it again, and it claims one device has an address all five have —
  a half-true record that reads as complete, which is the state the drift
  checker and census exist to prevent. It also holds the globally-unique
  slot. `--remove-excluded` is dry-run first and **provenance still
  governs**; a device's `primary_ip4`/`primary_ip6` is a **blocker, not a
  warning**, because deleting it nulls the device's primary — the cascade
  map's first known edge, since that is a **modification rather than a
  deletion** and the map only answers "what will be deleted".
- **A definition below the `if __name__ == "__main__"` guard does not exist
  for the program.** `--remove-excluded` crashed with
  `NameError: name '_remove_excluded' is not defined` on its first run: the
  function was in the file, forty lines below the guard, so `main()`
  executed and returned before Python reached it. **Importing the file
  hides this entirely** — `SourceFileLoader(...).exec_module()` runs the
  whole module with `__name__` set to the module's name, the guard never
  fires, and a test calling the function would have passed. Same shape as
  `FakeNetBox` being unable to cascade: the harness's import cannot exhibit
  the failure, so the check has to be about the **file**, not the loaded
  module. `test_script_entry_points.py` walks every script in `scripts/`
  for definitions stranded below the guard and for called names nothing
  binds, with floors on the script count, the parsed statement count **and**
  the number of scripts that actually have a guard — without that last one
  the ordering check passes by finding no guards.
  Sixth instance in one session of *the test names or constructs its
  subject, so it cannot notice that the caller does not*, and the purest:
  not a wrong signature, not an unreachable branch, a call to something
  that is not there. `nmas-verify-runbook` is the same idea for routes.
- **A NetBox filter that matches nothing is indistinguishable from a
  resource that is absent.** `--remove-excluded` reported 0 eligible and 0
  skipped against a NetBox holding both objects. Measured: the query is
  **unfiltered**, and the match happens client-side on the nested
  `vrf.name` — which is **null**, because the repair created the address
  with no `vrf_id`. NetBox had already said so in the refusal an hour
  earlier: *"Duplicate IP address found in the **global table**"*. The
  deeper defect is that matching on NetBox's VRF field was a **second copy
  of the exclusion rule**: it is defined on the config
  (`vrf forwarding clab-mgmt`), so the import read it there and the clean-up
  read it elsewhere, and they disagreed. Both now go through one `walk()`,
  and the report names the **config VRF and the NetBox VRF separately**
  because the gap between them is the finding. Swept `netbox_client` for the
  same shape: **37 filtered reads, none filters a relation by name** —
  relations are `*_id` throughout and every `name=`/`slug=` is an object's
  own identity field, which is correct. Pinned with a floor and a positive
  anchor, since "no offenders" is also what a scan that could not run
  produces.
- **The inventory is the population for a RESTORE PREVIEW, not the ref.**
  `plan_restore()` iterated `devices_at(ref)`, so a device onboarded after
  the tag was **absent from the preview entirely** — not an error, not a
  skip, not named — and the summary read *"Restoring 9 of 9"* over a
  ten-device fleet. The drift checker's *"all 9 clean"* over ten, arriving
  again in a different reader. **The tag decision was right all along and
  disagreed with the preview**: `_baseline_earned()` reads the current
  inventory and refuses the tag naming the device, while the screen the
  operator confirms from said nothing — two readers of one question, and
  the correct one is not the one a person looks at. The denominator is now
  the inventory, absent devices are named with what will happen to them
  ("leave it exactly as it is"), and the ref is flagged `partial`.
  **Surveyed for the same shape**: three instances, two now fixed
  (`drift_check`, `plan_restore`) plus the **Baselines panel**, whose
  `device_count` came from `devices_at()` so an old baseline read *9* and a
  new one *10* with nothing calling the first partial — **a number is not a
  statement**. Correct as they stand: `_baseline_earned()`,
  `event_monitor` (iterates the inventory and looks the artefact up, the
  right way round), and the single-device `next(...)` lookups.
  `check_runner` / `pipeline_builder` build CI checks from goldens where the
  artefact genuinely is the population, but state no coverage. A fourth
  instance is recorded unfixed: `routes/templatize.py`'s fleet report drops
  a device with an unreadable golden through a bare `continue`.
- **Onboarding revokes its platform's template approval at CREATE, not at
  promotion, and takes the cohort's deploy path offline until the new device
  has a capture.** `devices_for_template()` computes the bound set from the
  **manifest, every time** — never a stored list, which would drift — and
  applies **no `pending` filter**, while `commit_step` writes the device
  into the manifest in phase 1. So a device that has never answered SSH is
  bound the moment Create succeeds, the fingerprint changes, and
  `is_approved()` goes false for every other device on that platform. It
  **cannot be cleared by re-approving**: `POST /templates/approve` collects
  bound devices with no captured config and returns **400 naming them**, and
  that refusal is load-bearing — skipping them would validate five devices
  and store a fingerprint covering six, the gate passing because its two
  halves counted different populations. Two exits only: complete phase 2, or
  abandon the device (`manifest.release()` reverts the bound set). Whether a
  never-reached device should bind at all is a real question left open
  deliberately — binding on the manifest entry is exactly what makes the
  gate notice its population changed, and a test pins the current behaviour
  so a later change is a decision rather than a discovery.
- **The edge caches HTML and not JSON, so fresh data beside a stale page is
  NOT a rendering defect.** The app is behind a Cloudflare tunnel; a page
  can be hours old while every endpoint it fetches is current, and **a
  browser hard-reload does not bypass it**. Measured 2026-09-24: the
  Baselines panel drew a bare *"9 device(s)"* while `/golden/baselines`
  returned `partial: true`, and `?x=1` rendered it correctly. **Ask the
  origin first** — `curl -s http://<nmas>:5000/ | grep -c '<helper>'` — which
  is one command and partitions the space: ≥1 means stop reading the code.
  **The misattribution is the finding, not the cache.** Four defects of the
  shape *"computed, carried to the browser, drawn nowhere"* had been found
  the same night, so by the fifth report the diagnosis preceded the
  measurement. **A pattern that has been right four times is exactly the one
  to distrust on the fifth**, because confidence is what stops you running
  the cheap discriminator. What recovered it was rendering the page through
  `app.test_client().get("/")` and finding the call site present — and the
  right response to a report contradicting a measurement is to say so, not
  to edit correct code. Scoped as [NSOT_STAGE7_GUI.md](docs/NSOT_STAGE7_GUI.md)
  §6c: the honest fix is `Cache-Control: no-cache` on the app's HTML at the
  origin, not a purge-per-deploy that depends on somebody remembering —
  and it is the **same work as §0b**, because while 647 KB of script sits
  inside the HTML, the page and the script cannot have the different cache
  policies each needs.
- **The app's HTML is never cacheable and its static assets are, and §0b is
  what lets the two differ.** `@app.after_request` in `app.py`: HTML gets
  `no-cache, must-revalidate` **plus an ETag** — measured, the page had no
  validator at all, so a bare `no-cache` is a full re-download and with one
  it is a **304 and zero bytes**; a **versioned** `/static/` URL gets
  `public, max-age=30d, immutable`; an **unversioned** one gets `no-cache`,
  because a long lifetime on an unversioned URL is the stale-page problem
  one layer down. `@app.url_defaults` puts the file mtime in every
  `url_for('static', ...)`, so a deploy changes the URL rather than needing
  a purge. **The static branch was nearly the hazard it was written to
  avoid**: `setdefault` lost to Flask's own `Cache-Control: no-cache` and
  measured as `no-cache` on a 27 KB extracted script — caught by measuring
  the response, not by reading the code. JSON gets `no-store`: measured, it
  carried no cache headers at all and the edge happened not to cache it —
  **that freshness was somebody else's default, not our policy**, and the
  argument for a header over a Cache Rule is not to depend on one.
- **§0b moved 275 KB of pure inline script into `static/js/gen/`.** Measured
  first: 280 KB of inline script carries no Jinja and 166 KB does, and the
  Jinja-bearing blocks cannot move verbatim. Document **656 KB → 378 KB**,
  fixed cost **647,383 → 365,417**. **The total first load did not shrink** —
  it is marginally larger — and that is the point: 285 KB is now cacheable
  and 378 KB is not, where before one figure had to be both. The number that
  improves on a second visit went from **zero to 43%**.
  It broke **166 tests across 23 files**, because the renderer tests read
  *the source the browser executes*. `tests/js_source.py` is the one answer:
  `read_shipped()` for template reads, `with_loaded_scripts()` for tests that
  already read the rendered page — **strictly more faithful than before**,
  since it models the program the browser assembles. The appended script must
  be wrapped in `<script>` (bare, `_scripts()` returned nothing and the
  failures read *"no block defines X"* — a scan finding nothing in the words
  of a real defect) and **one element per file**, or a test indexing into a
  block finds a construct from a different one.
- **Coverage inherited, not designed — a property that holds for the
  original population and silently does not for anything added afterwards.**
  Two instances now, in different subsystems, both found by **adding one
  member**. The drift check covered the nine reference devices only because
  their pre-migration files happened to sit in `golden_configs/`; and
  clab-sync makes nine devices reboot-safe while r6, onboarded into its own
  lab by a newer path, comes back on its bootstrap config — `password 0`, no
  rotated credential, NMAS locked out of a device it manages. Same cause
  each time: a capability wired to *a list that was current when it was
  built* rather than to the population as it is now, invisible because the
  population that has it is the only one anybody looks at.
  Scoped in [docs/R6_PERSISTENCE.md](docs/R6_PERSISTENCE.md), where reading
  the code found the **worse half**: `clab_configs_dir`, `clab_launch_patch`
  and `clab_host` describe **one** lab, and `verify_startup_applies()` — the
  guard keeping the rcn-lab1 redeploy ban lifted — resolves the patch path
  internally. r6 fails closed today only because its config path is wrong
  too; **fixing only the configs directory would make the guard read
  rcn-lab1's patch for a device r6's own patch boots, and pass.** The three
  must move together, which is one reason the answer is a **device → lab
  map** rather than a second target — the strongest being that
  `verify_startup_file()` and `verify_startup_applies()` are **already
  parameterised per call** and only their defaults are installation-wide.
- **A stated problem is a hypothesis with a symptom attached.** Three times
  in one night the stated problem was narrower than the real one, and each
  correction came from **reading the code, not from the symptom**: *"Remove
  deleted two objects it did not create"* (the **import** had moved them
  forty minutes earlier); *"the Access values are empty in the file"* (the
  settings file **erased itself**); *"clab-sync doesn't know about
  `~/labs/r6`"* (the path is the survivable half — `clab_launch_patch` is
  the dangerous one). The symptom is generated by the defect's **last**
  step, so it names where the failure surfaced rather than where it began.
  The third is the sharpest because the narrower fix **would have passed its
  own acceptance** and made the system worse: configs directory corrected,
  file appears, sync reports success — and the launch-patch guard now reads
  rcn-lab1's copy for a device booting r6's, turning a check that fails
  closed into one that passes wrongly. Extend *read the function, don't
  infer it* from signatures to problem statements.
- **The persistence chain fails closed on a half-deploy, for a reason it
  inherited rather than designed.** `persist()` runs `verify_startup_file`
  (presence) **before** `verify_startup_applies` (applicability) and returns
  on failure — an ordering written after Stage B for an unrelated reason.
  It matters because `verify_startup_applies()` on a **bootstrap** file
  returns `ok: True, applies: True`: a `password 0` form genuinely *does*
  apply behind vrnetlab's injected line, so the function answers its own
  question truthfully, and **its question is not "is this device reboot-safe
  with the credential NMAS holds"**. Presence stops the chain first, so the
  window never reaches it. Swap the two stages and a half-deployed r6 stops
  failing closed; `TestThePersistenceChainFailsClosedOnAHalfDeploy` pins the
  order, the short-circuit, and both verdicts on the same file.
- **`clab_labs` + `manifest.clab_lab` + `clab_target_for()`: one resolver,
  all four values together.** The four `clab_*` settings **are** the lab
  named `default`, and an absent `clab_lab` means that lab — so every device
  predating the map is unchanged with no edit. The paths do **not** inherit:
  a lab naming no `configs_dir` or no `launch_patch` is refused by
  `persist()` before the sync runs, because
  `verify_startup_applies(launch_patch="")` falls back to the *setting* and
  would read another lab's patch for a device booting its own — **the exact
  state the map exists to prevent, reachable through the map itself**. Found
  by a control that passed, which is the third time in one night that a
  passing control was a missing test rather than a broken one. The sync
  **asks** (`GET /clab/sync_targets`, `scripts/nmas-clab-targets`) and never
  copies: no cache, and an unreachable NMAS **refuses** rather than falling
  back to a directory, because a guess about where a config boots from
  writes one device's credentials into another lab.
- **A setting whose default is EMPTY loses silently, and
  `nmas-settings-diff` cannot find it.** `clab_host` was set on 2026-09-22 —
  `nmas-check-startup-applies` passes no `clab=` and reported *"APPLIES for
  all five routers"* naming a helper it found inside a remote file, which an
  empty setting cannot do — and it is empty now. Between those the settings
  file erased itself and a version-0 reseed wrote 107 defaults.
  `clab_configs_dir` and `clab_launch_patch` have plausible non-empty
  defaults and survived **looking correct**; `clab_host`,
  `clab_sync_script` and `yang_push_script` went blank leaving no trace.
  The diff script lists what **differs** from the default and a reset key
  **equals** it, so the loss is recoverable from knowledge rather than
  measurement — hence `settings_schema.GUARD_GATING_EMPTY_DEFAULTS`, written
  down rather than derived. **The erasure's blast radius was assessed as
  "the Cloudflare Access values" and was wider**, which is the fourth
  instance of a stated problem being narrower than the real one and the
  first where the narrow statement was mine.
  On Stage 2's acceptance: the **function** ran on the live host and was
  *calibrated* — the marker-rename control is what caught the fourth
  could-not-fail control — so the acceptance was met by a check that
  executed. The **stage** inside `persist()` is a separate claim and likely
  has never run, because reaching it needs a real rotation.
- **A default fallback is how a caller bypasses a resolver by omission.**
  `verify_startup_file`/`verify_startup_applies` fell back to
  `get_setting()` when the caller passed nothing, so
  `nmas-check-startup-applies` read the **default** lab's
  `labs/lab/configs/r6.cfg` while `clab_target_for()` returned
  `labs/r6/configs` — the map existed and one caller was not using it,
  seventh instance of that class and the first **inside the thing built to
  prevent it**. It failed closed only because the file was absent, *the same
  accident that made the configs-only fix look safe*. The fix is the
  **removal** of the fallback: `_resolve_target()` is the one path, and
  `_lab_of()` with an empty `list_name` **derives the active list** rather
  than assuming `default`, because the alternative is not a refusal but a
  wrong answer. Control: a device whose lab differs from the default reads
  its **own** paths, with a floor that a default-lab device still reads the
  default.
- **`check_removed_definitions.py` cannot catch a deleted TEST**, because it
  exits non-zero when a removed definition is still *called* and nothing
  calls a test. A truncating edit removed a whole test class and two others;
  what surfaced it was **two controls passing** that should not have. Run
  the controls after editing the test file, not only after editing the code.
- **A check can be truthful, correct, and answering a different question.**
  `nmas-check-startup-applies r6` reported **APPLIES** — *"the password form
  applies behind the injected line"* — while r6's startup file held the
  **bootstrap** credential. True: a `password 0` form does apply. What it
  meant was *"this device will come back on a credential NMAS does not
  hold"*, printed green. **Worse than the absent-file failure it replaced,
  because that one was loud.** Inside `persist()` it is safe only because
  presence runs first and stops the chain — an **accident of ordering**, and
  the second such composite tonight. **Fix the checker, not the function**:
  `verify_startup_applies()`'s question is legitimate, and nothing was
  asking presence on that path. The checker now asks both, presence first,
  and *"the file does not carry the credential NMAS holds"* outranks *"the
  form would apply"*.
  The presence question needed a source, because `$9$` carries a per-hash
  salt and **cannot be recomputed**: `verify_startup_carries_current()`
  compares the startup file's `username` line against **the device's own
  golden**, with `inconclusive` as a third state when there is no golden.
  **"Applies" is never printable without naming what applies** — the result
  carries the line, `_redact_value()` keeps the form and drops the value,
  and a losing presence still reports the applicability answer labelled as
  *a true statement about a different question*.
- **The clab sync map carries the PLATFORM DIALECT as a column, asserted at
  the boundary.** `oxidized-to-config.sh` split router from switch on a
  hardcoded `ROUTERS="r1 r2 r3 r4 r5"` with `*) kind=switch`, so r6 would
  have been sanitised **as a switch** — silently, because the list was
  current when it was written. Third *"coverage inherited, not designed"*,
  and the third found by adding one member. A **column, not a per-device
  ask**: the sync iterates the fleet once, so one answer is one consistent
  snapshot; a per-device ask is N chances to become unreachable **mid-run**
  and a partial map is worse than none. `assert_dialect()` is applied where
  the column is built, because a slug reaching a consumer keyed on the
  dialect is a lookup that misses — and there the default is a **device
  kind**. A device whose platform will not resolve is reported *incomplete*
  and **omitted from the text form**, so the sanitizer cannot receive a
  device it has no rules for; the shell's `*)` branch must **refuse**, not
  pick a kind. Columns are appended and never reordered.
- **A running config is not a startup config, and a golden IS a captured
  running config.** The clab sanitizer is not cleaning up Oxidized's
  quirks — it compensates for two facts about running configs in general:
  **`no shutdown` re-injection** (a running config records `shutdown` on a
  down interface and **nothing** on an up one, so any harvested config
  brings every addressed interface back admin-down — a full rebuild on
  2026-08-30) and **`crypto key generate rsa`** for switches. A golden has
  both blind spots identically, so sourcing startup files from goldens
  changes only *which capture gets sanitised*.
  **The real risk is freshness, not source**: Oxidized's copy may be newer
  than the approved one, so a redeploy can bake in a change nobody
  approved. That makes the work a **comparison, not a migration** — of
  **content**, with time as context, since Oxidized polls and is newer most
  of the time. `roundtrip.configs_equivalent()` is the comparator, the same
  one a restore baseline uses. It belongs in **both** places: a pre-write
  gate in the sanitizer (the last moment before an unapproved state becomes
  durable — with an explicit authorisation path, or it gets disabled like
  the drift checker) **and** a Monitoring signal (a report, whose value is
  discovering divergence while the person who caused it still remembers).
  Recorded with how I got it wrong: I reasoned from *"the source of truth
  should be the source"* without reading the script, one turn after saying I
  had not read it — **every piece of evidence from one artifact, the
  conclusion about another**, which is the Stage 2 tell verbatim.
- **A regenerated self-signed certificate is not drift, and it had been
  reported as drift.** Measured both ways before deciding either: r1–r5 run
  `restconf` with `ip http secure-server`, which **uses** the certificate,
  while the yang-push subscriptions ride NETCONF over SSH and need none, and
  nothing pins one — so it **must exist and need not survive**, making the
  sanitizer dropping it a *correct omission*. And `configs_equivalent()`
  **did** report it: a regenerated body plus a new chassis-derived
  `TP-self-signed-<digits>` name gave three `only_left` and three
  `only_right` lines with nothing configured by anyone. So every C8000v has
  carried a standing unexplained difference since the 2026-09-22 redeploy
  (`758d1f56`'s only changes were certificates) — **unnoticed because the
  drift checker has been off since 2026-08-30, switched off three minutes
  after a run that flagged all nine devices.** Re-enabling it would have
  flagged every C8000v for something correct, which is the condition that
  silenced it. `normalize.strip_self_signed_certs()` is **block-aware** (a
  chain is a stanza, and `_strip()` matches line prefixes) and **narrow**: a
  CA-signed trustpoint is configuration somebody chose and a change to it is
  real drift.
- **Before re-enabling something that was switched off, ask what it will say
  FIRST, and whether that is the same thing it said last time.** The drift
  checker was silenced on 2026-08-30 three minutes after flagging all nine
  devices. Turning it back on would have flagged every C8000v again — for a
  regenerated self-signed certificate, which is correct device behaviour.
  **A latent defect whose surfacing would have reproduced the condition that
  hid it**: silenced by noise, and the noise on return is of the same kind,
  so the likely outcome is a second silencing that is harder to undo than
  the first. The argument it makes: **fix a known-noisy check before turning
  a checker back on, not after.** Turn-it-on-and-triage is right for an
  *unknown* signal and wrong for a measured one — the certificate diff was
  measurable from the repository without touching a device, so shipping the
  noise would have spent the checker's credibility to learn something
  already known. **The 24 lost days were not a technical outage** — the code
  ran fine when re-enabled — they were a trust outage, and that is earned
  back rather than deployed. Same shape: a guard whose first action after
  repair is to refuse something legitimate, and an alarm whose first firing
  is a false positive of the kind that muted it.
- **A loop can run the right check fewer times than there are things to
  check, and every evaluation still be correct.** `ssh` reads stdin to EOF
  and forwards it, so inside `while read … done < <(list)` the first `ssh`
  in the body swallows the rest of the list: the copy loop ran **once**,
  nine of ten files were written, and the script printed *"Startup-configs
  updated."* and exited **0**. Every command returned 0 — there was nothing
  for error handling to catch. **A new variety**: everything catalogued
  before is one evaluation producing a wrong answer (a gate that silently
  opens, a vacuous assertion, a check answering a different question); this
  is the right answer, too few times, and **the body cannot see it** because
  it has no way to know it is the only iteration.
  **So the check lives outside the loop and comes from the population** —
  count the destinations independently and refuse unless as many succeeded,
  which is *"checked 7 of 9"* applied to iterations rather than devices.
  `ssh -n` on every call not fed by a pipe is the **cause** fixed; the count
  is the **class** caught — measured, with the count in place, reverting the
  `-n` fix refuses instead of passing silently. Then **read the destinations
  back** (`cmp -s` per device, naming every mismatch, before the staging
  directory is removed): the count says the loop ran enough times and says
  nothing about what arrived. **A transport that says "done" is evidence
  about the transport.**
  The same `ssh` also ate the terminal that `less` needed, so a full diff
  that *was* asked for never appeared — and that review is no longer
  opt-in: it is **shown**, and the only question left is whether to proceed.
  Nobody should be deciding at 2am whether to look at what they are about to
  overwrite.
- **A refusal naming two causes and distinguishing neither hides whichever
  one is true.** `|| echo "Not a git repo, or nothing to commit"` has been
  printing since August while meaning only the second: reproduced exactly —
  `git rev-parse` **succeeds**, `git add -A configs` stages nothing, and
  `git commit -q` fails, with `-q` suppressing the success message but not
  the failure explanation, which is where the untracked-backup listing comes
  from. **The per-lab change did not introduce it**: for that destination the
  command is byte-identical to the original with `$dir` for `$REMOTE_DIR`, so
  it has never worked — and 29 untracked backup directories are a repo that
  has received nothing from this script, which is exactly what a working
  commit would have made unnecessary.
- **A review step with moving parts is a review step that will not happen.**
  The full diff has now failed three times for three different reasons: an
  opt-in prompt defaulting to No, `ssh` eating the tty `less` needed, and the
  pager itself. The block is correct — extracted verbatim and run against a
  stub it prints fine — so what remains is `${PAGER:-less -R}` depending on
  `less` being installed, `$PAGER` being usable and `$LESS` not carrying
  `-F`. Three ways to lose the only review before an irreversible write,
  none producing an error anybody would notice. **Remove the dependency
  rather than hardening it**: write the diff to stdout and let the terminal's
  scrollback do its job.
- **Per-lab config repos, and the coverage check is what makes that safe.**
  `labs/lab` is a git repo whose `configs/` is tracked and byte-identical to
  HEAD — a **correct no-op** — while `labs/r6` is not a repo at all, and both
  were reported with the same sentence. Outcomes of different severity
  sharing a report, the census's missing-baseline exit code again: one is the
  system working, the other a gap in coverage. Now `committed` /
  `unchanged` / **`NOT VERSIONED`** / `commit FAILED`, with only the last two
  needing action and the run naming every unversioned destination plus the
  `git init` line to paste. One repo at `~/labs` would cover future labs
  automatically but needs `labs/lab`'s history moved up a level — a migration
  against the store whose value is being the record. Per-lab is one
  `git init` and no migration, and **its failure mode is exactly what
  happened**: somebody adds a lab and forgets. The map already knows every
  destination, so the tool reports the gap every run rather than relying on
  anyone to remember — the same move as *"checked 7 of 9"*.
- **Four failures of one section, four causes, none of them the logic.** The
  sync's full diff failed as an opt-in prompt defaulting to No, then because
  `ssh` consumed the tty `less` needed, and finally because **`less -R`
  itself swallowed the output** with `PAGER` and `LESS` unset — measured,
  `PAGER=cat` displayed it correctly. The loop, the `diff` and the
  comparison were right every time; everything that broke was **between the
  correct answer and the operator's eyes**. A different axis from the rest
  of the catalogue, which is all wrong answers: not *is the computation
  correct* but *does it survive the trip to the reader*. A pipeline into
  `$PAGER` is three dependencies — the binary, `$PAGER`, `$LESS` — in the one
  place with no fallback and no error path, guarding the one action that
  cannot be undone. **Put the moving parts where a failure is visible, and
  none where a failure is silence**: the diff now goes to stdout and the
  terminal's scrollback is a pager that cannot be misconfigured into showing
  nothing.
  Also the limit of a local reproduction: running the block under a **pty**
  showed `less` paging correctly *here* and therefore cleared nothing
  *there*. The discriminator that settled it was one word in front of the
  command and was available from the first report — **meet a silent failure
  with the cheapest question that halves the space, not with the most likely
  explanation**, which was wrong three times running.
- **A message that says what to do without saying how to do it right
  produces the wrong thing.** The *"NOT VERSIONED"* report printed
  `git init && git add -A && git commit`, and a lab directory holds
  containerlab runtime state beside the configs — so it committed
  `clab-r6/.tls/ca/ca.key`, **a private key**. The script's own add was
  already scoped (`git add -A "$(basename "$dir")"` stages `configs` and
  nothing else) and was fine: **the defect was in the advice, not the
  action**, and it shipped in the commit that fixed the reporting — written
  to close a coverage gap and opening a secrets one. The recipe is now an
  **allowlist** (`.gitignore` first, then named paths, never `-A` at the top
  of a lab directory), says why, and is verified against a directory with a
  planted key: the resulting repo tracks `.gitignore` and `configs/` only.
  **The output is the interface**, and an incomplete instruction is a defect
  in it — same class as a refusal naming two causes.
- **Doubting a correct report is what a run of false ones costs.** The
  *"unchanged - nothing to commit"* line was right and was read as a
  failure. The defence is to **make a true report say something a false one
  could not**: *"unchanged — the content did not move"* is a claim with a
  mechanism in it, while *"nothing to commit"* is a shrug, and a shrug is
  what you learn to distrust.
- **A redeploy replays OXIDIZED's copy, so freshness is a gate and not a
  report.** Whatever Oxidized last polled is what a containerlab device boots
  with next, approved or not. The finding is that the **content differs**;
  the timestamp only says which way — Oxidized newer is a change nobody
  approved, golden newer is a poll race and self-corrects. *"Newer"* alone
  fires constantly and means nothing, because Oxidized polls.
  `roundtrip.configs_equivalent()` is the comparator, the same one a restore
  baseline is measured with. **The gate is the sanitiser's pre-write check**
  (`POST /freshness/gate`, exit 0/1/2 from `nmas-oxidized-freshness`) and the
  **signal** is the same measurement read continuously — the gate discovers
  divergence when somebody is already preparing a redeploy; the signal
  discovers it while the person who caused it still remembers what they did.
- **The gate compares the RAW Oxidized config, never the sanitiser's
  output.** Both raw-Oxidized and a golden are *captured running configs* —
  records of the device. The sanitised file is **derived**: its own
  `! <host> - from Oxidized HEAD <sha>` header, a re-injected `no shutdown`
  in every addressed interface, an appended `crypto key generate rsa`. A
  gate pointed at it compares a transformation against its own input and
  reports **every sanitiser rule as drift**, permanently, on every device —
  so it would be switched off in a week. It also makes the answer
  independent of the sanitiser: changing a sanitising rule cannot make the
  gate fire.
- **The noise floor arrived inside the artefact chosen to avoid it, on the
  side nobody writes.** Measured twice, and the second correction is the
  one that matters. `strip_for_diff` keeps `! text` (it drops only bare
  `!`) — but NMAS's **own** `! Golden config — …` header is in
  `DIFF_PREFIXES` and was handled years ago. What is not handled is
  **Oxidized's** metadata header: the store this project does not write,
  and therefore the one nobody ever built a prefix list for.
  `normalize.strip_provenance_comments()` is a **fifth filter job**, not an
  addition to `strip_for_diff`, which feeds restore baselines and the drift
  diff where a capture's comments are part of what was captured.
- **A refusal that is correct for the WRONG REASON is invisible to every
  test that asserts the refusal.** The gate fetched Oxidized's timestamps
  only on the signal path, so on the gate path every differing device came
  back `inconclusive`: it could never say *"a change nobody approved"* and
  could never tell one from a poll race — **it would have refused every
  difference, benign races included, which is exactly how a gate gets
  switched off.** The hazard the design doc named, reintroduced by the
  implementation of the thing that warns about it. It blocked either way,
  so nothing asserting a refusal could see it; what saw it was a **negative
  control aimed at something else** — forcing an unknown timestamp to read
  as a poll race broke the route test asserting `409`, which had no
  business depending on a timestamp. Sibling of `failed_checks: []` beside
  `failed_before_any_change`: there the reason was **absent**, here it was
  **present and wrong**, which is worse because it sends the reader to fix
  a timestamp.
- **The way through a gate is per-divergence and recorded, never a switch.**
  `freshness.authorise()` takes a person, a reason and the **fingerprint of
  that one divergence** (list + device + the sorted differing lines), and
  expires in 24h. A per-device flag would let the *next* divergence through
  while the gate reported `authorised` — a wrong thing wearing a passing
  result. There is no `--force` and no settings toggle; a test **parses**
  the module to assert no such name exists. That test was itself a finding:
  its first version was a substring search and matched the module's own
  paragraph explaining why there is no switch — *the better the comment,
  the more likely it quotes the code it explains*, for the sixth time.
- **`poll_race` is not blocked, and is never silent.** The copy about to be
  written predates an approved change rather than carrying an unapproved
  one, and it self-corrects at the next poll. It is named, counted, and
  says what it costs ("a startup config that predates the approved
  change") — the difference between not blocking and not mentioning.
- **Resolving a path must not create a list, on a READ path too.**
  `freshness._authorisation_path()` is consulted for every device on the
  comparison path; written with `get_list_data_dir()` it called
  `os.makedirs()`, so *asking whether a divergence was authorised* brought
  a list into existence. The known rule in the place it is easiest to
  overlook — nothing about the call looks like a write.
- **A designed distinction can be discarded at the only place it is read.**
  `nmas-oxidized-freshness` defines 0 clean / 1 drifted / **2 could-not-ask**
  precisely to keep *"the fleet has drifted"* apart from *"I could not tell
  you whether it has"*. The sanitiser then did `elif [ $gate_rc -ne 0 ]` ->
  *"a change nobody approved"*, so every code the helper does not define read
  as drift. Measured: the helper was not on `PATH`, the shell returned
  **127**, and the run printed `command not found` followed by a finding
  about the devices. **The helper was right, was tested, and the caller threw
  it away one line later** — and the script's own header promised the
  opposite (*"If the NMAS cannot be asked, this STOPS, exactly as it does for
  the map"*). Now **only 1 is drifted, only 0 is clean, everything else is
  could-not-ask**, naming the code and the command, with **127 its own
  message** because a missing binary reported as unapproved drift sends the
  operator to look at their devices. Pinned by lifting the `case` block out
  of the shipped script and running it under bash for each code — a
  reimplementation would have passed at every stage. Fourth instance of two
  outcomes of different severity sharing a report, after the census's missing
  baseline, *"Not a git repo, or nothing to commit"*, and the gate's own
  `failed_checks: []`.
- **Two settings keys named one fact, and only one had a form.**
  `oxidized_url` (the integration client, Settings > Integrations) and
  `oxidized_rest_url` (read only by the persistence chain) were both the
  oxidized-web base URL — **both fetch `nodes.json` from it**.
  `_oxidized_rest_base()` is the one resolver and **refuses rather than
  adopting**: a set legacy key gets a refusal naming the move and carrying
  the value, because copying it across would be a settings write nobody asked
  for and the rename would then be invisible. The key stays in the schema
  (keys are never deleted) and is read by nothing, pinned by an AST scan with
  a floor on the surviving key. Same rule as `ListRef`, the `nmas-managed`
  slug and the device → lab map.
- **Two names for one string was the stated defect; two owners of one
  CONNECTION was the real one.** `OxidizedIntegration` carries the URL, HTTP
  basic auth and the TLS-verify toggle; the persistence chain speaks bare
  `urllib` and sends **none of the auth**. On an Oxidized with auth on,
  stages 2 and 3 get a 401 reported as a failed reload — *a credential error,
  during a credential rotation, about the wrong credential entirely.* Latent
  (both auth keys are empty), so it is a **named refusal** now rather than a
  401; userinfo in the URL is accepted, because urllib does send that. Found
  by reading the two call sites rather than the two key names — the stated
  problem narrower than the real one, again.
- **A guard whose enabling setting defaults to EMPTY is indistinguishable,
  from its output, from a guard that ran.** It refuses, which is safe; it
  says "not configured", which is true; and nothing downstream can tell that
  apart from a check that executed and passed. `nmas-settings-diff` cannot
  see any of them, because a reset key equals its default by construction.
  `oxidized_rest_url` was the fourth — same refusal shape as the other three,
  same empty default, outside the hand-written tuple for its whole life
  because adding it depended on somebody remembering.
  **So the list became a scan.**
  `settings_schema.discover_empty_default_guards()` reads every string
  constant matching `"<key> is not configured"` **at position 0** (a pattern
  that can appear in English needs an anchor — the module's own prose quotes
  it), where `DEFAULTS[key] == ""`, excluding docstrings. The contract is
  **one-directional**: everything discovered must be recorded, which is the
  direction that would have caught the fourth. It is a **lower bound** —
  `yang_push_script` names its key in an advisory rather than a refusal and
  stays recorded by hand; asserting the reverse would force it off the list
  to make a test pass. The scan's first run produced a finding of its own:
  **`oxidized_url` has the same property**, the guard having moved onto the
  surviving key. The deprecated key is **not** listed — it gates nothing now,
  and a list that keeps ghosts stops meaning what it says.
- **`oxidized_reload` is stage 2 of the seven-stage persistence chain and
  `fetch_confirmed` is stage 3**, so an empty URL fails closed at the two
  earliest fallible stages after the router.db write — **loudly**, unlike
  `clab_host`'s silence: the state is `ROTATED_UNVERIFIED` and `summarise()`
  names the stage and says not to redeploy. **Whether it has been failing
  since the 2026-09-23 erasure is not knowable from the repository**, and
  that is its own finding: `persist()` is reached only from
  `nmas-rotate-credential` and `nmas-persist-credential` (`rotate()` stops at
  `ROTATED_PENDING_PERSIST`, so onboarding's phase 2 never enters the chain),
  and **a rotation leaves no durable record** — no audit file, no run log,
  nothing in `data/`. Recorded as a gap rather than guessed at.
- **A deploy may ADD an account; it may never CHANGE one.**
  `deploy.assert_credentials_unchanged()` compares every credential-bearing
  line in the **truthful** render against the same line in the capture, byte
  for byte, keyed on the account. A type-9 secret carries a per-hash salt and
  **cannot be regenerated**, so committed intent naming a ref whose stored
  value is not byte-identical to what the device holds renders a *different*
  credential — and every other guard passes it: not a mask, printable ASCII,
  present in the intended config, not a dangerous command. The push succeeds,
  the device changes password, and the tool keeps the old one. **A lockout
  dressed as a configuration change**, which is the worst failure available
  on that path. Deliberate rotation has its own path, which rotates and
  records atomically, so nothing legitimate changes a credential through a
  deploy and this **refuses** rather than warns. Three cases and only one
  refuses: differing → refuse; absent from the render → not its business
  (merge-only never removes); new in the render → additive and cannot lock
  anyone out. Ordered **after** `assert_no_mask()` (the masked render differs
  from the capture by construction and would refuse everything) and **before**
  anything connects. The capture's lines ride **on the artifact**, never as a
  parameter — an optional argument is how a caller bypasses a guard by
  omission. The refusal names the **form** and never the value
  (`secret 9 <value>`): a guard against a credential must not become a second
  place the credential lives.
- **Merge-only is a capability limit on what can be PLANNED, not only on
  what gets sent.** Scoping r6's branch site, the cheap option turned on
  removing `passive-interface Vlan99` from s3 — and `assert_merge_only()`
  requires every pushed command to appear verbatim in the intended config, so
  a line the render omits and the device holds is a removal warning that
  sends nothing. **The option chosen to prove the tool can author
  configuration contained a change the tool cannot author.** The escape does
  not work either: authoring `no passive-interface Vlan99` passes the guard
  (provenance, correctly, not a grep for `no`), but `passive-interface` is a
  non-default setting, so negating it leaves the running config showing
  **neither** line — the intent would permanently name a line the device can
  never echo, every plan would re-propose it, and the device would be
  permanently drifted. A one-off refusal traded for a standing lie in the
  repository. **Ask what a proposed change REMOVES before costing it.**
- **A router with one link in the routing domain cannot be a transit path,
  and that is structural rather than a matter of cost.** Raised against
  putting r6 on the management segment: would s3 prefer a path through the
  device the tool just configured, on the wire the manager reaches every
  device over? No — for SPF to route through r6 it needs a second link, and
  its only other interface is in a VRF and therefore not in the process. No
  metric makes a leaf of the shortest-path tree a transit path. The
  distinction worth keeping is that an adjacency **does** reclassify the
  segment from stub to transit **in the LSDB**, which is inherent and
  unavoidable — and inert, because no packet changes path. *Transit in the
  database is not transit in the forwarding table.*
- **The fleet's own config was the answer, and reading it beat designing
  one.** s3 already carries `ip route 10.255.1.10 255.255.255.255
  10.255.0.10` with `redistribute static subnets` — a static /32 to an
  address on the management segment, redistributed into area 0, in production
  and working. So the fleet's existing answer to *"how does something on that
  segment get a routed /32"* is a static route, **not an adjacency**: one
  added line, `static_routes` is a modelled host_vars field, it round-trips,
  and it leaves the segment a stub network. The option that survived pricing
  was already deployed on the device being asked to change.
- **A plan is for failing at the plan.** The branch site's cheap option was
  chosen to prove the tool can **author** configuration, and it contained a
  change the tool **cannot author** — `passive-interface Vlan99` had to be
  removed and the deploy path is merge-only. Nothing about that was visible
  from the option's risk profile, which is what it was being argued on; it
  came out of asking *what does this change remove* and reading
  `assert_merge_only()`. **It would otherwise have surfaced at the preview,
  as a removal warning that sends nothing, with the other device's half
  already deployed** — a half-made change on the manager's only gateway,
  discovered by the tool refusing to finish. Instead it cost nothing. The
  entry is here rather than in the plan because the general form is the
  useful part: **an option's capability cost is not visible from its risk
  profile, and the two get argued as if they were one thing.**
- **s3-first would have made the acceptance pass vacuously**, which is a
  better argument for the ordering than the prerequisite it was proposed on.
  `ip route 10.255.1.16 255.255.255.255 10.255.0.32` installs as soon as its
  **next hop** resolves — and the next hop is a live connected address — so
  the destination need not exist. Deploy s3 first and r1 learns
  `10.255.1.16` as an E2 pointing at an address nothing answers: the
  acceptance *"r1 learns the route, nobody touched r1"* **satisfied by a
  route to nowhere**. Ordering rules justified by prerequisite are worth
  re-deriving from *what would a wrong order let a check claim* — the two
  answers differ, and only one of them is about the check being worth
  anything.
- **One device → one intent commit → one plan → one confirm → one deploy →
  one golden commit.** Two devices' changes in one plan couples them through
  the **confirm hash** (either half moving between plan and apply refuses the
  other's confirmed program) and through the **intent commit**, since
  `.nsot/rolled_back.json` keys on the device's current intent commit and
  "Revert intent" applies the inverse of *that commit's own diff* — so a
  shared commit means reverting one device's rollback reverts the other's
  change. The deploy boundary and the commit boundary have to be the same
  boundary.
- **`load_saved_devices()`'s no-argument default read a pre-lists constant,
  and the survey moved the fix.** `DEVICES_FILE` is `data/Devices.csv`, kept
  *"for backwards compatibility"* and written by nothing since lists existed,
  so a bare `load_saved_devices()` returned **zero rows** on the deployment —
  an honestly empty fleet, with every count downstream honestly zero. Second
  instance in a week, after `nmas-netbox-repair-addresses` passed a list
  **name** where a path was wanted and reported *"nothing to create"*.
  **Surveyed before fixing, and the survey changed the fix**: of **87** call
  sites, **none** passes no argument and **none** passes a name-shaped
  variable — so the in-repo callers were never the exposure and the trap is
  ad-hoc and script use, which is exactly where both instances happened. Of
  25 sites branching on emptiness, most are single-device lookups; of the
  whole-inventory ones, `drift_check` already names it (*"Inventory is empty
  — nothing to check"*, correct since 3.3b) and `event_monitor` returns
  silently. No argument now resolves the **active list** (`a read may derive
  it; a write may not`), and a string that is not a path at all raises
  `UnknownDeviceList`.
- **A refusal's discriminator has to be measured against the real callers,
  not reasoned about.** The first version refused any path naming no known
  list that did not exist — and broke **twelve** tests passing
  `<tmpdir>/devices.csv`, which is a correctly built path for a directory
  with no file yet. A list with no devices is a real state; onboarding writes
  that CSV only at promotion. The shape that is actually wrong is narrower:
  **no separator, no `.csv`, and not a file** — a bare name, which no
  legitimate caller produces. *Refusing inside a function with 87 call sites
  is only safe because none of them can reach the refusal*, and that is a
  measurement with a test and a floor, not a belief.
- **A scan's own test is a mention, not a caller.** The survey test pinning
  *"no call site passes a bare name"* failed on **its own sibling**, which
  passes `"Default"` precisely to exercise the refusal. Scoped to non-test
  files, with a floor and a positive anchor (`app.py` must appear). Seventh
  instance of a scan matching the thing written to explain it — the same
  distinction `check_removed_definitions.py` had to learn.
- **An assertion satisfied by a state it was not written for — three in one
  session, and the third was the subtlest.** Step 8 of the branch-site plan
  asserts *"`Vlan99` shows no OSPF neighbour"*, the exact property C′ was
  chosen to protect. Had OSPF been deployed on r6 by mistake (C's shape, not
  C′'s) **that assertion would still have passed**, because s3's `Vlan99` is
  passive and no adjacency forms either way. The visible symptom would have
  been the *other* check failing — r1 never learning `10.255.1.16` — which
  reads as a routing problem rather than as the wrong option deployed. **A
  guard on a property can be satisfied by the absence of the mechanism that
  would violate it**, and then the failure surfaces somewhere that names the
  wrong cause. Siblings this session: the freshness gate refusing correctly
  for the wrong reason, and s3-first satisfying *"r1 learns the route"* with
  a route to nowhere.
- **Hand-authored host_vars meet `StrictUndefined`, and the extraction path
  could never have revealed it.** `roundtrip.render()` uses
  `StrictUndefined`, and the interface macro reads ~30 keys; a parser always
  emits all of them, so every render the project has ever done was fed a
  complete dict. The **first hand-authored intent** — the branch site, which
  is the whole point of the stage — fails with
  `'dict object' has no attribute 'no_switchport'` on a key the author had no
  reason to write. Measured. Note what `StrictUndefined` is and is not buying
  here: it does **not** catch a typo'd key (`descripton` is simply never
  read, strict or not), so on the authoring path it only catches *missing*
  keys, which is the one thing a human author will always do. The extraction
  path and the authoring path have different requirements and only one has
  ever run. **Scoped, not built**: fill absent *known* interface keys with
  their falsy defaults before rendering — same output the parser would have
  produced for an absent construct, so nothing else moves.
- **A calibration note, the operator's: the survey's answer was the opposite
  of the guess.** `load_saved_devices()` was expected to have many
  no-argument callers, the ~79-call-site docstring making blast radius the
  point. Measured: **87 sites, zero no-argument, zero name-shaped** — so the
  in-repo callers were never the exposure and *a fix aimed at the callers
  would have been aimed at nothing*. Worth keeping beside the rule it
  illustrates: **survey before fixing, and let the survey move the fix**, not
  only confirm it. The same instinct that produced *"a pattern right four
  times is the one to distrust on the fifth"*.
- **A FIXTURE THAT CANNOT EXHIBIT THE CASE — a third variety.** Everything
  else catalogued here is a check that computed the wrong answer, ran too few
  times, or was read from the wrong place. This one is different: **the
  assertions were exact and the input could never reach them.**
  `test_each_group_is_unwound_one_exit_per_level` compares the whole command
  list and would have caught the duplicated stanza header outright — but
  `TestMergeCommands.RUNNING` contains every container the intended config
  mentions, so no header is ever in `to_add` and the duplicating branch is
  unreachable. **The natural fixture for a merge path has the parent present
  by construction**: you cannot show that a child is given its header unless
  the header already exists somewhere, and the obvious place to put it is the
  device. Two siblings: `FakeNetBox` had no foreign keys, so the harness could
  not cascade and the cascade *was* the defect; and `SourceFileLoader` runs a
  module with `__name__` set, so a definition stranded below
  `if __name__ == "__main__"` is reachable in the test and absent in the
  program. Each time the test was correct and **the world it tested in was too
  small**. The repair is never a stronger assertion — one added to the same
  fixture passes too — it is a fixture that can fail.
- **The duplicated stanza header, and what it was masking.**
  `_section_chains()` yields a line's ancestors *excluding itself*, so a
  header that is itself in `to_add` was appended once as its own line and
  again as its first child's ancestor chain. It fired for **every brand-new
  stanza** — interface, `router ospf`, `vlan`, `line` — and a two-level one
  also exited and re-entered its parent. Forward it is harmless, IOS being
  idempotent about re-entering a section, which is why nothing noticed; but
  it is a line nobody authored in the program whose whole claim is that it is
  exactly what was confirmed.
  **Removing it alone would have made things worse.** It was what made
  `merge_commands()`'s consistency assertion hold, and that assertion was
  phrased as *"the program's leaves are exactly the lines I set out to add"* —
  an equivalence that is **false whenever a container is itself new**, since
  `interface Loopback0` is both an added line and the ancestry of two others.
  Restated rather than relaxed, into the two directions it was really
  guarding: nothing intended was dropped, and **no leaf is configuration
  nobody asked for**.
- **Undoing a creation is removing it, and the duplicate was hiding that this
  was broken.** With the duplicate, `program_structure()` called the first
  copy a leaf, so the rollback for a new interface came out as
  `no interface Loopback0` **followed by** `interface Loopback0` and the child
  negations — **self-cancelling**, deleting the section and recreating it
  empty. Deduplicated it would have been coherent and still wrong: the child
  negations leave a stanza the device never had. The correct rollback is the
  **single negation**, children implied. Latent since the merge path was
  built, and visible only during a rollback — *the one moment nobody is
  placed to notice, because they are already dealing with a failed push.*
  `created_containers()` is the one producer, consumed by the rollback builder
  and the provenance guard, for the same reason `program_structure()` exists.
- **An optional argument that can only TIGHTEN is not the
  bypassed-by-omission shape.** `assert_rollback_provenance(rollback, pushed,
  pre_config=None)` permits the negation of a created section only when told
  the prior config; omitting it makes `no <section>` an orphan exactly as
  before. The rule earned earlier — *a default fallback is how a caller
  bypasses a resolver by omission* — is about an argument whose absence
  **loosens** a check. Absence that only strengthens is safe, and the
  distinction is worth stating or the rule gets applied as a ban.
- **A created container is undone only if it LANDED.** `landed_leaves()` sees
  leaves, so a container needed its own check — without it, a push rejected at
  its very first line would be "undone" by negating a section that was never
  created. The same derive-from-the-wrong-source error `landed` already exists
  to prevent, one level up from the leaves it covered.
- **An empty pre-change snapshot is not evidence the device had nothing.**
  Without that guard every section looks created and the repair becomes `no`
  on all of them — the worst push this tool could produce, generated by the
  path meant to fix a failure. Absent and empty, again.
- **`/deploy/plan` and `/deploy/apply` were never driven into each other.**
  Both halves were well covered and the *handshake* was true by inspection
  only: the capture hash the plan publishes is the one the apply recomputes.
  The only outcome a mismatch can produce is `skipped_drifted`, and the one
  thing that would notice a guard refusing everything is a deploy that
  completes — which, on a tool whose goldens have all been Save All captures,
  had not happened. Measured through the test client with the same capture on
  both calls: the handshake **works**. Now asserted, with a stale hash and an
  empty confirmation as floors.
- **The deploy wizard sends `{confirmations}` and nothing else**, so
  `/deploy/apply`'s `if expected is not None:` never fires from the UI and the
  command-fingerprint recompute — *"the list is recomputed at apply and
  compared against the confirmed fingerprint"*, the deploy path's central
  claim — **is not exercised by the only client that reaches it.** The restore
  path does send `command_hashes`, which is the positive anchor. Same family
  as `/onboard/create` sending `body: '{}'`: two halves each tested alone, the
  defect living only in the relationship.
- **Two sound hypotheses, both wrong, both reasoning where one command would
  have settled it.** `skipped_drifted` on r6: mine was *the golden changed on
  disk* (git said it had not); the operator's was *the guard never matches and
  has refused every deploy since it was written* (the seam test says it
  matches). Each followed correctly from the evidence to hand. **The
  discriminator was available throughout** — the skip entry carries
  `fresh_capture` verbatim, so hashing it partitions the space in one command.
  The rule already recorded for the Cloudflare cache — *meet a silent failure
  with the cheapest question that halves the space, not with the most likely
  explanation* — applies to a diagnosis that has now produced two confident
  wrong answers in a row.
- **A refusal must state what it COMPARED, not what it thinks caused the
  difference.** `skipped_drifted` said *"the device configuration changed
  since you confirmed the diff"* — one explanation among several, and the
  check establishes none of them. The capture can be byte-identical and the
  confirmed value simply not be its hash: a client sending the wrong field, a
  copied value carrying whitespace, a stale plan. Measured live — the
  capture, the plan's `capture_hash` and the file on disk were all
  `c29fa63582da8f57`, the guard refused, and the entry carried the **whole
  config** and **neither** of the two sixteen-character strings it had just
  compared. `fresh_hash != confirmed[device]` firing while
  `sha256(fresh_capture)[:16]` equals the plan's hash is arithmetic: the
  arriving confirmation was not that value. **Four rounds and three wrong
  hypotheses, each of which printing the two operands would have ended.** The
  `refused` entry a hundred lines above already carried `confirmed_hash` and
  `current_hash`; the skip now matches it. Third false message in one
  session, after *"a change nobody approved"* for a missing binary and *"Not
  a git repo, or nothing to commit"* for two different states — and the
  generalisation is the one worth keeping: **a guard knows the comparison it
  made and does not know why the operands differ, so it may only report the
  first.**
- **A diagnostic that dumps the artefact but not the comparison is the
  expensive shape.** The skip entry carried `fresh_capture` — an entire
  device configuration, several kilobytes, in a JSON response — and omitted
  the two short strings that were the actual question. Bulk is not evidence.
  (The config in that field is also an unredacted secret surface on an API
  response; noted, not yet addressed.)
- **The branch site landed, and it is the first configuration this tool
  AUTHORED** (2026-09-24, [docs/R6_BRANCH_SITE.md](docs/R6_BRANCH_SITE.md)).
  Intent written by hand into git, rendered by an approved template,
  previewed as an exact command list, confirmed by hash, sent merge-only,
  verified, captured back — two devices, two independent changes, separate
  rollback boundaries. Every golden in this repository before it was
  extracted from a config somebody wrote by hand.
  **The acceptance was a COMPARISON, not an expectation**: r1 learned
  `10.255.1.16/32` as *metric 20, type extern 2, from 10.255.1.23* — the same
  form in which it already carried `10.255.1.10/32`, measured before anything
  was deployed (step 0c). Same originator, same type, same metric, or it is a
  finding even if the route appears. Nobody touched r1. `s3: Vl99 … DR 0/0
  neighbours` asserts the property C′ was chosen for rather than assuming it.
  **What it does not prove**, stated up front and unchanged by the result: no
  removals (merge-only cannot, and option C died on exactly that), no
  multi-platform in one plan, and nothing about a value wrong at the source.
- **A path that has never carried anything fails on first use, and the suite
  cannot tell you that in advance.** Ten defects surfaced walking the deploy
  path end to end for the first time — a duplicated stanza header and a
  self-cancelling rollback, both latent since the merge path was built; three
  more uncovered by fixing those; a refusal naming neither operand; and three
  still open. **The suite was green throughout and its assertions were
  exact** — they were pointed at fixtures that could not reach the case. The
  ratio is the argument: *walk the path, do not only test it.* Same method
  that produced every serious finding in Stage 4C.
- **THE SUITE WAS GREEN THROUGHOUT AND ITS ASSERTIONS WERE EXACT — THEY WERE
  POINTED AT FIXTURES THAT COULD NOT REACH THE CASE.** Ten defects on one
  path, two latent since the merge path was built, three more surfaced by
  fixing those. That is the argument for **walking a path rather than only
  testing it**, and the branch site is the second stage where the same method
  produced every serious finding.
- **`StrictUndefined` catches the key a person was right to omit and never
  the one they got wrong.** The template reads ~30 interface keys and a
  parser emits all of them, so every render this project had ever done was
  fed a complete dict; the **first hand-authored intent** — the deliverable —
  met `UndefinedError: 'dict object' has no attribute 'no_switchport'` for a
  key that does nothing. *The shortest distance between "this tool lets you
  write configuration" and "this tool doesn't."* `INTERFACE_DEFAULTS` fills
  absent known keys, which **changes no output** (the macro's `{% if i.x %}`
  emits nothing for a falsy value either way) — pinned against the whole
  fleet, since approval, preview and deploy all render through it.
  **The opposite half is the silent one and is the failure a human actually
  has**: a *misspelled* key is never read, the line does not render, and
  nothing says a word. `unknown_interface_keys()` is refused at the authoring
  gate with a line number, like a YAML error, because the render cannot
  report it at all. Two halves of one problem, and before this only the wrong
  half spoke.
- **A failure on an authoring path names the ACTION, not the absence.**
  *"missing `no_switchport`"* sends a person hand-copying thirty lines they
  do not need; *"known interface keys default to falsy and omitted ones are
  filled automatically"* ends it. Same rule as a refusal naming the right
  cause — and the refusal for a misspelling has to say **"omitting a key is
  fine and needs no action; misspelling one does"**, or the reader treats
  both as the same class and copies the thirty lines anyway.
- **The declared key set and the emitted key set are asserted equal in BOTH
  directions.** A key the parsers emit and the declaration lacks makes a
  parser's own document unrenderable; a declared key nothing emits is a ghost
  that would **bless a misspelling as official**. One producer, two floors.
- **The deploy wizard never sent `command_hashes`, so the confirm-fingerprint
  recompute had never run from the UI.** `/deploy/apply` compares the
  recomputed program against the confirmed one *only* when that field is
  supplied, and the wizard sent `{confirmations}` from the day it was
  written — so the deploy path's central claim, *the list is recomputed at
  apply and refused if anything moved*, was not exercised by the only client
  that reaches it. A plan left open while the device changed, or two people
  planning the same device, applied against a program nobody had read.
  **The hashes are carried in the DOM, never re-fetched**, and that is
  designed in rather than added after: re-fetching the plan at confirm time
  would recompute against whatever is current and agree with itself — the
  comparison would pass **by construction**, which is precisely the failure a
  confirm hash exists to prevent. A test asserts `applyDeploy` contains no
  call to `/deploy/plan`.
- **Turning on a guard that was never running makes its first refusal look
  like a malfunction**, because the path used to succeed. So the message says
  what it **did** (*"Nothing was sent"*), what the rule is (*"what you confirm
  is what is sent, so a list you have not read is never deployed"*), and —
  the part that costs nothing — **which side moved**: the capture hash is
  already in hand, so comparing it separates *the device changed* from *the
  intent or template changed*. `"the device or intent changed"` makes the
  reader check both; naming the one that moved leaves one place to look.
  Reported as `moved: capture | intent_or_template` alongside all four
  operands.
- **A count merged in after the fact contradicted the rows beneath it.**
  Refusals are built **outside** `run_batch()` and folded into the report, and
  the fold extended `results` without re-deriving `total` or `by_outcome` —
  so one refusal rendered as **"0 device(s) accounted for. Every device in a
  batch appears here."** beside a row for that device. Not a stale number: a
  **false statement of coverage**, in the one sentence this project's batch
  reports use to promise it. `_merge_refusals()` re-derives all three, and the
  restore path — which had folded them the same way and carried the same
  disagreement — now goes through it, because two copies of a fold is how they
  come to differ. A test pins that exactly one hand-rolled merge remains, and
  it is inside the helper.
- **"Does the specific message reach the UI" is answered by executing the
  renderer, never by reading the payload.** *Computed, carried to the browser,
  drawn nowhere* has been the shape four times here, and a refusal built
  outside the batch and folded in afterwards is exactly the join where a row
  is carried and not drawn. The shipped `_renderDeployResult` is run in
  duktape against the real `/deploy/apply` payload — **and `_dEsc` is lifted
  with it rather than stubbed**, because a harness that supplies its own
  escaper tests a renderer whose every field passes through a function that
  was not shipped.
- **`vs_intent` read the WORKING TREE, so it was vacuous for anyone editing
  the file on disk** — which is how a person actually works. The edit and
  "what is committed" were the same bytes, so the diff built to answer *"what
  does my edit do"* was empty by construction, permanently. **The worse half**:
  `document_changed` was added precisely to disambiguate an empty `vs_intent`
  — its own comment says so — and read the **same working file**, so the
  disambiguator was fooled by the cause it existed to expose. *Two signals
  that look independent, sharing one source, so their agreement carries no
  information.* Both now read the blob at **HEAD** through
  `RefSource(..., allow=("host_vars/",))`, bounded at the call site rather
  than by the function being careful. What saved the branch site was
  `vs_device`, which compares against the **device** and no local editing can
  fool — worth noting which of the two an operator would have trusted if only
  one had been shown.
- **"Never committed" and "committed and unchanged" both rendered as an empty
  diff.** The absent-versus-empty distinction that erased the settings file,
  arriving in the editor. `committed_at_head()` returns a third state and the
  editor **names** it — a state the payload carries and the screen does not is
  the defect the state was added to prevent. **The same absence means opposite
  things**: mid-onboarding it is normal and expected; for a device that has
  been in the fleet for weeks it is a gap — nothing has ever declared what it
  should look like, so it is `bootstrap` and not deployable — and the note
  names the action (*Extract, review, Commit*) rather than only the absence.
- **`pending` is DERIVED, not stored**, and the first version of the note read
  `entry["pending"]` — a manifest key nothing writes. Every device answered
  "not pending" and the mid-onboarding branch was unreachable: a field
  declared and never written, the `next_ts` shape, caught by its own test.
  `manifest.pending_devices()` is the one reader of the real pair
  (`onboarded_at` set, `verified_at` None).
- **A fixture that writes intent and skips the commit is testing a device with
  NO committed intent.** Four editor tests broke on the change and were right
  to: `write_committed()` puts a file on disk, and *committed* now means in
  git. The same correction the fixture's **golden** had already needed, for
  the same reason, recorded in the same file — `save_golden()` was called
  there because `_captured_golden()` reads at HEAD. One store learned the
  lesson and its neighbour had not.
- **Two keys for one fact was the name; two owners of one CONNECTION was the
  thing.** Collapsing `oxidized_rest_url` into `oxidized_url` fixed the
  former. `OxidizedIntegration` carries the URL, HTTP basic auth, the
  TLS-verify toggle and a retry policy; the persistence chain spoke bare
  `urllib` and sent **none of the auth** — so on an Oxidized with auth on,
  stages 2 and 3 take a 401 and report it as a failed reload: *a credential
  error, during a credential rotation, about the wrong credential entirely.*
  `oxidized_client()` is now the one owner and the chain's three call sites go
  through it; a test parses the module's imports to assert no second transport
  returns. An explicit `rest=` override pins the base URL through a delegating
  wrapper rather than becoming a second transport, so the auth still rides
  along.
  **The deprecated key gates nothing**: `oxidized_url` is what is read, and
  the legacy key is consulted only to *name the move* when the surviving key
  is empty. A guard gated on a key nothing sets always refuses — the
  `clab_host` shape with the setting removed rather than blanked — and a test
  pins that an empty legacy key never refuses a configured client.
- **A test that passes alone and fails in the suite is telling you which
  binding it is missing.** `get_setting` is bound in **three** modules — the
  definition, `integrations/base` (for `url`), `integrations/oxidized` (for
  `oxidized_username`) — and patching only the definition reached the chain
  and not the client. Run alone, `integrations.base` was imported for the
  first time *during* the patch, so its `from … import get_setting` bound the
  **stub** and kept it; run after another file had imported it, it held the
  real function. The `LISTS_DIR` rule, in its nastiest form: not a wrong
  answer but an **order-dependent** one. Worse, the old tests patched
  `urllib.request.urlopen`, which after the change intercepted nothing — so
  they began making **real DNS calls** and passing or failing on name
  resolution, in a suite whose rule is that no test touches a live network.
  One `_patch_settings()` helper and one seam (`_oxidized_get`) now.
- **A control that passes is either a missing test or a broken control** —
  and this time it was broken. Replacing the client's cached session to drop
  the auth changed nothing, because `OxidizedIntegration.session()` re-applies
  `s.auth` on **every** call rather than at build time. Re-aimed at the real
  path — the wrapper returning a bare session — it fired. The mutation has to
  target the mechanism, not a thing that looks like it.
- **A staged plan names the variable it changes and assumes the SUBJECT holds
  still.** Phases 1/2/3 for r6 were each *"one further variable from phase
  1"*, which is only meaningful while the subject is where phase 1 left it.
  r6 moved: committed intent, a golden, a route `r1` learns, an acceptance
  with a measured baseline. **Changing one variable from a different starting
  point is a different experiment** — phase 2 on r6 would not be phase 2 (can
  a device be onboarded without a known address) but *re-addressing a managed
  device*, which nothing needs. When the subject moves, the stage is
  **re-decided rather than re-run**. Scoped against a throwaway in
  [docs/PHASE2_DHCP.md](docs/PHASE2_DHCP.md), the way the wizard itself was
  proven on `bp-onboard-c` and not on a fleet device.
- **A management-address change is the one class where the ROLLBACK TRAVELS
  OVER THE THING BEING CHANGED.** `ip address 10.255.0.32 …` →
  `ip address dhcp` is expressible (merge-only pushes the new form and IOS
  replaces the old), the push **succeeds**, and what fails afterwards is
  reachability — at which point `_capture_failure_state()` reads back over a
  fresh connection and `rollback_commands()` delivers the restore, **both
  over the address just given up**. Every guard on the path is satisfied and
  none of them helps: the confirm hash is right, the program is merge-only,
  the credential guard passes. *The tool does exactly what it was asked,
  correctly, and loses the device.* Recovery is the console and the
  break-glass record. On a throwaway the same failure costs a
  `containerlab destroy`.
- **"Address optional" would be the wrong shape for DHCP onboarding.**
  `render_bootstrap()` raises `ManagementAddressRequired` and `build_plan()`
  makes it blocking, because the failure it prevents is silent — the device
  boots, reports healthy, answers its console, and is onboardable by nothing.
  Phase 2 adds a **stated source** (`static` | `dhcp`), not an optional
  field: a checkbox turns a refusal into something a person switches off, and
  the two failures then look identical from the wizard.
- **THE REPAIR PATH TRAVELS OVER THE THING BEING CHANGED.** Its own class,
  and the first one where **every guard is correct and every guard is
  useless**. Changing a device's management address from static to DHCP is
  expressible (merge-only pushes `ip address dhcp` and IOS replaces the old
  form), the confirm hash is right, the program is merge-only, the credential
  guard passes — and **the push succeeds**. What fails afterwards is
  reachability, at which point `_capture_failure_state()` reads back over a
  **fresh connection** and `rollback_commands()` delivers the restore, both
  over the address just given up. *The tool does exactly what it was asked,
  correctly, and loses the device.*
  **The general form covers more than addressing**: any change to the path the
  tool reaches the device on — the management interface itself, the VTY
  configuration, the credential, the route to the manager. Several already
  have ad-hoc protection and now there is a reason why:
  `credential_rotation` verifies the new credential on the **held session**
  before trusting it and reverts on that same session; `assert_sendable()` and
  the ASCII rule exist because a truncated line on a console-replayed platform
  hangs a boot; `manager_interface_lines()` refuses to guess an interface. Each
  was solved once, locally. **Naming the class says what they have in common,
  and what a new feature in it has to supply: a repair route that does not
  depend on the thing being changed.** Where none exists — as here — the
  subject must be something whose loss costs a `containerlab destroy`.
- **A DHCP address is onboardable only if it is RESERVED, and that is a
  precondition rather than an acceptance item.** A dynamic lease is correct
  the day it is recorded and wrong at some renewal nothing is watching: the
  manifest, the CSV and NetBox would all agree with each other and all
  disagree with the device — **two stores disagreeing, with a clock
  attached**, and this tool has no watcher for it. `build_plan()` asks Kea and
  refuses at plan time. Three states, not two: `reserved`, `not_reserved`, and
  **`unknown`** for a Kea that could not be asked — which also refuses,
  because *a check that did not run has not passed* and an unchecked
  precondition is indistinguishable from a met one afterwards.
- **`dhcp` is a stated SOURCE, never an "address optional" flag.**
  `render_bootstrap()` refuses an empty address because the failure it
  prevents is silent — the device boots, reports healthy, answers its console,
  and is onboardable by nothing. A checkbox turns that refusal into something
  a person switches off, after which *"I meant DHCP"* and *"I forgot the
  address"* look identical from the wizard. `address_source` carries the
  choice, the refusals are untouched for `static`, and the generator takes an
  explicit sentinel rather than inferring intent from absence.
- **The review screen states a claim the tool CAN CHECK.** *"assigned by
  DHCP"* is a promise about what will happen later and nothing here would
  notice it failing; *"assigned by Kea reservation `<mac>` → `<address>`"* is
  a claim checked a moment ago, naming the address the device will actually
  get. When the check could not run the screen says **that** — *"could not be
  asked … unchecked, not confirmed"* — rather than falling back to the
  unfalsifiable sentence, and a test asserts no state renders as the bare
  promise.
- **Kea serves no subnet for the management segment, and the fix is
  reservations-only rather than moving the probe.** Measured: `10.10.10.0/24`
  and `10.10.20.0/24` with pools, nothing for `10.255.0.0/24`, and **zero
  reservations anywhere** — so `reservation_for()` answering `not_reserved`
  was the read path working against an empty set. A pool-less `subnet4`
  carrying only `reservations` **is legal in Kea** and is the right posture
  for a segment holding the NMAS, s3's SVI and r6, all static: an unreserved
  client gets silence rather than an address. Moving the probe to the pooled
  subnet instead would put it behind the relay — **phase 3's shape**, and a
  failure could then be the device or the relay, which is the one distinction
  phase 2 exists to make.
  Two things a new subnet does **not** imply and both must be checked:
  `interfaces-config` must list the segment's interface (Kea answers only
  where it listens, and selects the subnet from the **receiving interface's
  address**), and `authoritative` decides whether an unreserved client is
  ignored or actively **NAK'd** — the change turns silence into a refusal,
  and the two look nothing alike from the client.
- **A value the tool needs in advance must not be one only the device can
  tell you after booting without it.** A DHCP reservation is keyed on the
  MAC; a vrnetlab node's data-interface MAC is assigned at boot unless the
  topology pins it. Discovering it means boot → read → reserve → reboot, so
  the node's *first* boot is the unaddressed state the phase exists to
  prevent. containerlab's per-endpoint `mac:` pins it, and the reservation is
  written before the first boot. Same rule as the management interface:
  **chosen, never defaulted.**
- **`ok: True` wrapped around `{"result": 1}` is a lie at the ENVELOPE
  level.** `KeaIntegration.command()` returned success for any HTTP 200, so a
  Control Agent answering *"service value must be a list"* came back as a
  success with the failure nested inside — measured live on
  `command("config-reload", service="dhcp4")`, which reported ok and had not
  reloaded. Every caller that checks `result["ok"]` and stops there believed a
  refused command ran. **Fifth instance of `success` meaning *no exception
  reached the top***, after the background agent's 27 runs,
  `bind_credentials_step`, `_sync_list_to_netbox_impl` and the sanitiser's
  exit code. `ok` now means **Kea did the thing**, decided from Kea's own
  per-service result rather than the transport's.
  **And `result: 3` stays a success**: it means the command worked and
  returned nothing, which is what `lease4-get-all` says on a server with no
  leases. Treating it as a failure would print *"v4: unavailable"* for an
  empty pool — the absent-versus-empty error, arriving on the monitoring card
  via the fix for its neighbour. Both directions are pinned.
- **A caller-facing footgun only a hand-written call can reach.** The Control
  Agent requires `"service": ["dhcp4"]` and answers `result: 1` for a bare
  string; the settings default is already a list, so every code path was
  correct and the first hand-typed call was not. Coerced now — but the
  general point is that *the defaults being right is why nobody found it*,
  which is the same reason `load_saved_devices()`'s no-argument form survived
  87 correct call sites.
- **The app's only working path to apply a Kea config change is a restart, and
  the reason is credentials rather than capability.** `systemctl reload` is not
  applicable to the unit; `kea-shell … config-reload` answered **HTTP 403**,
  which is informative — the agent is reachable and rejecting on *auth*, not
  down — and `kea_username` / `kea_password` are unset. So the gap is a
  missing credential, not a missing feature. Worth knowing that a **restart
  re-reads leases from the lease file** rather than preserving them in memory:
  harmless on subnets nothing holds, and not a thing to discover during a
  change that matters.
- **A check pointed at one data FORMAT goes blind when a file uses the
  other, and produces no offenders doing it.**
  `c8000v_links_on_the_reserved_interface()` read link endpoints as
  ``"node:iface"`` strings. containerlab also has an **extended** link format
  — a list of mappings, and the only one with a per-endpoint ``mac:``, which
  phase 2's probe needs because a DHCP reservation is keyed on a MAC that must
  be known before the first boot. `str(endpoint).partition(":")` on a dict
  yields garbage, so a `Gi1` cabled that way was **not an offender and not an
  error — it was not seen.** Measured before changing it: the whole suite
  passed against a topology deliberately cabling a c8000v's reserved
  interface. *A gate that silently opens produces no offenders, which is
  exactly what a clean run looks like* — and the first file to use the newer
  format would have lost the protection with nothing saying so. `_link_endpoints()`
  understands both, with the blindness pinned as a test and a floor that the
  extended form on `Gi2` is still accepted.
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
