# Changelog

All notable changes to Agentic NMAS.

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
NSoT phases refer to [docs/NSOT_PLAN.md](NSOT_PLAN.md).

---

## [Unreleased] — Seeding: the condition was the filesystem, not the repo

The seed-commit fix was right about *what* to commit and wrong about *when*.
It fired when ``seed_templates()`` reported having copied something:

```python
copied = result.get("copied") or []
if not copied:
    return result            # nothing happened this run, so nothing to commit
```

``copied`` is ``shutil``'s answer to "did anything happen this run". The
question is the repository's: "is anything missing". On the live box the old
GET-side-effect code had already copied the library in and committed nothing,
so seeding found every file present, returned ``copied == []``, and the fix
returned early. The files stayed untracked indefinitely — the exact state the
fix existed to end.

Sixth instance of one shape in this project: the fixture builds from scratch,
the real system has a history, and the code keys off *this run* rather than
*current state*.

``_seed_and_commit()`` now reads ``git status --porcelain -uall -- templates``.
``-uall`` matters — without it git reports a wholly-untracked directory as a
single ``?? templates/`` entry rather than the files inside it.

Only **untracked** paths are staged, and ``save_templates()`` gained a
``paths=`` argument so the commit stages those specific paths instead of the
whole tree. A tracked-but-modified template is someone's in-progress edit —
seeding never overwrites, so it cannot be seeding's doing — and sweeping it
into a commit labelled "seed library" would mislabel a commit exactly the way
this function exists to prevent. Modified paths are reported and left for
their own commit.

### Fixed — a porcelain parse that ate the first character of a path

Found by the new test, not by reading. ``git status --porcelain`` pads the
status field to two characters, so a tracked-but-modified file is `` M`` with a
**leading space** — and ``git()`` strips its stdout, so the first line loses
that space and a fixed ``line[3:]`` slice takes the path one character short.
It produced ``emplates/cisco_ios/base.j2``, which would have read as a path
that simply matched nothing. Parsed by whitespace now, with the rename form
(``old -> new``) handled.

### Deferred

Seeding still runs from ``GET /templates``. A read that writes to git is how
this stayed invisible for two rounds — the library was always already on disk
by the time anyone looked, so "when was this committed?" never came up. Moving
it to ``POST /templates/seed`` is queued, not done.

---

## [Unreleased] — Three findings from `git status` on the live repo

All three were visible only on a repo that already existed. None could have been
found by a test that builds its repo from scratch.

### Fixed — a `.gitignore` rule never reached the repo it was written for

The fifth instance of one shape: *a rule added later never reaches the artifacts
that already existed.* `_ensure_gitignore()` appends what is missing — but it
only ran from `init_repo()`, and `init_repo()` only ran on a write path. The
live lab repo, created with a two-line `.gitignore`, therefore committed nine
migration backups into version control and showed `.nsot/migrated.json` as
untracked.

`ensure_repo_hygiene()` now runs from `git()` itself, so every repo this process
touches — read or write — is topped up on first use. Deliberately **not**
memoised: a memo would mean a `.gitignore` edited after first touch stayed stale
for the life of the process, which is the same bug in a smaller window. The cost
is one small file read against a subprocess spawn.

`GITIGNORE_RULES` is now a named constant, so a test can assert the repo carries
all of it rather than restating the list.

### Fixed — the rename commit did not carry the manifest

`apply_pending_renames()` staged `golden` only, and called
`clear_pending_rename()` **after** the commit. So the commit that moved
`golden/R1.cfg` → `golden/R1-CORE.cfg` recorded the move and not where the
manifest said the file now lived.

A clone or bundle restore at that commit gets a manifest still naming the old
file. `_find_golden_config_file()` then finds no entry and falls through to the
deprecated legacy header scan — which reads `golden_configs/`, a directory a
restore does not recreate. The device resolves to nothing.

The manifest is now updated before staging and `.nsot` is staged with `golden`.
A test reads `.nsot/manifest.json` out of the rename commit itself and asserts
it names the new file with `pending_rename` cleared.

`save_golden()` already staged `.nsot` and still does. `save_templates()`
deliberately does not touch the manifest — identity is not a template's
business — and a test now pins that too, so "doesn't carry it" stays a decision
rather than becoming an oversight.

### Fixed — the seeded template library was copied in but never committed

`seed_templates()` runs from the template-list route and writes files. Nothing
committed them. The first `save_templates()` afterwards — in practice the
**approval** — staged `templates` and swept the entire library into a commit
subjected `template: approve <path>`.

