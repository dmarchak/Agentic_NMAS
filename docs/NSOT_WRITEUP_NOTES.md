# NSoT Write-up Notes

Running record of design decisions, trade-offs, and demo-worthy flows for the
CSCI 5840 Labs 4 & 5 write-up and demo video. Updated at the end of each phase.

Governing spec: [NSOT_PLAN.md](NSOT_PLAN.md).

---

## Phase 0 — Foundation, portability, and safety

**Status:** complete. 209 tests passing (120 pre-existing + 89 new).
**Lab objectives:** none directly — this phase makes Objectives 1.1–1.4
implementable without risking the hand-curated reference NetBox.

### Verification of the plan's current-state findings

Section 3 of the plan listed 11 findings from a review of `main` at `92fcbc8`.
Verified before writing any code: **9 accurate, 2 partly wrong**, plus several
issues the review missed. Worth mentioning in the write-up as an example of
auditing a spec against the code rather than trusting it.

**Partly wrong:**

1. *"`pipeline.py` is only called from `tests/test_pipeline.py`."* True of
   `PipelineRunner`, false of the module — `app.py` imports `_audit_dir`,
   `list_audit_entries`, and `load_audit_entry`, so the pipeline's audit log is
   already surfaced in the UI.
2. *"`_compact_interface` has no IP addresses."* True of the helper in
   isolation, but its only caller `netbox_get_interfaces` attaches
   `ip_addresses` from a separate IPAM query. The IPs already reach stage 1; the
   real defect is narrower — **stage 2 discards them**, reading only
   `["device"]` from the context. The Phase 1 fix is smaller than the plan
   implies.

**Missed by the review, found during verification:**

| Finding | Impact |
|---|---|
| `remove_list_from_netbox` deleted by **site membership**, not by provenance | It would delete any device in the site, NMAS-created or not. No "created by NMAS" record existed to filter on — Phase 0 had to *build* one. |
| The removal cascade was wired into the **delete-device-list route** | Deleting a list in the UI silently deleted the NetBox site, region, VRF and every device in it, with no confirmation. The sharpest edge in the codebase, and unmentioned in the plan. |
| `requests` absent from `requirements.txt` | A clean install per the README crashed on every NetBox path. |
| `pytest tests/` could not collect | No `pytest.ini`/`conftest.py`/`tests/__init__.py`. Only `python -m pytest` from the repo root worked. The plan's required IPv4-literal scanner would have silently collected nothing. |
| NetBox token stored in **plaintext** | The plan states encryption-at-rest as a rule for *new* integrations; it was an *existing* violation needing a migration. |
| `config.py` ran `os.makedirs("C:/TFTP-Root")` **at import time** | On Linux this created a literal `C:` directory in the repo root. It was present in the working tree and not gitignored — one `git add -A` from being committed. |
| IPv4-only regex in `_list_golden_configs` | A device reached over IPv6 mis-parses. Matters because the reference lab is dual-stack. |
| `_ensure_tag` already existed | Good news: `nmas-managed` tagging was a small reuse, not new machinery. |
| Collector ports already configurable | `collector_config.py` already stored `snmp_trap_port` / `netflow_port` per list; only the enable/disable toggles were new. |

The plan's `bat`-step attribution was also wrong: `jenkins_runner.py` contains
none. The actual emitters are `configure.py`, `pipeline_builder.py`,
`config_git.py`, and `ai_assistant.py`.

### Key design decision: keeping the buttons working

The plan (§6) specifies `allow_writes` defaulting to off and the import button
"disabled unless allow writes is on." Implemented with a deliberate deviation,
approved before coding.

**The problem.** A gate that greys out Sync and Remove reads as a broken
feature. The user hunts through Settings to find out why, and the safety
mechanism becomes something to switch off and forget — the worst outcome for a
safety mechanism.

**The observation that resolved it.** *A dry run is read-only.* It issues
nothing but GETs, so it can run with the gate closed. That means the button can
always be clickable, do real work, and produce an accurate preview, while
remaining incapable of writing.

**The flow.**

```
Click "Import to NetBox (discovery)"
  → dry run executes (read-only, always permitted)
  → modal: "Will create 7 devices, 24 interfaces, 12 IPs. Will update 2.
            Will not touch 31 existing objects."
  → [ Enable NetBox writes and import ]  ← flips the gate, then applies
```

One extra click, once. The gate still defaults off and the acceptance criterion
still holds literally — with it off, no write reaches NetBox, asserted by
`test_netbox_write_gate.py`.

**Implementation.** `netbox_guard.dry_run()` is a thread-local context manager.
Inside it the three write chokepoints record the operation they *would* have
performed and return a synthetic object with a negative id, so callers chaining
on `result["id"]` keep working. The sync logic itself is **unmodified** — the
preview is accurate precisely because it is the same code path. Thread-local
rather than global because sync runs on a background thread; there is a test for
that.

**Removal got the opposite treatment.** Its behaviour had to change anyway,
because deleting by `site_id=` is simply wrong. Rather than gating it, the
default became the safe action: delete only what is tagged `nmas-managed` *and*
in NMAS's created-id record, list the objects by name before confirming, and
show what is being left alone. A "just stop tracking" option removes NMAS's
claim without touching NetBox at all.

**Demo-worthy:** point the tool at a NetBox containing hand-made records, click
Remove, and show the modal reporting them as skipped — "not tracked as
NMAS-created, treated as yours."


### Phase 0 follow-up: one-shot authorization (post-review)

Review of the Phase 0 gate raised three questions. Two found real defects — a
good illustration for the write-up that "the tests pass" is not the same as
"the design is right".

**1. The confirmation was persistent, not one-shot.** Confirming an import
called `set_user_setting("netbox_allow_writes", True)`. The checkbox said
"remember this choice", which was at least honest, but it meant the *second*
import needed no confirmation at all. The gate degraded to a one-time
formality — exactly the failure mode the design was supposed to avoid.

The fix separates two concepts that had been conflated:

| | Means | Lifetime |
|---|---|---|
| `netbox_allow_writes` | "this instance may write to NetBox at all" | persistent, set deliberately in Settings |
| Authorization token | "these specific changes are approved" | single use, 5 minutes |

The preview issues a token bound to a SHA-256 of the plan. Execute consumes it,
**recomputes the plan**, and aborts if the hash differs. So approving a preview
of seven devices cannot result in nine being created because someone else
touched NetBox in the meantime.

Details that mattered:
- The hash ignores synthetic placeholder ids (they depend on thread-pool visit
  order) but preserves real ids, so a delete of object 5 is not interchangeable
  with a delete of object 6.
- Entries are sorted before hashing — the plan is built concurrently, so the
  same NetBox state must always produce the same hash.
- A token is burned even when validation fails, so there is no retry loop.
- The master switch is checked **before** the token is consumed, so an
  unauthorized instance cannot waste the operator's approval.

**2. Dry-run fidelity was broken for shared objects.** Asked to confirm that the
preview counts dependent objects, I tested it rather than reasoning about it —
and found a real over-count. Get-or-create helpers issue a real GET, find
nothing (the dry run created nothing), and plan another create. A three-device
import previewed **three** manufacturers, three platforms, and three device
types, and created one of each.

The fix gives the dry-run plan a virtual overlay of what it pretended to create,
which `_nb_get` and `_nb_first` consult. Preview now equals execution exactly,
verified at 1, 3, and 5 devices.

Testing this surfaced a second defect: `_nb_patch` returned a *synthetic* id for
an object that already exists. Callers chain child objects off that id, so
re-importing an unchanged device planned a spurious interface create. A PATCH
path embeds the real id (`dcim/devices/42/`), so the dry run now returns it.

It also produced a pleasing false alarm worth retelling: the first multi-device
test gave all three devices the serial `ABC123`, and the preview collapsed them
into one device. That was the overlay working correctly — `_upsert_device`
matches on serial before name, exactly as NetBox-backed de-duplication should.
The test data was wrong, not the code.

**3. Tag scope was already correct.** `nmas-managed` is injected in `_nb_post`
only, never `_nb_patch`, so an object NMAS updates but did not create stays
untagged and is therefore ineligible for deletion. It now has three tests,
including a structural one asserting that no PATCH payload anywhere carries the
tag — that one will catch a future regression that a behavioural test might miss.

**Demo-worthy addition:** confirm an import, then click confirm again from the
same stale modal. The second attempt is refused with "This confirmation has
expired or was already used", and the UI automatically re-runs the preview.

### Other decisions

**`jsonschema` over `pydantic`.** Settings are plain dicts round-tripped through
`load_user_settings`/`save_user_settings`. A declarative schema layers onto that
with no model layer; pydantic would have meant rewriting every settings access
as typed models or maintaining a parallel shadow of each dict. jsonschema is
also pure Python where pydantic pulls a compiled core.

**Defaults reproduce prior behaviour.** Every one of the 70 new settings defaults
to what the app already did — `bat` steps, collectors on, browser auto-open,
`0.0.0.0:5000`, `NMAS`/`nmas@localhost` git identity. `test_settings_migration.py`
asserts this per key, so the claim is enforced rather than merely intended.
`netbox_allow_writes` is the single deliberate exception.

**Byte-identical pipeline output.** The `bat`→`sh` refactor was verified by
generating pipeline XML from `HEAD`'s `pipeline_builder.py` and from the patched
one and diffing: identical. That is the kind of check worth showing — a
refactor of four call sites proven inert rather than asserted to be.

**Secrets.** `enc:v1:<fernet-token>` prefix, so unprefixed legacy values are
detected and upgraded rather than mis-decrypted. An undecryptable value returns
`""` and logs an error instead of raising: a restored `key.key` must not take
the settings page down.

