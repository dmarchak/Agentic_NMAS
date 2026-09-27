# CLAUDE.md — Agentic Network Management and Automation (NMAS)

## Project Overview

Flask-based web application for managing, automating, and monitoring Cisco IOS
network devices. Built by Dustin Marchak as a capstone/school project. The app is
a single-host management tool — not a multi-tenant SaaS — so there is no built-in
auth system.

**Stack:** Python 3.10+, Flask, Flask-SocketIO, Netmiko/Paramiko (SSH), Anthropic
Claude API (AI agent), vis.js (topology), Bootstrap 5, NetBox (source of
truth). Jenkins was removed in P.4 (docs/NSOT_CI.md).

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
- **[modules/pipeline.py](modules/pipeline.py)** (1,159) — 9-stage
  `PipelineRunner` (NetBox query → render → CI gate → snapshot → diff → deploy →
  snapshot → verify/rollback → audit). **Wired in**: `routes/deploy.py`
  `_deploy_one` runs it for every NSoT deploy AND every restore. (This line
  said "built but not wired into the UI" until 2026-09-26, long after Phase 3
  wired it: a document asserting a property the code no longer had.) Its
  `ci_gate` stage is a LOCAL dangerous-command check and its docstring says
  so (P.4 step 2). The Jenkins status read and the "syntax check" it used to
  claim were removed with Jenkins.
- **[modules/configure.py](modules/configure.py)** (1,093) — IOS config generator
  for 10 feature types (its Jenkins script and XML generators went in P.4)

### Collectors and checks
- **[modules/snmp_collector.py](modules/snmp_collector.py)** (763) — SNMP v1/v2c
  trap receiver + OID polling
- **[modules/netflow_collector.py](modules/netflow_collector.py)** (381)
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
  keyed on the template's closure hash (scheme 3, P.5)
- **[modules/nsot/deploy.py](modules/nsot/deploy.py)** — the deploy contract,
  merge-only diff, transport, circuit breaker, batch orchestration
- **[modules/nsot/convergence.py](modules/nsot/convergence.py)** — per-protocol
  settle windows
- **[modules/nsot/freshness.py](modules/nsot/freshness.py)** — is Oxidized's
  copy of a device the approved one; the gate, the signal, and the
  authorisation path
- **[modules/nsot/ztp.py](modules/nsot/ztp.py)** — P.6: the Kea reservation
  writer (a candidate tested with `kea-dhcp4 -t` before the live fragment is
  touched, then reload and read-back naming both operands) and D4's posture
  (no route or resolver option at any level; nothing on the segment answers
  broadcast DNS), at plan time and as a job-health row
- **[modules/nsot/ztp_responder.py](modules/nsot/ztp_responder.py)** — P.6:
  the read-only TFTP responder; serves a pending `ztp` device its config,
  rendered per request, only to its reserved address and only the file
  option 67 names, and only once the reveal row is written. Run by
  `scripts/nmas-ztp-responder` under `deploy/systemd/nmas-ztp-responder.socket`
- **[modules/integrations/](modules/integrations/)** — one client per external
  tool (NetBox, Prometheus, Grafana, Loki, Oxidized, Kea, topology service, NSoT
  git, S3). Phase 0 ships `test_connection()` only; Phase 5 adds read clients.
- **[modules/outbound.py](modules/outbound.py)** — config text on its way out:
  masked unless a person reveals it with `?reveal=1`, recorded. The golden
  routes and the backup download call it (C56): one pattern, not two
- **[modules/readonly_commands.py](modules/readonly_commands.py)** — C61:
  the ONE read-only command allowlist, whole command: verb, every output
  modifier after a `|`, no URL, no target-less ping, no line editing. The
  agent's tools use it; the lens, `/run_command` and `bulk_execute` adopt it
  in 7.3
- **[modules/nsot/receipts.py](modules/nsot/receipts.py)** — C60 (7.1): the
  deploy receipt, one masked row per device per batch, written by the deploy
  and restore apply paths after the golden commit: the program sent and its
  hash against the confirmed one, the actor, the checks that RAN (or why
  none did), rollback, and the commit. The follow-up window is not built,
  and each row says so
- **[modules/nsot/golden_state.py](modules/nsot/golden_state.py)** — E7:
  a baseline that is CONFIGURED AND WORKING. Every routing protocol a
  device's committed intent declares is judged up from real output (OSPF and
  OSPFv3 FULL or 2WAY, BGP established, RIP sources, RIPng next hops),
  failing closed with reasons; the baseline tag carries the claim and the
  snapshot, and `golden-state/<ts>` marks only a working fleet.
  `scripts/nmas-golden-state` takes one (dry-run by default)
- **[modules/invalidation.py](modules/invalidation.py)** — Stage 7.0: what
  each mutating route invalidates, in a finite vocabulary of data keys; the
  response carries it. Client: **[static/js/nmas_invalidation.js](static/js/nmas_invalidation.js)**
  (panels subscribe; a failed re-fetch marks the panel stale with a time)
- **[modules/preview_confirm.py](modules/preview_confirm.py)** — Stage 7.1:
  the preview-then-confirm contract. One builder for the six parts (what,
  what will NOT happen, program, operands, gates, confirm), refusing a part
  that is empty without saying so; per-screen adapters (`deploy_preview`).
  One renderer: **[static/js/nmas_preview_confirm.js](static/js/nmas_preview_confirm.js)**
  Its RESULT half (7.1 steps 2 and 3): `operation_result()` builds what
  happened FROM the receipt rows the apply wrote, the server computes the
  level (colour is only drawn, never decided in the browser), and
  `receipt_history()` serves the record back (`GET /deploy/receipts`, the
  Device page's Changes tab)
  Capture's client (7.1 step 4, Device page and Save All):
  **[static/js/nmas_capture.js](static/js/nmas_capture.js)**
- **[routes/](routes/)** — Flask blueprints: `settings_integrations.py`,
  `netbox_safety.py`, `inventory.py`, `golden.py`, `templatize.py`,
  `templates.py`, `deploy.py`, `freshness.py`, `devices_view.py` (the device
  list's regions, redrawn in place), `list_param.py` (a read of an unknown
  list refused, C51)

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
  approval_queue.json, config_repo/
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
- **Config push workflow:** the confirmed deploy path, and nothing else
  (P.3): plan, confirm by hash, then the pipeline snapshots, pushes
  merge-only, verifies and saves the golden. The older "push, then Jenkins
  CI, and a CI pass auto-approves" described a Jenkins nothing configured,
  and P.4 removed it.
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
- **No auto-continue** (P.3 step 8): the agent loops tool calls until the task completes, and a
  question it asks is for a person. It used to answer its own confirmation questions with a canned
  "yes, continue"; only the continuation of a reply the token limit cut off remains
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
  Drag-and-drop ordering is supposed to be stored in `source.json`, and it is NOT wired: `/reorder` refuses on a NetBox-sourced list and the source.json route has no caller (register D7).

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
- **`Actor-Verified:` says how the `Actor:` was established** (D10, P.3 step
  10): `access` (a request whose gate verified that same actor), `host-shell`
  (a CLI on the host) or `none`. It is written in ONE place, `repo.git()`,
  for any message carrying `Actor:`, so no writer has to remember it. It is
  decided by the code at the moment of the commit, never by date: the host
  ran old code after `c5a34c1` was pushed. A commit without it predates P.3,
  and its `Actor:` is a claim.
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
- **Approval is the TEMPLATE: its closure hash and who approved it (scheme 3,
  P.5, built 2026-09-26).** A claim about the template, never about a device:
  whether a device is reproduced faithfully is its own plan's
  `template_report`, gating in `blocking_reasons` per device with the lines
  named, so a device the template cannot reproduce is blocked ALONE instead
  of blocking every other device on its platform. Approving validates against
  the bound devices, needs **at least one** to round-trip, and records every
  device's result as evidence (validated, failed with the reason, not
  validated for want of a capture). The hash covers the **whole import
  closure** — a template is `base.j2` plus every macro file it imports, and
  `_common.j2` holds the routing, interface and service macros for both
  platforms, so editing any file revokes every approval whose closure
  contains it. The badge says what an approval **covers and what it does
  not** (`approval.COVERS` / `DOES_NOT_COVER`), because without the second
  sentence scheme 3 reads as weaker than scheme 2 to anyone who does not know
  why. History, each a correction: scheme 1 hashed each device's host_vars,
  so a deploy revoked its own approval; scheme 2 hashed the bound device set,
  so onboarding one device revoked every approval on its platform and one
  device the template could not reproduce blocked all the others (D11, D2).
  Records carry a `scheme`; an older one is never silently honoured, so the
  move to scheme 3 is an explicit re-approval. **Observed on the host
  2026-09-26:** after the deploy every deploy refused until a person
  re-approved both templates (`be60f59`, all nine devices round-tripping). By
  design, and the operator's reading of it is the rule: an older fingerprint
  answered a different question, so honouring it would be a gate that passes
  because nobody migrated it. The cost is one deliberate act; the alternative
  is a gate nobody can tell is stale.
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
  *not yet converged* distinctly from *failed*. **Until 2026-09-27 the
  routing check was real on 4 of 9 devices, measured against real output,
  and it is fixed.** It had read only the first protocol found (C62), a BGP
  count that matched no real row (C64), and the empty `"application"` table
  in place of RIP's (C65). So r3, r4, s1 and s2 compared 0 with 0, and the
  sentence here, "RIP is checked via the Routing Information Sources
  table", was false. Every protocol is compared now, BGP counts
  established sessions, RIP reads its own section, the route count is
  networks plus subnets (C66), the canary needs a non-loopback interface
  (C67), and progress means the count ROSE (C68). Acceptance from real
  captures: `tests/test_pipeline_reads_real_output.py`.
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

**Secrets are in more than one store** — see [docs/SECRETS.md](docs/SECRETS.md),
whose table is the claim. `user_settings.json` holds the ones
`secrets_store.SECRET_KEYS` covers (**a second store needs a second
mechanism**: a name in that tuple encrypts only what is in that file);
`.env` holds `ANTHROPIC_API_KEY` in **plaintext by design**, since
encrypting it would have the app decrypt its own key at startup using a key
in the same directory with the same mode. `data/jenkins_checks.json` is a
**retired** store (P.4): nothing reads it, and `nmas-check-secret-storage`
names it as a finding until it is deleted. The checker reports every store
by name and never by value. `scripts/nmas-settings-diff` lists
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

**Every read-modify-write of `user_settings.json` holds `config.settings_lock()`,
and every write uses its own temp file** (C20, 2026-09-25). Measured before
the fix: two threads each writing 150 keys left the file **unreadable** in 2 of
2 runs. Every writer used one temp name, so two documents landed in one inode,
and nothing serialised the read-modify-write. The unreadable-file guard then
refused every write: nothing was erased, and nothing could be saved. The lock
is an RLock in-process plus `flock` on `user_settings.json.lock` across
processes, because a CLI such as `nmas-retire` writes settings while the app
runs. After the fix: 300 of 300, threads and processes. An AST scan requires
the lock in any function that both loads and saves. **`write_settings()` is
not the only write path**: the general-settings POST in
`routes/settings_integrations.py` does its own read-modify-write. `migrate()`
RUNS on every GET of that panel, and WRITES only when the schema version is
behind or a secret is still plaintext. Both hold the lock now. The bypass is
recorded, not yet removed.
**Where it came from, and whether it fired.** The shared temp name arrived
in `4f8a0f1` (2026-09-23 18:26), the fix for that day's erasure. So it is
NOT the erasure's mechanism, which was truncate-in-place followed by a write
built on `{}`. It is a defect the fix introduced, and it was latent for two
days. On the live host on 2026-09-25 there were no `user_settings.json.corrupt-*`
copies and no stray temp files, so as far as anything durable shows, it never
fired there. A lost update leaves no trace, so that half cannot be ruled out.
The C7 frozen defaults come from the erasure's reseed, not from this.

**Encryption at rest here protects COPIES THAT TRAVEL, and nothing on the
live disk.** That is a property of the design, not a flaw in it. NMAS works
unattended: the drift schedule opens SSH sessions, redaction decrypts every
secret every 30 s to build its value table, the NetBox refresh resolves
credentials, and the freshness signal authenticates to Oxidized. So the key
has to be readable by the process with nobody present, and **whoever holds
the disk holds every secret**, whatever the store's format. What the
encryption buys is that a copy of `data/` without `key.key` (a backup, an
exported file, a leaked fragment) is worthless. The one design that keeps
the key off the disk supplies it when the service starts (a passphrase or a
TPM seal). **Declined 2026-09-25 with that reason**: it costs a person at
every reboot and buys nothing a deployment running unattended can use.

**A key copy and a copy of `data/` are one fix in two halves** (B5/B6).
Measured 2026-09-25: no vzdump job exists, so `key.key` was a single copy,
and so was everything it opens. Escrowing the key alone recovers nothing
after a disk loss, because the ciphertext dies with it. The key is escrowed
in the break-glass record (sealed by the passphrase, so the record still
does not DEPEND on the key), and **`nmas-breakglass verify --live` proves it
is the right key by decrypting the values actually stored on the host with
the ESCROWED key**. A copy of the wrong key looks exactly like a working one,
and a fingerprint match only says which file was copied. On the host, through
a sealed record: 45 of 45 opened, and a random key 0 of 45. `restore-key`
refuses to replace an existing file.

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

`config.py` no longer creates the TFTP root at import time. Call
`config.ensure_tftp_root()` at the point of use instead.

## Running the App

```bash
pip install -r requirements.txt
python app.py                      # opens http://127.0.0.1:5000
NMAS_HEADLESS=1 python app.py      # headless (no browser)
```

Settings (API key, integrations, TFTP, server bind) are all configurable
from the UI Settings panel — no restart needed except for bind host/port.

## Tests

```bash
scripts/nmas-test         # the suite, confined to loopback (C46); args go to pytest
scripts/nmas-test -n auto # in parallel: ONLY where pytest-xdist is installed
pytest                    # unconfined; says so in its header
pytest tests/test_netbox_write_gate.py -v
```

**Where each way runs** (2026-09-27): pytest-xdist 3.8.0 is installed on the
deployment host and in CI (to match CI), and is **not** installed on the
development laptop, where `-n auto` is refused as an unknown argument. So a
laptop run is serial and a host or CI run is parallel. They schedule tests
differently, which is the C43 class (a test depending on what ran before
it), and a result should say which machine it came from.

`pytest.ini` sets `pythonpath = .`, so both `pytest` and `python -m pytest` work
from the repo root. (Before Phase 0 only the latter did.)