Two problems in one: a commit whose subject describes a single file while adding
the entire library, and an approval nobody could review as a diff, because that
diff was the library. Seeding now gets its own commit, `template: seed library (N
file(s))`, and a test asserts that an approval afterwards touches exactly
`templates/.approvals.json`.

---

## [Unreleased] — Migration hardening, found by the first real run

Three defects the test suite could not have found, because all three needed
either a repo that had already been migrated or an inventory the fixtures did
not have. Fixed before approving any template, so the first `template:` commit
lands on a repo with no known write bug.

### Fixed — a second migration run rewrote every golden config

`plan()` computed `already_migrated` and **`apply()` never read it** — the same
shape as the `assert_no_negation` stub found in 3c: a safety value that exists,
is reported, and is consumed by nothing. The computed value was also wrong on
its own terms. It tested `os.path.isdir(repo/"golden")`, and `init_repo()`
creates that directory, so it was true from the first commit onward.

Re-running was not the harmless no-op it looked like. The two stores hold the
same device in different shapes: `golden_configs/r1.cfg` carries the NMAS
header, `config_repo/r1.cfg` has it stripped. The first run `git mv`s the repo
copy and wins; the second run finds only the *other* copy, renders it, and
commits the difference. On the live lab that was `e014843` — nine files, 18
insertions, all whitespace.

Two independent fixes, because one guard is not a discipline:

- **`.nsot/migrated.json`** — a marker holding the timestamp and the commit
  sha. `apply()` reads it and refuses with `already migrated at <sha>`; the
  route answers `409`. The guard no longer infers state from directory
  contents. The marker is deliberately gitignored: "has this data directory
  been migrated" is local installation state, like `.nsot/migration-backup/`,
  and it has to carry a sha that does not exist until after the commit that
  would contain it. The migration commit and its `baseline/` tag remain the
  version-controlled record.
- **An empty commit is now impossible even with the guard removed.** Migration
  adopts `save_golden`'s discipline: `_content_changed()` before rewriting each
  golden file, `git diff --cached --name-only` (the index, not the worktree)
  before committing, and no `--allow-empty` — a test asserts the flag's absence
  in code rather than trusting the check. Deleting the marker and re-running now
  produces no commit at all.

Also: the baseline tag goes through `_unique_tag()`, so two runs in the same
second can no longer create `baseline/<ts>-migrated` twice.

### Changed — `golden_configs/` is one-directional

Keeping the old store after migration is the right design — it is the rollback
if the layout is wrong. But it was still an *input*: a second migration read
from it, and `_migrate_golden_configs()` renamed files inside it. Both are now
closed. `_collect_candidates()` stops reading the directory once the marker
exists, and the legacy in-place rename returns immediately. The single
remaining reason to touch it is `_find_golden_config_file()` step 3, reached
only when the manifest has no entry for the device, and strictly read-only.

### Fixed — the manifest had no platform for any device

Migration builds its entries from config files, and a `.cfg` cannot tell you
whether the box is a C8000v or a vIOS-L2. Every entry on the live lab carried
`"platform": ""`, so parser selection — which reads it — silently fell back to
the default dialect for all nine devices.

Platform now comes from the **inventory**, which is the only thing that knows:
the `platform` CSV column for local lists, the NetBox platform slug for NetBox
lists, both resolved through `platform_for_device()`. It is threaded in at
migration time *and* refreshed whenever the inventory changes —
`manifest.sync_platforms()` is called from `refresh_list()` for NetBox lists and
from `write_devices_csv()` for local ones. Migration-time only would have been
wrong: a platform can be corrected after the fact, and Phase 4 onboarding reads
it from the manifest.

Like `_record_renames()`, the sync touches the manifest only — no repo lock, no
commit; the next `save_golden` carries it.

### Changed — `.gitignore` is append-if-missing

`init_repo()` wrote the file only when absent, so every repo created before a
new ignore rule existed silently lacked it. `_ensure_gitignore()` appends what
is missing and is idempotent, which is also how existing repos pick up the
marker rule.

---

## [Unreleased] — NSoT Phase 3c: deploy from template

`PipelineRunner` is wired to the UI at last. This is the only phase of the NSoT
work that reaches a device, and everything built before it exists to make that
reach refusable.

### Answered from the code: what gets saved, and when

- **`write memory` does happen.** `_push_via_netmiko` calls
  `conn.save_config()` immediately after `send_config_set`, which for a Cisco
  driver issues `copy running-config startup-config`. Rollback does the same.
  A reload does not lose the change, so the golden commit records something the
  device still has after a restart.