**Provenance over heuristics.** Identifying NMAS-created objects by tag *and* by
recorded id is deliberately redundant. The tag alone could be added by hand; the
id record alone could go stale against a rebuilt NetBox. Requiring both fails
safe in each direction.

### Trade-offs accepted

- **The created-id record is local state.** A user who imported before Phase 0
  has no record, so Remove will refuse and say so, directing them to NetBox.
  Correct but not frictionless; the alternative (trusting the tag alone) would
  reintroduce the deletion hazard.
- **Dry run costs a full read pass.** A preview of a large list issues the same
  GETs the real sync would. Acceptable for accuracy, and it is the behaviour
  that makes the preview trustworthy.
- **The Integrations panel renders cards from a JS spec** rather than nine
  hand-written HTML blocks. Less consistent with the existing hand-written
  settings markup, far more maintainable at nine tools × ~6 fields.
- **The S3 client depends on `minio`, which is not yet in requirements.txt.** It
  reports "not installed — archive uploads land in Phase 2" rather than failing.
  Adding the dependency before anything uses it seemed worse.

### Demo-worthy flows added

1. **Import preview** — click Import, show the object-by-object preview, point
   out that nothing has been written yet.
2. **Consent in context** — tick "Enable writes", confirm, watch it proceed.
3. **Protective removal** — Remove on a list, showing NMAS-created objects listed
   for deletion and hand-curated ones explicitly skipped.
4. **Integration status strip** — nine badges, all grey, degrading cleanly with
   nothing configured. Configure one, hit Test, watch it go green.
5. **Headless boot** — `NMAS_HEADLESS=1 python app.py` on Linux, no browser, no
   `C:` directory.
6. **The regression test** — run `pytest tests/test_netbox_write_gate.py -v` and
   show `test_removal_without_provenance_deletes_nothing` passing against a mock
   session that raises if any write verb is called.

### Open questions for later phases

- Phase 1 must decide whether a NetBox-sourced device list writes its created-id
  record at all — NetBox owns that inventory, so NMAS arguably creates nothing.
- Phase 2's `save_golden` needs to settle whether a golden commit for a
  NetBox-sourced list records the NetBox device id in the manifest, or resolves
  it at read time.
- The plan asks for `git gc --auto` after commits; worth confirming that it does
  not contend with the per-repo lock under the concurrent-write test Phase 2
  requires.

---

## Phase 1 — NetBox as the source of truth for inventory

**Status:** complete. 307 tests passing (243 + 64 new).
**Lab objective:** groundwork for 1.2a(ii) — the GUI now reads intent from NetBox.

### The design decision that made this phase small

`load_saved_devices()` has **79 call sites across 11 modules**. The obvious
approach — teach each consumer about inventory sources — would have touched bulk
ops, the terminal, backups, drift, topology, the connection pool, the approval
queue and every AI tool.

Instead, one dispatch point. `load_saved_devices(path)` reverses the path to a
list name, checks that list's source, and either reads the CSV or returns
adapted NetBox devices. The other 78 call sites did not change.

What made it work is **shape fidelity**, and the detail that mattered most is
easy to miss: `load_saved_devices` returns rows whose `password` and `secret`
are *still Fernet-encrypted*, because callers decrypt at the point of use. An
adapter returning plaintext would have broken every consumer in a way that only
showed up at SSH time. There is a test asserting the adapter's output decrypts
correctly through the same `decrypt_field` the real code uses.

This is the third time in this project that a single chokepoint has been the
right answer — the NetBox write gate, the dry-run overlay, and now inventory
dispatch. Worth calling out in the write-up as a pattern: **find the one
function everything already goes through, and put the new behaviour there.**

### Amendment: dispatch must never do network I/O

Several of those 79 call sites sit inside request handlers and per-device loops.
A NetBox round trip in dispatch would have put remote latency on every one, and
a NetBox outage would have hung the UI rather than degrading it.

So the work is split:

* **Background refresh** queries NetBox, adapts records, and resolves *and
  encrypts* credentials — once per refresh, not once per call.
* **Dispatch** is a deep copy out of a dict. The copy matters: a caller
  mutating its result must not corrupt the shared cache, and there is a test
  for exactly that.

The persisted cache holds **identity fields only, never credentials**. A restart
during an outage rehydrates the device list from disk and re-resolves
credentials from the local store. So secrets never touch that file, and the
operator still sees their devices — badged stale — instead of an empty list. An
empty list would be the dangerous failure: bulk operations would silently
no-op rather than error.

### Getting the stale-device comparison wrong first

The first implementation persisted the new inventory and *then* compared against
"the previous refresh" — which it read from the file it had just overwritten.
Every refresh compared the new list against itself, so a device could never be
detected as departed. The test caught it immediately; the fix is to capture the
previous IPs before persisting. A good reminder that ordering bugs in
cache-then-compare code are invisible to reading and obvious to testing.

### Stale devices are inert, not deleted

A device vanishing from NetBox — deleted, or just filtered out — never destroys
local artifacts. Golden configs, backups and history stay on disk and stay
browsable. But the device becomes inert: the approval executor, the drift
checker, and the AI device tools all refuse to act on it, and its pooled SSH
session is closed.

The AI-side detail worth demoing: the agent used to be told "device not found",
which sends it hunting for a typo. It is now told the device is no longer in
NetBox, that its configs are still readable, and how to make it active again.
Error messages aimed at an agent need to be as actionable as ones aimed at a
person.

### Credential inheritance, and containing its risk

Credentials come from one **designated** list named in `source.json`, not a scan
of every local list. The risk raised at planning was that coupling the two modes
makes resolution hard to reason about. Three things contain it:

1. Every device records `_cred_source` — `"local-list:Lab Devices"`,
   `"profile:default"`, `"device-override"` — shown in the UI.
2. A device that resolves to no credentials is a **skip with a reason**, not a
   failure inside netmiko ten minutes later.
3. Deleting a designated credential list returns 409 naming the dependent lists,
   and "Copy inherited credentials into device overrides" decouples on demand.

`_from_credential_list` reads the CSV directly rather than going through
dispatch, so a NetBox list can never inherit from another NetBox list and
recurse.

### Partial success is the normal case

The rule throughout: **a device that cannot be represented is skipped with a
per-device reason; the list still loads.** Nine good devices out of ten work,
and the tenth appears in a dismissible banner with a NetBox deep link.

There is a deliberate asymmetry worth explaining in the write-up:

| Missing | Result | Why |
|---|---|---|
| `primary_ip4` | **skip** | Nothing can be done with a device you cannot reach. |
| platform (unmapped) | **skip**, or a warning if `platform_default_netmiko_type` is set | Guessing the netmiko driver risks garbled sessions — but the operator may opt into a guess. |
| credentials | **skip** | Would otherwise fail at SSH time, far from the cause. |
| role (unmapped) | **warning only** | Role only drives a topology icon, and `_infer_role(hostname)` already handles a blank role for local lists. Skipping a perfectly reachable device over an icon would be absurd. |

That last row is the one the amendment sharpened: the test now asserts the role
is a *valid* value rather than merely present, and that a blank role still
yields a usable topology icon.

### The lookup fix

`netbox_get_device` fell back to `q=` fuzzy search and took the first hit. Asking
for "R1" could return "R10", and a template would be rendered against — or
config pushed to — the wrong device. Resolution is now exact name → IPAM
(`address=` → assigned interface → device) → a clear "not found".

The test that matters seeds R1, R10 and R100 and asserts each resolves to
itself, and that a bare "R" resolves to nothing. **Demo-worthy**, because the
failure mode is silent and the consequence is config on the wrong box.

Building it surfaced a nice point about test doubles: the first fake NetBox
rejected `?address=203.0.113.10` against a stored `203.0.113.10/24`, and did not
support `?device_id=` on IP addresses. Real NetBox does both. The fake was
wrong, not the code — a reminder that a mock that is *stricter* than reality
produces false failures just as a lenient one produces false passes.

### Render context

`build_render_context(device_name)` is now the only way a template gets data.
Two defects it closes: the merged `config_context` was never exposed (only
`local_context_data`), and pipeline stage 1 fetched interfaces that stage 2 then
discarded, so templates never saw an interface or an IP address.

`_compact_device` stays lean deliberately — it feeds AI tool payloads where
token size matters. The full records are fetched in the context builder instead.
`netbox` remains an alias for `device` so any template written against the old
signature still renders, and there is a test for that.

### Demo-worthy flows added

1. Point a list at NetBox with a site filter; devices appear with no CSV.
2. Remove a device's primary IP in NetBox, refresh, show the skip banner — and
   that the other devices still work.
3. Delete a device in NetBox; show its golden config still readable while a push
   to it is refused as stale.
4. Ask for "R" and get a clean "not found" instead of R1.
5. Render a template that walks `interfaces` and their `ip_addresses` — data the
   pipeline previously threw away.
6. Delete the designated credential list and show the 409 naming its dependents.

### Open questions for Phase 2

- A NetBox-sourced list's golden commits should probably record the NetBox
  device id in `.nsot/manifest.json`, so history survives a rename in NetBox.
  Phase 2's `git mv`-on-rename story needs to account for renames that originate
  *outside* NMAS.
- Stale devices still have golden configs in the repo. Phase 2 should decide
  whether a baseline tag includes them (arguably yes — the baseline is a
  point-in-time network snapshot).

---

## Phase 2 — Golden config repository and version control

**Status:** complete. 385 tests passing (307 + 78 new).
**Lab objectives:** 1.1 (version control and change management), 1.4 (golden
config saved with timestamp).

### The plan was wrong about the duplicated prefix lists, and that mattered