| File | Covers |
|---|---|
| `test_pipeline.py` | 9-stage pipeline, stage ordering, CI gate |
| `test_netbox_write_gate.py` | write gate, dry run, provenance-based removal |
| `test_netbox_authz.py` | one-shot tokens, plan hashing, stale-plan abort |
| `test_netbox_preview_fidelity.py` | preview counts == executed counts; tag scope |
| `test_netbox_update_provenance.py` | an update records its BEFORE, confers no ownership, and a zero cannot pose as an assurance |
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
| `test_template_approval.py` | template library, bindings; scheme 3: the fingerprint is the template alone; one validated device approves and the rest are evidence; onboarding and removal do not revoke; a scheme-2 record is not honoured; the approve route records a device with no capture |
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
| `test_server_reads_nothing_the_form_cannot_send.py` | a field only curl can supply is a feature no operator has; both directions, named exemptions |
| `test_syslog_block.py` | P.1: the captured device rendering round-trips on both platforms; only the exact heartbeat applet is claimed; whole-or-absent at the AUTHORING path, a true partial block recorded at extraction |
| `test_heartbeat_rules.py` | per-DEVICE windows from measured arrivals: quiet on one miss, firing on two, for each measured device; provisional and inseparable named in the rule's own label; `--check` names a moved rate; the anchored origin-id match |
| `test_no_pattern_kill.py` | nothing written down stops a process by pattern; the tunnel helper closes the master it opened, and reports one that will not stop |
| `test_seed_status.py` | C6: current / stale / edited / edited_and_stale from two git histories; edited is not a defect; a RELATIVE path classifies the same (the live run that got it wrong) |
| `test_netbox_seeded_specs.py` | code-defined NetBox specs against NetBox with both operands; a failed definition write warns and reaches the sync's notes |
| `test_template_library_renders.py` | the shared `_common.j2` is listed with what editing it revokes; a withdrawal's reason is drawn; the save message says what happened |
| `test_bulk_intent.py` | P.1b: before-state compare-and-set per device with both operands; every refusal reason at once; the group count is the headline; one-shot hash; one commit; one device reverts alone from it |
| `test_retire.py` | the whole exit in one commit, history kept; the break-glass record must hold the CURRENT credential; what it will NOT do is stated; resumable; a failed commit restores the tree |
| `test_clab_sync_commit.py` | the sanitiser's commit block EXECUTED under bash: identity rides on every commit; a failed commit names git's reason and is not "not versioned"; helpers resolve beside the script under a systemd PATH |
| `test_job_health.py` | a failing timer is visible: the cause line and the streak; not-installed is never ok; could-not-ask is unknown; the Proxmox images: stale when the job STOPPED, failing names the task's own status, a multi-VM failure does not condemn the VM that succeeded, `will_not_fit` asks about the next run (1.2 × the largest image), never a percentage |
| `test_netbox_backup.py` | P.2: complete-or-absent, `0600` whatever the original, newest never pruned, status never 0 with a failed restore test or an unconfigured destination, `-i` on every stdin-fed `docker exec` |
| `test_breakglass.py` | the record is independent of the key it escrows; `verify --live` tests the ESCROWED key against the stored values (a right key on disk cannot pass a wrong copy); zero values is unproven; restore never replaces a key |
| `test_route_gates.py` | P.3: every mutating endpoint and terminal event declared, both directions with floors; all 87 gated endpoints answer 403 with no identity and no view runs (views replaced by sentinels); the table agrees with every in-route gate; refused before input; a person passes and a service does not; the actor is the verified one |
| `test_p3_cuts.py` | P.3 step 2: the eight direct-push routes answer 404 and nothing shipped names them; bulk config mode and chat playbook replay refused by name; the Configure forms send nothing |
| `test_harness_leaves_the_app_log_alone.py` | the suite never writes into the app log of the checkout it runs in (C26) |
| `test_p3_restore_is_guarded.py` | P.3 step 3 (D5): both Restore Golden Config buttons open the guarded preview at HEAD; 7.1: the preview is the shared component over REAL `RestoreTarget`s, every line sent drawn, residue under its section (C73), the restore's own gates and no template gate, the confirm covering exactly what the preview selects; C75: a restore that would rewrite a held credential is blocked at preview and apply, never printing the value |
| `test_merge_is_keyed_on_the_section.py` | C76: the merge program keyed on (section, line): every child line the fleet shares between two stanzas (44, real configs, one real line removed from one real stanza) is sent to its own stanza; two new stanzas needing one child each get it; the consistency assertion names a skipped line |
| `test_previews_mask_secrets.py` | C77: neither preview returns a planted secret (as residue or as a line the program adds), the line still drawn with its slot masked; the command hash is of the truthful program, and a masked plan driven into the apply is accepted while a wrong hash is refused; the apply responses are masked too (a planted community came back in `results[].commands`) |
| `test_terminal_privilege.py` | B13: the terminal sends the enable secret ONLY in answer to a password prompt, once; a device at `#` receives nothing; the page states the terminal is break-glass and unmasked by design |
| `test_p3_wizard_draws_the_program.py` | P.3 step 4 (D4): the wizard draws every line of the program, with one authorise box per dangerous line that re-plans the device; an authorised `shutdown` deploys end to end and a changed authorisation is refused; restore can authorise; C24's unbuildable device is named |
| `test_job_health.py` (C28 rows) | a guard-gating setting empty on this install is an `unset_guard` row naming what it gates; unreadable settings is one `unknown` row; the real scan covers the four the erasure blanked |
| `test_p3_secrets_write_only.py` | P.3 step 6 (B11): all 86 argument-free GETs swept for planted secrets; an empty secret field saves nothing; B16: no GET-only view sends request-supplied text to a device, and `/run_command` is a gated POST; C29: HTTP errors keep their status |
| `test_terminal_audit.py` | P.3 step 7: every open, failed open, close (page or dropped browser) and refusal of the terminal is a row with actor, device, peer and time; keystrokes never; 0600; a recorder failure is counted and never breaks the terminal |
| `test_p3_agent_tools.py` | P.3 step 8: 24 tools gone from the list and the dispatch; the `execute_*` tools refuse everything but read-only verbs, before connecting; no reply is auto-answered |
| `test_credential_single_copy.py` | P.3 step 11 (B14): an empty secret falls back to the password; rotation writes no copy; break-glass reports only a distinct enable secret; the dedupe script's dry run writes nothing, prints no value, and refuses an unparseable store |
| `test_rotation_reports_the_boot_file.py` | P.3 step 12 (B15): success is the checker's SAFE verdict from one shared function; a broken sync stage is named and never success; the message leads with the danger; every outcome is recorded (never a credential) and a not-SAFE rotation is a job-health row until a later persist reads SAFE; the sync script has one owner |
| `test_actor_verified_trailer.py` | P.3 step 10 (D10): `access` only for the actor the gate verified, `host-shell` for a CLI, `none` for the app's threads; written once at `repo.git()`; every git commit in the tree goes through it or is named; a gated route in the real app commits `access`; C81: approving a drift item commits its golden as the verified person with `Source: approval`, never `ai-agent`, and refuses with nobody behind it |
| `test_setting_not_applicable.py` | C31: a declaration carries who, when and why, and refuses a missing reason or a set key; job health tells `not_applicable` from `unset_guard`, and set-and-declared is a `contradiction`; a declared consumer leaves the rotation's list |
| `test_harness_isolation.py` | C32/C36/C42/C43: the suite runs on a temporary store, initialised once before any test (a file that errored alone passes alone); a write into the checkout's `data/` is attributed (the test process by an audit hook, a child by its sitecustomize) and a change no test made is the running app's only when `/proc` shows it; children get the test store; the store guard's controls hold on this machine's clock and on a simulated ext4 at 1 ms (the host) and 1 s; every module derives its data path from `config.DATA_DIR` (AST, floor); the session guard sees a change; importing `app` starts no thread, and `__main__` still starts them |
| `test_reads_write_nothing.py` | C33: the GET routes that write, pinned against an initialized store; the list must not grow and keeps no ghosts; a floor that the sweep can see a known writer |
| `test_route_reachability.py` | 7.0 (1): every (method, route) pair is reachable from a rendered page (both pages, with a device; `url_for` in template source counted), non-GUI with a consumer shown to reference it, or allowlisted with its group and home; per METHOD where a PATH mixes a read and a write (decided per path: `/drift/settings` is two rules); exact both ways, ceiling pinned at the measured 54; anchors each way. `tests/route_references.py` is the shared reader |
| `test_invalidation_map.py` | 7.0 (2): every mutating route (115, from `url_map`) declares the data it changes or `Nothing` with a reason, and an undeclared one is found (a throwaway app is the built-in control); the response carries the keys (header always, `invalidates` in a JSON body) and is otherwise unchanged; subscriptions both directions with floors, and a shrinking list of declared keys nobody subscribes to yet; the shipped client EXECUTED in duktape against a real response's header, a failed re-fetch marking the panel with the time of the value shown; the device list redrawn from the index's own templates (the 0-to-1 case) |
| `test_payload_is_rendered.py` | 7.0 (3): 27 declared renderers, each against a REAL response (`tests/payload_providers.py`; a refusal is a broken fixture, never a payload); forward, every carried key is read by a declared function (comments stripped, lookup tables counted); reverse, a depth-one read on the payload names a carried key; exemptions capped at ten; two shrinking lists (UNDRAWN 99, PHANTOM 18) compared exactly; since 7.1 a server-side adapter's reads count, because it decides what reaches the screen; anchors `commands`/`dangerous`/`attribution` (read by the adapter) and `preview`/`lines`/`from_this_edit` (drawn) on `/deploy/plan`, `list` on `/onboard/pending`, `commands` on the restore preview. Found C55 |
| `test_no_duplicate_dict_keys.py` | C90: no dict literal with constant keys repeats one, in the program, its scripts or its tests (4,530 scanned, floor 4,000); a duplicate keeps the later value silently, which dropped a `RENDERS` entry and would drop a gate from `route_gates.GATES` |
| `test_intent_match.py` | C89 (c)/(d), C91: r2's REAL config and committed intent parsed from it, through the deploy plan's own comparison: the capture matches, the host's exact break differs by `+1 -1` naming both lines, no intent is `unknown`; through `save_golden`, a departing capture is committed with `Intent-Match: no: r2 (+1 -1)` and earns no baseline, a matching one earns it, and a committing Save All with a device skipped earns none (C91) |
| `test_capture.py` | C82, C89 (7.1 step 4): capture on r2's REAL config with the host's exact break; the preview shows the diff against the golden and the departure from intent, sends no raw read, and writes nothing; apply records `Source: capture` as the verified person with `Intent-Match: no`, never green; a device that moved since the preview is refused and nothing commits; the whole fleet at intent earns the baseline and is green, with a departure it earns none and says why; Save All opens the fleet capture; the one-click route is gone |
| `test_results_are_drawn.py` | 7.1 step 1: every action gated confirm, approve or publish_remote (41, the gate table) shows its result where it can be read again, or is placed: drawn by the component with a reader (deploy, restore; evidence from source), pending (31, measured, only shrinks) or no GUI (tied to the reachability list); a toast is never enough for this population, and the bar is shown refusing; colour is part of the result (`FALSE_GREEN`: Save All, the NetBox sync card, onboarding Create) and the first XSS-shaped finding is pinned (`UNESCAPED`) |
| `test_preview_confirm.py` | 7.1 (and C73: residue drawn under its section, a nested case from r3's real config, from a real residue plan): the builder refuses each silent part (the six are a floor); the SHIPPED renderer draws them in order, draws a none sentence rather than omitting a part, names every gate state in words (`at_apply` and `not_reached` are never "pass"), refuses a preview whose parts differ from its own; the real `/deploy/plan` drawn; confirm names the person or states the refusal, on the button too; no retrofitted screen draws a preview part itself, and the pending retrofits only shrink |
| `test_concepts_are_taught.py` | 7.0 (4): the nine concepts, read from the plan's own table and matched both ways; 4 live screens executed in duktape against real payloads (marked, non-empty, visible, and saying the concept's words); 5 pending, each naming its step, no ghosts |
| `test_no_get_returns_a_stored_secret.py` | B11 over the SURVEYED population (C55): a distinct value planted in every store (settings, credentials, device passwords, the collector config, goldens, backups, the queue, chat histories, the config cache, variables, `.env`); EVERY GET swept with its arguments filled by the planted objects' names, anonymous and as a person; its secret classes matched to the checker's; four known leaks (C56) in a list that only shrinks |
| `test_no_agent_tool_leaks_a_stored_secret.py` | C56 (agent side): every agent tool driven through the REAL `run_chat()` loop and provider boundary with a fake client, every store planted; no tool result the provider would receive holds a planted value; `read_variables` reached the store and withholds; a tool made to leak in prose is found |
| `test_netbox_write_failures_are_counted.py` | C8: against a NetBox that REFUSES chosen writes, the failures reported equal the failures injected, each naming device and write; the report's `complete` is false with no failed device and one missing write; an AST rule that every handler guarding a write records, re-raises, retries or refuses (floor 18); a refused delete is `failed` with its reason, never a skip |
| `test_netbox_untagged.py` | C59: a create whose tag cannot be ensured is REFUSED and counted, and a tag failure is never cached; `nmas-netbox-untagged` finds recorded-but-untagged objects and unrecorded creates by NMAS's account (identified from a recorded object's own changelog entry), never lists another account's, and reads an unreadable object or changelog as UNPROVEN, not gone |
| `test_readonly_commands.py` | C61: `show running-config \| redirect tftp://…` refused, and every spelling of a writing modifier (`redirect`, `tee`, `append`, `format`, abbreviated, unspaced, chained, hidden in a regex); an unknown modifier refused; the filters still pass (the control); a URL, a target-less ping, `?` and control characters refused; `clear` and `debug` are not reads; one verb list in the program (AST, floor); the agent delegates; the ambiguity guard shown with a constructed filter |
| `test_pipeline_reads_real_output.py` | C62, C64-C67: the pipeline's readers against REAL captures (`tests/fixtures/operational/`, read-only from the live fleet, with a README): the error pattern, the interface up-count and the OSPF row count pinned as correct; each finding a STRICT expected failure from a real capture, read with `--runxfail` to confirm it fails on its own assertion and not a crash; every command the pipeline reads with passes the shared allowlist |
| `test_other_readers_real_output.py` | The sweep's second half: topology (OSPF detail, BGP, CDP, LLDP, interfaces) and NetBox's cable readers against real captures, each expectation counted from the capture independently of the parser; ONE BGP summary reader (AST, no third); the rotation reads exactly its account, never a prefix |
| `test_capture_output.py` | `nmas-capture-output`, the probe kept as a tool: a refused command connects to nothing; captures never land in the store; a capture redaction changed is marked and written `.masked.txt`; its names are the fixtures'; bytecode off before any import |
| `test_deploy_receipts.py` | C60: a row per device (sent, failed or refused), the program masked and hashed against the confirmed hash, the checks that ran by name (r6's "no routing protocol" a real state; verify not reached says why), what is not built stated; `0600`, append-only, absent vs unreadable; /deploy/apply writes it after the commit by the verified person; the commit's `Program-Hash:` trailer; a failed write loud and never raising; the restore path writes them too; the shipped result renderer, executed against the real apply payload (a deployed row AND a refusal), names each device's checks and the receipt |
| `test_golden_state.py` | E7: what intent declares, from the real fleet configs; the fleet judged WORKING on real captures (r3, r1, s1, s3); each failure named from a minimal edit of real output (a BGP peer down, an OSPF neighbour stuck, RIP hearing nobody, a declared protocol not running, one not measured, no committed intent); r6's "no routing protocol" a real state; one unread device makes the weak claim; the tag carries the claim and the snapshot, `golden-state/<ts>` only when working, an older baseline reads "configured"; the badge's renderer executed; the CLI dry-runs by default and carries the snapshot into the commit |
| `test_reads_create_no_list.py` | C51 (7.0): EVERY GET, with an unknown list name in each place a list arrives, creates no list (24 did; floors on the sweep); the refusal is a named 404 that says it is not an empty list; a real list by name and by slug still reads |
| `test_requirements_lock.py` | C37: every third-party import is mapped and pinned exactly in the host-generated lock; the lock names its producer; the C35 pair is not what CI installs |
| `test_network_guard.py` | C46: the test process refuses non-loopback connects and loopback is still the kernel's answer; a child with a bare env, a DNS name, ssh/curl/rsync and a remote git are each refused and recorded; a fake the test built runs and one outside pytest's tree does not; C46's exact case cannot reach the live NMAS; an attempt fails the test that made it, observed from a nested run; the confinement measurement's three answers; what a run reports is what a CHILD process gets; a required run that is not confined stops; the runner requires what it creates and never runs as root |
| `test_ci_workflow.py` | P.4 step 3: the workflow reads only this repository (no `repository:`, no secret, read-only token, token not persisted), installs the lock, never gates on coverage, cancels superseded runs; parsed values, not raw text |
| (overview) | **[docs/TESTING.md](docs/TESTING.md)**: what the suite checks, the 180 controls that run every time against the ~330 that ran once, and what it cannot reach |
| `test_nmas_deploy.py` | P.4 step 4: the host moves only to a commit CI passed, and success is decided by IDENTITY (MainPID changed, `/health` answers from it, target commit loaded), never by time; the no-run rule is read from a green commit and a workflow change is never ignorable; no run, could-not-ask, failed, cancelled and running all refuse with HEAD unmoved; a docs-only push passes on the workflow's own paths-ignore; `--offline` runs the suite here; every run is an audit row |
| `test_settings_concurrency.py` | C20: concurrent writers (threads AND processes) lose nothing; every read-modify-write holds `settings_lock()` (AST scan with a floor); the file order that failed now passes |
| `test_proxmox_integration.py` | B6: read-only, token-authenticated, exactly four paths read; the settings card carries every key the client reads |
| `test_configless_patch.py` | P.6 M1: the configless launch patch checked by AST against the REAL adopted script (a hash-pinned fixture): the base disk booted and the install overlay (which holds a saved startup config) removed, shown by EXECUTING the constructor on a fake root; no config ISO at run time, the console prompt marks the VM running, the watchdog never restarts it; refuses a missing or duplicated anchor, a re-patch, and a production lab's own file |
| `test_ztp_reservations.py` | P.6 step 1: against a fake Kea that re-reads the fragment only on reload (as M5 measured): written, unchanged, removed, absent; per-device refusals (MAC or address reserved, address leased, no subnet); D4 at every level and on the entry; a refused candidate never touches the live fragment; a failed reload restores it; a server that did not take the write is named with both operands; 0644 whatever the umask; the DNS condition (broadcast, `.invalid`, unknown is never silent); the job-health row finds the ZTP subnet from Kea's listening interface; the probe helper and the module agree on D4 |
| `test_ztp_responder.py` | P.6 step 2 (and M4's fix: a real dual-stack IPv6 listener with an IPv4 client, the peer normalised once for identity and reply): section 10's six controls (a reveal row per fetch with the hash and never the text; only the reserved address; only pending, decided per request; an abandoned device not served; nothing written by the module; a fresh render each time), the filename checked against option 67 naming both, served only once recorded, and the protocol over loopback: blocks, the empty final block, a retransmitted block, writes, netascii and malformed requests refused; the real manifest read and no list created |
| `test_ztp_onboarding.py` | P.6 step 3: a `ztp` plan carries the typed address as the reservation, never as a static address, renders `ip address dhcp`, and states a claim naming the reservation it WRITES and the server and file it serves; every reason the write would refuse blocks the plan, and a check that raised has not passed; phase 1 is credentials, commit, reserve, render, with the reservation last among the fallible and a failure there offering cleanup; a ztp run with no reserve step cannot complete; D4 re-checked at write time; re-render and lease discovery shared with dhcp; step 4: the pending row's stage derived from the reservation in Kea's running config, the lease and the responder's audit rows (another device's fetch does not count, a Kea that cannot be asked is unknown), carried only on ztp rows, a raised read carried as unknown, and the shipped banner drawing it; step 5: every dhcp-only comparison in onboard.py is a declared plan branch; C52: a ztp render uses `secret 0`, the plan and the re-render alike, and every other render keeps `password 0`; step 6: abandon removes the reservation FIRST (it was written last) and keeps the name while it remains, including a writer refusal; M4: `asked_not_served` (an unattributed request matched by its address, another device's row never), and the responder's job-health row (socket down, not installed, failing since its last start, unknown) |
| `test_c53_device_stage.py` | C53: one pure judgement (`startup_carries`) for the save path and the job; the exposed line is not carried, no startup config is not, no username line is unknown; the check never saves; the CLI chain saves the device FIRST and a failure stops it and is recorded, with `nmas-persist-native` as the advice; the job's file (0600), a raised check is unknown, the script's exit codes; job-health rows: one ok row naming the count, the device that would boot the wrong credential named, stale, unreadable, and a run that found NO devices is not ok |
| `test_kea_m5_helper.py` | P.6 M5: the helper reads subnet 255 from kea-dhcp4's control socket and adds the config-set control reservation, against a fake Kea socket; refuses a MAC or address already reserved; never calls config-write; D4's refusal of route and resolver options (3, 6, 33, 121) at global, shared-network, subnet and reservation level, with client classes reported as not ruled out |
| `test_bootstrap_config.py` | ASCII over the whole output, comments included; probe fixtures == generator |
| `tests/fixtures/configs/` | sanitized real configs; `fleet/` holds all nine |
| `tests/fake_netbox.py` | in-memory NetBox API (not a test module) |
| `test_settings_migration.py` | schema, secret encryption, forward migration |
| `test_integrations_base.py` | optional-integration behaviour, secret masking |
| `test_portability.py` | TFTP root, env overrides |
| `test_no_ip_literals.py` | fails if an IPv4 literal appears in the new packages |
| `test_golden_enumeration.py` | one enumerator; repo-only devices; commit time not mtime; legacy retirement condition |
| `test_drift_population.py` | the inventory is the population; every device in exactly one bucket |
| `test_drift_scheduling.py` | per-list state, merge-not-replace, what a silenced check records |
| `test_check_removed_definitions.py` | the checker tells a use from a mention |
| `test_drift_routes.py` | the routes exercised over HTTP; a crash is JSON+500, never 302; wrapper signatures |
| `test_security_posture.py` | effective value vs origin; Access values withheld; the recorded posture still holds |
| `test_settings_write_path.py` | positive seed declaration; unknown keys refused; ratify-never-change |
| `test_secret_file_modes.py` | every secret file created 0600 by its creator; the retired `jenkins_checks.json` is named while it exists |
| `test_no_jenkins.py` | P.4: no file imports a removed Jenkins module (floor and a positive anchor), the modules and the `Jenkinsfile` are gone, no route serves Jenkins |
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
| `test_onboard_phase_two.py` | the full phase: every step reported, promotion last, the first golden a true record; P.6 M4: `persist` saves on the device and reads the startup config back (the running line verbatim, the form never the value), no startup config or an old line is not persisted, an unpersisted device is never promoted, the outcome is a rotation record job health reads, and its advice is `nmas-persist-native`, never the containerlab chain |
| `test_settings_file_integrity.py` | absent vs unreadable; a write on defaults refused; the save is atomic |
| `tests/fixtures/fleet_scale.py` | a fleet of any size with a realistic state mix (not a test module) |

All HTTP and SSH is mocked; **no test touches a live network, enforced in three layers** (C46, `tests/network_guard.py`): the test process refuses any non-loopback connect; **every process a test starts is refused by construction** (a wrapper on `subprocess.Popen` rewrites each child's environment, an explicit one included: a `sitecustomize` for Python, refusing shims for `ssh`/`curl`/`rsync` and the rest, local-only git), and an attempt FAILS the test that made it, by name; and **`scripts/nmas-test` runs the suite in a loopback-only network namespace**. The host namespace was **declined** (the operator, 2026-09-26): a root-owned path the TEST HARNESS invokes, on the machine holding `key.key`, is the wrong trade after the harness reached the live NMAS. Every run's header states which it got (`network: CONFINED` / `NOT CONFINED`), measured by a route lookup, never assumed. CI requires it. Plain `pytest` still runs, and says it is not confined. The deployment host cannot make a namespace (AppArmor), so `--offline` there says `NOT CONFINED` in its verdict. One test's subprocess asked the live NMAS for its map on every host run until 2026-09-26. And **no test touches the live store**:
conftest points `NMAS_DATA_DIR` at a fresh temporary directory before anything imports, and fails the
run if the checkout's `data/` changed at all (C32). Importing `app` starts no service (C36).

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
- **A commit records what it deliberately did NOT do.** `nmas-retire` writes
  one `Not-Done:` trailer per non-action (NetBox kept, Oxidized still
  polling, startup frozen), and the operator named the pattern worth reusing
  (2026-09-26). Each of those is correct and reads as an omission unless it
  is named, so the history says *retained, not skipped*. Use it wherever a
  commit's scope is narrower than a reader would assume: an adoption that
  records and does not rotate, a bulk change that refused some devices (`Refused:`
  already does this).
- **Print a commit message file's first line before `git commit -F`.** A
  write that failed leaves the previous message in place, and the commit
  takes it: `df17b55` carries `ff6fc24`'s 7.1 subject over four design
  documents. It is left unrewritten (the operator: a clear record beats a
  rewritten history), with `a94e0ca` as the empty commit stating its real
  content. The same holds for any file an action reads after a write: the
  action does not know the write failed.
- **A method call on another object is not a use of a removed module-level
  function** (`check_removed_definitions.py`, P.3 step 11). Removing the
  Flask view `disconnect` was flagged by every Netmiko `conn.disconnect()` in
  the tree, and needed `--no-verify`. For a top-level definition, `X.name`
  now counts only when `X` is its own module: the dotted path, `import m as
  A`, `from pkg import m`, or a relative import. A check people routinely
  override stops being a check.
- **A name that SURVIVES elsewhere is mentioned by strings for the survivor**
  (`check_removed_definitions.py`, P.4 step 1c). Deleting
  `jenkins_runner.save_config` was flagged by `url_for('save_config')` and the
  gate table's `"save_config"` key, both about app.py's own view. When the
  name is still defined at top level in another file, only an import from the
  removed module counts. The same commit fixed its reading of a deleted file:
  `+++ /dev/null` had left the previous file's path in place, so four
  deleted modules' definitions were listed under `configure.py`. The hook
  refused the commit; the refusal was a checker defect, and fixing the checker
  was the answer, not `--no-verify`.
- **A filename is a mention** (`check_removed_definitions.py`, P.4 step 1).
  `"jenkins_results.json"` has the dotted shape of `mod.attr`, so removing the
  view `jenkins_results` was flagged by a module writing a file of that name.
  A module path never ends in a file extension.
- **A string is a use only when it is shaped like a reference**
  (`check_removed_definitions.py`, P.3 step 2): a name, a dotted path, or
  `pkg.mod:attr`. A URL path in a 404 test and a sentence in a prompt are
  mentions. So a test pinning a removed ROUTE names it by path, and a
  removal and its pin can land in one commit without `--no-verify`.

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
- **Every route and socket event that can change a device, a secret, or the
  tool's own gates requires a verified identity, enforced by ONE table**
  (P.3, register B12, closed 2026-09-26). `modules/route_gates.py` declares
  every mutating endpoint (121: 41 `configure`, 23 `approve`, 15 `confirm`,
  5 `publish_remote`, 3 `reveal`, 34 `not_device` with a reason) and the
  terminal's socket events (`break_glass`). One `before_request` hook enforces
  it **ahead of input validation**, and `socket_gated()` does the same for
  the socket. An undeclared endpoint is refused at run time. **A new
  mutating route must be declared there**, which is a code change, not a
  setting. Routes record `identity.request_actor()`, the VERIFIED person,
  never an actor from the request body.
  **Measured, not asserted:**
  - `test_route_gates.py` sends a request with no identity to all 87 gated
    endpoints, with every view replaced by a sentinel. All 87 answer 403
    `requires_identity`, and no sentinel runs. Its control lets `approve`
    through and names every approve route that then reaches its view.
  - On the host, at `9c4cf07`, 2026-09-26: an unauthenticated POST answers
    **403 `no_header`** on `/deploy/apply`, `/golden/restore/apply`,
    `/ai/approvals/<id>/approve`, `/templatize/bulk/apply` and
    `/onboard/create`. Before P.3 the first three answered 400, 400 and 404:
    they reached their own input checks, so no gate ran. The two unguarded
    golden replays (`/bulk_restore_golden_config`,
    `/device/<ip>/restore_golden_config`) answer **404**: removed.
  - An unauthenticated socket asking the live terminal for `192.0.2.1` got
    `[refused: … no Cf-Access-Jwt-Assertion header.]`. No shell was opened,
    and one `refused` row went to `data/terminal_audit.jsonl` (`0600`, peer
    `127.0.0.1`). That row is the measurement's own probe.
  - Through the tunnel, a real deploy's golden commit carries the operator's
    email where it used to say `pipeline`. Since step 10, every commit's
    `Actor-Verified:` says how its actor was established.
  **What this does not cover, stated so it is not read as covered:** a CLI on
  the host is authenticated by SSH to the host, not by this gate. Its commits
  say `host-shell`. The AI agent is a separate matter: it cannot change a
  device (P.3 step 8), and a real pre-execution authority gate for its tools
  is Stage 8.3. The network (the Access-protected tunnel, and port 5000
  firewalled from the LAN) is a second layer now, not the only one.
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
- **A label that looks like a path, asserted as a finding** (the
  operator's own pattern, named by the operator, 2026-09-25). `nmas-deploy`
  prints `health: HTTP 200`, which was read as the PATH `/health`, and the
  runbook was reported wrong on that basis without measuring. The runbook
  and the script both checked `/`, and `/health` answered 404. (Since 2026-09-26
  `/health` exists and reports the commit the RUNNING process loaded and its
  start time; `nmas-deploy` waits on both, because a process that never
  restarted answers `/` with 200 too.) C1 was the same
  shape: a report read as a claim it did not make. The reader-side half of
  *a tool's output is a claim*: before reporting a document wrong, run the
  command it names.
- **An exit code that cannot distinguish the case it is used to check
  proves nothing about it** (the operator's pattern, 2026-09-26; three
  instances, one session). **(1)** `rclone delete` exited 0 on a file it
  never touched (B9). **(2)** `rclone copy` with a key that could not read
  retried a 401 ten times, printed `There was nothing to transfer`, and
  exited 0: "no permission", "no such file" and "already up to date" share
  one exit code, and the 401 shows only at `-vv` (C22). **(3)** systemd
  reports `Result=success` for a unit that does not exist, which is why
  `job_health` says `not_installed` rather than trusting `Result`. The form
  that holds up: **confirm the RESULT** (the object in a listing at the
  right size, the row count, the file's hash) and treat the exit code as a
  hint. rclone's summary line carries the tell (`Listed 133`, `Transferred
  0`).
- **A TEST THAT PASSES IN BOTH CASES SHOWS NOTHING. Before accepting a
  result, ask what ELSE produces that output** (B9, 2026-09-26; the
  operator's wording). The clearest instance yet. To prove a "write-only"
  B2 key could not delete, the test ran `rclone delete <bucket>/b2probe.txt`:
  exit 0, file still listed, read as PROVEN. But rclone's single-file path
  check needs `readFiles`, so it treated the path as an empty directory and
  never touched the file. The file survived because nothing tried to delete
  it. The test that could fail pointed at the bucket with `--include`:
  `Deleted`, the listing empty, the version hidden. The key HID the file
  with `writeFiles` alone, and the lifecycle deletes hidden versions a day
  later, so **withholding `deleteFiles` bought nothing**. Two lessons:
  - *A capability's NAME is not its power.* `writeFiles` includes hiding,
    and hide plus the lifecycle is delete.
  - *An absence after an action proves the action only if the action was
    shown to happen.* This is the vacuous-pass rule, applied to a live test
    rather than a unit test.

  **Its inverse: a gate that always REFUSES is the same defect as one that
  always passes** (P.4 step 4, 2026-09-26; the operator's framing). `nmas-deploy
  --offline` tested a `git archive`, where `/health`'s test fails on every
  commit, so it could not pass at all. Its exit 3 on the red commit was
  recorded as the acceptance passing, because refusal was the expected
  answer. A test of a gate needs one case of each: the red commit must
  refuse, and a green one must pass and proceed. Otherwise the result cannot
  distinguish a working gate from a closed one. Found only by reading WHICH
  tests failed (2, where the probe accounts for 1).
- **A marker is not a match: count the line's exact FORM** (C21,
  2026-09-25). The heartbeat query matched any line containing
  `NMAS-HEARTBEAT`. Removing the applet's timer logs an error that NAMES the
  applet, and it was counted as a heartbeat by the measurement and by the
  alert rules. The alert case is the unsafe direction: a broken applet's own
  error reads as a sign of life. Same family as *a pattern that can appear
  in English needs an anchor*, with a device's log as the English.
- **A monitor's permissions can hide what it monitors, and the API says 200.**
  The Proxmox backup listing returned HTTP 200 with 0 items to an auditor
  token while two images sat on the storage, so the first `job_health` read
  `never` for VMs that had images. *A lookup that misses is a fact about the
  query*, and here the query included the caller's privileges. The fix was
  not more privilege (those can restore over a VM and delete backups) but a
  different source the auditor can read: the task logs. The row states which
  claim it makes.
- **A GATE KEYED ON SOMETHING THAT MOVES FOR REASONS UNRELATED TO WHAT IT
  PROTECTS** (the operator's name for it, 2026-09-26). Three instances, each
  one level up from the last:
  1. Phase 3c: gating deployability on INTENT DRIFT would have made every
     change block itself. It was caught in design.
  2. Approval scheme 1 hashed each device's host_vars, so the deploy it
     authorised revoked it.
  3. Scheme 2 keyed on the bound device set, so onboarding one device revoked
     every approval on its platform (D11; scheme 3 built in P.5).
  4. **`not_already_type_9`** (register B13, 2026-09-26) was written to stop
     re-running the password-to-type-9 MIGRATION. It also refused every
     ROTATION, because after Stage 2 every device holds `secret 9`: the path
     that retires an exposed credential worked once per device, ever. It was
     found while a live credential was exposed. **The lesson of the fourth: a
     gate like this does not merely block routine work, it can disable the
     remedy exactly when the remedy is needed.** Ask of every refusal on a
     recovery path: what else will this refuse, and when?

  **Each was found the same way: something was revoked, or refused, that
  nobody had changed.** Treat that symptom as the signature. Before keying a gate, ask
  what ELSE moves the key, and whether any of it is the gate's business.
- **SEND, READ, DECIDE. Never send a secret into a session on a timer**
  (register B13, 2026-09-26). The terminal sent `enable`, then the stored
  secret, then a newline, on fixed sleeps without reading. Every device was
  already privileged, so the secret arrived as a COMMAND and was echoed to a
  browser: 27 of s1's 32 password characters. Netmiko reads the prompt first
  everywhere else in this tool, and the one hand-rolled session did not.
  **The gate in front of it was correct, and the thing behind it had never
  been examined.** Gating a path is not reviewing it. A credential is sent
  only in answer to the prompt that asks for it.
- **A GATE TABLE KEYED ON HTTP METHOD MISSES A GET THAT CHANGES A DEVICE**
  (register B16). P.3 step 1 declared every POST, PUT and DELETE endpoint,
  and `/run_command/<ip>` ran any exec-mode command from a GET, outside the
  table and link-triggerable. The table's population was chosen by the
  PROTOCOL's idea of mutation, while the property is "reaches a device". Now a
  test asserts no GET-only view sends request-supplied text to a device. Ask
  of any population: is it defined by the property, or by something that
  usually coincides with it?
  **Members, one shape each time** (the operator's list, 2026-09-26):
  - the drift checker enumerated the legacy golden store, not the inventory
    (3.3);
  - the census compared identity (`id:display`), not assignment, so a moved
    address read as unchanged;
  - approval scheme 2 keyed on the bound device set, not the template (D11);
  - the restore preview iterated the ref, not the inventory (C23);
  - the gate table was keyed on the HTTP method, not on reaching a device
    (B16);
  - the agent's "read-only" command tools were defined as NOT CONFIG MODE,
    not as cannot change anything, and reload, delete, copy and clear all
    run in exec mode (P.3 step 8, the operator's sixth). The fix is an
    ALLOWLIST (show, ping, traceroute, dir, more), which a command added later
    cannot outgrow, where "not config mode" already had been.
  - **B11's "no GET returns a secret" planted secrets only in the stores it
    knew about** (C55, C56; the operator's, 2026-09-27, and the sharpest:
    the proxy was INSIDE the check built to catch this class of leak).
    Planted over a survey of every store, with arguments filled, it found
    five routes. The fix makes the population EXTERNAL to the test: its
    stores are tied to the storage checker's secret classes, and those
    classes to the files the CODE writes, so a new store fails until it is
    planted. The same move as drift enumerating the inventory rather than
    the golden store.

  - **"The tool knows every change by construction"** (8.7, the
    operator's own counter-argument, 2026-09-27): changes made
    THROUGH the tool standing in for changes made TO the device. A gate
    controls the tool's actions, not the network's. Measured writers
    outside the pipeline on the live fleet:
    - RESTCONF on five routers and NETCONF on six devices;
    - the console and any SSH client holding the credential;
    - the device itself (regenerated certificates);
    - a redeploy from a stale startup file.

    The constraint-shaped fix is to make the DEVICE the witness (it logs
    every change, whatever the path), not to enumerate the paths.

  **The corollary (the operator's): a proxy population is a dependency on
  something staying true that nobody is watching.** Every member was correct
  WHEN WRITTEN and stopped being correct when something else moved:
  - the golden store stopped being written to;
  - NetBox gained assignments;
  - onboarding started adding devices;
  - baselines aged past the inventory;
  - a GET route started changing a device.

  So the sixth is found by listing what each population ASSUMES stays true,
  and asking what would move it.
- **"Nothing to set" and "somebody forgot" must not share a state** (C31).
  `yang_push_script` was empty, and the script it named was dead. Setting the
  key would have made job health read `ok` for a script that cannot work (the
  operator's reason for clearing it). Leaving it empty read `unset_guard`,
  which claims somebody forgot. `settings_not_applicable` records the third
  answer, with who, when and why. It is written only on the host, and job
  health reads it as `not_applicable`, or as `contradiction` when the key is
  also set.
- **THE SUITE HAD NEVER RUN CLEAN ANYWHERE** (C32, 2026-09-26; the operator's
  framing). Run from a pristine checkout for the first time it gave 5 failed and
  19 errors, every one passing here: tests wrote into the live `data/`, a guard
  looked only for NEW paths so the residue hid them, and four tests passed by
  reading the checkout's own settings file. **"N passed" is a statement about the
  environment it ran in** until the environment is shown not to matter, and the
  only way to show that is a second, empty one. It is also how two product reads
  that wrote (`/deploy/plan`, the onboarding plan) were found, and ten GETs that
  write (C33).
- **Lock the versions of the machine that RUNS** (C37). The laptop, the pins and
  the host were three version sets; a test failing on one (C35) was invisible
  until a fourth ran it. `requirements.lock` is generated ON THE HOST, and CI
  installs it. Its first import measurement missed Flask itself, because apt
  packages carry metadata that cannot map an import to its distribution: a
  floor of known imports caught it.
- **The host's environment cannot be reproduced by pip alone** (C40). Ubuntu
  satisfies a constraint PyPI enforces (netmiko 4.3.0 with textfsm 1.1.2) and ships
  packages with no dependency metadata, so a rebuild from `requirements.txt`, or
  from the lock through a resolver, is an environment nothing has tested. Rebuild
  with apt on the same release, or `pip install --no-deps -r requirements.lock`
  (docs/DEPLOY_LINUX.md).
- **A guard must ATTRIBUTE a change, never assume who else is on the
  machine** (2026-09-26, the operator's host run). The session guard saw the
  checkout's `data/` change and blamed the suite, with a parenthetical saying
  the app does not run there. On the deployment host it does, from the same
  checkout, and its approval queue wrote mid-run. Now the test process's own
  writes are SEEN (an audit hook) and fail the test that made them; a child
  gets the test store by construction and its writes are recorded the same
  way; and a change no test made is judged against a MEASURED fact (an app
  process in `/proc` whose argv names this checkout's `app.py`). The app's
  writes are a note naming its pid, since the suite reads only its own
  store; an unexplained change still fails.
  **Its first run found a false positive in itself**: `shutil.rmtree`
  removes entries as `os.rmdir(name, dir_fd=...)`, and resolving that name
  against the cwd (the checkout root) reported a temp directory's own `data`
  subdirectory as the checkout's `data/`. A `dir_fd`-relative path is resolved
  through `/proc/self/fd`, and one that cannot be resolved is not attributed.
- **A row that is true must say why it is true.** `last success 1104 min ago`
  on a DAILY timer was read as a missed run, with nothing on the row to judge
  it by. Each timer row now states its window (`stale after 50 h`), and a
  fact about a group of rows (Proxmox TLS off) sits on those rows, not as a
  warning above the headline.
- **A timestamp with millisecond digits is not a millisecond measurement**
  (the operator, 2026-09-26). psutil's process start on Linux is
  `/proc/stat`'s boot time, whole seconds and truncated, plus ticks, so
  `/health` printed `.340Z` for a start systemd put 0.66 s LATER. Deciding
  "did it restart" by comparing such times would false-fail a real restart;
  decide it by IDENTITY (the PID changed, and the process answering is that PID)
  and keep times for the record, from a clock that has the resolution printed.
- **The rule that says a check was not needed must come from a commit the check
  PASSED.** Reading `paths-ignore` from the commit being judged would let a
  commit widen it to `**` and wave itself through; a change to the CI itself is
  never ignorable.
- **A control whose timing is tighter than the clock is a test of the clock**
  (C42, 2026-09-26). The store guard's positive control made a directory and
  wrote into it within microseconds. The host stamps ext4 times from a 1 ms
  tick, so the directory's mtime did not move and the control failed there,
  while passing in CI and on the laptop. The guard was sound (it compares a
  store changed BEFORE the session with its state after); the control did not
  model that. Backdate the "before" state, and run under a simulated coarse
  clock. **The simulation needs the filesystem as well as the clock**: on
  tmpfs a directory's SIZE grows with its entries and gave the create away,
  so the first simulation passed with the fix removed. `requirements.lock`
  pins Python and packages; nothing pins the kernel, and
  `scripts/nmas-env-facts` prints what differs, in CI and on the host.
- **`--offline` could not pass on ANY commit, and refused a red one looking
  correct** (P.4 step 4, 2026-09-26). It ran the suite from `git archive`,
  which has no `.git`, and `/health`'s test reads the loaded commit from git,
  so it failed on every commit since `/health` existed. The red-commit test
  read its exit 3 as a pass. Its unit tests replaced the suite run with a
  stub, so nothing had ever run the suite inside an archive. Found by running
  it on the host and reading WHICH tests failed (2, where the probe accounts
  for 1). It now tests a `--shared` clone checked out at the target, the shape
  of what is deployed, and a test asserts the suite sees a checkout whose HEAD
  is the target.
- **An instrument that re-executes its setup can move what it measures.**
  Measuring GET writers by importing `tests.conftest` for a helper executed conftest
  a second time and re-pointed `NMAS_DATA_DIR`, so the measurement watched an empty
  directory and reported ZERO writers: the vacuous result, produced by the
  instrument. The floor that caught it was a writer already known to exist.
- **A CHECK OF THE CODE IS NOT A CHECK OF THE INSTALL** (register C28).
  `discover_empty_default_guards()` derived, from the code, every setting
  whose emptiness silently switches off a guard, and only tests called it. So
  the class was KNOWN while the 2026-09-23 erasure left four of them empty on
  the host, and each was found by the failure it caused: the fourth during a
  credential exposure (B15). Knowing which settings are load-bearing is half
  the job; the other half is a job that asks whether they are set HERE.
  `job_health.settings_rows()` is that job.
- **A message whose first words are good news is read as good news** (the
  operator, B15). *"s1: ROTATED and committed"* opened a message whose point
  was that the boot file still held the old password. Lead with the state
  the reader must act on.
- **A negative control that fires by CRASHING proves nothing.** Twice on
  2026-09-26 a mutation broke the file (a syntax error), or sent execution
  down a branch that raised (`set(None)`), and the suite went red for that
  reason rather than because the property was gone. Read WHICH tests failed:
  a control is valid only when the failures are the tests aimed at the
  property, and a count far above that is the tell. Redo it as the smallest
  change that removes the property and leaves the code running.
- **Restore a control's mutation from a COPY of the file, never from
  git.** A control harness ran `git checkout -- <file>` after each mutation,
  and the files held the step's own uncommitted work: all five reverted to
  HEAD (P.3 step 10, 2026-09-26). The work was recovered from the session
  transcript, which showed nothing else had touched those files since the
  last commit. `cp` to scratch before the mutation, `cp` back after it. `git
  checkout` is a restore only when the file's committed state IS the state
  you want.
- **A dangerous line and its authorisation are STRIPPED strings; the program
  keeps its indentation** (P.3 step 4). `dangerous_in()` returns `shutdown`
  where `commands` holds ` shutdown`, and the server strips each
  authorisation. So a renderer comparing them exactly never marks the line,
  and the line never gets its box. Compare trimmed. Found only by the REAL
  `/deploy/plan` payload: step 3's restore test passed because its payload
  was hand-built with the unstripped form. Build a renderer's test input from
  the route, never by hand.
- **A credential stored twice is a credential that leaks twice** (the
  operator, B14). The `secret` column duplicates the password on every device
  for no function, and that is what made sending it look harmless.
- **A harness must not write where a person reads** (C26, the narrow form,
  kept as its own rule). The count was clean. The cost was about 2,600
  fixture lines in the app log, where a fixture refusal looks exactly like a
  real one. Only a person can mistake them, and a person is who reads that
  file.
- **An investigation's instrument can be the variable** (C20, 2026-09-25).
  A settings test failed in streaks, eight in a row and then clean at the
  same SHA, which reads as a race. It was file-order dependent and fully
  deterministic. The randomness came from the command choosing the test
  subset: `grep` in the agent's shell is a parallel `ugrep`, so the file
  order changed between runs. **The tool used to investigate produced the
  symptom being investigated**, and a bisect built on it pointed at a commit
  (8 of 8 against 0 of 8) that had nothing to do with it. Before
  attributing variation to the system, fix every input to the experiment:
  pass an explicit, ordered file list, and write down the command that
  produced it. Same family as *a pattern that can appear in English*: in
  both, the measuring apparatus matched or moved the thing it was pointed at.
- **A document asserting a property the code does not have is worse than no
  document, because it stops the next person looking.** CLAUDE.md said
  `write_settings()` was "the one path into `user_settings.json`". There was
  a second, the general-settings POST, and the claim is why nobody went to
  look for it. What found it was a scan of the code (every function that both
  loads and saves), not the sentence. A property a document states should
  have a test, or be written as *intended* rather than as fact. **It
  happened again while recording it:** the correction said `migrate()`
  "writes on every GET", and the code writes only when there is something to
  migrate. Read the function before writing the sentence about it.

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
- **(Register C23: FIXED by P.3 step 5, 2026-09-26. The rule below now lives in `build_targets()`, which
  the preview and the apply both call, with `restore.coverage()` giving the denominator; `plan_restore()`,
  where it used to live and which no route called, is deleted.)**
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
- **Onboarding no longer revokes its platform's template approval (D2,
  resolved by scheme 3, P.5).** Until 2026-09-26 it did, at CREATE:
  `devices_for_template()` computes the bound set from the manifest with no
  `pending` filter, the scheme-2 fingerprint covered that set, so a device
  that had never answered SSH revoked the approval for every other device on
  its platform, and re-approval was refused (400) until it had a capture.
  That refusal was load-bearing only because the fingerprint covered the
  device set. Now no device is in the fingerprint, the bound set is still
  computed live but only for the EVIDENCE an approval records, and a bound
  device with no capture is recorded as not validated rather than refusing.
  Kept here because the reasoning is what stops the device set being put
  back into the key.
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
- **Two cases, and the reader must know which one they are in.**
  **(a) COUPLED changes, where the devices' changes depend on each other
  (the r6/s3 branch site): one device → one intent commit → one plan → one
  confirm → one deploy → one golden commit.** Reverting one alone leaves a
  half-state. **(b) The SAME change made INDEPENDENTLY on each device (the
  P.1 syslog block): one commit may name all of them**, and a batch deploy
  is correct (see the correction below, measured from the code).
  The original reasoning, written for (a): two devices' changes in one plan couples them through
  the **confirm hash** (either half moving between plan and apply refuses the
  other's confirmed program) and through the **intent commit**, since
  `.nsot/rolled_back.json` keys on the device's current intent commit and
  "Revert intent" applies the inverse of *that commit's own diff* — so a
  shared commit means reverting one device's rollback reverts the other's
  change. The deploy boundary and the commit boundary have to be the same
  boundary.
  **Corrected 2026-09-25, measured from the code: the rule is right for
  COUPLED changes and its stated reasons are wrong for independent ones.**
  "Revert intent" reads and writes only `host_vars/<hostname>.yml` at the
  commit (`committed_at(repo, hostname, sha)`) and commits that device alone.
  `record_rolled_back()` is keyed by hostname. So a commit touching six
  devices' files can be reverted for one of them without touching the other
  five. And a batch confirm is **per device** (`confirmations` and
  `command_hashes` are both keyed by device), so a device whose program moved
  is refused alone and the rest proceed. What the rule really protects is
  the branch site's shape: two halves of ONE logical change, where deploying
  either half alone is harmful. The P.1 syslog block is the same change made
  independently on each device, and one commit naming them is correct.
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
- **The harness imports the program before any test can patch it**
  (`conftest.py`, C20). A module that binds a function by name at import
  keeps whatever that name meant at the moment of its FIRST import. If that
  moment falls inside a test's monkeypatch, the stub stays for the rest of
  the process. Measured: `test_onboard_plan.py` run first left
  `modules.integrations.base` holding its `get_setting` lambda, and the Kea
  route echoed `''` after writing the value correctly. It was deterministic
  given the file order and invisible in the full suite, where an earlier
  test always imported `app` first. **The streaks that made it look like a
  race came from the command choosing the subset**: `grep` in the agent's
  shell is a parallel `ugrep`, so its file order varied between runs. *A
  diagnosis that says "race" needs the variable named. Here it was an input
  to the experiment, not the system under test.*
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
- **The constraint lives in the docker daemon and the files that must respect
  it live in the repository, so "pick a free subnet" is advice rather than a
  mechanism.** The phase 2 probe chose `172.30.50.0/24` — which is `clab-r6`,
  running now — and docker refuses a second network on an occupied subnet
  (*"Subnet already in use by Docker network clab"*). **Nothing here could have
  known**: r6's topology is a file on the clab host, not in this repo. Same
  shape as the device → lab map, where the authority and the consumers were in
  different places, and *a per-lab allocation that nothing owns is how the
  next one collides too.*
  The mechanism is narrower than it first looks, because the obvious rule is
  wrong: **five probe topologies deliberately share one network name** —
  sequential throwaways that never run together — so "every topology gets a
  distinct subnet" would flag five correct files. The real invariant is that
  **(network name → subnet) is a function in both directions**: one name never
  means two subnets, and one subnet never belongs to two names. That is exactly
  the collision, and it is now a test.
  `RESERVED_MGMT_SUBNETS` declares what is taken **outside** the repo, with a
  reason per entry, and the stated limit is that it can only know what somebody
  wrote down — declaring a lab there is the price of the test being able to
  help at all. A reserved list without reasons is one nobody can maintain,
  because the next reader cannot tell a live claim from a stale one.
- **EIGHTH instance of a capability existing and nothing a person can reach
  calling it**, and the plainest. Phase 2's `address_source` and `mgmt_mac`
  were built in `_plan_args()`, `build_plan()` and `render_bootstrap()`, and
  the wizard was still the static-only form — **its acceptance was written as
  *"the review screen reads 'assigned by Kea reservation …'"*, on a screen with
  no way to be told the address was reserved.** After `run_onboarding`
  returning 501, `loadOnboardPending` having no caller, the pending banner
  dropping its list, `finish_bootstrap` unwired, `/onboard/create` sending
  `body: '{}'`, the deploy wizard omitting `command_hashes`, and `vs_intent`
  reading the working tree.
  **Why the tests were silent**: the payload tests construct plan arguments
  directly — the seam that hid `body: '{}'` — and the renderer tests execute
  the render without the fetch. Each half was right about its own half.
- **So the class is mechanised: the server may read nothing the form cannot
  send.** `test_server_reads_nothing_the_form_cannot_send.py` parses what
  `_plan_args()` pulls out of `data` and what `ONBOARD_FIELDS` maps, and
  asserts the first is covered by the second — *a field only `curl` can supply
  is a feature no operator has.* It runs **both ways**: a field the form sends
  and the route ignores is a control that does nothing, which is the same lie
  as a greyed-out button wearing a placeholder. Exemptions are **named with a
  reason** and capped at five, because an exemption set that grows unnoticed is
  the check being switched off one field at a time; a commented-out field does
  not count as sent, or commenting one out would satisfy the check silently.
  **It found a second instance on its first run**: `domain` is read, defaults
  to `rcn.lab`, and has no field — unlike `secret` and `source_kind` there is
  no reason a person could not set it, so it is recorded as *a gap under
  exemption* rather than a clean one.
- **A control that passes on a renderer is a missing test.** Removing the
  review's DHCP branch left the suite green while the screen said nothing about
  the reservation — the claim was computed, carried to the browser and drawn
  nowhere, for the fifth time. `TestTheReviewStatesWhatKeaSaid` executes the
  shipped `onboardReviewHtml` against a DHCP plan, and carries a floor that the
  static branch is not captured by it.
- **COMPLETENESS IS JUDGED PER SOURCE, and judging it against one shape named
  the wrong cause AND the wrong remedy.** `bootstrap_artifact()` checked
  `params["address"]` alone, so a DHCP device — which has no address and no
  mask **by construction**, and whose complete committed set is `source` +
  `interface` + `mac` + `domain` — failed a presence test written against the
  static shape and fell through to the only explanation the check knew:
  *"Devices onboarded before these were recorded are in this state; abandon and
  re-create."* Reported on a device created two minutes ago, on current code.
  **Sixth message in one session describing a state that did not occur, and the
  most expensive of them**: the remedy it named would have destroyed a
  correctly-created device and produced the identical result the second time.
  A message is not just a report — *it is an instruction*, and a wrong one
  costs more than silence.
  The legacy message **survives and now only fires when it is true**: a
  document with no `source` key predates the field, so `address` present means
  static and complete, and `address` absent is the genuine legacy state. Both
  are pinned, and a pre-`source` static device still re-renders.
- **An empty field is honest and useless when the reader cannot tell "none"
  from "not yet".** The pending banner read *"bp-dhcp-a at — pending just
  now"*. For a DHCP device an absent address is the **normal** state until it
  boots, so the row now says what is expected and from where — *"awaiting DHCP
  (Kea reservation → 10.255.0.40)"* — and a static device with no address says
  **"no address recorded"** rather than rendering a blank. The manifest carries
  the reservation because it cannot ask Kea, so the row states what was
  *reserved* rather than claiming an address the device does not have yet.
  Same distinction as `inconclusive` against `failed`, and as *"checked 7 of
  9"* against a number that reads as complete.
- **A LEASE IS A FACT ABOUT THE DEVICE; A RESERVATION IS A STATEMENT OF
  INTENT.** They are normally equal — that is the point of requiring one — and
  they can differ: a reservation edited after the device leased, a device still
  holding an older lease. `discover_dhcp_address()` reads the **lease**, and
  when the two disagree it **refuses and names both**. Not a tiebreak: the tool
  cannot know which is stale, and writing either would make two stores disagree
  about one device, which is the shape the reservation precondition exists to
  prevent. And it **never falls back to the reservation when there is no
  lease** — *"what the device has"* has no answer then, and answering *"probably
  this"* is how an inventory acquires an address nobody verified.
- **The tool never wrote this address, so phase 2 has to discover it — and
  three separate places assumed it had.** `verify_device()` read `mgmt_ip` from
  the manifest, which is empty for a DHCP device **by construction**;
  `run_phase_two()` kept its own local copy, so adopting the address in verify
  alone would have left the capture, the RW removal, the golden and the CSV row
  all using `""`; and `bind_credentials_step()` keyed the device override on
  `plan.mgmt_ip`, staging the credential **under the empty string**, so
  `resolve()` at verify would look under the discovered address and find
  nothing. Each would have failed for a reason none of them could name.
  The address is resolved in **one** place and adopted, not re-derived:
  `mgmt_ip = seen.get("mgmt_ip") or mgmt_ip`. The credential is keyed on the
  **reserved** address, which is the address the device is *guaranteed* to get —
  that guarantee being why a reservation is a precondition — and a lease that
  disagrees refuses before anything asks for a credential, so a wrong key
  cannot be silently used.
- **containerlab's per-endpoint `mac:` survives vrnetlab's VM** — measured
  2026-09-24 on `bp-dhcp-a`: `bia aabb.cc00.0240` on `GigabitEthernet2` is the
  MAC pinned in the topology. The assumption was recorded as *probable,
  unverified* with a check and a fallback; it is now measured, and a DHCP
  reservation can be written before a node's first boot.
- **A DENYLIST OF SUSPICIOUS SOURCES WAS OUTGROWN BY THE NEXT SOURCE.**
  Verification reported `credential_source: "profile:default"` — the tool knew
  perfectly well it had fallen back to the list's default profile — and the
  causes list said *"only the credential is wrong"* and sent the operator to
  the console. The condition was `cred_source in ("none", "unresolved",
  "caller")`, so `profile:default` walked straight past it. **The diagnostic
  that solved the problem was in the payload and absent from the message.**
  `STAGED_CREDENTIAL_SOURCE` is an **allowlist of one**: a device
  mid-onboarding has never held any credential but the staged one, so a profile
  cannot be right even by accident, and an allowlist cannot be outgrown by a
  source `credentials.resolve()` adds later. It is the first cause, ahead of the
  console check, and says *"a profile cannot be right here even by accident"*
  rather than restating the source.
- **A device in an unrecoverable state with no signal is the pending-forever
  shape the banner exists to prevent** — and one existed. The override is keyed
  on the address `resolve()` looks under; a DHCP device staged before that key
  was corrected has its credential under the **empty string**, so Verify falls
  back to a profile, the device refuses it, and nothing beforehand said a word.
  `pending_devices()` now carries `credential_findable`, and the banner says
  **"Abandon and re-create — nothing has reached the device, so there is
  nothing to undo"**: the recovery *and* the reassurance, because a destructive
  instruction with no cost stated is one an operator hesitates over. An
  unreadable credential store answers **True**, since flagging every pending
  device as broken because the store could not be read is a worse lie than the
  one this catches.
- **Two of my own assertions failed the rules I had just applied elsewhere.** A
  test asserted `len(causes) == 1` — a **count standing in for a property** —
  and broke the moment a second, *correct* cause was added; and its replacement
  searched `why` for `"interface"` and matched the sentence that RULES THE
  INTERFACE OUT (*"so the interface and the address are right"*), which is *a
  pattern that can appear in English needing an anchor*, inside the test
  asserting it. Both now assert on the `cause` labels only.
- **A reveal driven by `change` alone is wrong on the SECOND use and right on
  the first**, which is why building and testing the field did not reveal it. A
  select's initial value is set without firing `change`, so a browser that
  remembered `dhcp` showed *DHCP* selected beside a visible, pre-filled
  Management IP and no MAC field: **the form said dhcp and collected static**,
  two sources disagreeing about one fact. The fix is to run it **on open, from
  the select's current value**, rather than assuming it starts at the default.
  **Which won, measured**: `onboardFormPayload()` reads every field
  unconditionally, so the *select* won — the bootstrap config emitted
  `ip address dhcp` and contained no static address — and in that session
  Create would have been **refused**, because the hidden MAC field was empty
  and a DHCP plan without a MAC is a blocking reason. The precondition caught
  it incidentally.
- **The cosmetic half was the smaller half: a DHCP plan must carry no static
  address at all.** The typed address rode along on the plan, `commit_step`
  records `plan.mgmt_ip` on the manifest, and `verify_device` starts with
  `mgmt_ip or entry["mgmt_ip"]` — so a stray address would have been written,
  found, and **the lease discovery skipped entirely**, sending verification at
  a torn-down device's old address. Dropped in `build_plan()`, the only
  constructor, so it holds however the arguments arrive. *Not merely unused —
  actively harmful, and the render being correct all along is what made it
  subtle.*
  Hidden fields are **cleared**, not just hidden: a hidden input still has a
  value and autofill puts one there, so hiding alone leaves the payload
  carrying an address the operator cannot see and did not choose.
- **A placeholder naming a real fleet address is a small trap of its own.** The
  Management IP field suggested `10.255.0.31` — bp-onboard-c's actual address
  from the first probe, a **torn-down** device. A placeholder naming a live
  range invites typing that exact address, and *an address that used to belong
  to something is the worst kind to reuse by accident*. RFC 5737 exists for
  this; a test now refuses any placeholder in the fleet's ranges, with a
  positive anchor so it cannot pass by the examples having been deleted.
- **Abandon DID clear the credential override — only the key it knew about.**
  It read `mgmt_ip` alone, guarded by `if mgmt_ip`, so the `''` key left by a
  device created before the DHCP key was corrected survived it — and
  **80b4e37 introduced a second leak of the same shape**, because a pending
  DHCP device's override is keyed on the **reserved** address and abandon never
  looked there. Both are cleared now, per key. *A staged credential outliving
  the device it was staged for is a secret with no owner, in the one file where
  a device-specific credential lives.*
- **`set_device_override("")` is refused.** An empty key means *"I do not know
  which device this is for"*, and a credential stored under it is worse than
  one not stored: nothing can look it up, nothing can attribute it, abandoning
  the device cannot clear it — **and the next such device collides with it**,
  which is one device's credential being served for another. The guard is at
  the setter, because that is the only place the decision is made.
- **`data/credential_profiles.json` is a secret store with no expiry and no
  owner check** — the shape of the 29 untracked backup directories beside
  `labs/lab/configs`, **except these hold credentials**. Measured on the live
  store: five keys, one `''`, one belonging to a probe torn down hours earlier,
  one nobody recognised. `scripts/nmas-credential-overrides` surveys which keys
  a list can plausibly look up — a `devices.csv` row, a manifest `mgmt_ip`, or
  a manifest `reserved_address` (a pending DHCP device) — and names the rest
  orphans. **Keys and names only; no value is read or printed**, or the audit
  becomes a second place the secrets appear. It **does not delete**: an override
  may be a deliberate break-glass credential, and removing a secret because a
  script could not attribute it is the wrong direction — it prints what would.
  And zero claims across every list is **UNPROVEN**, not *all orphans*: the
  inventories being unreadable would otherwise report the worst possible answer
  with confidence.
- **A script whose entry point cannot reach its own IMPORTS.**
  `nmas-credential-overrides` omitted the two lines fourteen other scripts
  carry, so it ran only with `PYTHONPATH` set — *which is to say it had never
  been run the way a person runs one*. Same family as `_remove_excluded`
  stranded below the `__main__` guard, and **the entry-point sweep built for
  that could not see it**: it parses for definitions the entry point cannot
  reach, and this is imports the entry point cannot reach.
  The rule is now *a script importing `modules` must put the repo root on
  `sys.path`*, with a floor on how many such scripts exist and a counterpart
  asserting that a dependency-free script (`nmas-clab-targets`, deliberately
  standalone so the clab host can run it) needs none.
- **`--help` is NOT the import check, measured — and the proposed runnable
  check would have passed on the broken script.** argparse prints and exits
  **before any function body runs**, and this project imports `modules`
  *inside* functions to keep startup cheap. So `--help` proves the file parses
  and argparse is wired, and says nothing about whether the imports resolve.
  Kept for what it does catch — a syntax error, a broken argparse, a
  module-level statement that raises — and **pinned as insufficient**, with a
  test that runs a bootstrap-less script both ways and shows `--help` passing
  where a real invocation fails. The danger is somebody later reading it as
  the import check. Third time this session a check could not exhibit the case
  it was written for.
- **Running it the real way found the next defect immediately.** With the
  import fixed, `nmas-credential-overrides` crashed on
  `get_device_lists()`, which returns `list[dict]` and not a mapping — the
  **sixth inferred-signature defect**, and mine. The script then ran and its
  own floor fired correctly: zero devices in this checkout's inventories, so
  it refused with **UNPROVEN** rather than reporting every override as an
  orphan.
- **My own bootstrap check matched one spelling of the construct.** The
  repository has two — `sys.path.insert(0, ROOT)` and the inline
  `sys.path.insert(0, os.path.dirname(...))` — and the literal-string version
  reported the five inline scripts as broken. Parsed now: any `sys.path.insert`
  or `.append`, however the path is computed. **The Gi1 link check blind to the
  extended format, one file over and two hours later.**
- **PHASE 2 IS PROVEN** (2026-09-24, [docs/PHASE2_DHCP.md](docs/PHASE2_DHCP.md)
  §8). A device the tool never addressed fetched its own address from a Kea
  reservation, was **found at that address by the tool asking Kea for the
  lease**, then reached, captured, rotated, cleaned, recorded and promoted —
  with **no relay in the path**, which is the variable phase 2 exists to
  isolate from phase 3. Four stores agree on `10.255.0.40`: the manifest
  (discovered, matching `reserved_address`), the CSV (with the rotated
  credential), Kea's lease, and NetBox.
- **An address without a prefix is a claim about the NETWORK, and NetBox
  recorded a host route where a /24 lives.** The mask is not in the manifest
  for a DHCP device — correctly, it is not known at plan time — so the record
  fell through to `_upsert_device`'s last resort, which exists for a golden
  that genuinely has no addresses. **The lease knows**: it carries a
  `subnet-id`, and the server's own configuration has the CIDR. Threaded from
  `lease_for()` through `discover_dhcp_address()`, the manifest and the device
  dict to the NetBox record. *Being wrong about the network is the one thing
  NetBox cannot be, because that is what NetBox is for.*
  **Unknown stays 0, never 32.** A host route is the honest answer when the
  length cannot be known, and guessing it in the new code would have moved the
  defect rather than removed it — the fallback survives, with a floor asserting
  it does.
- **A lease is a fact; a reservation is intent, and a tool that reads the
  reservation is reading its own intent back and calling it a discovery.**
  Phase 2 is closed (2026-09-24): a device the tool **never addressed** fetched
  its own address from a Kea reservation on a **pool-less** subnet — the first
  DHCP transaction that segment has ever carried — and was then **found** by
  `discover_dhcp_address()` asking Kea for the **lease**, never the
  reservation, before being reached, captured, rotated, cleaned, recorded and
  promoted. Four stores agree on the address, and the **leased** one is what
  was recorded. They agreed here, so the choice is invisible in the result,
  which is exactly why it had to be made before the probe: reading the
  reservation would report an address for a device that never booted, one that
  booted on a different interface, and one whose reservation was edited after
  the lease was granted. **A disagreement therefore refuses and names both
  operands** rather than preferring either — picking one puts an address into
  the inventory that another store contradicts, which is the failure the
  reservation precondition exists to prevent arriving one layer down, where
  nothing was watching. Same rule as a golden against a render: never
  substitute, *because they usually agree*. What it does **not** prove is
  reboot-safety (the node was destroyed, not rebooted) or a relay path (phase
  3) — isolating those is why it ran on a throwaway.
  [docs/PHASE2_DHCP.md](docs/PHASE2_DHCP.md) §9.
- **Running the tool is how defects are found; the suite is how they stay
  fixed.** Phase 2's ledger, because it is the argument for the method:
  **9 commits fixed things found by running it, carrying 15 distinct defects,
  and the suite caught none of the 15** — green throughout, 3,276 → 3,360
  tests, every assertion exact. **9 of 15 were written that day**, 4 the day
  before, 1 four days earlier, and 1 **five months** earlier (NetBox recording
  a leased address as a `/32`). The reason is uniform and therefore
  actionable: every one lives in a **seam** — between the form and the server,
  between a value and the store it is keyed in, between the tool and a
  service, between a function and the caller that no longer supplies what it
  reads, between a check and the spelling it was pointed at, between a message
  and the state that actually occurred, between a script's entry point and its
  imports, and between the repository and a constraint that lives in a running
  daemon. **A test that constructs its own subject cannot notice that the
  caller does not** — nine instances now, the dominant class in this project.
  The mechanical answers are the ones that have worked: one field list read by
  both ends (`test_server_reads_nothing_the_form_cannot_send.py`), the
  entry-point sweep, `assert_dialect()` at a boundary, and executing the
  **shipped** renderer against the payload the **deployed** endpoint returns.
  State the division of labour this way rather than as scepticism about tests:
  the suite made all 15 fixes **safe**, catching three regressions by name
  while they were made. A stage that only runs the suite discovers nothing,
  and a stage that only runs the tool goes backwards while it works.
  [docs/PHASE2_DHCP.md](docs/PHASE2_DHCP.md) §10.
- **`netbox_allow_writes` stays ON as the steady state, and an UPDATE is the
  class no provenance covers.** Both probe runbooks said *"turn it off again
  at teardown"* and neither said why — an instruction whose reason is *"that
  is what the last one said"* is one nobody can evaluate, so it was argued
  and dropped ([docs/PHASE2_DHCP.md](docs/PHASE2_DHCP.md) §11). The gate is
  real, but it was **on throughout both NetBox incidents it would nominally
  have prevented** — it has to be, or the import that caused them could not
  have run — so what caught them was the census baseline, the tag, the
  created-id record and `--compare`. Its contribution is *"you turned it on
  deliberately once"*: a reminder, not a defence, against which every onboard
  needs it and off means the next one refuses until somebody remembers.
  **The case worth checking exists, in the second half.** Nothing writes
  outside the gate — exactly **three** HTTP write calls in the tree, each
  inside its chokepoint behind `assert_writes_allowed()`. But `_nb_patch` is
  outside the **provenance** path: gated and previewed, yet **not tagged, not
  recorded, not reversible by Remove, and invisible to `--compare`** — the
  last measured, not reasoned, because the census identity is `id:display`
  and moving an address between interfaces changes neither (`41:10.0.0.15/24`
  both sides, `compare()` finds nothing). **That is precisely the 2026-09-24
  damage**: `_ensure_ip_address()` PATCHing `assigned_object_id`, the object
  never disappearing, so nothing had anything to report for weeks. Not
  tagging an update is **correct** — the tag means *NMAS created this*, and
  claiming a human's object would make it deletable — so the gap is that
  **nothing records the touch at all**. Eleven PATCH sites; `_ensure_site()`
  re-parents any slug-matching site with the comment *"if someone moved
  it"*, deliberately overriding a human on an object Remove correctly skips.
  **It does not change the decision**, and the reason is the sharp part: a
  control that is necessarily open whenever the dangerous path runs is not a
  defence against that path, so turning it off at teardown covers the
  uncovered class not at all. *Provenance protects an OBJECT; a cascade
  travels a RELATIONSHIP* — and **an update travels neither.**
- **`data/netbox_modified.json`: what NMAS MODIFIED, which is a different
  claim from what it created** (§12). A **second file**, keyed the same way,
  and that is the whole point — the created-id record is one half of
  removal's `tagged AND recorded`, so putting an update in it would mark a
  human's object as NMAS's own and **make it deletable**, the one ownership
  claim an update must not make. Pinned: after a modification is recorded,
  `was_created_by_nmas()` is still false, and `forget_created()` (what
  deleting a list does) leaves the history intact.
  **The BEFORE is the load-bearing half** — *"NMAS set it to 60"* is a fact,
  *"NMAS moved it from 44 to 60"* is the finding — so `_nb_patch` reads the
  object **itself**, immediately before the write, never from a caller: an
  optional `before=` is how a caller bypasses a guard by omission, and there
  are eleven PATCH sites. Three states, not two: a changed field records
  `{before, after}`, a payload setting values the object already holds
  records **nothing** (its content did not move), and an unreadable object
  records `before_unknown` — counted separately, because *"what changed is
  unknown"* and *"nothing changed"* must not share an answer. A field NetBox
  did not return is `<unknown>`, distinct from a genuine `null`. Values are
  capped **with a marker**, since *bulk is not evidence*. NetBox's nested
  form is normalised before comparing (`{"region": {"id": 5}}` against a
  payload's `5`), or every field of every PATCH looks changed and the log
  records a modification on every no-op sync — which is how a checker gets
  switched off.
- **A census PASS now states WHICH CLAIM it makes.** It has always meant *"no
  object was created or destroyed"* and was read as *"nothing changed"*, and
  those differ by exactly the class that caused the incident — measured: an
  address moved between interfaces reads `41:10.0.0.15/24` on both sides and
  `compare()` returns nothing. The headline is qualified (`PASS (with
  modifications — read them above)`) because a reader skimming for PASS will
  not read the paragraph under it; **exit codes are unchanged**, because a
  modification is not *"objects left behind"* and collapsing them repeats the
  error the three codes exist to avoid. **Four statuses, not two**, so a zero
  cannot pose as an assurance: `none` carries its **denominator** (*0 since
  the baseline, out of N recorded in total* — the total is what proves the
  recorder runs), `some`, `unknown` (*"weaker than 'none', not equal to it"*),
  and **`no-record`** (the file has never been written — on an install that
  has run an import, the recorder is not reaching it). The headline is chosen
  from that status and **never by matching the printed sentence**: the first
  version did, which is the *pattern that can appear in English* error
  committed inside the fix for it, and it read `unknown` as *"modifications
  exist"*. A baseline with no `taken_at` says **"all time — could not be
  scoped to the run"** rather than attributing old modifications to this
  teardown.
- **`_ensure_site()` re-parented any slug-matching site, and that was a
  behaviour nobody chose.** The comment said *"re-parent to the right region
  if someone moved it"* — so a site a human had deliberately placed was
  silently moved back on the next sync, which is the tool being inconsistent
  about ownership in the direction that matters: **removal refuses to touch
  an object NMAS did not create**, so it would decline to delete your site
  while happily moving it. It now re-parents only its own and **reports** when
  it declines, collected into the sync summary's `notes` rather than only
  logged, because a refusal nobody reads is the same as no refusal. Adoption
  is unchanged — a matching site is still used rather than duplicated; what
  changed is that it is no longer edited silently. Ownership is **tagged OR
  recorded**, deliberately not removal's **AND**: the actions differ in blast
  radius, deleting a human's object being unrecoverable while declining to
  re-parent NMAS's own costs a warning, and the tag is applied by `_nb_post`
  only, so a tagged site *was* created by NMAS even after its created-id
  record was lost with a deleted list.
- **Both provenance records are written temp-then-`os.replace`.** They were
  `open(path, "w")` — truncate in place, the shape that erased
  `user_settings.json` — and a fragment of either reads as **empty**: for the
  created-id record that means Remove can no longer find objects it created,
  which makes them *tagged and unrecorded*, the one combination it cannot act
  on.
- **THE FIX FOR A PROVENANCE GAP CREATED A NEW PLACE A CREDENTIAL LIVED.**
  §13. The modification record's first live run found three things and **one
  was the recorder**: 113,767 bytes from a single sync of ten devices,
  because the cap was on **strings** and `local_context_data` is a **dict**
  holding a whole running config. It stored a device's `secret 9 $9$…` and a
  `username … password 0` line unmasked — and `nmas-check-secret-storage` did
  not know the file existed, which is **verbatim that script's own warning**
  (*a secret in a store this script does not know about is not reported at
  all*) arriving in a store created after the warning was written. The other
  cost is the same end the drift checker reached by a different road: **a
  record costing 113 KB a sync is one somebody turns off.** The two genuine
  findings in that same run are the mechanism working — r6's loopback prefix,
  and NetBox holding a **month-stale** full config copy that the sync
  refreshed, which nothing would have reported before.
- **Cap a recorded value by SERIALISED SIZE, never by type**, and above it
  record *changed, this big, this hash* — `local_context_data: 14.2 KB → 15.1
  KB (sha 3f2a… → 9c81…)` is the finding; the bytes are not. Same lesson as
  `skipped_drifted` carrying a whole device config and neither of the two
  hashes it had compared. **The hash is of the RAW value, deliberately**:
  hashing the masked form makes a credential rotation hash-identical to no
  change at all — the one movement most worth noticing, made invisible by the
  masking meant to protect it — and a value short enough to be a guessable
  preimage never reaches that path, being under the cap and therefore
  redacted and stored instead.
- **An audit record is masked AT REST, and the golden-config argument does
  not extend to it.** *Masking is outbound, never at rest* holds for
  `golden/` because a golden has to restore a network and masking it would
  make the repository useless for its one purpose. Nobody restores anything
  from a modification record, so it is masked on the way **in**, through the
  same `redact_text()` — positional as well as value-based, so a device NMAS
  was never told about is covered. And it **fails closed**, the opposite of
  the log filter and for the reason that decided that one: a log that loses
  entries is the worse failure in the file an operator reaches for when
  something has gone wrong, and **nobody reaches for this file in an
  outage** — so a dropped value costs a detail while a leaked one costs a
  credential. Severity stated in both directions: a `$9$` value is a salted
  hash already in `golden/` by design, while the `password 0` form is a
  plaintext credential outright.
- **A checker whose stores are named keys needs a second shape for a blob
  whose policy is "no secret at all".** `nmas-check-secret-storage` classified
  named keys as encrypted or plaintext, which cannot express a file that
  should simply never contain a credential. Those are scanned instead with
  `redact_positional()` — *the finding is that redacting the file changes
  it* — reported UNPROVEN when the scan cannot run, and carrying a positive
  control that a planted secret IS found, because a scan that can only say
  "clean" is indistinguishable from one that could not run.
- **Fixing a writer does nothing about what is already written.**
  `scripts/nmas-netbox-modified --sanitise` rewrites the existing record
  through today's summarisation and masking, **keeping the findings** and
  dropping only the content of oversized fields — *a tightened mode does not
  undo exposure* applies to a record as much as to a file. Both provenance
  records are created `0600`, and a loose mode **self-heals on the next
  write**, because `os.replace` swaps in the temp file's inode (measured; the
  checker found `netbox_created_ids.json` at `0664` from before `open_secure`
  was applied). **`--sanitise` therefore always writes, even with nothing to
  rewrite** — measured, the first version returned early on `rewritten == 0`
  and left a loose mode exactly as it found it, while the checker names that
  command as the remedy for a loose mode. *A named remedy that runs, reports
  success and changes nothing* is one step worse than advice that is merely
  incomplete.
- **NETBOX SAYS s1 IS OFFLINE AND IT IS NOT, AND ONLY THE MODIFICATION RECORD
  COULD SEE IT** (§14, 2026-09-24 — the record's first live run). Measured by
  driving the real call site: `status="active" if (status_cache or
  {}).get(result["ip"], False) else "offline"`, where `status_cache` is the
  **in-memory ping cache** written by `connection.ping_worker` every 5s from
  `is_device_online()` — ICMP via ping3, falling back to TCP:22. So NetBox's
  `status` is *whether one probe answered within five seconds of the sync*,
  recorded as a standing claim. s1 answered SSH minutes later; s2–s4 stayed
  active in the same sync, which **rules the structural causes out** and
  leaves a genuine transient.
  **`.get(ip, False)` cannot tell "probed and failed" from "never probed"** —
  *a lookup that misses is a fact about the query, not about the system* —
  and the shared answer is the assertive one. Three ordinary ways to be
  never-probed: the worker pings **the active list only**, a NetBox-sourced
  list has no CSV so `os.path.exists(fn)` is false and **nothing in it is
  ever pinged**, and the first cycle has not finished at startup.
- **The status write is a SELF-SEALING loop on a NetBox-sourced list.** The
  default source filter is `{"status": "active"}`, passed straight into the
  device query — so one failed ping writes `offline`, the next refresh does
  not return the device (**absent, not skipped, not named**), everything
  keyed on the inventory stops covering it, and the next sync iterates the
  inventory that no longer contains it, so **nothing can ever set it back**.
  The state that removes a device is the state only that device being present
  could correct. Not firing today only because `default` has no
  `source.json` and is therefore `local` — **luck, not design**; it arms the
  moment a list is switched to `netbox`, which is Phase 1's whole point.
- **The fix is to stop writing it, and the project's own rule is the
  argument.** Not *"NetBox is not a monitoring system"*, true though that is:
  **`_scan_device` was deleted because *importing observed state into the
  source of truth is the wrong direction*** — and a ping result **is**
  observed state. That rule removed 140 lines of SSH scanner, and this field
  survived it by being three words on a call site rather than a function with
  a name. Precisely: **create** may set `status: active` (a lifecycle claim,
  earned because onboarding reached the device), **update** drops `status`
  from the PATCH allowlist entirely. Liveness already has an honest home —
  the app's own badge, live when read, which nobody mistakes for a stored
  fact. *Recorded, not applied: it changes what the tool asserts about the
  network.*
- **What the modification record bought, on day one.** `--compare` said *no
  object was created or destroyed* and **that was true**; the drift checker
  compares device configs, not NetBox fields; the census compares identity,
  and an in-place status change alters neither id nor display. **Nothing else
  looks.** A false statement sat in the source of truth and the only thing
  that could see it was the record built the day before — in a field nobody
  had thought to check, about a device nobody had reason to suspect.
- **A RULE IS APPLIED TO THINGS THAT HAVE NAMES, AND THE SAME VIOLATION IN AN
  EXPRESSION GOES UNEXAMINED** (§15). `_scan_device` — 140 lines — was deleted
  under *"importing observed state into the source of truth is the wrong
  direction"*, while `status="active" if (status_cache or {}).get(...) else
  "offline"` on a call site did the same thing and survived, because nothing
  about three words in an argument list presents itself as a subject for a
  rule. Now fixed: **`status` is out of the PATCH allowlist and the expression
  is deleted**; **create still sets `active`**, which after the change means
  *NMAS onboarded this device* rather than *it answered a ping*, and is earned
  because onboarding reached the device first. `status_cache` **keeps** its
  legitimate use — not opening an SSH session to a device that is down — with
  a control pinning that the fix did not overshoot into removing it.
- **Fixing a writer leaves every wrong value in place for ever** when nothing
  will write the field again. `scripts/nmas-netbox-status-reset` corrects them
  once, dry-run first, and **provenance governs exactly as removal does**: only
  devices NMAS created, with a human's `planned`/`staged`/`decommissioning`
  reported and left alone. It goes through `_nb_patch`, so it is gated and
  recorded like any other write.
- **Closing a loud loop can leave a quiet permanent one.** The NetBox source
  filter defaulted to `{"status": "active"}`; with status no longer tracking
  liveness it is frozen at whatever it was when the device was created, so a
  device unreachable during its first sync would be **invisible for ever** —
  *if status no longer tracks liveness, filtering on it selects for an accident
  of onboarding*. Default is now no status filter; an operator may still set
  one, and nothing assumes it.
- **The sweep's discriminator is not "observed versus intended".** The NetBox
  import is *designed* to run from golden configs, which are observations too —
  **approved** ones. The line that separates them is **does this field change
  without anybody deciding it?** `serial`, `os_version` and `model` change when
  the hardware or image changes, which is worth recording; a ping result
  changes on a five-second timer; and `comments` and
  `local_context_data.ndm_sync` both embed the sync's own timestamp, so they
  **differ on every sync by construction**.
- **That churn is the modification record's own "somebody turns it off".** Two
  fields differing every sync means an entry for **every device, every sync,
  for ever** — and `ndm_sync` sits *inside* `local_context_data`, so that
  field's hash moves every sync too. Same end the 113 KB would have reached by
  a different road: not volume of bytes but volume of meaningless entries, and
  a log whose every entry reads *"the sync ran"* teaches the reader to skip it,
  so the next false `offline` goes past unnoticed. Recorded, not applied — the
  honest fix is to drop the timestamps (NetBox's own `last_updated` already
  carries the sync time) rather than to exclude the fields from the record,
  which would hide a real write — **and would be the checker-exemption shape:
  the log quietly stops covering the writes that happen most.**
- **Both sync timestamps are gone** (`comments`' `Synced: <ts>` and
  `local_context_data.ndm_sync`), and the **second** reason is the stronger:
  NetBox already owns that fact — every object carries `last_updated` — so
  they were a **second copy of somebody else's field**. That makes it the
  two-owners rule rather than a noise fix, and dropping them removes a
  duplicate rather than losing information. The config template NMAS installs
  read `ndm_sync`, so **both ends moved together**: removing the key alone
  would leave `! Synced  : ` rendering empty for ever, a label with nothing
  behind it. What remains in `comments` changes when the platform, version or
  management address changes — pinned by a floor, since emptying the field
  would satisfy every no-timestamp assertion. The claim that matters is
  end-to-end: **a repeat sync of an unchanged device now records nothing at
  all**, not something small.
- **PROVENANCE-BY-CREATION IS THE WRONG TEST FOR A FIELD-LEVEL CORRECTION**
  (§16). `nmas-netbox-status-reset` refused to fix s1 — *"NMAS did not create
  them, so their status is somebody's decision"* — while
  `netbox_modified.json` held NMAS's own write of that exact value, `before
  {'label': 'Active', 'value': 'active'} → after 'offline'`. Correct by its
  rule and **false about the fact**: the tool declined to correct a value it
  had made, in a message asserting the opposite. *Did NMAS create this
  object* and *did NMAS write this value* are different questions — removal
  needs the first, because deleting what it did not create is unrecoverable;
  a field-level undo needs the second, which was **unanswerable until the
  modification record existed**, which is why the script was written against
  the wrong one. It now takes its authority from the log, which is also
  **stronger than resetting to `active`**: it restores what the field held
  *before NMAS touched it* — `active` for s1, `staged` for a device somebody
  staged. `_restore_target()` unwinds an **unbroken run of NMAS's own
  writes** and stops where the chain breaks, because a gap means somebody
  wrote in between and theirs is the one to restore; an unrecorded
  before-state **refuses** rather than defaulting, since this script exists
  because a value was asserted without being known.
- **Ten devices in NetBox and one of them removable, measured.** Both halves
  of provenance — the `nmas-managed` tag and `netbox_created_ids.json` —
  arrive in `eac9c5e` (**Phase 0, 2026-09-20**), while the NetBox sync dates
  from `3135efd` (**2026-04-22**). The nine reference devices were imported by
  five months of an importer with no provenance mechanism, so they carry
  **neither** tag nor record; r6, onboarded after, carries both. A
  provenance-based Remove can therefore act on r6 and is blind to the other
  nine — *safe*, and it means the teardown mechanism has never been proven
  against them and by construction never can be. Adopting them is a
  deliberate act, not something to do in passing.
- **A third churn source, in the comparison itself.** NetBox renders an enum
  as `{"value", "label"}` and accepts a bare string, and `_comparable` reduced
  a **reference** (`{"id": N}` → `N`) while leaving an **enum** alone — so an
  *unchanged* enum compared unequal and the record logged a change that did
  not happen. Reachable: `_ensure_ip_address` PATCHes its whole payload when
  only the description or VRF differs, and that payload carries `status`.
  Fixed keyed on the exact shape, so an arbitrary dict with a `value` key is
  left alone, with a floor that a real enum change is still recorded.
- **A RESTORE MUST NOT WALK PAST A CREATE, AND THE LOG CANNOT SEE ONE**
  (§17). The status reset's dry run offered `r6  active → offline` for a
  device that is up, reachable and onboarded an hour earlier. The mechanism is
  one step from the obvious reading: **the modification log holds only
  updates** — `_nb_post` calls `record_created`, `_nb_patch` calls
  `record_modified`, asserted now rather than assumed — so **reaching the
  earliest logged entry does not mean reaching the object's origin**. r6 was
  POSTed `offline` because the ping worker had not yet seen a device that had
  just booted, then PATCHed `active`; the single logged entry's `before` is
  NMAS's own create-time write, not a prior state. *(The create path is
  already fixed — the call site's `status=` argument is gone, so creates take
  the `active` default; r6 predates it.)*
- **The two records answer different questions, and using each for its own is
  the fix.** The **modification log** answers *did NMAS write this value* —
  authority to correct. The **created-object record** answers *did NMAS create
  this object* — whether *"before NMAS"* names anything at all. The first
  version used creation as authority and refused to undo NMAS's own write on
  s1; this uses it as an **existence test, scoped to `reached_start`**, so a
  **gap in the chain means a human's value and is restored however the object
  came to exist**. That scoping is the whole difference, and both directions
  are controlled: removing the stop reproduces the r6 row, applying it
  regardless of `reached_start` makes s1 unfixable again. Tag **or** record,
  since `_nb_post` alone injects the tag, so a tagged object was created by
  NMAS even where a deleted list took its record.
- **Naming both operands paid for itself twice in one evening.** The report
  said *"NMAS wrote 'active' over 'offline'"*, so the wrong row was readable
  at a glance by the operator **before anything was written**. The previous
  version said `0 to correct, 1 skipped` — a count with no operands — and
  would have been applied without anybody knowing. First `skipped_drifted`
  reporting neither hash and costing three wrong hypotheses; now a restore
  plan printing what it would replace and stopping a bad write. **The
  difference is not detail: one makes a claim a reader can check, the other
  asks to be trusted.**
- **A FOURTH CHURN SOURCE, FOUND BY THE VERIFICATION RATHER THAN BY THE NEXT
  SYNC** (§18). `role` and `device_role` are **one field under two names**
  (NetBox 3.x vs 4.x) and the payload sent both so either server accepts it —
  so a server echoes only its own and the other is absent from the response,
  recorded as `before: <unknown>`. An entry for every device on every sync,
  and the worst-looking of the four, because **`<unknown>` is the shape of a
  failed read rather than of a no-op**. Updates now send only the alias the
  server uses; creates still send both, where compatibility matters and
  nothing is logged anyway. **The test that found it first bypassed the filter
  it existed to exercise** — `changed_fields()` on a hand-built payload, i.e.
  a payload no code sends — and its fixture was thinner than what the sync
  writes, so an unchanged device looked changed. It drives `_upsert_device`
  now and builds the stored context with the real producer.
- **"No entries" is exactly what a broken recorder produces**, so it cannot be
  the check. Four sources of noise removed means **silence is the expected
  result**, which is indistinguishable from a recorder that has stopped — the
  vacuous pass, inside the check built to confirm the fix for noise. The
  verification is therefore two-sided: the entry count must not move across a
  sync, **and** a deliberately changed field must appear. Predicted in advance
  so it is not misread: `local_context_data` carries the running config, so
  r1–r5's regenerated self-signed certificates still log — a real change being
  reported, not the fix having failed.
- **THE s1 ARC — six steps, each only possible because of the last**
  ([docs/NSOT_WRITEUP_NOTES.md](docs/NSOT_WRITEUP_NOTES.md), *"The s1 arc"*).
  A ping cache wrote `offline` for a device that was up → **nothing existing
  could see it** (`--compare` checks identity, drift checks configs, the
  census checks membership — each correct and each structurally incapable) →
  a modification record built **hours earlier** caught it on its first real
  run → the writer was removed under a rule the project already had and had
  never applied to it, because it was an **expression rather than a
  function** → the value was restored using a *did NMAS write this* versus
  *did NMAS create this* distinction that **only existed because the record
  did** → and the restore is itself in the log. Remove any step and the rest
  do not happen. **And the whole chain rests on the census being changed to
  say which claim it was making** — had it gone on printing an unqualified
  `PASS`, the entry would have been written and nobody would have had reason
  to look. *A report that qualifies its own claim is not a courtesy to the
  reader; it is what makes the next question askable.*
- **A FIFTH CHURN SOURCE: AN UNORDERED COLLECTION COMPARED AS AN ORDERED ONE**
  (§19). `tags: [4, 2, 1] → [1, 2, 4]` — the same three tags, logged as a
  change on every sync for every device with more than one. **Two defects, and
  fixing only the comparison would have hidden the worse one**: the caller did
  `list(set(current_tags + tag_ids))`, which hands back an arbitrary order, and
  **PATCHed unconditionally** whenever the device had any protocol tag — a
  guaranteed no-op write every sync, for ever. Comparing unordered alone would
  have made the entry vanish while the pointless write carried on, which is the
  checker-exemption shape. So `sorted` makes the value stable *and* `if
  set(merged) != set(current_tags)` stops the write happening.
  **Named fields, never "every list"**: `UNORDERED_LIST_FIELDS = {tags,
  tagged_vlans, object_types}`, each a many-to-many reference NetBox returns in
  whatever order it pleases. The default stays **ordered**, because order
  carries meaning in an ACL, a route-map, a prefix-list — the same lesson
  `section_is_unordered()` already encodes for config sections, where the
  allowlist is explicit and *order-significant anywhere wins*. A control
  treating every list as a set fails, which is what stops this degrading into
  *"lists never differ"*.
- **Five churn sources, all found within a day of the record existing, none
  visible before it**: a sync timestamp in `comments`, the same timestamp in
  `local_context_data.ndm_sync`, the enum-versus-reference asymmetry, the
  `role`/`device_role` alias, and unordered tags plus their unconditional
  write. **Every one was a write NMAS had been making for months**, and the
  only reason they are visible is that something finally recorded what it
  wrote. *A record nobody can bear to read is worth nothing* — which is why
  each was fixed rather than filtered.
- **A SIXTH: A GUARD THAT COULD NEVER BE SATISFIED** (§20). The same entry
  twice — `template_code: 519 B → 521 B`, **identical before *and* after** —
  and the log's own repetition is what proved it representational rather than
  a content change. Measured, not guessed: the sizes are JSON-serialised, so
  **one stripped trailing newline is two characters**, exactly the delta.
  `_ensure_config_template` already guarded its PATCH on `existing !=
  _NDM_TEMPLATE_CODE`, comparing what NetBox stores against a string NetBox
  will never store — **permanently true**, so the template has been rewritten
  on every sync since it was introduced. *A guard that can never be satisfied
  is worse than no guard, because it makes the write look considered.* The
  constant is now defined as what NetBox will actually store, so the existing
  guard starts working for the first time. **Deliberately not `.strip()` on
  both sides**: that papers over any other normalisation NetBox applies —
  exactly the class the record exists to reveal — and would stop a genuine
  whitespace-only template edit ever deploying. Fix the measured discrepancy;
  let the record surface the next.
- **Six churn sources, and three of them are two representations of one fact
  compared as two facts** (enum vs reference, `role`/`device_role`,
  `template_code`'s newline). The record did not find six unrelated bugs — it
  found **one kind of mistake six times**, and could only find them by writing
  down what was actually sent. Device noise is now measured to zero: a
  ten-device sync produced **no device entries at all**.
- **A RECORDER WHOSE SUCCESS CONDITION IS SILENCE MUST REPORT ITS OWN
  FAILURES** (§21). `_write_json_atomic` logs at ERROR and returns `False`;
  `record_modified` **ignored the return**, so a record that could not be
  written reported nothing while `nmas-netbox-modified` printed
  `0 modifications` — which is how *"the noise is gone"* and *"the recorder
  stopped"* became indistinguishable. Failures are counted and printed
  **beside every count**, with the count named a **floor, not a total**. In
  memory, like `redact.health()`, for the same reason: *a record that cannot
  be written cannot write down that it could not be written* — lost on
  restart, stated rather than hidden.
- **An unreadable modification record would have been ERASED by the next
  write.** `_load_modified()` turns an unreadable file into `{}`, and
  appending one entry to that and writing it back replaces the whole history:
  **the settings-file erasure verbatim**, one store over. `absent` is fine and
  still writes; `unreadable` now refuses, counts, and leaves the damaged file
  alone. Absent and unreadable are different facts, for the third time in this
  project.
- **C1 was a misreading, and the shape is the finding.** *"`nmas-deploy` says
  already at `da4d479` while `32329bf` exists on origin"* — measured,
  `32329bf` is an **ancestor** of `da4d479`, so the tip contains it and the
  tool was right. C1 had been recorded as a defect an hour earlier and the
  next confusing output was attributed to it. **A register makes a finding
  easier to find, and therefore easier to reach for** — *a pattern that has
  been right four times is exactly the one to distrust on the fifth*, and a
  written-down finding is a pattern with a citation. The first report remains
  unexplained and needs one measurement, not a rewrite.
- **Two opposite states produce "the field is canonical and there is no
  entry"**: a sync ran and the recorder was silent, or **no sync ran and the
  edit never saved**. NetBox's own `last_updated` separates them and nothing
  else has to be believed. *Ask the cheapest question that halves the space,
  not the most likely explanation* — which has been wrong three times running
  here by the other route.
- **THE COMPARISON WAS NOT EATING IT, measured** (§22). *A fix for noise that
  suppresses signal* was the right hypothesis to raise — three of the six
  churn fixes **are** normalisations — so it was tested rather than argued:
  `changed_fields()` records `"… 10.255.1.11 TEST"` → `"… 10.255.1.11"`
  correctly, `_comparable` strips nothing from a string, and driving the
  **whole** path (`_upsert_device` → `_nb_patch` → the record) with a spy
  session produces the entry. **The repository's code records it**, so the
  remaining causes are about *which code ran and whether it could write*, not
  about what it compared.
- **`health()` counts in memory and the recorder runs inside the app**, while
  `nmas-netbox-modified` is a different process — so the health line the CLI
  printed was about the CLI and would read `0 writes failed` however badly the
  app was failing. *The reassuring zero, one level up*: the check built to stop
  **silence** meaning two things was itself silent about whose silence it
  reported. It now says so in its own output and names the channel that does
  cross processes — the app log, at ERROR from both `_write_json_atomic` and
  `record_modified`.
- **Three discriminators, cheapest first, and the expensive one is third.**
  (1) *Is the app running the deployed code?* — a long-running Flask process
  holds its modules, so `ps -o lstart=` against the deploy time can end the
  investigation outright. (2) *Did the write fail?* — the app log,
  `logs/device_manager.log` (**not** `journalctl -u nmas`; see below), since `--sanitise` and `--apply` run from a shell create
  `0600` owned by whoever ran them. (3) *Only then, the comparison.* Two
  rounds have now gone to *a pattern that has been right before*, and both
  times the cheap question was available from the first report.
- **THE RECORDER DID NOT MISS IT; THE POSITIVE CONTROL PASSED AND WAS READ
  AS FAILING** (§23). `data/netbox_modified.json` held `r1 comments … TEST →
  …` at `06:34:40Z`, with the file's mtime 0.18 s after NetBox's
  `last_updated`, listed by the reader as the last of 44 entries. C3 is
  closed, and the syncs that recorded nothing since then count as evidence
  again. **The misreading was the check lacking its own positive control, not
  the recorder**: "no entry" was accepted without anything showing that the
  reading method could see one. Re-run on `bbf3d8e`: record T0, hand-patch
  r1, sync. **One** new entry, r1's, after T0, and 0 recorder errors in
  550,725 log lines. The deliberate change appeared and nothing else did, so
  both sides were proven by one sync. **The cheapest discriminator
  was not on the list**: `ls -l` on the record beside NetBox's timestamp,
  cheaper than all three.
- **`journalctl -u nmas` is empty BY CONSTRUCTION on the deployment host.**
  The unit is `flask-app.service`, and even its journal carries only the
  start-up banner, because module loggers go to the root file handler. *(First
  recorded as "no unit, PPID 1": PPID 1 is systemd. That was inferred from a
  process listing instead of read from `systemctl`, and corrected the same
  day.)* So the channel named as *the one that crosses processes* printed
  `-- No entries --`, which is what "no failures" looks like, and a test asserting
  `"journalctl" in src` pinned it as correct. The app's root handler writes
  `logs/device_manager.log`; `nmas-netbox-modified` now **reads** it and
  prints a count with its denominator, reporting `UNPROVEN` when there is
  no log. **Name a channel only after reading something from it.**
  [docs/OPEN_FINDINGS.md](docs/OPEN_FINDINGS.md) C5.
- **A FINDING THAT SOMETHING IS ABSENT IS ONLY VALID IF THE THING THAT
  WOULD HOLD IT WAS THE THING CHECKED.** Twice on 2026-09-25. *"The recorder
  missed the write"*: the record held the entry, and the reading of it was
  never shown able to see one. *"There is no service unit"*: a process
  listing was checked, and systemd, which holds units, was not. Each absence
  was real in what was looked at and false about what was claimed. Before
  writing "X is not there", name the store that would hold X, and show the
  check can find an X that **is** there (a positive control). Same family as
  *a lookup that misses is a fact about the query*, stated for findings
  rather than code.
- **A seed that never overwrites needs something that COMPARES, or its
  copies go stale silently** (OPEN_FINDINGS C6). `nmas-seed-status` classifies
  every list's templates as current / stale / edited / edited_and_stale from
  the two git histories, and **"edited" is never a defect**: a tool that
  reports a deliberate change as a problem gets ignored. It also compares
  NMAS's code-defined NetBox specs with NetBox. Its first live run classified
  every file wrongly while its tests passed. The tests used absolute paths
  and the deployment passed a relative one, which `git -C` then doubled. A
  fixture that could not exhibit the case, again.
- **A timing difference was attributed to the network, and it was the
  device's clock.** s4's heartbeats arrived 391 s apart for a 300 s timer,
  and "91 s of jitter" moved the alert window. The operator asked what else
  it could be. Measured over five intervals, s4's own clock says 300.0 s
  every time while arrivals are 391–404 s apart: the vIOS clock runs at
  ~75% speed, while r2 (C8000v) is exact. A reason that makes a number safe
  is not therefore the true reason, and a rule tuned for jitter would have
  been wrong for a slow clock. One 750 s window would have alerted on a
  single missed s4 heartbeat. Windows are now per dialect, from measured
  real intervals, and an unmeasured dialect is refused.
- **A rate measured on one device is a fact about that device.** "vIOS runs
  at 75%" was s4, generalised to a platform. Measured over the fleet, the
  four switches run at 0.94, 0.94, 0.75 and 0.55–0.61 (s3 varies), and the
  per-platform window failed three of four, in both directions. The
  heartbeat window is now measured **per device**. A device with no
  measurement gets a window labelled **provisional** in the rule itself,
  and a moved rate is a named state (`STALE RATE`) from an hourly check
  that `job_health` watches. The same shape as the 60 s slack it replaced,
  caught within an hour this time rather than a day.
- **Never pass document text through a shell heredoc; write it with a file
  tool.** 2026-09-25: an edit sent a runbook section to `python3` through a
  heredoc delimited by `EOF`, and the section contained its own `EOF` lines
  (the runbook's own heredocs). The shell ended the heredoc early and ran
  the rest of the runbook, as shell, on the laptop. The prose's backticks
  became command substitutions, and a code fence (three backticks, then
  `bash`) started an interactive shell that blocked. It touched nothing,
  measured afterwards: the root steps failed on permissions, and the
  blocking shell sat BEFORE the cron write and the `ssh`/`rsync` test lines.
  That was luck of ordering, not design. Same family as *stop a process by
  identity*: text a tool treats as a boundary appears inside the payload.
  The runbook itself now uses `printf` plus a `cat` of each result. Every
  line expands `$DEST`, and an unset `$DEST` in a fresh root shell would
  otherwise write `find /hourly … -delete` into cron without an error.
- **A runbook line that depends on shell state does something different when
  followed slightly differently** (the operator's generalisation,
  2026-09-25). A variable set three blocks earlier, a `cd`, a sourced env
  file, a second terminal: each is state the reader may not have, and the
  line runs anyway, with no error, doing something else. The form that
  holds up: **write, then show what was written** (`printf … > f` then
  `cat f`), so the expanded value is on screen before anything reads it. A
  line whose result cannot be shown should refuse on missing state instead
  (`: "${DEST:?set DEST first}"`).
- **Two settings of one control are not two layers when one supersedes the
  other.** A key's `command=` and sshd's `ForceCommand` both force rrsync,
  and the config's wins, so exactly one is in force. The pair covers two
  different ways of LOSING the restriction, not a stronger restriction. So
  they must be identical, and the inert one is untestable until the other
  is removed. Say which case it is. *Belt and braces* is the natural
  reading, and it is wrong (docs/NETBOX_BACKUP.md 2c).
- **A job that fails into a journal nobody reads has not been reported**
  (C14). `clab-sync` refused correctly 72 times in a row, because its
  helper was on the login PATH and not systemd's, while r6's startup config
  went a day stale. **Resolve helpers beside the script, never through
  PATH**, and deploy scripts as symlinks to the repository, so there is one
  copy. `modules/job_health.py` reads each declared job's journal. It must
  never trust `Result` alone: systemd reports `Result=success` for a unit
  that does not exist. The sanitiser's commit also named a missing git
  identity "NOT VERSIONED" and prescribed `git init`. The committer's
  identity now rides on every commit (`-c`), and a failure in an existing
  repository reports git's own reason.
- **A device leaves management through `nmas-retire`, never the Delete
  button** (C11). Delete removes the CSV row and nothing else, and measured
  on r5 that left it bound to its template, in the sync map with a false
  INCOMPLETE reason, heartbeat-alerting, and with its only stored credential
  destroyed. Retire does the whole exit and **states what it does not do**
  (NetBox kept, Oxidized polling, startup frozen and declared unmapped),
  because each of those is correct and reads as an omission unless it is
  named. The credential check is a **refusal, not a step**: a sequence whose
  first step can be skipped will be skipped.
- **STOP A PROCESS BY IDENTITY, NEVER BY PATTERN.** `pkill -f "<pattern>"`
  killed the shell running it three times: a heredoc edit lost
  (`NSOT_WRITEUP_NOTES.md`), a file copy lost, and a probe teardown stopped
  half way (2026-09-25). A pattern naming a process is also text in whatever
  command contains it, so a cleverer pattern is not the fix. Not matching is.
  Tunnels go through `scripts/nmas-lab-tunnel` (an ssh control master closed
  by its socket), a service through its unit's `MainPID`, and a background
  job through the PID recorded at start. `tests/test_no_pattern_kill.py`
  refuses `pkill`, `killall` and `pgrep -f` in `scripts/`, `deploy/` and doc
  code blocks. It found §22's `pgrep -f 'python.*app\.py' | head -1`, which
  had avoided matching itself only because the backslash in its own pattern
  broke the match.
- **A TOOL'S OUTPUT IS A CLAIM, and it needs the same scrutiny as the thing
  it describes.** The C3 arc: the recorder was declared **verified FAILING**
  (`1b9b4d3`), the register and plan were rewritten around a live defect,
  and it was closed as a misreading (`bbf3d8e`). The record had held the
  06:34:40Z entry the whole time, and `nmas-netbox-modified` printed it as
  the last of 44 lines. The mechanism was never broken. What failed was the
  operator's reading of the diagnostic's output, and that false positive was
  trusted enough to declare a defect and cost a round of work. The lesson is
  not "check twice". It is the rule about naming both operands, applied to
  the **reader** rather than the writer: a guard reports the comparison it
  made, and a reader of a report asserts what the report was shown able to
  contain (T0, then the entry after T0), never what it did not visibly
  say. The same day, the register itself was read at a head four commits
  stale: *a stale read of a maintained file is indistinguishable from a stale
  file.*
- **Removing the config you can SEE does not remove the one you cannot**
  (P.6, 2026-09-26). The ZTP probe's configless variant removed vrnetlab's
  day-0 ISO. But the image's install step had saved a startup config into
  the overlay disk the launch script boots (`do wr`; r6's first golden
  carries two lines only that config writes). So M1 would have answered
  "the platform does not discover" about the INSTRUMENT. Found by reading
  before the first boot, and caught a second time by executing the
  constructor on a fake root: that test disproved my own account of which
  file sorts first. A probe that removes a precondition needs a row that
  checks the precondition is gone ON THE DEVICE (P-M0, `show
  startup-config`) before any later row means anything.
- **A configless IOS-XE device phones Cisco before it finds anything
  local** (P.6 M1 re-run, 2026-09-26; D4, decided). Given DNS and a route
  out, PnP resolved `devicehelper.cisco.com` and sent a HELLO carrying its
  UDI (product ID and serial). That is a property of ZTP, not of this lab: a
  deployment that has not thought about it announces its inventory to a
  third party during onboarding. So a ZTP reservation carries no route and no
  resolver (options 3, 6, 33, 121), and that is a CHECK over the EFFECTIVE
  options (global, shared-network, subnet, reservation), not a fact about
  subnet 255 that holds because nobody has touched it. **M3 sharpened it:
  withholding stops the CALL, not the ATTEMPT.** With no resolver the node
  broadcast `A? tools.cisco.com` to `255.255.255.255:53` (8 queries, 0
  replies), so the segment sees it reach for Cisco, and anything answering
  broadcast DNS there would hand it a resolver with no DHCP option at all.
  So D4 has a second condition: nothing on the ZTP segment answers DNS. The
  node's parameter request list asks for 3, 6 and 33, which is the measured
  reason D4 is a check and not a default.
- **A CONFINED ROOT PROCESS IS NOT ROOT FOR FILE PERMISSIONS** (the
  operator, P.6 D1, 2026-09-26). `sudo kea-dhcp4 -t` could not read a
  `0640 dmarchak:_kea` fragment: Kea's AppArmor profile withholds
  `dac_override` and `dac_read_search`, so the process is held to the mode
  bits, and root is neither the owner nor in the group. The profile DID
  allow the path (`/etc/kea/**`), which is why it would have read as a path
  problem indefinitely. Any design assuming "root can read it" about a
  service under AppArmor is wrong. The kernel log carries
  `apparmor="DENIED" operation="capable"`, and the same log held an older
  instance nobody had read (`/tmp/kea-broken.conf`, 2026-09-25). **Ask which
  reader a mode is for, and list every one**: the running daemon as `_kea`
  could read `0640`; only the offline check could not. So `0640` would have
  worked in production and made the config unvalidatable before a restart.
  `0644` was chosen because the file is inventory, not secrets. The recipe
  is in `docs/DEPLOY_LINUX.md` so a rebuild reproduces it.
- **A hash of the file you staged is not a hash of the file that runs**
  (P.6 M3's first run, 2026-09-27). The re-staged launch script was
  reported at the right hash, and the container bound a different state of
  that path: `/launch.py` inside the container hashed to the OLD patcher's
  output, with an mtime from before the new patcher arrived. A whole boot
  measured the old instrument, and its failure read at first as IOS-XE
  writing its own config. Check at the CONSUMER (`docker exec … sha256sum
  /launch.py`), the same rule as *a check of the code is not a check of the
  install*. And an instrument that speaks only when it acts cannot tell
  "absent" from "nothing to do": the patch now names its disk in every case.
- **A test that builds its own socket cannot see the one the deployment
  hands over** (P.6 M4, 2026-09-27). systemd's `ListenDatagram=69` is a
  dual-stack IPv6 socket, so an IPv4 device arrived as `::ffff:10.255.0.50`
  in a 4-tuple. It matched no reservation (refused as `?`), and the reply
  crashed on it, so the device heard silence. Every protocol test used
  AF_INET, and under the old code 24 of them still pass. The same seam as a
  staged file versus the running file: exercise the object the consumer
  actually gets (`TestTheSocketSystemdActuallyHandsOver`). **The crash hid a
  second defect**: a fix to the reply alone would have sent a correctly
  transmitted WRONG refusal.
- **A ZTP device does not retry for ever** (P.6 M4, the operator's reading,
  2026-09-27). IOS-XE 17.6 AutoInstall gave up after about 2.5 minutes and
  nine unanswered requests (`script execution not successful`), so a
  responder that is down, crashing or firewalled in that window FAILS an
  onboarding rather than delaying it, and the device needs a reload. Hence
  the pending stage `asked_not_served` and the `nmas-ztp-responder`
  job-health row. **Input ends discovery**: `en` alone stopped PnP, and the
  node had said so, so a watched console is TOUCHED by nothing.
- **A ZTP device has no SSH key unless the bootstrap makes one** (P.6 M4,
  2026-09-27). The C8000v was left out of `GENERATES_SSH_KEY` because
  vrnetlab's day-0 config generates its key, and ZTP removes that day-0
  config. M4's node applied its config and refused TCP 22. The
  `ztp` render now generates the key (the plan and the re-render alike),
  and every other render is unchanged. Third proxy population of the stage:
  a rule keyed on the PLATFORM whose real subject was the deployment.
- **A diagnosis drawn and then overwritten is a diagnosis nobody reads** (M4).
  `onboardVerify()` rendered the failure and its next line reloaded the
  same element, and phase 2 logged nothing, so the 409's reason existed for
  a moment on one screen. The operator had to infer the cause from another
  panel, and inferred the wrong one.
- **A RULE KEYED ON THE PLATFORM WHEN IT WAS REALLY ABOUT THE DEPLOYMENT**
  (the operator's name for it, P.6, 2026-09-27). Each was true of every
  device that existed when it was written, and each becomes false the first
  time a device arrives by a different route. ZTP is the first route to
  break all of them. The proxy-population rule, with "platform" standing in
  for "deployment":
  - `RESERVED_INTERFACES` refuses Gi1 for `cisco_iosxe` because vrnetlab owns
    it: false on a Proxmox VM or hardware (P6_ZTP_PROBE section 11, Q2);
  - `clab_target_for()` resolves an unknown lab to rcn-lab1's paths, because
    every device was a containerlab device (C50);
  - the generator skipped the SSH key for `cisco_iosxe` because "vrnetlab's
    own bootstrap config sets it up", and ZTP removes exactly that config
    (M4; fixed for `ztp`);
  - `VRNETLAB_INJECTS_USER = {"cisco_iosxe"}` gives a ZTP render the weaker
    `password 0` form, while nothing injects a user on a configless node
    (C52, found by the survey the pattern suggested).
  **Where to look for the next: anywhere the code asks WHAT a device is to
  answer HOW it got here.** Grepping the justifications for "vrnetlab" found
  the fourth in minutes. A member handled correctly shows the other shape:
  RW-community removal treats "nothing to remove" as success, because a real
  device may not arrive with one.
- **A VALUE THAT NAMES THE DANGER IS NOT A CHECK UNTIL SOMETHING READS IT**
  (the operator's wording, P.6 M4, 2026-09-27). The same shape as C50's
  `named: False`, which `clab_target_for()` computes and nothing reads.
  Phase 2 answered 200 and promoted a device whose startup config was "not
  present": one reload from a configless node, with NMAS holding a
  credential for an account that no longer existed. `rotate()` had returned
  `rotated_persistence_not_attempted`, the rotation record said the same,
  and job health read it as `not_safe_to_reboot`. Phase 2 judged by
  `rotated` and read none of it. Nothing on the path had ever saved a device
  (no `write memory` anywhere). Phase 2 now saves and reads back the
  device's own startup config before promotion, for every source. The
  information existed in two places, and the consumer looked at a third.
  **Measured on the fleet the same day (C53):** eight of nine devices boot
  their running credential. `s1` boots the credential the terminal exposed
  (B13), because its NVRAM was never saved after the rotation that retired
  it: B15 fixed the boot FILE, and a guest reload boots NVRAM. After the
  operator's `nmas-persist-native s1`, **nine of nine carry**, the first
  time by measurement. The CLI chain's first stage now saves on the device,
  and `nmas-startup-check` (hourly, read-only) keeps asking, because the
  answer changes silently.
- **A check's claim is scoped to the population it planted** (C55, C56, the
  operator's framing, 2026-09-27). B11's "no GET returns a secret" planted
  two values and swept the argument-free GETs, so it was true of a
  population it had defined itself. Planted over a SURVEY of every store
  and every GET with arguments filled, its first run found five routes: the
  collector config (C55, fixed) and four more (C56). Its population is now
  tied to the storage checker's secret classes, so a new store fails the
  sweep until it is planted.
- **A tool that DESCRIBES a secret defeats redaction that matches its
  SYNTAX** (C55, C56, measured 2026-09-27). Positional redaction masks
  `snmp-server community <X>`; it does not mask `SNMP community (RW):  <X>`
  or `name = <value>`, and value redaction knows only the stores in its
  table. `get_monitoring_config` and `read_variables` handed the model
  stored values that way. `test_no_agent_tool_leaks_a_stored_secret.py`
  drives EVERY tool through the real `run_chat()` loop with a fake provider
  and searches what the provider would receive. The boundary test before it
  used hand-written output shapes, all in config syntax, so it could not
  exhibit the case. Its first control passed wrongly, served by the
  process-wide tool-result cache, which each drive now clears.
- **Constrain the shape; do not only enumerate the instances** (the
  operator's naming, 2026-09-27). A survey finds what someone can see; a
  rule that every member of a CLASS must satisfy finds what nobody saw.
  Twice now the rule found more than the survey: the route gate table
  (every mutating endpoint declared, P.3) and C8's handler rule (every
  handler around a NetBox write records, re-raises, retries or refuses:
  the survey listed twenty, the rule found nine more). Reach for the
  constraint when the population can grow.
- **A pattern earns a member by measurement, not by resemblance** (the
  operator, 2026-09-27). C54 (a job-health row for a device that has left) was
  proposed to widen to the heartbeat check, whose row read `failing` after
  P.6's teardown. Measured, the heartbeat generator reconciles from NetBox,
  and its row was STALE: correct failures from checks run while the probe
  existed. A hand-started run read `ok`. The member was withdrawn, and the
  real gap was a teardown step (re-run the checks the probe made fail),
  because a correct probe-caused failure reads like a live one until the next
  tick.
- **Moving what a screen draws to the server moves the dropped-key failure
  with it** (7.1, 2026-09-27). Once `/deploy/plan` built a preview and one
  renderer drew it, the wizard stopped reading `commands` and `attribution`
  at all. The adapter that builds the preview became the step that could
  drop a key. A check reading only the browser's code would have had to
  exempt every raw key as "drawn through the preview", and that exemption
  holds whether the adapter carried the key or dropped it. So the
  payload-to-render check reads the adapter's
  source too, and a control that nulls the attribution in the adapter fails
  the anchor. Wherever a transformation sits between a payload and its
  renderer, the check has to cover the transformation.
- **A trigger that fires on an incident samples the moment a person
  intervened** (8.7, the operator's case, 2026-09-27). A scheduled check
  looks at a device at an arbitrary time; an alert-triggered one looks at it
  when the alert fired, and the alert is often caused by somebody's fix. So
  the faster trigger that makes a READ better makes an ACTION worse, and
  "seconds instead of 30 minutes" moves an automated revert from after the
  repair into the middle of it. Before wiring an action to an event, ask what
  else the event correlates with.
- **A first word is not a command** (C61, 2026-09-27). The agent's read-only
  allowlist checked the verb, and an IOS output modifier makes a `show`
  WRITE: `| redirect tftp://<host>/x` sends the whole config to another host,
  and the device sends it, so the tool's redaction never sees the bytes.
  B13's shape: a secret leaving through a path the gate did not examine.
  Both halves are allowlists now, verb and modifier. **Measured the same day:
  only the first `|` is a modifier on both platforms**, and the rest is the
  filter's regex, so the first parse (every `|` a modifier) refused the
  pipeline's own read and was corrected. The sweep for the shape
  found one more of the family (C63): the deploy's dangerous check is a list
  of forms, and misses `no router rip` on a fleet running RIP.
- **A CHECK IS ONLY AS GOOD AS THE STATE ITS FIXTURE CAN REACH** (the
  operator's rule, 2026-09-27). Three times in one day the check's own INPUT
  was the defect:
  - the RIP sample started at the RIP header;
  - the BGP summary written from memory had eight columns;
  - the payload check's `/deploy/apply` provider planned without the
    authorisation it applied with, so its "deployed row" was always a
    refusal. The not-drawn list rose 99 to 106 the moment it produced a real
    one: seven fields nobody had examined.

  A fixture that can produce only one outcome tests nothing about the other.
  The detection method is "build the test input from the route", pointed at
  the fixture. It is now mechanical: every empty collection in a provider's
  real payload is declared as strings or records (`EMPTY_IN_FIXTURE`, C72),
  and its first run caught a new field the moment it appeared. Its first
  reach, a real residue plan, found a defect at once (C73): residue drawn
  with no section.
- **When two places answer the same question about a device, one of them is
  wrong, and you will not know which until both meet real output** (the
  operator's, 2026-09-27). Three drift checkers, two golden enumerators, and
  now two BGP readers: topology's was right all along, and the deploy's,
  the one deciding whether to roll back, was wrong on the same output (C64,
  C69). The correct implementation already existed; nobody had to write it,
  only find it. The permanent fix is a test that fails when a second one
  appears, not a comment asking people to reuse the first.
- **A fixture that starts where the parser is supposed to end has assumed
  the thing under test** (the operator's wording, 2026-09-27). The RIP
  sample began at `Routing Protocol is "rip"`, so it could not exhibit a
  parser that never reaches that header (C65). Its test asserted "a
  RIP-only device is no longer invisible" and passed while every RIP device
  read 0. It is the second time in a day: the BGP sample from memory had
  eight columns.
- **A fixture sometimes has to build a state the live fleet does not
  currently offer. The rule then is that the PIECES are real even when the
  arrangement is not** (the operator, 2026-09-27). C74's row rule needed a
  junk line INSIDE a BGP table, and no device prints one there. The test
  took r3's own junk line, the one that sits between the IPv4 and IPv6
  tables, and placed it inside one. Nothing in the input was typed from
  memory, and the case now exists. Likewise, each golden-state failure is
  a minimal edit of a real capture (one peer down, one neighbour stuck).
  The pieces cannot be invented, because an invented piece is how C64-C67
  passed. Moving them is allowed, since otherwise every case the live
  fleet happens not to be in right now goes untested.
- **A parser written against imagined output passes every test written the
  same way** (C64-C67, the operator's sweep of `pipeline.py`, 2026-09-27).
  Four readers of device text were wrong on the real fleet, and the suite
  was green: the BGP pattern expects eight columns where IOS prints ten, and
  the RIP parser reads the `"application"` pseudo-protocol's empty table,
  which nobody writing `show ip protocols` from memory includes. The route
  count reads the Networks column. The canary accepts any "up", and Loopback0
  is always up. The deploy's verify therefore compared 0 with 0 on four
  devices in every recorded deploy. A parser's test is built from a capture
  (`tests/fixtures/operational/`), never a sample typed into the test (D4's
  rule, now with a directory). And a deploy receipt that records "verified"
  is only as true as the verify it records (C60 before C64-C67 would store
  a false claim).
- **Some controls exist to make behaviour visible, not to prevent it** (8.8,
  the operator's distinction, 2026-09-27). A written reason required when
  the second reading warns does not stop anyone. It makes the pattern
  legible to a person who can act on it, so "ok" typed thirty times is the
  finding, not a defeat of the control. Its measure is the AGGREGATE, per
  person and per device, drawn where people look. It stands on the
  attribution work (D10, P.3), which now serves accountability as well as
  security.
- **A claim names what it RESTS ON** (the operator, 2026-09-27). r3's and r4's
  only BGP peer is r5, retired from management: no credential, no capture, no
  heartbeat. "BGP established" reads as a two-sided fact, and the tool
  observes only one side. So the golden state names every routing peer that
  is not an address of a managed device, and every tag carries a limits
  line, the census's precedent: the tool sees what the managed devices
  report about themselves. The live claim reads "configured and working,
  resting on 4 routing peer(s) outside management".
- **Listing what a claim depends on is a way of finding defects, not only
  a way of being honest about limits** (the operator, 2026-09-27). C74
  was found by asking what "configured and working" rested on, one input
  at a time. BGP rested on `show ip bgp summary`, and that command lists
  IPv4 only, while r3's and r4's intent declares an IPv6 peer. So the
  claim had been judged on half the sessions it named, and no test or
  symptom pointed there. Each listed dependency is a question about the
  code: which reader supplies it, and what does that reader leave out? Ask
  those questions before writing the limits line.
- **A preview's gates part is that method applied to a screen** (7.1's
  restore retrofit, 2026-09-27). Drawing each gate by name meant stating
  what each check establishes, and stating it found four defects before
  C70 ran:
  - **C75.** A restore could CHANGE a credential the device holds. The
    deploy's rule had never been applied to restore, and a baseline
    predating a rotation pushed the old `username` line. The Baselines
    panel's acknowledgement let it through.
  - **C76.** The merge program compared lines as TEXT. Intent adding
    ` ipv6 ospf 1 area 0` to an interface on a device whose other
    interfaces had it produced an EMPTY program on deploy and restore
    alike. `classify_diff()`, in the same function, was chain-aware, so
    the preview named a line the program did not send.
  - **C77.** Both previews returned stored config verbatim.
  - **C78.** The gate "device unchanged since capture: re-read at apply"
    re-read the STORED capture, never the device. This session wrote that
    sentence into the deploy adapter, and the deploy wizard had said it for
    months.

  A gate drawn by name is a claim with a name. Before drawing one, find
  the line of code that makes it true.
- **A baseline is a record of a moment, and moments contain credentials:
  any re-apply is a time machine for secrets as well as for configuration**
  (the operator, 2026-09-27; C75 was LIVE). The newest baseline predates
  s1's rotation. From the UI, a baseline could only be re-applied to the
  whole fleet (C80), so "run the restore once, deliberately" (C70) would
  have pushed the credential B13 exposed back onto s1. It would have gone
  past a warning that could be acknowledged. Measured by hash on the host,
  all eleven baselines carry a stale account credential for s1, and seven
  carry the exposed one. **The path that had never run was more dangerous
  than anyone knew**, which is the strongest argument for the rule that
  made us run it. C75 closes rewriting. Adding back is still open (C79): a
  removed account, or an old community after its first rotation, returns as
  an ADDED line.
- **C76 is the Phase 3c promise broken in the quiet direction.** "What the
  operator confirms is what is sent" was written after one line was
  confirmed and eighty-three were sent. C76 is its mirror: the preview
  listed a line the program never sent, because a line counted as present
  if the same text sat under ANY section. Sending less than shown is the
  same promise broken, and only the loud direction had been looked for.
  When a guarantee is written after a failure, test it in both directions.
- **A procedure written against an assumed control** (the operator's
  name for it, 2026-09-27, C82). C70's step 2 said "Save r2", and no
  per-device golden capture exists: not on the device row, not on Manage,
  not as a curl-only route. It is the same shape as 7.4 listing "adopt" as
  the home for a capability that did not exist. The break-glass runbook
  assumes the same missing control ("captured into intent", and extraction
  reads the golden). Before running a written procedure, resolve each step
  to a control that exists: a route in `url_map` and a caller a person can
  reach. A step with neither is a finding, not a wording problem. Asking the
  question found three more things in one pass:
  - the only per-device capture, a drift item's approval, committed as
    `ai-agent` (C81, fixed);
  - every golden commit's subject claims "baseline", tagged or not (C83);
  - the restore's result is only a toast (C84).
- **A GUI that needs a terminal to finish an operation has delivered a
  TRIGGER, not the capability** (the operator, 2026-09-27, stopping C70).
  Restoring one device needed four workarounds: a console call, a
  fleet-wide Save All, the network tab and an SSH session. In a tool whose
  purpose is to be the single control point, the workarounds ARE the
  finding, so the run waits for the interface rather than being completed
  around it. The survey it prompted: of the 41 routes that change a device
  or the record, **none has a screen where its result can be read again
  later**. 16 draw it until the window closes, 17 only in a toast, and 8
  have no GUI. The payload-to-render check could not see this, because it
  checks the responses renderers draw and not the responses nobody draws
  (`/jobs/health`'s original shape). An operation is whole when a person
  can prepare, preview, confirm, read the result and find the record again,
  all from the interface. 7.1 is reshaped to that
  ([NSOT_STAGE7_PLAN.md](docs/NSOT_STAGE7_PLAN.md), "7.1 reshaped").
- **A check about drawn fields sees nothing its population or its fixture
  does not reach** (the operator's rule, 2026-09-27, made precise by
  measuring C85). C8 was fixed so that a partial NetBox import could not
  read as clean. The fix landed in the DATA (`write_failures`, `partial`
  and `complete` in the stored summary) and never reached the SCREEN: the
  sync card read `failed` and drew green. It was first written here as
  "a check that verifies drawn fields cannot see a field nobody draws".
  **That is true of a response with no declared renderer**, which is the
  result survey's population, and
  `test_results_are_drawn.py` exists for it. **It is not why C85 was
  missed.** The payload check's forward direction names a carried field
  nobody reads. It never saw C8's fields because its `GET /netbox/status`
  fixture had no stored import: `status` was empty and declared "NetBox is
  not configured in the fixture" (C72's class). Given a stored partial
  import, it named five fields at once, and one of them was a second C85:
  the import's own refusals (`notes`), collected "because a refusal nobody
  reads is the same as no refusal", and drawn nowhere. A positive control
  (a planted key) is what showed the first version examined nothing. That
  version was a duplicate dict key, silently dropped (C90).
  `test_results_are_drawn.py` (7.1 step 1) asks the complementary question
  of a population that is the gate table itself: every action that changes
  a device or the record shows its result where it can be read again. A
  toast is enough only when the action changes nothing durable and has no
  operands worth re-reading, and every gated kind fails that by
  construction. **Colour is part of the
  result.** A green toast on a partial success is a false statement in a
  different medium, and three places were making one: Save All's toast,
  the NetBox sync card, and onboarding's Create. With C83 (every golden
  commit's subject says "baseline"), that is the word or the colour
  asserting more than the operation earned.
- **A duplicate key in a dict literal silently keeps the later value, and
  that can disable a security control with no error, no warning and a green
  suite** (C90, the operator's emphasis, 2026-09-27). A new `RENDERS` entry
  was dropped behind an older one, and 22 tests passed about a route they
  were not examining. The same slip in `route_gates.GATES` would silently
  drop a gate. The failure is invisible at every stage a person looks: the
  source reads correctly, the tests pass, and the runtime behaves
  consistently. Only a scan finds it, so `test_no_duplicate_dict_keys.py`
  scans every dict literal with constant keys in the program, its scripts
  and its tests (4,530), with a control that catches the exact shape. When
  a language behaviour can remove a control without a trace, a mechanical
  scan is the only review that works.
- **A baseline asserts the network is at its committed INTENT, and every
  capture path now says whether it is** (C89 (c) and (d), decided
  2026-09-27). `save_golden()` is the one place every capture commits
  (Save All, deploy, restore, an approval, the CLI), so it computes each
  capture against committed intent with the deploy plan's own comparison
  (`intent_match`). It writes a computed `Intent-Match:` trailer on every
  golden commit, and it takes a baseline only with coverage AND every
  capture matching. Against the golden the comparison would be empty by
  construction, because the capture becomes the golden. **Writing it found
  C91**: coverage was checked only when nothing changed, so a Save All that
  committed took a baseline with a device skipped. Six tests had pinned
  that, by seeding Save All baselines with no inventory size.
- **Capture is an operation, and Save All is its fleet form** (C82, C89,
  7.1 step 4). `POST /golden/capture/preview` reads each device now and
  returns only a masked preview: the diff against its golden, and where it
  departs from committed intent. `POST /golden/capture/apply` re-reads each
  confirmed device, refuses one whose capture hash moved, and commits once
  as the verified person (`Source: capture`, or `save_all` for the fleet).
  `/golden_configs/save_all`, one click to golden, baseline and remote, is
  gone. One client, `static/js/nmas_capture.js`, serves the Device page's
  Capture button and Save All.
- **A test that models the assembled page must model every script the page
  loads.** `tests/js_source.with_loaded_scripts` included only the page's
  generated scripts, so a component loaded from `static/js/nmas_*.js` was
  invisible to every renderer test reading the assembled page (found wiring
  step 4). It includes them now; Bootstrap, vendored in the same directory,
  is deliberately not matched. So the payload-to-render check's population
  had a hole exactly where the newest code lives: the check was sound and
  its input incomplete, the fixture findings' class one level up.
- **Restore is gated by `RestoreTarget.checks`, ONE list read twice**:
  `blocking_reasons` derives from it, and the preview draws it as gates.
  The list covers a stored config at the ref, printable ASCII, and
  credential unchanged. The refusal says "re-apply <ref> to", never
  "deploy to". When both sides carry the same credential form, it says
  "with a different value", because the value is never printed and two
  identical strings read as no difference.
- **A population defined by the HTTP method missed a leak again** (C77, the
  B16 lesson's newest member). B11 swept every GET with every store
  planted. `/deploy/plan` and `/golden/restore/preview` are POSTs that
  compute and return stored config, and both returned a planted community,
  as residue and as a line the program adds. `outbound.mask_payload()`
  masks the response AFTER every hash is computed from the truthful
  program, so the confirm is still bound to what is sent. A masked plan
  driven into the apply is accepted, and a wrong hash is refused. The sweep
  that would find the next one (every `not_device` POST) is open in the
  register.
- **"Configured" and "configured and working" are different claims, and a
  baseline states which it makes** (E7, 2026-09-27). A baseline records
  configuration, so a broken moment and a good one read the same. A golden
  state is a baseline whose tag carries the operational snapshot, earned only
  when every protocol each device's intent declares is up. Choosing the
  evidence was a measurement. For RIPng, "learned a route" would have called
  r1 broken: it hears s1 and installs nothing, because OSPFv3 wins on
  distance. The next-hop table was the right evidence, found before building
  rather than after a false alarm.
- Silent failure is the dominant failure mode in this stack. Every integration
  call must log and surface its failures rather than swallowing them.
- `modules/pipeline.py` is real, tested and WIRED: every deploy and every
  restore runs it. `pipeline_builder.py` generated Jenkins pipeline XML and
  went with Jenkins in P.4.

## Open findings register

**[docs/OPEN_FINDINGS.md](docs/OPEN_FINDINGS.md) is the list of things
measured, recorded and not fixed, with no line item in any stage.** Each was
written into prose beside the thing it was found next to — the right place to
explain *why* it is true and the wrong place to keep a list, because prose
accumulates invisibly and knowing what is outstanding required having been
present when each was recorded. **51 open at 2026-09-27**, counted from the rows: 45 recorded only in
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
next. The gate list is **CONFIRMED 2026-09-27**
([docs/NSOT_PLAN.md](docs/NSOT_PLAN.md), the Stage 7 dependency notes):
- B1 before 7.0, with C51 inside 7.0's harness;
- C8 before 7.1;
- C17, E4, C54 and C53's check RUNNING before 7.2;
- C50 before 7.3, as the lab map's `kind:` entry;
- C10 before 7.4;
- C2 and B3 within 7.6;
- C7 before 7.7.
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
- **The terminal: the split is COMMITTED, in 7.3** (NSOT_FEATURE_AUDIT 3a): a
  read-only lens and config mode cut, in 7.3, with the console runbook as
  break-glass. The same allowlist goes on `/run_command` and
  `bulk_execute`. It first needs C61 fixed: the allowlist checks only the
  first word, so `| redirect` writes.
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