- **Stage 7 captured no config at all.** `_capture_operational_snapshot`
  collects neighbours, interface counts and route totals — operational metrics
  for convergence checking. Stage 8.5 would therefore have had nothing to
  commit but stage 4's *pre-deploy* copy, recording the wrong thing entirely.
  Stage 7 now captures the post-deploy running config on the session it already
  holds.
- Note: `write memory` runs at push time, **before** verify. If verify fails,
  rollback also saves, so startup ends up matching the rolled-back state. There
  is a window where a bad config is in startup — deferring the save until after
  verify would leave a device that reloads mid-verify with an unsaved *good*
  config, which is worse. Reported rather than changed.

### Added — `modules/nsot/deploy.py`

The 3b contract, enforced: refuse a non-deployable artifact → re-render with
**real** secrets in memory → `assert_no_mask()` → only then may a caller
connect. `prepare_device()` does them in that order and a test asserts the
order, because getting it wrong is silent.

`intended/` is never opened: a test walks the module's AST for file reads and
for path-shaped string literals rather than grepping prose, since the
docstrings discuss `intended/` at length.

### Merge-only, enforced by provenance

`merge_diff()` returns lines to add and **removal warnings** — lines on the
device that the template does not mention. Nothing is ever negated.

`assert_merge_only()` checks that every pushed command appears verbatim in the
intended config, rather than grepping for `no`. That distinction matters: a
template may legitimately contain `no ip http server`, which is real
configuration. What must never happen is the tool *synthesising* a negation,
and a synthesised one is by definition absent from the intended config.

### Per-platform transport short-circuit

`_push_config` gated NETCONF on one **global** setting and fell back to SSH only
*after* a failed attempt. On a batch containing vIOS-L2, which has no NETCONF at
all, that is one socket timeout per device before anything happens — a deploy
that looks hung.

Transport now comes from the platform map, per device. `supports_netconf: false`
goes straight to SSH with no attempt. The global setting survives as a master
off-switch only: it can disable NETCONF everywhere, never enable it on a
platform that lacks it.

### Settle windows for verification

`modules/nsot/convergence.py`. Verifying immediately after a change produces
spurious failures: RIP updates every 30 s, so a neighbour check two seconds
after a RIP change reliably reports a drop that is not real.

Per-check windows, configurable: OSPF 45 s, BGP 60 s, RIP 90 s (more than two
update cycles), interfaces 20 s — each with an initial wait before the first
poll. Three outcomes, not two: **converged**, **not yet converged**, and
**failed**. Reporting the middle one as a failure is what makes an operator
distrust the verifier and start skipping it.

Note: `_detect_routing_neighbors` probes BGP → OSPF → EIGRP → IS-IS and **never
RIP**, so S1/S2 skip the neighbour check entirely today. Recorded, not yet
fixed.

### Batch control

- **Sequential by default** (`deploy_max_workers`, capped at 16). vIOS-L2 has
  limited vty lines, and Oxidized, the drift checker, the ping worker and a
  nine-device batch can all want the same device at once.
- **Circuit breaker** (`deploy_verify_failure_limit`, default 2), distinct from
  drift: one drifted device means someone touched a box and the batch carries
  on without it; repeated *verify* failures mean something systemic, and
  continuing turns one mistake into nine. Unattempted devices are reported as
  unattempted.

### Stage 8.5 — save golden

Part of the flow, between verify and audit. Runs **after** verify so it never
records config about to be rolled back, and on **partial success** so a device
that deployed cleanly is recorded even when a sibling failed. A failure here is
a warning, not a rollback: the config is on the device either way.

Every device is accounted for — deployed, or skipped with a reason.

### Pipeline stage table: 9 → 10

The count was descriptive; the invariants were not. `audit_log` is still last,
the rollback stages are still deploy/post_snapshot/verify, and the pre-deploy
stages still abort. One existing test pinned `audit_log` to index 8 — it now
asserts the *invariant* (audit runs last) rather than the index, which is what
it existed to protect.

### RIP verification — a verify that checked nothing

`_detect_routing_neighbors` probed BGP → OSPF → EIGRP → IS-IS and **never RIP**.
S1 and S2 are the RIPv2 devices, so they matched nothing, returned a neighbour
count of −1, and the verify stage skipped the check entirely — reporting
"verified" having checked no neighbour state at all. False confidence in the one
phase where confidence matters.

RIP is distance-vector and has no adjacencies, so there is no
`show ip rip neighbor` to read. The equivalent is the **Routing Information
Sources** table in `show ip protocols`, which lists every gateway RIP is hearing
from and how long ago. That table now drives the check, reusing the 90-second
RIP settle window.

Three real outcomes, never a vacuous pass:
- **converged** — the count recovered within tolerance
- **not yet converged** — still short, but updates are arriving (a source
  updated within the last minute), so very likely not a failure