The spec said six modules carried a duplicated volatile-prefix list and asked
for one consolidated helper. Diffing them first showed they were **four
different jobs**:

| Site | Strips | Job |
|---|---|---|
| drift_check, agent_runner, ai_assistant | 11 prefixes | diff normalisation |
| pipeline | those + `! Pre-change` | it writes pre-change snapshots |
| config_git | **no** `version ` / `upgrade fpd`, plus NMAS headers | repo storage |
| app.py | plus `Last configuration change`, `!`, `end` | **what is safe to send to a device** |

Merging them would have changed drift results — `config_git` deliberately keeps
the IOS version line, because in a *stored* golden config the version is a real
reviewable fact, while in a *diff* it is noise. And the app.py list is not a
volatility filter at all: `end` mid-config silently truncates a startup-config,
so filtering it is a safety guard. Collapsing that into "cleanup" would have
been a genuine regression with a nasty failure mode.

`normalize.py` therefore holds every tuple, named and documented, with a test
that pins each against its pre-consolidation behaviour byte for byte — and one
test asserting the tuples are still *different*, so a future tidy-up that merges
them fails loudly.

**Write-up angle:** "remove the duplication" is usually right, but the first job
is checking whether it *is* duplication. Three of the six were genuinely
identical; the other three only looked it.

### Renames are the interesting problem

Making `git log --follow` survive a rename turned out to depend on a detail
that is easy to get wrong: **a rename must be its own commit**. Git has no
rename records — it infers them by similarity — and a `git mv` bundled with
content edits in the same commit defeats that inference. So `save_golden`
detects a pending rename and emits it as a separate commit immediately before
the content commit.

That interacts with the deferred-rename design. An inventory refresh runs on a
background thread and must never take the repo lock or commit, so it records
`pending_rename` in the manifest and stops. Until the rename is applied, the
golden file is still on disk under the *old* name while NetBox reports the
*new* one — so the manifest resolves **both** names. Without that, a device
would appear to lose its golden config in the window between a refresh and the
next save.

The acceptance test seeds two commits, records a rename, saves again, and
asserts `git log --follow` returns all three plus the rename commit.

### Three bugs the tests caught

1. **Tag collision.** The tag stamp has one-second resolution, so two saves in
   the same second produced the same tag name and the second silently lost its
   tag. Colliding names now take a short-sha suffix. Found because a test did
   six saves in a loop — faster than a human ever would, which is exactly why
   it surfaced.

2. **`git tag --format` does not expand `%x1f`.** That is a `git log` feature.
   The baseline listing was splitting on a separator that had been passed
   through literally, so it always returned an empty list — the feature was
   entirely broken while looking fine in code review.

3. **The migration was not idempotent.** `last_seen` lived in the
   version-controlled manifest and was touched on every call, producing a
   one-line diff and a fresh commit every run. The fix was conceptual rather
   than mechanical: **freshness is runtime state and does not belong in a
   version-controlled file.** It now lives only in the gitignored inventory
   cache.

A fourth was caught by reading rather than testing: `golden_configs_save_all`
gated its Jenkins validation pipeline on `has_staged_changes()`. Now that saves
commit immediately, nothing is ever staged, so that condition is permanently
false — validation pipelines would have silently stopped being created. The
trigger is now "did this save produce a commit".

### Migration: merging duplicates

The same device could exist twice — `R1.cfg` and `r1.cfg`, or two filenames
carrying the same management IP in the header. Migrating naively would have
produced two golden files for one device, and the drift checker would then
report permanent false drift against whichever one it happened to find.

Grouping is by management IP when present (the most reliable identity in the
old format), otherwise by case-folded hostname. The newest content wins, and
**every merge is reported** — both sources, the winner, the timestamps, and
whether content actually differed. Losers are backed up rather than deleted.

A nice detail: on a case-folding filesystem (Windows) `R1.cfg` and `r1.cfg` are
*already* one file, so there is nothing to merge. The report says so rather than
claiming a merge it did not perform.

### Restore is where "stale" actually matters

Baseline tags cover every device inherently — the tagged tree contains every
`golden/*.cfg`, so there was no decision to make there. The decision is at
restore time, and the rule is: **skip stale devices and name them**, in the
confirm dialog *before* anything is queued and again in the result. A partial
restore the operator did not know about is worse than a refused one. Their
golden configs at that baseline stay downloadable — skipping a device from a
restore must not hide its history.

Restore also never pushes. It creates per-device approval items, so the existing
human-review path still applies.

### Demo-worthy flows added

1. Save All across nine devices → **one** commit, nine device tags, one baseline
   tag. Run it again unchanged → no commit at all.
2. Rename a device in NetBox, refresh (no commit), save, then
   `git log --follow golden/<new>.cfg` showing pre-rename history.
3. The migration dry-run report on a repo with a `R1.cfg`/`r1.cfg` duplicate.
4. Restore to a baseline with a stale device, showing it named as skipped.
5. `git show --format=%B HEAD` on a golden commit, showing the trailers.
6. Two `save_golden` calls from two threads, no `.git/index.lock` collision.

### Open questions for Phase 3

- The round-trip validation compares a rendered template against the normalised
  running config. It should reuse `normalize.strip_for_diff`, but Phase 3 also
  wants to strip crypto PKI certificate bodies and build banners — that is a
  fifth filtering job, and the temptation will be to bolt it onto an existing
  tuple. It should be its own.
- `intended/<device>.cfg` lands in Phase 3. Worth deciding whether an intended
  config change alone warrants a commit, or only alongside a golden promotion.

---

## Phase 3a — parsers → host_vars → round-trip validation

**Status:** complete. 507 tests passing (385 + 122 new).
**Lab objective:** 1.3 (templatize existing config), plus the multi-vendor
extra credit via per-platform parser modules.

### The headline number

| Device | Platform | Modeled coverage | Round-trip fidelity |
|---|---|---|---|
| s1 | vIOS-L2, IOS 15.2 | **100.0%** | 100.0% |
| r1 | C8000v, IOS-XE 17.6 | **92.2%** | 100.0% |

Zero missing lines, zero invented lines, zero reordered sections on both. The
12 unmodeled lines on r1 are seven device-unique constructs — `redundancy`,
`subscriber templating`, `call-home`, `memory free low-watermark` — each on one
device, left unmodeled by the agreed rule.

Comfortably past the 80% bar, so 3b proceeds rather than 3a extending.

### Real configs changed the work

Building against the two sanitized fixtures rather than synthetic snippets
caught things I would not have invented:

- **VRRPv3 address-family blocks nest three levels deep.** ``vrrp 10
  address-family ipv4`` has its own indented settings under an interface, which
  is already indented. The first block splitter handled two levels and scattered
  ``priority 110`` / ``address … primary`` / ``exit-vrrp`` into ``unmodeled`` as
  orphans. Modelling it properly took s1 from 87% to 100%.
- **``exit-address-family``** is not decoration — IOS-XE emits it and a config
  without it does not parse on the device. The first VRF parser dropped it.
- **A secret appears twice.** The SNMP community is in ``snmp-server community
  public RO`` *and* inside ``snmp-server host … version 2c public``. Capturing
  only the first left ``public`` sitting in plaintext YAML — a leak that a
  synthetic fixture with one occurrence would never have shown.

### The bug that would have quietly broken every switch

``strip_for_roundtrip`` removes ``version `` because the image version is a
device fact, not intent. But an **indented** ``version 2`` inside ``router rip``
is RIPv2 — core to the lab topology. The filter was eating it.

The failure mode is the nasty kind: the round trip still "passed", because the
line was stripped from *both* sides before comparison. Only a parser test
asserting ``"version 2" in rip["settings"]`` caught it. Version stripping is now
top-level only.

**Write-up angle:** a normalisation step applied to both sides of a comparison
can hide the very thing it destroys. Comparison tests cannot catch that;
extraction tests can.

### The fixed-point test earned its place immediately

``extract → render → extract`` must produce byte-identical YAML. It failed on
the first run and found two asymmetries that every fidelity test was happy with:

1. **Routing blocks kept a redundant ``raw`` list** alongside the split
   ``settings``/``networks``. ``raw`` preserved document order; the template
   emits settings-then-networks. Same config, different YAML, so the model was
   carrying information the template could not reproduce.
2. **``unmodeled`` entries carried ``lineno``** — a pointer into the source
   document. Rendering moves lines, so the second extraction recorded different
   numbers.

Neither affects whether the config round-trips. Both mean the model is not a
faithful representation of intent, which is what 3b's editor will depend on.

### Design decisions worth defending

**Secrets are hashes, and that is not a workaround.** ``enable secret 9 $9$…``
uses a per-hash salt. There is no operation that turns a plaintext password into
*that* hash. So the store holds the hash string and the template emits it
verbatim. A design that stored plaintext would fail those lines on every round
trip forever, and no amount of parser work would fix it. The store records
``secret_kind: hash`` so Part 2's rotation skips them — "rotating" a hash means
asking the device to generate a new one, which is a different operation.

**Ordered by default.** The unordered allowlist has five entries and each has a
reason. BGP neighbors, OSPF/RIP networks, SNMP/NTP/logging hosts: the device
treats them as a set. Interface bodies: IOS reorders sub-commands itself, so the
order in ``show running-config`` is the device's, not the operator's. Everything
else — ACLs, prefix-lists, route-maps, ``ip sla`` probes — is ordered, because a
reorder there changes what matches first. There is a test that reorders an ACL
and asserts failure, and one that reorders BGP neighbors and asserts success.

**No raw copies in interface entries.** An early version kept every claimed line
alongside the structured fields. A template emitting those would have scored
100% fidelity while modelling nothing. Structured keys and ``unmodeled``
partition the body between them, so the coverage number cannot be gamed.

