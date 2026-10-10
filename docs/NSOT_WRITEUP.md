# The NSoT conversion: the writeup

[Author]

This is the writeup of NMAS's conversion into a Network Source of Truth, one
entry per phase and sub-task. [NSOT_WRITEUP_NOTES.md](NSOT_WRITEUP_NOTES.md)
is the notebook it draws on: raw findings, arguments and lessons, written as
they happened. This file is the account built from them.

## Development method

The operator directed the work throughout. The operator set the goals and the
order of the work, made every design decision recorded here (each is
attributed to "the operator" where it appears), and ran every step that
touched hardware or the lab: deploys to the host, device runs, lab probes,
NetBox, Grafana and Proxmox changes, and the acceptance runs that close each
stage. An AI coding agent implemented the code, the tests and the
documentation under that direction, including this writeup and its notebook.
The agent's work reached the host only by being pushed to the repository and
deployed by the operator; the agent ran read-only measurements on the lab
hosts where the operator allowed it, and nothing that changes a device, a
store or a lab service.

Where the text says "the implementation", "the check" or "the tool" was wrong,
that is the agent's work being described; where it says "the operator", the
decision or the observation was the operator's. The findings are reported as
they happened, including the ones the implementation caused.

## How it is kept

**An entry is written in the turn its stage or sub-task closes, while the
detail is still in hand** (the operator's requirement, 2026-09-29). Two
reasons. First, this project has already lost detail to summarisation: the
tenants-versus-regions exchange existed only in a conversation that was later
compressed, and it had to be reconstructed by measuring. Second, an entry
written at close carries the numbers (commits, time, findings, estimate versus
actual) that are hard to recover later, and the forecast corrections are part
of the story.

Every entry has the same parts:

1. **What it was**: the goal, in a paragraph.
2. **How it was implemented**: the design and the main mechanisms, not a
   commit list.
3. **Issues encountered**: the findings it produced, by register ID
   ([OPEN_FINDINGS.md](OPEN_FINDINGS.md)), including those outside its scope.
4. **How they were resolved**: fixed, deferred by decision, or withdrawn, with
   the reason.
5. **Numbers**: commits (with the rule that selected them, so a reader can
   check), elapsed time, findings, estimate versus actual, and the acceptance
   measurement.
6. **Where it left the product**: one sentence.

**A detail that cannot be recovered says so ("Not recoverable: …") and is
never filled in.** Every number carries its source in brackets.

**Closing a stage also checks its forecast against its actuals**, in the
entry, before the next forecast is made (the operator, 2026-09-29): 7.2's
forecast was never checked when it closed, so the next one would have been
built on an unexamined one. And a forecast is made from a finished stage of the
SAME KIND: the 7.1 multiplier, applied to Mode B, was about seven times too
high.

**This file is published once, at the end, as the deliverable** (the operator,
2026-09-29). Until then it lives only here: a published copy would be a second
owner of every fact in it, stale from the next entry on.

**Backfilled entries** (Phases 0 to 3.3, 4C, the branch site, Phase 2 (DHCP), P.1 to P.6, 7.0 to 7.2, and the side campaigns) were drafted on 2026-09-29
from the plan, the register and the git history, after the fact, and each says
where its sources ran out. They are marked *backfilled*. Entries written at
close are marked *written at close*.

### Conventions

- **Dates and times.** Git records commit times in local time (UTC−6). The
  plan and the register appear to date events in UTC. This is an inference,
  not a recorded convention: three drafts reached it independently from the
  times. For example, the register puts C70's re-run at "23:42–23:45, at
  `d17d650`", and git dates `d17d650` 2026-09-27 17:28 −0600, which is 23:28
  UTC. So an evening event can carry the next day's date in the documents.
  Times below are as each source prints them.
- **Commit hashes.** Every hash cited below was checked against this
  repository on 2026-09-29. Six are not in it: `7fd0ac0`, `2fb07db`,
  `5055fe5`, `c7711d6`, `e1e8e49` and `be60f59`. These are commits in a
  list's `config_repo` on the deployment host (the golden and intent record),
  not in the code. They are cited from the documents that recorded them, and
  not verified here. Five more are named as unverifiable where they appear:
  `758d1f56`, `092501f` and `2443892` (the same config_repo), and `e014843`
  and `32dbab73` (the lab's own config repository, Phase 2's migration).
- **Commit counts depend on a selection rule**, because several threads often
  shared one window. Each entry states its rule.

## Status of every entry

| Part | Item | State |
|---|---|---|
| Before the P-items | Phases 0, 1, 2, 3a, 3b, 3c; Stage 2; 3.3; 4C; r6 phase 1; the branch site; Phase 2 (DHCP) | Backfilled below (Part 0) |
| P-items | P.1 to P.6 | Backfilled below |
| | P.7 (alert rules generated and tested), P.8 (per-list settings) | Decided, not built; P.8's design document written 2026-10-04 (NSOT_P8_DESIGN.md) |
| | P.15 (several people at once) | Open. The decided fixes written below (R1, R2, R4, R5, R13, R19, R20, R24, R25, R28), then a second batch across processes (R6, R3's store half, R11, R12, R14, R15, R16); the audit's medium rows, three decisions and the multi-worker half (9.S) not built |
| Stage 7 | 7.0, 7.1, 7.2 | Backfilled below |
| | 7.3 | Open. Sub-tasks written below (seed intent, retire, Mode B, C188, persist, rotate, revert and retry, the break-glass export, capture on the v2 device page); persist and rotate accepted on the host; retire, revert/retry and the break-glass export await their real runs; the v2 capture's preview half ran on the host (2026-10-03), its record half awaits a real change; persist and rotate on v2 await their real runs |
| | 7.4 to 7.10 | Not started |
| Stage 8, Stage 9 | | Not started |
| Side campaigns | The store-hardening family (C20, C157, C158, C160), the Grafana rule audit (C165 to C168), the verify family (C62 to C68, C108, C114, C115, C178), Mode B's probe campaign | Backfilled below (Part III). The verify family's last member, C178, is built and awaits its real-device run |

## Part 0. Before the P-items: the phases

These phases predate the register (it began 2026-09-25 at `da4d479`), so their in-phase findings have no IDs; later rows against their mechanisms are named. Each of Phases 0, 1 and 2 landed as one squashed commit, so git records when a phase finished, not when it started. A naming hazard: the register's "Phase 2 ledger, 15 defects" is onboarding's DHCP phase 2 (below, and [PHASE2_DHCP.md](PHASE2_DHCP.md)), not the golden-repository Phase 2.

### Phase 0 — Foundation, portability, and safety

*Backfilled 2026-09-29.*

**1. What it was**

Make the codebase safe to build the NSoT work on, with no user-facing
features. NetBox writes had to become fail-closed, secrets encrypted, the app
deployable headless on Linux, settings schema-validated, and the test suite
runnable [PLAN §6 "Phase 0"; CHANGELOG at git eac9c5e]. Its acceptance: all
existing tests pass, the app starts on Windows and headless Linux, settings
round-trip, and with allow-writes off no code path can write to NetBox
[PLAN §6].

**2. How it was implemented**

- **Write gate.** All NetBox writes go through three chokepoints
  (`_nb_post`, `_nb_patch`, `_nb_delete`), each checking
  `netbox_guard`. `netbox_allow_writes` defaults off [CHANGELOG at
  git eac9c5e].
- **Dry run.** `netbox_guard.dry_run()` is a thread-local context. Inside it
  the chokepoints record the write they would make and return a synthetic
  object with a negative id, so the unmodified sync code produces the
  preview. A dry run is read-only, so the Import button stays clickable with
  the gate closed [NOTES "Key design decision"].
- **Provenance.** Every object NMAS creates is tagged `nmas-managed` (in
  `_nb_post` only) and its id recorded in `data/netbox_created_ids.json`.
  Remove deletes only objects that are tagged AND recorded [NOTES "Other
  decisions"].
- **One-shot authorization** (follow-up). A preview issues a single-use,
  5-minute token bound to a SHA-256 of the plan. Execute consumes it,
  recomputes the plan, and aborts if the hash differs. The master switch is
  checked before the token is consumed [git e7c3e66].
- **Settings.** `settings_schema.py`: defaults, JSON Schema validation
  (`jsonschema`, not pydantic), versioned forward migration. Each of the 70
  new settings defaults to prior behaviour, `netbox_allow_writes` excepted
  [NOTES "Other decisions"].
- **Secrets.** `secrets_store.py` encrypts settings secrets with the existing
  Fernet key, as `enc:v1:<token>`. Unprefixed legacy values are upgraded in
  place; an undecryptable value returns `""` and logs [NOTES "Other
  decisions"].
- **Integrations.** `modules/integrations/`: a base client plus nine clients
  with `test_connection()` only, drawn as cards from a JS spec [git eac9c5e;
  NOTES "Trade-offs accepted"].
- **Portability.** Bind host, port, browser auto-open, TFTP root and the
  Jenkins step shell come from settings or environment; `routes/` blueprint
  scaffolding; `pytest.ini` [CHANGELOG at git eac9c5e].

**3. Issues encountered**

The register did not exist yet (it began 2026-09-25 [git da4d479]), so
in-phase findings have no IDs.

- Plan audit: of the plan's 11 current-state findings, 9 accurate and 2 partly
  wrong. The plan's `bat`-step attribution was also wrong [NOTES
  "Verification"].
- Missed by the plan: Remove deleted by site membership, not provenance; list
  deletion silently cascaded into NetBox; `requests` missing from
  requirements; `pytest tests/` could not collect; the NetBox token stored in
  plaintext; `config.py` created a literal `C:` directory at import; an
  IPv4-only golden-header regex [NOTES "Verification"].
- Post-review: confirming an import set `netbox_allow_writes` persistently,
  so the second import needed no confirmation; the dry run over-counted
  shared objects (three manufacturers previewed, one created); `_nb_patch`
  returned a synthetic id for existing objects, planning spurious child
  creates [NOTES "Phase 0 follow-up"].

Later findings against this phase's mechanisms:

- A3: the nine reference devices predate provenance, so Remove is blind to
  them [OPEN_FINDINGS A3].
- C155: the token was checked in the NetBox tab's routes, not at the
  chokepoint, so list deletion's opt-in removal deleted with no token
  [OPEN_FINDINGS C155].
- C59 and C131: an untagged create; the host's created record held the
  suite's fixture ids [OPEN_FINDINGS].
- C130, C134, C135, C136: removal forgot unreadable objects; a preview
  overwrote the last import's record; the preview listed tag writes the import
  never makes ("preview count is the executed count" had been checked for
  creates only); the preview masked its own token [OPEN_FINDINGS].
- C8, C149: write failures logged at DEBUG with `failed=0`; 56 of 58
  modifications carried no actor [OPEN_FINDINGS].
- C171: five Phase 0 NSoT-git settings read by nothing [OPEN_FINDINGS C171].
- Settings: a version bump seeded 98 keys on a v1 install; the settings file
  erased itself on 2026-09-23 [CLAUDE.md "Settings"]. No register ID located.

**4. How they were resolved**

- In-phase: fixed in the phase commits: provenance-based removal, cascade
  made opt-in, token encrypted and upgraded, `requests` added, `pytest.ini`
  added, TFTP root no longer created at import [CHANGELOG at git eac9c5e].
  The persistent confirmation became the one-shot token; the over-count got a
  virtual overlay (preview equals execution at 1, 3 and 5 devices); PATCH
  returns the real id [NOTES "Phase 0 follow-up"].
- Later: C155 closed 2026-09-28 (the check moved to the write, and list
  deletion never deletes NetBox objects). C130, C134, C135, C136, C8 and C149
  fixed. C59 closed by decision, and its remedy withdrawn after C131. A3 is
  scheduled to 7.10, waiting on C100. C171's probe half is fixed, the rest
  sent to 7.7 [OPEN_FINDINGS].

**5. Numbers**

- Commits: 2. eac9c5e, 2026-09-20 01:59:13 -0600 (41 files, +5197/-325);
  e7c3e66, 2026-09-20 02:09:35 -0600 (11 files, +1097/-69) [git].
- Elapsed: 10 min 22 s between the two commits [git]. Start time: not
  recoverable (see the list at the end).
- Tests at close: 209 (120 pre-existing + 89 new) [NOTES "Phase 0" Status];
  243 after the follow-up (+34) [git e7c3e66].
- Findings in phase: 2 partly wrong plan claims, 7 missed defects, 3
  post-review defects [NOTES]. Later rows: listed above.
- Estimate: none recorded.

**6. Where it left the product**

NetBox writes were gated, previewed and provenance-bound, secrets encrypted,
and the app runnable headless with a collectable test suite.


### Phase 1 — NetBox as the source of truth for inventory

*Backfilled 2026-09-29.*

**1. What it was**

Let a device list take its inventory from NetBox instead of a CSV, while every
existing consumer kept working. Add a credential store, fix device lookup,
and give templates a render context with interfaces and addresses
[PLAN §6 "Phase 1"].

**2. How it was implemented**

- **One dispatch point.** `load_saved_devices()` had 79 call sites across 11
  modules. It now checks the list's source (`source.json`; absent means local)
  and returns CSV rows or adapted NetBox devices. The other 78 call sites did
  not change [NOTES "The design decision"].
- **Shape fidelity.** The adapter returns credentials still
  Fernet-encrypted, as a CSV row does, because callers decrypt at use
  [NOTES "The design decision"].
- **No network I/O in dispatch.** A background refresh queries NetBox and
  resolves and encrypts credentials once per refresh. Dispatch returns a deep
  copy from memory. The persisted cache holds identity only, never
  credentials [NOTES "Amendment"].
- **Credentials** (`modules/credentials.py`): device override, then the
  list's designated credential list, then role, site and default profile.
  Each device carries `_cred_source` [git d9e868d].
- **Partial success.** A missing `primary_ip4`, unmapped platform or
  unresolvable credential skips the device with a reason; an unmapped role is
  a warning [NOTES "Partial success"].
- **Stale devices** are inert, not deleted [NOTES "Stale devices"].
- **Lookup** is exact name, then IPAM, then "not found" [NOTES "The lookup
  fix"]. `build_render_context()` is the one way templates get data [NOTES
  "Render context"].

**3. Issues encountered**

No register IDs for in-phase findings; the register began later
[git da4d479].

- The stale-device comparison read the file it had just overwritten, so a
  departed device could never be detected. Caught by a test [NOTES "Getting
  the stale-device comparison wrong first"].
- `netbox_get_device` fell back to a fuzzy `q=` search and took the first
  hit: "R1" could return "R10" [NOTES "The lookup fix"].
- Pipeline stage 2 discarded the interfaces stage 1 fetched, and the merged
  `config_context` was never exposed [NOTES "Render context"].
- The fake NetBox was stricter than real NetBox (`address=` matching,
  `device_id=` on addresses), producing false failures [NOTES "The lookup
  fix"].

Later findings against this phase's mechanisms:

- D7: the commit said drag-and-drop reorder "still works, stored in
  source.json" [git d9e868d]; it fails on a NetBox list and the source.json
  route has no caller [OPEN_FINDINGS D7].
- C157, C160: the credential store and devices.csv had the settings file's
  erasure shape [OPEN_FINDINGS].
- B3: orphaned credential overrides [OPEN_FINDINGS B3].
- The default source filter `{"status": "active"}` combined with a
  ping-derived NetBox status could remove a device permanently from a NetBox
  list [docs/LESSONS.md#populations-by-property "The status write is a SELF-SEALING loop"]. No register ID
  located.
- A bare `load_saved_devices()` read a pre-lists file and returned zero rows
  [docs/LESSONS.md#survey-first-and-constrain-the-shape "`load_saved_devices()`'s no-argument default"]. No register ID
  located.

**4. How they were resolved**

- In-phase: all four fixed in the phase commit (capture previous addresses
  before persisting; exact lookup, tested with R1, R10, R100 and bare "R";
  the render context; the fake corrected) [NOTES; git d9e868d].
- Later: C157 and C160 fixed 2026-09-28; B3 closed by decision (report
  only); D7 scheduled to 7.4 [OPEN_FINDINGS]. The status filter default was
  removed and status dropped from updates [CLAUDE.md]. The no-argument form
  now resolves the active list, and a bare name raises `UnknownDeviceList`
  [CLAUDE.md].

**5. Numbers**

- Commits: 1. d9e868d, 2026-09-20 02:28:12 -0600 (25 files, +2765/-46)
  [git].
- Elapsed: 18 min 37 s after the Phase 0 follow-up commit [git]. Work time:
  not recoverable.
- Tests at close: 307 (243 + 64 new) [NOTES "Phase 1" Status; git d9e868d].
- Findings in phase: 4 [NOTES]. Later rows: listed above.
- Estimate: none recorded.

**6. Where it left the product**

A list could be sourced from NetBox, and every existing feature ran on it
through one dispatch function.


### Phase 2 — Golden config repository and version control

*Backfilled 2026-09-29.*

**1. What it was**

Turn golden configs into a version-controlled store: one write path, one
commit per save, timestamps in git as tags and trailers, identity through a
manifest, renames that keep history, and a one-time migration (lab objectives
1.1 and 1.4) [PLAN §6 "Phase 2"].

**2. How it was implemented**

- **One write path.** `nsot.repo.save_golden()` replaced six golden-write
  sites. One call is one commit, even for a nine-device Save All; an
  unchanged device makes no commit but is reported [git 4875e67].
- **Metadata in git.** The file keeps one stable header line. Commits carry
  `Source`, `Actor`, `Devices`, `Device-Id`, `Device-Name` trailers, and
  annotated tags `golden/<device>/<UTC>` and `baseline/<UTC>`. CI evidence is
  a git note [git 4875e67].
- **Manifest.** Devices key on `nb:<id>` or `uid:<uuid4>`. A rename is a
  `git mv` committed alone, so `git log --follow` survives it. Refresh
  records `pending_rename` and never commits; both names resolve while
  pending [NOTES "Renames"].
- **Normalisation.** The "duplicated" prefix lists were four different
  jobs, so `normalize.py` holds each, pinned to prior behaviour [NOTES "The
  plan was wrong"].
- **Migration** is dry-run by default, merges duplicates keeping the newest
  content, reports every merge and backs losers up [NOTES "Migration"].
- **Restore** queued per-device approvals and skipped stale devices by name
  [NOTES "Restore"].
- **Robustness.** Per-repo lock, stale `index.lock` detection, background
  post-commit hooks, tag retention [git 4875e67].

**3. Issues encountered**

No register IDs for in-phase or same-day findings.

In the phase commit [git 4875e67; NOTES "Three bugs"]: tag names collided
within one second; `git tag --format` does not expand `%x1f`, so the baseline
list was always empty; the migration was not idempotent (`last_seen` in the
manifest); Save All's validation trigger `has_staged_changes()` became
permanently false; the IPv4-only header regex (first found in the Phase 0 audit).

Same-day first runs against the live lab:

- Migration dry run: 18 devices and 0 merges for nine, because the two stores
  held one device in different formats [git 9f52b56].
- `already_migrated` was computed and read by no writer, and was true
  whenever `golden/` existed. A second run committed nine files and 18
  whitespace insertions in the lab repo [git 9cf3bad; NOTES "The unconsumed
  check"].
- Platform `""` for all nine manifest entries [git 9cf3bad].
- A `.gitignore` rule never reached an existing repo; the rename commit
  lacked the manifest [git 12e3c17].
- `save_golden` minted identity, giving s4 a second manifest entry
  [git b008b95]; six of nine CSV `device_uid`s named nothing [git 576cf89].
- Verification check 12 passed vacuously having compared nothing
  [git 2542170].

Later: C104 (readers took the working tree), C175 (writers staged whole
trees), C91 (a committing Save All took a baseline with a device skipped),
C83 (every subject said "baseline"), C23 (restore preview population), C25,
C161, C18 [OPEN_FINDINGS]. The golden enumerator still listed the legacy
directory [docs/ARCHITECTURE.md "One enumerator"].

**4. How they were resolved**

- In-phase: unique tags with a short-sha suffix; freshness moved to the
  gitignored cache; the trigger became "did this save commit" [NOTES "Three
  bugs"].
- Same day: union-find identity [git 9f52b56]; `.nsot/migrated.json` plus
  empty commits made impossible [git 9cf3bad]; platform from inventory via
  `sync_platforms()` [git 9cf3bad]; hygiene on every `git()` call and the
  manifest staged with renames [git 12e3c17]; minting unreachable from the
  resolver and a uid reconciler [git 576cf89].
- Restore was rerouted through the confirmed deploy path that evening
  [git c1aab4b].
- Later: C104, C175, C91, C83, C23 and C18 fixed; C25 scheduled to 7.4; C161
  deferred to Stage 9 [OPEN_FINDINGS].

**5. Numbers**

- Commits: 1 phase commit, 4875e67, 2026-09-20 12:50:32 -0600 (25 files,
  +3282/-87) [git]. Same-day fixes selected by touching Phase 2's
  migration, manifest or repo code: 9f52b56 (15:07:30) to 576cf89 (19:47:03)
  [git].
- Elapsed: 10 h 22 min 20 s after the Phase 1 commit [git]; this is a gap
  between commits, not work time.
- Tests at close: 385 (307 + 78 new) [NOTES "Phase 2" Status].
- Findings: 5 fixes named in the phase commit plus the plan's prefix-list
  claim [git 4875e67; NOTES]; 8 same-day, as listed [git]. Later rows:
  listed above.
- Estimate: none recorded.

**6. Where it left the product**

Golden configs lived in a per-list git repository with one write path,
identity-keyed history and tagged baselines.


#### Sources read (Phases 0, 1, 2)
- docs/NSOT_WRITEUP_NOTES.md: "Phase 0", "Phase 1", "Phase 2" and the
  sections after them to "The one that was caught".
- docs/NSOT_PLAN.md: header and §6 Phases 0 to 2; headings list.
- docs/ARCHITECTURE.md: "NetBox write safety", "Inventory sources", "Golden config
  repository", "Settings".
- docs/OPEN_FINDINGS.md: intro, section list, rows A3, B3, C8, C18, C23,
  C25, C59, C83, C91, C100, C104, C130, C131, C134, C135, C136, C149, C155,
  C157, C158, C160, C161, C171, C175, D7.
- docs/CHANGELOG.md as of git eac9c5e.
- git: log of the first 120 commits; commit messages and stats of eac9c5e,
  e7c3e66, d9e868d, 4875e67, 83b6fd3, 9f52b56, 9cf3bad, 6bf9bf0, 12e3c17,
  2542170, b008b95, 576cf89.

#### Could not recover (Phases 0, 1, 2)
- Start time of each phase: each landed as one commit, and the plan itself
  was first committed inside the Phase 0 commit (git eac9c5e), so git records
  only completion.
- Work time for Phases 1 and 2: the gaps between commits include
  non-working time, and nothing records hours.
- Estimates: NSOT_PLAN §6 records none for Phases 0 to 2.
- Lab-repo commits e014843 and 32dbab73: named in the notes and in
  git 2542170, but they are in the lab's config repository, not this one,
  so they cannot be checked here.
- Register IDs for in-phase findings: the register began 2026-09-25
  (git da4d479), five days after these phases.
- Test counts at the same-day fix commits (764 to 1099, git 9f52b56 to
  576cf89) include Phase 3 tests, so they are not Phase 2 counts.

**A note that applies to all five entries.** The open-findings register was
created on 2026-09-25 [git da4d479, 2026-09-25 00:31]. Every finding made
during Phase 3a, 3b, 3c, Stage 2 and Stage 3.3 predates it, so none of them has
a register ID. They are named below by the incident title in
NSOT_WRITEUP_NOTES.md (NOTES) or by the commit that fixed them. Register IDs
appear only for findings made later against the same code. Git times are local
(UTC−6), as git prints them; the documents' times appear to be UTC.

Phases 3a, 3b and 3c were built on one day. The three phase-named build
commits run from 13:23 to 14:52 on 2026-09-20, and the first-run corrections
run on to 21:37 the same evening [git 6f58123, 3be6550, 1704b49]. The
follow-up commits were sorted into the three phases by their subjects. That is
a judgement, so each entry lists them for a reader to recount.

### Phase 3a — Parsers, host_vars, and round-trip validation

*Backfilled 2026-09-29.*

**1. What it was**

Turn each device's running config into structured, per-device intent
(`host_vars` YAML), render it back through per-platform Jinja templates, and
prove the render reproduces the device [PLAN "Phase 3: Templatize existing
config"; lab objective 1.3]. It was read-only. Extractions went to a gitignored
staging area; 3b added the reviewed commit [git 6f58123].

**2. How it was implemented**

- One parser module per platform (`cisco_ios`, `cisco_iosxe`) on a shared
  base, and one interface-name table [git 6f58123].
- Secrets become `secret_refs`. A type-9 hash cannot be regenerated, so the
  store keeps the hash string, templates emit it verbatim, and `secret_kind:
  hash` stops rotation from touching it [NOTES "Phase 3a"].
- `roundtrip.py` compares hierarchically. Order matters by default; a
  five-entry unordered allowlist covers what the device treats as a set, plus
  interface bodies. Coverage (`modeled_coverage`) and fidelity are reported
  separately, and `unmodeled` counts against coverage [NOTES "Design decisions
  worth defending"].
- Unmodelled lines are kept whole in an `unmodeled` block and re-emitted.
  `strip_for_roundtrip()` removes only what a template cannot render
  [git 6f58123].
- A fixed-point test: extract, render, extract gives byte-identical YAML
  [NOTES "The fixed-point test"].
- The decision rule (model any construct on two or more devices, or any
  routing or redundancy protocol) is enforced by a test, not restated
  [git 0a1dcc5].
- Later the same day, the comparison became depth-aware (`sections.py`), and
  BGP address-families became their own model [git d7c8391, 4771a4c].

**3. Issues encountered** (none has a register ID; see the note above)

- **RIPv2's `version 2` stripped from both sides.** The volatile filter ate the
  nested line. The round trip still passed, and `strip_for_diff` had the same
  bug, so drift could never see RIPv2 become RIPv1. A pre-existing defect,
  found by an extraction-side test [NOTES "drift was blind to RIPv2 → RIPv1"].
- **Real configs changed the parser**: VRRPv3 nested three levels,
  `exit-address-family` was dropped, and the SNMP community leaked into YAML
  from `snmp-server host` [NOTES "Real configs changed the work"].
- **Two asymmetries the fixed-point test found**: a redundant `raw` list and a
  `lineno` in unmodelled entries [NOTES "The fixed-point test"].
- **The two-fixture figure was not the fleet's.** Two devices gave a 93.7% mean;
  the nine-device run found parser gaps (`snmp ifmib`, `ip sla`, and nine
  constructs to model) [git 0a1dcc5].
- **Three fixtures were derived, not transcribed**, and were wrong (r4, s2, s4)
  [git 071a130].
- **The template invented `control-plane`.** An empty-but-truthy default made
  an optional block mandatory; every fleet device had it, so only a minimal
  config showed it [NOTES "empty-but-truthy"].
- **The unmodelled path was exercised by nothing**, because the fleet was fully
  modelled [git 071a130].
- **Five unreproducible lines on all nine devices**: NMAS's own golden header
  and the IOS preamble [git ed42178; NOTES "the tool's own artifacts were never
  in the test corpus"].
- **The serialiser was not a fixed point over its own output**, so committed
  intent lost its `secret_refs` [git 606f89e, bbae24a]. Caught downstream in 3c
  (see 3c).
- **Coverage read 100% while certificate chains were counted nowhere**
  [git 0a7991d].
- **The metric could not see nesting.** r3, r4 and r5 rendered BGP networks and
  activations outside their address-families and scored 100%. A named test
  asserted the flattening. Found by asking what the extraction modelled
  (`address_families=0` beside 100%) [NOTES "The corpus had the right shape"].
  The fix introduced two regressions of its own (the global scope ordered, and
  an unknown config scoring 16.7%) [git d7c8391].
- **Later, 2026-09-22**: interface names were expanded inside `description`
  text (Stage 1.4) [git 447a72c; PLAN 1.4].

**4. How they were resolved**

All fixed. Volatile patterns anchor to column 0 unless allowlisted, with a test
over every tuple [git 0a1dcc5]. Optional blocks default to `None`, with a
parametrised test [git 071a130]. Fixtures were rewritten verbatim
[git 071a130]. The header and preamble are stripped [git ed42178], and fixtures now carry
NMAS's own artifacts [NOTES "the tool's own artifacts"]. The serialiser fixed point is asserted at
its own boundary [git bbae24a]. Coverage names what it did not examine
[git 0a7991d]. The depth-aware comparison and the address-family model fixed
the nesting, and the test was rewritten to assert membership [git d7c8391,
4771a4c]. Stage 1.4 fixed the parser and corrected committed intent in a
reviewed commit [PLAN 1.4; the commit, `2443892`, is in the list's config_repo
and not in this repository].

**5. Numbers**

- **Commits**: 3 by the rule "subject names Phase 3a or the pre-3b
  verification" [git 6f58123, 2026-09-20 13:23; 0a1dcc5, 13:36; 071a130,
  13:51]. Follow-ups the same day, sorted by subject: 8 [ed42178, 3169d68,
  606f89e, bbae24a, 0a7991d, d7c8391, 4771a4c, 1704b49, the last at 21:37].
- **Elapsed**: 28 minutes between the first and last phase-named commits; the
  previous phase's commit was at 12:50 [git 4875e67]. Not recoverable: working
  time, since git records only commit times.
- **Findings**: 12 items listed above (some hold more than one defect); 1 of
  them was found two days later.
- **Tests**: 507 [git 6f58123], 567 [0a1dcc5], 600 [071a130].
- **Acceptance**: s1 100.0% modelled, r1 92.2%, both 100.0% fidelity
  [git 6f58123]. Then all nine devices 100.0% and 100.0%, zero unmodelled
  [git 0a1dcc5]. Compared depth-aware, the figure for r3 and r4 fell from
  100.0 to 96.2 and r5's to 90.5 [git d7c8391, `nsot_metric_diff.py`], then all nine returned to 100.0%, with
  `merge_commands()` against each device's own golden empty [git 4771a4c].
- **Estimate versus actual**: none found in the sources read.
- **Duration of the wrong figure**: 7 h 49 min, 13:36 to 21:25 on 2026-09-20
  [git 0a1dcc5, d7c8391]. NOTES said "three weeks"; no calendar reading gives
  that, so NOTES was wrong and is corrected to git (2026-09-29).

**6. Where it left the product**

Every device's config could be parsed to intent and rendered back
byte-faithfully, with coverage stated honestly, but nothing yet committed or
deployed it.

### Phase 3b — The template library and the deploy gate

*Backfilled 2026-09-29.*

**1. What it was**

Give each network its own template library, let a person edit and preview a
template against captured config, and put a gate in front of any deploy: a
template must be approved, and a render must be provably deployable
[git 6735f97; docs/ARCHITECTURE.md "Template library and the deploy gate"]. Nothing in 3b
opened a socket [git 6735f97].

**2. How it was implemented**

- Templates are seeded by copy into `config_repo/templates/`, per platform,
  with per-device overrides in `bindings.yml`. The bound device list is
  computed from the manifest every time, never stored [git 6735f97].
- `RenderArtifact` is a frozen dataclass. `deployable` is a computed property
  with no backing field, and `build_artifact()` is the only constructor
  [git 6735f97].
- Unmodelled lines can be acknowledged (`unmodeled_ack`), but only by listing
  the exact lines, committed to git [git 6735f97].
- Previews and `intended/` are masked. Validation runs on the truthful render,
  held only as a local. `assert_no_mask()` guards the deploy path
  [git 6735f97].
- Approval is keyed on a fingerprint. Scheme 1 was template hash, bound
  devices and each device's host_vars [git 6735f97]. Scheme 2 dropped the
  host_vars [git 8a8613a]. The hash later covered the whole import closure
  [git a979220]. Revocation writes a tombstone with a reason [git 83a2335].
- Template commits use their own namespace and create no tags [git 6735f97].
  CodeMirror is vendored, not loaded from a CDN [git a386b5c].

**3. Issues encountered** (none has a register ID; see the note above)

- **Masked validation**: comparing a masked render with the real config would
  report every secret line as missing and invented [NOTES "masking applied to
  one side only"].
- **CodeMirror's mode path was wrong**, so the editor fell back to plain text
  silently [git a386b5c].
- **The seeded library was never committed**, so the first approval committed
  forty files under a one-file subject [git 12e3c17; NOTES "A commit subject
  that described one file while adding forty"]. The first fix keyed on this
  run's activity, not the repository's state, and did nothing on the live box;
  corrected in [git dbd0b07]. A status parser lost a character to `strip()` [git caff5bb].
- **The deploy gate asked about one device at a time**, so every template
  bound to more than one device could never be approved on the deploy path
  [git 5b2addb].
- **Approval validated one template tree and deploy rendered another**
  [git 866c817; NOTES "real checks positioned where they cannot fail", #2].
- **Scheme 1 revoked itself**: a deploy to s4 revoked the template for s1, s2
  and s3 [NOTES "The rule broken by its own author"].
- **The hash covered `base.j2` only**, not the shared `_common.j2`
  [git a979220].
- **Revocation deleted the record**, so a withdrawal looked like "never
  approved" [git 83a2335].
- **Later**: the preview diff was order- and whitespace-sensitive (Stage 1.3),
  masked lines showed as differences for ever (1.3b) [PLAN 1.3, 1.3b]; the
  preview read the legacy golden store [git 2751e62]; and `build_artifact()`
  defaulted `template_approved` to `False`, so a caller that never asked the
  store reported "not approved" [NOTES "A verdict about a store"; git
  063e337]. Scheme 2 was itself replaced: D11 and D2 [OPEN_FINDINGS D11, D2].

**4. How they were resolved**

All fixed. Validate the truthful render, display the masked one
[git 6735f97]. The asset test asserts every path resolves [git a386b5c].
Seeding commits itself, keyed on `git status --porcelain -uall` [git dbd0b07].
The gate hashes the whole bound set [git 5b2addb]. `template_root` travels on
the artifact [git 866c817]. Scheme 2 [git 8a8613a], the closure hash
[git a979220] and the tombstone [git 83a2335]. Stage 1.3 and 1.3b fixed the
preview [git 7ab6ac1, 61b72fc]. Scheme 3 replaced scheme 2 in P.5
[git 61b98a2, 2026-09-26 17:16].

**5. Numbers**

- **Commits**: 2 by the rule "subject names Phase 3b, or vendors its editor"
  [git 6735f97, 2026-09-20 14:08; a386b5c, 14:13]. Follow-ups the same day,
  sorted by subject: 11 [12e3c17 (item 3 of 3), d993bea, dbd0b07, be79b74,
  caff5bb, 5b2addb, 866c817, 8a8613a, 83a2335, a979220, 2159067, the last at
  21:32].
- **Elapsed**: 5 minutes between the phase-named commits; the last 3a commit
  was at 13:51 [git 071a130]. Not recoverable: working time.
- **Findings**: 8 on the day, plus 4 later and the two scheme-2 rows (D11, D2).
- **Tests**: 663 [git 6735f97], 672 [git a386b5c], 876 [git 866c817], 1175
  [git 83a2335], 1185 [git a979220].
- **Acceptance**: none recorded as such for 3b. The nearest measurement:
  after the evening's work, all nine devices had an approved template and
  100% coverage [git 1704b49].
- **Estimate versus actual**: none found in the sources read.

**6. Where it left the product**

A per-network template library existed, and no render could be deployable
unless the template reproduced the device and a person had approved it.

### Phase 3c — Deploy from template

*Backfilled 2026-09-29.*

**1. What it was**

Wire `PipelineRunner` to the interface so that committed intent, rendered
through an approved template, reaches a device: merge-only, confirmed by hash,
verified, rolled back on failure, and recorded as a golden. "The only part of
the NSoT work that reaches a device" [docs/ARCHITECTURE.md "Deploy from template";
git 3be6550].

**2. How it was implemented**

- The 3b contract, in order: refuse a non-deployable artifact, re-render with
  real secrets in memory, `assert_no_mask()`, then connect [git eac33c9].
- Merge-only, checked by provenance: every pushed line must appear in the
  intended config [git eac33c9; NOTES "assert_no_negation"].
- Transport per platform; settle windows per protocol (OSPF 45 s, BGP 60 s,
  RIP 90 s) with a "not yet converged" state; the pipeline's post-snapshot stage (its
  stage 7) captures the post-deploy config and its stage 8.5 saves it [git eac33c9].
- Batches run sequentially, with a circuit breaker on verify failures. Every
  device ends in exactly one outcome [git 3be6550].
- Built through the first runs: intent is committed, never inferred
  [git 081124c]; `merge_commands()` builds the exact program, and the
  confirmed list cannot be overwritten [git 839217c, 838b672];
  `assert_sendable()` [git c430bf7]; `error_pattern`, and a computed
  rollback [git e5423f9]; a rolled-back block with an explicit retry and
  Revert intent [git ddd0e2d to 0e7315b]; dangerous lines authorised at plan
  time [git 8d027fa]; one commit and a measured baseline per batch
  [git 067e28c, b3695a1]; re-apply of a baseline through the same path
  [git c1aab4b, 3357f19].

**3. Issues encountered** (none from the day has a register ID)

- **The pipeline's post-snapshot stage captured metrics, not config**: its
  stage 8.5 would have committed the pre-deploy config as the new golden
  [NOTES "The pipeline's post-snapshot stage captured metrics"].
- **`assert_no_negation` returned `None`** [NOTES].
- **RIP was never verified** [git 3be6550].
- **Intent derived from the capture**, so every diff was empty by construction
  [git 081124c].
- **The pipeline would have sent 83 lines for a 1-line preview**, and pipeline stage 2
  re-rendered over the confirmed list [git 839217c, 11d6a5a].
- **Missing secret refs** (the 3a serialiser defect) reached a plan as
  `<missing-secret:…>`; caught by `assert_no_mask()` four layers down, on a
  read-only plan [NOTES "defence in depth, measured"].
- **An em dash reached s4** as `description NSoT-managed b`, and rollback could
  not fire [git c430bf7; NOTES "checks positioned where they cannot fail" #4].
- **Identity minted** a second manifest entry for s4 [git b008b95].
- **Rejected lines read as success** [git e5423f9].
- **The rolled-back block took four wrong shapes** [NOTES "Method, not
  code"].
- **Dangerous lines were unrunnable** [git 8d027fa].
- **Rollback "restored" `interface Loopback0`** on s4 [git 178306d]; the
  broad key matched `ip mtu` to `ip address` [git c96fe77].
- **Failure capture over a desynced pooled session**, then a timeout after
  `write memory` [NOTES "Reading the evidence over the connection that just
  broke"; "Measuring before raising the number"].
- **A baseline tag claimed a whole network after 3 of 9 devices**
  [NOTES "A tag that claimed more than it measured"].
- **`_deploy_one()` deleted by a scripted edit** while 1133 tests passed
  [NOTES "A whole function deleted"].
- **Later, against this code**: the duplicated stanza header and a
  self-cancelling rollback, and a wizard that never sent `command_hashes`
  [git c9a9d90, e1eb453, 53b8112, 2026-09-24]; D4 [OPEN_FINDINGS D4]; the verify
  family C62, C64–C68, C108, C114, C115, C178; C63, C76, C78, C112, C118.

**4. How they were resolved**

The day's findings were all fixed the same day, by the commits cited. Two
structural changes carry the lessons: `Leaf` makes a header-as-setting
comparison a `TypeError` [git 756fc2b], and an AST test asserts every private
name a route calls is defined [git 3357f19], followed by a route-to-wire seam
test and a diff scan for removed definitions [git a060bd7]. The failure-read timeout
became a setting after measurement [git 0ec7579]. The later findings: fixed
(C62, C64–C68, C76, C108, C112, C114, C115, D4, and the 2026-09-24 three);
C118 closed by decision; C63 moved to Stage 8.8; C78's comparison deferred
pending measurement; C178 built and awaiting a real-device measurement
[OPEN_FINDINGS].

**5. Numbers**

- **Commits**: 2 by the rule "subject names Phase 3c" [git eac33c9,
  2026-09-20 14:29; 3be6550, 14:52]. Follow-ups the same day, sorted by
  subject: 33, from 7f53a50 (14:56) to 3402f1a (21:08); 6 of them build the
  re-apply (c1aab4b, 5ad2bc6, da8d7d4, 061158c, 7814ae0, 3357f19).
- **Elapsed**: 23 minutes between the phase-named commits; 6 h 16 min to the
  live smoke [git 3402f1a]. Not recoverable: working time.
- **Findings on the day**: 15 items listed above, some holding two related
  defects.
- **Tests**: 718 [git eac33c9], 756 [git 3be6550], 1133 when `_deploy_one`
  was found missing [git 3357f19].
- **Acceptance**: the live smoke on s3 through the route seam: 3 commands
  planned, 0 removal warnings, deployed, no rollback; the golden commit held
  `golden/s3.cfg` alone, and the baseline was correctly denied
  [git 3402f1a]. Its golden commit `092501f` is in the list's config_repo, not
  in this repository.
- **Estimate versus actual**: none found.

**6. Where it left the product**

A change to committed intent could be previewed as an exact program,
confirmed by hash, and sent merge-only to a device with a computed rollback.

### Stage 2 — Lifting the rcn-lab1 redeploy ban

*Backfilled 2026-09-29.*

**1. What it was**

On 2026-09-21 a reading of vrnetlab's launch script suggested that r1–r5
would not boot their own credential. The script applies its own `username
admin privilege 15 password admin` before the startup config, and IOS-XE
refuses a `secret` for a user that already has a password. A redeploy of the
production lab (rcn-lab1) was banned until that was measured and fixed
[git da5cb2f]. Stage 2 was to lift the ban by a successful redeploy, "not by
the four items being built" [PLAN "STAGE 2"].

**2. How it was implemented**

- **Measure on throwaway nodes, one question each.** Stage B: does r1's
  current startup file apply? Stage C: does a user-skip in the launch patch
  fix it? D2: has a vIOS ever booted a `secret 9` line? [NOTES "The redeploy:
  what a day and a half of measurement bought"].
- **Stage C's fixes, built and tested before anything was adopted**
  [git 1764926]:
  - `verify_startup_applies()` asks whether the startup file will apply,
    where `verify_startup_file()` only asked whether the hash was in it. It
    reads the launch script, so it passes only while the patch is in place.
  - The generator learned per-platform syntax: `DOMAIN_KEYWORD` and
    `GENERATES_SSH_KEY`.
  - `modules/breakglass.py`: a credential record that does not depend on
    `data/key.key` and can be verified without printing a value.
- **A patcher, not a hand-written diff**, which refuses a file that is not
  what stage B measured [git df312dd]. The operator applied it, since the lab
  host is shared [PLAN 2.1].
- **The runbook and a 27-box checklist were written before the redeploy**,
  and the checklist is kept for every future redeploy [git d03628d, e67647e;
  PLAN "STAGE 2"].

**3. Issues encountered** (none has a register ID; see the note above)

- **The hazard, confirmed on hardware**: `%CVAC-4-CLI_FAILURE`, the node
  healthy on `admin` [git df312dd; NOTES "Headline finding"].
- **`ip domain-name` was rejected on IOS-XE 17.6**, which spells it `ip domain
  name`. The node still booted healthy [NOTES "Stage C"].
- **An em dash in a comment hung a vIOS boot** [git 8b248d8].
- **The patcher refused a correct file** that used the combined import form
  [git fda8136].
- **Four controls that could not fail** [NOTES "Four controls that could not
  fail, in one stage"]:
  - a `--dry-run` that returned before the stage it was meant to test;
  - an `sshpass … || echo PASS` that passed when key exchange failed;
  - a count of `save_golden(` in source that matched a comment;
  - the applicability check itself, which searched for the helper's name and
    reported APPLIES for all five routers with the marker renamed
    [git 92efdc8].
- **A runbook step was a live rotation** on two devices, minutes before the
  redeploy it was meant to check [git fc9f3e7].
- **`nmas-check-credential` printed "failed at" on a success, and REFUSED for a
  login that had succeeded** [git 2f53e9e].
- **Item 0 was false**: switches losing SSH, reasoned from the probe configs
  rather than the real files [NOTES "Correct reasoning about the wrong
  object"].
- **A vIOS silently reloaded** during D2's first boot, after `Startup
  complete`, while its container stayed healthy [NOTES "The check that passed
  because it never asked"].
- **Queued from the session**: Q1 (a timeout read as REFUSED), Q2 (Baselines
  badge labels), Q3 (empty-command rejections on r3–r5 at boot)
  [PLAN "Queued from the Stage 2 session"].

**4. How they were resolved**

- The hazard: the user-skip. In stage C one changed input inverted the
  outcome: the file's credential accepted, `admin` refused [NOTES "Stage C"].
- Fixed: the generator [git 1764926], the ASCII rule over the whole bootstrap
  text [git 8b248d8], the patcher [git fda8136], the credential check (three
  verdicts, never a shell `ssh`) [git 8328e69, 2f53e9e], the applicability
  check (the call site, not the name; reports host, path and sha256)
  [git 92efdc8], and the runbook step [git fc9f3e7].
- Item 0 withdrawn as false [git 7eba257]. Uptime is read per device in the
  checklist (item 4.2) [PLAN "STAGE 2"].
- Q1 fixed [git 2a0eaf6]. Q2 became register row E1, scheduled in 7.5; Q3
  became E2, open [OPEN_FINDINGS E1, E2].
- What keeps the ban lifted is `verify_startup_applies()`, refusing such a
  line when a rotation would write it [git d358686].

**5. Numbers**

- **Commits**: 13 by the rule "between the ban and the lift, subject names a
  probe stage (B, C, D2), Stage 2, the ban, the patcher, the applicability
  check, or the checklist's credential check" [git da5cb2f, 2026-09-21 14:54,
  to d358686, 2026-09-22 18:14]: da5cb2f, df312dd, 1764926, a4c5c02, fda8136,
  d03628d, c7dfb29, 8328e69, e67647e, 2f53e9e, fc9f3e7, 92efdc8, d358686.
  Not counted: 8b248d8, 7eba257 (mixed), 2a0eaf6 (after the lift). Stage 1
  work shared the window.
- **Elapsed**: 27 h 20 min from the ban to the lift [git da5cb2f, d358686].
  NOTES said "four days"; the calendar span is two days (09-21 and 09-22),
  so NOTES was wrong and is corrected to git (2026-09-29).
- **Probe timings**: stage B 7m26s, stage C 7m15s, D2 2m03s to `Startup
  complete` [git df312dd; NOTES "Stage C"; git 8328e69].
- **Tests**: 1715 [git 8b248d8], 1775 [git 1764926], 2103 at the lift
  [git d358686].
- **Acceptance**: every checklist item passed. All nine `Startup complete`; no
  username line rejected; the skip fired exactly once per router; `secret 9`
  on all nine and `password 0` on none; NMAS's credential accepted on all
  nine; `admin/admin` refused on all five routers; Oxidized nine successes;
  drift 9/9 clean; the post-redeploy Save All (`758d1f56`, a config_repo
  commit) changed certificate bodies on r1–r5 and nothing else
  [git d358686].
- **Estimate versus actual**: none found.

**6. Where it left the product**

A redeploy of the production lab became a normal, checklisted operation, and
the next rotation cannot write a startup file that will not apply.

### Stage 3.3 — One enumerator, the drift checker's population, and re-enabling it

*Backfilled 2026-09-29.*

**1. What it was**

Retire the readers of the legacy `golden_configs/` store [PLAN 3.3, first
written in git 693a8cd, 2026-09-22 11:12]. On 2026-09-22 it grew: the drift
checker listed devices from that legacy directory, so a device onboarded after
the migration would never be checked, and the scheduler had been off since
2026-08-30. The finding was folded into 3.3 as a prerequisite for onboarding
r6 [git 7f79b87].

**2. How it was implemented**

- **3.3a, one enumerator.** `repo.list_goldens()` reads the manifest.
  `_list_golden_configs()` became a thin adapter with the same return shape,
  so fifteen call sites were fixed without being edited. `saved_at` is the
  commit time, and one `git log` serves the whole store [git 117fce1].
- **3.3b, the population is the inventory.** Every device lands in exactly one
  bucket (checked, no golden, stale, unreachable). Totals are checked against
  the inventory size, and the panel says "checked 7 of 9" with the others
  named [git 117fce1].
- **3.3c, scheduling.** State is per list. `_save_state()` merges.
  `set_disabled()` records who and when. `status()` reports disabled, idle or
  running [git 117fce1].
- **3.3d, the live-scan question answered "no".** `_scan_device` was deleted
  [git 117fce1].
- **3.3e, a retirement condition.** `legacy_only_goldens()`, `GET
  /golden/legacy_store` and a Golden-tab card [git 117fce1].
- **Re-enabling came last**, after 3.3a and 3.3b, at the operator's
  instruction [NOTES "What a silenced check looks like"].

**3. Issues encountered** (none has a register ID; see the note above)

- **Enumeration and content came from different stores.** 17 executable call
  sites across 9 modules asked the legacy directory which devices had a
  golden [git 117fce1]. The nine devices were covered only because their old
  files remained: "inherited, not designed" [NOTES "Coverage that was never
  designed"].
- **`event_monitor` fell back to another list's devices** for a NetBox list;
  `_check_empty_variables` had the same bug [PLAN 3.3b].
- **A device with no golden was a bare `return`** in drift [git 117fce1].
- **The silenced check recorded nothing**: switched off 2026-08-30 02:41,
  three minutes after a run that flagged all nine devices; no who or why; the
  panel blanked "Last run" [NOTES "What a silenced check looks like"].
- **Drift state was installation-wide**, and the scheduler's `finally`
  replaced the whole state, dropping `disabled` [NOTES, same section].
- **The removal checker could not be satisfied** by a correct deletion, and
  its fix had two bugs of its own (substring match, imports as `ast.alias`)
  [NOTES "The checker that could not be satisfied"].
- **One negative control could not fail** [git 117fce1].
- **Toggling the scheduler raised `TypeError`**, and the app's error handler
  turned every exception into a `302`, so the toggle silently reverted
  [NOTES "A crash delivered as a successful redirect"]. `/drift/settings`
  echoed its input, and the all-clean sentence omitted coverage [git 456897f].
- **A second, dead drift checker**, 172 lines in `agent_runner`
  [git 456897f].
- **`next_ts` was written after every run and read by nothing**, so the
  operator's test of editing it was invalid [NOTES "One file, three keys"].
  The test for its removal could not fail either [git f9dcd21].
- **Carried, not done**: `config_git.write_and_stage` [PLAN 3.3], and
  `detect_config_drift`, a third drift implementation in the AI tool layer
  [PLAN, Stage 8 notes]. Later register rows on this surface: C96 (the drift
  panel draws none of its last run), C176 and C183 (the legacy store's
  notice) [OPEN_FINDINGS].

**4. How they were resolved**

- Fixed: everything under 3.3a to 3.3e above [git 117fce1]; the handlers now
  redirect only a browser navigation and answer anything else with JSON and a
  real status [git 456897f]; the route reports what was stored
  [git 456897f]; the dead checker was removed [git 456897f]; `next_ts` is no
  longer written, and `status()` says the schedule is held in memory
  [git f9dcd21]. The removal checker parses instead of grepping
  [git 117fce1].
- Deferred: `write_and_stage` to the Git-tab retirement [PLAN 3.3]; it is still
  in `modules/config_git.py` today. `detect_config_drift` to Stage 8.2
  [docs/NSOT_PLAN.md "Known defects deferred"].
- Negative controls, each shown failing against reverted code: 7 of 14 on the
  enumerator, 10 of 11 on the population, 10 of 17 on scheduling
  [git 117fce1]; 13 of 15 on the routes [git 456897f].

**5. Numbers**

- **Commits**: 6 by the rule "subject names 3.3, the drift checker or its
  state, or a defect found in 3.3c" [git bf44a79, 2026-09-22 13:19, to 86ab370,
  2026-09-22 22:08]: bf44a79, 7f79b87, 117fce1, 456897f, f9dcd21, 86ab370.
  Not counted: the plan item [git 693a8cd] and a precursor that fixed one
  legacy reader on 2026-09-21 [git 2751e62].
- **Elapsed**: 8 h 49 min from the first 3.3 commit to the close, with the
  Stage 2 session in between; 2 h 21 min from the build commit to the close
  [git bf44a79, 117fce1, 86ab370]. Not recoverable: working time.
- **Scale of the main change**: 20 files, 1791 insertions, 310 deletions
  [git 117fce1].
- **Tests**: 2169 before [git 1de8ea5], 2231 [git 117fce1], 2246
  [git 456897f], 2253 [git f9dcd21].
- **Acceptance**: `scheduled 9 of 9` at 2026-09-23 04:03:14, fired from the
  in-memory schedule, 9/9 clean against committed goldens: the first scheduled
  drift check since 2026-08-30 02:38:48 [PLAN "STAGE 3.3 COMPLETE"; git
  86ab370]. The documents date the close 2026-09-23; git dates the commit
  2026-09-22 22:08 local.
- **Estimate versus actual**: none found.

**6. Where it left the product**

Drift detection ran on a schedule again, over the whole inventory, and said
how many devices it checked out of how many exist.


#### Sources read (Phases 3a to 3c, Stage 2, 3.3)

- docs/NSOT_WRITEUP_NOTES.md: "Phase 3a" and the defect sections after it,
  through "A whole function deleted, and 1133 tests passed", "Restoring the
  device without restoring the intent", "A baseline tag earned by
  measurement", "The corpus had the right shape"; "The same character,
  twice", "Headline finding", "Stage C", "Coverage that was never designed",
  "The check that passed because it never asked", "Correct reasoning about the
  wrong object", "Four controls that could not fail", "The redeploy";
  "Enumeration and content came from different stores" through "The run that
  closed the loop"; "A verdict about a store".
- docs/NSOT_PLAN.md: "Phase 3" and its 3c amendments; section 9, Stage 1, STAGE
  2, "Queued from the Stage 2 session", 3.3 and "STAGE 3.3 COMPLETE"; the
  Stage 8 note on `detect_config_drift`.
- docs/ARCHITECTURE.md: "Templatization (Phase 3a)", "Template library and the deploy gate
  (Phase 3b)", "Deploy from template (Phase 3c)", the rcn-lab1 paragraph, the
  drift entries.
- docs/OPEN_FINDINGS.md: rows C62–C68, C63, C76, C78, C96, C107, C108, C112,
  C114, C115, C118, C176, C178, C183, D2, D4, D11, E1, E2.
- docs/NSOT_WRITEUP.md: conventions, P.5, the verify-family pattern and "Where
  the product stood".
- docs/STAGE2_SESSION_CHECKLIST.md (header), docs/MERGE_COMMANDS_DUPLICATE_HEADER.md
  (header).
- Git: commit messages and stats from 4875e67 to 1704b49 (2026-09-20), from
  346702b to 86ab370 (2026-09-21 and 22), and 61b98a2, da4d479, c9a9d90,
  e1eb453, 53b8112.

#### Could not recover (Phases 3a to 3c, Stage 2, 3.3)

- Working time for any of the five items: git records commit times only.
- Estimates: none found for any of the five in the sources read.
- When Phase 3a work began, before its first commit at 2026-09-20 13:23.
- The times of the redeploy itself within the Stage 2 session: not recorded
  in the sources read.
- Three hashes cited from the documents are in a list's `config_repo` on the
  host, not in this repository, and were not verified: `758d1f56`,
  `092501f`, `2443892`.
- A per-phase acceptance statement for 3b: none was recorded.
- Commit counts for the follow-ups of 3a, 3b and 3c depend on sorting by
  subject, which is a judgement; the lists are given for recounting.

### Stage 4C — The onboarding wizard, proven on a throwaway probe

*Backfilled 2026-09-29.*

**1. What it was**

Stage 4 step C: build the onboarding wizard and prove it end to end on a throwaway C8000v (`bp-onboard-c`) with a management interface only and nothing existing touched, then prove the teardown: that the provenance-based NetBox Remove deletes exactly what NMAS created [NSOT_STAGE4C_PLAN.md header; NSOT_PLAN.md Stage 4]. The teardown was "the part that has never run" [STAGE4C_PROBE.md header].

**2. How it was implemented**

- A frozen `OnboardPlan` built only by `build_plan()`, with `onboardable` computed and every refusal listed at once (4C.1); a NetBox census by identity, `scripts/nmas-netbox-census` (4C.0); a random one-time bootstrap credential staged to survive a crash (4C.2); ordering in which "nothing committed" means no commit was created (4C.3); the wizard route and partial (4C.4); removal of vrnetlab's RW community with the nine RO communities kept (4C.5); immediate drift enrolment (4C.6); assembly of the real steps (4C.7) [NSOT_STAGE4C_PLAN.md §7].
- 4C.8 taught the bootstrap generator a management address on `10.255.0.0/24`, the segment the NMAS is L2-adjacent to via s3 `Vlan99`, with no routing protocol, loopback or route [NSOT_STAGE4C_PLAN.md §8.4].
- Onboarding became two phases. Phase 1 (credentials, commit, render) touches nothing external and leaves the device **pending** (manifest and git, not inventory). Phase 2 is seven steps, promotion last: verify, capture, rotate and record, remove RW, save golden, NetBox record, promote [CLAUDE.md; 0b9ba52]. NetBox creation moved from phase 1 to phase 2 [6f46272]. A pending banner with Verify and Abandon, and a bootstrap artefact re-derived from committed intent plus the staged credential [a5b28f2, 7e7c9d3].
- The probe ran every action through the GUI, with the shell only measuring [STAGE4C_PROBE.md, Method; 9d65904].

**3. Issues encountered** (no register IDs: the register was created afterwards, at da4d479, 2026-09-25 00:31; named incidents below)

- Build and wiring: `run_onboarding()` had no caller and `/onboard/create` returned 501 [a0b8ca8]; the bootstrap config could not reach the device it bootstraps (it pointed at the unreachable `clab-mgmt` VRF) [bb21bd0; NSOT_STAGE4C_PLAN.md §8.1-8.2]; `/onboard/create` sent `body: '{}'`, so Create had never succeeded; a render failure reported as `unsendable` [§8.9]; the probe topology bound no launch patch, the third time that line mattered [5075c88; CLAUDE.md]; a hand-rolled test driver that could not tell passed from never ran, and a node-vs-dukpy JavaScript check disagreement [f4a8489]; three copies of the field list [eccb333]; the target list inherited rather than chosen [98cbb41]; a template-approval gate that no first device of a network could satisfy [f57b83f]; the reserved Gi1 interface [d0ed3ac].
- Found by the probe, which the writeup counts as seven defects "live in code the suite passed" [NSOT_WRITEUP_NOTES.md, "What the Stage 4C probe found"]: phase 2 connecting with an empty password; the importer creating region, site and VRF and no device while reporting "Device onboarded"; a banner with no caller; banner actions dropping the list; the discarded bootstrap artefact; the settings file erasing itself; an empty peer allowlist trusting everyone [90a757b, 6f46272, ee8f99a, f3b3135, 7e7c9d3, 4f8a0f1, cd0696e].
- More in phase 2: the credential override written where nothing reads it [dfe71c2]; three discarded return values [483836d]; `rotate()`'s preflight keyed on proxies (a CSV row, a golden file) [5c31196]; a "promoted and unfinished" state reachable because promotion ran second [1eeeb61]; a device dict with no credentials [82fb977]; `failed_checks: []` beside a failure state, three causes (the `SELF_CONFIRMED` fingerprint, a discarded `reason`, one-field reporting) plus two from the controls [a3a42f6].
- Teardown: the census baseline was never taken, and `--compare` exited 1 for a missing baseline [80b75e5]. Remove then deleted two addresses NMAS did not create, `10.0.0.15/24` and `2001:db8::2/64` (ip-addresses 82 -> 80, total 229 -> 227) [1ff741c]. Diagnosis: the import's `_ensure_ip_address()` matched by address value and re-pointed r3's address to the probe's interface, so deleting that interface cascaded; "one NetBox object has been passed between six devices" [cd3e319; NSOT_WRITEUP_NOTES.md]. The repair then examined zero devices [caf001a]; NetBox could not hold five identical emulator addresses [b34bfdc]; a definition stranded below `__main__` [fddf79b]; the clean-up matched on a null VRF [3fe8f42].
- Sources conflict on the baseline: 80b75e5 says step 2's baseline was never taken; 1ff741c says the loss was "caught by the census by identity" against a baseline. Not recoverable: which baseline file the 82 -> 80 comparison used.

**4. How they were resolved**

- Fixed: nearly all of the above, each in the commit cited. The baseline became step 0a, and `--compare` gained exit 2 `UNPROVEN` [80b75e5]. Address lookup is keyed on the interface and refuses without one. A measured cascade map (`modules/netbox_cascade.py`) lists unmeasured types as unknown, never "takes nothing" [71a6df4]. `clab-mgmt` addresses are excluded from import by setting [b34bfdc]. `SELF_CONFIRMED` is recorded as a step [a3a42f6].
- Resolved later: onboarding revoking its platform's template approval (confirmed at b3c40cf, 2026-09-23 23:36, just after this range; register D2) was resolved by approval scheme 3 in P.5 [OPEN_FINDINGS.md D2].
- Deferred to later stages: the census compares identity, not assignment (A2, to 7.6), and nine of ten devices are outside Remove's provenance (A3, to 7.10) [OPEN_FINDINGS.md].
- Found false later: the "first golden is a true record" claim was false in effect until 2026-09-28, because the rotation committed its own golden before the RW removal (C147) [CLAUDE.md].

**5. Numbers**

- Commits: 51 [rule: `51bbe2c^..3fe8f42` is 56 commits; minus five Stage 7 commits by subject: f9a93c4, 2335119, e3b6a1c, 1068c94, 93c9260]. First 51bbe2c, 2026-09-23 13:00 (plan). Last 3fe8f42, 2026-09-23 23:06. The rule is ambiguous at the start: fe010cc (12:06, "Stage 4 decided") could also count.
- Elapsed: about 10 h 6 min [51bbe2c to 3fe8f42].
- Tests: 2443 passed at 8c5ac44 to 2,963 at 3fe8f42 [commit bodies]. Caveat: every "N passed" in 4C.8 before f4a8489 was harness-only [f4a8489], and the first real run was 2,638 passed / 6 failed [CLAUDE.md]. Per step: 4C.0 15, 4C.1 27, 4C.2 23, 4C.3 23, 4C.4 26, 4C.5 44, 4C.6 19, 4C.8 13 [NSOT_STAGE4C_PLAN.md §7].
- Acceptance: phase 2 ran clean on `bp-onboard-c`. Manifest `netbox_id 10`; a committed 6,907-byte golden with a device-generated `secret 9` and no `snmp-server` lines; `nmas-check-credential --expect` ACCEPTED, exit 0 [NSOT_WRITEUP_NOTES.md, "Step C proven"]. The teardown was not proven clean (above).
- Estimate versus actual: not recoverable; no estimate recorded in the 4C docs.

**6. Where it left the product**

NMAS could onboard a device in two phases (plan without touching anything, then reach, rotate, clean, record, promote), and NetBox removal previews had begun to report cascades.


### r6 phase 1 — A permanent tenth device, and making it survive a reboot

*Backfilled 2026-09-29.*

**1. What it was**

Onboard r6 as a permanent tenth device on `br-mgmt`, in its own containerlab lab, by the path the Stage 4C probe had walked. The one changed variable was that the device stays [R6_PHASE1.md header, §0]. The runbook named one gap to close first (restore previews iterating the ref, not the inventory) [git 40fcb8e]. It then set a deadline: r6's lab joins the persistence sync before phase 2, or the record states r6 is not reboot-safe [R6_PHASE1.md §0c]. Most of the work went into meeting that deadline [R6_PERSISTENCE.md header].

**2. How it was implemented**

- First, the restore preview and the Baselines panel took the inventory as their population ("9 of 10 — partial") [git 6c6a66a, ef6cfcc].
- A device → lab map. `clab_labs` in settings, with the old `clab_*` keys being the lab named `default`. `clab_lab` per device in the manifest, absent meaning `default`. One resolver, `clab_target_for()`, returns host, configs dir, launch patch and sync script together. `persist()` refuses if either path is missing [git 7caeefe, d346b12].
- The sync asks the NMAS and keeps no copy. `GET /clab/sync_targets` and `scripts/nmas-clab-targets` exit 2 on an unreachable NMAS, with no fallback directory [git 1f99024, d346b12]. The map gained the platform dialect as a column, checked by `assert_dialect()`, and an `oxidized_node` column [git 5ae94f9, 17753cd]. It also gained `--group`, `--reconcile` and `--stray` [git eb68227, 667bc92].
- Every verifier goes through the resolver. `nmas-check-startup-applies` asks presence (against the device's own golden) before applicability [git 667bc92, 3139da4].
- The sanitiser `oxidized-to-config.sh` was rewritten as a whole file with six hardcoded device lists removed. It then gained `ssh -n`, an iteration count, a `cmp -s` read-back, the diff on stdout, per-lab commit outcomes and a scoped `git init` recipe. The file was kept at `docs/patches/oxidized-to-config.sh.new` [git cf809fd, e6e1460, fdd0cc2, 7fcbf14, 709759a].

**3. Issues encountered** (no register IDs: the register began 2026-09-25; named by fixing commit)

- The restore preview left out a device the ref predates. So did the Baselines panel's count. A fourth reader, `routes/templatize.py`'s fleet report, drops a device through a bare `continue` [git 6c6a66a].
- Onboarding revokes its platform's approval at Create, and re-approving is refused until the device has a capture [git b3c40cf].
- The coverage fields were carried to the browser and drawn nowhere, in the commit that fixed coverage [git ef6cfcc]. This led to a sweep that every render helper is called [git 72c78c1].
- The Cloudflare edge served stale HTML, and it was misread as a rendering defect [git 4f54394].
- r6 was not reboot-safe. The worse half: fixing only `clab_configs_dir` would point the launch-patch guard at rcn-lab1's patch, and it would pass [git 7caeefe].
- An empty `launch_patch` fell back to the setting through the map itself [git d346b12].
- `clab_host` had been blanked by the 2026-09-23 settings erasure [git 5906b3b].
- The checker bypassed the map by omission and read `labs/lab/configs/r6.cfg`. `--stray` listed a local path [git 667bc92].
- "APPLIES" was printed green for a bootstrap credential [git 3139da4].
- The sanitiser keyed router versus switch on a hardcoded list, and any unknown device became a switch [git 5ae94f9]. There were six hardcoded lists, not four [git 17753cd].
- A proposal to build startup files from goldens was withdrawn [git 1289c07].
- Regenerated self-signed certificates read as drift on every C8000v [git 747e506].
- The hand-written patch was malformed [git cf809fd].
- `ssh` inside `while read` swallowed the destination list. r6 was not copied, and the script said "Startup-configs updated." and exited 0 [git 44978be].
- The full diff failed to show several times. The last cause was `less -R` [git 1716b0c, fdd0cc2, 7fcbf14].
- The sanitiser's commit never worked, and two states shared one message [git 1716b0c, fdd0cc2].
- The printed `NOT VERSIONED` recipe committed `clab-r6/.tls/ca/ca.key` [git 709759a].
- A correct "unchanged" line was read as a failure [git 53a1bef].
- In the tests: a truncating edit deleted tests (22 became 18) [git 667bc92]. Two tests matched their own prose [git d346b12, 3139da4]. `_reconcile` was placed below `__main__` [git eb68227].
- Registered later from this work:
  - C14: `clab-sync.service` failed 72 runs because `nmas-clab-targets` was not on systemd's PATH.
  - C15: a stranded sanitiser write.
  - C23: 6c6a66a's fix was in a function no route called.
  - C28: the settings erasure.
  - C50: an unknown lab resolves to rcn-lab1's paths.
  - D2: whether a pending device should bind.
  [OPEN_FINDINGS C14, C15, C23, C28, C50, D2]

**4. How they were resolved**

- Fixed in the commits cited, except the items below.
- Left open deliberately: whether a never-reached device should bind [git b3c40cf]. Resolved later by scheme 3 in P.5 [OPEN_FINDINGS D2].
- Recorded, not fixed: the templatize fourth reader [git 6c6a66a].
- Withdrawn: goldens as the startup source. The finding became a freshness comparison, scheduled next [git 1289c07, 53a1bef].
- The private key: `.git` removed and redone with an allowlist recipe. The key never left the host. `~/labs/lab`'s history was checked and holds no key [NOTES "A private key in git…"; git 53a1bef].
- Fixed later: C23 (P.3 step 5), C15 and C14's cause (2026-09-25). C28 was fixed as a job. C50 is open and latent [OPEN_FINDINGS].

**5. Numbers**

- **Commits:** 26. Rule: `40fcb8e^..53a1bef` holds 27, minus `edae32e` (Stage 7 §0b/§6c by subject). Six are onboarding preparation and its fallout (40fcb8e, 6c6a66a, b3c40cf, ef6cfcc, 72c78c1, 4f54394). Twenty are persistence (`7caeefe` through `53a1bef`, all in range after it) [git log].
- **First and last:** 40fcb8e, 2026-09-23 23:23:27 −0600. 53a1bef, 2026-09-24 13:44:27 −0600.
- **Elapsed:** 14 h 21 min. That includes 8 h 26 min with no commit, between 44978be (02:27:27) and e6e1460 (10:53:24) [git log].
- **Findings:** 0 register IDs at the time. 18 named findings plus 4 test-side ones (above). 6 were registered later.
- **Tests:** 2,963 before the range [git 3fe8f42], 2,972 [git 6c6a66a], 3,004 [git 7caeefe], 3,078 from cf809fd to 53a1bef [commit bodies]. Negative controls "shown failing": 3, 6, 5, 4, 2, 3 and 3 [git ef6cfcc, d346b12, 667bc92, 3139da4, 5ae94f9, eb68227, 747e506].
- **Estimate vs actual:** Not recoverable. The runbook set a deadline (before phase 2), not a time.
- **Acceptance:**
  - `r6.cfg` is the sanitised 74 lines, with `secret 9` present and `password 0` absent.
  - `nmas-check-startup-applies` reads SAFE, naming `labs/r6/patches/c8000v-launch-adopted.py@e483dd2475b5`.
  - The count and the read-back both report 10 of 10 [git 1716b0c].
  - `~/labs/r6` tracks exactly `.gitignore` and `configs/r6.cfg` [git 53a1bef].
  - The break-glass record holds ten, `complete: True`. `base.j2` is approved against six. There is a fleet baseline of ten [git 895f832; R6_PHASE1.md state].

**6. Where it left the product**

A device in its own containerlab lab is persisted through one lab map, and its reboot-safety is checked against its own startup file and launch patch.

#### Sources read (r6 phase 1)
- `git log` and `git show` (bodies and stats) for all 27 commits in `40fcb8e^..53a1bef`, and 3fe8f42 for the starting test count
- docs/R6_PHASE1.md (entire)
- docs/R6_PERSISTENCE.md (headings, header, §1–§2)
- docs/NSOT_WRITEUP_NOTES.md, from "The edge caches HTML…" through "Phase 1 closed…" (lines ~9025–10195), and "Step C proven" (~8340)
- docs/OPEN_FINDINGS.md rows C6, C14, C15, C23, C28, C50, D2
- CLAUDE.md paragraphs on the lab map, the clab sync map, the loop, per-lab repos and the private key
- docs/NSOT_PLAN.md: searched; it has no r6 phase-1 section
- All 27 hashes verified with `git cat-file -e`; all are in this repository

#### Could not recover (r6 phase 1)
- **r6's own onboarding figures.** R6_PHASE1.md's state block gives `netbox_id 10`, "verified at 03:42:21", a 6,907-byte golden and the tag `golden/bp-onboard-c/20260924T034213Z`. These are the 4C probe device bp-onboard-c's figures [NOTES "Step C proven" ~8340]. 03:42Z is before the runbook commit (23:23 −0600, which is 05:23Z). r6's real NetBox id, verify time and golden size are not recoverable. The onboarding happened before 00:20 −0600 on 09-24, when 4f54394 reports a ten-device baseline.
- **Contradiction:** R6_PHASE1.md's "What phase 1 does NOT establish" still says r6 does not survive a reboot. The state block, replaced at 53a1bef, says it is reboot-safe as measured.
- **Contradiction on the diff failures:** 1716b0c says "failed three times for three different reasons". fdd0cc2 says "five ruled out, four failures". The notes' tally has four rows, and row 3 is "(the same run…)", so three distinct causes. CLAUDE.md says "four failures, four causes".
- **Contradiction:** 6c6a66a says the restore confirm reads "N of M". C23 says that fix sat in a function no route called.
- When the operator installed the sanitiser on the clab host. C14's start (2026-09-24 08:40) is probably UTC, per the Conventions inference.
- Active working time inside the 14 h 21 min.

### The branch site: r6 and s3, the first configuration the tool authored

*Backfilled 2026-09-29.*

**1. What it was**

The first configuration NMAS **authored** rather than extracted: intent written by hand into git, rendered by an approved template, previewed, confirmed by hash, sent merge-only, verified and captured back [R6_BRANCH_SITE.md]. The planned form was an eBGP branch to r5, kept separate from onboarding [NSOT_PLAN.md Stage 4]. The acceptance was a device the tool did not touch: r1 learning r6's loopback.

**2. How it was implemented**

- Options A (move r6 into rcn-lab1), B (a shared bridge off s4) and C (OSPF over the management segment) were priced. C died because s3's half was a removal of `passive-interface Vlan99`, and the deploy path is merge-only [0ec41ee; R6_BRANCH_SITE.md §1].
- C′ copied what s3 already does for the NMAS's own /32: s3 gets `+ ip route 10.255.1.16 255.255.255.255 10.255.0.32` (redistributed into area 0); r6 gets `Loopback0 10.255.1.16/32` and a /16 static, with no OSPF [R6_BRANCH_SITE.md §1 C′].
- Two devices, two intent commits, two plans, deployed r6 first. s3-first would let r1 learn a route to an address nothing answers, making the acceptance vacuous [445eb4b; CLAUDE.md].
- The acceptance comparator was measured before deploying: the existing `10.255.1.10/32` external route on r1 [R6_BRANCH_SITE.md].

**3. Issues encountered** (no register IDs except where named; the table is R6_BRANCH_SITE.md's)

1. A duplicated stanza header for every new container (latent since the merge path was built).
2. A self-cancelling rollback for a created container (same age).
3. The provenance guard refused the correct rollback, and the pipeline dropped the device.
4. A created container was negated even if it never landed.
5. An empty pre-change snapshot made every section look created.
6. The capture-hash refusal named neither operand. Two wrong hypotheses were chased first [ddd387e, b40b4c9].
7. The deploy wizard never sent `command_hashes`.
8. `vs_intent` read the working tree.
9. `StrictUndefined` made a hand-authored interface dict unrenderable and never caught a misspelling.
10. `load_saved_devices()` with no argument returned an empty fleet, found in passing.

Two more, not in the table:
- A refusal folded in after the batch rendered "0 device(s) accounted for" beside its own row [73798ff].
- The `skipped_drifted` entry carried a whole device config, secrets included, later registered as B1 [OPEN_FINDINGS.md B1].

**4. How they were resolved**

- Fixed, all ten [R6_BRANCH_SITE.md]. At landing, six were fixed and three were queued [8c948bd]. The three were then fixed [c08e683, 53b8112, c7e4a9d].
- Key fixes: a creation is undone by one negation, children implied [e1eb453]; the refusal reports both hashes and which side moved [c7139f3, 53b8112]; absent interface keys are filled and misspelled ones refused [c08e683]; `vs_intent` reads HEAD, with "never committed" as a third state [c7e4a9d]; `_merge_refusals()` [73798ff].
- B1 was fixed 2026-09-27 [OPEN_FINDINGS.md].
- Deferred by decision: tightening `transport input` on r1-r5 (E3) [NSOT_PLAN.md]. The eBGP/B topology waits for the next redeploy [R6_BRANCH_SITE.md Recommendation].

**5. Numbers**

- Commits: 15 [rule: `60bcc63^..c7e4a9d`, all branch-site work]. First 60bcc63, 2026-09-24 14:31. Landed at 8c948bd, 2026-09-24 16:14. Last c7e4a9d, 2026-09-24 16:50.
- Elapsed: about 2 h 19 min [60bcc63 to c7e4a9d]; 1 h 43 min to landing.
- Findings: 10 in the table, plus the two above [R6_BRANCH_SITE.md; 73798ff; B1].
- Tests: 3,164 passed at 0ec41ee to 3,244 at c7e4a9d, 0 failed [commit bodies].
- Acceptance: r1 learned `10.255.1.16/32` as metric 20, type extern 2, from 10.255.1.23. This was identical in form to the baseline `10.255.1.10/32` and differed only in age (two minutes against 1d22h). s3 `Vl99` showed DR with 0/0 neighbours, and NMAS got an ICMP redirect from s3 pointing at `10.255.0.32` [R6_BRANCH_SITE.md].
- Estimate: none recorded.

**6. Where it left the product**

NMAS had configured a device from intent a person wrote, end to end, additive only.


### Phase 2 (DHCP): onboarding from a Kea reservation

*Backfilled 2026-09-29.*

**1. What it was**

Prove a device can be onboarded when the tool never writes its address: the device takes it from a Kea reservation, and the tool finds it. It was run on a throwaway (`bp-dhcp-a`), not r6, because on r6 it would have been re-addressing a managed device, and with no relay, which is phase 3 [PHASE2_DHCP.md §1, §9].

**2. How it was implemented**

- `address_source` is a stated source (`static` or `dhcp`), not an "address optional" flag. The plan requires a MAC and a reservation, whose check is three-state: `reserved`, `not_reserved`, and `unknown`, which also refuses [7f73ec4; PHASE2_DHCP.md §3a].
- Kea got a pool-less, reservations-only subnet on `10.255.0.0/24` [e90cfa5; §5]. The MAC was pinned in the containerlab topology so the reservation exists before first boot [§6].
- Phase 2 discovers the address from Kea's **lease**, never the reservation, and refuses naming both if they disagree [d17ad54; §9]. The lease's subnet id carries the prefix length to NetBox [421b8a7; §8].
- `test_server_reads_nothing_the_form_cannot_send.py` makes the form and server read one list [c4d0913; CLAUDE.md].

**3. Issues encountered**

- The ledger's 15 defects [PHASE2_DHCP.md §10]: Kea `ok` over `result: 1`; the Gi1 check blind to the extended link format; a probe subnet colliding with r6's lab; no address-source or MAC field in the wizard; completeness judged by the static shape; the pending row rendering `at —`; `verify_device()` reading an empty `mgmt_ip`; `run_phase_two()`'s local `""`; the override keyed on `""`, which fell back to `profile:default`; the failure omitting `credential_source`; the reveal running on `change` only; a torn-down device's address pre-filled; abandon missing the `reserved_address` key; a script unable to reach its imports; NetBox recording the lease as /32, a five-month-old defect.
- Also:
  - Kea served no subnet for the segment (a blocker) [§5].
  - Kea could be reloaded only by a restart: `config-reload` answered HTTP 403 for want of a credential [§7].
  - `domain` is read with no form field (register D1).
  - The `''` override key was left behind (register B3).
  - `_nb_patch` sits outside provenance, so NetBox updates were recorded nowhere [§11].

**4. How they were resolved**

- All 15 fixed [§10]. The ones not in the ledger:
  - The blocker was resolved by a reservations-only subnet [§5].
  - The reload gap was left as a missing credential, not built [§7].
  - D1 was deferred to 7.4 [OPEN_FINDINGS.md D1].
  - B3 was closed by the operator on 2026-09-28, report-only, with the `''` key cleared [OPEN_FINDINGS.md B3].
  - The §11 gap was closed by the modification record (§12) [4a89c94].
  - `netbox_allow_writes` stays on, by decision [37830dc; §11].
- Out of scope: reboot-safety and a relay path [§9].

**5. Numbers**

- Commits: 16 [rule: `8c7db67^..436b1af`], from 8c7db67 (2026-09-24 17:35) to 436b1af (2026-09-24 22:33). §11's decision adds 37830dc (23:00).
- Ledger: "9 commits fixed things found by running the tool (11 in the stage; two are probe authoring)", carrying 15 defects, "None of the 15 was caught by the suite" [§10]. The 11 match `b0521b2^..421b8a7` by count and by the test span; which two are "probe authoring" is not stated.
- Defect ages: 9 of 15 were written that day, 4 the day before, 1 four days earlier, and 1 five months earlier [§10].
- Tests: 3,276 to 3,360 [§10], matching b0521b2 and 421b8a7. Before that, 3,268 at 7f73ec4 [commit body]. `test_onboard_dhcp_source.py` has 23 tests [§3a].
- Elapsed: about 4 h 58 min [8c7db67 to 436b1af].
- Acceptance: `GigabitEthernet2 10.255.0.40 YES DHCP up/up`, bia `aabb.cc00.0240`. Kea leased 10.255.0.40 on subnet 255, and NMAS pinged it in 0.58 ms. The manifest, CSV, NetBox and Kea all agree on 10.255.0.40. The teardown census `--compare` exited 0 [§8, §9].
- Estimate: none recorded.

**6. Where it left the product**

The wizard could onboard a device whose address comes from a Kea reservation, and it records the address the device actually leased.


#### Sources read (4C, the branch site, Phase 2 (DHCP))
- docs/NSOT_STAGE4C_PLAN.md (§0, §1, §7, §8.1-8.9)
- docs/STAGE4C_PROBE.md (header, status 2026-09-24, step −1, 0a, closing)
- docs/NSOT_WRITEUP_NOTES.md (4C probe findings, phase 2 second failure, step C proven, Remove/cascade/import/repair/exclusion sections)
- docs/R6_BRANCH_SITE.md (status, defects, §0, §1 C′, recommendation)
- docs/PHASE2_DHCP.md (§1, §3a, §4, §7-§11)
- docs/NSOT_PLAN.md (Stage 4)
- docs/OPEN_FINDINGS.md (A2, A3, B1, B3, C41, D1, D2, E3, C147 via CLAUDE.md)
- CLAUDE.md (onboarding, branch site and DHCP paragraphs)
- git log 2026-09-22 to 2026-09-25, and bodies of the cited commits

#### Could not recover (4C, the branch site, Phase 2 (DHCP))
- Which census baseline the 4C teardown's 82 -> 80 comparison used: 80b75e5 says the baseline was never taken, and 1ff741c says the census caught the loss against one.
- Which two of Phase 2's 11 stage commits the ledger calls "probe authoring": the doc does not name them.
- Estimates for any of the three: none recorded in the docs read.
- 4C test counts before f4a8489 as real pytest results: 4C.8's counts were declared harness-only.
- r6 phase 1 (40fcb8e to 53a1bef), between 4C and the branch site, has its own entry above.

### Phase 4 (Mercury's records) — deploy receipts on the records database (open: the walk on the host)

*Written at the build's close, 2026-10-10 (UTC), under the Phase 7 operating mode. The walk on
the host comes at Phase 7's end, in the operator's order, and is added here then.*

1. **What it was.** The charter's "Mercury's own records" consolidates the audit trail into one
   PostgreSQL database. Receipts move first: they are the store with the R32 shape (several rows
   per handle, no lock) and the one History reads most [NSOT_PHASE4_RECORDS_POSTGRES.md section
   7]. The foundation (the container, host step 6a; the connection and its Test, board F2) was
   already built.
2. **How it was implemented.** `audit.receipt_lines` keeps the file's shape, one row per line
   with its hash and its place in the file, so `receipts._merged` runs unchanged on either
   backend. `receipts.write` and `read` switch on `records_store_receipts`, read at each call.
   `modules/records_migrate.py` is the one owner of the table. Its move is a person's operation
   on the Records database card, preview and bound confirm: copy, switch, copy again, check,
   read-only, switching back at once if the check fails. Its move back exports what was written
   since, then switches. The `records-check` reader runs the check every 300 s, and Needs
   attention draws a mismatch or a database that does not answer.
3. **Issues encountered.**
   - The suite's autouse fixture sends `receipts.path_for` to each test's own folder, while the
     first draft enumerated the files by a glob of its own: two owners of where receipts live.
   - The tests' first counts confused lines with receipts (6 lines merge to 5).
   - The card had claimed a Needs attention row that did not exist (C634).
   - The secret-storage check scans only the files (C635).
   - The first wake key for the reader, `goldens`, was a capture's too, which writes no receipt.
4. **How they were resolved.**
   - `receipts.files()` enumerates beside `path_for`, and the tests take `real_receipts_path`.
   - The counts were corrected.
   - The row was built (C634 closed); C635 is registered B.
   - The reader wakes on `deploy_job`, `device_state` and `settings`.
5. **Numbers.**
   - One commit [git: this commit].
   - 29 tests in `tests/test_records_receipts.py` against a real PostgreSQL 18, and seven
     controls, each failing its aimed tests.
   - The suite's population checks asked for nine declarations the build owed: a key in the
     vocabulary and the client's relays, a reader in the wakes table, a computed settings key, a
     POST body, the group's keys, a setting in SETTINGS.md, a words help link.
   - **Estimate versus actual:** no forecast was made. It is the first store moved, so it is the
     basis for the other stores' forecasts.
6. **Where it left the product.** Receipts can move to the records database and back from the
   card, with nothing lost either way. Nothing has moved on the host yet: that is the walk.

## Part I. Before Stage 7: the P-items

### P.1 — Switch syslog, and a heartbeat that makes silence a signal

*Backfilled 2026-09-29.*

**1. What it was**

The Loki card showed 0 switch log lines during a demo, read as "switch syslog
stopped around 2026-09-09". P.1 was carved out of Stage 5 as a pipeline defect
and scheduled before Stage 7 by the operator's decision, not by dependency
[NSOT_PLAN.md P.1; git 4b72661]. Its acceptance: switch lines queried from
Loki, any device change made through intent, and a signal when a device stops
logging, so the next outage is not found by a count of 0 [NSOT_PLAN.md P.1].

**2. How it was implemented**

Every hop was measured first (device buffer, device send counter, rsyslog
files, Alloy, logrotate, Loki). Nothing had stopped: every device had run
`logging trap critical` since 8 Sep, so almost nothing left the devices. s3's
one severity-2 line, present in Loki, was the positive control [NSOT_PLAN.md
P.1 "MEASURED"]. So P.1 became a decision plus a heartbeat, not a repair.

- **Decided:** trap level `notifications`, set in intent. An EEM applet
  (`event timer watchdog time 300` → syslog `NMAS-HEARTBEAT`). Trap level,
  host, source-interface and heartbeat are ONE template block, whole or absent.
  Onboarding gives every device the block. Grafana rules on Loki are generated
  from the inventory, with NoData = alerting [NSOT_PLAN.md "P.1 DECIDED"].
- **EEM proven first** on a throwaway lab of both platforms (vIOS-L2, C8000v),
  60 s watchdog, polled until three firings [NSOT_PLAN.md; git cff842f].
- **Modelled:** the parser, `_common.j2` and host_vars carry the block. It
  round-trips at 100% on r1 and s1 from device captures. Whole-or-absent is
  enforced where intent is authored, not at extraction [NSOT_PLAN.md "BUILT";
  git cf18ecb].
- **rsyslog** files every message by source address, with no addressing plan
  in the host file (`deploy/rsyslog/10-network-devices.conf`).
- **P.1b bulk intent** (`modules/nsot/bulk_intent.py`, `scripts/nmas-bulk-intent`):
  one compare-and-set change over schema paths, applied to seven devices as one
  commit, `7fd0ac0` [NSOT_PLAN.md P.1b; git 05498fb].
- **Rules** (`scripts/nmas-heartbeat-rules`): one rule per device, anchored on
  the device's own origin-id. Each window is measured from that device's Loki
  arrivals (C16). An hourly `--check` job is watched by `job_health`.
- **Deploy order:** s4, r2, then a batch of six, then s3, then r6, each checked
  before the next. r5 was retired rather than deleted (C11).

**3. Issues encountered**

- C6: a seeded template never learns its source changed; the shipped `_common.j2` reached no network by itself.
- D3: the template editor's confirmations did not say what happened; `_common.j2` could not be opened from the library.
- C9: the vIOS clock runs at about 75% speed (s4: 300.0 s device time = 391–404 s real).
- A4: NetBox records every device's platform as `ios`, written by NMAS's import.
- C10: the batch circuit breaker counts verify failures, not push failures.
- C11: deleting a device left it half-managed in five places; there was no retire.
- C12: P.1 is add-only; the deploy path cannot remove the applet.
- C13: rsyslog names r6 by address, because `/etc/hosts` lists only the original nine.
- C14: `clab-sync.service` failed 72 runs in a row and nothing said so.
- C15: a sanitiser write whose commit failed was stranded, reported as success.
- C16: the per-platform heartbeat window failed three of four switches.
- C17: NMAS's Loki and Grafana integrations were unconfigured on the host.
- C18: r5's retire commit (`3592113`) never pushed; CLI commits exited under their own push.
- C21 (after completion): the query counted any line naming the applet, including its own error.
- Unregistered: the EEM probe's wait loop matched `healthy` inside `unhealthy`; the rule generator read the interval as 0 and wrote 60 s windows; r6 had no logging config (onboarding gave none); the rsyslog filter filed only `10.255.1.` sources; the conf file's name sent the operator to an empty directory; bulk intent's first version reported only the first refusal reason [NSOT_PLAN.md P.1, P.1b].
- Surfaced later: C71 (the test fleet fixtures predate P.1), C151 (a new device has no rule until someone regenerates them).

**4. How they were resolved**

- Fixed: D3, C11 (built; acceptance on r5), C14 at its cause, C15, C16, C18, C21 (anchored on the exact `%HA_EM-\d-LOG` form), and every unregistered item (exact match; interval under 60 refused; onboarding baseline; new rsyslog conf; runbook names the path; all reasons reported) [OPEN_FINDINGS.md Closed].
- Closed on measurement: C17, 2026-09-28 (both URLs found set).
- Closed by decision: C12, the operator, 2026-09-28: accept add-only until Mode B.
- Decided, deferred to Stage 9 (minor): C9 (measure whether NTP can correct it), C13 (key everything on origin-id), C6 (two of six kinds answered), C71.
- Scheduled: C14's surfacing into 7.2; C10 into 7.4; A4 into 7.6. C151 closed in 7.2 step 8.

**5. Numbers**

- **Commits:** 19 by subject. Rule: the subject names P.1 or P.1b, the heartbeat or its window, EEM, or a P.1 step (r5's exit, step 4/5). The list: 4b72661, bfa9752, cff842f, fad2bbb, cf18ecb, 374ac27, 437809f, 050bda4, 03f69bf, 659d050, 05498fb, cab9fcf, 7af138f, 6120900, 4890fcd, 65e17d2, 97dedaf, df79525, 7d65203. Plus 17111e3 for C21 after completion. 4b72661, cff842f and fad2bbb are shared with P.2. The full range 4b72661..7d65203 holds 26 commits, including C6, C14 and C15 work [git log].
- **First and last:** 4b72661, 2026-09-25 10:07 −0600 (P.1 scheduled). 7d65203, 2026-09-25 16:06 −0600 ("P.1 complete").
- **Elapsed:** 5 h 59 min, interleaved with P.2.
- **Findings:** 14 registered IDs in its window (C6, D3, C9, A4, C10–C18, C21), 6 unregistered, 2 more later (C71, C151).
- **Estimate vs actual:** Not recoverable. No time estimate was written (searched NSOT_PLAN.md and NSOT_STAGE7_PLAN.md).
- **Acceptance:** s4's last heartbeat was 21:21:22. Its timer was removed at 21:22:27, and the alert fired at 21:40:00 with the other eight silent. That is 1,118 s after the last heartbeat, between the second and third missed heartbeat. It came 122 s past s4's 996 s window, and that latency is "not measured". Nine rules loaded (750 × 5, 797, 799, 996, 1286). Nine of nine managed devices were heartbeating [NSOT_PLAN.md "P.1 COMPLETE"].

**6. Where it left the product**

Every managed device logs at `notifications` from committed intent. Each sends
a heartbeat whose absence alerts per device, on a window measured from that
device's own clock.

### P.2 — NetBox backup with a tested restore

*Backfilled 2026-09-29.*

**1. What it was**

NetBox was the one store NMAS writes to with no restore path (register A1).
P.2 was scheduled before Stage 7 so that Stage 7 work could be recovered if it
damaged NetBox [NSOT_PLAN.md "What blocks what"]. Scope: a scheduled backup, a
restore tested against a scratch instance, the configuration secrets carried
encrypted, a copy off the host, version checks, and a visible failed or stale
backup [NSOT_PLAN.md P.2].

**2. How it was implemented**

- **Sized first:** netbox-docker, a 30 MB database, empty media volumes
  [NSOT_PLAN.md P.2].
- **`scripts/nmas-netbox-backup`**, hourly: `pg_dump` on an exported snapshot,
  the media volumes, `env/` and `configuration/`, and a manifest. The manifest
  holds image tags, versions, per-table row counts from the same snapshot, and
  a sha256 per file. Hourlies are kept about 26 h, dailies about 15 days
  [NETBOX_BACKUP.md].
- **`scripts/nmas-netbox-restore-test`** restores the newest backup into a
  scratch postgres. It compares every table's row count with the manifest,
  because the census alone would pass a restore that lost field values.
- **Encryption:** everything leaving the VM is gpg-encrypted to a public key.
  The env file holds the API token pepper, so it must travel with the dump,
  and so nothing goes to git.
- **Proxmox:** a push account restricted by `rrsync -wo`, forced in two places
  (the key's `command=` and a `ForceCommand` block). The runbook explains why
  these are two ways to lose one restriction, not two layers [NETBOX_BACKUP.md 2c].
- **Off-box:** dailies go to B2 via rclone. Each push is confirmed by listing
  the object at its exact size (C22).
- **Status:** `--status` names an unconfigured destination. A failed or stale
  restore test fails it.
- **Scope decision (the operator):** B5 (key escrow) and B6 (VM images) were
  done before P.2's steps [NSOT_PLAN.md P.2].

**3. Issues encountered**

- A1: nothing backed up NetBox (the item itself).
- B4: NetBox's env files were world-readable (0664).
- B5: `data/key.key` was a single copy.
- B6: no VM on the Proxmox host was imaged (`/etc/pve/jobs.cfg` did not exist).
- B7 (found on B6): the thin-provisioned pool's real allocation was not watched.
- B8: the backups' decryption key existed only on the operator's laptop.
- B9: the "write-only" B2 key could HIDE files, and the lifecycle deletes hidden versions a day later.
- B10: nothing checks that lock retention covers the lifecycle window.
- C22: rclone exited 0 after ten refused `401` retries; the push trusted exit codes.
- C19 (same commit, wider scope): secret stores the checker could not see. It now declares rclone.conf, the NetBox env files and the push key.
- Unregistered: the first live restore test failed because `docker exec` lacked `-i`, which the mocked seam could not show. `--status` exited 0 beside that FAIL. The push needed `--no-check-dest`. The claim "the B2 key cannot delete" was made (git c830467) and withdrawn (git a5b85ea). B9's lock retention was first written as 15 days, a day short [NETBOX_BACKUP.md; OPEN_FINDINGS.md B9].
- Later: C106 (4), 2026-09-27: the prune ran before the ship and by age alone, so a failed run left fewer backups. C144 and C145, 2026-09-28: the restore test never covered the encrypted copies; the key export would not import.

**4. How they were resolved**

- Closed on evidence: A1 (2026-09-26). B4 (chmod 600 by the operator; the backup writes 0600 regardless). B5 (escrowed in the break-glass record; a restored clone's key fingerprint matched). B6 (nightly vzdump to a separate disk, restore tested). B8 (2026-09-28: gpg-agent's key files copied to Proxmox, proven by an empty-keyring decrypt of a real B2 backup).
- Fixed: B7 (job_health watches the pool), C22 (confirm by listing), C19, C106 (4) (ship first, prune only what shipped), and every unregistered item.
- Deferred to Stage 9 by the operator's 2026-09-28 split: B9 as hardening. Its row says Object Lock is enabled "by the operator's account; not re-measured". B10 and C145 as minor.
- C144: the honesty half is done (the job-health row says the test covers the plain local copy only). A row for "last proven readable" is deferred to Stage 9.

**5. Numbers**

- **Commits:** 15 by subject (the subject names P.2, A1, B4, B8, B9/B10, the B2 key or off-box): 4b72661, bfa9752, cff842f, fad2bbb, 8cd2c2e, c830467, f15399f, 413c5c7, 363ccf1, a5b85ea, 8ffb840, fa7359d, 4ba1b50, 980a76e, 1a369ce.
- **Prerequisite commits (B5/B6/B7):** 8 more: 56121d9, 940396e, 51bbca5, c324792, 17111e3, 3ac6a9d, 4b3a624, bc6d20b.
- **Follow-ups:** bb1b6ce, 2c2abf5, 74d3d67.
- **Shared commits:** four are shared with P.1 (4b72661, bfa9752, cff842f, fad2bbb), and 17111e3 is shared with C21.
- **First and last:** 4b72661, 2026-09-25 10:07 −0600. 1a369ce, 2026-09-25 20:53 −0600 ("A1 closed").
- **Elapsed:** 10 h 46 min to A1's closure, and 2 d 14 h 34 min to B8's closure (74d3d67, 2026-09-28 00:41 −0600).
- **Findings:** 10 registered IDs in the window, 5 unregistered, and 3 later IDs.
- **Estimate vs actual:** Not recoverable. No time estimate was written.
- **Acceptance:** backup 3.4 s, 198 tables, 3,142 rows, dump 1.29 MB (first run). The installed restore test ran PASS, 198 tables and 3,143 rows identical, in 20 s. Three copies of 363,799 bytes. The NMAS answers `No secret key`, and the laptop decrypted the B2 copy. A broken Proxmox target read `failing` in `nmas-jobs` and recovered to `ok` [NETBOX_BACKUP.md; NSOT_PLAN.md "P.2 ACCEPTANCE STATUS"].
- **Recorded as not met:** the unattended twice-in-a-row watch (PENDING), the rrsync refusal half (not reported), and `--status` exit 0 (not reported).

**6. Where it left the product**

NetBox is backed up hourly with a restore tested nightly. Encrypted copies sit
on Proxmox and B2, readable only with a key that now has a proven second copy.

#### Sources read (P.1, P.2)

- docs/NSOT_PLAN.md: "Scope of what remains", "What blocks what", P.1 (measured, decided, built, steps, COMPLETE), P.1b, P.2 (sizing, acceptance, acceptance status, what has a copy).
- docs/OPEN_FINDINGS.md: rows A1, A4, B4–B10, C6, C9–C19, C21, C22, C71, C106, C144, C145, C151, D3; the 2026-09-28 re-triage legend.
- docs/NETBOX_BACKUP.md: header, sections 1, 2c, 4, 5, 6f, 6g, "What this does not give".
- CLAUDE.md (P.1/P.2 paragraphs); modules/job_health.py (restore-test row wording).
- git: `git log --date=iso` over 2026-09-24 to 2026-09-27; `--grep` on P.1/P.2/heartbeat/backup terms; `--name-only` for bfa9752^..1a369ce; `-S` for each register ID's first appearance; messages of c830467, 7d65203, bb1b6ce.
- docs/NSOT_WRITEUP_NOTES.md was searched and holds no P.1/P.2 material.

#### Could not recover (P.1, P.2)

- A time estimate for either item. None is written in NSOT_PLAN.md or NSOT_STAGE7_PLAN.md.
- Whether the operator regenerated and reinstalled the heartbeat rules after C21's fix (its row names this as an operator step, and no later record says it was done).
- Whether P.2's three unmet acceptance items (the unattended watch, the rrsync refusal half, `--status` exit 0) were ever observed. No later record was found.
- Whether B9's Object Lock is enabled as measured. The register records it only "by the operator's account; not re-measured".
- Whether NMAS's NetBox API token is v1 or v2. The plan records it as "not measured".
- The alert detection latency beyond the window (122 s). The plan states it is not measured.
- A single exact commit count for either item: commits interleave (P.1, P.2, B5/B6, C6, C14/C15 on one day). The counts above follow stated subject rules.

### P.3 — Every path that changes a device is guarded or gone

*Backfilled 2026-09-29.*

**1. What it was**

B12 found that of 19 mutating routes that reach a device, one checked identity, while CLAUDE.md said all did [NSOT_PLAN.md P.3]. Stage 7 would move these controls, and must not re-home a control whose guard does not exist. So P.3 made one statement true and mechanical: every route or socket event that can change a device, a secret, or the tool's gates either requires a person, or is removed [NSOT_PLAN.md P.3]. Scope: B12, B11, D5, D4, C23, the audit's direct-push cuts, the terminal's audit trail, and the agent's push, commit and self-modification tools. Decided by the operator on 2026-09-26 [NSOT_PLAN.md P.3].

**2. How it was implemented**

A step 0 came first: the operator rotated the Anthropic key, since B11 had exposed it for the route's whole life (since `e729267`, 2026-04-12), and then revoked the earlier keys (B17) [NSOT_PLAN.md P.3].

1. One gate table, `modules/route_gates.py`: every mutating endpoint and terminal event declared with a kind (`confirm`, `approve`, `reveal`, `publish_remote`, new `configure` and `break_glass`) or `not_device` with a reason. A `before_request` hook enforces it before input validation; an undeclared endpoint is refused and fails the suite. Routes record the verified actor [step 1].
2. Eight direct-push routes removed (404), with their UI. `/bulk_execute` refuses config mode by name (400); `/ai/chat` refuses `run_playbook_id` (410). Configure's Apply became "Check this form", which sends nothing [step 2].
3. D5: both "Restore Golden Config" buttons open the guarded restore preview at HEAD; both replay routes removed [step 3].
4. D4: the deploy wizard draws the program, one authorise box per dangerous line (re-plans so the hash covers it), and the attribution split; restore can authorise too [step 4].
5. C23: the inventory-population rule moved into `build_targets()`, which preview and apply both call; `restore.coverage()` gives the denominator; `plan_restore()` deleted [step 5].
6. B11: secrets are write-only (`*_set` flags); an empty secret field saves nothing; a sweep of 86 argument-free GETs with planted secrets [step 6].
7. Terminal audit: `data/terminal_audit.jsonl` (0600) records opened, open_failed, closed and refused; never keystrokes [step 7].
8. Agent: 73 tools became 49; 24 removed from list and dispatch; the three `execute_*` tools allow only read-only verbs; auto-continue removed [step 8].
9. CLAUDE.md states the enforced gate with its measurements and its limits [step 9].
10. D10: `Actor-Verified: access | host-shell | none`, written in one place, `repo.git()` [step 10].
11. B14: one stored copy of a credential; `scripts/nmas-credential-dedupe` for stored rows [step 11].
12. B15/B2: a rotation succeeds only on the checker's SAFE verdict (`startup_safety()`), leads with the danger, and records every exit in `data/rotation_audit.jsonl` [step 12].

**3. Issues encountered**

Scoped: B12, B11, D5, D4, C23 [NSOT_PLAN.md P.3]. Pre-existing and closed here: B2 [OPEN_FINDINGS.md B2]; D6 (`/configure/apply`'s docstring promised guards its body lacked) [OPEN_FINDINGS.md D6].

Found during P.3. The writeup counts eleven unscoped findings: B13, B14, B15, B16, C24, C27, C28, C29, C31, D10, D12 [NSOT_WRITEUP_NOTES.md "What P.3 cost and bought"]. Also registered in P.3 commits: C25, C26, D9, C30, B17 [git log -S on OPEN_FINDINGS.md].

- B13: opening the terminal through the tunnel to verify step 1 put 27 of s1's 32 password characters on screen; the rotation that would retire it refused (`not_already_type_9`) [OPEN_FINDINGS.md B13; NSOT_PLAN.md P.3].
- B14: every device stored its login password twice [OPEN_FINDINGS.md B14].
- B15: s1's rotation completed on the device and store, and the boot file kept the exposed password [OPEN_FINDINGS.md B15].
- B16: `/run_command/<ip>` ran any exec-mode command from an ungated GET; the gate table was keyed on HTTP method [OPEN_FINDINGS.md B16].
- B17: keys before the rotated one may still have been valid [OPEN_FINDINGS.md B17].
- C24: `/deploy/apply` silently dropped a confirmed device whose artifact could not be built [OPEN_FINDINGS.md C24].
- C25: one device without a manifest identity makes Save All commit nothing [OPEN_FINDINGS.md C25].
- C26: the suite wrote into the app log of the checkout it ran in [OPEN_FINDINGS.md C26].
- C27: the restore preview's confirm never showed the lines to be added [OPEN_FINDINGS.md C27].
- C28: after the 2026-09-23 erasure, nothing re-checked which guard-gating settings were empty on this install [OPEN_FINDINGS.md C28].
- C29: every HTTP error except 404 went out as a 500 [OPEN_FINDINGS.md C29].
- C30: the agent's prompt names 24 removed tools, 77 times [OPEN_FINDINGS.md C30].
- C31: `yang_push_script` empty with a dead script; "nothing to set" read like "somebody forgot" [OPEN_FINDINGS.md C31].
- D9: a freshness authorisation had no path a person can use [OPEN_FINDINGS.md D9].
- D10: every `Actor:` trailer before P.3 is a claim; 5 of 92 commits carried a verified identity [OPEN_FINDINGS.md D10].
- D12: a device's terminal was one shell shared by everyone who opened it [OPEN_FINDINGS.md D12].
- No ID: `dangerous`/`authorised` are stripped strings while `commands` keeps indentation, so exact comparison never marked a line [NSOT_PLAN.md P.3 step 4].
- No ID: acceptance item 1's floor (131) was stale after the cuts; the population was 121 [NSOT_PLAN.md P.3 acceptance].

**4. How they were resolved**

- B12, B11, D5, D4, C23: fixed in steps 1/9, 6, 3, 4 and 5 [OPEN_FINDINGS.md].
- B2, B15: fixed, step 12 [OPEN_FINDINGS.md B2, B15].
- B13: fixed out of sequence (`abea5ca`, `0ca267e`: send, read, decide; preflight fix); closed on two measured conditions: s1 rotated (`e1e8e49`, ACCEPTED) and break-glass record replaced. Stage-level evidence unrecoverable (a lost scrollback) [OPEN_FINDINGS.md B13].
- B14: code fixed (step 11); running the dedupe on the host was left as the operator's step [OPEN_FINDINGS.md B14]. Not recoverable whether it ran: no record found.
- B16: fixed; now a gated POST [OPEN_FINDINGS.md B16].
- B17: closed by the operator; revoked at Anthropic [OPEN_FINDINGS.md B17].
- C24, C27: fixed in steps 4 and 3 [OPEN_FINDINGS.md].
- C25: deferred to 7.4 (latent: 9 of 9 devices have an identity) [OPEN_FINDINGS.md C25].
- C26: fixed; conftest detaches the handler [OPEN_FINDINGS.md C26].
- C28: fixed as a job, `job_health.settings_rows()` [OPEN_FINDINGS.md C28].
- C29: fixed; HTTP errors keep their status [OPEN_FINDINGS.md C29].
- C30: deferred to Stage 8.5, the prompt rewrite [OPEN_FINDINGS.md C30].
- C31: decided and built (`settings_not_applicable`) [OPEN_FINDINGS.md C31].
- D6: the route was removed in `863d103` [git log -S '/configure/apply' -- app.py]; the register row still sits in an open section pointing at P.3 step 2 [OPEN_FINDINGS.md D6].
- D9: deferred to Stage 7.6 (latent) [OPEN_FINDINGS.md D9].
- D10: trailer built in step 10; the count and marks deferred to 7.5 [OPEN_FINDINGS.md D10].
- D12: decided by the operator: per-connection shells, built (`e6d31ec`) [OPEN_FINDINGS.md D12]. The terminal was later decided to be removed entirely (2026-09-27) [NSOT_FEATURE_AUDIT.md 3b].
- The unnumbered two: renderers compare trimmed text; the floor set to 121 and the correction stated [NSOT_PLAN.md P.3].

**5. Numbers**

- Commits: 20. Rule: every commit from `c5a34c1` (the first "P.3 step" commit) to `690fa90` ("P.3 complete") inclusive, 21 in all, minus `955d6ee` (authorization design, not P.3). 15 of the 20 name P.3 in the subject; the other five are B13 (3), C28 and D12 fixes inside the window [git log c5a34c1^..690fa90]. The plan text itself was `e437b4e` (2026-09-25 22:04), not counted.
- First: `c5a34c1`, 2026-09-25 22:34:32 -0600. Last build step: `5b087c4`, 2026-09-26 01:57:36 -0600. Accepted: `8401b88`, 12:03:56. Complete: `690fa90`, 2026-09-26 12:15:31 -0600 [git].
- Elapsed: 3 h 23 min for the twelve steps; 13 h 41 min to "complete", including an overnight gap before the acceptance run [computed from git dates].
- Estimate versus actual: Not recoverable: no estimate for P.3 was found in NSOT_PLAN.md, NSOT_STAGE7_PLAN.md or the writeup notes.
- Findings: 11 unscoped per the writeup; 16 new register IDs in the list above; 2 unnumbered.
- Suite: 3781 passed at step 1 [NSOT_PLAN.md step 1] to 3950 passed, 0 failed, 0 errors at `5b087c4` [NSOT_PLAN.md P.3].
- 55 definitions removed or moved, none still called [NSOT_PLAN.md acceptance table].
- Acceptance, at `5b087c4`: 121 mutating endpoints classified; all 87 gated endpoints answer 403 with no identity and no view reached; 206 targeted tests passed before and after eleven controls, each failing its targeted test [NSOT_PLAN.md P.3 acceptance run]. On the host at `9c4cf07`: 403 `no_header` on `/deploy/apply`, `/golden/restore/apply`, `/ai/approvals/<id>/approve` (400, 400 and 404 before) [OPEN_FINDINGS.md B12]. Through the tunnel: `c7711d6` and `2fb07db` carry `Actor-Verified: access` [NSOT_WRITEUP_NOTES.md].
- The terminal: an unauthenticated socket was refused and recorded [step 9]; a person opening it through the tunnel was "NOT REPORTED" [step 1].

**6. Where it left the product**

Every route and socket event that can change a device, a secret or a gate now needs a verified person or is gone, enforced by one table and measured over all 87 gated endpoints.

### P.4 — Cut Jenkins; GitHub Actions CI; nmas-deploy gating

*Backfilled 2026-09-29.*

**1. What it was**

Decided by the operator on 2026-09-26: remove Jenkins before Stage 7, so Stage 7 does not draw a tab it is about to delete [NSOT_PLAN.md P.4]. The design audit found nothing was configured and "no working path depends on it": `jenkins_url` empty, the `Jenkinsfile` could not run, the webhook accepted forged SUCCESS posts, and the deploy's `ci_gate` check 4 was fail-open and keyed on the active list [NSOT_CI.md §0]. The goals: remove Jenkins and its 19 agent tools; make `ci_gate` say what it checks; run repo CI on GitHub Actions; make `nmas-deploy` refuse a commit whose CI failed or is pending, with `--offline` for an air gap; version `nmas-deploy` in the repo [NSOT_PLAN.md P.4; NSOT_CI.md §6].

**2. How it was implemented**

- **Step 1a, app surface:** the tab, wizard, settings section, workflow switches and 14 routes (6 mutating, so the gate table's floor went from 121 to 115); Save All's validation pipeline; `event_monitor`'s sync; `agent_runner`'s Jenkins task; unused decrypted credentials in `PipelineContext` [NSOT_PLAN.md P.4].
- **Step 1b, agent:** the 19 CI tools (tool list 49 to 30) and the prompt's Jenkins section [NSOT_PLAN.md P.4].
- **Step 1c, modules:** `jenkins_runner`, `check_runner`, `jenkins_shell`, `pipeline_builder`, the `Jenkinsfile` and `configure.py`'s generators deleted. Settings keys stay (keys are never deleted); `data/jenkins_checks.json` is a retired store the secret checker names until deleted [NSOT_PLAN.md P.4].
- **Step 2:** `_stage_ci_gate` is a local dangerous-command check and says so [NSOT_PLAN.md P.4].
- **Step 3:** `.github/workflows/ci.yml` installs `requirements.lock` with `--no-deps` (the host's exact set); coverage reported, never gated. Built on branch `p4-ci`, merged after green [NSOT_PLAN.md P.4; git branch -a]. Why GitHub Actions and not Jenkins: the NMAS already has an executor with history (systemd timers plus `job_health`); Actions needs no server; air-gapped installs run the suite locally [NSOT_CI.md §3].
- **Step 4:** `scripts/nmas-deploy`, versioned (it had been 25 lines of bash on the host only). It gates on the target commit before HEAD moves; exits 0 to 5; "no run" is never a pass except a docs-only change matching the workflow's own `paths-ignore`; every run is a row in `data/deploy_audit.jsonl` [NSOT_PLAN.md P.4]. Two refinements after the operator's first live run: `GET /health` reports the commit the running process loaded, and the restart is confirmed by identity (MainPID changed, `/health` answers from it, target loaded), not by time; `paths-ignore` is read from the last green commit, and a workflow change is never ignorable [NSOT_PLAN.md P.4; git 3b5c6df, 1319890].

**3. Issues encountered**

- C40: CI run 1 failed at install; the host's package set is not pip-resolvable (netmiko 4.3.0 with textfsm 1.1.2), and Ubuntu ships packages with no dependency metadata [OPEN_FINDINGS.md C40; git a2c83d6].
- C42: the operator's `--offline` control run failed a test on the host that CI passed; the host's ext4 1 ms timestamp tick [OPEN_FINDINGS.md C42].
- C43: a test errored when its file ran alone [OPEN_FINDINGS.md C43; registered in c923a26].
- C44 (the operator's): a manual `git pull` bypasses the deploy gate and systemd loads it at the next restart [OPEN_FINDINGS.md C44].
- C45 (the operator's): the suite takes about 5 minutes on the host [OPEN_FINDINGS.md C45].
- C46: a test asked the live NMAS for its map on every host run [OPEN_FINDINGS.md C46].
- C32, C33, C34, C35, C36, C37: found by running the suite from a pristine checkout for the first time (5 failed, 19 errors) [git d0d696c]. The commit does not say P.4 prompted it; it sits in P.4's window. C39 (the repository is public) and C41 were also registered in the window [git b20a5c9, aebc613].
- C30 extended: 17 scattered CI-tool mentions remain in prompts [OPEN_FINDINGS.md C30].
- No ID: "deployed" was recorded with from == to, and a 200 from `/` would pass a process that never restarted [git 3b5c6df].
- No ID: `/health`'s psutil start time read 0.66 s before systemd's start [git 1319890].
- No ID: `paths-ignore` read from the target would let a commit widen it and wave itself through [git 1319890].
- No ID: the first red commit `003a93d` got no CI run, because its message contained GitHub's skip directive [git 7be2c93].
- No ID: `--offline` tested a `git archive` with no `.git`, so it could not pass on any commit; its exit 3 on the red commit was right for the wrong reason [git 7502759].

**4. How they were resolved**

- C40: install the lock `--no-deps`; the lock regenerated on the host from Python and dpkg metadata, 54 to 64 pins [git a2c83d6]. Dropping stale pins and `openai`/`groq` decided by the operator 2026-09-27, minor [OPEN_FINDINGS.md C40].
- C42: the control fixed (backdated, simulated ext4); the kernel gap accepted by the operator and the row closed 2026-09-28 [OPEN_FINDINGS.md C42].
- C43, C46, C32, C34, C36: fixed [OPEN_FINDINGS.md]. C35 settled as a pin defect, closed by the lock (C37) [OPEN_FINDINGS.md C35, C37].
- C44: deferred by the operator's decision 2026-09-27: a deploy clone only `nmas-deploy` moves, Stage 6 [OPEN_FINDINGS.md C44].
- C45: measured; the operator approved the fixes, built in `5eef2df` (store initialised once, xdist in CI) [OPEN_FINDINGS.md C45; git 5eef2df].
- C33: deferred, each route as it is rebuilt [OPEN_FINDINGS.md C33].
- C39: deferred for the lab by the operator (Stage 9) [OPEN_FINDINGS.md C39].
- C30: deferred to Stage 8.5 [OPEN_FINDINGS.md C30].
- The unnumbered items: fixed in `3b5c6df`, `1319890` and `7502759`; the skip-directive case was used as the no-run test and a second red commit `7be2c93` made [git].
- After P.4 closed, the gate itself produced more: C106 (refuse before moving what cannot finish), C124 (a cancelled run read as the verdict; caused C44's first real bypass), C142, C170, and `--wait` [OPEN_FINDINGS.md; git 76d0f7a, 4f92b96, 995498a, bad759a, 70e0ca4].

**5. Numbers**

- Commits: 13. Rule: in `d25e3ff^..f29d402` (25 commits), those whose subject names P.4, `nmas-deploy`, `/health` or a CI run: `d25e3ff`, `ca9842a`, `721933a`, `0999659`, `a2c83d6`, `700d8bb`, `3b5c6df`, `dc7c7b0`, `1319890`, `003a93d`, `7be2c93`, `7502759`, `f29d402` [git]. The other 12 are harness and finding commits; the boundary is a judgement.
- First: `d25e3ff`, 2026-09-26 12:28:08 -0600. Last: `f29d402`, 2026-09-26 16:53:27 -0600. Elapsed 4 h 25 min [git].
- Estimate versus actual: Not recoverable: no estimate for P.4 was found.
- Findings: 6 register IDs attributable to the CI and deploy work (C40, C42 to C46), plus 5 unnumbered; 8 more registered in the window with a weaker link.
- Removed: 146 definitions gone, none still called (`d25e3ff^..HEAD`) [NSOT_PLAN.md P.4 acceptance 1].
- Suite: 3950 at P.3's end to 4020 passed, 0 failed, 0 errors at `f29d402` [git f29d402].
- Acceptance (NSOT_CI.md §7): 1 MET; 2 MET; 3 MET with operands: pending and failed exit 1 on `7be2c93`; code with no run exit 2 on `003a93d`; docs-only exit 0 (`1319890 -> 13a5011`); green deploy `13a5011 -> 5eef2df`, pid 268370 -> 361070; `--offline` red `5055fe5` exit 3, "1 failed, 4004 passed in 287.81s" [NSOT_PLAN.md P.4]. 4 NOT YET OBSERVED; 5 not applicable yet; 6 carried by Stage 7 [NSOT_PLAN.md P.4]. Not recoverable: any later observation of item 4; none was found.
- Undecided inside P.4: scheduled protocol regression (N13) and config-repo checks (R5-R10) [NSOT_PLAN.md P.4].
- Later measurement: over ~28 h, 90 push runs, median 201 s push to green; 35 deploys refused while CI ran; the operator kept the gate and added `--wait` [NSOT_CI.md "CI's cost"].

**6. Where it left the product**

Jenkins is gone, and the host moves only to a commit GitHub Actions passed, confirmed by the identity of the restarted process.

#### Sources read (P.3, P.4)

- docs/NSOT_PLAN.md: P.3 (steps 1-12, acceptance, acceptance run) and P.4 (steps, acceptance)
- docs/OPEN_FINDINGS.md: rows B2, B11-B17, C1, C23-C46, C106, C124, C142, C170, D6, D9, D10, D12
- docs/NSOT_CI.md: §0, §3-§7, "CI's cost, measured"
- docs/NSOT_FEATURE_AUDIT.md: §0, §7 (decisions 2, 3, 3b)
- docs/NSOT_WRITEUP_NOTES.md: "What P.3 cost and bought"
- CLAUDE.md
- git: `git log --format='%h %ad %s' --date=iso` for 2026-09-25 to 2026-09-27; full messages of d0d696c, a2c83d6, b20a5c9, c923a26, 7502759, eb70788, 003a93d, 7be2c93, f29d402, 1319890, 3b5c6df; `git log -S` on OPEN_FINDINGS.md for each ID's first commit; `git log -S '/configure/apply' -- app.py`; `git branch -a`

#### Could not recover (P.3, P.4)

- An estimate for P.3 or P.4: none found in the plan documents.
- B13's stage-level evidence: the rotation CLI's output was in a terminal scrollback that no longer exists [OPEN_FINDINGS.md B13].
- Whether the operator ran `nmas-credential-dedupe` on the host (B14) and deleted `data/jenkins_checks.json` (P.4): both are recorded as the operator's steps, and no record of either being done was found.
- P.4 acceptance item 4: recorded NOT YET OBSERVED; no later observation found.
- Whether P.4 prompted the pristine-checkout run behind C32-C37: the commit (`d0d696c`) does not say.
- Exact commit boundaries: both selections are rules stated above, not a recorded list.

### P.5 — Template approval, scheme 3 (D11, D2)

*Backfilled 2026-09-29.*

**1. What it was**

Template approval under scheme 2 bound an approval to the template AND to the set
of devices bound to it. So approval was all-or-nothing per platform: one device
the template could not reproduce blocked deploys to every other device on its
platform, and every device that joined the set revoked the approval for all
[OPEN_FINDINGS.md D11; NSOT_FEATURE_AUDIT.md 8c]. P.5 made an approval a claim
about the template only: its closure hash and the person who approved it.
Per-device fidelity stays where it already ran, per plan [NSOT_PLAN.md P.5].

**2. How it was implemented**

- The premise was measured before any change. `RenderArtifact.template_report`
  is computed on every plan, from the capture's own parse, and
  `blocking_reasons` already refused a device with missing, invented or
  reordered lines, whatever approval said. So a device the template could not
  reproduce was already blocked alone, and the device-set half of scheme 2
  repeated that check as a property of the inventory [git 61b98a2].
- `approval.template_fingerprint()` is the hash of the template's whole import
  closure, with no device in it. Editing the template, or any macro file it
  imports, still revokes every approval over it [git 61b98a2].
- `approve()` needs at least one bound device to round-trip, not all of them.
  It records every device's result as evidence: validated; failed, with the
  reason; or not validated, for want of a capture [git 61b98a2].
- A scheme-2 record is not honoured silently. Moving to scheme 3 is an explicit
  re-approval [NSOT_PLAN.md P.5].
- The operator's addition: the badge states what an approval covers AND what it
  does not. `approval_status()` carries `covers` and `does_not_cover`, and the
  template library draws both, with the evidence and the approver
  [NSOT_PLAN.md P.5].
- The approve route records a bound device with no capture as "not validated"
  instead of answering 400. `nsot_reapprove_templates.py` does the same, and
  records the OS user as the actor instead of the literal "operator"
  [git 61b98a2].
- The deploy plan stopped building a full artifact for every bound device on
  every plan. That work fed a fingerprint that no longer reads devices
  [NSOT_PLAN.md P.5].

**3. Issues encountered**

- **D11**: approval was all-or-nothing per platform, and its device-set half
  duplicated the per-device gate. Registered 2026-09-25 [git 863d103].
- **D2**: whether a never-reached device should bind to a template was
  undecided, because binding took its platform's deploy path offline. First
  confirmed from the code on 2026-09-23: onboarding revoked the platform's
  approval at Create, not at Verify [git b3c40cf]. Registered with the
  register's creation [git da4d479].
- **Ten tests pinned scheme 2 as correct**, and the D2 tests pinned the
  revocation [git 61b98a2].
- **The migration refuses every deploy until a person re-approves.** Observed on
  the host after deploying P.5: every deploy refused until the operator
  re-approved both templates, with all nine devices round-tripping [docs/ARCHITECTURE.md,
  "Approval is the TEMPLATE"; git 8ff6698].
- **The concept table still described scheme 2.** The Stage 7 concept
  `approval-binds-a-set` asked the screen to state something false after P.5.
  No register ID [NSOT_STAGE7_PLAN.md, concept table].

**4. How they were resolved**

- **D11**: fixed by scheme 3, as above. Closed in the register [git 61b98a2].
- **D2**: resolved by scheme 3. A pending device is still bound, but no device
  is in the fingerprint, so onboarding revokes nothing. The approve route
  records a device with no capture as not validated [OPEN_FINDINGS.md D2].
- **The scheme-2 pins**: rewritten as scheme-3 claims; the D2 pins flipped, with
  the reason [git 61b98a2].
- **The migration refusal**: kept, by design. The operator's reading: an older
  fingerprint answered a different question, so honouring it would be a gate
  that passes because nobody migrated it [CLAUDE.md]. The re-approval was the
  operator's step [git 61b98a2, Not-Done trailer].
- **The concept**: renamed to `approval-binds-the-template` [NSOT_STAGE7_PLAN.md;
  git 91c81fd].

Five negative controls, run confined, each failed its target: every device
required again; the device set back in the fingerprint; a scheme-2 record
honoured; the badge without what it does not cover; the route refusing a device
with no capture [git 61b98a2].

**5. Numbers**

- **Commits**: 2 [git 61b98a2, 2026-09-26 17:16:52; git 8ff6698, 2026-09-26
  17:26:57]. Rule: commits whose subject names P.5 or the scheme-3 migration.
  The decision trail is 3 more commits and is not counted as build: D11
  registered [git 863d103, 2026-09-25 23:08:14]; the P.5 plan section, placement
  proposed [git 303f6c6, 2026-09-26 00:02:08]; placement approved
  [git 0ca267e, 2026-09-26 00:18:42].
- **Elapsed**: from D11's registration to the build commit, about 18 hours of
  wall time [git 863d103 → 61b98a2]. Not recoverable: working time on the
  build. The build is one commit, and the previous commit, 9 minutes earlier, is
  unrelated P.4 work [git f1bcb28].
- **Scale of change**: 13 files, 485 insertions, 412 deletions [git 61b98a2].
- **Findings**: 2 register rows closed (D2, D11). Register open count after:
  34 [git 61b98a2].
- **Estimate versus actual**: none recorded for P.5.
- **Acceptance**: full suite 4038 passed, 0 failed, 0 errors, confined on 4
  workers in 24 s and plain in 60 s [git 61b98a2]. Five controls fired, as
  above. On the host, deploys refused until re-approval, then passed with all
  nine devices round-tripping [CLAUDE.md]. The re-approval commit, `be60f59`, is in the list's `config_repo` on the host,
  not in the code repository, so it is cited from CLAUDE.md and not verified here.

**6. Where it left the product**

An approval now claims only that a person approved this template text, and a
device the template cannot reproduce is blocked alone at its own plan.

### P.6 — ZTP as a third address source (Lab 8)

*Backfilled 2026-09-29.*

**1. What it was**

Zero-touch provisioning of one new device, as a third onboarding address source
beside `static` and `dhcp`. A device boots with no configuration, gets an
address the tool reserved for it, fetches its bootstrap config from the tool,
and is then reached and finished by the unchanged phase 2. It covered course
Lab 8, and it measured ZTP's states on a throwaway, `bp-ztp-a`, before Stage 7
would draw them [NSOT_PLAN.md P.6; P6_ZTP.md §0, §6].

**2. How it was implemented**

The host was measured first: Kea 2.4.1 had no `reservation-*` commands, its
config file could not be written back by Kea, and nothing served TFTP
[P6_ZTP.md §1]. Six decisions followed. Their D-numbers are local to
P6_ZTP.md, not register IDs.

- **D1**: the ZTP subnet takes its reservations from an include fragment the
  tool owns. The writer (`modules/nsot/ztp.py`) takes a set of devices and
  returns per-device outcomes. It refuses conflicts and D4 hits, tests the
  candidate with `kea-dhcp4 -t`, swaps it in by rename, reloads, restores on
  failure, and reads back from the running server [git 1b7e639].
- **D2, D5, D6**: a read-only TFTP responder in the tool
  (`modules/nsot/ztp_responder.py`), with no write path. A systemd socket
  binds port 69, so the process holds no capability. It renders per request,
  keeps no copy, and serves only a pending ZTP device, at its reserved
  address, the file option 67 names, after writing a reveal row
  [git 7416cbf; P6_ZTP.md D2, D5, D6].
- **D3**: the server address is derived from Kea's serving interface, never
  read from a setting [P6_ZTP.md D3].
- **D4**: a reservation never carries a route or a resolver, enforced as a
  check at plan time and as a job-health row [P6_ZTP.md D4].

`ztp` became a stated source in `build_plan()`, with the reservation last among
phase 1's fallible steps [git 8ae4faa]. The pending row derives ZTP stages from
Kea and the responder's audit rows [git 4095240]. Abandon removes the
reservation first [git ba2e23f].

**3. Issues encountered**

Measurements [P6_ZTP.md §8; P6_ZTP_PROBE.md]:

- **M1 (2 runs).** The image's install overlay held a saved startup config, so
  removing vrnetlab's day-0 ISO was not enough. PnP defers to any startup
  config. After an erase, qemu's network answered Gi1 first, and AutoInstall
  stopped at that first lease. Unpredicted: PnP sent Cisco a HELLO carrying
  the device's UDI.
- **M2** had no separate run; M1 and M3 answered its questions.
- **M5 (1 run).** The include is live, and a `config-set`-only reservation
  vanishes at a restart.
- **M3 (2 runs).** Run 1 measured the old launch script, through a stale bind.
  Run 2 held: Kea's reservation answered and the node asked for exactly the
  named file by TFTP. It also broadcast DNS queries for `tools.cisco.com`
  (8 sent, 0 replies).
- **M4 (3 boots).** Boot 1: the responder crashed on systemd's dual-stack
  socket, hiding a second defect (the peer matched no reservation), and
  AutoInstall gave up after about 2.5 minutes. Boot 2: the config applied, but
  SSH was refused because no RSA key was generated, and the GUI overwrote
  Verify's diagnosis. Boot 3: phase 2 promoted with a 200 while the device
  had no startup config.

Register rows:

- **C48**: `tftp_server_ip` names an address the host lacks.
- **C49**: a reservation could vanish at Kea's restart.
- **C50**: an unknown lab name resolves to rcn-lab1's paths, silently.
- **C51**: a GET with a list name created that list [git 23f3fb6].
- **C52**: a ZTP render used the weaker `password 0` form.
- **C53**: the CLI rotation never saved the device; `s1`'s NVRAM booted the
  credential B13 exposed [git d91f494].
- **C54**: job health kept a rotation row for a departed device.
- **C57**: the persist step had never run in a real onboarding
  [git dc3dec8, registered just after].

Without an ID: Kea's AppArmor profile held a root `kea-dhcp4 -t` to the file's
mode bits [P6_ZTP_PROBE.md, D1]; `RESERVED_INTERFACES` is keyed on the platform
[P6_ZTP_PROBE.md §11 Q2]; three controls first proved nothing [git 7416cbf,
8ae4faa, ba2e23f]; three observations recorded and not explained
[P6_ZTP_PROBE.md]. The operator named the class: a rule keyed on the platform
when it was really about the deployment [git 87df56c].

**4. How they were resolved**

- **M1**: the patch boots the base disk; passthrough silences Gi1; the HELLO
  became D4 [git 944876c, f7388b3].
- **M3**: the patch reports which disk it boots [git b69f8d1]. TFTP was
  decided, and D4 gained a second condition: nothing on the segment answers
  DNS [git 365a143].
- **M4**: one peer normalisation for identity and reply [git 4146a8e]; an
  `asked_not_served` stage and a responder health row [git c1471f7]; the key
  generated and the diagnosis kept [git 5ca02db]. Boot 3 was mitigated by the
  operator's hand `write memory`, then fixed for every source: phase 2 saves
  and reads back the startup config before promotion [git f94c41e].
- **C48**: deferred. The operator decided to derive the address; the work is
  in 7.4 [OPEN_FINDINGS.md C48].
- **C49**: fixed by D1, shown by M5 [git 1380b9e].
- **C50**: open. Bucket B, critical: it blocks 7.3's rotate and retire
  [OPEN_FINDINGS.md C50].
- **C51**: fixed in Stage 7.0 [git 61f74b7].
- **C52**: fixed [git 77e909a].
- **C53**: fixed, and nine of nine then carried their credential
  [git d433c5c].
- **C54**: the operator withdrew the heartbeat member, and a teardown step was
  added [git 732c3bc]. The rotation row was fixed on 2026-09-28
  [git 185a4d3].
- **C57**: closed by R1 on 2026-09-28 [git c98f2b7].
- **`RESERVED_INTERFACES`**: deferred to a permanent device; no register row
  found [P6_ZTP_PROBE.md §11 Q2].
- **P-M4f** (a promoted device refused on a second request): left open and
  placed first in the teardown [git d162c0c]. Not recoverable: whether it
  ran.

**5. Numbers**

- **Commits**: 21 by subject [git 1bdab6c, 2026-09-26 13:20:00 → git 77e909a,
  2026-09-26 22:16:18]. Rule: the subject contains "P.6". Six commits whose
  bodies tie them to P.6 make 27, ending at git 732c3bc (22:41:39). The
  selection is ambiguous.
- **Elapsed**: 8 h 56 m from plan to close, including P.4 and P.5 work until
  17:16; 4 h 50 m from scoping to close [git 21d5b1f → 77e909a].
- **Runs**: 8 [P6_ZTP.md §8; git 77e909a].
- **Findings**: 7 rows opened (C48 to C54), plus C57. Open count 34 → 39
  [git 61b98a2, f94c41e]. The count at close is not stated.
- **Suite**: 4038 → 4273 passed [git 61b98a2, 77e909a]. Only P.6 commits lie
  between.
- **Estimate**: none recorded [NSOT_PLAN.md P.6].
- **Acceptance (Lab 8)**: a configless device was leased from a reservation
  the tool wrote, fetched its config from the tool (each fetch a reveal row),
  was reached, rotated, saved and read back, recorded in NetBox, promoted, and
  rebooted into its saved config [P6_ZTP.md §8]. Teardown was clean: census
  exit 0, the reservation removed and read back, r1's route to r6 unchanged
  [P6_ZTP_PROBE.md, teardown]. The caveat: the node had to be persuaded to
  ask. Lab 9 was not demonstrated within P.6 [P6_ZTP.md §8].

**6. Where it left the product**

The tool can reserve an address, serve a bootstrap config and onboard a
configless device end to end, and every onboarding now saves the device before
promotion.

#### Sources read (P.5, P.6)

- docs/NSOT_PLAN.md: P.5 and P.6 sections.
- docs/P6_ZTP.md: all, including §8's ledger.
- docs/P6_ZTP_PROBE.md: predictions and observations for M1, D1, M5, M3 and M4,
  the teardown result, §9, §10 and §11 Q2.
- docs/OPEN_FINDINGS.md: rows D2, D11, C48 to C54, C57.
- docs/NSOT_FEATURE_AUDIT.md §8c.
- docs/NSOT_STAGE7_PLAN.md: concept table, 7.4 and 7.6 rows, R2.
- docs/NSOT_WRITEUP_NOTES.md and docs/WRITEUP.md: searched; no P.5 or P.6
  content.
- CLAUDE.md.
- git: log over 2026-09-26 12:00 to 2026-09-28 03:00; bodies of 61b98a2,
  8ff6698, 1b7e639, 7416cbf, 8ae4faa, 4095240, ba2e23f, 23f3fb6, 4146a8e,
  c1471f7, 87df56c, f94c41e, d91f494, d433c5c, d162c0c and 77e909a; `-S`
  searches for register-row origins.

#### Could not recover (P.5, P.6)

- Working time on P.5's build: it is one commit, with unrelated work
  immediately before it.
- The host's re-approval commit `be60f59`: a `config_repo` commit on the host,
  cited from CLAUDE.md, not verified here.
- Whether P-M4f (a promoted device refused on a second request) was run, and
  its result.
- The register's open count at P.6's close: no commit states it.
- Whether the documents' 2026-09-27 dates are UTC by convention. They are
  consistent with UTC, but no convention is recorded.
- Any time or effort estimate for P.5 or P.6: none was found.

### P.9 — The monitoring profile, steps (a) to (c)

*Written 2026-10-01, when step (c) closed. Steps (a) and (b) closed on 2026-09-30 without an
entry; theirs is reconstructed from the plan, the register and git, and says where that ran
out. Step (d) is open.*

**1. What it was**

Every device, new and existing, carries what its integrations need (SNMP, syslog, NTP,
telemetry, LLDP), from ONE owner: a committed profile per network, derived from the connectors
the network uses. It came from r6 being called "unreachable" by an SNMP alert when its
configuration simply had no SNMP [NSOT_PLAN.md P.9; MONITORING_PROFILE.md §1].

**2. How it was implemented**

- **(a) The model** [git 38c64ef]: `profiles/monitoring.yml`, data in the parsers' `host_vars`
  shape; `profile.effective()` is the one merge (the device's own value wins, an empty value
  never overrides, an exclusion carries its reason), called by every render of intent; the
  deploy plan attributes `from_profile` lines apart.
- **(b) Existing devices** [git 39e49d2, 1954ce7]: PROPOSE (derived from the connectors, the
  fleet the cross-check, confirmed by hash and committed as the person) and APPLY (the deploy
  scoped to the profile's lines). Connectors got a home in Settings [git 3ffb4ac].
- **(c) New devices** [git bf13c4e and the adopt commit]: a device being onboarded or adopted
  has no full intent, so the program is computed from its CAPTURE
  (`profile_apply.for_capture`: its own parse rendered alone and with the profile). Onboarding's
  Verify became a preview and a confirm (the operator's decision 1): the preview reads the
  pending device and draws the RW removal and the profile program, masked, with a fingerprint;
  phase 2 recomputes it and sends nothing if it moved, then sends the profile after the RW
  removal and before the save, and reads it back. Adopt does the same from the capture its
  preview reads with the supplied credential.

**3. Issues it found** (register IDs)

- During (b) and its host run: C253 (LLDP and CDP read from a key no parser writes), C254
  (what an absent `cdp run`/`lldp run` means, unmeasured), C255 (SNMP never proposed: per-device
  fields compared), C256 (the topology renderer held outside the repository), C257 (host steps
  with no kind), C258 (connector settings file-only), C259 (Prometheus targets regenerated on
  inventory writes only), C260 (the Overview hid golden-versus-intent), C261 (profile screens
  misdescribing changes), C262 (r6's `cdp run`), and after staged run 8 C269 (r1 to r4 holding
  `cdp run` in their own intent) [OPEN_FINDINGS.md].
- During (c): a `to_send` row carried the community unmasked (caught by its own test before
  commit), and a measurement corrected an assumption: an unmodelled line counts as `unmodeled`,
  never as a render gap, so it is named and does not block.
- Outside its scope, found by its first apply on the host: C278 and C280, the publication gate
  holding four pushes for one more copy of an acknowledged community (r6 gained the fleet's
  community through the profile).

**4. How each was resolved**

C253, C255, C257 to C261 fixed the day they were found; C254 measured (staged runs) and
recorded per platform; C256 closed on measurement; C262 removed through Mode B on IOS-XE after
staged run 8; C269 scheduled as the operator's; C278 and C280 fixed [OPEN_FINDINGS.md].

**5. Numbers**

Commits (rule: subjects naming P.9, the profile or its findings, `git log --since=2026-09-30`):
13: twelve from 2f3a535 (2026-09-30 12:13, the design) to bf13c4e (2026-10-01 00:27), and the
adopt commit after it. Elapsed
about 13 hours, interleaved with the update button's runs, C270 to C280 and C271/C272. Findings
recorded: 11 in (a) and (b) (C253 to C262, C269), 2 outside its scope (C278, C280), none new
in (c). **Estimate versus actual: no forecast was made for P.9**, none in the plan, the profile
design or the register, so there is nothing to check; recorded so the next profile-sized item
gets one, from a finished stage of the same kind.

**6. Where it left the product**

A new device is monitored at promotion, through onboarding or adopt; an existing one by Apply
from its row. Not built: (d), the batch Apply from the fleet coverage view, and the profile's
IP SLA policy. SNMPv3 is the profile's next SNMP change (Stage 9).

*Not recoverable:* the minute-level split of (a) and (b)'s time between the profile and the
work interleaved with it on 2026-09-30.

**Step (d), in progress (added 2026-10-01, overnight, while the detail is in hand; the entry
closes with (d4)).** (d1) Monitoring > Coverage in v2 [git 2986b5c]. (d2) the batch Apply as a
v2 preview showing the rollout order (reorderable), one confirm, and a batch run as a job that
shows each device's step as it goes [git a6753de], its confirm clicked in a real browser
[git 460fe67]; building it made the deploy plan and apply one function each
(`routes.deploy.plan_devices`, `apply_batch`), called by the old routes and the job alike.
(d3) a device's Monitoring tab opens with what it is monitored by, with Apply where the profile
supplies a gap [git 3f27cb4]. Issues found: none new in (d2) or (d3); C290 (a running IP SLA
operation cannot be edited in place) was designed and built the same night as (d4)'s
prerequisite [git 1215d3e], its delete refused until staged run 9 measures it. Commits: 4 from
03:42 to 03:51 local (UTC-6) on 2026-10-01. Not recoverable: when (d2)'s build began (it
was written in a session summarised before its first commit, after C290's at 03:21). (d4), the profile's IP SLA policy, waits on staged run 9.

### P.15 — Several people at once (open): the decided fixes

*Written 2026-10-02, when the last of the fixes the operator ordered closed (R5's per-device
receipts). P.15 stays open: the audit's other rows are scheduled by risk, and its multi-worker
half lands with 9.S.*

**1. What it was**

Every write path made safe against another person, another tab and, after 9.S, another
worker process. A read-only audit (CONCURRENCY_AUDIT.md, each finding checked by a second
reader) ranked the write paths; the operator ordered the high and medium ones that affect
today's single-process install fixed first: R1, R24, R25 (the list repository), R4 (the
approval queue), then R5, R13, R19, R20, R28, and R2 [NSOT_PLAN.md P.15; CONCURRENCY_AUDIT.md
section 1].

**2. How it was implemented**

- **The repository** (R1, R24, R25) [git a5e7a2f]: one `flock` across processes from the first
  write to the last tag; staging and commit refused outside it; a commit names its paths; a
  save compares HEAD; retire's undo puts back only its own paths.
- **The approval queue** (R4) [git 723e758]: one lock across processes, an atomic replace, an
  unreadable queue refusing every write, reads that write nothing.
- **R20** as register C326 [git acb0f49]: an approved revert closes as approved.
- **R2** [git c3a21a6]: the intent editor's save carries the blob the person opened and is
  refused under the repository lock, naming who moved it, when intent moved since.
- **R5** [git 5bb86cb and the per-device receipts commit]: Update, `nmas-deploy` and every
  restart refuse while a device is held; the two restart routes removed; an operation whose
  process ended is kept and drawn on Needs attention; each device's receipt row written as it
  finishes, commit pending, and completed after the batch's commit, drawn PENDING by every
  reader.
- **R13** [git a682b4b]: the template approvals record locked, refusing when unreadable, the
  gate counting what is committed.
- **R19** [git 43aa91c]: drift state locked and never emptied by an unreadable read; one drift
  run per list across processes.
- **R28** [git 2d029a5]: one run per reader at a time, and never an older value stored over a
  newer one.

Each has a test that runs the collision for real where it can (a second process, a child that
holds devices and dies), and every check was shown able to fail.

**3. Issues it found** (register IDs)

C345 (the approvals record's damaged copy and a write's temp file inside the repository, where
seeding staged them), found building R13 [OPEN_FINDINGS.md]. Caught by the fixes' own tests
before commit, never registered: R13's lock first placed inside `templates/`, and R19's run
lock resolved through the active list (which created a list) and then by a relative path
(which wrote into the checkout).

**4. How each was resolved**

C345 fixed with a test that seeding never stages either file [git 8f84711]. The two caught
before commit were moved: the approvals lock beside the repository, the drift run lock under
`DATA_DIR/drift_runs/<list>.lock`.

**5. Numbers**

Commits (rule: subjects naming P.15, a CONCURRENCY_AUDIT row or C326, since the audit's commit
b217f12 at 2026-10-01 23:10 UTC-6): 10, the audit and nine fixes, the last being the per-device
receipts. The fixes run from acb0f49 (2026-10-02 11:52 UTC-6) to that commit. Findings recorded:
1 (C345). **Estimate versus actual: no forecast was made** (none in the plan, the audit or the
register); recorded so the remaining rows get one, made from this finished batch: ten rows in
about one working day, interleaved with the sidebar badge and the sign-offs.

**6. Where it left the product**

In one process, two people or two tabs can no longer erase each other's intent, approvals,
drift state or reader values, or commit over each other; nothing restarts the app under a
running operation; and an operation cut off by a process exit leaves a receipt for each
device it finished and a Needs attention row for the rest. Not built: the per-device progress
step under `deploy_max_workers > 1`, the audit's other rows, and everything that needs more
than one worker (9.S).

*Not recoverable:* when each fix's build began; the commit times bound only its end.

### P.15 — Several people at once (open): the second batch, across processes

*Written 2026-10-04, when the batch's last commit (ede1557) passed CI (#388). P.15 stays
open.*

**1. What it was**

The away queue's item 3 (the operator, 2026-10-04): the audit's remaining rows that need no
screen, highest risk first, each with its control. They were R6 (the manifest), R3 (the list
registry), R11 (the SSH session budget), R12 (an approval covers what was validated), R14
(templates and bindings written whole), R15 (hash-checked writers under the repository lock)
and R16 (a confirm carries its hash) [CONCURRENCY_AUDIT.md section 1].

**2. How it was implemented**

- **R6, R3** [git c420bcd]: the manifest is written under the repository's cross-process lock
  (`manifest.lock`, `load_for_write`), atomically, its temporary file beside the repository.
  The list registry's four writers hold one `PathLock` and replace the file atomically. R3's
  per-session half is a decision (below).
- **R11** [git aceb188]: the per-device SSH session budget is held in `flock`ed slot files, so
  it holds across processes. A refusal names each holder and its pid.
- **R12, R14** [git d50085b]: an approval fingerprints the template before validation and
  refuses, naming both fingerprints, if it moved before the record is written. Templates and
  bindings are written atomically, and unreadable bindings refuse (409) instead of reading as
  empty.
- **R15, R16** [git ede1557]: bulk intent, the profile proposal and IP SLA policy each run
  compare-then-write under the repository lock. `apply_batch` and the restore's `run_targets`
  refuse a confirm with no command hash, rather than skipping the comparison.

Each fix has a test that runs the collision for real where it can: a second process holding
the lock or the slot, or a template moved between validation and record. Every check was shown
able to fail.

**3. Issues it found** (register IDs)

- C431: `test_scale`'s 50 ms bound refused one gate under the three-shard load.
- Not registered, recorded in the audit: R16's compare happens before the device hold. Measured
  narrower than the audit stated, because the pipeline's fresh capture catches a device that
  moved.

**4. How each was resolved**

- C431 is open (bucket C), with its measurement named.
- R16's ordering is recorded and not restructured.
- **Three halves are the operator's decisions, written with a recommendation each** in
  CONCURRENCY_AUDIT.md:
  - R3's per-session active list: option A, per session, is recommended. It is decided with P.8
    (NSOT_P8_DESIGN, section 5).
  - R12's client half.
  - R14's client half.

**5. Numbers**

- **Commits:** 4, from c420bcd (2026-10-03 21:19 UTC-6) to ede1557 (2026-10-04 01:10 UTC-6),
  interleaved with C406, the canvas boards and the topology brief.
- **Diff:** 33 files, +1,187 −204 [git show --stat].
- **Findings recorded:** 1 (C431).
- **Estimate against actual.** The first batch's forecast, made from that finished batch, was
  "ten rows in about one working day". This batch was seven rows (R3 half done) in four commits,
  inside one evening's session, shared with other work. The forecast held, with time to spare.
  This was the same kind of work (a cross-process guard on one store, each with its collision
  test), so the forecast stands for the audit's remaining medium rows: R17, R18, R21 to R23,
  R26, R27 and R38 to R41.

**6. Where it left the product**

Across worker processes, the manifest, the list registry, the SSH session budget, template
approvals and the hash-checked writers no longer lose or interleave writes, and no apply runs
without the hash its preview showed. Not built: R3's per-session half, the two client halves,
the remaining medium rows, and 9.S's multi-worker install itself.

*Not recoverable:* when each fix's build began; the commit times bound only its end.

### P.15 — Several people at once (open): the third batch, the remaining medium rows

*Written 2026-10-04, when the batch's last row (R26's code half, 4aa81be) was pushed. CI was
still running then: each push cancelled the run before it (#393 to #399), so the batch is
verified by its last run (#400), recorded in the next entry. P.15 stays open.*

**1. What it was**

The operator's order of 2026-10-04: "continue P.15's remaining medium rows", and take the
recommendations for R12's and R14's client halves unless either changes a screen. The rows
were R12 and R14 (client halves), R17, R18, R21, R22, R23, R26, R27, R38, R39, R40 and R41,
plus R30 (low), which the batch's first gate found live.

**2. How it was implemented**

One commit per row, each gated, each with a test that runs the collision for real where it can
(two processes, a held device, a held lock), and every check shown able to fail:
- **The template editor** sends what it opened and what it showed (R14, R12) [git e423eda].
- **Keys are created once** across processes (R30) [git e423eda].
- **Settings forms send only changed fields**, refused when moved (R17) [git effb66d].
- **The publication record** is locked; an unreadable one says so; one publisher pushes the
  HEAD it reads (R18) [git 72be597].
- **The Kea ZTP fragment** is locked from read to read-back (R22) [git 07da602].
- **A list is never deleted** under a running operation (R38) [git 23c2e8b].
- **Onboarding's Create and Abandon** hold the device (R23) [git b6f10bf].
- **The publication acknowledgement** covers only the values it showed (R41) [git d3d31b5].
- **One NetBox writer per list** (R21) [git b1f6914].
- **router.db and the lab sync** are written by one process at a time, with a host step
  (R40) [git b8f872c].
- **One hold key per list**, and a probe never refuses an acquire (R26) [git 4aa81be].

**3. Issues it found**

- **R30, found by the gate itself.** R3's three-process test, on a fresh store, had one child
  read a half-written `key.key`. Two processes that both find no key each write their own,
  and whatever the first encrypted is lost.
- **R17's change exposed two defects.** The NetBox write switch, sent alone, was dropped by a
  branch waiting for the URL. The modal never read the general block's answer, so a refusal
  there would have been silent.
- **R40's measurement found the sync already serialised on the host**, by a wrapper outside
  the repository. Its "skipping" exits 0, and the persist then fails closed at its next
  stage.
- **R26's control reproduced the audit's words exactly:** 15 of 300 acquires refused as "?
  by unknown, held for 497538 h".
- **Two gates refused on tests:** a session-key test matched a code comment as a substring,
  and the wizard tests stubbed the plan with no hostname.

**4. How each was resolved**

- R30 is fixed in its own commit's batch: one helper links a whole key into place.
- R17's two defects are fixed in R17's commit.
- The substring test was rewritten to parse.
- R27 (the holder strip, a new element) waits for a mockup. Its broadcast half waits for
  C435, found surveying its subscribers: Coverage re-ticks every row on `goldens`, so a
  broadcast on every write would reset a person's selection.
- R39 is a decision, with removing the terminal now recommended.
- R26's lease and release is a decision, with a lease on v2's refusal card recommended.
- R23's binding to its dry run waits for v2's onboarding screen.

**5. Numbers**

- **Commits:** 10, from e423eda (2026-10-04 11:56 UTC-6) to 4aa81be (12:56 UTC-6).
- **Size:** 73 files, +2,461 −303 [git show --stat].
- **Rows:** 12 fixed or half-fixed, with R30 among them.
- **Gate refusals:** 3 (R30's race, the substring test, the stubbed tests), each fixed
  forward before the commit.
- **Estimate against actual.** The second batch's forecast (from the first: "ten rows in
  about one working day") said these rows would take about a day. They took about an hour
  and a half from the operator's decisions to the last push, beside host-step updates and the
  operator's 14.11 to 14.14 reports. The forecast held, faster again. The kind is the same (a
  cross-process guard on one store), so its multiplier now overstates by about five times.
  The low rows (R31 to R37) are the same kind, and a forecast for them should start from this
  batch's pace, not the first.

**6. Where it left the product**

Every medium-risk write path in the audit now holds across processes, refuses by name, and
never reads an unreadable store as empty. The exceptions:
- the holder strip (R27), waiting for a mockup;
- the terminal (R39), a decision;
- a lease (R26), a decision;
- the multi-worker half (9.S).

*Not recoverable:* when each fix's build began. Several were drafted while the previous gate
ran, so the commit times bound only their ends.

### Side campaign note — the history store (C406), built; its host steps the operator's

*Written 2026-10-04 at the build (87a2343, CI #384). Not closed: the history datasource is set
by the operator's host step 14.14, and its first real long range follows that.* Measured first:
Thanos Query answered the same queries as Prometheus (one difference of 2.13e-16, summation
order). Built: a panel range longer than `metrics_live_retention_days` reads the datasource
`grafana_history_datasource_uid` names, with a wide step, and says "from the history store";
unset, such a range is refused naming the setting, never trimmed. Host steps written in full:
14.12 (Loki to 90 days), 14.13 (Thanos query auto-downsampling), 14.14 (the history datasource,
its uid read from the app's store, shown and confirmed). Numbers: one commit, 14 files, +389 −22,
one new test file (`tests/test_history_store.py`). No forecast was made; none is checked.

### P.7 and P.8

Decided on 2026-09-28, not built: P.7 (alert rules generated and tested, its own item before 8.6) and P.8 (per-list settings: two lists are two networks) [NSOT_PLAN.md P.7, P.8]. Entries are written when they close.

### P.21 — Credential expiry and health

*Written at close, 2026-10-03 (overnight), except the declared Grafana expiry's field, which waits on the operator's decision.*

1. **What it was.** No code read any credential's expiry or age against a threshold, and Grafana's probe counted a refused token as up (C354). The operator signed off a design: exposed expiries warned 30 and 7 days ahead, ages over 180 days warned, Grafana's expiry declared when its token is entered, a refusal a danger row at once, anything beyond a year listed with no row [NSOT_PLAN.md P.21].
2. **How it was implemented.** One reader, `credential-health`, hourly, metadata only: NetBox's token by the suffix NetBox shows, Proxmox's token record, the TLS handshake of the verified HTTPS service, Grafana's declared expiry, each device's last rotation, each SNMP community's `last_rotated`. Its value feeds a Needs attention source. Refusal is the integrations reader's: the shared request helper reads 401 and 403 as `refused`, and Grafana and Loki ask endpoints that need their credential.
3. **Issues encountered.** The declared Grafana expiry is a Settings field, and Settings has no v2 page, while the same night's rule forbids new capability on a v1 page; and a device's last SAVE is not its last rotation, which the age reader had to tell apart (C362's states made that possible).
4. **How they were resolved.** The setting exists, is documented as waiting on its screen, and is honoured when set; until then Grafana's token is listed as "no expiry declared" and a refusal still raises a danger row within a minute. The age reader counts only rotation rows.
5. **Numbers.** One commit [git: this commit]. 24 tests in `tests/test_credential_health.py` and 5 more in `tests/test_integration_health.py`; nine controls, each failing its aimed tests. Findings closed: C354. **Estimate versus actual:** no forecast was made; the reader pattern (the fifteenth) made it about half a device card's time.
6. **Where it left the product.** An expiring, expired, refused or old credential is in front of a person with where to renew it and where to put it, before it breaks a connection; 7.6's Credentials page draws its list from the same stored value.
7. **Its first real run (2026-10-03, the operator) found three reader defects and one wrong level, all passed by the suite.** NetBox 4.6 lists a v2 token by its key, never by any part of its secret, so the suffix match found nothing (C378). The pinned `cryptography` 41.0.7, on the host and in CI, has no `not_valid_after_utc` (C379). Proxmox's PVEAuditor token cannot read its own record, and it is not widened; its expiry is now declared, as Grafana's is (C380). An unread expiry was drawn as a Warning (C381). Every one passed because its test was built on a shape typed from memory. The tests were rebuilt on real captures (NetBox's list, Proxmox's 403, and a real TLS handshake in CI's venv), each failing as the host did before its fix. The two declared-expiry fields are on today's Settings as the first recorded exceptions to the no-new-v1 rule.

### Coverage's not-reporting reader (the first of Coverage's three steps)

*Written at close, 2026-10-03 (overnight). The grid and the combined deploy are separate steps.*

1. **What it was.** Coverage said only whether a template was CONFIGURED. Artboard A (signed off 2026-10-02) adds a fourth state: configured, but its data not arriving. The cell says for how long and links to where the cause is found, never to a redeploy [NSOT_GUI_BRIEF.md 14.3; NSOT_STAGE7_PLAN.md, the Coverage redraw].
2. **How it was implemented.** First the read-only measurement on the host. The SNMP jobs are per platform, and every target came from a generated file named in its `__meta_filepath`. Telemetry is labelled `source`. The device's name in a syslog line follows IOS's sequence number. The installed heartbeat rules hold a measured window for every device. Then one reader, `coverage-reporting`, every 60 s, one query per source for the fleet. It stores ARRIVALS only, and `monitoring_coverage` judges each configured cell from them. A failing or stale reader makes a cell unjudged, never "not reporting".
3. **Issues encountered.** The first two regular expressions for the device's name were wrong: they assumed the name followed the sequence number. A flat window of twice the heartbeat period would have flagged s3, which beats about 7 times an hour. One control passed, because in today's lines rsyslog's hostname field equals the device's name.
4. **How they were resolved.** The expression was measured against the anchored per-device query, and it agreed on every count over 24 h. The heartbeat is judged by each device's own alert window, so Coverage and the alert agree. The test gained C13's measured shape (an address in rsyslog's field), and the control then failed.
5. **Numbers.** One commit [git: this commit]. 23 tests in `tests/test_coverage_reporting.py`, on a real capture from the host; nine controls, each failing its aimed tests. Findings: C376 recorded (Loki's series limit at fleet scale). **Estimate versus actual:** no forecast was made; a reader of the 7.2 kind.
6. **Where it left the product.** Today's Coverage table shows a configured template whose data stopped as its own state, with its age and the tab to look at. The redrawn grid draws the same verdicts as icons.

### Coverage's grid and selection (the second of Coverage's three steps)

*Written at close, 2026-10-03 (overnight), and extended the same night by NTP and LLDP's columns. The combined deploy is the third step.*

1. **What it was.** Artboard A's grid: icons only, with the why on hover. Selection only through the row boxes, and a bar naming what is ticked, with Deploy missing templates and Clear [NSOT_GUI_BRIEF.md 14.3].
2. **How it was implemented.** The table was redrawn from `fleet()`'s states, with no new server state. The selection is an Alpine component in the CSP build, beside the batch Apply's, with its words a pure function. The ticked row is highlighted by the stylesheet's `:has`, with no script. Deploy missing templates opens the profile's batch preview until the combined deploy replaces it.
3. **Issues encountered.** The board draws IP SLA's ring as plain. The operator's decision of the same day says IP SLA is reached from its cells until it folds into the profile. The test fixture that installs the reader replaced the lab's settings, not wrapped them, and that turned a gap into "not used".
4. **How they were resolved.** IP SLA's ring is the link, its words on hover; this is named for the operator's review. The fixture wraps whatever is installed.
5. **Numbers.** One commit [git: this commit]. 7 tests in `tests/test_coverage_grid.py` (one in a real browser), and the old table's tests moved to the grid; six controls, each failing its aimed tests. Screenshots taken in light and dark.
6. **Where it left the product.** Coverage reads like the signed board: the answer first, one icon per cell across its seven templates, and a selection that says what a deploy would send to whom.
7. **NTP and LLDP (the second commit).** Their columns are the grid's alone, never Needs attention rows. An absent `lldp run` is LLDP off only where the platform's default is measured off (platform_defaults.json). On IOS-XE it is not measured, so r6's real golden reads unknown, never "not configured". Whether NTP synchronises and whether LLDP finds neighbours is not read yet, and the cells say so. A first draft let the reader's absence call them unknown; a test caught it. 5 more tests, five controls.
8. **The host's shape (C377, the operator on 87e86c7).** Ticking a box did nothing on the host. The served script and the CSP were the tested ones; the data was not. Every device there had nothing the profile could send, so all nine boxes were drawn disabled, against the signed "no box on a fully covered device". The real-browser test had always run on a fixture with one deployable device. It now runs on the host's shape too. It failed as the host did before the fix, and no box is drawn where nothing can be deployed.

### History as one timeline (C369; board D)

*Written at close, 2026-10-03.*

1. **What it was.** The sidebar's History read git commits only, and a device's History tab read every per-device record: two readers of one history. The operator found r2's persist, windows, exports and rotations on its tab and none of them on the page. Board D (signed off 2026-10-03) makes them one timeline with one reader. A device's tab is that timeline filtered to the device, and a check holds the two to the same rows [OPEN_FINDINGS C369].
2. **How it was implemented.** `history_sources.timeline()` is the one reader. Its 17 sources each read their store once for the fleet: the 14 per-device ones, plus three that belong to no device (other commits, baseline decisions, app updates). Every row carries every device it is about, `[]` for the fleet's own. Golden and intent read one git log each, with one read of renames. A device's view follows its file to find candidates; the commit's own files decide. Filters by device, person, kind (Commits a kind) and time are in the address. One drawing, `_timeline.html`, serves both screens.
3. **Issues encountered.** git 2.53 refuses `--follow` with `--full-diff`. A trailer's value ends with a newline, which cut the header short. `git log -- .` skips empty commits, and a measurement that changed no golden is one. The parity check failed three times on its first runs, each time on a real divergence: a device view narrowing a row to itself; `--follow` attributing r3's creation to s8, a false claim the old tab also made; and a rename the device's own log never sees.
4. **How they were resolved.** The device view takes two bounded reads instead of `--full-diff`. The header ends with its own separator. The trailer reads take no pathspec. Each row keeps its full device list, and inclusion is by membership. Renames come from one read of all renames, applied to every row by time in both views.
5. **Numbers.** One commit [git: this commit]. `tests/test_history_one_timeline.py` (4) is the check; `tests/test_history_v2.py` (28) was rebuilt from the Commits tab to the timeline; the browser layout test was moved to the timeline. Five controls, each failing its aimed tests. Screenshots in light, dark and 390 px. **Estimate versus actual:** no forecast was made. It ran longer than a 7.2-kind read-only screen, because the readers were merged.
6. **Where it left the product.** "What happened recently" is answered in one place, for the fleet or one device, and the two can no longer disagree.

### The break-glass record on Credentials (board 7)

*Written at close, 2026-10-03.*

1. **What it was.** The break-glass export lived in a modal on today's pages. The operator's revision of board 7 asked for four things: the browser confirms the download arrived intact; "Check a break-glass file" opens the copy a person keeps; an offline drill every 90 days; and all of it on v2 only. The placement review moved it to Source of truth › Credentials, because the record is fleet-wide (signed off 2026-10-03).
2. **How it was implemented.** Three commits on one page.
   - **The record's state** is read from job health's stored judgement, so no credential is decrypted per page view.
   - **A, the export,** draws the real preview and posts to the ONE export route.
   - **B:** the browser hashes the bytes it received against the server's sha256, and its verdict is recorded. `breakglass.currency` became the one judgement for job health's rows, the page and History.
   - **C** opens a kept file in memory and compares it by digest.
   - **D:** a CLI receipt is checked against a logged export, with a row once overdue.
   - **The openers:** every way in, today's included, opens Credentials.
3. **Issues encountered.**
   - The preview crashed on a credential the key could not open (C384).
   - A first version of the tests let a browser that echoed the server's sha256 pass, because every test download arrived intact.
   - Firefox under snap cannot read the test's /tmp for an upload.
   - htmx's out-of-band swap was needed so the record's card is never "none exported" above a finished export.
4. **How they were resolved.**
   - Undecryptable credentials are named and refused.
   - A real-browser test alters a byte in transit and expects Not intact.
   - The upload is written beside the browser's profile.
   - The intact answer redraws the record's card with it.
5. **Numbers.** Three commits. `tests/test_credentials_v2.py`: 38 tests, five in a real browser. Seventeen controls, each failing its aimed tests. Findings: C384 recorded and closed. **Estimate versus actual:** no forecast was made. It was the kind of 7.3's device cards, about a card per commit.
6. **Where it left the product.** The way back into the devices can be exported, confirmed intact, checked where it is kept, and drilled offline, from one page, with Needs attention saying when any of it lapses.
7. **Its first real run (2026-10-03, the operator) found that both buttons did nothing, and the suite had passed.**
   - **Why.** The record's card refreshes itself with `hx-select="#bg-record"`, and htmx passed that selection down to the Export and Check links inside it. Each answer was filtered to nothing and swapped in silently (C385). The host's log later showed the six clicks, each answered 200. Every browser test had opened the card by its address, which the server draws, and none clicked the button. It was the third time this shape had shipped (C338).
   - **The fix ended the class.** A structural check reads every v2 template: no request may inherit a selection, and every element that selects passes nothing down. The script makes any answer that cannot be drawn say "Couldn't load: <why>" in place (C388). That change also drew the refusal cards that answered 4xx and had been discarded the same way.
   - **The same run found three more defects.** The drill's heading and the line below it disagreed, because a relative age was drawn of a future time (C386). The drill command named a file the host cannot know (C387). A proxy injected scripts into the served pages (C389). The test browser had also been saving its downloads into the operator's Downloads, and every confined test process left a geckodriver running: 442 of them, holding 2.9 GB (C391, C392).
   - **The retry passed end to end.** The export downloaded intact; both kept files checked current, device by device; the drill was recorded, next due 2027-01-01.
   - **Numbers.** Six commits, 2a1e2b9 to 02506d4. Findings C385 to C393, all closed. Three new test files: `test_v2_swaps_never_silent.py`, `test_served_page_is_what_was_sent.py` and `test_home_untouched.py`. Eighteen controls, each failing its aimed tests.

## Part II. Stage 7

### 7.0 — The checks every later step is written against

*Backfilled 2026-09-29.*

**1. What it was.**
7.0 built the mechanical checks that the rest of Stage 7 would be measured by,
before any screen was rebuilt. There were four: every route reachable from a page
(or named as non-GUI, or allowlisted); every mutating route declaring what data it
invalidates, so panels re-fetch; "if a payload carries it, the screen shows it";
and the nine concepts taught where the action happens [NSOT_STAGE7_PLAN.md §8,
row 7.0]. Two register findings were gates that had to be fixed first: B1 and C51
[NSOT_STAGE7_PLAN.md "7.0 built"].

**2. How it was implemented.**
- **Reachability** (`tests/test_route_reachability.py`, with a shared reader,
  `tests/route_references.py`) reads the rendered pages and counts `url_for` in
  template source. It decides "read or write" per METHOD where one path mixes both
  [git 379b4d8; CLAUDE.md test table].
- **Invalidation** (`modules/invalidation.py`, client `static/js/nmas_invalidation.js`)
  gives each mutating route a list of data keys from a finite vocabulary. The
  response carries them in a header, and panels subscribed to a key re-fetch. A
  failed re-fetch marks the panel stale [git a8dce41; CLAUDE.md module map].
  This is the live-data contract's first half: it sees only changes a response
  announces. The server-sent half came in 7.2 (C58).
- **Payload to render** (`tests/test_payload_is_rendered.py`, `tests/payload_providers.py`,
  `tests/payload_render.py`) calls each declared route through the test client,
  records the keys of its real JSON, parses the shipped renderer for the keys it
  reads, and checks both directions, with floors and named anchors
  [git dca1071; NSOT_STAGE7_PLAN.md §5].
- **Nine concepts** (`tests/test_concepts_are_taught.py`) runs the shipped screen
  code in duktape against real payloads and asserts a visible, non-empty
  `data-concept` element, not text, which prose could match [NSOT_STAGE7_PLAN.md §4].
- Each check starts with a measured allowlist, pinned at a ceiling and compared
  exactly, so it can only shrink [NSOT_STAGE7_PLAN.md "7.0 built"].

**3. Issues encountered.**
Register rows introduced in 7.0's window (attributed by the commit that first adds
the row to OPEN_FINDINGS.md, `git log -S`):
- **C55**: `GET /monitoring/config` returned both SNMP communities in plaintext; the
  RW one was drawn nowhere. Found by the payload check [git dca1071; OPEN_FINDINGS.md C55].
- **C56**: four more GETs returned stored secrets, found when B11's sweep was
  re-planted over every store [git dc3dec8; OPEN_FINDINGS.md C56].
- **C57**: the ZTP phase-2 persist step had never carried a real onboarding.
  Registered in the same commit; acceptance 6's third case waits on it
  [git dc3dec8; NSOT_STAGE7_PLAN.md "7.0 built"].
- **C58**: response-keyed invalidation cannot see a change made after the
  response or on a schedule. Found reading the code behind acceptance 6
  [git 76f7ffa; OPEN_FINDINGS.md C58].
- Gates fixed at the start: **B1** (a drifted deploy returned the device's
  configuration) and **C51** (24 GETs created the list they were asked about)
  [git 9df50ed, 61f74b7; OPEN_FINDINGS.md B1, C51].

Found while building, not register rows [NSOT_STAGE7_PLAN.md "7.0 built"]: the
six `/netbox/query/*` routes had a claimed consumer and no caller; reachability
first split read/write per rule, and its control did not fail because
`/drift/settings` is two rules on one path; the invalidation hook keyed on the
endpoint alone, so a read or a refusal announced an invalidation; the concept
`approval-binds-a-set` described the retired approval scheme 2; one anchor named
`list_name` where the key is `list`; the GUI doc's route floors predated P.3 and
P.4's removals.

Defects in 7.0's own checks, found later in 7.1: **C87** (reachability counted
intent revert reached through a shared URL prefix), **C72** (fourteen empty record
collections in the payload fixtures), **C90** (a duplicate dict key hid a new
`RENDERS` entry) [OPEN_FINDINGS.md C72, C87, C90].

**4. How they were resolved.**
- B1, C51: fixed before the checks [git 9df50ed, 61f74b7].
- C55: fixed right after 7.0; communities are write-only on every route. The plan
  kept it out of 7.0 "because 7.0 changes no route's behaviour"
  [git dc3dec8; NSOT_STAGE7_PLAN.md "7.0 built"].
- C56: fixed before 7.1, as the operator decided [git 68d2739]. C57: closed on its
  marker by the operator's R1 run, 2026-09-28 [OPEN_FINDINGS.md C56, C57].
- C58: moved to 7.2; the server-sent announcement was built as 7.2 step 10, and
  some background jobs still do not announce [OPEN_FINDINGS.md C58].
- Hook keyed on method too [git 9264d97]; concept renamed
  `approval-binds-the-template`, and the harness now fails if the plan's table
  disagrees; `/netbox/query/*` to removal in 7.8; floors restated as 212 and 115
  [NSOT_STAGE7_PLAN.md "7.0 built"].
- C87 fixed [git c59eefd]; C90 fixed as a rule (`test_no_duplicate_dict_keys.py`)
  [git d987c02]; C72 open, bucket C/M [OPEN_FINDINGS.md C72].

**5. Numbers.**
- Commits: 5 core, `379b4d8` (2026-09-26 23:01:07 -0600) to `91c81fd` (23:32:19):
  the four "Stage 7.0 (n)" commits plus the hook fix `9264d97` the plan cites. With
  the two gates and acceptance 6's first run, 8 (`9df50ed` 22:44:08 to `76f7ffa`
  23:48:50). `dc3dec8` (C55's fix) is excluded: the plan puts it outside 7.0
  [git log; NSOT_STAGE7_PLAN.md "7.0 built"].
- Elapsed: 31 min for the core; 1 h 4 min with gates and the first acceptance run
  [git timestamps].
- Findings: register rows went from 92 to 96 across the window (C55 to C58)
  [row count at git 9df50ed^ and 76f7ffa].
- Measured at build: 212 routes, 218 (method, route) pairs, 54 unreachable;
  115 mutating endpoints, 32 data keys, 29 unsubscribed; 27 renderers, 118 carried
  and undrawn, 18 unreached reads; 4 concepts live, 5 pending
  [NSOT_STAGE7_PLAN.md "7.0 built" table].
- Estimate versus actual: Not recoverable: no estimate for 7.0 is recorded in the
  plan or the commit messages read.
- Acceptance: acceptance 6 (the three cases updating on the host without a reload)
  was NOT passed on its first run, 2026-09-27. The Remote card updated but could
  not be attributed (C58); the drift case could not test the mechanism; the device
  list after Verify was not measured [NSOT_STAGE7_PLAN.md "7.0 built"]. Not
  recoverable: any later passing run of acceptance 6; none is recorded in the plan
  or register.

**6. Where it left the product.**
Every later Stage 7 step had four shrinking allowlists to be measured against, and
the one mechanism for "the screen is now wrong" worked only for changes a response
announces.

### 7.1 — An operation, whole, from the interface

*Backfilled 2026-09-29.*

**1. What it was.**
7.1 began as "the preview-then-confirm component, retrofitted to deploy, restore,
onboarding, bulk intent and NetBox import/remove" [NSOT_STAGE7_PLAN.md §8, row
7.1]. It was reshaped mid-stage, when the operator stopped the first real restore
run (C70) because it needed a browser console, a fleet-wide Save All, the network
tab and an SSH session. The goal became: every operation that changes a device or
the record has one preview, one confirm, one result and one record, and none of
it requires a console [NSOT_STAGE7_PLAN.md "7.1 reshaped", "7.1 acceptance"].

**2. How it was implemented.**
- **The preview half.** `modules/preview_confirm.py` builds six parts (what, what
  will NOT happen, program, operands, gates, confirm), refusing a silent part
  (`PreviewIncomplete`); per-screen adapters (`deploy_preview()`,
  `restore_preview()`, `onboard_preview`, `netbox_import_preview`,
  `netbox_removal_preview`). One renderer, `static/js/nmas_preview_confirm.js`.
  Gates have five states; `at_apply` and `not_reached` are never drawn as pass
  [NSOT_STAGE7_PLAN.md "7.1, deploy retrofitted", "7.1 acceptance"].
- Because the server now builds what the screen draws, the payload check reads
  the adapter's source too, and gained anchors `preview`, `lines`,
  `from_this_edit` [NSOT_STAGE7_PLAN.md "7.1, deploy retrofitted"].
- **The receipt** (C60's first half, `modules/nsot/receipts.py`): one masked row
  per device per batch, written by deploy and restore after the golden commit,
  with the program's hash against the confirmed one, the checks that ran, and
  `follow_up: not_run` stated [git 639e192; OPEN_FINDINGS.md C60].
- **The result half.** `operation_result()` builds what happened from the receipt
  rows the apply just wrote, so the screen and the record are one computation.
  The level (colour) is computed on the server. `GET /deploy/receipts` and the
  Device page's Changes tab read it back [git a97de2d; NSOT_STAGE7_PLAN.md
  "Steps 2 and 3 BUILT"].
- **Capture as an operation** (C82, C89): preview reads each device now and shows
  its diff against the golden and its departure from committed intent; apply
  re-reads, refuses a moved hash, commits as the verified person
  (`Source: capture`). Save All became its fleet form; `/golden_configs/save_all`
  was removed. `save_golden()` writes a computed `Intent-Match:` trailer and takes
  a baseline only with coverage AND every capture matching
  [git 7910e09, e263ff6].
- **Scoped restore** (C80): the Device page's "Restore from…" and a Baselines
  re-apply whose device scope starts empty [git a5c1663].
- **Onboarding and NetBox** retrofits: Create drawn as "Partly done" and pending
  (C86); Remove drawn from a recorded row, `data/netbox_removals.jsonl` (C121);
  then both previews moved onto the component (C122) [git 48ff343, cd16440,
  7a3a66e, 9e1cba2]; Verify and Abandon drawn from an onboarding run record
  [git 763649e].
- **Constraints over lists**: `test_results_are_drawn.py` takes its population
  from the gate table; `GREEN_TOASTS` declares every green toast, found by parsing
  each `showToast(` call [NSOT_STAGE7_PLAN.md "7.1 reshaped", "onboarding and
  NetBox Remove retrofitted"].

**3. Issues encountered.**
Attribution: the plan counts every register row added across 7.1's commit span,
"69 C-rows (C60 to C128) and 2 E-rows", and names six as side work (C119, C120,
C123, C124, C125, C126) [NSOT_STAGE7_PLAN.md "The forecast, corrected"]. Each ID was
checked with `git log -S "| Cnn |"`: every row C60 to C128 first appears in a
commit between `ff6fc24` and `763649e`, and E6 and E7 in `d11955d` and `c776d5c`.
Many came from threads running beside 7.1's screens (the verify sweep, Stage 8
design, concurrency); they are grouped by theme here, with no claim that all came from 7.1's
own screens.

*The component, the result and the record*
- C60: deploy receipt built; follow-up window not.
- C72: fourteen empty record collections in the payload fixtures.
- C73: residue drawn with no section.
- C84: a restore's result was a toast.
- C85: NetBox import outcome persisted, drawn nowhere, sync card green when partial.
- C86: Create said "Device onboarded." after phase 1.
- C87: reachability counted intent revert reached.
- C88: device text interpolated into HTML unescaped.
- C90: a duplicate dict key hid a `RENDERS` entry.
- C96: drift panel drew none of its last run.
- C109: an unselectable target greyed with no reason.
- C121: NetBox Remove drew a partial removal green.
- C122: "retrofitted" meant results, not previews.
- C125: "25 pending" was the ceiling; the count was 23.
- C127: capture preview said lines "will be sent".
- C128: NetBox previews sent the whole dry run to the browser.

*Restore and its gates (found building the gates part, or running C70)*
- C70: the baseline re-apply path had never carried a real restore.
- C75: a restore could change a held credential (it was live).
- C76: the merge program compared lines as text.
- C77: both previews returned stored config verbatim.
- C78: "re-read at apply" re-read the stored capture, not the device.
- C79: a restore could add back a rotated-away secret.
- C80: a baseline could be re-applied only to the whole fleet.
- C81: approving a drift item committed as `ai-agent`.
- C82: no per-device golden capture existed.
- C83: every golden commit subject said "baseline".
- C107: `Intent-Match` compared the raw capture.
- C108: verify took its protocol list from the before-state.
- C110: a restore was recorded `Source: pipeline`.
- C111: two paths wrote identical rotation records.

*Capture and the record*
- C89: capture promoted any device state to golden, baseline and remote.
- C91: a committing Save All took a baseline with a device skipped.
- C104: the manual commit, and readers taking uncommitted files.
- E7: a baseline recorded configuration, not a working network.

*Around the operation (C70's run and after)*
- C92: the online dot was one probe, and one miss drew "offline".
- C93: s3 misses probes while forwarding for the fleet.
- C94: the lab host is unmonitored.
- C97: NMAS leaked SSH sessions and locked itself out of r2.
- C98: a restore and a deploy ran on r2 at once.
- C99: a fifty-second restore showed nothing while it ran.
- C101: paths wrote to a device without holding it.
- C102: pre-model GUI controls reach undescribable states.
- C103: the template preview reads a second capture store.
- C105: three actions implemented twice.

*Verify and device-text readers*
- C61: the read-only allowlist checked the first word only.
- C62: verify read one protocol per device.
- C63: the dangerous-line check is a list of forms.
- C64: the BGP check expected eight fields; IOS prints ten.
- C65: the RIP check read the "application" table.
- C66: the route check read the Networks column.
- C67: the canary accepted Loopback0.
- C68: any count above zero was "progress".
- C69: two BGP summary readers, one wrong.
- C71: fleet fixtures predate P.1.
- C74: BGP judged on IPv4 only.
- C112: a failed rollback drawn as "rolled back".
- C113: "verify never failed" meant it was blind.
- C114: verify passed a device losing its only neighbour.
- C115: the route check was skipped and drawn as compared.
- C116: verify checks only loss.
- C117: the rollback path had never run.
- C118: s4 carried a rollback block for four days.

*Secrets, NetBox, tooling*
- C95: NetBox held every device's credentials in `local_context_data`.
- C100: NMAS's NetBox token is the operator's own account.
- C106: CLIs that stop half-way.
- C119: CI failure unreadable from here.
- C120: stale bytecode ran a mutated control.
- C123: four CDN libraries (a duplicate of D8).
- C124: `nmas-deploy` read a cancelled run as the verdict.
- C126: an unconfigured topology service drawn red.
- E6: no device logs its own config changes.

**4. How they were resolved.**
From each row's status column [OPEN_FINDINGS.md, by ID], with the fixing commit
where the subject names it [git log].
- **Fixed inside 7.1's window:** C61 [eecc900]; C62, C64-C68 [a8019b4]; C69
  [b2924e3]; C73 for deploy [94c9cf1], restore half [f22f8a3]; C74 [dc14f3b];
  C75, C76, C77 [f22f8a3; C77's sweep 6f6b917]; C78's false sentences only; C81
  [8533cb4]; C80 [a5c1663]; C82, C89 [7910e09, e263ff6]; C83 [5cce8f6]; C84
  [a97de2d, closed by C70's re-run]; C85 [d987c02]; C86 [48ff343]; C87 [c59eefd];
  C90 as a scan rule [d987c02]; C91 [7910e09]; C97 [3df10e3]; C98 [11ac30c]; C99
  [76d0f7a]; C101 [c865b4b]; C104 [4370619, 912e3f1, 6b79ab6]; C107 [d17d650];
  C108-C110 [9b39b3a]; C111 [1f6fee9]; C112 [d214f24]; C114, C115, C120 [224bb8f];
  C119 cause found [71401fe]; C121 [cd16440]; C122, C127, C128 [7a3a66e, 9e1cba2];
  C124 [4f92b96]; C123 closed by vendoring [bdea261]; C125 [1bf9a11]; E7 [9f49a33].
  C70 passed on its browser re-run at `d17d650`.
- **Fixed after 7.1 met:** C79, with C140's reason mechanism [e669cbd]; C95
  closed on measurement, 2026-09-28 [f441983]; C96 in 7.2.
- **Decided or closed by decision (the operator):** C88, (a) retire screen by
  screen plus (c) a CSP, built [0f3c61e]; C116 registered and left; C118 renamed
  "blocked change"; C126, Topology tab absorbed into 7.3, removed in 7.8.
- **Moved to a stage:** C58 and C92's reader to 7.2 (built); C92's drawing, C102,
  C103, C105, C106 (3) and C117 to 7.3 (C117 as seed intent's acceptance run);
  C63 to Stage 8.8.
- **Deferred, open:** C60's follow-up window (blocks Stage 8); E6 (blocks 8.7);
  C100 (blocks A3, with 6.2); C78's comparison (UNKNOWN until E6); C93 (UNKNOWN,
  needs C94's metrics); C71, C72, C94, C113, rest of C106 (minor).
- **Deferred by decision, not a finding:** bulk intent's retrofit, to 7.4, by the
  operator: it is fleet-shaped and its CLI works [NSOT_STAGE7_PLAN.md "7.1, deploy
  retrofitted"].

**5. Numbers.**
- Commits: **69**, `ff6fc24` (2026-09-27 00:38:22 -0600) to `763649e`
  (2026-09-27 21:19:05 -0600) [NSOT_STAGE7_PLAN.md "The forecast, corrected";
  confirmed by `git rev-list --count ff6fc24^..763649e`]. Rule: every commit in
  that span, which is the plan's rule; only 18 carry "7.1" in the subject
  [git log]. `df17b55` repeats `ff6fc24`'s subject over four design documents
  (CLAUDE.md conventions).
- Elapsed: **20 h 41 min** of wall time [NSOT_STAGE7_PLAN.md "The forecast,
  corrected"], including a 6 h 26 min gap between the first two commits [git
  ff6fc24, df17b55].
- Findings: register **97 rows to 168**, 69 C-rows and 2 E-rows; about one per
  commit; at `763649e` about 47 closed, 8 decided, about 14 open (a text
  classification) [NSOT_STAGE7_PLAN.md "The forecast, corrected"; row counts
  confirmed at git ff6fc24^ and 763649e].
- Estimate versus actual: measured partway, "13 hours and 32 commits". Actual was
  2.2x the commits and 1.6x the hours. The plan's lesson: an estimate from an
  unfinished stage is made from the part that went to plan [NSOT_STAGE7_PLAN.md
  "7.1 reshaped", "The forecast, corrected"]. The plan also says 7.1 "tripled"
  [NSOT_STAGE7_PLAN.md "7.1 reshaped"]; Not recoverable: the original pre-7.1
  estimate that "tripled" refers to.
- Acceptance: MET 2026-09-28 on the laptop suite, 5025 passed, 0 errors. Results:
  9 of 38 gated actions drawn by the result component, 21 pending (each homed in a
  later stage), 8 with no GUI; previews: five screens on the component, only bulk
  intent pending. The result survey began at 33 of 41 not drawn
  [NSOT_STAGE7_PLAN.md "7.1 acceptance"].
- Stated limit: only restore had run on the host. R1 (onboarding) and R2a/R2b
  (NetBox) closed it on 2026-09-28; R2b deleted exactly the 8 predicted objects and
  the census compare passed at 235 objects [NSOT_STAGE7_PLAN.md "7.1's stated
  limit"].

**6. Where it left the product.**
Deploy, restore, capture, onboarding and NetBox import and remove each had one
preview, a hash-bound confirm, a server-levelled result built from the record the
apply wrote, and a place to read that record again, with no console needed.

#### Sources read (7.0, 7.1)
- docs/NSOT_STAGE7_PLAN.md: §4, §5, §8 table, "7.0 built", "7.1, deploy
  retrofitted", "7.1, restore retrofitted", "7.1 reshaped", "7.1, onboarding and
  NetBox Remove retrofitted", "7.1 acceptance", "7.1's stated limit", "The forecast,
  corrected", §10.
- docs/OPEN_FINDINGS.md: rows B1, C51-C128, E6, E7 (titles and status columns;
  full text for C55-C58, C70, C75, C77, C79, C84, C122, C125).
- docs/NSOT_WRITEUP_NOTES.md: section headings; no 7.0 or 7.1 section found.
- CLAUDE.md: module map and test table entries for the named modules and tests.
- git: `git log --format='%h %ad %s' --date=iso` around 2026-09-26 to 28;
  `git show --stat` for 379b4d8, a8dce41, 9264d97, dca1071, 91c81fd, 76f7ffa;
  `git log -S` per register ID; `git rev-list --count`; register row counts at
  9df50ed^, 91c81fd, 76f7ffa, ff6fc24^, 763649e.

#### Could not recover (7.0, 7.1)
- Any estimate for 7.0.
- A passing host run of 7.0's acceptance 6; the plan records only the first,
  failing run.
- The original 7.1 estimate behind "7.1 tripled"; only the partway "13 hours and
  32 commits" is recorded.
- Which of the 71 rows in 7.1's span came from 7.1's own screens versus side
  threads, beyond the six the plan names; the theme grouping above is this writeup's.
- Fixing commits for rows whose status names no commit and whose fix no commit
  subject names (for example C112's exact commit is inferred from its subject).

### 7.2 — Needs attention, the reader job, and the live-data contract

*Backfilled 2026-09-29.*

**1. What it was**

7.2 built the landing view that answers "what needs attention", plus a status bar on every page [NSOT_STAGE7_PLAN.md table row 7.2]. Needs attention had to draw every source in the plan's section 1a: job health, drift with coverage, freshness, firing Grafana alerts, the approvals queue, pending onboardings, rollback blocks, a failed deploy, and an unearned baseline. It also leaves an empty slot for Stage 8 triage [NSOT_STAGE7_PLAN.md §1a]. The page could do no per-device work to render (§0a). A source that could not be read had to be a row, never an absence. The stage also carried C92: replace the one-probe "online" dot with a reader that counts consecutive misses [NSOT_STAGE7_PLAN.md table row 7.2; OPEN_FINDINGS C92].

**2. How it was implemented**

*The row and the source contract (step 1).* `modules/attention.py` has one constructor, `row()`. It refuses a row with no what, cause or action. Each row carries what, devices, since, cause, operands, one action, a level the server decides, and an empty `triage` slot [NSOT_STAGE7_PLAN.md 7.2 step 1]. `source_result()` records when a source was read, how long the read took and what it looked at. An unreadable source, or an adapter that raises, becomes a row [git 71ed99e]. Step 2 added `value_at`: a stored source is dated by its value (for example, the drift run), not by the read [NSOT_STAGE7_PLAN.md 7.2 step 2]. Step 3 added the attach rule: a queued drift approval folds into its device's drift row, so one event is one row [NSOT_STAGE7_PLAN.md 7.2 step 3].

*The sources on stored data.* Five sources read stored data:
- drift: the last stored run, never a re-check (step 2);
- approvals: through a new `read_pending()` that writes nothing, and pending onboardings (step 3);
- rollback blocks: through the one classifier the listing already used (step 4);
- deploys and restores: each device's latest receipt, judged by the result screen's own `result_level` (step 5);
- repeated authorisations: the same line authorised three or more times on one device (step 7).

For the baseline source, the operator chose to make the decision durable first. `save_golden()` now writes `Baseline: earned` or `Baseline: denied: <reasons>` into the commit it judged, and the source reads the newest decision [NSOT_STAGE7_PLAN.md 7.2 steps 5–6]. Step 8 moved each job-health row family's remedy out of the detail text and into the row's `action` field [NSOT_STAGE7_PLAN.md 7.2 step 8].

*The reader job (step 9).* `modules/reader_job.py` is one background read of an outside service. It stores its value dated by the value; a failed read keeps the last good one; an exactly-full page is refused as partial; its liveness is a job-health row; it announces its data keys when it finishes; and registration refuses a reader that does not declare its endpoints, its interval's measurement, or its keys [git f310e42]. The rules are written in the module's docstring. There were ten at first; two more followed: "a check stays live; only a report is cached" and "a reader's promise is about how fast NMAS notices, not how fast the source notices the world" [git 20483d6]. Step 19 extended rule 9: a reader that announces only on change must also send a keepalive, and registration refuses one without it [git 33a8041].

*The readers.* Built in 7.2:
- **Job health** (step 11), every 300 s. The operator measured the landing view on the host: job health took 9,797 ms, 99.4% of the page [NSOT_STAGE7_PLAN.md 7.2 step 11]. Its stored rows exclude the `reader:*` rows, so a stopped reader cannot freeze a cache that says it is fine [git a9377dc].
- **Grafana alerts** (step 14), every 60 s, from three named endpoints. It tells condition, no data and error apart, groups incidents on the onset (start minus window, within 360 s), and flags an evaluator that answers but has stopped [NSOT_STAGE7_PLAN.md 7.2 step 14].
- **Freshness** (step 15), every 300 s. Before this, the index page ran one Oxidized fetch per device on every load. The sanitiser's gate stays a live read on purpose [NSOT_STAGE7_PLAN.md 7.2 step 15].
- **Integration health** (step 16), every 60 s. Its probes run in parallel. It feeds both the status bar and Needs attention [NSOT_STAGE7_PLAN.md 7.2 step 16].
- **CI verdict** (step 17). It loads `scripts/nmas-deploy` and calls that script's own `ci_verdict()`. `GET /health/version` composes the answer and computes none of it [NSOT_STAGE7_PLAN.md 7.2 step 17].
- **Reachability** (step 19, C92), every 5 s, every list: per device the last result, which probe answered, the miss count against `miss_threshold()` (3), and since when. It owns the `device_status_cache` every consumer already read; `ping_worker` is gone [NSOT_STAGE7_PLAN.md 7.2 step 19].

A seventh reader, baseline usability, came after 7.2 was declared built and reused the same pattern [git 9c1037d].

*The live-data contract (steps 10 and 13).* `invalidation.announce()` sends a background job's data keys over Socket.IO. The client is loaded once, in `base.html`. The server sends a heartbeat every 30 s. A page that misses 2.5 beats marks every subscribed panel as not updating, on the panel's own data. Every value carries `value_at` and `stale_after_seconds`, judged on a local 15 s tick that makes no request. A reconnect re-fetches every subscribed panel once. There is no data polling, except Needs attention's 60 s poll, which stays until every sender announces [NSOT_STAGE7_PLAN.md 7.2 steps 10, 13].

*Presentation.* With no rows, the page is one line that still makes the positive claim (step 12). The operator then set Stage 7's rule: the screen answers the question the person came with, the evidence one level down; it was applied to four panels [git ca899db]. The status bar's three items are integration health, the version with its CI verdict, and who you are, read live from `/identity/status` [NSOT_STAGE7_PLAN.md 7.2 steps 16–18].

**3. Issues encountered**

*How findings were attributed.* A row counts if it was first written inside the 7.2 commit selection (C164–C174, by `git log -S` on OPEN_FINDINGS.md), or if a 7.2 step closed or advanced it. Findings with no ID are listed separately.

New register rows during 7.2:
- C164 — nine of ten job-health row families had no action a person could take from the interface.
- C165 — Grafana's rules view and its Alertmanager seemed to disagree on what was firing.
- C166 — two Grafana rules had been in no-data for days, and nothing surfaced it.
- C167 — `prometheus_url` appeared empty while Grafana queried Prometheus.
- C168 — the hand-built Grafana rules had never been verified. The SNMP scrape targets are also a hand-kept list.
- C169 — the ZTP responder sent a refusal before recording it (found by the commit gate; side finding).
- C170 — `nmas-deploy` refused a docs-only commit with a message describing a search it never made (side finding).
- C171 — the NSoT git probe described one global repository, and five of its settings are read by nothing (found from the status bar).
- C172 — an unreadable `remote.json` reads as no remote (found building C171's probe).
- C173 — lists separate devices, but settings are global. Latent defects include the status bar and the Grafana source (P.8 scoping, the operator's).
- C174 — NetBox tenants against regions (a deferral recorded out of P.8).

Existing rows 7.2 closed or advanced: C96, C151, C140 (1), C58, C92, C159, C163, C144. C38 was assigned to 7.2 and not built.

Findings with no register ID [git bodies]:
- The payload check sampled each list through its first item only, so nine `EMPTY_IN_FIXTURE` declarations were false [git 694d303].
- An unearned baseline's reason had no durable record [NSOT_STAGE7_PLAN.md 7.2 step 5].
- C58's premise was false: the index page held no Socket.IO connection [git f310e42].
- The reader rows' `since` was an ISO string where every other row used epoch seconds, so the first failing reader would have crashed the source. The subscription scan also never read `static/js/nmas_*.js` [git a9377dc].
- The commit gate read the previous run's result file, so e986e66 was committed on "5330 passed" when its suite never ran [git 6fc7b59].
- A plan note quoted C17 as open, taken from CLAUDE.md's restatement a day after the register had closed it [git dd87620].

*Gate runs before 7.2.* R1 (onboarding a throwaway) and R2a/R2b (the NetBox window) are recorded as closing **7.1's** stated limit. They were scheduled before 7.2 and listed as 7.2 gates [NSOT_STAGE7_PLAN.md "7.1's stated limit"; NSOT_PLAN.md dependency notes]. They are not part of 7.2's close, so their findings are not counted here: C130, C131, C133–C135 (R2a); C146–C154 and the C57 closure (R1, R2b). The other gates, C17, E4 and C54, closed or were fixed before step 1 [git 711dc74, 185a4d3].

**4. How they were resolved**

- **C96** — fixed in step 2. The drift panel draws what a run found. The payload fixture now reaches a real drift run [OPEN_FINDINGS C96].
- **C151** — closed in step 8. The heartbeat check's row carries "regenerate the rules" as its action [OPEN_FINDINGS C151].
- **C164** — 7.2's half fixed in step 8 (every row family's remedy is its action). The other half, persist as a Device action, was decided by the operator for 7.3 [OPEN_FINDINGS C164].
- **C140 (1)** — built in step 7. Part (2), one home for authorising, waits for the restore preview's re-planning [OPEN_FINDINGS C140].
- **C58** — mechanism built in steps 10 and 13. The remaining senders (post-commit push, drift run, NetBox refresh, another browser) stay open. Needs attention keeps its 60 s poll until they announce [OPEN_FINDINGS C58; NSOT_STAGE7_PLAN.md "What does not exist yet"].
- **C92** — split by decision. The reader was built in step 19. Drawing the claim and its age on the dot is 7.3's [OPEN_FINDINGS C92].
- **C165** — closed as a defect in the measurement. Both instances were `DatasourceNoData`. The design consequence (three kinds of instance, and a reader names its endpoint) went into the Grafana reader [OPEN_FINDINGS C165].
- **C166** — closed on measurement. The syslog rule was miscoded. The operator applied the attribution fix, and it was read back through the ruler [OPEN_FINDINGS C166].
- **C167** — closed on measurement. `prometheus_url` was set and answered. The class of the finding is the status bar's [OPEN_FINDINGS C167].
- **C168** — surveyed on the host, then scheduled into P.7 by decision: rules generated and tested [OPEN_FINDINGS C168].
- **C169** — fixed the same turn: record, then send [OPEN_FINDINGS C169].
- **C170** — fixed. Each ancestor is asked about by SHA, with a bound of 10 [OPEN_FINDINGS C170].
- **C171** — probe half fixed. Retiring the dead fields is scheduled into 7.7 [OPEN_FINDINGS C171].
- **C172** — deferred, sorted C/M [OPEN_FINDINGS C172].
- **C173** — decided by the operator as P.8, placed after 7.2 and before P.7 and 7.3 [OPEN_FINDINGS C173].
- **C174** — deferred by the operator to Stage 9, with both sides of the argument recorded [OPEN_FINDINGS C174].
- **C159** — extended: the approval queue saves on every read. Needs attention reads through `read_pending()` instead. The row stays deferred to Stage 9 [OPEN_FINDINGS C159].
- **C163** — a second unexplained error was added. Targeted runs are now saved whole [git a9377dc].
- **C144** — re-sorted to Stage 9, because "placed in 7.2" named a stage it was not in [git dd87620].
- **C38** — not built. The register still schedules an adjacency row into 7.2, and no adjacency source exists in `attention.py`.
- **Unnumbered findings:** all fixed in the commit that found them [git 694d303, 2a51799, a9377dc, 6fc7b59, dd87620].

**5. Numbers**

- **Commits: 37** [git 71ed99e^..33a8041]. The selection rule is every commit from the first "7.2 step" commit to the one declaring "7.2 is built". Of those, 19 carry "7.2 step N". The other 18 are register, P.7 and P.8 decisions, and C166–C171 measurements interleaved in the same window. The selection is ambiguous, because the interleaved commits are not all 7.2 work.
  - First: 71ed99e, 2026-09-28 12:31:21 −0600 [git 71ed99e].
  - Last: 33a8041, 2026-09-28 16:34:04 −0600 [git 33a8041].
- **Elapsed: about 4 h 03 min** between those two commits [git].
- **Findings: 11 new register rows** (C164–C174) [OPEN_FINDINGS; git -S]. Eight existing rows were closed or advanced. Six findings have no ID.
- **Estimate against actual:** the plan predicted 40 to 70 commits over about a day, with 30 to 50 findings, "to be checked when it closes" [NSOT_STAGE7_PLAN.md "The forecast, corrected"]. No check is recorded. Measured here: 37 commits in about 4 hours, and 11 new rows plus six without an ID.
- **Suite:** 5239 passed at step 1 and 5450 passed at step 19 (laptop, parallel) [git 71ed99e, 33a8041].
- **Host measurements taken during the stage:**
  - job health 9,797 ms per page load before it became a reader [NSOT_STAGE7_PLAN.md 7.2 step 11];
  - ten integrations answered in 266 ms [step 16];
  - Grafana's endpoints answered in 35–150 ms [git f310e42];
  - C92's threshold came from 2,946 offline runs, 93% of which ended at the next probe [OPEN_FINDINGS C92].
- **Acceptance:** Not recoverable. The plan records "7.2 is built" (step 19), and no whole-stage host acceptance of Stage 7 acceptance item 7 is recorded in the plan or in later commits.

**6. Where it left the product**

The landing page drew every section 1a source from stored or cached values, each dated and judged against its own promise, and the status bar read from the same readers. The reachability reader's claim and the adjacency rows (C38) were left undrawn.

**Reopened 2026-09-29: 7.2 was declared built without one of its scheduled sources.** C38 (nothing alerts on a protocol adjacency) was decided on 2026-09-27 as a Needs attention row and scheduled into 7.2, and `33a8041` declared 7.2 built with no adjacency source in `modules/attention.py`. Nothing recorded the omission; the backfill found it by reading the scheduled rows against the code. It is the same shape as C122 ("retrofitted" meaning half of each retrofit) and D6 (a row left in Scheduled three days after its work was done): a status claim ahead of the thing it describes. **The source moved to 7.3** (the operator, 2026-09-29), to be built with the Device page's Neighbours section: both need the expected adjacency set derived from committed intent, compared against what the device reports, so it is built once with two consumers (the per-device view and a Needs attention row), the reader pattern again. Built for the row alone in 7.2, the expected-set logic would have been built a second time for the page. It sits beside C178, since both ask how many neighbours a device should have against how many it has.

#### Sources read (7.2)
- docs/NSOT_STAGE7_PLAN.md (row 7.2, §1a, 7.1's limit, the forecast, steps 1–19, the presentation rule, §10); docs/NSOT_PLAN.md (gate notes, Stage 9); docs/OPEN_FINDINGS.md (the rows cited, Count); docs/NSOT_WRITEUP_NOTES.md; CLAUDE.md
- git: `log --grep='7.2'`, `log 71ed99e^..33a8041`, commit bodies, `log -S` per row, files added under `modules/readers/`

#### Could not recover (7.2)
- A whole-stage host acceptance of 7.2. None is recorded.
- A check of the 7.2 forecast against actuals. The plan says it would be checked at close, and none is written.
- Which interleaved commits the operator counts as 7.2 work. The subject lines do not settle it.
- Whether C189 (the WebSocket ERROR "that began today") was caused by 7.2 step 10's Socket.IO client. The register does not name the cause, so it is not attributed here.

### 7.3 — The Device page (open)

7.3 is open. The entries below are its sub-tasks that have closed, each written when it closed, or backfilled in the same session and marked as such. Commit times are the committer's local time (UTC-6). Host times are UTC.

#### 7.3 step 1 — Seed intent (C148)

*Backfilled 2026-09-29.*

1. **What it was.** Onboarding left a device with only a bootstrap intent. A device with no full committed intent is `bootstrap`, and it cannot be deployed. So nothing onboarded could ever be deployed to. Seeding closes that path: a device's first full intent is parsed from its committed golden, once.
2. **How it was implemented.** `modules/nsot/seed.py` parses the committed golden (`HEAD`, never the working file) into host_vars. It previews the document against the intent committed now and binds the confirm to a hash of the document and the golden. At apply it parses again and makes one commit of exactly the seeded files (`Source: seed`, a `Seeded-From:` trailer naming the golden). Only absent or bootstrap-only intent is seeded. What the template does not model is named in the preview and never blocks here. It is the Device page's "Seed intent" (`static/js/nmas_seed.js`), and it replaced four extraction routes, which now answer 404 [CLAUDE.md module map; `tests/test_seed_intent.py` row].
3. **Issues encountered.** C148 was the finding it fixed: it blocked the central loop, and the first triage had filed it as 7.3 work [docs/NSOT_PLAN.md "Open findings register"]. Not recoverable in this entry: whether building it surfaced other findings. This entry was backfilled from the commit and the docs, not written at close.
4. **How they were resolved.** C148 fixed by `195fdbe`.
5. **Numbers.** One commit, `195fdbe`, 2026-09-28 16:53: 27 files, +1,155 −196, and a 374-line test file [git 195fdbe]. Not recoverable: an estimate.
6. **Where it left the product.** An onboarded device can reach deployable intent from the interface.

#### 7.3 — Retire from the Device page

*Built 2026-09-28 and 2026-09-29. Its real retirement came on 2026-10-04 (r5), through the v2 device page that replaced this screen; the run is recorded in that entry ("Restore, revert and retry, seed and retire on the v2 device page"). Its numbers stay partial.*

1. **What it was.** Retiring a device (C11) existed only as `nmas-retire` on the host. The Device page needed the same operation, previewed and confirmed, with one implementation behind both entry points.
2. **How it was implemented.** `modules/nsot/retire.py` holds the whole exit. `routes/retire.py` serves `/retire/preview` (gated `not_device`) and `/retire/apply` (gated `approve`), and `static/js/nmas_retire.js` is the client. The browser cannot reach the break-glass record, which lives on a laptop. So the screen trusts the EXPORT LOG (`breakglass_logged`) and states that basis and its limit. The log records what was written and cannot show the file still exists, and the CLI's stronger check is to OPEN the record. Each refusal is keyed (`refused_by`), and every key the plan can produce is a gate by name. The apply refuses a rotation made after the preview, and a reason changed after it [`tests/test_retire_screen.py` row; the operator's decision, 2026-09-28].
3. **Issues encountered.**
   - C185: no page reaches a retired device's record once the modal closes.
   - C186: retire's failure paths carry two older shapes (whole-tree `checkout`/`reset`, C175's shape on the failure path).
   - C187: the plan told the operator to re-approve every bound template, an approval scheme 3 no longer withdraws.
4. **How they were resolved.**
   - C187 fixed in the same work: the step was replaced by a Not-Done line.
   - C185 scheduled into 7.3.
   - C186 registered, not fixed, under the sweep's stopping rule.
   - Writes off with a credential held: decided by the operator 2026-09-29 as a refusal, and built.
5. **Numbers.** So far: the screen in one commit, `47f8ecf`, 2026-09-28 18:30; r5's gaps in `6ff6fd0`, 2026-09-29 01:19; the writes-off decision built the next morning [git]. Not recoverable: an estimate (none was written). Not yet run on the host.
   - **r5's gaps (overnight 2026-09-29)**, modelled on r5's retire commit (`3592113`). NetBox's stored credentials (C139) are masked FIRST, with the same implementation as `nmas-netbox-mask-context` (moved to `modules/netbox_context_mask.py`), and read back. The legacy file (C176) is deleted only when its content survives in the repository. The heartbeat rule and the scrape targets, which NMAS does not own, are read and named.
   - **The writes-off decision (the operator, 2026-09-29 morning): neither option as written.** Reads work with writes off, so the preview checks the device's NetBox context; a credential held there REFUSES the retirement, naming it (C139 recurring), and a context with nothing to mask proceeds and says so.
   - **A record of a wrong summary**: the morning's summary told the operator to do four r5 leftovers, and three were already done (the legacy file deleted two days earlier, NetBox masked when C95 closed, no r5 in the heartbeat rules). The retire flow READS each of those before naming it; the summary did not. Only the Prometheus scrape target remained.
6. **Where it left the product.** A device can leave management from the interface, and the screen says what its break-glass check did and did not establish.

#### 7.3 — Persist from the Device page (C164)

*Written at close, 2026-09-29: accepted on the host the same day.*

1. **What it was.** The remedy the worst Needs attention rows name (`not_safe_to_reboot`: the running config holds the only working credential) existed only as `nmas-persist-native` on the host. The operator put PERSIST in 7.3's Device actions (2026-09-28), the first action added because a row asked for it [NSOT_STAGE7_PLAN.md "7.3 gains PERSIST"; OPEN_FINDINGS C164].
2. **How it was implemented.** `modules/nsot/persist_op.py` plans (reading only the registry, the inventory and the hourly startup check's record) and applies: it recomputes the plan against the confirmed hash, holds the device (C98, C101), saves and reads back through `onboard.persist_on_device` (the one save implementation, so no new one), and records as the verified person where job health's rotation row reads it. `routes/persist.py` and `static/js/nmas_persist.js` give it the preview-confirm-result treatment retire has; the rotation and startup rows' actions now name Persist… beside the host command [git: this commit].
3. **Issues encountered.**
   - The Device page offered the save three ways: Save Device Config and Save to Startup, neither verified nor recorded, and Persist (C103).
   - C209 (from the acceptance screens): the preview counted two reads as lines, "(3 line(s))" over one line sent, while the result said "Sent to the device: write memory". C127's wording defect back in a new preview.
   - C208 (the operator's question): the preview's `driver: cisco_ios` for r2, an IOS-XE router. The inventory records r1 to r4 as `cisco_ios` and r6 as `cisco_xe`.
4. **How they were resolved.**
   - C103's save half closed by the operator's decision: Persist is the one save, and the other two buttons and routes are removed.
   - C209 fixed structurally: a captioned program must say what its count counts, and persist's program is exactly what is sent, one producer for preview and result.
   - C208 registered: measured to change no behaviour (one Netmiko class for both names on 4.3.0 and 4.6.0, and nothing branches on the driver); the preview now draws the driver and the dialect apart.
5. **Numbers.** Two commits, `90b5a25` and the afternoon's [git]. 16 tests; four controls fired (the hold, the hash check, the unit refusal, the unit drawn) [tests/test_persist_screen.py]. Not recoverable: an estimate (none was written). **Acceptance on the host, r2** (the operator): sent `write memory`; read back "the startup config carries username admin privilege 15 secret <redacted> <value>"; the result "r2 is persisted …"; the record written as the operator, via the Device page.
6. **Where it left the product.** A device whose boot copy lags its running credential can be persisted from its own page, with what was read back said.

#### 7.3 — Rotate from the Device page

*Closed 2026-09-29: ACCEPTED on the host, on r2, by the operator.*

1. **What it was.** Rotation, the riskiest operation in the tool, existed only as `nmas-rotate-credential` on the host. The operator asked for it on the Device page, "built assuming a fourth failure mode exists": three ways in three days for a rotation to leave a device unmanageable (B15, C53, C106) [NSOT_STAGE7_PLAN.md "7.3 gains rotate"].
2. **How it was implemented.** Step 1 first: the recovery path (C210, below). Step 2: `rotate_op` runs `credential_rotation`'s plan, rotate and persist as one operation, holding the device across both; the apply is a job (rotate plus persist can pass the 100 s edge limit), announced when it finishes; the job carries the person's verified identity into its thread; the result is `summarise()`'s danger-first sentence with each of the eight states' one action. Landed after C205 (the connect bound), C203 (persist holding the device) and C50 (an unknown lab refused), each of which it depends on.
3. **Issues encountered.**
   - C210: designing the screen found the fourth failure mode before it happened. The password is staged before the push, so a process that dies between the push and the record (an app restart; a deploy causes one) leaves the device on a password the inventory does not hold, and nothing read the staged file.
   - A commit made on a background thread read `Actor-Verified: none` although the gate had verified the person who confirmed it (found building the job; no row, fixed in the step that needed it).
   - C211: `stage_plaintext()` creates the file then chmods it (ciphertext, minor).
   - From the real run (the operator): C217, the job's own in-flight row stayed at "starting" and called the operation "may be stuck" beside the device's true row ("persisting"), in garbled words; C218, about four minutes in the containerlab boot-file chain drawn only as "persisting"; C219, the result's next step drawn under "What did not happen"; C220, the preview's live line masked twice.
   - Around the run: C221, the break-glass row read "current" for the operator's first export of the day, which was deleted on the host before it reached the laptop (the row tracked that an export was WRITTEN).
4. **How they were resolved.** C210 fixed as step 1 (`nmas-rotation-recover`, a job-health row per staged file nobody holds); the identity carried by `identity.carried()`; C211 registered; C217 to C220 registered, the in-flight pair (C217, C218) to ride with the next change to that component (the operator); C221 fixed the same evening.
5. **Numbers.** Two commits, `fe951e9` (2026-09-29 11:01, step 1) and `9fd5e06` (11:08, step 2), after `2b1ea78` (10:54, C205, which it depends on) [git; the build's working time is not recoverable from commit times]; 12 and 24 tests; six controls fired. Not recoverable: an estimate (none was written). **Acceptance on the host, r2** (the operator, the afternoon of 2026-09-29): "rotated, committed, saved on the device and read back from its own startup config, present in the startup file, that file applies on boot, and nmas-check-startup-applies reads SAFE"; the fresh login verified on the first try; commit `60d233984c2c` carries `Source: rotation`, `Actor: <operator>`, `Intent-Match: yes (1 of 1)` and `Actor-Verified: access`, the carried identity's first real run; every gate passed, the sudo-helper gate included, which was expected to fail. The baseline-decay row fired 21 s after the rotation, naming r2, as designed. The break-glass record was exported again and read `ok 9 of 9 device(s) current`, the laptop's verify showing r2's digest changed (`<redacted-1>` -> `<redacted-2>`) and the other eight identical.
6. **Where it left the product.** A device's credential is rotated from its page, end to end, recorded as the person who confirmed it, persisted and read back; the operation that broke four ways that week completed from the interface on its first real run, and no state it can reach, a process dying mid-way included, goes unnamed.

#### 7.3 — Revert and retry from the Device page

*Open: built 2026-09-29, awaiting a real run (C117's run engineers the rollback they answer).*

1. **What it was.** A rollback restores the device and leaves intent asserting the change that failed, so the next plan is blocked. The two ways out mean opposite things (revert: the change was wrong; retry: it was right and the failure was elsewhere), and both existed as routes with no screen [NSOT_STAGE7_PLAN.md "7.3 gains rotate and retire", which names them as intent operations].
2. **How it was implemented.** `modules/nsot/intent_ops.py`, on seed's model: preview, confirm by hash with the list carried, apply holding the device, the one component's result. Revert splits `hostvars.revert_intent_change()` into `plan_revert()` (computed, nothing written) and the write, so preview and apply are one computation; it commits `Source: revert` with `Reverts:`, and puts the file back on a failed commit (the helper moved to `hostvars.put_back_committed`, which seed uses too). Retry takes a reason in the shape of one (C140's rule) and counts earlier retries. One per-device classifier, `note_applicability()`, extracted from `rolled_back_notes()`. The client, `static/js/nmas_intent_ops.js`, serves both from two Device-page buttons.
3. **Issues encountered.**
   - C213: the retry log, the audit of every decision to re-send a failed change, was read with an unreadable file taken as empty and written back by truncating in place.
   - C214: the old revert route cleared the rollback block after ANY committed revert, so reverting an unrelated change lifted the block on a failed one.
   - C215 (found measuring seed for the operator's question, fixed here by the operator's decision): the deploy plan read the device row from the ACTIVE list and defaulted the platform on a miss; the same shape in the baseline judgement.
   - Paused mid-build by the operator's three questions about seed; `tests/payload_render.shipped()` found files through a hand-kept list that persist and rotate were missing from, resolved by location now.
4. **How they were resolved.** C213 and C214 fixed in the operation's own path; C215 fixed at both sites. Controls: each fix put back from a copy fails exactly its test.
5. **Numbers.** One commit with the rest of the evening's items [git]; 26 tests. Not recoverable: an estimate (none was written).
6. **Where it left the product.** A rollback's two ways out are on the Device page, each previewed, recorded and drawn, and the block lifts only by measurement or by a stated decision, never by a side effect.

#### 7.3 — Adopt: bringing a device the tool did not build into management

*Open: being built, 2026-09-29. Steps 1 (the account) and 2 (the preview and the apply) are built; the screen and the real run remain.*

1. **What it was.** A device the tool did not configure (brownfield) had no way in: onboarding assumes a device booted from the tool's own bootstrap. The operator decided the shape on 2026-09-29: onboarding's phase 2 without phase 1, reaching the device with the credential a person supplies, adding an account for the tool and never rotating the supplied one, no RW-community removal or other change, and a persist that first previews running against startup [NSOT_STAGE7_PLAN.md "ADOPT, for brownfield"].
2. **How it was implemented (so far).** `modules/nsot/adopt.add_tool_account()` reuses rotation's pieces unchanged (staging before the push, the held session, the fresh-login verify, the record) with a different program and a different undo: one setter line for an account the device does not have, and `no username <tool>` read back gone if the verify fails. Rotation's orchestrator was left untouched, because it is built around one existing account (its preflight, recheck and revert all read that account's line).
   Step 2 puts that account step inside a preview and an apply.
   - **`plan()`** reads the device with the supplied credential and sends nothing. It draws each gate by name, persist as running against startup, and NetBox's existing objects plus the import's own dry run over the capture. A dry run may now be handed the text it previews; a real import still reads only what is committed.
   - **`apply()`** holds the device and plans again, refusing a moved fingerprint. It then adds the account, persists with a read-back, mints the identity and commits the first golden (`Source: adopt`). It records what NetBox held BEFORE the import in a third record (`data/netbox_adopted.json`), never the created one, then imports and promotes last.
   - **Resume:** a stopped run resumes on the tool's own record: its account is on the device, its credential is stored for the address, and a fresh login proves it.
   - **Recovery:** the account step's staged password gets a sidecar (address, driver, account). `nmas-adopt-recover` settles it from that sidecar, and job health names that command for an adoption's staged file.
3. **Issues encountered (so far).** `nmas-rotation-recover` cannot settle an adoption's staged password: it works from an inventory row, and a device being adopted has none. The first failed-record message pointed at it; it now says the staged copy is the only one and where it is, and the apply will carry adopt's own recovery. Settling the operator's two points before step 2 found a gap in the new test itself: its scan used `glob("**")`, which skips hidden directories, so a supplied password staged into `.nsot/staging/` was invisible to it. Its own control (staging the supplied password on purpose) passed, which is how it was found; `os.walk` reads every directory, and the control now fails on the seven paths that open a session. The suite's other recursive globs read source directories with no hidden entries, and the one scan of written stores uses `pathlib.rglob`, which includes them.
   Step 2 found:
   - **The supplied credential and the golden.** A golden is the device's config verbatim, so a device that stores the supplied account as `password 0` (vrnetlab's `admin`/`admin`) or `password 7` would put the supplied credential into the repository and its remote. That contradicts the operator's rule that it is never written, and it is a decision the rule did not cover.
   - **C225.** Onboarding's NetBox record calls every device a router, and adopt widens that to any device.
   - **The plan's own wording.** Its remaining list still said "the supplied credential staged".
   - **`listref.resolve()` derives an unknown list**, so adopt refuses with `exists()` first, the write-path rule (C51).
   - **Harness seams.** The suite's shared store carried one test's recorded override into the next, and a second binding of the list-directory helper created a real list directory. Both were fixed in the test.
4. **How they were resolved.** The message corrected in the same step; recovery placed in the apply. Controls: the delete-then-set program, the absence check removed and the undo removed each fail their tests.
   - **Step 2's supplied credential: decided by the operator the same evening, and built.**
     - Every local credential the golden would carry reversibly (`username … password 0|7`, `enable password`) is refused by name; SNMP communities are the accepted exception.
     - The SUPPLIED account alone may be converted, by a named opt-in: it is re-sent as a secret with the same password, using rotation's program on the held session after the tool's own account is proven. A fresh login as the owner follows, and if that fails the original line is put back and proven.
     - "Telling the person to change it by hand" was rejected because it sends them to a console.
     - Building it found one more defect: the delete the conversion needs removes EVERY line of the account, an autocommand included. So an account with more than one line is refused.
     - The no-copy test's scan had read only the data directory, never the list's repository, whose objects are compressed. It now also reads the list's files and the whole history as text, with a control that finds a committed clear golden.
   - **C225:** registered.
   - **The plan's wording:** corrected.
   - **Controls:** the gate removed, adopted objects written as created, resume removed, job health's branch removed, the importer honouring text outside a dry run, and the fingerprint not compared. Each fails exactly its own test.
5. **Numbers.** Estimate at scoping: about 6 to 10 hours and 12 to 20 commits, most of it the real run's findings [NSOT_STAGE7_PLAN.md]. So far four commits (step 1, the settled points, step 2, the reversible-credential decision) and 74 tests in two files.
6. **Where it left the product.** Not yet: the preview and the apply exist and are reachable from no screen. Their routes and client come with the screen, in the redesign.

#### 7.3 — The break-glass export from the browser

*Open: built 2026-09-29, awaiting a real run.*

1. **What it was.** The re-export after r2's rotation took about ten manual steps across two machines, and the first attempt was lost: the laptop half ran on the host and its cleanup deleted the staged file before it was copied, after the export had been logged (C221). The operator asked for a button that does the host side and downloads the file through the browser. The re-export was needed because of C182 (2026-09-28): nothing had compared the record with the credentials in use, so a digest comparison, an export log and a job-health row were built, and that row named r2 as stale after its rotation [OPEN_FINDINGS C182].
2. **How it was implemented.** `modules/breakglass_export.py`, apart from the record format so that module stays independent of the application's stores: the passphrase twice and 12+ characters, refused before anything is built; the plan recomputed and bound to the preview's hash; the record sealed in memory, then OPENED with the passphrase and checked (every device, every credential by digest, the escrowed key, and the key opening what the live key opens); a reveal row, required before anything is sent; the export log with `via: browser` and the sha256. The route returns the sealed bytes beside the masked result; the page decodes them into a download. One client, three entry points (the rotate result's new next-step slot, Needs attention's break-glass row, the Settings page), opened by a data attribute that names the operation, never a function. The CLI now calls the same device and key readers.
3. **Issues encountered.** The first placement put the export code in `modules/breakglass.py`, and its test that the record module never reads the app's stores failed: the property it guards (a record opens during an outage without them) was real, so the export moved to its own module. C219 (the result component had no slot for a next step) was built as part of the entry points.
4. **How they were resolved.** The module split; C219 fixed. Controls: skipping the verify, dropping the passphrase scrub and ignoring the reveal record each fail exactly their tests.
5. **Numbers.** One commit [git]; 17 tests. Not recoverable: an estimate (none was written).
6. **Where it left the product.** The break-glass record is exported from the browser, verified by the server before it is sent, recorded as a reveal, and tracked by job health as "downloaded by X at T" with the instruction to verify the copy kept.

#### 7.3 — C223: every commit publishes, and "not pushed" is measured at the remote

*Closed 2026-09-29: accepted on the host by the operator. Abandon's commit `7a72258` was left unpushed until the deploy, so the fix was seen closing a real gap.*

1. **What it was.** A demo onboard-and-abandon of a throwaway `R10` left the abandon commit on the host while onboarding's commit, one step earlier on the same list and remote, was on GitHub. The GUI reported a clean abandon, and the Git tab read "Everything is committed". The operator asked for the cause confirmed, the class swept and made structural, and "N commit(s) not pushed" drawn from HEAD against the remote, not from the hook's own record.
2. **How it was implemented.** `repo.commit()` is the one commit in a list's repository, and it hands every commit to the post-commit hooks. `repo.publish()` is called directly only where a caller tags between committing and pushing. A reader (`remote-publication`) asks each list's remote for its branch with `git ls-remote` through the repository's own `origin`, every 120 s and after every commit, and one sentence (`describe()`) is drawn by the Git tab, the Remote card and a Needs attention row. On the same screen, per the presentation rule: Save All's rules moved behind "How this works", and the "Pipeline (before P.4)" column, filled only for commits older than P.4, was removed with the reader behind it.
3. **Issues encountered.**
   - C223 itself: abandon committed through git directly and never reached the push hook, confirmed from the code. The sweep found four more sites bypassing it: the rename commit, both migration commits, and the list repository's first commit.
   - A stale sentence: the Git tab still said "Commit here for `infra/` files" for the manual commit C104 had removed; its test pinned it.
   - The first measurement from the host: `ls-remote` took 0.99 s, and a second attempt got no answer before the tunnel session closed. So the reader has a bound, and a remote that does not answer reads as not asked, never as in sync.
   - C172 (an unreadable `remote.json` read as no remote) produces the same symptom from another cause; the reader asks through `origin`, so it is visible now, and the row names it.
4. **How they were resolved.** C223 fixed and closed pending the host run; the stale sentence removed and its test inverted; C172's symptom made visible, the record itself not fixed (its row says so). Controls: abandon put back to a direct commit fails the scan and the real-abandon test; `_commit_paths` without `publish()` fails the deferral rule; a reader calling an ancestor "in sync" fails four state tests. One control first broke the file's syntax, so its result was discarded and it was redone as the smallest change.
5. **Numbers.** Two commits, `0dd102b` and the follow-up [git]; 35 tests in two files. Not recoverable: an estimate (none was written). **Acceptance on the host** (the operator, after `0dd102b`'s deploy): Needs attention read "1 commit(s) on Default not pushed … (oldest: 7a72258, 52 min)", compared 7 s earlier; Push now at 21:52:21Z sent it, and GitHub's `main` read `7a72258`. Two defects from that run, fixed the same turn: the row's action sent the operator to the Git tab, and the Push now button is on the Devices tab's Remote card (the operator had to ask where it was); and a manual push did not re-read the remote, so the row could stand for a reader cycle after the push.
6. **Where it left the product.** A commit cannot skip the push hook without failing the suite, and whether the history is on the remote is a measured fact on the screens a person reads.

#### 7.3 step 2 — Mode B: removing a line the device has and intent lacks

*Written at close, 2026-09-29.*

1. **What it was.** Every deploy was merge-only and every restore additive, so the tool could not remove a line. A hand change became permanent in the record: it could be adopted into intent or left, never removed. It surfaced as C184. r2's `load-interval 30`, put on by hand for C70, blocked every baseline for two days. The only resolution the screen could name was the console, in a tool that had removed its terminal. The operator moved Mode B from "deferred" to early 7.3, with r2 as the acceptance.
2. **How it was implemented.**
   - **The computation (2a).** `modules/nsot/removal.py` offers removable units: residue leaves, and stanzas the target lacks. A person selects each unit, and there is never a "converge to intent". The program is the device's own line, negated verbatim in its stanza, or the positive form of a `no` line.
   - **Refusals (2a).** Each has its reason: IOS will not remove it, a physical interface, an account, the management path (the interface holding the tool's address, vty, ip ssh, aaa, static routes), or a named object still referenced.
   - **The measured gate (2a).** `no <line>` can remove more than the line. So a line is removable only where its SHAPE was measured, on its platform, to remove exactly itself. `scripts/nmas-removal-probe` makes that measurement, dry-run by default and never saving, and records it in `removal_measured.json`. Refusing by resemblance is safe and allowing by resemblance is not.
   - **The pipeline (2b).** One `with_removals()` builds the program for plan, apply and run, and each removal carries a reason in the confirm hash and the receipt. Verify reads each removal back gone. Rollback re-adds the device's own lines (`restore_program`), never a negation.
   - **The screen (2c).** Selection is BY ID (`unit_id`), because the plan is masked and a secret-position line's text could never be sent back. Each line shows when it was last rolled back, and why.
3. **Issues encountered.**
   - C191: the device-writer scan does not read `scripts/`, so the new probe script passed the suite unnamed.
   - C192: the probe's dry run printed an AS it would never use, and hid that the BGP shape changes the device's live process.
   - C193: the setting key reduces `no logging buffered` and `no logging console` to one key. Found when the probe's first real run (s4) could not undo its own change.
   - C194: the probe did not record whether its repair ran. So "the repair works" was read from a run it may never have touched.
   - C195: r3's run measured the probe, not the platform (IOS-XE displays ACLs normalised). A shape collision would also have let a destructive removal borrow a safe one's measurement.
   - C196: removing one entry from numbered ACL 97 is destructive or exact depending on which form is sent (IOS: the whole list goes).
   - C197: the acceptance run asked for one decision twice, and the receipt did not keep the removal's read-back.
   - Also measured, not a finding: `logging buffered` leaves the device off its default (`overrides_default`), so it was retired from the probe set.
4. **How they were resolved.**
   - C192, C194, C195 and C197 fixed.
   - C193 pinned by a test and registered (C); FIXED 2026-09-29 overnight (a `no` form keyed on its whole remainder, paired with its positive by prefix, in all three consumers; C200 and C201 registered from the same reading).
   - C196 open (UNKNOWN: does vIOS accept the list-form edit).
   - C191 registered.
   - The numbered-ACL global entry is refused on IOS, citing s4.
   - BGP is unmeasured by choice.
   - The platform record holds cisco_ios (s4) and cisco_iosxe (r3, 9 shapes exact).
5. **Numbers.**
   - Estimate, at costing (2026-09-28 18:35, `c92e8bf`): "about three days to build … so plan on about a week, and treat the three days as the part that goes to plan" [NSOT_STAGE7_PLAN.md, the Mode B bullet].
   - Actual: from costing to acceptance on the host, about 5.5 hours of continuous work. Costed at 00:35 UTC. r2's receipt at 05:53:33 UTC. `baseline/20260929T060249Z` earned at 06:02 UTC, the first earned baseline with a recorded decision.
   - 15 commits from `81007e7` (18:59) to `03aeabe` (00:09 09-29) [git; selection: the Mode B and removal-probe subjects between those shas, excluding `da6b687` (C190, a Save All button)].
   - 7 findings (C191 to C197).
   - Three probe runs on real devices (s4, r3, and r3 again) and one acceptance run, all by the operator.
   - Why the actual is so far under the estimate: the estimate was in days of ordinary work, and this was one continuous session with the operator running probes as each piece landed.
6. **Where it left the product.** The tool can remove a line it measured it can remove, with a reason, verified gone and undoable. The line it could not remove for two days is gone, and the network is at its committed intent.

#### 7.3 — C188: Save All's speed

*Written at close, 2026-09-29.*

1. **What it was.**
   - Starting point: a capture preview failed once in the browser while the app answered 200. Save All read nine devices one after another, twice, and the preview sat past Cloudflare's 100 s edge limit.
   - The operator's scope: concurrent reads with a bounded pool, and an asynchronous preview.
   - Measurement: before and after, per device and in total, naming the slowest.
2. **How it was implemented.**
   - Step 1: `_read_all` reads every device at once (a pool capped at 16), times each device, and names the slowest on the screen.
   - Step 2: the preview is a job (`modules/nsot/capture_job.py`). The POST answers 202 with its id, and the in-flight panel shows the reads. The job announces `capture_preview` (C58, declared in `invalidation.ANNOUNCERS`), and the modal reads the result by id, offering "Check now" while the live channel is down.
   - The apply stays a request, deliberately: after step 1 it takes about the slowest device's read.
   - After the host measurement, each read is split into connect, `show running-config` and disconnect, logged and drawn.
3. **Issues encountered.**
   - C198: the apply took a third of the preview's time for the same nine reads, and every device was faster.
   - C199: the concurrency sweep found 21 serial per-device loops, most with no stated reason.
   - Evidence on C93: s3 was slower under concurrency (23 to 24 s alone, 40.9 s beside eight others). That fits its forwarding every other device's session.
   - C204 (the operator's next Save All): s3's connect failed on the apply, and the result said only "s3 skipped" and the log "not reached", while the reason sat in a traceback under its address.
   - C205, C204's cause: nothing sets the SSH connect timeout, so it is Netmiko's 10 s, below s3's measured 13.7 s connect.
4. **How they were resolved.**
   - C188 closed on the host's measurement.
   - C198 answered by the next Save All and closed: connects were stable run to run, and `show running-config` varied 2 to 10 times on the same device, so the variance is device-side execution; its remaining question moved to C94. The operator's warm-pool guess was ruled out from the code: every capture opens a fresh temporary session (C97).
   - C204 fixed the same morning: the read keeps where and why it failed, the log line says it, and the result leads with it and with what to do. C205 registered (B), with a timeout from measurement recommended.
   - C199 registered: none converted under the stopping rule, and every direct device-layer loop is declared with its reason by a test.
   - Overnight 2026-09-29 (the operator's queue item 5), the read loops were converted through one helper, `modules/fanout.read_each` (`79f5e2b`): the freshness reader's fetches, the hourly startup check, Refresh Hostnames, `nmas-golden-state`, the pending ZTP rows and the heartbeat measurement. The rest carry stated reasons. Converting them found C202: the persistent pool opens every session under one lock, which is why three loops over pooled sessions stay sequential.
   - s3's resources stay in Stage 9 (C93, C94).
   - The operator's standing rule came out of it: reads across devices run concurrently, writes only where order does not matter, and a serial multi-device operation states why.
5. **Numbers.**
   - Three commits: `774f2df` (00:15), `5b75941` (00:27), `782fe05` (00:54), 2026-09-29 [git]; about 45 minutes.
   - Before and after, measured on the host by the operator:

     | | Before (serial) | After (concurrent) | Serial sum, after-run |
     |---|---|---|---|
     | Preview | 101 s | 40.9 s | 124.3 s |
     | Apply | 102 s | 13.7 s | 71.1 s |
   - The slowest device was s3 every time.
   - `baseline/20260929T063600Z` was earned, the second earned baseline, 30 minutes after the first.
   - Suite: 5,685, then 5,694, then 5,704.
   - The next Save All (the operator, 2026-09-29 morning): preview nine devices at once in 25.1 s (serial 102.7 s: connecting 50.9 s, reading 42.7 s), slowest s3 at a 13.7 s connect; the apply read 8 of 9 and took no baseline, s3's connect failing at 11.2 s (C204, C205).
6. **Where it left the product.** Save All is 2.5 times faster to preview and 7.4 times faster to apply, and no request waits on a device. The varying reads are device-side execution (C94's question now), and a device that cannot be read says why and what to do.

#### 7.3 — Capture on the v2 device page

*Written at close, 2026-10-02. **First real run, 2026-10-03, by the operator on r2**: the preview half exercised (the card in place of the tab, what will and will not happen, "None: r2's running configuration equals its golden", r2 at its committed intent, the checks split into pass and at confirm, and no confirm offered: "Nothing to confirm: r2 matches its golden"), correct. **The record half was not reached** (the result card, the commit link, the History entry), since nothing differed; the next real change exercises it, and no change was made to manufacture one.*

1. **What it was.** The first of the device page's actions on v2, from the mockup the operator signed off that day ("Device actions on v2": the preview in place of the tab, the result in place with its next steps, the refusal when the device moved, a check failing on a holder, the phone width; the read timings on hover). The order after it: persist, rotate, deploy with Mode B [tests/signed_off_screens.py; NSOT_STAGE7_PLAN.md].
2. **How it was implemented.**
   - One home: the JSON routes' job start and apply were lifted out as `routes.golden.start_capture_preview` and `apply_captures`, and the card calls those, so the v2 card and today's modal share one read, one hash check and one commit.
   - `modules/device_actions.py` turns the job's preview and the apply's outcome into one card; `templates/v2/_capture.html` draws every state (starting, reading, the preview, the result, each refusal).
   - The card starts its own read (a POST on load) and then listens for `capture_preview`, so the card that waits is the element that asked, which C347's catch-up keys on. The confirm is an htmx button, busy on itself through CSS, and the write carries its list.
   - The Actions menu takes the mockup's order; the rows not yet built still open today's page.
3. **Issues encountered.**
   - The verified-person check first read the preview's own confirm part, which is also false when nothing would be recorded, so a device equal to its golden showed a failing identity check. It is now decided when the card is drawn, from who is viewing.
   - The commit link named an endpoint that does not exist (500 on the result); the route tests caught it.
   - The POST secret sweep had never driven an HTML answer: the card's masked slot is `&lt;redacted:`, and the sweep only knew the JSON spelling. Its follower now reads a job id from an HTML answer.
   - C348: masking a secret that ends a quoted line swallows the quote's close and the separator (seen in the sweep's own output; bucket C).
   - The real-browser click-through failed in 3 of 12 cold runs: htmx binds a swapped control during its settle (about 20 ms), and the test clicked before that. Measured with the page's own htmx events.
4. **How they were resolved.** The check and the link fixed with tests; the sweep extended (the escaped mask, the HTML job id, the device route driven as r1); C348 recorded and left open (C: nothing exposed); the browser test clicks only once nothing settles, then eight cold runs clean.
5. **Numbers.** One commit [git: this commit]. 14 tests in `tests/test_device_capture_v2.py`, two of them in a real browser; fourteen controls, each failing its aimed tests. Findings recorded: 1 (C348). **Estimate versus actual: no forecast was made**; recorded so persist, rotate and Mode B on v2 get one from this, the same kind of work: one action ported to a card with its tests in one session.
6. **Where it left the product.** A device's golden can be recorded from its v2 page, with what it will and will not do, what it was checked against, and the result in place. Save All stays on today's page until 7.4.

#### 7.3 — Persist on the v2 device page

*Written at close, 2026-10-03. **First real run, 2026-10-03, by the operator on r2**: the preview, the busy state and the result correct ("persisted", read back). **One failure: the persist was not in r2's History tab**, readable now and not later. Fixed as a class (C359): History read 4 of the 14 per-device records the survey found and now reads all 14, and every gated operation declares which records History reads for it, so a new one without a reader fails the suite; 12 operations keep no per-device record (C360), and rotation rows name no list (C361). **Once in History, the persist read "rotated and persisted"** (the operator, the same day): the save had always written the rotation's states, so every save, five on the host, claimed a rotation. Fixed at the source (C362): a save records its own state, the five rows are corrected through `record_exceptions` and never rewritten, and the survey for operations wearing another's record found five more (C364 to C368). Fixing it showed History had never drawn a golden exception (C363). A record that claimed something false was only visible once it was drawn where a person reads it later.*

1. **What it was.** The second of the device page's actions on v2, in the signed order (capture, persist, rotate, deploy with Mode B), on the same card pattern as capture [tests/signed_off_screens.py; NSOT_STAGE7_PLAN.md].
2. **How it was implemented.** The card is drawn from the operation's own builders (`persist_op.plan`, `persist_preview`, `persist_result`) through a shared one-device helper in `modules/device_actions.py`, which the remaining cards will use; its confirm calls `persist_op.apply`, the same apply as `/persist/apply`. Persist's preview contacts no device, so the card needs no job and is drawn at once; the confirm is busy on itself while the device saves and reads back. The menu row draws the card in place; without script the page draws it.
3. **Issues encountered.** None new. The one test that failed on first run pinned the sent line without the builder's own words (`write memory (the device's own save)`).
4. **How they were resolved.** The test pins the builder's words.
5. **Numbers.** One commit [git: this commit]. 14 tests in `tests/test_device_persist_v2.py`, two in a real browser, run confined in the gate's suite; eight controls, each failing its aimed tests. Findings recorded: none. **Estimate versus actual:** capture's entry made no forecast but set the basis, one action ported in a session; persist, the same kind with a simpler operation (no job), took a fraction of that, so rotate (a job, and the held-device mockup) is forecast between the two.
6. **Where it left the product.** A device's running configuration can be saved to startup and proved from its v2 page, with the result in place. Rotate and deploy with Mode B are next.

#### 7.3 — Rotate on the v2 device page

*Written at close, 2026-10-03. **First real run, 2026-10-03, by the operator on r2: SUCCEEDED** (rotated, a fresh login, commit d9d8049, confirmed in the startup config; the host's record holds the rotation and its full persistence chain, eight stages passing, in 58 s). Four failures of the card around a correct operation: no stepper while it ran (C370), a terminal command in a browser's result (C371), an export link that opened today's device page by address and nothing on it (C372, with two more such dead ends found on the capture card and one on Needs attention), and a "still true" that contradicted the result above it (C373). Each fixed the same day; the v2 export waits on its mockup.*

1. **What it was.** The third device action on v2, on the card pattern, including the mockup's held-device artboard: refused while another operation holds the device, the card names the holder and "reads again when it finishes" [tests/signed_off_screens.py].
2. **How it was implemented.** The card asks for its own preview, whose plan reads the device's account line live; its confirm and `/rotate/apply` call one `rotate_op.confirm_and_start` (the plan computed again, a moved fingerprint refused, the job started with the verified person carried in); the card then waits for the job's `rotation` announcement. For the mockup's promise, `device_ops` announces `device_holds` on each release in the app's process, and a card refused for a hold (capture's and persist's too) asks `when-free`, which answers 204 until the device is free.
3. **Issues encountered.** C358, found by the real-browser test: an announcement made while a button's request was swapping the answer into another element was lost, because C347's catch-up remembered requests only by the requesting element; the "Rotating" card waited for ever.
4. **How they were resolved.** The client remembers a request under its target's id as well (C358, fixed the same turn). A hold released by a host script cannot announce (it has no emitter): the card says it reads again "if the tool runs it", and keeps Preview it again.
5. **Numbers.** One commit [git: this commit]. 15 tests in `tests/test_device_rotate_v2.py`, two in a real browser; nine controls, each failing its aimed tests. Findings: 1 (C358, fixed). **Estimate versus actual:** persist's entry forecast rotate between capture and persist; it took about capture's time, the hold announcement and C358 being the difference.
6. **Where it left the product.** A device's credential can be rotated, recorded and persisted from its v2 page, with the result and its one next step in place, and a card blocked by a hold clears itself when the hold ends. Deploy with Mode B is next.

#### 7.3 — Deploy with Mode B on the v2 device page

*Written at close, 2026-10-03 (overnight). It awaits its real run on the host, which sends a program to a device and so is the operator's.*

1. **What it was.** The last of the four device actions on v2 (canvas boards 5 and 6): the device's whole committed intent, merge-only, with a dangerous line's stated reason and the residue a person ticks for removal (Mode B), each reason in the hash; run as a job with the stepper; the result from its receipt, and a rolled-back verify's two ways out.
2. **How it was implemented.** Nothing new on the server's deploy path: the card draws THE plan (`plan_devices`) and its preview, planned again on each change of the form, and the confirm runs the batch apply's job (`deploy_job`) for one device with the whole intent. The stepper is the pipeline's ten declared stages; since the pipeline notes a stage as it starts and rotation notes a step once done, each job declares which (`JOB_STEPPERS`). The rollback's next steps open today's revert and retry tools through the index's openers (map entries, no new function).
3. **Issues encountered.** The deploy job named every job "monitoring profile apply" (C364's shape), which a whole-intent deploy would have inherited; a control showed the card's own "waiting on a reason" guard decided nothing the preview's check did not already decide.
4. **How they were resolved.** The job's kind follows its scope (`deploy`, `IP SLA send`, the profile apply). The redundant guard left the confirm's condition and stays for the wording, one owner for the decision.
5. **Numbers.** One commit [git: this commit]. 11 tests in `tests/test_device_deploy_v2.py`, one in a real browser, and a deploy-steps test in `test_job_stepper.py`; seven controls, six failing their aimed tests and one showing the redundancy above. **Estimate versus actual:** rotate's entry set the basis (about capture's time); deploy took about that again, less the server work it reused.
6. **Where it left the product.** All four device actions run on v2: capture, persist, rotate and deploy with Mode B, each a card in place of the tab, the job-backed ones with the stepper. Today's device page keeps restore, seed and retire until their cards.

#### 7.3 — Restore, revert and retry, seed and retire on the v2 device page

*Written at close, 2026-10-03 (evening). Each awaits its real run on the host; restore sends a program to a device and so is the operator's.*

1. **What it was.** The device page's remaining actions, from the canvas's boards 8 to 12, signed off by the operator with two changes (seed shows the device's own lines as such, never blocking; retire drops what is generated and names the rest with how each is removed) and built in the operator's order: restore as a job carrying its list (C396), revert and retry, seed, retire. With them every action under the device page's Actions runs on v2, and a retired device's address shows its record (C185).
2. **How it was implemented.** Each card draws the operation's own builders, as the first four did: restore the plan the legacy route uses (`restore_plan`, split out of it) and the deploy job; revert and retry `intent_ops`' previews and applies, offered only while a rollback block stands (`block_state`, one read); seed `seed.entry_for` and `seed.apply`; retire `retire.plan` and `retire.apply`, its watchers sorted into generated (dropped at their next regeneration, the scrape targets regenerated and read back after the commit) and surviving (each with how it is removed). Each confirm carries its list. The retired record is read from the retire commit's trailer. The route-reachability scan learned to read the menu's loop of rows, as it reads the panel grid.
3. **Issues encountered.**
   - Board 8 had drawn three "unmodelled" lines typed from memory; measured, all nine real configs were fully modelled. Checking the operator's question about those lines found C397: the device's self-signed trustpoint, named after its chassis and regenerated at boot, was parsed into intent, so a deploy after a regeneration would send a trustpoint and keypair the device no longer has.
   - Board 9 promised a restore could "keep intent and re-apply" a moment before onboarding, and that re-applying the golden now would put lines back; the code does neither (it leaves the device or un-onboards it, and the golden now sends nothing by construction).
   - Board 12 said Oxidized drops a retired device "at its next sync from the inventory"; nothing regenerates `router.db` (C398).
   - C395 recurred while gating restore: a child pytest started inside a worker took itself for a worker.
4. **How they were resolved.**
   - C397 fixed in the one place every parse, program, residue and round trip already goes through (`strip_for_roundtrip`), the device's own blocks declared as one shape; intent committed before it is never sent the trustpoint either.
   - Boards 9 and 12 redrawn or drawn true, and C398 recorded for the operator's decision.
   - C395 decided from the session's own configuration.
5. **Numbers.** Four commits (4c336be, d354cc2, cd0ffc7, 35b838c), the first three green in CI (#364 to #366) and the fourth running when this was written. Tests: 13 for restore, 19 for revert and retry, 10 for seed, 16 for C397, 12 for retire, each action with a real-browser path from the menu to the result. Controls: about 30, each failing its aimed tests. Findings: C395 recurred and fixed, C396 half fixed (the legacy route waits for cutover, by decision), C397 and C185 fixed, C398 recorded. **Estimate versus actual:** deploy's entry set the basis, about capture's time per action; the four took about that each, restore more (its job and history fixture) and seed less, plus C397's fix.
6. **Where it left the product.** Every device action runs on the v2 device page, each with its preview, its confirm carrying its list, and its result in place; a device that leaves has an address that says so. The combined deploy's arrival watch is next. It is a different kind of work (a watch after a batch), so this entry forecasts nothing for it.

**Retire's real run (added 2026-10-04).**
- The operator retired r5 from its v2 page, the first real run of the REMOVE mode and of the
  Oxidized helper's first write since C415.
- Finish read "<r5's address>'s row was removed … read back". Measured read-only afterwards, the
  helper kept three backups of `router.db`.
- Finish could not say that it had pruned the older ones. That was C430, fixed the same night
  (0ccbcc3): Finish now names how many it removed, or that removing them failed.
- Restore, revert and retry and seed still await their real runs.

### 7.4 — Devices › Save (C593; the first of 7.4's fleet actions)

1. **What it was.** Today's Devices page offered Save All, a whole-network capture that can earn a baseline. v2 had none (C593, raised by the operator walking C553). Board C ("one Save does both", approved 2026-10-04) made it one operation: each chosen device saves its running config to startup, the startup is read back, and the running config is recorded as its golden, one commit for the batch. Board A gave the Devices page a selection bar whose Actions carry it.
2. **How it was implemented.** It is built from two operations that exist, never a third copy: persist's device-side save and read-back (`onboard.persist_on_device`, its record `_record_native_persist`, its device checks and hash now shared as `persist_op.row_checks`) and capture's read and record (`routes.golden._capture_entry`, `repo.save_golden`). `modules/nsot/save_op.py` plans from stored records only (the inventory, the hourly startup check, the reachability reader, the holds) and runs as a job. Each device runs on its own worker, which holds it, saves it, reads it back and reads its running config, then releases it; one commit follows, `Source: save`. `modules/save_page.py` shapes the plan, running and result cards. The Devices page gained the bar and a Startup column; the manual gained a How it works page with its diagram and the Devices page's new sections.
3. **Issues found** (all in this build): the job thread's hold did not cover a worker's session, because `device_ops.may_write` is per thread, so the real save would have been refused (found by the test asserting the save was held); `save_golden` refuses a whole batch for one device the manifest lacks (C597); board C's lead count, "not saved: startup differs", is measured by nothing (C596); the running card would never have redrawn, because v2's client relayed no `save` key (found by the subscription check); a form with no `method` is read as a GET by the reachability check.
4. **How they were resolved.** Each worker holds its own device. Save leaves a device the manifest lacks out, by name, before anything is sent; C597 itself (Capture and today's Save All) is registered UNKNOWN, its measurement the operator's, since the agent's hook refuses that read. The summary draws only what is measured ("accounts in startup"), and C596 asks the operator for a capture of the two `!` header lines on r2 and s1. The relay was added. The form carries `method="post"`.
5. **Numbers.** One commit, the code and its records together. Tests: 27 in `tests/test_save_v2.py`, three in a real browser. Eight controls, each failing its aimed tests; the eighth was written because the seventh first passed (the job's own hash re-check had no test). The whole suite ran once before the gate, with six population checks failing on declarations this build owed. Findings: C593 closed, C596 and C597 added. **Estimate versus actual:** no forecast was made for this sub-task, and its time is Not recoverable (no start was recorded). It is the first fleet action, so it is the basis 7.4's next ones are forecast from.
6. **Where it left the product.** Devices › Save replaces today's Save All on v2, and a record without a save is offered only by the device page's Capture. Next are the C553 walk on v2 (the operator's) and the capture C596 needs. 7.4's other rows on board A (Edit intent for N, Apply the profile to N) are not drawn until their operations exist on v2.

**Added 2026-10-09: C601.** The operator found the whole network's Save took no baseline. It committed `Source: save`, and the baseline decision wants one only for `save_all` (or two changed goldens), so the claim in point 1 above was false as built; the tests had asserted the commit and every outcome and never a baseline. Fixed the same day: the whole network saved together is `Source: save_all`, judged by measurement as today's Save All is, and the result card says earned or why not.

### 7.D — The GUI redesign (open)

7.D is open. Commit times are the committer's local time (UTC-6); the operator's decisions are dated in UTC, which is why a decision can read 2026-09-30 beside a commit of 09-29.

#### 7.D steps 1 to (c) — Research, brief, mockups and the stack costing

*Backfilled 2026-09-30, at the spike's close. These steps each closed at the operator's sign-off and no entry was written then: the rule "an entry is written in the turn its sub-task closes" was not applied to design steps, which is the gap this paragraph names.*

1. **What it was.** Redesigning the interface before building any more of it in the old layout: research on the existing pages, a design brief, mockups at desktop and phone width, and a costing of the stack against those mockups. The governing principle, the operator's: the frontend decides and the backend serves it; tests are a cost, never a veto [NSOT_STAGE7_PLAN 1g].
2. **How it was implemented.** Documents and mockups, no product code: the plan's requirements (`cdb48f5`), the research (`62ce209`), the brief and its five decisions (`84afd4c`, `741a973`), the integrated services and connector classification (`fcfab3b`), the services mockups (`91ad104`), the stack costing (`d24a509`) and the review of mockup version 7 (`c994fc6`). The mockups live on a canvas outside the repository (31 boards at version 9).
3. **Issues encountered.** C226, C227 and C228 (from the research's inventory: a dead Settings switch, Bootstrap loaded twice, a pointer to a removed button); C229 (the scrape targets hand-kept); C230 (the NMAS's Grafana token holds an Editor's permissions); C231 (the topology service's SVG served to the internet with no login); C100 advanced to its one-time steps. Beside them, the heredoc hook (`f46f0f6`), after a third slip.
4. **How they were resolved.** C226 to C228 fixed the same turn (`29fa733`); C229 scheduled into P.7, then pulled forward (below); C230 and C231 registered; the silence fetch built (`6a2897c`).
5. **Numbers.** Eight documentation commits from 18:55 to 22:15 on 09-29 (about 3 h 20 min), about 2,100 lines of brief and plan. Not recoverable: the time spent on the mockups separately from the documents.
6. **Where it left the product.** Unchanged for a person: every decision recorded, nothing built.

#### 7.D spike — The device page's Overview and Monitoring in option A

*Closed 2026-09-30 by the operator's review on desktop and phone: "it feels good", so option A (Jinja, htmx, Alpine's CSP build, uPlot, no build step) is approved for the redesign.*

1. **What it was.** One real screen built in the chosen stack before the rest of the redesign commits to it, judged first on what the operator judges (does it look like the mockup, do menus and live updates feel smooth, does it work on the phone) and then on page weight, the content security policy, lines of code and whether the tests catch a planted defect.
2. **How it was implemented.** `/v2/device/<name>`, beside today's page. `routes/device_v2.py` renders Jinja pages and fragments under a strict policy (`csp.STRICT_POLICY`: no inline script or style). `modules/device_page.py` reads every fact from a record the app already keeps; `modules/panels.py` is the pure panel logic; the grafana-dashboards reader stores every dashboard's model. `static/js/nmas_panels.js` draws each panel natively over uPlot, and `static/js/nmas_v2.js` relays the existing socket's announcements to htmx events. Libraries vendored by `scripts/nmas-vendor`, each tarball's sha512 checked against the registry.
3. **Issues encountered.**
   - C232, found building it: `rcn-lab1-snmp`'s device panels can show no device, because no SNMP series carries a `device` label. Measured further at the review: this Prometheus never had one (its oldest sample, 2026-08-30, is its install).
   - The review found four defects: the page drew the operator as `unauthenticated` (C233), the model was missing, the panels ignored the dashboard's layout, and a one-option selector read as broken.
   - Measured beside them: the inventory's `role` column says `router` for the four switches (C225 extended), r6's golden has no SNMP community, and retired r5 is still scraped.
4. **How they were resolved.**
   - C233 fixed the same turn (`identity.viewer()`, one path with `/identity/status`).
   - The model is read from the committed golden's own header, with its basis.
   - The panels placed by their own `gridPos`, with the dashboard's row headings.
   - The selector says "1 of 5 dashboards can show a single device" and lists the rest with why.
   - C232 fixed at the source: the scrape targets generated from the inventory with `device` and `role`, pulled forward from P.7 by the operator, with a job-health row comparing the running Prometheus. Its install is the operator's one-time step.
5. **Numbers.**
   - The spike commit `3a476b2`: 50 files, about 1,830 lines of program and 500 of tests, 8,600 insertions with the vendored libraries.
   - First load 192 KB compressed, 2 KB of it re-sent each load (today's `/`: 558 KB and 70 KB).
   - Ten planted defects, each caught by the test aimed at it (one only after a direct test was added).
   - No estimate was made, deliberately: no front-end build of this kind had finished to forecast from. This is the first, and the review fixes are its second commit.
   - Not recoverable: the build's start time. The backend was written in a session summarised before the first commit.
6. **Where it left the product.** Option A decided. One device page tab pair works in the new design with the operator's identity; the rest of the redesign builds on it. The device dashboards show data once the generated targets are installed.

#### 7.D step 4, part one — The Devices list and the device page's tabs (open: Ask the device)

*Written 2026-10-01 at about 10:45 UTC, overnight and without the operator, as the part closed short of one tab; the step stays open.*

1. **What it was.** The operator's item 5 for the night: the remaining step-4 work under the GUI brief, the Devices list and the device page's tabs. Under the night's rule (no session to any device beyond the app's own jobs, s3 being CPU-starved), every tab reads a store or a service the app already polls, never a device.
2. **How it was implemented.**
   - **Devices** [git f1863ba]: every device with status, address, platform and its intent state AS OF ITS LAST CAPTURE (the golden commit's `Intent-Match:` trailer), in a fixed number of reads (one bounded `git log`, one `ls-tree`), pending onboardings as rows.
   - **History** [git c752d89]: golden commits, intent commits and receipts as one timeline.
   - **Intent**, read-only [git fb5320d]: the document committed at HEAD, its last commit, the profile sections it inherits.
   - **Neighbours** [git 204f2e2], C38: the adjacencies the fleet's committed intent implies (OSPF by shared subnet under the network statements, passive interfaces excluded; OSPFv3; BGP's named neighbours), against Prometheus's `ospfNbrState`, `ospfv3NbrState` and `cbgpPeer2State`.
   - **Logs** [git 9428155]: the device's syslog from Loki, matched by origin-id, heartbeats folded by their exact form.
   - **NetBox** [git aa061be]: the record and who owns it by NMAS's provenance.
   - C38's second consumer [git f66e8ee]: a reader runs the Neighbours comparison fleet-wide and Needs attention names a down link once per pair, after two reads.
3. **Issues encountered.**
   - The passive-interface test could not fail at first: no fleet device had OSPF on s3's management segment, so the fixture could not exhibit it. A test now builds one from r1's intent.
   - The first prefix test for Logs (`r30`) could not fail either, since the substring stage already excluded it; it uses `br3`.
   - Measured beside them, from the night's captures: s3's heartbeats arrive about nine minutes apart for a five-minute timer and its own timestamps read Sep 27 (its slow clock, C93); NetBox holds `ios` for every device (A4, now drawn on the NetBox tab).
   - After the entry was first written: C291 (the Devices list linked a pending onboarding to a page that 404'd, mine from f1863ba) and C292 (three defects in the night's deploy-path code, P.9 (d2) and C290's: a v2 batch's golden commit recording `unauthenticated`, a rollback re-creating an IP SLA operation the push never reached, a refused device read as "not reached"), the second found by an independent review agent run over the night's two riskiest commits before any deploy.
4. **How they were resolved.** Both vacuous tests replaced and shown failing under a control; A4 drawn, its writer unchanged (7.6). C291 fixed by the pending page the brief already described [git 61a914a]; C292 fixed with six controls [git a924db5].
5. **Numbers.** Seven commits, f1863ba (03:59 local, UTC-6) to f66e8ee (04:42), then 61a914a (C291) and a924db5 (C292) by 05:04, about 45 minutes of commits after the Devices list's build began in the session before it. Every new check carries a control that fails only the test aimed at it (twelve controls across the seven). The fixtures are real answers captured read-only from the host (Prometheus, Loki, NetBox), the host's own addresses replaced. **No forecast was made for step 4**, so there is nothing to check; the page-per-tab rate here (one tab in 6 to 10 minutes of commit time, on a pattern the spike established) is the measurement the next forecast should start from. Not recoverable: when the Devices list's build began (the session was summarised before its first commit).
6. **Where it left the product.** The v2 device page draws every tab but Ask the device, which sends commands to a device and waits for a session with the operator awake. Needs attention names a down adjacency. None of it is deployed yet.

#### 7.D — Settings › Installation (boards F2 to F4)

*Written at close, 2026-10-10 (UTC), the turn its last tab was committed.*

1. **What it was.** The installation's own settings, the ones that hold for every network, lived only on today's Settings modal. Board F (P.8) gave them a v2 page of six tabs. F2 (the Records database card), F3 (the NetBox connection, Proxmox, Commit author and Server cards; the TFTP root retired, C616) and F4 (AI and workflow, Diagnostics, Access and identity, Platforms and roles) were each signed off before their build. F4's Platforms and roles carries the operator's validation: a driver is chosen from the drivers Mercury supports, Save previews the devices it moves, and Test opens one read-only session to one of them through the new driver.
2. **How it was implemented.** One page, `settings_installation.html`, with a tab per board section, each a fragment under the strict policy.
   - **The cards** (`modules/installation_settings.py`): Save writes what changed and records the field names, never values. Test draws the service's own answer. Replace stores a secret without drawing or recording it and tests at once. Turn off is NetBox writes' only control here.
   - **Diagnostics** (`modules/installation_diagnostics.py`): redaction measured by a canary through every log handler; one drift schedule, Check now, and the run's announcement; what is in flight across every network (`modules/in_flight.py`, now also the operations route's reader); the app's own log tail (`modules/app_log.py`, now also `/logs/server`'s).
   - **Access and identity** is read-only. Its one control, Record this decision, writes the value in force into the installation's settings record (C625).
   - **Platforms and roles** (`modules/platform_maps.py`): a preview from each NetBox network's last inventory, never a refresh; a Test through `reads.start` with a per-device driver override; a confirm bound to the preview's fingerprint.
3. **Issues encountered.**
   - A network card's save stored an installation secret sent to the Default network, then answered 404 (C615).
   - Nine texts sent a person to today's Settings > Integrations (C617). One of them was this build's own, claiming an editor that never existed.
   - `cf_access_jwks_ttl` 0 was read as 3600, while meaning "keep for ever" (C621).
   - The platform and role maps had no screen anywhere (C622). A new platform's dialect was stored as a template folder (C628).
   - Redaction's health was measured and drawn nowhere (C624). Ratifying a gate was only an app-log line (C625).
   - Mid-build, the laptop's /tmp ran out of inodes from the suite's leftover folders. Unrelated tests failed "No space left" (C627).
   - The revert's one-shot TFTP and the ZTP responder cannot share udp/69 (C618). Binding one address does not separate them, as measured in a network namespace.
4. **How they were resolved.**
   - C615 is refused before anything is written.
   - C617 is closed by a parsed scan of `modules/` and `routes/` with a planted case.
   - C621 is bounded to 300 s to a day, the reason on the field.
   - C622, C624, C625 and C628 were closed by the tabs that draw them.
   - C618's design 2 is signed off and waits for its build. C627 is registered UNKNOWN, to be measured for a week.
   - C619 (v2 cannot turn NetBox writes on), C620, C623 and C626 stay open, each placed in the register.
5. **Numbers.**
   - Seven build commits, 6dcd8c3 (12:58 UTC−6, 2026-10-09) to 441f977 (19:43), with three register commits among them. The C614 CI split and C615's fix also landed in that span, so its 6 h 45 min of commit time is not this page's alone.
   - 47 tests in `tests/test_installation_settings.py` (Condition 2 against a real PostgreSQL 18), and the six tabs in the browser layout test.
   - Eleven controls from F2 part 2 to F4, each failing its aimed test.
   - Findings: C615, C617, C621, C622, C624, C625 and C628 closed; C616, C618, C619, C620, C623, C626 and C627 open or waiting.
   - **Estimate versus actual:** no forecast was made. Measured here: F4's four tabs took 8, 42, 9 and 17 minutes of commit time after its sign-off commit (6a09233, 18:27), the longest the one with a new module and a Needs attention source. That rate is the basis for a forecast of the next settings-kind screen.
6. **Where it left the product.** Every installation setting is on v2: drawn, or read-only with its reason. `installation_settings` has left the cutover's gap list (`tests/todays_page_links.py`). None of it is deployed yet.

#### 7.D — The six cutover blockers (networks, NetBox, onboarding, Capture's reason, templates, Reload)

*Written at close, 2026-10-10 (UTC), the turn the sixth was committed. The six were one sub-task in the operator's order ("the six cutover blockers in dependency order"), so they have one entry.*

1. **What it was.** CUTOVER.md, re-measured against the route map (C630), named six things only today's pages could do. Each was built on v2 under the Phase 7 operating mode, its board drawn by the agent and counted as signed off, each decision logged in docs/STANDING_APPROVAL_LOG.md:
   - **Networks:** the top bar's picker, each verified person's own choice; create and delete (a deleted network's data moved aside, never erased); a network's inventory source.
   - **NetBox:** import and remove as preview jobs, the confirm bound to the preview's token and able to turn writes on (C619).
   - **Onboarding:** Add device (static, DHCP, ZTP by MAC), and a pending device's Verify, bootstrap config and Abandon.
   - **Capture's reason** for a shrink, and its What next by direction (C486).
   - **Templates:** Edit…, Bindings…, and Seed the library….
   - **Reload** (P.14's plain form).
2. **How it was implemented.**
   - **One core for today's routes and v2's.** Today's onboarding, NetBox and template code was taken out of its routes into functions both call (`routes/onboard.py`'s cores, `modules/netbox_ops.py`, `template_write.commit`), so v2 adds screens, not second implementations.
   - **Confirms bound to previews where today's were unbound.** Onboarding's Create, compared field by field with the reviewed plan (CONCURRENCY_AUDIT R36). Abandon's dry run, taken again under the device's hold. The template editor's base blob. Bindings' file and change. Seeding's library signature. Reload's read of the device.
   - **Reload's blast radius from records, not a probe.** Committed intent's subnets, and this host's own addresses.
3. **Issues encountered.**
   - A read that created a folder: the reload record's path resolved through `get_list_data_dir`, caught by the store-isolation teardown.
   - A preview race: NetBox's "importing" was written after its thread finished.
   - IOS-XE's `bootflash:x,12;` boot variable was parsed as a file name.
   - Reload's run refused itself, its busy check seeing its own hold.
   - A test that skipped whenever it ran (no banner block in the shipped template), rewritten to test.
   - Twice a gate run caught what the targeted runs had not: a 500 px overflow from a second row control, and a pinned signature.
   - Measured and not a finding: Approve…'s check does not leak a golden's secret, because the comparison masks it.
4. **How they were resolved.** Each defect was fixed in the commit that found it. A control for every new check, each failing its aimed test, with two tests rewritten when their controls passed: the VLAN rule's planted case lacked a device on the switch's own subnet, and the missing-image test also failed on the boot variable. C486, C619, C638, C639 and C640 were closed; C641 and C635 were registered.
5. **Numbers.**
   - **Commits:** ten build commits, from eda63ea (21:51 UTC−6, 2026-10-09) to Reload's, about 3 h of commit time across the six.
   - **Tests:** 126 new test functions in eleven files, three walking a real browser.
   - **Today's-page links:** the gaps fell from seven to four (`tests/todays_page_links.py`).
   - **Estimate versus actual:** the forecast was 2 to 3 h a blocker, from the F boards' rate. Measured: about 1 h each for networks, NetBox, onboarding and templates, 15 minutes for Capture's reason, and about 1 h 40 min for Reload, the only one with a new device-changing run. That is the basis for forecasting the nice-to-haves, which are screens of the same kind.
6. **Where it left the product.** Everything today's pages did that v2 must do before cutover is on v2. The four remaining today's-page links (Plan a deploy for several devices, Re-apply, Logs, DHCP) are nice-to-haves or C633. None of it is deployed yet, and none has run against a device or the real NetBox: the walk at the end of Phase 7 does that.

## Part III. Side campaigns

Threads that ran across stages rather than inside one: each started from one finding and followed its class. Their commits interleave with the stages', so each entry states the rule that selected them.

### Side campaign — Store hardening: from the settings erasure to one file-store module

*Backfilled 2026-09-29.*

**1. What it was**

It started on 2026-09-23. The onboarding wizard refused to create a device, the Cloudflare Access values were empty, and the cause turned out to be that `user_settings.json` had erased itself [4f8a0f1]. The same problem came back twice from other directions: a flaky settings test on 2026-09-25 (C20), and a credential override that disappeared on 2026-09-28 (C156, which led to C157). The campaign set out to find every store the program reads, modifies and writes back, and to establish whether a torn read or a concurrent writer could empty it. It gave most attention to stores whose loss cannot be rebuilt.

**2. How it was done**

- **The erasure.** It was a six-step chain [4f8a0f1]:
  - the save truncated the file in place;
  - a read landed in that window;
  - the unreadable file was read as `{}`;
  - the next write saved that `{}`;
  - the file then read as v0, and 107 defaults were seeded;
  - the blank peer allowlist trusted every peer.

  The fix separates *absent* from *unreadable*. An unreadable file raises `SettingsUnreadable` and is kept as `.corrupt-<ts>`; saves go through a temp file and `os.replace`; the posture panel draws the failure. `nmas-settings-diff` was added to recover which values somebody had chosen [a25bdba].
- **C20** added a temp file per write and `settings_lock()` (an RLock plus a cross-process `flock`) around all four read-modify-write sites. An AST scan requires the lock wherever a function both loads and saves [2a121ef].
- **C157** applied the same fix to the credential store [3a946bb]:
  - an unreadable store refuses on the write path and is preserved;
  - every write is logged with the key names it changes, never the values;
  - a save made outside the lock is refused.
- **`modules/filestore.py`** made that fix generic once [2449206]. It provides `PathLock`, `write_atomic` and `read_json_for_write`. The credential store, the NetBox created-object record, `rolled_back.json` and `devices.csv` all moved onto it.
- **The sweep.**
  - The first survey was static: 27 loaders that read an unreadable file as empty [3a946bb]. It was scoped by format (JSON), so it missed `devices.csv`.
  - The second survey listed every place the program writes a file, 85 of them. That is the population the property itself defines, and it found C160 [2449206; docs/LESSONS.md#the-sweep-stopping-rule "A SURVEY SCOPED BY FORMAT…"].
- **Controls.** Every fix has a control that removes the property and fails only its own test; 2449206 has eight [commit message]. The lost-update tests run the writers as separate processes.

**3. Issues encountered**

- **The erasure itself.** It has no register row; it is recorded in CLAUDE.md and NSOT_WRITEUP_NOTES. Its chain also exposed the fail-open peer allowlist [cd0696e].
- **Consequences recorded separately.** C7: the reseed froze every non-empty default. C28: settings that gate a guard were erased, and each was found only by the failure it caused [OPEN_FINDINGS].
- **C20.** The flaky test was caused by import-time binding. The real defect was a shared temp name plus unlocked writes, which corrupted the file. The shared temp name had arrived with the 09-23 fix itself [ca52ac1].
- **C156 (UNKNOWN).** An override left the credential store, and nothing records why.
- **C157.** The credential store had all three erasure ingredients: it read an unreadable file as empty, its lock worked within one process only, and it used one shared temp name. The 09-23 notes had said `credentials._save()` already had "the correct shape" [NSOT_WRITEUP_NOTES "The long fuse"].
- **C158.**
  - The created-object record could erase NetBox provenance for every list.
  - `rolled_back.json` was truncated in place with no lock, and a torn read lifted every rollback block.
- **C159.** The remaining stores in the sweep, where the loss is reconstructible or derived.
- **C160.** `devices.csv` had four problems:
  - it was truncated in place;
  - five read-modify-write paths held no lock;
  - Reorder dropped any device the order did not name;
  - Refresh Hostnames wrote back a copy that was minutes old.
- **Found while fixing the rest [2449206].**
  - C161: the migration backfill drops the `platform` column.
  - C162: a relative-path fixture put a lock file in the checkout root, and no guard noticed.
  - C163: one test error whose report was lost.
  - The new module's first test run hung, because lock depth was tracked per instance.

**4. How they were resolved**

- **Fixed:**
  - the erasure [4f8a0f1];
  - C20 [2a121ef];
  - C28, as a job-health row [b1fa4b0];
  - C157 [3a946bb];
  - C158 and C160, together, on filestore [2449206]. An unreadable rolled-back record now *blocks* every plan. Reorder keeps the devices it does not name, and Refresh applies only its renames.
  - The hang: lock depth is now tracked per (thread, path).
- **Deferred by the operator's stopping rule.** A sweep registers everything and fixes only its A items [2449206].
  - C159, C161 and C162 go to Stage 9.
  - C163 stays UNKNOWN until it recurs; the commit gate now keeps the whole run.
  - C7 is B and blocks 7.7.
  - C156 stays UNKNOWN; C157's write log answers it from now on.

**5. Numbers**

- **Commits.** Selection rule: a subject naming the erasure, C20, C157, C158 or C160. That gives 7 commits, 4f8a0f1 (2026-09-23 18:26 -0600) to 2449206 (2026-09-28 12:20 -0600): 4f8a0f1, a25bdba, 2a121ef, ca52ac1, f7a237f, 3a946bb and 2449206. The edge is ambiguous. With cd0696e (the peer allowlist), b1fa4b0 (C28) and 71ed99e (which recorded the survey lesson), the count is 10.
- **Elapsed time.** 4 d 17 h 54 min, in three bursts [commit dates]. The C157–C160 burst took 58 min.
- **Findings.** 4 fixed as primary (C20, C157, C158, C160). C28 fixed and C7 open as consequences. 5 registered and left (C156, C159, C161, C162, C163).
- **Measurements.**

  | Measurement | Value | Source |
  |---|---|---|
  | Defaults reseeded after the erasure | 107 | 4f8a0f1 |
  | C20 before the fix: two threads × 150 writes | file unreadable in 2 of 2 runs | 2a121ef |
  | C20 after the fix | 300 of 300 keys | 2a121ef |
  | C157 without the `flock`: two processes × 60 overrides | 76, 67 and 63 of 120 kept; **37–47% of writes lost** | 3a946bb |
  | Credential store at the time | 23 template secrets, 1 profile, 1 override | C157 row |
  | Surveys | 27 loaders, then 85 write sites | 3a946bb, 2449206 |
  | New tests | 4 + 12 (store integrity), 7 (settings concurrency) | counted |
  | Suite | 5197, then 5209 passed; 37 consecutive clean runs after the one error | 3a946bb, 2449206 |

**6. Where it left the product**

Every store whose loss is unrecoverable, or would lift a guard, now goes through one module. That module locks across processes, writes atomically and refuses to save over a file it could not read. The rest are named in C159.


### Side campaign — The Grafana rule audit: hand-built alert rules measured, and P.7 decided

*Backfilled 2026-09-29.*

**1. What it was**

On 2026-09-28 the operator was measuring a precondition for 8.6, the agent's triage reader. Grafana's rules view showed 16 rules, all inactive, while its Alertmanager held 2 active instances (C165) [05a0ccf]. Following that up exposed two rules that had been in no-data for days (C166). That led to the wider question of whether any hand-built rule had ever been verified (C168). The campaign set out to establish, rule by rule, whether each rule *could* fire on what the fleet produces, and whether it *had*.

**2. How it was done**

- **Read-only probes (3 to 6).** The operator ran them on the NMAS host, through NMAS's Grafana client and Grafana's datasource proxy [22cf328]. They collected:
  - each rule's expression, no-data setting and datasource;
  - the rule's own query over 24 h, then 7 days;
  - the syslog stream's labels, and its lines counted per IOS severity digit;
  - 30 days of state history.
- **The test for a rule.** A rule was judged by whether its query's extreme crosses its own threshold, not by whether it evaluates without error [796f2f7; NSOT_PLAN P.7].
- **Uncapped history.** After a capped read produced wrong verdicts, every history verdict was re-read one day per request. Any window that came back as a full page was split and read again [d99a260].
- **Rule fixes.** These are the operator's edits to rules NMAS does not own. They were specified in the register and dry-run first. The syslog fix refused to write unless every label named an inventory device [6ef9d8c].

**3. Issues encountered**

- **C165.** The two endpoints were not disagreeing. The control compared unlike counts (condition-firing instances against all active instances) [99ff600].
- **C166.**
  - `Interface down` had been in no-data since 2026-09-25T21:23:50Z, and `Critical syslog received` since 2026-09-27T08:40:50Z.
  - The syslog rule was not blind; it was miscoded. `|= "CRIT"` never matches IOS's severity digit.
  - The implementation's "never fired" was wrong. It had fired 9 times in 30 days, on mnemonic *names* containing CRIT.
  - The first attribution regex took IOS sequence numbers as devices, giving 11 "devices" [22cf328; 6ef9d8c; NSOT_PLAN P.7].
- **C167.** `prometheus_url` was empty while Grafana read Prometheus [5bb1cd7].
- **C168.** Of the seven hand-built rules [22cf328; OPEN_FINDINGS C168]:
  - gRPC is miscoded: a lost source's series vanishes, so its count never drops below 1;
  - `Interface down` reads a healthy network as no-data;
  - the syslog rule works by accident;
  - `IP SLA probe failing`, first read as never alerting, WORKS;
  - `Device unreachable` "never alerted" was false;
  - `Interface output discards` is noisy;
  - the syslog `host` label is the collector, so a syslog alert names no device.
- **Found outside the scope.**
  - The scrape targets are a hand-kept list: retired r5 is still polled, and r6 is polled by none [4ec7ffb].
  - A malformed register row passed every hygiene test [796f2f7].
  - C169: the ZTP responder sent a refusal before recording it. It was found by d99a260's own gate [d99a260].

**4. How they were resolved**

- **C165.** Closed as a measurement defect. A reader now names the endpoint it read and when [99ff600].
- **C166.** Closed after the operator's fix was read back. It alerts on severity 0–2 by the mnemonic's digit, takes the device from the origin-id, and treats no-data as OK; over 7 days it names r1, r3 and r4 [d99a260]. Severity 3 was deliberately left out (`SMART_LIC-3-COMM_FAILED` is expected under D4) [796f2f7].
- **C167.** Closed on measurement. `http://localhost:9090` is set, and NMAS's client counts 9 devices. The class goes to the 7.2 status bar [6ef9d8c].
- **gRPC and Interface down.** The operator's fixes read Normal [6ef9d8c].
- **C168.** Scheduled into **P.7**, decided 2026-09-28 and placed before 8.6 [4997141]. P.7 requires:
  - a generator per rule kind;
  - the expected set of members taken from the inventory;
  - one definition of "which device";
  - each rule shown able to cross its threshold on real data;
  - history read uncapped;
  - an expected alert rate per rule.

  Retire now names the scrape targets still polling a device it releases [6ff6fd0].
- **Also fixed.** The register-hygiene gap [796f2f7] and C169 [d99a260]. CLAUDE.md gained "A claim about ALL TIME needs a window that covers all time" [4997141; d99a260].

**5. Numbers**

- **Commits.** Selection rule: a subject naming C165–C168 or the P.7 decision. That gives 9 commits on 2026-09-28 (-0600), 05a0ccf (13:04) to 4ec7ffb (15:07): 05a0ccf, 99ff600, 5bb1cd7, 796f2f7, 22cf328, 4997141, 6ef9d8c, d99a260 and 4ec7ffb. The edge is ambiguous: 6991b32 (7.2 step 14) applies these rules in the reader, and 6ff6fd0 is 7.3 work; both are excluded.
- **Elapsed time.** 2 h 2 min 42 s in total. C166 was closed at 55 min [commit dates].
- **Findings.** C165–C168, plus C169 and the hygiene gap outside the scope.
- **Measurements.**
  - Syslog, 24 h: 3,155 lines, of which 1 was severity 2, 10 severity 3, 304 severity 4 and 2,828 severity 5; 0 contained "CRIT" in any case. 126 lines arrived in the last hour [OPEN_FINDINGS C166].
  - `host=nmas` on 3,151 of 3,151 lines [22cf328].
  - **Entered Alerting in 30 days, from the uncapped read** [d99a260]:

    | Rule | Alerts |
    |---|---|
    | `Device unreachable (SNMP)` | 38 |
    | `Interface output discards` | 229 in 2,305 transitions (the capped read showed 10) |
    | `Critical syslog received` | 9 |
    | `Interface down` | 6 |
    | `IP SLA probe failing` | 3 |
    | `gRPC telemetry stream lost` | 0 |
    | `Interface error rate elevated` | 0 |

  - gRPC: telemetry sources fell from 4 to 2 in 7 days, with 5 `Normal (MissingSeries)` recorded. It missed two incidents: 09-22 23:41 (about 20 minutes with every source silent) and 09-28 08:51–09:01 (r1 and r3) [OPEN_FINDINGS C168].
  - IP SLA: 73 failing runs in 7 days, across six probes [C168].
  - Nine polled addresses, of which eight resolve to devices [4ec7ffb].

**6. Where it left the product**

Three rules are fixed by the operator's hand. The requirement that a rule is verified by showing it can fire, not by showing it evaluates, is written into P.7, which is decided and not yet built.


#### Sources read (store hardening, the Grafana audit)
- `docs/OPEN_FINDINGS.md`: the preamble (the stopping rule); rows C7, C20, C21, C28, C156–C163, C165–C169.
- `CLAUDE.md`: the settings and store sections, filestore, "A SURVEY SCOPED BY FORMAT", "A lock's re-entrancy", "A claim about ALL TIME", and the test-table entries.
- `docs/NSOT_PLAN.md`: P.7.
- `docs/NSOT_WRITEUP_NOTES.md`: "The Access values were never set…", "An empty allowlist trusted everyone", "The long fuse".
- `git show` for these commits: cd0696e, 4f8a0f1, a25bdba, 2a121ef, ca52ac1, b1fa4b0, f7a237f, 3a946bb, 2449206, 71ed99e, 05a0ccf, 99ff600, 5bb1cd7, 796f2f7, 22cf328, 4997141, 6ef9d8c, d99a260, 4ec7ffb, 6991b32, 6ff6fd0.
- `git log --grep` for each ID, and `git log` of `modules/filestore.py` and the store-integrity test files. Test counts from `grep -c "def test_"`.

#### Could not recover (store hardening, the Grafana audit)
- **The date and time zone of the erasure's last settings write ("20:25:37").** The sources give the time only; CLAUDE.md calls it "the 2026-09-23 erasure".
- **Which writer truncated the settings file.** The chain was reconstructed from code and mtimes; no log of that write exists.
- **When and by what the hand-built Grafana rules were created.** They came from "earlier lab work", outside this repository.
- **The exact gRPC and Interface down expressions the operator applied.** They were edited in Grafana, and the commits record only that both read Normal.
- **Transition totals for rules other than `Interface output discards`.** They were not recorded.

### Side campaign — The verify family: the deploy's safety check, wrong in ten ways

*Backfilled 2026-09-29.*

**1. What it was**

Verify is the pipeline stage that decides whether a deploy or restore is rolled back. Over about two days it was found to pass, or to report a check it never made, in ten independent ways: C62, C64, C65, C66, C67, C68, C108, C114, C115 and C178 [OPEN_FINDINGS C178 row; NSOT_WRITEUP_NOTES "ten independent ways"]. None was found by reading the code for correctness. Each came from asking the same code a new question [f1277c5]. The rollback outcomes (C112) were fixed in the same campaign.

**2. How it was done**

- **Real captures.** A read-only probe on the NMAS host captured `show` output from r3, r1, s1 and s3. It ran from a `git archive` copy at `eecc900`, with bytecode off, through the pipeline's own reader, and redacted everything before it left the host [tests/fixtures/operational/README.md; fe61c33]. Each defect first got a strict expected-failure test built from a capture, checked with `--runxfail` to confirm it failed on its own assertion [fe61c33]. The fix commit removed the markers [a8019b4].
- **The rule.** "A parser's test is built from files in this directory, never from a sample typed into the test" [README]. A second sweep covered the other parsers (topology, NetBox cables) with 28 more captures, and the probe became a tool, `scripts/nmas-capture-output` [b2924e3].
- **Other questions.** A real restore (C70's re-run) found C108. The operator's questions "what counts as failure" and "what if the rollback fails" found C114, C115 and C112, and C114 was demonstrated through `_stage_verify` with the deploy path's own parameters [OPEN_FINDINGS C114]. Designing the rollback acceptance run (C117) found C178 [bc67b4f].
- **Controls.** Every fix carried mutation controls, each restored from a copy [a8019b4, d214f24, 224bb8f, 2abf4b7].

**3. Issues encountered**

- **C62**: verify read only the first routing protocol it found. Real coverage was 4 of 9 devices, vacuous on r3, r4, s1 and s2, and not applicable on r6 [fe61c33].
- **C64**: the BGP pattern expected eight fields, but IOS prints ten, so it counted nothing in either state. r3, r4 and r5 read bgp 0->0 in every recorded deploy [fe61c33].
- **C65**: RIP read the empty table of the `"application"` pseudo-protocol that both platforms print first [C65 row].
- **C66**: route retention read the Networks column (4 where r3 has 30) [C66 row].
- **C67**: the canary passed on any "up", and Loopback0 is always up [C67 row].
- **C68**: any count above zero counted as "progress", so a permanent partial loss read "not yet converged" and never failed. The C62 fix's own test found it [C68 row].
- **C69** (related): there were two `show ip bgp summary` readers; topology's was right and the deploy's was wrong [b2924e3].
- **C108**: the protocol list came from the BEFORE state. A restore of ` ipv6 ospf 1 area 0` on r2 reported "checked ospf, rip, ripng", without OSPFv3 [C108 row].
- **C112**: a failed rollback was drawn as "rolled back". A device with no pre-change file was recorded nowhere, and a sent undo was never read back [C112 row].
- **C113** (context): no failure in about 20 real verify runs on the host; mostly it could not fail [d214f24].
- **C114**: the neighbour tolerance was 1 (`drop <= 1`). In the demonstration, RIP 1->0 with routes 22->3 passed [C114 row].
- **C115**: `_deploy_one` passed `skip_route_check` on every deploy and restore, while the screen printed "routes 22 -> 22" as if it had compared them [C115 row].
- **C116**: verify checks only for loss, never for the change itself [C116 row].
- **C120**: found while fixing C114. A control's same-size edit survived its restore in bytecode [224bb8f].
- **C178**: `convergence.wait_for` returns at its first passing read, 10 s in, while IOS holds a BGP session for up to its 180 s hold time [C178 row]. The fix commit found it was worse than that: when the first post-push count matched, verify did not wait at all [2abf4b7].

**4. How they were resolved**

- **Fixed 2026-09-27 [a8019b4]:**
  - C62: every protocol is compared, with `checked_protocols` recorded per device.
  - C64: the ten-field row is read, and established sessions are counted apart from configured ones.
  - C65: the RIP section is read.
  - C66: the route count is networks plus subnets.
  - C67: the canary needs a non-loopback interface up/up.
  - C68: progress now means the count ROSE.
- **Fixed 2026-09-27, the rest:**
  - C69: one BGP reader [b2924e3].
  - C108: verify carries the target intent's protocols. A declared protocol still down is not passed and not rolled back [9b39b3a].
  - C112: six named rollback states, with a read-back over a fresh connection [d214f24].
  - C114: tolerance 0, the operator's decision.
  - C115: the route check runs, with a 90 s `routes` settle window (the operator's decision) [224bb8f].
- **Registered and left by decision:** C116 [224bb8f].
- **C178: BUILT 2026-09-29 overnight [2abf4b7].** Verify stamps each device's push time and reads BGP once more no earlier than the configured hold time after the push. A session gone by then, or an unreadable table, fails verify. The stated cost: up to 180 s longer for BGP devices (r3, r4). It is not closed. Two things remain: the operator's `show bgp all neighbors` capture, so the negotiated hold time can replace the configured bound, and C117's real-device loop [C178 row; 2abf4b7 Not-Done].

**5. Numbers**

- **Commits.** Rule: commits whose subject or body registers or fixes C62, C64–C68, C108, C112, C114, C115 or C178. That gives 10: d11955d, fe61c33, a8019b4, 9b39b3a, d214f24, 232d001, 224bb8f, bc67b4f, f1277c5, 2abf4b7 [git log --grep]. b2924e3 (C69, the one BGP reader) would make 11. Not counted: three commits that only added captures during other work (9f49a33, dc14f3b, 2083313), and commits that merely mention an ID (e.g. 5039740).
- **Elapsed.** From d11955d (2026-09-27 07:17:17) to 2abf4b7 (2026-09-29 01:34:55): about 42 h 18 min [git].
- **Findings.** 10 verify defects (above), plus C112, C69, C113, C116 and C120 found along the way.
- **Captures.** 81 capture files plus a README at HEAD [ls], added by five commits (24, 28, 24, 4, 2 added files; the first 24 may include the README).
- **Suite.** 4509 passed with 6 expected failures at fe61c33, then 4521 at a8019b4, and 5757 at 2abf4b7 [commit messages].
- **Controls fired.** Six at a8019b4 [a8019b4], and three at 2abf4b7 [2abf4b7].

**6. Where it left the product**

Verify now reads every declared protocol from real-shaped output. It waits out neighbour losses and route shrinks, and it says what each rollback achieved. Its last known gap, the BGP hold time, is built and still awaits confirmation on a real device.

### Side campaign — Mode B's probe: measuring which removals are safe

*Backfilled 2026-09-29.*

**1. What it was**

Mode B (removing a line the device has and intent lacks) was gated so that a line is removed only where `scripts/nmas-removal-probe` MEASURED, on the device's platform, that `no <line>` removes exactly that line. The operator's words: "ask the platform rather than reason about it" [cbeccc9]. The campaign built the probe, ran it on s4 (cisco_ios) and r3 (cisco_iosxe), and wrote `modules/nsot/removal_measured.json`.

**2. How it was done**

- For each shape in `removal.SHAPES`, the probe:
  - adds a scratch instance (`NMASPROBE` names, RFC 5737 addresses, Loopback199);
  - sends exactly what Mode B would send;
  - classifies the read-backs as exact, broader, different, incomplete or refused;
  - removes the scratch and puts back anything lost;
  - requires the device to be EQUIVALENT to its state before, or stops with NOT RESTORED as its first line.
- It changes only the running config, never saves, holds the device, and runs dry by default [cbeccc9].
- The operator ran it and shared the output files (`/dev/shm/removal-*.json` on the host). Records were merged from the probe's own output [6abe7e9, 5bd8230, 6ebc3e9, d9659d4].
- The gate is an allowlist. Until the first run, nothing was removable [cbeccc9].

**3. Issues encountered**

- **Dry run, C192.** The dry run printed `router bgp 65000`. At `--apply` the probe would have added a neighbour to r3's LIVE AS 65001 process, the one peering with r5. A device with no BGP recorded `failed`, a fact about the run posing as a fact about IOS [C192 row].
- **s4, first run.** The probe stopped with NOT RESTORED after `global.logging-buffered`. Removing `logging buffered 16001` left `no logging buffered`, so buffered logging was OFF, not at its default [6abe7e9].
- **C193.** The probe's repair used the residue calculation, whose setting key reduced `no logging buffered` and s4's own `no logging console` both to `logging`. The same key blinded Mode B's candidate list, the previews' "will NOT be removed" list and rollback's previous-value lookup [C193 row].
- **s4, second run.** `access-list 97 permit 192.0.2.1` removal also removed `permit 192.0.2.2` (broader). The route-map sequence, applet, prefix-list and named-ACL shapes were exact [5bd8230].
- **C194.** The probe did not record whether its repair sent anything. "No repair needed" was read from s4's second run and written in 5bd8230's message; neither was in the output [C194 row; b066324].
- **r3, first run, C195.** Both ACL shapes "did not land":
  - `plan_for()` dropped the read-back matching;
  - IOS-XE displays a numbered ACL as `ip access-list standard 97` / ` 10 permit X`.
  - The operator's point: in that form a numbered entry would have been classified as `named-acl.entry` and borrowed its safe measurement [C195 row].
- **C196.** One removal, two forms, two answers. The top-level form on IOS deleted the list, and the list form on IOS-XE removed one entry [C196 row].
- Found beside them: C200 (a rollback of a pushed `no` line can send `no no <line>`) and C201 (positive keys that share a keyword) [602f962]. C191 (the device-writer scan missed scripts) was registered when the probe passed the suite unnoticed [cbeccc9].

**4. How they were resolved**

- **C192: fixed before the run [ddf7713].** The live BGP shape runs only with `--allow-live-bgp`. A shape the run could not ask about is `unmeasured` and never enters the record, and neither does `failed`. A shape reads `exact` only if every example did. BGP stayed unmeasured by choice on both platforms [6ebc3e9, d9659d4].
- **logging buffered: classified `overrides_default` and retired from the probe, refused by name [6abe7e9].** s4 was restored without a reload by reading the default from s3, a sibling on the same image: `logging buffered 8192 debugging` [1964f7d].
- **C193:** the probe's repair was switched to a plain difference of the read-backs the same night [6abe7e9]. The key itself was FIXED 2026-09-29 [602f962]: a `no` form is keyed on its whole remainder and pairs with a unique positive by prefix, across all three consumers.
- **C194 and C195: fixed together [6ebc3e9].**
  - Each example records its restore.
  - The locator finds the displayed form.
  - `numbered-acl.list-entry` is its own shape.
  - Results are filed under the shape the device displays (`shown_as`).
  - A re-run proved no repair was needed [d9659d4].
- **C196: left refused.** Nothing needs it, and sending an undisplayed form would break the verbatim rule. It is UNKNOWN pending an IOS list-form exemplar [C196 row].
- **C200 and C201:** registered, not fixed, under the stopping rule [602f962].

**5. Numbers**

- **Commits.** Rule: path history of the probe and the record, plus `--grep` for the probe and C192–C196. That gives 11: cbeccc9, ddf7713, 6abe7e9, 319b593, 1964f7d, 5bd8230, b066324, d4ccd0a, 6ebc3e9, d9659d4, 602f962 [git].
- **Elapsed.** cbeccc9 (2026-09-28 20:53:57) to d9659d4 (23:13:52) is 2 h 20 min. Including the C193 key fix, 602f962 (2026-09-29 01:28:43), it is 4 h 35 min [git].
- **Runs.** Four device runs recorded: s4 twice and r3 twice [the four merge commits]. The dry run was also seen before r3 [C192 row].
- **Measurements** [removal_measured.json]:
  - **cisco_ios:** 8 exact (load-interval, description, snmp-server community, logging host, route-map sequence, applet, prefix-list entry, named-ACL entry), 1 broader (numbered ACL entry), 1 `overrides_default` (logging buffered).
  - **cisco_iosxe:** 9 exact: the same seven non-ACL shapes (load-interval, description, snmp-server community, logging host, route-map sequence, applet, prefix-list entry), plus the named-ACL entry and `numbered-acl.list-entry`. The top-level numbered form is recorded unmeasured with its reason (IOS-XE never displays it). BGP is unmeasured on both.
  - `removal.SHAPES` holds 11 shapes at HEAD [read-only import].
  - The snmp community was measured exact on IOS from three examples: plain, with an ACL, and with a view [6abe7e9].
- **Findings.** C191, C192, C193, C194, C195, C196, C200 and C201.
- **Suite.** 5616 passed at cbeccc9, then 5640 at d9659d4, and 5745 at 602f962 [commit messages].
- **Rules recorded in CLAUDE.md** [319b593, d4ccd0a]:
  - "Refusing by resemblance is safe; allowing by resemblance is not."
  - "A probe that continues past a failed restore measures its own damage."
  - "A clean result cannot prove a mechanism that was not exercised."

**6. Where it left the product**

Mode B can remove a line only in a shape measured exact on that platform. That unlocked r2's ` no load-interval 30` [6ebc3e9], and the numbered ACL entry that an unmeasured Mode B would have destroyed on IOS is refused by measurement.

#### Sources read (the verify family, Mode B's probe)
- `docs/OPEN_FINDINGS.md`: rows C62, C64–C68, C108, C112, C113, C114, C115, C116, C117, C178, C192–C196, C200, C201
- `docs/NSOT_WRITEUP_NOTES.md`: "The deploy's safety check was wrong in ten independent ways", "The line the tool could not remove"
- `docs/NSOT_STAGE7_PLAN.md`: Mode B's measured-gate and probe paragraphs (around lines 1750–1800 and 1920–1935)
- `CLAUDE.md` (in context): the verify, probe and resemblance rules
- `tests/fixtures/operational/README.md` and a listing of the directory
- `modules/nsot/removal_measured.json`; `removal.SHAPES`, via a read-only import (no bytecode written, checked)
- `git log` and `git show` for the 21 commits cited

#### Could not recover (the verify family, Mode B's probe)
- The exact number of verify runs before and after the fixes on the host: only C113's "about 20" is recorded. The run history lived in a rotating log and in per-device audit files that each run overwrites [d214f24].
- The date and time of the probe's dry run, and whether one was run on s4: the dry-run output is not committed; only C192's row records that the operator read it before r3.
- Whether s4's second run needed any repair past its teardowns: the probe did not record it then (C194). That is the point of the finding.
- C178's real-device outcome: it is awaiting the operator's capture and C117's run, so no result exists yet.
- Whether the first capture commit's 24 added files include the README: this was not separated, so "81 captures plus README" is taken from the directory at HEAD.

## Part IV. Across the stages

Collected from what the project already records, with citations in brackets. "CLAUDE.md" means its "Things to Keep in Mind" unless another section is named; "NOTES" is NSOT_WRITEUP_NOTES.md, "S7" NSOT_STAGE7_PLAN.md, "PLAN" NSOT_PLAN.md; register rows are cited by ID. *Backfilled 2026-09-29; kept current as stages close.*

### Patterns

#### 1. The proxy population

**Pattern.** A check's population is defined by something that usually
coincides with the property, not by the property itself, so it stops covering
the property when the proxy moves [docs/LESSONS.md#populations-by-property "A GATE TABLE KEYED ON HTTP METHOD
MISSES A GET THAT CHANGES A DEVICE"].

**Instances, in order** (the operator's list, 2026-09-26, extended since):
- The drift checker enumerated the legacy golden store, not the inventory
  (Phase 3.3, fixed 2026-09-23) [docs/LESSONS.md#populations-by-property "The drift check's population is the
  inventory"].
- The NetBox census compared identity (`id:display`), not assignment, so a
  moved address read as unchanged [CLAUDE.md, same list].
- Approval scheme 2 keyed on the bound device set, not the template (D11).
- The restore preview iterated the ref, not the inventory (C23, fixed by P.3
  step 5, 2026-09-26).
- The gate table was keyed on HTTP method, not on reaching a device (B16,
  2026-09-26).
- The agent's "read-only" tools meant "not config mode", not "cannot change
  anything" (P.3 step 8, the operator's sixth).
- B11's "no GET returns a secret" planted secrets only in stores it knew (C55,
  C56, 2026-09-27).
- C77: the same leak class in POSTs, missed because B11's population was GETs
  (2026-09-27).
- C121: "the false-green class is zero" was true of the list, false of the
  tool (2026-09-27).
- "The tool knows every change by construction" (8.7, 2026-09-27): changes
  through the tool standing in for changes to the device.
- The first store-hardening sweep listed JSON loaders and missed devices.csv
  (C160, 2026-09-28) [docs/LESSONS.md#the-sweep-stopping-rule "A SURVEY SCOPED BY FORMAT FINDS WHAT SHARES
  THE FORMAT"].

**Corollary** (the operator's): a proxy population is a dependency on
something staying true that nobody is watching.

**Mechanical answers.** One gate table, checked both ways with floors
(`modules/route_gates.py`, `tests/test_route_gates.py`); the GET and POST
secret sweeps with stores tied to the storage checker's secret classes
(`test_no_get_returns_a_stored_secret.py`,
`test_no_post_returns_a_stored_secret.py`); an allowlist for read-only
commands (`modules/readonly_commands.py`, C61); the drift population test
(`test_drift_population.py`); a declared-green toast scan
(`test_results_are_drawn.py`). The general rule: "Constrain the shape; do not
only enumerate the instances" [CLAUDE.md, the operator's naming, 2026-09-27].

#### 2. The verify family

**Pattern.** The deploy's verify, which decides rollback, passed or reported
a check it never made, ten separate ways [NOTES "The deploy's safety check
was wrong in ten independent ways"].

**Instances:** C62, C64, C65, C66, C67, C68, C108, C114, C115 and C178, each
with its cause and fix in the side campaign's entry ("The verify family:
the deploy's safety check, wrong in ten ways"), which is where they are
described; they are not repeated here. Measured effect before the fixes: on
eleven recorded deploys the routing check was real on four devices and
compared 0 with 0 on four [NOTES "The deploy's verify, against real
output"]. None was found by reading the code; each came from asking the same
code a new question. A sibling: two BGP summary readers, topology's right and
the deploy's wrong (C69).

**Mechanical answers.** Real captures in `tests/fixtures/operational/`;
`tests/test_pipeline_reads_real_output.py`, with strict expected failures
confirmed by `--runxfail`; one BGP reader, pinned by AST
(`test_other_readers_real_output.py`). Rule: "A CHECK THAT ACCEPTS THE FIRST
HEALTHY READING MUST WAIT OUT THE SUBJECT'S OWN SETTLING TIME" [CLAUDE.md,
C178].

#### 3. A check satisfied by something other than its property

Also named the vacuous pass and the control that passes.

**Pattern.** "A TEST THAT PASSES IN BOTH CASES SHOWS NOTHING" [CLAUDE.md, B9];
its inverse, "a gate that always REFUSES is the same defect as one that always
passes" [CLAUDE.md, P.4 step 4].

**Instances, in order:**
- "Real checks positioned where they cannot fail", six numbered:
  `assert_no_negation` returned `None`; approval validated a different
  template directory; `assert_merge_only` compared `intended` with itself;
  rollback's two conditions; `_restore_config` as a merge;
  `assert_rollback_provenance` saw only `no` lines [NOTES "A family of its
  own"].
- Four controls that could not fail, in Stage 2 (a dry run returning before
  the chain; an `ssh` failing at key exchange printing PASS; a count
  matching a comment; a marker substring) [NOTES "Four controls that could not
  fail, in one stage"].
- A hand-rolled harness in 4C.8 that silently skipped tests; the first genuine
  run was 2,638 passed and 6 failed [NOTES "The harness that could not tell
  'passed' from 'never ran'"].
- B9 (2026-09-26): `rclone delete` exited 0 without touching the file.
- `nmas-deploy --offline` could not pass on any commit, and its red result was
  read as the acceptance (P.4, 2026-09-26) [CLAUDE.md].
- C110 (2026-09-27): "no commit carries `Source: restore`" could not have come
  out otherwise; C111 the second half.
- The integration status "never probes" control passed on the error handling
  (2026-09-28) [docs/LESSONS.md#every-check-shown-able-to-fail "A CONTROL THAT WORKS BY BREAKING SOMETHING MUST
  CHECK THE BREAK WAS OBSERVED"].
- C120 (2026-09-27): a control's mutation survived in bytecode.
- C194 (2026-09-28/29): the removal probe did not record whether its repair
  ran [docs/LESSONS.md#every-check-shown-able-to-fail "A clean result cannot prove a mechanism that was not
  exercised"].
- A check whose NAME claims more than its code (2026-09-28): the daily
  restore test decrypts nothing, and its pass was read as proof the encrypted
  copies can be read (C144); `nmas-breakglass verify` proved the record opens
  and was claimed to settle whether it was current (C182); a backup key's
  export matched by hash on both hosts and could not be imported (B8)
  [docs/LESSONS.md#confirm-the-result "A CHECK THAT THE ARTEFACT ARRIVED CANNOT SEE WHETHER IT WORKS
  THERE"].
- C221 (2026-09-29): the break-glass row read "current" because an export
  was WRITTEN; the file had been deleted before it reached anywhere.

**Mechanical answers.** Floors on every scan (`_the_scan_finds_something`)
[docs/LESSONS.md#floors-and-independent-controls "An assertion over a set difference passes vacuously"]; about 180
built-in controls in 72 files, run every time, and about 330 one-off mutation
controls [TESTING.md "Negative controls"]; restore a mutation from a copy,
never git; `PYTHONDONTWRITEBYTECODE=1` in `scripts/nmas-test` (C120); a
control is valid only when the aimed tests fail, not by crashing [CLAUDE.md].

#### 4. Absent versus unreadable

**Pattern.** A reader that turns an unreadable store into an empty one lets
the next write persist the emptiness [docs/LESSONS.md#subsets-and-distinct-states "Absent and unreadable are
different facts, and collapsing them erased the settings file"].

**Instances:**
- The settings erasure, 2026-09-23: truncate in place, `{}` on unreadable,
  107 defaults reseeded, Cloudflare Access config blanked [docs/LESSONS.md#many-people-tabs-and-processes "Five
  defensible mechanisms composed into an invisible failure"].
- The NetBox modification record would have been erased the same way;
  "Absent and unreadable are different facts, for the third time in this
  project" [CLAUDE.md, §21].
- `/onboard/pending` must answer `ok: false`, not an empty list [docs/LESSONS.md#subsets-and-distinct-states "A
  banner that renders 'none pending' because the query FAILED"].
- C130 (2026-09-28): a failed NetBox read treated as "gone", so a preview
  forgot provenance.
- C157 (2026-09-28): the credential store.
- C158 (2026-09-28): the created-object record and `rolled_back.json`.
- C172 (open): `remote.json` unreadable read as no remote.

**Mechanical answers.** `SettingsUnreadable`; `.corrupt-<ts>` preserved;
`read_json_for_write` refuses (`modules/filestore.py`, C158); `_nb_read_by_id`
answers `ok`, `gone` or `unreadable` (C130).

#### 5. The store-hardening family

**Pattern.** A store the program read-modify-writes without a cross-process
lock, a per-write temp file and a refusal on unreadable can lose data or
lift a guard [CLAUDE.md `modules/filestore.py`].

**Instances:**
- C20 (2026-09-25): settings; a shared temp name and no lock left the file
  unreadable in 2 of 2 runs. It was introduced by `4f8a0f1`, the fix for the
  erasure [docs/ARCHITECTURE.md "Every read-modify-write of `user_settings.json` holds
  `config.settings_lock()`"].
- C157 (2026-09-28): the credential store had the three erasure ingredients;
  without the flock, 37 to 47% of writes were lost [CLAUDE.md, `test_
  credential_store_integrity.py` row].
- C158 (2026-09-28): the NetBox created-object record and `rolled_back.json`.
- C160 (2026-09-28): devices.csv, truncated in place, five paths with no lock;
  found only by listing all 85 write sites.
- C161: found inside C160's fix and left, the stopping rule's first
  application [OPEN_FINDINGS "The stopping rule for a sweep"].
- C213 (2026-09-29): the retry log, the audit of every decision to re-send a
  failed change, read an unreadable file as empty and wrote back by
  truncating in place; fixed when revert and retry reached the Device page.
- C159 (open, Stage 9): the approval queue saves on every read, the likely
  mechanism of a transient Needs attention row whose cause was not logged.

**Mechanical answers.** `PathLock`, `write_atomic`, `read_json_for_write`;
`test_settings_concurrency.py`, `test_credential_store_integrity.py`,
`test_store_integrity_c158_c160.py`. A side finding: re-entrancy belongs to
the path locked, not the lock object (C158) [CLAUDE.md].

#### 6. A fixture that cannot exhibit the case

**Pattern.** The assertions are exact, and the input can never reach them
[docs/LESSONS.md#fixtures-that-reach-the-case "A FIXTURE THAT CANNOT EXHIBIT THE CASE — a third variety"].

**Instances:**
- `TestMergeCommands.RUNNING` held every container, so the duplicate stanza
  header was unreachable (branch site, 2026-09-24).
- `FakeNetBox` had no foreign keys, so it could not cascade.
- `SourceFileLoader` hides a definition below the `__main__` guard.
- `nmas-seed-status`: tests used absolute paths, the host a relative one (C6).
- C64, C65 (2026-09-27): BGP and RIP samples typed from memory.
- The `/deploy/apply` payload provider only produced a refusal; the undrawn
  list rose 99 to 106 once it produced a deployed row [docs/LESSONS.md#fixtures-that-reach-the-case "A CHECK IS
  ONLY AS GOOD AS THE STATE ITS FIXTURE CAN REACH"].
- C72 (2026-09-27): fourteen empty record collections.
- C96 and C85: fixtures that never reached a drift run or a stored import.
- M4 (2026-09-27): tests built an AF_INET socket; systemd hands over a
  dual-stack IPv6 one.
- 7.1 step 5: a fixture that could not DISTINGUISH two states, r2's password
  equalling its account name [docs/LESSONS.md#fixtures-that-reach-the-case "A fixture can fail to DISTINGUISH
  two states"].

**Mechanical answers.** Parser tests from captures only; `EMPTY_IN_FIXTURE`
with a ceiling (C72); "build a renderer's test input from the route"; real
pieces allowed in a constructed arrangement [docs/LESSONS.md#fixtures-that-reach-the-case "A fixture sometimes
has to build a state the live fleet does not currently offer"].

#### 7. A gate keyed on something that moves for unrelated reasons

**Pattern.** The gate's key changes for reasons that are not the gate's
business, so it revokes or refuses what nobody changed [CLAUDE.md "A GATE
KEYED ON SOMETHING THAT MOVES..."].

**Instances:**
1. Phase 3c: gating deployability on intent drift (caught in design).
2. Approval scheme 1 hashed host_vars, so a deploy revoked its own approval.
3. Scheme 2 keyed on the bound device set, so onboarding revoked a platform's
   approval (D11, D2).
4. `not_already_type_9` refused every rotation after Stage 2 (B13,
   2026-09-26), found while a credential was exposed.

A related case: the onboarding approval gate that no first device could
satisfy (4C.8) [docs/LESSONS.md#populations-by-property "Template approval is an ADVISORY on the onboarding
path"].

**Mechanical answers.** Scheme 3: the template closure hash, per-device
fidelity in `blocking_reasons` (P.5, built 2026-09-26) [PLAN P.5]. The
signature to watch: "something was revoked, or refused, that nobody had
changed".

#### 8. Computed, carried, drawn nowhere

**Pattern.** The server computes a value, the payload carries it, and nothing
draws it [docs/LESSONS.md#a-stated-problem-is-a-hypothesis "The edge caches HTML and not JSON"; "four defects of the
shape" in one night].

**Instances:**
- The drift scheduler wrote `next_ts`, which nothing read (the "`next_ts`
  shape").
- The agent panel's three client guards (Phase 3.3).
- `loadOnboardPending` had no caller outside its own banner (4C).
- The DHCP review branch (Phase 2 DHCP, "for the fifth time").
- C85 (2026-09-27): the NetBox import's C8 fields in the stored summary,
  drawn nowhere.
- C96: the drift panel drew none of its last run.
- C138 (2026-09-28): drawn but unreadable (light text on near-white).

C138 marks the stated limit of the mechanised checks [OPEN_FINDINGS C138;
TESTING.md "What is NOT tested"].

**Mechanical answers.** Executing the shipped JavaScript in duktape against
real payloads (`test_agent_panel_renders.py`); `test_payload_is_rendered.py`
(7.0 (3)); `test_results_are_drawn.py` (7.1 step 1).

#### 9. "Success" meaning no exception reached the top

**Pattern.** `ok` or `success` recorded that the code did not crash, not that
the work happened [docs/NSOT_PLAN.md "'Success' must mean something happened"].

**Instances, as counted by CLAUDE.md:**
1. The background agent: 27 runs, zero tool calls, one `success: true` with
   nothing in it.
2. `bind_credentials_step`.
3. `_sync_list_to_netbox_impl` (`ok` with every device in `failed`).
4. The sanitiser's exit code.
5. Kea's envelope, `ok: True` around `{"result": 1}` ("Fifth instance").

The colour form arrived later: green on a partial success (C85, C121, Save
All, onboarding Create) [CLAUDE.md "Colour is part of the result"].

The exit-code cousin: "An exit code that cannot distinguish the case it is
used to check proves nothing about it", three instances (`rclone delete`,
`rclone copy`, systemd `Result=success` for a missing unit) [CLAUDE.md].

**Mechanical answers.** An agent run's `outcome` of `ok` / `failed` /
`interrupted` / `inconclusive`; Kea's `ok` decided from Kea's per-service
result; `FALSE_GREEN` and `GREEN_TOASTS` in `test_results_are_drawn.py`.

#### 10. A rule keyed on the platform when it was about the deployment

**Pattern.** A rule true of every device that existed when it was written
fails for the first device that arrives by another route [docs/LESSONS.md#nothing-lab-specific-in-the-product "A RULE
KEYED ON THE PLATFORM WHEN IT WAS REALLY ABOUT THE DEPLOYMENT", P.6,
2026-09-27].

**Instances:**
- `RESERVED_INTERFACES` refuses Gi1 on `cisco_iosxe`.
- `clab_target_for()` resolves an unknown lab to rcn-lab1 (C50).
- The SSH key was skipped for `cisco_iosxe` (M4).
- `VRNETLAB_INJECTS_USER` gave a ZTP render `password 0` (C52).

ZTP was the first route to break all four [P6_ZTP.md §8].

**Answer.** A search method, not a test: "anywhere the code asks WHAT a
device is to answer HOW it got here", and grep the justifications for
"vrnetlab". C52 is fixed with the form as a deployment property, pinned both
ways. No structural check is recorded.

#### 11. A status claim ahead of the thing it describes

A document or a status says a thing is done, built or scheduled, and the thing it describes is not in that state. Instances: C122 ("onboarding and NetBox Remove retrofitted" meant their results, not their previews, 2026-09-27); D6 (a register row left in Scheduled for three days after P.3 step 2 had removed the route it described, found 2026-09-29); C38 (7.2 declared built without one of its scheduled sources, found 2026-09-29). The two later ones were found by the writeup's backfill reading the scheduled rows against the code, which is what a stage close now does: acceptance item 14 requires the entry, and the entry lists the stage's findings and what became of them, so a scheduled source left unbuilt is named when the stage closes, not days later. The general rule it joins: a document asserting a property the code does not have stops the next person looking [CLAUDE.md].

#### 12. Further named families (brief)

- **Coverage inherited, not designed.** Found by adding one member: drift over
  the legacy store, clab-sync and r6, the sanitiser's hardcoded `ROUTERS`
  list [CLAUDE.md; NOTES "Coverage that was never designed, only
  inherited"].
- **A rule that never reaches what already exists.** Five instances, the
  `.gitignore` top-up the cleanest [NOTES "Five times"]. Answer: rules applied
  on access (`ensure_repo_hygiene()`).
- **Prose about code is not code; a pattern that can appear in English needs
  an anchor.** At least seven instances of a scan matching the text written
  to explain it [NOTES "A named pattern"; CLAUDE.md]. Answer: parse, never
  grep; `check_removed_definitions.py` tells a use from a mention.
- **Matching a name, a prefix or a mention.** C61, C87, C101 (twice), C103, and
  the one-home check keyed on spelling [docs/LESSONS.md#populations-by-property "When a check matches a
  NAME, a PREFIX or a MENTION"].
- **The seam.** "A test that constructs its own subject cannot notice that the
  caller does not", nine instances by Phase 2 DHCP [docs/LESSONS.md#walk-the-path-for-real "Running the
  tool is how defects are found"]. Answer:
  `test_server_reads_nothing_the_form_cannot_send.py`, the entry-point sweep,
  `assert_dialect()`.
- **A silently wrong record from a transformation.** `version 2` stripped both
  sides, an invented `control-plane`, masked validation, the pipeline's
  post-snapshot stage capturing metrics [NOTES "The pattern, now three deep"].
- **A method defect: a test written after the implementation encodes it.**
  Four in one week, on the rolled-back block and its revert [NOTES "Method,
  not code"].
- **Two places answer the same question.** Drift checkers, golden enumerators,
  BGP readers (C64, C69) [docs/LESSONS.md#one-owner-one-home "When two places answer the same question
  about a device"].
- **A preview runs the real code.** C130 and C134 [CLAUDE.md]. Answer:
  `TestNoPreviewWritesTheStore`.
- **The instrument is the variable.** `ugrep` file order (C20), bytecode
  (C120), a 420-character register dump (C106) [docs/LESSONS.md#a-stated-problem-is-a-hypothesis "An investigation's
  instrument can be the variable"].
- **A claim about all time from a short window.** Three instances; the first
  the operator's (2026-09-28), and the third, the same day, the implementation's own [docs/LESSONS.md#truncated-reads-and-whole-records "A claim about ALL TIME
  needs a window that covers all time"].
- **A bound nobody chose, or chosen "to be safe".** A suite wrapper waiting
  1500 s on a 121 s run and a 20 min CI job bound on 224 s jobs (2026-09-28);
  Netmiko's default 10 s connect timeout, set by nothing, below s3's measured
  13.7 s, so a device that was never failing was reported unreadable (C205,
  2026-09-29) [docs/LESSONS.md#bounds-from-measurement "A BOUND CHOSEN 'TO BE SAFE'"]. Answer: a bound is a
  small multiple of a measurement, written beside it, and a bound that fires
  names what was running.
- **A message describing a state that did not occur.** The sixth in one
  session was DHCP's `bootstrap_artifact` [docs/LESSONS.md#refusals-name-both-operands "COMPLETENESS IS JUDGED
  PER SOURCE"].

### Rate measurements

- **Findings per commit, 7.1.** 69 commits over 20 h 41 min (ff6fc24 to
  763649e). The register went from 97 rows to 168: 69 C-rows (C60 to C128) and
  2 E-rows. At least six came from side work. "Roughly one new finding per
  commit". "The rate did not fall as the stage went on." [S7 "The forecast,
  corrected (2026-09-28)"]
- **After 7.1.** R2a and the community branch: 21 commits over 2 h 34 min
  (763649e to 995498a), 14 rows (C129 to C142), "7.1's rate exactly". "The
  rate is a property of the WORK, not of a stage." [S7, same]
- **Findings per day.** 39 new on 2026-09-26, 43 on 2026-09-27; almost every
  one came from building and running [docs/LESSONS.md#writeup-entries-and-forecasts "In this project building is
  how surveying happens"].
- **Estimate against actual.** Measured partway through 7.1: "13 hours and 32
  commits", and the rest of Stage 7 "three to four more efforts that size"
  (about 110 commits). Actual 7.1: 2.2x the commits, 1.6x the hours, so the
  remainder was re-estimated at 200 to 280 commits. The operator's reading: an
  estimate from an unfinished stage is made from the part that went to plan
  [S7, same; CLAUDE.md].
- **7.2 prediction.** Made from the finished 7.1: 40 to 70 commits over about
  a day, 30 to 50 findings, "to be checked when it closes" [S7, same]. Nobody
  checked it when 7.2 closed. **Checked at backfill (2026-09-29)**: 37 commits
  in about 4 h 03 min, about 17 findings (11 new register rows plus six with
  no ID). Only 19 of the 37 were 7.2's own step commits; the rest were
  decisions and measurements made in the same window (see the 7.2 entry).
  **The operator's reading: the correction asked for after 7.1 overcorrected.**
  The rate assumption, about one finding per commit, held for 7.1 and not for
  7.2, because 7.2 read stores that 7.1 and that week's sweeps had already
  hardened. That is a result about where findings come from, not a forecasting
  failure. The prediction held the fact and read it the other way: "four of
  those were found this week in stores 7.2 draws from" was offered as a reason
  to expect findings in the sources [S7 "The forecast, corrected"].
  **An unchecked forecast is the base of the next one**, which is why closing a
  stage now includes checking its forecast against its actuals (acceptance
  item 14).
- **Mode B (7.3 step 2), 2026-09-28 to 29.** Estimated when costed at "about
  three days to build … plan on about a week". Actual, from costing to
  acceptance on the host: about 5.5 hours of continuous work, 15 commits and 7
  findings (C191 to C197), with four real runs by the operator (three probe
  runs and the acceptance) [the 7.3 entry]. The estimate was in days of
  ordinary work and the work was one continuous session, so the two are not
  like for like. **What it means for the method** (the operator, 2026-09-29):
  the "triple it" rule came from 7.1, a stage of unbounded screen work and
  first real runs. Applied to a well-bounded piece of work whose measurement
  campaign was already scoped, it produced a number about seven times too
  high. Forecasting from a finished stage is right; forecasting from a
  DIFFERENT KIND of stage is not.
- **C188 (7.3), 2026-09-29.** About 45 minutes, 3 commits, 2 new rows (C198,
  C199). The host measurement is the result: preview 101 s to 40.9 s, apply
  102 s to 13.7 s [the 7.3 entry].
- **Phase 2 (DHCP) ledger, 2026-09-24.** 9 commits fixed things found by
  running it, carrying 15 distinct defects; the suite caught none of the 15.
  Suite green throughout, 3,276 to 3,360 tests. 9 of 15 were written that
  day, 4 the day before, 1 four days earlier, 1 five months earlier. The suite
  caught three regressions by name while the fixes were made [docs/LESSONS.md#walk-the-path-for-real
  "Running the tool is how defects are found"; docs/PHASE2_DHCP.md §10].
- **Stage 4C probe.** Seven defects live in code the suite passed; the suite
  had "2,700+ tests" [NOTES "What the Stage 4C probe found"].
- **The branch site, 2026-09-24.** "Ten defects surfaced walking the deploy
  path end to end for the first time", suite green throughout [docs/LESSONS.md#walk-the-path-for-real "A
  path that has never carried anything fails on first use"].
- **P.3, 2026-09-26.** Scoped as five items; it found eleven more nobody had
  scoped [NOTES "What P.3 cost and bought"].
- **Verify.** Ten defects in two days (2026-09-27 and 28), none found by
  reading for correctness [NOTES "ten independent ways"].
- **"Three-for-three real runs."** S7 records it: "Three real runs, three sets
  of findings no test could reach (C70, R2a, R1): the rate has not dropped"
  (2026-09-28) [S7 "7.1's stated limit"].
  - **C70**, the restore. The first run found C82, C83, C84; the re-run
    (2026-09-27) found C108, C109, C110; and "the operation correct and its
    surroundings broken: C92, C97, C98, C99" [OPEN_FINDINGS C70].
  - **R2a**, the NetBox previews (2026-09-28). C130, C131, C133, C134, C135;
    25 of 39 import-preview lines were phantom [S7].
  - **R1**, onboarding on a throwaway (2026-09-28). C147, C148, C151, C152,
    C153, C154; closed C57; proved the reboot [S7 "R1's total"].
- **Register size over time** (counted from rows, each as recorded):
  - 59 open at 2026-09-27 [OPEN_FINDINGS "Count"].
  - 92 rows in the open sections before the 2026-09-28 triage, of which 31
    were already done [OPEN_FINDINGS "Triage"].
  - 61 open at 2026-09-28; 26 of 61 open rows were stage work [OPEN_FINDINGS
    rules].
  - 45, then 47 open at 2026-09-29, with 37 to 38 scheduled into stages
    [OPEN_FINDINGS "Count"].
- **Suite size and run time.**
  - Phase 0: 209. Phase 1: 307. Phase 2: 385. Phase 3a: 507 (all 2026-09-20)
    [NOTES Status lines].
  - "1133 tests passed" with a whole function deleted, and "1656 tests"
    parsing no JavaScript; dates Not recorded in those headings [NOTES].
  - 4C.8's first genuine run: 2,638 passed, 6 failed [NOTES].
  - Phase 2 DHCP: 3,276 to 3,360 [CLAUDE.md].
  - P.3, 2026-09-26: 3781 through 3950 passed at `5b087c4` [PLAN P.3].
  - TESTING.md, 2026-09-26: 3,942 tests in 137 files; CI about 4 minutes.
  - P.4 host `--offline`: 4004 passed plus one planted failure in 287.81 s
    [PLAN P.4].
  - 2026-09-28 laptop: 5025 passed, 42 s with `-n auto` on 24 cores against
    121 s serial; CI jobs 186 to 224 s [CLAUDE.md "Tests"].
  - 5344 passed on the tree of `e986e66` [docs/LESSONS.md#gate-results-from-this-run "A CHECK THAT READS A FILE
    SOME EARLIER RUN WROTE"].
  - The first pristine-checkout run gave 5 failures and 19 errors (found
    2026-09-26) [TESTING.md].

### Where the product stood

- **Phase 0, 2026-09-20.** Foundation, portability and safety: NetBox writes
  fail-closed behind a master switch and a one-shot token; no user-facing
  features; 209 tests [NOTES "Phase 0"; git `eac9c5e`, `e7c3e66`].
- **Phase 1, 2026-09-20.** A device list could be sourced from NetBox through
  the single dispatch point, and the GUI read inventory intent from NetBox;
  307 tests [NOTES "Phase 1"; git `d9e868d`].
- **Phase 2, 2026-09-20.** Golden configs lived in a per-list git repository,
  one write path, one call one commit; 385 tests [NOTES "Phase 2"; git
  `4875e67`]. Phase 2b's remote followed on 2026-09-20 and 21 [git
  `651ac82`, `710f7d8`].
- **Phase 3a, 2026-09-20.** Config parsed to host_vars and round-tripped; r1
  92.2% modelled and s1 100%, both 100% fidelity; 507 tests [NOTES "Phase
  3a"]. Later: 100% modelled on all nine under the depth-aware comparison
  [docs/ARCHITECTURE.md "Templatization"].
- **Phase 3b, 2026-09-20.** (No summary was recorded at the time: composed at
  backfill from CLAUDE.md's description and the commit date.) A per-network template library with an approval
  gate and a computed deployability gate; nothing in 3b opened a socket
  [docs/ARCHITECTURE.md "Template library and the deploy gate"; git `6735f97`].
- **Phase 3c, 2026-09-20.** (No summary was recorded at the time: composed at
  backfill, likewise.) Deploy from committed intent, merge-only, confirmed
  by hash: "The only part of the NSoT work that reaches a device" [docs/ARCHITECTURE.md
  "Deploy from template"; git `3be6550`].
- **Stage 2, 2026-09-22.** The rcn-lab1 redeploy ban lifted by a successful
  redeploy [PLAN "STAGE 2 ... COMPLETE"].
- **Stage 3.3, 2026-09-23.** The first scheduled drift run since 2026-08-30:
  9/9 clean against committed goldens [PLAN "STAGE 3.3 COMPLETE"].
- **Stage 4C, 2026-09-23.** "Half-run": the wizard had not yet proved
  end-to-end onboarding or Remove, and had found seven defects [NOTES "What
  the Stage 4C probe found"]. A later clean run proved onboarding end to end
  and left its teardown unprovable; its date is Not recorded [docs/LESSONS.md#absence-as-a-finding "A
  teardown that cannot be measured has not passed"].
- **The branch site, 2026-09-24.** "The first configuration this tool
  AUTHORED": two devices, intent written by hand, previewed, confirmed,
  merge-only, verified [docs/LESSONS.md#walk-the-path-for-real "The branch site landed"; git `8c948bd`].
- **Phase 2 DHCP, 2026-09-24.** Proven: a device the tool never addressed was
  found by its Kea lease, then reached, captured, rotated, cleaned, recorded
  and promoted [docs/LESSONS.md#from-things-to-keep-in-mind "PHASE 2 IS PROVEN"].
- **P.1, 2026-09-25.** Complete: switch syslog restored, nine devices
  heartbeating on per-device measured windows, a silenced s4 alerting alone
  [PLAN "P.1 COMPLETE"].
- **P.2, 2026-09-26.** A NetBox backup with a tested restore, "done except its
  unattended watch" [PLAN "P.2 ACCEPTANCE STATUS"; PLAN "Scope of what
  remains"].
- **P.3, 2026-09-26.** Complete: every device-changing path guarded or gone,
  one gate table, verified actors in commits; 3950 passed at `5b087c4` [PLAN
  "P.3 IS COMPLETE"].
- **P.4, 2026-09-26.** Jenkins removed; CI on GitHub Actions with the host's
  versions; `nmas-deploy` gates on the target commit. Acceptance items 1 to 3
  met; item 4 not yet observed [PLAN P.4 "ACCEPTANCE"].
- **P.5, 2026-09-26.** Built: approval is the template's closure hash and its
  approver; onboarding no longer revokes approvals [PLAN P.5].
- **P.6, 2026-09-27.** Complete: Lab 8 end to end; a configless device got its
  address from a reservation the tool wrote, fetched its config from the tool,
  and survived a reboot; teardown clean [PLAN P.6; P6_ZTP.md §8].
- **7.0, 2026-09-27.** Built, "awaiting the host check": reachability,
  invalidation, payload-to-render and nine-concept checks, each with an
  allowlist that only shrinks [S7 "7.0 built"]. The host check's result is Not
  recorded.
- **7.1, 2026-09-28.** Acceptance met on 5025 passing tests: every operation
  that changes a device or the record has one preview, one confirm, one result
  and one record, none needing a console. Its stated limit closed by R1 and
  R2b the same day [S7 "7.1 acceptance"; "7.1's stated limit"].
- **7.2, 2026-09-28.** "7.2 is built": Needs attention, the reader-job pattern
  (job health, Grafana, freshness, integration health, CI verdict,
  reachability) and the live-data contract [S7 "7.2 step 19"].
- **7.3 so far, 2026-09-28 to 29.** Accepted on the host:
  - Mode B removal (steps 2a to 2c): the acceptance run removed r2's
    `load-interval 30` and earned `baseline/20260929T060249Z`
    [NOTES "The line the tool could not remove"; git `03aeabe`];
  - Save All reading its devices at once, with the preview a job that
    announces its result (C188: preview 101 s to 40.9 s, apply 102 s to
    13.7 s, and a second earned baseline, `baseline/20260929T063600Z`);
  - Persist and Rotate from the Device page, both on r2 by the operator on
    2026-09-29, the rotation recorded as the person who confirmed it
    (`Actor-Verified: access`).

  Built and awaiting a real run: seed intent (step 1), retire, revert and
  retry, and the break-glass export from the browser. Not yet built: adopt,
  seed keeping declared blocks (C216), and the rest of 7.3 [the 7.3 entries;
  S7].

#### Sources read (cross-cutting)

- CLAUDE.md (project instructions, including "Things to Keep in Mind" and
  "Open findings register")
- docs/NSOT_WRITEUP_NOTES.md: phase status lines, the named-family sections,
  and the dated sections from P.3 onward
- docs/NSOT_STAGE7_PLAN.md: 7.0 built, 7.1 acceptance and stated limit, "The
  forecast, corrected", 7.2 steps, 7.3 status, "What does not exist yet"
- docs/NSOT_PLAN.md: Stage 2, Stage 3.3, "Scope of what remains", P.1, P.2
  acceptance status, P.3, P.4 acceptance, P.5, P.6
- docs/OPEN_FINDINGS.md: rules, triage, Count, and the rows cited above
- docs/TESTING.md
- docs/P6_ZTP.md §8
- read-only `git log` for commit dates and hashes