- **failed** — still short with no sign of life

A device with no routing protocol at all is now recorded explicitly as
`skipped`, so it cannot look the same as one that checked something and passed.

### Batch orchestration

Mid-batch drift **skips and continues**. Aborting is not atomic either: stopping
at device four leaves three deployed and six untouched, exactly as mixed a state
as skipping one. Abort prevents further change; it restores nothing. The drifted
device carries its fresh capture into a one-click re-preview.

Every device ends as exactly one of `deployed`, `skipped_drifted`, `refused`,
`failed`, `unattempted`, or `skipped_not_selected` — with a final reconciliation
that logs loudly if any device is missing from the report.

### Added

- `modules/nsot/deploy.py` gains `plan_batch()` and `run_batch()`.
- `routes/deploy.py` — plan (read-only) and apply. `templates/partials/deploy_wizard.html`.
- `PipelineContext` gains real fields for convergence, golden results, warnings
  and `settle_sleep`, replacing the `getattr` shims the first cut used.

### Tests

`test_deploy_contract.py` (14), `test_deploy_safety.py` (28),
`test_deploy_batch.py` (17), `test_rip_verify.py` (20), plus updated pipeline
contract tests. **756 total, all passing.** No test opens a socket.

A note on test speed: giving verify real settle windows made the pipeline suite
take 60 seconds, because a unit test has no device to converge and the probe
failure was being waited out. Two fixes — `wait_for` now gives up after three
consecutive probe errors (an unreachable device is a result, not something to
wait out), and `PipelineContext.settle_sleep` lets tests pass a no-op. Back to
0.09 seconds.

## [Unreleased] — NSoT Phase 3b: template library, editor, render preview

Read-mostly. **Nothing in 3b opens a socket to a device.** Every comparison is
against a captured artifact — a golden config or a stored backup. Deploy is 3c.

### The deployability gate

`modules/nsot/render_artifact.py`. A frozen dataclass whose `deployable` is a
**computed property with no backing field**, so no code path can construct a
deployable artifact for a device the parser does not fully model. A preview
always renders and is marked *Incomplete — not deployable*, listing the
unmodelled constructs by name.

Three tests keep it honest: a property test (unmodelled ⇒ not deployable), a
surface test (`build_artifact` is the only public function returning a
`RenderArtifact`, and it accepts no `skip_validation`/`force` parameter), and a
structural test (frozen, no setter, no `rendered_unmasked` field).

### The recorded escape hatch

A hard block would make people fork the code on a network with constructs these
parsers do not model. So deployability can be unblocked by an `unmodeled_ack`
block in `host_vars` listing the **exact** unmodelled lines plus actor and
timestamp. Acknowledged set must equal unmodelled set **exactly** — a new
unmodelled line makes the sets differ and the block returns; a stale
acknowledgement for a line that no longer exists also blocks. Committed to git,
reviewable, content-bound, not click-through dismissible.

### Secrets: `intended/` is masked and therefore never a deploy source

Previews and anything written to `intended/` render with every secret replaced
by `••••••••`. **Phase 3c must re-render from the template with real secrets
resolved in memory at deploy time and must never read `intended/`.**
`assert_no_mask()` is the backstop for that path; deploying the literal mask
string to a device is the failure mode it guards against.

Validation runs on the **truthful** render (a local inside `build_artifact`,
never stored) — comparing a masked render against the real config would report
every secret line as both missing and invented.

### Approval is keyed on a binding fingerprint

Not just template path + content hash, but **plus the sorted set of bound device
identities, plus a hash of each device's `host_vars`**. Without the device half,
a device onboarded in Phase 4 would silently inherit an approval for a template
it was never validated against. Editing the template, binding or unbinding a
device, or changing a device's `host_vars` each revoke approval, and the UI
names which of those happened.

### Added

- `modules/nsot/templates_repo.py` — per-network template library, seeding
  (copies built-ins, never overwrites), CRUD with path-traversal refusal and
  Jinja syntax checking, and bindings.
- `modules/nsot/approval.py` — the round-trip CI gate and fingerprinting.
- `repo.save_templates()` / `repo.save_host_vars()` — separate commit
  namespaces (`template:` / `host_vars:` vs `golden:`), own `Source` trailers,
  and **no tags**: a template change is not a network snapshot.
- `routes/templates.py`, `templates/partials/template_editor.html`.
- Tests: `test_render_artifact.py` (36), `test_template_approval.py` (23).
  **672 total, all passing.**

### Bindings store the mapping only