**Coverage counts ``unmodeled`` against it.** A line in a pass-through block
round-trips perfectly and is not modelled at all. Reporting one number would
have let ``unmodeled`` inflate it — which is precisely the padding that was
ruled out in advance. ``round_trip_fidelity`` is reported separately.

### Demo-worthy flows added

1. Extract s1 → 100% modeled, and show the generated YAML with ``secret_ref``
   placeholders where the hashes were.
2. Extract r1 → 92.2%, and show the ranked unmodeled list as the "what to model
   next" backlog.
3. Reorder two ACL entries and watch validation fail; reorder two BGP neighbors
   and watch it pass.
4. Compare ``Gi0/2`` against ``GigabitEthernet0/2`` — identical.
5. Run the fixed-point test and explain what a failure would mean.

### For 3b

- The seed templates live in ``modules/nsot/templates/``. 3b copies them into
  the list's repo for editing, which is the first time templates become
  per-network rather than built-in.
- The staging area is gitignored and the extractor commits nothing. 3b's
  "Review and commit extracted host_vars" is where a human first sees a diff.
- The seven unmodeled constructs on r1 are the natural first backlog if anyone
  wants r1 at 100% — but by the agreed rule they stay unmodeled until a second
  device shows the same construct.

---

## A pre-existing defect the NSoT work uncovered: drift was blind to RIPv2 → RIPv1

Worth recording separately from the phase notes, because it is the clearest
example in this project of **new work finding an old bug** — and of a class of
bug that is close to invisible by inspection.

### What was wrong

``modules/drift_check.py`` compares a device's running config against its golden
config. Both sides are normalised first, to stop NTP drift and build timestamps
showing up as false drift. The normalisation stripped any line beginning
``version ``, on the reasoning that ``version 17.6`` is the IOS image version —
a fact about the device, not configuration.

But IOS uses ``version`` at two levels:

```
version 15.2            <- image version: a device fact
router rip
 version 2              <- RIPv2: actual configuration
```

The filter matched both. So ``version 2`` was stripped from the running config
**and** from the golden config before they were compared.

### Why it was invisible

Because the strip ran on *both* sides, the comparison still succeeded. Drift
reported "no drift". The round-trip validator reported 100% fidelity. Every
test that compared two normalised configs agreed that nothing was wrong,
because from their point of view nothing *was* wrong — the line simply did not
exist in either input.

The consequence: if someone changed a switch from RIPv2 to RIPv1, the drift
checker would not have noticed. That is a routing-protocol version change on a
production switch, silently invisible to the tool whose job is to notice
exactly that.

### How it surfaced

Not by reading the code, and not by any comparison test. It surfaced in Phase 3a
from an **extraction-side** assertion:

```python
def test_rip_is_parsed_with_networks_split_out(self, s1):
    rip = s1["routing"]["rip"]
    assert "version 2" in rip["settings"]     # <- failed
```

The parser genuinely could not see the line, because the line had been removed
before the parser ran. Extraction cannot hide the loss the way comparison can:
there is only one side, and the content is either there or it is not.

### The generalisable lesson

**A normalisation step applied to both sides of a comparison can hide exactly
what it destroys.** Any test that compares normalised-A with normalised-B is
structurally incapable of detecting over-normalisation. Only a test that
inspects what survived normalisation — an extraction, a parse, a schema
assertion — can catch it.

### The structural fix

Patching the one pattern would have left the next one waiting. Instead, every
prefix pattern in ``modules/nsot/normalize.py`` now **anchors to column 0**
unless explicitly listed in ``NESTED_OK_PREFIXES``, which is currently empty and
carries a comment requiring a justification for any addition. A test asserts the
property over every tuple in the module, so a future addition cannot quietly
reintroduce the class of bug:

```python
def test_no_pattern_matches_an_indented_line_unless_allowlisted(self):
    ...
    assert offenders == []
```

Plus a direct regression test that ``strip_for_diff`` now distinguishes RIPv2
from RIPv1.

### For the write-up

This is the strongest argument in the project for why templatisation was worth
doing beyond the lab requirement. Building a parser forced the tool to *state
what it believes a config contains*, and that statement could be checked. A
tool that only ever diffs two configs can be confidently wrong forever, because
it never has to say what it thinks it is looking at.

---

## A second defect of the same shape: empty-but-truthy made every optional construct mandatory

Recorded alongside the drift blind spot because it is the same lesson wearing
different clothes, and because it is the more consequential of the two.

### What was wrong

The parser emits a complete schema so templates can render under
``StrictUndefined``. Optional constructs get an empty default. ``control_plane``
defaulted to:

```python
"control_plane": {"settings": []},
```

The template guarded on presence rather than content:

```jinja
{%- if v.control_plane is defined %}control-plane
```

An empty dict is *truthy*, and ``is defined`` is true for any key that exists.
So every rendered config gained a ``control-plane`` header — **including devices
that never had one**.

### Why it was invisible

All nine devices in the reference fleet happen to configure ``control-plane``.
So on every real input, the invented line matched a line that was genuinely
there, and the round trip reported 100% fidelity. Nine devices, two platforms,
zero disagreement. The bug only appeared when the ``unmodeled``-path tests fed
the parser a **minimal** config — a hostname and nothing else — which no
fixture resembled.

### Why it is worse than a dropped line

A dropped line makes a deploy incomplete. An **invented** line makes a deploy
*wrong*: Phase 3c would have pushed ``control-plane`` to a device that had never
been configured with it, as part of an operation the operator believed was
reproducing existing config. The tool would have been adding configuration while
reporting that it was matching it.

And it generalises past this one key. Any optional construct whose default is an
empty-but-truthy container — ``{}``, ``{"settings": []}``, ``[""]`` — becomes
mandatory at render time. The fix was not to special-case ``control_plane`` but
to make every optional block default to ``None``, with a parametrised test
asserting that nine named constructs are absent from a minimal render.

### The shared lesson

Both defects are the same shape:

| | Drift blind spot | Invented control-plane |
|---|---|---|
| Hidden by | normalisation applied to *both* sides | every fixture happening to have the construct |
| Reported | "no drift" | "100% fidelity" |
| Consequence | a real change invisible | a fabricated change invisible |
| Found by | an extraction-side assertion | a minimal input no fixture resembled |

Neither was findable by comparing two configs, because in both cases the two
sides agreed. **A comparison-only tool can be confidently wrong forever**, in
both directions: it can miss what is there, and it can manufacture what is not.
What broke the symmetry in each case was making the tool *state what it
believes* — a parse, a schema, a rendered artifact from a known-minimal input —
and then checking the statement against something other than another comparison.

### For the write-up

These two findings together are the argument for why the NSoT conversion earned
its keep beyond the lab objectives. The pre-NSoT tool could diff configs and
report drift, and it did so wrongly in at least two ways for an unknown length
of time, with no test capable of noticing. Building parsers forced the tool to
commit to a model of the configuration, and a model can be falsified.

---

## A third of the same family: masking applied to one side only

The two earlier findings were about a transformation applied to **both** sides
of a comparison. This one is the mirror image — a transformation applied to
**one** side — and it is just as dangerous, which is the point worth recording.

### What happened

Phase 3b renders previews with every secret replaced by ``••••••••``, so that
neither the screen nor ``intended/`` ever holds a credential. The first version
then validated that same masked render against the device's real config:

```python
rendered = roundtrip.render(parsed, platform, secret_lookup=lambda _: MASK)
report   = roundtrip.compare(running_config, rendered, parsed)   # wrong
```

Every line containing a secret then differed. ``username admin secret 5 $1$…``
in the real config versus ``username admin secret 5 ••••••••`` in the render.
The comparison dutifully reported each one as **both missing and invented**:

```
blocking: ['3 line(s) the template does not reproduce',
           '3 line(s) the template invents', ...]
```

### Why it matters more than it looks

Those counts feed the deployability gate. A correct template on a correct device
would have been reported as broken, in proportion to how many secrets the device
had. Worse, the numbers were *plausible* — three secrets, three "missing", three
"invented" — so they read like a real template defect rather than an artefact of
the measurement. Someone would have spent an afternoon editing a template that
was already right.

### The fix

Validate the **truthful** render; display the masked one.

```python
truthful = roundtrip.render(parsed, resolved_platform)    # real secrets
report   = roundtrip.compare(running_config, truthful, parsed)
del truthful                                              # never stored

rendered = roundtrip.render(parsed, resolved_platform,
                            secret_lookup=lambda _: MASK) # the only field
```

The unmasked render is a local. It is never a dataclass field, never returned,
never written. A test asserts ``RenderArtifact`` has no ``rendered`` or
``rendered_unmasked`` attribute, so it cannot quietly become one.

### The family

| | ``version 2`` | invented ``control-plane`` | masked validation |
|---|---|---|---|
| Transformation | strip, **both** sides | default, **neither** side | mask, **one** side |
| Symptom | real change invisible | fabricated line invisible | correct template reported broken |
| Hidden by | both sides agreeing | every fixture having the line | plausible-looking counts |

All three are failures of the same discipline: **whatever you transform before
comparing, you have to be able to say what the comparison is now measuring.**
Strip from both sides and you measure less than you think. Default a value and
you measure something that was never there. Transform one side and you measure
the transformation instead of the thing.

The rule that falls out, and the one worth putting in the write-up: *compare
like with like, and validate against truth — then mask for display, never
before.*

---

## Stage 7 captured metrics, not config — the silent-wrong-record bug

Same family as the drift blind spot and the invented ``control-plane``, and
found the same way: by asking what a thing actually does rather than what its
name suggests.

### What happened

Phase 3c added stage 8.5, which commits the post-deploy config as the new
golden baseline. Containerlab nodes are ephemeral, so that commit is the only
durable record of what was pushed.

Stage 7 is called ``post_snapshot``, and stage 4 is ``pre_snapshot``. Stage 4
captures a running config — stage 5 diffs against
``ctx.pre_snapshots[ip]["running_config"]``. The symmetry of the names made it
natural to assume stage 7 captured one too.

It did not. ``_capture_operational_snapshot`` collects **operational metrics**:
routing neighbours, interface up/down counts, route totals. It exists to diff
pre-versus-post for convergence checking, and a config never enters it.

So stage 8.5 would have found no post-deploy config and fallen back to the only
one available — stage 4's **pre-deploy** copy. Every golden commit would have
recorded the configuration the device had *before* the deploy, labelled as what
was just pushed.

### Why it would have been hard to notice

The commit would exist. The tags would be right. The timeline in the Golden tab
would show a promotion at the right moment with the right actor and source. The
diff against the previous golden would even look plausible, because most of the
config genuinely had not changed.

The only symptom would be that the thing you just deployed was missing from the
record of the deploy — and you would most likely discover that after a
containerlab redeploy wiped the device and the golden config turned out not to
contain the change you were restoring.

### The fix

Stage 7 now captures the post-deploy running config on the session it already
holds, and stage 8.5 commits that. If the capture fails, the device is listed
in ``golden_skipped`` with a reason and **no golden is written** — recording
nothing is better than recording the wrong thing.

### The pattern, now three deep

| | Hidden by | Would have reported |
|---|---|---|
| ``version 2`` stripped | both sides agreeing | "no drift" on a real change |
| invented ``control-plane`` | every fixture having it | "100% fidelity" on a fabricated line |
| masked validation | plausible counts | "template broken" on a correct one |
| stage 7 metrics | symmetrical stage names | "golden saved" on the wrong config |

Every one is a **silently wrong record** rather than a crash. None would have
been caught by a test comparing two artifacts, because in each case the two
artifacts agreed. What caught them was asking, separately, what each side
actually contained.

## Why ``write memory`` runs before verify, not after

A deliberate asymmetry worth defending in the write-up, because the safer-looking
option is the wrong one.

``_push_via_netmiko`` calls ``conn.save_config()`` immediately after
``send_config_set``, so the new config is in startup **before** verification
runs. If verify then fails, rollback restores the previous config and saves
again.

The obvious objection: for the duration of verification, a bad config is in
startup, and a reload in that window boots the device into it.

The alternative — save only after a successful verify — has the mirror problem,
and it is worse:

| | Save early (current) | Save late |
|---|---|---|
| Reload during verify | boots the **bad** config | boots the **old** config, losing a good change |
| Bounded by | rollback, seconds later | nothing — the change is simply gone |
| Recovery | automatic | re-deploy, if anyone notices |

Saving early risks a bad startup config for a few seconds, with rollback already
committed to fixing it. Saving late risks silently losing a *good* change, with
nothing at all committed to noticing. A bounded, self-correcting risk beats an
unbounded, silent one.

The window is also narrower than it looks: verification is the only thing
between the two saves, and a device reloading spontaneously during a
verification the operator is watching is a much rarer event than a deploy whose
result quietly fails to persist.

---

## A function that asserted nothing: `assert_no_negation`

The other findings in this project are asymmetric transformations — something
stripped from both sides, defaulted on neither, masked on one. This one is a
different class, and a worse one: **a guarantee that was named but never
implemented**, on the deploy path, with every test passing.

### What was written

Phase 3c's merge-only requirement says the tool must never generate a `no`
command to remove configuration. The first implementation:

```python
def assert_no_negation(commands: list) -> None:
    """Merge-only means no ``no`` command is ever generated by this tool.

    An operator's template may legitimately *contain* a ``no`` line — ``no ip
    http server`` is real configuration. What must never happen is this module
    synthesising one to remove something.
    """
    return None
```

The docstring is correct. It states the property precisely, and even
anticipates the subtle case. The body returns `None` and checks nothing.

### Why it survived

Every property this function guards was, at that moment, true — the merge diff
genuinely did not synthesise negations. So:

* every call site passed, because the function never raised;
* the deploy path looked guarded, because a function named `assert_*` sat in it;
* a reviewer reading the call site would see `assert_no_negation(commands)` and
  move on, exactly as intended;
* a reviewer reading the *function* would see a correct, careful docstring
  before reaching the one-line body.

It would have failed only when it mattered: the day a future change started
generating negations, at which point the guard would have waved them through
and the deploy would have removed configuration nobody asked to remove.

I wrote it. The honest account of how is that I knew what the property was,
wrote the docstring that described it, and then did not implement the check
because the check was not obvious — and a stub that returns `None` runs green.

### Why the obvious implementation is also wrong

The tempting fix is to grep for the word:

```python
if any(c.strip().startswith("no ") for c in commands):
    raise ...
```

That is wrong in both directions. It **rejects legitimate config**: `no ip http
server`, `no switchport`, `no auto-summary` and `no shutdown` are real lines
that appear in the reference fleet's templates and must be pushed. And it
**misses real synthesis**: a generated removal need not start with `no` at all —
`default interface GigabitEthernet0/1` removes far more.

### The replacement: check provenance, not spelling

```python
def assert_merge_only(to_push, intended_config):
    allowed = {canonicalise(l) for l in strip_for_roundtrip(intended_config)}
    invented = [c for c in to_push if canonicalise(c) not in allowed]
    if invented:
        raise NegationSynthesised(...)
```

Every command about to be pushed must appear **verbatim in the intended
config**. A line the operator wrote is allowed whatever it says; a line the tool
invented is refused whatever it says. That inverts the question from "does this
look like a removal?" — which is a guess about syntax — to "where did this come
from?", which is a fact.

It is also strictly stronger than the requirement: it catches any synthesised
command, not only negations.

### The lesson

**A stub that returns `None` is indistinguishable from a passing check.** Both
are silent, both are green, and the name of the function is doing all the work
of convincing everyone — including the person who wrote it — that something is
being enforced.

Two habits fall out, and both are worth stating in the write-up:

1. **An `assert_*` function must have a test that makes it raise.** Not a test
   that calls it and passes — one that constructs the forbidden input and
   asserts the exception. `test_invented_command_is_refused` is that test here,
   and it is the thing that would have caught the stub on day one.
2. **Prefer checking provenance to checking appearance.** Where a rule is about
   what the tool is allowed to *originate*, tracking origin is both simpler and
   sounder than pattern-matching the output.

---

## Fixtures written by the author cannot surprise the author

The migration bug that a dry run against the real NMAS found, and that none of
the tests could have.

### The bug

The Phase 2 migration moves golden configs from the two legacy stores into
``config_repo/golden/``. Run against the real NMAS in report-only mode, it said:

```
candidate files     : 18
devices after merge : 18
duplicate merges    : 0
```

Nine devices. Eighteen "devices". Zero merges. And each pair pointed at the same
destination:

```
r1  10.255.1.11   golden_configs/r1.cfg  -> golden/r1.cfg
r1  (no ip)       config_repo/r1.cfg     -> golden/r1.cfg
```

Applying it would have written each device's golden file twice, the second
silently overwriting the first, for all nine devices.

### The cause

The two stores hold the same device in **different formats**, and grouping used
a single key — management IP when present, case-folded hostname otherwise:

| File | Header | Parses to | Grouped as |
|---|---|---|---|
| ``golden_configs/s4.cfg`` | ``! Golden config — s4 (…)`` | an address | ``ip:…`` |
| ``config_repo/s4.cfg`` | stripped by ``write_and_stage`` | nothing | ``name:s4`` |

Two keys, one device. The merge detection built specifically to prevent one
device becoming two golden files could not see the most common way that
actually happens on a real system.

### Why no test caught it

There were already eight tests for duplicate detection, covering
case-insensitive names, IP-level duplicates, newest-content-wins, backup of
losers, and idempotence. They all passed.

Every one of them wrote **both copies in the same format**. Of course they did:
I wrote a helper, ``_write(lab, store, filename, hostname, ip, body)``, and
called it twice with different stores. A helper produces consistent output —
that is the point of a helper — and consistent output is exactly what the real
system does not have.

The asymmetry between the stores is not something the tests forgot to cover. It
is something they could not express, because the fixture generator had one code
path and the production system has two, written years apart by different
functions with different jobs.

### The generalisable point

**A fixture encodes the author's model of the data. A test built on it can only
falsify things the author already thought were possible.** It is very good at
catching regressions and very bad at catching the case where the model itself
is incomplete — which is most interesting bugs.

That is the whole argument for the dry run being the *default* mode, and for
running it against production shapes before anything else. It is the only step
in this project where reality gets to disagree with me. It disagreed
immediately.

Three habits fall out:

1. **Dry-run against real data before trusting a migration**, however well
   tested. The tests tell you the code does what you meant; only real data tells
   you whether what you meant covers what exists.
2. **Be suspicious of fixture helpers in tests about data variation.** A helper
   guarantees uniformity, which is precisely the property under test.
3. **Check the arithmetic of a report, not just its status.** The dry run did
   not error. It said "18 devices" for a nine-device network and "0 merges" for
   a case built to produce merges, and both numbers were right there. Reading
   "ok: true" and moving on would have missed it.

### The fix, and a second bug underneath

Identity became a **connected component**: two candidates are the same device if
they share an address *or* a case-folded hostname. Union-find over both, then
merge whole components.

Fixing that surfaced another. The merge picks the newest file as the winner, and
the header-stripped ``config_repo`` copy often *is* newer — but it has no
management IP. The manifest entry would have been written with an empty address,
breaking ``find_by_ip`` and therefore ``_find_golden_config_file``. The group's
richest identity now wins regardless of which member is newest.