`bindings.yml` holds `platforms` and `overrides` and nothing else. The resolved
device list is computed from the manifest every time it is needed — a stored
copy drifts from the manifest and then the two disagree silently.

### CodeMirror 5.65.16 vendored

`codemirror.js`, `codemirror.css`, and `mode/jinja2/jinja2.js`, loaded in that
order — the mode calls `CodeMirror.defineMode` and must follow the library.

A misplaced mode file is **not** an error in CodeMirror: the editor initialises
with an unknown mode and renders plain text, indistinguishable from the library
being absent. That is exactly what happened first — the script tag pointed at
the vendor root while the file lives under `mode/jinja2/`. So:

- the partial checks `CodeMirror.modes.jinja2` explicitly and reports the two
  failure cases differently;
- `tests/test_codemirror_assets.py` asserts every referenced asset resolves to
  a real file, that the mode loads after the library, and that no CDN is used;
- highlighting was verified by **executing** the library in a JS engine and
  tokenising a real template line, not by assuming the files load:
  `{%`/`%}`/`{{`/`}}` → `tag`, `for`/`in` → `keyword`.

## [Unreleased] — Phase 3a follow-up: fleet verification and structural filter fix

### Fleet coverage — all nine reference devices

| Device | Platform | Modeled | Fidelity | Unmodeled |
|---|---|---|---|---|
| r1–r5 | C8000v IOS-XE 17.6 | **100.0%** | 100.0% | 0 |
| s1–s4 | vIOS-L2 IOS 15.2 | **100.0%** | 100.0% | 0 |

Mean **100.0%** modeled, **100.0%** fidelity. Zero missing, zero extra, zero
reordered sections. **No construct appearing on 2+ devices is unmodeled.**

The two-fixture run reported 93.7% mean; the fleet run found the gaps. Nine
fixtures were worth the cost.

### Fixed — volatile patterns now anchor to column 0

The `version 2` bug got a structural fix rather than a patch. Every prefix
pattern in `normalize.py` anchors to column 0 unless listed in the new
`NESTED_OK_PREFIXES` allowlist (currently empty). `version 17.6` is the image
version; `  version 2` under `router rip` is RIPv2.

This also closes a **drift blind spot**: `strip_for_diff` was stripping nested
`version 2` from *both* sides, so a RIPv2→RIPv1 change would have gone
undetected. A normalisation step applied to both sides of a comparison can hide
exactly what it destroys, so only an extraction-side test catches it.
`test_normalize_equivalence.py` now asserts that no pattern in any tuple matches
an indented line unless allowlisted.

### Parser gaps found by the fleet run

- `snmp ifmib` was handled only by the IOS parser — all five routers have it.
- `ip sla` was handled only by IOS-XE — s3 has it too. Both promoted to the base.
- Newly modeled per the amended decision rule (2+ devices, or a
  routing/redundancy protocol in the design): `ip nat` (top-level and
  interface-level), `ip prefix-list` (grouped by name, sequence order
  preserved), `login`, `subscriber`, `multilink`, `diagnostic`, `memory`,
  `redundancy`, `call-home`.

### Verified

- **`unmodeled` captures full nested blocks.** `call-home` is preserved whole,
  including its two-level-deep `profile "CiscoTAC-1"` children, byte-identical
  to source, and it round-trips. A truncated call-home block has silently eaten
  config in this stack before, so it is now parsed as a verbatim body rather
  than restructured.
- **IOS-XE telemetry subscriptions 101/102 were present** in the original r1
  fixture and are fully modeled, along with `netconf detailed-error` /
  `max-sessions`. The parsers had seen them before the fleet run.

### Fixed — the template could invent a `control-plane` line

`control_plane` defaulted to `{"settings": []}`, which is truthy, so every
rendered config gained a `control-plane` header — **including devices that
never had one**. Every device in the fleet happens to have it, so only a
minimal config exposed the bug. Inventing a line is arguably worse than
dropping one: on deploy it would push configuration to a device. Now defaults
to `None`, with a parametrised regression test over nine optional constructs.

### Added

- `tests/fixtures/configs/fleet/` — all nine devices (R1–R5, S1–S4), hashes
  sanitized, certificate hex bodies trimmed (they are provably stripped;
  trustpoint blocks remain and are parsed).
- `tests/test_unmodeled_path.py` (33 tests) exercising the fallback path with
  constructs the parsers have never seen — flat, nested, two-level-nested, an
  unknown child inside a known interface, and a wholly foreign config.
- `tests/test_fleet_coverage.py` (53 tests) including
  `test_no_construct_on_two_or_more_devices_is_unmodeled`, which enforces the
  decision rule rather than restating it.

**600 tests, all passing.**

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