One bug hid another, and the second was only reachable once the first was
fixed — which is an argument for fixing and re-running rather than fixing and
assuming.

---

## The most repeatable lesson: the tool's own artifacts were never in the test corpus

Three separate bugs in this project share one root cause, and stating it
generally is more useful than any of the three individually.

### The three

| Bug | Symptom on real data |
|---|---|
| Migration counted one device as two | 18 "devices" for a nine-device fleet, 0 merges, both copies writing to the same path |
| Merge discarded the management IP | manifest entry with no address, breaking `find_by_ip` |
| Five unreproducible lines per device | `strip_for_roundtrip` never removed NMAS's own golden header |

Each had tests. The migration had eight duplicate-detection tests. The round
trip had a nine-device fleet at 100% fidelity. All passed.

### The single cause

**Every fixture was built from raw device output. None carried the artifacts
NMAS itself produces.**

A config fixture in this repo is what a device prints. A golden config on a real
NMAS is that, plus three header lines NMAS writes onto it:

```
! Golden config — s4 (10.255.1.24)
! Saved: 2026-09-15 22:36:40
! Source: show startup-config
```

And the second store, `config_repo/`, holds the same config with that header
*stripped* by `config_git.write_and_stage`. So a real device exists in two
formats, neither of which is "what the device printed", and the fixtures had
only the third form that no store actually contains.

Every one of the three bugs lives precisely in that gap:

* the migration could not group two formats as one device, because no fixture
  had two formats;
* the merge lost the IP, because no fixture had a copy *without* one;
* the round trip could not strip the header, because no fixture *had* one.

### Why it is easy to do and hard to notice

A fixture is written by reading the source of truth — a device — and capturing
what it says. That feels like the most faithful thing available, and for parser
tests it is. The mistake is assuming it stays faithful once the tool has
touched the data.

Everything the tool writes is a **transformation** of that input: a header
added, a header stripped, a normalisation applied, a byte count prefixed. Those
transformed forms are what the next stage actually reads, and they are what
production is full of. A corpus of pristine device output tests the first stage
and nothing after it.

The failure is silent in every case, because a fixture that is the wrong shape
does not error — it simply exercises a path production never takes, and reports
success.

### The rule

**Test fixtures must include the artifacts the tool itself produces, not only
the inputs it consumes.** For each store the system writes, there should be a
fixture in that store's format, produced the way the system produces it.

Concretely, what this project now has:

* `TestRealNmasGoldenShape` wraps each fleet fixture in the header NMAS writes
  and asserts the round-trip verdict is identical with and without it;
* `TestBothStoresHoldTheSameDevice` builds one device in *both* stored formats —
  one headered, one stripped — and asserts it counts as one device;
* and the general habit: **dry-run against production data before trusting a
  migration**, because it is the only step where reality gets to disagree with
  the author's model. It disagreed three times.

### For the write-up

This is the strongest methodological point the project produced. "We wrote
tests" is not the claim worth making. The claim worth making is: *we discovered
that our tests could only falsify what we had already imagined, and we found the
gap by running against production shapes instead.* Every one of these three bugs
would have reached a real deploy, and each would have failed quietly — a
silently wrong record, not a crash.


---

## The unconsumed check: `already_migrated`, and why it is the same bug as `assert_no_negation`

Found by re-running the migration against the live lab, not by any test.

### What happened

`plan()` returned a field called `already_migrated`. The migration UI read it
to decide whether to show the migration card. `apply()` — the function that
actually writes — never looked at it.

So when the migration ran a second time, it ran. Nothing stopped it, because
nothing was asking.

That alone would have been survivable if a second run were a no-op. It was not,
and the reason is the same two-stores asymmetry that produced three earlier
bugs. `golden_configs/r1.cfg` carries the NMAS header line; `config_repo/r1.cfg`
has it stripped. The first run `git mv`s the repo copy into `golden/` and that
copy wins. The second run looks for candidates, finds the repo copy gone from
where it used to be, finds only the `golden_configs/` copy — a *different shape
of the same config* — renders it, and commits the difference.

On the live repo that was commit `e014843`: nine files changed, eighteen
insertions, every one of them a blank line or a bare `!`. A diff that says
nothing, on top of a baseline the whole project is anchored to.

### The second signal, also wrong

The value `apply()` ignored was not merely unused. It was false on its own
terms:

```python
already_migrated = os.path.isdir(os.path.join(repo, "golden"))
```

`init_repo()` creates `golden/`, `intended/`, `.nsot/` and `infra/` on the first
call. So this expression is true from the moment the repository exists, before
a single device has been migrated. It never returned `False` on a real repo
except by accident of ordering.

Two failures stacked: a check that computed the wrong thing, and no caller that
would have noticed because no caller consumed it.

### The family it belongs to

This is the third instance in the project of one shape, and the clearest:

| Where | What it claimed | What it did |
|---|---|---|
| `assert_no_negation(commands)` | "raises if any command negates config" | `return None` |
| `plan()["already_migrated"]` | "this repo has already been migrated" | computed, reported, consumed by nothing |
| `RenderArtifact.deployable` | "this artifact is safe to push" | — a *property*, so nothing can set it |

The third is in the table because it is the counterexample. `deployable` has no
backing field: it is computed from the artifact's own contents every time it is
read, on a frozen dataclass, so there is no code path that can make it say yes
when the artifact says no. That is what the other two should have been.

The general shape is **a safety value whose truth is never tested by the thing
it is supposed to protect**. A stub that returns `None` and a field that no
caller reads are indistinguishable at the call site: in both cases the guard
appears in the source, reads correctly in review, and has no effect.

### Why a grep would not have found it

`already_migrated` *was* referenced — twice. Once where it was computed, once
in the template that renders the migration card. A search shows two hits and
looks healthy. The question that finds the bug is not "is this referenced" but
"is this read by the function that can do the damage", and no tool asks that.

### The two fixes, deliberately independent

The instinct is to fix the guard and stop. That produces a system with exactly
one thing standing between it and a bad commit, which is how the original got
written.

1. **A marker the guard can read.** `.nsot/migrated.json` holds a timestamp and
   the commit sha. `apply()` refuses with `already migrated at <sha>`. The
   state is recorded rather than inferred, so the check cannot be wrong about
   what it is checking the way `isdir("golden")` was.

2. **An empty commit made structurally impossible.** Independently of the
   guard, migration now matches the discipline `save_golden` already had:
   `_content_changed()` before rewriting any golden file, so an identical file
   is not touched; `git diff --cached --name-only` before committing, which
   asks the *index* what will be committed rather than asking the worktree what
   differs; and no `--allow-empty`, so git itself refuses. A test deletes the
   marker — simulating the guard being bypassed or removed — and asserts that
   re-running produces no commit.

The second fix is the one that matters for the write-up. A guard protects
against the case you thought of. A structural impossibility protects against
the case you did not, including "someone deletes the guard in six months".

### Why the marker is not version-controlled

It was tempting to commit it. Two reasons not to:

- It has to carry the commit sha, which does not exist until after the commit
  that would contain it. Committing it means either a second commit or a
  deliberate lie in the file.
- "Has this data directory been migrated" is local installation state, not
  repository content. It belongs with `.nsot/migration-backup/` and
  `.nsot/staging/`, both already ignored. The version-controlled record of the
  migration already exists: the migration commit and its `baseline/` tag.

### The rule

> A value that names a safety property must be read by the function that can
> violate it — and then the violation should be made impossible a second way,
> without reference to the value.

If only the first half is true, the property is documentation. If only the
second, the guard is redundant but harmless. Both is the point.

---

## Platform: inferred from the wrong artifact, then never refreshed

A smaller find from the same verification pass, worth recording because the fix
location is the interesting part.

Every manifest entry on the live lab had `"platform": ""` — all nine devices.
The cause is direct: migration builds its entries by reading config files, and a
`.cfg` file cannot tell you whether the box is a C8000v or a vIOS-L2. There was
nothing to read it *from*.

The consequence was silent. `platform_for_device()` falls back to
`DEFAULT_PLATFORM` when nothing is recorded, so parser selection kept working
and produced answers for every device — using the `cisco_ios` dialect for the
IOS-XE routers, which is exactly the conflation `modules/nsot/platform.py` was
written to end.

The fix has two halves and the second is the one that was nearly missed:

- Platform comes from the **inventory** — the CSV `platform` column for local
  lists, the NetBox platform slug for NetBox lists. The inventory is the only
  store that knows, because it is the only one a human or NetBox writes to.
- It is refreshed **whenever the inventory changes**, not only at migration.
  `manifest.sync_platforms()` is called from `refresh_list()` and from
  `write_devices_csv()` — the two points where a list's inventory is rewritten.

Migration-time-only would have looked correct in every test: migrate a list with
platforms set, assert the manifest has them. It would have been wrong the first
time an operator corrected a platform they had typed wrong, because Phase 4
onboarding reads platform from the manifest, not from the CSV. The value would
have been right in the place a human edits it and stale in the place the code
reads it — the most expensive kind of wrong, because both look authoritative.

The general form: **a value copied between stores needs a refresh path, not just
an initial-population path.** Deciding where the refresh hook goes is the same
question as "what event means this value might have changed", and answering it
at migration time only means the answer was "the migration", which is a
one-time event that the value's lifetime outlives.

---

## Five times: a rule that never reaches what already exists

Worth naming as its own pattern, because it has now happened five times in this
project and the fifth was found by reading `git status` on a live repo rather
than by any test.

The shape is always the same. A rule is added. It is correct. It is applied at
the point where new things are created. Everything created afterwards is fine.
Everything that already existed never receives it — silently, because nothing
reads the rule back to check.

| # | The rule | What never received it |
|---|---|---|
| 1 | `DEVICE_CSV_FIELDS` gaining `platform` / `device_uid` | three of four writer copies |
| 2 | volatile-line prefixes anchoring to column 0 | `strip_for_diff`'s existing callers |
| 3 | `NMAS_HEADER_PREFIXES` in `strip_for_roundtrip` | every config already in the corpus |
| 4 | the `nmas-managed` tag | every NetBox object created before it |
| 5 | `.nsot/migration-backup/` in `.gitignore` | the one repo that predated the rule |

Number five is the cleanest specimen. `init_repo()` contained this:

```python
gitignore = os.path.join(repo, ".gitignore")
if not os.path.exists(gitignore):
    with open(gitignore, "w", encoding="utf-8") as fh:
        fh.write("*.swp\n*.tmp\n.nsot/migration-backup/\n.nsot/staging/\n")
```

Read on its own it is obviously right: create the file with the rules in it.
The bug is entirely in the `if`. A repo created in week one has a `.gitignore`,
so the branch never runs again, so a rule added in week six reaches nothing that
was already on disk.

The visible consequence was nine backup copies of the loser golden configs
committed into the version-controlled store, plus the new migration marker
showing up as untracked. Neither is dangerous. Both are exactly the noise the
rule existed to prevent, sitting in the one repo the rule was written for.

### Why every test passed

Every test builds its repo with `init_repo()` in the same process that then
asserts on it. The file is always absent at creation, so the branch always runs,
so the rules are always present. There is no fixture anywhere in the suite for
"a repo that already existed before this rule did" — because writing one means
first knowing the rule might not have reached it, which is the thing being
tested for.

This is the same root cause recorded above under *the tool's own artifacts were
never in the test corpus*, seen from a different angle: there, the fixtures held
a config shape no store actually contained; here, they hold a repo *age* no real
repo actually had.

### The fix, and why it is not memoised

`ensure_repo_hygiene()` runs from `git()` — the one function every path,
read or write, goes through:

```python
def git(repo, *args):
    _clear_stale_lock(repo)
    ensure_repo_hygiene(repo)
    ...
```

The obvious optimisation is a per-process memo, and it is the wrong call. A memo
means a `.gitignore` edited after the first touch stays stale until restart —
which is this exact bug, with a shorter fuse. The cost of not memoising is one
small file read per `git()` invocation, against spawning a subprocess. Paying
it is not a trade.

### The general rule

> Any rule about the *shape* of persistent state needs an idempotent
> bring-up-to-date path that runs on access, not only a create path that runs
> on creation.

Creation-time application is an optimisation. It is correct only for a system
with no history, which describes a test suite and nothing else.

---

## The commit that carried the move but not the map

`apply_pending_renames()` did this:

```python
git(repo, "mv", "-f", old_rel, new_rel)
git(repo, "add", "-A", "golden")
git(repo, "commit", "-m", message)
_manifest.clear_pending_rename(repo, identity, new_name, new_rel)
```

Read top to bottom it looks complete: move the file, commit the move, update the
manifest. Every one of those things happens. The bug is that the last line
happens *after* the third, so the manifest change is not in the commit — and
`add -A golden` would not have staged it anyway.

The working tree is fine. `save_golden` stages `.nsot`, so the next golden save
sweeps the manifest update into its own commit and the live system never
notices. What is broken is the repository **as a historical artifact**: check out
the rename commit, or restore a bundle at it, and you get `golden/R1-CORE.cfg`
on disk alongside a manifest that says the device's golden config is at
`golden/R1.cfg`.

`_find_golden_config_file()` then finds no manifest entry and falls through to
step 3, the deprecated legacy header scan — which reads `golden_configs/`, a
directory a restore does not recreate. The device resolves to nothing, and the
failure presents as "this device has no golden config" rather than as anything
resembling a rename problem.

### Why this one is easy to write

The three operations are genuinely independent in the working tree, and the code
reads as a sequence of correct steps. Nothing about `clear_pending_rename` being
last looks wrong until you ask a different question: *what does someone see who
only has this commit?*

That question is not natural to ask while writing, because the author always has
the whole repo. It is the same blind spot as the fixtures one — the author's
context is richer than the consumer's, and the difference is invisible from
inside.

### The check that generalises

> For every commit a system creates, ask what a reader who has **only that
> commit** can resolve.

If the answer depends on state the commit does not contain, the commit is
incomplete regardless of whether the running system works. Tests for this read
blobs out of git (`git show HEAD:path`) rather than reading the working tree,
because the working tree is exactly the thing that hides the bug.

---

## A commit subject that described one file while adding forty

`seed_templates()` copies the built-in template library into the repo. It is
called from the template-list route, which is a `GET`. It commits nothing.

So the first thing to run `save_templates()` afterwards committed the library.
In practice that was the **approval**, which stages `templates` and would have
produced:

```
template: approve cisco_ios/base.j2
  40 files changed
```

Two distinct failures in one commit. The subject is a lie about the contents —
and every audit tool in this project, including its own `golden_history()`,
reads subjects and trailers. And the approval becomes unreviewable: the point of
committing an approval separately is that its diff is small enough to read, and
here the diff is the entire library.

The fix is one commit per intent — `template: seed library (N file(s))` when
seeding actually writes something, and nothing when it does not. The test that
matters is not "does seeding commit"; it is that an approval *after* seeding
touches exactly `templates/.approvals.json` and nothing else.

Secondary note worth recording: a `GET` route with a write side effect is how
this stayed invisible. Listing templates seeded them, so by the time anyone
looked at the library it already existed on disk, and the question "when was
this committed?" never came up.

---

## Sixth instance: the condition described the filesystem, not the repository

The fix for the uncommitted template library was right about what to commit and
wrong about when. One line decided:

```python
copied = result.get("copied") or []
if not copied:
    return result
```

`copied` is what `shutil` did during this call. The question the function
actually needed answered is what the repository is missing. Those coincide on a
machine with no history and diverge everywhere else.

On the live box the old code had already copied the library onto disk and
committed nothing. So the new code ran, `seed_templates()` found every file
already present, returned `copied == []`, and the fix returned early — leaving
the library untracked exactly as before. The fix was deployed, correct in
isolation, and inert.

### The tell

The test that "proved" the fix used a fixture that ran `init_repo()` into an
empty directory and then seeded. In that world `copied` is always non-empty on
the first call, so the branch always ran. Nothing in the suite had a repo where
seeding had *already happened without a commit*, because constructing that
fixture requires already suspecting the bug.

This is the same failure as the `.gitignore` one directly above it, and as the
fixtures lesson before that. The suite keeps testing the system's first five
minutes.

### The rule, sharpened

Earlier this was written as *"any rule about the shape of persistent state needs
a bring-up-to-date path that runs on access"*. This instance sharpens the
operative half:

> The condition for a repair action must be a **property of current state**, not
> a **record of this run's activity**.

`copied` is activity. `git status --porcelain` is state. Both are one line of
code; only one of them is idempotent in the sense that matters — able to finish
a job a previous, differently-versioned run left half done.

A useful test for which one you have written: *if this code had crashed halfway
through last time, would running it again finish the job?* Activity-based
conditions answer no, and they answer it silently.

### Two details worth keeping

**`-uall`.** `git status --porcelain` collapses a wholly-untracked directory to
a single `?? templates/` entry. Without `-uall` the repair sees one path where
there are several, and staging that one entry happens to work while the count
in the commit subject is a lie.

**Stage paths, not trees.** The repair stages the specific untracked paths
rather than `add -A templates`. A tracked-but-modified template is an
operator's in-progress edit — seeding never overwrites, so it cannot be
seeding's doing — and sweeping it into a commit subjected "seed library" would
mislabel a commit in precisely the way this whole function exists to prevent.
The narrower fix would have been to widen the staging; the correct one was to
narrow it.

### A defect the test found that reading would not have

The status parser used fixed column offsets, `line[:2]` and `line[3:]`.
Porcelain pads the status field to two characters, so a tracked-but-modified
file is `` M`` — leading space — and `git()` strips its stdout, so the *first*
line loses that space and the slice takes the path one character short. The
assertion failure read:

```
assert ['emplates/cisco_ios/base.j2'] == ['templates/cisco_ios/base.j2']
```

In production this would not have raised. It would have produced a path that
matched nothing, and the file would have been quietly excluded from the
category it belonged to — a silent miscategorisation, which is this codebase's
signature failure mode. The only reason it surfaced is that the test asserted
on the *exact path list* rather than on a count or a boolean.

> Assert on the values, not on how many of them there are. A count is right
> for the wrong reasons more often than a value is.

---

## `git()` stripping stdout, and the column-position parser downstream

Small, and the clearest single specimen of the pattern the whole project keeps
running into, so it gets its own entry.

`git()` is the subprocess wrapper every git call in the codebase goes through:

```python
proc = subprocess.run([...], capture_output=True, text=True, ...)
return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
```

The `.strip()` is entirely reasonable. Git output ends with a newline; every
caller that reads a sha, a branch name, a tag list or a status summary wants it
gone. It has been there since the module was written and has never caused a
problem, because every consumer up to now split on newlines and stripped each
line anyway.

Then a consumer arrived that reads by **column position**:

```python
code, path = line[:2], line[3:].strip()
```

That matches `git status --porcelain`, whose format is a two-character status
field, a space, then the path. For an untracked file the field is `??`, both
characters present, and the slice is correct. For a tracked-but-modified file
the field is `` M`` — a **leading space** and then `M` — and `stdout.strip()`
has already removed that leading space from the *first line of the output*. The
line becomes `M templates/cisco_ios/base.j2`, `line[3:]` starts one character
late, and the parser returns:

```
emplates/cisco_ios/base.j2
```

### Why this is the same bug as the rest

Every ingredient is individually correct:

* stripping trailing whitespace from subprocess output is good hygiene
* porcelain's format really is two columns then a space
* slicing at fixed offsets is the obvious way to read a fixed-width format

The defect exists only in the *seam*, and only for one of the two status codes,
and only on the first line. Nothing raises. The function returns a list of
strings that look like paths. In production the file would simply have been
absent from the category it belonged to — silently miscategorised, which is
this codebase's signature failure, shared with the drift blind spot, the masked
validation, and the invented `control-plane`.

The general form has now appeared often enough to state flatly:

> A transformation that is correct in isolation can destroy exactly the
> information a downstream consumer depends on, and neither end looks wrong on
> its own.

`strip()` removes leading whitespace; a fixed-offset parser depends on leading
whitespace. Neither knows about the other. The seam has no owner.

### What actually caught it

Not review — I wrote both halves and read both. The test:

```python
assert result["uncommitted_edits"] == ["templates/cisco_ios/base.j2"]
```

```
E  assert ['emplates/cisco_ios/base.j2'] == ['templates/cisco_ios/base.j2']
```

The assertion compares the **exact path list**. Had it asserted
`len(result["uncommitted_edits"]) == 1`, or `result["uncommitted_edits"] != []`,
it would have passed — the list has one element, and that element is a string.
Every weaker form of the same test is green on corrupt data.

> Assert on values, not on how many of them there are. A count is right for the
> wrong reasons far more often than a value is.

### The fix, and the better habit

Parse by splitting on whitespace rather than by offset, and handle porcelain's
rename form (`old -> new`) while there:

```python
code, _sep, rest = line.strip().partition(" ")
```

This is robust to the wrapper's stripping, to padding changes, and to being
handed already-stripped lines by some future caller. The narrow fix — stop
stripping in `git()` — would have been worse: it fixes this consumer and breaks
the dozen that rely on the strip.

> When a seam bug appears, fix the end that can be made *independent* of the
> assumption, not the end that currently satisfies it.

---

## The one that was caught: defence in depth, measured

Every other entry here is a defect found by inspection, by a test, or by a dry
run against real data. This one is different, and it is the most useful result
in the project for the write-up, because it is the only place where the safety
machinery was tested by an accident rather than by a test written to test it.

### The defect

`to_yaml()` strips the `secrets` key on the way out and recomputes
`secret_refs` from that same key. Feed its own output back in — which is
exactly what read-staged → write-committed does — and the key is gone, so the
refs come back empty:

```
after one pass  : secret_refs: [snmp_community_ro, user_admin_secret]
after two passes: secret_refs: []
```

Underneath it, a second defect: the commit route promoted the staged YAML,
which carries refs and never values *by design*, so `store_secrets()` had
nothing to move and the credential store stayed empty. Two independent bugs,
both silent, both in the path from "operator reviews an extraction" to "device
receives a config".

### What should have happened next

`host_vars/s4.yml` committed with `secret_refs: []`. The deploy path hydrates
secrets by name; there were no names, so it resolved nothing. The renderer's
fallback for an unresolvable secret is a marker string. The SNMP community
line, the enable secret line and the local user line would each have rendered
as:

```
snmp-server community <missing-secret:snmp_community_ro> RO
```

Merge-only then computes: these three lines are in the render and not on the
device, so push them. The device would have received three configuration
commands containing the literal text `<missing-secret:…>` — plausibly accepted
by IOS as an SNMP community string, and definitely destroying the enable
secret.

### What actually happened

```
secret_refs: []   →  hydrate_secrets() resolves nothing
                  →  render emits <missing-secret:user_admin_secret>
                  →  assert_no_mask() raises MaskedContentError
                  →  plan reports the error, to_add: 0, nothing pushed
```

Four layers downstream of the bug, on a **read-only plan**, one step before any
socket opened.

### Why that is the interesting part

`assert_no_mask()` was not written for this. It was written in Phase 3b for a
completely different failure: `intended/` is rendered masked for display, and
the worry was that someone would later wire the deploy path to read that file
and push `••••••••` to a device. The marker list was written for that:

```python
MASK_MARKERS = (MASK, "••••", "<masked>", "<missing-secret:")
```

`<missing-secret:` is in that tuple almost incidentally — it is the renderer's
"I could not resolve this" output, included because it is *another* way a
non-credential can end up where a credential belongs. That inclusion, made for
tidiness against a hypothetical, is what caught a real bug two phases later
arising from an unrelated cause.

The lesson is not "we got lucky". It is that the property being guarded was
stated correctly. `assert_no_mask()` does not check "did the preview path leak
into deploy" — the specific scenario. It checks **"does this text contain
something that is not a credential, in a position where a credential belongs"**
— the invariant. A guard written against a scenario catches that scenario. A
guard written against an invariant catches every route to violating it,
including the ones nobody imagined.

### The argument for a computed gate with no override

`deployable` is a property on a frozen dataclass with no backing field. Every
review of that design asks the same question: isn't this over-engineered for a
school project, when a boolean would do?

This is the answer, with numbers attached. The failure chain crossed four
components — serialiser, commit route, credential store, renderer — and at no
point did any of them *know* something was wrong. The serialiser returned valid
YAML. The commit route returned `ok: true`. The store returned an empty list,
correctly, because it was empty. The renderer produced a complete config. Every
component was locally correct and the composition was catastrophic.

Nothing upstream could have flagged it, because nothing upstream had the
information. The only place the problem is visible is at the boundary where the
text meets the device — and the only reason it was seen there is that the check
at that boundary cannot be turned off, cannot be set, and runs on the actual
bytes about to be sent.

Compare the alternative that was nearly built: a `deployable` field set by
whichever code path constructed the artifact. Every one of those four
components would have set it to `True`, correctly by its own lights.

> The value of a gate is not how strict it is. It is whether it is computed
> from the thing it protects, at the moment it protects it, by code that cannot
> be persuaded otherwise.

### A smaller note in the same shape

`intent_drift` reported `adds: 3, removes: 3` for this artifact — the three
secret-bearing lines, described as drift. That reading is *correct*: intent and
device genuinely did differ, because the render was broken. A drift report
tells the truth about a lie, and cannot tell you which it is looking at. Drift
is a symptom, never a diagnosis, which is the second reason it must not gate.

---

## A family of its own: real checks positioned where they cannot fail

Every other defect recorded here is a *transformation* bug — something correct
in isolation destroying what a neighbour depended on. This is a different
family, and it has now appeared three times, so it deserves naming separately.

The shape: **a check that is correctly written, correctly called, and placed
where it has nothing to check.** It is not a stub. It is not dead code. It
runs, it passes, and its passing means nothing.

| # | The check | Why it could not fail |
|---|---|---|
| 1 | `assert_no_negation(commands)` | the body was `return None` |
| 2 | approval's round-trip validation | validated `config_repo/templates/`; deploy rendered from `modules/nsot/templates/` |
| 3 | `assert_merge_only(to_push, intended)` | `to_push` *was* `intended`, so the subset test was trivially true |

Number one is the honest version — it never pretended to work, it just looked
like it did. Numbers two and three are worse, because both are real
implementations doing real comparisons. Nothing about reading them suggests a
problem. You have to ask a question that does not arise while writing the code:
*what would have to be true for this to fail?*

### Number three, in detail

`assert_merge_only()` enforces the project's central safety property: this tool
never synthesises a command to remove configuration a template does not
mention. It checks provenance — every pushed command must appear in the
intended config — which was itself a deliberate improvement over grepping for
`no`, since a template may legitimately contain `no ip http server`.

The implementation is right. The call site is right. And the pipeline was
handed the whole intended config as its command list, so the property being
checked was "is every line of X in X".

It would have passed on any input. Forever. Including inputs containing
synthesised negations, because those would have had to come *from* the intended
config to be in the list at all.

### What makes this family hard

The transformation bugs all have a detectable signature: two components, one
assumption, no shared owner. You can go looking for them by asking where data
crosses a boundary.

These have no signature. Each one is a single function that is correct.
The defect is in the *relationship between the check and its input*, and that
relationship is usually established somewhere else entirely — in number three's
case, one line in a different module:

```python
ctx.rendered_commands = {device_ip: prepared["config"].splitlines()}
```

Nothing about that line looks like it disables a safety check three files away.

### The question that finds them

Not "is this check correct" — all three were. The question is:

> **Construct the input that makes this check fail. If you cannot, it is not a
> check.**

For `assert_no_negation` there is no such input: the body ignores its argument.
For the template roots there is one, but it can never be produced, because the
two paths read different directories and only one of them is ever edited. For
`assert_merge_only` there is none while the caller passes the config to itself.

This is the same discipline as writing a test that fails before the fix. A
check nobody has ever seen fail is indistinguishable from a check that cannot.

### The cheap countermeasure

Every one of the three would have been caught by a single test asserting the
**negative**: hand the check something that must be rejected and assert it
raises. That test is two lines and it is the only one that proves the check is
load-bearing.

```python
def test_assert_merge_only_now_has_something_to_check(self):
    commands = merge_commands(INTENDED, RUNNING)
    assert_merge_only(commands, INTENDED)               # the real list passes
    with pytest.raises(NegationSynthesised):
        assert_merge_only(commands + ["no ip routing"], INTENDED)
```

The first line is the test everyone writes. The second is the one that matters.
Note that the second line could not have been written at all while the caller
passed the intended config to itself — there was no way to express a rejected
input. **An assertion you cannot write a failing case for is telling you
something about the code, not about your imagination.**
